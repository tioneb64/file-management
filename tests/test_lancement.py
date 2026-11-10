"""J5 : lancement sequentiel, reprise, acquittement, lancement manuel, orphelins, --etat."""
import contextlib
import datetime
import io
import json
import os
import subprocess
import sys
import unittest

from copie import __main__ as cli
from copie import base as modele_base
from copie import lancement, planification, processus
from copie.controles import verifier_fichier
from copie.execution import nom_hote
from tests.test_moteur import CasMoteur

QUOTIDIEN_7H = {"type": "quotidien", "heure": "07:00"}


class CasLancement(CasMoteur):
    """Lancements a une heure simulee (date et heure locales du poste)."""

    def setUp(self):
        super().setUp()
        self.jour = datetime.datetime(2026, 7, 15)               # milieu d'ete : pas de changement d'heure
        self.heure(6, 0)
        self.regles_brutes = []
        self.b.horloge = self.ts                                  # les dates de la base suivent l'horloge simulee

    def heure(self, h, m=0, jours=0):
        self.maintenant = self.jour + datetime.timedelta(days=jours, hours=h, minutes=m)

    def ts(self):
        return self.maintenant.timestamp()

    def brute(self, **modif):
        brut = {"id": "r1", "source": self.src, "cible": self.dst, "mode": "deplacement",
                "planification": QUOTIDIEN_7H, "selection": {"age_minimum_sec": 0}}
        brut.update(modif)
        self.regles_brutes.append(brut)
        return brut

    def parametrage(self):
        chemin = self.chemin("production.jsonl")
        entete = {"version": 1, "environnement": "production", "base": self.chemin_base,
                  "dossier_logs": self.chemin("logs"), "marge_espace_mo": 0}
        with open(chemin, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in [entete] + self.regles_brutes) + "\n")
        p, rapport = verifier_fichier(chemin)
        self.assertTrue(rapport.ok, rapport.en_texte())
        return p

    def lancer_env(self, **kw):
        kw.setdefault("direct", True)                  # sans processus fils : l'horloge simulee reste valable
        return lancement.lancer(self.parametrage(), self.b, self.journal, maintenant=self.ts,
                                maintenant_dt=lambda: self.maintenant, dormir=self.pauses.append, **kw)

    def regle_base(self, ident="r1"):
        return self.b.regle(self.b.numero_regle(ident))

    def fichier(self, nom="a.csv", contenu=b"contenu"):
        return self.source(nom, contenu, age_sec=600)


