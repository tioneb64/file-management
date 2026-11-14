<#
    .SYNOPSIS
        Fabrique les images du guide utilisateur (docs\images) : de vraies fenêtres de l'interface, remplies avec un environnement d'exemple.

    .DESCRIPTION
        1. Crée sous -Destination un environnement d'exemple neutre (production et recette : règles, fichiers, bases
           initialisées) et le fait tourner une fois avec le moteur, pour que la liste des règles ait des statuts variés
           (succès, erreur, attente, bloquée...), des journaux et un historique de modifications.
        2. Ouvre l'interface sur cet environnement, met chaque fenêtre dans l'état voulu et l'enregistre en PNG dans -Images.
        3. Supprime l'environnement d'exemple (sauf avec -ConserverEssai).

        À relancer après toute modification de l'aspect d'une fenêtre : les images du guide (docs\11-guide-utilisateur.md) sont
        alors régénérées à l'identique. Le script écrit seulement sous -Destination et -Images. Il refuse un -Destination qui
        existe déjà (rien d'existant n'est jamais supprimé).

        Le compte affiché dans les fenêtres est un compte fictif (EXPLOIT\a.martin) : aucune information de la machine ne figure
        sur les images. À lancer avec Windows PowerShell 5.1 en mode STA (powershell.exe -STA).

    .PARAMETER Python
        Interpréteur Python qui exécute le moteur.

    .PARAMETER Destination
        Dossier de l'environnement d'exemple (défaut : C:\Echanges). Ne doit pas exister.

    .PARAMETER Images
        Dossier des images (défaut : docs\images à côté du guide).

    .PARAMETER Echelle
        Facteur d'agrandissement des images (1,25 = nettes sur un écran à 125 %).

    .PARAMETER Reutiliser
        Utilise un environnement d'exemple déjà créé (par une exécution précédente avec -ConserverEssai) au lieu d'en
        créer un ; il n'est pas supprimé à la fin (mise au point du script).

    .PARAMETER ConserverEssai
        Ne supprime pas l'environnement d'exemple à la fin.

    .EXAMPLE
        powershell.exe -STA -File .\Generer-ImagesGuide.ps1 -Python D:\Python\python.exe
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Python,
    [string] $Destination = 'C:\Echanges',
    [string] $Images,
    [string] $RacineMoteur,
    [double] $Echelle = 1.25,
    [switch] $Reutiliser,
    [switch] $ConserverEssai
)

