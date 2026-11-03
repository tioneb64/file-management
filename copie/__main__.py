"""Point d'entree provisoire de la v2 : python -m copie --config FICHIER <commande>

Commandes disponibles : --verifier, --initialiser-base, --sauvegarder-base DOSSIER,
--lancer-regle ID [--simulation] (execution d'une seule regle, sans planification : le
lancement complet par Jenkins viendra aux jalons J5 et J6).
Le lanceur copie_fichiers.py (v1) reste en place tant que la v2 n'est pas livree.
"""
import argparse
import getpass
import hashlib
import json
import sys

from copie import __version__, base
from copie.controles import verifier_fichier

CODE_OK = 0
CODE_ERREUR = 1
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


def empreinte_regle(regle):
    return hashlib.blake2b(regle.brut.encode("utf-8"), digest_size=16).hexdigest()


def _lancer_regle(args, parametrage):
    import journal_si
    from copie.execution import RegleDejaEnCours, lancer_regle
    entete = parametrage.entete
    regle = next((r for r in parametrage.regles if r.id and r.id.lower() == args.lancer_regle.lower()), None)
    if regle is None:
        print("ERREUR : regle inconnue : %s" % args.lancer_regle, file=sys.stderr)
        return CODE_CONFIG
    if not regle.actif:
        print("ERREUR : la regle %s est inactive" % regle.id, file=sys.stderr)
        return CODE_CONFIG
    try:
        b = base.ouvrir(entete.base, entete.environnement, lecture_seule=args.simulation)
    except base.ErreurBase as e:
        print("ERREUR : %s" % e, file=sys.stderr)
        return CODE_CONFIG
    journal = journal_si.Journal()
    with b:
        if not args.simulation:
            b.synchroniser_regles([(r.id, empreinte_regle(r)) for r in parametrage.regles if r.id])
        journal.debut("copie_fichiers", entete.environnement, dossier=entete.dossier_logs,
                      console=True, evenement_debut="debut_lancement", evenement_fin="fin_lancement")
        try:
            bilan = lancer_regle(regle, entete, b, journal, declencheur="manuel",
                                 simulation=args.simulation)
        except RegleDejaEnCours:
            journal.fin(statut="ERREUR", code_retour=CODE_ERREUR, message="regle deja en cours")
            print("ERREUR : la regle %s est deja en cours d'execution" % regle.id, file=sys.stderr)
            return CODE_ERREUR
        except base.ErreurBase as e:
            journal.evenement("base_indisponible", "ERREUR", message=str(e))
            journal.fin(statut="ERREUR", code_retour=CODE_CONFIG)
            print("ERREUR : %s" % e, file=sys.stderr)
            return CODE_CONFIG
        code = {"SUCCES": CODE_OK, "WARNING": CODE_AVERTISSEMENT, "ERREUR": CODE_ERREUR}[bilan.statut]
        journal.fin(statut=bilan.statut, compteurs=bilan.compteurs, code_retour=code)
        if journal.pannes():
            print("ATTENTION : %d evenement(s) non ecrit(s) dans le dossier de journaux" % journal.pannes(),
                  file=sys.stderr)
    return code


def main(argv=None):
    p = argparse.ArgumentParser(prog="copie", description="copie_fichiers v2 %s" % __version__)
    p.add_argument("--config", required=True, help="fichier de parametrage (.jsonl)")
    commande = p.add_mutually_exclusive_group()
    commande.add_argument("--verifier", action="store_true", help="valide le parametrage")
    commande.add_argument("--initialiser-base", action="store_true",
                          help="cree la base de l'environnement (refuse si elle existe)")
    commande.add_argument("--sauvegarder-base", metavar="DOSSIER",
                          help="sauvegarde coherente de la base dans ce dossier")
    commande.add_argument("--lancer-regle", metavar="ID",
                          help="execute une regle, sans tenir compte de sa planification")
    p.add_argument("--simulation", action="store_true",
                   help="avec --lancer-regle : affiche ce qui serait fait, n'ecrit rien")
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
    if args.simulation and not args.lancer_regle:
        p.error("--simulation s'utilise avec --lancer-regle")
    if args.utilisateur is None:
        args.utilisateur = getpass.getuser()
    if not (args.verifier or args.initialiser_base or args.sauvegarder_base or args.lancer_regle):
        print("Commandes disponibles dans cette version : --verifier, --initialiser-base, "
              "--sauvegarder-base, --lancer-regle.", file=sys.stderr)
        return CODE_CONFIG

    parametrage, rapport = verifier_fichier(args.config, args.periode_declencheur_sec)
    if args.verifier:
        return _afficher_verification(args, parametrage, rapport)
    if not rapport.ok:
        print(rapport.en_texte(), file=sys.stderr)
        print("Parametrage invalide : commande annulee.", file=sys.stderr)
        return CODE_CONFIG
    if args.lancer_regle:
        return _lancer_regle(args, parametrage)
    return _commande_base(args, parametrage)


if __name__ == "__main__":
    sys.exit(main())
