"""J8 : controles d'acces (A01 a A07) et comparaison avec la version precedente (V01 a V04)."""
import contextlib
import io
import json
import os
import shutil
import sys
import time
import unittest
from unittest import mock

from file_management import __main__ as cli
from file_management import acces, base, chemins
from file_management.comparaison import comparer, selection_elargie
from file_management.controles import verifier_fichier
from file_management.diagnostic import Rapport
from file_management.parametrage import Selection, charger
from tests.outils import CasTemporaire


class CasAcces(CasTemporaire):
    def setUp(self):
        super().setUp()
        self.src, self.dst, self.arch = self.chemin("src"), self.chemin("dst"), self.chemin("arch")
        os.makedirs(self.src)
        self.donnees = self.chemin("donnees")
        os.makedirs(self.donnees)
        self.chemin_base = os.path.join(self.donnees, "production.db")
        self.regles = []

    def initialiser_base(self):
        base.initialiser(self.chemin_base, "production", "u")

    def regle(self, **modif):
        r = {"id": "r1", "source": self.src, "cible": self.dst, "mode": "copie",
             "planification": {"type": "quotidien", "heure": "07:00"}}
        r.update(modif)
        self.regles.append(r)
        return r

    def fichier_param(self, nom="production.jsonl"):
        entete = {"version": 1, "environnement": "production", "base": self.chemin_base,
                  "dossier_logs": os.path.join(self.donnees, "logs"),
                  "dossier_travail": os.path.join(self.donnees, "travail")}
        chemin = self.chemin(nom)
        with open(chemin, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in [entete] + self.regles) + "\n")
        return chemin

    def preparer(self):
        p, rapport = verifier_fichier(self.fichier_param())
        self.assertTrue(rapport.ok, rapport.en_texte())
        return p, rapport

    def controler(self):
        """Controles d'acces seuls, sur un parametrage valide. Renvoie le rapport."""
        p, rapport = self.preparer()
        acces.verifier_acces(p, rapport)
        return rapport

    def codes(self, rapport):
        return sorted(d.code for d in rapport.diagnostics)

    def contenu(self):
        return sorted(os.path.relpath(os.path.join(d, n), self.racine) for d, _, ns in os.walk(self.racine) for n in ns)


class TestBase(CasAcces):
    def test_base_absente(self):
        self.regle()
        r = self.controler()
        refus = [d for d in r.refus if d.code == "A05"]
        self.assertEqual(len(refus), 1)
        self.assertIn("--initialiser-base", refus[0].message)

    def test_base_utilisable(self):
        self.initialiser_base()
        self.regle()
        self.assertNotIn("A05", self.codes(self.controler()))

    def test_base_d_un_autre_environnement(self):
        base.initialiser(self.chemin_base, "recette", "u")
        self.regle()
        r = self.controler()
        self.assertIn("recette", [d for d in r.refus if d.code == "A05"][0].message)

    def test_base_sur_un_lecteur_reseau(self):
        self.initialiser_base()
        self.regle()
        if os.name != "nt":
            self.skipTest("lecteurs Windows")
        with mock.patch.object(base, "_type_lecteur", return_value=base.DRIVE_REMOTE):
            r = self.controler()
        self.assertIn("lecteur reseau", [d for d in r.refus if d.code == "A05"][0].message)

    def test_fichier_qui_n_est_pas_une_base(self):
        self.ecrire("donnees/production.db", b"ceci n'est pas une base sqlite" * 5)
        self.regle()
        self.assertIn("A05", self.codes(self.controler()))

    def test_la_verification_ne_modifie_pas_la_base(self):
        self.initialiser_base()
        self.regle()
        with base.ouvrir(self.chemin_base) as b:
            avant = b.c.execute("PRAGMA data_version").fetchone()[0], b.c.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
        self.controler()
        with base.ouvrir(self.chemin_base) as b:
            self.assertEqual((b.c.execute("SELECT COUNT(*) FROM executions").fetchone()[0],), (avant[1],))


