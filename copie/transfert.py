"""Primitives de transfert : copie verifiee, renommage sans ecrasement, suppression controlee.

Chaque echec est signale par une exception typee, que le moteur rattache a une situation
(docs/01-parametrage.md section 6). Specification : docs/02-moteur.md section 6.
"""
import hashlib
import os
import stat

TAILLE_BLOC = 4 * 1024 * 1024
ERREURS_VERROU = (32, 33)          # ERROR_SHARING_VIOLATION, ERROR_LOCK_VIOLATION


class ErreurTransfert(Exception):
    """Echec d'une operation sur un fichier. `cause` : l'exception d'origine, s'il y en a une."""

    def __init__(self, message, cause=None):
        Exception.__init__(self, message)
        self.cause = cause


class SourceDisparue(ErreurTransfert):
    """Le fichier a disparu (pris par un autre logiciel) : situation `fichier_disparu`."""


class ErreurSource(ErreurTransfert):
    """Lecture impossible de l'original. `verrou` : ouvert par un autre processus."""

    def __init__(self, message, cause=None):
        ErreurTransfert.__init__(self, message, cause)
        self.verrou = est_verrou(cause)


class ErreurCible(ErreurTransfert):
    """Ecriture impossible cote destination (droits, disque plein, reseau)."""


class FichierInstable(ErreurTransfert):
    """L'original a change pendant la lecture : encore en cours d'ecriture."""


class ErreurVerification(ErreurTransfert):
    """Taille ou SHA-256 de la copie different de la source."""


class CibleExiste(ErreurTransfert):
    """Un fichier de ce nom existe deja a l'arrivee."""


class SourceModifiee(ErreurTransfert):
    """L'original n'est plus celui qui a ete copie : il est conserve (garantie G4)."""


def est_verrou(erreur):
    if erreur is None:
        return False
    return getattr(erreur, "winerror", None) in ERREURS_VERROU


def rendre_modifiable(chemin):
    """Retire l'attribut lecture seule (sinon Windows refuse l'ecrasement et la suppression)."""
    try:
        mode = os.stat(chemin).st_mode
        if not mode & stat.S_IWRITE:
            os.chmod(chemin, mode | stat.S_IWRITE)
    except FileNotFoundError:
        pass


def supprimer_si_existe(chemin):
    try:
        rendre_modifiable(chemin)
        os.remove(chemin)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def sha256_fichier(chemin):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(TAILLE_BLOC), b""):
            h.update(bloc)
    return h.hexdigest()


def renommer(source, destination, ecraser):
    """Renomme sans jamais ecraser par surprise : CibleExiste si `destination` existe et que
    `ecraser` est faux. Sous Windows os.rename refuse d'ecraser, de facon atomique."""
    try:
        if ecraser:
            rendre_modifiable(destination)
            os.replace(source, destination)
        elif os.name == "nt":
            os.rename(source, destination)
        else:
            if os.path.lexists(destination):
                raise FileExistsError(destination)
            os.rename(source, destination)
    except FileExistsError as e:
        raise CibleExiste("existe deja : %s" % destination, e)
    except OSError as e:
        raise ErreurCible("renommage impossible vers %s : %s" % (destination, e), e)


class Copie(object):
    def __init__(self, sha256, taille, stat_source):
        self.sha256 = sha256
        self.taille = taille
        self.stat_source = stat_source


