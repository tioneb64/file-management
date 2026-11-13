"""Boite a outils : manipulation de fichiers (copie verifiee, decoupage de texte, fusion CSV, comparaison,
synchronisation, dossiers vides, inventaire)."""
import csv
import hashlib
import json
import os
import unittest
from unittest import mock

from outils.fichiers import (comparer_fichiers, copier_verifie, csv_fusionner, dossiers_vides_supprimer, inventaire,
                             synchroniser, texte_decouper)
from tests.boite_outils import CasOutil


def sha(octets):
    return hashlib.sha256(octets).hexdigest()


class TestCopierVerifie(CasOutil):
    def test_copie_un_fichier_et_journalise_l_empreinte(self):
        a = self.ecrire("src/a.txt", b"donnees")
        self.assertEqual(self.lancer(copier_verifie, a, "--vers", self.chemin("dest")), 0, self.erreur)
        self.assertEqual(self.lire(self.chemin("dest", "a.txt")), b"donnees")
        self.assertEqual(self.lire(a), b"donnees")
        lignes = self.controler_journal("copier_verifie", "SUCCES")
        evenement = [l for l in lignes if l["context"]["event"] == "fichier_copie"][0]["context"]
        self.assertEqual(evenement["sha256"], sha(b"donnees"))
        self.assertEqual(evenement["taille"], 7)
        self.assertEqual([n for n in self.arbre() if n.endswith(".copie_en_cours")], [])

    def test_dossier_avec_arborescence_ou_a_plat(self):
        self.ecrire("src/a.txt", b"1")
        self.ecrire("src/s/b.txt", b"2")
        self.assertEqual(self.lancer(copier_verifie, self.chemin("src"), "-r", "--vers", self.chemin("d1")), 0)
        self.assertEqual(self.arbre(self.chemin("d1")), ["a.txt", "s/b.txt"])
        self.assertEqual(self.lancer(copier_verifie, self.chemin("src"), "-r", "--vers", self.chemin("d2"), "--aplatir"), 0)
        self.assertEqual(self.arbre(self.chemin("d2")), ["a.txt", "b.txt"])

    def test_ne_pas_ecraser_sauf_option(self):
        a = self.ecrire("src/a.txt", b"nouveau")
        self.ecrire("dest/a.txt", b"ancien")
        self.assertEqual(self.lancer(copier_verifie, a, "--vers", self.chemin("dest")), 2)
        self.assertEqual(self.lire(self.chemin("dest", "a.txt")), b"ancien")
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "DUPLICATE_ENTITY")
        self.assertEqual(self.lancer(copier_verifie, a, "--vers", self.chemin("dest"), "--ecraser"), 0)
        self.assertEqual(self.lire(self.chemin("dest", "a.txt")), b"nouveau")

    def test_deplacer_supprime_la_source_apres_verification(self):
        a = self.ecrire("src/a.txt", b"x")
        self.assertEqual(self.lancer(copier_verifie, a, "--vers", self.chemin("dest"), "--deplacer"), 0)
        self.assertFalse(os.path.exists(a))
        self.assertEqual(self.lire(self.chemin("dest", "a.txt")), b"x")

    def test_copie_corrompue_source_conservee_rien_laisse(self):
        a = self.ecrire("src/a.txt", b"x" * 1000)
        with mock.patch("outils.commun.fichiers.sha256_fichier", side_effect=["a" * 64, "b" * 64]):
            code = self.lancer(copier_verifie, a, "--vers", self.chemin("dest"), "--deplacer")
        self.assertEqual(code, 2)
        self.assertTrue(os.path.exists(a))                                           # la source n'est pas supprimee
        self.assertFalse(os.path.exists(self.chemin("dest", "a.txt")))
        self.assertEqual([n for n in self.arbre() if n.endswith(".copie_en_cours")], [])

    def test_simulation(self):
        a = self.ecrire("src/a.txt")
        self.assertEqual(self.lancer(copier_verifie, a, "--vers", self.chemin("dest"), "--simulation"), 0)
        self.assertFalse(os.path.exists(self.chemin("dest")))
        self.assertEqual(len(self.lignes("fichier_a_copier")), 1)
        self.controler_journal("copier_verifie", simulation=True)

    def test_meme_fichier_et_parametres_et_absent(self):
        a = self.ecrire("src/a.txt")
        self.assertEqual(self.lancer(copier_verifie, a, "--vers", self.chemin("src")), 2)
        self.assertEqual(self.lancer(copier_verifie, a), 3)
        self.assertEqual(self.lancer(copier_verifie, self.chemin("absent.txt"), a, "--vers", self.chemin("dest")), 2)
        self.assertEqual(self.lire(self.chemin("dest", "a.txt")), b"contenu")           # l'autre est copie malgre l'erreur
        self.assertIn("FILE_NOT_FOUND", [b["error"]["type"] for b in self.erreurs_journal()])

    def test_variables_du_moteur(self):
        a = self.ecrire("src/a.txt")
        self.assertEqual(self.lancer(copier_verifie, "--vers", self.chemin("dest"), env={"COPIE_FICHIER": a}), 0)
        self.assertTrue(os.path.exists(self.chemin("dest", "a.txt")))