class TestLancementSequentiel(CasLancement):
    def test_regle_nouvelle_demarre_au_creneau_suivant(self):
        self.brute()
        self.fichier()
        r = self.lancer_env()                                     # 06:00 : creneau de la veille considere pris
        self.assertEqual((r.compteurs["lancees"], r.code_retour), (0, 0))
        self.assertEqual(os.listdir(self.src), ["a.csv"])
        self.assertEqual(len(self.evenements("regle_nouvelle")), 1)
        self.heure(6, 59)
        self.assertEqual(self.lancer_env().compteurs["lancees"], 0)
        self.heure(7, 0)
        r = self.lancer_env()
        self.assertEqual((r.compteurs["lancees"], r.compteurs["SUCCES"], r.code_retour), (1, 1, 0))
        self.assertEqual(os.listdir(self.dst), ["a.csv"])
        self.assertEqual(os.listdir(self.src), [])
        self.heure(7, 5)
        self.assertEqual(self.lancer_env().compteurs["lancees"], 0)           # creneau deja pris
        self.fichier("b.csv")
        self.heure(7, 30)
        self.assertEqual(self.lancer_env().compteurs["lancees"], 0)           # toujours le meme creneau
        self.heure(7, 0, jours=1)
        self.assertEqual(self.lancer_env().compteurs["lancees"], 1)           # lendemain
        self.assertEqual(sorted(os.listdir(self.dst)), ["a.csv", "b.csv"])

    def test_le_creneau_pris_est_memorise_en_base(self):
        self.brute()
        self.lancer_env()
        self.heure(7, 3)
        self.lancer_env()
        etat = self.regle_base()
        self.assertEqual(etat["dernier_creneau"], int(self.jour.timestamp() + 7 * 3600))
        self.assertEqual(etat["dernier_statut"], "SUCCES")
        ex = self.b.derniere_execution(etat["no"])
        self.assertEqual(ex["declencheur"], "planifie")

    def test_plusieurs_regles_dans_l_ordre_et_filtre(self):
        self.brute(id="a", cible=self.chemin("da"))
        self.brute(id="b", cible=self.chemin("db"))
        self.brute(id="c", cible=self.chemin("dc"), actif=False)
        self.fichier()
        self.lancer_env()
        self.heure(7, 1)
        r = self.lancer_env(filtre=["b"])
        self.assertEqual((r.compteurs["regles"], r.compteurs["lancees"]), (1, 1))
        self.assertFalse(os.path.exists(self.chemin("da")))
        self.assertEqual(os.listdir(self.chemin("db")), ["a.csv"])
        r = self.lancer_env()                                     # a seule restante (b deja prise, c inactive)
        self.assertEqual((r.compteurs["lancees"], r.compteurs["non_dues"]), (1, 2))
        ordre = [self.b.c.execute("SELECT id FROM regles WHERE no = ?", (l["regle_no"],)).fetchone()[0]
                 for l in self.b.c.execute("SELECT regle_no FROM executions ORDER BY id").fetchall()]
        self.assertEqual(ordre, ["b", "a"])

    def test_code_retour_selon_le_pire_evenement(self):
        self.brute(id="bonne", cible=self.chemin("ok"))
        self.brute(id="mauvaise", source=self.chemin("absente"), cible=self.chemin("ko"))
        self.fichier()
        self.lancer_env()
        self.heure(7, 1)
        r = self.lancer_env()
        self.assertEqual((r.compteurs["SUCCES"], r.compteurs["ERREUR"], r.code_retour), (1, 1, 1))

    def test_regle_orpheline_et_regle_modifiee(self):
        self.brute()
        self.lancer_env()
        self.regles_brutes[0]["description"] = "modifiee"
        self.brute(id="autre", cible=self.chemin("d2"))
        r = self.lancer_env()
        self.assertEqual(len(self.evenements("regle_modifiee")), 1)
        self.regles_brutes.pop(0)
        r = self.lancer_env()
        self.assertEqual((r.compteurs["orphelines"], r.code_retour), (1, 4))
        self.assertEqual(self.evenements("regle_orpheline")[0]["regle"], "r1")

    def test_base_indisponible_arrete_le_lancement(self):
        self.brute()
        p = self.parametrage()
        self.b.fermer()
        r = lancement.lancer(p, self.b, self.journal, maintenant=self.ts)
        self.assertEqual(r.code_retour, 2)
        self.assertEqual(len(self.evenements("base_indisponible", "ERREUR")), 1)
        self.b = modele_base.ouvrir(self.chemin_base)
        self.addCleanup(self.b.fermer)

    def test_simulation_ignore_la_planification_et_n_ecrit_rien(self):
        self.brute()
        self.brute(id="inactive", actif=False, cible=self.chemin("d2"))
        self.fichier()
        self.lancer_env()                                        # 06:00 : pas dues
        avant = self.b.c.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
        with modele_base.ouvrir(self.chemin_base, "production", lecture_seule=True) as ro:
            r = lancement.lancer(self.parametrage(), ro, self.journal, simulation=True,
                                 maintenant=self.ts, maintenant_dt=lambda: self.maintenant)
        self.assertEqual((r.compteurs["lancees"], r.code_retour), (1, 0))
        self.assertEqual(os.listdir(self.src), ["a.csv"])
        self.assertEqual(self.b.c.execute("SELECT COUNT(*) FROM executions").fetchone()[0], avant)
        self.assertEqual(len(self.evenements("fichier_a_livrer")), 1)


