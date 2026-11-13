# outil: synchroniser
# description: Rend CIBLE identique a SOURCE : copie les fichiers absents ou modifies (taille ou date de modification differente a 2 s pres, ou SHA-256 avec --comparer contenu), chaque copie etant verifiee par SHA-256 (--sans-verification pour...
# parametre: SOURCE | facultatif | dossier source (defaut : COPIE_SOURCE)
# parametre: CIBLE | facultatif | dossier cible, cree si absent (defaut : COPIE_CIBLE)
# parametre: --miroir | facultatif | supprime de la cible fichiers et dossiers absents de la source
# parametre: --comparer {date,contenu} | facultatif | date (defaut) : taille et date ; contenu : SHA-256
# parametre: --masque JOKER | facultatif | ne synchronise que ces noms ; repetable
# parametre: --exclure JOKER | facultatif | ecarte ces noms (jamais supprimes de la cible) ; repetable
# parametre: --sans-verification | facultatif | ne relit pas les copies pour comparer le SHA-256
# parametre: --max-suppressions N | facultatif | refuse le miroir s'il supprimerait plus de N elements
# parametre: --autoriser-source-vide | facultatif | autorise un miroir depuis une source sans fichier
"""Synchronise un dossier cible avec un dossier source (miroir a la robocopy), avec simulation."""
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import retenu
from outils.commun.erreurs import BUSINESS_RULE_VIOLATION, FILE_NOT_FOUND, ErreurOutil, ErreurParametres
from outils.commun.fichiers import copier_verifie, est_dans, sha256_fichier
from outils.commun.outil import Outil

OUTIL = Outil("synchroniser", "Rend CIBLE identique a SOURCE : copie les fichiers absents ou modifies (taille ou date "
              "de modification differente a 2 s pres, ou SHA-256 avec --comparer contenu), chaque copie etant "
              "verifiee par SHA-256 (--sans-verification pour desactiver). Par defaut RIEN n'est supprime ; "
              "--miroir supprime de la cible ce qui n'existe plus dans la source. Garde-fous : refuse un miroir "
              "si la source est vide ou introuvable, si l'un des dossiers contient l'autre ; --max-suppressions "
              "borne les suppressions. Essayer d'abord avec --simulation (dry-run). Sans arguments : COPIE_SOURCE "
              "et COPIE_CIBLE.", "fichiers")
TOLERANCE_NS = 2 * 10 ** 9


@OUTIL.arguments
def arguments(p):
    p.add_argument("source", nargs="?", metavar="SOURCE", help="dossier source (defaut : COPIE_SOURCE)")
    p.add_argument("cible", nargs="?", metavar="CIBLE", help="dossier cible, cree si absent (defaut : COPIE_CIBLE)")
    p.add_argument("--miroir", action="store_true", help="supprime de la cible fichiers et dossiers absents de la source")
    p.add_argument("--comparer", choices=("date", "contenu"), default="date", help="date (defaut) : taille et date ; contenu : SHA-256")
    p.add_argument("--masque", action="append", default=[], metavar="JOKER", help="ne synchronise que ces noms ; repetable")
    p.add_argument("--exclure", action="append", default=[], metavar="JOKER", help="ecarte ces noms (jamais supprimes de la cible) ; repetable")
    p.add_argument("--sans-verification", action="store_true", help="ne relit pas les copies pour comparer le SHA-256")
    p.add_argument("--max-suppressions", type=int, metavar="N", help="refuse le miroir s'il supprimerait plus de N elements")
    p.add_argument("--autoriser-source-vide", action="store_true", help="autorise un miroir depuis une source sans fichier")


def _lister(racine, masques, exclusions):
    """{chemin relatif '/' : chemin complet} des fichiers (liens de dossier non suivis) et liste des dossiers."""
    fichiers, dossiers = {}, []
    for dossier, sous, noms in os.walk(racine):
        sous[:] = sorted(d for d in sous if not os.path.islink(os.path.join(dossier, d)))
        for d in sous:
            dossiers.append(os.path.relpath(os.path.join(dossier, d), racine).replace("\\", "/"))
        for nom in sorted(noms):
            complet = os.path.join(dossier, nom)
            relatif = os.path.relpath(complet, racine).replace("\\", "/")
            if retenu(nom, relatif, masques, exclusions):
                fichiers[relatif] = complet
    return fichiers, dossiers


def _different(source, cible, par_contenu):
    a, b = os.stat(source), os.stat(cible)
    if a.st_size != b.st_size:
        return True
    if par_contenu:
        return sha256_fichier(source) != sha256_fichier(cible)
    return abs(a.st_mtime_ns - b.st_mtime_ns) > TOLERANCE_NS


