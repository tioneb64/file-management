"""J7 : programmes externes aux six points d'appel (avant_lot, avant_fichier, apres_fichier,
apres_lot, sur_erreur, reprise)."""
import json
import os
import sys
import textwrap
import time
import unittest

from file_management import base as modele_base
from file_management import lancement, programmes, processus, transfert
from file_management.parametrage import Programme
from tests.test_lancement import CasLancement
from tests.test_moteur import CasMoteur

SEPT_HEURES = {"type": "quotidien", "heure": "07:00"}


class CasProgramme(CasMoteur):
    """Regles de la couche d'execution (CasMoteur) avec des programmes factices en Python."""

    def setUp(self):
        super().setUp()
        self.entete.dossier_travail = self.chemin("travail")
        self.appels = self.chemin("appels.log")
        self.compteur = 0

    def programme(self, code=0, avant="", apres="", timeout_sec=30, arguments=()):
        """Fabrique un programme factice : enregistre son appel dans appels.log, execute `avant`,
        puis sort avec `code`. Renvoie le dictionnaire du champ `programmes`."""
        self.compteur += 1
        chemin = self.chemin("prog_%d.py" % self.compteur)
        corps = textwrap.dedent('''\
            import json, os, sys, time
            LOG = %r
            appel = {"argv": sys.argv[1:], "cwd": os.getcwd(), "pid": os.getpid(),
                     "env": {k: v for k, v in os.environ.items() if k.startswith("COPIE_")}}
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(appel, ensure_ascii=False) + "\\n")
            ''') % self.appels
        corps += textwrap.dedent(avant) + "\n" + "sys.exit(%s)\n" % code + textwrap.dedent(apres)
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(corps)
        return {"commande": [sys.executable, chemin] + list(arguments), "timeout_sec": timeout_sec}

    def lus(self):
        """Appels enregistres par les programmes factices."""
        if not os.path.exists(self.appels):
            return []
        with open(self.appels, encoding="utf-8") as f:
            return [json.loads(l) for l in f]

    def evenements_programme(self, point=None):
        return [e for e in self.evenements("programme_appele") if point is None or e["point"] == point]