$ErrorActionPreference = 'Stop'
if ($Echelle -le 0 -or $Echelle -gt 4) { throw '-Echelle : un nombre entre 0 et 4 est attendu.' }
if (-not (Test-Path -LiteralPath $Python)) { $Python = (Get-Command -Name $Python -ErrorAction Stop).Source }
if (-not $RacineMoteur) { $RacineMoteur = Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
if (-not $Images) { $Images = Join-Path $RacineMoteur 'docs\images' }
if (-not (Test-Path -LiteralPath (Join-Path $RacineMoteur 'file_management\__main__.py'))) { throw "Moteur introuvable dans $RacineMoteur" }
$Destination = [System.IO.Path]::GetFullPath($Destination)
$RacineExemple = Join-Path $Destination 'moteur'     # copie du moteur et des outils : les chemins affichés sur les images sont neutres
if (-not $Reutiliser -and (Test-Path -LiteralPath $Destination)) { throw "$Destination existe déjà : choisir un autre -Destination (rien n'est supprimé)." }
if ([System.Threading.Thread]::CurrentThread.GetApartmentState() -ne 'STA') { throw 'Lancer avec powershell.exe -STA.' }
Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase

$Compte = 'EXPLOIT\a.martin'
$Utf8 = New-Object System.Text.UTF8Encoding($false)
$Marqueur = '.environnement-exemple-guide'

# --------------------------------------------------------------------------------------------------------------------
# 1. Environnement d'exemple
# --------------------------------------------------------------------------------------------------------------------
function Write-Jsonl {
    param([string] $Fichier, [object[]] $Ligne)
    $texte = (($Ligne | ForEach-Object { $_ | ConvertTo-Json -Compress -Depth 10 }) -join "`n") + "`n"
    [System.IO.File]::WriteAllText($Fichier, $texte, $Utf8)
}
function New-Regle {
    param([string] $Id, [string] $Description, [string] $Mode, [hashtable] $Autres = @{})
    $r = [ordered]@{ id = $Id; description = $Description; actif = $true; mode = $Mode }
    foreach ($k in $Autres.Keys) { $r[$k] = $Autres[$k] }
    $r
}
function Write-Fichiers {
    param([string] $Dossier, [string[]] $Nom, [int] $AgeSec = 600)
    $null = New-Item -ItemType Directory -Force -Path $Dossier
    foreach ($n in $Nom) {
        $f = Join-Path $Dossier $n
        [System.IO.File]::WriteAllText($f, "id;nom`n1;exemple`n2;exemple`n", $Utf8)
        (Get-Item -LiteralPath $f).LastWriteTime = (Get-Date).AddSeconds(-$AgeSec)
    }
}
function Invoke-Moteur {
    param([string[]] $Argument)
    Push-Location $RacineExemple
    try { $sortie = & $Python -m file_management @Argument 2>&1 } finally { Pop-Location }
    $sortie
}

function New-EnvironnementExemple {
    $param = Join-Path $Destination 'parametrage'
    $null = New-Item -ItemType Directory -Force -Path $param
    $null = New-Item -ItemType Directory -Force -Path $RacineExemple
    foreach ($d in 'file_management', 'outils') { Copy-Item -LiteralPath (Join-Path $RacineMoteur $d) -Destination (Join-Path $RacineExemple $d) -Recurse }
    Copy-Item -LiteralPath (Join-Path $RacineMoteur 'journal_si.py') -Destination $RacineExemple
    Get-ChildItem -LiteralPath $RacineExemple -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
    [System.IO.File]::WriteAllText((Join-Path $Destination $Marqueur), 'Environnement d''exemple du guide : supprimé par Generer-ImagesGuide.ps1.', $Utf8)
    $prod = Join-Path $Destination 'production'
    $rec = Join-Path $Destination 'recette'
    $s = Join-Path $prod 'sources'
    Write-Fichiers (Join-Path $s 'clients') 'clients_001.csv', 'clients_002.csv', 'clients_003.csv'
    Write-Fichiers (Join-Path $s 'produits') 'produits_001.csv', 'produits_002.csv'
    Write-Fichiers (Join-Path $s 'ssis') 'ventes_001.csv', 'ventes_002.csv', 'ventes_003.csv'
    Write-Fichiers (Join-Path $s 'anciens') 'export_2025_01.log', 'export_2025_02.log' -AgeSec (400 * 86400)
    Write-Fichiers (Join-Path $s 'anciens') 'export_recent.log' -AgeSec 3600
    $null = New-Item -ItemType Directory -Force -Path (Join-Path $prod 'cibles')

    $toutes5min = [ordered]@{ type = 'intervalle'; frequence_sec = 300; debut = '00:00'; fin = '23:59'; jours = 'tous' }
    $quotidien = [ordered]@{ type = 'quotidien'; heure = '07:15'; jours = 'lun-ven'; rattrapage_sec = 14400 }
    $nuit = [ordered]@{ type = 'quotidien'; heure = '02:30'; jours = 'tous'; rattrapage_sec = 14400 }
    $suite = [ordered]@{ type = 'apres_dependances' }
    $sansAttente = @{ tentatives = 1; delai_sec = 0; niveau_final = 'ERREUR' }
    $enteteProd = [ordered]@{
        version = 1; environnement = 'production'; racine = $prod; racine_source = 'sources'; racine_cible = 'cibles'
        base = 'BDD\production.db'; dossier_logs = 'LOGS'; dossier_travail = 'TMP'; retention_journaux_jours = 90
    }
    $reglesProd = @(
        (New-Regle 'export_clients' 'Export des clients vers le partenaire' 'archivage' @{
                source = 'clients'; cible = 'clients'; archive = '.\archive\{AAAA}-{MM}-{JJ}'
                selection = [ordered]@{ masque = '*.csv'; age_minimum_sec = 60 }; planification = $toutes5min }),
        (New-Regle 'export_produits' 'Export du catalogue produits' 'deplacement' @{
                source = 'produits'; cible = 'produits'
                selection = [ordered]@{ masque = '*.csv;*.xml'; age_minimum_sec = 60 }; planification = $toutes5min }),
        (New-Regle 'import_catalogue' 'Import du catalogue dans l''ERP (après les deux exports)' 'copie' @{
                source = (Join-Path $prod 'cibles\produits'); cible = 'erp\catalogue'
                selection = [ordered]@{ masque = '*.csv'; age_minimum_sec = 60 }; planification = $quotidien
                apres = @('export_clients', 'export_produits'); condition = @('succes', 'fichiers') }),
        (New-Regle 'flux_ventes' 'Ventes déposées par le flux du magasin' 'copie' @{
                source = 'ventes'; cible = 'ventes'; selection = [ordered]@{ masque = '*.csv' }; planification = $toutes5min
                situations = [ordered]@{ source_inaccessible = $sansAttente } }),
        (New-Regle 'integration_ventes' 'Intégration des ventes (après le flux)' 'deplacement' @{
                source = 'ventes'; cible = 'ventes_integrees'; selection = [ordered]@{ masque = '*.csv' }; planification = $suite
                apres = @('flux_ventes'); condition = @('succes') }),
        (New-Regle 'attente_ssis' 'Attend les 5 fichiers du traitement SSIS' 'count' @{
                source = 'ssis'; selection = [ordered]@{ masque = '*.csv'; age_minimum_sec = 60 }; seuil_minimum = 5; planification = $toutes5min }),
        (New-Regle 'depot_ssis' 'Dépose les fichiers SSIS une fois les 5 arrivés' 'deplacement' @{
                source = 'ssis'; cible = 'ssis_livres'; selection = [ordered]@{ masque = '*.csv'; age_minimum_sec = 60 }; planification = $suite
                apres = @('attente_ssis'); condition = @('succes') }),
        (New-Regle 'menage_exports' 'Supprime les exports de plus de 365 jours' 'suppression' @{
                source = 'anciens'; selection = [ordered]@{ masque = '*.log'; age_minimum_sec = 31536000 }; planification = $nuit }),
        (New-Regle 'ancienne_regle' 'Ancien flux, désactivé' 'copie' @{
                actif = $false; source = 'clients'; cible = 'ancien'; selection = [ordered]@{ masque = '*.csv' }; planification = $quotidien })
    )
    Write-Jsonl (Join-Path $param 'production.jsonl') (@($enteteProd) + $reglesProd)

    $enteteRec = [ordered]@{
        version = 1; environnement = 'recette'; racine = $rec; racine_source = 'sources'; racine_cible = 'cibles'
        base = 'BDD\recette.db'; dossier_logs = 'LOGS'; dossier_travail = 'TMP'
    }
    Write-Fichiers (Join-Path $rec 'sources\clients') 'clients_001.csv'
    $reglesRec = @(
        (New-Regle 'export_clients' 'Export des clients (recette)' 'copie' @{
                source = 'clients'; cible = 'clients'; selection = [ordered]@{ masque = '*.csv' }; planification = $quotidien })
    )
    Write-Jsonl (Join-Path $param 'recette.jsonl') (@($enteteRec) + $reglesRec)

    $conf = @"
@{
    Acces = @{ GroupesAdmin = @('S-1-5-11') }
    Moteur = @{ Mode = 'Local'; Python = '$Python'; Racine = '$RacineExemple'; DelaiMaxSec = 120 }
    Parametrage = @{ Filtre = '*.jsonl'; VersionsSupportees = @(1); DossierVersions = 'versions'; DossierBrouillons = '.brouillons'; DossierSupprimes = '.supprimes'; PeriodeDeclencheurSec = 300 }
    Journal = @{ Dossier = ''; Environnement = 'prod' }
}
"@
    [System.IO.File]::WriteAllText((Join-Path $Destination 'Gestion-Copie.exemple.config.psd1'), $conf, $Utf8)

    foreach ($e in 'production', 'recette') {
        $sortie = Invoke-Moteur @('--config', (Join-Path $param "$e.jsonl"), '--initialiser-base')
        if ($LASTEXITCODE -ne 0) { throw "Base $e refusée : $sortie" }
    }
}

function Invoke-LancementsExemple {
    $fichier = Join-Path $Destination 'parametrage\production.jsonl'
    $null = Invoke-Moteur @('--config', $fichier, '--lancer-regle', 'export_clients', '--simulation')
    foreach ($id in 'export_clients', 'export_produits', 'flux_ventes', 'attente_ssis', 'menage_exports') {
        $null = Invoke-Moteur @('--config', $fichier, '--lancer-regle', $id)
    }
    $null = Invoke-Moteur @('--config', $fichier, '--lancer-regle', 'flux_ventes')
    $null = Invoke-Moteur @('--config', $fichier)
    # Nouveaux fichiers : les dernières exécutions des règles de copie livrent réellement quelque chose.
    $s = Join-Path $Destination 'production\sources'
    Write-Fichiers (Join-Path $s 'clients') 'clients_004.csv', 'clients_005.csv'
    Write-Fichiers (Join-Path $s 'produits') 'produits_003.csv', 'produits_004.csv', 'produits_005.xml'
    foreach ($id in 'export_clients', 'export_produits', 'import_catalogue') {
        $null = Invoke-Moteur @('--config', $fichier, '--lancer-regle', $id)
    }
}

# --------------------------------------------------------------------------------------------------------------------
# 2. Capture des fenêtres
# --------------------------------------------------------------------------------------------------------------------
function New-Brosse {
    param([string] $Couleur)
    $b = [System.Windows.Media.BrushConverter]::new().ConvertFromString($Couleur)
    $b.Freeze()
    $b
}

function Save-Image {
    <# Rend le contenu de la fenêtre en PNG, avec une barre de titre dessinée (le cadre de Windows n'est pas rendu par WPF). #>
    param([System.Windows.Window] $Fenetre, [string] $Nom)
    $Fenetre.UpdateLayout()
    $racine = [System.Windows.Media.VisualTreeHelper]::GetChild($Fenetre, 0)
    $largeur = [Math]::Ceiling($racine.ActualWidth)
    $hauteur = [Math]::Ceiling($racine.ActualHeight)
    $barre = 32
    $e = $Echelle
    $contenu = New-Object System.Windows.Media.Imaging.RenderTargetBitmap([int][Math]::Ceiling($largeur * $e), [int][Math]::Ceiling($hauteur * $e), (96 * $e), (96 * $e), [System.Windows.Media.PixelFormats]::Pbgra32)
    $contenu.Render($racine)
    $contenu.Freeze()

    $dv = New-Object System.Windows.Media.DrawingVisual
    $dc = $dv.RenderOpen()
    $culture = [System.Globalization.CultureInfo]::GetCultureInfo('fr-FR')
    $dc.DrawRectangle((New-Brosse '#FFFFFF'), $null, (New-Object System.Windows.Rect(0, 0, $largeur, ($hauteur + $barre))))
    $texte = New-Object System.Windows.Media.FormattedText($Fenetre.Title, $culture, [System.Windows.FlowDirection]::LeftToRight, (New-Object System.Windows.Media.Typeface('Segoe UI')), 12, (New-Brosse '#1A1A1A'), 1.0)
    $dc.DrawText($texte, (New-Object System.Windows.Point(12, (($barre - $texte.Height) / 2))))
    $glyphes = $(if ($Fenetre -eq $Script:FenetrePrincipale) { @([string][char]0xE921, [string][char]0xE922, [string][char]0xE8BB) } else { @([string][char]0xE8BB) })
    $x = $largeur - 46 * $glyphes.Count
    foreach ($g in $glyphes) {
        $t = New-Object System.Windows.Media.FormattedText($g, $culture, [System.Windows.FlowDirection]::LeftToRight, (New-Object System.Windows.Media.Typeface('Segoe MDL2 Assets')), 10, (New-Brosse '#1A1A1A'), 1.0)
        $dc.DrawText($t, (New-Object System.Windows.Point(($x + (46 - $t.Width) / 2), (($barre - $t.Height) / 2))))
        $x += 46
    }
    $dc.DrawImage($contenu, (New-Object System.Windows.Rect(0, $barre, $largeur, $hauteur)))
    $cadre = New-Object System.Windows.Media.Pen((New-Brosse '#6B7785'), 1)
    $dc.DrawRectangle($null, $cadre, (New-Object System.Windows.Rect(0.5, 0.5, ($largeur - 1), ($hauteur + $barre - 1))))
    $dc.Close()

    $final = New-Object System.Windows.Media.Imaging.RenderTargetBitmap([int][Math]::Ceiling($largeur * $e), [int][Math]::Ceiling(($hauteur + $barre) * $e), (96 * $e), (96 * $e), [System.Windows.Media.PixelFormats]::Pbgra32)
    $final.Render($dv)
    $enc = New-Object System.Windows.Media.Imaging.PngBitmapEncoder
    $enc.Frames.Add([System.Windows.Media.Imaging.BitmapFrame]::Create($final))
    $null = New-Item -ItemType Directory -Force -Path $Images
    $chemin = Join-Path $Images ($Nom + '.png')
    $flux = [System.IO.File]::Create($chemin)
    try { $enc.Save($flux) } finally { $flux.Close() }
    $Script:ImagesFaites.Add($Nom)
    Write-Host ('  image {0} ({1} x {2})' -f $Nom, [int]($largeur * $e), [int](($hauteur + $barre) * $e))
}

function Wait-Affichage {
    param([System.Windows.Window] $Fenetre)
    $Fenetre.Dispatcher.Invoke([action] {}, [System.Windows.Threading.DispatcherPriority]::ApplicationIdle)
    $Fenetre.UpdateLayout()
}

function Save-FenetreOuverte {
    <# Image d'une fenêtre déjà affichée (non modale), après un éventuel ajustement. #>
    param([System.Windows.Window] $Fenetre, [string] $Nom, [scriptblock] $Avant)
    if ($Avant) { & $Avant $Fenetre }
    Wait-Affichage $Fenetre
    Save-Image -Fenetre $Fenetre -Nom $Nom
}

# Boîtes modales : au chargement d'une fenêtre pendant « Invoke-Capturer », on la photographie puis on la ferme.
$Script:Demande = $null
$Script:ErreurCapture = $null
$gestionnaire = [System.Windows.RoutedEventHandler] {
    param($emetteur)
    if ($null -eq $Script:Demande -or $emetteur -isnot [System.Windows.Window] -or $emetteur -eq $Script:FenetrePrincipale) { return }
    $Script:Cible = $emetteur
    $Script:Photo = $Script:Demande
    $Script:Demande = $null
    $null = $emetteur.Dispatcher.BeginInvoke([System.Windows.Threading.DispatcherPriority]::ContextIdle, [System.Action] {
            try {
                if ($Script:Retouche) { & $Script:Retouche $Script:Cible }
                Wait-Affichage $Script:Cible
                Save-Image -Fenetre $Script:Cible -Nom $Script:Photo
            }
            catch { $Script:ErreurCapture = $_ }
            finally { $Script:Cible.Close() }
        })
}
[System.Windows.EventManager]::RegisterClassHandler([System.Windows.Window], [System.Windows.FrameworkElement]::LoadedEvent, $gestionnaire)

function Invoke-Capturer {
    <# Exécute -Ouvrir (qui doit afficher une boîte modale) et photographie cette boîte sous le nom -Nom. -Retouche règle la fenêtre avant la photo. #>
    param([string] $Nom, [scriptblock] $Ouvrir, [scriptblock] $Retouche)
    $Script:Demande = $Nom
    $Script:Retouche = $Retouche
    $Script:ErreurCapture = $null
    try { $null = & $Ouvrir } finally { $Script:Demande = $null; $Script:Retouche = $null }
    if ($Script:ErreurCapture) { throw ('Capture {0} : {1}' -f $Nom, $Script:ErreurCapture) }
    if (-not $Script:ImagesFaites.Contains($Nom)) { throw "Capture $Nom : aucune fenêtre n'a été ouverte." }
}

function Invoke-Module {
    param([scriptblock] $Bloc, [object[]] $Argument = @())
    & $Script:Module $Bloc @Argument
}

function Select-OngletPar {
    param($Tab, [string] $Titre)
    foreach ($o in $Tab.Items) { if ("$($o.Header)" -eq $Titre) { $Tab.SelectedItem = $o; return } }
    throw "Onglet introuvable : $Titre"
}

# Hauteur de la fenêtre portée à celle du contenu de l'onglet affiché du formulaire (rien n'est coupé sur l'image).
function Set-HauteurOnglet {
    param([System.Windows.Window] $Fenetre)
    $Fenetre.Height = 720
    Wait-Affichage $Fenetre
    $onglet = $Fenetre.FindName('Onglets').SelectedItem
    $defil = $onglet.Content
    $manque = $defil.ExtentHeight - $defil.ViewportHeight
    if ($manque -gt 0) {
        $Fenetre.Height = [Math]::Min(1500, 720 + $manque + 4)
        Wait-Affichage $Fenetre
    }
}

# --------------------------------------------------------------------------------------------------------------------
# 3. Les images
# --------------------------------------------------------------------------------------------------------------------
function Read-Regles {
    param([string] $Fichier)
    @(Get-Content -LiteralPath $Fichier -Encoding UTF8 | Select-Object -Skip 1 | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json })
}

