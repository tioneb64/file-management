"""J1 : lecture et validation du parametrage. Un groupe de tests par code de validation."""
import contextlib
import copy
import io
import json
import os
import unittest

from file_management import __main__ as cli
from file_management.controles import verifier_fichier
from tests.outils import CasTemporaire

SUPPR = object()      # dans une modification : supprime le champ


def entete(**modif):
    e = {"version": 1, "environnement": "production", "base": "D:\\Copie\\production.db"}
    return fusion(e, modif)


def regle(**modif):
    r = {"id": "r1", "source": "D:\\src", "cible": "D:\\dst", "mode": "copie",
         "planification": {"type": "intervalle", "frequence_sec": 300, "debut": "05:00",
                           "fin": "19:00", "jours": "lun-ven"}}
    return fusion(r, modif)


def fusion(base, modif):
    base = copy.deepcopy(base)
    for cle, valeur in modif.items():
        if valeur is SUPPR:
            base.pop(cle, None)
        elif cle != "planification" and isinstance(valeur, dict) and isinstance(base.get(cle), dict):
            base[cle] = fusion(base[cle], valeur)
        else:
            base[cle] = valeur
    return base


class CasParametrage(CasTemporaire):
    def fichier(self, lignes, nom="production.jsonl", brut=None):
        chemin = self.chemin(nom)
        if brut is not None:
            octets = brut
        else:
            texte = "\n".join(l if isinstance(l, str) else json.dumps(l) for l in lignes) + "\n"
            octets = texte.encode("utf-8")
        with open(chemin, "wb") as f:
            f.write(octets)
        return chemin

    def verifier(self, regles, en_tete=None, periode=None, **kw):
        chemin = self.fichier([en_tete or entete()] + list(regles), **kw)
        return verifier_fichier(chemin, periode)

    def codes(self, regles, **kw):
        return self.verifier(regles, **kw)[1].codes()

    def assertCodes(self, regles, attendus, **kw):
        _, rapport = self.verifier(regles, **kw)
        self.assertEqual(sorted(rapport.codes()), sorted(attendus), rapport.en_texte())

    def assertAucun(self, regles, **kw):
        self.assertCodes(regles, [], **kw)


