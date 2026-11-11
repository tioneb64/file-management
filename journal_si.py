"""Journal d'evenements JSON pour le systeme d'information (lu par Grafana Alloy).

Module autonome (bibliotheque standard seulement) : un programme du S.I. le copie tel quel et
n'appelle que trois fonctions.

    import journal_si as journal
    journal.debut(application="file_management", environnement="production", dossier=r"D:\\Copie\\logs")
    journal.evenement("fichier_livre", regle="export_clients", fichier=chemin, taille=15234)
    journal.fin(statut="WARNING", compteurs={"livres": 4})

Regles :
  * une ligne = un evenement JSON (UTF-8), ecrite en un seul appel d'ecriture atomique en mode
    ajout : plusieurs processus peuvent ecrire dans le meme fichier ;
  * un fichier par regle et par jour : <dossier>/<regle>_<AAAA-MM-JJ>.jsonl (jour local),
    <dossier>/_orchestrateur_<AAAA-MM-JJ>.jsonl pour les evenements sans regle ;
  * la journalisation ne leve JAMAIS d'exception : en cas de panne, la ligne part sur la
    sortie d'erreur et dans un fichier de secours local, et pannes() compte les incidents.

Format et catalogue : docs/02-moteur.md, section 11.
"""
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone

NIVEAUX = ("DEBUG", "INFO", "WARNING", "ERREUR")
CHAMPS_RESERVES = ("horodatage", "niveau", "application", "environnement", "job", "build",
                   "build_url", "noeud", "regle", "execution_id", "evenement")
VARIABLES_JENKINS = (("job", "JOB_NAME"), ("build", "BUILD_NUMBER"), ("build_url", "BUILD_URL"),
                     ("noeud", "NODE_NAME"))
LONGUEUR_MAX_TEXTE = 8192        # un champ texte plus long est coupe (sorties de programmes)
FICHIER_SANS_REGLE = "_orchestrateur"
_INTERDITS = re.compile(r"[^A-Za-z0-9_.-]")


# --------------------------------------------------------------------------- #
# Ecriture atomique en mode ajout
# --------------------------------------------------------------------------- #
class _FichierAjout(object):
    """Fichier ouvert en ajout seul. Sous Windows : CreateFileW avec FILE_APPEND_DATA, le systeme
    place chaque ecriture a la fin du fichier de facon atomique, meme entre processus (l'option
    O_APPEND du C ne le garantit pas). Ailleurs : O_APPEND."""

    def __init__(self, chemin):
        self.chemin = chemin
        self.handle = None
        self.fd = None
        if os.name == "nt":
            self._ouvrir_windows()
        else:
            self.fd = os.open(chemin, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)

    def _ouvrir_windows(self):
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                    ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                    wintypes.HANDLE]
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_char_p, wintypes.DWORD,
                                  ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        k32.WriteFile.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        FILE_APPEND_DATA, PARTAGE_TOTAL, OPEN_ALWAYS, NORMAL = 0x0004, 0x7, 4, 0x80
        handle = k32.CreateFileW(chemin_long(self.chemin), FILE_APPEND_DATA, PARTAGE_TOTAL, None,
                                 OPEN_ALWAYS, NORMAL, None)
        if handle is None or handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        self.handle, self._k32, self._ctypes, self._wintypes = handle, k32, ctypes, wintypes

    def ecrire(self, octets):
        if self.fd is not None:
            if os.write(self.fd, octets) != len(octets):
                raise OSError("ecriture incomplete")
            return
        ecrits = self._wintypes.DWORD(0)
        if not self._k32.WriteFile(self.handle, octets, len(octets), self._ctypes.byref(ecrits), None):
            raise self._ctypes.WinError(self._ctypes.get_last_error())
        if ecrits.value != len(octets):
            raise OSError("ecriture incomplete")

    def fermer(self):
        try:
            if self.fd is not None:
                os.close(self.fd)
            elif self.handle is not None:
                self._k32.CloseHandle(self.handle)
        finally:
            self.fd = self.handle = None


def chemin_long(chemin):
    """Prefixe \\\\?\\ les chemins Windows depassant 240 caracteres."""
    absolu = os.path.abspath(chemin)
    if os.name == "nt" and len(absolu) > 240 and not absolu.startswith("\\\\?\\"):
        absolu = "\\\\?\\UNC\\" + absolu[2:] if absolu.startswith("\\\\") else "\\\\?\\" + absolu
    return absolu


