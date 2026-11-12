"""Diagnostics de validation : codes, gravites, rapport texte et JSON.

La gravite d'un code est fixee ici (une seule fois) : le reste du moteur signale seulement
un code et un message. Voir docs/01-parametrage.md, section 7.
"""

REFUS = "refus"
AVERTISSEMENT = "avert"
INFORMATION = "info"          # n'a aucun effet sur le code retour

VERSION_CONTRAT = 1           # version du format JSON echange avec le front-end (docs/07)

# code -> (gravite, intitule du controle)
CODES = {
    "E01": (REFUS, "premiere ligne : en-tete valide"),
    "E02": (REFUS, "version du format supportee"),
    "E03": (REFUS, "environnement valide et egal au nom du fichier"),
    "E04": (REFUS, "base renseignee"),
    "E05": (REFUS, "base sur un disque local"),
    "E06": (REFUS, "JSON valide, champs connus et du bon type"),
    "E07": (REFUS, "racines et chemins de l'en-tete complets une fois places sous la racine"),
    "E08": (REFUS, "code_environnement dans la liste de la plateforme (dev, build, test, pprod, prod, run, int)"),
    "R01": (REFUS, "champs obligatoires presents"),
    "R02": (REFUS, "id valide et unique"),
    "R03": (REFUS, "source differente de la cible"),
    "R04": (REFUS, "mode archivage : archive obligatoire"),
    "R05": (AVERTISSEMENT, "archive renseigne hors mode archivage"),
    "R06": (REFUS, "valeur hors liste"),
    "R07": (REFUS, "nombre hors bornes"),
    "R08": (REFUS, "retention de l'historique superieure a la fenetre de selection"),
    "R09": (AVERTISSEMENT, "duree maximale inferieure aux attentes prevues"),
    "R10": (AVERTISSEMENT, "deux regles identiques (source, cible, masque)"),
    "R11": (AVERTISSEMENT, "deux regles ecrivent dans la meme cible sans dependance"),
    "R12": (AVERTISSEMENT, "variable inconnue dans un modele"),
    "R13": (REFUS, "retention_archive_jours exige le mode archivage et une archive datee"),
    "R14": (REFUS, "chemin de la regle complet une fois place sous la racine"),
    "R15": (AVERTISSEMENT, "mode suppression : suppression definitive des fichiers selectionnes"),
    "R16": (AVERTISSEMENT, "champ sans effet pour ce mode"),
    "R17": (REFUS, "mode synchro : aucun dossier (source, cible, archive, dossier_temporaire)"),
    "R18": (AVERTISSEMENT, "mode synchro : programme apres_fichier / apres_lot jamais execute"),
    "S01": (INFORMATION, "environnement suspendu : aucune regle n'est lancee"),
    "P01": (REFUS, "planification invalide"),
    "P02": (AVERTISSEMENT, "frequence inferieure a la periode du declencheur"),
    "D01": (REFUS, "dependance vers une regle inexistante"),
    "D02": (REFUS, "boucle de dependances"),
    "D03": (REFUS, "regle active dependant d'une regle inactive"),
    "D04": (AVERTISSEMENT, "la regle dependante demarre avant sa dependance"),
    "D05": (AVERTISSEMENT, "la regle dependante est plus frequente que sa dependance"),
    "D06": (REFUS, "condition ou dependance incoherente"),
    "G01": (REFUS, "programme externe invalide"),
    # controles d'acces (docs/01, section 7.3), executes avec le compte de service
    "A01": (REFUS, "source accessible en lecture"),
    "A02": (REFUS, "cible accessible en ecriture"),
    "A03": (AVERTISSEMENT, "archive accessible en ecriture"),
    "A04": (REFUS, "executable du programme present"),
    "A05": (REFUS, "base accessible en ecriture"),
    "A06": (AVERTISSEMENT, "dossiers de journaux et de travail accessibles en ecriture"),
    "A07": (INFORMATION, "espace disponible pour le compte de service"),
    # comparaison avec la version precedente du parametrage (docs/01, section 7.2)
    "V01": (REFUS, "un id existant ne peut pas etre modifie"),
    "V02": (AVERTISSEMENT, "regle supprimee"),
    "V03": (AVERTISSEMENT, "selection elargie"),
    "V04": (AVERTISSEMENT, "cible modifiee"),
}


class Diagnostic(object):
    def __init__(self, code, message, regle=None, ligne=None):
        self.code = code
        self.gravite = CODES[code][0]
        self.message = message
        self.regle = regle
        self.ligne = ligne

    def en_dict(self):
        d = {"code": self.code, "regle": self.regle, "message": self.message}
        if self.ligne is not None:
            d["ligne"] = self.ligne
        return d

    def en_texte(self):
        lieu = []
        if self.ligne is not None:
            lieu.append("ligne %d" % self.ligne)
        if self.regle:
            lieu.append("regle %s" % self.regle)
        etiquette = {REFUS: "REFUS", AVERTISSEMENT: "AVERT", INFORMATION: "INFO"}[self.gravite]
        return "%-7s %s%s" % (self.code + " " + etiquette, "[%s] " % ", ".join(lieu) if lieu else "", self.message)


class Rapport(object):
    def __init__(self):
        self.diagnostics = []

    def signaler(self, code, message, regle=None, ligne=None):
        self.diagnostics.append(Diagnostic(code, message, regle, ligne))

    @property
    def refus(self):
        return [d for d in self.diagnostics if d.gravite == REFUS]

    @property
    def avertissements(self):
        return [d for d in self.diagnostics if d.gravite == AVERTISSEMENT]

    @property
    def informations(self):
        return [d for d in self.diagnostics if d.gravite == INFORMATION]

    @property
    def ok(self):
        return not self.refus

    def codes(self):
        return [d.code for d in self.diagnostics]

    def en_dict(self):
        return {"version_contrat": VERSION_CONTRAT, "ok": self.ok,
                "refus": [d.en_dict() for d in self.refus],
                "avertissements": [d.en_dict() for d in self.avertissements],
                "informations": [d.en_dict() for d in self.informations]}

    def en_texte(self):
        lignes = [d.en_texte() for d in sorted(
            self.diagnostics, key=lambda d: ({REFUS: 0, AVERTISSEMENT: 1, INFORMATION: 2}[d.gravite],
                                             d.ligne or 0, d.code))]
        lignes.append("%d refus, %d avertissement(s) : %s" % (
            len(self.refus), len(self.avertissements),
            "parametrage valide" if self.ok else "parametrage INVALIDE"))
        return "\n".join(lignes)
