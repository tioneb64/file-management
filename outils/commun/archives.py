# bibliotheque: creation et extraction d'archives (zip, tar.*, 7z, rar, iso) partagees par les outils de compression
"""Creation et extraction d'archives (zip, tar.*, 7z, rar, iso) partagees par les outils de compression.

Bibliotheque standard pour zip et tar ; 7z.exe pour 7z, rar (extraction) et iso (extraction) ; rar.exe pour
creer un rar ; pyzipper (facultatif) pour le zip AES-256. Rien n'est ecrase sans `ecraser`, tout est ecrit
sous un nom temporaire puis renomme, et l'extraction refuse tout chemin qui sort du dossier de destination.
"""
import contextlib
import os
import shutil
import tarfile
import zipfile
import zlib

from outils.commun import dependances
from outils.commun.entrees import retenu
from outils.commun.erreurs import (BUSINESS_RULE_VIOLATION, DUPLICATE_ENTITY, EXTERNAL_SERVICE_ERROR, FILE_IO_ERROR,
                                   FILE_NOT_FOUND, RESOURCE_EXHAUSTED, DependanceAbsente, ErreurOutil)
from outils.commun.fichiers import (SUFFIXE_TEMPORAIRE, chemin_sous, est_dans, sortie_atomique, taille_lisible,
                                    verifier_ecrasement)

MODES_TAR = {".tar.gz": "w:gz", ".tgz": "w:gz", ".tar.bz2": "w:bz2", ".tbz2": "w:bz2", ".tar.xz": "w:xz",
             ".txz": "w:xz", ".tar": "w"}
EXTENSIONS_7Z = (".7z", ".rar", ".iso")
TAILLE_MAX_DEFAUT = 20 * 1024 ** 3


def format_archive(nom):
    """'zip', 'tar', '7z', 'rar', 'iso' d'apres l'extension, ou None."""
    bas = nom.lower()
    if bas.endswith(".zip"):
        return "zip"
    if any(bas.endswith(e) for e in MODES_TAR):
        return "tar"
    for e in EXTENSIONS_7Z:
        if bas.endswith(e):
            return e[1:]
    return None


# --------------------------------------------------------------------------- #
# Elements a archiver
# --------------------------------------------------------------------------- #
def elements_a_archiver(ctx, chemins, exclus=()):
    """Liste (chemin_disque, nom_dans_l'archive, est_dossier). Un fichier est range sous son nom ; un dossier
    sous son nom avec tout son contenu (masque / exclure s'appliquent aux fichiers). `exclus` : chemins a ne
    jamais prendre (l'archive en cours de creation)."""
    masques = getattr(ctx.args, "masque", None) or []
    exclusions = getattr(ctx.args, "exclure", None) or []
    exclus = [os.path.normcase(os.path.abspath(e)) for e in exclus]
    elements, vus = [], set()

    def ajouter(disque, nom, dossier):
        if os.path.normcase(os.path.abspath(disque)) in exclus:
            return
        if nom in vus:
            ctx.echec("doublon_nom_archive", "Deux elements portent le meme nom dans l'archive : %s" % nom,
                      DUPLICATE_ENTITY, fichier=disque)
            return
        vus.add(nom)
        elements.append((disque, nom, dossier))

    for chemin in chemins:
        base = os.path.basename(os.path.abspath(chemin).rstrip("\\/")) or "racine"
        if os.path.isdir(chemin):
            ajouter(chemin, base + "/", True)
            for racine, sous, noms in os.walk(chemin):
                sous[:] = sorted(d for d in sous if not os.path.islink(os.path.join(racine, d)))
                for d in sous:
                    ajouter(os.path.join(racine, d),
                            base + "/" + os.path.relpath(os.path.join(racine, d), chemin).replace(os.sep, "/") + "/",
                            True)
                for nom in sorted(noms):
                    complet = os.path.join(racine, nom)
                    rel = os.path.relpath(complet, chemin).replace(os.sep, "/")
                    if retenu(nom, rel, masques, exclusions):
                        ajouter(complet, base + "/" + rel, False)
        elif os.path.isfile(chemin):
            if retenu(base, base, masques, exclusions):
                ajouter(chemin, base, False)
        else:
            ctx.echec("fichier_introuvable", "Fichier ou dossier introuvable : %s" % chemin, FILE_NOT_FOUND,
                      fichier=chemin)
    return elements


