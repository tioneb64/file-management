"""J6 : dependances entre regles (EN_ATTENTE, BLOQUEE), processus fils, parallelisme, duree maximale,
arret de l'arbre de processus, fins anormales."""
import datetime
import json
import os
import subprocess
import sys
import textwrap
import time
import unittest

from copie import base as modele_base
from copie import lancement, orchestrateur, processus
from copie.dependances import BLOQUEE, EN_ATTENTE
from copie.execution import nom_hote
from tests.test_lancement import CasLancement

SEPT_HEURES = {"type": "quotidien", "heure": "07:00"}
SEPT_HEURES_QUINZE = {"type": "quotidien", "heure": "07:15"}
APRES = {"type": "apres_dependances"}
ATTENTE_LONGUE = {"aucun_fichier": {"tentatives": 100, "delai_sec": 30, "niveau_final": "ERREUR"}}
ATTENTE_COURTE = {"aucun_fichier": {"tentatives": 2, "delai_sec": 2, "niveau_final": "INFO"}}


class CasChaine(CasLancement):
    """Regles qui dependent les unes des autres, horloge simulee, sans processus fils."""

    def amorcer(self):
        """Premier lancement a 06:00 : les regles nouvelles sont enregistrees, rien ne part."""
        self.heure(6, 0)
        self.lancer_env()

    def lancer_a(self, h, m=0, jours=0, **kw):
        self.heure(h, m, jours)
        return self.lancer_env(**kw)

    def etat_de(self, ident):
        return self.regle_base(ident)

    def ordre_des_executions(self):
        lignes = self.b.c.execute("SELECT r.id FROM executions e JOIN regles r ON r.no = e.regle_no "
                                  "ORDER BY e.id").fetchall()
        return [l[0] for l in lignes]

    def en_erreur(self, ident):
        """Force une regle en ERREUR (source absente) sans passer par une execution reelle."""
        no = self.b.numero_regle(ident)
        ex = self.b.demarrer_execution(no, "planifie", 1)
        self.b.terminer_execution(ex, no, "ERREUR", motif="panne", erreur={"situation": "x", "message": "panne"})


class TestChaineDansUnLancement(CasChaine):
    def test_chaine_amont_aval_dans_un_seul_lancement(self):
        self.brute(id="a", cible=self.chemin("da"), planification=SEPT_HEURES)
        self.brute(id="b", cible=self.chemin("db"), planification=APRES, apres=["a"], mode="copie")
        self.brute(id="c", cible=self.chemin("dc"), planification=APRES, apres=["b"], mode="copie")
        self.fichier("x.csv")
        self.amorcer()
        r = self.lancer_a(7, 5)
        self.assertEqual(self.ordre_des_executions(), ["a", "b", "c"])
        self.assertEqual((r.compteurs["lancees"], r.compteurs["SUCCES"], r.code_retour), (3, 3, 0))
        # b copie ce que a a livre ; c depend de b qui ne livre rien de nouveau tant que a n'a rien livre
        self.assertEqual(self.etat_de("c")["dernier_statut"], "SUCCES")

    def test_dependance_pas_encore_tournee_en_attente_sans_alerte(self):
        self.brute(id="a", planification=SEPT_HEURES)
        self.brute(id="b", cible=self.chemin("db"), planification=APRES, apres=["a"])
        self.amorcer()
        r = self.lancer_a(6, 30)
        self.assertEqual(self.etat_de("b")["attente"], EN_ATTENTE)
        self.assertEqual((r.compteurs["en_attente"], r.compteurs["non_lancees"], r.code_retour), (1, 0, 0))
        self.assertEqual(self.evenements("regle_non_lancee"), [])           # l'attente d'une regle sans horaire est normale
        self.assertIn("n'a pas encore tourne", self.etat_de("b")["attente_motif"])

    def test_la_regle_attente_part_des_que_la_dependance_a_fini(self):
        self.brute(id="a", planification=SEPT_HEURES)
        self.brute(id="b", cible=self.chemin("db"), planification=APRES, apres=["a"])
        self.amorcer()
        self.lancer_a(6, 30)
        self.lancer_a(7, 5)
        self.assertEqual(self.ordre_des_executions(), ["a", "b"])
        self.assertIsNone(self.etat_de("b")["attente"])                   # etat d'attente efface au demarrage

    def test_une_execution_de_la_dependance_ne_declenche_qu_une_fois(self):
        self.brute(id="a", planification=SEPT_HEURES)
        self.brute(id="b", cible=self.chemin("db"), planification=APRES, apres=["a"])
        self.amorcer()
        self.lancer_a(7, 5)
        self.lancer_a(7, 10)
        self.lancer_a(7, 15)
        self.assertEqual(self.ordre_des_executions(), ["a", "b"])           # b ne repart pas sans nouvelle execution de a
        self.b.poser_lancement_manuel("a", "benoit")
        self.lancer_a(7, 20)
        self.assertEqual(self.ordre_des_executions(), ["a", "b", "a", "b"])

    def test_regle_horaire_qui_depend_d_une_autre_horaire(self):
        self.brute(id="export", cible=self.chemin("d1"), planification=SEPT_HEURES)
        self.brute(id="import", cible=self.chemin("d2"), planification=SEPT_HEURES_QUINZE, apres=["export"])
        self.amorcer()
        r = self.lancer_a(7, 20)
        self.assertEqual(self.ordre_des_executions(), ["export", "import"])
        self.assertEqual(r.code_retour, 0)


