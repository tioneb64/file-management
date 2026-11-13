# Module du point d'accès JEA de file_management : la seule fonction visible dans la session JEA.
#
# Contrat (docs/04-frontend.md §6) : Invoke-CopieMoteurJea -Argument <string[]> -Fichier <chemin> lance le
# moteur (python -m file_management) avec le compte de la session (compte virtuel ou compte de service géré) et
# renvoie Code, Sortie (le JSON du moteur) et Erreur. Tout ce qui n'est pas dans la grammaire ci-dessous
# est refusé AVANT le lancement : le point d'accès n'est pas un moyen d'exécuter autre chose que le moteur.

Set-StrictMode -Version 2.0

$Script:CheminConfig = Join-Path $PSScriptRoot 'FileManagement.Jea.config.psd1'

# Types de valeurs : expression régulière que la valeur doit respecter en entier.
$Script:Types = @{
    id          = '^[A-Za-z0-9_-]{1,64}$'                  # identifiant de règle (RE_ID du moteur)
    cle         = '^[0-9A-Fa-f]{1,128}$'                   # clé hexadécimale d'une livraison incertaine
    decision    = '^(livre|a_relivrer)$'
    utilisateur = '^[^\x00-\x1F]{1,256}$'
    texte       = '^[^\x00-\x08\x0B\x0C\x0E-\x1F]{1,2000}$'  # commentaire (retours à la ligne permis)
    chemin      = '^[^\x00-\x1F<>|?*]{1,520}$'
    dossierparam = '^[^\x00-\x1F<>|?*]{1,520}$'               # le dossier de paramétrage lui-même (index des outils d'un brouillon), jamais un autre
    cheminlibre = '^[^\x00-\x1F<>|?*]{1,520}$'                # chemin choisi par l'administrateur (dossier des outils) : non limité au dossier de paramétrage
}

# Grammaire : commande -> droit, type de la valeur de la commande (vide : aucune), besoin du fichier de
# paramétrage, options permises (nom -> type de valeur, ou 'interrupteur').
$Script:Grammaire = @{
    '--etat'               = @{ Droit = 'lecture'; Valeur = ''; Fichier = $true; Options = @{ '--regle' = 'id' } }
    '--verifier'           = @{ Droit = 'lecture'; Valeur = ''; Fichier = $true; Options = @{ '--syntaxe-seule' = 'interrupteur'; '--precedent' = 'chemin'; '--dossier-parametrage' = 'dossierparam' } }
    '--modele-regle'       = @{ Droit = 'lecture'; Valeur = ''; Fichier = $false; Options = @{} }
    # Parcourt un dossier choisi par l'administrateur (hors dossier de paramétrage) : droit d'écriture, donc compte tracé.
    '--scanner-outils'     = @{ Droit = 'ecriture'; Valeur = ''; Fichier = $false; Options = @{ '--dossier-outils' = 'cheminlibre'; '--utilisateur' = 'utilisateur' } }
    '--reprise'            = @{ Droit = 'ecriture'; Valeur = 'id'; Fichier = $true; Options = @{ '--utilisateur' = 'utilisateur'; '--commentaire' = 'texte' } }
    '--lancer-maintenant'  = @{ Droit = 'ecriture'; Valeur = 'id'; Fichier = $true; Options = @{ '--utilisateur' = 'utilisateur'; '--commentaire' = 'texte' } }
    '--acquitter'          = @{ Droit = 'ecriture'; Valeur = 'id'; Fichier = $true; Options = @{ '--utilisateur' = 'utilisateur'; '--commentaire' = 'texte' } }
    '--debloquer'          = @{ Droit = 'ecriture'; Valeur = 'id'; Fichier = $true; Options = @{ '--utilisateur' = 'utilisateur'; '--commentaire' = 'texte' } }
    '--purger'             = @{ Droit = 'ecriture'; Valeur = ''; Fichier = $true; Options = @{ '--regle' = 'id'; '--appliquer' = 'interrupteur' } }
    '--lancer-regle'       = @{ Droit = 'lecture'; Valeur = 'id'; Fichier = $true; Exige = '--simulation'; Options = @{ '--simulation' = 'interrupteur' } }
    '--controler-regle'    = @{ Droit = 'lecture'; Valeur = 'id'; Fichier = $true; Options = @{} }
    '--creer-dossiers-regle' = @{ Droit = 'ecriture'; Valeur = 'id'; Fichier = $true; Options = @{ '--utilisateur' = 'utilisateur'; '--commentaire' = 'texte' } }
    '--initialiser-base'   = @{ Droit = 'ecriture'; Valeur = ''; Fichier = $true; Options = @{ '--utilisateur' = 'utilisateur'; '--commentaire' = 'texte' } }
    '--renommer-environnement' = @{ Droit = 'ecriture'; Valeur = 'id'; Fichier = $true; Options = @{ '--utilisateur' = 'utilisateur'; '--commentaire' = 'texte' } }
    '--trancher-incertain' = @{ Droit = 'ecriture'; Valeur = 'cle'; Fichier = $true; Options = @{ '--decision' = 'decision'; '--utilisateur' = 'utilisateur'; '--commentaire' = 'texte' } }
}

