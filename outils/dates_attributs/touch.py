# outil: touch
# description: Fixe les dates de fichiers : --modification, --acces, --creation (Windows seulement), ou --tout.
# parametre: --modification DATE | facultatif | date de derniere modification
# parametre: --acces DATE | facultatif | date de dernier acces
# parametre: --creation DATE | facultatif | date de creation (Windows seulement)
# parametre: --tout DATE | facultatif | meme date pour les trois
# parametre: --copier-de FICHIER | facultatif | reprend les dates de ce fichier
# parametre: --decaler +Nh | facultatif | decalage des dates actuelles : +/- N puis s, m, h ou j
# parametre: --creer | facultatif | cree un fichier vide s'il n'existe pas
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Modifie les dates d'un fichier : creation, modification, acces (comme touch)."""
import os
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun import winfs
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import ErreurParametres
from outils.commun.outil import Outil

OUTIL = Outil("touch", "Fixe les dates de fichiers : --modification, --acces, --creation (Windows seulement), ou "
              "--tout. Une date s'ecrit AAAA-MM-JJ, \"AAAA-MM-JJ HH:MM[:SS]\" ou maintenant (heure locale). Sans "
              "date : modification et acces = maintenant. --copier-de reprend les dates d'un fichier modele ; "
              "--decaler +2h / --decaler=-1j / --decaler +30m decale les dates actuelles (un decalage negatif s'ecrit avec '='). --creer cree le fichier vide s'il "
              "n'existe pas.", "dates_attributs")
_RE_DECALAGE = re.compile(r"^([+-])(\d+)\s*(s|m|h|j|d)$")


@OUTIL.arguments
def arguments(p):
    options_entrees(p)
    p.add_argument("--modification", metavar="DATE", help="date de derniere modification")
    p.add_argument("--acces", metavar="DATE", help="date de dernier acces")
    p.add_argument("--creation", metavar="DATE", help="date de creation (Windows seulement)")
    p.add_argument("--tout", metavar="DATE", help="meme date pour les trois")
    p.add_argument("--copier-de", metavar="FICHIER", help="reprend les dates de ce fichier")
    p.add_argument("--decaler", metavar="+Nh", help="decalage des dates actuelles : +/- N puis s, m, h ou j")
    p.add_argument("--creer", action="store_true", help="cree un fichier vide s'il n'existe pas")


def lire_date(texte):
    """Date -> nanosecondes Unix (heure locale)."""
    if texte.strip().lower() in ("maintenant", "now"):
        return time.time_ns()
    for forme in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(texte.strip(), forme).timestamp()) * 10 ** 9
        except ValueError:
            continue
    raise ErreurParametres("date illisible : '%s' (AAAA-MM-JJ, \"AAAA-MM-JJ HH:MM:SS\" ou maintenant)" % texte)


def lire_decalage(texte):
    m = _RE_DECALAGE.match(texte.strip())
    if not m:
        raise ErreurParametres("decalage illisible : '%s' (exemples : +2h, -1j, +30m)" % texte)
    unite = {"s": 1, "m": 60, "h": 3600, "j": 86400, "d": 86400}[m.group(3)]
    return int(m.group(2)) * unite * 10 ** 9 * (1 if m.group(1) == "+" else -1)


@OUTIL.principal
def principal(ctx, args):
    fixes = {"creation": None, "modification": None, "acces": None}
    for nom in fixes:
        valeur = getattr(args, nom) or args.tout
        if valeur:
            fixes[nom] = lire_date(valeur)
    modele = None
    if args.copier_de:
        try:
            modele = os.stat(args.copier_de)
        except OSError as e:
            raise ErreurParametres("--copier-de : fichier modele illisible : %s" % (e.strerror or e))
    decalage = lire_decalage(args.decaler) if args.decaler else None
    if not any(fixes.values()) and modele is None and decalage is None:
        fixes["modification"] = fixes["acces"] = time.time_ns()
    designes = ctx.designes()
    for chemin in designes:
        if not os.path.exists(chemin) and args.creer and not ctx.simulation:
            with ctx.tolerer("creation_echec", fichier=chemin):
                os.makedirs(os.path.dirname(os.path.abspath(chemin)), exist_ok=True)
                open(chemin, "ab").close()
                ctx.info("fichier_cree", "Fichier vide cree : %s" % os.path.basename(chemin), fichier=chemin)
    for chemin, _ in ctx.fichiers(designes):
        with ctx.tolerer("dates_echec", fichier=chemin):
            info = os.stat(chemin)
            avant = {"creation": info.st_ctime_ns if os.name == "nt" else None, "modification": info.st_mtime_ns,
                     "acces": info.st_atime_ns}
            nouveau = dict(fixes)
            if modele is not None:
                nouveau["modification"] = nouveau["modification"] or modele.st_mtime_ns
                nouveau["acces"] = nouveau["acces"] or modele.st_atime_ns
                if os.name == "nt":
                    nouveau["creation"] = nouveau["creation"] or modele.st_ctime_ns
            if decalage is not None:
                for nom in ("creation", "modification", "acces"):
                    if nouveau[nom] is None and avant[nom] is not None and (nom != "creation" or os.name == "nt"):
                        nouveau[nom] = avant[nom] + decalage
            if ctx.simulation:
                ctx.action("dates_a_modifier", "Dates seraient modifiees : %s" % os.path.basename(chemin), fichier=chemin,
                           **{k: _iso(v) for k, v in nouveau.items() if v is not None})
                continue
            winfs.fixer_dates(chemin, nouveau["creation"], nouveau["modification"], nouveau["acces"])
            ctx.action("dates_modifiees", "Dates modifiees : %s" % os.path.basename(chemin), fichier=chemin,
                       **{k: _iso(v) for k, v in nouveau.items() if v is not None})


def _iso(ns):
    return datetime.fromtimestamp(ns // 10 ** 9).isoformat(sep=" ")


if __name__ == "__main__":
    OUTIL.lancer()
