"""Purge des journaux et des archives (jalon J12). Operation DESTRUCTIVE : prudente par construction.

  * Rien n'est jamais purge sans reglage explicite (`retention_journaux_jours`,
    `retention_archive_jours` : absents = conserves pour toujours).
  * `planifier` ne supprime rien : il dresse la liste. `appliquer` supprime ce que la liste contient.
    La ligne de commande ne supprime qu'avec --appliquer.
  * Journaux : seuls les fichiers `<regle>_<AAAA-MM-JJ>.jsonl` (et `_orchestrateur_<jour>.jsonl`)
    du dossier de journaux, d'apres la DATE DU NOM. Journal d'une regle absente du parametrage :
    conserve.
  * Archives : seuls les dossiers DATES de l'archive (modele `.\\archive\\{AAAA}-{MM}-{JJ}`), d'apres
    la date de leur nom - la seule date d'archivage fiable, car un deplacement conserve la date de
    modification d'origine. Une archive sans date n'est jamais purgee (controle R13).
  * Garde-fous : jamais la source, la cible ni un dossier qui les contient ; jamais la racine d'un
    disque ; jamais un lien symbolique ni une jonction ; jamais un dossier vers lequel des archivages
    sont encore en attente ; rien en dehors de la racine de l'archive.

Specification : docs/02-moteur.md section 11.2, docs/01-parametrage.md.
"""
import calendar
import datetime
import os
import re
import shutil

from file_management import chemins
from file_management.transfert import rendre_modifiable

RE_JOURNAL = re.compile(r"^(?P<id>.+)_(?P<date>\d{4}-\d{2}-\d{2})\.jsonl$")
SANS_REGLE = "_orchestrateur"
JOURNAUX_TECHNIQUES = ("journal_si_secours",)


class Element(object):
    def __init__(self, type_, regle, chemin, date, octets, fichiers=1, racine=None):
        self.type = type_               # journal | archive
        self.regle = regle
        self.chemin = chemin
        self.date = date                # date (du nom) utilisee pour decider
        self.octets = octets
        self.fichiers = fichiers
        self.racine = racine            # racine de l'archive (controle avant suppression)

    def en_dict(self):
        return {"type": self.type, "regle": self.regle, "chemin": self.chemin, "date": self.date.isoformat(),
                "octets": self.octets, "fichiers": self.fichiers}


class Plan(object):
    def __init__(self):
        self.elements = []
        self.ignores = []               # [{"chemin", "raison"}] : vus mais conserves
        self.erreurs = []               # [texte] : regle non purgeable

    def ignorer(self, chemin, raison):
        self.ignores.append({"chemin": chemin, "raison": raison})


def _limite(aujourdhui, jours):
    return aujourdhui - datetime.timedelta(days=jours)


def _taille(chemin):
    try:
        return os.stat(chemin).st_size
    except OSError:
        return 0


# --------------------------------------------------------------------------- #
# Journaux
# --------------------------------------------------------------------------- #
def _journaux(parametrage, aujourdhui, plan, filtre):
    entete = parametrage.entete
    dossier = entete.dossier_logs
    if not dossier or not os.path.isdir(dossier):
        return
    regles = {r.id.lower(): r for r in parametrage.regles if r.id}
    try:
        noms = sorted(os.listdir(dossier))
    except OSError as e:
        plan.erreurs.append("dossier de journaux illisible (%s) : %s" % (dossier, e))
        return
    for nom in noms:
        m = RE_JOURNAL.match(nom)
        chemin = os.path.join(dossier, nom)
        if not m or os.path.islink(chemin) or not os.path.isfile(chemin):
            continue
        ident = m.group("id")
        if ident in JOURNAUX_TECHNIQUES:
            continue
        if ident == SANS_REGLE:
            if filtre is not None:
                continue
            retention, nom_regle = entete.retention_journaux_jours, None
        else:
            regle = regles.get(ident.lower())
            if regle is None:
                plan.ignorer(chemin, "journal d'une regle absente du parametrage : conserve")
                continue
            if filtre is not None and ident.lower() not in filtre:
                continue
            retention = regle.retention_journaux_jours
            if retention is None:
                retention = entete.retention_journaux_jours
            nom_regle = regle.id
        if retention is None:
            continue
        try:
            date = datetime.datetime.strptime(m.group("date"), "%Y-%m-%d").date()
        except ValueError:
            plan.ignorer(chemin, "date invalide dans le nom du fichier")
            continue
        if date < _limite(aujourdhui, retention):
            plan.elements.append(Element("journal", nom_regle, chemin, date, _taille(chemin)))


