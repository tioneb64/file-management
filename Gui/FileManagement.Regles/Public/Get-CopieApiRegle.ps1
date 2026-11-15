function Get-CopieApiRegle {
    <#
    .SYNOPSIS
        Lit les règles d'un fichier de paramétrage (lecture seule) et renvoie l'empreinte du fichier lu.

    .DESCRIPTION
        L'empreinte peut être transmise à Add-/Set-/Remove-CopieApiRegle (-Empreinte) : si le fichier a changé
        entre la lecture et l'écriture, l'écriture est refusée (conflit) au lieu d'écraser le travail d'un autre.

    .PARAMETER Fichier
        Fichier de paramétrage (parametrage\<env>.jsonl).
    .PARAMETER Id
        Une seule règle (champ Regle) ; absent : toutes (champ Regles).
    .OUTPUTS
        [pscustomobject] Succes, Etape, Message, Empreinte, Entete, Regles, Regle.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param([Parameter(Mandatory)] [string] $Fichier, [string] $Id)
    if (-not (Test-Path -LiteralPath $Fichier -PathType Leaf)) { return New-CopieApiResultat $false 'lecture' ('Fichier introuvable : ' + $Fichier) }
    $p = Read-CopieFichierParametrage -Chemin $Fichier
    if ($p.Erreurs.Count -gt 0 -or $null -eq $p.Entete) { return New-CopieApiResultat $false 'lecture' ('Fichier illisible : ' + ($p.Erreurs -join ' ; ')) }
    $regles = @($p.Regles | ForEach-Object { $c = $_.PSObject.Copy(); $c.PSObject.Properties.Remove('Ligne'); $c })
    $r = $null
    if ($Id) {
        $r = $regles | Where-Object { "$(Get-CopieValeur $_ 'id' '')".ToLowerInvariant() -eq $Id.ToLowerInvariant() } | Select-Object -First 1
        if ($null -eq $r) { return New-CopieApiResultat $false 'introuvable' ('Règle introuvable : ' + $Id) }
    }
    [pscustomobject]@{
        PSTypeName = 'Copie.ApiLecture'; Succes = $true; Etape = 'ok'; Message = 'ok'; VersionApi = $Script:VersionApi
        Empreinte = $p.Empreinte; Entete = $p.Entete; Regles = $regles; Regle = $r
    }
}
