"""Lecture du fichier de parametrage (JSON Lines) : modele, types, valeurs de secours.

Les controles qui comparent plusieurs regles entre elles sont dans controles.py.
Specification : docs/01-parametrage.md.
"""
import json
import os
import re

from copie.diagnostic import Rapport

VERSION_FORMAT = 1

RE_ENVIRONNEMENT = re.compile(r"^[a-z0-9_-]{1,32}$")
RE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
RE_HEURE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
RE_MODIFIE_DEPUIS = re.compile(r"^(TOUT|J|J-(\d+))$")

MODES = ("copie", "deplacement", "archivage")
NIVEAUX = ("INFO", "WARNING", "ERREUR")
ORDRES = ("nom", "date_modification")
IDENTITES = ("version", "contenu")
SI_CIBLE_ABSENTE = ("ignorer", "recopier")
SI_EXISTE_CIBLE = ("erreur", "ecraser", "ignorer", "suffixe")
SI_EXISTE_ARCHIVE = ("suffixe", "ecraser", "erreur")
SI_DUREE_DEPASSEE = ("erreur", "relancer", "alerter")
APRES_ERREUR = ("arreter", "continuer")
TYPES_PLANIFICATION = ("intervalle", "quotidien", "apres_dependances")
CONDITIONS = ("termine", "succes", "fichiers")
JOURS = ("lun", "mar", "mer", "jeu", "ven", "sam", "dim")
PROGRAMMES = ("avant_lot", "avant_fichier", "apres_fichier", "apres_lot", "sur_erreur", "reprise")

VARIABLES_DATE = ("AAAA", "MM", "JJ", "hh", "mm", "ss")
VARIABLES_RENOMMAGE = VARIABLES_DATE + ("nom", "ext")
VARIABLES_PROGRAMME = ("environnement", "regle", "source", "cible", "archive", "fichier", "nom",
                       "fichier_cible", "liste", "liste_json", "date")

# situation -> (tentatives, delai_sec, niveau_final, suites autorisees, suite par defaut)
# Valeurs de secours : docs/01-parametrage.md, section 6.
AS, FS, CD = "arreter_regle", "fichier_suivant", "continuer_en_differe"
SITUATIONS = {
    "source_inaccessible":      (3, 30, "ERREUR",  (AS,),     AS),
    "cible_inaccessible":       (3, 30, "ERREUR",  (AS,),     AS),
    "archive_inaccessible":     (3, 30, "WARNING", (AS, CD),  CD),
    "espace_insuffisant_cible": (1, 0,  "ERREUR",  (AS,),     AS),
    "espace_insuffisant_archive": (1, 0, "WARNING", (AS, CD), CD),
    "aucun_fichier":            (1, 0,  "INFO",    (),        None),
    "fichier_verrouille":       (5, 60, "ERREUR",  (FS, AS),  AS),
    "fichier_instable":         (3, 30, "WARNING", (FS, AS),  AS),
    "fichier_disparu":          (1, 0,  "INFO",    (FS, AS),  FS),
    "copie_echec":              (3, 10, "ERREUR",  (FS, AS),  AS),
    "verification_echec":       (3, 10, "ERREUR",  (FS, AS),  AS),
    "fichier_existe_cible":     (1, 0,  "ERREUR",  (FS, AS),  AS),
    "fichier_existe_archive":   (1, 0,  "ERREUR",  (FS, AS),  AS),
    "source_modifiee":          (1, 0,  "WARNING", (FS,),     FS),
    "suppression_echec":        (3, 10, "WARNING", (AS, CD),  CD),
    "archivage_echec":          (3, 10, "WARNING", (AS, CD),  CD),
    "doublon_contenu":          (1, 0,  "INFO",    (FS,),     FS),
    "programme_avant_lot":      (1, 0,  "ERREUR",  (AS,),     AS),
    "programme_avant_fichier":  (1, 0,  "ERREUR",  (FS, AS),  AS),
    "programme_apres_fichier":  (1, 0,  "ERREUR",  (FS, AS),  AS),
    "programme_apres_lot":      (1, 0,  "ERREUR",  (),        None),
    "programme_reprise":        (1, 0,  "ERREUR",  (AS,),     AS),
}


