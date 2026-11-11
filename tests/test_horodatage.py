"""Option `horodater` (modes copie et archivage) : marque chaque fichier traite d'un horodatage."""
import datetime
import os
import unittest
from unittest import mock

from file_management import base as modele_base
from file_management import chemins, transfert
from file_management.diagnostic import Rapport
from file_management.modele import regle_par_defaut
from file_management.parametrage import lire_regle
from tests.test_moteur import CasMoteur


class TestNomHorodate(unittest.TestCase):
    INSTANT = datetime.datetime(2026, 11, 11, 10, 30, 12)

    def test_forme_du_nom(self):
        self.assertEqual(chemins.nom_horodate("a.csv", self.INSTANT), "a_traite_20261111_103012.csv")
        self.assertEqual(chemins.nom_horodate("a.csv", self.INSTANT, 1), "a_traite_20261111_103012_2.csv")
        self.assertEqual(chemins.nom_horodate("a.tar.gz", self.INSTANT), "a.tar_traite_20261111_103012.gz")
        self.assertEqual(chemins.nom_horodate("sans_extension", self.INSTANT), "sans_extension_traite_20261111_103012")

    def test_reconnaissance_du_marqueur(self):
        for nom in ("a_traite_20261111_103012.csv", "a_traite_20261111_103012_2.csv", "x_traite_20260101_000000"):
            self.assertTrue(chemins.est_horodate(nom), nom)
        # une date ordinaire dans le nom d'origine n'est PAS une marque
        for nom in ("export_20261111_103012.csv", "a.csv", "traite_20261111_103012.csv", "a_traite_2026.csv"):
            self.assertFalse(chemins.est_horodate(nom), nom)

    def test_un_nom_marque_est_reconnu_apres_marquage(self):
        for nom in ("a.csv", "b.tar.gz", "sans_extension", ".cache"):
            self.assertTrue(chemins.est_horodate(chemins.nom_horodate(nom, self.INSTANT)), nom)


class TestHorodatageCopie(CasMoteur):
    def marque(self, nom="a.csv"):
        return chemins.nom_horodate(nom, self.maintenant)

    def test_l_original_est_marque_dans_la_source_et_la_cible_garde_son_nom(self):
        a = self.source("a.csv", b"contenu A")
        r = self.regle(horodater=True)
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 1))
        self.assertEqual(self.livres(self.dst), ["a.csv"])
        self.assertFalse(os.path.exists(a))
        self.assertEqual(self.lire(os.path.join(self.src, self.marque())), b"contenu A")
        self.assertEqual(len(self.evenements("fichier_horodate")), 1)

    def test_le_fichier_marque_n_est_pas_copie_de_nouveau(self):
        self.source("a.csv")
        r = self.regle(horodater=True)
        self.lancer(r)
        bilan = self.lancer(r)
        self.assertEqual((bilan.compteurs["selectionnes"], bilan.compteurs["livres"]), (0, 0))
        self.assertEqual(self.livres(self.dst), ["a.csv"])
        self.assertEqual(len(self.evenements("fichier_horodate")), 1)

    def test_sans_l_option_rien_n_est_renomme(self):
        a = self.source("a.csv")
        self.lancer(self.regle())
        self.assertTrue(os.path.exists(a))
        self.assertEqual(self.evenements("fichier_horodate"), [])

    def test_une_nouvelle_version_du_meme_nom_est_copiee_puis_marquee(self):
        self.source("a.csv", b"v1")
        r = self.regle(horodater=True, si_existe_cible="suffixe")
        self.lancer(r)
        self.source("a.csv", b"version 2")
        bilan = self.lancer(r)                           # meme seconde : le nom marque existe deja
        self.assertEqual(bilan.compteurs["livres"], 1)
        self.assertEqual(sorted(os.listdir(self.src)),
                         sorted([self.marque(), chemins.nom_horodate("a.csv", self.maintenant, 1)]))

    def test_une_date_ordinaire_dans_le_nom_d_origine_n_empeche_pas_la_copie(self):
        self.source("export_20261111_103012.csv")
        bilan = self.lancer(self.regle(horodater=True))
        self.assertEqual(bilan.compteurs["livres"], 1)
        self.assertEqual(self.livres(self.dst), ["export_20261111_103012.csv"])

    def test_simulation_ne_renomme_rien(self):
        a = self.source("a.csv")
        bilan = self.lancer(self.regle(horodater=True), simulation=True)
        self.assertEqual(bilan.compteurs["livres"], 1)
        self.assertTrue(os.path.exists(a))

    def test_original_modifie_apres_la_copie_n_est_pas_marque(self):
        a = self.source("a.csv", b"contenu")
        r = self.regle(horodater=True)
        vraie = transfert.copier_verifier

        def copier_puis_modifier(src, *args, **kw):
            copie = vraie(src, *args, **kw)
            with open(src, "ab") as f:                   # le producteur reecrit le fichier juste apres
                f.write(b"+")
            return copie
        with mock.patch.object(transfert, "copier_verifier", copier_puis_modifier):
            self.lancer(r)
        self.assertTrue(os.path.exists(a))
        self.assertEqual(len(self.evenements("horodatage_ignore")), 1)

    def test_echec_du_marquage_est_un_avertissement_repris_au_lancement_suivant(self):
        a = self.source("a.csv")
        r = self.regle(horodater=True)
        vraie = transfert.renommer

        def renommer(source, destination, ecraser):
            if os.path.dirname(source) == self.src:      # seulement le marquage de l'original
                raise transfert.ErreurCible("fichier verrouille")
            return vraie(source, destination, ecraser)
        with mock.patch.object(transfert, "renommer", renommer):
            bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("WARNING", 1))
        self.assertTrue(os.path.exists(a))
        self.assertEqual(len(self.evenements("horodatage_echec", "WARNING")), 1)
        bilan = self.lancer(r)                           # le fichier est deja livre : il n'est que marque
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 0))
        self.assertFalse(os.path.exists(a))
        self.assertTrue(os.path.exists(os.path.join(self.src, self.marque())))
        self.assertEqual(self.livres(self.dst), ["a.csv"])

    def test_en_deplacement_l_option_est_sans_effet(self):
        self.source("a.csv")
        r = self.regle(mode="deplacement")
        r.horodater = True                               # R16 a l'enregistrement ; le moteur l'ignore
        self.lancer(r)
        self.assertEqual(os.listdir(self.src), [])
        self.assertEqual(self.livres(self.dst), ["a.csv"])


