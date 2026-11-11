"""Tests de caracterisation du script actuel (v1).

Ils figent le comportement observable de file_management.py avant la refonte : la v2 devra soit
le reproduire, soit s'en ecarter volontairement (et ces tests seront alors modifies avec une
explication). Ils ne modifient pas le script v1.
"""
import datetime
import hashlib
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import file_management as v1  # noqa: E402

from tests.outils import CasTemporaire  # noqa: E402


class TestCritere(unittest.TestCase):
    def test_valeurs_valides(self):
        self.assertEqual(v1.analyser_critere("J"), 0)
        self.assertEqual(v1.analyser_critere("j-1"), 1)
        self.assertEqual(v1.analyser_critere(" J - 7 "), 7)
        for tout in ("TOUT", "tout", "ALL", "*"):
            self.assertIsNone(v1.analyser_critere(tout))

    def test_valeurs_invalides(self):
        for mauvais in ("", "J+1", "J-", "hier", "1"):
            with self.assertRaises(v1.ErreurConfig):
                v1.analyser_critere(mauvais)

    def test_booleen(self):
        for vrai in ("oui", "O", "yes", "true", "1"):
            self.assertTrue(v1.analyser_booleen(vrai))
        for faux in ("non", "N", "no", "false", "0", ""):
            self.assertFalse(v1.analyser_booleen(faux))
        with self.assertRaises(v1.ErreurConfig):
            v1.analyser_booleen("peut-etre")


class TestSeuil(unittest.TestCase):
    def test_seuil(self):
        maintenant = datetime.datetime(2026, 11, 3, 14, 30)
        self.assertIsNone(v1.calculer_seuil(None, maintenant))
        self.assertEqual(v1.calculer_seuil(0, maintenant),
                         datetime.datetime(2026, 11, 3).timestamp())
        self.assertEqual(v1.calculer_seuil(2, maintenant),
                         datetime.datetime(2026, 11, 1).timestamp())


class TestParametrage(CasTemporaire):
    def conf(self, texte, encodage="utf-8"):
        chemin = self.chemin("copies.conf")
        with open(chemin, "w", encoding=encodage, newline="") as f:
            f.write(texte)
        return chemin

    def test_regle_complete(self):
        chemin = self.conf("# commentaire\n\nA:\\src | B:\\dst | J-3 | *.csv;*.xml | oui\n")
        (regle,) = v1.lire_parametrage(chemin)
        self.assertEqual(regle.num_ligne, 3)
        self.assertEqual(regle.jours, 3)
        self.assertEqual(regle.masques, ["*.csv", "*.xml"])
        self.assertTrue(regle.recursif)

    def test_valeurs_par_defaut(self):
        (regle,) = v1.lire_parametrage(self.conf("a | b | TOUT\n"))
        self.assertIsNone(regle.jours)
        self.assertEqual(regle.masques, ["*"])
        self.assertFalse(regle.recursif)

    def test_bom_accepte(self):
        (regle,) = v1.lire_parametrage(self.conf("a | b | J\n", "utf-8-sig"))
        self.assertEqual(regle.jours, 0)

    def test_variable_environnement(self):
        with mock.patch.dict(os.environ, {"RACINE_TEST": "X"}):
            variable = "%RACINE_TEST%" if os.name == "nt" else "$RACINE_TEST"
            (regle,) = v1.lire_parametrage(self.conf(variable + " | b | J\n"))
        self.assertEqual(os.path.basename(regle.source), "X")

    def test_erreurs_cumulees(self):
        with self.assertRaises(v1.ErreurConfig) as cm:
            v1.lire_parametrage(self.conf("a | b\nc | d | hier\n a | a | J\n"))
        message = str(cm.exception)
        self.assertIn("ligne 1", message)
        self.assertIn("ligne 2", message)
        self.assertIn("ligne 3", message)

    def test_source_identique_a_cible(self):
        with self.assertRaises(v1.ErreurConfig):
            v1.lire_parametrage(self.conf("a | a | J\n"))

    def test_recursif_cible_dans_source(self):
        with self.assertRaises(v1.ErreurConfig):
            v1.lire_parametrage(self.conf("a | a/sous | J | * | oui\n"))
        # sans recursivite c'est accepte
        v1.lire_parametrage(self.conf("a | a/sous | J | * | non\n"))

    def test_fichier_absent_ou_vide(self):
        with self.assertRaises(v1.ErreurConfig):
            v1.lire_parametrage(self.chemin("absent.conf"))
        with self.assertRaises(v1.ErreurConfig):
            v1.lire_parametrage(self.conf("# rien\n\n"))


