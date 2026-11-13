# bibliotheque: fichiers a traiter : arguments, --liste, jokers, masques, repli sur {fichier}, {liste} et {source} du moteur
"""Fichiers a traiter : arguments, --liste, jokers, masques, et repli sur les variables du moteur."""
import fnmatch
import glob
import os

from outils.commun.erreurs import FILE_NOT_FOUND
from outils.commun.fichiers import SUFFIXE_TEMPORAIRE, lire_liste


def options_entrees(parser, recursif=True, masques=True, positionnels=True):
    """Options communes de designation des fichiers."""
    g = parser.add_argument_group("fichiers a traiter (a defaut : COPIE_FICHIER, puis COPIE_LISTE, puis "
                                  "COPIE_SOURCE, variables du moteur)")
    if positionnels:
        g.add_argument("chemins", nargs="*", metavar="CHEMIN",
                       help="fichiers ou dossiers (jokers * ? [] acceptes)")
    g.add_argument("--liste", action="append", default=[], metavar="FICHIER",
                   help="fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable")
    if masques:
        g.add_argument("--masque", action="append", default=[], metavar="JOKER",
                       help="ne garder que les noms correspondant (ex. *.csv) ; repetable")
        g.add_argument("--exclure", action="append", default=[], metavar="JOKER",
                       help="ecarter les noms correspondant ; repetable")
    if recursif:
        g.add_argument("--recursif", "-r", action="store_true",
                       help="descendre dans les sous-dossiers des dossiers designes")
    return g


def developper(motif):
    """Un chemin ou un motif a jokers -> liste de chemins (motif sans correspondance : liste vide)."""
    if any(c in motif for c in "*?["):
        return sorted(glob.glob(motif, recursive=True))
    return [motif]


def designes(args, env):
    """Chemins designes, dans l'ordre : arguments, --liste, sinon variables du moteur. Liste vide si rien."""
    resultat = []
    for chemin in getattr(args, "chemins", None) or []:
        resultat.extend(developper(chemin))
    for liste in getattr(args, "liste", None) or []:
        for ligne in lire_liste(liste):
            resultat.extend(developper(ligne))
    if getattr(args, "chemins", None) or getattr(args, "liste", None):
        return resultat
    for variable, est_liste in (("COPIE_FICHIER", False), ("COPIE_LISTE", True), ("COPIE_SOURCE", False)):
        valeur = env.get(variable)
        if valeur:
            return lire_liste(valeur) if est_liste else [valeur]
    return resultat


def retenu(nom, relatif, masques, exclusions):
    """Le nom passe-t-il les masques et les exclusions (insensible a la casse, comme Windows) ?"""
    bas, rel = nom.lower(), relatif.lower().replace("\\", "/")
    if nom.endswith(SUFFIXE_TEMPORAIRE):
        return False
    if masques and not any(fnmatch.fnmatchcase(bas, m.lower()) for m in masques):
        return False
    return not any(fnmatch.fnmatchcase(bas, x.lower()) or fnmatch.fnmatchcase(rel, x.lower())
                   for x in exclusions)


def parcourir(dossier, recursif, masques=(), exclusions=(), dossiers_exclus=()):
    """Fichiers d'un dossier, tries (resultat reproductible). Renvoie des chemins complets.
    Les liens symboliques de dossier ne sont jamais suivis."""
    resultat = []
    if recursif:
        for racine, sous_dossiers, noms in os.walk(dossier):
            sous_dossiers[:] = sorted(d for d in sous_dossiers
                                      if not os.path.islink(os.path.join(racine, d)))
            for nom in sorted(noms):
                complet = os.path.join(racine, nom)
                if retenu(nom, os.path.relpath(complet, dossier), masques, exclusions):
                    resultat.append(complet)
    else:
        for nom in sorted(os.listdir(dossier)):
            complet = os.path.join(dossier, nom)
            if os.path.isfile(complet) and retenu(nom, nom, masques, exclusions):
                resultat.append(complet)
    return resultat


def fichiers(ctx, chemins=None, recursif=None, dossiers=True):
    """Generateur (chemin_complet, dossier_de_base) des fichiers a traiter. Un chemin introuvable est une
    erreur de l'element (FILE_NOT_FOUND) et le suivant est traite. `dossier_de_base` sert a calculer le
    chemin relatif d'un fichier trouve dans un dossier designe."""
    chemins = ctx.designes() if chemins is None else chemins
    recursif = getattr(ctx.args, "recursif", False) if recursif is None else recursif
    masques = getattr(ctx.args, "masque", None) or []
    exclusions = getattr(ctx.args, "exclure", None) or []
    for chemin in chemins:
        if os.path.isdir(chemin):
            if not dossiers:
                continue
            for fichier in parcourir(chemin, recursif, masques, exclusions):
                yield fichier, chemin
        elif os.path.isfile(chemin):
            if retenu(os.path.basename(chemin), os.path.basename(chemin), masques, exclusions):
                yield chemin, os.path.dirname(os.path.abspath(chemin))
        else:
            ctx.echec("fichier_introuvable", "Fichier ou dossier introuvable : %s" % chemin,
                      FILE_NOT_FOUND, fichier=chemin)
