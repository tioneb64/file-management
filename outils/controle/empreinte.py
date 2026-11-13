# outil: empreinte
# description: Empreintes SHA-256.
# parametre: --generer | facultatif | ecrit les fichiers d'empreintes
# parametre: --verifier | facultatif | verifie les fichiers contre les empreintes
# parametre: --afficher | facultatif | affiche les empreintes
# parametre: --algo {md5,sha1,sha256,sha512} | facultatif | algorithme (defaut sha256)
# parametre: --manifeste FICHIER | facultatif | un seul fichier d'empreintes pour tous (noms relatifs a son dossier)
# parametre: --attendu HASH | facultatif | verifier : empreinte attendue (un seul fichier)
# parametre: --ecraser | facultatif | generer : remplace un fichier d'empreintes existant
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Genere ou verifie les empreintes SHA-256 de fichiers (fichiers .sha256 au format sha256sum)."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import FILE_IO_ERROR, FILE_NOT_FOUND, ErreurOutil, ErreurParametres
from outils.commun.fichiers import sha256_fichier, sortie_atomique, verifier_ecrasement
from outils.commun.outil import Outil

OUTIL = Outil("empreinte", "Empreintes SHA-256. --generer ecrit <fichier>.sha256 a cote de chaque fichier (ligne "
              "\"<hash> *<nom>\", format de sha256sum), ou un seul fichier --manifeste. --verifier relit chaque "
              "fichier et le compare au .sha256 voisin, au --manifeste, ou a --attendu HASH ; un ecart est une "
              "erreur (code 2). --afficher imprime les empreintes sans rien ecrire.", "controle")
_RE_LIGNE = re.compile(r"^([0-9A-Fa-f]{32,128})\s+\*?(.+)$")
ALGOS = {"sha256": ".sha256", "sha512": ".sha512", "sha1": ".sha1", "md5": ".md5"}


@OUTIL.arguments
def arguments(p):
    options_entrees(p)
    groupe = p.add_mutually_exclusive_group(required=True)
    groupe.add_argument("--generer", action="store_true", help="ecrit les fichiers d'empreintes")
    groupe.add_argument("--verifier", action="store_true", help="verifie les fichiers contre les empreintes")
    groupe.add_argument("--afficher", action="store_true", help="affiche les empreintes")
    p.add_argument("--algo", choices=sorted(ALGOS), default="sha256", help="algorithme (defaut sha256)")
    p.add_argument("--manifeste", metavar="FICHIER", help="un seul fichier d'empreintes pour tous (noms relatifs a son dossier)")
    p.add_argument("--attendu", metavar="HASH", help="verifier : empreinte attendue (un seul fichier)")
    p.add_argument("--ecraser", action="store_true", help="generer : remplace un fichier d'empreintes existant")


def lire_manifeste(chemin):
    resultat = {}
    with open(chemin, encoding="utf-8-sig") as f:
        for ligne in f:
            m = _RE_LIGNE.match(ligne.rstrip("\r\n"))
            if m:
                resultat[os.path.normcase(m.group(2).replace("/", os.sep))] = m.group(1).lower()
    return resultat


@OUTIL.principal
def principal(ctx, args):
    if args.attendu and not args.verifier:
        raise ErreurParametres("--attendu va avec --verifier")
    extension = ALGOS[args.algo]
    fichiers = list(ctx.fichiers())
    if args.attendu and len(fichiers) != 1:
        raise ErreurParametres("--attendu : un seul fichier")
    manifeste = None
    if args.manifeste and args.verifier:
        with ctx.tolerer("manifeste_illisible", fichier=args.manifeste):
            manifeste = lire_manifeste(args.manifeste)
        if manifeste is None:
            return
    lignes = []
    for chemin, _ in fichiers:
        with ctx.tolerer("empreinte_echec", fichier=chemin):
            h = sha256_fichier(chemin, args.algo)
            nom = os.path.basename(chemin)
            if args.afficher:
                ctx.afficher("%s *%s" % (h, chemin))
                ctx.action("empreinte_calculee", "Empreinte calculee : %s" % nom, compteur="calculees", fichier=chemin, **{args.algo: h})
            elif args.generer:
                if args.manifeste:
                    base = os.path.dirname(os.path.abspath(args.manifeste))
                    lignes.append("%s *%s" % (h, os.path.relpath(chemin, base).replace("\\", "/")))
                    ctx.action("empreinte_calculee", "Empreinte calculee : %s" % nom, compteur="calculees", fichier=chemin, **{args.algo: h})
                    continue
                voisin = chemin + extension
                verifier_ecrasement(voisin, args.ecraser)
                if ctx.simulation:
                    ctx.action("empreinte_a_ecrire", "Empreinte serait ecrite : %s" % os.path.basename(voisin), fichier=chemin, **{args.algo: h})
                    continue
                with sortie_atomique(voisin, args.ecraser) as tmp:
                    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                        f.write("%s *%s\n" % (h, nom))
                ctx.action("empreinte_ecrite", "Empreinte ecrite : %s" % os.path.basename(voisin), fichier=chemin, cible=voisin, **{args.algo: h})
            else:
                if args.attendu:
                    attendu = args.attendu.lower()
                elif manifeste is not None:
                    cle = os.path.normcase(os.path.relpath(chemin, os.path.dirname(os.path.abspath(args.manifeste))))
                    attendu = manifeste.get(cle)
                    if attendu is None:
                        raise ErreurOutil("fichier absent du manifeste : %s" % nom, FILE_NOT_FOUND)
                else:
                    voisin = chemin + extension
                    if not os.path.isfile(voisin):
                        raise ErreurOutil("fichier d'empreinte introuvable : %s" % voisin, FILE_NOT_FOUND)
                    lues = lire_manifeste(voisin)
                    attendu = lues.get(os.path.normcase(nom)) or (list(lues.values())[0] if len(lues) == 1 else None)
                    if attendu is None:
                        raise ErreurOutil("empreinte de %s introuvable dans %s" % (nom, voisin), FILE_NOT_FOUND)
                if h != attendu:
                    raise ErreurOutil("empreinte differente pour %s : calculee %s, attendue %s" % (nom, h[:16], attendu[:16]),
                                      FILE_IO_ERROR)
                ctx.action("empreinte_verifiee", "Empreinte verifiee : %s" % nom, compteur="verifiees", fichier=chemin, **{args.algo: h})
    if args.generer and args.manifeste and lignes and not ctx.simulation:
        with sortie_atomique(args.manifeste, args.ecraser) as tmp:
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write("".join(l + "\n" for l in lignes))
        ctx.info("manifeste_ecrit", "Manifeste ecrit : %s" % os.path.basename(args.manifeste), fichier=args.manifeste,
                 fichiers=len(lignes))


if __name__ == "__main__":
    OUTIL.lancer()
