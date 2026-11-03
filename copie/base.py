"""Base SQLite d'un environnement : etat des regles, executions, empreintes des fichiers livres,
actions en attente, journal des actions d'exploitation.

Specification : docs/03-base-de-donnees.md. Une connexion par processus, transactions courtes
(BEGIN IMMEDIATE), disque local obligatoire, instants en secondes UTC.
"""
import contextlib
import hashlib
import os
import sqlite3
import time
import unicodedata
from datetime import datetime

from copie import __version__

VERSION_SCHEMA = 1
BUSY_TIMEOUT_MS = 30000
SECONDES_PAR_JOUR = 86400

# etats d'un fichier (table fichiers)
INTENTION, LIVRE, TERMINE, INCERTAIN = 1, 2, 3, 9
STATUTS_EXECUTION = ("SUCCES", "WARNING", "ERREUR", "ARRETEE")
TYPES_ACTION = ("livraison", "suppression", "archivage")


class ErreurBase(Exception):
    """Erreur de base de donnees : on ne traite rien (garantie G6)."""


class BaseAbsente(ErreurBase):
    pass


class BaseExiste(ErreurBase):
    pass


class BaseIncoherente(ErreurBase):
    """Fichier qui n'est pas une base de ce programme, ou base d'un autre environnement."""


class BaseTropRecente(ErreurBase):
    pass


class BaseIndisponible(ErreurBase):
    """Base verrouillee au-dela du delai d'attente : evenement `base_indisponible`."""


class BaseSurReseau(ErreurBase):
    """SQLite en mode WAL n'est pas fiable sur un partage reseau."""


class TransitionInvalide(ErreurBase):
    """Changement d'etat d'un fichier qui ne respecte pas le cycle INTENTION > LIVRE > TERMINE."""


# --------------------------------------------------------------------------- #
# Schema (version 1) : docs/03-base-de-donnees.md, section 3
# --------------------------------------------------------------------------- #
SCHEMA_V1 = """
CREATE TABLE meta (
  cle    TEXT PRIMARY KEY,
  valeur TEXT NOT NULL
);

CREATE TABLE regles (
  no                       INTEGER PRIMARY KEY AUTOINCREMENT,
  id                       TEXT NOT NULL UNIQUE COLLATE NOCASE,
  cree_le                  INTEGER NOT NULL,
  empreinte_parametres     TEXT,
  en_cours                 INTEGER NOT NULL DEFAULT 0,
  execution_id             INTEGER,
  pid                      INTEGER,
  pid_cree_le              INTEGER,
  hote                     TEXT,
  build                    TEXT,
  debut_traitement         INTEGER,
  dernier_lancement        INTEGER,
  dernier_creneau          INTEGER,
  dernier_fin              INTEGER,
  dernier_statut           TEXT NOT NULL DEFAULT 'JAMAIS_LANCEE',
  dernier_statut_le        INTEGER,
  dernier_motif            TEXT,
  dernier_succes           INTEGER,
  derniere_erreur_le       INTEGER,
  derniere_erreur_situation TEXT,
  derniere_erreur_message  TEXT,
  attente                  TEXT,
  attente_motif            TEXT,
  attente_depuis           INTEGER,
  reprise                  INTEGER NOT NULL DEFAULT 0,
  reprise_par              TEXT,
  reprise_le               INTEGER,
  lancement_manuel         INTEGER NOT NULL DEFAULT 0,
  arret_apres_erreur       INTEGER NOT NULL DEFAULT 0,
  relances                 INTEGER NOT NULL DEFAULT 0,
  archivage_degrade        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE executions (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  regle_no         INTEGER NOT NULL REFERENCES regles(no),
  declencheur      TEXT NOT NULL,
  debut            INTEGER NOT NULL,
  fin              INTEGER,
  statut           TEXT,
  situation_finale TEXT,
  nb_selectionnes  INTEGER NOT NULL DEFAULT 0,
  nb_livres        INTEGER NOT NULL DEFAULT 0,
  nb_ignores       INTEGER NOT NULL DEFAULT 0,
  nb_erreurs       INTEGER NOT NULL DEFAULT 0,
  nb_en_attente    INTEGER NOT NULL DEFAULT 0,
  octets_livres    INTEGER NOT NULL DEFAULT 0,
  hote             TEXT,
  pid              INTEGER,
  build            TEXT,
  simulation       INTEGER NOT NULL DEFAULT 0,
  message          TEXT
);
CREATE INDEX ix_executions_regle ON executions (regle_no, id DESC);

CREATE TABLE fichiers (
  cle       BLOB PRIMARY KEY,
  regle_no  INTEGER NOT NULL,
  etat      INTEGER NOT NULL,
  vu_jour   INTEGER NOT NULL,
  livre_le  INTEGER
) WITHOUT ROWID;

CREATE TABLE actions_en_attente (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  regle_no         INTEGER NOT NULL REFERENCES regles(no),
  cle              BLOB NOT NULL UNIQUE,
  type             TEXT NOT NULL,
  chemin_source    TEXT NOT NULL,
  chemin_cible     TEXT,
  chemin_archive   TEXT,
  taille           INTEGER,
  mtime_ns         INTEGER,
  sha256           TEXT,
  cree_le          INTEGER NOT NULL,
  tentatives       INTEGER NOT NULL DEFAULT 0,
  derniere_tentative INTEGER,
  dernier_message  TEXT
);
CREATE INDEX ix_actions_regle ON actions_en_attente (regle_no, id);

CREATE TABLE journal_actions (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  regle_no     INTEGER,
  action       TEXT NOT NULL,
  utilisateur  TEXT NOT NULL,
  commentaire  TEXT,
  demandee_le  INTEGER NOT NULL,
  resultat     TEXT
);
"""

