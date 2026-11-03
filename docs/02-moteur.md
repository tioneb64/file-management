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

## 4. Planification

Les calculs se font en **heure locale** du serveur d'exécution ; les résultats sont stockés en timestamps (secondes depuis 1970, UTC).

1. **Dernier créneau échu** : le plus récent créneau antérieur ou égal à maintenant, un jour autorisé. Un créneau n'est valable que jusqu'au **créneau suivant**, et au plus `rattrapage_sec` si renseigné.
2. **Règle due** si son dernier créneau échu est postérieur au `dernier_creneau` déjà pris en compte, ou si une commande de reprise ou de lancement manuel est en attente.
3. **Prise du créneau** : au moment où la règle est lancée, `dernier_creneau` reçoit ce créneau. Si Jenkins a été arrêté plusieurs heures, la règle ne part **qu'une fois**, pas une fois par créneau manqué.
4. **Règle en cours** quand un créneau arrive : elle n'est pas relancée. À sa fin, si un créneau est échu entre-temps, elle est due au lancement suivant.
5. **Nouvelle règle** (jamais vue en base) : son dernier créneau échu est considéré comme déjà pris. Elle démarre au créneau suivant ; pour la lancer tout de suite : `--lancer-maintenant`.
6. **`apres_erreur = arreter`** : après une `ERREUR`, aucun créneau n'est pris tant que la règle n'a pas reçu une reprise ou un acquittement.
7. **Changement d'heure** : un créneau situé dans l'heure supprimée au passage à l'heure d'été est exécuté à l'instant qui suit ; une heure répétée à l'automne ne donne qu'une exécution. Cas à couvrir par des tests.

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
