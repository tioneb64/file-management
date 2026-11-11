"""J5 : planification (creneaux, rattrapage, regle due, changement d'heure). Horloge simulee."""
import calendar
import copy
import datetime
import unittest

from file_management import planification
from file_management.diagnostic import Rapport
from file_management.parametrage import lire_regle

UTC = datetime.timezone.utc


def epoch_utc(annee, mois, jour, heure=0, minute=0, seconde=0):
    return calendar.timegm((annee, mois, jour, heure, minute, seconde))


class FuseauParis(object):
    """Fuseau fictif de la France en 2026 : heure d'ete du 29 mars 01:00 UTC au 25 octobre 01:00 UTC.
    Independant du fuseau de la machine qui execute les tests."""
    DEBUT_ETE = epoch_utc(2026, 3, 29, 1)
    FIN_ETE = epoch_utc(2026, 10, 25, 1)

    def decalage(self, instant):
        return 7200 if self.DEBUT_ETE <= instant < self.FIN_ETE else 3600

    def local(self, instant):
        mural = datetime.datetime.fromtimestamp(instant + self.decalage(instant), UTC).replace(tzinfo=None)
        if self.FIN_ETE + 0 <= instant < self.FIN_ETE + 3600:           # 2e passage de l'heure repetee
            mural = mural.replace(fold=1)
        return mural

    def epoch(self, mural):
        brut = calendar.timegm(mural.timetuple())
        ete, hiver = brut - 7200, brut - 3600
        valide_ete = self.decalage(ete) == 7200
        valide_hiver = self.decalage(hiver) == 3600
        if valide_ete and valide_hiver:          # heure repetee : premiere occurrence
            return ete
        if valide_ete:
            return ete
        if valide_hiver:
            return hiver
        return hiver                             # heure supprimee : l'instant qui suit


PARIS = FuseauParis()


def paris(annee, mois, jour, heure=0, minute=0, seconde=0):
    """Instant (secondes) d'une heure murale de Paris."""
    return PARIS.epoch(datetime.datetime(annee, mois, jour, heure, minute, seconde))


def regle(planification_, **autres):
    brut = {"id": "r1", "source": "D:\\s", "cible": "D:\\c", "mode": "copie", "planification": planification_}
    brut.update(autres)
    rapport = Rapport()
    r = lire_regle(copy.deepcopy(brut), 1, rapport)
    assert not rapport.refus, rapport.en_texte()
    return r


QUOTIDIEN = {"type": "quotidien", "heure": "07:15"}
TOUTES_LES_5_MIN = {"type": "intervalle", "frequence_sec": 300, "debut": "05:00", "fin": "19:00",
                    "jours": "lun-ven"}


def etat(**kw):
    base = {"en_cours": 0, "reprise": 0, "lancement_manuel": 0, "arret_apres_erreur": 0,
            "dernier_creneau": 1, "dernier_lancement": 1}
    base.update(kw)
    return base


