"""Controles d'acces (docs/01-parametrage.md, section 7.3) : A01 a A07.

A executer SUR LE SERVEUR D'EXECUTION avec le COMPTE DE SERVICE : les droits et les quotas
verifies sont ceux du compte qui lancera les regles. Aucun fichier n'est conserve : les essais
d'ecriture creent puis suppriment `.test_ecriture_<pid>`, et aucun dossier n'est cree (un
dossier absent est juge d'apres son plus proche parent existant).
"""
import datetime
import os
import shutil

from file_management import base as modele_base
from file_management import chemins

MO = 1024 * 1024


def essai_ecriture(dossier):
    """(ok, detail) : un fichier d'essai est cree puis supprime dans un dossier EXISTANT."""
    if not os.path.isdir(dossier):
        return False, "%s n'est pas un dossier" % dossier
    essai = os.path.join(dossier, ".test_ecriture_%d" % os.getpid())
    try:
        with open(essai, "wb") as f:
            f.write(b"x")
        os.remove(essai)
    except OSError as e:
        return False, "ecriture impossible dans %s : %s" % (dossier, e)
    return True, ""


def tester_ecriture(dossier, creer_dossiers=True, essai=essai_ecriture):
    """(ok, detail). Un dossier absent n'est accepte que si `creer_dossiers` est vrai ET si son plus
    proche parent existant est accessible en ecriture (il sera cree au premier lancement)."""
    absolu = os.path.abspath(dossier)
    existant = chemins.plus_proche_existant(absolu)
    sera_cree = os.path.normcase(existant) != os.path.normcase(absolu)
    if sera_cree and not creer_dossiers:
        return False, "le dossier n'existe pas et creer_dossiers vaut false"
    ok, detail = essai(existant)
    if not ok:
        return False, detail
    return True, ("le dossier sera cree dans %s" % existant) if sera_cree else ""


def tester_lecture(dossier):
    try:
        with os.scandir(dossier) as it:
            next(iter(it), None)
    except OSError as e:
        return False, str(e)
    return True, ""


def executable_present(commande):
    """None si l'element 0 contient une variable (non verifiable a l'avance), sinon vrai/faux."""
    premier = os.path.expandvars(commande[0])
    if "{" in premier:
        return None
    if os.path.dirname(premier) or os.path.isabs(premier):
        return os.path.isfile(premier)
    return shutil.which(premier) is not None


