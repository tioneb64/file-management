function Resolve-CopieDossierJournal {
    <#
    .SYNOPSIS
        Contrôle le dossier du journal de l'interface (Journal.Dossier) ; propose de le créer s'il n'existe pas.

    .DESCRIPTION
        Le dossier n'est jamais créé en silence : une faute de frappe dans le fichier de configuration créerait
        sinon un dossier au mauvais endroit sans que personne le sache. Absent, il est créé seulement si
        l'utilisateur le confirme (une seule question). Refus, création impossible ou chemin invalide : le journal
        fichier est désactivé pour la session (Journal.Dossier vidé EN MÉMOIRE, le fichier de configuration n'est pas
        modifié) ; le journal du panneau de l'interface continue de fonctionner. Sans Journal.Dossier : rien à faire.

    .PARAMETER Config
        Configuration (Get-CopieConfig), modifiée en mémoire si le journal fichier est désactivé.

    .PARAMETER Confirmer
        Bloc appelé avec la question de création ; renvoie $true pour créer.

    .OUTPUTS
        [pscustomobject] Actif ($true si un journal fichier sera écrit), Cree, Message (raison d'une désactivation, sinon '').
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)] [pscustomobject] $Config,
        [Parameter(Mandatory)] [scriptblock] $Confirmer
    )
    $saisi = "$($Config.Journal.Dossier)".Trim().Trim('"')
    if (-not $saisi) { return [pscustomobject]@{ Actif = $false; Cree = $false; Message = '' } }
    $desactiver = {
        param($raison)
        $Config.Journal.Dossier = ''
        [pscustomobject]@{ Actif = $false; Cree = $false; Message = ($raison + ' Le journal fichier de l''interface est désactivé pour cette session.') }
    }
    try {
        if (-not [System.IO.Path]::IsPathRooted($saisi)) { throw 'Le chemin doit être complet (par exemple D:\Journaux\Interface).' }
        $complet = [System.IO.Path]::GetFullPath($saisi)
    }
    catch { return (& $desactiver ('Journal.Dossier est invalide : {0} ({1}).' -f $saisi, $_.Exception.Message)) }
    if ($complet.Length -gt 3) { $complet = $complet.TrimEnd('\', '/') }

    if (Test-Path -LiteralPath $complet -PathType Leaf) {
        return (& $desactiver ('Journal.Dossier désigne un fichier, pas un dossier : {0}.' -f $complet))
    }
    if (Test-Path -LiteralPath $complet -PathType Container) {
        $Config.Journal.Dossier = $complet
        return [pscustomobject]@{ Actif = $true; Cree = $false; Message = '' }
    }
    $question = ("Le dossier du journal de l'interface n'existe pas :`n{0}`n`nLe créer maintenant ?`n(Non : le journal fichier sera désactivé pour cette session ; corrigez Journal.Dossier dans Gestion-Copie.config.psd1.)" -f $complet)
    if (-not [bool](& $Confirmer $question)) {
        return (& $desactiver ('Le dossier du journal n''existe pas et n''a pas été créé : {0}.' -f $complet))
    }
    try { $null = New-Item -ItemType Directory -Path $complet -ErrorAction Stop }
    catch { return (& $desactiver ('Création du dossier du journal impossible : {0} ({1}).' -f $complet, $_.Exception.Message)) }
    $Config.Journal.Dossier = $complet
    [pscustomobject]@{ Actif = $true; Cree = $true; Message = '' }
}
