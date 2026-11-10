<#
    .SYNOPSIS
        Lance l'interface de gestion des transferts de fichiers (copie_fichiers).

    .PARAMETER DossierParametrage
        Dossier qui contient les fichiers de paramétrage (un .jsonl par environnement). Obligatoire :
        il n'est écrit nulle part en dur.

    .PARAMETER Config
        Configuration de l'interface. Par défaut : Gestion-Copie.config.psd1 à côté de ce script.

    .EXAMPLE
        .\Lancer-GestionCopie.ps1 -DossierParametrage D:\Parametrage
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string] $DossierParametrage,

    [string] $Config
)

$ErrorActionPreference = 'Stop'
if (-not $Config) { $Config = Join-Path $PSScriptRoot 'Gestion-Copie.config.psd1' }

# WPF exige un thread STA (c'est celui de powershell.exe 5.1 ; pwsh 7 doit être lancé avec -STA).
if ([System.Threading.Thread]::CurrentThread.GetApartmentState() -ne 'STA') {
    $shell = (Get-Process -Id $PID).Path
    & $shell -NoProfile -STA -File $PSCommandPath -DossierParametrage $DossierParametrage -Config $Config
    exit $LASTEXITCODE
}

try {
    Import-Module (Join-Path $PSScriptRoot 'Copie.Gui\Copie.Gui.psd1') -Force
    Start-CopieGui -DossierParametrage $DossierParametrage -Config $Config
}
catch {
    Add-Type -AssemblyName PresentationFramework
    [void][System.Windows.MessageBox]::Show($_.Exception.Message, 'Gestion des transferts de fichiers', 'OK', 'Error')
    exit 1
}
