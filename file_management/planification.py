"""Planification : quel est le dernier creneau echu d'une regle, est-elle due ?

Calculs en heure LOCALE du serveur d'execution (creneaux ecrits en heures murales), resultats en
secondes depuis 1970 (UTC). Specification : docs/02-moteur.md section 4.
"""
import datetime
import time

SECONDES_PAR_JOUR = 86400
JOURS_EN_ARRIERE = 8          # une regle hebdomadaire a toujours un creneau dans les 7 derniers jours


class FuseauSysteme(object):
    """Fuseau du serveur. Remplacable dans les tests par un fuseau fictif (heures d'ete)."""

    def local(self, instant):
        """datetime naif en heure murale locale (avec `fold` pour l'heure repetee)."""
        return datetime.datetime.fromtimestamp(instant)

    def epoch(self, mural):
        """Heure murale (datetime naif) -> secondes depuis 1970. Une heure supprimee au passage a
        l'heure d'ete est ramenee a l'instant qui suit ; une heure repetee a l'automne vaut sa
        premiere occurrence (fold = 0)."""
        return mural.timestamp()


FUSEAU = FuseauSysteme()


class Decision(object):
    """Resultat de l'evaluation d'une regle."""

    def __init__(self, due, declencheur=None, creneau=None, motif="", nouvelle=False):
        self.due = due
        self.declencheur = declencheur        # planifie | reprise | manuel
        self.creneau = creneau                # creneau pris par cette execution (secondes)
        self.motif = motif
        self.nouvelle = nouvelle              # regle jamais vue : son dernier creneau est considere pris

    def __repr__(self):
        return "Decision(due=%r, %r, creneau=%r, %r)" % (self.due, self.declencheur, self.creneau, self.motif)


def creneaux_du_jour(planification, jour):
    """Secondes depuis minuit des creneaux de `jour` (date), dans l'ordre. Vide si le jour n'est
    pas autorise. Intervalle : debut, debut + k x frequence, ... jusqu'a fin INCLUS."""
    if jour.weekday() not in planification.jours:
        return []
    if planification.type == "quotidien":
        return [planification.heure * 60]
    if planification.type == "intervalle":
        debut, fin = planification.debut * 60, planification.fin * 60
        return list(range(debut, fin + 1, planification.frequence_sec))
    return []


def _creneau_mural(jour, secondes):
    return datetime.datetime.combine(jour, datetime.time.min) + datetime.timedelta(seconds=secondes)


def _instant_unique(planification, fuseau):
    """Instant (secondes) du creneau unique d'une planification `unique`, ou None si la date est absente."""
    return None if planification.date_heure is None else fuseau.epoch(planification.date_heure)


def unique_executee(planification, ligne, maintenant, fuseau=FUSEAU):
    """Une planification `unique` dont le creneau a ete pris, sans suite en attente : la regle est
    consideree comme terminee (le moteur n'ecrit jamais le fichier de parametrage : `actif` y reste a true).
    `ligne` : ligne de la table `regles` (dict) ou None. Une reprise, un lancement manuel, une execution en
    cours, un arret apres erreur ou une derniere execution en ERREUR gardent la regle "vivante"."""
    if planification is None or planification.type != "unique" or ligne is None:
        return False
    instant = _instant_unique(planification, fuseau)
    if instant is None or instant > maintenant or ligne["dernier_creneau"] is None or ligne["dernier_creneau"] < instant:
        return False
    return not (ligne["en_cours"] or ligne["reprise"] or ligne["lancement_manuel"] or ligne["arret_apres_erreur"]
                or ligne["dernier_statut"] == "ERREUR")


def dernier_creneau_echu(planification, maintenant, fuseau=FUSEAU):
    """Le plus recent creneau anterieur ou egal a `maintenant`, ou None."""
    if planification is not None and planification.type == "unique":
        instant = _instant_unique(planification, fuseau)
        return instant if instant is not None and instant <= maintenant else None
    if planification is None or planification.type not in ("quotidien", "intervalle"):
        return None
    aujourdhui = fuseau.local(maintenant).date()
    for recul in range(JOURS_EN_ARRIERE):
        jour = aujourdhui - datetime.timedelta(days=recul)
        for secondes in reversed(creneaux_du_jour(planification, jour)):
            instant = fuseau.epoch(_creneau_mural(jour, secondes))
            if instant <= maintenant:
                return instant
    return None


