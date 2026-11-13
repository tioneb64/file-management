"""Boite a outils : transfert SFTP (sftp_envoyer, sftp_recuperer), contre un serveur paramiko local en thread."""
import json
import os
import sys
import time
import unittest
from unittest import mock

import paramiko

from outils.transfert import sftp_envoyer, sftp_recuperer
from tests.boite_outils import CasOutil
from tests.serveur_sftp import ServeurSftp, empreinte_de

def lire_fichier(chemin):
    with open(chemin, "rb") as f:
        return f.read()


MDP = "S3cret-Pass!"
PHRASE = "Phrase-Secrete-9"


class CasSftp(CasOutil):
    def setUp(self):
        super().setUp()
        self.distant = self.chemin("serveur")
        self.local = self.chemin("local")
        os.makedirs(self.local)
        self.serveur = ServeurSftp(self.distant, utilisateur="demo", mot_de_passe=MDP).demarrer()
        self.addCleanup(self.serveur.arreter)
        self.env["MDP_SFTP"] = MDP

    def base(self, empreinte=True, mdp=True):
        a = ["--hote", "127.0.0.1", "--port", self.serveur.port, "--utilisateur", "demo", "--pause", "0"]
        if mdp:
            a += ["--mot-de-passe-env", "MDP_SFTP"]
        if empreinte:
            a += ["--empreinte-hote", self.serveur.empreinte]
        return a

    def envoyer(self, *argv, **kw):
        return self.lancer(sftp_envoyer, *(self.base(**kw.pop("base", {})) + list(argv)), **kw)

    def recuperer(self, *argv, **kw):
        return self.lancer(sftp_recuperer, *(self.base(**kw.pop("base", {})) + list(argv)), **kw)

    def lire(self, *morceaux):
        with open(os.path.join(self.distant, *morceaux), "rb") as f:
            return f.read()

    def ecrire_distant(self, relatif, contenu=b"distant", age_secondes=None):
        chemin = os.path.join(self.distant, *relatif.split("/"))
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "wb") as f:
            f.write(contenu)
        if age_secondes is not None:
            t = time.time() - age_secondes
            os.utime(chemin, (t, t))
        return chemin

    def tout_le_texte(self):
        """Journal, sortie standard et sortie d'erreur : l'endroit ou un secret ne doit jamais apparaitre."""
        brut = ""
        for nom in os.listdir(self.logs):
            with open(os.path.join(self.logs, nom), encoding="utf-8") as f:
                brut += f.read()
        return brut + self.sortie + self.erreur


