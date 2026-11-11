"""Controle d'un serveur d'execution : Python et Windows savent-ils faire ce dont file_management v2 a besoin ?

A lancer sur le serveur de recette (puis de production) avec le Python cible :

    C:\\Python314\\python.exe controle_serveur.py [--dossier D:\\temp] [--partage \\\\SERVEUR\\partage\\test]

Bibliotheque standard seulement. Ne cree que des fichiers temporaires, tous supprimes a la fin.
Code retour : 0 = tout est bon, 1 = au moins un controle en echec.
"""
import argparse
import json
import multiprocessing
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

EST_WINDOWS = os.name == "nt"
resultats = []


def controle(nom):
    """Decorateur : execute le controle, enregistre OK / ECHEC / IGNORE et le detail."""
    def decorateur(fonction):
        def execute(*args, **kwargs):
            try:
                detail = fonction(*args, **kwargs)
                if detail is IGNORE:
                    etat, detail = "IGNORE", "sans objet sur ce systeme"
                else:
                    etat = "OK"
            except Exception as e:   # un controle ne doit jamais arreter les autres
                etat, detail = "ECHEC", "%s: %s" % (type(e).__name__, e)
            resultats.append({"controle": nom, "etat": etat, "detail": str(detail or "")})
            print("%-7s %-34s %s" % (etat, nom, detail or ""))
        return execute
    return decorateur


IGNORE = object()


@controle("Python")
def ctl_python():
    return "%s | %s | %s" % (platform.python_version(), platform.python_implementation(),
                             "64 bits" if sys.maxsize > 2 ** 32 else "32 bits")


@controle("Systeme")
def ctl_systeme():
    return "%s %s (%s)" % (platform.system(), platform.version(), platform.machine())


@controle("Modules necessaires")
def ctl_modules():
    for nom in ("sqlite3", "ctypes", "multiprocessing", "subprocess", "hashlib", "json",
                "logging", "argparse", "fnmatch", "datetime"):
        __import__(nom)
    if EST_WINDOWS:
        __import__("msvcrt")
    return "tous importables"


@controle("Encodage de la console")
def ctl_encodage():
    return "stdout=%s, systeme de fichiers=%s" % (sys.stdout.encoding, sys.getfilesystemencoding())


@controle("Heure locale et fuseau")
def ctl_heure():
    return "%s (%s)" % (time.strftime("%Y-%m-%d %H:%M:%S"), time.tzname[0])


def _ecrire_base(args):
    chemin, numero = args
    c = sqlite3.connect(chemin, timeout=30)
    try:
        for i in range(50):
            c.execute("INSERT INTO t(k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = v + 1",
                      ("p%d_%d" % (numero, i), 1))
            c.commit()
    finally:
        c.close()
    return numero


@controle("SQLite (WAL, UPSERT, 4 processus)")
def ctl_sqlite(dossier):
    chemin = os.path.join(dossier, "controle.db")
    c = sqlite3.connect(chemin)
    mode = c.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    if mode.lower() != "wal":
        raise RuntimeError("mode WAL refuse (obtenu : %s)" % mode)
    c.execute("CREATE TABLE t(k TEXT PRIMARY KEY, v INTEGER) WITHOUT ROWID")
    c.commit()
    c.close()
    with multiprocessing.get_context("spawn").Pool(4) as pool:
        pool.map(_ecrire_base, [(chemin, n) for n in range(4)])
    c = sqlite3.connect(chemin)
    total = c.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    c.close()
    if total != 200:
        raise RuntimeError("%d lignes au lieu de 200" % total)
    return "SQLite %s, 200 ecritures concurrentes sans perte" % sqlite3.sqlite_version


@controle("Espace disque (GetDiskFreeSpaceExW)")
def ctl_espace(dossier):
    if not EST_WINDOWS:
        return IGNORE
    import ctypes
    from ctypes import wintypes
    libre_appelant = ctypes.c_ulonglong()
    total = ctypes.c_ulonglong()
    libre_total = ctypes.c_ulonglong()
    fonction = ctypes.windll.kernel32.GetDiskFreeSpaceExW
    fonction.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_ulonglong),
                         ctypes.POINTER(ctypes.c_ulonglong), ctypes.POINTER(ctypes.c_ulonglong)]
    if not fonction(dossier, ctypes.byref(libre_appelant), ctypes.byref(total),
                    ctypes.byref(libre_total)):
        raise ctypes.WinError()
    python = shutil.disk_usage(dossier).free
    mo = 1024 * 1024
    return "libre pour l'appelant %d Mo, libre total %d Mo, shutil.disk_usage %d Mo%s" % (
        libre_appelant.value // mo, libre_total.value // mo, python // mo,
        "" if python == libre_appelant.value else "  <-- shutil differe : utiliser l'appel Windows")


