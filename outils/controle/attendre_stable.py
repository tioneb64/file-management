# outil: attendre_stable
# description: Attend que chaque fichier ne change plus (taille et date de modification inchangees pendant --duree-stable secondes) et ne soit plus verrouille (ouverture en lecture-ecriture possible).
# parametre: --duree-stable SEC | facultatif | duree sans changement (defaut 5)
# parametre: --delai-max SEC | facultatif | delai maximal par fichier (defaut 300)
# parametre: --intervalle SEC | facultatif | pas de la surveillance (defaut 1)
# parametre: --sans-verrou | facultatif | ne controle pas le verrou, seulement la stabilite
# parametre: --attendre-existence | facultatif | attend aussi que le fichier apparaisse
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
"""Attend qu'un fichier soit stable (taille et date inchangees) et non verrouille."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import FILE_IO_ERROR, FILE_NOT_FOUND, TIMEOUT, ErreurOutil, ErreurParametres
from outils.commun.outil import Outil

OUTIL = Outil("attendre_stable", "Attend que chaque fichier ne change plus (taille et date de modification inchangees "
              "pendant --duree-stable secondes) et ne soit plus verrouille (ouverture en lecture-ecriture possible). "
              "Sert a ne pas livrer un fichier encore en cours d'ecriture par un autre programme. Delai depasse : "
              "erreur (code 2). --attendre-existence attend aussi son apparition.", "controle")


@OUTIL.arguments
def arguments(p):
    options_entrees(p, recursif=False)
    p.add_argument("--duree-stable", type=float, default=5.0, metavar="SEC", help="duree sans changement (defaut 5)")
    p.add_argument("--delai-max", type=float, default=300.0, metavar="SEC", help="delai maximal par fichier (defaut 300)")
    p.add_argument("--intervalle", type=float, default=1.0, metavar="SEC", help="pas de la surveillance (defaut 1)")
    p.add_argument("--sans-verrou", action="store_true", help="ne controle pas le verrou, seulement la stabilite")
    p.add_argument("--attendre-existence", action="store_true", help="attend aussi que le fichier apparaisse")


def verrouille(chemin):
    """Vrai si le fichier ne peut pas etre ouvert pour ecriture (autre programme qui le garde)."""
    try:
        with open(chemin, "r+b"):
            return False
    except PermissionError:
        if not os.access(chemin, os.W_OK):               # lecture seule : le verrou se teste en lecture
            try:
                with open(chemin, "rb"):
                    return False
            except OSError:
                return True
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return True


@OUTIL.principal
def principal(ctx, args):
    if min(args.duree_stable, args.intervalle) < 0 or args.delai_max <= 0 or args.intervalle == 0:
        raise ErreurParametres("durees positives attendues")
    chemins = ctx.designes()
    for chemin in chemins:
        with ctx.tolerer("attente_echec", fichier=chemin):
            debut = time.monotonic()
            precedent, depuis = None, None
            while True:
                if not os.path.isfile(chemin):
                    if not args.attendre_existence:
                        raise ErreurOutil("fichier introuvable : %s" % chemin, FILE_NOT_FOUND)
                    precedent = depuis = None
                else:
                    info = os.stat(chemin)
                    signature = (info.st_size, info.st_mtime_ns)
                    if signature != precedent:
                        precedent, depuis = signature, time.monotonic()
                    stable = time.monotonic() - depuis >= args.duree_stable
                    if stable and (args.sans_verrou or not verrouille(chemin)):
                        ctx.action("fichier_stable", "Fichier stable : %s" % os.path.basename(chemin), fichier=chemin,
                                   taille=info.st_size, attente_ms=int((time.monotonic() - debut) * 1000))
                        break
                if time.monotonic() - debut >= args.delai_max:
                    if precedent is None:
                        raise ErreurOutil("fichier jamais apparu apres %d s : %s" % (args.delai_max, chemin), FILE_NOT_FOUND)
                    raise ErreurOutil("fichier encore instable ou verrouille apres %d s : %s" % (args.delai_max, chemin),
                                      TIMEOUT if not args.sans_verrou else FILE_IO_ERROR)
                time.sleep(min(args.intervalle, max(0.01, args.delai_max - (time.monotonic() - debut))))


if __name__ == "__main__":
    OUTIL.lancer()
