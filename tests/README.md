# Tests et outils de développement

| Élément | Rôle |
|---|---|
| `tests/test_v1_caracterisation.py` | Fige le comportement du script actuel (`copie_fichiers.py`, v1) : paramétrage, copie vérifiée, historique, verrou, codes retour. |
| `tests/outils.py` | Classe de base `CasTemporaire` : dossier temporaire par test, création de fichiers datés. |
| `outils/lancer_tests.ps1` | Lance tous les tests avec le Python choisi ; un avertissement de dépréciation fait échouer. |
| `outils/controle_serveur.py` | À exécuter **sur le serveur de recette** avec Python 3.14 : vérifie SQLite (WAL, écritures concurrentes), espace disque, verrous, Job Object, remplacement atomique, partage réseau. |
| `tests/test_parametrage.py` | J1 : lecture et validation du paramétrage, un groupe de tests par code (E, R, P, D, G) et la ligne de commande. |
| `tests/test_base.py`, `tests/travailleurs.py` | J2 : base SQLite (schéma, flag atomique, journal d'intention, purge, sauvegarde) ; les tests de concurrence lancent de vrais processus séparés (`multiprocessing` n'est pas utilisable avec `python -m unittest`). |
| `tests/test_journal.py` | J3 : module `journal_si.py` (format, fichiers, pannes, charge entre processus). |
| `outils/charge_journal.py` | Test de charge du journal sur le serveur : 8 processus × 10 000 lignes dans un même fichier. |
| `outils/mesure_base.py` | Mesure sur le serveur : recherche dans un million d'empreintes, taille de la base, coût d'une transaction durable. |
| `copie/` | Package de la v2 : `parametrage.py` (lecture), `controles.py` (contrôles croisés), `diagnostic.py` (codes), `base.py` (SQLite), `__main__.py` (`python -m copie --verifier / --initialiser-base / --sauvegarder-base`). |
| `exemples/` | Fichiers d'essai : paramétrage `production.jsonl` (valide) et `invalide/production.jsonl` (6 refus), sortie du journal `journal/`, configuration `alloy/` (non testée). |

```powershell
.\outils\lancer_tests.ps1 -Python C:\Python314\python.exe
C:\Python314\python.exe outils\controle_serveur.py --partage \\SERVEUR\partage\test --json controle.json
```

Le script v1 n'est pas modifié. Quand la v2 remplacera v1, les tests de caractérisation seront adaptés un par un, avec la raison de chaque écart.
