# bibliotheque: detection des dependances facultatives (7z, rar, soffice, pyzipper, Pillow) : code retour 4 et message clair, jamais de trace
"""Dependances facultatives : programmes externes (7z, rar, soffice) et modules (pyzipper, Pillow).

Absentes, elles ne produisent jamais de trace Python : DependanceAbsente -> code retour 4 et un message
qui dit quoi installer ou quelle variable d'environnement renseigner.
"""
import importlib
import os
import shutil
import subprocess

from outils.commun.erreurs import DependanceAbsente

# variable d'environnement qui force le chemin du programme, noms a chercher dans le PATH, dossiers usuels
PROGRAMMES = {
    "7z": ("OUTIL_7Z", ("7z", "7za", "7zz"), (r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"),
           "installer 7-Zip (https://www.7-zip.org) ou renseigner OUTIL_7Z avec le chemin de 7z.exe"),
    "rar": ("OUTIL_RAR", ("rar",), (r"C:\Program Files\WinRAR\Rar.exe", r"C:\Program Files (x86)\WinRAR\Rar.exe"),
            "installer WinRAR (rar.exe est l'outil de creation ; 7-Zip sait seulement lire le RAR) ou "
            "renseigner OUTIL_RAR"),
    "soffice": ("OUTIL_SOFFICE", ("soffice", "libreoffice"),
                (r"C:\Program Files\LibreOffice\program\soffice.exe",
                 r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
                "installer LibreOffice ou renseigner OUTIL_SOFFICE avec le chemin de soffice.exe"),
}


def trouver_programme(nom, env=None):
    """Chemin du programme externe `nom` ('7z', 'rar', 'soffice') ou DependanceAbsente."""
    env = os.environ if env is None else env
    variable, noms, usuels, aide = PROGRAMMES[nom]
    force = env.get(variable)
    if force:
        if os.path.isfile(force):
            return force
        raise DependanceAbsente("%s : %s=%s n'existe pas" % (nom, variable, force))
    for candidat in noms:
        chemin = shutil.which(candidat)
        if chemin:
            return chemin
    for chemin in usuels:
        if os.path.isfile(chemin):
            return chemin
    raise DependanceAbsente("programme %s introuvable : %s" % (nom, aide))


def module_optionnel(nom, installer=None):
    """Importe un module facultatif ou leve DependanceAbsente."""
    try:
        return importlib.import_module(nom)
    except ImportError:
        raise DependanceAbsente("module Python '%s' absent : pip install %s" % (nom, installer or nom))


def module_disponible(nom):
    try:
        importlib.import_module(nom)
        return True
    except ImportError:
        return False


def executer_externe(argv, secrets=(), delai=3600, dossier=None, entree=None):
    """Lance un programme externe SANS shell. Renvoie (code, sortie texte). `secrets` : valeurs a masquer
    dans la sortie rendue (un mot de passe qui serait reaffiche). Un lancement impossible leve
    DependanceAbsente ; un delai depasse, ErreurOutil (TIMEOUT)."""
    from outils.commun.erreurs import ErreurOutil, TIMEOUT
    try:
        resultat = subprocess.run(argv, cwd=dossier, input=entree, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=delai,
                                  stdin=None if entree is not None else subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise ErreurOutil("delai depasse (%d s) pour %s" % (delai, os.path.basename(argv[0])), TIMEOUT)
    except OSError as e:
        raise DependanceAbsente("lancement impossible de %s : %s" % (argv[0], e))
    sortie = _decoder(resultat.stdout or b"")
    for secret in secrets:
        if secret:
            sortie = sortie.replace(secret, "***")
    return resultat.returncode, sortie


def _decoder(octets):
    try:
        return octets.decode("utf-8")
    except UnicodeDecodeError:
        return octets.decode("cp850" if os.name == "nt" else "latin-1", "replace")


def masquer(argv, secrets):
    """Ligne de commande lisible pour le journal, sans les secrets."""
    texte = []
    for element in argv:
        for secret in secrets:
            if secret:
                element = element.replace(secret, "***")
        texte.append(element)
    return " ".join(texte)
