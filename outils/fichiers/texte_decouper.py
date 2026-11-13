# outil: texte_decouper
# description: Decoupe un fichier texte en <nom>_001<ext>, <nom>_002<ext>... : --lignes N (N lignes par fichier) ou --taille T (T octets au plus, coupe a une fin de ligne).
# parametre: --lignes N | facultatif | nombre de lignes par morceau
# parametre: --taille TAILLE | facultatif | taille maximale d'un morceau (ex. 50M)
# parametre: --entete | facultatif | repete la premiere ligne dans chaque morceau
# parametre: --vers DOSSIER | facultatif | dossier des morceaux (defaut : celui du fichier)
# parametre: --ecraser | facultatif | remplace des morceaux existants
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
"""Decoupe un gros fichier texte (journal, CSV...) en plusieurs fichiers, par nombre de lignes ou par taille."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import BUSINESS_RULE_VIOLATION, ErreurOutil, ErreurParametres
from outils.commun.fichiers import SUFFIXE_TEMPORAIRE, lire_taille, verifier_ecrasement
from outils.commun.outil import Outil

OUTIL = Outil("texte_decouper", "Decoupe un fichier texte en <nom>_001<ext>, <nom>_002<ext>... : --lignes N (N lignes "
              "par fichier) ou --taille T (T octets au plus, coupe a une fin de ligne). --entete repete la premiere "
              "ligne (en-tete CSV) en tete de chaque morceau. Les octets sont recopies tels quels (encodage et "
              "fins de ligne inchanges).", "fichiers")


@OUTIL.arguments
def arguments(p):
    options_entrees(p, recursif=False)
    p.add_argument("--lignes", type=int, metavar="N", help="nombre de lignes par morceau")
    p.add_argument("--taille", metavar="TAILLE", help="taille maximale d'un morceau (ex. 50M)")
    p.add_argument("--entete", action="store_true", help="repete la premiere ligne dans chaque morceau")
    p.add_argument("--vers", metavar="DOSSIER", help="dossier des morceaux (defaut : celui du fichier)")
    p.add_argument("--ecraser", action="store_true", help="remplace des morceaux existants")


def decouper(chemin, sortie_base, ext, lignes, taille, entete, ecrire=True):
    """Ecrit les morceaux ; renvoie leurs noms. Ecriture sous nom temporaire, renommage a la fin."""
    noms, courant, n_lignes, n_octets, tete = [], None, 0, 0, b""
    def ouvrir():
        nom = "%s_%03d%s" % (sortie_base, len(noms) + 1, ext)
        noms.append(nom)
        f = open(nom + SUFFIXE_TEMPORAIRE, "wb") if ecrire else True
        if ecrire and tete:
            f.write(tete)
        return f, len(tete), (1 if tete else 0)
    with open(chemin, "rb") as source:
        premiere = True
        for ligne in source:
            if premiere and entete:
                tete, premiere = ligne, False
                continue
            premiere = False
            if courant is None or (lignes and n_lignes >= lignes) or (taille and n_octets + len(ligne) > taille and n_lignes):
                if courant is not None and ecrire:
                    courant.close()
                courant, n_octets, _ = ouvrir()
                n_lignes = 0
            if ecrire:
                courant.write(ligne)
            n_lignes += 1
            n_octets += len(ligne)
    if courant is not None and ecrire:
        courant.close()
    return noms


@OUTIL.principal
def principal(ctx, args):
    if bool(args.lignes) == bool(args.taille):
        raise ErreurParametres("indiquer --lignes OU --taille")
    if args.lignes is not None and args.lignes < 1:
        raise ErreurParametres("--lignes : au moins 1")
    taille = lire_taille(args.taille) if args.taille else None
    for chemin, _ in ctx.fichiers(dossiers=False):
        with ctx.tolerer("decoupage_echec", fichier=chemin):
            with open(chemin, "rb") as f:
                debut = f.read(4)
            if debut.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in debut:
                raise ErreurOutil("fichier UTF-16 ou binaire : decoupage par lignes impossible", BUSINESS_RULE_VIOLATION)
            dossier = args.vers or os.path.dirname(os.path.abspath(chemin))
            racine, ext = os.path.splitext(os.path.basename(chemin))
            base = os.path.join(dossier, racine)
            noms = decouper(chemin, base, ext, args.lignes, taille, args.entete, ecrire=False)
            if len(noms) <= 1:
                ctx.info("decoupage_inutile", "Un seul morceau suffit : %s" % os.path.basename(chemin), fichier=chemin)
                continue
            for nom in noms:
                verifier_ecrasement(nom, args.ecraser)
            if ctx.simulation:
                ctx.action("fichier_a_decouper", "Serait decoupe en %d morceaux : %s" % (len(noms), os.path.basename(chemin)),
                           fichier=chemin, morceaux=len(noms))
                continue
            os.makedirs(dossier, exist_ok=True)
            try:
                noms = decouper(chemin, base, ext, args.lignes, taille, args.entete)
                for nom in noms:
                    os.replace(nom + SUFFIXE_TEMPORAIRE, nom)
            finally:
                for nom in noms:
                    try:
                        os.remove(nom + SUFFIXE_TEMPORAIRE)
                    except OSError:
                        pass
            ctx.action("fichier_decoupe", "Decoupe en %d morceaux : %s" % (len(noms), os.path.basename(chemin)),
                       fichier=chemin, morceaux=len(noms))


if __name__ == "__main__":
    OUTIL.lancer()