# version de depart -> liste d'instructions SQL (ou fonction recevant la connexion)
MIGRATIONS = {}


# --------------------------------------------------------------------------- #
# Empreintes (docs/03, section 4.1)
# --------------------------------------------------------------------------- #
def normaliser_chemin_relatif(chemin):
    """NFC, separateurs uniformises (\\), minuscules : meme fichier = meme texte."""
    return unicodedata.normalize("NFC", chemin).replace("/", "\\").lower()


def _condenser(*champs):
    h = hashlib.blake2b(digest_size=16)
    h.update("\x1f".join(champs).encode("utf-8", "surrogatepass"))
    return h.digest()


def cle_version(regle_id, chemin_relatif, taille, mtime_ns):
    """Genre V : meme nom, meme taille, meme date de modification."""
    return _condenser("V", regle_id.lower(), normaliser_chemin_relatif(chemin_relatif),
                      str(taille), str(mtime_ns))


def cle_contenu(regle_id, chemin_relatif, sha256):
    """Genre C : meme nom, meme contenu (SHA-256)."""
    return _condenser("C", regle_id.lower(), normaliser_chemin_relatif(chemin_relatif),
                      sha256.lower())


def jour_de(instant):
    """Jours entiers depuis 1970 (UTC)."""
    return int(instant) // SECONDES_PAR_JOUR


# --------------------------------------------------------------------------- #
# Connexion
# --------------------------------------------------------------------------- #
DRIVE_REMOTE = 4