class TestOrphelins(CasLancement):
    def processus_mort(self):
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()
        return p.pid

    def test_processus_disparu_libere_la_regle(self):
        self.brute()
        self.lancer_env()
        no = self.b.numero_regle("r1")
        self.b.demarrer_execution(no, "planifie", self.processus_mort(), pid_cree_le=1, hote=nom_hote())
        self.heure(6, 10)
        r = self.lancer_env()
        etat = self.regle_base()
        self.assertEqual((etat["en_cours"], etat["dernier_statut"], etat["arret_apres_erreur"]), (0, "ERREUR", 1))
        self.assertEqual(etat["derniere_erreur_situation"], "arret_anormal")
        self.assertEqual((r.compteurs["nettoyees"], r.code_retour), (1, 1))
        self.assertEqual(len(self.evenements("arret_anormal", "ERREUR")), 1)
        ex = self.b.derniere_execution(no)
        self.assertEqual(ex["statut"], "ARRETEE")

    def test_apres_erreur_continuer_ne_bloque_pas(self):
        self.brute(apres_erreur="continuer")
        self.lancer_env()
        no = self.b.numero_regle("r1")
        self.b.demarrer_execution(no, "planifie", self.processus_mort(), hote=nom_hote())
        self.lancer_env()
        self.assertEqual(self.regle_base()["arret_apres_erreur"], 0)

    def test_processus_vivant_non_touche(self):
        self.brute()
        self.lancer_env()
        no = self.b.numero_regle("r1")
        self.b.demarrer_execution(no, "planifie", os.getpid(), processus.date_creation(os.getpid()),
                                  hote=nom_hote())
        r = self.lancer_env()
        self.assertEqual((r.compteurs["nettoyees"], self.regle_base()["en_cours"]), (0, 1))

    def test_identifiant_reutilise_avec_autre_date_de_creation(self):
        self.brute()
        self.lancer_env()
        no = self.b.numero_regle("r1")
        self.b.demarrer_execution(no, "planifie", os.getpid(), pid_cree_le=12345, hote=nom_hote())
        self.assertEqual(self.lancer_env().compteurs["nettoyees"], 1)

    def test_autre_serveur_non_touche(self):
        self.brute()
        self.lancer_env()
        no = self.b.numero_regle("r1")
        self.b.demarrer_execution(no, "planifie", self.processus_mort(), hote="UN-AUTRE-SERVEUR")
        self.assertEqual(self.lancer_env().compteurs["nettoyees"], 0)
        self.assertEqual(self.regle_base()["en_cours"], 1)

    def test_processus_systeme(self):
        self.assertTrue(processus.vivant(os.getpid(), processus.date_creation(os.getpid())))
        self.assertFalse(processus.vivant(self.processus_mort(), None))
        self.assertFalse(processus.vivant(None, None))
        self.assertAlmostEqual(processus.date_creation(os.getpid()), __import__("time").time(), delta=86400)


