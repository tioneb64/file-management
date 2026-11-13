"""Boite a outils vue du moteur : dossier des outils, index `outils.json`, variables {outil:nom} des programmes.

Un outil est un script Python dont l'en-tete (commentaires du debut du fichier) declare sa variable et ses
parametres (voir docs/13-boite-a-outils.md, section « Ecrire un nouvel outil »). Le dossier des outils est un
reglage du MOTEUR (pas d'un environnement) : il est range, avec la liste des outils trouves, dans le fichier
`outils.json` du dossier de parametrage, ecrit par l'interface apres un scan (`--scanner-outils`).
Dossier vide = le dossier `outils` a la racine du moteur.

Ce module n'importe rien d'autre du moteur : il est utilisable par le lecteur du parametrage, les controles,
l'execution des programmes et la ligne de commande.
"""
import json
import os
import re
import sys
import time

FICHIER_INDEX = "outils.json"
VERSION_INDEX = 1
RE_VARIABLE_OUTIL = re.compile(r"^\{outil:([^{}]*)\}$")
RE_NOM_OUTIL = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
LIGNES_ENTETE_MAX = 200
OCTETS_ENTETE_MAX = 65536
DOSSIERS_IGNORES = ("__pycache__",)            # plus tout dossier dont le nom commence par « _ » ou « . »


class ErreurOutils(Exception):
    """Dossier des outils ou index inutilisable (message en clair)."""


def racine_moteur():
    """Dossier qui contient le paquet `file_management` (et journal_si.py)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def dossier_par_defaut():
    return os.path.join(racine_moteur(), "outils")


# --------------------------------------------------------------------------- #
# Modele
# --------------------------------------------------------------------------- #
class Parametre(object):
    def __init__(self, forme, obligatoire, description):
        self.forme = forme                                    # ex. "--sortie ARCHIVE", "CHEMIN", "--recursif/-r"
        self.obligatoire = obligatoire
        self.description = description
        self.noms = tuple(n for n in forme.split()[0].split("/") if n)

    def en_dict(self):
        return {"forme": self.forme, "obligatoire": self.obligatoire, "description": self.description}


class Outil(object):
    def __init__(self, variable, fichier, description, parametres):
        self.variable = variable
        self.fichier = fichier                                # relatif au dossier des outils
        self.description = description
        self.parametres = parametres

    @property
    def sous_dossier(self):
        return os.path.dirname(self.fichier)

    def en_dict(self):
        return {"variable": self.variable, "fichier": self.fichier, "description": self.description,
                "parametres": [p.en_dict() for p in self.parametres]}

    @classmethod
    def depuis_dict(cls, d):
        return cls(d["variable"], d["fichier"], d.get("description", ""),
                   [Parametre(p["forme"], bool(p.get("obligatoire")), p.get("description", ""))
                    for p in d.get("parametres", [])])


# --------------------------------------------------------------------------- #
# En-tete d'un outil
# --------------------------------------------------------------------------- #
_RE_CLE = re.compile(r"^(outil|description|parametre)\s*:\s*(.*)$")
_RE_BIBLIOTHEQUE = re.compile(r"^bibliotheque\s*:\s*(.*)$")


def lire_bibliotheque(texte):
    """Un module de support (importe par les outils, jamais lance par une regle) se declare par une ligne
    `# bibliotheque: ce qu'il fournit` dans son en-tete. Renvoie (description, None), (None, None) si le fichier
    n'est pas declare ainsi, ou (None, cause) si la declaration est invalide."""
    descriptions, outils = [], 0
    for brute in texte.lstrip("\ufeff").splitlines()[:LIGNES_ENTETE_MAX]:
        if not brute.startswith("#"):
            break
        ligne = brute[1:].strip()
        m = _RE_BIBLIOTHEQUE.match(ligne)
        if m:
            descriptions.append(m.group(1).strip())
        elif ligne.startswith("outil") and _RE_CLE.match(ligne):
            outils += 1
    if not descriptions:
        return None, None
    if len(descriptions) > 1:
        return None, "en-tete invalide : plusieurs lignes '# bibliotheque:'"
    if not descriptions[0]:
        return None, "en-tete invalide : ligne '# bibliotheque:' vide (dire ce que le module fournit)"
    if outils:
        return None, "en-tete invalide : '# outil:' et '# bibliotheque:' dans le meme fichier (un module n'est pas un outil)"
    return descriptions[0], None