class TestEnvoi(CasSftp):
    def test_envoi_simple_sans_fichier_temporaire(self):
        fichier = self.ecrire("local/a.txt", b"bonjour")
        self.assertEqual(self.envoyer("--distant", "/depot", "--creer-dossiers", fichier), 0, self.erreur)
        self.assertEqual(self.lire("depot", "a.txt"), b"bonjour")
        self.assertEqual(os.listdir(os.path.join(self.distant, "depot")), ["a.txt"])      # pas de .tmp
        self.assertTrue(os.path.exists(fichier))                                          # conserve par defaut
        self.controler_journal("sftp_envoyer", statut="SUCCES")
        ligne = self.lignes("fichier_envoye")[0]
        self.assertEqual((ligne["distant"], ligne["taille"], ligne["verification"]), ("/depot/a.txt", 7, "taille"))

    def test_dossier_distant_absent_sans_creer_dossiers(self):
        fichier = self.ecrire("local/a.txt")
        self.assertEqual(self.envoyer("--distant", "/absent", fichier), 2)
        self.assertIn("dossier distant introuvable", self.erreur)

    def test_depot_d_un_dossier_recursif_et_filtre(self):
        self.ecrire("local/x.csv", b"1")
        self.ecrire("local/x.log", b"2")
        self.ecrire("local/sous/y.csv", b"3")
        os.makedirs(os.path.join(self.distant, "in"))
        code = self.envoyer("--distant", "/in", "--creer-dossiers", "-r", "--masque", "*.csv", self.chemin("local"))
        self.assertEqual(code, 0, self.erreur)
        self.assertEqual(self.lire("in", "sous", "y.csv"), b"3")
        self.assertEqual(sorted(os.listdir(os.path.join(self.distant, "in"))), ["sous", "x.csv"])

    def test_variable_fichier_du_moteur(self):
        fichier = self.ecrire("local/moteur.txt", b"m")
        os.makedirs(os.path.join(self.distant, "in"))
        self.assertEqual(self.envoyer("--distant", "/in", env={"COPIE_FICHIER": fichier}), 0, self.erreur)
        self.assertEqual(self.lire("in", "moteur.txt"), b"m")

    def test_jamais_d_ecrasement_sans_option(self):
        fichier = self.ecrire("local/a.txt", b"nouveau")
        self.ecrire_distant("in/a.txt", b"ancien")
        self.assertEqual(self.envoyer("--distant", "/in", fichier), 2)
        self.assertEqual(self.lire("in", "a.txt"), b"ancien")
        erreurs = [b for b in self.brutes() if b["level"] == "ERROR" and b["context"]["event"] != "outil_termine"]
        self.assertEqual(erreurs[0]["error"]["type"], "DUPLICATE_ENTITY")
        self.assertEqual(os.listdir(os.path.join(self.distant, "in")), ["a.txt"])          # rien laisse derriere

    def test_ecraser_remplace(self):
        fichier = self.ecrire("local/a.txt", b"nouveau")
        self.ecrire_distant("in/a.txt", b"ancien")
        self.assertEqual(self.envoyer("--distant", "/in", "--ecraser", fichier), 0, self.erreur)
        self.assertEqual(self.lire("in", "a.txt"), b"nouveau")

    def test_ignorer_existants(self):
        fichier = self.ecrire("local/a.txt", b"nouveau")
        autre = self.ecrire("local/b.txt", b"b")
        self.ecrire_distant("in/a.txt", b"ancien")
        self.assertEqual(self.envoyer("--distant", "/in", "--ignorer-existants", fichier, autre), 0, self.erreur)
        self.assertEqual(self.lire("in", "a.txt"), b"ancien")
        self.assertEqual(self.lire("in", "b.txt"), b"b")
        self.assertEqual(len(self.lignes("fichier_existant_ignore")), 1)

    def test_simulation_n_ecrit_rien(self):
        fichier = self.ecrire("local/a.txt", b"x")
        os.makedirs(os.path.join(self.distant, "in"))
        self.assertEqual(self.envoyer("--distant", "/in", "--simulation", "--apres-envoi", "supprimer", fichier), 0,
                         self.erreur)
        self.assertEqual(os.listdir(os.path.join(self.distant, "in")), [])
        self.assertTrue(os.path.exists(fichier))
        self.assertEqual(len(self.lignes("fichier_a_envoyer")), 1)
        self.controler_journal("sftp_envoyer", statut="SUCCES", simulation=True)

    def test_simulation_signale_un_conflit(self):
        fichier = self.ecrire("local/a.txt")
        self.ecrire_distant("in/a.txt")
        self.assertEqual(self.envoyer("--distant", "/in", "--simulation", fichier), 2)

    def test_verification_sha256(self):
        fichier = self.ecrire("local/a.bin", os.urandom(300000))
        os.makedirs(os.path.join(self.distant, "in"))
        self.assertEqual(self.envoyer("--distant", "/in", "--verification", "sha256", fichier), 0, self.erreur)
        self.assertEqual(len(self.lignes("fichier_envoye")[0]["sha256"]), 64)
        self.assertEqual(self.lire("in", "a.bin"), lire_fichier(fichier))

    def test_apres_envoi_supprimer(self):
        fichier = self.ecrire("local/a.txt")
        os.makedirs(os.path.join(self.distant, "in"))
        self.assertEqual(self.envoyer("--distant", "/in", "--apres-envoi", "supprimer", fichier), 0, self.erreur)
        self.assertFalse(os.path.exists(fichier))

    def test_apres_envoi_archiver_sans_ecraser_l_archive(self):
        os.makedirs(os.path.join(self.distant, "in"))
        archive = self.chemin("archive")
        self.ecrire("archive/a.txt", b"deja archive")
        fichier = self.ecrire("local/a.txt", b"nouveau")
        self.assertEqual(self.envoyer("--distant", "/in", "--apres-envoi", "archiver", "--archive-dossier", archive,
                                      fichier), 0, self.erreur)
        self.assertEqual(lire_fichier(os.path.join(archive, "a.txt")), b"deja archive")
        self.assertEqual(lire_fichier(os.path.join(archive, "a_2.txt")), b"nouveau")
        self.assertFalse(os.path.exists(fichier))

    def test_un_echec_n_archive_ni_ne_supprime(self):
        fichier = self.ecrire("local/a.txt")
        self.ecrire_distant("in/a.txt")
        self.assertEqual(self.envoyer("--distant", "/in", "--apres-envoi", "supprimer", fichier), 2)
        self.assertTrue(os.path.exists(fichier))

    def test_archiver_demande_un_dossier(self):
        self.assertEqual(self.envoyer("--distant", "/in", "--apres-envoi", "archiver", self.ecrire("local/a.txt")), 3)

    def test_rien_a_envoyer(self):
        os.makedirs(os.path.join(self.distant, "in"))
        self.assertEqual(self.envoyer("--distant", "/in", self.chemin("local", "*.zzz")), 0)
        self.assertIn("RIEN A FAIRE", self.sortie)


