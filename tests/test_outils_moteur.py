"""Boite a outils appelee par de VRAIES regles du moteur (file_management v2) : contrat des codes retour, variables
COPIE_*, et journal ecrit dans le meme fichier, avec la meme trace et le meme service que la regle."""
import os
import sys
import unittest
from unittest import mock

from file_management import execution
from file_management import base as modele_base
from tests.boite_outils import chemin_outil
from tests.test_format_plateforme import anomalies
from tests.test_programmes import CasProgramme


class CasOutilsMoteur(CasProgramme):
    def setUp(self):
        super().setUp()
        self.entete.dossier_logs = self.chemin("logs")                # le moteur et les outils ecrivent au meme endroit
        self.entete.code_environnement = "prod"
        patch = mock.patch.dict(os.environ, {"TRACEPARENT": self.journal.traceparent()})
        patch.start()
        self.addCleanup(patch.stop)

    def outil(self, domaine, nom, *arguments, timeout_sec=60):
        """Le champ `programmes` d'une regle : python <outil> <arguments> (aucun shell)."""
        return {"commande": [sys.executable, chemin_outil(domaine, nom)] + list(arguments), "timeout_sec": timeout_sec}

    def lignes_outil(self, nom_outil):
        return [e for e in self.evenements() if e.get("outil") == nom_outil]

    def brutes_outil(self, nom_outil):
        import glob
        import json
        resultat = []
        for chemin in sorted(glob.glob(os.path.join(self.chemin("logs"), "*.jsonl"))):
            with open(chemin, encoding="utf-8") as f:
                resultat.extend(b for b in (json.loads(l) for l in f if l.strip()) if b["context"].get("outil") == nom_outil)
        return resultat

    def controler_lignes_de_l_outil(self, nom_outil, simulation=False):
        """Les lignes de l'outil sont dans le journal de la regle, avec sa trace, son service et son execution."""
        brutes = self.brutes_outil(nom_outil)
        self.assertGreaterEqual(len(brutes), 2, brutes)
        derniere = None if simulation else self.b.derniere_execution(self.no(self.regle()))      # simulation : base en lecture seule
        trace = self.journal.traceparent().split("-")[1]
        for b in brutes:
            self.assertEqual(anomalies(b), [], b)
            self.assertEqual(b["service"]["name"], "file_management.r1")
            self.assertEqual(b["trace"]["trace_id"], trace)
            self.assertEqual(b["context"]["regle"], "r1")
            if derniere is not None:
                self.assertEqual(b["context"]["execution_id"], derniere["id"])
            else:
                self.assertNotIn("execution_id", b["context"])
            self.assertEqual(b["service"]["environment"], "prod")
            self.assertEqual(b["context"].get("simulation"), True if simulation else None)
        self.assertEqual(brutes[0]["context"]["event"], "outil_demarre")
        self.assertEqual(brutes[-1]["context"]["event"], "outil_termine")
        return brutes


