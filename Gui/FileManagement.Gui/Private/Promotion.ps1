function Get-CopieRegleAdaptee {
    <#
    .SYNOPSIS
        Adapte une règle à un autre environnement en remplaçant un texte dans ses chemins (promotion).

    .DESCRIPTION
        Le remplacement (sans tenir compte de la casse, le texte est littéral, pas une expression régulière)
        s'applique aux dossiers (source, cible, archive, dossier temporaire) et à chaque élément de la
        commande des programmes. La règle d'origine n'est pas modifiée. Renvoie aussi la liste de ce qui a
        changé, pour que l'utilisateur la vérifie avant d'aller plus loin.

    .PARAMETER Regle
        Règle d'origine (complète ou non).

    .PARAMETER Chercher
        Texte à remplacer (par exemple le début d'un chemin de production). Vide : rien n'est remplacé.

    .PARAMETER Remplacer
        Texte de remplacement.

    .OUTPUTS
        [pscustomobject] Regle (copie adaptée), Changements (Champ, Avant, Apres).
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param([Parameter(Mandatory)] $Regle, [string] $Chercher = '', [string] $Remplacer = '')

    $copie = Copy-CopieObjet -Objet $Regle
    if ($null -ne $copie.PSObject.Properties['Ligne']) { $copie.PSObject.Properties.Remove('Ligne') }
    $changements = New-Object System.Collections.Generic.List[object]
    if ($Chercher) {
        $motif = [regex]::new([regex]::Escape($Chercher), [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        $texteRemplacement = $Remplacer
        $adapter = {
            param($texte)
            $motif.Replace($texte, [System.Text.RegularExpressions.MatchEvaluator] { $texteRemplacement })
        }
        foreach ($champ in 'source', 'cible', 'archive', 'dossier_temporaire') {
            $p = $copie.PSObject.Properties[$champ]
            if ($null -eq $p -or $p.Value -isnot [string] -or -not $p.Value) { continue }
            $nouveau = & $adapter $p.Value
            if ($nouveau -cne $p.Value) { $changements.Add([pscustomobject]@{ Champ = $champ; Avant = $p.Value; Apres = $nouveau }); $p.Value = $nouveau }
        }
        $programmes = $copie.PSObject.Properties['programmes']
        if ($null -ne $programmes -and $programmes.Value -is [pscustomobject]) {
            foreach ($pp in $programmes.Value.PSObject.Properties) {
                if ($pp.Value -isnot [pscustomobject] -or $null -eq $pp.Value.PSObject.Properties['commande']) { continue }
                $elements = @($pp.Value.commande)
                $nouveaux = @($elements | ForEach-Object { & $adapter "$_" })
                for ($i = 0; $i -lt $elements.Count; $i++) {
                    if ($nouveaux[$i] -cne "$($elements[$i])") { $changements.Add([pscustomobject]@{ Champ = ('programmes.{0}.commande[{1}]' -f $pp.Name, $i); Avant = "$($elements[$i])"; Apres = $nouveaux[$i] }) }
                }
                $pp.Value.commande = $nouveaux
            }
        }
    }
    [pscustomobject]@{ Regle = $copie; Changements = $changements.ToArray() }
}

function Get-CopieDependanceManquante {
    <#
    .SYNOPSIS
        Dépendances (apres) d'une règle qui n'existent pas dans les règles d'un environnement cible.
    .PARAMETER Regle
        Règle à promouvoir.
    .PARAMETER Existantes
        Règles de l'environnement cible.
    .OUTPUTS
        [string[]]
    #>
    [CmdletBinding()]
    [OutputType([string[]])]
    param([Parameter(Mandatory)] $Regle, [AllowEmptyCollection()] [object[]] $Existantes = @())
    $ids = @($Existantes | ForEach-Object { "$(Get-CopieValeur $_ 'id' '')".ToLowerInvariant() })
    $manquantes = @(Get-CopieValeur $Regle 'apres' @() | Where-Object { $ids -notcontains "$_".ToLowerInvariant() } | ForEach-Object { "$_" })
    $manquantes
}
