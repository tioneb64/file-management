"""Boite a outils : notification (courriel SMTP, webhook HTTP), contre de petits serveurs locaux."""
import base64
import email
import json
import socket
import socketserver
import threading
import unittest
from email import policy
from unittest import mock
from http.server import BaseHTTPRequestHandler, HTTPServer

from outils.notification import courriel, webhook
from tests.boite_outils import CasOutil

SECRET = "S3cret-Pass!"


class _GestionnaireSmtp(socketserver.StreamRequestHandler):
    """Un serveur SMTP minimal : EHLO, AUTH PLAIN, MAIL, RCPT, DATA, QUIT. Le serveur (self.server.etat) garde les
    messages recus et peut refuser certains destinataires ou l'authentification."""

    def repondre(self, texte):
        self.wfile.write(texte.encode("utf-8") + b"\r\n")

    def handle(self):
        etat = self.server.etat
        self.repondre("220 test ESMTP")
        enveloppe = {"de": None, "a": []}
        while True:
            ligne = self.rfile.readline()
            if not ligne:
                return
            commande = ligne.decode("utf-8", "replace").strip()
            verbe = commande.split(" ", 1)[0].upper()
            if verbe == "EHLO":
                self.repondre("250-test")
                self.repondre("250 AUTH PLAIN")
            elif verbe == "AUTH":
                etat["auth"].append(commande)
                if etat["refuser_auth"]:
                    donnees = base64.b64decode(commande.split()[-1]).split(b"\0")
                    self.repondre("535 5.7.8 mot de passe %s refuse" % donnees[-1].decode())      # le serveur repete le secret
                else:
                    self.repondre("235 ok")
            elif verbe == "MAIL":
                enveloppe = {"de": commande.split(":", 1)[1].strip(" <>"), "a": []}
                self.repondre("250 ok")
            elif verbe == "RCPT":
                adresse = commande.split(":", 1)[1].strip(" <>")
                if adresse in etat["refuses"]:
                    self.repondre("550 destinataire refuse")
                else:
                    enveloppe["a"].append(adresse)
                    self.repondre("250 ok")
            elif verbe == "DATA":
                self.repondre("354 fin par <CRLF>.<CRLF>")
                lignes = []
                while True:
                    l = self.rfile.readline()
                    if l in (b".\r\n", b""):
                        break
                    lignes.append(l[1:] if l.startswith(b"..") else l)
                etat["messages"].append((enveloppe, b"".join(lignes)))
                self.repondre("250 recu")
            elif verbe == "QUIT":
                self.repondre("221 au revoir")
                return
            else:
                self.repondre("250 ok")


