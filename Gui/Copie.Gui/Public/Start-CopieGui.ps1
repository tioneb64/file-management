function Start-CopieGui {
    <#
    .SYNOPSIS
        Ouvre l'interface de gestion du paramétrage et de l'état des règles de copie_fichiers.

    .DESCRIPTION
        Le dossier des fichiers de paramétrage est un paramètre de lancement : il n'est écrit nulle part
        en dur. Un onglet par environnement (un fichier .jsonl = un environnement).

        Droits (docs/04-frontend.md §1, §7) : membre d'un groupe de Acces.GroupesAdmin = administrateur
        (modification) ; tout autre compte = consultation. La restriction de l'interface ne protège rien
        seule : le dossier de paramétrage doit aussi être protégé par ses droits NTFS (voir
        Initialiser-DossierParametrage.ps1) et le point d'accès distant limité au même groupe.

        L'interface ne lit jamais la base : l'état vient du moteur (--etat).

    .PARAMETER DossierParametrage
        Dossier qui contient les fichiers de paramétrage.

    .PARAMETER Config
        Fichier de configuration de l'interface (Gestion-Copie.config.psd1).

    .PARAMETER SansAffichage
        Construit la fenêtre sans l'afficher et la renvoie (tests et copies d'écran).

    .EXAMPLE
        Start-CopieGui -DossierParametrage D:\Parametrage -Config .\Gestion-Copie.config.psd1
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $DossierParametrage,
        [Parameter(Mandatory)] [string] $Config,
        [switch] $SansAffichage,
        [string[]] $GroupeUtilisateur
    )

    $configuration = Get-CopieConfig -Chemin $Config
    if ($PSBoundParameters.ContainsKey('GroupeUtilisateur')) { $profil = Get-CopieProfilAcces -Config $configuration -Groupe $GroupeUtilisateur }
    else { $profil = Get-CopieProfilAcces -Config $configuration }
    $utilisateur = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $dossier = (Resolve-Path -LiteralPath $DossierParametrage -ErrorAction Stop).ProviderPath

    $fenetre = Import-CopieXaml -Nom 'MainWindow'
    $ctx = @{
        Config = $configuration; Profil = $profil; Utilisateur = $utilisateur; Dossier = $dossier
        Fenetre = $fenetre; LogBox = $fenetre.FindName('LogBox'); PanneJournal = $false
    }
    $tabs = $fenetre.FindName('Tabs')
    $statut = $fenetre.FindName('StatusText')

    $fenetre.FindName('SubTitleText').Text = ('Dossier de paramétrage : ' + $dossier)
    $fenetre.FindName('UserText').Text = $utilisateur
    $badge = $fenetre.FindName('ModeBadge')
    $texteBadge = $fenetre.FindName('ModeText')
    if ($profil -eq 'Admin') {
        $texteBadge.Text = 'ADMINISTRATEUR'
        $badge.Background = [System.Windows.Media.BrushConverter]::new().ConvertFromString('#2E7D32')
    }
    else {
        $texteBadge.Text = 'LECTURE SEULE'
        $badge.Background = [System.Windows.Media.BrushConverter]::new().ConvertFromString('#C77700')
    }
    $fenetre.FindName('LogPathText').Text = $(if ($configuration.Journal.Dossier) { $configuration.Journal.Dossier } else { 'journal fichier désactivé' })

    $Script:Session = @{ Contexte = $ctx; Tabs = $tabs; Statut = $statut; Dossier = $dossier }
    $fenetre.FindName('BtnRefresh').Add_Click({ Update-CopieEnvironnements })
    $fenetre.FindName('BtnLogClear').Add_Click({ $Script:Session.Contexte.LogBox.Document.Blocks.Clear() })

    Write-CopieJournal -Contexte $ctx -Evenement 'ouverture' -Message ('Ouverture par {0} : profil {1}, dossier {2}' -f $utilisateur, $profil, $dossier) `
        -Donnees @{ profil = $profil; dossier = $dossier }
    Update-CopieEnvironnements

    if ($SansAffichage) { return $fenetre }
    $null = $fenetre.ShowDialog()
}
