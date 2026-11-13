"""Boite a outils : compression (zip, tar, 7z, rar, iso, zip chiffre, decoupage de gros fichiers)."""
import hashlib
import json
import os
import sys
import tarfile
import types
import unittest
import zipfile
from unittest import mock

from outils.compression import (archive_creer, archive_extraire, fichier_decouper, fichier_recoller, zip_chiffrer,
                                zip_creer, zip_extraire)
from tests.boite_outils import CasOutil

ABSENT = {"OUTIL_7Z": "Z:\\absent\\7z.exe", "OUTIL_RAR": "Z:\\absent\\rar.exe"}
FAUX_7Z = '''
    import json, os, sys
    a = sys.argv[1:]
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "appels.jsonl"), "a") as f:
        f.write(json.dumps(a) + "\\n")
    if a[0] == "a":
        archive = [x for x in a[2:] if not x.startswith("-")][0]
        open(archive, "wb").write(b"FAUX")
    elif a[0] == "x":
        sortie = [x[2:] for x in a if x.startswith("-o")][0]
        os.makedirs(sortie, exist_ok=True)
        open(os.path.join(sortie, "extrait.txt"), "w").write("ok")
    elif a[0] == "l":
        fichier = os.path.join(os.path.dirname(os.path.abspath(__file__)), "taille.txt")
        taille = open(fichier).read().strip() if os.path.exists(fichier) else "4"
        print("Path = a.bin\\nSize = " + taille + "\\nPacked Size = 1\\nPhysical Size = 99999999999")
    sys.exit(%d)
'''


class CasCompression(CasOutil):
    def noms_zip(self, chemin):
        with zipfile.ZipFile(chemin) as z:
            return sorted(z.namelist())

    def appels(self):
        chemin = os.path.join(self.chemin("faux"), "appels.jsonl")
        if not os.path.exists(chemin):
            return []
        with open(chemin, encoding="utf-8") as f:
            return [json.loads(l) for l in f]

    def faux(self, nom="7z", code=0):
        return self.faux_programme(nom, FAUX_7Z % code)

    def zip_malveillant(self, chemin, entrees):
        with zipfile.ZipFile(chemin, "w") as z:
            for nom, contenu in entrees:
                z.writestr(nom, contenu)
        return chemin

    def aucun_temporaire(self, dossier):
        for racine, dossiers, noms in os.walk(dossier):
            for n in noms + dossiers:
                self.assertFalse(n.endswith(".copie_en_cours"), os.path.join(racine, n))