class TestTexteDecouper(CasOutil):
    def test_par_nombre_de_lignes_avec_entete(self):
        contenu = b"id;nom\r\n" + b"".join(b"%d;x\r\n" % i for i in range(1, 8))
        a = self.ecrire("d/gros.csv", contenu)
        self.assertEqual(self.lancer(texte_decouper, a, "--lignes", "3", "--entete"), 0, self.erreur)
        self.assertEqual(self.arbre(self.chemin("d")), ["gros.csv", "gros_001.csv", "gros_002.csv", "gros_003.csv"])
        self.assertEqual(self.lire(self.chemin("d", "gros_001.csv")), b"id;nom\r\n1;x\r\n2;x\r\n3;x\r\n")
        self.assertEqual(self.lire(self.chemin("d", "gros_003.csv")), b"id;nom\r\n7;x\r\n")
        self.controler_journal("texte_decouper", "SUCCES")
        self.assertEqual(self.lignes("fichier_decoupe")[0]["morceaux"], 3)

    def test_par_taille_coupe_a_une_fin_de_ligne(self):
        a = self.ecrire("d/a.txt", b"".join(b"ligne %02d\n" % i for i in range(10)))        # 10 octets par ligne
        self.assertEqual(self.lancer(texte_decouper, a, "--taille", "35", "--vers", self.chemin("out")), 0)
        morceaux = self.arbre(self.chemin("out"))
        self.assertEqual(morceaux, ["a_001.txt", "a_002.txt", "a_003.txt", "a_004.txt"])
        self.assertTrue(all(len(self.lire(self.chemin("out", m))) <= 35 for m in morceaux))
        self.assertEqual(b"".join(self.lire(self.chemin("out", m)) for m in morceaux), self.lire(a))

    def test_un_seul_morceau_suffit_et_simulation(self):
        a = self.ecrire("d/a.txt", b"un\ndeux\n")
        self.assertEqual(self.lancer(texte_decouper, a, "--lignes", "10"), 0)
        self.assertEqual(self.arbre(self.chemin("d")), ["a.txt"])
        self.assertEqual(self.lancer(texte_decouper, a, "--lignes", "10", "--code-si-rien", "1"), 1)
        b = self.ecrire("d/b.txt", b"1\n2\n3\n")
        self.assertEqual(self.lancer(texte_decouper, b, "--lignes", "1", "--simulation"), 0)
        self.assertEqual(self.arbre(self.chemin("d")), ["a.txt", "b.txt"])
        self.assertEqual(len(self.lignes("fichier_a_decouper")), 1)

    def test_morceau_existant_refuse_puis_ecraser(self):
        a = self.ecrire("d/a.txt", b"1\n2\n3\n")
        self.ecrire("d/a_002.txt", b"existant")
        self.assertEqual(self.lancer(texte_decouper, a, "--lignes", "1"), 2)
        self.assertEqual(self.lire(self.chemin("d", "a_002.txt")), b"existant")
        self.assertNotIn("a_001.txt", self.arbre(self.chemin("d")))                    # rien d'ecrit si un morceau est refuse
        self.assertEqual(self.lancer(texte_decouper, a, "--lignes", "1", "--ecraser"), 0)
        self.assertEqual(self.lire(self.chemin("d", "a_002.txt")), b"2\n")

    def test_utf16_ou_binaire_refuse_et_parametres(self):
        u16 = self.ecrire("d/u.txt", "a\nb\n".encode("utf-16"))
        self.assertEqual(self.lancer(texte_decouper, u16, "--lignes", "1"), 2)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "BUSINESS_RULE_VIOLATION")
        a = self.ecrire("d/a.txt", b"x\n")
        self.assertEqual(self.lancer(texte_decouper, a), 3)
        self.assertEqual(self.lancer(texte_decouper, a, "--lignes", "2", "--taille", "10"), 3)
        self.assertEqual(self.lancer(texte_decouper, a, "--lignes", "0"), 3)
        self.assertEqual(self.lancer(texte_decouper, a, "--taille", "grand"), 3)


