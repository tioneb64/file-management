# bibliotheque: application d'un plan de renommage ou de deplacement : conflits, permutations, simulation, journal
"""Application d'un plan de renommage (ou de deplacement) : conflits, permutations, simulation, journal."""
import os
import uuid

from outils.commun.erreurs import DUPLICATE_ENTITY, ErreurOutil
from outils.commun.fichiers import SUFFIXE_TEMPORAIRE


def _meme(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def appliquer(ctx, plan, evenement="fichier_renomme", libelle="Renomme", libelle_simulation="Serait renomme"):
    """`plan` : liste de (source, destination). Chaque renommage est independant : un conflit (destination
    existante, deux sources vers le meme nom) est une erreur de l'element, les autres sont faits. Quand une
    destination est la source d'un autre renommage du meme lot (permutation, decalage de numeros), les deux
    passent par un nom temporaire : rien n'est ecrase."""
    plan = [(s, d) for s, d in plan if not _meme(s, d) or s != d]
    sources = {os.path.normcase(os.path.abspath(s)) for s, _ in plan}
    vus = {}
    retenus = []
    for source, dest in plan:
        cle = os.path.normcase(os.path.abspath(dest))
        with ctx.tolerer("renommage_echec", fichier=source):
            if cle in vus:
                raise ErreurOutil("deux fichiers recevraient le nom %s (%s et %s)"
                                  % (os.path.basename(dest), os.path.basename(vus[cle]), os.path.basename(source)),
                                  DUPLICATE_ENTITY)
            vus[cle] = source
            if os.path.lexists(dest) and not _meme(source, dest) and cle not in sources:
                raise ErreurOutil("le nom existe deja : %s" % dest, DUPLICATE_ENTITY)
            retenus.append((source, dest, cle in sources))
    if ctx.simulation:
        for source, dest, _ in retenus:
            ctx.action(evenement.replace("_renomme", "_a_renommer"), "%s : %s -> %s"
                       % (libelle_simulation, os.path.basename(source), os.path.basename(dest)),
                       fichier=source, cible=dest)
        return
    temporaires = []
    for source, dest, conflit in retenus:                   # phase 1 : les sources en conflit sortent du chemin
        if conflit:
            with ctx.tolerer("renommage_echec", fichier=source):
                tmp = os.path.join(os.path.dirname(source), "%s.%s%s" % (uuid.uuid4().hex[:12], "tmp", SUFFIXE_TEMPORAIRE))
                os.rename(source, tmp)
                temporaires.append((tmp, source, dest))
    for source, dest, conflit in retenus:
        if conflit:
            continue
        with ctx.tolerer("renommage_echec", fichier=source):
            os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
            os.rename(source, dest)
            ctx.action(evenement, "%s : %s -> %s" % (libelle, os.path.basename(source), os.path.basename(dest)),
                       fichier=source, cible=dest)
    for tmp, source, dest in temporaires:
        try:
            os.rename(tmp, dest)
            ctx.action(evenement, "%s : %s -> %s" % (libelle, os.path.basename(source), os.path.basename(dest)),
                       fichier=source, cible=dest)
        except OSError as e:
            try:
                os.rename(tmp, source)                      # retour a l'etat initial
            except OSError:
                pass
            ctx.echec("renommage_echec", "Renommage impossible (%s) : %s" % (e.strerror or e, source), fichier=source)
