"""J11 : migration de l'ancien script (copies.conf + historique) et outils de recette."""
import contextlib
import io
import json
import os
import subprocess
import sys
import time
import unittest
from unittest import mock

import file_management as v1
from copie import __main__ as cli
from copie import base, migration
from copie.controles import verifier_fichier
from copie.parametrage import charger
from tests.outils import CasTemporaire

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, "outils"))
import comparer_dossiers  # noqa: E402


class CasMigration(CasTemporaire):
    def conf(self, texte, nom="copies.conf", encodage="utf-8"):
        chemin = self.chemin(nom)
        with open(chemin, "w", encoding=encodage, newline="") as f:
            f.write(texte)
        return chemin

    def convertir(self, texte, **kw):
        sortie = self.chemin("sortie", "production.jsonl")
        compte = migration.convertir_conf(self.conf(texte), "production", self.chemin("donnees", "production.db"),
                                          sortie, **kw)
        return compte, sortie

    def regles(self, sortie):
        with open(sortie, encoding="utf-8") as f:
            lignes = [json.loads(l) for l in f]
        return lignes[0], lignes[1:]


class TestLectureDeLAncienneConf(CasMigration):
    def test_la_conf_d_exemple_du_depot_equivaut_a_l_analyse_de_l_ancien_script(self):
        chemin = os.path.join(RACINE, "copies.conf")
        nouvelles = migration.lire_ancienne_conf(chemin)
        anciennes = v1.lire_parametrage(chemin)
        self.assertEqual(len(nouvelles), len(anciennes))
        for n, a in zip(nouvelles, anciennes):
            self.assertEqual(os.path.normpath(os.path.expandvars(n.source)), a.source)
            self.assertEqual(os.path.normpath(os.path.expandvars(n.cible)), a.cible)
            self.assertEqual((n.jours, n.masques, n.recursif, n.numero), (a.jours, a.masques, a.recursif, a.num_ligne))

    def test_formats_acceptes_comme_l_ancien_script(self):
        lignes = migration.lire_ancienne_conf(self.conf(
            "# commentaire\n\n a | b | tout\nc|d|J|*.xml;*.json|OUI\ne|f|j - 7|*|0\ng|h|ALL|\n", encodage="utf-8-sig"))
        self.assertEqual([(l.critere, l.jours, l.masques, l.recursif) for l in lignes],
                         [("TOUT", None, ["*"], False), ("J", 0, ["*.xml", "*.json"], True),
                          ("J-7", 7, ["*"], False), ("TOUT", None, ["*"], False)])

    def test_erreurs_cumulees_avec_numeros_de_ligne(self):
        with self.assertRaises(migration.ErreurMigration) as cm:
            migration.lire_ancienne_conf(self.conf("a | b\nc | d | hier\n | b | J\na|b|J|*|peut-etre\na|b|J|*|oui|6\n"))
        message = str(cm.exception)
        for numero in (1, 2, 3, 4, 5):
            self.assertIn("ligne %d" % numero, message)

    def test_fichier_absent_ou_vide(self):
        with self.assertRaises(migration.ErreurMigration):
            migration.lire_ancienne_conf(self.chemin("absent.conf"))
        with self.assertRaises(migration.ErreurMigration):
            migration.lire_ancienne_conf(self.conf("# rien\n"))


