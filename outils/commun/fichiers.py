# bibliotheque: empreintes SHA-256, ecriture atomique, chemins surs, tailles et encodages communs aux outils
"""Aides communes sur les fichiers : empreintes, ecriture atomique, chemins surs, tailles, encodages."""
import contextlib
import hashlib
import os
import re

from outils.commun.erreurs import BUSINESS_RULE_VIOLATION, DUPLICATE_ENTITY, ErreurOutil, ErreurParametres

SUFFIXE_TEMPORAIRE = ".copie_en_cours"       # le moteur ignore les fichiers de ce suffixe
TAILLE_BLOC = 1024 * 1024
_RE_TAILLE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*([kmgt]?)(?:i?o|i?b)?\s*$", re.I)
_UNITES = {"": 1, "k": 1024, "m": 1024 ** 2, "g": 1024 ** 3, "t": 1024 ** 4}


def sha256_fichier(chemin, algorithme="sha256"):
    h = hashlib.new(algorithme)
    with open(chemin, "rb") as f:
        while True:
            bloc = f.read(TAILLE_BLOC)
            if not bloc:
                return h.hexdigest()
            h.update(bloc)


def lire_taille(texte):
    """'100M', '1,5G', '500Ko', '4096' -> octets. Leve ErreurParametres si illisible."""
    m = _RE_TAILLE.match(str(texte))
    if not m:
        raise ErreurParametres("taille illisible : '%s' (exemples : 4096, 500K, 100M, 1.5G)" % texte)
    octets = int(float(m.group(1).replace(",", ".")) * _UNITES[m.group(2).lower()])
    if octets <= 0:
        raise ErreurParametres("la taille doit etre positive : '%s'" % texte)
    return octets


def taille_lisible(octets):
    for unite in ("o", "Ko", "Mo", "Go"):
        if octets < 1024 or unite == "Go":
            return "%d %s" % (octets, unite) if unite == "o" else "%.1f %s" % (octets, unite)
        octets /= 1024.0


def verifier_ecrasement(chemin, ecraser):
    """Refuse d'ecraser un fichier existant sans --ecraser (DUPLICATE_ENTITY)."""
    if os.path.lexists(chemin) and not ecraser:
        raise ErreurOutil("le fichier existe deja (option --ecraser pour le remplacer) : %s" % chemin,
                          DUPLICATE_ENTITY)


@contextlib.contextmanager
def sortie_atomique(chemin, ecraser=False):
    """Fournit un chemin temporaire (suffixe .copie_en_cours) ; a la sortie sans erreur il est place sous
    son nom definitif (os.replace), sinon il est supprime. Rien n'est ecrase sans `ecraser`."""
    verifier_ecrasement(chemin, ecraser)
    dossier = os.path.dirname(os.path.abspath(chemin))
    os.makedirs(dossier, exist_ok=True)
    temporaire = chemin + SUFFIXE_TEMPORAIRE
    try:
        yield temporaire
        verifier_ecrasement(chemin, ecraser)
        os.replace(temporaire, chemin)
    finally:
        try:
            os.remove(temporaire)
        except OSError:
            pass


def est_dans(base, chemin):
    """Vrai si `chemin` (resolu) est `base` ou se trouve dessous."""
    base = os.path.normcase(os.path.realpath(base))
    chemin = os.path.normcase(os.path.realpath(chemin))
    try:
        return os.path.commonpath([base, chemin]) == base
    except ValueError:                      # disques differents
        return False


