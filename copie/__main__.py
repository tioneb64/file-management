"""Point d'entree provisoire de la v2 : python -m copie --config FICHIER [commande]

Sans commande : lancement (regles dues executees l'une apres l'autre ; le parallelisme et les
dependances viennent au jalon J6). Commandes : --verifier, --initialiser-base,
--sauvegarder-base DOSSIER, --etat, --reprise ID, --lancer-maintenant ID, --acquitter ID,
--trancher-incertain CLE, --lancer-regle ID (une seule regle, planification ignoree).
Le lanceur copie_fichiers.py (v1) reste en place tant que la v2 n'est pas livree.
"""
import argparse
import getpass
import json
import sys

from copie import __version__, base, lancement
from copie.controles import verifier_fichier

CODE_OK = 0
CODE_ERREUR = 1
CODE_CONFIG = 2
CODE_AVERTISSEMENT = 4

COMMANDES_EXPLOITATION = ("reprise", "lancer_maintenant", "acquitter", "trancher_incertain")


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
            base.initialiser(entete.base, entete.environnement, args.utilisateur or getpass.getuser())
            print("Base creee : %s (environnement %s)" % (entete.base, entete.environnement))
        else:
            chemin = base.sauvegarder(entete.base, args.sauvegarder_base)
            print("Sauvegarde creee : %s" % chemin)
    except base.ErreurBase as e:
        print("ERREUR : %s" % e, file=sys.stderr)
        return CODE_CONFIG
    return CODE_OK


def _ouvrir_base(parametrage, lecture_seule=False):
    entete = parametrage.entete
    try:
        return base.ouvrir(entete.base, entete.environnement, lecture_seule=lecture_seule), None
    except base.ErreurBase as e:
        print("ERREUR : %s" % e, file=sys.stderr)
        return None, CODE_CONFIG


def _journal(parametrage, console=True):
    import journal_si
    journal = journal_si.Journal()
    journal.debut("copie_fichiers", parametrage.entete.environnement, dossier=parametrage.entete.dossier_logs,
                  console=console, evenement_debut="debut_lancement", evenement_fin="fin_lancement")
    return journal


def _executer_fils(args, parametrage):
    """Commande INTERNE lancee par l'orchestrateur : execute une regle dans ce processus. Le drapeau
    « en cours » et l'execution ont deja ete pris par l'orchestrateur, qui nous place dans son Job
    Object puis nous donne le feu vert sur l'entree standard."""
    from copie import orchestrateur
    from copie.execution import lancer_regle
    if sys.stdin.readline().strip() != "go":
        return CODE_ERREUR
    entete = parametrage.entete
    regle = next((r for r in parametrage.regles if r.id and r.id.lower() == args.executer_regle.lower()), None)
    if regle is None:
        print("ERREUR : regle inconnue : %s" % args.executer_regle, file=sys.stderr)
        return CODE_CONFIG
    b, erreur = _ouvrir_base(parametrage)
    if b is None:
        return erreur
    import journal_si
    journal = journal_si.Journal()
    journal.debut("copie_fichiers", entete.environnement, dossier=entete.dossier_logs, console=True,
                  evenement_debut="processus_regle_demarre", regle=regle.id)
    with b:
        ligne = b.execution(args.execution_id)
        if ligne is None or ligne["fin"] is not None or ligne["regle_no"] != b.numero_regle(regle.id):
            print("ERREUR : execution %s inconnue ou deja terminee pour la regle %s"
                  % (args.execution_id, regle.id), file=sys.stderr)
            return CODE_CONFIG
        bilan = lancer_regle(regle, entete, b, journal, declencheur=ligne["declencheur"],
                             build=ligne["build"], execution_existante=args.execution_id,
                             journaliser_fin=False)
        orchestrateur.ecrire_resultat(entete, orchestrateur.resultat_depuis_bilan(bilan, regle.id,
                                                                                   args.execution_id))
    journal.fermer()
    return CODE_OK


def _terminer_journal(journal, statut, compteurs, code):
    journal.fin(statut=statut, compteurs=compteurs, code_retour=code)
    if journal.pannes():
        print("ATTENTION : %d evenement(s) non ecrit(s) dans le dossier de journaux" % journal.pannes(),
              file=sys.stderr)


