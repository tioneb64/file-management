# Front-end de gestion

Application **PowerShell 5.1** (Windows Server 2016) pour gérer le paramétrage et suivre l'état des règles. Son aspect graphique reprend celui du projet de gestion des clusters Hyper-V : **les maquettes seront fournies** et complétées dans ce document. Ce document décrit les fonctions, les règles et les échanges avec le moteur, pas l'aspect visuel.

## 1. Principes

1. **Une seule logique de validation, celle du moteur.** Le front-end fait les contrôles de saisie simples (champ vide, format d'heure, nombre) ; pour tout le reste il appelle `copie_fichiers.py --verifier` et affiche les codes renvoyés. Il ne peut donc jamais accepter ce que le moteur refuserait.
2. **Le front-end n'ouvre jamais la base.** Il lit l'état et déclenche les actions par des commandes du moteur.
3. **Droits.** Membre du groupe d'administrateurs AD : modification. Les autres : consultation de la configuration et de l'état.
4. **Le fichier de paramétrage n'est jamais écrit à moitié** : écriture dans un temporaire puis renommage.
5. **Toute action est tracée** (compte, heure, commentaire).

## 2. Configuration locale

Un petit fichier `frontend.json` à côté de l'application :

```json
{
  "dossier_parametrage": "\\\\SRV-JENKINS01\\parametrage",
  "dossier_versions": "\\\\SRV-JENKINS01\\parametrage\\versions",
  "serveur_execution": "SRV-JENKINS01",
  "python": "C:\\Python314\\python.exe",
  "script": "D:\\Scripts\\copie_fichiers.py",
  "groupe_admin_ad": "DOMAINE\\GG_Copie_Admins",
  "periode_declencheur_sec": 300,
  "url_grafana": "https://grafana.exemple/d/copie-fichiers"
}
```

Le front-end peut tourner **sur le serveur d'exécution ou sur un autre poste** : seul `dossier_parametrage` et le serveur d'exécution changent.

## 3. Environnements

- Au démarrage, le front-end **parcourt `dossier_parametrage`** et charge chaque fichier `*.jsonl`. Il lit la première ligne (en-tête) de chacun.
- **Un onglet par environnement**, nommé d'après l'en-tête.
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
| Liens | Vers Grafana (historique détaillé, fichiers livrés, erreurs) |

### 4.2 Modification (administrateurs)

| Fonction | Détail |
|---|---|
| Ajouter / dupliquer / modifier une règle | Formulaire regroupant les champs de [01-parametrage](01-parametrage.md), valeurs de secours préremplies |
| Activer / désactiver | Refusé si des règles actives en dépendent (D03) |
| Supprimer | Avertissement V02 ; l'état reste en base |
| Réordonner | Tri automatique : une règle dépendante est toujours placée **après** ses dépendances |
| Promouvoir | Copier une règle validée d'un environnement vers un autre, en adaptant les chemins |

Aides à la saisie : durées en unités lisibles à l'écran (converties en `_sec` à l'enregistrement), planification en sélecteurs, masques en liste, variables de date disponibles en liste, dépendances choisies parmi les règles existantes.

### 4.3 Actions d'exploitation (administrateurs)

| Action | Commande du moteur | Confirmation |
|---|---|---|
| **Reprise** | `--reprise ID` | Affiche les règles de la chaîne qui repartiront |
| **Lancer maintenant** | `--lancer-maintenant ID` | Oui |
| **Acquitter** | `--acquitter ID` | Commentaire obligatoire |
| **Débloquer** | `--debloquer ID` | Oui, avertit que l'arbre de processus sera arrêté |

## 5. Enregistrement du paramétrage