class TestCsvFusionner(CasOutil):
    def lire_csv(self, chemin, encodage="utf-8-sig"):
        with open(chemin, encoding=encodage, newline="") as f:
            return list(csv.reader(f, delimiter=";"))

    def test_en_tete_unique_ordre_alphabetique_et_colonne_source(self):
        self.ecrire("d/b.csv", b"id;nom\r\n3;Cl\r\n")
        self.ecrire("d/a.csv", b"id;nom\r\n1;Al\r\n2;Be\r\n")
        sortie = self.chemin("fusion.csv")
        self.assertEqual(self.lancer(csv_fusionner, self.chemin("d"), "--sortie", sortie, "--colonne-source", "origine"), 0, self.erreur)
        self.assertEqual(self.lire_csv(sortie), [["id", "nom", "origine"], ["1", "Al", "a.csv"], ["2", "Be", "a.csv"], ["3", "Cl", "b.csv"]])
        self.assertTrue(self.lire(sortie).startswith(b"\xef\xbb\xbf"))
        self.controler_journal("csv_fusionner", "SUCCES")
        self.assertEqual(self.lignes("csv_ecrit")[0]["lignes"], 3)

    def test_separateur_detecte_et_encodages_differents(self):
        self.ecrire("d/a.csv", "nom,ville\r\nZoé,Pau\r\n".encode("cp1252"))
        self.ecrire("d/b.csv", "nom,ville\r\nÉric,Dax\r\n".encode("utf-8"))
        sortie = self.chemin("f.csv")
        self.assertEqual(self.lancer(csv_fusionner, self.chemin("d"), "--sortie", sortie), 0, self.erreur)
        with open(sortie, encoding="utf-8-sig", newline="") as f:
            lignes = list(csv.reader(f, delimiter=","))
        self.assertEqual(lignes, [["nom", "ville"], ["Zoé", "Pau"], ["Éric", "Dax"]])

    def test_sans_entete(self):
        self.ecrire("d/a.csv", b"1;x\r\n")
        self.ecrire("d/b.csv", b"2;y\r\n")
        sortie = self.chemin("f.csv")
        self.assertEqual(self.lancer(csv_fusionner, self.chemin("d"), "--sortie", sortie, "--sans-entete"), 0)
        self.assertEqual(self.lire_csv(sortie), [["1", "x"], ["2", "y"]])

    def test_colonnes_differentes_rien_n_est_ecrit(self):
        self.ecrire("d/a.csv", b"id;nom\r\n1;A\r\n")
        self.ecrire("d/b.csv", b"id;prenom\r\n2;B\r\n")
        sortie = self.chemin("f.csv")
        self.assertEqual(self.lancer(csv_fusionner, self.chemin("d"), "--sortie", sortie), 2)
        self.assertFalse(os.path.exists(sortie))                                        # resultat incomplet : jamais ecrit
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "BUSINESS_RULE_VIOLATION")
        self.assertEqual([n for n in self.arbre() if n.endswith(".copie_en_cours")], [])

    def test_ecraser_simulation_et_la_sortie_n_est_pas_une_entree(self):
        self.ecrire("d/a.csv", b"id\r\n1\r\n")
        sortie = self.chemin("d", "fusion.csv")
        self.assertEqual(self.lancer(csv_fusionner, self.chemin("d"), "--sortie", sortie, "--simulation"), 0)
        self.assertFalse(os.path.exists(sortie))
        self.controler_journal("csv_fusionner", simulation=True)
        self.assertEqual(self.lancer(csv_fusionner, self.chemin("d"), "--sortie", sortie), 0)
        self.assertEqual(self.lancer(csv_fusionner, self.chemin("d"), "--sortie", sortie), 2)
        self.assertEqual(self.lancer(csv_fusionner, self.chemin("d"), "--sortie", sortie, "--ecraser"), 0)
        self.assertEqual(self.lire_csv(sortie), [["id"], ["1"]])                         # fusion.csv ne s'est pas relu lui-meme

    def test_parametres_et_fichier_absent(self):
        self.ecrire("d/a.csv", b"id\r\n1\r\n")
        self.assertEqual(self.lancer(csv_fusionner, self.chemin("d")), 3)
        self.assertEqual(self.lancer(csv_fusionner, self.chemin("d"), "--sortie", self.chemin("f.csv"), "--separateur", "ab"), 3)
        self.assertEqual(self.lancer(csv_fusionner, self.chemin("d"), "--sortie", self.chemin("f.csv"), "--encodage-sortie", "zz"), 3)
        self.assertEqual(self.lancer(csv_fusionner, self.chemin("d", "a.csv"), self.chemin("absent.csv"), "--sortie", self.chemin("f.csv")), 2)
        self.assertFalse(os.path.exists(self.chemin("f.csv")))


