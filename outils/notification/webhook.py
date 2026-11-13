# outil: webhook
# description: Envoie une requete POST JSON a une URL http(s).
# parametre: --url URL | facultatif | adresse http(s) (defaut : COPIE_WEBHOOK_URL)
# parametre: --json TEXTE | facultatif | corps JSON (un objet)
# parametre: --json-fichier FICHIER | facultatif | corps JSON lu dans un fichier UTF-8
# parametre: --champ CLE=VALEUR | facultatif | champ texte ajoute a l'objet ; repetable
# parametre: --auto | facultatif | ajoute les champs du moteur (COPIE_*)
# parametre: --en-tete NOM=VALEUR | facultatif | en-tete HTTP non secret ; repetable
# parametre: --en-tete-env NOM=VARIABLE | facultatif | en-tete HTTP dont la valeur est lue dans une variable d'environnement (jeton) ; repetable
# parametre: --delai SEC | facultatif | delai par tentative (defaut 30)
# parametre: --tentatives N | facultatif | nombre d'essais (defaut 3)
# parametre: --pause SEC | facultatif | pause entre deux essais (defaut 5)
"""Appelle un webhook HTTP (POST JSON) : alerte d'une regle vers Teams, Slack, une supervision..."""
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.erreurs import EXTERNAL_SERVICE_ERROR, TIMEOUT, ErreurOutil, ErreurParametres
from outils.commun.outil import Outil

OUTIL = Outil("webhook", "Envoie une requete POST JSON a une URL http(s). Le corps vient de --json (texte), "
              "--json-fichier et --champ cle=valeur, complete avec --auto par les variables du moteur (regle, "
              "environnement, execution_id, statut, situation, message, point_appel, hote). Succes : reponse 2xx ; "
              "--tentatives N rejoue les echecs reseau et les reponses 5xx. Un jeton d'authentification ne se met "
              "pas en ligne de commande : --en-tete-env \"Authorization=NOM_VARIABLE\". Le journal ne garde de "
              "l'URL que le serveur et le chemin (jamais les parametres ni les identifiants).", "notification")


@OUTIL.arguments
def arguments(p):
    p.add_argument("--url", metavar="URL", help="adresse http(s) (defaut : COPIE_WEBHOOK_URL)")
    p.add_argument("--json", metavar="TEXTE", help="corps JSON (un objet)")
    p.add_argument("--json-fichier", metavar="FICHIER", help="corps JSON lu dans un fichier UTF-8")
    p.add_argument("--champ", action="append", default=[], metavar="CLE=VALEUR", help="champ texte ajoute a l'objet ; repetable")
    p.add_argument("--auto", action="store_true", help="ajoute les champs du moteur (COPIE_*)")
    p.add_argument("--en-tete", action="append", default=[], metavar="NOM=VALEUR", help="en-tete HTTP non secret ; repetable")
    p.add_argument("--en-tete-env", action="append", default=[], metavar="NOM=VARIABLE",
                   help="en-tete HTTP dont la valeur est lue dans une variable d'environnement (jeton) ; repetable")
    p.add_argument("--delai", type=float, default=30.0, metavar="SEC", help="delai par tentative (defaut 30)")
    p.add_argument("--tentatives", type=int, default=3, metavar="N", help="nombre d'essais (defaut 3)")
    p.add_argument("--pause", type=float, default=5.0, metavar="SEC", help="pause entre deux essais (defaut 5)")


def url_sure(url):
    """URL sans identifiants ni parametres, pour le journal."""
    p = urllib.parse.urlsplit(url)
    return "%s://%s%s" % (p.scheme, p.hostname + (":%d" % p.port if p.port else ""), p.path)


def _paires(valeurs, nom):
    resultat = []
    for v in valeurs:
        cle, sep, valeur = v.partition("=")
        if not sep or not cle.strip():
            raise ErreurParametres("%s : forme CLE=VALEUR attendue : %r" % (nom, v))
        resultat.append((cle.strip(), valeur))
    return resultat


