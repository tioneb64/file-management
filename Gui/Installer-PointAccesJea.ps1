<#
    .SYNOPSIS
        Installe sur le serveur d'exécution le point d'accès JEA de copie_fichiers.

    .DESCRIPTION
        Le point d'accès n'expose que deux fonctions : Invoke-CopieMoteurJea (qui n'accepte que les commandes
        du contrat du moteur, docs/07-contrat-moteur-frontend.md §4, lit uniquement les fichiers du dossier
        de paramétrage, et exécute le moteur avec le compte de la session (pas celui de l'appelant) : les
        contrôles d'accès de --verifier reflètent alors ce que Jenkins pourra faire. Les commandes
        d'écriture sont réservées au groupe administrateur ; les autres membres du groupe de lecture ne
        peuvent que consulter (--etat, --verifier, --modele-regle). Le compte tracé par le moteur est celui
        de l'appelant) et Invoke-CopieDossiersJea (contrôle ou création des dossiers de la base, des journaux
        et du travail d'un environnement, lus dans l'en-tête de son fichier ; création réservée au groupe administrateur).

        Ce script : copie le module Copie.Jea dans les modules du système, écrit sa configuration,
        crée le fichier de session et l'enregistre (Register-PSSessionConfiguration). À lancer sur le
        serveur d'exécution, en administrateur. Il demande confirmation (-Confirm:$false pour l'éviter) et
        accepte -WhatIf.

        ATTENTION au compte d'exécution : un compte virtuel (par défaut) est LOCAL au serveur. Pour lire et
        écrire sur des partages réseau avec les droits du compte de service de Jenkins, il faut un compte de
        service géré (-CompteService 'DOMAINE\gmsa-copie$'), déjà installé sur le serveur.

    .PARAMETER Nom
        Nom du point d'accès (celui de Moteur.ConfigurationJea dans Gestion-Copie.config.psd1).

    .PARAMETER GroupeAdmin
        Groupe administrateur (DOMAINE\Groupe) : peut lancer toutes les commandes.

    .PARAMETER GroupeLecture
        Groupe qui peut seulement consulter (facultatif).

    .PARAMETER Python
        Interpréteur Python 3.14 du moteur.

    .PARAMETER Racine
        Dossier du moteur (celui qui contient le dossier copie\).

    .PARAMETER DossierParametrage
        Dossier des fichiers de paramétrage (le même que pour Initialiser-DossierParametrage.ps1).

    .PARAMETER CompteService
        Compte de service géré (DOMAINE\compte$). Absent : compte virtuel local.

    .PARAMETER DelaiMaxSec
        Durée maximale d'une commande (600 s par défaut).

    .PARAMETER DossierTraces
        Dossier des transcriptions de session (qui a lancé quoi) : par défaut sous ProgramData.

    .EXAMPLE
        .\Installer-PointAccesJea.ps1 -GroupeAdmin 'DOMAINE\GG_Copie_Admins' -Python C:\Python314\python.exe -Racine D:\copie_fichiers -DossierParametrage D:\Parametrage -CompteService 'DOMAINE\gmsa-copie$' -WhatIf
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [string] $Nom = 'CopieFichiers',
    [Parameter(Mandatory)] [string] $GroupeAdmin,
    [string] $GroupeLecture,
    [Parameter(Mandatory)] [string] $Python,
    [Parameter(Mandatory)] [string] $Racine,
    [Parameter(Mandatory)] [string] $DossierParametrage,
    [string] $CompteService,
    [ValidateRange(10, 86400)] [int] $DelaiMaxSec = 600,
    [string] $DossierTraces = (Join-Path $env:ProgramData 'CopieFichiers\Jea')
)

$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'Jea\Copie.Jea'
if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw "module introuvable : $source" }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "interpréteur Python introuvable : $Python" }
if (-not (Test-Path -LiteralPath (Join-Path $Racine 'copie') -PathType Container)) { throw "le dossier $Racine ne contient pas le paquet copie" }
if (-not (Test-Path -LiteralPath $DossierParametrage -PathType Container)) { throw "dossier de paramétrage introuvable : $DossierParametrage" }
if ($GroupeAdmin -notmatch '^[^\\]+\\[^\\]+$') { throw "GroupeAdmin doit s'écrire DOMAINE\Groupe" }
if ($GroupeLecture -and $GroupeLecture -notmatch '^[^\\]+\\[^\\]+$') { throw "GroupeLecture doit s'écrire DOMAINE\Groupe" }
$principal = New-Object System.Security.Principal.WindowsPrincipal([System.Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $WhatIfPreference -and -not $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'à lancer en administrateur (invite PowerShell élevée)'
}

$modules = Join-Path $env:ProgramFiles 'WindowsPowerShell\Modules'
$cible = Join-Path $modules 'Copie.Jea'
$fichierSession = Join-Path $DossierTraces ($Nom + '.pssc')

if ($PSCmdlet.ShouldProcess($env:COMPUTERNAME, "installer le point d'accès JEA « $Nom » (module $cible, session $Nom)")) {
    if (Test-Path -LiteralPath $cible) { Remove-Item -LiteralPath $cible -Recurse -Force }
    Copy-Item -LiteralPath $source -Destination $cible -Recurse
    $apostrophe = { param($t) "'" + ($t -replace "'", "''") + "'" }
    $texte = @(
        '@{'
        '    Python             = ' + (& $apostrophe $Python)
        '    Racine             = ' + (& $apostrophe $Racine)
        '    DossierParametrage = ' + (& $apostrophe $DossierParametrage)
        '    GroupeAdmin        = ' + (& $apostrophe $GroupeAdmin)
        '    DelaiMaxSec        = ' + $DelaiMaxSec
        '}'
    ) -join "`r`n"
    [System.IO.File]::WriteAllText((Join-Path $cible 'Copie.Jea.config.psd1'), $texte + "`r`n", (New-Object System.Text.UTF8Encoding($true)))

    $null = New-Item -ItemType Directory -Path $DossierTraces -Force
    $roles = @{ $GroupeAdmin = @{ RoleCapabilities = 'CopieFichiers' } }
    if ($GroupeLecture) { $roles[$GroupeLecture] = @{ RoleCapabilities = 'CopieFichiers' } }
    $session = @{
        Path                = $fichierSession
        SessionType         = 'RestrictedRemoteServer'
        TranscriptDirectory = $DossierTraces
        RoleDefinitions     = $roles
        Description         = 'copie_fichiers : point d''accès au moteur'
    }
    if ($CompteService) { $session['GroupManagedServiceAccount'] = $CompteService } else { $session['RunAsVirtualAccount'] = $true }
    New-PSSessionConfigurationFile @session
    if (Get-PSSessionConfiguration -Name $Nom -ErrorAction SilentlyContinue) { $null = Unregister-PSSessionConfiguration -Name $Nom -Force }
    $null = Register-PSSessionConfiguration -Name $Nom -Path $fichierSession -Force
    Write-Host ("Point d'accès « {0} » installé. Dans Gestion-Copie.config.psd1 : Moteur.Mode = 'Distant', Serveur = '{1}', ConfigurationJea = '{0}'." -f $Nom, $env:COMPUTERNAME)
    Write-Host ("Transcriptions des sessions : {0}" -f $DossierTraces)
}
