"""J8 : deblocage et contrat JSON entre le moteur et le front-end (docs/07-contrat-moteur-frontend.md)."""
import contextlib
import io
import json
import os
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

import journal_si
from copie import __main__ as cli
from copie import base as modele_base
from copie import lancement, orchestrateur, processus
from copie.execution import nom_hote
from tests.test_orchestrateur import ATTENTE_LONGUE, SEPT_HEURES, CasProcessus

CLES_COMMUNES = {"version_contrat", "ok", "code_retour", "message"}
CLES_REGLE_ETAT = {"id", "description", "actif", "mode", "planification", "en_cours", "statut", "attente",
                   "motif", "dernier_lancement", "dernier_creneau", "prochain_creneau", "dernier_succes",
                   "derniere_erreur", "derniere_execution", "reprise", "lancement_manuel",
                   "arret_apres_erreur", "archivage_degrade", "actions_en_attente", "livraisons_incertaines"}
CLES_COMPTEURS_LANCEMENT = {"regles", "lancees", "SUCCES", "WARNING", "ERREUR", "non_dues", "non_lancees",
                            "orphelines", "nettoyees", "en_attente", "bloquees", "depassees"}


class CasDeblocage(CasProcessus):
    def processus_long(self, avec_petit_fils=False):
        if avec_petit_fils:
            self.marque = self.chemin("petit_fils.pid")
            code = ("import subprocess, sys, time\n"
                    "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
                    "open(%r, 'w').write(str(p.pid))\n"
                    "time.sleep(300)\n" % self.marque)
        else:
            code = "import time; time.sleep(300)"
        p = subprocess.Popen([sys.executable, "-c", code])
        self.addCleanup(lambda: p.poll() is None and p.kill())
        return p

    def installer(self, pid=None, cree_le=True, hote=None, avec_petit_fils=False, **modif):
        self.brute(id="r1", planification=SEPT_HEURES, **modif)
        p = self.declencher()
        long_ = None if pid is not None else self.processus_long(avec_petit_fils)
        pid = pid if pid is not None else long_.pid
        no = self.b.numero_regle("r1")
        self.b.demarrer_execution(no, "planifie", pid, processus.date_creation(pid) if cree_le is True else cree_le,
                                  hote=hote or nom_hote())
        return p, long_

    def debloquer(self, p, **kw):
        return lancement.debloquer(p, self.b, self.journal, "r1", "benoit", "bloquee depuis une heure", **kw)


