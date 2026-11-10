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
    param()

    $session = $Script:Session
    $ctx = $session.Contexte
    $tabs = $session.Tabs
    $ctx.Fenetre.Cursor = [System.Windows.Input.Cursors]::Wait
    try {
        $courant = $null
        if ($tabs.SelectedItem -and $tabs.SelectedItem.Tag) { $courant = $tabs.SelectedItem.Tag.Env.Nom }
        $tabs.Items.Clear()
        $Script:Vues.Clear()
        $session.Statut.Text = 'Lecture du dossier de paramétrage...'
        try { $environnements = @(Get-CopieEnvironnement -Dossier $session.Dossier -Config $ctx.Config) }
        catch {
            Write-CopieJournal -Contexte $ctx -Niveau 'ERREUR' -Evenement 'lecture_dossier' -Message $_.Exception.Message
            $session.Statut.Text = $_.Exception.Message
            return
        }
        foreach ($env in $environnements) {
            $null = $tabs.Items.Add((New-CopieVueEnvironnement -Contexte $ctx -Environnement $env))
        }
        for ($i = 0; $i -lt $tabs.Items.Count; $i++) {
            if ($tabs.Items[$i].Tag.Env.Nom -eq $courant) { $tabs.SelectedIndex = $i }
        }
        if ($tabs.SelectedIndex -lt 0 -and $tabs.Items.Count -gt 0) { $tabs.SelectedIndex = 0 }
        if ($environnements.Count -eq 0) {
            Write-CopieJournal -Contexte $ctx -Niveau 'WARNING' -Evenement 'lecture_dossier' `
                -Message ('Aucun fichier {0} dans {1}' -f $ctx.Config.Parametrage.Filtre, $session.Dossier)
        }
        $session.Statut.Text = ('{0} environnement(s) chargé(s).' -f $environnements.Count)
    }
    finally { $ctx.Fenetre.Cursor = $null }
}
