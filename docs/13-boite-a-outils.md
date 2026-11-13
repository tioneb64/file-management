# 13. Boîte à outils (`outils\`)

Un **outil** est un script Python d'une seule tâche (`outils\<domaine>\<outil>.py`), appelé par un programme externe d'une règle (docs/02-moteur.md §9) ou lancé à la main. Le catalogue, avec un exemple de `commande` par outil, est dans [outils/README.md](../outils/README.md). Ce document fixe le **contrat** que tous respectent et explique comment en écrire un nouveau.

Trois choses à retenir :

- **Chaque outil a une variable** : dans la commande d'un programme, `"{outil:zip_creer}"` désigne le script sans écrire son chemin (§10). Une variable inconnue est refusée par le contrôle du paramétrage et, à l'exécution, par un message clair.
- **Le dossier des outils se règle au niveau du moteur** (§9) : vide, c'est le dossier `outils` à la racine du moteur ; sinon le dossier indiqué, n'importe où.
- **Un outil n'existe pour le moteur que s'il a un en-tête** (§7.2) : l'onglet « Outils » de l'interface (§11) parcourt le dossier, lit ces en-têtes et range la liste (variable, fichier, paramètres) dans `outils.json`. Pas d'en-tête, pas d'indexation.

## 1. Organisation

```
outils\
  _amorce\         amorce_outils.py : rend `outils.commun` et `journal_si` importables où que soit le dossier (§9.3)
  commun\          socle : options, journal, codes retour, entrées, atomicité, dépendances, archives, EXIF… (chaque module porte « # bibliotheque: », §7.2)
  compression\     zip_creer, zip_extraire, archive_creer, archive_extraire, zip_chiffrer, fichier_decouper, fichier_recoller
  recherche\       chercher_nom, chercher_contenu, remplacer_contenu, doublons_trouver
  organisation\    renommer_masse, noms_normaliser, trier_fichiers, doublons_supprimer
  conversion\      encodage_convertir, fin_ligne_convertir, xlsx_vers_csv, document_vers_pdf, image_convertir
  dates_attributs\ touch, attributs, permissions
  fichiers\        copier_verifie, texte_decouper, csv_fusionner, comparer_fichiers, synchroniser,
                   dossiers_vides_supprimer, inventaire
  controle\        attendre_stable, valider_fichier, empreinte, espace_disque
  notification\    courriel, webhook
  transfert\       sftp_envoyer, sftp_recuperer (SFTP, module paramiko facultatif)
```