class TestDebloquer(CasDeblocage):
    def test_arrete_le_processus_et_libere_la_regle(self):
        p, long_ = self.installer()
        r = self.debloquer(p)
        long_.wait(timeout=10)
        self.assertTrue(r["processus_arrete"] and r["drapeau_libere"] and r["reprise_necessaire"])
        self.assertEqual(set(r), {"regle", "execution_id", "pid", "processus_arrete", "drapeau_libere",
                                  "reprise_necessaire", "message"})
        etat = self.regle_base("r1")
        self.assertEqual((etat["en_cours"], etat["dernier_statut"], etat["derniere_erreur_situation"],
                          etat["arret_apres_erreur"]), (0, "ERREUR", "deblocage", 1))
        ex = self.b.derniere_execution(self.b.numero_regle("r1"))
        self.assertEqual((ex["statut"], ex["fin"] is not None), ("ARRETEE", True))
        trace = self.b.c.execute("SELECT utilisateur, commentaire, resultat FROM journal_actions WHERE action = 'deblocage'").fetchone()
        self.assertEqual(tuple(trace), ("benoit", "bloquee depuis une heure", "processus arrete"))
        evenement = self.evenements("deblocage")[0]
        self.assertEqual((evenement["utilisateur"], evenement["processus_arrete"]), ("benoit", True))
        self.assertIn("une reprise est necessaire", r["message"])

    def test_arrete_aussi_les_descendants(self):
        p, long_ = self.installer(avec_petit_fils=True)
        for _ in range(100):
            if os.path.exists(self.marque) and open(self.marque).read():
                break
            time.sleep(0.1)
        petit = int(open(self.marque).read())
        self.debloquer(p)
        long_.wait(timeout=10)
        time.sleep(0.5)
        self.assertIsNone(processus.date_creation(petit))

    def test_apres_erreur_continuer_ne_demande_pas_de_reprise(self):
        p, long_ = self.installer(apres_erreur="continuer")
        r = self.debloquer(p)
        self.assertFalse(r["reprise_necessaire"])
        self.assertEqual(self.regle_base("r1")["arret_apres_erreur"], 0)
        self.assertNotIn("reprise", r["message"])

    def test_processus_deja_disparu(self):
        mort = subprocess.Popen([sys.executable, "-c", "pass"])
        mort.wait()
        p, _ = self.installer(pid=mort.pid)
        r = self.debloquer(p)
        self.assertEqual((r["processus_arrete"], r["drapeau_libere"]), (False, True))
        self.assertIn("n'existait plus", r["message"])
        self.assertEqual(self.regle_base("r1")["en_cours"], 0)

    def test_identifiant_reutilise_le_processus_n_est_pas_touche(self):
        autre = self.processus_long()
        p, _ = self.installer(pid=autre.pid, cree_le=12345.0)       # date de creation differente : autre programme
        r = self.debloquer(p)
        self.assertIsNone(autre.poll())
        self.assertFalse(r["processus_arrete"])
        self.assertEqual(self.regle_base("r1")["en_cours"], 0)

    def test_refuse_si_la_regle_n_est_pas_en_cours(self):
        self.brute(id="r1", planification=SEPT_HEURES)
        p = self.declencher()
        with self.assertRaises(modele_base.ActionRefusee) as cm:
            self.debloquer(p)
        self.assertIn("n'est pas en cours", str(cm.exception))

    def test_refuse_pour_une_regle_inconnue(self):
        self.brute(id="r1", planification=SEPT_HEURES)
        p = self.declencher()
        with self.assertRaises(modele_base.ActionRefusee):
            lancement.debloquer(p, self.b, self.journal, "fantome", "benoit")

    def test_refuse_si_l_execution_tourne_sur_un_autre_serveur(self):
        p, long_ = self.installer(hote="UN-AUTRE-SERVEUR")
        with self.assertRaises(modele_base.ActionRefusee) as cm:
            self.debloquer(p)
        self.assertIn("UN-AUTRE-SERVEUR", str(cm.exception))
        self.assertIsNone(long_.poll())
        self.assertEqual(self.regle_base("r1")["en_cours"], 1)

    def test_ne_s_arrete_jamais_lui_meme(self):
        p, _ = self.installer(pid=os.getpid())
        with self.assertRaises(modele_base.ActionRefusee) as cm:
            self.debloquer(p)
        self.assertIn("processus courant", str(cm.exception))
        self.assertEqual(self.regle_base("r1")["en_cours"], 1)

    def test_processus_qui_ne_s_arrete_pas_le_drapeau_reste_pose(self):
        p, long_ = self.installer()
        with mock.patch.object(processus, "tuer_arbre", return_value=False):
            with self.assertRaises(modele_base.ActionRefusee) as cm:
                self.debloquer(p, attente_sec=0.3)
        self.assertIn("ne s'arrete pas", str(cm.exception))
        self.assertEqual(self.regle_base("r1")["en_cours"], 1)
        self.assertEqual(self.b.c.execute("SELECT COUNT(*) FROM journal_actions WHERE action = 'deblocage'").fetchone()[0], 0)

    def test_une_reprise_est_ensuite_necessaire(self):
        p, long_ = self.installer()
        self.debloquer(p)
        long_.wait(timeout=10)
        etat = self.regle_base("r1")
        from copie import planification
        decision = planification.evaluer(p.regles[0], etat, time.time())
        self.assertFalse(decision.due)
        self.b.poser_reprise("r1", "benoit", "relance apres deblocage")
        decision = planification.evaluer(p.regles[0], self.regle_base("r1"), time.time())
        self.assertEqual((decision.due, decision.declencheur), (True, "reprise"))

    def test_debloquer_une_execution_suivie_par_un_orchestrateur(self):
        """Un lancement en cours, rule bloquee : --debloquer l'arrete ; l'orchestrateur journalise la fin."""
        self.brute(id="r1", planification=SEPT_HEURES, situations=ATTENTE_LONGUE, duree_max_sec=3600)
        p = self.declencher("r1")
        resultat = {}

        def lancer():
            b = modele_base.ouvrir(self.chemin_base, "production")
            journal = journal_si.Journal()
            journal.debut("copie_fichiers", "production", dossier=self.chemin("logs"))
            try:
                resultat["lancement"] = lancement.lancer(p, b, journal)
            finally:
                b.fermer()
        fil = threading.Thread(target=lancer)
        fil.start()
        try:
            for _ in range(200):
                etat = self.regle_base("r1")
                if etat["en_cours"] and etat["pid"] and etat["pid"] != os.getpid():
                    break
                time.sleep(0.1)
            else:
                self.fail("la regle n'a jamais demarre")
            time.sleep(1.0)                           # laisser le fils atteindre sa boucle d'attente
            r = self.debloquer(p)
            self.assertTrue(r["processus_arrete"])
        finally:
            fil.join(timeout=60)
        self.assertFalse(fil.is_alive())
        etat = self.regle_base("r1")
        self.assertEqual((etat["en_cours"], etat["dernier_statut"]), (0, "ERREUR"))
        fins = self.evenements("regle_terminee")
        self.assertEqual([(e["regle"], e["statut"]) for e in fins], [("r1", "ERREUR")])
        self.assertEqual(resultat["lancement"].code_retour, 1)