function Get-Texte {
    <# Remplace, dans le texte visible, ce qui vient de la machine (compte, nom de la machine, chemin de Python) par des valeurs neutres. #>
    param([string] $Texte)
    $t = $Texte
    foreach ($r in @(@("$env:USERDOMAIN\$env:USERNAME", $Compte), @($Python, 'C:\Python312\python.exe'), @($env:COMPUTERNAME, 'SRV-EXPLOIT01'), @($RacineMoteur, 'C:\file_management'))) {
        if ($r[0]) { $t = $t.Replace($r[0], $r[1]) }
    }
    $t
}

function Get-RunsDe {
    param($Noeud)
    foreach ($e in [System.Windows.LogicalTreeHelper]::GetChildren($Noeud)) {
        if ($e -is [System.Windows.Documents.Run]) { $e }
        elseif ($e -is [System.Windows.DependencyObject]) { Get-RunsDe $e }
    }
}

function Hide-InfosLocales {
    <# Le journal de l'interface cite le compte Windows, la machine et le chemin de Python : on les remplace avant la photo. #>
    param([System.Windows.Window] $Fenetre)
    $boite = $Fenetre.FindName('LogBox')
    foreach ($run in @(Get-RunsDe $boite.Document)) { $run.Text = Get-Texte $run.Text }
}

