function ConvertTo-CopieLigneJson {
    <#
    .SYNOPSIS
        Objet (en-tête ou règle) -> une ligne JSON compacte, comme le moteur la lit (docs/04-frontend.md §5).

    .DESCRIPTION
        -Depth 10 : sans lui, Windows PowerShell 5.1 tronque les objets imbriqués (planification,
        situations, programmes) à deux niveaux. L'échappement \uXXXX de <, >, & et ' que fait 5.1 est du
        JSON valide, relu correctement par le moteur. Les null, booléens et entiers gardent leur type.

    .PARAMETER Objet
        Objet issu de ConvertFrom-Json ou construit par Merge-CopieRegle.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] $Objet)
    $copie = $Objet.PSObject.Copy()
    if ($null -ne $copie.PSObject.Properties['Ligne']) { $copie.PSObject.Properties.Remove('Ligne') }   # numéro de ligne : propre à l'affichage
    $copie | ConvertTo-Json -Compress -Depth 10
}

function Copy-CopieObjet {
    <#
    .SYNOPSIS
        Copie profonde d'un objet JSON (aller-retour par JSON).
    .PARAMETER Objet
        Objet à copier.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Objet)
    $Objet | ConvertTo-Json -Compress -Depth 10 | ConvertFrom-Json
}

function Get-CopieModeleRegle {
    <#
    .SYNOPSIS
        Valeurs de secours et listes de valeurs permises, demandées au moteur (--modele-regle).

    .DESCRIPTION
        Le moteur est la seule source de vérité : l'interface ne recopie ni les valeurs de secours ni les
        listes (docs/07). La réponse est gardée pour la session ; -Actualiser la redemande.

    .PARAMETER Config
        Configuration (Get-CopieConfig).

    .PARAMETER Actualiser
        Ignore la réponse gardée.

    .OUTPUTS
        L'objet JSON du moteur : regle, listes, situations, version_format.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [pscustomobject] $Config,
        [switch] $Actualiser
    )
    if ($Actualiser -or $null -eq $Script:ModeleRegle) {
        $reponse = Invoke-CopieMoteur -Config $Config -Argument @('--modele-regle')
        if (-not $reponse.Reussi) { throw ('Le moteur n''a pas fourni le modèle de règle : ' + $reponse.Erreur) }
        $Script:ModeleRegle = $reponse.Json
    }
    $Script:ModeleRegle
}

function Merge-CopieRegle {
    <#
    .SYNOPSIS
        Règle complète = modèle du moteur (valeurs de secours) + valeurs d'une règle existante.

    .DESCRIPTION
        Le front-end écrit toujours le réglage complet de chaque règle (docs/01 §1). Les champs absents du
        fichier prennent la valeur de secours du moteur ; les champs inconnus du modèle sont conservés
        en fin de règle (le moteur les refusera en E06 : l'interface ne les supprime pas en silence).
        L'ordre des champs est celui du modèle.

    .PARAMETER Modele
        Règle par défaut (Get-CopieModeleRegle).regle.

    .PARAMETER Existante
        Règle lue dans le fichier, ou $null pour une nouvelle règle.

    .OUTPUTS
        [pscustomobject] la règle complète (copie : les arguments ne sont pas modifiés).
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)] $Modele,
        [AllowNull()] $Existante
    )
    $fusion = {
        param($modele, $existant)
        $sortie = [ordered]@{}
        foreach ($p in $modele.PSObject.Properties) {
            # Affectation directe, jamais $(if ...) : le pipeline aplatit les tableaux d'un ou zéro élément.
            if ($null -ne $existant -and $null -ne $existant.PSObject.Properties[$p.Name]) { $sortie[$p.Name] = $existant.PSObject.Properties[$p.Name].Value }
            else { $sortie[$p.Name] = $p.Value }
        }
        if ($null -ne $existant) {
            foreach ($p in $existant.PSObject.Properties) {
                if ($p.Name -eq 'Ligne') { continue }
                if (-not $sortie.Contains($p.Name)) { $sortie[$p.Name] = $p.Value }
            }
        }
        [pscustomobject]$sortie
    }
    $regle = Copy-CopieObjet -Objet $Modele
    $fichierRegle = $null
    if ($null -ne $Existante) {
        $fichierRegle = Copy-CopieObjet -Objet $Existante
        if ($null -ne $fichierRegle.PSObject.Properties['Ligne']) { $fichierRegle.PSObject.Properties.Remove('Ligne') }
    }
    $resultat = & $fusion $regle $fichierRegle

    $resultat.selection = & $fusion $regle.selection (Get-CopieValeur $fichierRegle 'selection')
    $situationsExistantes = Get-CopieValeur $fichierRegle 'situations'
    $situations = [ordered]@{}
    foreach ($p in $regle.situations.PSObject.Properties) {
        $situations[$p.Name] = & $fusion $p.Value (Get-CopieValeur $situationsExistantes $p.Name)
    }
    $resultat.situations = [pscustomobject]$situations
    $programmesExistants = Get-CopieValeur $fichierRegle 'programmes'
    $programmes = [ordered]@{}
    foreach ($p in $regle.programmes.PSObject.Properties) {
        $programmes[$p.Name] = Get-CopieValeur $programmesExistants $p.Name $null
    }
    $resultat.programmes = [pscustomobject]$programmes
    $resultat
}