class TestOutilsAvantLot(CasOutilsMoteur):
    def test_code_0_la_regle_continue_et_l_outil_journalise_dans_le_fichier_de_la_regle(self):
        self.source("a.csv", b"id;nom\r\n1;A\r\n")
        prog = self.outil("controle", "valider_fichier", "--liste", "{liste}", "--format", "csv", "--colonnes", "id,nom")
        bilan = self.lancer(self.regle(programmes={"avant_lot": prog}))
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 1), bilan.motif)
        brutes = self.controler_lignes_de_l_outil("valider_fichier")
        self.assertEqual(brutes[-1]["context"]["statut"], "SUCCES")
        self.assertEqual(brutes[0]["context"]["point_appel"], "avant_lot")
        self.assertEqual(len(self.evenements("fichier_valide")), 1)
        regle = [f for f in os.listdir(self.chemin("logs")) if f.startswith("r1_")]
        self.assertEqual(len(regle), 1, regle)                           # les lignes de l'outil sont dans le fichier de la regle
        with open(self.chemin("logs", regle[0]), encoding="utf-8") as f:
            self.assertEqual(f.read().count('"event":"outil_demarre"'), 1)

    def test_code_1_rien_a_faire_est_une_fin_normale(self):
        self.source("a.csv")
        prog = self.outil("recherche", "chercher_nom", "--nom", "*.zzz", "--code-si-rien", "1")
        bilan = self.lancer(self.regle(programmes={"avant_lot": prog}))
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 0))
        self.assertEqual(bilan.motif, "avant_lot : rien a faire")
        self.assertEqual(self.livres(), [])
        self.assertEqual(self.controler_lignes_de_l_outil("chercher_nom")[-1]["context"]["statut"], "RIEN")

    def test_code_2_arrete_la_regle_en_erreur(self):
        self.source("a.csv", b"")                                          # un fichier vide dans la liste
        prog = self.outil("controle", "valider_fichier", "--liste", "{liste}")
        bilan = self.lancer(self.regle(programmes={"avant_lot": prog}))
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "programme_avant_lot"))
        self.assertEqual(self.livres(), [])
        self.assertIn("code retour 2", bilan.motif)
        erreurs = [b for b in self.brutes_outil("valider_fichier") if b["level"] == "ERROR"]
        self.assertEqual(erreurs[0]["error"]["type"], "BUSINESS_RULE_VIOLATION")
        self.assertEqual(self.controler_lignes_de_l_outil("valider_fichier")[-1]["context"]["statut"], "ERREUR")

    def test_code_3_parametres_invalides_arrete_la_regle(self):
        self.source("a.csv")
        bilan = self.lancer(self.regle(programmes={"avant_lot": self.outil("controle", "valider_fichier", "--format", "yaml")}))
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "programme_avant_lot"))
        self.assertIn("code retour 3", bilan.motif)

    def test_code_4_dependance_absente_arrete_la_regle_sans_trace_python(self):
        self.source("a.csv")
        archive = self.ecrire("archive.7z", b"pas une vraie archive")
        prog = self.outil("compression", "archive_extraire", archive, "--vers", self.chemin("x"))
        with mock.patch.dict(os.environ, {"OUTIL_7Z": self.chemin("inexistant", "7z.exe")}):
            bilan = self.lancer(self.regle(programmes={"avant_lot": prog}))
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "programme_avant_lot"))
        self.assertIn("code retour 4", bilan.motif)
        evenement = self.evenements_programme("avant_lot")[0]
        self.assertEqual(evenement["code"], 4)
        self.assertNotIn("Traceback", evenement["sortie"])
        self.assertIn("OUTIL_7Z", evenement["sortie"])
        self.assertEqual(self.controler_lignes_de_l_outil("archive_extraire")[-1]["context"]["statut"], "ERREUR")

    def test_les_variables_de_la_regle_suffisent_sans_argument(self):
        """Sans argument, l'outil prend la liste du lot (COPIE_LISTE) : la regle n'a pas a repeter les chemins."""
        self.source("a.csv")
        self.source("b.log")
        prog = self.outil("recherche", "chercher_nom", "--nom", "*.csv", "--sortie-liste", self.chemin("trouves.txt"))
        bilan = self.lancer(self.regle(programmes={"avant_lot": prog}))
        self.assertEqual(bilan.statut, "SUCCES")
        with open(self.chemin("trouves.txt"), encoding="utf-8") as f:
            self.assertEqual([os.path.basename(l.strip()) for l in f], ["a.csv"])

    def test_espace_disque_de_la_cible_par_la_variable_du_moteur(self):
        self.source("a.csv")
        prog = self.outil("controle", "espace_disque", "--libre-min", "1K")
        bilan = self.lancer(self.regle(programmes={"avant_lot": prog}))
        self.assertEqual(bilan.statut, "SUCCES", bilan.motif)
        self.assertEqual(len(self.lignes_outil("espace_disque")) >= 2, True)
        self.assertEqual(self.controler_lignes_de_l_outil("espace_disque")[-1]["context"]["statut"], "SUCCES")


