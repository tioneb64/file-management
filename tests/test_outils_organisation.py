"""Boite a outils : organisation (renommage en masse, normalisation des noms, tri, dedoublonnage)."""
import os
import unittest
from datetime import datetime

from outils.organisation import doublons_supprimer, noms_normaliser, renommer_masse, trier_fichiers
from tests.boite_outils import CasOutil

try:
    from PIL import Image
except ImportError:                                          # pragma: no cover
    Image = None


class TestRenommerMasse(CasOutil):
    def test_prefixe_suffixe_et_journal(self):
        a, b = self.ecrire("d/a.txt"), self.ecrire("d/b.csv")
        self.assertEqual(self.lancer(renommer_masse, a, b, "--prefixe", "ARCH_", "--suffixe", "_v1"), 0, self.erreur)
        self.assertEqual(self.arbre(self.chemin("d")), ["ARCH_a_v1.txt", "ARCH_b_v1.csv"])
        self.assertIn("traites=2", self.sortie)
        lignes = self.controler_journal("renommer_masse", "SUCCES")
        evenements = [l["context"]["event"] for l in lignes]
        self.assertEqual(evenements.count("fichier_renomme"), 2)

    def test_simulation_ne_renomme_rien(self):
        a = self.ecrire("d/a.txt")
        self.assertEqual(self.lancer(renommer_masse, a, "--prefixe", "X_", "--simulation"), 0)
        self.assertEqual(self.arbre(self.chemin("d")), ["a.txt"])
        self.controler_journal("renommer_masse", simulation=True)
        self.assertEqual(len(self.lignes("fichier_a_renommer")), 1)

    def test_numerotation_dans_l_ordre_des_noms(self):
        for nom in ("c.txt", "a.txt", "b.txt"):
            self.ecrire("d/" + nom, nom.encode())
        self.assertEqual(self.lancer(renommer_masse, self.chemin("d"), "--numeroter", "--debut", "10", "--largeur", "4"), 0, self.erreur)
        self.assertEqual(self.arbre(self.chemin("d")), ["0010_a.txt", "0011_b.txt", "0012_c.txt"])
        self.assertEqual(self.lire(self.chemin("d", "0010_a.txt")), b"a.txt")

    def test_modele_et_numerotation_par_date(self):
        self.ecrire("d/recent.txt", age_jours=1)
        self.ecrire("d/ancien.txt", age_jours=20)
        self.lancer(renommer_masse, self.chemin("d"), "--modele", "{n}_{dossier}", "--ordre", "date", "--largeur", "2")
        self.assertEqual(self.arbre(self.chemin("d")), ["01_d.txt", "02_d.txt"])
        self.assertEqual(self.lire(self.chemin("d", "01_d.txt")), b"contenu")

    def test_expression_reguliere_avec_groupes(self):
        a = self.ecrire("d/facture 2026 01.txt")
        self.assertEqual(self.lancer(renommer_masse, a, "--regex", r"^facture (\d+) (\d+)$", "--par", r"F\1-\2"), 0)
        self.assertEqual(self.arbre(self.chemin("d")), ["F2026-01.txt"])

    def test_extension_en_minuscules(self):
        a = self.ecrire("d/PHOTO.JPG")
        self.assertEqual(self.lancer(renommer_masse, a, "--minuscules"), 0)
        self.assertEqual(self.arbre(self.chemin("d")), ["PHOTO.jpg"])

    def test_date_de_modification_dans_le_nom(self):
        a = self.ecrire("d/a.txt", age_jours=3)
        attendu = datetime.fromtimestamp(os.path.getmtime(a)).strftime("%Y-%m-%d")
        self.assertEqual(self.lancer(renommer_masse, a, "--modele", "{date}_{nom}", "--format-date", "%Y-%m-%d"), 0)
        self.assertEqual(self.arbre(self.chemin("d")), ["%s_a.txt" % attendu])

    @unittest.skipIf(Image is None, "Pillow absent")
    def test_date_exif_et_repli_sur_la_modification(self):
        photo = self.chemin("d", "IMG_1.jpg")
        os.makedirs(os.path.dirname(photo))
        exif = Image.Exif()
        exif[0x8769] = {0x9003: "2024:05:06 07:08:09"}
        with Image.new("RGB", (4, 4)) as image:
            image.save(photo, exif=exif)
        sans = self.ecrire("d/IMG_2.jpg", b"pas une image", age_jours=2)
        code = self.lancer(renommer_masse, photo, sans, "--modele", "{date}", "--date-exif", "--format-date", "%Y%m%d-%H%M%S")
        self.assertEqual(code, 0, self.erreur)
        noms = self.arbre(self.chemin("d"))
        self.assertIn("20240506-070809.jpg", noms)
        self.assertEqual(len(noms), 2)
        self.assertEqual(len(self.lignes("exif_absent")), 1)                    # avertissement pour le fichier sans EXIF
        self.assertEqual(self.controler_journal("renommer_masse", "WARNING")[-1]["context"]["statut"], "WARNING")

    @unittest.skipIf(Image is None, "Pillow absent")
    def test_sans_repli_est_une_erreur(self):
        sans = self.ecrire("d/IMG_2.jpg", b"pas une image")
        self.assertEqual(self.lancer(renommer_masse, sans, "--modele", "{date}", "--date-exif", "--sans-repli"), 2)
        self.assertEqual(self.arbre(self.chemin("d")), ["IMG_2.jpg"])

    def test_conflit_de_nom_ne_ecrase_rien(self):
        a, b = self.ecrire("d/a.txt", b"A"), self.ecrire("d/b.txt", b"B")
        self.ecrire("d/x_a.txt", b"existant")
        code = self.lancer(renommer_masse, a, b, "--prefixe", "x_")
        self.assertEqual(code, 2)
        self.assertEqual(self.lire(self.chemin("d", "x_a.txt")), b"existant")
        self.assertEqual(self.lire(self.chemin("d", "a.txt")), b"A")
        self.assertEqual(self.lire(self.chemin("d", "x_b.txt")), b"B")          # l'autre est renomme malgre l'erreur
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "DUPLICATE_ENTITY")

    def test_deux_sources_vers_le_meme_nom(self):
        a, b = self.ecrire("d/a_1.txt"), self.ecrire("d/a_2.txt")
        code = self.lancer(renommer_masse, a, b, "--regex", "_.$", "--par", "")
        self.assertEqual(code, 2)
        self.assertEqual(len(self.arbre(self.chemin("d"))), 2)                  # le premier a pris le nom, l'autre reste
        self.assertIn("a.txt", self.arbre(self.chemin("d")))

    def test_decalage_de_numeros_sans_ecrasement(self):
        for nom in ("1.txt", "2.txt", "3.txt"):
            self.ecrire("d/" + nom, nom.encode())
        code = self.lancer(renommer_masse, self.chemin("d"), "--regex", r"^(\d)$", "--par", "x")
        self.assertEqual(code, 2)                                                # 3 sources, un seul nom : conflits
        self.assertEqual(self.arbre(self.chemin("d")), ["2.txt", "3.txt", "x.txt"])
        # decalage 1->2, 2->3 : le nom d'arrivee de l'un est le nom de depart de l'autre
        self.ecrire("e/1.txt", b"un")
        self.ecrire("e/2.txt", b"deux")
        code = self.lancer(renommer_masse, self.chemin("e"), "--modele", "{n}", "--debut", "2", "--largeur", "1")
        self.assertEqual(code, 0, self.erreur)
        self.assertEqual(self.lire(self.chemin("e", "2.txt")), b"un")
        self.assertEqual(self.lire(self.chemin("e", "3.txt")), b"deux")
        self.assertEqual([n for n in self.arbre(self.chemin("e")) if n.endswith(".copie_en_cours")], [])

    def test_nom_resultant_invalide(self):
        a = self.ecrire("d/a.txt")
        self.assertEqual(self.lancer(renommer_masse, a, "--prefixe", "x/y"), 2)
        self.assertEqual(self.arbre(self.chemin("d")), ["a.txt"])
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "BUSINESS_RULE_VIOLATION")

    def test_parametres_invalides(self):
        a = self.ecrire("d/a.txt")
        self.assertEqual(self.lancer(renommer_masse, a), 3)                      # aucune transformation
        self.assertEqual(self.lancer(renommer_masse, a, "--regex", "("), 3)
        self.assertEqual(self.lancer(renommer_masse, a, "--modele", "{inconnu}"), 3)

    def test_variables_du_moteur_et_fichier_absent(self):
        a = self.ecrire("d/a.txt")
        self.assertEqual(self.lancer(renommer_masse, "--prefixe", "p_", env={"COPIE_FICHIER": a}), 0)
        self.assertEqual(self.arbre(self.chemin("d")), ["p_a.txt"])
        self.assertEqual(self.lancer(renommer_masse, self.chemin("absent.txt"), "--prefixe", "p_"), 2)
        self.assertIn("FILE_NOT_FOUND", [b["error"]["type"] for b in self.erreurs_journal()])


