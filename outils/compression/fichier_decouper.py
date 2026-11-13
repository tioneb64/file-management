# outil: fichier_decouper
# description: Decoupe un gros fichier en morceaux (defaut 100M) : <nom>.001, <nom>.002... et un manifeste <nom>.manifeste.json (taille, SHA-256 du fichier entier) lu par fichier_recoller.
# parametre: --taille TAILLE | facultatif | taille d'un morceau (defaut 100M ; 500K, 1G...)
# parametre: --vers DOSSIER | facultatif | dossier des morceaux (defaut : celui du fichier)
# parametre: --ecraser | facultatif | remplace des morceaux existants
# parametre: --supprimer-source | facultatif | supprime le fichier d'origine une fois les morceaux ecrits et verifies
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
"""Decoupe un gros fichier en morceaux de taille fixe (nom.001, nom.002...) avec un manifeste SHA-256."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import ErreurOutil, RESOURCE_EXHAUSTED
from outils.commun.fichiers import (TAILLE_BLOC, lire_taille, sortie_atomique, taille_lisible, verifier_ecrasement)
from outils.commun.outil import Outil
import hashlib
import shutil

OUTIL = Outil("fichier_decouper", "Decoupe un gros fichier en morceaux (defaut 100M) : <nom>.001, <nom>.002... et un "
              "manifeste <nom>.manifeste.json (taille, SHA-256 du fichier entier) lu par fichier_recoller.",
              "compression")


@OUTIL.arguments
def arguments(p):
    options_entrees(p, recursif=False)
    p.add_argument("--taille", default="100M", metavar="TAILLE", help="taille d'un morceau (defaut 100M ; 500K, 1G...)")
    p.add_argument("--vers", metavar="DOSSIER", help="dossier des morceaux (defaut : celui du fichier)")
    p.add_argument("--ecraser", action="store_true", help="remplace des morceaux existants")
    p.add_argument("--supprimer-source", action="store_true",
                   help="supprime le fichier d'origine une fois les morceaux ecrits et verifies")


def _ecrire_morceaux(source, morceau, noms):
    """Ecrit les morceaux sous leur nom temporaire ; renvoie (empreinte, [(nom, taille)])."""
    h = hashlib.sha256()
    resultat = []
    with open(source, "rb") as f:
        numero = 0
        while True:
            numero += 1
            nom = noms(numero)
            restant, ecrit = morceau, 0
            tmp = nom + ".copie_en_cours"
            with open(tmp, "wb") as sortie:
                while restant:
                    bloc = f.read(min(TAILLE_BLOC, restant))
                    if not bloc:
                        break
                    h.update(bloc)
                    sortie.write(bloc)
                    restant -= len(bloc)
                    ecrit += len(bloc)
            if ecrit == 0:
                os.remove(tmp)
                return h.hexdigest(), resultat
            resultat.append((nom, ecrit))
            if ecrit < morceau:
                return h.hexdigest(), resultat


@OUTIL.principal
def principal(ctx, args):
    morceau = lire_taille(args.taille)
    for source, _ in ctx.fichiers(dossiers=False):
        with ctx.tolerer("decoupage_echec", fichier=source):
            taille = os.path.getsize(source)
            dossier = args.vers or os.path.dirname(os.path.abspath(source))
            base = os.path.join(dossier, os.path.basename(source))
            nombre = max(1, -(-taille // morceau))
            noms = lambda n: "%s.%03d" % (base, n)
            manifeste = base + ".manifeste.json"
            if taille <= morceau:
                ctx.info("decoupage_inutile", "Fichier deja plus petit que la taille d'un morceau : %s"
                         % os.path.basename(source), fichier=source, taille=taille)
                continue
            for n in range(1, nombre + 1):
                verifier_ecrasement(noms(n), args.ecraser)
            verifier_ecrasement(manifeste, args.ecraser)
            if ctx.simulation:
                ctx.action("fichier_a_decouper", "Serait decoupe en %d morceau(x) de %s : %s"
                           % (nombre, taille_lisible(morceau), os.path.basename(source)), fichier=source,
                           taille=taille, morceaux=nombre)
                continue
            os.makedirs(dossier, exist_ok=True)
            libre = shutil.disk_usage(dossier).free
            if libre < taille:
                raise ErreurOutil("espace insuffisant dans %s : %s necessaires, %s libres"
                                  % (dossier, taille_lisible(taille), taille_lisible(libre)), RESOURCE_EXHAUSTED)
            empreinte, ecrits = _ecrire_morceaux(source, morceau, noms)
            try:
                if sum(t for _, t in ecrits) != taille:
                    raise ErreurOutil("le fichier a change pendant le decoupage : %s" % source)
                for nom, _ in ecrits:
                    os.replace(nom + ".copie_en_cours", nom)
                with sortie_atomique(manifeste, args.ecraser) as tmp:
                    with open(tmp, "w", encoding="utf-8") as m:
                        json.dump({"fichier": os.path.basename(source), "taille": taille, "sha256": empreinte,
                                   "morceaux": [{"nom": os.path.basename(n), "taille": t} for n, t in ecrits]},
                                  m, indent=1)
            finally:
                for nom, _ in ecrits:
                    try:
                        os.remove(nom + ".copie_en_cours")
                    except OSError:
                        pass
            ctx.action("fichier_decoupe", "Fichier decoupe en %d morceau(x) : %s" % (len(ecrits), os.path.basename(source)),
                       fichier=source, taille=taille, morceaux=len(ecrits), sha256=empreinte)
            if args.supprimer_source:
                os.remove(source)
                ctx.info("fichier_supprime", "Fichier d'origine supprime : %s" % os.path.basename(source),
                         fichier=source)


if __name__ == "__main__":
    OUTIL.lancer()
