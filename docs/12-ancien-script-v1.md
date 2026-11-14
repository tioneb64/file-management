> **Ancien script (v1).** Cette documentation décrit `Legacy\file_management_v1.py` (appelé `file_management.py` dans la suite du document ; les commandes se lancent depuis le dossier `Legacy\` ou avec ce chemin) et `Legacy\copies.conf`, encore en service jusqu'à la bascule vers la v2 ([09-migration-et-recette](09-migration-et-recette.md)). La documentation de la v2 est à partir du [README](../README.md).

# file_management.py

Script de copie incrémentale et vérifiée de fichiers, de la production vers les environnements de test. Il est conçu pour être ordonnancé par Jenkins sur Windows Server 2016.

## Fonctionnalités

- **Plusieurs règles** dans un seul fichier de paramétrage, une règle par couple dossier source / dossier cible.
- **Sélection par date** de modification : `J`, `J-1`, `J-N` ou `TOUT`.
- **Filtrage par masque** (`*.csv`, `FACT_*.xml;FACT_*.pdf`…).
- **Copie récursive** optionnelle, avec reproduction de l'arborescence.
- **Pas de recopie** des fichiers déjà copiés, grâce à un historique JSON.
- **Vérification de chaque copie** : taille, checksum SHA-256 et stabilité de la source pendant la copie.
- **Copie atomique** : la cible n'est jamais visible à moitié copiée.
- **Nouveaux essais automatiques** en cas d'échec.
- **Verrou** contre les exécutions simultanées.
- **Mode simulation** pour valider un paramétrage sans rien copier.
- **Codes retour** exploitables par Jenkins.

## Prérequis

- Python 3.6 ou supérieur. Le script n'utilise que la bibliothèque standard.
- Le compte qui exécute le script (le compte de service Jenkins) doit avoir :
  - les droits en **lecture** sur les dossiers sources de production ;
  - les droits en **écriture** sur les dossiers cibles de test ;
  - les droits en **écriture** sur le dossier de l'historique et des logs.

## Utilisation

```bat
python file_management.py --config copies.conf [options]
```

| Option | Défaut | Description |
|---|---|---|
| `-c`, `--config` | *(obligatoire)* | Fichier de paramétrage |
| `--historique` | `<config>.historique.json` | Fichier d'historique des copies |
| `--log` | aucun | Fichier de log, en plus de la console |
| `--simulation` | désactivé | Affiche ce qui serait copié, sans rien copier ni modifier l'historique |
| `--essais` | `3` | Nombre d'essais par fichier |
| `--delai` | `10` | Secondes d'attente entre deux essais |
| `--retention` | `90` | Nombre de jours avant la purge des entrées d'historique dont la source a disparu |
| `-v`, `--verbeux` | désactivé | Affiche aussi les fichiers ignorés car déjà copiés |

### Exemples

```bat
REM Valider un nouveau paramétrage sans rien copier
python D:\Scripts\file_management.py -c D:\Scripts\copies.conf --simulation

REM Exécution normale avec fichier de log
python D:\Scripts\file_management.py -c D:\Scripts\copies.conf --log D:\Scripts\logs\copie.log
```

### Intégration Jenkins

Ajoute une étape « Execute Windows batch command » avec la commande ci-dessus. Le job passe en échec dès que le code retour est différent de 0.

Il est recommandé de cocher « Do not allow concurrent builds ». Le script a son propre verrou, mais cette option évite des builds en échec inutiles.

## Codes retour

| Code | Signification |
|---|---|
| `0` | Exécution correcte : tout est copié ou était déjà à jour |
| `1` | Au moins une erreur : dossier inaccessible ou copie en échec après tous les essais |
| `2` | Erreur de paramétrage : fichier de configuration invalide, historique illisible ou arguments incorrects |
| `3` | Une autre exécution est déjà en cours, le verrou est pris |

## Fichier de paramétrage

### Format

Une règle par ligne. Les champs sont séparés par `|` :

```
dossier source | dossier cible | critère | masque (optionnel) | récursif (optionnel)
```

| Champ | Obligatoire | Description |
|---|---|---|
| dossier source | oui | Chemin local (`D:\Prod\Exports`) ou UNC (`\\SRV-PROD01\exports`) |
| dossier cible | oui | Chemin local ou UNC. Il est créé s'il n'existe pas |
| critère | oui | Filtre sur la date de modification (voir ci-dessous) |
| masque | non | Un ou plusieurs motifs séparés par `;`. Défaut : `*` |
| récursif | non | `oui` / `non`. Défaut : `non` |

### Critère de sélection

Le critère s'applique à la date de **modification** du fichier, à partir de minuit (heure locale du serveur) :

| Critère | Fichiers sélectionnés |
|---|---|
| `J` | modifiés depuis aujourd'hui 00h00 |
| `J-1` | modifiés depuis hier 00h00 |
| `J-N` | modifiés depuis il y a N jours, 00h00 |
| `TOUT` | tous, sans filtre de date |

Les majuscules et minuscules ne comptent pas, et les espaces sont tolérés (`j - 1` est accepté).

### Règles de syntaxe

- Les lignes vides et celles qui commencent par `#` sont ignorées.
- Les espaces autour des `|` sont ignorés. Les chemins peuvent donc contenir des espaces sans guillemets.
- Les variables d'environnement sont acceptées dans les chemins (`%DOSSIER_PROD%\exports`).
- Le fichier est lu en UTF-8, avec ou sans BOM. Un fichier enregistré depuis le Bloc-notes fonctionne.
- La source et la cible ne doivent pas être identiques. En mode récursif, la cible ne doit pas se trouver dans la source.
- Si une ligne est invalide, **aucune** copie n'est lancée. Toutes les erreurs sont listées avec leur numéro de ligne (code retour 2).

### Exemple

```
# --- Recette ---
\\SRV-PROD01\exports\factures   | \\SRV-RECETTE01\imports\factures | J-1 | *.csv
\\SRV-PROD01\exports\factures   | \\SRV-RECETTE01\imports\pdf      | J-1 | FACT_*.pdf
\\SRV-PROD01\exports\clients    | \\SRV-RECETTE01\imports\clients  | J   | *.xml;*.json

# --- Qualification ---
\\SRV-PROD01\exports\factures   | \\SRV-QUALIF01\imports\factures  | J-2 | *.csv
D:\Prod\Archives\Mensuel        | \\SRV-QUALIF01\archives          | J-7 | *    | oui
```

Un même dossier source peut alimenter plusieurs cibles. Un même environnement peut recevoir plusieurs types de fichiers.

## Fonctionnement détaillé

### Ce qui fait qu'un fichier est copié

Pour chaque règle, un fichier est **candidat** si son nom correspond au masque et que sa date de modification respecte le critère.

Un candidat est ensuite **ignoré** dans l'un de ces deux cas :

- l'historique indique que cette version du fichier (même taille, même date de modification) a déjà été copiée vers cette cible, **et** la copie existe toujours ;
- la cible contient déjà un fichier identique, avec la même taille et le même SHA-256. Il est alors simplement ajouté à l'historique.

Un candidat est **recopié** dans l'un de ces deux cas :

- il a été modifié en production depuis la dernière copie ;
- sa copie a été supprimée de la cible.

Si un fichier existe dans la cible mais avec un contenu différent, il est écrasé.

### Déroulement d'une copie

1. Le contenu est copié dans un fichier temporaire `<nom>.copie_en_cours`. Le SHA-256 de la source est calculé pendant cette lecture.
2. Le script vérifie que la source n'a pas changé pendant la copie (taille et date identiques). Cela détecte les fichiers encore en cours d'écriture en production.
3. Il vérifie la taille de la copie.
4. Il relit la copie et compare son SHA-256 à celui de la source.
5. Il recopie les métadonnées : la date de modification d'origine est conservée.
6. Il renomme le fichier temporaire en nom définitif. Ce renommage est atomique. Un éventuel attribut lecture seule sur la cible est levé au préalable.
7. Il contrôle une dernière fois la présence et la taille du fichier définitif.

En cas d'échec, le temporaire est supprimé et la copie est retentée (`--essais`, `--delai`). Après le dernier essai, l'erreur est journalisée et le script passe au fichier suivant.

### Historique

Fichier JSON. Par défaut, il est nommé d'après le fichier de paramétrage (`copies.conf` → `copies.historique.json`). Chaque entrée contient :

```json
"\\\\srv-prod01\\exports\\factures\\f1.csv => \\\\srv-recette01\\imports\\factures\\f1.csv": {
  "source": "\\\\SRV-PROD01\\exports\\factures\\F1.csv",
  "cible": "\\\\SRV-RECETTE01\\imports\\factures\\F1.csv",
  "taille": 15234,
  "mtime_ns": 1761980400000000000,
  "sha256": "9f86d081884c7d65...",
  "copie_le": "2026-11-01T06:30:12"
}
```

- Il est sauvegardé après chaque règle, de façon atomique (écriture dans `.tmp` puis renommage).
- S'il est illisible, le script s'arrête (code 2) au lieu de tout recopier sans prévenir.
- S'il est supprimé, rien n'est cassé : les fichiers déjà présents et identiques dans les cibles sont détectés par checksum et ne sont pas recopiés.
- Les entrées de plus de `--retention` jours dont le fichier source n'existe plus sont purgées en fin d'exécution.

### Verrou

Le fichier `<historique>.lock` est verrouillé pendant toute l'exécution. Une seconde instance lancée en parallèle s'arrête avec le code 3. Le verrou est libéré automatiquement par le système, même si le processus est tué.

### Journalisation

Chaque message est horodaté et envoyé sur la console (visible dans Jenkins), ainsi que dans le fichier `--log` s'il est précisé. Le script affiche un bilan par règle (sélectionnés, copiés, déjà copiés, erreurs), puis un total général.

```
2026-11-01 06:30:12 INFO    COPIE   \\SRV-PROD01\exports\factures\F1.csv -> \\SRV-RECETTE01\imports\factures\F1.csv (15234 o, sha256 9f86d0...)
2026-11-01 06:30:12 INFO    Bilan : 12 selectionne(s), 3 copie(s), 9 deja copie(s), 0 erreur(s)
```

## Référence du code

### Constantes

| Nom | Valeur | Rôle |
|---|---|---|
| `CODE_OK`, `CODE_ERREUR_COPIE`, `CODE_ERREUR_CONFIG`, `CODE_DEJA_EN_COURS` | 0, 1, 2, 3 | Codes retour |
| `TAILLE_BLOC` | 4 Mo | Taille des blocs de lecture et d'écriture |
| `SUFFIXE_TMP` | `.copie_en_cours` | Suffixe des fichiers temporaires côté cible |
| `SEPARATEUR` | `\|` | Séparateur des champs du paramétrage |

### Exceptions

| Classe | Levée quand |
|---|---|
| `ErreurConfig` | le paramétrage ou l'historique est invalide |
| `FichierInstable` | la source a été modifiée pendant la copie |
| `DejaEnCours` | le verrou est déjà pris par une autre instance |

### Paramétrage

| Fonction / classe | Rôle |
|---|---|
| `Regle` | Représente une ligne du paramétrage : source, cible, nombre de jours, masques, récursif |
| `analyser_critere(texte)` | Convertit `J` / `J-N` / `TOUT` en nombre de jours (`None` pour `TOUT`) |
| `analyser_booleen(texte)` | Convertit `oui` / `non` (et leurs variantes) en booléen |
| `analyser_ligne(num, champs)` | Valide une ligne et construit une `Regle` |
| `lire_parametrage(chemin)` | Lit le fichier complet et renvoie la liste des règles, ou lève `ErreurConfig` avec toutes les erreurs |
| `calculer_seuil(jours, maintenant)` | Renvoie le timestamp de J-N à 00h00, ou `None` |

### Historique — classe `Historique`

| Méthode | Rôle |
|---|---|
| `__init__(chemin)` | Charge l'historique s'il existe |
| `cle(src, dst)` | Construit la clé unique d'un couple source/cible, insensible à la casse sous Windows |
| `deja_copie(src, dst, st)` | Vrai si cette version du fichier a déjà été copiée et que la copie existe |
| `present_mais_cible_absente(src, dst)` | Vrai si le fichier a été copié mais supprimé depuis de la cible |
| `enregistrer(src, dst, st, sha)` | Ajoute ou met à jour une entrée |
| `purger(jours_retention)` | Supprime les entrées anciennes dont la source n'existe plus |
| `sauvegarder()` | Écrit l'historique de façon atomique, seulement s'il a été modifié |

### Verrou — classe `Verrou`

Gestionnaire de contexte (`with Verrou(...)`). Il pose un verrou exclusif non bloquant : `msvcrt.locking` sous Windows, `fcntl.flock` sous Linux.

### Copie

| Fonction | Rôle |
|---|---|
| `sha256_fichier(chemin)` | Calcule le SHA-256 d'un fichier par blocs |
| `rendre_modifiable(chemin)` | Retire l'attribut lecture seule d'un fichier |
| `supprimer_silencieusement(chemin)` | Supprime un fichier en ignorant les erreurs |
| `copier_verifier(src, dst)` | Copie via un temporaire, vérifie (stabilité, taille, SHA-256), renomme. Renvoie `(sha256, stat source)` |
| `copier_avec_essais(src, dst, essais, delai)` | Appelle `copier_verifier` avec de nouveaux essais. Renvoie `None` après le dernier échec |

### Traitement

| Fonction / classe | Rôle |
|---|---|
| `Stats` | Compteurs : sélectionnés, copiés, ignorés, erreurs |
| `lister_fichiers(regle, stats)` | Liste les fichiers de la source, récursivement ou non, triés |
| `correspond(nom, masques)` | Vrai si le nom correspond à l'un des masques |
| `traiter_regle(regle, historique, maintenant, args)` | Applique une règle complète et renvoie ses `Stats` |

### Programme principal

| Fonction | Rôle |
|---|---|
| `configurer_logs(args)` | Configure la console (sans plantage d'encodage) et le fichier de log |
| `main(argv)` | Lit les arguments et le paramétrage, prend le verrou, traite les règles, purge et sauvegarde l'historique, renvoie le code retour |

## Limites connues

- Le critère porte sur la date de **modification** et non sur la date de création. Un fichier copié en production avec sa date d'origine peut donc ne pas être sélectionné.
- Les suppressions ne sont pas propagées : un fichier supprimé en production n'est pas supprimé en test.
- Les chemins de plus de 260 caractères nécessitent d'activer le support des chemins longs de Windows (`LongPathsEnabled`) ou d'utiliser le préfixe `\\?\`.
- Un fichier verrouillé en écriture exclusive par une application de production ne peut pas être lu. Il est signalé en erreur, puis retenté à l'exécution suivante.
