# Vue d'un environnement. Les gestionnaires d'événements WPF s'exécutent après le retour de la fonction
# qui les a créés : ils ne peuvent pas compter sur les variables locales (et GetNewClosure() les couperait
# des fonctions du module). Chaque vue est donc rangée dans $Script:Vues, retrouvée par l'étiquette (Tag)
# du contrôle qui déclenche l'événement.
$Script:Vues = @{}

function Show-CopieDiagnostics {
    <#
    .SYNOPSIS
        Fenêtre qui affiche les refus, avertissements et informations d'une vérification du moteur.
    .PARAMETER Contexte
        Contexte de la session (Fenetre = fenêtre propriétaire).
    .PARAMETER Reponse
        Réponse du moteur à --verifier (Copie.ReponseMoteur).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [hashtable] $Contexte,
        [Parameter(Mandatory)] [pscustomobject] $Reponse
    )
    $fenetre = Import-CopieXaml -Nom 'Dialog.Diagnostics'
    if ($null -ne $Contexte.Fenetre) { $fenetre.Owner = $Contexte.Fenetre }
    $lignes = New-Object System.Collections.Generic.List[object]
    $json = $Reponse.Json
    foreach ($def in @(@('refus', 'Refus', '#C0392B'), @('avertissements', 'Avertissement', '#C77700'), @('informations', 'Information', '#1F6FB2'))) {
        foreach ($d in @(Get-CopieValeur $json $def[0] @())) {
            $ligne = Get-CopieValeur $d 'ligne'
            $lignes.Add([pscustomobject]@{
                    Gravite = $def[1]; Couleur = $def[2]; Code = "$(Get-CopieValeur $d 'code' '')"
                    Regle = "$(Get-CopieValeur $d 'regle' '')"; Ligne = $(if ($null -ne $ligne) { "$ligne" } else { '' })
                    Message = "$(Get-CopieValeur $d 'message' '')"
                })
        }
    }
    $nbRefus = @(Get-CopieValeur $json 'refus' @()).Count
    $nbAvert = @(Get-CopieValeur $json 'avertissements' @()).Count
    $fenetre.FindName('Grille').ItemsSource = $lignes.ToArray()
    $resume = $fenetre.FindName('Resume')
    if ($nbRefus -gt 0) { $resume.Text = ('{0} refus, {1} avertissement(s) : ce paramétrage ne serait pas accepté par le moteur.' -f $nbRefus, $nbAvert) }
    elseif ($nbAvert -gt 0) { $resume.Text = ('Paramétrage valide, avec {0} avertissement(s).' -f $nbAvert) }
    else { $resume.Text = 'Paramétrage valide, sans avertissement.' }
    $null = $fenetre.ShowDialog()
}

function Set-CopieFiltres {
    <#
    .SYNOPSIS
        Applique les filtres (recherche, statut, mode, actives) à la grille des règles.
    .PARAMETER Vue
        Vue d'un environnement (New-CopieVueEnvironnement).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)
    if ($Vue.Chargement) { return }
    $texte = $Vue.Recherche.Text.Trim().ToLowerInvariant()
    $statut = "$($Vue.FiltreStatut.SelectedItem)"
    $mode = "$($Vue.FiltreMode.SelectedItem)"
    $actives = [bool]$Vue.Actives.IsChecked
    $visibles = @($Vue.Lignes | Where-Object {
            ($statut -in '', 'Tous' -or $_.Statut -eq $statut) -and
            ($mode -in '', 'Tous' -or $_.Mode -eq $mode) -and
            (-not $actives -or $_.Actif -eq 'Oui') -and
            (-not $texte -or ($_.Id + ' ' + $_.Description + ' ' + $_.Chemins).ToLowerInvariant().Contains($texte))
        })
    $Vue.Grille.ItemsSource = $visibles
    $Vue.Compteur.Text = ('{0} règle(s) affichée(s) sur {1}' -f $visibles.Count, $Vue.Lignes.Count)
}

function Select-CopieRegle {
    <#
    .SYNOPSIS
        Affiche le détail et l'état de la règle sélectionnée dans la grille.
    .PARAMETER Vue
        Vue d'un environnement.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)
    $ligne = $Vue.Grille.SelectedItem
    if ($null -ne $Vue.Ajouter) { Update-CopieBoutons -Vue $Vue }
    if ($null -eq $ligne) { $Vue.Detail.ItemsSource = $null; $Vue.Etat.ItemsSource = $null; return }
    $Vue.Detail.ItemsSource = ConvertTo-CopieGroupeRegle -Regle $ligne.Regle
    $Vue.Etat.ItemsSource = ConvertTo-CopieGroupeEtat -Etat $ligne.Etat
}