class TestReprise(CasLancement):
    def preparer_erreur(self, **modif):
        """Regle qui s'arrete en ERREUR (source absente) au creneau de 07:00."""
        self.brute(source=self.chemin("pas_encore"), **modif)
        self.lancer_env()
        self.heure(7, 0)
        r = self.lancer_env()
        self.assertEqual(r.compteurs["ERREUR"], 1)
        return r

    def test_apres_erreur_arreter_plus_aucun_creneau_pris(self):
        self.preparer_erreur()
        etat = self.regle_base()
        self.assertEqual((etat["dernier_statut"], etat["arret_apres_erreur"]), ("ERREUR", 1))
        os.makedirs(self.chemin("pas_encore"))                    # le probleme est corrige...
        self.heure(7, 0, jours=1)
        r = self.lancer_env()                                     # ...mais il faut une reprise
        self.assertEqual(r.compteurs["lancees"], 0)
        self.assertEqual(self.regle_base()["dernier_statut"], "ERREUR")

    def test_reprise_relance_hors_creneau_et_remet_en_marche(self):
        self.preparer_erreur()
        os.makedirs(self.chemin("pas_encore"))
        ancien = self.ecrire("pas_encore/a.csv")
        os.utime(ancien, (self.ts() - 600, self.ts() - 600))
        self.b.poser_reprise("r1", "benoit", "source retablie")
        self.assertEqual(self.regle_base()["reprise"], 1)
        self.heure(7, 12)
        r = self.lancer_env()
        self.assertEqual((r.compteurs["lancees"], r.compteurs["SUCCES"]), (1, 1))
        etat = self.regle_base()
        self.assertEqual((etat["dernier_statut"], etat["reprise"], etat["arret_apres_erreur"]), ("SUCCES", 0, 0))
        self.assertEqual(self.b.derniere_execution(etat["no"])["declencheur"], "reprise")
        self.assertEqual(len(self.evenements("reprise_demarree")), 1)
        trace = self.b.c.execute("SELECT action, utilisateur, commentaire FROM journal_actions "
                                 "WHERE action = 'reprise'").fetchone()
        self.assertEqual((trace["utilisateur"], trace["commentaire"]), ("benoit", "source retablie"))
        self.heure(7, 20)
        self.assertEqual(self.lancer_env().compteurs["lancees"], 0)           # pas de seconde execution

    def test_reprise_en_echec_exige_une_nouvelle_reprise(self):
        self.preparer_erreur()
        self.b.poser_reprise("r1", "benoit")
        self.heure(7, 12)
        r = self.lancer_env()
        self.assertEqual(r.compteurs["ERREUR"], 1)                # source toujours absente
        etat = self.regle_base()
        self.assertEqual((etat["dernier_statut"], etat["reprise"], etat["arret_apres_erreur"]), ("ERREUR", 0, 1))
        self.assertEqual(self.lancer_env().compteurs["lancees"], 0)

    def test_lancer_maintenant(self):
        self.brute()
        self.fichier()
        self.lancer_env()
        self.b.poser_lancement_manuel("r1", "benoit")
        self.heure(6, 5)                                          # bien avant le creneau de 07:00
        r = self.lancer_env()
        self.assertEqual(r.compteurs["lancees"], 1)
        etat = self.regle_base()
        self.assertEqual((etat["lancement_manuel"], self.b.derniere_execution(etat["no"])["declencheur"]),
                         (0, "manuel"))
        self.assertEqual(os.listdir(self.dst), ["a.csv"])

    def test_reprise_refusee_si_en_cours_ou_inconnue(self):
        self.brute()
        self.lancer_env()
        no = self.b.numero_regle("r1")
        self.b.demarrer_execution(no, "planifie", 1)
        with self.assertRaises(modele_base.ActionRefusee):
            self.b.poser_reprise("r1", "benoit")
        with self.assertRaises(modele_base.ActionRefusee):
            self.b.poser_lancement_manuel("r1", "benoit")
        with self.assertRaises(modele_base.ActionRefusee):
            self.b.poser_reprise("fantome", "benoit")

    def test_reprise_apres_un_incertain_a_relivrer(self):
        self.brute(mode="copie")
        self.fichier()
        self.lancer_env()
        self.heure(7, 0)
        from unittest import mock
        from copie import transfert
        from tests.test_moteur import Plantage
        with mock.patch.object(transfert, "copier_verifier", side_effect=Plantage):
            with self.assertRaises(Plantage):
                self.lancer_env()
        self.heure(7, 10)
        self.b.poser_lancement_manuel("r1", "benoit")
        r = self.lancer_env()
        self.assertEqual(r.compteurs["ERREUR"], 1)
        (cle, _, _), = self.b.incertains(self.b.numero_regle("r1"))
        self.b.resoudre_incertain(cle, "a_relivrer", "benoit", "absent de la cible")
        self.b.poser_reprise("r1", "benoit", "decision prise")
        self.heure(7, 20)
        r = self.lancer_env()
        self.assertEqual((r.compteurs["SUCCES"], os.listdir(self.dst)), (1, ["a.csv"]))


