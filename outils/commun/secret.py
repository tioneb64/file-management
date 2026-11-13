# bibliotheque: mots de passe : lus dans une variable d'environnement ou un fichier, jamais en ligne de commande ni au journal
"""Mots de passe : jamais en ligne de commande, jamais dans le journal."""

from outils.commun.erreurs import ErreurParametres


def options_mot_de_passe(parser, obligatoire=False):
    groupe = parser.add_argument_group("mot de passe (jamais en ligne de commande, jamais journalise)")
    groupe.add_argument("--mot-de-passe-env", metavar="NOM",
                        help="nom de la variable d'environnement qui contient le mot de passe")
    groupe.add_argument("--mot-de-passe-fichier", metavar="FICHIER",
                        help="fichier (UTF-8) dont la premiere ligne est le mot de passe")
    return groupe


def lire_mot_de_passe(args, env, obligatoire=False):
    """Mot de passe (texte) ou None. Erreur de parametres si les deux sources sont donnees, si la variable est
    vide ou le fichier illisible."""
    nom = getattr(args, "mot_de_passe_env", None)
    fichier = getattr(args, "mot_de_passe_fichier", None)
    if nom and fichier:
        raise ErreurParametres("--mot-de-passe-env et --mot-de-passe-fichier sont exclusifs")
    secret = None
    if nom:
        secret = env.get(nom)
        if not secret:
            raise ErreurParametres("la variable d'environnement %s est absente ou vide" % nom)
    elif fichier:
        try:
            with open(fichier, encoding="utf-8-sig") as f:
                secret = f.readline().rstrip("\r\n")
        except OSError as e:
            raise ErreurParametres("fichier de mot de passe illisible : %s" % (e.strerror or e))
        if not secret:
            raise ErreurParametres("le fichier de mot de passe est vide")
    if obligatoire and not secret:
        raise ErreurParametres("un mot de passe est obligatoire : --mot-de-passe-env NOM ou "
                               "--mot-de-passe-fichier FICHIER")
    return secret
