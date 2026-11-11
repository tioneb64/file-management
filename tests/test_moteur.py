"""J4 : execution complete d'une regle (copie, deplacement, archivage, situations, pannes)."""
import copy
import datetime
import glob
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import journal_si
from file_management import base as modele_base
from file_management import catalogue_journal, chemins, execution, transfert
from file_management.diagnostic import Rapport
from file_management.parametrage import Entete, lire_regle
from tests.outils import CasTemporaire, lire_journaux


class Plantage(BaseException):
    """Simule un arret brutal du processus (ne doit etre attrape par aucun `except Exception`)."""


class CasMoteur(CasTemporaire):
    @classmethod
    def setUpClass(cls):
        cls.dossier_modele = tempfile.mkdtemp(prefix="copie_modele_")
        cls.addClassCleanup(shutil.rmtree, cls.dossier_modele, True)
        cls.modele = os.path.join(cls.dossier_modele, "modele.db")
        modele_base.initialiser(cls.modele, "production", "testeur")
        with modele_base.ouvrir(cls.modele) as b:
            b.c.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def setUp(self):
        super().setUp()
        self.src, self.dst, self.arch = self.chemin("src"), self.chemin("dst"), self.chemin("arch")
        os.makedirs(self.src)
        self.chemin_base = self.chemin("donnees", "production.db")
        os.makedirs(os.path.dirname(self.chemin_base))
        shutil.copy(self.modele, self.chemin_base)
        self.b = modele_base.ouvrir(self.chemin_base, "production")
        self.addCleanup(self.b.fermer)
        self.entete = Entete()
        self.entete.environnement = "production"
        self.journal = journal_si.Journal()
        self.journal.catalogue = catalogue_journal.decrire             # comme le moteur (__main__._nouveau_journal)
        self.journal.debut("file_management", "prod", dossier=self.chemin("logs"), verbeux=True)
        self.addCleanup(self.journal.fermer)
        self.maintenant = datetime.datetime.now()
        self.pauses = []

    # ----- fabrication d'une regle ---------------------------------------- #
    def regle(self, **modif):
        brut = {"id": "r1", "source": self.src, "cible": self.dst, "mode": "copie",
                "planification": {"type": "quotidien", "heure": "07:00"}}
        for cle, valeur in modif.items():
            if isinstance(valeur, dict) and isinstance(brut.get(cle), dict) and cle != "planification":
                brut[cle].update(valeur)
            else:
                brut[cle] = valeur
        rapport = Rapport()
        r = lire_regle(copy.deepcopy(brut), 1, rapport)
        self.assertEqual(rapport.refus, [], rapport.en_texte())
        r.brut = json.dumps(brut)
        self.b.synchroniser_regles([(r.id, "e")])
        return r

    def lancer(self, regle, simulation=False, dormir=None, base=None):
        return execution.lancer_regle(regle, self.entete, base or self.b, self.journal,
                                      simulation=simulation, maintenant=lambda: self.maintenant,
                                      dormir=dormir or self.pauses.append)

    def evenements(self, nom=None, niveau=None):
        resultat = lire_journaux(self.chemin("logs"))
        return [e for e in resultat if (nom is None or e["evenement"] == nom)
                and (niveau is None or e["niveau"] == niveau)]

    # ----- fichiers -------------------------------------------------------- #
    def source(self, nom, contenu=b"contenu", age_sec=300):
        chemin = self.ecrire(os.path.join("src", nom), contenu)
        instant = self.maintenant.timestamp() - age_sec
        os.utime(chemin, (instant, instant))
        return chemin

    def livres(self, dossier=None):
        racine = dossier or self.dst
        trouves = []
        for dossier_, _, noms in os.walk(racine):
            trouves.extend(os.path.relpath(os.path.join(dossier_, n), racine) for n in noms)
        return sorted(trouves)

    def etats(self):
        return sorted(l["etat"] for l in self.b.c.execute("SELECT etat FROM fichiers"))

    def no(self, regle):
        return self.b.numero_regle(regle.id)