# --------------------------------------------------------------------------- #
# Creation
# --------------------------------------------------------------------------- #
def creer_zip(ctx, elements, temporaire, niveau=6, mot_de_passe=None, module=None):
    """Zip standard, ou AES-256 avec `module` (pyzipper). Un element illisible est une erreur de l'element."""
    if module is not None:
        zf = module.AESZipFile(temporaire, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=niveau,
                               allowZip64=True)
        zf.setpassword(mot_de_passe.encode("utf-8"))
        zf.setencryption(module.WZ_AES, nbits=256)
    else:
        zf = zipfile.ZipFile(temporaire, "w", zipfile.ZIP_DEFLATED, compresslevel=niveau, allowZip64=True)
    with zf:
        for disque, nom, dossier in elements:
            with ctx.tolerer("ajout_archive_echec", fichier=disque):
                zf.write(disque, nom)
                ctx.action("fichier_archive_ajoute", "Ajoute a l'archive : %s" % nom.rstrip("/"),
                           compteur="dossiers" if dossier else "fichiers", fichier=disque,
                           taille=None if dossier else os.path.getsize(disque))


def creer_tar(ctx, elements, temporaire, mode, niveau=6):
    options = {"compresslevel": niveau} if mode in ("w:gz", "w:bz2") else {}
    with tarfile.open(temporaire, mode, **options) as tf:
        for disque, nom, dossier in elements:
            with ctx.tolerer("ajout_archive_echec", fichier=disque):
                tf.add(disque, arcname=nom.rstrip("/"), recursive=False)
                ctx.action("fichier_archive_ajoute", "Ajoute a l'archive : %s" % nom.rstrip("/"),
                           compteur="dossiers" if dossier else "fichiers", fichier=disque,
                           taille=None if dossier else os.path.getsize(disque))


def lancer_7z_ou_rar(ctx, programme, argv, secrets=()):
    """Lance 7z / rar ; code 0 : bon, 1 : avertissement (journalise), autre : ErreurOutil."""
    code, sortie = dependances.executer_externe(argv, secrets=secrets)
    resume = sortie.strip().replace("\r", "")[-600:]
    if code == 1:
        ctx.avertir("programme_externe_avertissement", "%s a rendu des avertissements : %s" % (programme, resume),
                    commande=dependances.masquer(argv, secrets))
    elif code != 0:
        raise ErreurOutil("%s a echoue (code %s) : %s" % (programme, code, resume), EXTERNAL_SERVICE_ERROR)
    return sortie


@contextlib.contextmanager
def sortie_dans_dossier_temporaire(chemin, ecraser):
    """Pour les programmes qui exigent un nom d'archive correct : ils ecrivent dans
    <archive>.copie_en_cours\\<nom final> ; le resultat est ensuite place sous son nom definitif."""
    verifier_ecrasement(chemin, ecraser)
    dossier = chemin + SUFFIXE_TEMPORAIRE
    shutil.rmtree(dossier, ignore_errors=True)
    os.makedirs(dossier)
    interne = os.path.join(dossier, os.path.basename(chemin))
    try:
        yield interne
        verifier_ecrasement(chemin, ecraser)
        os.replace(interne, chemin)
    finally:
        shutil.rmtree(dossier, ignore_errors=True)


