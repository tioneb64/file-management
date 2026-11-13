"""Boite a outils : socle commun (options, codes retour, journal, entrees, ecriture atomique, dependances)."""
import os
import unittest

from outils.commun import dependances, entrees, fichiers
from outils.commun.erreurs import (DependanceAbsente, ErreurOutil, ErreurParametres, BUSINESS_RULE_VIOLATION,
                                   FILE_NOT_FOUND, DUPLICATE_ENTITY)
from outils.commun.outil import Outil
from outils.commun.secret import lire_mot_de_passe
from outils.compression import zip_creer
from tests.boite_outils import CasOutil, TRACE


def fabriquer(**options):
    """Un petit outil de test qui traite chaque fichier designe ; le fichier 'mauvais*' est une erreur."""
    outil = Outil("outil_test", "Outil de test", "test")

    @outil.arguments
    def arguments(p):
        entrees.options_entrees(p)
        p.add_argument("--option", default="x")

    @outil.principal
    def principal(ctx, args):
        for chemin, _ in ctx.fichiers():
            with ctx.tolerer("traitement_echec", fichier=chemin):
                if os.path.basename(chemin).startswith("mauvais"):
                    raise ErreurOutil("fichier refuse", BUSINESS_RULE_VIOLATION)
                if os.path.basename(chemin).startswith("os"):
                    open(os.path.join(chemin, "inexistant"))
                if os.path.basename(chemin).startswith("bug"):
                    raise KeyError("bug")
                ctx.action("fichier_traite", "Traite : %s" % os.path.basename(chemin), fichier=chemin)
        if options.get("avertir"):
            ctx.avertir("avertissement_test", "Un avertissement")
        if options.get("dependance"):
            raise DependanceAbsente("programme truc introuvable")
        if options.get("parametres"):
            raise ErreurParametres("parametre bizarre")
        if options.get("plante"):
            raise RuntimeError("plantage")

    class Module(object):
        OUTIL = outil
    return Module


