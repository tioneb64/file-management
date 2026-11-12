"""Mode synchro : aucune source ni cible, apres des dependances ; lance avant_lot puis avant_fichier
(s'ils existent) et rend seulement un statut (SUCCES ou ERREUR)."""
import copy
import datetime
import json
import os
import unittest

from file_management import dependances
from file_management import base as modele_base
from file_management.diagnostic import Rapport
from file_management.parametrage import lire_regle
from tests.test_programmes import CasProgramme


def _brut(**modif):
    brut = {"id": "sync", "mode": "synchro", "apres": ["amont"],
            "planification": {"type": "apres_dependances"}}
    brut.update(modif)
    return brut


def _lire(**modif):
    rapport = Rapport()
    return lire_regle(copy.deepcopy(_brut(**modif)), 3, rapport), rapport


def _codes(rapport):
    return sorted({d.code for d in rapport.refus + rapport.avertissements})


PROG = {"commande": ["python", "-c", "pass"], "timeout_sec": 5}


class TestSynchroParametrage(unittest.TestCase):
    def test_regle_minimale_sans_dossier_est_valide(self):
        r, rapport = _lire()
        self.assertEqual(_codes(rapport), [])
        self.assertEqual((r.mode, r.source, r.cible), ("synchro", None, None))

    def test_un_dossier_est_refuse(self):
        for champ in ("source", "cible", "archive", "dossier_temporaire"):
            with self.subTest(champ=champ):
                _, rapport = _lire(**{champ: "D:\\x"})
                self.assertEqual([d.code for d in rapport.refus], ["R17"], rapport.en_texte())
                self.assertIn(champ, rapport.refus[0].message)

    def test_source_vide_ou_nulle_est_acceptee(self):
        _, rapport = _lire(source=None, cible="")
        self.assertEqual(_codes(rapport), [])

    def test_heure_de_debut_et_de_fin_refusees(self):
        for planification in ({"type": "quotidien", "heure": "07:00"},
                              {"type": "intervalle", "debut": "01:00", "fin": "05:00", "frequence_sec": 60}):
            with self.subTest(type=planification["type"]):
                _, rapport = _lire(planification=planification)
                self.assertEqual([d.code for d in rapport.refus], ["P01"], rapport.en_texte())

    def test_planification_obligatoire(self):
        brut = _brut()
        del brut["planification"]
        rapport = Rapport()
        lire_regle(brut, 3, rapport)
        self.assertEqual([d.code for d in rapport.refus], ["R01"])

    def test_programmes_apres_avertissent_qu_ils_ne_seront_pas_executes(self):
        _, rapport = _lire(programmes={"avant_lot": PROG, "apres_fichier": PROG, "apres_lot": PROG})
        self.assertEqual(rapport.refus, [])
        self.assertEqual([d.code for d in rapport.avertissements], ["R18", "R18"])
        self.assertIn("apres_fichier", rapport.avertissements[0].message)
        self.assertIn("apres_lot", rapport.avertissements[1].message)

    def test_avant_lot_et_avant_fichier_sans_avertissement(self):
        _, rapport = _lire(programmes={"avant_lot": PROG, "avant_fichier": PROG})
        self.assertEqual(_codes(rapport), [])

    def test_variables_de_fichier_ou_de_dossier_refusees(self):
        for variable in ("{liste}", "{fichier}", "{source}", "{cible}", "{archive}"):
            with self.subTest(variable=variable):
                prog = {"commande": ["x", variable], "timeout_sec": 5}
                _, rapport = _lire(programmes={"avant_lot": prog, "avant_fichier": prog})
                self.assertEqual({d.code for d in rapport.refus}, {"G01"})
        _, rapport = _lire(programmes={"avant_lot": {"commande": ["x", "{regle}", "{date}", "{environnement}"],
                                                     "timeout_sec": 5}})
        self.assertEqual(_codes(rapport), [])

    def test_champs_de_fichiers_ignores_avec_un_avertissement(self):
        _, rapport = _lire(selection={"masque": "*.txt"}, horodater=True, seuil_minimum=1)
        self.assertEqual(rapport.refus, [])
        self.assertEqual([d.code for d in rapport.avertissements], ["R16"])
        for champ in ("selection", "horodater", "seuil_minimum"):
            self.assertIn(champ, rapport.avertissements[0].message)

    def test_valeurs_par_defaut_explicites_sans_avertissement(self):
        """Le formulaire de l'interface envoie tous les champs : seules les valeurs non par defaut comptent."""
        _, rapport = _lire(creer_dossiers=True, horodater=False, seuil_minimum=None, identite="version",
                           retention_historique_jours=90, si_cible_absente="ignorer", si_existe_cible="erreur",
                           renommage_cible=None, selection={"masque": "*", "recursif": False, "ordre": "nom"})
        self.assertEqual(_codes(rapport), [])
        _, rapport = _lire(identite="contenu", selection={"recursif": True})
        self.assertEqual([d.code for d in rapport.avertissements], ["R16"])
        self.assertIn("identite", rapport.avertissements[0].message)
        self.assertIn("selection", rapport.avertissements[0].message)

    def test_sans_liste_apres_la_regle_est_refusee(self):
        from file_management.controles import verifier_fichier
        import tempfile
        dossier = tempfile.mkdtemp(prefix="copie_synchro_")
        self.addCleanup(__import__("shutil").rmtree, dossier, True)
        chemin = os.path.join(dossier, "test.jsonl")
        entete = {"version": 1, "environnement": "test", "base": os.path.join(dossier, "b", "test.db")}
        with open(chemin, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in (entete, _brut(apres=[]))) + "\n")
        _, rapport = verifier_fichier(chemin)
        self.assertEqual([d.code for d in rapport.refus], ["D06"], rapport.en_texte())


