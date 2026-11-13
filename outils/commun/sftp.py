# bibliotheque: connexion SFTP (paramiko) : options, authentification, cle d'hote verifiee, reconnexion, transferts reprenables
"""Connexion SFTP des outils `sftp_envoyer` et `sftp_recuperer`.

- `paramiko` est une dependance facultative : absent, l'outil s'arrete avec le code 4 et un message clair.
- Aucun secret en ligne de commande : mot de passe par variable ou fichier (outils.commun.secret), phrase
  secrete de la cle privee par variable ; rien de tout cela n'est journalise.
- La cle de l'hote est toujours verifiee : empreinte attendue (--empreinte-hote), fichier known_hosts
  (--known-hosts, sinon celui de l'utilisateur) ; une cle inconnue est refusee, sauf --hote-inconnu accepter
  (avertissement dans le journal avec l'empreinte relevee). Une cle DIFFERENTE de celle connue est toujours refusee.
- Une authentification refusee n'est jamais rejouee (risque de verrouillage du compte) ; un incident reseau
  l'est (--tentatives, --pause), y compris en cours de transfert : la session est rouverte et le transfert
  reprend la ou il s'est arrete (fichier temporaire, prefixe verifie par SHA-256).
- Un fichier n'est jamais visible sous son nom definitif avant d'etre complet et verifie : depot sous un nom
  temporaire puis renommage ; rien n'est ecrase sans option.
"""
import base64
import errno
import hashlib
import os
import posixpath
import socket
import stat
import time

from outils.commun.dependances import module_optionnel
from outils.commun.erreurs import (DUPLICATE_ENTITY, EXTERNAL_SERVICE_ERROR, FILE_NOT_FOUND, TIMEOUT,
                                   ErreurOutil, ErreurParametres)
from outils.commun.fichiers import SUFFIXE_TEMPORAIRE, TAILLE_BLOC, sha256_fichier
from outils.commun.secret import lire_mot_de_passe, options_mot_de_passe

SUFFIXE_DISTANT = ".tmp"
BLOC = 256 * 1024
VERIFICATIONS = ("taille", "sha256", "aucune")


# --------------------------------------------------------------------------- #
# Options
# --------------------------------------------------------------------------- #
def options_connexion(parser):
    g = parser.add_argument_group("connexion SFTP")
    g.add_argument("--hote", required=True, metavar="HOTE", help="serveur SFTP (nom ou adresse)")
    g.add_argument("--port", type=int, default=22, metavar="N", help="port (defaut 22)")
    g.add_argument("--utilisateur", required=True, metavar="COMPTE", help="compte de connexion")
    options_mot_de_passe(parser)
    g.add_argument("--cle-privee", metavar="FICHIER", help="cle privee d'authentification (OpenSSH ou PEM)")
    g.add_argument("--phrase-env", metavar="NOM",
                   help="nom de la variable d'environnement qui contient la phrase secrete de la cle privee")
    g.add_argument("--empreinte-hote", metavar="SHA256:XXX",
                   help="empreinte attendue de la cle de l'hote (ssh-keygen -lf, ou relevee dans le journal)")
    g.add_argument("--known-hosts", metavar="FICHIER",
                   help="fichier known_hosts (defaut : celui de l'utilisateur s'il existe)")
    g.add_argument("--hote-inconnu", choices=("refuser", "accepter"), default="refuser", metavar="{refuser,accepter}",
                   help="cle d'un hote jamais vu : refuser (defaut) ou accepter avec avertissement")
    g.add_argument("--delai", type=float, default=30.0, metavar="SEC", help="delai reseau (defaut 30)")
    g.add_argument("--tentatives", type=int, default=3, metavar="N",
                   help="nombre d'essais en cas d'incident reseau (defaut 3) ; une authentification refusee "
                        "n'est jamais rejouee")
    g.add_argument("--pause", type=float, default=5.0, metavar="SEC", help="pause entre deux essais (defaut 5)")
    return g