def _type_lecteur(racine):
    """GetDriveTypeW de Windows ; None si la question n'a pas de sens (autre systeme)."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    fonction = ctypes.windll.kernel32.GetDriveTypeW
    fonction.argtypes = [wintypes.LPCWSTR]
    fonction.restype = wintypes.UINT
    return fonction(racine)


def verifier_disque_local(chemin):
    """Refuse un chemin UNC et un lecteur reseau mappe (Z:). Le dossier peut ne pas exister."""
    absolu = os.path.abspath(chemin)
    if absolu.startswith("\\\\") or absolu.startswith("//"):
        raise BaseSurReseau("la base doit etre sur un disque local, pas sur un partage reseau : %s"
                            % chemin)
    racine = os.path.splitdrive(absolu)[0]
    if racine and _type_lecteur(racine + "\\") == DRIVE_REMOTE:
        raise BaseSurReseau("%s est un lecteur reseau : la base doit etre sur un disque local"
                            % racine)


def _uri_lecture_seule(chemin):
    from pathlib import Path
    return Path(os.path.abspath(chemin)).as_uri() + "?mode=ro"


def _est_verrouillee(e):
    message = str(e).lower()
    return "locked" in message or "busy" in message


class _Annuler(Exception):
    """Interne : annule la transaction en cours sans signaler d'erreur."""


