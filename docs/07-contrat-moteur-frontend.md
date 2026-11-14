# Contrat entre le moteur et le front-end

Le front-end (PowerShell, voir [04-frontend](04-frontend.md)) **n'ouvre jamais la base** et **ne relit pas la logique de validation** : il appelle le moteur et lit du JSON. Ce document est le contrat : tant que `version_contrat` vaut `1`, les champs listés ici ne changent ni de nom ni de type ; des champs peuvent être **ajoutés** (le front-end doit ignorer ceux qu'il ne connaît pas).

## 1. Appel

```powershell
$py = 'C:\Python314\python.exe'
$sortie = & $py -m file_management --config D:\Parametrage\production.jsonl --format json --etat
$resultat = $sortie | ConvertFrom-Json          # un seul objet JSON
$LASTEXITCODE                                   # voir §3
```

- **`--format json`** est un paramètre de toutes les commandes. La sortie standard contient **exactement un objet JSON**, en **UTF-8 sans BOM**, accents écrits tels quels (pas de `\u00e9`). La sortie d'erreur reste vide. Aucune ligne de console des processus fils ne s'y mêle.
- En PowerShell 5.1, forcer le décodage : `[Console]::OutputEncoding = [Text.Encoding]::UTF8` avant l'appel, sinon les accents sont mal lus.
- **Exception** : une erreur d'arguments (option inconnue, `--utilisateur` manquant) est refusée par l'analyse de la ligne de commande : code 2, message d'aide sur la **sortie d'erreur**, sortie standard vide. Le front-end construit ses commandes : une telle erreur est un défaut du front-end.
- Distant : `Invoke-Command -ComputerName SERVEUR -ScriptBlock { & $using:py -m file_management ... }` ; recommandé : point de terminaison JEA qui n'expose que ces commandes ([04-frontend §6](04-frontend.md)).
- Le fichier de paramétrage est toujours donné par `--config`. Il est lu, jamais écrit.

## 2. Champs communs

Toute réponse JSON, quelle que soit la commande :

| Champ | Type | Sens |
|---|---|---|
| `version_contrat` | entier | `1` |
| `ok` | booléen | `true` si le code retour vaut 0 ou 4 |
| `code_retour` | entier | Le code de sortie du processus (§3) |
| `message` | texte | Explication lisible, destinée à l'utilisateur. Vide ou absent pour `--etat` et `--verifier`. |

Si le **paramétrage lui-même est invalide**, toute commande (sauf `--verifier`) répond `ok: false`, `code_retour: 2`, `message: "Parametrage invalide : commande annulee."` et les listes `refus`, `avertissements`, `informations` du §4.1.

## 3. Codes retour

| Code | Sens | Pour `--verifier` |
|---|---|---|
| 0 | Succès | Valide, sans avertissement |
| 1 | Au moins une erreur pendant ce lancement (`--lancer-regle` : la règle est en erreur) | — |
| 2 | Commande refusée, paramétrage invalide, base absente ou inutilisable, arguments incorrects | Au moins un refus |
| 4 | Succès avec au moins un avertissement | Valide avec avertissements |

Les informations (`A07`) n'ont aucun effet sur le code.

## 4. Commandes

Colonne « Droits » : **lecture** = tout compte, **écriture** = administrateurs ; la restriction est appliquée par le front-end, par les droits NTFS et par JEA ([04-frontend §7](04-frontend.md)).

