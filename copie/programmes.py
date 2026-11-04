"""Programmes externes appeles par une regle (docs/02-moteur.md, section 9).

Lancement par `subprocess` SANS shell : `commande` est un tableau dont chaque element recoit ses
variables {xxx}. Sous Windows le programme demarre suspendu, est place dans un Job Object puis
repris : si la duree maximale est depassee, tout son arbre de processus est arrete.
"""
import json
import os
import subprocess
import time
from datetime import datetime

from copie import processus
from copie.chemins import remplacer_variables

POINTS = ("avant_lot", "avant_fichier", "apres_fichier", "apres_lot", "sur_erreur", "reprise")
CODES_ACCEPTES = {"avant_lot": (0, 1), "avant_fichier": (0, 1), "apres_fichier": (0, 1),
                  "apres_lot": (0, 1), "reprise": (0, 1)}
LONGUEUR_SORTIE_MAX = 8192
CREATE_SUSPENDED = 0x00000004
CREATE_NO_WINDOW = 0x08000000


class ResultatProgramme(object):
    def __init__(self):
        self.code = None            # code retour, None si le programme n'a pas pu s'executer
        self.sortie = ""
        self.duree_ms = 0
        self.depasse = False        # duree maximale depassee : arbre de processus arrete
        self.erreur = None          # lancement impossible
        self.argv = []              # commande reellement lancee (variables remplacees)

    def accepte(self, point):
        return not self.depasse and self.erreur is None and self.code in CODES_ACCEPTES.get(point, ())

    def explication(self, point):
        if self.erreur:
            return self.erreur
        if self.depasse:
            return "duree maximale depassee"
        return "code retour %s (attendu : %s)" % (self.code, " ou ".join(str(c) for c in CODES_ACCEPTES.get(point, ())))


def decoder_sortie(octets):
    """UTF-8 si possible, sinon page de code OEM de la console Windows ; jamais d'exception."""
    try:
        return octets.decode("utf-8")
    except UnicodeDecodeError:
        pass
    page = "cp850"
    if os.name == "nt":
        try:
            import ctypes
            page = "cp%d" % ctypes.windll.kernel32.GetOEMCP()
        except (OSError, AttributeError):
            pass
    try:
        return octets.decode(page, "replace")
    except LookupError:
        return octets.decode("latin-1", "replace")


def _reprendre(popen):
    """Reprend un processus demarre avec CREATE_SUSPENDED (NtResumeProcess)."""
    import ctypes
    from ctypes import wintypes
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    ntdll.NtResumeProcess.restype = ctypes.c_long
    return ntdll.NtResumeProcess(wintypes.HANDLE(int(popen._handle))) == 0


def executer(programme, point, valeurs, environnement, dossier_travail):
    """Lance `programme` (commande + timeout_sec). `valeurs` : variables des elements de la
    commande ; `environnement` : variables COPIE_* ajoutees. Renvoie un ResultatProgramme."""
    resultat = ResultatProgramme()
    argv = [remplacer_variables(element, valeurs) for element in programme.commande]
    resultat.argv = argv
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")               # un programme Python ecrit en UTF-8, pas en page ANSI
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.update(environnement)
    os.makedirs(dossier_travail, exist_ok=True)
    debut = time.monotonic()
    drapeaux = (CREATE_SUSPENDED | CREATE_NO_WINDOW) if os.name == "nt" else 0
    try:
        popen = subprocess.Popen(argv, cwd=dossier_travail, env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=drapeaux)
    except (OSError, ValueError) as e:
        resultat.erreur = "lancement impossible de %s : %s" % (argv[0], e)
        return resultat
    job = processus.JobObject(kill_on_close=False)
    try:
        job.assigner(popen)
        if os.name == "nt" and not _reprendre(popen):
            processus.tuer_arbre(popen.pid)
            popen.communicate()
            resultat.erreur = "demarrage impossible de %s" % argv[0]
            return resultat
        try:
            sortie, _ = popen.communicate(timeout=programme.timeout_sec)
        except subprocess.TimeoutExpired:
            resultat.depasse = True
            if not job.terminer():
                processus.tuer_arbre(popen.pid)
            try:
                sortie, _ = popen.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                processus.tuer_arbre(popen.pid)
                sortie = b""
        resultat.code = popen.returncode
        texte = decoder_sortie(sortie or b"").replace("\r\n", "\n")
        resultat.sortie = texte if len(texte) <= LONGUEUR_SORTIE_MAX else texte[:LONGUEUR_SORTIE_MAX] + "...[tronquee]"
    finally:
        job.fermer()
        resultat.duree_ms = int((time.monotonic() - debut) * 1000)
    return resultat


# --------------------------------------------------------------------------- #
# Listes de fichiers transmises aux programmes
# --------------------------------------------------------------------------- #
def ecrire_listes(dossier_travail, execution_id, point, entrees):
    """Ecrit `liste_<execution>_<point>.txt` (un chemin par ligne, UTF-8) et `.json` (chemin,
    taille, date de modification, et pour apres_lot le resultat). Renvoie (txt, json)."""
    os.makedirs(dossier_travail, exist_ok=True)
    base = os.path.join(dossier_travail, "liste_%s_%s" % (execution_id if execution_id is not None else "sim", point))
    chemin_txt, chemin_json = base + ".txt", base + ".json"
    with open(chemin_txt, "w", encoding="utf-8", newline="\n") as f:
        for entree in entrees:
            f.write(entree["chemin"] + "\n")
    with open(chemin_json, "w", encoding="utf-8") as f:
        json.dump(entrees, f, ensure_ascii=False, indent=1)
    return chemin_txt, chemin_json


def entree_fichier(candidat, **supplement):
    """Description d'un fichier pour les listes JSON."""
    entree = {"chemin": candidat.chemin, "relatif": candidat.relatif, "taille": candidat.taille,
              "date_modification": datetime.fromtimestamp(candidat.mtime_ns / 1e9).isoformat(timespec="seconds")}
    entree.update(supplement)
    return entree


def supprimer_listes(*chemins):
    for chemin in chemins:
        try:
            os.remove(chemin)
        except OSError:
            pass