# =========================================================================== #
class TestLancementDUnProgramme(CasMoteur):
    def setUp(self):
        super().setUp()
        self.travail = self.chemin("travail")
        self.journal_prog = self.chemin("prog.txt")

    def lancer_script(self, corps, *arguments, timeout_sec=30, valeurs=None, environnement=None):
        script = self.chemin("p.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(corps))
        programme = Programme((sys.executable, script) + arguments, timeout_sec)
        return programmes.executer(programme, "avant_lot", valeurs or {}, environnement or {}, self.travail)

    def test_code_retour_et_sortie_standard_et_erreur_reunies(self):
        r = self.lancer_script('''
            import sys
            print("sortie"); print("erreur", file=sys.stderr); sys.exit(3)
            ''')
        self.assertEqual(r.code, 3)
        self.assertIn("sortie", r.sortie)
        self.assertIn("erreur", r.sortie)
        self.assertFalse(r.depasse)
        self.assertFalse(r.accepte("avant_lot"))
        self.assertIn("3", r.explication("avant_lot"))

    def test_codes_acceptes_par_point(self):
        r = self.lancer_script("import sys; sys.exit(1)")
        self.assertTrue(r.accepte("avant_lot") and r.accepte("avant_fichier"))
        self.assertTrue(r.accepte("reprise"))
        self.assertFalse(r.accepte("sur_erreur"))               # sur_erreur n'a pas de code attendu

    def test_variables_remplacees_element_par_element_sans_shell(self):
        dangereux = 'Facture & (copie) "x" ; echo piege %PATH%.xml'
        r = self.lancer_script('''
            import json, sys
            print(json.dumps(sys.argv[1:], ensure_ascii=False))
            ''', "{fichier}", "--regle={regle}", "{inconnue}", valeurs={"fichier": dangereux, "regle": "r1"})
        argv = json.loads(r.sortie)
        self.assertEqual(argv, [dangereux, "--regle=r1", "{inconnue}"])      # un element = un argument, intact
        self.assertEqual(r.argv[-3:], [dangereux, "--regle=r1", "{inconnue}"])

    def test_variables_d_environnement_et_repertoire_courant(self):
        r = self.lancer_script('''
            import os
            print(os.environ["COPIE_REGLE"], os.environ["COPIE_POINT_APPEL"], os.getcwd())
            ''', environnement={"COPIE_REGLE": "r1", "COPIE_POINT_APPEL": "avant_lot"})
        regle, point, cwd = r.sortie.split(None, 2)
        self.assertEqual((regle, point), ("r1", "avant_lot"))
        self.assertEqual(os.path.normcase(cwd.strip()), os.path.normcase(self.travail))

    def test_entree_standard_fermee(self):
        r = self.lancer_script('''
            import sys
            print(repr(sys.stdin.read()))
            ''', timeout_sec=10)
        self.assertEqual(r.sortie.strip(), "''")                  # lecture immediate : fin de fichier

    def test_accents_utf8_et_page_de_code_oem(self):
        r = self.lancer_script('''
            import sys
            sys.stdout.buffer.write("é à ü — ok\\n".encode("utf-8"))
            ''')
        self.assertIn("é à ü", r.sortie)
        r = self.lancer_script('''
            import sys
            sys.stdout.buffer.write("café sorti\\n".encode("cp850"))
            ''')
        self.assertIn("caf", r.sortie)                            # jamais d'exception de decodage
        self.assertTrue(r.sortie.startswith("caf"))

    def test_sortie_tronquee_a_8_ko(self):
        r = self.lancer_script('print("x" * 50000)')
        self.assertLessEqual(len(r.sortie), programmes.LONGUEUR_SORTIE_MAX + 20)
        self.assertTrue(r.sortie.endswith("[tronquee]"))

    def test_lancement_impossible(self):
        programme = Programme((self.chemin("n_existe_pas.exe"),), 5)
        r = programmes.executer(programme, "avant_lot", {}, {}, self.travail)
        self.assertIsNone(r.code)
        self.assertIn("lancement impossible", r.erreur)
        self.assertFalse(r.accepte("avant_lot"))

    def test_duree_maximale_depassee(self):
        debut = time.time()
        r = self.lancer_script("import time; time.sleep(120)", timeout_sec=1)
        self.assertLess(time.time() - debut, 15)
        self.assertTrue(r.depasse)
        self.assertFalse(r.accepte("avant_lot"))
        self.assertEqual(r.explication("avant_lot"), "duree maximale depassee")

    def test_arret_de_l_arbre_des_la_premiere_instruction(self):
        """Le programme lance un petit-fils immediatement : il n'echappe pas au Job Object."""
        for essai in range(3):
            marque = self.chemin("petit_fils_%d.pid" % essai)
            r = self.lancer_script('''
                import subprocess, sys, time
                petit = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
                open(%r, "w").write(str(petit.pid))
                time.sleep(300)
                ''' % marque, timeout_sec=1)
            self.assertTrue(r.depasse)
            pid = int(open(marque).read())
            time.sleep(0.5)
            self.assertIsNone(processus.date_creation(pid), "petit-fils survivant (essai %d)" % essai)

    def test_listes_de_fichiers(self):
        class Candidat(object):
            chemin, relatif, taille, mtime_ns = "C:\\src\\é.csv", "é.csv", 12, 1_700_000_000_000_000_000
        entree = programmes.entree_fichier(Candidat(), resultat="livre")
        txt, js = programmes.ecrire_listes(self.travail, 42, "apres_lot", [entree])
        self.assertTrue(txt.endswith("liste_42_apres_lot.txt") and js.endswith("liste_42_apres_lot.json"))
        with open(txt, encoding="utf-8") as f:
            self.assertEqual(f.read(), "C:\\src\\é.csv\n")
        with open(js, encoding="utf-8") as f:
            contenu = json.load(f)
        self.assertEqual((contenu[0]["taille"], contenu[0]["resultat"], contenu[0]["relatif"]), (12, "livre", "é.csv"))
        self.assertRegex(contenu[0]["date_modification"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$")
        programmes.supprimer_listes(txt, js, os.path.join(self.travail, "absent"))
        self.assertEqual(os.listdir(self.travail), [])


# =========================================================================== #
class TestAvantLot(CasProgramme):
    def test_code_0_continue_et_recoit_la_liste(self):
        self.source("a.csv", b"AAA")
        self.source("b.csv", b"BB")
        copie = self.chemin("liste_recue.json")
        prog = self.programme(avant='import shutil; shutil.copy(os.environ["COPIE_LISTE_JSON"], %r)' % copie,
                              arguments=["{liste}"])
        bilan = self.lancer(self.regle(programmes={"avant_lot": prog}))
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 2))
        liste = json.load(open(copie, encoding="utf-8"))
        self.assertEqual(sorted(os.path.basename(e["chemin"]) for e in liste), ["a.csv", "b.csv"])
        self.assertEqual(sorted(e["taille"] for e in liste), [2, 3])
        (appel,) = self.lus()
        self.assertTrue(appel["argv"][0].endswith("liste_%s_avant_lot.txt" % self.b.derniere_execution(self.no(self.regle()))["id"])
                        or appel["argv"][0].endswith("_avant_lot.txt"))
        self.assertEqual(appel["env"]["COPIE_REGLE"], "r1")
        self.assertEqual(appel["env"]["COPIE_POINT_APPEL"], "avant_lot")
        self.assertEqual(appel["env"]["COPIE_MODE"], "copie")
        self.assertEqual(appel["env"]["COPIE_SIMULATION"], "0")
        self.assertEqual(os.path.normcase(appel["cwd"]), os.path.normcase(self.chemin("travail")))
        self.assertEqual(os.listdir(self.chemin("travail")), [])           # listes supprimees ensuite

    def test_code_1_rien_a_faire_sans_erreur(self):
        self.source("a.csv")
        bilan = self.lancer(self.regle(programmes={"avant_lot": self.programme(code=1)}))
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 0))
        self.assertEqual(bilan.motif, "avant_lot : rien a faire")
        self.assertEqual(self.livres(), [])
        self.assertEqual(self.etats(), [])

    def test_autre_code_arrete_la_regle_en_erreur(self):
        self.source("a.csv")
        bilan = self.lancer(self.regle(programmes={"avant_lot": self.programme(code=2)}))
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "programme_avant_lot"))
        self.assertEqual(self.livres(), [])
        self.assertIn("code retour 2", bilan.motif)
        evenement = self.evenements_programme("avant_lot")[0]
        self.assertEqual((evenement["code"], evenement["niveau"]), (2, "WARNING"))

    def test_lancement_impossible_et_duree_depassee(self):
        self.source("a.csv")
        inconnu = {"commande": [self.chemin("introuvable.exe")], "timeout_sec": 5}
        bilan = self.lancer(self.regle(programmes={"avant_lot": inconnu}))
        self.assertEqual(bilan.situation_finale, "programme_avant_lot")
        self.assertIn("lancement impossible", bilan.motif)
        lent = self.programme(avant="time.sleep(60)", timeout_sec=1)
        bilan = self.lancer(self.regle(id="r2", cible=self.chemin("d2"), programmes={"avant_lot": lent}))
        self.assertEqual(bilan.situation_finale, "programme_avant_lot")
        self.assertIn("duree maximale depassee", bilan.motif)

    def test_la_source_est_relue_apres_le_programme(self):
        self.source("a.csv", b"A")
        prog = self.programme(avant='open(os.path.join(%r, "ajout.csv"), "wb").write(b"nouveau")' % self.src
                              + "\nimport os as _o; t = time.time() - 600; _o.utime(os.path.join(%r, 'ajout.csv'), (t, t))" % self.src)
        bilan = self.lancer(self.regle(selection={"age_minimum_sec": 0}, programmes={"avant_lot": prog}))
        self.assertEqual(self.livres(), ["a.csv", "ajout.csv"])           # le fichier ajoute par le programme est livre
        self.assertEqual(bilan.compteurs["livres"], 2)

    def test_le_programme_peut_vider_la_source(self):
        a = self.source("a.csv")
        prog = self.programme(avant="os.remove(%r)" % a)
        bilan = self.lancer(self.regle(programmes={"avant_lot": prog}))
        self.assertEqual((bilan.statut, self.livres()), ("SUCCES", []))   # aucun_fichier : information par defaut

    def test_pas_appele_quand_il_n_y_a_rien_a_livrer(self):
        self.lancer(self.regle(programmes={"avant_lot": self.programme()}))
        self.assertEqual(self.lus(), [])

    def test_tentatives_avant_de_conclure(self):
        self.source("a.csv")
        compteur = self.chemin("essais.txt")
        prog = self.programme(avant='''
            n = int(open(%r).read()) if os.path.exists(%r) else 0
            open(%r, "w").write(str(n + 1))
            if n < 2: sys.exit(5)
            ''' % (compteur, compteur, compteur) + "\n")
        r = self.regle(programmes={"avant_lot": prog},
                       situations={"programme_avant_lot": {"tentatives": 3, "delai_sec": 7}})
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, self.pauses, len(self.lus())), ("SUCCES", [7, 7], 3))
        self.assertEqual(len(self.evenements("tentative_echouee")), 2)