# =========================================================================== #
class TestModeCopie(CasMoteur):
    def test_livraison_verifiee_puis_aucun_doublon(self):
        a = self.source("a.csv", b"contenu A")
        self.source("b.csv", b"contenu B")
        r = self.regle()
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"], bilan.compteurs["erreurs"]), ("SUCCES", 2, 0))
        self.assertEqual(self.livres(), ["a.csv", "b.csv"])
        self.assertEqual(self.lire(os.path.join(self.dst, "a.csv")), b"contenu A")
        self.assertEqual(os.stat(os.path.join(self.dst, "a.csv")).st_mtime_ns, os.stat(a).st_mtime_ns)
        self.assertTrue(os.path.exists(a))                                   # copie : l'original reste
        self.assertEqual(self.etats(), [modele_base.TERMINE] * 2)
        self.assertEqual(self.b.actions(self.no(r)), [])
        # second lancement : rien de nouveau
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"], bilan.compteurs["ignores"]), ("SUCCES", 0, 2))
        self.assertEqual(len(self.evenements("fichier_livre")), 2)

    def test_execution_et_etat_enregistres_en_base(self):
        self.source("a.csv")
        r = self.regle()
        self.lancer(r)
        etat = self.b.regle(self.no(r))
        self.assertEqual((etat["en_cours"], etat["dernier_statut"]), (0, "SUCCES"))
        ex = self.b.c.execute("SELECT * FROM executions").fetchone()
        self.assertEqual((ex["statut"], ex["nb_livres"], ex["declencheur"]), ("SUCCES", 1, "manuel"))
        self.assertEqual([e["evenement"] for e in self.evenements() if e["evenement"].startswith("regle_")],
                         ["regle_demarree", "regle_terminee"])

    def test_nouvelle_version_livree_a_nouveau(self):
        self.source("a.csv", b"v1")
        r = self.regle(si_existe_cible="ecraser")       # le destinataire n'a pas encore pris la v1
        self.lancer(r)
        self.source("a.csv", b"version 2")
        self.assertEqual(self.lancer(r).compteurs["livres"], 1)
        self.assertEqual(self.lire(os.path.join(self.dst, "a.csv")), b"version 2")
        # meme taille, nouvelle date : nouvelle version aussi
        chemin = self.source("a.csv", b"version 3")
        os.utime(chemin, (self.maintenant.timestamp() - 10, self.maintenant.timestamp() - 10))
        self.assertEqual(self.lancer(r).compteurs["livres"], 1)

    def test_sous_dossiers_reproduits(self):
        self.source(os.path.join("n1", "n2", "a.txt"), b"profond")
        self.source("b.txt")
        self.lancer(self.regle(selection={"recursif": True}))
        self.assertEqual(self.livres(), ["b.txt", os.path.join("n1", "n2", "a.txt")])

    def test_renommage_de_la_cible(self):
        self.source("C1.xml")
        self.lancer(self.regle(renommage_cible="{nom}_{AAAA}{MM}{JJ}_{hh}{mm}{ss}{ext}"))
        attendu = "C1_%s.xml" % self.maintenant.strftime("%Y%m%d_%H%M%S")
        self.assertEqual(self.livres(), [attendu])

    def test_nom_renomme_invalide_refuse(self):
        self.source("a.csv")
        self.source("b.csv")
        bilan = self.lancer(self.regle(renommage_cible="{nom}:{ext}"))
        self.assertEqual(self.livres(), [])
        self.assertEqual(bilan.statut, "ERREUR")
        self.assertEqual(bilan.situation_finale, "copie_echec")
        self.assertEqual(self.pauses, [])                       # pas de nouvelle tentative inutile
        self.assertEqual(self.etats(), [])                      # aucune trace d'intention

    def test_masque_exclusion_age_et_limite(self):
        self.source("a.csv", age_sec=1000)
        self.source("b.csv", age_sec=900)
        self.source("c.csv", age_sec=800)
        self.source("~d.csv", age_sec=800)
        self.source("neuf.csv", age_sec=1)
        self.source("e.txt")
        r = self.regle(selection={"masque": "*.csv", "exclure": "~*", "age_minimum_sec": 60,
                                  "ordre": "date_modification", "limite_fichiers": 2})
        bilan = self.lancer(r)
        self.assertEqual(self.livres(), ["a.csv", "b.csv"])            # les 2 plus anciens
        self.assertEqual(bilan.compteurs["selectionnes"], 3)
        self.assertEqual(self.lancer(r).compteurs["livres"], 1)          # rattrapage progressif
        self.assertEqual(self.livres(), ["a.csv", "b.csv", "c.csv"])

    def test_dossier_cible_cree(self):
        self.source("a.csv")
        self.lancer(self.regle(cible=self.chemin("nouveau", "profond")))
        self.assertEqual(self.livres(self.chemin("nouveau", "profond")), ["a.csv"])

    def test_cible_absente_sans_creation_est_une_erreur(self):
        self.source("a.csv")
        bilan = self.lancer(self.regle(creer_dossiers=False, cible=self.chemin("absent")))
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "cible_inaccessible"))
        self.assertEqual(len(self.pauses), 2)                            # 3 tentatives, 2 attentes
        self.assertEqual(bilan.compteurs["livres"], 0)

    def test_source_absente(self):
        bilan = self.lancer(self.regle(source=self.chemin("absente")))
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "source_inaccessible"))
        self.assertEqual(self.pauses, [30, 30])

    def test_fichiers_temporaires_du_moteur_jamais_livres(self):
        self.source("a.csv")
        self.source("b.csv.copie_en_cours")
        self.lancer(self.regle())
        self.assertEqual(self.livres(), ["a.csv"])

    def test_dossier_temporaire_separe(self):
        self.source("a.csv")
        tmp = self.chemin("tmp_arrivee")
        self.lancer(self.regle(dossier_temporaire=tmp))
        self.assertEqual(self.livres(), ["a.csv"])
        self.assertEqual(os.listdir(tmp), [])

    def test_aucun_fichier_avec_boucle(self):
        r = self.regle(situations={"aucun_fichier": {"tentatives": 3, "delai_sec": 300, "niveau_final": "ERREUR"}})
        bilan = self.lancer(r)
        self.assertEqual(self.pauses, [300, 300])
        self.assertEqual(bilan.statut, "ERREUR")
        self.assertTrue(bilan.arret_apres_erreur)

    def test_aucun_fichier_par_defaut_n_est_pas_une_anomalie(self):
        bilan = self.lancer(self.regle())
        self.assertEqual((bilan.statut, self.pauses, bilan.arret_apres_erreur), ("SUCCES", [], False))

    def test_le_fichier_arrive_pendant_la_boucle(self):
        r = self.regle(situations={"aucun_fichier": {"tentatives": 3, "delai_sec": 60, "niveau_final": "ERREUR"}})

        def dormir(secondes):
            self.pauses.append(secondes)
            self.source("arrive.csv")
        bilan = self.lancer(r, dormir=dormir)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"], self.pauses), ("SUCCES", 1, [60]))

    def test_date_dans_le_futur_signalee(self):
        self.source("futur.csv", age_sec=-7200)
        self.source("a.csv")
        bilan = self.lancer(self.regle())
        self.assertEqual((bilan.statut, self.livres()), ("WARNING", ["a.csv"]))
        self.assertEqual(len(self.evenements("fichier_date_future")), 1)

    def test_apres_erreur_continuer(self):
        r = self.regle(source=self.chemin("absente"), apres_erreur="continuer")
        self.assertFalse(self.lancer(r).arret_apres_erreur)
        r = self.regle(id="r2", source=self.chemin("absente"))
        self.assertTrue(self.lancer(r).arret_apres_erreur)
        self.assertEqual(self.b.regle(self.no(r))["arret_apres_erreur"], 1)


