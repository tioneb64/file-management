#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
copie_fichiers.py - Copie incrementale et verifiee de fichiers (production -> test).

Lit un fichier de parametrage (une regle par ligne), selectionne les fichiers
par date de modification, copie uniquement ceux qui n'ont pas deja ete copies,
et verifie chaque copie par SHA-256 avant de la valider.

Codes retour (exploites par Jenkins) :
  0 : tout s'est bien passe
  1 : au moins une regle ou une copie en erreur
  2 : erreur dans le fichier de parametrage, l'historique ou les arguments
  3 : une autre execution est deja en cours (verrou)

Compatible Python 3.6+ (Windows Server 2016 OK).
"""

import argparse
import datetime
import fnmatch
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import sys
import time

CODE_OK = 0
CODE_ERREUR_COPIE = 1
CODE_ERREUR_CONFIG = 2
CODE_DEJA_EN_COURS = 3

TAILLE_BLOC = 4 * 1024 * 1024          # lecture par blocs de 4 Mo
SUFFIXE_TMP = ".copie_en_cours"         # fichier temporaire cote cible
SEPARATEUR = "|"                        # interdit dans les noms Windows -> sans ambiguite

log = logging.getLogger("copie_fichiers")


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class ErreurConfig(Exception):
    """Erreur de parametrage ou d'historique : on ne lance rien."""


class FichierInstable(Exception):
    """Le fichier source a change pendant la copie (encore en cours d'ecriture)."""


class DejaEnCours(Exception):
    """Une autre instance du script tient le verrou."""


# --------------------------------------------------------------------------- #
# Parametrage
# --------------------------------------------------------------------------- #
class Regle(object):
    def __init__(self, num_ligne, source, cible, jours, masques, recursif):
        self.num_ligne = num_ligne
        self.source = source
        self.cible = cible
        self.jours = jours            # None = TOUT, 0 = J, 1 = J-1, ...
        self.masques = masques
        self.recursif = recursif

    def libelle_critere(self):
        if self.jours is None:
            return "TOUT"
        return "J" if self.jours == 0 else "J-%d" % self.jours

    def __str__(self):
        return "Regle ligne %d : %s -> %s [%s, masque %s%s]" % (
            self.num_ligne, self.source, self.cible, self.libelle_critere(),
            ";".join(self.masques), ", recursif" if self.recursif else "")


def analyser_critere(texte):
    t = texte.upper().replace(" ", "")
    if t in ("TOUT", "ALL", "*"):
        return None
    m = re.match(r"^J(?:-(\d+))?$", t)
    if not m:
        raise ErreurConfig("critere de selection invalide '%s' "
                           "(attendu : J, J-1, J-7, TOUT...)" % texte)
    return int(m.group(1)) if m.group(1) else 0


def analyser_booleen(texte):
    v = texte.strip().lower()
    if v in ("oui", "o", "yes", "y", "true", "1"):
        return True
    if v in ("non", "n", "no", "false", "0", ""):
        return False
    raise ErreurConfig("valeur 'recursif' invalide '%s' (attendu : oui / non)" % texte)


def analyser_ligne(num, champs):
    if not 3 <= len(champs) <= 5:
        raise ErreurConfig("3 a 5 champs attendus separes par '%s', %d trouves"
                           % (SEPARATEUR, len(champs)))
    if not champs[0] or not champs[1]:
        raise ErreurConfig("dossier source ou cible vide")

    source = os.path.normpath(os.path.expandvars(champs[0]))
    cible = os.path.normpath(os.path.expandvars(champs[1]))
    jours = analyser_critere(champs[2])

    masques = ["*"]
    if len(champs) >= 4 and champs[3]:
        masques = [m.strip() for m in champs[3].split(";") if m.strip()] or ["*"]

    recursif = analyser_booleen(champs[4]) if len(champs) == 5 else False

    ns = os.path.normcase(os.path.abspath(source))
    nc = os.path.normcase(os.path.abspath(cible))
    if ns == nc:
        raise ErreurConfig("le dossier source et le dossier cible sont identiques")
    if recursif and (nc + os.sep).startswith(ns + os.sep):
        raise ErreurConfig("en mode recursif, la cible ne peut pas etre dans la source")

    return Regle(num, source, cible, jours, masques, recursif)


def lire_parametrage(chemin):
    if not os.path.isfile(chemin):
        raise ErreurConfig("fichier de parametrage introuvable : %s" % chemin)
    regles, erreurs = [], []
    # utf-8-sig : accepte les fichiers enregistres avec BOM par le Bloc-notes
    with open(chemin, encoding="utf-8-sig") as f:
        for num, ligne in enumerate(f, 1):
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#"):
                continue
            champs = [c.strip() for c in ligne.split(SEPARATEUR)]
            try:
                regles.append(analyser_ligne(num, champs))
            except ErreurConfig as e:
                erreurs.append("ligne %d : %s" % (num, e))
    if erreurs:
        raise ErreurConfig("parametrage invalide :\n  " + "\n  ".join(erreurs))
    if not regles:
        raise ErreurConfig("aucune regle dans %s" % chemin)
    return regles


