"""Lancement d'un environnement (version sequentielle du jalon J5) et etat des regles.

Un lancement : synchronise les regles avec la base, libere les executions orphelines, determine
les regles dues (planification, reprise, lancement manuel) et les execute UNE PAR UNE dans ce
processus. Le parallelisme (un processus par regle), les dependances entre regles et l'arret
des executions trop longues viennent au jalon J6.

Specification : docs/02-moteur.md sections 2, 4 et 10 ; etat : docs/03-base-de-donnees.md section 6.
"""
import datetime
import hashlib
import os
import time

from file_management import base as modele_base
from file_management import planification, processus
from file_management.execution import lancer_regle, nom_hote, notifier_erreur, trier_apres_arret
from file_management.orchestrateur import Orchestrateur


def empreinte_regle(regle):
    """Empreinte du texte de la regle : detecte une regle modifiee depuis le dernier lancement."""
    return hashlib.blake2b(regle.brut.encode("utf-8"), digest_size=16).hexdigest()


class Lancement(object):
    def __init__(self):
        self.compteurs = {"regles": 0, "lancees": 0, "SUCCES": 0, "WARNING": 0, "ERREUR": 0,
                          "non_dues": 0, "non_lancees": 0, "orphelines": 0, "nettoyees": 0,
                          "en_attente": 0, "bloquees": 0, "depassees": 0}
        self.niveau = 0                    # 0 INFO, 1 WARNING, 2 ERREUR : pire evenement du lancement
        self.interrompu = None             # message si le lancement a du s'arreter (base indisponible)
        self.suspendu = False              # environnement suspendu : aucune regle lancee

    def noter(self, niveau):
        self.niveau = max(self.niveau, {"INFO": 0, "WARNING": 1, "ERREUR": 2}[niveau])

    @property
    def code_retour(self):
        if self.interrompu:
            return 2
        return {0: 0, 1: 4, 2: 1}[self.niveau]


def _regles_a_traiter(parametrage, filtre):
    filtre = {f.lower() for f in filtre} if filtre else None
    return [r for r in parametrage.regles if r.id and (filtre is None or r.id.lower() in filtre)]


def synchroniser(parametrage, base, journal, lancement):
    """Ajoute les regles nouvelles en base ; signale celles que la base connait et que le fichier
    ne contient plus (docs/02, section 2, etape 2)."""
    numeros, modifiees = base.synchroniser_regles(
        [(r.id, empreinte_regle(r)) for r in parametrage.regles if r.id])
    for ident in modifiees:
        journal.evenement("regle_modifiee", "INFO", regle=ident,
                          message="les parametres de la regle ont change depuis le dernier lancement")
    connues = set(numeros)
    for ligne in base.toutes_les_regles():
        if ligne["id"].lower() not in connues:
            lancement.compteurs["orphelines"] += 1
            lancement.noter("WARNING")
            journal.evenement("regle_orpheline", "WARNING", regle=ligne["id"],
                              message="regle connue de la base mais absente du parametrage")
    return numeros


