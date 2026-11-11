"""J4 : commande provisoire `python -m file_management --lancer-regle ID` de bout en bout."""
import contextlib
import glob
import io
import json
import os
import unittest

from file_management import __main__ as cli
from file_management import base
from tests.outils import CasTemporaire


class TestLancerRegle(CasTemporaire):
    def setUp(self):
        super().setUp()
        self.src, self.dst = self.chemin("src"), self.chemin("dst")
        os.makedirs(self.src)
        self.conf = self.chemin("production.jsonl")
        self.ecrire_conf()

    def ecrire_conf(self, **modif):
        entete = {"version": 1, "environnement": "production",
                  "base": self.chemin("donnees", "production.db"),
                  "dossier_logs": self.chemin("logs"), "marge_espace_mo": 0}
        regle = {"id": "export", "source": self.src, "cible": self.dst, "mode": "deplacement",
                 "planification": {"type": "quotidien", "heure": "07:00"},
                 "selection": {"age_minimum_sec": 0}}
        regle.update(modif)
        inactive = dict(regle, id="inactive", actif=False, cible=self.chemin("autre"))
        with open(self.conf, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in (entete, regle, inactive)) + "\n")

    def commande(self, *args):
        sortie, erreur = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
            code = cli.main(["--config", self.conf] + list(args))
        return code, sortie.getvalue(), erreur.getvalue()

    def initialiser(self):
        self.assertEqual(self.commande("--initialiser-base")[0], 0)

    def evenements(self):
        resultat = []
        for chemin in glob.glob(self.chemin("logs", "*.jsonl")):
            with open(chemin, encoding="utf-8") as f:
                resultat.extend(json.loads(l) for l in f)
        return resultat

    def test_livraison_de_bout_en_bout(self):
        self.initialiser()
        self.ecrire("src/a.csv", b"contenu")
        code, sortie, _ = self.commande("--lancer-regle", "export")
        self.assertEqual(code, 0, sortie)
        self.assertEqual(os.listdir(self.dst), ["a.csv"])
        self.assertEqual(os.listdir(self.src), [])
        self.assertIn("fichier_livre", sortie)                           # console lisible
        evenements = self.evenements()
        noms = [e["evenement"] for e in evenements]
        self.assertIn("debut_lancement", noms)
        self.assertIn("fin_lancement", noms)
        fin = next(e for e in evenements if e["evenement"] == "fin_lancement")
        self.assertEqual((fin["statut"], fin["code_retour"], fin["compteurs"]["livres"]), ("SUCCES", 0, 1))
        with base.ouvrir(self.chemin("donnees", "production.db"), "production") as b:
            self.assertEqual(b.regle(b.numero_regle("export"))["dernier_statut"], "SUCCES")

    def test_identifiant_sans_tenir_compte_de_la_casse(self):
        self.initialiser()
        self.assertEqual(self.commande("--lancer-regle", "EXPORT")[0], 0)

    def test_codes_retour(self):
        self.initialiser()
        # avertissement : original verrouille impossible a simuler ici ; une date future suffit
        chemin = self.ecrire("src/futur.csv", b"x")
        import time
        instant = time.time() + 7200
        os.utime(chemin, (instant, instant))
        self.assertEqual(self.commande("--lancer-regle", "export")[0], 4)
        # erreur : source absente
        os.remove(chemin)
        os.rmdir(self.src)
        code, _, _ = self.commande("--lancer-regle", "export")
        self.assertEqual(code, 1)

    def test_simulation_n_ecrit_rien(self):
        self.initialiser()
        self.ecrire("src/a.csv", b"contenu")
        code, sortie, _ = self.commande("--lancer-regle", "export", "--simulation")
        self.assertEqual(code, 0, sortie)
        self.assertFalse(os.path.exists(self.dst))
        self.assertEqual(os.listdir(self.src), ["a.csv"])
        with base.ouvrir(self.chemin("donnees", "production.db"), "production") as b:
            self.assertEqual(b.c.execute("SELECT COUNT(*) FROM executions").fetchone()[0], 0)
            self.assertEqual(b.c.execute("SELECT COUNT(*) FROM fichiers").fetchone()[0], 0)

    def test_simulation_json_detaille_les_fichiers_a_livrer(self):
        self.initialiser()
        self.ecrire("src/a.csv", b"contenu")
        self.ecrire("src/b.csv", b"xy")
        code, sortie, _ = self.commande("--lancer-regle", "export", "--simulation", "--format", "json")
        self.assertEqual(code, 0, sortie)
        r = json.loads(sortie)
        self.assertTrue(r["simulation"])
        self.assertEqual((r["source"], r["cible"], r["mode"]), (self.src, self.dst, "deplacement"))
        self.assertEqual(r["apercu_total"], 2)
        self.assertFalse(r["apercu_tronque"])
        self.assertEqual(sorted(os.path.basename(x["fichier"]) for x in r["apercu"]), ["a.csv", "b.csv"])
        self.assertEqual(sorted(x["taille"] for x in r["apercu"]), [2, 7])
        self.assertTrue(all(os.path.dirname(x["cible"]) == self.dst for x in r["apercu"]))
        self.assertFalse(os.path.exists(self.dst))

    def test_simulation_json_plafonne_le_detail(self):
        from file_management import execution
        self.initialiser()
        for i in range(5):
            self.ecrire("src/f%d.csv" % i, b"x")
        ancien, execution.APERCU_MAX = execution.APERCU_MAX, 3
        try:
            code, sortie, _ = self.commande("--lancer-regle", "export", "--simulation", "--format", "json")
        finally:
            execution.APERCU_MAX = ancien
        r = json.loads(sortie)
        self.assertEqual((r["apercu_total"], len(r["apercu"]), r["apercu_tronque"]), (5, 3, True))

    def controles(self, r):
        return {c["role"]: c for c in r["controles"]}

    def test_simulation_controle_les_dossiers_et_l_espace(self):
        self.initialiser()
        self.ecrire("src/a.csv", b"contenu")
        os.makedirs(self.dst)
        code, sortie, _ = self.commande("--lancer-regle", "export", "--simulation", "--format", "json")
        c = self.controles(json.loads(sortie))
        self.assertEqual((c["source"]["existe"], c["source"]["lecture"], c["source"]["ecriture"]), (True, True, True))
        self.assertEqual((c["cible"]["existe"], c["cible"]["lecture"], c["cible"]["ecriture"]), (True, True, True))
        self.assertTrue(c["cible"]["espace"]["suffisant"])
        self.assertEqual(c["cible"]["espace"]["necessaire_octets"], 7)       # marge_espace_mo = 0
        self.assertEqual(os.listdir(self.src), ["a.csv"])                      # l'essai d'ecriture ne laisse rien
        self.assertEqual(os.listdir(self.dst), [])

    def test_simulation_dossiers_absents_et_creation(self):
        self.initialiser()
        self.ecrire("src/a.csv", b"contenu")
        code, sortie, _ = self.commande("--lancer-regle", "export", "--simulation", "--format", "json")
        c = self.controles(json.loads(sortie))
        self.assertFalse(c["cible"]["existe"])
        self.assertTrue(c["cible"]["a_creer"])
        self.assertFalse(os.path.exists(self.dst))
        # --creer-dossiers-regle exige --utilisateur ; la source existe : seule la cible est creee
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                self.commande("--creer-dossiers-regle", "export")
        code, sortie, _ = self.commande("--creer-dossiers-regle", "export", "--utilisateur", "benoit", "--format", "json")
        self.assertEqual(code, 0, sortie)
        self.assertEqual([x["role"] for x in json.loads(sortie)["crees"]], ["cible"])
        self.assertTrue(os.path.isdir(self.dst))

    def test_source_absente_est_proposee_a_la_creation_mais_jamais_creee_au_lancement(self):
        self.initialiser()
        os.rmdir(self.src)
        code, sortie, _ = self.commande("--lancer-regle", "export", "--simulation", "--format", "json")
        c = self.controles(json.loads(sortie))
        self.assertEqual((c["source"]["existe"], c["source"]["a_creer"]), (False, True))
        self.assertIn("ne cree jamais la source seul", c["source"]["detail"])
        self.assertFalse(os.path.exists(self.src))                 # la simulation n'ecrit rien
        code, sortie, _ = self.commande("--creer-dossiers-regle", "export", "--utilisateur", "benoit", "--format", "json")
        self.assertEqual(code, 0, sortie)
        self.assertEqual(sorted(x["role"] for x in json.loads(sortie)["crees"]), ["cible", "source"])
        self.assertTrue(os.path.isdir(self.src))
        self.assertTrue(os.path.isdir(self.dst))

    def test_simulation_espace_insuffisant(self):
        from file_management import acces
        self.initialiser()
        self.ecrire("src/a.csv", b"contenu")
        os.makedirs(self.dst)
        ancien = acces.chemins.espace_disponible
        acces.chemins.espace_disponible = lambda chemin: 3
        try:
            code, sortie, _ = self.commande("--lancer-regle", "export", "--simulation", "--format", "json")
        finally:
            acces.chemins.espace_disponible = ancien
        r = json.loads(sortie)
        self.assertFalse(self.controles(r)["cible"]["espace"]["suffisant"])
        self.assertEqual(r["statut"], "ERREUR")                              # le lancement reel s'arreterait aussi

    def test_controler_regle_sans_base_ni_livraison(self):
        # aucune base initialisee : --controler-regle ne la lit pas
        self.ecrire("src/a.csv", b"contenu")
        code, sortie, _ = self.commande("--controler-regle", "export", "--format", "json")
        self.assertEqual(code, 0, sortie)
        r = json.loads(sortie)
        c = {x["role"]: x for x in r["controles"]}
        self.assertTrue(c["source"]["existe"])
        self.assertFalse(c["cible"]["existe"])
        self.assertTrue(c["cible"]["a_creer"])
        self.assertEqual(os.listdir(self.src), ["a.csv"])
        self.assertFalse(os.path.exists(self.dst))
        code, _, erreur = self.commande("--controler-regle", "inconnue")
        self.assertEqual(code, 2)
        self.assertIn("inconnue", erreur)

    def test_sans_base_rien_n_est_copie(self):
        self.ecrire("src/a.csv")
        code, _, erreur = self.commande("--lancer-regle", "export")
        self.assertEqual(code, 2)
        self.assertIn("introuvable", erreur)
        self.assertEqual(os.listdir(self.src), ["a.csv"])
        self.assertFalse(os.path.exists(self.dst))

    def test_regle_inconnue_ou_inactive(self):
        self.initialiser()
        code, _, erreur = self.commande("--lancer-regle", "fantome")
        self.assertEqual((code, "inconnue" in erreur), (2, True))
        code, _, erreur = self.commande("--lancer-regle", "inactive")
        self.assertEqual((code, "inactive" in erreur), (2, True))

    def test_regle_deja_en_cours(self):
        self.initialiser()
        with base.ouvrir(self.chemin("donnees", "production.db")) as b:
            numeros, _ = b.synchroniser_regles([("export", "e")])
            b.demarrer_execution(numeros["export"], "planifie", 1)
        code, _, erreur = self.commande("--lancer-regle", "export")
        self.assertEqual(code, 1)
        self.assertIn("deja en cours", erreur)

    def test_base_d_un_autre_environnement(self):
        base.initialiser(self.chemin("donnees", "production.db"), "recette", "u")
        code, _, erreur = self.commande("--lancer-regle", "export")
        self.assertEqual(code, 2)
        self.assertIn("recette", erreur)

    def test_parametrage_invalide(self):
        self.ecrire_conf(mode="teleportation")
        code, _, erreur = self.commande("--lancer-regle", "export")
        self.assertEqual(code, 2)
        self.assertIn("R06", erreur)

    def test_simulation_refusee_avec_une_autre_commande(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                cli.main(["--config", self.conf, "--verifier", "--simulation"])


if __name__ == "__main__":
    unittest.main()