Les scripts existants de `outils\` (`charge_journal.py`, `comparer_dossiers.py`, `controle_serveur.py`, `mesure_*.py`, `lancer_tests.ps1`) ne sont pas touchés : sans en-tête d'outil, le scan les ignore (« non retenu : pas d'en-tête », sans gravité). Chaque outil se lance directement (`python outils\controle\valider_fichier.py …`, depuis n'importe quel dossier) : ses deux premières lignes de code importent l'amorce, qui retrouve le moteur (§9.3).

## 2. Appel par le moteur

Le moteur lance l'outil comme tout programme (§9 du moteur ; avec `{outil:nom}` il remplace la variable par l'interpréteur Python du moteur et le chemin du script, §10) : sans shell, tableau `commande` dont chaque élément reçoit ses variables, répertoire courant `dossier_travail`, entrée standard fermée, sortie standard + erreur reprises dans le journal (8 Ko). Il fournit aux outils, en variables d'environnement :

| Variable | Contenu |
|---|---|
| `COPIE_REGLE`, `COPIE_EXECUTION_ID`, `COPIE_POINT_APPEL`, `COPIE_SIMULATION` | La règle, son exécution, le point d'appel, 0/1 |
| `COPIE_FICHIER`, `COPIE_FICHIER_CIBLE`, `COPIE_LISTE`, `COPIE_LISTE_JSON`, `COPIE_SOURCE`, `COPIE_CIBLE`, `COPIE_ARCHIVE`, `COPIE_STATUT`, `COPIE_SITUATION`, `COPIE_MESSAGE` | Les éléments à traiter (voir §3) |
| **`COPIE_DOSSIER_LOGS`** | Dossier des journaux de l'en-tête (ajoutée pour la boîte à outils) |
| **`COPIE_CODE_ENVIRONNEMENT`** | Code d'environnement de la plateforme d'observabilité (`prod`, `pprod`…) (ajoutée) |
| **`COPIE_DOSSIER_TRAVAIL`** | Dossier de travail du moteur (ajoutée) |
| **`COPIE_RACINE_MOTEUR`** | Dossier du moteur (celui qui contient `journal_si.py` et `file_management\`) ; l'amorce des outils s'en sert quand le dossier des outils n'est pas à côté du moteur (ajoutée avec le réglage du dossier des outils) |
| `TRACEPARENT` | Trace W3C du lancement (héritée de l'orchestrateur) |

Le moteur interprète le code retour : **0 et 1 acceptés** à chaque point d'appel ; 1 à `avant_lot` = « rien à faire » (la règle s'arrête sans erreur), à `avant_fichier` = « ignorer ce fichier ». Tout autre code applique la situation `programme_<point>` avec ses tentatives.

## 3. Contrat d'un outil

### 3.1 Entrées

- **Fichiers à traiter** : arguments (jokers `* ? []` acceptés), `--liste FICHIER` (un chemin par ligne, UTF-8, comme `{liste}`), `--masque`, `--exclure`, `--recursif`. Sans rien : `COPIE_FICHIER`, sinon `COPIE_LISTE`, sinon `COPIE_SOURCE`. Les fichiers `*.copie_en_cours` (écriture en cours du moteur) sont toujours ignorés.
- **Outils de dossier** (`synchroniser`, `inventaire`, `dossiers_vides_supprimer`, `espace_disque`, `comparer_fichiers`, `chercher_nom` pour l'arborescence) : passer les dossiers explicitement (`{source}`, `{cible}`) ; `chercher_nom` teste aussi sur leur nom les fichiers désignés (la `{liste}` du lot).
- **Secrets** : `--mot-de-passe-env NOM` (variable d'environnement) ou `--mot-de-passe-fichier F` ; jamais `--mot-de-passe VALEUR`. Un jeton HTTP : `--en-tete-env`.
- **Tailles** : `4096`, `500K`, `100M`, `1.5G`. **Dates** : `AAAA-MM-JJ`, `"AAAA-MM-JJ HH:MM[:SS]"`, `maintenant`.

### 3.2 Comportement

| Règle | Détail |
|---|---|
| Simulation | `--simulation` (ou `COPIE_SIMULATION=1`) dès que l'outil écrit, supprime ou envoie : il journalise ce qu'il ferait (événements `*_a_*`, `simulation: true`) et ne touche à rien |
| Pas d'écrasement | Un fichier de sortie existant est une erreur (`DUPLICATE_ENTITY`) sauf `--ecraser` |
| Atomicité | Écriture dans `<fichier>.copie_en_cours` puis `os.replace` ; jamais de fichier de sortie à moitié écrit (un échec le supprime) |
| Tolérance | Un élément en erreur est journalisé (`ERROR`) et les suivants sont traités ; code 2 à la fin. `--arreter-si-erreur` stoppe au premier |
| Rien à faire | Zéro action → statut `RIEN`, code 0 ; code 1 avec `--code-si-rien 1` |
| Sortie standard | Brève (le moteur tronque à 8 Ko) : une ligne finale `OK : <outil> : <compteurs>`, `OK AVEC AVERTISSEMENT`, `RIEN A FAIRE` ou `ERREUR` (+ ` (simulation)`) |
| Aide | `--aide`, en ASCII (consoles Windows en page OEM) |
| Erreur imprévue | Journalisée avec `INTERNAL_ERROR`, `exception` et `stacktrace` dans le **journal** ; jamais de trace Python sur la sortie |

### 3.3 Codes retour

`0` fait · `1` rien à faire (avec `--code-si-rien 1`) ou fichier à ignorer (`valider_fichier --code-si-invalide 1`, `espace_disque --code-si-insuffisant 1`) · `2` erreur d'exécution · `3` paramètres invalides · `4` dépendance externe absente.

## 4. Journal

Chaque outil utilise `journal_si.Journal`, **comme le moteur** (`file_management/__main__.py`) : même bibliothèque, même catalogue de messages, même format de la plateforme d'observabilité (vérifié par `tests/test_format_plateforme.py` sur les lignes des outils).

| Élément | Valeur |
|---|---|
| Fichier | `<dossier_logs>\<règle>_<AAAA-MM-JJ>.jsonl` : **le même que celui de la règle** (sans règle : `_orchestrateur_<jour>.jsonl`) |
| `service.name` | `file_management.<règle>` |
| `service.environment` | `--environnement`, sinon `COPIE_CODE_ENVIRONNEMENT`, sinon déduit de `COPIE_ENVIRONNEMENT`, sinon `dev` |
| Trace | `TRACEPARENT` (même `trace_id` que le moteur) ; `execution_id` = `COPIE_EXECUTION_ID` |
| Contexte | `outil` (nom), `regle`, `execution_id`, `point_appel`, `simulation: true` en simulation seulement |
| Cycle de vie | `outil_demarre` (début), `outil_termine` (fin : `statut` SUCCES / WARNING / ERREUR / RIEN, `compteurs`, `code_retour`, `duration_ms`) |
| Actions | Un événement par action (`fichier_renomme`, `archive_creee`, `courriel_envoye`…), niveau INFO ; en simulation `fichier_a_renommer`… |
| Niveaux | DEBUG (détails, `--verbeux`), INFO, WARNING (avertissement, fichier invalide toléré), ERROR (élément en échec), CRITICAL |
| `error.type` | `FILE_IO_ERROR`, `FILE_NOT_FOUND`, `DUPLICATE_ENTITY`, `RESOURCE_EXHAUSTED`, `EXTERNAL_SERVICE_ERROR`, `TIMEOUT`, `INTERNAL_ERROR`, `BUSINESS_RULE_VIOLATION` (paramètres ou fichier invalides) |
| Messages | Français **sans accents** (comme le moteur) |
| Secrets | Un mot de passe ou un jeton n'est **jamais** écrit : ni dans les champs, ni dans les messages d'erreur (les textes renvoyés par un serveur sont masqués), ni dans la ligne de commande journalisée ; l'URL d'un webhook est réduite à `serveur + chemin` |

Lancé à la main, sans règle, un outil écrit dans `_orchestrateur_<jour>.jsonl` du dossier `--dossier-logs` (défaut `JOURNAL_SI_DOSSIER`, sinon `logs`). `--console` recopie sur la console.

## 5. Dépendances facultatives

| Dépendance | Outils | Détection | Absente |
|---|---|---|---|
| 7-Zip `7z.exe` | `archive_creer` (7z), `archive_extraire` (7z, rar, iso), `zip_chiffrer` (repli), `zip_extraire` (zip AES sans `pyzipper`) | `OUTIL_7Z`, `PATH`, `C:\Program Files\7-Zip` | code 4 |
| WinRAR `rar.exe` | `archive_creer` (rar) | `OUTIL_RAR`, `PATH`, `C:\Program Files\WinRAR` | code 4 |
| `pyzipper` | `zip_chiffrer`, `zip_extraire` (zip AES) | `import pyzipper` | repli 7-Zip, sinon code 4 |
| LibreOffice | `document_vers_pdf` | `OUTIL_SOFFICE`, `PATH`, `C:\Program Files\LibreOffice\program` | code 4 |
| Pillow | `image_convertir` | `import PIL` | code 4 |
| `paramiko` (`pip install paramiko`) | `sftp_envoyer`, `sftp_recuperer` | `import paramiko` | code 4 |

Une variable `OUTIL_*` qui désigne un fichier inexistant est une erreur de configuration (code 4), pas un repli silencieux.

**ISO** : extraction seulement (via 7-Zip). Créer une image ISO n'a pas de solution fiable en bibliothèque standard ni d'outil d'usage courant sur un serveur ; l'outil le dit et refuse.

## 6. Sécurité

- **Aucun shell** : programmes externes (7z, rar, soffice, icacls) lancés avec un tableau d'arguments ; les comptes et droits d'`icacls` sont validés par expression régulière avant l'appel.
- **Chemins** : extraction zip / tar / 7z refuse tout chemin qui sort du dossier de destination (`..`, chemin absolu, lecteur, lien) ; les tar avec liens ou fichiers spéciaux sont refusés ; les liens de dossier ne sont jamais suivis (`dossiers_vides_supprimer`, `synchroniser`, parcours).
- **Bombes de décompression** : `--taille-max` et contrôle de l'espace disque avant extraction, pour zip, tar et aussi 7z / rar / iso (taille annoncée lue par `7z l -slt` avant d'extraire).
- **Mots de passe** : jamais en ligne de commande, sauf **limite connue** : 7-Zip reçoit le mot de passe en argument (`-p`), visible des autres processus du serveur pendant l'exécution ; l'outil la signale par un `WARNING` (`mot_de_passe_ligne_de_commande`) et préfère `pyzipper`, qui ne l'expose pas.
- **Suppressions** : `doublons_supprimer` exige `--action` ; `synchroniser --miroir` refuse une source vide, des dossiers imbriqués et, avec `--max-suppressions`, un nombre de suppressions trop élevé ; `dossiers_vides_supprimer` refuse une racine de disque. Toujours essayer d'abord avec `--simulation`.
- **Notifications** : `courriel` rejette les adresses contenant un saut de ligne et rend le sujet sur une ligne (pas d'injection d'en-tête) ; `webhook` refuse les identifiants dans l'URL.
- **SFTP** (`sftp_envoyer`, `sftp_recuperer`) : (1) la **clé de l'hôte est toujours vérifiée** : empreinte attendue `--empreinte-hote SHA256:…` ou `known_hosts` (`--known-hosts`, sinon celui de l'utilisateur) ; une clé inconnue est **refusée** (le message donne l'empreinte relevée, à faire confirmer par le partenaire), sauf `--hote-inconnu accepter` (avertissement journalisé) ; une clé **différente** de celle connue est toujours refusée, et ce **avant** l'envoi du mot de passe ; (2) mot de passe seulement par variable ou fichier, phrase secrète de la clé privée par variable, rien au journal ni dans les sorties (testé) ; (3) une **authentification refusée n'est jamais rejouée** (pas de verrouillage du compte), un incident réseau l'est (`--tentatives`, `--pause`), même en cours de fichier ; (4) dépôt sous un nom temporaire (`.tmp` côté serveur, `.copie_en_cours` en local) puis renommage : un fichier n'est jamais visible incomplet ; une coupure laisse le temporaire, repris au prochain essai **si son contenu est exactement le début du fichier** (comparaison SHA-256 du préfixe), sinon réécrit ; (5) jamais d'écrasement sans `--ecraser` (ni pour le fichier final, ni pour l'archive : un nom déjà pris devient `nom_2.ext`) ; (6) `--apres-envoi` / `--apres-recuperation` n'agissent qu'après un transfert contrôlé : un échec laisse le fichier d'origine intact.

## 7. Écrire un nouvel outil

Un nouvel outil est un fichier Python de plus dans le dossier des outils : rien à déclarer ailleurs que dans **son en-tête**, que le scan (§11) lit pour créer sa variable.

### 7.1 Étapes

1. **Créer le fichier** `<dossier des outils>\<domaine>\<nom>.py`, dans un sous-dossier existant ou nouveau (le scan parcourt tous les sous-dossiers ; un sous-dossier dont le nom commence par `_` ou `.` est ignoré).
2. **Écrire l'en-tête** (§7.2), tout en haut, avant la docstring.
3. **Écrire le code** sur le squelette du §7.3.
4. **Écrire les tests** (§7.5).
5. **Scanner** : onglet « Outils » de l'interface, bouton « Enregistrer et scanner » (ou `python -m file_management --scanner-outils` pour voir le résultat sans rien écrire). L'outil n'est utilisable par `{outil:nom}` qu'après le scan.
6. **Documenter** : une ligne dans [outils/README.md](../outils/README.md), une dans le cahier de tests.

### 7.2 L'en-tête (obligatoire)

L'en-tête est le **bloc de commentaires `#` du tout début du fichier** (il s'arrête à la première ligne qui n'est pas un commentaire ; au plus 200 lignes). Le scan ne lit que lui : il n'exécute ni n'importe jamais le script.