class TestComparerFichiers(CasOutil):
    def test_fichiers_identiques_rien_a_faire(self):
        a, b = self.ecrire("a.txt", b"x\ny\n"), self.ecrire("b.txt", b"x\ny\n")
        self.assertEqual(self.lancer(comparer_fichiers, a, b), 0)
        self.assertEqual(self.lancer(comparer_fichiers, a, b, "--code-si-rien", "1"), 1)
        self.controler_journal("comparer_fichiers", "RIEN")

    def test_diff_unifie_difference_n_est_pas_une_erreur(self):
        a, b = self.ecrire("a.txt", b"un\ndeux\ntrois\n"), self.ecrire("b.txt", b"un\n2\ntrois\n")
        self.assertEqual(self.lancer(comparer_fichiers, a, b), 0, self.erreur)
        self.assertIn("-deux", self.sortie)
        self.assertIn("+2", self.sortie)
        self.assertIn("lignes_differentes=2", self.sortie)
        self.controler_journal("comparer_fichiers", "SUCCES")
        self.assertEqual(len(self.lignes("difference_trouvee")), 1)

    def test_erreur_si_different_et_rapport(self):
        a, b = self.ecrire("a.txt", b"1\n"), self.ecrire("b.txt", b"2\n")
        rapport = self.chemin("diff.txt")
        self.assertEqual(self.lancer(comparer_fichiers, a, b, "--erreur-si-different", "--rapport", rapport), 2)
        with open(rapport, encoding="utf-8") as f:
            self.assertIn("-1", f.read())
        self.assertEqual(self.lancer(comparer_fichiers, a, b, "--rapport", rapport), 2)               # existe deja
        self.assertEqual(self.lancer(comparer_fichiers, a, b, "--rapport", rapport, "--ecraser"), 0)

    def test_ignorer_les_blancs_de_fin_de_ligne(self):
        a, b = self.ecrire("a.txt", b"un  \ndeux\n"), self.ecrire("b.txt", b"un\ndeux\n")
        self.assertEqual(self.lancer(comparer_fichiers, a, b, "--ignorer-blancs", "--code-si-rien", "1"), 1)
        self.assertEqual(self.lancer(comparer_fichiers, a, b, "--code-si-rien", "1"), 0)

    def test_fichiers_binaires(self):
        a, b = self.ecrire("a.bin", b"\x00\x01"), self.ecrire("b.bin", b"\x00\x02")
        self.assertEqual(self.lancer(comparer_fichiers, a, b), 0)
        self.assertIn("binaires differents", self.sortie)

    def test_dossiers(self):
        self.ecrire("g/commun.txt", b"=")
        self.ecrire("d/commun.txt", b"=")
        self.ecrire("g/seul_g.txt", b"g")
        self.ecrire("d/seul_d.txt", b"d")
        self.ecrire("g/modif.txt", b"avant")
        self.ecrire("d/modif.txt", b"apres")
        self.ecrire("g/s/p.txt", b"1")
        self.ecrire("d/s/p.txt", b"1")
        rapport = self.chemin("ecarts.json")
        self.assertEqual(self.lancer(comparer_fichiers, self.chemin("g"), self.chemin("d"), "-r", "--rapport", rapport), 0, self.erreur)
        with open(rapport, encoding="utf-8") as f:
            ecarts = json.load(f)
        self.assertEqual(ecarts, {"seulement_gauche": ["seul_g.txt"], "seulement_droite": ["seul_d.txt"],
                                  "differents": ["modif.txt"], "identiques": 2})
        self.assertIn("seulement gauche : seul_g.txt", self.sortie)
        self.assertEqual(self.lancer(comparer_fichiers, self.chemin("g"), self.chemin("d"), "--erreur-si-different"), 2)

    def test_dossiers_masque_exclusion_identiques(self):
        self.ecrire("g/a.txt", b"1")
        self.ecrire("d/a.txt", b"1")
        self.ecrire("g/b.log", b"1")
        self.ecrire("d/b.log", b"2")
        self.assertEqual(self.lancer(comparer_fichiers, self.chemin("g"), self.chemin("d"), "--masque", "*.txt", "--code-si-rien", "1"), 1)
        self.assertEqual(self.lancer(comparer_fichiers, self.chemin("g"), self.chemin("d"), "--exclure", "*.log", "--code-si-rien", "1"), 1)

    def test_parametres_et_introuvable(self):
        a = self.ecrire("a.txt")
        self.ecrire("d/x.txt")
        self.assertEqual(self.lancer(comparer_fichiers, a, self.chemin("d")), 3)
        self.assertEqual(self.lancer(comparer_fichiers, a, self.chemin("absent.txt")), 2)
        self.assertIn("FILE_NOT_FOUND", [b["error"]["type"] for b in self.erreurs_journal()])


