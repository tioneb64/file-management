# Installation

Ce guide installe copie_fichiers v2 (moteur Python, Jenkins, journaux, interface de gestion) **dans l'ordre**, avec une vérification à la fin de chaque étape. Il s'adresse à l'exploitation. Les spécifications sont dans les autres documents de ce dossier ; l'usage de l'interface est dans [11-guide-utilisateur](11-guide-utilisateur.md).

> **État de validation.** Les commandes ci-dessous ont été vérifiées sur un poste Windows 10 avec Python 3.14.10 et Windows PowerShell 5.1. **Rien n'a encore été joué sur le serveur Windows Server 2016**, ni dans votre Jenkins, ni avec une vraie session JEA, ni avec Alloy. Chaque étape indique ce qui reste à confirmer ; les tests correspondants sont dans le [cahier de tests](06-cahier-de-tests.md).

## 0. Ce qu'il faut avant de commencer

| Élément | Détail |
|---|---|
| Serveur d'exécution | Windows Server 2016, **PowerShell 5.1**. Disque **local** pour la base (jamais un partage réseau). Horloge synchronisée (NTP) |
| Compte de service | Celui de l'agent Jenkins. Droits : **lecture** des sources, **écriture** des cibles et archives, écriture de la base, des journaux et du dossier de travail, **lecture seule** du paramétrage |
| Groupe AD des administrateurs | Les membres modifient le paramétrage ; les autres consultent. Distinct du compte de service |
| Poste de l'administrateur | Windows avec PowerShell 5.1 (l'interface est en WPF). Il peut être le serveur lui-même ou un autre poste |
| Dossier du dépôt | Exemples de ce guide : `D:\Scripts\copie_fichiers` (le dépôt), `D:\Parametrage` (paramétrage), `D:\Copie` (bases et journaux). À adapter |
| Python | **3.14** (`C:\Python314\python.exe` dans les exemples) : la 3.15 n'est pas retenue pour Windows Server 2016 |

## 1. Python et contrôle du serveur

1. Installer Python 3.14 pour tous les utilisateurs, dans `C:\Python314`.
2. Contrôler que le serveur sait faire ce dont le moteur a besoin (SQLite en mode WAL, écritures concurrentes, verrous, Job Object, remplacement atomique, partage réseau). Depuis le dossier du dépôt, **avec le compte de service si possible** :

```bat
C:\Python314\python.exe outils\controle_serveur.py --partage \\SERVEUR\partage\test --json rapports\controle_serveur.json
```

Tout doit être en succès (code retour 0). Un échec est à traiter **avant** d'aller plus loin ; le rapport est à envoyer au développement.

3. Lancer les tests du moteur sur le serveur (une dizaine de minutes) :

```powershell
.\outils\lancer_tests.ps1 -Python C:\Python314\python.exe
```

Le rapport est écrit dans `rapports\tests_<machine>_<date>.txt`. **Attendu : tous les tests OK.** C'est le jalon J0 du [cahier de tests](06-cahier-de-tests.md) ; Python 3.14 sur Windows Server 2016 n'y a pas encore été essayé.

## 2. Le moteur

1. Copier le dépôt sur le serveur (`D:\Scripts\copie_fichiers`). Le moteur n'utilise que la bibliothèque standard : **aucun `pip install`**.
2. Vérifier l'appel :

```bat
cd /d D:\Scripts\copie_fichiers
C:\Python314\python.exe -m copie --help
```

Le moteur se lance toujours par `python -m copie` depuis ce dossier (ou par `copie_fichiers_v2.py`, qui est équivalent). `copie_fichiers.py` reste l'**ancien** script v1 tant que la bascule n'est pas faite ([09-migration-et-recette](09-migration-et-recette.md)).

## 3. Dossier de paramétrage protégé

Le fichier de paramétrage décide quels programmes le compte de service exécute : celui qui peut l'écrire agit avec les droits de ce compte. Le dossier est donc réservé aux administrateurs et au compte de service (en **lecture seule**).

1. Aperçu, sans rien modifier (le script demande de toute façon une confirmation) :

```powershell
.\Gui\Initialiser-DossierParametrage.ps1 -Dossier D:\Parametrage -GroupeAdmin 'DOMAINE\GG_Copie_Admins' -CompteService 'DOMAINE\svc-jenkins' -WhatIf
```

