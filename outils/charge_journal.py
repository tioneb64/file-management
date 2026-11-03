"""Test de charge du journal : N processus ecrivent dans le MEME fichier, on verifie qu'aucune
ligne n'est corrompue, perdue ou melangee. Critere de sortie du jalon J3 : 8 x 10 000 lignes.

    C:\\Python314\\python.exe outils\\charge_journal.py [--processus 8] [--lignes 10000]
        [--taille 100] [--dossier D:\\temp] [--json rapports\\charge_journal.json]

A lancer sur le serveur, de preference avec le dossier de journaux reel (meme disque, meme
antivirus). Les fichiers de test sont supprimes a la fin.
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)


def travailleur(dossier, numero, lignes, taille):
    import journal_si
    journal_si.debut("charge", "test", dossier=dossier, evenement_debut="demarre")
    message = "x" * taille
    for i in range(lignes):
        journal_si.evenement("ligne", regle="r1", processus=numero, numero=i, message=message)
    pannes = journal_si.pannes()
    journal_si.fin()
    return pannes


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--processus", type=int, default=8)
    p.add_argument("--lignes", type=int, default=10000, help="lignes par processus")
    p.add_argument("--taille", type=int, default=100, help="taille du message de chaque ligne")
    p.add_argument("--dossier", help="dossier local des fichiers temporaires")
    p.add_argument("--json", help="ecrit aussi le resultat dans ce fichier")
    p.add_argument("--travailleur", nargs=2, metavar=("DOSSIER", "NUMERO"), help=argparse.SUPPRESS)
    args = p.parse_args()

    if args.travailleur:
        sys.exit(1 if travailleur(args.travailleur[0], int(args.travailleur[1]), args.lignes,
                                  args.taille) else 0)

    dossier = tempfile.mkdtemp(prefix="charge_journal_", dir=args.dossier)
    resultat = {"serveur": platform.node(), "python": platform.python_version(),
                "processus": args.processus, "lignes_par_processus": args.lignes,
                "taille_message": args.taille}
    try:
        debut = time.time()
        fils = [subprocess.Popen([sys.executable, os.path.abspath(__file__), "--travailleur", dossier,
                                  str(n), "--lignes", str(args.lignes), "--taille", str(args.taille)])
                for n in range(args.processus)]
        codes = [f.wait() for f in fils]
        resultat["duree_s"] = round(time.time() - debut, 1)

        (nom,) = [f for f in os.listdir(dossier) if f.startswith("r1_")]
        taille_fichier = os.path.getsize(os.path.join(dossier, nom))
        valides, corrompues, vues = 0, 0, {}
        with open(os.path.join(dossier, nom), "rb") as f:
            for brut in f:
                try:
                    evenement = json.loads(brut.decode("utf-8"))
                except ValueError:
                    corrompues += 1
                    continue
                valides += 1
                if evenement.get("evenement") == "ligne":
                    vues.setdefault(evenement["processus"], []).append(evenement["numero"])
        complets = all(vues.get(n) == list(range(args.lignes)) for n in range(args.processus))
        attendu = args.processus * args.lignes       # demarre et fin vont dans le fichier sans regle
        resultat.update({"lignes_valides": valides, "lignes_corrompues": corrompues,
                         "lignes_attendues": attendu, "sequences_completes_et_ordonnees": complets,
                         "taille_fichier_mo": round(taille_fichier / 1048576, 1),
                         "lignes_par_seconde": int(valides / max(resultat["duree_s"], 0.1)),
                         "codes_retour_travailleurs": codes})
    finally:
        shutil.rmtree(dossier, ignore_errors=True)

    ok = (resultat["lignes_corrompues"] == 0 and resultat["lignes_valides"] == resultat["lignes_attendues"]
          and resultat["sequences_completes_et_ordonnees"] and not any(resultat["codes_retour_travailleurs"]))
    print("Charge du journal - %s - Python %s" % (resultat["serveur"], resultat["python"]))
    print("  %d processus x %d lignes dans un seul fichier (%s Mo) en %s s (%d lignes/s)" % (
        args.processus, args.lignes, resultat["taille_fichier_mo"], resultat["duree_s"],
        resultat["lignes_par_seconde"]))
    print("  lignes valides %d / %d attendues, corrompues %d, sequences completes et ordonnees : %s"
          % (resultat["lignes_valides"], resultat["lignes_attendues"], resultat["lignes_corrompues"],
             resultat["sequences_completes_et_ordonnees"]))
    print("  RESULTAT : %s" % ("OK" if ok else "ECHEC"))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=1)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