class TestNomsNormaliser(CasOutil):
    def test_accents_espaces_et_caracteres_interdits(self):
        self.ecrire("d/Café crème  été.TXT")
        self.ecrire("d/dœuvre.md")
        code = self.lancer(noms_normaliser, self.chemin("d"))
        self.assertEqual(code, 0, self.erreur)
        noms = self.arbre(self.chemin("d"))
        self.assertIn("Cafe_creme_ete.TXT", noms)
        self.assertIn("doeuvre.md", noms)
        self.controler_journal("noms_normaliser", "SUCCES")

    def test_caracteres_interdits_noms_reserves_et_points_de_fin(self):
        """Noms impossibles a creer sous Windows : la fonction de normalisation est testee directement."""
        args = noms_normaliser.OUTIL.parser().parse_args(["x"])
        self.assertEqual(noms_normaliser.normaliser('a:b?c<d>"e|f*.txt', args), "a_b_c_d_e_f_.txt")
        self.assertEqual(noms_normaliser.normaliser("fin.  ", args), "fin")
        self.assertEqual(noms_normaliser.normaliser("NUL.txt", args), "_NUL.txt")
        self.assertEqual(noms_normaliser.normaliser("com1", args), "_com1")
        self.assertEqual(noms_normaliser.normaliser("...", args), "sans_nom")
        self.assertEqual(noms_normaliser.normaliser("a  \t b.TXT", args), "a_b.TXT")

    def test_options(self):
        self.ecrire("d/Grand Café €.TXT")
        self.assertEqual(self.lancer(noms_normaliser, self.chemin("d"), "--espace-par", "-", "--ascii", "--minuscules"), 0)
        self.assertEqual(self.arbre(self.chemin("d")), ["grand-cafe-_.txt"])
        self.ecrire("e/été vert.txt")
        self.assertEqual(self.lancer(noms_normaliser, self.chemin("e"), "--garder-accents", "--espace-par", ""), 0)
        self.assertEqual(self.arbre(self.chemin("e")), ["étévert.txt"])

    def test_noms_reserves_et_longueur(self):
        self.ecrire("d/" + "x" * 50 + ".txt")
        self.assertEqual(self.lancer(noms_normaliser, self.chemin("d"), "--longueur-max", "20"), 0)
        noms = self.arbre(self.chemin("d"))
        self.assertEqual(noms, ["x" * 16 + ".txt"])

    def test_nom_deja_normal_et_rien_a_faire(self):
        self.ecrire("d/propre.txt")
        self.assertEqual(self.lancer(noms_normaliser, self.chemin("d")), 0)
        self.assertIn("RIEN", self.sortie.upper())
        self.assertEqual(self.lancer(noms_normaliser, self.chemin("d"), "--code-si-rien", "1"), 1)
        self.controler_journal("noms_normaliser", "RIEN")

    def test_simulation(self):
        self.ecrire("d/a b.txt")
        self.assertEqual(self.lancer(noms_normaliser, self.chemin("d"), "--simulation"), 0)
        self.assertEqual(self.arbre(self.chemin("d")), ["a b.txt"])
        self.assertEqual(len(self.lignes("fichier_a_renommer")), 1)
        self.controler_journal("noms_normaliser", simulation=True)

    def test_conflit_apres_normalisation(self):
        self.ecrire("d/a b.txt", b"1")
        self.ecrire("d/a_b.txt", b"2")
        self.assertEqual(self.lancer(noms_normaliser, self.chemin("d")), 2)
        self.assertEqual(self.lire(self.chemin("d", "a b.txt")), b"1")
        self.assertEqual(self.lire(self.chemin("d", "a_b.txt")), b"2")
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "DUPLICATE_ENTITY")

    def test_dossiers(self):
        self.ecrire("d/Résumé 2026/note finale.txt")
        self.assertEqual(self.lancer(noms_normaliser, self.chemin("d"), "-r", "--dossiers"), 0, self.erreur)
        self.assertEqual(self.arbre(self.chemin("d")), ["Resume_2026/note_finale.txt"])
        self.assertEqual(len(self.lignes("dossier_renomme")), 1)

    def test_parametre_invalide(self):
        self.assertEqual(self.lancer(noms_normaliser, self.chemin("d"), "--longueur-max", "3"), 3)


