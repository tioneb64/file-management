"""J9 : integration Jenkins. journal_si en ligne de commande (evenements de niveau job), coherence des
Jenkinsfile et de la bibliotheque partagee, lancements simultanes, abandon d'un build.

La bibliotheque Groovy n'est PAS executee ici (aucun Jenkins ni Groovy sur le poste) : ses
controles statiques et le format des evenements qu'elle fait ecrire sont testes ; son execution
reelle est dans le cahier de tests (J9-M).
"""
import glob
import io
import json
import os
import re
import shlex
import subprocess
import sys
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

import journal_si
from copie import __main__ as cli
from copie import lancement, orchestrateur, processus
from tests.outils import CasTemporaire
from tests.test_orchestrateur import ATTENTE_LONGUE, SEPT_HEURES, CasProcessus

RACINE = orchestrateur.RACINE
JENKINS = os.path.join(RACINE, "jenkins")
ENV_JENKINS = {"JOB_NAME": "COPIE_PROD", "BUILD_NUMBER": "1542", "BUILD_URL": "https://jenkins.exemple/job/COPIE_PROD/1542/",
               "NODE_NAME": "SRV-JENKINS01"}


def evenements_de(dossier):
    resultat = []
    for chemin in sorted(glob.glob(os.path.join(dossier, "*.jsonl"))):
        with open(chemin, encoding="utf-8") as f:
            resultat.extend(json.loads(l) for l in f)
    return resultat


