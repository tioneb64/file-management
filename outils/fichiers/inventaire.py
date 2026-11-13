# outil: inventaire
# description: Liste les fichiers d'une arborescence (chemin relatif, nom, extension, taille, date de modification, SHA-256 avec --sha256) dans --sortie : .json ou .csv (UTF-8 avec BOM, separateur ;).
# parametre: --sortie FICHIER | obligatoire | inventaire a ecrire (.csv ou .json)
# parametre: --sans-recursion | facultatif | ne descend pas dans les sous-dossiers
# parametre: --sha256 | facultatif | ajoute l'empreinte SHA-256 de chaque fichier (relit tout)
# parametre: --ecraser | facultatif | remplace l'inventaire s'il existe
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
"""Dresse l'inventaire d'un dossier (chemin, taille, date, SHA-256 facultatif) en CSV ou JSON."""
import csv
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import ErreurParametres
from outils.commun.fichiers import sha256_fichier, sortie_atomique, verifier_ecrasement
from outils.commun.outil import Outil

OUTIL = Outil("inventaire", "Liste les fichiers d'une arborescence (chemin relatif, nom, extension, taille, date de "
              "modification, SHA-256 avec --sha256) dans --sortie : .json ou .csv (UTF-8 avec BOM, separateur ;). "
              "Utile pour tracer ce qu'une regle a livre ou pour controler une cible. Le recursif est actif par "
              "defaut (--sans-recursion pour le desactiver).", "fichiers")
COLONNES = ["chemin", "nom", "extension", "taille", "modification"]


@OUTIL.arguments
def arguments(p):
    options_entrees(p, recursif=False)
    p.add_argument("--sortie", required=True, metavar="FICHIER", help="inventaire a ecrire (.csv ou .json)")
    p.add_argument("--sans-recursion", action="store_true", help="ne descend pas dans les sous-dossiers")
    p.add_argument("--sha256", action="store_true", help="ajoute l'empreinte SHA-256 de chaque fichier (relit tout)")
    p.add_argument("--ecraser", action="store_true", help="remplace l'inventaire s'il existe")


@OUTIL.principal
def principal(ctx, args):
    if not args.sortie.lower().endswith((".csv", ".json")):
        raise ErreurParametres("--sortie : extension .csv ou .json")
    sortie = os.path.abspath(args.sortie)
    lignes = []
    for chemin, base in ctx.fichiers(recursif=not args.sans_recursion):
        if os.path.normcase(os.path.abspath(chemin)) == os.path.normcase(sortie):
            continue
        with ctx.tolerer("inventaire_echec", fichier=chemin):
            info = os.stat(chemin)
            ligne = {"chemin": os.path.relpath(chemin, base).replace("\\", "/"), "nom": os.path.basename(chemin),
                     "extension": os.path.splitext(chemin)[1].lower(), "taille": info.st_size,
                     "modification": datetime.fromtimestamp(info.st_mtime).isoformat(timespec="seconds")}
            if args.sha256:
                ligne["sha256"] = sha256_fichier(chemin)
            lignes.append(ligne)
            ctx.compter("fichiers")
    if not lignes:
        return
    if ctx.simulation:
        verifier_ecrasement(sortie, args.ecraser)
        ctx.action("inventaire_a_ecrire", "Inventaire serait ecrit (%d fichier(s)) : %s" % (len(lignes), os.path.basename(sortie)),
                   compteur=None, fichier=sortie)
        return
    with sortie_atomique(sortie, args.ecraser) as tmp:
        if sortie.lower().endswith(".json"):
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(lignes, f, ensure_ascii=False, indent=1)
        else:
            colonnes = COLONNES + (["sha256"] if args.sha256 else [])
            with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=colonnes, delimiter=";", lineterminator="\r\n")
                w.writeheader()
                w.writerows(lignes)
    ctx.action("inventaire_ecrit", "Inventaire ecrit (%d fichier(s)) : %s" % (len(lignes), os.path.basename(sortie)),
               compteur=None, fichier=sortie, taille=os.path.getsize(sortie))


if __name__ == "__main__":
    OUTIL.lancer()
