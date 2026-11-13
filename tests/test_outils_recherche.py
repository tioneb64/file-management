"""Boite a outils : recherche (par nom, dans le contenu, remplacement en masse, doublons)."""
import csv
import json
import os
import unittest

from outils.recherche import chercher_contenu, chercher_nom, doublons_trouver, remplacer_contenu
from tests.boite_outils import CasOutil


class TestChercherNom(CasOutil):
    def arbre_de_recherche(self):
        self.ecrire("d/a.csv")
        self.ecrire("d/B.CSV")
        self.ecrire("d/rapport_2026.txt")
        self.ecrire("d/sous/c.csv", b"123456789", age_jours=40)
        self.ecrire("d/sous/profond/d.csv.copie_en_cours")
        self.ecrire("d/dossier_csv/x.bin")

    def noms(self):
        return sorted(l.replace("\\", "/").split("/d/")[1] for l in self.sortie.splitlines() if "/d" in l.replace("\\", "/"))

    def test_joker_insensible_a_la_casse_et_recursif(self):
        self.arbre_de_recherche()
        self.assertEqual(self.lancer(chercher_nom, self.chemin("d"), "--nom", "*.csv"), 0)
        self.assertEqual(self.noms(), ["B.CSV", "a.csv", "sous/c.csv"])         # le .copie_en_cours est ignore
        self.assertIn("trouves=3", self.sortie)
        lignes = self.controler_journal("chercher_nom", "SUCCES")
        self.assertEqual(self.lignes("recherche_terminee")[0]["resultats"], 3)

    def test_expression_reguliere_et_type_dossier(self):
        self.arbre_de_recherche()
        self.assertEqual(self.lancer(chercher_nom, self.chemin("d"), "--regex", r"^rapport_\d{4}\.txt$"), 0)
        self.assertEqual(self.noms(), ["rapport_2026.txt"])
        self.assertEqual(self.lancer(chercher_nom, self.chemin("d"), "--regex", "CSV", "--ignorer-casse", "--type", "dossier"), 0)
        self.assertEqual(self.noms(), ["dossier_csv"])
        self.assertEqual(self.lancer(chercher_nom, self.chemin("d"), "--nom", "s*", "--type", "tout"), 0)
        self.assertEqual(self.noms(), ["sous"])

    def test_filtres_de_taille_d_age_et_recursion(self):
        self.arbre_de_recherche()
        self.assertEqual(self.lancer(chercher_nom, self.chemin("d"), "--nom", "*.csv", "--taille-min", "8"), 0)
        self.assertEqual(self.noms(), ["sous/c.csv"])
        self.lancer(chercher_nom, self.chemin("d"), "--nom", "*.csv", "--plus-ancien-que", "30")
        self.assertEqual(self.noms(), ["sous/c.csv"])
        self.lancer(chercher_nom, self.chemin("d"), "--nom", "*.csv", "--plus-recent-que", "30")
        self.assertEqual(self.noms(), ["B.CSV", "a.csv"])
        self.lancer(chercher_nom, self.chemin("d"), "--nom", "*.csv", "--sans-recursion")
        self.assertEqual(self.noms(), ["B.CSV", "a.csv"])
        self.lancer(chercher_nom, self.chemin("d"), "--nom", "*.csv", "--taille-max", "8")
        self.assertEqual(self.noms(), ["B.CSV", "a.csv"])

    def test_liste_en_sortie_et_simulation(self):
        self.arbre_de_recherche()
        liste = self.chemin("trouves.txt")
        self.assertEqual(self.lancer(chercher_nom, self.chemin("d"), "--nom", "*.csv", "--sortie-liste", liste), 0)
        with open(liste, encoding="utf-8") as f:
            self.assertEqual(sorted(os.path.basename(l.strip()) for l in f), ["B.CSV", "a.csv", "c.csv"])
        os.remove(liste)
        self.assertEqual(self.lancer(chercher_nom, self.chemin("d"), "--nom", "*.csv", "--sortie-liste", liste, "--simulation"), 0)
        self.assertFalse(os.path.exists(liste))                      # la recherche ne modifie rien ; la liste est une ecriture

    def test_max_affiches(self):
        for i in range(5):
            self.ecrire("d/f%d.txt" % i)
        self.lancer(chercher_nom, self.chemin("d"), "--nom", "*.txt", "--max-affiches", "2")
        self.assertIn("... et 3 autre(s)", self.sortie)
        self.assertEqual(len(self.lignes("recherche_terminee")), 1)

    def test_aucun_resultat_rien_a_faire(self):
        self.arbre_de_recherche()
        self.assertEqual(self.lancer(chercher_nom, self.chemin("d"), "--nom", "*.xyz"), 0)
        self.assertEqual(self.lancer(chercher_nom, self.chemin("d"), "--nom", "*.xyz", "--code-si-rien", "1"), 1)
        self.controler_journal("chercher_nom", "RIEN")

    def test_parametres_invalides_et_dossier_introuvable(self):
        self.assertEqual(self.lancer(chercher_nom, self.chemin("d")), 3)
        self.assertEqual(self.lancer(chercher_nom, self.chemin("d"), "--regex", "("), 3)
        self.assertEqual(self.lancer(chercher_nom, self.chemin("d"), "--nom", "*", "--taille-min", "grand"), 3)
        self.assertEqual(self.lancer(chercher_nom, self.chemin("absent"), "--nom", "*"), 2)
        self.assertIn("FILE_NOT_FOUND", [b["error"]["type"] for b in self.erreurs_journal()])

    def test_un_fichier_designe_est_teste_sur_son_nom(self):
        """Dans une regle, la liste du lot (fichiers) est designee a la place d'un dossier."""
        a, b = self.ecrire("d/a.csv"), self.ecrire("d/b.log")
        self.assertEqual(self.lancer(chercher_nom, a, b, "--nom", "*.csv"), 0)
        self.assertEqual(self.noms(), ["a.csv"])
        self.assertEqual(self.lancer(chercher_nom, b, "--nom", "*.csv", "--code-si-rien", "1"), 1)
        liste = self.ecrire("liste.txt", os.linesep.join([a, b, ""]).encode("utf-8"))
        self.assertEqual(self.lancer(chercher_nom, "--nom", "*.log", env={"COPIE_LISTE": liste}), 0)
        self.assertEqual(self.noms(), ["b.log"])

    def test_variable_copie_source(self):
        self.arbre_de_recherche()
        self.assertEqual(self.lancer(chercher_nom, "--nom", "*.txt", env={"COPIE_SOURCE": self.chemin("d")}), 0)
        self.assertEqual(self.noms(), ["rapport_2026.txt"])


