# outil: csv_fusionner
# description: Fusionne des fichiers CSV dans --sortie, dans l'ordre alphabetique des noms.
# parametre: --sortie FICHIER.csv | obligatoire | fichier fusionne
# parametre: --sans-entete | facultatif | les fichiers n'ont pas d'en-tete
# parametre: --separateur CAR | facultatif | separateur impose (defaut : detecte dans le premier fichier)
# parametre: --encodage-sortie NOM | facultatif | encodage du resultat (defaut utf-8-sig)
# parametre: --colonne-source NOM | facultatif | ajoute une colonne portant le nom du fichier d'origine
# parametre: --ecraser | facultatif | remplace le fichier fusionne s'il existe
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Fusionne plusieurs fichiers CSV en un seul (en-tete unique, controle des colonnes)."""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import BUSINESS_RULE_VIOLATION, ErreurOutil, ErreurParametres
from outils.commun.fichiers import encodage_fichier, sortie_atomique, verifier_ecrasement
from outils.commun.outil import Outil

OUTIL = Outil("csv_fusionner", "Fusionne des fichiers CSV dans --sortie, dans l'ordre alphabetique des noms. Par "
              "defaut la premiere ligne est un en-tete : il est ecrit une fois, et un fichier dont les colonnes "
              "different est refuse (erreur de l'element, le fichier n'est pas fusionne). Le separateur est "
              "detecte (; , tabulation |) ; chaque fichier est lu dans son encodage detecte ; la sortie est en "
              "UTF-8 avec BOM par defaut. --colonne-source ajoute le nom du fichier d'origine.", "fichiers")


@OUTIL.arguments
def arguments(p):
    options_entrees(p)
    p.add_argument("--sortie", required=True, metavar="FICHIER.csv", help="fichier fusionne")
    p.add_argument("--sans-entete", action="store_true", help="les fichiers n'ont pas d'en-tete")
    p.add_argument("--separateur", metavar="CAR", help="separateur impose (defaut : detecte dans le premier fichier)")
    p.add_argument("--encodage-sortie", default="utf-8-sig", metavar="NOM", help="encodage du resultat (defaut utf-8-sig)")
    p.add_argument("--colonne-source", metavar="NOM", help="ajoute une colonne portant le nom du fichier d'origine")
    p.add_argument("--ecraser", action="store_true", help="remplace le fichier fusionne s'il existe")


def separateur_de(chemin, encodage):
    with open(chemin, encoding=encodage, errors="replace", newline="") as f:
        ligne = f.readline()
    comptes = {c: ligne.count(c) for c in (";", ",", "\t", "|")}
    meilleur = max(comptes, key=lambda c: (comptes[c], c == ";"))
    return meilleur if comptes[meilleur] else ";"


@OUTIL.principal
def principal(ctx, args):
    sortie = os.path.abspath(args.sortie)
    try:
        "".encode(args.encodage_sortie)
    except LookupError:
        raise ErreurParametres("encodage inconnu : %s" % args.encodage_sortie)
    if args.separateur is not None and len(args.separateur) != 1:
        raise ErreurParametres("--separateur : un seul caractere")
    entrees = [c for c, _ in ctx.fichiers() if os.path.normcase(os.path.abspath(c)) != os.path.normcase(sortie)]
    if not entrees:
        return
    verifier_ecrasement(sortie, args.ecraser)
    separateur = args.separateur or separateur_de(entrees[0], encodage_fichier(entrees[0])[0])
    if ctx.simulation:
        for chemin in entrees:
            ctx.action("fichier_a_fusionner", "Serait fusionne : %s" % os.path.basename(chemin), fichier=chemin)
        return
    entete, lignes_total = None, 0
    with sortie_atomique(sortie, args.ecraser) as tmp:
        with open(tmp, "w", encoding=args.encodage_sortie, newline="") as f:
            w = csv.writer(f, delimiter=separateur, lineterminator="\r\n")
            for chemin in entrees:
                with ctx.tolerer("fusion_echec", fichier=chemin):
                    encodage = encodage_fichier(chemin)[0]
                    with open(chemin, encoding=encodage, newline="") as source:
                        lecteur = csv.reader(source, delimiter=separateur)
                        lignes = list(lecteur)
                    if not args.sans_entete and lignes:
                        courant = lignes.pop(0)
                        if entete is None:
                            entete = courant
                            w.writerow(entete + ([args.colonne_source] if args.colonne_source else []))
                        elif courant != entete:
                            raise ErreurOutil("colonnes differentes de celles du premier fichier (%s au lieu de %s)"
                                              % (separateur.join(courant), separateur.join(entete)), BUSINESS_RULE_VIOLATION)
                    for ligne in lignes:
                        w.writerow(ligne + ([os.path.basename(chemin)] if args.colonne_source else []))
                    lignes_total += len(lignes)
                    ctx.action("fichier_fusionne", "Fusionne (%d ligne(s)) : %s" % (len(lignes), os.path.basename(chemin)),
                               fichier=chemin, lignes=len(lignes), encodage=encodage)
        if ctx.nb_erreurs or not ctx.compteurs.get("traites"):
            raise ErreurOutil("fusion incomplete : resultat non ecrit (%d erreur(s) ci-dessus)" % ctx.nb_erreurs)
    ctx.compteurs["lignes"] = lignes_total
    ctx.info("csv_ecrit", "CSV fusionne ecrit : %s" % os.path.basename(sortie), fichier=sortie, lignes=lignes_total)


if __name__ == "__main__":
    OUTIL.lancer()
