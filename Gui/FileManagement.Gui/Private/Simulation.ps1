# Simulation d'une règle : ce que le moteur ferait maintenant, sans rien écrire (--lancer-regle ID --simulation).

function Format-CopieTaille {
    <#
    .SYNOPSIS
        Taille en octets -> texte lisible (o, Ko, Mo, Go).
    .PARAMETER Octets
        Nombre d'octets.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([double] $Octets = 0)
    if ($Octets -lt 1KB) { return ('{0:N0} o' -f $Octets) }
    if ($Octets -lt 1MB) { return ('{0:N1} Ko' -f ($Octets / 1KB)) }
    if ($Octets -lt 1GB) { return ('{0:N1} Mo' -f ($Octets / 1MB)) }
    '{0:N2} Go' -f ($Octets / 1GB)
}

function ConvertTo-CopieControleSimulation {
    <#
    .SYNOPSIS
        Contrôles de répertoires de la simulation (controles du moteur) -> lignes lisibles : existe, lecture, écriture, espace.

    .DESCRIPTION
        Verdict : OK, A_CREER (dossier absent que le moteur sait créer avec les droits du compte) ou PROBLEME. Un dossier
        absent n'a ni droit de lecture ni d'écriture à montrer : « Écriture » dit alors si le dossier pourrait y être créé.

    .PARAMETER Controle
        Liste controles de la réponse du moteur (role, chemin, existe, lecture, ecriture, a_creer, espace, detail).
    #>
    [CmdletBinding()]
    param([AllowEmptyCollection()] [object[]] $Controle = @())
    $libelles = @{ source = 'Répertoire d''origine'; cible = 'Répertoire cible'; temporaire = 'Dossier temporaire'; archive = 'Dossier d''archive' }
    $ouiNon = { param($v) if ($null -eq $v) { [string][char]0x2014 } elseif ($v) { 'Oui' } else { 'Non' } }
    foreach ($c in $Controle) {
        $role = "$(Get-CopieValeur $c 'role' '')"
        $existe = [bool](Get-CopieValeur $c 'existe' $false)
        $aCreer = [bool](Get-CopieValeur $c 'a_creer' $false)
        $lecture = Get-CopieValeur $c 'lecture'
        $ecriture = Get-CopieValeur $c 'ecriture'
        $espace = Get-CopieValeur $c 'espace'
        $espaceTexte = [string][char]0x2014
        $espaceOk = $true
        if ($null -ne $espace) {
            $espaceOk = [bool](Get-CopieValeur $espace 'suffisant' $true)
            $espaceTexte = '{0} libres, {1} nécessaires : {2}' -f (Format-CopieTaille -Octets ([double](Get-CopieValeur $espace 'libre_octets' 0))),
            (Format-CopieTaille -Octets ([double](Get-CopieValeur $espace 'necessaire_octets' 0))), $(if ($espaceOk) { 'OK' } else { 'INSUFFISANT' })
        }
        $ecritureTexte = & $ouiNon $ecriture
        if (-not $existe -and $aCreer) { $ecritureTexte = 'Oui (création possible)' }
        $verdict = 'OK'
        if (-not $existe) { $verdict = $(if ($aCreer -and $role -ne 'source') { 'A_CREER' } else { 'PROBLEME' }) }
        elseif ($lecture -eq $false -or $ecriture -eq $false) { $verdict = 'PROBLEME' }
        if (-not $espaceOk -or [bool](Get-CopieValeur $c 'volume_incorrect' $false)) { $verdict = 'PROBLEME' }
        [pscustomobject]@{
            Role = $(if ($libelles.ContainsKey($role)) { $libelles[$role] } else { $role }); RoleId = $role
            Chemin = "$(Get-CopieValeur $c 'chemin' '')"; Existe = $(if ($existe) { 'Oui' } else { 'Non' })
            Lecture = (& $ouiNon $lecture); Ecriture = $ecritureTexte; Espace = $espaceTexte; Verdict = $verdict
            Remarque = "$(Get-CopieValeur $c 'detail' '')"
        }
    }
}

