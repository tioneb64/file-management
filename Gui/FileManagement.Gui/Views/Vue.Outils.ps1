# Onglet « Outils » : dossier des outils, liste des outils (variable {outil:nom}, paramètres), scan.
# Le dossier est un réglage du moteur, commun à tous les environnements : il est enregistré dans outils.json (dossier de
# paramétrage) avec la liste des outils trouvés. Une seule vue existe : $Script:VueOutils (les gestionnaires WPF la
# retrouvent par ce nom, comme $Script:Vues pour les environnements).
$Script:VueOutils = $null

function Update-CopieVueOutils {
    <#
    .SYNOPSIS
        Relit outils.json et remplit l'onglet (dossier, grille, compteur, détail).
    .PARAMETER Vue
        Vue de l'onglet (New-CopieVueOutils).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)
    $index = Get-CopieIndexOutils -Dossier $Vue.Contexte.Dossier
    $Vue.Index = $index
    $Vue.Dossier.Text = $index.DossierConfigure
    if ($index.Erreur) { $Vue.InfoDossier.Text = $index.Erreur + ' Enregistrez le dossier pour recréer l''index.' }
    elseif (-not $index.Present) {
        $Vue.InfoDossier.Text = 'Aucun index des outils : tant que le dossier n''est pas enregistré et scanné, aucune règle ne peut appeler un outil par sa variable {outil:nom}.'
    }
    elseif ($index.DossierConfigure) { $Vue.InfoDossier.Text = 'Dossier utilisé par le moteur : ' + $index.DossierConfigure }
    else { $Vue.InfoDossier.Text = 'Dossier utilisé par le moteur : le dossier « outils » situé à la racine du moteur' + $(if ($index.DossierResolu) { ' (' + $index.DossierResolu + ' au dernier scan)' } else { '' }) + '.' }
    if ($index.Present -and -not $index.Erreur) {
        $Vue.InfoScan.Text = ('Dernier scan : {0}{1} — {2} outil(s) indexé(s).' -f ($index.ScanneLe -replace 'T', ' '), $(if ($index.ScannePar) { ' par ' + $index.ScannePar } else { '' }), @($index.Outils).Count)
    }
    else { $Vue.InfoScan.Text = '' }
    Set-CopieFiltreOutils -Vue $Vue
}

