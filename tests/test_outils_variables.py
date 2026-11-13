"""Variables {outil:nom} : en-tete des outils, scan du dossier, index outils.json, controle G01, execution par le moteur
(dossier des outils par defaut ou deplace sous un autre nom) et commande --scanner-outils."""
import contextlib
import glob
import importlib
import io
import json
import os
import shutil
import sys
import unittest

from file_management import __main__ as principal
from file_management import outils
from file_management.controles import verifier_fichier
from file_management.outils import ErreurOutils, contenu_index, lire_entete, scanner
from tests.outils import CasTemporaire
from tests.test_outils_moteur import CasOutilsMoteur

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def entete(variable="mon_outil", description="Fait quelque chose.", parametres=()):
    lignes = ["# outil: %s" % variable, "# description: %s" % description]
    lignes += ["# parametre: %s" % p for p in parametres]
    return "\n".join(lignes) + "\n"


PARAMETRES = ("CHEMIN | facultatif | fichiers a traiter", "--sortie FICHIER | obligatoire | fichier a creer",
              "--recursif/-r | facultatif | descend dans les sous-dossiers")


# =========================================================================== #
class TestLireEntete(unittest.TestCase):
    def test_entete_valide(self):
        o, cause = lire_entete(entete(parametres=PARAMETRES) + '"""Doc."""\nimport os\n', "x\\mon_outil.py")
        self.assertIsNone(cause)
        self.assertEqual((o.variable, o.fichier, o.description), ("mon_outil", "x\\mon_outil.py", "Fait quelque chose."))
        self.assertEqual([(p.forme, p.obligatoire) for p in o.parametres],
                         [("CHEMIN", False), ("--sortie FICHIER", True), ("--recursif/-r", False)])
        self.assertEqual(o.parametres[1].noms, ("--sortie",))
        self.assertEqual(o.parametres[2].noms, ("--recursif", "-r"))
        self.assertEqual(o.parametres[1].description, "fichier a creer")

    def test_bom_ligne_shebang_et_commentaires_libres_toleres(self):
        texte = "\ufeff#!/usr/bin/env python\n# un commentaire libre\n" + entete() + "# fin\nimport os\n"
        o, cause = lire_entete(texte)
        self.assertIsNone(cause, cause)
        self.assertEqual(o.variable, "mon_outil")

    def test_la_description_d_un_parametre_peut_contenir_une_barre(self):
        o, cause = lire_entete(entete(parametres=("--x VAL | facultatif | a | b ou c",)))
        self.assertIsNone(cause)
        self.assertEqual(o.parametres[0].description, "a | b ou c")

    def test_pas_d_entete_n_est_pas_un_entete_invalide(self):
        for texte in ("", '"""Doc."""\nimport os\n', "import os\n# outil: x\n", "\n# outil: x\n# description: d\n"):
            o, cause = lire_entete(texte)
            self.assertIsNone(o)
            self.assertIn("pas d'en-tete", cause, texte)

    def test_entetes_invalides_avec_la_cause(self):
        cas = [
            (entete(variable="Zip"), "nom d'outil 'Zip' refuse"),
            (entete(variable="1zip"), "nom d'outil '1zip' refuse"),
            (entete(variable="a-b"), "nom d'outil 'a-b' refuse"),
            (entete(variable="x" * 65), "refuse"),
            ("# outil: a\n# outil: b\n# description: d\n", "plusieurs lignes '# outil:'"),
            ("# outil: a\n", "'# description:' absente"),
            ("# outil: a\n# description:\n", "'# description:' absente ou vide"),
            ("# outil: a\n# description: d\n# description: e\n", "plusieurs lignes '# description:'"),
            (entete(parametres=("--x | facultatif",)), "'# parametre:' invalide"),
            (entete(parametres=("--x | peut-etre | d",)), "'# parametre:' invalide"),
            (entete(parametres=(" | facultatif | d",)), "'# parametre:' invalide"),
            (entete(parametres=("--x A | facultatif | d", "--x B | obligatoire | e")), "declare deux fois : --x"),
            (entete(parametres=("--x A | facultatif | d", "-x/--x | facultatif | e")), "declare deux fois : --x"),
        ]
        for texte, attendu in cas:
            o, cause = lire_entete(texte)
            self.assertIsNone(o, texte)
            self.assertIn("en-tete invalide", cause, texte)
            self.assertIn(attendu, cause, texte)

    def test_l_entete_s_arrete_a_la_premiere_ligne_qui_n_est_pas_un_commentaire(self):
        o, cause = lire_entete("# commentaire\n\n" + entete())
        self.assertIsNone(o)
        o, cause = lire_entete(entete() + "\n# parametre: --x | obligatoire | tard\n")
        self.assertEqual(o.parametres, [])

    def test_lignes_au_dela_de_la_limite_ignorees(self):
        o, cause = lire_entete("# commentaire\n" * 250 + entete())
        self.assertIsNone(o)


