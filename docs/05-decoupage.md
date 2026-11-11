# Découpage du développement

Ordre pensé pour traiter **d'abord ce qui est le plus risqué** (base, moteur de copie) et pour que chaque jalon soit **testable seul**. Les tailles sont relatives : **S** = quelques heures, **M** = 1 à 2 jours, **L** = plusieurs jours, **XL** = une à deux semaines. Ce ne sont pas des engagements de calendrier.

## 1. Vue d'ensemble

```
J0 Socle ─► J1 Paramétrage ─► J2 Base ─► J3 Journal ─► J4 Transfert d'une règle ─► J5 Planification et reprise
                                  │                                                         │
                                  │                                          ══ Version minimale exploitable ══
                                  │                                                         ▼
                                  │                                  J6 Orchestrateur parallèle + dépendances
                                  │                                                         ▼
                                  │                                             J7 Programmes externes
                                  ▼                                                         ▼
                       J8 Commandes pour le front-end ──────────────────────────► J9 Jenkins ─► J10 Front-end
                                                                                                    ▼
                                                                              J11 Migration et recette ─► J12 Purge (projet séparé)
```

| Jalon | Contenu | Dépend de | Taille |
|---|---|---|---|
| **J0** Socle | Structure du dépôt, package Python, outillage de tests, installation et validation de Python 3.14 sur le serveur de recette, exécution des tests en 3.14, tests de caractérisation du script actuel | — | S |
| **J1** Paramétrage | Lecture du JSON Lines, validation (E, R, P, D, G), `--verifier --syntaxe-seule`, sortie JSON | J0 | M |
| **J2** Base | Schéma, migrations, flag atomique, empreintes, journal d'intention, `--initialiser-base`, `--sauvegarder-base` | J0 | L |
| **J3** Journalisation | Module `journal_si`, format, repli en cas de panne, test d'écriture concurrente | J0 | M |
| **J4** Transfert d'une règle | Sélection, modes `copie` / `deplacement` / `archivage`, copie vérifiée, contrôles préalables, espace disque, situations et boucles, renommage, archive dégradée, reprise après arrêt brutal, simulation | J1, J2, J3 | XL |
| **J5** Planification et reprise | Créneaux, rattrapage, état, `--etat`, `--reprise`, `--acquitter`, `--lancer-maintenant`, exécution séquentielle des règles dues | J4 | L |
| **J6** Orchestrateur | Processus fils, Job Object, arrêt de l'arbre, durée maximale, orphelins, dépendances, statuts `BLOQUEE` / `EN_ATTENTE`, code retour 4 | J5 | L |
| **J7** Programmes externes | Six points d'appel, liste de fichiers, variables, durées maximales, sorties dans le journal | J4 (J6 pour l'arrêt d'arbre) | M |
| **J8** Commandes front-end | `--verifier` complet (accès, JSON), `--debloquer`, sorties JSON stables, documentation des échanges | J5, J6 | M |
| **J9** Jenkins | Jenkinsfile type, Shared Library (événements de job), builds parallèles, exécuteurs, compte de service | J3, J6 | M |
| **J10** Front-end | Écrans, validation via le moteur, enregistrement atomique, versions, actions d'exploitation, graphe. En quatre étapes A à D ([04-frontend §8](04-frontend.md)) puis une étape de compléments E (point d'accès JEA, livraisons incertaines, état en arrière-plan, restauration) ; toutes sont faites | J1, J8 + maquettes | XL |
| **J11** Migration et recette | `--migrer-ancien`, exécution en simulation sur les données réelles, passage en parallèle avec l'ancien script, bascule | J9 | L |
| **J12** Gestion des fichiers | Purge des journaux et des archives par `id` de règle, paramétrée depuis le front-end | J10 | M |

## 2. Version minimale exploitable (J0 à J5)

Après J5 on peut déjà exploiter **un environnement en séquence** : paramétrage validé, base, journaux, copie / déplacement / archivage sécurisés, planification, reprise. Il manque le parallélisme, les dépendances, les programmes externes et le front-end ; le paramétrage s'édite alors à la main, contrôlé par `--verifier`.

Intérêt : c'est ce qui concentre le risque. Elle peut être testée en simulation, puis en production sur une règle peu critique, pendant que les jalons suivants se développent.

## 3. Pistes parallèles

Dès que le format de journal (J3) et les sorties du moteur (J8) sont figés, trois travaux peuvent avancer **en parallèle** de J6–J7 :

| Piste | Qui | Prérequis |
|---|---|---|
| Moteur (J4 → J8) | Développement Python | — |
| Shared Library Groovy et pipeline (J9) | Responsable applicatif et équipe Jenkins | Format de journal (J3) |
| Front-end PowerShell (J10) | Développement PowerShell | Maquettes, contrat de J1 et J8 |
| Tableaux de bord Grafana et configuration Alloy | Équipe de la plateforme de surveillance | Format de journal (J3) |

