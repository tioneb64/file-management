# Migration et recette

Passage de l'ancien script (`Legacy\file_management_v1.py` + `Legacy\copies.conf` + historique JSON) à la v2, **règle par règle**, sans relivrer ce qui a déjà été livré et sans trou. L'ancien script n'est jamais modifié : il reste le plan de repli.

## 1. Outils fournis

| Outil | Rôle |
|---|---|
| `python -m file_management --migrer-ancien COPIES.CONF --environnement E --base B [--sortie F] [--frequence-sec N] [--actives]` | Convertit `copies.conf` en fichier de paramétrage. **Ne demande pas `--config`**. Règles **inactives** par défaut ; refuse d'écraser un fichier existant ; le nom du fichier doit être `<environnement>.jsonl` |
| `python -m file_management --config F --importer-historique HISTORIQUE.JSON --utilisateur U [--commentaire C]` | Importe l'historique de l'ancien script dans la base : les fichiers déjà copiés ne seront **pas relivrés**. Idempotent, tracé |
| `outils\comparer_dossiers.py ANCIEN NOUVEAU [--masque *.csv] [--dates]` | Compare deux dossiers cibles (présence, taille, SHA-256) : preuve que la v2 livre la même chose que la v1. Lecture seule |
| `file_management.py` | Lanceur de la v2 (équivalent de `python -m file_management`) ; l'ancien script est dans `Legacy\` |

## 2. Ce que la conversion fait (et ne fait pas)

Une ligne `source | cible | critère | masque | récursif` devient une règle :

