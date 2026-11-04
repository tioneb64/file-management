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

## 6. Jalon J4 — Transfert d'une règle

Testé le 2026-11-04 sur Windows 10, Python 3.14.10 : 307 tests au total (185 précédents + 122 de J4), tous OK en 3 min 35 s (durée dominée par les fsync).

C'est le jalon le plus sensible : **les tests manuels ci-dessous doivent être joués sur le serveur avec de vrais partages, de vrais droits et si possible le vrai logiciel destinataire**, en commençant par des dossiers de test.

Commandes (provisoires) :

```powershell
# une règle, en simulation puis pour de vrai (la base doit exister : --initialiser-base)
C:\Python314\python.exe -m copie --config D:\Parametrage\recette.jsonl --lancer-regle export_clients --simulation
C:\Python314\python.exe -m copie --config D:\Parametrage\recette.jsonl --lancer-regle export_clients
# débit de transfert
C:\Python314\python.exe outils\mesure_transfert.py --source D:\temp --fichiers 200 --taille-ko 100 [--cible \\SERVEUR\partage\test]
# livraisons de résultat inconnu (après un arrêt brutal) : lister, puis trancher
C:\Python314\python.exe -c "from copie import base; b=base.ouvrir(r'D:\Copie\recette.db'); print([(c.hex(), s, d) for c, s, d in b.incertains(b.numero_regle('export_clients'))])"
C:\Python314\python.exe -c "from copie import base; b=base.ouvrir(r'D:\Copie\recette.db'); b.resoudre_incertain(bytes.fromhex('CLE'), 'a_relivrer', 'benoit', 'absent de la cible')"
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
| J4-A09 | `test_moteur.py` | **Espace disque** : cible insuffisante, juste assez, calcul sur ce qui sera livré, archive sur le même volume (non contrôlée) ou un autre (contrôlée, dégradée si pleine) | OK | |
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

Commandes (provisoires, le lanceur `copie_fichiers.py` reste la v1) :

```powershell
# lancement de l'environnement : exécute les règles dues, l'une après l'autre
C:\Python314\python.exe -m copie --config D:\Parametrage\recette.jsonl
C:\Python314\python.exe -m copie --config D:\Parametrage\recette.jsonl --simulation [--regle export_clients]
# état des règles
C:\Python314\python.exe -m copie --config D:\Parametrage\recette.jsonl --etat [--regle ID] [--format json]
# exploitation (--utilisateur obligatoire)
C:\Python314\python.exe -m copie --config ... --reprise ID --utilisateur DOMAINE\benoit --commentaire "source rétablie"
C:\Python314\python.exe -m copie --config ... --lancer-maintenant ID --utilisateur DOMAINE\benoit
C:\Python314\python.exe -m copie --config ... --acquitter ID --utilisateur DOMAINE\benoit --commentaire "traité à la main"
C:\Python314\python.exe -m copie --config ... --trancher-incertain CLE_HEXA --decision a_relivrer --utilisateur DOMAINE\benoit --commentaire "absent de la cible"
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
| J5-A10 | `test_lancement.py` | **Ligne de commande** de bout en bout : initialisation, lancement, `--lancer-maintenant`, état JSON, reprise, acquittement avec et sans commentaire, `--utilisateur` obligatoire, règle inconnue, décision incertaine, base absente, simulation de lancement | OK | |

### 7.2 Tests manuels sur le serveur

| ID | Objectif | Procédure | Attendu | Serveur |
|---|---|---|---|---|
| J5-M01 | **Règle toutes les 5 minutes avec Jenkins** | Job de recette `python -m copie --config ...` toutes les 5 min, règle `intervalle` 300 s, dépôt d'un fichier toutes les 10 min | Une exécution par créneau, jamais deux ; les fichiers sont livrés au créneau qui suit leur arrivée | |
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
C:\Python314\python.exe -m copie --config D:\Parametrage\recette.jsonl
C:\Python314\python.exe -m copie --config D:\Parametrage\recette.jsonl --etat      # EN_ATTENTE / BLOQUEE y apparaissent
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
C:\Python314\python.exe -m copie --config D:\Parametrage\recette.jsonl --simulation --simulation-programmes --regle export_clients
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
& $py -m copie --config D:\Parametrage\recette.jsonl --verifier --format json | ConvertFrom-Json
# avant d'enregistrer une modification : syntaxe + comparaison avec la version actuelle
& $py -m copie --config D:\Parametrage\nouveau.jsonl --verifier --syntaxe-seule --precedent D:\Parametrage\recette.jsonl --format json
# déblocage d'une règle qui ne répond plus
& $py -m copie --config D:\Parametrage\recette.jsonl --debloquer export_clients --utilisateur DOMAINE\benoit --commentaire "bloquee" --format json
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
| J8-M01 | **Accès avec le compte de service** | `--verifier --format json` sur la vraie configuration de recette, avec le compte de service Jenkins (`runas` ou job) | Aucun refus `A01` à `A05` ; les informations `A07` donnent l'espace réel ; noter tout refus avec son message | |
| J8-M02 | Droits retirés | Retirer au compte de service : lecture de la source / écriture de la cible / écriture de l'archive / base | Respectivement `A01`, `A02`, `A03` (avertissement) et `A05` ; rétablir les droits ensuite | |
| J8-M03 | Quota | Volume de la cible avec un quota pour le compte de service | `A07` indique l'espace du quota, pas l'espace du disque | |
| J8-M04 | Exécutable manquant | Renommer un programme référencé par une règle | `A04` nomme le point d'appel et le chemin | |
| J8-M05 | Aucun effet de bord | Comparer l'arborescence de la cible avant / après `--verifier` | Identique ; aucun dossier créé, aucun `.test_ecriture_*` restant | |
| J8-M06 | **Depuis le poste du front-end** | `Invoke-Command -ComputerName SERVEUR -ScriptBlock { & C:\Python314\python.exe -m copie ... --format json }` puis `ConvertFrom-Json` | Un objet exploitable, accents corrects (avec `[Console]::OutputEncoding` en UTF-8) ; noter si les accents sont faux sans cette ligne | |
| J8-M07 | Comparaison de versions | Modifier une copie du paramétrage : changer un `id`, élargir `modifie_depuis`, changer une cible, supprimer une règle ; `--precedent` | `V01` (refus), `V03`, `V04`, `V02` conformes ; sans modification, aucun diagnostic | |
| J8-M08 | **Déblocage d'une vraie règle bloquée** | Règle qui attend longtemps (programme `sleep`), `--debloquer` depuis un autre compte | Le processus et le programme lancé disparaissent (`tasklist`), la règle est en `ERREUR` ; `--reprise` la relance | |
| J8-M09 | Déblocage depuis un autre serveur | `--debloquer` lancé depuis une machine qui n'est pas celle de l'exécution (base partagée impossible : tester sur la machine d'exécution) | Refus explicite si l'hôte diffère | |
| J8-M10 | Droits d'écriture du paramétrage | Compte non administrateur : tenter de modifier le dossier de paramétrage, puis lancer `--reprise` via le point de terminaison JEA | Écriture refusée par NTFS ; commande refusée par JEA ; `--etat` accessible | |

## 11. Jalons suivants

Les sections suivantes seront ajoutées au fur et à mesure du développement, avec la même structure (tests automatiques, tests manuels sur le serveur) :

| Jalon | Contenu prévu du cahier |
|---|---|
| J6 à J12 | Arrêt d'arbre de processus, dépendances, Jenkins, front-end, migration, recette |