## 4. Détail et critères de sortie

### J0 — Socle

- Package `copie/` (modules : paramétrage, base, planification, sélection, transfert, situations, programmes, orchestrateur, journal) et lanceur `file_management.py`.
- Tests avec `unittest` (bibliothèque standard, aucune installation sur le serveur), dossiers temporaires, outils d'injection de pannes (fichier verrouillé, dossier absent, disque plein simulé, source modifiée pendant la copie).
- Installation de Python 3.14 sur le serveur de recette (Windows Server 2016) et vérification que `sqlite3`, `ctypes`, `multiprocessing` et la création d'un Job Object fonctionnent. **C'est le premier test du projet** : si la 3.14 ne s'installe pas ou ne fonctionne pas correctement sur Windows Server 2016, on le sait avant d'avoir écrit du code.
- Script d'exécution des tests ; le code ne doit utiliser aucun module retiré (contrôle par `python -W error`).
- **Sortie** : le comportement du script actuel est couvert par des tests de caractérisation ; les tests passent en 3.14 sur le poste de développement **et** sur le serveur de recette.

### J1 — Paramétrage

- Un test par code de validation du §7 de [01-parametrage](01-parametrage.md) (cas valide et cas invalide).
- Lecture d'un fichier enregistré depuis le Bloc-notes (BOM) et depuis PowerShell.
- **Sortie** : tous les codes E, R, P, D, G sont implémentés et testés ; `--verifier --syntaxe-seule --format json` stable.

### J2 — Base

- Tests multi-processus : deux processus prennent le flag en même temps, un seul réussit ; écritures simultanées ; arrêt brutal pendant une transaction.
- Migration de schéma, refus d'une base plus récente, refus de démarrer sans base.
- **Sortie** : les opérations atomiques du §5 de [03-base-de-donnees](03-base-de-donnees.md) sont prouvées par des tests ; mesure de performance sur un million d'entrées refaite sur le serveur cible avec Python 3.14.

### J3 — Journalisation

- Interface `debut` / `evenement` / `fin`, repli en cas d'échec, catalogue des événements.
- Test de charge : 8 processus × 10 000 lignes dans le même fichier, aucune ligne corrompue.
- **Sortie** : format validé par l'équipe de la plateforme de surveillance, configuration Alloy d'exemple lisant les fichiers.

### J4 — Transfert d'une règle (jalon le plus sensible)

- Garanties G1 à G4 prouvées par tests : arrêt brutal simulé entre chaque étape de la séquence du §6.1 de [02-moteur](02-moteur.md) ; source modifiée avant suppression ; archive absente ; dossier cible sans droits ; fichier verrouillé ; même nom déjà présent ; disque plein simulé.
- Comparaison de volume (renommage ou copie) et espace disponible pour l'appelant (`GetDiskFreeSpaceExW`) vérifiés sur un partage UNC réel.
- **Sortie** : tous les cas de la liste des situations ont un test ; aucun test ne laisse de fichier temporaire ni ne perd de fichier.

### J5 — Planification et reprise

- Tests d'horloge simulée : créneaux, rattrapage, changement d'heure, règle en cours, nouvelle règle, `apres_erreur`.
- **Sortie** : une règle quotidienne et une règle toutes les 5 minutes se comportent comme décrit au §4 de [02-moteur](02-moteur.md).

### J6 — Orchestrateur

- Un fils bloqué est arrêté avec tous ses sous-processus ; un fils mort brutalement est détecté et journalisé ; chaîne 8, 9, 10 → 11 avec condition `succes` + `fichiers`.
- Reprise en cascade : la règle 2 en erreur, la règle 4 `BLOQUEE`, reprise de la règle 2, la règle 4 part.
- **Sortie** : scénarios d'exploitation du §10 de [02-moteur](02-moteur.md) rejoués en test.

### J9 — Jenkins

- Builds simultanés autorisés, exécuteurs suffisants, `UNSTABLE` pour le code 4, durée maximale du pipeline.
- **Sortie** : un lancement Jenkins sur un environnement de recette, journaux de job et de règles dans Grafana.

### J11 — Migration et recette

1. `--migrer-ancien` sur le paramétrage actuel, comparaison des règles produites.
2. Exécution en `--simulation` sur la production, contrôle des fichiers qui seraient livrés.
3. Passage en parallèle sur une règle (ancien script désactivé pour cette règle uniquement).
4. Bascule règle par règle, journaux surveillés.
5. Sauvegarde quotidienne de la base en place avant la bascule.

### J12 — Purge des journaux et des archives