class TestSourceCibleArchive(CasAcces):
    def setUp(self):
        super().setUp()
        self.initialiser_base()

    def test_source_absente_ou_illisible(self):
        self.regle(source=self.chemin("absente"))
        r = self.controler()
        self.assertEqual([(d.code, d.regle) for d in r.refus], [("A01", "r1")])
        with mock.patch.object(acces.os, "scandir", side_effect=PermissionError("refuse")):
            self.regles = []
            self.regle()
            r = self.controler()
        self.assertEqual([d.code for d in r.refus], ["A01"])

    def test_cible_existante_accessible(self):
        os.makedirs(self.dst)
        self.regle()
        self.assertEqual([d for d in self.controler().diagnostics if d.code in ("A02", "A03")], [])

    def test_cible_absente_sera_creee_sans_rien_creer(self):
        self.regle(cible=self.chemin("nouveau", "profond"))
        p, rapport = self.preparer()
        avant = self.contenu()
        acces.verifier_acces(p, rapport)
        self.assertTrue(rapport.ok, rapport.en_texte())
        self.assertFalse(os.path.exists(self.chemin("nouveau")))
        self.assertEqual(self.contenu(), avant)

    def test_cible_absente_sans_creation(self):
        self.regle(cible=self.chemin("nouveau"), creer_dossiers=False)
        r = self.controler()
        self.assertIn("creer_dossiers", [d for d in r.refus if d.code == "A02"][0].message)

    def test_cible_impossible_a_ecrire(self):
        self.ecrire("bloc", b"un fichier a la place du dossier")
        self.regle(cible=self.chemin("bloc", "sous"))
        self.assertEqual([d.code for d in self.controler().refus], ["A02"])

    def test_cible_en_lecture_seule(self):
        os.makedirs(self.dst)
        self.regle()
        with mock.patch("builtins.open", side_effect=PermissionError("acces refuse")) as ouvrir:
            ok, detail = acces.tester_ecriture(self.dst)
        self.assertFalse(ok)
        self.assertIn("acces refuse", detail)

    def test_dossier_temporaire(self):
        self.regle(dossier_temporaire=self.chemin("tmp"))
        self.assertTrue(self.controler().ok)
        self.regles = []
        self.regle(dossier_temporaire=self.chemin("tmp"))
        with mock.patch.object(chemins, "meme_volume", return_value=False):
            r = self.controler()
        self.assertIn("meme volume", [d for d in r.refus if d.code == "A02"][0].message)

    def test_archive_inaccessible_est_un_avertissement(self):
        self.ecrire("arch_bloquee", b"x")
        self.regle(mode="archivage", archive=self.chemin("arch_bloquee"))
        r = self.controler()
        self.assertTrue(r.ok)
        self.assertEqual([d.code for d in r.avertissements], ["A03"])
        self.assertIn("mode degrade", r.avertissements[0].message)

    def test_archive_relative_datee_dans_la_source(self):
        self.regle(mode="archivage", archive=".\\archive\\{AAAA}-{MM}-{JJ}")
        r = self.controler()
        self.assertEqual([d for d in r.diagnostics if d.code == "A03"], [])
        self.assertFalse(os.path.exists(os.path.join(self.src, "archive")))

    def test_archive_ignoree_hors_mode_archivage(self):
        self.ecrire("arch_bloquee", b"x")
        self.regle(mode="copie", archive=self.chemin("arch_bloquee"))
        self.assertEqual([d for d in self.controler().diagnostics if d.code == "A03"], [])

    def test_regle_inactive_non_controlee(self):
        self.regle(source=self.chemin("absente"), actif=False)
        self.assertEqual([d for d in self.controler().diagnostics if d.code.startswith("A0") and d.code != "A06"], [])

    def test_aucune_trace_laissee(self):
        self.regle(cible=self.chemin("nouveau"))
        self.regle(id="r2", cible=self.chemin("autre"))
        p, rapport = self.preparer()
        avant = self.contenu()
        acces.verifier_acces(p, rapport)
        self.assertEqual(self.contenu(), avant)
        self.assertEqual([n for n in os.listdir(self.racine)], sorted(os.listdir(self.racine)))   # aucun dossier cree
        self.assertFalse(os.path.exists(self.chemin("nouveau")) or os.path.exists(self.chemin("autre")))