def calculer_seuil(jours, maintenant):
    """Timestamp de J-n a 00:00:00 (heure locale), ou None pour TOUT."""
    if jours is None:
        return None
    minuit = datetime.datetime.combine(maintenant.date(), datetime.time.min)
    return (minuit - datetime.timedelta(days=jours)).timestamp()


# --------------------------------------------------------------------------- #
# Historique des copies
# --------------------------------------------------------------------------- #
class Historique(object):
    def __init__(self, chemin):
        self.chemin = chemin
        self.entrees = {}
        self.modifie = False
        if os.path.isfile(chemin):
            try:
                with open(chemin, encoding="utf-8") as f:
                    self.entrees = json.load(f).get("fichiers", {})
            except (ValueError, OSError) as e:
                # On s'arrete plutot que de tout recopier sans le savoir
                raise ErreurConfig("historique illisible %s : %s" % (chemin, e))

    @staticmethod
    def cle(src, dst):
        return (os.path.normcase(os.path.abspath(src)) + " => "
                + os.path.normcase(os.path.abspath(dst)))

    def deja_copie(self, src, dst, st):
        """Vrai si cette version du fichier source a deja ete copiee et que la copie existe."""
        e = self.entrees.get(self.cle(src, dst))
        return (e is not None
                and e.get("taille") == st.st_size
                and e.get("mtime_ns") == st.st_mtime_ns
                and os.path.isfile(dst))

    def present_mais_cible_absente(self, src, dst):
        return self.cle(src, dst) in self.entrees and not os.path.isfile(dst)

    def enregistrer(self, src, dst, st, sha):
        self.entrees[self.cle(src, dst)] = {
            "source": src,
            "cible": dst,
            "taille": st.st_size,
            "mtime_ns": st.st_mtime_ns,
            "sha256": sha,
            "copie_le": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        self.modifie = True

    def purger(self, jours_retention):
        """Oublie les copies anciennes dont le fichier source n'existe plus."""
        limite = datetime.datetime.now() - datetime.timedelta(days=jours_retention)
        a_supprimer = []
        for cle, e in self.entrees.items():
            try:
                copie_le = datetime.datetime.strptime(e.get("copie_le", ""), "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                continue
            if copie_le < limite and not os.path.exists(e.get("source", "")):
                a_supprimer.append(cle)
        for cle in a_supprimer:
            del self.entrees[cle]
        if a_supprimer:
            self.modifie = True
            log.info("Historique : %d entree(s) obsolete(s) purgee(s)", len(a_supprimer))

    def sauvegarder(self):
        if not self.modifie:
            return
        dossier = os.path.dirname(os.path.abspath(self.chemin))
        os.makedirs(dossier, exist_ok=True)
        tmp = self.chemin + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "fichiers": self.entrees}, f,
                      indent=1, ensure_ascii=False, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.chemin)   # ecriture atomique : jamais d'historique a moitie ecrit
        self.modifie = False


# --------------------------------------------------------------------------- #
# Verrou (evite deux executions simultanees ; libere automatiquement si le
# processus est tue par Jenkins)
# --------------------------------------------------------------------------- #
class Verrou(object):
    def __init__(self, chemin):
        self.chemin = chemin
        self.f = None

    def __enter__(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.chemin)), exist_ok=True)
        self.f = open(self.chemin, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, OSError):
            self.f.close()
            raise DejaEnCours("verrou deja pris : %s" % self.chemin)
        return self

    def __exit__(self, *exc):
        try:
            if os.name == "nt":
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
        except (IOError, OSError):
            pass
        finally:
            self.f.close()
        return False


# --------------------------------------------------------------------------- #
# Copie et verification
# --------------------------------------------------------------------------- #
def sha256_fichier(chemin):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(TAILLE_BLOC), b""):
            h.update(bloc)
    return h.hexdigest()


def rendre_modifiable(chemin):
    """Retire l'attribut lecture seule (sinon Windows refuse l'ecrasement)."""
    try:
        mode = os.stat(chemin).st_mode
        if not mode & stat.S_IWRITE:
            os.chmod(chemin, mode | stat.S_IWRITE)
    except FileNotFoundError:
        pass


def supprimer_silencieusement(chemin):
    try:
        rendre_modifiable(chemin)
        os.remove(chemin)
    except OSError:
        pass