class TestExistenceCible(CasMoteur):
    def preparer(self, **modif):
        self.source("a.csv", b"nouveau")
        self.ecrire("dst/a.csv", b"occupant")
        return self.regle(**modif)

    def test_erreur_par_defaut(self):
        bilan = self.lancer(self.preparer())
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "fichier_existe_cible"))
        self.assertEqual(self.lire(os.path.join(self.dst, "a.csv")), b"occupant")
        self.assertEqual(self.etats(), [])                               # aucune trace : sera retente

    def test_attente_que_le_destinataire_prenne_le_fichier(self):
        r = self.preparer(situations={"fichier_existe_cible": {"tentatives": 3, "delai_sec": 60,
                                                               "niveau_final": "ERREUR"}})

        def dormir(secondes):
            self.pauses.append(secondes)
            os.remove(os.path.join(self.dst, "a.csv"))              # le logiciel destinataire l'a pris
        bilan = self.lancer(r, dormir=dormir)
        self.assertEqual((bilan.statut, self.pauses), ("SUCCES", [60]))
        self.assertEqual(self.lire(os.path.join(self.dst, "a.csv")), b"nouveau")

    def test_ecraser(self):
        self.assertEqual(self.lancer(self.preparer(si_existe_cible="ecraser")).statut, "SUCCES")
        self.assertEqual(self.lire(os.path.join(self.dst, "a.csv")), b"nouveau")

    def test_ignorer(self):
        bilan = self.lancer(self.preparer(si_existe_cible="ignorer"))
        self.assertEqual((bilan.statut, bilan.compteurs["ignores"], bilan.compteurs["livres"]), ("SUCCES", 1, 0))
        self.assertEqual(self.lire(os.path.join(self.dst, "a.csv")), b"occupant")
        self.assertEqual(self.etats(), [])

    def test_suffixe(self):
        bilan = self.lancer(self.preparer(si_existe_cible="suffixe"))
        self.assertEqual(bilan.statut, "SUCCES")
        noms = self.livres()
        self.assertEqual(len(noms), 2)
        self.assertEqual(self.lire(os.path.join(self.dst, "a.csv")), b"occupant")
        suffixe = [n for n in noms if n != "a.csv"][0]
        self.assertRegex(suffixe, r"^a_\d{8}_\d{6}\.csv$")


class TestIdentiteContenu(CasMoteur):
    def test_fichier_regenere_a_l_identique_non_relivre(self):
        r = self.regle(identite="contenu")
        self.source("a.csv", b"meme contenu")
        self.assertEqual(self.lancer(r).compteurs["livres"], 1)
        chemin = self.source("a.csv", b"meme contenu")                   # regenere : autre date
        os.utime(chemin, (self.maintenant.timestamp() - 20, self.maintenant.timestamp() - 20))
        bilan = self.lancer(r)
        self.assertEqual((bilan.compteurs["livres"], bilan.compteurs["ignores"]), (0, 1))
        self.assertEqual(len(self.evenements("doublon_contenu")), 1)
        # la version regeneree est memorisee : plus relue au lancement suivant
        with mock.patch.object(transfert, "sha256_fichier") as lecture:
            self.assertEqual(self.lancer(r).compteurs["ignores"], 1)
        lecture.assert_not_called()

    def test_contenu_different_relivre(self):
        r = self.regle(identite="contenu", si_existe_cible="ecraser")
        self.source("a.csv", b"v1")
        self.lancer(r)
        self.source("a.csv", b"v2 different")
        self.assertEqual(self.lancer(r).compteurs["livres"], 1)

    def test_la_version_par_defaut_relivre_un_fichier_regenere(self):
        r = self.regle(si_existe_cible="ecraser")
        self.source("a.csv", b"meme contenu")
        self.lancer(r)
        chemin = self.source("a.csv", b"meme contenu")
        os.utime(chemin, (self.maintenant.timestamp() - 20, self.maintenant.timestamp() - 20))
        self.assertEqual(self.lancer(r).compteurs["livres"], 1)

    def test_doublon_en_mode_deplacement_original_traite(self):
        r = self.regle(identite="contenu", mode="deplacement")
        self.source("a.csv", b"meme contenu")
        self.lancer(r)
        self.source("a.csv", b"meme contenu", age_sec=200)             # regenere : autre date
        bilan = self.lancer(r)
        self.assertEqual((bilan.compteurs["livres"], bilan.compteurs["ignores"]), (0, 1))
        self.assertFalse(os.path.exists(os.path.join(self.src, "a.csv")))      # supprime sans relivrer


class TestSiCibleAbsente(CasMoteur):
    def test_ignorer_par_defaut(self):
        r = self.regle()
        self.source("a.csv")
        self.lancer(r)
        os.remove(os.path.join(self.dst, "a.csv"))                     # le destinataire l'a prise
        self.assertEqual(self.lancer(r).compteurs["livres"], 0)
        self.assertEqual(self.livres(), [])

    def test_recopier(self):
        r = self.regle(si_cible_absente="recopier")
        self.source("a.csv")
        self.lancer(r)
        os.remove(os.path.join(self.dst, "a.csv"))
        self.assertEqual(self.lancer(r).compteurs["livres"], 1)
        self.assertEqual(self.livres(), ["a.csv"])
        self.assertEqual(self.lancer(r).compteurs["livres"], 0)         # present : plus rien