# --------------------------------------------------------------------------- #
# Archives datees
# --------------------------------------------------------------------------- #
class ErreurModele(Exception):
    pass


def _regex_composant(composant):
    sortie = ""
    for morceau in re.split(r"(\{[^{}]*\})", composant):
        if morceau == "{AAAA}":
            sortie += r"(?P<AAAA>\d{4})"
        elif morceau == "{MM}":
            sortie += r"(?P<MM>\d{2})"
        elif morceau == "{JJ}":
            sortie += r"(?P<JJ>\d{2})"
        elif morceau in ("{hh}", "{mm}", "{ss}"):
            sortie += r"\d{2}"
        elif morceau.startswith("{"):
            raise ErreurModele("variable inconnue %s dans le modele d'archive" % morceau)
        else:
            sortie += re.escape(morceau)
    return re.compile("^" + sortie + "$", re.IGNORECASE)


def decouper_modele(modele, source):
    """(racine, [regex par niveau de dossier date]) pour un modele d'archive comme
    `.\\archive\\{AAAA}-{MM}-{JJ}`. La racine est la partie fixe du chemin."""
    modele = os.path.expandvars(modele)
    lecteur, reste = os.path.splitdrive(modele)
    absolu = os.path.isabs(modele) or modele.startswith("\\\\")
    composants = [c for c in re.split(r"[\\/]+", reste) if c and c != "."]
    premier = next((i for i, c in enumerate(composants) if "{" in c), None)
    if premier is None:
        raise ErreurModele("le modele d'archive ne contient aucune variable de date")
    fixe = composants[:premier]
    if absolu:
        racine = os.path.normpath(lecteur + os.sep + os.sep.join(fixe))
    else:
        racine = os.path.normpath(os.path.join(source, *fixe))
    variables = re.findall(r"\{(AAAA|MM|JJ)\}", "/".join(composants[premier:]))
    if len(variables) != len(set(variables)):
        raise ErreurModele("une variable de date est repetee dans le modele d'archive")
    return racine, [_regex_composant(c) for c in composants[premier:]]


def _est_lien(entree):
    try:
        return entree.is_symlink() or (hasattr(entree, "is_junction") and entree.is_junction())
    except OSError:
        return True


def _dossiers_dates(racine, niveaux):
    """Dossiers du dernier niveau du modele, avec les valeurs AAAA / MM / JJ lues dans leurs noms."""
    def descendre(dossier, k, valeurs):
        if k == len(niveaux):
            yield dossier, valeurs
            return
        try:
            with os.scandir(dossier) as it:
                entrees = sorted(it, key=lambda e: e.name)
        except OSError:
            return
        for entree in entrees:
            try:
                if _est_lien(entree) or not entree.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            m = niveaux[k].match(entree.name)
            if m:
                fusion = dict(valeurs)
                fusion.update({cle: v for cle, v in m.groupdict().items() if v is not None})
                yield from descendre(entree.path, k + 1, fusion)
    return descendre(racine, 0, {})


def fin_de_periode(valeurs):
    """Dernier jour couvert par le dossier : le jour, sinon la fin du mois, sinon la fin de l'annee."""
    annee = int(valeurs["AAAA"])
    if "MM" in valeurs:
        mois = int(valeurs["MM"])
        if "JJ" in valeurs:
            return datetime.date(annee, mois, int(valeurs["JJ"]))
        return datetime.date(annee, mois, calendar.monthrange(annee, mois)[1])
    return datetime.date(annee, 12, 31)


def _mesurer(dossier):
    octets, fichiers = 0, 0
    for racine, _, noms in os.walk(dossier):
        for nom in noms:
            fichiers += 1
            octets += _taille(os.path.join(racine, nom))
    return octets, fichiers


