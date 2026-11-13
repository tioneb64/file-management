# outil: encodage_convertir
# description: Convertit l'encodage de fichiers texte.
# parametre: --de ENCODAGE | facultatif | encodage d'origine (defaut auto)
# parametre: --vers {utf-8,utf-8-sig,cp1252,latin-1,utf-16} | obligatoire | encodage cible
# parametre: --sortie-dossier DOSSIER | facultatif | ecrit les fichiers convertis ici au lieu de les remplacer
# parametre: --sauvegarde | facultatif | sur place : garde l'original sous <fichier>.bak
# parametre: --ecraser | facultatif | autorise le remplacement d'un fichier de sortie ou d'un .bak existant
# parametre: --taille-max TAILLE | facultatif | taille maximale d'un fichier (lu en entier ; defaut 200M)
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Convertit l'encodage de fichiers texte : UTF-8 <-> ANSI (cp1252) / Latin-1 / UTF-16, avec ou sans BOM."""
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import BUSINESS_RULE_VIOLATION, ErreurOutil, ErreurParametres, RESOURCE_EXHAUSTED
from outils.commun.fichiers import (detecter_encodage, est_binaire, lire_taille, sortie_atomique, taille_lisible,
                                    verifier_ecrasement)
from outils.commun.outil import Outil

ENCODAGES = ("utf-8", "utf-8-sig", "cp1252", "latin-1", "utf-16")
OUTIL = Outil("encodage_convertir", "Convertit l'encodage de fichiers texte. --de auto (defaut) detecte BOM, UTF-8 "
              "strict, sinon ANSI cp1252. --vers : utf-8 (sans BOM), utf-8-sig (avec BOM), cp1252 (ANSI), latin-1, "
              "utf-16. Un caractere non representable dans l'encodage cible est une erreur de l'element (rien "
              "n'est perdu en silence). Remplace le fichier sur place, ou ecrit dans --sortie-dossier.",
              "conversion")


@OUTIL.arguments
def arguments(p):
    options_entrees(p)
    p.add_argument("--de", default="auto", metavar="ENCODAGE", help="encodage d'origine (defaut auto)")
    p.add_argument("--vers", required=True, choices=ENCODAGES, help="encodage cible")
    p.add_argument("--sortie-dossier", metavar="DOSSIER", help="ecrit les fichiers convertis ici au lieu de les remplacer")
    p.add_argument("--sauvegarde", action="store_true", help="sur place : garde l'original sous <fichier>.bak")
    p.add_argument("--ecraser", action="store_true", help="autorise le remplacement d'un fichier de sortie ou d'un .bak existant")
    p.add_argument("--taille-max", default="200M", metavar="TAILLE", help="taille maximale d'un fichier (lu en entier ; defaut 200M)")


@OUTIL.principal
def principal(ctx, args):
    maxi = lire_taille(args.taille_max)
    if args.de != "auto":
        try:
            "".encode(args.de)
        except LookupError:
            raise ErreurParametres("encodage d'origine inconnu : %s" % args.de)
    for chemin, base in ctx.fichiers():
        with ctx.tolerer("conversion_echec", fichier=chemin):
            taille = os.path.getsize(chemin)
            if taille > maxi:
                raise ErreurOutil("fichier trop gros (%s, limite %s)" % (taille_lisible(taille), taille_lisible(maxi)),
                                  RESOURCE_EXHAUSTED)
            with open(chemin, "rb") as f:
                octets = f.read()
            if est_binaire(octets):
                ctx.compter("binaires_ignores")
                continue
            origine = detecter_encodage(octets)[0] if args.de == "auto" else args.de
            if origine == "utf-8":
                origine = "utf-8-sig"                   # un BOM eventuel ne doit pas devenir un caractere
            try:
                texte = octets.decode(origine)
            except UnicodeDecodeError as e:
                raise ErreurOutil("contenu non valide en %s (octet %d) : preciser --de" % (origine, e.start),
                                  BUSINESS_RULE_VIOLATION)
            try:
                sortie = texte.encode(args.vers)
            except UnicodeEncodeError as e:
                raise ErreurOutil("caractere %r non representable en %s (position %d)"
                                  % (texte[e.start], args.vers, e.start), BUSINESS_RULE_VIOLATION)
            if sortie == octets and not args.sortie_dossier:
                ctx.compter("deja_conformes")
                ctx.debug("deja_conforme", "Deja en %s : %s" % (args.vers, os.path.basename(chemin)), fichier=chemin)
                continue
            if args.sortie_dossier:
                destination = os.path.join(args.sortie_dossier, os.path.relpath(chemin, base))
            else:
                destination = chemin
            if ctx.simulation:
                verifier_ecrasement(destination, args.ecraser or destination == chemin)
                ctx.action("fichier_a_convertir", "Serait converti de %s en %s : %s"
                           % (origine, args.vers, os.path.basename(chemin)), fichier=chemin, de=origine, vers=args.vers)
                continue
            if args.sauvegarde and destination == chemin:
                verifier_ecrasement(chemin + ".bak", args.ecraser)
                shutil.copy2(chemin, chemin + ".bak")
            with sortie_atomique(destination, ecraser=args.ecraser or destination == chemin) as tmp:
                with open(tmp, "wb") as f:
                    f.write(sortie)
                if destination == chemin:
                    shutil.copymode(chemin, tmp)
            ctx.action("fichier_converti", "Converti de %s en %s : %s" % (origine, args.vers, os.path.basename(chemin)),
                       fichier=chemin, cible=destination, de=origine, vers=args.vers)


if __name__ == "__main__":
    OUTIL.lancer()
