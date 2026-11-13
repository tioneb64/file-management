"""Boite a outils : conversion (encodage, fins de ligne, xlsx -> csv, document -> pdf, images)."""
import csv
import os
import unittest
import zipfile
from unittest import mock

from outils.conversion import (document_vers_pdf, encodage_convertir, fin_ligne_convertir, image_convertir,
                               xlsx_vers_csv)
from tests.boite_outils import CasOutil

try:
    from PIL import Image
except ImportError:                                          # pragma: no cover
    Image = None

TEXTE = "café à l'été\r\nligne 2\r\n"


class TestEncodageConvertir(CasOutil):
    def test_ansi_vers_utf8_detection_automatique(self):
        a = self.ecrire("a.txt", TEXTE.encode("cp1252"))
        self.assertEqual(self.lancer(encodage_convertir, a, "--vers", "utf-8"), 0, self.erreur)
        self.assertEqual(self.lire(a), TEXTE.encode("utf-8"))
        lignes = self.controler_journal("encodage_convertir", "SUCCES")
        evenement = [l for l in lignes if l["context"]["event"] == "fichier_converti"][0]["context"]
        self.assertEqual((evenement["de"], evenement["vers"]), ("cp1252", "utf-8"))

    def test_utf8_vers_ansi_avec_bom_et_utf16(self):
        a = self.ecrire("a.txt", TEXTE.encode("utf-8"))
        self.assertEqual(self.lancer(encodage_convertir, a, "--vers", "cp1252"), 0)
        self.assertEqual(self.lire(a), TEXTE.encode("cp1252"))
        self.assertEqual(self.lancer(encodage_convertir, a, "--vers", "utf-8-sig", "--de", "cp1252"), 0)
        self.assertEqual(self.lire(a), b"\xef\xbb\xbf" + TEXTE.encode("utf-8"))
        self.assertEqual(self.lancer(encodage_convertir, a, "--vers", "utf-8"), 0)                # le BOM disparait
        self.assertEqual(self.lire(a), TEXTE.encode("utf-8"))
        self.assertEqual(self.lancer(encodage_convertir, a, "--vers", "utf-16"), 0)
        self.assertEqual(self.lire(a).decode("utf-16"), TEXTE)
        self.assertEqual(self.lancer(encodage_convertir, a, "--vers", "latin-1"), 0)
        self.assertEqual(self.lire(a), TEXTE.encode("latin-1"))

    def test_deja_conforme_n_est_pas_reecrit(self):
        a = self.ecrire("a.txt", b"ascii seulement", age_jours=9)
        avant = os.stat(a).st_mtime_ns
        self.assertEqual(self.lancer(encodage_convertir, a, "--vers", "utf-8"), 0)
        self.assertEqual(os.stat(a).st_mtime_ns, avant)
        self.assertIn("deja_conformes=1", self.sortie)
        self.assertEqual(self.lancer(encodage_convertir, a, "--vers", "utf-8", "--code-si-rien", "1"), 1)
        self.controler_journal("encodage_convertir", "RIEN")

    def test_caractere_non_representable_ne_perd_rien(self):
        a = self.ecrire("a.txt", "prix : 5 € 中".encode("utf-8"))
        self.assertEqual(self.lancer(encodage_convertir, a, "--vers", "cp1252"), 2)
        self.assertEqual(self.lire(a), "prix : 5 € 中".encode("utf-8"))
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "BUSINESS_RULE_VIOLATION")
        self.assertEqual([n for n in os.listdir(self.racine) if n.endswith(".copie_en_cours")], [])

    def test_contenu_invalide_pour_l_encodage_impose_et_binaire_ignore(self):
        a = self.ecrire("a.txt", b"\x81\x8d\x8f\x90 x")                            # non defini en cp1252
        code = self.lancer(encodage_convertir, a, "--de", "utf-8", "--vers", "cp1252")
        self.assertEqual(code, 2)
        binaire = self.ecrire("b.dat", b"\x00\x01\x02\x03")
        self.assertEqual(self.lancer(encodage_convertir, binaire, "--vers", "utf-8"), 0)
        self.assertEqual(self.lire(binaire), b"\x00\x01\x02\x03")
        self.assertIn("binaires_ignores=1", self.sortie)

    def test_sortie_dossier_sauvegarde_et_ecraser(self):
        a = self.ecrire("src/sous/a.txt", TEXTE.encode("cp1252"))
        self.assertEqual(self.lancer(encodage_convertir, self.chemin("src"), "-r", "--vers", "utf-8",
                                     "--sortie-dossier", self.chemin("out")), 0, self.erreur)
        self.assertEqual(self.lire(self.chemin("out", "sous", "a.txt")), TEXTE.encode("utf-8"))
        self.assertEqual(self.lire(a), TEXTE.encode("cp1252"))                       # l'original est intact
        self.assertEqual(self.lancer(encodage_convertir, self.chemin("src"), "-r", "--vers", "utf-8",
                                     "--sortie-dossier", self.chemin("out")), 2)     # la sortie existe deja
        self.assertEqual(self.lancer(encodage_convertir, self.chemin("src"), "-r", "--vers", "utf-8",
                                     "--sortie-dossier", self.chemin("out"), "--ecraser"), 0)
        self.assertEqual(self.lancer(encodage_convertir, a, "--vers", "utf-8", "--sauvegarde"), 0)
        self.assertEqual(self.lire(a + ".bak"), TEXTE.encode("cp1252"))
        self.assertEqual(self.lancer(encodage_convertir, a, "--vers", "cp1252", "--sauvegarde"), 2)   # .bak existe deja
        self.assertEqual(self.lire(a), TEXTE.encode("utf-8"))

    def test_simulation(self):
        a = self.ecrire("a.txt", TEXTE.encode("cp1252"))
        self.assertEqual(self.lancer(encodage_convertir, a, "--vers", "utf-8", "--simulation"), 0)
        self.assertEqual(self.lire(a), TEXTE.encode("cp1252"))
        self.controler_journal("encodage_convertir", simulation=True)
        self.assertEqual(len(self.lignes("fichier_a_convertir")), 1)

    def test_un_fichier_en_erreur_n_arrete_pas_les_autres(self):
        mauvais = self.ecrire("1.txt", "中".encode("utf-8"))
        bon = self.ecrire("2.txt", TEXTE.encode("cp1252"))
        self.assertEqual(self.lancer(encodage_convertir, mauvais, self.chemin("absent.txt"), bon, "--vers", "cp1252"), 2)
        self.assertEqual(self.lire(bon), TEXTE.encode("cp1252"))                     # deja en cp1252 : inchange, pas d'erreur
        self.assertEqual(self.lancer(encodage_convertir, mauvais, "--vers", "utf-8", "--taille-max", "1"), 2)
        self.assertEqual(self.erreurs_journal()[-2]["error"]["type"], "RESOURCE_EXHAUSTED")

    def test_parametres(self):
        a = self.ecrire("a.txt")
        self.assertEqual(self.lancer(encodage_convertir, a), 3)
        self.assertEqual(self.lancer(encodage_convertir, a, "--vers", "ebcdic"), 3)
        self.assertEqual(self.lancer(encodage_convertir, a, "--vers", "utf-8", "--de", "inconnu"), 3)