class TestSynchroExecution(CasProgramme):
    def synchro(self, **modif):
        brut = _brut(**modif)
        rapport = Rapport()
        r = lire_regle(copy.deepcopy(brut), 1, rapport)
        self.assertEqual(rapport.refus, [], rapport.en_texte())
        r.brut = json.dumps(brut)
        self.b.synchroniser_regles([(r.id, "e")])
        return r

    def points(self):
        return [a["env"]["COPIE_POINT_APPEL"] for a in self.lus()]

    def test_sans_programme_la_regle_reussit_sans_rien_toucher(self):
        self.source("a.csv")
        bilan = self.lancer(self.synchro())
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 0))
        self.assertIn("aucun programme", bilan.motif)
        self.assertEqual(self.lus(), [])
        self.assertEqual(os.listdir(self.src), ["a.csv"])
        self.assertFalse(os.path.exists(self.dst))

    def test_avant_lot_seul(self):
        bilan = self.lancer(self.synchro(programmes={"avant_lot": self.programme()}))
        self.assertEqual(bilan.statut, "SUCCES")
        self.assertEqual(self.points(), ["avant_lot"])
        self.assertIn("1 programme", bilan.motif)

    def test_avant_fichier_seul(self):
        bilan = self.lancer(self.synchro(programmes={"avant_fichier": self.programme()}))
        self.assertEqual(bilan.statut, "SUCCES")
        self.assertEqual(self.points(), ["avant_fichier"])

    def test_les_deux_dans_l_ordre_avant_lot_puis_avant_fichier(self):
        # declares dans l'ordre inverse : l'ordre d'execution ne depend pas du fichier
        r = self.synchro(programmes={"avant_fichier": self.programme(), "avant_lot": self.programme()})
        bilan = self.lancer(r)
        self.assertEqual(bilan.statut, "SUCCES")
        self.assertEqual(self.points(), ["avant_lot", "avant_fichier"])
        self.assertIn("2 programme", bilan.motif)

    def test_aucun_dossier_ni_fichier_dans_l_environnement_du_programme(self):
        self.lancer(self.synchro(programmes={"avant_lot": self.programme(arguments=["{regle}"])}))
        (appel,) = self.lus()
        env = appel["env"]
        self.assertEqual((env["COPIE_MODE"], env["COPIE_REGLE"]), ("synchro", "sync"))
        for nom in ("COPIE_SOURCE", "COPIE_CIBLE", "COPIE_ARCHIVE", "COPIE_FICHIER", "COPIE_LISTE"):
            self.assertEqual(env[nom], "", nom)
        self.assertEqual(appel["argv"], ["sync"])

    def test_code_1_est_une_erreur_en_synchro(self):
        """Ailleurs, le code 1 d'avant_lot veut dire « rien a faire » ; ici la regle ne peut dire que oui ou non."""
        bilan = self.lancer(self.synchro(programmes={"avant_lot": self.programme(code=1)}))
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "programme_avant_lot"))
        self.assertIn("code retour 1 (attendu : 0)", bilan.motif)

    def test_echec_d_avant_lot_n_appelle_pas_avant_fichier(self):
        r = self.synchro(programmes={"avant_lot": self.programme(code=2), "avant_fichier": self.programme()})
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "programme_avant_lot"))
        self.assertEqual(self.points(), ["avant_lot"])

    def test_echec_d_avant_fichier_apres_un_avant_lot_reussi(self):
        r = self.synchro(programmes={"avant_lot": self.programme(), "avant_fichier": self.programme(code=3)})
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "programme_avant_fichier"))
        self.assertEqual(self.points(), ["avant_lot", "avant_fichier"])

    def test_duree_depassee_et_lancement_impossible_sont_des_erreurs(self):
        lent = self.programme(avant="time.sleep(60)", timeout_sec=1)
        bilan = self.lancer(self.synchro(programmes={"avant_lot": lent}))
        self.assertEqual(bilan.statut, "ERREUR")
        self.assertIn("duree maximale depassee", bilan.motif)
        inconnu = {"commande": [self.chemin("introuvable.exe")], "timeout_sec": 5}
        bilan = self.lancer(self.synchro(programmes={"avant_fichier": inconnu}))
        self.assertEqual(bilan.statut, "ERREUR")
        self.assertIn("lancement impossible", bilan.motif)

    def test_les_points_apres_ne_sont_jamais_executes(self):
        r = self.synchro(programmes={"avant_lot": self.programme(), "apres_fichier": self.programme(),
                                     "apres_lot": self.programme()})
        bilan = self.lancer(r)
        self.assertEqual(bilan.statut, "SUCCES")
        self.assertEqual(self.points(), ["avant_lot"])

    def test_sur_erreur_est_appele_quand_la_synchro_echoue(self):
        r = self.synchro(programmes={"avant_lot": self.programme(code=2), "sur_erreur": self.programme()})
        bilan = self.lancer(r)
        self.assertEqual(bilan.statut, "ERREUR")
        self.assertEqual(self.points(), ["avant_lot", "sur_erreur"])

    def test_simulation_n_appelle_aucun_programme(self):
        r = self.synchro(programmes={"avant_lot": self.programme(), "avant_fichier": self.programme()})
        with modele_base.ouvrir(self.chemin_base, "production", lecture_seule=True) as ro:
            bilan = self.lancer(r, simulation=True, base=ro)
        self.assertEqual(bilan.statut, "SUCCES")
        self.assertEqual(self.lus(), [])

    def test_un_enfant_attend_une_synchro_en_succes(self):
        sync = self.synchro(apres=[])
        aval = self.regle(id="aval", apres=["sync"], condition=["succes"],
                          planification={"type": "apres_dependances"})
        self.lancer(sync)
        lignes = {l["id"].lower(): dict(l) for l in self.b.toutes_les_regles()}
        self.assertEqual(dependances.evaluer(aval, lignes.get("aval"), lignes, self.b).etat, dependances.PRETE)

    def test_un_enfant_n_est_pas_pret_si_la_synchro_echoue(self):
        sync = self.synchro(apres=[], programmes={"avant_lot": self.programme(code=2)})
        aval = self.regle(id="aval", apres=["sync"], condition=["succes"],
                          planification={"type": "apres_dependances"})
        self.assertEqual(self.lancer(sync).statut, "ERREUR")
        lignes = {l["id"].lower(): dict(l) for l in self.b.toutes_les_regles()}
        self.assertNotEqual(dependances.evaluer(aval, lignes.get("aval"), lignes, self.b).etat, dependances.PRETE)


if __name__ == "__main__":
    unittest.main()