def _lancer_regle(args, parametrage):
    from copie.execution import RegleDejaEnCours, lancer_regle
    entete = parametrage.entete
    regle = next((r for r in parametrage.regles if r.id and r.id.lower() == args.lancer_regle.lower()), None)
    if regle is None:
        print("ERREUR : regle inconnue : %s" % args.lancer_regle, file=sys.stderr)
        return CODE_CONFIG
    if not regle.actif:
        print("ERREUR : la regle %s est inactive" % regle.id, file=sys.stderr)
        return CODE_CONFIG
    b, erreur = _ouvrir_base(parametrage, lecture_seule=args.simulation)
    if b is None:
        return erreur
    journal = _journal(parametrage)
    with b:
        if not args.simulation:
            b.synchroniser_regles([(r.id, lancement.empreinte_regle(r)) for r in parametrage.regles if r.id])
        try:
            bilan = lancer_regle(regle, entete, b, journal, declencheur="manuel", simulation=args.simulation,
                                 simulation_programmes=args.simulation_programmes)
        except RegleDejaEnCours:
            _terminer_journal(journal, "ERREUR", {}, CODE_ERREUR)
            print("ERREUR : la regle %s est deja en cours d'execution" % regle.id, file=sys.stderr)
            return CODE_ERREUR
        except base.ErreurBase as e:
            journal.evenement("base_indisponible", "ERREUR", message=str(e))
            _terminer_journal(journal, "ERREUR", {}, CODE_CONFIG)
            print("ERREUR : %s" % e, file=sys.stderr)
            return CODE_CONFIG
        code = {"SUCCES": CODE_OK, "WARNING": CODE_AVERTISSEMENT, "ERREUR": CODE_ERREUR}[bilan.statut]
        _terminer_journal(journal, bilan.statut, bilan.compteurs, code)
    return code


def _lancement(args, parametrage):
    b, erreur = _ouvrir_base(parametrage, lecture_seule=args.simulation)
    if b is None:
        return erreur
    journal = _journal(parametrage)
    with b:
        resultat = lancement.lancer(parametrage, b, journal, filtre=args.regle, simulation=args.simulation,
                                    simulation_programmes=args.simulation_programmes)
        statut = {0: "SUCCES", 1: "WARNING", 2: "ERREUR"}[resultat.niveau]
        _terminer_journal(journal, statut, resultat.compteurs, resultat.code_retour)
    if resultat.interrompu:
        print("ERREUR : %s" % resultat.interrompu, file=sys.stderr)
    return resultat.code_retour


def _etat(args, parametrage):
    b, erreur = _ouvrir_base(parametrage, lecture_seule=True)
    if b is None:
        return erreur
    with b:
        resultat = lancement.etat(parametrage, b, filtre=args.regle)
    if args.format == "json":
        print(json.dumps(resultat, ensure_ascii=False, indent=1))
    else:
        print(lancement.etat_texte(resultat))
    return CODE_OK