class TestEnAttente(CasChaine):
    def test_dependance_plus_tardive_avertit_une_fois_par_creneau_puis_la_regle_part(self):
        self.brute(id="export", cible=self.chemin("d1"), planification={"type": "quotidien", "heure": "08:00"})
        self.brute(id="import", cible=self.chemin("d2"), planification=SEPT_HEURES_QUINZE, apres=["export"])
        self.amorcer()
        r = self.lancer_a(7, 20)
        self.assertEqual((r.compteurs["en_attente"], r.code_retour), (1, 4))
        evenement = self.evenements("regle_non_lancee")
        self.assertEqual((len(evenement), evenement[0]["niveau"], evenement[0]["attente"]), (1, "WARNING", EN_ATTENTE))
        r = self.lancer_a(7, 25)                                         # meme creneau : pas de nouvel avertissement
        self.assertEqual((len(self.evenements("regle_non_lancee")), r.code_retour), (1, 0))
        self.assertEqual(self.etat_de("import")["attente"], EN_ATTENTE)
        # l'export tourne a 08:00 ; l'import, dont l'heure est passee, part aussitot (reprise en cascade)
        self.lancer_a(8, 5)
        self.assertEqual(self.ordre_des_executions(), ["export", "import"])

    def test_rattrapage_depasse_la_regle_repasse_a_son_etat_precedent(self):
        self.brute(id="export", cible=self.chemin("d1"), planification={"type": "quotidien", "heure": "10:00"})
        self.brute(id="import", cible=self.chemin("d2"), apres=["export"],
                   planification={"type": "quotidien", "heure": "07:15", "rattrapage_sec": 3600})
        self.amorcer()
        self.lancer_a(7, 30)
        self.assertEqual(self.etat_de("import")["attente"], EN_ATTENTE)
        self.lancer_a(8, 30)                                              # 07:15 + 1 h : le creneau a expire
        self.assertIsNone(self.etat_de("import")["attente"])
        self.lancer_a(10, 5)
        self.assertEqual(self.ordre_des_executions(), ["export"])         # import ne part pas hors rattrapage

    def test_condition_fichiers_exige_une_livraison(self):
        self.brute(id="export", cible=self.chemin("d1"), planification=SEPT_HEURES)
        self.brute(id="import", cible=self.chemin("d2"), planification=SEPT_HEURES_QUINZE, apres=["export"],
                   condition=["succes", "fichiers"], mode="copie")
        self.amorcer()
        r = self.lancer_a(7, 20)                                          # export n'a rien livre (source vide)
        self.assertEqual(self.ordre_des_executions(), ["export"])
        self.assertEqual(self.etat_de("import")["attente"], EN_ATTENTE)
        self.assertEqual(r.code_retour, 4)
        self.fichier("a.csv")                                             # un fichier arrive, export repart
        self.b.poser_lancement_manuel("export", "benoit")
        self.lancer_a(7, 30)
        self.assertEqual(self.ordre_des_executions(), ["export", "export", "import"])

    def test_condition_termine_accepte_une_dependance_en_erreur(self):
        self.brute(id="export", source=self.chemin("absente"), cible=self.chemin("d1"), planification=SEPT_HEURES)
        self.brute(id="import", cible=self.chemin("d2"), planification=SEPT_HEURES_QUINZE, apres=["export"],
                   condition=["termine"])
        self.amorcer()
        r = self.lancer_a(7, 20)
        self.assertEqual(self.ordre_des_executions(), ["export", "import"])
        self.assertEqual(self.etat_de("export")["dernier_statut"], "ERREUR")
        self.assertEqual(self.etat_de("import")["dernier_statut"], "SUCCES")

    def test_dependance_deja_en_cours_dans_un_autre_lancement(self):
        self.brute(id="export", cible=self.chemin("d1"), planification=SEPT_HEURES, duree_max_sec=86400)
        self.brute(id="import", cible=self.chemin("d2"), planification=APRES, apres=["export"])
        self.amorcer()
        self.b.demarrer_execution(self.b.numero_regle("export"), "planifie", os.getpid(),
                                  processus.date_creation(os.getpid()), hote=nom_hote())
        self.lancer_a(7, 5)
        self.assertIn("est en cours", self.etat_de("import")["attente_motif"])
        self.assertEqual(self.etat_de("import")["attente"], EN_ATTENTE)


