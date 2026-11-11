"""Chemins, noms et espace disque : modeles de nom, archive, noms Windows valides, volumes.

Specification : docs/01-parametrage.md section 5, docs/02-moteur.md sections 7 et 8.
"""
import fnmatch
import os
import re
import shutil

NOMS_RESERVES = {"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)} \
    | {"LPT%d" % i for i in range(1, 10)}
RE_VARIABLE = re.compile(r"\{([^{}]*)\}")
LONGUEUR_NOM_MAX = 255


def variables_date(instant):
    """instant : datetime local. Valeurs des variables {AAAA} {MM} {JJ} {hh} {mm} {ss}."""
    return {"AAAA": "%04d" % instant.year, "MM": "%02d" % instant.month, "JJ": "%02d" % instant.day,
            "hh": "%02d" % instant.hour, "mm": "%02d" % instant.minute, "ss": "%02d" % instant.second}


def remplacer_variables(modele, valeurs):
    """Remplace {nom} par sa valeur ; une variable inconnue est laissee telle quelle."""
    return RE_VARIABLE.sub(lambda m: valeurs.get(m.group(1), m.group(0)), modele)


def decouper_nom(nom):
    """'rapport.final.csv' -> ('rapport.final', '.csv') ; un nom commencant par un point n'a pas d'extension."""
    base, ext = os.path.splitext(nom)
    return (nom, "") if not base else (base, ext)


def appliquer_modele_nom(modele, nom, instant):
    """Nom final d'un fichier : {nom} sans extension, {ext} avec le point, variables de date."""
    base, ext = decouper_nom(nom)
    valeurs = dict(variables_date(instant), nom=base, ext=ext)
    return remplacer_variables(modele, valeurs)


def nom_avec_suffixe(nom, instant, compteur=0):
    """Ajoute un horodatage : 'a.csv' -> 'a_20261103_063012.csv' (puis '_2', '_3'... au besoin)."""
    base, ext = decouper_nom(nom)
    v = variables_date(instant)
    suffixe = "_%s%s%s_%s%s%s" % (v["AAAA"], v["MM"], v["JJ"], v["hh"], v["mm"], v["ss"])
    if compteur:
        suffixe += "_%d" % (compteur + 1)
    return base + suffixe + ext


MARQUEUR_HORODATAGE = "_traite_"
RE_HORODATE = re.compile(r"_traite_\d{8}_\d{6}(_\d+)?$")


def nom_horodate(nom, instant, compteur=0):
    """Marque un fichier traite : 'a.csv' -> 'a_traite_20261111_103012.csv' (puis '_2', '_3'... au
    besoin). Le marqueur '_traite_' distingue ce nom d'une date ordinaire du nom d'origine."""
    base, ext = decouper_nom(nom)
    v = variables_date(instant)
    suffixe = "%s%s%s%s_%s%s%s" % (MARQUEUR_HORODATAGE, v["AAAA"], v["MM"], v["JJ"], v["hh"], v["mm"], v["ss"])
    if compteur:
        suffixe += "_%d" % (compteur + 1)
    return base + suffixe + ext


def est_horodate(nom):
    """Vrai si `nom` porte deja la marque de nom_horodate (le fichier a deja ete traite)."""
    return bool(RE_HORODATE.search(decouper_nom(nom)[0]))


def nom_invalide(nom):
    """Raison pour laquelle un NOM de fichier est refuse par Windows, ou None s'il est valide."""
    if not nom or not nom.strip():
        return "nom vide"
    if len(nom) > LONGUEUR_NOM_MAX:
        return "nom de plus de %d caracteres" % LONGUEUR_NOM_MAX
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', nom):
        return "caractere interdit dans '%s'" % nom
    if nom[-1] in " .":
        return "un nom ne peut pas finir par un point ou un espace : '%s'" % nom
    if nom.split(".")[0].strip().upper() in NOMS_RESERVES:
        return "nom reserve par Windows : '%s'" % nom
    return None


def normaliser(chemin):
    return os.path.normcase(os.path.normpath(os.path.expandvars(chemin)))


def resoudre_archive(modele, racine_source, instant):
    """Chemin reel de l'archive : absolu tel quel, relatif calcule depuis la racine de source,
    variables de date remplacees."""
    modele = remplacer_variables(modele, variables_date(instant))
    modele = os.path.expandvars(modele)
    if os.path.isabs(modele) or modele.startswith("\\\\"):
        return os.path.normpath(modele)
    return os.path.normpath(os.path.join(racine_source, modele))


def exclusion_dossiers(racine_source, modele_archive, autres_dossiers=()):
    """Fonction `est_exclu(composants)` : vrai pour un sous-dossier de la source qui est le
    dossier d'archive (toute date comprise) ou un autre dossier a ne pas parcourir.
    composants : tuple des noms du dossier relativement a la racine."""
    motifs = []
    if modele_archive:
        modele = os.path.expandvars(modele_archive)
        if not (os.path.isabs(modele) or modele.startswith("\\\\")):
            relatif = os.path.normpath(modele)
            motifs.append([RE_VARIABLE.sub("*", c).lower() for c in relatif.split(os.sep)
                           if c and c != "."])
        else:
            absolu = os.path.normpath(RE_VARIABLE.sub("*", modele))
            racine = normaliser(racine_source) + os.sep
            if normaliser(absolu).startswith(racine):
                relatif = os.path.relpath(absolu, racine_source)
                motifs.append([c.lower() for c in relatif.split(os.sep)])
    for autre in autres_dossiers:
        if autre and normaliser(autre).startswith(normaliser(racine_source) + os.sep):
            motifs.append([c.lower() for c in os.path.relpath(autre, racine_source).split(os.sep)])

    def est_exclu(composants):
        bas = [c.lower() for c in composants]
        return any(len(bas) >= len(m) and all(fnmatch.fnmatchcase(bas[i], m[i]) for i in range(len(m)))
                   for m in motifs if m)
    return est_exclu


# --------------------------------------------------------------------------- #
# Volumes et espace disque
# --------------------------------------------------------------------------- #
def plus_proche_existant(chemin):
    chemin = os.path.abspath(chemin)
    while not os.path.exists(chemin):
        parent = os.path.dirname(chemin)
        if parent == chemin:
            break
        chemin = parent
    return chemin


def meme_volume(a, b):
    """Vrai si les deux chemins sont sur le meme volume (identifiant `st_dev`). En cas de doute
    (identifiant nul ou erreur), faux : on copie au lieu de renommer."""
    try:
        da, db = os.stat(plus_proche_existant(a)).st_dev, os.stat(plus_proche_existant(b)).st_dev
    except OSError:
        return False
    return bool(da) and da == db


def espace_disponible(chemin):
    """Octets disponibles POUR LE COMPTE QUI EXECUTE (quotas compris). Windows : appel
    GetDiskFreeSpaceExW, qui fonctionne aussi sur un chemin UNC ; ailleurs shutil."""
    cible = plus_proche_existant(chemin)
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        libre_appelant = ctypes.c_ulonglong()
        fonction = ctypes.windll.kernel32.GetDiskFreeSpaceExW
        fonction.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_ulonglong),
                             ctypes.POINTER(ctypes.c_ulonglong), ctypes.POINTER(ctypes.c_ulonglong)]
        total, libre_total = ctypes.c_ulonglong(), ctypes.c_ulonglong()
        if not fonction(cible, ctypes.byref(libre_appelant), ctypes.byref(total),
                        ctypes.byref(libre_total)):
            raise ctypes.WinError()
        return libre_appelant.value
    return shutil.disk_usage(cible).free
