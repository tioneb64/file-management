# Front-end de gestion

Application **PowerShell 5.1** (Windows Server 2016) pour gérer le paramétrage et suivre l'état des règles. Son aspect graphique reprend celui du projet de gestion des clusters Hyper-V : **les maquettes seront fournies** et complétées dans ce document. Ce document décrit les fonctions, les règles et les échanges avec le moteur, pas l'aspect visuel.

## 1. Principes

1. **Une seule logique de validation, celle du moteur.** Le front-end fait les contrôles de saisie simples (champ vide, format d'heure, nombre) ; pour tout le reste il appelle `file_management.py --verifier` et affiche les codes renvoyés. Il ne peut donc jamais accepter ce que le moteur refuserait.
2. **Le front-end n'ouvre jamais la base.** Il lit l'état et déclenche les actions par des commandes du moteur.
3. **Droits.** Membre du groupe d'administrateurs AD : modification. Les autres : consultation de la configuration et de l'état.
4. **Le fichier de paramétrage n'est jamais écrit à moitié** : écriture dans un temporaire puis renommage.
5. **Toute action est tracée** (compte, heure, commentaire).

## 2. Lancement et configuration

Le **dossier de paramétrage** n'est écrit nulle part : il est passé au lancement.

```powershell
.\Lancer-GestionCopie.ps1 -DossierParametrage D:\Parametrage
```

Le reste est dans `Gestion-Copie.config.psd1`, à côté de l'application (fichier de données PowerShell, jamais exécuté ; une clé inconnue est refusée, comme dans le moteur) :

| Section | Clés | Rôle |
|---|---|---|
| `Acces` | `GroupesAdmin` | Groupes dont les membres modifient (`DOMAINE\Groupe`, nom sans domaine ou SID). **Obligatoire** : sans groupe, l'outil refuse de démarrer (jamais d'accès ouvert par défaut) |
| `Moteur` | `Mode`, `Python`, `Racine`, `Serveur`, `ConfigurationJea`, `DelaiMaxSec` | Où et comment le moteur est lancé (§6) |
| `Parametrage` | `Filtre`, `VersionsSupportees`, `DossierVersions`, `DossierBrouillons`, `PeriodeDeclencheurSec` | Fichiers lus dans le dossier, versions du format d'en-tête acceptées, sous-dossier des anciennes versions, sous-dossier des brouillons vérifiés avant enregistrement (le compte de service doit pouvoir le lire), période du déclencheur Jenkins (contrôle P02) |
| `Journal` | `Dossier` | Journal de l'outil (JSON Lines, un fichier par jour, lu par Alloy) ; vide = pas de fichier |

Le front-end peut tourner **sur le serveur d'exécution ou sur un autre poste** : seuls `Moteur.Mode` et `Moteur.Serveur` changent. Il ne contient aucun lien vers Grafana : les journaux vont dans Loki et Grafana les interroge de son côté.

## 3. Environnements

- Au démarrage, le front-end **parcourt `dossier_parametrage`** et charge chaque fichier `*.jsonl`. Il lit la première ligne (en-tête) de chacun.
- **Un onglet par environnement**, nommé d'après l'en-tête.
- **Moteur introuvable** (mode Local) : `Resolve-CopieMoteurLocal` vérifie `Moteur.Python` et `Moteur.Racine` ; s'ils n'existent pas, il cherche `python.exe` (PATH hors faux lanceurs du Windows Store, puis `py -3`) et le dépôt au-dessus du module, pose **une question**, et corrige la configuration **en mémoire** pour la session si l'utilisateur accepte. Sinon l'interface s'ouvre avec un avertissement et chaque appel du moteur dit quelle clé corriger.
- **Dossier absent** : un administrateur se voit proposer de le créer (jamais sans réponse), un autre compte reçoit un message qui nomme le groupe administrateur. **Dossier vide** : écran « aucun environnement » avec, pour un administrateur, la création du premier environnement proposée d'office.
- Contrôles à l'ouverture : deux fichiers qui déclarent le même environnement, un environnement différent du nom du fichier, une version de format inconnue. Un fichier non supporté est affiché en lecture seule avec un message.

