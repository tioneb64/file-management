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

    .PARAMETER ConfirmerCreationDossier
        Bloc appelé avec la question quand le dossier de paramétrage n'existe pas et que l'utilisateur est administrateur
        (tests). Par défaut : une fenêtre Oui / Non. Un dossier absent n'est jamais créé sans accord.

    .PARAMETER ConfirmerMoteurLocal
        Bloc appelé avec la question quand, en mode Local, Python ou le dossier du moteur configurés n'existent pas et
        que d'autres ont été trouvés (tests). Par défaut : une fenêtre Oui / Non.

    .EXAMPLE
        Start-CopieGui -DossierParametrage D:\Parametrage -Config .\Gestion-Copie.config.psd1
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $DossierParametrage,
        [Parameter(Mandatory)] [string] $Config,
        [switch] $SansAffichage,
        [string[]] $GroupeUtilisateur,
        [scriptblock] $ConfirmerCreationDossier,
        [scriptblock] $ConfirmerMoteurLocal
    )

    $configuration = Get-CopieConfig -Chemin $Config
    # TEMPORAIRE (poste de développement sans accès à l'AD) : la vérification d'appartenance au groupe
    # Acces.GroupesAdmin est désactivée, tout utilisateur est Admin. A RÉACTIVER avant toute mise en
    # production : supprimer la ligne `$profil = 'Admin'` et décommenter le bloc ci-dessous (voir CHANGELOG).
    # if ($PSBoundParameters.ContainsKey('GroupeUtilisateur')) { $profil = Get-CopieProfilAcces -Config $configuration -Groupe $GroupeUtilisateur }
    # else { $profil = Get-CopieProfilAcces -Config $configuration }
    $profil = 'Admin'
    $null = $GroupeUtilisateur   # inutilisé tant que la vérification est désactivée
    $utilisateur = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    if ($null -eq $ConfirmerCreationDossier) {
        $ConfirmerCreationDossier = {
            param($question)
            Add-Type -AssemblyName PresentationFramework
            [System.Windows.MessageBox]::Show($question, 'Dossier de paramétrage', 'YesNo', 'Question', 'No') -eq [System.Windows.MessageBoxResult]::Yes
        }
    }
    if ($null -eq $ConfirmerMoteurLocal) {
        $ConfirmerMoteurLocal = {
            param($question)
            Add-Type -AssemblyName PresentationFramework
            [System.Windows.MessageBox]::Show($question, 'Moteur de copie', 'YesNo', 'Question', 'Yes') -eq [System.Windows.MessageBoxResult]::Yes
        }
    }
    $moteurLocal = Resolve-CopieMoteurLocal -Config $configuration -Confirmer $ConfirmerMoteurLocal
    if (-not $moteurLocal.Ok -and -not $SansAffichage) {
        Add-Type -AssemblyName PresentationFramework
        [void][System.Windows.MessageBox]::Show(($moteurLocal.Message + "`n`nL'interface s'ouvre, mais aucune action qui passe par le moteur ne fonctionnera."), 'Moteur de copie', 'OK', 'Warning')
    }
    $dossier = Resolve-CopieDossierParametrage -Chemin $DossierParametrage -Profil $profil -GroupeAdmin $configuration.Acces.GroupesAdmin -Confirmer $ConfirmerCreationDossier
    if ($null -eq $dossier) { return }       # création refusée : rien à ouvrir

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

    $Script:Session = @{
        Contexte = $ctx; Tabs = $tabs; Statut = $statut; Dossier = $dossier
        Barre = $fenetre.FindName('BarreEnvironnements'); BtnNouveau = $fenetre.FindName('BtnEnvNouveau'); BtnModifier = $fenetre.FindName('BtnEnvModifier')
        BtnBase = $fenetre.FindName('BtnEnvBase'); BtnCopier = $fenetre.FindName('BtnEnvCopier'); BtnSupprimer = $fenetre.FindName('BtnEnvSupprimer')
        EtatVide = $fenetre.FindName('EtatVide'); EtatVideTitre = $fenetre.FindName('EtatVideTitre'); EtatVideTexte = $fenetre.FindName('EtatVideTexte')
        BtnEtatVideCreer = $fenetre.FindName('BtnEtatVideCreer')
    }
    $Script:Session.BtnNouveau.Add_Click({ Invoke-CopieNouvelEnvironnement -Contexte $Script:Session.Contexte })
    $Script:Session.BtnEtatVideCreer.Add_Click({ Invoke-CopieNouvelEnvironnement -Contexte $Script:Session.Contexte })
    $Script:Session.BtnModifier.Add_Click({ $t = $Script:Session.Tabs.SelectedItem; if ($t -and $t.Tag) { Invoke-CopieModifierEnvironnement -Vue $t.Tag } })
    $Script:Session.BtnCopier.Add_Click({ $t = $Script:Session.Tabs.SelectedItem; if ($t -and $t.Tag) { Invoke-CopieCopierEnvironnement -Vue $t.Tag } })
    $Script:Session.BtnBase.Add_Click({ $t = $Script:Session.Tabs.SelectedItem; if ($t -and $t.Tag) { Invoke-CopieCreerBase -Vue $t.Tag } })
    $Script:Session.BtnSupprimer.Add_Click({ $t = $Script:Session.Tabs.SelectedItem; if ($t -and $t.Tag) { Invoke-CopieSupprimerEnvironnement -Vue $t.Tag } })
    $tabs.Add_SelectionChanged({ Update-CopieBarreEnvironnements })
    $fenetre.FindName('BtnRefresh').Add_Click({ Update-CopieEnvironnements })
    $fenetre.FindName('BtnLogClear').Add_Click({ $Script:Session.Contexte.LogBox.Document.Blocks.Clear() })

    Write-CopieJournal -Contexte $ctx -Evenement 'ouverture' -Message ('Ouverture par {0} : profil {1}, dossier {2}' -f $utilisateur, $profil, $dossier) `
        -Donnees @{ profil = $profil; dossier = $dossier }
    Update-CopieEnvironnements

    # Dossier vide : un administrateur se voit proposer tout de suite de créer le premier environnement.
    if ($profil -eq 'Admin' -and $tabs.Items.Count -eq 0 -and $Script:Session.BtnEtatVideCreer.Visibility -eq 'Visible' -and -not $SansAffichage) {
        $Script:PremiereProposition = $false
        $fenetre.Add_ContentRendered({
                if (-not $Script:PremiereProposition) {
                    $Script:PremiereProposition = $true
                    if ($Script:Session.Tabs.Items.Count -eq 0) { Invoke-CopieNouvelEnvironnement -Contexte $Script:Session.Contexte }
                }
            })
    }

    if ($SansAffichage) { return $fenetre }
    $null = $fenetre.ShowDialog()
}
