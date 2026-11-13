"""Boite a outils : controle (attente de stabilite, validation, empreintes, espace disque)."""
import collections
import hashlib
import os
import threading
import time
import unittest
from unittest import mock

from outils.controle import attendre_stable, empreinte, espace_disque, valider_fichier
from tests.boite_outils import CasOutil

WINDOWS = os.name == "nt"


def sha(octets, algo="sha256"):
    return hashlib.new(algo, octets).hexdigest()


class TestAttendreStable(CasOutil):
    RAPIDE = ("--duree-stable", "0.2", "--intervalle", "0.05")

    def test_fichier_deja_stable(self):
        a = self.ecrire("a.txt", b"fini")
        debut = time.monotonic()
        self.assertEqual(self.lancer(attendre_stable, a, *self.RAPIDE), 0, self.erreur)
        self.assertGreaterEqual(time.monotonic() - debut, 0.2)
        lignes = self.controler_journal("attendre_stable", "SUCCES")
        evenement = [l for l in lignes if l["context"]["event"] == "fichier_stable"][0]["context"]
        self.assertEqual(evenement["taille"], 4)

    def test_fichier_qui_grossit_puis_se_stabilise(self):
        a = self.ecrire("a.txt", b"0")
        arret = threading.Event()

        def ecrire():
            for _ in range(8):
                time.sleep(0.05)
                with open(a, "ab") as f:
                    f.write(b"x")
            arret.set()
        fil = threading.Thread(target=ecrire)
        fil.start()
        try:
            self.assertEqual(self.lancer(attendre_stable, a, *self.RAPIDE, "--delai-max", "10"), 0, self.erreur)
        finally:
            fil.join()
        self.assertTrue(arret.is_set())
        self.assertEqual(os.path.getsize(a), 9)                                      # l'outil a attendu la fin des ecritures

    def test_delai_depasse_si_le_fichier_change_toujours(self):
        a = self.ecrire("a.txt", b"0")
        continuer = threading.Event()
        continuer.set()

        def ecrire():
            while continuer.is_set():
                with open(a, "ab") as f:
                    f.write(b"x")
                time.sleep(0.03)
        fil = threading.Thread(target=ecrire)
        fil.start()
        try:
            code = self.lancer(attendre_stable, a, "--duree-stable", "0.5", "--intervalle", "0.05", "--delai-max", "0.6")
        finally:
            continuer.clear()
            fil.join()
        self.assertEqual(code, 2)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "TIMEOUT")

    def test_fichier_verrouille_est_attendu_puis_delai(self):
        a = self.ecrire("a.txt")
        with mock.patch.object(attendre_stable, "verrouille", return_value=True):
            self.assertEqual(self.lancer(attendre_stable, a, *self.RAPIDE, "--delai-max", "0.5"), 2)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "TIMEOUT")
        with mock.patch.object(attendre_stable, "verrouille", return_value=True) as sonde:
            self.assertEqual(self.lancer(attendre_stable, a, *self.RAPIDE, "--sans-verrou"), 0)
        sonde.assert_not_called()

    @unittest.skipUnless(WINDOWS, "verrou de partage : Windows")
    def test_verrou_reel_sous_windows(self):
        import ctypes
        from ctypes import wintypes
        a = self.ecrire("a.txt")
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        poignee = k32.CreateFileW(a, 0x80000000 | 0x40000000, 0, None, 3, 0x80, None)      # lecture+ecriture, aucun partage
        self.assertNotEqual(poignee, ctypes.c_void_p(-1).value)
        try:
            self.assertTrue(attendre_stable.verrouille(a))
            self.assertEqual(self.lancer(attendre_stable, a, *self.RAPIDE, "--delai-max", "0.5"), 2)
        finally:
            k32.CloseHandle(poignee)
        self.assertFalse(attendre_stable.verrouille(a))
        self.assertEqual(self.lancer(attendre_stable, a, *self.RAPIDE), 0)

    def test_fichier_absent_et_attendre_existence(self):
        absent = self.chemin("arrive.txt")
        self.assertEqual(self.lancer(attendre_stable, absent, *self.RAPIDE), 2)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "FILE_NOT_FOUND")

        def creer():
            time.sleep(0.3)
            with open(absent, "wb") as f:
                f.write(b"la")
        fil = threading.Thread(target=creer)
        fil.start()
        try:
            code = self.lancer(attendre_stable, absent, *self.RAPIDE, "--attendre-existence", "--delai-max", "10")
        finally:
            fil.join()
        self.assertEqual(code, 0, self.erreur)
        self.assertEqual(self.lancer(attendre_stable, self.chemin("jamais.txt"), *self.RAPIDE, "--attendre-existence", "--delai-max", "0.3"), 2)

    def test_plusieurs_fichiers_et_parametres(self):
        a, b = self.ecrire("a.txt"), self.ecrire("b.txt")
        self.assertEqual(self.lancer(attendre_stable, a, self.chemin("absent.txt"), b, *self.RAPIDE), 2)
        self.assertEqual(len(self.lignes("fichier_stable")), 2)                       # les autres sont attendus malgre l'erreur
        self.assertEqual(self.lancer(attendre_stable, a, "--delai-max", "0"), 3)
        self.assertEqual(self.lancer(attendre_stable, a, "--intervalle", "0"), 3)
        self.assertEqual(self.lancer(attendre_stable, a, "--duree-stable", "-1"), 3)

    def test_variable_du_moteur(self):
        a = self.ecrire("a.txt")
        self.assertEqual(self.lancer(attendre_stable, *self.RAPIDE, env={"COPIE_FICHIER": a}), 0)


