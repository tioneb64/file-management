"""Execution d'une regle : controles, selection, anti-doublon, livraison verifiee, action du
mode (copie / deplacement / archivage), situations anormales, archive degradee.

Specification : docs/02-moteur.md sections 5 a 8 (les programmes externes, section 9, sont
branches au jalon J7). Une instance de ExecutionRegle traite UNE regle dans UN processus.
"""
import datetime
import hashlib
import os
import socket
import time

from file_management import base as modele_base
from file_management import chemins, processus, programmes, selection, transfert
from file_management.parametrage import MODE_SYNCHRO, MODES_HORODATAGE, MODES_MESURE, MODES_TRANSFERT
from file_management.transfert import (CibleExiste, ErreurCible, ErreurSource, ErreurTransfert,
                             ErreurVerification, FichierInstable, SourceDisparue, SourceModifiee)

RANG = {"INFO": 0, "WARNING": 1, "ERREUR": 2}
NIVEAU_STATUT = {"SUCCES": "INFO", "WARNING": "WARNING", "ERREUR": "ERREUR"}
STATUTS = ("SUCCES", "WARNING", "ERREUR")
EXCEPTIONS_RETENTABLES = (ErreurTransfert, OSError)
MARGE_OCTETS = 1024 * 1024
APERCU_MAX = 500                   # fichiers detailles dans la reponse d'une simulation


class Bilan(object):
    def __init__(self):
        self.statut = "SUCCES"
        self.attente = False                # modes count / size : bornes non respectees (statut ATTENTE)
        self.statut_final = None            # statut enregistre en base : SUCCES, WARNING, ERREUR ou ATTENTE
        self.motif = None
        self.situation_finale = None
        self.compteurs = {"selectionnes": 0, "livres": 0, "ignores": 0, "erreurs": 0,
                          "en_attente": 0, "octets": 0}
        self.erreur = None                  # {"situation", "message"} de la premiere ERREUR
        self.arret_apres_erreur = False
        self.duree_ms = 0
        self.apercu = []                    # simulation : fichiers qui seraient livres (plafonne)
        self.apercu_total = 0
        self.octets_prevus = 0              # volume a livrer, connu avant la livraison (controle d'espace)


def _octets_lisibles(n):
    for unite in ("octets", "Ko", "Mo", "Go", "To"):
        if n < 1024 or unite == "To":
            return ("%d %s" % (n, unite)) if unite == "octets" else ("%.1f %s" % (n, unite)).replace(".0 ", " ")
        n /= 1024.0


class EchecSituation(Exception):
    """Une operation a echoue apres toutes les tentatives de sa situation."""

    def __init__(self, situation, message, cause=None):
        Exception.__init__(self, message)
        self.situation = situation
        self.message = message
        self.cause = cause


class ArretRegle(Exception):
    """Interne : la regle s'arrete (suite = arreter_regle ou controle bloquant)."""

    def __init__(self, situation, message):
        Exception.__init__(self, message)
        self.situation = situation
        self.message = message


class IgnorerFichier(Exception):
    """Interne : si_existe_cible = ignorer."""


class ErreurProgramme(ErreurTransfert):
    """Un programme externe a echoue (code retour inattendu, duree depassee, lancement impossible)."""


def situation_copie(erreur):
    """Situation (docs/01 section 6) correspondant a un echec de copie."""
    if isinstance(erreur, SourceDisparue):
        return "fichier_disparu"
    if isinstance(erreur, ErreurSource):
        return "fichier_verrouille" if erreur.verrou else "copie_echec"
    if isinstance(erreur, FichierInstable):
        return "fichier_instable"
    if isinstance(erreur, ErreurVerification):
        return "verification_echec"
    if isinstance(erreur, CibleExiste):
        return "fichier_existe_cible"
    return "copie_echec"


