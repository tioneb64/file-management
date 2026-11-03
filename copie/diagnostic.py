"""Diagnostics de validation : codes, gravites, rapport texte et JSON.

La gravite d'un code est fixee ici (une seule fois) : le reste du moteur signale seulement
un code et un message. Voir docs/01-parametrage.md, section 7.
"""

REFUS = "refus"
AVERTISSEMENT = "avert"

# code -> (gravite, intitule du controle)
CODES = {
    "E01": (REFUS, "premiere ligne : en-tete valide"),
    "E02": (REFUS, "version du format supportee"),
    "E03": (REFUS, "environnement valide et egal au nom du fichier"),
    "E04": (REFUS, "base renseignee"),
    "E05": (REFUS, "base sur un disque local"),
    "E06": (REFUS, "JSON valide, champs connus et du bon type"),
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
    "P01": (REFUS, "planification invalide"),
    "P02": (AVERTISSEMENT, "frequence inferieure a la periode du declencheur"),
    "D01": (REFUS, "dependance vers une regle inexistante"),
    "D02": (REFUS, "boucle de dependances"),
    "D03": (REFUS, "regle active dependant d'une regle inactive"),
    "D04": (AVERTISSEMENT, "la regle dependante demarre avant sa dependance"),
    "D05": (AVERTISSEMENT, "la regle dependante est plus frequente que sa dependance"),
    "D06": (REFUS, "condition ou dependance incoherente"),
    "G01": (REFUS, "programme externe invalide"),
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
        return "%-7s %s%s" % (self.code + " " + ("REFUS" if self.gravite == REFUS else "AVERT"),
                              "[%s] " % ", ".join(lieu) if lieu else "", self.message)


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
    def ok(self):
        return not self.refus

    def codes(self):
        return [d.code for d in self.diagnostics]

    def en_dict(self):
        return {"ok": self.ok,
                "refus": [d.en_dict() for d in self.refus],
                "avertissements": [d.en_dict() for d in self.avertissements]}

    def en_texte(self):
        lignes = [d.en_texte() for d in sorted(
            self.diagnostics, key=lambda d: (d.gravite != REFUS, d.ligne or 0, d.code))]
        lignes.append("%d refus, %d avertissement(s) : %s" % (
            len(self.refus), len(self.avertissements),
            "parametrage valide" if self.ok else "parametrage INVALIDE"))
        return "\n".join(lignes)