## 4. Fonctions

### 4.1 Consultation

| Fonction | Détail |
|---|---|
| Liste des règles | `id`, description, mode, source → cible, planification en clair (« toutes les 5 min de 05:00 à 19:00, lun-ven »), actif, statut, dernier lancement, prochain créneau. Filtres : statut, mode, texte, actif |
| Détail d'une règle | Tous les champs en lecture, regroupés (sélection, planification, dépendances, réactions, programmes) |
| Graphe des dépendances | Règles et flèches « attend », colorées par statut ; une règle `BLOQUEE` indique la règle bloquante |
| État | Valeurs de `--etat` : statut, motif, dernière erreur, dernier succès, fichiers livrés, actions en attente, `archivage_degrade`, flag de reprise |
| Historique des modifications | Versions du fichier de paramétrage : qui, quand, différences |

Réalisation (étape D) :

- **Graphe** : onglet « Dépendances » sous la grille. Colonnes de gauche à droite : une règle est toujours à droite de celles dont elle dépend ; la flèche va de la règle attendue vers celle qui attend. Seules les règles liées sont dessinées (le nombre des autres est indiqué). Couleur du nœud = statut du moteur, pointillé estompé = règle inactive, infobulle avec le motif d'attente. Une règle `EN_ATTENTE` ou `BLOQUEE` dont le motif nomme une de ses dépendances a cette flèche en rouge (le moteur ne renvoie la règle bloquante que dans ce texte). Un clic sur un nœud sélectionne la règle. Les dépendances inconnues sont signalées (refus D01 du moteur).
- **Historique** : bouton « Historique… » (tous les comptes qui peuvent lire le dossier des versions). Une ligne par enregistrement de l'interface (date, compte, commentaire, lus dans la fiche `.meta.json` ; à défaut, dans le nom du fichier). Le fichier versionné est l'état d'**avant** : les différences d'une ligne sont calculées entre cette version et la suivante (ou le fichier actuel pour la plus récente). Les règles sont rapprochées par identifiant (un déplacement n'est pas une modification), les règles modifiées sont comparées champ par champ, l'en-tête aussi. Les avertissements acceptés à l'enregistrement sont rappelés. **Restauration** : pour un administrateur dont l'environnement est modifiable, le bouton « Revenir à l'état d'avant cette modification… » relit la version choisie, annonce le nombre de différences avec le fichier actuel puis la réécrit par l'enregistrement sécurisé du §5 (vérification du moteur avec comparaison au fichier actuel, donc avertissements V0x si une règle disparaît ; commentaire obligatoire ; copie de l'état actuel dans les versions). Rien n'est effacé : la restauration est une ligne de l'historique et s'annule de la même façon.

### 4.2 Modification (administrateurs)

| Fonction | Détail |
|---|---|
| Ajouter / dupliquer / modifier une règle | Formulaire regroupant les champs de [01-parametrage](01-parametrage.md), valeurs de secours préremplies |
| Activer / désactiver | Refusé si des règles actives en dépendent (D03) |
| Supprimer | Avertissement V02 ; l'état reste en base |
| Réordonner | Tri automatique : une règle dépendante est toujours placée **après** ses dépendances |
| Promouvoir | Copier une règle validée d'un environnement vers un autre, en adaptant les chemins : choix de la cible, remplacement d'un texte dans les dossiers et dans la commande des programmes (littéral, sans tenir compte de la casse, aperçu avant/après), avertissement si la règle existe déjà dans la cible (elle est remplacée) ou si ses dépendances n'y existent pas. La règle adaptée s'ouvre ensuite dans le **formulaire de la cible** puis suit exactement l'enregistrement sécurisé du §5 (vérification du moteur, commentaire, version précédente) : la promotion ne contourne aucun contrôle |

Aides à la saisie : durées en unités lisibles à l'écran (converties en `_sec` à l'enregistrement), planification en sélecteurs, masques en liste, variables de date disponibles en liste, dépendances choisies parmi les règles existantes.

