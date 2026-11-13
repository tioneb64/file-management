# bibliotheque: exceptions des outils, codes retour (0 a 4) et types d'erreur du journal
"""Exceptions des outils et correspondance avec les codes retour et les types d'erreur du journal."""
import errno

CODE_OK = 0
CODE_RIEN = 1            # "rien a faire" : seulement avec --code-si-rien 1 (le moteur accepte 0 et 1)
CODE_ERREUR = 2          # erreur d'execution (au moins un element en echec)
CODE_PARAMETRES = 3      # parametres invalides
CODE_DEPENDANCE = 4      # dependance externe absente (7z, soffice, Pillow...)

# Types d'erreur utilises (meme vocabulaire que le moteur, docs/02-moteur.md section 11.4)
FILE_IO_ERROR = "FILE_IO_ERROR"
FILE_NOT_FOUND = "FILE_NOT_FOUND"
DUPLICATE_ENTITY = "DUPLICATE_ENTITY"
RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
TIMEOUT = "TIMEOUT"
INTERNAL_ERROR = "INTERNAL_ERROR"
BUSINESS_RULE_VIOLATION = "BUSINESS_RULE_VIOLATION"
TYPES_ERREUR = (FILE_IO_ERROR, FILE_NOT_FOUND, DUPLICATE_ENTITY, RESOURCE_EXHAUSTED,
                EXTERNAL_SERVICE_ERROR, TIMEOUT, INTERNAL_ERROR, BUSINESS_RULE_VIOLATION)


class ErreurOutil(Exception):
    """Echec d'UN element : journalise (ERROR) et l'outil passe au suivant."""

    def __init__(self, message, type_erreur=FILE_IO_ERROR):
        Exception.__init__(self, message)
        self.type_erreur = type_erreur


class ErreurParametres(Exception):
    """Parametres invalides : l'outil s'arrete avec le code 3."""


class DependanceAbsente(Exception):
    """Programme ou module facultatif absent : l'outil s'arrete avec le code 4 et un message clair."""


class ArretOutil(Exception):
    """Leve apres la premiere erreur avec --arreter-si-erreur (l'erreur est deja journalisee)."""


def type_erreur_os(e):
    """Type d'erreur du journal pour une exception du systeme de fichiers."""
    if isinstance(e, FileNotFoundError):
        return FILE_NOT_FOUND
    if isinstance(e, FileExistsError):
        return DUPLICATE_ENTITY
    if getattr(e, "errno", None) in (errno.ENOSPC, getattr(errno, "EDQUOT", -1)):
        return RESOURCE_EXHAUSTED
    return FILE_IO_ERROR


def decrire_os(e):
    """Texte court d'une OSError : cause et fichier concerne."""
    cause = e.strerror or str(e)
    return "%s (%s)" % (cause, e.filename) if getattr(e, "filename", None) else cause
