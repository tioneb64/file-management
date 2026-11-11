"""J4 : chemins, noms, espace disque, selection, primitives de transfert."""
import datetime
import os
import sys
import unittest
from unittest import mock

from file_management import chemins, selection, transfert
from file_management.parametrage import Selection
from tests.outils import CasTemporaire

MAINTENANT = datetime.datetime(2026, 11, 3, 6, 30, 12)


class TestNoms(unittest.TestCase):
    def test_modele_de_nom(self):
        self.assertEqual(chemins.appliquer_modele_nom("{nom}_{AAAA}{MM}{JJ}_{hh}{mm}{ss}{ext}",
                                                      "C1.xml", MAINTENANT), "C1_20261103_063012.xml")
        self.assertEqual(chemins.appliquer_modele_nom("{nom}.bak", "rapport.final.csv", MAINTENANT),
                         "rapport.final.bak")
        self.assertEqual(chemins.appliquer_modele_nom("{nom}{ext}", ".gitignore", MAINTENANT),
                         ".gitignore")
        self.assertEqual(chemins.appliquer_modele_nom("fixe.txt", "x.csv", MAINTENANT), "fixe.txt")

    def test_suffixe_d_horodatage(self):
        self.assertEqual(chemins.nom_avec_suffixe("a.csv", MAINTENANT), "a_20261103_063012.csv")
        self.assertEqual(chemins.nom_avec_suffixe("a.csv", MAINTENANT, 1), "a_20261103_063012_2.csv")
        self.assertEqual(chemins.nom_avec_suffixe("sans_ext", MAINTENANT), "sans_ext_20261103_063012")

    def test_noms_windows_invalides(self):
        for mauvais in ("", " ", "a<b", 'a"b', "a:b", "a|b", "a?b", "a*b", "a/b", "a\\b", "x\x01",
                        "fin.", "fin ", "CON", "con.txt", "NUL", "COM1.csv", "LPT9", "x" * 256):
            self.assertIsNotNone(chemins.nom_invalide(mauvais), repr(mauvais))
        for bon in ("a.csv", "é à ü.txt", "a b (1).xml", "CONSOLE.txt", "COM10.txt", ".gitignore", "x" * 255):
            self.assertIsNone(chemins.nom_invalide(bon), repr(bon))


class TestArchive(CasTemporaire):
    def test_resolution(self):
        self.assertEqual(chemins.resoudre_archive("D:\\archive\\{AAAA}-{MM}-{JJ}", "C:\\src", MAINTENANT),
                         os.path.normpath("D:\\archive\\2026-11-03"))
        self.assertEqual(chemins.resoudre_archive(".\\archive", "C:\\src", MAINTENANT),
                         os.path.normpath("C:\\src\\archive"))
        self.assertEqual(chemins.resoudre_archive(".\\{AAAA}\\{MM}", "C:\\src", MAINTENANT),
                         os.path.normpath("C:\\src\\2026\\11"))
        self.assertEqual(chemins.resoudre_archive("archive_{JJ}", "C:\\src", MAINTENANT),
                         os.path.normpath("C:\\src\\archive_03"))

    def test_exclusion_de_l_archive_toutes_dates(self):
        exclu = chemins.exclusion_dossiers(self.chemin("src"), ".\\archive\\{AAAA}-{MM}-{JJ}")
        self.assertTrue(exclu(("archive", "2025-01-02")))
        self.assertTrue(exclu(("archive", "2026-11-03", "sous")))
        self.assertTrue(exclu(("ARCHIVE", "2026-11-03")))
        self.assertFalse(exclu(("archive",)))                    # le dossier racine seul : pas de date
        self.assertFalse(exclu(("autre", "2026-11-03")))

    def test_exclusion_archive_absolue_dans_la_source(self):
        exclu = chemins.exclusion_dossiers(self.chemin("src"), self.chemin("src", "old", "{AAAA}"))
        self.assertTrue(exclu(("old", "2026")))
        self.assertFalse(exclu(("new", "2026")))

    def test_aucune_exclusion_pour_une_archive_hors_de_la_source(self):
        exclu = chemins.exclusion_dossiers(self.chemin("src"), self.chemin("ailleurs"))
        self.assertFalse(exclu(("ailleurs",)))

    def test_exclusion_du_dossier_temporaire_dans_la_source(self):
        exclu = chemins.exclusion_dossiers(self.chemin("src"), None, [self.chemin("src", "tmp")])
        self.assertTrue(exclu(("tmp",)))
        self.assertTrue(exclu(("tmp", "x")))

    def test_volumes(self):
        os.makedirs(self.chemin("a"))
        self.assertTrue(chemins.meme_volume(self.chemin("a"), self.chemin("b", "n'existe", "pas")))
        self.assertFalse(chemins.meme_volume(self.chemin("a"), self.chemin("a")) is False)

    def test_espace_disponible(self):
        libre = chemins.espace_disponible(self.chemin("pas", "encore", "cree"))
        self.assertGreater(libre, 1_000_000)
        self.assertIsInstance(libre, int)


