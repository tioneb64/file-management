# outil: valider_fichier
# description: Controle des fichiers : non vide (defaut), --taille-min / --taille-max, --format json | jsonl | xml | csv (bien forme), --colonnes a,b,c (en-tete CSV exact), --nb-colonnes N, --lignes-min N (lignes de donnees CSV), --encodage utf-8...
# parametre: --non-vide | facultatif | refuse un fichier de taille 0 (actif si aucun autre controle)
# parametre: --taille-min TAILLE | facultatif | taille minimale (ex. 1K)
# parametre: --taille-max TAILLE | facultatif | taille maximale
# parametre: --format {json,jsonl,xml,csv} | facultatif | le contenu doit etre bien forme
# parametre: --colonnes A,B,C | facultatif | CSV : noms exacts des colonnes de l'en-tete, dans l'ordre
# parametre: --nb-colonnes N | facultatif | CSV : nombre de colonnes de chaque ligne
# parametre: --lignes-min N | facultatif | CSV : nombre minimal de lignes de donnees (hors en-tete)
# parametre: --separateur CAR | facultatif | CSV : separateur (defaut : detecte)
# parametre: --sans-entete | facultatif | CSV : pas d'en-tete
# parametre: --encodage NOM | facultatif | le contenu doit etre valide dans cet encodage (ex. utf-8)
# parametre: --code-si-invalide N | facultatif | code retour d'un fichier invalide : 2 (erreur, defaut) ou 1 (avertissement, ignorer le fichier)
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Valide des fichiers : non vide, taille, JSON / XML / CSV bien formes, colonnes attendues."""
import csv
import json
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import BUSINESS_RULE_VIOLATION, ErreurOutil, ErreurParametres
from outils.commun.fichiers import encodage_fichier, lire_taille, taille_lisible
from outils.commun.outil import Outil

OUTIL = Outil("valider_fichier", "Controle des fichiers : non vide (defaut), --taille-min / --taille-max, --format "
              "json | jsonl | xml | csv (bien forme), --colonnes a,b,c (en-tete CSV exact), --nb-colonnes N, "
              "--lignes-min N (lignes de donnees CSV), --encodage utf-8 (octets valides). Un fichier invalide est "
              "une erreur (code 2) ; avec --code-si-invalide 1 c'est un avertissement et le code retour 1, que le "
              "moteur traduit en 'ignorer ce fichier' au point avant_fichier.", "controle")
LIMITE_ANALYSE = 200 * 1024 * 1024


@OUTIL.arguments
def arguments(p):
    options_entrees(p)
    p.add_argument("--non-vide", action="store_true", help="refuse un fichier de taille 0 (actif si aucun autre controle)")
    p.add_argument("--taille-min", metavar="TAILLE", help="taille minimale (ex. 1K)")
    p.add_argument("--taille-max", metavar="TAILLE", help="taille maximale")
    p.add_argument("--format", choices=("json", "jsonl", "xml", "csv"), help="le contenu doit etre bien forme")
    p.add_argument("--colonnes", metavar="A,B,C", help="CSV : noms exacts des colonnes de l'en-tete, dans l'ordre")
    p.add_argument("--nb-colonnes", type=int, metavar="N", help="CSV : nombre de colonnes de chaque ligne")
    p.add_argument("--lignes-min", type=int, metavar="N", help="CSV : nombre minimal de lignes de donnees (hors en-tete)")
    p.add_argument("--separateur", metavar="CAR", help="CSV : separateur (defaut : detecte)")
    p.add_argument("--sans-entete", action="store_true", help="CSV : pas d'en-tete")
    p.add_argument("--encodage", metavar="NOM", help="le contenu doit etre valide dans cet encodage (ex. utf-8)")
    p.add_argument("--code-si-invalide", type=int, default=2, choices=(1, 2), metavar="N",
                   help="code retour d'un fichier invalide : 2 (erreur, defaut) ou 1 (avertissement, ignorer le fichier)")


def _csv(chemin, args):
    encodage = encodage_fichier(chemin)[0]
    with open(chemin, encoding=encodage, errors="replace", newline="") as f:
        echantillon = f.readline()
    if args.separateur:
        sep = args.separateur
    else:
        comptes = {c: echantillon.count(c) for c in (";", ",", "\t", "|")}
        sep = max(comptes, key=lambda c: (comptes[c], c == ";")) if any(comptes.values()) else ";"
    with open(chemin, encoding=encodage, errors="replace", newline="") as f:
        lignes = [l for l in csv.reader(f, delimiter=sep) if l]
    if not lignes:
        raise ErreurOutil("CSV vide", BUSINESS_RULE_VIOLATION)
    largeur = args.nb_colonnes or len(lignes[0])
    for numero, ligne in enumerate(lignes, 1):
        if len(ligne) != largeur:
            raise ErreurOutil("CSV mal forme : %d colonne(s) a la ligne %d, %d attendue(s)" % (len(ligne), numero, largeur),
                              BUSINESS_RULE_VIOLATION)
    donnees = lignes if args.sans_entete else lignes[1:]
    if args.colonnes and not args.sans_entete:
        attendues = [c.strip() for c in args.colonnes.split(",")]
        lues = [c.strip().lstrip("\ufeff") for c in lignes[0]]
        if lues != attendues:
            raise ErreurOutil("colonnes differentes : %s au lieu de %s" % (",".join(lues), ",".join(attendues)),
                              BUSINESS_RULE_VIOLATION)
    if args.lignes_min is not None and len(donnees) < args.lignes_min:
        raise ErreurOutil("%d ligne(s) de donnees, %d au minimum" % (len(donnees), args.lignes_min), BUSINESS_RULE_VIOLATION)


def controler(chemin, args):
    taille = os.path.getsize(chemin)
    if (args.non_vide or not (args.taille_min or args.taille_max or args.format or args.encodage)) and taille == 0:
        raise ErreurOutil("fichier vide", BUSINESS_RULE_VIOLATION)
    if args.taille_min and taille < lire_taille(args.taille_min):
        raise ErreurOutil("trop petit : %s (minimum %s)" % (taille_lisible(taille), args.taille_min), BUSINESS_RULE_VIOLATION)
    if args.taille_max and taille > lire_taille(args.taille_max):
        raise ErreurOutil("trop gros : %s (maximum %s)" % (taille_lisible(taille), args.taille_max), BUSINESS_RULE_VIOLATION)
    if (args.format or args.encodage) and taille > LIMITE_ANALYSE:
        raise ErreurOutil("trop gros pour etre analyse (%s)" % taille_lisible(taille), BUSINESS_RULE_VIOLATION)
    if args.encodage:
        with open(chemin, "rb") as f:
            try:
                f.read().decode(args.encodage)
            except UnicodeDecodeError as e:
                raise ErreurOutil("octet invalide en %s a la position %d" % (args.encodage, e.start), BUSINESS_RULE_VIOLATION)
    try:
        if args.format == "json":
            with open(chemin, encoding="utf-8-sig") as f:
                json.load(f)
        elif args.format == "jsonl":
            with open(chemin, encoding="utf-8-sig") as f:
                for numero, ligne in enumerate(f, 1):
                    if ligne.strip():
                        try:
                            json.loads(ligne)
                        except ValueError as e:
                            raise ErreurOutil("JSON invalide a la ligne %d : %s" % (numero, e), BUSINESS_RULE_VIOLATION)
        elif args.format == "xml":
            ET.parse(chemin)
        elif args.format == "csv":
            _csv(chemin, args)
    except (ValueError, ET.ParseError, csv.Error) as e:
        raise ErreurOutil("contenu %s mal forme : %s" % (args.format.upper(), e), BUSINESS_RULE_VIOLATION)


@OUTIL.principal
def principal(ctx, args):
    if args.colonnes and args.format != "csv":
        raise ErreurParametres("--colonnes exige --format csv")
    for opt in ("taille_min", "taille_max"):
        if getattr(args, opt):
            lire_taille(getattr(args, opt))
    if args.encodage:
        try:
            "".encode(args.encodage)
        except LookupError:
            raise ErreurParametres("encodage inconnu : %s" % args.encodage)
    for chemin, _ in ctx.fichiers():
        try:
            controler(chemin, args)
        except ErreurOutil as e:
            if args.code_si_invalide == 1:
                ctx.avertir("fichier_invalide", "Fichier invalide (%s) : %s" % (e, os.path.basename(chemin)), fichier=chemin,
                            raison=str(e))
                ctx.compter("invalides")
                ctx.imposer_code(1)
            else:
                ctx.compter("invalides")
                ctx.echec("fichier_invalide", "Fichier invalide (%s) : %s" % (e, os.path.basename(chemin)), BUSINESS_RULE_VIOLATION,
                          fichier=chemin, raison=str(e))
            continue
        except OSError as e:
            with ctx.tolerer("lecture_echec", fichier=chemin):
                raise
            continue
        ctx.action("fichier_valide", "Fichier valide : %s" % os.path.basename(chemin), compteur="valides", fichier=chemin,
                   taille=os.path.getsize(chemin))


if __name__ == "__main__":
    OUTIL.lancer()