@OUTIL.principal
def principal(ctx, args):
    env = ctx.env
    url = args.url or env.get("COPIE_WEBHOOK_URL")
    if not url:
        raise ErreurParametres("--url est obligatoire (ou COPIE_WEBHOOK_URL)")
    analyse = urllib.parse.urlsplit(url)
    if analyse.scheme not in ("http", "https") or not analyse.hostname:
        raise ErreurParametres("l'URL doit etre http:// ou https://")
    if analyse.username or analyse.password:
        raise ErreurParametres("identifiants dans l'URL non pris en charge : utiliser --en-tete-env "
                               "\"Authorization=NOM_VARIABLE\" (le jeton reste hors de la ligne de commande)")
    if args.tentatives < 1:
        raise ErreurParametres("--tentatives : au moins 1")
    corps = {}
    try:
        if args.json_fichier:
            with open(args.json_fichier, encoding="utf-8-sig") as f:
                corps.update(json.load(f))
        if args.json:
            corps.update(json.loads(args.json))
    except (ValueError, TypeError, OSError) as e:
        raise ErreurParametres("corps JSON illisible ou ce n'est pas un objet : %s" % e)
    if args.auto:
        for cle, variable in (("regle", "COPIE_REGLE"), ("environnement", "COPIE_ENVIRONNEMENT"),
                              ("execution_id", "COPIE_EXECUTION_ID"), ("statut", "COPIE_STATUT"),
                              ("situation", "COPIE_SITUATION"), ("message", "COPIE_MESSAGE"),
                              ("point_appel", "COPIE_POINT_APPEL")):
            if env.get(variable):
                corps.setdefault(cle, env[variable])
        corps.setdefault("hote", socket.gethostname())
    corps.update(_paires(args.champ, "--champ"))
    if not corps:
        raise ErreurParametres("corps vide : indiquer --json, --json-fichier, --champ ou --auto")
    en_tetes = {"Content-Type": "application/json; charset=utf-8", "User-Agent": "file_management-outils"}
    en_tetes.update(_paires(args.en_tete, "--en-tete"))
    for nom, variable in _paires(args.en_tete_env, "--en-tete-env"):
        if not env.get(variable):
            raise ErreurParametres("la variable d'environnement %s (en-tete %s) est absente ou vide" % (variable, nom))
        en_tetes[nom] = env[variable]
    donnees = json.dumps(corps, ensure_ascii=False).encode("utf-8")
    champs = dict(url=url_sure(url), octets=len(donnees), champs=sorted(corps))
    if ctx.simulation:
        ctx.action("webhook_a_appeler", "Webhook serait appele : %s" % url_sure(url), compteur="a_appeler", **champs)
        return
    derniere = None
    for essai in range(1, args.tentatives + 1):
        requete = urllib.request.Request(url, data=donnees, headers=en_tetes, method="POST")
        try:
            with urllib.request.urlopen(requete, timeout=args.delai) as reponse:
                code = reponse.status
                reponse.read(4096)
            ctx.action("webhook_appele", "Webhook appele (HTTP %d) : %s" % (code, url_sure(url)), compteur="appeles",
                       code_http=code, essai=essai, **champs)
            return
        except urllib.error.HTTPError as e:
            derniere = ErreurOutil("le webhook a repondu HTTP %d" % e.code, EXTERNAL_SERVICE_ERROR)
            if e.code < 500 and e.code != 429:
                break
        except (socket.timeout, TimeoutError):
            derniere = ErreurOutil("delai depasse (%s s) : %s" % (args.delai, url_sure(url)), TIMEOUT)
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                derniere = ErreurOutil("delai depasse (%s s) : %s" % (args.delai, url_sure(url)), TIMEOUT)
            else:
                derniere = ErreurOutil("webhook injoignable (%s) : %s" % (e.reason, url_sure(url)), EXTERNAL_SERVICE_ERROR)
        except OSError as e:
            derniere = ErreurOutil("webhook injoignable (%s) : %s" % (e, url_sure(url)), EXTERNAL_SERVICE_ERROR)
        if essai < args.tentatives:
            ctx.avertir("webhook_tentative_echouee", "Essai %d/%d echoue : %s" % (essai, args.tentatives, derniere),
                        essai=essai, url=url_sure(url))
            time.sleep(args.pause)
    raise derniere


if __name__ == "__main__":
    OUTIL.lancer()