class TestBloquee(CasChaine):
    def preparer(self):
        self.brute(id="export", source=self.chemin("absente"), cible=self.chemin("d1"), planification=SEPT_HEURES)
        self.brute(id="import", cible=self.chemin("d2"), planification=SEPT_HEURES_QUINZE, apres=["export"])
        self.amorcer()

    def test_dependance_en_erreur_bloque_la_regle_sans_propager_l_erreur(self):
        self.preparer()
        r = self.lancer_a(7, 20)
        self.assertEqual(self.ordre_des_executions(), ["export"])
        etat = self.etat_de("import")
        self.assertEqual((etat["attente"], etat["dernier_statut"]), (BLOQUEE, "JAMAIS_LANCEE"))   # l'ERREUR n'est pas propagee
        self.assertIn("export est en ERREUR", etat["attente_motif"])
        self.assertEqual(self.etat_de("export")["dernier_statut"], "ERREUR")
        evenement = self.evenements("regle_non_lancee")[0]
        self.assertEqual((evenement["regle"], evenement["attente"], evenement["bloquante"], evenement["niveau"]),
                         ("import", BLOQUEE, "export", "WARNING"))
        self.assertEqual((r.compteurs["bloquees"], r.compteurs["ERREUR"], r.code_retour), (1, 1, 1))
        # une fois par creneau
        r = self.lancer_a(7, 25)
        self.assertEqual(len(self.evenements("regle_non_lancee")), 1)
        self.assertEqual(r.code_retour, 0)                                # export est arretee : rien de nouveau a signaler

    def test_reprise_de_la_regle_en_erreur_fait_repartir_toute_la_chaine(self):
        self.preparer()
        self.lancer_a(7, 20)
        os.makedirs(self.chemin("absente"))
        self.b.poser_reprise("export", "benoit", "source retablie")
        r = self.lancer_a(7, 40)
        self.assertEqual(self.ordre_des_executions(), ["export", "export", "import"])
        self.assertEqual(self.etat_de("import")["dernier_statut"], "SUCCES")
        self.assertIsNone(self.etat_de("import")["attente"])
        self.assertEqual(r.code_retour, 0)

    def test_blocage_en_cascade(self):
        self.brute(id="a", source=self.chemin("absente"), cible=self.chemin("d1"), planification=SEPT_HEURES)
        self.brute(id="b", cible=self.chemin("d2"), planification=SEPT_HEURES_QUINZE, apres=["a"])
        self.brute(id="c", cible=self.chemin("d3"), planification=APRES, apres=["b"])
        self.amorcer()
        self.lancer_a(7, 20)
        self.assertEqual((self.etat_de("b")["attente"], self.etat_de("c")["attente"]), (BLOQUEE, BLOQUEE))
        self.assertIn("elle-meme bloquee", self.etat_de("c")["attente_motif"])
        self.assertEqual(self.etat_de("c")["dernier_statut"], "JAMAIS_LANCEE")

    def test_acquittement_de_la_dependance_debloque(self):
        self.preparer()
        self.lancer_a(7, 20)
        self.b.acquitter("export", "benoit", "traite a la main")
        self.lancer_a(7, 40)
        self.assertEqual(self.ordre_des_executions(), ["export", "import"])    # ACQUITTEE compte comme un succes

    def test_un_avertissement_ne_bloque_pas(self):
        self.brute(id="export", cible=self.chemin("d1"), planification=SEPT_HEURES)
        self.brute(id="import", cible=self.chemin("d2"), planification=SEPT_HEURES_QUINZE, apres=["export"])
        self.amorcer()
        self.source("futur.csv", age_sec=-7200)                           # date dans le futur : export termine en WARNING
        self.lancer_a(7, 20)
        self.assertEqual(self.etat_de("export")["dernier_statut"], "WARNING")
        self.assertEqual(self.ordre_des_executions(), ["export", "import"])

    def test_niveau_info_ne_change_pas_le_code_retour(self):
        self.brute(id="export", source=self.chemin("absente"), cible=self.chemin("d1"), planification=SEPT_HEURES)
        self.brute(id="info", cible=self.chemin("d2"), planification=SEPT_HEURES_QUINZE, apres=["export"],
                   si_condition_non_remplie="INFO")
        self.amorcer()
        r = self.lancer_a(7, 20)
        evenement = self.evenements("regle_non_lancee")[0]
        self.assertEqual((evenement["niveau"], r.code_retour), ("INFO", 1))      # 1 a cause d'export seulement

    def test_niveau_erreur_est_journalise_au_niveau_demande(self):
        self.brute(id="export", source=self.chemin("absente"), cible=self.chemin("d1"), planification=SEPT_HEURES)
        self.brute(id="grave", cible=self.chemin("d2"), planification=SEPT_HEURES_QUINZE, apres=["export"],
                   si_condition_non_remplie="ERREUR", apres_erreur="continuer")
        self.amorcer()
        self.lancer_a(7, 20)
        self.assertEqual(self.evenements("regle_non_lancee")[0]["niveau"], "ERREUR")

    def test_blocage_visible_dans_l_etat(self):
        self.preparer()
        self.lancer_a(7, 20)
        with modele_base.ouvrir(self.chemin_base, "production", lecture_seule=True) as ro:
            e = lancement.etat(self.parametrage(), ro, maintenant=self.ts)
        par_id = {r["id"]: r for r in e["regles"]}
        self.assertEqual((par_id["import"]["statut"], par_id["export"]["statut"]), (BLOQUEE, "ERREUR"))
        self.assertIn("export", par_id["import"]["motif"])
        self.assertIn(BLOQUEE, lancement.etat_texte(e))

    def test_dependance_absente_de_la_base_en_attente(self):
        from copie import dependances
        from copie.diagnostic import Rapport
        from copie.parametrage import lire_regle
        r = lire_regle({"id": "r", "source": "s", "cible": "c", "mode": "copie", "apres": ["inconnue"],
                        "planification": {"type": "apres_dependances"}}, 1, Rapport())
        self.assertEqual(dependances.evaluer(r, None, {}, self.b).etat, EN_ATTENTE)

    def test_bloquee_par_une_regle_deja_marquee_bloquee_dans_la_base(self):
        from copie import dependances
        self.preparer()
        self.lancer_a(7, 20)
        ligne_import = self.etat_de("import")
        lignes = {l["id"].lower(): l for l in self.b.toutes_les_regles()}
        autre = self.brute(id="suite", planification=APRES, apres=["import"], cible=self.chemin("d4"))
        from copie.diagnostic import Rapport
        from copie.parametrage import lire_regle
        r = lire_regle(dict(autre), 1, Rapport())
        self.assertEqual(dependances.evaluer(r, None, lignes, self.b).etat, BLOQUEE)


