"""Evaluation des dependances d'une regle (docs/02-moteur.md, section 3).

Pour une regle R due et chacune des regles D de `apres`, avec `ref` = debut de la derniere
execution de R (0 si jamais lancee) :

  * termine : D a termine au moins une execution apres `ref` ;
  * succes  : la derniere execution de D date d'apres `ref` et son statut est SUCCES, WARNING
              ou ACQUITTEE ;
  * fichiers: au moins une execution de D apres `ref` a livre un fichier.

Resultat : PRETE (tout est rempli), BLOQUEE (une dependance non remplie est en ERREUR ou elle-meme
BLOQUEE : seule la cause reste en rouge, l'ERREUR n'est pas propagee) ou EN_ATTENTE.
"""

PRETE, EN_ATTENTE, BLOQUEE = "PRETE", "EN_ATTENTE", "BLOQUEE"
STATUTS_REUSSIS = ("SUCCES", "WARNING", "ACQUITTEE")


class Evaluation(object):
    def __init__(self, etat, motif="", bloquante=None):
        self.etat = etat
        self.motif = motif
        self.bloquante = bloquante

    def __repr__(self):
        return "Evaluation(%s, %r, %r)" % (self.etat, self.motif, self.bloquante)


def _condition_remplie(condition, d, ref, base):
    if condition == "termine":
        return base.a_termine_apres(d["no"], ref)
    if condition == "succes":
        return (d["dernier_statut"] in STATUTS_REUSSIS and d["dernier_statut_le"] is not None
                and d["dernier_statut_le"] > ref)
    if condition == "fichiers":
        return base.a_livre_apres(d["no"], ref)
    return False


def evaluer(regle, ligne, lignes, base, bloquees=()):
    """`ligne` : ligne `regles` de R (dict) ou None ; `lignes` : {id en minuscules: ligne} de
    toutes les regles de la base ; `bloquees` : ids (minuscules) deja evalues BLOQUEE pendant ce
    lancement."""
    ref = (ligne or {}).get("dernier_lancement") or 0
    attente, bloquante, bloquee_par = [], None, None
    for ident in regle.apres:
        d = lignes.get(ident.lower())
        if d is None:
            attente.append("%s n'a jamais tourne" % ident)
            continue
        if all(_condition_remplie(c, d, ref, base) for c in regle.condition):
            continue
        en_erreur = (not d["en_cours"] and d["dernier_statut"] == "ERREUR")
        deja_bloquee = ident.lower() in bloquees or (d["attente"] == BLOQUEE and not d["en_cours"])
        if en_erreur or deja_bloquee:
            bloquante = bloquante or d["id"]
            bloquee_par = ("%s est en ERREUR" % d["id"]) if en_erreur else ("%s est elle-meme bloquee" % d["id"])
        elif d["en_cours"]:
            attente.append("%s est en cours" % d["id"])
        elif d["dernier_statut"] == "ATTENTE" and (d["dernier_statut_le"] or 0) > ref:
            attente.append("%s : %s" % (d["id"], d.get("dernier_motif") or "condition non remplie"))
        else:
            attente.append("%s n'a pas encore tourne depuis le dernier lancement" % d["id"])
    if bloquante:
        return Evaluation(BLOQUEE, "bloquee : %s" % bloquee_par, bloquante)
    if attente:
        return Evaluation(EN_ATTENTE, "en attente : " + " ; ".join(attente))
    return Evaluation(PRETE)