class TestTrierFichiers(CasOutil):
    def test_par_type_deplace_et_cree_les_dossiers(self):
        self.ecrire("src/a.JPG", b"img")
        self.ecrire("src/b.pdf", b"doc")
        self.ecrire("src/c.zip", b"arc")
        self.ecrire("src/d.xyz", b"???")
        code = self.lancer(trier_fichiers, self.chemin("src"), "--par", "type", "--vers", self.chemin("tri"))
        self.assertEqual(code, 0, self.erreur)
        self.assertEqual(self.arbre(self.chemin("tri")), ["archives/c.zip", "autres/d.xyz", "documents/b.pdf", "images/a.JPG"])
        self.assertEqual(self.arbre(self.chemin("src")), [])
        self.assertEqual(self.lire(self.chemin("tri", "images", "a.JPG")), b"img")
        self.assertEqual(self.controler_journal("trier_fichiers", "SUCCES")[-1]["context"]["compteurs"]["traites"], 4)

    def test_par_extension_et_sans_extension(self):
        self.ecrire("src/a.TXT")
        self.ecrire("src/b.txt")
        self.ecrire("src/LISEZMOI")
        self.assertEqual(self.lancer(trier_fichiers, self.chemin("src"), "--par", "extension", "--vers", self.chemin("tri")), 0)
        self.assertEqual(self.arbre(self.chemin("tri")), ["sans_extension/LISEZMOI", "txt/a.TXT", "txt/b.txt"])

    def test_par_date_de_modification(self):
        a = self.ecrire("src/a.txt")
        os.utime(a, (datetime(2025, 3, 14, 12).timestamp(),) * 2)
        self.assertEqual(self.lancer(trier_fichiers, a, "--par", "date", "--vers", self.chemin("tri")), 0)
        self.assertEqual(self.arbre(self.chemin("tri")), ["2025/03/a.txt"])
        b = self.ecrire("src/b.txt")
        os.utime(b, (datetime(2024, 12, 31, 12).timestamp(),) * 2)
        self.lancer(trier_fichiers, b, "--par", "date", "--vers", self.chemin("tri"), "--format-date", "%Y-%m")
        self.assertIn("2024-12/b.txt", self.arbre(self.chemin("tri")))

    @unittest.skipIf(Image is None, "Pillow absent")
    def test_par_date_exif(self):
        photo = self.chemin("src", "p.jpg")
        os.makedirs(os.path.dirname(photo))
        exif = Image.Exif()
        exif[0x8769] = {0x9003: "2019:07:08 09:10:11"}
        with Image.new("RGB", (4, 4)) as image:
            image.save(photo, exif=exif)
        self.assertEqual(self.lancer(trier_fichiers, photo, "--par", "date", "--source-date", "exif", "--vers", self.chemin("tri")), 0)
        self.assertEqual(self.arbre(self.chemin("tri")), ["2019/07/p.jpg"])

    def test_copie_verifiee_conserve_la_source(self):
        a = self.ecrire("src/a.txt", b"donnees")
        self.assertEqual(self.lancer(trier_fichiers, a, "--par", "type", "--vers", self.chemin("tri"), "--copier"), 0, self.erreur)
        self.assertEqual(self.lire(a), b"donnees")
        self.assertEqual(self.lire(self.chemin("tri", "documents", "a.txt")), b"donnees")
        self.assertEqual(len(self.lignes("fichier_range")[0]["sha256"]), 64)

    def test_simulation(self):
        a = self.ecrire("src/a.txt")
        self.assertEqual(self.lancer(trier_fichiers, a, "--par", "type", "--vers", self.chemin("tri"), "--simulation"), 0)
        self.assertEqual(self.arbre(self.chemin("src")), ["a.txt"])
        self.assertFalse(os.path.exists(self.chemin("tri")))
        self.controler_journal("trier_fichiers", simulation=True)
        self.assertEqual(len(self.lignes("fichier_a_ranger")), 1)

    def test_nom_existant_erreur_ignorer_suffixe_ecraser(self):
        for contenu, option in ((b"nouveau", None),):
            self.ecrire("tri/documents/a.txt", b"ancien")
            a = self.ecrire("src/a.txt", contenu)
            self.assertEqual(self.lancer(trier_fichiers, a, "--par", "type", "--vers", self.chemin("tri")), 2)
            self.assertEqual(self.lire(self.chemin("tri", "documents", "a.txt")), b"ancien")
            self.assertEqual(self.lire(a), b"nouveau")                           # la source n'est pas perdue
            self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "DUPLICATE_ENTITY")
        self.assertEqual(self.lancer(trier_fichiers, a, "--par", "type", "--vers", self.chemin("tri"), "--si-existe", "ignorer"), 0)
        self.assertEqual(self.lire(a), b"nouveau")
        self.assertEqual(self.lancer(trier_fichiers, a, "--par", "type", "--vers", self.chemin("tri"), "--si-existe", "suffixe"), 0)
        self.assertEqual(self.lire(self.chemin("tri", "documents", "a_1.txt")), b"nouveau")
        b = self.ecrire("src/a.txt", b"encore")
        self.assertEqual(self.lancer(trier_fichiers, b, "--par", "type", "--vers", self.chemin("tri"), "--si-existe", "ecraser"), 0)
        self.assertEqual(self.lire(self.chemin("tri", "documents", "a.txt")), b"encore")

    def test_les_fichiers_deja_ranges_sont_ignores(self):
        self.ecrire("racine/a.txt")
        self.ecrire("racine/tri/documents/deja.txt")
        code = self.lancer(trier_fichiers, self.chemin("racine"), "--par", "type", "--vers", self.chemin("racine", "tri"))
        self.assertEqual(code, 0)
        self.assertEqual(self.arbre(self.chemin("racine")), ["tri/documents/a.txt", "tri/documents/deja.txt"])

    def test_parametres_invalides_et_absent(self):
        a = self.ecrire("src/a.txt")
        self.assertEqual(self.lancer(trier_fichiers, a, "--par", "type"), 3)
        self.assertEqual(self.lancer(trier_fichiers, a, "--par", "mauvais", "--vers", self.chemin("t")), 3)
        self.assertEqual(self.lancer(trier_fichiers, self.chemin("absent.txt"), "--par", "type", "--vers", self.chemin("t")), 2)
        self.assertIn("FILE_NOT_FOUND", [b["error"]["type"] for b in self.erreurs_journal()])


