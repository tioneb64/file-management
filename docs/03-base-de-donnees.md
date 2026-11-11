# Base de données

Une base SQLite **par environnement**, sur un **disque local** du serveur d'exécution. Son chemin est donné par le champ `base` de l'en-tête du paramétrage.

## 1. Rôle

| Besoin | Table |
|---|---|
| Savoir si une règle est en cours, quand elle a tourné, son dernier statut, ses flags de reprise | `regles` |
| Historique des exécutions (début, fin, statut, compteurs) | `executions` |
| Ne jamais livrer deux fois la même version d'un fichier | `fichiers` |
| Mémoriser les actions à terminer ou à vérifier (archivage différé, suppression différée, livraison interrompue) | `actions_en_attente` |
| Tracer les actions d'exploitation | `journal_actions` |
| Version du schéma | `meta`, `PRAGMA user_version` |

L'historique détaillé fichier par fichier est dans les **journaux** (Grafana), pas dans la base : la table `fichiers` ne contient que des empreintes.

## 2. Réglages

| Réglage | Valeur | Raison |
|---|---|---|
| `journal_mode` | `WAL` | Lecteurs et écrivains simultanés ; plusieurs processus par environnement |
| `synchronous` | `FULL` | Le journal d'intention doit survivre à une coupure de courant |
| `busy_timeout` | 30 000 ms | Attente si un autre processus écrit |
| `foreign_keys` | `ON` | |
| Disque | **Local** | SQLite en WAL n'est pas fiable sur un partage réseau. Le moteur refuse un chemin `\\serveur\partage\...` **et** un lecteur réseau mappé (`GetDriveTypeW`), à la création comme à l'ouverture |

Une connexion par processus. Transactions courtes. Les écritures utilisent `BEGIN IMMEDIATE`. Si la base reste verrouillée au-delà d'un nombre borné de tentatives : événement `base_indisponible` et arrêt de l'exécution.

## 3. Schéma (version 1)

