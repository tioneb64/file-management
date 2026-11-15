function Get-CopieApiModele {
    <#
    .SYNOPSIS
        Règle par défaut du moteur (tous les champs et leurs valeurs de secours) : le format de référence.

    .DESCRIPTION
        Sert à connaître les champs valides. Il n'est pas nécessaire de la fournir à Add-CopieApiRegle :
        l'API complète elle-même les champs absents avec ces valeurs.

    .PARAMETER Config
        Chemin de Gestion-Copie.config.psd1 (défaut : celui de l'interface).
    .OUTPUTS
        [pscustomobject] Succes, VersionFormat, Regle (le modèle).
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param([string] $Config)
    $contexte = Open-CopieApiContexte -Config $Config
    if ($contexte -is [pscustomobject]) { return $contexte }
    [pscustomobject]@{
        PSTypeName = 'Copie.ApiModele'; Succes = $true; Etape = 'ok'; Message = 'ok'; VersionApi = $Script:VersionApi
        VersionFormat = [int]$contexte.Modele.version_format; Regle = $contexte.Modele.regle
    }
}