```python
# outil: archive_extraire
# description: Extrait une archive (zip, tar, 7z, rar, iso) dans un dossier, avec protection contre les chemins dangereux.
# parametre: ARCHIVE | obligatoire | archive a extraire
# parametre: --vers DOSSIER | obligatoire | dossier de destination
# parametre: --taille-max TAILLE | facultatif | refuse l'archive si elle annonce plus (ex. 2G)
# parametre: --ecraser/-e | facultatif | remplace les fichiers existants
```

| Ligne | Règle |
|---|---|
| `# outil: nom` | **Une seule** ligne : le nom de la variable, `{outil:nom}`. Minuscules, chiffres et `_`, commence par une lettre, 64 caractères au plus |
| `# description: texte` | **Une seule** ligne, non vide : ce que fait l'outil (affichée dans l'onglet Outils) |
| `# parametre: forme \| obligatoire ou facultatif \| description` | Zéro ou plusieurs. La **forme** commence par le nom du paramètre, tel qu'on l'écrit dans la commande (`--vers`, `CHEMIN`) ; les synonymes se séparent par `/` (`--ecraser/-e`) ; ce qui suit le nom est le texte d'aide (`DOSSIER`). La description peut contenir des `\|` |
| `# bibliotheque: texte` | **Modules de support seulement** (pas un outil) : une seule ligne non vide qui dit ce que le module fournit. Le module est alors listé à part par le scan (« Bibliothèque ») et n'entre jamais dans l'index. Incompatible avec `# outil:` dans le même fichier |
| autre commentaire | Libre (shebang, licence, notes) : ignoré |

