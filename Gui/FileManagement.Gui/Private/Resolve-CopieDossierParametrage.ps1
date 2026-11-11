function Resolve-CopieDossierParametrage {
    <#
    .SYNOPSIS
        Contrôle le dossier de paramétrage donné au lancement ; propose de le créer s'il n'existe pas (administrateurs).

    .DESCRIPTION
        Renvoie le chemin complet. Un dossier absent n'est créé que si l'utilisateur est administrateur ET le confirme
        (Confirmer reçoit le texte de la question) ; refus de l'utilisateur : renvoie $null (on n'ouvre rien).
        Tous les autres cas sont des erreurs avec un message clair : chemin vide ou invalide, chemin d'un fichier,
        dossier absent pour un compte non administrateur, dossier inaccessible, création impossible.

    .PARAMETER Chemin
        Chemin donné au lancement (absolu ou relatif au dossier courant).

    .PARAMETER Profil
        Profil de l'utilisateur (Get-CopieProfilAcces).

    .PARAMETER GroupeAdmin
        Groupes administrateurs de la configuration (pour le message d'un compte non administrateur).

    .PARAMETER Confirmer
        Bloc appelé avec la question de création ; $true pour créer. Absent : jamais de création.

    .OUTPUTS
        [string] chemin complet, ou $null si la création a été refusée.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [AllowEmptyString()] [string] $Chemin = '',
        [Parameter(Mandatory)] [string] $Profil,
        [string[]] $GroupeAdmin = @(),
        [scriptblock] $Confirmer
    )
    $saisi = "$Chemin".Trim().Trim('"')
    if (-not $saisi) { throw 'Le dossier de paramétrage n''est pas renseigné.' }
    try {
        if (-not [System.IO.Path]::IsPathRooted($saisi)) { $saisi = Join-Path (Get-Location -PSProvider FileSystem).ProviderPath $saisi }
        $complet = [System.IO.Path]::GetFullPath($saisi)
    }
    catch { throw ('Le chemin du dossier de paramétrage est invalide : {0} ({1})' -f $Chemin, $_.Exception.Message) }
    if ($complet.Length -gt 3) { $complet = $complet.TrimEnd('\', '/') }

    if (Test-Path -LiteralPath $complet -PathType Leaf) {
        throw ('Ce chemin désigne un fichier, pas un dossier : {0}' -f $complet)
    }
    if (Test-Path -LiteralPath $complet -PathType Container) {
        try { $null = @(Get-ChildItem -LiteralPath $complet -ErrorAction Stop | Select-Object -First 1) }
        catch { throw ('Le dossier de paramétrage n''est pas accessible avec votre compte : {0}{1}{2}' -f $complet, [Environment]::NewLine, $_.Exception.Message) }
        return $complet
    }

    if ($Profil -ne 'Admin') {
        throw ("Le dossier de paramétrage n'existe pas : {0}`n`nVérifiez le chemin. Seul un administrateur (groupe : {1}) peut le créer." -f $complet, ($GroupeAdmin -join ', '))
    }
    $question = ("Le dossier de paramétrage n'existe pas :`n{0}`n`nLe créer maintenant ? (vous pourrez ensuite y créer un premier environnement)" -f $complet)
    $accord = $false
    if ($null -ne $Confirmer) { $accord = [bool](& $Confirmer $question) }
    if (-not $accord) { return $null }
    try { $null = New-Item -ItemType Directory -Path $complet -Force -ErrorAction Stop }
    catch { throw ('Création du dossier impossible : {0}{1}{2}{1}Vérifiez vos droits sur le dossier parent.' -f $complet, [Environment]::NewLine, $_.Exception.Message) }
    $complet
}
