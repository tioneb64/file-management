"""Chemins racine (environnement, sources, cibles) et modes suppression, count, size."""
import json
import os
import unittest

from file_management import dependances, execution
from file_management.diagnostic import Rapport
from file_management.parametrage import charger, est_absolu, lire_regle, resoudre_chemin
from tests.outils import CasTemporaire
from tests.test_moteur import CasMoteur


def _codes(rapport):
    return sorted({d.code for d in rapport.refus + rapport.avertissements})


class TestResolutionDesChemins(unittest.TestCase):
    def test_chemin_complet_conserve(self):
        for chemin in ("D:\\LOGS", "d:/logs", "\\\\serveur\\partage\\x"):
            self.assertEqual(resoudre_chemin(chemin, "E:\\racine"), chemin)

    def test_chemin_partiel_place_sous_la_racine_avec_ou_sans_separateur_final(self):
        self.assertEqual(resoudre_chemin("LOGS", "D:\\r\\preprod\\"), os.path.normpath("D:\\r\\preprod\\LOGS"))
        self.assertEqual(resoudre_chemin("LOGS", "D:\\r\\preprod"), os.path.normpath("D:\\r\\preprod\\LOGS"))
        self.assertEqual(resoudre_chemin("BDD\\p.db", "D:\\r\\"), os.path.normpath("D:\\r\\BDD\\p.db"))
        self.assertEqual(resoudre_chemin("\\LOGS", "D:\\r"), os.path.normpath("D:\\r\\LOGS"))

    def test_sans_racine_le_chemin_est_inchange(self):
        self.assertEqual(resoudre_chemin("LOGS", None), "LOGS")
        self.assertEqual(resoudre_chemin("LOGS", "  "), "LOGS")

    def test_est_absolu(self):
        self.assertTrue(est_absolu("C:\\x"))
        self.assertTrue(est_absolu("\\\\srv\\x"))
        self.assertFalse(est_absolu("LOGS\\x"))
        self.assertFalse(est_absolu("D\\programmation"))      # le deux-points oublie reste un chemin partiel


class TestRacinesDeLEnvironnement(CasTemporaire):
    def charger(self, entete, regles=()):
        chemin = self.chemin("preprod.jsonl")
        base = {"version": 1, "environnement": "preprod", "base": "BDD\\preprod.db"}
        base.update(entete)
        lignes = [json.dumps(base)] + [json.dumps(r) for r in regles]
        with open(chemin, "w", encoding="utf-8") as f:
            f.write("\n".join(lignes) + "\n")
        return charger(chemin)

    def regle(self, **modif):
        r = {"id": "r1", "source": "IN", "cible": "OUT", "mode": "copie",
             "planification": {"type": "quotidien", "heure": "07:00"}}
        r.update(modif)
        return r

    def test_chemins_partiels_de_l_en_tete(self):
        racine = self.chemin("preprod") + os.sep               # separateur final autorise
        p, rapport = self.charger({"racine": racine, "dossier_logs": "LOGS", "dossier_travail": "TMP"})
        self.assertEqual(rapport.refus, [], rapport.en_texte())
        e = p.entete
        self.assertEqual(e.base, os.path.join(self.chemin("preprod"), "BDD", "preprod.db"))
        self.assertEqual(e.dossier_logs, os.path.join(self.chemin("preprod"), "LOGS"))
        self.assertEqual(e.dossier_travail, os.path.join(self.chemin("preprod"), "TMP"))

    def test_chemin_complet_conserve_dans_l_en_tete(self):
        racine = self.chemin("preprod")
        autre = self.chemin("ailleurs", "LOGS")
        p, rapport = self.charger({"racine": racine, "dossier_logs": autre})
        self.assertEqual(rapport.refus, [], rapport.en_texte())
        self.assertEqual(p.entete.dossier_logs, autre)

    def test_valeurs_par_defaut_des_journaux_et_du_travail_a_cote_de_la_base(self):
        p, rapport = self.charger({"racine": self.chemin("preprod")})
        dossier_base = os.path.join(self.chemin("preprod"), "BDD")
        self.assertEqual((p.entete.dossier_logs, p.entete.dossier_travail),
                         (os.path.join(dossier_base, "logs"), os.path.join(dossier_base, "travail")))

    def test_base_relative_sans_racine_est_refusee_E07(self):
        p, rapport = self.charger({})
        self.assertIn("E07", [d.code for d in rapport.refus])

    def test_racine_non_absolue_refusee_E07(self):
        p, rapport = self.charger({"racine": "preprod"})
        self.assertIn("E07", [d.code for d in rapport.refus])

    def test_racines_des_sources_et_des_cibles(self):
        racine = self.chemin("preprod")
        p, rapport = self.charger(
            {"racine": racine, "racine_source": "SRC\\", "racine_cible": self.chemin("dest")},
            [self.regle(), self.regle(id="r2", source=self.chemin("libre", "in"), cible="OUT2")])
        self.assertEqual(rapport.refus, [], rapport.en_texte())
        r1, r2 = p.regles
        self.assertEqual(r1.source, os.path.join(racine, "SRC", "IN"))
        self.assertEqual(r1.cible, os.path.join(self.chemin("dest"), "OUT"))
        self.assertEqual(r2.source, self.chemin("libre", "in"))             # chemin complet : conserve
        self.assertEqual(r2.cible, os.path.join(self.chemin("dest"), "OUT2"))

    def test_sans_racine_des_sources_c_est_la_racine_de_l_environnement(self):
        racine = self.chemin("preprod")
        p, rapport = self.charger({"racine": racine}, [self.regle()])
        self.assertEqual(rapport.refus, [], rapport.en_texte())
        self.assertEqual((p.regles[0].source, p.regles[0].cible),
                         (os.path.join(racine, "IN"), os.path.join(racine, "OUT")))

    def test_chemin_de_regle_partiel_sans_racine_refuse_R14(self):
        p, rapport = self.charger({"base": self.chemin("b", "preprod.db")}, [self.regle()])
        self.assertIn("R14", [d.code for d in rapport.refus])

    def test_la_regle_archive_reste_relative_a_la_source(self):
        racine = self.chemin("preprod")
        p, rapport = self.charger({"racine": racine}, [self.regle(mode="archivage", archive="archive")])
        self.assertEqual(p.regles[0].archive, "archive")