class TestAcquittement(CasLancement):
    def en_erreur(self):
        self.brute(source=self.chemin("absente"))
        self.lancer_env()
        self.heure(7, 0)
        self.lancer_env()
        return self.regle_base()

    def test_acquittement(self):
        self.en_erreur()
        self.b.acquitter("r1", "benoit", "fichiers deplaces a la main")
        etat = self.regle_base()
        self.assertEqual((etat["dernier_statut"], etat["arret_apres_erreur"]), ("ACQUITTEE", 0))
        self.assertIn("fichiers deplaces a la main", etat["dernier_motif"])
        trace = self.b.c.execute("SELECT utilisateur, commentaire, resultat FROM journal_actions "
                                 "WHERE action = 'acquittement'").fetchone()
        self.assertEqual((trace["utilisateur"], trace["commentaire"], trace["resultat"]),
                         ("benoit", "fichiers deplaces a la main", "ok"))
        # la regle repart au creneau suivant, sans reprise
        os.makedirs(self.chemin("absente"))
        self.heure(7, 0, jours=1)
        self.assertEqual(self.lancer_env().compteurs["lancees"], 1)
        self.assertEqual(self.regle_base()["dernier_statut"], "SUCCES")

    def test_acquittement_ne_compte_pas_comme_une_livraison(self):
        self.en_erreur()
        self.b.acquitter("r1", "benoit", "ok")
        no = self.b.numero_regle("r1")
        self.assertEqual(self.b.c.execute("SELECT COUNT(*) FROM executions").fetchone()[0], 1)   # aucune execution ajoutee
        self.assertEqual(self.b.derniere_execution(no)["nb_livres"], 0)
        self.assertEqual(self.livres(), [])

    def test_commentaire_obligatoire(self):
        self.en_erreur()
        for vide in (None, "", "   "):
            with self.assertRaises(modele_base.ActionRefusee):
                self.b.acquitter("r1", "benoit", vide)
        self.assertEqual(self.regle_base()["dernier_statut"], "ERREUR")

    def test_seulement_une_regle_en_erreur(self):
        self.brute()
        self.lancer_env()
        with self.assertRaises(modele_base.ActionRefusee) as cm:
            self.b.acquitter("r1", "benoit", "x")                 # JAMAIS_LANCEE
        self.assertIn("JAMAIS_LANCEE", str(cm.exception))

    def test_refuse_tant_que_des_livraisons_sont_incertaines(self):
        self.brute(mode="copie")
        self.fichier()
        self.lancer_env()
        self.heure(7, 0)
        from unittest import mock
        from copie import transfert
        from tests.test_moteur import Plantage
        with mock.patch.object(transfert, "copier_verifier", side_effect=Plantage):
            with self.assertRaises(Plantage):
                self.lancer_env()
        self.b.poser_lancement_manuel("r1", "benoit")
        self.lancer_env()
        with self.assertRaises(modele_base.ActionRefusee) as cm:
            self.b.acquitter("r1", "benoit", "je pense que c'est livre")
        self.assertIn("resultat inconnu", str(cm.exception))

    def test_regle_en_cours(self):
        self.en_erreur()
        self.b.demarrer_execution(self.b.numero_regle("r1"), "reprise", 1)
        with self.assertRaises(modele_base.ActionRefusee):
            self.b.acquitter("r1", "benoit", "x")