class TestFinLigneConvertir(CasOutil):
    def test_crlf_vers_lf_et_retour(self):
        a = self.ecrire("a.txt", b"un\r\ndeux\r\ntrois")
        self.assertEqual(self.lancer(fin_ligne_convertir, a, "--vers", "lf"), 0, self.erreur)
        self.assertEqual(self.lire(a), b"un\ndeux\ntrois")
        self.assertEqual(self.lancer(fin_ligne_convertir, a, "--vers", "crlf"), 0)
        self.assertEqual(self.lire(a), b"un\r\ndeux\r\ntrois")
        self.controler_journal("fin_ligne_convertir", "SUCCES")

    def test_fins_melangees_et_cr_isole(self):
        a = self.ecrire("a.txt", b"a\r\nb\nc\rd\n")
        self.lancer(fin_ligne_convertir, a, "--vers", "crlf")
        self.assertEqual(self.lire(a), b"a\r\nb\r\nc\r\nd\r\n")

    def test_encodage_non_touche(self):
        contenu = "café\r\n".encode("cp1252")
        a = self.ecrire("a.txt", contenu)
        self.lancer(fin_ligne_convertir, a, "--vers", "lf")
        self.assertEqual(self.lire(a), "café\n".encode("cp1252"))

    def test_deja_conforme_binaire_et_utf16_ignores(self):
        a = self.ecrire("a.txt", b"x\ny\n", age_jours=5)
        avant = os.stat(a).st_mtime_ns
        self.assertEqual(self.lancer(fin_ligne_convertir, a, "--vers", "lf"), 0)
        self.assertEqual(os.stat(a).st_mtime_ns, avant)
        binaire = self.ecrire("b.bin", b"\x00\r\n\x01")
        u16 = self.ecrire("c.txt", "a\r\nb".encode("utf-16"))
        self.assertEqual(self.lancer(fin_ligne_convertir, binaire, u16, "--vers", "lf"), 0)
        self.assertEqual(self.lire(binaire), b"\x00\r\n\x01")
        self.assertEqual(self.lire(u16), "a\r\nb".encode("utf-16"))
        self.assertIn("binaires_ignores=2", self.sortie)

    def test_simulation_sortie_dossier_sauvegarde(self):
        a = self.ecrire("src/a.txt", b"x\r\ny")
        self.assertEqual(self.lancer(fin_ligne_convertir, a, "--vers", "lf", "--simulation"), 0)
        self.assertEqual(self.lire(a), b"x\r\ny")
        self.controler_journal("fin_ligne_convertir", simulation=True)
        self.assertEqual(self.lancer(fin_ligne_convertir, self.chemin("src"), "--vers", "lf", "--sortie-dossier", self.chemin("out")), 0)
        self.assertEqual(self.lire(self.chemin("out", "a.txt")), b"x\ny")
        self.assertEqual(self.lire(a), b"x\r\ny")
        self.assertEqual(self.lancer(fin_ligne_convertir, a, "--vers", "lf", "--sauvegarde"), 0)
        self.assertEqual(self.lire(a + ".bak"), b"x\r\ny")

    def test_erreurs_par_element(self):
        a = self.ecrire("a.txt", b"x\r\n")
        gros = self.ecrire("gros.txt", b"x\r\n" * 100)
        self.assertEqual(self.lancer(fin_ligne_convertir, self.chemin("absent.txt"), gros, a, "--vers", "lf", "--taille-max", "50"), 2)
        self.assertEqual(self.lire(a), b"x\n")
        self.assertEqual(self.lire(gros), b"x\r\n" * 100)
        types = sorted(b["error"]["type"] for b in self.erreurs_journal() if b["context"]["event"] != "outil_termine")
        self.assertEqual(types, ["FILE_NOT_FOUND", "RESOURCE_EXHAUSTED"])

    def test_parametre_obligatoire_et_variable_moteur(self):
        a = self.ecrire("a.txt", b"x\r\n")
        self.assertEqual(self.lancer(fin_ligne_convertir, a), 3)
        self.assertEqual(self.lancer(fin_ligne_convertir, "--vers", "lf", env={"COPIE_FICHIER": a}), 0)
        self.assertEqual(self.lire(a), b"x\n")


