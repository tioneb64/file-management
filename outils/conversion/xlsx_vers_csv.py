# outil: xlsx_vers_csv
# description: Convertit un .xlsx en CSV : une feuille (--feuille, defaut la premiere) ou toutes (--toutes-les-feuilles : <classeur>_<feuille>.csv).
# parametre: --vers DOSSIER | facultatif | dossier des CSV (defaut : a cote du classeur)
# parametre: --sortie FICHIER.csv | facultatif | nom du CSV (un seul classeur, une seule feuille)
# parametre: --feuille NOM_OU_NUMERO | facultatif | feuille a exporter : nom ou numero a partir de 1 (defaut 1)
# parametre: --toutes-les-feuilles | facultatif | un CSV par feuille
# parametre: --separateur CAR | facultatif | separateur de colonnes (defaut ;)
# parametre: --encodage NOM | facultatif | encodage du CSV (defaut utf-8-sig)
# parametre: --ecraser | facultatif | remplace un CSV existant
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
"""Convertit un classeur Excel (.xlsx) en CSV, sans Excel ni module externe (zip + XML de la bibliotheque standard)."""
import csv
import datetime
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import BUSINESS_RULE_VIOLATION, ErreurOutil, ErreurParametres
from outils.commun.fichiers import sortie_atomique, verifier_ecrasement
from outils.commun.outil import Outil

OUTIL = Outil("xlsx_vers_csv", "Convertit un .xlsx en CSV : une feuille (--feuille, defaut la premiere) ou toutes "
              "(--toutes-les-feuilles : <classeur>_<feuille>.csv). Les valeurs sont celles enregistrees dans le "
              "classeur (les formules ne sont pas recalculees) ; les dates deviennent AAAA-MM-JJ. CSV en UTF-8 "
              "avec BOM et separateur ; (ouvrable directement dans Excel en francais).", "conversion")
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
FORMATS_DATE_INTEGRES = set(range(14, 23)) | set(range(27, 37)) | set(range(45, 48)) | set(range(50, 59))
_RE_DATE_PERSO = re.compile(r"(?<![a-zA-Z])(yy|yyyy|d|dd|mmm|mmmm|m/d|d/m)(?![a-zA-Z])|h:mm|hh:mm", re.I)


@OUTIL.arguments
def arguments(p):
    options_entrees(p, recursif=False)
    p.add_argument("--vers", metavar="DOSSIER", help="dossier des CSV (defaut : a cote du classeur)")
    p.add_argument("--sortie", metavar="FICHIER.csv", help="nom du CSV (un seul classeur, une seule feuille)")
    p.add_argument("--feuille", metavar="NOM_OU_NUMERO", help="feuille a exporter : nom ou numero a partir de 1 (defaut 1)")
    p.add_argument("--toutes-les-feuilles", action="store_true", help="un CSV par feuille")
    p.add_argument("--separateur", default=";", metavar="CAR", help="separateur de colonnes (defaut ;)")
    p.add_argument("--encodage", default="utf-8-sig", metavar="NOM", help="encodage du CSV (defaut utf-8-sig)")
    p.add_argument("--ecraser", action="store_true", help="remplace un CSV existant")


def colonne(reference):
    """'AB12' -> 27 (index de colonne a partir de 0)."""
    lettres = re.match(r"[A-Za-z]+", reference).group(0).upper()
    n = 0
    for c in lettres:
        n = n * 26 + ord(c) - 64
    return n - 1


def _chaines(z):
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    racine = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])) for si in racine.findall("m:si", NS)]


def _styles_date(z):
    """Indices de style (cellXfs) dont le format est une date."""
    if "xl/styles.xml" not in z.namelist():
        return set()
    racine = ET.fromstring(z.read("xl/styles.xml"))
    perso = {}
    for nf in racine.findall("m:numFmts/m:numFmt", NS):
        code = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]', "", nf.get("formatCode", ""))
        perso[int(nf.get("numFmtId"))] = bool(_RE_DATE_PERSO.search(code))
    resultat = set()
    for i, xf in enumerate(racine.findall("m:cellXfs/m:xf", NS)):
        fid = int(xf.get("numFmtId", 0))
        if fid in FORMATS_DATE_INTEGRES or perso.get(fid):
            resultat.add(i)
    return resultat


def _feuilles(z):
    """[(nom, chemin dans le zip)] dans l'ordre du classeur."""
    classeur = ET.fromstring(z.read("xl/workbook.xml"))
    liens = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).findall("rel:Relationship", NS)}
    resultat = []
    for s in classeur.findall("m:sheets/m:sheet", NS):
        cible = liens[s.get("{%s}id" % NS["r"])]
        resultat.append((s.get("name"), cible.lstrip("/") if cible.startswith("/") else "xl/" + cible))
    return resultat