def creer_avec_7z(ctx, chemins_elements, interne, type_7z, niveau=5, mot_de_passe=None, zip_aes=False,
                  env=None):
    """7z.exe a -t<type> ... Les elements sont donnes par leur chemin ; 7z range chacun sous son nom.
    ATTENTION : le mot de passe passe sur la ligne de commande de 7z (visible des autres processus
    locaux) : preferer pyzipper pour le zip chiffre."""
    programme = dependances.trouver_programme("7z", env)
    argv = [programme, "a", "-t" + type_7z, "-mx=%d" % niveau, "-y", "-bd"]
    secrets = []
    if mot_de_passe:
        argv.append("-p" + mot_de_passe)
        secrets.append(mot_de_passe)
        if type_7z == "7z":
            argv.append("-mhe=on")                     # noms de fichiers chiffres aussi
        if zip_aes:
            argv.append("-mem=AES256")
        ctx.avertir("mot_de_passe_ligne_de_commande",
                    "Le mot de passe est transmis a 7z sur sa ligne de commande (visible des autres processus "
                    "du serveur) : installer pyzipper pour un zip AES sans ce defaut")
    argv.append(interne)
    argv.extend(chemins_elements)
    lancer_7z_ou_rar(ctx, "7z", argv, secrets)


def creer_rar(ctx, chemins_elements, interne, niveau=3, mot_de_passe=None, env=None):
    programme = dependances.trouver_programme("rar", env)
    argv = [programme, "a", "-m%d" % niveau, "-ep1", "-y", "-idq"]
    secrets = []
    if mot_de_passe:
        argv.append("-hp" + mot_de_passe)
        secrets.append(mot_de_passe)
        ctx.avertir("mot_de_passe_ligne_de_commande",
                    "Le mot de passe est transmis a rar sur sa ligne de commande (visible des autres processus)")
    argv.append(interne)
    argv.extend(chemins_elements)
    lancer_7z_ou_rar(ctx, "rar", argv, secrets)


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
def _verifier_place(vers, octets):
    existant = vers
    while existant and not os.path.exists(existant):
        parent = os.path.dirname(existant)
        if parent == existant:
            break
        existant = parent
    libre = shutil.disk_usage(existant or ".").free
    if octets > libre:
        raise ErreurOutil("espace insuffisant dans %s : %s a extraire, %s libres"
                          % (vers, taille_lisible(octets), taille_lisible(libre)), RESOURCE_EXHAUSTED)


def _copier_vers(ctx, flux, cible, ecraser, date=None, evenement="fichier_extrait", taille=None):
    with sortie_atomique(cible, ecraser) as tmp:
        with open(tmp, "wb") as f:
            shutil.copyfileobj(flux, f, 1024 * 1024)
    if date:
        try:
            os.utime(cible, (date, date))
        except OSError:
            pass
    ctx.action(evenement, "Extrait : %s" % os.path.basename(cible), fichier=cible,
               taille=taille if taille is not None else os.path.getsize(cible))


