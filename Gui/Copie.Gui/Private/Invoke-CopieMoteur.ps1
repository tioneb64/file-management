function Get-CopieBlocProcessus {
    <#
    .SYNOPSIS
        Bloc de script qui lance un programme et renvoie son code retour et ses sorties.
    .DESCRIPTION
        Autonome (aucune dépendance au module) : il s'exécute tel quel sur cette machine ou, par
        Invoke-Command, sur le serveur d'exécution. Sortie standard lue en UTF-8 (le moteur écrit de
        l'UTF-8, jamais la page de code de la console), aucune fenêtre, durée maximale imposée : au-delà,
        le processus est arrêté et le code vaut -1.
    #>
    [CmdletBinding()]
    [OutputType([scriptblock])]
    param()
    {
        param([string] $Programme, [string[]] $Argument, [string] $Dossier, [int] $DelaiMaxSec)
        $citer = {
            param([string] $texte)
            if ($texte -eq '') { return '""' }
            if ($texte -notmatch '[\s"]') { return $texte }
            # Règles de la ligne de commande Windows : \ devant " doublés, " échappé, \ final doublé.
            $s = [regex]::Replace($texte, '(\\*)"', '$1$1\"')
            $s = [regex]::Replace($s, '(\\+)$', '$1$1')
            '"' + $s + '"'
        }
        $info = New-Object System.Diagnostics.ProcessStartInfo
        $info.FileName = $Programme
        $info.Arguments = (@($Argument | ForEach-Object { & $citer $_ }) -join ' ')
        if ($Dossier) { $info.WorkingDirectory = $Dossier }
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
        if (-not $processus.WaitForExit($DelaiMaxSec * 1000)) {
            try { $processus.Kill() } catch { $null = $_ }
            return [pscustomobject]@{ Code = -1; Sortie = ''; Erreur = ('délai de {0} s dépassé, processus arrêté' -f $DelaiMaxSec) }
        }
        $processus.WaitForExit()
        [pscustomobject]@{ Code = $processus.ExitCode; Sortie = $sortie.Result; Erreur = $erreur.Result }
    }
}

function Invoke-CopieMoteur {
    <#
    .SYNOPSIS
        Appelle le moteur (python -m copie ... --format json) et renvoie sa réponse décodée.

    .DESCRIPTION
        Trois façons d'atteindre le moteur, choisies par la configuration (Moteur.Mode) :
        - Local : sur cette machine ;
        - Distant, Moteur.ConfigurationJea vide : sur Moteur.Serveur par Invoke-Command, avec le compte
          de l'utilisateur connecté (administrateurs de la DSI) ;
        - Distant, Moteur.ConfigurationJea renseignée : par le point d'accès JEA, qui n'expose que la
          fonction Invoke-CopieMoteurJea (contrat dans docs/04-frontend.md §6). Les accès aux dossiers
          sont alors contrôlés avec le compte de service du point d'accès.

        L'interface n'ouvre jamais la base : tout passe par le moteur (docs/07-contrat-moteur-frontend.md).
        --format json est toujours ajouté. Une erreur d'arguments du moteur (sortie standard vide, code 2)
        est un défaut de l'interface : elle est renvoyée dans Erreur.

    .PARAMETER Config
        Configuration (Get-CopieConfig).

    .PARAMETER Fichier
        Fichier de paramétrage (--config). Absent pour les commandes qui n'en ont pas besoin.

    .PARAMETER Argument
        Arguments de la commande, sans --config ni --format (par exemple '--etat').

    .OUTPUTS
        [pscustomobject] Copie.ReponseMoteur : Code, Json (objet ou $null), Sortie, Erreur, Commande,
        DureeMs, Reussi ($true si le code vaut 0 ou 4 et que le JSON est lisible).
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)]
        [pscustomobject] $Config,

        [string] $Fichier,

        [Parameter(Mandatory)]
        [string[]] $Argument
    )

    $moteur = $Config.Moteur
    $arguments = New-Object System.Collections.Generic.List[string]
    $arguments.AddRange([string[]]@('-m', 'copie'))
    if ($Fichier) { $arguments.AddRange([string[]]@('--config', $Fichier)) }
    $arguments.AddRange([string[]]$Argument)
    $arguments.AddRange([string[]]@('--format', 'json'))
    $argumentsMoteur = @($Argument)       # le point d'acces JEA ajoute lui-meme --config et --format json

    $chrono = [System.Diagnostics.Stopwatch]::StartNew()
    $bloc = Get-CopieBlocProcessus
    try {
        if ($moteur.Mode -eq 'Local') {
            $texteCommande = '{0} {1}' -f $moteur.Python, ($arguments -join ' ')
            $brut = & $bloc $moteur.Python $arguments.ToArray() $moteur.Racine $moteur.DelaiMaxSec
        }
        elseif ($moteur.ConfigurationJea) {
            $texteCommande = '[JEA {0}@{1}] {2}' -f $moteur.ConfigurationJea, $moteur.Serveur, ($argumentsMoteur -join ' ')
            $session = New-PSSession -ComputerName $moteur.Serveur -ConfigurationName $moteur.ConfigurationJea -ErrorAction Stop
            try {
                $null = Import-PSSession -Session $session -CommandName 'Invoke-CopieMoteurJea' -DisableNameChecking `
                    -AllowClobber -ErrorAction Stop
                $brut = Invoke-CopieMoteurJea -Argument $argumentsMoteur -Fichier $Fichier
            }
            finally { Remove-PSSession -Session $session -ErrorAction SilentlyContinue }
        }
        else {
            $texteCommande = '[{0}] {1} {2}' -f $moteur.Serveur, $moteur.Python, ($arguments -join ' ')
            $brut = Invoke-Command -ComputerName $moteur.Serveur -ScriptBlock $bloc `
                -ArgumentList $moteur.Python, $arguments.ToArray(), $moteur.Racine, $moteur.DelaiMaxSec -ErrorAction Stop
        }
    }
    catch {
        $brut = [pscustomobject]@{ Code = -1; Sortie = ''; Erreur = $_.Exception.Message }
        if (-not (Get-Variable -Name texteCommande -ErrorAction SilentlyContinue)) { $texteCommande = ($arguments -join ' ') }
    }
    $chrono.Stop()

    $json = $null
    $erreur = "$($brut.Erreur)".Trim()
    $sortie = "$($brut.Sortie)".Trim()
    if ($sortie) {
        try { $json = $sortie | ConvertFrom-Json }
        catch { if (-not $erreur) { $erreur = 'réponse du moteur illisible (JSON attendu)' } }
    }
    elseif (-not $erreur) { $erreur = 'le moteur n''a rien répondu' }

    [pscustomobject]@{
        PSTypeName = 'Copie.ReponseMoteur'
        Code       = [int]$brut.Code
        Json       = $json
        Sortie     = $sortie
        Erreur     = $erreur
        Commande   = $texteCommande
        DureeMs    = $chrono.ElapsedMilliseconds
        Reussi     = ($null -ne $json -and $brut.Code -in 0, 4)
    }
}
