"""Lecture du fichier de parametrage (JSON Lines) : modele, types, valeurs de secours.

Les controles qui comparent plusieurs regles entre elles sont dans controles.py.
Specification : docs/01-parametrage.md.
"""
import json
import os
import re

from file_management.diagnostic import Rapport
from file_management.outils import RE_NOM_OUTIL, variable_outil

VERSION_FORMAT = 1

RE_ENVIRONNEMENT = re.compile(r"^[a-z0-9_-]{1,32}$")
# Codes d'environnement de la plateforme d'observabilite (journal) : aucune autre valeur n'est admise.
CODES_ENVIRONNEMENT = ("dev", "build", "test", "pprod", "prod", "run", "int")
ALIAS_CODES_ENVIRONNEMENT = {"production": "prod", "preprod": "pprod", "preproduction": "pprod",
                             "pre-prod": "pprod", "recette": "test", "developpement": "dev",
                             "integration": "int"}


def deduire_code_environnement(nom):
    """Code de la plateforme d'apres le nom de l'environnement (production -> prod), ou None."""
    nom = (nom or "").strip().lower()
    return nom if nom in CODES_ENVIRONNEMENT else ALIAS_CODES_ENVIRONNEMENT.get(nom)
RE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
RE_HEURE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
RE_MODIFIE_DEPUIS = re.compile(r"^(TOUT|J|J-(\d+))$")

MODES = ("copie", "deplacement", "archivage", "suppression", "count", "size", "synchro")
MODES_TRANSFERT = ("copie", "deplacement", "archivage")     # ces modes ont une cible
MODES_MESURE = ("count", "size")                            # ces modes comptent, sans rien toucher
MODE_SYNCHRO = "synchro"           # aucun dossier : retourne seulement un statut (apres des dependances)
# Champs sans objet pour le mode synchro : les dossiers sont refuses, le reste est ignore (R16).
CHAMPS_DOSSIERS_SYNCHRO = ("source", "cible", "archive", "dossier_temporaire")
CHAMPS_FICHIERS_SYNCHRO = ("creer_dossiers", "horodater", "selection", "fichier_declencheur",
                           "consommer_declencheur", "temoin_cible", "seuil_minimum", "seuil_maximum",
                           "identite", "retention_historique_jours", "retention_journaux_jours",
                           "retention_archive_jours", "si_cible_absente", "si_existe_cible",
                           "si_existe_archive", "renommage_cible", "renommage_archive")
POINTS_SANS_OBJET_SYNCHRO = ("apres_fichier", "apres_lot")  # rien ne s'execute apres : on previent
MODES_HORODATAGE = ("copie", "archivage")                   # seuls modes ou `horodater` a un sens
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
_COMMUNES = ("environnement", "regle", "source", "cible", "archive", "date")
_FICHIER = ("fichier", "nom", "fichier_cible")
_LISTE = ("liste", "liste_json")
# {fichier} n'a de sens qu'autour d'un fichier, {liste} qu'autour d'un lot
VARIABLES_PAR_POINT = {"avant_lot": _COMMUNES + _LISTE, "avant_fichier": _COMMUNES + _FICHIER,
                       "apres_fichier": _COMMUNES + _FICHIER, "apres_lot": _COMMUNES + _LISTE,
                       "sur_erreur": _COMMUNES + _LISTE, "reprise": _COMMUNES}
# Mode synchro : ni dossier ni fichier, donc seulement l'environnement, la regle et la date
VARIABLES_SYNCHRO = ("environnement", "regle", "date")

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
        self.code_environnement = None            # code de la plateforme d'observabilite (journal)
        self.racine = None                        # dossier racine de l'environnement (chemins relatifs)
        self.racine_source = None                 # racine des dossiers source des regles
        self.racine_cible = None                  # racine des dossiers cible des regles
        self.base = ""
        self.dossier_logs = None
        self.dossier_travail = None
        self.parallele_max = None
        self.retention_executions_jours = 365
        self.retention_journaux_jours = None      # None : les journaux ne sont jamais purges
        self.marge_espace_mo = 64
        self.suspendu = False                     # maintenance : aucune regle n'est lancee
        self.motif_suspension = None
        self.dossier_parametrage = None           # dossier du fichier lu (la, outils.json : index des outils)


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
        self.limite_octets = None        # volume maximum d'un lot (le premier fichier est toujours pris)

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
    def __init__(self, commande, timeout_sec, outil=None):
        self.commande = commande
        self.timeout_sec = timeout_sec
        self.outil = outil              # variable d'outil ({outil:nom}) du premier element, ou None


