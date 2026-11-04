# Tests et outils de développement

| Élément | Rôle |
|---|---|
| `tests/test_v1_caracterisation.py` | Fige le comportement du script actuel (`copie_fichiers.py`, v1) : paramétrage, copie vérifiée, historique, verrou, codes retour. |
| `tests/outils.py` | Classe de base `CasTemporaire` : dossier temporaire par test, création de fichiers datés. |
| `outils/lancer_tests.ps1` | Lance tous les tests avec le Python choisi ; un avertissement de dépréciation fait échouer. |
| `outils/controle_serveur.py` | À exécuter **sur le serveur de recette** avec Python 3.14 : vérifie SQLite (WAL, écritures concurrentes), espace disque, verrous, Job Object, remplacement atomique, partage réseau. |
| `tests/test_parametrage.py` | J1 : lecture et validation du paramétrage, un groupe de tests par code (E, R, P, D, G) et la ligne de commande. |
| `tests/test_base.py`, `tests/travailleurs.py` | J2 : base SQLite (schéma, flag atomique, journal d'intention, purge, sauvegarde) ; les tests de concurrence lancent de vrais processus séparés (`multiprocessing` n'est pas utilisable avec `python -m unittest`). |
| `tests/test_chemins_selection.py`, `tests/test_moteur.py`, `tests/test_lancer_regle.py` | J4 : chemins et noms, sélection, copie vérifiée, exécution d'une règle (copie, déplacement, archivage, archive dégradée, espace disque, situations, arrêts brutaux, simulation) et commande `--lancer-regle`. Utilisent de vrais fichiers, de vrais verrous Windows et des pannes injectées. |
| `tests/test_planification.py`, `tests/test_lancement.py` | J5 : creneaux, regle due, rattrapage et changement d'heure (horloge simulee, fuseau fictif), lancement sequentiel, orphelins, reprise, acquittement, `--etat` et ligne de commande. |
| `tests/test_orchestrateur.py` | J6 : dependances (EN_ATTENTE, BLOQUEE, cascade), processus fils reels, parallelisme, duree maximale (erreur, relancer, alerter), arret de l'arbre de processus, fins anormales, Job Object. |
| `tests/test_programmes.py` | J7 : programmes externes aux six points d'appel (codes retour, tentatives, variables, listes, arbre de processus, avant_fichier qui modifie la source, apres_fichier en echec, reprise, simulation). |
| `tests/test_acces.py`, `tests/test_contrat.py` | J8 : controles d'acces A01-A07, comparaison de versions V01-V04, `--debloquer` (processus reels), contrat JSON avec le front-end (cles exactes, UTF-8, aucune pollution de la sortie). |
| `tests/test_jenkins.py` | J9 : `journal_si.py` en ligne de commande (evenements de job), coherence statique des Jenkinsfile et de la bibliotheque Groovy (non executee), builds simultanes et abandon d'un build avec de vrais processus. |
| `jenkins/` | Jenkinsfile (transfert, sauvegarde, verification) et bibliotheque partagee `journal-si` (`vars/journalSI.groovy`, `vars/copieFichiers.groovy`). |
| `outils/mesure_transfert.py` | Mesure sur le serveur : débit de livraison (copie, déplacement, relance), cible locale ou réseau. |
| `tests/test_journal.py` | J3 : module `journal_si.py` (format, fichiers, pannes, charge entre processus). |
| `outils/charge_journal.py` | Test de charge du journal sur le serveur : 8 processus × 10 000 lignes dans un même fichier. |
| `outils/mesure_base.py` | Mesure sur le serveur : recherche dans un million d'empreintes, taille de la base, coût d'une transaction durable. |
| `copie/` | Package de la v2 : `parametrage.py` (lecture), `controles.py` (contrôles croisés), `diagnostic.py` (codes), `base.py` (SQLite), `selection.py`, `chemins.py`, `transfert.py`, `execution.py` (transfert d'une règle), `planification.py`, `lancement.py`, `orchestrateur.py`, `dependances.py`, `programmes.py`, `acces.py`, `comparaison.py`, `processus.py`, `__main__.py` (`python -m copie --verifier / --initialiser-base / --sauvegarder-base / --lancer-regle`). |
| `exemples/` | Fichiers d'essai : paramétrage `production.jsonl` (valide) et `invalide/production.jsonl` (6 refus), sortie du journal `journal/`, configuration `alloy/` (non testée). |

```powershell
.\outils\lancer_tests.ps1 -Python C:\Python314\python.exe
C:\Python314\python.exe outils\controle_serveur.py --partage \\SERVEUR\partage\test --json controle.json
```

Le script v1 n'est pas modifié. Quand la v2 remplacera v1, les tests de caractérisation seront adaptés un par un, avec la raison de chaque écart.