# =========================================================================== #
class TestJournalEnLigneDeCommande(CasTemporaire):
    def setUp(self):
        super().setUp()
        self.logs = self.chemin("logs")

    def ecrire(self, *args, env=None, entree=None):
        sortie, erreur = io.StringIO(), io.StringIO()
        environnement = {k: v for k, v in os.environ.items() if k not in ENV_JENKINS}
        environnement.update(env or {})
        from unittest import mock
        with mock.patch.dict(os.environ, environnement, clear=True), redirect_stdout(sortie), redirect_stderr(erreur):
            code = journal_si.main(["--dossier", self.logs, "--application", "file_management",
                                    "--environnement", "production"] + list(args))
        return code, sortie.getvalue(), erreur.getvalue()

    def test_evenement_au_meme_format_que_le_module(self):
        self.ecrire("--evenement", "debut_job", "--champ", "message=bonjour", env=ENV_JENKINS)
        (e,) = evenements_de(self.logs)
        j = journal_si.Journal()
        j.configurer("file_management", "production", self.chemin("autre"))
        from unittest import mock
        with mock.patch.dict(os.environ, ENV_JENKINS):
            j.evenement("debut_job", message="bonjour")
        (reference,) = evenements_de(self.chemin("autre"))
        self.assertEqual(list(e), list(reference))                     # memes champs, dans le meme ordre
        self.assertEqual({k: v for k, v in e.items() if k != "horodatage"},
                         {k: v for k, v in reference.items() if k != "horodatage"})
        self.assertEqual((e["job"], e["build"], e["build_url"], e["noeud"]),
                         ("COPIE_PROD", "1542", "https://jenkins.exemple/job/COPIE_PROD/1542/", "SRV-JENKINS01"))

    def test_fichier_sans_regle(self):
        self.ecrire("--evenement", "debut_job")
        self.assertEqual([os.path.basename(f).rsplit("_", 1)[0] for f in glob.glob(os.path.join(self.logs, "*"))],
                         ["_orchestrateur"])

    def test_regle_et_fichier_de_la_regle(self):
        self.ecrire("--evenement", "note", "--regle", "export_clients")
        self.assertTrue(glob.glob(os.path.join(self.logs, "export_clients_*.jsonl")))
        self.assertEqual(evenements_de(self.logs)[0]["regle"], "export_clients")

    def test_champs_json_types_accents_et_bom(self):
        chemin = self.chemin("champs.json")
        with open(chemin, "w", encoding="utf-8-sig") as f:               # le BOM est tolere
            json.dump({"statut": "UNSTABLE", "duree_ms": 12345, "code_retour": 4, "message": "é à ü — ok",
                       "imbrique": {"a": [1, 2]}}, f, ensure_ascii=False)
        self.ecrire("--evenement", "fin_job", "--niveau", "WARNING", "--champs-json", chemin)
        (e,) = evenements_de(self.logs)
        self.assertEqual((e["niveau"], e["statut"], e["duree_ms"], e["code_retour"], e["message"]),
                         ("WARNING", "UNSTABLE", 12345, 4, "é à ü — ok"))
        self.assertEqual(e["imbrique"], {"a": [1, 2]})

    def test_niveaux(self):
        for niveau, attendu in (("INFO", "INFO"), ("WARNING", "WARNING"), ("ERREUR", "ERREUR"), ("inconnu", "INFO")):
            self.ecrire("--evenement", "x_" + niveau, "--niveau", niveau)
        par_nom = {e["evenement"]: e["niveau"] for e in evenements_de(self.logs)}
        self.assertEqual(par_nom, {"x_INFO": "INFO", "x_WARNING": "WARNING", "x_ERREUR": "ERREUR", "x_inconnu": "INFO"})

    def test_ne_leve_jamais_d_echec(self):
        # fichier de champs absent, JSON invalide : l'evenement est ecrit sans les champs, code 0
        code, _, erreur = self.ecrire("--evenement", "a", "--champs-json", self.chemin("absent.json"))
        self.assertEqual(code, 0)
        self.assertIn("non ecrit", erreur)
        with open(self.chemin("casse.json"), "w") as f:
            f.write("{pas du json")
        code, _, erreur = self.ecrire("--evenement", "b", "--champs-json", self.chemin("casse.json"))
        self.assertEqual(code, 0)

    def test_dossier_impossible_replie_sur_le_fichier_de_secours(self):
        with open(self.chemin("bloc"), "w") as f:
            f.write("x")
        self.logs = self.chemin("bloc", "logs")                         # un fichier a la place du dossier
        from unittest import mock
        with mock.patch.object(journal_si.tempfile, "gettempdir", return_value=self.racine):
            code, _, erreur = self.ecrire("--evenement", "debut_job")
        self.assertEqual(code, 0)
        self.assertIn("replie", erreur)
        self.assertTrue(glob.glob(os.path.join(self.racine, "journal_si_secours_*.jsonl")))

    def test_console(self):
        _, sortie, _ = self.ecrire("--evenement", "fin_job", "--niveau", "ERREUR", "--console")
        self.assertIn("fin_job", sortie)
        self.assertIn("ERREUR", sortie)

    def test_processus_reel_comme_le_fait_la_bibliotheque(self):
        """journal_si.py lance par `bat`, avec les variables d'environnement de Jenkins."""
        champs = self.chemin("champs.json")
        with open(champs, "w", encoding="utf-8") as f:
            f.write(json.dumps({"statut": "SUCCESS", "duree_ms": 4200}))
        env = dict(os.environ, **ENV_JENKINS)
        resultat = subprocess.run([sys.executable, os.path.join(RACINE, "journal_si.py"), "--dossier", self.logs,
                                   "--application", "file_management", "--environnement", "production",
                                   "--evenement", "fin_job", "--niveau", "INFO", "--champs-json", champs],
                                  cwd=self.racine, env=env, capture_output=True)
        self.assertEqual((resultat.returncode, resultat.stdout, resultat.stderr), (0, b"", b""))
        (e,) = evenements_de(self.logs)
        self.assertEqual((e["evenement"], e["job"], e["statut"], e["duree_ms"]), ("fin_job", "COPIE_PROD", "SUCCESS", 4200))

    def test_arguments_obligatoires(self):
        with self.assertRaises(SystemExit):
            with redirect_stderr(io.StringIO()):
                journal_si.main(["--dossier", self.logs])