class TestEtat(CasLancement):
    def etat(self, **kw):
        with modele_base.ouvrir(self.chemin_base, "production", lecture_seule=True) as ro:
            return lancement.etat(self.parametrage(), ro, maintenant=self.ts, **kw)

    def par_id(self, resultat):
        return {r["id"]: r for r in resultat["regles"]}

    def test_regle_jamais_vue_en_base(self):
        self.brute(planification={"type": "quotidien", "heure": "07:15"})
        e = self.etat()
        r = e["regles"][0]
        self.assertEqual((r["statut"], r["dernier_lancement"], r["en_cours"]), ("JAMAIS_LANCEE", None, False))
        self.assertEqual(r["prochain_creneau"], int(self.jour.timestamp() + 7 * 3600 + 15 * 60))
        self.assertEqual(r["planification"], "a 07:15, tous les jours")
        self.assertEqual((e["environnement"], e["genere_le"], e["orphelines"]), ("production", int(self.ts()), []))

    def test_statuts_et_details(self):
        self.brute(id="bonne", cible=self.chemin("d1"))
        self.brute(id="fautive", source=self.chemin("absente"), cible=self.chemin("d2"))
        self.brute(id="inactive", actif=False, cible=self.chemin("d3"))
        self.brute(id="occupee", cible=self.chemin("d4"))
        self.fichier()
        self.lancer_env()
        self.heure(7, 0)
        self.lancer_env()
        self.b.demarrer_execution(self.b.numero_regle("occupee"), "planifie", os.getpid())
        self.b.poser_reprise("fautive", "benoit")
        e = self.par_id(self.etat())
        self.assertEqual((e["bonne"]["statut"], e["fautive"]["statut"], e["inactive"]["statut"],
                          e["occupee"]["statut"]), ("SUCCES", "ERREUR", "INACTIVE", "EN_COURS"))
        self.assertEqual(e["bonne"]["derniere_execution"]["nb_livres"], 1)
        self.assertEqual(e["bonne"]["dernier_succes"], int(self.ts()))
        self.assertEqual(e["fautive"]["derniere_erreur"]["situation"], "source_inaccessible")
        self.assertTrue(e["fautive"]["reprise"] and e["fautive"]["arret_apres_erreur"])
        self.assertTrue(e["occupee"]["en_cours"])
        self.assertEqual(json.loads(json.dumps(self.etat()))["regles"][0]["id"], "bonne")   # serialisable

    def test_actions_incertains_et_archive_degradee(self):
        self.ecrire("bloc", b"x")
        self.brute(mode="archivage", archive=self.chemin("bloc"))
        self.fichier()
        self.lancer_env()
        self.heure(7, 0)
        self.lancer_env()
        r = self.etat()["regles"][0]
        self.assertEqual((r["statut"], r["archivage_degrade"], r["actions_en_attente"]), ("WARNING", True, 1))

    def test_regle_orpheline_et_filtre(self):
        self.brute(id="a", cible=self.chemin("d1"))
        self.brute(id="b", cible=self.chemin("d2"))
        self.lancer_env()
        self.regles_brutes.pop()
        e = self.etat()
        self.assertEqual(e["orphelines"], ["b"])
        e = self.etat(filtre=["a"])
        self.assertEqual(([r["id"] for r in e["regles"]], e["orphelines"]), (["a"], []))

    def test_etat_texte(self):
        self.brute(source=self.chemin("absente"))
        self.lancer_env()
        self.heure(7, 0)
        self.lancer_env()
        texte = lancement.etat_texte(self.etat())
        for attendu in ("r1", "ERREUR", "a 07:00, tous les jours", "source_inaccessible", "arretee apres erreur"):
            self.assertIn(attendu, texte)

    def test_etat_n_ecrit_rien(self):
        self.brute()
        self.lancer_env()
        avant = self.b.c.execute("PRAGMA data_version").fetchone()[0]
        self.etat()
        self.assertEqual(self.b.c.execute("PRAGMA data_version").fetchone()[0], avant)

    def test_etat_liste_les_livraisons_incertaines(self):
        self.brute(mode="copie")
        self.fichier()
        self.lancer_env()
        self.heure(7, 0)
        from unittest import mock
        from copie import transfert
        from tests.test_moteur import Plantage
        with mock.patch.object(transfert, "copier_verifier", side_effect=Plantage):
            with self.assertRaises(Plantage):
                self.lancer_env()
        self.heure(7, 10)
        self.b.poser_lancement_manuel("r1", "benoit")
        self.lancer_env()
        (cle, source, cible), = self.b.incertains(self.b.numero_regle("r1"))
        entree = self.etat()["regles"][0]
        self.assertEqual(entree["livraisons_incertaines"], 1)
        self.assertEqual(entree["incertains"], [{"cle": cle.hex(), "source": source, "cible": cible}])


