# Cahier de tests

Ce cahier est **complété à chaque jalon**. Tout est d'abord exécuté sur le poste de développement (Windows 10, Python 3.14.10) par le développement ; la colonne « Serveur » est remplie ensuite par le responsable applicatif sur le serveur de recette (Windows Server 2016).

## 1. Mode d'emploi

### 1.1 Préparer le serveur

1. Installer Python 3.14 pour tous les utilisateurs (ou en copie portable) ; noter le chemin (`C:\Python314\python.exe` dans les exemples).
2. Copier le dépôt (ou le dossier du jalon testé) sur le serveur, par exemple `D:\Scripts\file_management_test\`.
3. Les tests ne touchent à aucun dossier de production : ils travaillent dans des dossiers temporaires (`%TEMP%`) qu'ils suppriment. Seuls les tests marqués **manuel** utilisent des dossiers que vous indiquez.

### 1.2 Lancer les tests automatiques

```powershell
cd D:\Scripts\file_management_test
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

Commande de vérification (le lanceur `file_management.py` de la racine équivaut à `python -m file_management`) :

```powershell
C:\Python314\python.exe -m file_management --config exemples\production.jsonl --verifier --syntaxe-seule [--format json] [--periode-declencheur-sec 300]
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
| J1-M01 | Fichier d'exemple valide | `-m file_management --config exemples\production.jsonl --verifier --syntaxe-seule` | `0 refus, 0 avertissement(s)`, code retour 0 (`$LASTEXITCODE`) | |
| J1-M02 | Fichier d'exemple invalide | Même commande sur `exemples\invalide\production.jsonl` | Code retour 2 et 6 refus : R02, E06, R06, D01 (×2), P01, chacun avec son numéro de ligne | |
| J1-M03 | Sortie JSON lisible par PowerShell 5.1 | `... --format json \| ConvertFrom-Json` puis afficher `.refus`, `.ok`, `.regles_lues` | Objet correct ; accents correctement affichés | |
| J1-M04 | Fichier enregistré par le **Bloc-notes** (UTF-8 avec BOM) | Ouvrir l'exemple valide dans le Bloc-notes, ajouter un accent dans une `description`, enregistrer en « UTF-8 avec BOM » | Valide | |
| J1-M05 | Fichier enregistré par `Set-Content -Encoding UTF8` (PowerShell 5.1, BOM) | `Get-Content exemples\production.jsonl \| Set-Content $env:TEMP\production.jsonl -Encoding UTF8` puis vérifier ce fichier | Valide | |
| J1-M06 | Fichier enregistré par `Out-File` (UTF-16 par défaut) | `Get-Content exemples\production.jsonl \| Out-File $env:TEMP\production.jsonl` puis vérifier ce fichier | **Refus E01** « n'est pas de l'UTF-8 valide » (c'est voulu : le front-end écrit en UTF-8, voir [04-frontend §5](04-frontend.md)) | |
| J1-M07 | Fichier enregistré en « ANSI » avec un accent | Enregistrer l'exemple en ANSI après avoir ajouté `é` dans une description | **Refus E01** | |
| J1-M08 | Lecture depuis un partage en lecture seule, avec le compte de service | `--config \\SERVEUR\parametrage\production.jsonl` | Valide ; aucun fichier créé ou modifié sur le partage | |
| J1-M09 | Droits insuffisants | Fichier sur lequel le compte n'a pas de droit de lecture | Refus E01 « illisible » avec le message de Windows, code retour 2 | |
| J1-M10 | Durée sur un gros fichier | Générer 2 000 règles (script du développement, sur demande) et vérifier | Moins de 10 s ; noter la durée | |

## 4. Jalon J2 — Base de données

Testé le 2026-11-03 sur Windows 10, Python 3.14.10, SQLite 3.50.4 : 151 tests au total (91 précédents + 60 de J2), tous OK en 45 s environ (la durée dépend surtout du coût d'un fsync sur le disque).

Commandes (provisoires) :

```powershell
C:\Python314\python.exe -m file_management --config exemples\production.jsonl --initialiser-base
C:\Python314\python.exe -m file_management --config exemples\production.jsonl --sauvegarder-base D:\Copie\sauvegardes
C:\Python314\python.exe outils\mesure_base.py --dossier D:\temp [--entrees 1000000] [--json rapports\mesure_base.json]
```

Pour les essais, remplacer le champ `base` de la copie du fichier d'exemple par un chemin local de la machine (`D:\Copie\test\production.db`).

### 4.1 Tests automatiques (fichier `tests/test_base.py`)

| ID | Ce qui est vérifié | PC | Serveur |
|---|---|---|---|
| J2-A01 | Création : schéma, `user_version`, mode WAL, `meta`, trace `initialisation` ; refus d'une base existante ; la base n'est **jamais** créée par `ouvrir` (aucun fichier laissé) | OK | |
| J2-A02 | Refus : chemin `\\serveur\...`, lecteur réseau mappé (simulé), fichier qui n'est pas une base, base SQLite d'un autre logiciel, base d'un **autre environnement**, schéma plus récent que le moteur | OK | |
| J2-A03 | Migration de schéma : réussie, manquante (refus), en échec au milieu (rien n'est modifié) | OK | |
| J2-A04 | Réglages de connexion : `synchronous = FULL`, clés étrangères, attente de 30 s ; ouverture en lecture seule (écriture refusée) | OK | |
| J2-A05 | Règles : synchronisation idempotente sans tenir compte de la casse, détection d'un changement de paramètres | OK | |
| J2-A06 | Flag « en cours » : prise puis refus (sans exécution fantôme), deux règles indépendantes, fin d'exécution atomique, erreur mémorisée, **fin tardive d'un processus débloqué sans effet sur le nouveau**, libération d'un orphelin | OK | |
| J2-A07 | Empreintes : 16 octets, stables, sensibles à chaque composant ; casse, `/` et `\`, accents composés ou décomposés équivalents ; genres V et C distincts ; nom Windows avec caractère isolé | OK | |
| J2-A08 | Journal d'intention : cycle complet (copie, archivage), doublon refusé, transitions invalides refusées, orphelins → `INCERTAIN`, résolution d'un incertain (tracée, commentaire obligatoire), `vu_jour` au plus une fois par jour | OK | |
| J2-A09 | Purge : seuls les `TERMINE` anciens sont supprimés, une fois par jour, règles hors liste intactes | OK | |
| J2-A10 | Sauvegarde d'une base **en cours d'utilisation** : un seul fichier autonome, intègre, restauration par copie | OK | |
| J2-A11 | **Concurrence (vrais processus)** : 8 processus visent la même règle → un seul gagnant ; 30 demandes sur 10 règles → 10 gagnants ; 4 processus écrivent 200 empreintes → aucune perdue, aucun « database is locked » ; base verrouillée → `BaseIndisponible` après le délai puis retour à la normale | OK | |
| J2-A12 | **Arrêt brutal** (`os._exit` d'un processus) : transaction non validée disparue, intention validée conservée puis devenue `INCERTAIN` au lancement suivant, confirmation validée conservée | OK | |
| J2-A13 | Recherche de 1 000 empreintes dans 100 000 entrées en moins de 2 s | OK | |
| J2-A14 | Commandes `--initialiser-base`, `--sauvegarder-base` : codes retour, messages, paramétrage invalide, commandes exclusives entre elles | OK | |

### 4.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J2-M01 | **Mesure de performance sur le serveur** | `outils\mesure_base.py --dossier D:\temp` (disque local, comme la vraie base) | Recherche de 2 000 empreintes < 0,3 s ; fichier d'environ 30 Mo. **Noter la ligne « une livraison (2 transactions) »** : PC = 71 ms en FULL, 0,6 ms en NORMAL. Si le serveur est au-dessus de 150 ms en FULL, le signaler (voir [03 §4.2 bis](03-base-de-donnees.md)) | |
| J2-M02 | Création de la base avec le compte de service | Copier `exemples\production.jsonl`, mettre un `base` local, lancer `--initialiser-base` **avec le compte de service Jenkins** | Fichier créé, code 0 ; une seconde exécution refuse (code 2, « existe deja ») | |
| J2-M03 | Droits : le compte de service n'a pas le droit d'écrire dans le dossier de la base | Retirer l'écriture sur le dossier puis lancer `--initialiser-base` | Refus clair, code 2, aucun fichier partiel | |
| J2-M04 | Partage et lecteur réseau refusés | `base` en `\\SERVEUR\partage\x.db`, puis sur un lecteur réseau mappé (`net use Z: ...`) | Refus pour les deux (« disque local »), code 2. Le lecteur mappé doit être refusé avec le compte qui lance l'outil | |
| J2-M05 | Sauvegarde pendant l'écriture | Dans une console, `mesure_base.py --entrees 200000` ; pendant l'exécution, dans une autre, lancer `--sauvegarder-base` sur une base de test en cours d'utilisation (ou sur `mesure.db` si le dossier est conservé) | Sauvegarde créée, sans erreur, un seul fichier `.db` ; aucune erreur dans la console de mesure | |
| J2-M06 | Restauration | Arrêter les traitements, copier la sauvegarde à la place de la base, relancer la suite de tests J2 sur ce fichier ou ouvrir avec `python -c "from file_management import base; b=base.ouvrir(r'D:\\...\\production.db'); print(b.meta('environnement'), b.verifier_integrite())"` | Environnement affiché, liste d'anomalies vide `[]` | |
| J2-M07 | Antivirus et fichiers `-wal` / `-shm` | Lancer la suite complète deux fois ; surveiller `PermissionError`, `database is locked`, tests lents | Aucune erreur ; sinon demander l'exclusion du dossier de la base à l'équipe sécurité | |
| J2-M08 | **Coupure de courant** (machine virtuelle de recette, optionnel mais recommandé) | Lancer `mesure_base.py --cycles 500`, puis mettre la VM hors tension brutalement (arrêt forcé sans arrêt du système). Relancer, ouvrir la base de mesure si elle subsiste (`--dossier` fixe, ne pas supprimer) | La base s'ouvre, `verifier_integrite()` vide ; au plus quelques derniers cycles manquants | |
| J2-M09 | Disque plein (optionnel) | Base sur un petit volume (VHD de 20 Mo) rempli : lancer `mesure_base.py` | Erreur claire (`ErreurBase`/`disk is full`), base non corrompue (`verifier_integrite()` vide) | |

## 5. Jalon J3 — Journalisation

Testé le 2026-11-04 sur Windows 10, Python 3.14.10 : 185 tests au total (151 précédents + 34 de J3), tous OK.

Le module est [journal_si.py](../journal_si.py) ; exemple de sortie dans `exemples\journal\`, exemple Alloy (non testé) dans `exemples\alloy\`.

```powershell
C:\Python314\python.exe outils\charge_journal.py --dossier D:\Copie\logs_test --json rapports\charge_journal.json
C:\Python314\python.exe outils\charge_journal.py --processus 8 --lignes 2000 --taille 3500
```

### 5.1 Tests automatiques (fichier `tests/test_journal.py`)

| ID | Ce qui est vérifié | PC | Serveur |
|---|---|---|---|
| J3-A01 | Format : champs de la racine dans l'ordre (`timestamp`, `duration_ms`, `level`, `message`, `trace`, `service`, `context`), horodatage UTC au millième (`2026-11-03T06:30:12.481Z`), variables Jenkins ajoutées à `context` si présentes et absentes sinon, UTF-8 sans échappement des accents, retours à la ligne dans un message, champs réservés non écrasables (`x_…`), valeurs non sérialisables, nom Windows avec caractère isolé, texte trop long coupé | OK | |
| J3-A02 | Niveaux (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` ; `ERREUR` → `ERROR`, inconnu → INFO), `DEBUG` seulement en mode verbeux, contexte défini une fois (`definir`), contexte passé à `debut` | OK | |
| J3-A03 | Fichiers : un par règle et par jour, fichier `_orchestrateur_` sans règle, changement de jour, nom de règle assaini (jamais hors du dossier), dossier créé, dossier par défaut par variable d'environnement | OK | |
| J3-A04 | `fin` : bilan, durée, niveau selon le statut, fichiers fermés puis rouverts ; lecture du fichier pendant qu'il est ouvert (comme Alloy) ; suppression d'un autre fichier pendant l'exécution | OK | |
| J3-A05 | **Pannes (G7)** : dossier impossible, secours impossible, `stderr` fermé, sérialisation qui échoue → jamais d'exception, ligne retrouvée sur `stderr` et dans le fichier de secours, `pannes()` correct, reprise automatique quand le dossier revient | OK | |
| J3-A06 | Console : une ligne lisible par événement avec `console=True`, silence sinon | OK | |
| J3-A07 | Interface de module (`debut`, `evenement`, `fin`, `definir`, `pannes`) | OK | |
| J3-A08 | **Charge** : 8 processus × 1 000 lignes dans le même fichier, puis 6 × 300 lignes de 3,5 Ko : aucune ligne corrompue, perdue ou mélangée, séquence de chaque processus complète et dans l'ordre | OK | |
| J3-A09 | **Critère de sortie** `outils\charge_journal.py` : 8 processus × 10 000 lignes → 80 000 lignes valides, 0 corrompue, 39 Mo (format de la plateforme, lignes plus longues), 6,6 s (12 100 lignes/s) | OK | |
| J3-A10 | **Format de la plateforme** (`TestFormatPlateforme`) : ordre et forme des champs, version, `service.name` par règle, `object` / `object_id` par défaut (fichier, règle, lancement), `correlation_id` et spans, `trace_id` hérité de `TRACEPARENT` (valeur invalide ignorée), `error` obligatoire pour ERROR et CRITICAL, catalogue (l'appelant l'emporte, un catalogue défaillant n'empêche pas d'écrire), `message` et `duration_ms` à la racine, aucun niveau hors liste | OK | |
| J3-A11 | **Conformité de bout en bout** (`tests/test_format_plateforme.py`) : validateur de la plateforme appliqué à toutes les lignes d'un lancement réel (processus fils compris) et aux exemples `exemples\journal\` ; un lancement = une trace, même span côté fils et côté orchestrateur ; catalogue : types d'erreur dans la liste de la plateforme, CRITICAL (`base_indisponible`, `livraison_incertaine`, `erreur_interne`, disque plein), toutes les situations et tous les événements émis couverts | OK | |