def lire_entete(texte, fichier=""):
    """Analyse l'en-tete d'un script. Renvoie (Outil, None) ou (None, cause) ; la cause « pas d'en-tete »
    est distincte d'un en-tete invalide."""
    lignes = []
    for brute in texte.lstrip("\ufeff").splitlines()[:LIGNES_ENTETE_MAX]:
        if not brute.startswith("#"):
            break
        lignes.append(brute[1:].strip())
    noms, description, parametres = [], [], []
    erreurs = []
    for ligne in lignes:
        m = _RE_CLE.match(ligne)
        if not m:
            continue                                          # commentaire libre
        cle, valeur = m.group(1), m.group(2).strip()
        if cle == "outil":
            noms.append(valeur)
        elif cle == "description":
            description.append(valeur)
        else:
            morceaux = [x.strip() for x in valeur.split("|", 2)]
            if len(morceaux) != 3 or not morceaux[0] or morceaux[1] not in ("obligatoire", "facultatif"):
                erreurs.append("ligne '# parametre:' invalide (attendu : forme | obligatoire ou facultatif | "
                               "description) : %s" % ligne)
            else:
                parametres.append(Parametre(morceaux[0], morceaux[1] == "obligatoire", morceaux[2]))
    if not noms:
        return None, "pas d'en-tete d'outil (ligne '# outil: nom' absente)"
    if len(noms) > 1:
        return None, "en-tete invalide : plusieurs lignes '# outil:'"
    nom = noms[0]
    if not RE_NOM_OUTIL.match(nom):
        return None, ("en-tete invalide : nom d'outil '%s' refuse (minuscules, chiffres et _, commence par une "
                      "lettre, 64 caracteres au plus)" % nom)
    if not description or not description[0]:
        erreurs.append("ligne '# description:' absente ou vide")
    if len(description) > 1:
        erreurs.append("plusieurs lignes '# description:'")
    vus = set()
    for p in parametres:
        for n in p.noms:
            if n in vus:
                erreurs.append("parametre declare deux fois : %s" % n)
            vus.add(n)
    if erreurs:
        return None, "en-tete invalide : " + " ; ".join(erreurs)
    return Outil(nom, fichier, description[0], parametres), None


# --------------------------------------------------------------------------- #
# Scan du dossier des outils
# --------------------------------------------------------------------------- #
class Scan(object):
    def __init__(self, dossier):
        self.dossier = dossier
        self.outils = []                    # Outil, tries par variable
        self.non_retenus = []               # {"fichier": relatif, "cause": texte}
        self.bibliotheques = []             # {"fichier": relatif, "description": texte} : modules de support, hors index
        self.erreurs = []                   # {"chemin": ..., "message": ...} dossiers illisibles
        self.fichiers_python = 0
        self.dossiers = 0

    def en_dict(self):
        return {"dossier": self.dossier, "outils": [o.en_dict() for o in self.outils],
                "non_retenus": list(self.non_retenus), "bibliotheques": list(self.bibliotheques),
                "erreurs": list(self.erreurs),
                "fichiers_python": self.fichiers_python, "dossiers": self.dossiers}


def _est_lien(chemin):
    est_jonction = getattr(os.path, "isjunction", None)
    return os.path.islink(chemin) or bool(est_jonction and est_jonction(chemin))


def _ignorer_dossier(nom):
    return nom in DOSSIERS_IGNORES or nom.startswith("_") or nom.startswith(".")