class TestConversion(CasMigration):
    def test_regle_equivalente_a_la_ligne(self):
        compte, sortie = self.convertir("D:\\src\\factures | D:\\dst\\factures | J-3 | *.csv;*.xml | oui\n")
        entete, (regle,) = self.regles(sortie)
        self.assertEqual(entete, {"version": 1, "environnement": "production",
                                  "base": self.chemin("donnees", "production.db")})
        self.assertEqual((regle["id"], regle["mode"], regle["actif"]), ("copie_01_factures", "copie", False))
        self.assertEqual(regle["selection"], {"masque": "*.csv;*.xml", "recursif": True, "modifie_depuis": "J-3"})
        self.assertEqual((regle["source"], regle["cible"]), ("D:\\src\\factures", "D:\\dst\\factures"))
        # comportement de l'ancien script : recopie si la cible a perdu le fichier, ecrasement du meme nom
        self.assertEqual((regle["si_cible_absente"], regle["si_existe_cible"], regle["identite"]),
                         ("recopier", "ecraser", "version"))
        self.assertIn("ligne 1", regle["description"])
        self.assertIn("copies.conf", regle["description"])

    def test_le_fichier_produit_est_valide(self):
        compte, sortie = self.convertir(open(os.path.join(RACINE, "copies.conf"), encoding="utf-8").read())
        self.assertTrue(compte["verification"].ok, compte["verification"].en_texte())
        self.assertEqual(len(compte["regles"]), 5)
        self.assertEqual(compte["verification"].codes(), [])
        parametrage, rapport = verifier_fichier(sortie)
        self.assertTrue(rapport.ok)
        self.assertEqual(len(parametrage.regles), 5)

    def test_criteres(self):
        compte, sortie = self.convertir("a:\\s1 | b:\\d1 | TOUT\na:\\s2 | b:\\d2 | J\na:\\s3 | b:\\d3 | J-7\n")
        _, regles = self.regles(sortie)
        self.assertEqual([r["selection"]["modifie_depuis"] for r in regles], ["TOUT", "J", "J-7"])

    def test_retention_toujours_superieure_a_la_fenetre(self):
        compte, sortie = self.convertir("a:\\s1 | b:\\d1 | J-120\na:\\s2 | b:\\d2 | J-1\n")
        _, regles = self.regles(sortie)
        self.assertEqual([r["retention_historique_jours"] for r in regles], [151, 90])
        self.assertTrue(compte["verification"].ok, compte["verification"].en_texte())      # pas de R08

    def test_identifiants_uniques_valides_et_bornes(self):
        longue = "x" * 200
        compte, sortie = self.convertir("a:\\ventes | b:\\d1 | J\na:\\ventes | b:\\d2 | J\na:\\%s | b:\\d3 | J\n"
                                        "\\\\SRV\\Donnees ÉTÉ & co | b:\\d4 | J\na:\\ | b:\\d5 | J\n" % longue)
        _, regles = self.regles(sortie)
        ids = [r["id"] for r in regles]
        self.assertEqual(len(set(i.lower() for i in ids)), 5)
        self.assertTrue(all(len(i) <= 64 for i in ids))
        self.assertEqual(ids[:2], ["copie_01_ventes", "copie_02_ventes"])
        self.assertTrue(compte["verification"].ok, compte["verification"].en_texte())

    def test_inactives_par_defaut_actives_sur_demande(self):
        _, sortie = self.convertir("a:\\s | b:\\d | J\n")
        self.assertFalse(self.regles(sortie)[1][0]["actif"])
        os.remove(sortie)
        compte, sortie = self.convertir("a:\\s | b:\\d | J\n", actives=True)
        self.assertTrue(self.regles(sortie)[1][0]["actif"])
        self.assertFalse(any("INACTIVES" in n for n in compte["notes"]))

    def test_planification_par_defaut_et_personnalisee(self):
        _, sortie = self.convertir("a:\\s | b:\\d | J\n", frequence_sec=300)
        self.assertEqual(self.regles(sortie)[1][0]["planification"],
                         {"type": "intervalle", "frequence_sec": 300, "debut": "00:00", "fin": "23:59", "jours": "tous"})

    def test_notes_pour_la_revue(self):
        compte, _ = self.convertir("%RACINE%\\s | b:\\d | J | * | oui\n")
        texte = " ".join(compte["notes"])
        for attendu in ("PROVISOIRES", "Planification par defaut", "si_cible_absente = recopier", "INACTIVES",
                        "%VAR%", "recursives"):
            self.assertIn(attendu, texte)

    def test_ne_jamais_ecraser_un_parametrage(self):
        compte, sortie = self.convertir("a:\\s | b:\\d | J\n")
        avant = open(sortie, encoding="utf-8").read()
        with self.assertRaises(migration.ErreurMigration) as cm:
            migration.convertir_conf(self.conf("autre:\\s | autre:\\d | J\n"), "production", "x.db", sortie)
        self.assertIn("existe deja", str(cm.exception))
        self.assertEqual(open(sortie, encoding="utf-8").read(), avant)
        self.assertEqual(os.listdir(os.path.dirname(sortie)), ["production.jsonl"])        # pas de .tmp

    def test_conf_invalide_n_ecrit_rien(self):
        with self.assertRaises(migration.ErreurMigration):
            migration.convertir_conf(self.conf("a | b | hier\n"), "production", "x.db", self.chemin("s", "p.jsonl"))
        self.assertFalse(os.path.exists(self.chemin("s")))

    def test_les_defauts_de_la_conf_sont_signales_par_le_controle_standard(self):
        compte, _ = self.convertir("a:\\s | a:\\s | J\n")                        # source = cible
        self.assertFalse(compte["verification"].ok)
        self.assertEqual(compte["verification"].refus[0].code, "R03")

    def test_accents_conserves(self):
        compte, sortie = self.convertir("D:\\Données\\é | D:\\Cible\\à | J\n")
        self.assertIn("Données", open(sortie, encoding="utf-8").read())              # pas de \u00e9
        self.assertEqual(self.regles(sortie)[1][0]["source"], "D:\\Données\\é")