class TestFichier(CasParametrage):
    def test_fichier_valide_sans_aucun_diagnostic(self):
        self.assertAucun([regle(), regle(id="r2", cible="D:\\autre")])

    def test_valeurs_de_secours(self):
        p, rapport = self.verifier([regle()])
        r = p.regles[0]
        self.assertEqual((r.actif, r.identite, r.apres_erreur, r.si_duree_depassee,
                          r.si_cible_absente, r.duree_max_sec, r.retention_historique_jours),
                         (True, "version", "arreter", "erreur", "ignorer", 1800, 90))
        self.assertEqual(r.situations["fichier_verrouille"].tentatives, 5)
        self.assertEqual(r.situations["fichier_verrouille"].suite, "arreter_regle")
        self.assertEqual(r.situations["archive_inaccessible"].suite, "continuer_en_differe")
        self.assertIsNone(r.situations["aucun_fichier"].suite)
        self.assertEqual(r.selection.masque, "*")
        self.assertEqual(p.entete.dossier_logs, os.path.join("D:\\Copie", "logs"))

    def test_bom_crlf_lignes_vides(self):
        contenu = ("\ufeff" + json.dumps(entete()) + "\r\n\r\n" + json.dumps(regle()) + "\r\n\r\n")
        p, rapport = self.verifier([], brut=contenu.encode("utf-8"))
        self.assertTrue(rapport.ok, rapport.en_texte())
        self.assertEqual(p.regles[0].ligne, 3)

    def test_numero_de_ligne_physique(self):
        contenu = json.dumps(entete()) + "\n\n\n{pas du json\n"
        _, rapport = self.verifier([], brut=contenu.encode("utf-8"))
        self.assertEqual([(d.code, d.ligne) for d in rapport.diagnostics], [("E06", 4)])

    def test_exemple_complet_de_la_specification(self):
        export = {
            "id": "export_clients", "description": "Export clients", "actif": True,
            "source": "\\\\SRV-PROD01\\exports\\clients", "cible": "D:\\SFTP\\out\\clients",
            "mode": "archivage", "archive": ".\\archive\\{AAAA}-{MM}-{JJ}", "creer_dossiers": True,
            "dossier_temporaire": "D:\\SFTP\\tmp",
            "selection": {"masque": "*.xml;*.json", "exclure": "~*", "recursif": False,
                          "modifie_depuis": "TOUT", "age_minimum_sec": 60, "age_maximum_sec": None,
                          "taille_minimum_octets": 1, "ordre": "date_modification",
                          "limite_fichiers": None},
            "identite": "version", "retention_historique_jours": 90, "si_cible_absente": "ignorer",
            "si_existe_cible": "erreur", "si_existe_archive": "suffixe",
            "renommage_cible": "{nom}_{AAAA}{MM}{JJ}_{hh}{mm}{ss}{ext}", "renommage_archive": None,
            "planification": {"type": "intervalle", "frequence_sec": 300, "debut": "05:00",
                              "fin": "19:00", "jours": "lun-ven", "rattrapage_sec": None},
            "apres": [], "condition": ["succes"], "si_condition_non_remplie": "WARNING",
            "duree_max_sec": 1800, "si_duree_depassee": "erreur", "relances_max": 2,
            "apres_erreur": "arreter",
            "situations": {
                "aucun_fichier": {"tentatives": 1, "delai_sec": 0, "niveau_final": "INFO"},
                "fichier_verrouille": {"tentatives": 5, "delai_sec": 60, "niveau_final": "ERREUR",
                                       "suite": "arreter_regle"},
                "archive_inaccessible": {"tentatives": 3, "delai_sec": 30,
                                         "niveau_final": "WARNING", "suite": "continuer_en_differe"}},
            "programmes": {"avant_lot": None, "avant_fichier": None, "apres_fichier": None,
                           "apres_lot": None, "sur_erreur": None, "reprise": None}}
        simples = [regle(id=i, cible="D:\\sortie\\" + i) for i in ("export_produits", "export_tarifs")]
        catalogue = {
            "id": "import_catalogue", "actif": True, "source": "D:\\Echanges\\catalogue",
            "cible": "\\\\SRV-ERP01\\import\\catalogue", "mode": "deplacement",
            "selection": {"masque": "CATALOGUE_*.csv", "recursif": False,
                          "modifie_depuis": "TOUT", "age_minimum_sec": 30},
            "planification": {"type": "quotidien", "heure": "07:15", "jours": "tous",
                              "rattrapage_sec": 14400},
            "apres": ["export_clients", "export_produits", "export_tarifs"],
            "condition": ["succes", "fichiers"], "si_condition_non_remplie": "WARNING",
            "duree_max_sec": 3600, "si_duree_depassee": "erreur", "apres_erreur": "arreter",
            "situations": {"aucun_fichier": {"tentatives": 3, "delai_sec": 300,
                                             "niveau_final": "ERREUR"}}}
        p, rapport = self.verifier([export] + simples + [catalogue])
        self.assertEqual(rapport.codes(), [], rapport.en_texte())
        self.assertEqual(len(p.regles), 4)


