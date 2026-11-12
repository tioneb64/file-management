"""Plafond de volume (limite_octets), temoins de la source et de la cible, suspension d'un environnement."""
import copy
import json
import os
import unittest

from file_management import base as modele_base
from file_management import lancement, selection
from file_management.controles import verifier_fichier
from file_management.diagnostic import Rapport
from file_management.parametrage import lire_regle
from tests.test_lancement import CasLancement
from tests.test_moteur import CasMoteur


def _lire(**modif):
    brut = {"id": "r1", "source": "D:\\in", "cible": "D:\\out", "mode": "copie",
            "planification": {"type": "quotidien", "heure": "07:00"}}
    brut.update(modif)
    rapport = Rapport()
    return lire_regle(copy.deepcopy(brut), 1, rapport), rapport


def _codes(rapport):
    return sorted({d.code for d in rapport.refus + rapport.avertissements})


# =========================================================================== #
class TestLimiteOctets(CasMoteur):
    def test_le_lot_s_arrete_avant_de_depasser_le_volume_puis_la_suite_part_au_lancement_suivant(self):
        for nom in ("a.bin", "b.bin", "c.bin"):
            self.source(nom, b"x" * 100)
        r = self.regle(selection={"limite_octets": 250})
        bilan = self.lancer(r)
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 2))
        self.assertEqual(self.livres(), ["a.bin", "b.bin"])
        (e,) = self.evenements("limite_octets_atteinte")
        self.assertEqual((e["limite_octets"], e["octets"], e["retenus"], e["restants"]), (250, 200, 2, 1))
        bilan = self.lancer(r)
        self.assertEqual((bilan.compteurs["livres"], self.livres()), (1, ["a.bin", "b.bin", "c.bin"]))
        self.assertEqual(len(self.evenements("limite_octets_atteinte")), 1)          # plus rien a tronquer

    def test_le_premier_fichier_est_toujours_pris_meme_plus_gros_que_la_limite(self):
        self.source("a_gros.bin", b"x" * 1000)
        self.source("b_petit.bin", b"x" * 10)
        r = self.regle(selection={"limite_octets": 100})
        self.assertEqual(self.lancer(r).compteurs["livres"], 1)
        self.assertEqual(self.livres(), ["a_gros.bin"])            # le petit attend : l'ordre est respecte
        self.assertEqual(self.lancer(r).compteurs["livres"], 1)
        self.assertEqual(self.livres(), ["a_gros.bin", "b_petit.bin"])

    def test_un_seul_fichier_trop_gros_est_signale(self):
        self.source("gros.bin", b"x" * 1000)
        bilan = self.lancer(self.regle(selection={"limite_octets": 100}))
        self.assertEqual(bilan.compteurs["livres"], 1)
        (e,) = self.evenements("limite_octets_depassee")
        self.assertEqual((e["limite_octets"], e["taille"]), (100, 1000))

    def test_combinee_avec_limite_fichiers(self):
        for nom in ("a", "b", "c", "d"):
            self.source(nom + ".bin", b"x" * 100)
        bilan = self.lancer(self.regle(selection={"limite_fichiers": 3, "limite_octets": 250}))
        self.assertEqual(bilan.compteurs["livres"], 2)
        self.assertEqual(len(self.evenements("limite_atteinte")), 1)
        self.assertEqual(len(self.evenements("limite_octets_atteinte")), 1)

    def test_sans_limite_tout_part(self):
        for nom in ("a", "b", "c"):
            self.source(nom + ".bin", b"x" * 100)
        self.assertEqual(self.lancer(self.regle()).compteurs["livres"], 3)

    def test_mode_suppression(self):
        for nom in ("a", "b", "c"):
            self.source(nom + ".log", b"x" * 100)
        bilan = self.lancer(self.regle(mode="suppression", cible=None, selection={"limite_octets": 250}))
        self.assertEqual(bilan.compteurs["livres"], 2)
        self.assertEqual(sorted(os.listdir(self.src)), ["c.log"])

    def test_parametrage(self):
        r, rapport = _lire(selection={"limite_octets": 5000})
        self.assertEqual((r.selection.limite_octets, _codes(rapport)), (5000, []))
        for faux in (0, -1, "gros", 1.5):
            _, rapport = _lire(selection={"limite_octets": faux})
            self.assertTrue(rapport.refus, faux)