def _traiter_trop_long(ligne, regle, base, journal, lancement, maintenant, entete=None):
    """Une execution d'un AUTRE lancement, vivante mais au-dela de `duree_max_sec` : on applique
    `si_duree_depassee` (on ne tient pas son Job Object : arret de l'arbre par taskkill /T)."""
    if regle is None or not ligne["debut_traitement"] or ligne["debut_traitement"] + regle.duree_max_sec >= maintenant:
        return
    message = "duree maximale depassee (%d s) pour l'execution %s" % (regle.duree_max_sec, ligne["execution_id"])
    if regle.si_duree_depassee == "alerter":
        lancement.noter("WARNING")
        lancement.compteurs["depassees"] += 1
        journal.evenement("duree_depassee", "WARNING", regle=ligne["id"], message=message + " : l'execution continue",
                          action="alerter")
        return
    processus.tuer_arbre(ligne["pid"])
    lancement.compteurs["depassees"] += 1
    relance = regle.si_duree_depassee == "relancer" and (ligne["relances"] or 0) < regle.relances_max
    if not relance and entete is not None:
        trier_apres_arret(regle, entete, base, ligne["no"], journal, ligne["execution_id"])
    if regle.si_duree_depassee == "relancer" and (ligne["relances"] or 0) < regle.relances_max:
        base.liberer_flag(ligne["no"], message + " : relance", statut_regle="ARRETEE")
        base.incrementer_relances(ligne["no"])
        base.poser_lancement_manuel(ligne["id"], "orchestrateur", "relance apres depassement de duree")
        lancement.noter("WARNING")
        journal.evenement("duree_depassee", "WARNING", regle=ligne["id"], message=message + " : arret puis relance",
                          action="relancer")
        return
    liberee = base.liberer_flag(ligne["no"], message, statut_regle="ERREUR",
                                arret_apres_erreur=regle.apres_erreur == "arreter",
                                erreur={"situation": "duree_depassee", "message": message})
    lancement.noter("ERREUR")
    journal.evenement("duree_depassee", "ERREUR", regle=ligne["id"], message=message + " : arbre de processus arrete",
                      action="erreur")
    if entete is not None and liberee:
        notifier_erreur(regle, entete, base, ligne["no"], journal, ligne["execution_id"], "duree_depassee", message)


def nettoyer_orphelins(parametrage, base, journal, lancement, hote=None, maintenant=time.time):
    """Libere les regles dont le processus a disparu (meme serveur) : execution en ERREUR,
    situation `arret_anormal` (docs/02, section 2, etape 3)."""
    hote = hote or nom_hote()
    regles = {r.id.lower(): r for r in parametrage.regles if r.id}
    for ligne in base.toutes_les_regles():
        if not ligne["en_cours"] or (ligne["hote"] and ligne["hote"] != hote):
            continue
        regle = regles.get(ligne["id"].lower())
        if processus.vivant(ligne["pid"], ligne["pid_cree_le"]):
            _traiter_trop_long(ligne, regle, base, journal, lancement, maintenant(), parametrage.entete)
            continue
        arret = regle is None or regle.apres_erreur == "arreter"
        message = "processus %s disparu pendant l'execution %s" % (ligne["pid"], ligne["execution_id"])
        if base.liberer_flag(ligne["no"], message, statut_regle="ERREUR", arret_apres_erreur=arret,
                             erreur={"situation": "arret_anormal", "message": message}):
            lancement.compteurs["nettoyees"] += 1
            lancement.noter("ERREUR")
            journal.evenement("arret_anormal", "ERREUR", regle=ligne["id"], message=message)
            notifier_erreur(regle, parametrage.entete, base, ligne["no"], journal, ligne["execution_id"],
                            "arret_anormal", message)


def purger_base(parametrage, base, journal, lancement):
    """Purge de la base (fichiers termines, executions anciennes), une fois par jour. Un echec n'arrete
    pas le lancement : simple avertissement."""
    retentions = {}
    for r in parametrage.regles:
        no = base.numero_regle(r.id) if r.id else None
        if no is not None:
            retentions[no] = r.retention_historique_jours
    try:
        bilan = base.purger(retentions, parametrage.entete.retention_executions_jours)
    except modele_base.ErreurBase as e:
        lancement.noter("WARNING")
        journal.evenement("purge_base_echec", "WARNING", message=str(e))
        return
    if bilan is not None:
        journal.evenement("purge_base", "INFO", **bilan)


