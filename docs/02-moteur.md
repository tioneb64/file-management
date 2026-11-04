# Moteur

Le moteur est le programme Python `copie_fichiers.py` (lanceur léger) et son package. Il évalue les règles d'un environnement et exécute celles qui sont à lancer.

## 1. Ligne de commande et codes retour

```bat
python copie_fichiers.py --config D:\Parametrage\production.jsonl [options]
```

| Commande / option | Rôle |
|---|---|
| *(aucune commande)* | **Lancement** : orchestrateur, évalue et exécute les règles à lancer |
| `--regle ID` (répétable) | Limite le lancement aux règles indiquées |
| `--simulation` | Affiche ce qui serait fait : aucune copie, aucune écriture en base (ouverte en lecture seule), planification ignorée, programmes non appelés (sauf `--simulation-programmes`, qui leur transmet `COPIE_SIMULATION=1`) |
| `--verifier [--syntaxe-seule] [--periode-declencheur-sec N] [--format json]` | Validation du paramétrage et des accès. Voir le §7 de [01-parametrage](01-parametrage.md). `--periode-declencheur-sec` permet le contrôle P02 |
| `--initialiser-base` | Crée la base d'un nouvel environnement. **La base n'est jamais créée automatiquement** |
| `--etat [--regle ID] [--format json]` | État des règles (lecture de la base) |
| `--reprise ID --utilisateur U [--commentaire C]` | Pose le flag de reprise (§10) |
| `--lancer-maintenant ID --utilisateur U` | Lance la règle au prochain lancement, sans programme de reprise |
| `--acquitter ID --utilisateur U --commentaire C` | Considère la règle comme corrigée, sans la relancer. Le commentaire est obligatoire |
| `--debloquer ID --utilisateur U` | Arrête une exécution bloquée et libère le flag « en cours » |
| `--executer-regle ID --execution-id N` | **Interne** : exécution d'une règle dans un processus fils |
| `--sauvegarder-base DOSSIER` | Sauvegarde cohérente de la base (API de sauvegarde SQLite) |
| `--migrer-ancien conf [historique]` | Convertit un ancien `copies.conf` (et son historique) en fichier de paramétrage et en entrées de base |
| `--essais`, `--delai`, `--retention`, `-v` | Options du script actuel : supprimées ou remplacées par le paramétrage |

| Code | Signification | Statut Jenkins |
|---|---|---|
| `0` | Aucune anomalie, ou uniquement des messages `INFO` | SUCCESS |
| `1` | Au moins une `ERREUR` pendant ce lancement | FAILURE |
| `2` | Paramétrage invalide, base absente ou inaccessible, arguments incorrects | FAILURE |
| `4` | Au moins un `WARNING`, aucune `ERREUR` | UNSTABLE |

L'ancien code 3 (« exécution déjà en cours ») disparaît : le verrou est **par règle**, et une règle déjà en cours est simplement ignorée par les autres lancements. Le code retour reflète les événements **de ce lancement** (décision à valider, voir le point 4 de la vue d'ensemble).

## 2. Orchestrateur

À chaque lancement :