class TestZipCreer(CasCompression):
    def preparer(self):
        self.ecrire("src/a.txt", b"AAA")
        self.ecrire("src/sous/b.csv", b"BBB")
        self.ecrire("src/sous/c.log", b"CCC")
        self.ecrire("seul.txt", "accentu\u00e9".encode("utf-8"))

    def test_fichiers_et_dossiers(self):
        self.preparer()
        code = self.lancer(zip_creer, self.chemin("src"), self.chemin("seul.txt"), "--sortie", self.chemin("o", "lot.zip"))
        self.assertEqual(code, 0, self.erreur)
        self.assertEqual(self.noms_zip(self.chemin("o", "lot.zip")),
                         ["seul.txt", "src/", "src/a.txt", "src/sous/", "src/sous/b.csv", "src/sous/c.log"])
        with zipfile.ZipFile(self.chemin("o", "lot.zip")) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(z.read("src/sous/b.csv"), b"BBB")
        self.assertIn("dossiers=2, fichiers=4", self.sortie)
        self.aucun_temporaire(self.racine)
        lignes = self.controler_journal("zip_creer", "SUCCES")
        evenements = [l["context"]["event"] for l in lignes]
        self.assertEqual(evenements.count("fichier_archive_ajoute"), 6)
        self.assertIn("archive_creee", evenements)
        self.assertEqual(self.lignes("archive_creee")[0]["fichier"], self.chemin("o", "lot.zip"))
        self.assertEqual(self.lignes("archive_creee")[0]["taille"], os.path.getsize(self.chemin("o", "lot.zip")))

    def test_masque_exclusion_et_liste(self):
        self.preparer()
        liste = self.ecrire("liste.txt", "%s\n%s\n" % (self.chemin("src"), self.chemin("seul.txt")))
        code = self.lancer(zip_creer, "--liste", liste, "--masque", "*.csv", "--masque", "*.txt", "--exclure", "a.*",
                           "--sortie", self.chemin("o.zip"))
        self.assertEqual(code, 0)
        self.assertEqual(self.noms_zip(self.chemin("o.zip")), ["seul.txt", "src/", "src/sous/", "src/sous/b.csv"])

    def test_l_archive_n_est_pas_ajoutee_a_elle_meme(self):
        self.preparer()
        self.assertEqual(self.lancer(zip_creer, self.chemin("src"), "--sortie", self.chemin("src", "lot.zip")), 0)
        self.assertNotIn("src/lot.zip", self.noms_zip(self.chemin("src", "lot.zip")))

    def test_simulation_n_ecrit_rien(self):
        self.preparer()
        code = self.lancer(zip_creer, self.chemin("src"), "--sortie", self.chemin("o.zip"), "--simulation")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(self.chemin("o.zip")))
        self.controler_journal("zip_creer", "SUCCES", simulation=True)
        self.assertEqual(len(self.lignes("fichier_a_archiver")), 5)
        self.assertEqual(self.lignes("fichier_archive_ajoute"), [])

    def test_ecraser(self):
        self.preparer()
        self.ecrire("o.zip", b"ancien")
        self.assertEqual(self.lancer(zip_creer, self.chemin("seul.txt"), "--sortie", self.chemin("o.zip")), 2)
        self.assertEqual(self.lire(self.chemin("o.zip")), b"ancien")
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "DUPLICATE_ENTITY")
        self.assertEqual(self.lancer(zip_creer, self.chemin("seul.txt"), "--sortie", self.chemin("o.zip"), "--ecraser"), 0)
        self.assertEqual(self.noms_zip(self.chemin("o.zip")), ["seul.txt"])
        self.assertEqual(self.lancer(zip_creer, self.chemin("seul.txt"), "--sortie", self.chemin("o.zip"), "--simulation"), 2)

    def test_un_element_introuvable_donne_le_code_2_et_pas_d_archive_incomplete(self):
        self.preparer()
        code = self.lancer(zip_creer, self.chemin("seul.txt"), self.chemin("absent.txt"), "--sortie", self.chemin("o.zip"))
        self.assertEqual(code, 2)
        self.assertFalse(os.path.exists(self.chemin("o.zip")))
        self.aucun_temporaire(self.racine)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "FILE_NOT_FOUND")
        self.assertEqual(len(self.lignes("fichier_archive_ajoute")), 1)           # l'autre element a ete traite

    def test_rien_a_archiver(self):
        self.assertEqual(self.lancer(zip_creer, "--sortie", self.chemin("o.zip"), "--code-si-rien", "1"), 1)
        self.assertFalse(os.path.exists(self.chemin("o.zip")))

    def test_variables_du_moteur(self):
        self.preparer()
        code = self.lancer(zip_creer, "--sortie", self.chemin("o.zip"), env={"COPIE_FICHIER": self.chemin("seul.txt")})
        self.assertEqual((code, self.noms_zip(self.chemin("o.zip"))), (0, ["seul.txt"]))


