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
| J0-A01 | Le comportement du script actuel (v1) est inchangé | §1.2 | Tous les tests `OK` (33 pour la v1, plus ceux des jalons suivants), aucun avertissement de dépréciation | OK | |
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

## 3. Jalon J1 — Paramétrage

Testé le 2026-11-03 sur Windows 10, Python 3.14.10 : 91 tests au total (33 de J0, 58 pour J1), tous OK ; contrôles manuels J1-M03 et J1-M05 à J1-M07 déjà rejoués sur le PC avec PowerShell 5.1.

Commande de vérification (provisoire, le lanceur `copie_fichiers.py` reste la v1 jusqu'à la livraison) :

```powershell
C:\Python314\python.exe -m copie --config exemples\production.jsonl --verifier --syntaxe-seule [--format json] [--periode-declencheur-sec 300]
```

Codes retour : `0` valide, `4` valide avec avertissements, `2` refus.

### 3.1 Tests automatiques (fichier `tests/test_parametrage.py`)

Lancer §1.2 : les tests J1 sont inclus. Détail de ce que couvre chaque groupe (tous OK sur le PC, serveur à remplir par la suite complète J0-A01) :

| ID | Code(s) | Ce qui est vérifié | PC | Serveur |
|---|---|---|---|---|
| J1-A01 | — | Fichier valide sans aucun diagnostic ; valeurs de secours ; BOM, CRLF, lignes vides ; numéro de ligne physique ; exemple complet de la spécification | OK | |
| J1-A02 | E01, E02 | Fichier vide, absent, non UTF-8, première ligne qui est une règle ; version `2`, `"1"`, `true` | OK | |
| J1-A03 | E03, E04, E05 | Environnement différent du nom de fichier, majuscules, trop long ; `base` absente ; `base` en `\\serveur\...` ou `//serveur/...` | OK | |
| J1-A04 | E06 | JSON invalide (avec numéro de ligne), champ inconnu à tous les niveaux, mauvais types (texte, nombre à virgule, booléen pris pour un entier), champ en double, `NaN`, situation ou programme inconnu | OK | |
| J1-A05 | R01, R02, R03 | Champs obligatoires ; id invalide, doublon sans tenir compte de la casse ; source = cible, cible dans la source en récursif, variables d'environnement | OK | |
| J1-A06 | R04, R05, R06, R07 | Archive obligatoire en mode archivage, ignorée sinon ; valeurs hors liste, `suite` non autorisée selon la situation ; bornes numériques | OK | |
| J1-A07 | R08, R09, R10, R11, R12 | Rétention et fenêtre de sélection (`J-7` = 8 jours) ; durée maximale ; règles identiques ; même cible sans dépendance (directe et indirecte) ; variables de modèles | OK | |
| J1-A08 | P01, P02 | Planifications valides et 14 variantes invalides ; période du déclencheur | OK | |
| J1-A09 | D01 à D06 | Chaîne valide, référence inconnue (casse comprise), boucles (simple, à trois règles, deux boucles séparées), active vers inactive, ordre des horaires, fréquences, conditions | OK | |
| J1-A10 | G01 | Programme valide, toutes les variables, 10 variantes invalides | OK | |
| J1-A11 | — | Ligne de commande : codes retour 0 / 4 / 2, sortie JSON, sortie texte, accents | OK | |
| J1-A12 | — | Volume : 2 000 règles contrôlées en moins de 10 s (0,9 s mesuré) | OK | |

### 3.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J1-M01 | Fichier d'exemple valide | `-m copie --config exemples\production.jsonl --verifier --syntaxe-seule` | `0 refus, 0 avertissement(s)`, code retour 0 (`$LASTEXITCODE`) | |
| J1-M02 | Fichier d'exemple invalide | Même commande sur `exemples\invalide\production.jsonl` | Code retour 2 et 6 refus : R02, E06, R06, D01 (×2), P01, chacun avec son numéro de ligne | |
| J1-M03 | Sortie JSON lisible par PowerShell 5.1 | `... --format json \| ConvertFrom-Json` puis afficher `.refus`, `.ok`, `.regles_lues` | Objet correct ; accents correctement affichés | |
| J1-M04 | Fichier enregistré par le **Bloc-notes** (UTF-8 avec BOM) | Ouvrir l'exemple valide dans le Bloc-notes, ajouter un accent dans une `description`, enregistrer en « UTF-8 avec BOM » | Valide | |
| J1-M05 | Fichier enregistré par `Set-Content -Encoding UTF8` (PowerShell 5.1, BOM) | `Get-Content exemples\production.jsonl \| Set-Content $env:TEMP\production.jsonl -Encoding UTF8` puis vérifier ce fichier | Valide | |
| J1-M06 | Fichier enregistré par `Out-File` (UTF-16 par défaut) | `Get-Content exemples\production.jsonl \| Out-File $env:TEMP\production.jsonl` puis vérifier ce fichier | **Refus E01** « n'est pas de l'UTF-8 valide » (c'est voulu : le front-end écrit en UTF-8, voir [04-frontend §5](04-frontend.md)) | |
| J1-M07 | Fichier enregistré en « ANSI » avec un accent | Enregistrer l'exemple en ANSI après avoir ajouté `é` dans une description | **Refus E01** | |
| J1-M08 | Lecture depuis un partage en lecture seule, avec le compte de service | `--config \\SERVEUR\parametrage\production.jsonl` | Valide ; aucun fichier créé ou modifié sur le partage | |
| J1-M09 | Droits insuffisants | Fichier sur lequel le compte n'a pas de droit de lecture | Refus E01 « illisible » avec le message de Windows, code retour 2 | |
| J1-M10 | Durée sur un gros fichier | Générer 2 000 règles (script du développement, sur demande) et vérifier | Moins de 10 s ; noter la durée | |

## 4. Jalons suivants

Les sections suivantes seront ajoutées au fur et à mesure du développement, avec la même structure (tests automatiques, tests manuels sur le serveur) :

| Jalon | Contenu prévu du cahier |
|---|---|
| J2 Base | Concurrence multi-processus, arrêt brutal, performance sur 1 million d'entrées **sur le serveur** |
| J3 Journal | Charge concurrente, lecture par Grafana Alloy, contrôle de la ligne JSON |
| J4 Transfert | Pannes injectées, fichiers verrouillés par un vrai logiciel, droits NTFS, quotas, partages réels |
| J5 Planification | Horloge simulée, changement d'heure, reprise et acquittement |
| J6 à J12 | Arrêt d'arbre de processus, dépendances, Jenkins, front-end, migration, recette |