### 4.2 bis Gestion des environnements (administrateurs)

| Fonction | Détail |
|---|---|
| Créer | Nom (`^[a-z0-9_-]{1,32}$`), base locale complète (E04, E05), dossiers, parallélisme, rétentions ; refus d'un nom, d'un fichier, d'une base ou d'un dossier de travail déjà utilisés ; fichier sans règle, vérifié par le moteur (`--verifier --syntaxe-seule`) avant d'être placé ; `--initialiser-base` ensuite (une base existante n'est pas une erreur) |
| Modifier l'en-tête | Même pipeline que l'enregistrement d'une règle (§5) |
| Renommer | Fichier + en-tête + nom dans la base (`--renommer-environnement ANCIEN`, refusé si une règle est en cours) + préfixe des versions de l'historique. Le nouveau fichier est placé avant le renommage de la base ; si le moteur refuse, il est retiré et rien n'a changé. Une base absente n'empêche pas le renommage. Le nom ne se change pas en même temps que le reste |
| Copier | Nouvel environnement avec toutes les règles (écrites telles quelles, `actif = false` par défaut), même en-tête sauf nom, base, dossiers de logs et de travail |
| Supprimer | Double validation (avertissement, puis saisie du nom exact + commentaire). Le fichier, ses versions et une fiche vont dans `Parametrage.DossierSupprimes` (`.supprimes`) ; **base, journaux et archives intacts** ; refusé si une règle est en cours ou si l'état n'est pas lisible |

**Dossiers techniques (base, journaux, travail).** Après l'écriture du fichier et avant la création de la base, `Invoke-CopieQuestionDossiers` contrôle les trois dossiers par `Invoke-CopieDossiersEnvironnement` (PowerShell, pas le moteur Python : une création de dossier n'a rien de propre au moteur). Les chemins sont lus dans l'en-tête du fichier ; vides, ils valent `logs` et `travail` à côté de la base (comme le moteur). Local : dans le processus de l'interface ; Distant : `Invoke-Command` sur le serveur ; JEA : `Invoke-CopieDossiersJea` du point d'accès (lecture libre, création réservée au groupe administrateur, aucun chemin fourni par l'appelant). Un dossier absent est créable si son plus proche parent existant accepte l'écriture (fichier d'essai créé puis supprimé). **Une seule question** liste les dossiers à créer ; refus = fichier créé, base non créée. Appelé par la création, la copie, la modification et « Créer la base… ».

Toutes ces fonctions exigent le profil Admin dans l'interface **et** les droits NTFS d'écriture sur le dossier. Par JEA, `--initialiser-base`, `--renommer-environnement` et `--creer-dossiers-regle` sont des commandes d'écriture (groupe administrateur).

### 4.2 quater Racines, modes et affichage

