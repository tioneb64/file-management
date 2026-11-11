"""J3 : journal d'evenements JSON (module journal_si)."""
import contextlib
import glob
import io
import json
import os
import re
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import journal_si  # noqa: E402
from tests.outils import CasTemporaire  # noqa: E402
from tests.travailleurs import lancer_en_parallele  # noqa: E402

# 2026-11-03 06:30:12.481 UTC
INSTANT = 1793687412.481


class CasJournal(CasTemporaire):
    def setUp(self):
        super().setUp()
        self.dossier = self.chemin("logs")
        self.j = journal_si.Journal(horloge=lambda: INSTANT)
        self.addCleanup(self.j.fermer)
        env = {k: v for k, v in os.environ.items()
               if k not in ("JOB_NAME", "BUILD_NUMBER", "BUILD_URL", "NODE_NAME")}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def demarrer(self, **kw):
        self.j.debut("file_management", "production", dossier=self.dossier, **kw)

    def lignes(self, motif="*.jsonl"):
        """Toutes les lignes ecrites, en objets (chaque ligne doit etre un JSON valide)."""
        resultat = []
        for chemin in sorted(glob.glob(os.path.join(self.dossier, motif))):
            with open(chemin, "rb") as f:
                contenu = f.read()
            self.assertTrue(contenu.endswith(b"\n"), chemin)
            for ligne in contenu.decode("utf-8").split("\n")[:-1]:
                resultat.append(json.loads(ligne))
        return resultat

    def fichiers(self):
        return sorted(os.listdir(self.dossier)) if os.path.isdir(self.dossier) else []