def options_transfert(parser):
    g = parser.add_argument_group("transfert")
    g.add_argument("--ecraser", action="store_true", help="remplace un fichier qui existe deja (sinon : erreur)")
    g.add_argument("--ignorer-existants", action="store_true",
                   help="passe sans erreur un fichier qui existe deja (rien n'est ecrase)")
    g.add_argument("--verification", choices=VERIFICATIONS, default="taille", metavar="{taille,sha256,aucune}",
                   help="controle apres transfert : taille (defaut), sha256 (relit le fichier) ou aucune")
    g.add_argument("--suffixe-temporaire", default=SUFFIXE_DISTANT, metavar="SUFFIXE",
                   help="suffixe du nom temporaire cote serveur (defaut .tmp)")
    return g


def empreinte(cle):
    """Empreinte d'une cle publique, au format de ssh-keygen : SHA256:<base64 sans =>."""
    return "SHA256:" + base64.b64encode(hashlib.sha256(cle.asbytes()).digest()).decode("ascii").rstrip("=")


# --------------------------------------------------------------------------- #
# Connexion
# --------------------------------------------------------------------------- #
class Connexion(object):
    def __init__(self, ctx, args):
        self.ctx = ctx
        self.args = args
        self.paramiko = module_optionnel("paramiko")             # absent : DependanceAbsente (code 4)
        if args.tentatives < 1:
            raise ErreurParametres("--tentatives : au moins 1")
        if args.delai <= 0 or args.pause < 0:
            raise ErreurParametres("--delai doit etre positif et --pause ne peut etre negative")
        if not 0 < args.port < 65536:
            raise ErreurParametres("--port : de 1 a 65535")
        if args.empreinte_hote and args.known_hosts:
            raise ErreurParametres("--empreinte-hote et --known-hosts sont exclusifs")
        self.secret = lire_mot_de_passe(args, ctx.env)
        self.phrase = None
        if args.phrase_env:
            self.phrase = ctx.env.get(args.phrase_env)
            if not self.phrase:
                raise ErreurParametres("la variable d'environnement %s est absente ou vide" % args.phrase_env)
        if not self.secret and not args.cle_privee:
            raise ErreurParametres("aucun moyen d'authentification : --mot-de-passe-env / --mot-de-passe-fichier "
                                   "ou --cle-privee")
        self.cle = self._charger_cle(args.cle_privee) if args.cle_privee else None
        self.attendue = None
        if args.empreinte_hote:
            self.attendue = args.empreinte_hote.strip()
            if not self.attendue.upper().startswith("SHA256:"):
                self.attendue = "SHA256:" + self.attendue
        self.transport = None
        self.sftp = None
        self.ouvertures = 0

    # ----- ouverture ----- #
    def _charger_cle(self, chemin):
        p = self.paramiko
        if not os.path.isfile(chemin):
            raise ErreurParametres("cle privee introuvable : %s" % chemin)
        # PKey.from_path attend la phrase en octets pour une cle OpenSSH et en texte pour une cle PEM : on essaie
        # les deux, puis les classes de cle une a une (comportement de paramiko variable selon les versions)
        phrases = [None] if not self.phrase else [self.phrase.encode("utf-8"), self.phrase]
        tentatives = [lambda ph=ph: p.PKey.from_path(chemin, ph) for ph in phrases]
        for classe in (p.Ed25519Key, p.ECDSAKey, p.RSAKey):
            tentatives.append(lambda c=classe: c.from_private_key_file(chemin, self.phrase))
        for tentative in tentatives:
            try:
                return tentative()
            except Exception:
                continue
        raise ErreurParametres("cle privee illisible ou phrase secrete incorrecte : %s" % chemin)

    def _nom_known_hosts(self):
        return self.args.hote if self.args.port == 22 else "[%s]:%d" % (self.args.hote, self.args.port)

    def _verifier_cle_hote(self, cle):
        a = self.args
        relevee = empreinte(cle)
        if self.attendue:
            if relevee != self.attendue:
                raise ErreurOutil("cle de l'hote %s differente de l'empreinte attendue (attendue %s, relevee %s) : "
                                  "connexion refusee, possible interception" % (a.hote, self.attendue, relevee),
                                  EXTERNAL_SERVICE_ERROR)
            return
        fichier = a.known_hosts
        if not fichier:
            par_defaut = os.path.join(os.path.expanduser("~"), ".ssh", "known_hosts")
            fichier = par_defaut if os.path.isfile(par_defaut) else None
        connues = None
        if fichier:
            connues = self.paramiko.HostKeys()
            try:
                connues.load(fichier)
            except OSError as e:
                raise ErreurParametres("fichier known_hosts illisible : %s" % (e.strerror or e))
            entrees = connues.lookup(self._nom_known_hosts())
            if entrees is not None:
                if any(k.asbytes() == cle.asbytes() for k in entrees.values()):
                    return
                raise ErreurOutil("la cle de l'hote %s differe de celle de known_hosts (relevee %s) : connexion "
                                  "refusee, possible interception" % (a.hote, relevee), EXTERNAL_SERVICE_ERROR)
        if a.hote_inconnu == "accepter":
            self.ctx.avertir("hote_inconnu_accepte", "Hote %s jamais vu : cle acceptee (%s) ; a fixer par "
                             "--empreinte-hote" % (a.hote, relevee), hote=a.hote, empreinte=relevee)
            return
        raise ErreurOutil("cle de l'hote %s inconnue (%s %s) : connexion refusee ; la verifier aupres du "
                          "partenaire puis la fixer par --empreinte-hote (ou l'inscrire dans known_hosts)"
                          % (a.hote, cle.get_name(), relevee), EXTERNAL_SERVICE_ERROR)

    def _authentifier(self, transport):
        a, p = self.args, self.paramiko
        essais = []
        if self.cle is not None:
            essais.append(lambda: transport.auth_publickey(a.utilisateur, self.cle))
        if self.secret:
            essais.append(lambda: transport.auth_password(a.utilisateur, self.secret))
        for i, essai in enumerate(essais):
            try:
                essai()
                return
            except p.AuthenticationException:
                if i == len(essais) - 1:
                    raise ErreurOutil("authentification refusee pour %s sur %s (non rejouee, pour ne pas verrouiller "
                                      "le compte)" % (a.utilisateur, a.hote), EXTERNAL_SERVICE_ERROR)
                transport = self._rouvrir_transport_apres_refus(transport)

    def _rouvrir_transport_apres_refus(self, transport):
        # un serveur peut fermer la session apres un refus : on repart d'une session saine pour la 2e methode
        if transport.is_active():
            return transport
        raise ErreurOutil("authentification refusee pour %s sur %s (non rejouee)" % (self.args.utilisateur,
                                                                                  self.args.hote),
                          EXTERNAL_SERVICE_ERROR)

    def _ouvrir_une_fois(self):
        a, p = self.args, self.paramiko
        sock = socket.create_connection((a.hote, a.port), timeout=a.delai)
        try:
            transport = p.Transport(sock)
        except Exception:
            sock.close()
            raise
        self.transport = transport
        transport.banner_timeout = a.delai
        transport.start_client(timeout=a.delai)
        self._verifier_cle_hote(transport.get_remote_server_key())
        self._authentifier(transport)
        self.sftp = p.SFTPClient.from_transport(transport)
        self.sftp.get_channel().settimeout(a.delai)
        self.ouvertures += 1

    def ouvrir(self):
        a, p = self.args, self.paramiko
        derniere = None
        for essai in range(1, a.tentatives + 1):
            try:
                self._ouvrir_une_fois()
                return
            except (ErreurOutil, ErreurParametres):
                self.fermer()
                raise
            except (OSError, EOFError, p.SSHException) as e:
                self.fermer()
                derniere = e
                if essai < a.tentatives:
                    self.ctx.avertir("sftp_connexion_echouee", "Connexion %d/%d echouee (%s) : nouvel essai"
                                     % (essai, a.tentatives, _cause(e)), hote=a.hote, port=a.port, essai=essai)
                    time.sleep(a.pause)
        delai = isinstance(derniere, (socket.timeout, TimeoutError))
        raise ErreurOutil("connexion impossible a %s:%d apres %d essai(s) : %s" % (a.hote, a.port, a.tentatives,
                                                                                 _cause(derniere)),
                          TIMEOUT if delai else EXTERNAL_SERVICE_ERROR)

    def fermer(self):
        for objet in (self.sftp, self.transport):
            try:
                if objet is not None:
                    objet.close()
            except Exception:
                pass
        self.sftp = self.transport = None

    def __enter__(self):
        self.ouvrir()
        return self

    def __exit__(self, *_):
        self.fermer()
        return False

    # ----- reprise apres incident reseau ----- #
    def actif(self):
        return self.transport is not None and self.transport.is_active()

    def est_coupure(self, e):
        p = self.paramiko
        if isinstance(e, (ErreurOutil, ErreurParametres, p.AuthenticationException)):
            return False
        if isinstance(e, (p.SSHException, EOFError, socket.timeout, TimeoutError, ConnectionError)):
            return True
        if isinstance(e, OSError):
            return not self.actif()          # une erreur de fichier du serveur laisse la session vivante
        return False

    def executer(self, fonction, **champs):
        """fonction(sftp, essai) ; en cas de coupure, rouvre la session et rappelle la fonction (qui reprend
        la ou le transfert s'est arrete), dans la limite de --tentatives."""
        a = self.args
        for essai in range(1, a.tentatives + 1):
            try:
                if self.sftp is None:
                    self.ouvrir()
                return fonction(self.sftp, essai)
            except Exception as e:
                if not self.est_coupure(e):
                    raise
                self.fermer()
                if essai >= a.tentatives:
                    delai = isinstance(e, (socket.timeout, TimeoutError))
                    raise ErreurOutil("connexion perdue en cours de transfert apres %d essai(s) : %s"
                                      % (a.tentatives, _cause(e)), TIMEOUT if delai else EXTERNAL_SERVICE_ERROR)
                self.ctx.avertir("sftp_reprise", "Connexion perdue (%s) : reprise %d/%d" % (_cause(e), essai,
                                                                                         a.tentatives - 1),
                                 essai=essai, **champs)
                time.sleep(a.pause)