| Ancien | v2 |
|---|---|
| `source`, `cible`, `masque`, `récursif` | identiques (`selection.masque`, `selection.recursif`) |
| `J`, `J-N`, `TOUT` | `selection.modifie_depuis` ; `retention_historique_jours` = max(90, N + 31) pour rester supérieur à la fenêtre (contrôle R08) |
| *(le job Jenkins fixait la fréquence)* | Planification par défaut : toutes les `--frequence-sec` (3 600 s), 24 h sur 24 → **à adapter** |
| *(copie)* | `mode = copie`, `identite = version` (nom + taille + date, comme l'historique de la v1) |
| Cible qui a perdu le fichier : recopie | `si_cible_absente = recopier` |
| Fichier du même nom dans la cible : écrasé | `si_existe_cible = ecraser` (à **durcir** ensuite, par exemple `erreur` ou `suffixe` : un fichier écrasé ne peut pas être rattrapé) |
| *(rien)* | `id` provisoire `copie_<ligne>_<dossier>` : **le renommer avant le premier lancement**, il ne change plus ensuite |
| *(rien)* | `actif: false` : on active une règle à la fois |

Le fichier produit est immédiatement vérifié (syntaxe) et le compte rendu liste les points à revoir. Rien n'est créé ailleurs : ni base, ni dossier.

## 3. Pré-requis avant toute bascule

- [ ] Cahier de tests rejoué **sur le serveur** (J0 à J9) ; tout écart analysé. Au minimum : J0-M, J2-M01, J4-M (verrous, droits, partages, arrêt brutal), J5-M, J6-M, J8-M01, J9-M.
- [ ] Débit mesuré (`outils\mesure_transfert.py`) compatible avec les volumes réels (voir [02 §6.4](02-moteur.md)).
- [ ] **Sauvegarde nocturne de la base en place** (`jenkins/Jenkinsfile.sauvegarde`) et restauration essayée (J2-M06).
- [ ] Journaux lus par Alloy, validés par l'équipe de supervision (J3-M05).
- [ ] Comportement des logiciels destinataires connu (prennent-ils les fichiers ? ignorent-ils `.copie_en_cours` ? — J4-M12).
- [ ] Un interlocuteur désigné pour les décisions d'exploitation (livraison incertaine, reprise, acquittement).

## 4. Déroulement

### Étape 1 — Générer, relire, vérifier (aucun risque)

```powershell
cd D:\Scripts\file_management
C:\Python314\python.exe -m file_management --migrer-ancien D:\Anciens\copies.conf --environnement recette --base D:\Copie\recette.db --sortie D:\Parametrage\recette.jsonl
# relire le fichier : renommer les id, régler les planifications, durcir si_existe_cible
C:\Python314\python.exe -m file_management --config D:\Parametrage\recette.jsonl --verifier        # avec le compte de service
```

### Étape 2 — Base et historique

```powershell
C:\Python314\python.exe -m file_management --config D:\Parametrage\recette.jsonl --initialiser-base
# travailler sur une COPIE de l'historique : l'ancien script tourne encore
C:\Python314\python.exe -m file_management --config D:\Parametrage\recette.jsonl --importer-historique D:\Anciens\copies.historique.copie.json --utilisateur DOMAINE\benoit --commentaire "recette"
```

Lire le compte rendu : `sans_regle` doit être **0** (ou compris : fichiers d'une ligne retirée du `copies.conf`). Un historique qui ne correspond à aucune règle signale en général un chemin différent entre `copies.conf` et le paramétrage.

### Étape 3 — Simulation sur les données réelles

```powershell
C:\Python314\python.exe -m file_management --config D:\Parametrage\recette.jsonl --simulation --regle copie_01_factures
```

Attendu : seuls les fichiers **arrivés depuis la dernière exécution de l'ancien script** sont « à livrer » ; tout le reste est « déjà livré ». Si tout est « à livrer », l'import n'a pas fonctionné (chemins, masque, casse) : ne pas continuer.

### Étape 4 — Marche en parallèle, sur UNE règle peu critique

L'ancien script continue de livrer vers la **vraie cible**. Dupliquer la règle avec une **cible de recette** distincte (`D:\Recette\cible_v2`), l'activer, laisser tourner quelques jours ouvrés, puis comparer :

```powershell
C:\Python314\python.exe outils\comparer_dossiers.py \\SRV-RECETTE01\imports\factures D:\Recette\cible_v2 --masque *.csv --dates
```

Attendu : mêmes fichiers, mêmes tailles, mêmes SHA-256. Un écart se traite avant d'aller plus loin (cause fréquente : masque, fenêtre `modifie_depuis`, fichiers modifiés après leur copie).

### Étape 5 — Bascule d'une règle (ordre à respecter)

1. Relancer l'import de l'historique (idempotent) pour prendre les derniers fichiers livrés par l'ancien script.
2. **Désactiver la ligne** dans `copies.conf` (la commenter avec `#`).
3. Mettre la règle v2 à `actif: true` avec la **vraie cible**.
4. Observer le premier lancement : journaux, `--etat`, aucun fichier relivré (`livres` ne contient que les nouveautés), cible conforme.

Désactiver l'ancienne ligne **avant** d'activer la règle évite un doublon ; l'import juste avant évite un trou. Une règle à la fois, au moins une journée complète d'observation entre deux règles critiques.

### Étape 6 — Retour arrière (règle par règle)

1. Mettre la règle v2 à `actif: false`.
2. Décommenter la ligne de `copies.conf`.

L'historique de l'ancien script n'a pas été modifié ; il recopie ce que la v2 a livré depuis la bascule (identique : il l'enregistre sans le recopier, « déjà présent à l'identique »). Aucune perte, pas de doublon visible.

### Étape 7 — Fin de migration

- Toutes les règles basculées et stables (au moins deux semaines).
- Dans le dépôt, c'est fait : l'ancien script et sa configuration sont dans `Legacy\` (`file_management_v1.py`, `copies.conf`, conservés pour le retour arrière) et le lanceur de la v2 s'appelle `file_management.py`. Dans le dépôt de déploiement, reproduire ce rangement ; dans les jobs Jenkins, rien à changer si le lanceur s'appelait déjà `file_management.py` (sinon `lanceur: 'file_management.py'`). Un job qui lançait encore la v1 doit viser `Legacy\file_management_v1.py` tant qu'il n'est pas basculé. Les tests de caractérisation du dépôt chargent `Legacy\file_management_v1.py`.
- Garder `copies.conf` et l'historique de l'ancien script archivés avec la dernière sauvegarde de la base.

## 5. Différences de comportement à connaître

| Sujet | Ancien script | v2 |
|---|---|---|
| Exécutions simultanées | Un verrou global, code 3 si déjà en cours | Un verrou **par règle**, plusieurs lancements en parallèle, code 3 supprimé |
| Planification | Celle du job Jenkins | Créneaux par règle (intervalle, quotidien, après dépendances) |
| Historique | Un fichier JSON | Base SQLite (à **sauvegarder**) |
| Fichier du même nom dans la cible | Écrasé | Au choix (`erreur` par défaut hors migration) |
| Erreur de copie | 3 essais puis erreur | Situations réglables : tentatives, délai, suite (fichier suivant, arrêt de la règle) |
| Arrêt brutal pendant une copie | Fichier temporaire recopié au lancement suivant | Livraison **de résultat inconnu** : décision d'exploitation, jamais de doublon |
| Journaux | Console et fichier texte | JSON, un fichier par règle et par jour (Grafana) |
| Suppression / archivage | Non | Modes `deplacement` et `archivage` |
| Fichier temporaire de copie | `<nom>.copie_en_cours` dans la cible | Identique (ou `dossier_temporaire`) |

## 6. Critères de fin

- Plus aucune ligne active dans `copies.conf` ; l'ancien job Jenkins désactivé.
- Chaque règle est observée sur un cycle complet (semaine, fin de mois s'il y a lieu).
- Sauvegarde de la base contrôlée par une restauration réelle.
- Les règles sont durcies (`si_existe_cible`, tentatives, planification) selon les besoins réels, plus selon les valeurs de migration.