def fabriquer_xlsx(chemin, feuilles=None, dates=True, inline=False):
    """Un classeur .xlsx minimal ecrit a la main (zip + XML) : feuilles = [(nom, lignes_xml)]."""
    feuilles = feuilles or [("Ventes", """
        <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row>
        <row r="2"><c r="A2" t="s"><v>3</v></c><c r="B2"><v>12</v></c><c r="C2" s="1"><v>45678</v></c></row>
        <row r="4"><c r="A4" t="inlineStr"><is><t>direct</t></is></c><c r="C4"><v>3.5</v></c><c r="D4" t="b"><v>1</v></c></row>"""),
        ("Autre", '<row r="1"><c r="A1" t="str"><f>1+1</f><v>deux</v></c></row>')]
    espace = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook %s xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>%s</sheets></workbook>'
                   % (espace, "".join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (n, i, i) for i, (n, _) in enumerate(feuilles, 1))))
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">%s</Relationships>'
                   % "".join('<Relationship Id="rId%d" Target="worksheets/sheet%d.xml"/>' % (i, i) for i in range(1, len(feuilles) + 1)))
        z.writestr("xl/sharedStrings.xml", '<?xml version="1.0"?><sst %s><si><t>Produit</t></si><si><t>Quantite</t></si><si><t>Date</t></si><si><t>Café; à "emporter"</t></si></sst>' % espace)
        z.writestr("xl/styles.xml", '<?xml version="1.0"?><styleSheet %s><cellXfs><xf numFmtId="0"/><xf numFmtId="%d"/></cellXfs></styleSheet>' % (espace, 14 if dates else 0))
        for i, (_, lignes) in enumerate(feuilles, 1):
            z.writestr("xl/worksheets/sheet%d.xml" % i, '<?xml version="1.0"?><worksheet %s><sheetData>%s</sheetData></worksheet>' % (espace, lignes))


