# outil: archive_creer
# description: Cree une archive tar, tar.gz, tar.bz2, tar.xz (bibliotheque standard), 7z (necessite 7z.exe) ou rar (necessite rar.exe de WinRAR) ; le format est celui de l'extension de --sortie.
# parametre: --sortie ARCHIVE | obligatoire | archive a creer (.tar .tar.gz .tgz .tar.bz2 .tar.xz .7z .rar)
# parametre: --niveau 0-9 | facultatif | niveau de compression (defaut 6 ; borne par le format pour 7z et rar)
# parametre: --ecraser | facultatif | remplace l'archive si elle existe
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --mot-de-passe-env NOM | facultatif | nom de la variable d'environnement qui contient le mot de passe
# parametre: --mot-de-passe-fichier FICHIER | facultatif | fichier (UTF-8) dont la premiere ligne est le mot de passe
"""Cree une archive de format multiple : tar, tar.gz, tar.bz2, tar.xz, 7z, rar (le format vient de l'extension)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun import archives
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import BUSINESS_RULE_VIOLATION, ErreurOutil, ErreurParametres
from outils.commun.fichiers import sortie_atomique, verifier_ecrasement
from outils.commun.outil import Outil
from outils.commun.secret import lire_mot_de_passe, options_mot_de_passe

OUTIL = Outil("archive_creer", "Cree une archive tar, tar.gz, tar.bz2, tar.xz (bibliotheque standard), 7z "
              "(necessite 7z.exe) ou rar (necessite rar.exe de WinRAR) ; le format est celui de l'extension de "
              "--sortie. Pour un zip : zip_creer. Pour un zip chiffre : zip_chiffrer. Le format iso n'est pas "
              "cree : seule l'extraction est prise en charge (archive_extraire).", "compression")


@OUTIL.arguments
def arguments(p):
    options_entrees(p, recursif=False)
    p.add_argument("--sortie", required=True, metavar="ARCHIVE",
                   help="archive a creer (.tar .tar.gz .tgz .tar.bz2 .tar.xz .7z .rar)")
    p.add_argument("--niveau", type=int, default=6, choices=range(0, 10), metavar="0-9",
                   help="niveau de compression (defaut 6 ; borne par le format pour 7z et rar)")
    p.add_argument("--ecraser", action="store_true", help="remplace l'archive si elle existe")
    options_mot_de_passe(p)


@OUTIL.principal
def principal(ctx, args):
    sortie = os.path.abspath(args.sortie)
    format_ = archives.format_archive(sortie)
    if format_ not in ("tar", "7z", "rar"):
        raise ErreurParametres("extension de --sortie non prise en charge : %s (voir --aide ; zip : zip_creer ; "
                               "iso : extraction seulement)" % os.path.basename(sortie))
    secret = lire_mot_de_passe(args, ctx.env)
    if secret and format_ == "tar":
        raise ErreurParametres("un tar ne se chiffre pas : utiliser 7z, rar ou zip_chiffrer")
    designes = ctx.designes()
    if not designes:
        return
    elements = archives.elements_a_archiver(ctx, designes, exclus=[sortie])
    if not elements:
        return
    if ctx.simulation:
        verifier_ecrasement(sortie, args.ecraser)
        if format_ != "tar":
            from outils.commun import dependances
            dependances.trouver_programme("7z" if format_ == "7z" else "rar", ctx.env)
        for disque, nom, dossier in elements:
            ctx.action("fichier_a_archiver", "Serait ajoute a l'archive : %s" % nom.rstrip("/"), fichier=disque,
                       compteur="dossiers" if dossier else "fichiers")
        return
    if format_ == "tar":
        mode = next(m for e, m in archives.MODES_TAR.items() if sortie.lower().endswith(e))
        with sortie_atomique(sortie, args.ecraser) as temporaire:
            archives.creer_tar(ctx, elements, temporaire, mode, args.niveau)
            if ctx.nb_erreurs:
                raise ErreurOutil("archive incomplete, non creee (%d erreur(s) ci-dessus)" % ctx.nb_erreurs)
    else:
        # 7z et rar archivent des chemins existants : seuls les elements de premier niveau sont passes
        if ctx.nb_erreurs:
            raise ErreurOutil("archive non creee (%d erreur(s) sur les elements ci-dessus)" % ctx.nb_erreurs)
        premiers = [d for d, nom, _ in elements if nom.count("/") == (1 if nom.endswith("/") else 0)]
        with archives.sortie_dans_dossier_temporaire(sortie, args.ecraser) as interne:
            if format_ == "7z":
                archives.creer_avec_7z(ctx, premiers, interne, "7z", min(args.niveau, 9), secret, env=ctx.env)
            else:
                archives.creer_rar(ctx, premiers, interne, min(args.niveau // 2, 5), secret, env=ctx.env)
            if not os.path.isfile(interne):
                raise ErreurOutil("le programme n'a pas cree l'archive", BUSINESS_RULE_VIOLATION)
        for disque, nom, dossier in elements:
            ctx.compter("dossiers" if dossier else "fichiers")
        ctx.nb_actions += 1
    ctx.info("archive_creee", "Archive creee : %s" % os.path.basename(sortie), fichier=sortie,
             taille=os.path.getsize(sortie))


if __name__ == "__main__":
    OUTIL.lancer()