def extraire_zip(ctx, archive, vers, ecraser, mot_de_passe=None, taille_max=TAILLE_MAX_DEFAUT, module=None):
    import time
    try:
        zf = (module.AESZipFile(archive) if module is not None else zipfile.ZipFile(archive))
    except (zipfile.BadZipFile, EOFError, zlib.error) as e:
        raise ErreurOutil("archive zip illisible : %s (%s)" % (os.path.basename(archive), e), FILE_IO_ERROR)
    with zf:
        infos = zf.infolist()
        if module is None and any(i.compress_type == 99 for i in infos):
            raise DependanceAbsente("archive zip chiffree en AES : installer pyzipper (pip install pyzipper) ou 7-Zip")
        total = sum(i.file_size for i in infos)
        if total > taille_max:
            raise ErreurOutil("archive trop grosse une fois extraite : %s (limite %s, option --taille-max)"
                              % (taille_lisible(total), taille_lisible(taille_max)), RESOURCE_EXHAUSTED)
        if not ctx.simulation:
            _verifier_place(vers, total)
        if mot_de_passe:
            zf.setpassword(mot_de_passe.encode("utf-8"))
        for info in infos:
            with ctx.tolerer("extraction_echec", fichier=info.filename):
                cible = chemin_sous(vers, info.filename)
                if info.is_dir():
                    if not ctx.simulation:
                        os.makedirs(cible, exist_ok=True)
                    continue
                if ctx.simulation:
                    verifier_ecrasement(cible, ecraser)
                    ctx.action("fichier_a_extraire", "Serait extrait : %s" % os.path.basename(cible), fichier=cible,
                               taille=info.file_size)
                    continue
                date = time.mktime(info.date_time + (0, 0, -1))
                try:
                    with zf.open(info) as flux:
                        _copier_vers(ctx, flux, cible, ecraser, date, taille=info.file_size)
                except RuntimeError as e:
                    raise ErreurOutil("mot de passe absent ou incorrect pour %s (%s)" % (info.filename, e),
                                      BUSINESS_RULE_VIOLATION)
                except (zipfile.BadZipFile, zlib.error, EOFError) as e:
                    raise ErreurOutil("donnees corrompues dans %s (%s)" % (info.filename, e), FILE_IO_ERROR)


def extraire_tar(ctx, archive, vers, ecraser, taille_max=TAILLE_MAX_DEFAUT):
    try:
        tf = tarfile.open(archive, "r:*")
        membres = tf.getmembers()
    except (tarfile.TarError, EOFError, zlib.error, OSError) as e:
        raise ErreurOutil("archive tar illisible : %s (%s)" % (os.path.basename(archive), e), FILE_IO_ERROR)
    with tf:
        total = sum(m.size for m in membres if m.isreg())
        if total > taille_max:
            raise ErreurOutil("archive trop grosse une fois extraite : %s (limite %s, option --taille-max)"
                              % (taille_lisible(total), taille_lisible(taille_max)), RESOURCE_EXHAUSTED)
        if not ctx.simulation:
            _verifier_place(vers, total)
        for m in membres:
            with ctx.tolerer("extraction_echec", fichier=m.name):
                cible = chemin_sous(vers, m.name)
                if m.isdir():
                    if not ctx.simulation:
                        os.makedirs(cible, exist_ok=True)
                    continue
                if not m.isreg():
                    raise ErreurOutil("lien ou fichier special refuse : %s" % m.name, BUSINESS_RULE_VIOLATION)
                if ctx.simulation:
                    verifier_ecrasement(cible, ecraser)
                    ctx.action("fichier_a_extraire", "Serait extrait : %s" % os.path.basename(cible), fichier=cible,
                               taille=m.size)
                    continue
                try:
                    with tf.extractfile(m) as flux:
                        _copier_vers(ctx, flux, cible, ecraser, m.mtime, taille=m.size)
                except (tarfile.TarError, EOFError, zlib.error) as e:
                    raise ErreurOutil("donnees corrompues dans %s (%s)" % (m.name, e), FILE_IO_ERROR)


def _taille_annoncee_7z(texte):
    """Somme des 'Size = N' d'un listage `7z l -slt` (une ligne par element ; 'Physical Size' n'en fait pas partie)."""
    total = 0
    for ligne in texte.splitlines():
        if ligne.startswith("Size = "):
            try:
                total += int(ligne[7:].strip())
            except ValueError:
                pass
    return total


