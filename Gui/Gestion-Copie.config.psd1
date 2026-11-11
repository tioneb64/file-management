#
# Configuration de l'interface de gestion des transferts de fichiers (Lancer-GestionCopie.ps1).
# Le dossier des fichiers de paramétrage n'est PAS ici : il se passe au lancement (-DossierParametrage).
# Une clé inconnue est refusée (une faute de frappe ne doit pas être ignorée en silence).
# Les lignes marquées  # A ADAPTER  sont à vérifier avant le premier usage.
#
@{
    Acces = @{
        # Groupes dont les membres peuvent MODIFIER. Les autres comptes consultent seulement.
        # Forme acceptée : 'DOMAINE\Groupe', 'Groupe' (sans domaine) ou un SID ('S-1-5-21-...').
        # Aucun groupe renseigné : l'interface refuse de démarrer (jamais d'accès ouvert par défaut).
        GroupesAdmin = @('DOMAINE\GG_Copie_Admins')                   # A ADAPTER
    }

    Moteur = @{
        # Local   : le moteur (python -m file_management) est lancé sur cette machine.
        # Distant : il est lancé sur 'Serveur' par Invoke-Command, avec le compte de l'utilisateur,
        #           ou par un point d'accès JEA si 'ConfigurationJea' est renseignée (le point
        #           d'accès choisit alors lui-même Python et le dossier : Python et Racine inutiles).
        Mode             = 'Local'
        Python           = 'C:\Python314\python.exe'                  # A ADAPTER (sur la machine qui exécute le moteur)
        Racine           = 'D:\Scripts\file_management'                # A ADAPTER : dossier qui contient le paquet 'file_management'
        Serveur          = ''                                         # mode Distant
        ConfigurationJea = ''                                         # mode Distant : nom du point d'accès JEA, '' = compte de l'utilisateur
        DelaiMaxSec      = 120                                        # durée maximale d'un appel du moteur
    }

    Parametrage = @{
        Filtre            = '*.jsonl'                                 # fichiers lus dans le dossier de paramétrage
        VersionsSupportees = @(1)                                     # versions du format d'en-tête que l'interface sait lire
        DossierVersions   = 'versions'                                # sous-dossier des anciennes versions (relatif au dossier de paramétrage ; le compte de service n'y a pas accès)
        DossierBrouillons = '.brouillons'                             # sous-dossier où le moteur vérifie un fichier avant son enregistrement (le compte de service doit pouvoir le lire)
        DossierSupprimes  = '.supprimes'                                 # sous-dossier où sont rangés le fichier et les versions d'un environnement supprimé (rien n'est effacé)
        PeriodeDeclencheurSec = 300                                   # période du déclencheur Jenkins (contrôle P02)
    }

    Journal = @{
        # Journal de l'interface (JSON Lines, un fichier par jour) lu par Alloy. '' = pas de fichier.
        Dossier = ''                                                  # A ADAPTER
        Environnement = 'prod'                                        # code d'environnement de la plateforme d'observabilité : dev, build, test, pprod, prod, run, int
    }
}
