"""J3 : journal d'evenements JSON (module journal_si), au format de la plateforme d'observabilite."""
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
from tests.outils import CasTemporaire, aplatir  # noqa: E402
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
        self.j.debut("file_management", "prod", dossier=self.dossier, **kw)

    def lignes(self, motif="*.jsonl"):
        """Toutes les lignes ecrites, aplaties (voir tests.outils.aplatir ; `brut` = la ligne telle quelle)."""
        resultat = []
        for chemin in sorted(glob.glob(os.path.join(self.dossier, motif))):
            with open(chemin, "rb") as f:
                contenu = f.read()
            self.assertTrue(contenu.endswith(b"\n"), chemin)
            for ligne in contenu.decode("utf-8").split("\n")[:-1]:
                resultat.append(aplatir(json.loads(ligne)))
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
        brut = livre["brut"]
        self.assertEqual(list(brut), ["timestamp", "duration_ms", "level", "message", "trace", "service", "context"])
        self.assertEqual(brut["timestamp"], "2026-11-03T06:30:12.481Z")
        self.assertEqual((brut["level"], brut["duration_ms"]), ("INFO", 182))
        self.assertEqual(brut["service"], {"name": "file_management.export_clients", "version": "0.0.0",
                                           "environment": "prod", "instance": journal_si.nom_machine()})
        self.assertEqual((livre["regle"], livre["execution_id"], livre["evenement"]),
                         ("export_clients", 8812, "fichier_livre"))
        self.assertEqual((livre["fichier"], livre["taille"]), ("\\\\SRV\\x\\C1.xml", 15234))
        self.assertNotIn("error", brut)                               # seulement pour ERROR et CRITICAL

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
        self.j.evenement("test", event="faux", niveau_x=1, job="pirate", build_url="http://x", timestamp="libre")
        e = self.lignes()[1]
        self.assertEqual(e["brut"]["context"]["event"], "test")
        self.assertEqual(e["x_event"], "faux")
        self.assertEqual(e["x_job"], "pirate")
        self.assertEqual(e["x_build_url"], "http://x")
        self.assertEqual(e["niveau_x"], 1)
        self.assertEqual(e["timestamp"], "libre")                     # champ libre du contexte, pas la racine
        self.assertEqual(e["brut"]["timestamp"], "2026-11-03T06:30:12.481Z")

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
        self.j.evenement("b", "ERREUR")                     # vocabulaire interne : devient ERROR
        self.j.evenement("c", "BIZARRE")
        self.j.evenement("d", "DEBUG")                      # ignore : pas en mode verbeux
        self.j.evenement("e", "critical")
        self.assertEqual([l["niveau"] for l in self.lignes()][1:], ["WARNING", "ERROR", "INFO", "CRITICAL"])

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