class Regle(object):
    def __init__(self, ligne):
        self.ligne = ligne
        self.brut = ""
        self.id = None
        self.description = ""
        self.actif = True
        self.source = None
        self.cible = None
        self.mode = None
        self.archive = None
        self.seuil_minimum = None                 # modes count / size : bornes de la valeur mesuree
        self.seuil_maximum = None
        self.creer_dossiers = True
        self.horodater = False                    # copie / archivage : marque chaque fichier traite d'un horodatage
        self.fichier_declencheur = None           # nom ou masque d'un fichier temoin (.ok) attendu dans la source
        self.consommer_declencheur = True         # le temoin est supprime quand le lot est entierement traite
        self.temoin_cible = None                  # nom du fichier temoin depose dans la cible apres chaque lot livre
        self.dossier_temporaire = None
        self.selection = Selection()
        self.identite = "version"
        self.retention_historique_jours = 90
        self.retention_journaux_jours = None      # None : valeur de l'en-tete, sinon jamais purges
        self.retention_archive_jours = None       # None : l'archive n'est jamais purgee
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


def est_absolu(chemin):
    """Chemin complet : lettre de lecteur suivie d'un separateur, partage reseau, ou absolu pour le systeme."""
    c = chemin.strip()
    return bool(re.match(r"^[A-Za-z]:[\\/]", c)) or est_chemin_reseau(c) \
        or (os.name != "nt" and os.path.isabs(c))