function Save-Formulaire {
    <# Photographie un onglet d'un formulaire de règle (hauteur ajustée au contenu). #>
    param($Modele, $Regle, [string] $Mode, [string] $Nom, [string] $Onglet)
    $Script:Formulaire = @{ Modele = $Modele; Regle = $Regle; Mode = $Mode; Onglet = $Onglet }
    Invoke-Capturer -Nom $Nom -Ouvrir {
        $d = $Script:Formulaire
        Invoke-Module { param($c, $m, $r, $mode) $f = New-CopieFormulaireRegle -Contexte $c -Modele $m -Regle $r -Mode $mode; $null = $f.ShowDialog() } @($Script:Contexte, $d.Modele, $d.Regle, $d.Mode)
    } -Retouche {
        param($f)
        Select-OngletPar $f.FindName('Onglets') $Script:Formulaire.Onglet
        Set-HauteurOnglet $f
    }
}

function Get-RegleFormulaire {
    <# Règle complète (valeurs de secours du moteur + valeurs données) pour un formulaire. #>
    param($Modele, $Existante)
    Invoke-Module { param($m, $r) Merge-CopieRegle -Modele $m.regle -Existante $r } @($Modele, $Existante)
}

function Add-VersionsExemple {
    <# Quelques modifications faites « par l'interface » pour que l'historique ait du contenu. #>
    param($Modele, [string] $Fichier)
    $modifications = @(
        @{ Compte = 'EXPLOIT\a.martin'; Commentaire = "Fréquence d'export_produits portée à 10 minutes (demande de l'équipe exploitation)"
            Faire = { param($l) ($l | Where-Object { $_.id -eq 'export_produits' }).planification.frequence_sec = 600 } },
        @{ Compte = 'EXPLOIT\s.durand'; Commentaire = "Ancien flux désactivé, il n'est plus utilisé depuis la migration"
            Faire = { param($l) ($l | Where-Object { $_.id -eq 'ancienne_regle' }).description = 'Ancien flux, désactivé depuis la migration' } },
        @{ Compte = 'EXPLOIT\a.martin'; Commentaire = "Âge minimum d'export_clients : 2 minutes (fichiers encore en cours d'écriture)"
            Faire = { param($l) ($l | Where-Object { $_.id -eq 'export_clients' }).selection.age_minimum_sec = 120 } }
    )
    foreach ($m in $modifications) {
        $p = Invoke-Module { param($f) Read-CopieFichierParametrage -Chemin $f } @($Fichier)
        $liste = @($p.Regles | ForEach-Object { Get-RegleFormulaire $Modele $_ })
        & $m.Faire $liste
        $r = Invoke-Module { param($c, $f, $p, $l, $compte, $comm) Save-CopieParametrage -Config $c.Config -Fichier $f -EmpreinteAttendue $p.Empreinte -Entete $p.Entete -Regle $l -Compte $compte -Commentaire $comm -Confirmer { $true } } @($Script:Contexte, $Fichier, $p, $liste, $m.Compte, $m.Commentaire)
        if (-not $r.Enregistre) { throw "Version d'exemple refusée : $($r.Message)" }
        Start-Sleep -Milliseconds 1200       # le nom d'une version commence par l'horodatage à la seconde
    }
}

