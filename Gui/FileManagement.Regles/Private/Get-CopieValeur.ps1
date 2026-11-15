function Get-CopieValeur {
    <#
    .SYNOPSIS
        Lit une propriété d'un objet JSON sans échouer si elle est absente (le fichier peut omettre des champs).
    .PARAMETER Objet
        Objet issu de ConvertFrom-Json (ou $null).
    .PARAMETER Nom
        Nom de la propriété.
    .PARAMETER Defaut
        Valeur renvoyée si l'objet ou la propriété est absent.
    #>
    [CmdletBinding()]
    param(
        [AllowNull()] $Objet,
        [Parameter(Mandatory)][string] $Nom,
        $Defaut = $null
    )
    if ($null -eq $Objet) { return $Defaut }
    $prop = $Objet.PSObject.Properties[$Nom]
    if ($null -eq $prop) { return $Defaut }
    $prop.Value
}