class TestCopieVerifiee(CasTemporaire):
    def test_copie_conserve_contenu_et_date(self):
        src = self.ecrire("src/a.csv", b"abc" * 1000, age_jours=5)
        dst = self.chemin("dst/sous/a.csv")
        sha, st = v1.copier_verifier(src, dst)
        self.assertEqual(self.lire(dst), b"abc" * 1000)
        self.assertEqual(sha, hashlib.sha256(b"abc" * 1000).hexdigest())
        self.assertEqual(st.st_size, 3000)
        self.assertAlmostEqual(os.stat(dst).st_mtime, os.stat(src).st_mtime, delta=2)
        self.assertFalse(os.path.exists(dst + v1.SUFFIXE_TMP))

    def test_fichier_vide(self):
        src = self.ecrire("src/vide.txt", b"")
        dst = self.chemin("dst/vide.txt")
        v1.copier_verifier(src, dst)
        self.assertEqual(os.path.getsize(dst), 0)

    def test_ecrase_une_cible_en_lecture_seule(self):
        src = self.ecrire("src/a.txt", b"nouveau")
        dst = self.ecrire("dst/a.txt", b"ancien")
        os.chmod(dst, 0o444)
        v1.copier_verifier(src, dst)
        self.assertEqual(self.lire(dst), b"nouveau")

    def test_reliquat_temporaire_supprime(self):
        src = self.ecrire("src/a.txt", b"x")
        dst = self.chemin("dst/a.txt")
        self.ecrire("dst/a.txt" + v1.SUFFIXE_TMP, b"reste d'une coupure")
        v1.copier_verifier(src, dst)
        self.assertFalse(os.path.exists(dst + v1.SUFFIXE_TMP))

    def test_source_modifiee_pendant_la_copie(self):
        src = self.ecrire("src/a.txt", b"x" * 100)
        dst = self.chemin("dst/a.txt")
        vrai_stat = os.stat
        appels = {"n": 0}

        def stat_truque(chemin, *a, **k):
            resultat = vrai_stat(chemin, *a, **k)
            if os.path.abspath(chemin) == os.path.abspath(src):
                appels["n"] += 1
                if appels["n"] >= 2:        # 2e lecture : apres la copie
                    return os.stat_result((resultat.st_mode, resultat.st_ino, resultat.st_dev,
                                           resultat.st_nlink, resultat.st_uid, resultat.st_gid,
                                           resultat.st_size + 1, resultat.st_atime,
                                           resultat.st_mtime, resultat.st_ctime))
            return resultat

        with mock.patch.object(v1.os, "stat", stat_truque):
            with self.assertRaises(v1.FichierInstable):
                v1.copier_verifier(src, dst)
        self.assertFalse(os.path.exists(dst))
        self.assertFalse(os.path.exists(dst + v1.SUFFIXE_TMP))

    def test_checksum_different_refuse(self):
        src = self.ecrire("src/a.txt", b"abc")
        dst = self.ecrire("dst/a.txt", b"ancien")
        with mock.patch.object(v1, "sha256_fichier", return_value="faux"):
            with self.assertRaises(IOError):
                v1.copier_verifier(src, dst)
        self.assertEqual(self.lire(dst), b"ancien")     # la cible existante n'est pas touchee
        self.assertFalse(os.path.exists(dst + v1.SUFFIXE_TMP))

    def test_essais_puis_abandon(self):
        with mock.patch.object(v1, "copier_verifier", side_effect=OSError("verrouille")) as m, \
                mock.patch.object(v1.time, "sleep") as dodo, mock.patch.object(v1, "log"):
            self.assertIsNone(v1.copier_avec_essais("s", "d", 3, 7))
        self.assertEqual(m.call_count, 3)
        self.assertEqual(dodo.call_count, 2)           # pas d'attente apres le dernier essai


