"""Orchestrateur d'un lancement : une regle = un processus fils, execution en parallele,
dependances entre regles, duree maximale, fins anormales.

Specification : docs/02-moteur.md sections 2 et 3. Le fils (`--executer-regle`) execute la
regle et ecrit son resultat en base et dans un petit fichier JSON ; c'est l'orchestrateur qui
journalise la fin de chaque regle, y compris quand le fils est mort sans rien ecrire.
"""
import json
import os
import subprocess
import sys
import time

from file_management import dependances, planification, processus
from file_management.execution import NIVEAU_STATUT, RegleDejaEnCours, lancer_regle, nom_hote

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DELAI_ARRET_FILS_SEC = 30


# --------------------------------------------------------------------------- #
# Resultat transmis par le fils
# --------------------------------------------------------------------------- #
def resultat_depuis_bilan(bilan, regle_id, execution_id):
    return {"regle": regle_id, "execution_id": execution_id, "statut": bilan.statut, "motif": bilan.motif,
            "situation_finale": bilan.situation_finale, "compteurs": bilan.compteurs, "erreur": bilan.erreur,
            "arret_apres_erreur": bilan.arret_apres_erreur, "duree_ms": bilan.duree_ms}


def chemin_resultat(entete, execution_id):
    return os.path.join(entete.dossier_travail, "resultat_%d.json" % execution_id)


def ecrire_resultat(entete, resultat):
    """Ecriture atomique du resultat d'un fils (temporaire puis renommage)."""
    os.makedirs(entete.dossier_travail, exist_ok=True)
    chemin = chemin_resultat(entete, resultat["execution_id"])
    with open(chemin + ".tmp", "w", encoding="utf-8") as f:
        json.dump(resultat, f, ensure_ascii=False)
    os.replace(chemin + ".tmp", chemin)


def lire_resultat(entete, execution_id, supprimer=True):
    chemin = chemin_resultat(entete, execution_id)
    try:
        with open(chemin, encoding="utf-8") as f:
            resultat = json.load(f)
    except (OSError, ValueError):
        return None
    if supprimer:
        try:
            os.remove(chemin)
        except OSError:
            pass
    return resultat


class Fils(object):
    def __init__(self, regle, no, execution_id, popen=None, job=None, resultat=None):
        self.regle = regle
        self.no = no
        self.execution_id = execution_id
        self.popen = popen
        self.job = job
        self.resultat = resultat                   # mode direct : deja termine
        self.debut = time.monotonic()
        self.alerte = False                        # duree depassee signalee (si_duree_depassee = alerter)

    def termine(self):
        return self.resultat is not None or (self.popen is not None and self.popen.poll() is not None)


