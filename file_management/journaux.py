"""Lecture des journaux d'une regle pour le front-end (--journaux-regle) : fichiers du dossier de journaux et
evenements decomposes, sans que l'interface ait a lire le JSON brut.

Format lu : celui de la plateforme d'observabilite (journal_si : timestamp, level, message, context{...}) ET l'ancien
format a plat (horodatage, niveau, evenement, ...) qui peut subsister dans les anciens fichiers. Un fichier par
regle et par jour : <dossier_logs>/<regle>_<AAAA-MM-JJ>.jsonl. Lecture seule, aucune ecriture.
Voir docs/07-contrat-moteur-frontend.md (--journaux-regle).
"""
import datetime
import json
import os
import re

from file_management import catalogue_journal

MAX_JOURNAUX = 45                 # fichiers resumes dans la liste (les plus recents)
LIMITE_EVENEMENTS = 1500          # evenements rendus pour un fichier (les derniers si le fichier en contient plus)
# Taille maximale de la reponse JSON (en caracteres) : Windows PowerShell 5.1 refuse de lire un JSON de plus de 2 Mo.
BUDGET_CARACTERES = 1400000

# Champs que l'interface montre dans ses colonnes : on ne les repete pas dans le detail.
_CHAMPS_COLONNES_CONTEXTE = ("object", "object_id", "event", "regle", "execution_id")
_CHAMPS_COLONNES_PLAT = ("horodatage", "niveau", "evenement", "message", "duree_ms", "application", "environnement",
                         "regle", "execution_id")


class ErreurJournal(Exception):
    pass


def _motif(regle_id):
    return re.compile(r"^%s_(\d{4}-\d{2}-\d{2})\.jsonl$" % re.escape(regle_id), re.IGNORECASE)


