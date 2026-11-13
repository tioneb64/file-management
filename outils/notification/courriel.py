# outil: courriel
# description: Envoie un courriel par SMTP (bibliotheque standard).
# parametre: --serveur HOTE | facultatif | serveur SMTP (defaut : COPIE_SMTP_SERVEUR)
# parametre: --port N | facultatif | port (defaut : COPIE_SMTP_PORT, sinon 25 / 587 starttls / 465 ssl)
# parametre: --securite {aucune,starttls,ssl} | facultatif | chiffrement (defaut aucune)
# parametre: --utilisateur COMPTE | facultatif | compte d'authentification SMTP (facultatif)
# parametre: --de ADRESSE | facultatif | expediteur (defaut : COPIE_SMTP_DE)
# parametre: --a ADRESSE | facultatif | destinataire ; repetable ou separes par , ou ; (defaut : COPIE_SMTP_A)
# parametre: --cc ADRESSE | facultatif | destinataire en copie ; repetable
# parametre: --sujet TEXTE | facultatif | sujet
# parametre: --corps TEXTE | facultatif | texte du message
# parametre: --corps-fichier FICHIER | facultatif | texte du message lu dans un fichier UTF-8
# parametre: --joindre FICHIER | facultatif | piece jointe ; repetable
# parametre: --taille-max-pieces TAILLE | facultatif | taille totale maximale des pieces jointes (defaut 10M)
# parametre: --delai SEC | facultatif | delai reseau (defaut 30)
# parametre: --mot-de-passe-env NOM | facultatif | nom de la variable d'environnement qui contient le mot de passe
# parametre: --mot-de-passe-fichier FICHIER | facultatif | fichier (UTF-8) dont la premiere ligne est le mot de passe
"""Envoie un courriel (SMTP) : alerte d'une regle, compte rendu, piece jointe."""
import mimetypes
import os
import smtplib
import socket
import ssl
import sys
from email.message import EmailMessage

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.erreurs import EXTERNAL_SERVICE_ERROR, TIMEOUT, ErreurOutil, ErreurParametres
from outils.commun.fichiers import lire_taille, taille_lisible
from outils.commun.outil import Outil
from outils.commun.secret import lire_mot_de_passe, options_mot_de_passe

OUTIL = Outil("courriel", "Envoie un courriel par SMTP (bibliotheque standard). Prevu pour le point sur_erreur : le "
              "sujet et le corps acceptent {regle} {environnement} {execution_id} {statut} {situation} {message} "
              "{point_appel} {hote} (variables COPIE_* du moteur) ; ATTENTION : dans la commande d'une regle, le "
              "moteur remplace lui-meme {regle} et {environnement} mais refuse les autres (controle G01) : "
              "{statut}, {situation}, {message}... ne s'utilisent que si l'outil est lance a la main ; depuis une "
              "regle, ne pas les ecrire et laisser le message standard (sans --sujet ni --corps), qui les contient "
              "tous ; sans --sujet ni --corps, un message standard "
              "est compose. Serveur, port, expediteur et destinataires peuvent venir des variables COPIE_SMTP_SERVEUR, "
              "COPIE_SMTP_PORT, COPIE_SMTP_DE, COPIE_SMTP_A. Le mot de passe SMTP ne passe jamais en ligne de "
              "commande (--mot-de-passe-env / --mot-de-passe-fichier) et n'est jamais journalise.", "notification")


@OUTIL.arguments
def arguments(p):
    p.add_argument("--serveur", metavar="HOTE", help="serveur SMTP (defaut : COPIE_SMTP_SERVEUR)")
    p.add_argument("--port", type=int, metavar="N", help="port (defaut : COPIE_SMTP_PORT, sinon 25 / 587 starttls / 465 ssl)")
    p.add_argument("--securite", choices=("aucune", "starttls", "ssl"), default="aucune", help="chiffrement (defaut aucune)")
    p.add_argument("--utilisateur", metavar="COMPTE", help="compte d'authentification SMTP (facultatif)")
    p.add_argument("--de", metavar="ADRESSE", help="expediteur (defaut : COPIE_SMTP_DE)")
    p.add_argument("--a", action="append", default=[], metavar="ADRESSE", help="destinataire ; repetable ou separes par , ou ; (defaut : COPIE_SMTP_A)")
    p.add_argument("--cc", action="append", default=[], metavar="ADRESSE", help="destinataire en copie ; repetable")
    p.add_argument("--sujet", metavar="TEXTE", help="sujet")
    p.add_argument("--corps", metavar="TEXTE", help="texte du message")
    p.add_argument("--corps-fichier", metavar="FICHIER", help="texte du message lu dans un fichier UTF-8")
    p.add_argument("--joindre", action="append", default=[], metavar="FICHIER", help="piece jointe ; repetable")
    p.add_argument("--taille-max-pieces", default="10M", metavar="TAILLE", help="taille totale maximale des pieces jointes (defaut 10M)")
    p.add_argument("--delai", type=float, default=30.0, metavar="SEC", help="delai reseau (defaut 30)")
    options_mot_de_passe(p)


class _Variables(dict):
    def __missing__(self, cle):
        return ""


def _est_un_delai(erreur):
    """Vrai si l'erreur, ou la cause qu'elle enveloppe, est un delai reseau depasse."""
    vue = set()
    while erreur is not None and id(erreur) not in vue:
        if isinstance(erreur, (socket.timeout, TimeoutError)):
            return True
        vue.add(id(erreur))
        erreur = erreur.__cause__ or erreur.__context__
    return False


