"""Mesure du debit de transfert sur le serveur : livraison de N fichiers en mode copie, puis
deplacement, puis relance (tous les fichiers deja connus).

    C:\\Python314\\python.exe outils\\mesure_transfert.py [--fichiers 200] [--taille-ko 100]
        [--source D:\\temp] [--cible \\\\SERVEUR\\partage\\test] [--json rapports\\mesure_transfert.json]

--source : dossier LOCAL de travail (source, base, journaux). --cible : dossier d'arrivee, par
defaut un sous-dossier du dossier de travail ; indiquer un partage reseau pour mesurer le cas
reel. Tout est supprime a la fin.
"""
import argparse
import copy
import datetime
import json
import os
import platform
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import journal_si  # noqa: E402
from file_management import base, execution  # noqa: E402
from file_management.diagnostic import Rapport  # noqa: E402
from file_management.parametrage import Entete, lire_regle  # noqa: E402


def regle(ident, source, cible, mode):
    brut = {"id": ident, "source": source, "cible": cible, "mode": mode,
            "planification": {"type": "quotidien", "heure": "07:00"},
            "selection": {"age_minimum_sec": 0}}
    r = lire_regle(copy.deepcopy(brut), 1, Rapport())
    return r


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--fichiers", type=int, default=200)
    p.add_argument("--taille-ko", type=int, default=100)
    p.add_argument("--source", help="dossier local de travail")
    p.add_argument("--cible", help="dossier d'arrivee (partage reseau possible)")
    p.add_argument("--json", help="ecrit aussi le resultat dans ce fichier")
    args = p.parse_args()

    travail = tempfile.mkdtemp(prefix="mesure_transfert_", dir=args.source)
    cible_racine = tempfile.mkdtemp(prefix="mesure_transfert_", dir=args.cible) if args.cible \
        else os.path.join(travail, "cible")
    resultat = {"serveur": platform.node(), "python": platform.python_version(),
                "fichiers": args.fichiers, "taille_ko": args.taille_ko,
                "cible_reseau": bool(args.cible)}
    try:
        entete = Entete()
        entete.environnement = "mesure"
        entete.marge_espace_mo = 0
        chemin_base = os.path.join(travail, "mesure.db")
        base.initialiser(chemin_base, "mesure", "mesure")
        journal = journal_si.Journal()
        journal.debut("mesure", "mesure", dossier=os.path.join(travail, "logs"))
        contenu = os.urandom(args.taille_ko * 1024)

        def creer(dossier):
            os.makedirs(dossier, exist_ok=True)
            instant = time.time() - 600
            for i in range(args.fichiers):
                chemin = os.path.join(dossier, "f%05d.dat" % i)
                with open(chemin, "wb") as f:
                    f.write(contenu)
                os.utime(chemin, (instant + i % 100, instant + i % 100))

        def lancer(r, b):
            debut = time.time()
            bilan = execution.lancer_regle(r, entete, b, journal, dormir=lambda s: None)
            return bilan, time.time() - debut

        with base.ouvrir(chemin_base, "mesure") as b:
            for mode in ("copie", "deplacement"):
                source = os.path.join(travail, "source_" + mode)
                cible = os.path.join(cible_racine, mode)
                creer(source)
                r = regle(mode, source, cible, mode)
                b.synchroniser_regles([(r.id, "m")])
                bilan, duree = lancer(r, b)
                resultat[mode] = {"statut": bilan.statut, "livres": bilan.compteurs["livres"],
                                  "duree_s": round(duree, 2),
                                  "ms_par_fichier": round(duree / max(args.fichiers, 1) * 1000, 1),
                                  "mo_par_s": round(args.fichiers * args.taille_ko / 1024 / max(duree, 0.001), 1)}
                if mode == "copie":                   # relance : tout est connu, rien ne doit etre relivre
                    bilan, duree = lancer(r, b)
                    resultat["relance"] = {"livres": bilan.compteurs["livres"],
                                           "ignores": bilan.compteurs["ignores"],
                                           "duree_s": round(duree, 2)}
    finally:
        journal.fermer()
        shutil.rmtree(travail, ignore_errors=True)
        if args.cible:
            shutil.rmtree(cible_racine, ignore_errors=True)

    print("Mesure de transfert - %s - Python %s - cible %s" % (
        resultat["serveur"], resultat["python"], "reseau" if args.cible else "locale"))
    print("  %d fichiers de %d Ko" % (args.fichiers, args.taille_ko))
    for mode in ("copie", "deplacement"):
        m = resultat[mode]
        print("  %-12s %s : %d livres en %s s (%s ms par fichier, %s Mo/s)" % (
            mode, m["statut"], m["livres"], m["duree_s"], m["ms_par_fichier"], m["mo_par_s"]))
    r = resultat["relance"]
    print("  relance      : %d livres, %d ignores en %s s" % (r["livres"], r["ignores"], r["duree_s"]))
    ok = (resultat["copie"]["livres"] == args.fichiers and resultat["deplacement"]["livres"] == args.fichiers
          and resultat["relance"]["livres"] == 0 and resultat["relance"]["ignores"] == args.fichiers)
    print("  RESULTAT : %s" % ("OK" if ok else "ECHEC"))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=1)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