# =========================================================================== #
class TestFichierDeclencheur(CasMoteur):
    def temoin(self, nom="fin.ok"):
        return self.source(nom, b"", age_sec=60)

    def test_sans_temoin_la_regle_attend_et_ne_livre_rien(self):
        a = self.source("a.csv")
        bilan = self.lancer(self.regle(fichier_declencheur="*.ok"))
        self.assertEqual((bilan.statut, bilan.attente, bilan.compteurs["livres"]), ("SUCCES", True, 0))
        self.assertIn("en attente du fichier declencheur '*.ok'", bilan.motif)
        self.assertTrue(os.path.exists(a))
        self.assertFalse(os.path.exists(self.dst) and os.listdir(self.dst))
        self.assertEqual(len(self.evenements("declencheur_absent")), 1)

    def test_avec_temoin_les_fichiers_partent_sauf_le_temoin_qui_est_supprime(self):
        self.source("a.csv")
        self.source("b.csv")
        temoin = self.temoin()
        bilan = self.lancer(self.regle(fichier_declencheur="*.ok"))
        self.assertEqual((bilan.attente, bilan.compteurs["livres"]), (False, 2))
        self.assertEqual(self.livres(), ["a.csv", "b.csv"])          # le temoin n'est pas livre
        self.assertFalse(os.path.exists(temoin))
        self.assertEqual(len(self.evenements("declencheur_present")), 1)
        self.assertEqual(len(self.evenements("declencheur_consomme")), 1)

    def test_nom_exact_et_casse_ignoree(self):
        self.source("a.csv")
        temoin = self.temoin("FIN.OK")
        self.assertEqual(self.lancer(self.regle(fichier_declencheur="fin.ok")).compteurs["livres"], 1)
        self.assertFalse(os.path.exists(temoin))

    def test_temoin_conserve_si_consommer_declencheur_est_faux(self):
        self.source("a.csv")
        temoin = self.temoin()
        r = self.regle(fichier_declencheur="*.ok", consommer_declencheur=False)
        self.assertEqual(self.lancer(r).compteurs["livres"], 1)
        self.assertTrue(os.path.exists(temoin))
        self.source("b.csv")
        self.assertEqual(self.lancer(r).compteurs["livres"], 1)           # le nouveau fichier part aussitot

    def test_un_lot_tronque_par_une_limite_garde_son_temoin(self):
        for nom in ("a", "b", "c"):
            self.source(nom + ".csv")
        temoin = self.temoin()
        r = self.regle(fichier_declencheur="*.ok", selection={"limite_fichiers": 2})
        self.assertEqual(self.lancer(r).compteurs["livres"], 2)
        self.assertTrue(os.path.exists(temoin))                           # il reste un fichier du lot
        self.assertEqual(self.lancer(r).compteurs["livres"], 1)
        self.assertFalse(os.path.exists(temoin))                          # lot termine : temoin consomme

    def test_une_erreur_garde_le_temoin(self):
        self.source("a.csv")
        temoin = self.temoin()
        with open(self.dst, "wb") as f:                                   # la « cible » est un fichier : inaccessible
            f.write(b"x")
        bilan = self.lancer(self.regle(fichier_declencheur="*.ok"))
        self.assertEqual(bilan.statut, "ERREUR")
        self.assertTrue(os.path.exists(temoin))
        self.assertEqual(self.evenements("declencheur_consomme"), [])

    def test_le_temoin_d_un_sous_dossier_ne_compte_pas(self):
        self.source("a.csv")
        self.source(os.path.join("sous", "fin.ok"), b"")
        bilan = self.lancer(self.regle(fichier_declencheur="*.ok", selection={"recursif": True}))
        self.assertTrue(bilan.attente)

    def test_simulation_ne_supprime_pas_le_temoin(self):
        self.source("a.csv")
        temoin = self.temoin()
        r = self.regle(fichier_declencheur="*.ok")
        with modele_base.ouvrir(self.chemin_base, "production", lecture_seule=True) as ro:
            bilan = self.lancer(r, simulation=True, base=ro)
        self.assertEqual((bilan.attente, bilan.compteurs["livres"]), (False, 1))
        self.assertTrue(os.path.exists(temoin))

    def test_modes_count_et_suppression(self):
        for nom in ("a", "b"):
            self.source(nom + ".log")
        count = self.regle(mode="count", cible=None, fichier_declencheur="*.ok")
        self.assertTrue(self.lancer(count).attente)
        temoin = self.temoin()
        bilan = self.lancer(count)
        self.assertEqual((bilan.attente, bilan.motif), (False, "2 fichier(s)"))      # le temoin n'est pas compte
        self.assertFalse(os.path.exists(temoin))
        temoin = self.temoin()
        sup = self.regle(id="r2", mode="suppression", cible=None, fichier_declencheur="*.ok")
        self.assertEqual(self.lancer(sup).compteurs["livres"], 2)
        self.assertEqual(os.listdir(self.src), [])                         # temoin supprime aussi

    def test_une_regle_dependante_patiente_tant_que_le_temoin_manque(self):
        from file_management import dependances
        self.source("a.csv")
        amont = self.regle(id="amont", fichier_declencheur="*.ok")
        aval = self.regle(id="aval", cible=self.chemin("dst2"), apres=["amont"], condition=["succes"],
                          planification={"type": "apres_dependances"})
        self.lancer(amont)
        lignes = {l["id"].lower(): dict(l) for l in self.b.toutes_les_regles()}
        evaluation = dependances.evaluer(aval, lignes.get("aval"), lignes, self.b)
        self.assertEqual(evaluation.etat, dependances.EN_ATTENTE)
        self.temoin()
        self.maintenant = self.maintenant + __import__("datetime").timedelta(seconds=5)
        self.lancer(amont)
        lignes = {l["id"].lower(): dict(l) for l in self.b.toutes_les_regles()}
        self.assertEqual(dependances.evaluer(aval, lignes.get("aval"), lignes, self.b).etat, dependances.PRETE)

    def test_trouver_declencheurs(self):
        self.source("a.csv")
        self.temoin("x.OK")
        self.temoin("y.ok")
        trouves = selection.trouver_declencheurs(self.src, "*.ok")
        self.assertEqual([os.path.basename(t) for t in trouves], ["x.OK", "y.ok"])

    def test_parametrage(self):
        r, rapport = _lire(fichier_declencheur=" *.ok ")
        self.assertEqual((r.fichier_declencheur, r.consommer_declencheur, _codes(rapport)), ("*.ok", True, []))
        r, _ = _lire(fichier_declencheur="", consommer_declencheur=False)
        self.assertEqual((r.fichier_declencheur, r.consommer_declencheur), (None, False))
        for faux in ("sous\\fin.ok", "D:\\x\\fin.ok", "a/b.ok", "a.ok;b.ok"):
            r, rapport = _lire(fichier_declencheur=faux)
            self.assertEqual([d.code for d in rapport.refus], ["R06"], faux)
            self.assertIsNone(r.fichier_declencheur)
        _, rapport = _lire(consommer_declencheur="oui")
        self.assertTrue(rapport.refus)

    def test_synchro_ignore_le_declencheur_avec_un_avertissement(self):
        brut = {"id": "s", "mode": "synchro", "apres": ["a"], "planification": {"type": "apres_dependances"},
                "fichier_declencheur": "*.ok"}
        rapport = Rapport()
        lire_regle(brut, 1, rapport)
        self.assertEqual([d.code for d in rapport.avertissements], ["R16"])
        self.assertIn("fichier_declencheur", rapport.avertissements[0].message)