1. **Charger et valider** le paramétrage (erreur : code 2, rien n'est lancé).
2. **Ouvrir la base**. Absente ou inaccessible : code 2, rien n'est lancé (G6). Synchroniser la table des règles : nouvelles règles ajoutées, règles retirées du fichier signalées en `WARNING`.
3. **Nettoyer les exécutions orphelines**, y compris celles des autres lancements, pour les règles dont le flag « en cours » est posé :
   - processus disparu (même serveur) : exécution terminée en `ERREUR`, situation `arret_anormal`, flag libéré ;
   - processus vivant mais `duree_max_sec` dépassée : application de `si_duree_depassee` (arrêt de **l'arbre** de processus, puis `erreur`, `relancer` ou `alerter`).
4. **Déterminer les règles à lancer** (§4) parmi les règles actives.
5. **Évaluer les dépendances** de ces règles (§3) : prête, `EN_ATTENTE` ou `BLOQUEE`.
6. **Lancer** les règles prêtes, chacune dans un processus fils, dans la limite de `parallele_max` (illimité par défaut). La prise du flag « en cours » est **atomique** : si un autre lancement l'a déjà prise, la règle est ignorée.
7. **Surveiller** les fils. À chaque fin d'exécution, ré-évaluer les règles qui l'attendaient : une chaîne 10 → 11 se déroule dans un seul lancement.
8. **Terminer** quand plus aucune règle n'est en cours ni lançable par ce lancement. Journaliser l'événement `fin_lancement` (compteurs par statut, code retour) et sortir.

Le fils écrit son résultat dans la base (table `executions`) et un petit fichier JSON dans `dossier_travail`. **C'est l'orchestrateur qui journalise la fin de chaque règle**, y compris quand le fils est mort sans rien écrire : aucune fin de règle ne passe inaperçue.

**Arrêt d'un arbre de processus** : les fils sont placés dans un *Job Object* Windows (via `ctypes`), ce qui garantit l'arrêt des programmes externes qu'ils ont lancés. À défaut : `taskkill /T /F /PID`. Détection d'un processus « vivant » : identifiant **et** date de création du processus (pour éviter qu'un identifiant réutilisé fasse croire qu'il tourne encore). Le nettoyage des orphelins ne concerne que les processus du même serveur (`hote`).

## 3. Dépendances et statuts

### 3.1 Statuts

| Statut | Sens | Stocké dans |
|---|---|---|
| `JAMAIS_LANCEE` | Aucune exécution | `dernier_statut` |
| `SUCCES` | Dernière exécution sans `ERREUR` ni `WARNING` | `dernier_statut` |
| `WARNING` | Dernière exécution terminée avec au moins un `WARNING` | `dernier_statut` |
| `ERREUR` | Dernière exécution en erreur, ou arrêtée | `dernier_statut` |
| `ACQUITTEE` | Erreur acquittée manuellement (§10) | `dernier_statut` |
| `EN_COURS` | Le flag « en cours » est posé | `en_cours` |
| `EN_ATTENTE` | Créneau dû mais une dépendance n'a pas encore tourné | `attente` |
| `BLOQUEE` | Créneau dû mais une dépendance est en `ERREUR` ou elle-même `BLOQUEE` ; le motif nomme la règle bloquante | `attente` |
| `INACTIVE` | `actif = false` (calculé depuis le paramétrage) | — |

Le statut d'une règle ne passe à `SUCCES` que par **une exécution réelle réussie**, ou à `ACQUITTEE` par un acquittement tracé. Un flag modifié à la main ne suffit pas.

### 3.2 Évaluation de la condition

Soit `R` la règle évaluée, `ref` la date de début de sa dernière exécution (0 si jamais lancée), et `D` chacune des règles de `apres`. Pour chaque `D` :

| Condition | Remplie si |
|---|---|
| `termine` | `D` a terminé au moins une exécution **après `ref`** |
| `succes` | La dernière exécution de `D` date d'**après `ref`** et son statut est `SUCCES`, `WARNING` ou `ACQUITTEE` |
| `fichiers` | Au moins une exécution de `D` après `ref` a livré un fichier |

Résultat pour `R` :

- **prête** : toutes les conditions sont remplies pour toutes les dépendances ;
- **`BLOQUEE`** : une dépendance a un statut `ERREUR` (ou est elle-même `BLOQUEE`). Le statut `ERREUR` n'est **pas** propagé : seule la cause reste en rouge ;
- **`EN_ATTENTE`** : sinon (une dépendance est en cours, ou n'a pas encore tourné depuis `ref`).

Une règle `BLOQUEE` ou `EN_ATTENTE` **garde son créneau**. Elle est ré-évaluée à chaque lancement et part dès que ses dépendances sont remplies, même si l'heure prévue est passée, dans la limite de `rattrapage_sec` (reprise en cascade). Quand une règle dont dépendent d'autres règles est reprise, toute la chaîne repart d'elle-même.

Le niveau `si_condition_non_remplie` est journalisé **une fois par créneau** (événement `regle_non_lancee`) et compte dans le code retour du lancement. Quand le créneau expire sans que la condition soit remplie, la règle repasse à son état précédent.

Une règle `apres_dependances` n'a pas d'horaire : elle est lancée dès que ses dépendances sont remplies depuis `ref`.

### 3.3 Précisions apportées par l'implémentation (J6)

Code : `copie/orchestrateur.py` (fils, parallélisme, durée maximale), `copie/dependances.py` (évaluation pure), `copie/processus.py` (Job Object, arrêt d'arbre).

- **Un processus par règle.** L'orchestrateur prend le drapeau et crée l'exécution **lui-même** (atomique), lance `python -m copie --config … --executer-regle ID --execution-id N` (commande interne), place le fils dans un **Job Object** puis lui envoie « go » sur son entrée standard : le fils ne commence rien avant d'être dans son job, donc aucun descendant n'échappe à l'arrêt. L'orchestrateur renseigne en base l'identifiant **et** la date de création du fils (détection d'un processus vivant, voir §2). La sortie du fils (lignes lisibles de la console) est celle de l'orchestrateur : elle apparaît dans la console Jenkins.
- **Résultat du fils** : écrit en base (`terminer_execution`) et dans `dossier_travail\resultat_<id>.json` (écriture atomique, supprimé après lecture). **L'orchestrateur journalise la fin de chaque règle** (`regle_terminee`) : à partir du JSON ; sinon de la ligne `executions` si le fils a écrit en base sans écrire le JSON ; sinon la règle passe en `ERREUR` (situation `arret_anormal`, exécution `ARRETEE`, drapeau libéré) et l'événement `arret_anormal` donne le code de sortie du fils.
- **Parallélisme** : `parallele_max` de l'en-tête (défaut : aucune limite). Les règles prêtes partent dans l'ordre du fichier. À chaque fin de fils, les règles en attente sont réévaluées : une chaîne 8 → 9 → 10 se déroule dans un seul lancement.
- **Durée maximale** (`duree_max_sec` depuis le démarrage du fils) : `erreur` → arrêt de l'**arbre** de processus (Job Object, sinon `taskkill /T /F`), exécution en `ERREUR`, situation `duree_depassee`, arrêt après erreur selon `apres_erreur` ; `relancer` → arrêt puis nouvelle exécution immédiate, au plus `relances_max` fois de suite (compteur `relances`, remis à zéro par toute fin normale), puis `ERREUR` ; `alerter` → on laisse tourner, un seul `WARNING` `duree_depassee`, l'exécution se termine en `WARNING` si elle réussit. Une exécution vivante d'un **autre lancement** (parallèle) qui dépasse sa durée est traitée de la même façon au démarrage du lancement suivant (arrêt par `taskkill /T`, car son Job Object n'appartient pas au nouvel orchestrateur).
- **Interruption** (arrêt du build Jenkins, Ctrl+C) : tous les fils et leurs descendants sont arrêtés, les drapeaux libérés, règles en `ERREUR` (`arret_anormal`). Le Job Object est configuré `KILL_ON_JOB_CLOSE` : si l'orchestrateur est tué brutalement, Windows arrête aussi les fils.
- **Dépendances** (`ref` = début de la dernière exécution de la règle, 0 si jamais lancée ; comparaisons strictes) : voir le tableau du §3.2. Une dépendance non remplie est `BLOQUEE` si elle est en `ERREUR` (et pas en cours) ou si elle est elle-même `BLOQUEE` ; sinon `EN_ATTENTE`. L'erreur n'est **pas** propagée : le statut de la règle bloquée reste inchangé, seul `attente` (+ motif) est renseigné. Une dépendance dont les conditions sont remplies n'est jamais bloquante, même en `ERREUR` (condition `termine`).
- **Règle sans horaire** (`apres_dependances`) : candidate à chaque lancement. Elle n'est signalée que lorsqu'elle passe en `BLOQUEE` ; l'attente d'une dépendance qui n'a pas encore tourné est un état normal, sans avertissement.
- **Règle horaire avec `apres`** : l'état d'attente n'est mémorisé et journalisé (`regle_non_lancee`, niveau `si_condition_non_remplie`) qu'**à la fin du lancement**, si la règle n'a pas pu partir malgré les réévaluations, et **une seule fois par créneau** (le créneau concerné est conservé dans `attente_depuis`) ; un passage en `BLOQUEE` dans le même créneau est signalé une fois de plus. Le code retour compte ces événements. Dès que le créneau expire (`rattrapage_sec` ou créneau suivant), la règle repasse à son état précédent et l'attente est effacée.
- **Reprise en cascade** : tant que le créneau n'est pas pris ni expiré, une règle bloquée ou en attente repart d'elle-même dès que ses dépendances sont remplies, même si son heure est passée. `--reprise` de la règle en erreur suffit donc à relancer toute la chaîne. Les reprises et lancements manuels respectent aussi les dépendances.
- **Simulation** : exécutée dans le processus de l'orchestrateur, règle après règle, sans drapeau, sans fils, sans évaluation des dépendances.

## 4. Planification

Les calculs se font en **heure locale** du serveur d'exécution ; les résultats sont stockés en timestamps (secondes depuis 1970, UTC).

1. **Dernier créneau échu** : le plus récent créneau antérieur ou égal à maintenant, un jour autorisé. Un créneau n'est valable que jusqu'au **créneau suivant**, et au plus `rattrapage_sec` si renseigné.
2. **Règle due** si son dernier créneau échu est postérieur au `dernier_creneau` déjà pris en compte, ou si une commande de reprise ou de lancement manuel est en attente.
3. **Prise du créneau** : au moment où la règle est lancée, `dernier_creneau` reçoit ce créneau. Si Jenkins a été arrêté plusieurs heures, la règle ne part **qu'une fois**, pas une fois par créneau manqué.
4. **Règle en cours** quand un créneau arrive : elle n'est pas relancée. À sa fin, si un créneau est échu entre-temps, elle est due au lancement suivant.
5. **Nouvelle règle** (jamais vue en base) : son dernier créneau échu est considéré comme déjà pris. Elle démarre au créneau suivant ; pour la lancer tout de suite : `--lancer-maintenant`.
6. **`apres_erreur = arreter`** : après une `ERREUR`, aucun créneau n'est pris tant que la règle n'a pas reçu une reprise ou un acquittement.
7. **Changement d'heure** : un créneau situé dans l'heure supprimée au passage à l'heure d'été est exécuté à l'instant qui suit ; une heure répétée à l'automne ne donne qu'une exécution. Cas à couvrir par des tests.

### 4.1 Précisions apportées par l'implémentation (J5)

Code : `copie/planification.py` (calcul pur, horloge injectée), `copie/lancement.py` (lancement séquentiel, état), `copie/processus.py`.

- **Sans commande**, `python -m copie --config FICHIER [--regle ID] [--simulation]` est un **lancement** : il synchronise les règles avec la base, libère les exécutions orphelines, évalue chaque règle dans l'ordre du fichier et exécute les règles dues **l'une après l'autre dans ce processus**. Le parallélisme (un processus par règle) et la durée maximale arrivent au jalon J6. Code retour : 0, 4 si au moins un `WARNING`, 1 si au moins une `ERREUR`, 2 si la base est inutilisable.
- **Dépendances** : tant que le jalon J6 n'est pas fait, une règle qui a un champ `apres` n'est **pas lancée** quand elle est due : événement `regle_non_lancee` (WARNING) et code retour 4. Les règles sans dépendance fonctionnent normalement.
- **Créneau pris** : l'exécution enregistre le créneau qu'elle prend au moment où elle prend le drapeau (même transaction). Une reprise ou un lancement manuel prend aussi le dernier créneau échu, pour que la règle ne reparte pas aussitôt.
- **Règle nouvelle** (jamais lancée, `dernier_creneau` vide) : son dernier créneau échu est considéré comme pris au premier lancement qui la voit ; elle démarre au créneau suivant. `--lancer-maintenant` la démarre tout de suite (la règle est enregistrée en base par la commande).
- **Changement d'heure** : les créneaux sont des heures murales du serveur. Heure supprimée (printemps) : exécution à l'instant qui suit. Heure répétée (automne) : une seule exécution, à la première occurrence. Une règle horaire (00:00 à 23:00) s'exécute 24 fois un jour normal, 23 fois au printemps et 24 fois à l'automne ; une règle toutes les 5 minutes, 288 fois à l'automne (testé avec un fuseau fictif, indépendant du poste).
- **Orphelins** : une règle dont le drapeau « en cours » est posé par un processus disparu (identifiant **et** date de création, même serveur) est libérée au lancement suivant : exécution `ARRETEE`, règle en `ERREUR`, situation `arret_anormal`, arrêt après erreur si `apres_erreur = arreter`. Un processus vivant, ou d'un autre serveur, n'est jamais touché. Le cas d'une exécution vivante mais trop longue (arrêt de l'arbre de processus) arrive au jalon J6.
- **Commandes d'exploitation** (`--utilisateur` obligatoire, toutes tracées dans `journal_actions` et dans le journal) :
  - `--reprise ID` et `--lancer-maintenant ID` : refusées si la règle est en cours ; consommées au démarrage de l'exécution suivante (elles remettent aussi à zéro l'arrêt après erreur).
  - `--acquitter ID` : règle en `ERREUR` seulement, **commentaire obligatoire**, statut `ACQUITTEE`, pas de nouvelle exécution. **Refusé tant que des livraisons de résultat inconnu existent** : il faut d'abord les trancher.
  - `--trancher-incertain CLE --decision livre|a_relivrer --commentaire …` : décision sur une livraison de résultat inconnu (§6.3). La clé est donnée par `--etat` (compteur) et par la commande Python du cahier de tests ; elle sera listée par le front-end.