class _ServeurSmtp(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass                                                   # un client qui coupe la connexion n'est pas une erreur du test


class CasServeur(CasOutil):
    def demarrer(self, serveur):
        fil = threading.Thread(target=serveur.serve_forever, kwargs={"poll_interval": 0.05})
        fil.start()

        def arreter():
            serveur.shutdown()
            serveur.server_close()
            fil.join()
        self.addCleanup(arreter)
        return serveur.server_address[1]


class TestCourriel(CasServeur):
    def serveur_smtp(self, refuses=(), refuser_auth=False):
        serveur = _ServeurSmtp(("127.0.0.1", 0), _GestionnaireSmtp)
        serveur.etat = {"messages": [], "auth": [], "refuses": set(refuses), "refuser_auth": refuser_auth}
        self.etat = serveur.etat
        return self.demarrer(serveur)

    def base(self, port, *plus):
        return ["--serveur", "127.0.0.1", "--port", str(port), "--de", "moteur@exemple.test", "--a", "admin@exemple.test"] + list(plus)

    def message(self, indice=0):
        enveloppe, octets = self.etat["messages"][indice]
        return enveloppe, email.message_from_bytes(octets, policy=policy.default)

    def test_envoi_avec_variables_du_moteur(self):
        port = self.serveur_smtp()
        env = {"COPIE_ENVIRONNEMENT": "prod", "COPIE_STATUT": "ERREUR", "COPIE_SITUATION": "programme_apres_fichier",
               "COPIE_MESSAGE": "le fichier est vide"}
        code = self.lancer(courriel, *self.base(port), "--sujet", "[{environnement}] {regle} : {statut}",
                           "--corps", "Execution {execution_id} - {situation} - {message}", env=env)
        self.assertEqual(code, 0, self.erreur + self.sortie)
        enveloppe, msg = self.message()
        self.assertEqual((enveloppe["de"], enveloppe["a"]), ("moteur@exemple.test", ["admin@exemple.test"]))
        self.assertEqual(msg["Subject"], "[prod] regle_test : ERREUR")
        self.assertEqual(msg.get_content().strip(), "Execution 42 - programme_apres_fichier - le fichier est vide")
        lignes = self.controler_journal("courriel", "SUCCES")
        evenement = [l for l in lignes if l["context"]["event"] == "courriel_envoye"][0]["context"]
        self.assertEqual(evenement["destinataires"], ["admin@exemple.test"])

    def test_message_standard_serveur_et_adresses_par_variables(self):
        port = self.serveur_smtp()
        env = {"COPIE_SMTP_SERVEUR": "127.0.0.1", "COPIE_SMTP_PORT": str(port), "COPIE_SMTP_DE": "m@exemple.test",
               "COPIE_SMTP_A": "a@exemple.test; b@exemple.test", "COPIE_STATUT": "ERREUR", "COPIE_ENVIRONNEMENT": "int"}
        self.assertEqual(self.lancer(courriel, env=env), 0, self.erreur)
        enveloppe, msg = self.message()
        self.assertEqual(enveloppe["a"], ["a@exemple.test", "b@exemple.test"])
        self.assertEqual(msg["Subject"], "[int] Regle regle_test : ERREUR")
        corps = msg.get_content()
        self.assertIn("Regle : regle_test", corps)
        self.assertIn("Execution : 42", corps)

    def test_copie_pieces_jointes_et_corps_fichier(self):
        port = self.serveur_smtp()
        piece = self.ecrire("rapport.csv", b"a;b\n1;2\n")
        corps = self.ecrire("corps.txt", "Bonjour café".encode("utf-8"))
        code = self.lancer(courriel, *self.base(port, "--cc", "chef@exemple.test", "--sujet", "Rapport", "--corps-fichier", corps,
                                                "--joindre", piece))
        self.assertEqual(code, 0, self.erreur)
        enveloppe, msg = self.message()
        self.assertEqual(sorted(enveloppe["a"]), ["admin@exemple.test", "chef@exemple.test"])
        self.assertEqual(msg["Cc"], "chef@exemple.test")
        pieces = list(msg.iter_attachments())
        self.assertEqual([p.get_filename() for p in pieces], ["rapport.csv"])
        self.assertEqual(pieces[0].get_content(), "a;b\n1;2\n")
        self.assertIn("Bonjour café", msg.get_body().get_content())

    def test_le_sujet_ne_peut_pas_injecter_d_en_tete(self):
        port = self.serveur_smtp()
        env = {"COPIE_MESSAGE": "ligne1\r\nBcc: pirate@exemple.test"}
        self.assertEqual(self.lancer(courriel, *self.base(port, "--sujet", "Alerte {message}"), env=env), 0, self.erreur)
        enveloppe, msg = self.message()
        self.assertEqual(msg["Subject"], "Alerte ligne1 Bcc: pirate@exemple.test")
        self.assertIsNone(msg["Bcc"])
        self.assertEqual(enveloppe["a"], ["admin@exemple.test"])

    def test_authentification_sans_journaliser_le_mot_de_passe(self):
        port = self.serveur_smtp()
        env = {"SMTP_MDP": SECRET}
        code = self.lancer(courriel, *self.base(port, "--utilisateur", "compte", "--mot-de-passe-env", "SMTP_MDP", "--sujet", "x", "--corps", "y"), env=env)
        self.assertEqual(code, 0, self.erreur)
        jeton = base64.b64decode(self.etat["auth"][0].split()[-1])
        self.assertEqual(jeton.split(b"\0")[-2:], [b"compte", SECRET.encode()])
        self.assertNotIn(SECRET, self.texte_journal() + self.sortie + self.erreur)

    def test_authentification_refusee_le_secret_est_masque(self):
        port = self.serveur_smtp(refuser_auth=True)
        env = {"SMTP_MDP": SECRET}
        code = self.lancer(courriel, *self.base(port, "--utilisateur", "compte", "--mot-de-passe-env", "SMTP_MDP", "--sujet", "x", "--corps", "y"), env=env)
        self.assertEqual(code, 2)
        self.assertEqual(self.etat["messages"], [])
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "EXTERNAL_SERVICE_ERROR")
        self.assertNotIn(SECRET, self.texte_journal() + self.sortie + self.erreur)
        self.assertIn("***", self.texte_journal())

    def test_mot_de_passe_depuis_un_fichier(self):
        port = self.serveur_smtp()
        fichier = self.ecrire("mdp.txt", SECRET.encode() + b"\n")
        code = self.lancer(courriel, *self.base(port, "--utilisateur", "c", "--mot-de-passe-fichier", fichier, "--sujet", "x", "--corps", "y"))
        self.assertEqual(code, 0, self.erreur)
        self.assertEqual(base64.b64decode(self.etat["auth"][0].split()[-1]).split(b"\0")[-1], SECRET.encode())

    def test_destinataire_refuse(self):
        port = self.serveur_smtp(refuses={"mauvais@exemple.test"})
        code = self.lancer(courriel, *self.base(port, "--cc", "mauvais@exemple.test", "--sujet", "x", "--corps", "y"))
        self.assertEqual(code, 2)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "EXTERNAL_SERVICE_ERROR")
        self.assertIn("mauvais@exemple.test", self.erreurs_journal()[0]["message"])
        port = self.serveur_smtp(refuses={"admin@exemple.test"})
        self.assertEqual(self.lancer(courriel, *self.base(port, "--sujet", "x", "--corps", "y")), 2)           # tous refuses

    def test_simulation_n_ouvre_aucune_connexion(self):
        libre = socket.socket()
        libre.bind(("127.0.0.1", 0))
        port = libre.getsockname()[1]
        libre.close()
        self.assertEqual(self.lancer(courriel, *self.base(port, "--sujet", "x", "--corps", "y", "--simulation")), 0)
        self.controler_journal("courriel", simulation=True)
        self.assertEqual(len(self.lignes("courriel_a_envoyer")), 1)

    def test_serveur_injoignable(self):
        with mock.patch("outils.notification.courriel.smtplib.SMTP", side_effect=ConnectionRefusedError(10061, "refuse")):
            self.assertEqual(self.lancer(courriel, *self.base(25, "--sujet", "x", "--corps", "y")), 2)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "EXTERNAL_SERVICE_ERROR")
        self.assertNotIn("Traceback", self.sortie + self.erreur)

    def test_delai_depasse(self):
        mort = socket.socket()
        mort.bind(("127.0.0.1", 0))
        mort.listen(1)                                              # accepte la connexion (backlog) mais ne repond jamais
        self.addCleanup(mort.close)
        port = mort.getsockname()[1]
        self.assertEqual(self.lancer(courriel, *self.base(port, "--sujet", "x", "--corps", "y", "--delai", "0.4")), 2)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "TIMEOUT")

    def test_starttls_non_propose_et_ssl_sur_un_serveur_clair(self):
        port = self.serveur_smtp()
        self.assertEqual(self.lancer(courriel, *self.base(port, "--securite", "starttls", "--sujet", "x", "--corps", "y")), 2)
        self.assertEqual(self.etat["messages"], [])
        self.assertEqual(self.lancer(courriel, *self.base(port, "--securite", "ssl", "--sujet", "x", "--corps", "y", "--delai", "3")), 2)
        self.assertEqual(self.etat["messages"], [])                 # jamais d'envoi en clair apres un echec de chiffrement

    def test_parametres_invalides(self):
        self.assertEqual(self.lancer(courriel), 3)
        base = ["--serveur", "127.0.0.1", "--de", "m@exemple.test", "--a", "a@exemple.test"]
        self.assertEqual(self.lancer(courriel, "--serveur", "x", "--de", "sans-arobase", "--a", "a@exemple.test"), 3)
        self.assertEqual(self.lancer(courriel, "--serveur", "x", "--de", "m@exemple.test", "--a", "a@exemple.test\nBcc:x@y.z"), 3)
        self.assertEqual(self.lancer(courriel, *base, "--mot-de-passe-env", "SMTP_MDP", env={"SMTP_MDP": "x"}), 3)       # sans --utilisateur
        self.assertEqual(self.lancer(courriel, *base, "--joindre", self.chemin("absent.txt")), 3)
        self.assertEqual(self.lancer(courriel, *base, "--corps", "accolade { seule"), 3)
        gros = self.ecrire("gros.bin", b"x" * 2048)
        self.assertEqual(self.lancer(courriel, *base, "--joindre", gros, "--taille-max-pieces", "1K"), 3)