1. Au chargement, le front-end mémorise la date de modification et l'empreinte du fichier.
2. À l'enregistrement, il construit le fichier complet en mémoire : en-tête + une ligne par règle, triées.
3. Il l'écrit dans un fichier temporaire du même dossier.
4. Il appelle `--verifier --syntaxe-seule --format json` sur ce temporaire. Un **refus** annule l'enregistrement et affiche les codes ; les **avertissements** sont présentés pour confirmation.
5. Il compare avec la version chargée pour les contrôles V01 à V04.
6. **Contrôle d'édition simultanée** : si le fichier a changé depuis le chargement, l'enregistrement est refusé et le fichier est rechargé.
7. Il copie la version précédente dans `dossier_versions` (`production_20261103_101500_DOMAINE_benoit.jsonl`), en enregistrant le compte et un commentaire.
8. Il remplace le fichier par renommage atomique.
9. Il propose de lancer `--verifier` complet (accès) sur le serveur d'exécution.

Écriture du fichier en PowerShell 5.1 :

- UTF-8 **sans BOM** : `[System.IO.File]::WriteAllText($chemin, $texte, (New-Object System.Text.UTF8Encoding $false))` (`Set-Content -Encoding UTF8` ajoute un BOM, accepté par le moteur mais inutile ; `Out-File` écrit en UTF-16 par défaut).
- `ConvertTo-Json -Compress -Depth 10` pour chaque règle : sans `-Depth`, les objets imbriqués (`planification`, `situations`, `programmes`) sont tronqués à deux niveaux.
- `ConvertTo-Json` de PowerShell 5.1 échappe `<`, `>`, `&` et `'` en `\uXXXX` : valide en JSON, le moteur le relit correctement.
- Les valeurs `null`, les booléens et les entiers conservent leur type ; tester `[int]` et `[bool]` sur les champs saisis en texte.

## 6. Communication avec le moteur

Le front-end exécute le moteur sur le serveur d'exécution, **avec le compte de l'administrateur connecté** pour les actions tracées :

```powershell
Invoke-Command -ComputerName $cfg.serveur_execution -ScriptBlock {
    param($py, $script, $conf)
    & $py $script --config $conf --etat --format json
} -ArgumentList $cfg.python, $cfg.script, $fichierConf
```

- Sortie JSON UTF-8, lue avec `ConvertFrom-Json`. Les codes retour du moteur sont interprétés : 0, 1 (anomalies déjà dans le JSON), 2 (erreur de configuration).
- Sur le serveur d'exécution lui-même : exécution locale directe.
- Recommandé : limiter l'accès distant par un point de terminaison **JEA** qui n'expose que les commandes du moteur.
- Pas d'interrogation automatique plus fréquente que toutes les 30 secondes ; bouton d'actualisation manuel.

## 7. Sécurité

| Sujet | Règle |
|---|---|
| Qui est administrateur | Appartenance du compte Windows courant au groupe `groupe_admin_ad` (`[Security.Principal.WindowsPrincipal]::IsInRole`). Résultat affiché en haut de l'écran |
| Contournement | La restriction du front-end ne protège rien seule : les droits d'écriture du dossier de paramétrage et du point de terminaison d'exécution distante doivent aussi être limités au même groupe |
| Programmes | Qui modifie `programmes` fait exécuter un programme par le compte de service. Le formulaire affiche un avertissement et la modification est tracée |
| Secrets | Aucun mot de passe ni jeton dans les champs du paramétrage |

## 8. Tests

- Jeu de fichiers de paramétrage valides et invalides (un par code de validation) vérifiant que le front-end affiche le code attendu.
- Tests Pester (module PowerShell) sur la lecture / écriture JSON (profondeur, encodage, types) et sur la construction des commandes.
- Recette sur Windows Server 2016 avec PowerShell 5.1, y compris l'exécution distante.

## 9. À fournir

| Élément | De qui |
|---|---|
| Maquettes des écrans (style du projet de gestion des clusters Hyper-V) | Responsable applicatif |
| Nom du groupe AD, serveur d'exécution, partage du paramétrage | Responsable applicatif |
| URL Grafana et paramètres de liaison des tableaux de bord | Équipe de la plateforme de surveillance |
