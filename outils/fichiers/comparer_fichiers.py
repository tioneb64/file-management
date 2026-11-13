# outil: comparer_fichiers
# description: Compare deux fichiers (diff unifie si ce sont des textes, sinon SHA-256) ou deux dossiers (fichiers seulement a gauche, seulement a droite, differents par la taille ou le SHA-256, identiques).
# parametre: GAUCHE | obligatoire | fichier ou dossier de reference
# parametre: DROITE | obligatoire | fichier ou dossier compare
# parametre: --recursif/-r | facultatif | dossiers : descend dans les sous-dossiers
# parametre: --masque JOKER | facultatif | dossiers : ne compare que ces noms ; repetable
# parametre: --exclure JOKER | facultatif | dossiers : ecarte ces noms ; repetable
# parametre: --ignorer-blancs | facultatif | fichiers texte : ignore les espaces en fin de ligne
# parametre: --rapport FICHIER | facultatif | ecrit le diff ou la liste des ecarts
# parametre: --ecraser | facultatif | remplace le rapport s'il existe
# parametre: --erreur-si-different | facultatif | une difference est une erreur (code 2)
# parametre: --max-affiches N | facultatif | lignes reprises sur la sortie standard (defaut 40)
"""Compare deux fichiers (diff ligne a ligne) ou deux dossiers (presence, taille, SHA-256)."""
import difflib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import parcourir
from outils.commun.erreurs import BUSINESS_RULE_VIOLATION, ErreurOutil, ErreurParametres, FILE_NOT_FOUND
from outils.commun.fichiers import encodage_fichier, est_binaire, sha256_fichier, sortie_atomique
from outils.commun.outil import Outil

OUTIL = Outil("comparer_fichiers", "Compare deux fichiers (diff unifie si ce sont des textes, sinon SHA-256) ou deux "
              "dossiers (fichiers seulement a gauche, seulement a droite, differents par la taille ou le SHA-256, "
              "identiques). Une difference n'est pas une erreur : code 0. 'Rien a faire' = identiques (code 1 avec "
              "--code-si-rien 1, pour ne traiter que ce qui a change). --erreur-si-different en fait une erreur "
              "(code 2). --rapport ecrit le diff ou la liste des ecarts (.json si l'extension est .json).", "fichiers")


@OUTIL.arguments
def arguments(p):
    p.add_argument("gauche", metavar="GAUCHE", help="fichier ou dossier de reference")
    p.add_argument("droite", metavar="DROITE", help="fichier ou dossier compare")
    p.add_argument("--recursif", "-r", action="store_true", help="dossiers : descend dans les sous-dossiers")
    p.add_argument("--masque", action="append", default=[], metavar="JOKER", help="dossiers : ne compare que ces noms ; repetable")
    p.add_argument("--exclure", action="append", default=[], metavar="JOKER", help="dossiers : ecarte ces noms ; repetable")
    p.add_argument("--ignorer-blancs", action="store_true", help="fichiers texte : ignore les espaces en fin de ligne")
    p.add_argument("--rapport", metavar="FICHIER", help="ecrit le diff ou la liste des ecarts")
    p.add_argument("--ecraser", action="store_true", help="remplace le rapport s'il existe")
    p.add_argument("--erreur-si-different", action="store_true", help="une difference est une erreur (code 2)")
    p.add_argument("--max-affiches", type=int, default=40, metavar="N", help="lignes reprises sur la sortie standard (defaut 40)")


def _lignes(chemin, ignorer_blancs):
    with open(chemin, encoding=encodage_fichier(chemin)[0], errors="replace", newline="") as f:
        lignes = f.read().splitlines()
    return [l.rstrip() for l in lignes] if ignorer_blancs else lignes


