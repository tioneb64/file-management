"""Point d'entree provisoire de la v2 : python -m copie --config FICHIER [commande] [--format json]

Sans commande : lancement (les regles dues, en parallele, apres evaluation de leurs dependances).
Commandes : --verifier [--syntaxe-seule] [--precedent FICHIER], --initialiser-base,
--sauvegarder-base DOSSIER, --etat, --reprise ID, --lancer-maintenant ID, --acquitter ID,
--debloquer ID, --trancher-incertain CLE, --lancer-regle ID (une seule regle, planification
ignoree). Avec --format json, TOUTES les commandes ecrivent un seul objet JSON UTF-8 sur la
sortie standard (contrat : docs/07-contrat-moteur-frontend.md).
Le lanceur copie_fichiers.py (v1) reste en place tant que la v2 n'est pas livree.
"""
import argparse
import getpass
import json
import os
import sys

from copie import __version__, base, lancement
from copie.controles import verifier_fichier
from copie.diagnostic import VERSION_CONTRAT

CODE_OK = 0
CODE_ERREUR = 1
CODE_CONFIG = 2
CODE_AVERTISSEMENT = 4

ETIQUETTES = {CODE_ERREUR: "ERREUR", CODE_CONFIG: "ERREUR"}


def _repondre(args, code, message, etiquette=None, **details):
    """Reponse d'une commande. JSON : un seul objet sur la sortie standard, quel que soit le
    resultat. Texte : message sur la sortie standard, ou sur l'erreur standard en cas d'echec."""
    ok = code in (CODE_OK, CODE_AVERTISSEMENT)
    if args.format == "json":
        resultat = {"version_contrat": VERSION_CONTRAT, "ok": ok, "code_retour": code, "message": message}
        resultat.update(details)
        print(json.dumps(resultat, ensure_ascii=False, indent=1))
    elif ok:
        if message:
            print(message)
    else:
        print("%s : %s" % (etiquette or ETIQUETTES.get(code, "ERREUR"), message), file=sys.stderr)
    return code


def _ouvrir_base(args, parametrage, lecture_seule=False):
    entete = parametrage.entete
    try:
        return base.ouvrir(entete.base, entete.environnement, lecture_seule=lecture_seule), None
    except base.ErreurBase as e:
        return None, _repondre(args, CODE_CONFIG, str(e))


def _journal(args, parametrage, console=True):
    import journal_si
    journal = journal_si.Journal()
    journal.debut("copie_fichiers", parametrage.entete.environnement, dossier=parametrage.entete.dossier_logs,
                  console=console and args.format != "json", evenement_debut="debut_lancement",
                  evenement_fin="fin_lancement")
    return journal


def _terminer_journal(journal, statut, compteurs, code):
    journal.fin(statut=statut, compteurs=compteurs, code_retour=code)
    if journal.pannes():
        print("ATTENTION : %d evenement(s) non ecrit(s) dans le dossier de journaux" % journal.pannes(),
              file=sys.stderr)


# --------------------------------------------------------------------------- #
# --verifier
# --------------------------------------------------------------------------- #
def _verifier(args, parametrage, rapport):
    acces = "non_controle"
    if parametrage is not None:
        if args.precedent:
            from copie.comparaison import comparer
            from copie.parametrage import charger
            ancien, ancien_rapport = charger(args.precedent)
            if ancien is None or not ancien_rapport.ok:
                return _repondre(args, CODE_CONFIG, "fichier precedent illisible ou invalide : %s" % args.precedent)
            historique = None
            try:
                historique = base.ouvrir(parametrage.entete.base, parametrage.entete.environnement,
                                         lecture_seule=True)
            except base.ErreurBase:
                pass
            try:
                comparer(ancien, parametrage, rapport, historique)
            finally:
                if historique is not None:
                    historique.fermer()
        if not args.syntaxe_seule and rapport.ok:
            from copie.acces import verifier_acces
            verifier_acces(parametrage, rapport)
            acces = "controle"
    if args.format == "json":
        resultat = rapport.en_dict()
        resultat["regles_lues"] = len(parametrage.regles) if parametrage else 0
        resultat["acces"] = acces
        resultat["code_retour"] = (CODE_CONFIG if not rapport.ok
                                   else CODE_AVERTISSEMENT if rapport.avertissements else CODE_OK)
        print(json.dumps(resultat, ensure_ascii=False, indent=1))
    else:
        print(rapport.en_texte())
        if not args.syntaxe_seule and acces == "non_controle":
            print("Controles d'acces (A01-A07) : non realises car le parametrage est invalide.")
    if not rapport.ok:
        return CODE_CONFIG
    return CODE_AVERTISSEMENT if rapport.avertissements else CODE_OK