function New-ImagesGuide {
    $parametrage = Join-Path $Destination 'parametrage'
    $fichierProd = Join-Path $parametrage 'production.jsonl'
    $configuration = Join-Path $Destination 'Gestion-Copie.exemple.config.psd1'
    $Script:ImagesFaites = New-Object System.Collections.Generic.List[string]
    $Script:FenetrePrincipale = $null
    Import-Module (Join-Path $RacineMoteur 'Gui\FileManagement.Gui\FileManagement.Gui.psd1') -Force
    $Script:Module = Get-Module 'FileManagement.Gui'

    $fenetre = Start-CopieGui -DossierParametrage $parametrage -Config $configuration -SansAffichage -GroupeUtilisateur @('S-1-5-11')
    $Script:FenetrePrincipale = $fenetre
    try {
        $fenetre.WindowStartupLocation = 'Manual'; $fenetre.Left = 10; $fenetre.Top = 10
        $fenetre.Height = 1040
        $fenetre.FindName('UserText').Text = $Compte
        Invoke-Module { param($c) $Script:Session.Contexte.Utilisateur = $c } @($Compte)
        $fenetre.Show()
        Invoke-Module { Wait-CopieTache }
        Wait-Affichage $fenetre
        $Script:Contexte = Invoke-Module { $Script:Session.Contexte }
        $tabs = $fenetre.FindName('Tabs')
        Select-OngletPar $tabs 'production'
        $vue = $tabs.SelectedItem.Tag
        $grille = $vue.Grille
        $choisir = { param($id) $grille.SelectedItem = @($grille.ItemsSource | Where-Object { $_.Id -eq $id })[0]; Wait-Affichage $fenetre }
        $photoPrincipale = {
            param($nom)
            Hide-InfosLocales $fenetre
            Save-FenetreOuverte $fenetre $nom
        }
        $onglets = $vue.Tab.FindName('Onglets')

        # --- Fenêtre principale ---------------------------------------------------------------------------------------
        & $choisir 'export_clients'
        $onglets.SelectedIndex = 0
        & $photoPrincipale '01-fenetre-principale'
        $onglets.SelectedIndex = 1
        & $photoPrincipale '02-onglet-dependances'
        & $choisir 'integration_ventes'
        $onglets.SelectedIndex = 2
        & $photoPrincipale '03-regle-bloquee'
        & $choisir 'attente_ssis'
        & $photoPrincipale '04-regle-en-attente'
        & $choisir 'flux_ventes'
        & $photoPrincipale '05-regle-en-erreur'
        $onglets.SelectedIndex = 0
        $vue.Recherche.Text = 'export'
        Wait-Affichage $fenetre
        & $photoPrincipale '06-recherche'
        $vue.Recherche.Text = ''
        $vue.FiltreStatut.SelectedIndex = 0
        Wait-Affichage $fenetre
        Select-OngletPar $tabs 'Outils'
        Wait-Affichage $fenetre
        & $photoPrincipale '07-onglet-outils-vide'
        $vueOutils = $tabs.SelectedItem.Tag
        Invoke-Capturer -Nom '08-scan-outils' -Ouvrir { Invoke-Module { param($v) Invoke-CopieScanOutils -Vue $v -Dossier '' } @($vueOutils) }
        Wait-Affichage $fenetre
        $vueOutils.Grille.SelectedItem = @($vueOutils.Grille.ItemsSource | Where-Object { "$($_.Variable)" -match 'zip_creer' } | Select-Object -First 1)[0]
        Wait-Affichage $fenetre
        & $photoPrincipale '09-onglet-outils'
        Select-OngletPar $tabs 'production'

        # --- Formulaire d'une règle -----------------------------------------------------------------------------------
        $modele = Invoke-Module { param($c) Get-CopieModeleRegle -Config $c.Config } @($Script:Contexte)
        $existantes = Read-Regles $fichierProd
        $regle = { param($id) Get-RegleFormulaire $modele ($existantes | Where-Object { $_.id -eq $id }) }
        $export = & $regle 'export_clients'
        Save-Formulaire $modele $export 'modification' '10-regle-general' 'Général'
        Save-Formulaire $modele $export 'modification' '11-regle-selection' 'Sélection'
        Save-Formulaire $modele $export 'modification' '12-regle-anti-doublon' 'Anti-doublon et nommage'
        Save-Formulaire $modele $export 'modification' '13-regle-planification-intervalle' 'Planification'
        Save-Formulaire $modele (& $regle 'import_catalogue') 'modification' '14-regle-planification-quotidien' 'Planification'
        Save-Formulaire $modele (& $regle 'integration_ventes') 'modification' '15-regle-planification-apres-dependances' 'Planification'
        Save-Formulaire $modele (& $regle 'import_catalogue') 'modification' '16-regle-dependances' 'Dépendances'
        Save-Formulaire $modele $export 'modification' '17-regle-duree-erreurs' 'Durée et erreurs'
        Save-Formulaire $modele $export 'modification' '18-regle-situations' 'Situations'
        Save-Formulaire $modele $export 'modification' '19-regle-purge' 'Purge'
        $zip = Get-RegleFormulaire $modele ([pscustomobject]@{
                id = 'archives_zip'; description = 'Compresse la livraison dans un fichier ZIP'; mode = 'copie'; source = 'clients'; cible = 'clients'
                programmes = [pscustomobject]@{ apres_lot = [pscustomobject]@{ commande = @('{outil:zip_creer}', '--sortie', '{cible}\lot.zip', '--liste', '{liste}'); timeout_sec = 600 } } })
        Save-Formulaire $modele $zip 'ajout' '20-regle-programmes' 'Programmes'
        Save-Formulaire $modele (Get-RegleFormulaire $modele $null) 'ajout' '21-nouvelle-regle-general' 'Général'
        Save-Formulaire $modele (& $regle 'attente_ssis') 'modification' '22-mode-count' 'Général'
        Save-Formulaire $modele (& $regle 'menage_exports') 'modification' '23-mode-suppression' 'Général'
        $synchro = Get-RegleFormulaire $modele ([pscustomobject]@{ id = 'statut_traitement'; description = 'Retourne un statut après le traitement des exports'; mode = 'synchro'; apres = @('export_clients') })
        Save-Formulaire $modele $synchro 'ajout' '24-mode-synchro' 'Général'
        $factures = Get-RegleFormulaire $modele ([pscustomobject]@{ id = 'export_factures'; description = 'Export des factures vers le comptable'; mode = 'archivage'
                source = 'factures'; cible = 'comptabilite'; archive = '.\archive\{AAAA}-{MM}-{JJ}'
                selection = [pscustomobject]@{ masque = '*.pdf;*.xml'; exclure = '~*;*.tmp'; age_minimum_sec = 120 }
                planification = [pscustomobject]@{ type = 'quotidien'; heure = '18:30'; jours = @('lun', 'mar', 'mer', 'jeu', 'ven') } })
        Save-Formulaire $modele $factures 'ajout' '26-exemple-regle-general' 'Général'
        Save-Formulaire $modele $factures 'ajout' '27-exemple-regle-selection' 'Sélection'
        Save-Formulaire $modele $factures 'ajout' '28-exemple-regle-planification' 'Planification'
        $declencheur = Get-RegleFormulaire $modele ([pscustomobject]@{ id = 'depot_partenaire'; description = 'Dépose les fichiers quand le partenaire a posé le témoin'; mode = 'copie'
                source = 'depot'; cible = 'depot'; fichier_declencheur = '*.ok'; consommer_declencheur = $true; temoin_cible = 'fin.ok' })
        Save-Formulaire $modele $declencheur 'ajout' '25-fichier-declencheur' 'Général'

        # --- Vérifier le paramétrage ----------------------------------------------------------------------------------
        Invoke-Capturer -Nom '30-verification-valide' -Ouvrir {
            Invoke-Module { param($c, $f) $r = Invoke-CopieMoteur -Config $c.Config -Fichier $f -Argument @('--verifier', '--periode-declencheur-sec', '300'); Show-CopieDiagnostics -Contexte $c -Reponse $r } @($Script:Contexte, $fichierProd)
        }
        $brouillon = Join-Path $Destination 'brouillon'
        $null = New-Item -ItemType Directory -Force -Path $brouillon
        $lignes = @(Get-Content -LiteralPath $fichierProd -Encoding UTF8)
        $mauvaises = @(
            (New-Regle 'copie_sans_cible' 'Oubli de la cible' 'copie' @{ source = 'clients'; selection = [ordered]@{ masque = '*.csv' }; planification = [ordered]@{ type = 'quotidien'; heure = '08:00'; jours = 'tous'; rattrapage_sec = 3600 } }),
            (New-Regle 'depend_de_rien' 'Dépend d''une règle qui n''existe pas' 'copie' @{ source = 'clients'; cible = 'clients'; selection = [ordered]@{ masque = '*.csv' }; planification = [ordered]@{ type = 'apres_dependances' }; apres = @('regle_absente'); condition = @('succes') }),
            (New-Regle 'menage_test' 'Supprime les fichiers temporaires' 'suppression' @{ source = 'tmp'; selection = [ordered]@{ masque = '*.tmp' }; planification = [ordered]@{ type = 'intervalle'; frequence_sec = 3600; debut = '00:00'; fin = '23:59'; jours = 'tous' } })
        )
        [System.IO.File]::WriteAllText((Join-Path $brouillon 'production.jsonl'), (($lignes -join "`n") + "`n" + (($mauvaises | ForEach-Object { $_ | ConvertTo-Json -Compress -Depth 10 }) -join "`n") + "`n"), $Utf8)
        Invoke-Capturer -Nom '31-verification-refus' -Ouvrir {
            Invoke-Module { param($c, $f) $r = Invoke-CopieMoteur -Config $c.Config -Fichier $f -Argument @('--verifier', '--periode-declencheur-sec', '300'); Show-CopieDiagnostics -Contexte $c -Reponse $r } @($Script:Contexte, (Join-Path $brouillon 'production.jsonl'))
        }

        # --- Contrôle des répertoires, simulation ---------------------------------------------------------------------
        Invoke-Capturer -Nom '32-controle-repertoires' -Ouvrir {
            Invoke-Module {
                param($c, $v)
                $titre = 'Contrôle des répertoires'
                $faits = @(New-CopieLigneResultat -Gravite 'Information' -Sujet 'Enregistrement' -Message ('La règle « flux_ventes » est enregistrée dans {0}.' -f $v.Env.Nom))
                $r = Invoke-CopieMoteur -Config $c.Config -Fichier $v.Env.Fichier -Argument @('--controler-regle', 'flux_ventes')
                $controles = @(ConvertTo-CopieControleSimulation -Controle @($r.Json.controles))
                $lignes = @($faits) + @(ConvertTo-CopieLignesResultatControle -Controle $controles) + @(New-CopieLigneResultat -Gravite 'Information' -Sujet 'À faire' -Message 'Corrigez la règle (Modifier) ou les droits, puis relancez « Simuler la règle ».')
                Show-CopieResultat -Contexte $c -Titre $titre -Resume (Get-CopieResumeResultat -Ligne $lignes -Debut ('Règle « flux_ventes » enregistrée. Répertoires contrôlés avec {0}.' -f $c.Utilisateur)) -Ligne $lignes
            } @($Script:Contexte, $vue)
        }
        $s = Join-Path $Destination 'production\sources'
        Write-Fichiers (Join-Path $s 'produits') 'produits_010.csv', 'produits_011.csv', 'produits_012.xml'
        Invoke-Capturer -Nom '33-simulation' -Ouvrir {
            Invoke-Module {
                param($c, $v)
                $r = Invoke-CopieMoteur -Config $c.Config -Fichier $v.Env.Fichier -Argument @('--lancer-regle', 'export_produits', '--simulation')
                $null = Show-CopieSimulation -Contexte $c -Regle 'export_produits' -Resume (ConvertTo-CopieResumeSimulation -Json $r.Json)
            } @($Script:Contexte, $vue)
        }

        # --- Journaux d'une règle -------------------------------------------------------------------------------------
        & $choisir 'flux_ventes'
        Invoke-Capturer -Nom '40-journaux-erreur' -Ouvrir { Invoke-Module { param($v) Show-CopieJournaux -Vue $v; Wait-CopieTache } @($vue) }
        & $choisir 'export_clients'
        Invoke-Capturer -Nom '41-journaux-succes' -Ouvrir { Invoke-Module { param($v) Show-CopieJournaux -Vue $v; Wait-CopieTache } @($vue) } -Retouche {
            param($f)
            $f.FindName('Executions').SelectedIndex = 0
            Wait-Affichage $f
            $g = $f.FindName('Evenements')
            $ligne = @($g.ItemsSource | Where-Object { $_.Message -match '^Fichier livre' } | Select-Object -First 1)
            if ($ligne.Count -gt 0) { $g.SelectedItem = $ligne[0]; $g.ScrollIntoView($ligne[0]) }
        }

        # --- Dialogues divers -----------------------------------------------------------------------------------------
        Invoke-Capturer -Nom '50-commentaire' -Ouvrir {
            Invoke-Module { param($c) Read-CopieCommentaire -Contexte $c -Question 'Vous allez modifier la règle « export_clients » dans production.' } @($Script:Contexte)
        } -Retouche { param($f) $f.FindName('Commentaire').Text = "Âge minimum porté à 2 minutes : des fichiers étaient lus pendant leur écriture (ticket 4521)." }
        Select-OngletPar $tabs 'recette'
        $vueRecette = $tabs.SelectedItem.Tag
        Select-OngletPar $tabs 'production'
        Invoke-Capturer -Nom '51-promotion' -Ouvrir {
            Invoke-Module { param($c, $regle, $cibles) Show-CopiePromotion -Contexte $c -Regle $regle -Source 'production' -Cibles $cibles } @($Script:Contexte, ($existantes | Where-Object { $_.id -eq 'export_clients' }), @($vueRecette))
        } -Retouche { param($f) $f.FindName('Chercher').Text = 'production'; $f.FindName('Remplacer').Text = 'recette' }
        $purge = [pscustomobject]@{ Json = [pscustomobject]@{
                message = '3 élément(s) à purger (12,4 Mo).'
                a_purger = @(
                    [pscustomobject]@{ type = 'journal'; regle = 'export_clients'; chemin = 'C:\Echanges\production\LOGS\export_clients_2026-08-02.jsonl'; date = '2026-08-02'; octets = 1572864 },
                    [pscustomobject]@{ type = 'journal'; regle = 'export_produits'; chemin = 'C:\Echanges\production\LOGS\export_produits_2026-08-02.jsonl'; date = '2026-08-02'; octets = 2097152 },
                    [pscustomobject]@{ type = 'archive'; regle = 'export_clients'; chemin = 'C:\Echanges\production\sources\archive\2026-05-30'; date = '2026-05-30'; octets = 9437184 })
                erreurs_regles = @(); ignores = @() } }
        Invoke-Capturer -Nom '52-purge' -Ouvrir { Invoke-Module { param($c, $r) Show-CopiePurge -Contexte $c -Reponse $r } @($Script:Contexte, $purge) }
        $incertains = @(
            [pscustomobject]@{ cle = 'export_clients|clients_004.csv|1'; source = 'C:\Echanges\production\sources\clients\clients_004.csv'; cible = 'C:\Echanges\production\cibles\clients\clients_004.csv' },
            [pscustomobject]@{ cle = 'export_clients|clients_005.csv|1'; source = 'C:\Echanges\production\sources\clients\clients_005.csv'; cible = 'C:\Echanges\production\cibles\clients\clients_005.csv' })
        Invoke-Capturer -Nom '53-livraisons-incertaines' -Ouvrir {
            Invoke-Module { param($c, $i) Show-CopieIncertain -Contexte $c -Regle 'export_clients' -Incertain $i } @($Script:Contexte, $incertains)
        } -Retouche {
            param($f)
            $f.FindName('Grille').SelectedIndex = 0
            $f.FindName('DecisionLivre').IsChecked = $true
            $f.FindName('Commentaire').Text = "Fichier présent chez le partenaire (vérifié avec lui par téléphone, taille identique)."
        }

        # --- Environnements -------------------------------------------------------------------------------------------
        Invoke-Capturer -Nom '60-environnement-nouveau' -Ouvrir {
            Invoke-Module { param($c) Read-CopieSaisieEnvironnement -Contexte $c -Mode 'creation' -Existants @() } @($Script:Contexte)
        } -Retouche {
            param($f)
            $valeurs = [ordered]@{ Nom = 'preprod'; Racine = 'C:\Echanges\preprod'; RacineSource = 'sources'; RacineCible = 'cibles'; Base = 'BDD\preprod.db'; DossierLogs = 'LOGS'; DossierTravail = 'TMP' }
            foreach ($k in $valeurs.Keys) { $f.FindName($k).Text = $valeurs[$k] }
        }
        $saisieProd = Invoke-Module { param($p) ConvertFrom-CopieEnteteEnvironnement -Entete $p.Entete } @((Invoke-Module { param($f) Read-CopieFichierParametrage -Chemin $f } @($fichierProd)))
        Invoke-Capturer -Nom '61-environnement-modifier' -Ouvrir {
            Invoke-Module { param($c, $s) Read-CopieSaisieEnvironnement -Contexte $c -Mode 'modification' -Saisie $s -Existants @() } @($Script:Contexte, $saisieProd)
        }
        Invoke-Capturer -Nom '62-environnement-copier' -Ouvrir {
            Invoke-Module { param($c, $s) Read-CopieSaisieEnvironnement -Contexte $c -Mode 'copie' -Saisie $s -Existants @() } @($Script:Contexte, $saisieProd)
        } -Retouche { param($f) $f.FindName('Nom').Text = 'preprod'; $f.FindName('Racine').Text = 'C:\Echanges\preprod' }
        Invoke-Capturer -Nom '63-environnement-supprimer' -Ouvrir {
            Invoke-Module { param($c) Read-CopieConfirmationSuppression -Contexte $c -Nom 'recette' } @($Script:Contexte)
        } -Retouche { param($f) $f.FindName('Nom').Text = 'recette'; $f.FindName('Commentaire').Text = 'Remplacé par preprod' }

        # --- Historique (en dernier : il modifie le fichier de production) ---------------------------------------------
        Add-VersionsExemple $modele $fichierProd
        Invoke-Capturer -Nom '70-historique' -Ouvrir { Invoke-Module { param($v) Show-CopieHistorique -Vue $v } @($vue) }
    }
    finally { $fenetre.Close() }
}

# --------------------------------------------------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------------------------------------------------
$etaitNouveau = -not $Reutiliser
try {
    if ($etaitNouveau) {
        Write-Host "Création de l'environnement d'exemple dans $Destination"
        New-EnvironnementExemple
        Invoke-LancementsExemple
    }
    Write-Host "Images dans $Images"
    New-ImagesGuide
    Write-Host ('{0} image(s) écrite(s).' -f $Script:ImagesFaites.Count)
}
finally {
    if ($etaitNouveau -and -not $ConserverEssai -and (Test-Path -LiteralPath (Join-Path $Destination $Marqueur))) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
        Write-Host "Environnement d'exemple supprimé."
    }
}
