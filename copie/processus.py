"""Processus du systeme : date de creation et detection d'un processus encore vivant.

Un identifiant de processus peut etre reutilise par Windows : on compare donc aussi la date de
creation (docs/02-moteur.md, section 2). Bibliotheque standard + ctypes.
"""
import os

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
ECART_FILETIME = 11644473600                 # secondes entre 1601 et 1970


def date_creation(pid):
    """Date de creation du processus en secondes depuis 1970, ou None s'il n'existe pas.
    Hors Windows : None si absent, 0 si present (date inconnue)."""
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return 0
        except OSError:
            return None
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None                              # introuvable (ou acces refuse : on le dit vivant ci-dessous)
    try:
        code = wintypes.DWORD()
        if k32.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value != STILL_ACTIVE:
            return None                          # termine, mais un handle d'un autre processus le retient
        creation, sortie, noyau, utilisateur = (wintypes.FILETIME() for _ in range(4))
        if not k32.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(sortie),
                                   ctypes.byref(noyau), ctypes.byref(utilisateur)):
            return 0
        ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return ticks / 1e7 - ECART_FILETIME
    finally:
        k32.CloseHandle(handle)


def vivant(pid, cree_le):
    """Vrai si le processus `pid` existe encore ET a la date de creation memorisee (a 2 s pres).
    Une date inconnue (None ou 0) se contente de l'existence du processus."""
    if pid is None:
        return False
    actuelle = date_creation(pid)
    if actuelle is None:
        return False
    if not cree_le or not actuelle:
        return True
    return abs(actuelle - cree_le) < 2


# --------------------------------------------------------------------------- #
# Arret d'un arbre de processus
# --------------------------------------------------------------------------- #
def tuer_arbre(pid):
    """Arrete un processus et tous ses descendants (taskkill /T /F). Sert aux processus dont on
    ne tient pas le Job Object (lancements d'un autre orchestrateur). Renvoie True si taskkill
    a reussi. Ne s'arrete jamais soi-meme."""
    import subprocess
    if pid == os.getpid():
        return False
    try:
        if os.name == "nt":
            resultat = subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True,
                                      timeout=30)
            return resultat.returncode == 0
        import signal
        os.kill(pid, signal.SIGKILL)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


class JobObject(object):
    """Job Object Windows : tout processus place dedans, et ses descendants, est arrete par
    terminer() ou a la fermeture du dernier handle (KILL_ON_JOB_CLOSE). Hors Windows ou si le
    processus ne peut pas y etre place, `actif` est faux : l'appelant utilise tuer_arbre()."""

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    JobObjectExtendedLimitInformation = 9

    def __init__(self, kill_on_close=True):
        self.handle = None
        self.actif = False
        self.kill_on_close = kill_on_close
        if os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes
        self._ct, self._wt = ctypes, wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._k32 = k32

        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class IOCOUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in
                        ("ReadOp", "WriteOp", "OtherOp", "ReadBytes", "WriteBytes", "OtherBytes")]

        class EXTENDED(ctypes.Structure):
            _fields_ = [("Basic", BASIC), ("Io", IOCOUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]
        handle = k32.CreateJobObjectW(None, None)
        if not handle:
            return
        infos = EXTENDED()
        infos.Basic.LimitFlags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE if self.kill_on_close else 0
        if not k32.SetInformationJobObject(handle, self.JobObjectExtendedLimitInformation,
                                           ctypes.byref(infos), ctypes.sizeof(infos)):
            k32.CloseHandle(handle)
            return
        self.handle = handle

    def assigner(self, popen):
        """Place le processus dans le job. Renvoie True en cas de succes."""
        if self.handle is None:
            return False
        ok = self._k32.AssignProcessToJobObject(self.handle, self._wt.HANDLE(int(popen._handle)))
        self.actif = bool(ok)
        return self.actif

    def terminer(self):
        """Arrete tous les processus du job. Renvoie True si le job a ete arrete."""
        if self.handle is None or not self.actif:
            return False
        return bool(self._k32.TerminateJobObject(self.handle, 1))

    def fermer(self):
        """Ferme le job : les processus restants sont arretes (KILL_ON_JOB_CLOSE)."""
        if self.handle is not None:
            self._k32.CloseHandle(self.handle)
            self.handle = None
            self.actif = False