class TestChercherContenu(CasOutil):
    def test_texte_dans_plusieurs_encodages(self):
        self.ecrire("d/utf8.txt", "premiere\ncafé au lait\n".encode("utf-8"))
        self.ecrire("d/ansi.txt", "premiere\ncafé noir\n".encode("cp1252"))
        self.ecrire("d/utf16.txt", "café glace\n".encode("utf-16"))
        self.ecrire("d/bom.txt", b"\xef\xbb\xbfcaf\xc3\xa9 bom\r\n")
        self.ecrire("d/autre.txt", b"rien ici\n")
        self.ecrire("d/binaire.bin", b"caf\xc3\xa9\x00\x01\x02")
        self.assertEqual(self.lancer(chercher_contenu, self.chemin("d"), "--texte", "café"), 0, self.erreur)
        sortie = self.sortie.replace("\\", "/")
        for nom, texte in (("utf8.txt:2:café au lait", 1), ("ansi.txt:2:café noir", 1), ("utf16.txt:1:café glace", 1),
                           ("bom.txt:1:café bom", 1)):
            self.assertIn(nom, sortie)
        self.assertNotIn("binaire.bin", sortie)
        self.assertNotIn("autre.txt", sortie)
        self.assertIn("fichiers_trouves=4", self.sortie)
        self.assertIn("binaires_ignores=1", self.sortie)
        self.controler_journal("chercher_contenu", "SUCCES")
        encodages = {os.path.basename(l["fichier"]): l["encodage"] for l in self.lignes("contenu_trouve")}
        self.assertEqual(encodages, {"utf8.txt": "utf-8", "ansi.txt": "cp1252", "utf16.txt": "utf-16", "bom.txt": "utf-8-sig"})

    def test_expression_reguliere_casse_et_encodage_impose(self):
        self.ecrire("a.txt", b"Facture F-2026-001\nautre\nfacture f-2025-777\n")
        self.assertEqual(self.lancer(chercher_contenu, self.chemin("a.txt"), "--regex", r"F-\d{4}-\d+"), 0)
        self.assertEqual(self.sortie.count("a.txt:"), 1)
        self.lancer(chercher_contenu, self.chemin("a.txt"), "--regex", r"F-\d{4}-\d+", "--ignorer-casse")
        self.assertEqual(self.sortie.count("a.txt:"), 2)
        self.ecrire("b.txt", "été\n".encode("latin-1"))
        self.lancer(chercher_contenu, self.chemin("b.txt"), "--texte", "été", "--encodage", "latin-1")
        self.assertIn("b.txt:1", self.sortie)

    def test_liste_des_fichiers_et_sortie(self):
        self.ecrire("d/a.txt", b"cle=1\ncle=2\n")
        self.ecrire("d/b.txt", b"rien\n")
        liste = self.chemin("liste.txt")
        self.lancer(chercher_contenu, self.chemin("d"), "--texte", "cle", "--liste-fichiers-seulement", "--sortie-liste", liste)
        self.assertEqual(self.sortie.count("a.txt"), 1)
        with open(liste, encoding="utf-8") as f:
            self.assertEqual([os.path.basename(l.strip()) for l in f], ["a.txt"])
        self.assertEqual(self.lignes("contenu_trouve")[0]["lignes"], 2)
        os.remove(liste)
        self.lancer(chercher_contenu, self.chemin("d"), "--texte", "cle", "--sortie-liste", liste, "--simulation")
        self.assertFalse(os.path.exists(liste))

    def test_recursif_masque_et_rien_trouve(self):
        self.ecrire("d/a.log", b"erreur\n")
        self.ecrire("d/s/b.log", b"erreur\n")
        self.ecrire("d/s/c.txt", b"erreur\n")
        self.lancer(chercher_contenu, self.chemin("d"), "--texte", "erreur", "-r", "--masque", "*.log")
        self.assertEqual(self.sortie.count(".log:1:erreur"), 2)
        self.assertEqual(self.lancer(chercher_contenu, self.chemin("d"), "--texte", "inconnu", "-r", "--code-si-rien", "1"), 1)

    def test_parametres_invalides_et_fichier_introuvable(self):
        self.assertEqual(self.lancer(chercher_contenu, self.chemin("d")), 3)
        self.assertEqual(self.lancer(chercher_contenu, self.chemin("d"), "--texte", "a", "--regex", "b"), 3)
        self.assertEqual(self.lancer(chercher_contenu, self.chemin("d"), "--regex", "("), 3)
        self.assertEqual(self.lancer(chercher_contenu, self.chemin("d"), "--texte", "a", "--encodage", "inconnu"), 3)
        self.assertEqual(self.lancer(chercher_contenu, self.chemin("absent.txt"), "--texte", "a"), 2)
        self.assertIn("FILE_NOT_FOUND", [b["error"]["type"] for b in self.erreurs_journal()])

    def test_max_affiches(self):
        self.ecrire("a.txt", b"x\n" * 10)
        self.lancer(chercher_contenu, self.chemin("a.txt"), "--texte", "x", "--max-affiches", "3")
        self.assertEqual(self.sortie.count("a.txt:"), 3)
        self.assertIn("non affiches", self.sortie)
        self.assertEqual(self.lignes("contenu_trouve")[0]["lignes"], 10)