def _exploitation(args, parametrage):
    """Reprise, lancement manuel, acquittement, decision sur une livraison incertaine."""
    b, erreur = _ouvrir_base(parametrage)
    if b is None:
        return erreur
    journal = _journal(parametrage)
    with b:
        try:
            if not args.trancher_incertain:       # une regle nouvelle du parametrage doit exister en base
                b.synchroniser_regles([(r.id, lancement.empreinte_regle(r)) for r in parametrage.regles if r.id])
            if args.reprise:
                b.poser_reprise(args.reprise, args.utilisateur, args.commentaire)
                journal.evenement("reprise_demandee", "INFO", regle=args.reprise,
                                  utilisateur=args.utilisateur, commentaire=args.commentaire)
                message = "Reprise demandee pour %s : elle partira au prochain lancement." % args.reprise
            elif args.lancer_maintenant:
                b.poser_lancement_manuel(args.lancer_maintenant, args.utilisateur, args.commentaire)
                journal.evenement("lancement_manuel_demande", "INFO", regle=args.lancer_maintenant,
                                  utilisateur=args.utilisateur)
                message = "%s sera lancee au prochain lancement." % args.lancer_maintenant
            elif args.acquitter:
                b.acquitter(args.acquitter, args.utilisateur, args.commentaire)
                journal.evenement("acquittement", "INFO", regle=args.acquitter, utilisateur=args.utilisateur,
                                  commentaire=args.commentaire)
                message = "%s acquittee." % args.acquitter
            else:
                try:
                    cle = bytes.fromhex(args.trancher_incertain)
                except ValueError:
                    raise base.ActionRefusee("la cle doit etre un nombre hexadecimal (voir --etat / incertains)")
                if args.decision not in ("livre", "a_relivrer"):
                    raise base.ActionRefusee("--decision livre ou a_relivrer est obligatoire")
                b.resoudre_incertain(cle, args.decision, args.utilisateur, args.commentaire)
                journal.evenement("incertain_tranche", "INFO", utilisateur=args.utilisateur,
                                  decision=args.decision, commentaire=args.commentaire)
                message = "Livraison incertaine tranchee : %s." % args.decision
        except (base.ErreurBase, ValueError) as e:
            _terminer_journal(journal, "ERREUR", {}, CODE_CONFIG)
            print("REFUSE : %s" % e, file=sys.stderr)
            return CODE_CONFIG
        _terminer_journal(journal, "SUCCES", {}, CODE_OK)
    print(message)
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
    commande.add_argument("--etat", action="store_true", help="etat des regles (lecture de la base)")
    commande.add_argument("--reprise", metavar="ID",
                          help="relance la regle au prochain lancement, quelle que soit l'heure")
    commande.add_argument("--lancer-maintenant", metavar="ID",
                          help="lance la regle au prochain lancement, sans attendre son creneau")
    commande.add_argument("--acquitter", metavar="ID",
                          help="considere la regle en ERREUR comme corrigee (commentaire obligatoire)")
    commande.add_argument("--trancher-incertain", metavar="CLE",
                          help="decide du sort d'une livraison de resultat inconnu (avec --decision)")
    commande.add_argument("--lancer-regle", metavar="ID",
                          help="execute une seule regle maintenant, planification ignoree")
    commande.add_argument("--executer-regle", metavar="ID",
                          help="INTERNE : execution d'une regle par un fils de l'orchestrateur")
    p.add_argument("--execution-id", type=int, metavar="N", help="INTERNE : avec --executer-regle")
    p.add_argument("--regle", action="append", metavar="ID",
                   help="limite le lancement ou l'etat a cette regle (repetable)")
    p.add_argument("--simulation", action="store_true",
                   help="affiche ce qui serait fait, n'ecrit rien (planification ignoree)")
    p.add_argument("--simulation-programmes", action="store_true",
                   help="avec --simulation : appelle quand meme les programmes (COPIE_SIMULATION=1)")
    p.add_argument("--decision", choices=("livre", "a_relivrer"),
                   help="avec --trancher-incertain : le fichier est bien arrive, ou il faut le relivrer")
    p.add_argument("--utilisateur", help="compte a tracer (obligatoire pour les commandes d'exploitation)")
    p.add_argument("--commentaire", help="commentaire trace avec la commande")
    p.add_argument("--syntaxe-seule", action="store_true",
                   help="avec --verifier : controles du fichier seul, sans acceder aux dossiers")
    p.add_argument("--periode-declencheur-sec", type=int, metavar="N",
                   help="periode du declencheur Jenkins, pour le controle P02")
    p.add_argument("--format", choices=("texte", "json"), default="texte")
    args = p.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.periode_declencheur_sec is not None and args.periode_declencheur_sec < 1:
        p.error("--periode-declencheur-sec doit etre superieur a 0")
    lancement_ou_regle = not (args.verifier or args.initialiser_base or args.sauvegarder_base or args.etat
                              or args.reprise or args.lancer_maintenant or args.acquitter
                              or args.trancher_incertain or args.executer_regle)
    if args.simulation and not (lancement_ou_regle or args.lancer_regle):
        p.error("--simulation s'utilise avec un lancement ou --lancer-regle")
    if args.simulation_programmes and not args.simulation:
        p.error("--simulation-programmes s'utilise avec --simulation")
    if args.regle and not (lancement_ou_regle or args.etat):
        p.error("--regle s'utilise avec un lancement ou --etat")
    if args.executer_regle and args.execution_id is None:
        p.error("--executer-regle exige --execution-id")
    exploitation = args.reprise or args.lancer_maintenant or args.acquitter or args.trancher_incertain
    if exploitation and not args.utilisateur:
        p.error("--utilisateur est obligatoire pour cette commande")

    parametrage, rapport = verifier_fichier(args.config, args.periode_declencheur_sec)
    if args.verifier:
        return _afficher_verification(args, parametrage, rapport)
    if not rapport.ok:
        print(rapport.en_texte(), file=sys.stderr)
        print("Parametrage invalide : commande annulee.", file=sys.stderr)
        return CODE_CONFIG
    if args.initialiser_base or args.sauvegarder_base:
        return _commande_base(args, parametrage)
    if args.etat:
        return _etat(args, parametrage)
    if exploitation:
        return _exploitation(args, parametrage)
    if args.executer_regle:
        return _executer_fils(args, parametrage)
    if args.lancer_regle:
        return _lancer_regle(args, parametrage)
    return _lancement(args, parametrage)


if __name__ == "__main__":
    sys.exit(main())
