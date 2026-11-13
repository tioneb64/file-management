# outil: chercher_contenu
# description: Cherche un texte (--texte) ou une expression reguliere (--regex) dans le contenu de fichiers.
# parametre: --texte TEXTE | facultatif | texte exact a chercher
# parametre: --regex EXPR | facultatif | expression reguliere a chercher dans chaque ligne
# parametre: --ignorer-casse | facultatif | ignore majuscules et minuscules
# parametre: --encodage NOM | facultatif | auto (defaut) ou un encodage impose (utf-8, cp1252, latin-1, utf-16...)
# parametre: --liste-fichiers-seulement | facultatif | n'affiche que les noms de fichiers, une fois chacun
# parametre: --sortie-liste FICHIER | facultatif | ecrit les fichiers qui contiennent le motif (un par ligne)
# parametre: --max-affiches N | facultatif | nombre de lignes reprises sur la sortie standard (defaut 50)
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Cherche un texte ou une expression reguliere dans le contenu des fichiers (comme grep), encodage detecte."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import ErreurParametres
from outils.commun.fichiers import encodage_fichier, est_binaire
from outils.commun.outil import Outil

OUTIL = Outil("chercher_contenu", "Cherche un texte (--texte) ou une expression reguliere (--regex) dans le contenu "
              "de fichiers. L'encodage de chaque fichier est detecte (BOM, UTF-8, sinon ANSI cp1252) ; les "
              "fichiers binaires sont ignores. Sortie : fichier:ligne:texte. Code retour 1 si rien n'est trouve "
              "et --code-si-rien 1.", "recherche")


@OUTIL.arguments
def arguments(p):
    options_entrees(p)
    p.add_argument("--texte", metavar="TEXTE", help="texte exact a chercher")
    p.add_argument("--regex", metavar="EXPR", help="expression reguliere a chercher dans chaque ligne")
    p.add_argument("--ignorer-casse", action="store_true", help="ignore majuscules et minuscules")
    p.add_argument("--encodage", default="auto", metavar="NOM",
                   help="auto (defaut) ou un encodage impose (utf-8, cp1252, latin-1, utf-16...)")
    p.add_argument("--liste-fichiers-seulement", action="store_true",
                   help="n'affiche que les noms de fichiers, une fois chacun")
    p.add_argument("--sortie-liste", metavar="FICHIER", help="ecrit les fichiers qui contiennent le motif (un par ligne)")
    p.add_argument("--max-affiches", type=int, default=50, metavar="N",
                   help="nombre de lignes reprises sur la sortie standard (defaut 50)")


@OUTIL.principal
def principal(ctx, args):
    if bool(args.texte) == bool(args.regex):
        raise ErreurParametres("indiquer --texte OU --regex")
    try:
        motif = re.compile(re.escape(args.texte) if args.texte else args.regex, re.I if args.ignorer_casse else 0)
    except re.error as e:
        raise ErreurParametres("expression reguliere invalide : %s" % e)
    if args.encodage != "auto":
        try:
            "".encode(args.encodage)
        except LookupError:
            raise ErreurParametres("encodage inconnu : %s" % args.encodage)
    fichiers_trouves, nb_lignes, affiches = [], 0, 0
    for chemin, _ in ctx.fichiers():
        with ctx.tolerer("lecture_echec", fichier=chemin):
            with open(chemin, "rb") as f:
                if est_binaire(f.read(8192)):
                    ctx.compter("binaires_ignores")
                    ctx.debug("fichier_binaire_ignore", "Fichier binaire ignore : %s" % os.path.basename(chemin),
                              fichier=chemin)
                    continue
            encodage = args.encodage if args.encodage != "auto" else encodage_fichier(chemin)[0]
            ctx.compter("fichiers_lus")
            trouve = 0
            with open(chemin, encoding=encodage, errors="replace", newline="") as f:
                for numero, ligne in enumerate(f, 1):
                    if motif.search(ligne):
                        trouve += 1
                        if not args.liste_fichiers_seulement and affiches < args.max_affiches:
                            ctx.afficher("%s:%d:%s" % (chemin, numero, ligne.rstrip("\r\n")[:300]))
                            affiches += 1
            if trouve:
                fichiers_trouves.append(chemin)
                nb_lignes += trouve
                if args.liste_fichiers_seulement and affiches < args.max_affiches:
                    ctx.afficher(chemin)
                    affiches += 1
                ctx.action("contenu_trouve", "%d ligne(s) trouvee(s) dans %s" % (trouve, os.path.basename(chemin)),
                           compteur="fichiers_trouves", fichier=chemin, lignes=trouve, encodage=encodage)
    if fichiers_trouves:
        ctx.compteurs["lignes_trouvees"] = nb_lignes
        if args.sortie_liste and not ctx.simulation:
            with open(args.sortie_liste, "w", encoding="utf-8", newline="\n") as f:
                f.write("".join(c + "\n" for c in fichiers_trouves))
        if affiches >= args.max_affiches and nb_lignes > affiches:
            ctx.afficher("... resultats suivants non affiches (voir le journal ou --sortie-liste)")


if __name__ == "__main__":
    OUTIL.lancer()