class TestHistorique(CasTemporaire):
    def entree(self, h, src, dst):
        st = os.stat(src)
        h.enregistrer(src, dst, st, "sha")
        return st

    def test_aller_retour_et_deja_copie(self):
        src = self.ecrire("src/a.txt")
        dst = self.ecrire("dst/a.txt")
        h = v1.Historique(self.chemin("h.json"))
        st = self.entree(h, src, dst)
        h.sauvegarder()
        h2 = v1.Historique(self.chemin("h.json"))
        self.assertTrue(h2.deja_copie(src, dst, st))
        self.assertFalse(os.path.exists(self.chemin("h.json.tmp")))

    def test_version_modifiee_ou_cible_absente(self):
        src = self.ecrire("src/a.txt", b"1")
        dst = self.ecrire("dst/a.txt")
        h = v1.Historique(self.chemin("h.json"))
        st = self.entree(h, src, dst)
        self.ecrire("src/a.txt", b"22")
        self.assertFalse(h.deja_copie(src, dst, os.stat(src)))
        os.remove(dst)
        self.assertFalse(h.deja_copie(src, dst, st))
        self.assertTrue(h.present_mais_cible_absente(src, dst))

    def test_historique_illisible_arrete(self):
        self.ecrire("h.json", b"{pas du json")
        with self.assertRaises(v1.ErreurConfig):
            v1.Historique(self.chemin("h.json"))

    def test_purge_seulement_si_vieux_et_source_disparue(self):
        src = self.ecrire("src/a.txt")
        dst = self.ecrire("dst/a.txt")
        h = v1.Historique(self.chemin("h.json"))
        self.entree(h, src, dst)
        cle = h.cle(src, dst)
        vieux = (datetime.datetime.now() - datetime.timedelta(days=200)).isoformat(timespec="seconds")
        h.entrees[cle]["copie_le"] = vieux
        h.purger(90)
        self.assertIn(cle, h.entrees)               # la source existe encore : on garde
        os.remove(src)
        h.purger(90)
        self.assertNotIn(cle, h.entrees)


class TestVerrou(CasTemporaire):
    def test_deuxieme_verrou_refuse_puis_libere(self):
        chemin = self.chemin("x.lock")
        with v1.Verrou(chemin):
            with self.assertRaises(v1.DejaEnCours):
                with v1.Verrou(chemin):
                    pass
        with v1.Verrou(chemin):
            pass