class TestZipExtraire(CasCompression):
    def archive(self, niveau="6"):
        self.ecrire("src/a.txt", b"AAA")
        self.ecrire("src/sous/b.txt", b"BBB")
        self.lancer(zip_creer, self.chemin("src"), "--sortie", self.chemin("lot.zip"), "--niveau", niveau)
        for nom in os.listdir(self.logs):
            os.remove(os.path.join(self.logs, nom))
        return self.chemin("lot.zip")

    def test_nominal(self):
        archive = self.archive()
        code = self.lancer(zip_extraire, archive, "--vers", self.chemin("dest"))
        self.assertEqual(code, 0, self.erreur)
        self.assertEqual(self.arbre(self.chemin("dest")), ["src/a.txt", "src/sous/b.txt"])
        self.assertEqual(self.lire(self.chemin("dest", "src", "sous", "b.txt")), b"BBB")
        self.controler_journal("zip_extraire", "SUCCES")
        self.assertEqual(len(self.lignes("fichier_extrait")), 2)
        self.aucun_temporaire(self.racine)

    def test_un_dossier_par_archive(self):
        self.assertEqual(self.lancer(zip_extraire, self.archive(), "--vers", self.chemin("dest"), "--un-dossier-par-archive"), 0)
        self.assertEqual(self.arbre(self.chemin("dest")), ["lot/src/a.txt", "lot/src/sous/b.txt"])

    def test_simulation(self):
        self.assertEqual(self.lancer(zip_extraire, self.archive(), "--vers", self.chemin("dest"), "--simulation"), 0)
        self.assertFalse(os.path.exists(self.chemin("dest")))
        self.controler_journal("zip_extraire", simulation=True)
        self.assertEqual(len(self.lignes("fichier_a_extraire")), 2)

    def test_ecraser(self):
        archive = self.archive()
        self.ecrire("dest/src/a.txt", b"ANCIEN")
        self.assertEqual(self.lancer(zip_extraire, archive, "--vers", self.chemin("dest")), 2)
        self.assertEqual(self.lire(self.chemin("dest", "src", "a.txt")), b"ANCIEN")
        self.assertEqual(self.lire(self.chemin("dest", "src", "sous", "b.txt")), b"BBB")      # l'autre est extrait
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "DUPLICATE_ENTITY")
        self.assertEqual(self.lancer(zip_extraire, archive, "--vers", self.chemin("dest"), "--ecraser"), 0)
        self.assertEqual(self.lire(self.chemin("dest", "src", "a.txt")), b"AAA")
        self.assertEqual(self.lancer(zip_extraire, archive, "--vers", self.chemin("dest"), "--simulation"), 2)

    def test_zip_slip_refuse(self):
        archive = self.zip_malveillant(self.chemin("mal.zip"), [
            ("../evil.txt", b"x"), ("a/../../evil2.txt", b"x"), ("/abs.txt", b"x"), ("C:/evil3.txt", b"x"),
            ("..\\evil4.txt", b"x"), ("ok.txt", b"ok")])
        code = self.lancer(zip_extraire, archive, "--vers", self.chemin("dest", "sous"))
        self.assertEqual(code, 2)
        self.assertEqual(self.arbre(self.chemin("dest")), ["sous/ok.txt"])             # rien n'est sorti du dossier
        for nom in ("evil.txt", "evil2.txt", "abs.txt", "evil3.txt", "evil4.txt"):
            self.assertFalse(os.path.exists(self.chemin(nom)), nom)
            self.assertFalse(os.path.exists(self.chemin("dest", nom)), nom)
        erreurs = [b for b in self.erreurs_journal() if b["context"]["event"] == "extraction_echec"]
        self.assertEqual(len(erreurs), 5)
        self.assertEqual({e["error"]["type"] for e in erreurs}, {"BUSINESS_RULE_VIOLATION"})

    def test_taille_maximale_extraite(self):
        archive = self.zip_malveillant(self.chemin("bombe.zip"), [("gros.txt", b"0" * 100000)])
        self.assertEqual(self.lancer(zip_extraire, archive, "--vers", self.chemin("dest"), "--taille-max", "10K"), 2)
        self.assertFalse(os.path.exists(self.chemin("dest", "gros.txt")))
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "RESOURCE_EXHAUSTED")
        self.assertEqual(self.lancer(zip_extraire, archive, "--vers", self.chemin("dest"), "--taille-max", "1M"), 0)

    def test_archive_corrompue_ou_pas_un_zip(self):
        self.ecrire("faux.zip", b"ceci n'est pas un zip")
        self.assertEqual(self.lancer(zip_extraire, self.chemin("faux.zip"), "--vers", self.chemin("dest")), 2)
        self.assertNotIn("Traceback", self.erreur)
        self.assertEqual(self.lancer(zip_extraire, self.ecrire("a.tar.gz"), "--vers", self.chemin("dest")), 2)   # pas un zip
        self.assertEqual(self.lancer(zip_extraire, self.chemin("absente.zip"), "--vers", self.chemin("dest")), 2)

    def test_zip_corrompu_au_milieu(self):
        archive = self.archive("0")
        octets = bytearray(self.lire(archive))
        i = octets.find(b"AAA")
        octets[i] = ord("Z")                                      # le CRC ne correspond plus
        with open(archive, "wb") as f:
            f.write(octets)
        self.assertEqual(self.lancer(zip_extraire, archive, "--vers", self.chemin("dest")), 2)
        self.assertEqual(self.arbre(self.chemin("dest")), ["src/sous/b.txt"])
        self.aucun_temporaire(self.racine)

    def test_zip_aes_sans_pyzipper_ni_7z_code_4(self):
        archive = self.zip_malveillant(self.chemin("aes.zip"), [("a.txt", b"secret")])
        octets = bytearray(self.lire(archive))
        j = octets.find(b"PK\x03\x04") + 8
        octets[j:j + 2] = (99).to_bytes(2, "little")
        i = octets.find(b"PK\x01\x02") + 10
        octets[i:i + 2] = (99).to_bytes(2, "little")
        with open(archive, "wb") as f:
            f.write(octets)
        with mock.patch.dict(sys.modules, {"pyzipper": None}):
            code = self.lancer(zip_extraire, archive, "--vers", self.chemin("dest"), env=ABSENT)
        self.assertEqual(code, 4)
        self.assertIn("pyzipper", self.erreur + "".join(b["message"] for b in self.brutes()))
        self.assertNotIn("Traceback", self.erreur)

    def test_mot_de_passe_inexistant_code_3(self):
        self.assertEqual(self.lancer(zip_extraire, self.archive(), "--vers", self.chemin("dest"), "--mot-de-passe-env", "ABSENTE"), 3)


