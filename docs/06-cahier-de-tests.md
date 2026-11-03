# Cahier de tests

Ce cahier est **complété à chaque jalon**. Tout est d'abord exécuté sur le poste de développement (Windows 10, Python 3.14.10) par le développement ; la colonne « Serveur » est remplie ensuite par le responsable applicatif sur le serveur de recette (Windows Server 2016).

## 1. Mode d'emploi

### 1.1 Préparer le serveur

1. Installer Python 3.14 pour tous les utilisateurs (ou en copie portable) ; noter le chemin (`C:\Python314\python.exe` dans les exemples).
2. Copier le dépôt (ou le dossier du jalon testé) sur le serveur, par exemple `D:\Scripts\copie_fichiers_test\`.
3. Les tests ne touchent à aucun dossier de production : ils travaillent dans des dossiers temporaires (`%TEMP%`) qu'ils suppriment. Seuls les tests marqués **manuel** utilisent des dossiers que vous indiquez.

### 1.2 Lancer les tests automatiques

```powershell
cd D:\Scripts\copie_fichiers_test
.\outils\lancer_tests.ps1 -Python C:\Python314\python.exe
```

Le script affiche chaque test et écrit un rapport dans `rapports\tests_<serveur>_<date>.txt`. **Renvoyer ce fichier** : il contient la version de Python, du système et le détail des échecs.

### 1.3 Lancer le contrôle du serveur

```powershell
C:\Python314\python.exe outils\controle_serveur.py --partage \\SERVEUR\partage\test --json rapports\controle_serveur.json
```

`--partage` désigne un dossier de test sur un vrai partage de la production (source, cible ou archive). Le relancer pour chaque type de partage.

### 1.4 Remplir les colonnes

| Valeur | Sens |
|---|---|
| OK | Résultat conforme à l'attendu |
| ECHEC | Non conforme : joindre la sortie ou une capture |
| N/A | Sans objet sur cet environnement (préciser pourquoi) |

Les colonnes PC portent la date et la version testée par le développement. Un test en ECHEC sur le serveur et OK sur le PC indique une différence d'environnement : c'est exactement ce que ce cahier cherche.

## 2. Jalon J0 — Socle

Environnement de développement : Windows 10 (19045), Python 3.14.10, SQLite 3.50.4. Testé le 2026-11-03.

### 2.1 Tests automatiques

| ID | Objectif | Procédure | Attendu | PC | Serveur |
|---|---|---|---|---|---|
| J0-A01 | Le comportement du script actuel (v1) est inchangé | §1.2 | 33 tests, `OK`, aucun avertissement de dépréciation | OK | |
| J0-A02 | Python 3.14 : version et architecture | §1.3, ligne « Python » | 3.14.x, 64 bits | OK | |
| J0-A03 | Modules nécessaires importables (`sqlite3`, `ctypes`, `multiprocessing`, `msvcrt`…) | §1.3, ligne « Modules » | OK | OK | |
| J0-A04 | Encodage console et système de fichiers | §1.3, ligne « Encodage » | `utf-8` pour le système de fichiers ; console notée (cp850 acceptable : le moteur force l'UTF-8 dans ses journaux) | OK | |
| J0-A05 | SQLite : mode WAL, UPSERT, `WITHOUT ROWID`, 4 processus qui écrivent en même temps | §1.3, ligne « SQLite » | 200 écritures, aucune perdue, aucune erreur « database is locked » | OK (SQLite 3.50.4) | |
| J0-A06 | Espace disque disponible pour l'appelant | §1.3, ligne « Espace disque » | Valeur de `GetDiskFreeSpaceExW`. Si `shutil.disk_usage` diffère, le noter (le moteur utilisera l'appel Windows) | OK (identiques) | |
| J0-A07 | Verrou de fichier : le second est refusé | §1.3, ligne « Verrou » | Second verrou refusé | OK | |
| J0-A08 | `os.replace` remplace un fichier existant | §1.3, ligne « Remplacement » | OK | OK | |
| J0-A09 | Noms accentués, espaces, `&`, parenthèses | §1.3, ligne « Noms » | OK | OK | |
| J0-A10 | Job Object : un processus et son petit-fils sont arrêtés ensemble | §1.3, ligne « Job Object » | « fils et petit-fils arrêtés » | OK | |
| J0-A11 | Partage réseau : écriture, renommage, suppression, relecture de la date de modification | §1.3 avec `--partage` | OK ; **noter l'écart de date** (attendu : 0 à 2 s) | OK (disque local : 0,000 s) | |

### 2.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J0-M01 | Python 3.14 s'installe et démarre sur Windows Server 2016 | `C:\Python314\python.exe --version` puis `-c "import sqlite3; print(sqlite3.sqlite_version)"` | `Python 3.14.x` ; SQLite 3.45 ou plus | |
| J0-M02 | Les tests passent sous le **compte de service Jenkins**, pas seulement en administrateur | Ouvrir une session (ou `runas`) avec ce compte, refaire §1.2 et §1.3 | Mêmes résultats ; noter toute erreur d'accès | |
| J0-M03 | Les tests passent **lancés par Jenkins** | Job Jenkins de test exécutant §1.2 et §1.3 (étape `powershell` ou `bat`) | Mêmes résultats ; les accents s'affichent correctement dans la console Jenkins ; le rapport est archivé | |
| J0-M04 | Chaque type de partage réel se comporte comme attendu | §1.3 avec `--partage` pour : un partage source, un partage cible, un partage d'archive | OK pour chacun ; écart de date noté pour chacun | |
| J0-M05 | Espace « disponible pour l'appelant » avec quota | Sur un volume ayant un quota pour le compte de service : §1.3 | `libre pour l'appelant` inférieur ou égal à `libre total`. Si pas de quota : N/A | |
| J0-M06 | L'antivirus ne gêne pas les tests | Lancer §1.2 deux fois de suite ; noter la durée | Pas d'échec aléatoire d'un lancement à l'autre ; durée du même ordre que le PC (3 s environ) | |
| J0-M07 | Fuseau et heure du serveur | Ligne « Heure locale » du contrôle | Heure et fuseau corrects (Paris) ; noter si le serveur est synchronisé NTP (`w32tm /query /status`) | |

### 2.3 Notes de lecture des résultats

- Une différence entre `libre pour l'appelant` et `libre total` n'est pas une erreur, c'est le cas d'usage du contrôle d'espace.
- `database is locked` dans J0-A05 serait bloquant : la base ne pourrait pas servir de verrou entre processus sur ce serveur.
- Un écart de date supérieur à 2 s sur un partage (J0-A11) oblige à comparer les dates avec une tolérance ; à signaler.

## 3. Jalons suivants

Les sections suivantes seront ajoutées au fur et à mesure du développement, avec la même structure (tests automatiques, tests manuels sur le serveur) :

| Jalon | Contenu prévu du cahier |
|---|---|
| J1 Paramétrage | Un test par code de validation ; fichiers enregistrés par le Bloc-notes et par PowerShell ; sortie `--verifier` |
| J2 Base | Concurrence multi-processus, arrêt brutal, performance sur 1 million d'entrées **sur le serveur** |
| J3 Journal | Charge concurrente, lecture par Grafana Alloy, contrôle de la ligne JSON |
| J4 Transfert | Pannes injectées, fichiers verrouillés par un vrai logiciel, droits NTFS, quotas, partages réels |
| J5 Planification | Horloge simulée, changement d'heure, reprise et acquittement |
| J6 à J12 | Arrêt d'arbre de processus, dépendances, Jenkins, front-end, migration, recette |
