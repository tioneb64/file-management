# outil: renommer_masse
# description: Renomme des fichiers (jamais d'ecrasement : un nom deja pris est une erreur de l'element).
# parametre: --prefixe TEXTE | facultatif | texte ajoute au debut du nom
# parametre: --suffixe TEXTE | facultatif | texte ajoute avant l'extension
# parametre: --regex EXPR | facultatif | expression reguliere appliquee au nom sans extension
# parametre: --par TEXTE | facultatif | remplacement de --regex (\1 pour un groupe ; defaut vide)
# parametre: --modele MODELE | facultatif | modele du nom sans extension (defaut {nom})
# parametre: --numeroter | facultatif | ajoute un numero : utile avec {n} dans --modele ; sinon le modele devient {n}_{nom}
# parametre: --debut N | facultatif | premier numero (defaut 1)
# parametre: --largeur N | facultatif | largeur du numero, complete de zeros (defaut 3)
# parametre: --ordre {nom,date} | facultatif | ordre de numerotation (defaut : nom)
# parametre: --date-exif | facultatif | {date} vient de l'EXIF des JPEG (sinon : date de modification)
# parametre: --format-date FORMAT | facultatif | format de {date} (defaut %Y%m%d_%H%M%S)
# parametre: --sans-repli | facultatif | une photo sans EXIF est une erreur au lieu de prendre la date de modification
# parametre: --minuscules | facultatif | met l'extension en minuscules
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Renomme des fichiers en masse : prefixe, suffixe, numerotation, expression reguliere, date EXIF."""
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun import exif, renommage
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import BUSINESS_RULE_VIOLATION, ErreurOutil, ErreurParametres
from outils.commun.outil import Outil

OUTIL = Outil("renommer_masse", "Renomme des fichiers (jamais d'ecrasement : un nom deja pris est une erreur de "
              "l'element). Le nouveau nom = prefixe + modele + suffixe + extension. Le modele (defaut {nom}) "
              "accepte {nom} (nom sans extension, apres --regex), {n} (numero), {date} (date EXIF de prise de "
              "vue, sinon date de modification avec un avertissement), {jour} {mois} {annee} et {dossier} (nom du "
              "dossier parent). Exemples : --prefixe ARCH_ ; --modele \"{date}_{n}\" --date-exif ; --regex "
              "\"\\s+\" --par _.", "organisation")


@OUTIL.arguments
def arguments(p):
    options_entrees(p)
    p.add_argument("--prefixe", default="", metavar="TEXTE", help="texte ajoute au debut du nom")
    p.add_argument("--suffixe", default="", metavar="TEXTE", help="texte ajoute avant l'extension")
    p.add_argument("--regex", metavar="EXPR", help="expression reguliere appliquee au nom sans extension")
    p.add_argument("--par", default="", metavar="TEXTE", help="remplacement de --regex (\\1 pour un groupe ; defaut vide)")
    p.add_argument("--modele", default="{nom}", metavar="MODELE", help="modele du nom sans extension (defaut {nom})")
    p.add_argument("--numeroter", action="store_true", help="ajoute un numero : utile avec {n} dans --modele ; sinon "
                   "le modele devient {n}_{nom}")
    p.add_argument("--debut", type=int, default=1, metavar="N", help="premier numero (defaut 1)")
    p.add_argument("--largeur", type=int, default=3, metavar="N", help="largeur du numero, complete de zeros (defaut 3)")
    p.add_argument("--ordre", choices=("nom", "date"), default="nom", help="ordre de numerotation (defaut : nom)")
    p.add_argument("--date-exif", action="store_true", help="{date} vient de l'EXIF des JPEG (sinon : date de modification)")
    p.add_argument("--format-date", default="%Y%m%d_%H%M%S", metavar="FORMAT", help="format de {date} (defaut %%Y%%m%%d_%%H%%M%%S)")
    p.add_argument("--sans-repli", action="store_true", help="une photo sans EXIF est une erreur au lieu de prendre la date de modification")
    p.add_argument("--minuscules", action="store_true", help="met l'extension en minuscules")


@OUTIL.principal
def principal(ctx, args):
    if args.regex:
        try:
            motif = re.compile(args.regex)
            motif.sub(args.par, "")
        except (re.error, IndexError) as e:
            raise ErreurParametres("expression reguliere ou remplacement invalide : %s" % e)
    else:
        motif = None
    modele = args.modele
    if args.numeroter and not re.search(r"\{n[}:!]", modele):
        modele = "{n}_" + modele
    if not (args.prefixe or args.suffixe or motif or modele != "{nom}" or args.minuscules):
        raise ErreurParametres("aucune transformation demandee (--prefixe, --suffixe, --regex, --modele, --numeroter)")
    try:
        modele.format(nom="", n=0, date="", jour="", mois="", annee="", dossier="")
        datetime.now().strftime(args.format_date)
    except (KeyError, IndexError, ValueError) as e:
        raise ErreurParametres("modele ou format de date invalide : %s" % e)
    liste = [c for c, _ in ctx.fichiers()]
    if args.ordre == "date":
        liste.sort(key=lambda c: (os.path.getmtime(c) if os.path.exists(c) else 0, c))
    plan, numero = [], args.debut
    for chemin in liste:
        with ctx.tolerer("renommage_echec", fichier=chemin):
            dossier, nom = os.path.split(chemin)
            racine, ext = os.path.splitext(nom)
            if motif:
                racine = motif.sub(args.par, racine)
            date = datetime.fromtimestamp(os.path.getmtime(chemin))
            if args.date_exif:
                prise = exif.date_prise_de_vue(chemin)
                if prise is None:
                    if args.sans_repli:
                        raise ErreurOutil("pas de date de prise de vue EXIF : %s" % nom, BUSINESS_RULE_VIOLATION)
                    ctx.avertir("exif_absent", "Pas de date EXIF, date de modification utilisee : %s" % nom,
                                fichier=chemin)
                else:
                    date = prise
            nouveau = args.prefixe + modele.format(
                nom=racine, n="%0*d" % (args.largeur, numero), date=date.strftime(args.format_date),
                jour=date.strftime("%d"), mois=date.strftime("%m"), annee=date.strftime("%Y"),
                dossier=os.path.basename(os.path.abspath(dossier))) + args.suffixe
            nouveau += ext.lower() if args.minuscules else ext
            numero += 1
            if not nouveau.strip(" .") or re.search(r'[<>:"/\\|?*\x00-\x1f]', nouveau):
                raise ErreurOutil("nom resultant invalide : %r" % nouveau, BUSINESS_RULE_VIOLATION)
            plan.append((chemin, os.path.join(dossier, nouveau)))
    renommage.appliquer(ctx, plan)


if __name__ == "__main__":
    OUTIL.lancer()