class TestPlusieursRegles(CasChaine):
    def test_regles_independantes_toutes_lancees(self):
        for ident in ("a", "b", "c"):
            self.brute(id=ident, cible=self.chemin("d" + ident), planification=SEPT_HEURES)
        self.fichier()
        self.amorcer()
        r = self.lancer_a(7, 5)
        self.assertEqual((r.compteurs["lancees"], r.compteurs["SUCCES"], r.code_retour), (3, 3, 0))

    def test_une_regle_en_erreur_ne_bloque_pas_les_autres(self):
        self.brute(id="mauvaise", source=self.chemin("absente"), cible=self.chemin("d1"), planification=SEPT_HEURES)
        self.brute(id="bonne", cible=self.chemin("d2"), planification=SEPT_HEURES)
        self.fichier()
        self.amorcer()
        r = self.lancer_a(7, 5)
        self.assertEqual((r.compteurs["SUCCES"], r.compteurs["ERREUR"], r.code_retour), (1, 1, 1))
        self.assertEqual(os.listdir(self.chemin("d2")), ["a.csv"])


# =========================================================================== #
# Processus fils reels
# =========================================================================== #
class CasProcessus(CasChaine):
    """Execution reelle : un processus fils par regle, horloge reelle."""

    def setUp(self):
        super().setUp()
        self.b.horloge = time.time
        self.maintenant = datetime.datetime.now()

    def declencher(self, *identifiants):
        """Declare les regles dues (lancement manuel) pour un lancement reel."""
        p = self.parametrage()
        self.b.synchroniser_regles([(r.id, lancement.empreinte_regle(r)) for r in p.regles if r.id])
        for ident in identifiants:
            self.b.poser_lancement_manuel(ident, "essai")
        return p

    def lancer_reel(self, *identifiants, **kw):
        p = self.declencher(*identifiants)
        return lancement.lancer(p, self.b, self.journal, **kw)

    def source_reelle(self, nom="a.csv", dossier=None):
        chemin = self.ecrire(os.path.join(dossier or "src", nom), b"contenu")
        t = time.time() - 600
        os.utime(chemin, (t, t))
        return chemin

    def execution(self, ident, dernier=True):
        no = self.b.numero_regle(ident)
        return self.b.derniere_execution(no)

    def vivant(self, pid):
        return processus.date_creation(pid) is not None