class TestCodesRetourEtJournal(CasOutil):
    def test_succes(self):
        a = self.ecrire("a.txt")
        code = self.lancer(fabriquer(), a)
        self.assertEqual(code, 0)
        self.assertIn("OK : outil_test : traites=1", self.sortie)
        lignes = self.controler_journal("outil_test", "SUCCES")
        self.assertEqual([l["context"]["event"] for l in lignes], ["outil_demarre", "fichier_traite", "outil_termine"])
        fin = lignes[-1]
        self.assertEqual(fin["context"]["compteurs"], {"traites": 1})
        self.assertEqual(fin["context"]["code_retour"], 0)
        self.assertIn("duration_ms", fin)
        self.assertEqual(lignes[1]["context"]["object"], "fichier")
        self.assertEqual(lignes[1]["context"]["object_id"], "a.txt")
        self.assertEqual(lignes[0]["message"], "Outil demarre : outil_test")

    def test_rien_a_faire_code_0_ou_1(self):
        self.assertEqual(self.lancer(fabriquer()), 0)
        self.assertIn("RIEN A FAIRE", self.sortie)
        self.controler_journal("outil_test", "RIEN")
        self.assertEqual(self.lancer(fabriquer(), "--code-si-rien", "1"), 1)
        self.assertEqual(self.lancer(fabriquer(), "--code-si-rien", "3"), 3)       # refuse : parametres invalides

    def test_une_erreur_n_arrete_pas_les_autres_elements_et_donne_le_code_2(self):
        bons = [self.ecrire("a.txt"), self.ecrire("c.txt")]
        mauvais = self.ecrire("mauvais.txt")
        code = self.lancer(fabriquer(), bons[0], mauvais, bons[1])
        self.assertEqual(code, 2)
        lignes = self.controler_journal("outil_test", "ERREUR")
        self.assertEqual(sum(1 for l in lignes if l["context"]["event"] == "fichier_traite"), 2)
        (erreur,) = self.erreurs_journal()[:1]
        self.assertEqual(erreur["error"]["type"], "BUSINESS_RULE_VIOLATION")
        self.assertEqual(erreur["context"]["fichier"], mauvais)
        self.assertEqual(lignes[-1]["context"]["compteurs"], {"traites": 2, "erreurs": 1})
        self.assertEqual(lignes[-1]["error"]["type"], "BUSINESS_RULE_VIOLATION")
        self.assertIn("ERREUR : fichier refuse", self.erreur)

    def test_arreter_si_erreur(self):
        a, c = self.ecrire("c.txt"), self.ecrire("z.txt")
        self.assertEqual(self.lancer(fabriquer(), self.ecrire("mauvais.txt"), a, c, "--arreter-si-erreur"), 2)
        self.assertEqual(self.lignes("fichier_traite"), [])

    def test_exceptions_du_systeme_et_inattendues_sont_journalisees_sans_trace_python(self):
        # le nom du fichier declenche l'exception dans l'outil de test
        fichier_os, fichier_bug = self.ecrire("os1.txt"), self.ecrire("bug1.txt")
        code = self.lancer(fabriquer(), fichier_os, fichier_bug)
        self.assertEqual(code, 2)
        types = sorted(b["error"]["type"] for b in self.erreurs_journal() if b["context"]["event"] == "traitement_echec")
        self.assertIn(types[0], ("FILE_NOT_FOUND", "FILE_IO_ERROR"))        # selon le systeme (ENOENT ou ENOTDIR)
        self.assertEqual(types[1], "INTERNAL_ERROR")
        inattendue = [b for b in self.erreurs_journal() if b["error"]["type"] == "INTERNAL_ERROR"][0]
        self.assertIn("stacktrace", inattendue["error"])
        self.assertNotIn("Traceback", self.erreur)
        self.assertNotIn("Traceback", self.sortie)

    def test_fichier_introuvable_est_une_erreur_de_l_element(self):
        code = self.lancer(fabriquer(), self.chemin("absent.txt"), self.ecrire("b.txt"))
        self.assertEqual(code, 2)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "FILE_NOT_FOUND")
        self.assertEqual(len(self.lignes("fichier_traite")), 1)

    def test_avertissement(self):
        self.assertEqual(self.lancer(fabriquer(avertir=True), self.ecrire("a.txt")), 0)
        self.assertIn("OK AVEC AVERTISSEMENT", self.sortie)
        self.controler_journal("outil_test", "WARNING")
        self.assertEqual(self.lignes("avertissement_test")[0]["niveau"], "WARNING")

    def test_dependance_absente_code_4(self):
        self.assertEqual(self.lancer(fabriquer(dependance=True), self.ecrire("a.txt")), 4)
        self.assertIn("DEPENDANCE ABSENTE : programme truc introuvable", self.erreur)
        self.assertNotIn("Traceback", self.erreur)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "EXTERNAL_SERVICE_ERROR")

    def test_parametres_invalides_en_cours_d_execution_code_3(self):
        self.assertEqual(self.lancer(fabriquer(parametres=True), self.ecrire("a.txt")), 3)

    def test_exception_non_prevue_hors_element_code_2(self):
        self.assertEqual(self.lancer(fabriquer(plante=True), self.ecrire("a.txt")), 2)
        self.assertNotIn("Traceback", self.erreur)
        erreur = self.erreurs_journal()[0]
        self.assertEqual((erreur["error"]["type"], erreur["error"]["exception"]), ("INTERNAL_ERROR", "RuntimeError"))
        self.assertIn("RuntimeError", erreur["error"]["stacktrace"])