Conséquences :

- **Sans ligne `# outil:`, le script n'est pas indexé** (cause « pas d'en-tete d'outil ») : c'est le cas voulu des scripts ordinaires (scripts de recette, de mesure).
- **Un module importé par les outils** (tout `commun\*.py`) n'a ni ligne de commande ni paramètres : il ne peut pas être appelé par une règle. Il se déclare par `# bibliotheque: …` (une ligne) pour que le scan le range à part, avec sa description, au lieu de le signaler comme script sans en-tête. Un test du dépôt exige cette ligne sur chaque module de `outils\commun`.
- Un en-tête **invalide** n'est pas indexé non plus, et le scan donne la cause : nom refusé, deux `# outil:`, `# description:` absente ou en double, ligne `# parametre:` mal formée, paramètre déclaré deux fois.
- Deux scripts qui annoncent le **même nom** : le premier (ordre alphabétique du chemin) garde la variable, l'autre est « non retenu : la variable est déjà prise ».
- Le fichier doit être en **UTF-8**. Les outils du dépôt écrivent leur en-tête en ASCII (comme leur aide).
- Les paramètres **obligatoires** qui sont des options (`--vers`) sont vérifiés par le contrôle du paramétrage : une commande `["{outil:archive_extraire}", "{fichier}"]` sans `--vers` est refusée (G01) avant le premier lancement. Les paramètres positionnels et facultatifs sont affichés mais pas contrôlés.
- Un test du dépôt (`TestEnteteDesOutilsDuDepot`, `tests/test_outils_variables.py`) compare l'en-tête de **chaque outil du dépôt** à son analyseur d'arguments (mêmes options, mêmes obligations) : un paramètre ajouté au code sans l'être dans l'en-tête fait échouer les tests. Pour un outil hors dépôt, cette vérification est à votre charge.