- **`--etat [--regle ID] [--format json]`** : lecture seule de la base, aucune écriture. Une règle absente de la base est `JAMAIS_LANCEE`. Statut affiché : `INACTIVE`, `EN_COURS`, `EN_ATTENTE`/`BLOQUEE` (jalon J6), sinon le dernier statut. Champs ajoutés au JSON du §6 de la base : `planification` (en clair), `lancement_manuel`, `arret_apres_erreur`, `livraisons_incertaines`, `orphelines`.
- **Horloge de la base** : toutes les dates de la base sont en secondes UTC prises sur l'horloge du serveur ; la planification, elle, compare des heures murales locales.

## 5. Exécution d'une règle

Dans le processus fils :

| # | Étape |
|---|---|
| 0 | **Prise du flag** « en cours » (atomique) et création de l'exécution en base |
| 1 | Si reprise : appel du programme `reprise` (`COPIE_REPRISE=1`) |
| 2 | **Actions en attente** des exécutions précédentes : suppressions et archivages différés ; livraisons interrompues (§6.3) |
| 3 | **Contrôles préalables** : source lisible, cible écrivable (§8), archive (§7), base |
| 4 | **Sélection** des fichiers (§5.1), avec la boucle de la situation `aucun_fichier` |
| 5 | Programme `avant_lot` (reçoit la liste) ; si le programme a tourné, la source est **relue** |
| 6 | **Filtre anti-doublon** : fichiers dont la version est déjà en base |
| 7 | **Contrôle d'espace** pour la cible et, si besoin, l'archive (§8) |
| 8 | Application de `ordre` et de `limite_fichiers` |
| 9 | **Pour chaque fichier** : `avant_fichier` → copie vérifiée → `apres_fichier` → action du mode (§6) |
| 10 | Programme `apres_lot` (reçoit la liste avec le résultat de chaque fichier) |
| 11 | **Bilan** : statut final, mise à jour de l'état et de l'exécution, libération du flag, événement `regle_terminee` |

