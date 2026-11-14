# Journaux d'une règle (--journaux-regle) : le JSON du moteur est décomposé en lignes lisibles pour la fenêtre « Journaux ».
# Fonctions pures (aucune fenêtre) : testées sans interface.

$Script:LibellesChampsJournal = @{
    fichier = 'Fichier'; cible = 'Destination'; taille = 'Taille'; sha256 = 'Empreinte SHA-256'; chemin = 'Chemin'
    controle = 'Contrôle'; situation = 'Situation'; motif = 'Motif'; statut = 'Statut'; compteurs = 'Compteurs'
    declencheur = 'Déclenché par'; simulation = 'Simulation'; tentative = 'Tentative'; tentatives = 'Tentatives permises'
    candidats = 'Fichiers candidats'; vus = 'Fichiers vus'; hors_masque = 'Hors masque'; trop_recents = 'Trop récents'
    trop_anciens = 'Trop anciens'; trop_petits = 'Trop petits'; dates_futures = 'Dates dans le futur'
    deja_horodates = 'Déjà horodatés'; outil = 'Outil'; point_appel = 'Point d''appel'; archive = 'Archive'
    code_retour = 'Code de retour'; job = 'Job Jenkins'; build = 'Numéro de build'; build_url = 'Adresse du build'
    noeud = 'Nœud Jenkins'; decision = 'Décision'; type = 'Type'; role = 'Répertoire'; point = 'Point d''appel'
    duree_ms = 'Durée'; commande = 'Commande'; message = 'Message'; sortie = 'Sortie'; erreur = 'Erreur'
    cle = 'Clé'; lot = 'Lot'; fichiers = 'Fichiers'; octets = 'Volume'
}

$Script:LibellesCompteursJournal = @{
    selectionnes = 'Sélectionnés'; livres = 'Livrés'; ignores = 'Ignorés'; erreurs = 'En erreur'
    en_attente = 'En attente'; octets = 'Volume'
}

$Script:LibellesNiveauJournal = @{ DEBUG = 'Détail'; INFO = 'Information'; WARNING = 'Avertissement'; ERROR = 'Erreur'; CRITICAL = 'Critique' }

function Get-CopieLibelleChampJournal {
    <#
    .SYNOPSIS
        Libellé lisible d'un champ du journal (« hors_masque » -> « Hors masque ») ; un champ inconnu est mis en forme sans être perdu.
    .PARAMETER Cle
        Nom du champ dans le journal.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [string] $Cle)
    if ($Script:LibellesChampsJournal.ContainsKey($Cle)) { return $Script:LibellesChampsJournal[$Cle] }
    $texte = $Cle -replace '^x_', '' -replace '_', ' '
    if ($texte.Length -gt 0) { $texte = $texte.Substring(0, 1).ToUpperInvariant() + $texte.Substring(1) }
    $texte
}

function Format-CopieValeurJournal {
    <#
    .SYNOPSIS
        Valeur d'un champ du journal rendue lisible : Oui / Non, taille en Ko / Mo, durée en secondes, « — » si vide.
    .PARAMETER Cle
        Nom du champ (décide du format).
    .PARAMETER Valeur
        Valeur lue dans le journal.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [string] $Cle, [AllowNull()] $Valeur)
    if ($null -eq $Valeur -or "$Valeur" -eq '') { return [string][char]0x2014 }
    if ($Valeur -is [bool]) { return $(if ($Valeur) { 'Oui' } else { 'Non' }) }
    $numerique = ($Valeur -is [int] -or $Valeur -is [long] -or $Valeur -is [double] -or $Valeur -is [decimal])
    if ($numerique -and $Cle -in 'taille', 'octets', 'libre_octets', 'necessaire_octets') { return (Format-CopieTaille -Octets ([double]$Valeur)) }
    if ($numerique -and $Cle -like '*_ms') { return (Format-CopieDureeMs -Millisecondes ([double]$Valeur)) }
    "$Valeur"
}

function Format-CopieDureeMs {
    <#
    .SYNOPSIS
        Durée en millisecondes -> « 850 ms », « 14,0 s », « 2 min 05 s ».
    .PARAMETER Millisecondes
        Durée.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [double] $Millisecondes)
    if ($Millisecondes -lt 1000) { return ('{0:N0} ms' -f $Millisecondes) }
    if ($Millisecondes -lt 60000) { return ('{0:N1} s' -f ($Millisecondes / 1000)) }
    $s = [math]::Round($Millisecondes / 1000)
    if ($s -lt 3600) { return ('{0} min {1:00} s' -f [math]::Floor($s / 60), ($s % 60)) }
    '{0} h {1:00} min' -f [math]::Floor($s / 3600), [math]::Floor(($s % 3600) / 60)
}