1. Rétentions par règle (`retention_journaux_jours`, `retention_archive_jours`) et d'en-tête ; contrôle R13.
2. `copie/purge.py` : plan (liste) puis application, garde-fous, tracé ; commande `--purger [--appliquer]`.
3. Purge de la base à chaque lancement (une fois par jour) ; `jenkins/Jenkinsfile.purge`.
4. Le paramétrage depuis le front-end suivra J10 (les champs sont de simples champs de règle).

## 5. Stratégie de tests

**Méthode retenue** : le développement exécute tout sur le poste du responsable applicatif (Windows 10, Python 3.14.10). À chaque jalon, les tests sont ajoutés au [cahier de tests](06-cahier-de-tests.md), qui sert ensuite de fiche de passage sur le serveur de recette (Windows Server 2016). Un jalon n'est « terminé » que lorsque ses tests automatiques passent sur le poste et que ses tests manuels sont décrits dans le cahier.

| Niveau | Outil | Contenu |
|---|---|---|
| Unitaire | `unittest` | Fonctions pures : sélection, planification, empreintes, résolution des chemins, validation |
| Intégration | `unittest` + dossiers temporaires | Copie complète avec injection de pannes, base réelle, processus réels |
| Concurrence | `unittest` + `multiprocessing` | Flag, écritures de base, écritures de journal |
| Compatibilité | Exécution du même jeu sur le poste de développement et sur le serveur de recette en 3.14 | Détecte les écarts d'environnement (Windows Server 2016) |
| Recette | Serveur Windows Server 2016, partages réels | Verrous de fichiers, quotas, `GetDiskFreeSpaceExW`, dates de modification sur partage |
| Front-end | Pester | JSON, encodage, appels distants |

Les futures montées de version de Python (3.15 et suivantes) se feront en rejouant ce même jeu de tests sur le serveur de recette.

## 6. Risques

| Risque | Gravité | Réponse |
|---|---|---|
| Base SQLite verrouillée ou corrompue | Élevée | Disque local, WAL, transactions courtes, tests multi-processus, sauvegarde quotidienne |
| Livraison en double après arrêt brutal | Élevée | Journal d'intention et état `INCERTAIN` (G2) |
| Un destinataire prend le fichier temporaire | Moyenne | `dossier_temporaire` hors du périmètre surveillé |
| Fils bloqués, programmes qui ne se terminent pas | Moyenne | Job Object, durée maximale, nettoyage des orphelins |
| Partages réseau : verrous, quotas, résolution des dates | Moyenne | Tests de recette sur partages réels, comparaison toujours faite sur la même source |
| Horloges désynchronisées | Moyenne | NTP, détection des dates dans le futur |
| Python 3.14 non officiellement testé sur Windows Server 2016 | Moyenne | Installation et tests sur le serveur de recette dès J0 ; repli sur la version 3.12 ou 3.13 si un défaut est constaté (le code n'utilise rien de propre à la 3.14) |
| Écritures concurrentes dans un même journal | Faible | Test de charge au jalon J3 ; repli par fichier de processus si besoin |
| Paramétrage modifié par un compte non autorisé | Élevée | Droits NTFS et JEA limités au groupe AD, versions conservées et tracées |
| Fin de support de Windows Server 2016 (12 janvier 2027) | Moyenne | Hors périmètre de ce projet ; à prévoir dans la feuille de route |

## 7. Évolutions possibles après la v2

| Fonction | Remarque |
|---|---|
| Fichiers témoins (`.ok`, `.done`) côté source et côté cible | Pour les logiciels qui signalent la fin d'écriture par un témoin |
| Rejeu de fichiers archivés | Action « Rejouer » dans le front-end |
| Conversion d'encodage et de fins de ligne | À activer règle par règle ; risqué |
| Fichier `.sha256` déposé à côté | Vérification par le destinataire |
| Compression ou décompression | |
| Détection d'un même contenu livré sous un autre nom | |
| Plafond de volume par exécution | En plus de `limite_fichiers` |
| Journalisation directe vers Loki ou OpenTelemetry | Sans modifier les appelants du module de journal |
| Condition de dépendance propre à chaque règle (`export_clients:succes`) | |

## 8. Ce dont j'ai besoin pour démarrer

| Jalon | Information |
|---|---|
| J0 | Emplacement de déploiement des scripts, chemin de Python sur le serveur, outil de test déjà utilisé |
| J3 | Interlocuteur de l'équipe de surveillance pour valider le format de journal, version de Grafana Alloy |
| J4 | Exemples de dossiers et de fichiers réels, comportement des logiciels qui lisent les cibles (prennent-ils les fichiers ? les suppriment-ils ?) |
| J9 | Version de Jenkins, nombre d'exécuteurs, compte de service, nom du groupe AD |
| J10 | Maquettes des écrans |
