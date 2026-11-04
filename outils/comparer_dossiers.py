"""Compare deux arborescences : sert a prouver, pendant la recette, que la v2 a livre la meme chose que
l'ancien script (docs/09-migration-et-recette.md).

    C:\\Python314\\python.exe outils\\comparer_dossiers.py DOSSIER_ANCIEN DOSSIER_NOUVEAU
        [--masque *.csv] [--sans-contenu] [--dates] [--json rapport.json]

Compare, pour chaque chemin relatif (sans tenir compte de la casse) : la presence, la taille et le
SHA-256 du contenu (sauf --sans-contenu) ; avec --dates, la date de modification (a 2 s pres).
Les fichiers temporaires `.copie_en_cours` sont ignores. Code retour : 0 si identiques, 1 sinon.
Lecture seule.
"""
import argparse
import fnmatch
import hashlib
import json
import os
import sys

SUFFIXE_TEMPORAIRE = ".copie_en_cours"


def lister(racine, masque="*"):
    resultat = {}
    for dossier, _, noms in os.walk(racine):
        for nom in noms:
            if nom.endswith(SUFFIXE_TEMPORAIRE) or not fnmatch.fnmatch(nom.lower(), masque.lower()):
                continue
            chemin = os.path.join(dossier, nom)
            resultat[os.path.relpath(chemin, racine).lower()] = chemin
    return resultat


def sha256(chemin):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(bloc)
    return h.hexdigest()


def comparer(a, b, masque="*", contenu=True, dates=False):
    """Renvoie {'identiques', 'seulement_a', 'seulement_b', 'differents'} (listes de chemins relatifs)."""
    la, lb = lister(a, masque), lister(b, masque)
    resultat = {"identiques": [], "seulement_a": sorted(set(la) - set(lb)),
                "seulement_b": sorted(set(lb) - set(la)), "differents": []}
    for cle in sorted(set(la) & set(lb)):
        sa, sb = os.stat(la[cle]), os.stat(lb[cle])
        raison = None
        if sa.st_size != sb.st_size:
            raison = "taille %d / %d" % (sa.st_size, sb.st_size)
        elif contenu and sha256(la[cle]) != sha256(lb[cle]):
            raison = "contenu different"
        elif dates and abs(sa.st_mtime - sb.st_mtime) > 2:
            raison = "date de modification differente"
        if raison:
            resultat["differents"].append({"chemin": cle, "raison": raison})
        else:
            resultat["identiques"].append(cle)
    return resultat


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("ancien")
    p.add_argument("nouveau")
    p.add_argument("--masque", default="*")
    p.add_argument("--sans-contenu", action="store_true", help="ne compare pas le SHA-256 (plus rapide)")
    p.add_argument("--dates", action="store_true", help="compare aussi la date de modification")
    p.add_argument("--json", help="ecrit aussi le resultat dans ce fichier")
    args = p.parse_args(argv)
    for dossier in (args.ancien, args.nouveau):
        if not os.path.isdir(dossier):
            print("dossier introuvable : %s" % dossier, file=sys.stderr)
            return 2
    r = comparer(args.ancien, args.nouveau, args.masque, not args.sans_contenu, args.dates)
    print("identiques : %d | seulement dans l'ancien : %d | seulement dans le nouveau : %d | differents : %d" % (
        len(r["identiques"]), len(r["seulement_a"]), len(r["seulement_b"]), len(r["differents"])))
    for nom in r["seulement_a"][:50]:
        print("  seulement dans l'ancien : %s" % nom)
    for nom in r["seulement_b"][:50]:
        print("  seulement dans le nouveau : %s" % nom)
    for d in r["differents"][:50]:
        print("  different : %s (%s)" % (d["chemin"], d["raison"]))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    return 0 if not (r["seulement_a"] or r["seulement_b"] or r["differents"]) else 1


if __name__ == "__main__":
    sys.exit(main())