class Orchestrateur(object):
    def __init__(self, parametrage, base, journal, lancement, filtre=None, maintenant=None,
                 fuseau=planification.FUSEAU, build=None, direct=False, maintenant_dt=None,
                 dormir=time.sleep, pas_sec=0.2, rappel=None, commande_fils=None):
        self.parametrage = parametrage
        self.entete = parametrage.entete
        self.base = base
        self.journal = journal
        self.lancement = lancement
        self.filtre = filtre
        self.maintenant = maintenant or time.time
        self.fuseau = fuseau
        self.build = build or os.environ.get("BUILD_NUMBER")
        self.direct = direct                      # sans processus fils (tests, horloge simulee)
        self.maintenant_dt = maintenant_dt
        self.dormir = dormir
        self.pas_sec = pas_sec
        self.rappel = rappel                      # appele a chaque tour de surveillance (tests)
        self.commande_fils = commande_fils or self._commande_fils
        self.fils = {}                            # id de regle -> Fils en cours
        self.evaluations = {}                     # id de regle -> dependances.Evaluation
        self.bloquees = set()
        self.cree_le = processus.date_creation(os.getpid())

    # ------------------------------------------------------------------ #
    # Deroulement
    # ------------------------------------------------------------------ #
    def executer(self):
        pendantes = self._regles_dues()
        try:
            while True:
                demarres = self._lancer_prets(pendantes)
                if not self.fils:
                    if not demarres:
                        break
                    continue
                self._surveiller()
        finally:
            self._arreter_les_fils()
        self._memoriser_attentes(pendantes)

    def _regles_dues(self):
        """[(regle, decision, no)] des regles actives dues, dans l'ordre du fichier."""
        base, c = self.base, self.lancement.compteurs
        resultat = []
        filtre = {f.lower() for f in self.filtre} if self.filtre else None
        for regle in self.parametrage.regles:
            if not regle.id or (filtre is not None and regle.id.lower() not in filtre):
                continue
            c["regles"] += 1
            if not regle.actif:
                c["non_dues"] += 1
                continue
            no = base.numero_regle(regle.id)
            etat = base.regle(no) if no is not None else None
            decision = planification.evaluer(regle, etat, self.maintenant(), self.fuseau)
            if decision.nouvelle:
                if decision.creneau is not None and no is not None:
                    base.definir_creneau(no, decision.creneau)
                c["non_dues"] += 1
                self.journal.evenement("regle_nouvelle", "INFO", regle=regle.id,
                                       message="regle nouvelle : elle demarrera au prochain creneau "
                                               "(ou immediatement avec --lancer-maintenant)")
                continue
            if not decision.due:
                c["non_dues"] += 1
                if etat and etat["attente"]:            # le creneau a expire : retour a l'etat precedent
                    base.definir_attente(no, None)
                self.journal.evenement("regle_non_due", "DEBUG", regle=regle.id, motif=decision.motif)
                continue
            resultat.append((regle, decision, no))
        return resultat

    def _lancer_prets(self, pendantes):
        """Evalue les dependances de chaque regle en attente et demarre celles qui sont pretes,
        dans la limite de `parallele_max`. Renvoie le nombre de regles demarrees ou retirees."""
        lignes = {l["id"].lower(): l for l in self.base.toutes_les_regles()}
        progres = 0
        for element in list(pendantes):
            regle, decision, no = element
            ligne = lignes.get(regle.id.lower())
            if ligne is not None and ligne["en_cours"]:           # prise entre-temps par un autre lancement
                pendantes.remove(element)
                self.lancement.compteurs["non_dues"] += 1
                self.journal.evenement("regle_non_due", "INFO", regle=regle.id, motif="deja en cours")
                progres += 1
                continue
            evaluation = (dependances.evaluer(regle, ligne, lignes, self.base, self.bloquees)
                          if regle.apres else dependances.Evaluation(dependances.PRETE))
            self.evaluations[regle.id] = evaluation
            if evaluation.etat == dependances.BLOQUEE:
                self.bloquees.add(regle.id.lower())
            if evaluation.etat != dependances.PRETE:
                continue
            limite = self.entete.parallele_max
            if limite is not None and len(self.fils) >= limite:
                continue
            pendantes.remove(element)
            self._demarrer(regle, decision, no)
            progres += 1
        return progres

    # ------------------------------------------------------------------ #
    # Demarrage d'un fils
    # ------------------------------------------------------------------ #
    def _commande_fils(self, regle, execution_id):
        return [sys.executable, "-m", "file_management", "--config", os.path.abspath(self.parametrage.chemin),
                "--executer-regle", regle.id, "--execution-id", str(execution_id)]

    def _demarrer(self, regle, decision, no, declencheur=None, creneau=None):
        base = self.base
        execution_id = base.demarrer_execution(
            no, declencheur or decision.declencheur, os.getpid(), pid_cree_le=self.cree_le, hote=nom_hote(),
            build=self.build, creneau=decision.creneau if creneau is None else creneau,
            controler_decision=True)
        if execution_id is None:                      # prise par un autre lancement, ou sa demande/son creneau aussi
            self.lancement.compteurs["non_dues"] += 1
            self.journal.evenement("regle_non_due", "INFO", regle=regle.id,
                                   motif="deja pris par un autre lancement")
            return None
        if self.direct:
            fils = self._executer_direct(regle, no, execution_id, declencheur or decision.declencheur,
                                         decision.creneau if creneau is None else creneau)
        else:
            fils = self._lancer_processus(regle, no, execution_id)
        if fils is not None:
            self.fils[regle.id] = fils
        return fils

    def _executer_direct(self, regle, no, execution_id, declencheur, creneau):
        try:
            bilan = lancer_regle(regle, self.entete, self.base, self.journal, declencheur=declencheur,
                                 maintenant=self.maintenant_dt, dormir=self.dormir, build=self.build,
                                 creneau=creneau, execution_existante=execution_id, journaliser_fin=False)
        except RegleDejaEnCours:
            return None
        return Fils(regle, no, execution_id, resultat=resultat_depuis_bilan(bilan, regle.id, execution_id))

    def _lancer_processus(self, regle, no, execution_id):
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        env["PYTHONPATH"] = RACINE + os.pathsep + env.get("PYTHONPATH", "")
        try:
            popen = subprocess.Popen(self.commande_fils(regle, execution_id), stdin=subprocess.PIPE,
                                     cwd=RACINE, env=env, universal_newlines=True)
        except OSError as e:
            self._fin_anormale_sans_fils(regle, no, execution_id, "lancement du processus impossible : %s" % e)
            return None
        job = processus.JobObject()
        job.assigner(popen)
        self.base.attacher_processus(execution_id, popen.pid, processus.date_creation(popen.pid))
        try:
            popen.stdin.write("go\n")                 # le fils attend d'etre dans son job avant de commencer
            popen.stdin.flush()
            popen.stdin.close()
        except OSError:
            pass
        return Fils(regle, no, execution_id, popen, job)

    # ------------------------------------------------------------------ #
    # Surveillance
    # ------------------------------------------------------------------ #
    def _surveiller(self):
        """Attend qu'au moins un fils se termine ; traite les depassements de duree."""
        while True:
            termines = [f for f in list(self.fils.values()) if f.termine()]
            for fils in termines:
                self._terminer(fils)
            if termines:
                return
            if self.rappel:
                self.rappel(self)
            for fils in list(self.fils.values()):
                if (not fils.alerte and fils.popen is not None
                        and time.monotonic() - fils.debut > fils.regle.duree_max_sec):
                    if self._depasse(fils):
                        return
            if not self.fils:
                return
            time.sleep(self.pas_sec)

    def _terminer(self, fils):
        """Fin normale ou anormale d'un fils : journalise la fin de la regle."""
        self.fils.pop(fils.regle.id, None)
        code = fils.popen.returncode if fils.popen is not None else 0
        if fils.job is not None:
            fils.job.fermer()                       # arrete aussi ce qui aurait survecu au fils
        resultat = fils.resultat or lire_resultat(self.entete, fils.execution_id)
        if resultat is None:
            ligne = self.base.execution(fils.execution_id)
            if ligne is not None and ligne["fin"] is not None:
                resultat = self._resultat_depuis_ligne(fils, ligne)
            else:
                self._fin_anormale(fils, "le processus de la regle s'est arrete sans resultat (code %s)" % code)
                return
        if fils.alerte and resultat["statut"] == "SUCCES":
            self.base.forcer_warning(fils.execution_id, fils.no)
            resultat["statut"] = "WARNING"
        self._journaliser_fin(fils.regle, fils.execution_id, resultat, code)

    def _resultat_depuis_ligne(self, fils, ligne):
        statut = ligne["statut"] if ligne["statut"] in ("SUCCES", "WARNING") else "ERREUR"
        return {"regle": fils.regle.id, "execution_id": fils.execution_id, "statut": statut,
                "motif": ligne["message"], "situation_finale": ligne["situation_finale"],
                "compteurs": {"selectionnes": ligne["nb_selectionnes"], "livres": ligne["nb_livres"],
                              "ignores": ligne["nb_ignores"], "erreurs": ligne["nb_erreurs"],
                              "en_attente": ligne["nb_en_attente"], "octets": ligne["octets_livres"]},
                "erreur": None, "arret_apres_erreur": False,
                "duree_ms": (ligne["fin"] - ligne["debut"]) * 1000}

    def _journaliser_fin(self, regle, execution_id, resultat, code=None):
        c = self.lancement.compteurs
        c["lancees"] += 1
        c[resultat["statut"]] += 1
        self.lancement.noter(NIVEAU_STATUT[resultat["statut"]])
        self.journal.evenement("regle_terminee", NIVEAU_STATUT[resultat["statut"]], regle=regle.id,
                               execution_id=execution_id, statut=resultat["statut"], motif=resultat["motif"],
                               compteurs=resultat["compteurs"], duree_ms=resultat["duree_ms"],
                               **({"code_fils": code} if code else {}))

    def _fin_anormale(self, fils, message):
        """Le fils a disparu sans rien ecrire : la regle passe en ERREUR (arret_anormal)."""
        if fils.job is not None:
            fils.job.terminer()
        if fils.popen is not None and fils.popen.poll() is None:
            processus.tuer_arbre(fils.popen.pid)
        self._fin_anormale_sans_fils(fils.regle, fils.no, fils.execution_id, message)

    def _fin_anormale_sans_fils(self, regle, no, execution_id, message):
        arret = regle.apres_erreur == "arreter"
        self.base.liberer_flag(no, message, statut_regle="ERREUR", arret_apres_erreur=arret,
                               erreur={"situation": "arret_anormal", "message": message})
        self.journal.evenement("arret_anormal", "ERREUR", regle=regle.id, execution_id=execution_id,
                               message=message)
        self._journaliser_fin(regle, execution_id, {
            "statut": "ERREUR", "motif": message, "duree_ms": 0,
            "compteurs": {"selectionnes": 0, "livres": 0, "ignores": 0, "erreurs": 1, "en_attente": 0,
                          "octets": 0}})

    # ------------------------------------------------------------------ #
    # Duree maximale (docs/02, section 2, etape 3)
    # ------------------------------------------------------------------ #
    def _depasse(self, fils):
        """Applique `si_duree_depassee`. Renvoie True si le fils a ete retire de la surveillance."""
        regle, base = fils.regle, self.base
        ligne = base.execution(fils.execution_id)
        if ligne is not None and ligne["fin"] is not None:
            return False                              # il vient de terminer : traite au prochain tour
        politique = regle.si_duree_depassee
        message = "duree maximale depassee (%d s)" % regle.duree_max_sec
        if politique == "alerter":
            fils.alerte = True
            self.lancement.noter("WARNING")
            self.lancement.compteurs["depassees"] += 1
            self.journal.evenement("duree_depassee", "WARNING", regle=regle.id, execution_id=fils.execution_id,
                                   message=message + " : l'execution continue", action="alerter")
            return False
        self._tuer(fils)
        self.fils.pop(regle.id, None)
        self.lancement.compteurs["depassees"] += 1
        etat = base.regle(fils.no)
        if politique == "relancer" and (etat["relances"] or 0) < regle.relances_max:
            base.liberer_flag(fils.no, message + " : relance", statut_regle="ARRETEE")
            base.incrementer_relances(fils.no)
            self.journal.evenement("duree_depassee", "WARNING", regle=regle.id, execution_id=fils.execution_id,
                                   message=message + " : arbre de processus arrete, relance",
                                   action="relancer", relance=(etat["relances"] or 0) + 1)
            self.lancement.noter("WARNING")
            decision = planification.Decision(True, "relance", None, "relance apres depassement de duree")
            self._demarrer(regle, decision, fils.no)
            return True
        if politique == "relancer":
            message += " ; %d relance(s) epuisee(s)" % regle.relances_max
        arret = regle.apres_erreur == "arreter"
        erreur = {"situation": "duree_depassee", "message": message}
        base.terminer_execution(fils.execution_id, fils.no, "ERREUR", motif=message,
                                compteurs={"erreurs": 1}, situation_finale="duree_depassee", message=message,
                                erreur=erreur, arret_apres_erreur=arret)
        self.journal.evenement("duree_depassee", "ERREUR", regle=regle.id, execution_id=fils.execution_id,
                               message=message + " : arbre de processus arrete", action="erreur")
        self._journaliser_fin(regle, fils.execution_id, {
            "statut": "ERREUR", "motif": message, "duree_ms": regle.duree_max_sec * 1000,
            "compteurs": {"selectionnes": 0, "livres": 0, "ignores": 0, "erreurs": 1, "en_attente": 0,
                          "octets": 0}})
        return True

    def _tuer(self, fils):
        """Arrete le fils ET tout ce qu'il a lance (Job Object, sinon taskkill /T)."""
        arrete = fils.job.terminer() if fils.job is not None else False
        if not arrete:
            processus.tuer_arbre(fils.popen.pid)
        try:
            fils.popen.wait(timeout=DELAI_ARRET_FILS_SEC)
        except subprocess.TimeoutExpired:
            processus.tuer_arbre(fils.popen.pid)
        if fils.job is not None:
            fils.job.fermer()

    def _arreter_les_fils(self):
        """Fin du lancement ou interruption : aucun fils ne doit survivre a l'orchestrateur."""
        for fils in list(self.fils.values()):
            if fils.popen is not None and fils.popen.poll() is None:
                self._tuer(fils)
                self.base.liberer_flag(fils.no, "orchestrateur interrompu", statut_regle="ERREUR",
                                       arret_apres_erreur=fils.regle.apres_erreur == "arreter",
                                       erreur={"situation": "arret_anormal",
                                               "message": "orchestrateur interrompu"})
            elif fils.job is not None:
                fils.job.fermer()
        self.fils.clear()

    # ------------------------------------------------------------------ #
    # Regles qui n'ont pas pu partir (docs/02, section 3.2)
    # ------------------------------------------------------------------ #
    def _memoriser_attentes(self, pendantes):
        """EN_ATTENTE / BLOQUEE : memorise l'etat et journalise une fois par creneau, au niveau
        `si_condition_non_remplie` (compte dans le code retour)."""
        c = self.lancement.compteurs
        for regle, decision, no in pendantes:
            evaluation = self.evaluations.get(regle.id)
            if evaluation is None or evaluation.etat == dependances.PRETE:
                continue
            ligne = self.base.regle(no)
            creneau = decision.creneau
            if evaluation.etat == dependances.BLOQUEE:
                c["bloquees"] += 1
            else:
                c["en_attente"] += 1
            if regle.planification is not None and regle.planification.type == "apres_dependances":
                # pas d'horaire : on ne signale que le passage en BLOQUEE (l'attente est normale)
                a_signaler = (evaluation.etat == dependances.BLOQUEE
                              and (ligne["attente"] != dependances.BLOQUEE or ligne["attente_motif"] != evaluation.motif))
            else:
                a_signaler = (ligne["attente_depuis"] != creneau or ligne["attente"] is None
                              or (evaluation.etat == dependances.BLOQUEE and ligne["attente"] != dependances.BLOQUEE))
            self.base.definir_attente(no, evaluation.etat, evaluation.motif, creneau)
            if a_signaler:
                niveau = regle.si_condition_non_remplie
                c["non_lancees"] += 1
                self.lancement.noter(niveau)
                self.journal.evenement("regle_non_lancee", niveau, regle=regle.id, attente=evaluation.etat,
                                       motif=evaluation.motif, bloquante=evaluation.bloquante)
