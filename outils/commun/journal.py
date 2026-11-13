# bibliotheque: journal des outils : meme module que le moteur (journal_si), meme fichier de regle, meme trace
"""Journal des outils : le MEME module que le moteur (journal_si.Journal), meme fichier, meme trace.

Un outil appele par une regle ecrit dans <dossier_logs>\\<regle>_<AAAA-MM-JJ>.jsonl avec
service.name = file_management.<regle>, la trace de la variable TRACEPARENT, l'execution_id de la
regle, outil=<nom>, point_appel et (en simulation) simulation=true.
"""

import journal_si

APPLICATION = "file_management"

# Code de la plateforme d'apres le nom de l'environnement du parametrage (production -> prod)
_ALIAS = {"production": "prod", "preproduction": "pprod", "recette": "test", "developpement": "dev",
          "integration": "int", "qualification": "test"}


def deduire_code_environnement(nom):
    """Meme regle que file_management.parametrage.deduire_code_environnement (sans importer le moteur
    si on peut l'eviter)."""
    try:
        from file_management.parametrage import deduire_code_environnement as moteur
        return moteur(nom)
    except Exception:
        nom = (nom or "").strip().lower()
        return nom if nom in journal_si.ENVIRONNEMENTS else _ALIAS.get(nom)


def version():
    try:
        from file_management import __version__
        return __version__
    except Exception:
        return None


def decrire(nom, niveau, champs):
    """Catalogue des evenements de cycle de vie ; les autres evenements portent leur message."""
    if nom == "outil_demarre":
        return {"message": "Outil demarre : %s" % champs.get("outil", "")}
    if nom == "outil_termine":
        return {"message": "Outil termine : %s : %s" % (champs.get("outil", ""), champs.get("statut", ""))}
    return {}


def resoudre(args, env):
    """(code d'environnement, dossier de journaux, regle, execution_id, point d'appel, trace_id) d'apres
    les options puis les variables COPIE_* du moteur."""
    code = (getattr(args, "environnement", None) or env.get("COPIE_CODE_ENVIRONNEMENT")
            or deduire_code_environnement(env.get("COPIE_ENVIRONNEMENT")) or "dev")
    dossier = (getattr(args, "dossier_logs", None) or env.get("COPIE_DOSSIER_LOGS")
               or env.get("JOURNAL_SI_DOSSIER") or None)
    regle = getattr(args, "regle", None) or env.get("COPIE_REGLE") or None
    execution = env.get("COPIE_EXECUTION_ID", "").strip()
    execution = int(execution) if execution.isdigit() else None
    parent = journal_si.lire_traceparent(env.get("TRACEPARENT", ""))
    return code, dossier, regle, execution, env.get("COPIE_POINT_APPEL") or None, (parent[0] if parent else None)


def ouvrir(nom_outil, args, env, simulation):
    """Cree le journal de l'outil et ecrit `outil_demarre`. Leve ValueError si le code d'environnement
    n'est pas un code de la plateforme."""
    code, dossier, regle, execution, point, trace = resoudre(args, env)
    if code not in journal_si.ENVIRONNEMENTS:
        raise ValueError("code d'environnement '%s' hors de la liste de la plateforme (%s)"
                         % (code, ", ".join(journal_si.ENVIRONNEMENTS)))
    champs = {"outil": nom_outil}
    if regle:
        champs["regle"] = regle
    if execution is not None:
        champs["execution_id"] = execution
    if point:
        champs["point_appel"] = point
    if simulation:
        champs["simulation"] = True
    j = journal_si.Journal()
    j.catalogue = decrire
    j.debut(APPLICATION, code, dossier=dossier, verbeux=getattr(args, "verbeux", False),
            console=getattr(args, "console", False), version=version(),
            evenement_debut="outil_demarre", evenement_fin="outil_termine", trace_id=trace, **champs)
    return j