class TestCreneaux(unittest.TestCase):
    def jours(self, planif):
        return regle(planif).planification

    def test_quotidien(self):
        p = self.jours({"type": "quotidien", "heure": "07:15"})
        self.assertEqual(planification.creneaux_du_jour(p, datetime.date(2026, 11, 3)), [7 * 3600 + 15 * 60])

    def test_intervalle_fin_incluse(self):
        p = self.jours(TOUTES_LES_5_MIN)
        creneaux = planification.creneaux_du_jour(p, datetime.date(2026, 11, 3))       # un mardi
        self.assertEqual((creneaux[0], creneaux[-1], len(creneaux)), (5 * 3600, 19 * 3600, 169))

    def test_intervalle_fin_hors_pas(self):
        p = self.jours({"type": "intervalle", "frequence_sec": 300, "debut": "05:00", "fin": "05:07"})
        self.assertEqual(planification.creneaux_du_jour(p, datetime.date(2026, 11, 3)), [18000, 18300])

    def test_jours_autorises(self):
        p = self.jours(TOUTES_LES_5_MIN)
        self.assertEqual(planification.creneaux_du_jour(p, datetime.date(2026, 11, 7)), [])      # samedi
        self.assertEqual(planification.creneaux_du_jour(p, datetime.date(2026, 11, 8)), [])      # dimanche
        self.assertNotEqual(planification.creneaux_du_jour(p, datetime.date(2026, 11, 6)), [])   # vendredi

    def test_dernier_creneau_echu(self):
        p = self.jours(TOUTES_LES_5_MIN)
        f = planification.dernier_creneau_echu
        self.assertEqual(f(p, paris(2026, 11, 3, 7, 0), PARIS), paris(2026, 11, 3, 7, 0))        # pile sur le creneau
        self.assertEqual(f(p, paris(2026, 11, 3, 7, 4, 59), PARIS), paris(2026, 11, 3, 7, 0))
        self.assertEqual(f(p, paris(2026, 11, 3, 7, 5), PARIS), paris(2026, 11, 3, 7, 5))
        self.assertEqual(f(p, paris(2026, 11, 3, 4, 59), PARIS), paris(2026, 11, 2, 19, 0))      # veille
        self.assertEqual(f(p, paris(2026, 11, 3, 23, 0), PARIS), paris(2026, 11, 3, 19, 0))      # apres la fin

    def test_le_week_end_est_saute(self):
        p = self.jours(TOUTES_LES_5_MIN)
        lundi_4h = paris(2026, 11, 9, 4, 0)
        self.assertEqual(planification.dernier_creneau_echu(p, lundi_4h, PARIS), paris(2026, 11, 6, 19, 0))
        self.assertEqual(planification.prochain_creneau(p, paris(2026, 11, 6, 19, 0), PARIS), paris(2026, 11, 9, 5, 0))

    def test_regle_hebdomadaire(self):
        p = self.jours({"type": "quotidien", "heure": "07:00", "jours": "lun"})
        dimanche = paris(2026, 11, 8, 12, 0)
        self.assertEqual(planification.dernier_creneau_echu(p, dimanche, PARIS), paris(2026, 11, 2, 7, 0))
        self.assertEqual(planification.prochain_creneau(p, dimanche, PARIS), paris(2026, 11, 9, 7, 0))

    def test_prochain_creneau(self):
        p = self.jours(QUOTIDIEN)
        self.assertEqual(planification.prochain_creneau(p, paris(2026, 11, 3, 7, 14), PARIS), paris(2026, 11, 3, 7, 15))
        self.assertEqual(planification.prochain_creneau(p, paris(2026, 11, 3, 7, 15), PARIS), paris(2026, 11, 4, 7, 15))

    def test_apres_dependances_n_a_pas_de_creneau(self):
        p = self.jours({"type": "apres_dependances"})
        self.assertIsNone(planification.dernier_creneau_echu(p, paris(2026, 11, 3, 7), PARIS))
        self.assertIsNone(planification.prochain_creneau(p, paris(2026, 11, 3, 7), PARIS))

    def test_libelles(self):
        self.assertEqual(planification.libelle(self.jours(TOUTES_LES_5_MIN)),
                         "toutes les 5 min de 05:00 a 19:00, lun-ven")
        self.assertEqual(planification.libelle(self.jours(QUOTIDIEN)), "a 07:15, tous les jours")
        self.assertEqual(planification.libelle(self.jours({"type": "quotidien", "heure": "07:00", "jours": "lun,mer"})),
                         "a 07:00, lun,mer")
        self.assertEqual(planification.libelle(self.jours({"type": "apres_dependances"})), "apres ses dependances")


