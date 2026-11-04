"""J12 : purge des journaux et des archives, purge de la base a chaque lancement, commande --purger."""
import contextlib
import datetime
import io
import json
import os
import stat
import unittest

from copie import __main__ as cli
from copie import base, lancement, purge
from copie.controles import verifier_fichier
from tests.outils import CasTemporaire

AUJOURDHUI = datetime.date(2026, 6, 15)
MODELE = ".\\archive\\{AAAA}-{MM}-{JJ}"


def jour(age):
    return (AUJOURDHUI - datetime.timedelta(days=age)).isoformat()


class Enregistreur(object):
    def __init__(self):
        self.evenements = []

    def evenement(self, nom, niveau, **champs):
        self.evenements.append((nom, niveau, champs))

    def noms(self):
        return [e[0] for e in self.evenements]


class CasPurge(CasTemporaire):
    def setUp(self):
        super().setUp()
        self.src, self.dst = self.chemin("src"), self.chemin("dst")
        self.logs = self.chemin("donnees", "logs")
        self.chemin_base = self.chemin("donnees", "production.db")
        os.makedirs(self.src)
        os.makedirs(self.dst)
        os.makedirs(self.logs)
        self.entete_extra = {}
        self.regles = []

    def regle(self, **modif):
        r = {"id": "r1", "source": self.src, "cible": self.dst, "mode": "archivage", "archive": MODELE,
             "planification": {"type": "quotidien", "heure": "07:00"}}
        r.update(modif)
        self.regles.append(r)
        return r

    def fichier_param(self):
        entete = {"version": 1, "environnement": "production", "base": self.chemin_base,
                  "dossier_logs": self.logs, "dossier_travail": self.chemin("donnees", "travail")}
        entete.update(self.entete_extra)
        chemin = self.chemin("production.jsonl")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in [entete] + self.regles) + "\n")
        return chemin

    def parametrage(self):
        p, rapport = verifier_fichier(self.fichier_param())
        self.assertTrue(rapport.ok, rapport.en_texte())
        return p

    def base(self):
        base.initialiser(self.chemin_base, "production", "u")
        return base.ouvrir(self.chemin_base, "production")

    def journal(self, nom, age):
        chemin = os.path.join(self.logs, "%s_%s.jsonl" % (nom, jour(age)))
        with open(chemin, "w") as f:
            f.write('{"x": 1}\n')
        return chemin

    def archive(self, age, contenu=b"abc", racine=None, nom=None):
        dossier = os.path.join(racine or os.path.join(self.src, "archive"), nom or jour(age))
        os.makedirs(dossier)
        chemin = os.path.join(dossier, "f.txt")
        with open(chemin, "wb") as f:
            f.write(contenu)
        return dossier

    def planifier(self, filtre=None, avec_base=False):
        p = self.parametrage()
        if avec_base:
            with self.base() as b:
                return purge.planifier(p, b, AUJOURDHUI, filtre)
        return purge.planifier(p, None, AUJOURDHUI, filtre)


class TestJournaux(CasPurge):
    def test_rien_sans_retention(self):
        self.regle()
        self.journal("r1", 4000)
        self.assertEqual(self.planifier().elements, [])

    def test_retention_de_l_entete_et_de_la_regle(self):
        self.entete_extra = {"retention_journaux_jours": 30}
        self.regle()
        self.regle(id="r2", retention_journaux_jours=5)
        vieux, recent = self.journal("r1", 31), self.journal("r1", 29)
        deux = self.journal("r2", 6)
        orch = self.journal("_orchestrateur", 90)
        plan = self.planifier()
        self.assertEqual({e.chemin for e in plan.elements}, {vieux, deux, orch})
        self.assertNotIn(recent, [e.chemin for e in plan.elements])

    def test_la_limite_exacte_est_conservee(self):
        self.entete_extra = {"retention_journaux_jours": 30}
        self.regle()
        self.journal("r1", 30)
        self.assertEqual(self.planifier().elements, [])

    def test_journal_d_une_regle_inconnue_ou_technique_conserve(self):
        self.entete_extra = {"retention_journaux_jours": 1}
        self.regle()
        inconnue = self.journal("ancienne_regle", 500)
        self.journal("journal_si_secours", 500)
        with open(os.path.join(self.logs, "notes.txt"), "w") as f:
            f.write("a")
        plan = self.planifier()
        self.assertEqual(plan.elements, [])
        self.assertEqual([i["chemin"] for i in plan.ignores], [inconnue])

    def test_filtre_par_regle_exclut_l_orchestrateur(self):
        self.entete_extra = {"retention_journaux_jours": 1}
        self.regle()
        self.regle(id="r2")
        a, b, c = self.journal("r1", 9), self.journal("r2", 9), self.journal("_orchestrateur", 9)
        plan = self.planifier(filtre=["R1"])
        self.assertEqual([e.chemin for e in plan.elements], [a])

    def test_le_plan_ne_supprime_rien_et_appliquer_supprime(self):
        self.entete_extra = {"retention_journaux_jours": 10}
        self.regle()
        vieux = self.journal("r1", 50)
        os.chmod(vieux, stat.S_IREAD)
        plan = self.planifier()
        self.assertTrue(os.path.exists(vieux))
        journal = Enregistreur()
        resultat = purge.appliquer(plan, journal)
        self.assertFalse(os.path.exists(vieux))
        self.assertEqual((resultat["journaux"], resultat["archives"], resultat["erreurs"]), (1, 0, []))
        self.assertEqual(journal.noms(), ["purge_supprime"])