class TestProgramme(CasTemporaire):
    """Execution de bout en bout par main(), comme Jenkins la lance."""

    def setUp(self):
        super().setUp()
        self.addCleanup(self.vider_logs)

    @staticmethod
    def vider_logs():
        for h in list(v1.log.handlers):
            h.close()
            v1.log.removeHandler(h)

    def lancer(self, *options, regles=None):
        conf = self.chemin("copies.conf")
        if regles is not None:
            with open(conf, "w", encoding="utf-8") as f:
                f.write(regles)
        self.vider_logs()
        with open(os.devnull, "w") as poubelle, mock.patch.object(sys, "stdout", poubelle):
            return v1.main(["-c", conf, "--essais", "1", "--delai", "0"] + list(options))

    def regle(self, criteres="TOUT", masque="*", recursif="non"):
        return "%s | %s | %s | %s | %s\n" % (self.chemin("src"), self.chemin("dst"),
                                             criteres, masque, recursif)

    def test_copie_puis_cible_absente_recopiee(self):
        self.ecrire("src/a.csv", b"1")
        self.ecrire("src/b.csv", b"2")
        self.assertEqual(self.lancer(regles=self.regle()), v1.CODE_OK)
        self.assertEqual(self.lire(self.chemin("dst/a.csv")), b"1")
        os.remove(self.chemin("dst/a.csv"))
        self.assertEqual(self.lancer(), v1.CODE_OK)
        self.assertTrue(os.path.isfile(self.chemin("dst/a.csv")))
        self.assertTrue(os.path.isfile(self.chemin("copies.historique.json")))

    def test_fichier_modifie_est_recopie(self):
        self.ecrire("src/a.csv", b"1")
        self.lancer(regles=self.regle())
        self.ecrire("src/a.csv", b"version 2")
        self.lancer()
        self.assertEqual(self.lire(self.chemin("dst/a.csv")), b"version 2")

    def test_simulation_ne_copie_rien(self):
        self.ecrire("src/a.csv")
        self.assertEqual(self.lancer("--simulation", regles=self.regle()), v1.CODE_OK)
        self.assertFalse(os.path.exists(self.chemin("dst")))
        self.assertFalse(os.path.exists(self.chemin("copies.historique.json")))

    def test_masque_et_critere_de_date(self):
        self.ecrire("src/recent.csv", b"r", age_jours=0)
        self.ecrire("src/ancien.csv", b"a", age_jours=10)
        self.ecrire("src/recent.txt", b"t", age_jours=0)
        self.lancer(regles=self.regle(criteres="J-2", masque="*.csv"))
        self.assertEqual(sorted(os.listdir(self.chemin("dst"))), ["recent.csv"])

    def test_recursif_reproduit_l_arborescence(self):
        self.ecrire("src/n1/n2/a.txt", b"profond")
        self.ecrire("src/b.txt", b"racine")
        self.lancer(regles=self.regle(recursif="oui"))
        self.assertEqual(self.lire(self.chemin("dst/n1/n2/a.txt")), b"profond")
        self.assertTrue(os.path.isfile(self.chemin("dst/b.txt")))

    def test_non_recursif_ignore_les_sous_dossiers(self):
        self.ecrire("src/n1/a.txt")
        self.ecrire("src/b.txt")
        self.lancer(regles=self.regle())
        self.assertEqual(os.listdir(self.chemin("dst")), ["b.txt"])

    def test_cible_deja_identique_enregistree_sans_recopie(self):
        src = self.ecrire("src/a.txt", b"meme")
        dst = self.ecrire("dst/a.txt", b"meme")
        marque = time.time() - 12345
        os.utime(dst, (marque, marque))
        self.lancer(regles=self.regle())
        self.assertAlmostEqual(os.stat(dst).st_mtime, marque, delta=2)    # pas recopie
        historique = v1.Historique(self.chemin("copies.historique.json"))
        self.assertTrue(historique.present_mais_cible_absente(src, dst) is False
                        and historique.cle(src, dst) in historique.entrees)

    def test_codes_retour(self):
        self.assertEqual(self.lancer(regles="mauvaise ligne\n"), v1.CODE_ERREUR_CONFIG)
        self.assertEqual(self.lancer(regles=self.regle()), v1.CODE_ERREUR_COPIE)   # source absente
        self.ecrire("src/a.txt")
        with v1.Verrou(self.chemin("copies.historique.json.lock")):
            self.assertEqual(self.lancer(), v1.CODE_DEJA_EN_COURS)
        self.ecrire("copies.historique.json", b"{casse")
        self.assertEqual(self.lancer(), v1.CODE_ERREUR_CONFIG)
        self.assertEqual(self.lire(self.chemin("copies.historique.json")), b"{casse")

    def test_options_invalides(self):
        with open(os.devnull, "w") as poubelle, mock.patch.object(sys, "stderr", poubelle):
            with self.assertRaises(SystemExit):
                v1.main(["-c", "x", "--essais", "0"])


if __name__ == "__main__":
    unittest.main()
