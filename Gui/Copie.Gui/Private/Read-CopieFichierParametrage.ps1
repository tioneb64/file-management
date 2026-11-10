function Read-CopieFichierParametrage {
    <#
    .SYNOPSIS
        Lit un fichier de paramétrage JSON Lines : en-tête et règles.

    .DESCRIPTION
        Ligne 1 = en-tête, lignes suivantes = une règle chacune, lignes vides ignorées (docs/01 §1).
        UTF-8 avec ou sans BOM. L'interface n'interprète pas les règles : elle les affiche. La validation
        est celle du moteur (--verifier). Cette lecture ne sert qu'à l'affichage ; une ligne illisible
        est signalée dans Erreurs avec son numéro, les autres lignes restent lues.

    .PARAMETER Chemin
        Fichier .jsonl.

    .OUTPUTS
        [pscustomobject] Copie.Parametrage : Fichier, Entete (ou $null), Regles (avec NoteProperty Ligne),
        Erreurs (liste de textes), Empreinte (SHA-256 du contenu), ModifieLe.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)]
        [string] $Chemin
    )

    $erreurs = New-Object System.Collections.Generic.List[string]
    $regles = New-Object System.Collections.Generic.List[object]
    $entete = $null
    $empreinte = $null
    $modifieLe = $null

    try {
        $octets = [System.IO.File]::ReadAllBytes($Chemin)
        $modifieLe = (Get-Item -LiteralPath $Chemin).LastWriteTimeUtc
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try { $empreinte = ([BitConverter]::ToString($sha.ComputeHash($octets))).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose() }
        $texte = (New-Object System.Text.UTF8Encoding($false)).GetString($octets)
        if ($texte.Length -gt 0 -and $texte[0] -eq [char]0xFEFF) { $texte = $texte.Substring(1) }
    }
    catch {
        $erreurs.Add(('fichier illisible : {0}' -f $_.Exception.Message))
        $texte = ''
    }

    $numero = 0
    foreach ($ligne in ($texte -split "`r?`n")) {
        $numero++
        if (-not $ligne.Trim()) { continue }
        try { $objet = $ligne | ConvertFrom-Json }
        catch {
            $erreurs.Add(('ligne {0} : JSON invalide ({1})' -f $numero, $_.Exception.Message))
            continue
        }
        if ($objet -isnot [pscustomobject]) {
            $erreurs.Add(('ligne {0} : un objet JSON est attendu' -f $numero))
            continue
        }
        Add-Member -InputObject $objet -NotePropertyName 'Ligne' -NotePropertyValue $numero -Force
        if ($null -eq $entete) { $entete = $objet } else { $regles.Add($objet) }
    }
    if ($null -eq $entete -and $erreurs.Count -eq 0) { $erreurs.Add('fichier vide : l''en-tête (ligne 1) est absent') }

    [pscustomobject]@{
        PSTypeName = 'Copie.Parametrage'
        Fichier    = $Chemin
        Entete     = $entete
        Regles     = $regles.ToArray()
        Erreurs    = $erreurs.ToArray()
        Empreinte  = $empreinte
        ModifieLe  = $modifieLe
    }
}
