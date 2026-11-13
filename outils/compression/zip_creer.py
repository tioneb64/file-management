# outil: zip_creer
# description: Cree une archive zip a partir de fichiers et de dossiers (un dossier est range avec tout son contenu, sous son nom).
# parametre: --sortie ARCHIVE.zip | obligatoire | archive a creer
# parametre: --niveau 0-9 | facultatif | niveau de compression (defaut 6 ; 0 = stocke)
# parametre: --ecraser | facultatif | remplace l'archive si elle existe
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
"""Cree une archive zip (fichiers et dossiers) : ecriture atomique, rien n'est ecrase sans --ecraser."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun import archives
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import ErreurOutil
from outils.commun.fichiers import sortie_atomique, verifier_ecrasement
from outils.commun.outil import Outil

OUTIL = Outil("zip_creer", "Cree une archive zip a partir de fichiers et de dossiers (un dossier est range avec "
              "tout son contenu, sous son nom).", "compression")


@OUTIL.arguments
def arguments(p):
    options_entrees(p, recursif=False)
    p.add_argument("--sortie", required=True, metavar="ARCHIVE.zip", help="archive a creer")
    p.add_argument("--niveau", type=int, default=6, choices=range(0, 10), metavar="0-9",
                   help="niveau de compression (defaut 6 ; 0 = stocke)")
    p.add_argument("--ecraser", action="store_true", help="remplace l'archive si elle existe")


@OUTIL.principal
def principal(ctx, args):
    designes = ctx.designes()
    if not designes:
        return
    sortie = os.path.abspath(args.sortie)
    elements = archives.elements_a_archiver(ctx, designes, exclus=[sortie])
    if not elements:
        return
    if ctx.simulation:
        verifier_ecrasement(sortie, args.ecraser)
        for disque, nom, dossier in elements:
            ctx.action("fichier_a_archiver", "Serait ajoute a l'archive : %s" % nom.rstrip("/"), fichier=disque,
                       compteur="dossiers" if dossier else "fichiers")
        return
    with sortie_atomique(sortie, args.ecraser) as temporaire:
        archives.creer_zip(ctx, elements, temporaire, args.niveau)
        if ctx.nb_erreurs:
            raise ErreurOutil("archive incomplete, non creee (%d erreur(s) ci-dessus)" % ctx.nb_erreurs)
    ctx.info("archive_creee", "Archive creee : %s" % os.path.basename(sortie), fichier=sortie,
             taille=os.path.getsize(sortie))


if __name__ == "__main__":
    OUTIL.lancer()