class TestModeDeplacement(CasMoteur):
    def test_original_supprime_apres_verification(self):
        a = self.source("a.csv", b"contenu")
        os.chmod(a, 0o444)                                              # lecture seule : doit partir quand meme
        r = self.regle(mode="deplacement")
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 1))
        self.assertFalse(os.path.exists(a))
        self.assertEqual(self.lire(os.path.join(self.dst, "a.csv")), b"contenu")
        self.assertEqual((self.etats(), self.b.actions(self.no(r))), ([modele_base.TERMINE], []))
        self.assertEqual(len(self.evenements("fichier_supprime")), 1)

    def test_original_modifie_apres_la_copie_est_conserve(self):
        a = self.source("a.csv", b"version 1")
        vraie_copie = transfert.copier_verifier

        def copie_puis_modification(*args, **kw):
            resultat = vraie_copie(*args, **kw)
            with open(a, "wb") as f:                                   # nouvelle version pendant le traitement
                f.write(b"version 2, plus longue")
            return resultat
        with mock.patch.object(transfert, "copier_verifier", copie_puis_modification):
            bilan = self.lancer(self.regle(mode="deplacement", si_existe_cible="ecraser"))
        self.assertTrue(os.path.exists(a))                              # G4 : jamais supprime
        self.assertEqual(self.lire(os.path.join(self.dst, "a.csv")), b"version 1")
        self.assertEqual(bilan.statut, "WARNING")
        self.assertEqual(len(self.evenements("fichier_erreur", "WARNING")), 1)
        # la nouvelle version est livree normalement au lancement suivant
        self.assertEqual(self.lancer(self.regle(mode="deplacement", si_existe_cible="ecraser")).compteurs["livres"], 1)
        self.assertEqual(self.lire(os.path.join(self.dst, "a.csv")), b"version 2, plus longue")
        self.assertFalse(os.path.exists(a))

    @unittest.skipUnless(sys.platform == "win32", "partage de fichiers Windows")
    def test_suppression_impossible_puis_reussie_au_lancement_suivant_sans_relivrer(self):
        a = self.source("a.csv")
        r = self.regle(mode="deplacement", situations={"suppression_echec": {"tentatives": 1}})
        with open(a, "rb"):                                              # fichier ouvert : suppression refusee
            bilan = self.lancer(r)
            self.assertEqual((bilan.statut, bilan.compteurs["livres"], bilan.compteurs["en_attente"]),
                             ("WARNING", 1, 1))
            self.assertTrue(os.path.exists(a))
            self.assertEqual(self.etats(), [modele_base.LIVRE])
            self.assertEqual([x["type"] for x in self.b.actions(self.no(r))], ["suppression"])
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"], bilan.compteurs["en_attente"]),
                         ("SUCCES", 0, 0))
        self.assertFalse(os.path.exists(a))
        self.assertEqual((self.etats(), self.b.actions(self.no(r))), ([modele_base.TERMINE], []))
        self.assertEqual(len(self.evenements("fichier_livre")), 1)       # jamais relivre

    @unittest.skipUnless(sys.platform == "win32", "partage de fichiers Windows")
    def test_suppression_reussit_a_la_deuxieme_tentative(self):
        a = self.source("a.csv")
        f = open(a, "rb")
        self.addCleanup(lambda: f.closed or f.close())

        def dormir(secondes):
            self.pauses.append(secondes)
            f.close()
        r = self.regle(mode="deplacement")
        bilan = self.lancer(r, dormir=dormir)
        self.assertEqual((bilan.statut, self.pauses), ("SUCCES", [10]))
        self.assertFalse(os.path.exists(a))

    @unittest.skipUnless(sys.platform == "win32", "partage de fichiers Windows")
    def test_suppression_impossible_avec_arret_de_la_regle(self):
        a = self.source("a.csv")
        self.source("b.csv")
        r = self.regle(mode="deplacement", situations={"suppression_echec": {"tentatives": 1,
                                                                              "suite": "arreter_regle"}})
        with open(a, "rb"):
            bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.situation_finale), ("WARNING", "suppression_echec"))
        self.assertEqual(self.livres(), ["a.csv"])                      # b.csv jamais traite


