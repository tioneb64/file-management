# Spécifications — transfert sécurisé de fichiers (copie_fichiers v2)

| | |
|---|---|
| Statut | Validé le 2026-11-03 (hors éléments à fournir) |
| Date | 2026-11-03 |
| Responsable applicatif | Benoit Thibaudeau |
| Version du format de paramétrage | 1 |

Ces documents décrivent la **cible (v2)**. Le [README](../README.md) décrit le script actuel (v1) et reste valable jusqu'à la livraison de la v2.

| Document | Contenu |
|---|---|
| **00-vue-ensemble** (ce document) | Contexte, architecture, garanties, décisions, points validés |
| [01-parametrage](01-parametrage.md) | Format du fichier de paramétrage, champs, règles de validation |
| [02-moteur](02-moteur.md) | Comportement du moteur Python : orchestration, copie, modes, erreurs, journalisation |
| [03-base-de-donnees](03-base-de-donnees.md) | Base SQLite : tables, clés, transactions, maintenance |
| [04-frontend](04-frontend.md) | Application PowerShell de gestion du paramétrage et de l'état |
| [05-decoupage](05-decoupage.md) | Jalons de développement, tests, risques, mise en production |
| [09-migration-et-recette](09-migration-et-recette.md) | Passage de l'ancien script à la v2 règle par règle, recette, retour arrière |
| [08-jenkins](08-jenkins.md) | Jobs Jenkins, bibliothèque partagée, builds simultanés, codes retour, journaux de job |
| [07-contrat-moteur-frontend](07-contrat-moteur-frontend.md) | Commandes, codes retour et JSON échangés entre le moteur et le front-end |
| [06-cahier-de-tests](06-cahier-de-tests.md) | Tests joués sur le poste de développement puis sur le serveur de recette, complété à chaque jalon |

---

## 1. Contexte et objectifs

Le système d'information est composé de logiciels anciens, sans API. Les échanges se font en **déposant des fichiers dans un dossier** pour qu'un autre logiciel, ou un serveur SFTP, les prenne.

Le script actuel copie de façon incrémentale et vérifiée des fichiers de la production vers les environnements de test. La v2 en fait un **outil de transfert de production** :

- **Fiable** : aucun fichier perdu, aucun fichier livré en double, aucun fichier livré à moitié écrit.
- **Souple** : copie, déplacement ou archivage, réglés règle par règle ; réactions configurables à chaque anomalie ; programmes externes appelables avant et après chaque étape.
- **Ordonnancé** : plusieurs règles indépendantes en parallèle, avec dépendances entre règles et planification propre à chacune.
- **Observable** : journaux JSON pour la stack Grafana, état de chaque règle consultable.
- **Exploitable** : reprise après erreur depuis une interface, sans toucher aux fichiers de paramétrage ni à la base.

## 2. Périmètre

**Inclus dans la v2**

- Moteur de transfert (Python, bibliothèque standard uniquement).
- Base SQLite par environnement (état, historique des fichiers, audit).
- Fichier de paramétrage par environnement.
- Module de journalisation commun et format des journaux.
- Intégration Jenkins (Jenkinsfile type) ; format attendu par la Shared Library Groovy.
- Front-end PowerShell de gestion du paramétrage et de l'état.
- Outil de migration depuis le script actuel.

**Hors périmètre de la v2** (prévu plus tard, voir [05-decoupage](05-decoupage.md))

- Module de purge des journaux et des archives (paramétré depuis le même front-end, projet séparé).
- Fichiers témoins (`.ok`), conversion d'encodage, fichier `.sha256`, compression.
- Propagation des suppressions de la source vers la cible.
- Client SFTP : le moteur dépose dans un dossier, le serveur SFTP le publie.

## 3. Architecture

```
 Jenkins : un job par environnement, déclenché toutes les N minutes, builds parallèles autorisés
   │  Jenkinsfile + Shared Library (journaux de job : début, fin, statut)
   ▼
 copie_fichiers.py --config production.jsonl                    « orchestrateur »
   │  lit le paramétrage · évalue planification et dépendances · lit/écrit la base
   ├──► processus fils « règle A » ──► copie vérifiée ──► logs\regle_A_AAAA-MM-JJ.jsonl
   ├──► processus fils « règle B » ──► …
   ▼
 production.db  (SQLite, disque local)         parametrage\production.jsonl  (lu, jamais écrit par le moteur)
   ▲                                                          ▲
   └──────── commandes --etat / --reprise / … ──────┬─────────┘
                                                    │
                                    Front-end PowerShell (écriture : admins AD ; sinon consultation)

 logs\*.jsonl ──► Grafana Alloy ──► Loki ──► Grafana
```