class TestCommandes(CasLancement):
    """La ligne de commande, de bout en bout (horloge reelle)."""

    def setUp(self):
        super().setUp()
        self.conf = self.chemin("production.jsonl")
        self.maintenant = datetime.datetime.now()
        self.brute(planification={"type": "quotidien", "heure": "00:00"})
        self.parametrage()
        self.b.fermer()
        os.remove(self.chemin_base)
        for suffixe in ("-wal", "-shm"):
            if os.path.exists(self.chemin_base + suffixe):
                os.remove(self.chemin_base + suffixe)
        self.b = None
        self.addCleanup(lambda: None)

    def tearDown(self):
        super().tearDown()

    def commande(self, *args):
        sortie, erreur = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
            code = cli.main(["--config", self.conf] + list(args))
        return code, sortie.getvalue(), erreur.getvalue()

    def test_parcours_complet(self):
        self.assertEqual(self.commande("--initialiser-base")[0], 0)
        self.ecrire("src/a.csv", b"contenu")
        old = self.maintenant.timestamp() - 600
        os.utime(self.chemin("src", "a.csv"), (old, old))
        # une regle nouvelle ne part pas toute seule ; --lancer-maintenant la declenche
        code, sortie, _ = self.commande()
        self.assertEqual((code, os.listdir(self.src)), (0, ["a.csv"]))
        code, sortie, _ = self.commande("--lancer-maintenant", "r1", "--utilisateur", "benoit")
        self.assertEqual(code, 0)
        self.assertIn("sera lancee", sortie)
        code, sortie, _ = self.commande()
        self.assertEqual((code, os.listdir(self.src), os.listdir(self.dst)), (0, [], ["a.csv"]))
        # etat en JSON puis en texte
        code, sortie, _ = self.commande("--etat", "--format", "json")
        etat = json.loads(sortie)
        self.assertEqual((code, etat["regles"][0]["statut"], etat["regles"][0]["derniere_execution"]["nb_livres"]),
                         (0, "SUCCES", 1))
        code, sortie, _ = self.commande("--etat", "--regle", "R1")
        self.assertIn("SUCCES", sortie)

    def test_reprise_et_acquittement_en_ligne_de_commande(self):
        self.commande("--initialiser-base")
        self.commande("--lancer-maintenant", "r1", "--utilisateur", "benoit")       # source absente : ERREUR
        os.rmdir(self.src)
        self.assertEqual(self.commande()[0], 1)
        code, _, erreur = self.commande("--reprise", "r1", "--utilisateur", "benoit", "--commentaire", "retablie")
        self.assertEqual(code, 0)
        code, _, erreur = self.commande("--acquitter", "r1", "--utilisateur", "benoit")
        self.assertEqual(code, 2)                                  # r1 n'est plus en cours mais statut ERREUR : commentaire manquant
        self.assertIn("commentaire", erreur)
        code, sortie, _ = self.commande("--acquitter", "r1", "--utilisateur", "benoit", "--commentaire", "traite a la main")
        self.assertEqual(code, 0)
        code, sortie, _ = self.commande("--etat", "--format", "json")
        self.assertEqual(json.loads(sortie)["regles"][0]["statut"], "ACQUITTEE")

    def test_utilisateur_obligatoire(self):
        for option in ("--reprise", "--lancer-maintenant", "--acquitter"):
            with self.assertRaises(SystemExit):
                with contextlib.redirect_stderr(io.StringIO()):
                    cli.main(["--config", self.conf, option, "r1"])

    def test_regle_inconnue_refusee(self):
        self.commande("--initialiser-base")
        code, _, erreur = self.commande("--reprise", "fantome", "--utilisateur", "benoit")
        self.assertEqual(code, 2)
        self.assertIn("inconnue", erreur)

    def test_trancher_une_livraison_incertaine(self):
        self.commande("--initialiser-base")
        code, _, erreur = self.commande("--trancher-incertain", "zz", "--decision", "livre",
                                        "--utilisateur", "benoit", "--commentaire", "x")
        self.assertEqual(code, 2)
        self.assertIn("hexadecimal", erreur)
        code, _, erreur = self.commande("--trancher-incertain", "00ff", "--decision", "livre",
                                        "--utilisateur", "benoit", "--commentaire", "x")
        self.assertEqual(code, 2)                                  # aucune livraison incertaine avec cette cle

    def test_sans_base_aucun_lancement(self):
        code, _, erreur = self.commande()
        self.assertEqual(code, 2)
        self.assertIn("introuvable", erreur)
        self.assertEqual(self.commande("--etat")[0], 2)

    def test_simulation_de_lancement(self):
        self.commande("--initialiser-base")
        self.ecrire("src/a.csv")
        old = self.maintenant.timestamp() - 600
        os.utime(self.chemin("src", "a.csv"), (old, old))
        code, sortie, _ = self.commande("--simulation")
        self.assertEqual((code, os.listdir(self.src), os.path.exists(self.dst)), (0, ["a.csv"], False))
        self.assertIn("fichier_a_livrer", sortie)


if __name__ == "__main__":
    unittest.main()