class TestHorodatageArchivage(CasMoteur):
    def test_le_fichier_archive_porte_l_heure_de_l_archivage(self):
        a = self.source("a.csv", b"contenu")
        r = self.regle(mode="archivage", archive=self.arch, horodater=True)
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 1))
        self.assertFalse(os.path.exists(a))
        attendu = chemins.nom_horodate("a.csv", self.maintenant)
        self.assertEqual(self.livres(self.arch), [attendu])
        self.assertEqual(self.livres(self.dst), ["a.csv"])      # la cible garde le nom d'origine
        self.assertEqual(self.b.actions(self.no(r)), [])
        self.assertEqual(self.etats(), [modele_base.TERMINE])

    def test_se_combine_avec_le_renommage_de_l_archive(self):
        self.source("a.csv")
        r = self.regle(mode="archivage", archive=self.arch, horodater=True, renommage_archive="{nom}.arch{ext}")
        self.lancer(r)
        self.assertEqual(self.livres(self.arch), [chemins.nom_horodate("a.arch.csv", self.maintenant)])

    def test_archive_dans_la_source_les_fichiers_marques_ne_sont_pas_relus(self):
        self.source("a.csv")
        r = self.regle(mode="archivage", archive=os.path.join(self.src, "archive"), horodater=True,
                       selection={"recursif": True})
        self.lancer(r)
        bilan = self.lancer(r)
        self.assertEqual((bilan.compteurs["selectionnes"], bilan.compteurs["livres"]), (0, 0))

    def test_sans_l_option_le_nom_est_conserve(self):
        self.source("a.csv")
        self.lancer(self.regle(mode="archivage", archive=self.arch))
        self.assertEqual(self.livres(self.arch), ["a.csv"])


class TestHorodatageParametrage(unittest.TestCase):
    def lire(self, **modif):
        brut = {"id": "r1", "source": "D:\\in", "cible": "D:\\out", "mode": "copie",
                "planification": {"type": "quotidien", "heure": "07:00"}}
        brut.update(modif)
        rapport = Rapport()
        return lire_regle(brut, 1, rapport), rapport

    def codes(self, rapport):
        return sorted({d.code for d in rapport.refus + rapport.avertissements})

    def test_faux_par_defaut_et_dans_le_modele_du_front_end(self):
        r, rapport = self.lire()
        self.assertEqual((r.horodater, self.codes(rapport)), (False, []))
        self.assertIs(regle_par_defaut()["horodater"], False)

    def test_accepte_pour_copie_et_archivage(self):
        r, rapport = self.lire(horodater=True)
        self.assertEqual((r.horodater, self.codes(rapport)), (True, []))
        r, rapport = self.lire(horodater=True, mode="archivage", archive="archive")
        self.assertEqual((r.horodater, self.codes(rapport)), (True, []))

    def test_avertissement_R16_pour_les_autres_modes(self):
        _, rapport = self.lire(horodater=True, mode="deplacement")
        self.assertEqual(self.codes(rapport), ["R16"])
        _, rapport = self.lire(horodater=True, mode="suppression", cible=None)
        self.assertIn("R16", self.codes(rapport))

    def test_doit_etre_un_booleen(self):
        _, rapport = self.lire(horodater="oui")
        self.assertEqual(self.codes(rapport), ["E06"])


if __name__ == "__main__":
    unittest.main()