| Composant | Technologie | Rôle |
|---|---|---|
| Moteur | Python 3.14, bibliothèque standard | Orchestrateur, exécution des règles, commandes d'exploitation |
| Base | SQLite (module `sqlite3`) | État des règles, historique des fichiers, actions en attente, audit |
| Paramétrage | JSON Lines (un fichier par environnement) | Décrit les règles ; lu par le moteur, écrit par le front-end |
| Journal | Module Python `journal_si.py` | Interface stable `debut()` / `evenement()` / `fin()` ; fichiers JSON lus par Alloy |
| Jenkins | Jenkinsfile + Shared Library Groovy | Déclenchement, journaux de niveau « job », statut du build |
| Front-end | PowerShell 5.1 | Saisie validée, consultation, actions de reprise |

## 4. Contraintes techniques

- **Python 3.14** sur le serveur d'exécution (version cible fixée par le responsable applicatif ; la 3.15 existe mais n'est pas retenue sur Windows Server 2016). Le code doit donc :
  - n'utiliser que la bibliothèque standard ;
  - ne pas dépendre de `zoneinfo` (sous Windows il exige le paquet `tzdata`, hors bibliothèque standard) : les horaires sont en heure locale du serveur ;
  - ne pas utiliser le mode « sans GIL » (build expérimental) ni les sous-interpréteurs : le parallélisme reste un processus par règle ;
  - utiliser le SQLite fourni avec Python 3.14 (3.50 ou plus) : UPSERT, WAL, `WITHOUT ROWID`, `RETURNING` disponibles, mais le schéma n'en dépend pas, pour pouvoir changer d'installation sans migration ;
  - ne pas utiliser de module retiré en 3.13 (`cgi`, `telnetlib`, `imp`, `asyncore`…) ;
  - être testé sur le serveur cible dès le jalon J0 (voir le point de vigilance ci-dessous).
- **Point de vigilance Python 3.14 sur Windows Server 2016** : les versions récentes de Python ne sont officiellement testées que sur les Windows encore maintenus par Microsoft. Windows Server 2016 est basé sur Windows 10 (1607) et devrait convenir, mais ce n'est pas garanti : le jalon J0 commence par installer la 3.14 sur le serveur de recette et exécuter `python -c "import sqlite3, ctypes, subprocess"` puis les tests. La fin de support de Windows Server 2016 (12 janvier 2027) renforce la nécessité de prévoir son remplacement.
- **Windows Server 2016** (fin de support Microsoft : 12 janvier 2027), **PowerShell 5.1**.
- La base SQLite est sur un **disque local** du serveur d'exécution (jamais sur un partage réseau).
- Horloges de tous les serveurs concernés synchronisées (NTP) : l'âge des fichiers est comparé à l'heure du serveur d'exécution.
- Compte de service Jenkins avec : lecture des sources, écriture des cibles et archives, écriture de la base, des journaux et du dossier de travail, **lecture seule** du paramétrage.
- Jenkins : « Do not allow concurrent builds » **désactivé**, nombre d'exécuteurs suffisant.

## 5. Garanties

| # | Garantie |
|---|---|
| G1 | **Aucune perte** : l'original n'est jamais supprimé ni déplacé avant que la copie soit vérifiée (taille et SHA-256) et enregistrée en base. |
| G2 | **Aucun doublon** : au plus une livraison par version de fichier. En cas de doute après un arrêt brutal, le moteur s'arrête et alerte au lieu de relivrer. |
| G3 | **Aucun fichier incomplet visible** : écriture dans un temporaire, puis renommage atomique. |
| G4 | Un original **modifié depuis la copie** n'est jamais supprimé ni archivé ; la nouvelle version sera livrée au lancement suivant. |
| G5 | Le moteur **ne modifie jamais** le fichier de paramétrage. |
| G6 | **Pas de base, pas de traitement** : si la base est absente ou inaccessible, rien n'est copié. |
| G7 | La **journalisation n'est jamais bloquante** : si elle échoue, le moteur écrit dans un journal local de secours. |
| G8 | **Une règle bloquée ne bloque pas les autres** : une règle = un processus, arrêté avec tous ses sous-processus en cas de dépassement de durée. |
| G9 | Toute **action d'exploitation** (reprise, acquittement, déblocage) est tracée avec le compte, l'heure et un commentaire. |

## 6. Glossaire