```sql
PRAGMA user_version = 1;

CREATE TABLE meta (
  cle    TEXT PRIMARY KEY,
  valeur TEXT NOT NULL
);   -- environnement, cree_le, version_moteur

CREATE TABLE regles (
  no                       INTEGER PRIMARY KEY AUTOINCREMENT,
  id                       TEXT NOT NULL UNIQUE COLLATE NOCASE,
  cree_le                  INTEGER NOT NULL,
  empreinte_parametres     TEXT,                              -- détecte une règle modifiée
  -- exécution en cours
  en_cours                 INTEGER NOT NULL DEFAULT 0,
  execution_id             INTEGER,
  pid                      INTEGER,
  pid_cree_le              INTEGER,                           -- date de création du processus
  hote                     TEXT,
  build                    TEXT,
  debut_traitement         INTEGER,
  -- planification
  dernier_lancement        INTEGER,
  dernier_creneau          INTEGER,
  dernier_fin              INTEGER,
  -- résultat
  dernier_statut           TEXT NOT NULL DEFAULT 'JAMAIS_LANCEE',
  dernier_statut_le        INTEGER,
  dernier_motif            TEXT,
  dernier_succes           INTEGER,
  derniere_erreur_le       INTEGER,
  derniere_erreur_situation TEXT,
  derniere_erreur_message  TEXT,
  -- attente de dépendances
  attente                  TEXT,                              -- NULL | EN_ATTENTE | BLOQUEE
  attente_motif            TEXT,
  attente_depuis           INTEGER,
  -- reprise et arrêt
  reprise                  INTEGER NOT NULL DEFAULT 0,
  reprise_par              TEXT,
  reprise_le               INTEGER,
  lancement_manuel         INTEGER NOT NULL DEFAULT 0,
  arret_apres_erreur       INTEGER NOT NULL DEFAULT 0,
  relances                 INTEGER NOT NULL DEFAULT 0,
  archivage_degrade        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE executions (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  regle_no         INTEGER NOT NULL REFERENCES regles(no),
  declencheur      TEXT NOT NULL,        -- planifie | dependance | reprise | manuel
  debut            INTEGER NOT NULL,
  fin              INTEGER,
  statut           TEXT,                 -- SUCCES | WARNING | ERREUR | ARRETEE
  situation_finale TEXT,
  nb_selectionnes  INTEGER NOT NULL DEFAULT 0,
  nb_livres        INTEGER NOT NULL DEFAULT 0,
  nb_ignores       INTEGER NOT NULL DEFAULT 0,
  nb_erreurs       INTEGER NOT NULL DEFAULT 0,
  nb_en_attente    INTEGER NOT NULL DEFAULT 0,
  octets_livres    INTEGER NOT NULL DEFAULT 0,
  hote             TEXT,
  pid              INTEGER,
  build            TEXT,
  simulation       INTEGER NOT NULL DEFAULT 0,
  message          TEXT
);
CREATE INDEX ix_executions_regle ON executions (regle_no, id DESC);

CREATE TABLE fichiers (
  cle       BLOB PRIMARY KEY,            -- empreinte de 16 octets, voir §4
  regle_no  INTEGER NOT NULL,
  etat      INTEGER NOT NULL,            -- 1 INTENTION, 2 LIVRE, 3 TERMINE, 9 INCERTAIN
  vu_jour   INTEGER NOT NULL,            -- dernier jour où le fichier a été vu (jours depuis 1970)
  livre_le  INTEGER
) WITHOUT ROWID;

CREATE TABLE actions_en_attente (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  regle_no         INTEGER NOT NULL REFERENCES regles(no),
  cle              BLOB NOT NULL UNIQUE,
  type             TEXT NOT NULL,        -- livraison | suppression | archivage
  chemin_source    TEXT NOT NULL,
  chemin_cible     TEXT,
  chemin_archive   TEXT,
  taille           INTEGER,
  mtime_ns         INTEGER,
  sha256           TEXT,
  cree_le          INTEGER NOT NULL,
  tentatives       INTEGER NOT NULL DEFAULT 0,
  derniere_tentative INTEGER,
  dernier_message  TEXT
);
CREATE INDEX ix_actions_regle ON actions_en_attente (regle_no, id);

CREATE TABLE journal_actions (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  regle_no     INTEGER,
  action       TEXT NOT NULL,            -- reprise | lancer_maintenant | acquittement | deblocage | initialisation | migration
  utilisateur  TEXT NOT NULL,
  commentaire  TEXT,
  demandee_le  INTEGER NOT NULL,
  resultat     TEXT
);
```

Tous les instants sont des **timestamps entiers (secondes, UTC)**, sauf `mtime_ns` (nanosecondes, valeur du système de fichiers).

## 4. Anti-doublon

### 4.1 Empreinte

Pour chaque fichier, la clé est un condensat BLAKE2b de 16 octets (`hashlib.blake2b(digest_size=16)`), calculé sur des champs séparés par le caractère `\x1f` :

| Genre | Champs hachés | Usage |
|---|---|---|
| **Version** (`V`) | `V`, `id` de la règle, chemin relatif en minuscules et normalisé, taille, `mtime_ns` | Défaut (`identite = version`) |
| **Contenu** (`C`) | `C`, `id` de la règle, chemin relatif en minuscules et normalisé, SHA-256 | `identite = contenu` |

