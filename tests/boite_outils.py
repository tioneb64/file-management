"""Aides communes aux tests de la boite a outils (outils/) : lancement en processus, lecture du journal,
controle du format de la plateforme, faux programmes externes."""
import contextlib
import io
import json
import os
import stat
import sys
import textwrap

from tests.outils import CasTemporaire, lire_journaux
from tests.test_format_plateforme import anomalies

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACE = "ab" * 16
SPAN_PARENT = "cd" * 8


def chemin_outil(domaine, nom):
    return os.path.join(RACINE, "outils", domaine, nom + ".py")


class CasOutil(CasTemporaire):
    """Un dossier de journaux et l'environnement d'une regle fictive ; `lancer` execute un outil dans le
    processus de test et renvoie son code retour."""

    def setUp(self):
        super().setUp()
        self.logs = self.chemin("logs")
        self.env = {"COPIE_DOSSIER_LOGS": self.logs, "COPIE_REGLE": "regle_test", "COPIE_EXECUTION_ID": "42",
                    "COPIE_CODE_ENVIRONNEMENT": "test", "COPIE_POINT_APPEL": "avant_lot",
                    "TRACEPARENT": "00-%s-%s-01" % (TRACE, SPAN_PARENT)}
        self.sortie = self.erreur = ""

    def lancer(self, outil, *argv, env=None):
        """`outil` : le module de l'outil (il expose OUTIL). Renvoie le code retour ; sortie standard et
        sortie d'erreur sont dans self.sortie et self.erreur."""
        flux_sortie, flux_erreur = io.StringIO(), io.StringIO()
        environnement = dict(self.env)
        environnement.update(env or {})
        with contextlib.redirect_stdout(flux_sortie), contextlib.redirect_stderr(flux_erreur):
            code = outil.OUTIL.executer([str(a) for a in argv], environnement)
        self.sortie, self.erreur = flux_sortie.getvalue(), flux_erreur.getvalue()
        return code

    # ----- journal ----- #
    def brutes(self):
        resultat = []
        if os.path.isdir(self.logs):
            for nom in sorted(os.listdir(self.logs)):
                with open(os.path.join(self.logs, nom), encoding="utf-8") as f:
                    resultat.extend(json.loads(l) for l in f if l.strip())
        return resultat

    def lignes(self, evenement=None, niveau=None):
        """Lignes du journal (aplaties, voir tests.outils.aplatir)."""
        return [l for l in lire_journaux(self.logs) if (evenement is None or l["evenement"] == evenement)
                and (niveau is None or l["niveau"] == niveau)]

    def controler_journal(self, nom_outil, statut=None, simulation=False, regle="regle_test"):
        """Le journal de l'outil : format de la plateforme, meme fichier et meme service que la regle, meme
        trace, execution_id, outil, point d'appel, debut et fin."""
        fichiers = [f for f in os.listdir(self.logs)]
        self.assertEqual(len(fichiers), 1, fichiers)
        self.assertTrue(fichiers[0].startswith(regle + "_") and fichiers[0].endswith(".jsonl"), fichiers)
        brutes = self.brutes()
        for b in brutes:
            self.assertEqual(anomalies(b), [], b)
            self.assertEqual(b["service"]["name"], "file_management." + regle)
            self.assertEqual(b["trace"]["trace_id"], TRACE)
            self.assertEqual(b["context"]["outil"], nom_outil)
            self.assertEqual(b["context"]["execution_id"], 42)
            self.assertEqual(b["context"]["point_appel"], "avant_lot")
            self.assertEqual(b["service"]["environment"], "test")
            self.assertEqual(b["context"].get("simulation"), True if simulation else None, b)
        self.assertEqual(brutes[0]["context"]["event"], "outil_demarre")
        self.assertEqual(brutes[-1]["context"]["event"], "outil_termine")
        if statut:
            self.assertEqual(brutes[-1]["context"]["statut"], statut)
        return brutes

    def texte_journal(self):
        """Tout le texte des fichiers du journal (pour verifier qu'un secret n'y figure pas)."""
        texte = []
        for nom in sorted(os.listdir(self.logs)):
            with open(os.path.join(self.logs, nom), encoding="utf-8") as f:
                texte.append(f.read())
        return "".join(texte)

    def erreurs_journal(self):
        return [b for b in self.brutes() if b["level"] in ("ERROR", "CRITICAL")]

    # ----- fichiers ----- #
    def arbre(self, racine=None):
        """Chemins relatifs ('/') de tous les fichiers sous `racine`, tries."""
        racine = racine or self.racine
        trouves = []
        for dossier, _, noms in os.walk(racine):
            trouves.extend(os.path.relpath(os.path.join(dossier, n), racine).replace("\\", "/") for n in noms)
        return sorted(trouves)

    def faux_programme(self, nom, corps_python):
        """Cree un faux executable (.cmd sous Windows, script sinon) qui lance `corps_python` avec ses
        arguments dans sys.argv ; renvoie son chemin."""
        dossier = self.chemin("faux")
        os.makedirs(dossier, exist_ok=True)
        script = os.path.join(dossier, nom + ".py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(corps_python))
        if os.name == "nt":
            chemin = os.path.join(dossier, nom + ".cmd")
            with open(chemin, "w", encoding="ascii") as f:
                f.write('@"%s" "%s" %%*\r\n' % (sys.executable, script))
        else:
            chemin = os.path.join(dossier, nom)
            with open(chemin, "w", encoding="ascii") as f:
                f.write('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, script))
            os.chmod(chemin, os.stat(chemin).st_mode | stat.S_IEXEC)
        return chemin