### 7.3 Squelette

```python
# outil: mon_outil
# description: Une phrase : ce que fait l'outil.
# parametre: --sortie DOSSIER | obligatoire | ou ecrire les fichiers traites
# parametre: --ecraser | facultatif | remplace un fichier existant
# parametre: CHEMIN | facultatif | fichiers a traiter (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
"""Une phrase : ce que fait l'outil."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import ErreurOutil, ErreurParametres
from outils.commun.fichiers import sortie_atomique, verifier_ecrasement
from outils.commun.outil import Outil

OUTIL = Outil("mon_outil", "Description (ASCII, sert d'aide)", "domaine")


@OUTIL.arguments
def arguments(p):
    options_entrees(p)                           # chemins, --liste, --masque, --exclure, --recursif
    p.add_argument("--sortie", required=True)
    p.add_argument("--ecraser", action="store_true")


@OUTIL.principal
def principal(ctx, args):
    for chemin, base in ctx.fichiers():          # un chemin introuvable est une erreur de l'element
        with ctx.tolerer("mon_echec", fichier=chemin):      # l'exception est journalisee, on passe au suivant
            cible = os.path.join(args.sortie, os.path.relpath(chemin, base))
            if ctx.simulation:
                verifier_ecrasement(cible, args.ecraser)
                ctx.action("fichier_a_traiter", "Serait traite : %s" % os.path.basename(chemin), fichier=chemin)
                continue
            with sortie_atomique(cible, args.ecraser) as tmp:
                ...                              # ecrire dans tmp
            ctx.action("fichier_traite", "Traite : %s" % os.path.basename(chemin), fichier=chemin, cible=cible)


if __name__ == "__main__":
    OUTIL.lancer()
```

