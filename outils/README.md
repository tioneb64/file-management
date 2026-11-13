# Boîte à outils (`outils\`)

Des **outils unitaires**, un script Python par tâche (compresser, chercher, renommer, convertir, valider, notifier…), prévus pour être appelés par les **programmes externes d'une règle** du moteur (`avant_lot`, `avant_fichier`, `apres_fichier`, `apres_lot`, `sur_erreur`, `reprise` ; voir [docs/02-moteur.md §9](../docs/02-moteur.md)). Chacun se lance aussi à la main. Contrat complet, journal, sécurité et écriture d'un nouvel outil : [docs/13-boite-a-outils.md](../docs/13-boite-a-outils.md).

- **Une variable par outil** : `{outil:nom}` (le nom est celui de la colonne « Outil » ci-dessous) dans le premier élément de la `commande`, à la place de l'interpréteur et du chemin du script. La liste des outils, des variables et des paramètres est dans l'onglet **Outils** de l'interface, alimentée par un scan ; le dossier des outils se règle au niveau du moteur (vide = ce dossier). Un script **sans en-tête** (`# outil: …`) n'est pas un outil. Voir [docs/13-boite-a-outils.md](../docs/13-boite-a-outils.md) §7, §9 à §11.
- Python 3.14, **bibliothèque standard seulement**. Les dépendances facultatives (7-Zip, WinRAR, `pyzipper`, LibreOffice, Pillow) sont détectées proprement : absentes, l'outil s'arrête avec le **code 4** et un message clair, jamais une trace Python.
- **Chaque outil journalise ses actions** avec la même bibliothèque que le moteur (`journal_si`), **dans le même fichier que la règle** (`<dossier_logs>\<règle>_<AAAA-MM-JJ>.jsonl`), avec la même trace, le même `execution_id` et `service.name = file_management.<règle>`.
- `--simulation` partout où l'outil écrit ou supprime : il décrit sans rien faire (et la variable `COPIE_SIMULATION=1`, transmise par `--simulation-programmes`, a le même effet).
- Jamais d'écrasement sans `--ecraser`, écritures atomiques (`.copie_en_cours` puis renommage), un élément en erreur n'arrête pas les suivants (code 2 à la fin), aucun mot de passe sur la ligne de commande ni dans le journal.

## Exemple : une règle qui valide, copie, puis fait l'empreinte

```json
"programmes": {
  "avant_fichier": {"commande": ["{outil:valider_fichier}",
                                 "{fichier}", "--format", "csv", "--colonnes", "id,nom", "--code-si-invalide", "1"], "timeout_sec": 60},
  "apres_fichier": {"commande": ["{outil:empreinte}",
                                 "{fichier_cible}", "--generer"], "timeout_sec": 60},
  "sur_erreur":    {"commande": ["{outil:webhook}",
                                 "--url", "https://hooks.exemple.test/abc", "--auto"], "timeout_sec": 60}
}
```

