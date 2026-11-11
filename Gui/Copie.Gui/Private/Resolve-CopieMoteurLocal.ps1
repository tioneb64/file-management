function Find-CopiePythonLocal {
    <#
    .SYNOPSIS
        Cherche un python.exe utilisable sur cette machine (PATH, puis lanceur py), hors faux lanceurs du Windows Store.
    .OUTPUTS
        [string] Chemin complet, ou '' si rien n'est trouvé.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param()
    foreach ($commande in @(Get-Command -Name 'python.exe' -CommandType Application -All -ErrorAction SilentlyContinue)) {
        $chemin = "$($commande.Source)"
        if ($chemin -and $chemin -notmatch '\\WindowsApps\\' -and (Test-Path -LiteralPath $chemin -PathType Leaf)) { return $chemin }
    }
    $lanceur = Get-Command -Name 'py.exe' -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($lanceur) {
        try {
            $reel = @(& $lanceur.Source -3 -c 'import sys; print(sys.executable)' 2>$null) | Select-Object -First 1
            if ($reel -and (Test-Path -LiteralPath "$reel" -PathType Leaf)) { return "$reel".Trim() }
        }
        catch { $null = $_ }
    }
    ''
}

function Resolve-CopieMoteurLocal {
    <#
    .SYNOPSIS
        Mode Local : vérifie que Moteur.Python et Moteur.Racine existent ; sinon les cherche et propose de les utiliser.

    .DESCRIPTION
        Le fichier de configuration modèle porte des chemins d'exemple (C:\Python314\python.exe, D:\Scripts\copie_fichiers)
        qui n'existent pas sur un poste de développement. Python est cherché dans le PATH puis par le lanceur py ; la
        racine du moteur est le dossier qui contient « copie\__main__.py » au-dessus de ce module (dépôt). Une seule
        question est posée pour tout ce qui est corrigé. Rien n'est écrit dans le fichier de configuration : la
        correction vaut pour la session. Hors mode Local, ne fait rien.

    .PARAMETER Config
        Configuration (Get-CopieConfig), modifiée en mémoire si l'utilisateur accepte.

    .PARAMETER Confirmer
        Bloc appelé avec la question ; renvoie $true pour accepter.

    .PARAMETER RacineDepot
        Racine du dépôt à essayer (par défaut : trois niveaux au-dessus de ce fichier).

    .OUTPUTS
        [pscustomobject] Ok ($true si le moteur est utilisable à la fin), Modifie, Message (problème restant, sinon '').
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)] [pscustomobject] $Config,
        [Parameter(Mandatory)] [scriptblock] $Confirmer,
        [string] $RacineDepot = ''
    )
    $moteur = $Config.Moteur
    if ($moteur.Mode -ne 'Local') { return [pscustomobject]@{ Ok = $true; Modifie = $false; Message = '' } }

    $pythonOk = ($moteur.Python -and (Test-Path -LiteralPath $moteur.Python -PathType Leaf))
    $racineOk = ($moteur.Racine -and (Test-Path -LiteralPath (Join-Path $moteur.Racine 'copie\__main__.py') -PathType Leaf))
    if ($pythonOk -and $racineOk) { return [pscustomobject]@{ Ok = $true; Modifie = $false; Message = '' } }

    if (-not $RacineDepot) { $RacineDepot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) }
    $python = $moteur.Python
    $racine = $moteur.Racine
    $probleme = New-Object System.Collections.Generic.List[string]
    $propose = New-Object System.Collections.Generic.List[string]

    if (-not $pythonOk) {
        $trouve = Find-CopiePythonLocal
        if ($trouve) { $python = $trouve; $propose.Add('Python : ' + $trouve) }
        else { $probleme.Add(('Python introuvable (Moteur.Python = {0}) et aucun python.exe dans le PATH.' -f $moteur.Python)) }
    }
    if (-not $racineOk) {
        if ($RacineDepot -and (Test-Path -LiteralPath (Join-Path $RacineDepot 'copie\__main__.py') -PathType Leaf)) { $racine = $RacineDepot; $propose.Add('Moteur : ' + $RacineDepot) }
        else { $probleme.Add(('Dossier du moteur introuvable (Moteur.Racine = {0}) : il doit contenir copie\__main__.py.' -f $moteur.Racine)) }
    }

    $modifie = $false
    if ($propose.Count -gt 0) {
        $question = ("La configuration du moteur est incorrecte sur ce poste :`n- Python : {0}`n- Dossier du moteur : {1}`n`nTrouvé :`n{2}`n`nLes utiliser pour cette session ? (le fichier de configuration n'est pas modifié ; corrigez Moteur.Python et Moteur.Racine dans Gestion-Copie.config.psd1 pour que ce soit définitif)" -f $moteur.Python, $moteur.Racine, ($propose -join "`n"))
        if (& $Confirmer $question) {
            $moteur.Python = $python
            $moteur.Racine = $racine
            $modifie = $true
        }
        else { $probleme.Add('Chemins du moteur non corrigés : corrigez Moteur.Python et Moteur.Racine dans Gestion-Copie.config.psd1.') }
    }
    $okPython = ($moteur.Python -and (Test-Path -LiteralPath $moteur.Python -PathType Leaf))
    $okRacine = ($moteur.Racine -and (Test-Path -LiteralPath (Join-Path $moteur.Racine 'copie\__main__.py') -PathType Leaf))
    [pscustomobject]@{ Ok = [bool]($okPython -and $okRacine); Modifie = $modifie; Message = ($probleme -join "`n") }
}