Les deux lignes d'amorce sont **obligatoires et à cet endroit** (avant tout `from outils…`) : si le dossier des outils est déplacé (§9) ou porte un autre nom, elles seules retrouvent `outils.commun` et `journal_si`. Les options communes (`--simulation`, `--aide`, `--verbeux`, `--console`, `--dossier-logs`, `--environnement`, …) viennent de la classe `Outil` : ne pas les déclarer dans l'en-tête.

L'outil ne doit **jamais** ajouter lui-même le dossier des outils à `sys.path` : un sous-dossier comme `compression` masquerait le paquet standard du même nom (Python 3.14).

### 7.4 Règles de code

Messages sans accents ; `ErreurParametres` pour un paramètre invalide (code 3), `DependanceAbsente` pour un programme ou module manquant (code 4), `ErreurOutil(message, type_erreur)` pour une erreur d'élément ; `ctx.imposer_code(1)` pour « fichier à ignorer » ; aucun `print` direct (`ctx.afficher`) ; jamais de mot de passe dans un champ de journal.

### 7.5 Tests et documentation

- `tests\test_outils_<domaine>.py`, classe de base `tests.boite_outils.CasOutil` (`self.lancer(module, *arguments)`, `self.controler_journal(...)`). Par outil : cas nominal, simulation (rien d'écrit), erreur sur un élément, `--ecraser`, lignes de journal (`outil_demarre`, action, `outil_termine`, `service.name`, `simulation`). Sans `ResourceWarning` ni `DeprecationWarning` (`lancer_tests.ps1` échoue sinon).
- Le test `test_les_outils_du_depot_sont_tous_retenus` et le garde-fou de l'en-tête (§7.2) s'appliquent d'office aux nouveaux outils du dépôt ; le nombre d'outils attendu y est à mettre à jour.
- Documentation : une ligne dans [outils/README.md](../outils/README.md) (variable, exemple de commande), une dans le cahier de tests.

## 8. Tests

| Fichier | Contenu |
|---|---|
| `tests/test_outils_commun.py` | Socle : options, codes retour, journal, entrées, atomicité, secrets |
| `tests/test_outils_<domaine>.py` | Un fichier par domaine (compression, recherche, organisation, conversion, dates_attributs, fichiers, controle, notification, transfert ; le serveur SFTP local des essais : `tests/serveur_sftp.py`) |
| `tests/test_outils_moteur.py` | **Vraies règles du moteur** appelant les outils à `avant_lot`, `avant_fichier`, `apres_fichier`, `apres_lot`, `sur_erreur` : contrat des codes 0 / 1 / 2 / 3 / 4, variables `COPIE_*`, lignes d'outil dans le fichier de la règle (même trace, même `execution_id`, même `service.name`), simulation |
| `tests/test_programmes.py` | Variables `COPIE_DOSSIER_LOGS`, `COPIE_CODE_ENVIRONNEMENT`, `COPIE_DOSSIER_TRAVAIL` transmises par le moteur |
| `tests/test_outils_variables.py` | En-tête (valide, invalide, cause), scan (sous-dossiers, variable déjà prise, liens, dossier vide), index `outils.json`, `{outil:nom}` à l'exécution (outil inconnu, fichier disparu, aucun index, dossier déplacé et renommé), contrôles G01, commande `--scanner-outils`, garde-fou en-tête / analyseur d'arguments des 38 outils |
| `Gui/Tests/Outils.Tests.ps1` | Onglet « Outils » : lecture de l'index, exemple de commande, lignes de la fenêtre de résultat, scan réel (moteur Python), écriture atomique de `outils.json`, journal de l'interface |

Ce qui n'a **pas** été essayé pour de vrai (7-Zip, WinRAR, LibreOffice, `pyzipper`, SMTP réel, ISO) est testé avec de faux programmes et de faux modules, et figure dans « ACTIONS À FAIRE » du [CHANGELOG](../CHANGELOG.md).
## 9. Dossier des outils et index

### 9.1 Où sont les outils

Le dossier des outils est un **réglage du moteur**, commun à tous les environnements (il ne dépend d'aucun d'eux, comme les racines de l'en-tête n'en dépendent pas pour le moteur lui-même) :

| Réglage | Dossier utilisé |
|---|---|
| **vide** (défaut) | `outils\` à la racine du moteur (le dossier qui contient `file_management\`) |
| **un chemin** | exactement ce dossier, avec ses sous-dossiers. Pas de variante « sous-dossier `outils` du chemin indiqué » |

Les outils peuvent donc vivre à côté du moteur ou ailleurs (un dossier partagé, un autre dépôt), sous n'importe quel nom. Ils sont indépendants du reste du moteur sauf pour deux modules : `journal_si` et, via l'amorce, `outils.commun` (§9.3).

### 9.2 L'index `outils.json`

Le réglage et la liste des outils trouvés sont rangés dans **`outils.json`, dans le dossier de paramétrage** (à côté du fichier `--config`). Il est écrit par l'interface après un scan ; le moteur le lit (et le met en cache le temps d'un lancement), il ne l'écrit jamais.

```json
{
 "version": 1,
 "dossier_outils": "",
 "dossier_resolu": "D:\\moteur\\outils",
 "scanne_le": "2026-11-13T09:41:07",
 "scanne_par": "DOM\\benoit",
 "outils": [
  {
   "variable": "archive_extraire",
   "fichier": "compression\\archive_extraire.py",
   "description": "Extrait une archive (zip, tar, 7z, rar, iso) …",
   "parametres": [
    {"forme": "--vers DOSSIER", "obligatoire": true, "description": "dossier de destination"}
   ]
  }
 ]
}
```

| Champ | Sens |
|---|---|
| `dossier_outils` | Le **réglage** : vide = dossier `outils` du moteur |
| `dossier_resolu` | Le dossier réellement parcouru lors du scan (information) |
| `fichier` | Chemin **relatif** au dossier des outils, avec le sous-dossier : `compression\archive_extraire.py` |
| `variable` | Nom de la variable : `{outil:archive_extraire}` |
| `parametres` | Les lignes `# parametre:` de l'en-tête |

Le moteur concatène le dossier du réglage (ou celui du moteur) et `fichier` : changer le réglage puis **scanner de nouveau** suffit à tout déplacer. Un `outils.json` illisible, ou d'une `version` inconnue, est une erreur de paramétrage dite en clair (il n'est lu que si une commande utilise `{outil:…}` ; sans variable d'outil, son absence n'a aucune conséquence).

