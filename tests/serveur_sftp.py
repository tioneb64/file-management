"""Serveur SFTP local (paramiko) pour les tests et la demonstration : un thread, une racine, un compte.

    serveur = ServeurSftp(racine, utilisateur="demo", mot_de_passe="...")
    serveur.demarrer()
    ... serveur.port, serveur.empreinte ...
    serveur.arreter()

Options d'essai : `couper_ecriture_apres` / `couper_lecture_apres` (nombre d'octets apres lesquels la connexion
est coupee, UNE seule fois), `cle_autorisee` (authentification par cle). Tout le systeme de fichiers reste
confine a `racine`. Le serveur compte les tentatives d'authentification (`serveur.tentatives_auth`).
"""
import base64
import hashlib
import logging
import os
import socket
import stat as modstat
import threading

import paramiko
from paramiko import SFTPAttributes, SFTPHandle, SFTPServer, SFTPServerInterface, ServerInterface
from paramiko.common import AUTH_FAILED, AUTH_SUCCESSFUL, OPEN_SUCCEEDED
from paramiko.sftp import SFTP_FAILURE, SFTP_OK

logging.getLogger("paramiko").addHandler(logging.NullHandler())     # pas de trace sur la console lors des coupures voulues


def empreinte_de(cle):
    return "SHA256:" + base64.b64encode(hashlib.sha256(cle.asbytes()).digest()).decode("ascii").rstrip("=")


class _Acces(ServerInterface):
    def __init__(self, serveur):
        self.serveur = serveur
        self.transport = None

    def get_allowed_auths(self, username):
        return "password,publickey"

    def check_channel_request(self, kind, chanid):
        return OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username, password):
        self.serveur.tentatives_auth += 1
        ok = username == self.serveur.utilisateur and password == self.serveur.mot_de_passe
        return AUTH_SUCCESSFUL if ok else AUTH_FAILED

    def check_auth_publickey(self, username, key):
        if self.serveur.cle_autorisee is not None and username == self.serveur.utilisateur \
                and key.asbytes() == self.serveur.cle_autorisee.asbytes():
            self.serveur.tentatives_auth += 1
            return AUTH_SUCCESSFUL
        self.serveur.tentatives_auth += 1
        return AUTH_FAILED


class _Poignee(SFTPHandle):
    def __init__(self, interface, flags=0):
        SFTPHandle.__init__(self, flags)
        self.interface = interface

    def stat(self):
        return SFTPAttributes.from_stat(os.fstat(self.readfile.fileno()))

    def chattr(self, attr):
        return SFTP_OK

    def read(self, offset, length):
        donnees = SFTPHandle.read(self, offset, length)
        if isinstance(donnees, bytes):
            self.interface.compter("lecture", len(donnees))
        return donnees

    def write(self, offset, data):
        self.interface.compter("ecriture", len(data))
        return SFTPHandle.write(self, offset, data)


