$Script:Taches = New-Object System.Collections.Generic.List[object]
$Script:MinuterieTaches = $null

function Start-CopieTache {
    <#
    .SYNOPSIS
        Lance le moteur en arrière-plan : la fenêtre reste utilisable pendant l'appel.

    .DESCRIPTION
        L'appel (Invoke-CopieMoteur) s'exécute dans un espace d'exécution (runspace) distinct qui recharge
        le module. Une minuterie du thread de l'interface (250 ms) surveille la fin de l'appel et exécute
        alors SurFin sur ce thread : SurFin peut donc toucher aux contrôles. SurFin reçoit la tâche :
        .Reponse (Copie.ReponseMoteur) et .Donnees (ce qui a été fourni ici). Une exception dans SurFin est
        journalisée et affichée, elle ne casse pas la minuterie.

    .PARAMETER Config
        Configuration (Get-CopieConfig).

    .PARAMETER Fichier
        Fichier de paramétrage (--config), ou vide.

    .PARAMETER Argument
        Arguments du moteur (voir Invoke-CopieMoteur).

    .PARAMETER SurFin
        Bloc appelé à la fin, sur le thread de l'interface, avec la tâche en paramètre.

    .PARAMETER Donnees
        Données remises à SurFin (la vue, le contexte...), car les variables locales ne sont pas
        visibles d'un gestionnaire d'événement.

    .OUTPUTS
        La tâche (hashtable).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [pscustomobject] $Config,
        [string] $Fichier = '',
        [Parameter(Mandatory)] [string[]] $Argument,
        [Parameter(Mandatory)] [scriptblock] $SurFin,
        [hashtable] $Donnees = @{}
    )
    $chemin = $ExecutionContext.SessionState.Module.Path
    $ps = [powershell]::Create()
    $null = $ps.AddScript({
            param($module, $config, $fichier, $argument)
            Import-Module $module -Force
            & (Get-Module 'FileManagement.Gui') { param($c, $f, $a) Invoke-CopieMoteur -Config $c -Fichier $f -Argument $a } $config $fichier $argument
        }).AddArgument($chemin).AddArgument($Config).AddArgument($Fichier).AddArgument($Argument)
    $tache = @{ Ps = $ps; Poignee = $ps.BeginInvoke(); SurFin = $SurFin; Donnees = $Donnees; Reponse = $null; Debut = Get-Date }
    $Script:Taches.Add($tache)
    if ($null -eq $Script:MinuterieTaches) {
        Add-Type -AssemblyName WindowsBase
        $Script:MinuterieTaches = New-Object System.Windows.Threading.DispatcherTimer
        $Script:MinuterieTaches.Interval = [TimeSpan]::FromMilliseconds(250)
        $Script:MinuterieTaches.Add_Tick({ Step-CopieTache })
    }
    $Script:MinuterieTaches.Start()
    $tache
}

function Step-CopieTache {
    <#
    .SYNOPSIS
        Traite les tâches terminées (appelée par la minuterie, ou à la main dans les tests).
    .OUTPUTS
        [int] nombre de tâches encore en cours.
    #>
    [CmdletBinding()]
    [OutputType([int])]
    param()
    foreach ($t in @($Script:Taches.ToArray())) {
        if (-not $t.Poignee.IsCompleted) { continue }
        $null = $Script:Taches.Remove($t)
        $reponse = $null
        try {
            $sortie = @($t.Ps.EndInvoke($t.Poignee))
            $reponse = $sortie | Where-Object { $_ -and $_.PSObject.Properties['Code'] } | Select-Object -Last 1
            if ($null -eq $reponse) {
                $erreur = (@($t.Ps.Streams.Error | ForEach-Object { "$_" }) -join ' ')
                $reponse = [pscustomobject]@{ Code = -1; Json = $null; Sortie = ''; Erreur = $(if ($erreur) { $erreur } else { 'tâche sans réponse' }); Commande = ''; DureeMs = 0; Reussi = $false }
            }
        }
        catch {
            $reponse = [pscustomobject]@{ Code = -1; Json = $null; Sortie = ''; Erreur = $_.Exception.Message; Commande = ''; DureeMs = 0; Reussi = $false }
        }
        finally { $t.Ps.Dispose() }
        $t.Reponse = $reponse
        try { & $t.SurFin $t }
        catch {
            $ctx = $t.Donnees.Contexte
            if ($null -ne $ctx) {
                Write-CopieJournal -Contexte $ctx -Niveau 'ERREUR' -Evenement 'tache_arriere_plan' -Message $_.Exception.Message
                if ($null -ne $ctx.Fenetre) { [void][System.Windows.MessageBox]::Show($ctx.Fenetre, $_.Exception.Message, 'Erreur', 'OK', 'Error') }
            }
        }
    }
    if ($Script:Taches.Count -eq 0 -and $null -ne $Script:MinuterieTaches) { $Script:MinuterieTaches.Stop() }
    $Script:Taches.Count
}

function Wait-CopieTache {
    <#
    .SYNOPSIS
        Attend la fin de toutes les tâches en traitant leurs résultats (tests, scripts sans fenêtre).
    .PARAMETER DelaiSec
        Délai maximal.
    #>
    [CmdletBinding()]
    param([int] $DelaiSec = 60)
    $limite = (Get-Date).AddSeconds($DelaiSec)
    while ((Step-CopieTache) -gt 0) {
        if ((Get-Date) -gt $limite) { throw 'Wait-CopieTache : délai dépassé' }
        Start-Sleep -Milliseconds 50
    }
}
