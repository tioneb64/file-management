function New-CopieApiResultat {
    <#
    .SYNOPSIS
        Résultat commun à toutes les fonctions d'écriture de l'API.
    .PARAMETER Succes
        L'opération est terminée avec succès.
    .PARAMETER Etape
        ok, droits, configuration, lecture, version, conflit, introuvable, existe, invalide, moteur, refus, avertissements, ecriture.
    .PARAMETER Message
        Texte lisible.
    .PARAMETER Refus
        Refus du moteur (code, message).
    .PARAMETER Avertissements
        Avertissements du moteur.
    .PARAMETER Version
        Fichier de la version précédente conservée.
    .PARAMETER Empreinte
        Empreinte du nouveau fichier.
    .PARAMETER Regle
        Règle écrite (complète).
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param([bool] $Succes, [string] $Etape, [string] $Message, $Refus = @(), $Avertissements = @(), $Version = $null, $Empreinte = $null, $Regle = $null)
    [pscustomobject]@{
        PSTypeName = 'Copie.ApiResultat'; Succes = $Succes; Etape = $Etape; Message = $Message
        Refus = @($Refus); Avertissements = @($Avertissements); Version = $Version; Empreinte = $Empreinte; Regle = $Regle
        VersionApi = $Script:VersionApi
    }
}

function ConvertTo-CopieApiObjet {
    <#
    .SYNOPSIS
        Table de hachage, objet ou texte JSON -> objet JSON (pscustomobject) ; $null si illisible.
    .PARAMETER Valeur
        Entrée de l'appelant.
    #>
    [CmdletBinding()]
    param([AllowNull()] $Valeur)
    if ($null -eq $Valeur) { return $null }
    try {
        if ($Valeur -is [string]) { $o = $Valeur | ConvertFrom-Json }
        else { $o = $Valeur | ConvertTo-Json -Depth 10 | ConvertFrom-Json }
    }
    catch { return $null }
    if ($o -isnot [pscustomobject]) { return $null }
    $o
}

function Merge-CopieApiPatch {
    <#
    .SYNOPSIS
        Applique des modifications partielles à une règle : les objets sont fusionnés champ par champ, le reste est remplacé.
    .PARAMETER Base
        Règle actuelle.
    .PARAMETER Patch
        Champs à changer (ceux qui ne sont pas cités restent tels quels).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Base, [Parameter(Mandatory)] $Patch)
    $sortie = [ordered]@{}
    foreach ($p in $Base.PSObject.Properties) { $sortie[$p.Name] = $p.Value }
    foreach ($p in $Patch.PSObject.Properties) {
        $actuel = $sortie[$p.Name]
        if ($p.Value -is [pscustomobject] -and $actuel -is [pscustomobject]) { $sortie[$p.Name] = Merge-CopieApiPatch -Base $actuel -Patch $p.Value }
        else { $sortie[$p.Name] = $p.Value }
    }
    [pscustomobject]$sortie
}

function Write-CopieApiJournal {
    <#
    .SYNOPSIS
        Trace une action de l'API dans Journal.Dossier (ApiRegles_AAAA-MM-JJ.jsonl), si ce dossier est configuré et existe.
    .PARAMETER Config
        Configuration.
    .PARAMETER Donnees
        Champs tracés.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Config, [Parameter(Mandatory)] [hashtable] $Donnees)
    $dossier = "$($Config.Journal.Dossier)"
    if (-not $dossier -or -not (Test-Path -LiteralPath $dossier -PathType Container)) { return }
    try {
        $ligne = [ordered]@{ timestamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ'); service = 'file_management_api_regles' }
        foreach ($k in $Donnees.Keys) { $ligne[$k] = $Donnees[$k] }
        $chemin = Join-Path $dossier ('ApiRegles_{0}.jsonl' -f (Get-Date -Format 'yyyy-MM-dd'))
        [System.IO.File]::AppendAllText($chemin, (($ligne | ConvertTo-Json -Compress -Depth 6) + "`n"), (New-Object System.Text.UTF8Encoding($false)))
    }
    catch { $null = $_ }   # une panne de journal ne bloque jamais l'API
}

