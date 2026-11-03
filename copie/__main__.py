"""Point d'entree provisoire de la v2 : python -m copie --config FICHIER <commande>

Commandes disponibles : --verifier, --initialiser-base, --sauvegarder-base DOSSIER.
Le lanceur copie_fichiers.py (v1) reste en place tant que la v2 n'est pas livree.
"""
import argparse
import getpass
import json
import sys

from copie import __version__, base
from copie.controles import verifier_fichier

CODE_OK = 0
CODE_CONFIG = 2
CODE_AVERTISSEMENT = 4


def _afficher_verification(args, parametrage, rapport):
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


def _commande_base(args, parametrage):
    entete = parametrage.entete
    try:
        if args.initialiser_base:
            base.initialiser(entete.base, entete.environnement, args.utilisateur)
            print("Base creee : %s (environnement %s)" % (entete.base, entete.environnement))
        else:
            chemin = base.sauvegarder(entete.base, args.sauvegarder_base)
            print("Sauvegarde creee : %s" % chemin)
    except base.ErreurBase as e:
        print("ERREUR : %s" % e, file=sys.stderr)
        return CODE_CONFIG
    return CODE_OK


def main(argv=None):
    p = argparse.ArgumentParser(prog="copie", description="copie_fichiers v2 %s" % __version__)
    p.add_argument("--config", required=True, help="fichier de parametrage (.jsonl)")
    commande = p.add_mutually_exclusive_group()
    commande.add_argument("--verifier", action="store_true", help="valide le parametrage")
    commande.add_argument("--initialiser-base", action="store_true",
                          help="cree la base de l'environnement (refuse si elle existe)")
    commande.add_argument("--sauvegarder-base", metavar="DOSSIER",
                          help="sauvegarde coherente de la base dans ce dossier")
    p.add_argument("--syntaxe-seule", action="store_true",
                   help="avec --verifier : controles du fichier seul, sans acceder aux dossiers")
    p.add_argument("--periode-declencheur-sec", type=int, metavar="N",
                   help="periode du declencheur Jenkins, pour le controle P02")
    p.add_argument("--utilisateur", default=None,
                   help="compte a tracer dans le journal des actions (defaut : compte courant)")
    p.add_argument("--format", choices=("texte", "json"), default="texte")
    args = p.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.periode_declencheur_sec is not None and args.periode_declencheur_sec < 1:
        p.error("--periode-declencheur-sec doit etre superieur a 0")
    if args.utilisateur is None:
        args.utilisateur = getpass.getuser()
    if not (args.verifier or args.initialiser_base or args.sauvegarder_base):
        print("Commandes disponibles dans cette version : --verifier, --initialiser-base, "
              "--sauvegarder-base.", file=sys.stderr)
        return CODE_CONFIG

    parametrage, rapport = verifier_fichier(args.config, args.periode_declencheur_sec)
    if args.verifier:
        return _afficher_verification(args, parametrage, rapport)
    if not rapport.ok:
        print(rapport.en_texte(), file=sys.stderr)
        print("Parametrage invalide : commande annulee.", file=sys.stderr)
        return CODE_CONFIG
    return _commande_base(args, parametrage)


if __name__ == "__main__":
    sys.exit(main())