class TestXlsxVersCsv(CasOutil):
    def lire_csv(self, chemin):
        with open(chemin, encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f, delimiter=";"))

    def test_premiere_feuille_valeurs_dates_et_lignes_vides(self):
        classeur = self.chemin("d", "ventes.xlsx")
        os.makedirs(os.path.dirname(classeur))
        fabriquer_xlsx(classeur)
        self.assertEqual(self.lancer(xlsx_vers_csv, classeur), 0, self.erreur)
        self.assertEqual(self.lire_csv(self.chemin("d", "ventes.csv")), [
            ["Produit", "Quantite", "Date"],
            ['Café; à "emporter"', "12", "2025-01-21"],
            [],
            ["direct", "", "3.5", "VRAI"]])
        self.assertTrue(self.lire(self.chemin("d", "ventes.csv")).startswith(b"\xef\xbb\xbf"))
        self.controler_journal("xlsx_vers_csv", "SUCCES")
        self.assertEqual(self.lignes("feuille_convertie")[0]["lignes"], 3)

    def test_feuille_par_nom_par_numero_et_toutes(self):
        classeur = self.chemin("c.xlsx")
        fabriquer_xlsx(classeur)
        self.assertEqual(self.lancer(xlsx_vers_csv, classeur, "--feuille", "Autre", "--sortie", self.chemin("autre.csv")), 0)
        self.assertEqual(self.lire_csv(self.chemin("autre.csv")), [["deux"]])
        self.assertEqual(self.lancer(xlsx_vers_csv, classeur, "--feuille", "2", "--sortie", self.chemin("n2.csv")), 0)
        self.assertEqual(self.lire_csv(self.chemin("n2.csv")), [["deux"]])
        self.assertEqual(self.lancer(xlsx_vers_csv, classeur, "--toutes-les-feuilles", "--vers", self.chemin("out")), 0)
        self.assertEqual(self.arbre(self.chemin("out")), ["c_Autre.csv", "c_Ventes.csv"])
        self.assertEqual(self.lancer(xlsx_vers_csv, classeur, "--feuille", "Inconnue"), 2)

    def test_separateur_encodage_et_dates_desactivees(self):
        classeur = self.chemin("c.xlsx")
        fabriquer_xlsx(classeur, dates=False)
        self.assertEqual(self.lancer(xlsx_vers_csv, classeur, "--separateur", ",", "--encodage", "utf-8", "--sortie", self.chemin("c.csv")), 0)
        with open(self.chemin("c.csv"), encoding="utf-8", newline="") as f:
            lignes = list(csv.reader(f))
        self.assertEqual(lignes[1][2], "45678")                      # sans format de date : le nombre brut
        self.assertEqual(self.lancer(xlsx_vers_csv, classeur, "--separateur", ";;"), 3)
        self.assertEqual(self.lancer(xlsx_vers_csv, classeur, "--encodage", "inconnu"), 3)

    def test_ecraser_et_simulation(self):
        classeur = self.chemin("c.xlsx")
        fabriquer_xlsx(classeur)
        self.assertEqual(self.lancer(xlsx_vers_csv, classeur, "--simulation"), 0)
        self.assertFalse(os.path.exists(self.chemin("c.csv")))
        self.controler_journal("xlsx_vers_csv", simulation=True)
        self.assertEqual(self.lancer(xlsx_vers_csv, classeur), 0)
        self.assertEqual(self.lancer(xlsx_vers_csv, classeur), 2)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "DUPLICATE_ENTITY")
        self.assertEqual(self.lancer(xlsx_vers_csv, classeur, "--ecraser"), 0)

    def test_fichiers_invalides_les_autres_sont_convertis(self):
        faux = self.ecrire("faux.xlsx", b"pas un zip")
        texte = self.ecrire("notes.txt")
        bon = self.chemin("bon.xlsx")
        fabriquer_xlsx(bon)
        self.assertEqual(self.lancer(xlsx_vers_csv, faux, texte, self.chemin("absent.xlsx"), bon), 2)
        self.assertTrue(os.path.exists(self.chemin("bon.csv")))
        self.assertFalse(os.path.exists(self.chemin("faux.csv")))
        self.assertEqual([n for n in os.listdir(self.racine) if n.endswith(".copie_en_cours")], [])

    def test_sortie_incompatible(self):
        a, b = self.chemin("a.xlsx"), self.chemin("b.xlsx")
        fabriquer_xlsx(a)
        fabriquer_xlsx(b)
        self.assertEqual(self.lancer(xlsx_vers_csv, a, b, "--sortie", self.chemin("x.csv")), 3)
        self.assertEqual(self.lancer(xlsx_vers_csv, a, "--toutes-les-feuilles", "--sortie", self.chemin("x.csv")), 3)