class TestArchiveCreerExtraire(CasCompression):
    def preparer(self):
        self.ecrire("src/a.txt", b"AAA")
        self.ecrire("src/sous/b.txt", b"BBB")

    def test_formats_tar_aller_retour(self):
        self.preparer()
        for extension in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"):
            archive = self.chemin("o", "lot" + extension)
            self.assertEqual(self.lancer(archive_creer, self.chemin("src"), "--sortie", archive), 0, (extension, self.erreur))
            with tarfile.open(archive) as t:
                self.assertEqual(sorted(t.getnames()), ["src", "src/a.txt", "src/sous", "src/sous/b.txt"], extension)
            dest = self.chemin("dest" + extension.replace(".", "_"))
            self.assertEqual(self.lancer(archive_extraire, archive, "--vers", dest), 0, (extension, self.erreur))
            self.assertEqual(self.arbre(dest), ["src/a.txt", "src/sous/b.txt"], extension)
            self.assertEqual(self.lire(os.path.join(dest, "src", "sous", "b.txt")), b"BBB")
        self.aucun_temporaire(self.racine)

    def test_zip_par_archive_extraire(self):
        self.preparer()
        self.lancer(zip_creer, self.chemin("src"), "--sortie", self.chemin("lot.zip"))
        self.assertEqual(self.lancer(archive_extraire, self.chemin("lot.zip"), "--vers", self.chemin("dest")), 0)
        self.assertEqual(self.arbre(self.chemin("dest")), ["src/a.txt", "src/sous/b.txt"])

    def test_creer_simulation_et_ecraser(self):
        self.preparer()
        sortie = self.chemin("lot.tar.gz")
        self.assertEqual(self.lancer(archive_creer, self.chemin("src"), "--sortie", sortie, "--simulation"), 0)
        self.assertFalse(os.path.exists(sortie))
        self.controler_journal("archive_creer", simulation=True)
        self.ecrire("lot.tar.gz", b"ancien")
        self.assertEqual(self.lancer(archive_creer, self.chemin("src"), "--sortie", sortie), 2)
        self.assertEqual(self.lire(sortie), b"ancien")
        self.assertEqual(self.lancer(archive_creer, self.chemin("src"), "--sortie", sortie, "--ecraser"), 0)
        self.assertTrue(tarfile.is_tarfile(sortie))

    def test_extension_non_prise_en_charge_et_iso_en_creation(self):
        self.preparer()
        for nom in ("lot.zip", "lot.iso", "lot.bin", "lot"):
            self.assertEqual(self.lancer(archive_creer, self.chemin("src"), "--sortie", self.chemin(nom)), 3, nom)
        self.assertIn("iso", self.erreur)
        self.assertEqual(self.lancer(archive_creer, self.chemin("src"), "--sortie", self.chemin("lot.tar"),
                                     "--mot-de-passe-env", "MDP", env={"MDP": "x"}), 3)           # un tar ne se chiffre pas

    def test_extraction_tar_refuse_liens_et_chemins_dangereux(self):
        chemin = self.chemin("mal.tar")
        with tarfile.open(chemin, "w") as t:
            for nom, contenu in (("../evil.txt", b"x"), ("ok.txt", b"ok")):
                info = tarfile.TarInfo(nom)
                info.size = len(contenu)
                import io
                t.addfile(info, io.BytesIO(contenu))
            lien = tarfile.TarInfo("lien")
            lien.type, lien.linkname = tarfile.SYMTYPE, "../../secret"
            t.addfile(lien)
            dur = tarfile.TarInfo("dur")
            dur.type, dur.linkname = tarfile.LNKTYPE, "ok.txt"
            t.addfile(dur)
        self.assertEqual(self.lancer(archive_extraire, chemin, "--vers", self.chemin("dest", "s")), 2)
        self.assertEqual(self.arbre(self.chemin("dest")), ["s/ok.txt"])
        self.assertFalse(os.path.exists(self.chemin("dest", "evil.txt")))
        self.assertEqual(len([b for b in self.erreurs_journal() if b["context"]["event"] == "extraction_echec"]), 3)

    def test_extraction_tar_ecraser_simulation_et_corruption(self):
        self.preparer()
        archive = self.chemin("lot.tar.gz")
        self.lancer(archive_creer, self.chemin("src"), "--sortie", archive)
        self.ecrire("dest/src/a.txt", b"ANCIEN")
        self.assertEqual(self.lancer(archive_extraire, archive, "--vers", self.chemin("dest")), 2)
        self.assertEqual(self.lancer(archive_extraire, archive, "--vers", self.chemin("dest"), "--ecraser"), 0)
        self.assertEqual(self.lire(self.chemin("dest", "src", "a.txt")), b"AAA")
        self.assertEqual(self.lancer(archive_extraire, archive, "--vers", self.chemin("autre"), "--simulation"), 0)
        self.assertFalse(os.path.exists(self.chemin("autre")))
        self.ecrire("casse.tar.gz", self.lire(archive)[:40])
        self.assertEqual(self.lancer(archive_extraire, self.chemin("casse.tar.gz"), "--vers", self.chemin("autre")), 2)
        self.assertNotIn("Traceback", self.erreur)

    def test_format_inconnu(self):
        self.assertEqual(self.lancer(archive_extraire, self.ecrire("a.xyz"), "--vers", self.chemin("dest")), 2)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "BUSINESS_RULE_VIOLATION")

    # ----- 7z, rar, iso : faux programme (7-Zip et WinRAR ne sont pas installes sur le poste de developpement) ----- #
    def test_7z_creation_avec_un_faux_programme(self):
        self.preparer()
        faux = self.faux("7z")
        self.ecrire("autre/src/z.txt", b"Z")
        code = self.lancer(archive_creer, self.chemin("src"), self.chemin("autre", "src"), "--sortie", self.chemin("o", "lot.7z"),
                           env={"OUTIL_7Z": faux})
        self.assertEqual(code, 2)                                      # deux elements de meme nom : refuse
        self.assertEqual(self.appels(), [])
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "DUPLICATE_ENTITY")
        code = self.lancer(archive_creer, self.chemin("src"), "--sortie", self.chemin("o", "lot.7z"), env={"OUTIL_7Z": faux})
        self.assertEqual(code, 0, self.erreur)
        (appel,) = self.appels()
        self.assertEqual(appel[:2], ["a", "-t7z"])
        self.assertIn(self.chemin("src"), appel)
        self.assertTrue(os.path.isfile(self.chemin("o", "lot.7z")))
        self.aucun_temporaire(self.racine)

    def test_rar_creation_avec_un_faux_programme(self):
        self.preparer()
        faux = self.faux("rar")
        self.assertEqual(self.lancer(archive_creer, self.chemin("src"), "--sortie", self.chemin("lot.rar"), env={"OUTIL_RAR": faux}), 0)
        self.assertEqual(self.appels()[0][0], "a")
        self.assertTrue(os.path.isfile(self.chemin("lot.rar")))

    def test_7z_et_rar_absents_code_4_meme_en_simulation(self):
        self.preparer()
        for nom, programme in (("lot.7z", "7z"), ("lot.rar", "rar")):
            for option in ((), ("--simulation",)):
                code = self.lancer(archive_creer, self.chemin("src"), "--sortie", self.chemin(nom), *option, env=ABSENT)
                self.assertEqual(code, 4, (nom, option))
                self.assertFalse(os.path.exists(self.chemin(nom)))
        self.assertNotIn("Traceback", self.erreur)

    def test_7z_code_retour_d_echec_et_d_avertissement(self):
        self.preparer()
        self.assertEqual(self.lancer(archive_creer, self.chemin("src"), "--sortie", self.chemin("lot.7z"),
                                     env={"OUTIL_7Z": self.faux("7z", 2)}), 2)
        self.assertFalse(os.path.exists(self.chemin("lot.7z")))
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "EXTERNAL_SERVICE_ERROR")
        self.aucun_temporaire(self.racine)
        for nom in os.listdir(self.logs):
            os.remove(os.path.join(self.logs, nom))
        self.assertEqual(self.lancer(archive_creer, self.chemin("src"), "--sortie", self.chemin("lot2.7z"),
                                     env={"OUTIL_7Z": self.faux("7z", 1)}), 0)
        self.assertEqual(self.lignes("programme_externe_avertissement")[0]["niveau"], "WARNING")

    def test_7z_extraction_iso_rar_avec_un_faux_programme(self):
        faux = self.faux("7z")
        for nom in ("a.7z", "a.rar", "a.iso"):
            archive = self.ecrire(nom, b"FAUX")
            dest = self.chemin("dest_" + nom.replace(".", "_"))
            self.assertEqual(self.lancer(archive_extraire, archive, "--vers", dest, env={"OUTIL_7Z": faux}), 0, self.erreur)
            self.assertEqual(self.arbre(dest), ["extrait.txt"])
        self.assertEqual([a[0] for a in self.appels()[:2]], ["l", "x"])    # taille annoncee d'abord, puis extraction
        appel = self.appels()[1]
        self.assertIn("-aos", appel)                                   # rien n'est ecrase
        self.assertEqual(self.lancer(archive_extraire, self.chemin("a.iso"), "--vers", self.chemin("d2"), "--ecraser",
                                     env={"OUTIL_7Z": faux}), 0)
        self.assertIn("-aoa", self.appels()[-1])
        self.assertEqual(self.lancer(archive_extraire, self.chemin("a.iso"), "--vers", self.chemin("d3"), "--simulation",
                                     env={"OUTIL_7Z": faux}), 0)
        self.assertEqual(self.appels()[-1][0], "l")
        self.assertFalse(os.path.exists(self.chemin("d3")))

    def test_7z_extraction_refusee_si_la_taille_annoncee_depasse_la_limite(self):
        faux = self.faux("7z")
        self.ecrire("faux/taille.txt", b"5000000")
        archive = self.ecrire("a.7z", b"FAUX")
        code = self.lancer(archive_extraire, archive, "--vers", self.chemin("dest"), "--taille-max", "1M", env={"OUTIL_7Z": faux})
        self.assertEqual(code, 2)
        self.assertEqual([a[0] for a in self.appels()], ["l"])         # jamais d'extraction
        self.assertFalse(os.path.exists(self.chemin("dest")))
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "RESOURCE_EXHAUSTED")
        self.assertEqual(self.lancer(archive_extraire, archive, "--vers", self.chemin("dest"), "--taille-max", "10M",
                                     env={"OUTIL_7Z": faux}), 0)

    def test_7z_absent_pour_l_extraction_code_4(self):
        self.assertEqual(self.lancer(archive_extraire, self.ecrire("a.iso"), "--vers", self.chemin("dest"), env=ABSENT), 4)
        self.assertEqual(self.lancer(archive_extraire, self.ecrire("a.zip", b"PK"), "--vers", self.chemin("dest"), env=ABSENT), 2)

    def test_mot_de_passe_7z_jamais_dans_le_journal_ni_la_sortie(self):
        self.preparer()
        faux = self.faux("7z")
        code = self.lancer(archive_creer, self.chemin("src"), "--sortie", self.chemin("lot.7z"), "--mot-de-passe-env", "MDP",
                           env={"OUTIL_7Z": faux, "MDP": "T0pS3cret"})
        self.assertEqual(code, 0, self.erreur)
        appel = self.appels()[0]
        self.assertIn("-pT0pS3cret", appel)                            # 7z l'exige : c'est signale dans le journal
        self.assertIn("-mhe=on", appel)
        self.assertEqual(len(self.lignes("mot_de_passe_ligne_de_commande")), 1)
        texte = self.texte_journal()
        self.assertNotIn("T0pS3cret", texte + self.sortie + self.erreur)


