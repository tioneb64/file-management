# outil: fichier_recoller
# description: Recolle <nom>.001, <nom>.002... en <nom>.
# parametre: --sortie FICHIER | facultatif | fichier recolle (defaut : le nom sans le .001, a cote)
# parametre: --ecraser | facultatif | remplace le fichier recolle s'il existe
# parametre: --supprimer-morceaux | facultatif | supprime les morceaux (et le manifeste) apres un recollage verifie
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
"""Recolle les morceaux produits par fichier_decouper (ou tout fichier nom.001, nom.002...) en un seul fichier."""
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import BUSINESS_RULE_VIOLATION, ErreurOutil, FILE_NOT_FOUND
from outils.commun.fichiers import TAILLE_BLOC, sortie_atomique, taille_lisible, verifier_ecrasement
from outils.commun.outil import Outil

OUTIL = Outil("fichier_recoller", "Recolle <nom>.001, <nom>.002... en <nom>. Verifie la suite des numeros (aucun "
              "morceau manquant) et, si <nom>.manifeste.json existe, la taille et le SHA-256 du resultat. "
              "Designer le premier morceau (<nom>.001).", "compression")
_RE_MORCEAU = re.compile(r"^(.*)\.(\d{3,})$")


@OUTIL.arguments
def arguments(p):
    options_entrees(p, recursif=False, masques=False)
    p.add_argument("--sortie", metavar="FICHIER", help="fichier recolle (defaut : le nom sans le .001, a cote)")
    p.add_argument("--ecraser", action="store_true", help="remplace le fichier recolle s'il existe")
    p.add_argument("--supprimer-morceaux", action="store_true",
                   help="supprime les morceaux (et le manifeste) apres un recollage verifie")


def morceaux_de(premier):
    """(base, [chemins des morceaux 001, 002...]) ; ErreurOutil si un numero manque."""
    m = _RE_MORCEAU.match(premier)
    if not m:
        raise ErreurOutil("ce n'est pas un morceau (nom.001 attendu) : %s" % os.path.basename(premier),
                          BUSINESS_RULE_VIOLATION)
    base, largeur = m.group(1), len(m.group(2))
    dossier, nom_base = os.path.dirname(os.path.abspath(base)), os.path.basename(base)
    numeros = sorted(int(x.group(2)) for x in (_RE_MORCEAU.match(f) for f in os.listdir(dossier))
                     if x and x.group(1) == nom_base)
    if not numeros or numeros[0] != 1:
        raise ErreurOutil("le premier morceau (%s.%0*d) est introuvable" % (nom_base, largeur, 1), FILE_NOT_FOUND)
    for attendu in range(1, numeros[-1] + 1):
        if attendu not in numeros:
            raise ErreurOutil("morceau manquant : %s.%0*d (morceaux presents : %d sur %d)"
                              % (nom_base, largeur, attendu, len(numeros), numeros[-1]), FILE_NOT_FOUND)
    liste = ["%s.%0*d" % (base, largeur, n) for n in numeros]
    return base, liste


@OUTIL.principal
def principal(ctx, args):
    for premier, _ in ctx.fichiers(dossiers=False):
        with ctx.tolerer("recollage_echec", fichier=premier):
            base, liste = morceaux_de(premier)
            sortie = args.sortie or base
            total = sum(os.path.getsize(c) for c in liste)
            manifeste = base + ".manifeste.json"
            attendu = None
            if os.path.isfile(manifeste):
                with open(manifeste, encoding="utf-8") as f:
                    attendu = json.load(f)
                noms = [os.path.basename(c) for c in liste]
                if noms != [m["nom"] for m in attendu["morceaux"]] or total != attendu["taille"]:
                    raise ErreurOutil("les morceaux ne correspondent pas au manifeste (nombre ou tailles)",
                                      BUSINESS_RULE_VIOLATION)
            if ctx.simulation:
                verifier_ecrasement(sortie, args.ecraser)
                ctx.action("fichier_a_recoller", "Serait recolle (%d morceaux, %s) : %s"
                           % (len(liste), taille_lisible(total), os.path.basename(sortie)), fichier=sortie,
                           taille=total, morceaux=len(liste))
                continue
            h = hashlib.sha256()
            with sortie_atomique(sortie, args.ecraser) as tmp:
                with open(tmp, "wb") as out:
                    for chemin in liste:
                        with open(chemin, "rb") as f:
                            while True:
                                bloc = f.read(TAILLE_BLOC)
                                if not bloc:
                                    break
                                h.update(bloc)
                                out.write(bloc)
                if attendu and h.hexdigest() != attendu["sha256"]:
                    raise ErreurOutil("SHA-256 different du manifeste : un morceau est corrompu",
                                      BUSINESS_RULE_VIOLATION)
            ctx.action("fichier_recolle", "Fichier recolle (%d morceaux) : %s" % (len(liste), os.path.basename(sortie)),
                       fichier=sortie, taille=total, morceaux=len(liste), sha256=h.hexdigest(),
                       verifie_par_manifeste=attendu is not None)
            if args.supprimer_morceaux:
                for chemin in liste + ([manifeste] if attendu else []):
                    os.remove(chemin)
                    ctx.info("fichier_supprime", "Morceau supprime : %s" % os.path.basename(chemin), fichier=chemin)


if __name__ == "__main__":
    OUTIL.lancer()
