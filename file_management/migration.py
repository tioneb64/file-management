"""Migration de l'ancien script (copies.conf + historique JSON) vers la v2.

  * convertir_conf : copies.conf -> fichier de parametrage JSON Lines (une regle par ligne) ;
  * importer_historique : l'historique de l'ancien script devient la memoire de la v2, pour que les
    fichiers deja copies ne soient PAS relivres.

Specification : docs/03-base-de-donnees.md section 8, docs/09-migration-et-recette.md.
"""
import datetime
import json
import os
import re
import time

from file_management import base as modele_base
from file_management import chemins, selection
from file_management.controles import verifier_fichier

VRAIS = ("oui", "o", "yes", "y", "true", "1")
FAUX = ("non", "n", "no", "false", "0", "")
RE_CRITERE = re.compile(r"^J(?:-(\d+))?$")


class ErreurMigration(Exception):
    pass


class LigneAncienne(object):
    def __init__(self, numero, source, cible, critere, jours, masques, recursif):
        self.numero = numero
        self.source = source
        self.cible = cible
        self.critere = critere          # "TOUT", "J", "J-N" (texte normalise)
        self.jours = jours              # None = TOUT, sinon N
        self.masques = masques
        self.recursif = recursif


def lire_ancienne_conf(chemin):
    """Lit un copies.conf (format de l'ancien script : source | cible | critere | masque | recursif).
    Renvoie la liste des LigneAncienne ; leve ErreurMigration avec TOUTES les erreurs de ligne."""
    if not os.path.isfile(chemin):
        raise ErreurMigration("fichier introuvable : %s" % chemin)
    lignes, erreurs = [], []
    with open(chemin, encoding="utf-8-sig") as f:
        for numero, brute in enumerate(f, 1):
            ligne = brute.strip()
            if not ligne or ligne.startswith("#"):
                continue
            champs = [c.strip() for c in ligne.split("|")]
            try:
                lignes.append(_analyser(numero, champs))
            except ErreurMigration as e:
                erreurs.append("ligne %d : %s" % (numero, e))
    if erreurs:
        raise ErreurMigration("copies.conf invalide :\n  " + "\n  ".join(erreurs))
    if not lignes:
        raise ErreurMigration("aucune regle dans %s" % chemin)
    return lignes


def _analyser(numero, champs):
    if not 3 <= len(champs) <= 5:
        raise ErreurMigration("3 a 5 champs attendus separes par '|', %d trouves" % len(champs))
    if not champs[0] or not champs[1]:
        raise ErreurMigration("dossier source ou cible vide")
    texte = champs[2].upper().replace(" ", "")
    if texte in ("TOUT", "ALL", "*"):
        critere, jours = "TOUT", None
    else:
        m = RE_CRITERE.match(texte)
        if not m:
            raise ErreurMigration("critere de selection invalide '%s' (attendu : J, J-1, J-7, TOUT...)" % champs[2])
        jours = int(m.group(1)) if m.group(1) else 0
        critere = "J" if jours == 0 else "J-%d" % jours
    masques = ["*"]
    if len(champs) >= 4 and champs[3]:
        masques = [m.strip() for m in champs[3].split(";") if m.strip()] or ["*"]
    recursif = False
    if len(champs) == 5:
        v = champs[4].strip().lower()
        if v in VRAIS:
            recursif = True
        elif v not in FAUX:
            raise ErreurMigration("valeur 'recursif' invalide '%s' (attendu : oui / non)" % champs[4])
    return LigneAncienne(numero, champs[0], champs[1], critere, jours, masques, recursif)


def _nom_court(chemin):
    morceaux = [m for m in re.split(r"[\\/]+", os.path.expandvars(chemin)) if m and m not in (".", "..")]
    texte = re.sub(r"[^a-z0-9]+", "_", (morceaux[-1] if morceaux else "dossier").lower()).strip("_")
    return texte or "dossier"


