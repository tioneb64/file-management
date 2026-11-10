<#
    .SYNOPSIS
        Lance les tests de l'interface (Pester 5) puis l'analyse PSScriptAnalyzer.

    .DESCRIPTION
        À lancer avec Windows PowerShell 5.1 (la version de production) : les tests de fenêtre exigent un
        thread STA, ce que fait powershell.exe. Les tests qui lancent le vrai moteur Python lisent
        l'interpréteur dans -Python ou, à défaut, dans la variable COPIE_TEST_PYTHON ; sans interpréteur
        ils sont ignorés (et le résumé le dit).

    .PARAMETER Python
        Interpréteur Python 3.14 pour les tests d'intégration.

    .PARAMETER SansAnalyse
        Ne lance pas PSScriptAnalyzer.
#>
[CmdletBinding()]
param([string] $Python, [switch] $SansAnalyse)

$ErrorActionPreference = 'Stop'
if ($Python) { $env:COPIE_TEST_PYTHON = $Python }
Import-Module Pester -MinimumVersion 5.0.0
$config = New-PesterConfiguration
$config.Run.Path = $PSScriptRoot
$config.Run.Exit = $false
$config.Run.PassThru = $true
$config.Output.Verbosity = 'Normal'
$resultat = Invoke-Pester -Configuration $config
$echecs = $resultat.FailedCount
if (-not $env:COPIE_TEST_PYTHON) { Write-Warning 'COPIE_TEST_PYTHON absent : les tests du moteur et de la fenêtre complète ont été ignorés.' }

if (-not $SansAnalyse) {
    $reglages = Join-Path $PSScriptRoot 'PSScriptAnalyzerSettings.psd1'
    $problemes = @(Invoke-ScriptAnalyzer -Path (Split-Path -Parent $PSScriptRoot) -Recurse -Settings $reglages)
    $problemes | Format-Table -AutoSize RuleName, Severity, ScriptName, Line, Message | Out-String | Write-Host
    $echecs += @($problemes | Where-Object Severity -in 'Error', 'Warning').Count
}
if ($echecs -gt 0) { Write-Error ('{0} échec(s)' -f $echecs); exit 1 }
Write-Host 'Tous les tests passent.'
