"""Lecture des journaux d'une regle pour le front-end : `--journaux-regle ID [--journal NOM] [--limite-evenements N]`."""
import contextlib
import io
import json
import os
import unittest

from file_management import __main__ as cli
from file_management import journaux
from tests.outils import CasTemporaire


def ligne(evenement, heure, niveau="INFO", message=None, execution_id=None, duree=None, erreur=None, **champs):
    contexte = {"object": "regle", "object_id": "export", "event": evenement, "regle": "export"}
    if execution_id is not None:
        contexte["execution_id"] = execution_id
    contexte.update(champs)
    x = {"timestamp": heure, "level": niveau, "message": message or evenement, "context": contexte}
    if duree is not None:
        x["duration_ms"] = duree
    if erreur:
        x["error"] = erreur
    return json.dumps(x, ensure_ascii=False)


class TestJournauxRegle(CasTemporaire):
    def setUp(self):
        super().setUp()
        self.src, self.dst = self.chemin("src"), self.chemin("dst")
        os.makedirs(self.src)
        self.logs = self.chemin("logs")
        os.makedirs(self.logs)
        self.conf = self.chemin("production.jsonl")
        entete = {"version": 1, "environnement": "production", "base": self.chemin("donnees", "production.db"),
                  "dossier_logs": self.logs, "marge_espace_mo": 0}
        regle = {"id": "export", "source": self.src, "cible": self.dst, "mode": "deplacement",
                 "planification": {"type": "quotidien", "heure": "07:00"}, "selection": {"age_minimum_sec": 0}}
        with open(self.conf, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in (entete, regle)) + "\n")

    def commande(self, *args):
        sortie, erreur = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
            code = cli.main(["--config", self.conf] + list(args))
        return code, sortie.getvalue(), erreur.getvalue()

    def journal(self, nom, lignes):
        with open(os.path.join(self.logs, nom), "w", encoding="utf-8") as f:
            f.write("\n".join(lignes) + "\n")

    def preparer(self):
        self.journal("export_2026-11-10.jsonl", [
            ligne("regle_demarree", "2026-11-10T08:00:00.000Z", execution_id=1, declencheur="planifie"),
            ligne("regle_terminee", "2026-11-10T08:00:05.000Z", message="Regle terminee : SUCCES", execution_id=1,
                  duree=5000, statut="SUCCES", motif="1 fichier(s) livre(s)", compteurs={"livres": 1})])
        self.journal("export_2026-11-11.jsonl", [
            ligne("regle_demarree", "2026-11-11T08:00:00.000Z", execution_id=2, declencheur="planifie"),
            ligne("tentative_echouee", "2026-11-11T08:00:01.000Z", niveau="WARNING", message="verrouille", execution_id=2,
                  situation="fichier_verrouille", fichier="a.csv"),
            ligne("fichier_erreur", "2026-11-11T08:00:02.000Z", niveau="ERROR", message="Erreur sur le fichier a.csv",
                  execution_id=2, fichier="a.csv", erreur={"type": "FILE_IO_ERROR", "message": "x"}),
            "ceci n'est pas du json",
            ligne("regle_terminee", "2026-11-11T08:00:03.000Z", message="Regle terminee : ERREUR", execution_id=2,
                  duree=3000, statut="ERREUR", motif="1 erreur", compteurs={"erreurs": 1})])
        # ancien format a plat, et simulation (sans execution_id)
        self.journal("export_2026-11-12.jsonl", [
            json.dumps({"horodatage": "2026-11-12T09:00:00.000Z", "niveau": "INFO", "application": "file_management",
                        "environnement": "production", "evenement": "fichier_livre", "regle": "export",
                        "fichier": "D:\\src\\b.csv", "taille": 12, "execution_id": 3}),
            ligne("regle_demarree", "2026-11-12T10:00:00.000Z", declencheur="manuel", simulation=True),
            ligne("selection", "2026-11-12T10:00:01.000Z", candidats=2, simulation=True),
            ligne("regle_terminee", "2026-11-12T10:00:02.000Z", statut="SUCCES", motif="2 a livrer", simulation=True),
            ligne("debut_lancement", "2026-11-12T11:00:00.000Z")])
        self.journal("export_autre_2026-11-12.jsonl", [ligne("regle_demarree", "2026-11-12T10:00:00.000Z")])
        self.journal("_orchestrateur_2026-11-12.jsonl", [ligne("debut_lancement", "2026-11-12T10:00:00.000Z")])

    def reponse(self, *args):
        code, sortie, erreur = self.commande(*(args + ("--format", "json")))
        return code, (json.loads(sortie) if sortie.strip() else None), erreur

    def test_liste_des_journaux_du_plus_recent_au_plus_ancien(self):
        self.preparer()
        code, r, _ = self.reponse("--journaux-regle", "export")
        self.assertEqual(code, 0)
        self.assertEqual([j["jour"] for j in r["journaux"]], ["2026-11-12", "2026-11-11", "2026-11-10"])
        j12, j11, j10 = r["journaux"]
        self.assertEqual((j10["statut"], j10["avertissements"], j10["erreurs"], j10["executions"]), ("SUCCES", 0, 0, 1))
        self.assertEqual((j11["statut"], j11["avertissements"], j11["erreurs"], j11["illisibles"]), ("ERREUR", 1, 1, 1))
        self.assertEqual((j12["statut"], j12["motif"]), ("SUCCES", "2 a livrer"))        # la simulation compte
        self.assertFalse(r["tronque"])
        self.assertEqual(r["dossier"], self.logs)

    def test_sans_journal_liste_vide(self):
        code, r, _ = self.reponse("--journaux-regle", "export")
        self.assertEqual((code, r["journaux"]), (0, []))
        os.rmdir(self.logs)
        code, r, _ = self.reponse("--journaux-regle", "export")
        self.assertEqual((code, r["journaux"]), (0, []))

    def test_contenu_decompose_d_un_journal(self):
        self.preparer()
        code, r, _ = self.reponse("--journaux-regle", "export", "--journal", "export_2026-11-11.jsonl")
        self.assertEqual(code, 0)
        self.assertEqual([e["evenement"] for e in r["evenements"]],
                         ["regle_demarree", "tentative_echouee", "fichier_erreur", "regle_terminee"])
        self.assertEqual([e["numero"] for e in r["evenements"]], [1, 2, 3, 4])
        avert = r["evenements"][1]
        self.assertEqual((avert["niveau"], avert["groupe"], avert["execution_id"]), ("WARNING", "2", 2))
        self.assertIn({"cle": "situation", "valeur": "fichier_verrouille"}, avert["champs"])
        self.assertNotIn("regle", [c["cle"] for c in avert["champs"]])                    # deja dans les colonnes
        self.assertEqual(r["evenements"][2]["erreur"]["type"], "FILE_IO_ERROR")
        self.assertEqual(r["illisibles"], 1)
        x = r["executions"][0]
        self.assertEqual((x["cle"], x["statut"], x["declencheur"], x["avertissements"], x["erreurs"], x["duree_ms"]),
                         ("2", "ERREUR", "planifie", 1, 1, 3000))
        self.assertEqual(x["compteurs"], {"erreurs": 1})

    def test_ancien_format_simulation_et_evenements_hors_execution(self):
        self.preparer()
        code, r, _ = self.reponse("--journaux-regle", "export", "--journal", "export_2026-11-12.jsonl")
        self.assertEqual(code, 0)
        ancien = r["evenements"][0]
        self.assertEqual((ancien["evenement"], ancien["message"], ancien["execution_id"]), ("fichier_livre", "Fichier livre : b.csv", 3))
        self.assertIn({"cle": "taille", "valeur": 12}, ancien["champs"])
        self.assertEqual([x["cle"] for x in r["executions"]], ["3", "s1"])
        simulation = r["executions"][1]
        self.assertTrue(simulation["simulation"])
        self.assertEqual((simulation["declencheur"], simulation["statut"]), ("manuel", "SUCCES"))
        self.assertEqual([e["groupe"] for e in r["evenements"]], ["3", "s1", "s1", "s1", None])

    def test_limite_garde_les_derniers_evenements(self):
        self.preparer()
        code, r, _ = self.reponse("--journaux-regle", "export", "--journal", "export_2026-11-11.jsonl",
                                  "--limite-evenements", "2")
        self.assertEqual((code, r["total"], r["tronque"]), (0, 4, True))
        self.assertEqual([e["numero"] for e in r["evenements"]], [3, 4])

    def test_budget_de_taille_garde_les_derniers_evenements(self):
        self.preparer()
        ancien = journaux.BUDGET_CARACTERES
        journaux.BUDGET_CARACTERES = 1300
        try:
            _, r, _ = self.reponse("--journaux-regle", "export", "--journal", "export_2026-11-11.jsonl")
        finally:
            journaux.BUDGET_CARACTERES = ancien
        self.assertTrue(r["tronque"])
        self.assertEqual(r["total"], 4)
        self.assertLess(len(r["evenements"]), 4)
        self.assertEqual(r["evenements"][-1]["numero"], 4)                        # on garde la fin du fichier
        self.assertEqual(r["executions"][0]["statut"], "ERREUR")                  # le resume des executions reste complet

    def test_refus_regle_inconnue_chemin_ou_journal_d_une_autre_regle(self):
        self.preparer()
        code, _, erreur = self.commande("--journaux-regle", "inconnue")
        self.assertEqual((code, "inconnue" in erreur), (2, True))
        for nom in ("export_autre_2026-11-12.jsonl", "_orchestrateur_2026-11-12.jsonl", "export_2026-01-01.jsonl",
                    os.path.join("..", "production.jsonl"), os.path.join(self.logs, "export_2026-11-10.jsonl")):
            code, _, erreur = self.commande("--journaux-regle", "export", "--journal", nom)
            self.assertEqual((code, "journal inconnu" in erreur), (2, True), nom)

    def test_options_mal_associees(self):
        for args in (["--journal", "x.jsonl"], ["--limite-evenements", "3"], ["--journaux-regle", "export", "--limite-evenements", "3"],
                     ["--journaux-regle", "export", "--journal", "export_2026-11-10.jsonl", "--limite-evenements", "0"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
                cli.main(["--config", self.conf] + args)
            self.assertEqual(cm.exception.code, 2, args)

    def test_journaux_ecrits_par_le_moteur(self):
        self.assertEqual(self.commande("--initialiser-base")[0], 0)
        self.ecrire("src/a.csv", b"contenu")
        self.assertEqual(self.commande("--lancer-regle", "export")[0], 0)
        _, r, _ = self.reponse("--journaux-regle", "export")
        self.assertEqual(len(r["journaux"]), 1)
        self.assertEqual(r["journaux"][0]["statut"], "SUCCES")
        _, d, _ = self.reponse("--journaux-regle", "export", "--journal", r["journaux"][0]["nom"])
        noms = [e["evenement"] for e in d["evenements"]]
        self.assertIn("fichier_livre", noms)
        livre = next(e for e in d["evenements"] if e["evenement"] == "fichier_livre")
        self.assertEqual(livre["message"], "Fichier livre : a.csv")
        self.assertRegex(livre["heure"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        self.assertEqual(d["executions"][-1]["statut"], "SUCCES")

    def test_normaliser_ignore_ce_qui_n_est_pas_un_evenement(self):
        self.assertIsNone(journaux.normaliser([1, 2]))
        self.assertIsNone(journaux.normaliser({"autre": 1}))


if __name__ == "__main__":
    unittest.main()