### 9.3 Amorce et déplacement

Chaque outil commence par `import amorce_outils` (fichier `_amorce\amorce_outils.py` du dossier des outils). Elle :

1. enregistre le dossier des outils sous le nom de paquet `outils` (même s'il s'appelle autrement) ;
2. ajoute à la fin de `sys.path` le dossier du moteur : variable d'environnement **`COPIE_RACINE_MOTEUR`** (transmise par le moteur), sinon le dossier parent du dossier des outils ;
3. sort avec le **code 4** et un message clair si `journal_si.py` reste introuvable : « définir `COPIE_RACINE_MOTEUR` ».

Lancé à la main depuis un dossier déplacé, un outil a donc besoin de `COPIE_RACINE_MOTEUR` s'il n'est pas à côté du moteur. Lancé par le moteur, rien à faire. Le dossier `_amorce` doit accompagner les outils quand on les déplace.

## 10. Appeler un outil par une variable

Dans un programme (`avant_lot`, `avant_fichier`, `apres_fichier`, `apres_lot`, `sur_erreur`, `reprise`), le **premier élément** de `commande` peut être `{outil:nom}` :

```json
"avant_lot": {
  "commande": ["{outil:valider_fichier}", "--liste", "{liste}", "--code-si-invalide", "1"],
  "timeout_sec": 300
}
```

Le moteur remplace cet élément par **deux** éléments : l'interpréteur Python qui fait tourner le moteur et le chemin du script (dossier du réglage + `fichier` de l'index). Les autres variables (`{liste}`, `{fichier}`, `{source}`…) sont remplacées ensuite, comme pour tout programme. La suite des éléments est à écrire à la main : les paramètres attendus sont affichés dans l'onglet Outils, avec un exemple de début de commande à copier.