class TestControleR13(CasPurge):
    def codes(self):
        _, rapport = verifier_fichier(self.fichier_param())
        return [d.code for d in rapport.diagnostics]

    def test_refuse_hors_archivage(self):
        self.regle(mode="copie", archive=None, retention_archive_jours=30)
        self.assertIn("R13", self.codes())

    def test_refuse_archive_sans_date(self):
        self.regle(archive=".\\archive", retention_archive_jours=30)
        self.assertIn("R13", self.codes())

    def test_accepte_archive_datee(self):
        self.regle(retention_archive_jours=30)
        self.assertNotIn("R13", self.codes())

    def test_valeur_invalide(self):
        self.regle(retention_archive_jours=0)
        _, rapport = verifier_fichier(self.fichier_param())
        self.assertFalse(rapport.ok)


class TestArchives(CasPurge):
    def test_seuls_les_dossiers_anciens_sont_listes(self):
        self.regle(retention_archive_jours=30)
        vieux, limite, recent = self.archive(31), self.archive(30), self.archive(1)
        plan = self.planifier()
        self.assertEqual([e.chemin for e in plan.elements], [vieux])
        self.assertEqual(plan.elements[0].fichiers, 1)
        self.assertEqual(plan.elements[0].octets, 3)
        self.assertTrue(os.path.isdir(limite) and os.path.isdir(recent))

    def test_dossier_non_date_jamais_touche(self):
        self.regle(retention_archive_jours=1)
        racine = os.path.join(self.src, "archive")
        divers = self.archive(0, racine=racine, nom="divers")
        faux = self.archive(0, racine=racine, nom="2020-13-45")
        plan = self.planifier()
        self.assertEqual([e.chemin for e in plan.elements], [])
        self.assertEqual([i["chemin"] for i in plan.ignores], [faux])
        self.assertTrue(os.path.isdir(divers))

    def test_appliquer_supprime_meme_en_lecture_seule(self):
        self.regle(retention_archive_jours=10)
        vieux = self.archive(100)
        os.chmod(os.path.join(vieux, "f.txt"), stat.S_IREAD)
        recent = self.archive(2)
        resultat = purge.appliquer(self.planifier())
        self.assertFalse(os.path.exists(vieux))
        self.assertTrue(os.path.isdir(recent))
        self.assertEqual((resultat["archives"], resultat["erreurs"]), (1, []))

    def test_modele_par_annee_mois_jour_supprime_les_dossiers_parents_vides(self):
        self.regle(archive=".\\archive\\{AAAA}\\{MM}\\{JJ}", retention_archive_jours=60)
        racine = os.path.join(self.src, "archive")
        ancien = os.path.join(racine, "2026", "01", "10")
        os.makedirs(ancien)
        with open(os.path.join(ancien, "a.txt"), "w") as f:
            f.write("a")
        recent = os.path.join(racine, "2026", "06", "10")
        os.makedirs(recent)
        purge.appliquer(self.planifier())
        self.assertFalse(os.path.exists(os.path.join(racine, "2026", "01")))
        self.assertTrue(os.path.isdir(recent))
        self.assertTrue(os.path.isdir(racine))

    def test_archive_mensuelle_n_est_purgee_qu_apres_son_dernier_jour(self):
        self.regle(archive=".\\archive\\{AAAA}-{MM}", retention_archive_jours=20)
        racine = os.path.join(self.src, "archive")
        mai = self.archive(0, racine=racine, nom="2026-05")        # fin le 31/05 = 15 jours
        avril = self.archive(0, racine=racine, nom="2026-04")      # fin le 30/04 = 46 jours
        plan = self.planifier()
        self.assertEqual([e.chemin for e in plan.elements], [avril])
        self.assertTrue(os.path.isdir(mai))

    def test_archive_absolue_ailleurs(self):
        racine = self.chemin("archives_ailleurs")
        self.regle(archive=racine + "\\{AAAA}-{MM}-{JJ}", retention_archive_jours=10)
        vieux = self.archive(40, racine=racine)
        os.makedirs(racine, exist_ok=True)
        self.assertEqual([e.chemin for e in self.planifier().elements], [vieux])

    def test_racine_confondue_avec_la_source_refusee(self):
        self.regle(archive="{AAAA}-{MM}-{JJ}", retention_archive_jours=10)
        dossier = self.archive(100, racine=self.src)
        plan = self.planifier()
        self.assertEqual(plan.elements, [])
        self.assertEqual(len(plan.erreurs), 1)
        self.assertIn("source", plan.erreurs[0])
        self.assertTrue(os.path.isdir(dossier))

    def test_racine_dans_la_cible_ou_contenant_la_cible_refusee(self):
        self.regle(archive=self.dst + "\\{AAAA}-{MM}-{JJ}", retention_archive_jours=10)
        self.archive(100, racine=self.dst)
        plan = self.planifier()
        self.assertEqual(plan.elements, [])
        self.assertEqual(len(plan.erreurs), 1)

    def test_racine_d_un_disque_refusee(self):
        lecteur = os.path.splitdrive(self.racine)[0] + "\\"
        erreur = purge._garde_fous(lecteur, self.src, self.dst)
        self.assertIsNotNone(erreur)

    def test_modele_sans_variable_ou_variable_repetee(self):
        with self.assertRaises(purge.ErreurModele):
            purge.decouper_modele(".\\archive", self.src)
        with self.assertRaises(purge.ErreurModele):
            purge.decouper_modele(".\\{AAAA}\\{AAAA}", self.src)
        with self.assertRaises(purge.ErreurModele):
            purge.decouper_modele(".\\archive\\{Inconnue}", self.src)

    def test_archivages_en_attente_protegent_le_dossier(self):
        self.regle(retention_archive_jours=10)
        vieux = self.archive(100)
        autre = self.archive(90)
        p = self.parametrage()
        base.initialiser(self.chemin_base, "production", "u")
        with base.ouvrir(self.chemin_base, "production") as b:
            numeros, _ = b.synchroniser_regles([("r1", b"x")])
            no = numeros["r1"]
            b.noter_intention(no, b"k" * 16, os.path.join(self.src, "a.txt"), self.dst,
                              os.path.join(vieux, "a.txt"), 1, 1, "00")
            b.confirmer_livraison(b"k" * 16, False, "archivage")
            self.assertEqual(len(b.actions(no, "archivage")), 1)
            plan = purge.planifier(p, b, AUJOURDHUI)
        self.assertNotIn(vieux, [e.chemin for e in plan.elements])
        self.assertIn(autre, [e.chemin for e in plan.elements])
        self.assertIn(vieux, [i["chemin"] for i in plan.ignores])

    def test_lien_symbolique_ou_jonction_jamais_suivi(self):
        self.regle(retention_archive_jours=10)
        cible = self.chemin("ailleurs")
        os.makedirs(cible)
        garde = os.path.join(cible, "important.txt")
        with open(garde, "w") as f:
            f.write("a")
        racine = os.path.join(self.src, "archive")
        os.makedirs(racine)
        lien = os.path.join(racine, jour(100))
        try:
            os.symlink(cible, lien, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("creation de lien symbolique impossible sans privilege")
        plan = self.planifier()
        self.assertEqual(plan.elements, [])
        purge.appliquer(plan)
        self.assertTrue(os.path.exists(garde))

    def test_suppression_hors_racine_refusee(self):
        autre = self.chemin("autre")
        os.makedirs(autre)
        with self.assertRaises(OSError):
            purge._supprimer_arbre(autre, self.chemin("racine"))
        self.assertTrue(os.path.isdir(autre))

    def test_une_erreur_n_arrete_pas_les_suivants(self):
        self.regle(retention_archive_jours=10)
        a, b = self.archive(100), self.archive(90)
        plan = self.planifier()
        journal = Enregistreur()
        ouvert = open(os.path.join(a, "f.txt"), "rb")          # Windows : fichier verrouille
        try:
            resultat = purge.appliquer(plan, journal)
        finally:
            ouvert.close()
        if os.name == "nt":
            self.assertEqual(len(resultat["erreurs"]), 1)
            self.assertIn("purge_echec", journal.noms())
            self.assertEqual(resultat["archives"], 1)
            self.assertFalse(os.path.exists(b))


class TestPurgeBase(CasPurge):
    def test_une_fois_par_jour_et_evenement(self):
        self.regle()
        p = self.parametrage()
        journal, lanc = Enregistreur(), lancement.Lancement()
        with self.base() as b:
            b.synchroniser_regles([("r1", b"x")])
            lancement.purger_base(p, b, journal, lanc)
            lancement.purger_base(p, b, journal, lanc)
        self.assertEqual(journal.noms(), ["purge_base"])
        self.assertEqual(journal.evenements[0][2], {"fichiers": 0, "executions": 0})

    def test_un_echec_est_un_avertissement(self):
        self.regle()
        p = self.parametrage()

        class Casse(object):
            def numero_regle(self, ident):
                return 1

            def purger(self, *a, **k):
                raise base.ErreurBase("disque plein")

        journal, lanc = Enregistreur(), lancement.Lancement()
        lancement.purger_base(p, Casse(), journal, lanc)
        self.assertEqual(journal.noms(), ["purge_base_echec"])
        self.assertEqual(journal.evenements[0][1], "WARNING")
        self.assertEqual(lanc.niveau, 1)


class TestCommande(CasPurge):
    def lancer(self, *args):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(io.StringIO()):
            code = cli._main(["--config", self.fichier_param(), "--purger", "--format", "json"] + list(args))
        return code, json.loads(sortie.getvalue())

    def preparer(self):
        self.entete_extra = {"retention_journaux_jours": 10}
        self.regle(retention_archive_jours=10)
        base.initialiser(self.chemin_base, "production", "u")
        self.vieux_journal = self.journal("r1", 60)
        self.vieille_archive = self.archive(60)

    def test_sans_appliquer_rien_n_est_supprime(self):
        self.preparer()
        code, r = self.lancer()
        self.assertEqual(code, 0)
        self.assertEqual(r["version_contrat"], 1)
        self.assertFalse(r["appliquee"])
        self.assertEqual({e["type"] for e in r["a_purger"]}, {"journal", "archive"})
        self.assertTrue(os.path.exists(self.vieux_journal) and os.path.isdir(self.vieille_archive))

    def test_appliquer_supprime_et_trace(self):
        self.preparer()
        code, r = self.lancer("--appliquer")
        self.assertEqual(code, 0)
        self.assertTrue(r["appliquee"])
        self.assertEqual((r["resultat"]["journaux"], r["resultat"]["archives"]), (1, 1))
        self.assertFalse(os.path.exists(self.vieux_journal))
        self.assertFalse(os.path.exists(self.vieille_archive))
        contenu = ""
        for f in os.listdir(self.logs):
            with open(os.path.join(self.logs, f), encoding="utf-8") as fichier:
                contenu += fichier.read()
        self.assertIn("purge_supprime", contenu)

    def test_rien_a_purger(self):
        self.regle()
        base.initialiser(self.chemin_base, "production", "u")
        code, r = self.lancer("--appliquer")
        self.assertEqual((code, r["a_purger"]), (0, []))

    def test_regle_en_erreur_donne_un_avertissement(self):
        self.regle(archive="{AAAA}-{MM}-{JJ}", retention_archive_jours=10)
        base.initialiser(self.chemin_base, "production", "u")
        os.makedirs(os.path.join(self.src, jour(100)))
        code, r = self.lancer()
        self.assertEqual(code, 4)
        self.assertEqual(len(r["erreurs_regles"]), 1)

    def test_base_absente(self):
        self.regle(retention_archive_jours=10)
        code, r = self.lancer()
        self.assertEqual(code, 2)

    def test_appliquer_sans_purger_refuse(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            cli._main(["--config", "x.jsonl", "--appliquer"])


if __name__ == "__main__":
    unittest.main()