class TestModeArchivage(CasMoteur):
    def regle_archive(self, **modif):
        return self.regle(mode="archivage", archive=self.arch, **modif)

    def test_original_deplace_dans_l_archive(self):
        a = self.source("a.csv", b"contenu")
        r = self.regle_archive()
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 1))
        self.assertFalse(os.path.exists(a))
        self.assertEqual(self.lire(os.path.join(self.arch, "a.csv")), b"contenu")
        self.assertEqual(self.lire(os.path.join(self.dst, "a.csv")), b"contenu")
        self.assertEqual((self.etats(), self.b.actions(self.no(r))), ([modele_base.TERMINE], []))
        self.assertEqual(len(self.evenements("fichier_archive")), 1)

    def test_archive_relative_datee_dans_la_source_non_reselectionnee(self):
        self.source("a.csv")
        r = self.regle(mode="archivage", archive=".\\archive\\{AAAA}-{MM}-{JJ}",
                       selection={"recursif": True})
        self.lancer(r)
        jour = self.maintenant.strftime("%Y-%m-%d")
        self.assertTrue(os.path.exists(os.path.join(self.src, "archive", jour, "a.csv")))
        bilan = self.lancer(r)                                          # l'archive n'est pas relue comme source
        self.assertEqual((bilan.compteurs["selectionnes"], bilan.compteurs["livres"]), (0, 0))
        self.assertEqual(self.livres(), ["a.csv"])

    def test_arborescence_reproduite_et_renommage_archive(self):
        self.source(os.path.join("n1", "a.csv"))
        self.lancer(self.regle_archive(selection={"recursif": True}, renommage_archive="{nom}{ext}.arch"))
        self.assertEqual(self.livres(self.arch), [os.path.join("n1", "a.csv.arch")])

    def test_nom_deja_archive_suffixe_par_defaut(self):
        self.ecrire("arch/a.csv", b"ancien archive")
        self.source("a.csv", b"nouveau")
        self.lancer(self.regle_archive())
        noms = self.livres(self.arch)
        self.assertEqual(len(noms), 2)
        self.assertEqual(self.lire(os.path.join(self.arch, "a.csv")), b"ancien archive")   # jamais ecrase

    def test_nom_deja_archive_ecraser_ou_erreur(self):
        self.ecrire("arch/a.csv", b"ancien archive")
        self.source("a.csv", b"nouveau")
        self.lancer(self.regle_archive(si_existe_archive="ecraser"))
        self.assertEqual(self.lire(os.path.join(self.arch, "a.csv")), b"nouveau")

    def test_nom_deja_archive_erreur(self):
        self.ecrire("arch/a.csv", b"ancien archive")
        a = self.source("a.csv", b"nouveau")
        r = self.regle_archive(si_existe_archive="erreur",
                               situations={"fichier_existe_archive": {"suite": "fichier_suivant"}})
        bilan = self.lancer(r)
        self.assertEqual(bilan.statut, "ERREUR")
        self.assertTrue(os.path.exists(a))                              # original conserve
        self.assertEqual(self.lire(os.path.join(self.arch, "a.csv")), b"ancien archive")

    def test_autre_volume_copie_verifiee_puis_suppression(self):
        a = self.source("a.csv", b"contenu")
        with mock.patch.object(chemins, "meme_volume", return_value=False):
            bilan = self.lancer(self.regle_archive())
        self.assertEqual((bilan.statut, self.livres(self.arch)), ("SUCCES", ["a.csv"]))
        self.assertFalse(os.path.exists(a))
        self.assertEqual(os.listdir(self.arch), ["a.csv"])               # pas de temporaire

    def test_original_modifie_non_archive(self):
        a = self.source("a.csv", b"version 1")
        vraie_copie = transfert.copier_verifier

        def copie_puis_modification(*args, **kw):
            resultat = vraie_copie(*args, **kw)
            if args[0] == a:
                with open(a, "wb") as f:
                    f.write(b"version 2, plus longue")
            return resultat
        with mock.patch.object(transfert, "copier_verifier", copie_puis_modification):
            bilan = self.lancer(self.regle_archive())
        self.assertEqual(bilan.statut, "WARNING")
        self.assertTrue(os.path.exists(a))
        self.assertEqual(self.livres(self.arch), [])


class TestArchiveDegradee(CasMoteur):
    def archive_bloquee(self):
        self.ecrire("arch_bloquee", b"un fichier a la place du dossier d'archive")
        return self.chemin("arch_bloquee")

    def test_livraison_poursuivie_et_archivage_differe(self):
        a = self.source("a.csv")
        r = self.regle(mode="archivage", archive=self.archive_bloquee())
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"], bilan.compteurs["en_attente"]),
                         ("WARNING", 1, 1))
        self.assertEqual(self.livres(), ["a.csv"])
        self.assertTrue(os.path.exists(a))                              # pas encore archive
        etat = self.b.regle(self.no(r))
        self.assertEqual(etat["archivage_degrade"], 1)
        self.assertEqual([x["type"] for x in self.b.actions(self.no(r))], ["archivage"])
        self.assertEqual(self.etats(), [modele_base.LIVRE])
        self.assertEqual(len(self.evenements("archivage_degrade", "WARNING")), 1)
        self.assertEqual(self.pauses, [30, 30])                         # 3 tentatives avant de basculer
        # chaque execution rappelle l'anomalie, sans relivrer
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("WARNING", 0))
        self.assertEqual(len(self.evenements("archivage_degrade")), 2)
        self.assertEqual(len(self.evenements("fichier_livre")), 1)
        # aucun fichier temoin dans le dossier de production
        self.assertEqual(sorted(os.listdir(self.src)), ["a.csv"])

    def test_retablissement_vide_la_file_et_leve_le_drapeau(self):
        a = self.source("a.csv", b"contenu")
        self.source("b.csv", b"autre")
        archive = self.archive_bloquee()
        r = self.regle(mode="archivage", archive=archive)
        self.lancer(r)
        os.remove(archive)                                              # l'archive redevient accessible
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"], bilan.compteurs["en_attente"]),
                         ("SUCCES", 0, 0))
        self.assertEqual(self.livres(archive), ["a.csv", "b.csv"])
        self.assertFalse(os.path.exists(a))
        self.assertEqual(self.b.regle(self.no(r))["archivage_degrade"], 0)
        self.assertEqual(len(self.evenements("archivage_retabli")), 1)
        self.assertEqual((self.etats(), self.b.actions(self.no(r))), ([modele_base.TERMINE] * 2, []))

    def test_original_modifie_pendant_la_panne_n_est_pas_archive(self):
        a = self.source("a.csv", b"ancienne version")
        archive = self.archive_bloquee()
        r = self.regle(mode="archivage", archive=archive, si_existe_cible="ecraser")
        self.lancer(r)
        self.source("a.csv", b"une nouvelle version, plus longue")
        os.remove(archive)
        bilan = self.lancer(r)
        # G4 : l'action differee n'a pas archive la nouvelle version a la place de l'ancienne ;
        # l'avertissement le dit, puis la nouvelle version est livree et archivee normalement.
        avertissements = self.evenements("fichier_erreur", "WARNING")
        self.assertEqual([e["situation"] for e in avertissements], ["source_modifiee"])
        self.assertEqual(bilan.compteurs["livres"], 1)
        self.assertEqual(self.lire(os.path.join(archive, "a.csv")), b"une nouvelle version, plus longue")
        self.assertEqual(self.lire(os.path.join(self.dst, "a.csv")), b"une nouvelle version, plus longue")
        self.assertFalse(os.path.exists(a))
        self.assertEqual(len(self.evenements("fichier_livre")), 2)       # les deux versions ont ete livrees

    def test_arreter_la_regle_ne_copie_rien(self):
        self.source("a.csv")
        r = self.regle(mode="archivage", archive=self.archive_bloquee(),
                       situations={"archive_inaccessible": {"suite": "arreter_regle",
                                                            "niveau_final": "ERREUR"}})
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "archive_inaccessible"))
        self.assertEqual(self.livres(), [])
        self.assertEqual(self.etats(), [])

    def test_archive_inutile_hors_mode_archivage(self):
        self.source("a.csv")
        bilan = self.lancer(self.regle(mode="copie", archive=self.archive_bloquee()))
        self.assertEqual(bilan.statut, "SUCCES")