class TestReprise(CasSftp):
    def test_coupure_pendant_l_envoi_reprise_dans_la_meme_execution(self):
        contenu = os.urandom(3 * 1024 * 1024)
        fichier = self.ecrire("local/gros.bin", contenu)
        os.makedirs(os.path.join(self.distant, "in"))
        self.serveur.couper_ecriture_apres = 700000
        self.assertEqual(self.envoyer("--distant", "/in", "--tentatives", 3, "--verification", "sha256", fichier), 0,
                         self.erreur)
        self.assertEqual(self.lire("in", "gros.bin"), contenu)
        self.assertEqual(os.listdir(os.path.join(self.distant, "in")), ["gros.bin"])
        self.assertEqual(len(self.lignes("sftp_reprise")), 1)
        self.assertGreater(self.lignes("fichier_envoye")[0]["octets_repris"], 0)       # reprise, pas de depart a zero
        self.assertGreaterEqual(self.serveur.connexions, 2)
        self.controler_journal("sftp_envoyer", statut="WARNING")

    def test_coupure_sans_nouvel_essai_puis_reprise_a_l_execution_suivante(self):
        contenu = os.urandom(2 * 1024 * 1024)
        fichier = self.ecrire("local/gros.bin", contenu)
        os.makedirs(os.path.join(self.distant, "in"))
        self.serveur.couper_ecriture_apres = 600000
        self.assertEqual(self.envoyer("--distant", "/in", "--tentatives", 1, fichier), 2)
        self.assertFalse(os.path.exists(os.path.join(self.distant, "in", "gros.bin")))        # jamais visible incomplet
        self.assertTrue(os.path.exists(os.path.join(self.distant, "in", "gros.bin.tmp")))
        self.assertEqual(self.envoyer("--distant", "/in", fichier), 0, self.erreur)
        self.assertEqual(self.lire("in", "gros.bin"), contenu)
        self.assertGreater(self.lignes("fichier_envoye")[-1]["octets_repris"], 0)

    def test_temporaire_qui_n_est_pas_le_debut_du_fichier_est_ecrase(self):
        contenu = os.urandom(200000)
        fichier = self.ecrire("local/a.bin", contenu)
        self.ecrire_distant("in/a.bin.tmp", os.urandom(50000))
        self.assertEqual(self.envoyer("--distant", "/in", "--verification", "sha256", fichier), 0, self.erreur)
        self.assertEqual(self.lire("in", "a.bin"), contenu)
        self.assertNotIn("octets_repris", self.lignes("fichier_envoye")[0])

    def test_coupure_pendant_la_recuperation(self):
        contenu = os.urandom(3 * 1024 * 1024)
        self.ecrire_distant("out/gros.bin", contenu)
        self.serveur.couper_lecture_apres = 800000
        recu = self.chemin("recu")
        self.assertEqual(self.recuperer("--distant", "/out", "--local", recu, "--verification", "sha256"), 0,
                         self.erreur)
        self.assertEqual(lire_fichier(os.path.join(recu, "gros.bin")), contenu)
        self.assertEqual(os.listdir(recu), ["gros.bin"])                         # pas de .copie_en_cours
        self.assertEqual(len(self.lignes("sftp_reprise")), 1)

    def test_serveur_injoignable_apres_toutes_les_tentatives(self):
        self.serveur.arreter()
        fichier = self.ecrire("local/a.txt")
        self.assertEqual(self.envoyer("--distant", "/in", "--tentatives", 2, "--delai", 2, fichier), 2)
        self.assertEqual(len(self.lignes("sftp_connexion_echouee")), 1)
        self.assertIn("connexion impossible", self.erreur)