class FauxPyzipper(types.ModuleType):
    """Module factice : un zip ordinaire qui enregistre le mot de passe et le chiffrement demandes."""
    WZ_AES = "WZ_AES"
    appels = []

    def __init__(self):
        types.ModuleType.__init__(self, "pyzipper")
        module = self

        class AESZipFile(zipfile.ZipFile):
            def setpassword(self, pwd):
                module.appels.append(("mot_de_passe", pwd))

            def setencryption(self, methode, nbits=256):
                module.appels.append(("chiffrement", methode, nbits))
        self.AESZipFile = AESZipFile


class TestZipChiffrer(CasCompression):
    def preparer(self):
        self.ecrire("src/a.txt", b"AAA")
        self.ecrire("src/b.txt", b"BBB")

    def test_pyzipper_aes256(self):
        self.preparer()
        faux = FauxPyzipper()
        faux.appels = []
        with mock.patch.dict(sys.modules, {"pyzipper": faux}):
            code = self.lancer(zip_chiffrer, self.chemin("src"), "--sortie", self.chemin("secret.zip"),
                               "--mot-de-passe-env", "MDP", env={"MDP": "T0pS3cret"})
        self.assertEqual(code, 0, self.erreur)
        self.assertIn(("mot_de_passe", b"T0pS3cret"), faux.appels)
        self.assertIn(("chiffrement", "WZ_AES", 256), faux.appels)
        self.assertEqual(self.noms_zip(self.chemin("secret.zip")), ["src/", "src/a.txt", "src/b.txt"])
        texte = self.texte_journal()
        self.assertNotIn("T0pS3cret", texte + self.sortie + self.erreur)
        fin = self.controler_journal("zip_chiffrer", "SUCCES")
        self.assertEqual(self.lignes("archive_creee")[0]["chiffrement"], "AES-256")
        self.assertEqual(self.lignes("archive_creee")[0]["moteur"], "pyzipper")
        self.assertEqual(self.lignes("mot_de_passe_ligne_de_commande"), [])     # pyzipper : pas de ligne de commande

    def test_mot_de_passe_obligatoire_et_jamais_en_ligne_de_commande(self):
        self.preparer()
        self.assertEqual(self.lancer(zip_chiffrer, self.chemin("src"), "--sortie", self.chemin("s.zip")), 3)
        self.assertEqual(self.lancer(zip_chiffrer, self.chemin("src"), "--sortie", self.chemin("s.zip"), "--mot-de-passe", "x"), 3)
        self.assertIn("parametres invalides", self.erreur)

    def test_mot_de_passe_dans_un_fichier(self):
        self.preparer()
        mdp = self.ecrire("mdp.txt", "fichier-S3cret\n")
        faux = FauxPyzipper()
        faux.appels = []
        with mock.patch.dict(sys.modules, {"pyzipper": faux}):
            self.assertEqual(self.lancer(zip_chiffrer, self.chemin("src"), "--sortie", self.chemin("s.zip"),
                                         "--mot-de-passe-fichier", mdp), 0)
        self.assertIn(("mot_de_passe", b"fichier-S3cret"), faux.appels)

    def test_simulation_et_ecraser(self):
        self.preparer()
        faux = FauxPyzipper()
        faux.appels = []
        options = ("--mot-de-passe-env", "MDP")
        with mock.patch.dict(sys.modules, {"pyzipper": faux}):
            self.assertEqual(self.lancer(zip_chiffrer, self.chemin("src"), "--sortie", self.chemin("s.zip"), "--simulation",
                                         *options, env={"MDP": "x"}), 0)
            self.assertFalse(os.path.exists(self.chemin("s.zip")))
            self.controler_journal("zip_chiffrer", simulation=True)
            self.ecrire("s.zip", b"ancien")
            self.assertEqual(self.lancer(zip_chiffrer, self.chemin("src"), "--sortie", self.chemin("s.zip"), *options, env={"MDP": "x"}), 2)
            self.assertEqual(self.lire(self.chemin("s.zip")), b"ancien")
            self.assertEqual(self.lancer(zip_chiffrer, self.chemin("src"), "--sortie", self.chemin("s.zip"), "--ecraser",
                                         *options, env={"MDP": "x"}), 0)

    def test_sans_pyzipper_ni_7z_code_4(self):
        self.preparer()
        with mock.patch.dict(sys.modules, {"pyzipper": None}):
            code = self.lancer(zip_chiffrer, self.chemin("src"), "--sortie", self.chemin("s.zip"), "--mot-de-passe-env", "MDP",
                               env=dict(ABSENT, MDP="x"))
        self.assertEqual(code, 4)
        self.assertFalse(os.path.exists(self.chemin("s.zip")))
        self.assertNotIn("Traceback", self.erreur)

    def test_repli_sur_7z_avec_avertissement_et_sans_fuite(self):
        self.preparer()
        faux = self.faux("7z")
        with mock.patch.dict(sys.modules, {"pyzipper": None}):
            code = self.lancer(zip_chiffrer, self.chemin("src"), "--sortie", self.chemin("s.zip"), "--mot-de-passe-env", "MDP",
                               env={"OUTIL_7Z": faux, "MDP": "T0pS3cret"})
        self.assertEqual(code, 0, self.erreur)
        appel = self.appels()[0]
        self.assertEqual(appel[:2], ["a", "-tzip"])
        self.assertIn("-mem=AES256", appel)
        self.assertEqual(len(self.lignes("mot_de_passe_ligne_de_commande")), 1)
        texte = self.texte_journal()
        self.assertNotIn("T0pS3cret", texte + self.sortie)
        self.assertEqual(self.lignes("archive_creee")[0]["moteur"], "7z")

    def test_moteur_pyzipper_impose_et_absent(self):
        self.preparer()
        with mock.patch.dict(sys.modules, {"pyzipper": None}):
            self.assertEqual(self.lancer(zip_chiffrer, self.chemin("src"), "--sortie", self.chemin("s.zip"), "--moteur", "pyzipper",
                                         "--mot-de-passe-env", "MDP", env={"MDP": "x"}), 4)