| Commande | Droits | Effet | Champs propres de la réponse |
|---|---|---|---|
| `--verifier [--syntaxe-seule] [--precedent FICHIER] [--dossier-parametrage DOSSIER] [--periode-declencheur-sec N]` | lecture | Valide le fichier ; sans `--syntaxe-seule`, contrôle aussi les accès (A01 à A07) **avec le compte qui exécute la commande** ; avec `--precedent`, compare avec l'ancienne version (V01 à V04) | §4.1 |
| `--etat [--regle ID]` | lecture | État de chaque règle (lecture seule de la base) | §4.2 |
| `--modele-regle` | lecture | Valeurs de secours d'une règle et listes de valeurs permises, pour le formulaire du front-end. Ne demande pas `--config` et ne lit aucun fichier ni aucune base | `commande`, `version_format`, `regle` (règle complète, valeurs de secours), `listes` (valeurs permises de chaque champ à liste fermée, variables par point d'appel), `situations` (tentatives, délai, niveau, suites permises et suite par défaut) |
| `--initialiser-base` | écriture | Crée la base de l'environnement | `base`, `environnement` |
| `--sauvegarder-base DOSSIER` | écriture | Sauvegarde cohérente de la base | `fichier` |
| `--reprise ID --utilisateur U [--commentaire C]` | écriture | La règle repartira au prochain lancement, quelle que soit l'heure | `commande`, `regle` |
| `--lancer-maintenant ID --utilisateur U` | écriture | Idem, sans programme de reprise | `commande`, `regle` |
| `--acquitter ID --utilisateur U --commentaire C` | écriture | Règle en `ERREUR` considérée comme corrigée (commentaire obligatoire) | `commande`, `regle` |
| `--debloquer ID --utilisateur U [--commentaire C]` | écriture | Arrête l'exécution en cours (processus et descendants) et libère la règle | `commande`, `regle`, `execution_id`, `pid`, `processus_arrete`, `drapeau_libere`, `reprise_necessaire` |
| `--purger [--regle ID] [--appliquer]` | écriture | Sans `--appliquer` : liste ce qui serait purgé (journaux et archives), **ne supprime rien**. Avec : supprime. Code 4 si une règle n'est pas purgeable ou si une suppression échoue | `commande`, `appliquee`, `a_purger` (`type`, `regle`, `chemin`, `date`, `octets`, `fichiers`), `octets`, `ignores` (`chemin`, `raison`), `erreurs_regles`, `resultat` (avec `--appliquer` : `journaux`, `archives`, `octets`, `erreurs`) |
| `--trancher-incertain CLE --decision livre\|a_relivrer --utilisateur U --commentaire C` | écriture | Décide du sort d'une livraison de résultat inconnu | `commande`, `decision` |
| `--lancer-regle ID [--simulation]` | écriture (lecture avec `--simulation`) | Exécute une seule règle maintenant. Avec `--simulation`, rien n'est écrit et aucune temporisation n'est observée | `regle`, `statut`, `compteurs`, `simulation` ; avec `--simulation` en plus : `source`, `cible`, `mode`, `situation`, `apercu` (`fichier`, `cible`, `taille`, `archive`), `apercu_total`, `apercu_tronque` (plafond 500), `controles` (voir `--controler-regle`) |
| `--controler-regle ID` | lecture | Contrôle les dossiers d'une règle sans lire la base ni rien livrer | `regle`, `mode`, `controles` : liste de `role` (`source`, `cible`, `temporaire`, `archive`), `chemin`, `existe`, `lecture`, `ecriture` (`null` : non testé ; dossier absent : droit de le créer), `a_creer`, `detail`, `espace` (`libre_octets`, `necessaire_octets`, `suffisant`), `volume_incorrect` |
| `--journaux-regle ID [--journal NOM] [--limite-evenements N]` | lecture | Journaux d'une règle, sans base. Sans `--journal` : liste. Avec : contenu d'un fichier `<ID>_<AAAA-MM-JJ>.jsonl` (un nom, jamais un chemin ; refusé sinon, code 2) | Liste : `regle`, `dossier`, `journaux` (du plus récent : `nom`, `jour`, `octets`, `evenements`, `illisibles`, `executions`, `avertissements`, `erreurs`, `statut` et `motif` de la dernière exécution terminée, `dernier` : heure locale du dernier événement), `tronque` (plus de 45 fichiers), `total_fichiers`. Fichier : `journal`, `total`, `tronque`, `illisibles` (lignes ignorées), `executions` (`cle`, `execution_id` ou `null` pour une simulation, `heure`, `declencheur`, `simulation`, `statut`, `motif`, `duree_ms`, `compteurs`, `avertissements`, `erreurs`), `evenements` (`numero`, `heure` locale, `niveau`, `evenement`, `message`, `execution_id`, `groupe` = clé de l'exécution ou `null`, `duree_ms`, `erreur` {`type`, `exception`, `pile`} ou `null`, `champs` : liste {`cle`, `valeur`}) |
| `--creer-dossiers-regle ID --utilisateur U` | écriture | Crée les dossiers source, cible, temporaire et archive manquants que les contrôles jugent créables (la source n'est jamais créée par un lancement ordinaire) | `regle`, `crees`, `echecs` (`role`, `chemin`, `erreur`) ; code 1 s'il y a un échec |
| `--scanner-outils [--dossier-outils D] [--utilisateur U]` | écriture | Parcourt le dossier des outils (`D`, sinon `outils` à la racine du moteur) et ses sous-dossiers ; ne lit ni `--config` ni base et **n'écrit rien** : l'interface enregistre `contenu_index` dans `outils.json` (dossier de paramétrage) | `dossier` (parcouru), `dossier_configure` (`D` ou vide), `outils` (`variable`, `fichier` relatif, `description`, `parametres` : `forme`, `obligatoire`, `description`), `non_retenus` (`fichier`, `cause`), `bibliotheques` (`fichier`, `description` : modules déclarés `# bibliotheque:`, hors index), `erreurs` (`chemin`, `message` : dossiers illisibles), `fichiers_python`, `dossiers`, `contenu_index` (texte exact d'`outils.json`), `message` ; `ok` faux et code 2 si le dossier est introuvable |
| `--renommer-environnement ANCIEN [--utilisateur U]` | écriture | La base du fichier `--config`, encore au nom d'environnement `ANCIEN`, prend le nom du fichier ; refusé si une règle est en cours ou si la base porte un autre nom | `base`, `environnement` |
| *(aucune)* `[--regle ID] [--simulation]` | écriture | Lancement : toutes les règles dues (utilisé par Jenkins) | `statut`, `compteurs`, `simulation`, `suspendu` (vrai : environnement suspendu, aucune règle lancée, code 0) |

Les commandes d'exploitation (`--reprise`, `--lancer-maintenant`, `--acquitter`, `--debloquer`, `--trancher-incertain`) exigent `--utilisateur`, qui est tracé dans la base et dans le journal ; le front-end y passe le compte Active Directory authentifié. Un **refus** (règle en cours, commentaire manquant…) répond `ok: false`, `code_retour: 2` et la raison dans `message`.

Commande interne `--executer-regle` : réservée à l'orchestrateur, **ne pas utiliser**.

### 4.1 `--verifier`

```json
{"version_contrat": 1, "ok": false, "code_retour": 2, "regles_lues": 12, "acces": "controle",
 "refus": [{"code": "D03", "regle": "import_catalogue", "ligne": 7, "message": "depend de export_produits, qui est inactive"}],
 "avertissements": [{"code": "D04", "regle": "import_catalogue", "ligne": 7, "message": "demarre a 06:00, avant export_clients (07:00)"}],
 "informations": [{"code": "A07", "regle": "export_clients", "ligne": 2, "message": "espace disponible ... : 28125 Mo"}]}
```

| Champ | Type | Sens |
|---|---|---|
| `refus`, `avertissements`, `informations` | liste | Diagnostics. `ok` vaut `true` si `refus` est vide |
| diagnostic `.code` | texte | Code de [01-parametrage §7](01-parametrage.md) : `E`, `R`, `P`, `D`, `G` (syntaxe), `A` (accès), `V` (comparaison) |
| diagnostic `.regle` | texte ou `null` | `id` de la règle concernée, `null` pour l'en-tête et le fichier |
| diagnostic `.ligne` | entier (facultatif) | Numéro de ligne du fichier |
| diagnostic `.message` | texte | Explication |
| `regles_lues` | entier | Nombre de règles lues |
| `acces` | texte | `controle` si les accès ont été contrôlés, `non_controle` avec `--syntaxe-seule` ou si le paramétrage est invalide |

Gravité des codes d'accès : `A01` `A02` `A04` `A05` refus ; `A03` `A06` avertissement ; `A07` information. Un chemin absent est jugé d'après son plus proche parent existant (aucun dossier n'est créé par la vérification).

### 4.2 `--etat`

```json
{"version_contrat": 1, "ok": true, "code_retour": 0, "environnement": "production", "genere_le": 1793609412,
 "suspendu": false, "motif_suspension": null, "orphelines": [],
 "regles": [{"id": "export_clients", "description": "...", "actif": true, "mode": "archivage",
             "planification": "toutes les 5 min de 05:00 a 19:00, lun-ven",
             "statut": "WARNING", "en_cours": false, "attente": null, "motif": "archivage differe : 12 fichier(s)",
             "dernier_lancement": 1793609101, "dernier_creneau": 1793609100, "prochain_creneau": 1793609400,
             "dernier_succes": 1793605500,
             "derniere_erreur": {"le": 1793520000, "situation": "fichier_verrouille", "message": "..."},
             "derniere_execution": {"statut": "WARNING", "nb_livres": 4, "nb_erreurs": 0, "declencheur": "planifie", "duree_sec": 11},
             "reprise": false, "lancement_manuel": false, "arret_apres_erreur": false,
             "archivage_degrade": true, "actions_en_attente": 12, "livraisons_incertaines": 0, "incertains": []}]}
```

| Champ d'une règle | Type | Sens |
|---|---|---|
| `statut` | texte | `JAMAIS_LANCEE`, `SUCCES`, `WARNING`, `ERREUR`, `ATTENTE`, `ACQUITTEE`, `ARRETEE`, `EN_COURS`, `EN_ATTENTE`, `BLOQUEE`, `INACTIVE` |
| `attente`, `motif` | texte ou `null` | `EN_ATTENTE` / `BLOQUEE` et son explication (nomme la règle bloquante) ; `motif` reprend sinon le motif de la dernière exécution |
| `planification` | texte | Planification en clair |
| `dernier_lancement`, `dernier_creneau`, `prochain_creneau`, `dernier_succes` | entier ou `null` | **Secondes depuis 1970, UTC** (à convertir pour l'affichage) |
| `derniere_erreur` | objet ou `null` | `le` (entier), `situation`, `message` |
| `derniere_execution` | objet ou `null` | `statut`, `nb_livres`, `nb_erreurs`, `declencheur`, `duree_sec` |
| `reprise`, `lancement_manuel`, `arret_apres_erreur`, `archivage_degrade` | booléen | Drapeaux (reprise demandée, règle arrêtée après erreur, archive indisponible…) |
| `actions_en_attente`, `livraisons_incertaines` | entier | Suppressions / archivages différés ; livraisons de résultat inconnu (à trancher) |
| `incertains` | liste | Les livraisons de résultat inconnu : `cle` (hexadécimal, à donner à `--trancher-incertain`), `source`, `cible` (`null` si la trace de l'action a disparu). Vide s'il n'y en a pas. Champ ajouté après la première version du contrat : ignoré par un front-end plus ancien |
| `orphelines` (racine) | liste de textes | `id` connus de la base mais absents du paramétrage |

### 4.3 Lancement et `--lancer-regle`

`statut` vaut `SUCCES`, `WARNING` ou `ERREUR` ; `statut_final` (règle seule) vaut en plus `ATTENTE` pour une règle `count` / `size` hors bornes (le `statut` reste `SUCCES`, code 0). `mode` vaut `copie`, `deplacement`, `archivage`, `suppression`, `count`, `size` ou `synchro` ; `cible` est `null` pour les quatre derniers (et `source` aussi pour `synchro`). `compteurs` d'un **lancement** : `regles`, `lancees`, `SUCCES`, `WARNING`, `ERREUR`, `non_dues`, `non_lancees`, `orphelines`, `nettoyees`, `en_attente`, `bloquees`, `depassees`. `compteurs` d'une **règle** : `selectionnes`, `livres`, `ignores`, `erreurs`, `en_attente`, `octets`. Le détail fichier par fichier est dans les journaux (Grafana), pas dans cette réponse.

## 5. Enregistrement d'une modification (séquence recommandée)

1. Écrire le nouveau fichier dans un temporaire du dossier de paramétrage.
2. `--config <temporaire> --verifier --syntaxe-seule --precedent <fichier actuel> --dossier-parametrage <dossier> --format json` (`--dossier-parametrage` : le brouillon est dans un sous-dossier ; l'index `outils.json` des `{outil:nom}` est lu dans le dossier de paramétrage, pas à côté du brouillon) : **refus** → annuler et afficher ; **avertissements** (dont `V02`, `V03`, `V04`) → demander confirmation.
3. Copier l'ancienne version dans `versions\`, remplacer le fichier par renommage atomique.
4. Proposer `--verifier` complet **sur le serveur d'exécution** : seul lui voit les accès du compte de service.

## 6. Évolutions

Un champ ajouté ne change pas `version_contrat`. Un champ supprimé, renommé ou dont le type change incrémente `version_contrat` ; le moteur et le front-end sont alors livrés ensemble.