function Get-CopieJeaConfig {
    <#
    .SYNOPSIS
        Lit et valide la configuration du point d'accès (écrite par Installer-PointAccesJea.ps1).
    #>
    [CmdletBinding()]
    param()
    if (-not (Test-Path -LiteralPath $Script:CheminConfig -PathType Leaf)) { throw "configuration du point d'accès introuvable : $Script:CheminConfig" }
    $c = Import-PowerShellDataFile -LiteralPath $Script:CheminConfig
    foreach ($cle in 'Python', 'Racine', 'DossierParametrage') {
        if (-not $c.ContainsKey($cle) -or -not "$($c[$cle])".Trim()) { throw "configuration du point d'accès : '$cle' manquant" }
    }
    $delai = 600
    if ($c.ContainsKey('DelaiMaxSec')) { $delai = [int]$c['DelaiMaxSec'] }
    $groupe = ''
    if ($c.ContainsKey('GroupeAdmin')) { $groupe = "$($c['GroupeAdmin'])".Trim() }
    [pscustomobject]@{ Python = "$($c['Python'])"; Racine = "$($c['Racine'])"; DossierParametrage = "$($c['DossierParametrage'])"; DelaiMaxSec = $delai; GroupeAdmin = $groupe }
}

function Get-CopieJeaIdentite {
    <#
    .SYNOPSIS
        Compte qui a ouvert la session JEA et test d'appartenance à un groupe ($null hors session distante).
    #>
    [CmdletBinding()]
    param()
    $v = Get-Variable -Name PSSenderInfo -Scope Global -ErrorAction SilentlyContinue
    if ($null -eq $v -or $null -eq $v.Value) { return $null }
    $info = $v.Value
    $principal = $null
    try { $principal = New-Object System.Security.Principal.WindowsPrincipal($info.UserInfo.WindowsIdentity) } catch { $principal = $null }
    [pscustomobject]@{ Compte = "$($info.ConnectedUser)"; Principal = $principal }
}