def lancer(parametrage, base, journal, filtre=None, simulation=False, maintenant=None,
           fuseau=planification.FUSEAU, build=None, dormir=time.sleep, maintenant_dt=None,
           direct=False, pas_sec=0.2, rappel=None, simulation_programmes=False):
    """Lancement d'un environnement : renvoie un objet Lancement (compteurs et code retour).
    Chaque regle due est executee dans un processus fils, en parallele, apres evaluation de ses
    dependances. `direct` : sans processus fils (tests avec horloge simulee).
    Simulation : planification ignoree, aucune ecriture, toutes les regles actives sont simulees
    l'une apres l'autre dans ce processus."""
    maintenant = maintenant or time.time
    if maintenant_dt is None:
        def maintenant_dt():
            return datetime.datetime.fromtimestamp(maintenant())
    lancement = Lancement()
    entete = parametrage.entete
    if entete.suspendu and not simulation:
        # Maintenance : rien n'est lance (ni lancement planifie, ni lancement manuel, ni reprise). Les
        # executions deja en cours ne sont pas touchees. Niveau INFO : le code retour reste 0, Jenkins ne
        # passe pas au rouge ; l'alerte « suspendu depuis trop longtemps » se regle dans la plateforme.
        lancement.suspendu = True
        journal.evenement("environnement_suspendu", "INFO", motif=entete.motif_suspension)
        return lancement
    try:
        if not simulation:
            synchroniser(parametrage, base, journal, lancement)
            purger_base(parametrage, base, journal, lancement)
            nettoyer_orphelins(parametrage, base, journal, lancement, maintenant=maintenant)
            Orchestrateur(parametrage, base, journal, lancement, filtre=filtre, maintenant=maintenant,
                          fuseau=fuseau, build=build, direct=direct, maintenant_dt=maintenant_dt,
                          dormir=dormir, pas_sec=pas_sec, rappel=rappel).executer()
        else:
            for regle in _regles_a_traiter(parametrage, filtre):
                lancement.compteurs["regles"] += 1
                _traiter(regle, entete, base, journal, lancement, maintenant_dt, simulation_programmes)
    except modele_base.ErreurBase as e:
        lancement.interrompu = str(e)
        lancement.noter("ERREUR")
        journal.evenement("base_indisponible", "ERREUR", message=str(e))
    return lancement


def _traiter(regle, entete, base, journal, lancement, maintenant_dt, simulation_programmes=False):
    """Simulation d'une regle (planification ignoree, aucune ecriture)."""
    if not regle.actif:
        lancement.compteurs["non_dues"] += 1
        return
    bilan = lancer_regle(regle, entete, base, journal, declencheur="simulation", simulation=True,
                         maintenant=maintenant_dt, simulation_programmes=simulation_programmes)
    lancement.compteurs["lancees"] += 1
    lancement.compteurs[bilan.statut] += 1
    lancement.noter({"SUCCES": "INFO", "WARNING": "WARNING", "ERREUR": "ERREUR"}[bilan.statut])