def _cause(e):
    texte = str(e) or type(e).__name__
    return texte if len(texte) < 200 else texte[:200] + "..."


# --------------------------------------------------------------------------- #
# Chemins et operations distantes
# --------------------------------------------------------------------------- #
def joindre_distant(base, relatif):
    """base + relatif (separateurs / ou \\), sans '..' ni chemin absolu : un nom venu d'ailleurs ne sort pas de base."""
    morceaux = [m for m in relatif.replace("\\", "/").split("/") if m not in ("", ".")]
    if ".." in morceaux:
        raise ErreurOutil("chemin refuse (sortirait du dossier distant) : %s" % relatif, FILE_NOT_FOUND)
    return posixpath.join(base, *morceaux) if morceaux else base


def attributs(sftp, chemin):
    """Attributs distants ou None si le chemin n'existe pas."""
    try:
        return sftp.stat(chemin)
    except IOError as e:
        if getattr(e, "errno", None) == errno.ENOENT:
            return None
        raise


def creer_dossiers(sftp, dossier):
    chemin = ""
    for morceau in [m for m in dossier.split("/") if m]:
        chemin = chemin + "/" + morceau if (dossier.startswith("/") or chemin) else morceau
        if attributs(sftp, chemin) is None:
            sftp.mkdir(chemin)