class TestEspaceDisque(CasMoteur):
    def test_espace_insuffisant_sur_la_cible(self):
        self.source("a.csv", b"x" * 1000)
        self.entete.marge_espace_mo = 64
        with mock.patch.object(chemins, "espace_disponible", return_value=10 * 1024 * 1024):
            bilan = self.lancer(self.regle())
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "espace_insuffisant_cible"))
        self.assertEqual(self.livres(), [])
        self.assertEqual(self.etats(), [])

    def test_exactement_assez_de_place(self):
        self.source("a.csv", b"x" * 1000)
        self.entete.marge_espace_mo = 0
        with mock.patch.object(chemins, "espace_disponible", return_value=1000):
            self.assertEqual(self.lancer(self.regle()).statut, "SUCCES")

    def test_le_controle_ne_porte_que_sur_ce_qui_sera_livre(self):
        r = self.regle()
        self.source("deja.csv", b"x" * 5000)
        self.lancer(r)
        self.entete.marge_espace_mo = 0
        with mock.patch.object(chemins, "espace_disponible", return_value=10):
            bilan = self.lancer(r)                                       # rien de nouveau : aucun besoin
        self.assertEqual(bilan.statut, "SUCCES")

    def test_archive_sur_le_meme_volume_que_la_source_sans_controle(self):
        self.source("a.csv", b"x" * 1000)
        self.entete.marge_espace_mo = 0
        appels = []

        def libre(chemin):
            appels.append(os.path.normcase(chemin))
            return 1_000_000
        with mock.patch.object(chemins, "espace_disponible", libre):
            self.lancer(self.regle(mode="archivage", archive=self.arch))
        self.assertEqual(appels, [os.path.normcase(self.dst)])            # la cible seulement

    def test_archive_sur_un_autre_volume_controlee_et_degradee_si_pleine(self):
        a = self.source("a.csv", b"x" * 1000)
        self.entete.marge_espace_mo = 0

        def libre(chemin):
            return 10 if os.path.normcase(chemin) == os.path.normcase(self.arch) else 10_000_000
        with mock.patch.object(chemins, "meme_volume", return_value=False), \
                mock.patch.object(chemins, "espace_disponible", libre):
            bilan = self.lancer(self.regle(mode="archivage", archive=self.arch))
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("WARNING", 1))
        self.assertTrue(os.path.exists(a))
        self.assertEqual(self.b.regle(self.no(self.regle(mode="archivage", archive=self.arch)))["archivage_degrade"], 1)