Le chemin relatif part de la racine de `source`. La normalisation est NFC pour les caractères accentués, et les séparateurs sont uniformisés (`\`).

Avec `identite = contenu`, la recherche se fait en **deux niveaux** : si la clé de version est connue, le fichier est ignoré sans le relire ; sinon son SHA-256 est calculé et la clé de contenu est cherchée. Un fichier régénéré à l'identique reçoit alors une clé de version (pour ne plus être relu), mais n'est pas relivré.

### 4.2 Mesures

Mesures sur un poste de développement (Python 3.12, SQLite 3.45 ; à refaire en Python 3.14 sur le serveur cible au jalon J2), pour 1 000 fichiers à vérifier par lancement :

| Méthode | 100 000 entrées | 1 000 000 entrées |
|---|---|---|
| `findstr`, un processus par fichier | 34 s | 91 s |
| Recherche dans le fichier texte, sans processus | 0,8 s | 6 s |
| Fichier chargé en mémoire (ensemble) | 0,04 s | 0,54 s |
| **SQLite, clé hachée** | **0,15 s** | **0,13 s** |
| SQLite, trois colonnes (nom, taille, date) | 0,11 s | 0,17 s |

**Mesure du jalon J2** (poste de développement Windows 10, Python 3.14.10, SQLite 3.50.4, `outils/mesure_base.py`) : un million d'entrées dans `fichiers` = fichier de **29,7 Mo** ; 2 000 recherches (1 000 trouvées, 1 000 absentes) en **0,05 s**. À refaire sur le serveur (cahier de tests J2-M01).

Taille de la base pour un million d'entrées : environ 24 Mo avec la seule clé, 50 Mo avec trois colonnes. La clé hachée divise donc la taille par deux. Avec les colonnes supplémentaires de `fichiers` (règle, état, jour, date), compter 35 à 45 Mo par million de fichiers.

### 4.2 bis Coût d'une transaction durable

Avec `synchronous = FULL`, chaque validation attend l'écriture physique sur le disque. Mesuré sur le poste de développement : **environ 36 ms par transaction**, soit **71 ms par livraison** (transactions A et B) et environ 107 ms avec la transaction C. Avec `synchronous = NORMAL` : 0,6 ms. Pour 1 000 fichiers livrés dans un même lancement, la base représente donc 1 à 2 minutes sur ce poste en FULL.

Ce coût dépend du disque (cache d'écriture du contrôleur, SSD) ; il doit être mesuré sur le serveur (J2-M01). Si ce coût était gênant, la seule transaction qui doit absolument être durable est la **A** (intention, avant la copie) : la perte de B ou de C après une coupure de courant donnerait un fichier `INCERTAIN` (sans doublon, avec décision d'exploitation), jamais un fichier relivré. Cette optimisation n'est **pas** faite : elle sera décidée avec les mesures du serveur.

### 4.3 États d'un fichier

| État | Sens | Transition |
|---|---|---|
| `INTENTION` (1) | La copie va démarrer ou est en cours. Écrit **avant** la copie, avec une ligne `actions_en_attente` de type `livraison` | → `LIVRE` si la copie est vérifiée |
| `LIVRE` (2) | Copie vérifiée et renommée. Une action d'archivage ou de suppression reste éventuellement à faire | → `TERMINE` |
| `TERMINE` (3) | Plus rien à faire (mode `copie` : directement après la livraison) | — |
| `INCERTAIN` (9) | Arrêt pendant la livraison, résultat inconnu. **Bloque la règle** (G2) | Décision d'exploitation |

### 4.4 Purge

- À chaque fichier vu dans un parcours, `vu_jour` est mis à jour, **au plus une fois par jour** (`UPDATE … WHERE vu_jour < :aujourd_hui`). Mis à jour à chaque lancement, il coûterait 2 s par lancement pour 1000 fichiers à un million d'entrées.
- Chaque nuit (premier lancement du jour) : suppression des lignes `TERMINE` dont `vu_jour` est plus ancien que `retention_historique_jours` de leur règle.
- Une règle dont la sélection est une fenêtre de N jours exige une rétention supérieure à N (contrôle R08), sinon un fichier encore visible pourrait être relivré après sa purge.
- Les lignes `actions_en_attente`, `INTENTION`, `LIVRE` et `INCERTAIN` ne sont jamais purgées automatiquement.
- `executions` : purge au-delà de `retention_executions_jours`.

## 5. Opérations atomiques

### 5.1 Prise du flag « en cours »

```sql
UPDATE regles
   SET en_cours = 1, execution_id = :exec, pid = :pid, pid_cree_le = :pid_cree_le,
       hote = :hote, build = :build, debut_traitement = :maintenant,
       dernier_lancement = :maintenant
 WHERE no = :no AND en_cours = 0;
```

La requête modifie une ligne : le lancement a pris la règle (`cursor.rowcount == 1`). Zéro ligne : un autre lancement l'a déjà prise, la règle est ignorée. Deux lancements simultanés ne peuvent donc jamais exécuter la même règle.

### 5.2 Libération

À la fin de l'exécution, dans **une seule transaction** : mise à jour de l'exécution, du statut de la règle, `en_cours = 0`. Si le processus meurt avant, le flag reste posé : le nettoyage des orphelins de l'orchestrateur (processus disparu) le libère au lancement suivant.

### 5.3 Journal d'intention

Pour chaque fichier, dans cet ordre :

1. Transaction A : insertion de `fichiers` (`INTENTION`) et de `actions_en_attente` (`livraison`). **Commit.**
2. Copie et vérification.
3. Transaction B : `fichiers.etat = LIVRE` (ou `TERMINE` en mode `copie`) ; suppression de l'action `livraison` ; si le mode l'exige, insertion d'une action `suppression` ou `archivage`. **Commit.**
4. Action sur l'original.
5. Transaction C : `fichiers.etat = TERMINE` ; suppression de l'action.

## 6. Commandes de lecture : `--etat`

Le front-end n'ouvre jamais la base. Il appelle le moteur, qui renvoie du JSON :

```json
{"environnement": "production", "genere_le": 1793609412,
 "regles": [
  {"id": "export_clients", "actif": true, "en_cours": false,
   "statut": "WARNING", "attente": null, "motif": "archivage différé : 12 fichiers",
   "dernier_lancement": 1793609101, "dernier_creneau": 1793609100, "prochain_creneau": 1793609400,
   "dernier_succes": 1793605500,
   "derniere_erreur": {"le": 1793520000, "situation": "fichier_verrouille", "message": "…"},
   "derniere_execution": {"statut": "WARNING", "nb_livres": 4, "nb_erreurs": 0, "duree_sec": 11},
   "reprise": false, "archivage_degrade": true, "actions_en_attente": 12}
 ]}
```

Les timestamps sont en secondes UTC ; le front-end les convertit pour l'affichage.

## 7. Maintenance

| Tâche | Fréquence | Moyen |
|---|---|---|
| **Sauvegarde** | Quotidienne | `--sauvegarder-base DOSSIER` (API de sauvegarde SQLite : copie cohérente même base en cours d'utilisation). Job Jenkins dédié |
| Purge des fichiers et exécutions | Automatique | Premier lancement du jour |
| `wal_checkpoint(TRUNCATE)` | Après la purge | Évite un fichier WAL qui grossit |
| `VACUUM` | Rare, à la demande | Aucun lancement ne doit tourner |
| Montée de schéma | À la mise à jour du moteur | `PRAGMA user_version` + scripts de migration numérotés. Le moteur refuse une base plus récente que lui |

**Perte de la base** : le moteur refuse de démarrer sur une base absente (G6) et il faut une action volontaire (`--initialiser-base`). En mode `copie`, une base neuve ferait relivrer tous les fichiers encore présents dans les sources : c'est la raison de la sauvegarde quotidienne. La restauration se fait par copie de la dernière sauvegarde.

## 8. Initialisation et migration

Réalisé au jalon J2 : `python -m file_management --config FICHIER --initialiser-base [--utilisateur U]` et `--sauvegarder-base DOSSIER`. Le fichier de sauvegarde s'appelle `<environnement>_AAAAMMJJ_HHMMSS.db`, il est vérifié (`integrity_check`) avant d'être mis en place et ne dépend d'aucun fichier `-wal`. La restauration est une copie du fichier à la place de la base, moteur arrêté. Le moteur refuse d'ouvrir la base d'un autre environnement (`meta.environnement`) ou un fichier qui n'est pas une base de ce programme.

- `--initialiser-base` : crée le fichier, le schéma, la ligne `meta` (environnement). Refuse si la base existe déjà.
- **Migration** (jalon J11, deux commandes, voir [09-migration-et-recette](09-migration-et-recette.md)) : `--migrer-ancien copies.conf` convertit chaque ligne de l'ancien paramétrage en règle (`mode = copie`, `si_cible_absente = recopier` et `si_existe_cible = ecraser` pour conserver le comportement actuel, règles inactives) ; `--importer-historique copies.historique.json` importe l'historique : l'ancien historique contient source, cible, taille et `mtime_ns`, donc l'empreinte de version est recalculée (`cle_version(id de la règle, chemin relatif, taille, mtime_ns)`) et chaque fichier déjà copié devient une version `TERMINE` : il n'est pas relivré. Une entrée est rattachée à la règle dont la source, la cible, le nom relatif et le masque correspondent. Idempotent ; chaque import est tracé dans `journal_actions` (action `migration`).
