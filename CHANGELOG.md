# Journal des modifications

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Une entrée par jalon ; le détail des tests est dans [docs/06-cahier-de-tests.md](docs/06-cahier-de-tests.md). À mettre à jour à chaque jalon ou étape validé.

## [Non publié]

### Ajouté
- **Documentation d'installation et d'utilisation** (2026-11-11) : `docs/10-installation.md`, `docs/11-guide-utilisateur.md` ; `README.md` réécrit pour la v2 (l'ancien est conservé dans `docs/12-ancien-script-v1.md`).
- **J10 étape E — Front-end : compléments** (2026-11-11) : point d'accès JEA (module `Gui\Jea\Copie.Jea`, `Installer-PointAccesJea.ps1` : grammaire stricte, fichiers limités au dossier de paramétrage, compte tracé = compte de la session, écriture réservée au groupe administrateur) ; écran « Trancher… » des livraisons incertaines ; état des règles lu en arrière-plan à l'ouverture et à l'actualisation ; restauration d'une version depuis l'historique. Moteur : `--etat` liste les livraisons incertaines (`incertains` : clé, source, cible).
- **J10 étape D — Front-end : graphe, promotion, historique** (2026-11-11) : onglet « Dépendances » (graphe coloré par statut, règle qui retient en rouge, clic pour sélectionner), historique des modifications (qui, quand, commentaire, différences champ par champ), promotion d'une règle vers un autre environnement avec adaptation des chemins, formulaire et enregistrement sécurisé de la cible.
- **J10 étape C — Front-end : exploitation** (2026-11-10) : reprise (avec les règles dépendantes), lancement immédiat, acquittement, déblocage et purge (liste puis suppression) depuis l'interface, tracés avec le compte de l'administrateur ; exécution en arrière-plan de la vérification et de la purge ; bouton « Actualiser l'état ».
- **J10 étape B — Front-end : édition** (2026-11-10) : formulaire de règle (ajouter, dupliquer, modifier), activer / désactiver, supprimer, tri automatique par dépendances. Enregistrement sécurisé : brouillon, vérification par le moteur, confirmation des avertissements, contrôle d'édition simultanée, version précédente avec fiche `.meta.json` (commentaire obligatoire), remplacement atomique. Moteur : commande `--modele-regle` (valeurs de secours et listes de valeurs). Paramètre `Parametrage.DossierBrouillons`.
- **J10 étape A — Front-end : consultation** (2026-11-10) : interface WPF dans `Gui\` (droits AD, un onglet par environnement, règles, détail, état, vérification), `Initialiser-DossierParametrage.ps1`.
- **J12 — Purge** (2026-11-04) : `--purger [--appliquer]` pour les journaux, archives et la base ; `Jenkinsfile.purge`.
- **J11 — Migration** (2026-11-04) : migration de l'ancien script et outils de recette.
- **J9 — Jenkins** (2026-11-04) : `Jenkinsfile`, bibliothèque partagée, journal de job.
- **J8 — Commandes pour le front-end** (2026-11-04) : accès, comparaison, déblocage, contrat JSON.
- **J7 — Programmes externes** (2026-11-04) : six points d'appel.
- **J6 — Orchestrateur** (2026-11-04) : exécution parallèle, dépendances, durée maximale.
- **J5 — Planification** (2026-11-04) : reprise, acquittement, état des règles.
- **J4 — Transfert** (2026-11-04) : copie, déplacement, archivage.
- **J3 — Journal d'événements JSON** (2026-11-04).
- **J2 — Base SQLite** (2026-11-03) : schéma, drapeau atomique, journal d'intention, sauvegarde.
- **J1 — Paramétrage** (2026-11-03) : lecture et validation (`python -m copie --verifier`).
- **J0 — Socle de tests** (2026-11-03) : tests de caractérisation de la v1, contrôle du serveur, cahier de tests.
- Spécifications de copie_fichiers v2 (Python 3.14) dans `docs\` (2026-11-03).

### À venir
- Aucun jalon en attente : reste à rejouer le cahier de tests sur le serveur (Windows Server 2016) et à valider le point d'accès JEA sur un vrai serveur.
