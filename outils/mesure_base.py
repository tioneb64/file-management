"""Mesure des performances de la base sur le serveur : recherche d'empreintes dans une grande
table, taille du fichier, cout d'une transaction durable (fsync).

    C:\\Python314\\python.exe outils\\mesure_base.py [--entrees 1000000] [--dossier D:\\temp] [--json mesure.json]

Cree une base temporaire dans le dossier indiqu\u00e9 (disque LOCAL, comme la vraie base) et la supprime.
"""
import argparse
import json
import os
import platform
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from file_management import base  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--entrees", type=int, default=1_000_000)
    p.add_argument("--recherches", type=int, default=1000)
    p.add_argument("--cycles", type=int, default=50, help="cycles intention + confirmation mesures")
    p.add_argument("--dossier", help="dossier local des fichiers temporaires")
    p.add_argument("--json", help="ecrit aussi le resultat dans ce fichier")
    args = p.parse_args()

    dossier = tempfile.mkdtemp(prefix="mesure_base_", dir=args.dossier)
    resultat = {"serveur": platform.node(), "python": platform.python_version(),
                "entrees": args.entrees}
    try:
        chemin = os.path.join(dossier, "mesure.db")
        base.initialiser(chemin, "mesure", "mesure")
        with base.ouvrir(chemin) as b:
            numeros, _ = b.synchroniser_regles([("r1", "e")])
            no = numeros["r1"]

            debut = time.time()
            b.c.execute("BEGIN")
            b.c.executemany(
                "INSERT INTO fichiers(cle, regle_no, etat, vu_jour) VALUES (?, ?, 3, 20000)",
                ((base.cle_version("r1", "dossier/fichier_%d.csv" % i, i, i * 7), no)
                 for i in range(args.entrees)))
            b.c.execute("COMMIT")
            resultat["insertion_s"] = round(time.time() - debut, 2)
            b.c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            resultat["taille_mo"] = round(os.path.getsize(chemin) / 1048576, 1)

            pas = max(1, args.entrees // args.recherches)
            cles = [base.cle_version("r1", "dossier/fichier_%d.csv" % i, i, i * 7)
                    for i in range(0, args.entrees, pas)][:args.recherches]
            absentes = [base.cle_version("r1", "inconnu_%d" % i, i, i) for i in range(len(cles))]
            debut = time.time()
            trouvees = sum(1 for c in cles if b.etat_fichier(c) is not None)
            manquees = sum(1 for c in absentes if b.etat_fichier(c) is None)
            resultat["recherche_%d_s" % len(cles)] = round(time.time() - debut, 3)
            resultat["recherches_correctes"] = trouvees == len(cles) and manquees == len(absentes)

            for mode in ("FULL", "NORMAL"):
                b.c.execute("PRAGMA synchronous = %s" % mode)
                debut = time.time()
                for i in range(args.cycles):
                    cle = base.cle_version("r1", "cycle_%s_%d" % (mode, i), i, i)
                    b.noter_intention(no, cle, "S", "C")
                    b.confirmer_livraison(cle, termine=True)
                ms = (time.time() - debut) / args.cycles * 1000
                resultat["ms_par_fichier_%s" % mode.lower()] = round(ms, 1)
    finally:
        shutil.rmtree(dossier, ignore_errors=True)

    print("Mesure de la base - %s - Python %s" % (resultat["serveur"], resultat["python"]))
    print("  %d entrees inserees en %s s ; fichier de %s Mo" % (
        args.entrees, resultat["insertion_s"], resultat["taille_mo"]))
    cle_recherche = [k for k in resultat if k.startswith("recherche_") and k.endswith("_s")][0]
    print("  %s recherches (trouvees et absentes) : %s s ; resultats corrects : %s" % (
        cle_recherche.split("_")[1], resultat[cle_recherche], resultat["recherches_correctes"]))
    print("  une livraison (2 transactions) : %s ms en synchronous=FULL, %s ms en NORMAL" % (
        resultat["ms_par_fichier_full"], resultat["ms_par_fichier_normal"]))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=1)
    return 0 if resultat["recherches_correctes"] else 1


if __name__ == "__main__":
    sys.exit(main())