class TestSecurite(CasSftp):
    def test_cle_d_hote_inconnue_refusee_par_defaut(self):
        fichier = self.ecrire("local/a.txt")
        vide = self.ecrire("known_hosts", b"")
        code = self.envoyer("--distant", "/in", "--known-hosts", vide, fichier, base={"empreinte": False})
        self.assertEqual(code, 2)
        self.assertIn("inconnue", self.erreur)
        self.assertIn(self.serveur.empreinte, self.erreur)                   # l'empreinte releve permet de la verifier
        self.assertEqual(self.serveur.tentatives_auth, 0)                    # refusee AVANT d'envoyer le mot de passe
        self.assertFalse(os.path.exists(os.path.join(self.distant, "in")))

    def test_hote_inconnu_accepte_avec_avertissement(self):
        fichier = self.ecrire("local/a.txt")
        os.makedirs(os.path.join(self.distant, "in"))
        vide = self.ecrire("known_hosts", b"")
        code = self.envoyer("--distant", "/in", "--known-hosts", vide, "--hote-inconnu", "accepter", fichier,
                            base={"empreinte": False})
        self.assertEqual(code, 0, self.erreur)
        self.assertEqual(self.lignes("hote_inconnu_accepte")[0]["empreinte"], self.serveur.empreinte)
        self.controler_journal("sftp_envoyer", statut="WARNING")

    def test_mauvaise_empreinte_refusee_meme_avec_accepter(self):
        fichier = self.ecrire("local/a.txt")
        fausse = empreinte_de(paramiko.ECDSAKey.generate())
        code = self.envoyer("--empreinte-hote", fausse, "--hote-inconnu", "accepter", "--distant", "/in", fichier,
                            base={"empreinte": False})
        self.assertEqual(code, 2)
        self.assertIn("differente", self.erreur)
        self.assertEqual(self.serveur.tentatives_auth, 0)

    def test_known_hosts_avec_la_bonne_cle(self):
        fichier = self.ecrire("local/a.txt")
        os.makedirs(os.path.join(self.distant, "in"))
        cle = self.serveur.cle_hote
        ligne = "[127.0.0.1]:%d %s %s\n" % (self.serveur.port, cle.get_name(), cle.get_base64())
        known = self.ecrire("known_hosts", ligne)
        self.assertEqual(self.envoyer("--distant", "/in", "--known-hosts", known, fichier, base={"empreinte": False}),
                         0, self.erreur)

    def test_known_hosts_avec_une_autre_cle_refuse_meme_avec_accepter(self):
        autre = paramiko.ECDSAKey.generate()
        ligne = "[127.0.0.1]:%d %s %s\n" % (self.serveur.port, autre.get_name(), autre.get_base64())
        known = self.ecrire("known_hosts", ligne)
        fichier = self.ecrire("local/a.txt")
        code = self.envoyer("--distant", "/in", "--known-hosts", known, "--hote-inconnu", "accepter", fichier,
                            base={"empreinte": False})
        self.assertEqual(code, 2)
        self.assertIn("differe", self.erreur)

    def test_empreinte_et_known_hosts_sont_exclusifs(self):
        known = self.ecrire("known_hosts", b"")
        self.assertEqual(self.envoyer("--distant", "/in", "--known-hosts", known, self.ecrire("local/a.txt")), 3)

    def test_authentification_refusee_jamais_rejouee(self):
        fichier = self.ecrire("local/a.txt")
        code = self.envoyer("--distant", "/in", "--tentatives", 5, fichier, env={"MDP_SFTP": "mauvais-mdp-X"})
        self.assertEqual(code, 2)
        self.assertEqual(self.serveur.tentatives_auth, 1)                    # une seule tentative : pas de verrouillage
        self.assertIn("authentification refusee", self.erreur)
        self.assertEqual(self.lignes("sftp_connexion_echouee"), [])

    def test_aucun_secret_dans_le_journal_ni_les_sorties(self):
        fichier = self.ecrire("local/a.txt")
        os.makedirs(os.path.join(self.distant, "in"))
        self.assertEqual(self.envoyer("--distant", "/in", "--verbeux", "--console", fichier), 0, self.erreur)
        self.assertEqual(self.envoyer("--distant", "/in", fichier, env={"MDP_SFTP": MDP + "x"}), 2)
        self.assertNotIn(MDP, self.tout_le_texte())
        self.assertNotIn(MDP + "x", self.tout_le_texte())

    def test_mot_de_passe_par_fichier(self):
        secret = self.ecrire("secret.txt", MDP + "\n")
        os.makedirs(os.path.join(self.distant, "in"))
        code = self.lancer(sftp_envoyer, *(self.base(mdp=False) + ["--mot-de-passe-fichier", secret, "--distant", "/in",
                                                                    self.ecrire("local/a.txt")]))
        self.assertEqual(code, 0, self.erreur)

    def test_variable_de_mot_de_passe_absente(self):
        self.assertEqual(self.envoyer("--distant", "/in", self.ecrire("local/a.txt"), env={"MDP_SFTP": ""}), 3)

    def test_aucun_moyen_d_authentification(self):
        code = self.lancer(sftp_envoyer, *(self.base(mdp=False) + ["--distant", "/in", self.ecrire("local/a.txt")]))
        self.assertEqual(code, 3)
        self.assertIn("aucun moyen d'authentification", self.erreur)

    def test_cle_privee_avec_phrase_secrete(self):
        cle = paramiko.ECDSAKey.generate()
        fichier_cle = self.chemin("cle_privee")
        cle.write_private_key_file(fichier_cle, password=PHRASE)
        self.serveur.cle_autorisee = cle
        os.makedirs(os.path.join(self.distant, "in"))
        code = self.lancer(sftp_envoyer, *(self.base(mdp=False) + ["--cle-privee", fichier_cle, "--phrase-env", "PHRASE",
                                                                    "--distant", "/in", self.ecrire("local/a.txt")]),
                           env={"PHRASE": PHRASE})
        self.assertEqual(code, 0, self.erreur)
        self.assertNotIn(PHRASE, self.tout_le_texte())

    def test_cle_privee_phrase_incorrecte(self):
        cle = paramiko.ECDSAKey.generate()
        fichier_cle = self.chemin("cle_privee")
        cle.write_private_key_file(fichier_cle, password=PHRASE)
        code = self.lancer(sftp_envoyer, *(self.base(mdp=False) + ["--cle-privee", fichier_cle, "--phrase-env", "PHRASE",
                                                                    "--distant", "/in", self.ecrire("local/a.txt")]),
                           env={"PHRASE": "autre"})
        self.assertEqual(code, 3)

    def test_paramiko_absent_code_4(self):
        fichier = self.ecrire("local/a.txt")
        with mock.patch.dict(sys.modules, {"paramiko": None}):
            self.assertEqual(self.envoyer("--distant", "/in", fichier), 4)
            self.assertIn("paramiko", self.erreur)
            self.assertEqual(self.recuperer("--distant", "/in", "--local", self.chemin("r")), 4)
        self.assertEqual(self.serveur.connexions, 0)