def resoudre_chemin(chemin, racine):
    """Chemin complet d'un chemin saisi : un chemin complet est conserve tel quel, un chemin partiel
    est place sous `racine` (avec ou sans separateur final). Sans racine, le chemin reste inchange."""
    if not chemin or not chemin.strip() or not racine or not racine.strip():
        return chemin
    if est_absolu(os.path.expandvars(chemin)):
        return chemin
    return os.path.normpath(os.path.join(racine.strip(), chemin.strip().lstrip("\\/")))


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
    e.dossier_parametrage = os.path.dirname(os.path.abspath(chemin_fichier))
    lecteur = Lecteur(objet, rapport, ligne, contexte="")
    lecteur.valeur("version", "entier", VERSION_FORMAT)
    e.environnement = lecteur.valeur("environnement", "texte", "")
    e.code_environnement = lecteur.valeur("code_environnement", "texte_ou_null", None)
    e.racine = lecteur.valeur("racine", "texte_ou_null", None)
    e.racine_source = lecteur.valeur("racine_source", "texte_ou_null", None)
    e.racine_cible = lecteur.valeur("racine_cible", "texte_ou_null", None)
    e.base = lecteur.valeur("base", "texte", "")
    e.dossier_logs = lecteur.valeur("dossier_logs", "texte_ou_null", None)
    e.dossier_travail = lecteur.valeur("dossier_travail", "texte_ou_null", None)
    e.parallele_max = lecteur.entier("parallele_max", None, minimum=1, nullable=True)
    e.retention_executions_jours = lecteur.entier("retention_executions_jours", 365, minimum=1)
    e.retention_journaux_jours = lecteur.entier("retention_journaux_jours", None, minimum=1, nullable=True)
    e.marge_espace_mo = lecteur.entier("marge_espace_mo", 64, minimum=0)
    e.suspendu = lecteur.valeur("suspendu", "booleen", False)
    e.motif_suspension = (lecteur.valeur("motif_suspension", "texte_ou_null", None) or "").strip() or None
    lecteur.inconnus()

    nom_fichier = os.path.splitext(os.path.basename(chemin_fichier))[0]
    if "environnement" not in objet or not RE_ENVIRONNEMENT.match(e.environnement):
        rapport.signaler("E03", "environnement absent ou invalide (attendu : minuscules, chiffres, "
                         "_ et -, 32 caracteres maximum)", ligne=ligne)
    elif e.environnement != nom_fichier:
        rapport.signaler("E03", "l'environnement '%s' doit etre egal au nom du fichier '%s'"
                         % (e.environnement, nom_fichier), ligne=ligne)

    # Code d'environnement de la plateforme : explicite, sinon deduit du nom (production -> prod)
    code = (e.code_environnement or "").strip() or None
    if code is not None and code not in CODES_ENVIRONNEMENT:
        rapport.signaler("E08", "code_environnement '%s' hors de la liste de la plateforme (%s)"
                         % (code, ", ".join(CODES_ENVIRONNEMENT)), ligne=ligne)
        code = None
    elif code is None and RE_ENVIRONNEMENT.match(e.environnement or ""):
        code = deduire_code_environnement(e.environnement)
        if code is None:
            rapport.signaler("E08", "code_environnement absent et non deductible du nom '%s' (valeurs : %s)"
                             % (e.environnement, ", ".join(CODES_ENVIRONNEMENT)), ligne=ligne)
    e.code_environnement = code

    # Racines : la racine de l'environnement doit etre un chemin complet ; les racines des sources et des
    # cibles peuvent etre partielles (elles se placent alors sous la racine de l'environnement).
    e.racine = (e.racine or "").strip() or None
    if e.racine and not est_absolu(os.path.expandvars(e.racine)):
        rapport.signaler("E07", "racine : '%s' n'est pas un chemin complet (exemple : D:\\Transferts\\preprod)"
                         % e.racine, ligne=ligne)
        e.racine = None
    for nom in ("racine_source", "racine_cible"):
        valeur = (getattr(e, nom) or "").strip() or None
        valeur = resoudre_chemin(valeur, e.racine) if valeur else None
        if valeur and not est_absolu(os.path.expandvars(valeur)):
            rapport.signaler("E07", "%s : '%s' n'est pas un chemin complet et il n'y a pas de racine de "
                             "l'environnement pour le completer" % (nom, valeur), ligne=ligne)
            valeur = None
        setattr(e, nom, valeur)
    for nom in ("base", "dossier_logs", "dossier_travail"):
        valeur = getattr(e, nom)
        if valeur and valeur.strip():
            complet = resoudre_chemin(valeur, e.racine)
            if not est_absolu(os.path.expandvars(complet)):
                rapport.signaler("E07", "%s : '%s' n'est pas un chemin complet et il n'y a pas de racine de "
                                 "l'environnement pour le completer" % (nom, valeur), ligne=ligne)
            setattr(e, nom, complet)

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
    s.limite_octets = lecteur.entier("limite_octets", None, minimum=1, nullable=True)
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
    outil = None
    if "commande" not in valeur:
        lecteur.signaler("G01", "programmes.%s.commande est obligatoire" % nom)
    elif not (isinstance(commande, list) and commande
              and all(isinstance(c, str) and c.strip() for c in commande)):
        lecteur.signaler("G01", "programmes.%s.commande : un tableau non vide de textes non vides "
                         "est attendu (pas une chaine)" % nom)
        commande = None
    else:
        autorisees = VARIABLES_SYNCHRO if regle.mode == MODE_SYNCHRO else VARIABLES_PAR_POINT[nom]
        premier = commande[0]
        if premier.startswith("{outil:"):
            outil = variable_outil(premier)
            if outil is None:
                lecteur.signaler("G01", "programmes.%s.commande : {outil:...} doit etre seul dans le premier element "
                                 "(%s)" % (nom, premier))
            elif not RE_NOM_OUTIL.match(outil):
                lecteur.signaler("G01", "programmes.%s.commande : nom d'outil invalide dans %s (minuscules, chiffres "
                                 "et _)" % (nom, premier))
        for position, element in enumerate(commande):
            if "{outil:" in element and not (position == 0 and premier.startswith("{outil:")):
                lecteur.signaler("G01", "programmes.%s.commande : {outil:...} n'est permis que comme premier "
                                 "element de la commande (%s)" % (nom, element))
                continue
            if position == 0 and premier.startswith("{outil:"):
                continue
            for variable in variables_inconnues(element, autorisees):
                lecteur.signaler("G01", "programmes.%s.commande : variable {%s} inconnue ou sans objet a ce "
                                 "point d'appel (autorisees : %s)"
                                 % (nom, variable, ", ".join(autorisees)))
    timeout = valeur.get("timeout_sec")
    if "timeout_sec" not in valeur:
        lecteur.signaler("G01", "programmes.%s.timeout_sec est obligatoire" % nom)
    elif not _est_entier(timeout) or timeout <= 0:
        lecteur.signaler("G01", "programmes.%s.timeout_sec doit etre un entier superieur a 0" % nom)
        timeout = None
    lecteur.inconnus()
    if commande is None or timeout is None:
        return None
    return Programme(tuple(commande), timeout, outil)