class TestModesSansTransfert(CasMoteur):
    def test_suppression_supprime_les_fichiers_anciens_et_garde_les_recents(self):
        vieux = self.source("vieux.log", age_sec=40 * 86400)
        recent = self.source("recent.log", age_sec=60)
        r = self.regle(mode="suppression", cible=None, selection={"age_minimum_sec": 30 * 86400})
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 1))
        self.assertFalse(os.path.exists(vieux))
        self.assertTrue(os.path.exists(recent))
        self.assertEqual(bilan.motif, "1 fichier(s) supprime(s)")

    def test_suppression_en_simulation_ne_supprime_rien(self):
        fichier = self.source("a.log", age_sec=40 * 86400)
        r = self.regle(mode="suppression", cible=None, selection={"age_minimum_sec": 86400})
        bilan = self.lancer(r, simulation=True)
        self.assertTrue(os.path.exists(fichier))
        self.assertEqual((bilan.compteurs["livres"], bilan.apercu_total), (1, 1))

    def test_suppression_respecte_la_limite_de_fichiers(self):
        for n in range(4):
            self.source("f%d.log" % n)
        r = self.regle(mode="suppression", cible=None, selection={"limite_fichiers": 3})
        self.assertEqual(self.lancer(r).compteurs["livres"], 3)
        self.assertEqual(len(os.listdir(self.src)), 1)

    def test_suppression_sans_fichier_rien_a_supprimer(self):
        r = self.regle(mode="suppression", cible=None)
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.motif), ("SUCCES", "rien a supprimer"))

    def test_count_dans_les_bornes_reussit_et_ne_touche_aucun_fichier(self):
        for n in range(5):
            self.source("f%d.csv" % n)
        r = self.regle(mode="count", cible=None, seuil_minimum=5)
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.attente, bilan.compteurs["selectionnes"]), ("SUCCES", False, 5))
        self.assertEqual(len(os.listdir(self.src)), 5)
        self.assertEqual(self.b.regle(self.no(r))["dernier_statut"], "SUCCES")

    def test_count_insuffisant_sort_en_attente_sans_erreur(self):
        for n in range(4):
            self.source("f%d.csv" % n)
        r = self.regle(mode="count", cible=None, seuil_minimum=5)
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.attente, bilan.statut_final), ("SUCCES", True, "ATTENTE"))
        ligne = self.b.regle(self.no(r))
        self.assertEqual(ligne["dernier_statut"], "ATTENTE")
        self.assertIn("4 fichier(s)", ligne["dernier_motif"])
        self.assertIn("au moins 5", ligne["dernier_motif"])
        self.assertIsNone(ligne["dernier_succes"])

    def test_count_au_dessus_du_maximum_sort_en_attente(self):
        for n in range(3):
            self.source("f%d.csv" % n)
        r = self.regle(mode="count", cible=None, seuil_maximum=2)
        self.assertTrue(self.lancer(r).attente)

    def test_count_sans_seuil_ne_fait_que_mesurer(self):
        self.source("a.csv")
        r = self.regle(mode="count", cible=None)
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.attente), ("SUCCES", False))
        self.assertTrue(self.evenements("mesure"))

    def test_size_compare_le_volume_total(self):
        self.source("a.bin", contenu=b"x" * 1500)
        self.source("b.bin", contenu=b"x" * 1500)
        assez = self.regle(mode="size", cible=None, seuil_minimum=3000)
        self.assertFalse(self.lancer(assez).attente)
        trop = self.regle(id="r2", mode="size", cible=None, seuil_maximum=2999)
        bilan = self.lancer(trop)
        self.assertTrue(bilan.attente)
        self.assertIn("Ko", bilan.motif)

    def test_source_absente_en_mode_count_est_une_erreur(self):
        os.rmdir(self.src)
        r = self.regle(mode="count", cible=None, seuil_minimum=1)
        bilan = self.lancer(r, dormir=lambda s: None)
        self.assertEqual(bilan.statut, "ERREUR")

    def test_une_regle_dependante_attend_le_count_puis_part(self):
        for n in range(4):
            self.source("f%d.csv" % n)
        comptage = self.regle(id="comptage", mode="count", cible=None, seuil_minimum=5)
        envoi = self.regle(id="envoi", apres=["comptage"], condition=["succes"],
                           planification={"type": "apres_dependances"})
        self.lancer(comptage)                                  # 4 fichiers sur 5 : ATTENTE
        lignes = {l["id"].lower(): dict(l) for l in self.b.toutes_les_regles()}
        evaluation = dependances.evaluer(envoi, lignes.get("envoi"), lignes, self.b)
        self.assertEqual(evaluation.etat, dependances.EN_ATTENTE)
        self.assertIn("au moins 5", evaluation.motif)

        self.source("f4.csv")                                  # le cinquieme arrive
        self.maintenant = self.maintenant + __import__("datetime").timedelta(seconds=5)
        self.lancer(comptage)
        lignes = {l["id"].lower(): dict(l) for l in self.b.toutes_les_regles()}
        evaluation = dependances.evaluer(envoi, lignes.get("envoi"), lignes, self.b)
        self.assertEqual(evaluation.etat, dependances.PRETE)