| Terme | Sens |
|---|---|
| **Environnement** | Production, recette, développement… Un fichier de paramétrage et une base par environnement. |
| **Règle** | Une ligne du paramétrage : un couple source / cible avec son mode, sa sélection, sa planification et ses réactions. Identifiée par un `id`. |
| **Lancement** | Une exécution du programme `copie_fichiers.py` par Jenkins. Il évalue toutes les règles. |
| **Exécution** | Un traitement complet d'une règle, dans un processus fils. |
| **Créneau** | Un instant prévu par la planification d'une règle (7h15, ou 5h00 + k × 5 min). |
| **Version d'un fichier** | Un fichier à un instant donné : même nom, même taille, même date de modification. |
| **Livraison** | Copie vérifiée d'une version vers la cible. |
| **Reprise** | Demande d'exploitation de relancer une règle tout de suite, quelle que soit sa planification. |
| **Acquittement** | Demande d'exploitation de considérer une règle en erreur comme corrigée, sans la relancer. |

## 7. Décisions arrêtées

| Thème | Décision |
|---|---|
| Langage, version | Python 3.14, bibliothèque standard (la 3.15 n'est pas retenue sur Windows Server 2016) |
| Parallélisme | Un processus par règle, piloté par un orchestrateur ; pas de maximum par défaut |
| Paramétrage | Un fichier par environnement : en-tête `{"version", "environnement", …}` puis une ligne JSON par règle |
| Modes | `copie`, `deplacement`, `archivage` — copier, vérifier, puis seulement toucher à l'original |
| Réglages | Tout est réglé **par règle** : mode, sélection, planification, réactions, programmes |
| Unités | L'unité est dans le **nom du champ**, la valeur est un entier (`age_minimum_sec`) |
| Planification | Format lisible ; le script est lancé souvent, chaque règle a sa fréquence ou son horaire |
| Dépendances | `apres` / `condition` / `si_condition_non_remplie` ; propagation ; statut `BLOQUEE` ; reprise en cascade |
| Règle inactive | Une règle active ne peut pas dépendre d'une règle inactive : enregistrement refusé |
| État | SQLite : flag « en cours » atomique, flag de reprise, exécutions, fichiers ; instants en timestamps |
| Après une erreur | `apres_erreur` = `arreter` par défaut ; `suite` = `arreter_regle` par défaut |
| Durée dépassée | `si_duree_depassee` = `erreur` par défaut |
| Archive inaccessible | Création du dossier si possible, sinon livraison poursuivie, fichiers notés en base, avertissement ; si la base est aussi inaccessible : arrêt |
| Anti-doublon | Empreinte hachée en base ; `si_cible_absente` = `ignorer` par défaut |
| Journaux | Module Python commun ; un fichier JSON par règle et par jour ; lu par Grafana Alloy |
| Code retour | 0 = OK, 1 = erreur, 2 = configuration ou infrastructure, 4 = avertissement (UNSTABLE) |
| Programmes externes | `avant_lot`, `avant_fichier` (modifie la source sur place), `apres_fichier`, `apres_lot`, `sur_erreur`, `reprise` |
| Front-end | PowerShell, modification réservée aux admins AD, consultation pour les autres ; passe par les commandes du script |
| Python | 3.14 ; installation validée sur le serveur de recette au jalon J0 |

## 8. Points validés le 2026-11-03

| # | Point | Décision |
|---|---|---|
| 1 | Identité d'un fichier pour l'anti-doublon | Empreinte hachée calculée depuis **nom + taille + date de modification** (`identite: "version"`, par défaut). L'option `"contenu"` (nom + SHA-256) reste disponible règle par règle. |
| 2 | Base obligatoire, sans fichier témoin en production | Validé : base créée seulement par `--initialiser-base`, état dégradé de l'archivage en base ([02-moteur §7](02-moteur.md)). |
| 3 | Condition `succes` | Remplie par `SUCCES`, `WARNING` et `ACQUITTEE`. |
| 4 | Code retour | Reflète les événements du lancement en cours, pas l'état persistant. |
| 5 | Programmes externes | `commande` est un tableau, sans shell. |
| 6 | Valeurs de secours des réactions | Tableau de [01-parametrage §6](01-parametrage.md) validé ; **autorisation donnée d'ajouter d'autres paramètres** si les tests en montrent la nécessité (ajout documenté dans 01 à chaque fois, valeur de secours conservant le comportement le plus prudent). |
| 7 | Version de Python | **3.14** (la 3.15 n'est pas retenue sur Windows Server 2016). Installation validée sur le serveur de recette au jalon J0. |

Aucun point en attente. Restent à fournir par le responsable applicatif les éléments listés au §8 de [05-decoupage](05-decoupage.md) et dans [04-frontend §10](04-frontend.md).