# --------------------------------------------------------------------------- #
# Journal
# --------------------------------------------------------------------------- #
class Journal(object):
    def __init__(self, horloge=time.time):
        self.horloge = horloge
        self.application = None
        self.environnement = None
        self.dossier = None
        self.dossier_secours = None
        self.verbeux = False
        self.console = False
        self.evenement_fin = "fin"
        self.contexte = {}
        self.debut_le = None
        self.nb_pannes = 0
        self._ouverts = {}

    def configurer(self, application, environnement, dossier=None, verbeux=False, console=False,
                   dossier_secours=None, evenement_fin="fin", **contexte):
        """Prepare le journal sans ecrire d'evenement (utilise aussi par la ligne de commande)."""
        self.application = application
        self.environnement = environnement
        self.dossier = dossier or os.environ.get("JOURNAL_SI_DOSSIER") or "logs"
        self.dossier_secours = dossier_secours
        self.verbeux, self.console = verbeux, console
        self.evenement_fin = evenement_fin
        self.contexte = dict(contexte)
        self.debut_le = self.horloge()

    # ----- interface en trois fonctions ----- #
    def debut(self, application, environnement, dossier=None, verbeux=False, console=False,
              dossier_secours=None, evenement_debut="debut", evenement_fin="fin", **contexte):
        self.configurer(application, environnement, dossier, verbeux, console, dossier_secours,
                        evenement_fin, **contexte)
        self.evenement(evenement_debut)

    def evenement(self, nom, niveau="INFO", **champs):
        try:
            ligne = self._construire(nom, niveau, champs)
            if ligne is None:
                return
            niveau_ecrit, regle, octets, texte = ligne
            self._ecrire(regle, octets, texte)
            if self.console:
                self._afficher(niveau_ecrit, nom, champs)
        except Exception as e:          # la journalisation ne doit jamais arreter un transfert
            self._panne("erreur interne: %s: %s" % (type(e).__name__, e))

    def fin(self, statut="OK", compteurs=None, **champs):
        niveau = {"ERREUR": "ERREUR", "WARNING": "WARNING"}.get(str(statut).upper(), "INFO")
        if self.debut_le is not None:
            champs["duree_ms"] = int((self.horloge() - self.debut_le) * 1000)
        self.evenement(self.evenement_fin, niveau, statut=statut, compteurs=compteurs or {}, **champs)
        self.fermer()

    # ----- complements ----- #
    def definir(self, **contexte):
        """Champs ajoutes a tous les evenements suivants (regle, execution_id...)."""
        self.contexte.update(contexte)

    def pannes(self):
        """Nombre d'evenements qui n'ont pas pu etre ecrits dans le dossier de journaux."""
        return self.nb_pannes

    def fermer(self):
        for fichier in self._ouverts.values():
            try:
                fichier.fermer()
            except Exception:
                pass
        self._ouverts = {}

    # ----- interne ----- #
    def _construire(self, nom, niveau, champs):
        niveau = str(niveau).upper()
        if niveau not in NIVEAUX:
            niveau = "INFO"
        if niveau == "DEBUG" and not self.verbeux:
            return None
        maintenant = self.horloge()
        evenement = {
            "horodatage": _horodatage(maintenant),
            "niveau": niveau,
            "application": self.application,
            "environnement": self.environnement,
        }
        for cle, variable in VARIABLES_JENKINS:
            if os.environ.get(variable):
                evenement[cle] = os.environ[variable]
        champs = dict(self.contexte, **champs)
        regle = champs.get("regle")
        for cle in ("regle", "execution_id"):
            if champs.get(cle) is not None:
                evenement[cle] = champs[cle]
        evenement["evenement"] = nom
        for cle, valeur in champs.items():
            if cle in ("regle", "execution_id"):
                continue
            evenement["x_" + cle if cle in CHAMPS_RESERVES else cle] = _borner(valeur)
        texte = json.dumps(evenement, ensure_ascii=False, separators=(",", ":"), default=_en_texte)
        octets = (texte + "\n").encode("utf-8", "backslashreplace")
        return niveau, regle, octets, texte

    def _chemin(self, regle):
        nom = _INTERDITS.sub("_", str(regle)) if regle else FICHIER_SANS_REGLE
        jour = datetime.fromtimestamp(self.horloge()).strftime("%Y-%m-%d")      # jour local
        return os.path.join(self.dossier, "%s_%s.jsonl" % (nom, jour))

    def _ecrire(self, regle, octets, texte):
        chemin = None
        try:
            chemin = self._chemin(regle)
            fichier = self._ouverts.get(chemin)
            if fichier is None:
                os.makedirs(self.dossier, exist_ok=True)
                self.fermer_anciens(chemin)
                fichier = self._ouverts[chemin] = _FichierAjout(chemin)
            fichier.ecrire(octets)
        except Exception as e:
            # on oublie le fichier : la prochaine ecriture tentera de le rouvrir
            fautif = self._ouverts.pop(chemin, None)
            if fautif is not None:
                try:
                    fautif.fermer()
                except Exception:
                    pass
            self._panne("%s: %s" % (type(e).__name__, e), texte)

    def fermer_anciens(self, chemin_courant):
        """Ferme les fichiers des jours precedents de la meme regle."""
        prefixe = os.path.basename(chemin_courant).rsplit("_", 1)[0]
        for ancien in [c for c in self._ouverts
                       if c != chemin_courant and os.path.basename(c).rsplit("_", 1)[0] == prefixe]:
            try:
                self._ouverts.pop(ancien).fermer()
            except Exception:
                pass

    def _panne(self, cause, texte=None):
        """Repli : sortie d'erreur, puis fichier de secours local. Ne leve jamais."""
        self.nb_pannes += 1
        try:
            if self.nb_pannes == 1:
                sys.stderr.write("journal_si: ecriture impossible (%s), repli sur le fichier de "
                                 "secours\n" % cause)
            if texte:
                sys.stderr.write("journal_si: %s\n" % texte)
            sys.stderr.flush()
        except Exception:
            pass
        if texte:
            try:
                dossier = self.dossier_secours or tempfile.gettempdir()
                jour = datetime.fromtimestamp(self.horloge()).strftime("%Y-%m-%d")
                with open(os.path.join(dossier, "journal_si_secours_%s.jsonl" % jour), "ab") as f:
                    f.write((texte + "\n").encode("utf-8", "backslashreplace"))
            except Exception:
                pass

    def _afficher(self, niveau, nom, champs):
        try:
            detail = " ".join("%s=%s" % (k, _borner(v)) for k, v in champs.items()
                              if k in ("regle", "message", "fichier", "statut"))
            sys.stdout.write("%s %-7s %s %s\n" % (time.strftime("%H:%M:%S", time.localtime(
                self.horloge())), niveau, nom, detail))
            sys.stdout.flush()
        except Exception:
            pass