def extraire_avec_7z(ctx, archive, vers, ecraser, mot_de_passe=None, env=None, taille_max=TAILLE_MAX_DEFAUT):
    """7z.exe x : seul moyen d'ouvrir 7z, rar et iso. En simulation : liste seulement (7z l). Avant d'extraire,
    la taille annoncee (7z l -slt) est comparee a `taille_max` et a l'espace libre (bombe de decompression)."""
    programme = dependances.trouver_programme("7z", env)
    secrets = [mot_de_passe] if mot_de_passe else []
    if ctx.simulation:
        argv = [programme, "l", "-y", archive]
        if mot_de_passe:
            argv.append("-p" + mot_de_passe)
        sortie = lancer_7z_ou_rar(ctx, "7z", argv, secrets)
        ctx.action("archive_a_extraire", "Serait extraite : %s" % os.path.basename(archive), fichier=archive)
        return
    listage = [programme, "l", "-slt", "-y", archive] + (["-p" + mot_de_passe] if mot_de_passe else [])
    annoncee = _taille_annoncee_7z(lancer_7z_ou_rar(ctx, "7z", listage, secrets))
    if annoncee > taille_max:
        raise ErreurOutil("archive trop grosse une fois extraite : %s annonces, limite %s (--taille-max)"
                          % (taille_lisible(annoncee), taille_lisible(taille_max)), RESOURCE_EXHAUSTED)
    _verifier_place(vers, annoncee)
    argv = [programme, "x", "-y", "-bd", "-o" + vers, "-aoa" if ecraser else "-aos"]
    if mot_de_passe:
        argv.append("-p" + mot_de_passe)
        ctx.avertir("mot_de_passe_ligne_de_commande",
                    "Le mot de passe est transmis a 7z sur sa ligne de commande (visible des autres processus)")
    argv.append(archive)
    os.makedirs(vers, exist_ok=True)
    lancer_7z_ou_rar(ctx, "7z", argv, secrets)
    ctx.action("archive_extraite", "Archive extraite : %s" % os.path.basename(archive), fichier=archive,
               compteur="archives")
    # 7z a pu ecrire hors du dossier ? il assainit les noms ; on le verifie par prudence.
    for racine, _, noms in os.walk(vers):
        if not est_dans(vers, racine):
            raise ErreurOutil("7z a ecrit hors du dossier de destination : %s" % racine, BUSINESS_RULE_VIOLATION)


def pyzipper_si_present():
    """Module pyzipper (zip AES) ou None."""
    return importlib_optionnel("pyzipper")


def importlib_optionnel(nom):
    return dependances.module_optionnel(nom) if dependances.module_disponible(nom) else None


def extraire_archive(ctx, archive, vers, ecraser, mot_de_passe=None, taille_max=TAILLE_MAX_DEFAUT,
                     formats=("zip", "tar", "7z", "rar", "iso"), env=None):
    """Extrait `archive` selon son format (extension) dans `vers`. Leve ErreurOutil si le format est inconnu
    ou non autorise pour cet outil, DependanceAbsente si 7z.exe manque pour 7z / rar / iso."""
    format_ = format_archive(archive)
    if format_ is None or format_ not in formats:
        raise ErreurOutil("format d'archive non pris en charge par cet outil : %s (formats : %s)"
                          % (os.path.basename(archive), ", ".join(formats)), BUSINESS_RULE_VIOLATION)
    if not os.path.isfile(archive):
        raise ErreurOutil("archive introuvable : %s" % archive, FILE_NOT_FOUND)
    if format_ == "zip":
        try:
            return extraire_zip(ctx, archive, vers, ecraser, mot_de_passe, taille_max, pyzipper_si_present())
        except DependanceAbsente:
            # zip AES sans pyzipper : 7-Zip sait le lire s'il est installe
            try:
                dependances.trouver_programme("7z", env)
            except DependanceAbsente as e:
                raise DependanceAbsente("zip chiffre en AES : installer pyzipper (pip install pyzipper) ou 7-Zip (%s)" % e)
            return extraire_avec_7z(ctx, archive, vers, ecraser, mot_de_passe, env, taille_max)
    if format_ == "tar":
        return extraire_tar(ctx, archive, vers, ecraser, taille_max)
    return extraire_avec_7z(ctx, archive, vers, ecraser, mot_de_passe, env, taille_max)