# --------------------------------------------------------------------------- #
# Base
# --------------------------------------------------------------------------- #
def _commande_base(args, parametrage):
    entete = parametrage.entete
    try:
        if args.initialiser_base:
            base.initialiser(entete.base, entete.environnement, args.utilisateur or getpass.getuser())
            return _repondre(args, CODE_OK, "Base creee : %s (environnement %s)" % (entete.base, entete.environnement),
                             base=entete.base, environnement=entete.environnement)
        chemin = base.sauvegarder(entete.base, args.sauvegarder_base)
        return _repondre(args, CODE_OK, "Sauvegarde creee : %s" % chemin, fichier=chemin)
    except base.ErreurBase as e:
        return _repondre(args, CODE_CONFIG, str(e))


# --------------------------------------------------------------------------- #
# Migration de l'ancien script
# --------------------------------------------------------------------------- #
def _migrer_ancien(args):
    from copie import migration
    if not args.environnement or not args.base:
        return _repondre(args, CODE_CONFIG, "--migrer-ancien exige --environnement et --base")
    sortie = args.sortie or (args.environnement + ".jsonl")
    try:
        compte = migration.convertir_conf(args.migrer_ancien, args.environnement, args.base, sortie,
                                          frequence_sec=args.frequence_sec, actives=args.actives)
    except migration.ErreurMigration as e:
        return _repondre(args, CODE_CONFIG, str(e))
    rapport = compte["verification"]
    code = CODE_CONFIG if not rapport.ok else CODE_AVERTISSEMENT if rapport.avertissements else CODE_OK
    message = "%d regle(s) ecrite(s) dans %s (%s)" % (len(compte["regles"]), sortie,
                                                       "actives" if args.actives else "INACTIVES")
    if args.format == "json":
        details = rapport.en_dict()
        details.update(fichier=sortie, regles=compte["regles"], notes=compte["notes"])
        for cle in ("version_contrat", "ok", "code_retour", "message"):
            details.pop(cle, None)
        return _repondre(args, code, message, **details)
    print(message)
    for note in compte["notes"]:
        print("  - " + note)
    print(rapport.en_texte())
    return code


def _importer_historique(args, parametrage):
    from copie import migration
    b, erreur = _ouvrir_base(args, parametrage)
    if b is None:
        return erreur
    with b:
        try:
            compte = migration.importer_historique(parametrage, b, args.importer_historique, args.utilisateur,
                                                   args.commentaire)
        except (migration.ErreurMigration, base.ErreurBase) as e:
            return _repondre(args, CODE_CONFIG, str(e), etiquette="REFUSE")
    message = ("%d fichier(s) importe(s) sur %d entree(s) de l'historique (%d deja connu(s), %d sans regle "
               "correspondante)" % (compte["importees"], compte["entrees"], compte["deja_connues"], compte["sans_regle"]))
    code = CODE_AVERTISSEMENT if compte["sans_regle"] else CODE_OK
    return _repondre(args, code, message, commande="importer_historique", **compte)