class TestValiderFichier(CasOutil):
    def test_non_vide_par_defaut(self):
        plein, vide = self.ecrire("p.txt", b"x"), self.ecrire("v.txt", b"")
        self.assertEqual(self.lancer(valider_fichier, plein), 0, self.erreur)
        self.controler_journal("valider_fichier", "SUCCES")
        self.assertEqual(self.lancer(valider_fichier, vide), 2)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "BUSINESS_RULE_VIOLATION")
        self.assertIn("fichier vide", self.erreurs_journal()[0]["message"])

    def test_code_si_invalide_1_est_un_avertissement_qui_force_le_code_1(self):
        vide = self.ecrire("v.txt", b"")
        self.assertEqual(self.lancer(valider_fichier, vide, "--code-si-invalide", "1"), 1)
        self.assertEqual(self.erreurs_journal(), [])
        self.assertEqual(len(self.lignes("fichier_invalide", "WARNING")), 1)
        bon = self.ecrire("b.txt", b"x")
        self.assertEqual(self.lancer(valider_fichier, bon, vide, "--code-si-invalide", "1"), 1)       # un invalide parmi d'autres
        self.assertIn("valides=1", self.sortie)
        self.assertEqual(self.lancer(valider_fichier, bon, "--code-si-invalide", "1"), 0)

    def test_taille_min_et_max(self):
        a = self.ecrire("a.bin", b"x" * 100)
        self.assertEqual(self.lancer(valider_fichier, a, "--taille-min", "100", "--taille-max", "100"), 0)
        self.assertEqual(self.lancer(valider_fichier, a, "--taille-min", "101"), 2)
        self.assertEqual(self.lancer(valider_fichier, a, "--taille-max", "99"), 2)
        self.assertEqual(self.lancer(valider_fichier, a, "--taille-min", "beaucoup"), 3)

    def test_json_jsonl_xml(self):
        bon = self.ecrire("b.json", b'{"a": [1, 2]}')
        mauvais = self.ecrire("m.json", b'{"a": ')
        bom = self.ecrire("bom.json", b'\xef\xbb\xbf{"a": 1}')
        self.assertEqual(self.lancer(valider_fichier, bon, bom, "--format", "json"), 0)
        self.assertEqual(self.lancer(valider_fichier, mauvais, "--format", "json"), 2)
        jl = self.ecrire("l.jsonl", b'{"a":1}\n\n{"b":2}\n')
        jl_casse = self.ecrire("c.jsonl", b'{"a":1}\n{oups}\n')
        self.assertEqual(self.lancer(valider_fichier, jl, "--format", "jsonl"), 0)
        self.assertEqual(self.lancer(valider_fichier, jl_casse, "--format", "jsonl"), 2)
        self.assertIn("ligne 2", self.erreurs_journal()[-2]["message"])
        xml = self.ecrire("b.xml", b"<racine><a/></racine>")
        xml_casse = self.ecrire("m.xml", b"<racine><a></racine>")
        self.assertEqual(self.lancer(valider_fichier, xml, "--format", "xml"), 0)
        self.assertEqual(self.lancer(valider_fichier, xml_casse, "--format", "xml"), 2)

    def test_csv_largeur_colonnes_et_lignes_min(self):
        bon = self.ecrire("b.csv", b"id;nom\r\n1;A\r\n2;B\r\n")
        large = self.ecrire("l.csv", b"id;nom\r\n1;A;en_trop\r\n")
        self.assertEqual(self.lancer(valider_fichier, bon, "--format", "csv"), 0, self.erreur)
        self.assertEqual(self.lancer(valider_fichier, large, "--format", "csv"), 2)
        self.assertEqual(self.lancer(valider_fichier, bon, "--format", "csv", "--colonnes", "id,nom"), 0)
        self.assertEqual(self.lancer(valider_fichier, bon, "--format", "csv", "--colonnes", "id,prenom"), 2)
        self.assertEqual(self.lancer(valider_fichier, bon, "--format", "csv", "--colonnes", "nom,id"), 2)            # l'ordre compte
        self.assertEqual(self.lancer(valider_fichier, bon, "--format", "csv", "--nb-colonnes", "3"), 2)
        self.assertEqual(self.lancer(valider_fichier, bon, "--format", "csv", "--lignes-min", "2"), 0)
        self.assertEqual(self.lancer(valider_fichier, bon, "--format", "csv", "--lignes-min", "3"), 2)
        entete_seul = self.ecrire("e.csv", b"id;nom\r\n")
        self.assertEqual(self.lancer(valider_fichier, entete_seul, "--format", "csv", "--lignes-min", "1"), 2)
        self.assertEqual(self.lancer(valider_fichier, bon, "--format", "csv", "--sans-entete", "--lignes-min", "3"), 0)

    def test_csv_separateur_detecte_et_bom_dans_l_en_tete(self):
        virgule = self.ecrire("v.csv", b"a,b\n1,2\n")
        self.assertEqual(self.lancer(valider_fichier, virgule, "--format", "csv", "--colonnes", "a,b"), 0)
        bom = self.ecrire("bom.csv", b"\xef\xbb\xbfid;nom\r\n1;A\r\n")
        self.assertEqual(self.lancer(valider_fichier, bom, "--format", "csv", "--colonnes", "id,nom"), 0)
        tab = self.ecrire("t.csv", b"a\tb\n1\t2\n")
        self.assertEqual(self.lancer(valider_fichier, tab, "--format", "csv", "--separateur", "\t", "--nb-colonnes", "2"), 0)
        self.assertEqual(self.lancer(valider_fichier, self.ecrire("z.csv", b"\n\n"), "--format", "csv", "--taille-min", "1"), 2)

    def test_encodage(self):
        utf8 = self.ecrire("u.txt", "café".encode("utf-8"))
        ansi = self.ecrire("a.txt", "café".encode("cp1252"))
        self.assertEqual(self.lancer(valider_fichier, utf8, "--encodage", "utf-8"), 0)
        self.assertEqual(self.lancer(valider_fichier, ansi, "--encodage", "utf-8"), 2)
        self.assertEqual(self.lancer(valider_fichier, ansi, "--encodage", "cp1252"), 0)

    def test_parametres_invalides(self):
        a = self.ecrire("a.txt")
        self.assertEqual(self.lancer(valider_fichier, a, "--colonnes", "a,b"), 3)
        self.assertEqual(self.lancer(valider_fichier, a, "--encodage", "inconnu"), 3)
        self.assertEqual(self.lancer(valider_fichier, a, "--code-si-invalide", "3"), 3)
        self.assertEqual(self.lancer(valider_fichier, a, "--format", "yaml"), 3)

    def test_dossier_recursif_masque_et_fichier_absent(self):
        self.ecrire("d/a.json", b"{}")
        self.ecrire("d/s/b.json", b"{")
        self.ecrire("d/s/c.txt", b"")
        self.assertEqual(self.lancer(valider_fichier, self.chemin("d"), "-r", "--masque", "*.json", "--format", "json"), 2)
        self.assertEqual(self.lancer(valider_fichier, self.chemin("d"), "--masque", "*.json", "--format", "json"), 0)       # sans -r : a.json seul
        self.assertEqual(self.lancer(valider_fichier, self.chemin("absent.txt")), 2)
        self.assertIn("FILE_NOT_FOUND", [b["error"]["type"] for b in self.erreurs_journal()])

    def test_deux_fichiers_un_invalide_l_autre_est_valide(self):
        bon, vide = self.ecrire("b.txt", b"x"), self.ecrire("v.txt", b"")
        self.assertEqual(self.lancer(valider_fichier, vide, bon), 2)
        self.assertEqual(len(self.lignes("fichier_valide")), 1)


