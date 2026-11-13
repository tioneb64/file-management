# bibliotheque: dates et attributs de fichiers Windows (ctypes), reperes portables quand c'est possible
"""Dates et attributs de fichiers Windows (ctypes) ; reperes portables quand c'est possible."""
import os
import stat

from outils.commun.erreurs import BUSINESS_RULE_VIOLATION, ErreurOutil

EST_WINDOWS = os.name == "nt"
ATTRIBUTS = {"lecture_seule": 0x1, "cache": 0x2, "systeme": 0x4, "archive": 0x20}
_EPOQUE_WINDOWS_NS = 11644473600 * 10 ** 9


def _filetime(ns_unix):
    """Nanosecondes Unix -> FILETIME (intervalles de 100 ns depuis 1601)."""
    return (ns_unix + _EPOQUE_WINDOWS_NS) // 100


def fixer_dates(chemin, creation_ns=None, modification_ns=None, acces_ns=None):
    """Fixe les dates (nanosecondes Unix) ; None = inchangee. La date de creation n'existe que sous Windows."""
    if creation_ns is not None:
        if not EST_WINDOWS:
            raise ErreurOutil("la date de creation ne peut etre fixee que sous Windows", BUSINESS_RULE_VIOLATION)
        _fixer_filetime(chemin, creation_ns, modification_ns, acces_ns)
        return
    if modification_ns is None and acces_ns is None:
        return
    info = os.stat(chemin)
    os.utime(chemin, ns=(acces_ns if acces_ns is not None else info.st_atime_ns,
                         modification_ns if modification_ns is not None else info.st_mtime_ns))


def _fixer_filetime(chemin, creation_ns, modification_ns, acces_ns):
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.SetFileTime.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    k32.SetFileTime.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    FILE_WRITE_ATTRIBUTES, PARTAGE, OUVRIR, SEMANTIQUE_SAUVEGARDE = 0x100, 0x7, 3, 0x02000000
    handle = k32.CreateFileW(os.path.abspath(chemin), FILE_WRITE_ATTRIBUTES, PARTAGE, None, OUVRIR,
                             SEMANTIQUE_SAUVEGARDE, None)
    if handle is None or handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        def ft(ns):
            return None if ns is None else ctypes.byref(ctypes.c_ulonglong(_filetime(ns)))
        if not k32.SetFileTime(handle, ft(creation_ns), ft(acces_ns), ft(modification_ns)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        k32.CloseHandle(handle)


def lire_attributs(chemin):
    """{'lecture_seule': bool, 'cache': bool, 'systeme': bool, 'archive': bool}."""
    info = os.stat(chemin)
    if EST_WINDOWS:
        valeur = info.st_file_attributes
        return {nom: bool(valeur & bit) for nom, bit in ATTRIBUTS.items()}
    return {"lecture_seule": not (info.st_mode & stat.S_IWUSR), "cache": False, "systeme": False, "archive": False}


def fixer_attributs(chemin, changements):
    """`changements` : {nom: True/False}. Les autres attributs sont conserves. Hors Windows, seule la lecture seule
    existe (bit d'ecriture du proprietaire)."""
    if EST_WINDOWS:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
        k32.SetFileAttributesW.restype = wintypes.BOOL
        valeur = os.stat(chemin).st_file_attributes
        for nom, actif in changements.items():
            valeur = valeur | ATTRIBUTS[nom] if actif else valeur & ~ATTRIBUTS[nom]
        if not k32.SetFileAttributesW(os.path.abspath(chemin), valeur & 0xFFFF):
            raise ctypes.WinError(ctypes.get_last_error())
        return
    autres = [n for n in changements if n != "lecture_seule"]
    if autres:
        raise ErreurOutil("attributs %s : Windows seulement" % ", ".join(autres), BUSINESS_RULE_VIOLATION)
    mode = os.stat(chemin).st_mode
    os.chmod(chemin, mode & ~stat.S_IWUSR if changements["lecture_seule"] else mode | stat.S_IWUSR)