class ExecutionRegle(object):
    def __init__(self, regle, entete, base, regle_no, journal, simulation=False, maintenant=None,
                 dormir=time.sleep, declencheur=None, simulation_programmes=False, execution_id=None):
        self.declencheur = declencheur
        self.simulation_programmes = simulation_programmes
        self.execution_id = execution_id
        self.resultats = []                       # un element par fichier traite (liste de apres_lot)
        self._res = {}
        self.regle = regle
        self.entete = entete
        self.base = base
        self.no = regle_no
        self.journal = journal
        self.simulation = simulation
        self.maintenant = maintenant or datetime.datetime.now
        self.dormir = dormir
        self.debut = self.maintenant()            # les variables de date valent le debut du lancement
        self.bilan = Bilan()
        self.rang = 0
        self.archive_differee = False
        self.archive_dir = None
        self.mode_ecrit = not simulation
        self.horodate = bool(regle.horodater and regle.mode in MODES_HORODATAGE)
        self.est_exclu = None
        self.dossiers_interdits = []

    # ------------------------------------------------------------------ #
    # Utilitaires
    # ------------------------------------------------------------------ #
    def _log(self, nom, niveau="INFO", **champs):
        if self.simulation:
            champs["simulation"] = True
        self.journal.evenement(nom, niveau, **champs)

    def _noter_niveau(self, niveau):
        self.rang = max(self.rang, RANG[niveau])

    def _signaler(self, situation, message, **champs):
        """Journalise une situation anormale au niveau de sa reaction et met a jour le bilan."""
        cfg = self.regle.situations[situation]
        evenement = "fichier_erreur" if "fichier" in champs else "regle_anomalie"
        self._log(evenement, cfg.niveau_final, situation=situation, message=message, **champs)
        self._noter_niveau(cfg.niveau_final)
        if cfg.niveau_final == "ERREUR":
            self.bilan.compteurs["erreurs"] += 1
            if self.bilan.erreur is None:
                self.bilan.erreur = {"situation": situation, "message": message}
        return cfg

    def _essayer(self, operation, classifier, **champs):
        """Execute `operation` avec les tentatives et le delai de la situation que `classifier`
        associe a chaque echec. Leve EchecSituation apres la derniere tentative."""
        echecs = {}
        while True:
            try:
                return operation()
            except EXCEPTIONS_RETENTABLES as e:
                situation = classifier(e)
                cfg = self.regle.situations[situation]
                echecs[situation] = echecs.get(situation, 0) + 1
                if echecs[situation] < cfg.tentatives:
                    self._log("tentative_echouee", "WARNING", situation=situation,
                              tentative=echecs[situation], tentatives=cfg.tentatives,
                              message=str(e), **champs)
                    self.dormir(cfg.delai_sec)
                    continue
                raise EchecSituation(situation, str(e), e)

    def _arreter(self, echec, **champs):
        """Une situation bloquante : journalise puis arrete la regle."""
        self._signaler(echec.situation, echec.message, **champs)
        raise ArretRegle(echec.situation, echec.message)

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #
    def executer(self):
        try:
            self._preparer_chemins()
            self._appel_reprise()
            if self.regle.mode == MODE_SYNCHRO:
                self._synchroniser()
                return self._finir()
            self._intentions_interrompues()
            self._controles_prealables()
            self._actions_en_attente()
            if self.regle.mode in MODES_MESURE:
                self._mesurer()
            elif self.regle.mode == "suppression":
                self._supprimer_tout()
            else:
                a_livrer = self._selectionner()
                if a_livrer:
                    a_livrer = self._avant_lot(a_livrer)
                if a_livrer:
                    self._livrer_tout(a_livrer)
                    self._apres_lot()
        except ArretRegle as a:
            self.bilan.motif = a.message
            self.bilan.situation_finale = a.situation
        return self._finir()

    def _finir(self):
        bilan = self._conclure()
        if bilan.statut == "ERREUR":
            self._sur_erreur(bilan)
        return bilan

    def _synchroniser(self):
        """Mode synchro : lance avant_lot puis avant_fichier (s'ils existent), puis rend son statut.
        Aucun fichier n'est lu ni touche ; les points apres_* n'ont pas de sens et ne sont pas appeles.
        Seul le code retour 0 est un succes : un programme qui repond 1 (« rien a faire ») ou autre
        chose est une erreur, la regle ne peut dire que oui ou non."""
        appeles = 0
        for point in ("avant_lot", "avant_fichier"):
            try:
                if self._programme(point, codes=(0,)) is not None:
                    appeles += 1
            except EchecSituation as e:
                self._arreter(e)
        self.bilan.motif = ("synchronisation : %d programme(s) execute(s)" % appeles) if appeles \
            else "synchronisation : aucun programme a lancer"

    # ------------------------------------------------------------------ #
    # Programmes externes (docs/02, section 9)
    # ------------------------------------------------------------------ #
    def _dossier_travail(self):
        if self.entete.dossier_travail:
            return self.entete.dossier_travail
        import tempfile
        return os.path.join(tempfile.gettempdir(), "copie_travail")

    def _variables_programme(self, point, c, destination, statut, chemin_liste, chemin_json):
        r = self.regle
        archive = self.archive_dir or ""
        valeurs = {"environnement": self.entete.environnement, "regle": r.id, "source": self.source or "",
                   "cible": self.cible or "", "archive": archive, "date": self.debut.strftime("%Y-%m-%d"),
                   "fichier": c.chemin if c else "", "nom": c.nom if c else "",
                   "fichier_cible": destination or "", "liste": chemin_liste or "",
                   "liste_json": chemin_json or ""}
        environnement = {
            "COPIE_ENVIRONNEMENT": valeurs["environnement"], "COPIE_REGLE": r.id,
            "COPIE_EXECUTION_ID": str(self.execution_id if self.execution_id is not None else ""),
            "COPIE_SOURCE": valeurs["source"], "COPIE_CIBLE": valeurs["cible"], "COPIE_ARCHIVE": archive,
            "COPIE_MODE": r.mode, "COPIE_FICHIER": valeurs["fichier"],
            "COPIE_FICHIER_CIBLE": valeurs["fichier_cible"], "COPIE_LISTE": valeurs["liste"],
            "COPIE_LISTE_JSON": valeurs["liste_json"],
            "COPIE_REPRISE": "1" if self.declencheur == "reprise" else "0",
            "COPIE_SIMULATION": "1" if self.simulation else "0", "COPIE_POINT_APPEL": point,
            "COPIE_STATUT": statut or ""}
        return valeurs, environnement

    def _programme(self, point, c=None, destination=None, liste=None, statut=None, codes=None, **champs):
        """Appelle le programme du point d'appel `point`, avec les tentatives de la situation
        `programme_<point>`. Renvoie son code retour (0 ou 1), ou None s'il n'y a pas de
        programme. Leve EchecSituation pour tout autre code, une duree depassee ou un lancement
        impossible. `codes` : codes retour acceptes (par defaut ceux du point d'appel)."""
        programme = self.regle.programmes.get(point)
        if programme is None:
            return None
        if self.simulation and not self.simulation_programmes:
            self._log("programme_non_appele", "DEBUG", point=point)
            return None
        travail = self._dossier_travail()
        fichiers_liste = programmes.ecrire_listes(travail, self.execution_id, point, liste) if liste is not None else (None, None)
        valeurs, environnement = self._variables_programme(point, c, destination, statut, *fichiers_liste)

        def operation():
            res = programmes.executer(programme, point, valeurs, environnement, travail)
            ok = res.accepte(point, codes)
            self._log("programme_appele", "INFO" if ok else "WARNING", point=point, commande=res.argv,
                      code=res.code, duree_ms=res.duree_ms, depasse=res.depasse or None,
                      sortie=res.sortie, **champs)
            if ok:
                return res.code
            raise ErreurProgramme("programme %s : %s" % (point, res.explication(point, codes)))
        try:
            return self._essayer(operation, lambda e: "programme_" + point, **champs)
        finally:
            if liste is not None:
                programmes.supprimer_listes(*fichiers_liste)

    def _appel_reprise(self):
        if self.declencheur != "reprise":
            return
        try:
            self._programme("reprise")
        except EchecSituation as e:
            self._arreter(e)

    def _avant_lot(self, a_livrer):
        """Renvoie la liste a livrer : inchangee, vide (le programme a repondu « rien a faire ») ou
        relue (le programme a pu ajouter, retirer ou modifier des fichiers)."""
        try:
            code = self._programme("avant_lot", liste=[programmes.entree_fichier(c) for c in a_livrer])
        except EchecSituation as e:
            self._arreter(e)
        if code is None:
            return a_livrer
        if code == 1:
            self.bilan.motif = "avant_lot : rien a faire"
            self._log("avant_lot_rien_a_faire", "INFO", message="le programme avant_lot demande de ne rien livrer")
            return []
        return self._selectionner()               # le programme a tourne : la source est relue

    def _apres_lot(self):
        if not self.resultats:
            return
        try:
            self._programme("apres_lot", liste=self.resultats, statut=STATUTS[self.rang])
        except EchecSituation as e:
            self._signaler(e.situation, e.message)

    def _sur_erreur(self, bilan):
        """Notification : le resultat du programme est seulement journalise."""
        programme = self.regle.programmes.get("sur_erreur")
        if programme is None or (self.simulation and not self.simulation_programmes):
            return
        liste = programmes.ecrire_listes(self._dossier_travail(), self.execution_id, "sur_erreur", self.resultats)
        try:
            valeurs, environnement = self._variables_programme("sur_erreur", None, None, bilan.statut, *liste)
            environnement["COPIE_SITUATION"] = (bilan.erreur or {}).get("situation") or bilan.situation_finale or ""
            environnement["COPIE_MESSAGE"] = bilan.motif or ""
            res = programmes.executer(programme, "sur_erreur", valeurs, environnement, self._dossier_travail())
            self._log("programme_appele", "INFO" if res.code == 0 and not res.depasse and not res.erreur else "WARNING",
                      point="sur_erreur", commande=res.argv, code=res.code, duree_ms=res.duree_ms,
                      depasse=res.depasse or None, sortie=res.sortie or res.erreur)
        finally:
            programmes.supprimer_listes(*liste)

    def _preparer_chemins(self):
        regle = self.regle
        self.cible = os.path.normpath(os.path.expandvars(regle.cible)) if regle.cible else None
        if regle.mode == MODE_SYNCHRO:
            self.source = None                  # aucun dossier : rien a preparer
            return
        self.source = os.path.normpath(os.path.expandvars(regle.source))
        if regle.mode == "archivage":
            self.archive_dir = chemins.resoudre_archive(regle.archive, self.source, self.debut)
        self.est_exclu = chemins.exclusion_dossiers(
            self.source, regle.archive if regle.mode == "archivage" else None,
            [regle.dossier_temporaire])
        self.dossier_temporaire = (os.path.normpath(os.path.expandvars(regle.dossier_temporaire))
                                   if regle.dossier_temporaire and regle.mode in MODES_TRANSFERT else None)

    # ----- 6.3 : livraisons interrompues ----------------------------------- #
    def _intentions_interrompues(self):
        deja = self.base.incertains(self.no)
        nouveaux = []
        for it in self.base.intentions(self.no):
            if self._livraison_verifiee(it):
                self._log("livraison_reprise", "INFO", fichier=it["chemin_source"],
                          cible=it["chemin_cible"], message="copie retrouvee intacte dans la cible")
                if self.mode_ecrit:
                    suivante = {"deplacement": "suppression", "archivage": "archivage"}.get(self.regle.mode)
                    self.base.confirmer_livraison(it["cle"], termine=suivante is None,
                                                  action_suivante=suivante)
            elif self.regle.si_cible_absente == "recopier" and self.regle.mode == "copie":
                if self.mode_ecrit:
                    self.base.oublier_fichier(it["cle"])
                self._log("livraison_a_refaire", "INFO", fichier=it["chemin_source"])
            else:
                nouveaux.append(it)
                if self.mode_ecrit:
                    self.base.marquer_incertain(it["cle"])
        for chemin_source, chemin_cible in ([(i[1], i[2]) for i in deja]
                                            + [(i["chemin_source"], i["chemin_cible"]) for i in nouveaux]):
            self._log("livraison_incertaine", "ERREUR", fichier=chemin_source, cible=chemin_cible,
                      message="resultat inconnu apres un arret brutal : decision d'exploitation requise")
        if deja or nouveaux:
            total = len(deja) + len(nouveaux)
            self.bilan.compteurs["erreurs"] += total
            self._noter_niveau("ERREUR")
            message = ("%d livraison(s) de resultat inconnu apres un arret brutal : verifier la cible "
                       "puis indiquer si les fichiers sont a relivrer ou livres" % total)
            self.bilan.erreur = {"situation": "livraison_incertaine", "message": message}
            raise ArretRegle("livraison_incertaine", message)

    def _livraison_verifiee(self, it):
        try:
            st = os.stat(it["chemin_source"])
            if st.st_size != it["taille"] or st.st_mtime_ns != it["mtime_ns"]:
                return False
            if os.path.getsize(it["chemin_cible"]) != it["taille"]:
                return False
            return transfert.sha256_fichier(it["chemin_source"]) == transfert.sha256_fichier(it["chemin_cible"])
        except (OSError, TypeError):
            return False

    # ----- 3 : controles prealables ---------------------------------------- #
    def _verifier_ecriture(self, dossier):
        if self.simulation:
            if not os.path.isdir(dossier) and not self.regle.creer_dossiers:
                raise ErreurCible("dossier absent : %s" % dossier)
            return
        try:
            if not os.path.isdir(dossier):
                if not self.regle.creer_dossiers:
                    raise ErreurCible("dossier absent : %s" % dossier)
                os.makedirs(dossier, exist_ok=True)
            essai = os.path.join(dossier, ".test_ecriture_%d" % os.getpid())
            with open(essai, "wb") as f:
                f.write(b"x")
            os.remove(essai)
        except OSError as e:
            raise ErreurCible("ecriture impossible dans %s : %s" % (dossier, e), e)

    def _controles_prealables(self):
        regle = self.regle
        try:
            self._essayer(lambda: os.listdir(self.source), lambda e: "source_inaccessible")
        except EchecSituation as e:
            self._arreter(e)
        self._log("controle_prealable", "INFO", controle="source", chemin=self.source)
        if regle.mode not in MODES_TRANSFERT:
            return                          # suppression, count, size : pas de cible ni d'archive

        try:
            self._essayer(lambda: self._verifier_ecriture(self.cible), lambda e: "cible_inaccessible")
            if self.dossier_temporaire:
                self._essayer(lambda: self._verifier_temporaire(), lambda e: "cible_inaccessible")
        except EchecSituation as e:
            self._arreter(e)
        self._log("controle_prealable", "INFO", controle="cible", chemin=self.cible)

        if regle.mode == "archivage":
            try:
                self._essayer(lambda: self._verifier_ecriture(self.archive_dir),
                              lambda e: "archive_inaccessible")
                self._log("controle_prealable", "INFO", controle="archive", chemin=self.archive_dir)
            except EchecSituation as e:
                self._archive_indisponible(e)

    def _verifier_temporaire(self):
        self._verifier_ecriture(self.dossier_temporaire)
        if not chemins.meme_volume(self.dossier_temporaire, self.cible):
            raise ErreurCible("dossier_temporaire (%s) doit etre sur le meme volume que la cible (%s)"
                              % (self.dossier_temporaire, self.cible))

    def _archive_indisponible(self, echec):
        cfg = self._signaler(echec.situation, echec.message, chemin=self.archive_dir)
        if cfg.suite == "continuer_en_differe":
            self.archive_differee = True
            self._log("archivage_degrade", "WARNING", chemin=self.archive_dir,
                      message="les fichiers sont livres ; l'archivage sera retente aux prochains lancements")
            self._noter_niveau("WARNING")
            if self.mode_ecrit:
                self.base.definir_archivage_degrade(self.no, True)
        else:
            raise ArretRegle(echec.situation, echec.message)

    # ----- 2 : actions restees a faire (suppression / archivage differes) --- #
    def _actions_en_attente(self):
        regle = self.regle
        actions = [a for a in self.base.actions(self.no) if a["type"] in ("suppression", "archivage")]
        for action in actions:
            if action["type"] == "archivage" and self.archive_differee:
                continue
            if self.simulation:
                self._log("action_a_rejouer", "INFO", type=action["type"], fichier=action["chemin_source"])
                continue
            self._rejouer(action)
        if self.mode_ecrit and regle.mode == "archivage":
            restantes = [a for a in self.base.actions(self.no, "archivage")]
            if (not restantes and not self.archive_differee
                    and self.base.regle(self.no)["archivage_degrade"]):
                self.base.definir_archivage_degrade(self.no, False)
                self._log("archivage_retabli", "INFO", message="plus aucune action d'archivage en attente")

    def _rejouer(self, action):
        champs = {"fichier": action["chemin_source"]}
        try:
            self._executer_action(action["type"], action["chemin_source"], action["taille"],
                                  action["mtime_ns"], action["chemin_archive"], **champs)
            self.base.terminer_fichier(action["cle"])
        except EchecSituation as e:
            self._apres_echec_action(e, action["cle"], action["type"], **champs)

    def _apres_echec_action(self, echec, cle, type_, **champs):
        if echec.situation == "source_modifiee":
            self._source_modifiee(cle, echec.message, **champs)
        else:
            self._action_en_echec(echec, cle, type_, **champs)

    def _source_modifiee(self, cle, message, **champs):
        """G4 : l'original a change, il est conserve ; la version livree est complete."""
        self._signaler("source_modifiee", message, **champs)
        if self.mode_ecrit:
            self.base.terminer_fichier(cle)

    def _action_en_echec(self, echec, cle, type_, **champs):
        cfg = self._signaler(echec.situation, echec.message, **champs)
        if cfg.suite == "arreter_regle":
            raise ArretRegle(echec.situation, echec.message)
        self.bilan.compteurs["en_attente"] += 1
        self._log("action_differee", "WARNING", type=type_, message=echec.message, **champs)
        self._noter_niveau("WARNING")
        action = self.base.action(cle)
        if action is not None:
            self.base.echec_action(action["id"], echec.message)

    def _executer_action(self, type_, source, taille, mtime_ns, chemin_archive, **champs):
        """Suppression ou archivage de l'original, avec les tentatives de la situation."""
        if type_ == "suppression":
            def operation():
                return transfert.supprimer_original(source, taille, mtime_ns)
            situation = "suppression_echec"
        else:
            def operation():
                return self._archiver(source, taille, mtime_ns, chemin_archive)
            situation = "archivage_echec"

        def classifier(e):
            if isinstance(e, SourceModifiee):
                return "source_modifiee"
            if isinstance(e, CibleExiste):
                return "fichier_existe_archive"
            return situation
        resultat = self._essayer(operation, classifier, **champs)
        if resultat == "supprime":
            self._log("fichier_supprime", "INFO", **champs)
        elif resultat == "archive":
            self._log("fichier_archive", "INFO", archive=chemin_archive, **champs)
        return resultat

    def _archiver(self, source, taille, mtime_ns, destination):
        """Deplace l'original dans l'archive : renommage sur le meme volume, sinon copie verifiee
        puis suppression. Renvoie 'archive' ou 'absent'."""
        if not transfert.verifier_original_inchange(source, taille, mtime_ns):
            return "absent"
        politique = self.regle.si_existe_archive
        maintenant = self.maintenant()
        try:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
        except OSError as e:
            raise ErreurCible("dossier d'archive inaccessible : %s" % e, e)
        meme = chemins.meme_volume(source, os.path.dirname(destination))
        for compteur in range(1000):
            candidat = destination
            if compteur:
                dossier, nom = os.path.split(destination)
                candidat = os.path.join(dossier, chemins.nom_avec_suffixe(nom, maintenant, compteur - 1))
            if politique == "suffixe" and compteur == 0 and os.path.lexists(destination):
                continue
            try:
                if meme:
                    transfert.renommer(source, candidat, ecraser=(politique == "ecraser"))
                else:
                    transfert.copier_verifier(source, candidat, self._temporaire(candidat),
                                              ecraser=(politique == "ecraser"),
                                              attendu=(taille, mtime_ns))
                    transfert.supprimer_original(source, taille, mtime_ns)
                return "archive"
            except CibleExiste:
                if politique != "suffixe":
                    raise
        raise ErreurCible("aucun nom libre dans l'archive pour %s" % destination)

    # ----- modes sans transfert : count, size, suppression ------------------ #
    def _lister_brut(self):
        """Tous les fichiers qui correspondent a la selection (sans anti-doublon : on mesure ou on supprime
        ce qui est present maintenant)."""
        regle = self.regle
        interdits = [self.dossier_temporaire] if self.dossier_temporaire else []

        def operation():
            res = selection.lister(self.source, regle.selection, self.maintenant(), self.est_exclu, interdits)
            if res.erreurs and not res.candidats:
                raise res.erreurs[0][1]
            return res
        try:
            res = self._essayer(operation, lambda e: "source_inaccessible")
        except EchecSituation as e:
            self._arreter(e)
        self._bilan_selection(res)
        return res

    def _mesurer(self):
        """Modes count et size : mesure la selection et compare aux bornes ; hors bornes, la regle
        sort en ATTENTE (ni succes ni erreur) : les regles qui en dependent patientent."""
        regle, b = self.regle, self.bilan
        res = self._lister_brut()
        nombre = len(res.candidats)
        octets = sum(c.taille for c in res.candidats)
        valeur, unite = (nombre, "fichier(s)") if regle.mode == "count" else (octets, "octet(s)")
        mini, maxi = regle.seuil_minimum, regle.seuil_maximum
        self._log("mesure", "INFO", mode=regle.mode, nombre=nombre, octets=octets, seuil_minimum=mini,
                  seuil_maximum=maxi)
        description = ("%d fichier(s)" % nombre) if regle.mode == "count" else \
            "%s en %d fichier(s)" % (_octets_lisibles(octets), nombre)
        if (mini is not None and valeur < mini) or (maxi is not None and valeur > maxi):
            bornes = " et ".join(t for t in (("au moins %d %s" % (mini, unite)) if mini is not None else None,
                                             ("au plus %d %s" % (maxi, unite)) if maxi is not None else None) if t)
            b.attente = True
            b.motif = "condition non remplie : %s, attendu %s" % (description, bornes)
            self._log("condition_non_remplie", "INFO", message=b.motif)
        else:
            b.motif = description

    def _supprimer_tout(self):
        """Mode suppression : supprime definitivement les fichiers selectionnes (original verifie inchange)."""
        regle, b = self.regle, self.bilan
        res = self._lister_brut()
        a_supprimer = res.candidats
        sel = regle.selection
        if sel.limite_fichiers is not None and len(a_supprimer) > sel.limite_fichiers:
            self._log("limite_atteinte", "INFO", limite=sel.limite_fichiers,
                      restants=len(a_supprimer) - sel.limite_fichiers)
            a_supprimer = a_supprimer[:sel.limite_fichiers]
        for c in a_supprimer:
            champs = {"fichier": c.chemin}
            if self.simulation:
                b.compteurs["livres"] += 1
                b.compteurs["octets"] += c.taille
                self._log("fichier_a_supprimer", "INFO", taille=c.taille, **champs)
                self._noter_apercu(c, None)
                continue
            try:
                resultat = self._executer_action("suppression", c.chemin, c.taille, c.mtime_ns, None, **champs)
            except EchecSituation as e:
                cfg = self._signaler(e.situation, e.message, **champs)
                if cfg.suite == "arreter_regle":
                    raise ArretRegle(e.situation, e.message)
                continue                    # le fichier reste selectionne : retente au prochain lancement
            if resultat == "supprime":
                b.compteurs["livres"] += 1
                b.compteurs["octets"] += c.taille

    # ----- 4 + 6 : selection et anti-doublon -------------------------------- #
    def _selectionner(self):
        regle = self.regle
        interdits = [self.dossier_temporaire] if self.dossier_temporaire else []

        def operation():
            res = selection.lister(self.source, regle.selection, self.maintenant(), self.est_exclu,
                                   interdits, ignorer_horodates=self.horodate)
            self._derniere_selection = res
            if res.erreurs and not res.candidats:
                raise res.erreurs[0][1]
            a_livrer = self._filtrer(res)
            if not a_livrer:
                raise ErreurTransfert("aucun fichier a livrer")
            return a_livrer

        def classifier(e):
            return "aucun_fichier" if isinstance(e, ErreurTransfert) else "source_inaccessible"
        try:
            a_livrer = self._essayer(operation, classifier)
        except EchecSituation as e:
            res = getattr(self, "_derniere_selection", None)
            self._bilan_selection(res)
            if e.situation == "source_inaccessible":
                self._arreter(e)
            self._signaler("aucun_fichier", "aucun fichier a livrer")
            return []
        self._bilan_selection(self._derniere_selection)
        return a_livrer

    def _bilan_selection(self, res):
        if res is None:
            return
        for chemin in res.dates_futures:
            self._log("fichier_date_future", "WARNING", fichier=chemin,
                      message="date de modification dans le futur : fichier ignore (horloges ?)")
            self._noter_niveau("WARNING")
        for chemin, erreur in res.erreurs:
            self._log("lecture_impossible", "WARNING", chemin=chemin, message=str(erreur))
            self._noter_niveau("WARNING")
        self._log("selection", "INFO", candidats=len(res.candidats), vus=res.vus,
                  hors_masque=res.hors_masque, trop_recents=res.trop_recents,
                  trop_anciens=res.trop_anciens, trop_petits=res.trop_petits,
                  dates_futures=len(res.dates_futures), deja_horodates=res.deja_horodates or None)
        self.bilan.compteurs["selectionnes"] = len(res.candidats)

    def _cle_version(self, c):
        return modele_base.cle_version(self.regle.id, c.relatif, c.taille, c.mtime_ns)

    def _cible_deterministe(self):
        modele = self.regle.renommage_cible
        return modele is None or not any("{%s}" % v in modele for v in chemins.variables_date(self.debut))

    def _filtrer(self, res):
        """Anti-doublon : ne garde que les versions jamais livrees."""
        regle = self.regle
        a_livrer, ignores = [], 0
        for c in res.candidats:
            cle = self._cle_version(c)
            etat = self.base.etat_fichier(cle)
            if etat is None:
                a_livrer.append(c)
                continue
            if (etat == modele_base.TERMINE and regle.mode == "copie"
                    and regle.si_cible_absente == "recopier" and self._cible_deterministe()
                    and not os.path.exists(self._destination_theorique(c))):
                if self.mode_ecrit:
                    self.base.oublier_fichier(cle, etats=(modele_base.TERMINE,))
                self._log("cible_absente_recopie", "INFO", fichier=c.chemin)
                a_livrer.append(c)
                continue
            ignores += 1
            if self.mode_ecrit and etat == modele_base.TERMINE:
                self.base.noter_vu(cle)
                if self.horodate and regle.mode == "copie":
                    self._horodater_source(c, {"fichier": c.chemin})   # copie faite, marque restee a poser
            self.journal.evenement("fichier_ignore", "DEBUG", fichier=c.chemin)
        self.bilan.compteurs["ignores"] = ignores
        return a_livrer

    def _nom_cible(self, c):
        if not self.regle.renommage_cible:
            return c.nom
        return chemins.appliquer_modele_nom(self.regle.renommage_cible, c.nom, self.debut)

    def _destination_theorique(self, c):
        return os.path.join(self.cible, os.path.dirname(c.relatif), self._nom_cible(c))

    # ----- 7 + 8 : ordre, limite, espace ---------------------------------- #
    def _livrer_tout(self, a_livrer):
        sel = self.regle.selection
        if sel.limite_fichiers is not None and len(a_livrer) > sel.limite_fichiers:
            self._log("limite_atteinte", "INFO", limite=sel.limite_fichiers, restants=len(a_livrer) - sel.limite_fichiers)
            a_livrer = a_livrer[:sel.limite_fichiers]
        self._controler_espace(a_livrer)
        for c in a_livrer:
            self._livrer(c)

    def _controler_espace(self, a_livrer):
        self.bilan.octets_prevus = sum(c.taille for c in a_livrer)
        besoin = self.bilan.octets_prevus + self.entete.marge_espace_mo * MARGE_OCTETS

        def verifier(dossier):
            libre = chemins.espace_disponible(dossier)
            if libre < besoin:
                raise ErreurCible("espace insuffisant dans %s : %d Mo disponibles pour %d Mo necessaires"
                                  % (dossier, libre // MARGE_OCTETS, besoin // MARGE_OCTETS))
        try:
            self._essayer(lambda: verifier(self.cible), lambda e: "espace_insuffisant_cible")
        except EchecSituation as e:
            self._arreter(e)
        self._log("controle_prealable", "INFO", controle="espace_cible", necessaire_octets=besoin)

        if (self.regle.mode == "archivage" and not self.archive_differee
                and not chemins.meme_volume(self.source, self.archive_dir)):
            try:
                self._essayer(lambda: verifier(self.archive_dir), lambda e: "espace_insuffisant_archive")
            except EchecSituation as e:
                self._archive_indisponible(e)

    # ----- 9 : un fichier -------------------------------------------------- #
    def _temporaire(self, destination):
        if self.dossier_temporaire:
            empreinte = hashlib.blake2b(os.path.normcase(destination).encode("utf-8", "surrogatepass"),
                                        digest_size=8).hexdigest()
            return os.path.join(self.dossier_temporaire, "%s_%s%s" % (
                self.regle.id, empreinte, selection.SUFFIXE_TEMPORAIRE))
        return destination + selection.SUFFIXE_TEMPORAIRE

    def _destination(self, c):
        """(chemin final, ecraser) selon si_existe_cible ; leve CibleExiste ou IgnorerFichier."""
        nom = self._nom_cible(c)
        raison = chemins.nom_invalide(nom)
        if raison:
            raise EchecSituation("copie_echec", "nom de fichier refuse : %s" % raison)
        destination = os.path.join(self.cible, os.path.dirname(c.relatif), nom)
        if not os.path.lexists(destination):
            return destination, False
        politique = self.regle.si_existe_cible
        if politique == "ecraser":
            return destination, True
        if politique == "ignorer":
            raise IgnorerFichier(destination)
        if politique == "suffixe":
            maintenant = self.maintenant()
            for compteur in range(1000):
                candidat = os.path.join(os.path.dirname(destination),
                                        chemins.nom_avec_suffixe(nom, maintenant, compteur))
                if not os.path.lexists(candidat):
                    return candidat, False
            raise ErreurCible("aucun nom libre dans la cible pour %s" % destination)
        raise CibleExiste("un fichier de ce nom attend deja dans la cible : %s" % destination)

    def _livrer(self, c):
        champs = {"fichier": c.chemin}
        self._res = {"resultat": "ignore"}
        try:
            if not self._avant_fichier(c, champs):
                return
            self._livrer_version(c, self._cle_version(c), champs)
        except IgnorerFichier as i:
            self.bilan.compteurs["ignores"] += 1
            self._log("fichier_ignore", "INFO", cible=str(i), message="un fichier de ce nom existe deja dans la cible",
                      **champs)
        except EchecSituation as e:
            if self._res["resultat"] != "livre":
                self._res["resultat"] = "erreur"
            self._res["message"] = e.message
            self._echec_fichier(e, **champs)
        finally:
            self.resultats.append(programmes.entree_fichier(c, **self._res))

    def _avant_fichier(self, c, champs):
        """Programme avant_fichier. Renvoie False si le fichier doit etre ignore. Le programme peut
        modifier la source sur place : taille et date sont relues AVANT de calculer l'empreinte."""
        code = self._programme("avant_fichier", c=c, destination=self._destination_theorique(c), **champs)
        if code is None:
            return True
        if code == 1:
            self.bilan.compteurs["ignores"] += 1
            self._log("fichier_ignore", "INFO", message="le programme avant_fichier demande d'ignorer ce fichier",
                      **champs)
            return False
        avant = self._cle_version(c)
        try:
            st = os.stat(c.chemin)
        except FileNotFoundError:
            self.bilan.compteurs["ignores"] += 1
            self._log("fichier_ignore", "INFO", message="fichier disparu apres avant_fichier", **champs)
            return False
        c.taille, c.mtime_ns = st.st_size, st.st_mtime_ns
        apres = self._cle_version(c)
        if apres != avant:
            self._log("fichier_modifie_par_programme", "INFO", taille=c.taille, **champs)
            if self.base.etat_fichier(apres) is not None:        # cette version a deja ete livree
                self.bilan.compteurs["ignores"] += 1
                return False
        return True

    def _echec_fichier(self, echec, **champs):
        cfg = self._signaler(echec.situation, echec.message, **champs)
        if cfg.niveau_final == "INFO":
            self.bilan.compteurs["ignores"] += 1
        if cfg.suite == "arreter_regle":
            raise ArretRegle(echec.situation, echec.message)

    def _livrer_version(self, c, cle, champs):
        regle = self.regle
        # contenu identique deja livre sous une autre version ?
        sha_contenu = None
        if regle.identite == "contenu":
            cle_contenu, sha_contenu = self._cle_contenu(c, champs)
            if self.base.etat_fichier(cle_contenu) is not None:
                self._doublon_contenu(c, cle, champs)
                return
            cle_principale = cle_contenu
        else:
            cle_principale = cle

        # destination libre ? (avec les tentatives de fichier_existe_cible, avant toute ecriture)
        destination, _ = self._essayer(lambda: self._destination(c), situation_copie, **champs)

        if self.simulation:
            self.bilan.compteurs["livres"] += 1
            self.bilan.compteurs["octets"] += c.taille
            self._log("fichier_a_livrer", "INFO", cible=destination, taille=c.taille, **champs)
            self._noter_apercu(c, destination)
            self._res.update(resultat="a_livrer", cible=destination)
            self._programme("apres_fichier", c=c, destination=destination, **champs)
            return

        destination_archive = self._destination_archive(c) if regle.mode == "archivage" else None
        if not self.base.noter_intention(self.no, cle_principale, c.chemin, destination,
                                         destination_archive, c.taille, c.mtime_ns, sha_contenu):
            self.bilan.compteurs["ignores"] += 1
            return

        debut = time.time()

        def operation():
            dest, ecraser = self._destination(c)
            copie = transfert.copier_verifier(c.chemin, dest, self._temporaire(dest), ecraser,
                                              attendu=(c.taille, c.mtime_ns))
            return copie, dest
        try:
            copie, destination = self._essayer(operation, situation_copie, **champs)
        except (EchecSituation, IgnorerFichier):
            self.base.oublier_fichier(cle_principale)      # on SAIT que rien n'a ete livre
            raise

        suivante = {"deplacement": "suppression", "archivage": "archivage"}.get(regle.mode)
        self.base.confirmer_livraison(cle_principale, termine=suivante is None,
                                      action_suivante=suivante, sha256=copie.sha256)
        if regle.identite == "contenu":
            self.base.ajouter_termine(self.no, cle)
        self.bilan.compteurs["livres"] += 1
        self.bilan.compteurs["octets"] += copie.taille
        self._log("fichier_livre", "INFO", cible=destination, taille=copie.taille,
                  sha256=copie.sha256, duree_ms=int((time.time() - debut) * 1000), **champs)
        self._res.update(resultat="livre", cible=destination, taille=copie.taille)

        try:
            self._programme("apres_fichier", c=c, destination=destination, **champs)
        except EchecSituation:
            # l'original n'est ni supprime ni archive : le fichier est livre, plus aucune action n'est due
            if suivante:
                self.base.terminer_fichier(cle_principale)
            raise

        if suivante:
            self._action_du_mode(c, cle_principale, suivante, destination_archive, champs)
        elif self.horodate and regle.mode == "copie":
            self._horodater_source(c, champs)

    def _horodater_source(self, c, champs):
        """Mode copie + horodater : l'original, qui reste dans la source, prend la marque de l'instant
        du traitement (trace visuelle). Jamais bloquant : un echec est un avertissement, et la marque
        sera reposee a la prochaine execution (le fichier est alors vu comme deja livre)."""
        try:
            if not transfert.verifier_original_inchange(c.chemin, c.taille, c.mtime_ns):
                return                                  # disparu : rien a marquer
        except SourceModifiee as e:
            self._log("horodatage_ignore", "INFO", message="%s ; non marque, sera livre de nouveau" % e, **champs)
            return
        except ErreurSource as e:
            self._horodatage_echoue(str(e), **champs)
            return
        maintenant = self.maintenant()
        dossier = os.path.dirname(c.chemin)
        for compteur in range(1000):
            nouveau = os.path.join(dossier, chemins.nom_horodate(c.nom, maintenant, compteur))
            try:
                transfert.renommer(c.chemin, nouveau, ecraser=False)
            except CibleExiste:
                continue
            except ErreurCible as e:
                self._horodatage_echoue(str(e), **champs)
                return
            self._log("fichier_horodate", "INFO", fichier_horodate=nouveau, **champs)
            return
        self._horodatage_echoue("aucun nom libre pour marquer %s" % c.chemin, **champs)

    def _horodatage_echoue(self, message, **champs):
        self._log("horodatage_echec", "WARNING", message=message + " ; nouvel essai au prochain lancement", **champs)
        self._noter_niveau("WARNING")

    def _noter_apercu(self, c, destination):
        """Simulation : garde de quoi dire « deplacera X fichier(s) de R vers D » (plafonne a APERCU_MAX)."""
        self.bilan.apercu_total += 1
        if len(self.bilan.apercu) >= APERCU_MAX:
            return
        element = {"fichier": c.chemin, "cible": destination, "taille": c.taille}
        if self.regle.mode == "archivage" and self.archive_dir and not self.archive_differee:
            element["archive"] = self._destination_archive(c)
        self.bilan.apercu.append(element)

    def _destination_archive(self, c):
        nom = c.nom
        if self.regle.renommage_archive:
            nom = chemins.appliquer_modele_nom(self.regle.renommage_archive, c.nom, self.debut)
        if self.horodate:
            nom = chemins.nom_horodate(nom, self.maintenant())     # l'heure de l'archivage de ce fichier
        return os.path.join(self.archive_dir, os.path.dirname(c.relatif), nom)

    def _action_du_mode(self, c, cle, type_, destination_archive, champs):
        if type_ == "archivage" and self.archive_differee:
            self.bilan.compteurs["en_attente"] += 1
            self._log("action_differee", "WARNING", type="archivage", archive=destination_archive,
                      message="archive indisponible : archivage retente aux prochains lancements", **champs)
            self._noter_niveau("WARNING")
            return
        try:
            self._executer_action(type_, c.chemin, c.taille, c.mtime_ns, destination_archive, **champs)
            self.base.terminer_fichier(cle)
        except EchecSituation as e:
            self._apres_echec_action(e, cle, type_, **champs)

    # ----- identite = contenu ---------------------------------------------- #
    def _cle_contenu(self, c, champs):
        def operation():
            try:
                return transfert.sha256_fichier(c.chemin)
            except FileNotFoundError as e:
                raise SourceDisparue("fichier disparu : %s" % c.chemin, e)
            except OSError as e:
                raise ErreurSource("lecture impossible : %s" % e, e)
        sha = self._essayer(operation, situation_copie, **champs)
        return modele_base.cle_contenu(self.regle.id, c.relatif, sha), sha

    def _doublon_contenu(self, c, cle, champs):
        regle = self.regle
        self._log("doublon_contenu", self.regle.situations["doublon_contenu"].niveau_final,
                  message="ce contenu a deja ete livre", **champs)
        self.bilan.compteurs["ignores"] += 1
        if self.mode_ecrit:
            self.base.ajouter_termine(self.no, cle)
        if regle.mode in ("deplacement", "archivage") and self.mode_ecrit:
            type_ = "suppression" if regle.mode == "deplacement" else "archivage"
            if type_ == "archivage" and self.archive_differee:
                return
            try:
                self._executer_action(type_, c.chemin, c.taille, c.mtime_ns,
                                      self._destination_archive(c) if type_ == "archivage" else None,
                                      **champs)
            except EchecSituation as e:
                self._log("action_reportee", "WARNING", message=str(e), **champs)
                self._noter_niveau("WARNING")

    # ----- 11 : bilan ------------------------------------------------------ #
    def _conclure(self):
        b = self.bilan
        b.statut = STATUTS[self.rang]
        if b.erreur is not None:
            b.statut = "ERREUR"
        b.compteurs["en_attente"] = max(b.compteurs["en_attente"], len(self.base.actions(self.no)))
        if b.motif is None:
            c = b.compteurs
            if b.statut == "SUCCES" and self.regle.mode == "suppression":
                b.motif = "%d fichier(s) supprime(s)" % c["livres"] if c["livres"] else "rien a supprimer"
            elif b.statut == "SUCCES":
                b.motif = "%d fichier(s) livre(s)" % c["livres"] if c["livres"] else "rien a livrer"
            elif b.erreur:
                b.motif = b.erreur["message"]
            else:
                b.motif = "termine avec des avertissements"
        b.arret_apres_erreur = b.statut == "ERREUR" and self.regle.apres_erreur == "arreter"
        return b


# --------------------------------------------------------------------------- #
# Lancement complet d'une regle : flag, journal, execution en base
# --------------------------------------------------------------------------- #
class RegleDejaEnCours(Exception):
    pass


def nom_hote():
    return os.environ.get("COMPUTERNAME") or socket.gethostname()


def lancer_regle(regle, entete, base, journal, declencheur="manuel", simulation=False,
                 maintenant=None, dormir=time.sleep, build=None, creneau=None, execution_existante=None,
                 journaliser_fin=True, simulation_programmes=False):
    """Prend le flag de la regle, l'execute, libere le flag. Renvoie le Bilan.
    `declencheur` : planifie | reprise | manuel | dependance ; `creneau` : creneau pris par cette
    execution (secondes). En simulation : aucune ecriture en base (ouverte en lecture seule),
    pas de flag. `execution_existante` : l'orchestrateur a deja pris le drapeau et cree l'execution
    (on ne fait que l'executer) ; `journaliser_fin` : faux pour un fils, dont l'orchestrateur
    journalise la fin."""
    no = base.numero_regle(regle.id)
    if no is None and simulation:
        no = -1                       # regle jamais vue en base : aucune ligne ne correspond
    elif no is None:
        raise modele_base.ErreurBase("regle inconnue de la base : %s (synchroniser d'abord)" % regle.id)
    execution_id = execution_existante
    if not simulation and execution_id is None:
        execution_id = base.demarrer_execution(no, declencheur, os.getpid(),
                                               pid_cree_le=processus.date_creation(os.getpid()),
                                               hote=nom_hote(), build=build, creneau=creneau)
        if execution_id is None:
            raise RegleDejaEnCours(regle.id)
    journal.definir(regle=regle.id, execution_id=execution_id)
    if declencheur == "reprise":
        journal.evenement("reprise_demarree", "INFO", message="execution lancee par une reprise")
    journal.evenement("regle_demarree", "INFO", declencheur=declencheur,
                      **({"simulation": True} if simulation else {}))
    debut = time.time()
    execution = ExecutionRegle(regle, entete, base, no, journal, simulation, maintenant, dormir,
                               declencheur=declencheur, simulation_programmes=simulation_programmes,
                               execution_id=execution_id)
    try:
        bilan = execution.executer()
    except Exception as e:                          # defaut du programme : jamais de flag orphelin
        bilan = execution.bilan
        bilan.statut = "ERREUR"
        bilan.situation_finale = "erreur_interne"
        bilan.erreur = {"situation": "erreur_interne", "message": "%s: %s" % (type(e).__name__, e)}
        bilan.motif = bilan.erreur["message"]
        bilan.arret_apres_erreur = True
        journal.evenement("erreur_interne", "ERREUR", message=bilan.motif)
    except BaseException:
        if not simulation:
            base.liberer_flag(no, "interrompue")
        raise
    statut_final = "ATTENTE" if bilan.attente else bilan.statut
    bilan.statut_final = statut_final
    if not simulation:
        base.terminer_execution(execution_id, no, statut_final, motif=bilan.motif,
                                compteurs=bilan.compteurs, situation_finale=bilan.situation_finale,
                                message=bilan.motif, erreur=bilan.erreur,
                                arret_apres_erreur=bilan.arret_apres_erreur)
    bilan.duree_ms = int((time.time() - debut) * 1000)
    if journaliser_fin:
        journal.evenement("regle_terminee", NIVEAU_STATUT[bilan.statut],
                          statut=statut_final, motif=bilan.motif, compteurs=bilan.compteurs,
                          duree_ms=bilan.duree_ms,
                          **({"situation": bilan.situation_finale} if bilan.situation_finale else {}),
                          **({"simulation": True} if simulation else {}))
    journal.definir(regle=None, execution_id=None)
    return bilan
