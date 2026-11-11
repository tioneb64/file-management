function Get-CopieDispositionGraphe {
    <#
    .SYNOPSIS
        Place les règles liées par des dépendances en colonnes : une règle est toujours à droite de celles dont elle dépend.

    .DESCRIPTION
        Niveau d'une règle = 0 sans dépendance connue, sinon 1 + le plus grand niveau de ses dépendances (une
        boucle ou une dépendance inconnue ne bloque pas : le moteur les refuse, D01 et D02). Seules les règles
        qui ont au moins un lien (elles dépendent d'une règle connue, ou une autre en dépend) sont placées ;
        les autres sont comptées dans SansLien. Dans une colonne, l'ordre suit le fichier, affiné une fois par
        la position moyenne des dépendances pour limiter les croisements.

    .PARAMETER Regle
        Règles du fichier.

    .PARAMETER LargeurNoeud
        Largeur d'un nœud (pixels).

    .PARAMETER HauteurNoeud
        Hauteur d'un nœud.

    .PARAMETER EspaceX
        Espace horizontal entre colonnes.

    .PARAMETER EspaceY
        Espace vertical entre nœuds.

    .OUTPUTS
        [pscustomobject] Noeuds (Id, Niveau, Rang, X, Y), Aretes (De = dépendance, Vers = dépendante),
        Manquantes (dépendances inconnues : Regle, Dependance), SansLien (nombre), Largeur, Hauteur.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [AllowEmptyCollection()] [object[]] $Regle = @(),
        [int] $LargeurNoeud = 190,
        [int] $HauteurNoeud = 46,
        [int] $EspaceX = 70,
        [int] $EspaceY = 18
    )
    $ids = New-Object System.Collections.Generic.List[string]
    $original = @{}
    $deps = @{}
    foreach ($r in $Regle) {
        $id = "$(Get-CopieValeur $r 'id' '')"
        if (-not $id -or $original.ContainsKey($id.ToLowerInvariant())) { continue }
        $original[$id.ToLowerInvariant()] = $id
        $ids.Add($id.ToLowerInvariant())
        $deps[$id.ToLowerInvariant()] = @(Get-CopieValeur $r 'apres' @() | ForEach-Object { "$_".ToLowerInvariant() })
    }
    $aretes = New-Object System.Collections.Generic.List[object]
    $manquantes = New-Object System.Collections.Generic.List[object]
    $lies = New-Object System.Collections.Generic.HashSet[string]
    foreach ($id in $ids) {
        foreach ($d in $deps[$id]) {
            if ($d -eq $id) { continue }
            if ($original.ContainsKey($d)) { $aretes.Add([pscustomobject]@{ De = $original[$d]; Vers = $original[$id] }); $null = $lies.Add($id); $null = $lies.Add($d) }
            else { $manquantes.Add([pscustomobject]@{ Regle = $original[$id]; Dependance = $d }) }
        }
    }
    $niveau = @{}
    $calculer = $null
    $calculer = {
        param($id, $pile)
        if ($niveau.ContainsKey($id)) { return $niveau[$id] }
        if ($pile.Contains($id)) { return 0 }
        $null = $pile.Add($id)
        $n = 0
        foreach ($d in $deps[$id]) { if ($d -ne $id -and $original.ContainsKey($d)) { $n = [Math]::Max($n, 1 + (& $calculer $d $pile)) } }
        $null = $pile.Remove($id)
        $niveau[$id] = $n
        $n
    }
    foreach ($id in $ids) { $null = & $calculer $id (New-Object System.Collections.Generic.HashSet[string]) }

    $colonnes = @{}
    foreach ($id in $ids) {
        if (-not $lies.Contains($id)) { continue }
        $n = $niveau[$id]
        if (-not $colonnes.ContainsKey($n)) { $colonnes[$n] = New-Object System.Collections.Generic.List[string] }
        $colonnes[$n].Add($id)
    }
    $rang = @{}
    foreach ($n in @($colonnes.Keys | Sort-Object)) {
        $liste = @($colonnes[$n])
        if ($n -gt 0) {
            $moyenne = @{}
            foreach ($id in $liste) {
                $positions = @($deps[$id] | Where-Object { $rang.ContainsKey($_) } | ForEach-Object { $rang[$_] })
                $moyenne[$id] = $(if ($positions.Count -gt 0) { ($positions | Measure-Object -Average).Average } else { 0 })
            }
            $i = 0
            $liste = @($liste | ForEach-Object { [pscustomobject]@{ Id = $_; M = $moyenne[$_]; I = $i++ } } | Sort-Object M, I | ForEach-Object Id)
        }
        for ($k = 0; $k -lt $liste.Count; $k++) { $rang[$liste[$k]] = $k }
    }
    $noeuds = foreach ($id in $ids) {
        if (-not $lies.Contains($id)) { continue }
        [pscustomobject]@{ Id = $original[$id]; Niveau = $niveau[$id]; Rang = $rang[$id]
            X = $niveau[$id] * ($LargeurNoeud + $EspaceX); Y = $rang[$id] * ($HauteurNoeud + $EspaceY) }
    }
    $noeuds = @($noeuds)
    $maxN = ($noeuds | ForEach-Object Niveau | Measure-Object -Maximum).Maximum
    $maxR = ($noeuds | ForEach-Object Rang | Measure-Object -Maximum).Maximum
    [pscustomobject]@{
        Noeuds = $noeuds; Aretes = $aretes.ToArray(); Manquantes = $manquantes.ToArray()
        SansLien = ($ids.Count - $lies.Count)
        Largeur = $(if ($noeuds.Count) { ($maxN + 1) * ($LargeurNoeud + $EspaceX) - $EspaceX } else { 0 })
        Hauteur = $(if ($noeuds.Count) { ($maxR + 1) * ($HauteurNoeud + $EspaceY) - $EspaceY } else { 0 })
    }
}
