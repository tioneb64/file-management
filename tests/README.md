# Tests et outils de développement (jalon J0)

| Élément | Rôle |
|---|---|
| `tests/test_v1_caracterisation.py` | Fige le comportement du script actuel (`copie_fichiers.py`, v1) : paramétrage, copie vérifiée, historique, verrou, codes retour. |
| `tests/outils.py` | Classe de base `CasTemporaire` : dossier temporaire par test, création de fichiers datés. |
| `outils/lancer_tests.ps1` | Lance tous les tests avec le Python choisi ; un avertissement de dépréciation fait échouer. |
| `outils/controle_serveur.py` | À exécuter **sur le serveur de recette** avec Python 3.14 : vérifie SQLite (WAL, écritures concurrentes), espace disque, verrous, Job Object, remplacement atomique, partage réseau. |
| `copie/` | Package de la v2 (vide pour l'instant, rempli à partir de J1). |

```powershell
.\outils\lancer_tests.ps1 -Python C:\Python314\python.exe
C:\Python314\python.exe outils\controle_serveur.py --partage \\SERVEUR\partage\test --json controle.json
```

Le script v1 n'est pas modifié. Quand la v2 remplacera v1, les tests de caractérisation seront adaptés un par un, avec la raison de chaque écart.