def scanner(dossier):
    """Parcourt `dossier` et ses sous-dossiers ; un .py est un outil s'il a un en-tete valide et une variable
    libre. Leve ErreurOutils si le dossier est introuvable."""
    dossier = os.path.abspath(dossier)
    if not os.path.isdir(dossier):
        raise ErreurOutils("dossier des outils introuvable : %s" % dossier)
    scan = Scan(dossier)
    prises = {}
    erreurs_marche = []
    for courant, sous, fichiers in os.walk(dossier, onerror=erreurs_marche.append):
        sous[:] = sorted(d for d in sous if not _ignorer_dossier(d) and not _est_lien(os.path.join(courant, d)))
        scan.dossiers += 1
        for nom in sorted(fichiers):
            if not nom.lower().endswith(".py") or nom == "__init__.py":
                continue
            scan.fichiers_python += 1
            chemin = os.path.join(courant, nom)
            relatif = os.path.relpath(chemin, dossier)
            try:
                with open(chemin, "rb") as f:
                    texte = f.read(OCTETS_ENTETE_MAX).decode("utf-8")
            except UnicodeDecodeError:
                scan.non_retenus.append({"fichier": relatif, "cause": "fichier illisible : UTF-8 attendu"})
                continue
            except OSError as e:
                scan.non_retenus.append({"fichier": relatif, "cause": "fichier illisible : %s" % (e.strerror or e)})
                continue
            description, cause = lire_bibliotheque(texte)
            if description is not None:
                scan.bibliotheques.append({"fichier": relatif, "description": description})
                continue
            if cause is not None:
                scan.non_retenus.append({"fichier": relatif, "cause": cause})
                continue
            outil, cause = lire_entete(texte, relatif)
            if outil is None:
                scan.non_retenus.append({"fichier": relatif, "cause": cause})
            elif outil.variable in prises:
                scan.non_retenus.append({"fichier": relatif, "cause": "la variable {outil:%s} est deja prise par %s"
                                         % (outil.variable, prises[outil.variable])})
            else:
                prises[outil.variable] = relatif
                scan.outils.append(outil)
    for e in erreurs_marche:
        scan.erreurs.append({"chemin": str(e.filename), "message": "dossier illisible : %s" % (e.strerror or e)})
    scan.outils.sort(key=lambda o: o.variable)
    return scan


def contenu_index(scan, dossier_configure="", utilisateur="", maintenant=None):
    """Texte exact du fichier outils.json (UTF-8, une indentation d'un espace)."""
    document = {"version": VERSION_INDEX, "dossier_outils": dossier_configure or "", "dossier_resolu": scan.dossier,
                "scanne_le": time.strftime("%Y-%m-%dT%H:%M:%S", maintenant or time.localtime()),
                "scanne_par": utilisateur or "", "outils": [o.en_dict() for o in scan.outils]}
    return json.dumps(document, ensure_ascii=False, indent=1) + "\n"


# --------------------------------------------------------------------------- #
# Index ecrit par l'interface, lu par le moteur
# --------------------------------------------------------------------------- #
class Index(object):
    def __init__(self, chemin, dossier_configure, outils, scanne_le="", scanne_par="", dossier_resolu=""):
        self.chemin = chemin                                  # chemin d'outils.json
        self.dossier_configure = dossier_configure            # '' = dossier par defaut
        self.outils = {o.variable: o for o in outils}
        self.scanne_le = scanne_le
        self.scanne_par = scanne_par
        self.dossier_resolu = dossier_resolu

    @property
    def dossier(self):
        """Dossier a utiliser MAINTENANT : celui du reglage, ou le dossier `outils` du moteur si le reglage est vide."""
        return self.dossier_configure or dossier_par_defaut()

    def chemin_outil(self, outil):
        return os.path.join(self.dossier, outil.fichier)


def chemin_index(dossier_parametrage):
    return os.path.join(dossier_parametrage, FICHIER_INDEX)


