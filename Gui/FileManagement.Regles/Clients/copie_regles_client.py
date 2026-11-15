"""Client Python de l'API de règles de file_management.

Ce module n'écrit JAMAIS le fichier de règles : il demande au module PowerShell FileManagement.Regles
(via Invoke-RegleApi.ps1) de le faire. Le format des règles, le contrôle de conflit, les versions conservées
et la vérification du moteur restent donc ceux de l'outil, même si le format évolue.

Utilisation :

    from copie_regles_client import ClientRegles

    api = ClientRegles(appelant="mon_script")
    lecture = api.lire(r"D:\\Parametrage\\prod.jsonl")                 # empreinte + règles
    res = api.ajouter(r"D:\\Parametrage\\prod.jsonl",
                      {"id": "flux_x", "source": r"\\\\srv\\a", "cible": r"\\\\srv\\b", "mode": "copie"},
                      commentaire="ajout par mon_script", empreinte=lecture["empreinte"])
    if not res["succes"]:
        print(res["etape"], res["message"], res["refus"])

Seule la bibliothèque standard est utilisée. Chaque appel lance powershell.exe (Windows PowerShell 5.1).
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Any

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # dossier du module (parent de Clients)


class ErreurApi(RuntimeError):
    """Erreur technique (PowerShell introuvable, sortie illisible, code 2) : pas un refus métier."""


class ClientRegles:
    """Appelle Invoke-RegleApi.ps1. Chaque méthode renvoie le dictionnaire JSON du résultat.

    Un refus métier (droits, conflit, refus du moteur, règle introuvable...) n'est PAS une exception :
    ``resultat["succes"]`` vaut False, ``resultat["etape"]`` et ``resultat["message"]`` l'expliquent.
    """

    def __init__(self, appelant: str = "", config: str | None = None, script: str | None = None,
                 powershell: str = "powershell.exe", delai_sec: int = 300) -> None:
        self.appelant = appelant
        self.config = config
        self.script = script or os.path.join(_RACINE, "Invoke-RegleApi.ps1")
        self.powershell = powershell
        self.delai_sec = delai_sec

    def _appeler(self, action: str, fichier: str | None = None, identifiant: str | None = None,
                 entree: dict[str, Any] | None = None) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="copie_api_") as dossier:
            sortie = os.path.join(dossier, "sortie.json")
            commande = [self.powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-File", self.script, "-Action", action, "-SortieJson", sortie]
            if fichier:
                commande += ["-Fichier", fichier]
            if identifiant:
                commande += ["-Id", identifiant]
            if self.config:
                commande += ["-Config", self.config]
            if entree is not None:
                chemin = os.path.join(dossier, "entree.json")
                with open(chemin, "w", encoding="utf-8") as f:
                    json.dump(entree, f, ensure_ascii=False)
                commande += ["-EntreeJson", chemin]
            try:
                processus = subprocess.run(commande, capture_output=True, timeout=self.delai_sec, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ErreurApi(f"appel de PowerShell impossible : {exc}") from exc
            if not os.path.isfile(sortie):
                detail = processus.stderr.decode("utf-8", "replace").strip() or processus.stdout.decode("utf-8", "replace").strip()
                raise ErreurApi(f"l'API n'a rien rendu (code {processus.returncode}) : {detail}")
            with open(sortie, encoding="utf-8-sig") as f:
                resultat = json.load(f)
            if processus.returncode == 2:
                raise ErreurApi(resultat.get("message", "erreur de l'API"))
            return resultat

    def _ecriture(self, commentaire: str, empreinte: str | None, accepter_avertissements: bool) -> dict[str, Any]:
        return {"commentaire": commentaire, "appelant": self.appelant, "empreinte": empreinte or "",
                "accepter_avertissements": accepter_avertissements}

    def info(self) -> dict[str, Any]:
        """Versions de l'API et du format de règle du moteur."""
        return self._appeler("info")

    def modele(self) -> dict[str, Any]:
        """Règle par défaut du moteur (tous les champs valides)."""
        return self._appeler("modele")

    def lire(self, fichier: str, identifiant: str | None = None) -> dict[str, Any]:
        """Règles du fichier et son empreinte (à repasser en ``empreinte`` pour détecter un conflit)."""
        return self._appeler("lire", fichier, identifiant)

    def ajouter(self, fichier: str, regle: dict[str, Any], commentaire: str, empreinte: str | None = None,
                accepter_avertissements: bool = False) -> dict[str, Any]:
        """Ajoute une règle ; les champs absents prennent la valeur de secours du moteur."""
        entree = self._ecriture(commentaire, empreinte, accepter_avertissements)
        entree["regle"] = regle
        return self._appeler("ajouter", fichier, entree=entree)

    def modifier(self, fichier: str, identifiant: str, modification: dict[str, Any], commentaire: str,
                 empreinte: str | None = None, accepter_avertissements: bool = False) -> dict[str, Any]:
        """Modifie une règle : seuls les champs de ``modification`` changent."""
        entree = self._ecriture(commentaire, empreinte, accepter_avertissements)
        entree["modification"] = modification
        return self._appeler("modifier", fichier, identifiant, entree)

    def supprimer(self, fichier: str, identifiant: str, commentaire: str, empreinte: str | None = None,
                  accepter_avertissements: bool = False) -> dict[str, Any]:
        """Supprime une règle (la version précédente du fichier est conservée)."""
        return self._appeler("supprimer", fichier, identifiant, self._ecriture(commentaire, empreinte, accepter_avertissements))
