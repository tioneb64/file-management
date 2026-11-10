function Get-CopieConfig {
    <#
    .SYNOPSIS
        Lit et valide la configuration de l'interface (Gestion-Copie.config.psd1).

    .DESCRIPTION
        Fichier de données PowerShell (jamais exécuté). Une clé inconnue est refusée : une faute de
        frappe ne doit pas être ignorée en silence. Les valeurs absentes prennent la valeur de secours
        documentée dans le fichier fourni. Toutes les erreurs sont cumulées dans un seul message.

    .PARAMETER Chemin
        Fichier de configuration.

    .OUTPUTS
        [pscustomobject] Copie.Config : Acces, Moteur, Parametrage, Journal.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)]
        [string] $Chemin
    )

    if (-not (Test-Path -LiteralPath $Chemin -PathType Leaf)) {
        throw ('Configuration introuvable : {0}' -f $Chemin)
    }
    $brut = Import-PowerShellDataFile -LiteralPath $Chemin
    $erreurs = New-Object System.Collections.Generic.List[string]

    $schema = @{
        Acces       = @('GroupesAdmin')
        Moteur      = @('Mode', 'Python', 'Racine', 'Serveur', 'ConfigurationJea', 'DelaiMaxSec')
        Parametrage = @('Filtre', 'VersionsSupportees', 'DossierVersions', 'PeriodeDeclencheurSec')
        Journal     = @('Dossier')
    }
    foreach ($cle in @($brut.Keys)) {
        if (-not $schema.ContainsKey($cle)) { $erreurs.Add(('section inconnue : {0}' -f $cle)) }
    }
    $section = @{}
    foreach ($nom in $schema.Keys) {
        $valeurs = $brut[$nom]
        if ($null -eq $valeurs) { $valeurs = @{} }
        if ($valeurs -isnot [System.Collections.IDictionary]) {
            $erreurs.Add(('la section {0} doit être une table @{{ ... }}' -f $nom))
            $valeurs = @{}
        }
        foreach ($cle in @($valeurs.Keys)) {
            if ($schema[$nom] -notcontains $cle) { $erreurs.Add(('clé inconnue : {0}.{1}' -f $nom, $cle)) }
        }
        $section[$nom] = $valeurs
    }

    $lire = {
        param($nomSection, $cle, $defaut)
        $v = $section[$nomSection][$cle]
        if ($null -eq $v) { return $defaut }
        return $v
    }

    $groupes = @(& $lire 'Acces' 'GroupesAdmin' @() | Where-Object { $_ -and "$_".Trim() } | ForEach-Object { "$_".Trim() })
    if ($groupes.Count -eq 0) {
        $erreurs.Add('Acces.GroupesAdmin : au moins un groupe est obligatoire (jamais d''accès ouvert par défaut)')
    }

    $mode = "$(& $lire 'Moteur' 'Mode' 'Local')"
    if ($mode -notin 'Local', 'Distant') { $erreurs.Add(('Moteur.Mode : "{0}" inconnu (Local ou Distant)' -f $mode)) }
    $jea = "$(& $lire 'Moteur' 'ConfigurationJea' '')".Trim()
    $serveur = "$(& $lire 'Moteur' 'Serveur' '')".Trim()
    $python = "$(& $lire 'Moteur' 'Python' '')".Trim()
    $racine = "$(& $lire 'Moteur' 'Racine' '')".Trim()
    if ($mode -eq 'Distant' -and -not $serveur) { $erreurs.Add('Moteur.Serveur : obligatoire en mode Distant') }
    if ($jea -and $mode -ne 'Distant') { $erreurs.Add('Moteur.ConfigurationJea : réservé au mode Distant') }
    if (-not $jea) {
        if (-not $python) { $erreurs.Add('Moteur.Python : obligatoire (sauf point d''accès JEA)') }
        if (-not $racine) { $erreurs.Add('Moteur.Racine : obligatoire (sauf point d''accès JEA)') }
    }
    $delai = [int](& $lire 'Moteur' 'DelaiMaxSec' 120)
    if ($delai -lt 1) { $erreurs.Add('Moteur.DelaiMaxSec doit être supérieur à 0') }

    $filtre = "$(& $lire 'Parametrage' 'Filtre' '*.jsonl')"
    $versions = @(& $lire 'Parametrage' 'VersionsSupportees' @(1) | ForEach-Object { [int]$_ })
    $dossierVersions = "$(& $lire 'Parametrage' 'DossierVersions' 'versions')"
    $periode = [int](& $lire 'Parametrage' 'PeriodeDeclencheurSec' 300)
    if ($periode -lt 1) { $erreurs.Add('Parametrage.PeriodeDeclencheurSec doit être supérieur à 0') }

    if ($erreurs.Count -gt 0) {
        throw ('Configuration invalide ({0}) :{1}{2}' -f $Chemin, [Environment]::NewLine,
            (($erreurs | ForEach-Object { '  - ' + $_ }) -join [Environment]::NewLine))
    }

    [pscustomobject]@{
        PSTypeName  = 'Copie.Config'
        Chemin      = (Resolve-Path -LiteralPath $Chemin).ProviderPath
        Acces       = [pscustomobject]@{ GroupesAdmin = $groupes }
        Moteur      = [pscustomobject]@{
            Mode = $mode; Python = $python; Racine = $racine; Serveur = $serveur
            ConfigurationJea = $jea; DelaiMaxSec = $delai
        }
        Parametrage = [pscustomobject]@{
            Filtre = $filtre; VersionsSupportees = $versions; DossierVersions = $dossierVersions
            PeriodeDeclencheurSec = $periode
        }
        Journal     = [pscustomobject]@{ Dossier = "$(& $lire 'Journal' 'Dossier' '')".Trim() }
    }
}
