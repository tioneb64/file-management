"""J2 : base SQLite. Schema, ouverture, flag atomique, journal d'intention, purge, sauvegarde,
concurrence entre processus et arret brutal."""
import contextlib
import io
import json
import os
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from file_management import __main__ as cli
from file_management import base
from tests.outils import CasTemporaire
from tests.travailleurs import lancer_en_parallele

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lancer(code):
    """Execute du code dans un processus Python separe (pour simuler un arret brutal)."""
    return subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, %r)\n%s"
                           % (RACINE, code)], capture_output=True, text=True, timeout=60)


class CasBase(CasTemporaire):
    """Base modele creee une fois par classe (chaque commit coute un fsync), copiee pour chaque test."""

    @classmethod
    def setUpClass(cls):
        cls.dossier_modele = tempfile.mkdtemp(prefix="copie_modele_")
        cls.addClassCleanup(shutil.rmtree, cls.dossier_modele, True)
        cls.modele = os.path.join(cls.dossier_modele, "modele.db")
        base.initialiser(cls.modele, "production", "testeur")
        with base.ouvrir(cls.modele) as b:
            b.synchroniser_regles([("r1", "e1"), ("r2", "e2")])
            b.c.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def setUp(self):
        super().setUp()
        self.chemin_base = self.chemin("donnees", "production.db")
        os.makedirs(os.path.dirname(self.chemin_base))
        shutil.copy(self.modele, self.chemin_base)
        self.b = base.ouvrir(self.chemin_base, "production")
        self.addCleanup(self.fermer)
        self.numeros, _ = self.b.synchroniser_regles([("r1", "e1"), ("r2", "e2")])
        self.no = self.numeros["r1"]

    def fermer(self):
        with contextlib.suppress(sqlite3.Error):
            self.b.fermer()

    def cle(self, nom="a.csv", taille=10, mtime=1):
        return base.cle_version("r1", nom, taille, mtime)