def verifier_dossier(sftp, dossier):
    st = attributs(sftp, dossier)
    if st is None:
        raise ErreurOutil("dossier distant introuvable : %s" % dossier, FILE_NOT_FOUND)
    if not stat.S_ISDIR(st.st_mode or 0):
        raise ErreurOutil("le chemin distant n'est pas un dossier : %s" % dossier, FILE_NOT_FOUND)


def nom_libre_distant(sftp, dossier, nom):
    base, ext = posixpath.splitext(nom)
    candidat, n = nom, 1
    while attributs(sftp, posixpath.join(dossier, candidat)) is not None:
        n += 1
        candidat = "%s_%d%s" % (base, n, ext)
    return posixpath.join(dossier, candidat)


def nom_libre_local(dossier, nom):
    base, ext = os.path.splitext(nom)
    candidat, n = nom, 1
    while os.path.lexists(os.path.join(dossier, candidat)):
        n += 1
        candidat = "%s_%d%s" % (base, n, ext)
    return os.path.join(dossier, candidat)


def renommer_distant(sftp, source, cible, ecraser):
    """Renomme sans rien ecraser (sauf `ecraser`)."""
    if attributs(sftp, cible) is not None:
        if not ecraser:
            raise ErreurOutil("le fichier distant existe deja (--ecraser pour le remplacer) : %s" % cible,
                              DUPLICATE_ENTITY)
        try:
            sftp.posix_rename(source, cible)
            return
        except (IOError, OSError) as e:
            if getattr(e, "errno", None) == errno.ENOENT or not _simple_refus(e):
                raise
        sftp.remove(cible)
    sftp.rename(source, cible)