# =========================================================================== #
def sans_commentaires_ni_chaines(texte):
    """Texte Groovy sans commentaires ni chaines : sert a verifier l'equilibre des delimiteurs."""
    sortie, i, n = [], 0, len(texte)
    while i < n:
        c = texte[i]
        if texte.startswith("//", i):
            i = texte.find("\n", i)
            i = n if i < 0 else i
        elif texte.startswith("/*", i):
            i = texte.find("*/", i) + 2
        elif c in "'\"":
            fin = i + 1
            while fin < n and texte[fin] != c:
                fin += 2 if texte[fin] == "\\" else 1
            i = fin + 1
            sortie.append("S")
        else:
            sortie.append(c)
            i += 1
    return "".join(sortie)


def fichiers_jenkins():
    return sorted(glob.glob(os.path.join(JENKINS, "Jenkinsfile.*")) + glob.glob(os.path.join(JENKINS, "vars", "*.groovy")))


def lire(chemin):
    with open(chemin, encoding="utf-8") as f:
        return f.read()


class TestFichiersJenkins(unittest.TestCase):
    def test_les_fichiers_existent(self):
        noms = {os.path.relpath(f, JENKINS) for f in fichiers_jenkins()}
        self.assertEqual(noms, {"Jenkinsfile.transfert", "Jenkinsfile.sauvegarde", "Jenkinsfile.verification",
                                "Jenkinsfile.purge", os.path.join("vars", "journalSI.groovy"), os.path.join("vars", "fileManagement.groovy")})

    def test_delimiteurs_equilibres_et_pas_de_tabulation(self):
        for chemin in fichiers_jenkins():
            texte = lire(chemin)
            self.assertNotIn("\t", texte, chemin)
            nu = sans_commentaires_ni_chaines(texte)
            for ouvrant, fermant in ("{}", "()", "[]"):
                self.assertEqual(nu.count(ouvrant), nu.count(fermant), "%s : %s%s" % (chemin, ouvrant, fermant))
            # ordre : jamais de fermant avant son ouvrant
            pile = []
            for c in nu:
                if c in "{([":
                    pile.append(c)
                elif c in "})]":
                    self.assertTrue(pile and "{([".index(pile.pop()) == "})]".index(c), chemin)
            self.assertEqual(pile, [], chemin)

    def test_les_fichiers_sont_en_utf8_sans_caractere_exotique(self):
        for chemin in fichiers_jenkins():
            octets = open(chemin, "rb").read()
            self.assertFalse(octets.startswith(b"\xef\xbb\xbf"), chemin)
            octets.decode("utf-8")

    def test_bibliotheque_journalSI(self):
        texte = lire(os.path.join(JENKINS, "vars", "journalSI.groovy"))
        for fonction in ("def evenement(Map p)", "def debutJob(Map p)", "def finJob(Map p)"):
            self.assertIn(fonction, texte)
        # le statut Jenkins devient un niveau du journal
        ligne_niveaux = next(l for l in texte.splitlines() if "def niveaux" in l)
        niveaux = dict(re.findall(r"(\w+): '(INFO|WARNING|ERREUR)'", ligne_niveaux))
        self.assertEqual(niveaux, {"SUCCESS": "INFO", "UNSTABLE": "WARNING", "ABORTED": "WARNING",
                                   "FAILURE": "ERREUR", "NOT_BUILT": "INFO"})
        self.assertTrue(set(niveaux.values()) <= set(journal_si.NIVEAUX))
        # les options passees a journal_si.py existent
        for option in re.findall(r"' --([a-z-]+)", texte):
            self.assertIn("--" + option, io_aide_journal(), option)
        self.assertIn("catch (Exception e)", texte)              # une panne de journal n'echoue jamais le build
        self.assertIn("debut_job", texte)
        self.assertIn("fin_job", texte)

    def test_bibliotheque_fileManagement_traduit_les_codes_retour(self):
        texte = lire(os.path.join(JENKINS, "vars", "fileManagement.groovy"))
        self.assertIn("def call(Map p)", texte)
        self.assertIn("rc == 0", texte)
        self.assertIn("rc == 4", texte)
        self.assertIn("unstable(", texte)
        self.assertIn("error(", texte)
        self.assertEqual(cli.CODE_AVERTISSEMENT, 4)                # 4 = UNSTABLE, comme documente
        self.assertIn("-m copie", texte)

    def test_job_de_transfert_autorise_les_builds_simultanes(self):
        texte = lire(os.path.join(JENKINS, "Jenkinsfile.transfert"))
        code = sans_commentaires_ni_chaines(texte)
        self.assertNotIn("disableConcurrentBuilds", code)           # voulu : la protection est dans le moteur
        self.assertIn("cron('H/5 * * * *')", texte)
        self.assertIn("timeout(time:", texte)
        self.assertIn("@Library('journal-si') _", texte)
        self.assertIn("journalSI.debutJob", texte)
        self.assertIn("post {", texte)
        self.assertRegex(texte, r"always\s*\{\s*script\s*\{\s*journalSI\.finJob")

    def test_jobs_de_sauvegarde_et_de_verification_ne_sont_pas_simultanes(self):
        for nom in ("Jenkinsfile.sauvegarde", "Jenkinsfile.verification", "Jenkinsfile.purge"):
            texte = lire(os.path.join(JENKINS, nom))
            self.assertIn("disableConcurrentBuilds()", sans_commentaires_ni_chaines(texte), nom)
            self.assertIn("journalSI.finJob", texte)

    def test_les_commandes_des_jenkinsfile_sont_acceptees_par_le_moteur(self):
        """Chaque `commande: '...'` des Jenkinsfile est analysee par le meme analyseur d'arguments que le moteur."""
        trouvees = 0
        for chemin in glob.glob(os.path.join(JENKINS, "Jenkinsfile.*")):
            for ligne in lire(chemin).splitlines():
                m = re.search(r"commande:\s*(.+?)\)\s*$", ligne)
                if not m or ligne.strip().startswith("//"):
                    continue
                expression = re.sub(r"'\s*\+\s*env\.[A-Z_]+\s*\+\s*'", "VALEUR", m.group(1).strip())
                self.assertTrue(expression.startswith("'") and expression.endswith("'"), expression)
                arguments = shlex.split(expression[1:-1].replace("\\\\", "/"))
                p, args = cli._arguments(["--config", "x.jsonl"] + arguments)
                trouvees += 1
        self.assertGreaterEqual(trouvees, 2)                        # sauvegarde et verification

    def test_la_commande_de_lancement_du_job_de_transfert(self):
        p, args = cli._arguments(["--config", "x.jsonl"])
        self.assertFalse(args.verifier or args.etat or args.executer_regle)    # sans commande = lancement