class TestCommandesMigration(CasMigration):
    def lancer(self, *args):
        sortie, erreur = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
            code = cli.main(list(args))
        return code, sortie.getvalue(), erreur.getvalue()

    def test_migrer_sans_config(self):
        conf = self.conf("a:\\s | b:\\d | J\n")
        code, sortie, _ = self.lancer("--migrer-ancien", conf, "--environnement", "production", "--base",
                                      self.chemin("db", "p.db"), "--sortie", self.chemin("production.jsonl"))
        self.assertEqual(code, 0, sortie)
        self.assertIn("INACTIVES", sortie)
        self.assertTrue(os.path.isfile(self.chemin("production.jsonl")))

    def test_migrer_en_json(self):
        conf = self.conf("a:\\s | b:\\d | J\n")
        code, sortie, erreur = self.lancer("--migrer-ancien", conf, "--environnement", "production", "--base",
                                           self.chemin("p.db"), "--sortie", self.chemin("production.jsonl"), "--format", "json",
                                           "--frequence-sec", "600", "--actives")
        r = json.loads(sortie)
        self.assertEqual((code, erreur, r["ok"], r["version_contrat"]), (0, "", True, 1))
        self.assertEqual((r["regles"][0]["id"], r["fichier"], r["refus"]), ("copie_01_s", self.chemin("production.jsonl"), []))
        self.assertTrue(r["notes"])

    def test_erreurs(self):
        conf = self.conf("a | b | hier\n")
        code, _, erreur = self.lancer("--migrer-ancien", conf, "--environnement", "production", "--base", "x.db")
        self.assertEqual(code, 2)
        self.assertIn("ligne 1", erreur)
        code, _, erreur = self.lancer("--migrer-ancien", conf)
        self.assertEqual(code, 2)
        self.assertIn("--environnement", erreur)
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                cli.main(["--etat"])                                        # --config reste obligatoire ailleurs

    def test_code_2_quand_le_parametrage_genere_est_refuse(self):
        conf = self.conf("a:\\s | a:\\s | J\n")
        code, sortie, _ = self.lancer("--migrer-ancien", conf, "--environnement", "production", "--base", "x.db",
                                      "--sortie", self.chemin("production.jsonl"))
        self.assertEqual(code, 2)
        self.assertIn("R03", sortie)

    def test_le_nom_du_fichier_de_sortie_est_celui_de_l_environnement(self):
        conf = self.conf("a:\\s | b:\\d | J\n")
        code, _, erreur = self.lancer("--migrer-ancien", conf, "--environnement", "production", "--base", "x.db",
                                      "--sortie", self.chemin("autre_nom.jsonl"))
        self.assertEqual(code, 2)
        self.assertIn("production.jsonl", erreur)
        self.assertFalse(os.path.exists(self.chemin("autre_nom.jsonl")))


