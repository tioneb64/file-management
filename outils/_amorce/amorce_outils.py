"""Amorce des outils : rend importables `outils.commun` et `journal_si`, ou que soit place le dossier des outils.

Le dossier des outils peut etre deplace (parametre du moteur, docs/13-boite-a-outils.md) et porter un autre nom
que `outils`. Chaque outil commence donc par :

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
    import amorce_outils  # noqa: F401

- le dossier des outils est enregistre sous le nom de paquet `outils` (meme s'il s'appelle autrement) ;
- le dossier du moteur (celui qui contient `journal_si.py` et le paquet `file_management`) est ajoute
  a la fin de `sys.path` : variable COPIE_RACINE_MOTEUR transmise par le moteur, sinon le dossier parent
  des outils (disposition d'origine).

Ce dossier `_amorce` est le seul ajoute a `sys.path` : le dossier des outils lui-meme ne l'est jamais, car
un sous-dossier comme `compression` masquerait le paquet standard du meme nom (Python 3.14).
"""
import importlib.util
import os
import sys

DOSSIER_OUTILS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _enregistrer_paquet():
    paquet = sys.modules.get("outils")
    chemins = [os.path.normcase(os.path.abspath(c)) for c in getattr(paquet, "__path__", [])]
    if paquet is not None and os.path.normcase(DOSSIER_OUTILS) in chemins:
        return
    spec = importlib.util.spec_from_file_location("outils", os.path.join(DOSSIER_OUTILS, "__init__.py"),
                                                  submodule_search_locations=[DOSSIER_OUTILS])
    module = importlib.util.module_from_spec(spec)
    sys.modules["outils"] = module
    spec.loader.exec_module(module)


def _racines_moteur():
    voulues = [os.environ.get("COPIE_RACINE_MOTEUR"), os.path.dirname(DOSSIER_OUTILS)]
    return [r for r in voulues if r and os.path.isdir(r)]


def amorcer():
    _enregistrer_paquet()
    for racine in _racines_moteur():
        if racine not in sys.path:
            sys.path.append(racine)
    if importlib.util.find_spec("journal_si") is None:         # code 4 : dependance absente (docs/13-boite-a-outils.md)
        sys.stderr.write("ERREUR : journal_si.py introuvable. Definir la variable d'environnement COPIE_RACINE_MOTEUR "
                         "(dossier du moteur : celui qui contient journal_si.py et file_management).\n")
        sys.exit(4)


amorcer()