def lire_regle(objet, ligne, rapport, entete=None):
    """Construit une regle depuis un objet JSON. Les valeurs erronees sont remplacees par leur
    valeur de secours : la regle reste exploitable par les controles croises, le rapport porte
    les refus. `entete` : fournit les racines qui completent les chemins partiels (source, cible,
    dossier temporaire) ; sans entete, les chemins restent tels que saisis."""
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
    r.mode = lecteur.choix("mode", MODES, None, obligatoire=True)
    synchro = r.mode == MODE_SYNCHRO
    r.source = lecteur.valeur("source", "texte_ou_null" if synchro else "texte", None, obligatoire=not synchro)
    r.cible = lecteur.valeur("cible", "texte_ou_null", None)
    transfert = r.mode is None or r.mode in MODES_TRANSFERT      # mode inconnu : on ne dit rien de plus
    if r.cible is None and transfert and "cible" not in objet:
        lecteur.signaler("R01", "champ obligatoire absent : cible")
    elif r.cible is None and transfert:
        lecteur.signaler("E06", "cible : un texte attendu")
    for nom in ("source", "cible"):
        if getattr(r, nom) is not None and not getattr(r, nom).strip():
            if (nom == "source" and not synchro) or transfert:
                lecteur.signaler("R01", "champ obligatoire vide : %s" % nom)
            setattr(r, nom, None)
    r.archive = lecteur.valeur("archive", "texte_ou_null", None)
    r.creer_dossiers = lecteur.valeur("creer_dossiers", "booleen", True)
    r.horodater = lecteur.valeur("horodater", "booleen", False)
    r.dossier_temporaire = lecteur.valeur("dossier_temporaire", "texte_ou_null", None)
    r.fichier_declencheur = (lecteur.valeur("fichier_declencheur", "texte_ou_null", None) or "").strip() or None
    r.consommer_declencheur = lecteur.valeur("consommer_declencheur", "booleen", True)
    if r.fichier_declencheur and any(c in r.fichier_declencheur for c in "\\/;:"):
        lecteur.signaler("R06", "fichier_declencheur : un nom ou un masque de fichier de la source (exemple : "
                         "*.ok), sans chemin ni point-virgule")
        r.fichier_declencheur = None
    r.temoin_cible = (lecteur.valeur("temoin_cible", "texte_ou_null", None) or "").strip() or None
    if r.temoin_cible and any(c in r.temoin_cible for c in "\\/;:*?"):
        lecteur.signaler("R06", "temoin_cible : un nom de fichier fixe (exemple : fin.ok), sans chemin, "
                         "masque ni point-virgule")
        r.temoin_cible = None
    r.seuil_minimum = lecteur.entier("seuil_minimum", None, minimum=0, nullable=True)
    r.seuil_maximum = lecteur.entier("seuil_maximum", None, minimum=0, nullable=True)
    if synchro:
        _controler_synchro(lecteur, objet, r)

    # Chemins partiels : places sous la racine des sources / des cibles (ou de l'environnement)
    if entete is not None:
        for nom, racine in (("source", entete.racine_source or entete.racine),
                            ("cible", entete.racine_cible or entete.racine),
                            ("dossier_temporaire", entete.racine)):
            valeur = getattr(r, nom)
            if not valeur or not valeur.strip():
                continue
            complet = resoudre_chemin(valeur, racine)
            if not est_absolu(os.path.expandvars(complet)):
                lecteur.signaler("R14", "%s : '%s' n'est pas un chemin complet et l'en-tete n'a pas de racine "
                                 "pour le completer" % (nom, valeur))
            setattr(r, nom, complet)

    if r.mode == "archivage" and not (r.archive and r.archive.strip()):
        lecteur.signaler("R04", "le mode archivage impose le champ 'archive'")
    elif r.archive and r.mode in ("copie", "deplacement") + ("suppression",) + MODES_MESURE:
        lecteur.signaler("R05", "'archive' est renseigne mais le mode est '%s' : il sera ignore"
                         % r.mode)
    if r.horodater and r.mode is not None and r.mode not in MODES_HORODATAGE and not synchro:
        lecteur.signaler("R16", "'horodater' n'a de sens que pour les modes copie et archivage : "
                         "il sera ignore (mode '%s')" % r.mode)
    if r.temoin_cible and r.mode is not None and r.mode not in MODES_TRANSFERT and not synchro:
        lecteur.signaler("R16", "'temoin_cible' n'a de sens que pour les modes copie, deplacement et archivage : "
                         "il sera ignore (mode '%s')" % r.mode)
    if r.mode in ("suppression",) + MODES_MESURE and r.cible:
        lecteur.signaler("R16", "'cible' est renseignee mais le mode est '%s' : elle sera ignoree" % r.mode)
    if r.mode == "suppression":
        s = lecteur.objet.get("selection") if isinstance(lecteur.objet.get("selection"), dict) else {}
        borne = any(s.get(c) for c in ("age_minimum_sec", "age_maximum_sec")) \
            or str(s.get("modifie_depuis", "TOUT")).upper() != "TOUT"
        lecteur.signaler("R15", "mode suppression : les fichiers selectionnes seront supprimes DEFINITIVEMENT"
                         + ("" if borne else " (aucun critere d'age ni de date : tous les fichiers du masque "
                            "seront supprimes a chaque lancement)"))
    if r.mode in MODES_MESURE:
        if r.seuil_minimum is not None and r.seuil_maximum is not None and r.seuil_minimum > r.seuil_maximum:
            lecteur.signaler("R07", "seuil_minimum (%d) doit etre inferieur ou egal a seuil_maximum (%d)"
                             % (r.seuil_minimum, r.seuil_maximum))
    elif (r.seuil_minimum is not None or r.seuil_maximum is not None) and not synchro:
        lecteur.signaler("R16", "seuil_minimum / seuil_maximum n'ont de sens que pour les modes count et size : "
                         "ils seront ignores")
    if r.archive:
        for v in variables_inconnues(r.archive, VARIABLES_DATE):
            lecteur.signaler("R12", "archive : variable inconnue {%s}" % v)

    sel = lecteur.valeur("selection", "objet", None)
    if sel is not None:
        r.selection = _lire_selection(sel, ligne, r, rapport)

    r.identite = lecteur.choix("identite", IDENTITES, "version")
    r.retention_historique_jours = lecteur.entier("retention_historique_jours", 90, minimum=1)
    r.retention_journaux_jours = lecteur.entier("retention_journaux_jours", None, minimum=1, nullable=True)
    r.retention_archive_jours = lecteur.entier("retention_archive_jours", None, minimum=1, nullable=True)
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
        if synchro and r.planification.type in TYPES_PLANIFICATION \
                and r.planification.type != "apres_dependances":
            lecteur.signaler("P01", "mode synchro : pas d'heure de debut ni de fin, seule la planification "
                             "'apres_dependances' est admise (et la regle a besoin d'une liste 'apres')")

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
    if synchro:
        inutiles = _fichiers_ignores_synchro(r)
        if inutiles:
            lecteur.signaler("R16", "mode synchro : champ(s) sans effet, ignore(s) : %s" % ", ".join(inutiles))
        for nom in POINTS_SANS_OBJET_SYNCHRO:
            if prog.get(nom) is not None:
                lecteur.signaler("R18", "programmes.%s ne sera jamais execute : le mode synchro lance seulement "
                                 "avant_lot puis avant_fichier, puis rend son statut" % nom)

    lecteur.inconnus()
    return r


