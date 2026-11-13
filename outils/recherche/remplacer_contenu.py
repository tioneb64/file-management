# outil: remplacer_contenu
# description: Remplace un texte (--chercher) par un autre (--remplacer) dans plusieurs fichiers texte, ou une expression reguliere avec --regex (\1 pour un groupe).
# parametre: --chercher TEXTE | obligatoire | texte (ou expression avec --regex) a remplacer
# parametre: --remplacer TEXTE | facultatif | texte de remplacement (defaut : vide = supprimer)
# parametre: --regex | facultatif | --chercher est une expression reguliere
# parametre: --ignorer-casse | facultatif | ignore majuscules et minuscules
# parametre: --encodage NOM | facultatif | auto (defaut) ou un encodage impose
# parametre: --sauvegarde | facultatif | garde l'original sous <fichier>.bak (--ecraser pour remplacer un .bak)
# parametre: --ecraser | facultatif | autorise le remplacement d'un .bak existant
# parametre: --garder-date | facultatif | conserve la date de modification d'origine
# parametre: --taille-max TAILLE | facultatif | taille maximale d'un fichier (il est lu en entier ; defaut 200M)
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Chercher / remplacer en masse dans le contenu de fichiers texte, en gardant leur encodage et leurs fins de ligne."""
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import BUSINESS_RULE_VIOLATION, ErreurOutil, ErreurParametres, RESOURCE_EXHAUSTED
from outils.commun.fichiers import est_binaire, lire_taille, sortie_atomique, taille_lisible, verifier_ecrasement
from outils.commun.outil import Outil

OUTIL = Outil("remplacer_contenu", "Remplace un texte (--chercher) par un autre (--remplacer) dans plusieurs fichiers "
              "texte, ou une expression reguliere avec --regex (\\1 pour un groupe). L'encodage (BOM, UTF-8, "
              "ANSI cp1252) et les fins de ligne sont conserves ; un fichier sans occurrence n'est pas touche ; "
              "--sauvegarde garde l'original en .bak. Fichiers binaires ignores.", "recherche")


@OUTIL.arguments
def arguments(p):
    options_entrees(p)
    p.add_argument("--chercher", required=True, metavar="TEXTE", help="texte (ou expression avec --regex) a remplacer")
    p.add_argument("--remplacer", default="", metavar="TEXTE", help="texte de remplacement (defaut : vide = supprimer)")
    p.add_argument("--regex", action="store_true", help="--chercher est une expression reguliere")
    p.add_argument("--ignorer-casse", action="store_true", help="ignore majuscules et minuscules")
    p.add_argument("--encodage", default="auto", metavar="NOM", help="auto (defaut) ou un encodage impose")
    p.add_argument("--sauvegarde", action="store_true", help="garde l'original sous <fichier>.bak (--ecraser pour remplacer un .bak)")
    p.add_argument("--ecraser", action="store_true", help="autorise le remplacement d'un .bak existant")
    p.add_argument("--garder-date", action="store_true", help="conserve la date de modification d'origine")
    p.add_argument("--taille-max", default="200M", metavar="TAILLE",
                   help="taille maximale d'un fichier (il est lu en entier ; defaut 200M)")


def _decoder(octets, encodage):
    if encodage != "auto":
        return octets.decode(encodage), encodage
    for bom, nom in ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16")):
        if octets.startswith(bom):
            return octets.decode(nom), nom
    try:
        return octets.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return octets.decode("cp1252", "strict"), "cp1252"


@OUTIL.principal
def principal(ctx, args):
    if not args.chercher:
        raise ErreurParametres("--chercher ne peut pas etre vide")
    maxi = lire_taille(args.taille_max)
    drapeaux = re.I if args.ignorer_casse else 0
    try:
        motif = re.compile(args.chercher if args.regex else re.escape(args.chercher), drapeaux)
        remplacement = args.remplacer if args.regex else args.remplacer.replace("\\", "\\\\")
        motif.sub(remplacement, "")
    except (re.error, IndexError) as e:
        raise ErreurParametres("expression ou remplacement invalide : %s" % e)
    if args.encodage != "auto":
        try:
            "".encode(args.encodage)
        except LookupError:
            raise ErreurParametres("encodage inconnu : %s" % args.encodage)
    for chemin, _ in ctx.fichiers():
        with ctx.tolerer("remplacement_echec", fichier=chemin):
            taille = os.path.getsize(chemin)
            if taille > maxi:
                raise ErreurOutil("fichier trop gros pour un remplacement (%s, limite %s)"
                                  % (taille_lisible(taille), taille_lisible(maxi)), RESOURCE_EXHAUSTED)
            with open(chemin, "rb") as f:
                octets = f.read()
            if est_binaire(octets):
                ctx.compter("binaires_ignores")
                continue
            try:
                texte, encodage = _decoder(octets, args.encodage)
            except UnicodeDecodeError as e:
                raise ErreurOutil("contenu illisible avec l'encodage choisi : %s" % e, BUSINESS_RULE_VIOLATION)
            nouveau, nombre = motif.subn(remplacement, texte)
            if not nombre or nouveau == texte:
                ctx.compter("sans_occurrence")
                continue
            if ctx.simulation:
                ctx.action("fichier_a_modifier", "Serait modifie (%d remplacement(s)) : %s"
                           % (nombre, os.path.basename(chemin)), fichier=chemin, remplacements=nombre)
                continue
            try:
                sortie = nouveau.encode(encodage)
            except UnicodeEncodeError as e:
                raise ErreurOutil("le texte de remplacement n'est pas representable en %s : %s" % (encodage, e),
                                  BUSINESS_RULE_VIOLATION)
            if args.sauvegarde:
                verifier_ecrasement(chemin + ".bak", args.ecraser)
                shutil.copy2(chemin, chemin + ".bak")
            date = os.stat(chemin)
            with sortie_atomique(chemin, ecraser=True) as tmp:
                with open(tmp, "wb") as f:
                    f.write(sortie)
                shutil.copymode(chemin, tmp)
            if args.garder_date:
                os.utime(chemin, ns=(date.st_atime_ns, date.st_mtime_ns))
            ctx.action("fichier_modifie", "Modifie (%d remplacement(s)) : %s" % (nombre, os.path.basename(chemin)),
                       fichier=chemin, remplacements=nombre, encodage=encodage)
            ctx.compter("remplacements", nombre)


if __name__ == "__main__":
    OUTIL.lancer()