class TestFilsReels(CasProcessus):
    def test_chaque_regle_s_execute_dans_son_propre_processus(self):
        self.source_reelle()
        self.brute(id="a", cible=self.chemin("da"), planification=SEPT_HEURES)
        self.brute(id="b", source=self.chemin("src2"), cible=self.chemin("db"), planification=SEPT_HEURES)
        os.makedirs(self.chemin("src2"))
        self.source_reelle("b.csv", "src2")
        r = self.lancer_reel("a", "b")
        self.assertEqual((r.compteurs["lancees"], r.compteurs["SUCCES"], r.code_retour), (2, 2, 0))
        pids = {self.execution("a")["pid"], self.execution("b")["pid"]}
        self.assertEqual(len(pids), 2)
        self.assertNotIn(os.getpid(), pids)
        self.assertEqual(os.listdir(self.chemin("da")), ["a.csv"])
        self.assertEqual(os.listdir(self.chemin("db")), ["b.csv"])
        self.assertEqual(os.listdir(self.chemin("travail")) if os.path.isdir(self.chemin("travail")) else [], [])
        for ident in ("a", "b"):
            etat = self.regle_base(ident)
            self.assertEqual((etat["en_cours"], etat["dernier_statut"], etat["pid"]), (0, "SUCCES", None))
        # le journal : evenements du fils et fin journalisee par l'orchestrateur
        noms = [e["evenement"] for e in self.evenements()]
        self.assertEqual(noms.count("processus_regle_demarre"), 2)
        self.assertEqual(noms.count("regle_terminee"), 2)
        fin = self.evenements("regle_terminee")[0]
        self.assertEqual(fin["compteurs"]["livres"], 1)

    def test_un_fils_qui_echoue_est_rapporte_par_l_orchestrateur(self):
        self.brute(id="mauvaise", source=self.chemin("absente"), planification=SEPT_HEURES,
                   situations={"source_inaccessible": {"tentatives": 1}})
        r = self.lancer_reel("mauvaise")
        self.assertEqual((r.compteurs["ERREUR"], r.code_retour), (1, 1))
        etat = self.regle_base("mauvaise")
        self.assertEqual((etat["dernier_statut"], etat["arret_apres_erreur"]), ("ERREUR", 1))
        self.assertEqual(etat["derniere_erreur_situation"], "source_inaccessible")
        fin = self.evenements("regle_terminee")[0]
        self.assertEqual((fin["statut"], fin["niveau"]), ("ERREUR", "ERREUR"))

    def test_parallelisme_et_limite(self):
        for ident in ("a", "b", "c"):
            self.brute(id=ident, cible=self.chemin("d" + ident), planification=SEPT_HEURES,
                       situations=ATTENTE_COURTE)
        r = self.lancer_reel("a", "b", "c")
        self.assertEqual(r.compteurs["SUCCES"], 3)
        intervalles = [(self.execution(i)["debut"], self.execution(i)["fin"]) for i in ("a", "b", "c")]
        chevauchements = sum(1 for i in range(3) for j in range(i + 1, 3)
                             if intervalles[i][0] < intervalles[j][1] and intervalles[j][0] < intervalles[i][1])
        self.assertGreaterEqual(chevauchements, 1, intervalles)           # elles ont tourne en meme temps

    def test_parallele_max_un_execute_les_regles_l_une_apres_l_autre(self):
        for ident in ("a", "b"):
            self.brute(id=ident, cible=self.chemin("d" + ident), planification=SEPT_HEURES,
                       situations=ATTENTE_COURTE)
        p = self.declencher("a", "b")
        p.entete.parallele_max = 1
        r = lancement.lancer(p, self.b, self.journal)
        self.assertEqual(r.compteurs["SUCCES"], 2)
        (da, fa), (db, fb) = [(self.execution(i)["debut"], self.execution(i)["fin"]) for i in ("a", "b")]
        self.assertTrue(fa <= db or fb <= da, (da, fa, db, fb))           # aucun chevauchement

    def test_chaine_avec_processus_reels(self):
        self.source_reelle()
        self.brute(id="a", cible=self.chemin("da"), planification=SEPT_HEURES)
        self.brute(id="b", source=self.chemin("src2"), cible=self.chemin("db"), planification=APRES, apres=["a"])
        os.makedirs(self.chemin("src2"))
        self.source_reelle("b.csv", "src2")
        r = self.lancer_reel("a")
        self.assertEqual(self.ordre_des_executions(), ["a", "b"])
        self.assertEqual((r.compteurs["SUCCES"], r.code_retour), (2, 0))