# =========================================================================== #
class TestImportDeLHistorique(CasMigration):
    def setUp(self):
        super().setUp()
        self.src, self.dst = self.chemin("src"), self.chemin("dst")
        os.makedirs(self.src)
        self.chemin_base = self.chemin("donnees", "production.db")
        base.initialiser(self.chemin_base, "production", "u")
        self.b = base.ouvrir(self.chemin_base, "production")
        self.addCleanup(self.b.fermer)

    def parametrage(self, *regles):
        chemin = self.chemin("param", "production.jsonl")
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        entete = {"version": 1, "environnement": "production", "base": self.chemin_base}
        with open(chemin, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in [entete] + list(regles)) + "\n")
        p, rapport = charger(chemin)
        self.assertTrue(rapport.ok, rapport.en_texte())
        return p

    def regle(self, ident="r1", **modif):
        r = {"id": ident, "source": self.src, "cible": self.dst, "mode": "copie",
             "planification": {"type": "quotidien", "heure": "07:00"}}
        for cle, valeur in modif.items():
            if isinstance(valeur, dict) and isinstance(r.get(cle), dict):
                r[cle].update(valeur)
            else:
                r[cle] = valeur
        return r

    def historique(self, *entrees):
        chemin = self.chemin("copies.historique.json")
        fichiers = {}
        for source, cible, taille, mtime_ns, copie_le in entrees:
            cle = os.path.normcase(os.path.abspath(source)) + " => " + os.path.normcase(os.path.abspath(cible))
            fichiers[cle] = {"source": source, "cible": cible, "taille": taille, "mtime_ns": mtime_ns,
                             "sha256": "x", "copie_le": copie_le}
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "fichiers": fichiers}, f)
        return chemin

    def importer(self, p, chemin):
        return migration.importer_historique(p, self.b, chemin, "benoit", "migration de recette")

    def entree(self, nom, taille=10, mtime_ns=1_700_000_000_000_000_000, quand="2026-11-01T10:00:00"):
        return (os.path.join(self.src, nom), os.path.join(self.dst, nom), taille, mtime_ns, quand)

    def test_les_versions_deja_copiees_deviennent_termine(self):
        p = self.parametrage(self.regle())
        compte = self.importer(p, self.historique(self.entree("a.csv"), self.entree("b.csv", 20)))
        self.assertEqual((compte["entrees"], compte["importees"], compte["sans_regle"], compte["par_regle"]),
                         (2, 2, 0, {"r1": 2}))
        cle = base.cle_version("r1", "a.csv", 10, 1_700_000_000_000_000_000)
        self.assertEqual(self.b.etat_fichier(cle), base.TERMINE)
        self.assertIsNone(self.b.etat_fichier(base.cle_version("r1", "a.csv", 11, 1_700_000_000_000_000_000)))
        ligne = self.b.c.execute("SELECT vu_jour, livre_le FROM fichiers WHERE cle = ?", (cle,)).fetchone()
        import datetime
        self.assertEqual(ligne["livre_le"], int(datetime.datetime(2026, 11, 1, 10).timestamp()))
        self.assertEqual(ligne["vu_jour"], base.jour_de(ligne["livre_le"]))

    def test_idempotent_et_trace(self):
        p = self.parametrage(self.regle())
        chemin = self.historique(self.entree("a.csv"))
        self.importer(p, chemin)
        compte = self.importer(p, chemin)
        self.assertEqual((compte["importees"], compte["deja_connues"]), (0, 1))
        trace = self.b.c.execute("SELECT utilisateur, commentaire, resultat FROM journal_actions "
                                 "WHERE action = 'migration' ORDER BY id").fetchall()
        self.assertEqual([tuple(t) for t in trace],
                         [("benoit", "migration de recette", "1 fichier(s) importe(s) depuis copies.historique.json"),
                          ("benoit", "migration de recette", "0 fichier(s) importe(s) depuis copies.historique.json")])

    def test_entrees_sans_regle_comptees_et_listees(self):
        p = self.parametrage(self.regle(selection={"masque": "*.csv"}))
        compte = self.importer(p, self.historique(
            self.entree("a.csv"),
            (os.path.join(self.chemin("ailleurs"), "x.csv"), os.path.join(self.dst, "x.csv"), 1, 1, "2026-11-01T10:00:00"),
            (os.path.join(self.src, "a.csv"), os.path.join(self.chemin("autre_cible"), "a.csv"), 1, 1, "2026-11-01T10:00:00"),
            (os.path.join(self.src, "a.csv"), os.path.join(self.dst, "renomme.csv"), 1, 1, "2026-11-01T10:00:00"),
            (os.path.join(self.src, "n.xml"), os.path.join(self.dst, "n.xml"), 1, 1, "2026-11-01T10:00:00"),
            (os.path.join(self.src, "sous", "r.csv"), os.path.join(self.dst, "sous", "r.csv"), 1, 1, "2026-11-01T10:00:00")))
        self.assertEqual((compte["importees"], compte["sans_regle"]), (1, 5))
        self.assertEqual(len(compte["exemples_sans_regle"]), 5)

    def test_sous_dossiers_seulement_pour_une_regle_recursive(self):
        p = self.parametrage(self.regle(selection={"recursif": True}))
        entree = (os.path.join(self.src, "n1", "n2", "a.csv"), os.path.join(self.dst, "n1", "n2", "a.csv"), 5, 7, "2026-11-01T10:00:00")
        compte = self.importer(p, self.historique(entree))
        self.assertEqual(compte["importees"], 1)
        self.assertEqual(self.b.etat_fichier(base.cle_version("r1", "n1\\n2\\a.csv", 5, 7)), base.TERMINE)

    def test_plusieurs_regles_la_bonne_est_choisie_par_le_masque(self):
        p = self.parametrage(self.regle("csv", selection={"masque": "*.csv"}),
                             self.regle("xml", selection={"masque": "*.xml"}))
        compte = self.importer(p, self.historique(self.entree("a.csv"), self.entree("b.xml")))
        self.assertEqual(compte["par_regle"], {"csv": 1, "xml": 1})

    def test_casse_et_variables_d_environnement(self):
        os.environ["COPIE_TEST_SRC"] = self.src
        self.addCleanup(os.environ.pop, "COPIE_TEST_SRC", None)
        variable = "%COPIE_TEST_SRC%" if os.name == "nt" else "$COPIE_TEST_SRC"
        p = self.parametrage(self.regle(source=variable))
        entree = (os.path.join(self.src.upper(), "A.CSV"), os.path.join(self.dst, "A.csv"), 1, 1, "2026-11-01T10:00:00")
        self.assertEqual(self.importer(p, self.historique(entree))["importees"], 1)

    def test_historique_illisible_ou_absent(self):
        p = self.parametrage(self.regle())
        with self.assertRaises(migration.ErreurMigration):
            self.importer(p, self.chemin("absent.json"))
        with open(self.chemin("casse.json"), "w") as f:
            f.write("{pas du json")
        with self.assertRaises(migration.ErreurMigration):
            self.importer(p, self.chemin("casse.json"))
        with open(self.chemin("liste.json"), "w") as f:
            f.write("[1, 2]")
        with self.assertRaises(migration.ErreurMigration):
            self.importer(p, self.chemin("liste.json"))

    def test_entrees_incompletes_ignorees_sans_planter(self):
        p = self.parametrage(self.regle())
        chemin = self.chemin("h.json")
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "fichiers": {"x": {"source": "a"}, "y": {"source": self.src + "\\a.csv",
                       "cible": self.dst + "\\a.csv", "taille": "dix", "mtime_ns": 1}}}, f)
        compte = self.importer(p, chemin)
        self.assertEqual((compte["importees"], compte["sans_regle"]), (0, 2))

    def test_gros_historique(self):
        p = self.parametrage(self.regle())
        entrees = [(os.path.join(self.src, "f%d.csv" % i), os.path.join(self.dst, "f%d.csv" % i), i, i, "2026-11-01T10:00:00")
                   for i in range(20000)]
        debut = time.time()
        compte = self.importer(p, self.historique(*entrees))
        self.assertEqual(compte["importees"], 20000)
        self.assertLess(time.time() - debut, 20)