class TestOptionsEtEnvironnement(CasOutil):
    def test_argument_inconnu_ou_manquant_code_3_sans_trace_python(self):
        for argv in (["--bidon"], ["--option"], ["--code-si-rien", "x"]):
            self.assertEqual(self.lancer(fabriquer(), *argv), 3, argv)
            self.assertIn("parametres invalides", self.erreur)
            self.assertNotIn("Traceback", self.erreur)
        self.assertEqual(self.lancer(zip_creer), 3)                       # --sortie obligatoire
        self.assertFalse(os.path.exists(self.logs))

    def test_aide_ascii_code_0(self):
        self.assertEqual(self.lancer(fabriquer(), "--aide"), 0)
        self.assertIn("--simulation", self.sortie)
        self.assertIn("--code-si-rien", self.sortie)
        self.sortie.encode("ascii")
        self.assertEqual(self.lancer(zip_creer, "-h"), 0)
        self.sortie.encode("ascii")

    def test_abreviation_refusee(self):
        self.assertEqual(self.lancer(fabriquer(), "--simul"), 3)

    def test_simulation_par_option_ou_variable(self):
        a = self.ecrire("a.txt")
        self.lancer(fabriquer(), a, "--simulation")
        self.controler_journal("outil_test", simulation=True)
        self.assertIn("(simulation)", self.sortie)
        self.nettoyer_logs()
        self.lancer(fabriquer(), a, env={"COPIE_SIMULATION": "1"})
        self.controler_journal("outil_test", simulation=True)
        self.nettoyer_logs()
        self.lancer(fabriquer(), a, env={"COPIE_SIMULATION": "0"})
        self.controler_journal("outil_test", simulation=False)

    def nettoyer_logs(self):
        for nom in os.listdir(self.logs):
            os.remove(os.path.join(self.logs, nom))

    def test_dossier_logs_regle_environnement_par_option_ou_variables(self):
        a = self.ecrire("a.txt")
        autre = self.chemin("autres_logs")
        self.lancer(fabriquer(), a, "--dossier-logs", autre, "--regle", "r_option", "--environnement", "prod",
                    env={"COPIE_ENVIRONNEMENT": "production"})
        (nom,) = os.listdir(autre)
        self.assertTrue(nom.startswith("r_option_"))
        brute = self.brutes_de(autre)[0]
        self.assertEqual((brute["service"]["name"], brute["service"]["environment"]),
                         ("file_management.r_option", "prod"))
        self.assertFalse(os.path.exists(self.logs))

    def brutes_de(self, dossier):
        import json
        with open(os.path.join(dossier, os.listdir(dossier)[0]), encoding="utf-8") as f:
            return [json.loads(l) for l in f]

    def test_code_environnement_deduit_du_nom_puis_dev(self):
        a = self.ecrire("a.txt")
        env = {"COPIE_CODE_ENVIRONNEMENT": ""}
        self.lancer(fabriquer(), a, env=dict(env, COPIE_ENVIRONNEMENT="production"))
        self.assertEqual(self.brutes()[0]["service"]["environment"], "prod")
        for nom in os.listdir(self.logs):
            os.remove(os.path.join(self.logs, nom))
        self.lancer(fabriquer(), a, env=dict(env, COPIE_ENVIRONNEMENT="inconnu"))
        self.assertEqual(self.brutes()[0]["service"]["environment"], "dev")

    def test_code_environnement_invalide_code_3(self):
        self.assertEqual(self.lancer(fabriquer(), "--environnement", "production"), 3)
        self.assertIn("hors de la liste", self.erreur)

    def test_sans_regle_le_journal_va_dans_le_fichier_du_lancement(self):
        env = {"COPIE_REGLE": ""}
        self.lancer(fabriquer(), self.ecrire("a.txt"), env=env)
        (nom,) = os.listdir(self.logs)
        self.assertTrue(nom.startswith("_orchestrateur_"))
        self.assertEqual(self.brutes()[0]["service"]["name"], "file_management")

    def test_trace_de_la_variable_traceparent_ou_nouvelle(self):
        self.lancer(fabriquer(), self.ecrire("a.txt"))
        self.assertEqual({b["trace"]["trace_id"] for b in self.brutes()}, {TRACE})
        self.assertEqual({b["trace"]["span_id"] for b in self.brutes()},
                         {__import__("journal_si").span_regle(TRACE, 42)})
        for nom in os.listdir(self.logs):
            os.remove(os.path.join(self.logs, nom))
        self.lancer(fabriquer(), self.ecrire("b.txt"), env={"TRACEPARENT": ""})
        trace = self.brutes()[0]["trace"]["trace_id"]
        self.assertRegex(trace, "^[0-9a-f]{32}$")
        self.assertNotEqual(trace, TRACE)

    def test_verbeux_ecrit_le_debug(self):
        self.lancer(fabriquer(), self.ecrire("a.txt"))
        self.assertEqual([b for b in self.brutes() if b["level"] == "DEBUG"], [])

    def test_console_reprend_le_journal_sur_la_sortie(self):
        self.lancer(fabriquer(), self.ecrire("a.txt"), "--console")
        self.assertIn("outil_demarre", self.sortie)
        self.assertIn("fichier_traite", self.sortie)


