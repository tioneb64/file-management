function Get-CopieErreurDelaiUnique {
    <#
    .SYNOPSIS
        Contrôle du délai d'une planification « unique » (OneShot) : au moins deux périodes du déclencheur avant la date.

    .DESCRIPTION
        Le moteur ne démarre une règle unique que s'il l'a vue avant sa date : sinon, à son premier passage, la date est déjà
        passée, la règle est « nouvelle » donc considérée comme manquée et ne part jamais. Il faut donc au moins deux périodes
        du déclencheur Jenkins (Parametrage.PeriodeDeclencheurSec) entre maintenant et la date.
        Ce contrôle est UNIQUE : l'interface (formulaire de règle) et l'API de règles l'appellent. Une date illisible n'est pas
        jugée ici (le formulaire et le moteur la refusent : P01).
        La date d'une règle déjà jouée et non modifiée n'est pas refusée (-Initiale) : on peut modifier le reste de la règle.

    .PARAMETER Planification
        Objet planification de la règle.
    .PARAMETER PeriodeSec
        Période du déclencheur Jenkins, en secondes (défaut 300).
    .PARAMETER Initiale
        Date actuelle de la règle (texte) en cas de modification ; $null pour une nouvelle règle.
    .PARAMETER Maintenant
        Instant de référence (tests).

    .OUTPUTS
        $null si la date convient (ou n'est pas une planification unique) ; sinon [pscustomobject] Message, DateMinimale (AAAA-MM-JJ HH:MM).
    #>
    [CmdletBinding()]
    param(
        [AllowNull()] $Planification,
        [int] $PeriodeSec = 300,
        [AllowNull()] [string] $Initiale,
        [datetime] $Maintenant = (Get-Date)
    )
    if ("$(Get-CopieValeur $Planification 'type' '')" -ne 'unique') { return $null }
    $texte = "$(Get-CopieValeur $Planification 'date_heure' '')".Trim()
    if (-not $texte) { return $null }
    $invariant = [System.Globalization.CultureInfo]::InvariantCulture
    $date = [datetime]::MinValue
    if (-not [datetime]::TryParseExact($texte, [string[]]@('yyyy-MM-dd HH:mm', 'yyyy-MM-ddTHH:mm'), $invariant, [System.Globalization.DateTimeStyles]::None, [ref]$date)) { return $null }
    $limite = $Maintenant.AddSeconds(2 * $PeriodeSec)
    if ($date -gt $limite) { return $null }
    if ($Initiale -and $texte -eq "$Initiale".Trim()) { return $null }
    $minimale = $limite.ToString('yyyy-MM-dd HH:mm', $invariant)
    [pscustomobject]@{
        Message       = ("Date et heure de lancement : au moins {0} min d'avance (deux fois la période du déclencheur Jenkins) : le moteur doit voir la règle avant sa date, sinon elle est considérée comme manquée et ne part pas. Date minimale : {1}." -f [math]::Ceiling(2 * $PeriodeSec / 60), $minimale)
        DateMinimale  = $minimale
    }
}
