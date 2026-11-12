"""Catalogue des evenements du journal : traduction du vocabulaire interne du moteur vers le format de la
plateforme d'observabilite (message lisible, error.type, niveau CRITICAL, objet).

Le moteur emet des evenements avec leurs noms et leurs niveaux internes (ERREUR, situations...). Le
journal (journal_si.Journal) appelle `decrire(nom, niveau, champs)` a chaque ecriture et complete la ligne.
Une valeur passee explicitement par l'appelant (message=..., error_type=...) l'emporte toujours.
Reference des types d'erreur : docs de la plateforme (liste des erreurs) ; voir docs/02-moteur.md, section 11.
"""
import re

# --------------------------------------------------------------------------- #
# Messages : "{champ}" est remplace par la valeur du champ de l'evenement (nom de fichier pour `fichier`).
# --------------------------------------------------------------------------- #
MESSAGES = {
    "debut_lancement": "Lancement demarre",
    "fin_lancement": "Lancement termine : {statut}",
    "processus_regle_demarre": "Processus de la regle demarre",
    "regle_modifiee": "Regle modifiee dans le parametrage",
    "regle_nouvelle": "Regle nouvelle enregistree",
    "regle_orpheline": "Regle presente en base mais absente du parametrage",
    "regle_non_due": "Regle non due : {motif}",
    "regle_non_lancee": "Regle non lancee : {motif}",
    "regle_demarree": "Regle demarree ({declencheur})",
    "regle_terminee": "Regle terminee : {statut}",
    "regle_anomalie": "Anomalie de la regle : {situation}",
    "reprise_demarree": "Execution lancee par une reprise",
    "reprise_demandee": "Reprise demandee",
    "lancement_manuel_demande": "Lancement manuel demande",
    "acquittement": "Erreur acquittee",
    "deblocage": "Regle debloquee",
    "incertain_tranche": "Livraison incertaine tranchee : {decision}",
    "duree_depassee": "Duree maximale depassee",
    "arret_anormal": "Arret anormal de la regle",
    "erreur_interne": "Erreur interne du moteur",
    "base_indisponible": "Base de suivi indisponible",
    "purge_base": "Purge de la base terminee",
    "purge_base_echec": "Purge de la base en echec",
    "purge_supprime": "Element purge : {type}",
    "purge_echec": "Purge impossible : {type}",
    "dossier_cree": "Dossier cree : {role}",
    "dossier_creation_impossible": "Creation du dossier impossible : {role}",
    "controle_prealable": "Controle prealable : {controle}",
    "selection": "Selection des fichiers terminee",
    "mesure": "Mesure terminee",
    "condition_non_remplie": "Condition non remplie",
    "limite_atteinte": "Limite de fichiers atteinte",
    "limite_octets_atteinte": "Limite de volume atteinte : lot tronque",
    "limite_octets_depassee": "Fichier plus gros que la limite de volume : pris seul",
    "declencheur_absent": "Fichier declencheur absent : en attente",
    "declencheur_present": "Fichier declencheur present",
    "declencheur_consomme": "Fichier declencheur supprime apres le lot",
    "declencheur_non_supprime": "Fichier declencheur non supprime",
    "temoin_cible_retire": "Temoin de la cible retire avant la livraison",
    "temoin_cible_non_retire": "Temoin de la cible non retire",
    "temoin_cible_depose": "Temoin depose dans la cible",
    "environnement_suspendu": "Environnement suspendu : aucune regle lancee",
    "tentative_echouee": "Tentative echouee : {situation}",
    "programme_appele": "Programme appele : {point}",
    "programme_non_appele": "Programme non appele : {point}",
    "avant_lot_rien_a_faire": "Le programme avant_lot demande de ne rien livrer",
    "livraison_reprise": "Livraison reprise apres interruption : {fichier}",
    "livraison_a_refaire": "Livraison a refaire : {fichier}",
    "livraison_incertaine": "Livraison incertaine : {fichier}",
    "archivage_degrade": "Archivage degrade",
    "archivage_retabli": "Archivage retabli",
    "action_a_rejouer": "Action en attente rejouee : {type}",
    "action_differee": "Action differee : {type}",
    "action_reportee": "Action reportee",
    "cible_absente_recopie": "Fichier absent de la cible, recopie : {fichier}",
    "fichier_a_livrer": "Fichier a livrer : {fichier}",
    "fichier_livre": "Fichier livre : {fichier}",
    "fichier_a_supprimer": "Fichier a supprimer : {fichier}",
    "fichier_supprime": "Fichier supprime : {fichier}",
    "fichier_archive": "Fichier archive : {fichier}",
    "fichier_horodate": "Fichier horodate : {fichier}",
    "fichier_ignore": "Fichier ignore : {fichier}",
    "fichier_modifie_par_programme": "Fichier modifie par un programme : {fichier}",
    "fichier_date_future": "Fichier date dans le futur : {fichier}",
    "fichier_erreur": "Erreur sur le fichier {fichier} : {situation}",
    "horodatage_ignore": "Horodatage ignore : {fichier}",
    "horodatage_echec": "Horodatage en echec : {fichier}",
    "lecture_impossible": "Lecture impossible : {chemin}",
    "doublon_contenu": "Doublon de contenu : {fichier}",
}

