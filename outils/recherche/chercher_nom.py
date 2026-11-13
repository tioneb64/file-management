# outil: chercher_nom
# description: Cherche dans une arborescence les fichiers (ou dossiers) dont le nom correspond a un joker (--nom) ou a une expression reguliere (--regex).
# parametre: --nom JOKER | facultatif | joker sur le nom (ex. *.csv) ; repetable
# parametre: --regex EXPR | facultatif | expression reguliere sur le nom (re.search)
# parametre: --ignorer-casse | facultatif | ignore la casse pour --regex (les jokers l'ignorent deja)
# parametre: --type {fichier,dossier,tout} | facultatif | defaut : fichier
# parametre: --sans-recursion | facultatif | ne descend pas dans les sous-dossiers
# parametre: --taille-min TAILLE | facultatif | taille minimale des fichiers (ex. 10M)
# parametre: --taille-max TAILLE | facultatif | taille maximale des fichiers
# parametre: --plus-ancien-que JOURS | facultatif | modifie il y a plus de N jours
# parametre: --plus-recent-que JOURS | facultatif | modifie il y a moins de N jours
# parametre: --sortie-liste FICHIER | facultatif | ecrit les chemins trouves (UTF-8, un par ligne)
# parametre: --max-affiches N | facultatif | nombre de resultats repris sur la sortie standard (defaut 50 ; la liste est complete)
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
"""Cherche des fichiers ou dossiers par nom (jokers ou expression reguliere) dans une arborescence."""
import fnmatch
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import ErreurParametres, FILE_NOT_FOUND
from outils.commun.fichiers import SUFFIXE_TEMPORAIRE, lire_taille
from outils.commun.outil import Outil

OUTIL = Outil("chercher_nom", "Cherche dans une arborescence les fichiers (ou dossiers) dont le nom correspond a un "
              "joker (--nom) ou a une expression reguliere (--regex). Code retour 1 s'il n'y a aucun resultat "
              "et --code-si-rien 1. Un fichier designe (par exemple la {liste} du lot) est teste sur son nom. La liste "
              "(--sortie-liste) peut servir de {liste} a un autre outil.", "recherche")


@OUTIL.arguments
def arguments(p):
    options_entrees(p, recursif=False, masques=False)
    p.add_argument("--nom", action="append", default=[], metavar="JOKER", help="joker sur le nom (ex. *.csv) ; repetable")
    p.add_argument("--regex", metavar="EXPR", help="expression reguliere sur le nom (re.search)")
    p.add_argument("--ignorer-casse", action="store_true", help="ignore la casse pour --regex (les jokers l'ignorent deja)")
    p.add_argument("--type", choices=("fichier", "dossier", "tout"), default="fichier", help="defaut : fichier")
    p.add_argument("--sans-recursion", action="store_true", help="ne descend pas dans les sous-dossiers")
    p.add_argument("--taille-min", metavar="TAILLE", help="taille minimale des fichiers (ex. 10M)")
    p.add_argument("--taille-max", metavar="TAILLE", help="taille maximale des fichiers")
    p.add_argument("--plus-ancien-que", type=float, metavar="JOURS", help="modifie il y a plus de N jours")
    p.add_argument("--plus-recent-que", type=float, metavar="JOURS", help="modifie il y a moins de N jours")
    p.add_argument("--sortie-liste", metavar="FICHIER", help="ecrit les chemins trouves (UTF-8, un par ligne)")
    p.add_argument("--max-affiches", type=int, default=50, metavar="N",
                   help="nombre de resultats repris sur la sortie standard (defaut 50 ; la liste est complete)")


@OUTIL.principal
def principal(ctx, args):
    if not args.nom and not args.regex:
        raise ErreurParametres("--nom ou --regex est obligatoire")
    try:
        regex = re.compile(args.regex, re.I if args.ignorer_casse else 0) if args.regex else None
    except re.error as e:
        raise ErreurParametres("expression reguliere invalide : %s" % e)
    mini = lire_taille(args.taille_min) if args.taille_min else None
    maxi = lire_taille(args.taille_max) if args.taille_max else None
    maintenant = time.time()
    racines = ctx.designes() or ["."]
    trouves = []

    def correspond(nom):
        if args.nom and not any(fnmatch.fnmatchcase(nom.lower(), m.lower()) for m in args.nom):
            return False
        return regex is None or regex.search(nom) is not None

    def retenu(chemin, est_dossier):
        if args.type == "fichier" and est_dossier or args.type == "dossier" and not est_dossier:
            return False
        if not correspond(os.path.basename(chemin)) or chemin.endswith(SUFFIXE_TEMPORAIRE):
            return False
        if est_dossier:
            return True
        info = os.stat(chemin)
        age = (maintenant - info.st_mtime) / 86400.0
        return not ((mini is not None and info.st_size < mini) or (maxi is not None and info.st_size > maxi)
                    or (args.plus_ancien_que is not None and age < args.plus_ancien_que)
                    or (args.plus_recent_que is not None and age > args.plus_recent_que))

    for racine in racines:
        if os.path.isfile(racine):                      # un fichier designe (liste du lot) : on teste son nom
            with ctx.tolerer("lecture_echec", fichier=racine):
                if retenu(racine, False):
                    trouves.append(racine)
                    ctx.debug("resultat_recherche", "Trouve : %s" % os.path.basename(racine), fichier=racine)
            continue
        if not os.path.isdir(racine):
            ctx.echec("dossier_introuvable", "Dossier de recherche introuvable : %s" % racine, FILE_NOT_FOUND,
                      fichier=racine)
            continue
        erreurs_marche = []
        for dossier, sous, noms in os.walk(racine, onerror=erreurs_marche.append):
            sous[:] = sorted(d for d in sous if not os.path.islink(os.path.join(dossier, d)))
            if args.sans_recursion:
                sous[:] = []
            for nom, est_dossier in [(d, True) for d in sous] + [(f, False) for f in sorted(noms)]:
                chemin = os.path.join(dossier, nom)
                with ctx.tolerer("lecture_echec", fichier=chemin):
                    if retenu(chemin, est_dossier):
                        trouves.append(chemin)
                        ctx.debug("resultat_recherche", "Trouve : %s" % nom, fichier=chemin)
        for e in erreurs_marche:
            ctx.echec("lecture_dossier_echec", "Dossier illisible : %s" % (e.strerror or e), fichier=e.filename)
    if not trouves:
        return
    ctx.action("recherche_terminee", "%d resultat(s)" % len(trouves), compteur=None, resultats=len(trouves),
               racines=racines)
    ctx.compteurs["trouves"] = len(trouves)
    if args.sortie_liste and not ctx.simulation:
        with open(args.sortie_liste, "w", encoding="utf-8", newline="\n") as f:
            f.write("".join(c + "\n" for c in trouves))
    for chemin in trouves[:args.max_affiches]:
        ctx.afficher(chemin)
    if len(trouves) > args.max_affiches:
        ctx.afficher("... et %d autre(s)" % (len(trouves) - args.max_affiches))


if __name__ == "__main__":
    OUTIL.lancer()
