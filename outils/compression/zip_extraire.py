# outil: zip_extraire
# description: Extrait des archives zip dans un dossier.
# parametre: --vers DOSSIER | obligatoire | dossier de destination (cree si absent)
# parametre: --un-dossier-par-archive | facultatif | extrait chaque archive dans un sous-dossier portant son nom
# parametre: --ecraser | facultatif | remplace les fichiers existants
# parametre: --taille-max TAILLE | facultatif | taille maximale une fois extrait, par archive (defaut 20G ; protege des zip bombes)
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --mot-de-passe-env NOM | facultatif | nom de la variable d'environnement qui contient le mot de passe
# parametre: --mot-de-passe-fichier FICHIER | facultatif | fichier (UTF-8) dont la premiere ligne est le mot de passe
"""Extrait des archives zip (mot de passe possible) vers un dossier, en refusant les chemins dangereux."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun import archives
from outils.commun.entrees import options_entrees
from outils.commun.fichiers import lire_taille
from outils.commun.outil import Outil
from outils.commun.secret import lire_mot_de_passe, options_mot_de_passe

OUTIL = Outil("zip_extraire", "Extrait des archives zip dans un dossier. Refuse les chemins qui sortent du "
              "dossier de destination (zip-slip), n'ecrase rien sans --ecraser, limite la taille extraite.",
              "compression")


@OUTIL.arguments
def arguments(p):
    options_entrees(p, recursif=False)
    p.add_argument("--vers", required=True, metavar="DOSSIER", help="dossier de destination (cree si absent)")
    p.add_argument("--un-dossier-par-archive", action="store_true",
                   help="extrait chaque archive dans un sous-dossier portant son nom")
    p.add_argument("--ecraser", action="store_true", help="remplace les fichiers existants")
    p.add_argument("--taille-max", default="20G", metavar="TAILLE",
                   help="taille maximale une fois extrait, par archive (defaut 20G ; protege des zip bombes)")
    options_mot_de_passe(p)


@OUTIL.principal
def principal(ctx, args):
    taille_max = lire_taille(args.taille_max)
    secret = lire_mot_de_passe(args, ctx.env)
    for archive, _ in ctx.fichiers(dossiers=True):
        with ctx.tolerer("extraction_archive_echec", fichier=archive):
            vers = os.path.join(args.vers, os.path.splitext(os.path.basename(archive))[0]) \
                if args.un_dossier_par_archive else args.vers
            archives.extraire_archive(ctx, archive, vers, args.ecraser, secret, taille_max, formats=("zip",),
                                      env=ctx.env)


if __name__ == "__main__":
    OUTIL.lancer()
