# Fichier de paramétrage

## 1. Principes

- **Un fichier par environnement** : `parametrage\production.jsonl`, `recette.jsonl`… Le nom du fichier (sans extension) est égal à l'environnement déclaré dans l'en-tête.
- **JSON Lines**, UTF-8 avec ou sans BOM : une ligne = un objet JSON. Les lignes vides sont ignorées. Pas de commentaires : utiliser le champ `description`.
- **Ligne 1 : l'en-tête.** Lignes suivantes : une règle par ligne.
- Écrit **uniquement par le front-end** (écriture atomique). Le moteur le lit une fois au démarrage et ne le modifie jamais.
- **Champs inconnus refusés** : une faute de frappe (`si_fichier_verouille`) est une erreur, pas un champ ignoré.
- Le front-end écrit toujours le **réglage complet** de chaque règle. Le moteur connaît aussi des valeurs de secours (§6), pour qu'un fichier plus ancien reste valide si un champ est ajouté dans une version ultérieure du format.
- Les règles sont rangées par le front-end avec les règles dépendantes **après** celles dont elles dépendent.
- Chemins : locaux (`D:\Echanges`) ou UNC (`\\SRV\partage`). Les variables d'environnement `%VAR%` sont acceptées. Dans le JSON, les `\` sont doublés.

## 2. En-tête

```json
{"version": 1, "environnement": "production", "base": "D:\\Copie\\production.db"}
```

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| `version` | entier | oui | Version du format : `1` |
| `environnement` | texte | oui | `[a-z0-9_-]{1,32}`, égal au nom du fichier |
| `code_environnement` | texte | non | **Code d'environnement de la plateforme d'observabilité** (`dev`, `build`, `test`, `pprod`, `prod`, `run`, `int`), écrit dans chaque ligne du journal (`service.environment`). Absent : déduit du nom (`production` → `prod`, `preprod` → `pprod`, `recette` → `test`, `developpement` → `dev`, `integration` → `int`, ou un code lui-même). Un nom dont le code ne se déduit pas (`essai`, `copie`…) **exige** ce champ : refus **E08** sinon |
| `racine` | chemin complet | non | **Racine de l'environnement.** Un chemin partiel de l'en-tête (`base`, `dossier_logs`, `dossier_travail`) ou d'une règle (`dossier_temporaire`, et `source` / `cible` à défaut de racine dédiée) se place sous elle ; un chemin complet est conservé. Le `\` final est facultatif. Copier un environnement n'oblige plus à réécrire tous les chemins : il suffit de changer la racine |
| `racine_source` | chemin | non | Racine des dossiers `source` partiels des règles. Partielle, elle se place elle-même sous `racine`. Absente : `racine` |
| `racine_cible` | chemin | non | Racine des dossiers `cible` partiels des règles. Mêmes règles. Absente : `racine` |
| `base` | chemin | oui | Fichier SQLite (partiel : `BDD\preprod.db` sous la racine). **Disque local**, jamais un chemin UNC |
| `dossier_logs` | chemin | non | Défaut : `logs` à côté de la base |
| `dossier_travail` | chemin | non | Listes de fichiers transmises aux programmes, résultats. Défaut : `travail` à côté de la base |
| `parallele_max` | entier ou `null` | non | Nombre maximum de règles en parallèle. `null` (défaut) : pas de limite |
| `retention_executions_jours` | entier | non | Durée de conservation des exécutions en base. Défaut : `365` |
| `retention_journaux_jours` | entier | non | Durée de conservation des fichiers de journaux (`<règle>_<AAAA-MM-JJ>.jsonl`, `_orchestrateur_…`), d'après la **date inscrite dans leur nom**. Absent : jamais purgés. Peut être surchargé par règle |
| `marge_espace_mo` | entier | non | Espace libre à conserver en plus de la taille des fichiers à livrer, pour la cible et l'archive. Défaut : `64` |
| `suspendu` | booléen | non | **Maintenance** (défaut `false`) : `true` suspend l'environnement, aucune règle n'est lancée (§3.2 quater). Les exécutions déjà en cours ne sont pas interrompues |
| `motif_suspension` | texte | non | Raison de la suspension, écrite au journal et affichée par l'interface |

**Chemins complets et partiels.** Un chemin est *complet* s'il commence par un lecteur (`D:\...`) ou un partage (`\\serveur\partage`). Exemple avec `"racine": "D:\\Transferts\\preprod"` : `"base": "BDD\\preprod.db"` donne `D:\Transferts\preprod\BDD\preprod.db` ; `"dossier_logs": "D:\\LOGS"` reste `D:\LOGS`. Un chemin partiel sans racine est refusé (**E07** pour l'en-tête, **R14** pour une règle). Le dossier d'archive n'est pas touché : relatif, il se calcule depuis la source à chaque lancement.

## 3. Règle : référence des champs

Les durées sont des **entiers**, l'unité figure dans le nom du champ (`_sec`, `_jours`, `_octets`, `_mo`).

### 3.1 Identification

| Champ | Type | Oblig. | Défaut | Description |
|---|---|---|---|---|
| `id` | texte | oui | — | `[A-Za-z0-9_-]{1,64}`, unique (sans tenir compte de la casse). **Ne doit jamais être modifié** : l'historique y est rattaché |
| `description` | texte | non | `""` | Libellé libre |
| `actif` | booléen | oui | `true` | Une règle inactive n'est jamais lancée |

### 3.2 Source, cible, mode