# --------------------------------------------------------------------------- #
# Deblocage (--debloquer)
# --------------------------------------------------------------------------- #
def debloquer(parametrage, base, journal, ident, utilisateur, commentaire=None, hote=None, attente_sec=10):
    """--debloquer : arrete l'execution en cours de la regle (processus ET descendants) et libere
    son drapeau. La regle passe en ERREUR (situation `deblocage`) ; avec `apres_erreur = arreter` une
    reprise est ensuite necessaire. Ne vise jamais un processus qui n'est plus celui de l'execution
    (identifiant reutilise) ni ce processus-ci. Renvoie un dict decrivant ce qui a ete fait."""
    hote = hote or nom_hote()
    no = base.numero_regle(ident)
    ligne = base.regle(no) if no is not None else None
    if ligne is None:
        raise modele_base.ActionRefusee("regle inconnue de la base : %s" % ident)
    if not ligne["en_cours"]:
        raise modele_base.ActionRefusee("la regle %s n'est pas en cours d'execution" % ident)
    if ligne["hote"] and ligne["hote"] != hote:
        raise modele_base.ActionRefusee(
            "l'execution de %s tourne sur %s : lancer le deblocage depuis ce serveur" % (ident, ligne["hote"]))
    pid, vivant = ligne["pid"], processus.vivant(ligne["pid"], ligne["pid_cree_le"])
    if vivant and pid == os.getpid():
        raise modele_base.ActionRefusee("l'execution de %s est portee par le processus courant" % ident)
    arrete = False
    if vivant:
        processus.tuer_arbre(pid)
        fin = time.monotonic() + attente_sec
        while processus.vivant(pid, ligne["pid_cree_le"]) and time.monotonic() < fin:
            time.sleep(0.1)
        if processus.vivant(pid, ligne["pid_cree_le"]):
            raise modele_base.ActionRefusee("le processus %s de la regle %s ne s'arrete pas" % (pid, ident))
        arrete = True
    regle = next((r for r in parametrage.regles if r.id and r.id.lower() == ident.lower()), None)
    arret = regle is None or regle.apres_erreur == "arreter"
    # la copie interrompue laisse des intentions de livraison : on les examine tout de suite (avant de liberer
    # le drapeau), l'incertitude est ainsi visible et tranchable sans attendre la reprise
    incertaines = trier_apres_arret(regle, parametrage.entete, base, no, journal, ligne["execution_id"])
    message = "execution %s debloquee par %s" % (ligne["execution_id"], utilisateur)
    if commentaire:
        message += " : " + commentaire
    liberee = base.liberer_flag(no, message, statut_regle="ERREUR", arret_apres_erreur=arret,
                                erreur={"situation": "deblocage", "message": message})
    base.journaliser_action(no, "deblocage", utilisateur, commentaire,
                            "processus arrete" if arrete else "processus deja absent")
    journal.evenement("deblocage", "INFO", regle=ligne["id"], execution_id=ligne["execution_id"],
                      utilisateur=utilisateur, commentaire=commentaire, processus_arrete=arrete, pid=pid)
    texte = "%s debloquee : %s" % (ligne["id"], "processus %s et ses descendants arretes" % pid if arrete
                                  else "le processus n'existait plus")
    if incertaines:
        texte += (" ; %d livraison(s) de resultat inconnu : verifier la cible puis les trancher "
                  "(livree ou a relivrer) avant la reprise" % incertaines)
    if arret:
        texte += " ; une reprise est necessaire pour la relancer"
    if liberee:                         # sinon l'orchestrateur a constate la fin avant nous et a deja notifie
        notifier_erreur(regle, parametrage.entete, base, no, journal, ligne["execution_id"], "deblocage", message)
    return {"regle": ligne["id"], "execution_id": ligne["execution_id"], "pid": pid,
            "processus_arrete": arrete, "drapeau_libere": liberee, "reprise_necessaire": arret,
            "livraisons_incertaines": incertaines, "message": texte}


# --------------------------------------------------------------------------- #
# Etat des regles (--etat)
# --------------------------------------------------------------------------- #
def _entier(instant):
    return None if instant is None else int(instant)


