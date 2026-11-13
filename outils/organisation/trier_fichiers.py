# outil: trier_fichiers
# description: Range les fichiers dans des sous-dossiers de --vers : --par type (images, documents, tableurs, archives, audio, video, donnees, code, autres), --par extension (un dossier par extension) ou --par date (dossier AAAA\MM par defaut,...
# parametre: --par {type,date,extension} | obligatoire | critere de tri
# parametre: --vers DOSSIER | obligatoire | dossier racine du rangement (cree si absent)
# parametre: --copier | facultatif | copie (verifiee par SHA-256) au lieu de deplacer
# parametre: --format-date FORMAT | facultatif | sous-dossier pour --par date (defaut %Y/%m)
# parametre: --source-date {modification,creation,exif} | facultatif | date utilisee pour --par date (exif : prise de vue d'un JPEG, repli sur la modification)
# parametre: --si-existe {erreur,ignorer,ecraser,suffixe} | facultatif | si le nom existe deja dans la destination (defaut : erreur ; suffixe : _1, _2...)
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Trie des fichiers dans des sous-dossiers : par type, par date ou par extension."""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun import exif
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import DUPLICATE_ENTITY, ErreurOutil, ErreurParametres
from outils.commun.fichiers import copier_verifie, deplacer_fichier
from outils.commun.outil import Outil

TYPES = {
    "images": (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic", ".svg"),
    "documents": (".doc", ".docx", ".odt", ".rtf", ".pdf", ".txt", ".md"),
    "tableurs": (".xls", ".xlsx", ".xlsm", ".ods", ".csv"),
    "presentations": (".ppt", ".pptx", ".odp"),
    "archives": (".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".iso"),
    "audio": (".mp3", ".wav", ".flac", ".ogg", ".m4a", ".wma"),
    "video": (".mp4", ".avi", ".mkv", ".mov", ".wmv", ".mpg", ".mpeg"),
    "donnees": (".xml", ".json", ".jsonl", ".yaml", ".yml", ".sql", ".db", ".sqlite", ".log"),
    "code": (".py", ".ps1", ".bat", ".cmd", ".js", ".cs", ".java", ".sh", ".xaml", ".html", ".css"),
}

OUTIL = Outil("trier_fichiers", "Range les fichiers dans des sous-dossiers de --vers : --par type (images, documents, "
              "tableurs, archives, audio, video, donnees, code, autres), --par extension (un dossier par "
              "extension) ou --par date (dossier AAAA\\MM par defaut, --format-date pour changer). Deplace par defaut "
              "(--copier pour copier avec verification SHA-256). Un nom deja pris est une erreur de l'element "
              "sauf --si-existe.", "organisation")


@OUTIL.arguments
def arguments(p):
    options_entrees(p)
    p.add_argument("--par", required=True, choices=("type", "date", "extension"), help="critere de tri")
    p.add_argument("--vers", required=True, metavar="DOSSIER", help="dossier racine du rangement (cree si absent)")
    p.add_argument("--copier", action="store_true", help="copie (verifiee par SHA-256) au lieu de deplacer")
    p.add_argument("--format-date", default="%Y/%m", metavar="FORMAT", help="sous-dossier pour --par date (defaut %%Y/%%m)")
    p.add_argument("--source-date", choices=("modification", "creation", "exif"), default="modification",
                   help="date utilisee pour --par date (exif : prise de vue d'un JPEG, repli sur la modification)")
    p.add_argument("--si-existe", choices=("erreur", "ignorer", "ecraser", "suffixe"), default="erreur",
                   help="si le nom existe deja dans la destination (defaut : erreur ; suffixe : _1, _2...)")


def sous_dossier(chemin, args):
    ext = os.path.splitext(chemin)[1].lower()
    if args.par == "extension":
        return ext.lstrip(".") or "sans_extension"
    if args.par == "type":
        return next((nom for nom, exts in TYPES.items() if ext in exts), "autres")
    info = os.stat(chemin)
    instant = datetime.fromtimestamp(info.st_ctime if args.source_date == "creation" and os.name == "nt"
                                     else info.st_mtime)
    if args.source_date == "exif":
        instant = exif.date_prise_de_vue(chemin) or instant
    return instant.strftime(args.format_date)


@OUTIL.principal
def principal(ctx, args):
    try:
        datetime.now().strftime(args.format_date)
    except ValueError as e:
        raise ErreurParametres("format de date invalide : %s" % e)
    racine = os.path.abspath(args.vers)
    for chemin, _ in ctx.fichiers():
        if os.path.abspath(chemin).startswith(racine + os.sep):
            ctx.debug("deja_range", "Deja dans le dossier de rangement : %s" % os.path.basename(chemin), fichier=chemin)
            continue
        with ctx.tolerer("tri_echec", fichier=chemin):
            dossier = os.path.join(racine, *sous_dossier(chemin, args).replace("\\", "/").split("/"))
            cible = os.path.join(dossier, os.path.basename(chemin))
            ecraser = args.si_existe == "ecraser"
            if os.path.lexists(cible) and not ecraser:
                if args.si_existe == "ignorer":
                    ctx.compter("ignores")
                    ctx.debug("fichier_ignore", "Existe deja, ignore : %s" % os.path.basename(chemin), fichier=chemin)
                    continue
                if args.si_existe == "suffixe":
                    base, ext = os.path.splitext(cible)
                    n = 1
                    while os.path.lexists("%s_%d%s" % (base, n, ext)):
                        n += 1
                    cible = "%s_%d%s" % (base, n, ext)
                else:
                    raise ErreurOutil("le fichier existe deja dans la destination : %s" % cible, DUPLICATE_ENTITY)
            if ctx.simulation:
                ctx.action("fichier_a_ranger", "Serait %s vers %s : %s" % ("copie" if args.copier else "deplace",
                           os.path.relpath(dossier, racine), os.path.basename(chemin)), fichier=chemin, cible=cible)
                continue
            if args.copier:
                os.makedirs(dossier, exist_ok=True)
                empreinte = copier_verifie(chemin, cible, ecraser)
            else:
                deplacer_fichier(chemin, cible, ecraser)
                empreinte = None
            ctx.action("fichier_range", "%s vers %s : %s" % ("Copie" if args.copier else "Deplace",
                       os.path.relpath(dossier, racine), os.path.basename(chemin)), fichier=chemin, cible=cible,
                       sha256=empreinte)


if __name__ == "__main__":
    OUTIL.lancer()