def copier_verifier(src, dst):
    """
    Copie src vers dst via un fichier temporaire, puis :
      - verifie que la source n'a pas bouge pendant la copie,
      - verifie la taille et le SHA-256 de la copie,
      - renomme le temporaire en nom definitif (la cible n'est jamais visible a moitie copiee).
    Renvoie (sha256, stat de la source).
    """
    dossier = os.path.dirname(dst)
    if dossier:
        os.makedirs(dossier, exist_ok=True)
    tmp = dst + SUFFIXE_TMP
    supprimer_silencieusement(tmp)    # reliquat d'une execution interrompue

    st_avant = os.stat(src)
    h = hashlib.sha256()
    try:
        # Lecture unique de la source : on calcule son empreinte en meme temps qu'on copie
        with open(src, "rb") as fs, open(tmp, "wb") as fd:
            for bloc in iter(lambda: fs.read(TAILLE_BLOC), b""):
                h.update(bloc)
                fd.write(bloc)
            fd.flush()
            os.fsync(fd.fileno())
        sha_src = h.hexdigest()

        st_apres = os.stat(src)
        if (st_avant.st_size, st_avant.st_mtime_ns) != (st_apres.st_size, st_apres.st_mtime_ns):
            raise FichierInstable("le fichier source a ete modifie pendant la copie")

        taille_tmp = os.path.getsize(tmp)
        if taille_tmp != st_avant.st_size:
            raise IOError("taille incorrecte (source %d o, copie %d o)"
                          % (st_avant.st_size, taille_tmp))

        sha_tmp = sha256_fichier(tmp)
        if sha_tmp != sha_src:
            raise IOError("checksum different (source %s, copie %s)" % (sha_src, sha_tmp))

        shutil.copystat(src, tmp)     # conserve la date de modification d'origine
        rendre_modifiable(dst)
        os.replace(tmp, dst)
    except BaseException:
        supprimer_silencieusement(tmp)
        raise

    if not os.path.isfile(dst) or os.path.getsize(dst) != st_avant.st_size:
        raise IOError("fichier cible absent ou de taille incorrecte apres validation")
    return sha_src, st_avant


# --------------------------------------------------------------------------- #
# Traitement d'une regle
# --------------------------------------------------------------------------- #
class Stats(object):
    def __init__(self):
        self.selectionnes = 0
        self.copies = 0
        self.ignores = 0
        self.erreurs = 0

    def ajouter(self, autre):
        self.selectionnes += autre.selectionnes
        self.copies += autre.copies
        self.ignores += autre.ignores
        self.erreurs += autre.erreurs


def lister_fichiers(regle, stats):
    if regle.recursif:
        def sur_erreur(e):
            log.error("Lecture impossible : %s", e)
            stats.erreurs += 1
        for racine, dossiers, fichiers in os.walk(regle.source, onerror=sur_erreur):
            dossiers.sort()
            for nom in sorted(fichiers):
                yield os.path.join(racine, nom)
    else:
        for nom in sorted(os.listdir(regle.source)):
            chemin = os.path.join(regle.source, nom)
            if os.path.isfile(chemin):
                yield chemin


def correspond(nom, masques):
    return any(fnmatch.fnmatch(nom, m) for m in masques)


def copier_avec_essais(src, dst, essais, delai):
    for essai in range(1, essais + 1):
        try:
            return copier_verifier(src, dst)
        except (OSError, FichierInstable) as e:
            log.warning("Essai %d/%d echoue pour %s : %s", essai, essais, src, e)
            if essai < essais:
                time.sleep(delai)
    return None