class TestEvaluer(unittest.TestCase):
    def evaluer(self, r, etat_, maintenant):
        return planification.evaluer(r, etat_, maintenant, PARIS)

    def test_regle_inactive(self):
        d = self.evaluer(regle(QUOTIDIEN, actif=False), etat(), paris(2026, 11, 3, 8))
        self.assertEqual((d.due, d.motif), (False, "inactive"))

    def test_regle_nouvelle_son_dernier_creneau_est_considere_pris(self):
        r = regle(QUOTIDIEN)
        d = self.evaluer(r, None, paris(2026, 11, 3, 8))
        self.assertEqual((d.due, d.nouvelle, d.creneau), (False, True, paris(2026, 11, 3, 7, 15)))
        d = self.evaluer(r, etat(dernier_creneau=None, dernier_lancement=None), paris(2026, 11, 3, 8))
        self.assertTrue(d.nouvelle and not d.due)

    def test_regle_en_cours_jamais_relancee(self):
        d = self.evaluer(regle(QUOTIDIEN), etat(en_cours=1, reprise=1), paris(2026, 11, 3, 8))
        self.assertEqual((d.due, d.motif), (False, "deja en cours"))

    def test_creneau_echu_puis_pris(self):
        r = regle(QUOTIDIEN)
        veille = paris(2026, 11, 2, 7, 15)
        d = self.evaluer(r, etat(dernier_creneau=veille), paris(2026, 11, 3, 7, 14))
        self.assertFalse(d.due)                                        # le creneau n'est pas arrive
        d = self.evaluer(r, etat(dernier_creneau=veille), paris(2026, 11, 3, 7, 15))
        self.assertEqual((d.due, d.declencheur, d.creneau), (True, "planifie", paris(2026, 11, 3, 7, 15)))
        d = self.evaluer(r, etat(dernier_creneau=paris(2026, 11, 3, 7, 15)), paris(2026, 11, 3, 7, 20))
        self.assertEqual((d.due, d.motif), (False, "creneau deja pris"))

    def test_reprise_et_lancement_manuel_hors_creneau(self):
        r = regle(QUOTIDIEN)
        pris = etat(dernier_creneau=paris(2026, 11, 3, 7, 15))
        d = self.evaluer(r, dict(pris, reprise=1), paris(2026, 11, 3, 8))
        self.assertEqual((d.due, d.declencheur), (True, "reprise"))
        d = self.evaluer(r, dict(pris, lancement_manuel=1), paris(2026, 11, 3, 8))
        self.assertEqual((d.due, d.declencheur), (True, "manuel"))

    def test_arret_apres_erreur_bloque_les_creneaux_mais_pas_la_reprise(self):
        r = regle(TOUTES_LES_5_MIN)
        bloquee = etat(arret_apres_erreur=1, dernier_creneau=paris(2026, 11, 3, 7, 0))
        d = self.evaluer(r, bloquee, paris(2026, 11, 3, 7, 30))
        self.assertFalse(d.due)
        self.assertIn("reprise ou acquittement", d.motif)
        self.assertTrue(self.evaluer(r, dict(bloquee, reprise=1), paris(2026, 11, 3, 7, 30)).due)

    def test_regle_apres_dependances_sans_horaire(self):
        r = regle({"type": "apres_dependances"}, apres=["autre"])
        d = self.evaluer(r, etat(), paris(2026, 11, 3, 8))
        self.assertEqual((d.due, d.declencheur, d.creneau), (True, "dependance", None))     # l'evaluation des dependances decide
        d = self.evaluer(r, etat(dernier_creneau=None, dernier_lancement=None), paris(2026, 11, 3, 8))
        self.assertEqual((d.due, d.nouvelle), (True, False))                                  # ref = 0 : pas de regle "nouvelle"
        d = self.evaluer(r, etat(arret_apres_erreur=1), paris(2026, 11, 3, 8))
        self.assertFalse(d.due)

    def test_rattrapage(self):
        r = regle({"type": "quotidien", "heure": "07:15", "rattrapage_sec": 14400})
        veille = etat(dernier_creneau=paris(2026, 11, 2, 7, 15))
        self.assertTrue(self.evaluer(r, veille, paris(2026, 11, 3, 11, 15)).due)             # pile 4 h apres
        d = self.evaluer(r, veille, paris(2026, 11, 3, 11, 16))
        self.assertEqual(d.due, False)
        self.assertIn("expire", d.motif)
        self.assertFalse(self.evaluer(r, veille, paris(2026, 11, 3, 20)).due)

    def test_sans_rattrapage_le_creneau_reste_valable_jusqu_au_suivant(self):
        r = regle(QUOTIDIEN)
        veille = etat(dernier_creneau=paris(2026, 11, 2, 7, 15))
        self.assertTrue(self.evaluer(r, veille, paris(2026, 11, 3, 23, 59)).due)