def identifiant(ligne):
    """Identifiant PROVISOIRE de la regle : copie_<numero de ligne>_<dernier dossier de la source>.
    L'id ne doit plus changer apres le premier lancement : le renommer avant, si besoin."""
    return ("copie_%02d_%s" % (ligne.numero, _nom_court(ligne.source)))[:64].rstrip("_")


def regle_depuis_ligne(ligne, nom_fichier, actif, frequence_sec):
    retention = 90 if ligne.jours is None else max(90, ligne.jours + 31)    # doit depasser la fenetre (R08)
    description = "Migre de %s ligne %d : %s -> %s [%s, masque %s%s]" % (
        nom_fichier, ligne.numero, ligne.source, ligne.cible, ligne.critere, ";".join(ligne.masques),
        ", recursif" if ligne.recursif else "")
    return {
        "id": identifiant(ligne), "description": description, "actif": actif,
        "source": ligne.source, "cible": ligne.cible, "mode": "copie", "creer_dossiers": True,
        "selection": {"masque": ";".join(ligne.masques), "recursif": ligne.recursif,
                      "modifie_depuis": ligne.critere},
        "identite": "version", "retention_historique_jours": retention,
        # comportement de l'ancien script : fichier absent de la cible = recopie ; fichier du meme nom = ecrase
        "si_cible_absente": "recopier", "si_existe_cible": "ecraser",
        "planification": {"type": "intervalle", "frequence_sec": frequence_sec, "debut": "00:00",
                          "fin": "23:59", "jours": "tous"},
    }


def convertir_conf(chemin_conf, environnement, chemin_base, chemin_sortie, frequence_sec=3600, actives=False):
    """Ecrit le fichier de parametrage et renvoie un compte rendu (dict). Refuse d'ecraser un fichier
    existant. Les regles sont INACTIVES par defaut : on les active une a une pendant la bascule."""
    lignes = lire_ancienne_conf(chemin_conf)
    if os.path.splitext(os.path.basename(chemin_sortie))[0] != environnement:
        raise ErreurMigration("le fichier de sortie doit s'appeler %s.jsonl (le nom du fichier est celui de "
                              "l'environnement) : %s" % (environnement, chemin_sortie))
    if os.path.exists(chemin_sortie):
        raise ErreurMigration("le fichier de sortie existe deja : %s (ne jamais ecraser un parametrage)" % chemin_sortie)
    nom = os.path.basename(chemin_conf)
    regles = [regle_depuis_ligne(l, nom, actives, frequence_sec) for l in lignes]
    entete = {"version": 1, "environnement": environnement, "base": chemin_base}
    texte = "\n".join(json.dumps(x, ensure_ascii=False) for x in [entete] + regles) + "\n"
    dossier = os.path.dirname(os.path.abspath(chemin_sortie))
    os.makedirs(dossier, exist_ok=True)
    temporaire = chemin_sortie + ".tmp"
    with open(temporaire, "w", encoding="utf-8", newline="\n") as f:
        f.write(texte)
    os.replace(temporaire, chemin_sortie)

    parametrage, rapport = verifier_fichier(chemin_sortie)
    notes = ["Identifiants PROVISOIRES (copie_<ligne>_<dossier>) : les renommer avant le premier lancement, "
             "un identifiant ne peut plus changer ensuite.",
             "Planification par defaut : toutes les %d s, 24 h sur 24, tous les jours (l'ancien script etait lance "
             "au rythme du job Jenkins) : a adapter regle par regle." % frequence_sec,
             "Comportement de l'ancien script conserve : si_cible_absente = recopier, si_existe_cible = ecraser "
             "(a durcir ensuite : un fichier ecrase ne peut pas etre rattrape)."]
    if not actives:
        notes.append("Les regles sont INACTIVES : activer (actif: true) une regle a la fois pendant la bascule, apres "
                     "avoir desactive la ligne correspondante de l'ancien script.")
    if any("%" in l.source + l.cible for l in lignes):
        notes.append("Des chemins contiennent des variables %VAR% : elles doivent exister pour le COMPTE DE SERVICE "
                     "sur le serveur d'execution.")
    if any(l.recursif for l in lignes):
        notes.append("Regles recursives : verifier que la cible n'est jamais dans la source (controle R03).")
    return {"fichier": chemin_sortie, "regles": [{"id": r["id"], "ligne": l.numero, "source": l.source,
                                                  "cible": l.cible, "critere": l.critere}
                                                 for r, l in zip(regles, lignes)],
            "notes": notes, "verification": rapport, "parametrage": parametrage}