def traiter_regle(regle, historique, maintenant, args):
    stats = Stats()
    seuil = calculer_seuil(regle.jours, maintenant)
    log.info("=" * 78)
    log.info("%s", regle)
    if seuil is not None:
        log.info("Fichiers modifies depuis le %s",
                 datetime.datetime.fromtimestamp(seuil).strftime("%d/%m/%Y %H:%M"))

    if not os.path.isdir(regle.source):
        log.error("Dossier source inaccessible : %s", regle.source)
        stats.erreurs += 1
        return stats
    if not args.simulation:
        try:
            os.makedirs(regle.cible, exist_ok=True)
        except OSError as e:
            log.error("Dossier cible inaccessible %s : %s", regle.cible, e)
            stats.erreurs += 1
            return stats

    try:
        for src in lister_fichiers(regle, stats):
            nom = os.path.basename(src)
            if nom.endswith(SUFFIXE_TMP) or not correspond(nom, regle.masques):
                continue
            try:
                st = os.stat(src)
            except OSError as e:
                log.error("Impossible de lire %s : %s", src, e)
                stats.erreurs += 1
                continue
            if seuil is not None and st.st_mtime < seuil:
                continue

            stats.selectionnes += 1
            dst = os.path.join(regle.cible, os.path.relpath(src, regle.source))

            if historique.deja_copie(src, dst, st):
                stats.ignores += 1
                log.debug("Deja copie : %s", src)
                continue
            if historique.present_mais_cible_absente(src, dst):
                log.info("Copie absente de la cible, recopie : %s", dst)

            if args.simulation:
                log.info("[SIMULATION] a copier : %s -> %s", src, dst)
                stats.copies += 1
                continue

            # Fichier deja present a l'identique (ex : historique perdu) -> on l'enregistre sans recopier
            if os.path.isfile(dst) and os.path.getsize(dst) == st.st_size:
                try:
                    sha = sha256_fichier(src)
                    if sha == sha256_fichier(dst):
                        historique.enregistrer(src, dst, st, sha)
                        stats.ignores += 1
                        log.info("Deja present a l'identique : %s", dst)
                        continue
                except OSError:
                    pass   # on tentera une copie normale

            resultat = copier_avec_essais(src, dst, args.essais, args.delai)
            if resultat is None:
                log.error("ECHEC   %s -> %s", src, dst)
                stats.erreurs += 1
                continue
            sha, st_copie = resultat
            historique.enregistrer(src, dst, st_copie, sha)
            stats.copies += 1
            log.info("COPIE   %s -> %s (%d o, sha256 %s)", src, dst, st_copie.st_size, sha)
    except OSError as e:
        log.error("Erreur lors du parcours de %s : %s", regle.source, e)
        stats.erreurs += 1
    finally:
        if not args.simulation:
            historique.sauvegarder()

    log.info("Bilan : %d selectionne(s), %d copie(s)%s, %d deja copie(s), %d erreur(s)",
             stats.selectionnes, stats.copies, " a faire" if args.simulation else "",
             stats.ignores, stats.erreurs)
    return stats


# --------------------------------------------------------------------------- #
# Programme principal
# --------------------------------------------------------------------------- #
def configurer_logs(args):
    # Evite les plantages d'encodage dans la console Jenkins (accents dans les noms)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    log.setLevel(logging.DEBUG if args.verbeux else logging.INFO)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    log.addHandler(console)
    if args.log:
        os.makedirs(os.path.dirname(os.path.abspath(args.log)), exist_ok=True)
        fichier = logging.FileHandler(args.log, encoding="utf-8")
        fichier.setFormatter(fmt)
        log.addHandler(fichier)


def main(argv=None):
    p = argparse.ArgumentParser(description="Copie incrementale et verifiee de fichiers (prod -> test).")
    p.add_argument("-c", "--config", required=True, help="fichier de parametrage")
    p.add_argument("--historique", help="fichier d'historique JSON (defaut : <config>.historique.json)")
    p.add_argument("--log", help="fichier de log en plus de la console")
    p.add_argument("--simulation", action="store_true", help="affiche ce qui serait copie, sans rien copier")
    p.add_argument("--essais", type=int, default=3, help="nombre d'essais par fichier (defaut 3)")
    p.add_argument("--delai", type=int, default=10, help="secondes entre deux essais (defaut 10)")
    p.add_argument("--retention", type=int, default=90,
                   help="jours avant purge des entrees d'historique dont la source a disparu (defaut 90)")
    p.add_argument("-v", "--verbeux", action="store_true", help="affiche aussi les fichiers ignores")
    args = p.parse_args(argv)

    if args.essais < 1 or args.delai < 0 or args.retention < 1:
        p.error("--essais >= 1, --delai >= 0 et --retention >= 1 attendus")

    configurer_logs(args)
    chemin_historique = args.historique or os.path.splitext(args.config)[0] + ".historique.json"
    log.info("Parametrage : %s | Historique : %s%s", args.config, chemin_historique,
             " | MODE SIMULATION" if args.simulation else "")

    try:
        regles = lire_parametrage(args.config)
    except ErreurConfig as e:
        log.error("%s", e)
        return CODE_ERREUR_CONFIG

    try:
        with Verrou(chemin_historique + ".lock"):
            try:
                historique = Historique(chemin_historique)
            except ErreurConfig as e:
                log.error("%s", e)
                return CODE_ERREUR_CONFIG

            maintenant = datetime.datetime.now()
            total = Stats()
            for regle in regles:
                total.ajouter(traiter_regle(regle, historique, maintenant, args))

            if not args.simulation:
                historique.purger(args.retention)
                historique.sauvegarder()
    except DejaEnCours as e:
        log.error("Une autre execution est en cours (%s)", e)
        return CODE_DEJA_EN_COURS

    log.info("=" * 78)
    log.info("TOTAL : %d regle(s), %d selectionne(s), %d copie(s)%s, %d deja copie(s), %d erreur(s)",
             len(regles), total.selectionnes, total.copies,
             " a faire" if args.simulation else "", total.ignores, total.erreurs)
    return CODE_ERREUR_COPIE if total.erreurs else CODE_OK


if __name__ == "__main__":
    sys.exit(main())
