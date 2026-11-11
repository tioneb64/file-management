function Get-CopieBlocDossiers {
    <#
    .SYNOPSIS
        Bloc de script qui contrôle (ou crée) les dossiers techniques d'un environnement : base, journaux, travail.
    .DESCRIPTION
        Autonome (aucune dépendance au module) : il s'exécute tel quel sur cette machine ou, par Invoke-Command, sur le
        serveur d'exécution. Les chemins viennent de l'en-tête du fichier de paramétrage (jamais d'une saisie libre) ;
        les champs vides prennent les valeurs par défaut du moteur (logs et travail à côté de la base). Un dossier
        absent est créable si son plus proche parent existant est accessible en écriture. L'écriture est vérifiée par
        un fichier d'essai créé puis supprimé aussitôt. Action 'creer' : crée les dossiers absents créables.
        Le même code existe dans le module du point d'accès JEA (Invoke-CopieDossiersJea) : à garder identique.
    #>
    [CmdletBinding()]
    [OutputType([scriptblock])]
    param()
    {
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
        $base = & $lire 'base'
        if (-not $base) { throw 'l''en-tête ne contient pas de chemin de base' }
        $racine = [System.IO.Path]::GetDirectoryName($base)
        $logs = & $lire 'dossier_logs'
        if (-not $logs) { $logs = [System.IO.Path]::Combine($racine, 'logs') }
        $travail = & $lire 'dossier_travail'
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
}

function Invoke-CopieDossiersEnvironnement {
    <#
    .SYNOPSIS
        Contrôle ou crée les dossiers techniques d'un environnement (base, journaux, travail), là où tourne le moteur.

    .DESCRIPTION
        Local : dans le processus de l'interface, avec les droits de l'utilisateur. Distant sans JEA : par Invoke-Command
        sur Moteur.Serveur. Distant avec JEA : par la fonction Invoke-CopieDossiersJea du point d'accès (compte de service,
        création réservée au groupe administrateur). Les chemins sont lus dans l'en-tête du fichier, jamais saisis.

    .PARAMETER Config
        Configuration (Get-CopieConfig).

    .PARAMETER Fichier
        Fichier de paramétrage de l'environnement (déjà écrit).

    .PARAMETER Action
        controler (lecture seule) ou creer.

    .OUTPUTS
        [pscustomobject] Ok, Dossiers (Role, Chemin, Existe, Ecriture, ACreer, Cree, Erreur), Message (si Ok est faux).
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)] [pscustomobject] $Config,
        [Parameter(Mandatory)] [string] $Fichier,
        [Parameter(Mandatory)] [ValidateSet('controler', 'creer')] [string] $Action
    )
    $moteur = $Config.Moteur
    $bloc = Get-CopieBlocDossiers
    try {
        if ($moteur.Mode -eq 'Local') { $brut = @(& $bloc $Action $Fichier) }
        elseif ($moteur.ConfigurationJea) {
            $session = New-PSSession -ComputerName $moteur.Serveur -ConfigurationName $moteur.ConfigurationJea -ErrorAction Stop
            try {
                $null = Import-PSSession -Session $session -CommandName 'Invoke-CopieDossiersJea' -DisableNameChecking -AllowClobber -ErrorAction Stop
                $r = Invoke-CopieDossiersJea -Action $Action -Fichier $Fichier
                if ($r.Code -ne 0) { return [pscustomobject]@{ Ok = $false; Dossiers = @(); Message = "$($r.Erreur)" } }
                $brut = @($r.Dossiers)
            }
            finally { Remove-PSSession -Session $session -ErrorAction SilentlyContinue }
        }
        else { $brut = @(Invoke-Command -ComputerName $moteur.Serveur -ScriptBlock $bloc -ArgumentList $Action, $Fichier -ErrorAction Stop) }
    }
    catch { return [pscustomobject]@{ Ok = $false; Dossiers = @(); Message = $_.Exception.Message } }
    [pscustomobject]@{ Ok = $true; Dossiers = @($brut | Where-Object { $null -ne $_ }); Message = '' }
}

function Get-CopieTexteDossiersManquants {
    <#
    .SYNOPSIS
        Texte de la question unique « créer ces dossiers ? » et liste des dossiers concernés.
    .PARAMETER Dossier
        Dossiers contrôlés (Invoke-CopieDossiersEnvironnement).
    .PARAMETER Compte
        Compte avec lequel les droits ont été contrôlés (pour l'afficher).
    .OUTPUTS
        [pscustomobject] ACreer (dossiers créables), Impossibles (dossiers absents ou inaccessibles qu'on ne peut pas créer).
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param([AllowEmptyCollection()] [object[]] $Dossier = @(), [string] $Compte = '')
    $aCreer = @($Dossier | Where-Object { -not $_.Existe -and $_.ACreer })
    $impossibles = @($Dossier | Where-Object { (-not $_.Existe -and -not $_.ACreer) -or ($_.Existe -and -not $_.Ecriture) })
    $noms = @{ base = 'Base (SQLite)'; journaux = 'Journaux'; travail = 'Travail' }
    $texte = New-Object System.Collections.Generic.List[string]
    if ($aCreer.Count -gt 0) {
        $texte.Add('Ces dossiers n''existent pas :')
        foreach ($d in $aCreer) { $texte.Add(('- {0} : {1}' -f $noms[$d.Role], $d.Chemin)) }
    }
    if ($impossibles.Count -gt 0) {
        if ($texte.Count -gt 0) { $texte.Add('') }
        $texte.Add('Problèmes (non réglés par la création) :')
        foreach ($d in $impossibles) {
            $raison = $(if ($d.Erreur) { $d.Erreur } elseif ($d.Existe) { 'écriture refusée' } else { 'création impossible' })
            $texte.Add(('- {0} : {1} ({2})' -f $noms[$d.Role], $d.Chemin, $raison))
        }
    }
    if ($Compte) { $texte.Add(''); $texte.Add('Droits contrôlés avec : ' + $Compte) }
    [pscustomobject]@{ ACreer = $aCreer; Impossibles = $impossibles; Texte = ($texte -join "`n") }
}
