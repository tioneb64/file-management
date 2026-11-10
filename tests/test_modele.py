"""J10 etape B : commande --modele-regle (valeurs de secours et listes pour le formulaire du front-end)."""
import contextlib
import copy
import io
import json
import os
import unittest

from copie import __main__ as cli
from copie import modele, parametrage
from copie.controles import verifier_fichier
from tests.outils import CasTemporaire


class TestModeleRegle(CasTemporaire):
    def ecrire_parametrage(self, regle):
        entete = {"version": 1, "environnement": "production", "base": self.chemin("donnees", "production.db")}
        chemin = self.chemin("production.jsonl")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(json.dumps(entete) + "\n" + json.dumps(regle) + "\n")
        return chemin

    def regle_complete(self):
        regle = copy.deepcopy(modele.modele()["regle"])
        regle.update(id="r1", source=self.chemin("s"), cible=self.chemin("c"), mode="copie",
                     planification={"type": "quotidien", "heure": "07:00", "jours": "tous", "rattrapage_sec": None})
        return regle

    def test_la_regle_par_defaut_completee_est_acceptee_telle_quelle(self):
        """Ce que le front-end ecrit (reglage complet, valeurs nulles comprises) passe la validation."""
        _, rapport = verifier_fichier(self.ecrire_parametrage(self.regle_complete()))
        self.assertTrue(rapport.ok, rapport.en_texte())
        self.assertEqual(rapport.avertissements, [])

    def test_les_valeurs_de_secours_sont_celles_du_moteur(self):
        p, _ = verifier_fichier(self.ecrire_parametrage(self.regle_complete()))
        lue, defaut = p.regles[0], parametrage.Regle(0)
        for champ in ("retention_historique_jours", "duree_max_sec", "relances_max", "apres_erreur",
                      "si_duree_depassee", "si_cible_absente", "si_existe_cible", "si_existe_archive", "identite"):
            self.assertEqual(getattr(lue, champ), getattr(defaut, champ), champ)
        self.assertEqual(lue.selection.ordre, defaut.selection.ordre)
        for nom, situation in lue.situations.items():
            self.assertEqual(situation.tentatives, defaut.situations[nom].tentatives, nom)
            self.assertEqual(situation.suite, defaut.situations[nom].suite, nom)

    def test_chaque_champ_du_modele_est_connu_du_moteur(self):
        """Un champ du modele que le moteur refuserait (E06) casserait tout enregistrement."""
        regle = self.regle_complete()
        regle["champ_inconnu"] = 1
        _, rapport = verifier_fichier(self.ecrire_parametrage(regle))
        self.assertIn("E06", [d.code for d in rapport.refus])

    def test_les_listes_correspondent_aux_constantes_du_moteur(self):
        m = modele.modele()
        self.assertEqual(m["listes"]["modes"], list(parametrage.MODES))
        self.assertEqual(m["listes"]["points_programme"], list(parametrage.PROGRAMMES))
        self.assertEqual(set(m["situations"]), set(parametrage.SITUATIONS))
        self.assertEqual(m["situations"]["fichier_verrouille"]["suites"], ["fichier_suivant", "arreter_regle"])
        self.assertEqual(m["situations"]["aucun_fichier"]["suites"], [])
        self.assertIsNone(m["situations"]["aucun_fichier"]["suite_defaut"])
        self.assertEqual(m["version_format"], parametrage.VERSION_FORMAT)

    def test_la_regle_par_defaut_n_a_pas_de_suite_pour_les_situations_sans_suite(self):
        situations = modele.regle_par_defaut()["situations"]
        self.assertNotIn("suite", situations["aucun_fichier"])
        self.assertEqual(situations["fichier_verrouille"]["suite"], "arreter_regle")

    def test_commande_json_sans_config(self):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = cli._main(["--modele-regle", "--format", "json"])
        reponse = json.loads(sortie.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual((reponse["version_contrat"], reponse["ok"], reponse["commande"]), (1, True, "modele_regle"))
        self.assertEqual(set(reponse), {"version_contrat", "ok", "code_retour", "message", "commande",
                                        "version_format", "regle", "listes", "situations"})

    def test_commande_texte(self):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = cli._main(["--modele-regle"])
        self.assertEqual(code, 0)
        self.assertIn("situations", json.loads(sortie.getvalue()))

    def test_les_parametres_du_modele_ne_dependent_d_aucun_fichier(self):
        self.assertFalse(os.path.exists("production.jsonl"))
        self.assertEqual(modele.modele(), modele.modele())


if __name__ == "__main__":
    unittest.main()