function Update-CopieVue {
    <#
    .SYNOPSIS
        Recharge l'état des règles d'un environnement (appel du moteur : --etat) et remplit la grille.

    .DESCRIPTION
        Si la base n'est pas initialisée ou si le moteur est injoignable, la liste s'affiche quand même, à
        partir du fichier, avec un message (jamais d'écran vide).

    .PARAMETER Vue
        Vue d'un environnement.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)

    $Vue.Chargement = $true
    try {
        $ctx = $Vue.Contexte
        $parametrage = $Vue.Env.Parametrage
        $etats = @{}
        $messagesEtat = New-Object System.Collections.Generic.List[string]
        $lisible = ($null -ne $parametrage.Entete -and $parametrage.Erreurs.Count -eq 0)
        if ($lisible) {
            $reponse = Invoke-CopieMoteur -Config $ctx.Config -Fichier $Vue.Env.Fichier -Argument @('--etat')
            $niveau = $(if ($reponse.Reussi) { 'INFO' } else { 'WARNING' })
            Write-CopieJournal -Contexte $ctx -Niveau $niveau -Evenement 'moteur_appel' `
                -Message ('{0} -> code {1} en {2} ms' -f $reponse.Commande, $reponse.Code, $reponse.DureeMs) `
                -Donnees @{ environnement = $Vue.Env.Nom; code = $reponse.Code; duree_ms = $reponse.DureeMs }
            if ($reponse.Reussi) {
                foreach ($r in @(Get-CopieValeur $reponse.Json 'regles' @())) { $etats[("$($r.id)").ToLowerInvariant()] = $r }
                $orphelines = @(Get-CopieValeur $reponse.Json 'orphelines' @())
                if ($orphelines.Count -gt 0) { $messagesEtat.Add(('Règles connues de la base mais absentes du fichier : ' + ($orphelines -join ', ') + '.')) }
            }
            else {
                $detail = $(if ($reponse.Json -and $reponse.Json.message) { $reponse.Json.message } else { $reponse.Erreur })
                $messagesEtat.Add(('État indisponible : {0}' -f $detail))
            }
        }
        else { $messagesEtat.Add('État indisponible : le fichier n''est pas lisible.') }

        $lignes = foreach ($regle in $parametrage.Regles) {
            $id = ("$(Get-CopieValeur $regle 'id' '')").ToLowerInvariant()
            ConvertTo-CopieLigneRegle -Regle $regle -Etat $etats[$id]
        }
        $Vue.Lignes = @($lignes)

        $tiret = [string][char]0x2014
        $statuts = @('Tous') + @($Vue.Lignes | ForEach-Object { $_.Statut } | Where-Object { $_ -ne $tiret } | Sort-Object -Unique)
        $precedent = "$($Vue.FiltreStatut.SelectedItem)"
        $Vue.FiltreStatut.Items.Clear()
        foreach ($s in $statuts) { $null = $Vue.FiltreStatut.Items.Add($s) }
        $position = [array]::IndexOf($statuts, $precedent)
        $Vue.FiltreStatut.SelectedIndex = $(if ($position -ge 0) { $position } else { 0 })

        $tous = New-Object System.Collections.Generic.List[string]
        foreach ($m in $Vue.Messages) { $tous.Add($m) }
        foreach ($m in $messagesEtat) { $tous.Add($m) }
        $Vue.BandeauTexte.Text = ($tous -join "`n")
        $Vue.Bandeau.Visibility = $(if ($tous.Count -gt 0) { 'Visible' } else { 'Collapsed' })
    }
    finally { $Vue.Chargement = $false }
    Set-CopieFiltres -Vue $Vue
    Update-CopieGraphe -Vue $Vue
    $Vue.Detail.ItemsSource = $null
    $Vue.Etat.ItemsSource = $null
}

function Invoke-CopieVerification {
    <#
    .SYNOPSIS
        Vérifie le paramétrage d'un environnement avec le moteur (--verifier) et affiche le résultat.

    .DESCRIPTION
        Contrôles de syntaxe et d'accès. Les accès sont contrôlés avec le compte qui exécute le moteur :
        le compte de l'administrateur (mode Local, ou Distant sans JEA) ou celui du point d'accès JEA.
        La vérification est tracée au journal (compte, résultat).

    .PARAMETER Vue
        Vue d'un environnement.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)

    $ctx = $Vue.Contexte
    if ($Vue.Occupe) { return }
    Set-CopieOccupe -Vue $Vue -Occupe $true -Libelle ('Vérification de {0}' -f $Vue.Env.Nom)
    $null = Start-CopieTache -Config $ctx.Config -Fichier $Vue.Env.Fichier `
        -Argument @('--verifier', '--periode-declencheur-sec', "$($ctx.Config.Parametrage.PeriodeDeclencheurSec)") `
        -SurFin { param($t) Complete-CopieVerification -Tache $t } -Donnees @{ Vue = $Vue; Contexte = $ctx }
}

function Complete-CopieVerification {
    <#
    .SYNOPSIS
        Fin de la vérification en arrière-plan : journal et affichage du résultat.
    .PARAMETER Tache
        Tâche terminée (Donnees : Vue, Contexte).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Tache)
    $Vue = $Tache.Donnees.Vue
    $ctx = $Tache.Donnees.Contexte
    $reponse = $Tache.Reponse
    Set-CopieOccupe -Vue $Vue -Occupe $false
    if ($null -eq $reponse.Json) {
        Write-CopieJournal -Contexte $ctx -Niveau 'ERREUR' -Evenement 'verification' -Message ('Vérification impossible : ' + $reponse.Erreur)
        [void][System.Windows.MessageBox]::Show($ctx.Fenetre, ('Vérification impossible : ' + $reponse.Erreur), 'Vérification', 'OK', 'Error')
        return
    }
    $niveau = switch ($reponse.Code) { 0 { 'INFO' } 4 { 'WARNING' } default { 'ERREUR' } }
    Write-CopieJournal -Contexte $ctx -Niveau $niveau -Evenement 'verification' `
        -Message ('Vérification de {0} (compte {1}) : code {2}' -f $Vue.Env.Nom, $ctx.Utilisateur, $reponse.Code) `
        -Donnees @{ environnement = $Vue.Env.Nom; code = $reponse.Code }
    Show-CopieDiagnostics -Contexte $ctx -Reponse $reponse
}