@OUTIL.principal
def principal(ctx, args):
    source = args.source or ctx.env.get("COPIE_SOURCE")
    cible = args.cible or ctx.env.get("COPIE_CIBLE")
    if not source or not cible:
        raise ErreurParametres("SOURCE et CIBLE sont obligatoires (arguments ou COPIE_SOURCE / COPIE_CIBLE)")
    source, cible = os.path.abspath(source), os.path.abspath(cible)
    if not os.path.isdir(source):
        raise ErreurOutil("dossier source introuvable : %s" % source, FILE_NOT_FOUND)
    if est_dans(source, cible) or est_dans(cible, source):
        raise ErreurParametres("la source et la cible ne doivent pas se contenir : %s / %s" % (source, cible))
    f_source, d_source = _lister(source, args.masque, args.exclure)
    if args.miroir and not f_source and not args.autoriser_source_vide:
        raise ErreurOutil("miroir refuse : la source ne contient aucun fichier (--autoriser-source-vide pour "
                          "vider la cible volontairement)", BUSINESS_RULE_VIOLATION)
    f_cible, d_cible = _lister(cible, args.masque, args.exclure) if os.path.isdir(cible) else ({}, [])
    a_supprimer = [r for r in f_cible if r not in f_source] if args.miroir else []
    # dossiers vides de la cible absents de la source : seulement apres les fichiers, du plus profond au plus haut
    dossiers_sources = set(d_source)
    dossiers_a_supprimer = sorted((d for d in d_cible if d not in dossiers_sources), key=lambda d: -d.count("/")) \
        if args.miroir and not args.masque and not args.exclure else []
    if args.max_suppressions is not None and len(a_supprimer) + len(dossiers_a_supprimer) > args.max_suppressions:
        raise ErreurOutil("miroir refuse : %d suppression(s) prevue(s), au-dessus de --max-suppressions %d"
                          % (len(a_supprimer) + len(dossiers_a_supprimer), args.max_suppressions), BUSINESS_RULE_VIOLATION)
    for d in sorted(d_source):
        destination = os.path.join(cible, *d.split("/"))
        if not os.path.isdir(destination):
            with ctx.tolerer("dossier_echec", fichier=destination):
                if not ctx.simulation:
                    os.makedirs(destination, exist_ok=True)
                ctx.action("dossier_cree", "Dossier %s : %s" % ("a creer" if ctx.simulation else "cree", d),
                           compteur="dossiers_crees", fichier=destination)
    for relatif, chemin in f_source.items():
        destination = os.path.join(cible, *relatif.split("/"))
        with ctx.tolerer("synchronisation_echec", fichier=chemin):
            existe = os.path.isfile(destination)
            if existe and not _different(chemin, destination, args.comparer == "contenu"):
                ctx.compter("identiques")
                continue
            evenement = "fichier_mis_a_jour" if existe else "fichier_copie"
            if ctx.simulation:
                ctx.action("fichier_a_copier", "Serait %s : %s" % ("mis a jour" if existe else "copie", relatif), compteur="a_copier",
                           fichier=chemin, cible=destination)
                continue
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if args.sans_verification:
                tmp = destination + ".copie_en_cours"
                try:
                    shutil.copy2(chemin, tmp)
                    os.replace(tmp, destination)
                finally:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                empreinte = None
            else:
                empreinte = copier_verifie(chemin, destination, ecraser=True)
            ctx.action(evenement, "%s : %s" % ("Mis a jour" if existe else "Copie", relatif), fichier=chemin,
                       cible=destination, taille=os.path.getsize(destination), sha256=empreinte,
                       compteur="mis_a_jour" if existe else "copies")
    for relatif in a_supprimer:
        chemin = os.path.join(cible, *relatif.split("/"))
        with ctx.tolerer("suppression_echec", fichier=chemin):
            if ctx.simulation:
                ctx.action("fichier_a_supprimer", "Serait supprime de la cible : %s" % relatif, compteur="a_supprimer",
                           fichier=chemin)
                continue
            os.remove(chemin)
            ctx.action("fichier_supprime", "Supprime de la cible : %s" % relatif, compteur="supprimes", fichier=chemin)
    for relatif in dossiers_a_supprimer:
        chemin = os.path.join(cible, *relatif.split("/"))
        with ctx.tolerer("suppression_echec", fichier=chemin):
            if ctx.simulation:
                ctx.action("dossier_a_supprimer", "Dossier serait supprime de la cible : %s" % relatif,
                           compteur="dossiers_a_supprimer", fichier=chemin)
                continue
            if not os.listdir(chemin):                      # un dossier qui contient encore un fichier exclu reste
                os.rmdir(chemin)
                ctx.action("dossier_supprime", "Dossier supprime de la cible : %s" % relatif,
                           compteur="dossiers_supprimes", fichier=chemin)


if __name__ == "__main__":
    OUTIL.lancer()