def rejouer(r, debut, fin, pas=60, fuseau=PARIS, jenkins_arrete=()):
    """Simule des lancements toutes les `pas` secondes : renvoie les instants d'execution. L'etat
    evolue comme en base (creneau pris au demarrage). `jenkins_arrete` : intervalles sans lancement."""
    etat_ = etat(dernier_creneau=planification.dernier_creneau_echu(r.planification, debut - 1, fuseau),
                 dernier_lancement=1)
    executions = []
    for instant in range(debut, fin, pas):
        if any(a <= instant < b for a, b in jenkins_arrete):
            continue
        d = planification.evaluer(r, etat_, instant, fuseau)
        if d.due:
            etat_["dernier_creneau"] = d.creneau
            executions.append(instant)
    return executions


class TestSimulationDeLancements(unittest.TestCase):
    def test_une_regle_toutes_les_5_minutes_une_journee(self):
        r = regle(TOUTES_LES_5_MIN)
        executions = rejouer(r, paris(2026, 11, 3, 0), paris(2026, 11, 4, 0))
        self.assertEqual(len(executions), 169)
        self.assertEqual((executions[0], executions[-1]), (paris(2026, 11, 3, 5, 0), paris(2026, 11, 3, 19, 0)))

    def test_declencheur_irregulier(self):
        r = regle(TOUTES_LES_5_MIN)
        executions = rejouer(r, paris(2026, 11, 3, 6, 0), paris(2026, 11, 3, 7, 0), pas=420)    # toutes les 7 min
        self.assertEqual(len(executions), 9)                  # 9 passages, 9 creneaux differents, aucun double

    def test_jenkins_arrete_la_regle_part_une_seule_fois(self):
        r = regle(TOUTES_LES_5_MIN)
        arret = [(paris(2026, 11, 3, 8, 0), paris(2026, 11, 3, 10, 0))]
        executions = rejouer(r, paris(2026, 11, 3, 7, 0), paris(2026, 11, 3, 12, 0), jenkins_arrete=arret)
        apres = [e for e in executions if e >= paris(2026, 11, 3, 10, 0)]
        self.assertEqual(apres[0], paris(2026, 11, 3, 10, 0))
        self.assertEqual(apres[1], paris(2026, 11, 3, 10, 5))           # pas 24 rattrapages d'un coup
        self.assertEqual(len([e for e in executions if paris(2026, 11, 3, 8, 0) <= e < paris(2026, 11, 3, 10, 1)]), 1)

    def test_quotidien_avec_et_sans_rattrapage(self):
        arret = [(paris(2026, 11, 3, 6, 0), paris(2026, 11, 3, 13, 0))]
        sans = regle(QUOTIDIEN)
        self.assertEqual(rejouer(sans, paris(2026, 11, 3, 0), paris(2026, 11, 4, 0), jenkins_arrete=arret)[0],
                         paris(2026, 11, 3, 13, 0))
        avec = regle({"type": "quotidien", "heure": "07:15", "rattrapage_sec": 14400})
        self.assertEqual(rejouer(avec, paris(2026, 11, 3, 0), paris(2026, 11, 4, 0), jenkins_arrete=arret), [])

    def test_week_end_sans_execution(self):
        r = regle(TOUTES_LES_5_MIN)
        self.assertEqual(rejouer(r, paris(2026, 11, 7, 0), paris(2026, 11, 9, 0)), [])
        self.assertEqual(rejouer(r, paris(2026, 11, 9, 0), paris(2026, 11, 9, 5, 1))[-1], paris(2026, 11, 9, 5, 0))