function Get-CopieGraviteJournal {
    <#
    .SYNOPSIS
        Gravité d'affichage d'un niveau du journal : Erreur (ERROR, CRITICAL), Avertissement (WARNING), Normal.
    .PARAMETER Niveau
        Niveau du journal.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([AllowNull()] [string] $Niveau)
    switch ($Niveau) { 'ERROR' { 'Erreur' } 'CRITICAL' { 'Erreur' } 'WARNING' { 'Avertissement' } default { 'Normal' } }
}

function Format-CopieGroupeJournal {
    <#
    .SYNOPSIS
        Libellé d'une exécution dans le journal : « n° 37 » (exécution réelle), « Simulation 1 », ou « — » hors exécution.
    .PARAMETER Groupe
        Clé de groupe du moteur (« 37 », « s1 », ou vide).
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([AllowNull()] $Groupe)
    if ($null -eq $Groupe -or "$Groupe" -eq '') { return [string][char]0x2014 }
    if ("$Groupe" -match '^s(\d+)$') { return ('Simulation {0}' -f $Matches[1]) }
    'n° {0}' -f $Groupe
}

function ConvertTo-CopieLignesJournaux {
    <#
    .SYNOPSIS
        Réponse de --journaux-regle (liste des fichiers) -> lignes de la liste de gauche, du plus récent au plus ancien.
    .PARAMETER Json
        Réponse du moteur (journaux : nom, jour, statut, motif, avertissements, erreurs, ...).
    .OUTPUTS
        [pscustomobject[]] Nom, Jour, Statut, Anomalies, Executions, Resume, Gravite, Couleur.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Json)
    $fr = [System.Globalization.CultureInfo]::GetCultureInfo('fr-FR')
    foreach ($j in @(Get-CopieValeur $Json 'journaux' @())) {
        $avert = [int](Get-CopieValeur $j 'avertissements' 0)
        $erreurs = [int](Get-CopieValeur $j 'erreurs' 0)
        $statut = "$(Get-CopieValeur $j 'statut' '')"
        $date = [datetime]::MinValue
        $jour = "$(Get-CopieValeur $j 'jour' '')"
        $texteJour = $jour
        if ([datetime]::TryParseExact($jour, 'yyyy-MM-dd', [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::None, [ref]$date)) { $texteJour = $date.ToString('ddd dd/MM/yyyy', $fr) }
        $anomalies = @()
        if ($erreurs -gt 0) { $anomalies += ('{0} erreur(s)' -f $erreurs) }
        if ($avert -gt 0) { $anomalies += ('{0} avertissement(s)' -f $avert) }
        $gravite = 'Normal'
        if ($erreurs -gt 0 -or $statut -eq 'ERREUR') { $gravite = 'Erreur' }
        elseif ($avert -gt 0 -or $statut -eq 'WARNING') { $gravite = 'Avertissement' }
        [pscustomobject]@{
            PSTypeName = 'Copie.LigneJournal'
            Nom        = "$(Get-CopieValeur $j 'nom' '')"
            Jour       = $texteJour
            Statut     = $(if ($statut) { $statut } else { [string][char]0x2014 })
            Anomalies  = $(if ($anomalies.Count -gt 0) { $anomalies -join ', ' } else { 'aucune' })
            Executions = [int](Get-CopieValeur $j 'executions' 0)
            Resume     = "$(Get-CopieValeur $j 'motif' '')"
            Gravite    = $gravite
            Couleur    = $(if ($gravite -eq 'Erreur') { '#C0392B' } elseif ($gravite -eq 'Avertissement') { '#C77700' } else { '#1F2933' })
        }
    }
}