function Get-CopieRegleOrdonnee {
    <#
    .SYNOPSIS
        Range les règles : une règle dépendante est toujours placée après celles dont elle dépend.

    .DESCRIPTION
        Tri stable : hors dépendances, l'ordre d'origine est conservé. Une dépendance inconnue ou une
        boucle ne bloque pas le tri (le moteur les refuse : D01, D02).

    .PARAMETER Regle
        Liste de règles.
    #>
    [CmdletBinding()]
    param([AllowEmptyCollection()] [object[]] $Regle)
    $parId = @{}
    foreach ($r in $Regle) { $id = "$(Get-CopieValeur $r 'id' '')".ToLowerInvariant(); if ($id -and -not $parId.ContainsKey($id)) { $parId[$id] = $r } }
    $place = New-Object System.Collections.Generic.HashSet[object]
    $sortie = New-Object System.Collections.Generic.List[object]
    $visite = {
        param($r, $chemin)
        if ($place.Contains($r) -or $chemin.Contains($r)) { return }
        $null = $chemin.Add($r)
        foreach ($ref in @(Get-CopieValeur $r 'apres' @())) {
            $dep = $parId["$ref".ToLowerInvariant()]
            if ($null -ne $dep) { & $visite $dep $chemin }
        }
        $null = $chemin.Remove($r)
        if ($place.Add($r)) { $sortie.Add($r) }
    }
    foreach ($r in $Regle) { & $visite $r (New-Object System.Collections.Generic.HashSet[object]) }
    $sortie.ToArray()
}

function Get-CopieNomVersion {
    <#
    .SYNOPSIS
        Nom du fichier de version : <environnement>_<AAAAMMJJ_hhmmss>_<compte>.jsonl (docs/04 §5).
    .PARAMETER Environnement
        Nom de l'environnement.
    .PARAMETER Compte
        Compte qui enregistre (DOMAINE\nom) ; les caractères interdits dans un nom de fichier deviennent « _ ».
    .PARAMETER Date
        Instant de l'enregistrement.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [string] $Environnement,
        [Parameter(Mandatory)] [string] $Compte,
        [datetime] $Date = (Get-Date)
    )
    $interdits = [regex]::Escape((-join [System.IO.Path]::GetInvalidFileNameChars()))
    $propre = [regex]::Replace($Compte, '[' + $interdits + ']', '_')
    '{0}_{1}_{2}.jsonl' -f $Environnement, $Date.ToString('yyyyMMdd_HHmmss'), $propre
}