class TestFormatPlateforme(CasJournal):
    """Conformite au format des logs de la plateforme d'observabilite (docs/02-moteur.md, section 11)."""

    def test_ordre_et_forme_des_champs(self):
        self.demarrer(version="1.4.2")
        brut = self.lignes()[0]["brut"]
        self.assertEqual(list(brut), ["timestamp", "level", "message", "trace", "service", "context"])
        self.assertRegex(brut["trace"]["trace_id"], r"^[0-9a-f]{32}$")
        self.assertRegex(brut["trace"]["span_id"], r"^[0-9a-f]{16}$")
        self.assertEqual(brut["service"]["version"], "1.4.2")
        self.assertEqual(brut["service"]["name"], "file_management")           # sans regle : le nom de l'application
        self.assertEqual(brut["message"], "debut")                              # sans catalogue : le nom de l'evenement
        self.assertEqual(brut["context"]["event"], "debut")

    def test_version_par_defaut_et_variable(self):
        self.demarrer()
        self.assertEqual(self.lignes()[0]["brut"]["service"]["version"], "0.0.0")
        os.environ["JOURNAL_SI_VERSION"] = "2.3.4"
        self.j.fermer()
        self.j = journal_si.Journal(horloge=lambda: INSTANT)
        self.addCleanup(self.j.fermer)
        self.demarrer()
        self.assertEqual(self.lignes()[-1]["brut"]["service"]["version"], "2.3.4")

    def test_nom_de_service_par_regle(self):
        self.demarrer()
        self.j.evenement("a", regle="export clients")
        e = self.lignes("export_clients_*.jsonl")[0]["brut"]
        self.assertEqual(e["service"]["name"], "file_management.export_clients")

    def test_objet_par_defaut(self):
        self.demarrer()
        self.j.evenement("a", regle="r1", fichier="\\\\SRV\\x\\C1.xml")
        self.j.evenement("b", regle="r1")
        self.j.evenement("c")
        self.j.evenement("d", regle="r1", object="dossier", object_id="D:\\a")
        os.environ.update({"JOB_NAME": "COPIE_PROD", "BUILD_NUMBER": "7"})
        self.j.evenement("e")
        par_nom = {l["evenement"]: l["brut"]["context"] for l in self.lignes() + self.lignes("r1_*.jsonl")}
        self.assertEqual((par_nom["a"]["object"], par_nom["a"]["object_id"]), ("fichier", "C1.xml"))
        self.assertEqual((par_nom["b"]["object"], par_nom["b"]["object_id"]), ("regle", "r1"))
        self.assertEqual(par_nom["c"]["object"], "lancement")
        self.assertEqual((par_nom["d"]["object"], par_nom["d"]["object_id"]), ("dossier", "D:\\a"))
        self.assertEqual(par_nom["e"]["object_id"], "COPIE_PROD-7")
        for contexte in par_nom.values():                       # object et object_id : toujours presents
            self.assertTrue(contexte["object"] and contexte["object_id"])

    def test_correlation_et_spans(self):
        os.environ.update({"JOB_NAME": "COPIE_PROD", "BUILD_NUMBER": "7"})
        self.demarrer()
        self.j.evenement("a")
        self.j.evenement("b", regle="r1", execution_id=11)
        self.j.evenement("c", regle="r1", execution_id=11)
        self.j.evenement("d", regle="r2", execution_id=12)
        lignes = {l["evenement"]: l["brut"]["trace"] for l in self.lignes() + self.lignes("r*_*.jsonl")}
        self.assertEqual(len({t["trace_id"] for t in lignes.values()}), 1)          # une seule trace
        self.assertEqual(lignes["a"]["correlation_id"], "COPIE_PROD-7")
        self.assertEqual(lignes["b"]["correlation_id"], "COPIE_PROD-7-r1")
        self.assertEqual(lignes["b"]["span_id"], lignes["c"]["span_id"])             # meme execution : meme span
        self.assertNotEqual(lignes["b"]["span_id"], lignes["d"]["span_id"])
        self.assertEqual(lignes["b"]["span_id"], journal_si.span_regle(lignes["b"]["trace_id"], 11))

    def test_trace_heritee_de_traceparent(self):
        parent = "00-" + "ab" * 16 + "-" + "cd" * 8 + "-01"
        os.environ["TRACEPARENT"] = parent
        self.demarrer()
        self.assertEqual(self.lignes()[0]["brut"]["trace"]["trace_id"], "ab" * 16)
        enfant = self.j.traceparent()
        self.assertRegex(enfant, r"^00-" + "ab" * 16 + r"-[0-9a-f]{16}-01$")
        self.assertEqual(journal_si.lire_traceparent(enfant)[0], "ab" * 16)

    def test_traceparent_invalide_ignore(self):
        for valeur in ("n'importe quoi", "00-" + "0" * 32 + "-" + "cd" * 8 + "-01", "00-" + "AB" * 16 + "-" + "cd" * 8 + "-01"):
            self.assertIsNone(journal_si.lire_traceparent(valeur), valeur)
        os.environ["TRACEPARENT"] = "n'importe quoi"
        self.demarrer()
        self.assertRegex(self.lignes()[0]["brut"]["trace"]["trace_id"], r"^[0-9a-f]{32}$")

    def test_erreur_obligatoire_pour_error_et_critical(self):
        self.demarrer()
        self.j.evenement("a", "ERREUR", message="boum")
        self.j.evenement("b", "ERROR", error_type="FILE_NOT_FOUND", exception="OSError", stacktrace="trace", message="m")
        self.j.evenement("c", "CRITICAL", message="grave")
        self.j.evenement("d", "WARNING")
        a, b, c, d = [l["brut"] for l in self.lignes()[1:]]
        self.assertEqual(a["error"], {"type": "UNKNOWN_ERROR", "message": "boum"})
        self.assertEqual(b["error"], {"type": "FILE_NOT_FOUND", "message": "m", "exception": "OSError",
                                      "stacktrace": "trace"})
        self.assertEqual((c["level"], c["error"]["type"]), ("CRITICAL", "UNKNOWN_ERROR"))
        self.assertNotIn("error", d)
        self.assertNotIn("error_type", b["context"])                  # consomme : n'apparait pas dans le contexte

    def test_catalogue(self):
        def catalogue(nom, niveau, champs):
            if nom == "a":
                return {"message": "Message du catalogue", "niveau": "CRITICAL", "error_type": "DB_CONNECTION_ERROR"}
            return {"message": "autre"}
        self.j.catalogue = catalogue
        self.demarrer()
        self.j.evenement("a", "ERREUR")
        self.j.evenement("a", "ERREUR", message="explicite")                      # l'appelant l'emporte
        self.j.evenement("b", "INFO")
        _, a1, a2, b = [l["brut"] for l in self.lignes()]
        self.assertEqual((a1["level"], a1["message"], a1["error"]["type"]), ("CRITICAL", "Message du catalogue",
                                                                              "DB_CONNECTION_ERROR"))
        self.assertEqual(a2["message"], "explicite")
        self.assertEqual(b["message"], "autre")

    def test_catalogue_defaillant_n_empeche_pas_d_ecrire(self):
        def catalogue(nom, niveau, champs):
            raise RuntimeError("explose")
        self.j.catalogue = catalogue
        self.demarrer()
        self.j.evenement("a")
        self.assertEqual((self.j.pannes(), [l["message"] for l in self.lignes()]), (0, ["debut", "a"]))

    def test_message_et_duree_remontent_a_la_racine(self):
        self.demarrer()
        self.j.evenement("a", message="Bonjour", duree_ms=42)
        brut = self.lignes()[1]["brut"]
        self.assertEqual((brut["message"], brut["duration_ms"]), ("Bonjour", 42))
        self.assertNotIn("message", brut["context"])
        self.assertNotIn("duree_ms", brut["context"])

    def test_aucune_valeur_hors_liste_pour_le_niveau(self):
        self.demarrer()
        for niveau in ("info", "ERREUR", "fatal", "TRACE", "", None):
            self.j.evenement("a", niveau)
        self.assertTrue({l["niveau"] for l in self.lignes()} <= set(journal_si.NIVEAUX))


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
        self.assertEqual(fin["brut"]["duration_ms"], 12500)
        self.assertEqual(self.j._ouverts, {})
        self.j.evenement("apres")                       # rouvre sans probleme
        self.assertEqual(len(self.lignes()), 3)

    def test_niveau_de_fin_selon_le_statut(self):
        for statut, niveau in (("OK", "INFO"), ("SUCCES", "INFO"), ("WARNING", "WARNING"),
                               ("ERREUR", "ERROR")):
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
            evenements = [json.loads(l)["context"]["event"] for l in f]
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
            journal_si.debut(application="file_management", environnement="prod",
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
                evenement = aplatir(json.loads(brut.decode("utf-8")))     # une ligne corrompue leverait ici
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