class TestRecuperation(CasSftp):
    def test_recuperation_simple(self):
        self.ecrire_distant("out/a.txt", b"aaa")
        self.ecrire_distant("out/b.txt", b"bbb")
        recu = self.chemin("recu")
        self.assertEqual(self.recuperer("--distant", "/out", "--local", recu), 0, self.erreur)
        self.assertEqual(sorted(os.listdir(recu)), ["a.txt", "b.txt"])
        self.assertEqual(self.lire("out", "a.txt"), b"aaa")                  # conserve cote serveur par defaut
        self.controler_journal("sftp_recuperer", statut="SUCCES")

    def test_masque_exclusion_et_noms_temporaires(self):
        for nom in ("a.csv", "b.csv", "c.txt", "d.csv.tmp"):
            self.ecrire_distant("out/" + nom)
        recu = self.chemin("recu")
        code = self.recuperer("--distant", "/out", "--local", recu, "--masque", "*.csv", "--exclure", "b.*")
        self.assertEqual(code, 0, self.erreur)
        self.assertEqual(os.listdir(recu), ["a.csv"])

    def test_recursif_reproduit_l_arborescence(self):
        self.ecrire_distant("out/x.txt", b"1")
        self.ecrire_distant("out/s/y.txt", b"2")
        recu = self.chemin("recu")
        self.assertEqual(self.recuperer("--distant", "/out", "--local", recu), 0)
        self.assertEqual(os.listdir(recu), ["x.txt"])
        self.assertEqual(self.recuperer("--distant", "/out", "--local", recu, "-r", "--ignorer-existants"), 0)
        self.assertEqual(lire_fichier(os.path.join(recu, "s", "y.txt")), b"2")

    def test_age_minimum(self):
        self.ecrire_distant("out/vieux.txt", age_secondes=3600)
        self.ecrire_distant("out/frais.txt", age_secondes=1)
        recu = self.chemin("recu")
        self.assertEqual(self.recuperer("--distant", "/out", "--local", recu, "--age-minimum", 60), 0, self.erreur)
        self.assertEqual(os.listdir(recu), ["vieux.txt"])
        self.assertEqual(len(self.lignes("fichier_trop_recent")), 1)

    def test_rien_que_des_fichiers_trop_recents_n_est_pas_une_erreur(self):
        self.ecrire_distant("out/frais.txt", age_secondes=1)
        self.assertEqual(self.recuperer("--distant", "/out", "--local", self.chemin("recu"), "--age-minimum", 600), 0)
        self.assertIn("RIEN A FAIRE", self.sortie)

    def test_jamais_d_ecrasement_local(self):
        self.ecrire_distant("out/a.txt", b"distant")
        self.ecrire("recu/a.txt", b"local")
        self.assertEqual(self.recuperer("--distant", "/out", "--local", self.chemin("recu")), 2)
        self.assertEqual(lire_fichier(self.chemin("recu", "a.txt")), b"local")
        self.assertEqual(self.recuperer("--distant", "/out", "--local", self.chemin("recu"), "--ecraser"), 0)
        self.assertEqual(lire_fichier(self.chemin("recu", "a.txt")), b"distant")

    def test_apres_recuperation_supprimer(self):
        self.ecrire_distant("out/a.txt")
        self.assertEqual(self.recuperer("--distant", "/out", "--local", self.chemin("recu"),
                                        "--apres-recuperation", "supprimer"), 0, self.erreur)
        self.assertEqual(os.listdir(os.path.join(self.distant, "out")), [])
        self.assertTrue(os.path.exists(self.chemin("recu", "a.txt")))

    def test_apres_recuperation_archiver_sans_ecraser(self):
        self.ecrire_distant("out/a.txt", b"nouveau")
        self.ecrire_distant("archive/a.txt", b"ancienne archive")
        self.assertEqual(self.recuperer("--distant", "/out", "--local", self.chemin("recu"), "--apres-recuperation",
                                        "archiver", "--archive-distant", "/archive"), 0, self.erreur)
        self.assertEqual(self.lire("archive", "a.txt"), b"ancienne archive")
        self.assertEqual(self.lire("archive", "a_2.txt"), b"nouveau")
        self.assertFalse(os.path.exists(os.path.join(self.distant, "out", "a.txt")))

    def test_un_echec_local_ne_touche_pas_au_fichier_distant(self):
        self.ecrire_distant("out/a.txt")
        self.ecrire("recu/a.txt", b"local")
        self.recuperer("--distant", "/out", "--local", self.chemin("recu"), "--apres-recuperation", "supprimer")
        self.assertTrue(os.path.exists(os.path.join(self.distant, "out", "a.txt")))

    def test_simulation(self):
        self.ecrire_distant("out/a.txt")
        recu = self.chemin("recu")
        self.assertEqual(self.recuperer("--distant", "/out", "--local", recu, "--simulation",
                                        "--apres-recuperation", "supprimer"), 0, self.erreur)
        self.assertFalse(os.path.exists(recu))
        self.assertTrue(os.path.exists(os.path.join(self.distant, "out", "a.txt")))
        self.assertEqual(len(self.lignes("fichier_a_recuperer")), 1)
        self.controler_journal("sftp_recuperer", statut="SUCCES", simulation=True)

    def test_dossier_distant_introuvable(self):
        self.assertEqual(self.recuperer("--distant", "/nulle-part", "--local", self.chemin("recu")), 2)
        self.assertIn("dossier distant introuvable", self.erreur)

    def test_archiver_demande_un_dossier(self):
        self.assertEqual(self.recuperer("--distant", "/out", "--local", self.chemin("r"), "--apres-recuperation",
                                        "archiver"), 3)


if __name__ == "__main__":
    unittest.main()
