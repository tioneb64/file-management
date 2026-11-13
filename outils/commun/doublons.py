# bibliotheque: detection des doublons par contenu (taille puis SHA-256) pour les outils de recherche et d'organisation
"""Detection de doublons par contenu : taille d'abord, puis SHA-256 (jamais le nom ni la date)."""
import collections
import os

from outils.commun.fichiers import sha256_fichier

CRITERES = ("plus-ancien", "plus-recent", "premier", "chemin-court")


def grouper(ctx, chemins, taille_min=1):
    """Groupes de fichiers de meme contenu : liste triee de (sha256, taille, [chemins tries]). Un fichier
    illisible est une erreur de l'element, les autres sont compares."""
    par_taille = collections.defaultdict(list)
    for chemin in chemins:
        with ctx.tolerer("lecture_echec", fichier=chemin):
            taille = os.path.getsize(chemin)
            if taille >= taille_min:
                par_taille[taille].append(chemin)
    groupes = []
    for taille, liste in par_taille.items():
        if len(liste) < 2:
            continue
        par_empreinte = collections.defaultdict(list)
        for chemin in liste:
            with ctx.tolerer("empreinte_echec", fichier=chemin):
                par_empreinte[sha256_fichier(chemin)].append(chemin)
        for empreinte, membres in par_empreinte.items():
            if len(membres) > 1:
                groupes.append((empreinte, taille, sorted(membres)))
    return sorted(groupes, key=lambda g: g[2][0])


def choisir_original(membres, critere):
    """Le fichier a conserver dans un groupe de doublons."""
    if critere == "plus-ancien":
        return min(membres, key=lambda c: (os.path.getmtime(c), c))
    if critere == "plus-recent":
        return max(membres, key=lambda c: (os.path.getmtime(c), c))
    if critere == "chemin-court":
        return min(membres, key=lambda c: (len(c), c))
    return membres[0]