class TestSituationsEtTentatives(CasMoteur):
    @unittest.skipUnless(sys.platform == "win32", "verrous de region Windows")
    def test_fichier_verrouille_puis_libere_pendant_les_tentatives(self):
        import msvcrt
        a = self.source("a.csv", b"x" * 100)
        f = open(a, "r+b")
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 50)
        self.addCleanup(lambda: f.closed or f.close())

        def dormir(secondes):
            self.pauses.append(secondes)
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 50)
            f.close()
        r = self.regle()
        bilan = self.lancer(r, dormir=dormir)
        self.assertEqual((bilan.statut, self.pauses, self.livres()), ("SUCCES", [60], ["a.csv"]))
        tentative = self.evenements("tentative_echouee")
        self.assertEqual((len(tentative), tentative[0]["situation"], tentative[0]["niveau"]),
                         (1, "fichier_verrouille", "WARNING"))
        self.assertEqual(self.etats(), [modele_base.TERMINE])

    @unittest.skipUnless(sys.platform == "win32", "verrous de region Windows")
    def test_fichier_toujours_verrouille_arrete_la_regle_par_defaut(self):
        import msvcrt
        a = self.source("a.csv", b"x" * 100)
        self.source("b.csv")
        f = open(a, "r+b")
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 50)
        try:
            bilan = self.lancer(self.regle())
        finally:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 50)
            f.close()
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "fichier_verrouille"))
        self.assertEqual(self.pauses, [60, 60, 60, 60])                 # 5 tentatives
        self.assertEqual(self.livres(), [])                              # arreter_regle : b.csv non traite
        self.assertEqual(self.etats(), [])                               # l'intention est effacee : sera retente
        self.assertTrue(bilan.arret_apres_erreur)

    @unittest.skipUnless(sys.platform == "win32", "verrous de region Windows")
    def test_fichier_suivant_traite_les_autres(self):
        import msvcrt
        a = self.source("a.csv", b"x" * 100)
        self.source("b.csv")
        f = open(a, "r+b")
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 50)
        try:
            r = self.regle(situations={"fichier_verrouille": {"tentatives": 2, "delai_sec": 5,
                                                              "suite": "fichier_suivant"}})
            bilan = self.lancer(r)
        finally:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 50)
            f.close()
        self.assertEqual((bilan.statut, bilan.compteurs["erreurs"], bilan.compteurs["livres"]), ("ERREUR", 1, 1))
        self.assertEqual(self.livres(), ["b.csv"])
        self.assertEqual(self.pauses, [5])

    def test_fichier_disparu_est_ignore_sans_erreur(self):
        a = self.source("a.csv")
        self.source("b.csv")
        vraie_copie = transfert.copier_verifier

        def copie(src, *args, **kw):
            if src == a:
                os.remove(a)                                          # pris par un autre logiciel
            return vraie_copie(src, *args, **kw)
        with mock.patch.object(transfert, "copier_verifier", copie):
            bilan = self.lancer(self.regle())
        self.assertEqual((bilan.statut, bilan.compteurs["ignores"], bilan.compteurs["erreurs"]), ("SUCCES", 1, 0))
        self.assertEqual(self.livres(), ["b.csv"])
        self.assertEqual(self.etats(), [modele_base.TERMINE])

    def test_fichier_instable_modifie_pendant_la_copie(self):
        a = self.source("a.csv", b"x" * 100)
        vraie_copie = transfert.copier_verifier
        appels = {"n": 0}

        def copie(src, dst, tmp, ecraser=False, attendu=None):
            appels["n"] += 1
            if appels["n"] == 1:
                with open(a, "ab") as f:                             # encore en cours d'ecriture
                    f.write(b"+")
            return vraie_copie(src, dst, tmp, ecraser, None)
        with mock.patch.object(transfert, "copier_verifier", copie):
            bilan = self.lancer(self.regle(situations={"fichier_instable": {"tentatives": 3, "delai_sec": 1,
                                                                            "niveau_final": "WARNING"}}))
        # 1re tentative : l'original a change depuis le listage ; les suivantes : copie normale
        self.assertEqual(self.pauses, [])
        self.assertEqual(bilan.statut, "SUCCES")
        self.assertEqual(self.livres(), ["a.csv"])

    def test_copie_en_echec_fichier_suivant_puis_arret(self):
        for nom in ("a.csv", "b.csv", "c.csv"):
            self.source(nom)
        vraie_copie = transfert.copier_verifier

        def copie(src, *args, **kw):
            if os.path.basename(src) == "b.csv":
                raise transfert.ErreurCible("disque plein")
            return vraie_copie(src, *args, **kw)
        with mock.patch.object(transfert, "copier_verifier", copie):
            bilan = self.lancer(self.regle(situations={"copie_echec": {"suite": "fichier_suivant"}}))
        self.assertEqual((bilan.statut, self.livres(), bilan.compteurs["erreurs"]),
                         ("ERREUR", ["a.csv", "c.csv"], 1))
        self.assertEqual(self.pauses, [10, 10])
        with mock.patch.object(transfert, "copier_verifier", copie):
            bilan = self.lancer(self.regle(id="r2", cible=self.chemin("dst2")))      # arreter_regle par defaut
        self.assertEqual(self.livres(self.chemin("dst2")), ["a.csv"])

    def test_verification_en_echec_ne_laisse_rien(self):
        self.source("a.csv")
        with mock.patch.object(transfert, "sha256_fichier", return_value="faux"):
            bilan = self.lancer(self.regle())
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "verification_echec"))
        self.assertEqual(os.listdir(self.dst), [])
        self.assertEqual(self.etats(), [])

    def test_erreur_info_ne_change_pas_le_statut(self):
        self.source("a.csv")
        r = self.regle(situations={"copie_echec": {"tentatives": 1, "niveau_final": "INFO",
                                                   "suite": "fichier_suivant"}})
        with mock.patch.object(transfert, "copier_verifier", side_effect=transfert.ErreurCible("x")):
            bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["erreurs"]), ("SUCCES", 0))