# --------------------------------------------------------------------------- #
# Historique
# --------------------------------------------------------------------------- #
def lire_historique(chemin):
    if not os.path.isfile(chemin):
        raise ErreurMigration("historique introuvable : %s" % chemin)
    try:
        with open(chemin, encoding="utf-8-sig") as f:
            contenu = json.load(f)
    except (OSError, ValueError) as e:
        raise ErreurMigration("historique illisible : %s" % e)
    if not isinstance(contenu, dict) or not isinstance(contenu.get("fichiers", {}), dict):
        raise ErreurMigration("historique invalide : objet {\"version\": 1, \"fichiers\": {...}} attendu")
    return contenu.get("fichiers", {})


def _instant(texte):
    try:
        return int(datetime.datetime.strptime(texte, "%Y-%m-%dT%H:%M:%S").timestamp())
    except (TypeError, ValueError):
        return int(time.time())


def importer_historique(parametrage, base, chemin_historique, utilisateur, commentaire=None):
    """Importe l'historique de l'ancien script : chaque fichier deja copie devient une version
    TERMINE de la regle correspondante (meme source, meme cible, meme nom relatif), donc il n'est
    pas relivre. Idempotent. Renvoie un compte rendu."""
    entrees = lire_historique(chemin_historique)
    base.synchroniser_regles([(r.id, "migration") for r in parametrage.regles if r.id])
    regles = []
    for r in parametrage.regles:
        if r.id:
            regles.append((r, chemins.normaliser(r.source), chemins.normaliser(r.cible),
                           selection.compiler_masques(r.selection.masque) or ["*"]))
    par_regle, sans_regle = {}, []
    for cle_ancienne, e in entrees.items():
        try:
            src = chemins.normaliser(e["source"])
            dst = chemins.normaliser(e["cible"])
            taille, mtime_ns = int(e["taille"]), int(e["mtime_ns"])
        except (KeyError, TypeError, ValueError):
            sans_regle.append(cle_ancienne)
            continue
        trouvee = None
        for r, rs, rc, masques in regles:
            if not (src.startswith(rs + os.sep) and dst.startswith(rc + os.sep)):
                continue
            rel_src, rel_dst = src[len(rs) + 1:], dst[len(rc) + 1:]
            if rel_src != rel_dst:
                continue
            if not r.selection.recursif and os.sep in rel_src:
                continue
            if not selection.correspond(os.path.basename(rel_src), masques):
                continue
            trouvee = (r, rel_src)
            break
        if trouvee is None:
            sans_regle.append(cle_ancienne)
            continue
        r, relatif = trouvee
        instant = _instant(e.get("copie_le"))
        par_regle.setdefault(r.id, []).append(
            (modele_base.cle_version(r.id, relatif, taille, mtime_ns), modele_base.jour_de(instant), instant))
    compte = {"entrees": len(entrees), "importees": 0, "deja_connues": 0, "sans_regle": len(sans_regle),
              "par_regle": {}, "exemples_sans_regle": sans_regle[:5]}
    for ident, lignes in par_regle.items():
        no = base.numero_regle(ident)
        nouvelles = base.importer_termines(no, lignes)
        compte["importees"] += nouvelles
        compte["deja_connues"] += len(lignes) - nouvelles
        compte["par_regle"][ident] = nouvelles
        base.journaliser_action(no, "migration", utilisateur, commentaire,
                                "%d fichier(s) importe(s) depuis %s" % (nouvelles, os.path.basename(chemin_historique)))
    return compte
