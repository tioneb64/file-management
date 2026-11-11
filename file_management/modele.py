"""Modele d'une regle pour le front-end (docs/07, commande --modele-regle).

Le front-end propose, a la creation d'une regle, les valeurs de secours du moteur et les listes de
valeurs permises. Il ne les recopie pas : il les demande au moteur, seule source de verite. Rien ici
ne lit de fichier ni de base.
"""
from file_management import parametrage as p
from file_management.parametrage import Regle


def _situations():
    return {nom: {"tentatives": v[0], "delai_sec": v[1], "niveau_final": v[2],
                  "suites": list(v[3]), "suite_defaut": v[4]}
            for nom, v in p.SITUATIONS.items()}


def regle_par_defaut():
    """La regle complete avec les valeurs de secours du moteur (sans id, source, cible, mode ni
    planification, qui sont obligatoires). Meme forme que celle que le front-end ecrit."""
    r = Regle(0)
    selection = r.selection
    situations = {}
    for nom, v in p.SITUATIONS.items():
        situation = {"tentatives": v[0], "delai_sec": v[1], "niveau_final": v[2]}
        if v[4] is not None:
            situation["suite"] = v[4]
        situations[nom] = situation
    return {
        "id": None, "description": r.description, "actif": r.actif,
        "source": None, "cible": None, "mode": None, "archive": r.archive,
        "seuil_minimum": r.seuil_minimum, "seuil_maximum": r.seuil_maximum,
        "creer_dossiers": r.creer_dossiers, "horodater": r.horodater, "dossier_temporaire": r.dossier_temporaire,
        "selection": {"masque": selection.masque, "exclure": selection.exclure,
                      "recursif": selection.recursif, "modifie_depuis": selection.modifie_depuis,
                      "age_minimum_sec": selection.age_minimum_sec,
                      "age_maximum_sec": selection.age_maximum_sec,
                      "taille_minimum_octets": selection.taille_minimum_octets,
                      "ordre": selection.ordre, "limite_fichiers": selection.limite_fichiers},
        "identite": r.identite, "retention_historique_jours": r.retention_historique_jours,
        "retention_journaux_jours": r.retention_journaux_jours,
        "retention_archive_jours": r.retention_archive_jours,
        "si_cible_absente": r.si_cible_absente, "si_existe_cible": r.si_existe_cible,
        "si_existe_archive": r.si_existe_archive,
        "renommage_cible": r.renommage_cible, "renommage_archive": r.renommage_archive,
        "planification": None,
        "apres": list(r.apres), "condition": list(r.condition),
        "si_condition_non_remplie": r.si_condition_non_remplie,
        "duree_max_sec": r.duree_max_sec, "si_duree_depassee": r.si_duree_depassee,
        "relances_max": r.relances_max, "apres_erreur": r.apres_erreur,
        "situations": situations,
        "programmes": {nom: None for nom in p.PROGRAMMES},
    }


def listes():
    """Valeurs permises de chaque champ a liste fermee."""
    return {
        "modes": list(p.MODES), "niveaux": list(p.NIVEAUX), "ordres": list(p.ORDRES),
        "identites": list(p.IDENTITES), "si_cible_absente": list(p.SI_CIBLE_ABSENTE),
        "si_existe_cible": list(p.SI_EXISTE_CIBLE), "si_existe_archive": list(p.SI_EXISTE_ARCHIVE),
        "si_duree_depassee": list(p.SI_DUREE_DEPASSEE), "apres_erreur": list(p.APRES_ERREUR),
        "types_planification": list(p.TYPES_PLANIFICATION), "conditions": list(p.CONDITIONS),
        "jours": list(p.JOURS), "points_programme": list(p.PROGRAMMES),
        "variables_date": list(p.VARIABLES_DATE), "variables_renommage": list(p.VARIABLES_RENOMMAGE),
        "variables_par_point": {k: list(v) for k, v in p.VARIABLES_PAR_POINT.items()},
        "codes_environnement": list(p.CODES_ENVIRONNEMENT),
    }


def modele():
    return {"version_format": p.VERSION_FORMAT, "regle": regle_par_defaut(), "listes": listes(),
            "situations": _situations()}