def _simple_refus(e):
    return getattr(e, "errno", None) is None            # operation non prise en charge par le serveur


def lister_distant(sftp, dossier, recursif, relatif=""):
    """(chemin distant, chemin relatif, attributs) des fichiers ordinaires, tries ; liens et speciaux ignores."""
    for attr in sorted(sftp.listdir_attr(dossier), key=lambda a: a.filename):
        chemin = posixpath.join(dossier, attr.filename)
        rel = posixpath.join(relatif, attr.filename) if relatif else attr.filename
        mode = attr.st_mode or 0
        if stat.S_ISDIR(mode):
            if recursif:
                for suite in lister_distant(sftp, chemin, recursif, rel):
                    yield suite
        elif stat.S_ISREG(mode):
            yield chemin, rel, attr


# --------------------------------------------------------------------------- #
# Empreintes
# --------------------------------------------------------------------------- #
def sha256_local_debut(chemin, n):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        restant = n
        while restant > 0:
            bloc = f.read(min(TAILLE_BLOC, restant))
            if not bloc:
                break
            h.update(bloc)
            restant -= len(bloc)
    return h.hexdigest()


def sha256_distant(sftp, chemin, n=None):
    """SHA-256 du fichier distant (ou de ses n premiers octets)."""
    h = hashlib.sha256()
    with sftp.open(chemin, "rb") as f:
        restant = n
        while restant is None or restant > 0:
            bloc = f.read(BLOC if restant is None else min(BLOC, restant))
            if not bloc:
                break
            h.update(bloc)
            if restant is not None:
                restant -= len(bloc)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# Transferts
