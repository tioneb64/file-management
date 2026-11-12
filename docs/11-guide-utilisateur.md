# Guide d'utilisation de l'interface de gestion

Ce guide s'adresse aux personnes qui **suivent** les transferts de fichiers (consultation) et à celles qui **gèrent** le paramétrage et l'exploitation (administrateurs). L'installation est décrite dans [10-installation](10-installation.md) ; les règles complètes du paramétrage dans [01-parametrage](01-parametrage.md).

> L'interface n'a pas encore été utilisée sur le serveur de production. Les écrans ont été vérifiés par des tests automatiques et des captures d'écran, **pas encore à la souris par une personne** : signaler tout écart avec ce guide.

## 1. À quoi sert l'interface

Le transfert lui-même est fait par le **moteur**, lancé par Jenkins toutes les 5 minutes : il copie, déplace ou archive des fichiers selon des **règles**. L'interface ne copie rien. Elle sert à :

- **voir** les règles et leur état (réussie, en erreur, en attente…) ;
- **modifier** les règles (administrateurs) ;
- **agir** quand une règle est en difficulté : la reprendre, la lancer tout de suite, acquitter une erreur, débloquer une exécution, trancher une livraison incertaine, purger les vieux journaux ;
- **comprendre** (graphe des dépendances, historique des modifications) et **réutiliser** une règle d'un environnement dans un autre.

Elle n'ouvre jamais la base de données : tout passe par les commandes du moteur, qui est la seule référence pour valider un paramétrage.

## 2. Ouvrir l'interface