En cas d'arrêt de la règle sur anomalie, le programme `sur_erreur` est appelé avant le bilan. La durée totale est surveillée par l'orchestrateur (`duree_max_sec`).

### 5.1 Sélection

Un fichier est **candidat** s'il :

1. correspond à `masque` et pas à `exclure` (le nom est comparé sans tenir compte de la casse) ;
2. n'est pas un fichier temporaire du moteur (`.copie_en_cours`) ni dans le dossier d'archive ;
3. respecte `modifie_depuis`, `age_minimum_sec`, `age_maximum_sec`, `taille_minimum_octets`.

Particularités :

- Un fichier plus récent que `age_minimum_sec` est **ignoré pour ce lancement**, sans erreur ; il sera repris à un lancement suivant. S'il n'en reste aucun, la situation `aucun_fichier` s'applique.
- Un fichier dont la date de modification est **dans le futur** de plus d'une minute (horloges désynchronisées) est ignoré et signalé en `WARNING`.
- La boucle de `aucun_fichier` relit le dossier à chaque tentative.

### 5.2 Anti-doublon

Voir [03-base-de-donnees §4](03-base-de-donnees.md). En résumé : avant toute livraison, le moteur calcule l'empreinte de la **version** du fichier (ou de son **contenu** si `identite = contenu`) et la cherche en base. Trouvée : le fichier est ignoré (mode `copie`) ou son original est traité sans nouvelle livraison (modes `deplacement`, `archivage`, si une action est en attente).

## 6. Copie vérifiée et modes

### 6.1 Séquence pour un fichier