class TestDureeMaximale(CasProcessus):
    def regle_longue(self, **modif):
        return self.brute(id="longue", planification=SEPT_HEURES, duree_max_sec=1, situations=ATTENTE_LONGUE, **modif)

    def test_erreur_arrete_le_fils_et_met_la_regle_en_erreur(self):
        self.regle_longue()
        debut = time.time()
        r = self.lancer_reel("longue")
        self.assertLess(time.time() - debut, 25)
        self.assertEqual((r.compteurs["ERREUR"], r.compteurs["depassees"], r.code_retour), (1, 1, 1))
        etat = self.regle_base("longue")
        self.assertEqual((etat["en_cours"], etat["dernier_statut"], etat["derniere_erreur_situation"],
                          etat["arret_apres_erreur"]), (0, "ERREUR", "duree_depassee", 1))
        ex = self.execution("longue")
        self.assertEqual(ex["statut"], "ERREUR")
        self.assertFalse(self.vivant(ex["pid"]))                          # le fils a bien ete arrete
        evenement = self.evenements("duree_depassee", "ERREUR")[0]
        self.assertEqual(evenement["action"], "erreur")

    def test_alerter_laisse_tourner_et_termine_en_warning(self):
        self.brute(id="lente", planification=SEPT_HEURES, duree_max_sec=1, si_duree_depassee="alerter",
                   situations={"aucun_fichier": {"tentatives": 2, "delai_sec": 4, "niveau_final": "INFO"}})
        r = self.lancer_reel("lente")
        self.assertEqual((r.compteurs["WARNING"], r.compteurs["depassees"], r.code_retour), (1, 1, 4))
        self.assertEqual(self.regle_base("lente")["dernier_statut"], "WARNING")
        self.assertEqual(self.execution("lente")["statut"], "WARNING")
        self.assertEqual(self.evenements("duree_depassee")[0]["action"], "alerter")
        self.assertEqual(len(self.evenements("duree_depassee")), 1)       # une seule alerte

    def test_relancer_puis_erreur_quand_les_relances_sont_epuisees(self):
        self.regle_longue(si_duree_depassee="relancer", relances_max=1)
        r = self.lancer_reel("longue")
        self.assertEqual(r.compteurs["depassees"], 2)
        actions = [e["action"] for e in self.evenements("duree_depassee")]
        self.assertEqual(actions, ["relancer", "erreur"])
        self.assertEqual(self.b.c.execute("SELECT COUNT(*) FROM executions").fetchone()[0], 2)
        etat = self.regle_base("longue")
        self.assertEqual((etat["dernier_statut"], etat["en_cours"]), ("ERREUR", 0))
        self.assertIn("relance(s) epuisee(s)", etat["dernier_motif"])

    def test_relancer_la_deuxieme_execution_peut_reussir(self):
        self.brute(id="r", planification=SEPT_HEURES, duree_max_sec=2, si_duree_depassee="relancer", relances_max=2,
                   situations={"aucun_fichier": {"tentatives": 2, "delai_sec": 5, "niveau_final": "INFO"}})
        # premiere execution : source vide, trop lente ; un fichier arrive pendant la relance
        import threading

        def deposer():
            time.sleep(3.5)
            self.source_reelle()
        self.brute  # (la regle ci-dessus lit self.src)
        fil = threading.Thread(target=deposer)
        fil.start()
        r = self.lancer_reel("r")
        fil.join()
        self.assertGreaterEqual(r.compteurs["depassees"], 1)
        self.assertEqual(self.b.c.execute("SELECT COUNT(*) FROM executions").fetchone()[0] >= 2, True)