def _controler_synchro(lecteur, objet, r):
    """Mode synchro : aucun dossier (refus), aucun champ de fichiers (ignores, avertissement)."""
    dossiers = [n for n in CHAMPS_DOSSIERS_SYNCHRO if isinstance(objet.get(n), str) and objet[n].strip()]
    if dossiers:
        lecteur.signaler("R17", "mode synchro : aucun dossier n'est admis (%s), la regle retourne seulement "
                         "un statut" % ", ".join(dossiers))
    r.source = r.cible = r.archive = r.dossier_temporaire = None


def _fichiers_ignores_synchro(r):
    """Champs de fichiers dont la valeur n'est pas celle par defaut : le formulaire de l'interface
    envoie tous les champs avec leurs valeurs par defaut, qui ne doivent pas faire d'avertissement."""
    defaut = Regle(0)
    inutiles = []
    for nom in CHAMPS_FICHIERS_SYNCHRO:
        if nom == "selection":
            if vars(r.selection) != vars(defaut.selection):
                inutiles.append(nom)
        elif getattr(r, nom) != getattr(defaut, nom):
            inutiles.append(nom)
    return inutiles


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
            regle = lire_regle(objet, numero, rapport, p.entete)
            regle.brut = ligne
            p.regles.append(regle)

    if p.entete is None:
        rapport.signaler("E01", "le fichier est vide : l'en-tete est obligatoire")
        return None, rapport
    return p, rapport