function ConvertTo-CopieResumeSimulation {
    <#
    .SYNOPSIS
        Réponse de --lancer-regle --simulation -> phrase de synthèse, lignes de la grille et remarques.

    .DESCRIPTION
        La phrase dit ce que la règle ferait si elle partait maintenant : « Déplacera 3 fichier(s) (1,2 Mo) du
        répertoire R vers le répertoire D. ». Une simulation n'écrit rien : ni fichier, ni base, ni journal de
        livraison. Les fichiers détaillés sont plafonnés par le moteur (apercu_tronque).

    .PARAMETER Json
        Objet JSON de la réponse (source, cible, mode, apercu, compteurs, statut, motif...).

    .OUTPUTS
        [pscustomobject] Phrase, Lignes (Fichier, Cible, Taille, Archive), Remarques (string[]), Niveau (INFO, WARNING, ERREUR).
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param([Parameter(Mandatory)] $Json)
    $source = "$(Get-CopieValeur $Json 'source' '')"
    $cible = "$(Get-CopieValeur $Json 'cible' '')"
    $mode = "$(Get-CopieValeur $Json 'mode' '')"
    $compteurs = Get-CopieValeur $Json 'compteurs'
    $n = [int](Get-CopieValeur $compteurs 'livres' 0)
    $octets = [double](Get-CopieValeur $compteurs 'octets' 0)
    $apercu = @(Get-CopieValeur $Json 'apercu' @())
    $statut = "$(Get-CopieValeur $Json 'statut' '')"
    $motif = "$(Get-CopieValeur $Json 'motif' '')"
    $remarques = New-Object System.Collections.Generic.List[string]

    $verbe = switch ($mode) { 'deplacement' { 'Déplacera' } 'archivage' { 'Copiera' } default { 'Copiera' } }
    if ($mode -eq 'suppression') {
        if ($n -gt 0) { $phrase = 'Supprimera DÉFINITIVEMENT {0} fichier(s) ({1}) du répertoire {2}. Aucune copie n''est conservée.' -f $n, (Format-CopieTaille -Octets $octets), $source }
        else { $phrase = 'Aucun fichier à supprimer dans le répertoire {0} pour le moment.' -f $source }
    }
    elseif ($mode -in 'count', 'size') {
        $phrase = 'Mesure du répertoire {0} : {1}.' -f $source, $(if ($motif) { $motif } else { 'résultat indisponible' })
        if ($statut -eq 'ATTENTE') { $phrase += ' La règle sortirait en ATTENTE : les règles qui en dépendent patienteraient.' }
        else { $phrase += ' Les seuils sont respectés : la règle sortirait en succès. Aucun fichier n''est touché.' }
    }
    elseif ($n -gt 0) {
        $phrase = '{0} {1} fichier(s) ({2}) du répertoire {3} vers le répertoire {4}.' -f $verbe, $n, (Format-CopieTaille -Octets $octets), $source, $cible
        if ($mode -eq 'archivage') {
            $archive = @($apercu | Where-Object { Get-CopieValeur $_ 'archive' } | Select-Object -First 1)
            if ($archive.Count -gt 0) { $phrase += ' Les originaux seront ensuite archivés dans {0}.' -f (Split-Path -Parent "$($archive[0].archive)") }
            else { $phrase += ' Les originaux seront ensuite archivés.' }
        }
        elseif ($mode -eq 'copie') { $phrase += ' Les originaux restent en place.' }
    }
    else { $phrase = 'Aucun fichier à traiter dans le répertoire {0} pour le moment.' -f $source }

    $niveau = 'INFO'
    if ($statut -eq 'ATTENTE') { $niveau = 'WARNING' }
    if ($statut -eq 'ERREUR') {
        $niveau = 'ERREUR'
        $remarques.Add('La règle ne pourrait pas s''exécuter : ' + $(if ($motif) { $motif } else { 'voir le journal du moteur' }))
    }
    elseif ($statut -eq 'WARNING') {
        $niveau = 'WARNING'
        if ($motif) { $remarques.Add('Avertissement : ' + $motif) }
    }
    $ignores = [int](Get-CopieValeur $compteurs 'ignores' 0)
    if ($ignores -gt 0) { $remarques.Add(('{0} fichier(s) ignoré(s) (déjà livrés, doublons ou exclus).' -f $ignores)) }
    $enAttente = [int](Get-CopieValeur $compteurs 'en_attente' 0)
    if ($enAttente -gt 0) { $remarques.Add(('{0} action(s) en attente d''une exécution précédente.' -f $enAttente)) }
    if ([bool](Get-CopieValeur $Json 'apercu_tronque' $false)) {
        $remarques.Add(('Seuls les {0} premiers fichiers sont listés (sur {1}).' -f $apercu.Count, (Get-CopieValeur $Json 'apercu_total' $n)))
    }
    $controles = @(ConvertTo-CopieControleSimulation -Controle @(Get-CopieValeur $Json 'controles' @()))
    $problemes = @($controles | Where-Object { $_.Verdict -eq 'PROBLEME' })
    $manquants = @($controles | Where-Object { $_.Verdict -eq 'A_CREER' })
    if ($problemes.Count -gt 0) {
        $niveau = 'ERREUR'
        $remarques.Add(('{0} problème(s) sur les répertoires : la règle ne pourrait pas livrer correctement (détail dans le tableau des contrôles).' -f $problemes.Count))
    }
    if ($manquants.Count -gt 0) { $remarques.Add(('{0} dossier(s) absent(s) peuvent être créés : {1}.' -f $manquants.Count, (($manquants | ForEach-Object { $_.Role.ToLowerInvariant() }) -join ', '))) }
    $remarques.Add('Simulation : rien n''a été copié, déplacé ni enregistré (un petit fichier d''essai est créé puis supprimé aussitôt dans les dossiers testés). Les programmes avant/après ne sont pas appelés.')

    $lignes = foreach ($a in $apercu) {
        [pscustomobject]@{
            Fichier = "$(Get-CopieValeur $a 'fichier' '')"; Cible = "$(Get-CopieValeur $a 'cible' '')"
            Taille  = (Format-CopieTaille -Octets ([double](Get-CopieValeur $a 'taille' 0))); Archive = "$(Get-CopieValeur $a 'archive' '')"
        }
    }
    [pscustomobject]@{ PSTypeName = 'Copie.ResumeSimulation'; Phrase = $phrase; Lignes = @($lignes); Remarques = $remarques.ToArray(); Niveau = $niveau
        Controles = $controles; ACreer = $manquants }
}