class TestFinsAnormales(CasProcessus):
    def ecrire_fils(self, corps):
        chemin = self.chemin("faux_fils.py")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(corps))
        return lambda regle, execution_id: [sys.executable, chemin, str(execution_id), self.chemin_base]

    def lancer_avec_faux_fils(self, corps, rappel=None, *identifiants):
        p = self.declencher(*(identifiants or ("r",)))
        c = lancement.Lancement()
        o = orchestrateur.Orchestrateur(p, self.b, self.journal, c, commande_fils=self.ecrire_fils(corps),
                                        rappel=rappel, pas_sec=0.05)
        o.executer()
        return c

    def test_fils_mort_sans_resultat(self):
        self.brute(id="r", planification=SEPT_HEURES)
        c = self.lancer_avec_faux_fils("""
            import sys
            sys.stdin.readline()
            sys.exit(3)
            """)
        self.assertEqual((c.compteurs["ERREUR"], c.code_retour), (1, 1))
        etat = self.regle_base("r")
        self.assertEqual((etat["en_cours"], etat["dernier_statut"], etat["derniere_erreur_situation"],
                          etat["arret_apres_erreur"]), (0, "ERREUR", "arret_anormal", 1))
        self.assertEqual(self.execution("r")["statut"], "ARRETEE")
        evenement = self.evenements("arret_anormal")[0]
        self.assertIn("code 3", evenement["message"])
        self.assertEqual(self.evenements("regle_terminee")[0]["statut"], "ERREUR")    # fin toujours journalisee

    def test_fils_qui_a_ecrit_en_base_mais_pas_son_fichier_resultat(self):
        self.brute(id="r", planification=SEPT_HEURES)
        c = self.lancer_avec_faux_fils("""
            import sys
            sys.stdin.readline()
            sys.path.insert(0, %r)
            from copie import base
            b = base.ouvrir(sys.argv[2])
            no = b.numero_regle("r")
            b.terminer_execution(int(sys.argv[1]), no, "SUCCES", compteurs={"livres": 2}, message="fait")
            """ % os.path.dirname(os.path.dirname(os.path.abspath(modele_base.__file__))))
        self.assertEqual((c.compteurs["SUCCES"], c.code_retour), (1, 0))
        fin = self.evenements("regle_terminee")[0]
        self.assertEqual((fin["statut"], fin["compteurs"]["livres"]), ("SUCCES", 2))

    def test_le_fils_attend_le_feu_vert(self):
        self.brute(id="r", planification=SEPT_HEURES)
        marque = self.chemin("demarre.txt")
        self.lancer_avec_faux_fils("""
            import sys, time
            ligne = sys.stdin.readline()
            open(%r, "w").write(repr(ligne))
            sys.exit(0)
            """ % marque)
        self.assertEqual(open(marque).read(), repr("go\n"))

    def test_fils_tue_de_l_exterieur(self):
        self.brute(id="r", planification=SEPT_HEURES)
        tue = {"fait": False}

        def tuer(orchestre):
            if tue["fait"] or "r" not in orchestre.fils:
                return
            time.sleep(0.5)
            tue["fait"] = True
            processus.tuer_arbre(orchestre.fils["r"].popen.pid)
        c = self.lancer_avec_faux_fils("""
            import sys, time
            sys.stdin.readline()
            time.sleep(300)
            """, rappel=tuer)
        self.assertEqual((c.compteurs["ERREUR"], c.code_retour), (1, 1))
        self.assertEqual(self.regle_base("r")["derniere_erreur_situation"], "arret_anormal")

    def test_interruption_de_l_orchestrateur_arrete_les_fils(self):
        self.brute(id="r", planification=SEPT_HEURES)
        pids = {}

        def interrompre(orchestre):
            if "r" in orchestre.fils:
                pids["fils"] = orchestre.fils["r"].popen.pid
                raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.lancer_avec_faux_fils("""
                import sys, time
                sys.stdin.readline()
                time.sleep(300)
                """, rappel=interrompre)
        time.sleep(0.3)
        self.assertFalse(self.vivant(pids["fils"]))
        etat = self.regle_base("r")
        self.assertEqual((etat["en_cours"], etat["dernier_statut"]), (0, "ERREUR"))

    def test_arret_de_l_arbre_complet(self):
        """Le fils a lance un petit-fils (comme un programme externe) : les deux disparaissent."""
        self.brute(id="r", planification=SEPT_HEURES, duree_max_sec=1)
        marque = self.chemin("petit_fils.pid")
        c = self.lancer_avec_faux_fils("""
            import subprocess, sys, time
            sys.stdin.readline()
            petit = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
            open(%r, "w").write(str(petit.pid))
            time.sleep(300)
            """ % marque)
        self.assertEqual(c.compteurs["depassees"], 1)
        pid = int(open(marque).read())
        time.sleep(0.5)
        self.assertFalse(self.vivant(pid), "le petit-fils a survecu a l'arret du fils")
        self.assertEqual(self.regle_base("r")["derniere_erreur_situation"], "duree_depassee")

    def test_commande_interne_refuse_une_execution_inconnue(self):
        self.brute(id="r", planification=SEPT_HEURES)
        p = self.declencher()
        env = dict(os.environ, PYTHONPATH=orchestrateur.RACINE)
        resultat = subprocess.run([sys.executable, "-m", "copie", "--config", p.chemin, "--executer-regle", "r",
                                   "--execution-id", "999"], input="go\n", cwd=orchestrateur.RACINE, env=env,
                                  capture_output=True, text=True)
        self.assertEqual(resultat.returncode, 2)
        self.assertIn("inconnue ou deja terminee", resultat.stderr)
        sans_feu_vert = subprocess.run([sys.executable, "-m", "copie", "--config", p.chemin, "--executer-regle",
                                        "r", "--execution-id", "1"], input="", cwd=orchestrateur.RACINE, env=env,
                                       capture_output=True, text=True)
        self.assertEqual(sans_feu_vert.returncode, 1)                     # parent disparu : le fils ne fait rien