class TestAvantFichier(CasProgramme):
    def test_appele_pour_chaque_fichier_avec_ses_variables(self):
        self.source(os.path.join("sous", "a.csv"), b"A")
        self.source("b.csv", b"B")
        prog = self.programme(arguments=["{fichier}", "{nom}", "{fichier_cible}"])
        bilan = self.lancer(self.regle(selection={"recursif": True},
                                       programmes={"avant_fichier": prog}))
        self.assertEqual(bilan.compteurs["livres"], 2)
        appels = {os.path.basename(a["argv"][0]): a for a in self.lus()}
        self.assertEqual(set(appels), {"a.csv", "b.csv"})
        a = appels["a.csv"]
        self.assertEqual(a["argv"][1], "a.csv")
        self.assertEqual(os.path.normcase(a["argv"][2]), os.path.normcase(os.path.join(self.dst, "sous", "a.csv")))
        self.assertEqual(a["env"]["COPIE_FICHIER"], a["argv"][0])
        self.assertEqual(a["env"]["COPIE_FICHIER_CIBLE"], a["argv"][2])

    def test_nom_de_fichier_piege_arrive_intact(self):
        nom = "Facture & (copie) 'x' ; ^ %PATH% n°1.csv"
        self.source(nom, b"X")
        prog = self.programme(arguments=["{fichier}"])
        bilan = self.lancer(self.regle(programmes={"avant_fichier": prog}))
        self.assertEqual(bilan.statut, "SUCCES")
        (appel,) = self.lus()
        self.assertEqual(os.path.basename(appel["argv"][0]), nom)

    def test_code_1_ignore_le_fichier_sans_erreur_ni_trace(self):
        self.source("a.csv")
        prog = self.programme(code=1)
        r = self.regle(programmes={"avant_fichier": prog})
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"], bilan.compteurs["ignores"]), ("SUCCES", 0, 1))
        self.assertEqual((self.livres(), self.etats()), ([], []))
        self.lancer(r)
        self.assertEqual(len(self.lus()), 2)                  # sans trace en base : rappele au lancement suivant

    def test_autre_code_arrete_la_regle_par_defaut(self):
        for nom in ("a.csv", "b.csv"):
            self.source(nom)
        bilan = self.lancer(self.regle(programmes={"avant_fichier": self.programme(code=4)}))
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "programme_avant_fichier"))
        self.assertEqual((self.livres(), len(self.lus())), ([], 1))       # b.csv n'a pas ete traite
        self.assertEqual(self.etats(), [])

    def test_fichier_suivant(self):
        self.source("a.csv", b"A")
        self.source("b.csv", b"B")
        prog = self.programme(avant='sys.exit(4 if sys.argv[1].endswith("a.csv") else 0)', arguments=["{fichier}"])
        r = self.regle(programmes={"avant_fichier": prog},
                       situations={"programme_avant_fichier": {"suite": "fichier_suivant"}})
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, self.livres(), bilan.compteurs["erreurs"]), ("ERREUR", ["b.csv"], 1))

    def test_le_programme_modifie_la_source_sur_place_sans_boucle(self):
        """Decision : l'empreinte est calculee sur la taille et la date RELUES apres le programme."""
        self.source("a.csv", b"original")
        prog = self.programme(avant='open(sys.argv[1], "ab").write(b" + en-tete")', arguments=["{fichier}"])
        r = self.regle(programmes={"avant_fichier": prog})
        bilan = self.lancer(r)
        self.assertEqual(bilan.compteurs["livres"], 1)
        self.assertEqual(self.lire(os.path.join(self.dst, "a.csv")), b"original + en-tete")     # version modifiee livree
        self.assertEqual(len(self.evenements("fichier_modifie_par_programme")), 1)
        bilan = self.lancer(r)                                                                    # lancement suivant
        self.assertEqual((bilan.compteurs["livres"], bilan.compteurs["ignores"]), (0, 1))
        self.assertEqual(len(self.lus()), 1)                  # le fichier modifie n'est pas retraite : pas de boucle

    def test_fichier_disparu_apres_le_programme(self):
        self.source("a.csv")
        prog = self.programme(avant="os.remove(sys.argv[1])", arguments=["{fichier}"])
        bilan = self.lancer(self.regle(programmes={"avant_fichier": prog}))
        self.assertEqual((bilan.statut, bilan.compteurs["ignores"], bilan.compteurs["livres"]), ("SUCCES", 1, 0))