class TestCreation(CasTemporaire):
    def test_initialiser_cree_schema_meta_et_journal(self):
        chemin = self.chemin("sous", "dossier", "production.db")
        base.initialiser(chemin, "production", "benoit")
        with base.ouvrir(chemin, "production") as b:
            tables = {l[0] for l in b.c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"meta", "regles", "executions", "fichiers", "actions_en_attente",
                             "journal_actions"} <= tables)
            self.assertEqual(b.c.execute("PRAGMA user_version").fetchone()[0], base.VERSION_SCHEMA)
            self.assertEqual(b.c.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(b.meta("environnement"), "production")
            self.assertIsNotNone(b.meta("cree_le"))
            ligne = b.c.execute("SELECT utilisateur, action FROM journal_actions").fetchone()
            self.assertEqual((ligne["utilisateur"], ligne["action"]), ("benoit", "initialisation"))

    def test_initialiser_refuse_une_base_existante(self):
        chemin = self.chemin("production.db")
        base.initialiser(chemin, "production", "u")
        with self.assertRaises(base.BaseExiste):
            base.initialiser(chemin, "production", "u")

    def test_initialiser_refuse_un_partage_reseau(self):
        with self.assertRaises(base.BaseSurReseau):
            base.initialiser("\\\\SRV\\partage\\x.db", "production", "u")
        with self.assertRaises(base.BaseSurReseau):
            base.ouvrir("\\\\SRV\\partage\\x.db")

    def test_lecteur_reseau_mappe_refuse(self):
        if os.name != "nt":
            self.skipTest("lecteurs Windows")
        with mock.patch.object(base, "_type_lecteur", return_value=base.DRIVE_REMOTE):
            with self.assertRaises(base.BaseSurReseau) as cm:
                base.initialiser(self.chemin("x.db"), "production", "u")
        self.assertIn("lecteur reseau", str(cm.exception))
        self.assertFalse(os.path.exists(self.chemin("x.db")))

    def test_disque_local_reel_accepte(self):
        base.verifier_disque_local(self.chemin("x.db"))

    def test_la_base_n_est_jamais_creee_automatiquement(self):
        chemin = self.chemin("absente.db")
        with self.assertRaises(base.BaseAbsente):
            base.ouvrir(chemin)
        self.assertFalse(os.path.exists(chemin))
        self.assertEqual(os.listdir(self.racine), [])

    def test_fichier_qui_n_est_pas_une_base(self):
        self.ecrire("texte.db", b"ceci n'est pas une base sqlite" * 10)
        with self.assertRaises(base.BaseIncoherente):
            base.ouvrir(self.chemin("texte.db"))

    def test_base_sqlite_etrangere(self):
        chemin = self.chemin("autre.db")
        c = sqlite3.connect(chemin)
        c.execute("CREATE TABLE x(a)")
        c.commit()
        c.close()
        with self.assertRaises(base.BaseIncoherente):
            base.ouvrir(chemin)

    def test_base_d_un_autre_environnement(self):
        chemin = self.chemin("recette.db")
        base.initialiser(chemin, "recette", "u")
        with self.assertRaises(base.BaseIncoherente) as cm:
            base.ouvrir(chemin, "production")
        self.assertIn("recette", str(cm.exception))

    def test_schema_plus_recent_refuse(self):
        chemin = self.chemin("production.db")
        base.initialiser(chemin, "production", "u")
        c = sqlite3.connect(chemin)
        c.execute("PRAGMA user_version = 99")
        c.close()
        with self.assertRaises(base.BaseTropRecente):
            base.ouvrir(chemin)

    def test_migration_de_schema(self):
        chemin = self.chemin("production.db")
        base.initialiser(chemin, "production", "u")
        migrations = {1: ["ALTER TABLE regles ADD COLUMN nouveaute TEXT"]}
        with mock.patch.object(base, "VERSION_SCHEMA", 2), \
                mock.patch.object(base, "MIGRATIONS", migrations):
            with base.ouvrir(chemin) as b:
                self.assertEqual(b.c.execute("PRAGMA user_version").fetchone()[0], 2)
                b.c.execute("SELECT nouveaute FROM regles")
            with base.ouvrir(chemin):          # deja a jour : pas de seconde migration
                pass

    def test_migration_manquante_refusee(self):
        chemin = self.chemin("production.db")
        base.initialiser(chemin, "production", "u")
        with mock.patch.object(base, "VERSION_SCHEMA", 2), mock.patch.object(base, "MIGRATIONS", {}):
            with self.assertRaises(base.ErreurBase):
                base.ouvrir(chemin)

    def test_migration_en_echec_ne_change_rien(self):
        chemin = self.chemin("production.db")
        base.initialiser(chemin, "production", "u")
        migrations = {1: ["ALTER TABLE regles ADD COLUMN a TEXT", "INSTRUCTION INVALIDE"]}
        with mock.patch.object(base, "VERSION_SCHEMA", 2), \
                mock.patch.object(base, "MIGRATIONS", migrations):
            with self.assertRaises(base.ErreurBase):
                base.ouvrir(chemin)
        with base.ouvrir(chemin) as b:
            self.assertEqual(b.c.execute("PRAGMA user_version").fetchone()[0], 1)
            colonnes = [l[1] for l in b.c.execute("PRAGMA table_info(regles)")]
            self.assertNotIn("a", colonnes)

    def test_reglages_de_connexion(self):
        chemin = self.chemin("production.db")
        base.initialiser(chemin, "production", "u")
        with base.ouvrir(chemin) as b:
            self.assertEqual(b.c.execute("PRAGMA synchronous").fetchone()[0], 2)     # FULL
            self.assertEqual(b.c.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(b.c.execute("PRAGMA busy_timeout").fetchone()[0], 30000)

    def test_lecture_seule(self):
        chemin = self.chemin("production.db")
        base.initialiser(chemin, "production", "u")
        with base.ouvrir(chemin, lecture_seule=True) as b:
            self.assertEqual(b.meta("environnement"), "production")
            with self.assertRaises(base.ErreurBase):
                b.ecrire_meta("x", "y")
            with self.assertRaises(sqlite3.OperationalError):
                b.c.execute("INSERT INTO meta VALUES ('a', 'b')")


class TestRegles(CasBase):
    def test_synchronisation_idempotente_et_sans_casse(self):
        numeros, modifiees = self.b.synchroniser_regles([("R1", "e1"), ("r3", "e3")])
        self.assertEqual(numeros["r1"], self.no)                 # meme regle malgre la casse
        self.assertEqual(modifiees, [])
        self.assertEqual(self.b.c.execute("SELECT COUNT(*) FROM regles").fetchone()[0], 3)

    def test_changement_de_parametres_detecte(self):
        _, modifiees = self.b.synchroniser_regles([("r1", "e1-bis"), ("r2", "e2")])
        self.assertEqual(modifiees, ["r1"])
        self.assertEqual(self.b.regle(self.no)["empreinte_parametres"], "e1-bis")

    def test_etat_initial(self):
        r = self.b.regle(self.no)
        self.assertEqual((r["en_cours"], r["dernier_statut"], r["reprise"], r["archivage_degrade"]),
                         (0, "JAMAIS_LANCEE", 0, 0))


class TestFlagEtExecutions(CasBase):
    def test_prise_puis_refus(self):
        premiere = self.b.demarrer_execution(self.no, "planifie", 1234, 99, "SRV", "42")
        self.assertIsNotNone(premiere)
        r = self.b.regle(self.no)
        self.assertEqual((r["en_cours"], r["execution_id"], r["pid"], r["hote"], r["build"]),
                         (1, premiere, 1234, "SRV", "42"))
        self.assertIsNone(self.b.demarrer_execution(self.no, "planifie", 5678))
        # la tentative refusee ne laisse aucune execution fantome
        self.assertEqual(self.b.c.execute("SELECT COUNT(*) FROM executions").fetchone()[0], 1)

    def test_deux_regles_independantes(self):
        self.assertIsNotNone(self.b.demarrer_execution(self.numeros["r1"], "planifie", 1))
        self.assertIsNotNone(self.b.demarrer_execution(self.numeros["r2"], "planifie", 2))

    def test_fin_d_execution_atomique(self):
        ex = self.b.demarrer_execution(self.no, "planifie", 1)
        ok = self.b.terminer_execution(ex, self.no, "SUCCES", motif="ras",
                                       compteurs={"selectionnes": 5, "livres": 4, "ignores": 1,
                                                  "octets": 1000})
        self.assertTrue(ok)
        r = self.b.regle(self.no)
        self.assertEqual((r["en_cours"], r["execution_id"], r["dernier_statut"], r["dernier_motif"]),
                         (0, None, "SUCCES", "ras"))
        self.assertIsNotNone(r["dernier_succes"])
        e = self.b.c.execute("SELECT * FROM executions WHERE id = ?", (ex,)).fetchone()
        self.assertEqual((e["statut"], e["nb_livres"], e["octets_livres"]), ("SUCCES", 4, 1000))
        self.assertIsNotNone(self.b.demarrer_execution(self.no, "planifie", 2))     # libre a nouveau

    def test_erreur_memorisee_et_arret(self):
        ex = self.b.demarrer_execution(self.no, "planifie", 1)
        self.b.terminer_execution(ex, self.no, "ERREUR", compteurs={"erreurs": 1},
                                  erreur={"situation": "fichier_verrouille", "message": "verrou"},
                                  arret_apres_erreur=True)
        r = self.b.regle(self.no)
        self.assertEqual((r["dernier_statut"], r["derniere_erreur_situation"],
                          r["derniere_erreur_message"], r["arret_apres_erreur"]),
                         ("ERREUR", "fichier_verrouille", "verrou", 1))
        self.assertIsNone(r["dernier_succes"])
        # un succes ulterieur garde la trace de la derniere erreur
        ex = self.b.demarrer_execution(self.no, "reprise", 1)
        self.b.terminer_execution(ex, self.no, "SUCCES")
        r = self.b.regle(self.no)
        self.assertEqual(r["derniere_erreur_situation"], "fichier_verrouille")
        self.assertIsNotNone(r["dernier_succes"])
        self.assertEqual(r["arret_apres_erreur"], 0)

    def test_statut_inconnu_refuse(self):
        ex = self.b.demarrer_execution(self.no, "planifie", 1)
        with self.assertRaises(ValueError):
            self.b.terminer_execution(ex, self.no, "BIZARRE")

    def test_fin_apres_deblocage_ne_touche_pas_la_regle(self):
        ex = self.b.demarrer_execution(self.no, "planifie", 1)
        self.assertTrue(self.b.liberer_flag(self.no, "debloquee par exploitation"))
        ex2 = self.b.demarrer_execution(self.no, "planifie", 2)
        # le processus debloque se termine tardivement : il ne doit pas liberer le flag du nouveau
        self.assertFalse(self.b.terminer_execution(ex, self.no, "SUCCES"))
        r = self.b.regle(self.no)
        self.assertEqual((r["en_cours"], r["execution_id"]), (1, ex2))

    def test_liberation_d_un_orphelin(self):
        ex = self.b.demarrer_execution(self.no, "planifie", 1)
        self.assertTrue(self.b.liberer_flag(self.no, "processus disparu"))
        e = self.b.c.execute("SELECT statut, message, fin FROM executions WHERE id = ?",
                             (ex,)).fetchone()
        self.assertEqual((e["statut"], e["message"]), ("ARRETEE", "processus disparu"))
        self.assertIsNotNone(e["fin"])
        self.assertEqual(self.b.regle(self.no)["dernier_statut"], "ARRETEE")
        self.assertFalse(self.b.liberer_flag(self.no, "deja libre"))

    def test_horloge_injectee(self):
        self.b.horloge = lambda: 1_700_000_000
        ex = self.b.demarrer_execution(self.no, "planifie", 1)
        self.assertEqual(self.b.regle(self.no)["debut_traitement"], 1_700_000_000)
        self.b.terminer_execution(ex, self.no, "SUCCES")
        self.assertEqual(self.b.regle(self.no)["dernier_succes"], 1_700_000_000)


class TestEmpreintes(unittest.TestCase):
    def test_longueur_et_stabilite(self):
        cle = base.cle_version("r1", "a.csv", 10, 5)
        self.assertEqual(len(cle), 16)
        self.assertEqual(cle, base.cle_version("r1", "a.csv", 10, 5))

    def test_chaque_composant_change_la_cle(self):
        reference = base.cle_version("r1", "a.csv", 10, 5)
        for autre in (base.cle_version("r2", "a.csv", 10, 5), base.cle_version("r1", "b.csv", 10, 5),
                      base.cle_version("r1", "a.csv", 11, 5), base.cle_version("r1", "a.csv", 10, 6)):
            self.assertNotEqual(autre, reference)

    def test_normalisation_du_nom(self):
        self.assertEqual(base.cle_version("R1", "Dossier/Fichier.CSV", 1, 1),
                         base.cle_version("r1", "dossier\\fichier.csv", 1, 1))
        decompose = "été.csv"       # e + accent combinant
        compose = "été.csv"
        self.assertEqual(base.cle_version("r1", decompose, 1, 1), base.cle_version("r1", compose, 1, 1))

    def test_genres_version_et_contenu_distincts(self):
        self.assertNotEqual(base.cle_version("r1", "a", 1, 1), base.cle_contenu("r1", "a", "ab"))
        self.assertEqual(base.cle_contenu("r1", "A", "ABC"), base.cle_contenu("r1", "a", "abc"))
        self.assertNotEqual(base.cle_contenu("r1", "a", "abc"), base.cle_contenu("r1", "a", "abd"))

    def test_separateur_sans_ambiguite(self):
        self.assertNotEqual(base.cle_version("r1", "a", 12, 3), base.cle_version("r1", "a", 1, 23))

    def test_nom_avec_caractere_isole_windows(self):
        self.assertEqual(len(base.cle_version("r1", "bizarre\udcff.txt", 1, 1)), 16)


class TestJournalIntention(CasBase):
    def livraison(self, cle=None, **kw):
        cle = cle or self.cle()
        self.assertTrue(self.b.noter_intention(self.no, cle, "S\\a.csv", "C\\a.csv", **kw))
        return cle

    def test_cycle_complet_mode_copie(self):
        cle = self.livraison(taille=10, mtime_ns=1)
        self.assertEqual(self.b.etat_fichier(cle), base.INTENTION)
        self.assertEqual([a["type"] for a in self.b.actions(self.no)], ["livraison"])
        self.b.confirmer_livraison(cle, termine=True)
        self.assertEqual(self.b.etat_fichier(cle), base.TERMINE)
        self.assertEqual(self.b.actions(self.no), [])

    def test_cycle_complet_avec_archivage(self):
        cle = self.livraison(chemin_archive="A\\a.csv")
        self.b.confirmer_livraison(cle, termine=False, action_suivante="archivage", sha256="abc")
        self.assertEqual(self.b.etat_fichier(cle), base.LIVRE)
        (action,) = self.b.actions(self.no)
        self.assertEqual((action["type"], action["chemin_source"], action["chemin_archive"],
                          action["sha256"]), ("archivage", "S\\a.csv", "A\\a.csv", "abc"))
        self.b.terminer_fichier(cle)
        self.assertEqual(self.b.etat_fichier(cle), base.TERMINE)
        self.assertEqual(self.b.actions(self.no), [])

    def test_intention_en_double_refusee(self):
        cle = self.livraison()
        self.assertFalse(self.b.noter_intention(self.no, cle, "S", "C"))
        self.assertEqual(self.b.c.execute("SELECT COUNT(*) FROM actions_en_attente").fetchone()[0], 1)

    def test_transitions_invalides(self):
        cle = self.cle("x.csv")
        with self.assertRaises(base.TransitionInvalide):
            self.b.confirmer_livraison(cle, termine=True)        # jamais note
        with self.assertRaises(base.TransitionInvalide):
            self.b.terminer_fichier(self.livraison())            # INTENTION -> TERMINE direct
        autre = self.livraison(self.cle("y.csv"))
        self.b.confirmer_livraison(autre, termine=True)
        with self.assertRaises(base.TransitionInvalide):
            self.b.confirmer_livraison(autre, termine=True)      # deja termine
        with self.assertRaises(ValueError):
            self.b.confirmer_livraison(self.livraison(self.cle("z.csv")), termine=True,
                                       action_suivante="suppression")

    def test_orphelins_deviennent_incertains(self):
        cle = self.livraison()
        livre = self.livraison(self.cle("b.csv"))
        self.b.confirmer_livraison(livre, termine=True)
        self.assertEqual(self.b.marquer_orphelins_incertains(self.no), 1)
        self.assertEqual(self.b.etat_fichier(cle), base.INCERTAIN)
        self.assertEqual(self.b.etat_fichier(livre), base.TERMINE)
        self.assertEqual(self.b.incertains(self.no), [(cle, "S\\a.csv", "C\\a.csv")])
        self.assertEqual(self.b.incertains(self.numeros["r2"]), [])
        self.assertEqual(self.b.marquer_orphelins_incertains(self.no), 0)

    def test_resolution_d_un_incertain(self):
        cle = self.livraison()
        self.b.marquer_orphelins_incertains(self.no)
        with self.assertRaises(ValueError):
            self.b.resoudre_incertain(cle, "livre", "benoit", " ")
        self.b.resoudre_incertain(cle, "livre", "benoit", "verifie dans la cible")
        self.assertEqual(self.b.etat_fichier(cle), base.TERMINE)
        self.assertEqual(self.b.incertains(self.no), [])
        self.assertEqual(self.b.actions(self.no), [])
        trace = self.b.c.execute("SELECT utilisateur, resultat FROM journal_actions "
                                 "WHERE action = 'incertain'").fetchone()
        self.assertEqual((trace["utilisateur"], trace["resultat"]), ("benoit", "livre"))

    def test_incertain_a_relivrer_est_oublie(self):
        cle = self.livraison()
        self.b.marquer_orphelins_incertains(self.no)
        self.b.resoudre_incertain(cle, "a_relivrer", "benoit", "absent de la cible")
        self.assertIsNone(self.b.etat_fichier(cle))
        self.assertTrue(self.b.noter_intention(self.no, cle, "S", "C"))        # peut etre relivre

    def test_vu_jour_au_plus_une_fois_par_jour(self):
        cle = self.livraison()
        self.b.confirmer_livraison(cle, termine=True)
        jour = base.jour_de(self.b.maintenant())
        self.assertFalse(self.b.noter_vu(cle, jour))                 # deja vu aujourd'hui
        self.assertTrue(self.b.noter_vu(cle, jour + 1))
        self.assertFalse(self.b.noter_vu(cle, jour + 1))
        self.assertFalse(self.b.noter_vu(cle, jour))                 # jamais en arriere

    def test_echec_d_action(self):
        cle = self.livraison()
        self.b.confirmer_livraison(cle, termine=False, action_suivante="suppression")
        (action,) = self.b.actions(self.no, "suppression")
        self.b.echec_action(action["id"], "verrouille")
        self.b.echec_action(action["id"], "verrouille encore")
        (action,) = self.b.actions(self.no)
        self.assertEqual((action["tentatives"], action["dernier_message"]), (2, "verrouille encore"))


class TestPurge(CasBase):
    def remplir(self):
        self.b.horloge = lambda: 1_700_000_000 + 86400 * 100
        for nom, etat, vu in (("vieux_termine", base.TERMINE, 10), ("recent_termine", base.TERMINE, 99),
                              ("vieux_livre", base.LIVRE, 10), ("vieux_incertain", base.INCERTAIN, 10)):
            self.b.c.execute("INSERT INTO fichiers(cle, regle_no, etat, vu_jour) VALUES (?, ?, ?, ?)",
                             (self.cle(nom), self.no, etat, base.jour_de(1_700_000_000) + vu))
        self.b.c.execute("INSERT INTO executions(regle_no, declencheur, debut, fin, statut) "
                         "VALUES (?, 'planifie', ?, ?, 'SUCCES')", (self.no, 1_700_000_000, 1_700_000_100))
        self.b.c.execute("INSERT INTO executions(regle_no, declencheur, debut) VALUES (?, 'planifie', ?)",
                         (self.no, 1_700_000_000))        # jamais terminee : conservee

    def test_purge_ne_touche_que_les_termines_anciens(self):
        self.remplir()
        resultat = self.b.purger({self.no: 30}, 365 // 4)
        self.assertEqual(resultat, {"fichiers": 1, "executions": 1})
        self.assertIsNone(self.b.etat_fichier(self.cle("vieux_termine")))
        for conserve in ("recent_termine", "vieux_livre", "vieux_incertain"):
            self.assertIsNotNone(self.b.etat_fichier(self.cle(conserve)), conserve)
        self.assertEqual(self.b.c.execute("SELECT COUNT(*) FROM executions").fetchone()[0], 1)

    def test_purge_une_seule_fois_par_jour(self):
        self.remplir()
        self.assertIsNotNone(self.b.purger({self.no: 30}, 30))
        self.assertIsNone(self.b.purger({self.no: 30}, 30))
        self.assertIsNotNone(self.b.purger({self.no: 30}, 30, forcer=True))
        self.b.horloge = lambda: 1_700_000_000 + 86400 * 101
        self.assertIsNotNone(self.b.purger({self.no: 30}, 30))

    def test_regle_hors_liste_non_purgee(self):
        self.remplir()
        self.b.purger({self.numeros["r2"]: 1}, 30)
        self.assertIsNotNone(self.b.etat_fichier(self.cle("vieux_termine")))


class TestSauvegarde(CasBase):
    def test_sauvegarde_coherente_d_une_base_en_cours_d_utilisation(self):
        cle = self.cle()
        self.b.noter_intention(self.no, cle, "S", "C")
        self.b.confirmer_livraison(cle, termine=True)
        dossier = self.chemin("sauvegardes")
        fichier = base.sauvegarder(self.chemin_base, dossier)           # self.b reste ouverte
        self.assertTrue(os.path.basename(fichier).startswith("production_"))
        self.assertEqual(os.listdir(dossier), [os.path.basename(fichier)])     # pas de .tmp, un seul fichier
        with base.ouvrir(fichier, "production") as copie:
            self.assertEqual(copie.etat_fichier(cle), base.TERMINE)
            self.assertEqual(copie.verifier_integrite(), [])
            self.assertEqual(copie.c.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        # la base d'origine est intacte et reste utilisable
        self.assertEqual(self.b.etat_fichier(cle), base.TERMINE)

    def test_sauvegarde_d_une_base_absente(self):
        with self.assertRaises(base.BaseAbsente):
            base.sauvegarder(self.chemin("rien.db"), self.chemin("sauvegardes"))
        self.assertFalse(os.path.exists(self.chemin("sauvegardes")))

    def test_restauration_par_copie(self):
        import shutil
        cle = self.cle()
        self.b.noter_intention(self.no, cle, "S", "C")
        self.b.confirmer_livraison(cle, termine=True)
        fichier = base.sauvegarder(self.chemin_base, self.chemin("sauvegardes"))
        self.b.fermer()
        for suffixe in ("", "-wal", "-shm"):
            with contextlib.suppress(OSError):
                os.remove(self.chemin_base + suffixe)
        shutil.copy(fichier, self.chemin_base)
        with base.ouvrir(self.chemin_base, "production") as restauree:
            self.assertEqual(restauree.etat_fichier(cle), base.TERMINE)
            self.b = restauree

    def test_integrite(self):
        self.assertEqual(self.b.verifier_integrite(), [])


class TestConcurrence(CasBase):
    def test_un_seul_gagnant_pour_une_meme_regle(self):
        gagnants = lancer_en_parallele("prendre", [(self.chemin_base, self.no)] * 8)
        self.assertEqual(sum(gagnants), 1)
        self.assertEqual(self.b.c.execute("SELECT COUNT(*) FROM executions").fetchone()[0], 1)

    def test_chaque_regle_prise_une_fois_sous_forte_concurrence(self):
        regles = [("c%d" % i, "e") for i in range(10)]
        numeros, _ = self.b.synchroniser_regles(regles)
        taches = [(self.chemin_base, numeros["c%d" % i]) for i in range(10) for _ in range(3)]
        gagnants = lancer_en_parallele("prendre", taches)
        self.assertEqual(sum(gagnants), 10)
        self.assertEqual(self.b.c.execute("SELECT COUNT(*) FROM regles WHERE en_cours = 1").fetchone()[0], 10)
        self.assertEqual(self.b.c.execute("SELECT COUNT(*) FROM executions").fetchone()[0], 10)

    def test_ecritures_simultanees_sans_perte_ni_verrou(self):
        taches = [(self.chemin_base, self.no, p * 50, 50) for p in range(4)]
        ecrites = lancer_en_parallele("ecrire", taches)
        self.assertEqual(sum(ecrites), 200)
        self.assertEqual(self.b.c.execute("SELECT COUNT(*) FROM fichiers").fetchone()[0], 200)
        self.assertEqual(self.b.c.execute("SELECT COUNT(*) FROM actions_en_attente").fetchone()[0], 200)

    def test_base_verrouillee_signalee_apres_le_delai(self):
        autre = base.ouvrir(self.chemin_base, busy_timeout_ms=200)
        self.addCleanup(autre.fermer)
        self.b.c.execute("BEGIN IMMEDIATE")
        try:
            with self.assertRaises(base.BaseIndisponible):
                autre.demarrer_execution(self.no, "planifie", 1)
        finally:
            self.b.c.execute("ROLLBACK")
        self.assertIsNotNone(autre.demarrer_execution(self.no, "planifie", 1))     # tout est revenu


class TestArretBrutal(CasBase):
    def test_transaction_non_validee_disparait(self):
        self.b.fermer()
        code = ("import os\nfrom file_management import base\n"
                "b = base.ouvrir(%r)\n"
                "b.c.execute('BEGIN IMMEDIATE')\n"
                "b.c.execute(\"INSERT INTO fichiers(cle, regle_no, etat, vu_jour) VALUES (x'00', 1, 1, 1)\")\n"
                "os._exit(1)\n" % self.chemin_base)
        self.assertEqual(_lancer(code).returncode, 1)
        self.b = base.ouvrir(self.chemin_base)
        self.assertEqual(self.b.c.execute("SELECT COUNT(*) FROM fichiers").fetchone()[0], 0)
        self.assertEqual(self.b.verifier_integrite(), [])

    def test_intention_validee_survit_et_devient_incertaine(self):
        self.b.fermer()
        code = ("import os\nfrom file_management import base\n"
                "b = base.ouvrir(%r)\n"
                "no = b.numero_regle('r1')\n"
                "ex = b.demarrer_execution(no, 'planifie', os.getpid())\n"
                "b.noter_intention(no, base.cle_version('r1', 'a.csv', 10, 1), 'S\\\\a.csv', 'C\\\\a.csv')\n"
                "os._exit(1)      # mort pendant la copie\n" % self.chemin_base)
        self.assertEqual(_lancer(code).returncode, 1)
        self.b = base.ouvrir(self.chemin_base)
        no = self.b.numero_regle("r1")
        r = self.b.regle(no)
        self.assertEqual(r["en_cours"], 1)                              # flag reste pose
        self.assertEqual(self.b.etat_fichier(base.cle_version("r1", "a.csv", 10, 1)), base.INTENTION)
        # nettoyage au lancement suivant : le flag est libere, la livraison devient incertaine
        self.assertTrue(self.b.liberer_flag(no, "processus disparu"))
        ex = self.b.demarrer_execution(no, "planifie", os.getpid())
        self.assertIsNotNone(ex)
        self.assertEqual(self.b.marquer_orphelins_incertains(no), 1)
        self.assertEqual(len(self.b.incertains(no)), 1)

    def test_coupure_apres_confirmation_ne_perd_rien(self):
        self.b.fermer()
        code = ("import os\nfrom file_management import base\n"
                "b = base.ouvrir(%r)\n"
                "no = b.numero_regle('r1')\n"
                "cle = base.cle_version('r1', 'a.csv', 10, 1)\n"
                "b.noter_intention(no, cle, 'S', 'C')\n"
                "b.confirmer_livraison(cle, termine=False, action_suivante='suppression')\n"
                "os._exit(1)\n" % self.chemin_base)
        _lancer(code)
        self.b = base.ouvrir(self.chemin_base)
        cle = base.cle_version("r1", "a.csv", 10, 1)
        self.assertEqual(self.b.etat_fichier(cle), base.LIVRE)
        self.assertEqual([a["type"] for a in self.b.actions(self.b.numero_regle("r1"))], ["suppression"])


class TestVolume(CasBase):
    def test_recherche_dans_une_base_de_cent_mille_cles(self):
        import time
        self.b.c.execute("BEGIN")
        self.b.c.executemany("INSERT INTO fichiers(cle, regle_no, etat, vu_jour) VALUES (?, ?, 3, 1)",
                             ((base.cle_version("r1", "f%d" % i, i, i), self.no) for i in range(100_000)))
        self.b.c.execute("COMMIT")
        cles = [base.cle_version("r1", "f%d" % i, i, i) for i in range(0, 100_000, 100)]
        debut = time.time()
        trouvees = sum(1 for cle in cles if self.b.etat_fichier(cle) == base.TERMINE)
        self.assertEqual(trouvees, 1000)
        self.assertLess(time.time() - debut, 2)


class TestCommandes(CasTemporaire):
    def parametrage(self, environnement="production"):
        chemin = self.chemin(environnement + ".jsonl")
        entete = '{"version": 1, "environnement": "%s", "base": %s}\n' % (
            environnement, '"%s"' % self.chemin("donnees", environnement + ".db").replace("\\", "\\\\"))
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(entete)
        return chemin

    def lancer(self, *args):
        sortie, erreur = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
            code = cli.main(list(args))
        return code, sortie.getvalue(), erreur.getvalue()

    def test_initialiser_puis_sauvegarder(self):
        conf = self.parametrage()
        code, sortie, _ = self.lancer("--config", conf, "--initialiser-base", "--utilisateur", "benoit")
        self.assertEqual(code, 0, sortie)
        self.assertTrue(os.path.isfile(self.chemin("donnees", "production.db")))
        code, sortie, erreur = self.lancer("--config", conf, "--initialiser-base")
        self.assertEqual(code, 2)
        self.assertIn("existe deja", erreur)
        code, sortie, _ = self.lancer("--config", conf, "--sauvegarder-base", self.chemin("sauv"))
        self.assertEqual(code, 0)
        self.assertEqual(len(os.listdir(self.chemin("sauv"))), 1)

    def ecrire_entete(self, chemin, environnement, base_db):
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(json.dumps({"version": 1, "environnement": environnement, "base": base_db}) + "\n")

    def test_renommer_environnement(self):
        ancienne = self.parametrage("production")
        self.assertEqual(self.lancer("--config", ancienne, "--initialiser-base")[0], 0)
        # le fichier est renomme et son en-tete aussi, la base garde son ancien nom : le moteur la refuse
        nouvelle = self.chemin("recette.jsonl")
        self.ecrire_entete(nouvelle, "recette", self.chemin("donnees", "production.db"))
        code, _, erreur = self.lancer("--config", nouvelle, "--etat")
        self.assertEqual(code, 2)
        self.assertIn("production", erreur)
        code, sortie, _ = self.lancer("--config", nouvelle, "--renommer-environnement", "production",
                                      "--utilisateur", "benoit")
        self.assertEqual(code, 0, sortie)
        self.assertEqual(self.lancer("--config", nouvelle, "--etat")[0], 0)
        with base.ouvrir(self.chemin("donnees", "production.db"), "recette") as b:
            self.assertEqual(b.c.execute("SELECT action FROM journal_actions ORDER BY id DESC").fetchone()[0],
                             "renommage_environnement")
        # une seconde fois : la base n'est plus a l'ancien nom
        code, _, erreur = self.lancer("--config", nouvelle, "--renommer-environnement", "production")
        self.assertEqual(code, 2)

    def test_renommer_refuse_si_une_regle_est_en_cours(self):
        ancienne = self.parametrage("production")
        self.lancer("--config", ancienne, "--initialiser-base")
        with base.ouvrir(self.chemin("donnees", "production.db")) as b:
            b.synchroniser_regles([("r1", "e")])
            b.c.execute("UPDATE regles SET en_cours = 1")
        nouvelle = self.chemin("recette.jsonl")
        self.ecrire_entete(nouvelle, "recette", self.chemin("donnees", "production.db"))
        code, _, erreur = self.lancer("--config", nouvelle, "--renommer-environnement", "production")
        self.assertEqual(code, 2)
        self.assertIn("en cours", erreur)

    def test_sauvegarde_sans_base(self):
        code, _, erreur = self.lancer("--config", self.parametrage(), "--sauvegarder-base",
                                      self.chemin("sauv"))
        self.assertEqual(code, 2)
        self.assertIn("introuvable", erreur)

    def test_parametrage_invalide_annule_la_commande(self):
        conf = self.chemin("production.jsonl")
        with open(conf, "w", encoding="utf-8") as f:
            f.write('{"version": 1, "environnement": "production"}\n')
        code, _, erreur = self.lancer("--config", conf, "--initialiser-base")
        self.assertEqual(code, 2)
        self.assertIn("E04", erreur)

    def test_commandes_exclusives(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                cli.main(["--config", "x", "--verifier", "--initialiser-base"])


if __name__ == "__main__":
    unittest.main()
