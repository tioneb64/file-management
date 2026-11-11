function Get-CopieEnvironnement {
    <#
    .SYNOPSIS
        Parcourt le dossier de paramétrage et décrit chaque environnement (un fichier = un environnement).

    .DESCRIPTION
        Charge chaque fichier du dossier (Parametrage.Filtre) et lit son en-tête. Contrôles d'ouverture
        (docs/04-frontend.md §3) : deux fichiers qui déclarent le même environnement, un environnement
        différent du nom du fichier, une version de format inconnue, un en-tête absent ou illisible.
        Un fichier concerné est renvoyé en lecture seule (Modifiable = $false) avec son message : il
        reste affiché, mais aucune modification n'y est permise.

    .PARAMETER Dossier
        Dossier de paramétrage (passé au lancement de l'outil).

    .PARAMETER Config
        Configuration (Get-CopieConfig).

    .OUTPUTS
        [pscustomobject[]] Copie.Environnement : Nom, Fichier, Parametrage, Modifiable, Message.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject[]])]
    param(
        [Parameter(Mandatory)]
        [string] $Dossier,

        [Parameter(Mandatory)]
        [pscustomobject] $Config
    )

    if (-not (Test-Path -LiteralPath $Dossier -PathType Container)) {
        throw ('Dossier de paramétrage introuvable : {0}' -f $Dossier)
    }
    $fichiers = @(Get-ChildItem -LiteralPath $Dossier -Filter $Config.Parametrage.Filtre -File | Sort-Object Name)
    $liste = foreach ($fichier in $fichiers) {
        $p = Read-CopieFichierParametrage -Chemin $fichier.FullName
        $base = [System.IO.Path]::GetFileNameWithoutExtension($fichier.Name)
        $messages = New-Object System.Collections.Generic.List[string]
        foreach ($e in $p.Erreurs) { $messages.Add($e) }

        $declare = $null
        if ($null -ne $p.Entete) {
            $prop = $p.Entete.PSObject.Properties['environnement']
            if ($null -ne $prop) { $declare = "$($prop.Value)" }
            $version = $p.Entete.PSObject.Properties['version']
            if ($null -eq $version -or $Config.Parametrage.VersionsSupportees -notcontains [int]"$($version.Value)") {
                $messages.Add(('version de format non prise en charge : {0}' -f $(if ($null -eq $version) { 'absente' } else { $version.Value })))
            }
            if (-not $declare) { $messages.Add('l''en-tête ne déclare pas d''environnement') }
            elseif ($declare -ne $base) {
                $messages.Add(('l''environnement déclaré ({0}) diffère du nom du fichier ({1})' -f $declare, $base))
            }
        }
        [pscustomobject]@{
            PSTypeName  = 'Copie.Environnement'
            Nom         = $(if ($declare) { $declare } else { $base })
            Fichier     = $fichier.FullName
            Parametrage = $p
            Modifiable  = ($messages.Count -eq 0)
            Message     = ($messages -join ' ; ')
        }
    }
    $liste = @($liste)

    # Deux fichiers qui déclarent le même environnement : les deux passent en lecture seule.
    foreach ($groupe in @($liste | Group-Object -Property Nom | Where-Object { $_.Count -gt 1 })) {
        foreach ($env in $groupe.Group) {
            $autres = @($groupe.Group | Where-Object { $_ -ne $env } | ForEach-Object { Split-Path -Leaf $_.Fichier })
            $env.Modifiable = $false
            $texte = 'l''environnement est aussi déclaré par ' + ($autres -join ', ')
            $env.Message = $(if ($env.Message) { $env.Message + ' ; ' + $texte } else { $texte })
        }
    }
    $liste
}
