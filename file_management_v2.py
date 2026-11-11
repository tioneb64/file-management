"""Lanceur de file_management v2 : equivalent de `python -m copie`.

    python file_management_v2.py --config D:\\Parametrage\\production.jsonl [commande] [--format json]

A la fin de la migration (docs/09-migration-et-recette.md), l'ancien file_management.py (v1) est
conserve sous le nom file_management_v1.py pour pouvoir revenir en arriere, et ce lanceur devient
file_management.py : les jobs Jenkins n'ont alors rien a changer.
"""
import sys

from copie.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
