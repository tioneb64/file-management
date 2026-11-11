"""Selection des fichiers candidats d'une regle (docs/02-moteur.md section 5.1)."""
import datetime
import fnmatch
import os

from file_management.parametrage import RE_MODIFIE_DEPUIS

SUFFIXE_TEMPORAIRE = ".copie_en_cours"
TOLERANCE_FUTUR_SEC = 60


class Candidat(object):
    __slots__ = ("chemin", "relatif", "nom", "taille", "mtime_ns")

    def __init__(self, chemin, relatif, taille, mtime_ns):
        self.chemin = chemin
        self.relatif = relatif
        self.nom = os.path.basename(chemin)
        self.taille = taille
        self.mtime_ns = mtime_ns

    @property
    def mtime(self):
        return self.mtime_ns / 1e9


class Resultat(object):
    def __init__(self):
        self.candidats = []
        self.vus = 0
        self.hors_masque = 0
        self.trop_recents = 0
        self.trop_anciens = 0
        self.trop_petits = 0
        self.dates_futures = []        # chemins ignores car modifies "dans le futur"
        self.erreurs = []              # [(chemin, OSError)] : lecture impossible


def compiler_masques(texte):
    """'FACT_*.xml;FACT_*.pdf' -> ['fact_*.xml', 'fact_*.pdf'] (comparaison sans la casse)."""
    return [m.strip().lower() for m in texte.split(";") if m.strip()]


def correspond(nom, masques):
    bas = nom.lower()
    return any(fnmatch.fnmatchcase(bas, m) for m in masques)


def seuil_modifie_depuis(modifie_depuis, maintenant):
    """Instant (epoch) a partir duquel un fichier est retenu, ou None pour TOUT.
    maintenant : datetime local. J = aujourd'hui 00h00, J-N = il y a N jours 00h00."""
    m = RE_MODIFIE_DEPUIS.match(modifie_depuis)
    if not m or m.group(1) == "TOUT":
        return None
    jours = int(m.group(2)) if m.group(2) else 0
    minuit = datetime.datetime.combine(maintenant.date(), datetime.time.min)
    return (minuit - datetime.timedelta(days=jours)).timestamp()


def lister(source, selection, maintenant, est_exclu=None, interdits=()):
    """Parcourt `source` selon `selection` (objet Selection). `maintenant` : datetime local.
    interdits : noms de dossiers absolus a ne pas traverser. Renvoie un Resultat ; les erreurs
    de lecture sont rapportees, jamais levees."""
    res = Resultat()
    masques = compiler_masques(selection.masque) or ["*"]
    exclus = compiler_masques(selection.exclure)
    seuil = seuil_modifie_depuis(selection.modifie_depuis, maintenant)
    maintenant_ts = maintenant.timestamp()
    interdits = {os.path.normcase(os.path.normpath(i)) for i in interdits if i}

    def parcourir(dossier, composants):
        try:
            with os.scandir(dossier) as it:
                entrees = list(it)
        except OSError as e:
            res.erreurs.append((dossier, e))
            return
        for entree in entrees:
            try:
                if entree.is_symlink():
                    continue
                if entree.is_dir():
                    if not selection.recursif:
                        continue
                    sous = composants + (entree.name,)
                    if os.path.normcase(os.path.normpath(entree.path)) in interdits:
                        continue
                    if est_exclu and est_exclu(sous):
                        continue
                    if hasattr(entree, "is_junction") and entree.is_junction():
                        continue
                    parcourir(entree.path, sous)
                    continue
                if not entree.is_file():
                    continue
                st = entree.stat()
            except OSError as e:
                res.erreurs.append((entree.path, e))
                continue
            res.vus += 1
            nom = entree.name
            if nom.endswith(SUFFIXE_TEMPORAIRE):
                continue
            if not correspond(nom, masques) or (exclus and correspond(nom, exclus)):
                res.hors_masque += 1
                continue
            mtime = st.st_mtime_ns / 1e9
            if mtime > maintenant_ts + TOLERANCE_FUTUR_SEC:
                res.dates_futures.append(entree.path)
                continue
            if seuil is not None and mtime < seuil:
                res.trop_anciens += 1
                continue
            age = maintenant_ts - mtime
            if selection.age_minimum_sec is not None and age < selection.age_minimum_sec:
                res.trop_recents += 1
                continue
            if selection.age_maximum_sec is not None and age > selection.age_maximum_sec:
                res.trop_anciens += 1
                continue
            if selection.taille_minimum_octets is not None and st.st_size < selection.taille_minimum_octets:
                res.trop_petits += 1
                continue
            relatif = os.path.join(*(composants + (nom,)))
            res.candidats.append(Candidat(entree.path, relatif, st.st_size, st.st_mtime_ns))

    parcourir(source, ())
    if selection.ordre == "date_modification":
        res.candidats.sort(key=lambda c: (c.mtime_ns, c.relatif.lower()))
    else:
        res.candidats.sort(key=lambda c: c.relatif.lower())
    return res
