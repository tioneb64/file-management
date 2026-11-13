# Boîte à outils vue de l'interface : lecture de l'index (outils.json du dossier de paramétrage), lignes d'affichage,
# résultat d'un scan. Le moteur reste le seul à parcourir le dossier des outils (python -m file_management
# --scanner-outils) : l'interface n'écrit que le texte d'index qu'il lui renvoie (docs/13-boite-a-outils.md §9 à §11).

$Script:FichierIndexOutils = 'outils.json'

function Get-CopieCheminIndexOutils {
    <#
    .SYNOPSIS
        Chemin de l'index des outils (outils.json) dans le dossier de paramétrage.
    .PARAMETER Dossier
        Dossier de paramétrage.
    .OUTPUTS
        [string]
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [string] $Dossier)
    Join-Path $Dossier $Script:FichierIndexOutils
}

function Get-CopieExempleOutil {
    <#
    .SYNOPSIS
        Début de commande à copier dans un programme : [ "{outil:nom}", paramètres obligatoires ].
    .PARAMETER Outil
        Outil de l'index (variable, parametres).
    .OUTPUTS
        [string] tableau JSON sur une ligne.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [pscustomobject] $Outil)
    $elements = New-Object System.Collections.Generic.List[string]
    $elements.Add('{outil:' + $Outil.Nom + '}')
    foreach ($p in @($Outil.Parametres | Where-Object { $_.Obligatoire -eq 'Oui' })) {
        $mots = @("$($p.Parametre)" -split '\s+' | Where-Object { $_ })
        $nom = ($mots[0] -split '/')[0]
        $elements.Add($nom)
        if ($mots.Count -gt 1) { $elements.Add('<' + ($mots[1..($mots.Count - 1)] -join ' ') + '>') }
    }
    '[' + (($elements | ForEach-Object { '"' + ($_ -replace '\\', '\\' -replace '"', '\"') + '"' }) -join ', ') + ']'
}

function ConvertTo-CopieOutilAffichage {
    <#
    .SYNOPSIS
        Une ligne d'affichage (grille et détail) pour un outil de l'index.
    .PARAMETER Outil
        Outil lu dans outils.json (variable, fichier, description, parametres).
    .OUTPUTS
        [pscustomobject] Copie.Outil : Nom, Variable ({outil:nom}), SousDossier, Fichier, Description, Obligatoires, Parametres, Exemple.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param([Parameter(Mandatory)] [object] $Outil)
    $fichier = "$(Get-CopieValeur $Outil 'fichier' '')"
    $parametres = New-Object System.Collections.Generic.List[object]
    foreach ($p in @(Get-CopieValeur $Outil 'parametres' @())) {
        $parametres.Add([pscustomobject]@{
                Parametre = "$(Get-CopieValeur $p 'forme' '')"
                Obligatoire = $(if (Get-CopieValeur $p 'obligatoire' $false) { 'Oui' } else { '' })
                Description = "$(Get-CopieValeur $p 'description' '')"
            })
    }
    $obligatoires = @($parametres | Where-Object { $_.Obligatoire -eq 'Oui' } | ForEach-Object { $_.Parametre }) -join ', '
    $nom = "$(Get-CopieValeur $Outil 'variable' '')"
    $ligne = [pscustomobject]@{
        PSTypeName = 'Copie.Outil'; Nom = $nom; Variable = ('{outil:' + $nom + '}')
        SousDossier = (Split-Path -Parent $fichier); Fichier = (Split-Path -Leaf $fichier)
        FichierRelatif = $fichier; Description = "$(Get-CopieValeur $Outil 'description' '')"
        Obligatoires = $obligatoires; Parametres = $parametres.ToArray(); Exemple = ''
    }
    $ligne.Exemple = Get-CopieExempleOutil -Outil $ligne
    $ligne
}

function Get-CopieIndexOutils {
    <#
    .SYNOPSIS
        Lit l'index des outils du dossier de paramétrage.
    .DESCRIPTION
        Ne lève jamais d'exception : un fichier absent donne Present = $false ; un fichier illisible donne
        Present = $true, Erreur renseignée et aucun outil.
    .PARAMETER Dossier
        Dossier de paramétrage.
    .OUTPUTS
        [pscustomobject] Copie.IndexOutils : Present, Chemin, DossierConfigure ('' = dossier outils du moteur), DossierResolu,
        ScanneLe, ScannePar, Outils (Copie.Outil triés par variable), Erreur.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param([Parameter(Mandatory)] [string] $Dossier)
    $chemin = Get-CopieCheminIndexOutils -Dossier $Dossier
    $index = [pscustomobject]@{
        PSTypeName = 'Copie.IndexOutils'; Present = $false; Chemin = $chemin; DossierConfigure = ''; DossierResolu = ''
        ScanneLe = ''; ScannePar = ''; Outils = @(); Erreur = ''
    }
    if (-not (Test-Path -LiteralPath $chemin -PathType Leaf)) { return $index }
    $index.Present = $true
    try {
        $texte = [System.IO.File]::ReadAllText($chemin, (New-Object System.Text.UTF8Encoding($false)))
        $document = $texte | ConvertFrom-Json
        if ($null -eq $document -or $document.version -ne 1) { throw ('version {0} non prise en charge (attendu : 1)' -f $document.version) }
        $index.DossierConfigure = "$(Get-CopieValeur $document 'dossier_outils' '')"
        $index.DossierResolu = "$(Get-CopieValeur $document 'dossier_resolu' '')"
        $index.ScanneLe = "$(Get-CopieValeur $document 'scanne_le' '')"
        $index.ScannePar = "$(Get-CopieValeur $document 'scanne_par' '')"
        $liste = New-Object System.Collections.Generic.List[object]
        foreach ($o in @(Get-CopieValeur $document 'outils' @())) { $liste.Add((ConvertTo-CopieOutilAffichage -Outil $o)) }
        $index.Outils = @($liste.ToArray() | Sort-Object Nom)
    }
    catch { $index.Erreur = ('{0} illisible : {1}' -f $Script:FichierIndexOutils, $_.Exception.Message) }
    $index
}