class TestProgrammesEtDossiers(CasAcces):
    def setUp(self):
        super().setUp()
        self.initialiser_base()

    def programme(self, commande):
        return {"avant_lot": {"commande": commande, "timeout_sec": 10}}

    def test_executable_present_par_chemin_ou_par_nom(self):
        interprete = os.path.basename(sys.executable)
        self.regle(programmes=self.programme([sys.executable, "x.py"]))
        self.regle(id="r2", cible=self.chemin("d2"), programmes=self.programme(["cmd" if os.name == "nt" else "sh"]))
        self.assertEqual([d for d in self.controler().diagnostics if d.code == "A04"], [])

    def test_executable_introuvable(self):
        self.regle(programmes=self.programme([self.chemin("outils", "valider.exe")]))
        self.regle(id="r2", cible=self.chemin("d2"), programmes=self.programme(["programme_qui_n_existe_pas"]))
        r = self.controler()
        self.assertEqual([(d.code, d.regle) for d in r.refus], [("A04", "r1"), ("A04", "r2")])
        self.assertIn("avant_lot", r.refus[0].message)

    def test_executable_avec_variable_non_verifiable(self):
        self.regle(programmes=self.programme(["{source}\\valider.exe"]))
        self.assertEqual([d for d in self.controler().diagnostics if d.code == "A04"], [])

    def test_variable_d_environnement_dans_le_chemin(self):
        os.environ["COPIE_TEST_OUTILS"] = os.path.dirname(sys.executable)
        self.addCleanup(os.environ.pop, "COPIE_TEST_OUTILS", None)
        variable = "%COPIE_TEST_OUTILS%" if os.name == "nt" else "$COPIE_TEST_OUTILS"
        self.regle(programmes=self.programme([variable + os.sep + os.path.basename(sys.executable)]))
        self.assertEqual([d for d in self.controler().diagnostics if d.code == "A04"], [])

    def test_dossiers_de_journaux_et_de_travail(self):
        self.ecrire("donnees/logs", b"un fichier a la place du dossier")
        self.regle()
        r = self.controler()
        self.assertEqual([d.code for d in r.avertissements], ["A06"])
        self.assertIn("journaux", r.avertissements[0].message)
        self.assertTrue(r.ok)

    def test_espace_disponible_est_une_information(self):
        os.makedirs(self.dst)
        self.regle(mode="archivage", archive=self.arch)
        r = self.controler()
        infos = [d for d in r.diagnostics if d.code == "A07"]
        self.assertEqual(len(infos), 2)
        self.assertRegex(infos[0].message, r"\d+ Mo")
        self.assertEqual(r.informations, infos)
        self.assertEqual((r.ok, r.avertissements), (True, []))
        self.assertIn("A07 INFO", r.en_texte())

    def test_beaucoup_de_regles_sur_les_memes_dossiers(self):
        os.makedirs(self.dst)
        for i in range(1500):
            self.regle(id="r%d" % i, cible=os.path.join(self.dst, "sous_%d" % i), source=self.src)
        p, rapport = self.preparer()
        debut = time.time()
        acces.verifier_acces(p, rapport)
        self.assertLess(time.time() - debut, 8)


