# outil: dossiers_vides_supprimer
# description: Supprime les sous-dossiers vides des dossiers designes, du plus profond au plus haut (un dossier qui ne contient plus que des dossiers vides l'est aussi).
# parametre: --racine | facultatif | supprime aussi le dossier designe s'il devient vide
# parametre: --ignorer JOKER | facultatif | fichiers consideres comme absents (et supprimes avec le dossier) ; repetable
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
"""Supprime les dossiers vides d'une arborescence."""
import fnmatch
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import BUSINESS_RULE_VIOLATION, FILE_NOT_FOUND, ErreurOutil
from outils.commun.outil import Outil

OUTIL = Outil("dossiers_vides_supprimer", "Supprime les sous-dossiers vides des dossiers designes, du plus profond au "
              "plus haut (un dossier qui ne contient plus que des dossiers vides l'est aussi). Les dossiers designes "
              "eux-memes sont conserves, sauf avec --racine. --ignorer traite comme absents certains fichiers "
              "(ex. Thumbs.db, desktop.ini : ils sont alors supprimes avec le dossier). Les liens et jonctions ne "
              "sont jamais suivis ni supprimes ; une racine de disque est refusee.", "fichiers")


@OUTIL.arguments
def arguments(p):
    options_entrees(p, recursif=False, masques=False)
    p.add_argument("--racine", action="store_true", help="supprime aussi le dossier designe s'il devient vide")
    p.add_argument("--ignorer", action="append", default=[], metavar="JOKER",
                   help="fichiers consideres comme absents (et supprimes avec le dossier) ; repetable")


def est_vide(dossier, ignorer, a_supprimer):
    noms = os.listdir(dossier)
    restants = [n for n in noms if not any(fnmatch.fnmatchcase(n.lower(), m.lower()) for m in ignorer)
                or os.path.isdir(os.path.join(dossier, n))]
    if restants:
        return False
    a_supprimer.extend(os.path.join(dossier, n) for n in noms)
    return True


@OUTIL.principal
def principal(ctx, args):
    for racine in ctx.designes():
        racine = os.path.abspath(racine)
        with ctx.tolerer("dossier_echec", fichier=racine):
            if not os.path.isdir(racine):
                raise ErreurOutil("dossier introuvable : %s" % racine, FILE_NOT_FOUND)
            if os.path.dirname(racine) == racine:
                raise ErreurOutil("racine de disque refusee : %s" % racine, BUSINESS_RULE_VIOLATION)
            supprimes = set()
            for dossier, sous, _ in os.walk(racine, topdown=False):
                if os.path.islink(dossier) or (dossier == racine and not args.racine):
                    continue
                with ctx.tolerer("suppression_echec", fichier=dossier):
                    fichiers_ignores = []
                    if ctx.simulation:
                        contenu = [n for n in os.listdir(dossier) if os.path.join(dossier, n) not in supprimes]
                        vide = all(any(fnmatch.fnmatchcase(n.lower(), m.lower()) for m in args.ignorer)
                                   and not os.path.isdir(os.path.join(dossier, n)) for n in contenu)
                    else:
                        vide = est_vide(dossier, args.ignorer, fichiers_ignores)
                    if not vide:
                        continue
                    if ctx.simulation:
                        supprimes.add(dossier)
                        ctx.action("dossier_a_supprimer", "Dossier vide serait supprime : %s" % os.path.basename(dossier),
                                   compteur="supprimes", fichier=dossier)
                        continue
                    for f in fichiers_ignores:
                        os.remove(f)
                    os.rmdir(dossier)
                    ctx.action("dossier_supprime", "Dossier vide supprime : %s" % os.path.basename(dossier),
                               compteur="supprimes", fichier=dossier)


if __name__ == "__main__":
    OUTIL.lancer()