# --------------------------------------------------------------------------- #
# Modele
# --------------------------------------------------------------------------- #
class Entete(object):
    def __init__(self):
        self.version = VERSION_FORMAT
        self.environnement = ""
        self.base = ""
        self.dossier_logs = None
        self.dossier_travail = None
        self.parallele_max = None
        self.retention_executions_jours = 365
        self.marge_espace_mo = 64


class Selection(object):
    def __init__(self):
        self.masque = "*"
        self.exclure = ""
        self.recursif = False
        self.modifie_depuis = "TOUT"
        self.age_minimum_sec = None
        self.age_maximum_sec = None
        self.taille_minimum_octets = None
        self.ordre = "nom"
        self.limite_fichiers = None

    def fenetre_jours(self):
        """Fenetre de selection en jours (None = pas de fenetre) : J = 1, J-N = N + 1."""
        fenetres = []
        m = RE_MODIFIE_DEPUIS.match(self.modifie_depuis)
        if m and m.group(1) != "TOUT":
            fenetres.append(int(m.group(2)) + 1 if m.group(2) else 1)
        if self.age_maximum_sec:
            fenetres.append(-(-self.age_maximum_sec // 86400))      # arrondi au jour superieur
        return max(fenetres) if fenetres else None


class Planification(object):
    def __init__(self):
        self.type = None
        self.frequence_sec = None
        self.debut = None            # minutes depuis minuit
        self.fin = None
        self.heure = None
        self.jours = frozenset(range(7))
        self.rattrapage_sec = None


class Situation(object):
    def __init__(self, tentatives, delai_sec, niveau_final, suite):
        self.tentatives = tentatives
        self.delai_sec = delai_sec
        self.niveau_final = niveau_final
        self.suite = suite


class Programme(object):
    def __init__(self, commande, timeout_sec):
        self.commande = commande
        self.timeout_sec = timeout_sec


class Regle(object):
    def __init__(self, ligne):
        self.ligne = ligne
        self.id = None
        self.description = ""
        self.actif = True
        self.source = None
        self.cible = None
        self.mode = None
        self.archive = None
        self.creer_dossiers = True
        self.dossier_temporaire = None
        self.selection = Selection()
        self.identite = "version"
        self.retention_historique_jours = 90
        self.si_cible_absente = "ignorer"
        self.si_existe_cible = "erreur"
        self.si_existe_archive = "suffixe"
        self.renommage_cible = None
        self.renommage_archive = None
        self.planification = None
        self.apres = []
        self.condition = ["succes"]
        self.condition_explicite = False
        self.si_condition_non_remplie = "WARNING"
        self.duree_max_sec = 1800
        self.si_duree_depassee = "erreur"
        self.relances_max = 2
        self.apres_erreur = "arreter"
        self.situations = {n: Situation(v[0], v[1], v[2], v[4]) for n, v in SITUATIONS.items()}
        self.programmes = {n: None for n in PROGRAMMES}

    @property
    def etiquette(self):
        return self.id if self.id else "ligne %d" % self.ligne


class Parametrage(object):
    def __init__(self, chemin):
        self.chemin = chemin
        self.entete = None
        self.regles = []


# --------------------------------------------------------------------------- #
# Lecture JSON
# --------------------------------------------------------------------------- #
class _ErreurJson(ValueError):
    pass


def _paires(paires):
    objet = {}
    for cle, valeur in paires:
        if cle in objet:
            raise _ErreurJson("champ '%s' present deux fois" % cle)
        objet[cle] = valeur
    return objet


def _constante(nom):
    raise _ErreurJson("valeur %s non autorisee" % nom)


def analyser_json(texte):
    return json.loads(texte, object_pairs_hook=_paires, parse_constant=_constante)


# --------------------------------------------------------------------------- #
# Lecture d'un objet champ par champ
# --------------------------------------------------------------------------- #
def _est_entier(v):
    return isinstance(v, int) and not isinstance(v, bool)


TYPES = {
    "texte": (lambda v: isinstance(v, str), False, "un texte"),
    "texte_ou_null": (lambda v: isinstance(v, str), True, "un texte ou null"),
    "booleen": (lambda v: isinstance(v, bool), False, "true ou false"),
    "entier": (_est_entier, False, "un nombre entier"),
    "entier_ou_null": (_est_entier, True, "un nombre entier ou null"),
    "liste_texte": (lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
                    False, "une liste de textes"),
    "objet": (lambda v: isinstance(v, dict), False, "un objet"),
    "objet_ou_null": (lambda v: isinstance(v, dict), True, "un objet ou null"),
}


class Lecteur(object):
    """Lit les champs d'un objet JSON, signale les types faux (E06) puis les champs inconnus (E06)."""

    def __init__(self, objet, rapport, ligne, regle=None, contexte=""):
        self.objet = objet
        self.rapport = rapport
        self.ligne = ligne
        self.regle = regle
        self.prefixe = contexte + "." if contexte else ""
        self.lus = set()

    def signaler(self, code, message):
        self.rapport.signaler(code, message, regle=self.regle, ligne=self.ligne)

    def a(self, nom):
        return nom in self.objet

    def valeur(self, nom, type_, defaut, obligatoire=False):
        self.lus.add(nom)
        if nom not in self.objet:
            if obligatoire:
                self.signaler("R01", "champ obligatoire absent : %s%s" % (self.prefixe, nom))
            return defaut
        v = self.objet[nom]
        verifie, accepte_null, attendu = TYPES[type_]
        if v is None and accepte_null:
            return None
        if v is None or not verifie(v):
            self.signaler("E06", "%s%s : %s attendu" % (self.prefixe, nom, attendu))
            return defaut
        return v

    def choix(self, nom, autorises, defaut, obligatoire=False):
        v = self.valeur(nom, "texte", defaut, obligatoire)
        if v is not None and v not in autorises:
            self.signaler("R06", "%s%s : '%s' non autorise (attendu : %s)"
                          % (self.prefixe, nom, v, ", ".join(autorises)))
            return defaut
        return v

    def entier(self, nom, defaut, minimum=None, nullable=False):
        v = self.valeur(nom, "entier_ou_null" if nullable else "entier", defaut)
        if v is not None and minimum is not None and v < minimum:
            self.signaler("R07", "%s%s : %d est inferieur au minimum %d"
                          % (self.prefixe, nom, v, minimum))
            return defaut
        return v

    def inconnus(self):
        for nom in self.objet:
            if nom not in self.lus:
                self.signaler("E06", "champ inconnu : %s%s" % (self.prefixe, nom))


# --------------------------------------------------------------------------- #
# En-tete
# --------------------------------------------------------------------------- #
def est_chemin_reseau(chemin):
    return chemin.startswith("\\\\") or chemin.startswith("//")


def lire_entete(objet, ligne, chemin_fichier, rapport):
    """Renvoie l'en-tete, ou None si le fichier ne peut pas etre interprete (E01, E02)."""
    if not isinstance(objet, dict) or "version" not in objet:
        rapport.signaler("E01", "la premiere ligne doit etre l'en-tete "
                         '{"version": 1, "environnement": ..., "base": ...}', ligne=ligne)
        return None
    if objet["version"] != VERSION_FORMAT or not _est_entier(objet["version"]):
        rapport.signaler("E02", "version du format %r non supportee (supportee : %d)"
                         % (objet["version"], VERSION_FORMAT), ligne=ligne)
        return None

    e = Entete()
    lecteur = Lecteur(objet, rapport, ligne, contexte="")
    lecteur.valeur("version", "entier", VERSION_FORMAT)
    e.environnement = lecteur.valeur("environnement", "texte", "")
    e.base = lecteur.valeur("base", "texte", "")
    e.dossier_logs = lecteur.valeur("dossier_logs", "texte_ou_null", None)
    e.dossier_travail = lecteur.valeur("dossier_travail", "texte_ou_null", None)
    e.parallele_max = lecteur.entier("parallele_max", None, minimum=1, nullable=True)
    e.retention_executions_jours = lecteur.entier("retention_executions_jours", 365, minimum=1)
    e.marge_espace_mo = lecteur.entier("marge_espace_mo", 64, minimum=0)
    lecteur.inconnus()

    nom_fichier = os.path.splitext(os.path.basename(chemin_fichier))[0]
    if "environnement" not in objet or not RE_ENVIRONNEMENT.match(e.environnement):
        rapport.signaler("E03", "environnement absent ou invalide (attendu : minuscules, chiffres, "
                         "_ et -, 32 caracteres maximum)", ligne=ligne)
    elif e.environnement != nom_fichier:
        rapport.signaler("E03", "l'environnement '%s' doit etre egal au nom du fichier '%s'"
                         % (e.environnement, nom_fichier), ligne=ligne)

    if not e.base.strip():
        rapport.signaler("E04", "le champ 'base' est obligatoire", ligne=ligne)
    elif est_chemin_reseau(e.base):
        rapport.signaler("E05", "la base ne peut pas etre sur un partage reseau : %s" % e.base,
                         ligne=ligne)
    else:
        racine = os.path.dirname(e.base)
        e.dossier_logs = e.dossier_logs or os.path.join(racine, "logs")
        e.dossier_travail = e.dossier_travail or os.path.join(racine, "travail")
    return e


# --------------------------------------------------------------------------- #
# Regle
# --------------------------------------------------------------------------- #
def lire_jours(texte):
    """'tous', 'lun-ven', 'lun,mer,ven' -> ensemble de numeros (0 = lundi), ou None si invalide."""
    texte = texte.strip().lower()
    if texte == "tous":
        return frozenset(range(7))
    jours = set()
    for morceau in texte.split(","):
        morceau = morceau.strip()
        if morceau in JOURS:
            jours.add(JOURS.index(morceau))
        elif "-" in morceau:
            debut, _, fin = morceau.partition("-")
            if debut not in JOURS or fin not in JOURS or JOURS.index(debut) > JOURS.index(fin):
                return None
            jours.update(range(JOURS.index(debut), JOURS.index(fin) + 1))
        else:
            return None
    return frozenset(jours)


def lire_heure(texte):
    m = RE_HEURE.match(texte) if isinstance(texte, str) else None
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _lire_selection(objet, ligne, regle, rapport):
    s = Selection()
    lecteur = Lecteur(objet, rapport, ligne, regle.id, "selection")
    s.masque = lecteur.valeur("masque", "texte", "*")
    s.exclure = lecteur.valeur("exclure", "texte", "")
    s.recursif = lecteur.valeur("recursif", "booleen", False)
    depuis = lecteur.valeur("modifie_depuis", "texte", "TOUT").strip().upper()
    if RE_MODIFIE_DEPUIS.match(depuis):
        s.modifie_depuis = depuis
    else:
        lecteur.signaler("R06", "selection.modifie_depuis : '%s' invalide (attendu : TOUT, J, J-N)"
                         % depuis)
    s.age_minimum_sec = lecteur.entier("age_minimum_sec", None, minimum=0, nullable=True)
    s.age_maximum_sec = lecteur.entier("age_maximum_sec", None, minimum=1, nullable=True)
    s.taille_minimum_octets = lecteur.entier("taille_minimum_octets", None, minimum=0, nullable=True)
    s.ordre = lecteur.choix("ordre", ORDRES, "nom")
    s.limite_fichiers = lecteur.entier("limite_fichiers", None, minimum=1, nullable=True)
    lecteur.inconnus()
    if (s.age_minimum_sec is not None and s.age_maximum_sec is not None
            and s.age_minimum_sec >= s.age_maximum_sec):
        lecteur.signaler("R07", "selection : age_minimum_sec (%d) doit etre inferieur a "
                         "age_maximum_sec (%d)" % (s.age_minimum_sec, s.age_maximum_sec))
    return s


def _lire_planification(objet, ligne, regle, rapport):
    p = Planification()
    lecteur = Lecteur(objet, rapport, ligne, regle.id, "planification")
    p.type = lecteur.valeur("type", "texte", None, obligatoire=True)
    if p.type is not None and p.type not in TYPES_PLANIFICATION:
        lecteur.signaler("P01", "planification.type : '%s' inconnu (attendu : %s)"
                         % (p.type, ", ".join(TYPES_PLANIFICATION)))
    if p.type in ("intervalle", "quotidien"):
        jours = lecteur.valeur("jours", "texte", "tous")
        lus = lire_jours(jours)
        if lus is None:
            lecteur.signaler("P01", "planification.jours : '%s' invalide (exemples : tous, "
                             "lun-ven, lun,mer,ven)" % jours)
        else:
            p.jours = lus
        p.rattrapage_sec = lecteur.entier("rattrapage_sec", None, minimum=0, nullable=True)
    if p.type == "intervalle":
        for nom in ("debut", "fin"):
            texte = lecteur.valeur(nom, "texte", None)
            minutes = lire_heure(texte)
            if texte is None:
                lecteur.signaler("P01", "planification.%s est obligatoire pour un intervalle" % nom)
            elif minutes is None:
                lecteur.signaler("P01", "planification.%s : '%s' n'est pas une heure HH:MM"
                                 % (nom, texte))
            setattr(p, nom, minutes)
        if lecteur.a("frequence_sec"):
            p.frequence_sec = lecteur.entier("frequence_sec", None, minimum=1)
        else:
            lecteur.signaler("P01", "planification.frequence_sec est obligatoire pour un intervalle")
        if p.debut is not None and p.fin is not None and p.debut >= p.fin:
            lecteur.signaler("P01", "planification : debut doit etre anterieur a fin")
    elif p.type == "quotidien":
        texte = lecteur.valeur("heure", "texte", None)
        p.heure = lire_heure(texte)
        if texte is None:
            lecteur.signaler("P01", "planification.heure est obligatoire pour un quotidien")
        elif p.heure is None:
            lecteur.signaler("P01", "planification.heure : '%s' n'est pas une heure HH:MM" % texte)
    lecteur.inconnus()
    return p


def _lire_situations(objet, ligne, regle, rapport):
    for nom, valeur in objet.items():
        if nom not in SITUATIONS:
            rapport.signaler("E06", "situations : situation inconnue '%s'" % nom,
                             regle=regle.id, ligne=ligne)
            continue
        if not isinstance(valeur, dict):
            rapport.signaler("E06", "situations.%s : un objet est attendu" % nom,
                             regle=regle.id, ligne=ligne)
            continue
        tent, delai, niveau, suites, suite_defaut = SITUATIONS[nom]
        lecteur = Lecteur(valeur, rapport, ligne, regle.id, "situations." + nom)
        s = Situation(
            lecteur.entier("tentatives", tent, minimum=1),
            lecteur.entier("delai_sec", delai, minimum=0),
            lecteur.choix("niveau_final", NIVEAUX, niveau),
            suite_defaut)
        if lecteur.a("suite"):
            if suites:
                s.suite = lecteur.choix("suite", suites, suite_defaut)
            else:
                lecteur.lus.add("suite")
                lecteur.signaler("R06", "situations.%s.suite : cette situation n'a pas de 'suite'"
                                 % nom)
        lecteur.inconnus()
        regle.situations[nom] = s


def variables_inconnues(modele, autorisees):
    """Noms de variables {xxx} absents de la liste ; une accolade isolee compte comme erreur."""
    inconnues = [n for n in re.findall(r"\{([^{}]*)\}", modele) if n not in autorisees]
    reste = re.sub(r"\{[^{}]*\}", "", modele)
    if "{" in reste or "}" in reste:
        inconnues.append("accolade non fermee")
    return inconnues


def _lire_programme(nom, valeur, ligne, regle, rapport):
    if valeur is None:
        return None
    if not isinstance(valeur, dict):
        rapport.signaler("E06", "programmes.%s : un objet ou null est attendu" % nom,
                         regle=regle.id, ligne=ligne)
        return None
    lecteur = Lecteur(valeur, rapport, ligne, regle.id, "programmes." + nom)
    # Les contenus de 'commande' et 'timeout_sec' relevent de G01, pas de E06
    lecteur.lus.update(("commande", "timeout_sec"))
    commande = valeur.get("commande")
    if "commande" not in valeur:
        lecteur.signaler("G01", "programmes.%s.commande est obligatoire" % nom)
    elif not (isinstance(commande, list) and commande
              and all(isinstance(c, str) and c.strip() for c in commande)):
        lecteur.signaler("G01", "programmes.%s.commande : un tableau non vide de textes non vides "
                         "est attendu (pas une chaine)" % nom)
        commande = None
    else:
        for element in commande:
            for variable in variables_inconnues(element, VARIABLES_PROGRAMME):
                lecteur.signaler("G01", "programmes.%s.commande : variable inconnue {%s}"
                                 % (nom, variable))
    timeout = valeur.get("timeout_sec")
    if "timeout_sec" not in valeur:
        lecteur.signaler("G01", "programmes.%s.timeout_sec est obligatoire" % nom)
    elif not _est_entier(timeout) or timeout <= 0:
        lecteur.signaler("G01", "programmes.%s.timeout_sec doit etre un entier superieur a 0" % nom)
        timeout = None
    lecteur.inconnus()
    if commande is None or timeout is None:
        return None
    return Programme(tuple(commande), timeout)


def lire_regle(objet, ligne, rapport):
    """Construit une regle depuis un objet JSON. Les valeurs erronees sont remplacees par leur
    valeur de secours : la regle reste exploitable par les controles croises, le rapport porte
    les refus."""
    r = Regle(ligne)
    if not isinstance(objet, dict):
        rapport.signaler("E06", "la ligne doit etre un objet JSON", ligne=ligne)
        return r
    ident = objet.get("id")
    r.id = ident if isinstance(ident, str) else None

    lecteur = Lecteur(objet, rapport, ligne, r.id)
    lecteur.valeur("id", "texte", None, obligatoire=True)
    if r.id is not None and not RE_ID.match(r.id):
        lecteur.signaler("R02", "id '%s' invalide (attendu : lettres, chiffres, _ et -, "
                         "64 caracteres maximum)" % r.id)
    r.description = lecteur.valeur("description", "texte", "")
    r.actif = lecteur.valeur("actif", "booleen", True)
    r.source = lecteur.valeur("source", "texte", None, obligatoire=True)
    r.cible = lecteur.valeur("cible", "texte", None, obligatoire=True)
    for nom in ("source", "cible"):
        if getattr(r, nom) is not None and not getattr(r, nom).strip():
            lecteur.signaler("R01", "champ obligatoire vide : %s" % nom)
    r.mode = lecteur.choix("mode", MODES, None, obligatoire=True)
    r.archive = lecteur.valeur("archive", "texte_ou_null", None)
    r.creer_dossiers = lecteur.valeur("creer_dossiers", "booleen", True)
    r.dossier_temporaire = lecteur.valeur("dossier_temporaire", "texte_ou_null", None)

    if r.mode == "archivage" and not (r.archive and r.archive.strip()):
        lecteur.signaler("R04", "le mode archivage impose le champ 'archive'")
    elif r.archive and r.mode in ("copie", "deplacement"):
        lecteur.signaler("R05", "'archive' est renseigne mais le mode est '%s' : il sera ignore"
                         % r.mode)
    if r.archive:
        for v in variables_inconnues(r.archive, VARIABLES_DATE):
            lecteur.signaler("R12", "archive : variable inconnue {%s}" % v)

    sel = lecteur.valeur("selection", "objet", None)
    if sel is not None:
        r.selection = _lire_selection(sel, ligne, r, rapport)

    r.identite = lecteur.choix("identite", IDENTITES, "version")
    r.retention_historique_jours = lecteur.entier("retention_historique_jours", 90, minimum=1)
    r.si_cible_absente = lecteur.choix("si_cible_absente", SI_CIBLE_ABSENTE, "ignorer")
    r.si_existe_cible = lecteur.choix("si_existe_cible", SI_EXISTE_CIBLE, "erreur")
    r.si_existe_archive = lecteur.choix("si_existe_archive", SI_EXISTE_ARCHIVE, "suffixe")
    for nom in ("renommage_cible", "renommage_archive"):
        modele = lecteur.valeur(nom, "texte_ou_null", None)
        setattr(r, nom, modele)
        for v in variables_inconnues(modele or "", VARIABLES_RENOMMAGE):
            lecteur.signaler("R12", "%s : variable inconnue {%s}" % (nom, v))

    planif = lecteur.valeur("planification", "objet", None, obligatoire=True)
    if planif is not None:
        r.planification = _lire_planification(planif, ligne, r, rapport)

    r.apres = lecteur.valeur("apres", "liste_texte", [])
    r.condition_explicite = lecteur.a("condition")
    r.condition = lecteur.valeur("condition", "liste_texte", ["succes"])
    r.si_condition_non_remplie = lecteur.choix("si_condition_non_remplie", NIVEAUX, "WARNING")

    r.duree_max_sec = lecteur.entier("duree_max_sec", 1800, minimum=1)
    r.si_duree_depassee = lecteur.choix("si_duree_depassee", SI_DUREE_DEPASSEE, "erreur")
    r.relances_max = lecteur.entier("relances_max", 2, minimum=0)
    r.apres_erreur = lecteur.choix("apres_erreur", APRES_ERREUR, "arreter")

    sit = lecteur.valeur("situations", "objet", {})
    _lire_situations(sit, ligne, r, rapport)
    prog = lecteur.valeur("programmes", "objet", {})
    for nom, valeur in prog.items():
        if nom not in PROGRAMMES:
            rapport.signaler("E06", "programmes : programme inconnu '%s'" % nom,
                             regle=r.id, ligne=ligne)
        else:
            r.programmes[nom] = _lire_programme(nom, valeur, ligne, r, rapport)

    lecteur.inconnus()
    return r


# --------------------------------------------------------------------------- #
# Fichier complet
# --------------------------------------------------------------------------- #
def charger(chemin, rapport=None):
    """Lit le fichier et renvoie (Parametrage ou None, Rapport). Aucun controle croise ici."""
    rapport = rapport or Rapport()
    try:
        with open(chemin, "rb") as f:
            brut = f.read()
        texte = brut.decode("utf-8-sig")
    except OSError as e:
        rapport.signaler("E01", "fichier de parametrage illisible : %s" % e)
        return None, rapport
    except UnicodeDecodeError as e:
        rapport.signaler("E01", "le fichier n'est pas de l'UTF-8 valide : %s" % e)
        return None, rapport

    p = Parametrage(chemin)
    for numero, brute in enumerate(texte.split("\n"), 1):
        ligne = brute.strip()
        if not ligne:
            continue
        try:
            objet = analyser_json(ligne)
        except (ValueError, RecursionError) as e:
            code = "E01" if p.entete is None else "E06"
            rapport.signaler(code, "JSON invalide : %s" % e, ligne=numero)
            if p.entete is None and code == "E01":
                return None, rapport
            continue
        if p.entete is None:
            p.entete = lire_entete(objet, numero, chemin, rapport)
            if p.entete is None:
                return None, rapport
        else:
            p.regles.append(lire_regle(objet, numero, rapport))

    if p.entete is None:
        rapport.signaler("E01", "le fichier est vide : l'en-tete est obligatoire")
        return None, rapport
    return p, rapport