class TestEntrees(CasOutil):
    def test_arguments_jokers_dossiers_liste_masque_exclusion(self):
        self.ecrire("d/a.csv")
        self.ecrire("d/b.txt")
        self.ecrire("d/sous/c.csv")
        self.ecrire("d/x.csv.copie_en_cours")
        liste = self.ecrire("liste.txt", "\ufeff%s\r\n\r\n%s\n" % (self.chemin("d", "b.txt"), self.chemin("d", "a.csv")))

        class Contexte(object):
            def __init__(self, args):
                self.args, self.erreurs = args, []

            def designes(self):
                return entrees.designes(self.args, {})

            def echec(self, *a, **k):
                self.erreurs.append(a)

        import argparse
        def args(**kw):
            base = dict(chemins=[], liste=[], masque=[], exclure=[], recursif=False)
            base.update(kw)
            return argparse.Namespace(**base)
        noms = lambda c: [os.path.relpath(f, self.racine).replace("\\", "/") for f, _ in entrees.fichiers(c)]
        self.assertEqual(noms(Contexte(args(chemins=[self.chemin("d")]))), ["d/a.csv", "d/b.txt"])
        self.assertEqual(noms(Contexte(args(chemins=[self.chemin("d")], recursif=True))),
                         ["d/a.csv", "d/b.txt", "d/sous/c.csv"])
        self.assertEqual(noms(Contexte(args(chemins=[self.chemin("d")], recursif=True, masque=["*.CSV"]))),
                         ["d/a.csv", "d/sous/c.csv"])
        self.assertEqual(noms(Contexte(args(chemins=[self.chemin("d")], recursif=True, exclure=["sous/*", "b.*"]))),
                         ["d/a.csv"])
        self.assertEqual(noms(Contexte(args(chemins=[self.chemin("d", "*.txt")]))), ["d/b.txt"])
        self.assertEqual(noms(Contexte(args(liste=[liste]))), ["d/b.txt", "d/a.csv"])        # ordre de la liste
        contexte = Contexte(args(chemins=[self.chemin("absent")]))
        self.assertEqual(noms(contexte), [])
        self.assertEqual(contexte.erreurs[0][2], FILE_NOT_FOUND)

    def test_repli_sur_les_variables_du_moteur(self):
        self.ecrire("a.txt")
        self.ecrire("b.txt")
        liste = self.ecrire("liste.txt", "%s\n" % self.chemin("b.txt"))
        self.assertEqual(self.lancer(fabriquer(), env={"COPIE_FICHIER": self.chemin("a.txt"), "COPIE_LISTE": liste}), 0)
        self.assertEqual([os.path.basename(l["fichier"]) for l in self.lignes("fichier_traite")], ["a.txt"])
        self.lancer(fabriquer(), env={"COPIE_LISTE": liste})
        self.assertEqual([os.path.basename(l["fichier"]) for l in self.lignes("fichier_traite")], ["a.txt", "b.txt"])
        avant = len(self.lignes("fichier_traite"))
        self.lancer(fabriquer(), env={"COPIE_SOURCE": self.racine})
        self.assertEqual(len(self.lignes("fichier_traite")) - avant, 3)       # a.txt, b.txt, liste.txt (dossier non recursif)

    def test_aucun_argument_ni_variable_rien_a_faire(self):
        self.assertEqual(self.lancer(fabriquer()), 0)
        self.assertIn("RIEN A FAIRE", self.sortie)

    def test_liste_illisible_code_3(self):
        self.assertEqual(self.lancer(fabriquer(), "--liste", self.chemin("absente.txt")), 3)
        self.assertNotIn("Traceback", self.erreur)


class TestFichiers(CasOutil):
    def test_taille(self):
        self.assertEqual(fichiers.lire_taille("100M"), 100 * 1024 * 1024)
        self.assertEqual(fichiers.lire_taille("1,5 Ko"), 1536)
        self.assertEqual(fichiers.lire_taille("4096"), 4096)
        for mauvais in ("", "abc", "-5", "0", "10X"):
            with self.assertRaises(ErreurParametres):
                fichiers.lire_taille(mauvais)

    def test_ecriture_atomique(self):
        cible = self.chemin("sortie.txt")
        with fichiers.sortie_atomique(cible) as tmp:
            self.assertTrue(tmp.endswith(".copie_en_cours"))
            with open(tmp, "w") as f:
                f.write("a")
            self.assertFalse(os.path.exists(cible))
        self.assertEqual(self.lire(cible), b"a")
        self.assertEqual(os.listdir(self.racine), ["sortie.txt"])
        with self.assertRaises(ErreurOutil) as e:
            with fichiers.sortie_atomique(cible):
                pass
        self.assertEqual(e.exception.type_erreur, DUPLICATE_ENTITY)
        with self.assertRaises(RuntimeError):
            with fichiers.sortie_atomique(cible, ecraser=True) as tmp:
                with open(tmp, "w") as f:
                    f.write("b")
                raise RuntimeError("panne")
        self.assertEqual((self.lire(cible), os.listdir(self.racine)), (b"a", ["sortie.txt"]))   # rien d'abime

    def test_chemin_sous_refuse_les_chemins_dangereux(self):
        base = self.chemin("dest")
        os.makedirs(base)
        self.assertEqual(fichiers.chemin_sous(base, "a/b.txt"), os.path.join(base, "a", "b.txt"))
        self.assertEqual(fichiers.chemin_sous(base, "./a\\b.txt"), os.path.join(base, "a", "b.txt"))
        for mauvais in ("../x", "a/../../x", "/etc/passwd", "\\\\serveur\\partage\\x", "C:\\Windows\\x", "c:x"):
            with self.assertRaises(ErreurOutil, msg=mauvais) as e:
                fichiers.chemin_sous(base, mauvais)
            self.assertEqual(e.exception.type_erreur, BUSINESS_RULE_VIOLATION)

    def test_detection_d_encodage(self):
        self.assertEqual(fichiers.detecter_encodage("caf\u00e9".encode("utf-8")), ("utf-8", True))
        self.assertEqual(fichiers.detecter_encodage("caf\u00e9".encode("cp1252")), ("cp1252", False))
        self.assertEqual(fichiers.detecter_encodage(b"\xef\xbb\xbfabc"), ("utf-8-sig", True))
        self.assertEqual(fichiers.detecter_encodage("abc".encode("utf-16"))[0], "utf-16")
        self.assertEqual(fichiers.detecter_encodage(b"abc"), ("utf-8", True))
        self.assertTrue(fichiers.est_binaire(b"ab\x00cd"))
        self.assertFalse(fichiers.est_binaire("abc".encode("utf-16")))
        gros = self.ecrire("gros.txt", ("e" * 65535 + "\u00e9" * 10).encode("utf-8"))        # caractere coupe par l'echantillon
        self.assertEqual(fichiers.encodage_fichier(gros), ("utf-8", True))