class CasSelection(CasTemporaire):
    def lister(self, source=None, maintenant=MAINTENANT, **options):
        s = Selection()
        for cle, valeur in options.items():
            setattr(s, cle, valeur)
        return selection.lister(source or self.chemin("src"), s, maintenant)

    def noms(self, res):
        return [c.relatif for c in res.candidats]


class TestSelection(CasSelection):
    def setUp(self):
        super().setUp()
        self.maintenant = datetime.datetime.now()

    def fichier(self, nom, age_sec=3600, contenu=b"x"):
        chemin = self.ecrire(os.path.join("src", nom), contenu)
        instant = self.maintenant.timestamp() - age_sec
        os.utime(chemin, (instant, instant))
        return chemin

    def test_masque_et_exclusion_sans_tenir_compte_de_la_casse(self):
        for nom in ("A.CSV", "b.csv", "c.xml", "~temp.csv", "d.txt"):
            self.fichier(nom)
        res = self.lister(maintenant=self.maintenant, masque="*.csv;*.XML", exclure="~*")
        self.assertEqual(self.noms(res), ["A.CSV", "b.csv", "c.xml"])
        self.assertEqual(res.hors_masque, 2)

    def test_non_recursif_ignore_les_sous_dossiers(self):
        self.fichier("a.txt")
        self.fichier(os.path.join("sous", "b.txt"))
        self.assertEqual(self.noms(self.lister(maintenant=self.maintenant)), ["a.txt"])

    def test_recursif_conserve_l_arborescence(self):
        self.fichier("a.txt")
        self.fichier(os.path.join("n1", "n2", "b.txt"))
        res = self.lister(maintenant=self.maintenant, recursif=True)
        self.assertEqual(self.noms(res), ["a.txt", os.path.join("n1", "n2", "b.txt")])

    def test_fichiers_temporaires_du_moteur_ignores(self):
        self.fichier("a.csv")
        self.fichier("a.csv.copie_en_cours")
        self.assertEqual(self.noms(self.lister(maintenant=self.maintenant)), ["a.csv"])

    def test_dossier_exclu_non_traverse(self):
        self.fichier("a.txt")
        self.fichier(os.path.join("archive", "2026-11-03", "vieux.txt"))
        exclu = chemins.exclusion_dossiers(self.chemin("src"), ".\\archive\\{AAAA}-{MM}-{JJ}")
        s = Selection()
        s.recursif = True
        res = selection.lister(self.chemin("src"), s, self.maintenant, exclu)
        self.assertEqual(self.noms(res), ["a.txt"])

    def test_modifie_depuis(self):
        minuit = datetime.datetime.combine(self.maintenant.date(), datetime.time.min).timestamp()
        for nom, quand in (("aujourdhui.txt", minuit + 60), ("hier.txt", minuit - 3600),
                           ("il_y_a_3_jours.txt", minuit - 3 * 86400 + 60),
                           ("ancien.txt", minuit - 10 * 86400)):
            chemin = self.ecrire(os.path.join("src", nom), b"x")
            os.utime(chemin, (quand, quand))
        # le test tourne apres minuit local : "aujourdhui.txt" est dans le futur de la journee ?
        maintenant = datetime.datetime.fromtimestamp(minuit + 7200)
        self.assertEqual(self.noms(self.lister(maintenant=maintenant, modifie_depuis="J")), ["aujourdhui.txt"])
        self.assertEqual(self.noms(self.lister(maintenant=maintenant, modifie_depuis="J-1")),
                         ["aujourdhui.txt", "hier.txt"])
        self.assertEqual(self.noms(self.lister(maintenant=maintenant, modifie_depuis="J-3")),
                         ["aujourdhui.txt", "hier.txt", "il_y_a_3_jours.txt"])
        self.assertEqual(len(self.lister(maintenant=maintenant, modifie_depuis="TOUT").candidats), 4)

    def test_age_minimum_et_maximum(self):
        self.fichier("tout_neuf.txt", age_sec=5)
        self.fichier("recent.txt", age_sec=120)
        self.fichier("vieux.txt", age_sec=7200)
        res = self.lister(maintenant=self.maintenant, age_minimum_sec=60)
        self.assertEqual(self.noms(res), ["recent.txt", "vieux.txt"])
        self.assertEqual(res.trop_recents, 1)
        res = self.lister(maintenant=self.maintenant, age_minimum_sec=60, age_maximum_sec=3600)
        self.assertEqual(self.noms(res), ["recent.txt"])
        self.assertEqual(res.trop_anciens, 1)

    def test_taille_minimum(self):
        self.fichier("vide.txt", contenu=b"")
        self.fichier("plein.txt", contenu=b"x")
        res = self.lister(maintenant=self.maintenant, taille_minimum_octets=1)
        self.assertEqual(self.noms(res), ["plein.txt"])
        self.assertEqual(res.trop_petits, 1)

    def test_date_dans_le_futur_ignoree_et_signalee(self):
        self.fichier("futur.txt", age_sec=-3600)
        self.fichier("presque.txt", age_sec=-30)               # sous la tolerance d'une minute
        res = self.lister(maintenant=self.maintenant)
        self.assertEqual(self.noms(res), ["presque.txt"])
        self.assertEqual([os.path.basename(c) for c in res.dates_futures], ["futur.txt"])

    def test_ordre(self):
        self.fichier("b.txt", age_sec=100)
        self.fichier("a.txt", age_sec=300)
        self.fichier("C.txt", age_sec=200)
        self.assertEqual(self.noms(self.lister(maintenant=self.maintenant, ordre="nom")),
                         ["a.txt", "b.txt", "C.txt"])
        self.assertEqual(self.noms(self.lister(maintenant=self.maintenant, ordre="date_modification")),
                         ["a.txt", "C.txt", "b.txt"])

    def test_dossier_illisible_signale_sans_lever(self):
        self.fichier("a.txt")
        with mock.patch.object(selection.os, "scandir", side_effect=PermissionError("refuse")):
            res = self.lister(maintenant=self.maintenant)
        self.assertEqual(res.candidats, [])
        self.assertEqual(len(res.erreurs), 1)

    def test_lien_symbolique_ignore(self):
        self.fichier("a.txt")
        try:
            os.symlink(self.chemin("src", "a.txt"), self.chemin("src", "lien.txt"))
        except (OSError, NotImplementedError):
            self.skipTest("liens symboliques non autorises")
        self.assertEqual(self.noms(self.lister(maintenant=self.maintenant)), ["a.txt"])

    def test_noms_avec_accents_espaces_et_esperluette(self):
        nom = "Facture é à & co (copie) n°1.xml"
        self.fichier(nom)
        self.assertEqual(self.noms(self.lister(maintenant=self.maintenant)), [nom])


