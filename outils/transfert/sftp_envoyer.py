# outil: sftp_envoyer
# description: Depose des fichiers sur un serveur SFTP (nom temporaire puis renommage, controle, cle d'hote verifiee).
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
# parametre: --distant DOSSIER | obligatoire | dossier de depot sur le serveur
# parametre: --creer-dossiers | facultatif | cree le dossier distant (et les sous-dossiers) s'il manque
# parametre: --apres-envoi {conserver,archiver,supprimer} | facultatif | sort du dossier local les fichiers envoyes et verifies (defaut conserver)
# parametre: --archive-dossier DOSSIER | facultatif | dossier local d'archivage (avec --apres-envoi archiver)
# parametre: --ecraser | facultatif | remplace un fichier qui existe deja (sinon : erreur)
# parametre: --ignorer-existants | facultatif | passe sans erreur un fichier qui existe deja (rien n'est ecrase)
# parametre: --verification {taille,sha256,aucune} | facultatif | controle apres transfert : taille (defaut), sha256 (relit le fichier) ou aucune
# parametre: --suffixe-temporaire SUFFIXE | facultatif | suffixe du nom temporaire cote serveur (defaut .tmp)
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Depose des fichiers sur un serveur SFTP, sans jamais montrer un fichier incomplet ni rien ecraser."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun import sftp as lib
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import DUPLICATE_ENTITY, ErreurOutil, ErreurParametres
from outils.commun.fichiers import deplacer_fichier
from outils.commun.outil import Outil

OUTIL = Outil("sftp_envoyer", "Depose des fichiers sur un serveur SFTP (paramiko). Chaque fichier est ecrit sous un "
              "nom temporaire (.tmp) puis renomme apres controle (taille, ou --verification sha256) : le partenaire "
              "ne voit jamais un fichier incomplet. Rien n'est ecrase sans --ecraser. La cle de l'hote est toujours "
              "verifiee (--empreinte-hote ou known_hosts ; hote inconnu refuse sauf --hote-inconnu accepter). Le mot "
              "de passe ne passe jamais en ligne de commande (--mot-de-passe-env / --mot-de-passe-fichier) et n'est "
              "jamais journalise ; une authentification refusee n'est pas rejouee, un incident reseau l'est "
              "(--tentatives), y compris en cours de fichier (le transfert reprend ou il s'est arrete). "
              "--apres-envoi archiver|supprimer sort du dossier local les fichiers dont l'envoi est verifie. "
              "Necessite le module Python paramiko (code retour 4 s'il est absent).", "transfert")


@OUTIL.arguments
def arguments(p):
    lib.options_connexion(p)
    p.add_argument("--distant", required=True, metavar="DOSSIER", help="dossier de depot sur le serveur")
    p.add_argument("--creer-dossiers", action="store_true",
                   help="cree le dossier distant (et les sous-dossiers) s'il manque")
    p.add_argument("--apres-envoi", choices=("conserver", "archiver", "supprimer"), default="conserver",
                   metavar="{conserver,archiver,supprimer}",
                   help="sort du dossier local les fichiers envoyes et verifies (defaut conserver)")
    p.add_argument("--archive-dossier", metavar="DOSSIER", help="dossier local d'archivage (avec --apres-envoi archiver)")
    lib.options_transfert(p)
    options_entrees(p, recursif=True)


@OUTIL.principal
def principal(ctx, args):
    if args.apres_envoi == "archiver" and not args.archive_dossier:
        raise ErreurParametres("--apres-envoi archiver demande --archive-dossier")
    if args.ecraser and args.ignorer_existants:
        raise ErreurParametres("--ecraser et --ignorer-existants sont exclusifs")
    designes = ctx.designes()
    if not designes:
        return
    racine = args.distant.replace("\\", "/")
    with lib.Connexion(ctx, args) as cnx:
        if args.creer_dossiers:
            if not ctx.simulation:
                lib.creer_dossiers(cnx.sftp, racine)
        else:
            lib.verifier_dossier(cnx.sftp, racine)
        for fichier, base in ctx.fichiers(designes):
            with ctx.tolerer(fichier=fichier, hote=args.hote, port=args.port):
                _un_fichier(ctx, args, cnx, fichier, base, racine)


def _un_fichier(ctx, args, cnx, fichier, base, racine):
    relatif = os.path.relpath(fichier, base).replace(os.sep, "/")
    distant = lib.joindre_distant(racine, relatif)
    taille = os.path.getsize(fichier)
    champs = dict(fichier=fichier, distant=distant, hote=args.hote, port=args.port)
    existe = lib.attributs(cnx.sftp, distant) is not None
    if existe and args.ignorer_existants:
        ctx.info("fichier_existant_ignore", "Deja present, ignore : %s" % distant, **champs)
        ctx.compter("ignores")
        return
    if existe and not args.ecraser:
        raise ErreurOutil("le fichier distant existe deja (--ecraser pour le remplacer) : %s" % distant,
                          DUPLICATE_ENTITY)
    if ctx.simulation:
        ctx.action("fichier_a_envoyer", "Serait envoye : %s -> %s" % (os.path.basename(fichier), distant),
                   compteur="a_envoyer", taille=taille, **champs)
        return
    dossier_distant = distant.rsplit("/", 1)[0] or "/"
    if args.creer_dossiers and dossier_distant != racine:
        lib.creer_dossiers(cnx.sftp, dossier_distant)
    envoye, repris, sha = cnx.executer(
        lambda sftp, essai: lib.envoyer_fichier(sftp, fichier, distant, args.ecraser, args.verification,
                                                args.suffixe_temporaire, essai), fichier=fichier, distant=distant)
    ctx.compter("octets", envoye)
    extra = {"sha256": sha} if sha else {}
    if repris:
        extra["octets_repris"] = repris
    ctx.action("fichier_envoye", "Fichier envoye : %s -> %s" % (os.path.basename(fichier), distant),
               compteur="envoyes", taille=envoye, verification=args.verification, **dict(champs, **extra))
    _apres(ctx, args, fichier)


def _apres(ctx, args, fichier):
    """Sort le fichier du dossier local une fois l'envoi verifie (jamais avant)."""
    if args.apres_envoi == "supprimer":
        os.remove(fichier)
        ctx.action("fichier_supprime", "Fichier local supprime apres envoi : %s" % os.path.basename(fichier),
                   compteur="supprimes", fichier=fichier)
    elif args.apres_envoi == "archiver":
        os.makedirs(args.archive_dossier, exist_ok=True)
        cible = lib.nom_libre_local(args.archive_dossier, os.path.basename(fichier))      # jamais d'ecrasement
        deplacer_fichier(fichier, cible)
        ctx.action("fichier_archive", "Fichier local archive apres envoi : %s" % os.path.basename(cible),
                   compteur="archives", fichier=fichier, archive=cible)


if __name__ == "__main__":
    OUTIL.lancer()