class _Interface(SFTPServerInterface):
    def __init__(self, acces, *args, **kwargs):
        SFTPServerInterface.__init__(self, acces, *args, **kwargs)
        self.acces = acces
        self.serveur = acces.serveur

    def compter(self, sens, n):
        """Coupe la connexion (une seule fois) quand le seuil d'octets est atteint."""
        s = self.serveur
        s.octets[sens] += n
        seuil = s.couper_ecriture_apres if sens == "ecriture" else s.couper_lecture_apres
        if seuil is not None and not s.coupure_faite[sens] and s.octets[sens] >= seuil:
            s.coupure_faite[sens] = True
            self.acces.transport.close()

    def _reel(self, chemin):
        morceaux = [m for m in chemin.replace("\\", "/").split("/") if m not in ("", ".")]
        if ".." in morceaux:
            raise OSError(13, "interdit")
        return os.path.join(self.serveur.racine, *morceaux)

    def _erreur(self, e):
        return SFTPServer.convert_errno(e.errno) if getattr(e, "errno", None) else SFTP_FAILURE

    def list_folder(self, path):
        try:
            resultat = []
            reel = self._reel(path)
            for nom in sorted(os.listdir(reel)):
                a = SFTPAttributes.from_stat(os.lstat(os.path.join(reel, nom)))
                a.filename = nom
                resultat.append(a)
            return resultat
        except OSError as e:
            return self._erreur(e)

    def stat(self, path):
        try:
            return SFTPAttributes.from_stat(os.stat(self._reel(path)))
        except OSError as e:
            return self._erreur(e)

    def lstat(self, path):
        try:
            return SFTPAttributes.from_stat(os.lstat(self._reel(path)))
        except OSError as e:
            return self._erreur(e)

    def open(self, path, flags, attr):
        try:
            reel = self._reel(path)
            flags |= getattr(os, "O_BINARY", 0)
            fd = os.open(reel, flags, 0o666)
        except OSError as e:
            return self._erreur(e)
        if flags & os.O_WRONLY:
            mode = "ab" if flags & os.O_APPEND else "wb"
        elif flags & os.O_RDWR:
            mode = "a+b" if flags & os.O_APPEND else "r+b"
        else:
            mode = "rb"
        try:
            f = os.fdopen(fd, mode)
        except OSError as e:
            return self._erreur(e)
        poignee = _Poignee(self, flags)
        poignee.filename = reel
        poignee.readfile = f
        poignee.writefile = f
        return poignee

    def remove(self, path):
        try:
            os.remove(self._reel(path))
        except OSError as e:
            return self._erreur(e)
        return SFTP_OK

    def rename(self, oldpath, newpath):
        try:
            ancien, nouveau = self._reel(oldpath), self._reel(newpath)
            if os.path.lexists(nouveau):
                return SFTP_FAILURE                      # SFTP v3 : le renommage n'ecrase jamais
            os.rename(ancien, nouveau)
        except OSError as e:
            return self._erreur(e)
        return SFTP_OK

    def posix_rename(self, oldpath, newpath):
        try:
            os.replace(self._reel(oldpath), self._reel(newpath))
        except OSError as e:
            return self._erreur(e)
        return SFTP_OK

    def mkdir(self, path, attr):
        try:
            os.mkdir(self._reel(path))
        except OSError as e:
            return self._erreur(e)
        return SFTP_OK

    def rmdir(self, path):
        try:
            os.rmdir(self._reel(path))
        except OSError as e:
            return self._erreur(e)
        return SFTP_OK

    def chattr(self, path, attr):
        return SFTP_OK

    def canonicalize(self, path):
        return "/" + "/".join(m for m in path.replace("\\", "/").split("/") if m not in ("", "."))


class ServeurSftp(object):
    def __init__(self, racine, utilisateur="demo", mot_de_passe="secret", cle_hote=None, cle_autorisee=None,
                 adresse="127.0.0.1", port=0, couper_ecriture_apres=None, couper_lecture_apres=None):
        self.racine = os.path.abspath(racine)
        self.utilisateur = utilisateur
        self.mot_de_passe = mot_de_passe
        self.cle_hote = cle_hote or paramiko.ECDSAKey.generate()
        self.cle_autorisee = cle_autorisee
        self.adresse = adresse
        self.port = port
        self.couper_ecriture_apres = couper_ecriture_apres
        self.couper_lecture_apres = couper_lecture_apres
        self.octets = {"ecriture": 0, "lecture": 0}
        self.coupure_faite = {"ecriture": False, "lecture": False}
        self.tentatives_auth = 0
        self.connexions = 0
        self._socket = None
        self._arret = threading.Event()
        self._transports = []

    @property
    def empreinte(self):
        return empreinte_de(self.cle_hote)

    def demarrer(self):
        os.makedirs(self.racine, exist_ok=True)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((self.adresse, self.port))
        self._socket.listen(20)
        self._socket.settimeout(0.2)
        self.port = self._socket.getsockname()[1]
        self._fil = threading.Thread(target=self._boucle, daemon=True)
        self._fil.start()
        return self

    def arreter(self):
        self._arret.set()
        for t in list(self._transports):
            try:
                t.close()
            except Exception:
                pass
        try:
            self._socket.close()
        except Exception:
            pass
        self._fil.join(5)

    def __enter__(self):
        return self.demarrer()

    def __exit__(self, *_):
        self.arreter()

    def _boucle(self):
        while not self._arret.is_set():
            try:
                client, _ = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self.connexions += 1
            threading.Thread(target=self._servir, args=(client,), daemon=True).start()

    def _servir(self, client):
        transport = None
        try:
            transport = paramiko.Transport(client)
            self._transports.append(transport)
            transport.add_server_key(self.cle_hote)
            acces = _Acces(self)
            acces.transport = transport
            transport.set_subsystem_handler("sftp", SFTPServer, _Interface)
            transport.start_server(server=acces)
            canal = transport.accept(30)          # a garder : un canal ramasse est ferme
            if canal is None:
                return
            while transport.is_active() and not self._arret.is_set():
                self._arret.wait(0.05)
        except Exception:
            pass
        finally:
            try:
                if transport is not None:
                    transport.close()
            except Exception:
                pass