def _valeur(c, chaines, dates):
    type_, style = c.get("t"), int(c.get("s", 0))
    v = c.find("m:v", NS)
    if type_ == "inlineStr":
        return "".join(t.text or "" for t in c.iter("{%s}t" % NS["m"]))
    if v is None or v.text is None:
        return ""
    if type_ == "s":
        return chaines[int(v.text)]
    if type_ == "b":
        return "VRAI" if v.text == "1" else "FAUX"
    if type_ in ("str", "e"):
        return v.text
    if style in dates:
        try:
            jour = datetime.datetime(1899, 12, 30) + datetime.timedelta(days=float(v.text))
            return jour.strftime("%Y-%m-%d") if jour.hour == jour.minute == jour.second == 0 else jour.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OverflowError):
            return v.text
    texte = v.text
    try:
        nombre = float(texte)
        return str(int(nombre)) if nombre == int(nombre) and "E" not in texte.upper() else texte
    except ValueError:
        return texte


def exporter_feuille(z, chemin, chaines, dates, sortie, separateur, encodage):
    lignes = 0
    with open(sortie, "w", encoding=encodage, newline="") as f:
        w = csv.writer(f, delimiter=separateur)
        derniere = 0
        with z.open(chemin) as flux:
            for _, ligne in ET.iterparse(flux):
                if ligne.tag != "{%s}row" % NS["m"]:
                    continue
                numero = int(ligne.get("r", derniere + 1))
                for _ in range(numero - derniere - 1):
                    w.writerow([])
                derniere = numero
                valeurs = {}
                for c in ligne.findall("m:c", NS):
                    ref = c.get("r")
                    valeurs[colonne(ref) if ref else len(valeurs)] = _valeur(c, chaines, dates)
                w.writerow([valeurs.get(i, "") for i in range(max(valeurs) + 1)] if valeurs else [])
                lignes += 1
                ligne.clear()
    return lignes


@OUTIL.principal
def principal(ctx, args):
    if len(args.separateur) != 1:
        raise ErreurParametres("--separateur : un seul caractere")
    try:
        "".encode(args.encodage)
    except LookupError:
        raise ErreurParametres("encodage inconnu : %s" % args.encodage)
    classeurs = [c for c, _ in ctx.fichiers()]
    if args.sortie and (len(classeurs) > 1 or args.toutes_les_feuilles):
        raise ErreurParametres("--sortie ne va qu'avec un classeur et une feuille")
    for classeur in classeurs:
        with ctx.tolerer("conversion_echec", fichier=classeur):
            if not classeur.lower().endswith((".xlsx", ".xlsm")):
                raise ErreurOutil("format non pris en charge (xlsx ou xlsm attendu) : %s" % os.path.basename(classeur),
                                  BUSINESS_RULE_VIOLATION)
            try:
                z = zipfile.ZipFile(classeur)
            except zipfile.BadZipFile:
                raise ErreurOutil("classeur illisible (pas un xlsx valide) : %s" % os.path.basename(classeur))
            with z:
                feuilles = _feuilles(z)
                if not feuilles:
                    raise ErreurOutil("le classeur n'a aucune feuille : %s" % os.path.basename(classeur), BUSINESS_RULE_VIOLATION)
                if not args.toutes_les_feuilles:
                    choix = args.feuille or "1"
                    feuilles = [f for i, f in enumerate(feuilles, 1) if f[0] == choix or str(i) == choix]
                    if not feuilles:
                        raise ErreurOutil("feuille introuvable : %s" % choix, BUSINESS_RULE_VIOLATION)
                chaines, dates = _chaines(z), _styles_date(z)
                dossier = args.vers or os.path.dirname(os.path.abspath(classeur))
                racine = os.path.splitext(os.path.basename(classeur))[0]
                for nom, chemin in feuilles:
                    sortie = args.sortie or os.path.join(dossier, "%s%s.csv" % (
                        racine, "_" + re.sub(r'[<>:"/\\|?*]', "_", nom) if args.toutes_les_feuilles else ""))
                    if ctx.simulation:
                        verifier_ecrasement(sortie, args.ecraser)
                        ctx.action("feuille_a_convertir", "Serait convertie : %s (%s)" % (nom, os.path.basename(classeur)),
                                   fichier=classeur, cible=sortie, feuille=nom)
                        continue
                    with sortie_atomique(sortie, args.ecraser) as tmp:
                        lignes = exporter_feuille(z, chemin, chaines, dates, tmp, args.separateur, args.encodage)
                    ctx.action("feuille_convertie", "Feuille convertie : %s (%d ligne(s))" % (nom, lignes), fichier=classeur,
                               cible=sortie, feuille=nom, lignes=lignes)


if __name__ == "__main__":
    OUTIL.lancer()
