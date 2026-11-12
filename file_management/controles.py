"""Controles qui comparent plusieurs regles entre elles (docs/01-parametrage.md, section 7.1)."""
import os

from file_management.diagnostic import Rapport
from file_management.parametrage import CONDITIONS, charger

SECONDES_PAR_JOUR = 86400


def _chemin(texte):
    return os.path.normcase(os.path.normpath(os.path.expandvars(texte)))


def _cle(ident):
    return ident.lower()


def controler_regles(p, rapport, periode_declencheur_sec=None):
    regles = p.regles
    if p.entete is not None and p.entete.suspendu:
        rapport.signaler("S01", "environnement SUSPENDU : aucune regle ne sera lancee%s"
                         % ((" (" + p.entete.motif_suspension + ")") if p.entete.motif_suspension else ""))
    _controler_ids(regles, rapport)
    par_id = {}
    for r in regles:
        if r.id and _cle(r.id) not in par_id:
            par_id[_cle(r.id)] = r
    for r in regles:
        _controler_regle_seule(r, rapport, periode_declencheur_sec)
    _controler_dependances(regles, par_id, rapport)
    _controler_doublons(regles, par_id, rapport)


def _controler_ids(regles, rapport):
    vus = {}
    for r in regles:
        if not r.id:
            continue
        precedente = vus.get(_cle(r.id))
        if precedente is not None:
            rapport.signaler("R02", "id '%s' deja utilise a la ligne %d (la casse ne compte pas)"
                             % (r.id, precedente), regle=r.id, ligne=r.ligne)
        else:
            vus[_cle(r.id)] = r.ligne


def _controler_regle_seule(r, rapport, periode_declencheur_sec):
    def signaler(code, message):
        rapport.signaler(code, message, regle=r.etiquette, ligne=r.ligne)

    if r.source and r.cible:
        source, cible = _chemin(r.source), _chemin(r.cible)
        if source == cible:
            signaler("R03", "la source et la cible sont identiques : %s" % r.source)
        elif r.selection.recursif and (cible + os.sep).startswith(source + os.sep):
            signaler("R03", "en mode recursif, la cible ne peut pas etre dans la source")

    if r.retention_archive_jours is not None and (
            r.mode != "archivage" or not r.archive or "{AAAA}" not in r.archive):
        signaler("R13", "retention_archive_jours n'est possible qu'en mode archivage avec une archive datee "
                 "(par exemple .\\archive\\{AAAA}-{MM}-{JJ}) : la date du dossier est la seule date d'archivage fiable")

    fenetre = r.selection.fenetre_jours()
    if fenetre is not None and r.retention_historique_jours <= fenetre:
        signaler("R08", "retention_historique_jours (%d) doit etre superieure a la fenetre de "
                 "selection (%d jours)" % (r.retention_historique_jours, fenetre))

    attentes = sum((s.tentatives - 1) * s.delai_sec for s in r.situations.values())
    if r.duree_max_sec < attentes:
        signaler("R09", "duree_max_sec (%d) est inferieure a la somme des attentes prevues dans "
                 "'situations' (%d s)" % (r.duree_max_sec, attentes))

    pl = r.planification
    if (pl is not None and pl.type == "intervalle" and pl.frequence_sec
            and periode_declencheur_sec and pl.frequence_sec < periode_declencheur_sec):
        signaler("P02", "frequence_sec (%d) est inferieure a la periode du declencheur Jenkins "
                 "(%d s) : des creneaux seront sautes" % (pl.frequence_sec, periode_declencheur_sec))


def _heure_debut(r):
    pl = r.planification
    if pl is None:
        return None
    return pl.debut if pl.type == "intervalle" else pl.heure if pl.type == "quotidien" else None


def _frequence(r):
    pl = r.planification
    if pl is None:
        return None
    if pl.type == "intervalle":
        return pl.frequence_sec
    return SECONDES_PAR_JOUR if pl.type == "quotidien" else None


def _controler_dependances(regles, par_id, rapport):
    graphe = {}                       # id -> ids dont la regle depend (existants seulement)
    for r in regles:
        pl = r.planification
        etiquette = r.etiquette

        def signaler(code, message, r=r, etiquette=etiquette):
            rapport.signaler(code, message, regle=etiquette, ligne=r.ligne)

        inconnues = [c for c in r.condition if c not in CONDITIONS]
        if inconnues:
            signaler("D06", "condition inconnue : %s (attendu : %s)"
                     % (", ".join(inconnues), ", ".join(CONDITIONS)))
        if not r.apres:
            if pl is not None and pl.type == "apres_dependances":
                signaler("D06", "la planification 'apres_dependances' impose une liste 'apres'")
            elif r.condition_explicite and r.condition != ["succes"]:
                signaler("D06", "'condition' sans 'apres' n'a pas de sens")
        liens = graphe.setdefault(_cle(r.id) if r.id else "?%d" % r.ligne, [])
        for ref in r.apres:
            cible = par_id.get(_cle(ref))
            if cible is None:
                signaler("D01", "depend de '%s', qui n'existe pas" % ref)
                continue
            if cible is r:
                signaler("D02", "la regle depend d'elle-meme")
                continue
            if ref != cible.id:
                signaler("D01", "'%s' : la casse differe de l'id '%s'" % (ref, cible.id))
            liens.append(_cle(cible.id))
            if r.actif and not cible.actif:
                signaler("D03", "depend de '%s', qui est inactive" % cible.id)
            _comparer_horaires(r, cible, signaler)

    _chercher_boucles(graphe, par_id, rapport)