class TestRemplacerContenu(CasOutil):
    def test_conserve_encodage_bom_et_fins_de_ligne(self):
        utf8 = self.ecrire("utf8.txt", "café ancien\r\nligne ancien\n".encode("utf-8"))
        bom = self.ecrire("bom.txt", b"\xef\xbb\xbfancien\r\n")
        ansi = self.ecrire("ansi.txt", "café ancien\r\n".encode("cp1252"))
        utf16 = self.ecrire("utf16.txt", "ancien\r\n".encode("utf-16"))
        code = self.lancer(remplacer_contenu, utf8, bom, ansi, utf16, "--chercher", "ancien", "--remplacer", "nouveau")
        self.assertEqual(code, 0, self.erreur)
        self.assertEqual(self.lire(utf8), "café nouveau\r\nligne nouveau\n".encode("utf-8"))
        self.assertEqual(self.lire(bom), b"\xef\xbb\xbfnouveau\r\n")
        self.assertEqual(self.lire(ansi), "café nouveau\r\n".encode("cp1252"))
        self.assertEqual(self.lire(utf16), "nouveau\r\n".encode("utf-16"))
        self.assertIn("remplacements=5", self.sortie)
        self.assertEqual(self.controler_journal("remplacer_contenu", "SUCCES")[1]["context"]["event"], "fichier_modifie")
        self.assertEqual([n for n in os.listdir(self.racine) if n.endswith(".copie_en_cours")], [])

    def test_fichier_sans_occurrence_n_est_pas_touche(self):
        chemin = self.ecrire("a.txt", b"rien", age_jours=10)
        avant = os.stat(chemin).st_mtime_ns
        self.assertEqual(self.lancer(remplacer_contenu, chemin, "--chercher", "xyz", "--remplacer", "abc"), 0)
        self.assertEqual(os.stat(chemin).st_mtime_ns, avant)
        self.assertIn("sans_occurrence=1", self.sortie)
        self.assertEqual(self.lancer(remplacer_contenu, chemin, "--chercher", "xyz", "--code-si-rien", "1"), 1)

    def test_simulation_n_ecrit_rien(self):
        chemin = self.ecrire("a.txt", b"ancien ancien")
        self.assertEqual(self.lancer(remplacer_contenu, chemin, "--chercher", "ancien", "--remplacer", "n", "--simulation"), 0)
        self.assertEqual(self.lire(chemin), b"ancien ancien")
        self.controler_journal("remplacer_contenu", simulation=True)
        self.assertEqual(self.lignes("fichier_a_modifier")[0]["remplacements"], 2)

    def test_expression_reguliere_et_groupes(self):
        chemin = self.ecrire("a.txt", b"nom=Dupont; nom=Durand")
        self.assertEqual(self.lancer(remplacer_contenu, chemin, "--regex", "--chercher", r"nom=(\w+)", "--remplacer", r"client:\1"), 0)
        self.assertEqual(self.lire(chemin), b"client:Dupont; client:Durand")
        chemin = self.ecrire("b.txt", b"a.b a*b")
        self.lancer(remplacer_contenu, chemin, "--chercher", "a.b", "--remplacer", r"x\1\n")             # texte litteral
        self.assertEqual(self.lire(chemin), b"x\\1\\n a*b")
        self.assertEqual(self.lancer(remplacer_contenu, chemin, "--regex", "--chercher", "(", "--remplacer", "x"), 3)

    def test_ignorer_la_casse_et_suppression(self):
        chemin = self.ecrire("a.txt", b"Alpha ALPHA alpha")
        self.lancer(remplacer_contenu, chemin, "--chercher", "alpha", "--ignorer-casse")
        self.assertEqual(self.lire(chemin), b"  ")

    def test_sauvegarde_et_ecraser(self):
        chemin = self.ecrire("a.txt", b"ancien")
        self.assertEqual(self.lancer(remplacer_contenu, chemin, "--chercher", "ancien", "--remplacer", "v2", "--sauvegarde"), 0)
        self.assertEqual((self.lire(chemin), self.lire(chemin + ".bak")), (b"v2", b"ancien"))
        self.assertEqual(self.lancer(remplacer_contenu, chemin, "--chercher", "v2", "--remplacer", "v3", "--sauvegarde"), 2)
        self.assertEqual((self.lire(chemin), self.lire(chemin + ".bak")), (b"v2", b"ancien"))             # rien n'a change
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "DUPLICATE_ENTITY")
        self.assertEqual(self.lancer(remplacer_contenu, chemin, "--chercher", "v2", "--remplacer", "v3", "--sauvegarde", "--ecraser"), 0)
        self.assertEqual((self.lire(chemin), self.lire(chemin + ".bak")), (b"v3", b"v2"))

    def test_garder_la_date(self):
        chemin = self.ecrire("a.txt", b"ancien", age_jours=30)
        avant = os.stat(chemin).st_mtime_ns
        self.lancer(remplacer_contenu, chemin, "--chercher", "ancien", "--remplacer", "nouveau", "--garder-date")
        self.assertEqual(os.stat(chemin).st_mtime_ns, avant)
        self.lancer(remplacer_contenu, chemin, "--chercher", "nouveau", "--remplacer", "encore")
        self.assertGreater(os.stat(chemin).st_mtime_ns, avant + 10 ** 9)

    def test_erreurs_par_element_les_autres_sont_traites(self):
        bon = self.ecrire("bon.txt", b"ancien")
        ansi = self.ecrire("ansi.txt", "café ancien".encode("cp1252"))
        binaire = self.ecrire("bin.dat", b"ancien\x00\x01")
        gros = self.ecrire("gros.txt", b"ancien" * 1000)
        code = self.lancer(remplacer_contenu, ansi, binaire, self.chemin("absent.txt"), gros, bon, "--chercher", "ancien",
                           "--remplacer", "€中", "--taille-max", "2K")
        self.assertEqual(code, 2)
        self.assertEqual(self.lire(binaire), b"ancien\x00\x01")                 # binaire ignore
        self.assertEqual(self.lire(ansi), "café ancien".encode("cp1252"))   # ni 'euro' ni 'chinois' en cp1252 : refuse, intact
        self.assertEqual(self.lire(gros), b"ancien" * 1000)
        self.assertEqual(self.lire(bon), "€中".encode("utf-8"))        # le dernier est traite malgre les erreurs
        types = sorted(b["error"]["type"] for b in self.erreurs_journal() if b["context"]["event"] != "outil_termine")
        self.assertEqual(types, ["BUSINESS_RULE_VIOLATION", "FILE_NOT_FOUND", "RESOURCE_EXHAUSTED"])

    def test_parametres(self):
        a = self.ecrire("a.txt", b"x")
        self.assertEqual(self.lancer(remplacer_contenu, a, "--chercher", ""), 3)
        self.assertEqual(self.lancer(remplacer_contenu, a), 3)
        self.assertEqual(self.lancer(remplacer_contenu, a, "--chercher", "x", "--encodage", "inconnu"), 3)

    def test_encodage_impose_et_contenu_incompatible(self):
        a = self.ecrire("a.txt", "café x".encode("cp1252"))
        self.assertEqual(self.lancer(remplacer_contenu, a, "--chercher", "x", "--remplacer", "y", "--encodage", "utf-8"), 2)
        self.assertEqual(self.lire(a), "café x".encode("cp1252"))
        self.assertEqual(self.lancer(remplacer_contenu, a, "--chercher", "x", "--remplacer", "y", "--encodage", "cp1252"), 0)
        self.assertEqual(self.lire(a), "café y".encode("cp1252"))