class TestDoublonsSupprimer(CasOutil):
    def preparer(self):
        self.ecrire("d/a.txt", b"identique", age_jours=30)
        self.ecrire("d/copie.txt", b"identique", age_jours=10)
        self.ecrire("d/sous/autre.txt", b"identique", age_jours=5)
        self.ecrire("d/unique.txt", b"unique")
        self.ecrire("d/vide1.txt", b"")
        self.ecrire("d/vide2.txt", b"")

    def test_action_obligatoire(self):
        self.preparer()
        self.assertEqual(self.lancer(doublons_supprimer, self.chemin("d"), "-r"), 3)
        self.assertEqual(self.lancer(doublons_supprimer, self.chemin("d"), "-r", "--action", "deplacer"), 3)
        self.assertEqual(len(self.arbre(self.chemin("d"))), 6)

    def test_suppression_garde_le_plus_ancien(self):
        self.preparer()
        self.assertEqual(self.lancer(doublons_supprimer, self.chemin("d"), "-r", "--action", "supprimer"), 0, self.erreur)
        self.assertEqual(self.arbre(self.chemin("d")), ["a.txt", "unique.txt", "vide1.txt", "vide2.txt"])
        self.assertIn("supprimes=2", self.sortie)
        self.controler_journal("doublons_supprimer", "SUCCES")
        self.assertEqual(len(self.lignes("fichier_supprime")), 2)

    def test_garder_le_plus_recent_et_fichiers_vides(self):
        self.preparer()
        self.lancer(doublons_supprimer, self.chemin("d"), "-r", "--action", "supprimer", "--garder", "plus-recent", "--inclure-vides")
        restants = self.arbre(self.chemin("d"))
        self.assertEqual([n for n in restants if not n.startswith("vide")], ["sous/autre.txt", "unique.txt"])
        self.assertEqual(len([n for n in restants if n.startswith("vide")]), 1)

    def test_quarantaine(self):
        self.preparer()
        code = self.lancer(doublons_supprimer, self.chemin("d"), "-r", "--action", "deplacer", "--vers", self.chemin("quarantaine"))
        self.assertEqual(code, 0, self.erreur)
        mis_de_cote = self.arbre(self.chemin("quarantaine"))
        self.assertEqual(len(mis_de_cote), 2)
        self.assertTrue(all(n.endswith("copie.txt") or n.endswith("autre.txt") for n in mis_de_cote), mis_de_cote)
        self.assertEqual(self.lire(self.chemin("d", "a.txt")), b"identique")

    def test_simulation(self):
        self.preparer()
        code = self.lancer(doublons_supprimer, self.chemin("d"), "-r", "--action", "supprimer", "--simulation")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.arbre(self.chemin("d"))), 6)
        self.assertEqual(len(self.lignes("copie_a_traiter")), 2)
        self.controler_journal("doublons_supprimer", simulation=True)

    def test_aucun_doublon_rien_a_faire(self):
        self.ecrire("d/a.txt", b"1")
        self.ecrire("d/b.txt", b"2")
        self.assertEqual(self.lancer(doublons_supprimer, self.chemin("d"), "--action", "supprimer", "--code-si-rien", "1"), 1)
        self.controler_journal("doublons_supprimer", "RIEN")

    def test_erreur_sur_une_copie_les_autres_sont_traitees(self):
        self.preparer()
        pris = self.chemin("quarantaine")
        self.ecrire("quarantaine/.rien")
        # un dossier occupe le nom de quarantaine d'une des copies : cette copie echoue, l'autre est traitee
        self.lancer(doublons_supprimer, self.chemin("d"), "-r", "--action", "deplacer", "--vers", pris, "--simulation")
        cible = [l["cible"] for l in self.lignes("copie_a_traiter") if "cible" in l]
        self.assertEqual(cible, [])                                              # la simulation ne calcule pas de cible
        sha = self.lignes("copie_a_traiter")[0]["sha256"][:8]
        os.makedirs(os.path.join(pris, "%s_copie.txt" % sha))                    # le nom de destination est deja pris
        code = self.lancer(doublons_supprimer, self.chemin("d"), "-r", "--action", "deplacer", "--vers", pris)
        self.assertEqual(code, 2)
        self.assertTrue(os.path.exists(self.chemin("d", "copie.txt")))
        self.assertFalse(os.path.exists(self.chemin("d", "sous", "autre.txt")))
        self.assertEqual(len(self.lignes("fichier_deplace")), 1)


if __name__ == "__main__":
    unittest.main()