class TestDocumentVersPdf(CasOutil):
    FAUX_SOFFICE = """
        import os, sys
        a = sys.argv[1:]
        ici = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(ici, "appels.txt"), "a") as f:
            f.write(" ".join(a) + "\\n")
        if os.path.exists(os.path.join(ici, "echec")):
            print("conversion impossible")
            sys.exit(1)
        sortie = a[a.index("--outdir") + 1]
        document = a[-1]
        os.makedirs(sortie, exist_ok=True)
        base = os.path.splitext(os.path.basename(document))[0]
        with open(os.path.join(sortie, base + ".pdf"), "wb") as f:
            f.write(b"%PDF-1.4 faux")
    """

    def preparer(self):
        self.faux_soffice = self.faux_programme("soffice", self.FAUX_SOFFICE)
        self.env["OUTIL_SOFFICE"] = self.faux_soffice
        self.appels = os.path.join(os.path.dirname(self.faux_soffice), "appels.txt")
        self.echec = os.path.join(os.path.dirname(self.faux_soffice), "echec")

    def test_conversion_a_cote_du_document_et_profil_temporaire(self):
        self.preparer()
        doc = self.ecrire("d/rapport.docx")
        self.assertEqual(self.lancer(document_vers_pdf, doc), 0, self.erreur)
        self.assertEqual(self.lire(self.chemin("d", "rapport.pdf")), b"%PDF-1.4 faux")
        with open(self.appels, encoding="utf-8") as f:
            appel = f.read()
        self.assertIn("--headless", appel)
        self.assertIn("-env:UserInstallation=file:///", appel)
        self.assertIn("--convert-to pdf", appel)
        self.controler_journal("document_vers_pdf", "SUCCES")
        self.assertEqual([n for n in os.listdir(os.path.dirname(self.chemin("d", "x"))) if n.endswith(".copie_en_cours")], [])

    def test_dossier_de_sortie_ecraser_et_simulation(self):
        self.preparer()
        doc = self.ecrire("d/rapport.docx")
        self.assertEqual(self.lancer(document_vers_pdf, doc, "--vers", self.chemin("pdf")), 0)
        self.assertTrue(os.path.isfile(self.chemin("pdf", "rapport.pdf")))
        self.assertEqual(self.lancer(document_vers_pdf, doc, "--vers", self.chemin("pdf")), 2)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "DUPLICATE_ENTITY")
        self.assertEqual(self.lancer(document_vers_pdf, doc, "--vers", self.chemin("pdf"), "--ecraser"), 0)
        os.remove(self.chemin("pdf", "rapport.pdf"))
        self.assertEqual(self.lancer(document_vers_pdf, doc, "--vers", self.chemin("pdf"), "--simulation"), 0)
        self.assertFalse(os.path.exists(self.chemin("pdf", "rapport.pdf")))
        self.assertEqual(len(self.lignes("document_a_convertir")), 1)

    def test_echec_de_libreoffice_et_format_non_pris_en_charge(self):
        self.preparer()
        doc = self.ecrire("d/rapport.docx")
        autre = self.ecrire("d/image.png")
        self.ecrire("faux/echec", b"")
        code = self.lancer(document_vers_pdf, autre, doc)
        self.assertEqual(code, 2)
        types = sorted(b["error"]["type"] for b in self.erreurs_journal() if b["context"]["event"] != "outil_termine")
        self.assertEqual(types, ["BUSINESS_RULE_VIOLATION", "EXTERNAL_SERVICE_ERROR"])
        self.assertFalse(os.path.exists(self.chemin("d", "rapport.pdf")))

    def test_libreoffice_absent_code_4(self):
        doc = self.ecrire("d/rapport.docx")
        with mock.patch("outils.commun.dependances.trouver_programme",
                        side_effect=__import__("outils.commun.erreurs", fromlist=["x"]).DependanceAbsente("LibreOffice absent")):
            self.assertEqual(self.lancer(document_vers_pdf, doc), 4)
        self.assertIn("LibreOffice absent", self.sortie + self.erreur)
        self.assertNotIn("Traceback", self.sortie + self.erreur)
        self.controler_journal("document_vers_pdf", "ERREUR")

    def test_rien_a_convertir_ne_cherche_pas_libreoffice(self):
        self.assertEqual(self.lancer(document_vers_pdf, self.chemin("vide"), "--code-si-rien", "1") in (1, 2), True)