def etat(parametrage, base, maintenant=None, fuseau=planification.FUSEAU, filtre=None):
    """Etat de chaque regle du parametrage, lu dans la base (aucune ecriture). Instants en
    secondes depuis 1970 (UTC)."""
    maintenant = int((maintenant or time.time)())
    lignes = {l["id"].lower(): l for l in base.toutes_les_regles()}
    resultat = {"environnement": parametrage.entete.environnement, "genere_le": maintenant, "regles": [],
                "orphelines": [], "suspendu": bool(parametrage.entete.suspendu),
                "motif_suspension": parametrage.entete.motif_suspension}
    connues = set()
    for regle in _regles_a_traiter(parametrage, filtre):
        connues.add(regle.id.lower())
        ligne = lignes.get(regle.id.lower())
        entree = {"id": regle.id, "description": regle.description, "actif": regle.actif,
                  "mode": regle.mode, "planification": planification.libelle(regle.planification),
                  "en_cours": False, "statut": "JAMAIS_LANCEE", "attente": None, "motif": None,
                  "dernier_lancement": None, "dernier_creneau": None,
                  "prochain_creneau": _entier(planification.prochain_creneau(regle.planification, maintenant, fuseau)),
                  "dernier_succes": None, "derniere_erreur": None, "derniere_execution": None,
                  "reprise": False, "lancement_manuel": False, "arret_apres_erreur": False,
                  "archivage_degrade": False, "actions_en_attente": 0, "livraisons_incertaines": 0,
                  "incertains": []}
        if ligne is not None:
            no = ligne["no"]
            derniere = base.derniere_execution(no)
            entree.update({
                "en_cours": bool(ligne["en_cours"]), "statut": ligne["dernier_statut"],
                "attente": ligne["attente"], "motif": ligne["attente_motif"] or ligne["dernier_motif"],
                "dernier_lancement": ligne["dernier_lancement"], "dernier_creneau": ligne["dernier_creneau"],
                "dernier_succes": ligne["dernier_succes"],
                "reprise": bool(ligne["reprise"]), "lancement_manuel": bool(ligne["lancement_manuel"]),
                "arret_apres_erreur": bool(ligne["arret_apres_erreur"]),
                "archivage_degrade": bool(ligne["archivage_degrade"]),
                "actions_en_attente": base.nb_actions(no), "livraisons_incertaines": base.nb_incertains(no),
                "incertains": [{"cle": c.hex(), "source": src, "cible": cib}
                               for c, src, cib in base.incertains(no)]})
            if ligne["derniere_erreur_le"]:
                entree["derniere_erreur"] = {"le": ligne["derniere_erreur_le"],
                                             "situation": ligne["derniere_erreur_situation"],
                                             "message": ligne["derniere_erreur_message"]}
            if derniere:
                fin = derniere["fin"]
                entree["derniere_execution"] = {
                    "statut": derniere["statut"], "nb_livres": derniere["nb_livres"],
                    "nb_erreurs": derniere["nb_erreurs"], "declencheur": derniere["declencheur"],
                    "duree_sec": (fin - derniere["debut"]) if fin else None}
        if not regle.actif:
            entree["statut"] = "INACTIVE"
        elif entree["en_cours"]:
            entree["statut"] = "EN_COURS"
        elif entree["attente"]:
            entree["statut"] = entree["attente"]
        resultat["regles"].append(entree)
    if not filtre:
        resultat["orphelines"] = [l["id"] for l in lignes.values() if l["id"].lower() not in connues]
    return resultat


def _heure(instant):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(instant)) if instant else "-"


def etat_texte(resultat):
    lignes = ["Environnement %s - %s" % (resultat["environnement"], _heure(resultat["genere_le"]))]
    if resultat.get("suspendu"):
        lignes.append("*** ENVIRONNEMENT SUSPENDU : aucune regle n'est lancee%s ***"
                      % ((" (" + resultat["motif_suspension"] + ")") if resultat.get("motif_suspension") else ""))
    for r in resultat["regles"]:
        lignes.append("%-24s %-12s %s" % (r["id"], r["statut"], r["planification"]))
        lignes.append("    dernier lancement %s | prochain creneau %s | dernier succes %s" % (
            _heure(r["dernier_lancement"]), _heure(r["prochain_creneau"]), _heure(r["dernier_succes"])))
        if r["motif"]:
            lignes.append("    motif : %s" % r["motif"])
        if r["derniere_erreur"]:
            e = r["derniere_erreur"]
            lignes.append("    derniere erreur %s : %s - %s" % (_heure(e["le"]), e["situation"], e["message"]))
        drapeaux = [nom for nom, actif in (("reprise demandee", r["reprise"]),
                                           ("lancement manuel demande", r["lancement_manuel"]),
                                           ("arretee apres erreur", r["arret_apres_erreur"]),
                                           ("archivage degrade", r["archivage_degrade"])) if actif]
        if r["actions_en_attente"]:
            drapeaux.append("%d action(s) en attente" % r["actions_en_attente"])
        if r["livraisons_incertaines"]:
            drapeaux.append("%d livraison(s) INCERTAINE(S)" % r["livraisons_incertaines"])
        if drapeaux:
            lignes.append("    " + ", ".join(drapeaux))
    for ident in resultat["orphelines"]:
        lignes.append("regle orpheline (en base, absente du parametrage) : %s" % ident)
    return "\n".join(lignes)