class TestSecret(CasOutil):
    def args(self, **kw):
        import argparse
        base = dict(mot_de_passe_env=None, mot_de_passe_fichier=None)
        base.update(kw)
        return argparse.Namespace(**base)

    def test_sources_du_mot_de_passe(self):
        self.assertIsNone(lire_mot_de_passe(self.args(), {}))
        self.assertEqual(lire_mot_de_passe(self.args(mot_de_passe_env="MDP"), {"MDP": "s3cret"}), "s3cret")
        fichier = self.ecrire("mdp.txt", "\ufeffs3cret\r\nautre ligne\n")
        self.assertEqual(lire_mot_de_passe(self.args(mot_de_passe_fichier=fichier), {}), "s3cret")
        for mauvais in (self.args(mot_de_passe_env="MDP"), self.args(mot_de_passe_fichier=self.chemin("absent")),
                        self.args(mot_de_passe_env="MDP", mot_de_passe_fichier=fichier)):
            with self.assertRaises(ErreurParametres):
                lire_mot_de_passe(mauvais, {})
        with self.assertRaises(ErreurParametres):
            lire_mot_de_passe(self.args(), {}, obligatoire=True)


class TestDependances(CasOutil):
    def test_programme_force_par_variable_ou_absent(self):
        faux = self.faux_programme("7z", "print('x')")
        self.assertEqual(dependances.trouver_programme("7z", {"OUTIL_7Z": faux}), faux)
        with self.assertRaises(DependanceAbsente) as e:
            dependances.trouver_programme("7z", {"OUTIL_7Z": self.chemin("absent.exe")})
        self.assertIn("OUTIL_7Z", str(e.exception))
        with self.assertRaises(DependanceAbsente) as e:
            dependances.trouver_programme("rar", {"OUTIL_RAR": self.chemin("absent.exe")})
        self.assertIn("introuvable", str(e.exception).replace("n'existe pas", "introuvable"))

    def test_module_optionnel(self):
        self.assertTrue(dependances.module_disponible("json"))
        self.assertFalse(dependances.module_disponible("module_qui_n_existe_pas"))
        with self.assertRaises(DependanceAbsente) as e:
            dependances.module_optionnel("module_qui_n_existe_pas", "paquet-pip")
        self.assertIn("pip install paquet-pip", str(e.exception))

    def test_masquage_des_secrets(self):
        self.assertEqual(dependances.masquer(["7z", "-ps3cret", "a"], ["s3cret"]), "7z -p*** a")

    def test_programme_externe_lance_sans_shell_et_secret_masque(self):
        faux = self.faux_programme("echo7z", "import sys; print('mot de passe ' + sys.argv[1])")
        code, sortie = dependances.executer_externe([faux, "s3cret&calc"], secrets=["s3cret"])
        self.assertEqual(code, 0)
        self.assertIn("***", sortie)
        self.assertNotIn("s3cret", sortie)


if __name__ == "__main__":
    unittest.main()
