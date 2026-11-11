"""Comparaison avec la version precedente du parametrage (docs/01-parametrage.md, section 7.2).

Appelee par le front-end avant d'enregistrer une modification (`--verifier --precedent FICHIER`) :
V01 (refus) un id existant ne peut pas etre modifie ; V02 une regle supprimee ; V03 une selection
elargie ; V04 une cible modifiee.
"""
from file_management.chemins import normaliser
from file_management.selection import compiler_masques


def _signature(regle):
    """Ce qui identifie une regle en dehors de son id : d'ou vers ou, et quoi."""
    return (normaliser(regle.source or ""), normaliser(regle.cible or ""),
            tuple(sorted(compiler_masques(regle.selection.masque))))


def selection_elargie(ancienne, nouvelle):
    """Motif pour lequel `nouvelle` peut retenir des fichiers que `ancienne` ne retenait pas, ou None."""
    motifs = []
    a, n = ancienne.fenetre_jours(), nouvelle.fenetre_jours()
    if a is not None and (n is None or n > a):
        motifs.append("fenetre de selection elargie (%s jour(s) -> %s)" % (a, "tout" if n is None else "%d jour(s)" % n))
    if set(compiler_masques(nouvelle.masque)) - set(compiler_masques(ancienne.masque)):
        motifs.append("masque elargi ou modifie (%s -> %s)" % (ancienne.masque, nouvelle.masque))
    if set(compiler_masques(ancienne.exclure)) - set(compiler_masques(nouvelle.exclure)):
        motifs.append("exclusion retiree (%s -> %s)" % (ancienne.exclure or "aucune", nouvelle.exclure or "aucune"))
    if nouvelle.recursif and not ancienne.recursif:
        motifs.append("sous-dossiers desormais parcourus")
    ancien_min, nouveau_min = ancienne.taille_minimum_octets, nouvelle.taille_minimum_octets
    if ancien_min is not None and (nouveau_min is None or nouveau_min < ancien_min):
        motifs.append("taille minimale abaissee")
    return " ; ".join(motifs) or None


def comparer(ancien, nouveau, rapport, base=None):
    """`ancien`, `nouveau` : objets Parametrage. `base` : base ouverte (lecture), facultative, pour
    savoir si une regle supprimee avait un historique."""
    anciennes = {r.id.lower(): r for r in ancien.regles if r.id}
    nouvelles = {r.id.lower(): r for r in nouveau.regles if r.id}
    retirees = [r for k, r in anciennes.items() if k not in nouvelles]
    ajoutees = [r for k, r in nouvelles.items() if k not in anciennes]

    # V01 : une regle retiree dont la signature se retrouve dans une regle ajoutee a ete renommee
    for r in list(retirees):
        for a in list(ajoutees):
            if _signature(r) == _signature(a):
                rapport.signaler("V01", "l'id '%s' a ete remplace par '%s' : l'historique de la regle serait "
                                        "perdu (un id existant ne peut pas etre modifie)" % (r.id, a.id),
                                 regle=a.id, ligne=a.ligne)
                retirees.remove(r)
                ajoutees.remove(a)
                break

    for r in retirees:
        historique = ""
        if base is not None:
            no = base.numero_regle(r.id)
            if no is not None and (base.derniere_execution(no) is not None):
                historique = " : son etat et ses fichiers memorises restent en base"
        rapport.signaler("V02", "la regle '%s' est supprimee%s" % (r.id, historique), regle=r.id, ligne=r.ligne)

    for cle, n in nouvelles.items():
        a = anciennes.get(cle)
        if a is None:
            continue
        motif = selection_elargie(a.selection, n.selection)
        if motif:
            rapport.signaler("V03", "la selection est elargie, des fichiers anciens pourraient etre livres : %s" % motif,
                             regle=n.id, ligne=n.ligne)
        if normaliser(a.cible or "") != normaliser(n.cible or ""):
            rapport.signaler("V04", "la cible change (%s -> %s) : les fichiers deja livres ne sont pas relivres, "
                                    "les nouveaux iront vers la nouvelle cible" % (a.cible, n.cible),
                             regle=n.id, ligne=n.ligne)
    return rapport