def _comparer_dossiers(ctx, args):
    def lister(racine):
        return {os.path.relpath(c, racine).replace("\\", "/"): c
                for c in parcourir(racine, args.recursif, args.masque, args.exclure)}
    g, d = lister(args.gauche), lister(args.droite)
    ecarts = {"seulement_gauche": sorted(set(g) - set(d)), "seulement_droite": sorted(set(d) - set(g)),
              "differents": [], "identiques": 0}
    for nom in sorted(set(g) & set(d)):
        with ctx.tolerer("comparaison_echec", fichier=g[nom]):
            if os.path.getsize(g[nom]) != os.path.getsize(d[nom]) or sha256_fichier(g[nom]) != sha256_fichier(d[nom]):
                ecarts["differents"].append(nom)
            else:
                ecarts["identiques"] += 1
    return ecarts


@OUTIL.principal
def principal(ctx, args):
    g, d = args.gauche, args.droite
    for chemin in (g, d):
        if not os.path.exists(chemin):
            raise ErreurOutil("introuvable : %s" % chemin, FILE_NOT_FOUND)
    if os.path.isdir(g) != os.path.isdir(d):
        raise ErreurParametres("comparer deux fichiers ou deux dossiers, pas un fichier avec un dossier")
    ecart_total, rapport, texte_rapport = 0, None, ""
    if os.path.isdir(g):
        ecarts = _comparer_dossiers(ctx, args)
        ecart_total = len(ecarts["seulement_gauche"]) + len(ecarts["seulement_droite"]) + len(ecarts["differents"])
        ctx.compter("identiques", ecarts["identiques"])
        for cle in ("seulement_gauche", "seulement_droite", "differents"):
            ctx.compter(cle, len(ecarts[cle]))
            for nom in ecarts[cle]:
                ctx.debug("ecart", "%s : %s" % (cle.replace("_", " "), nom), fichier=nom)
        lignes = ["%s : %s" % (cle.replace("_", " "), nom) for cle in ("seulement_gauche", "seulement_droite", "differents")
                  for nom in ecarts[cle]]
        rapport, texte_rapport = ecarts, "\n".join(lignes) + ("\n" if lignes else "")
    else:
        if os.path.getsize(g) == os.path.getsize(d) and sha256_fichier(g) == sha256_fichier(d):
            lignes = []
        else:
            with open(g, "rb") as a, open(d, "rb") as b:
                binaire = est_binaire(a.read(8192)) or est_binaire(b.read(8192))
            if binaire:
                lignes = ["fichiers binaires differents (SHA-256 %s / %s)" % (sha256_fichier(g)[:12], sha256_fichier(d)[:12])]
            else:
                lignes = list(difflib.unified_diff(_lignes(g, args.ignorer_blancs), _lignes(d, args.ignorer_blancs),
                                                   fromfile=g, tofile=d, lineterm=""))
        ecart_total = len(lignes)
        ctx.compter("lignes_differentes", len([l for l in lignes if l[:1] in "+-" and l[:3] not in ("+++", "---")]))
        rapport, texte_rapport = {"differences": lignes}, "\n".join(lignes) + ("\n" if lignes else "")
    if not ecart_total:
        ctx.info("identiques", "Aucune difference entre %s et %s" % (os.path.basename(g), os.path.basename(d)))
        return
    ctx.action("difference_trouvee", "Differences entre %s et %s" % (os.path.basename(g), os.path.basename(d)),
               compteur="comparaisons", gauche=g, droite=d)
    for ligne in texte_rapport.splitlines()[:args.max_affiches]:
        ctx.afficher(ligne)
    if args.rapport and not ctx.simulation:
        with sortie_atomique(args.rapport, args.ecraser) as tmp:
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                if args.rapport.lower().endswith(".json"):
                    json.dump(rapport, f, ensure_ascii=False, indent=1)
                else:
                    f.write(texte_rapport)
    if args.erreur_si_different:
        raise ErreurOutil("les deux %s different" % ("dossiers" if os.path.isdir(g) else "fichiers"), BUSINESS_RULE_VIOLATION)


if __name__ == "__main__":
    OUTIL.lancer()