function Open-CopieApiContexte {
    <#
    .SYNOPSIS
        Charge la configuration et lit le modèle de règle du moteur ; vérifie les versions de format prises en charge.
    .PARAMETER Config
        Chemin de Gestion-Copie.config.psd1 (défaut : celui de l'interface).
    .OUTPUTS
        @{ Config; Modele } ou un résultat d'échec (Copie.ApiResultat).
    #>
    [CmdletBinding()]
    param([string] $Config)
    if (-not $Config) { $Config = $Script:ConfigurationParDefaut }
    try { $cfg = Get-CopieConfig -Chemin $Config }
    catch { return New-CopieApiResultat $false 'configuration' ('Configuration inutilisable : ' + $_.Exception.Message) }
    $reponse = Invoke-CopieMoteur -Config $cfg -Argument @('--modele-regle')
    if ($null -eq $reponse.Json) { return New-CopieApiResultat $false 'moteur' ('Modèle de règle du moteur illisible : ' + $reponse.Erreur) }
    if ($cfg.Parametrage.VersionsSupportees -notcontains [int]"$($reponse.Json.version_format)") {
        return New-CopieApiResultat $false 'version' ('Version de format du moteur non prise en charge : {0} (prises en charge : {1}).' -f $reponse.Json.version_format, ($cfg.Parametrage.VersionsSupportees -join ', '))
    }
    @{ Config = $cfg; Modele = $reponse.Json }
}

function Invoke-CopieApiModification {
    <#
    .SYNOPSIS
        Cœur de l'API : charge, contrôle les droits et la version, applique la transformation, enregistre par Save-CopieParametrage.

    .DESCRIPTION
        Mêmes garanties que l'interface : empreinte (conflit), brouillon, vérification du moteur
        (--verifier --syntaxe-seule --precedent), version conservée avec fiche, File.Replace atomique.
        Sans -Empreinte, une modification concurrente est absorbée par une relecture (jusqu'à 3 essais) ;
        avec -Empreinte (celle lue avant), le moindre écart est un conflit rendu à l'appelant.

    .PARAMETER Fichier
        Fichier de paramétrage (parametrage\<env>.jsonl).
    .PARAMETER Config
        Chemin de Gestion-Copie.config.psd1.
    .PARAMETER Transformer
        Scriptblock(param($Regles, $Modele, $Argument)) renvoyant @{ Regles; Id; Regle } ou un résultat d'échec (Copie.ApiResultat).
    .PARAMETER Argument
        Données passées au scriptblock (il ne voit pas les variables de l'appelant ni les fonctions privées en tant que fermeture).
    .PARAMETER Action
        Nom de l'action tracée.
    .PARAMETER Commentaire
        Commentaire de la version (obligatoire).
    .PARAMETER Appelant
        Nom du programme appelant, tracé.
    .PARAMETER Empreinte
        Empreinte attendue (concurrence optimiste).
    .PARAMETER AccepterAvertissements
        Enregistre malgré les avertissements du moteur.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)] [string] $Fichier,
        [string] $Config,
        [Parameter(Mandatory)] [scriptblock] $Transformer,
        [hashtable] $Argument = @{},
        [Parameter(Mandatory)] [string] $Action,
        [string] $Commentaire,
        [string] $Appelant,
        [string] $Empreinte,
        [switch] $AccepterAvertissements
    )
    if (-not "$Commentaire".Trim()) { return New-CopieApiResultat $false 'invalide' 'Commentaire obligatoire : il est tracé avec la version.' }
    $contexte = Open-CopieApiContexte -Config $Config
    if ($contexte -is [pscustomobject]) { return $contexte }
    $cfg = $contexte.Config
    if ((Get-CopieProfilAcces -Config $cfg) -ne 'Admin') {
        return New-CopieApiResultat $false 'droits' 'Le compte courant n''appartient pas à Acces.GroupesAdmin : modification refusée.'
    }
    $compte = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $libelle = $(if ($Appelant) { "[API $Appelant] $($Commentaire.Trim())" } else { "[API] $($Commentaire.Trim())" })
    $accord = $AccepterAvertissements.IsPresent
    $confirmer = { param($avertissements) $null = $avertissements; $accord }.GetNewClosure()

    $res = $null
    $t = $null
    for ($essai = 1; $essai -le 3; $essai++) {
        if (-not (Test-Path -LiteralPath $Fichier -PathType Leaf)) { return New-CopieApiResultat $false 'lecture' ('Fichier introuvable : ' + $Fichier) }
        $p = Read-CopieFichierParametrage -Chemin $Fichier
        if ($p.Erreurs.Count -gt 0 -or $null -eq $p.Entete) { return New-CopieApiResultat $false 'lecture' ('Fichier illisible : ' + ($p.Erreurs -join ' ; ')) }
        $version = Get-CopieValeur $p.Entete 'version'
        if ($null -eq $version -or $cfg.Parametrage.VersionsSupportees -notcontains [int]"$version") {
            return New-CopieApiResultat $false 'version' ('Version de format du fichier non prise en charge : {0} (prises en charge : {1}).' -f $version, ($cfg.Parametrage.VersionsSupportees -join ', '))
        }
        if ($Empreinte -and $Empreinte -ne $p.Empreinte) {
            return New-CopieApiResultat $false 'conflit' 'Le fichier a changé depuis la lecture dont vient l''empreinte : rien n''a été enregistré. Relisez-le.'
        }
        $t = & $Transformer $p.Regles $contexte.Modele.regle $Argument
        if ($t -is [pscustomobject] -and $t.PSObject.TypeNames -contains 'Copie.ApiResultat') { return $t }

        $res = Save-CopieParametrage -Config $cfg -Fichier $Fichier -EmpreinteAttendue $p.Empreinte -Entete $p.Entete `
            -Regle @($t.Regles) -Compte $compte -Commentaire $libelle -Confirmer $confirmer
        if ($res.Etape -eq 'conflit' -and -not $Empreinte -and $essai -lt 3) { continue }
        break
    }
    Write-CopieApiJournal -Config $cfg -Donnees @{
        action = $Action; regle = $t.Id; fichier = $Fichier; appelant = $Appelant; compte = $compte
        etape = $res.Etape; succes = [bool]$res.Enregistre; commentaire = $Commentaire
    }
    $message = $res.Message
    if ($res.Enregistre) { $message = '{0} : {1} enregistré.' -f $Action, $t.Id }
    New-CopieApiResultat ([bool]$res.Enregistre) $res.Etape $message $res.Refus $res.Avertissements $res.Version $res.Empreinte $t.Regle
}
