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