function New-CopieVueEnvironnement {
    <#
    .SYNOPSIS
        Crée l'onglet d'un environnement : règles, détail, état, vérification.

    .DESCRIPTION
        L'onglet est en lecture seule si l'environnement l'est (fichier non pris en charge, doublon) ou si
        l'utilisateur n'est pas administrateur : les boutons d'édition (étape B) sont alors masqués.

    .PARAMETER Contexte
        Contexte de la session.

    .PARAMETER Environnement
        Environnement (Get-CopieEnvironnement).

    .OUTPUTS
        [System.Windows.Controls.TabItem] ; sa propriété Tag contient la vue.
    #>
    [CmdletBinding()]
    [OutputType([System.Windows.Controls.TabItem])]
    param(
        [Parameter(Mandatory)] [hashtable] $Contexte,
        [Parameter(Mandatory)] [pscustomobject] $Environnement
    )

    $tab = Import-CopieXaml -Nom 'Environnement'
    $cle = [guid]::NewGuid().ToString()
    $vue = @{
        Cle = $cle; Contexte = $Contexte; Env = $Environnement; Lignes = @(); Tab = $tab; Chargement = $false
        Grille = $tab.FindName('GrilleRegles'); Detail = $tab.FindName('Detail'); Etat = $tab.FindName('Etat')
        Compteur = $tab.FindName('Compteur'); Recherche = $tab.FindName('Recherche')
        FiltreStatut = $tab.FindName('FiltreStatut'); FiltreMode = $tab.FindName('FiltreMode')
        Actives = $tab.FindName('ActivesSeules'); Info = $tab.FindName('InfoFichier')
        Bandeau = $tab.FindName('Bandeau'); BandeauTexte = $tab.FindName('BandeauTexte')
        Verifier = $tab.FindName('BtnVerifier')
        Ajouter = $tab.FindName('BtnAjouter'); Dupliquer = $tab.FindName('BtnDupliquer'); Modifier = $tab.FindName('BtnModifier')
        Activer = $tab.FindName('BtnActiver'); Supprimer = $tab.FindName('BtnSupprimer')
        Actualiser = $tab.FindName('BtnActualiser'); Reprise = $tab.FindName('BtnReprise'); Lancer = $tab.FindName('BtnLancer')
        Acquitter = $tab.FindName('BtnAcquitter'); Debloquer = $tab.FindName('BtnDebloquer'); Purger = $tab.FindName('BtnPurger')
        Promouvoir = $tab.FindName('BtnPromouvoir'); Historique = $tab.FindName('BtnHistorique')
        Graphe = $tab.FindName('Graphe'); GrapheInfo = $tab.FindName('GrapheInfo')
        Occupe = $false
    }
    $Script:Vues[$cle] = $vue
    $tiret = [string][char]0x2014
    $lectureSeule = (-not $Environnement.Modifiable) -or ($Contexte.Profil -ne 'Admin')
    $tab.Header = $(if ($lectureSeule) { $Environnement.Nom + ' (lecture seule)' } else { $Environnement.Nom })
    $vue.Info.Text = ('{0}  {1}  {2} règle(s)' -f (Split-Path -Leaf $Environnement.Fichier), $tiret, @($Environnement.Parametrage.Regles).Count)

    $messages = New-Object System.Collections.Generic.List[string]
    if ($Environnement.Message) { $messages.Add('Lecture seule : ' + $Environnement.Message + '.') }
    if ($Contexte.Profil -ne 'Admin') { $messages.Add('Votre compte n''est pas administrateur : consultation uniquement.') }
    $vue.Messages = $messages.ToArray()

    foreach ($m in @('Tous', 'copie', 'deplacement', 'archivage')) { $null = $vue.FiltreMode.Items.Add($m) }
    $vue.FiltreMode.SelectedIndex = 0

    foreach ($controle in $vue.Grille, $vue.Recherche, $vue.FiltreStatut, $vue.FiltreMode, $vue.Actives, $vue.Verifier, $vue.Ajouter, $vue.Dupliquer, $vue.Modifier, $vue.Activer, $vue.Supprimer, $vue.Actualiser, $vue.Reprise, $vue.Lancer, $vue.Acquitter, $vue.Debloquer, $vue.Purger, $vue.Promouvoir, $vue.Historique) { $controle.Tag = $cle }
    $vue.Grille.Add_SelectionChanged({ param($emetteur) Select-CopieRegle -Vue $Script:Vues[$emetteur.Tag] })
    $vue.Recherche.Add_TextChanged({ param($emetteur) Set-CopieFiltres -Vue $Script:Vues[$emetteur.Tag] })
    $vue.FiltreStatut.Add_SelectionChanged({ param($emetteur) Set-CopieFiltres -Vue $Script:Vues[$emetteur.Tag] })
    $vue.FiltreMode.Add_SelectionChanged({ param($emetteur) Set-CopieFiltres -Vue $Script:Vues[$emetteur.Tag] })
    $vue.Actives.Add_Click({ param($emetteur) Set-CopieFiltres -Vue $Script:Vues[$emetteur.Tag] })
    $vue.Verifier.Add_Click({ param($emetteur) Invoke-CopieVerification -Vue $Script:Vues[$emetteur.Tag] })
    $vue.Ajouter.Add_Click({ param($emetteur) Invoke-CopieEdition -Vue $Script:Vues[$emetteur.Tag] -Action 'ajout' })
    $vue.Dupliquer.Add_Click({ param($emetteur) Invoke-CopieEdition -Vue $Script:Vues[$emetteur.Tag] -Action 'duplication' })
    $vue.Modifier.Add_Click({ param($emetteur) Invoke-CopieEdition -Vue $Script:Vues[$emetteur.Tag] -Action 'modification' })
    $vue.Activer.Add_Click({ param($emetteur) Invoke-CopieEdition -Vue $Script:Vues[$emetteur.Tag] -Action 'activation' })
    $vue.Supprimer.Add_Click({ param($emetteur) Invoke-CopieEdition -Vue $Script:Vues[$emetteur.Tag] -Action 'suppression' })
    $vue.Actualiser.Add_Click({ param($emetteur) Update-CopieEtatVue -Vue $Script:Vues[$emetteur.Tag] })
    $vue.Reprise.Add_Click({ param($emetteur) Invoke-CopieActionRegle -Vue $Script:Vues[$emetteur.Tag] -Action 'reprise' })
    $vue.Lancer.Add_Click({ param($emetteur) Invoke-CopieActionRegle -Vue $Script:Vues[$emetteur.Tag] -Action 'lancement' })
    $vue.Acquitter.Add_Click({ param($emetteur) Invoke-CopieActionRegle -Vue $Script:Vues[$emetteur.Tag] -Action 'acquittement' })
    $vue.Debloquer.Add_Click({ param($emetteur) Invoke-CopieActionRegle -Vue $Script:Vues[$emetteur.Tag] -Action 'deblocage' })
    $vue.Purger.Add_Click({ param($emetteur) Invoke-CopiePurge -Vue $Script:Vues[$emetteur.Tag] })
    $vue.Promouvoir.Add_Click({ param($emetteur) Invoke-CopiePromotion -Vue $Script:Vues[$emetteur.Tag] })
    $vue.Historique.Add_Click({ param($emetteur) Show-CopieHistorique -Vue $Script:Vues[$emetteur.Tag] })

    Update-CopieVue -Vue $vue
    Update-CopieBoutons -Vue $vue
    $tab.Tag = $vue
    $tab
}