# --------------------------------------------------------------------------- #
def envoyer_fichier(sftp, local, distant, ecraser=False, verification="taille", suffixe=SUFFIXE_DISTANT, essai=1):
    """Depose `local` sur le serveur sous `distant` : ecriture sous `distant + suffixe`, controle, renommage.
    Un temporaire laisse par une coupure est repris si son contenu est le debut exact du fichier local.
    Renvoie (taille, octets repris, sha256 ou None)."""
    taille = os.path.getsize(local)
    temporaire = distant + suffixe
    st_tmp = attributs(sftp, temporaire)
    existant = attributs(sftp, distant)
    sha_local = sha256_fichier(local) if verification == "sha256" else None
    if existant is not None:
        if essai > 1 and st_tmp is None and existant.st_size == taille and (
                sha_local is None or sha256_distant(sftp, distant) == sha_local):
            return taille, taille, sha_local            # renomme juste avant la coupure : rien a refaire
        if not ecraser:
            raise ErreurOutil("le fichier distant existe deja (--ecraser pour le remplacer) : %s" % distant,
                              DUPLICATE_ENTITY)
    debut = 0
    if st_tmp is not None and 0 < st_tmp.st_size <= taille and \
            sha256_distant(sftp, temporaire, st_tmp.st_size) == sha256_local_debut(local, st_tmp.st_size):
        debut = st_tmp.st_size
    with sftp.open(temporaire, "r+b" if debut else "wb") as f:
        f.set_pipelined(True)
        if debut:
            f.seek(debut)
        with open(local, "rb") as src:
            src.seek(debut)
            while True:
                bloc = src.read(BLOC)
                if not bloc:
                    break
                f.write(bloc)
    if sftp.stat(temporaire).st_size != taille:
        _retirer_distant(sftp, temporaire)
        raise ErreurOutil("taille distante differente apres l'envoi (%d attendus) : %s" % (taille, distant))
    if sha_local is not None and sha256_distant(sftp, temporaire) != sha_local:
        _retirer_distant(sftp, temporaire)
        raise ErreurOutil("SHA-256 distant different de la source apres l'envoi : %s" % distant)
    renommer_distant(sftp, temporaire, distant, ecraser)
    return taille, debut, sha_local


def recuperer_fichier(sftp, distant, local, taille, ecraser=False, verification="taille", essai=1):
    """Telecharge `distant` vers `local` : ecriture sous `local + .copie_en_cours` (ignore par le moteur),
    controle, renommage. Reprise d'un temporaire dont le contenu est le debut exact du fichier distant.
    Renvoie (taille, octets repris, sha256 ou None)."""
    if os.path.lexists(local) and not ecraser:
        raise ErreurOutil("le fichier existe deja (--ecraser pour le remplacer) : %s" % local, DUPLICATE_ENTITY)
    os.makedirs(os.path.dirname(os.path.abspath(local)), exist_ok=True)
    temporaire = local + SUFFIXE_TEMPORAIRE
    debut = 0
    if os.path.isfile(temporaire):
        existant = os.path.getsize(temporaire)
        if 0 < existant <= taille and sha256_local_debut(temporaire, existant) == sha256_distant(sftp, distant,
                                                                                               existant):
            debut = existant
    with open(temporaire, "r+b" if debut else "wb") as dest:
        dest.seek(debut)
        dest.truncate()
        with sftp.open(distant, "rb") as f:
            if debut:
                f.seek(debut)
            else:
                f.prefetch(taille)
            while True:
                bloc = f.read(BLOC)
                if not bloc:
                    break
                dest.write(bloc)
    if os.path.getsize(temporaire) != taille:
        raise ErreurOutil("taille locale differente apres le telechargement (%d attendus) : %s" % (taille, distant))
    sha = None
    if verification == "sha256":
        sha = sha256_fichier(temporaire)
        if sha256_distant(sftp, distant) != sha:
            os.remove(temporaire)
            raise ErreurOutil("SHA-256 different de la source distante apres le telechargement : %s" % distant)
    if os.path.lexists(local) and not ecraser:
        raise ErreurOutil("le fichier existe deja (--ecraser pour le remplacer) : %s" % local, DUPLICATE_ENTITY)
    os.replace(temporaire, local)
    return taille, debut, sha


def _retirer_distant(sftp, chemin):
    try:
        sftp.remove(chemin)
    except (IOError, OSError):
        pass
