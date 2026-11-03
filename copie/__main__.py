"""Point d'entree provisoire de la v2 : python -m copie --config FICHIER --verifier [...]

Le lanceur copie_fichiers.py (v1) reste en place tant que la v2 n'est pas livree.
"""
import argparse
import json
import sys

from copie import __version__
from copie.controles import verifier_fichier

CODE_OK = 0
CODE_CONFIG = 2
CODE_AVERTISSEMENT = 4


def main(argv=None):
    p = argparse.ArgumentParser(prog="copie", description="copie_fichiers v2 %s" % __version__)
    p.add_argument("--config", required=True, help="fichier de parametrage (.jsonl)")
    p.add_argument("--verifier", action="store_true", help="valide le parametrage")
    p.add_argument("--syntaxe-seule", action="store_true",
                   help="avec --verifier : controles du fichier seul, sans acceder aux dossiers")
    p.add_argument("--periode-declencheur-sec", type=int, metavar="N",
                   help="periode du declencheur Jenkins, pour le controle P02")
    p.add_argument("--format", choices=("texte", "json"), default="texte")
    args = p.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not args.verifier:
        print("Seule la commande --verifier est disponible dans cette version (jalon J1).",
              file=sys.stderr)
        return CODE_CONFIG
    if args.periode_declencheur_sec is not None and args.periode_declencheur_sec < 1:
        p.error("--periode-declencheur-sec doit etre superieur a 0")

    parametrage, rapport = verifier_fichier(args.config, args.periode_declencheur_sec)
    if args.format == "json":
        resultat = rapport.en_dict()
        resultat["regles_lues"] = len(parametrage.regles) if parametrage else 0
        resultat["acces"] = "non_controle"
        print(json.dumps(resultat, ensure_ascii=False, indent=1))
    else:
        print(rapport.en_texte())
        if not args.syntaxe_seule:
            print("Controles d'acces (A01-A07) : non realises dans cette version (jalon J8).")
    if not rapport.ok:
        return CODE_CONFIG
    return CODE_AVERTISSEMENT if rapport.avertissements else CODE_OK


if __name__ == "__main__":
    sys.exit(main())