class TestContratJson(CasProcessus):
    """Chaque commande, avec --format json, ecrit UN objet JSON sur la sortie standard et rien d'autre."""

    def setUp(self):
        super().setUp()
        self.b.fermer()
        os.remove(self.chemin_base)
        for suffixe in ("-wal", "-shm"):
            if os.path.exists(self.chemin_base + suffixe):
                os.remove(self.chemin_base + suffixe)
        self.brute(id="export", planification=SEPT_HEURES, description="Export des factures é à ü",
                   selection={"age_minimum_sec": 0})
        self.brute(id="inactive", actif=False, cible=self.chemin("autre"))
        self.conf = self.chemin("production.jsonl")
        self.parametrage()
        self.b = None
        self.addCleanup(lambda: None)

    def tearDown(self):
        super().tearDown()

    def commande(self, *args):
        sortie, erreur = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
            code = cli.main(["--config", self.conf, "--format", "json"] + list(args))
        return code, sortie.getvalue(), erreur.getvalue()

    def json(self, *args, attendu=0):
        code, sortie, erreur = self.commande(*args)
        self.assertEqual(code, attendu, sortie + erreur)
        self.assertEqual(erreur, "", "rien sur la sortie d'erreur en mode JSON")
        resultat = json.loads(sortie)                          # leve si autre chose que UN objet JSON
        self.assertIsInstance(resultat, dict)
        self.assertEqual(resultat["version_contrat"], 1)
        self.assertEqual(resultat["code_retour"], code)
        return resultat

    def initialiser(self):
        self.json("--initialiser-base")

    def test_initialiser_et_sauvegarder(self):
        r = self.json("--initialiser-base")
        self.assertEqual(set(r), CLES_COMMUNES | {"base", "environnement"})
        self.assertTrue(r["ok"])
        r = self.json("--sauvegarder-base", self.chemin("sauvegardes"))
        self.assertEqual(set(r), CLES_COMMUNES | {"fichier"})
        self.assertTrue(os.path.isfile(r["fichier"]))

    def test_etat(self):
        self.initialiser()
        self.json("--lancer-maintenant", "export", "--utilisateur", "benoit")
        r = self.json("--etat")
        self.assertEqual(set(r), {"version_contrat", "ok", "code_retour", "environnement", "genere_le", "regles",
                                  "orphelines"})
        self.assertEqual((r["ok"], r["environnement"], r["orphelines"]), (True, "production", []))
        regle = {x["id"]: x for x in r["regles"]}["export"]
        self.assertEqual(set(regle), CLES_REGLE_ETAT)
        self.assertEqual((regle["statut"], regle["lancement_manuel"], regle["description"]),
                         ("JAMAIS_LANCEE", True, "Export des factures é à ü"))
        self.assertEqual({x["id"]: x["statut"] for x in r["regles"]}["inactive"], "INACTIVE")
        self.assertIsInstance(regle["prochain_creneau"], int)
        self.assertEqual(self.json("--etat", "--regle", "export")["regles"][0]["id"], "export")

    def test_etat_apres_une_execution_en_erreur(self):
        self.initialiser()
        os.rmdir(self.src)
        self.json("--lancer-maintenant", "export", "--utilisateur", "benoit")
        code, sortie, _ = self.commande()
        self.assertEqual(code, 1)
        regle = self.json("--etat")["regles"][0]
        self.assertEqual(regle["statut"], "ERREUR")
        self.assertEqual(set(regle["derniere_erreur"]), {"le", "situation", "message"})
        self.assertEqual(set(regle["derniere_execution"]), {"statut", "nb_livres", "nb_erreurs", "declencheur", "duree_sec"})
        self.assertEqual(regle["derniere_erreur"]["situation"], "source_inaccessible")

    def test_commandes_d_exploitation(self):
        self.initialiser()
        r = self.json("--lancer-maintenant", "export", "--utilisateur", "benoit")
        self.assertEqual(set(r), CLES_COMMUNES | {"commande", "regle"})
        self.assertEqual((r["commande"], r["regle"]), ("lancer_maintenant", "export"))
        r = self.json("--reprise", "export", "--utilisateur", "benoit", "--commentaire", "rien")
        self.assertEqual((r["commande"], r["ok"]), ("reprise", True))

    def test_acquittement_et_deblocage_en_json(self):
        self.initialiser()
        with modele_base.ouvrir(self.chemin_base) as b:
            numeros, _ = b.synchroniser_regles([("export", "e")])
            ex = b.demarrer_execution(numeros["export"], "planifie", 1)
            b.terminer_execution(ex, numeros["export"], "ERREUR", motif="panne")
        r = self.json("--acquitter", "export", "--utilisateur", "benoit", "--commentaire", "traite a la main")
        self.assertEqual((r["commande"], r["ok"]), ("acquitter", True))
        mort = subprocess.Popen([sys.executable, "-c", "pass"])
        mort.wait()
        with modele_base.ouvrir(self.chemin_base) as b:
            b.demarrer_execution(b.numero_regle("export"), "planifie", mort.pid, hote=nom_hote())
        r = self.json("--debloquer", "export", "--utilisateur", "benoit")
        self.assertEqual(set(r), CLES_COMMUNES | {"commande", "regle", "execution_id", "pid", "processus_arrete",
                                                  "drapeau_libere", "reprise_necessaire"})
        self.assertEqual((r["commande"], r["processus_arrete"], r["drapeau_libere"]), ("debloquer", False, True))

    def test_refus_toujours_en_json_sur_la_sortie_standard(self):
        self.initialiser()
        r = self.json("--reprise", "fantome", "--utilisateur", "benoit", attendu=2)
        self.assertEqual((r["ok"], r["code_retour"]), (False, 2))
        self.assertIn("inconnue", r["message"])
        r = self.json("--acquitter", "export", "--utilisateur", "benoit", "--commentaire", "x", attendu=2)
        self.assertFalse(r["ok"])
        r = self.json("--debloquer", "export", "--utilisateur", "benoit", attendu=2)
        self.assertIn("n'est pas en cours", r["message"])

    def test_base_absente(self):
        for commande in (["--etat"], ["--lancer-maintenant", "export", "--utilisateur", "b"], []):
            r = self.json(*commande, attendu=2)
            self.assertEqual(r["ok"], False)
            self.assertIn("introuvable", r["message"])

    def test_parametrage_invalide(self):
        with open(self.conf, "w", encoding="utf-8") as f:
            f.write('{"version": 1, "environnement": "production"}\n')
        code, sortie, erreur = self.commande("--etat")
        r = json.loads(sortie)
        self.assertEqual((code, erreur, r["ok"], r["code_retour"]), (2, "", False, 2))
        self.assertEqual(r["refus"][0]["code"], "E04")
        self.assertIn("invalide", r["message"])

    def test_verifier(self):
        self.initialiser()
        os.makedirs(self.dst, exist_ok=True)
        r = self.json("--verifier")
        self.assertEqual(set(r), {"version_contrat", "ok", "refus", "avertissements", "informations",
                                  "regles_lues", "acces", "code_retour"})
        for d in r["refus"] + r["avertissements"] + r["informations"]:
            self.assertTrue({"code", "regle", "message"} <= set(d) <= {"code", "regle", "message", "ligne"})

    def test_lancement_et_simulation(self):
        self.initialiser()
        self.json("--lancer-maintenant", "export", "--utilisateur", "benoit")
        fichier = self.source_reelle("a.csv")
        r = self.json()                                        # vrais processus fils : aucune pollution de la sortie
        self.assertEqual(set(r), CLES_COMMUNES | {"statut", "compteurs", "simulation"})
        self.assertEqual(set(r["compteurs"]), CLES_COMPTEURS_LANCEMENT)
        self.assertEqual((r["statut"], r["compteurs"]["livres"] if "livres" in r["compteurs"] else None,
                          r["compteurs"]["SUCCES"], r["simulation"]), ("SUCCES", None, 1, False))
        self.assertEqual(os.listdir(self.dst), ["a.csv"])
        self.source_reelle("b.csv")
        r = self.json("--simulation")
        self.assertTrue(r["simulation"])
        self.assertEqual(os.listdir(self.dst), ["a.csv"])

    def test_lancer_regle_en_json(self):
        self.initialiser()
        self.source_reelle("a.csv")
        r = self.json("--lancer-regle", "export")
        self.assertEqual(set(r), CLES_COMMUNES | {"regle", "statut", "compteurs", "simulation"})
        self.assertEqual((r["regle"], r["statut"], r["compteurs"]["livres"]), ("export", "SUCCES", 1))

    def test_erreurs_d_arguments_ne_sont_pas_du_json(self):
        sortie, erreur = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
            with self.assertRaises(SystemExit) as cm:
                cli.main(["--config", self.conf, "--format", "json", "--reprise", "export"])
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(sortie.getvalue(), "")
        self.assertIn("--utilisateur", erreur.getvalue())

    def test_la_variable_de_console_est_restauree(self):
        self.initialiser()
        self.assertNotIn("COPIE_SANS_CONSOLE", os.environ)
        self.json("--etat")
        self.assertNotIn("COPIE_SANS_CONSOLE", os.environ)

    def test_processus_reel_utf8_sans_bom_et_stderr_vide(self):
        """Comme le front-end PowerShell : un vrai processus, la sortie decodee en UTF-8 strict."""
        env = dict(os.environ, PYTHONPATH=orchestrateur.RACINE)
        base_commande = [sys.executable, "-m", "copie", "--config", self.conf, "--format", "json"]
        resultat = subprocess.run(base_commande + ["--initialiser-base"], cwd=orchestrateur.RACINE, env=env,
                                  capture_output=True)
        self.assertEqual((resultat.returncode, resultat.stderr), (0, b""))
        resultat = subprocess.run(base_commande + ["--etat"], cwd=orchestrateur.RACINE, env=env, capture_output=True)
        self.assertEqual((resultat.returncode, resultat.stderr), (0, b""))
        self.assertFalse(resultat.stdout.startswith(b"\xef\xbb\xbf"))
        texte = resultat.stdout.decode("utf-8")                # strict
        self.assertIn("Export des factures é à ü", texte)      # accents ecrits tels quels, sans é
        self.assertEqual(json.loads(texte)["regles"][0]["id"], "export")


if __name__ == "__main__":
    unittest.main()
