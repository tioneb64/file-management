<#
    .SYNOPSIS
        Prépare un jeu d'essai de l'interface sur un poste de développement (jamais en production).

    .DESCRIPTION
        Crée sous -Destination :
          parametrage\  production.jsonl, recette.jsonl (valides) et ancien.jsonl (environnement déclaré
                        différent du nom du fichier : affiché en lecture seule)
          donnees\      bases SQLite (le dossier est celui déclaré dans l'en-tête de chaque fichier)
          sources\ cibles\  dossiers réels des règles, avec quelques fichiers
          Gestion-Copie.essai.config.psd1   configuration de l'interface pour cet essai
        puis initialise les bases avec le moteur et exécute les règles de production une fois, pour que
        la colonne « Statut » ait des valeurs.

        Le groupe administrateur de la configuration d'essai est le SID S-1-5-11 (utilisateurs
        authentifiés) : tout compte du poste est administrateur. Pour essayer la consultation seule,
        remplacer ce groupe par un groupe dont vous n'êtes pas membre.

    .PARAMETER Destination
        Dossier d'essai (créé s'il n'existe pas ; refusé s'il contient déjà un fichier .jsonl).

    .PARAMETER Python
        Interpréteur Python 3.14 qui exécutera le moteur.

    .EXAMPLE
        .\Initialiser-Essai.ps1 -Destination D:\Essai\copie -Python C:\Python314\python.exe
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Destination,
    [Parameter(Mandatory)] [string] $Python
)

$ErrorActionPreference = 'Stop'
$racineMoteur = Split-Path -Parent $PSScriptRoot | Split-Path -Parent
if (-not (Test-Path -LiteralPath (Join-Path $racineMoteur 'copie\__main__.py'))) { throw "Moteur introuvable dans $racineMoteur" }
$Destination = [System.IO.Path]::GetFullPath($Destination)
$param = Join-Path $Destination 'parametrage'
if (Test-Path -LiteralPath $param) {
    if (Get-ChildItem -LiteralPath $param -Filter '*.jsonl' -ErrorAction SilentlyContinue) { throw "Un essai existe déjà dans $param" }
}
foreach ($d in 'parametrage', 'donnees', 'sources\clients', 'sources\produits', 'cibles\clients', 'cibles\produits') {
    $null = New-Item -ItemType Directory -Force -Path (Join-Path $Destination $d)
}
Set-Content -LiteralPath (Join-Path $Destination 'sources\clients\clients_001.csv') -Value 'id;nom' -Encoding ASCII
Set-Content -LiteralPath (Join-Path $Destination 'sources\clients\clients_002.csv') -Value 'id;nom' -Encoding ASCII
Set-Content -LiteralPath (Join-Path $Destination 'sources\produits\produits_001.csv') -Value 'id;libelle' -Encoding ASCII

function Write-FichierEssai {
    param([string] $Fichier, [object[]] $Lignes)
    $texte = (($Lignes | ForEach-Object { $_ | ConvertTo-Json -Compress -Depth 10 }) -join "`n") + "`n"
    [System.IO.File]::WriteAllText($Fichier, $texte, (New-Object System.Text.UTF8Encoding($false)))
}
function New-RegleEssai {
    param([string] $Id, [string] $Description, [string] $Mode, [string] $Source, [string] $Cible, [hashtable] $Planification, [hashtable] $Autres = @{})
    $r = [ordered]@{
        id = $Id; description = $Description; actif = $true; source = $Source; cible = $Cible; mode = $Mode
        selection = [ordered]@{ masque = '*.csv'; age_minimum_sec = 0 }
        planification = $Planification
    }
    foreach ($k in $Autres.Keys) { $r[$k] = $Autres[$k] }
    $r
}
$src = Join-Path $Destination 'sources'
$cib = Join-Path $Destination 'cibles'
$toutes5min = @{ type = 'intervalle'; frequence_sec = 300; debut = '00:00'; fin = '23:59'; jours = 'tous' }
$quotidien = @{ type = 'quotidien'; heure = '07:15'; jours = 'lun-ven'; rattrapage_sec = 14400 }

foreach ($env in 'production', 'recette') {
    $entete = [ordered]@{ version = 1; environnement = $env; base = (Join-Path $Destination "donnees\$env.db") }
    $regles = @(
        (New-RegleEssai 'export_clients' 'Export des clients' 'archivage' (Join-Path $src 'clients') (Join-Path $cib 'clients') $toutes5min @{ archive = '.\archive\{AAAA}-{MM}-{JJ}' }),
        (New-RegleEssai 'export_produits' 'Export des produits' 'deplacement' (Join-Path $src 'produits') (Join-Path $cib 'produits') $toutes5min),
        (New-RegleEssai 'import_catalogue' 'Import du catalogue (après les exports)' 'copie' (Join-Path $cib 'produits') (Join-Path $cib 'clients') $quotidien @{ apres = @('export_clients', 'export_produits'); condition = @('succes', 'fichiers') })
    )
    Write-FichierEssai -Fichier (Join-Path $param "$env.jsonl") -Lignes (@($entete) + $regles)
}
# Environnement déclaré différent du nom du fichier : doit s'afficher en lecture seule.
Write-FichierEssai -Fichier (Join-Path $param 'ancien.jsonl') -Lignes @(
    [ordered]@{ version = 1; environnement = 'autre'; base = (Join-Path $Destination 'donnees\autre.db') },
    (New-RegleEssai 'regle_ancienne' 'Règle d''un ancien environnement' 'copie' (Join-Path $src 'clients') (Join-Path $cib 'clients') $quotidien))

$configuration = @"
@{
    Acces = @{ GroupesAdmin = @('S-1-5-11') }
    Moteur = @{
        Mode = 'Local'
        Python = '$Python'
        Racine = '$racineMoteur'
        DelaiMaxSec = 120
    }
    Parametrage = @{ Filtre = '*.jsonl'; VersionsSupportees = @(1); DossierVersions = 'versions'; DossierBrouillons = '.brouillons'; PeriodeDeclencheurSec = 300 }
    Journal = @{ Dossier = '$(Join-Path $Destination 'journal-gui')' }
}
"@
[System.IO.File]::WriteAllText((Join-Path $Destination 'Gestion-Copie.essai.config.psd1'), $configuration, (New-Object System.Text.UTF8Encoding($false)))

Push-Location $racineMoteur
try {
    foreach ($env in 'production', 'recette') {
        & $Python -m copie --config (Join-Path $param "$env.jsonl") --initialiser-base
        if ($LASTEXITCODE -ne 0) { throw "Initialisation de la base $env refusée (code $LASTEXITCODE)" }
    }
    foreach ($id in 'export_clients', 'export_produits') {
        & $Python -m copie --config (Join-Path $param 'production.jsonl') --lancer-regle $id | Out-Null
    }
}
finally { Pop-Location }

Write-Host "Essai prêt dans $Destination"
Write-Host "Lancer : .\Lancer-GestionCopie.ps1 -DossierParametrage '$param' -Config '$(Join-Path $Destination 'Gestion-Copie.essai.config.psd1')'"