class TestEmpreinte(CasOutil):
    def test_generer_puis_verifier_avec_le_fichier_voisin(self):
        a = self.ecrire("d/a.txt", b"contenu")
        self.assertEqual(self.lancer(empreinte, a, "--generer"), 0, self.erreur)
        self.assertEqual(self.lire(a + ".sha256"), ("%s *a.txt\n" % sha(b"contenu")).encode())             # format sha256sum
        lignes = self.controler_journal("empreinte", "SUCCES")
        self.assertEqual([l for l in lignes if l["context"]["event"] == "empreinte_ecrite"][0]["context"]["sha256"], sha(b"contenu"))
        self.assertEqual(self.lancer(empreinte, a, "--verifier"), 0, self.erreur)
        self.assertIn("verifiees=1", self.sortie)

    def test_verification_d_un_fichier_altere(self):
        a = self.ecrire("a.txt", b"contenu")
        self.lancer(empreinte, a, "--generer")
        self.ecrire("a.txt", b"altere!")
        self.assertEqual(self.lancer(empreinte, a, "--verifier"), 2)
        erreur = self.erreurs_journal()[-2]
        self.assertEqual(erreur["error"]["type"], "FILE_IO_ERROR")
        self.assertIn("empreinte differente", erreur["message"])

    def test_verifier_sans_fichier_d_empreinte(self):
        a = self.ecrire("a.txt")
        self.assertEqual(self.lancer(empreinte, a, "--verifier"), 2)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "FILE_NOT_FOUND")

    def test_ecraser_et_simulation(self):
        a = self.ecrire("a.txt", b"v1")
        self.assertEqual(self.lancer(empreinte, a, "--generer", "--simulation"), 0)
        self.assertFalse(os.path.exists(a + ".sha256"))
        self.controler_journal("empreinte", simulation=True)
        self.assertEqual(self.lancer(empreinte, a, "--generer"), 0)
        self.ecrire("a.txt", b"v2")
        self.assertEqual(self.lancer(empreinte, a, "--generer"), 2)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "DUPLICATE_ENTITY")
        self.assertEqual(self.lancer(empreinte, a, "--generer", "--ecraser"), 0)
        self.assertEqual(self.lancer(empreinte, a, "--verifier"), 0)

    def test_manifeste_unique(self):
        self.ecrire("d/a.txt", b"A")
        self.ecrire("d/s/b.txt", b"B")
        manifeste = self.chemin("d", "SHA256SUMS")
        self.assertEqual(self.lancer(empreinte, self.chemin("d"), "-r", "--masque", "*.txt", "--generer", "--manifeste", manifeste), 0, self.erreur)
        with open(manifeste, encoding="utf-8") as f:
            self.assertEqual(f.read().splitlines(), ["%s *a.txt" % sha(b"A"), "%s *s/b.txt" % sha(b"B")])
        self.assertEqual(self.lancer(empreinte, self.chemin("d"), "-r", "--masque", "*.txt", "--verifier", "--manifeste", manifeste), 0, self.erreur)
        self.ecrire("d/s/b.txt", b"corrompu")
        self.assertEqual(self.lancer(empreinte, self.chemin("d"), "-r", "--masque", "*.txt", "--verifier", "--manifeste", manifeste), 2)
        self.ecrire("d/nouveau.txt", b"N")
        self.lancer(empreinte, self.chemin("d"), "-r", "--masque", "*.txt", "--verifier", "--manifeste", manifeste)
        self.assertIn("FILE_NOT_FOUND", [b["error"]["type"] for b in self.erreurs_journal()])                 # fichier hors manifeste
        self.assertEqual(self.lancer(empreinte, self.chemin("d"), "--verifier", "--manifeste", self.chemin("absent")), 2)

    def test_hash_attendu_et_autres_algorithmes(self):
        a = self.ecrire("a.txt", b"abc")
        self.assertEqual(self.lancer(empreinte, a, "--verifier", "--attendu", sha(b"abc").upper()), 0)
        self.assertEqual(self.lancer(empreinte, a, "--verifier", "--attendu", sha(b"autre")), 2)
        self.assertEqual(self.lancer(empreinte, a, "--generer", "--algo", "md5"), 0)
        self.assertEqual(self.lire(a + ".md5"), ("%s *a.txt\n" % sha(b"abc", "md5")).encode())
        self.assertEqual(self.lancer(empreinte, a, "--verifier", "--algo", "md5"), 0)
        self.assertEqual(self.lancer(empreinte, a, "--generer", "--algo", "sha512"), 0)
        self.assertTrue(os.path.exists(a + ".sha512"))

    def test_afficher_n_ecrit_rien(self):
        a = self.ecrire("a.txt", b"abc")
        self.assertEqual(self.lancer(empreinte, a, "--afficher"), 0)
        self.assertIn(sha(b"abc"), self.sortie)
        self.assertFalse(os.path.exists(a + ".sha256"))

    def test_parametres(self):
        a, b = self.ecrire("a.txt"), self.ecrire("b.txt")
        self.assertEqual(self.lancer(empreinte, a), 3)                                                 # un mode est obligatoire
        self.assertEqual(self.lancer(empreinte, a, "--generer", "--verifier"), 3)
        self.assertEqual(self.lancer(empreinte, a, "--generer", "--attendu", "ab"), 3)
        self.assertEqual(self.lancer(empreinte, a, b, "--verifier", "--attendu", "ab"), 3)
        self.assertEqual(self.lancer(empreinte, a, "--generer", "--algo", "crc32"), 3)

    def test_fichier_absent_les_autres_sont_traites(self):
        a = self.ecrire("a.txt")
        self.assertEqual(self.lancer(empreinte, self.chemin("absent.txt"), a, "--generer"), 2)
        self.assertTrue(os.path.exists(a + ".sha256"))


