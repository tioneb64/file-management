# Journaux d'une règle : lire le contenu du dernier journal (ou d'un journal plus ancien) sans ouvrir le JSON brut.
# Ouverte à tous les comptes : le moteur ne fait que lire le dossier des journaux (--journaux-regle).

function Show-CopieJournaux {
    <#
    .SYNOPSIS
        Bouton « Journaux… » : lit la liste des journaux de la règle choisie (en arrière-plan) puis ouvre la fenêtre.
    .PARAMETER Vue
        Vue d'un environnement.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)
    $ctx = $Vue.Contexte
    $choisie = $Vue.Grille.SelectedItem
    if ($null -eq $choisie -or $Vue.Occupe) { return }
    Set-CopieOccupe -Vue $Vue -Occupe $true -Libelle ('Lecture des journaux de la règle {0}' -f $choisie.Id)
    $null = Start-CopieTache -Config $ctx.Config -Fichier $Vue.Env.Fichier -Argument @('--journaux-regle', $choisie.Id) `
        -SurFin { param($t) Complete-CopieJournaux -Tache $t } -Donnees @{ Vue = $Vue; Contexte = $ctx; Regle = $choisie.Id }
}

function Complete-CopieJournaux {
    <#
    .SYNOPSIS
        Fin de la lecture de la liste des journaux : message si rien à lire, sinon fenêtre des journaux.
    .PARAMETER Tache
        Tâche terminée (Donnees : Vue, Contexte, Regle).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Tache)
    $vue = $Tache.Donnees.Vue
    $ctx = $Tache.Donnees.Contexte
    $regle = $Tache.Donnees.Regle
    $reponse = $Tache.Reponse
    Set-CopieOccupe -Vue $vue -Occupe $false
    $lisible = ($null -ne $reponse.Json -and $null -ne $reponse.Json.PSObject.Properties['journaux'])
    Write-CopieJournal -Contexte $ctx -Niveau $(if ($lisible) { 'INFO' } else { 'WARNING' }) -Evenement 'journaux_regle' `
        -Message ('Lecture des journaux de {0} dans {1} (compte {2}) : code {3}' -f $regle, $vue.Env.Nom, $ctx.Utilisateur, $reponse.Code) `
        -Donnees @{ environnement = $vue.Env.Nom; regle = $regle; code = $reponse.Code }
    if (-not $lisible) {
        [void][System.Windows.MessageBox]::Show($ctx.Fenetre, ('Les journaux de la règle ne peuvent pas être lus : ' + (Get-CopieTexteReponse -Reponse $reponse)), 'Journaux', 'OK', 'Warning')
        return
    }
    $lignes = @(ConvertTo-CopieLignesJournaux -Json $reponse.Json)
    if ($lignes.Count -eq 0) {
        $dossier = "$(Get-CopieValeur $reponse.Json 'dossier' '')"
        [void][System.Windows.MessageBox]::Show($ctx.Fenetre, ('Aucun journal pour la règle « {0} »{1}.' -f $regle, $(if ($dossier) { ' dans ' + $dossier } else { '' })), 'Journaux', 'OK', 'Information')
        return
    }
    Show-CopieFenetreJournaux -Vue $vue -Regle $regle -Ligne $lignes -Json $reponse.Json
}

function Show-CopieFenetreJournaux {
    <#
    .SYNOPSIS
        Fenêtre des journaux : fichiers par jour à gauche, événements du fichier choisi à droite, détail de l'événement en bas.
    .PARAMETER Vue
        Vue d'un environnement.
    .PARAMETER Regle
        Identifiant de la règle.
    .PARAMETER Ligne
        Lignes de ConvertTo-CopieLignesJournaux.
    .PARAMETER Json
        Réponse du moteur (liste des journaux).
    .PARAMETER SansAffichage
        Construit la fenêtre sans l'ouvrir (tests) : la fenêtre est renvoyée.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [hashtable] $Vue, [Parameter(Mandatory)] [string] $Regle,
        [Parameter(Mandatory)] [object[]] $Ligne, [Parameter(Mandatory)] $Json, [switch] $SansAffichage
    )
    $ctx = $Vue.Contexte
    $fenetre = Import-CopieXaml -Nom 'Dialog.Journaux'
    if ($null -ne $ctx.Fenetre) { $fenetre.Owner = $ctx.Fenetre }
    $fenetre.Title = 'Journaux de la règle « {0} » : {1}' -f $Regle, $Vue.Env.Nom
    $fenetre.Tag = @{ Vue = $Vue; Regle = $Regle; Evenements = @(); Reponse = $null; Chargement = $false }
    $resume = '{0} journal(aux) dans {1}.' -f $Ligne.Count, (Get-CopieValeur $Json 'dossier' '')
    if ([bool](Get-CopieValeur $Json 'tronque' $false)) { $resume += (' Seuls les {0} plus récents sont listés ({1} fichiers au total ; les plus anciens sont purgés selon la rétention).' -f $Ligne.Count, (Get-CopieValeur $Json 'total_fichiers' $Ligne.Count)) }
    $resume += ' Choisissez un journal pour lire ses événements.'
    $fenetre.FindName('Resume').Text = $resume
    $grille = $fenetre.FindName('Journaux')
    $grille.ItemsSource = $Ligne
    $grille.Add_SelectionChanged({ param($s) Read-CopieJournalChoisi -Fenetre ([System.Windows.Window]::GetWindow($s)) })
    $fenetre.FindName('Executions').Add_SelectionChanged({ param($s) Update-CopieJournauxAffichage -Fenetre ([System.Windows.Window]::GetWindow($s)) })
    $fenetre.FindName('Anomalies').Add_Click({ param($s) Update-CopieJournauxAffichage -Fenetre ([System.Windows.Window]::GetWindow($s)) })
    $fenetre.FindName('Evenements').Add_SelectionChanged({ param($s) Update-CopieJournalDetail -Fenetre ([System.Windows.Window]::GetWindow($s)) })
    $fenetre.FindName('BtnCopier').Add_Click({
            param($s)
            $f = [System.Windows.Window]::GetWindow($s)
            $texte = (@($f.FindName('Detail').ItemsSource) | ForEach-Object { '{0} : {1}' -f $_.Rubrique, $_.Valeur }) -join "`r`n"
            if ($texte) { try { [System.Windows.Clipboard]::SetText($texte) } catch { Write-Verbose ('Presse-papiers indisponible : ' + $_.Exception.Message) } }
        })
    $grille.SelectedIndex = 0                                  # le journal le plus récent
    if ($SansAffichage) { return $fenetre }
    $null = $fenetre.ShowDialog()
}

function Read-CopieJournalChoisi {
    <#
    .SYNOPSIS
        Lit le contenu du journal choisi à gauche (appel court du moteur) et remplit les choix d'exécution et les événements.
    .PARAMETER Fenetre
        Fenêtre des journaux.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [System.Windows.Window] $Fenetre)
    $etat = $Fenetre.Tag
    $choisi = $Fenetre.FindName('Journaux').SelectedItem
    $combo = $Fenetre.FindName('Executions')
    $combo.ItemsSource = $null
    $Fenetre.FindName('Evenements').ItemsSource = $null
    $Fenetre.FindName('Detail').ItemsSource = $null
    $Fenetre.FindName('ResumeJournal').Text = ''
    $etat.Evenements = @()
    if ($null -eq $choisi) { return }
    $vue = $etat.Vue
    $ctx = $vue.Contexte
    $Fenetre.Cursor = [System.Windows.Input.Cursors]::Wait
    try { $reponse = Invoke-CopieMoteur -Config $ctx.Config -Fichier $vue.Env.Fichier -Argument @('--journaux-regle', $etat.Regle, '--journal', $choisi.Nom) }
    finally { $Fenetre.Cursor = $null }
    if ($null -eq $reponse.Json -or $null -eq $reponse.Json.PSObject.Properties['evenements']) {
        $Fenetre.FindName('ResumeJournal').Text = 'Ce journal ne peut pas être lu : ' + (Get-CopieTexteReponse -Reponse $reponse)
        return
    }
    $etat.Reponse = $reponse.Json
    $etat.Evenements = @(ConvertTo-CopieLignesEvenements -Json $reponse.Json)
    $choix = @(ConvertTo-CopieChoixExecutions -Json $reponse.Json)
    $combo.ItemsSource = $choix
    # Par défaut : la dernière exécution (le plus utile pour comprendre un échec), sinon tout le fichier.
    $combo.SelectedIndex = $(if ($choix.Count -gt 1) { 1 } else { 0 })
    Update-CopieJournauxAffichage -Fenetre $Fenetre
}

function Update-CopieJournauxAffichage {
    <#
    .SYNOPSIS
        Applique les filtres de la fenêtre (exécution choisie, avertissements et erreurs seulement) aux événements du journal lu.
    .PARAMETER Fenetre
        Fenêtre des journaux.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [System.Windows.Window] $Fenetre)
    $etat = $Fenetre.Tag
    if ($null -eq $etat.Reponse) { return }
    $choixExecution = $Fenetre.FindName('Executions').SelectedItem
    $groupe = $null
    if ($null -ne $choixExecution) { $groupe = $choixExecution.Cle }
    $anomalies = [bool]$Fenetre.FindName('Anomalies').IsChecked
    $affiches = @(Select-CopieEvenementsJournal -Ligne $etat.Evenements -Groupe $groupe -AnomaliesSeulement:$anomalies)
    $grille = $Fenetre.FindName('Evenements')
    $grille.ItemsSource = $affiches
    $Fenetre.FindName('ResumeJournal').Text = (Get-CopieResumeJournal -Json $etat.Reponse -Ligne $etat.Evenements) + $(if ($affiches.Count -ne @($etat.Evenements).Count) { (' Affichés : {0}.' -f $affiches.Count) } else { '' })
    if ($affiches.Count -gt 0) {
        # On se place sur le premier avertissement ou la première erreur s'il y en a, sinon sur le dernier événement.
        $cible = @($affiches | Where-Object { $_.Gravite -ne 'Normal' } | Select-Object -First 1)
        $ligne = $(if ($cible.Count -gt 0) { $cible[0] } else { $affiches[$affiches.Count - 1] })
        $grille.SelectedItem = $ligne
        $grille.ScrollIntoView($ligne)
    }
    else { Update-CopieJournalDetail -Fenetre $Fenetre }
}

function Update-CopieJournalDetail {
    <#
    .SYNOPSIS
        Affiche, en bas de la fenêtre, le détail lisible (rubrique : valeur) de l'événement sélectionné.
    .PARAMETER Fenetre
        Fenêtre des journaux.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [System.Windows.Window] $Fenetre)
    $choisi = $Fenetre.FindName('Evenements').SelectedItem
    $detail = $Fenetre.FindName('Detail')
    if ($null -eq $choisi) {
        $detail.ItemsSource = $null
        $Fenetre.FindName('BtnCopier').IsEnabled = $false
        return
    }
    $detail.ItemsSource = @(Get-CopieDetailEvenement -Evenement $choisi.Brut)
    $Fenetre.FindName('BtnCopier').IsEnabled = $true
}