class TestApresFichier(CasProgramme):
    def test_appele_apres_la_livraison_et_avant_la_suppression(self):
        a = self.source("a.csv", b"contenu")
        constat = self.chemin("constat.json")
        prog = self.programme(avant=('json.dump({"original": os.path.exists(sys.argv[1]), "cible": os.path.exists(sys.argv[2]),'
                                     ' "taille_cible": os.path.getsize(sys.argv[2])}, open(%r, "w"))' % constat),
                              arguments=["{fichier}", "{fichier_cible}"])
        bilan = self.lancer(self.regle(mode="deplacement", programmes={"apres_fichier": prog}))
        self.assertEqual(bilan.statut, "SUCCES")
        self.assertEqual(json.load(open(constat)), {"original": True, "cible": True, "taille_cible": 7})
        self.assertFalse(os.path.exists(a))                                     # supprime ensuite
        self.assertEqual(self.etats(), [modele_base.TERMINE])

    def test_echec_conserve_l_original(self):
        a = self.source("a.csv")
        r = self.regle(mode="deplacement", programmes={"apres_fichier": self.programme(code=7)})
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "programme_apres_fichier"))
        self.assertTrue(os.path.exists(a))                                      # ni supprime ni archive
        self.assertEqual(self.livres(), ["a.csv"])                              # mais livre
        self.assertEqual((self.etats(), self.b.actions(self.no(r))), ([modele_base.TERMINE], []))
        bilan = self.lancer(r)                                                  # aucune suppression tardive
        self.assertTrue(os.path.exists(a))
        self.assertEqual((bilan.compteurs["livres"], len(self.evenements("fichier_livre"))), (0, 1))

    def test_echec_en_mode_archivage_n_archive_pas(self):
        a = self.source("a.csv")
        r = self.regle(mode="archivage", archive=self.arch, programmes={"apres_fichier": self.programme(code=7)})
        self.lancer(r)
        self.assertTrue(os.path.exists(a))
        self.assertFalse(os.path.exists(self.arch) and os.listdir(self.arch))

    def test_codes_0_et_1_sont_acceptes(self):
        self.source("a.csv")
        self.source("b.csv")
        prog = self.programme(avant='sys.exit(1 if sys.argv[1].endswith("b.csv") else 0)', arguments=["{fichier}"])
        bilan = self.lancer(self.regle(programmes={"apres_fichier": prog}))
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 2))

    def test_fichier_suivant_apres_un_echec(self):
        self.source("a.csv")
        self.source("b.csv")
        prog = self.programme(avant='sys.exit(7 if sys.argv[1].endswith("a.csv") else 0)', arguments=["{fichier}"])
        r = self.regle(mode="deplacement", programmes={"apres_fichier": prog},
                       situations={"programme_apres_fichier": {"suite": "fichier_suivant"}})
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"], bilan.compteurs["erreurs"]), ("ERREUR", 2, 1))
        self.assertEqual(sorted(os.listdir(self.src)), ["a.csv"])               # b supprime, a conserve