def copier_verifier(src, dst, temporaire, ecraser=False, attendu=None):
    """Copie `src` vers `dst` via le fichier `temporaire` (meme volume que `dst`) :

      1. lecture unique de la source, calcul du SHA-256 pendant la copie ;
      2. la source n'a pas bouge (taille et date) pendant la lecture ;
      3. taille puis SHA-256 de la copie relue egaux a ceux de la source ;
      4. date de modification d'origine recopiee ;
      5. renommage atomique vers le nom definitif (CibleExiste si `ecraser` est faux).

    `attendu` : (taille, mtime_ns) vus lors du listage ; un fichier deja different au moment de
    la copie est FichierInstable (la version enregistree ne serait pas celle qui est livree).

    Le temporaire est supprime en cas d'echec : la destination n'est jamais visible a moitie
    copiee. Les exceptions sont des ErreurTransfert."""
    try:
        st_avant = os.stat(src)
    except FileNotFoundError as e:
        raise SourceDisparue("fichier disparu : %s" % src, e)
    except OSError as e:
        raise ErreurSource("lecture impossible de %s : %s" % (src, e), e)

    if attendu is not None and (st_avant.st_size, st_avant.st_mtime_ns) != tuple(attendu):
        raise FichierInstable("l'original a change depuis son listage : %s" % src)

    try:
        os.makedirs(os.path.dirname(temporaire), exist_ok=True)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
    except OSError as e:
        raise ErreurCible("dossier d'arrivee inaccessible : %s" % e, e)
    supprimer_si_existe(temporaire)             # reliquat d'une execution interrompue

    h = hashlib.sha256()
    try:
        try:
            source = open(src, "rb")
        except FileNotFoundError as e:
            raise SourceDisparue("fichier disparu : %s" % src, e)
        except OSError as e:
            raise ErreurSource("ouverture impossible de %s : %s" % (src, e), e)
        with source:
            try:
                sortie = open(temporaire, "wb")
            except OSError as e:
                raise ErreurCible("creation impossible de %s : %s" % (temporaire, e), e)
            with sortie:
                while True:
                    try:
                        bloc = source.read(TAILLE_BLOC)
                    except OSError as e:
                        erreur = ErreurSource("lecture interrompue de %s : %s" % (src, e), e)
                        # fichier deja ouvert puis refus de lecture : region verrouillee par un autre processus
                        erreur.verrou = erreur.verrou or isinstance(e, PermissionError)
                        raise erreur
                    if not bloc:
                        break
                    h.update(bloc)
                    try:
                        sortie.write(bloc)
                    except OSError as e:
                        raise ErreurCible("ecriture impossible : %s" % e, e)
                try:
                    sortie.flush()
                    os.fsync(sortie.fileno())
                except OSError as e:
                    raise ErreurCible("ecriture impossible : %s" % e, e)
        sha = h.hexdigest()

        try:
            st_apres = os.stat(src)
        except OSError as e:
            raise SourceDisparue("fichier disparu apres lecture : %s" % src, e)
        if (st_avant.st_size, st_avant.st_mtime_ns) != (st_apres.st_size, st_apres.st_mtime_ns):
            raise FichierInstable("l'original a ete modifie pendant la copie : %s" % src)

        try:
            taille_copie = os.path.getsize(temporaire)
            if taille_copie != st_avant.st_size:
                raise ErreurVerification("taille incorrecte (source %d o, copie %d o)"
                                         % (st_avant.st_size, taille_copie))
            sha_copie = sha256_fichier(temporaire)
        except OSError as e:
            raise ErreurCible("relecture impossible de la copie : %s" % e, e)
        if sha_copie != sha:
            raise ErreurVerification("SHA-256 different (source %s, copie %s)" % (sha, sha_copie))

        try:
            os.utime(temporaire, ns=(st_avant.st_atime_ns, st_avant.st_mtime_ns))
        except OSError as e:
            raise ErreurCible("date de modification non recopiee : %s" % e, e)
        renommer(temporaire, dst, ecraser)
    except BaseException:
        supprimer_si_existe(temporaire)
        raise

    try:
        taille_finale = os.path.getsize(dst)
    except OSError as e:
        raise ErreurCible("fichier absent apres renommage : %s" % e, e)
    if taille_finale != st_avant.st_size:
        raise ErreurVerification("taille incorrecte apres renommage (%d o au lieu de %d)"
                                 % (taille_finale, st_avant.st_size))
    return Copie(sha, st_avant.st_size, st_avant)


def verifier_original_inchange(chemin, taille, mtime_ns):
    """Renvoie False si l'original a disparu ; SourceModifiee s'il a change (G4)."""
    try:
        st = os.stat(chemin)
    except FileNotFoundError:
        return False
    except OSError as e:
        raise ErreurSource("lecture impossible de %s : %s" % (chemin, e), e)
    if st.st_size != taille or st.st_mtime_ns != mtime_ns:
        raise SourceModifiee("l'original a change depuis la copie : %s" % chemin)
    return True


def supprimer_original(chemin, taille, mtime_ns):
    """Mode deplacement : supprime l'original s'il est inchange. Renvoie 'supprime' ou 'absent'."""
    if not verifier_original_inchange(chemin, taille, mtime_ns):
        return "absent"
    try:
        rendre_modifiable(chemin)
        os.remove(chemin)
    except FileNotFoundError:
        return "absent"
    except OSError as e:
        raise ErreurSource("suppression impossible de %s : %s" % (chemin, e), e)
    return "supprime"