class TestOutilsAvantFichier(CasOutilsMoteur):
    def test_code_1_ignore_le_fichier_invalide_sans_erreur(self):
        self.source("a.csv", b"id\r\n1\r\n")
        self.source("b.csv", b"")
        prog = self.outil("controle", "valider_fichier", "{fichier}", "--code-si-invalide", "1")
        bilan = self.lancer(self.regle(programmes={"avant_fichier": prog}))
        self.assertEqual((bilan.statut, bilan.compteurs["livres"], bilan.compteurs["erreurs"]), ("SUCCES", 1, 0), bilan.motif)
        self.assertEqual(self.livres(), ["a.csv"])
        avertissements = [b for b in self.brutes_outil("valider_fichier") if b["context"].get("event") == "fichier_invalide"]
        self.assertEqual(len(avertissements), 1)
        self.assertEqual(avertissements[0]["level"], "WARNING")

    def test_code_2_arrete_la_regle(self):
        self.source("a.csv", b"")
        prog = self.outil("controle", "valider_fichier", "{fichier}")
        bilan = self.lancer(self.regle(programmes={"avant_fichier": prog}))
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "programme_avant_fichier"))
        self.assertEqual(self.livres(), [])

    def test_attendre_stable_et_variable_fichier(self):
        self.source("a.csv")
        prog = self.outil("controle", "attendre_stable", "--duree-stable", "0.1", "--intervalle", "0.05", "--delai-max", "10")
        bilan = self.lancer(self.regle(programmes={"avant_fichier": prog}))      # le fichier vient de COPIE_FICHIER
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 1), bilan.motif)
        self.assertEqual(len(self.evenements("fichier_stable")), 1)


class TestOutilsApresFichier(CasOutilsMoteur):
    def test_empreinte_du_fichier_livre_puis_original_supprime(self):
        a = self.source("a.csv", b"contenu")
        prog = self.outil("controle", "empreinte", "--generer", "{fichier_cible}")
        bilan = self.lancer(self.regle(mode="deplacement", programmes={"apres_fichier": prog}))
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 1), bilan.motif)
        self.assertEqual(self.livres(), ["a.csv", "a.csv.sha256"])
        self.assertFalse(os.path.exists(a))
        with open(os.path.join(self.dst, "a.csv.sha256"), encoding="utf-8") as f:
            self.assertTrue(f.read().endswith(" *a.csv\n"))
        self.assertEqual(self.controler_lignes_de_l_outil("empreinte")[0]["context"]["point_appel"], "apres_fichier")

    def test_echec_de_la_validation_conserve_l_original(self):
        a = self.source("a.csv", b"id;nom\r\n")
        prog = self.outil("controle", "valider_fichier", "{fichier_cible}", "--format", "csv", "--lignes-min", "1")
        r = self.regle(mode="deplacement", programmes={"apres_fichier": prog})
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "programme_apres_fichier"))
        self.assertTrue(os.path.exists(a))                                      # la source n'est pas supprimee
        self.assertEqual(self.livres(), ["a.csv"])
        self.assertEqual(self.etats(), [modele_base.TERMINE])

    def test_code_1_est_accepte_a_ce_point(self):
        self.source("a.csv", b"")
        prog = self.outil("controle", "valider_fichier", "{fichier_cible}", "--code-si-invalide", "1")
        bilan = self.lancer(self.regle(programmes={"apres_fichier": prog}))
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 1), bilan.motif)