def _adresses(valeurs):
    resultat = []
    for v in valeurs:
        resultat.extend(a.strip() for a in v.replace(";", ",").split(",") if a.strip())
    return resultat


@OUTIL.principal
def principal(ctx, args):
    env = ctx.env
    serveur = args.serveur or env.get("COPIE_SMTP_SERVEUR")
    expediteur = args.de or env.get("COPIE_SMTP_DE")
    destinataires = _adresses(args.a or ([env["COPIE_SMTP_A"]] if env.get("COPIE_SMTP_A") else []))
    copies = _adresses(args.cc)
    if not serveur or not expediteur or not destinataires:
        raise ErreurParametres("serveur, expediteur et au moins un destinataire sont obligatoires "
                               "(--serveur --de --a, ou COPIE_SMTP_SERVEUR / COPIE_SMTP_DE / COPIE_SMTP_A)")
    for adresse in [expediteur] + destinataires + copies:
        if "@" not in adresse or any(c in adresse for c in "\r\n <>"):
            raise ErreurParametres("adresse invalide : %r" % adresse)
    port = args.port or int(env.get("COPIE_SMTP_PORT") or {"aucune": 25, "starttls": 587, "ssl": 465}[args.securite])
    secret = lire_mot_de_passe(args, env)
    if secret and not args.utilisateur:
        raise ErreurParametres("un mot de passe SMTP exige --utilisateur")
    variables = _Variables(regle=env.get("COPIE_REGLE", ""), environnement=env.get("COPIE_ENVIRONNEMENT", ""),
                           execution_id=env.get("COPIE_EXECUTION_ID", ""), statut=env.get("COPIE_STATUT", ""),
                           situation=env.get("COPIE_SITUATION", ""), message=env.get("COPIE_MESSAGE", ""),
                           point_appel=env.get("COPIE_POINT_APPEL", ""), hote=socket.gethostname())
    corps = args.corps
    if args.corps_fichier:
        with open(args.corps_fichier, encoding="utf-8-sig") as f:
            corps = f.read()
    sujet = args.sujet or "[{environnement}] Regle {regle} : {statut} {situation}"
    corps = corps if corps is not None else (
        "Regle : {regle}\nEnvironnement : {environnement}\nExecution : {execution_id}\nStatut : {statut}\n"
        "Situation : {situation}\nMessage : {message}\nServeur : {hote}\n")
    message = EmailMessage()
    message["From"], message["To"] = expediteur, ", ".join(destinataires)
    if copies:
        message["Cc"] = ", ".join(copies)
    try:
        sujet_final = " ".join(sujet.format_map(variables).split())             # jamais de saut de ligne dans un en-tete
        corps_final = corps.format_map(variables)
    except (ValueError, IndexError, AttributeError) as e:
        raise ErreurParametres("sujet ou corps : accolade invalide (doubler {{ et }} pour une accolade litterale) : %s" % e)
    message["Subject"] = sujet_final
    message.set_content(corps_final)
    total = 0
    for piece in args.joindre:
        if not os.path.isfile(piece):
            raise ErreurParametres("piece jointe introuvable : %s" % piece)
        total += os.path.getsize(piece)
    if total > lire_taille(args.taille_max_pieces):
        raise ErreurParametres("pieces jointes trop grosses : %s (maximum %s)" % (taille_lisible(total), args.taille_max_pieces))
    for piece in args.joindre:
        type_, _ = mimetypes.guess_type(piece)
        principal_, _, sous = (type_ or "application/octet-stream").partition("/")
        with open(piece, "rb") as f:
            message.add_attachment(f.read(), maintype=principal_, subtype=sous, filename=os.path.basename(piece))
    champs = dict(serveur=serveur, port=port, securite=args.securite, expediteur=expediteur,
                  destinataires=destinataires + copies, sujet=message["Subject"], pieces_jointes=len(args.joindre))
    if ctx.simulation:
        ctx.action("courriel_a_envoyer", "Courriel serait envoye a %d destinataire(s) : %s" % (len(destinataires + copies),
                   message["Subject"]), compteur="a_envoyer", **champs)
        return
    try:
        if args.securite == "ssl":
            smtp = smtplib.SMTP_SSL(serveur, port, timeout=args.delai, context=ssl.create_default_context())
        else:
            smtp = smtplib.SMTP(serveur, port, timeout=args.delai)
        with smtp:
            if args.securite == "starttls":
                smtp.starttls(context=ssl.create_default_context())
            if args.utilisateur:
                smtp.login(args.utilisateur, secret or "")
            refus = smtp.send_message(message, to_addrs=destinataires + copies)
    except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
        if _est_un_delai(e):                    # smtplib range un delai de lecture dans SMTPServerDisconnected
            raise ErreurOutil("delai depasse (%s s) avec le serveur SMTP %s:%d" % (args.delai, serveur, port), TIMEOUT)
        texte = str(e)
        if secret:
            texte = texte.replace(secret, "***")
        raise ErreurOutil("envoi SMTP impossible vers %s:%d (%s) : %s" % (serveur, port, type(e).__name__, texte),
                          EXTERNAL_SERVICE_ERROR)
    if refus:
        raise ErreurOutil("destinataire(s) refuse(s) par le serveur : %s" % ", ".join(refus), EXTERNAL_SERVICE_ERROR)
    ctx.action("courriel_envoye", "Courriel envoye a %d destinataire(s) : %s" % (len(destinataires + copies), message["Subject"]),
               compteur="envoyes", **champs)


if __name__ == "__main__":
    OUTIL.lancer()
