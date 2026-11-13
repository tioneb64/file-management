# outil: zip_chiffrer
# description: Cree un zip chiffre en AES-256.
# parametre: --sortie ARCHIVE.zip | obligatoire | archive chiffree a creer
# parametre: --niveau 0-9 | facultatif | niveau de compression (defaut 6)
# parametre: --moteur {auto,pyzipper,7z} | facultatif | auto : pyzipper s'il est installe, sinon 7z
# parametre: --ecraser | facultatif | remplace l'archive si elle existe
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --mot-de-passe-env NOM | facultatif | nom de la variable d'environnement qui contient le mot de passe
# parametre: --mot-de-passe-fichier FICHIER | facultatif | fichier (UTF-8) dont la premiere ligne est le mot de passe
"""Cree une archive zip protegee par mot de passe, chiffree en AES-256."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun import archives, dependances
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import BUSINESS_RULE_VIOLATION, ErreurOutil
from outils.commun.fichiers import sortie_atomique, verifier_ecrasement
from outils.commun.outil import Outil
from outils.commun.secret import lire_mot_de_passe, options_mot_de_passe

OUTIL = Outil("zip_chiffrer", "Cree un zip chiffre en AES-256. Moteur prefere : le module Python pyzipper (le mot "
              "de passe ne passe jamais sur une ligne de commande) ; a defaut 7-Zip (7z.exe), dont la ligne de "
              "commande expose le mot de passe aux autres processus du serveur (avertissement journalise). Aucun "
              "des deux : code retour 4.", "compression")


@OUTIL.arguments
def arguments(p):
    options_entrees(p, recursif=False)
    p.add_argument("--sortie", required=True, metavar="ARCHIVE.zip", help="archive chiffree a creer")
    p.add_argument("--niveau", type=int, default=6, choices=range(0, 10), metavar="0-9",
                   help="niveau de compression (defaut 6)")
    p.add_argument("--moteur", choices=("auto", "pyzipper", "7z"), default="auto",
                   help="auto : pyzipper s'il est installe, sinon 7z")
    p.add_argument("--ecraser", action="store_true", help="remplace l'archive si elle existe")
    options_mot_de_passe(p)


@OUTIL.principal
def principal(ctx, args):
    secret = lire_mot_de_passe(args, ctx.env, obligatoire=True)
    designes = ctx.designes()
    if not designes:
        return
    sortie = os.path.abspath(args.sortie)
    module = None
    if args.moteur in ("auto", "pyzipper"):
        module = archives.pyzipper_si_present()
        if module is None and args.moteur == "pyzipper":
            module = dependances.module_optionnel("pyzipper")       # leve DependanceAbsente
    if module is None:
        dependances.trouver_programme("7z", ctx.env)                 # DependanceAbsente si aucun moteur
    elements = archives.elements_a_archiver(ctx, designes, exclus=[sortie])
    if not elements:
        return
    if ctx.simulation:
        verifier_ecrasement(sortie, args.ecraser)
        for disque, nom, dossier in elements:
            ctx.action("fichier_a_archiver", "Serait ajoute a l'archive chiffree : %s" % nom.rstrip("/"),
                       fichier=disque, compteur="dossiers" if dossier else "fichiers", moteur="pyzipper" if module else "7z")
        return
    if module is not None:
        with sortie_atomique(sortie, args.ecraser) as temporaire:
            archives.creer_zip(ctx, elements, temporaire, args.niveau, secret, module)
            if ctx.nb_erreurs:
                raise ErreurOutil("archive incomplete, non creee (%d erreur(s) ci-dessus)" % ctx.nb_erreurs)
    else:
        if ctx.nb_erreurs:
            raise ErreurOutil("archive non creee (%d erreur(s) sur les elements ci-dessus)" % ctx.nb_erreurs)
        premiers = [d for d, nom, _ in elements if nom.count("/") == (1 if nom.endswith("/") else 0)]
        with archives.sortie_dans_dossier_temporaire(sortie, args.ecraser) as interne:
            archives.creer_avec_7z(ctx, premiers, interne, "zip", min(args.niveau, 9), secret, zip_aes=True,
                                   env=ctx.env)
            if not os.path.isfile(interne):
                raise ErreurOutil("7z n'a pas cree l'archive", BUSINESS_RULE_VIOLATION)
        ctx.nb_actions += 1
        ctx.compter("fichiers", len([e for e in elements if not e[2]]))
    ctx.info("archive_creee", "Archive chiffree creee : %s" % os.path.basename(sortie), fichier=sortie,
             taille=os.path.getsize(sortie), chiffrement="AES-256", moteur="pyzipper" if module else "7z")


if __name__ == "__main__":
    OUTIL.lancer()
