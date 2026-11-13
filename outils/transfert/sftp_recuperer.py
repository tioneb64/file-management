# outil: sftp_recuperer
# description: Recupere des fichiers d'un serveur SFTP (nom temporaire puis renommage, controle, cle d'hote verifiee).
# parametre: --hote HOTE | obligatoire | serveur SFTP (nom ou adresse)
# parametre: --port N | facultatif | port (defaut 22)
# parametre: --utilisateur COMPTE | obligatoire | compte de connexion
# parametre: --mot-de-passe-env NOM | facultatif | nom de la variable d'environnement qui contient le mot de passe
# parametre: --mot-de-passe-fichier FICHIER | facultatif | fichier (UTF-8) dont la premiere ligne est le mot de passe
# parametre: --cle-privee FICHIER | facultatif | cle privee d'authentification (OpenSSH ou PEM)
# parametre: --phrase-env NOM | facultatif | nom de la variable d'environnement qui contient la phrase secrete de la cle privee
# parametre: --empreinte-hote SHA256:XXX | facultatif | empreinte attendue de la cle de l'hote (ssh-keygen -lf, ou relevee dans le journal)
# parametre: --known-hosts FICHIER | facultatif | fichier known_hosts (defaut : celui de l'utilisateur s'il existe)
# parametre: --hote-inconnu {refuser,accepter} | facultatif | cle d'un hote jamais vu : refuser (defaut) ou accepter avec avertissement
# parametre: --delai SEC | facultatif | delai reseau (defaut 30)
# parametre: --tentatives N | facultatif | nombre d'essais en cas d'incident reseau (defaut 3) ; une authentification refusee n'est jamais rejouee
# parametre: --pause SEC | facultatif | pause entre deux essais (defaut 5)
# parametre: --distant DOSSIER | obligatoire | dossier a relever sur le serveur
# parametre: --local DOSSIER | obligatoire | dossier local de reception
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers du dossier distant (l'arborescence est reproduite)
# parametre: --age-minimum SEC | facultatif | ignore les fichiers modifies depuis moins de SEC secondes (fichier peut-etre encore en cours de depot)
# parametre: --apres-recuperation {conserver,archiver,supprimer} | facultatif | action sur le fichier distant une fois recupere et verifie (defaut conserver)
# parametre: --archive-distant DOSSIER | facultatif | dossier distant d'archivage (avec --apres-recuperation archiver)
# parametre: --ecraser | facultatif | remplace un fichier qui existe deja (sinon : erreur)
# parametre: --ignorer-existants | facultatif | passe sans erreur un fichier qui existe deja (rien n'est ecrase)
# parametre: --verification {taille,sha256,aucune} | facultatif | controle apres transfert : taille (defaut), sha256 (relit le fichier) ou aucune
# parametre: --suffixe-temporaire SUFFIXE | facultatif | suffixe du nom temporaire cote serveur (defaut .tmp)
"""Recupere des fichiers d'un serveur SFTP, sans jamais livrer un fichier incomplet ni rien ecraser."""
import fnmatch
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun import sftp as lib
from outils.commun.erreurs import DUPLICATE_ENTITY, ErreurOutil, ErreurParametres
from outils.commun.fichiers import SUFFIXE_TEMPORAIRE, chemin_sous
from outils.commun.outil import Outil

OUTIL = Outil("sftp_recuperer", "Recupere des fichiers d'un serveur SFTP (paramiko) dans un dossier local. Chaque "
              "fichier est ecrit sous un nom temporaire (.copie_en_cours, ignore du moteur) puis renomme apres "
              "controle (taille, ou --verification sha256) ; un telechargement interrompu reprend ou il s'est "
              "arrete. Rien n'est ecrase sans --ecraser. --age-minimum laisse de cote les fichiers que le "
              "partenaire est peut-etre en train de deposer ; les noms en .tmp sont toujours ignores. "
              "--apres-recuperation archiver|supprimer traite le fichier distant une fois la copie locale "
              "verifiee. Memes regles de connexion que sftp_envoyer : cle de l'hote toujours verifiee, mot de "
              "passe jamais en ligne de commande ni dans le journal, authentification refusee non rejouee, "
              "incident reseau rejoue. Necessite le module Python paramiko (code retour 4 s'il est absent).",
              "transfert")


@OUTIL.arguments
def arguments(p):
    lib.options_connexion(p)
    p.add_argument("--distant", required=True, metavar="DOSSIER", help="dossier a relever sur le serveur")
    p.add_argument("--local", required=True, metavar="DOSSIER", help="dossier local de reception")
    p.add_argument("--masque", action="append", default=[], metavar="JOKER",
                   help="ne garder que les noms correspondant (ex. *.csv) ; repetable")
    p.add_argument("--exclure", action="append", default=[], metavar="JOKER",
                   help="ecarter les noms correspondant ; repetable")
    p.add_argument("--recursif", "-r", action="store_true",
                   help="descendre dans les sous-dossiers du dossier distant (l'arborescence est reproduite)")
    p.add_argument("--age-minimum", type=float, metavar="SEC",
                   help="ignore les fichiers modifies depuis moins de SEC secondes (fichier peut-etre encore en "
                        "cours de depot)")
    p.add_argument("--apres-recuperation", choices=("conserver", "archiver", "supprimer"), default="conserver",
                   metavar="{conserver,archiver,supprimer}",
                   help="action sur le fichier distant une fois recupere et verifie (defaut conserver)")
    p.add_argument("--archive-distant", metavar="DOSSIER",
                   help="dossier distant d'archivage (avec --apres-recuperation archiver)")
    lib.options_transfert(p)


def _retenu(nom, relatif, args):
    if nom.endswith(args.suffixe_temporaire) or nom.endswith(SUFFIXE_TEMPORAIRE):
        return False
    bas, rel = nom.lower(), relatif.lower()
    if args.masque and not any(fnmatch.fnmatchcase(bas, m.lower()) for m in args.masque):
        return False
    return not any(fnmatch.fnmatchcase(bas, x.lower()) or fnmatch.fnmatchcase(rel, x.lower()) for x in args.exclure)


@OUTIL.principal
def principal(ctx, args):
    if args.apres_recuperation == "archiver" and not args.archive_distant:
        raise ErreurParametres("--apres-recuperation archiver demande --archive-distant")
    if args.ecraser and args.ignorer_existants:
        raise ErreurParametres("--ecraser et --ignorer-existants sont exclusifs")
    if args.age_minimum is not None and args.age_minimum < 0:
        raise ErreurParametres("--age-minimum : un nombre de secondes positif")
    racine = args.distant.replace("\\", "/")
    archive = args.archive_distant.replace("\\", "/") if args.archive_distant else None
    with lib.Connexion(ctx, args) as cnx:
        lib.verifier_dossier(cnx.sftp, racine)
        trouves = cnx.executer(lambda sftp, essai: list(lib.lister_distant(sftp, racine, args.recursif)))
        for distant, relatif, attr in trouves:
            if not _retenu(os.path.basename(distant), relatif, args):
                continue
            with ctx.tolerer(distant=distant, hote=args.hote, port=args.port):
                _un_fichier(ctx, args, cnx, racine, archive, distant, relatif, attr)


def _un_fichier(ctx, args, cnx, racine, archive, distant, relatif, attr):
    local = chemin_sous(args.local, relatif)
    taille = attr.st_size or 0
    champs = dict(fichier=local, distant=distant, hote=args.hote, port=args.port)
    if args.age_minimum is not None and attr.st_mtime and time.time() - attr.st_mtime < args.age_minimum:
        ctx.info("fichier_trop_recent", "Modifie depuis moins de %g s, laisse de cote : %s" % (args.age_minimum, distant),
                 age=round(time.time() - attr.st_mtime, 1), **champs)
        ctx.compter("trop_recents")
        return
    if os.path.lexists(local):
        if args.ignorer_existants:
            ctx.info("fichier_existant_ignore", "Deja present, ignore : %s" % local, **champs)
            ctx.compter("ignores")
            return
        if not args.ecraser:
            raise ErreurOutil("le fichier existe deja (--ecraser pour le remplacer) : %s" % local, DUPLICATE_ENTITY)
    if ctx.simulation:
        ctx.action("fichier_a_recuperer", "Serait recupere : %s -> %s" % (distant, local), compteur="a_recuperer",
                   taille=taille, **champs)
        return
    recu, repris, sha = cnx.executer(
        lambda sftp, essai: lib.recuperer_fichier(sftp, distant, local, taille, args.ecraser, args.verification,
                                                  essai), fichier=local, distant=distant)
    ctx.compter("octets", recu)
    extra = {"sha256": sha} if sha else {}
    if repris:
        extra["octets_repris"] = repris
    ctx.action("fichier_recupere", "Fichier recupere : %s -> %s" % (distant, local), compteur="recuperes",
               taille=recu, verification=args.verification, **dict(champs, **extra))
    _apres(ctx, args, cnx, archive, distant, relatif, champs)


def _apres(ctx, args, cnx, archive, distant, relatif, champs):
    """Traite le fichier distant une fois la copie locale en place (jamais avant)."""
    if args.apres_recuperation == "supprimer":
        cnx.executer(lambda sftp, essai: sftp.remove(distant), fichier=distant)
        ctx.action("fichier_distant_supprime", "Fichier distant supprime apres recuperation : %s" % distant,
                   compteur="supprimes_distants", **champs)
    elif args.apres_recuperation == "archiver":
        def archiver(sftp, essai):
            lib.creer_dossiers(sftp, archive)
            cible = lib.nom_libre_distant(sftp, archive, os.path.basename(distant))      # jamais d'ecrasement
            sftp.rename(distant, cible)
            return cible
        cible = cnx.executer(archiver, fichier=distant)
        ctx.action("fichier_distant_archive", "Fichier distant archive apres recuperation : %s" % cible,
                   compteur="archives_distants", archive_distant=cible, **champs)


if __name__ == "__main__":
    OUTIL.lancer()