# --------------------------------------------------------------------------- #
# Fils d'une regle (interne)
# --------------------------------------------------------------------------- #
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
    try:
        b = base.ouvrir(entete.base, entete.environnement)
    except base.ErreurBase as e:
        print("ERREUR : %s" % e, file=sys.stderr)
        return CODE_CONFIG
    import journal_si
    journal = journal_si.Journal()
    journal.debut("copie_fichiers", entete.environnement, dossier=entete.dossier_logs,
                  console=not os.environ.get("COPIE_SANS_CONSOLE"),
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


# --------------------------------------------------------------------------- #
# Lancements
# --------------------------------------------------------------------------- #
def _lancer_regle(args, parametrage):
    from copie.execution import RegleDejaEnCours, lancer_regle
    entete = parametrage.entete
    regle = next((r for r in parametrage.regles if r.id and r.id.lower() == args.lancer_regle.lower()), None)
    if regle is None:
        return _repondre(args, CODE_CONFIG, "regle inconnue : %s" % args.lancer_regle)
    if not regle.actif:
        return _repondre(args, CODE_CONFIG, "la regle %s est inactive" % regle.id)
    b, erreur = _ouvrir_base(args, parametrage, lecture_seule=args.simulation)
    if b is None:
        return erreur
    journal = _journal(args, parametrage)
    with b:
        if not args.simulation:
            b.synchroniser_regles([(r.id, lancement.empreinte_regle(r)) for r in parametrage.regles if r.id])
        try:
            bilan = lancer_regle(regle, entete, b, journal, declencheur="manuel", simulation=args.simulation,
                                 simulation_programmes=args.simulation_programmes)
        except RegleDejaEnCours:
            _terminer_journal(journal, "ERREUR", {}, CODE_ERREUR)
            return _repondre(args, CODE_ERREUR, "la regle %s est deja en cours d'execution" % regle.id)
        except base.ErreurBase as e:
            journal.evenement("base_indisponible", "ERREUR", message=str(e))
            _terminer_journal(journal, "ERREUR", {}, CODE_CONFIG)
            return _repondre(args, CODE_CONFIG, str(e))
        code = {"SUCCES": CODE_OK, "WARNING": CODE_AVERTISSEMENT, "ERREUR": CODE_ERREUR}[bilan.statut]
        _terminer_journal(journal, bilan.statut, bilan.compteurs, code)
    if args.format == "json":
        return _repondre(args, code, bilan.motif or "", regle=regle.id, statut=bilan.statut,
                         compteurs=bilan.compteurs, simulation=bool(args.simulation))
    return code


def _lancement(args, parametrage):
    b, erreur = _ouvrir_base(args, parametrage, lecture_seule=args.simulation)
    if b is None:
        return erreur
    journal = _journal(args, parametrage)
    with b:
        resultat = lancement.lancer(parametrage, b, journal, filtre=args.regle, simulation=args.simulation,
                                    simulation_programmes=args.simulation_programmes)
        statut = {0: "SUCCES", 1: "WARNING", 2: "ERREUR"}[resultat.niveau]
        _terminer_journal(journal, statut, resultat.compteurs, resultat.code_retour)
    if resultat.interrompu:
        return _repondre(args, resultat.code_retour, resultat.interrompu, statut=statut,
                         compteurs=resultat.compteurs)
    if args.format == "json":
        return _repondre(args, resultat.code_retour, "", statut=statut, compteurs=resultat.compteurs,
                         simulation=bool(args.simulation))
    return resultat.code_retour


def _etat(args, parametrage):
    b, erreur = _ouvrir_base(args, parametrage, lecture_seule=True)
    if b is None:
        return erreur
    with b:
        resultat = lancement.etat(parametrage, b, filtre=args.regle)
    if args.format == "json":
        resultat["version_contrat"] = VERSION_CONTRAT
        resultat["ok"] = True
        resultat["code_retour"] = CODE_OK
        print(json.dumps(resultat, ensure_ascii=False, indent=1))
    else:
        print(lancement.etat_texte(resultat))
    return CODE_OK


# --------------------------------------------------------------------------- #
# Exploitation
# --------------------------------------------------------------------------- #
def _exploitation(args, parametrage):
    """Reprise, lancement manuel, acquittement, deblocage, decision sur une livraison incertaine."""
    b, erreur = _ouvrir_base(args, parametrage)
    if b is None:
        return erreur
    journal = _journal(args, parametrage)
    details = {}
    with b:
        try:
            if not args.trancher_incertain:       # une regle nouvelle du parametrage doit exister en base
                b.synchroniser_regles([(r.id, lancement.empreinte_regle(r)) for r in parametrage.regles if r.id])
            if args.reprise:
                b.poser_reprise(args.reprise, args.utilisateur, args.commentaire)
                journal.evenement("reprise_demandee", "INFO", regle=args.reprise,
                                  utilisateur=args.utilisateur, commentaire=args.commentaire)
                message = "Reprise demandee pour %s : elle partira au prochain lancement." % args.reprise
                details = {"commande": "reprise", "regle": args.reprise}
            elif args.lancer_maintenant:
                b.poser_lancement_manuel(args.lancer_maintenant, args.utilisateur, args.commentaire)
                journal.evenement("lancement_manuel_demande", "INFO", regle=args.lancer_maintenant,
                                  utilisateur=args.utilisateur)
                message = "%s sera lancee au prochain lancement." % args.lancer_maintenant
                details = {"commande": "lancer_maintenant", "regle": args.lancer_maintenant}
            elif args.acquitter:
                b.acquitter(args.acquitter, args.utilisateur, args.commentaire)
                journal.evenement("acquittement", "INFO", regle=args.acquitter, utilisateur=args.utilisateur,
                                  commentaire=args.commentaire)
                message = "%s acquittee." % args.acquitter
                details = {"commande": "acquitter", "regle": args.acquitter}
            elif args.debloquer:
                resultat = lancement.debloquer(parametrage, b, journal, args.debloquer, args.utilisateur,
                                               args.commentaire)
                message = resultat["message"]
                details = dict((k, v) for k, v in resultat.items() if k != "message")
                details["commande"] = "debloquer"
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
                details = {"commande": "trancher_incertain", "decision": args.decision}
        except (base.ErreurBase, ValueError) as e:
            _terminer_journal(journal, "ERREUR", {}, CODE_CONFIG)
            return _repondre(args, CODE_CONFIG, str(e), etiquette="REFUSE")
        _terminer_journal(journal, "SUCCES", {}, CODE_OK)
    return _repondre(args, CODE_OK, message, **details)


# --------------------------------------------------------------------------- #
def _arguments(argv=None):
    p = argparse.ArgumentParser(prog="copie", description="copie_fichiers v2 %s" % __version__)
    p.add_argument("--config", help="fichier de parametrage (.jsonl) ; absent seulement avec --migrer-ancien")
    commande = p.add_mutually_exclusive_group()
    commande.add_argument("--verifier", action="store_true", help="valide le parametrage (et les acces)")
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
    commande.add_argument("--debloquer", metavar="ID",
                          help="arrete l'execution en cours de la regle (et son arbre de processus) et libere son drapeau")
    commande.add_argument("--trancher-incertain", metavar="CLE",
                          help="decide du sort d'une livraison de resultat inconnu (avec --decision)")
    commande.add_argument("--migrer-ancien", metavar="COPIES.CONF",
                          help="convertit l'ancien fichier copies.conf en parametrage v2 (regles inactives)")
    commande.add_argument("--importer-historique", metavar="HISTORIQUE.JSON",
                          help="importe l'historique de l'ancien script : ses fichiers ne seront pas relivres")
    commande.add_argument("--lancer-regle", metavar="ID",
                          help="execute une seule regle maintenant, planification ignoree")
    commande.add_argument("--executer-regle", metavar="ID",
                          help="INTERNE : execution d'une regle par un fils de l'orchestrateur")
    p.add_argument("--execution-id", type=int, metavar="N", help="INTERNE : avec --executer-regle")
    p.add_argument("--environnement", help="avec --migrer-ancien : nom de l'environnement (= nom du fichier)")
    p.add_argument("--base", help="avec --migrer-ancien : chemin de la base SQLite (disque local)")
    p.add_argument("--sortie", help="avec --migrer-ancien : fichier de parametrage a ecrire (defaut : <environnement>.jsonl)")
    p.add_argument("--frequence-sec", type=int, default=3600, metavar="N",
                   help="avec --migrer-ancien : frequence de la planification par defaut (defaut : 3600)")
    p.add_argument("--actives", action="store_true", help="avec --migrer-ancien : regles actives (defaut : inactives)")
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
    p.add_argument("--precedent", metavar="FICHIER",
                   help="avec --verifier : compare avec la version precedente du parametrage (V01 a V04)")
    p.add_argument("--periode-declencheur-sec", type=int, metavar="N",
                   help="periode du declencheur Jenkins, pour le controle P02")
    p.add_argument("--format", choices=("texte", "json"), default="texte")
    return p, p.parse_args(argv)


def _main(argv=None):
    p, args = _arguments(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.periode_declencheur_sec is not None and args.periode_declencheur_sec < 1:
        p.error("--periode-declencheur-sec doit etre superieur a 0")
    lancement_ou_regle = not (args.verifier or args.initialiser_base or args.sauvegarder_base or args.etat
                              or args.reprise or args.lancer_maintenant or args.acquitter or args.debloquer
                              or args.trancher_incertain or args.executer_regle or args.migrer_ancien
                              or args.importer_historique)
    if args.simulation and not (lancement_ou_regle or args.lancer_regle):
        p.error("--simulation s'utilise avec un lancement ou --lancer-regle")
    if args.simulation_programmes and not args.simulation:
        p.error("--simulation-programmes s'utilise avec --simulation")
    if args.regle and not (lancement_ou_regle or args.etat):
        p.error("--regle s'utilise avec un lancement ou --etat")
    if args.precedent and not args.verifier:
        p.error("--precedent s'utilise avec --verifier")
    if args.executer_regle and args.execution_id is None:
        p.error("--executer-regle exige --execution-id")
    if not args.config and not args.migrer_ancien:
        p.error("--config est obligatoire")
    if args.frequence_sec < 1:
        p.error("--frequence-sec doit etre superieur a 0")
    exploitation = (args.reprise or args.lancer_maintenant or args.acquitter or args.debloquer
                    or args.trancher_incertain or args.importer_historique)
    if exploitation and not args.utilisateur:
        p.error("--utilisateur est obligatoire pour cette commande")

    if args.format == "json":
        os.environ["COPIE_SANS_CONSOLE"] = "1"      # les fils ne doivent pas polluer la sortie JSON
    if args.migrer_ancien:
        return _migrer_ancien(args)
    parametrage, rapport = verifier_fichier(args.config, args.periode_declencheur_sec)
    if args.verifier:
        return _verifier(args, parametrage, rapport)
    if not rapport.ok:
        if args.format == "json":
            resultat = rapport.en_dict()
            resultat.update(code_retour=CODE_CONFIG, message="Parametrage invalide : commande annulee.")
            print(json.dumps(resultat, ensure_ascii=False, indent=1))
        else:
            print(rapport.en_texte(), file=sys.stderr)
            print("Parametrage invalide : commande annulee.", file=sys.stderr)
        return CODE_CONFIG
    if args.initialiser_base or args.sauvegarder_base:
        return _commande_base(args, parametrage)
    if args.etat:
        return _etat(args, parametrage)
    if args.importer_historique:
        return _importer_historique(args, parametrage)
    if exploitation:
        return _exploitation(args, parametrage)
    if args.executer_regle:
        return _executer_fils(args, parametrage)
    if args.lancer_regle:
        return _lancer_regle(args, parametrage)
    return _lancement(args, parametrage)


def main(argv=None):
    precedent = os.environ.get("COPIE_SANS_CONSOLE")
    try:
        return _main(argv)
    finally:
        if precedent is None:
            os.environ.pop("COPIE_SANS_CONSOLE", None)
        else:
            os.environ["COPIE_SANS_CONSOLE"] = precedent


if __name__ == "__main__":
    sys.exit(main())
