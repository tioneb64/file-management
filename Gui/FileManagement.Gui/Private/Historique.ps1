function Get-CopieHistorique {
    <#
    .SYNOPSIS
        Versions successives d'un fichier de paramétrage, de la plus récente à la plus ancienne.

    .DESCRIPTION
        Chaque enregistrement de l'interface copie l'ancienne version dans le dossier des versions
        (<environnement>_<AAAAMMJJ>_<hhmmss>_<compte>.jsonl) et écrit à côté une fiche .meta.json (compte,
        date, commentaire). Une entrée décrit donc UN changement : le contenu du fichier versionné est l'état
        d'AVANT, l'état d'APRÈS est la version suivante (ou le fichier actuel pour la plus récente). Une
        version sans fiche (copiée à la main) est listée avec le compte et la date lus dans son nom.

    .PARAMETER Fichier
        Fichier de paramétrage actuel.

    .PARAMETER Config
        Configuration (Parametrage.DossierVersions).

    .OUTPUTS
        [pscustomobject[]] Copie.Version : Fichier (état d'avant), Apres (fichier d'état d'après), Date, Compte,
        Commentaire, Avertissements, AFiche.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject[]])]
    param([Parameter(Mandatory)] [string] $Fichier, [Parameter(Mandatory)] [pscustomobject] $Config)

    $nom = [System.IO.Path]::GetFileNameWithoutExtension($Fichier)
    $dossierVersions = Join-Path (Split-Path -Parent $Fichier) $Config.Parametrage.DossierVersions
    if (-not (Test-Path -LiteralPath $dossierVersions -PathType Container)) { return @() }
    $modele = '^{0}_(\d{{8}})_(\d{{6}})_(.+)\.jsonl$' -f [regex]::Escape($nom)
    $versions = New-Object System.Collections.Generic.List[object]
    foreach ($f in @(Get-ChildItem -LiteralPath $dossierVersions -Filter '*.jsonl' -File)) {
        $m = [regex]::Match($f.Name, $modele)
        if (-not $m.Success) { continue }
        $date = [datetime]::MinValue
        $null = [datetime]::TryParseExact($m.Groups[1].Value + $m.Groups[2].Value, 'yyyyMMddHHmmss', [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::None, [ref]$date)
        $dateIncoherente = $false
        $compte = $m.Groups[3].Value
        $commentaire = ''
        $avertissements = @()
        $afiche = $false
        $fiche = $f.FullName -replace '\.jsonl$', '.meta.json'
        if (Test-Path -LiteralPath $fiche -PathType Leaf) {
            try {
                $meta = [System.IO.File]::ReadAllText($fiche, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                $afiche = $true
                if ($meta.compte) { $compte = "$($meta.compte)" }
                if ($meta.commentaire) { $commentaire = "$($meta.commentaire)" }
                if ($meta.avertissements) { $avertissements = @($meta.avertissements | ForEach-Object { "$_" }) }
                $utc = [datetime]::MinValue
                if ($meta.date -and [datetime]::TryParse("$($meta.date)", [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::AdjustToUniversal -bor [System.Globalization.DateTimeStyles]::AssumeUniversal, [ref]$utc)) {
                    # La date de la fiche (UTC) sert à l'affichage tant qu'elle concorde avec le nom du fichier ; une fiche
                    # écrite à la main avec une date fausse ne doit pas faire apparaître l'historique dans le désordre.
                    if ($date -eq [datetime]::MinValue -or [math]::Abs(($utc.ToLocalTime() - $date).TotalMinutes) -le 5) { $date = $utc.ToLocalTime() }
                    else { $dateIncoherente = $true }
                }
            }
            catch { $commentaire = '(fiche illisible)' }
        }
        $versions.Add([pscustomobject]@{ PSTypeName = 'Copie.Version'; Fichier = $f.FullName; Apres = $null; Date = $date; Compte = $compte
                Commentaire = $commentaire; Avertissements = $avertissements; AFiche = $afiche; DateIncoherente = $dateIncoherente; Cle = $f.Name })
    }
    # Ordre chronologique (le nom du fichier commence par l'horodatage : comparaison ordinale, sans règle de langue).
    $liste = $versions.ToArray()
    [array]::Sort($liste, [System.Comparison[object]] { param($a, $b) [string]::CompareOrdinal($a.Cle, $b.Cle) })
    for ($i = 0; $i -lt $liste.Count; $i++) { $liste[$i].Apres = $(if ($i -lt $liste.Count - 1) { $liste[$i + 1].Fichier } else { $Fichier }) }
    # Résultat : les plus récentes en premier.
    [array]::Reverse($liste)
    $liste
}

function Get-CopieFeuille {
    <#
    .SYNOPSIS
        Aplatit un objet JSON en chemin -> valeur lisible (pour comparer deux règles champ par champ).
    .PARAMETER Objet
        Objet issu de ConvertFrom-Json.
    .PARAMETER Prefixe
        Chemin déjà parcouru.
    .OUTPUTS
        [System.Collections.Specialized.OrderedDictionary]
    #>
    [CmdletBinding()]
    param([AllowNull()] $Objet, [string] $Prefixe = '')
    $sortie = [ordered]@{}
    if ($Objet -is [pscustomobject]) {
        foreach ($p in $Objet.PSObject.Properties) {
            if ($p.Name -eq 'Ligne') { continue }
            $chemin = $(if ($Prefixe) { $Prefixe + '.' + $p.Name } else { $p.Name })
            if ($p.Value -is [pscustomobject]) {
                $sous = Get-CopieFeuille -Objet $p.Value -Prefixe $chemin
                foreach ($k in $sous.Keys) { $sortie[$k] = $sous[$k] }
                if ($sous.Count -eq 0) { $sortie[$chemin] = '{}' }
            }
            else { $sortie[$chemin] = (Format-CopieValeurDiff $p.Value) }
        }
    }
    $sortie
}

function Format-CopieValeurDiff {
    <#
    .SYNOPSIS
        Valeur scalaire ou tableau -> texte comparable et lisible.
    .PARAMETER Valeur
        Valeur d'un champ.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([AllowNull()] $Valeur)
    if ($null -eq $Valeur) { return 'null' }
    if ($Valeur -is [bool]) { return $(if ($Valeur) { 'true' } else { 'false' }) }
    if ($Valeur -is [System.Array]) { return (ConvertTo-Json -InputObject $Valeur -Compress -Depth 10) }
    "$Valeur"
}

function Compare-CopieParametrage {
    <#
    .SYNOPSIS
        Différences entre deux états d'un fichier de paramétrage : en-tête, règles ajoutées, supprimées, modifiées.

    .DESCRIPTION
        Les règles sont rapprochées par identifiant (casse ignorée), pas par position : un simple
        déplacement dans le fichier n'est pas une modification. Les règles modifiées sont comparées champ par
        champ (chemin à points).

    .PARAMETER Avant
        Paramétrage d'avant (Read-CopieFichierParametrage).

    .PARAMETER Apres
        Paramétrage d'après.

    .OUTPUTS
        [pscustomobject[]] Regle, Changement (En-tête, Ajoutée, Supprimée, Modifiée), Champ, Avant, Apres.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject[]])]
    param([Parameter(Mandatory)] $Avant, [Parameter(Mandatory)] $Apres)

    $diff = New-Object System.Collections.Generic.List[object]
    $ligne = {
        param($regle, $changement, $champ, $a, $b)
        [pscustomobject]@{ Regle = $regle; Changement = $changement; Champ = $champ; Avant = $a; Apres = $b }
    }
    $fa = Get-CopieFeuille -Objet $Avant.Entete
    $fb = Get-CopieFeuille -Objet $Apres.Entete
    foreach ($k in @($fa.Keys) + @($fb.Keys | Where-Object { -not $fa.Contains($_) })) {
        $va = $(if ($fa.Contains($k)) { $fa[$k] } else { '' }); $vb = $(if ($fb.Contains($k)) { $fb[$k] } else { '' })
        if ($va -ne $vb) { $diff.Add((& $ligne '' 'En-tête' $k $va $vb)) }
    }
    $index = {
        param($regles)
        $h = [ordered]@{}
        foreach ($r in @($regles)) { $id = "$(Get-CopieValeur $r 'id' '')".ToLowerInvariant(); if ($id -and -not $h.Contains($id)) { $h[$id] = $r } }
        $h
    }
    $ra = & $index $Avant.Regles
    $rb = & $index $Apres.Regles
    foreach ($id in $ra.Keys) {
        if (-not $rb.Contains($id)) { $diff.Add((& $ligne (Get-CopieValeur $ra[$id] 'id') 'Supprimée' '' (Get-CopieValeur $ra[$id] 'description' '') '')) }
    }
    foreach ($id in $rb.Keys) {
        if (-not $ra.Contains($id)) { $diff.Add((& $ligne (Get-CopieValeur $rb[$id] 'id') 'Ajoutée' '' '' (Get-CopieValeur $rb[$id] 'description' ''))); continue }
        $a = Get-CopieFeuille -Objet $ra[$id]
        $b = Get-CopieFeuille -Objet $rb[$id]
        foreach ($k in @($a.Keys) + @($b.Keys | Where-Object { -not $a.Contains($_) })) {
            $va = $(if ($a.Contains($k)) { $a[$k] } else { '(absent)' }); $vb = $(if ($b.Contains($k)) { $b[$k] } else { '(absent)' })
            if ($va -ne $vb) { $diff.Add((& $ligne (Get-CopieValeur $rb[$id] 'id') 'Modifiée' $k $va $vb)) }
        }
    }
    $diff.ToArray()
}
