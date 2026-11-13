# outil: espace_disque
# description: Controle l'espace libre du volume de chaque dossier designe (defaut : COPIE_CIBLE) : --libre-min 10G et/ou --libre-min-pct 10, et --pour CHEMIN (fichier ou dossier ; repetable) pour verifier qu'il y a la place d'y copier ces fichiers...
# parametre: DOSSIER | facultatif | dossier ou lecteur a controler (defaut : COPIE_CIBLE)
# parametre: --libre-min TAILLE | facultatif | espace libre minimal (ex. 10G)
# parametre: --libre-min-pct POURCENT | facultatif | espace libre minimal en % du volume
# parametre: --pour CHEMIN | facultatif | fichier ou dossier a y copier ; repetable
# parametre: --marge TAILLE | facultatif | marge ajoutee a la place necessaire (defaut 0)
# parametre: --code-si-insuffisant N | facultatif | code retour si l'espace manque : 2 (erreur, defaut) ou 1 (avertissement)
"""Controle l'espace disque libre d'un dossier ou d'un lecteur (minimum, et place necessaire pour des fichiers)."""
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.erreurs import FILE_NOT_FOUND, RESOURCE_EXHAUSTED, ErreurOutil, ErreurParametres
from outils.commun.fichiers import lire_taille, taille_lisible
from outils.commun.outil import Outil

OUTIL = Outil("espace_disque", "Controle l'espace libre du volume de chaque dossier designe (defaut : COPIE_CIBLE) : "
              "--libre-min 10G et/ou --libre-min-pct 10, et --pour CHEMIN (fichier ou dossier ; repetable) pour "
              "verifier qu'il y a la place d'y copier ces fichiers (taille totale + --marge). Espace insuffisant : "
              "erreur RESOURCE_EXHAUSTED (code 2) ; avec --code-si-insuffisant 1, avertissement et code 1.", "controle")


@OUTIL.arguments
def arguments(p):
    p.add_argument("dossiers", nargs="*", metavar="DOSSIER", help="dossier ou lecteur a controler (defaut : COPIE_CIBLE)")
    p.add_argument("--libre-min", metavar="TAILLE", help="espace libre minimal (ex. 10G)")
    p.add_argument("--libre-min-pct", type=float, metavar="POURCENT", help="espace libre minimal en %% du volume")
    p.add_argument("--pour", action="append", default=[], metavar="CHEMIN", help="fichier ou dossier a y copier ; repetable")
    p.add_argument("--marge", default="0", metavar="TAILLE", help="marge ajoutee a la place necessaire (defaut 0)")
    p.add_argument("--code-si-insuffisant", type=int, choices=(1, 2), default=2, metavar="N",
                   help="code retour si l'espace manque : 2 (erreur, defaut) ou 1 (avertissement)")


def taille_de(chemin):
    if os.path.isfile(chemin):
        return os.path.getsize(chemin)
    total = 0
    for dossier, _, noms in os.walk(chemin):
        for n in noms:
            try:
                total += os.path.getsize(os.path.join(dossier, n))
            except OSError:
                pass
    return total


@OUTIL.principal
def principal(ctx, args):
    dossiers = args.dossiers or ([ctx.env["COPIE_CIBLE"]] if ctx.env.get("COPIE_CIBLE") else [])
    if not dossiers:
        return
    if not (args.libre_min or args.libre_min_pct or args.pour):
        raise ErreurParametres("indiquer --libre-min, --libre-min-pct ou --pour")
    mini = lire_taille(args.libre_min) if args.libre_min else 0
    marge = lire_taille(args.marge) if args.marge not in ("0", 0) else 0
    for chemin in args.pour:
        if not os.path.exists(chemin):
            raise ErreurParametres("--pour : introuvable : %s" % chemin)
    besoin = sum(taille_de(c) for c in args.pour) + (marge if args.pour else 0)
    for dossier in dossiers:
        with ctx.tolerer("controle_espace_echec", fichier=dossier):
            existant = os.path.abspath(dossier)
            while not os.path.exists(existant) and os.path.dirname(existant) != existant:
                existant = os.path.dirname(existant)            # un dossier a creer : on controle son volume
            if not os.path.exists(existant):
                raise ErreurOutil("introuvable : %s" % dossier, FILE_NOT_FOUND)
            usage = shutil.disk_usage(existant)
            exigence = max(mini, int(usage.total * (args.libre_min_pct or 0) / 100.0), 0) + besoin
            champs = dict(fichier=dossier, libre=usage.free, total=usage.total, exige=exigence)
            ctx.afficher("%s : %s libres sur %s" % (dossier, taille_lisible(usage.free), taille_lisible(usage.total)))
            if usage.free >= exigence:
                ctx.action("espace_suffisant", "Espace suffisant : %s libres (%s exiges)" % (taille_lisible(usage.free),
                           taille_lisible(exigence)), compteur="controles", **champs)
                continue
            message = "Espace insuffisant sur %s : %s libres, %s exiges" % (dossier, taille_lisible(usage.free),
                                                                           taille_lisible(exigence))
            if args.code_si_insuffisant == 1:
                ctx.avertir("espace_insuffisant", message, **champs)
                ctx.imposer_code(1)
            else:
                ctx.echec("espace_insuffisant", message, RESOURCE_EXHAUSTED, **champs)


if __name__ == "__main__":
    OUTIL.lancer()