# =========================================================================== #
class CasDossierOutils(CasTemporaire):
    def ecrire_outil(self, relatif, texte=None, **champs):
        self.ecrire(relatif, (texte if texte is not None else entete(**champs) + 'print("ok")\n').encode("utf-8"))
        return self.chemin(relatif)


class TestScanner(CasDossierOutils):
    def test_outils_retenus_tries_et_sous_dossiers(self):
        self.ecrire_outil("t/zebre.py", variable="zebre")
        self.ecrire_outil("t/domaine_b/b.py", variable="beta", parametres=PARAMETRES)
        self.ecrire_outil("t/domaine_a/profond/a.py", variable="alpha")
        scan = scanner(self.chemin("t"))
        self.assertEqual([o.variable for o in scan.outils], ["alpha", "beta", "zebre"])
        self.assertEqual([o.fichier for o in scan.outils],
                         [os.path.join("domaine_a", "profond", "a.py"), os.path.join("domaine_b", "b.py"), "zebre.py"])
        self.assertEqual(scan.non_retenus, [])
        self.assertEqual((scan.fichiers_python, scan.dossiers), (3, 4))
        self.assertEqual(scan.dossier, self.chemin("t"))

    def test_non_retenus_avec_leur_cause(self):
        self.ecrire_outil("t/bon.py", variable="bon")
        self.ecrire_outil("t/sans_entete.py", texte='"""Rien."""\n')
        self.ecrire_outil("t/invalide.py", variable="Mauvais Nom")
        self.ecrire_outil("t/doublon_b.py", variable="bon")
        self.ecrire("t/latin1.py", b"# outil: x\n# description: \xe9t\xe9\n")
        self.ecrire("t/notes.txt", b"pas un script")
        scan = scanner(self.chemin("t"))
        self.assertEqual([o.variable for o in scan.outils], ["bon"])
        causes = {n["fichier"]: n["cause"] for n in scan.non_retenus}
        self.assertEqual(sorted(causes), ["doublon_b.py", "invalide.py", "latin1.py", "sans_entete.py"])
        self.assertIn("pas d'en-tete", causes["sans_entete.py"])
        self.assertIn("nom d'outil 'Mauvais Nom' refuse", causes["invalide.py"])
        self.assertEqual(causes["doublon_b.py"], "la variable {outil:bon} est deja prise par bon.py")
        self.assertIn("UTF-8", causes["latin1.py"])
        self.assertEqual(scan.fichiers_python, 5)                       # notes.txt n'est pas un script

    def test_le_premier_dans_l_ordre_alphabetique_garde_la_variable(self):
        self.ecrire_outil("t/b/x.py", variable="meme")
        self.ecrire_outil("t/a/y.py", variable="meme")
        scan = scanner(self.chemin("t"))
        self.assertEqual(scan.outils[0].fichier, os.path.join("a", "y.py"))
        self.assertIn(os.path.join("a", "y.py"), scan.non_retenus[0]["cause"] + "")
        self.assertEqual(scan.non_retenus[0]["fichier"], os.path.join("b", "x.py"))

    def test_dossiers_ignores_init_et_caches(self):
        self.ecrire_outil("t/bon.py", variable="bon")
        self.ecrire_outil("t/__pycache__/c.py", variable="cache")
        self.ecrire_outil("t/_amorce/a.py", variable="amorce")
        self.ecrire_outil("t/.git/g.py", variable="git")
        self.ecrire_outil("t/__init__.py", variable="init")
        self.ecrire_outil("t/sous/__init__.py", variable="init2")
        scan = scanner(self.chemin("t"))
        self.assertEqual([o.variable for o in scan.outils], ["bon"])
        self.assertEqual(scan.non_retenus, [])

    def test_liens_vers_des_dossiers_non_suivis(self):
        self.ecrire_outil("t/bon.py", variable="bon")
        self.ecrire_outil("ailleurs/autre.py", variable="autre")
        try:
            os.symlink(self.chemin("ailleurs"), self.chemin("t", "lien"), target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques non permis sur ce poste")
        self.assertEqual([o.variable for o in scanner(self.chemin("t")).outils], ["bon"])

    def test_dossier_introuvable_ou_fichier(self):
        with self.assertRaises(ErreurOutils) as e:
            scanner(self.chemin("absent"))
        self.assertIn("dossier des outils introuvable", str(e.exception))
        with self.assertRaises(ErreurOutils):
            scanner(self.ecrire("fichier.txt"))

    def test_dossier_vide(self):
        os.makedirs(self.chemin("vide"))
        scan = scanner(self.chemin("vide"))
        self.assertEqual((scan.outils, scan.non_retenus, scan.fichiers_python), ([], [], 0))

    def test_seul_l_entete_est_lu(self):
        gros = entete(variable="gros") + "x = 1\n" * 200000
        self.ecrire_outil("t/gros.py", texte=gros)
        self.assertEqual([o.variable for o in scanner(self.chemin("t")).outils], ["gros"])

    def test_les_outils_du_depot_sont_tous_retenus(self):
        scan = scanner(os.path.join(RACINE, "outils"))
        domaines = {"compression", "controle", "conversion", "dates_attributs", "fichiers", "notification", "transfert",
                    "organisation", "recherche"}
        self.assertEqual({o.sous_dossier for o in scan.outils}, domaines)
        self.assertEqual(len(scan.outils), 38)
        self.assertEqual(scan.erreurs, [])
        for n in scan.non_retenus:                                     # seuls les scripts de recette restent
            self.assertTrue(os.sep not in n["fichier"], n)
            self.assertIn("pas d'en-tete", n["cause"])

    def test_les_modules_communs_se_declarent_bibliotheques(self):
        """Chaque module de outils/commun porte `# bibliotheque:` : ni outil, ni script « non retenu »."""
        scan = scanner(os.path.join(RACINE, "outils"))
        modules = sorted(f for f in os.listdir(os.path.join(RACINE, "outils", "commun"))
                         if f.endswith(".py") and f != "__init__.py")
        self.assertEqual(sorted(b["fichier"] for b in scan.bibliotheques),
                         [os.path.join("commun", m) for m in modules])
        self.assertGreaterEqual(len(modules), 12)
        for b in scan.bibliotheques:
            self.assertTrue(b["description"].strip(), b)
        self.assertEqual([o.variable for o in scan.outils if o.sous_dossier == "commun"], [])

    def test_bibliotheque_declaree_a_part_des_outils_et_des_non_retenus(self):
        self.ecrire_outil("t/a.py", variable="a")
        self.ecrire("t/commun/lib.py", b"# bibliotheque: ce que le module fournit\nimport os\n")
        scan = scanner(self.chemin("t"))
        self.assertEqual([o.variable for o in scan.outils], ["a"])
        self.assertEqual(scan.bibliotheques,
                         [{"fichier": os.path.join("commun", "lib.py"), "description": "ce que le module fournit"}])
        self.assertEqual(scan.non_retenus, [])
        self.assertEqual(scan.fichiers_python, 2)
        self.assertEqual([o["variable"] for o in json.loads(contenu_index(scan))["outils"]], ["a"])   # hors index
        self.assertEqual(scan.en_dict()["bibliotheques"], scan.bibliotheques)

    def test_bibliotheque_invalide(self):
        self.ecrire("t/vide.py", b"# bibliotheque:\nx = 1\n")
        self.ecrire("t/double.py", b"# bibliotheque: a\n# bibliotheque: b\n")
        self.ecrire("t/mixte.py", b"# outil: mixte\n# description: d\n# bibliotheque: b\n")
        scan = scanner(self.chemin("t"))
        self.assertEqual((scan.outils, scan.bibliotheques), ([], []))
        causes = {n["fichier"]: n["cause"] for n in scan.non_retenus}
        self.assertEqual(sorted(causes), ["double.py", "mixte.py", "vide.py"])
        self.assertIn("vide", causes["vide.py"])
        self.assertIn("plusieurs", causes["double.py"])
        self.assertIn("pas un outil", causes["mixte.py"])

    def test_un_commentaire_apres_le_code_n_est_pas_une_declaration(self):
        self.ecrire("t/tard.py", b"x = 1\n# bibliotheque: trop tard\n")
        scan = scanner(self.chemin("t"))
        self.assertEqual(scan.bibliotheques, [])
        self.assertEqual([n["fichier"] for n in scan.non_retenus], ["tard.py"])


class TestEnteteDesOutilsDuDepot(unittest.TestCase):
    """Garde-fou : l'en-tete de chaque outil dit la meme chose que son analyseur d'arguments."""

    def outils_du_depot(self):
        for chemin in sorted(glob.glob(os.path.join(RACINE, "outils", "*", "*.py"))):
            domaine, nom = os.path.basename(os.path.dirname(chemin)), os.path.basename(chemin)[:-3]
            if domaine in ("commun", "_amorce") or nom == "__init__":
                continue
            yield chemin, importlib.import_module("outils.%s.%s" % (domaine, nom)).OUTIL

    def test_variable_description_et_parametres_correspondent_a_l_analyseur(self):
        vus = 0
        for chemin, declare in self.outils_du_depot():
            with open(chemin, encoding="utf-8") as f:
                texte = f.read()
            o, cause = lire_entete(texte, chemin)
            self.assertIsNone(cause, chemin)
            self.assertEqual(o.variable, declare.nom, chemin)
            self.assertTrue(o.description, chemin)
            reels = {}
            for groupe in declare.parser()._action_groups:
                if groupe.title == "options communes":
                    continue
                for a in groupe._group_actions:
                    if a.option_strings:
                        reels[a.option_strings[0] if len(a.option_strings) == 1 else
                              next(s for s in a.option_strings if s.startswith("--"))] = bool(a.required)
                    else:
                        reels[a.metavar or a.dest.upper()] = bool(a.required) and a.nargs not in ("*", "?")
            attendus = {(p.noms[0] if len(p.noms) == 1 else next(n for n in p.noms if n.startswith("--"))): p.obligatoire
                        for p in o.parametres}
            self.assertEqual(attendus, {k: v for k, v in reels.items() if k not in ("--aide", "-h")}, chemin)
            for ligne in texte.split("\n")[:len(o.parametres) + 2]:
                ligne.encode("ascii")                                  # en-tete ASCII
            vus += 1
        self.assertEqual(vus, 38)

    def test_les_parametres_obligatoires_connus(self):
        index = {o.variable: o for o in scanner(os.path.join(RACINE, "outils")).outils}
        self.assertEqual([p.forme for p in index["zip_creer"].parametres if p.obligatoire], ["--sortie ARCHIVE.zip"])
        self.assertEqual([p.forme for p in index["archive_extraire"].parametres if p.obligatoire], ["--vers DOSSIER"])
        self.assertEqual([p.forme for p in index["inventaire"].parametres if p.obligatoire], ["--sortie FICHIER"])


# =========================================================================== #
class TestIndex(CasDossierOutils):
    def ecrire_index(self, dossier_param, dossier_configure="", dossier_outils=None):
        scan = scanner(dossier_outils or self.chemin("t"))
        os.makedirs(dossier_param, exist_ok=True)
        with open(os.path.join(dossier_param, outils.FICHIER_INDEX), "w", encoding="utf-8", newline="") as f:
            f.write(contenu_index(scan, dossier_configure, "admin"))

    def test_contenu_et_relecture(self):
        self.ecrire_outil("t/d/a.py", variable="a", parametres=PARAMETRES)
        scan = scanner(self.chemin("t"))
        texte = contenu_index(scan, self.chemin("t"), "benoit")
        document = json.loads(texte)
        self.assertEqual((document["version"], document["dossier_outils"], document["dossier_resolu"], document["scanne_par"]),
                         (1, self.chemin("t"), self.chemin("t"), "benoit"))
        self.assertRegex(document["scanne_le"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$")
        self.assertTrue(texte.endswith("}\n"))
        self.ecrire_index(self.chemin("param"), self.chemin("t"))
        index = outils.charger_index(self.chemin("param"))
        self.assertEqual(sorted(index.outils), ["a"])
        self.assertEqual(index.dossier, self.chemin("t"))
        self.assertEqual(index.chemin_outil(index.outils["a"]), self.chemin("t", "d", "a.py"))
        self.assertEqual([(p.forme, p.obligatoire) for p in index.outils["a"].parametres],
                         [("CHEMIN", False), ("--sortie FICHIER", True), ("--recursif/-r", False)])
        self.assertEqual(index.scanne_par, "admin")

    def test_dossier_vide_dans_l_index_veut_dire_le_dossier_outils_du_moteur(self):
        self.ecrire_outil("t/a.py", variable="a")
        self.ecrire_index(self.chemin("param"), "")
        index = outils.charger_index(self.chemin("param"))
        self.assertEqual(index.dossier_configure, "")
        self.assertEqual(index.dossier, outils.dossier_par_defaut())
        self.assertEqual(os.path.basename(outils.dossier_par_defaut()), "outils")
        self.assertEqual(os.path.dirname(outils.dossier_par_defaut()), RACINE)

    def test_absent_illisible_et_version_inconnue(self):
        os.makedirs(self.chemin("param"))
        self.assertIsNone(outils.charger_index(self.chemin("param")))
        for contenu, attendu in ((b"{pas du json", "illisible"), (b'{"version": 2, "outils": []}', "version 2"),
                                 (b'{"version": 1}', "contenu invalide"), (b'{"version": 1, "outils": [{"x": 1}]}', "contenu invalide"),
                                 (b"[]", "contenu invalide")):
            self.ecrire("param/outils.json", contenu)
            with self.assertRaises(ErreurOutils) as e:
                outils.charger_index(self.chemin("param"))
            self.assertIn(attendu, str(e.exception), contenu)

    def test_index_avec_bom_utf8(self):
        self.ecrire_outil("t/a.py", variable="a")
        self.ecrire_index(self.chemin("param"))
        chemin = self.chemin("param", "outils.json")
        with open(chemin, "rb") as f:
            brut = f.read()
        with open(chemin, "wb") as f:
            f.write(b"\xef\xbb\xbf" + brut)
        self.assertEqual(sorted(outils.charger_index(self.chemin("param")).outils), ["a"])

    def test_le_cache_suit_le_fichier(self):
        self.ecrire_outil("t/a.py", variable="a")
        self.ecrire_index(self.chemin("param"))
        self.assertEqual(sorted(outils.index_de(self.chemin("param")).outils), ["a"])
        self.assertIs(outils.index_de(self.chemin("param")), outils.index_de(self.chemin("param")))
        self.ecrire_outil("t/b.py", variable="b")
        self.ecrire_index(self.chemin("param"))
        self.assertEqual(sorted(outils.index_de(self.chemin("param")).outils), ["a", "b"])
        os.remove(self.chemin("param", "outils.json"))
        self.assertIsNone(outils.index_de(self.chemin("param")))

    def test_resoudre(self):
        self.ecrire_outil("t/a.py", variable="a")
        self.ecrire_index(self.chemin("param"), self.chemin("t"))
        index = outils.charger_index(self.chemin("param"))
        debut, message = outils.resoudre("a", index)
        self.assertEqual((debut, message), ([sys.executable, self.chemin("t", "a.py")], None))
        debut, message = outils.resoudre("b", index)
        self.assertIsNone(debut)
        self.assertEqual(message, "outil inconnu : {outil:b} (outils indexes : a)")
        os.remove(self.chemin("t", "a.py"))
        self.assertIn("introuvable", outils.resoudre("a", index)[1])
        self.assertIn("aucun index", outils.resoudre("a", None)[1])

    def test_parametres_manquants(self):
        self.ecrire_outil("t/a.py", variable="a", parametres=PARAMETRES)
        o = scanner(self.chemin("t")).outils[0]
        self.assertEqual(outils.parametres_manquants(o, ["x"]), ["--sortie FICHIER"])
        self.assertEqual(outils.parametres_manquants(o, ["--sortie", "f"]), [])
        self.assertEqual(outils.parametres_manquants(o, ["--sortie=f"]), [])
        self.assertEqual(outils.parametres_manquants(o, ["--sortie-autre", "f"]), ["--sortie FICHIER"])


# =========================================================================== #
class CasOutilsVariables(CasOutilsMoteur, CasDossierOutils):
    """Regles du moteur avec un index d'outils dans le dossier de parametrage."""

    def setUp(self):
        super().setUp()
        self.param = self.chemin("param")
        os.makedirs(self.param)
        self.entete.dossier_parametrage = self.param

    def indexer(self, dossier_outils, configure=None):
        scan = scanner(dossier_outils)
        with open(os.path.join(self.param, outils.FICHIER_INDEX), "w", encoding="utf-8", newline="") as f:
            f.write(contenu_index(scan, dossier_outils if configure is None else configure, "essai"))
        return scan

    def commande(self, *elements, timeout_sec=60):
        return {"commande": list(elements), "timeout_sec": timeout_sec}


class TestExecutionAvecVariableOutil(CasOutilsVariables):
    def test_un_outil_du_depot_par_sa_variable(self):
        self.indexer(os.path.join(RACINE, "outils"), "")                   # '' = dossier outils du moteur
        self.source("a.csv", b"1;A\n")
        bilan = self.lancer(self.regle(programmes={"avant_lot": self.commande("{outil:empreinte}", "--afficher", "{liste}")}))
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 1), bilan.motif)
        appel = self.evenements_programme("avant_lot")[0]
        self.assertEqual(appel["commande"][0], sys.executable)
        self.assertEqual(appel["commande"][1], os.path.join(RACINE, "outils", "controle", "empreinte.py"))
        self.assertEqual(appel["code"], 0)
        brutes = self.controler_lignes_de_l_outil("empreinte")
        self.assertEqual(brutes[-1]["context"]["statut"], "SUCCES")

    def test_dossier_des_outils_deplace_sous_un_autre_nom(self):
        """Le moteur transmet COPIE_RACINE_MOTEUR : l'outil retrouve journal_si et son socle ailleurs que sous le moteur."""
        ailleurs = self.chemin("partage", "scripts_dsi")
        shutil.copytree(os.path.join(RACINE, "outils"), ailleurs, ignore=shutil.ignore_patterns("__pycache__"))
        self.indexer(ailleurs)
        self.source("a.csv", b"1;A\n")
        bilan = self.lancer(self.regle(programmes={"avant_lot": self.commande("{outil:empreinte}", "--afficher", "{liste}")}))
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 1), bilan.motif)
        appel = self.evenements_programme("avant_lot")[0]
        self.assertEqual(appel["commande"][1], os.path.join(ailleurs, "controle", "empreinte.py"))
        self.controler_lignes_de_l_outil("empreinte")                          # journalise dans le fichier de la regle

    def test_changer_le_dossier_et_scanner_de_nouveau_suffit(self):
        premier = self.chemin("v1")
        self.ecrire_outil("v1/outil_a.py", texte=entete(variable="faire") + "import sys\nprint('version 1')\n")
        self.indexer(premier)
        self.source("a.csv")
        self.lancer(self.regle(programmes={"avant_lot": self.commande("{outil:faire}")}))
        self.assertIn("version 1", self.evenements_programme("avant_lot")[0]["sortie"])
        self.ecrire_outil("v2/place_differente/autre_nom.py", texte=entete(variable="faire") + "print('version 2')\n")
        self.indexer(self.chemin("v2"))
        self.source("b.csv")
        self.lancer(self.regle(programmes={"avant_lot": self.commande("{outil:faire}")}))
        self.assertIn("version 2", self.evenements_programme("avant_lot")[-1]["sortie"])

    def test_les_autres_variables_restent_remplacees_apres_l_outil(self):
        self.ecrire_outil("t/echo.py", texte=entete(variable="echo", parametres=("TEXTE | facultatif | texte",))
                   + "import sys\nprint('|'.join(sys.argv[1:]))\n")
        self.indexer(self.chemin("t"))
        self.source("a.csv")
        self.lancer(self.regle(programmes={"avant_lot": self.commande("{outil:echo}", "regle={regle}", "{environnement}")}))
        self.assertIn("regle=r1|production", self.evenements_programme("avant_lot")[0]["sortie"])

    def test_outil_inconnu_apres_indexation_arrete_la_regle_proprement(self):
        self.indexer(os.path.join(RACINE, "outils"), "")
        prog = self.regle(programmes={"avant_lot": self.commande("{outil:empreinte}", "--afficher")})
        self.ecrire_outil("t/x.py", variable="x")
        self.indexer(self.chemin("t"))                                         # l'index ne connait plus 'empreinte'
        self.source("a.csv")
        bilan = self.lancer(prog)
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "programme_avant_lot"))
        self.assertIn("outil inconnu : {outil:empreinte} (outils indexes : x)", bilan.motif)
        self.assertEqual(self.livres(), [])

    def test_fichier_de_l_outil_disparu(self):
        self.ecrire_outil("t/x.py", variable="x")
        self.indexer(self.chemin("t"))
        os.remove(self.chemin("t", "x.py"))
        self.source("a.csv")
        bilan = self.lancer(self.regle(programmes={"avant_lot": self.commande("{outil:x}")}))
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "programme_avant_lot"))
        self.assertIn("est introuvable", bilan.motif)
        self.assertIn("scanner de nouveau", bilan.motif)

    def test_aucun_index(self):
        self.source("a.csv")
        bilan = self.lancer(self.regle(programmes={"avant_lot": self.commande("{outil:x}")}))
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "programme_avant_lot"))
        self.assertIn("aucun index des outils", bilan.motif)

    def test_variable_d_environnement_pour_les_outils(self):
        self.ecrire_outil("t/e.py", texte=entete(variable="env") + "import os\nprint('RACINE=' + os.environ['COPIE_RACINE_MOTEUR'])\n")
        self.indexer(self.chemin("t"))
        self.source("a.csv")
        self.lancer(self.regle(programmes={"avant_lot": self.commande("{outil:env}")}))
        self.assertIn("RACINE=" + RACINE, self.evenements_programme("avant_lot")[0]["sortie"])

    def test_tous_les_points_d_appel_acceptent_une_variable_d_outil(self):
        self.ecrire_outil("t/n.py", texte=entete(variable="note") + "import os\nopen(os.environ['COPIE_DOSSIER_TRAVAIL'] + '/pts.txt', 'a').write(os.environ['COPIE_POINT_APPEL'] + '\\n')\n")
        self.indexer(self.chemin("t"))
        self.source("a.csv")
        c = self.commande("{outil:note}")
        self.lancer(self.regle(programmes={"avant_lot": c, "avant_fichier": c, "apres_fichier": c, "apres_lot": c}))
        with open(self.chemin("travail", "pts.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read().split(), ["avant_lot", "avant_fichier", "apres_fichier", "apres_lot"])

    def test_sur_erreur_avec_une_variable_d_outil(self):
        self.ecrire_outil("t/n.py", texte=entete(variable="note") + "import os\nopen(os.environ['COPIE_DOSSIER_TRAVAIL'] + '/erreur.txt', 'w').write(os.environ['COPIE_POINT_APPEL'])\n")
        self.indexer(self.chemin("t"))
        self.source("a.csv")
        mauvais = {"commande": [sys.executable, "-c", "raise SystemExit(2)"], "timeout_sec": 30}
        bilan = self.lancer(self.regle(programmes={"avant_lot": mauvais, "sur_erreur": self.commande("{outil:note}")}))
        self.assertEqual(bilan.statut, "ERREUR")
        with open(self.chemin("travail", "erreur.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "sur_erreur")


# =========================================================================== #
class TestParametrageDesVariablesOutil(CasOutilsVariables):
    """Controles du fichier de parametrage (G01) : lecture et controles croises."""

    def fichier(self, programmes, nom="production.jsonl"):
        entete_json = {"version": 1, "environnement": "production", "base": self.chemin("base.db")}
        regle = {"id": "r1", "source": self.chemin("s"), "cible": self.chemin("c"), "mode": "copie",
                 "planification": {"type": "quotidien", "heure": "07:00"}, "programmes": programmes}
        chemin = os.path.join(self.param, nom)
        with open(chemin, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(entete_json) + "\n" + json.dumps(regle) + "\n")
        return chemin

    def verifier(self, programmes):
        p, rapport = verifier_fichier(self.fichier(programmes))
        return rapport

    def messages(self, rapport):
        return [m for m in rapport.en_texte().split("\n") if "G01" in m]

    def test_syntaxe_valide_et_index_complet(self):
        self.ecrire_outil("t/x.py", variable="x", parametres=PARAMETRES)
        self.indexer(self.chemin("t"))
        rapport = self.verifier({"avant_lot": self.commande("{outil:x}", "--sortie", "{cible}", "{liste}")})
        self.assertTrue(rapport.ok, rapport.en_texte())

    def test_parametre_obligatoire_manquant(self):
        self.ecrire_outil("t/x.py", variable="x", parametres=PARAMETRES)
        self.indexer(self.chemin("t"))
        rapport = self.verifier({"avant_lot": self.commande("{outil:x}", "{liste}")})
        self.assertFalse(rapport.ok)
        self.assertIn("le parametre --sortie FICHIER de l'outil {outil:x} est obligatoire", rapport.en_texte())
        self.assertIn("programmes.avant_lot.commande", rapport.en_texte())
        self.assertTrue(self.verifier({"avant_lot": self.commande("{outil:x}", "--sortie=f")}).ok)

    def test_outil_inconnu_cite_les_outils_connus(self):
        self.ecrire_outil("t/x.py", variable="x")
        self.ecrire_outil("t/y.py", variable="y")
        self.indexer(self.chemin("t"))
        rapport = self.verifier({"avant_lot": self.commande("{outil:zzz}")})
        self.assertFalse(rapport.ok)
        self.assertIn("outil inconnu : {outil:zzz} (outils indexes : x, y)", rapport.en_texte())

    def test_aucun_index_ou_index_illisible(self):
        rapport = self.verifier({"avant_lot": self.commande("{outil:x}")})
        self.assertFalse(rapport.ok)
        self.assertIn("aucun index des outils", rapport.en_texte())
        self.ecrire("param/outils.json", b"{casse")
        rapport = self.verifier({"avant_lot": self.commande("{outil:x}")})
        self.assertIn("outils.json illisible", rapport.en_texte())

    def test_l_index_n_est_pas_lu_sans_variable_d_outil(self):
        self.ecrire("param/outils.json", b"{casse")
        rapport = self.verifier({"avant_lot": self.commande(sys.executable, "-c", "pass")})
        self.assertTrue(rapport.ok, rapport.en_texte())

    def test_syntaxe_de_la_variable(self):
        self.ecrire_outil("t/x.py", variable="x")
        self.indexer(self.chemin("t"))
        cas = [
            (("{outil:x}suite",), "doit etre seul dans le premier element"),
            (("python", "{outil:x}"), "n'est permis que comme premier element"),
            (("{outil:x}", "a{outil:x}"), "n'est permis que comme premier element"),
            (("{outil:X}",), "nom d'outil invalide"),
            (("{outil:}",), "nom d'outil invalide"),
            (("{outil:x}", "{inconnue}"), "variable {inconnue} inconnue"),
        ]
        for elements, attendu in cas:
            rapport = self.verifier({"avant_lot": self.commande(*elements)})
            self.assertFalse(rapport.ok, elements)
            self.assertIn(attendu, rapport.en_texte(), elements)

    def test_les_variables_de_fichier_restent_refusees_a_avant_lot(self):
        self.ecrire_outil("t/x.py", variable="x")
        self.indexer(self.chemin("t"))
        rapport = self.verifier({"avant_lot": self.commande("{outil:x}", "{fichier}")})
        self.assertFalse(rapport.ok)
        self.assertIn("variable {fichier} inconnue ou sans objet", rapport.en_texte())

    def test_brouillon_verifie_avec_le_dossier_du_parametrage(self):
        """L'interface verifie un brouillon range dans un sous-dossier (.brouillons\<guid>) : l'index des outils
        est celui du dossier de parametrage, donne par --dossier-parametrage."""
        self.ecrire_outil("t/x.py", variable="x")
        self.indexer(self.chemin("t"))
        reel = self.fichier({"avant_lot": self.commande("{outil:x}")})
        brouillon = os.path.join(self.param, ".brouillons", "abc", "production.jsonl")
        os.makedirs(os.path.dirname(brouillon))
        shutil.copy(reel, brouillon)
        self.assertFalse(verifier_fichier(brouillon)[1].ok)                                # index cherche a cote du brouillon
        self.assertIn("aucun index des outils", verifier_fichier(brouillon)[1].en_texte())
        self.assertTrue(verifier_fichier(brouillon, None, self.param)[1].ok)
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = principal.main(["--config", brouillon, "--verifier", "--syntaxe-seule", "--format", "json",
                                   "--dossier-parametrage", self.param])
        self.assertEqual(code, 0, sortie.getvalue())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            principal.main(["--config", reel, "--dossier-parametrage", self.param])    # sans --verifier : refuse

    def test_verification_complete_controle_aussi_le_fichier_de_l_outil(self):
        self.ecrire_outil("t/x.py", variable="x")
        self.indexer(self.chemin("t"))
        os.remove(self.chemin("t", "x.py"))
        chemin = self.fichier({"avant_lot": self.commande("{outil:x}")})
        self.assertTrue(verifier_fichier(chemin)[1].ok)                      # syntaxe et index : bon
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = principal.main(["--config", chemin, "--verifier", "--syntaxe-seule", "--format", "json"])
        self.assertEqual(code, 0, sortie.getvalue())
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = principal.main(["--config", chemin, "--verifier", "--format", "json"])
        self.assertEqual(code, 2)
        self.assertIn("est introuvable", sortie.getvalue())
        self.assertIn("scanner de nouveau", sortie.getvalue())


# =========================================================================== #
class TestCommandeScannerOutils(CasDossierOutils):
    def lancer_cli(self, *argv):
        sortie, erreur = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
            try:
                code = principal.main(list(argv))
            except SystemExit as e:
                code = e.code
        return code, sortie.getvalue(), erreur.getvalue()

    def test_json_sans_config(self):
        self.ecrire_outil("t/a.py", variable="a", parametres=PARAMETRES)
        self.ecrire_outil("t/b.py", texte="pas d'en-tete\n")
        code, sortie, erreur = self.lancer_cli("--scanner-outils", "--dossier-outils", self.chemin("t"), "--utilisateur",
                                               "DOM\\admin", "--format", "json")
        self.assertEqual(code, 0, erreur)
        r = json.loads(sortie)
        self.assertTrue(r["ok"])
        self.assertEqual((r["dossier"], r["dossier_configure"]), (self.chemin("t"), self.chemin("t")))
        self.assertEqual([o["variable"] for o in r["outils"]], ["a"])
        self.assertEqual(r["non_retenus"][0]["fichier"], "b.py")
        self.assertIn("1 outil(s) retenu(s), 1 script(s) non retenu(s)", r["message"])
        self.assertEqual(r["bibliotheques"], [])
        document = json.loads(r["contenu_index"])
        self.assertEqual((document["scanne_par"], document["dossier_outils"]), ("DOM\\admin", self.chemin("t")))
        self.assertEqual(document["outils"][0]["parametres"][1]["obligatoire"], True)
        self.assertEqual(sorted(os.listdir(self.chemin("t"))), ["a.py", "b.py"])      # rien n'est ecrit

    def test_sans_dossier_c_est_le_dossier_outils_du_moteur(self):
        code, sortie, erreur = self.lancer_cli("--scanner-outils", "--format", "json")
        self.assertEqual(code, 0, erreur)
        r = json.loads(sortie)
        self.assertEqual((r["dossier"], r["dossier_configure"]), (os.path.join(RACINE, "outils"), ""))
        self.assertEqual(len(r["outils"]), 38)
        self.assertEqual(json.loads(r["contenu_index"])["dossier_outils"], "")

    def test_dossier_introuvable_code_2(self):
        code, sortie, erreur = self.lancer_cli("--scanner-outils", "--dossier-outils", self.chemin("absent"), "--format", "json")
        self.assertEqual(code, 2)
        r = json.loads(sortie)
        self.assertFalse(r["ok"])
        self.assertIn("dossier des outils introuvable", r["message"])

    def test_texte(self):
        self.ecrire_outil("t/a.py", variable="a")
        self.ecrire_outil("t/b.py", texte="x\n")
        code, sortie, erreur = self.lancer_cli("--scanner-outils", "--dossier-outils", self.chemin("t"))
        self.assertEqual(code, 0, erreur)
        self.assertIn("1 outil(s) retenu(s)", sortie)
        self.assertIn("{outil:a}  a.py", sortie)
        self.assertIn("non retenu : b.py : pas d'en-tete", sortie)

    def test_dossier_outils_seul_est_refuse(self):
        code, sortie, erreur = self.lancer_cli("--dossier-outils", self.chemin("t"), "--config", "x.jsonl")
        self.assertEqual(code, 2)
        self.assertIn("--dossier-outils s'utilise avec --scanner-outils", erreur)


if __name__ == "__main__":
    unittest.main()