class TestVolume(CasParametrage):
    def test_deux_mille_regles_en_quelques_secondes(self):
        import time
        regles = [regle(id="r%d" % i, source="D:\\s%d" % i, cible="D:\\c%d" % i) for i in range(2000)]
        debut = time.time()
        self.assertAucun(regles)
        self.assertLess(time.time() - debut, 10)

    def test_beaucoup_de_regles_sur_la_meme_cible(self):
        regles = [regle(id="r%d" % i, source="D:\\s%d" % i) for i in range(150)]
        _, rapport = self.verifier(regles)
        self.assertEqual(rapport.codes().count("R11"), 150 * 149 // 2)


class TestEntete(CasParametrage):
    def test_e01(self):
        self.assertEqual(self.codes([], brut=b""), ["E01"])
        self.assertEqual(self.codes([], brut=b"pas du json\n"), ["E01"])
        _, rapport = verifier_fichier(self.fichier([regle()]))     # premiere ligne = une regle
        self.assertEqual(rapport.codes(), ["E01"])
        _, rapport = verifier_fichier(self.fichier([], brut=b"\xff\xfe\x00bad"))
        self.assertEqual(rapport.codes(), ["E01"])
        _, rapport = verifier_fichier(self.chemin("absent.jsonl"))
        self.assertEqual(rapport.codes(), ["E01"])

    def test_e02(self):
        for version in (2, "1", True, 1.0 + 1):
            self.assertEqual(self.codes([], en_tete=entete(version=version)), ["E02"], version)

    def test_e03(self):
        self.assertEqual(self.codes([], en_tete=entete(environnement="recette")), ["E03"])
        self.assertEqual(self.codes([], en_tete=entete(environnement="Production")), ["E03"])
        self.assertEqual(self.codes([], en_tete=entete(environnement="x" * 33)), ["E03"])
        self.assertEqual(self.codes([], en_tete=entete(environnement=SUPPR)), ["E03"])
        self.assertEqual(self.codes([], en_tete=entete(environnement="recette"),
                                    nom="recette.jsonl"), [])

    def test_e04(self):
        self.assertEqual(self.codes([], en_tete=entete(base=SUPPR)), ["E04"])
        self.assertEqual(self.codes([], en_tete=entete(base="  ")), ["E04"])

    def test_e05(self):
        self.assertEqual(self.codes([], en_tete=entete(base="\\\\SRV\\partage\\x.db")), ["E05"])
        self.assertEqual(self.codes([], en_tete=entete(base="//SRV/partage/x.db")), ["E05"])

    def test_e08(self):
        # code explicite hors de la liste de la plateforme
        self.assertEqual(self.codes([], en_tete=entete(code_environnement="production")), ["E08"])
        self.assertEqual(self.codes([], en_tete=entete(code_environnement="PROD")), ["E08"])
        # nom d'environnement dont le code ne se deduit pas : le code explicite est obligatoire
        self.assertEqual(self.codes([], en_tete=entete(environnement="essai"), nom="essai.jsonl"), ["E08"])
        self.assertEqual(self.codes([], en_tete=entete(environnement="essai", code_environnement="int"),
                                    nom="essai.jsonl"), [])

    def test_code_environnement_deduit_ou_explicite(self):
        for nom, attendu in (("production", "prod"), ("preprod", "pprod"), ("recette", "test"), ("dev", "dev"),
                             ("int", "int"), ("developpement", "dev")):
            p, rapport = self.verifier([], en_tete=entete(environnement=nom), nom=nom + ".jsonl")
            self.assertEqual((rapport.codes(), p.entete.code_environnement), ([], attendu), nom)
        p, _ = self.verifier([], en_tete=entete(code_environnement="build"))      # l'explicite l'emporte
        self.assertEqual(p.entete.code_environnement, "build")
        p, _ = self.verifier([], en_tete=entete(code_environnement=None))         # null = a deduire
        self.assertEqual(p.entete.code_environnement, "prod")

    def test_champs_optionnels_de_l_entete(self):
        e = entete(parallele_max=4, retention_executions_jours=30, marge_espace_mo=0,
                   dossier_logs="D:\\L", dossier_travail="D:\\T")
        p, rapport = self.verifier([], en_tete=e)
        self.assertEqual(rapport.codes(), [])
        self.assertEqual((p.entete.parallele_max, p.entete.dossier_logs), (4, "D:\\L"))
        self.assertEqual(self.codes([], en_tete=entete(parallele_max=0)), ["R07"])
        self.assertEqual(self.codes([], en_tete=entete(marge_espace_mo=-1)), ["R07"])
        self.assertEqual(self.codes([], en_tete=entete(inconnu=1)), ["E06"])


class TestE06(CasParametrage):
    def test_json_invalide_cite_la_ligne(self):
        chemin = self.fichier([entete(), "{casse", regle()])
        _, rapport = verifier_fichier(chemin)
        self.assertEqual([(d.code, d.ligne) for d in rapport.diagnostics], [("E06", 2)])

    def test_champ_inconnu(self):
        self.assertAucun([regle(description="ok")])
        self.assertCodes([regle(si_fichier_verouille="x")], ["E06"])
        self.assertCodes([regle(selection={"maske": "*"})], ["E06"])
        self.assertCodes([regle(planification={"type": "apres_dependances", "couleur": "bleu"})],
                         ["E06", "D06"])

    def test_mauvais_types(self):
        self.assertCodes([regle(actif="oui")], ["E06"])
        self.assertCodes([regle(duree_max_sec="1800")], ["E06"])
        self.assertCodes([regle(duree_max_sec=1.5)], ["E06"])
        self.assertCodes([regle(duree_max_sec=True)], ["E06"])
        self.assertCodes([regle(apres="r2")], ["E06"])
        self.assertCodes([regle(selection="*.csv")], ["E06"])
        self.assertIn("E06", self.codes([regle(source=3)]))

    def test_null_refuse_hors_champs_nullables(self):
        self.assertCodes([regle(actif=None)], ["E06"])
        self.assertAucun([regle(archive=None, dossier_temporaire=None,
                                selection={"age_minimum_sec": None})])

    def test_champ_present_deux_fois(self):
        ligne = '{"id": "r1", "id": "r2", "source": "a", "cible": "b", "mode": "copie"}'
        _, rapport = verifier_fichier(self.fichier([entete(), ligne]))
        self.assertEqual(rapport.codes(), ["E06"])

    def test_valeurs_non_finies(self):
        ligne = '{"id": "r1", "duree_max_sec": NaN}'
        _, rapport = verifier_fichier(self.fichier([entete(), ligne]))
        self.assertEqual(rapport.codes(), ["E06"])

    def test_ligne_qui_n_est_pas_un_objet(self):
        _, rapport = verifier_fichier(self.fichier([entete(), "[1, 2]"]))
        self.assertEqual(rapport.codes(), ["E06"])

    def test_situation_et_programme_inconnus(self):
        self.assertCodes([regle(situations={"fichier_perdu": {"tentatives": 1}})], ["E06"])
        self.assertCodes([regle(situations={"aucun_fichier": 3})], ["E06"])
        self.assertCodes([regle(programmes={"apres_midi": None})], ["E06"])
        self.assertCodes([regle(situations={"aucun_fichier": {"essais": 3}})], ["E06"])


class TestRegle(CasParametrage):
    def test_r01_champs_obligatoires(self):
        for champ in ("id", "source", "cible", "mode", "planification"):
            self.assertIn("R01", self.codes([regle(**{champ: SUPPR})]), champ)
        self.assertCodes([regle(source="  ")], ["R01"])

    def test_r02_id(self):
        for mauvais in ("a b", "é", "x" * 65, "", "a/b"):
            self.assertCodes([regle(id=mauvais)], ["R02"])
        self.assertCodes([regle(id="Export"), regle(id="EXPORT", cible="D:\\autre")], ["R02"])
        self.assertAucun([regle(id="a-b_C9" + "x" * 58)])

    def test_r03_source_cible(self):
        self.assertCodes([regle(source="D:\\a", cible="D:\\a")], ["R03"])
        self.assertCodes([regle(source="D:\\a", cible="d:\\A\\")], ["R03"])
        self.assertCodes([regle(source="D:\\a", cible="D:\\a\\sous",
                                selection={"recursif": True})], ["R03"])
        self.assertAucun([regle(source="D:\\a", cible="D:\\a\\sous")])           # non recursif
        self.assertAucun([regle(source="D:\\a", cible="D:\\ab", selection={"recursif": True})])

    def test_r03_variables_d_environnement(self):
        os.environ["COPIE_TEST_RACINE"] = "D:\\a"
        self.addCleanup(os.environ.pop, "COPIE_TEST_RACINE", None)
        variable = "%COPIE_TEST_RACINE%" if os.name == "nt" else "$COPIE_TEST_RACINE"
        self.assertCodes([regle(source=variable, cible="D:\\a")], ["R03"])

    def test_r04_r05_archive(self):
        self.assertCodes([regle(mode="archivage")], ["R04"])
        self.assertCodes([regle(mode="archivage", archive="  ")], ["R04"])
        self.assertAucun([regle(mode="archivage", archive=".\\archive")])
        self.assertCodes([regle(mode="copie", archive="D:\\arch")], ["R05"])
        self.assertCodes([regle(mode="deplacement", archive="D:\\arch")], ["R05"])
        self.assertTrue(self.verifier([regle(mode="copie", archive="D:\\arch")])[1].ok)

    def test_r06_valeurs_hors_liste(self):
        for modif in ({"mode": "teleportation"}, {"identite": "hash"}, {"si_cible_absente": "x"},
                      {"si_existe_cible": "x"}, {"si_existe_archive": "ecraser_tout"},
                      {"si_duree_depassee": "x"}, {"apres_erreur": "x"},
                      {"si_condition_non_remplie": "info"},
                      {"selection": {"ordre": "taille"}},
                      {"selection": {"modifie_depuis": "hier"}},
                      {"selection": {"modifie_depuis": "J-"}},
                      {"situations": {"aucun_fichier": {"niveau_final": "FATAL"}}}):
            self.assertCodes([regle(**modif)], ["R06"])

    def test_r06_suite_autorisee_selon_la_situation(self):
        self.assertCodes([regle(situations={"source_inaccessible": {"suite": "fichier_suivant"}})],
                         ["R06"])
        self.assertCodes([regle(situations={"aucun_fichier": {"suite": "arreter_regle"}})], ["R06"])
        self.assertCodes([regle(situations={"source_modifiee": {"suite": "arreter_regle"}})], ["R06"])
        self.assertAucun([regle(situations={"fichier_verrouille": {"suite": "fichier_suivant"},
                                            "archive_inaccessible": {"suite": "arreter_regle"}})])

    def test_modifie_depuis_insensible_a_la_casse(self):
        p, rapport = self.verifier([regle(selection={"modifie_depuis": "j-3"})])
        self.assertEqual(rapport.codes(), [])
        self.assertEqual(p.regles[0].selection.modifie_depuis, "J-3")

    def test_r07_bornes(self):
        for modif in ({"situations": {"copie_echec": {"tentatives": 0}}},
                      {"situations": {"copie_echec": {"delai_sec": -1}}},
                      {"selection": {"age_minimum_sec": -1}},
                      {"selection": {"age_maximum_sec": 0}},
                      {"selection": {"age_minimum_sec": 60, "age_maximum_sec": 60}},
                      {"selection": {"age_minimum_sec": 120, "age_maximum_sec": 60}},
                      {"selection": {"limite_fichiers": 0}},
                      {"selection": {"taille_minimum_octets": -1}},
                      {"duree_max_sec": 0}, {"relances_max": -1},
                      {"retention_historique_jours": 0}):
            self.assertCodes([regle(**modif)], ["R07"])
        self.assertAucun([regle(selection={"age_minimum_sec": 0, "age_maximum_sec": 3600,
                                           "limite_fichiers": 1, "taille_minimum_octets": 0},
                                relances_max=0)])

    def test_r08_retention_et_fenetre(self):
        self.assertCodes([regle(retention_historique_jours=7, selection={"modifie_depuis": "J-7"})],
                         ["R08"])
        self.assertCodes([regle(retention_historique_jours=8, selection={"modifie_depuis": "J-7"})],
                         ["R08"])             # J-7 = 7 jours en arriere + aujourd'hui = 8 jours
        self.assertAucun([regle(retention_historique_jours=9, selection={"modifie_depuis": "J-7"})])
        self.assertCodes([regle(retention_historique_jours=1, selection={"modifie_depuis": "J"})],
                         ["R08"])
        self.assertCodes([regle(retention_historique_jours=2,
                                selection={"age_maximum_sec": 3 * 86400})], ["R08"])
        self.assertAucun([regle(retention_historique_jours=1)])               # TOUT : pas de fenetre
        self.assertAucun([regle(selection={"modifie_depuis": "J-30"})])       # 90 > 31

    def test_r09_duree_inferieure_aux_attentes(self):
        self.assertCodes([regle(duree_max_sec=100)], ["R09"])
        self.assertAucun([regle(duree_max_sec=1800)])
        long = {"fichier_verrouille": {"tentatives": 10, "delai_sec": 600}}
        self.assertCodes([regle(situations=long, duree_max_sec=1800)], ["R09"])
        self.assertTrue(self.verifier([regle(duree_max_sec=100)])[1].ok)

    def test_r10_doublon(self):
        self.assertCodes([regle(), regle(id="r2")], ["R10", "R11"])
        self.assertAucun([regle(), regle(id="r2", selection={"masque": "*.csv"})]
                         and [regle(), regle(id="r2", cible="D:\\autre")])
        self.assertCodes([regle(), regle(id="r2", selection={"masque": "*.csv"})], ["R11"])

    def test_r11_meme_cible(self):
        deux = [regle(), regle(id="r2", source="D:\\autre", apres=["r1"],
                               planification={"type": "apres_dependances"})]
        self.assertAucun(deux)
        sans_lien = [regle(), regle(id="r2", source="D:\\autre")]
        self.assertCodes(sans_lien, ["R11"])
        inactive = [regle(), regle(id="r2", source="D:\\autre", actif=False)]
        self.assertAucun(inactive)

    def test_r11_dependance_indirecte(self):
        a = regle(id="a", cible="D:\\x")
        b = regle(id="b", cible="D:\\y", apres=["a"], planification={"type": "apres_dependances"})
        c = regle(id="c", cible="D:\\x", source="D:\\autre", apres=["b"],
                  planification={"type": "apres_dependances"})
        self.assertAucun([a, b, c])

    def test_r12_variables(self):
        self.assertCodes([regle(mode="archivage", archive=".\\{AAAA}\\{nom}")], ["R12"])
        self.assertCodes([regle(renommage_cible="{nom}_{date}{ext}")], ["R12"])
        self.assertCodes([regle(renommage_archive="{nom")], ["R12"])
        self.assertAucun([regle(renommage_cible="{nom}_{AAAA}{MM}{JJ}_{hh}{mm}{ss}{ext}",
                                renommage_archive="{nom}{ext}",
                                mode="archivage", archive="D:\\a\\{AAAA}-{MM}")])
        self.assertTrue(self.verifier([regle(renommage_cible="{x}")])[1].ok)


class TestPlanification(CasParametrage):
    def test_p01_planifications_valides(self):
        for planif in ({"type": "intervalle", "frequence_sec": 60, "debut": "00:00", "fin": "23:59"},
                       {"type": "quotidien", "heure": "07:15", "jours": "tous", "rattrapage_sec": 3600},
                       {"type": "quotidien", "heure": "23:59", "jours": "lun,mer,ven"},
                       {"type": "quotidien", "heure": "00:00", "jours": "sam-dim"}):
            self.assertAucun([regle(planification=planif)])
        self.assertAucun([regle(id="a"), regle(id="b", cible="D:\\x", apres=["a"],
                                               planification={"type": "apres_dependances"})])

    def test_p01_planifications_invalides(self):
        i = {"type": "intervalle", "frequence_sec": 300, "debut": "05:00", "fin": "19:00"}
        q = {"type": "quotidien", "heure": "07:15"}
        self.assertIn("R01", self.codes([regle(planification={"frequence_sec": 60})]))   # type absent
        for planif in ({"type": "hebdomadaire"},
                       dict(i, debut="5h"), dict(i, fin="24:00"), dict(i, debut="19:00"),
                       dict(i, debut="20:00"), dict(i, jours="lundi"), dict(i, jours="ven-lun"),
                       dict(i, jours="lun-"), {k: v for k, v in i.items() if k != "frequence_sec"},
                       {k: v for k, v in i.items() if k != "debut"},
                       dict(q, heure="7:15"), {"type": "quotidien"}, dict(q, jours="")):
            self.assertIn("P01", self.codes([regle(planification=planif)]), planif)

    def test_p01_frequence_zero_est_une_borne(self):
        self.assertCodes([regle(planification={"type": "intervalle", "frequence_sec": 0,
                                               "debut": "05:00", "fin": "19:00"})], ["R07"])

    def test_p02_periode_du_declencheur(self):
        self.assertAucun([regle()])
        self.assertAucun([regle()], periode=300)
        self.assertAucun([regle()], periode=60)
        self.assertCodes([regle()], ["P02"], periode=600)
        self.assertCodes([regle(planification={"type": "quotidien", "heure": "07:00"})], [],
                         periode=600)


class TestDependances(CasParametrage):
    def apres(self, ident, *refs, **modif):
        return regle(id=ident, cible="D:\\" + ident, apres=list(refs),
                     planification={"type": "apres_dependances"}, **modif)

    def test_chaine_valide(self):
        self.assertAucun([regle(id="a", cible="D:\\a"), self.apres("b", "a"), self.apres("c", "b", "a")])

    def test_d01_reference_inconnue(self):
        self.assertCodes([regle(), self.apres("b", "fantome")], ["D01"])
        self.assertCodes([regle(id="Export", cible="D:\\x"), self.apres("b", "export")], ["D01"])

    def test_d02_boucles(self):
        self.assertCodes([self.apres("a", "b"), self.apres("b", "a")], ["D02"])
        self.assertCodes([self.apres("a", "a")], ["D02"])
        self.assertCodes([self.apres("a", "c"), self.apres("b", "a"), self.apres("c", "b")], ["D02"])
        _, rapport = self.verifier([self.apres("a", "b"), self.apres("b", "a")])
        self.assertIn("a -> b -> a", rapport.diagnostics[0].message)

    def test_d02_deux_boucles_separees(self):
        regles = [self.apres("a", "b"), self.apres("b", "a"), self.apres("c", "d"), self.apres("d", "c")]
        self.assertCodes(regles, ["D02", "D02"])

    def test_d03_active_depend_d_une_inactive(self):
        a = regle(id="a", cible="D:\\a", actif=False)
        self.assertCodes([a, self.apres("b", "a")], ["D03"])
        self.assertAucun([a, self.apres("b", "a", actif=False)])
        self.assertAucun([regle(id="a", cible="D:\\a"), self.apres("b", "a", actif=False)])

    def test_d04_demarre_avant_sa_dependance(self):
        a = regle(id="a", cible="D:\\a", planification={"type": "quotidien", "heure": "07:00"})
        b = regle(id="b", cible="D:\\b", apres=["a"],
                  planification={"type": "quotidien", "heure": "06:00"})
        self.assertCodes([a, b], ["D04"])
        b_apres = regle(id="b", cible="D:\\b", apres=["a"],
                        planification={"type": "quotidien", "heure": "07:30"})
        self.assertAucun([a, b_apres])
        a_weekend = regle(id="a", cible="D:\\a",
                          planification={"type": "quotidien", "heure": "07:00", "jours": "sam-dim"})
        b_semaine = regle(id="b", cible="D:\\b", apres=["a"],
                          planification={"type": "quotidien", "heure": "06:00", "jours": "lun-ven"})
        self.assertAucun([a_weekend, b_semaine])           # jamais le meme jour

    def test_d05_plus_frequente_que_sa_dependance(self):
        a = regle(id="a", cible="D:\\a", planification={"type": "quotidien", "heure": "05:00"})
        b = regle(id="b", cible="D:\\b", apres=["a"],
                  planification={"type": "intervalle", "frequence_sec": 300, "debut": "06:00",
                                 "fin": "18:00"})
        self.assertCodes([a, b], ["D05"])
        lente = regle(id="a", cible="D:\\a", planification={"type": "intervalle", "frequence_sec": 60,
                                                            "debut": "05:00", "fin": "06:00"})
        self.assertAucun([lente, b])

    def test_d06_conditions(self):
        self.assertCodes([regle(), self.apres("b", "r1", condition=["succes", "magique"])], ["D06"])
        self.assertCodes([regle(id="a", planification={"type": "apres_dependances"})], ["D06"])
        self.assertCodes([regle(condition=["fichiers"])], ["D06"])
        self.assertAucun([regle(condition=["succes"], apres=[])])      # ecriture par defaut du front-end
        self.assertAucun([regle(), self.apres("b", "r1", condition=["termine", "fichiers"])])


class TestProgrammes(CasParametrage):
    def prog(self, **modif):
        p = {"commande": ["python", "D:\\Scripts\\notifier.py", "{regle}"], "timeout_sec": 60}
        return regle(programmes={"apres_lot": fusion(p, modif)})

    def test_programme_valide(self):
        p, rapport = self.verifier([self.prog()])
        self.assertEqual(rapport.codes(), [])
        self.assertEqual(p.regles[0].programmes["apres_lot"].commande[0], "python")
        self.assertEqual(p.regles[0].programmes["apres_lot"].timeout_sec, 60)
        self.assertIsNone(p.regles[0].programmes["reprise"])

    def test_variables_selon_le_point_d_appel(self):
        communes = ["environnement", "regle", "source", "cible", "archive", "date"]
        fichier, liste = ["fichier", "nom", "fichier_cible"], ["liste", "liste_json"]
        attendu = {"avant_lot": communes + liste, "avant_fichier": communes + fichier,
                   "apres_fichier": communes + fichier, "apres_lot": communes + liste,
                   "sur_erreur": communes + liste, "reprise": communes}
        for point, variables in attendu.items():
            commande = ["x"] + ["{%s}" % v for v in variables]
            self.assertAucun([regle(programmes={point: {"commande": commande, "timeout_sec": 5}})])

    def test_variable_sans_objet_a_ce_point_d_appel(self):
        for point, variable in (("avant_lot", "fichier"), ("apres_lot", "nom"), ("reprise", "liste"),
                                ("avant_fichier", "liste_json"), ("apres_fichier", "liste")):
            programme = {"commande": ["x", "{%s}" % variable], "timeout_sec": 5}
            _, rapport = self.verifier([regle(programmes={point: programme})])
            self.assertEqual(rapport.codes(), ["G01"], (point, variable))
            self.assertIn("sans objet", rapport.diagnostics[0].message)

    def test_g01(self):
        for modif in ({"commande": "python x.py"}, {"commande": []}, {"commande": [""]},
                      {"commande": [1, 2]}, {"commande": ["x", "{inconnue}"]},
                      {"timeout_sec": 0}, {"timeout_sec": -5}, {"timeout_sec": "60"},
                      {"timeout_sec": SUPPR}, {"commande": SUPPR}):
            self.assertCodes([self.prog(**modif)], ["G01"])

    def test_champ_inconnu_dans_un_programme(self):
        self.assertCodes([self.prog(shell=True)], ["E06"])

    def test_programme_non_objet(self):
        self.assertCodes([regle(programmes={"apres_lot": "x"})], ["E06"])


class TestCommande(CasParametrage):
    def lancer(self, *args):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(list(args))
        return code, sortie.getvalue()

    def test_codes_retour_et_json(self):
        bon = self.fichier([entete(), regle()])
        code, texte = self.lancer("--config", bon, "--verifier", "--syntaxe-seule", "--format", "json")
        self.assertEqual(code, 0)
        resultat = json.loads(texte)
        self.assertEqual((resultat["ok"], resultat["refus"], resultat["regles_lues"]), (True, [], 1))

        code, texte = self.lancer("--config", bon, "--verifier", "--syntaxe-seule",
                                  "--periode-declencheur-sec", "600", "--format", "json")
        self.assertEqual(code, 4)
        self.assertEqual(json.loads(texte)["avertissements"][0]["code"], "P02")

        mauvais = self.fichier([entete(), regle(mode="x")], nom="production.jsonl")
        code, texte = self.lancer("--config", mauvais, "--verifier", "--syntaxe-seule", "--format", "json")
        self.assertEqual(code, 2)
        refus = json.loads(texte)["refus"][0]
        self.assertEqual((refus["code"], refus["regle"], refus["ligne"]), ("R06", "r1", 2))

    def test_texte_lisible(self):
        mauvais = self.fichier([entete(), regle(id="a b")])
        code, texte = self.lancer("--config", mauvais, "--verifier", "--syntaxe-seule")
        self.assertEqual(code, 2)
        self.assertIn("R02", texte)
        self.assertIn("INVALIDE", texte)

    def test_controles_d_acces_sans_syntaxe_seule(self):
        bon = self.fichier([entete(), regle()])
        code, texte = self.lancer("--config", bon, "--verifier")
        self.assertEqual(code, 2)                          # base absente, dossiers inexistants : les acces sont controles
        self.assertIn("A05", texte)
        self.assertIn("A01", texte)

    def test_sans_verifier(self):
        bon = self.fichier([entete(), regle()])
        code, _ = self.lancer("--config", bon)
        self.assertEqual(code, 2)

    def test_accents_dans_la_sortie(self):
        bon = self.fichier([entete(), regle(description="Livraison é à ü")])
        code, _ = self.lancer("--config", bon, "--verifier", "--syntaxe-seule", "--format", "json")
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
