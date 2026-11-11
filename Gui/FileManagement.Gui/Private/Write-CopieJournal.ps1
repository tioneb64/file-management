function Write-CopieJournal {
    <#
    .SYNOPSIS
        Écrit une ligne dans le journal de l'interface (panneau du bas) et, si configuré, dans un fichier JSON Lines.

    .DESCRIPTION
        Toute action est tracée (compte, heure, message) : docs/04-frontend.md §1. Le fichier est un
        fichier par jour (GestionCopie_AAAA-MM-JJ.jsonl) dans Journal.Dossier, lisible par Alloy, au format
        de la plateforme d'observabilité (timestamp, level, message, trace, service, context ; error pour les
        niveaux ERROR et CRITICAL). Le code d'environnement vient de Journal.Environnement (défaut : prod).
        Une panne d'écriture du fichier n'empêche jamais l'interface de fonctionner : elle est signalée une fois.

    .PARAMETER Contexte
        Contexte de la session : Config, Utilisateur, LogBox (RichTextBox ou $null).

    .PARAMETER Niveau
        INFO, WARNING ou ERREUR (écrit ERROR dans le fichier ; CRITICAL est aussi admis).

    .PARAMETER Evenement
        Nom court de l'événement (par exemple moteur_appel, verification).

    .PARAMETER Message
        Texte lisible.

    .PARAMETER Donnees
        Champs supplémentaires du fichier JSON (table de hachage).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [hashtable] $Contexte,
        [ValidateSet('INFO', 'WARNING', 'ERREUR', 'CRITICAL')] [string] $Niveau = 'INFO',
        [string] $Evenement = 'message',
        [Parameter(Mandatory)] [string] $Message,
        [hashtable] $Donnees = @{}
    )

    $maintenant = Get-Date
    $boite = $Contexte.LogBox
    if ($null -ne $boite) {
        $couleur = switch ($Niveau) { 'ERREUR' { '#FF8A80' } 'WARNING' { '#FFD180' } default { '#DDE3EA' } }
        $paragraphe = New-Object System.Windows.Documents.Paragraph
        $paragraphe.Margin = New-Object System.Windows.Thickness(0)
        $run = New-Object System.Windows.Documents.Run(('{0}  {1,-7} {2}' -f $maintenant.ToString('HH:mm:ss'), $Niveau, $Message))
        $run.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString($couleur)
        $paragraphe.Inlines.Add($run)
        $boite.Document.Blocks.Add($paragraphe)
        $boite.ScrollToEnd()
    }

    $dossier = $Contexte.Config.Journal.Dossier
    if (-not $dossier) { return }
    try {
        if (-not (Test-Path -LiteralPath $dossier)) { $null = New-Item -ItemType Directory -Path $dossier -Force }
        if (-not $Contexte.TraceId) {                      # une session de l'interface = une trace
            $Contexte.TraceId = -join (1..32 | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })
            $Contexte.SpanId = -join (1..16 | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })
        }
        $codeEnvironnement = "$($Contexte.Config.Journal.Environnement)".Trim()
        if ((Get-CopieCodesPlateforme) -cnotcontains $codeEnvironnement) { $codeEnvironnement = 'prod' }
        $niveauFichier = $(if ($Niveau -eq 'ERREUR') { 'ERROR' } else { $Niveau })
        $contexteLigne = [ordered]@{ object = 'interface'; object_id = "$($Contexte.Utilisateur)"; event = $Evenement; utilisateur = $Contexte.Utilisateur }
        foreach ($cle in $Donnees.Keys) {
            $nomChamp = $(if (@('object', 'object_id', 'event') -contains $cle) { 'x_' + $cle } else { $cle })
            $contexteLigne[$nomChamp] = $Donnees[$cle]
        }
        $ligne = [ordered]@{
            timestamp = $maintenant.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
            level     = $niveauFichier
            message   = $Message
            trace     = [ordered]@{ trace_id = $Contexte.TraceId; span_id = $Contexte.SpanId; correlation_id = $Contexte.TraceId }
            service   = [ordered]@{ name = 'file_management.interface'; version = '2.0.0'; environment = $codeEnvironnement; instance = $env:COMPUTERNAME.ToLowerInvariant() }
            context   = $contexteLigne
        }
        if ($niveauFichier -in 'ERROR', 'CRITICAL') { $ligne['error'] = [ordered]@{ type = 'UNKNOWN_ERROR'; message = $Message } }
        $texte = ($ligne | ConvertTo-Json -Compress -Depth 6) + "`n"
        $fichier = Join-Path $dossier ('GestionCopie_{0}.jsonl' -f $maintenant.ToString('yyyy-MM-dd'))
        [System.IO.File]::AppendAllText($fichier, $texte, (New-Object System.Text.UTF8Encoding($false)))
    }
    catch {
        if (-not $Contexte.PanneJournal) {
            $Contexte.PanneJournal = $true
            if ($null -ne $boite) {
                $p = New-Object System.Windows.Documents.Paragraph(New-Object System.Windows.Documents.Run(('journal fichier indisponible : ' + $_.Exception.Message)))
                $boite.Document.Blocks.Add($p)
            }
        }
    }
}