# =========================================================================== #
class TestAncienScriptPuisNouveau(CasMigration):
    """Parcours reel : l'ancien script copie, on migre, le nouveau ne relivre RIEN."""

    def setUp(self):
        super().setUp()
        self.src, self.dst = self.chemin("src"), self.chemin("dst")
        os.makedirs(self.src)
        self.ecrire("src/a.csv", b"contenu A")
        self.ecrire("src/b.csv", b"contenu B")
        self.ecrire("src/sous/c.csv", b"contenu C")
        self.ecrire("src/ignore.txt", b"pas un csv")
        self.conf_v1 = self.conf("%s | %s | J-1 | *.csv | oui\n" % (self.src, self.dst))
        self.historique = self.chemin("copies.historique.json")
        self.addCleanup(self.vider_logs_v1)

    @staticmethod
    def vider_logs_v1():
        for h in list(v1.log.handlers):
            h.close()
            v1.log.removeHandler(h)

    def ancien_script(self):
        self.vider_logs_v1()
        with open(os.devnull, "w") as poubelle, mock.patch.object(sys, "stdout", poubelle):
            return v1.main(["-c", self.conf_v1, "--historique", self.historique, "--essais", "1", "--delai", "0"])

    def commande(self, *args):
        sortie, erreur = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
            code = cli.main(list(args) + ["--format", "json"])
        return code, json.loads(sortie.getvalue())

    def migrer(self):
        self.param = self.chemin("param", "production.jsonl")
        code, r = self.commande("--migrer-ancien", self.conf_v1, "--environnement", "production", "--base",
                                self.chemin("donnees", "production.db"), "--sortie", self.param, "--actives")
        self.assertEqual(code, 0, r)
        self.assertEqual(self.commande("--config", self.param, "--initialiser-base")[0], 0)

    def test_le_nouveau_moteur_ne_relivre_rien(self):
        self.assertEqual(self.ancien_script(), 0)
        self.assertEqual(sorted(comparer_dossiers.lister(self.dst)), ["a.csv", "b.csv", os.path.join("sous", "c.csv")])
        self.migrer()
        code, r = self.commande("--config", self.param, "--importer-historique", self.historique,
                                "--utilisateur", "benoit", "--commentaire", "recette")
        self.assertEqual((code, r["importees"], r["entrees"], r["sans_regle"]), (0, 3, 3, 0))
        regle = r["par_regle"]
        self.assertEqual(list(regle.values()), [3])
        ident = list(regle)[0]
        code, r = self.commande("--config", self.param, "--lancer-regle", ident)
        self.assertEqual((code, r["statut"], r["compteurs"]["livres"], r["compteurs"]["ignores"]), (0, "SUCCES", 0, 3))
        # sans l'import, le nouveau moteur aurait tout relivre (ecrase) : c'est ce que l'import evite
        self.assertEqual(comparer_dossiers.comparer(self.src, self.dst, "*.csv")["differents"], [])

    def test_sans_import_tout_serait_relivre(self):
        self.ancien_script()
        self.migrer()
        ident = self.commande("--config", self.param, "--etat")[1]["regles"][0]["id"]
        code, r = self.commande("--config", self.param, "--lancer-regle", ident)
        self.assertEqual(r["compteurs"]["livres"], 3)             # preuve de l'utilite de l'import

    def test_les_nouveautes_sont_livrees_comme_avant(self):
        self.ancien_script()
        self.migrer()
        self.commande("--config", self.param, "--importer-historique", self.historique, "--utilisateur", "benoit")
        ident = self.commande("--config", self.param, "--etat")[1]["regles"][0]["id"]
        self.ecrire("src/nouveau.csv", b"un nouveau")
        self.ecrire("src/b.csv", b"contenu B modifie")           # une version modifiee
        code, r = self.commande("--config", self.param, "--lancer-regle", ident)
        self.assertEqual((r["compteurs"]["livres"], r["compteurs"]["ignores"]), (2, 2))
        self.assertEqual(open(os.path.join(self.dst, "b.csv"), "rb").read(), b"contenu B modifie")
        # meme comportement que l'ancien script sur les memes donnees
        self.vider_logs_v1()
        os.remove(self.historique)
        self.assertEqual(self.ancien_script(), 0)
        self.assertEqual(comparer_dossiers.comparer(self.src, self.dst, "*.csv")["differents"], [])

    def test_fichier_pris_dans_la_cible_est_recopie_comme_avant(self):
        self.ancien_script()
        self.migrer()
        self.commande("--config", self.param, "--importer-historique", self.historique, "--utilisateur", "benoit")
        ident = self.commande("--config", self.param, "--etat")[1]["regles"][0]["id"]
        os.remove(os.path.join(self.dst, "a.csv"))               # le destinataire a perdu le fichier
        code, r = self.commande("--config", self.param, "--lancer-regle", ident)
        self.assertEqual(r["compteurs"]["livres"], 1)
        self.assertTrue(os.path.exists(os.path.join(self.dst, "a.csv")))


