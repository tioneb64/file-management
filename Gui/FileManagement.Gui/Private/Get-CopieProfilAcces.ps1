function Get-CopieProfilAcces {
    <#
    .SYNOPSIS
        Profil de l'utilisateur courant : Admin (modification) ou Lecture (consultation).

    .DESCRIPTION
        Admin si l'utilisateur appartient à l'un des groupes de Acces.GroupesAdmin, d'après les groupes
        du jeton Windows (groupes imbriqués compris, sans le module ActiveDirectory). Une entrée de la
        configuration s'écrit « DOMAINE\Groupe » (comparée au nom complet), « Groupe » (comparée au
        nom sans domaine) ou un SID. La casse ne compte pas. Un SID orphelin du jeton est ignoré.

        Ce profil ne protège rien seul : les droits NTFS du dossier de paramétrage et le point
        d'accès distant limitent aussi l'écriture aux administrateurs (docs/04-frontend.md §7).

    .PARAMETER Config
        Configuration (Get-CopieConfig).

    .PARAMETER Groupe
        Noms (DOMAINE\Groupe) et SID des groupes de l'utilisateur. Par défaut : ceux du jeton courant.

    .OUTPUTS
        [string] Admin ou Lecture.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [pscustomobject] $Config,

        [AllowEmptyCollection()]
        [string[]] $Groupe
    )

    if (-not $PSBoundParameters.ContainsKey('Groupe')) {
        $Groupe = @(foreach ($sid in @([Security.Principal.WindowsIdentity]::GetCurrent().Groups)) {
                $sid.Value
                try { $sid.Translate([Security.Principal.NTAccount]).Value }
                catch { $null = $_ }   # SID orphelin (groupe supprimé) : ignoré
            })
    }
    $complets = @($Groupe | Where-Object { $_ })
    $courts = @($complets | ForEach-Object { ($_ -split '\\')[-1] })

    foreach ($entree in $Config.Acces.GroupesAdmin) {
        if ($entree -like '*\*') { $trouve = $complets -contains $entree }
        elseif ($entree -match '^S-\d-') { $trouve = $complets -contains $entree }
        else { $trouve = $courts -contains $entree }
        if ($trouve) { return 'Admin' }
    }
    'Lecture'
}