class TestOutilsApresLotEtSurErreur(CasOutilsMoteur):
    def test_apres_lot_inventaire_de_la_cible(self):
        self.source("a.csv")
        self.source("b.csv")
        prog = self.outil("fichiers", "inventaire", self.dst, "--sortie", self.chemin("inventaire.csv"))
        bilan = self.lancer(self.regle(programmes={"apres_lot": prog}))
        self.assertEqual(bilan.statut, "SUCCES", bilan.motif)
        with open(self.chemin("inventaire.csv"), encoding="utf-8-sig") as f:
            self.assertEqual(len(f.read().splitlines()), 3)                      # en-tete + 2 fichiers livres
        self.assertEqual(self.controler_lignes_de_l_outil("inventaire")[0]["context"]["point_appel"], "apres_lot")

    def test_sur_erreur_notification_par_webhook_avec_le_contexte_de_la_regle(self):
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        recus = []

        class Gestionnaire(BaseHTTPRequestHandler):
            def do_POST(self):
                recus.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass
        serveur = HTTPServer(("127.0.0.1", 0), Gestionnaire)
        fil = threading.Thread(target=serveur.serve_forever, kwargs={"poll_interval": 0.05})
        fil.start()
        self.addCleanup(fil.join)
        self.addCleanup(serveur.server_close)
        self.addCleanup(serveur.shutdown)
        self.source("a.csv")
        url = "http://127.0.0.1:%d/alerte" % serveur.server_address[1]
        r = self.regle(programmes={"avant_lot": self.outil("controle", "valider_fichier", "--format", "yaml"),
                                   "sur_erreur": self.outil("notification", "webhook", "--url", url, "--auto", "--tentatives", "1")})
        bilan = self.lancer(r)
        self.assertEqual(bilan.statut, "ERREUR")
        self.assertEqual(len(recus), 1, bilan.motif)
        self.assertEqual((recus[0]["regle"], recus[0]["statut"], recus[0]["point_appel"]), ("r1", "ERREUR", "sur_erreur"))
        self.assertEqual(recus[0]["situation"], "programme_avant_lot")
        self.controler_lignes_de_l_outil("webhook")


class TestOutilsEnSimulation(CasOutilsMoteur):
    def test_simulation_programmes_l_outil_le_sait_et_n_ecrit_rien(self):
        a = self.source("a.csv", b"contenu")
        prog = self.outil("controle", "empreinte", "--generer", "{fichier}")
        r = self.regle(programmes={"apres_fichier": prog})
        with modele_base.ouvrir(self.chemin_base, "production", lecture_seule=True) as ro:
            bilan = execution.lancer_regle(r, self.entete, ro, self.journal, simulation=True, simulation_programmes=True,
                                           maintenant=lambda: self.maintenant, dormir=self.pauses.append)
        self.assertEqual(bilan.statut, "SUCCES", bilan.motif)
        self.assertFalse(os.path.exists(a + ".sha256"))                          # COPIE_SIMULATION=1 : l'outil n'ecrit rien
        brutes = self.controler_lignes_de_l_outil("empreinte", simulation=True)
        self.assertEqual(len([b for b in brutes if b["context"].get("event") == "empreinte_a_ecrire"]), 1)


class TestLanceurAutonome(unittest.TestCase):
    """Un outil se lance aussi seul, depuis n'importe quel dossier : python outils\\...\\outil.py --aide."""

    def test_aide_depuis_un_autre_dossier_sans_importer_le_depot_courant(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as dossier:
            for domaine, nom in (("controle", "valider_fichier"), ("compression", "zip_creer"), ("fichiers", "synchroniser"),
                                 ("notification", "courriel")):
                r = subprocess.run([sys.executable, chemin_outil(domaine, nom), "--aide"], cwd=dossier, capture_output=True,
                                   timeout=60)
                self.assertEqual(r.returncode, 0, (nom, r.stderr))
                self.assertIn(b"--simulation", r.stdout)
                self.assertIn(b"Codes retour", r.stdout)
                r.stdout.decode("ascii")                                             # l'aide est en ASCII (console Windows)

    def test_code_3_sur_un_parametre_inconnu_et_aucune_trace_python(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as dossier:
            r = subprocess.run([sys.executable, chemin_outil("fichiers", "inventaire"), "--inconnu"], cwd=dossier,
                               capture_output=True, timeout=60)
            self.assertEqual(r.returncode, 3)
            self.assertNotIn(b"Traceback", r.stderr + r.stdout)


if __name__ == "__main__":
    unittest.main()