class Base(object):
    def __init__(self, connexion, chemin, lecture_seule):
        self.c = connexion
        self.chemin = chemin
        self.lecture_seule = lecture_seule
        self.horloge = time.time

    def maintenant(self):
        return int(self.horloge())

    def fermer(self):
        self.c.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.fermer()
        return False

    @contextlib.contextmanager
    def transaction(self):
        if self.lecture_seule:
            raise ErreurBase("base ouverte en lecture seule")
        try:
            self.c.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as e:
            if _est_verrouillee(e):
                raise BaseIndisponible("base verrouillee : %s" % e)
            raise ErreurBase("transaction impossible : %s" % e)
        try:
            yield self.c
            self.c.execute("COMMIT")
        except BaseException as e:
            with contextlib.suppress(sqlite3.Error):
                self.c.execute("ROLLBACK")
            if isinstance(e, sqlite3.OperationalError) and _est_verrouillee(e):
                raise BaseIndisponible("base verrouillee : %s" % e)
            if isinstance(e, sqlite3.Error):
                raise ErreurBase("erreur de base : %s" % e)
            raise

    # ----- meta, journal des actions ---------------------------------------- #
    def meta(self, cle, defaut=None):
        ligne = self.c.execute("SELECT valeur FROM meta WHERE cle = ?", (cle,)).fetchone()
        return ligne["valeur"] if ligne else defaut

    def ecrire_meta(self, cle, valeur):
        with self.transaction() as c:
            c.execute("INSERT INTO meta(cle, valeur) VALUES (?, ?) "
                      "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur", (cle, str(valeur)))

    def journaliser_action(self, regle_no, action, utilisateur, commentaire=None, resultat=None):
        with self.transaction() as c:
            c.execute("INSERT INTO journal_actions(regle_no, action, utilisateur, commentaire, "
                      "demandee_le, resultat) VALUES (?, ?, ?, ?, ?, ?)",
                      (regle_no, action, utilisateur, commentaire, self.maintenant(), resultat))

    # ----- regles ------------------------------------------------------------ #
    def synchroniser_regles(self, regles):
        """regles : liste de (id, empreinte). Cree les lignes manquantes ; renvoie
        ({id en minuscules: no}, [ids dont l'empreinte a change])."""
        numeros, modifiees = {}, []
        with self.transaction() as c:
            for ident, empreinte in regles:
                ligne = c.execute("SELECT no, empreinte_parametres FROM regles WHERE id = ?",
                                  (ident,)).fetchone()
                if ligne is None:
                    cur = c.execute("INSERT INTO regles(id, cree_le, empreinte_parametres) "
                                    "VALUES (?, ?, ?)", (ident, self.maintenant(), empreinte))
                    numeros[ident.lower()] = cur.lastrowid
                else:
                    numeros[ident.lower()] = ligne["no"]
                    if ligne["empreinte_parametres"] not in (None, empreinte):
                        modifiees.append(ident)
                    if ligne["empreinte_parametres"] != empreinte:
                        c.execute("UPDATE regles SET empreinte_parametres = ? WHERE no = ?",
                                  (empreinte, ligne["no"]))
        return numeros, modifiees

    def regle(self, no):
        ligne = self.c.execute("SELECT * FROM regles WHERE no = ?", (no,)).fetchone()
        return dict(ligne) if ligne else None

    def numero_regle(self, ident):
        ligne = self.c.execute("SELECT no FROM regles WHERE id = ?", (ident,)).fetchone()
        return ligne["no"] if ligne else None

    # ----- flag « en cours » et executions (docs/03, sections 5.1 et 5.2) ---- #
    def demarrer_execution(self, regle_no, declencheur, pid, pid_cree_le=None, hote=None,
                           build=None, simulation=False):
        """Prend le flag de la regle et cree l'execution, dans une seule transaction.
        Renvoie l'id de l'execution, ou None si un autre lancement a deja pris la regle."""
        maintenant = self.maintenant()
        try:
            with self.transaction() as c:
                cur = c.execute(
                    "INSERT INTO executions(regle_no, declencheur, debut, hote, pid, build, "
                    "simulation) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (regle_no, declencheur, maintenant, hote, pid, build, int(simulation)))
                execution_id = cur.lastrowid
                cur = c.execute(
                    "UPDATE regles SET en_cours = 1, execution_id = ?, pid = ?, pid_cree_le = ?, "
                    "hote = ?, build = ?, debut_traitement = ?, dernier_lancement = ? "
                    "WHERE no = ? AND en_cours = 0",
                    (execution_id, pid, pid_cree_le, hote, build, maintenant, maintenant, regle_no))
                if cur.rowcount != 1:
                    raise _Annuler()
        except _Annuler:
            return None
        return execution_id

    def terminer_execution(self, execution_id, regle_no, statut, motif=None, compteurs=None,
                           situation_finale=None, message=None, erreur=None,
                           arret_apres_erreur=False):
        """Fin d'execution : execution, statut de la regle et liberation du flag, atomiques.
        Renvoie False si le flag n'appartenait plus a cette execution (deblocage manuel)."""
        if statut not in STATUTS_EXECUTION:
            raise ValueError("statut inconnu : %r" % statut)
        compteurs = compteurs or {}
        maintenant = self.maintenant()
        with self.transaction() as c:
            c.execute(
                "UPDATE executions SET fin = ?, statut = ?, situation_finale = ?, "
                "nb_selectionnes = ?, nb_livres = ?, nb_ignores = ?, nb_erreurs = ?, "
                "nb_en_attente = ?, octets_livres = ?, message = ? WHERE id = ?",
                (maintenant, statut, situation_finale, compteurs.get("selectionnes", 0),
                 compteurs.get("livres", 0), compteurs.get("ignores", 0),
                 compteurs.get("erreurs", 0), compteurs.get("en_attente", 0),
                 compteurs.get("octets", 0), message, execution_id))
            succes = maintenant if statut in ("SUCCES", "WARNING") else None
            cur = c.execute(
                "UPDATE regles SET en_cours = 0, execution_id = NULL, pid = NULL, "
                "pid_cree_le = NULL, dernier_fin = ?, dernier_statut = ?, dernier_statut_le = ?, "
                "dernier_motif = ?, dernier_succes = COALESCE(?, dernier_succes), "
                "derniere_erreur_le = CASE WHEN ? = 'ERREUR' THEN ? ELSE derniere_erreur_le END, "
                "derniere_erreur_situation = CASE WHEN ? = 'ERREUR' THEN ? "
                "ELSE derniere_erreur_situation END, "
                "derniere_erreur_message = CASE WHEN ? = 'ERREUR' THEN ? "
                "ELSE derniere_erreur_message END, "
                "arret_apres_erreur = ? "
                "WHERE no = ? AND en_cours = 1 AND execution_id = ?",
                (maintenant, statut, maintenant, motif, succes,
                 statut, maintenant, statut, (erreur or {}).get("situation"),
                 statut, (erreur or {}).get("message"),
                 int(bool(arret_apres_erreur)), regle_no, execution_id))
            return cur.rowcount == 1

    def liberer_flag(self, regle_no, motif):
        """Libere une regle dont le processus a disparu ou qu'on debloque : l'execution est
        marquee ARRETEE. Renvoie True si un flag a ete libere."""
        maintenant = self.maintenant()
        with self.transaction() as c:
            ligne = c.execute("SELECT en_cours, execution_id FROM regles WHERE no = ?",
                              (regle_no,)).fetchone()
            if ligne is None or not ligne["en_cours"]:
                return False
            if ligne["execution_id"] is not None:
                c.execute("UPDATE executions SET fin = ?, statut = 'ARRETEE', message = ? "
                          "WHERE id = ? AND fin IS NULL", (maintenant, motif, ligne["execution_id"]))
            c.execute("UPDATE regles SET en_cours = 0, execution_id = NULL, pid = NULL, "
                      "pid_cree_le = NULL, dernier_fin = ?, dernier_statut = 'ARRETEE', "
                      "dernier_statut_le = ?, dernier_motif = ? WHERE no = ?",
                      (maintenant, maintenant, motif, regle_no))
            return True

    # ----- fichiers : journal d'intention (docs/03, section 5.3) ------------- #
    def etat_fichier(self, cle):
        ligne = self.c.execute("SELECT etat FROM fichiers WHERE cle = ?", (cle,)).fetchone()
        return ligne["etat"] if ligne else None

    def noter_vu(self, cle, jour=None):
        """Met a jour `vu_jour` au plus une fois par jour. Renvoie True si la ligne a change."""
        jour = jour_de(self.maintenant()) if jour is None else jour
        with self.transaction() as c:
            return c.execute("UPDATE fichiers SET vu_jour = ? WHERE cle = ? AND vu_jour < ?",
                             (jour, cle, jour)).rowcount == 1

    def noter_intention(self, regle_no, cle, chemin_source, chemin_cible, chemin_archive=None,
                        taille=None, mtime_ns=None, sha256=None):
        """Transaction A : la livraison va commencer. Renvoie False si la cle existe deja."""
        maintenant = self.maintenant()
        try:
            with self.transaction() as c:
                if c.execute("SELECT 1 FROM fichiers WHERE cle = ?", (cle,)).fetchone():
                    raise _Annuler()
                c.execute("INSERT INTO fichiers(cle, regle_no, etat, vu_jour) VALUES (?, ?, ?, ?)",
                          (cle, regle_no, INTENTION, jour_de(maintenant)))
                c.execute("INSERT INTO actions_en_attente(regle_no, cle, type, chemin_source, "
                          "chemin_cible, chemin_archive, taille, mtime_ns, sha256, cree_le) "
                          "VALUES (?, ?, 'livraison', ?, ?, ?, ?, ?, ?, ?)",
                          (regle_no, cle, chemin_source, chemin_cible, chemin_archive, taille,
                           mtime_ns, sha256, maintenant))
        except _Annuler:
            return False
        return True

    def confirmer_livraison(self, cle, termine, action_suivante=None, sha256=None):
        """Transaction B : copie verifiee. `termine` (mode copie) : etat TERMINE ; sinon LIVRE
        et `action_suivante` ('suppression' ou 'archivage') est memorisee."""
        if action_suivante is not None and action_suivante not in TYPES_ACTION[1:]:
            raise ValueError("action suivante inconnue : %r" % action_suivante)
        if termine and action_suivante:
            raise ValueError("un fichier TERMINE n'a pas d'action suivante")
        maintenant = self.maintenant()
        with self.transaction() as c:
            if c.execute("UPDATE fichiers SET etat = ?, livre_le = ? WHERE cle = ? AND etat = ?",
                         (TERMINE if termine else LIVRE, maintenant, cle, INTENTION)).rowcount != 1:
                raise TransitionInvalide("le fichier n'est pas en etat INTENTION")
            ancienne = c.execute("SELECT * FROM actions_en_attente WHERE cle = ?", (cle,)).fetchone()
            c.execute("DELETE FROM actions_en_attente WHERE cle = ?", (cle,))
            if action_suivante and ancienne is not None:
                c.execute("INSERT INTO actions_en_attente(regle_no, cle, type, chemin_source, "
                          "chemin_cible, chemin_archive, taille, mtime_ns, sha256, cree_le) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (ancienne["regle_no"], cle, action_suivante, ancienne["chemin_source"],
                           ancienne["chemin_cible"], ancienne["chemin_archive"], ancienne["taille"],
                           ancienne["mtime_ns"], sha256 or ancienne["sha256"], maintenant))

    def terminer_fichier(self, cle):
        """Transaction C : l'action sur l'original est faite."""
        with self.transaction() as c:
            if c.execute("UPDATE fichiers SET etat = ? WHERE cle = ? AND etat = ?",
                         (TERMINE, cle, LIVRE)).rowcount != 1:
                raise TransitionInvalide("le fichier n'est pas en etat LIVRE")
            c.execute("DELETE FROM actions_en_attente WHERE cle = ?", (cle,))

    def marquer_orphelins_incertains(self, regle_no):
        """A appeler apres avoir pris le flag : toute INTENTION restante vient d'une execution
        morte en pleine livraison. Elle devient INCERTAIN (garantie G2). Renvoie le nombre."""
        with self.transaction() as c:
            return c.execute("UPDATE fichiers SET etat = ? WHERE regle_no = ? AND etat = ?",
                             (INCERTAIN, regle_no, INTENTION)).rowcount

    def incertains(self, regle_no):
        """Livraisons dont le resultat est inconnu : [(cle, chemin_source, chemin_cible)]."""
        lignes = self.c.execute(
            "SELECT f.cle, a.chemin_source, a.chemin_cible FROM fichiers f "
            "LEFT JOIN actions_en_attente a ON a.cle = f.cle "
            "WHERE f.regle_no = ? AND f.etat = ? ORDER BY f.cle", (regle_no, INCERTAIN)).fetchall()
        return [(l["cle"], l["chemin_source"], l["chemin_cible"]) for l in lignes]

    def resoudre_incertain(self, cle, decision, utilisateur, commentaire):
        """Decision d'exploitation. 'livre' : le fichier est bien arrive (TERMINE) ;
        'a_relivrer' : on oublie la tentative, le fichier sera relivre."""
        if decision not in ("livre", "a_relivrer"):
            raise ValueError("decision inconnue : %r" % decision)
        if not commentaire or not commentaire.strip():
            raise ValueError("un commentaire est obligatoire")
        with self.transaction() as c:
            ligne = c.execute("SELECT regle_no FROM fichiers WHERE cle = ? AND etat = ?",
                              (cle, INCERTAIN)).fetchone()
            if ligne is None:
                raise TransitionInvalide("aucun fichier INCERTAIN avec cette cle")
            if decision == "livre":
                c.execute("UPDATE fichiers SET etat = ?, livre_le = ? WHERE cle = ?",
                          (TERMINE, self.maintenant(), cle))
            else:
                c.execute("DELETE FROM fichiers WHERE cle = ?", (cle,))
            c.execute("DELETE FROM actions_en_attente WHERE cle = ?", (cle,))
            c.execute("INSERT INTO journal_actions(regle_no, action, utilisateur, commentaire, "
                      "demandee_le, resultat) VALUES (?, 'incertain', ?, ?, ?, ?)",
                      (ligne["regle_no"], utilisateur, commentaire, self.maintenant(), decision))

    # ----- actions en attente ------------------------------------------------ #
    def actions(self, regle_no, type_=None):
        requete = "SELECT * FROM actions_en_attente WHERE regle_no = ?"
        params = [regle_no]
        if type_:
            requete += " AND type = ?"
            params.append(type_)
        return [dict(l) for l in self.c.execute(requete + " ORDER BY id", params).fetchall()]

    def echec_action(self, action_id, message):
        with self.transaction() as c:
            c.execute("UPDATE actions_en_attente SET tentatives = tentatives + 1, "
                      "derniere_tentative = ?, dernier_message = ? WHERE id = ?",
                      (self.maintenant(), message, action_id))

    # ----- purge et maintenance (docs/03, sections 4.4 et 7) ----------------- #
    def purger(self, retentions_par_regle, retention_executions_jours, forcer=False):
        """retentions_par_regle : {no: jours}. Une fois par jour. Renvoie
        {'fichiers': n, 'executions': n} ou None si la purge du jour est deja faite."""
        maintenant = self.maintenant()
        jour = jour_de(maintenant)
        if not forcer and self.meta("derniere_purge_jour") == str(jour):
            return None
        fichiers = 0
        with self.transaction() as c:
            for no, jours in retentions_par_regle.items():
                fichiers += c.execute("DELETE FROM fichiers WHERE regle_no = ? AND etat = ? "
                                      "AND vu_jour < ?", (no, TERMINE, jour - jours)).rowcount
            limite = maintenant - retention_executions_jours * SECONDES_PAR_JOUR
            executions = c.execute("DELETE FROM executions WHERE fin IS NOT NULL AND debut < ?",
                                   (limite,)).rowcount
            c.execute("INSERT INTO meta(cle, valeur) VALUES ('derniere_purge_jour', ?) "
                      "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur", (str(jour),))
        self.c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return {"fichiers": fichiers, "executions": executions}

    def verifier_integrite(self):
        """Liste de messages d'anomalie ; vide si la base est saine."""
        lignes = [l[0] for l in self.c.execute("PRAGMA integrity_check").fetchall()]
        return [] if lignes == ["ok"] else lignes