# =========================================================================== #
class TestTemoinCible(CasMoteur):
    def contenu_cible(self):
        return sorted(f for f in os.listdir(self.dst) if not f.endswith(selection.SUFFIXE_TEMPORAIRE))             if os.path.isdir(self.dst) else []

    def test_le_temoin_est_depose_apres_le_lot(self):
        self.source("a.csv")
        self.source("b.csv")
        bilan = self.lancer(self.regle(temoin_cible="fin.ok"))
        self.assertEqual((bilan.statut, bilan.compteurs["livres"]), ("SUCCES", 2))
        self.assertEqual(self.contenu_cible(), ["a.csv", "b.csv", "fin.ok"])
        self.assertEqual(os.path.getsize(os.path.join(self.dst, "fin.ok")), 0)
        self.assertFalse([f for f in os.listdir(self.dst) if f.endswith(selection.SUFFIXE_TEMPORAIRE)])
        (e,) = self.evenements("temoin_cible_depose")
        self.assertEqual(e["livres"], 2)

    def test_rien_a_livrer_pas_de_temoin(self):
        self.source("a.csv")
        r = self.regle(temoin_cible="fin.ok")
        self.lancer(r)
        os.remove(os.path.join(self.dst, "fin.ok"))                      # le destinataire l'a consomme
        self.lancer(r)                                                   # rien de nouveau
        self.assertEqual(self.contenu_cible(), ["a.csv"])
        self.assertEqual(len(self.evenements("temoin_cible_depose")), 1)

    def test_un_temoin_non_consomme_est_retire_puis_redepose_pour_le_lot_suivant(self):
        self.source("a.csv")
        r = self.regle(temoin_cible="fin.ok")
        self.lancer(r)
        self.source("b.csv")
        self.lancer(r)
        self.assertEqual(self.contenu_cible(), ["a.csv", "b.csv", "fin.ok"])
        self.assertEqual(len(self.evenements("temoin_cible_retire")), 1)
        self.assertEqual(len(self.evenements("temoin_cible_depose")), 2)

    def test_un_lot_tronque_par_une_limite_a_son_temoin(self):
        for nom in ("a", "b", "c"):
            self.source(nom + ".csv")
        self.lancer(self.regle(temoin_cible="fin.ok", selection={"limite_fichiers": 2}))
        self.assertEqual(self.contenu_cible(), ["a.csv", "b.csv", "fin.ok"])

    def test_une_erreur_sur_un_fichier_pas_de_temoin(self):
        self.source("a.csv")
        self.source("b.csv")
        os.makedirs(self.dst)
        os.makedirs(os.path.join(self.dst, "b.csv"))                     # un dossier de meme nom : livraison impossible
        bilan = self.lancer(self.regle(temoin_cible="fin.ok", si_existe_cible="ecraser"))
        self.assertEqual(bilan.statut, "ERREUR")
        self.assertNotIn("fin.ok", self.contenu_cible())
        self.assertEqual(self.evenements("temoin_cible_depose"), [])

    def test_ecriture_impossible_arrete_la_regle_en_erreur(self):
        self.source("a.csv")
        os.makedirs(os.path.join(self.dst, "fin.ok"))                    # un dossier occupe le nom du temoin
        bilan = self.lancer(self.regle(temoin_cible="fin.ok"))
        self.assertEqual(bilan.statut, "ERREUR")
        self.assertEqual(self.livres(), ["a.csv"])                       # le fichier est livre
        self.assertEqual(self.evenements("temoin_cible_depose"), [])

    def test_mode_deplacement(self):
        a = self.source("a.csv")
        self.lancer(self.regle(mode="deplacement", temoin_cible="fin.ok"))
        self.assertFalse(os.path.exists(a))
        self.assertEqual(self.contenu_cible(), ["a.csv", "fin.ok"])

    def test_simulation_ne_depose_rien(self):
        self.source("a.csv")
        r = self.regle(temoin_cible="fin.ok")
        with modele_base.ouvrir(self.chemin_base, "production", lecture_seule=True) as ro:
            self.lancer(r, simulation=True, base=ro)
        self.assertEqual(self.contenu_cible(), [])
        self.assertEqual(self.evenements("temoin_cible_depose"), [])

    def test_avec_le_declencheur_de_la_source(self):
        self.source("a.csv")
        self.source("go.ok", b"", age_sec=60)
        self.lancer(self.regle(fichier_declencheur="*.ok", temoin_cible="fin.ok"))
        self.assertEqual(self.contenu_cible(), ["a.csv", "fin.ok"])
        self.assertEqual(os.listdir(self.src), ["a.csv"] if os.path.exists(os.path.join(self.src, "a.csv")) else [])

    def test_parametrage(self):
        r, rapport = _lire(temoin_cible=" fin.ok ")
        self.assertEqual((r.temoin_cible, _codes(rapport)), ("fin.ok", []))
        r, _ = _lire(temoin_cible="")
        self.assertIsNone(r.temoin_cible)
        for faux in ("sous\\fin.ok", "a/b.ok", "*.ok", "a.ok;b.ok", "fin?.ok"):
            r, rapport = _lire(temoin_cible=faux)
            self.assertEqual([d.code for d in rapport.refus], ["R06"], faux)
            self.assertIsNone(r.temoin_cible)
        _, rapport = _lire(mode="suppression", cible=None, temoin_cible="fin.ok")
        self.assertEqual([d.code for d in rapport.avertissements if d.code == "R16"], ["R16"])

    def test_synchro_ignore_le_temoin_avec_un_avertissement(self):
        brut = {"id": "s", "mode": "synchro", "apres": ["a"], "planification": {"type": "apres_dependances"},
                "temoin_cible": "fin.ok"}
        rapport = Rapport()
        lire_regle(brut, 1, rapport)
        self.assertEqual([d.code for d in rapport.avertissements], ["R16"])
        self.assertIn("temoin_cible", rapport.avertissements[0].message)