@controle("Verrou de fichier (msvcrt)")
def ctl_verrou(dossier):
    if not EST_WINDOWS:
        return IGNORE
    import msvcrt
    chemin = os.path.join(dossier, "controle.lock")
    premier = open(chemin, "a+")
    second = open(chemin, "a+")
    try:
        msvcrt.locking(premier.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            second.seek(0)
            msvcrt.locking(second.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return "le second verrou est bien refuse"
        raise RuntimeError("le second verrou a ete accorde")
    finally:
        premier.close()
        second.close()


@controle("Remplacement atomique (os.replace)")
def ctl_replace(dossier):
    a = os.path.join(dossier, "a.tmp")
    b = os.path.join(dossier, "b.txt")
    for chemin, texte in ((a, "nouveau"), (b, "ancien")):
        with open(chemin, "w") as f:
            f.write(texte)
    os.replace(a, b)
    with open(b) as f:
        if f.read() != "nouveau":
            raise RuntimeError("contenu inattendu")
    return "remplace un fichier existant"


@controle("Noms longs et accents")
def ctl_noms(dossier):
    nom = os.path.join(dossier, "é" * 40 + "_résumé n°1 & co (copie).txt")
    with open(nom, "w", encoding="utf-8") as f:
        f.write("x")
    if os.path.basename(nom) not in os.listdir(dossier):
        raise RuntimeError("nom non retrouve")
    return "accents, espaces et & acceptes"


@controle("Job Object (arret de l'arbre de processus)")
def ctl_job():
    if not EST_WINDOWS:
        return IGNORE
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.windll.kernel32
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.OpenProcess.restype = wintypes.HANDLE

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                    ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class IOCOUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in
                    ("ReadOp", "WriteOp", "OtherOp", "ReadBytes", "WriteBytes", "OtherBytes")]

    class EXTENDED(ctypes.Structure):
        _fields_ = [("Basic", BASIC), ("Io", IOCOUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    job = k32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError()
    infos = EXTENDED()
    infos.Basic.LimitFlags = 0x2000           # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k32.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(infos),
                                       ctypes.sizeof(infos)):
        raise ctypes.WinError()

    code = ("import subprocess, sys, time\n"
            "sys.stdin.readline()\n"
            "pf = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
            "print(pf.pid, flush=True)\n"
            "time.sleep(120)\n")
    fils = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, universal_newlines=True)
    try:
        if not k32.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(int(fils._handle))):
            raise ctypes.WinError()
        fils.stdin.write("go\n")
        fils.stdin.flush()
        pid_petit_fils = int(fils.stdout.readline())
        k32.TerminateJobObject(wintypes.HANDLE(job), 1)
        fils.wait(timeout=10)
        handle = k32.OpenProcess(0x00100000, False, pid_petit_fils)   # SYNCHRONIZE
        if handle:
            termine = k32.WaitForSingleObject(wintypes.HANDLE(handle), 5000) == 0
            k32.CloseHandle(wintypes.HANDLE(handle))
            if not termine:
                raise RuntimeError("le petit-fils (pid %d) tourne encore" % pid_petit_fils)
        return "fils et petit-fils arretes ensemble"
    finally:
        if fils.poll() is None:
            fils.kill()
        k32.CloseHandle(wintypes.HANDLE(job))


@controle("Partage reseau")
def ctl_partage(chemin):
    if not chemin:
        return IGNORE
    os.makedirs(chemin, exist_ok=True)
    fichier = os.path.join(chemin, "controle_copie.tmp")
    cible = os.path.join(chemin, "controle_copie.txt")
    with open(fichier, "wb") as f:
        f.write(b"x" * 1000)
    os.utime(fichier, (1700000000, 1700000001))
    os.replace(fichier, cible)
    st = os.stat(cible)
    os.remove(cible)
    ecart = st.st_mtime - 1700000001
    return "ecriture, renommage, suppression OK ; date de modification relue avec %.3f s d'ecart" % ecart


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--dossier", help="dossier local pour les fichiers temporaires")
    p.add_argument("--partage", help="dossier d'un partage reseau a tester (ecriture, renommage)")
    p.add_argument("--json", help="ecrit aussi le resultat dans ce fichier JSON")
    args = p.parse_args()

    dossier = tempfile.mkdtemp(prefix="controle_copie_", dir=args.dossier)
    print("Controle du serveur %s - %s\n" % (platform.node(), time.strftime("%Y-%m-%d %H:%M:%S")))
    try:
        ctl_python()
        ctl_systeme()
        ctl_modules()
        ctl_encodage()
        ctl_heure()
        ctl_sqlite(dossier)
        ctl_espace(dossier)
        ctl_verrou(dossier)
        ctl_replace(dossier)
        ctl_noms(dossier)
        ctl_job()
        ctl_partage(args.partage)
    finally:
        shutil.rmtree(dossier, ignore_errors=True)

    echecs = [r for r in resultats if r["etat"] == "ECHEC"]
    print("\n%s" % ("TOUS LES CONTROLES SONT BONS" if not echecs
                    else "%d CONTROLE(S) EN ECHEC" % len(echecs)))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"serveur": platform.node(), "python": platform.python_version(),
                       "resultats": resultats}, f, ensure_ascii=False, indent=1)
    return 1 if echecs else 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