- **Racines.** La boîte « Environnement » demande la *racine de l'environnement*, la *racine des sources* et la *racine des cibles* (toutes facultatives, `\` final facultatif) et affiche les **chemins complets** tels que le moteur les utilisera. Un chemin partiel se place sous la racine, un chemin complet est conservé. Les mêmes chemins complets apparaissent dans la grille, le détail d'une règle (avec la saisie entre parenthèses quand elle diffère), les messages et la simulation (`Private/Chemins.ps1`, même règle que `resoudre_chemin` du moteur). À la copie d'un environnement, seule la racine change.
- **Modes.** Le formulaire propose `copie`, `deplacement`, `archivage`, `suppression`, `count`, `size` ; la cible n'est exigée que pour les trois premiers ; les seuils concernent `count` et `size`. Un avertissement de suppression définitive est affiché à l'enregistrement. La simulation décrit la suppression (« supprimera DÉFINITIVEMENT N fichier(s) ») et la mesure (résultat, ATTENTE ou succès).
- **Filtres de la fenêtre principale.** Statut : tous les statuts possibles, y compris `ERREUR`, `WARNING`, `ATTENTE`, `EN_COURS`, `BLOQUEE`, même quand aucune règle n'y est ; mode : les six modes ; règles : toutes / actives / inactives.
- **Couleurs des lignes.** Grise : règle inactive ; rouge : dernier lancement en erreur, règle arrêtée ou bloquée (l'inactive prime) ; bleu ciel : ligne sélectionnée (la sélection prime).

### 4.2 ter Contrôle des répertoires et simulation

**Règle d'affichage (toute l'interface).** Une boîte de message Oui / Non par *demande* (accord, confirmation). Les informations, avertissements et erreurs d'une même opération sont rassemblés dans **une seule fenêtre de résultat** (`Show-CopieResultat`, `Dialog.Resultat.xaml`), comme le résultat de « Vérifier le paramétrage » : gravité colorée, sujet, message. Appliqué au contrôle des répertoires après l'enregistrement d'une règle, à la création des dossiers manquants et à toutes les opérations sur les environnements (création, copie, modification, base, renommage, suppression) : les étapes notent leurs messages dans un collecteur (`Add-CopieLigneOperation`) et l'opération n'ouvre qu'une fenêtre à la fin (`Show-CopieOperation`). Seuls restent en boîte « OK » les arrêts immédiats d'un seul message (environnement en lecture seule, fichier modifié depuis son affichage, fichier illisible) et la correction d'une saisie de formulaire.

- Après l'enregistrement d'une règle : `--controler-regle ID` (sans base) renvoie, pour la source, la cible, le dossier temporaire et l'archive : existence, lecture, écriture (essai réel d'un fichier temporaire), possibilité de création d'un dossier absent, espace pour la cible et l'archive. Les problèmes sont affichés ; les dossiers absents créables (source comprise) peuvent être créés par `--creer-dossiers-regle ID --utilisateur U` (tracé dans le journal du moteur).
- « Simuler la règle… » : `--lancer-regle ID --simulation` donne la liste des fichiers (`apercu`, plafonnée à 500) et les contrôles de répertoires avec l'espace nécessaire (volume à livrer + marge). Par JEA, la simulation est une commande de **lecture** : le point d'accès exige `--simulation` et ne lance jamais de transfert réel.
- Ces contrôles s'exécutent avec le compte du moteur (le vôtre, celui du serveur ou le compte de service du point d'accès JEA).

### 4.3 Actions d'exploitation (administrateurs)

| Action | Commande du moteur | Confirmation |
|---|---|---|
| **Reprise** | `--reprise ID` | Affiche les règles de la chaîne qui repartiront |
| **Lancer maintenant** | `--lancer-maintenant ID` | Oui |
| **Acquitter** | `--acquitter ID` | Commentaire obligatoire |
| **Débloquer** | `--debloquer ID --utilisateur U` | Oui, avertit que l'arbre de processus sera arrêté et qu'une reprise sera ensuite nécessaire |
| **Purger** | `--purger [--regle ID]` puis `--purger --appliquer` | Liste d'abord (type, règle, date, taille, chemin), suppression seulement après le clic sur « Purger » ; peut se limiter à la règle sélectionnée |

Réalisation (étape C) :