def charger_index(dossier_parametrage):
    """Index du dossier de parametrage, ou None s'il n'existe pas. Leve ErreurOutils s'il est illisible."""
    chemin = chemin_index(dossier_parametrage)
    try:
        with open(chemin, "rb") as f:
            document = json.loads(f.read().decode("utf-8-sig"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise ErreurOutils("%s illisible : %s" % (FICHIER_INDEX, e))
    try:
        if document.get("version") != VERSION_INDEX:
            raise ErreurOutils("%s : version %r non prise en charge (attendu : %d)"
                               % (FICHIER_INDEX, document.get("version"), VERSION_INDEX))
        outils = [Outil.depuis_dict(o) for o in document["outils"]]
        return Index(chemin, document.get("dossier_outils") or "", outils, document.get("scanne_le", ""),
                     document.get("scanne_par", ""), document.get("dossier_resolu", ""))
    except ErreurOutils:
        raise
    except (KeyError, TypeError, AttributeError) as e:
        raise ErreurOutils("%s : contenu invalide (%s)" % (FICHIER_INDEX, e))


_CACHE = {}


def index_de(dossier_parametrage):
    """charger_index avec un cache (un lancement lit l'index une fois) ; invalide si le fichier change."""
    chemin = chemin_index(dossier_parametrage)
    try:
        info = os.stat(chemin)
        cle = (info.st_mtime_ns, info.st_size)
    except OSError:
        cle = None
    precedent = _CACHE.get(chemin)
    if precedent is not None and precedent[0] == cle:
        return precedent[1]
    index = charger_index(dossier_parametrage)
    _CACHE[chemin] = (cle, index)
    return index


# --------------------------------------------------------------------------- #
# Variables {outil:nom} d'une commande
# --------------------------------------------------------------------------- #
def variable_outil(element):
    """'{outil:zip_creer}' -> 'zip_creer' ; None si l'element n'est pas une variable d'outil seule."""
    m = RE_VARIABLE_OUTIL.match(element)
    return m.group(1) if m else None


def resoudre(variable, index):
    """Renvoie (liste d'elements de commande, None) ou (None, message d'erreur) pour `{outil:variable}`."""
    if index is None:
        return None, ("outil {outil:%s} introuvable : aucun index des outils (%s absent du dossier de parametrage) ; "
                      "scanner le dossier des outils dans l'interface (onglet Outils)" % (variable, FICHIER_INDEX))
    outil = index.outils.get(variable)
    if outil is None:
        connus = ", ".join(sorted(index.outils)) or "aucun"
        return None, "outil inconnu : {outil:%s} (outils indexes : %s)" % (variable, connus)
    chemin = index.chemin_outil(outil)
    if not os.path.isfile(chemin):
        return None, ("le fichier de l'outil {outil:%s} est introuvable : %s (dossier des outils deplace ou fichier "
                      "supprime : scanner de nouveau)" % (variable, chemin))
    return [sys.executable, chemin], None


def parametres_manquants(outil, elements):
    """Parametres obligatoires (options '-...') de `outil` absents des `elements` de la commande."""
    presents = set()
    for e in elements:
        presents.add(e)
        if e.startswith("-") and "=" in e:
            presents.add(e.split("=", 1)[0])
    return [p.forme for p in outil.parametres
            if p.obligatoire and p.noms and p.noms[0].startswith("-") and not (set(p.noms) & presents)]


def controler_programmes(parametrage, rapport, verifier_fichiers=False):
    """Controle G01 des programmes qui appellent un outil : index present, outil connu, parametres
    obligatoires donnes, et (verifier_fichiers) fichier de l'outil present. L'index n'est lu que si une
    commande utilise {outil:...}."""
    index, erreur, charge = None, None, False
    dossier = os.path.dirname(os.path.abspath(parametrage.chemin))
    for r in parametrage.regles:
        for point, programme in r.programmes.items():
            variable = getattr(programme, "outil", None)
            if programme is None or variable is None:
                continue
            if not charge:
                charge = True
                try:
                    index = index_de(dossier)
                except ErreurOutils as e:
                    erreur = str(e)

            def signaler(message, point=point, r=r):
                rapport.signaler("G01", "programmes.%s.commande : %s" % (point, message), regle=r.etiquette,
                                 ligne=r.ligne)
            if erreur:
                signaler(erreur)
                continue
            argv, message = resoudre(variable, index)
            if argv is None and (verifier_fichiers or index is None or variable not in index.outils):
                signaler(message)
                continue
            outil = index.outils[variable]
            for forme in parametres_manquants(outil, programme.commande[1:]):
                signaler("le parametre %s de l'outil {outil:%s} est obligatoire" % (forme, variable))
