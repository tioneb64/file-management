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
| `base` | chemin | oui | Fichier SQLite. **Disque local**, jamais un chemin UNC |
| `dossier_logs` | chemin | non | Défaut : `logs` à côté de la base |
| `dossier_travail` | chemin | non | Listes de fichiers transmises aux programmes, résultats. Défaut : `travail` à côté de la base |
| `parallele_max` | entier ou `null` | non | Nombre maximum de règles en parallèle. `null` (défaut) : pas de limite |
| `retention_executions_jours` | entier | non | Durée de conservation des exécutions en base. Défaut : `365` |
| `marge_espace_mo` | entier | non | Espace libre à conserver en plus de la taille des fichiers à livrer, pour la cible et l'archive. Défaut : `64` |

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
| `source` | chemin | oui | — | Dossier à lire |
| `cible` | chemin | oui | — | Dossier de dépôt. Créé s'il n'existe pas et si `creer_dossiers` |
| `mode` | texte | oui | — | `copie` : l'original reste en place ; `deplacement` : l'original est supprimé après copie vérifiée ; `archivage` : l'original est déplacé dans `archive` après copie vérifiée |
| `archive` | chemin ou `null` | si `mode = archivage` | `null` | Absolu (`C:\archive`) ou relatif (`.\archive`, calculé depuis la **racine** de `source`). Variables de date acceptées (§5.2) |
| `creer_dossiers` | booléen | non | `true` | Créer `cible` et `archive` s'ils n'existent pas |
| `dossier_temporaire` | chemin ou `null` | non | `null` | Dossier où écrire les fichiers en cours de copie. `null` : dans `cible`, avec le suffixe `.copie_en_cours`. Si renseigné, il doit être **sur le même volume que `cible`** (renommage atomique) et hors du périmètre surveillé par le logiciel destinataire |

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

Le dossier d'archive est **toujours exclu** du parcours de la source.

### 3.4 Anti-doublon et nommage

| Champ | Type | Défaut | Description |
|---|---|---|---|
| `identite` | texte | `version` | `version` : un fichier est identique s'il a même nom, même taille et même date de modification. `contenu` : identique s'il a même nom et même SHA-256 (voir le point à valider n° 1 de la vue d'ensemble) |
| `retention_historique_jours` | entier | `90` | Durée pendant laquelle un fichier **non revu** reste mémorisé. Doit être **supérieure** à la fenêtre `modifie_depuis` |
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
- Variables remplacées dans chaque élément : `{environnement}` `{regle}` `{source}` `{cible}` `{archive}` `{fichier}` `{nom}` `{fichier_cible}` `{liste}` `{liste_json}` `{date}`.
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

Ces contrôles sont réalisés **par le moteur** (`copie_fichiers.py --verifier`, à chaque démarrage et à la demande du front-end). Le front-end affiche les codes et ne refait pas la logique, sauf les contrôles de saisie simples (champ vide, format de l'heure). Gravité : **refus** = enregistrement impossible et rien n'est lancé (code retour 2) ; **avert.** = enregistrement possible, avertissement affiché.

### 7.1 Syntaxe et cohérence (`--verifier --syntaxe-seule`)

| Code | Gravité | Contrôle |
|---|---|---|
| E01 | refus | La première ligne est un en-tête valide |
| E02 | refus | La version du format est supportée |
| E03 | refus | `environnement` valide et égal au nom du fichier |
| E04 | refus | `base` renseigné |
| E05 | refus | `base` n'est pas un chemin réseau (SQLite en mode WAL ne le supporte pas) |
| E06 | refus | Ligne JSON invalide, champ inconnu ou de mauvais type (avec le numéro de ligne) |
| R01 | refus | Champs obligatoires présents (`id`, `source`, `cible`, `mode`, `planification`) |
| R02 | refus | `id` valide et unique, sans tenir compte de la casse |
| R03 | refus | `source` différente de `cible` ; en mode récursif, `cible` hors de `source` |
| R04 | refus | `mode = archivage` impose `archive` |
| R05 | avert. | `archive` renseigné alors que le mode n'est pas `archivage` : ignoré |
| R06 | refus | Valeur hors liste (mode, niveaux, `suite` non autorisée pour la situation, `ordre`, `identite`…) |
| R07 | refus | Nombres hors bornes (`tentatives` < 1, `delai_sec` < 0, `age_minimum_sec` ≥ `age_maximum_sec`…) |
| R08 | refus | `retention_historique_jours` doit être supérieure à la fenêtre de sélection, quand il y en a une (`modifie_depuis = J-N`, ou `age_maximum_sec`) |
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
| V04 | avert. | `cible` modifiée : tous les fichiers sélectionnés seront relivrés vers la nouvelle cible |

### 7.3 Accès (`--verifier` complet, exécuté sur le serveur d'exécution avec le compte de service)

| Code | Contrôle |
|---|---|
| A01 | `source` existe et est lisible |
| A02 | `cible` existe ou peut être créée ; écriture vérifiée par un fichier d'essai créé puis supprimé |
| A03 | `archive` : idem, si renseignée |
| A04 | Les exécutables des programmes existent |
| A05 | La base est accessible en écriture |
| A06 | Les dossiers de journaux et de travail sont accessibles en écriture |
| A07 | Espace disponible pour le compte de service sur `cible` et `archive` (information) |

Le résultat est disponible en texte et en JSON (`--format json`) :

```json
{"ok": false, "refus": [{"code": "D03", "regle": "import_catalogue", "message": "dépend de export_produits, qui est inactive"}],
 "avertissements": [{"code": "D04", "regle": "import_catalogue", "message": "démarre à 06:00, avant export_clients (07:00)"}]}
```

### 7.4 Précisions apportées par l'implémentation (J1)

- **Fenêtre de sélection (R08)** : `J` = 1 jour, `J-N` = N + 1 jours (de minuit il y a N jours à maintenant), `age_maximum_sec` arrondi au jour supérieur. `retention_historique_jours` doit être **strictement supérieure** à la plus grande des deux fenêtres.
- **D06** : une liste `apres` vide avec `condition` égale à `["succes"]` est acceptée (c'est ce qu'écrit le front-end par défaut) ; elle est refusée si `condition` est autre chose que `["succes"]`.
- **G01** couvre tout le contenu d'un programme : `commande` qui n'est pas un tableau non vide de textes non vides (par exemple une simple chaîne), variable inconnue, `timeout_sec` absent, non entier ou ≤ 0. Les champs inconnus d'un programme restent en E06.
- **Types (E06)** : un booléen n'est pas accepté comme entier, `60.0` n'est pas un entier, un champ présent deux fois sur une ligne est refusé, `NaN` et `Infinity` sont refusés.
- **Champ absent dans `planification`** : `type` absent est un R01 ; les autres champs requis d'un type sont des P01.
- **E05** détecte les chemins `\\serveur\...` et `//serveur/...`. Une lettre de lecteur réseau mappé ne peut pas être reconnue sans accéder au disque : ce sera le contrôle d'accès A05.
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
