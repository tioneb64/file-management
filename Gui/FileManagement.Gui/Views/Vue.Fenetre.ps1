function Update-CopieEnvironnements {
    <#
    .SYNOPSIS
        Relit le dossier de paramétrage et reconstruit les onglets (un par environnement).

    .DESCRIPTION
        Utilise la session ouverte par Start-CopieGui ($Script:Session). L'onglet sélectionné est conservé
        quand l'environnement existe toujours. Pas d'interrogation automatique : ce rechargement se fait à
        l'ouverture et sur le bouton Actualiser (docs/04-frontend.md §6).
    #>
    [CmdletBinding()]
    param([string] $Selection = '')

    $session = $Script:Session
    $ctx = $session.Contexte
    $tabs = $session.Tabs
    $ctx.Fenetre.Cursor = [System.Windows.Input.Cursors]::Wait
    try {
        $courant = $null
        $surOutils = ($tabs.SelectedItem -and $tabs.SelectedItem.Tag -and $tabs.SelectedItem.Tag.Type -eq 'Outils')
        if ($tabs.SelectedItem -and $tabs.SelectedItem.Tag -and -not $surOutils) { $courant = $tabs.SelectedItem.Tag.Env.Nom }
        if ($Selection) { $courant = $Selection; $surOutils = $false }
        $tabs.Items.Clear()
        $Script:Vues.Clear()
        $session.Statut.Text = 'Lecture du dossier de paramétrage...'
        try { $environnements = @(Get-CopieEnvironnement -Dossier $session.Dossier -Config $ctx.Config) }
        catch {
            Write-CopieJournal -Contexte $ctx -Niveau 'ERREUR' -Evenement 'lecture_dossier' -Message $_.Exception.Message
            $session.Statut.Text = $_.Exception.Message
            Show-CopieEtatVide -Titre 'Le dossier de paramétrage ne peut pas être lu' -Texte $_.Exception.Message -Creation $false
            return
        }
        foreach ($env in $environnements) {
            $null = $tabs.Items.Add((New-CopieVueEnvironnement -Contexte $ctx -Environnement $env))
        }
        # L'onglet « Outils » (réglage du moteur, commun à tous les environnements) suit les environnements.
        if ($environnements.Count -gt 0) { $null = $tabs.Items.Add((New-CopieVueOutils -Contexte $ctx)) }
        for ($i = 0; $i -lt $tabs.Items.Count; $i++) {
            $vueOnglet = $tabs.Items[$i].Tag
            if ($surOutils -and $vueOnglet.Type -eq 'Outils') { $tabs.SelectedIndex = $i }
            elseif (-not $surOutils -and $vueOnglet.Type -ne 'Outils' -and $vueOnglet.Env.Nom -eq $courant) { $tabs.SelectedIndex = $i }
        }
        if ($tabs.SelectedIndex -lt 0 -and $tabs.Items.Count -gt 0) { $tabs.SelectedIndex = 0 }
        if ($environnements.Count -eq 0) {
            if ($ctx.Profil -eq 'Admin') {
                Show-CopieEtatVide -Titre 'Aucun environnement' -Creation $true -Texte ("Le dossier {0} ne contient aucun fichier de paramétrage ({1}).`n`nUn environnement = un fichier de paramétrage + sa base. Créez le premier : l'outil écrit le fichier, le fait vérifier par le moteur et crée la base." -f $session.Dossier, $ctx.Config.Parametrage.Filtre)
            }
            else {
                Show-CopieEtatVide -Titre 'Aucun environnement' -Creation $false -Texte ("Le dossier {0} ne contient aucun fichier de paramétrage ({1}).`n`nVotre compte n'est pas administrateur : demandez à un administrateur (groupe : {2}) de créer le premier environnement." -f $session.Dossier, $ctx.Config.Parametrage.Filtre, ($ctx.Config.Acces.GroupesAdmin -join ', '))
            }
            Write-CopieJournal -Contexte $ctx -Niveau 'WARNING' -Evenement 'lecture_dossier' `
                -Message ('Aucun fichier {0} dans {1}' -f $ctx.Config.Parametrage.Filtre, $session.Dossier)
        }
        if ($environnements.Count -gt 0) { Hide-CopieEtatVide }
        $session.Statut.Text = ('{0} environnement(s) chargé(s).' -f $environnements.Count)
    }
    finally {
        $ctx.Fenetre.Cursor = $null
        Update-CopieBarreEnvironnements
    }
}

function Show-CopieEtatVide {
    <#
    .SYNOPSIS
        Remplace la zone des onglets par une explication (aucun environnement, dossier illisible) et, si permis, un bouton de création.
    .PARAMETER Titre
        Titre de l'explication.
    .PARAMETER Texte
        Explication.
    .PARAMETER Creation
        Montre le bouton « Créer un premier environnement » (administrateurs).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Titre, [Parameter(Mandatory)] [string] $Texte, [Parameter(Mandatory)] [bool] $Creation)
    $s = $Script:Session
    $s.EtatVideTitre.Text = $Titre
    $s.EtatVideTexte.Text = $Texte
    $s.BtnEtatVideCreer.Visibility = $(if ($Creation) { 'Visible' } else { 'Collapsed' })
    $s.EtatVide.Visibility = 'Visible'
}

function Hide-CopieEtatVide {
    <#
    .SYNOPSIS
        Retire l'explication « aucun environnement » : les onglets sont visibles.
    #>
    [CmdletBinding()]
    param()
    $Script:Session.EtatVide.Visibility = 'Collapsed'
}