2. Puis sans `-WhatIf`, **avec un compte membre du groupe administrateur** (le script refuse sinon, pour ne pas vous couper l'accès).

Il crée le dossier et son sous-dossier `versions` (historique des modifications, **sans accès** pour le compte de service), coupe l'héritage et pose les droits. Les administrateurs locaux n'y ont pas accès, sauf `-InclureAdministrateursLocaux`.

**Vérifier** : avec le compte de service, lire un fichier du dossier fonctionne, en écrire un est refusé ; ouvrir `versions` est refusé.

> Si le dossier est un partage réseau (`\\SERVEUR\Parametrage`) pour que les administrateurs travaillent depuis leur poste, appliquer les mêmes droits sur le partage **et** sur le dossier, et utiliser **le même chemin UNC partout** (interface, Jenkins, JEA).

## 4. Un environnement : paramétrage et base

Chaque environnement (production, recette…) a **un fichier** `D:\Parametrage\<environnement>.jsonl` et **une base** SQLite.

1. **Écrire le fichier** : soit partir de `exemples\production.jsonl`, soit convertir l'ancien `copies.conf` (règles créées **inactives**, à relire une à une : voir [09-migration-et-recette](09-migration-et-recette.md) §4). L'en-tête (première ligne) donne l'environnement (le même que le nom du fichier) et le chemin de la base, **sur un disque local** :

```json
{"version": 1, "environnement": "production", "base": "D:\\Copie\\production.db"}
```

2. **Vérifier la syntaxe** :

```bat
C:\Python314\python.exe -m copie --config D:\Parametrage\production.jsonl --verifier --syntaxe-seule
```

3. **Vérifier les accès** (droits sur les sources, cibles, archives, programmes, base), **avec le compte de service** : c'est lui qui exécutera les transferts, un contrôle fait avec un autre compte ne prouve rien pour Jenkins.

```bat
C:\Python314\python.exe -m copie --config D:\Parametrage\production.jsonl --verifier
```

Code 0 : tout est bon ; 4 : avertissements à lire ; 2 : refus à corriger.

4. **Créer la base** (une fois, avec le compte de service, ou un compte qui lui laisse l'écriture sur le dossier) :

```bat
C:\Python314\python.exe -m copie --config D:\Parametrage\production.jsonl --initialiser-base
```

La base n'est **jamais** créée automatiquement : sans elle, le moteur ne traite rien (si la base disparaît, rien n'est copié plutôt que de tout relivrer).

5. **Essai sans risque** :

```bat
C:\Python314\python.exe -m copie --config D:\Parametrage\production.jsonl --simulation
```

Affiche ce qui serait livré sans rien copier ni modifier.

## 5. Jenkins

Les quatre Jenkinsfile (transfert toutes les 5 minutes, sauvegarde et vérification nocturnes, purge) et la bibliothèque `journal-si` sont dans `jenkins\`. La mise en place pas à pas (agent étiqueté `copie-fichiers`, bibliothèque partagée, jobs *Pipeline*, nombre d'exécuteurs) est dans [08-jenkins](08-jenkins.md) §1 à §8.

Points à ne pas manquer :

- adapter les cinq valeurs de la section `environment` de chaque Jenkinsfile (`COPIE_PYTHON`, `COPIE_DEPOT`, `COPIE_CONFIG`, `COPIE_LOGS`, `COPIE_ENV`) ; `COPIE_LOGS` est le `dossier_logs` du paramétrage (par défaut `logs` à côté de la base) ;
- **ne pas** désactiver les builds simultanés du job de transfert ;
- **la sauvegarde de la base est une condition de mise en production** : sans elle, une base perdue ferait relivrer en mode `copie` tous les fichiers encore présents dans les sources ;
- la purge (`Jenkinsfile.purge`) se lance d'abord **sans** `--appliquer`, jusqu'à ce que la liste ait été relue.

**Non testé dans votre Jenkins** (versions et modules à confirmer : [08-jenkins](08-jenkins.md) §8). Tests : J9-M du cahier.

## 6. Journaux, Alloy, Grafana

Le moteur écrit des fichiers JSON Lines dans `dossier_logs` ; la plateforme de surveillance les lit. Un exemple de configuration Alloy (non testé) est dans `exemples\alloy\copie_fichiers.alloy`, un exemple de sortie dans `exemples\journal\`. Les tableaux de bord et la configuration Alloy relèvent de l'équipe de la plateforme de surveillance. Le journal de l'interface (`Journal.Dossier`, §7) peut être lu de la même façon.

## 7. L'interface de gestion

### 7.1 Poste ou serveur

L'interface (dossier `Gui\`) tourne sur le serveur d'exécution **ou** sur le poste d'un administrateur. Copier le dossier `Gui\` à l'endroit voulu (elle n'a aucune dépendance à installer ; elle lit le moteur par ses commandes JSON).

### 7.2 Configuration

Éditer `Gui\Gestion-Copie.config.psd1` (les lignes `# A ADAPTER`). Une clé inconnue est refusée, comme dans le moteur.

| Clé | À renseigner |
|---|---|
| `Acces.GroupesAdmin` | Le groupe AD des administrateurs (`DOMAINE\Groupe` ou SID). **Obligatoire** : sans groupe, l'interface refuse de démarrer |
| `Moteur.Mode` | `Local` : le moteur est sur la même machine que l'interface. `Distant` : il est sur `Moteur.Serveur` |
| `Moteur.Python`, `Moteur.Racine` | Python 3.14 et dossier du dépôt **sur la machine qui exécute le moteur** (inutiles avec JEA) |
| `Moteur.ConfigurationJea` | Nom du point d'accès JEA (§8) ; vide : l'appel se fait avec le compte de l'administrateur |
| `Parametrage.PeriodeDeclencheurSec` | Période du déclencheur Jenkins (300 pour « toutes les 5 minutes ») |
| `Journal.Dossier` | Dossier du journal de l'interface (vide : pas de fichier) |

### 7.3 Lancement

```powershell
.\Gui\Lancer-GestionCopie.ps1 -DossierParametrage D:\Parametrage
```

Le script relance lui-même PowerShell en mode STA si nécessaire. Un message d'erreur s'affiche si la configuration est invalide ou si le dossier est introuvable.

### 7.4 Mode distant

Depuis un poste d'administrateur, avec `Moteur.Mode = 'Distant'` et `Moteur.Serveur` :

- **sans JEA** : l'interface appelle le moteur par `Invoke-Command` avec le compte de l'administrateur. **WinRM doit être activé** sur le serveur et le compte doit pouvoir s'y connecter. Les contrôles d'accès de « Vérifier le paramétrage » sont alors faits **avec le compte de l'administrateur**, pas avec celui de Jenkins ;
- **avec JEA** : voir §8.

Dans les deux cas, le chemin du fichier de paramétrage transmis au moteur est celui que voit l'interface : il doit donc être **valable aussi sur le serveur** (un partage UNC visible des deux côtés, ou le même dossier).

**À confirmer sur le serveur** : J10A-M09, J10B-M11, J10C-M10.

## 8. Point d'accès JEA (facultatif, recommandé en mode distant)

JEA évite de donner aux administrateurs un accès complet au serveur : la session ne permet que la fonction `Invoke-CopieMoteurJea`, qui n'accepte que les commandes du contrat du moteur, sur les fichiers du dossier de paramétrage, avec le compte de service. Le compte tracé reste celui de l'administrateur. Détail dans [04-frontend](04-frontend.md) §6.

1. Sur le serveur d'exécution, **en administrateur** (invite PowerShell élevée) :

```powershell
.\Gui\Installer-PointAccesJea.ps1 -GroupeAdmin 'DOMAINE\GG_Copie_Admins' -Python C:\Python314\python.exe -Racine D:\Scripts\copie_fichiers -DossierParametrage '\\SERVEUR\Parametrage' -CompteService 'DOMAINE\gmsa-copie$' -WhatIf
```

puis sans `-WhatIf`. Options : `-GroupeLecture` (membres qui ne peuvent que consulter), `-Nom` (par défaut `CopieFichiers`), `-DelaiMaxSec`, `-DossierTraces`.

2. **Compte d'exécution** : le compte virtuel (si `-CompteService` est absent) est **local au serveur** : il ne peut pas utiliser les droits du compte de service de Jenkins sur les partages réseau. Pour cela, utiliser un **compte de service géré** (`DOMAINE\gmsa-copie$`), déjà installé sur le serveur (`Install-ADServiceAccount`).
3. **`-DossierParametrage` doit être écrit exactement comme l'interface le voit** (même chemin UNC ou même lecteur) : le point d'accès refuse tout fichier dont le chemin n'est pas dans ce dossier, sans chercher d'équivalence entre `D:\Parametrage` et `\\SERVEUR\Parametrage`.
4. Dans `Gestion-Copie.config.psd1` : `Moteur.Mode = 'Distant'`, `Moteur.Serveur = 'SERVEUR'`, `Moteur.ConfigurationJea = 'CopieFichiers'`.
5. Les sessions sont transcrites dans `%ProgramData%\CopieFichiers\Jea` (qui a lancé quoi).

Pour **modifier** le point d'accès (groupe, chemins), relancer le script : il remplace le module, la configuration et l'enregistrement. Pour le retirer : `Unregister-PSSessionConfiguration -Name CopieFichiers` puis supprimer `C:\Program Files\WindowsPowerShell\Modules\Copie.Jea`.

> **Jamais essayé dans une vraie session JEA** : le module est testé en l'appelant directement. Tests à jouer : J10E-M01 à M08 du cahier. Surveiller en particulier le point 3 et le fonctionnement du compte de service géré.

## 9. Vérification finale

| # | Vérification | Résultat attendu |
|---|---|---|
| 1 | `controle_serveur.py` et `lancer_tests.ps1` sur le serveur | Tout en succès |
| 2 | `--verifier` (complet, compte de service) | Code 0 ou 4 expliqué |
| 3 | `--etat --format json` | Une règle par ligne du fichier, statut `JAMAIS_LANCEE` |
| 4 | Job de transfert lancé à la main avec `--simulation`, puis réellement sur une règle d'essai | Fichier livré, statut `SUCCES`, ligne `debut_job`/`fin_job` dans le journal |
| 5 | Interface ouverte par un administrateur, puis par un non-administrateur | Badge « ADMINISTRATEUR » puis « LECTURE SEULE » ; boutons d'édition masqués au second |
| 6 | Modification d'une règle depuis l'interface | Une version et sa fiche `.meta.json` dans `versions\` |
| 7 | Sauvegarde de la base | Un fichier de sauvegarde par nuit |
| 8 | Journaux dans Grafana | Les événements du lancement apparaissent |

## 10. Exploitation courante

- **Sauvegarde** : la base (job nocturne) et le dossier de paramétrage avec ses `versions\` (sauvegarde du serveur de fichiers).
- **Purge** : voir le guide utilisateur (§ « Purger ») et `Jenkinsfile.purge`.
- **Mise à jour du moteur** : remplacer le contenu du dépôt (le paramétrage et la base ne sont pas dans le dépôt), relancer `lancer_tests.ps1`, puis `--verifier`. Le contrat JSON est numéroté (`version_contrat`) : [07-contrat-moteur-frontend](07-contrat-moteur-frontend.md) §6.
- **Mise à jour de l'interface** : remplacer le dossier `Gui\` en gardant `Gestion-Copie.config.psd1`. Si le moteur est plus ancien que l'interface, certains champs peuvent manquer (par exemple la liste des livraisons incertaines) : mettre le moteur à jour en premier.
- **Retour arrière** : règle par règle, voir [09-migration-et-recette](09-migration-et-recette.md) §4, étape 6.
- **Fin de support** de Windows Server 2016 : 12 janvier 2027.

## 11. Problèmes fréquents

| Symptôme | Cause probable | Action |
|---|---|---|
| L'interface refuse de démarrer, « groupe » | `Acces.GroupesAdmin` vide ou groupe introuvable | Renseigner le groupe (`DOMAINE\Groupe` ou SID) |
| « LECTURE SEULE » alors qu'on est administrateur | Session ouverte avant l'ajout au groupe AD | Fermer la session Windows et la rouvrir (le jeton est lu à l'ouverture) |
| « État indisponible » dans le bandeau | Base non initialisée, moteur injoignable ou ancien | Lire le message ; `--initialiser-base` ; vérifier `Moteur.*` |
| Les accents s'affichent mal dans la console Jenkins | Encodage de l'agent | Démarrer l'agent avec `-Dfile.encoding=UTF-8` ([08-jenkins](08-jenkins.md) §6) |
| JEA : « fichier de paramétrage hors du dossier autorisé » | Chemin différent de celui configuré (UNC contre lecteur) | Réinstaller avec le chemin tel que l'interface le voit |
| JEA : « commande réservée aux administrateurs » | Appelant hors du groupe administrateur | Normal pour un lecteur ; sinon vérifier `-GroupeAdmin` |
| `--verifier` réussit depuis l'interface mais le job échoue | Contrôle fait avec le compte de l'administrateur | Utiliser JEA avec le compte de service, ou lancer `--verifier` en tant que compte de service |
