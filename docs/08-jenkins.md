# Intégration Jenkins

Jenkins ne fait que **déclencher** le moteur et **recevoir son code retour** : toute la logique (planification, verrous, reprise, dépendances) est dans le moteur. Les fichiers livrés avec le dépôt sont dans [`jenkins/`](../jenkins/).

| Fichier | Rôle |
|---|---|
| `jenkins/Jenkinsfile.transfert` | Job de transfert, un par environnement, toutes les 5 minutes, **builds simultanés autorisés** |
| `jenkins/Jenkinsfile.sauvegarde` | Sauvegarde quotidienne de la base (`--sauvegarder-base`) |
| `jenkins/Jenkinsfile.verification` | Vérification nocturne du paramétrage et des accès (`--verifier`) |
| `jenkins/vars/fileManagement.groovy` | Étape `fileManagement(...)` : lance le moteur, traduit le code retour en résultat du build |
| `jenkins/vars/journalSI.groovy` | Bibliothèque partagée `journal-si` : événements `debut_job` / `fin_job` dans le journal |
| `journal_si.py` (racine) | Écrit réellement ces événements : **le format est défini à un seul endroit** (voir §5) |

> **Non testé dans un vrai Jenkins.** Les fichiers Groovy ont été relus et contrôlés statiquement (délimiteurs, options, cohérence avec le moteur) ; le moteur, lui, est testé avec de vrais processus qui reproduisent ce que fait Jenkins (builds simultanés, abandon d'un build, codes retour). L'exécution réelle sur votre Jenkins est l'objet des tests J9-M du [cahier de tests](06-cahier-de-tests.md). Je n'ai ni la version de Jenkins, ni la liste de ses modules : les points à vérifier sont au §8.

## 1. Mise en place

1. **Agent.** Un agent Windows (Windows Server 2016) étiqueté `file-management`, qui peut atteindre les sources, les cibles, les archives, le dossier de paramétrage et dispose en local de la base et des journaux.
2. **Compte de service.** L'agent s'exécute sous le compte de service du moteur (droits au §6 de [00-vue-ensemble](00-vue-ensemble.md) et au §4 de [02-moteur](02-moteur.md)) : lecture des sources, écriture des cibles et archives, écriture de la base, des journaux et du dossier de travail, **lecture seule** du paramétrage.
3. **Dépôt et Python.** Le dépôt est copié sur l'agent (`D:\Scripts\file_management` dans les exemples) avec Python 3.14 (`C:\Python314\python.exe`). Dans chaque Jenkinsfile, adapter la section `environment` : `COPIE_PYTHON`, `COPIE_DEPOT`, `COPIE_CONFIG`, `COPIE_LOGS` (**identique au `dossier_logs` du paramétrage**, par défaut `logs` à côté de la base), `COPIE_ENV` (**code de la plateforme d'observabilité** : `dev`, `build`, `test`, `pprod`, `prod`, `run`, `int` ; le même que `code_environnement` de l'en-tête, voir [01-parametrage](01-parametrage.md)).
4. **Bibliothèque partagée.** *Administrer Jenkins → System → Global Pipeline Libraries* : nom `journal-si`, version par défaut `main`, source = le dépôt contenant le dossier `jenkins/` (les fichiers `vars/*.groovy` doivent être à la racine de la bibliothèque : soit un dépôt dédié, soit une bibliothèque dont le *Library Path* est `jenkins`, option disponible selon la version du module). Cocher *Load implicitly* est facultatif ; les Jenkinsfile contiennent `@Library('journal-si') _`.
5. **Initialiser la base** (une fois par environnement) : `python -m file_management --config D:\Parametrage\production.jsonl --initialiser-base`.
6. **Créer les trois jobs** de type *Pipeline* (*Pipeline script from SCM*, chemin `jenkins/Jenkinsfile.transfert`, etc.). Déclencheur : le `cron` du fichier (`H/5 * * * *`, `H 2 * * *`, `H 4 * * *`).
7. **Essai** : lancer le job de transfert à la main une fois, `--simulation` d'abord (voir le cahier de tests J9-M02).

## 2. Builds simultanés et exécuteurs

- **Ne pas** ajouter `disableConcurrentBuilds()` au job de transfert. Si un lancement dure plus de 5 minutes (gros fichiers, programme lent), le suivant doit pouvoir démarrer : chaque règle est protégée par un drapeau atomique en base, un build qui la trouve déjà en cours l'ignore, et les dépendances d'une règle en cours restent `EN_ATTENTE`. Mesuré : deux lancements simultanés sur huit règles exécutent chaque règle exactement une fois, sans erreur.
- **Nombre d'exécuteurs de l'agent** ≥ `ceil(durée maximale d'un lancement ÷ 5 min) + 1`, plus 1 pour la sauvegarde et la vérification (qui ont lieu la nuit). Exemple : lancements de 12 minutes au plus → 4 exécuteurs ; ajouter une marge. Si les exécuteurs manquent, les builds attendent dans la file : surveiller sa longueur.
- Le moteur lui-même lance un processus par règle ; l'agent doit pouvoir porter `exécuteurs × règles en parallèle` processus Python. `parallele_max` dans l'en-tête du paramétrage plafonne ce nombre par lancement.

## 3. Codes retour et résultat du build

| Code du moteur | Résultat du build | Sens |
|---|---|---|
| 0 | `SUCCESS` | Aucune anomalie, ou seulement des messages d'information |
| 4 | `UNSTABLE` | Au moins un avertissement pendant **ce** lancement (aucune erreur) |
| 1 | `FAILURE` | Au moins une erreur pendant ce lancement |
| 2 | `FAILURE` | Paramétrage invalide, base absente ou inutilisable |

Le code reflète les événements **du lancement**, pas l'état persistant : une règle arrêtée en erreur, en attente d'une reprise, ne rend pas rouge un build toutes les 5 minutes. Pour l'état courant : `--etat`, le front-end et Grafana.

## 4. Durée maximale et abandon d'un build

- `timeout(time: 3, unit: 'HOURS')` dans le job de transfert est un **garde-fou** : le build est arrêté. Il doit rester supérieur à la plus grande valeur de `duree_max_sec` des règles et à la durée de la plus longue chaîne de dépendances. La durée de chaque règle est surveillée par le moteur lui-même.
- **Abandon manuel ou arrêt par `timeout`.** Mesuré avec de vrais processus : si l'arbre de processus du build est arrêté (ce que fait Jenkins), plus aucun processus du moteur ne survit ; si **seul** l'orchestrateur est tué, ses fils disparaissent aussi (Job Object). Les règles qui étaient en cours gardent leur drapeau jusqu'au lancement suivant, qui les libère (`arret_anormal`, règle en `ERREUR`) : une reprise est ensuite nécessaire si `apres_erreur = arreter`. Une livraison interrompue en pleine copie devient « de résultat inconnu » et demande une décision d'exploitation (jamais de doublon).
- Programmes lancés par une règle qui doivent **survivre au build** : à éviter. Jenkins arrête les processus du build à sa fin ; sinon, leur donner `JENKINS_NODE_COOKIE=dontKillMe` et l'assumer.

## 5. Journaux de job (Grafana)

`journalSI.debutJob(...)` et `journalSI.finJob(...)` écrivent `debut_job` et `fin_job` dans le même fichier que le bilan du lancement (`<dossier_logs>\_orchestrateur_<jour>.jsonl`), **au même format** que le module Python (format de la plateforme d'observabilité, [02-moteur](02-moteur.md) §11) : `timestamp`, `duration_ms`, `level`, `message` (« Job demarre », « Job termine : <statut> »), `trace`, `service` (dont `environment` = `COPIE_ENV`), puis `context` : `object` = `lancement`, `object_id` = `<job>-<build>`, `event`, `job`, `build`, `build_url`, `noeud`, `statut` (`SUCCESS`, `UNSTABLE`, `FAILURE`, `ABORTED`), `code_retour`. Niveau : `SUCCESS` → INFO, `UNSTABLE` et `ABORTED` → WARNING, `FAILURE` → ERROR (avec `error.type` = `UNKNOWN_ERROR`). Les événements de job ne portent pas la trace du moteur (le moteur est un autre processus) ; ils se retrouvent par `correlation_id` = `<job>-<build>`.

Pour garantir un format unique, la bibliothèque Groovy **n'écrit pas elle-même** : elle appelle `journal_si.py` (champs transmis dans un fichier JSON, aucun problème de guillemets ni d'accents). Une panne de journalisation n'échoue jamais le build.

Lien entre un build et ses règles : tous les événements d'un lancement portent le même `build` et `build_url` ; dans Grafana, filtrer sur `job` et `build`.

## 6. Console du build

- Le moteur écrit en UTF-8 ; l'étape `fileManagement` fait `chcp 65001`. Si les accents sont mal affichés dans la console Jenkins, démarrer l'agent avec `-Dfile.encoding=UTF-8`.
- La console affiche une ligne lisible par événement (règle, fichier, anomalie) : suffisant pour un diagnostic rapide ; le détail est dans les journaux.

## 7. Sauvegarde et vérification

- **Sauvegarde** (`Jenkinsfile.sauvegarde`, une fois par nuit) : copie cohérente de la base, même pendant un transfert. **Condition de mise en production** : sans sauvegarde, une base perdue ferait relivrer en mode `copie` tous les fichiers encore présents dans les sources. La rotation et la copie hors serveur sont à décider avec l'exploitation (exemple commenté dans le fichier).
- **Vérification** (`Jenkinsfile.verification`) : `--verifier` complet avec le compte de service ; `UNSTABLE` = avertissement (archive inaccessible…), `FAILURE` = refus.

## 8. Points à vérifier sur votre Jenkins

| Point | Pourquoi |
|---|---|
| Version de Jenkins et modules *Pipeline*, *Pipeline: Shared Groovy Libraries*, *Timestamper* | Les fichiers utilisent `pipeline`, `@Library`, `timestamps()`, `bat`, `writeFile`, `unstable`, `dir`, `pwd(tmp: true)` |
| Bibliothèque « de confiance » | Une bibliothèque globale s'exécute hors du bac à sable ; `groovy.json.JsonOutput` y est autorisé. Dans une bibliothèque de dossier ou de dépôt, il faudra peut-être approuver la signature |
| Étiquette de l'agent | `file-management` dans les exemples |
| `H/5 * * * *` | La lettre `H` répartit la charge ; pour un déclenchement exact toutes les 5 minutes : `*/5 * * * *` |
| Chemins | `COPIE_PYTHON`, `COPIE_DEPOT`, `COPIE_LOGS` |
| Remplacement du lanceur | Quand `file_management.py` v2 remplacera la v1, passer `lanceur: 'file_management.py'` à `fileManagement` |
