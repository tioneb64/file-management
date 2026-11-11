# file_management v2

Transfert **fiable** de fichiers entre dossiers, ordonnancé par Jenkins sur Windows Server 2016 : copie, déplacement ou archivage, réglés **règle par règle**, avec planification, dépendances entre règles, reprise après erreur et journaux pour Grafana. Les logiciels du système d'information échangent en déposant des fichiers dans un dossier ; cet outil les y dépose sans jamais en perdre, doubler ou livrer à moitié.

Il se compose de quatre éléments :

| Élément | Où | Rôle |
|---|---|---|
| **Moteur** | `file_management\` (`python -m file_management`) | Python 3.14, bibliothèque standard seulement. Lit le paramétrage, tient l'état dans une base SQLite, exécute les transferts, écrit les journaux JSON |
| **Jenkins** | `jenkins\` | Jobs de transfert (toutes les 5 minutes), sauvegarde, vérification et purge ; bibliothèque `journal-si` |
| **Interface de gestion** | `Gui\` | Application PowerShell 5.1 / WPF : consulter l'état, modifier le paramétrage, reprendre, acquitter, promouvoir, historique |
| **Point d'accès JEA** | `Gui\Jea\`, `Gui\Installer-PointAccesJea.ps1` | Accès restreint au moteur depuis un poste distant (facultatif) |

## Garanties

Aucune perte (l'original n'est touché qu'après copie vérifiée par taille et SHA-256), aucun doublon (même après un arrêt brutal : le moteur s'arrête et demande une décision plutôt que de relivrer), aucun fichier incomplet visible (écriture temporaire puis renommage atomique), pas de base pas de traitement, une règle bloquée ne bloque pas les autres, chaque action d'exploitation tracée avec le compte. Liste complète : [docs/00-vue-ensemble.md](docs/00-vue-ensemble.md) §5.

## Par où commencer

| Je veux… | Lire |
|---|---|
| **Installer** | [docs/10-installation.md](docs/10-installation.md) |
| **Utiliser l'interface** (suivre, modifier, exploiter) | [docs/11-guide-utilisateur.md](docs/11-guide-utilisateur.md) |
| Écrire ou comprendre un fichier de paramétrage | [docs/01-parametrage.md](docs/01-parametrage.md) (exemple : `exemples\production.jsonl`) |
| Comprendre le comportement du moteur | [docs/02-moteur.md](docs/02-moteur.md), [docs/03-base-de-donnees.md](docs/03-base-de-donnees.md) |
| Configurer Jenkins | [docs/08-jenkins.md](docs/08-jenkins.md) |
| Migrer depuis l'ancien script | [docs/09-migration-et-recette.md](docs/09-migration-et-recette.md) |
| Intégrer un autre outil au moteur (JSON) | [docs/07-contrat-moteur-frontend.md](docs/07-contrat-moteur-frontend.md) |
| Rejouer les tests, suivre l'avancement | [docs/06-cahier-de-tests.md](docs/06-cahier-de-tests.md), [tests/README.md](tests/README.md), [CHANGELOG.md](CHANGELOG.md) |

Vue d'ensemble, architecture et décisions : [docs/00-vue-ensemble.md](docs/00-vue-ensemble.md).

## Le moteur en une minute

```bat
cd /d D:\Scripts\file_management
python -m file_management --config D:\Parametrage\production.jsonl --verifier                  REM valider le paramétrage et les accès
python -m file_management --config D:\Parametrage\production.jsonl --initialiser-base          REM une seule fois
python -m file_management --config D:\Parametrage\production.jsonl --simulation               REM voir ce qui serait livré
python -m file_management --config D:\Parametrage\production.jsonl                             REM lancement (ce que fait Jenkins)
python -m file_management --config D:\Parametrage\production.jsonl --etat                      REM état de chaque règle
python -m file_management --help                                                               REM toutes les commandes
```

Codes retour : `0` succès, `1` au moins une erreur pendant ce lancement, `2` commande refusée (paramétrage invalide, base absente, arguments), `4` succès avec avertissement. Avec `--format json`, toute commande répond par un objet JSON (contrat versionné, [docs/07](docs/07-contrat-moteur-frontend.md)).

## L'interface en une minute

```powershell
.\Gui\Lancer-GestionCopie.ps1 -DossierParametrage D:\Parametrage
```

Les membres du groupe AD configuré (`Gui\Gestion-Copie.config.psd1`) modifient, les autres consultent. Voir le [guide d'utilisation](docs/11-guide-utilisateur.md). Pour l'essayer sur un poste de développement sans toucher à la production : `Gui\Outils\Initialiser-Essai.ps1`.

## Tests

```powershell
.\outils\lancer_tests.ps1 -Python C:\Python314\python.exe      # moteur (rapport dans rapports\)
powershell.exe -NoProfile -STA -File .\Gui\Tests\Run-Tests.ps1 -Python C:\Python314\python.exe   # interface (Pester 5) + analyse
```

État : tests Python et Pester tous OK sur un poste Windows 10 (voir le [CHANGELOG](CHANGELOG.md)). **Pas encore rejoués sur le serveur Windows Server 2016**, dans le vrai Jenkins, ni avec une vraie session JEA : c'est l'objet de la colonne « Serveur » du cahier de tests.

## Ancien script (v1)

`file_management.py` et `copies.conf` restent en service jusqu'à la bascule, règle par règle. Leur documentation est conservée dans [docs/12-ancien-script-v1.md](docs/12-ancien-script-v1.md).

## Responsable

Responsable applicatif : Benoit Thibaudeau.