function ConvertTo-CopieChoixExecutions {
    <#
    .SYNOPSIS
        Exécutions d'un journal -> choix de la liste déroulante (« Toutes les exécutions » en premier), de la plus récente à la plus ancienne.
    .PARAMETER Json
        Réponse du moteur pour un fichier (executions).
    .OUTPUTS
        [pscustomobject[]] Cle ($null pour « toutes »), Libelle.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Json)
    $execs = @(Get-CopieValeur $Json 'executions' @())
    $choix = New-Object System.Collections.Generic.List[object]
    $choix.Add([pscustomobject]@{ Cle = $null; Libelle = ('Toutes les exécutions ({0})' -f $execs.Count) })
    for ($i = $execs.Count - 1; $i -ge 0; $i--) {
        $x = $execs[$i]
        $heure = "$(Get-CopieValeur $x 'heure' '')"
        if ($heure.Length -ge 19) { $heure = $heure.Substring(11, 8) }
        $parties = @((Format-CopieGroupeJournal -Groupe (Get-CopieValeur $x 'cle' $null)), $heure)
        $declencheur = "$(Get-CopieValeur $x 'declencheur' '')"
        if ($declencheur) { $parties += $declencheur }
        $statut = "$(Get-CopieValeur $x 'statut' '')"
        $parties += $(if ($statut) { $statut } else { 'sans fin enregistrée' })
        $texte = $parties -join ' · '
        $motif = "$(Get-CopieValeur $x 'motif' '')"
        if ($motif) { $texte += ' : ' + $motif }
        $choix.Add([pscustomobject]@{ Cle = "$(Get-CopieValeur $x 'cle' '')"; Libelle = $texte })
    }
    $choix.ToArray()
}

function Get-CopieDetailEvenement {
    <#
    .SYNOPSIS
        Un événement du journal -> lignes « rubrique : valeur » (tout le JSON décomposé, les compteurs développés).
    .PARAMETER Evenement
        Événement de la réponse du moteur (heure, niveau, evenement, message, groupe, duree_ms, erreur, champs).
    .OUTPUTS
        [pscustomobject[]] Rubrique, Valeur.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Evenement)
    $lignes = New-Object System.Collections.Generic.List[object]
    $ajouter = { param($r, $v) $lignes.Add([pscustomobject]@{ Rubrique = $r; Valeur = $v }) }
    $niveau = "$(Get-CopieValeur $Evenement 'niveau' 'INFO')"
    & $ajouter 'Date et heure' "$(Get-CopieValeur $Evenement 'heure' '')"
    & $ajouter 'Niveau' $(if ($Script:LibellesNiveauJournal.ContainsKey($niveau)) { $Script:LibellesNiveauJournal[$niveau] } else { $niveau })
    & $ajouter 'Message' "$(Get-CopieValeur $Evenement 'message' '')"
    & $ajouter 'Événement' "$(Get-CopieValeur $Evenement 'evenement' '')"
    & $ajouter 'Exécution' (Format-CopieGroupeJournal -Groupe (Get-CopieValeur $Evenement 'groupe' $null))
    $duree = Get-CopieValeur $Evenement 'duree_ms' $null
    if ($null -ne $duree) { & $ajouter 'Durée' (Format-CopieDureeMs -Millisecondes ([double]$duree)) }
    $erreur = Get-CopieValeur $Evenement 'erreur' $null
    if ($null -ne $erreur) {
        & $ajouter 'Type d''erreur' "$(Get-CopieValeur $erreur 'type' '')"
        $exception = "$(Get-CopieValeur $erreur 'exception' '')"
        if ($exception) { & $ajouter 'Exception' $exception }
        $pile = "$(Get-CopieValeur $erreur 'pile' '')"
        if ($pile) { & $ajouter 'Trace technique' $pile }
    }
    foreach ($c in @(Get-CopieValeur $Evenement 'champs' @())) {
        $cle = "$(Get-CopieValeur $c 'cle' '')"
        $valeur = Get-CopieValeur $c 'valeur' $null
        $libelle = Get-CopieLibelleChampJournal -Cle $cle
        $structure = $null
        if ($cle -eq 'compteurs' -and $valeur -is [string] -and $valeur.StartsWith('{')) { try { $structure = $valeur | ConvertFrom-Json } catch { $structure = $null } }
        elseif ($valeur -is [pscustomobject]) { $structure = $valeur }
        if ($null -ne $structure) {
            foreach ($p in $structure.PSObject.Properties) {
                $sous = $(if ($Script:LibellesCompteursJournal.ContainsKey($p.Name)) { $Script:LibellesCompteursJournal[$p.Name] } else { Get-CopieLibelleChampJournal -Cle $p.Name })
                & $ajouter ('{0} : {1}' -f $libelle, $sous) (Format-CopieValeurJournal -Cle $p.Name -Valeur $p.Value)
            }
            continue
        }
        & $ajouter $libelle (Format-CopieValeurJournal -Cle $cle -Valeur $valeur)
    }
    $lignes.ToArray()
}

