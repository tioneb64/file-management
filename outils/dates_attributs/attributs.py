# outil: attributs
# description: Modifie les attributs Windows de fichiers (--lecture-seule, --cache, --systeme, --archive : oui ou non ; les autres attributs sont conserves) ou les affiche (--afficher).
# parametre: --lecture-seule {oui,non} | facultatif | attribut lecture seule
# parametre: --cache {oui,non} | facultatif | attribut cache
# parametre: --systeme {oui,non} | facultatif | attribut systeme
# parametre: --archive {oui,non} | facultatif | attribut archive
# parametre: --afficher | facultatif | affiche les attributs sans rien modifier
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Lit ou modifie les attributs de fichiers : lecture seule, cache, systeme, archive."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun import winfs
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import ErreurParametres
from outils.commun.outil import Outil

OUTIL = Outil("attributs", "Modifie les attributs Windows de fichiers (--lecture-seule, --cache, --systeme, "
              "--archive : oui ou non ; les autres attributs sont conserves) ou les affiche (--afficher). Hors "
              "Windows, seule la lecture seule existe.", "dates_attributs")


@OUTIL.arguments
def arguments(p):
    options_entrees(p)
    p.add_argument("--lecture-seule", choices=("oui", "non"), help="attribut lecture seule")
    p.add_argument("--cache", choices=("oui", "non"), help="attribut cache")
    p.add_argument("--systeme", choices=("oui", "non"), help="attribut systeme")
    p.add_argument("--archive", choices=("oui", "non"), help="attribut archive")
    p.add_argument("--afficher", action="store_true", help="affiche les attributs sans rien modifier")


@OUTIL.principal
def principal(ctx, args):
    changements = {nom: valeur == "oui" for nom, valeur in (
        ("lecture_seule", args.lecture_seule), ("cache", args.cache), ("systeme", args.systeme),
        ("archive", args.archive)) if valeur}
    if not changements and not args.afficher:
        raise ErreurParametres("rien a faire : indiquer --lecture-seule, --cache, --systeme, --archive ou --afficher")
    for chemin, _ in ctx.fichiers():
        with ctx.tolerer("attributs_echec", fichier=chemin):
            actuels = winfs.lire_attributs(chemin)
            if args.afficher and not changements:
                ctx.afficher("%s : %s" % (chemin, " ".join(n for n, v in actuels.items() if v) or "aucun"))
                ctx.action("attributs_lus", "Attributs lus : %s" % os.path.basename(chemin), fichier=chemin,
                           compteur="lus", **actuels)
                continue
            utiles = {n: v for n, v in changements.items() if actuels[n] != v}
            if not utiles:
                ctx.compter("deja_conformes")
                continue
            if ctx.simulation:
                ctx.action("attributs_a_modifier", "Attributs seraient modifies : %s" % os.path.basename(chemin),
                           fichier=chemin, **utiles)
                continue
            winfs.fixer_attributs(chemin, utiles)
            ctx.action("attributs_modifies", "Attributs modifies : %s" % os.path.basename(chemin), fichier=chemin, **utiles)


if __name__ == "__main__":
    OUTIL.lancer()
