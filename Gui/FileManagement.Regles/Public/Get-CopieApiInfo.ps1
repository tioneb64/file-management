function Get-CopieApiInfo {
    <#
    .SYNOPSIS
        Versions de l'API et du format de règle du moteur : à lire avant d'écrire, pour refuser un format inconnu.
    .PARAMETER Config
        Chemin de Gestion-Copie.config.psd1 (défaut : celui de l'interface).
    .OUTPUTS
        [pscustomobject] Succes, VersionApi, VersionFormat (moteur), VersionsSupportees, Message.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param([string] $Config)
    $contexte = Open-CopieApiContexte -Config $Config
    if ($contexte -is [pscustomobject]) { return $contexte }
    [pscustomobject]@{
        PSTypeName = 'Copie.ApiInfo'; Succes = $true; Etape = 'ok'; Message = 'ok'; VersionApi = $Script:VersionApi
        VersionFormat = [int]$contexte.Modele.version_format; VersionsSupportees = @($contexte.Config.Parametrage.VersionsSupportees)
    }
}
