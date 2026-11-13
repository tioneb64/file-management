# outil: copier_verifie
# description: Copie des fichiers vers --vers : ecriture sous un nom temporaire (.copie_en_cours), relecture et comparaison du SHA-256 de la copie avec celui de la source, puis renommage.
# parametre: --vers DOSSIER | obligatoire | dossier de destination (cree si absent)
# parametre: --aplatir | facultatif | ne conserve pas l'arborescence des dossiers designes
# parametre: --ecraser | facultatif | remplace les fichiers existants
# parametre: --deplacer | facultatif | supprime la source une fois la copie verifiee
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Copie des fichiers avec verification SHA-256 (la copie est relue et comparee a la source)."""
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import RESOURCE_EXHAUSTED, ErreurOutil
from outils.commun.fichiers import copier_verifie, taille_lisible, verifier_ecrasement
from outils.commun.outil import Outil

OUTIL = Outil("copier_verifie", "Copie des fichiers vers --vers : ecriture sous un nom temporaire (.copie_en_cours), "
              "relecture et comparaison du SHA-256 de la copie avec celui de la source, puis renommage. Rien n'est "
              "ecrase sans --ecraser. Les dossiers designes sont copies avec leur arborescence "
              "(--aplatir pour tout mettre a plat). --deplacer supprime la source apres verification.", "fichiers")


@OUTIL.arguments
def arguments(p):
    options_entrees(p)
    p.add_argument("--vers", required=True, metavar="DOSSIER", help="dossier de destination (cree si absent)")
    p.add_argument("--aplatir", action="store_true", help="ne conserve pas l'arborescence des dossiers designes")
    p.add_argument("--ecraser", action="store_true", help="remplace les fichiers existants")
    p.add_argument("--deplacer", action="store_true", help="supprime la source une fois la copie verifiee")


@OUTIL.principal
def principal(ctx, args):
    vers = os.path.abspath(args.vers)
    for chemin, base in ctx.fichiers():
        with ctx.tolerer("copie_echec", fichier=chemin):
            relatif = os.path.basename(chemin) if args.aplatir else os.path.relpath(chemin, base)
            cible = os.path.join(vers, relatif)
            if os.path.normcase(os.path.abspath(chemin)) == os.path.normcase(cible):
                raise ErreurOutil("la source et la destination sont le meme fichier : %s" % chemin)
            if ctx.simulation:
                verifier_ecrasement(cible, args.ecraser)
                ctx.action("fichier_a_copier", "Serait copie : %s" % os.path.basename(chemin), fichier=chemin, cible=cible)
                continue
            taille = os.path.getsize(chemin)
            os.makedirs(os.path.dirname(cible), exist_ok=True)
            libre = shutil.disk_usage(os.path.dirname(cible)).free
            if libre < taille:
                raise ErreurOutil("espace insuffisant dans %s : %s necessaires, %s libres"
                                  % (os.path.dirname(cible), taille_lisible(taille), taille_lisible(libre)), RESOURCE_EXHAUSTED)
            empreinte = copier_verifie(chemin, cible, args.ecraser)
            ctx.action("fichier_copie", "Copie verifiee : %s" % os.path.basename(chemin), fichier=chemin, cible=cible,
                       taille=taille, sha256=empreinte)
            if args.deplacer:
                os.remove(chemin)
                ctx.info("fichier_supprime", "Source supprimee apres verification : %s" % os.path.basename(chemin), fichier=chemin)


if __name__ == "__main__":
    OUTIL.lancer()