class TestChangementDHeure(unittest.TestCase):
    def test_le_fuseau_de_test_est_correct(self):
        self.assertEqual(PARIS.epoch(datetime.datetime(2026, 11, 3, 12)), epoch_utc(2026, 11, 3, 11))
        self.assertEqual(PARIS.epoch(datetime.datetime(2026, 7, 1, 12)), epoch_utc(2026, 7, 1, 10))
        # heure supprimee : 02:30 le 29 mars n'existe pas, elle vaut 03:30 (heure d'ete)
        self.assertEqual(PARIS.epoch(datetime.datetime(2026, 3, 29, 2, 30)), epoch_utc(2026, 3, 29, 1, 30))
        # heure repetee : 02:30 le 25 octobre, premiere occurrence (heure d'ete)
        self.assertEqual(PARIS.epoch(datetime.datetime(2026, 10, 25, 2, 30)), epoch_utc(2026, 10, 25, 0, 30))

    def test_creneau_dans_l_heure_supprimee_execute_a_l_instant_suivant(self):
        r = regle({"type": "quotidien", "heure": "02:30"})
        executions = rejouer(r, paris(2026, 3, 28, 12), paris(2026, 3, 30, 12))
        # le 28 : 02:30 deja passe ; le 29 : 02:30 n'existe pas -> 03:30 ; le 30 : 02:30 normal
        self.assertEqual(executions, [epoch_utc(2026, 3, 29, 1, 30), paris(2026, 3, 30, 2, 30)])

    def test_heure_repetee_une_seule_execution(self):
        r = regle({"type": "quotidien", "heure": "02:30"})
        executions = rejouer(r, paris(2026, 10, 24, 12), paris(2026, 10, 26, 12))
        self.assertEqual(executions, [epoch_utc(2026, 10, 25, 0, 30), paris(2026, 10, 26, 2, 30)])

    def test_regle_horaire_23_executions_au_printemps_24_a_l_automne(self):
        toutes_les_heures = {"type": "intervalle", "frequence_sec": 3600, "debut": "00:00", "fin": "23:00"}
        r = regle(toutes_les_heures)
        printemps = rejouer(r, paris(2026, 3, 29, 0), paris(2026, 3, 30, 0), pas=60)
        automne = rejouer(r, paris(2026, 10, 25, 0), paris(2026, 10, 26, 0), pas=60)
        jour_normal = rejouer(r, paris(2026, 11, 3, 0), paris(2026, 11, 4, 0), pas=60)
        self.assertEqual((len(jour_normal), len(printemps), len(automne)), (24, 23, 24))
        # a l'automne, aucune execution pendant la 2e occurrence de 02:xx
        deuxieme_passage = (epoch_utc(2026, 10, 25, 1), epoch_utc(2026, 10, 25, 2))
        self.assertEqual([e for e in automne if deuxieme_passage[0] <= e < deuxieme_passage[1]], [])

    def test_regle_toutes_les_5_minutes_traverse_le_changement_d_heure(self):
        r = regle({"type": "intervalle", "frequence_sec": 300, "debut": "00:00", "fin": "23:55"})
        automne = rejouer(r, paris(2026, 10, 25, 0), paris(2026, 10, 26, 0), pas=60)
        self.assertEqual(len(automne), 288)                    # 24 h x 12 : l'heure repetee n'ajoute rien


if __name__ == "__main__":
    unittest.main()