# --------------------------------------------------------------------------- #
# Types d'erreur de la plateforme.
# --------------------------------------------------------------------------- #
TYPES_SITUATION = {
    "source_inaccessible": "FILE_IO_ERROR",
    "cible_inaccessible": "FILE_IO_ERROR",
    "archive_inaccessible": "FILE_IO_ERROR",
    "espace_insuffisant_cible": "RESOURCE_EXHAUSTED",
    "espace_insuffisant_archive": "RESOURCE_EXHAUSTED",
    "fichier_verrouille": "FILE_IO_ERROR",
    "fichier_instable": "FILE_IO_ERROR",
    "fichier_disparu": "FILE_NOT_FOUND",
    "aucun_fichier": "FILE_NOT_FOUND",
    "copie_echec": "FILE_IO_ERROR",
    "verification_echec": "FILE_IO_ERROR",
    "fichier_existe_cible": "DUPLICATE_ENTITY",
    "fichier_existe_archive": "DUPLICATE_ENTITY",
    "doublon_contenu": "DUPLICATE_ENTITY",
    "source_modifiee": "FILE_IO_ERROR",
    "suppression_echec": "FILE_IO_ERROR",
    "archivage_echec": "FILE_IO_ERROR",
    "programme_avant_lot": "EXTERNAL_SERVICE_ERROR",
    "programme_avant_fichier": "EXTERNAL_SERVICE_ERROR",
    "programme_apres_fichier": "EXTERNAL_SERVICE_ERROR",
    "programme_apres_lot": "EXTERNAL_SERVICE_ERROR",
    "programme_reprise": "EXTERNAL_SERVICE_ERROR",
    "duree_depassee": "TIMEOUT",
    "arret_anormal": "INTERNAL_ERROR",
    "erreur_interne": "INTERNAL_ERROR",
}

TYPES_EVENEMENT = {
    "duree_depassee": "TIMEOUT",
    "arret_anormal": "INTERNAL_ERROR",
    "erreur_interne": "INTERNAL_ERROR",
    "base_indisponible": "DB_CONNECTION_ERROR",
    "livraison_incertaine": "FILE_IO_ERROR",
    "dossier_creation_impossible": "FILE_IO_ERROR",
    "regle_non_lancee": "BUSINESS_RULE_VIOLATION",
}

# Evenements qui passent de ERROR a CRITICAL : le service ne peut plus fonctionner ou l'etat des donnees
# est incertain (a traiter par une personne sans attendre).
EVENEMENTS_CRITIQUES = ("base_indisponible", "livraison_incertaine", "erreur_interne")
SITUATIONS_CRITIQUES = ("espace_insuffisant_cible",)        # disque plein sur la cible

_RE_EXCEPTION = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Exit|Interrupt))\s*:")


class _Champs(dict):
    def __missing__(self, cle):
        return ""


def _nom_fichier(chemin):
    return re.split(r"[\\/]", str(chemin).rstrip("\\/"))[-1]


def _message(nom, champs):
    modele = MESSAGES.get(nom)
    if modele is None:
        return nom.replace("_", " ")
    valeurs = _Champs((k, v) for k, v in champs.items() if v is not None and not isinstance(v, (dict, list)))
    if "fichier" in valeurs:
        valeurs["fichier"] = _nom_fichier(valeurs["fichier"])
    try:
        texte = modele.format_map(valeurs)
    except (ValueError, IndexError):
        return nom.replace("_", " ")
    # champ absent : on retire les separateurs devenus orphelins ("Regle terminee : " -> "Regle terminee")
    return re.sub(r"\s*\(\s*\)", "", re.sub(r"\s*:\s*$", "", texte)).strip()


def decrire(nom, niveau, champs):
    """Complement d'une ligne de journal : {message, niveau, error_type, exception} (cles absentes = defaut)."""
    complement = {"message": _message(nom, champs)}
    if niveau not in ("ERROR", "CRITICAL"):
        return complement
    situation = champs.get("situation")
    if nom in EVENEMENTS_CRITIQUES or situation in SITUATIONS_CRITIQUES:
        complement["niveau"] = "CRITICAL"
    complement["error_type"] = (TYPES_EVENEMENT.get(nom) or TYPES_SITUATION.get(situation)
                                or "UNKNOWN_ERROR")
    if nom == "erreur_interne":
        m = _RE_EXCEPTION.match(str(champs.get("message") or ""))
        if m:
            complement["exception"] = m.group(1)
    return complement