def chemin_sous(base, relatif):
    """Joint `relatif` (venant d'une archive, d'une liste...) a `base` ; refuse tout ce qui sort de `base`
    (chemin absolu, '..', lecteur, lien) : protection contre le zip-slip et la traversee de dossiers."""
    nom = relatif.replace("\\", "/")
    if nom.startswith("/") or re.match(r"^[A-Za-z]:", nom) or ".." in nom.split("/"):
        raise ErreurOutil("chemin dangereux refuse (hors du dossier de destination) : %s" % relatif,
                          BUSINESS_RULE_VIOLATION)
    complet = os.path.join(base, *[p for p in nom.split("/") if p not in ("", ".")])
    if not est_dans(base, os.path.dirname(complet) or base) or not est_dans(base, complet):
        raise ErreurOutil("chemin dangereux refuse (hors du dossier de destination) : %s" % relatif,
                          BUSINESS_RULE_VIOLATION)
    return complet


def lire_liste(chemin):
    """Fichier liste (un chemin par ligne, UTF-8 avec ou sans BOM), comme {liste} du moteur."""
    with open(chemin, encoding="utf-8-sig") as f:
        return [ligne.rstrip("\r\n") for ligne in f if ligne.strip()]


# --------------------------------------------------------------------------- #
# Encodages et texte
# --------------------------------------------------------------------------- #
BOMS = ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16"))


def detecter_encodage(octets):
    """Encodage probable d'un contenu : BOM, sinon UTF-8 strict, sinon cp1252 (ANSI occidental).
    Renvoie (encodage, certain) : `certain` est faux quand on a du se rabattre sur cp1252."""
    for bom, nom in BOMS:
        if octets.startswith(bom):
            return nom, True
    try:
        octets.decode("utf-8")
        return "utf-8", True
    except UnicodeDecodeError:
        pass
    try:
        octets.decode("cp1252")
    except UnicodeDecodeError:
        return "latin-1", False
    return "cp1252", False


def est_binaire(octets):
    """Contenu binaire : octet nul dans le debut (hors UTF-16 reconnu par son BOM)."""
    if octets.startswith((b"\xff\xfe", b"\xfe\xff")):
        return False
    return b"\x00" in octets[:8192]


def decouper_morceaux(chemin, taille_bloc=TAILLE_BLOC):
    with open(chemin, "rb") as f:
        while True:
            bloc = f.read(taille_bloc)
            if not bloc:
                return
            yield bloc


def encodage_fichier(chemin, echantillon=65536):
    """Encodage probable d'un fichier d'apres son debut (voir detecter_encodage). Renvoie
    (encodage, certain). Un caractere UTF-8 coupe par la fin de l'echantillon n'est pas une erreur."""
    with open(chemin, "rb") as f:
        debut = f.read(echantillon)
        complet = len(debut) < echantillon
    if not complet:
        for coupe in range(0, 4):
            try:
                debut[:len(debut) - coupe].decode("utf-8")
                debut = debut[:len(debut) - coupe]
                break
            except UnicodeDecodeError:
                continue
    return detecter_encodage(debut)


def copier_verifie(source, dest, ecraser=False):
    """Copie `source` vers `dest` (fichier temporaire, SHA-256 compare, puis renommage). Renvoie l'empreinte."""
    import shutil
    avant = sha256_fichier(source)
    with sortie_atomique(dest, ecraser) as tmp:
        shutil.copyfile(source, tmp)
        if sha256_fichier(tmp) != avant:
            raise ErreurOutil("la copie ne correspond pas a la source (SHA-256 different) : %s" % source)
        try:
            shutil.copystat(source, tmp)
        except OSError:
            pass
    return avant


def deplacer_fichier(source, dest, ecraser=False):
    """Deplace un fichier sans rien ecraser (sauf `ecraser`) : renommage sur le meme volume, sinon copie
    verifiee puis suppression de la source."""
    verifier_ecrasement(dest, ecraser)
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    try:
        if ecraser:
            os.replace(source, dest)
        else:
            os.rename(source, dest)
        return
    except OSError:
        if os.path.exists(source) is False or os.stat(source).st_dev == os.stat(os.path.dirname(os.path.abspath(dest))).st_dev:
            raise
    copier_verifie(source, dest, ecraser)
    os.remove(source)