class TestDiagnosticsDesNouveauxModes(unittest.TestCase):
    def lire(self, **modif):
        r = {"id": "r1", "source": "D:\\in", "cible": "D:\\out", "mode": "copie",
             "planification": {"type": "quotidien", "heure": "07:00"}}
        r.update(modif)
        rapport = Rapport()
        return lire_regle(r, 1, rapport), rapport

    def test_suppression_avertit_toujours_R15(self):
        _, rapport = self.lire(mode="suppression", cible=None, selection={"age_minimum_sec": 3600})
        self.assertEqual(rapport.refus, [])
        self.assertEqual(_codes(rapport), ["R15"])

    def test_suppression_sans_critere_d_age_le_dit(self):
        _, rapport = self.lire(mode="suppression", cible=None)
        message = [d.message for d in rapport.avertissements if d.code == "R15"][0]
        self.assertIn("tous les fichiers du masque", message)

    def test_cible_obligatoire_seulement_pour_les_modes_de_transfert(self):
        _, rapport = self.lire(cible=None)
        self.assertIn("E06", [d.code for d in rapport.refus])
        r, rapport = self.lire(mode="count", cible=None, seuil_minimum=1)
        self.assertEqual((rapport.refus, rapport.avertissements), ([], []))
        self.assertIsNone(r.cible)

    def test_cible_ignoree_hors_transfert_R16(self):
        _, rapport = self.lire(mode="count")
        self.assertEqual(_codes(rapport), ["R16"])

    def test_seuils_ignores_hors_count_et_size_R16(self):
        _, rapport = self.lire(seuil_minimum=3)
        self.assertEqual(_codes(rapport), ["R16"])

    def test_seuil_minimum_superieur_au_maximum_refuse(self):
        _, rapport = self.lire(mode="count", cible=None, seuil_minimum=5, seuil_maximum=2)
        self.assertIn("R07", [d.code for d in rapport.refus])


if __name__ == "__main__":
    unittest.main()