class TestSynchroniser(CasOutil):
    def preparer(self):
        self.ecrire("src/a.txt", b"A", age_jours=3)
        self.ecrire("src/s/b.txt", b"B", age_jours=3)
        os.makedirs(self.chemin("src", "vide"))

    def test_premiere_synchro_copie_tout_et_la_seconde_ne_fait_rien(self):
        self.preparer()
        self.assertEqual(self.lancer(synchroniser, self.chemin("src"), self.chemin("cible")), 0, self.erreur)
        self.assertEqual(self.arbre(self.chemin("cible")), ["a.txt", "s/b.txt"])
        self.assertTrue(os.path.isdir(self.chemin("cible", "vide")))
        self.assertIn("copies=2", self.sortie)
        lignes = self.controler_journal("synchroniser", "SUCCES")
        copie = [l for l in lignes if l["context"]["event"] == "fichier_copie"][0]["context"]
        self.assertEqual(len(copie["sha256"]), 64)
        self.assertEqual(self.lancer(synchroniser, self.chemin("src"), self.chemin("cible"), "--code-si-rien", "1"), 1)

    def test_fichier_modifie_est_mis_a_jour_et_rien_n_est_supprime_sans_miroir(self):
        self.preparer()
        self.lancer(synchroniser, self.chemin("src"), self.chemin("cible"))
        self.ecrire("src/a.txt", b"A2")
        self.ecrire("cible/en_trop.txt", b"?")
        self.assertEqual(self.lancer(synchroniser, self.chemin("src"), self.chemin("cible")), 0)
        self.assertEqual(self.lire(self.chemin("cible", "a.txt")), b"A2")
        self.assertTrue(os.path.exists(self.chemin("cible", "en_trop.txt")))
        self.assertIn("mis_a_jour=1", self.sortie)

    def test_comparaison_par_contenu(self):
        self.ecrire("src/a.txt", b"AAAA", age_jours=3)
        self.ecrire("cible/a.txt", b"BBBB", age_jours=3)
        os.utime(self.chemin("cible", "a.txt"), ns=(os.stat(self.chemin("src", "a.txt")).st_atime_ns, os.stat(self.chemin("src", "a.txt")).st_mtime_ns))
        self.assertEqual(self.lancer(synchroniser, self.chemin("src"), self.chemin("cible"), "--code-si-rien", "1"), 1)   # meme taille et date
        self.assertEqual(self.lancer(synchroniser, self.chemin("src"), self.chemin("cible"), "--comparer", "contenu"), 0)
        self.assertEqual(self.lire(self.chemin("cible", "a.txt")), b"AAAA")

    def test_miroir_supprime_fichiers_et_dossiers_en_trop(self):
        self.preparer()
        self.ecrire("cible/a.txt", b"A", age_jours=3)
        self.ecrire("cible/vieux.txt")
        self.ecrire("cible/ancien/sous/x.txt")
        self.assertEqual(self.lancer(synchroniser, self.chemin("src"), self.chemin("cible"), "--miroir"), 0, self.erreur)
        self.assertEqual(self.arbre(self.chemin("cible")), ["a.txt", "s/b.txt"])
        self.assertFalse(os.path.exists(self.chemin("cible", "ancien")))
        self.assertEqual(len(self.lignes("fichier_supprime")), 2)

    def test_simulation_ne_modifie_rien(self):
        self.preparer()
        self.ecrire("cible/vieux.txt")
        self.assertEqual(self.lancer(synchroniser, self.chemin("src"), self.chemin("cible"), "--miroir", "--simulation"), 0)
        self.assertEqual(self.arbre(self.chemin("cible")), ["vieux.txt"])
        self.assertEqual(len(self.lignes("fichier_a_copier")), 2)
        self.assertEqual(len(self.lignes("fichier_a_supprimer")), 1)
        self.controler_journal("synchroniser", simulation=True)

    def test_garde_fous_du_miroir(self):
        os.makedirs(self.chemin("src_vide"))
        self.ecrire("cible/precieux.txt", b"!")
        self.assertEqual(self.lancer(synchroniser, self.chemin("src_vide"), self.chemin("cible"), "--miroir"), 2)
        self.assertTrue(os.path.exists(self.chemin("cible", "precieux.txt")))               # source vide : cible protegee
        self.assertEqual(self.lancer(synchroniser, self.chemin("src_vide"), self.chemin("cible"), "--miroir", "--autoriser-source-vide"), 0)
        self.assertFalse(os.path.exists(self.chemin("cible", "precieux.txt")))
        self.preparer()
        for i in range(5):
            self.ecrire("cible2/x%d.txt" % i)
        self.assertEqual(self.lancer(synchroniser, self.chemin("src"), self.chemin("cible2"), "--miroir", "--max-suppressions", "2"), 2)
        self.assertEqual(len(self.arbre(self.chemin("cible2"))), 5)                          # rien n'a ete fait
        self.assertEqual(self.lancer(synchroniser, self.chemin("absent"), self.chemin("cible")), 2)
        self.assertIn("FILE_NOT_FOUND", [b["error"]["type"] for b in self.erreurs_journal()])

    def test_dossiers_imbriques_refuses(self):
        self.preparer()
        self.assertEqual(self.lancer(synchroniser, self.chemin("src"), self.chemin("src", "sous_cible"), "--miroir"), 3)
        self.assertEqual(self.lancer(synchroniser, self.chemin("src", "s"), self.chemin("src")), 3)

    def test_masque_et_exclusion_ne_suppriment_pas_ce_qui_est_exclu(self):
        self.ecrire("src/a.txt", b"A")
        self.ecrire("src/b.log", b"B")
        self.ecrire("cible/c.log", b"garde")
        self.assertEqual(self.lancer(synchroniser, self.chemin("src"), self.chemin("cible"), "--miroir", "--exclure", "*.log"), 0)
        self.assertEqual(self.arbre(self.chemin("cible")), ["a.txt", "c.log"])

    def test_sans_verification_et_variables_du_moteur(self):
        self.preparer()
        code = self.lancer(synchroniser, "--sans-verification", env={"COPIE_SOURCE": self.chemin("src"), "COPIE_CIBLE": self.chemin("cible")})
        self.assertEqual(code, 0, self.erreur)
        self.assertEqual(self.arbre(self.chemin("cible")), ["a.txt", "s/b.txt"])
        self.assertIsNone(self.lignes("fichier_copie")[0].get("sha256"))
        self.assertEqual(self.lancer(synchroniser), 3)

    def test_erreur_sur_un_fichier_les_autres_sont_copies(self):
        self.preparer()
        os.makedirs(self.chemin("cible", "a.txt"))                                           # un dossier occupe le nom du fichier
        code = self.lancer(synchroniser, self.chemin("src"), self.chemin("cible"))
        self.assertEqual(code, 2)
        self.assertEqual(self.lire(self.chemin("cible", "s", "b.txt")), b"B")


