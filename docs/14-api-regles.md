# 14 — API de règles (ajouter ou modifier des règles depuis un autre programme)

Un programme qui n'est pas l'interface graphique (script PowerShell, script Python, outil d'équipe) peut **ajouter, modifier ou supprimer des règles** sans connaître le format du fichier. Il passe par le module **`FileManagement.Regles`**, qui est **le seul habilité à écrire le fichier des règles** (`parametrage\<env>.jsonl`). L'interface graphique utilise le même noyau : il n'existe qu'**un seul exemplaire** du code qui écrit.

## 1. Principe

| Question | Réponse |
|---|---|
| Qui écrit le fichier ? | **Uniquement** le module `Gui\FileManagement.Regles` (l'interface charge ses fichiers `Private\`). Le moteur ne l'écrit jamais (G5). Aucun appelant ne construit de JSON de règle complet ni n'écrit dans le fichier |
| Qui connaît le format ? | Le **moteur** (`--modele-regle`). Quand le format évolue (champ ajouté, valeur de secours changée), l'API complète elle-même les champs absents : l'appelant ne fournit que ce qui compte |
| Un champ inconnu ou une valeur invalide ? | Le moteur la **refuse** (E06, P01…) : le fichier n'est pas touché. Rien n'est écrit en silence |
| Édition simultanée ? | Même contrôle que l'interface : **empreinte SHA-256** du fichier, brouillon, vérification du moteur, **version précédente conservée** (`versions\`, avec fiche `.meta.json`), remplacement atomique |
| Qui a le droit ? | Les membres de `Acces.GroupesAdmin` (même configuration que l'interface) ; les droits NTFS du dossier de paramétrage restent la protection de fond |
| Traçabilité | Chaque version porte le **compte**, la date et le **commentaire** préfixé de l'appelant (`[API mon_script] …`) ; chaque action est aussi écrite dans `ApiRegles_AAAA-MM-JJ.jsonl` du dossier de journal de l'interface (`Journal.Dossier`), si configuré |

Le module lit `Gui\Gestion-Copie.config.psd1` (ou le fichier passé en `-Config`) : mêmes réglages du moteur (Python, racine, mode Local/Distant/JEA), des versions de format acceptées (`Parametrage.VersionsSupportees`) et des dossiers de versions/brouillons.

## 2. Depuis PowerShell

```powershell
Import-Module D:\Scripts\file_management\Gui\FileManagement.Regles\FileManagement.Regles.psd1

$f = 'D:\Parametrage\prod.jsonl'
Get-CopieApiInfo                                   # version de l'API, version du format du moteur
Get-CopieApiModele                                 # tous les champs valides et leurs valeurs de secours

$l = Get-CopieApiRegle -Fichier $f                 # règles + empreinte du fichier lu
Add-CopieApiRegle -Fichier $f -Commentaire 'ajout flux X (ticket 123)' -Appelant 'mon_script' -Empreinte $l.Empreinte -Regle @{
    id = 'flux_x'; source = '\\srv\a'; cible = '\\srv\b'; mode = 'copie'
    planification = @{ type = 'intervalle'; frequence_sec = 600; debut = '06:00'; fin = '20:00' } }

Set-CopieApiRegle    -Fichier $f -Id flux_x -Modification @{ actif = $false } -Commentaire 'suspendu'
Remove-CopieApiRegle -Fichier $f -Id flux_x -Commentaire 'flux arrêté'
```

| Fonction | Rôle |
|---|---|
| `Get-CopieApiInfo` | `VersionApi`, `VersionFormat` du moteur, `VersionsSupportees` |
| `Get-CopieApiModele` | La règle par défaut du moteur (référence du format) |
| `Get-CopieApiRegle` `-Fichier` `[-Id]` | Lecture seule : `Regles` (ou `Regle`), `Entete`, `Empreinte` |
| `Add-CopieApiRegle` | Ajoute une règle (champ `id` obligatoire) ; les champs absents prennent la valeur de secours du moteur ; id déjà pris = étape `existe` |
| `Set-CopieApiRegle` | Modifie : seuls les champs fournis changent, les objets (`selection`, `planification`, `situations`…) sont fusionnés champ par champ, une liste ou une valeur est remplacée, `$null` vide un champ |
| `Remove-CopieApiRegle` | Supprime une règle (refusée par le moteur si d'autres en dépendent : D01) |

Paramètres communs d'écriture : `-Commentaire` (**obligatoire**, tracé), `-Appelant`, `-Empreinte` (concurrence optimiste, voir §4), `-AccepterAvertissements`, `-Config`.

### Résultat

Chaque écriture renvoie un objet `Copie.ApiResultat` : `Succes`, `Etape`, `Message`, `Refus` (liste `code`, `message`, `regle`, `ligne`), `Avertissements`, `Version` (fichier de la version précédente conservée), `Empreinte` (du nouveau fichier), `Regle` (règle écrite, complète), `VersionApi`.

| `Etape` | Sens |
|---|---|
| `ok` | Écrit |
| `droits` | Le compte n'est pas dans `Acces.GroupesAdmin` |
| `configuration` / `moteur` / `version` | Configuration inutilisable, moteur injoignable, **version de format non prise en charge** (fichier ou moteur) : l'API refuse d'écrire plutôt que de deviner |
| `lecture` | Fichier introuvable ou illisible |
| `invalide` | Appel incomplet (pas d'`id`, commentaire vide, JSON illisible) |
| `existe` / `introuvable` | Ajout d'un id déjà pris / modification ou suppression d'une règle absente |
| `conflit` | Le fichier a changé (voir §4) |
| `refus` | Le moteur refuse le paramétrage : `Refus` donne les codes, le fichier n'est pas touché |
| `avertissements` | Le moteur donne des avertissements et `-AccepterAvertissements` n'a pas été passé : rien n'est écrit, `Avertissements` les liste |
| `ecriture` | Erreur d'écriture (droits NTFS, disque) |

## 3. Depuis Python (ou tout autre langage)

`Gui\FileManagement.Regles\Invoke-RegleApi.ps1` est le point d'entrée en ligne de commande : paramètres en `-EntreeJson` (fichier JSON UTF-8), résultat en JSON (`-SortieJson` ou sortie standard), noms de champs en minuscules (`succes`, `etape`, `message`, `refus`, `avertissements`, `version`, `empreinte`, `regle`, `version_api`…).

Code retour : **0** fait · **1** refusé ou impossible (lire `etape` et `message`) · **2** erreur d'emploi ou erreur technique.

```text
powershell.exe -NoProfile -File Invoke-RegleApi.ps1 -Action modifier -Fichier D:\Parametrage\prod.jsonl -Id flux_x -EntreeJson demande.json -SortieJson resultat.json
demande.json : {"modification": {"actif": false}, "commentaire": "suspendu", "appelant": "mon_script", "empreinte": "", "accepter_avertissements": false}
```

Actions : `info`, `modele`, `lire`, `ajouter` (champ `regle`), `modifier` (champ `modification`), `supprimer`.

Un client Python prêt à l'emploi (bibliothèque standard seule) est fourni : `Gui\FileManagement.Regles\Clients\copie_regles_client.py`.

```python
from copie_regles_client import ClientRegles

api = ClientRegles(appelant="mon_script")
f = r"D:\Parametrage\prod.jsonl"
lecture = api.lire(f)
res = api.ajouter(f, {"id": "flux_x", "source": r"\\srv\a", "cible": r"\\srv\b", "mode": "copie"},
                  commentaire="ajout flux X", empreinte=lecture["empreinte"])
if not res["succes"]:
    print(res["etape"], res["message"], res["refus"])
```

Un refus métier n'est **pas** une exception (`res["succes"]` vaut `False`) ; `ErreurApi` signale une panne technique (PowerShell introuvable, sortie illisible). Le script s'exécute avec **le compte de l'appelant** : celui-ci doit être dans `Acces.GroupesAdmin` et avoir le droit d'écrire dans le dossier de paramétrage (un programme planifié utilise un compte de service ajouté à ce groupe).

## 4. Concurrence : deux écrivains en même temps

- **Sans `-Empreinte`** : l'API lit, applique votre modification et écrit ; si quelqu'un a modifié le fichier entre-temps (l'interface, un autre programme), elle **relit et recommence** (3 essais). Adapté à « ajoute/modifie telle règle, peu importe le reste ».
- **Avec `-Empreinte`** (celle de `Get-CopieApiRegle`) : le moindre écart avec le fichier lu est un **`conflit`** rendu à l'appelant, sans rien écrire. À utiliser quand la modification dépend de ce que vous avez lu.
- Dans tous les cas, l'empreinte est **recontrôlée juste avant le remplacement** du fichier : on n'écrase jamais le travail d'un autre.

## 5. Évolution du format

- Ajout d'un champ de règle : rien à changer chez les appelants. `Add-/Set-CopieApiRegle` complètent avec le modèle du moteur ; un champ que l'appelant fournit mais que le moteur ne connaît plus est refusé (E06), pas perdu en silence.
- Changement **incompatible** (`version_format` du moteur absent de `Parametrage.VersionsSupportees`) : l'API **refuse d'écrire** (étape `version`) tant que le module n'a pas été mis à jour avec le moteur (ils se livrent ensemble).
- `VersionApi` (1) ne change que si les fonctions ou leurs résultats changent de façon incompatible ; un champ ajouté au résultat ne la change pas.

## 6. Ce que l'API ne fait pas

Elle ne crée pas d'environnement (en-tête), ne lance pas de règle, ne lit pas l'état d'exécution (voir le contrat moteur, [07](07-contrat-moteur-frontend.md)) et ne contourne aucun contrôle : le moteur vérifie tout enregistrement, comme pour l'interface.

Tests : cahier [06](06-cahier-de-tests.md), J10F-A23 (`Gui\Tests\Api.Tests.ps1`).
