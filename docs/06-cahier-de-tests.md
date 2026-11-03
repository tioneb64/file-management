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

## 4. Jalon J2 — Base de données

Testé le 2026-11-03 sur Windows 10, Python 3.14.10, SQLite 3.50.4 : 151 tests au total (91 précédents + 60 de J2), tous OK en 45 s environ (la durée dépend surtout du coût d'un fsync sur le disque).

Commandes (provisoires) :

```powershell
C:\Python314\python.exe -m copie --config exemples\production.jsonl --initialiser-base
C:\Python314\python.exe -m copie --config exemples\production.jsonl --sauvegarder-base D:\Copie\sauvegardes
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
| J2-M06 | Restauration | Arrêter les traitements, copier la sauvegarde à la place de la base, relancer la suite de tests J2 sur ce fichier ou ouvrir avec `python -c "from copie import base; b=base.ouvrir(r'D:\\...\\production.db'); print(b.meta('environnement'), b.verifier_integrite())"` | Environnement affiché, liste d'anomalies vide `[]` | |
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
| J3-A01 | Format : champs de base dans l'ordre, horodatage UTC au millième (`2026-11-03T06:30:12.481Z`), variables Jenkins ajoutées si présentes et absentes sinon, UTF-8 sans échappement des accents, retours à la ligne dans un message, champs réservés non écrasables (`x_…`), valeurs non sérialisables, nom Windows avec caractère isolé, texte trop long coupé | OK | |
| J3-A02 | Niveaux (inconnu → INFO), `DEBUG` seulement en mode verbeux, contexte défini une fois (`definir`), contexte passé à `debut` | OK | |
| J3-A03 | Fichiers : un par règle et par jour, fichier `_orchestrateur_` sans règle, changement de jour, nom de règle assaini (jamais hors du dossier), dossier créé, dossier par défaut par variable d'environnement | OK | |
| J3-A04 | `fin` : bilan, durée, niveau selon le statut, fichiers fermés puis rouverts ; lecture du fichier pendant qu'il est ouvert (comme Alloy) ; suppression d'un autre fichier pendant l'exécution | OK | |
| J3-A05 | **Pannes (G7)** : dossier impossible, secours impossible, `stderr` fermé, sérialisation qui échoue → jamais d'exception, ligne retrouvée sur `stderr` et dans le fichier de secours, `pannes()` correct, reprise automatique quand le dossier revient | OK | |
| J3-A06 | Console : une ligne lisible par événement avec `console=True`, silence sinon | OK | |
| J3-A07 | Interface de module (`debut`, `evenement`, `fin`, `definir`, `pannes`) | OK | |
| J3-A08 | **Charge** : 8 processus × 1 000 lignes dans le même fichier, puis 6 × 300 lignes de 3,5 Ko : aucune ligne corrompue, perdue ou mélangée, séquence de chaque processus complète et dans l'ordre | OK | |
| J3-A09 | **Critère de sortie** `outils\charge_journal.py` : 8 processus × 10 000 lignes → 80 000 lignes valides, 0 corrompue, 21 Mo, 10 s (7 800 lignes/s) | OK | |

### 5.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J3-M01 | **Charge sur le disque réel des journaux** | `outils\charge_journal.py --dossier <dossier de journaux réel>` avec le compte de service, puis avec `--taille 3500 --lignes 2000` | `RESULTAT : OK`, 0 ligne corrompue. Noter la durée et les lignes/s. Si l'antivirus ralentit fortement (< 1 000 lignes/s), le signaler | |
| J3-M02 | Écriture atomique réellement vérifiée sur Windows Server 2016 | Même test ; en cas d'échec : joindre la sortie | Aucune corruption. (Sur le PC, `O_APPEND` seul corrompt les lignes ; le module utilise `FILE_APPEND_DATA`.) | |
| J3-M03 | Dossier de journaux sur un **partage réseau** (information) | Même test avec `--dossier \\SERVEUR\partage\tmp` | Noter le résultat. Si des lignes sont corrompues, le dossier de journaux doit rester **local** (Alloy lit sur le serveur) | |
| J3-M04 | Panne de journalisation | Retirer le droit d'écriture du compte sur le dossier de journaux puis lancer un petit programme utilisant le module (`python -c "import journal_si as j; j.debut('t','recette',dossier=r'D:\\Copie\\logs'); j.evenement('essai'); print(j.pannes())"`) | Aucune exception, message sur la console, ligne dans `journal_si_secours_<jour>.jsonl` du dossier temporaire du compte, `pannes()` affiche `2` | |
| J3-M05 | Lecture par **Grafana Alloy** | Avec l'équipe de surveillance : déposer `exemples\journal\*.jsonl` dans le dossier lu, adapter `exemples\alloy\copie_fichiers.alloy` | Les événements apparaissent dans Loki avec les libellés `application`, `environnement`, `regle`, `niveau` et l'heure de la ligne ; les champs sont consultables (`| json`) ; **validation formelle du format par l'équipe** | |
| J3-M06 | Accents et caractères spéciaux dans la console Jenkins | Job Jenkins exécutant un script qui appelle `debut(..., console=True)` avec `message="é à ü"` | Les accents s'affichent correctement dans la console et sont intacts dans le fichier | |
| J3-M07 | Changement de jour | Laisser un programme tourner autour de minuit (ou changer l'heure de la VM de recette) | Deux fichiers `<regle>_<jour>.jsonl`, aucune ligne perdue | |

## 6. Jalons suivants

Les sections suivantes seront ajoutées au fur et à mesure du développement, avec la même structure (tests automatiques, tests manuels sur le serveur) :

| Jalon | Contenu prévu du cahier |
|---|---|
| J4 Transfert | Pannes injectées, fichiers verrouillés par un vrai logiciel, droits NTFS, quotas, partages réels |
| J5 Planification | Horloge simulée, changement d'heure, reprise et acquittement |
| J6 à J12 | Arrêt d'arbre de processus, dépendances, Jenkins, front-end, migration, recette |
