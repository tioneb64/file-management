"""Lanceur de copie_fichiers v2 : equivalent de `python -m copie`.

    python copie_fichiers_v2.py --config D:\\Parametrage\\production.jsonl [commande] [--format json]

A la fin de la migration (docs/09-migration-et-recette.md), l'ancien copie_fichiers.py (v1) est
conserve sous le nom copie_fichiers_v1.py pour pouvoir revenir en arriere, et ce lanceur devient
copie_fichiers.py : les jobs Jenkins n'ont alors rien a changer.
"""
import sys

from copie.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