function ConvertTo-CopieLignesEvenements {
    <#
    .SYNOPSIS
        Réponse de --journaux-regle --journal (un fichier) -> lignes du tableau des événements, dans l'ordre du fichier.
    .PARAMETER Json
        Réponse du moteur (evenements).
    .OUTPUTS
        [pscustomobject[]] Numero, Heure, Niveau, Gravite, Execution, Groupe, Message, Detail (résumé sur une ligne),
        Couleur, Brut (événement d'origine, pour le détail).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Json)
    foreach ($e in @(Get-CopieValeur $Json 'evenements' @())) {
        $niveau = "$(Get-CopieValeur $e 'niveau' 'INFO')"
        $gravite = Get-CopieGraviteJournal -Niveau $niveau
        $heure = "$(Get-CopieValeur $e 'heure' '')"
        if ($heure.Length -ge 19) { $heure = $heure.Substring(11, 8) }
        $resume = @()
        foreach ($c in @(Get-CopieValeur $e 'champs' @())) {
            $cle = "$(Get-CopieValeur $c 'cle' '')"
            if ($cle -in 'compteurs', 'simulation', 'job', 'build', 'build_url', 'noeud') { continue }
            $resume += ('{0} : {1}' -f (Get-CopieLibelleChampJournal -Cle $cle), (Format-CopieValeurJournal -Cle $cle -Valeur (Get-CopieValeur $c 'valeur' $null)))
            if ($resume.Count -ge 3) { break }
        }
        $groupe = Get-CopieValeur $e 'groupe' $null
        [pscustomobject]@{
            PSTypeName = 'Copie.LigneEvenement'
            Numero     = [int](Get-CopieValeur $e 'numero' 0)
            Heure      = $heure
            Niveau     = $(if ($Script:LibellesNiveauJournal.ContainsKey($niveau)) { $Script:LibellesNiveauJournal[$niveau] } else { $niveau })
            Gravite    = $gravite
            Execution  = (Format-CopieGroupeJournal -Groupe $groupe)
            Groupe     = $(if ($null -eq $groupe -or "$groupe" -eq '') { $null } else { "$groupe" })
            Message    = "$(Get-CopieValeur $e 'message' '')"
            Detail     = ($resume -join '  ·  ')
            Couleur    = $(if ($gravite -eq 'Erreur') { '#C0392B' } elseif ($gravite -eq 'Avertissement') { '#C77700' } else { '#1F2933' })
            Brut       = $e
        }
    }
}

function Select-CopieEvenementsJournal {
    <#
    .SYNOPSIS
        Filtre les lignes d'événements : une exécution précise et/ou seulement les avertissements et erreurs.
    .PARAMETER Ligne
        Lignes de ConvertTo-CopieLignesEvenements.
    .PARAMETER Groupe
        Clé de l'exécution voulue ($null ou vide : toutes).
    .PARAMETER AnomaliesSeulement
        Garde seulement les avertissements et les erreurs.
    #>
    [CmdletBinding()]
    param([AllowNull()] [object[]] $Ligne, [AllowNull()] [string] $Groupe, [switch] $AnomaliesSeulement)
    foreach ($l in @($Ligne)) {
        if ($null -eq $l) { continue }
        if ($Groupe -and $l.Groupe -ne $Groupe) { continue }
        if ($AnomaliesSeulement -and $l.Gravite -eq 'Normal') { continue }
        $l
    }
}

function Get-CopieResumeJournal {
    <#
    .SYNOPSIS
        Phrase de synthèse d'un fichier de journal (nombre d'événements, d'exécutions, d'anomalies, lignes ignorées, troncature).
    .PARAMETER Json
        Réponse du moteur pour un fichier.
    .PARAMETER Ligne
        Lignes d'événements (pour compter les anomalies de ce qui est affiché).
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] $Json, [AllowNull()] [object[]] $Ligne)
    $lignes = @($Ligne)
    $erreurs = @($lignes | Where-Object { $_.Gravite -eq 'Erreur' }).Count
    $avert = @($lignes | Where-Object { $_.Gravite -eq 'Avertissement' }).Count
    $total = [int](Get-CopieValeur $Json 'total' $lignes.Count)
    $phrase = '{0} événement(s), {1} exécution(s) ; {2} erreur(s), {3} avertissement(s).' -f $total, @(Get-CopieValeur $Json 'executions' @()).Count, $erreurs, $avert
    if ([bool](Get-CopieValeur $Json 'tronque' $false)) { $phrase += (' Les {0} derniers événements seulement sont affichés (le fichier est plus long).' -f $lignes.Count) }
    $illisibles = [int](Get-CopieValeur $Json 'illisibles' 0)
    if ($illisibles -gt 0) { $phrase += (' {0} ligne(s) illisible(s) ignorée(s).' -f $illisibles) }
    $phrase
}