# =========================================================================== #
class TestSuspension(CasLancement):
    def lancer_suspendu(self, suspendu=True, **kw):
        p = self.parametrage()
        p.entete.suspendu = suspendu
        p.entete.motif_suspension = "maintenance du serveur" if suspendu else None
        kw.setdefault("direct", True)
        return p, lancement.lancer(p, self.b, self.journal, maintenant=self.ts,
                                   maintenant_dt=lambda: self.maintenant, dormir=self.pauses.append, **kw)

    def preparer(self):
        self.brute(mode="copie")
        self.fichier("a.csv")
        self.lancer_env()                  # 06:00 : la regle est nouvelle, elle demarrera au creneau de 07:00
        self.heure(7, 1)

    def test_rien_n_est_lance_et_le_code_retour_reste_0(self):
        self.preparer()
        _, r = self.lancer_suspendu()
        self.assertTrue(r.suspendu)
        self.assertEqual((r.code_retour, r.compteurs["lancees"], r.compteurs["regles"]), (0, 0, 0))
        self.assertEqual(self.livres(), [])
        (e,) = self.evenements("environnement_suspendu")
        self.assertEqual((e["niveau"], e["motif"]), ("INFO", "maintenance du serveur"))

    def test_la_reprise_relance_les_regles_normalement(self):
        self.preparer()
        self.lancer_suspendu()
        _, r = self.lancer_suspendu(suspendu=False)
        self.assertFalse(r.suspendu)
        self.assertEqual(self.livres(), ["a.csv"])

    def test_le_lancement_manuel_est_aussi_bloque(self):
        self.preparer()
        p = self.parametrage()
        self.b.synchroniser_regles([(x.id, lancement.empreinte_regle(x)) for x in p.regles])
        self.b.poser_lancement_manuel("r1", "essai")
        _, r = self.lancer_suspendu()
        self.assertEqual((r.suspendu, self.livres()), (True, []))
        self.assertTrue(self.b.regle(self.b.numero_regle("r1"))["lancement_manuel"])     # la demande reste en attente

    def test_la_simulation_reste_possible(self):
        self.preparer()
        _, r = self.lancer_suspendu(simulation=True)
        self.assertFalse(r.suspendu)
        self.assertEqual(r.compteurs["lancees"], 1)

    def test_etat_indique_la_suspension(self):
        self.preparer()
        p = self.parametrage()
        p.entete.suspendu, p.entete.motif_suspension = True, "maintenance"
        etat = lancement.etat(p, self.b)
        self.assertEqual((etat["suspendu"], etat["motif_suspension"]), (True, "maintenance"))
        self.assertIn("ENVIRONNEMENT SUSPENDU", lancement.etat_texte(etat))
        self.assertIn("(maintenance)", lancement.etat_texte(etat))
        p.entete.suspendu = False
        self.assertNotIn("SUSPENDU", lancement.etat_texte(lancement.etat(p, self.b)))

    def test_entete_et_information_a_la_verification(self):
        import tempfile
        dossier = tempfile.mkdtemp(prefix="copie_susp_")
        self.addCleanup(__import__("shutil").rmtree, dossier, True)
        chemin = os.path.join(dossier, "test.jsonl")
        entete = {"version": 1, "environnement": "test", "base": os.path.join(dossier, "b", "test.db"),
                  "suspendu": True, "motif_suspension": " migration du disque "}
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(json.dumps(entete) + "\n")
        p, rapport = verifier_fichier(chemin)
        self.assertEqual((p.entete.suspendu, p.entete.motif_suspension), (True, "migration du disque"))
        self.assertEqual(rapport.refus, [])
        (info,) = [d for d in rapport.diagnostics if d.code == "S01"]
        self.assertIn("migration du disque", info.message)
        entete["suspendu"] = "oui"
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(json.dumps(entete) + "\n")
        _, rapport = verifier_fichier(chemin)
        self.assertEqual([d.code for d in rapport.refus], ["E06"])


if __name__ == "__main__":
    unittest.main()