def _archives(parametrage, base, aujourdhui, plan, filtre):
    for regle in parametrage.regles:
        if not regle.id or regle.retention_archive_jours is None:
            continue
        if filtre is not None and regle.id.lower() not in filtre:
            continue
        if regle.mode != "archivage" or not regle.archive:
            continue
        source = os.path.normpath(os.path.expandvars(regle.source))
        cible = os.path.normpath(os.path.expandvars(regle.cible))
        try:
            racine, niveaux = decouper_modele(regle.archive, source)
        except ErreurModele as e:
            plan.erreurs.append("regle %s : %s" % (regle.id, e))
            continue
        erreur = _garde_fous(racine, source, cible)
        if erreur:
            plan.erreurs.append("regle %s : %s (%s)" % (regle.id, erreur, racine))
            continue
        if not os.path.isdir(racine):
            continue
        en_attente = []
        no = base.numero_regle(regle.id) if base is not None else None
        if no is not None:
            en_attente = [chemins.normaliser(a["chemin_archive"]) for a in base.actions(no)
                          if a["chemin_archive"]]
        limite = _limite(aujourdhui, regle.retention_archive_jours)
        for dossier, valeurs in _dossiers_dates(racine, niveaux):
            try:
                fin = fin_de_periode(valeurs)
            except ValueError:
                plan.ignorer(dossier, "date invalide dans le nom du dossier")
                continue
            if fin >= limite:
                continue
            norme = chemins.normaliser(dossier)
            if any(a.startswith(norme + os.sep) or a == norme for a in en_attente):
                plan.ignorer(dossier, "des archivages sont encore en attente vers ce dossier")
                continue
            octets, fichiers = _mesurer(dossier)
            plan.elements.append(Element("archive", regle.id, dossier, fin, octets, fichiers, racine))


def _garde_fous(racine, source, cible):
    """Raison pour laquelle la racine d'archive ne doit PAS etre purgee, ou None."""
    norme = chemins.normaliser(racine)
    if os.path.dirname(racine.rstrip("\\/")) == racine.rstrip("\\/") or len(norme.rstrip("\\/")) <= 3:
        return "la racine de l'archive est la racine d'un disque"
    for nom, dossier in (("source", source), ("cible", cible)):
        d = chemins.normaliser(dossier)
        if norme == d:
            return "la racine de l'archive est la %s" % nom
        if d.startswith(norme + os.sep):
            return "la racine de l'archive contient la %s" % nom
    if norme.startswith(chemins.normaliser(cible) + os.sep):
        return "la racine de l'archive est dans la cible"
    return None


# --------------------------------------------------------------------------- #
# Plan et application
# --------------------------------------------------------------------------- #
def planifier(parametrage, base, aujourdhui=None, filtre=None):
    """Dresse la liste de ce qui serait purge. NE SUPPRIME RIEN. `filtre` : ids de regles (ou None)."""
    aujourdhui = aujourdhui or datetime.date.today()
    filtre = {f.lower() for f in filtre} if filtre else None
    plan = Plan()
    _journaux(parametrage, aujourdhui, plan, filtre)
    _archives(parametrage, base, aujourdhui, plan, filtre)
    return plan


def _supprimer_arbre(chemin, racine):
    reel, reel_racine = os.path.realpath(chemin), os.path.realpath(racine)
    if not os.path.normcase(reel).startswith(os.path.normcase(reel_racine) + os.sep):
        raise OSError("le dossier est en dehors de la racine de l'archive : %s" % chemin)
    if os.path.islink(chemin):
        raise OSError("lien symbolique : %s" % chemin)

    def forcer(fonction, cible, exception):
        rendre_modifiable(cible)
        fonction(cible)
    shutil.rmtree(chemin, onexc=forcer)
    parent = os.path.dirname(chemin)
    while os.path.normcase(parent) != os.path.normcase(racine) and \
            os.path.normcase(parent).startswith(os.path.normcase(racine)):
        try:
            os.rmdir(parent)                       # seulement s'il est vide
        except OSError:
            break
        parent = os.path.dirname(parent)


def appliquer(plan, journal=None):
    """Supprime les elements du plan. Une erreur sur un element n'arrete pas les suivants."""
    resultat = {"journaux": 0, "archives": 0, "octets": 0, "erreurs": []}
    for e in plan.elements:
        try:
            if e.type == "journal":
                rendre_modifiable(e.chemin)
                os.remove(e.chemin)
                resultat["journaux"] += 1
            else:
                _supprimer_arbre(e.chemin, e.racine)
                resultat["archives"] += 1
            resultat["octets"] += e.octets
            if journal is not None:
                journal.evenement("purge_supprime", "INFO", regle=e.regle, type=e.type, chemin=e.chemin,
                                  date=e.date.isoformat(), octets=e.octets, fichiers=e.fichiers)
        except OSError as erreur:
            resultat["erreurs"].append({"chemin": e.chemin, "message": str(erreur)})
            if journal is not None:
                journal.evenement("purge_echec", "WARNING", regle=e.regle, type=e.type, chemin=e.chemin,
                                  message=str(erreur))
    return resultat