class TestDecouperRecoller(CasOutil):
    def gros(self, taille=2500000):
        contenu = os.urandom(taille)
        return self.ecrire("gros.bin", contenu), contenu

    def test_aller_retour_avec_manifeste(self):
        chemin, contenu = self.gros()
        self.assertEqual(self.lancer(fichier_decouper, chemin, "--taille", "1M"), 0, self.erreur)
        self.assertEqual(self.arbre(), sorted(["gros.bin", "gros.bin.001", "gros.bin.002", "gros.bin.003", "gros.bin.manifeste.json"]
                                              + [os.path.join("logs", n).replace("\\", "/") for n in os.listdir(self.logs)]))
        tailles = [os.path.getsize("%s.%03d" % (chemin, i)) for i in (1, 2, 3)]
        self.assertEqual(tailles, [1048576, 1048576, len(contenu) - 2097152])
        with open(chemin + ".manifeste.json", encoding="utf-8") as f:
            manifeste = json.load(f)
        self.assertEqual((manifeste["taille"], manifeste["sha256"]), (len(contenu), hashlib.sha256(contenu).hexdigest()))
        self.controler_journal("fichier_decouper", "SUCCES")
        self.assertEqual(self.lignes("fichier_decoupe")[0]["morceaux"], 3)
        os.remove(chemin)
        self.assertEqual(self.lancer(fichier_recoller, chemin + ".001"), 0, self.erreur)
        self.assertEqual(self.lire(chemin), contenu)
        self.assertTrue(self.lignes("fichier_recolle")[0]["verifie_par_manifeste"])

    def test_decouper_simulation_ecraser_source_et_fichier_petit(self):
        chemin, contenu = self.gros()
        self.assertEqual(self.lancer(fichier_decouper, chemin, "--taille", "1M", "--simulation"), 0)
        self.assertFalse(os.path.exists(chemin + ".001"))
        self.assertEqual(self.lignes("fichier_a_decouper")[0]["morceaux"], 3)
        self.lancer(fichier_decouper, chemin, "--taille", "1M")
        self.assertEqual(self.lancer(fichier_decouper, chemin, "--taille", "1M"), 2)           # morceaux existants
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "DUPLICATE_ENTITY")
        self.assertEqual(self.lancer(fichier_decouper, chemin, "--taille", "1M", "--ecraser", "--supprimer-source"), 0)
        self.assertFalse(os.path.exists(chemin))
        petit = self.ecrire("petit.txt", b"abc")
        self.assertEqual(self.lancer(fichier_decouper, petit, "--taille", "1M", "--code-si-rien", "1"), 1)
        self.assertFalse(os.path.exists(petit + ".001"))

    def test_decouper_vers_un_autre_dossier_sans_temporaire(self):
        chemin, _ = self.gros(300000)
        self.assertEqual(self.lancer(fichier_decouper, chemin, "--taille", "100K", "--vers", self.chemin("parts")), 0)
        self.assertEqual(sorted(os.listdir(self.chemin("parts"))), ["gros.bin.001", "gros.bin.002", "gros.bin.003",
                                                                  "gros.bin.manifeste.json"])

    def test_recoller_morceau_manquant(self):
        chemin, _ = self.gros()
        self.lancer(fichier_decouper, chemin, "--taille", "1M")
        os.remove(chemin)
        os.remove(chemin + ".002")
        self.assertEqual(self.lancer(fichier_recoller, chemin + ".001"), 2)
        self.assertFalse(os.path.exists(chemin))
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "FILE_NOT_FOUND")
        self.assertIn("gros.bin.002", self.erreur)

    def test_recoller_morceau_corrompu_n_ecrit_rien(self):
        chemin, _ = self.gros()
        self.lancer(fichier_decouper, chemin, "--taille", "1M")
        os.remove(chemin)
        with open(chemin + ".002", "r+b") as f:
            f.write(b"CORROMPU")
        self.assertEqual(self.lancer(fichier_recoller, chemin + ".001"), 2)
        self.assertFalse(os.path.exists(chemin))
        self.assertEqual([n for n in os.listdir(self.racine) if n.endswith(".copie_en_cours")], [])
        self.assertIn("SHA-256", self.erreur)

    def test_recoller_sans_manifeste_simulation_ecraser_et_suppression(self):
        chemin, contenu = self.gros(300000)
        self.lancer(fichier_decouper, chemin, "--taille", "100K")
        os.remove(chemin + ".manifeste.json")
        self.assertEqual(self.lancer(fichier_recoller, chemin + ".001", "--simulation", "--sortie", self.chemin("recolle.bin")), 0)
        self.assertFalse(os.path.exists(self.chemin("recolle.bin")))
        self.assertEqual(self.lignes("fichier_a_recoller")[0]["morceaux"], 3)
        self.assertEqual(self.lancer(fichier_recoller, chemin + ".001"), 2)                  # le fichier d'origine existe
        self.assertEqual(self.lancer(fichier_recoller, chemin + ".001", "--sortie", self.chemin("recolle.bin"),
                                     "--supprimer-morceaux"), 0)
        self.assertEqual(self.lire(self.chemin("recolle.bin")), contenu)
        self.assertEqual([n for n in os.listdir(self.racine) if ".00" in n], [])
        self.assertFalse(self.lignes("fichier_recolle")[0]["verifie_par_manifeste"])

    def test_recoller_ce_n_est_pas_un_morceau(self):
        self.assertEqual(self.lancer(fichier_recoller, self.ecrire("a.txt")), 2)
        self.assertEqual(self.lancer(fichier_recoller, self.ecrire("a.txt.002")), 2)

    def test_taille_invalide(self):
        self.assertEqual(self.lancer(fichier_decouper, self.ecrire("a.bin"), "--taille", "beaucoup"), 3)


if __name__ == "__main__":
    unittest.main()