| Champ | Type | Oblig. | Défaut | Description |
|---|---|---|---|---|
| `source` | chemin | oui, sauf `synchro` | — | Dossier à lire. **Refusé** avec `synchro` (**R17**) |
| `cible` | chemin | si `mode` = `copie`, `deplacement` ou `archivage` | — | Dossier de dépôt. Créé s'il n'existe pas et si `creer_dossiers`. Sans objet (ignoré, **R16**) pour `suppression`, `count`, `size` ; **refusé** avec `synchro` (**R17**) |
| `mode` | texte | oui | — | `copie` : l'original reste en place ; `deplacement` : l'original est supprimé après copie vérifiée ; `archivage` : l'original est déplacé dans `archive` après copie vérifiée ; `suppression` : **supprime définitivement** les fichiers sélectionnés (avertissement **R15**) ; `count` / `size` : comptent / mesurent les fichiers sélectionnés et les comparent aux seuils, sans rien toucher ; `synchro` : aucun dossier, retourne seulement un statut (§3.2 quater) |
| `seuil_minimum`, `seuil_maximum` | entier ou `null` | non | `null` | Modes `count` (nombre de fichiers) et `size` (octets) seulement. En dessous du minimum ou au-dessus du maximum, la règle sort en **ATTENTE** (§3.2 bis). Ignorés avec un autre mode (**R16**) ; minimum > maximum : refus (**R07**) |
| `archive` | chemin ou `null` | si `mode = archivage` | `null` | Absolu (`C:\archive`) ou relatif (`.\archive`, calculé depuis la **racine** de `source`). Variables de date acceptées (§5.2) |
| `creer_dossiers` | booléen | non | `true` | Créer `cible` et `archive` s'ils n'existent pas, au lancement. La **source** n'est jamais créée au lancement (un administrateur peut la créer sur demande depuis l'interface) |
| `horodater` | booléen | non | `false` | Modes `copie` et `archivage` seulement : garde une **trace visible du moment du traitement** (§3.2 ter). Ignoré avec un autre mode (**R16**) |
| `fichier_declencheur` | texte ou `null` | non | `null` | Nom ou masque d'un **fichier témoin** (`*.ok`, `FIN.done`) que le flux dépose à la **racine de la source** une fois son dépôt terminé (§3.2 quater). Absent : la règle sort en `ATTENTE` sans rien toucher. Un chemin (`\`, `/`, `;`, `:`) est refusé (**R06**). Avec `synchro` : ignoré (**R16**) |
| `consommer_declencheur` | booléen | non | `true` | Supprimer le témoin quand le lot est entièrement traité sans erreur. `false` : le témoin reste |
| `temoin_cible` | texte ou `null` | non | `null` | Nom **fixe** (`fin.ok`) d'un fichier vide déposé à la **racine de la cible** quand le lot est livré sans erreur, pour le logiciel destinataire (§3.2 quater). Modes `copie`, `deplacement`, `archivage` ; ignoré avec un autre mode (**R16**). Nom avec chemin, masque ou `;` : refusé (**R06**) |
| `dossier_temporaire` | chemin ou `null` | non | `null` | Dossier où écrire les fichiers en cours de copie. `null` : dans `cible`, avec le suffixe `.copie_en_cours`. Si renseigné, il doit être **sur le même volume que `cible`** (renommage atomique) et hors du périmètre surveillé par le logiciel destinataire |

### 3.2 bis Modes `suppression`, `count` et `size`

- **`suppression`** : supprime définitivement les fichiers sélectionnés (masque, âge, date). Exemple : `"selection": {"masque": "*.log", "age_minimum_sec": 31536000}` supprime les journaux de plus de 365 jours. Sans critère d'âge ni de date, **tous** les fichiers du masque sont supprimés à chaque lancement : le diagnostic **R15** le précise. L'interface avertit à l'enregistrement et la simulation annonce « supprimera DÉFINITIVEMENT ». Pas de cible ni d'archive.
- **`count`** et **`size`** : comptent (nombre de fichiers) ou mesurent (octets) les fichiers sélectionnés, inscrivent le résultat au journal et le comparent à `seuil_minimum` / `seuil_maximum`. Aucun fichier n'est touché. Résultat dans les bornes : **succès**. Hors bornes : statut d'exécution **`ATTENTE`**, ni succès ni erreur (bilan `SUCCES`, code retour 0).
- **Déclencheur.** Un flux SSIS dépose 5 fichiers : une règle `count` (`seuil_minimum: 5`) sort en `ATTENTE` tant qu'il en manque ; la règle de déplacement qui en dépend (`apres` avec `condition: succes`) **patiente** (statut `EN_ATTENTE`) au lieu d'être bloquée, et part dès que le `count` sort en succès. Une règle en `ATTENTE` ne compte pas comme un succès pour les dépendances.

### 3.2 quater Mode `synchro`

Une règle qui **ne fait qu'une chose : retourner un statut** (`SUCCES` ou `ERREUR`) une fois ses dépendances satisfaites. Elle sert de point de synchronisation : les règles qui en dépendent (`apres` + `condition`) partent quand elle réussit, et peuvent lancer un programme externe juste avant.