class TestLigneDeCommande(CasAcces):
    def lancer(self, *args):
        sortie, erreur = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
            code = cli.main(["--config", self.fichier_param()] + list(args))
        return code, sortie.getvalue(), erreur.getvalue()

    def test_verification_complete_en_json(self):
        self.initialiser_base()
        os.makedirs(self.dst)
        self.regle()
        code, sortie, _ = self.lancer("--verifier", "--format", "json")
        r = json.loads(sortie)
        self.assertEqual((code, r["ok"], r["acces"], r["code_retour"], r["refus"], r["avertissements"]),
                         (0, True, "controle", 0, [], []))
        self.assertEqual([d["code"] for d in r["informations"]], ["A07"])

    def test_code_retour_selon_la_gravite(self):
        self.initialiser_base()
        os.makedirs(self.dst)
        self.ecrire("arch_bloquee", b"x")
        self.regle(mode="archivage", archive=self.chemin("arch_bloquee"))
        self.assertEqual(self.lancer("--verifier")[0], 4)                       # A03 : avertissement
        self.regles = []
        self.regle(source=self.chemin("absente"))
        code, sortie, _ = self.lancer("--verifier", "--format", "json")
        self.assertEqual((code, json.loads(sortie)["code_retour"], json.loads(sortie)["refus"][0]["code"]), (2, 2, "A01"))

    def test_syntaxe_seule_ne_touche_pas_aux_dossiers(self):
        self.regle(source=self.chemin("absente"))
        code, sortie, _ = self.lancer("--verifier", "--syntaxe-seule", "--format", "json")
        r = json.loads(sortie)
        self.assertEqual((code, r["acces"], r["refus"]), (0, "non_controle", []))

    def test_pas_de_controle_d_acces_si_le_parametrage_est_invalide(self):
        self.regle(mode="teleportation")
        code, sortie, _ = self.lancer("--verifier", "--format", "json")
        r = json.loads(sortie)
        self.assertEqual((code, r["acces"], [d["code"] for d in r["refus"]]), (2, "non_controle", ["R06"]))
        code, texte, _ = self.lancer("--verifier")
        self.assertIn("non realises", texte)


