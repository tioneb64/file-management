# bibliotheque: date de prise de vue d'une photo JPEG (analyseur EXIF maison, bibliotheque standard seulement)
"""Date de prise de vue d'une photo JPEG : petit analyseur EXIF maison (bibliotheque standard seulement).

Lit le segment APP1 "Exif", l'en-tete TIFF, l'IFD principal puis l'IFD Exif : DateTimeOriginal (0x9003),
sinon DateTimeDigitized (0x9004), sinon DateTime (0x0132). Ne leve jamais : renvoie None si le fichier n'est
pas un JPEG, n'a pas d'EXIF ou est tronque.
"""
import struct
from datetime import datetime

TAGS_DATE = (0x9003, 0x9004, 0x0132)


def date_prise_de_vue(chemin):
    try:
        with open(chemin, "rb") as f:
            return _lire(f)
    except (OSError, struct.error, ValueError, IndexError):
        return None


def _lire(f):
    if f.read(2) != b"\xff\xd8":
        return None
    while True:
        marque = f.read(2)
        if len(marque) < 2 or marque[0] != 0xFF:
            return None
        if marque[1] in (0xDA, 0xD9):                  # debut des donnees image / fin : plus de metadonnees
            return None
        longueur = struct.unpack(">H", f.read(2))[0]
        corps = f.read(longueur - 2)
        if marque[1] == 0xE1 and corps.startswith(b"Exif\x00\x00"):
            return _lire_tiff(corps[6:])


def _lire_tiff(t):
    ordre = {b"II": "<", b"MM": ">"}.get(t[:2])
    if ordre is None or struct.unpack(ordre + "H", t[2:4])[0] != 42:
        return None
    ifd0 = struct.unpack(ordre + "I", t[4:8])[0]
    entrees = _ifd(t, ifd0, ordre)
    trouvees = {}
    if 0x8769 in entrees:
        trouvees.update(_ifd(t, struct.unpack(ordre + "I", entrees[0x8769][8:12])[0], ordre))
    for tag, valeur in entrees.items():
        trouvees.setdefault(tag, valeur)
    for tag in TAGS_DATE:
        if tag in trouvees:
            texte = _texte(t, trouvees[tag], ordre)
            try:
                return datetime.strptime(texte, "%Y:%m:%d %H:%M:%S")
            except ValueError:
                continue
    return None


def _ifd(t, decalage, ordre):
    """{tag: 12 octets de l'entree} d'un repertoire IFD."""
    nombre = struct.unpack(ordre + "H", t[decalage:decalage + 2])[0]
    resultat = {}
    for i in range(min(nombre, 512)):
        entree = t[decalage + 2 + 12 * i: decalage + 14 + 12 * i]
        if len(entree) == 12:
            resultat[struct.unpack(ordre + "H", entree[:2])[0]] = entree
    return resultat


def _texte(t, entree, ordre):
    type_, nombre = struct.unpack(ordre + "HI", entree[2:8])
    if type_ != 2:
        return ""
    brut = entree[8:12] if nombre <= 4 else t[struct.unpack(ordre + "I", entree[8:12])[0]:][:nombre]
    return brut[:nombre].split(b"\x00")[0].decode("ascii", "replace").strip()