def _horodatage(instant):
    """UTC, ISO 8601 au millieme de seconde (arrondi, pour eviter les erreurs de virgule flottante)."""
    millis = int(round(instant * 1000))
    return (datetime.fromtimestamp(millis // 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            + ".%03dZ" % (millis % 1000))


def _en_texte(valeur):
    if isinstance(valeur, bytes):
        return valeur.decode("utf-8", "replace")
    if isinstance(valeur, (set, frozenset, tuple)):
        return list(valeur)
    return str(valeur)


def _borner(valeur):
    if isinstance(valeur, bytes):
        valeur = valeur.decode("utf-8", "replace")
    if isinstance(valeur, str) and len(valeur) > LONGUEUR_MAX_TEXTE:
        return valeur[:LONGUEUR_MAX_TEXTE] + "...[tronque, %d caracteres]" % len(valeur)
    return valeur


# --------------------------------------------------------------------------- #
# Ligne de commande : evenements ecrits par un autre outil (pipeline Jenkins)
# --------------------------------------------------------------------------- #
def main(argv=None):
    """python journal_si.py --dossier D --application A --environnement E --evenement debut_job
    [--niveau INFO] [--regle ID] [--champ cle=valeur ...] [--champs-json FICHIER] [--console]

    Ecrit UN evenement, avec exactement le format du module. Sort TOUJOURS avec le code 0 : une
    panne de journalisation ne doit jamais faire echouer le pipeline (elle est signalee sur la
    sortie d'erreur et repliee dans le fichier de secours)."""
    import argparse
    p = argparse.ArgumentParser(description=main.__doc__.split("\n")[0])
    p.add_argument("--dossier", required=True)
    p.add_argument("--application", required=True)
    p.add_argument("--environnement", required=True)
    p.add_argument("--evenement", required=True)
    p.add_argument("--niveau", default="INFO")
    p.add_argument("--regle")
    p.add_argument("--champ", action="append", default=[], metavar="CLE=VALEUR",
                   help="champ texte (repetable) ; pour des valeurs typees, --champs-json")
    p.add_argument("--champs-json", metavar="FICHIER",
                   help="fichier JSON (UTF-8) contenant un objet de champs a ajouter")
    p.add_argument("--console", action="store_true", help="ecrit aussi une ligne lisible sur la sortie standard")
    args = p.parse_args(argv)
    journal = Journal()
    try:
        champs = {}
        if args.champs_json:
            with open(args.champs_json, encoding="utf-8-sig") as f:
                contenu = json.load(f)
            if isinstance(contenu, dict):
                champs.update(contenu)
        for element in args.champ:
            cle, _, valeur = element.partition("=")
            if cle:
                champs[cle] = valeur
        if args.regle:
            champs["regle"] = args.regle
        journal.configurer(args.application, args.environnement, args.dossier, console=args.console)
        journal.evenement(args.evenement, args.niveau, **champs)
    except Exception as e:                     # y compris un fichier JSON illisible : jamais d'echec
        sys.stderr.write("journal_si: evenement non ecrit (%s: %s)\n" % (type(e).__name__, e))
    finally:
        journal.fermer()
    if journal.pannes():
        sys.stderr.write("journal_si: %d evenement(s) replie(s) dans le fichier de secours\n" % journal.pannes())
    return 0


# --------------------------------------------------------------------------- #
# Interface de module : un journal par processus
# --------------------------------------------------------------------------- #
_journal = Journal()


def debut(*args, **kwargs):
    return _journal.debut(*args, **kwargs)


def evenement(nom, niveau="INFO", **champs):
    return _journal.evenement(nom, niveau, **champs)


def fin(*args, **kwargs):
    return _journal.fin(*args, **kwargs)


def definir(**contexte):
    return _journal.definir(**contexte)


def pannes():
    return _journal.pannes()


if __name__ == "__main__":
    sys.exit(main())