| Situation | Où | Résultat |
|---|---|---|
| `{outil:…}` ailleurs qu'en premier élément, ou mal formé (`{outil:}`, majuscules, `{outil:a}b`) | contrôle du paramétrage | refus **G01**, avec le point d'appel |
| Nom absent de l'index | contrôle du paramétrage **et** exécution | G01 « outil inconnu : {outil:x} (outils indexes : a, b, …) » ; à l'exécution, le programme n'est pas lancé et l'erreur est la même, claire |
| Aucun `outils.json` | idem | « aucun index des outils … scanner le dossier des outils dans l'interface (onglet Outils) » |
| Paramètre obligatoire (option) absent de la commande | contrôle du paramétrage | G01, avec la forme attendue (`--vers DOSSIER`) |
| Fichier de l'outil disparu (déplacé, supprimé) | `--verifier` complet et exécution | « le fichier de l'outil … est introuvable … scanner de nouveau » ; **pas** contrôlé par `--syntaxe-seule` (qui ne regarde aucun fichier) |

Une commande qui n'utilise pas `{outil:…}` n'est jamais concernée : l'index n'est même pas lu. L'ancienne forme (chemin complet de l'interpréteur et du script) reste valide.

## 11. Scan et onglet « Outils »

### 11.1 Le scan

`python -m file_management --scanner-outils [--dossier-outils DOSSIER] [--utilisateur U] [--format json]` parcourt le dossier (le réglage ou, sans option, le dossier `outils` du moteur) **et ses sous-dossiers**. Il **n'écrit rien** : il renvoie le résultat et le texte du futur `outils.json` (champ `contenu_index`), c'est l'interface qui l'enregistre. Ignorés d'office : `__init__.py`, les dossiers `__pycache__`, ceux dont le nom commence par `_` ou `.`, les liens de dossier. Seuls les `.py` sont examinés, et seule la tête du fichier est lue.

Réponse JSON : `ok`, `message`, `dossier`, `dossier_configure`, `outils` (variable, fichier, description, paramètres), `non_retenus` (`fichier`, `cause`), `bibliotheques` (`fichier`, `description`), `erreurs` (dossiers illisibles), `fichiers_python`, `dossiers`, `contenu_index`. Code 2 si le dossier est introuvable.

Un module qui porte `# bibliotheque:` est rangé dans `bibliotheques` (`fichier`, `description`), ni retenu ni non retenu. Un script est **non retenu** pour l'une de ces causes : pas d'en-tête d'outil (information : script ordinaire) ; en-tête invalide (détail de la ligne fautive) ; variable déjà prise par un autre script ; fichier illisible (pas de l'UTF-8, droits).

### 11.2 L'onglet

L'onglet **Outils** de la fenêtre du moteur (le dernier, après les onglets d'environnement) :

- **Dossier des outils** : zone de saisie (vide = dossier `outils` du moteur) et « Parcourir… » (moteur local seulement) ;
- **« Enregistrer et scanner »** : lance le scan ; si au moins un outil est retenu, écrit `outils.json` (de façon atomique) ; sinon **n'écrit rien** : un dossier faux ne remplace pas un bon index ;
- la **liste** : variable `{outil:nom}`, sous-dossier, fichier, description, paramètres obligatoires ; une recherche filtre sur ces colonnes ;
- le **détail** de l'outil choisi : description, fichier, les paramètres (obligatoire ou non, rôle) et un **début de commande à copier** (`["{outil:nom}", "--obligatoire", "<valeur>"]`).

À la fin du scan, **une fenêtre de résultat** (comme les autres opérations de l'interface) liste le dossier analysé, chaque outil retenu, chaque module de bibliothèque (information) et chaque script non retenu avec sa cause ; les mêmes lignes sont écrites dans le **journal de l'interface** (événements `outils_scan`, `outil_retenu`, `outil_bibliotheque`, `outil_non_retenu`, `outils_index`).

Droits : l'enregistrement du réglage et de l'index est une action d'**administrateur**, comme les autres modifications du paramétrage ; pour un autre compte, l'onglet reste consultable (zone en lecture seule, boutons masqués). Avec JEA, la commande `--scanner-outils` est autorisée (droit d'écriture, `--dossier-outils` en chemin libre, `--utilisateur` ajouté automatiquement).

À refaire après chaque ajout, retrait, déplacement ou modification d'en-tête d'un outil.