### 5.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J3-M01 | **Charge sur le disque réel des journaux** | `outils\charge_journal.py --dossier <dossier de journaux réel>` avec le compte de service, puis avec `--taille 3500 --lignes 2000` | `RESULTAT : OK`, 0 ligne corrompue. Noter la durée et les lignes/s. Si l'antivirus ralentit fortement (< 1 000 lignes/s), le signaler | |
| J3-M02 | Écriture atomique réellement vérifiée sur Windows Server 2016 | Même test ; en cas d'échec : joindre la sortie | Aucune corruption. (Sur le PC, `O_APPEND` seul corrompt les lignes ; le module utilise `FILE_APPEND_DATA`.) | |
| J3-M03 | Dossier de journaux sur un **partage réseau** (information) | Même test avec `--dossier \\SERVEUR\partage\tmp` | Noter le résultat. Si des lignes sont corrompues, le dossier de journaux doit rester **local** (Alloy lit sur le serveur) | |
| J3-M04 | Panne de journalisation | Retirer le droit d'écriture du compte sur le dossier de journaux puis lancer un petit programme utilisant le module (`python -c "import journal_si as j; j.debut('t','test',dossier=r'D:\\Copie\\logs'); j.evenement('essai'); print(j.pannes())"`) | Aucune exception, message sur la console, ligne dans `journal_si_secours_<jour>.jsonl` du dossier temporaire du compte, `pannes()` affiche `2` | |
| J3-M05 | Lecture par **Grafana Alloy** | Avec l'équipe de surveillance : déposer `exemples\journal\*.jsonl` dans le dossier lu, adapter `exemples\alloy\file_management.alloy` | Les événements apparaissent dans Loki avec les libellés `environnement`, `instance`, `level`, `service_name`, `object`, `error_type` (les deux derniers seulement quand ils existent) et l'heure de la ligne ; les champs sont consultables (`| json`) ; **validation formelle du format par l'équipe de la plateforme** (valeurs `object`, cardinalité de `service_name`, casse de `object_id`) | |
| J3-M06 | Accents et caractères spéciaux dans la console Jenkins | Job Jenkins exécutant un script qui appelle `debut(..., console=True)` avec `message="é à ü"` | Les accents s'affichent correctement dans la console et sont intacts dans le fichier | |
| J3-M07 | Changement de jour | Laisser un programme tourner autour de minuit (ou changer l'heure de la VM de recette) | Deux fichiers `<regle>_<jour>.jsonl`, aucune ligne perdue | |

## 6. Jalon J4 — Transfert d'une règle

Testé le 2026-11-04 sur Windows 10, Python 3.14.10 : 307 tests au total (185 précédents + 122 de J4), tous OK en 3 min 35 s (durée dominée par les fsync).

C'est le jalon le plus sensible : **les tests manuels ci-dessous doivent être joués sur le serveur avec de vrais partages, de vrais droits et si possible le vrai logiciel destinataire**, en commençant par des dossiers de test.

Commandes (provisoires) :

```powershell
# une règle, en simulation puis pour de vrai (la base doit exister : --initialiser-base)
C:\Python314\python.exe -m file_management --config D:\Parametrage\recette.jsonl --lancer-regle export_clients --simulation
C:\Python314\python.exe -m file_management --config D:\Parametrage\recette.jsonl --lancer-regle export_clients
# débit de transfert
C:\Python314\python.exe outils\mesure_transfert.py --source D:\temp --fichiers 200 --taille-ko 100 [--cible \\SERVEUR\partage\test]
# livraisons de résultat inconnu (après un arrêt brutal) : lister, puis trancher
C:\Python314\python.exe -c "from file_management import base; b=base.ouvrir(r'D:\Copie\recette.db'); print([(c.hex(), s, d) for c, s, d in b.incertains(b.numero_regle('export_clients'))])"
C:\Python314\python.exe -c "from file_management import base; b=base.ouvrir(r'D:\Copie\recette.db'); b.resoudre_incertain(bytes.fromhex('CLE'), 'a_relivrer', 'benoit', 'absent de la cible')"
```

Codes retour de `--lancer-regle` : 0 succès, 4 avertissement, 1 erreur, 2 paramétrage ou base inutilisable.

### 6.1 Tests automatiques

| ID | Fichier | Ce qui est vérifié | PC | Serveur |
|---|---|---|---|---|
| J4-A01 | `test_chemins_selection.py` | Modèles de nom, suffixes d'horodatage, noms Windows invalides (caractères, noms réservés, point final, 255 caractères) ; archive relative/absolue/datée, exclusion de l'archive toutes dates confondues ; volumes ; espace disponible | OK | |
| J4-A02 | `test_chemins_selection.py` | Sélection : masque et exclusion sans la casse, récursif, temporaires du moteur, `modifie_depuis` J / J-N, âge minimal et maximal, taille, dates futures, ordre, dossier illisible, liens symboliques, accents et `&` | OK | |
| J4-A03 | `test_chemins_selection.py` | Copie vérifiée : contenu, date à la nanoseconde, fichier vide et multi-blocs ; source disparue, changée depuis le listage, changée pendant la lecture ; SHA-256 ou taille faux ; destination impossible ; disque plein simulé ; cible existante ; lecture seule ; réliquat de temporaire ; **vrai verrou de fichier Windows** ; suppression contrôlée ; renommage sans écrasement | OK | |
| J4-A04 | `test_moteur.py` | **Mode copie** : livraison puis aucun doublon, état en base, nouvelle version relivrée, sous-dossiers, renommage, masque/âge/limite/ordre, dossier cible créé, cible ou source inaccessible (tentatives et attentes), dossier temporaire séparé, boucle `aucun_fichier` (y compris fichier qui arrive pendant l'attente), dates futures, `apres_erreur` | OK | |
| J4-A05 | `test_moteur.py` | Fichier de même nom dans la cible : `erreur`, attente que le destinataire le prenne, `ecraser`, `ignorer`, `suffixe` ; `identite = contenu` (régénéré à l'identique, contenu différent, mode déplacement) ; `si_cible_absente` ignorer / recopier | OK | |
| J4-A06 | `test_moteur.py` | **Mode déplacement** : original supprimé après vérification (même en lecture seule) ; **original modifié après la copie conservé (G4)** puis nouvelle version livrée ; suppression refusée par un vrai partage de fichier : action différée, puis exécutée au lancement suivant **sans relivrer** ; réussite à la 2e tentative ; arrêt de la règle | OK | |
| J4-A07 | `test_moteur.py` | **Mode archivage** : archive à plat, relative datée dans la source (non relue), arborescence et renommage d'archive, nom déjà archivé (suffixe / écraser / erreur), autre volume (copie vérifiée puis suppression), original modifié non archivé | OK | |
| J4-A08 | `test_moteur.py` | **Archive dégradée** : livraison poursuivie, action mémorisée, drapeau en base, avertissement à chaque lancement, aucun fichier témoin ; rétablissement : file vidée et drapeau levé ; original modifié pendant la panne ; arrêt de la règle ; archive ignorée hors mode archivage | OK | |
| J4-A09 | `test_moteur.py` | **Espace disque** : cible insuffisante, juste assez, calcul sur ce qui sera livré, archive sur le même volume (non contrôlée) ou un autre (contrôlée, dégradée si pleine) ; **écrasement par une version plus volumineuse** (copie et déplacement) : sans place pour la nouvelle version la règle s'arrête avant toute écriture, l'espace de l'ancienne n'est pas compté, l'ancienne version reste intacte, sans temporaire ; disque plein pendant l'écriture : temporaire supprimé, ancienne version intacte | OK | |
| J4-A10 | `test_moteur.py` | **Situations** : fichier réellement verrouillé puis libéré pendant les tentatives, toujours verrouillé (arrêt de la règle), fichier suivant, fichier disparu, instable, copie ou vérification en échec, niveau `INFO` sans effet sur le statut | OK | |
| J4-A11 | `test_moteur.py` | **Arrêt brutal** : après la copie (reconnue livrée au lancement suivant, pas de doublon), avant la copie (`livraison_incertaine`, rien relivré, règle bloquée jusqu'à décision, `a_relivrer` / `livre`), `recopier`, mode déplacement, action différée ; défaut interne et Ctrl+C sans drapeau orphelin | OK | |
| J4-A12 | `test_moteur.py` | **Simulation** : aucun dossier créé, aucune écriture en base, fichiers déjà livrés reconnus, règle inconnue de la base | OK | |
| J4-A13 | `test_lancer_regle.py` | Commande de bout en bout : livraison, journaux, codes retour 0 / 4 / 1 / 2, simulation, base absente, règle inconnue ou inactive, règle déjà en cours, base d'un autre environnement | OK | |

### 6.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J4-M01 | **Débit** | `outils\mesure_transfert.py --source D:\temp --fichiers 200 --taille-ko 100`, puis avec `--cible \\SERVEUR\partage\test` | `RESULTAT : OK`. **Noter les ms par fichier.** PC : 186 ms (copie), 226 ms (déplacement) en local ; relance 0,1 s. Si le serveur est au-dessus de 500 ms par fichier, le signaler (voir [02 §6.4](02-moteur.md)) | |
| J4-M02 | Simulation sur données réelles | `--lancer-regle ... --simulation` sur une règle de recette pointant des dossiers réels | Liste des fichiers « à livrer » cohérente ; **aucun fichier créé** (comparer le contenu des dossiers avant/après) ; aucune ligne ajoutée en base | |
| J4-M03 | Livraison réelle en mode copie | Règle de recette `copie` sur 20 fichiers réels | Fichiers livrés avec taille, SHA-256 et **date de modification** identiques (`Get-FileHash`, `LastWriteTime`) ; relance : 0 livré, 20 ignorés | |
| J4-M04 | Modes déplacement et archivage | Mêmes essais en `deplacement` puis `archivage` (archive relative datée, puis archive sur un autre volume, puis sur un partage) | Originaux supprimés / archivés ; arborescence correcte ; archive jamais relue comme source ; chronométrer l'archivage sur le même volume (instantané) et sur un autre | |
| J4-M05 | **Vrai verrou par un vrai logiciel** | Ouvrir un fichier de la source dans le logiciel producteur ou dans Excel (verrou exclusif), lancer la règle ; le fermer pendant une attente | `tentative_echouee` (WARNING) puis livraison réussie après fermeture ; sinon `fichier_verrouille` après les tentatives et **aucun fichier partiel dans la cible** | |
| J4-M06 | Suppression impossible d'un original | Mode déplacement, ouvrir l'original dans une application qui interdit la suppression | Livré, `suppression_echec` (WARNING), action en attente ; après fermeture, le lancement suivant le supprime **sans relivrer** | |
| J4-M07 | Droits NTFS | Retirer au compte de service : (a) l'écriture dans la cible, (b) l'écriture dans l'archive, (c) la lecture de la source | (a) `cible_inaccessible`, ERREUR, rien copié ; (b) archive dégradée, livraison poursuivie, WARNING ; (c) `source_inaccessible`, ERREUR | |
| J4-M08 | Coupure réseau pendant une copie | Lancer sur de gros fichiers (500 Mo) vers un partage, couper le réseau (désactiver la carte de la VM) en cours de copie, le rétablir | Erreur proprement journalisée ; **jamais de fichier partiel sous le nom définitif** ; après rétablissement, la livraison reprend sans doublon | |
| J4-M09 | **Arrêt brutal du processus** | Lancer sur 300 fichiers de 50 Mo, tuer `python.exe` (`taskkill /F`) en cours de copie, relancer | Au plus un fichier `livraison_incertaine` ou reconnu livré (`livraison_reprise`), **aucun doublon dans la cible** ; décision avec les commandes ci-dessus puis relance : tout est livré une seule fois | |
| J4-M10 | Disque presque plein / quota | Cible sur un petit volume (VHD de 100 Mo) ou avec un quota FSRM pour le compte de service | `espace_insuffisant_cible` avant toute copie ; avec quota, l'espace « disponible pour l'appelant » est bien celui du quota | |
| J4-M11 | Chemins longs, accents, caractères spéciaux | Fichiers `é à ü & ( ) n°1.xml`, chemins de plus de 260 caractères (source et cible), noms réservés (`CON.txt`) | Accents et `&` livrés intacts ; chemins longs : **noter si Python 3.14 les gère** (clé `LongPathsEnabled`) ; nom réservé : situation `copie_echec` | |
| J4-M12 | **Logiciel destinataire réel** | Cible = dossier surveillé par le vrai logiciel, avec puis sans `dossier_temporaire` | Le logiciel ne prend **jamais** un fichier incomplet ni un `.copie_en_cours` ; noter s'il prend les fichiers (sinon `si_existe_cible` à régler) | |
| J4-M13 | Fichier de même nom non encore pris | Livrer deux versions successives d'un fichier avant que le destinataire ait pris la première | `fichier_existe_cible` (ERREUR) par défaut ; avec `tentatives = 6, delai_sec = 60`, attente puis livraison | |
| J4-M14 | Antivirus | Livrer 200 fichiers ; chercher `tentative_echouee` dans les journaux | Noter le nombre de tentatives échouées (verrou temporaire de l'antivirus sur le fichier créé) ; si fréquent, prévoir plus de tentatives | |
| J4-M15 | Dates de modification d'un autre serveur | Source dont l'horloge avance de plus d'une minute | `fichier_date_future` (WARNING), fichier ignoré | |
| J4-M16 | Journaux dans Grafana | Après une exécution réelle, consulter les événements `regle_demarree`, `selection`, `fichier_livre`, `regle_terminee` dans Loki | Événements présents et lisibles, libellés corrects | |

## 7. Jalon J5 — Planification, reprise et état

Testé le 2026-11-04 sur Windows 10, Python 3.14.10 : 375 tests au total (307 précédents + 68 de J5), tous OK en 4 min 41 s.

La planification est vérifiée avec une **horloge simulée** et un **fuseau fictif (France 2026)** : les tests de changement d'heure donnent le même résultat quel que soit le fuseau du poste. Les tests manuels sur le serveur contrôlent le comportement avec la vraie horloge et le vrai fuseau.

Commandes (le lanceur `file_management.py` de la racine équivaut à `python -m file_management`) :

```powershell
# lancement de l'environnement : exécute les règles dues, l'une après l'autre
C:\Python314\python.exe -m file_management --config D:\Parametrage\recette.jsonl
C:\Python314\python.exe -m file_management --config D:\Parametrage\recette.jsonl --simulation [--regle export_clients]
# état des règles
C:\Python314\python.exe -m file_management --config D:\Parametrage\recette.jsonl --etat [--regle ID] [--format json]
# exploitation (--utilisateur obligatoire)
C:\Python314\python.exe -m file_management --config ... --reprise ID --utilisateur DOMAINE\benoit --commentaire "source rétablie"
C:\Python314\python.exe -m file_management --config ... --lancer-maintenant ID --utilisateur DOMAINE\benoit
C:\Python314\python.exe -m file_management --config ... --acquitter ID --utilisateur DOMAINE\benoit --commentaire "traité à la main"
C:\Python314\python.exe -m file_management --config ... --trancher-incertain CLE_HEXA --decision a_relivrer --utilisateur DOMAINE\benoit --commentaire "absent de la cible"
```

### 7.1 Tests automatiques

| ID | Fichier | Ce qui est vérifié | PC | Serveur |
|---|---|---|---|---|
| J5-A01 | `test_planification.py` | Créneaux : quotidien, intervalle (fin incluse, fin hors pas), jours autorisés, week-end sauté, règle hebdomadaire, dernier créneau échu, prochain créneau, règle sans créneau, libellés en clair | OK | |
| J5-A02 | `test_planification.py` | Règle due : inactive, nouvelle (créneau considéré pris), en cours, créneau échu / pas encore / déjà pris, reprise et lancement manuel hors créneau, arrêt après erreur, `apres_dependances`, rattrapage (borne exacte à 4 h), validité jusqu'au créneau suivant | OK | |
| J5-A03 | `test_planification.py` | **Lancements simulés** : 169 exécutions pour une règle toutes les 5 min de 05:00 à 19:00 ; déclencheur irrégulier (aucun double) ; Jenkins arrêté 2 h → **une seule** exécution au retour ; quotidien avec et sans rattrapage ; week-end | OK | |
| J5-A04 | `test_planification.py` | **Changement d'heure** (fuseau fictif) : heure supprimée → exécution à l'instant suivant ; heure répétée → une seule exécution ; règle horaire : 24 exécutions un jour normal, **23 au printemps, 24 à l'automne** ; règle toutes les 5 min : 288 à l'automne | OK | |
| J5-A05 | `test_lancement.py` | Lancement séquentiel : règle nouvelle puis créneau, créneau pris en base, ordre des règles et filtre, code retour selon le pire événement, règles avec dépendances non lancées (avertissement), règle orpheline ou modifiée, base indisponible, simulation sans écriture | OK | |
| J5-A06 | `test_lancement.py` | **Orphelins** : processus disparu libéré (ERREUR, arrêt anormal), `apres_erreur = continuer`, processus vivant intact, identifiant réutilisé avec autre date de création, autre serveur intact | OK | |
| J5-A07 | `test_lancement.py` | **Reprise** : plus aucun créneau pris après erreur, reprise hors créneau, drapeaux consommés, trace dans `journal_actions`, reprise en échec → nouvelle reprise, lancement manuel, refus si en cours ou règle inconnue, reprise après décision sur une livraison incertaine | OK | |
| J5-A08 | `test_lancement.py` | **Acquittement** : statut `ACQUITTEE`, trace, la règle repart au créneau suivant, commentaire obligatoire, seulement en `ERREUR`, refusé tant que des livraisons sont incertaines, refusé si en cours | OK | |
| J5-A09 | `test_lancement.py` | **`--etat`** : règle jamais vue, statuts (SUCCES, ERREUR, INACTIVE, EN_COURS), détails, archive dégradée et actions en attente, orphelines et filtre, rendu texte, aucune écriture en base | OK | |
| J5-A11 | `test_planification.py`, `test_lancement.py`, `test_parametrage.py` | **Planification `unique` (OneShot)** : date invalide ou absente = P01, mode `synchro` refusé ; créneau unique, libellé, règle enregistrée avant sa date qui part à la date puis une seule fois (même avec un lancement par minute), règle nouvelle à date passée non rejouée, rattrapage, reprise et lancement manuel après la fin, nouvelle date = règle réarmée ; **état** : `unique_executee` et statut `INACTIVE` après le run (fichier inchangé), jamais en cas d'`ERREUR` ni de demande en attente | OK | |
| J5-A10 | `test_lancement.py` | **Ligne de commande** de bout en bout : initialisation, lancement, `--lancer-maintenant`, état JSON, reprise, acquittement avec et sans commentaire, `--utilisateur` obligatoire, règle inconnue, décision incertaine, base absente, simulation de lancement | OK | |

### 7.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J5-M01 | **Règle toutes les 5 minutes avec Jenkins** | Job de recette `python -m file_management --config ...` toutes les 5 min, règle `intervalle` 300 s, dépôt d'un fichier toutes les 10 min | Une exécution par créneau, jamais deux ; les fichiers sont livrés au créneau qui suit leur arrivée | |
| J5-M02 | Jenkins arrêté puis relancé | Arrêter le job 30 min, le relancer | La règle part **une seule fois** au retour, pas une fois par créneau manqué | |
| J5-M03 | Règle quotidienne et rattrapage | Règle `quotidien` à H+10 min avec `rattrapage_sec = 300`, job arrêté pendant l'heure du créneau | Pas de lancement tardif au-delà du rattrapage ; sans rattrapage, lancement tardif | |
| J5-M04 | **Fuseau et heure du serveur** | Règle `quotidien` à 5 min dans le futur, comparer avec `Get-TimeZone` et `w32tm /query /status` | Elle part à l'heure locale attendue ; noter le fuseau du serveur | |
| J5-M05 | **Changement d'heure réel** (VM de recette) | Avancer l'horloge de la VM autour du 29 mars et du 25 octobre avec une règle horaire | 23 exécutions au printemps, 24 à l'automne, aucun doublon pendant l'heure répétée | |
| J5-M06 | Erreur, arrêt, reprise | Règle dont la source est absente → ERREUR ; rétablir la source ; attendre un créneau (rien ne part) ; `--reprise` | Rien ne part sans reprise ; la reprise exécute la règle immédiatement ; statut `SUCCES` | |
| J5-M07 | Acquittement | Règle en ERREUR, régler à la main, `--acquitter` sans puis avec commentaire | Refus sans commentaire ; avec : statut `ACQUITTEE`, la règle repart au créneau suivant, trace dans `--etat` | |
| J5-M08 | **Processus tué** | Lancer une règle sur de gros fichiers, tuer `python.exe` (`taskkill /F`), relancer le job | Règle libérée (`arret_anormal`, ERREUR), livraison incertaine ou reconnue livrée, aucun doublon ; `--etat` l'affiche | |
| J5-M09 | Deux lancements simultanés | Lancer deux fois la commande en même temps sur la même règle | Une seule exécution de la règle ; l'autre lancement l'ignore sans erreur | |
| J5-M10 | `--etat` depuis le front-end | `Invoke-Command ... -- --etat --format json` depuis un autre poste, `ConvertFrom-Json` | JSON lisible, accents corrects, dates en secondes UTC | |
| J5-M11 | Règle avec dépendances | Règle avec `apres` : lancement | `regle_non_lancee` (WARNING), code retour 4, rien n'est exécuté (comportement provisoire jusqu'au jalon J6) | |
| J5-M12 | Compte de service Jenkins | Rejouer J5-M01 et J5-M06 avec le compte de service | Mêmes résultats ; la base, les journaux et le dossier de travail sont accessibles en écriture | |

## 8. Jalon J6 — Orchestrateur, parallélisme et dépendances

Testé le 2026-11-04 sur Windows 10, Python 3.14.10 : 422 tests au total (375 précédents + 47 de J6), tous OK en 5 min 9 s.

Le comportement attendu est décrit au [§3.3 de 02-moteur](02-moteur.md). Commande : la même que pour J5 (lancement sans commande) ; chaque règle due s'exécute maintenant dans **son propre processus** `python.exe` (visible dans le gestionnaire de tâches).

```powershell
C:\Python314\python.exe -m file_management --config D:\Parametrage\recette.jsonl
C:\Python314\python.exe -m file_management --config D:\Parametrage\recette.jsonl --etat      # EN_ATTENTE / BLOQUEE y apparaissent
```

### 8.1 Tests automatiques

| ID | Fichier | Ce qui est vérifié | PC | Serveur |
|---|---|---|---|---|
| J6-A01 | `test_orchestrateur.py` | **Chaîne** a → b → c dans un seul lancement ; attente sans alerte d'une règle sans horaire ; la règle part dès que sa dépendance a fini ; une exécution de la dépendance ne déclenche la suite qu'une fois ; règle horaire qui dépend d'une autre | OK | |
| J6-A02 | `test_orchestrateur.py` | **EN_ATTENTE** : dépendance plus tardive (un avertissement par créneau, pas de répétition, la règle part ensuite même après son heure), rattrapage dépassé (retour à l'état précédent), conditions `fichiers` et `termine`, dépendance en cours dans un autre lancement | OK | |
| J6-A03 | `test_orchestrateur.py` | **BLOQUEE** : dépendance en erreur, **erreur non propagée** (statut de la règle inchangé), un événement par créneau, reprise de la règle en erreur → toute la chaîne repart, blocage en cascade, acquittement qui débloque, avertissement qui ne bloque pas, niveau `si_condition_non_remplie`, visible dans `--etat` | OK | |
| J6-A04 | `test_orchestrateur.py` | Plusieurs règles indépendantes ; une règle en erreur ne bloque pas les autres | OK | |
| J6-A05 | `test_orchestrateur.py` | **Processus fils réels** : un processus par règle (identifiants distincts), résultat transmis par la base et le fichier JSON (supprimé ensuite), fin journalisée par l'orchestrateur, erreur d'un fils, **exécution simultanée** (intervalles qui se chevauchent), `parallele_max = 1` (aucun chevauchement), chaîne en processus réels | OK | |
| J6-A06 | `test_orchestrateur.py` | **Durée maximale** : `erreur` (fils arrêté, `duree_depassee`), `alerter` (WARNING, exécution terminée), `relancer` (relances épuisées → ERREUR ; relance qui peut réussir) | OK | |
| J6-A07 | `test_orchestrateur.py` | **Fins anormales** : fils mort sans résultat, fils qui a écrit en base sans JSON, fils qui attend le « go », fils tué de l'extérieur, interruption de l'orchestrateur (fils arrêtés, drapeaux libérés), **arrêt de l'arbre complet (petit-fils compris)**, commande interne refusée si exécution inconnue ou parent disparu | OK | |
| J6-A08 | `test_orchestrateur.py` | **Exécution d'un autre lancement trop longue** : `erreur`, `alerter`, `relancer`, pas de dépassement avant la durée maximale | OK | |
| J6-A09 | `test_orchestrateur.py` | Job Object (arrêt du processus et de ses descendants, fermeture), `tuer_arbre`, un processus ne s'arrête jamais lui-même, fichier résultat atomique | OK | |

### 8.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J6-M01 | **Délai de démarrage d'un fils** | Lancement avec une règle qui a un fichier à livrer ; comparer l'heure de `debut_lancement` et de `processus_regle_demarre` dans les journaux | Quelques secondes au plus (PC : 1 à 3 s). Noter la valeur ; si elle dépasse 5 s, l'antivirus analyse sans doute `python.exe` à chaque lancement | |
| J6-M02 | Parallélisme réel | Trois règles de recette sur de gros fichiers (500 Mo), lancer, observer le gestionnaire de tâches | Trois `python.exe` fils en même temps, plus l'orchestrateur ; fin des trois règles ; code retour 0 | |
| J6-M03 | `parallele_max` | `parallele_max: 2` dans l'en-tête, quatre règles | Jamais plus de deux fils simultanés | |
| J6-M04 | **Arrêt d'un build Jenkins** | Lancer le job sur de gros fichiers, l'**abandonner** depuis Jenkins | Plus aucun `python.exe` du lancement ; règles en `ERREUR` (`arret_anormal`, orchestrateur interrompu) ; au lancement suivant, livraison incertaine ou reprise sans doublon | |
| J6-M05 | Job Object sur Windows Server 2016 | Lancer une règle dont la durée maximale est de 5 s sur de gros fichiers | Le fils disparaît à l'échéance (`duree_depassee`), aucun processus orphelin ; si les journaux indiquent un arrêt par `taskkill`, noter-le (Job Object indisponible sous Jenkins) | |
| J6-M06 | Durée dépassée : `relancer` et `alerter` | Rejouer J6-M05 avec chaque politique | `relancer` : nouvelle exécution puis ERREUR après `relances_max` ; `alerter` : l'exécution continue, un seul WARNING, code retour 4 | |
| J6-M07 | **Chaîne réelle** | Reproduire une chaîne de production (par exemple les règles 8, 9 et 10 → 11) en recette avec leurs dépendances | Ordre respecté, la règle 11 part dans le même lancement que la dernière de ses dépendances | |
| J6-M08 | Panne dans la chaîne | Mettre la règle 9 en erreur (source indisponible) | La règle 11 est `BLOQUEE` (`--etat` nomme la règle 9), un seul avertissement par créneau, les autres règles continuent | |
| J6-M09 | Reprise en cascade | Rétablir la source de la règle 9 puis `--reprise 9` | La règle 9 repart immédiatement, puis la règle 11, dans le même lancement ; plus de blocage | |
| J6-M10 | Deux builds simultanés | Autoriser les builds concurrents, déclencher deux lancements à quelques secondes d'écart avec des règles longues | Chaque règle n'est exécutée qu'une fois ; l'autre lancement l'ignore (« déjà en cours ») ; les dépendances en cours sont `EN_ATTENTE` | |
| J6-M11 | Exécution trop longue d'un autre lancement | Lancer une règle longue (durée maximale courte) ; déclencher un second lancement | Le second lancement arrête l'arbre de processus de la règle (`taskkill /T`) et la met en `ERREUR` (`duree_depassee`) | |
| J6-M12 | Console Jenkins | Observer la console du job pendant un lancement avec plusieurs règles | Les lignes des fils s'affichent avec les accents corrects ; le code retour du lancement apparaît dans `fin_lancement` | |
| J6-M13 | Compte de service | Rejouer J6-M02 et J6-M07 avec le compte de service Jenkins | Les fils démarrent sous le même compte, avec les mêmes droits sur les partages | |

## 9. Jalon J7 — Programmes externes

Testé le 2026-11-04 sur Windows 10, Python 3.14.10 : 470 tests au total (422 précédents + 48 de J7), tous OK en 6 min 28 s.

Comportement détaillé au [§9.1 de 02-moteur](02-moteur.md). Les programmes d'essai sont de petits scripts Python ; les essais manuels du serveur utilisent **vos vrais programmes** (PowerShell, exécutables, scripts de validation, notification).

```powershell
# simulation avec appel des programmes (ils reçoivent COPIE_SIMULATION=1)
C:\Python314\python.exe -m file_management --config D:\Parametrage\recette.jsonl --simulation --simulation-programmes --regle export_clients
```

### 9.1 Tests automatiques

| ID | Fichier | Ce qui est vérifié | PC | Serveur |
|---|---|---|---|---|
| J7-A01 | `test_programmes.py` | **Lancement** : code retour, sortie standard et d'erreur réunies, **un élément = un argument** (espaces, `&`, guillemets, `%PATH%`), variables d'environnement, répertoire courant, entrée standard fermée, accents UTF-8 et page OEM, sortie tronquée à 8 Ko, programme introuvable, durée dépassée | OK | |
| J7-A02 | `test_programmes.py` | **Arrêt de l'arbre** : un programme qui lance un petit-fils dès sa première instruction est arrêté avec lui, 3 essais sur 3 | OK | |
| J7-A03 | `test_programmes.py` | Listes de fichiers : texte et JSON, accents, dates, suppression ensuite | OK | |
| J7-A04 | `test_programmes.py` | **`avant_lot`** : liste reçue, code 1 (rien à faire, sans erreur), autre code (règle en erreur, rien copié), programme introuvable et durée dépassée, **source relue** (fichier ajouté ou retiré par le programme), non appelé sans fichier, tentatives et délais | OK | |
| J7-A05 | `test_programmes.py` | **`avant_fichier`** : variables par fichier, nom piégé intact, code 1 (ignoré, sans trace), autre code (arrêt ou fichier suivant), **programme qui modifie la source sur place : livré modifié, jamais retraité** | OK | |
| J7-A06 | `test_programmes.py` | **`apres_fichier`** : appelé après la livraison et **avant** la suppression, échec → original conservé et plus aucune suppression tardive (déplacement et archivage), codes 0 et 1, fichier suivant | OK | |
| J7-A07 | `test_programmes.py` | **`apres_lot`** : résultat de chaque fichier (livré, ignoré, erreur avec message), statut du lot, non appelé sans fichier traité, échec signalé sans annuler la livraison | OK | |
| J7-A08 | `test_programmes.py` | **`sur_erreur`** : appelé avec situation et message, pas en cas de succès ou d'avertissement, son échec n'aggrave rien, appelé après une erreur de programme | OK | |
| J7-A09 | `test_programmes.py` | **`reprise`** : appelé en premier et seulement pour une reprise (pas pour un créneau ni un lancement manuel), échec → règle arrêtée avant toute copie | OK | |
| J7-A10 | `test_programmes.py` | Simulation : programmes non appelés ; avec `--simulation-programmes` appelés avec `COPIE_SIMULATION=1`, rien n'est livré | OK | |
| J7-A11 | `test_programmes.py`, `test_parametrage.py` | Journal `programme_appele` (commande, code, durée, sortie) ; variables autorisées par point d'appel (G01) ; programme lancé depuis un fils réel de l'orchestrateur | OK | |

### 9.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J7-M01 | **Vos vrais programmes** | Brancher les programmes de production (validation, notification, nettoyage) sur une règle de recette, un point d'appel à la fois | Appelés au bon moment, avec les bons arguments ; sorties lisibles dans le journal (`programme_appele`) | |
| J7-M02 | **PowerShell** | `commande`: `["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "D:\\Scripts\\valider.ps1", "-Liste", "{liste}"]` | Le script lit la liste, le code retour 0/1 est respecté (`exit 1`) ; accents des sorties corrects dans le journal | |
| J7-M03 | Accents dans la sortie | Programme qui affiche `é à ü` : un script PowerShell, un exécutable natif, un script Python | Accents lisibles dans le journal pour les trois (sinon noter la page de code utilisée) | |
| J7-M04 | Nom de fichier piégé | Fichier `Facture & (copie) n°1.xml` avec un programme `avant_fichier` qui écrit `%1` dans un fichier | Nom intact ; **ne pas utiliser de `.bat`** pour ces fichiers | |
| J7-M05 | Arbre de processus sur le serveur | Programme qui lance un processus fils long, `timeout_sec = 5` | À l'échéance : plus aucun processus (`tasklist`), situation `programme_<point>` | |
| J7-M06 | `avant_fichier` qui modifie la source | Programme qui ajoute une ligne au fichier source | Le fichier livré contient la modification ; au lancement suivant il n'est pas retraité | |
| J7-M07 | `apres_fichier` en échec | Programme qui sort avec 5 en mode `deplacement` | Original conservé dans la source, fichier livré dans la cible, règle en ERREUR (`arreter_regle`) ; pas de suppression au lancement suivant | |
| J7-M08 | `reprise` | Règle en erreur, programme de nettoyage branché sur `reprise`, puis `--reprise` | Le programme nettoie avant toute copie ; il n'est pas appelé aux exécutions suivantes | |
| J7-M09 | `sur_erreur` et supervision | Programme qui envoie un message (messagerie, canal de supervision) | Message reçu avec la situation et le message d'erreur ; une panne du programme de notification n'empêche rien | |
| J7-M10 | Droits du compte de service | Rejouer J7-M01 et J7-M02 avec le compte de service Jenkins | Les programmes s'exécutent avec les droits du compte de service ; noter tout refus | |
| J7-M11 | Antivirus et PowerShell | Chronométrer un appel de script PowerShell | Durée raisonnable (quelques secondes) ; sinon augmenter `timeout_sec` | |
| J7-M12 | Sécurité du paramétrage | Relire qui peut écrire dans le dossier de paramétrage | Seul le groupe d'administrateurs AD : qui modifie `programmes` fait exécuter un programme par le compte de service | |

## 10. Jalon J8 — Commandes pour le front-end

Testé le 2026-11-04 sur Windows 10, Python 3.14.10 : 537 tests au total (470 précédents + 67 de J8), tous OK en 7 min 35 s.

Le contrat complet est dans [07-contrat-moteur-frontend](07-contrat-moteur-frontend.md). Les contrôles d'accès (A01 à A07) ne sont **pertinents que sur le serveur d'exécution avec le compte de service** : le PC de développement ne prouve que la logique.

```powershell
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$py = 'C:\Python314\python.exe'
# vérification complète : syntaxe + accès (à lancer SUR LE SERVEUR avec le compte de service)
& $py -m file_management --config D:\Parametrage\recette.jsonl --verifier --format json | ConvertFrom-Json
# avant d'enregistrer une modification : syntaxe + comparaison avec la version actuelle
& $py -m file_management --config D:\Parametrage\nouveau.jsonl --verifier --syntaxe-seule --precedent D:\Parametrage\recette.jsonl --format json
# déblocage d'une règle qui ne répond plus
& $py -m file_management --config D:\Parametrage\recette.jsonl --debloquer export_clients --utilisateur DOMAINE\benoit --commentaire "bloquee" --format json
```

### 10.1 Tests automatiques

| ID | Fichier | Ce qui est vérifié | PC | Serveur |
|---|---|---|---|---|
| J8-A01 | `test_acces.py` | **A05** base : absente (message `--initialiser-base`), utilisable, d'un autre environnement, sur un lecteur réseau, qui n'est pas une base ; la vérification ne modifie pas la base | OK | |
| J8-A02 | `test_acces.py` | **A01 / A02 / A03** : source absente ou illisible ; cible existante, **absente (sera créée, rien n'est créé)**, sans création autorisée, impossible, en lecture seule ; dossier temporaire sur un autre volume ; archive inaccessible = avertissement ; archive relative datée ; règle inactive ignorée ; **aucune trace laissée** | OK | |
| J8-A03 | `test_acces.py` | **A04 / A06 / A07** : exécutable présent (chemin, `PATH`, variable d'environnement), introuvable, nom avec variable non vérifiable ; dossiers de journaux et de travail ; espace disponible en **information** (sans effet sur le code retour) ; 1 500 règles contrôlées en quelques secondes | OK | |
| J8-A04 | `test_acces.py` | Ligne de commande : vérification complète en JSON, code retour selon la gravité (0 / 4 / 2), `--syntaxe-seule` sans toucher aux dossiers, accès non contrôlés si le paramétrage est invalide | OK | |
| J8-A05 | `test_acces.py` | **Comparaison V01 à V04** : id modifié (refus), règle supprimée (avec historique), sélection élargie (fenêtre, masque, exclusion, récursivité, taille) sans faux positif quand elle se restreint, cible modifiée (écriture différente du même chemin ignorée), `--precedent` en ligne de commande | OK | |
| J8-A06 | `test_contrat.py` | **`--debloquer`** : processus et **descendants** arrêtés, règle en erreur (`deblocage`), trace et événement, `apres_erreur = continuer`, processus déjà disparu, **identifiant réutilisé non touché**, refus (règle non en cours, inconnue, autre serveur, processus courant, processus qui ne s'arrête pas), reprise ensuite nécessaire, **exécution suivie par un orchestrateur réel** | OK | |
| J8-A07 | `test_contrat.py` | **Contrat JSON** : un seul objet sur la sortie standard et rien sur l'erreur standard pour chaque commande ; clés exactes de `--etat` (règle, dernière erreur, dernière exécution), de `--verifier`, des commandes d'exploitation, du lancement ; refus et base absente en JSON ; paramétrage invalide ; **fils réels sans pollution de la sortie** ; erreurs d'arguments non JSON ; **vrai processus : UTF-8 strict, sans BOM, accents intacts** | OK | |

### 10.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J8-A08 | `test_fins_hors_execution.py` | **Fins hors exécution** : `--debloquer` et durée maximale dépassée appellent `sur_erreur` (variables `COPIE_SITUATION`, `COPIE_MESSAGE`), un `sur_erreur` en échec n'empêche pas le déblocage, `alerter` n'appelle rien ; les livraisons incertaines sont visibles et tranchables dès le déblocage ; **reprise d'une règle en aval seule** sans relancer l'amont, mais toujours bloquée si l'amont est en erreur, et un lancement manuel attend toujours l'amont | OK | |
| J8-M01 | **Accès avec le compte de service** | `--verifier --format json` sur la vraie configuration de recette, avec le compte de service Jenkins (`runas` ou job) | Aucun refus `A01` à `A05` ; les informations `A07` donnent l'espace réel ; noter tout refus avec son message | |
| J8-M02 | Droits retirés | Retirer au compte de service : lecture de la source / écriture de la cible / écriture de l'archive / base | Respectivement `A01`, `A02`, `A03` (avertissement) et `A05` ; rétablir les droits ensuite | |
| J8-M03 | Quota | Volume de la cible avec un quota pour le compte de service | `A07` indique l'espace du quota, pas l'espace du disque | |
| J8-M04 | Exécutable manquant | Renommer un programme référencé par une règle | `A04` nomme le point d'appel et le chemin | |
| J8-M05 | Aucun effet de bord | Comparer l'arborescence de la cible avant / après `--verifier` | Identique ; aucun dossier créé, aucun `.test_ecriture_*` restant | |
| J8-M06 | **Depuis le poste du front-end** | `Invoke-Command -ComputerName SERVEUR -ScriptBlock { & C:\Python314\python.exe -m file_management ... --format json }` puis `ConvertFrom-Json` | Un objet exploitable, accents corrects (avec `[Console]::OutputEncoding` en UTF-8) ; noter si les accents sont faux sans cette ligne | |
| J8-M07 | Comparaison de versions | Modifier une copie du paramétrage : changer un `id`, élargir `modifie_depuis`, changer une cible, supprimer une règle ; `--precedent` | `V01` (refus), `V03`, `V04`, `V02` conformes ; sans modification, aucun diagnostic | |
| J8-M08 | **Déblocage d'une vraie règle bloquée** | Règle qui attend longtemps (programme `sleep`), `--debloquer` depuis un autre compte | Le processus et le programme lancé disparaissent (`tasklist`), la règle est en `ERREUR` ; `--reprise` la relance | |
| J8-M09 | Déblocage depuis un autre serveur | `--debloquer` lancé depuis une machine qui n'est pas celle de l'exécution (base partagée impossible : tester sur la machine d'exécution) | Refus explicite si l'hôte diffère | |
| J8-M10 | Droits d'écriture du paramétrage | Compte non administrateur : tenter de modifier le dossier de paramétrage, puis lancer `--reprise` via le point de terminaison JEA | Écriture refusée par NTFS ; commande refusée par JEA ; `--etat` accessible | |

## 11. Jalon J9 — Intégration Jenkins

Testé le 2026-11-04 sur Windows 10, Python 3.14.10 : 562 tests au total (537 précédents + 25 de J9), tous OK en 8 min 6 s.

Guide de mise en place : [08-jenkins](08-jenkins.md). **Les fichiers Groovy n'ont jamais été exécutés dans un vrai Jenkins** (ni Jenkins ni Groovy sur le poste de développement) : seuls leur contenu statique et ce qu'ils font écrire sont vérifiés. **Les tests J9-M sont donc indispensables** et peuvent révéler des ajustements (version des modules, droits d'une bibliothèque, quotes).

```powershell
# ce que fait la bibliothèque partagée pour écrire un événement de job
$env:JOB_NAME='COPIE_PROD'; $env:BUILD_NUMBER='1'
C:\Python314\python.exe journal_si.py --dossier D:\Copie\logs --application file_management --environnement prod --evenement fin_job --niveau WARNING --champs-json champs.json
```

### 11.1 Tests automatiques (fichier `tests/test_jenkins.py`)

| ID | Ce qui est vérifié | PC | Serveur |
|---|---|---|---|
| J9-A01 | **`journal_si.py` en ligne de commande** : événement **au même format et dans le même ordre que le module**, variables Jenkins (`job`, `build`, `build_url`, `noeud`, dans `context`), fichier sans règle / avec règle, champs typés par JSON (accents, BOM, entiers, objets), niveaux, **ne lève jamais d'échec** (JSON absent ou cassé, dossier impossible → fichier de secours), console, vrai processus | OK | |
| J9-A02 | **Fichiers Jenkins** : délimiteurs équilibrés, pas de tabulation, UTF-8 sans BOM, fonctions de la bibliothèque, **statut Jenkins → niveau du journal**, options passées à `journal_si.py` existantes, codes 0 / 4 traduits, `UNSTABLE` = code 4 du moteur | OK | |
| J9-A03 | **Job de transfert** : builds simultanés autorisés (pas de `disableConcurrentBuilds`), `cron`, `timeout`, `debut_job` / `fin_job` ; sauvegarde et vérification sans builds simultanés ; **chaque `commande:` des Jenkinsfile est acceptée par l'analyseur d'arguments du moteur** | OK | |
| J9-A04 | **Deux builds simultanés** (vrais processus, huit règles) : chaque règle exécutée **une seule fois**, livrée une seule fois, aucun drapeau resté posé, événements identifiés par leur build ; un build ignore une règle déjà en cours dans l'autre sans erreur | OK | |
| J9-A05 | **Job simulé** : `debut_job` → lancement → `fin_job` avec le code retour ; code 0 puis code 4 (avertissement) ; code 2 pour un paramétrage invalide ; mêmes champs de job dans les événements du job et du lancement | OK | |
| J9-A06 | **Abandon d'un build** (vrais processus) : arbre de processus arrêté comme le fait Jenkins → plus aucun fils, drapeau libéré au lancement suivant (`arret_anormal`) ; **orchestrateur tué seul → ses fils disparaissent** (Job Object) | OK | |

### 11.2 Tests manuels sur Jenkins et le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J9-M01 | **Bibliothèque partagée** | Déclarer `journal-si`, créer le job de transfert depuis `jenkins/Jenkinsfile.transfert` (chemins adaptés), lancer un build | Le build démarre, la bibliothèque est chargée. **Noter la version de Jenkins et tout message de sécurité (signature à approuver)** | |
| J9-M02 | Premier lancement en simulation | Créer provisoirement `commande`/options pour `--simulation` ou lancer `--simulation` à la main sur l'agent | Liste des fichiers « à livrer », aucun fichier créé, code retour 0 | |
| J9-M03 | **Build de bout en bout** | Un fichier de recette déposé, build du job de transfert | Fichier livré, build `SUCCESS` (vert), console lisible avec accents, événements `debut_job` et `fin_job` dans `_orchestrateur_<jour>.jsonl` | |
| J9-M04 | Code retour 4 → `UNSTABLE` | Provoquer un avertissement (fichier à la date dans le futur, archive inaccessible) | Build jaune, message `au moins un avertissement`, `fin_job` au niveau WARNING | |
| J9-M05 | Code retour 1 / 2 → `FAILURE` | Source absente (1) ; paramétrage cassé (2) | Build rouge, code dans le message et dans `fin_job` (`code_retour`) | |
| J9-M06 | **Builds simultanés** | Règle longue (30 s) et cron toutes les minutes pendant 5 minutes | Plusieurs builds en même temps (autant d'exécuteurs que prévu), chaque règle exécutée une fois, aucun doublon dans la cible, aucun build en erreur à cause de la concurrence | |
| J9-M07 | **Nombre d'exécuteurs** | Appliquer la formule du §2 de 08-jenkins, observer la file d'attente sur une journée | Pas d'accumulation durable dans la file ; sinon ajouter des exécuteurs | |
| J9-M08 | **Abandon d'un build** | Lancer une règle longue (500 Mo), cliquer « Abandonner » dans Jenkins | Plus de `python.exe` du lancement ; au build suivant, règle en `ERREUR` (`arret_anormal`) ou livraison de résultat inconnu à trancher ; jamais de fichier partiel ni de doublon | |
| J9-M09 | Garde-fou `timeout` | Abaisser le `timeout` du job à 2 minutes avec une règle longue | Le build est interrompu, mêmes constats que J9-M08 | |
| J9-M10 | Panne de la journalisation | Retirer au compte de l'agent l'écriture sur `COPIE_LOGS` pendant un build | Le build n'échoue pas à cause du journal ; message `journal-si : …` ; ligne dans `journal_si_secours_*.jsonl` | |
| J9-M11 | **Alloy et Grafana** | Avec l'équipe de supervision : événements `debut_job` / `fin_job` visibles avec les libellés `application`, `environnement`, `niveau` ; lien du build (`build_url`) cliquable | Événements de job et de règles consultables ensemble | |
| J9-M12 | Sauvegarde nocturne | Lancer `Jenkinsfile.sauvegarde` à la main | Fichier `<environnement>_<date>.db` créé, build vert ; ouvrir la sauvegarde (cahier J2-M06) | |
| J9-M13 | Vérification nocturne | Lancer `Jenkinsfile.verification` | Vert si tout est accessible ; jaune ou rouge avec le diagnostic (code `A…`) dans la console | |
| J9-M14 | Compte de service | Rejouer J9-M03 et J9-M12 | Mêmes résultats, aucune erreur d'accès | |
| J9-M15 | Panne de Jenkins | Arrêter Jenkins 30 minutes puis le redémarrer | Au premier build, chaque règle part **une seule fois** (pas une fois par créneau manqué) | |

## 12. Jalon J11 — Migration et recette

Testé le 2026-11-04 sur Windows 10, Python 3.14.10 : 602 tests au total (562 précédents + 40 de J11), tous OK en 8 min 27 s.

Déroulement complet, étape par étape, et retour arrière : [09-migration-et-recette](09-migration-et-recette.md). Ce jalon est le seul qui **touche aux données de production** : les tests manuels se font d'abord sur une **copie** de `copies.conf` et de l'historique, avec des dossiers de recette.

```powershell
C:\Python314\python.exe -m file_management --migrer-ancien D:\Anciens\copies.conf --environnement recette --base D:\Copie\recette.db --sortie D:\Parametrage\recette.jsonl
C:\Python314\python.exe -m file_management --config D:\Parametrage\recette.jsonl --initialiser-base
C:\Python314\python.exe -m file_management --config D:\Parametrage\recette.jsonl --importer-historique D:\Anciens\copies.historique.copie.json --utilisateur DOMAINE\benoit
C:\Python314\python.exe outils\comparer_dossiers.py D:\Recette\cible_v1 D:\Recette\cible_v2 --dates
```

### 12.1 Tests automatiques (fichier `tests/test_migration.py`)

| ID | Ce qui est vérifié | PC | Serveur |
|---|---|---|---|
| J11-A01 | **Lecture de `copies.conf`** : la conf d'exemple du dépôt (`Legacy\copies.conf`) est analysée **comme le fait l'ancien script** (comparaison champ par champ avec lui), formats acceptés (BOM, commentaires, `oui`/`0`, `J - 7`, `ALL`), erreurs cumulées avec numéros de ligne, fichier absent ou vide | OK | |
| J11-A02 | **Conversion** : critères `TOUT`, `J`, `J-N`, masques, récursivité, comportement de l'ancien script conservé (`recopier`, `ecraser`), rétention toujours supérieure à la fenêtre (pas de R08), identifiants uniques, valides et bornés à 64 caractères, règles inactives par défaut, planification par défaut ou choisie, notes de revue, **jamais d'écrasement d'un paramétrage**, nom de sortie = environnement, accents conservés, défauts signalés par le contrôle standard | OK | |
| J11-A03 | **Commandes** : `--migrer-ancien` sans `--config`, sortie JSON, erreurs (conf invalide, option manquante, paramétrage généré refusé = code 2) | OK | |
| J11-A04 | **Import de l'historique** : versions copiées → `TERMINE` avec la bonne clé et les bonnes dates, **idempotent** et tracé, entrées sans règle (autre dossier, autre cible, autre nom, mauvais masque, sous-dossier d'une règle non récursive), règles récursives, choix de la règle par le masque, casse et variables d'environnement, historique absent / cassé / mal formé, entrées incomplètes, 20 000 entrées en quelques secondes | OK | |
| J11-A05 | **Parcours réel ancien script → nouveau** : l'ancien script copie vraiment, on migre, on importe → le nouveau moteur **ne relivre rien** (trois fichiers ignorés) ; **sans l'import il aurait tout relivré** ; une nouveauté et une version modifiée sont livrées comme avant, le résultat est identique à celui de l'ancien script ; un fichier perdu par la cible est recopié comme avant | OK | |
| J11-A06 | **Comparateur de dossiers** : identiques, absents d'un côté, taille ou contenu différent, casse, masque, temporaires ignorés, dates, codes retour | OK | |
| J11-A07 | Lanceur `file_management.py` (racine) équivalent à `python -m file_management` | OK | |

### 12.2 Tests manuels sur le serveur (sur des copies, puis en recette)

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J11-M01 | **Conversion de la vraie `copies.conf`** | `--migrer-ancien` sur une copie | Autant de règles que de lignes utiles, aucun refus ; relire les notes ; renommer les `id` | |
| J11-M02 | Vérification complète | `--verifier` avec le compte de service sur le fichier généré | Aucun refus `A01` à `A05` ; noter les avertissements | |
| J11-M03 | **Import de la vraie historique** (une copie) | `--importer-historique` | `sans_regle = 0` ou compris ; nombre importé = nombre de fichiers de l'historique | |
| J11-M04 | **Simulation après import** | `--simulation` sur une règle active en production de l'ancien script | Seules les vraies nouveautés sont « à livrer » ; tout le reste est ignoré | |
| J11-M05 | **Marche en parallèle** | Une règle peu critique, cible v2 distincte, 3 à 5 jours ouvrés ; `outils\comparer_dossiers.py` chaque jour | Aucun écart (présence, taille, SHA-256) | |
| J11-M06 | **Bascule d'une règle** | Étape 5 du guide (import, ancienne ligne commentée, règle `actif: true`) | Premier lancement : seules les nouveautés livrées, aucun doublon, journaux lisibles | |
| J11-M07 | **Retour arrière** | Après J11-M06 : règle v2 inactive, ligne `copies.conf` rétablie | L'ancien script reprend sans rien relivrer d'inutile ni perdre de fichier | |
| J11-M08 | Bascule de toutes les règles, une par une | Une règle par jour, la plus critique en dernier | Chaque bascule observée une journée complète avant la suivante | |
| J11-M09 | Fin de migration | Renommage des lanceurs (étape 7, fait dans le dépôt : l'ancien script est dans `Legacy\`), jobs Jenkins inchangés | `python file_management.py --config … --verifier` répond ; `Legacy\file_management_v1.py` conservé | |
| J11-M10 | **Restauration de la base** | Restaurer la dernière sauvegarde dans un dossier de recette et ouvrir (J2-M06) après quelques jours de production v2 | La base restaurée connaît les fichiers livrés ; un lancement ne relivre rien | |

## 13. Jalon J12 — Purge des journaux et des archives

Testé le 2026-11-04 sur Windows 10, Python 3.14.10 : 634 tests au total (602 précédents + 32 de J12), tous OK en 8 min 16 s.

Spécification : [02-moteur §11.2](02-moteur.md). La purge **supprime des données** : toujours commencer par la liste (sans `--appliquer`).

```powershell
C:\Python314\python.exe -m file_management --config D:\Parametrage\recette.jsonl --purger
C:\Python314\python.exe -m file_management --config D:\Parametrage\recette.jsonl --purger --regle r1 --appliquer
```

### 13.1 Tests automatiques (fichier `tests/test_purge.py`)

| ID | Ce qui est vérifié | PC | Serveur |
|---|---|---|---|
| J12-A01 | **Journaux** : rien sans rétention ; rétention d'en-tête et de règle ; limite exacte conservée ; journal d'une règle inconnue, journaux de secours et autres fichiers conservés ; filtre `--regle` ; le plan ne supprime rien ; fichier en lecture seule supprimé | OK | |
| J12-A02 | **Contrôle R13** : refus hors archivage, avec archive sans date, valeur invalide | OK | |
| J12-A03 | **Archives** : seuls les dossiers plus anciens que la rétention (jour, mois, année/mois/jour) ; dossiers non datés ou à date impossible jamais touchés ; contenu en lecture seule ; parents vides retirés ; archive absolue ailleurs | OK | |
| J12-A04 | **Garde-fous** : racine = source, dans ou contenant la cible, racine de disque refusées ; modèle sans variable / répétée / inconnue ; dossier visé par une action en attente protégé ; lien symbolique jamais suivi ; suppression hors racine refusée ; une erreur (fichier verrouillé) n'arrête pas les suivantes | OK | |
| J12-A05 | **Purge de la base** : une fois par jour, événement `purge_base` ; un échec n'est qu'un avertissement | OK | |
| J12-A06 | **Commande** : sans `--appliquer` rien n'est supprimé ; avec, suppression et trace au journal ; rien à purger ; règle non purgeable = code 4 ; base absente = code 2 ; `--appliquer` sans `--purger` refusé ; Jenkinsfile.purge accepté par l'analyseur d'arguments | OK | |

### 13.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J12-M01 | **Liste sans suppression** | Dossier de recette avec des journaux et des archives de dates variées ; `--purger` | La liste correspond à ce qui dépasse la rétention ; rien n'a disparu | |
| J12-M02 | Suppression réelle | Même jeu, `--purger --appliquer` | Seuls les éléments listés disparaissent ; événements `purge_supprime` dans le journal | |
| J12-M03 | **Droits** | Compte de service sans droit de suppression sur un dossier d'archive | `purge_echec`, code 4, les autres éléments sont purgés | |
| J12-M04 | **Archive sur partage réseau** | Archive absolue `\\serveur\partage\…\{AAAA}-{MM}-{JJ}` | Même résultat qu'en local ; aucun dossier hors de la racine touché | |
| J12-M05 | Job Jenkins | Créer le job `Jenkinsfile.purge` (sans `--appliquer`) | Liste visible dans le journal du build ; statut SUCCESS (UNSTABLE si avertissement) | |
| J12-M06 | Purge de la base | Deux lancements le même jour, puis le lendemain | `purge_base` une seule fois par jour | |

## 14. Jalon J10, étape A — Front-end : consultation

Testé le 2026-11-10 sur Windows 10, Windows PowerShell 5.1, Pester 5.9.1 : 42 tests Pester, tous OK (PSScriptAnalyzer sans avertissement), moteur Python 3.14.10 réel. Spécification : [04-frontend](04-frontend.md). L'interface est dans `Gui\` ; les étapes suivantes sont décrites aux §15 à §18 : cette étape ne modifie aucun fichier de paramétrage.

```powershell
.\Gui\Outils\Initialiser-Essai.ps1 -Destination D:\Essai\copie -Python C:\Python314\python.exe     # jeu d'essai (poste de développement)
.\Gui\Lancer-GestionCopie.ps1 -DossierParametrage D:\Essai\copie\parametrage -Config D:\Essai\copie\Gestion-Copie.essai.config.psd1
.\Gui\Tests\Run-Tests.ps1 -Python C:\Python314\python.exe                                        # tests Pester + PSScriptAnalyzer
```

### 14.1 Tests automatiques (dossier `Gui\Tests`)

| ID | Ce qui est vérifié | PC | Serveur |
|---|---|---|---|
| J10A-A01 | **Configuration** : valeurs de secours, groupe administrateur obligatoire, clé ou section inconnue refusée, mode `Distant` (serveur obligatoire), JEA (sans Python ni racine), JEA refusée en mode `Local`, fichier absent, fichier fourni accepté | OK | |
| J10A-A02 | **Droits** : nom complet, nom sans domaine, SID, casse ignorée, nom proche non confondu, aucun groupe, jeton Windows réel | OK | |
| J10A-A03 | **Dossier de paramétrage** : un onglet par fichier, BOM ou non, accents, lecture seule si environnement ≠ nom du fichier / version inconnue ou absente / doublon / JSON invalide (numéro de ligne) / fichier vide, autres extensions ignorées, dossier absent, empreinte stable | OK | |
| J10A-A04 | **Mise en forme** : dates UTC → locales, durées, planification en clair, couleurs de statut, champs absents (« défaut du moteur »), ligne de grille avec et sans état, cartes de détail et d'état | OK | |
| J10A-A05 | **Appel du moteur réel** : JSON décodé (accents), code 2 si la base n'existe pas, état après initialisation, chemin avec espaces, Python introuvable sans exception, délai maximal (processus arrêté) | OK | |
| J10A-A06 | **Fenêtre** : vues XAML chargées et contrôles retrouvés, un onglet par fichier, profil administrateur / lecture seule, état du moteur dans la grille, filtres (mode, recherche), détail et état à la sélection, journal JSON de l'interface | OK | |
| J10A-A07 | **Initialiser-DossierParametrage.ps1** : essai à la main sur un dossier temporaire (`-WhatIf` ne crée rien, refus si le compte n'est pas dans le groupe, droits posés : SYSTEM, groupe en modification, compte de service en lecture seule, versions sans le compte de service) | OK (manuel) | |

### 14.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J10A-M01 | **Windows PowerShell 5.1 du serveur** | `Gui\Tests\Run-Tests.ps1` sur Windows Server 2016 (Pester 5 à installer si absent) | Tous les tests passent | |
| J10A-M02 | **Dossier protégé** | `Initialiser-DossierParametrage.ps1 -WhatIf` puis réel avec le vrai groupe et le vrai compte de service Jenkins | Droits conformes (`Get-Acl`) ; un compte hors groupe ne voit pas le dossier | |
| J10A-M03 | **Jenkins lit, ne modifie pas** | Un job Jenkins (compte de service) lance le moteur sur ce dossier ; essai d'écriture avec ce compte | Lecture OK ; écriture refusée ; le sous-dossier des versions est inaccessible | |
| J10A-M04 | **Ouverture administrateur** | `Lancer-GestionCopie.ps1 -DossierParametrage <dossier>` avec un membre du groupe | Badge « ADMINISTRATEUR », onglets sans « lecture seule » | |
| J10A-M05 | **Consultation seule** | Même commande avec un compte hors groupe (qui a accès au dossier) | Badge « LECTURE SEULE », bandeau « consultation uniquement » | |
| J10A-M06 | **Groupe vide ou absent de la configuration** | Retirer `GroupesAdmin` | L'outil refuse de démarrer avec un message clair | |
| J10A-M07 | **État des règles** | Ouvrir l'onglet de production après quelques lancements Jenkins | Statuts, derniers lancements et prochains créneaux cohérents avec `--etat` en ligne de commande | |
| J10A-M08 | **Vérification** | Bouton « Vérifier le paramétrage » | Même liste de refus, avertissements et informations que `--verifier` ; une ligne dans le journal de l'outil | |
| J10A-M09 | **Mode distant, compte administrateur** | Depuis un poste : `Moteur.Mode = 'Distant'`, `ConfigurationJea` vide | Mêmes résultats qu'en local ; les contrôles d'accès (A01 à A07) reflètent le compte de l'administrateur | |
| J10A-M10 | **Mode distant, point d'accès JEA** | Créer le point d'accès (fonction `Invoke-CopieMoteurJea`, voir 04 §6), renseigner `ConfigurationJea` | Mêmes résultats ; les contrôles d'accès reflètent le compte de service ; une commande hors liste est refusée | |
| J10A-M11 | **Fichier non pris en charge** | Déposer un fichier dont l'environnement diffère de son nom | Onglet « (lecture seule) » avec le message | |
| J10A-M12 | **Durée d'ouverture** | Chronométrer l'ouverture avec les vrais environnements | Noter la durée (un appel du moteur par environnement) ; si elle gêne, l'étape C ajoutera l'exécution en arrière-plan | |

## 15. Jalon J10, étape B — Front-end : édition

Testé le 2026-11-10 sur Windows 10, Windows PowerShell 5.1, Pester 5.9.1 : 66 tests Pester (dont 24 propres à l'étape B), tous OK, PSScriptAnalyzer sans avertissement, moteur Python 3.14.10 réel ; 8 tests Python (`tests/test_modele.py`) pour `--modele-regle`. Spécification : [04-frontend](04-frontend.md) §4.2 et §5. Les étapes C et D ne sont pas faites. **Les formulaires n'ont été construits et relus que par programme (contrôles WPF réels, non affichés) et vus sur capture d'écran ; ils n'ont pas été joués à la souris.**

### 15.1 Tests automatiques

| ID | Ce qui est vérifié | PC | Serveur |
|---|---|---|---|
| J10B-A01 | **`--modele-regle`** (Python) : la règle par défaut complétée est acceptée telle quelle par le moteur, valeurs de secours identiques à celles du moteur, aucun champ inconnu, listes égales aux constantes du moteur, commande JSON sans `--config` | OK | |
| J10B-A02 | **Écriture JSON** : ligne compacte, tableaux à un élément et `null` conservés, accents et caractères spéciaux, imbrication profonde, numéro de ligne jamais écrit | OK | |
| J10B-A03 | **Fusion et tri** : le modèle complète une règle existante sans rien perdre, ordre des champs, dépendances rangées avant leurs dépendantes, boucle ou dépendance inconnue sans blocage, nom de version | OK | |
| J10B-A04 | **Enregistrement sécurisé (moteur réel)** : fichier remplacé, UTF-8 sans BOM, version et fiche `.meta.json` créées, brouillons supprimés ; refus du moteur (R02, V01, D03) sans toucher au fichier ; édition simultanée refusée ; avertissements refusés puis acceptés (tracés dans la fiche) ; moteur injoignable sans écriture | OK | |
| J10B-A05 | **Formulaire** : jours (tous, plages, listes), durées et unités, formulaire non touché = règle de départ à l'octet près, tableaux à un élément, saisies incorrectes signalées par nom de champ, identifiant déjà pris, champs de planification selon le type, règle saisie acceptée par le moteur | OK | |

### 15.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J10B-M01 | **Boutons réservés aux administrateurs** | Ouvrir avec un compte hors groupe, puis avec un administrateur | Hors groupe : aucun bouton d'édition ; administrateur : Ajouter, Dupliquer, Modifier, Activer, Supprimer (les quatre derniers actifs après sélection) | |
| J10B-M02 | **Ajouter une règle** | Ajouter une règle quotidienne, laisser les valeurs de secours, saisir un commentaire | Règle dans la grille, version précédente et fiche dans `versions`, ligne dans le journal de l'outil, proposition de vérification complète | |
| J10B-M03 | **Refus du moteur** | Ajouter une règle dont l'identifiant est invalide, puis une dont la dépendance n'existe pas | Fenêtre des refus avec les codes ; le formulaire se rouvre avec la saisie ; le fichier n'a pas changé | |
| J10B-M04 | **Avertissement** | Planifier un intervalle de 60 secondes | Avertissement (P02) à confirmer ; refusé : rien n'est écrit ; accepté : enregistré, avertissement dans la fiche | |
| J10B-M05 | **Dupliquer / modifier** | Dupliquer une règle, modifier la copie ; modifier l'original (l'identifiant n'est pas modifiable) | Les deux règles coexistent, valeurs reprises à l'identique | |
| J10B-M06 | **Activer / désactiver** | Désactiver une règle dont une autre dépend, puis une règle sans dépendante | Refus D03 pour la première ; la seconde passe en « Non » | |
| J10B-M07 | **Supprimer** | Supprimer une règle sans dépendante | Disparaît du fichier ; son historique reste en base (visible par `--etat` comme règle orpheline) | |
| J10B-M08 | **Tri automatique** | Ajouter une règle qui dépend d'une règle placée plus bas dans le fichier | Dans le fichier, la dépendance est avant la dépendante | |
| J10B-M09 | **Édition simultanée** | Ouvrir l'outil, modifier le fichier à la main (ou depuis un second poste), puis enregistrer depuis l'outil | Message « fichier modifié » ; rechargement ; rien n'est écrit | |
| J10B-M10 | **Droits NTFS** | Enregistrer avec un administrateur, vérifier avec `Get-Acl` | Le fichier remplacé garde les droits du dossier (compte de service en lecture seule) ; le dossier `.brouillons` est vide | |
| J10B-M11 | **Mode distant** | Enregistrer depuis un poste distant (mode `Distant`, administrateur puis JEA) | Même résultat qu'en local ; la vérification se fait sur le serveur d'exécution | |
| J10B-M12 | **Programmes et situations** | Activer un programme (une commande, un élément par ligne) et modifier une situation | Écrits tels quels dans le fichier (`commande` est un tableau, même à un élément) | |

## 16. Jalon J10, étape C — Front-end : exploitation

Testé le 2026-11-10 sur Windows 10, Windows PowerShell 5.1, Pester 5.9.1 : 83 tests Pester (dont 17 propres à l'étape C), tous OK, PSScriptAnalyzer sans avertissement, moteur Python 3.14.10 réel. Spécification : [04-frontend](04-frontend.md) §4.3. L'étape D n'est pas faite. **Les fenêtres de confirmation, la fenêtre de purge et le grisage des boutons pendant un appel en arrière-plan n'ont pas été joués à la souris** ; seuls leur logique et l'état des boutons sont testés par programme.

### 16.1 Tests automatiques

| ID | Ce qui est vérifié | PC | Serveur |
|---|---|---|---|
| J10C-A01 | **Chaîne de reprise** : règles dépendantes de proche en proche, casse ignorée, dépendance circulaire sans blocage | OK | |
| J10C-A02 | **Arguments des actions** : ligne de commande du contrat pour reprise, lancement, acquittement, déblocage ; compte avec antislash ; commentaire ignoré pour le lancement ; acquittement sans commentaire refusé | OK | |
| J10C-A03 | **Moteur réel** : reprise tracée (drapeau visible dans `--etat`), lancement immédiat, refus du déblocage d'une règle qui ne tourne pas, refus de l'acquittement d'une règle inconnue | OK | |
| J10C-A04 | **Exécution en arrière-plan** : la main est rendue avant la fin de l'appel, la réponse parvient au bloc de fin avec ses données, plusieurs tâches simultanées, Python introuvable sans exception, une exception du bloc de fin ne bloque pas les autres tâches | OK | |
| J10C-A05 | **Purge** : liste sans suppression puis application, en arrière-plan ; mise en forme des éléments (taille, chemin) | OK | |
| J10C-A06 | **Boutons** : visibles pour l'administrateur, actifs selon la sélection (Purger sans sélection), tous grisés pendant un appel en arrière-plan puis réactivés | OK | |

### 16.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J10C-M01 | **Droits** | Ouvrir avec un compte hors groupe, puis avec un administrateur | Hors groupe : aucun bouton d'exploitation (seul « Actualiser l'état ») ; administrateur : Reprise, Lancer maintenant, Acquitter, Débloquer, Purger… | |
| J10C-M02 | **Reprise en cascade** | Provoquer une erreur sur une règle dont d'autres dépendent, puis « Reprise » | La confirmation liste les règles dépendantes ; au job suivant, la chaîne repart ; le compte et le commentaire figurent dans le journal du moteur | |
| J10C-M03 | **Lancer maintenant** | Sur une règle quelconque, hors de son heure | Elle part au prochain lancement du job, sans programme « reprise » | |
| J10C-M04 | **Acquitter** | Sur une règle en erreur | Commentaire exigé ; statut cohérent après « Actualiser l'état » | |
| J10C-M05 | **Débloquer** | Pendant l'exécution d'une règle longue (programme qui dort) | Avertissement ; processus et descendants arrêtés ; message « reprise nécessaire » si `apres_erreur = arreter` | |
| J10C-M06 | **Refus du moteur** | Reprise d'une règle en cours | Le message du moteur est affiché ; rien n'est modifié | |
| J10C-M07 | **Purge** | « Purger… » avec des journaux plus anciens que la rétention | Liste exacte ; « Fermer sans purger » ne supprime rien ; « Purger » supprime et affiche le bilan ; la fenêtre reste utilisable pendant la recherche | |
| J10C-M08 | **Purge d'une règle** | Sélectionner une règle puis « Purger… » → Oui | Seuls les éléments de cette règle sont listés | |
| J10C-M09 | **Vérification en arrière-plan** | « Vérifier le paramétrage » sur un environnement dont les dossiers sont lents (partage réseau) | La fenêtre ne se fige pas ; boutons de l'onglet grisés puis réactivés ; résultat identique à `--verifier` | |
| J10C-M10 | **Mode distant / JEA** | Mêmes actions depuis un poste distant, administrateur puis JEA | Mêmes résultats ; le compte tracé est celui de l'administrateur connecté | |
| J10C-M11 | **Durée d'ouverture** | Chronométrer l'ouverture avec les vrais environnements | Noter la durée ; l'état est encore chargé de façon synchrone à l'ouverture | |

## 17. Jalon J10, étape D — Front-end : graphe, promotion, historique

Testé le 2026-11-11 sur Windows 10, Windows PowerShell 5.1, Pester 5.9.1 : 102 tests Pester (dont 19 propres à l'étape D), tous OK, PSScriptAnalyzer sans avertissement, moteur Python 3.14.10 réel. Spécification : [04-frontend](04-frontend.md) §4.1 et §4.2. C'est la dernière étape du front-end. **Les fenêtres (historique, promotion) et le clic sur le graphe n'ont pas été joués à la souris** ; la logique, la construction des contrôles et le dessin du graphe sont testés par programme (capture d'écran du graphe vérifiée à l'œil).

### 17.1 Tests automatiques

| ID | Ce qui est vérifié | PC | Serveur |
|---|---|---|---|
| J10D-A01 | **Disposition du graphe** : niveaux (une règle à droite de ses dépendances), règles sans lien non dessinées et comptées, aucun nœud superposé, casse des identifiants, dépendances inconnues signalées, boucle et auto-dépendance sans blocage, liste vide | OK | |
| J10D-A02 | **Comparaison de versions** : rapprochement par identifiant, règle ajoutée, supprimée, modifiée champ par champ (tableaux, booléens, objets imbriqués), en-tête, simple déplacement de règle sans différence | OK | |
| J10D-A03 | **Liste des versions** : filtrage exact sur l'environnement (`prod_x_…` et `autre_…` écartés), tri du plus récent au plus ancien, fiche lue (compte, commentaire, avertissements, date UTC → locale), version sans fiche, absence de dossier | OK | |
| J10D-A04 | **Historique de bout en bout (moteur réel)** : deux enregistrements successifs, deux entrées avec leurs commentaires, différences de chacune (règle ajoutée, durée modifiée) | OK | |
| J10D-A05 | **Promotion** : remplacement dans les dossiers et les commandes de programmes, casse ignorée, texte littéral (pas d'expression régulière ni de `$1`), tableau `commande` à un élément conservé, original intact, dépendances absentes de la cible | OK | |
| J10D-A06 | **Fenêtres** : l'historique affiche les différences de la version choisie ; l'aperçu de la promotion montre les chemins adaptés, la règle déjà présente et les dépendances absentes | OK | |
| J10D-A07 | **Graphe dans la fenêtre** : un nœud par règle liée, une flèche par dépendance, le clic sélectionne la règle ; boutons Promouvoir et Historique | OK | |

### 17.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J10D-M01 | **Graphe sur les vrais environnements** | Ouvrir l'onglet « Dépendances » d'un environnement avec des chaînes de règles | Colonnes cohérentes avec les champs `apres` ; couleurs conformes aux statuts ; infobulle lisible | |
| J10D-M02 | **Règle qui en retient une autre** | Provoquer une erreur sur une règle dont une autre dépend, puis « Actualiser l'état » | La règle dépendante est `BLOQUEE` ou `EN_ATTENTE`, la flèche venant de la règle en erreur est rouge | |
| J10D-M03 | **Clic sur un nœud** | Cliquer sur un nœud | La règle est sélectionnée dans la grille (si un filtre la masque, rien ne se passe) | |
| J10D-M04 | **Grand graphe** | Environnement avec plus de 30 règles liées | Défilement horizontal et vertical, pas de superposition ; noter si la lisibilité suffit | |
| J10D-M05 | **Historique** | Après plusieurs modifications, « Historique… » | Une ligne par modification avec compte, date et commentaire ; différences exactes pour chacune | |
| J10D-M06 | **Droits sur les versions** | Ouvrir l'historique avec un compte qui n'a pas accès au dossier des versions | Message clair, pas d'exception | |
| J10D-M07 | **Promotion simple** | Promouvoir une règle de recette vers production en remplaçant `\\serveur-recette\` par `\\serveur-prod\` | Aperçu exact ; formulaire de production prérempli ; enregistrement avec commentaire ; version et fiche dans `versions` de production | |
| J10D-M08 | **Promotion d'une règle existante** | Promouvoir une règle déjà présente dans la cible | Confirmation de remplacement ; identifiant conservé ; la règle de la cible est remplacée, l'ancienne est dans les versions | |
| J10D-M09 | **Dépendance absente** | Promouvoir une règle dont la dépendance n'existe pas dans la cible | Avertissement dans la fenêtre de promotion ; refus D01 du moteur à l'enregistrement tant qu'elle manque | |
| J10D-M10 | **Programmes** | Promouvoir une règle qui a un programme dont la commande contient un chemin de l'environnement d'origine | Le chemin est adapté dans la commande ; l'aperçu le montre | |

## 18. Jalon J10, étape E — Front-end : compléments (JEA, livraisons incertaines, état en arrière-plan, restauration)

Testé le 2026-11-11 sur Windows 10, Windows PowerShell 5.1, Pester 5.9.1 : 127 tests Pester (dont 25 propres à l'étape E), tous OK, PSScriptAnalyzer sans avertissement, moteur Python 3.14.10 réel ; tests Python du moteur : nouveau champ `incertains` de `--etat`. Spécification : [04-frontend](04-frontend.md) §4.3, §6, §8 et [07-contrat-moteur-frontend](07-contrat-moteur-frontend.md) §4.2. **Jamais exécuté** : une vraie session JEA (elle exige un serveur, un compte d'administrateur local et un groupe AD) et les fenêtres à la souris. La logique est testée par programme, le module JEA est appelé directement (sans session).

### 18.1 Tests automatiques

| ID | Ce qui est vérifié | PC | Serveur |
|---|---|---|---|
| J10E-A01 | **Moteur** : `--etat` donne `incertains` (clé hexadécimale, source, cible) ; le décompte baisse après `--trancher-incertain` | OK | |
| J10E-A02 | **JEA, grammaire** : commandes du contrat acceptées ; `--initialiser-base`, `--sauvegarder-base`, `--lancer-regle`, `--migrer-ancien`, `-c`, commande vide, option inconnue, répétée, sans valeur ou d'une autre commande refusées | OK | |
| J10E-A03 | **JEA, valeurs** : identifiant, clé hexadécimale et décision contrôlés ; un commentaire qui commence par un tiret n'est pas pris pour une option (`--option=valeur`) | OK | |
| J10E-A04 | **JEA, fichiers** : seuls les fichiers du dossier de paramétrage (et `--precedent`) ; `..`, dossier voisin au nom proche (`param2`), autre disque refusés ; casse ignorée | OK | |
| J10E-A05 | **JEA, compte et droits** : le compte de la session remplace `--utilisateur` annoncé ; commande d'écriture refusée hors du groupe administrateur ; consultation permise ; configuration absente refusée | OK | |
| J10E-A06 | **JEA, moteur réel** : `--modele-regle` sans fichier, `--verifier --syntaxe-seule`, refus d'une commande hors contrat sans lancer le moteur | OK | |
| J10E-A07 | **Installateur** : s'analyse sans erreur, refuse un groupe mal écrit, `-WhatIf` ne crée rien | OK | |
| J10E-A08 | **Trancher** : ligne de commande (commentaire obligatoire, clé hexadécimale, décision), mise en forme de la liste, moteur réel (livré puis à relivrer, clé déjà tranchée refusée avec son message) | OK | |
| J10E-A09 | **Fenêtre « Trancher »** : validation grisée tant qu'une ligne et une décision ne sont pas choisies | OK | |
| J10E-A10 | **État en arrière-plan** : liste du fichier tout de suite sans état, boutons grisés, état et sélection à l'arrivée ; réponse d'un onglet reconstruit ignorée | OK | |
| J10E-A11 | **Restauration** : le fichier redevient l'état d'avant, par l'enregistrement sécurisé, avec avertissement confirmé ; l'historique garde les trois lignes | OK | |

### 18.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J10E-M01 | **Installer le point d'accès** | En administrateur sur le serveur d'exécution : `Installer-PointAccesJea.ps1 -WhatIf` puis sans, avec le groupe, Python, la racine, le dossier de paramétrage et `-CompteService` | Message de fin ; `Get-PSSessionConfiguration FileManagement` existe ; module dans `Program Files\WindowsPowerShell\Modules` | |
| J10E-M02 | **Session restreinte** | `Enter-PSSession -ComputerName SERVEUR -ConfigurationName FileManagement` puis `Get-Command` | Seule `Invoke-CopieMoteurJea` (et les commandes de base de JEA) ; `Get-Process`, `dir`, `python` refusés | |
| J10E-M03 | **Consultation par un membre du groupe de lecture** | Interface en mode `Distant` + `ConfigurationJea` : ouvrir un environnement, « Actualiser l'état », « Vérifier » | État et vérification affichés ; les contrôles d'accès reflètent le compte de service | |
| J10E-M04 | **Écriture refusée au lecteur** | Même compte, tenter une reprise (appel direct de la fonction) | « commande réservée aux administrateurs » | |
| J10E-M05 | **Compte tracé** | Reprise par un administrateur depuis l'interface | Dans la base, le journal du moteur et la transcription : le compte de l'administrateur, pas le compte de service | |
| J10E-M06 | **Commande hors liste** | Dans la session : `Invoke-CopieMoteurJea -Argument '--initialiser-base' -Fichier ...` et un fichier hors du dossier de paramétrage | Refus, le moteur n'est pas lancé | |
| J10E-M07 | **Partages réseau** | `--verifier` complet par JEA sur une règle dont la source est un partage | Les accès A01 à A07 reflètent le compte de service géré (pas la machine) | |
| J10E-M08 | **Transcriptions** | Après les essais, ouvrir le dossier des traces | Une transcription par session, avec la commande lancée | |
| J10E-M09 | **Livraison incertaine** | Interrompre brutalement une copie (arrêt du processus), relancer, puis « Actualiser l'état » et « Trancher… » | La règle est en erreur « livraison incertaine » ; la liste montre la source et la cible ; après vérification et décision, le décompte baisse et le moteur répond | |
| J10E-M10 | **Décision « à relivrer »** | Trancher « à relivrer », puis demander une reprise | Le fichier est relivré au lancement suivant | |
| J10E-M11 | **Ouverture sans blocage** | Ouvrir l'interface avec plusieurs environnements sur un serveur distant lent | La fenêtre apparaît tout de suite avec les règles ; les statuts arrivent ensuite | |
| J10E-M12 | **Restauration** | Après deux modifications, « Historique… », choisir la plus ancienne, « Revenir à l'état d'avant cette modification… » | Confirmation avec le nombre de différences, commentaire demandé, fichier rétabli, nouvelle ligne dans l'historique ; une restauration qui supprime une règle demande confirmation des avertissements | |

## 19. Jalon J10, étape F — Dossier absent ou vide, environnements, simulation, contrôle des répertoires

Testé le 2026-11-11 sur Windows 10, Windows PowerShell 5.1, Pester 5.9.1 : 155 tests Pester, tous OK, PSScriptAnalyzer sans avertissement, moteur Python réel. Spécification : [04-frontend](04-frontend.md) §3, §4.2 bis et ter, [07-contrat-moteur-frontend](07-contrat-moteur-frontend.md) §4. **Jamais exécuté** : les fenêtres à la souris, une vraie session JEA, le serveur Windows Server 2016.

### 19.1 Tests automatiques

| ID | Ce qui est vérifié | PC | Serveur |
|---|---|---|---|
| J10F-A01 | **Moteur, simulation JSON** : `apercu` (fichier, cible, taille), `apercu_total`, plafond, `source` / `cible` / `mode` ; rien n'est écrit ; **aucune temporisation** (source absente signalée tout de suite) | OK | |
| J10F-A02 | **Moteur, contrôles** : existence, lecture, écriture, espace nécessaire (volume + marge), dossier à créer, espace insuffisant (simulé) ; l'essai d'écriture ne laisse aucun fichier | OK | |
| J10F-A03 | **Moteur, `--controler-regle`** : sans base, sans livraison ; règle inconnue refusée | OK | |
| J10F-A04 | **Moteur, `--creer-dossiers-regle`** : exige `--utilisateur`, crée la cible et, sur demande, la source absente (le moteur ne la crée **jamais** seul au lancement) | OK | |
| J10F-A05 | **Moteur, `--renommer-environnement`** : la base absente du nouveau nom est refusée avant, acceptée après ; trace dans le journal des actions ; refusé si une règle est en cours | OK | |
| J10F-A06 | **JEA** : `--lancer-regle` accepté seulement avec `--simulation` (lecture) ; `--controler-regle` (lecture) ; `--initialiser-base`, `--renommer-environnement`, `--creer-dossiers-regle` (écriture) | OK | |
| J10F-A07 | **Dossier de paramétrage** : absent + administrateur → question, création ou refus ; absent + non administrateur → message avec le groupe, rien créé ; vide, invalide, fichier, relatif, guillemets | OK | |
| J10F-A08 | **Fenêtre** : dossier vide → écran « aucun environnement », bouton de création pour l'administrateur seulement ; barre des environnements visible pour l'administrateur seulement et active selon l'onglet | OK | |
| J10F-A09 | **Saisie d'un environnement** : nom, base (réseau, relative, vide, doublon), dossier de travail doublon, entiers ; en-tête construit sans champ vide | OK | |
| J10F-A10 | **Créer** (moteur réel) : fichier vérifié, base créée, aucun brouillon laissé ; refus sans droit, nom ou base pris | OK | |
| J10F-A11 | **Renommer** (moteur réel) : fichier, en-tête, base rouverte par le moteur, versions renommées (pas celles d'un autre environnement), règles conservées ; refus : nom identique, invalide, existant, sans droit | OK | |
| J10F-A12 | **Supprimer** (moteur réel) : fichier et versions rangés, fiche, base intacte ; refus sans droit ou sans commentaire | OK | |
| J10F-A13 | **Copier** (moteur réel) : toutes les règles, désactivées ou actives, dépendances et répertoires conservés, base propre, original intact ; même base ou même dossier de travail refusés | OK | |
| J10F-A14 | **Simulation** (moteur réel) : « Déplacera 2 fichier(s) … vers … », cible à créer signalée, création puis tout OK, source absente = problème non créable | OK | |
| J10F-A15 | **Résumé** : phrases copie / archivage / vide, verdicts (droits refusés, espace insuffisant, volume incorrect), tailles | OK | |
| J10F-A16 | **Dossiers d'un environnement** : contrôle (trois dossiers à créer, rien créé), création, second contrôle propre, valeurs par défaut (`logs`, `travail` à côté de la base), lecteur introuvable non créable, aucun fichier d'essai laissé | OK | |
| J10F-A17 | **Une seule question** : trois dossiers absents = une question qui les nomme ; refus = rien créé ; accord = créés ; tout existe = aucune question | OK | |
| J10F-A18 | **Création d'environnement** (moteur réel) : question refusée = fichier créé, base non créée, résultat explicite ; question acceptée = base créée dans le dossier créé | OK | |
| J10F-A19 | **JEA** : `Invoke-CopieDossiersJea` contrôle en lecture, refuse la création hors groupe administrateur, refuse un fichier hors du dossier de paramétrage, crée pour un administrateur | OK | |
| J10F-A20 | **Détection du moteur** : configuration correcte = aucune question ; chemins d'exemple = une question, correction pour la session ; refus = configuration inchangée et message ; rien trouvé = message sans question ; mode Distant ignoré | OK | |
| J10F-A23 | `Api.Tests.ps1` | **API de règles** (module `FileManagement.Regles`, seul écrivain) : le noyau d'écriture n'est plus dans l'interface ; ajout complété par le modèle du moteur, version précédente conservée avec le commentaire `[API appelant]`, brouillon nettoyé ; doublon (`existe`), id absent et commentaire vide (`invalide`) ; modification partielle avec fusion des objets ; empreinte périmée = `conflit` sans écriture ; champ inconnu = refus E06 sans écriture ; avertissements refusés sans accord explicite ; compte hors `GroupesAdmin` = `droits` ; journal de l'API ; ligne de commande (codes retour 0, 1, 2) ; client Python (ajout, conflit) ; suppression ; **planification unique** : date à moins de deux périodes du déclencheur refusée à l'ajout et à la modification (étape `delai`, date minimale donnée, rien écrit), date non modifiée non contrôlée | OK | |
| J10F-A22 | `Formulaire.Tests.ps1`, `Socle.Tests.ps1` | **Planification `unique` (OneShot)** : le champ « Date et heure de lancement » n'apparaît que pour ce type (avec le rattrapage, sans les jours) ; date lue, refusée si mal écrite, passée ou à moins de deux périodes du déclencheur (période réglable ; sauf règle déjà jouée non touchée) ; affichage « une seule fois, le … à … » ; la règle jouée apparaît inactive (colonne Active « Non », ligne grise) et l'état explique pourquoi | OK | |
| J10F-A21 | `Garde.Tests.ps1` | **Dossier du journal de l'interface** : sans `Journal.Dossier` rien n'est demandé ; dossier existant = aucune question ; absent + accord = une seule question et dossier créé ; absent + refus, chemin qui désigne un fichier, chemin relatif ou création impossible = journal fichier désactivé avec la raison, rien de créé ; `Write-CopieJournal` ne crée jamais le dossier (panne signalée une fois) | OK | |

### 19.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J10F-M01 | **Dossier absent** | `Lancer-GestionCopie.ps1 -DossierParametrage D:\Parametrage\neuf` en administrateur, puis en simple lecteur | Administrateur : question de création, dossier créé, écran « aucun environnement » puis proposition de créer le premier ; lecteur : message avec le groupe, rien créé | |
| J10F-M02 | **Créer un environnement** | « Nouvel environnement… » avec une base locale, case « créer la base » | Fichier créé, base créée, onglet affiché ; base sur un partage refusée | |
| J10F-M03 | **Renommer** | Renommer puis lancer le moteur (`--etat`) ; essayer pendant l'exécution d'une règle | Le moteur rouvre la base sous le nouveau nom ; refus pendant l'exécution ; l'historique des versions suit | |
| J10F-M04 | **Copier** | « Copier vers un nouvel environnement… » | Toutes les règles présentes, désactivées ; répertoires à modifier | |
| J10F-M05 | **Supprimer** | Supprimer : annuler au 1er avertissement, puis au 2e (mauvais nom : bouton grisé), puis confirmer | Fichier et versions dans `.supprimes\…` ; base intacte ; remise en place du fichier = environnement de retour | |
| J10F-M06 | **Contrôle après enregistrement** | Enregistrer une règle dont la cible n'existe pas ; puis une dont la source n'existe pas ; puis une cible sans droit d'écriture | Cible : proposition de créer ; source : problème, pas de création ; droit : message avec le compte utilisé (JEA : compte de service) | |
| J10F-M07 | **Simulation** | « Simuler la règle… » sur une règle avec des fichiers en attente | Phrase correcte, contrôles, liste ; rien n'a bougé ; espace insuffisant signalé sur un petit volume de test | |
| J10F-M09 | **Dossiers d'un environnement** | Créer « preprod » avec une base, un dossier de journaux et un dossier de travail qui n'existent pas ; répondre Non, puis recommencer avec Oui | Une seule question qui nomme les trois dossiers ; Non : fichier créé, base non créée, message ; Oui : dossiers et base créés, lignes `dossier_cree` dans le journal de l'interface | |
| J10F-M10 | **Python introuvable** | Lancer avec la configuration modèle (chemins d'exemple) sur un poste où Python est dans le PATH | Une question propose Python et le dépôt trouvés ; Oui : tout fonctionne pour la session ; le fichier de configuration est inchangé | |
| J10F-M11 | **Dossiers par JEA** | Créer un environnement avec `ConfigurationJea`, dossiers absents, avec puis sans le groupe administrateur | Administrateur : question puis création avec le compte de service ; autre : création refusée, message clair | |
| J10F-M13 | **Règle OneShot** | Essayer d'abord une date dans 5 minutes (refusée, avec la date minimale) ; créer une règle de type `unique` dans 15 minutes ; attendre le passage du moteur après l'heure ; la sélectionner ; changer la date pour la réarmer | Avant : « une seule fois, le … » et prochain créneau = la date. Après le run : statut INACTIVE, « Active : Non », motif « planification unique exécutée… », prochain créneau vide ; le fichier garde `actif: true`. Nouvelle date : la règle redevient active et repart à cette date | |
| J10F-M12 | **Dossier du journal absent** | Renseigner `Journal.Dossier` avec un dossier qui n'existe pas, lancer l'interface ; répondre Non, relancer, répondre Oui | Une seule question avec le chemin ; Non : la barre d'état indique « journal fichier désactivé » et le panneau du bas dit pourquoi, rien n'est créé ; Oui : dossier créé, un fichier `GestionCopie_AAAA-MM-JJ.jsonl` apparaît | |
| J10F-M08 | **Simulation par JEA** | Même simulation avec `ConfigurationJea` | Résultat identique ; la commande n'est pas refusée ; `--lancer-regle` sans `--simulation` refusé | |

## 19 bis. Jalon J10, étape G — Racines, modes `suppression` / `count` / `size`, filtres (2026-11-11)

### Automatiques

| N° | Fichier | Vérifie | État | Date |
|---|---|---|---|---|
| J10G-A01 | `tests/test_modes_et_racines.py` | **Racines** : chemin partiel sous la racine (avec ou sans `\` final), chemin complet conservé, racines de sources / cibles, E07 (racine relative, chemin partiel sans racine), R14 | OK | 2026-11-11 |
| J10G-A02 | `tests/test_modes_et_racines.py` | **Suppression** : âge minimum, avertissement R15, pas de cible, R16 si cible renseignée | OK | 2026-11-11 |
| J10G-A03 | `tests/test_modes_et_racines.py` | **count / size** : nombre et volume, seuils, ATTENTE persisté, bilan `SUCCES` code 0, dépendance `succes` qui patiente puis part | OK | 2026-11-11 |
| J10G-A04 | `Gui/Tests/Racines.Tests.ps1` | `Resolve-CopieChemin`, chemins complets d'un environnement et d'une règle, saisie avec racine, en-tête, création des dossiers sous la racine | OK | 2026-11-11 |
| J10G-A05 | `Gui/Tests/Racines.Tests.ps1` | Ligne de la grille (chemins selon le mode, aspect inactive / erreur), détail, couleur `ATTENTE`, modes, simulation suppression et mesure | OK | 2026-11-11 |
| J10G-A06 | `tests/test_horodatage.py` | **Horodater** : forme et reconnaissance du nom marqué, copie (original marqué, pas de recopie, nouvelle version, date ordinaire dans le nom, simulation, original modifié, échec puis reprise), archivage (nom archivé, avec `renommage_archive`, archive dans la source), R16, E06, modèle du front-end | OK | 2026-11-11 |
| J10G-A07 | `Gui/Tests/Formulaire.Tests.ps1`, `Racines.Tests.ps1` | Case « Horodater » : proposée pour copie et archivage seulement, décochée et grisée sinon, écrite dans la règle | OK | 2026-11-11 |
| J10G-A08 | `tests/test_parametrage.py` | **Code d'environnement** : déduit du nom (`production` → `prod`…), explicite prioritaire, `null` = à déduire, **E08** (hors liste, nom non déductible sans code) | OK | 2026-11-12 |
| J10G-A09 | `Gui/Tests/Environnements.Tests.ps1` | Champ « Code plateforme » : déduction comme le moteur, contrôle de la saisie, écriture dans l'en-tête et relecture, présence dans le formulaire, **renommage vers un nom non déductible : le code de l'ancien nom est conservé** | OK | 2026-11-12 |
| J10G-A10 | `Gui/Tests/Garde.Tests.ps1` | **Journal de l'interface** au format de la plateforme : `timestamp`, `level` (`ERREUR` → `ERROR`), `service`, `context.object` = `interface`, `error` pour ERROR, une session = une trace, code d'environnement hors liste → `prod` | OK | 2026-11-12 |
| J10G-A11 | `tests/test_synchro.py` | **Mode synchro**, paramétrage : minimal valide, dossiers refusés (R17), heures refusées (P01), planification obligatoire, apres_fichier / apres_lot (R18), variables de fichier refusées (G01), champs de fichiers ignorés (R16) seulement hors valeurs par défaut, `apres` obligatoire (D06) | OK | 2026-11-12 |
| J10G-A12 | `tests/test_synchro.py` | **Mode synchro**, exécution : sans programme = succès sans rien toucher, avant_lot seul, avant_fichier seul, **les deux dans l'ordre**, environnement du programme sans dossier, **code 1 = erreur**, échec d'avant_lot n'appelle pas avant_fichier, durée dépassée / lancement impossible, `apres_*` jamais appelés, `sur_erreur` appelé, simulation, règle dépendante prête ou non | OK | 2026-11-12 |
| J10G-A13 | `Gui/Tests/Formulaire.Tests.ps1`, `Racines.Tests.ps1` | Formulaire en mode synchro (dossiers et seuils grisés et vidés, planification imposée, aucune erreur de saisie, retour aux autres modes), grille « (aucun dossier) », sept modes | OK | 2026-11-12 |
| J10G-A14 | `tests/test_declencheur_limites_suspension.py` | **Plafond de volume** : lot arrêté avant la limite puis suite au lancement suivant, premier fichier toujours pris (signalé), combinaison avec `limite_fichiers`, mode suppression, lecture du paramétrage | OK | 2026-11-12 |
| J10G-A15 | `tests/test_declencheur_limites_suspension.py` | **Fichier déclencheur** : sans témoin = ATTENTE sans rien livrer, avec témoin = fichiers livrés et témoin supprimé (jamais livré), masque et casse, `consommer_declencheur` faux, lot tronqué ou en erreur = témoin conservé, sous-dossier ignoré, simulation, modes `count` / `suppression`, dépendante qui patiente, refus d'un chemin, ignoré avec `synchro` | OK | 2026-11-12 |
| J10G-A16 | `tests/test_declencheur_limites_suspension.py`, `test_contrat.py` | **Suspension** : rien lancé et code 0, reprise, lancement manuel bloqué, simulation possible, `--etat` (`suspendu`, `motif_suspension`), information S01 ; contrat JSON mis à jour | OK | 2026-11-12 |
| J10G-A18 | `tests/test_declencheur_limites_suspension.py` | **Témoin de la cible** : déposé après le lot (vide, sans temporaire), pas de témoin sans fichier livré ni après une erreur, retiré puis redéposé au lot suivant, lot tronqué = témoin, échec d'écriture = ERREUR sans temporaire orphelin, mode `deplacement`, simulation, avec le déclencheur de la source, R06, R16, ignoré avec `synchro` | OK | 2026-11-12 |
| J10G-A17 | `Gui/Tests/Environnements.Tests.ps1`, `Racines.Tests.ps1` | Suspension écrite dans l'en-tête seulement si cochée et relue ; formulaire : fichier déclencheur, consommation, volume maximum ; dialogue d'environnement chargé | OK | 2026-11-12 |

Suite complète : 795 tests Python OK ; Pester 217 réussis, 0 échec, 4 ignorés (droits administrateur, voir le CHANGELOG).

### Manuels

| N° | Essai | Marche à suivre | Attendu | État |
|---|---|---|---|---|
| J10G-M01 | Racine à la création d'un environnement | Renseigner la racine, la base `BDD\x.db`, les journaux `LOGS`, le travail `D:\TMP` | L'aperçu montre `<racine>\BDD\x.db`, `<racine>\LOGS`, `D:\TMP` ; une seule question pour créer les dossiers manquants | |
| J10G-M02 | Copie d'un environnement | Copier un environnement en changeant seulement la racine | Les chemins partiels des règles suivent la nouvelle racine | |
| J10G-M03 | Couleurs et filtres | Rendre une règle inactive, en provoquer une en erreur, filtrer sur `ERREUR`, `count`, « Inactives » | Ligne grise / rouge / bleu ciel ; filtres corrects | |
| J10G-M04 | Déclencheur `count` | Règle `count` (minimum 5) sur un dossier de 4 fichiers, règle de déplacement dépendante (`succes`) ; ajouter le 5e fichier | `ATTENTE` puis succès ; le déplacement patiente puis part | |
| J10G-M07 | Mode synchro | Règle `synchro` après une règle `count`, avec un programme `avant_lot` puis un `avant_fichier` qui écrivent chacun une ligne dans un fichier ; lancer ; essayer ensuite un `apres_lot` | Les deux lignes dans l'ordre ; statut `SUCCES` ; l'enregistrement avertit pour `apres_lot` qui n'est jamais exécuté ; un programme qui sort avec le code 1 donne `ERREUR` | |
| J10G-M06 | Horodater (copie) | Cocher « Horodater les fichiers traités » sur une règle `copie`, déposer `a.csv`, lancer deux fois | La cible contient `a.csv` ; la source contient `a_traite_AAAAMMJJ_hhmmss.csv` ; le 2e lancement ne copie rien | |
| J10G-M07 | Horodater (archivage) et case grisée | Même essai en mode `archivage` ; puis passer le mode à `deplacement` dans le formulaire | L'archive contient le nom marqué ; la case se grise et se décoche | |
| J10G-M08 | Code plateforme à la création d'un environnement | Créer « essai » sans code, puis avec le code `test` ; renommer « production » en « prod2 » | Sans code : message demandant le code ; avec : fichier écrit avec `code_environnement` ; renommage : le code `prod` est conservé dans l'en-tête | |
| J10G-M05 | Suppression | Règle `suppression` d'âge minimum sur un dossier d'essai ; simulation puis exécution | Avertissement à l'enregistrement ; simulation annonce la suppression définitive ; seuls les fichiers assez anciens sont supprimés | |
| J10G-M09 | Fichier déclencheur | Règle `copie` avec `fichier_declencheur` = `*.ok` ; déposer `a.csv` sans témoin, lancer ; déposer `fin.ok`, lancer | 1er lancement : `ATTENTE` (« en attente du fichier déclencheur »), rien livré ; 2e : `a.csv` livré, `fin.ok` ni livré ni resté dans la source | |
| J10G-M14 | Témoin dans la cible | Règle `copie` avec `temoin_cible` = `fin.ok` ; lancer avec 2 fichiers ; relancer sans nouveau fichier ; supprimer `fin.ok`, redéposer un fichier, lancer ; laisser `fin.ok` en place, redéposer un fichier, lancer | `fin.ok` après les fichiers ; rien de plus au 2e lancement ; réapparaît avec le nouveau lot ; si laissé en place, retiré avant la livraison puis redéposé (événements `temoin_cible_retire` puis `temoin_cible_depose`) | |
| J10G-M10 | Plafond de volume | Règle avec `limite_octets` = 1 Mo sur 5 fichiers de 400 Ko ; lancer trois fois | 2 fichiers, puis 2, puis 1 ; événement `limite_octets_atteinte` ; un fichier de 3 Mo est pris seul (`limite_octets_depassee`) | |
| J10G-M11 | Suspension d'environnement | Cocher « Suspendre l'environnement » avec un motif, enregistrer, lancer depuis Jenkins ; décocher, relancer | Bandeau « ENVIRONNEMENT SUSPENDU » ; 1er lancement : événement `environnement_suspendu`, aucune règle lancée, build vert ; après reprise : les règles repartent | |
| J10G-M12 | Règle longue relancée par Jenkins | Règle dont un programme `avant_lot` dort 10 min ; relancer Jenkins après 5 min | Le second lancement ignore la règle (déjà en cours), les autres règles tournent ; aucun fichier `.lock` dans la source ; une fois la première exécution finie, le lancement suivant la reprend | |
| J10G-M13 | Alerte « sans succès » (Loki) | Avec l'équipe de la plateforme : charger `exemples\loki\regles_alerte.yaml`, adapter fenêtre et libellés, laisser une règle sans succès | L'alerte `FileManagementRegleSansSucces` part pour la bonne règle (**non testé** : à valider avec la plateforme) | |

## 19 ter. Boîte à outils `outils/` (2026-11-13)

Outils unitaires appelés par les règles (documentation : [13-boite-a-outils.md](13-boite-a-outils.md)).

### Automatiques

| N° | Fichier | Vérifie | État | Date |
|---|---|---|---|---|
| BO-A01 | `tests/test_outils_commun.py` | **Socle** : journal (champs, trace, simulation, pas de mot de passe), codes retour, arguments communs, désignation des fichiers (`COPIE_FICHIER`, `COPIE_LISTE`, `COPIE_SOURCE`), écritures atomiques, refus d'écraser, secrets | OK | 2026-11-13 |
| BO-A02 | `tests/test_outils_compression.py` | **Compression** : zip (anti zip-slip, bombes, plafond), tar.gz, 7z / rar / iso avec faux programmes (listage avant extraction, plafond de taille, mot de passe jamais journalisé), découpage / réassemblage, zip AES (faux pyzipper et repli 7z), simulation sans écriture | OK | 2026-11-13 |
| BO-A03 | `tests/test_outils_recherche.py` | **Recherche** : par nom (jokers, regex, filtres de taille et d'âge, fichier désigné), contenu avec encodage, remplacement en masse (sauvegarde, atomique), détection des doublons | OK | 2026-11-13 |
| BO-A04 | `tests/test_outils_organisation.py` | **Organisation** : renommage en masse (modèles, collisions, simulation), normalisation des noms, rangement par type / extension / date, suppression ou quarantaine des doublons | OK | 2026-11-13 |
| BO-A05 | `tests/test_outils_conversion.py` | **Conversion** : encodage, CRLF / LF, docx → pdf (faux soffice), xlsx → csv, images (Pillow réel) | OK | 2026-11-13 |
| BO-A06 | `tests/test_outils_dates_attributs.py` | **Dates, attributs, droits** : `touch` (dates, décalage, modèle), attributs Windows, ACL (`icacls` réel ; 3 tests ignorés selon le poste) | OK | 2026-11-13 |
| BO-A07 | `tests/test_outils_fichiers.py` | **Manipulation de fichiers** : découpage de texte, fusion CSV, différences, miroir `synchroniser` (simulation, suppression), copie vérifiée, inventaire, dossiers vides, rien d'écrasé sans `--ecraser` | OK | 2026-11-13 |
| BO-A08 | `tests/test_outils_controle.py` | **Contrôle** : attente de stabilité, validation (taille, encodage, format), empreintes SHA-256, espace disque | OK | 2026-11-13 |
| BO-A09 | `tests/test_outils_notification.py` | **Notifications** : courriel SMTP (serveur de test local : TLS refusé, authentification, pièce jointe, délai dépassé), webhook (URL à identifiants refusée, code HTTP, délai) | OK | 2026-11-13 |
| BO-A09b | `tests/test_outils_transfert.py` | **Transfert SFTP** (`sftp_envoyer`, `sftp_recuperer`), contre un serveur paramiko local en thread (`tests/serveur_sftp.py`) : dépôt sans fichier visible incomplet, dossier distant absent, récursif et masques, variables du moteur, **jamais d'écrasement** (fichier et archive), `--ecraser`, `--ignorer-existants`, simulation, SHA-256, archivage / suppression après envoi (rien si échec), **reprise après coupure** (même exécution, exécution suivante, temporaire qui n'est pas le début du fichier, lecture), serveur injoignable, **clé d'hôte** (inconnue refusée, acceptée avec avertissement, empreinte fausse, known_hosts bon / autre clé, exclusivités), **authentification refusée jamais rejouée**, **aucun secret dans le journal ni les sorties**, mot de passe par fichier, clé privée avec phrase secrète, paramiko absent = code 4, `--age-minimum`, noms temporaires ignorés, archivage distant sans écrasement | OK | 2026-11-13 |
| BO-A10 | `tests/test_outils_moteur.py` | **Outils appelés par de vraies règles** aux cinq points d'appel : variables transmises, une ligne de journal par outil dans le fichier de la règle (même trace), simulation, code 1 accepté, lanceur autonome | OK | 2026-11-13 |
| BO-A11 | `tests/test_programmes.py` | **Variables pour les outils** : `COPIE_DOSSIER_LOGS`, `COPIE_CODE_ENVIRONNEMENT`, `COPIE_DOSSIER_TRAVAIL` transmises aux programmes | OK | 2026-11-13 |
| BO-A12b | `tests/test_outils_variables.py`, `Gui/Tests/Outils.Tests.ps1` | **Modules de bibliothèque** : `# bibliotheque:` rangé à part (ni outil ni non retenu, hors index), déclaration vide / double / mêlée à `# outil:` refusée avec sa cause, déclaration après le code ignorée, chaque module de `outils/commun` déclaré ; fenêtre de résultat et journal de l'interface | OK | 2026-11-13 |
| BO-A12c | `tests/test_outils_variables.py`, `Gui/Tests/Edition.Tests.ps1`, `Gui/Tests/Jea.Tests.ps1` | **Brouillon verifie avec `--dossier-parametrage`** : un brouillon range dans un sous-dossier est refuse (G01 « aucun index ») sans l'option, accepte avec ; l'option est refusee sans `--verifier` ; enregistrement d'une regle qui appelle `{outil:nom}` par l'interface (moteur reel) ; JEA accepte l'option dans le dossier de parametrage et la refuse ailleurs | OK | 2026-11-14 |
| BO-A12 | `tests/test_outils_variables.py` | **Variable `{outil:nom}`** : lecture de l'en-tête (valide, sans en-tête, invalide avec la cause), scan (sous-dossiers, variable déjà prise, liens, `_` et `.`, fichier illisible, dossier vide ou introuvable), index `outils.json` (écriture, relecture, BOM, cache, version inconnue), exécution (outil du dépôt, dossier **déplacé et renommé**, changement de dossier puis nouveau scan, outil inconnu, fichier disparu, aucun index, tous les points d'appel), contrôles G01 (syntaxe, index, outil inconnu avec la liste, paramètre obligatoire absent, fichier présent seulement hors `--syntaxe-seule`), commande `--scanner-outils`, **garde-fou** : l'en-tête des 38 outils du dépôt = leur analyseur d'arguments | OK | 2026-11-13 |
| BO-A13 | `Gui/Tests/Outils.Tests.ps1` | **Onglet Outils** : lecture de l'index (absent, illisible, version inconnue), exemple de commande, lignes de la fenêtre de résultat (outil retenu, non retenu avec cause, aucun outil), scan réel avec le moteur Python, écriture atomique d'`outils.json`, rien d'écrit si aucun outil, journal de l'interface | OK | 2026-11-13 |
| BO-A14 | `Gui/Tests/Jea.Tests.ps1`, `Moteur.Tests.ps1` | **JEA** : `--scanner-outils` (écriture, `--dossier-outils` libre, `--utilisateur` automatique, refusé pour une autre commande) ; la fenêtre a un onglet de plus (Outils) | OK | 2026-11-13 |

Suite complète Python (2026-11-13) : 1182 tests OK, 3 ignorés (selon le poste), dont 48 nouveaux pour la variable `{outil:nom}` ; Pester : 238 réussis, 0 échec, 4 ignorés, PSScriptAnalyzer sans avertissement (dont 20 tests pour l'onglet Outils).

### Manuels

| N° | Essai | Marche à suivre | Attendu | État |
|---|---|---|---|---|
| BO-M01 | Compression 7z / rar / iso | Installer 7-Zip (et WinRAR si besoin) ; créer puis extraire une archive 7z, une rar et une iso ; relancer avec `--taille-max` trop petit | Archive créée, contenu identique ; extraction refusée (code 2, `RESOURCE_EXHAUSTED`) avant d'écrire quoi que ce soit | |
| BO-M02 | Zip AES | Installer pyzipper puis créer un zip avec `--mot-de-passe-env` ; recommencer sans pyzipper | Avec pyzipper : aucun avertissement ; sans : avertissement « mot de passe sur la ligne de commande » ; dans les deux cas le mot de passe est absent du journal | |
| BO-M03 | docx → pdf | Installer LibreOffice ; convertir un `.docx` avec `conversion\document_vers_pdf.py` | PDF créé, original intact ; sans soffice : code 4 sans trace d'exception | |
| BO-M04 | Courriel et webhook | Envoyer un courriel de test à la messagerie de recette, puis appeler un webhook de test | Message reçu / réponse 2xx ; une panne réseau donne un code 2 et un type d'erreur de la plateforme | |
| BO-M05 | Droits sur le serveur | Lire puis modifier les droits d'un dossier d'essai avec les outils d'ACL, en simulation puis pour de vrai | Simulation : rien ne change ; réel : droits modifiés comme annoncé | |
| BO-M07 | Onglet Outils dans une vraie fenêtre | Ouvrir l'interface, onglet « Outils » : laisser le dossier vide, « Enregistrer et scanner » ; filtrer ; choisir un outil | Fenêtre de résultat (38 outils retenus ; 17 scripts non retenus « pas d'en-tête » : les 5 scripts existants de `outils\` et les 12 modules de `commun\`) ; `outils.json` créé dans le dossier de paramétrage ; liste, détail, paramètres et exemple de commande lisibles ; un compte non administrateur voit la liste sans bouton | |
| BO-M08 | Dossier des outils déplacé | Copier `outils\` (avec `_amorce`) dans `D:\Outils-test\scripts`, saisir ce dossier, scanner ; lancer une règle dont `avant_lot` est `["{outil:espace_disque}", …]` | Index à jour (`dossier_resolu` = le nouveau dossier) ; l'outil tourne depuis le nouvel emplacement et écrit dans le journal de la règle | |
| BO-M09 | Outil sans en-tête, en-tête invalide, doublon | Ajouter dans le dossier un script sans en-tête, un avec `# parametre:` mal formé, un deuxième `# outil: touch` ; scanner | Fenêtre : le premier en information, les deux autres en avertissement avec la cause ; la variable `touch` reste au premier fichier ; les mêmes lignes dans le journal de l'interface | |
| BO-M10 | Variable d'outil inconnue | Dans une règle, mettre `["{outil:inexistant}"]` en `avant_lot` ; `--verifier --syntaxe-seule` puis formulaire de règle | G01 « outil inconnu : {outil:inexistant} (outils indexes : …) » ; la règle n'est pas enregistrable | |
| BO-M11 | Scan par le point d'accès JEA | Mode distant avec JEA : scanner depuis l'onglet | Scan accepté (commande `--scanner-outils`), index écrit par l'interface ; une autre commande hors grammaire reste refusée | |
| BO-M06 | Règle réelle avec outils | Dans une règle de recette, appeler `empreinte --generer` en `apres_fichier` et `archive_creer` en `apres_lot` ; ouvrir le journal de la règle | Les lignes des outils sont dans le même fichier que celles de la règle, avec la même trace, le même `execution_id`, `outil` et `point_appel` | |

## 19 quater. Confort de l'interface : ordre de l'historique, journaux d'une règle (2026-11-14)

### Automatiques

| N° | Fichier | Vérifie | État | Date |
|---|---|---|---|---|
| J10H-A01 | `Gui/Tests/Analyse.Tests.ps1` | **Historique** : cinq versions écrites dans le désordre, rendues du plus récent au plus ancien ; dates décroissantes ; une fiche à la date fausse (une heure de trop) signalée et affichée avec la date du nom ; chaînage « état d'après » intact | OK | 2026-11-14 |
| J10H-A02 | `tests/test_journaux.py` | **Moteur, `--journaux-regle`** : liste du plus récent au plus ancien (autre règle, `_orchestrateur` et `export_autre_…` écartés), contenu décomposé, exécutions et simulations regroupées, ancien format à plat, ligne illisible comptée, limite et budget de taille (derniers événements gardés), refus d'un chemin / d'un journal d'une autre règle / d'une option mal associée, journaux réellement écrits par `--lancer-regle` | OK | 2026-11-14 |
| J10H-A03 | `Gui/Tests/Jea.Tests.ps1` | **JEA** : `--journaux-regle` en lecture, `--journal` limité à `<règle>_<AAAA-MM-JJ>.jsonl` (chemin, mauvaise extension, injection refusés), `--limite-evenements` entier | OK | 2026-11-14 |
| J10H-A04 | `Gui/Tests/Journaux.Tests.ps1` | **Fenêtre des journaux** : liste (gravité, anomalies), événements (niveau en français, exécutions, simulations), filtres, choix des exécutions, détail décomposé (compteurs développés, tailles, erreur, valeurs vides), résumé ; fenêtre réelle (STA) : dernière exécution ouverte d'office, première anomalie sélectionnée, filtre | OK | 2026-11-14 |

### Manuels

| N° | Ce qu'on essaie | Comment | Résultat attendu |
|---|---|---|---|
| J10H-M01 | Ordre de l'historique | « Historique… » sur un environnement modifié plusieurs fois | La modification la plus récente est en haut, les dates descendent ; un clic sur « Date » inverse l'ordre |
| J10H-M02 | Journaux d'une règle en erreur | Provoquer une erreur (source verrouillée ou absente), puis « Journaux… » sur la règle | Le journal du jour est en haut, ligne rouge ; la dernière exécution est choisie ; la première erreur est sélectionnée et son détail (type d'erreur, fichier) est lisible |
| J10H-M03 | Journaux d'une règle sans erreur | « Journaux… » sur une règle qui réussit | Une ligne par jour, « aucune » anomalie ; événements « fichier livré… » ; compteurs en clair en fin d'exécution |
| J10H-M04 | Règle sans journal | « Journaux… » sur une règle jamais lancée | Message « Aucun journal pour la règle … dans … » |
| J10H-M05 | Mode distant / JEA | Mêmes essais depuis un poste administrateur et un poste lecteur | Mêmes écrans ; aucun accès au dossier des journaux nécessaire côté poste |

## 20. Jalons suivants

Les sections suivantes seront ajoutées au fur et à mesure du développement, avec la même structure (tests automatiques, tests manuels sur le serveur) :

| Jalon | Contenu prévu du cahier |
|---|---|
