<#
.SYNOPSIS
    Dessine le schéma de l'API de règles du guide utilisateur (docs\images\80-api-regles.png).

.DESCRIPTION
    L'API n'a pas de fenêtre : l'image est un schéma (System.Drawing, aucun accès au moteur ni aux fichiers).
    À relancer si le fonctionnement de l'API change (étapes, noms de fonctions, fichiers écrits).

.PARAMETER Sortie
    Fichier PNG à écrire (défaut : docs\images\80-api-regles.png).
.PARAMETER Echelle
    Agrandissement (1,25 par défaut, comme les images des fenêtres).
#>
[CmdletBinding()]
param(
    [string] $Sortie,
    [double] $Echelle = 1.25
)
Add-Type -AssemblyName System.Drawing
if (-not $Sortie) { $Sortie = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'docs\images\80-api-regles.png' }

$largeur = 1000; $hauteur = 640
$bmp = New-Object System.Drawing.Bitmap ([int]($largeur * $Echelle)), ([int]($hauteur * $Echelle))
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.ScaleTransform([single]$Echelle, [single]$Echelle)
$g.SmoothingMode = 'AntiAlias'
$g.TextRenderingHint = 'ClearTypeGridFit'
$g.Clear([System.Drawing.Color]::White)

$couleur = { param($hex) [System.Drawing.ColorTranslator]::FromHtml($hex) }
$police = { param($taille, $gras) New-Object System.Drawing.Font('Segoe UI', $taille, $(if ($gras) { [System.Drawing.FontStyle]::Bold } else { [System.Drawing.FontStyle]::Regular })) }
$encre = & $couleur '#1F2933'
$bleu = & $couleur '#1F6FB2'
$centre = New-Object System.Drawing.StringFormat
$centre.Alignment = 'Center'; $centre.LineAlignment = 'Center'

$boite = {
    param($x, $y, $l, $h, $fond, $bord, $titre, $texte)
    $r = New-Object System.Drawing.Rectangle $x, $y, $l, $h
    $g.FillRectangle((New-Object System.Drawing.SolidBrush (& $couleur $fond)), $r)
    $g.DrawRectangle((New-Object System.Drawing.Pen (& $couleur $bord), 1.5), $r)
    $zone = New-Object System.Drawing.RectangleF ($x + 6), $y, ($l - 12), $h
    if ($texte) {
        $zt = New-Object System.Drawing.RectangleF ($x + 6), ($y + 6), ($l - 12), 22
        $g.DrawString($titre, (& $police 10 $true), (New-Object System.Drawing.SolidBrush $encre), $zt, $centre)
        $zc = New-Object System.Drawing.RectangleF ($x + 8), ($y + 28), ($l - 16), ($h - 32)
        $g.DrawString($texte, (& $police 8.5 $false), (New-Object System.Drawing.SolidBrush $encre), $zc, $centre)
    }
    else { $g.DrawString($titre, (& $police 10 $true), (New-Object System.Drawing.SolidBrush $encre), $zone, $centre) }
}
$fleche = {
    param($x1, $y1, $x2, $y2)
    $stylo = New-Object System.Drawing.Pen $bleu, 2
    $stylo.CustomEndCap = New-Object System.Drawing.Drawing2D.AdjustableArrowCap 5, 6
    $g.DrawLine($stylo, $x1, $y1, $x2, $y2)
}
$etiquette = {
    param($x, $y, $l, $texte, $gras)
    $g.DrawString($texte, (& $police 9 $gras), (New-Object System.Drawing.SolidBrush $bleu), (New-Object System.Drawing.RectangleF $x, $y, $l, 20), $centre)
}

$g.DrawString("API de règles : un seul module écrit le fichier des règles", (& $police 14 $true), (New-Object System.Drawing.SolidBrush $encre), (New-Object System.Drawing.RectangleF 0, 8, $largeur, 30), $centre)