function Save-CopieIndexOutils {
    <#
    .SYNOPSIS
        Écrit outils.json (le texte renvoyé par le moteur) dans le dossier de paramétrage, de façon atomique.
    .DESCRIPTION
        Fichier temporaire du même dossier puis remplacement : le moteur ne lit jamais un index à moitié écrit.
        UTF-8 sans BOM. Les droits sont ceux de l'utilisateur qui enregistre (administrateur).
    .PARAMETER Dossier
        Dossier de paramétrage.
    .PARAMETER Contenu
        Texte exact du fichier (champ contenu_index de la réponse du moteur).
    .OUTPUTS
        [string] chemin écrit.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [string] $Dossier, [Parameter(Mandatory)] [string] $Contenu)
    $chemin = Get-CopieCheminIndexOutils -Dossier $Dossier
    $temporaire = $chemin + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [System.IO.File]::WriteAllText($temporaire, $Contenu, (New-Object System.Text.UTF8Encoding($false)))
        if (Test-Path -LiteralPath $chemin -PathType Leaf) { [System.IO.File]::Replace($temporaire, $chemin, [NullString]::Value) }
        else { [System.IO.File]::Move($temporaire, $chemin) }
    }
    finally { if (Test-Path -LiteralPath $temporaire) { Remove-Item -LiteralPath $temporaire -Force -ErrorAction SilentlyContinue } }
    $chemin
}

function ConvertTo-CopieLignesScanOutils {
    <#
    .SYNOPSIS
        Lignes de la fenêtre de résultat d'un scan (Show-CopieOperation) : outils retenus, scripts non retenus avec la cause.
    .DESCRIPTION
        Un module qui se déclare « # bibliotheque: » est une information à part (support des outils, jamais appelé par une règle) ;
        un script sans en-tête est une information (script ordinaire, normal) ; un en-tête invalide, une variable
        déjà prise, un fichier illisible ou un dossier illisible sont des avertissements.
    .PARAMETER Reponse
        Réponse du moteur à --scanner-outils (Copie.ReponseMoteur).
    .OUTPUTS
        [pscustomobject[]] lignes (New-CopieLigneResultat).
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject[]])]
    param([Parameter(Mandatory)] [pscustomobject] $Reponse)
    $lignes = New-Object System.Collections.Generic.List[object]
    $json = $Reponse.Json
    if (-not $Reponse.Reussi) {
        $message = $(if ($null -ne $json -and (Get-CopieValeur $json 'message' '')) { "$($json.message)" } else { $Reponse.Erreur })
        $lignes.Add((New-CopieLigneResultat -Gravite 'Erreur' -Sujet 'Scan des outils' -Message $message))
        return $lignes.ToArray()
    }
    $outils = @(Get-CopieValeur $json 'outils' @())
    $nonRetenus = @(Get-CopieValeur $json 'non_retenus' @())
    $lignes.Add((New-CopieLigneResultat -Gravite 'Information' -Sujet 'Dossier analysé' `
                -Message ('{0} ({1} dossier(s), {2} script(s) Python)' -f (Get-CopieValeur $json 'dossier' ''), (Get-CopieValeur $json 'dossiers' 0), (Get-CopieValeur $json 'fichiers_python' 0))))
    foreach ($o in $outils) {
        $lignes.Add((New-CopieLigneResultat -Gravite 'Information' -Sujet ('Outil retenu : {outil:' + $o.variable + '}') `
                    -Message ('{0} : {1}' -f $o.fichier, $o.description)))
    }
    foreach ($b in @(Get-CopieValeur $json 'bibliotheques' @())) {
        $lignes.Add((New-CopieLigneResultat -Gravite 'Information' -Sujet ('Bibliothèque : ' + $b.fichier) -Message "$($b.description)"))
    }
    foreach ($n in $nonRetenus) {
        $gravite = $(if ("$($n.cause)" -like 'pas d''en-tete*') { 'Information' } else { 'Avertissement' })
        $lignes.Add((New-CopieLigneResultat -Gravite $gravite -Sujet ('Non retenu : ' + $n.fichier) -Message "$($n.cause)"))
    }
    foreach ($e in @(Get-CopieValeur $json 'erreurs' @())) {
        $lignes.Add((New-CopieLigneResultat -Gravite 'Avertissement' -Sujet ('Non parcouru : ' + $e.chemin) -Message "$($e.message)"))
    }
    if ($outils.Count -eq 0) {
        $lignes.Add((New-CopieLigneResultat -Gravite 'Avertissement' -Sujet 'Aucun outil' `
                    -Message 'Aucun script n''a d''en-tête d''outil valide dans ce dossier : le réglage et l''index précédents sont conservés.'))
    }
    $lignes.ToArray()
}