class TestComparaison(CasTemporaire):
    def parametrage(self, nom, *regles):
        entete = {"version": 1, "environnement": "production", "base": self.chemin("donnees", "production.db")}
        chemin = self.chemin(nom, "production.jsonl")
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in [entete] + list(regles)) + "\n")
        p, rapport = charger(chemin)
        self.assertTrue(rapport.ok, rapport.en_texte())
        return p

    @staticmethod
    def regle(ident="r1", **modif):
        r = {"id": ident, "source": "D:\\src\\" + ident, "cible": "D:\\dst\\" + ident, "mode": "copie",
             "planification": {"type": "quotidien", "heure": "07:00"}}
        for cle, valeur in modif.items():
            if isinstance(valeur, dict) and isinstance(r.get(cle), dict):
                r[cle].update(valeur)
            else:
                r[cle] = valeur
        return r

    def comparer(self, avant, apres):
        rapport = Rapport()
        comparer(self.parametrage("avant", *avant), self.parametrage("apres", *apres), rapport)
        return rapport

    def test_aucun_changement(self):
        self.assertEqual(self.comparer([self.regle()], [self.regle()]).codes(), [])

    def test_v01_id_modifie(self):
        r = self.comparer([self.regle("export_clients")], [self.regle("export_clients_v2", source="D:\\src\\export_clients",
                                                                      cible="D:\\dst\\export_clients")])
        self.assertEqual([(d.code, d.regle) for d in r.refus], [("V01", "export_clients_v2")])
        self.assertIn("export_clients", r.refus[0].message)
        self.assertEqual(r.codes(), ["V01"])                      # pas aussi une suppression

    def test_v02_regle_supprimee(self):
        r = self.comparer([self.regle("a"), self.regle("b")], [self.regle("a")])
        self.assertEqual([(d.code, d.regle) for d in r.avertissements], [("V02", "b")])
        self.assertTrue(r.ok)

    def test_v02_mentionne_l_historique_si_la_base_est_fournie(self):
        from file_management.diagnostic import Rapport
        base.initialiser(self.chemin("donnees", "production.db"), "production", "u")
        with base.ouvrir(self.chemin("donnees", "production.db")) as b:
            numeros, _ = b.synchroniser_regles([("b", "e")])
            ex = b.demarrer_execution(numeros["b"], "planifie", 1)
            b.terminer_execution(ex, numeros["b"], "SUCCES")
            rapport = Rapport()
            comparer(self.parametrage("avant", self.regle("a"), self.regle("b")),
                     self.parametrage("apres", self.regle("a")), rapport, b)
        self.assertIn("restent en base", rapport.avertissements[0].message)

    def test_v03_selection_elargie(self):
        base_ = self.regle(selection={"modifie_depuis": "J-1", "masque": "*.csv"})
        cas = {"fenetre": {"modifie_depuis": "J-7"}, "tout": {"modifie_depuis": "TOUT"},
               "masque": {"masque": "*.csv;*.xml"}, "etoile": {"masque": "*"},
               "exclusion": {"exclure": ""}, "recursif": {"recursif": True},
               "taille": {"taille_minimum_octets": 0}}
        base_avec = self.regle(selection={"modifie_depuis": "J-1", "masque": "*.csv", "exclure": "~*",
                                          "taille_minimum_octets": 10})
        for nom, changement in cas.items():
            ancien = base_avec if nom in ("exclusion", "taille") else base_
            nouveau = self.regle(selection=dict(ancien["selection"], **changement))
            r = self.comparer([ancien], [nouveau])
            self.assertEqual(r.codes(), ["V03"], nom)

    def test_v03_pas_de_faux_positif_quand_la_selection_se_restreint(self):
        ancien = self.regle(selection={"modifie_depuis": "J-7", "masque": "*.csv;*.xml", "recursif": True,
                                       "taille_minimum_octets": 1})
        nouveau = self.regle(selection={"modifie_depuis": "J-1", "masque": "*.csv", "recursif": False,
                                        "exclure": "~*", "taille_minimum_octets": 100})
        self.assertEqual(self.comparer([ancien], [nouveau]).codes(), [])

    def test_selection_elargie_fonction(self):
        a, n = Selection(), Selection()
        self.assertIsNone(selection_elargie(a, n))
        a.modifie_depuis, n.modifie_depuis = "J-2", "J-3"
        self.assertIn("fenetre", selection_elargie(a, n))
        a.age_maximum_sec, n.age_maximum_sec, n.modifie_depuis = 3 * 86400, 10 * 86400, "J-2"
        a.modifie_depuis = "J-2"
        self.assertIn("fenetre", selection_elargie(a, n))

    def test_v04_cible_modifiee(self):
        r = self.comparer([self.regle()], [self.regle(cible="D:\\autre")])
        self.assertEqual([(d.code, d.regle) for d in r.avertissements], [("V04", "r1")])
        self.assertIn("deja livres ne sont pas relivres", r.avertissements[0].message)
        r = self.comparer([self.regle(cible="D:\\Dst\\R1")], [self.regle(cible="d:\\dst\\r1\\")])
        self.assertEqual(r.codes(), [])                           # meme chemin, ecrit autrement

    def test_plusieurs_changements_et_regle_ajoutee(self):
        r = self.comparer([self.regle("a"), self.regle("b")],
                          [self.regle("a", cible="D:\\x"), self.regle("c", source="D:\\autre", cible="D:\\autre2")])
        self.assertEqual(sorted(r.codes()), ["V02", "V04"])      # c est nouvelle : rien a signaler

    def test_ligne_de_commande_precedent(self):
        avant = self.parametrage("avant", self.regle("a"), self.regle("b"))
        apres_chemin = self.parametrage("apres", self.regle("a", cible="D:\\x")).chemin
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["--config", apres_chemin, "--verifier", "--syntaxe-seule", "--precedent",
                             avant.chemin, "--format", "json"])
        r = json.loads(sortie.getvalue())
        self.assertEqual((code, sorted(d["code"] for d in r["avertissements"])), (4, ["V02", "V04"]))

    def test_precedent_illisible(self):
        apres = self.parametrage("apres", self.regle("a")).chemin
        sortie, erreur = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
            code = cli.main(["--config", apres, "--verifier", "--syntaxe-seule", "--precedent",
                             self.chemin("absent.jsonl")])
        self.assertEqual(code, 2)
        self.assertIn("precedent", erreur.getvalue())

    def test_precedent_sans_verifier(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                cli.main(["--config", "x", "--precedent", "y", "--etat"])


if __name__ == "__main__":
    unittest.main()