- **Aucun dossier** : `source`, `cible`, `archive` et `dossier_temporaire` sont **refusés** (**R17**). Les champs de fichiers (`selection`, `horodater`, seuils, renommages, anti-doublon, rétentions autres que celle par défaut) sont ignorés avec un avertissement (**R16**) s'ils ont une valeur autre que celle par défaut.
- **Aucune heure** : la planification est obligatoire et ne peut être que `apres_dependances` (**P01** sinon), ce qui impose une liste `apres` (**D06** sinon). Pas d'heure de début ni de fin.
- **Programmes** : si `programmes.avant_lot` et / ou `programmes.avant_fichier` existent, le moteur les lance **dans cet ordre** (`avant_lot` puis `avant_fichier`, quel que soit l'ordre d'écriture dans le fichier) avant de rendre son statut. Un seul des deux suffit. Les variables `{source}`, `{cible}`, `{archive}`, `{fichier}`, `{nom}`, `{fichier_cible}`, `{liste}`, `{liste_json}` n'existent pas ici (**G01**) : seules `{environnement}`, `{regle}` et `{date}` sont admises.
- **Programmes `apres_fichier` et `apres_lot`** : rien ne s'exécute après le statut ; ils sont acceptés mais **jamais lancés**, et le diagnostic **R18** en prévient. `sur_erreur` (notification) et `reprise` restent actifs.
- **Statut** : `SUCCES` si les programmes présents ont tous répondu **0** (ou s'il n'y en a pas) ; `ERREUR` sinon. Contrairement aux autres modes, le code **1** n'est pas « rien à faire » : la règle ne peut dire que oui ou non, il est donc une erreur. Une durée maximale dépassée ou un lancement impossible sont aussi des erreurs. Les situations `programme_avant_lot` / `programme_avant_fichier` (tentatives, délai, niveau) s'appliquent ; la suite `fichier_suivant` n'a pas de sens ici et vaut `arreter_regle`.
- **Journal** : événements `programme_appele` (un par programme) puis `regle_terminee`. Aucun fichier n'est lu, créé ni supprimé.

### 3.2 ter Horodater les fichiers traités (`horodater`)

Case à cocher de la règle (modes `copie` et `archivage`). Le nom reçoit la marque `_traite_AAAAMMJJ_hhmmss` avant l'extension (`a.csv` → `a_traite_20261111_103012.csv` ; `_2`, `_3`… si ce nom existe déjà). L'heure est celle du traitement du fichier.