Lancer `Lancer-GestionCopie.ps1 -DossierParametrage <dossier>` (ou le raccourci fourni par l'exploitation).

**Si le dossier n'existe pas** : un administrateur se voit proposer de le créer (Oui / Non, le chemin complet est rappelé) ; un autre compte reçoit un message qui nomme le groupe des administrateurs. Un chemin vide, invalide, qui désigne un fichier ou un dossier inaccessible donne un message clair, jamais une erreur technique.
**Si Python ou le moteur configurés n'existent pas** (mode Local) : l'interface les cherche (PATH, lanceur `py`, dépôt) et vous demande, en une seule question, si vous voulez les utiliser pour la session. Le fichier de configuration n'est pas modifié : corrigez `Moteur.Python` et `Moteur.Racine` dedans pour que ce soit définitif.
**Si le dossier est vide** : la fenêtre explique qu'il n'y a aucun environnement ; l'administrateur se voit proposer tout de suite de **créer le premier** (§13), les autres sont renvoyés à un administrateur.

La fenêtre s'ouvre avec :

- **en haut** : le dossier de paramétrage, votre compte, et un badge **ADMINISTRATEUR** (vert) ou **LECTURE SEULE** (orange). Le badge dépend de votre appartenance au groupe AD des administrateurs, lue à l'ouverture de votre session Windows ;
- **un onglet par environnement** (production, recette…), nommé d'après le fichier. Un environnement au fichier problématique (même nom déclaré deux fois, nom différent de celui du fichier, format inconnu) s'affiche en **lecture seule** avec un message dans le bandeau ;
- **en bas** : la barre d'état et le panneau « Journal » de l'interface (bouton « Effacer » pour le vider à l'écran).

Le bouton **Actualiser** de la fenêtre relit tout le dossier de paramétrage et reconstruit les onglets.

À l'ouverture, la liste des règles s'affiche **tout de suite** ; les statuts arrivent quelques instants plus tard (message « État en cours de lecture… »). Pendant ce temps les boutons de l'onglet sont grisés.

## 3. L'onglet d'un environnement

### 3.1 La liste des règles

Une ligne par règle : identifiant, description, mode, chemins source → cible, planification en clair, actif, **statut**, dernier lancement et prochain créneau.

Filtres en haut de la liste : recherche libre (identifiant, description, chemins), **statut** (tous les statuts du §3.2, même ceux qu'aucune règle n'a pour le moment : on peut chercher `ERREUR` ou `WARNING`), **mode** (`copie`, `deplacement`, `archivage`, `suppression`, `count`, `size`, `synchro`) et **Règles** : toutes, actives seulement ou inactives seulement. Les chemins affichés sont les **chemins complets** (racine comprise, §13).

Couleurs : ligne **grise** = règle inactive ; ligne **rouge** = dernière exécution en erreur, règle arrêtée ou bloquée ; ligne **bleu ciel** = règle sélectionnée. Le compteur indique « N règle(s) affichée(s) sur M ».

### 3.2 Les statuts

| Statut | Sens | Que faire |
|---|---|---|
| `JAMAIS_LANCEE` | La règle n'a jamais tourné (nouvelle, ou pas encore à l'heure) | Rien ; **Lancer maintenant** pour ne pas attendre |
| `SUCCES` | Dernière exécution sans erreur ni avertissement | Rien |
| `WARNING` | Terminée avec au moins un avertissement (archive indisponible, fichier ignoré…) | Lire le motif dans l'onglet **État** |
| `ERREUR` | Dernière exécution en erreur, ou arrêtée | Voir §6 : corriger la cause, puis **Reprise** ou **Acquitter** |
| `ATTENTE` | Règle `count` ou `size` dont les seuils ne sont pas atteints (par exemple 4 fichiers sur 5 attendus) : ni succès ni erreur | Rien : les règles qui en dépendent patientent ; elle sort en succès dès que le seuil est atteint |
| `ACQUITTEE` | Erreur déclarée corrigée par un administrateur | Rien |
| `EN_COURS` | Une exécution est en cours | Attendre ; **Débloquer** seulement si elle est figée |
| `EN_ATTENTE` | Son heure est passée, mais une règle dont elle dépend n'a pas encore tourné | Normal ; partira toute seule |
| `BLOQUEE` | Une règle dont elle dépend est en `ERREUR` ; le motif la nomme | Corriger la règle en erreur : toute la chaîne repart ensuite |
| `INACTIVE` | La règle est désactivée dans le paramétrage | Rien, ou **Activer** |

### 3.3 Les onglets du bas

- **Détail de la règle** : tous les champs de la règle sélectionnée, regroupés.
- **État** : statut, motif, dernière erreur, dernier succès, dernière exécution (fichiers livrés, erreurs, durée), actions en attente, livraisons incertaines, drapeaux (reprise demandée, arrêt après erreur, archivage dégradé).
- **Dépendances** : voir §8.

### 3.4 Boutons

| Bouton | Qui | Rôle |
|---|---|---|
| Vérifier le paramétrage | Tous | Contrôle complet du fichier par le moteur (§4) |
| Actualiser l'état | Tous | Relit le fichier et l'état. **Il n'y a pas d'actualisation automatique** |
| Ajouter, Dupliquer, Modifier, Activer / Désactiver, Supprimer | Administrateurs | Édition (§5) |
| Reprise, Lancer maintenant, Acquitter, Débloquer, Trancher… | Administrateurs | Exploitation (§6) |
| Purger… | Administrateurs | Purge des journaux et archives (§6.6) |
| Promouvoir… | Administrateurs | Copier une règle vers un autre environnement (§9) |
| Historique… | Tous (si le dossier des versions est lisible) | Modifications passées, restauration (§10) |
| Simuler la règle… | Tous (règle sélectionnée) | Ce que la règle ferait maintenant, avec contrôle des répertoires (§14) |
| Nouvel environnement…, Modifier / renommer…, Copier vers un nouvel environnement…, Créer la base…, Supprimer… | Administrateurs (barre « Environnements », au-dessus des onglets) | Gestion des environnements (§13) |

Les boutons d'édition n'apparaissent que si vous êtes administrateur **et** que l'environnement n'est pas en lecture seule. Ceux d'exploitation exigent un administrateur et un fichier lisible, et (sauf Purger) une règle sélectionnée.

## 4. Vérifier le paramétrage

**Vérifier le paramétrage** lance, en arrière-plan, le contrôle complet du moteur : syntaxe et accès (sources lisibles, cibles et archives accessibles en écriture, programmes présents, base utilisable, espace disque). Une fenêtre liste :

- les **refus** (rouge) : le moteur n'accepterait pas ce fichier ;
- les **avertissements** (orange) : acceptable, mais à lire ;
- les **informations** (bleu) : par exemple l'espace disponible.

Les accès sont contrôlés **avec le compte qui exécute le moteur** : avec un point d'accès JEA, celui du compte de service (donc de Jenkins) ; sans JEA, **le vôtre** : dans ce cas, un contrôle réussi ne prouve rien pour Jenkins.

## 5. Modifier le paramétrage (administrateurs)

### 5.1 Ajouter, dupliquer, modifier

**Ajouter** ouvre le formulaire d'une règle avec les valeurs de secours du moteur ; **Dupliquer** part de la règle sélectionnée (il faut un nouvel identifiant) ; **Modifier** ouvre la règle sélectionnée.

Le formulaire est organisé en onglets : **Général** (identifiant, description, actif, source, cible, mode, archive, planification), **Sélection** (masque, exclusions, récursivité, fenêtre de dates, âges, tailles), **Anti-doublon et nommage**, **Dépendances** (règles qui doivent avoir tourné avant, et à quelle condition), **Durée et erreurs** (durée maximale, réactions aux situations : nouvel essai, délai, suite), **Purge**, ainsi que les programmes externes à appeler.

Points d'attention :

- **L'identifiant d'une règle ne doit jamais changer** : l'historique en base y est rattaché. Pour « renommer », créer une nouvelle règle.
- Les durées se saisissent avec leur unité (secondes, minutes, heures…) ; les champs à choix sont des listes.
- Une règle **active** ne peut pas dépendre d'une règle **inactive**.
- Modifier ou ajouter un **programme** fait exécuter ce programme par le compte de service : le formulaire le rappelle et la modification est tracée.

### 5.2 Enregistrer

Le bouton **Enregistrer…** déclenche la même séquence pour toute modification :

1. Vous saisissez un **commentaire obligatoire** (pourquoi cette modification).
2. Le fichier complet est écrit dans un brouillon et **vérifié par le moteur** (syntaxe et comparaison avec la version actuelle). Un **refus** s'affiche dans la fenêtre des diagnostics et vous revenez au formulaire, avec votre saisie, pour corriger.
3. Les **avertissements** (par exemple une règle qui démarre avant une règle dont elle dépend, ou une sélection élargie qui ferait livrer plus de fichiers qu'avant) sont soumis à votre confirmation.
4. Si quelqu'un d'autre a modifié le fichier entre-temps, **rien n'est écrit** : le fichier est rechargé et vous recommencez.
5. L'ancienne version est **copiée dans `versions\`** avec une fiche (compte, date, commentaire), puis le fichier est remplacé en une seule opération : il n'est jamais écrit à moitié.
6. L'interface **contrôle aussitôt les répertoires de la règle** (§5.4).

Le moteur **prend en compte** le nouveau fichier au lancement suivant (dans les 5 minutes). Une règle nouvelle démarre à son **créneau suivant** ; pour la lancer tout de suite : **Lancer maintenant**.

### 5.3 Activer, désactiver, supprimer

**Désactiver** (ou **Activer**) change seulement le champ `actif`. **Supprimer** retire la règle du fichier après confirmation ; son historique reste en base (le moteur la signale comme « orpheline » dans le bandeau). Dans les deux cas, le commentaire est demandé et la même vérification s'applique.

### 5.4 Contrôle des répertoires après l'enregistrement

Le moteur vérifie le fichier **sans** aller voir les dossiers (la vérification d'enregistrement est « syntaxe seule »). C'est pourquoi, **dès qu'une règle est enregistrée**, l'interface demande au moteur de contrôler ses répertoires : source, cible, dossier temporaire et archive. Pour chacun : **existe**, **lecture**, **écriture** (un petit fichier d'essai est créé puis supprimé aussitôt) ; la cible et l'archive dont le volume diffère de la source sont aussi contrôlées pour l'**espace disque**.

**Un seul écran de résultat.** Seule une *demande* (par exemple « Créer maintenant les dossiers manquants ? ») s'affiche dans une boîte Oui / Non. Tout le reste (règle enregistrée, dossiers créés, répertoires en bon état, avertissements, erreurs) est rassemblé dans **une seule fenêtre « Contrôle des répertoires »**, comme « Vérifier le paramétrage » : une ligne par information, en bleu (information), orange (avertissement) ou rouge (erreur). Plus de série de boîtes « OK ».

- Tout va bien : une ligne d'information par répertoire, et la synthèse en tête de fenêtre nomme le compte avec lequel le contrôle a été fait.
- Un **problème** (dossier absent côté source, droit refusé, dossier temporaire sur un autre volume) : message en clair, avec le chemin, ce qui manque et le conseil de corriger la règle ou les droits. La règle reste enregistrée : le contrôle n'empêche rien, il informe.
- Un **dossier absent qui peut être créé** (source, cible, temporaire, archive) : l'administrateur se voit proposer de le **créer**, dans **une seule question** qui les liste tous ; le contrôle est refait ensuite. Vérifiez bien le chemin complet affiché avant de répondre Oui : un dossier source absent est souvent une faute de frappe. Au lancement, le moteur ne crée **jamais** la source seul (c'est le système producteur qui l'alimente) ; il crée la cible et l'archive si la case « Créer les dossiers manquants » est cochée.

**Avec quel compte ?** Les droits contrôlés sont ceux du compte qui exécute le moteur : le vôtre en mode local, celui du serveur en mode distant, le **compte de service du point d'accès JEA** si vous passez par JEA (c'est le compte qui fera les transferts). Le message le dit.

## 6. Exploitation (administrateurs)

Toutes ces actions sont tracées avec **votre compte** dans la base, le journal du moteur et celui de l'interface. Quand le moteur refuse (règle déjà en cours, commentaire manquant…), son message est affiché tel quel et rien n'est modifié.

### 6.1 Reprise

À utiliser après avoir **corrigé la cause** d'une erreur : la règle repartira **au prochain lancement**, quelle que soit l'heure, et son programme « reprise » sera appelé en premier s'il existe. La confirmation liste les règles qui **dépendent** de celle-ci : elles repartiront d'elles-mêmes dès que leurs dépendances seront remplies. Le commentaire est facultatif.

### 6.2 Lancer maintenant

La règle part au prochain lancement sans attendre son créneau et **sans** programme de reprise. Utile pour une règle nouvelle ou pour une relance ponctuelle.

### 6.3 Acquitter

Pour une règle en `ERREUR` que vous considérez comme **traitée à la main** (le fichier a été livré autrement, l'erreur est sans conséquence) : elle passe en `ACQUITTEE` sans être relancée. Le **commentaire est obligatoire**. Pour que la règle reparte, utiliser plutôt **Reprise**.

### 6.4 Débloquer

Une règle `EN_COURS` qui ne se termine pas (programme figé) : **Débloquer arrête l'exécution**, tue le processus et tous ses descendants, et libère la règle (elle passe en erreur). Selon son réglage `apres_erreur`, une **reprise** est ensuite nécessaire ; l'interface le signale. À n'utiliser que si l'exécution est réellement figée : une copie interrompue en pleine écriture devient une livraison incertaine (§6.5).

### 6.5 Trancher une livraison incertaine

Quand une exécution est arrêtée brutalement **pendant la copie d'un fichier**, le moteur ne sait pas si le fichier est arrivé entier. Pour ne **jamais créer de doublon**, il s'arrête et la règle reste en erreur (« livraison incertaine ») ; l'onglet **État** affiche leur nombre. Le bouton **Trancher…** est actif quand la règle sélectionnée en a.

1. **Regardez dans le dossier cible** : le fichier est-il là, entier ?
2. **Trancher…** ouvre la liste (source, cible, clé). Choisissez une ligne.
3. Choisissez **« Le fichier est bien arrivé… »** (il est considéré comme livré) ou **« Le fichier n'est pas arrivé (ou incomplet)… »** (il sera relivré).
4. Saisissez un **commentaire obligatoire** (ce que vous avez vérifié), puis **Valider la décision**.

Une livraison est tranchée à la fois : recommencez pour les suivantes (l'interface indique combien il en reste). Après avoir tranché, demandez une **Reprise** pour que la règle reparte.

### 6.6 Purger

**Purger…** supprime les **journaux** et **archives** plus anciens que la durée de conservation réglée dans le paramétrage. Si une règle est sélectionnée, l'interface demande si la purge ne doit porter que sur elle.

1. L'interface affiche d'abord la **liste** de ce qui serait supprimé (type, règle, date, taille, chemin), les règles non purgeables et les éléments ignorés. **Rien n'est supprimé à ce stade.**
2. **Purger** confirme ; **Fermer sans purger** abandonne. La suppression est **définitive**.

Le job Jenkins de purge fait la même chose chaque jour ; commencez par lire la liste avant d'activer `--appliquer`.

## 7. Actualiser et comprendre un état

**Actualiser l'état** relit le fichier et le statut des règles et conserve la règle sélectionnée. Rien n'est interrogé automatiquement : si vous attendez une règle, cliquez de temps en temps.

Si le bandeau (en haut de l'onglet) indique **« État indisponible : … »**, la liste des règles s'affiche quand même, d'après le fichier, mais sans statut : la base n'est pas initialisée, le moteur est injoignable ou trop ancien. Le message donne la raison.

## 8. Le graphe des dépendances

L'onglet **Dépendances** dessine les règles qui dépendent les unes des autres : chaque règle est **à droite** de celles qu'elle attend, la flèche va de la règle attendue vers celle qui attend. Les règles sans lien ne sont pas dessinées (leur nombre est indiqué).

- La **couleur** est celle du statut ; un nœud estompé est une règle inactive ; l'infobulle donne le motif d'attente.
- Une flèche **rouge** désigne la règle qui retient les autres (règle `EN_ATTENTE` ou `BLOQUEE` dont le motif la nomme).
- Un **clic** sur un nœud sélectionne la règle dans la liste (si un filtre la masque, rien ne se passe : assouplir les filtres).

## 9. Promouvoir une règle d'un environnement à un autre

Pour reprendre une règle validée (par exemple de la recette vers la production) en **adaptant ses chemins** :

1. Sélectionnez la règle, puis **Promouvoir…**.
2. Choisissez l'**environnement cible**, le **texte à remplacer** et le **texte de remplacement** (par exemple `\\serveur-recette\` par `\\serveur-prod\`). Le remplacement est littéral, sans tenir compte de la casse, et s'applique aux dossiers de la règle et à la commande de ses programmes. L'aperçu montre avant et après.
3. L'interface signale si la règle **existe déjà** dans la cible (elle sera remplacée) ou si les règles dont elle dépend **n'y existent pas**.
4. **Continuer vers le formulaire…** : la règle adaptée s'ouvre dans le formulaire de la cible. Vous relisez, puis l'enregistrement suit **exactement** le §5.2 (vérification du moteur, commentaire, version précédente) : la promotion ne contourne aucun contrôle.

Il faut être administrateur et pouvoir modifier l'environnement cible.

## 10. Historique et restauration

**Historique…** liste les modifications faites par l'interface : date, compte, commentaire. Sélectionnez une ligne : la partie droite affiche **ce que cette modification a changé** (règle ajoutée, supprimée, modifiée champ par champ, en-tête), les avertissements acceptés à l'époque, et signale une version sans fiche (copiée à la main : compte et date lus dans le nom du fichier).

Pour **revenir en arrière** (administrateurs) : choisissez la modification à défaire puis **Revenir à l'état d'avant cette modification…**. L'interface indique le nombre de différences avec le fichier actuel : **les modifications faites depuis seront annulées**. Après confirmation, le commentaire est demandé et l'enregistrement suit le §5.2 (le moteur peut avertir qu'une règle disparaît : c'est normal). **Rien n'est effacé** : l'état avant restauration est lui-même conservé, la restauration est une ligne de l'historique et peut être défaite de la même façon.

## 11. Le journal de l'interface

Le panneau du bas montre ce que fait l'interface (ouverture, appels du moteur avec leur code retour et leur durée, enregistrements, actions). Si `Journal.Dossier` est renseigné, le même journal est écrit chaque jour dans un fichier JSON Lines lu par la plateforme de surveillance : dans le format de la plateforme d'observabilité (service `file_management.interface`, `context.utilisateur` = le compte ; une session = une trace) : c'est **la trace de qui a fait quoi** côté interface (la base et le journal du moteur gardent leur propre trace).

## 12. Que faire quand…

| Situation | Action |
|---|---|
| Une règle est `ERREUR` | Lire le motif (onglet État) ; corriger la cause (droits, dossier, programme) ; **Reprise** ; ou **Acquitter** si traité à la main |
| Des règles sont `BLOQUEE` | Regarder le graphe : la flèche rouge désigne la règle en erreur ; la corriger et la reprendre, toute la chaîne repart |
| Une règle est `EN_COURS` depuis trop longtemps | Vérifier sa durée maximale ; en dernier recours **Débloquer** |
| « livraison(s) incertaine(s) » | §6.5 |
| Une règle nouvelle ne part pas | Elle part à son prochain créneau ; **Lancer maintenant** pour la lancer tout de suite |
| On a enregistré une modification par erreur | **Historique…** puis **Revenir à l'état d'avant cette modification…** |
| « Le fichier a été modifié depuis son affichage » | Quelqu'un d'autre a enregistré : l'interface recharge ; refaire sa modification |
| Un bouton est absent | Mode lecture seule (badge orange, ou environnement en lecture seule) |
| Un bouton est grisé | Aucune règle sélectionnée, un appel du moteur est en cours, ou (Trancher…) pas de livraison incertaine |
| « Le dossier des versions n'est pas lisible avec votre compte » | Votre compte n'a pas accès à `versions\` : demander les droits à l'exploitation |

## 13. Gérer les environnements (administrateurs)

**Une seule fenêtre de résultat.** Chaque opération (créer, modifier, copier, créer la base, renommer, supprimer) pose ses **questions** en boîtes Oui / Non (accord pour créer les dossiers, changement de base, suppression), puis rassemble **tout le reste** (enregistrement, dossiers créés, base créée ou non, avertissements, erreurs) dans **une seule fenêtre** à la fin, une ligne par information.

Au-dessus des onglets, la barre **Environnements** n'est visible que pour un administrateur. Toutes ces opérations passent par un brouillon vérifié par le moteur avant l'écriture, et sont **tracées** (journal de l'interface : compte, action, résultat). Le contrôle des droits de l'interface ne remplace pas ceux du dossier de paramétrage (NTFS) : voir [10-installation](10-installation.md).

| Bouton | Ce qu'il fait |
|---|---|
| **Nouvel environnement…** | Formulaire : nom (minuscules, chiffres, `_`, `-`, 32 maximum), **racine** de l'environnement (facultative), racine des sources et des cibles, chemin de la base (local, pas de partage réseau ; partiel sous la racine, par exemple `BDD\preprod.db`, ou complet), dossiers des journaux et de travail (idem : `LOGS`, `TMP`), parallélisme, rétentions, marge d'espace. Refus d'un nom ou d'une base déjà utilisés. Le fichier est écrit **sans règle**, puis les dossiers sont contrôlés (voir ci-dessous) et la base est créée si la case est cochée. Proposé d'office quand le dossier est vide |
| **Modifier / renommer…** | Modifie l'en-tête. **Renommer** change le nom du fichier, de l'environnement dans la base, et de l'historique des versions ; il se fait **seul**, sans autre changement, et est refusé tant qu'une règle s'exécute. Les **jobs Jenkins** qui citent l'ancien nom de fichier restent à modifier. Changer le chemin de la base ne déplace pas l'historique : la nouvelle base démarre vide (confirmation demandée) |
| **Copier vers un nouvel environnement…** | Nouvel environnement avec **toutes les règles** de l'original, même en-tête (le nom, la base et les dossiers propres à chaque environnement sont à saisir). Les règles **gardent leurs répertoires** : s'ils sont partiels (sous la racine des sources / cibles), ils suivent la nouvelle racine sans rien modifier ; s'ils sont complets, c'est à vous de les modifier ensuite. Par défaut elles sont copiées **désactivées**, pour que deux environnements ne livrent pas les mêmes fichiers au même endroit ; décochez la case pour les garder actives |
| **Créer la base…** | Crée la base d'un environnement qui n'en a pas encore ; refuse d'écraser une base existante |
| **Supprimer…** | **Double validation** : (1) un avertissement qui détaille les conséquences, (2) la saisie du **nom exact** de l'environnement et d'un commentaire. Rien n'est effacé : le fichier et ses versions sont rangés dans `.supprimes\<nom>_<date>\` avec une fiche (compte, date, commentaire, chemin de la base) ; pour annuler, remettre le fichier `.jsonl` dans le dossier de paramétrage. La **base, les journaux et les archives ne sont jamais touchés**. Refusé tant qu'une règle s'exécute |

**Racines.** Un chemin *partiel* est placé sous la racine, un chemin *complet* (`D:\LOGS`, `\\serveur\partage`) est conservé ; le `\` final de la racine est facultatif. Avec la racine `D:\Transferts\preprod`, la base `BDD\preprod.db` devient `D:\Transferts\preprod\BDD\preprod.db`. La zone « Chemins complets » de la boîte montre le résultat tel que le moteur l'utilisera. Racine des sources et des cibles : elles complètent les dossiers source / cible partiels des règles ; vides, la racine de l'environnement sert aux deux.

**Dossiers de la base, des journaux et du travail.** Dès que le fichier d'un environnement est écrit (création, copie, modification de ces chemins, bouton « Créer la base… »), l'interface contrôle les trois dossiers là où tourne le moteur. S'il en manque, **une seule question** les liste et propose de les créer (Oui / Non), en rappelant le compte dont les droits sont contrôlés. Oui : ils sont créés (tracé dans le journal), puis la base. Non : le fichier reste créé, la base ne l'est pas, et le message le dit. Un dossier qu'on ne peut pas créer (lecteur introuvable, droits) est signalé en clair. Cette règle vaut pour **tout chemin saisi dans l'outil** : dossier de paramétrage, dossiers d'un environnement, répertoires d'une règle (§5.4) et simulation (§14).

## 13 bis. Les modes `suppression`, `count`, `size` et `synchro`

- **`suppression`** : supprime **définitivement** les fichiers sélectionnés (par exemple ceux de plus de 365 jours : critère d'âge de la sélection). Pas de dossier cible. L'enregistrement affiche un avertissement ; sans critère d'âge ni de date, tous les fichiers du masque sont supprimés à chaque lancement. Commencez toujours par **Simuler la règle** (§14).
- **`count`** / **`size`** : comptent (nombre) ou mesurent (octets) les fichiers sélectionnés et écrivent le résultat dans le journal, sans rien toucher. Avec un `seuil_minimum` et / ou `seuil_maximum`, la règle sort en succès dans les bornes et en **`ATTENTE`** sinon. **Déclencheur** : un flux dépose 5 fichiers ; une règle `count` (minimum 5) attend qu'ils soient là ; la règle de déplacement qui en dépend (condition `succes`) ne part qu'ensuite.
- **`synchro`** : une règle **sans dossier ni heure** qui ne fait que rendre un statut, succès ou erreur, quand les règles dont elle dépend sont terminées. Dans le formulaire, choisissez le mode : les dossiers et les seuils se grisent, la planification passe à « apres_dependances » et il faut remplir **Se lance après** (onglet *Dépendances*). Si vous déclarez un programme **avant le lot** et / ou **avant le fichier** (onglet *Programmes*), il est lancé avant de rendre le statut ; s'il y en a deux, `avant_lot` passe en premier. Le programme doit répondre **0** pour un succès ; tout autre code, y compris 1, est une erreur. Un programme **après** le fichier ou le lot n'a pas de sens ici : il n'est **jamais exécuté** et l'enregistrement vous en avertit.

## 13 ter. Horodater les fichiers traités

Pour les règles en mode `copie` ou `archivage`, cochez **« Horodater les fichiers traités »** (onglet *Général* du formulaire de règle ; la case est grisée pour les autres modes). C'est un simple clic qui laisse une **trace visible du moment du traitement** :

- **copie** : le fichier d'origine, resté dans le dossier source, est renommé `rapport_traite_20261111_103012.csv`. La copie dans la cible garde son nom.
- **archivage** : le fichier rangé dans l'archive porte cette marque.

Les fichiers marqués ne sont plus repris par la règle (ils sont considérés comme traités). Les fichiers déjà copiés avant d'avoir coché la case sont marqués au prochain lancement. Si un fichier est verrouillé au moment du renommage, la règle sort en avertissement et réessaie au lancement suivant.

## 13 quater. Fichier déclencheur, plafond de volume et suspension

- **Fichier déclencheur** (onglet *Général* de la règle) : pour un flux qui dépose ses fichiers puis un fichier témoin (`export.ok`) quand il a fini. Saisissez le nom ou le masque du témoin ; tant qu'il n'est pas à la racine de la source, la règle reste en **ATTENTE** et ne touche à rien. Le témoin n'est jamais livré ; il est supprimé quand le lot est entièrement traité (décochez *Supprimer le témoin après le lot* pour le garder).
- **Fichier témoin dans la cible** (onglet *Général*) : pour un logiciel destinataire qui ne doit lire qu'un lot complet. Saisissez un nom fixe (`fin.ok`) : la règle dépose ce fichier vide dans la cible **après** les fichiers, seulement si le lot s'est bien passé. Le destinataire le supprime quand il a fini ; s'il ne l'a pas fait, la règle le retire avant le lot suivant puis le redépose. Si le témoin ne peut pas être écrit, la règle passe en erreur (les fichiers sont déjà livrés : déposez le témoin à la main).
- **Volume maximum par lot** (onglet *Sélection*) : pour rattraper un gros arriéré sans saturer le réseau, la règle s'arrête avant de dépasser ce nombre d'octets et reprend le reste au lancement suivant. Un fichier plus gros que la limite est quand même pris, seul.
- **Suspendre l'environnement** (boîte « Environnement », administrateurs) : pour une maintenance. Tant que la case est cochée, **aucune règle n'est lancée** et Jenkins reste vert (code 0). Un bandeau le rappelle sur l'onglet. Pensez à la décocher : la plateforme d'observabilité peut vous alerter d'une suspension qui dure (`exemples\loki\regles_alerte.yaml`).
- **Une règle longue n'est pas lancée deux fois** : si Jenkins relance pendant qu'elle tourne encore, le second lancement l'ignore (aucun fichier `.lock` n'est posé dans vos dossiers).

## 14. Simuler une règle

Sélectionnez une règle puis **Simuler la règle…** (tous les comptes) : le moteur dit ce qu'il ferait **maintenant**, sans rien copier, déplacer ni enregistrer. Il faut que la base de l'environnement existe et que la règle soit active.

La fenêtre montre :

- une **phrase** : « Déplacera 12 fichier(s) (3,4 Mo) du répertoire R vers le répertoire D. » (copie : « Copiera… Les originaux restent en place » ; archivage : « …puis archivés dans… ») ;
- le tableau **Contrôles des répertoires** : pour la source, la cible, le dossier temporaire et l'archive : **existe** Oui / Non, **lecture** Oui / Non, **écriture** Oui / Non (« création possible » pour un dossier absent), **espace disque** (libre et nécessaire pour les fichiers listés plus la marge, OK ou INSUFFISANT), **verdict** (OK, A_CREER, PROBLEME) et remarque ;
- la liste des **fichiers concernés** (source, destination, taille, archive), plafonnée à 500 ;
- des remarques : fichiers ignorés (déjà livrés, doublons), avertissements, nombre de problèmes.

Pour un administrateur, le bouton **Créer les dossiers manquants…** apparaît s'il en manque : confirmation, création (source, cible, temporaire, archive), puis la simulation est refaite. La simulation n'attend jamais : pas de temporisation entre tentatives (une source absente est signalée tout de suite).

## 15. Ce que l'interface ne fait pas

- Elle ne lance pas les transferts : c'est Jenkins (ou **Lancer maintenant** / **Reprise**, qui ne font que demander un départ au prochain lancement).
- Elle n'interroge rien automatiquement et ne remplace pas Grafana pour la surveillance continue.
- Elle ne **supprime jamais** une base, un journal ou une archive (la suppression d'un environnement range son fichier, rien d'autre).
- Elle ne modifie pas les jobs Jenkins : après un renommage ou une suppression d'environnement, ils sont à mettre à jour à la main.