class TestDossiersVidesSupprimer(CasOutil):
    def preparer(self):
        self.ecrire("d/plein/a.txt")
        os.makedirs(self.chemin("d", "vide1"))
        os.makedirs(self.chemin("d", "chaine", "b", "c"))
        os.makedirs(self.chemin("d", "plein", "creux"))
        self.ecrire("d/thumbs/Thumbs.db")

    def test_supprime_du_plus_profond_au_plus_haut_et_garde_la_racine(self):
        self.preparer()
        self.assertEqual(self.lancer(dossiers_vides_supprimer, self.chemin("d")), 0, self.erreur)
        self.assertEqual(sorted(os.listdir(self.chemin("d"))), ["plein", "thumbs"])
        self.assertEqual(os.listdir(self.chemin("d", "plein")), ["a.txt"])
        self.assertIn("supprimes=5", self.sortie)
        self.controler_journal("dossiers_vides_supprimer", "SUCCES")

    def test_ignorer_des_fichiers_et_racine(self):
        self.preparer()
        self.assertEqual(self.lancer(dossiers_vides_supprimer, self.chemin("d"), "--ignorer", "thumbs.db"), 0)
        self.assertFalse(os.path.exists(self.chemin("d", "thumbs")))
        os.makedirs(self.chemin("e", "x"))
        self.assertEqual(self.lancer(dossiers_vides_supprimer, self.chemin("e"), "--racine"), 0)
        self.assertFalse(os.path.exists(self.chemin("e")))

    def test_simulation_decrit_la_cascade_sans_rien_supprimer(self):
        self.preparer()
        self.assertEqual(self.lancer(dossiers_vides_supprimer, self.chemin("d"), "--simulation"), 0)
        self.assertEqual(len(self.lignes("dossier_a_supprimer")), 5)                  # vide1, chaine, b, c et creux (thumbs garde : Thumbs.db)
        self.assertTrue(os.path.isdir(self.chemin("d", "chaine", "b", "c")))
        self.controler_journal("dossiers_vides_supprimer", simulation=True)

    def test_rien_a_faire_introuvable_et_racine_de_disque(self):
        self.ecrire("d/plein/a.txt")
        self.assertEqual(self.lancer(dossiers_vides_supprimer, self.chemin("d"), "--code-si-rien", "1"), 1)
        self.assertEqual(self.lancer(dossiers_vides_supprimer, self.chemin("absent")), 2)
        self.assertIn("FILE_NOT_FOUND", [b["error"]["type"] for b in self.erreurs_journal()])
        disque = os.path.abspath(os.sep)
        self.assertEqual(self.lancer(dossiers_vides_supprimer, disque), 2)
        self.assertEqual(self.erreurs_journal()[-2]["error"]["type"], "BUSINESS_RULE_VIOLATION")

    @unittest.skipUnless(hasattr(os, "symlink"), "liens symboliques")
    def test_les_liens_ne_sont_jamais_suivis(self):
        os.makedirs(self.chemin("cible_lien", "vide"))
        os.makedirs(self.chemin("d"))
        try:
            os.symlink(self.chemin("cible_lien"), self.chemin("d", "lien"), target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("creation de lien symbolique non permise")
        self.assertEqual(self.lancer(dossiers_vides_supprimer, self.chemin("d")), 0)
        self.assertTrue(os.path.isdir(self.chemin("cible_lien", "vide")))                # la cible du lien est intacte


class TestInventaire(CasOutil):
    def preparer(self):
        self.ecrire("d/a.TXT", b"aaa", age_jours=2)
        self.ecrire("d/s/b.csv", b"bbbb")
        self.ecrire("d/s/c.bin", b"")

    def test_csv_recursif_par_defaut(self):
        self.preparer()
        sortie = self.chemin("inv.csv")
        self.assertEqual(self.lancer(inventaire, self.chemin("d"), "--sortie", sortie), 0, self.erreur)
        with open(sortie, encoding="utf-8-sig", newline="") as f:
            lignes = list(csv.DictReader(f, delimiter=";"))
        self.assertEqual([l["chemin"] for l in lignes], ["a.TXT", "s/b.csv", "s/c.bin"])
        self.assertEqual([l["extension"] for l in lignes], [".txt", ".csv", ".bin"])
        self.assertEqual([l["taille"] for l in lignes], ["3", "4", "0"])
        self.assertNotIn("sha256", lignes[0])
        self.controler_journal("inventaire", "SUCCES")

    def test_json_avec_sha256_et_sans_recursion(self):
        self.preparer()
        sortie = self.chemin("inv.json")
        self.assertEqual(self.lancer(inventaire, self.chemin("d"), "--sortie", sortie, "--sha256", "--sans-recursion"), 0)
        with open(sortie, encoding="utf-8") as f:
            lignes = json.load(f)
        self.assertEqual([l["chemin"] for l in lignes], ["a.TXT"])
        self.assertEqual(lignes[0]["sha256"], sha(b"aaa"))

    def test_la_sortie_n_est_pas_dans_l_inventaire_ecraser_et_simulation(self):
        self.preparer()
        sortie = self.chemin("d", "inv.csv")
        self.assertEqual(self.lancer(inventaire, self.chemin("d"), "--sortie", sortie, "--simulation"), 0)
        self.assertFalse(os.path.exists(sortie))
        self.controler_journal("inventaire", simulation=True)
        self.assertEqual(self.lancer(inventaire, self.chemin("d"), "--sortie", sortie), 0)
        self.assertEqual(self.lancer(inventaire, self.chemin("d"), "--sortie", sortie), 2)
        self.assertEqual(self.lancer(inventaire, self.chemin("d"), "--sortie", sortie, "--ecraser"), 0)
        with open(sortie, encoding="utf-8-sig") as f:
            self.assertNotIn("inv.csv", f.read())

    def test_parametres_vide_et_absent(self):
        self.preparer()
        self.assertEqual(self.lancer(inventaire, self.chemin("d"), "--sortie", self.chemin("inv.txt")), 3)
        os.makedirs(self.chemin("vide"))
        self.assertEqual(self.lancer(inventaire, self.chemin("vide"), "--sortie", self.chemin("i.csv"), "--code-si-rien", "1"), 1)
        self.assertFalse(os.path.exists(self.chemin("i.csv")))
        self.assertEqual(self.lancer(inventaire, self.chemin("absent"), "--sortie", self.chemin("i.csv")), 2)


if __name__ == "__main__":
    unittest.main()
