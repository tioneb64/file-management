# Résultat d'une opération en un seul écran. Règle d'affichage : une boîte de message Oui / Non pour chaque DEMANDE
# (accord, confirmation) ; tout ce qui n'est que de l'information, un avertissement ou une erreur est rassemblé dans
# une seule fenêtre, comme « Vérifier le paramétrage », au lieu d'une boîte « OK » par message.

function New-CopieLigneResultat {
    <#
    .SYNOPSIS
        Une ligne de la fenêtre de résultat : gravité, sujet, message.
    .PARAMETER Gravite
        Information, Avertissement ou Erreur.
    .PARAMETER Sujet
        Ce dont il s'agit (« Enregistrement », « Répertoire d'origine »...).
    .PARAMETER Message
        Le message, en clair.
    .OUTPUTS
        [pscustomobject] Gravite, Couleur, Sujet, Message.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)] [ValidateSet('Information', 'Avertissement', 'Erreur')] [string] $Gravite,
        [Parameter(Mandatory)] [string] $Sujet,
        [Parameter(Mandatory)] [AllowEmptyString()] [string] $Message
    )
    $couleur = switch ($Gravite) { 'Erreur' { '#C0392B' } 'Avertissement' { '#C77700' } default { '#1F6FB2' } }
    [pscustomobject]@{ PSTypeName = 'Copie.LigneResultat'; Gravite = $Gravite; Couleur = $couleur; Sujet = $Sujet; Message = $Message }
}

function Get-CopieResumeResultat {
    <#
    .SYNOPSIS
        Phrase de synthèse d'une liste de lignes de résultat : « 2 erreur(s), 1 avertissement(s). » ou « Tout s'est bien passé. ».
    .PARAMETER Ligne
        Lignes (New-CopieLigneResultat).
    .PARAMETER Debut
        Texte placé avant le décompte (par exemple « Règle « x » enregistrée. »).
    .OUTPUTS
        [string]
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([AllowEmptyCollection()] [object[]] $Ligne = @(), [string] $Debut = '')
    $erreurs = @($Ligne | Where-Object { $_.Gravite -eq 'Erreur' }).Count
    $avertissements = @($Ligne | Where-Object { $_.Gravite -eq 'Avertissement' }).Count
    $fin = $(if ($erreurs -gt 0) { '{0} erreur(s), {1} avertissement(s).' -f $erreurs, $avertissements }
        elseif ($avertissements -gt 0) { '{0} avertissement(s), aucune erreur.' -f $avertissements }
        else { 'Tout s''est bien passé.' })
    (($Debut + ' ' + $fin).Trim())
}

function Show-CopieResultat {
    <#
    .SYNOPSIS
        Fenêtre unique qui rassemble les informations, avertissements et erreurs d'une opération.
    .PARAMETER Contexte
        Contexte de la session (Fenetre = fenêtre propriétaire).
    .PARAMETER Titre
        Titre de la fenêtre.
    .PARAMETER Resume
        Phrase d'en-tête (voir Get-CopieResumeResultat).
    .PARAMETER Ligne
        Lignes à afficher (New-CopieLigneResultat), dans l'ordre.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [hashtable] $Contexte,
        [Parameter(Mandatory)] [string] $Titre,
        [Parameter(Mandatory)] [string] $Resume,
        [Parameter(Mandatory)] [AllowEmptyCollection()] [object[]] $Ligne
    )
    $fenetre = Import-CopieXaml -Nom 'Dialog.Resultat'
    if ($null -ne $Contexte.Fenetre) { $fenetre.Owner = $Contexte.Fenetre }
    $fenetre.Title = $Titre
    $fenetre.FindName('Resume').Text = $Resume
    $fenetre.FindName('Grille').ItemsSource = @($Ligne)
    $null = $fenetre.ShowDialog()
}

# Collecteur d'une opération en plusieurs étapes (création d'un environnement : fichier, dossiers, base...). Chaque étape
# y note ce qu'elle a à dire ; l'opération n'ouvre qu'une fenêtre, à la fin (Show-CopieOperation).
$Script:LignesOperation = New-Object System.Collections.Generic.List[object]

function Reset-CopieOperation {
    <#
    .SYNOPSIS
        Vide le collecteur : à appeler au début de chaque opération.
    #>
    [CmdletBinding()]
    param()
    $Script:LignesOperation.Clear()
}

function Add-CopieLigneOperation {
    <#
    .SYNOPSIS
        Note une information, un avertissement ou une erreur pour la fenêtre de fin d'opération.
    .PARAMETER Gravite
        Information, Avertissement ou Erreur.
    .PARAMETER Sujet
        Ce dont il s'agit.
    .PARAMETER Message
        Le message.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [ValidateSet('Information', 'Avertissement', 'Erreur')] [string] $Gravite,
        [Parameter(Mandatory)] [string] $Sujet,
        [Parameter(Mandatory)] [AllowEmptyString()] [string] $Message
    )
    $Script:LignesOperation.Add((New-CopieLigneResultat -Gravite $Gravite -Sujet $Sujet -Message $Message))
}

function Get-CopieGraviteIcone {
    <#
    .SYNOPSIS
        Icône de boîte de message (Information, Warning, Error) -> gravité de la fenêtre de résultat.
    .PARAMETER Icone
        Information, Warning ou Error.
    .OUTPUTS
        [string]
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([string] $Icone = 'Information')
    switch ($Icone) { 'Error' { 'Erreur' } 'Warning' { 'Avertissement' } default { 'Information' } }
}

function Show-CopieOperation {
    <#
    .SYNOPSIS
        Montre, en une seule fenêtre, tout ce qu'une opération a noté (collecteur) plus les lignes données ; vide le collecteur.
    .PARAMETER Contexte
        Contexte de la session.
    .PARAMETER Titre
        Titre de la fenêtre.
    .PARAMETER Debut
        Début de la phrase de synthèse.
    .PARAMETER Ligne
        Lignes à placer avant celles du collecteur.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [hashtable] $Contexte,
        [Parameter(Mandatory)] [string] $Titre,
        [string] $Debut = '',
        [AllowEmptyCollection()] [object[]] $Ligne = @()
    )
    $lignes = @($Ligne) + @($Script:LignesOperation.ToArray())
    $Script:LignesOperation.Clear()
    if ($lignes.Count -eq 0) { return }
    Show-CopieResultat -Contexte $Contexte -Titre $Titre -Resume (Get-CopieResumeResultat -Ligne $lignes -Debut $Debut) -Ligne $lignes
}