class TestExecutionsTropLonguesDUnAutreLancement(CasProcessus):
    """Une execution vivante d'un autre lancement qui depasse sa duree maximale."""

    def processus_long(self):
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
        self.addCleanup(lambda: p.poll() is None and p.kill())
        return p

    def installer(self, **modif):
        self.brute(id="r", planification=SEPT_HEURES, duree_max_sec=1, **modif)
        p = self.declencher()
        p_long = self.processus_long()
        no = self.b.numero_regle("r")
        self.b.horloge = lambda: time.time() - 100                        # l'execution a commence il y a 100 s
        self.b.demarrer_execution(no, "planifie", p_long.pid, processus.date_creation(p_long.pid), hote=nom_hote())
        self.b.horloge = time.time
        return p, p_long

    def test_erreur(self):
        p, long_ = self.installer()
        c = lancement.Lancement()
        lancement.nettoyer_orphelins(p, self.b, self.journal, c)
        long_.wait(timeout=10)
        etat = self.regle_base("r")
        self.assertEqual((etat["en_cours"], etat["dernier_statut"], etat["derniere_erreur_situation"]),
                         (0, "ERREUR", "duree_depassee"))
        self.assertEqual((c.compteurs["depassees"], c.code_retour), (1, 1))

    def test_alerter_ne_touche_pas_au_processus(self):
        p, long_ = self.installer(si_duree_depassee="alerter")
        c = lancement.Lancement()
        lancement.nettoyer_orphelins(p, self.b, self.journal, c)
        self.assertIsNone(long_.poll())
        self.assertEqual((self.regle_base("r")["en_cours"], c.code_retour), (1, 4))

    def test_relancer_arrete_et_declenche_une_nouvelle_execution(self):
        p, long_ = self.installer(si_duree_depassee="relancer")
        c = lancement.Lancement()
        lancement.nettoyer_orphelins(p, self.b, self.journal, c)
        long_.wait(timeout=10)
        etat = self.regle_base("r")
        self.assertEqual((etat["en_cours"], etat["lancement_manuel"], etat["relances"]), (0, 1, 1))

    def test_pas_de_depassement_avant_la_duree_maximale(self):
        self.brute(id="r", planification=SEPT_HEURES, duree_max_sec=3600)
        p = self.declencher()
        long_ = self.processus_long()
        self.b.demarrer_execution(self.b.numero_regle("r"), "planifie", long_.pid,
                                  processus.date_creation(long_.pid), hote=nom_hote())
        c = lancement.Lancement()
        lancement.nettoyer_orphelins(p, self.b, self.journal, c)
        self.assertIsNone(long_.poll())
        self.assertEqual(c.compteurs["depassees"], 0)


class TestProcessus(unittest.TestCase):
    def tuer(self, *popen):
        for p in popen:
            if p.poll() is None:
                p.kill()

    def lancer_arbre(self):
        code = ("import subprocess, sys, time\n"
                "print(subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)']).pid, flush=True)\n"
                "time.sleep(300)\n")
        p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
        self.addCleanup(self.tuer, p)
        petit = int(p.stdout.readline())
        return p, petit

    @unittest.skipUnless(sys.platform == "win32", "Job Object Windows")
    def test_job_object_arrete_le_processus_et_ses_descendants(self):
        job = processus.JobObject()
        self.addCleanup(job.fermer)
        p = subprocess.Popen([sys.executable, "-c",
                              "import subprocess, sys, time\n"
                              "sys.stdin.readline()\n"
                              "print(subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)']).pid, flush=True)\n"
                              "time.sleep(300)\n"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.addCleanup(self.tuer, p)
        self.assertTrue(job.assigner(p))
        p.stdin.write("go\n")
        p.stdin.flush()
        petit = int(p.stdout.readline())
        self.assertIsNotNone(processus.date_creation(petit))
        self.assertTrue(job.terminer())
        p.wait(timeout=10)
        time.sleep(0.3)
        self.assertIsNone(processus.date_creation(petit))

    @unittest.skipUnless(sys.platform == "win32", "Job Object Windows")
    def test_fermer_le_job_arrete_ce_qui_reste(self):
        job = processus.JobObject()
        p, petit = self.lancer_arbre()
        # deja demarre : on place le pere dans le job ; le petit-fils lance AVANT n'en fait pas partie
        self.assertTrue(job.assigner(p))
        job.fermer()
        p.wait(timeout=10)
        self.assertIsNotNone(p.returncode)
        self.addCleanup(lambda: processus.tuer_arbre(petit))

    def test_tuer_arbre(self):
        p, petit = self.lancer_arbre()
        self.assertTrue(processus.tuer_arbre(p.pid))
        p.wait(timeout=10)
        time.sleep(0.5)
        self.assertIsNone(processus.date_creation(petit))
        self.assertFalse(processus.tuer_arbre(p.pid))                      # deja parti

    def test_un_processus_ne_s_arrete_pas_lui_meme(self):
        self.assertFalse(processus.tuer_arbre(os.getpid()))
        self.assertIsNotNone(processus.date_creation(os.getpid()))

    def test_processus_inexistant(self):
        self.assertIsNone(processus.date_creation(2 ** 22 + 12345))
        self.assertFalse(processus.vivant(2 ** 22 + 12345, None))

    def test_resultat_ecrit_atomiquement_puis_supprime(self):
        class Entete(object):
            dossier_travail = None
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            e = Entete()
            e.dossier_travail = os.path.join(d, "travail")
            orchestrateur.ecrire_resultat(e, {"execution_id": 7, "statut": "SUCCES", "regle": "r"})
            self.assertEqual(os.listdir(e.dossier_travail), ["resultat_7.json"])
            self.assertEqual(orchestrateur.lire_resultat(e, 7)["statut"], "SUCCES")
            self.assertEqual(os.listdir(e.dossier_travail), [])
            self.assertIsNone(orchestrateur.lire_resultat(e, 7))
            with open(orchestrateur.chemin_resultat(e, 8), "w") as f:
                f.write("{pas du json")
            self.assertIsNone(orchestrateur.lire_resultat(e, 8))


if __name__ == "__main__":
    unittest.main()