def _jours_communs(a, b):
    return bool(a.planification.jours & b.planification.jours)


def _comparer_horaires(r, dependance, signaler):
    """D04 et D05 : la regle `r` attend `dependance`."""
    if r.planification is None or dependance.planification is None:
        return
    debut_r, debut_d = _heure_debut(r), _heure_debut(dependance)
    if (debut_r is not None and debut_d is not None and debut_r < debut_d
            and _jours_communs(r, dependance)):
        signaler("D04", "demarre a %02d:%02d, avant '%s' (%02d:%02d) : elle lirait le resultat de "
                 "la veille" % (debut_r // 60, debut_r % 60, dependance.id,
                                debut_d // 60, debut_d % 60))
    freq_r, freq_d = _frequence(r), _frequence(dependance)
    if freq_r is not None and freq_d is not None and freq_r < freq_d:
        signaler("D05", "plus frequente (%d s) que '%s' (%d s)" % (freq_r, dependance.id, freq_d))


def _chercher_boucles(graphe, par_id, rapport):
    BLANC, GRIS, NOIR = 0, 1, 2
    couleur = {n: BLANC for n in graphe}
    signalees = set()

    def visiter(depart):
        pile = [(depart, iter(graphe.get(depart, [])))]
        chemin = [depart]
        couleur[depart] = GRIS
        while pile:
            noeud, suivants = pile[-1]
            for voisin in suivants:
                if couleur.get(voisin, BLANC) == GRIS:
                    cycle = chemin[chemin.index(voisin):] + [voisin]
                    cle = frozenset(cycle)
                    if cle not in signalees:
                        signalees.add(cle)
                        noms = " -> ".join(par_id[n].id if n in par_id else n for n in cycle)
                        premier = par_id.get(voisin)
                        rapport.signaler("D02", "boucle de dependances : %s" % noms,
                                         regle=premier.id if premier else None,
                                         ligne=premier.ligne if premier else None)
                elif couleur.get(voisin, BLANC) == BLANC:
                    couleur[voisin] = GRIS
                    chemin.append(voisin)
                    pile.append((voisin, iter(graphe.get(voisin, []))))
                    break
            else:
                couleur[noeud] = NOIR
                chemin.pop()
                pile.pop()

    for n in list(graphe):
        if couleur[n] == BLANC:
            visiter(n)


def _atteignables(graphe, depart):
    vus, a_voir = set(), [depart]
    while a_voir:
        for suivant in graphe.get(a_voir.pop(), []):
            if suivant not in vus:
                vus.add(suivant)
                a_voir.append(suivant)
    return vus


def _controler_doublons(regles, par_id, rapport):
    """R10 (meme source, cible, masque) et R11 (meme cible sans dependance).

    Les regles sont regroupees par cible : on ne compare que celles qui la partagent."""
    graphe = {_cle(r.id): [_cle(a) for a in r.apres if _cle(a) in par_id]
              for r in regles if r.id}
    par_cible = {}
    for r in regles:
        if r.id and r.source and r.cible:
            par_cible.setdefault(_chemin(r.cible), []).append(r)
    atteignables = {}

    def en_aval(ident):
        if ident not in atteignables:
            atteignables[ident] = _atteignables(graphe, ident)
        return atteignables[ident]

    for groupe in par_cible.values():
        for i, a in enumerate(groupe):
            for b in groupe[i + 1:]:
                if (_chemin(a.source) == _chemin(b.source)
                        and a.selection.masque.strip().lower() == b.selection.masque.strip().lower()):
                    rapport.signaler("R10", "meme source, cible et masque que '%s' (ligne %d)"
                                     % (a.id, a.ligne), regle=b.id, ligne=b.ligne)
                if a.actif and b.actif and _cle(b.id) not in en_aval(_cle(a.id))                         and _cle(a.id) not in en_aval(_cle(b.id)):
                    rapport.signaler("R11", "ecrit dans la meme cible que '%s' (ligne %d) sans "
                                     "dependance entre les deux" % (a.id, a.ligne),
                                     regle=b.id, ligne=b.ligne)


def verifier_fichier(chemin, periode_declencheur_sec=None):
    """Lecture + controles croises : renvoie (Parametrage ou None, Rapport)."""
    rapport = Rapport()
    p, rapport = charger(chemin, rapport)
    if p is not None:
        controler_regles(p, rapport, periode_declencheur_sec)
    return p, rapport