function Save-CopieParametrage {
    <#
    .SYNOPSIS
        Enregistre un fichier de paramétrage de façon sûre (docs/04-frontend.md §5).

    .DESCRIPTION
        1. Contrôle d'édition simultanée : le fichier doit être celui qui a été chargé (empreinte).
        2. Construit le fichier complet : en-tête + une ligne par règle, triées (dépendances d'abord).
        3. L'écrit dans un dossier de brouillons du même dossier (même volume : renommage atomique),
           sous le nom de l'environnement (le moteur exige que le nom du fichier soit celui de
           l'environnement : E03).
        4. Appelle le moteur : --verifier --syntaxe-seule --precedent <fichier actuel>. Un refus annule ;
           les avertissements sont soumis à confirmation (Confirmer).
        5. Recontrôle l'empreinte, copie la version précédente dans le dossier des versions (nom avec
           compte et date, fiche .meta.json avec le commentaire), puis remplace le fichier par
           File.Replace (atomique). Le fichier n'est donc jamais écrit à moitié.
        UTF-8 sans BOM (Set-Content -Encoding UTF8 ajoute un BOM, Out-File écrit en UTF-16).

    .PARAMETER Config
        Configuration (Get-CopieConfig).

    .PARAMETER Fichier
        Fichier de paramétrage à remplacer.

    .PARAMETER EmpreinteAttendue
        Empreinte du fichier au chargement (Read-CopieFichierParametrage).

    .PARAMETER Entete
        Objet d'en-tête.

    .PARAMETER Regle
        Règles complètes (Merge-CopieRegle).

    .PARAMETER Compte
        Compte tracé (DOMAINE\nom).

    .PARAMETER Commentaire
        Commentaire tracé avec la version.

    .PARAMETER Confirmer
        Scriptblock appelé avec la liste des avertissements ; renvoie $true pour enregistrer quand même.
        Absent : un avertissement empêche l'enregistrement.

    .OUTPUTS
        [pscustomobject] Copie.Enregistrement : Enregistre, Etape (conflit, moteur, refus, avertissements,
        ecriture, ok), Message, Refus, Avertissements, Version, Empreinte.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)] [pscustomobject] $Config,
        [Parameter(Mandatory)] [string] $Fichier,
        [Parameter(Mandatory)] [string] $EmpreinteAttendue,
        [Parameter(Mandatory)] $Entete,
        [AllowEmptyCollection()] [object[]] $Regle = @(),
        [Parameter(Mandatory)] [string] $Compte,
        [Parameter(Mandatory)] [string] $Commentaire,
        [scriptblock] $Confirmer
    )

    $resultat = {
        param($ok, $etape, $message, $refus, $avertissements, $version, $empreinte)
        [pscustomobject]@{ PSTypeName = 'Copie.Enregistrement'; Enregistre = $ok; Etape = $etape; Message = $message
            Refus = @($refus); Avertissements = @($avertissements); Version = $version; Empreinte = $empreinte }
    }
    $empreinteFichier = {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try { ([BitConverter]::ToString($sha.ComputeHash([System.IO.File]::ReadAllBytes($Fichier)))).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose() }
    }
    $verifierInchange = {
        try { (& $empreinteFichier) -eq $EmpreinteAttendue } catch { $false }
    }

    if (-not (& $verifierInchange)) {
        return (& $resultat $false 'conflit' 'Le fichier a été modifié par quelqu''un d''autre depuis son chargement : rien n''a été enregistré. Rechargez-le.' @() @() $null $null)
    }

    $nom = [System.IO.Path]::GetFileNameWithoutExtension($Fichier)
    $dossier = Split-Path -Parent $Fichier
    $brouillons = Join-Path $dossier ($Config.Parametrage.DossierBrouillons + '\' + [guid]::NewGuid().ToString('N'))
    $temporaire = Join-Path $brouillons ($nom + '.jsonl')
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    try {
        $lignes = @((ConvertTo-CopieLigneJson -Objet $Entete)) + @(@(Get-CopieRegleOrdonnee -Regle $Regle) | ForEach-Object { ConvertTo-CopieLigneJson -Objet $_ })
        $null = New-Item -ItemType Directory -Path $brouillons -Force
        [System.IO.File]::WriteAllText($temporaire, (($lignes -join "`n") + "`n"), $utf8)

        $reponse = Invoke-CopieMoteur -Config $Config -Fichier $temporaire -Argument @(
            '--verifier', '--syntaxe-seule', '--precedent', $Fichier, '--dossier-parametrage', $dossier,
            '--periode-declencheur-sec', "$($Config.Parametrage.PeriodeDeclencheurSec)")
        if ($null -eq $reponse.Json) {
            return (& $resultat $false 'moteur' ('Vérification impossible : ' + $reponse.Erreur) @() @() $null $null)
        }
        $refus = @(Get-CopieValeur $reponse.Json 'refus' @())
        $avertissements = @(Get-CopieValeur $reponse.Json 'avertissements' @())
        if ($refus.Count -gt 0 -or $reponse.Code -eq 2) {
            return (& $resultat $false 'refus' ('Le moteur refuse ce paramétrage ({0} refus) : rien n''a été enregistré.' -f $refus.Count) $refus $avertissements $null $null)
        }
        if ($avertissements.Count -gt 0) {
            $accord = $false
            if ($null -ne $Confirmer) { $accord = [bool](& $Confirmer $avertissements) }
            if (-not $accord) {
                return (& $resultat $false 'avertissements' 'Enregistrement annulé : les avertissements n''ont pas été acceptés.' @() $avertissements $null $null)
            }
        }

        if (-not (& $verifierInchange)) {
            return (& $resultat $false 'conflit' 'Le fichier a été modifié par quelqu''un d''autre pendant la vérification : rien n''a été enregistré. Rechargez-le.' @() @() $null $null)
        }
        $dossierVersions = Join-Path $dossier $Config.Parametrage.DossierVersions
        if (-not (Test-Path -LiteralPath $dossierVersions)) { $null = New-Item -ItemType Directory -Path $dossierVersions }
        $maintenant = Get-Date
        $version = Join-Path $dossierVersions (Get-CopieNomVersion -Environnement $nom -Compte $Compte -Date $maintenant)
        Copy-Item -LiteralPath $Fichier -Destination $version -ErrorAction Stop
        $nouvelleEmpreinte = $null
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try { $nouvelleEmpreinte = ([BitConverter]::ToString($sha.ComputeHash([System.IO.File]::ReadAllBytes($temporaire)))).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose() }
        $fiche = [ordered]@{
            environnement = $nom; compte = $Compte; date = $maintenant.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
            commentaire = $Commentaire; empreinte_version = $EmpreinteAttendue; empreinte_nouvelle = $nouvelleEmpreinte
            avertissements = @($avertissements | ForEach-Object { "$($_.code) $($_.message)" })
        }
        [System.IO.File]::WriteAllText(($version -replace '\.jsonl$', '.meta.json'), ($fiche | ConvertTo-Json -Depth 4), $utf8)

        [System.IO.File]::Replace($temporaire, $Fichier, [NullString]::Value)   # atomique, même volume ($null deviendrait "" en 5.1)
        return (& $resultat $true 'ok' 'Paramétrage enregistré.' @() $avertissements $version $nouvelleEmpreinte)
    }
    catch {
        return (& $resultat $false 'ecriture' ('Enregistrement impossible : ' + $_.Exception.Message) @() @() $null $null)
    }
    finally {
        if (Test-Path -LiteralPath $brouillons) { Remove-Item -LiteralPath $brouillons -Recurse -Force -ErrorAction SilentlyContinue }
    }
}