class TestApresLot(CasProgramme):
    def test_recoit_le_resultat_de_chaque_fichier_et_le_statut(self):
        self.source("a.csv", b"A")
        self.source("b.csv", b"B")
        copie = self.chemin("resultat.json")
        prog = self.programme(avant='import shutil; shutil.copy(os.environ["COPIE_LISTE_JSON"], %r)' % copie)
        self.ecrire("dst/b.csv", b"occupant")
        r = self.regle(si_existe_cible="ignorer", programmes={"apres_lot": prog})
        bilan = self.lancer(r)
        liste = {os.path.basename(e["chemin"]): e for e in json.load(open(copie, encoding="utf-8"))}
        self.assertEqual(liste["a.csv"]["resultat"], "livre")
        self.assertEqual(os.path.basename(liste["a.csv"]["cible"]), "a.csv")
        self.assertEqual(liste["b.csv"]["resultat"], "ignore")
        (appel,) = self.lus()
        self.assertEqual(appel["env"]["COPIE_STATUT"], "SUCCES")
        self.assertEqual(bilan.statut, "SUCCES")

    def test_le_statut_transmis_est_celui_du_lot(self):
        self.source("a.csv")
        self.source("futur.csv", age_sec=-7200)
        bilan = self.lancer(self.regle(programmes={"apres_lot": self.programme()}))
        self.assertEqual(bilan.statut, "WARNING")
        self.assertEqual(self.lus()[0]["env"]["COPIE_STATUT"], "WARNING")

    def test_pas_appele_sans_fichier_traite(self):
        self.lancer(self.regle(programmes={"apres_lot": self.programme()}))
        self.assertEqual(self.lus(), [])

    def test_echec_est_signale_au_niveau_de_la_situation_sans_arret(self):
        self.source("a.csv")
        r = self.regle(programmes={"apres_lot": self.programme(code=9)})
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.situation_finale, bilan.compteurs["livres"]), ("ERREUR", None, 1))
        self.assertEqual(bilan.erreur["situation"], "programme_apres_lot")
        self.assertEqual(self.livres(), ["a.csv"])                             # la livraison a bien eu lieu

    def test_avec_une_erreur_en_cours_de_lot(self):
        self.source("a.csv")
        self.source("b.csv")
        vraie = transfert.copier_verifier
        from unittest import mock

        def copie(src, *a, **k):
            if src.endswith("b.csv"):
                raise transfert.ErreurCible("disque plein")
            return vraie(src, *a, **k)
        copie_json = self.chemin("res.json")
        prog = self.programme(avant='import shutil; shutil.copy(os.environ["COPIE_LISTE_JSON"], %r)' % copie_json)
        with mock.patch.object(transfert, "copier_verifier", copie):
            self.lancer(self.regle(programmes={"apres_lot": prog},
                                   situations={"copie_echec": {"suite": "fichier_suivant", "tentatives": 1}}))
        liste = {os.path.basename(e["chemin"]): e for e in json.load(open(copie_json, encoding="utf-8"))}
        self.assertEqual((liste["a.csv"]["resultat"], liste["b.csv"]["resultat"]), ("livre", "erreur"))
        self.assertIn("disque plein", liste["b.csv"]["message"])
        self.assertEqual(self.lus()[0]["env"]["COPIE_STATUT"], "ERREUR")