# --------------------------------------------------------------------------- #
# Creation, ouverture, sauvegarde
# --------------------------------------------------------------------------- #
def _connecter(chemin, lecture_seule, busy_timeout_ms):
    c = None
    try:
        if lecture_seule:
            c = sqlite3.connect(_uri_lecture_seule(chemin), uri=True,
                                timeout=busy_timeout_ms / 1000, isolation_level=None)
        else:
            c = sqlite3.connect(chemin, timeout=busy_timeout_ms / 1000, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA busy_timeout = %d" % busy_timeout_ms)
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("PRAGMA synchronous = FULL")
        return c
    except sqlite3.Error as e:
        if c is not None:
            c.close()
        if "not a database" in str(e).lower():
            raise BaseIncoherente("%s n'est pas une base SQLite" % chemin)
        raise ErreurBase("ouverture impossible de %s : %s" % (chemin, e))


def initialiser(chemin, environnement, utilisateur):
    """--initialiser-base : cree le fichier, le schema et la ligne meta. Refuse si la base existe."""
    verifier_disque_local(chemin)
    if os.path.exists(chemin):
        raise BaseExiste("la base existe deja : %s" % chemin)
    dossier = os.path.dirname(os.path.abspath(chemin))
    os.makedirs(dossier, exist_ok=True)
    c = _connecter(chemin, False, BUSY_TIMEOUT_MS)
    try:
        mode = c.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        if mode.lower() != "wal":
            raise ErreurBase("le mode WAL n'est pas disponible sur ce disque (obtenu : %s)" % mode)
        c.executescript("BEGIN IMMEDIATE;" + SCHEMA_V1 + "PRAGMA user_version = %d; COMMIT;"
                        % VERSION_SCHEMA)
        maintenant = int(time.time())
        c.executemany("INSERT INTO meta(cle, valeur) VALUES (?, ?)",
                      [("environnement", environnement), ("cree_le", str(maintenant)),
                       ("version_moteur", __version__)])
        c.execute("INSERT INTO journal_actions(action, utilisateur, commentaire, demandee_le, "
                  "resultat) VALUES ('initialisation', ?, ?, ?, 'ok')",
                  (utilisateur, "environnement %s" % environnement, maintenant))
    except BaseException:
        c.close()
        for suffixe in ("", "-wal", "-shm"):
            with contextlib.suppress(OSError):
                os.remove(chemin + suffixe)
        raise
    c.close()


def ouvrir(chemin, environnement=None, lecture_seule=False, busy_timeout_ms=BUSY_TIMEOUT_MS):
    """Ouvre une base existante (jamais de creation automatique : garantie G6)."""
    verifier_disque_local(chemin)
    if not os.path.isfile(chemin):
        raise BaseAbsente("base introuvable : %s (creer avec --initialiser-base)" % chemin)
    c = _connecter(chemin, lecture_seule, busy_timeout_ms)
    base = Base(c, chemin, lecture_seule)
    try:
        version = c.execute("PRAGMA user_version").fetchone()[0]
        try:
            env_base = c.execute("SELECT valeur FROM meta WHERE cle = 'environnement'").fetchone()
        except sqlite3.DatabaseError:
            env_base = None
        if env_base is None:
            raise BaseIncoherente("%s n'est pas une base de copie_fichiers" % chemin)
        if environnement is not None and env_base["valeur"] != environnement:
            raise BaseIncoherente("la base est celle de l'environnement '%s', pas '%s'"
                                  % (env_base["valeur"], environnement))
        if version > VERSION_SCHEMA:
            raise BaseTropRecente("schema %d plus recent que ce programme (%d) : mettre le "
                                  "moteur a jour" % (version, VERSION_SCHEMA))
        if version < VERSION_SCHEMA:
            if lecture_seule:
                raise ErreurBase("la base (schema %d) doit etre migree avant lecture" % version)
            _migrer(base, version)
        if not lecture_seule:
            mode = c.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if mode.lower() != "wal":
                raise ErreurBase("mode WAL indisponible (obtenu : %s)" % mode)
    except sqlite3.DatabaseError as e:
        c.close()
        if _est_verrouillee(e):
            raise BaseIndisponible("base verrouillee : %s" % e)
        raise BaseIncoherente("%s n'est pas une base SQLite lisible : %s" % (chemin, e))
    except BaseException:
        c.close()
        raise
    return base


def _migrer(base, version):
    while version < VERSION_SCHEMA:
        if version not in MIGRATIONS:
            raise ErreurBase("aucune migration du schema %d vers %d" % (version, version + 1))
        with base.transaction() as c:
            for etape in MIGRATIONS[version]:
                if callable(etape):
                    etape(c)
                else:
                    c.execute(etape)
            c.execute("PRAGMA user_version = %d" % (version + 1))
        version += 1


def sauvegarder(chemin, dossier):
    """--sauvegarder-base : copie coherente par l'API de sauvegarde SQLite, meme base en cours
    d'utilisation. Renvoie le chemin du fichier cree."""
    with ouvrir(chemin, lecture_seule=True) as base:
        environnement = base.meta("environnement")
        os.makedirs(dossier, exist_ok=True)
        nom = "%s_%s.db" % (environnement, datetime.now().strftime("%Y%m%d_%H%M%S"))
        final = os.path.join(dossier, nom)
        if os.path.exists(final):
            raise BaseExiste("sauvegarde deja presente : %s" % final)
        temporaire = final + ".tmp"
        copie = sqlite3.connect(temporaire)
        try:
            base.c.backup(copie)
            copie.execute("PRAGMA journal_mode = DELETE")     # un seul fichier, autonome
            verdict = [l[0] for l in copie.execute("PRAGMA integrity_check").fetchall()]
        except BaseException:
            copie.close()
            with contextlib.suppress(OSError):
                os.remove(temporaire)
            raise
        copie.close()
        if verdict != ["ok"]:
            os.remove(temporaire)
            raise ErreurBase("la sauvegarde est corrompue : %s" % "; ".join(verdict))
        os.replace(temporaire, final)
    return final