- **`copie`** : l'original, laissé dans la **source**, est renommé **après** la copie vérifiée (et après le programme `apres_fichier`, qui voit encore le nom d'origine). La copie dans la cible garde son nom. Le renommage n'a lieu que si l'original est inchangé depuis la copie (sinon il est conservé tel quel et sera livré comme une nouvelle version). Un échec (fichier verrouillé…) est un **avertissement** : le fichier est livré, et la marque est reposée au lancement suivant.
- **`archivage`** : le fichier **archivé** porte la marque (après `renommage_archive` s'il y en a un). La cible garde le nom d'origine.
- **Fichiers déjà marqués.** Avec l'option, un fichier dont le nom porte la marque est considéré comme traité : il n'est plus sélectionné (c'est ce qui évite de recopier à l'infini les originaux marqués). Une date ordinaire dans un nom (`export_20261111_103012.csv`) n'est **pas** une marque. Si l'option est retirée plus tard, les fichiers marqués redeviennent des candidats ordinaires.
- **Fichiers déjà copiés avant l'activation.** Ils sont marqués au lancement suivant (l'heure est alors celle de ce lancement).
- Sans effet en simulation (rien n'est renommé).

### 3.2 quater Fichier déclencheur, plafond de volume et suspension

**Fichier déclencheur (`fichier_declencheur`).** Pour un flux qui dépose plusieurs fichiers puis un témoin (`export.ok`) quand il a fini : la règle ne prend **rien** tant que le témoin n'est pas à la racine de la source (statut **`ATTENTE`**, événement `declencheur_absent`, comme un seuil non atteint : les règles qui en dépendent patientent). Témoin présent (`declencheur_present`) : le lot est traité normalement ; le témoin lui-même n'est **jamais** livré ni compté, même s'il correspond au masque. Il est supprimé (`declencheur_consomme`) seulement si `consommer_declencheur` est vrai **et** que le lot est complet : un lot tronqué par `limite_fichiers` / `limite_octets`, ou en erreur, garde son témoin et la suite part au lancement suivant. Un échec de suppression est un avertissement (`declencheur_non_supprime`) : les fichiers déjà livrés ne le sont pas deux fois. Sans effet en simulation. 
**Témoin côté cible (`temoin_cible`).** Pour un logiciel destinataire qui ne doit lire les fichiers qu'une fois le lot complet : la règle dépose un fichier **vide** nommé `temoin_cible` à la racine de la cible, après la livraison de tous les fichiers du lot **et** après le programme `apres_lot`, si au moins un fichier a été livré **sans erreur** (événement `temoin_cible_depose`). Un lot tronqué par une limite compte comme un lot complet. Le fichier est écrit sous un nom temporaire puis renommé : le destinataire ne voit jamais un témoin à moitié écrit. Un témoin du lot précédent que le destinataire n'a pas consommé est **retiré avant** la livraison suivante (`temoin_cible_retire`), puis redéposé à la fin : il ne peut pas annoncer un lot en cours d'écriture. Aucun fichier livré : aucun témoin. Une erreur sur un fichier : pas de témoin (le lot est repris au lancement suivant). **Échec d'écriture du témoin** : la règle s'arrête sur la situation `cible_inaccessible` (les fichiers sont déjà livrés et ne le seront pas deux fois : après correction, déposer le témoin à la main). Sans effet en simulation.

**Plafond de volume (`selection.limite_octets`).** Complète `limite_fichiers` : le lot s'arrête **avant** de dépasser ce nombre d'octets cumulés (événement `limite_octets_atteinte` : retenus, restants). Le **premier fichier est toujours pris**, même plus gros que la limite (`limite_octets_depassee`) : sinon il bloquerait le flux pour toujours. Le reste attend le lancement suivant (rattrapage progressif). Appliqué après `limite_fichiers`, aux modes de livraison et de suppression.

**Suspension d'environnement (`suspendu`, `motif_suspension`).** À `true`, le lancement n'évalue ni ne démarre aucune règle : il écrit un seul événement `environnement_suspendu` (INFO, avec le motif) et sort avec le **code 0** (Jenkins ne passe pas au rouge). Les exécutions déjà en cours ne sont pas interrompues. La simulation reste possible. `--etat` renvoie `suspendu` et `motif_suspension` ; le contrôle du paramétrage émet l'information **S01**. Pour reprendre : remettre `false` (ou retirer la clé).

### 3.3 Sélection

```json
"selection": {"masque": "*.csv", "exclure": "~*;*.tmp", "recursif": false,
              "modifie_depuis": "J-1", "age_minimum_sec": 60, "age_maximum_sec": null,
              "taille_minimum_octets": 1, "ordre": "date_modification", "limite_fichiers": null}
```

| Champ | Type | Défaut | Description |
|---|---|---|---|
| `masque` | texte | `*` | Un ou plusieurs motifs séparés par `;` (`FACT_*.xml;FACT_*.pdf`) |
| `exclure` | texte | `""` | Motifs à exclure, même syntaxe |
| `recursif` | booléen | `false` | Parcourt les sous-dossiers et reproduit l'arborescence |
| `modifie_depuis` | texte | `TOUT` | `TOUT`, `J` (depuis aujourd'hui 00h00), `J-N` (depuis il y a N jours, 00h00). Heure locale du serveur d'exécution |
| `age_minimum_sec` | entier ou `null` | `null` | Ignore pour ce lancement les fichiers modifiés depuis **moins** de N secondes (fichier encore en écriture) |
| `age_maximum_sec` | entier ou `null` | `null` | Ignore les fichiers modifiés depuis **plus** de N secondes (fenêtre glissante, contrairement à `J-N` qui part de minuit) |
| `taille_minimum_octets` | entier ou `null` | `null` | `1` exclut les fichiers vides |
| `ordre` | texte | `nom` | `nom` ou `date_modification` (du plus ancien au plus récent) |
| `limite_fichiers` | entier ou `null` | `null` | Nombre maximum de fichiers livrés par exécution (rattrapage progressif) |
| `limite_octets` | entier ou `null` | `null` | Volume maximum (octets) d'un lot ; le premier fichier est toujours pris (§3.2 quater) |

Le dossier d'archive est **toujours exclu** du parcours de la source.

### 3.4 Anti-doublon et nommage

| Champ | Type | Défaut | Description |
|---|---|---|---|
| `identite` | texte | `version` | `version` : un fichier est identique s'il a même nom, même taille et même date de modification. `contenu` : identique s'il a même nom et même SHA-256 (voir le point à valider n° 1 de la vue d'ensemble) |
| `retention_historique_jours` | entier | `90` | Durée pendant laquelle un fichier **non revu** reste mémorisé. Doit être **supérieure** à la fenêtre `modifie_depuis` |
| `retention_journaux_jours` | entier | *(en-tête)* | Durée de conservation des journaux de **cette** règle. Absent : valeur de l'en-tête, sinon jamais purgés |
| `retention_archive_jours` | entier | *(aucune)* | Mode `archivage` seulement : les **dossiers d'archive datés** dont la date (fin de période) dépasse cette durée sont supprimés avec leur contenu. Absent : l'archive n'est **jamais** purgée. Exige une archive datée (R13) |
| `si_cible_absente` | texte | `ignorer` | Mode `copie` : `ignorer` si la copie a disparu de la cible (le destinataire l'a prise) ; `recopier` pour une synchronisation |
| `si_existe_cible` | texte | `erreur` | Un fichier du même nom attend déjà dans la cible : `erreur`, `ecraser`, `ignorer`, `suffixe` (horodatage ajouté au nom) |
| `si_existe_archive` | texte | `suffixe` | Même cas dans l'archive : `suffixe`, `ecraser`, `erreur` |
| `renommage_cible` | texte ou `null` | `null` | Modèle du nom déposé (§5.2). `null` : nom conservé |
| `renommage_archive` | texte ou `null` | `null` | Modèle du nom archivé. `null` : nom conservé |

### 3.5 Planification

Le moteur est lancé souvent par Jenkins (toutes les 1 ou 5 minutes). Chaque règle déclare **quand** elle est à exécuter.

```json
"planification": {"type": "intervalle", "frequence_sec": 300, "debut": "05:00", "fin": "19:00",
                  "jours": "lun-ven", "rattrapage_sec": null}
"planification": {"type": "quotidien", "heure": "07:15", "jours": "tous", "rattrapage_sec": 14400}
"planification": {"type": "apres_dependances"}
```

| Type | Champs | Créneaux |
|---|---|---|
| `intervalle` | `frequence_sec`, `debut`, `fin`, `jours`, `rattrapage_sec` | `debut`, `debut + frequence_sec`, … jusqu'à `fin` inclus, les jours indiqués |
| `quotidien` | `heure`, `jours`, `rattrapage_sec` | Un créneau par jour indiqué, à `heure` |
| `apres_dependances` | — | Pas d'horaire : la règle part dès que ses dépendances sont remplies (§3.6) |

- Heures au format `HH:MM`, **heure locale** du serveur d'exécution.
- `jours` : `tous`, `lun-ven`, `lun,mer,ven`.
- Règles de décision au §4 de [02-moteur](02-moteur.md).

### 3.6 Dépendances

| Champ | Type | Défaut | Description |
|---|---|---|---|
| `apres` | liste d'`id` | `[]` | Règles qui doivent avoir terminé avant cette règle |
| `condition` | liste | `["succes"]` | `termine` : finie, quel que soit le résultat ; `succes` : finie sans erreur ; `fichiers` : a livré au moins un fichier. Les conditions se cumulent |
| `si_condition_non_remplie` | texte | `WARNING` | Niveau signalé quand la règle ne peut pas partir : `INFO`, `WARNING`, `ERREUR` |

La condition porte sur ce que les règles dont on dépend ont fait **depuis le dernier lancement de cette règle**. Sémantique complète au §3 de [02-moteur](02-moteur.md).

### 3.7 Durée, erreurs, reprise

| Champ | Type | Défaut | Description |
|---|---|---|---|
| `duree_max_sec` | entier | `1800` | Durée maximale d'une exécution. Le front-end propose le double des attentes prévues |
| `si_duree_depassee` | texte | `erreur` | `erreur` : arrêt de l'arbre de processus, statut `ERREUR` ; `relancer` : arrêt puis relance immédiate ; `alerter` : on laisse tourner, statut `WARNING` |
| `relances_max` | entier | `2` | Nombre de relances consécutives si `si_duree_depassee = relancer` |
| `apres_erreur` | texte | `arreter` | `arreter` : la règle ne repart qu'après une reprise ou un acquittement ; `continuer` : elle repart au créneau suivant |

### 3.8 Situations et réactions

Chaque situation anormale a sa réaction. Le champ `situations` est un objet dont les clés sont les situations de la liste du §6.

```json
"situations": {
  "aucun_fichier":      {"tentatives": 3, "delai_sec": 300, "niveau_final": "ERREUR"},
  "fichier_verrouille": {"tentatives": 5, "delai_sec": 60,  "niveau_final": "ERREUR", "suite": "arreter_regle"},
  "archive_inaccessible": {"tentatives": 3, "delai_sec": 30, "niveau_final": "WARNING", "suite": "continuer_en_differe"}
}
```

| Champ | Description |
|---|---|
| `tentatives` | Nombre total d'essais, premier compris. `1` = pas de boucle |
| `delai_sec` | Attente entre deux essais, dans le même lancement |
| `niveau_final` | Niveau journalisé après le dernier essai : `INFO`, `WARNING`, `ERREUR` |
| `suite` | Que faire ensuite (selon la situation, voir §6) : `fichier_suivant`, `arreter_regle`, `continuer_en_differe` |

### 3.9 Programmes externes

```json
"programmes": {
  "avant_lot":     {"commande": ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "D:\\Scripts\\valider.ps1", "-Liste", "{liste}"], "timeout_sec": 600},
  "avant_fichier": null,
  "apres_fichier": null,
  "apres_lot":     {"commande": ["python", "D:\\Scripts\\notifier.py", "{regle}"], "timeout_sec": 60},
  "sur_erreur":    null,
  "reprise":       {"commande": ["python", "D:\\Scripts\\nettoyage.py", "{source}"], "timeout_sec": 300}
}
```

- `commande` : **tableau** de textes. Le premier élément est l'exécutable. Aucun shell n'est utilisé.
- Variables remplacées dans chaque élément : `{environnement}` `{regle}` `{source}` `{cible}` `{archive}` `{date}` à tous les points d'appel ; `{fichier}` `{nom}` `{fichier_cible}` seulement pour `avant_fichier` et `apres_fichier` ; `{liste}` `{liste_json}` seulement pour `avant_lot`, `apres_lot` et `sur_erreur`. Une variable sans objet à un point d'appel est refusée (G01).
- Les mêmes informations sont transmises en variables d'environnement (`COPIE_REGLE`, `COPIE_FICHIER`, `COPIE_LISTE`, `COPIE_REPRISE`, `COPIE_SIMULATION`, …).
- Comportement, codes retour : §9 de [02-moteur](02-moteur.md).
- Éviter les fichiers `.bat` qui reçoivent des noms de fichiers : `cmd.exe` réinterprète `&`, `^`, `%`.

## 4. Exemple complet

Chaque règle tient sur **une seule ligne** dans le fichier ; elle est présentée sur plusieurs lignes pour la lecture.

```json
{"version": 1, "environnement": "production", "base": "D:\\Copie\\production.db"}
```

```json
{
  "id": "export_clients", "description": "Export clients vers le SFTP du partenaire", "actif": true,
  "source": "\\\\SRV-PROD01\\exports\\clients", "cible": "D:\\SFTP\\out\\clients",
  "mode": "archivage", "archive": ".\\archive\\{AAAA}-{MM}-{JJ}", "creer_dossiers": true,
  "dossier_temporaire": "D:\\SFTP\\tmp",
  "selection": {"masque": "*.xml;*.json", "exclure": "~*", "recursif": false, "modifie_depuis": "TOUT",
                "age_minimum_sec": 60, "age_maximum_sec": null, "taille_minimum_octets": 1,
                "ordre": "date_modification", "limite_fichiers": null},
  "identite": "version", "retention_historique_jours": 90, "si_cible_absente": "ignorer",
  "si_existe_cible": "erreur", "si_existe_archive": "suffixe",
  "renommage_cible": "{nom}_{AAAA}{MM}{JJ}_{hh}{mm}{ss}{ext}", "renommage_archive": null,
  "planification": {"type": "intervalle", "frequence_sec": 300, "debut": "05:00", "fin": "19:00", "jours": "lun-ven", "rattrapage_sec": null},
  "apres": [], "condition": ["succes"], "si_condition_non_remplie": "WARNING",
  "duree_max_sec": 1800, "si_duree_depassee": "erreur", "relances_max": 2, "apres_erreur": "arreter",
  "situations": {
    "aucun_fichier": {"tentatives": 1, "delai_sec": 0, "niveau_final": "INFO"},
    "fichier_verrouille": {"tentatives": 5, "delai_sec": 60, "niveau_final": "ERREUR", "suite": "arreter_regle"},
    "archive_inaccessible": {"tentatives": 3, "delai_sec": 30, "niveau_final": "WARNING", "suite": "continuer_en_differe"}
  },
  "programmes": {"avant_lot": null, "avant_fichier": null, "apres_fichier": null, "apres_lot": null, "sur_erreur": null, "reprise": null}
}
```

```json
{
  "id": "import_catalogue", "actif": true,
  "source": "D:\\Echanges\\catalogue", "cible": "\\\\SRV-ERP01\\import\\catalogue", "mode": "deplacement",
  "selection": {"masque": "CATALOGUE_*.csv", "recursif": false, "modifie_depuis": "TOUT", "age_minimum_sec": 30},
  "planification": {"type": "quotidien", "heure": "07:15", "jours": "tous", "rattrapage_sec": 14400},
  "apres": ["export_clients", "export_produits", "export_tarifs"], "condition": ["succes", "fichiers"],
  "si_condition_non_remplie": "WARNING",
  "duree_max_sec": 3600, "si_duree_depassee": "erreur", "apres_erreur": "arreter",
  "situations": {"aucun_fichier": {"tentatives": 3, "delai_sec": 300, "niveau_final": "ERREUR"}}
}
```

## 5. Modèles et variables

### 5.1 Variables de date

`{AAAA}` année, `{MM}` mois, `{JJ}` jour, `{hh}` heure, `{mm}` minute, `{ss}` seconde. Elles prennent la valeur du **début du lancement** (identique pour tous les fichiers d'un même lancement). Elles sont utilisables dans `archive` et dans les modèles de renommage.

### 5.2 Modèles de nom

`{nom}` : nom sans extension, `{ext}` : extension avec le point. Les modèles de renommage s'appliquent au nom du fichier, pas au chemin. Un modèle qui produit un nom invalide pour Windows est refusé à l'exécution (situation `copie_echec`).

## 6. Situations, valeurs de secours et `suite`

Les valeurs ci-dessous s'appliquent à une situation absente du fichier. Le front-end les propose à la création d'une règle. **Seules les valeurs par défaut de `suite` (`arreter_regle`), `apres_erreur`, `si_duree_depassee` et `si_cible_absente` sont validées ; le reste est une proposition.**

| Situation | Exemple | tent. | délai | niveau | `suite` autorisées (défaut en gras) |
|---|---|---|---|---|---|
| `source_inaccessible` | partage coupé, droits manquants | 3 | 30 | ERREUR | **arreter_regle** |
| `cible_inaccessible` | idem côté cible, création impossible | 3 | 30 | ERREUR | **arreter_regle** |
| `archive_inaccessible` | dossier absent et non créable | 3 | 30 | WARNING | arreter_regle, **continuer_en_differe** |
| `espace_insuffisant_cible` | disque cible presque plein | 1 | 0 | ERREUR | **arreter_regle** |
| `espace_insuffisant_archive` | idem pour l'archive | 1 | 0 | WARNING | arreter_regle, **continuer_en_differe** |
| `aucun_fichier` | rien à livrer | 1 | 0 | INFO | — |
| `fichier_verrouille` | ouvert en écriture par la production | 5 | 60 | ERREUR | fichier_suivant, **arreter_regle** |
| `fichier_instable` | modifié pendant la copie | 3 | 30 | WARNING | fichier_suivant, **arreter_regle** |
| `fichier_disparu` | pris par un autre logiciel entre le listage et la copie | 1 | 0 | INFO | **fichier_suivant**, arreter_regle |
| `copie_echec` | écriture impossible, disque plein, réseau | 3 | 10 | ERREUR | fichier_suivant, **arreter_regle** |
| `verification_echec` | taille ou SHA-256 différents | 3 | 10 | ERREUR | fichier_suivant, **arreter_regle** |
| `fichier_existe_cible` | si `si_existe_cible = erreur` | 1 | 0 | ERREUR | fichier_suivant, **arreter_regle** |
| `fichier_existe_archive` | si `si_existe_archive = erreur` | 1 | 0 | ERREUR | fichier_suivant, **arreter_regle** |
| `source_modifiee` | nouvelle version arrivée avant suppression ou archivage : l'original est conservé | 1 | 0 | WARNING | **fichier_suivant** |
| `suppression_echec` | original verrouillé (mode `deplacement`) | 3 | 10 | WARNING | arreter_regle, **continuer_en_differe** |
| `archivage_echec` | original verrouillé (mode `archivage`) | 3 | 10 | WARNING | arreter_regle, **continuer_en_differe** |
| `doublon_contenu` | mode `identite = contenu`, contenu déjà livré | 1 | 0 | INFO | **fichier_suivant** |
| `programme_avant_lot` | erreur ou durée dépassée | 1 | 0 | ERREUR | **arreter_regle** |
| `programme_avant_fichier` | idem | 1 | 0 | ERREUR | fichier_suivant, **arreter_regle** |
| `programme_apres_fichier` | l'original n'est ni supprimé ni archivé | 1 | 0 | ERREUR | fichier_suivant, **arreter_regle** |
| `programme_apres_lot` | niveau seulement | 1 | 0 | ERREUR | — |
| `programme_reprise` | erreur du programme de reprise | 1 | 0 | ERREUR | **arreter_regle** |

Sens de `suite` :

- `fichier_suivant` : le fichier est abandonné pour ce lancement, les suivants sont traités. Déconseillé quand le destinataire exige les fichiers dans l'ordre.
- `arreter_regle` : la règle s'arrête, aucun fichier suivant n'est traité.
- `continuer_en_differe` : la livraison continue ; l'action manquante (archivage, suppression) est mémorisée en base et retentée aux lancements suivants.

Le **niveau final** détermine le statut de l'exécution : `ERREUR` → statut `ERREUR`, `WARNING` → statut `WARNING`, `INFO` → n'influence pas le statut.

## 7. Contrôles de validation

Ces contrôles sont réalisés **par le moteur** (`file_management.py --verifier`, à chaque démarrage et à la demande du front-end). Le front-end affiche les codes et ne refait pas la logique, sauf les contrôles de saisie simples (champ vide, format de l'heure). Gravité : **refus** = enregistrement impossible et rien n'est lancé (code retour 2) ; **avert.** = enregistrement possible, avertissement affiché.

### 7.1 Syntaxe et cohérence (`--verifier --syntaxe-seule`)

| Code | Gravité | Contrôle |
|---|---|---|
| E01 | refus | La première ligne est un en-tête valide |
| E02 | refus | La version du format est supportée |
| E03 | refus | `environnement` valide et égal au nom du fichier |
| E04 | refus | `base` renseigné |
| E05 | refus | `base` n'est pas un chemin réseau (SQLite en mode WAL ne le supporte pas) |
| E06 | refus | Ligne JSON invalide, champ inconnu ou de mauvais type (avec le numéro de ligne) |
| E07 | refus | `racine`, `racine_source` ou `racine_cible` non complète ; chemin partiel de l'en-tête sans racine pour le compléter |
| E08 | refus | `code_environnement` hors de la liste de la plateforme, ou absent alors que le nom de l'environnement ne permet pas de le déduire |
| R01 | refus | Champs obligatoires présents (`id`, `source`, `mode`, `planification`, et `cible` pour les modes de transfert) |
| R02 | refus | `id` valide et unique, sans tenir compte de la casse |
| R03 | refus | `source` différente de `cible` ; en mode récursif, `cible` hors de `source` |
| R04 | refus | `mode = archivage` impose `archive` |
| R05 | avert. | `archive` renseigné alors que le mode n'est pas `archivage` : ignoré |
| R06 | refus | Valeur hors liste (mode, niveaux, `suite` non autorisée pour la situation, `ordre`, `identite`…) ; `fichier_declencheur` ou `temoin_cible` contenant un chemin ou un masque (`temoin_cible`) |
| R07 | refus | Nombres hors bornes (`tentatives` < 1, `delai_sec` < 0, `age_minimum_sec` ≥ `age_maximum_sec`…) |
| R08 | refus | `retention_historique_jours` doit être supérieure à la fenêtre de sélection, quand il y en a une (`modifie_depuis = J-N`, ou `age_maximum_sec`) |
| R14 | refus | `source`, `cible` ou `dossier_temporaire` partiel alors que l'en-tête n'a pas de racine pour le compléter |
| R15 | avert. | Mode `suppression` : suppression définitive des fichiers sélectionnés (précise s'il n'y a ni âge ni date) |
| R16 | avert. | Champ sans effet pour le mode : `cible` avec `suppression` / `count` / `size`, seuils avec un autre mode, `horodater` avec un mode autre que `copie` / `archivage`, `temoin_cible` avec un mode sans cible, champs de fichiers avec `synchro` (y compris `fichier_declencheur` et `temoin_cible`) |
| R17 | refus | Mode `synchro` : `source`, `cible`, `archive` ou `dossier_temporaire` renseigné |
| R18 | avert. | Mode `synchro` : programme `apres_fichier` ou `apres_lot` déclaré, jamais exécuté |
| S01 | info | Environnement suspendu (`suspendu` = `true`) : aucune règle n'est lancée |
| R13 | refus | `retention_archive_jours` sans mode `archivage`, ou avec une archive sans date (`{AAAA}` absent) : la date du dossier est la seule date d'archivage fiable (un déplacement conserve la date de modification d'origine) |
| R09 | avert. | `duree_max_sec` inférieure à la somme des attentes prévues dans `situations` |
| R10 | avert. | Deux règles avec la même source, cible et masque |
| R11 | avert. | Deux règles écrivent dans la même cible sans dépendance entre elles |
| R12 | avert. | Variable inconnue dans `archive` ou dans un modèle de renommage |
| P01 | refus | Planification invalide (type, heures, `debut` < `fin`, `jours`) |
| P02 | avert. | `frequence_sec` inférieure à la période du déclencheur Jenkins |
| D01 | refus | `apres` référence une règle qui n'existe pas |
| D02 | refus | Boucle de dépendances |
| D03 | refus | Règle **active** qui dépend d'une règle **inactive** (valable aussi dans l'autre sens : on ne peut pas désactiver une règle dont dépendent des règles actives) |
| D04 | avert. | La règle dépendante démarre **avant** celle dont elle dépend (`debut` ou `heure`) : elle lirait le résultat de la veille |
| D05 | avert. | La règle dépendante est plus fréquente que sa dépendance |
| D06 | refus | `condition` inconnue ; `condition` ou `apres_dependances` sans `apres` |
| G01 | refus | `commande` : tableau non vide de textes, variables connues, `timeout_sec` > 0 |

### 7.2 Comparaison avec la version précédente (front-end)

| Code | Gravité | Contrôle |
|---|---|---|
| V01 | refus | Un `id` existant ne peut pas être modifié |
| V02 | avert. | Une règle qui avait un historique est supprimée : son état et ses fichiers mémorisés restent en base |
| V03 | avert. | La sélection est élargie (`modifie_depuis`, masque) : des fichiers anciens pourraient être livrés |
| V04 | avert. | `cible` modifiée : les fichiers **déjà livrés ne sont pas relivrés** (l'empreinte ne contient pas la cible), seuls les nouveaux iront vers la nouvelle cible |

### 7.3 Accès (`--verifier` complet, exécuté sur le serveur d'exécution avec le compte de service)

| Code | Gravité | Contrôle |
|---|---|---|
| A01 | refus | `source` existe et est lisible |
| A02 | refus | `cible` existe ou peut être créée ; écriture vérifiée par un fichier d'essai créé puis supprimé |
| A03 | avert. | `archive` : idem, si renseignée |
| A04 | refus | Les exécutables des programmes existent |
| A05 | refus | La base est accessible en écriture |
| A06 | avert. | Les dossiers de journaux et de travail sont accessibles en écriture |
| A07 | info | Espace disponible pour le compte de service sur `cible` et `archive` (information) |

Le résultat est disponible en texte et en JSON (`--format json`) :

```json
{"ok": false, "refus": [{"code": "D03", "regle": "import_catalogue", "message": "dépend de export_produits, qui est inactive"}],
 "avertissements": [{"code": "D04", "regle": "import_catalogue", "message": "démarre à 06:00, avant export_clients (07:00)"}]}
```

### 7.3 bis Précisions apportées par l'implémentation (J8)

- **Où et avec quel compte** : `--verifier` sans `--syntaxe-seule` doit être lancé **sur le serveur d'exécution avec le compte de service** (ou via le point de terminaison JEA qui l'utilise) : les droits et les quotas contrôlés sont ceux du compte qui exécute la commande.
- **Aucun effet de bord** : les essais d'écriture créent puis suppriment `.test_ecriture_<pid>` dans un dossier existant ; aucun dossier n'est créé. Un dossier absent est jugé d'après son plus proche parent existant (« sera créé dans… »), et refusé si `creer_dossiers` vaut `false`. Un dossier existant n'est testé qu'une fois, même si des centaines de règles l'utilisent.
- **A02** couvre aussi `dossier_temporaire` (écriture, et **même volume que la cible**). **A03** n'est contrôlé qu'en mode `archivage` ; un échec est un avertissement car la livraison continue en mode dégradé. **A04** : l'exécutable est cherché par son chemin ou dans le `PATH` ; si son nom contient une variable (`{source}\x.exe`) il n'est pas vérifiable à l'avance. **A05** : base absente, d'un autre environnement, sur un lecteur réseau ou verrouillée ; une transaction d'écriture vide prouve l'accès. **A06** : dossiers de journaux et de travail (leur absence de droits n'arrête rien : repli sur le fichier de secours, résultat des fils relu en base).
- **Règles inactives** : non contrôlées. Les accès ne sont contrôlés que si le paramétrage est valide (`acces: non_controle` sinon).
- **Comparaison (V01 à V04)** : `--verifier --precedent FICHIER`. **V01** détecte un `id` modifié par la signature (même source, même cible, mêmes masques sous un autre `id`). **V03** compare la fenêtre (`modifie_depuis`, `age_maximum_sec`), les masques, les exclusions, la récursivité et la taille minimale ; une sélection qui se **restreint** ne signale rien. **V02** précise si la règle avait un historique en base.

### 7.4 Précisions apportées par l'implémentation (J1)

- **Fenêtre de sélection (R08)** : `J` = 1 jour, `J-N` = N + 1 jours (de minuit il y a N jours à maintenant), `age_maximum_sec` arrondi au jour supérieur. `retention_historique_jours` doit être **strictement supérieure** à la plus grande des deux fenêtres.
- **D06** : une liste `apres` vide avec `condition` égale à `["succes"]` est acceptée (c'est ce qu'écrit le front-end par défaut) ; elle est refusée si `condition` est autre chose que `["succes"]`.
- **G01** couvre tout le contenu d'un programme : `commande` qui n'est pas un tableau non vide de textes non vides (par exemple une simple chaîne), variable inconnue, `timeout_sec` absent, non entier ou ≤ 0. Les champs inconnus d'un programme restent en E06.
- **Types (E06)** : un booléen n'est pas accepté comme entier, `60.0` n'est pas un entier, un champ présent deux fois sur une ligne est refusé, `NaN` et `Infinity` sont refusés.
- **Champ absent dans `planification`** : `type` absent est un R01 ; les autres champs requis d'un type sont des P01.
- **E05** détecte les chemins `\\serveur\...` et `//serveur/...`. Un lecteur réseau mappé (`Z:`) ne peut pas être reconnu sans interroger Windows : il est refusé par `--initialiser-base` et à l'ouverture de la base (jalon J2), et sera aussi signalé par le contrôle d'accès A05.
- **R09** : somme, sur toutes les situations (valeurs de secours comprises), de `(tentatives - 1) × delai_sec`.
- **D04 / D05** : D04 compare `debut` ou `heure` pour les jours communs aux deux règles ; une règle `quotidien` compte pour 86 400 s dans D05 ; une règle `apres_dependances` n'est comparée à rien.
- **Hors de `--syntaxe-seule`** (non réalisé en J1) : contrôles d'accès A01–A07 (jalon J8) et comparaison avec la version précédente V01–V04 (front-end).
- **Non vérifié** : le fait que `dossier_temporaire` soit sur le même volume que `cible` ne peut être contrôlé qu'avec accès aux disques ; il le sera en A02.

## 8. Changements par rapport aux exemples des échanges précédents

| Avant | Maintenant |
|---|---|
| `suppression` (mode) | `deplacement` |
| `si_aucun_fichier`, `si_fichier_verrouille`… (champs de la règle) | `situations.aucun_fichier`, `situations.fichier_verrouille`… |
| `"delai": "1min"`, `"5min"`, `"1j"` | Entiers, unité dans le nom : `delai_sec`, `frequence_sec`, `duree_max_sec`, `retention_historique_jours` |
| `age_minimum_s`, critères à plat | Objet `selection` : `age_minimum_sec`, `age_maximum_sec`, `modifie_depuis`… |
| `commande` : texte | `commande` : tableau |
| `duree_max_min` | `duree_max_sec` |