class Controleur(object):
    def __init__(self, parametrage, rapport, maintenant=None):
        self.p = parametrage
        self.e = parametrage.entete
        self.rapport = rapport
        self.maintenant = maintenant or datetime.datetime.now()
        self._essais = {}

    def _essai(self, existant):
        """Un seul fichier d'essai par dossier existant, meme si des centaines de regles l'utilisent."""
        cle = os.path.normcase(existant)
        if cle not in self._essais:
            self._essais[cle] = essai_ecriture(existant)
        return self._essais[cle]

    def ecriture(self, dossier, creer):
        return tester_ecriture(dossier, creer, essai=self._essai)

    def executer(self):
        self.base()
        self.dossiers_techniques()
        for regle in self.p.regles:
            if regle.id and regle.actif:
                self.regle(regle)
        return self.rapport

    def signaler(self, code, message, regle=None):
        self.rapport.signaler(code, message, regle=regle.id if regle else None,
                              ligne=regle.ligne if regle else None)

    # ----- A05 ----------------------------------------------------------- #
    def base(self):
        chemin = self.e.base
        try:
            modele_base.verifier_disque_local(chemin)
        except modele_base.ErreurBase as e:
            self.rapport.signaler("A05", str(e))
            return
        if not os.path.isfile(chemin):
            self.rapport.signaler("A05", "base absente : %s (la creer avec --initialiser-base ; sans base, "
                                         "rien n'est copie)" % chemin)
            return
        try:
            with modele_base.ouvrir(chemin, self.e.environnement) as b:
                with b.transaction():
                    pass
        except modele_base.ErreurBase as e:
            self.rapport.signaler("A05", "base inutilisable : %s" % e)

    # ----- A06 ----------------------------------------------------------- #
    def dossiers_techniques(self):
        for nom, dossier in (("journaux", self.e.dossier_logs), ("travail", self.e.dossier_travail)):
            if not dossier:
                continue
            ok, detail = self.ecriture(dossier, True)
            if not ok:
                consequence = ("les evenements iront dans le fichier de secours" if nom == "journaux"
                               else "les resultats des processus fils seront relus en base")
                self.rapport.signaler("A06", "dossier de %s inaccessible (%s) : %s" % (nom, dossier, detail)
                                      + " ; " + consequence)

    # ----- A01 a A04 et A07 ------------------------------------------------ #
    def regle(self, regle):
        source = os.path.normpath(os.path.expandvars(regle.source))
        cible = os.path.normpath(os.path.expandvars(regle.cible)) if regle.cible else None

        ok, detail = tester_lecture(source)
        if not ok:
            self.signaler("A01", "source illisible (%s) : %s" % (source, detail), regle)

        if regle.mode == "suppression":
            ok, detail = self.ecriture(source, False)       # supprimer demande le droit d'ecrire dans la source
            if not ok:
                self.signaler("A01", "source non modifiable, la suppression echouera (%s) : %s" % (source, detail), regle)
        if cible is not None and regle.mode in ("copie", "deplacement", "archivage"):
            ok, detail = self.ecriture(cible, regle.creer_dossiers)
            if not ok:
                self.signaler("A02", "cible inaccessible en ecriture (%s) : %s" % (cible, detail), regle)
        if regle.dossier_temporaire and cible is not None:
            temporaire = os.path.normpath(os.path.expandvars(regle.dossier_temporaire))
            ok, detail = self.ecriture(temporaire, regle.creer_dossiers)
            if not ok:
                self.signaler("A02", "dossier temporaire inaccessible en ecriture (%s) : %s" % (temporaire, detail), regle)
            elif not chemins.meme_volume(temporaire, cible):
                self.signaler("A02", "dossier_temporaire (%s) doit etre sur le meme volume que la cible (%s) : "
                                     "le renommage final doit etre atomique" % (temporaire, cible), regle)

        archive = None
        if regle.mode == "archivage" and regle.archive:
            archive = chemins.resoudre_archive(regle.archive, source, self.maintenant)
            ok, detail = self.ecriture(archive, regle.creer_dossiers)
            if not ok:
                self.signaler("A03", "archive inaccessible en ecriture (%s) : %s ; les fichiers seraient livres "
                                     "puis archives plus tard (mode degrade)" % (archive, detail), regle)

        for point, programme in regle.programmes.items():
            if programme is None:
                continue
            present = executable_present(programme.commande)
            if present is False:
                self.signaler("A04", "programme %s introuvable : %s" % (point, programme.commande[0]), regle)

        for libelle, dossier in (("cible", cible if regle.mode in ("copie", "deplacement", "archivage") else None),
                                 ("archive", archive)):
            if dossier is None:
                continue
            try:
                libre = chemins.espace_disponible(dossier)
            except OSError:
                continue
            self.signaler("A07", "espace disponible pour le compte de service sur la %s (%s) : %d Mo"
                          % (libelle, dossier, libre // MO), regle)


def verifier_acces(parametrage, rapport, maintenant=None):
    """Ajoute au rapport les diagnostics A01 a A07 des regles actives."""
    return Controleur(parametrage, rapport, maintenant).executer()


# --------------------------------------------------------------------------- #
# Controles d'une regle pour la simulation du front-end (--lancer-regle --simulation)
# --------------------------------------------------------------------------- #
def _controle_dossier(role, chemin, ecriture_requise, creer_dossiers, creable):
    """Un dossier : existe, lecture, ecriture (droit de creer s'il est absent), et s'il peut etre cree.
    `ecriture_requise` : faux pour une source en mode copie (on n'y supprime rien).
    Un fichier d'essai `.test_ecriture_<pid>` est cree puis supprime aussitot (comme --verifier)."""
    c = {"role": role, "chemin": chemin, "existe": os.path.isdir(chemin), "lecture": None, "ecriture": None,
         "a_creer": False, "detail": ""}
    if c["existe"]:
        c["lecture"], detail_lecture = tester_lecture(chemin)
        detail = [detail_lecture] if detail_lecture else []
        if ecriture_requise:
            c["ecriture"], detail_ecriture = essai_ecriture(chemin)
            if detail_ecriture:
                detail.append(detail_ecriture)
        c["detail"] = " ; ".join(detail)
        return c
    if not creable:
        c["detail"] = "le dossier n'existe pas"
        return c
    ok, detail = tester_ecriture(chemin, True)
    c["ecriture"] = ok
    c["a_creer"] = ok
    c["detail"] = detail or "le dossier n'existe pas"
    if role == "source":
        c["detail"] += " ; le moteur ne cree jamais la source seul : seul un administrateur peut la creer, sur demande"
    elif ok and not creer_dossiers:
        c["detail"] += " ; la regle a creer_dossiers = false : le moteur ne le creera pas seul"
    return c


def _controle_espace(c, chemin, besoin):
    try:
        libre = chemins.espace_disponible(chemin)
    except OSError:
        return
    c["espace"] = {"libre_octets": libre, "necessaire_octets": besoin, "suffisant": libre >= besoin}


def controler_dossiers_regle(regle, entete, octets=0, maintenant=None):
    """Liste de controles (source, cible, temporaire, archive) pour la simulation d'une regle :
    existence, droits de lecture et d'ecriture, espace disponible pour les `octets` a livrer plus la
    marge, et possibilite de creer un dossier absent. Meme logique que le lancement reel."""
    maintenant = maintenant or datetime.datetime.now()
    source = os.path.normpath(os.path.expandvars(regle.source))
    besoin = octets + entete.marge_espace_mo * MO
    resultat = [_controle_dossier("source", source, regle.mode not in ("copie", "count", "size"),
                                  regle.creer_dossiers, True)]
    if regle.mode not in ("copie", "deplacement", "archivage"):
        return resultat                 # suppression, count, size : ni cible ni archive
    cible = os.path.normpath(os.path.expandvars(regle.cible))
    c = _controle_dossier("cible", cible, True, regle.creer_dossiers, True)
    _controle_espace(c, cible, besoin)
    resultat.append(c)
    if regle.dossier_temporaire:
        temporaire = os.path.normpath(os.path.expandvars(regle.dossier_temporaire))
        c = _controle_dossier("temporaire", temporaire, True, regle.creer_dossiers, True)
        if not chemins.meme_volume(temporaire, cible):
            c["detail"] = (c["detail"] + " ; " if c["detail"] else "") + \
                "doit etre sur le meme volume que la cible (renommage atomique)"
            c["volume_incorrect"] = True
        resultat.append(c)
    if regle.mode == "archivage" and regle.archive:
        archive = chemins.resoudre_archive(regle.archive, source, maintenant)
        c = _controle_dossier("archive", archive, True, regle.creer_dossiers, True)
        if not chemins.meme_volume(source, archive):
            _controle_espace(c, archive, besoin)
        resultat.append(c)
    return resultat
