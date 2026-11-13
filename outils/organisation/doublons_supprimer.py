# outil: doublons_supprimer
# description: Dedoublonne par contenu (taille puis SHA-256) : dans chaque groupe un original est conserve (--garder), les copies sont supprimees (--action supprimer) ou deplacees dans un dossier de quarantaine (--action deplacer --vers DOSSIER,...
# parametre: --action {supprimer,deplacer} | obligatoire | que faire des copies
# parametre: --vers DOSSIER | facultatif | quarantaine pour --action deplacer (la hierarchie n'est pas conservee)
# parametre: --garder {plus-ancien,plus-recent,premier,chemin-court} | facultatif | original conserve : le plus ancien (defaut), le plus recent, le premier par ordre alphabetique ou le chemin le plus court
# parametre: --inclure-vides | facultatif | traite aussi les fichiers vides (ignores par defaut)
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Dedoublonne : supprime ou met de cote les copies en trop de fichiers de meme contenu (SHA-256)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun import doublons
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import ErreurParametres
from outils.commun.fichiers import deplacer_fichier
from outils.commun.outil import Outil

OUTIL = Outil("doublons_supprimer", "Dedoublonne par contenu (taille puis SHA-256) : dans chaque groupe un original "
              "est conserve (--garder), les copies sont supprimees (--action supprimer) ou deplacees dans un "
              "dossier de quarantaine (--action deplacer --vers DOSSIER, recommande). L'action est obligatoire : "
              "rien n'est jamais supprime par defaut. Essayer d'abord avec --simulation.", "organisation")


@OUTIL.arguments
def arguments(p):
    options_entrees(p)
    p.add_argument("--action", required=True, choices=("supprimer", "deplacer"), help="que faire des copies")
    p.add_argument("--vers", metavar="DOSSIER", help="quarantaine pour --action deplacer (la hierarchie n'est pas conservee)")
    p.add_argument("--garder", choices=doublons.CRITERES, default="plus-ancien",
                   help="original conserve : le plus ancien (defaut), le plus recent, le premier par ordre alphabetique ou le chemin le plus court")
    p.add_argument("--inclure-vides", action="store_true", help="traite aussi les fichiers vides (ignores par defaut)")


@OUTIL.principal
def principal(ctx, args):
    if args.action == "deplacer" and not args.vers:
        raise ErreurParametres("--action deplacer exige --vers DOSSIER")
    chemins = [c for c, _ in ctx.fichiers()]
    for empreinte, taille, membres in doublons.grouper(ctx, chemins, 0 if args.inclure_vides else 1):
        original = doublons.choisir_original(membres, args.garder)
        for copie in [m for m in membres if m != original]:
            with ctx.tolerer("dedoublonnage_echec", fichier=copie):
                if ctx.simulation:
                    ctx.action("copie_a_traiter", "Serait %s (doublon de %s) : %s"
                               % ("supprimee" if args.action == "supprimer" else "deplacee", os.path.basename(original),
                                  os.path.basename(copie)), compteur="copies", fichier=copie, original=original,
                               sha256=empreinte, taille=taille)
                    continue
                if args.action == "supprimer":
                    os.remove(copie)
                    ctx.action("fichier_supprime", "Doublon supprime (copie de %s) : %s"
                               % (os.path.basename(original), os.path.basename(copie)), compteur="supprimes",
                               fichier=copie, original=original, sha256=empreinte, taille=taille)
                else:
                    cible = os.path.join(args.vers, "%s_%s" % (empreinte[:8], os.path.basename(copie)))
                    deplacer_fichier(copie, cible)
                    ctx.action("fichier_deplace", "Doublon deplace (copie de %s) : %s"
                               % (os.path.basename(original), os.path.basename(copie)), compteur="deplaces",
                               fichier=copie, cible=cible, original=original, sha256=empreinte, taille=taille)


if __name__ == "__main__":
    OUTIL.lancer()