class TestCopieVerifiee(CasTemporaire):
    def test_copie_conserve_contenu_et_date(self):
        src = self.ecrire("src/a.csv", b"abc" * 5000, age_jours=5)
        dst = self.chemin("dst", "sous", "a.csv")
        copie = transfert.copier_verifier(src, dst, dst + ".copie_en_cours")
        self.assertEqual(self.lire(dst), b"abc" * 5000)
        self.assertEqual(os.stat(dst).st_mtime_ns, os.stat(src).st_mtime_ns)
        self.assertEqual(copie.taille, 15000)
        self.assertEqual(copie.sha256, transfert.sha256_fichier(src))
        self.assertEqual(os.listdir(self.chemin("dst", "sous")), ["a.csv"])

    def test_fichier_vide_et_gros_fichier_multi_blocs(self):
        vide = self.ecrire("src/vide", b"")
        transfert.copier_verifier(vide, self.chemin("dst", "vide"), self.chemin("dst", "vide.tmp"))
        self.assertEqual(os.path.getsize(self.chemin("dst", "vide")), 0)
        gros = self.ecrire("src/gros", os.urandom(100_000))
        with mock.patch.object(transfert, "TAILLE_BLOC", 4096):
            transfert.copier_verifier(gros, self.chemin("dst", "gros"), self.chemin("dst", "gros.tmp"))
        self.assertEqual(self.lire(self.chemin("dst", "gros")), self.lire(gros))

    def test_source_disparue(self):
        with self.assertRaises(transfert.SourceDisparue):
            transfert.copier_verifier(self.chemin("rien"), self.chemin("dst", "x"), self.chemin("dst", "x.tmp"))

    def test_changement_depuis_le_listage(self):
        src = self.ecrire("src/a.txt", b"12345")
        stat = os.stat(src)
        self.ecrire("src/a.txt", b"123456")
        with self.assertRaises(transfert.FichierInstable):
            transfert.copier_verifier(src, self.chemin("dst", "a"), self.chemin("dst", "a.tmp"),
                                      attendu=(stat.st_size, stat.st_mtime_ns))
        self.assertFalse(os.path.exists(self.chemin("dst", "a")))

    def test_source_modifiee_pendant_la_lecture(self):
        src = self.ecrire("src/a.txt", b"x" * 100)
        vrai_stat, appels = os.stat, {"n": 0}

        def stat_truque(chemin, *a, **k):
            r = vrai_stat(chemin, *a, **k)
            if os.path.abspath(chemin) == os.path.abspath(src):
                appels["n"] += 1
                if appels["n"] >= 2:
                    return os.stat_result((r.st_mode, r.st_ino, r.st_dev, r.st_nlink, r.st_uid,
                                           r.st_gid, r.st_size + 1, r.st_atime, r.st_mtime, r.st_ctime))
            return r
        with mock.patch.object(transfert.os, "stat", stat_truque):
            with self.assertRaises(transfert.FichierInstable):
                transfert.copier_verifier(src, self.chemin("dst", "a"), self.chemin("dst", "a.tmp"))
        self.assertEqual(os.listdir(self.chemin("dst")), [])

    def test_verification_sha256_en_echec(self):
        src = self.ecrire("src/a.txt", b"abc")
        dst = self.ecrire("dst/a.txt", b"ancien")
        with mock.patch.object(transfert, "sha256_fichier", return_value="faux"):
            with self.assertRaises(transfert.ErreurVerification):
                transfert.copier_verifier(src, dst, dst + ".tmp", ecraser=True)
        self.assertEqual(self.lire(dst), b"ancien")             # destination existante intacte
        self.assertEqual(sorted(os.listdir(self.chemin("dst"))), ["a.txt"])

    def test_taille_incorrecte(self):
        src = self.ecrire("src/a.txt", b"abc")
        with mock.patch.object(transfert.os.path, "getsize", return_value=1):
            with self.assertRaises(transfert.ErreurVerification):
                transfert.copier_verifier(src, self.chemin("dst", "a"), self.chemin("dst", "a.tmp"))
        self.assertFalse(os.path.exists(self.chemin("dst", "a.tmp")))

    def test_destination_impossible(self):
        src = self.ecrire("src/a.txt", b"abc")
        self.ecrire("bloc", b"un fichier a la place du dossier")
        with self.assertRaises(transfert.ErreurCible):
            transfert.copier_verifier(src, self.chemin("bloc", "a"), self.chemin("bloc", "a.tmp"))

    def test_disque_plein_pendant_l_ecriture(self):
        src = self.ecrire("src/a.txt", b"abc" * 100)

        class Plein(object):
            def __init__(self, f):
                self.f = f

            def __getattr__(self, nom):
                return getattr(self.f, nom)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.f.close()

            def write(self, _):
                raise OSError(28, "No space left on device")
        vrai_open = open

        def faux_open(chemin, mode="r", *a, **k):
            f = vrai_open(chemin, mode, *a, **k)
            return Plein(f) if mode == "wb" else f
        with mock.patch("builtins.open", faux_open):
            with self.assertRaises(transfert.ErreurCible):
                transfert.copier_verifier(src, self.chemin("dst", "a"), self.chemin("dst", "a.tmp"))
        self.assertEqual(os.listdir(self.chemin("dst")), [])

    def test_cible_existante_sans_ecraser(self):
        src = self.ecrire("src/a.txt", b"nouveau")
        dst = self.ecrire("dst/a.txt", b"ancien")
        with self.assertRaises(transfert.CibleExiste):
            transfert.copier_verifier(src, dst, dst + ".tmp")
        self.assertEqual(self.lire(dst), b"ancien")
        self.assertFalse(os.path.exists(dst + ".tmp"))

    def test_ecrasement_d_une_cible_en_lecture_seule(self):
        src = self.ecrire("src/a.txt", b"nouveau")
        dst = self.ecrire("dst/a.txt", b"ancien")
        os.chmod(dst, 0o444)
        transfert.copier_verifier(src, dst, dst + ".tmp", ecraser=True)
        self.assertEqual(self.lire(dst), b"nouveau")

    def test_la_copie_n_herite_pas_de_la_lecture_seule(self):
        src = self.ecrire("src/a.txt", b"x")
        os.chmod(src, 0o444)
        dst = self.chemin("dst", "a.txt")
        transfert.copier_verifier(src, dst, dst + ".tmp")
        os.remove(dst)                                      # leve si la copie est en lecture seule

    def test_reliquat_temporaire_remplace(self):
        src = self.ecrire("src/a.txt", b"x")
        dst = self.chemin("dst", "a.txt")
        self.ecrire("dst/a.txt.tmp", b"reste d'une coupure")
        transfert.copier_verifier(src, dst, dst + ".tmp")
        self.assertEqual(os.listdir(self.chemin("dst")), ["a.txt"])

    @unittest.skipUnless(sys.platform == "win32", "verrous de region Windows")
    def test_fichier_verrouille_signale_comme_tel(self):
        import msvcrt
        src = self.ecrire("src/a.txt", b"x" * 100)
        with open(src, "r+b") as f:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 50)
            try:
                with self.assertRaises(transfert.ErreurSource) as cm:
                    transfert.copier_verifier(src, self.chemin("dst", "a"), self.chemin("dst", "a.tmp"))
                self.assertTrue(cm.exception.verrou)
            finally:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 50)
        self.assertEqual(os.listdir(self.chemin("dst")), [])

    def test_suppression_controlee(self):
        src = self.ecrire("src/a.txt", b"abc")
        st = os.stat(src)
        os.chmod(src, 0o444)
        self.assertEqual(transfert.supprimer_original(src, st.st_size, st.st_mtime_ns), "supprime")
        self.assertFalse(os.path.exists(src))
        self.assertEqual(transfert.supprimer_original(src, st.st_size, st.st_mtime_ns), "absent")

    def test_suppression_refusee_si_l_original_a_change(self):
        src = self.ecrire("src/a.txt", b"abc")
        st = os.stat(src)
        self.ecrire("src/a.txt", b"abcd")
        with self.assertRaises(transfert.SourceModifiee):
            transfert.supprimer_original(src, st.st_size, st.st_mtime_ns)
        self.assertTrue(os.path.exists(src))
        instant = st.st_mtime + 100                         # meme taille, autre date
        self.ecrire("src/b.txt", b"abc")
        st_b = os.stat(self.chemin("src", "b.txt"))
        os.utime(self.chemin("src", "b.txt"), (instant, instant))
        with self.assertRaises(transfert.SourceModifiee):
            transfert.supprimer_original(self.chemin("src", "b.txt"), st_b.st_size, st_b.st_mtime_ns)

    def test_renommer_sans_ecraser(self):
        a = self.ecrire("a.txt", b"1")
        b = self.ecrire("b.txt", b"2")
        with self.assertRaises(transfert.CibleExiste):
            transfert.renommer(a, b, ecraser=False)
        self.assertEqual(self.lire(b), b"2")
        transfert.renommer(a, b, ecraser=True)
        self.assertEqual(self.lire(b), b"1")


if __name__ == "__main__":
    unittest.main()
