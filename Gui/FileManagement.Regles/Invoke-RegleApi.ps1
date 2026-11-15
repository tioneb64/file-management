<#
.SYNOPSIS
    Point d'entrée en ligne de commande de l'API de règles (pour les scripts Python et tout programme qui n'importe pas le module).

.DESCRIPTION
    Appelle les fonctions du module FileManagement.Regles et rend UN document JSON (stdout, ou -SortieJson).
    Les noms de champs sont en minuscules avec « _ » (succes, etape, message, refus, avertissements, version_api...).
    Les entrées volumineuses passent par -EntreeJson (fichier JSON UTF-8) : pas de problème de guillemets ni d'encodage.

    Code retour : 0 = fait ; 1 = refusé ou impossible (droits, conflit, refus du moteur, règle introuvable...) :
    lire « etape » et « message » ; 2 = erreur d'emploi ou erreur technique inattendue.

    Fichier -EntreeJson, champs : regle (ajouter), modification (modifier), commentaire, appelant, empreinte,
    accepter_avertissements.

.PARAMETER Action
    info, modele, lire, ajouter, modifier, supprimer.
.PARAMETER Fichier
    Fichier de paramétrage (parametrage\<env>.jsonl) ; inutile pour info et modele.
.PARAMETER Id
    Règle visée (lire : facultatif ; modifier et supprimer : obligatoire).
.PARAMETER EntreeJson
    Fichier JSON des paramètres d'écriture (voir ci-dessus).
.PARAMETER SortieJson
    Écrit le résultat dans ce fichier (UTF-8 sans BOM) au lieu de la sortie standard.
.PARAMETER Config
    Gestion-Copie.config.psd1 (défaut : celui de l'interface).

.EXAMPLE
    .\Invoke-RegleApi.ps1 -Action ajouter -Fichier D:\Parametrage\prod.jsonl -EntreeJson .\demande.json -SortieJson .\resultat.json
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [ValidateSet('info', 'modele', 'lire', 'ajouter', 'modifier', 'supprimer')] [string] $Action,
    [string] $Fichier,
    [string] $Id,
    [string] $EntreeJson,
    [string] $SortieJson,
    [string] $Config
)
$ErrorActionPreference = 'Stop'
$Script:Sortie = $SortieJson   # lu par Write-Resultat

function ConvertTo-Minuscules {
    param($Objet)
    $sortie = [ordered]@{}
    foreach ($p in $Objet.PSObject.Properties) {
        if ($p.Name -eq 'PSTypeName') { continue }
        $nom = ([regex]::Replace($p.Name, '(?<=[a-z0-9])([A-Z])', '_$1')).ToLowerInvariant()
        $sortie[$nom] = $p.Value
    }
    $sortie
}

function Write-Resultat {
    param($Objet, [int] $Code)
    $json = (ConvertTo-Minuscules -Objet $Objet) | ConvertTo-Json -Depth 12
    if ($Script:Sortie) { [System.IO.File]::WriteAllText($Script:Sortie, $json, (New-Object System.Text.UTF8Encoding($false))) }
    else {
        [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
        [Console]::Out.WriteLine($json)
    }
    exit $Code
}

try {
    Import-Module (Join-Path $PSScriptRoot 'FileManagement.Regles.psd1') -Force
    $demande = $null
    if ($EntreeJson) {
        $demande = [System.IO.File]::ReadAllText($EntreeJson, (New-Object System.Text.UTF8Encoding($false))) | ConvertFrom-Json
    }
    $v = { param($nom, $defaut) if ($null -ne $demande -and $null -ne $demande.PSObject.Properties[$nom]) { $demande.PSObject.Properties[$nom].Value } else { $defaut } }
    $commun = @{}
    if ($Config) { $commun.Config = $Config }
    $ecriture = @{
        Commentaire = [string](& $v 'commentaire' ''); Appelant = [string](& $v 'appelant' ''); Empreinte = [string](& $v 'empreinte' '')
        AccepterAvertissements = [bool](& $v 'accepter_avertissements' $false)
    }
    $manque = {
        param($texte)
        Write-Resultat ([pscustomobject]@{ Succes = $false; Etape = 'invalide'; Message = $texte; VersionApi = 1 }) 2
    }
    switch ($Action) {
        'info' { $r = Get-CopieApiInfo @commun }
        'modele' { $r = Get-CopieApiModele @commun }
        'lire' {
            if (-not $Fichier) { & $manque '-Fichier est obligatoire.' }
            $args2 = @{ Fichier = $Fichier }
            if ($Id) { $args2.Id = $Id }
            $r = Get-CopieApiRegle @args2
        }
        'ajouter' {
            if (-not $Fichier) { & $manque '-Fichier est obligatoire.' }
            if ($null -eq (& $v 'regle' $null)) { & $manque 'Le champ regle est obligatoire dans -EntreeJson.' }
            $r = Add-CopieApiRegle -Fichier $Fichier -Regle ((& $v 'regle' $null) | ConvertTo-Json -Depth 12) @ecriture @commun
        }
        'modifier' {
            if (-not $Fichier -or -not $Id) { & $manque '-Fichier et -Id sont obligatoires.' }
            if ($null -eq (& $v 'modification' $null)) { & $manque 'Le champ modification est obligatoire dans -EntreeJson.' }
            $r = Set-CopieApiRegle -Fichier $Fichier -Id $Id -Modification ((& $v 'modification' $null) | ConvertTo-Json -Depth 12) @ecriture @commun
        }
        'supprimer' {
            if (-not $Fichier -or -not $Id) { & $manque '-Fichier et -Id sont obligatoires.' }
            $r = Remove-CopieApiRegle -Fichier $Fichier -Id $Id @ecriture @commun
        }
    }
    Write-Resultat $r $(if ($r.Succes) { 0 } else { 1 })
}
catch {
    Write-Resultat ([pscustomobject]@{ Succes = $false; Etape = 'erreur'; Message = $_.Exception.Message; VersionApi = 1 }) 2
}
