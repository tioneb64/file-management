# outil: fin_ligne_convertir
# description: Convertit les fins de ligne en CRLF ou en LF (octets : l'encodage n'est pas touche, les fichiers binaires et UTF-16 sont ignores).
# parametre: --vers {crlf,lf} | obligatoire | fin de ligne cible
# parametre: --sortie-dossier DOSSIER | facultatif | ecrit les fichiers convertis ici au lieu de les remplacer
# parametre: --sauvegarde | facultatif | sur place : garde l'original sous <fichier>.bak
# parametre: --ecraser | facultatif | autorise le remplacement d'un fichier de sortie ou d'un .bak existant
# parametre: --taille-max TAILLE | facultatif | taille maximale d'un fichier (defaut 200M)
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Convertit les fins de ligne de fichiers texte : CRLF (Windows) <-> LF (Unix)."""
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import ErreurOutil, RESOURCE_EXHAUSTED
from outils.commun.fichiers import est_binaire, lire_taille, sortie_atomique, taille_lisible, verifier_ecrasement
from outils.commun.outil import Outil

OUTIL = Outil("fin_ligne_convertir", "Convertit les fins de ligne en CRLF ou en LF (octets : l'encodage n'est pas "
              "touche, les fichiers binaires et UTF-16 sont ignores). Un CR isole est traite comme une fin de "
              "ligne. Remplace le fichier sur place ou ecrit dans --sortie-dossier ; un fichier deja conforme "
              "n'est pas reecrit.", "conversion")


@OUTIL.arguments
def arguments(p):
    options_entrees(p)
    p.add_argument("--vers", required=True, choices=("crlf", "lf"), help="fin de ligne cible")
    p.add_argument("--sortie-dossier", metavar="DOSSIER", help="ecrit les fichiers convertis ici au lieu de les remplacer")
    p.add_argument("--sauvegarde", action="store_true", help="sur place : garde l'original sous <fichier>.bak")
    p.add_argument("--ecraser", action="store_true", help="autorise le remplacement d'un fichier de sortie ou d'un .bak existant")
    p.add_argument("--taille-max", default="200M", metavar="TAILLE", help="taille maximale d'un fichier (defaut 200M)")


@OUTIL.principal
def principal(ctx, args):
    maxi = lire_taille(args.taille_max)
    for chemin, base in ctx.fichiers():
        with ctx.tolerer("conversion_echec", fichier=chemin):
            taille = os.path.getsize(chemin)
            if taille > maxi:
                raise ErreurOutil("fichier trop gros (%s, limite %s)" % (taille_lisible(taille), taille_lisible(maxi)),
                                  RESOURCE_EXHAUSTED)
            with open(chemin, "rb") as f:
                octets = f.read()
            if est_binaire(octets) or octets.startswith((b"\xff\xfe", b"\xfe\xff")):
                ctx.compter("binaires_ignores")
                continue
            neutre = re.sub(rb"\r\n|\r", b"\n", octets)
            sortie = neutre.replace(b"\n", b"\r\n") if args.vers == "crlf" else neutre
            if sortie == octets and not args.sortie_dossier:
                ctx.compter("deja_conformes")
                ctx.debug("deja_conforme", "Deja en %s : %s" % (args.vers.upper(), os.path.basename(chemin)), fichier=chemin)
                continue
            destination = os.path.join(args.sortie_dossier, os.path.relpath(chemin, base)) if args.sortie_dossier else chemin
            if ctx.simulation:
                verifier_ecrasement(destination, args.ecraser or destination == chemin)
                ctx.action("fichier_a_convertir", "Serait converti en %s : %s" % (args.vers.upper(), os.path.basename(chemin)),
                           fichier=chemin, vers=args.vers)
                continue
            if args.sauvegarde and destination == chemin:
                verifier_ecrasement(chemin + ".bak", args.ecraser)
                shutil.copy2(chemin, chemin + ".bak")
            with sortie_atomique(destination, ecraser=args.ecraser or destination == chemin) as tmp:
                with open(tmp, "wb") as f:
                    f.write(sortie)
                if destination == chemin:
                    shutil.copymode(chemin, tmp)
            ctx.action("fichier_converti", "Converti en %s : %s" % (args.vers.upper(), os.path.basename(chemin)),
                       fichier=chemin, cible=destination, vers=args.vers)


if __name__ == "__main__":
    OUTIL.lancer()
