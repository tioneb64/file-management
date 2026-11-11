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

function Format-CopieDate {
    <#
    .SYNOPSIS
        Secondes depuis 1970 (UTC, contrat du moteur) -> date locale lisible ; « — » si absente.
    .PARAMETER Secondes
        Entier ou $null.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([AllowNull()] $Secondes)
    if ($null -eq $Secondes -or "$Secondes" -eq '') { return [string][char]0x2014 }
    $utc = [DateTimeOffset]::FromUnixTimeSeconds([long]$Secondes)
    $utc.LocalDateTime.ToString('dd/MM/yyyy HH:mm:ss')
}

function Format-CopieDuree {
    <#
    .SYNOPSIS
        Durée en secondes -> texte lisible (« 90 s », « 5 min », « 1 h 30 »).
    .PARAMETER Secondes
        Nombre de secondes.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)][long] $Secondes)
    if ($Secondes -lt 60) { return ('{0} s' -f $Secondes) }
    if ($Secondes % 86400 -eq 0) { return ('{0} j' -f ($Secondes / 86400)) }
    if ($Secondes % 3600 -eq 0) { return ('{0} h' -f ($Secondes / 3600)) }
    if ($Secondes -ge 3600) {
        $h = [math]::Floor($Secondes / 3600)
        $m = [math]::Floor(($Secondes % 3600) / 60)
        if ($Secondes % 60 -eq 0) { return ('{0} h {1:00}' -f $h, $m) }
    }
    if ($Secondes % 60 -eq 0) { return ('{0} min' -f ($Secondes / 60)) }
    '{0} s' -f $Secondes
}

function Format-CopiePlanification {
    <#
    .SYNOPSIS
        Planification d'une règle (objet du fichier) en clair, comme le fait le moteur (--etat).
    .DESCRIPTION
        Sert seulement quand l'état du moteur n'est pas disponible (base non initialisée, moteur
        injoignable) : sinon l'interface affiche le texte calculé par le moteur.
    .PARAMETER Planification
        Objet « planification » de la règle, ou $null.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([AllowNull()] $Planification)
    if ($null -eq $Planification) { return 'non planifiée' }
    $type = "$(Get-CopieValeur $Planification 'type')"
    $jours = "$(Get-CopieValeur $Planification 'jours' 'tous')"
    $joursTexte = $(if ($jours -eq 'tous') { 'tous les jours' } else { $jours })
    switch ($type) {
        'intervalle' {
            $frequence = Format-CopieDuree -Secondes ([long](Get-CopieValeur $Planification 'frequence_sec' 0))
            return ('toutes les {0} de {1} à {2}, {3}' -f $frequence, (Get-CopieValeur $Planification 'debut' '?'),
                (Get-CopieValeur $Planification 'fin' '?'), $joursTexte)
        }
        'quotidien' { return ('à {0}, {1}' -f (Get-CopieValeur $Planification 'heure' '?'), $joursTexte) }
        'apres_dependances' { return 'après ses dépendances' }
        default { return ('planification « {0} »' -f $type) }
    }
}

function Get-CopieCouleurStatut {
    <#
    .SYNOPSIS
        Couleur d'affichage (#RRGGBB) d'un statut de règle.
    .PARAMETER Statut
        JAMAIS_LANCEE, SUCCES, WARNING, ERREUR, ATTENTE, ACQUITTEE, ARRETEE, EN_COURS, EN_ATTENTE, BLOQUEE, INACTIVE.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([AllowNull()][string] $Statut)
    switch ($Statut) {
        'SUCCES' { '#2E7D32' }
        'WARNING' { '#C77700' }
        'ERREUR' { '#C0392B' }
        'ARRETEE' { '#8E2A1F' }
        'ACQUITTEE' { '#1B7F7A' }
        'ATTENTE' { '#2C7DA0' }
        'EN_COURS' { '#1F6FB2' }
        'EN_ATTENTE' { '#6A5ACD' }
        'BLOQUEE' { '#8E44AD' }
        default { '#7A8796' }       # JAMAIS_LANCEE, INACTIVE, inconnu
    }
}