class TestEspaceDisque(CasOutil):
    def usage(self, libre, total=1000 * 1024 * 1024):
        return mock.patch("outils.controle.espace_disque.shutil.disk_usage",
                          return_value=collections.namedtuple("usage", "total used free")(total, total - libre, libre))

    def test_espace_suffisant_reel(self):
        self.assertEqual(self.lancer(espace_disque, self.racine, "--libre-min", "1K"), 0, self.erreur)
        self.assertIn("libres sur", self.sortie)
        lignes = self.controler_journal("espace_disque", "SUCCES")
        evenement = [l for l in lignes if l["context"]["event"] == "espace_suffisant"][0]["context"]
        self.assertGreater(evenement["libre"], 1024)
        self.assertEqual(evenement["exige"], 1024)

    def test_espace_insuffisant_est_une_erreur_resource_exhausted(self):
        with self.usage(libre=5 * 1024 * 1024):
            self.assertEqual(self.lancer(espace_disque, self.racine, "--libre-min", "10M"), 2)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "RESOURCE_EXHAUSTED")
        self.assertIn("Espace insuffisant", self.erreurs_journal()[0]["message"])

    def test_code_si_insuffisant_1_avertissement(self):
        with self.usage(libre=5 * 1024 * 1024):
            self.assertEqual(self.lancer(espace_disque, self.racine, "--libre-min", "10M", "--code-si-insuffisant", "1"), 1)
        self.assertEqual(self.erreurs_journal(), [])
        self.assertEqual(len(self.lignes("espace_insuffisant", "WARNING")), 1)

    def test_pourcentage_du_volume(self):
        with self.usage(libre=50 * 1024 * 1024, total=1000 * 1024 * 1024):                  # 5 % libres
            self.assertEqual(self.lancer(espace_disque, self.racine, "--libre-min-pct", "10"), 2)
            self.assertEqual(self.lancer(espace_disque, self.racine, "--libre-min-pct", "4"), 0)

    def test_place_necessaire_pour_des_fichiers_avec_marge(self):
        a = self.ecrire("src/a.bin", b"x" * 3000)
        self.ecrire("src/s/b.bin", b"x" * 2000)
        with self.usage(libre=6000):
            self.assertEqual(self.lancer(espace_disque, self.racine, "--pour", self.chemin("src")), 0, self.erreur)
            self.assertEqual(self.lancer(espace_disque, self.racine, "--pour", self.chemin("src"), "--marge", "1000"), 0)
            self.assertEqual(self.lancer(espace_disque, self.racine, "--pour", self.chemin("src"), "--marge", "1001"), 2)
            self.assertEqual(self.lancer(espace_disque, self.racine, "--pour", a, "--pour", self.chemin("src", "s", "b.bin"), "--libre-min", "1000"), 0)

    def test_dossier_a_creer_controle_son_volume(self):
        self.assertEqual(self.lancer(espace_disque, self.chemin("a", "creer", "plus-tard"), "--libre-min", "1K"), 0, self.erreur)

    def test_plusieurs_dossiers_et_variable_du_moteur(self):
        self.assertEqual(self.lancer(espace_disque, "--libre-min", "1K", env={"COPIE_CIBLE": self.racine}), 0, self.erreur)
        self.assertEqual(len(self.lignes("espace_suffisant")), 1)
        with self.usage(libre=10):
            self.assertEqual(self.lancer(espace_disque, self.racine, self.chemin("autre"), "--libre-min", "1K"), 2)
        self.assertEqual(len([b for b in self.erreurs_journal() if b["context"]["event"] != "outil_termine"]), 2)

    def test_parametres(self):
        self.assertEqual(self.lancer(espace_disque, self.racine), 3)
        self.assertEqual(self.lancer(espace_disque, self.racine, "--libre-min", "enorme"), 3)
        self.assertEqual(self.lancer(espace_disque, self.racine, "--pour", self.chemin("absent"), "--libre-min", "1K"), 3)
        self.assertEqual(self.lancer(espace_disque, "--libre-min", "1K"), 0)                    # aucun dossier : rien a faire
        self.assertEqual(self.lancer(espace_disque, "--libre-min", "1K", "--code-si-rien", "1"), 1)


if __name__ == "__main__":
    unittest.main()