`valider_fichier` rend **1** pour un fichier invalide (le moteur l'ignore sans erreur à `avant_fichier`) ; `empreinte` écrit `a.csv.sha256` à côté du fichier livré ; `webhook` envoie le contexte de la règle (`regle`, `statut`, `situation`, `message`…) quand elle s'arrête en erreur.

La forme longue reste valable : `["C:\\Python314\\python.exe", "D:\\Scripts\\file_management\\outils\\controle\\empreinte.py", "{fichier_cible}", "--generer"]`. Avec `{outil:nom}`, l'outil est retrouvé par l'index `outils.json` : déplacer le dossier des outils ne demande qu'un nouveau scan, pas de réécrire les règles. Un nom inconnu est refusé par `--verifier` (G01) avec la liste des outils indexés.

Dans les tableaux ci-dessous, seuls les **arguments** sont donnés (ceux qui suivent `{outil:nom}`). Les variables `{source}`, `{cible}`, `{archive}`, `{date}`, `{regle}`, `{environnement}`, `{fichier}`, `{nom}`, `{fichier_cible}`, `{liste}` sont remplacées par le moteur, **un élément = un argument**, sans shell. Toutes les options : `--aide`.

## Codes retour

| Code | Sens |
|---|---|
| `0` | Fait (ou rien à faire, sans `--code-si-rien 1`) |
| `1` | « Rien à faire » **seulement avec `--code-si-rien 1`** ; certains outils ont une option qui le rend pour un fichier à ignorer (`valider_fichier --code-si-invalide 1`, `espace_disque --code-si-insuffisant 1`) |
| `2` | Erreur d'exécution (au moins un élément en erreur ; les autres ont été traités, sauf `--arreter-si-erreur`) |
| `3` | Paramètres invalides |
| `4` | Dépendance externe absente (programme ou module facultatif) |

Le moteur accepte `0` et `1` à chaque point d'appel et traite tout autre code comme un échec de la situation `programme_<point>` (avec ses tentatives).

## Options communes

| Option | Effet |
|---|---|
| `--simulation` | Ne fait rien, décrit (et journalise `simulation: true`). Aussi `COPIE_SIMULATION=1` |
| `--code-si-rien 1` | Code retour 1 quand l'outil n'a rien eu à faire |
| `--arreter-si-erreur` | Arrête au premier élément en erreur |
| `--dossier-logs`, `--regle`, `--environnement` | Journal : repris des variables `COPIE_DOSSIER_LOGS`, `COPIE_REGLE`, `COPIE_CODE_ENVIRONNEMENT` du moteur ; à renseigner pour un lancement à la main |
| `--console`, `--verbeux` | Journal aussi sur la console ; niveau DEBUG |
| `CHEMIN…`, `--liste FICHIER`, `--masque`, `--exclure`, `--recursif` / `-r` | Fichiers à traiter. Sans rien : `COPIE_FICHIER`, sinon `COPIE_LISTE` (le lot), sinon `COPIE_SOURCE` |
| `--mot-de-passe-env NOM`, `--mot-de-passe-fichier F` | Mot de passe (jamais en clair sur la ligne de commande) |
| `--aide` | Aide (ASCII) |

## Compression et archives (`compression\`)

| Outil | Rôle | Exemple d'arguments | Dépendance |
|---|---|---|---|
| `zip_creer` | zip de fichiers et de dossiers | `--liste {liste} --sortie D:\Archives\{regle}_{date}.zip` | — |
| `zip_extraire` | extrait des zip (anti zip-slip, `--taille-max`) | `{fichier} --vers D:\Travail\{regle} --taille-max 2G` | — |
| `archive_creer` | tar, tar.gz, tar.bz2, tar.xz, 7z, rar (selon l'extension de `--sortie`) | `--liste {liste} --sortie D:\Archives\lot.7z` | 7z : `7z.exe` ; rar : `rar.exe` (WinRAR) |
| `archive_extraire` | extrait zip, tar*, 7z, rar, **iso** | `{fichier} --vers D:\Travail\x --un-dossier-par-archive` | 7z, rar, iso : `7z.exe` |
| `zip_chiffrer` | zip chiffré **AES-256** | `--liste {liste} --sortie D:\Archives\lot.zip --mot-de-passe-env ZIP_MDP` | `pyzipper` (conseillé) ou `7z.exe` |
| `fichier_decouper` | coupe un gros fichier : `nom.001`, `nom.002`… + `nom.manifeste.json` | `{fichier} --taille 100M --vers D:\Sortie` | — |
| `fichier_recoller` | recolle les morceaux (suite des numéros et SHA-256 vérifiés) | `D:\Sortie\gros.bin.001 --sortie D:\Sortie\gros.bin` | — |

Le format **ISO** n'est qu'**extrait** (7-Zip sait le lire ; il n'existe ni outil standard ni outil fiable pour le créer).

## Recherche et contenu (`recherche\`)

| Outil | Rôle | Exemple d'arguments |
|---|---|---|
| `chercher_nom` | par nom (jokers `--nom`, expression `--regex`), taille, âge ; `--sortie-liste` | `{source} --nom *.csv --code-si-rien 1` |
| `chercher_contenu` | texte ou expression dans le contenu, encodage détecté, binaires ignorés | `{source} -r --masque *.log --texte ERREUR --code-si-rien 1` |
| `remplacer_contenu` | chercher / remplacer en masse (encodage, BOM et fins de ligne conservés) | `{fichier} --chercher ancien --remplacer nouveau --sauvegarde` |
| `doublons_trouver` | doublons par SHA-256, **ne modifie rien** ; rapport `.json` / `.csv` | `{cible} -r --rapport D:\Rapports\doublons.csv --ecraser` |

## Renommer et organiser (`organisation\`)

| Outil | Rôle | Exemple d'arguments |
|---|---|---|
| `renommer_masse` | préfixe, suffixe, numérotation, expression, date EXIF (`{date}`) | `{cible} -r --regex "\s+" --par _` ; `--modele "{date}_{n}" --date-exif` |
| `noms_normaliser` | accents, espaces, caractères interdits sous Windows, noms réservés | `{source} --ascii --minuscules` (à `avant_lot` : la source est relue ensuite) |
| `trier_fichiers` | tri par type, par date ou par extension | `{cible} --par date --vers D:\Tries --copier` |
| `doublons_supprimer` | supprime ou met en quarantaine les copies (l'action est **obligatoire**) | `{cible} -r --action deplacer --vers D:\Quarantaine` |

Renommer au point `avant_fichier` le fichier même que traite la règle le lui ferait perdre : renommer la **source** à `avant_lot`, ou la **cible** à `apres_lot`.

## Conversion (`conversion\`)

| Outil | Rôle | Exemple d'arguments | Dépendance |
|---|---|---|---|
| `encodage_convertir` | UTF-8, UTF-8 avec BOM, ANSI (cp1252), Latin-1, UTF-16 | `{fichier} --vers utf-8` | — |
| `fin_ligne_convertir` | CRLF <-> LF | `{fichier} --vers crlf` | — |
| `xlsx_vers_csv` | classeur Excel -> CSV (une ou toutes les feuilles ; formules non recalculées) | `{fichier} --vers D:\Echange --ecraser` | — |
| `document_vers_pdf` | docx, doc, odt, rtf, xlsx, pptx… -> PDF | `{fichier_cible} --vers D:\PDF` | LibreOffice (`soffice`) |
| `image_convertir` | png <-> jpg <-> webp…, redimensionner, compresser | `{fichier} --format jpg --largeur-max 1920 --vers D:\Images` | Pillow |

## Dates et attributs (`dates_attributs\`)

| Outil | Rôle | Exemple d'arguments |
|---|---|---|
| `touch` | dates de création (Windows), modification, accès ; `--copier-de`, `--decaler=-1j` | `{fichier_cible} --modification "2026-01-01 08:00"` |
| `attributs` | lecture seule, caché, système, archive | `{fichier_cible} --lecture-seule oui` |
| `permissions` | ACL Windows (`icacls`) : afficher, accorder, refuser, retirer, héritage, propriétaire | `{fichier_cible} --accorder *S-1-5-32-545:R` |

## Manipulation de fichiers (`fichiers\`)

| Outil | Rôle | Exemple d'arguments |
|---|---|---|
| `copier_verifie` | copie + relecture SHA-256 (`--deplacer` supprime la source ensuite) | `{fichier_cible} --vers D:\Copie2` |
| `texte_decouper` | découpe un fichier texte par lignes ou par taille, `--entete` répété | `{fichier} --lignes 100000 --entete --vers D:\Morceaux` |
| `csv_fusionner` | fusionne des CSV (en-tête unique, colonnes contrôlées) | `{source} --masque *.csv --sortie D:\Fusion\{regle}.csv --ecraser` |
| `comparer_fichiers` | diff de deux fichiers ou de deux dossiers | `{source} {cible} -r --erreur-si-different` |
| `synchroniser` | miroir à la robocopy avec **simulation** et garde-fous (`--miroir`, `--max-suppressions`) | `{source} {cible} --miroir --max-suppressions 50` |
| `dossiers_vides_supprimer` | supprime les dossiers vides, du plus profond au plus haut | `{source} --ignorer Thumbs.db` |
| `inventaire` | liste un dossier (chemin, taille, date, SHA-256) en CSV ou JSON | `{cible} --sortie D:\Inventaires\{regle}_{date}.csv --sha256` |

## Contrôle (`controle\`)

| Outil | Rôle | Exemple d'arguments |
|---|---|---|
| `attendre_stable` | attend qu'un fichier ne change plus et ne soit plus verrouillé | `{fichier} --duree-stable 10 --delai-max 600` |
| `valider_fichier` | non vide, taille, JSON / XML / CSV bien formé, colonnes, encodage | `{fichier} --format csv --colonnes id,nom --code-si-invalide 1` |
| `empreinte` | génère / vérifie / affiche des SHA-256 (`.sha256` voisin ou manifeste) | `{fichier_cible} --generer` puis `--verifier` |
| `espace_disque` | espace libre minimal, place nécessaire pour des fichiers | `{cible} --pour {source} --marge 1G` |

## Notification (`notification\`)

| Outil | Rôle | Exemple d'arguments |
|---|---|---|
| `courriel` | courriel SMTP (`{regle}`, `{statut}`, `{situation}`, `{message}`… dans le sujet et le corps ; pièces jointes) | `--serveur smtp.exemple.test --de moteur@exemple.test --a equipe@exemple.test --sujet "[{environnement}] {regle} : erreur"` |
| `webhook` | POST JSON (Teams, Slack, supervision…) ; `--auto` ajoute le contexte de la règle ; nouvelles tentatives sur 5xx | `--url https://hooks.exemple.test/abc --auto` |

Prévus pour `sur_erreur`. Le jeton d'un webhook se donne par `--en-tete-env "Authorization=NOM_VARIABLE"`, le mot de passe SMTP par `--mot-de-passe-env`.

## Transfert (`transfert\`)

| Outil | Rôle | Exemple d'arguments |
|---|---|---|
| `sftp_envoyer` | dépose des fichiers sur un serveur SFTP (nom temporaire `.tmp` puis renommage, contrôle taille ou SHA-256, reprise après coupure) ; `--apres-envoi archiver\|supprimer` ; `--creer-dossiers` ; `-r` | `--hote sftp.exemple.test --utilisateur compte --mot-de-passe-env MDP_SFTP --empreinte-hote SHA256:abc… --distant /depot {fichier}` |
| `sftp_recuperer` | relève un dossier distant (`--masque`, `-r`, `--age-minimum 60` pour laisser de côté un fichier en cours de dépôt) ; `--apres-recuperation archiver\|supprimer` | `--hote … --utilisateur … --mot-de-passe-env MDP_SFTP --empreinte-hote SHA256:abc… --distant /sortie --local {cible} --apres-recuperation archiver --archive-distant /sortie/archive` |

Nécessitent `pip install paramiko` (code 4 sinon). Règles : la clé de l'hôte est **toujours vérifiée** (empreinte attendue ou `known_hosts` ; hôte inconnu refusé, sauf `--hote-inconnu accepter` avec avertissement) ; le mot de passe se donne par `--mot-de-passe-env` / `--mot-de-passe-fichier` (jamais sur la ligne de commande, jamais au journal), la clé privée par `--cle-privee` (+ `--phrase-env`) ; une authentification refusée n'est **pas rejouée**, un incident réseau l'est (`--tentatives`, `--pause`) ; rien n'est écrasé sans `--ecraser`, et `--ignorer-existants` laisse passer un fichier déjà présent. `--simulation` se connecte (lecture seule) pour contrôler les conflits mais n'écrit rien.

## Dépendances facultatives

| Dépendance | Pour | Si absente |
|---|---|---|
| `7z.exe` (7-Zip), variable `OUTIL_7Z` pour en donner le chemin | 7z, rar et iso (lecture), zip AES sans `pyzipper` | code 4, message « installer 7-Zip… » |
| `rar.exe` (WinRAR), `OUTIL_RAR` | création de rar | code 4 |
| `pyzipper` (`pip install pyzipper`) | zip AES-256 sans exposer le mot de passe | repli sur 7-Zip, sinon code 4 |
| LibreOffice, `OUTIL_SOFFICE` | `document_vers_pdf` | code 4 |
| Pillow (`pip install Pillow`) | `image_convertir` | code 4 |
| `paramiko` (`pip install paramiko`) | `sftp_envoyer`, `sftp_recuperer` | code 4 |

## Tests

`tests\test_outils_<domaine>.py` (un fichier par domaine), `tests\test_outils_moteur.py` (appels par de vraies règles du moteur), `tests\test_outils_variables.py` (en-têtes, scan, index, variable `{outil:nom}`), `tests\boite_outils.py` (aides communes). Lancés par `.\outils\lancer_tests.ps1` avec toute la suite. Détail dans le [cahier de tests](../docs/06-cahier-de-tests.md) (jalon « Boîte à outils »).
