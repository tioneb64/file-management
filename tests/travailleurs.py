"""Programmes lances comme processus separes par les tests de concurrence.

Lancement : python -m tests.travailleurs <travail> <arguments...> ; le resultat est un entier
ecrit sur la sortie standard. (multiprocessing n'est pas utilise : avec `python -m unittest`,
les processus fils rejouent le lanceur de tests.)
"""
import os
import subprocess
import sys

from copie import base

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def prendre(chemin, no):
    """1 si ce processus a obtenu le flag de la regle, 0 sinon."""
    with base.ouvrir(chemin) as b:
        return int(b.demarrer_execution(int(no), "planifie", os.getpid()) is not None)


def ecrire(chemin, no, debut, n):
    """Nombre d'intentions ecrites (chaque cle est distincte)."""
    debut, n = int(debut), int(n)
    with base.ouvrir(chemin) as b:
        return sum(b.noter_intention(int(no), base.cle_version("r", "f%d" % i, i, i), "s", "c")
                   for i in range(debut, debut + n))


def journaliser(dossier, numero, n, taille_message=100):
    """Ecrit n evenements numerotes dans le MEME fichier que les autres processus."""
    import journal_si
    journal_si.debut("charge", "test", dossier=dossier, evenement_debut="demarre")
    message = "x" * int(taille_message)
    for i in range(int(n)):
        journal_si.evenement("ligne", regle="r1", processus=int(numero), numero=i, message=message)
    ecrites = int(n) - journal_si.pannes()
    journal_si.fin()
    return ecrites


def lancer_en_parallele(travail, liste_arguments):
    """Demarre tous les processus ensemble, attend, renvoie la liste des entiers rendus."""
    processus = [subprocess.Popen([sys.executable, "-m", "tests.travailleurs", travail]
                                  + [str(a) for a in arguments], cwd=RACINE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for arguments in liste_arguments]
    resultats = []
    for p in processus:
        sortie, erreur = p.communicate(timeout=120)
        if p.returncode != 0:
            raise RuntimeError("travailleur en echec : %s" % erreur)
        resultats.append(int(sortie.strip()))
    return resultats


if __name__ == "__main__":
    print(globals()[sys.argv[1]](*sys.argv[2:]))