class TestFormat(CasJournal):
    def test_champs_de_base(self):
        self.demarrer()
        self.j.evenement("fichier_livre", regle="export_clients", execution_id=8812,
                         fichier="\\\\SRV\\x\\C1.xml", taille=15234, duree_ms=182)
        debut, livre = self.lignes()
        self.assertEqual(debut["evenement"], "debut")
        self.assertEqual(list(livre)[:6], ["horodatage", "niveau", "application", "environnement",
                                           "regle", "execution_id"])
        self.assertEqual(livre["horodatage"], "2026-11-03T06:30:12.481Z")
        self.assertEqual((livre["niveau"], livre["application"], livre["environnement"],
                          livre["regle"], livre["execution_id"], livre["evenement"]),
                         ("INFO", "file_management", "production", "export_clients", 8812,
                          "fichier_livre"))
        self.assertEqual((livre["fichier"], livre["taille"], livre["duree_ms"]),
                         ("\\\\SRV\\x\\C1.xml", 15234, 182))

    def test_horodatage_en_utc_au_format_iso(self):
        self.demarrer()
        self.assertRegex(self.lignes()[0]["horodatage"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")

    def test_variables_jenkins_ajoutees_si_presentes(self):
        os.environ.update({"JOB_NAME": "COPIE_PROD", "BUILD_NUMBER": "1542",
                           "BUILD_URL": "https://jenkins/job/COPIE_PROD/1542/",
                           "NODE_NAME": "SRV-JENKINS01"})
        self.demarrer()
        e = self.lignes()[0]
        self.assertEqual((e["job"], e["build"], e["build_url"], e["noeud"]),
                         ("COPIE_PROD", "1542", "https://jenkins/job/COPIE_PROD/1542/", "SRV-JENKINS01"))

    def test_pas_de_champ_jenkins_hors_jenkins(self):
        self.demarrer()
        e = self.lignes()[0]
        for champ in ("job", "build", "build_url", "noeud", "regle"):
            self.assertNotIn(champ, e)

    def test_accents_et_unicode_ecrits_en_utf8(self):
        self.demarrer()
        self.j.evenement("note", message="Livraison é à ü — 日本語 😀")
        with open(glob.glob(os.path.join(self.dossier, "*.jsonl"))[0], "rb") as f:
            brut = f.read()
        self.assertIn("é à ü — 日本語 😀".encode("utf-8"), brut)         # pas d'echappement \u00e9
        self.assertEqual(self.lignes()[1]["message"], "Livraison é à ü — 日本語 😀")

    def test_retour_a_la_ligne_dans_un_message_reste_sur_une_ligne(self):
        self.demarrer()
        self.j.evenement("sortie", message="ligne 1\nligne 2\r\nligne 3")
        self.assertEqual(len(self.lignes()), 2)
        self.assertEqual(self.lignes()[1]["message"], "ligne 1\nligne 2\r\nligne 3")

    def test_champs_reserves_non_ecrasables(self):
        self.demarrer()
        self.j.evenement("test", horodatage="faux", niveau_x=1, application="autre", job="pirate")
        e = self.lignes()[1]
        self.assertEqual(e["application"], "file_management")
        self.assertEqual(e["x_horodatage"], "faux")
        self.assertEqual(e["x_application"], "autre")
        self.assertEqual(e["x_job"], "pirate")
        self.assertEqual(e["niveau_x"], 1)

    def test_valeurs_non_serialisables(self):
        self.demarrer()
        self.j.evenement("test", chemin=Path("D:/a/b"), octets="é".encode("utf-8"),
                         ensemble={3}, quand=datetime(2026, 1, 2), nul=None, vrai=True)
        e = self.lignes()[1]
        self.assertEqual(e["octets"], "é")
        self.assertEqual(e["ensemble"], [3])
        self.assertEqual((e["nul"], e["vrai"]), (None, True))
        self.assertIn("2026-01-02", e["quand"])
        self.assertIn("b", e["chemin"])

    def test_nom_windows_avec_caractere_isole(self):
        self.demarrer()
        self.j.evenement("fichier_livre", fichier="bizarre\udcff.txt")
        self.assertEqual(self.j.pannes(), 0)
        self.assertEqual(len(self.lignes()), 2)

    def test_texte_trop_long_tronque(self):
        self.demarrer()
        self.j.evenement("sortie", message="x" * 100_000)
        message = self.lignes()[1]["message"]
        self.assertLess(len(message), 8300)
        self.assertIn("tronque, 100000", message)

    def test_niveaux(self):
        self.demarrer()
        self.j.evenement("a", "warning")
        self.j.evenement("b", "ERREUR")
        self.j.evenement("c", "BIZARRE")
        self.j.evenement("d", "DEBUG")                      # ignore : pas en mode verbeux
        self.assertEqual([l["niveau"] for l in self.lignes()][1:], ["WARNING", "ERREUR", "INFO"])

    def test_mode_verbeux_garde_debug(self):
        self.demarrer(verbeux=True)
        self.j.evenement("d", "DEBUG")
        self.assertEqual(self.lignes()[1]["niveau"], "DEBUG")

    def test_contexte_defini_une_fois(self):
        self.demarrer()
        self.j.definir(regle="export_clients", execution_id=7)
        self.j.evenement("a")
        self.j.evenement("b", regle="autre")
        a, b = self.lignes("export_clients_*.jsonl"), self.lignes("autre_*.jsonl")
        self.assertEqual((a[0]["execution_id"], a[0]["regle"]), (7, "export_clients"))
        self.assertEqual(b[0]["regle"], "autre")

    def test_contexte_passe_a_debut(self):
        self.demarrer(lancement=12)
        self.assertEqual(self.lignes()[0]["lancement"], 12)


class TestFichiers(CasJournal):
    def test_un_fichier_par_regle_et_par_jour(self):
        self.demarrer()
        self.j.evenement("a", regle="export_clients")
        self.j.evenement("b", regle="export_clients")
        self.j.evenement("c", regle="import_catalogue")
        jour = datetime.fromtimestamp(INSTANT).strftime("%Y-%m-%d")
        self.assertEqual(self.fichiers(), ["_orchestrateur_%s.jsonl" % jour,
                                           "export_clients_%s.jsonl" % jour,
                                           "import_catalogue_%s.jsonl" % jour])
        self.assertEqual(len(self.lignes("export_clients_*.jsonl")), 2)

    def test_changement_de_jour(self):
        instant = [INSTANT]
        self.j.horloge = lambda: instant[0]
        self.demarrer()
        self.j.evenement("a", regle="r1")
        instant[0] += 86400
        self.j.evenement("b", regle="r1")
        self.assertEqual(len([f for f in self.fichiers() if f.startswith("r1_")]), 2)

    def test_nom_de_regle_assaini(self):
        self.demarrer()
        self.j.evenement("a", regle="..\\..\\evil/x:y")
        self.assertTrue(all(os.path.dirname(os.path.join(self.dossier, f)) == self.dossier
                            for f in self.fichiers()))
        self.assertEqual(len(self.fichiers()), 2)       # orchestrateur + regle assainie
        self.assertEqual(os.listdir(self.racine), ["logs"])

    def test_dossier_cree_s_il_manque(self):
        self.dossier = self.chemin("a", "b", "c")
        self.demarrer()
        self.assertEqual(len(self.lignes()), 1)

    def test_dossier_par_defaut_depuis_l_environnement(self):
        os.environ["JOURNAL_SI_DOSSIER"] = self.dossier
        self.j.debut("app", "test")
        self.assertEqual(len(self.lignes()), 1)

    def test_fin_ecrit_bilan_et_ferme(self):
        instant = [INSTANT]
        self.j.horloge = lambda: instant[0]
        self.demarrer(evenement_fin="fin_lancement", evenement_debut="debut_lancement")
        instant[0] += 12.5
        self.j.fin(statut="WARNING", compteurs={"livres": 4, "erreurs": 0}, code_retour=4)
        debut, fin = self.lignes()
        self.assertEqual((debut["evenement"], fin["evenement"]), ("debut_lancement", "fin_lancement"))
        self.assertEqual((fin["niveau"], fin["statut"], fin["compteurs"], fin["duree_ms"],
                          fin["code_retour"]), ("WARNING", "WARNING", {"livres": 4, "erreurs": 0},
                                                12500, 4))
        self.assertEqual(self.j._ouverts, {})
        self.j.evenement("apres")                       # rouvre sans probleme
        self.assertEqual(len(self.lignes()), 3)

    def test_niveau_de_fin_selon_le_statut(self):
        for statut, niveau in (("OK", "INFO"), ("SUCCES", "INFO"), ("WARNING", "WARNING"),
                               ("ERREUR", "ERREUR")):
            self.dossier = self.chemin("logs_" + statut)
            self.j = journal_si.Journal(horloge=lambda: INSTANT)
            self.demarrer()
            self.j.fin(statut=statut)
            self.assertEqual(self.lignes()[-1]["niveau"], niveau, statut)

    def test_lisible_pendant_que_le_fichier_est_ouvert(self):
        self.demarrer()
        self.j.evenement("a")
        with open(glob.glob(os.path.join(self.dossier, "*.jsonl"))[0], "rb") as f:   # comme Alloy
            self.assertEqual(len(f.read().splitlines()), 2)
        self.j.evenement("b")
        self.assertEqual(len(self.lignes()), 3)

    def test_fichier_supprime_par_la_purge_pendant_l_execution(self):
        """Une purge qui supprime le fichier d'un autre jour ne gene pas l'ecriture du jour."""
        self.demarrer()
        self.j.evenement("a", regle="r1")
        ancien = os.path.join(self.dossier, "r1_2020-01-01.jsonl")
        with open(ancien, "w") as f:
            f.write("{}\n")
        os.remove(ancien)
        self.j.evenement("b", regle="r1")
        self.assertEqual(len(self.lignes("r1_*.jsonl")), 2)


class TestPannes(CasJournal):
    def avec_stderr(self):
        erreur = io.StringIO()
        return erreur, contextlib.redirect_stderr(erreur)

    def test_dossier_impossible_ne_leve_rien_et_replie(self):
        self.ecrire("fichier_bloquant", b"x")
        self.dossier = self.chemin("fichier_bloquant")          # un fichier a la place du dossier
        secours = self.chemin("secours")
        os.makedirs(secours)
        erreur, redirection = self.avec_stderr()
        with redirection:
            self.demarrer(dossier_secours=secours)
            self.j.evenement("fichier_livre", regle="r1", fichier="a.csv")
        self.assertEqual(self.j.pannes(), 2)
        self.assertIn("journal_si", erreur.getvalue())
        self.assertIn("fichier_livre", erreur.getvalue())
        (nom,) = os.listdir(secours)
        with open(os.path.join(secours, nom), encoding="utf-8") as f:
            evenements = [json.loads(l)["evenement"] for l in f]
        self.assertEqual(evenements, ["debut", "fichier_livre"])

    def test_secours_lui_meme_impossible(self):
        self.ecrire("bloc", b"x")
        self.dossier = self.chemin("bloc")
        erreur, redirection = self.avec_stderr()
        with redirection:
            self.demarrer(dossier_secours=self.chemin("bloc", "inexistant"))
            self.j.evenement("a")
        self.assertEqual(self.j.pannes(), 2)                     # aucune exception

    def test_stderr_ferme(self):
        self.ecrire("bloc", b"x")
        self.dossier = self.chemin("bloc")
        ferme = io.StringIO()
        ferme.close()
        with mock.patch.object(sys, "stderr", ferme):
            self.demarrer(dossier_secours=self.racine)
            self.j.evenement("a")
        self.assertEqual(self.j.pannes(), 2)

    def test_reprise_automatique_quand_le_dossier_revient(self):
        self.ecrire("bloc", b"x")
        self.dossier = self.chemin("bloc")
        _, redirection = self.avec_stderr()
        with redirection:
            self.demarrer(dossier_secours=self.racine)
        os.remove(self.chemin("bloc"))                           # le dossier devient possible
        self.j.evenement("retour")
        self.assertEqual(self.j.pannes(), 1)
        self.assertEqual([l["evenement"] for l in self.lignes()], ["retour"])

    def test_evenement_sans_debut_ne_leve_rien(self):
        journal = journal_si.Journal()
        _, redirection = self.avec_stderr()
        with redirection:
            journal.evenement("a")                              # dossier non defini
            journal.fin()
        self.assertGreaterEqual(journal.pannes(), 0)

    def test_erreur_interne_de_serialisation(self):
        class Piege(object):
            def __str__(self):
                raise RuntimeError("explose")
        self.demarrer()
        _, redirection = self.avec_stderr()
        with redirection:
            self.j.evenement("a", objet=Piege())
        self.assertEqual(self.j.pannes(), 1)
        self.j.evenement("b")
        self.assertEqual([l["evenement"] for l in self.lignes()], ["debut", "b"])


class TestConsole(CasJournal):
    def test_ligne_lisible_sur_la_sortie_standard(self):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            self.demarrer(console=True)
            self.j.evenement("fichier_livre", "WARNING", regle="r1", message="presque")
        texte = sortie.getvalue()
        self.assertIn("WARNING", texte)
        self.assertIn("fichier_livre", texte)
        self.assertIn("regle=r1", texte)
        self.assertIn("message=presque", texte)

    def test_silencieuse_par_defaut(self):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            self.demarrer()
            self.j.evenement("a")
        self.assertEqual(sortie.getvalue(), "")


class TestInterfaceDeModule(CasJournal):
    def test_trois_fonctions_du_module(self):
        journal_si._journal.fermer()
        with mock.patch.object(journal_si, "_journal", journal_si.Journal(horloge=lambda: INSTANT)):
            journal_si.debut(application="file_management", environnement="production",
                             dossier=self.dossier)
            journal_si.definir(regle="r1")
            journal_si.evenement("fichier_livre", fichier="a.csv")
            journal_si.fin(statut="OK", compteurs={"livres": 1})
            self.assertEqual(journal_si.pannes(), 0)
        evenements = [l["evenement"] for l in self.lignes()]
        self.assertEqual(sorted(evenements), ["debut", "fichier_livre", "fin"])


class TestCharge(CasTemporaire):
    def controler(self, dossier, processus, par_processus, taille=100):
        (nom,) = [f for f in os.listdir(dossier) if f.startswith("r1_")]
        vues = {}
        with open(os.path.join(dossier, nom), "rb") as f:
            for brut in f:
                evenement = json.loads(brut.decode("utf-8"))          # une ligne corrompue leverait ici
                if evenement["evenement"] == "ligne":
                    self.assertEqual(len(evenement["message"]), taille)
                    vues.setdefault(evenement["processus"], []).append(evenement["numero"])
        self.assertEqual(sorted(vues), list(range(processus)))
        for numeros in vues.values():
            self.assertEqual(numeros, list(range(par_processus)))     # complet et dans l'ordre

    def test_huit_processus_dans_le_meme_fichier(self):
        dossier = self.chemin("logs")
        ecrites = lancer_en_parallele("journaliser", [(dossier, p, 1000) for p in range(8)])
        self.assertEqual(ecrites, [1000] * 8)
        self.controler(dossier, 8, 1000)

    def test_lignes_longues_toujours_atomiques(self):
        dossier = self.chemin("logs")
        ecrites = lancer_en_parallele("journaliser", [(dossier, p, 300, 3500) for p in range(6)])
        self.assertEqual(ecrites, [300] * 6)
        self.controler(dossier, 6, 300, taille=3500)


if __name__ == "__main__":
    unittest.main()