# =========================================================================== #
class TestComparateurDeDossiers(CasTemporaire):
    def arbo(self, nom, **fichiers):
        for relatif, contenu in fichiers.items():
            self.ecrire(os.path.join(nom, relatif.replace("__", os.sep)), contenu)

    def test_identiques(self):
        self.arbo("a", **{"x.csv": b"1", "sous__y.csv": b"22"})
        self.arbo("b", **{"x.csv": b"1", "sous__y.csv": b"22"})
        r = comparer_dossiers.comparer(self.chemin("a"), self.chemin("b"))
        self.assertEqual((len(r["identiques"]), r["seulement_a"], r["seulement_b"], r["differents"]), (2, [], [], []))

    def test_differences(self):
        self.arbo("a", **{"seul_a.csv": b"1", "taille.csv": b"123", "contenu.csv": b"abc", "ok.csv": b"1"})
        self.arbo("b", **{"seul_b.csv": b"1", "taille.csv": b"12", "contenu.csv": b"abd", "ok.csv": b"1"})
        r = comparer_dossiers.comparer(self.chemin("a"), self.chemin("b"))
        self.assertEqual((r["seulement_a"], r["seulement_b"], r["identiques"]), (["seul_a.csv"], ["seul_b.csv"], ["ok.csv"]))
        self.assertEqual({d["chemin"]: d["raison"] for d in r["differents"]},
                         {"taille.csv": "taille 3 / 2", "contenu.csv": "contenu different"})
        r = comparer_dossiers.comparer(self.chemin("a"), self.chemin("b"), contenu=False)
        self.assertEqual([d["chemin"] for d in r["differents"]], ["taille.csv"])

    def test_casse_masque_et_temporaires(self):
        self.arbo("a", **{"Fichier.CSV": b"1", "x.txt": b"1", "t.csv.copie_en_cours": b"1"})
        self.arbo("b", **{"fichier.csv": b"1"})
        self.assertEqual(comparer_dossiers.comparer(self.chemin("a"), self.chemin("b"), "*.csv")["seulement_a"], [])
        r = comparer_dossiers.comparer(self.chemin("a"), self.chemin("b"))
        self.assertEqual(r["seulement_a"], ["x.txt"])             # le temporaire est ignore

    def test_dates(self):
        self.arbo("a", **{"x.csv": b"1"})
        self.arbo("b", **{"x.csv": b"1"})
        os.utime(self.chemin("a", "x.csv"), (1_700_000_000, 1_700_000_000))
        os.utime(self.chemin("b", "x.csv"), (1_700_000_100, 1_700_000_100))
        self.assertEqual(comparer_dossiers.comparer(self.chemin("a"), self.chemin("b"))["differents"], [])
        r = comparer_dossiers.comparer(self.chemin("a"), self.chemin("b"), dates=True)
        self.assertEqual(r["differents"][0]["raison"], "date de modification differente")

    def test_ligne_de_commande(self):
        self.arbo("a", **{"x.csv": b"1"})
        self.arbo("b", **{"x.csv": b"1"})
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = comparer_dossiers.main([self.chemin("a"), self.chemin("b"), "--json", self.chemin("r.json")])
        self.assertEqual(code, 0)
        self.assertEqual(json.load(open(self.chemin("r.json")))["identiques"], ["x.csv"])
        self.arbo("b", **{"en_trop.csv": b"1"})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(comparer_dossiers.main([self.chemin("a"), self.chemin("b")]), 1)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(comparer_dossiers.main([self.chemin("a"), self.chemin("absent")]), 2)


class TestLanceurV2(CasTemporaire):
    def test_le_lanceur_equivaut_a_python_m_copie(self):
        chemin = self.chemin("production.jsonl")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write('{"version": 1, "environnement": "production", "base": "D:\\\\Copie\\\\production.db"}\n')
        resultat = subprocess.run([sys.executable, os.path.join(RACINE, "file_management_v2.py"), "--config", chemin,
                                   "--verifier", "--syntaxe-seule", "--format", "json"], cwd=self.racine,
                                  capture_output=True)
        self.assertEqual((resultat.returncode, resultat.stderr), (0, b""))
        self.assertTrue(json.loads(resultat.stdout.decode("utf-8"))["ok"])


if __name__ == "__main__":
    unittest.main()
