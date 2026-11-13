"""Boite a outils : dates et attributs (touch, attributs, permissions)."""
import os
import stat
import time
import unittest
from datetime import datetime
from unittest import mock

from outils.dates_attributs import attributs, permissions, touch
from tests.boite_outils import CasOutil

WINDOWS = os.name == "nt"
SECONDE = 10 ** 9


def ns(texte):
    return int(datetime.strptime(texte, "%Y-%m-%d %H:%M:%S").timestamp()) * SECONDE


class TestTouch(CasOutil):
    def test_modification_et_acces(self):
        a = self.ecrire("a.txt")
        code = self.lancer(touch, a, "--modification", "2020-05-06 07:08:09", "--acces", "2021-01-02")
        self.assertEqual(code, 0, self.erreur)
        info = os.stat(a)
        self.assertEqual(info.st_mtime_ns // SECONDE * SECONDE, ns("2020-05-06 07:08:09"))
        self.assertEqual(info.st_atime_ns // SECONDE * SECONDE, ns("2021-01-02 00:00:00"))
        lignes = self.controler_journal("touch", "SUCCES")
        evenement = [l for l in lignes if l["context"]["event"] == "dates_modifiees"][0]["context"]
        self.assertEqual(evenement["modification"], "2020-05-06 07:08:09")

    def test_sans_option_modification_et_acces_maintenant(self):
        a = self.ecrire("a.txt", age_jours=100)
        self.assertEqual(self.lancer(touch, a), 0)
        self.assertLess(abs(time.time() - os.path.getmtime(a)), 30)

    def test_tout_et_formes_de_date(self):
        a = self.ecrire("a.txt")
        for texte, attendu in (("2019-03-04", "2019-03-04 00:00:00"), ("2019-03-04 10:11", "2019-03-04 10:11:00"),
                               ("2019-03-04T10:11:12", "2019-03-04 10:11:12")):
            self.assertEqual(self.lancer(touch, a, "--tout", texte), 0, texte)
            self.assertEqual(os.stat(a).st_mtime_ns // SECONDE * SECONDE, ns(attendu))
        self.assertEqual(self.lancer(touch, a, "--tout", "maintenant"), 0)
        self.assertLess(abs(time.time() - os.path.getmtime(a)), 30)

    def test_copier_de_un_modele(self):
        modele = self.ecrire("modele.txt", age_jours=50)
        a = self.ecrire("a.txt")
        self.assertEqual(self.lancer(touch, a, "--copier-de", modele), 0, self.erreur)
        self.assertEqual(os.stat(a).st_mtime_ns // SECONDE, os.stat(modele).st_mtime_ns // SECONDE)
        self.assertEqual(self.lancer(touch, a, "--copier-de", self.chemin("absent.txt")), 3)

    def test_decalage(self):
        a = self.ecrire("a.txt")
        self.lancer(touch, a, "--tout", "2020-01-01 12:00:00")
        self.assertEqual(self.lancer(touch, a, "--decaler", "+2h"), 0, self.erreur)
        self.assertEqual(os.stat(a).st_mtime_ns // SECONDE * SECONDE, ns("2020-01-01 12:00:00") + 2 * 3600 * SECONDE)
        self.assertEqual(self.lancer(touch, a, "--decaler=-1j"), 0, self.erreur)
        self.assertEqual(os.stat(a).st_mtime_ns // SECONDE * SECONDE, ns("2020-01-01 12:00:00") + 2 * 3600 * SECONDE - 86400 * SECONDE)
        self.assertEqual(self.lancer(touch, a, "--decaler", "+30m"), 0)
        self.assertEqual(os.stat(a).st_mtime_ns // SECONDE * SECONDE,
                         ns("2020-01-01 12:00:00") + (2 * 3600 - 86400 + 1800) * SECONDE)
        self.assertEqual(self.lancer(touch, a, "--decaler", "bientot"), 3)

    def test_creer_un_fichier_absent(self):
        absent = self.chemin("nouveau", "n.txt")
        self.assertEqual(self.lancer(touch, absent), 2)                               # sans --creer : introuvable
        self.assertIn("FILE_NOT_FOUND", [b["error"]["type"] for b in self.erreurs_journal()])
        self.assertEqual(self.lancer(touch, absent, "--creer", "--modification", "2020-01-01"), 0, self.erreur)
        self.assertEqual(os.path.getsize(absent), 0)
        self.assertEqual(os.stat(absent).st_mtime_ns // SECONDE * SECONDE, ns("2020-01-01 00:00:00"))

    def test_simulation_ne_cree_ni_ne_modifie(self):
        a = self.ecrire("a.txt", age_jours=10)
        avant = os.stat(a).st_mtime_ns
        absent = self.chemin("n.txt")
        self.assertEqual(self.lancer(touch, a, absent, "--creer", "--tout", "2000-01-01", "--simulation"), 2)  # l'absent n'est pas cree
        self.assertEqual(os.stat(a).st_mtime_ns, avant)
        self.assertFalse(os.path.exists(absent))
        self.assertEqual(self.lancer(touch, a, "--tout", "2000-01-01", "--simulation"), 0)
        self.assertEqual(os.stat(a).st_mtime_ns, avant)
        self.assertEqual(len(self.lignes("dates_a_modifier")), 2)

    def test_dossier_recursif_avec_masque(self):
        self.ecrire("d/a.txt")
        self.ecrire("d/s/b.txt")
        self.ecrire("d/s/c.log")
        self.assertEqual(self.lancer(touch, self.chemin("d"), "-r", "--masque", "*.txt", "--tout", "2001-01-01"), 0)
        self.assertEqual(os.stat(self.chemin("d", "s", "b.txt")).st_mtime_ns // SECONDE * SECONDE, ns("2001-01-01 00:00:00"))
        self.assertGreater(os.path.getmtime(self.chemin("d", "s", "c.log")), time.time() - 3600)

    def test_parametres_invalides(self):
        a = self.ecrire("a.txt")
        self.assertEqual(self.lancer(touch, a, "--modification", "hier"), 3)
        self.assertEqual(self.lancer(touch, a, "--tout", "2020-13-45"), 3)

    @unittest.skipUnless(WINDOWS, "date de creation : Windows")
    def test_date_de_creation_sous_windows(self):
        a = self.ecrire("a.txt")
        self.assertEqual(self.lancer(touch, a, "--creation", "2015-06-07 08:09:10"), 0, self.erreur)
        self.assertEqual(os.stat(a).st_ctime_ns // SECONDE * SECONDE, ns("2015-06-07 08:09:10"))
        modele = self.ecrire("m.txt")
        self.lancer(touch, modele, "--tout", "2012-02-03 04:05:06")
        self.assertEqual(self.lancer(touch, a, "--copier-de", modele), 0)
        self.assertEqual(os.stat(a).st_ctime_ns // SECONDE * SECONDE, ns("2012-02-03 04:05:06"))

    @unittest.skipIf(WINDOWS, "hors Windows seulement")
    def test_date_de_creation_refusee_hors_windows(self):
        a = self.ecrire("a.txt")
        self.assertEqual(self.lancer(touch, a, "--creation", "2015-06-07"), 2)


class TestAttributs(CasOutil):
    def proteger(self, chemin):
        """Le dossier temporaire doit pouvoir etre supprime a la fin du test."""
        self.addCleanup(lambda: os.path.exists(chemin) and os.chmod(chemin, stat.S_IWRITE | stat.S_IREAD))

    def test_lecture_seule_oui_non(self):
        a = self.ecrire("a.txt")
        self.proteger(a)
        self.assertEqual(self.lancer(attributs, a, "--lecture-seule", "oui"), 0, self.erreur)
        self.assertFalse(os.access(a, os.W_OK) and not WINDOWS)
        self.assertTrue(os.stat(a).st_mode & stat.S_IWRITE == 0)
        self.controler_journal("attributs", "SUCCES")
        self.assertEqual(self.lancer(attributs, a, "--lecture-seule", "non"), 0)
        self.assertTrue(os.stat(a).st_mode & stat.S_IWRITE)

    def test_deja_conforme_ne_fait_rien(self):
        a = self.ecrire("a.txt")
        self.assertEqual(self.lancer(attributs, a, "--lecture-seule", "non"), 0)
        self.assertIn("deja_conformes=1", self.sortie)
        self.assertEqual(self.lancer(attributs, a, "--lecture-seule", "non", "--code-si-rien", "1"), 1)

    def test_afficher_ne_modifie_rien(self):
        a = self.ecrire("a.txt")
        self.proteger(a)
        os.chmod(a, stat.S_IREAD)
        self.assertEqual(self.lancer(attributs, a, "--afficher"), 0, self.erreur)
        self.assertIn("lecture_seule", self.sortie)
        self.assertTrue(os.stat(a).st_mode & stat.S_IWRITE == 0)
        self.assertEqual(self.lignes("attributs_lus")[0]["lecture_seule"], True)

    def test_simulation(self):
        a = self.ecrire("a.txt")
        self.assertEqual(self.lancer(attributs, a, "--lecture-seule", "oui", "--simulation"), 0)
        self.assertTrue(os.stat(a).st_mode & stat.S_IWRITE)
        self.assertEqual(len(self.lignes("attributs_a_modifier")), 1)
        self.controler_journal("attributs", simulation=True)

    def test_parametres(self):
        a = self.ecrire("a.txt")
        self.assertEqual(self.lancer(attributs, a), 3)
        self.assertEqual(self.lancer(attributs, a, "--cache", "peut-etre"), 3)

    def test_erreur_sur_un_element_les_autres_sont_traites(self):
        a = self.ecrire("a.txt")
        self.proteger(a)
        self.assertEqual(self.lancer(attributs, self.chemin("absent.txt"), a, "--lecture-seule", "oui"), 2)
        self.assertTrue(os.stat(a).st_mode & stat.S_IWRITE == 0)

    @unittest.skipUnless(WINDOWS, "attributs cache / systeme / archive : Windows")
    def test_cache_systeme_archive_sous_windows(self):
        a = self.ecrire("a.txt")
        self.proteger(a)
        self.assertEqual(self.lancer(attributs, a, "--cache", "oui", "--systeme", "oui", "--archive", "non"), 0, self.erreur)
        valeur = os.stat(a).st_file_attributes
        self.assertTrue(valeur & stat.FILE_ATTRIBUTE_HIDDEN and valeur & stat.FILE_ATTRIBUTE_SYSTEM)
        self.assertFalse(valeur & stat.FILE_ATTRIBUTE_ARCHIVE)
        self.assertEqual(self.lancer(attributs, a, "--cache", "non", "--systeme", "non", "--lecture-seule", "oui"), 0)
        valeur = os.stat(a).st_file_attributes
        self.assertFalse(valeur & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM))
        self.assertTrue(valeur & stat.FILE_ATTRIBUTE_READONLY)
        self.assertEqual(self.lancer(attributs, a, "--afficher"), 0)
        self.assertIn("lecture_seule", self.sortie)

    @unittest.skipIf(WINDOWS, "hors Windows seulement")
    def test_attribut_cache_refuse_hors_windows(self):
        a = self.ecrire("a.txt")
        self.assertEqual(self.lancer(attributs, a, "--cache", "oui"), 2)


class TestPermissions(CasOutil):
    def test_parametres_invalides_sur_toutes_les_plateformes(self):
        a = self.ecrire("a.txt")
        self.assertEqual(self.lancer(permissions, a), 3)
        self.assertEqual(self.lancer(permissions, a, "--accorder", "sans_droits"), 3)
        self.assertEqual(self.lancer(permissions, a, "--accorder", "Utilisateur:"), 3)
        self.assertEqual(self.lancer(permissions, a, "--accorder", 'Eve" /grant Tous:F'), 3)
        self.assertEqual(self.lancer(permissions, a, "--retirer", "a|b"), 3)
        self.assertEqual(self.lancer(permissions, a, "--proprietaire", "x*"), 3)

    @unittest.skipIf(WINDOWS, "hors Windows seulement")
    def test_hors_windows_code_4(self):
        a = self.ecrire("a.txt")
        self.assertEqual(self.lancer(permissions, a, "--afficher"), 4)
        self.assertNotIn("Traceback", self.sortie + self.erreur)

    @unittest.skipUnless(WINDOWS, "icacls : Windows")
    def test_accorder_afficher_retirer_avec_un_sid(self):
        a = self.ecrire("a.txt")
        # S-1-5-32-545 : groupe local « Utilisateurs » ; le SID evite toute dependance a la langue du systeme
        self.assertEqual(self.lancer(permissions, a, "--accorder", "*S-1-5-32-545:R"), 0, self.sortie + self.erreur)
        lignes = self.controler_journal("permissions", "SUCCES")
        evenement = [l for l in lignes if l["context"]["event"] == "acl_modifiee"][0]["context"]
        self.assertIn("/grant *S-1-5-32-545:R", evenement["options"])
        self.assertEqual(self.lancer(permissions, a, "--afficher"), 0)
        self.assertIn("a.txt", self.sortie)
        self.assertEqual(self.lancer(permissions, a, "--retirer", "*S-1-5-32-545"), 0, self.sortie)
        self.assertEqual(self.lancer(permissions, a, "--heriter", "activer"), 0)

    @unittest.skipUnless(WINDOWS, "icacls : Windows")
    def test_simulation_et_dossier_recursif(self):
        self.ecrire("d/a.txt")
        self.assertEqual(self.lancer(permissions, self.chemin("d"), "--accorder", "*S-1-5-32-545:(OI)(CI)R", "--simulation"), 0)
        self.assertEqual(len(self.lignes("acl_a_modifier")), 1)
        self.controler_journal("permissions", simulation=True)
        self.assertEqual(self.lancer(permissions, self.chemin("d"), "-r", "--accorder", "*S-1-5-32-545:R"), 0, self.sortie)
        self.assertIn("/T", self.lignes("acl_modifiee")[0]["options"].split())

    @unittest.skipUnless(WINDOWS, "icacls : Windows")
    def test_echec_d_icacls_et_fichier_introuvable(self):
        a = self.ecrire("a.txt")
        with mock.patch("outils.commun.dependances.executer_externe", return_value=(5, "Acces refuse")):
            self.assertEqual(self.lancer(permissions, a, "--afficher"), 2)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "FILE_IO_ERROR")
        self.assertEqual(self.lancer(permissions, self.chemin("absent.txt"), "--afficher"), 2)
        self.assertIn("FILE_NOT_FOUND", [b["error"]["type"] for b in self.erreurs_journal()])

    @unittest.skipUnless(WINDOWS, "icacls : Windows")
    def test_icacls_n_est_jamais_lance_via_un_shell(self):
        a = self.ecrire("a.txt")
        with mock.patch("outils.commun.dependances.executer_externe", return_value=(0, "ok")) as faux:
            self.assertEqual(self.lancer(permissions, a, "--accorder", "*S-1-5-32-545:R"), 0)
        argv = faux.call_args[0][0]
        self.assertEqual(argv[0], "icacls")
        self.assertEqual(argv[2:], ["/grant", "*S-1-5-32-545:R"])


if __name__ == "__main__":
    unittest.main()