def io_aide_journal():
    sortie = io.StringIO()
    try:
        with redirect_stdout(sortie):
            journal_si.main(["--help"])
    except SystemExit:
        pass
    return sortie.getvalue()


# =========================================================================== #
class CasLancementProcessus(CasProcessus):
    """Lancements du moteur comme Jenkins les fait : un processus `python -m copie` par build."""

    def lancer(self, build, *options, ligne_commande=None):
        env = dict(os.environ, PYTHONPATH=RACINE, **{"JOB_NAME": "COPIE_PROD", "BUILD_NUMBER": str(build),
                                                      "BUILD_URL": "https://jenkins.exemple/job/COPIE_PROD/%d/" % build,
                                                      "NODE_NAME": "SRV-JENKINS01"})
        return subprocess.Popen([sys.executable, "-m", "copie", "--config", self.conf] + list(options),
                                cwd=RACINE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def preparer(self, nombre, **modif):
        for i in range(nombre):
            os.makedirs(self.chemin("src%d" % i))
            fichier = self.ecrire(os.path.join("src%d" % i, "f.csv"), b"contenu %d" % i)
            t = time.time() - 600
            os.utime(fichier, (t, t))
            self.brute(id="r%d" % i, source=self.chemin("src%d" % i), cible=self.chemin("d%d" % i),
                       planification=SEPT_HEURES, **modif)
        p = self.declencher(*["r%d" % i for i in range(nombre)])
        self.conf = p.chemin
        return p


class TestBuildsSimultanes(CasLancementProcessus):
    def test_deux_builds_en_meme_temps_chaque_regle_une_seule_fois(self):
        self.preparer(8)
        a, b = self.lancer(1), self.lancer(2)
        sorties = [a.communicate(timeout=120)[0], b.communicate(timeout=120)[0]]
        self.assertEqual((a.returncode, b.returncode), (0, 0), sorties)
        for i in range(8):
            no = self.b.numero_regle("r%d" % i)
            executions = self.b.c.execute("SELECT statut FROM executions WHERE regle_no = ?", (no,)).fetchall()
            self.assertEqual([e[0] for e in executions], ["SUCCES"], "r%d" % i)       # exactement une execution
            self.assertEqual(os.listdir(self.chemin("d%d" % i)), ["f.csv"])            # livre une seule fois
            self.assertEqual(self.regle_base("r%d" % i)["en_cours"], 0)
        evenements = evenements_de(self.chemin("logs"))
        livres = [e for e in evenements if e["evenement"] == "fichier_livre"]
        self.assertEqual(len(livres), 8)
        # chaque evenement identifie son build Jenkins
        self.assertEqual({e["build"] for e in evenements if e["evenement"] == "regle_terminee"} - {"1", "2"}, set())
        self.assertTrue(all(e.get("job") == "COPIE_PROD" for e in livres))

    def test_un_build_ignore_les_regles_deja_en_cours_dans_l_autre(self):
        self.preparer(1, situations=ATTENTE_COURTE_2S)
        premier = self.lancer(1)
        time.sleep(1.5)                                             # le premier build tient la regle
        second = self.lancer(2)
        sortie2 = second.communicate(timeout=60)[0]
        premier.communicate(timeout=60)
        self.assertEqual(second.returncode, 0, sortie2)             # deja en cours : pas une erreur
        self.assertEqual(self.b.c.execute("SELECT COUNT(*) FROM executions").fetchone()[0], 1)


ATTENTE_COURTE_2S = {"aucun_fichier": {"tentatives": 2, "delai_sec": 4, "niveau_final": "INFO"}}


class TestJobSimule(CasLancementProcessus):
    """La sequence d'un job Jenkins : debut_job, lancement, fin_job avec le code retour."""

    def journal_job(self, evenement, niveau, build, **champs):
        env = dict(os.environ, **{"JOB_NAME": "COPIE_PROD", "BUILD_NUMBER": str(build),
                                  "BUILD_URL": "https://jenkins.exemple/job/COPIE_PROD/%d/" % build, "NODE_NAME": "SRV-JENKINS01"})
        fichier = self.chemin("champs_%s.json" % evenement)
        with open(fichier, "w", encoding="utf-8") as f:
            json.dump(champs, f)
        subprocess.run([sys.executable, os.path.join(RACINE, "journal_si.py"), "--dossier", self.chemin("logs"),
                        "--application", "file_management", "--environnement", "production", "--evenement", evenement,
                        "--niveau", niveau, "--champs-json", fichier], cwd=self.racine, env=env, check=True)

    def test_sequence_complete_succes_et_avertissement(self):
        self.preparer(2)
        self.journal_job("debut_job", "INFO", 10)
        build = self.lancer(10)
        build.communicate(timeout=120)
        self.assertEqual(build.returncode, 0)
        self.journal_job("fin_job", "INFO", 10, statut="SUCCESS", duree_ms=4000, code_retour=0)

        os.utime(self.ecrire("src0/futur.csv", b"x"), (time.time() + 7200, time.time() + 7200))     # date future : avertissement
        self.b.poser_lancement_manuel("r0", "essai")
        self.journal_job("debut_job", "INFO", 11)
        build = self.lancer(11)
        build.communicate(timeout=120)
        self.assertEqual(build.returncode, 4)                                                      # -> UNSTABLE
        self.journal_job("fin_job", "WARNING", 11, statut="UNSTABLE", duree_ms=5000, code_retour=4)

        evenements = evenements_de(self.chemin("logs"))
        job = [(e["build"], e["evenement"], e["niveau"]) for e in evenements if e["evenement"] in ("debut_job", "fin_job")]
        self.assertEqual(job, [("10", "debut_job", "INFO"), ("10", "fin_job", "INFO"),
                               ("11", "debut_job", "INFO"), ("11", "fin_job", "WARNING")])
        # le bilan du lancement et les evenements de job partagent le meme fichier et les memes champs
        fins = [e for e in evenements if e["evenement"] == "fin_lancement"]
        self.assertEqual([(e["build"], e["niveau"], e["code_retour"]) for e in fins], [("10", "INFO", 0), ("11", "WARNING", 4)])
        self.assertEqual({e["noeud"] for e in evenements if "noeud" in e}, {"SRV-JENKINS01"})

    def test_code_retour_d_un_parametrage_invalide(self):
        self.preparer(1)
        with open(self.conf, "w", encoding="utf-8") as f:
            f.write('{"version": 1, "environnement": "production"}\n')
        build = self.lancer(12)
        sortie = build.communicate(timeout=60)[0].decode("utf-8", "replace")
        self.assertEqual(build.returncode, 2)                        # -> FAILURE
        self.assertIn("E04", sortie)


class TestAbandonDUnBuild(CasLancementProcessus):
    def attendre(self, condition, delai=40):
        fin = time.time() + delai
        while time.time() < fin:
            valeur = condition()
            if valeur:
                return valeur
            time.sleep(0.2)
        self.fail("condition jamais remplie")

    def demarrer_regle_longue(self):
        self.preparer(1, situations=ATTENTE_LONGUE, duree_max_sec=3600)
        os.remove(os.path.join(self.chemin("src0"), "f.csv"))         # rien a livrer : la regle attend
        build = self.lancer(20)
        self.addCleanup(lambda: build.poll() is None and processus.tuer_arbre(build.pid))
        ligne = self.attendre(lambda: (lambda l: l if l["en_cours"] and l["pid"] and l["pid"] != build.pid else None)
                              (self.regle_base("r0")))
        time.sleep(1.0)
        return build, ligne["pid"]

    def test_abandon_avec_arret_de_l_arbre_comme_le_fait_jenkins(self):
        build, pid_fils = self.demarrer_regle_longue()
        self.assertTrue(processus.tuer_arbre(build.pid))              # Jenkins arrete l'arbre de processus du build
        build.wait(timeout=30)
        time.sleep(0.5)
        self.assertIsNone(processus.date_creation(pid_fils))
        self.assertEqual(self.regle_base("r0")["en_cours"], 1)         # le drapeau est reste pose...
        # ... et le lancement suivant le libere (processus disparu), sans rien relivrer
        suivant = self.lancer(21)
        suivant.communicate(timeout=60)
        etat = self.regle_base("r0")
        self.assertEqual((etat["en_cours"], etat["dernier_statut"], etat["derniere_erreur_situation"]),
                         (0, "ERREUR", "arret_anormal"))
        self.assertEqual(suivant.returncode, 1)

    def test_si_seul_l_orchestrateur_est_tue_ses_fils_disparaissent(self):
        """Job Object KILL_ON_JOB_CLOSE : meme sans arret de l'arbre, aucun fils ne survit."""
        build, pid_fils = self.demarrer_regle_longue()
        subprocess.run(["taskkill", "/F", "/PID", str(build.pid)], capture_output=True)    # sans /T
        build.wait(timeout=30)
        fin = time.time() + 15
        while processus.date_creation(pid_fils) is not None and time.time() < fin:
            time.sleep(0.2)
        self.assertIsNone(processus.date_creation(pid_fils), "le fils a survecu a la mort de l'orchestrateur")


if __name__ == "__main__":
    unittest.main()