function Set-CopieFiltreOutils {
    <#
    .SYNOPSIS
        Applique la recherche à la grille des outils et met à jour le compteur.
    .PARAMETER Vue
        Vue de l'onglet.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)
    $texte = "$($Vue.Recherche.Text)".Trim()
    $outils = @($Vue.Index.Outils)
    if ($texte) {
        $outils = @($outils | Where-Object {
                $ligne = ($_.Variable, $_.SousDossier, $_.Fichier, $_.Description, $_.Obligatoires) -join ' '
                $ligne.IndexOf($texte, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 })
    }
    $selection = $(if ($Vue.Grille.SelectedItem) { $Vue.Grille.SelectedItem.Nom } else { '' })
    $Vue.Grille.ItemsSource = $outils
    $Vue.Compteur.Text = $(if ($texte) { '{0} outil(s) sur {1}' -f $outils.Count, @($Vue.Index.Outils).Count } else { '{0} outil(s)' -f $outils.Count })
    $retrouve = @($outils | Where-Object { $_.Nom -eq $selection })
    if ($retrouve.Count -gt 0) { $Vue.Grille.SelectedItem = $retrouve[0] } else { Select-CopieOutil -Vue $Vue }
}

function Select-CopieOutil {
    <#
    .SYNOPSIS
        Affiche le détail de l'outil sélectionné (description, fichier, début de commande, paramètres).
    .PARAMETER Vue
        Vue de l'onglet.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)
    $o = $Vue.Grille.SelectedItem
    if ($null -eq $o) {
        $Vue.Titre.Text = 'Aucun outil sélectionné'
        $Vue.DescriptionOutil.Text = ''
        $Vue.FichierOutil.Text = ''
        $Vue.Exemple.Text = ''
        $Vue.GrilleParametres.ItemsSource = @()
        return
    }
    $Vue.Titre.Text = $o.Variable
    $Vue.DescriptionOutil.Text = $o.Description
    $dossier = $(if ($Vue.Index.DossierConfigure) { $Vue.Index.DossierConfigure } elseif ($Vue.Index.DossierResolu) { $Vue.Index.DossierResolu } else { '(dossier outils du moteur)' })
    $Vue.FichierOutil.Text = 'Fichier : ' + (Join-Path $dossier $o.FichierRelatif)
    $Vue.Exemple.Text = $o.Exemple
    $Vue.GrilleParametres.ItemsSource = @($o.Parametres)
}

function Invoke-CopieScanOutils {
    <#
    .SYNOPSIS
        Enregistre le dossier des outils : le moteur le parcourt, l'index est écrit, une fenêtre donne le résultat.

    .DESCRIPTION
        1. python -m file_management --scanner-outils [--dossier-outils X] (lecture seule, côté moteur) ;
        2. si au moins un outil est retenu, le texte d'index renvoyé est écrit dans outils.json (atomique) ;
           sinon rien n'est écrit (un dossier faux ne doit pas effacer un bon index) ;
        3. chaque outil retenu et chaque script non retenu (avec sa cause) est tracé dans le journal de l'interface ;
        4. une seule fenêtre montre le résultat (Show-CopieOperation).

    .PARAMETER Vue
        Vue de l'onglet (New-CopieVueOutils).

    .PARAMETER Dossier
        Dossier des outils à enregistrer ; vide = le dossier « outils » du moteur. Par défaut : la valeur saisie dans l'onglet.

    .OUTPUTS
        [pscustomobject] Reponse (réponse du moteur), Enregistre ($true si outils.json a été écrit), Lignes.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param([Parameter(Mandatory)] [hashtable] $Vue, [string] $Dossier)
    $ctx = $Vue.Contexte
    if (-not $PSBoundParameters.ContainsKey('Dossier')) { $Dossier = "$($Vue.Dossier.Text)" }
    $Dossier = $Dossier.Trim()
    $ctx.Fenetre.Cursor = [System.Windows.Input.Cursors]::Wait
    try {
        $argument = @('--scanner-outils', '--utilisateur', $ctx.Utilisateur)
        if ($Dossier) { $argument += @('--dossier-outils', $Dossier) }
        $reponse = Invoke-CopieMoteur -Config $ctx.Config -Argument $argument
    }
    finally { $ctx.Fenetre.Cursor = $null }
    $lignes = @(ConvertTo-CopieLignesScanOutils -Reponse $reponse)
    $retenus = $(if ($reponse.Reussi) { @(Get-CopieValeur $reponse.Json 'outils' @()) } else { @() })
    $enregistre = $false
    $debut = ''
    if (-not $reponse.Reussi) {
        Write-CopieJournal -Contexte $ctx -Niveau 'ERREUR' -Evenement 'outils_scan' -Message ('Scan des outils impossible : ' + $lignes[0].Message) -Donnees @{ dossier = $Dossier }
        $debut = 'Scan des outils impossible : rien n''a été enregistré.'
    }
    elseif ($retenus.Count -eq 0) { $debut = 'Aucun outil trouvé : rien n''a été enregistré.' }
    else {
        try {
            $chemin = Save-CopieIndexOutils -Dossier $ctx.Dossier -Contenu "$($reponse.Json.contenu_index)"
            $enregistre = $true
            $lignes += New-CopieLigneResultat -Gravite 'Information' -Sujet 'Index enregistré' -Message ('{0} : lu par le moteur à chaque lancement.' -f $chemin)
            $debut = 'Dossier des outils enregistré.'
        }
        catch {
            $lignes += New-CopieLigneResultat -Gravite 'Erreur' -Sujet 'Enregistrement de l''index' -Message $_.Exception.Message
            Write-CopieJournal -Contexte $ctx -Niveau 'ERREUR' -Evenement 'outils_index' -Message ('Index des outils non enregistré : ' + $_.Exception.Message)
            $debut = 'L''index n''a pas pu être enregistré.'
        }
    }
    if ($reponse.Reussi) {
        Write-CopieJournal -Contexte $ctx -Niveau $(if ($retenus.Count -eq 0) { 'WARNING' } else { 'INFO' }) -Evenement 'outils_scan' `
            -Message ('Scan des outils : {0} retenu(s), {1} non retenu(s) dans {2}' -f $retenus.Count, @(Get-CopieValeur $reponse.Json 'non_retenus' @()).Count, (Get-CopieValeur $reponse.Json 'dossier' '')) `
            -Donnees @{ dossier = "$(Get-CopieValeur $reponse.Json 'dossier' '')"; retenus = $retenus.Count; non_retenus = @(Get-CopieValeur $reponse.Json 'non_retenus' @()).Count; bibliotheques = @(Get-CopieValeur $reponse.Json 'bibliotheques' @()).Count; enregistre = $enregistre }
        foreach ($o in $retenus) {
            Write-CopieJournal -Contexte $ctx -Evenement 'outil_retenu' -Message ('Outil retenu : {{outil:{0}}} ({1})' -f $o.variable, $o.fichier) `
                -Donnees @{ outil = "$($o.variable)"; fichier = "$($o.fichier)" }
        }
        foreach ($b in @(Get-CopieValeur $reponse.Json 'bibliotheques' @())) {
            Write-CopieJournal -Contexte $ctx -Evenement 'outil_bibliotheque' -Message ('Module de bibliothèque ignoré : {0} : {1}' -f $b.fichier, $b.description) `
                -Donnees @{ fichier = "$($b.fichier)"; description = "$($b.description)" }
        }
        foreach ($n in @(Get-CopieValeur $reponse.Json 'non_retenus' @())) {
            $niveau = $(if ("$($n.cause)" -like 'pas d''en-tete*') { 'INFO' } else { 'WARNING' })
            Write-CopieJournal -Contexte $ctx -Niveau $niveau -Evenement 'outil_non_retenu' -Message ('Script non retenu : {0} : {1}' -f $n.fichier, $n.cause) `
                -Donnees @{ fichier = "$($n.fichier)"; cause = "$($n.cause)" }
        }
    }
    Show-CopieOperation -Contexte $ctx -Titre 'Scan des outils' -Debut $debut -Ligne $lignes
    if ($enregistre) { Update-CopieVueOutils -Vue $Vue }
    [pscustomobject]@{ Reponse = $reponse; Enregistre = $enregistre; Lignes = $lignes }
}

function Invoke-CopieParcourirOutils {
    <#
    .SYNOPSIS
        Choix du dossier des outils dans une boîte « Parcourir » (moteur local seulement).
    .PARAMETER Vue
        Vue de l'onglet.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)
    Add-Type -AssemblyName System.Windows.Forms
    $boite = New-Object System.Windows.Forms.FolderBrowserDialog
    $boite.Description = 'Dossier des outils (le moteur le parcourt avec ses sous-dossiers)'
    if ($Vue.Dossier.Text -and (Test-Path -LiteralPath $Vue.Dossier.Text -PathType Container)) { $boite.SelectedPath = $Vue.Dossier.Text }
    try { if ($boite.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { $Vue.Dossier.Text = $boite.SelectedPath } }
    finally { $boite.Dispose() }
}

function New-CopieVueOutils {
    <#
    .SYNOPSIS
        Crée l'onglet « Outils ».
    .DESCRIPTION
        Consultation pour tous ; l'enregistrement du dossier (et donc le scan) est réservé aux administrateurs.
        Le bouton « Parcourir… » n'existe que si le moteur tourne sur cette machine (Moteur.Mode = Local) : en mode
        Distant, le dossier est celui du serveur et se saisit à la main.
    .PARAMETER Contexte
        Contexte de la session.
    .OUTPUTS
        [System.Windows.Controls.TabItem] ; sa propriété Tag contient la vue (Type = 'Outils').
    #>
    [CmdletBinding()]
    [OutputType([System.Windows.Controls.TabItem])]
    param([Parameter(Mandatory)] [hashtable] $Contexte)
    $tab = Import-CopieXaml -Nom 'Outils'
    $admin = ($Contexte.Profil -eq 'Admin')
    $vue = @{
        Type = 'Outils'; Contexte = $Contexte; Tab = $tab; Index = $null
        Dossier = $tab.FindName('DossierOutils'); Parcourir = $tab.FindName('BtnOutilsParcourir'); Scanner = $tab.FindName('BtnOutilsScanner')
        InfoDossier = $tab.FindName('InfoDossierOutils'); InfoScan = $tab.FindName('InfoScanOutils')
        Compteur = $tab.FindName('CompteurOutils'); Recherche = $tab.FindName('RechercheOutils'); Grille = $tab.FindName('GrilleOutils')
        Titre = $tab.FindName('OutilTitre'); DescriptionOutil = $tab.FindName('OutilDescription'); FichierOutil = $tab.FindName('OutilFichier')
        Exemple = $tab.FindName('OutilExemple'); GrilleParametres = $tab.FindName('GrilleParametres')
    }
    $Script:VueOutils = $vue
    $tab.Tag = $vue
    $vue.Dossier.IsReadOnly = (-not $admin)
    $vue.Scanner.Visibility = $(if ($admin) { 'Visible' } else { 'Collapsed' })
    $vue.Parcourir.Visibility = $(if ($admin -and $Contexte.Config.Moteur.Mode -eq 'Local') { 'Visible' } else { 'Collapsed' })
    if (-not $admin) { $vue.Dossier.ToolTip = 'Votre compte n''est pas administrateur : consultation uniquement.' }
    $vue.Grille.Add_SelectionChanged({ Select-CopieOutil -Vue $Script:VueOutils })
    $vue.Recherche.Add_TextChanged({ Set-CopieFiltreOutils -Vue $Script:VueOutils })
    $vue.Parcourir.Add_Click({ Invoke-CopieParcourirOutils -Vue $Script:VueOutils })
    $vue.Scanner.Add_Click({ $null = Invoke-CopieScanOutils -Vue $Script:VueOutils })
    Update-CopieVueOutils -Vue $vue
    $tab
}