def prochain_creneau(planification, maintenant, fuseau=FUSEAU):
    """Le premier creneau strictement posterieur a `maintenant`, ou None."""
    if planification is not None and planification.type == "unique":
        instant = _instant_unique(planification, fuseau)
        return instant if instant is not None and instant > maintenant else None
    if planification is None or planification.type not in ("quotidien", "intervalle"):
        return None
    aujourdhui = fuseau.local(maintenant).date()
    for avance in range(JOURS_EN_ARRIERE):
        jour = aujourdhui + datetime.timedelta(days=avance)
        for secondes in creneaux_du_jour(planification, jour):
            instant = fuseau.epoch(_creneau_mural(jour, secondes))
            if instant > maintenant:
                return instant
    return None


def evaluer(regle, etat, maintenant, fuseau=FUSEAU):
    """Decide si `regle` est a lancer. `etat` : ligne de la table `regles` (dict) ou None si la
    regle n'est pas encore en base. `maintenant` : secondes depuis 1970."""
    if not regle.actif:
        return Decision(False, motif="inactive")
    planification = regle.planification
    echu = dernier_creneau_echu(planification, maintenant, fuseau)
    if etat is None:
        return Decision(False, motif="regle nouvelle", creneau=echu, nouvelle=True)
    if etat["en_cours"]:
        return Decision(False, motif="deja en cours")
    if etat["reprise"]:
        return Decision(True, "reprise", echu, "reprise demandee")
    if etat["lancement_manuel"]:
        return Decision(True, "manuel", echu, "lancement manuel demande")
    apres_dependances = planification is not None and planification.type == "apres_dependances"
    unique = planification is not None and planification.type == "unique"
    # une regle `unique` deja enregistree (creneau a venir) n'est pas « nouvelle » : son creneau doit pouvoir partir
    if not apres_dependances and not unique and etat["dernier_creneau"] is None and etat["dernier_lancement"] is None:
        # jamais vue : son dernier creneau echu est considere comme deja pris (docs/02, section 4.5)
        return Decision(False, motif="regle nouvelle", creneau=echu, nouvelle=True)
    if etat["arret_apres_erreur"]:
        return Decision(False, motif="arretee apres une erreur : reprise ou acquittement requis")
    if apres_dependances or planification is None:
        # pas d'horaire : candidate a chaque lancement, l'evaluation des dependances decide
        return Decision(True, "dependance", None, "attend ses dependances")
    if echu is None:
        return Decision(False, motif="aucun creneau")
    if planification.rattrapage_sec is not None and maintenant - echu > planification.rattrapage_sec:
        return Decision(False, motif="creneau expire (rattrapage de %d s depasse)" % planification.rattrapage_sec,
                        creneau=echu)
    if etat["dernier_creneau"] is not None and echu <= etat["dernier_creneau"]:
        return Decision(False, motif="creneau deja pris", creneau=echu)
    return Decision(True, "planifie", echu, "creneau echu")


def libelle(planification):
    """Planification en clair, pour l'affichage (--etat)."""
    jours_noms = ("lun", "mar", "mer", "jeu", "ven", "sam", "dim")
    if planification is None:
        return ""
    if planification.type == "apres_dependances":
        return "apres ses dependances"
    if planification.type == "unique":
        d = planification.date_heure
        return "une seule fois, le %s a %s" % (d.strftime("%Y-%m-%d"), d.strftime("%H:%M")) if d else "une seule fois"
    jours = planification.jours
    if len(jours) == 7:
        texte_jours = "tous les jours"
    elif jours == frozenset(range(5)):
        texte_jours = "lun-ven"
    else:
        texte_jours = ",".join(jours_noms[j] for j in sorted(jours))
    if planification.type == "quotidien":
        return "a %02d:%02d, %s" % (planification.heure // 60, planification.heure % 60, texte_jours)
    f = planification.frequence_sec
    pas = "%d min" % (f // 60) if f % 60 == 0 else "%d s" % f
    return "toutes les %s de %02d:%02d a %02d:%02d, %s" % (
        pas, planification.debut // 60, planification.debut % 60,
        planification.fin // 60, planification.fin % 60, texte_jours)
