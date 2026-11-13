# outil: doublons_trouver
# description: Detecte les doublons par contenu (taille, puis SHA-256 : jamais le nom ni la date).
# parametre: --garder {plus-ancien,plus-recent,premier,chemin-court} | facultatif | original d'un groupe : le plus ancien (defaut), le plus recent, le premier par ordre alphabetique, ou le chemin le plus court
# parametre: --inclure-vides | facultatif | compte aussi les fichiers vides (ignores par defaut)
# parametre: --rapport FICHIER | facultatif | rapport des groupes (.json ou .csv)
# parametre: --sortie-liste FICHIER | facultatif | liste des copies en trop (un chemin par ligne)
# parametre: --ecraser | facultatif | remplace le rapport et la liste s'ils existent
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Detecte les fichiers en double par contenu (taille puis SHA-256) et produit un rapport."""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun import doublons
from outils.commun.entrees import options_entrees
from outils.commun.fichiers import sortie_atomique, taille_lisible
from outils.commun.outil import Outil

OUTIL = Outil("doublons_trouver", "Detecte les doublons par contenu (taille, puis SHA-256 : jamais le nom ni la "
              "date). Ne modifie rien. --rapport ecrit les groupes (.json ou .csv) ; --sortie-liste ecrit les "
              "copies en trop (tout sauf l'original choisi par --garder), utilisable comme {liste}. Pour agir sur "
              "les doublons : doublons_supprimer.", "recherche")


@OUTIL.arguments
def arguments(p):
    options_entrees(p)
    p.add_argument("--garder", choices=doublons.CRITERES, default="plus-ancien",
                   help="original d'un groupe : le plus ancien (defaut), le plus recent, le premier par ordre "
                        "alphabetique, ou le chemin le plus court")
    p.add_argument("--inclure-vides", action="store_true", help="compte aussi les fichiers vides (ignores par defaut)")
    p.add_argument("--rapport", metavar="FICHIER", help="rapport des groupes (.json ou .csv)")
    p.add_argument("--sortie-liste", metavar="FICHIER", help="liste des copies en trop (un chemin par ligne)")
    p.add_argument("--ecraser", action="store_true", help="remplace le rapport et la liste s'ils existent")


@OUTIL.principal
def principal(ctx, args):
    chemins = [c for c, _ in ctx.fichiers()]
    groupes = doublons.grouper(ctx, chemins, 0 if args.inclure_vides else 1)
    ctx.compter("fichiers_examines", len(chemins))
    if not groupes:
        return
    en_trop, octets_perdus, lignes = [], 0, []
    for empreinte, taille, membres in groupes:
        original = doublons.choisir_original(membres, args.garder)
        copies = [m for m in membres if m != original]
        en_trop.extend(copies)
        octets_perdus += taille * len(copies)
        lignes.append({"sha256": empreinte, "taille": taille, "original": original, "copies": copies})
        ctx.action("groupe_doublons", "%d copie(s) de %s" % (len(copies), os.path.basename(original)), compteur="groupes",
                   fichier=original, sha256=empreinte, taille=taille, copies=copies)
    ctx.compteurs["copies_en_trop"] = len(en_trop)
    ctx.afficher("%d groupe(s) de doublons, %d copie(s) en trop, %s recuperables"
                 % (len(groupes), len(en_trop), taille_lisible(octets_perdus)))
    if ctx.simulation:
        return
    if args.rapport:
        with sortie_atomique(args.rapport, args.ecraser) as tmp:
            if args.rapport.lower().endswith(".csv"):
                with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
                    w = csv.writer(f, delimiter=";")
                    w.writerow(["sha256", "taille", "original", "copie"])
                    for g in lignes:
                        for copie in g["copies"]:
                            w.writerow([g["sha256"], g["taille"], g["original"], copie])
            else:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(lignes, f, ensure_ascii=False, indent=1)
    if args.sortie_liste:
        with sortie_atomique(args.sortie_liste, args.ecraser) as tmp:
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write("".join(c + "\n" for c in en_trop))


if __name__ == "__main__":
    OUTIL.lancer()
