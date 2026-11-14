"""Lanceur de file_management : equivalent de `python -m file_management`.

    python file_management.py --config D:\\Parametrage\\production.jsonl [commande] [--format json]

L'ancien script (v1) et sa configuration sont conserves dans Legacy/ (file_management_v1.py, copies.conf) pour
pouvoir revenir en arriere (docs/09-migration-et-recette.md).
"""
import sys

from file_management.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