def _heure_locale(texte):
    """'2026-11-13T23:32:29.194Z' (UTC) -> '2026-11-14 00:32:29' (heure locale de la machine du moteur)."""
    if not texte:
        return ""
    try:
        t = datetime.datetime.strptime(str(texte)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
        return t.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return str(texte)


def _valeur(v):
    """Valeur d'un champ rendue au front-end : scalaire tel quel, structure en texte JSON compact."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def _message(evenement, niveau, champs):
    return catalogue_journal.decrire(evenement, niveau, champs).get("message", evenement)


def normaliser(ligne):
    """Une ligne de journal (dict) -> evenement a plat pour l'interface, ou None si la ligne n'est pas un evenement."""
    if not isinstance(ligne, dict):
        return None
    if isinstance(ligne.get("context"), dict) or "timestamp" in ligne:
        contexte = ligne.get("context") if isinstance(ligne.get("context"), dict) else {}
        evenement = str(contexte.get("event") or "")
        niveau = str(ligne.get("level") or "INFO").upper()
        erreur = ligne.get("error") if isinstance(ligne.get("error"), dict) else None
        return {"horodatage": ligne.get("timestamp") or "", "niveau": niveau, "evenement": evenement,
                "message": str(ligne.get("message") or _message(evenement, niveau, contexte)),
                "execution_id": contexte.get("execution_id"), "duree_ms": ligne.get("duration_ms"),
                "erreur": ({"type": erreur.get("type"), "exception": erreur.get("exception"),
                            "pile": erreur.get("stacktrace")} if erreur else None),
                "champs": [(k, _valeur(v)) for k, v in contexte.items() if k not in _CHAMPS_COLONNES_CONTEXTE]}
    if "horodatage" in ligne or "evenement" in ligne:
        evenement = str(ligne.get("evenement") or "")
        niveau = str(ligne.get("niveau") or "INFO").upper()
        autres = {k: v for k, v in ligne.items() if k not in _CHAMPS_COLONNES_PLAT}
        return {"horodatage": ligne.get("horodatage") or "", "niveau": niveau, "evenement": evenement,
                "message": str(ligne.get("message") or _message(evenement, niveau, autres)),
                "execution_id": ligne.get("execution_id"), "duree_ms": ligne.get("duree_ms"),
                "erreur": None, "champs": [(k, _valeur(v)) for k, v in autres.items()]}
    return None


def _lire(chemin):
    """Evenements d'un fichier + nombre de lignes illisibles. Tolere un fichier en cours d'ecriture (derniere ligne coupee)."""
    evenements, illisibles = [], 0
    try:
        with open(chemin, "r", encoding="utf-8", errors="replace") as f:
            for brut in f:
                brut = brut.strip()
                if not brut:
                    continue
                try:
                    e = normaliser(json.loads(brut))
                except ValueError:
                    e = None
                if e is None:
                    illisibles += 1
                else:
                    evenements.append(e)
    except OSError as e:
        raise ErreurJournal("journal illisible (%s) : %s" % (os.path.basename(chemin), e))
    return evenements, illisibles


def executions(evenements):
    """Regroupe les evenements par execution : debut, statut, declencheur, duree, compteurs. Chaque evenement recoit
    la cle de son groupe (`groupe`). Une execution reelle porte son execution_id ; une simulation n'en a pas : ses
    evenements sont regroupes de regle_demarree a regle_terminee (cles s1, s2...). Les autres (debut_lancement, ...)
    n'ont pas de groupe."""
    ordre, parcle = [], {}
    anonyme, nb_anonymes = None, 0
    for e in evenements:
        ident = e["execution_id"]
        if ident is not None:
            cle = str(ident)
        elif e["evenement"] == "regle_demarree":
            nb_anonymes += 1
            anonyme = cle = "s%d" % nb_anonymes
        else:
            cle = anonyme
        if ident is None and e["evenement"] == "regle_terminee":
            anonyme = None
        e["groupe"] = cle
        if cle is None:
            continue
        x = parcle.get(cle)
        if x is None:
            x = {"cle": cle, "execution_id": ident, "debut": e["horodatage"], "declencheur": None, "simulation": False,
                 "statut": None, "motif": None, "duree_ms": None, "compteurs": None, "avertissements": 0, "erreurs": 0}
            parcle[cle] = x
            ordre.append(x)
        champs = dict(e["champs"])
        if e["evenement"] == "regle_demarree":
            x["debut"] = e["horodatage"] or x["debut"]
            x["declencheur"] = champs.get("declencheur")
        if champs.get("simulation"):
            x["simulation"] = True
        if e["evenement"] == "regle_terminee":
            x["statut"], x["motif"], x["duree_ms"] = champs.get("statut"), champs.get("motif"), e["duree_ms"]
            compteurs = champs.get("compteurs")
            if isinstance(compteurs, str):
                try:
                    compteurs = json.loads(compteurs)
                except ValueError:
                    pass
            x["compteurs"] = compteurs
        if e["niveau"] == "WARNING":
            x["avertissements"] += 1
        elif e["niveau"] in ("ERROR", "CRITICAL"):
            x["erreurs"] += 1
    for x in ordre:
        x["heure"] = _heure_locale(x["debut"])
    return ordre


def _noms_journaux(parametrage, regle_id):
    dossier = parametrage.entete.dossier_logs
    if not dossier or not os.path.isdir(dossier):
        return dossier, []
    motif = _motif(regle_id)
    try:
        noms = os.listdir(dossier)
    except OSError as e:
        raise ErreurJournal("dossier de journaux illisible (%s) : %s" % (dossier, e))
    trouves = []
    for nom in noms:
        m = motif.match(nom)
        chemin = os.path.join(dossier, nom)
        if m and os.path.isfile(chemin) and not os.path.islink(chemin):
            trouves.append((m.group(1), nom))
    trouves.sort(reverse=True)                 # plus recent d'abord
    return dossier, trouves


def lister(parametrage, regle_id):
    """Journaux d'une regle, les plus recents d'abord, avec leur resume (statut de la derniere execution, anomalies)."""
    dossier, trouves = _noms_journaux(parametrage, regle_id)
    journaux = []
    for jour, nom in trouves[:MAX_JOURNAUX]:
        chemin = os.path.join(dossier, nom)
        evenements, illisibles = _lire(chemin)
        execs = executions(evenements)
        terminees = [x for x in execs if x["statut"]]
        dernier = terminees[-1] if terminees else None
        journaux.append({
            "nom": nom, "jour": jour, "octets": os.path.getsize(chemin), "evenements": len(evenements),
            "illisibles": illisibles, "executions": len(execs),
            "avertissements": sum(1 for e in evenements if e["niveau"] == "WARNING"),
            "erreurs": sum(1 for e in evenements if e["niveau"] in ("ERROR", "CRITICAL")),
            "statut": dernier["statut"] if dernier else None, "motif": dernier["motif"] if dernier else None,
            "dernier": _heure_locale(evenements[-1]["horodatage"]) if evenements else ""})
    return {"dossier": dossier, "journaux": journaux, "tronque": len(trouves) > MAX_JOURNAUX,
            "total_fichiers": len(trouves)}


def lire(parametrage, regle_id, nom, limite=LIMITE_EVENEMENTS):
    """Evenements decomposes d'un journal de la regle. `nom` doit etre un fichier <regle>_<jour>.jsonl de la regle :
    jamais un chemin."""
    if limite is None or limite < 1:
        limite = LIMITE_EVENEMENTS
    dossier, trouves = _noms_journaux(parametrage, regle_id)
    vrai = next((n for _, n in trouves if nom and n.lower() == nom.lower()), None)
    if vrai is None:
        raise ErreurJournal("journal inconnu pour la regle %s : %s" % (regle_id, nom))
    evenements, illisibles = _lire(os.path.join(dossier, vrai))
    total = len(evenements)
    execs = executions(evenements)
    if total > limite:
        evenements = evenements[-limite:]
    premier = total - len(evenements)
    rendus = [{"numero": premier + i, "heure": _heure_locale(e["horodatage"]), "niveau": e["niveau"],
               "evenement": e["evenement"], "message": e["message"], "execution_id": e["execution_id"], "groupe": e["groupe"],
               "duree_ms": e["duree_ms"], "erreur": e["erreur"],
               "champs": [{"cle": k, "valeur": v} for k, v in e["champs"]]}
              for i, e in enumerate(evenements, 1)]
    # Budget de taille : on garde les derniers evenements qui tiennent (les plus recents sont les plus utiles).
    reste = BUDGET_CARACTERES - len(json.dumps(execs, ensure_ascii=False, indent=1))
    gardes = 0
    for e in reversed(rendus):
        reste -= len(json.dumps(e, ensure_ascii=False, indent=1)) + 2
        if reste < 0:
            break
        gardes += 1
    rendus = rendus[len(rendus) - gardes:]
    return {"journal": vrai, "evenements": rendus, "total": total, "tronque": total > len(rendus),
            "illisibles": illisibles, "executions": execs}