- Les boutons d'exploitation sont visibles pour les administrateurs dont le fichier est lisible (y compris un environnement en lecture seule pour l'édition : ces actions ne modifient pas le paramétrage). Reprise, lancement, acquittement et déblocage exigent une règle sélectionnée ; le compte de l'administrateur est transmis au moteur (`--utilisateur`) et tracé dans la base, le journal du moteur et le journal de l'interface.
- La confirmation de la **reprise** liste les règles qui dépendent de la règle reprise, de proche en proche : elles repartent d'elles-mêmes dès que leurs dépendances sont remplies ([02-moteur](02-moteur.md) §3). Le commentaire est facultatif pour la reprise et le déblocage, obligatoire pour l'acquittement.
- Un refus du moteur (règle en cours, règle qui ne tourne pas...) est affiché tel quel, rien n'est modifié.
- **Exécution en arrière-plan** : la vérification complète et la purge (liste puis suppression) s'exécutent dans un espace d'exécution distinct ; la fenêtre reste utilisable, les boutons de l'onglet concerné sont grisés et la barre d'état indique l'opération. Les commandes qui se contentent de poser un drapeau (reprise, lancement, acquittement, déblocage) restent synchrones. Le chargement de l'état à l'ouverture et le bouton « Actualiser l'état » sont aussi en arrière-plan : la liste des règles du fichier s'affiche tout de suite (sans état, message « État en cours de lecture… »), puis le statut arrive quand le moteur a répondu et la règle sélectionnée est resélectionnée ; une réponse qui arrive après la reconstruction des onglets est ignorée. Après une action (enregistrement, reprise…), la relecture reste synchrone : la suite (vérification proposée, nouvelle action) a besoin d'une vue prête.
- « Actualiser l'état » relit le fichier et l'état des règles ; il n'y a toujours aucune interrogation automatique (§6).
- **Livraisons incertaines** : une livraison dont le programme s'est arrêté pendant la copie est « de résultat inconnu » et bloque la règle ([02-moteur](02-moteur.md)). Le bouton « Trancher… » (actif quand la règle sélectionnée en a) ouvre la liste (source, cible, clé) fournie par `--etat` (champ `incertains`) ; l'administrateur vérifie dans le dossier cible, choisit « bien arrivé » (`livre`) ou « à relivrer » (`a_relivrer`) et saisit un commentaire obligatoire, puis le front-end appelle `--trancher-incertain`. Une livraison à la fois ; après « à relivrer », la règle repart à la prochaine reprise.

## 5. Enregistrement du paramétrage

