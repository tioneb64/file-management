"""Fins en ERREUR decidees HORS de l'execution d'une regle (deblocage, duree maximale, processus disparu) :
le programme `sur_erreur` est appele, les livraisons incertaines sont visibles tout de suite, et une reprise
d'une regle en aval n'attend pas un nouveau passage de son amont (docs/02, sections 2, 3 et 9)."""
import datetime
import json
import os
import sys
import time

from file_management import lancement
from tests.test_contrat import CasDeblocage
from tests.test_orchestrateur import (APRES, ATTENTE_LONGUE, SEPT_HEURES, CasChaine, CasProcessus)

SCRIPT_ALERTE = """\
import json, os
with open(%r, "w", encoding="utf-8") as f:
    json.dump({k: v for k, v in os.environ.items() if k.startswith("COPIE_")}, f)
"""


class OutilAlerte(object):
    def programme_alerte(self):
        """Programme `sur_erreur` factice : enregistre les variables COPIE_* qu'il a recues."""
        self.sortie_alerte = self.chemin("alerte.json")
        script = self.chemin("alerte.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(SCRIPT_ALERTE % self.sortie_alerte)
        return {"commande": [sys.executable, script], "timeout_sec": 30}

    def alerte_recue(self):
        if not os.path.exists(self.sortie_alerte):
            return None
        with open(self.sortie_alerte, encoding="utf-8") as f:
            return json.load(f)


class TestDeblocage(OutilAlerte, CasDeblocage):
    def test_deblocage_appelle_sur_erreur(self):
        p, long_ = self.installer(programmes={"sur_erreur": self.programme_alerte()})
        self.debloquer(p)
        long_.wait(timeout=10)
        recu = self.alerte_recue()
        self.assertIsNotNone(recu, "le programme sur_erreur n'a pas ete appele apres le deblocage")
        self.assertEqual((recu["COPIE_REGLE"], recu["COPIE_SITUATION"], recu["COPIE_STATUT"], recu["COPIE_POINT_APPEL"]),
                         ("r1", "deblocage", "ERREUR", "sur_erreur"))
        self.assertIn("debloquee par benoit", recu["COPIE_MESSAGE"])
        self.assertEqual(self.regle_base("r1")["dernier_statut"], "ERREUR")

    def test_deblocage_sans_programme_sur_erreur(self):
        p, long_ = self.installer()
        r = self.debloquer(p)
        long_.wait(timeout=10)
        self.assertTrue(r["drapeau_libere"])
        self.assertEqual(r["livraisons_incertaines"], 0)

    def test_un_programme_sur_erreur_en_echec_n_empeche_pas_le_deblocage(self):
        p, long_ = self.installer(programmes={"sur_erreur": {"commande": [self.chemin("introuvable.exe")],
                                                             "timeout_sec": 5}})
        r = self.debloquer(p)
        long_.wait(timeout=10)
        self.assertTrue(r["drapeau_libere"])
        self.assertEqual(self.regle_base("r1")["dernier_statut"], "ERREUR")

    def test_deblocage_rend_visibles_les_livraisons_incertaines(self):
        p, long_ = self.installer()
        no = self.b.numero_regle("r1")
        self.b.noter_intention(no, b"0123456789abcdef", self.chemin("source_disparue.csv"),
                               self.chemin("cible_partielle.csv"), taille=10, mtime_ns=1)
        r = self.debloquer(p)
        long_.wait(timeout=10)
        self.assertEqual(r["livraisons_incertaines"], 1)
        self.assertIn("1 livraison(s) de resultat inconnu", r["message"])
        self.assertEqual(self.b.nb_incertains(no), 1)                      # visible AVANT toute reprise
        self.assertEqual(lancement.etat(p, self.b)["regles"][0]["livraisons_incertaines"], 1)
        self.assertEqual(len(self.evenements("livraison_incertaine", "CRITICAL")), 1)
        self.b.resoudre_incertain(b"0123456789abcdef", "a_relivrer", "benoit", "copie incomplete")
        self.assertEqual(self.b.nb_incertains(no), 0)                      # tranchable sans reprise


class TestDureeDepassee(OutilAlerte, CasProcessus):
    def test_duree_depassee_appelle_sur_erreur(self):
        self.brute(id="longue", planification=SEPT_HEURES, duree_max_sec=1, situations=ATTENTE_LONGUE,
                   programmes={"sur_erreur": self.programme_alerte()})
        debut = time.time()
        r = self.lancer_reel("longue")
        self.assertLess(time.time() - debut, 25)
        self.assertEqual(r.compteurs["ERREUR"], 1)
        recu = self.alerte_recue()
        self.assertIsNotNone(recu, "le programme sur_erreur n'a pas ete appele apres la duree depassee")
        self.assertEqual((recu["COPIE_REGLE"], recu["COPIE_SITUATION"]), ("longue", "duree_depassee"))
        self.assertIn("duree maximale depassee", recu["COPIE_MESSAGE"])

    def test_alerter_n_appelle_pas_sur_erreur(self):
        self.brute(id="lente", planification=SEPT_HEURES, duree_max_sec=1, si_duree_depassee="alerter",
                   situations={"aucun_fichier": {"tentatives": 3, "delai_sec": 1, "niveau_final": "INFO"}},
                   programmes={"sur_erreur": self.programme_alerte()})
        self.lancer_reel("lente")
        self.assertIsNone(self.alerte_recue())                              # la regle finit en WARNING, pas en ERREUR


class TestRepriseEnAval(CasChaine):
    def preparer_chaine(self):
        self.fichier("x.csv")
        self.brute(id="amont", cible=self.chemin("d_amont"), planification=SEPT_HEURES)
        self.brute(id="aval", source=self.chemin("absente"), cible=self.chemin("d_aval"), planification=APRES,
                   apres=["amont"], mode="copie")
        self.amorcer()
        self.lancer_a(7, 5)

    def retablir_la_source_de_l_aval(self):
        os.makedirs(self.chemin("absente"), exist_ok=True)
        fichier = self.chemin(os.path.join("absente", "y.csv"))
        with open(fichier, "wb") as f:
            f.write(b"y")
        hier = (self.jour - datetime.timedelta(days=1)).timestamp()         # l'horloge du test est simulee
        os.utime(fichier, (hier, hier))

    def test_reprise_de_l_aval_seule_n_attend_pas_l_amont(self):
        self.preparer_chaine()
        self.assertEqual(self.ordre_des_executions(), ["amont", "aval"])
        self.assertEqual(self.etat_de("aval")["dernier_statut"], "ERREUR")
        self.retablir_la_source_de_l_aval()
        self.b.poser_reprise("aval", "benoit", "source retablie")
        r = self.lancer_a(7, 40)
        self.assertEqual(self.ordre_des_executions(), ["amont", "aval", "aval"])   # l'amont n'a pas tourne
        self.assertEqual(self.etat_de("aval")["dernier_statut"], "SUCCES")
        self.assertIsNone(self.etat_de("aval")["attente"])
        self.assertEqual(r.code_retour, 0)

    def test_reprise_de_l_aval_reste_bloquee_si_l_amont_est_en_erreur(self):
        self.preparer_chaine()
        self.retablir_la_source_de_l_aval()
        self.en_erreur("amont")                                             # l'amont vient d'echouer
        self.b.poser_reprise("aval", "benoit", "source retablie")
        self.lancer_a(7, 40)
        self.assertEqual(self.ordre_des_executions().count("aval"), 1)      # pas relancee
        self.assertEqual(self.etat_de("aval")["attente"], "BLOQUEE")

    def test_lancement_manuel_de_l_aval_attend_toujours_l_amont(self):
        self.preparer_chaine()
        self.retablir_la_source_de_l_aval()
        self.b.poser_lancement_manuel("aval", "benoit")
        self.lancer_a(7, 40)
        self.assertEqual(self.ordre_des_executions().count("aval"), 1)      # seule la reprise est dispensee
        self.assertEqual(self.etat_de("aval")["attente"], "EN_ATTENTE")