function Test-CopieJeaChemin {
    <#
    .SYNOPSIS
        Vrai si le chemin est dans le dossier de paramétrage (après normalisation : « .. » ne s'échappe pas).
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param([Parameter(Mandatory)] [string] $Chemin, [Parameter(Mandatory)] [string] $Dossier)
    try {
        $complet = [System.IO.Path]::GetFullPath($Chemin)
        $base = [System.IO.Path]::GetFullPath($Dossier).TrimEnd('\') + '\'
    }
    catch { return $false }
    $complet.StartsWith($base, [System.StringComparison]::OrdinalIgnoreCase)
}

function ConvertTo-CopieJeaLigne {
    <#
    .SYNOPSIS
        Valide les arguments contre la grammaire et construit la ligne du moteur.
    .DESCRIPTION
        Renvoie @{ Erreur = '' ; Arguments = string[] ; Droit = 'lecture|ecriture' }. Les valeurs sont
        passées sous la forme --option=valeur : une valeur qui commence par un tiret n'est jamais prise
        pour une option.
    #>
    [CmdletBinding()]
    param(
        [AllowEmptyCollection()] [string[]] $Argument,
        [string] $Fichier,
        [Parameter(Mandatory)] $Config,
        [string] $Utilisateur
    )
    $refus = { param($texte) @{ Erreur = $texte; Arguments = @(); Droit = '' } }
    $jetons = @($Argument)
    if ($jetons.Count -eq 0) { return (& $refus 'aucune commande') }
    $commande = $jetons[0]
    if (-not $Script:Grammaire.ContainsKey($commande)) { return (& $refus ("commande non permise : {0}" -f $commande)) }
    $regle = $Script:Grammaire[$commande]
    $lignes = New-Object System.Collections.Generic.List[string]
    $lignes.Add('-m'); $lignes.Add('file_management')
    if ($regle.Fichier) {
        if (-not $Fichier) { return (& $refus 'le fichier de paramétrage est obligatoire pour cette commande') }
        if ($Fichier -notmatch $Script:Types.chemin -or -not (Test-CopieJeaChemin -Chemin $Fichier -Dossier $Config.DossierParametrage)) {
            return (& $refus 'fichier de paramétrage hors du dossier autorisé')
        }
        $lignes.Add('--config=' + [System.IO.Path]::GetFullPath($Fichier))
    }
    $i = 1
    if ($regle.Valeur) {
        if ($jetons.Count -lt 2 -or $jetons[1] -notmatch $Script:Types[$regle.Valeur]) { return (& $refus ("valeur incorrecte pour {0}" -f $commande)) }
        $lignes.Add($commande + '=' + $jetons[1])
        $i = 2
    }
    else { $lignes.Add($commande) }
    $vues = @{}
    $aUtilisateur = $false
    while ($i -lt $jetons.Count) {
        $nom = $jetons[$i]
        if (-not $regle.Options.ContainsKey($nom)) { return (& $refus ("option non permise avec {0} : {1}" -f $commande, $nom)) }
        if ($vues.ContainsKey($nom)) { return (& $refus ("option répétée : {0}" -f $nom)) }
        $vues[$nom] = $true
        $type = $regle.Options[$nom]
        if ($type -eq 'interrupteur') { $lignes.Add($nom); $i++; continue }
        if ($i + 1 -ge $jetons.Count) { return (& $refus ("valeur manquante pour {0}" -f $nom)) }
        $valeur = $jetons[$i + 1]
        if ($nom -eq '--utilisateur') { $aUtilisateur = $true; $valeur = $(if ($Utilisateur) { $Utilisateur } else { $valeur }) }
        if ($valeur -notmatch $Script:Types[$type]) { return (& $refus ("valeur incorrecte pour {0}" -f $nom)) }
        if ($type -eq 'chemin' -and -not (Test-CopieJeaChemin -Chemin $valeur -Dossier $Config.DossierParametrage)) { return (& $refus ('fichier hors du dossier autorisé : {0}' -f $nom)) }
        if ($type -eq 'dossierparam') {
            try { $egal = [System.IO.Path]::GetFullPath($valeur).TrimEnd('\') -ieq [System.IO.Path]::GetFullPath($Config.DossierParametrage).TrimEnd('\') } catch { $egal = $false }
            if (-not $egal) { return (& $refus ('dossier hors du dossier autorisé : {0}' -f $nom)) }
        }
        $lignes.Add($nom + '=' + $valeur)
        $i += 2
    }
    if ($regle.ContainsKey('Exige') -and -not $vues.ContainsKey($regle.Exige)) { return (& $refus ('{0} exige {1} (le point d''accès ne lance pas de transfert réel)' -f $commande, $regle.Exige)) }
    if ($regle.Droit -eq 'ecriture' -and -not $aUtilisateur) {
        # Le moteur exige --utilisateur : on le fournit (c'est le compte de la session, jamais une saisie).
        if (-not $Utilisateur) { return (& $refus '--utilisateur est obligatoire') }
        $lignes.Add('--utilisateur=' + $Utilisateur)
    }
    $lignes.Add('--format=json')
    @{ Erreur = ''; Arguments = $lignes.ToArray(); Droit = $regle.Droit }
}

function Invoke-CopieMoteurJea {
    <#
    .SYNOPSIS
        Lance le moteur file_management pour le front-end (seule fonction exposée par le point d'accès JEA).

    .DESCRIPTION
        Refuse toute commande ou option hors de la grammaire du contrat (docs/07 §4). Pour les commandes
        d'écriture, l'appelant doit appartenir au groupe administrateur de la configuration. L'utilisateur
        tracé par le moteur est le compte qui a ouvert la session (--utilisateur du front-end est ignoré
        quand la session le connaît). Le fichier de paramétrage doit être dans le dossier de paramétrage.

    .PARAMETER Argument
        Arguments de la commande, sans --config ni --format (par exemple '--etat').

    .PARAMETER Fichier
        Fichier de paramétrage (absent pour --modele-regle).

    .OUTPUTS
        [pscustomobject] Code (-1 : refusé ou non lancé), Sortie (JSON du moteur), Erreur.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)] [AllowEmptyCollection()] [string[]] $Argument,
        [string] $Fichier = ''
    )
    $non = { param($texte) [pscustomobject]@{ Code = -1; Sortie = ''; Erreur = ("Refusé par le point d'accès JEA : " + $texte) } }
    try { $config = Get-CopieJeaConfig } catch { return (& $non $_.Exception.Message) }
    $identite = Get-CopieJeaIdentite
    $compte = ''
    if ($null -ne $identite) { $compte = $identite.Compte }
    $ligne = ConvertTo-CopieJeaLigne -Argument $Argument -Fichier $Fichier -Config $config -Utilisateur $compte
    if ($ligne.Erreur) { return (& $non $ligne.Erreur) }
    if ($ligne.Droit -eq 'ecriture' -and $null -ne $identite) {
        $membre = $false
        if ($config.GroupeAdmin -and $null -ne $identite.Principal) {
            try { $membre = $identite.Principal.IsInRole($config.GroupeAdmin) } catch { $membre = $false }
        }
        if (-not $membre) { return (& $non 'commande réservée aux administrateurs') }
    }

    $citer = {
        param([string] $texte)
        if ($texte -eq '') { return '""' }
        if ($texte -notmatch '[\s"]') { return $texte }
        $s = [regex]::Replace($texte, '(\\*)"', '$1$1\"')
        $s = [regex]::Replace($s, '(\\+)$', '$1$1')
        '"' + $s + '"'
    }
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $config.Python
    $info.Arguments = (@($ligne.Arguments | ForEach-Object { & $citer $_ }) -join ' ')
    $info.WorkingDirectory = $config.Racine
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $info.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $processus = New-Object System.Diagnostics.Process
    $processus.StartInfo = $info
    try { $null = $processus.Start() }
    catch { return [pscustomobject]@{ Code = -1; Sortie = ''; Erreur = ('lancement impossible : ' + $_.Exception.Message) } }
    $sortie = $processus.StandardOutput.ReadToEndAsync()
    $erreur = $processus.StandardError.ReadToEndAsync()
    if (-not $processus.WaitForExit($config.DelaiMaxSec * 1000)) {
        try { $processus.Kill() } catch { $null = $_ }
        return [pscustomobject]@{ Code = -1; Sortie = ''; Erreur = ('délai de {0} s dépassé, processus arrêté' -f $config.DelaiMaxSec) }
    }
    $processus.WaitForExit()
    [pscustomobject]@{ Code = $processus.ExitCode; Sortie = $sortie.Result; Erreur = $erreur.Result }
}

function Invoke-CopieDossiersJea {
    <#
    .SYNOPSIS
        Contrôle ou crée les dossiers techniques d'un environnement (base, journaux, travail) avec le compte du point d'accès.

    .DESCRIPTION
        Les chemins ne sont JAMAIS fournis par l'appelant : ils sont lus dans l'en-tête du fichier de paramétrage, qui doit
        être dans le dossier de paramétrage autorisé. Le contrôle est une lecture ; la création est réservée au groupe
        administrateur de la configuration. Même logique que Get-CopieBlocDossiers du module de l'interface (à garder identique).

    .PARAMETER Action
        controler ou creer.

    .PARAMETER Fichier
        Fichier de paramétrage de l'environnement.

    .OUTPUTS
        [pscustomobject] Code (0 : fait, -1 : refusé ou en erreur), Dossiers, Erreur.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)] [ValidateSet('controler', 'creer')] [string] $Action,
        [Parameter(Mandatory)] [string] $Fichier
    )
    $non = { param($texte) [pscustomobject]@{ Code = -1; Dossiers = @(); Erreur = ("Refusé par le point d'accès JEA : " + $texte) } }
    try { $config = Get-CopieJeaConfig } catch { return (& $non $_.Exception.Message) }
    if ($Fichier -notmatch $Script:Types.chemin -or -not (Test-CopieJeaChemin -Chemin $Fichier -Dossier $config.DossierParametrage)) {
        return (& $non 'fichier de paramétrage hors du dossier autorisé')
    }
    if (-not (Test-Path -LiteralPath $Fichier -PathType Leaf)) { return (& $non 'fichier de paramétrage introuvable') }
    if ($Action -eq 'creer') {
        $identite = Get-CopieJeaIdentite
        if ($null -ne $identite) {
            $membre = $false
            if ($config.GroupeAdmin -and $null -ne $identite.Principal) {
                try { $membre = $identite.Principal.IsInRole($config.GroupeAdmin) } catch { $membre = $false }
            }
            if (-not $membre) { return (& $non 'commande réservée aux administrateurs') }
        }
    }
    $bloc = {
        param([string] $Action, [string] $Fichier)
        $essai = {
            param([string] $dossier)
            $f = Join-Path $dossier ('.test_ecriture_' + [System.Diagnostics.Process]::GetCurrentProcess().Id)
            try { [System.IO.File]::WriteAllText($f, 'x'); Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue; $true }
            catch { $false }
        }
        $en = $null
        try {
            $premiere = (Get-Content -LiteralPath $Fichier -Encoding UTF8 -TotalCount 1)
            $en = $premiere | ConvertFrom-Json
        }
        catch { throw ('en-tête du fichier illisible : ' + $_.Exception.Message) }
        $lire = { param($nom) $p = $en.PSObject.Properties[$nom]; if ($null -ne $p -and "$($p.Value)".Trim()) { "$($p.Value)".Trim() } else { '' } }
        # Racine de l'environnement : un chemin partiel (BDD\preprod.db, LOGS, TMP) se place dessous, un chemin complet reste tel quel.
        $racineEnv = & $lire 'racine'
        $complet = {
            param([string] $chemin)
            if (-not $chemin -or -not $racineEnv -or $chemin -match '^([A-Za-z]:[\\/]|\\\\[^\\]|//[^/])') { return $chemin }
            [System.IO.Path]::Combine($racineEnv.TrimEnd('\', '/'), $chemin.TrimStart('\', '/'))
        }
        $base = & $complet (& $lire 'base')
        if (-not $base) { throw 'l''en-tête ne contient pas de chemin de base' }
        $racine = [System.IO.Path]::GetDirectoryName($base)
        $logs = & $complet (& $lire 'dossier_logs')
        if (-not $logs) { $logs = [System.IO.Path]::Combine($racine, 'logs') }
        $travail = & $complet (& $lire 'dossier_travail')
        if (-not $travail) { $travail = [System.IO.Path]::Combine($racine, 'travail') }
        $sortie = New-Object System.Collections.Generic.List[object]
        foreach ($d in @(@('base', $racine), @('journaux', $logs), @('travail', $travail))) {
            $role = $d[0]
            $chemin = $d[1]
            try { $chemin = [System.IO.Path]::GetFullPath($chemin) } catch { $null = $_ }
            $ligne = [pscustomobject]@{ Role = $role; Chemin = $chemin; Existe = $false; Ecriture = $false; ACreer = $false; Cree = $false; Erreur = '' }
            if (Test-Path -LiteralPath $chemin -PathType Container) {
                $ligne.Existe = $true
                $ligne.Ecriture = [bool](& $essai $chemin)
            }
            elseif (Test-Path -LiteralPath $chemin) { $ligne.Erreur = 'un fichier porte ce nom' }
            else {
                $parent = $chemin
                while ($parent -and -not (Test-Path -LiteralPath $parent -PathType Container)) { $parent = [System.IO.Path]::GetDirectoryName($parent) }
                if (-not $parent) { $ligne.Erreur = 'lecteur ou partage introuvable' }
                elseif (& $essai $parent) { $ligne.ACreer = $true }
                else { $ligne.Erreur = ('pas de droit d''écriture dans ' + $parent) }
            }
            if ($Action -eq 'creer' -and $ligne.ACreer) {
                try {
                    $null = New-Item -ItemType Directory -Path $chemin -Force -ErrorAction Stop
                    $ligne.Cree = $true
                    $ligne.Existe = $true
                    $ligne.ACreer = $false
                    $ligne.Ecriture = [bool](& $essai $chemin)
                }
                catch { $ligne.Erreur = $_.Exception.Message }
            }
            $sortie.Add($ligne)
        }
        # Un même dossier peut revenir deux fois (base, logs et travail dans le même dossier) : on ne le garde qu'une fois.
        $vus = @{}
        foreach ($l in $sortie) {
            $cle = $l.Chemin.ToLowerInvariant()
            if ($vus.ContainsKey($cle)) { continue }
            $vus[$cle] = $true
            $l
        }
    }

    try { $dossiers = @(& $bloc $Action ([System.IO.Path]::GetFullPath($Fichier))) }
    catch { return [pscustomobject]@{ Code = -1; Dossiers = @(); Erreur = $_.Exception.Message } }
    [pscustomobject]@{ Code = 0; Dossiers = $dossiers; Erreur = '' }
}

Export-ModuleMember -Function Invoke-CopieMoteurJea, Invoke-CopieDossiersJea