class TestSurErreur(CasProgramme):
    def test_appele_quand_la_regle_s_arrete_en_erreur(self):
        r = self.regle(source=self.chemin("absente"), programmes={"sur_erreur": self.programme()},
                       situations={"source_inaccessible": {"tentatives": 1}})
        bilan = self.lancer(r)
        self.assertEqual(bilan.statut, "ERREUR")
        (appel,) = self.lus()
        env = appel["env"]
        self.assertEqual((env["COPIE_STATUT"], env["COPIE_SITUATION"], env["COPIE_POINT_APPEL"]),
                         ("ERREUR", "source_inaccessible", "sur_erreur"))
        self.assertIn("introuvable", env["COPIE_MESSAGE"].lower().replace("é", "e").replace("é", "e") + "introuvable")

    def test_pas_appele_en_cas_de_succes_ou_d_avertissement(self):
        self.source("a.csv")
        self.source("futur.csv", age_sec=-7200)
        self.lancer(self.regle(programmes={"sur_erreur": self.programme()}))
        self.assertEqual(self.lus(), [])

    def test_son_propre_echec_n_aggrave_rien(self):
        r = self.regle(source=self.chemin("absente"), programmes={"sur_erreur": self.programme(code=99)},
                       situations={"source_inaccessible": {"tentatives": 1}})
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.situation_finale), ("ERREUR", "source_inaccessible"))
        evenement = self.evenements_programme("sur_erreur")[0]
        self.assertEqual((evenement["code"], evenement["niveau"]), (99, "WARNING"))

    def test_appele_aussi_apres_une_erreur_de_programme(self):
        self.source("a.csv")
        r = self.regle(programmes={"avant_lot": self.programme(code=2), "sur_erreur": self.programme()})
        self.lancer(r)
        points = [a["env"]["COPIE_POINT_APPEL"] for a in self.lus()]
        self.assertEqual(points, ["avant_lot", "sur_erreur"])