Écritures en base **avant** chaque étape irréversible (journal d'intention) :

1. `avant_fichier` (peut modifier la source sur place). La taille et la date du fichier sont relues **après** le programme.
2. **Enregistrement d'intention** : l'empreinte est inscrite en base à l'état `INTENTION`, avec les chemins, dans la même transaction (commit avant de copier).
3. **Copie** de la source vers un temporaire (`dossier_temporaire`, ou `<nom>.copie_en_cours` dans la cible), avec calcul du SHA-256 en lisant la source une seule fois.
4. **Source stable** : taille et date identiques avant et après la lecture, sinon `fichier_instable`.
5. **Taille** du temporaire égale à celle de la source.
6. **SHA-256** du temporaire relu égal à celui de la source.
7. Date de modification d'origine recopiée ; attribut lecture seule de la cible levé.
8. **Nom final** appliqué (`renommage_cible`) ; si un fichier du même nom existe : `si_existe_cible`.
9. **Renommage atomique** du temporaire vers le nom définitif ; contrôle de présence et de taille.
10. État `LIVRE` en base (et `TERMINE` en mode `copie`).
11. `apres_fichier`. Code retour autre que 0 : l'original **n'est ni supprimé ni archivé**.
12. **Action du mode** (§6.2), puis état `TERMINE` en base.

### 6.2 Modes

| Mode | Action de l'étape 12 |
|---|---|
| `copie` | Aucune. L'original reste en place. |
| `deplacement` | Suppression de l'original, après vérification que sa taille et sa date sont **inchangées** depuis la copie (G4). Attribut lecture seule levé si besoin. |
| `archivage` | Déplacement de l'original dans le dossier d'archive (§7), après la même vérification. |

Si l'original a changé : il est conservé, `source_modifiee` est journalisé, et la nouvelle version sera livrée comme un nouveau fichier. Si la suppression ou l'archivage échoue : situation `suppression_echec` / `archivage_echec`, et avec `continuer_en_differe` l'action est mémorisée en base et retentée au début des exécutions suivantes, **sans relivrer** le fichier.

### 6.3 Reprise après arrêt brutal

Au début de chaque exécution (étape 2), les enregistrements restés à l'état `INTENTION` sont examinés :

- si la cible contient un fichier de même taille et de même SHA-256 que la source, inchangée : le fichier est considéré `LIVRE` ;
- sinon, **on ne sait pas** si la livraison a eu lieu et si le destinataire l'a déjà pris. Le fichier passe à l'état `INCERTAIN` et la règle s'arrête en `ERREUR` (G2). Une décision d'exploitation est nécessaire : reprise après avoir indiqué que le fichier doit être relivré, ou acquittement s'il est considéré livré. Exception : si `si_cible_absente = recopier`, le fichier est simplement relivré.

### 6.4 Précisions apportées par l'implémentation (J4)

Code : `copie/selection.py`, `copie/chemins.py`, `copie/transfert.py`, `copie/execution.py`. Commande provisoire : `python -m copie --config FICHIER --lancer-regle ID [--simulation]` (une règle, sans planification ; le lancement complet vient aux jalons J5 et J6). Codes retour : 0 succès, 4 avertissement, 1 erreur, 2 paramétrage ou base inutilisable.

- **Ordre des étapes** : (a) livraisons interrompues (§6.3), (b) contrôles préalables, (c) actions en attente, (d) sélection, (e) limite et espace, (f) livraison. Les contrôles passent avant les actions en attente car un archivage différé a besoin de savoir si l'archive est accessible. Les points d'appel des programmes externes (J7) s'insèrent aux mêmes endroits qu'au §5.
- **`aucun_fichier`** s'applique quand, **après** le filtre anti-doublon, il n'y a rien à livrer (et non quand la source est vide) : en mode `copie`, les fichiers restent dans la source, et un fichier déjà livré n'est pas « un fichier à livrer ». La boucle relit le dossier à chaque tentative, ce qui permet d'attendre l'arrivée d'un fichier. Niveau de secours `INFO` : une règle qui n'a souvent rien à faire ne passe pas en erreur.
- **`limite_fichiers` et espace disque** : la limite est appliquée avant le contrôle d'espace, qui ne porte donc que sur les fichiers réellement livrés ce jour-là.
- **Fichier modifié entre le listage et la copie** : la version enregistrée en base serait différente de la version livrée. La copie le détecte (`attendu`) et applique `fichier_instable` ; le fichier est repris au lancement suivant avec sa nouvelle empreinte.
- **`source_modifiee`** (original changé après la copie, au moment de supprimer ou d'archiver) : un seul essai, l'original est conservé, la version livrée est marquée terminée, la nouvelle version sera livrée normalement. L'action en attente ne reste pas bloquée.
- **Un fichier de même nom attend dans la cible** (`si_existe_cible = erreur`, défaut) : en mode `copie`, une nouvelle version d'un fichier non encore pris par le destinataire est donc refusée (situation `fichier_existe_cible`, 1 tentative). Pour attendre que le destinataire le prenne, augmenter `tentatives` et `delai_sec` de cette situation ; pour remplacer, `ecraser` ; pour conserver les deux, `suffixe`.
- **`si_cible_absente = recopier`** n'est possible que si le nom déposé est prévisible (`renommage_cible` absent ou sans variable de date). Sinon le moteur ne peut pas savoir quel fichier chercher et se comporte comme `ignorer`.
- **`identite = contenu`** : le SHA-256 n'est calculé que pour les versions inconnues. Un fichier régénéré à l'identique est signalé (`doublon_contenu`, niveau de la situation) ; en mode `deplacement` ou `archivage` son original est alors supprimé ou archivé sans nouvelle livraison.
- **Temporaire** : `<nom final>.copie_en_cours` dans la cible, ou `<id>_<empreinte>.copie_en_cours` dans `dossier_temporaire`. Le temporaire est écrit **et synchronisé sur le disque** (`fsync`) avant le renommage : une coupure de courant ne peut pas exposer un fichier tronqué sous son nom définitif. Le renommage n'écrase jamais (Windows : `os.rename`) sauf `si_existe_cible = ecraser`.
- **Date de modification** recopiée à la nanoseconde ; l'attribut lecture seule de l'original n'est pas copié (la cible est modifiable) mais ne bloque ni la suppression ni l'archivage de l'original.
- **Classification des échecs** : original disparu → `fichier_disparu` ; ouvert ou verrouillé par un autre processus (violation de partage ou de verrou Windows, lecture refusée en cours de route) → `fichier_verrouille` ; écriture impossible côté cible → `copie_echec` ; taille ou SHA-256 différents → `verification_echec` ; original changé pendant la lecture → `fichier_instable`.
- **Événements ajoutés au catalogue** : `regle_anomalie` (situation au niveau de la règle), `livraison_reprise`, `livraison_a_refaire`, `livraison_incertaine` (ERREUR), `fichier_date_future` (WARNING), `lecture_impossible` (WARNING), `limite_atteinte`, `cible_absente_recopie`, `action_a_rejouer` et `fichier_a_livrer` (simulation), `action_reportee`, `erreur_interne` (ERREUR).
- **Livraison incertaine** (§6.3) : événement `livraison_incertaine` pour chaque fichier, statut `ERREUR`, la règle s'arrête à chaque lancement tant que l'exploitation n'a pas tranché (`resoudre_incertain` : `livre` ou `a_relivrer`, commentaire obligatoire, tracé dans `journal_actions`). Les commandes d'exploitation correspondantes seront exposées aux jalons J5 et J8.
- **Coût de l'intégrité** (mesuré sur le poste de développement, 100 Ko par fichier) : environ 190 ms par fichier en mode `copie`, 230 ms en `deplacement` ; deux tiers viennent des `fsync` (copie et base). À mesurer sur le serveur (cahier J4-M01) avant toute optimisation.

## 7. Archive et mode dégradé

### 7.1 Résolution du chemin

- Chemin absolu : utilisé tel quel. Chemin relatif (`.\archive`) : calculé depuis la **racine de `source`**, en mode récursif comme en mode simple.
- Les variables de date sont remplacées (`.\archive\{AAAA}-{MM}-{JJ}`).
- Le dossier d'archive est **exclu du parcours** de la source.
- L'arborescence relative des sous-dossiers est reproduite dans l'archive.

### 7.2 Déplacement dans l'archive

- Même volume que la source (comparaison de l'identifiant du volume) : **renommage** immédiat, sans copie.
- Autre volume ou autre serveur : copie vérifiée (même séquence que §6.1, étapes 3 à 9), puis suppression de l'original.
- Un fichier du même nom déjà archivé : `si_existe_archive` (`suffixe` : horodatage ajouté ; une archive n'est jamais écrasée sauf avec `ecraser`).

### 7.3 Archive inaccessible : mode dégradé

Contrôle à l'étape 3, seulement si `archive` est renseigné :

1. Le dossier existe : contrôle d'écriture par un fichier d'essai.
2. Il n'existe pas : création si `creer_dossiers` (droits vérifiés avant).
3. Création ou écriture impossible : situation `archive_inaccessible` (tentatives, délai) puis `suite` :
   - `arreter_regle` : la règle s'arrête, rien n'est copié ;
   - `continuer_en_differe` (défaut) :
     1. le flag `archivage_degrade` est posé en base ;
     2. la **livraison continue** normalement ;
     3. pour chaque fichier livré, une action d'archivage est mémorisée en base avec ses chemins (la version est de toute façon enregistrée, donc **jamais relivrée**) ;
     4. un `WARNING` est journalisé à chaque exécution (événement `archivage_degrade`), ce qui donne le code retour 4 et un statut `WARNING` visible dans le front-end ;
     5. au début de chaque exécution suivante, le moteur retente l'archivage des actions en attente, dans l'ordre. Quand la file est vide, le flag est retiré et `archivage_retabli` est journalisé.
4. **Garde-fou** : un original modifié entre-temps n'est pas archivé (G4), et un `WARNING` précise que l'ancienne version a été livrée sans être archivée.

Dans le dossier de production, **aucun fichier témoin** n'est écrit : l'état dégradé est un flag en base.

Si la **base elle-même** est inaccessible, rien n'est copié (G6) : sans mémoire des fichiers traités, le moteur risquerait de relivrer.

## 8. Contrôles préalables et espace disque

Réalisés par le compte de service qui exécute le moteur, donc avec **ses** droits et **ses** quotas.

| Contrôle | Méthode |
|---|---|
| Source lisible | Listage du dossier |
| Cible écrivable | Création puis suppression d'un fichier d'essai (`.test_ecriture_<pid>`) ; création du dossier si `creer_dossiers` |
| Archive écrivable | Idem, **seulement si `archive` est renseigné** |
| Espace sur la cible | Octets disponibles **pour l'appelant** ≥ somme des tailles des fichiers à livrer + marge |
| Espace sur l'archive | Idem, **sauf si l'archive est sur le même volume que la source** (un renommage ne consomme rien) |

- L'espace est lu avec l'appel Windows `GetDiskFreeSpaceExW` (via `ctypes`), qui renvoie l'espace **disponible pour l'appelant**, quotas inclus, y compris sur un chemin UNC. À vérifier au développement : la fonction `shutil.disk_usage` de Python peut renvoyer l'espace libre total et non l'espace disponible pour l'utilisateur.
- Marge : `marge_espace_mo` de l'en-tête du paramétrage (64 Mo par défaut).
- Le contrôle d'espace est fait **après** le filtre anti-doublon : il ne porte que sur ce qui sera réellement livré.
- Volume : comparaison de l'identifiant de volume renvoyé par `os.stat(...).st_dev`.

## 9. Programmes externes

| Point d'appel | Moment | Code 0 | Code 1 | Autre code |
|---|---|---|---|---|
| `avant_lot` | Après la sélection, avant toute copie | Continuer | Rien à faire : la règle s'arrête **sans erreur** | Situation `programme_avant_lot` |
| `avant_fichier` | Avant la copie de chaque fichier | Copier | Fichier ignoré, sans erreur | Situation `programme_avant_fichier` |
| `apres_fichier` | Après la copie vérifiée, **avant** la suppression ou l'archivage | OK | OK | Situation `programme_apres_fichier` : l'original est conservé |
| `apres_lot` | Quand tous les fichiers sont traités | OK | OK | Situation `programme_apres_lot` |
| `sur_erreur` | Quand une règle s'arrête sur anomalie | — | — | Journalisé seulement |
| `reprise` | Au début d'une exécution lancée par reprise | OK | OK | Situation `programme_reprise` |

- **Lancement** : `subprocess` sans shell, avec le tableau `commande` dont les variables sont remplacées élément par élément. Répertoire courant : `dossier_travail`.
- **Durée maximale** : `timeout_sec`. Au-delà, l'**arbre** de processus est arrêté et la situation correspondante s'applique.
- **Sorties** : la sortie standard et la sortie d'erreur sont reprises dans le journal (événement `programme_appele`, tronquées à 8 Ko).
- **Liste de fichiers** : écrite dans `dossier_travail` en deux formats, `{liste}` (texte UTF-8, un chemin par ligne) et `{liste_json}` (chemin, taille, date de modification ; pour `apres_lot`, le résultat de chaque fichier).
- **Variables d'environnement** : `COPIE_ENVIRONNEMENT`, `COPIE_REGLE`, `COPIE_EXECUTION_ID`, `COPIE_SOURCE`, `COPIE_CIBLE`, `COPIE_ARCHIVE`, `COPIE_MODE`, `COPIE_FICHIER`, `COPIE_FICHIER_CIBLE`, `COPIE_LISTE`, `COPIE_LISTE_JSON`, `COPIE_REPRISE`, `COPIE_SIMULATION`, et pour `apres_lot` `COPIE_STATUT`.
- **`avant_fichier` modifie la source sur place** (décision) : l'empreinte de la version est calculée sur la taille et la date **relues après** le programme. Sinon, au lancement suivant, le fichier modifié paraîtrait nouveau et serait retraité sans fin.
- **Sécurité** : le paramétrage permet de faire exécuter des programmes par le compte de service. Voir §13.

### 9.1 Précisions apportées par l'implémentation (J7)

Code : `copie/programmes.py` (lancement, listes), appels dans `copie/execution.py`.

- **Lancement** : `subprocess` sans shell ; chaque élément de `commande` reçoit ses variables, un élément reste un argument même s'il contient des espaces, des guillemets ou `&`. Entrée standard fermée. Sortie standard et sortie d'erreur **réunies**, décodées en UTF-8 puis, à défaut, dans la page de code OEM de la console ; tronquées à **8 Ko**. Les programmes Python reçoivent `PYTHONUTF8=1` et `PYTHONIOENCODING=utf-8` (leur sortie est en UTF-8). Répertoire courant : `dossier_travail`.
- **Arbre de processus** : sous Windows le programme démarre **suspendu**, est placé dans son propre Job Object, puis repris : un petit-fils lancé dès la première instruction n'échappe pas à l'arrêt. À l'expiration de `timeout_sec`, tout l'arbre est arrêté (mesuré : aucun survivant sur 3 essais consécutifs).
- **Variables par point d'appel** (contrôle G01) : `{fichier}`, `{nom}`, `{fichier_cible}` seulement pour `avant_fichier` et `apres_fichier` ; `{liste}`, `{liste_json}` seulement pour `avant_lot`, `apres_lot` et `sur_erreur` ; `{environnement}`, `{regle}`, `{source}`, `{cible}`, `{archive}` (vide s'il n'y a pas d'archive) et `{date}` (date du lancement, `AAAA-MM-JJ`) partout. Une variable sans objet à un point d'appel est refusée par `--verifier`.
- **Variables d'environnement** : `COPIE_ENVIRONNEMENT`, `COPIE_REGLE`, `COPIE_EXECUTION_ID`, `COPIE_SOURCE`, `COPIE_CIBLE`, `COPIE_ARCHIVE`, `COPIE_MODE`, `COPIE_FICHIER`, `COPIE_FICHIER_CIBLE`, `COPIE_LISTE`, `COPIE_LISTE_JSON`, `COPIE_REPRISE` (0/1), `COPIE_SIMULATION` (0/1), `COPIE_POINT_APPEL`, `COPIE_STATUT` ; pour `sur_erreur` aussi `COPIE_SITUATION` et `COPIE_MESSAGE`.
- **Listes** : `dossier_travail\liste_<exécution>_<point>.txt` (un chemin par ligne, UTF-8) et `.json` (`chemin`, `relatif`, `taille`, `date_modification`, et pour `apres_lot` / `sur_erreur` `resultat` = `livre`, `ignore`, `erreur` ou `a_livrer`, `cible`, `message`). Supprimées après l'appel.
- **Codes retour** : 0 et 1 sont acceptés aux cinq points qui ont une règle (tableau ci-dessus) ; tout autre code, une durée dépassée ou un programme introuvable applique la situation `programme_<point>` **avec ses tentatives et son délai** (par exemple trois essais espacés de 30 s). `sur_erreur` n'a pas de code attendu : son résultat est journalisé (`programme_appele`, WARNING si ≠ 0), il ne change jamais le statut.
- **Ordre des appels dans une exécution** : `reprise` (seulement si l'exécution a été déclenchée par une reprise, pas par un créneau ni un lancement manuel) **avant tout contrôle** → contrôles → actions en attente → sélection → `avant_lot` (si le programme s'est exécuté, la source est **relue**, les fichiers ajoutés ou retirés sont pris en compte) → pour chaque fichier `avant_fichier` → copie vérifiée → `apres_fichier` → suppression ou archivage → `apres_lot` → bilan → `sur_erreur` si le statut est `ERREUR`.
- **`avant_lot`** n'est appelé que s'il y a au moins un fichier à livrer ; **`apres_lot`** que si au moins un fichier a été traité (aucun message de fin quand il n'y a rien eu à faire). Code 1 de `avant_lot` : la règle se termine en succès avec le motif « avant_lot : rien a faire ».
- **`avant_fichier`** peut modifier la source sur place : la taille et la date sont relues, **l'empreinte est calculée sur les valeurs relues** (le fichier modifié n'est pas retraité au lancement suivant, mesuré par un test : le programme n'est appelé qu'une fois). Code 1 : le fichier est ignoré, sans erreur et **sans trace en base** (le programme sera rappelé au lancement suivant). Fichier disparu après le programme : ignoré.
- **`apres_fichier` en échec** : le fichier est déjà livré (état `TERMINE`), **aucune suppression ni archivage n'aura lieu, ni maintenant ni plus tard** (l'action en attente est supprimée) ; l'original reste dans la source et la situation s'applique (`fichier_suivant` ou `arreter_regle`).
- **Simulation** : les programmes ne sont pas appelés ; avec `--simulation-programmes` ils le sont avec `COPIE_SIMULATION=1` (aucune livraison pour autant).

## 10. Reprise, acquittement, déblocage

Les commandes sont enregistrées dans `journal_actions` avec le compte, l'heure et le commentaire (G9).

| Commande | Condition | Effet |
|---|---|---|
| `--reprise ID` | Règle non en cours | `reprise = 1`. Au prochain lancement : exécution **quelle que soit l'heure**, programme `reprise` appelé en premier, flag remis à 0 au démarrage de l'exécution. Le statut redevient `SUCCES` si l'exécution réussit, `ERREUR` sinon (il faut alors une nouvelle reprise) |
| `--lancer-maintenant ID` | Règle non en cours | Comme la reprise, sans le programme `reprise` |
| `--acquitter ID` | Règle en `ERREUR` | Statut `ACQUITTEE`, `arret_apres_erreur` levé. Compte comme un succès pour les dépendances, mais **pas** comme une livraison (`fichiers`). Commentaire obligatoire |
| `--debloquer ID` | Règle `EN_COURS` | Arrêt de l'arbre de processus, exécution terminée en `ERREUR`, flag libéré. Dans l'état `ERREUR` avec `apres_erreur = arreter`, une reprise est ensuite nécessaire |

Cas d'exploitation :

| Situation | Action |
|---|---|
| Règle simple en erreur, problème corrigé | Reprise |
| Chaîne bloquée par une règle en erreur | Reprise de **la règle en erreur** ; la chaîne suit |
| Problème traité à la main (fichiers déplacés) | Acquittement |
| Règle qui ne répond plus | Déblocage, puis reprise |
| Test ou rattrapage | Lancer maintenant |
| Rejouer des fichiers archivés | Prévu dans un second temps |

## 11. Journalisation

### 11.1 Interface du module commun

```python
journal.debut(application="copie_fichiers", environnement="production")
journal.evenement("fichier_livre", regle="export_clients", fichier=..., taille=..., sha256=..., duree_ms=...)
journal.fin(statut="WARNING", compteurs={...})
```

Les programmes n'appellent que ces trois fonctions. Le fonctionnement interne (aujourd'hui : fichiers lus par Alloy ; demain : envoi direct) peut changer sans modifier les appelants. **Une panne de journalisation ne doit jamais arrêter un transfert (G7)** : repli sur la sortie d'erreur et sur un fichier de secours local.

### 11.2 Fichiers

- `<dossier_logs>\<regle>_<AAAA-MM-JJ>.jsonl` : un fichier par règle et par jour. `<dossier_logs>\_orchestrateur_<AAAA-MM-JJ>.jsonl` pour le lancement.
- UTF-8, une ligne = un événement, écrite en **un seul appel d'écriture** en mode ajout. Plusieurs processus peuvent écrire dans le même fichier ; un test de charge (8 processus × 10 000 lignes, aucune ligne corrompue) fait partie des critères de sortie.
- La purge des anciens fichiers est un module séparé, paramétré par `id` de règle.

### 11.3 Format

```json
{"horodatage":"2026-11-03T06:30:12.481Z","niveau":"INFO","application":"copie_fichiers",
 "environnement":"production","job":"COPIE_PROD","build":"1542","build_url":"https://jenkins/job/COPIE_PROD/1542/",
 "noeud":"SRV-JENKINS01","regle":"export_clients","execution_id":8812,
 "evenement":"fichier_livre","fichier":"\\\\SRV-PROD01\\exports\\clients\\C1.xml","cible":"D:\\SFTP\\out\\clients\\C1_20261103_063012.xml",
 "taille":15234,"sha256":"9f86d0…","duree_ms":182,"statut":"OK","message":"…"}
```

- Horodatage en UTC. Les variables Jenkins (`JOB_NAME`, `BUILD_NUMBER`, `BUILD_URL`, `NODE_NAME`) sont ajoutées automatiquement.
- Niveaux : `INFO`, `WARNING`, `ERREUR` (et `DEBUG` en mode verbeux).
- **Libellés Loki conseillés** (peu de valeurs différentes) : `application`, `environnement`, `regle`, `niveau`. Jamais le nom du fichier.

### 11.4 Catalogue des événements

| Événement | Niveau habituel | Contenu |
|---|---|---|
| `debut_lancement`, `fin_lancement` | INFO | Compteurs par statut, code retour (bilan de l'état persistant) |
| `regle_demarree`, `regle_terminee` | INFO | Déclencheur, statut, durée, compteurs |
| `regle_non_lancee` | `si_condition_non_remplie` | Motif (`BLOQUEE` / `EN_ATTENTE`), règle bloquante |
| `regle_orpheline` | WARNING | Règle en base absente du paramétrage |
| `controle_prealable` | INFO / ERREUR | Résultat de chaque contrôle |
| `selection` | INFO | Nombre de candidats, ignorés, trop récents |
| `fichier_livre` | INFO | Source, cible, taille, SHA-256, durée |
| `fichier_ignore` | DEBUG | Déjà livré |
| `doublon_contenu` | INFO | Contenu déjà livré |
| `tentative_echouee` | WARNING | Situation, numéro de tentative |
| `fichier_erreur` | niveau de la situation | Situation, message |
| `fichier_supprime`, `fichier_archive` | INFO | Chemins |
| `action_differee` | WARNING | Type d'action mémorisée |
| `archivage_degrade`, `archivage_retabli` | WARNING / INFO | Nombre d'actions en attente |
| `programme_appele` | INFO / niveau de la situation | Commande, code retour, durée, sortie |
| `reprise_demandee`, `reprise_demarree`, `acquittement`, `deblocage` | INFO | Compte, commentaire |
| `duree_depassee`, `arret_anormal` | ERREUR | Durée, action appliquée |
| `base_indisponible` | ERREUR | Message |

### 11.5 Précisions apportées par l'implémentation (J3)

Le module est le fichier autonome [journal_si.py](../journal_si.py), à la racine du dépôt : un autre programme du S.I. peut le copier tel quel.

- **Appel** : `debut(application, environnement, dossier=…, verbeux=False, console=False, dossier_secours=None, evenement_debut="debut", evenement_fin="fin", **contexte)`, `evenement(nom, niveau="INFO", **champs)`, `fin(statut="OK", compteurs=None, **champs)`. Le moteur passe `evenement_debut="debut_lancement"` et `evenement_fin="fin_lancement"`. `definir(regle=…, execution_id=…)` ajoute des champs à tous les événements suivants (un processus fils d'exécution y met sa règle). Dossier par défaut : variable d'environnement `JOURNAL_SI_DOSSIER`, sinon `logs`.
- **`fin`** ajoute `duree_ms` (depuis `debut`), `statut` et `compteurs`, et son niveau suit le statut (`ERREUR` → ERREUR, `WARNING` → WARNING, le reste INFO). Elle ferme les fichiers.
- **Fichiers** : le jour du nom de fichier est le **jour local** du serveur ; l'horodatage de chaque ligne reste en UTC. Un événement sans `regle` va dans `_orchestrateur_<jour>.jsonl`. Le nom de règle est assaini (`[A-Za-z0-9_.-]`, le reste devient `_`) pour qu'il ne sorte jamais du dossier.
- **Ordre des champs** : `horodatage`, `niveau`, `application`, `environnement`, variables Jenkins (`job`, `build`, `build_url`, `noeud`, seulement si présentes), `regle`, `execution_id`, `evenement`, puis les champs de l'appelant. Un champ de l'appelant qui porte le nom d'un champ réservé est conservé sous `x_<nom>` (il n'écrase jamais le champ du module).
- **Écriture atomique** : sous Windows, la ligne est écrite avec `WriteFile` sur un handle ouvert avec `FILE_APPEND_DATA` seul : le système place chaque écriture à la fin du fichier, même entre processus. **L'option `O_APPEND` du C ne suffit pas** : mesurée sur le poste de développement avec 8 processus écrivant 16 000 lignes de 3,5 Ko, il reste 9 098 lignes dont 1 460 corrompues (les autres sont perdues ou mélangées). Le fichier est ouvert avec un partage complet (lecture, écriture, suppression) : Alloy peut le lire et la purge peut le supprimer.
- **Bornage** : un champ texte de plus de 4 000 caractères est coupé et suffixé `...[tronque, N caracteres]` (sorties de programmes). Les valeurs non convertibles en JSON (`Path`, `bytes`, ensembles, dates) sont converties ; un nom de fichier Windows avec un caractère isolé ne fait pas échouer l'écriture.
- **Panne (G7)** : jamais d'exception. En cas d'échec (dossier absent et non créable, disque plein, droits), la ligne est écrite sur la sortie d'erreur et dans `journal_si_secours_<jour>.jsonl` (dossier `dossier_secours`, sinon dossier temporaire du compte), `pannes()` compte les incidents et la prochaine écriture retente le dossier normal. Le moteur doit ajouter un WARNING au bilan quand `pannes() > 0`.
- **Console** : avec `console=True`, chaque événement est aussi écrit en une ligne lisible sur la sortie standard (console Jenkins).
- **Exemple de sortie** : [exemples/journal/](../exemples/journal/) ; **exemple de configuration Alloy** (non testé) : [exemples/alloy/copie_fichiers.alloy](../exemples/alloy/copie_fichiers.alloy).

## 12. Intégration Jenkins

Un job par environnement, déclenché toutes les N minutes, **builds simultanés autorisés**. Exemple indicatif de `Jenkinsfile` (la Shared Library `journal-si` reste à créer) :

```groovy
@Library('journal-si') _
pipeline {
  agent { label 'copie-fichiers' }
  triggers { cron('H/5 * * * *') }
  options { timeout(time: 3, unit: 'HOURS') }
  stages {
    stage('Transfert') {
      steps {
        script {
          def rc = bat(returnStatus: true,
            script: 'python D:\\Scripts\\copie_fichiers.py --config D:\\Parametrage\\production.jsonl')
          if (rc == 4) { unstable('Au moins un avertissement') }
          else if (rc != 0) { error("copie_fichiers : code retour ${rc}") }
        }
      }
    }
  }
  post { always { journalSI.finJob(application: 'copie_fichiers', environnement: 'production') } }
}
```

La Shared Library produit les événements de niveau job (`debut_job`, `fin_job`, statut, durée, lien du build) **dans le même format JSON** que le module Python, pour uniformiser les journaux de tous les programmes.

## 13. Sécurité

- Le compte de service a un accès **en lecture seule** au paramétrage. Qui peut modifier le paramétrage peut faire exécuter un programme par ce compte : les droits d'écriture sur le dossier de paramétrage sont réservés au groupe d'administrateurs Active Directory.
- Les mots de passe, clés et jetons ne figurent jamais dans le paramétrage ni dans les arguments des programmes.
- Les sorties des programmes sont journalisées : elles ne doivent pas contenir de secret.
- Les commandes d'exploitation (`--reprise`, `--acquitter`…) exigent `--utilisateur` ; le front-end y passe le compte AD authentifié. L'accès distant à ces commandes doit être restreint aux administrateurs (WinRM avec point de terminaison JEA recommandé).

## 14. Limites connues

- La date de modification est comparée à l'heure du serveur d'exécution : horloges à synchroniser.
- Résolution des dates de modification variable selon le système de fichiers (100 ns en NTFS, 2 s en FAT) : comparaison toujours faite sur la même source.
- Les chemins de plus de 260 caractères nécessitent le support des chemins longs de Windows.
- Un fichier verrouillé en lecture exclusive par une application de production est signalé (`fichier_verrouille`) et retenté.
- Le moteur ne propage pas les suppressions de la source vers la cible.