1. Au chargement, le front-end mémorise la date de modification et l'empreinte du fichier.
2. À l'enregistrement, il construit le fichier complet en mémoire : en-tête + une ligne par règle, triées.
3. Il l'écrit sous le **nom de l'environnement** (le moteur exige que le nom du fichier soit celui de l'environnement : E03) dans un sous-dossier de brouillons du même dossier (`.brouillons\<guid>`, paramètre `Parametrage.DossierBrouillons`), donc sur le même volume que le fichier à remplacer. Ce sous-dossier est supprimé à la fin, réussite ou non.
4. Il appelle `--verifier --syntaxe-seule --precedent <fichier actuel> --format json` sur ce temporaire : le moteur fait les contrôles de syntaxe **et** la comparaison avec la version chargée (V01 à V04). Un **refus** annule l'enregistrement et affiche les codes ; les **avertissements** sont présentés pour confirmation.
5. *(supprimé : la comparaison V01 à V04 est faite par le moteur, étape 4.)*
6. **Contrôle d'édition simultanée** : si le fichier a changé depuis le chargement, l'enregistrement est refusé et le fichier est rechargé.
7. Il copie la version précédente dans `dossier_versions` (`production_20261103_101500_DOMAINE_benoit.jsonl`) et écrit à côté une fiche `.meta.json` : compte, date (UTC), **commentaire (obligatoire)**, empreintes avant et après, avertissements acceptés.
8. Il remplace le fichier par `[System.IO.File]::Replace` (atomique ; le fichier n'est jamais écrit à moitié). L'empreinte est recontrôlée juste avant le remplacement.
9. Il propose de lancer `--verifier` complet (accès) sur le serveur d'exécution.

Le formulaire ne recopie ni les valeurs de secours ni les listes de valeurs : il les demande au moteur (`--modele-regle`, [07-contrat-json](07-contrat-json.md)). Un champ absent du fichier prend la valeur de secours du moteur ; le front-end écrit toujours le réglage complet de la règle. Après un refus du moteur ou des avertissements non acceptés, le formulaire se rouvre avec la saisie. Avant toute action, le fichier est relu : s'il a changé depuis son affichage, la vue est rechargée et l'action abandonnée.

Écriture du fichier en PowerShell 5.1 :

- UTF-8 **sans BOM** : `[System.IO.File]::WriteAllText($chemin, $texte, (New-Object System.Text.UTF8Encoding $false))` (`Set-Content -Encoding UTF8` ajoute un BOM, accepté par le moteur mais inutile ; `Out-File` écrit en UTF-16 par défaut).
- `ConvertTo-Json -Compress -Depth 10` pour chaque règle : sans `-Depth`, les objets imbriqués (`planification`, `situations`, `programmes`) sont tronqués à deux niveaux.
- `ConvertTo-Json` de PowerShell 5.1 échappe `<`, `>`, `&` et `'` en `\uXXXX` : valide en JSON, le moteur le relit correctement.
- Les valeurs `null`, les booléens et les entiers conservent leur type ; tester `[int]` et `[bool]` sur les champs saisis en texte.
- Piège 5.1 : `$(if ($x) { $tableau })` et `$v = if …` **aplatissent** les tableaux d'un ou de zéro élément (`[1]` devient `1`, `[]` devient `{}`) : les affectations se font dans les branches.
- `[System.IO.File]::Replace($a, $b, $null)` échoue en 5.1 (le `$null` devient une chaîne vide) : passer `[NullString]::Value`.

## 6. Communication avec le moteur

Le format exact des échanges (commandes, champs JSON, codes retour) est le **[contrat moteur / front-end](07-contrat-moteur-frontend.md)**.

Le front-end exécute le moteur sur le serveur d'exécution, **avec le compte de l'administrateur connecté** pour les actions tracées :

```powershell
Invoke-Command -ComputerName $cfg.serveur_execution -ScriptBlock {
    param($py, $script, $conf)
    & $py $script --config $conf --etat --format json
} -ArgumentList $cfg.python, $cfg.script, $fichierConf
```

- Sortie JSON UTF-8, lue avec `ConvertFrom-Json`. Les codes retour du moteur sont interprétés : 0, 1 (anomalies déjà dans le JSON), 2 (erreur de configuration).
- Sur le serveur d'exécution lui-même : exécution locale directe.
- Deux façons d'atteindre le moteur à distance, au choix de la configuration (`Moteur.Mode = 'Distant'`) :
  - **Compte de l'administrateur** (`ConfigurationJea` vide) : `Invoke-Command` avec le compte connecté. Convient aux personnes de la DSI. Les accès aux dossiers (`--verifier` complet) sont alors contrôlés **avec ce compte**, pas avec le compte de service : un contrôle réussi ne prouve rien pour Jenkins.
  - **Point d'accès JEA** (`ConfigurationJea` renseignée) : la session n'expose que la fonction `Invoke-CopieMoteurJea -Argument <string[]> -Fichier <chemin>` ; le point d'accès ajoute lui-même `--config` et `--format json`, choisit Python et le dossier du moteur, refuse toute commande hors de la liste du contrat ([07 §4](07-contrat-moteur-frontend.md)) et s'exécute sous le compte de service (compte virtuel ou géré) : les contrôles d'accès reflètent alors ce que Jenkins pourra faire. La fonction renvoie `Code`, `Sortie` (le JSON du moteur) et `Erreur`.
    - Réalisation (étape E) : module `Gui\Jea\FileManagement.Jea` (fonction, grammaire, configuration), rôle de capacité `FileManagement.psrc`, installation par `Installer-PointAccesJea.ps1` (`-WhatIf` pour voir). **Grammaire stricte** : seules les commandes du contrat que le front-end utilise sont permises (`--etat`, `--verifier`, `--modele-regle`, `--reprise`, `--lancer-maintenant`, `--acquitter`, `--debloquer`, `--purger`, `--trancher-incertain`), chacune avec ses seules options ; ni `--initialiser-base`, ni `--sauvegarder-base`, ni lancement. Les valeurs sont contrôlées par type (identifiant de règle, clé hexadécimale, décision…) et transmises sous la forme `--option=valeur` : une valeur ne peut pas passer pour une option. Le fichier de paramétrage (et `--precedent`) doit être dans le dossier de paramétrage configuré (chemin normalisé, `..` n'échappe pas). **Le compte tracé est celui qui a ouvert la session** (`$PSSenderInfo`), jamais le `--utilisateur` annoncé par le poste. Les commandes d'écriture exigent l'appartenance au groupe administrateur de la configuration, vérifiée dans la session ; les autres membres du rôle ne peuvent que consulter. Les sessions sont transcrites (qui a lancé quoi).
    - Compte d'exécution : le compte virtuel est **local au serveur** ; pour accéder aux partages réseau avec les droits du compte de service de Jenkins, installer avec `-CompteService 'DOMAINE\gmsa-copie$'` (compte de service géré déjà installé sur le serveur).
- Pas d'interrogation automatique plus fréquente que toutes les 30 secondes ; bouton d'actualisation manuel.

## 7. Sécurité

| Sujet | Règle |
|---|---|
| Qui est administrateur | Appartenance du compte Windows courant au groupe `groupe_admin_ad` (`[Security.Principal.WindowsPrincipal]::IsInRole`). Résultat affiché en haut de l'écran |
| Contournement | La restriction du front-end ne protège rien seule : les droits d'écriture du dossier de paramétrage et du point de terminaison d'exécution distante doivent aussi être limités au même groupe |
| Programmes | Qui modifie `programmes` fait exécuter un programme par le compte de service. Le formulaire affiche un avertissement et la modification est tracée |
| Secrets | Aucun mot de passe ni jeton dans les champs du paramétrage |

## 8. Réalisation par étapes

L'application est dans `Gui\` (même organisation que l'outil de gestion du cluster Hyper-V : module `FileManagement.Gui` avec `Private`, `Public`, `Views`, vues XAML dans `Gui\Xaml`, styles repris à l'identique). Quatre étapes (A à D), chacune validée avant la suivante, puis une étape de compléments (E) :

| Étape | Contenu | État |
|---|---|---|
| **A** | Fenêtre, contrôle des droits AD, onglets par environnement, liste des règles (filtres), détail, état (`--etat`), vérification (`--verifier`), journal, `Initialiser-DossierParametrage.ps1` | faite |
| **B** | Formulaire d'édition (ajouter, dupliquer, modifier, activer / désactiver, supprimer), tri automatique, enregistrement sécurisé (§5 : vérification, contrôle d'édition simultanée, versions avec fiche et commentaire, remplacement atomique) | faite |
| **C** | Actions d'exploitation (§4.3 : reprise, lancement, acquittement, déblocage), purge (`--purger`), exécution en arrière-plan de la vérification et de la purge, « Actualiser l'état » | faite |
| **D** | Graphe des dépendances, promotion d'un environnement à l'autre, historique des versions | faite |
| **E** | Compléments : point d'accès JEA, écran des livraisons incertaines, état lu en arrière-plan, restauration d'une version | faite |
| **F** | Dossier de paramétrage absent ou vide, gestion des environnements (créer, modifier / renommer, copier, créer la base, supprimer), simulation d'une règle, contrôle des répertoires après enregistrement | faite (non rejouée sur le serveur) |

Dossier protégé : `Initialiser-DossierParametrage.ps1 -Dossier … -GroupeAdmin … -CompteService …` crée le dossier et son sous-dossier de versions, coupe l'héritage et pose : administrateurs en modification, compte de service Jenkins en **lecture seule** (le moteur ne l'écrit jamais), aucun accès du compte de service aux versions. Il demande confirmation (`-WhatIf` pour voir), et refuse de s'appliquer si le compte qui le lance n'est pas dans le groupe (il se couperait l'accès).

## 9. Tests

- Jeu de fichiers de paramétrage valides et invalides (un par code de validation) vérifiant que le front-end affiche le code attendu.
- Tests Pester (module PowerShell) sur la lecture / écriture JSON (profondeur, encodage, types) et sur la construction des commandes.
- Recette sur Windows Server 2016 avec PowerShell 5.1, y compris l'exécution distante.

## 10. À fournir

| Élément | De qui |
|---|---|
| Maquettes des écrans (style du projet de gestion des clusters Hyper-V) | Responsable applicatif |
| Nom du groupe AD, serveur d'exécution, partage du paramétrage | Responsable applicatif |
