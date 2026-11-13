# outil: permissions
# description: Gere les ACL Windows avec icacls : --afficher, --accorder COMPTE:DROITS, --refuser COMPTE:DROITS, --retirer COMPTE, --heriter activer|desactiver|copier-et-couper, --proprietaire COMPTE.
# parametre: --afficher | facultatif | affiche l'ACL (icacls sans option)
# parametre: --accorder COMPTE:DROITS | facultatif | accorde des droits ; repetable
# parametre: --refuser COMPTE:DROITS | facultatif | refuse des droits ; repetable
# parametre: --retirer COMPTE | facultatif | retire les droits accordes a un compte ; repetable
# parametre: --heriter {activer,copier-et-couper,desactiver} | facultatif | heritage des droits du dossier parent
# parametre: --proprietaire COMPTE | facultatif | change le proprietaire
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Lit ou modifie les droits (ACL Windows) de fichiers et de dossiers, avec icacls."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun import dependances
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import DependanceAbsente, ErreurOutil, ErreurParametres, FILE_IO_ERROR
from outils.commun.outil import Outil

OUTIL = Outil("permissions", "Gere les ACL Windows avec icacls : --afficher, --accorder COMPTE:DROITS, --refuser "
              "COMPTE:DROITS, --retirer COMPTE, --heriter activer|desactiver|copier-et-couper, --proprietaire "
              "COMPTE. Un compte s'ecrit DOMAINE\\Nom, Nom ou *S-1-5-... (SID) ; les droits sont ceux d'icacls : "
              "F (total), M (modification), RX (lecture et execution), R (lecture), W (ecriture), eventuellement "
              "precedes de (OI)(CI) pour un dossier. Les dossiers designes ne sont modifies que sur eux-memes "
              "sans --recursif.", "dates_attributs")
_RE_DROIT = re.compile(r"^(\*S-[0-9-]+|[^:/\\\"<>|?*\s][^:/\"<>|?*]*):((?:\([A-Za-z,]+\))*[A-Za-z]*)$")
_RE_COMPTE = re.compile(r"^(\*S-[0-9-]+|[^:/\"<>|?*]+)$")
HERITAGE = {"activer": "e", "desactiver": "d", "copier-et-couper": "r"}


@OUTIL.arguments
def arguments(p):
    options_entrees(p, masques=False)
    p.add_argument("--afficher", action="store_true", help="affiche l'ACL (icacls sans option)")
    p.add_argument("--accorder", action="append", default=[], metavar="COMPTE:DROITS", help="accorde des droits ; repetable")
    p.add_argument("--refuser", action="append", default=[], metavar="COMPTE:DROITS", help="refuse des droits ; repetable")
    p.add_argument("--retirer", action="append", default=[], metavar="COMPTE", help="retire les droits accordes a un compte ; repetable")
    p.add_argument("--heriter", choices=sorted(HERITAGE), help="heritage des droits du dossier parent")
    p.add_argument("--proprietaire", metavar="COMPTE", help="change le proprietaire")


@OUTIL.principal
def principal(ctx, args):
    options = []
    for valeur in args.accorder + args.refuser:
        if not _RE_DROIT.match(valeur) or not valeur.split(":", 1)[1]:
            raise ErreurParametres("droits illisibles : '%s' (forme COMPTE:DROITS, ex. DOMAINE\\Groupe:(OI)(CI)M)" % valeur)
    for valeur in args.retirer + ([args.proprietaire] if args.proprietaire else []):
        if not _RE_COMPTE.match(valeur):
            raise ErreurParametres("compte illisible : '%s'" % valeur)
    for v in args.accorder:
        options += ["/grant", v]
    for v in args.refuser:
        options += ["/deny", v]
    for v in args.retirer:
        options += ["/remove", v]
    if args.heriter:
        options.append("/inheritance:" + HERITAGE[args.heriter])
    if args.proprietaire:
        options += ["/setowner", args.proprietaire]
    if not options and not args.afficher:
        raise ErreurParametres("rien a faire : indiquer --afficher, --accorder, --refuser, --retirer, --heriter ou --proprietaire")
    if os.name != "nt":
        raise DependanceAbsente("les ACL Windows (icacls) n'existent que sous Windows")
    if getattr(args, "recursif", False):
        options.append("/T")
    for chemin in ctx.designes():
        with ctx.tolerer("acl_echec", fichier=chemin):
            complet = os.path.abspath(chemin)
            if not os.path.exists(complet):
                raise ErreurOutil("introuvable : %s" % chemin, "FILE_NOT_FOUND")
            if not options:
                code, sortie = dependances.executer_externe(["icacls", complet])
                if code != 0:
                    raise ErreurOutil("icacls a echoue (code %d) : %s" % (code, sortie.strip()[-300:]), FILE_IO_ERROR)
                ctx.afficher(sortie.strip().replace("\r", ""))
                ctx.action("acl_lue", "ACL lue : %s" % os.path.basename(complet), compteur="lus", fichier=chemin)
                continue
            if ctx.simulation:
                ctx.action("acl_a_modifier", "ACL serait modifiee : %s" % os.path.basename(complet), fichier=chemin,
                           options=" ".join(options))
                continue
            code, sortie = dependances.executer_externe(["icacls", complet] + options)
            if code != 0:
                raise ErreurOutil("icacls a echoue (code %d) : %s" % (code, sortie.strip()[-300:]), FILE_IO_ERROR)
            ctx.action("acl_modifiee", "ACL modifiee : %s" % os.path.basename(complet), fichier=chemin,
                       options=" ".join(options))


if __name__ == "__main__":
    OUTIL.lancer()
