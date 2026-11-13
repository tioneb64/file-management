# outil: noms_normaliser
# description: Normalise les noms de fichiers : retire les accents (e), remplace les espaces (--espace-par, defaut _) et les caracteres interdits sous Windows (< > : " / \ | ? *) par _, supprime les points et espaces de fin, evite les noms reserves...
# parametre: --espace-par CAR | facultatif | remplace les espaces (defaut _ ; vide = supprimer)
# parametre: --garder-accents | facultatif | ne retire pas les accents
# parametre: --ascii | facultatif | tout caractere non ASCII restant devient _
# parametre: --minuscules | facultatif | met le nom entier en minuscules
# parametre: --longueur-max N | facultatif | longueur maximale du nom (defaut 200)
# parametre: --dossiers | facultatif | renomme aussi les dossiers designes ou trouves (du plus profond au plus haut)
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Normalise les noms de fichiers : accents, espaces, caracteres interdits sous Windows, noms reserves."""
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun import renommage
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import ErreurParametres
from outils.commun.outil import Outil

OUTIL = Outil("noms_normaliser", "Normalise les noms de fichiers : retire les accents (e), remplace les espaces "
              "(--espace-par, defaut _) et les caracteres interdits sous Windows (< > : \" / \\ | ? *) par _, "
              "supprime les points et espaces de fin, evite les noms reserves (CON, NUL, COM1...), borne la "
              "longueur. Un nom deja pris est une erreur de l'element (rien n'est ecrase).", "organisation")
RESERVES = {"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)} | {"LPT%d" % i for i in range(1, 10)}


@OUTIL.arguments
def arguments(p):
    options_entrees(p)
    p.add_argument("--espace-par", default="_", metavar="CAR", help="remplace les espaces (defaut _ ; vide = supprimer)")
    p.add_argument("--garder-accents", action="store_true", help="ne retire pas les accents")
    p.add_argument("--ascii", action="store_true", help="tout caractere non ASCII restant devient _")
    p.add_argument("--minuscules", action="store_true", help="met le nom entier en minuscules")
    p.add_argument("--longueur-max", type=int, default=200, metavar="N", help="longueur maximale du nom (defaut 200)")
    p.add_argument("--dossiers", action="store_true", help="renomme aussi les dossiers designes ou trouves (du plus profond au plus haut)")


def normaliser(nom, args):
    racine, ext = os.path.splitext(nom)
    texte = racine
    if not args.garder_accents:
        texte = "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c))
        texte = texte.replace("œ", "oe").replace("Œ", "OE").replace("æ", "ae").replace("Æ", "AE")
    if args.ascii:
        texte = re.sub(r"[^\x00-\x7f]", "_", texte)
    texte = re.sub(r"\s", args.espace_par, texte)
    texte = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", texte)
    texte = re.sub(r"_{2,}", "_", texte).strip(" .")
    ext = re.sub(r'[<>:"/\\|?*\x00-\x1f\s]', "_", ext.rstrip(". \t"))
    if args.minuscules:
        texte, ext = texte.lower(), ext.lower()
    if not texte:
        texte = "sans_nom"
    if texte.upper() in RESERVES:
        texte = "_" + texte
    return texte[:max(1, args.longueur_max - len(ext))] + ext


@OUTIL.principal
def principal(ctx, args):
    if args.longueur_max < 8:
        raise ErreurParametres("--longueur-max : au moins 8")
    plan = []
    for chemin, base in ctx.fichiers():
        with ctx.tolerer("normalisation_echec", fichier=chemin):
            dossier, nom = os.path.split(chemin)
            nouveau = normaliser(nom, args)
            if nouveau != nom:
                plan.append((chemin, os.path.join(dossier, nouveau)))
            else:
                ctx.debug("nom_deja_normal", "Nom deja normalise : %s" % nom, fichier=chemin)
    renommage.appliquer(ctx, plan)
    if args.dossiers and not ctx.simulation:
        _dossiers(ctx, args)
    elif args.dossiers:
        ctx.avertir("dossiers_non_simules", "--dossiers : les dossiers ne sont pas listes en simulation")


def _dossiers(ctx, args):
    racines = [c for c in ctx.designes() if os.path.isdir(c)]
    for racine in racines:
        for dossier, sous, _ in os.walk(racine, topdown=False):
            for nom in sous:
                complet = os.path.join(dossier, nom)
                nouveau = normaliser(nom, args)
                if nouveau != nom and not os.path.islink(complet):
                    renommage.appliquer(ctx, [(complet, os.path.join(dossier, nouveau))],
                                        evenement="dossier_renomme", libelle="Dossier renomme")


if __name__ == "__main__":
    OUTIL.lancer()