class CasReprise(CasLancement):
    """Reprise : le declencheur de l'execution decide de l'appel du programme `reprise`."""

    def setUp(self):
        super().setUp()
        self.entete_travail = self.chemin("travail")
        self.appels = self.chemin("appels.log")

    def programme_reprise(self, code=0, verifie=None):
        verifie = verifie or self.src
        chemin = self.chemin("reprise.py")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent('''\
                import json, os, sys
                with open(%r, "a") as f:
                    f.write(json.dumps({"reprise": os.environ["COPIE_REPRISE"], "point": os.environ["COPIE_POINT_APPEL"],
                                        "existe": os.path.exists(%r)}) + "\\n")
                sys.exit(%s)
                ''') % (self.appels, verifie, code))
        return {"commande": [sys.executable, chemin], "timeout_sec": 30}

    def lus(self):
        if not os.path.exists(self.appels):
            return []
        with open(self.appels) as f:
            return [json.loads(l) for l in f]


class TestReprise(CasReprise):
    def test_appele_en_premier_seulement_pour_une_reprise(self):
        self.brute(programmes={"reprise": self.programme_reprise()}, mode="copie")
        self.fichier()
        self.heure(6, 0)
        self.lancer_env()
        self.heure(7, 0)
        self.lancer_env()                                       # execution planifiee : pas de programme de reprise
        self.assertEqual(self.lus(), [])
        self.b.poser_lancement_manuel("r1", "benoit")
        self.heure(7, 30)
        self.lancer_env()                                       # lancement manuel : pas de programme non plus
        self.assertEqual(self.lus(), [])
        self.b.poser_reprise("r1", "benoit", "retablie")
        self.heure(8, 0)
        self.lancer_env()
        (appel,) = self.lus()
        self.assertEqual((appel["reprise"], appel["point"]), ("1", "reprise"))
        self.assertEqual(self.b.derniere_execution(self.b.numero_regle("r1"))["declencheur"], "reprise")

    def test_echec_arrete_la_regle(self):
        self.brute(programmes={"reprise": self.programme_reprise(code=3)}, mode="copie")
        self.fichier()
        self.heure(6, 0)
        self.lancer_env()
        self.b.poser_reprise("r1", "benoit")
        self.heure(7, 30)
        r = self.lancer_env()
        etat = self.regle_base()
        self.assertEqual((etat["dernier_statut"], etat["derniere_erreur_situation"]), ("ERREUR", "programme_reprise"))
        self.assertEqual(os.listdir(self.src), ["a.csv"])
        self.assertEqual(os.path.exists(self.dst), False)         # rien n'a ete copie : le programme passe avant tout

    def test_appel_avant_les_controles_et_la_selection(self):
        self.brute(programmes={"reprise": self.programme_reprise(verifie=self.chemin("pas_encore"))},
                   source=self.chemin("pas_encore"))
        self.heure(6, 0)
        self.lancer_env()
        self.b.poser_reprise("r1", "benoit")
        self.heure(7, 30)
        self.lancer_env()
        (appel,) = self.lus()
        self.assertFalse(appel["existe"])                        # la source n'existait pas encore : nettoyage possible avant


class TestSimulationDesProgrammes(CasProgramme):
    def test_non_appeles_en_simulation(self):
        self.source("a.csv")
        r = self.regle(programmes={"avant_lot": self.programme(), "avant_fichier": self.programme(),
                                   "apres_fichier": self.programme(), "apres_lot": self.programme()})
        with modele_base.ouvrir(self.chemin_base, "production", lecture_seule=True) as ro:
            bilan = self.lancer(r, simulation=True, base=ro)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 1))
        self.assertEqual(self.lus(), [])

    def test_appeles_avec_simulation_programmes(self):
        self.source("a.csv")
        r = self.regle(programmes={"avant_lot": self.programme(), "apres_fichier": self.programme(),
                                   "apres_lot": self.programme()})
        from file_management import execution
        with modele_base.ouvrir(self.chemin_base, "production", lecture_seule=True) as ro:
            bilan = execution.lancer_regle(r, self.entete, ro, self.journal, simulation=True,
                                           simulation_programmes=True, maintenant=lambda: self.maintenant,
                                           dormir=self.pauses.append)
        self.assertEqual(bilan.statut, "SUCCES")
        self.assertEqual([a["env"]["COPIE_POINT_APPEL"] for a in self.lus()], ["avant_lot", "apres_fichier", "apres_lot"])
        self.assertTrue(all(a["env"]["COPIE_SIMULATION"] == "1" for a in self.lus()))
        self.assertFalse(os.path.exists(self.dst))               # rien n'est livre pour autant


