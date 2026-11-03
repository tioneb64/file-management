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