class TestArretBrutal(CasMoteur):
    def test_arret_apres_la_copie_avant_la_confirmation(self):
        self.source("a.csv", b"contenu")
        r = self.regle()
        with mock.patch.object(modele_base.Base, "confirmer_livraison", side_effect=Plantage):
            with self.assertRaises(Plantage):
                self.lancer(r)
        self.assertEqual(self.etats(), [modele_base.INTENTION])
        self.assertEqual(self.b.regle(self.no(r))["en_cours"], 0)        # le flag n'est pas laisse orphelin
        # au lancement suivant : la copie est retrouvee intacte dans la cible, elle est reconnue livree
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 0))
        self.assertEqual(self.etats(), [modele_base.TERMINE])
        self.assertEqual(self.livres(), ["a.csv"])
        self.assertEqual(len(self.evenements("livraison_reprise")), 1)

    def test_arret_avant_la_copie_rend_le_resultat_incertain(self):
        self.source("a.csv")
        r = self.regle()
        with mock.patch.object(transfert, "copier_verifier", side_effect=Plantage):
            with self.assertRaises(Plantage):
                self.lancer(r)
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "livraison_incertaine"))
        self.assertEqual(self.livres(), [])                              # on ne relivre PAS dans le doute
        self.assertEqual(self.etats(), [modele_base.INCERTAIN])
        # tant que personne ne tranche, la regle reste bloquee
        self.assertEqual(self.lancer(r).situation_finale, "livraison_incertaine")
        self.assertEqual(self.livres(), [])
        # decision d'exploitation : a relivrer
        (cle, _, _), = self.b.incertains(self.no(r))
        self.b.resoudre_incertain(cle, "a_relivrer", "benoit", "absent de la cible")
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 1))
        self.assertEqual(self.livres(), ["a.csv"])

    def test_decision_livre_ne_relivre_pas(self):
        self.source("a.csv")
        r = self.regle()
        with mock.patch.object(transfert, "copier_verifier", side_effect=Plantage):
            with self.assertRaises(Plantage):
                self.lancer(r)
        self.lancer(r)
        (cle, _, _), = self.b.incertains(self.no(r))
        self.b.resoudre_incertain(cle, "livre", "benoit", "le destinataire l'a deja prise")
        self.assertEqual(self.lancer(r).compteurs["livres"], 0)
        self.assertEqual(self.livres(), [])

    def test_si_cible_absente_recopier_relivre_sans_decision(self):
        self.source("a.csv")
        r = self.regle(si_cible_absente="recopier")
        with mock.patch.object(transfert, "copier_verifier", side_effect=Plantage):
            with self.assertRaises(Plantage):
                self.lancer(r)
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 1))
        self.assertEqual(self.livres(), ["a.csv"])

    def test_mode_deplacement_arret_apres_la_copie(self):
        a = self.source("a.csv", b"contenu")
        r = self.regle(mode="deplacement")
        with mock.patch.object(modele_base.Base, "confirmer_livraison", side_effect=Plantage):
            with self.assertRaises(Plantage):
                self.lancer(r)
        bilan = self.lancer(r)
        self.assertEqual(bilan.statut, "SUCCES")
        self.assertFalse(os.path.exists(a))                              # la suppression a eu lieu apres reprise
        self.assertEqual(self.etats(), [modele_base.TERMINE])
        self.assertEqual(self.livres(), ["a.csv"])

    def test_arret_pendant_une_action_differee_ne_relivre_pas(self):
        a = self.source("a.csv")
        r = self.regle(mode="deplacement")
        with mock.patch.object(transfert, "supprimer_original", side_effect=Plantage):
            with self.assertRaises(Plantage):
                self.lancer(r)
        self.assertEqual(self.etats(), [modele_base.LIVRE])
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 0))
        self.assertFalse(os.path.exists(a))
        self.assertEqual(len(self.evenements("fichier_livre")), 1)

    def test_defaut_du_programme_ne_laisse_pas_de_flag(self):
        self.source("a.csv")
        r = self.regle()
        with mock.patch.object(execution.ExecutionRegle, "_selectionner", side_effect=RuntimeError("bug")):
            bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "erreur_interne"))
        etat = self.b.regle(self.no(r))
        self.assertEqual((etat["en_cours"], etat["dernier_statut"]), (0, "ERREUR"))
        self.assertEqual(len(self.evenements("erreur_interne", "CRITICAL")), 1)


class TestSimulation(CasMoteur):
    def test_rien_n_est_ecrit(self):
        a = self.source("a.csv")
        r = self.regle(mode="archivage", archive=self.arch)
        avant = {t: self.b.c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
                 for t in ("fichiers", "executions", "actions_en_attente")}
        with modele_base.ouvrir(self.chemin_base, "production", lecture_seule=True) as ro:
            bilan = self.lancer(r, simulation=True, base=ro)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"], bilan.compteurs["octets"]), ("SUCCES", 1, 7))
        self.assertFalse(os.path.exists(self.dst))                        # dossiers non crees
        self.assertFalse(os.path.exists(self.arch))
        self.assertTrue(os.path.exists(a))
        apres = {t: self.b.c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0] for t in avant}
        self.assertEqual(avant, apres)
        self.assertEqual(self.b.regle(self.no(r))["en_cours"], 0)
        a_livrer = self.evenements("fichier_a_livrer")
        self.assertEqual(len(a_livrer), 1)
        self.assertTrue(a_livrer[0]["simulation"])

    def test_simulation_connait_les_fichiers_deja_livres(self):
        self.source("a.csv")
        r = self.regle()
        self.lancer(r)
        self.source("b.csv")
        with modele_base.ouvrir(self.chemin_base, "production", lecture_seule=True) as ro:
            bilan = self.lancer(r, simulation=True, base=ro)
        self.assertEqual((bilan.compteurs["livres"], bilan.compteurs["ignores"]), (1, 1))
        self.assertEqual(self.livres(), ["a.csv"])

    def test_simulation_d_une_regle_inconnue_de_la_base(self):
        self.source("a.csv")
        brut = self.regle(id="nouvelle")
        self.b.c.execute("DELETE FROM regles WHERE id = 'nouvelle'")
        with modele_base.ouvrir(self.chemin_base, "production", lecture_seule=True) as ro:
            bilan = self.lancer(brut, simulation=True, base=ro)
        self.assertEqual(bilan.compteurs["livres"], 1)


class TestFlag(CasMoteur):
    def test_regle_deja_en_cours(self):
        r = self.regle()
        self.assertIsNotNone(self.b.demarrer_execution(self.no(r), "planifie", 1))
        with self.assertRaises(execution.RegleDejaEnCours):
            self.lancer(r)

    def test_regle_non_synchronisee(self):
        r = self.regle()
        self.b.c.execute("DELETE FROM regles")
        with self.assertRaises(modele_base.ErreurBase):
            self.lancer(r)

    def test_interruption_clavier_libere_le_flag(self):
        self.source("a.csv")
        r = self.regle()
        with mock.patch.object(execution.ExecutionRegle, "_selectionner", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.lancer(r)
        self.assertEqual(self.b.regle(self.no(r))["en_cours"], 0)


if __name__ == "__main__":
    unittest.main()