class _GestionnaireHttp(BaseHTTPRequestHandler):
    def do_POST(self):
        etat = self.server.etat
        longueur = int(self.headers.get("Content-Length", 0))
        etat["requetes"].append({"chemin": self.path, "corps": self.rfile.read(longueur), "en_tetes": dict(self.headers)})
        code = etat["codes"].pop(0) if etat["codes"] else 200
        self.send_response(code)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


class TestWebhook(CasServeur):
    def serveur_http(self, codes=()):
        serveur = HTTPServer(("127.0.0.1", 0), _GestionnaireHttp)
        serveur.etat = {"requetes": [], "codes": list(codes)}
        self.etat = serveur.etat
        port = self.demarrer(serveur)
        return "http://127.0.0.1:%d" % port

    def corps(self, indice=0):
        return json.loads(self.etat["requetes"][indice]["corps"].decode("utf-8"))

    def test_post_json_avec_champs_et_variables_du_moteur(self):
        url = self.serveur_http()
        env = {"COPIE_STATUT": "ERREUR", "COPIE_MESSAGE": "café renverse", "COPIE_ENVIRONNEMENT": "prod"}
        code = self.lancer(webhook, "--url", url + "/hooks/abc", "--auto", "--champ", "source=moteur", "--json", '{"x": 1}', env=env)
        self.assertEqual(code, 0, self.erreur)
        requete = self.etat["requetes"][0]
        self.assertEqual(requete["chemin"], "/hooks/abc")
        self.assertTrue(requete["en_tetes"]["Content-Type"].startswith("application/json"))
        corps = self.corps()
        self.assertEqual((corps["regle"], corps["execution_id"], corps["statut"], corps["message"], corps["source"], corps["x"]),
                         ("regle_test", "42", "ERREUR", "café renverse", "moteur", 1))
        self.assertIn("hote", corps)
        lignes = self.controler_journal("webhook", "SUCCES")
        evenement = [l for l in lignes if l["context"]["event"] == "webhook_appele"][0]["context"]
        self.assertEqual((evenement["code_http"], evenement["essai"]), (200, 1))

    def test_json_fichier_et_url_par_variable(self):
        url = self.serveur_http()
        fichier = self.ecrire("c.json", b'\xef\xbb\xbf{"a": "b"}')
        self.assertEqual(self.lancer(webhook, "--json-fichier", fichier, env={"COPIE_WEBHOOK_URL": url}), 0, self.erreur)
        self.assertEqual(self.corps(), {"a": "b"})

    def test_jeton_par_variable_d_environnement_jamais_journalise(self):
        url = self.serveur_http()
        code = self.lancer(webhook, "--url", url, "--champ", "a=b", "--en-tete-env", "Authorization=JETON_WEBHOOK",
                           "--en-tete", "X-Test=1", env={"JETON_WEBHOOK": "Bearer " + SECRET})
        self.assertEqual(code, 0, self.erreur)
        self.assertEqual(self.etat["requetes"][0]["en_tetes"]["Authorization"], "Bearer " + SECRET)
        self.assertEqual(self.etat["requetes"][0]["en_tetes"]["X-Test"], "1")
        self.assertNotIn(SECRET, self.texte_journal() + self.sortie + self.erreur)
        self.assertEqual(self.lancer(webhook, "--url", url, "--champ", "a=b", "--en-tete-env", "Authorization=ABSENTE"), 3)

    def test_url_sans_parametres_dans_le_journal(self):
        url = self.serveur_http()
        self.assertEqual(self.lancer(webhook, "--url", url + "/chemin?token=%s" % SECRET, "--champ", "a=b"), 0, self.erreur)
        self.assertEqual(self.etat["requetes"][0]["chemin"], "/chemin?token=%s" % SECRET)        # la requete porte bien le parametre
        texte = self.texte_journal() + self.sortie
        self.assertNotIn(SECRET, texte)
        self.assertNotIn("token=", texte)
        self.assertIn("/chemin", texte)

    def test_identifiants_dans_l_url_refuses_sans_les_afficher(self):
        url = self.serveur_http().replace("http://", "http://utilisateur:%s@" % SECRET)
        self.assertEqual(self.lancer(webhook, "--url", url, "--champ", "a=b"), 3)
        self.assertEqual(self.etat["requetes"], [])
        self.assertNotIn(SECRET, self.texte_journal() + self.sortie + self.erreur)

    def test_nouvel_essai_sur_5xx_puis_succes(self):
        url = self.serveur_http(codes=[500, 503, 200])
        code = self.lancer(webhook, "--url", url, "--champ", "a=b", "--pause", "0", "--tentatives", "3")
        self.assertEqual(code, 0, self.erreur)
        self.assertEqual(len(self.etat["requetes"]), 3)
        self.assertEqual(len(self.lignes("webhook_tentative_echouee", "WARNING")), 2)
        self.assertEqual(self.lignes("webhook_appele")[0]["essai"], 3)
        self.controler_journal("webhook", "WARNING")

    def test_pas_de_nouvel_essai_sur_4xx(self):
        url = self.serveur_http(codes=[404, 200])
        self.assertEqual(self.lancer(webhook, "--url", url, "--champ", "a=b", "--pause", "0", "--tentatives", "3"), 2)
        self.assertEqual(len(self.etat["requetes"]), 1)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "EXTERNAL_SERVICE_ERROR")
        self.assertIn("HTTP 404", self.erreurs_journal()[0]["message"])

    def test_echec_apres_toutes_les_tentatives(self):
        url = self.serveur_http(codes=[500, 500])
        self.assertEqual(self.lancer(webhook, "--url", url, "--champ", "a=b", "--pause", "0", "--tentatives", "2"), 2)
        self.assertEqual(len(self.etat["requetes"]), 2)

    def test_serveur_injoignable_et_delai_depasse(self):
        with mock.patch("outils.notification.webhook.urllib.request.urlopen", side_effect=ConnectionRefusedError(10061, "refuse")):
            self.assertEqual(self.lancer(webhook, "--url", "http://127.0.0.1:9", "--champ", "a=b", "--tentatives", "1"), 2)
        self.assertEqual(self.erreurs_journal()[0]["error"]["type"], "EXTERNAL_SERVICE_ERROR")
        mort = socket.socket()
        mort.bind(("127.0.0.1", 0))
        mort.listen(1)
        self.addCleanup(mort.close)
        code = self.lancer(webhook, "--url", "http://127.0.0.1:%d" % mort.getsockname()[1], "--champ", "a=b", "--tentatives", "1", "--delai", "0.4")
        self.assertEqual(code, 2)
        self.assertIn("TIMEOUT", [b["error"]["type"] for b in self.erreurs_journal()])

    def test_simulation_n_appelle_rien(self):
        url = self.serveur_http()
        self.assertEqual(self.lancer(webhook, "--url", url, "--champ", "a=b", "--simulation"), 0)
        self.assertEqual(self.etat["requetes"], [])
        self.controler_journal("webhook", simulation=True)
        self.assertEqual(self.lignes("webhook_a_appeler")[0]["champs"], ["a"])

    def test_parametres_invalides(self):
        self.assertEqual(self.lancer(webhook, "--champ", "a=b"), 3)                                  # pas d'URL
        self.assertEqual(self.lancer(webhook, "--url", "ftp://x/y", "--champ", "a=b"), 3)
        self.assertEqual(self.lancer(webhook, "--url", "http://127.0.0.1:1"), 3)                     # corps vide
        self.assertEqual(self.lancer(webhook, "--url", "http://127.0.0.1:1", "--json", "[1]"), 3)    # pas un objet
        self.assertEqual(self.lancer(webhook, "--url", "http://127.0.0.1:1", "--json", "{oups"), 3)
        self.assertEqual(self.lancer(webhook, "--url", "http://127.0.0.1:1", "--champ", "sans_egal"), 3)
        self.assertEqual(self.lancer(webhook, "--url", "http://127.0.0.1:1", "--champ", "a=b", "--tentatives", "0"), 3)


if __name__ == "__main__":
    unittest.main()