class TestVariablesPourLesOutils(CasProgramme):
    """COPIE_DOSSIER_LOGS, COPIE_CODE_ENVIRONNEMENT et COPIE_DOSSIER_TRAVAIL : ce qu'il faut a un programme de
    outils/ pour ecrire dans le meme journal que la regle."""

    def test_dossier_de_journaux_code_d_environnement_et_dossier_de_travail(self):
        self.source("a.csv")
        self.entete.dossier_logs = self.chemin("logs")
        self.entete.code_environnement = "pprod"
        bilan = self.lancer(self.regle(programmes={"avant_lot": self.programme(), "apres_fichier": self.programme()}))
        self.assertEqual(bilan.statut, "SUCCES")
        for appel in self.lus():
            env = appel["env"]
            self.assertEqual(os.path.normcase(env["COPIE_DOSSIER_LOGS"]), os.path.normcase(self.chemin("logs")))
            self.assertEqual(env["COPIE_CODE_ENVIRONNEMENT"], "pprod")
            self.assertEqual(os.path.normcase(env["COPIE_DOSSIER_TRAVAIL"]), os.path.normcase(self.chemin("travail")))
            self.assertEqual(os.path.normcase(appel["cwd"]), os.path.normcase(env["COPIE_DOSSIER_TRAVAIL"]))

    def test_valeurs_vides_quand_l_entete_ne_les_donne_pas(self):
        self.source("a.csv")
        self.entete.dossier_logs = None
        self.entete.code_environnement = None
        self.lancer(self.regle(programmes={"avant_lot": self.programme()}))
        (appel,) = self.lus()
        self.assertEqual((appel["env"]["COPIE_DOSSIER_LOGS"], appel["env"]["COPIE_CODE_ENVIRONNEMENT"]), ("", ""))
        self.assertNotEqual(appel["env"]["COPIE_DOSSIER_TRAVAIL"], "")


class TestJournalDesProgrammes(CasProgramme):
    def test_evenement_programme_appele(self):
        self.source("a.csv")
        prog = self.programme(avant='print("bonjour é"); print("x" * 20000)', arguments=["{regle}"])
        self.lancer(self.regle(programmes={"avant_lot": prog}))
        (e,) = self.evenements_programme("avant_lot")
        self.assertEqual((e["code"], e["niveau"], e["point"], e["regle"]), (0, "INFO", "avant_lot", "r1"))
        self.assertIn("bonjour é", e["sortie"])
        self.assertLessEqual(len(e["sortie"]), 8192 + 40)
        self.assertEqual(e["commande"][-1], "r1")                 # variables remplacees dans la commande journalisee
        self.assertGreaterEqual(e["duree_ms"], 0)


class TestProgrammesEtOrchestrateur(CasLancement):
    def test_programme_dans_un_fils_reel(self):
        """Bout en bout : l'orchestrateur lance le fils, le fils lance le programme."""
        self.b.horloge = time.time
        self.maintenant = __import__("datetime").datetime.now()
        marque = self.chemin("marque.txt")
        script = self.chemin("p.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write("import os, sys\nopen(%r, 'w').write(str(os.getpid()) + ' ' + os.environ['COPIE_STATUT'])\n" % marque)
        self.brute(mode="copie", programmes={"apres_lot": {"commande": [sys.executable, script], "timeout_sec": 30}})
        ancien = self.ecrire("src/a.csv", b"contenu")
        os.utime(ancien, (time.time() - 600, time.time() - 600))
        p = self.parametrage()
        self.b.synchroniser_regles([(r.id, lancement.empreinte_regle(r)) for r in p.regles])
        self.b.poser_lancement_manuel("r1", "essai")
        r = lancement.lancer(p, self.b, self.journal)
        self.assertEqual((r.compteurs["SUCCES"], r.code_retour), (1, 0))
        pid_programme, statut = open(marque).read().split()
        self.assertEqual(statut, "SUCCES")
        self.assertNotIn(int(pid_programme), (os.getpid(), self.b.derniere_execution(self.b.numero_regle("r1"))["pid"]))


if __name__ == "__main__":
    unittest.main()