class TestDoublonsTrouver(CasOutil):
    def preparer(self):
        self.ecrire("d/a.txt", b"identique", age_jours=30)
        self.ecrire("d/copie_de_a.txt", b"identique", age_jours=10)
        self.ecrire("d/sous/a_bis.txt", b"identique", age_jours=5)
        self.ecrire("d/autre.txt", b"identiqu3")                       # meme taille, contenu different
        self.ecrire("d/unique.txt", b"seul au monde")
        self.ecrire("d/vide1.txt", b"")
        self.ecrire("d/vide2.txt", b"")

    def test_groupes_par_contenu_et_rapport_json(self):
        self.preparer()
        rapport, liste = self.chemin("rapport.json"), self.chemin("copies.txt")
        code = self.lancer(doublons_trouver, self.chemin("d"), "-r", "--rapport", rapport, "--sortie-liste", liste)
        self.assertEqual(code, 0, self.erreur)
        self.assertIn("1 groupe(s) de doublons, 2 copie(s) en trop", self.sortie)
        with open(rapport, encoding="utf-8") as f:
            (groupe,) = json.load(f)
        self.assertEqual(os.path.basename(groupe["original"]), "a.txt")                 # le plus ancien
        self.assertEqual(sorted(os.path.basename(c) for c in groupe["copies"]), ["a_bis.txt", "copie_de_a.txt"])
        self.assertEqual(groupe["taille"], 9)
        with open(liste, encoding="utf-8") as f:
            self.assertEqual(sorted(os.path.basename(l.strip()) for l in f), ["a_bis.txt", "copie_de_a.txt"])
        self.controler_journal("doublons_trouver", "SUCCES")
        self.assertEqual(self.lignes("groupe_doublons")[0]["sha256"], groupe["sha256"])
        self.assertTrue(os.path.exists(self.chemin("d", "copie_de_a.txt")))              # rien n'est modifie

    def test_critere_garder_et_fichiers_vides(self):
        self.preparer()
        for critere, attendu in (("plus-recent", "a_bis.txt"), ("premier", "a.txt"), ("chemin-court", "a.txt")):
            self.lancer(doublons_trouver, self.chemin("d"), "-r", "--garder", critere, "--rapport", self.chemin(critere + ".json"))
            with open(self.chemin(critere + ".json"), encoding="utf-8") as f:
                self.assertEqual(os.path.basename(json.load(f)[0]["original"]), attendu, critere)
        self.lancer(doublons_trouver, self.chemin("d"), "-r", "--inclure-vides")
        self.assertIn("2 groupe(s)", self.sortie)

    def test_rapport_csv_ecraser_et_simulation(self):
        self.preparer()
        rapport = self.chemin("rapport.csv")
        self.assertEqual(self.lancer(doublons_trouver, self.chemin("d"), "-r", "--rapport", rapport), 0)
        with open(rapport, encoding="utf-8-sig", newline="") as f:
            lignes = list(csv.reader(f, delimiter=";"))
        self.assertEqual(lignes[0], ["sha256", "taille", "original", "copie"])
        self.assertEqual(len(lignes), 3)
        self.assertEqual(self.lancer(doublons_trouver, self.chemin("d"), "-r", "--rapport", rapport), 2)
        self.assertEqual(self.lancer(doublons_trouver, self.chemin("d"), "-r", "--rapport", rapport, "--ecraser"), 0)

    def test_simulation_n_ecrit_pas_le_rapport(self):
        self.preparer()
        rapport = self.chemin("rapport.csv")
        self.assertEqual(self.lancer(doublons_trouver, self.chemin("d"), "-r", "--rapport", rapport, "--simulation"), 0)
        self.assertFalse(os.path.exists(rapport))
        self.controler_journal("doublons_trouver", simulation=True)

    def test_aucun_doublon_rien_a_faire(self):
        self.ecrire("d/a.txt", b"1")
        self.ecrire("d/b.txt", b"2")
        self.assertEqual(self.lancer(doublons_trouver, self.chemin("d"), "--code-si-rien", "1"), 1)

    def test_un_fichier_illisible_n_empeche_pas_les_autres(self):
        self.preparer()
        code = self.lancer(doublons_trouver, self.chemin("d"), self.chemin("absent.txt"), "-r")
        self.assertEqual(code, 2)
        self.assertEqual(len(self.lignes("groupe_doublons")), 1)


if __name__ == "__main__":
    unittest.main()