@unittest.skipIf(Image is None, "Pillow absent")
class TestImageConvertir(CasOutil):
    def image(self, chemin_relatif, taille=(40, 20), format_="PNG", mode="RGB", couleur=(200, 30, 30)):
        chemin = self.chemin(chemin_relatif)
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with Image.new(mode, taille, couleur) as im:
            im.save(chemin, format_)
        return chemin

    def dimensions(self, chemin):
        with Image.open(chemin) as im:
            return im.size, im.format

    def test_png_vers_jpg_et_retour(self):
        png = self.image("src/a.png", mode="RGBA", couleur=(10, 20, 30, 0))
        self.assertEqual(self.lancer(image_convertir, png, "--format", "jpg", "--vers", self.chemin("out")), 0, self.erreur)
        self.assertEqual(self.dimensions(self.chemin("out", "a.jpg")), ((40, 20), "JPEG"))
        self.assertEqual(self.lancer(image_convertir, self.chemin("out", "a.jpg"), "--format", "png", "--vers", self.chemin("out2")), 0)
        self.assertEqual(self.dimensions(self.chemin("out2", "a.png")), ((40, 20), "PNG"))
        self.assertTrue(os.path.exists(png))
        self.controler_journal("image_convertir")

    def test_redimensionnement_proportionnel_sans_agrandissement(self):
        grande = self.image("src/grande.png", taille=(400, 200))
        petite = self.image("src/petite.png", taille=(40, 20))
        self.assertEqual(self.lancer(image_convertir, grande, petite, "--largeur-max", "100", "--vers", self.chemin("out")), 0, self.erreur)
        self.assertEqual(self.dimensions(self.chemin("out", "grande.png"))[0], (100, 50))
        self.assertEqual(self.dimensions(self.chemin("out", "petite.png"))[0], (40, 20))
        self.lancer(image_convertir, grande, "--hauteur-max", "20", "--vers", self.chemin("o2"))
        self.assertEqual(self.dimensions(self.chemin("o2", "grande.png"))[0], (40, 20))

    def test_qualite_reduit_la_taille_d_un_jpeg(self):
        import random
        alea = random.Random(1)
        chemin = self.chemin("src", "photo.jpg")
        os.makedirs(os.path.dirname(chemin))
        with Image.new("RGB", (120, 120)) as im:
            im.putdata([(alea.randrange(256), alea.randrange(256), alea.randrange(256)) for _ in range(120 * 120)])
            im.save(chemin, quality=95)
        self.assertEqual(self.lancer(image_convertir, chemin, "--qualite", "20", "--vers", self.chemin("out")), 0)
        self.assertLess(os.path.getsize(self.chemin("out", "photo.jpg")), os.path.getsize(chemin))

    def test_sur_place_garde_l_original_s_il_n_y_a_rien_a_gagner(self):
        png = self.image("a.png")
        self.assertEqual(self.lancer(image_convertir, png, "--sur-place"), 0)          # premiere passe : optimisee
        avant = self.lire(png)
        self.assertEqual(self.lancer(image_convertir, png, "--sur-place"), 0)          # deuxieme : plus rien a gagner
        self.assertEqual(self.lire(png), avant)
        self.assertIn("deja_optimales=1", self.sortie)
        grande = self.image("g.png", taille=(300, 300))
        self.assertEqual(self.lancer(image_convertir, grande, "--sur-place", "--largeur-max", "50"), 0)
        self.assertEqual(self.dimensions(grande)[0], (50, 50))

    def test_sur_place_avec_changement_de_format_cree_a_cote(self):
        png = self.image("a.png")
        self.assertEqual(self.lancer(image_convertir, png, "--sur-place", "--format", "jpg"), 0)
        self.assertEqual(self.dimensions(self.chemin("a.jpg"))[1], "JPEG")
        self.assertTrue(os.path.exists(png))

    def test_exif_conserve_pour_les_jpeg(self):
        chemin = self.chemin("src", "p.jpg")
        os.makedirs(os.path.dirname(chemin))
        exif = Image.Exif()
        exif[0x8769] = {0x9003: "2020:01:02 03:04:05"}
        with Image.new("RGB", (80, 80)) as im:
            im.save(chemin, exif=exif)
        self.assertEqual(self.lancer(image_convertir, chemin, "--largeur-max", "40", "--vers", self.chemin("out")), 0)
        from outils.commun import exif as lecteur
        self.assertEqual(str(lecteur.date_prise_de_vue(self.chemin("out", "p.jpg"))), "2020-01-02 03:04:05")

    def test_simulation_ecraser_et_erreurs(self):
        png = self.image("src/a.png")
        self.assertEqual(self.lancer(image_convertir, png, "--format", "jpg", "--vers", self.chemin("out"), "--simulation"), 0)
        self.assertFalse(os.path.exists(self.chemin("out")))
        self.controler_journal("image_convertir", simulation=True)
        self.assertEqual(self.lancer(image_convertir, png, "--format", "jpg", "--vers", self.chemin("out")), 0)
        self.assertEqual(self.lancer(image_convertir, png, "--format", "jpg", "--vers", self.chemin("out")), 2)
        self.assertEqual(self.lancer(image_convertir, png, "--format", "jpg", "--vers", self.chemin("out"), "--ecraser"), 0)
        casse = self.ecrire("src/casse.png", b"pas une image")
        texte = self.ecrire("src/notes.txt")
        code = self.lancer(image_convertir, casse, texte, self.chemin("src", "absente.png"), png, "--format", "webp", "--vers", self.chemin("w"))
        self.assertEqual(code, 2)
        self.assertTrue(os.path.exists(self.chemin("w", "a.webp")))                     # la bonne image est convertie malgre les erreurs
        self.assertEqual([n for n in self.arbre() if n.endswith(".copie_en_cours")], [])

    def test_parametres_invalides(self):
        png = self.image("a.png")
        self.assertEqual(self.lancer(image_convertir, png), 3)
        self.assertEqual(self.lancer(image_convertir, png, "--sur-place", "--vers", self.chemin("o")), 3)
        self.assertEqual(self.lancer(image_convertir, png, "--sur-place", "--qualite", "0"), 3)
        self.assertEqual(self.lancer(image_convertir, png, "--sur-place", "--largeur-max", "0"), 3)
        self.assertEqual(self.lancer(image_convertir, png, "--sur-place", "--format", "psd"), 3)


class TestImageSansPillow(CasOutil):
    def test_pillow_absent_code_4_sans_trace(self):
        png = self.ecrire("a.png", b"x")
        with mock.patch.dict("sys.modules", {"PIL": None}):
            code = self.lancer(image_convertir, png, "--sur-place")
        self.assertEqual(code, 4)
        self.assertIn("Pillow", self.sortie + self.erreur)
        self.assertNotIn("Traceback", self.sortie + self.erreur)
        self.controler_journal("image_convertir", "ERREUR")


if __name__ == "__main__":
    unittest.main()