# Appelants
& $boite 30 60 280 74 '#E8F1FA' '#1F6FB2' 'Interface graphique' "Enregistrer, Activer, Supprimer...`n(fenêtres de l'outil)"
& $boite 360 60 280 74 '#E8F1FA' '#1F6FB2' 'Script PowerShell' "Add-CopieApiRegle`nSet-CopieApiRegle, Remove-CopieApiRegle"
& $boite 690 60 280 74 '#E8F1FA' '#1F6FB2' 'Script Python' "copie_regles_client.py`n(passe par Invoke-RegleApi.ps1, JSON)"
& $fleche 170 134 170 176
& $fleche 500 134 500 176
& $fleche 830 134 830 176

# Module
$mx = 30; $my = 176; $ml = 940; $mh = 250
$g.FillRectangle((New-Object System.Drawing.SolidBrush (& $couleur '#F4F8EC')), $mx, $my, $ml, $mh)
$g.DrawRectangle((New-Object System.Drawing.Pen (& $couleur '#5B8C2A'), 2), $mx, $my, $ml, $mh)
$g.DrawString("Module FileManagement.Regles : le seul qui écrit le fichier", (& $police 11 $true), (New-Object System.Drawing.SolidBrush $encre), (New-Object System.Drawing.RectangleF $mx, ($my + 4), $ml, 24), $centre)
$etapes = @(
    @('1. Droits', "Le compte est dans`nAcces.GroupesAdmin ?"),
    @('2. Format', "Champs absents complétés`npar le modèle du moteur"),
    @('3. Conflit', "Le fichier a-t-il changé`ndepuis la lecture ?`n(empreinte)"),
    @('4. Vérification', "Le moteur contrôle un`nbrouillon : refus ou`navertissements"),
    @('5. Version', "L'ancien fichier est`nconservé avec le`ncommentaire"),
    @('6. Écriture', "Remplacement atomique :`njamais à moitié écrit")
)
$ex = 48
foreach ($e in $etapes) {
    & $boite $ex ($my + 40) 140 100 '#FFFFFF' '#5B8C2A' $e[0] $e[1]
    $ex += 150
}
for ($i = 0; $i -lt 5; $i++) { & $fleche (48 + 140 + $i * 150) ($my + 90) (48 + 150 + $i * 150) ($my + 90) }
$g.DrawString("Un refus à une étape quelconque (droits, conflit, moteur) : rien n'est écrit, la réponse dit laquelle et pourquoi.", (& $police 9 $false), (New-Object System.Drawing.SolidBrush $encre), (New-Object System.Drawing.RectangleF $mx, ($my + 156), $ml, 22), $centre)
& $boite 48 ($my + 186) 906 52 '#FFF7E0' '#C79A00' 'Le moteur Python définit le format' "Les appelants ne fournissent que ce qui compte ; si le format évolue, le module suit (modèle du moteur), pas les appelants. Le moteur n'écrit jamais le fichier."

# Résultats
& $fleche 170 426 170 470
& $fleche 500 426 500 470
& $fleche 830 426 830 470
& $boite 30 470 280 80 '#FFFFFF' '#52606D' 'Fichier des règles' "parametrage\<environnement>.jsonl`nnouvelle version"
& $boite 360 470 280 80 '#FFFFFF' '#52606D' 'Dossier des versions' "versions\<env>_<date>_<compte>.jsonl`n+ fiche .meta.json (qui, quand, pourquoi)"
& $boite 690 470 280 80 '#FFFFFF' '#52606D' "Journal de l'API" "ApiRegles_AAAA-MM-JJ.jsonl`naction, règle, appelant, compte, résultat"
$g.DrawString("Même contrôle de conflit et mêmes versions que l'interface : une modification faite par un script apparaît dans l'historique comme une version `"[API nom_du_script] commentaire`".", (& $police 9 $false), (New-Object System.Drawing.SolidBrush $encre), (New-Object System.Drawing.RectangleF 30, 570, 940, 40), $centre)

$dossier = Split-Path -Parent $Sortie
if (-not (Test-Path -LiteralPath $dossier)) { $null = New-Item -ItemType Directory -Path $dossier }
$bmp.Save((Join-Path (Resolve-Path -LiteralPath $dossier).ProviderPath (Split-Path -Leaf $Sortie)), [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Host ('Image écrite : ' + $Sortie)
