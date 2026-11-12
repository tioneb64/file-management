# Gestion des environnements (étape F) : créer, modifier (dont le nom), supprimer. Réservé aux administrateurs.
# Aucune fenêtre ici : ces fonctions sont testables seules. Toute écriture passe par un brouillon vérifié par le
# moteur (--verifier --syntaxe-seule) ; rien n'est jamais supprimé pour de bon (le fichier et ses versions sont
# rangés dans le dossier des environnements supprimés) et la base n'est jamais touchée par une suppression.

function Test-CopieNomEnvironnement {
    <#
    .SYNOPSIS
        Vrai si le nom est un nom d'environnement valide pour le moteur (E03) : minuscules, chiffres, _ et -, 32 maximum.
    .PARAMETER Nom
        Nom à tester.
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param([AllowEmptyString()] [string] $Nom = '')
    $Nom -cmatch '^[a-z0-9_-]{1,32}$'
}

function Get-CopieCodesPlateforme {
    <#
    .SYNOPSIS
        Codes d'environnement admis par la plateforme d'observabilité (champ service.environment du journal du moteur).
    #>
    [CmdletBinding()]
    [OutputType([string[]])]
    param()
    'dev', 'build', 'test', 'pprod', 'prod', 'run', 'int'
}

function Get-CopieCodeEnvironnement {
    <#
    .SYNOPSIS
        Code de la plateforme d'observabilité que le moteur déduit du nom d'un environnement (production -> prod), ou $null.
    .DESCRIPTION
        Même table que le moteur (parametrage.deduire_code_environnement) : le moteur reste seul juge (refus E08).
    .PARAMETER Nom
        Nom de l'environnement.
    #>
    [CmdletBinding()]
    param([AllowEmptyString()] [string] $Nom = '')
    $alias = @{ production = 'prod'; preprod = 'pprod'; preproduction = 'pprod'; 'pre-prod' = 'pprod'; recette = 'test'; developpement = 'dev'; integration = 'int' }
    $n = $Nom.Trim().ToLowerInvariant()
    if ((Get-CopieCodesPlateforme) -contains $n) { return $n }
    if ($alias.ContainsKey($n)) { return $alias[$n] }
    $null
}

function Test-CopieCheminAbsolu {
    <#
    .SYNOPSIS
        Vrai pour un chemin complet (lecteur ou partage réseau) ; un chemin relatif dépendrait du dossier de lancement.
    .PARAMETER Chemin
        Chemin à tester.
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param([AllowEmptyString()] [string] $Chemin = '')
    $Chemin -match '^([A-Za-z]:[\\/]|\\\\[^\\]|//[^/])'
}

function Test-CopieSaisieEnvironnement {
    <#
    .SYNOPSIS
        Contrôle la saisie d'un environnement avant de la proposer au moteur (le moteur reste seul juge).
    .DESCRIPTION
        Renvoie la liste des problèmes en français (vide si la saisie est acceptable). Ces contrôles ne servent qu'à
        guider l'utilisateur : tout ce qui est écrit est de nouveau vérifié par le moteur.
    .PARAMETER Saisie
        Table : Nom, CodeEnvironnement, Racine, RacineSource, RacineCible, Base, DossierLogs, DossierTravail, ParalleleMax, RetentionExecutions,
        RetentionJournaux, MargeEspaceMo, Suspendu (booléen : maintenance, aucune règle lancée), MotifSuspension. Base, journaux et travail peuvent être partiels : ils se placent sous Racine.
    .PARAMETER Existants
        Les environnements déjà présents (Get-CopieEnvironnement), pour refuser un doublon de nom ou de base.
    .PARAMETER Ignorer
        Nom de l'environnement en cours de modification (il ne compte pas comme doublon de lui-même).
    #>
    [CmdletBinding()]
    [OutputType([string[]])]
    param(
        [Parameter(Mandatory)] [hashtable] $Saisie,
        [AllowEmptyCollection()] [object[]] $Existants = @(),
        [string] $Ignorer = ''
    )
    $p = New-Object System.Collections.Generic.List[string]
    $nom = "$($Saisie.Nom)".Trim()
    if (-not (Test-CopieNomEnvironnement -Nom $nom)) {
        $p.Add('Le nom doit contenir 1 à 32 caractères parmi : minuscules, chiffres, _ et - (par exemple « production »).')
    }
    elseif (@($Existants | Where-Object { $_.Nom -eq $nom -and $_.Nom -ne $Ignorer }).Count -gt 0) {
        $p.Add(('Un environnement « {0} » existe déjà.' -f $nom))
    }
    $code = "$($Saisie.CodeEnvironnement)".Trim()
    if ($code) {
        if ((Get-CopieCodesPlateforme) -cnotcontains $code) {
            $p.Add(('Le code plateforme doit être l''une des valeurs : {0} (ou rester vide : il se déduit alors du nom).' -f ((Get-CopieCodesPlateforme) -join ', ')))
        }
    }
    elseif ((Test-CopieNomEnvironnement -Nom $nom) -and -not (Get-CopieCodeEnvironnement -Nom $nom)) {
        $p.Add(('Le code plateforme ne se déduit pas du nom « {0} » : choisissez-le parmi {1}.' -f $nom, ((Get-CopieCodesPlateforme) -join ', ')))
    }
    $racine = "$($Saisie.Racine)".Trim()
    if ($racine -and -not (Test-CopieCheminAbsolu -Chemin $racine)) {
        $p.Add('La racine de l''environnement doit être un chemin complet (par exemple D:\Transferts\preprod).')
        $racine = ''
    }
    foreach ($def in @(@('RacineSource', 'La racine des sources'), @('RacineCible', 'La racine des cibles'))) {
        $v = Resolve-CopieChemin -Chemin "$($Saisie[$def[0]])" -Racine $racine
        if ($v -and -not (Test-CopieCheminAbsolu -Chemin $v)) { $p.Add(('{0} doit être un chemin complet, ou la racine de l''environnement doit être renseignée pour la compléter (ou la laisser vide).' -f $def[1])) }
    }
    $base = Resolve-CopieChemin -Chemin "$($Saisie.Base)" -Racine $racine
    if (-not $base) { $p.Add('Le chemin de la base est obligatoire.') }
    elseif ($base -match '^(\\\\|//)') { $p.Add('La base ne peut pas être sur un partage réseau : elle doit être sur un disque local du serveur d''exécution.') }
    elseif (-not (Test-CopieCheminAbsolu -Chemin $base)) { $p.Add('Le chemin de la base doit être complet (par exemple D:\Copie\production.db), ou la racine de l''environnement doit être renseignée pour le compléter (par exemple BDD\production.db).') }
    else {
        $autres = @($Existants | Where-Object {
                $_.Nom -ne $Ignorer -and $null -ne $_.Parametrage.Entete -and
                (Get-CopieCheminsEnvironnement -Entete $_.Parametrage.Entete).Base.ToLowerInvariant().Replace('/', '\') -eq $base.ToLowerInvariant().Replace('/', '\')
            })
        if ($autres.Count -gt 0) { $p.Add(('Cette base est déjà celle de l''environnement « {0} » : une base ne sert qu''à un environnement.' -f $autres[0].Nom)) }
    }
    $travail = (Resolve-CopieChemin -Chemin "$($Saisie.DossierTravail)" -Racine $racine).ToLowerInvariant().Replace('/', '\')
    if ($travail) {
        $autre = @($Existants | Where-Object {
                $_.Nom -ne $Ignorer -and $null -ne $_.Parametrage.Entete -and
                "$(Get-CopieValeur $_.Parametrage.Entete 'dossier_travail' '')".Trim() -and
                (Get-CopieCheminsEnvironnement -Entete $_.Parametrage.Entete).DossierTravail.ToLowerInvariant().Replace('/', '\') -eq $travail
            })
        if ($autre.Count -gt 0) { $p.Add(('Ce dossier de travail est déjà celui de l''environnement « {0} » : chaque environnement a le sien.' -f $autre[0].Nom)) }
    }
    foreach ($def in @(@('DossierLogs', 'Le dossier des journaux'), @('DossierTravail', 'Le dossier de travail'))) {
        $v = Resolve-CopieChemin -Chemin "$($Saisie[$def[0]])" -Racine $racine
        if ($v -and -not (Test-CopieCheminAbsolu -Chemin $v)) { $p.Add(('{0} doit être un chemin complet, ou la racine de l''environnement doit être renseignée pour le compléter (ou rester vide).' -f $def[1])) }
    }
    foreach ($def in @(@('ParalleleMax', 1, 'Le nombre de règles en parallèle'), @('RetentionExecutions', 1, 'La conservation de l''historique (jours)'),
            @('RetentionJournaux', 1, 'La conservation des journaux (jours)'), @('MargeEspaceMo', 0, 'La marge d''espace disque (Mo)'))) {
        $v = "$($Saisie[$def[0]])".Trim()
        if (-not $v) { continue }
        $n = 0
        if (-not [int]::TryParse($v, [ref]$n) -or $n -lt $def[1]) { $p.Add(('{0} doit être un nombre entier supérieur ou égal à {1} (ou rester vide).' -f $def[2], $def[1])) }
    }
    $p.ToArray()
}

function ConvertTo-CopieEnteteEnvironnement {
    <#
    .SYNOPSIS
        Saisie -> objet d'en-tête du fichier de paramétrage (les champs laissés vides sont omis : valeur de secours du moteur).
    .PARAMETER Saisie
        Table de saisie (voir Test-CopieSaisieEnvironnement).
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param([Parameter(Mandatory)] [hashtable] $Saisie)
    $e = [ordered]@{ version = 1; environnement = "$($Saisie.Nom)".Trim() }
    if ("$($Saisie.CodeEnvironnement)".Trim()) { $e['code_environnement'] = "$($Saisie.CodeEnvironnement)".Trim() }
    foreach ($def in @(@('Racine', 'racine'), @('RacineSource', 'racine_source'), @('RacineCible', 'racine_cible'))) {
        $v = "$($Saisie[$def[0]])".Trim()
        if ($v) { $e[$def[1]] = $v }
    }
    $e['base'] = "$($Saisie.Base)".Trim()
    foreach ($def in @(@('DossierLogs', 'dossier_logs'), @('DossierTravail', 'dossier_travail'))) {
        $v = "$($Saisie[$def[0]])".Trim()
        if ($v) { $e[$def[1]] = $v }
    }
    foreach ($def in @(@('ParalleleMax', 'parallele_max'), @('RetentionExecutions', 'retention_executions_jours'),
            @('RetentionJournaux', 'retention_journaux_jours'), @('MargeEspaceMo', 'marge_espace_mo'))) {
        $v = "$($Saisie[$def[0]])".Trim()
        if ($v) { $e[$def[1]] = [int]$v }
    }
    if ($Saisie.Suspendu -eq $true) {
        $e['suspendu'] = $true
        if ("$($Saisie.MotifSuspension)".Trim()) { $e['motif_suspension'] = "$($Saisie.MotifSuspension)".Trim() }
    }
    [pscustomobject]$e
}

function ConvertFrom-CopieEnteteEnvironnement {
    <#
    .SYNOPSIS
        En-tête d'un fichier -> table de saisie du formulaire (champs absents : texte vide).
    .PARAMETER Entete
        Objet d'en-tête (Read-CopieFichierParametrage).Entete.
    #>
    [CmdletBinding()]
    [OutputType([hashtable])]
    param([Parameter(Mandatory)] $Entete)
    $texte = { param($objet, $nom) $v = Get-CopieValeur $objet $nom $null; if ($null -eq $v) { '' } else { "$v" } }
    @{
        Nom = (& $texte $Entete 'environnement'); CodeEnvironnement = (& $texte $Entete 'code_environnement'); Racine = (& $texte $Entete 'racine'); RacineSource = (& $texte $Entete 'racine_source')
        RacineCible = (& $texte $Entete 'racine_cible'); Base = (& $texte $Entete 'base'); DossierLogs = (& $texte $Entete 'dossier_logs')
        DossierTravail = (& $texte $Entete 'dossier_travail'); ParalleleMax = (& $texte $Entete 'parallele_max')
        RetentionExecutions = (& $texte $Entete 'retention_executions_jours'); RetentionJournaux = (& $texte $Entete 'retention_journaux_jours')
        MargeEspaceMo = (& $texte $Entete 'marge_espace_mo')
        Suspendu = [bool](Get-CopieValeur $Entete 'suspendu' $false); MotifSuspension = (& $texte $Entete 'motif_suspension')
    }
}

function New-CopieResultatEnvironnement {
    <#
    .SYNOPSIS
        Résultat d'une opération sur un environnement : Ok, Etape, Message, Refus, Avertissements, Fichier, Base, Dossier.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param([bool] $Ok, [string] $Etape, [string] $Message, [object[]] $Refus = @(), [object[]] $Avertissements = @(),
        [string] $Fichier = '', [string] $Base = '', [string] $Dossier = '')
    [pscustomobject]@{ PSTypeName = 'Copie.ResultatEnvironnement'; Ok = $Ok; Etape = $Etape; Message = $Message
        Refus = @($Refus); Avertissements = @($Avertissements); Fichier = $Fichier; Base = $Base; Dossier = $Dossier }
}

function Get-CopieEmpreinteFichier {
    <#
    .SYNOPSIS
        Empreinte SHA-256 d'un fichier (minuscules), ou $null s'il est illisible.
    .PARAMETER Chemin
        Fichier.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Chemin)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { ([BitConverter]::ToString($sha.ComputeHash([System.IO.File]::ReadAllBytes($Chemin)))).Replace('-', '').ToLowerInvariant() }
    catch { $null }
    finally { $sha.Dispose() }
}

function Confirm-CopieBrouillonEnvironnement {
    <#
    .SYNOPSIS
        Écrit l'en-tête (et les règles) dans un brouillon et le fait vérifier par le moteur.
    .DESCRIPTION
        Renvoie @{ Ok; Resultat (si refus) ; Brouillon ; Dossier ; Avertissements }. Le brouillon est dans le dossier des
        brouillons, sous le nom <environnement>.jsonl (le moteur exige que le nom du fichier soit celui de l'environnement).
        L'appelant supprime Dossier quand il a fini.
    .PARAMETER Config
        Configuration (Get-CopieConfig).
    .PARAMETER Dossier
        Dossier de paramétrage.
    .PARAMETER Entete
        En-tête à écrire.
    .PARAMETER Regle
        Règles reprises telles quelles (renommage) ; aucune pour une création.
    .PARAMETER Confirmer
        Bloc appelé avec les avertissements ; $true pour continuer. Absent : un avertissement arrête l'opération.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [pscustomobject] $Config,
        [Parameter(Mandatory)] [string] $Dossier,
        [Parameter(Mandatory)] $Entete,
        [AllowEmptyCollection()] [object[]] $Regle = @(),
        [scriptblock] $Confirmer
    )
    $brouillons = Join-Path $Dossier ($Config.Parametrage.DossierBrouillons + '\' + [guid]::NewGuid().ToString('N'))
    $brouillon = Join-Path $brouillons ("$($Entete.environnement)" + '.jsonl')
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $lignes = @((ConvertTo-CopieLigneJson -Objet $Entete)) + @(@($Regle) | Where-Object { $null -ne $_ } | ForEach-Object { ConvertTo-CopieLigneJson -Objet $_ })
    $null = New-Item -ItemType Directory -Path $brouillons -Force
    [System.IO.File]::WriteAllText($brouillon, (($lignes -join "`n") + "`n"), $utf8)
    $reponse = Invoke-CopieMoteur -Config $Config -Fichier $brouillon -Argument @(
        '--verifier', '--syntaxe-seule', '--periode-declencheur-sec', "$($Config.Parametrage.PeriodeDeclencheurSec)")
    $sortie = @{ Ok = $false; Resultat = $null; Brouillon = $brouillon; Dossier = $brouillons; Avertissements = @() }
    if ($null -eq $reponse.Json) {
        $sortie.Resultat = New-CopieResultatEnvironnement -Ok $false -Etape 'moteur' -Message ('Vérification impossible : ' + $reponse.Erreur)
        return $sortie
    }
    $refus = @(Get-CopieValeur $reponse.Json 'refus' @())
    $avertissements = @(Get-CopieValeur $reponse.Json 'avertissements' @())
    if ($refus.Count -gt 0 -or $reponse.Code -eq 2) {
        $sortie.Resultat = New-CopieResultatEnvironnement -Ok $false -Etape 'refus' -Refus $refus -Avertissements $avertissements `
            -Message ('Le moteur refuse ce paramétrage ({0} refus) : rien n''a été écrit.' -f $refus.Count)
        return $sortie
    }
    if ($avertissements.Count -gt 0) {
        $accord = $false
        if ($null -ne $Confirmer) { $accord = [bool](& $Confirmer $avertissements) }
        if (-not $accord) {
            $sortie.Resultat = New-CopieResultatEnvironnement -Ok $false -Etape 'avertissements' -Avertissements $avertissements `
                -Message 'Opération annulée : les avertissements n''ont pas été acceptés.'
            return $sortie
        }
    }
    $sortie.Ok = $true
    $sortie.Avertissements = $avertissements
    $sortie
}

function Get-CopieTexteReponse {
    <#
    .SYNOPSIS
        Message d'une réponse du moteur (le message JSON, sinon la sortie d'erreur).
    .PARAMETER Reponse
        Réponse du moteur (Copie.ReponseMoteur).
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [pscustomobject] $Reponse)
    $m = ''
    if ($null -ne $Reponse.Json) { $m = "$(Get-CopieValeur $Reponse.Json 'message' '')" }
    if (-not $m) { $m = "$($Reponse.Erreur)" }
    $m.Trim()
}

function Initialize-CopieBaseEnvironnement {
    <#
    .SYNOPSIS
        Crée la base d'un environnement (--initialiser-base) ; une base déjà présente n'est pas une erreur.
    .DESCRIPTION
        Le moteur crée le dossier de la base si les droits le permettent et refuse d'écraser une base existante.
    .PARAMETER Config
        Configuration (Get-CopieConfig).
    .PARAMETER Fichier
        Fichier de paramétrage de l'environnement.
    .PARAMETER Compte
        Compte tracé dans la base.
    .OUTPUTS
        [pscustomobject] Statut (creee, existante, echec) et Message.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param([Parameter(Mandatory)] [pscustomobject] $Config, [Parameter(Mandatory)] [string] $Fichier, [Parameter(Mandatory)] [string] $Compte)
    $r = Invoke-CopieMoteur -Config $Config -Fichier $Fichier -Argument @('--initialiser-base', '--utilisateur', $Compte)
    $texte = Get-CopieTexteReponse -Reponse $r
    if ($r.Reussi) { return [pscustomobject]@{ Statut = 'creee'; Message = $texte } }
    if ($texte -match 'existe d[eé]j[aà]') { return [pscustomobject]@{ Statut = 'existante'; Message = $texte } }
    [pscustomobject]@{ Statut = 'echec'; Message = $texte }
}

function Get-CopieEtatBaseEnvironnement {
    <#
    .SYNOPSIS
        Dit si la base d'un environnement existe et si une règle y est en cours d'exécution (lecture de l'état).
    .DESCRIPTION
        Statut : presente, absente (base pas encore créée), illisible (moteur injoignable, base incohérente...).
        EnCours : identifiants des règles en cours d'exécution.
    .PARAMETER Config
        Configuration (Get-CopieConfig).
    .PARAMETER Fichier
        Fichier de paramétrage de l'environnement.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param([Parameter(Mandatory)] [pscustomobject] $Config, [Parameter(Mandatory)] [string] $Fichier)
    $r = Invoke-CopieMoteur -Config $Config -Fichier $Fichier -Argument @('--etat')
    if ($r.Reussi) {
        $enCours = @(@(Get-CopieValeur $r.Json 'regles' @()) | Where-Object { Get-CopieValeur $_ 'en_cours' $false } | ForEach-Object { "$($_.id)" })
        return [pscustomobject]@{ Statut = 'presente'; EnCours = $enCours; Message = '' }
    }
    $texte = Get-CopieTexteReponse -Reponse $r
    $statut = $(if ($texte -match 'introuvable') { 'absente' } else { 'illisible' })
    [pscustomobject]@{ Statut = $statut; EnCours = @(); Message = $texte }
}

function New-CopieEnvironnement {
    <#
    .SYNOPSIS
        Crée un environnement : fichier de paramétrage (en-tête seul, sans règle) et, au choix, sa base.

    .DESCRIPTION
        Réservé aux administrateurs. Le nom ne doit être ni celui d'un fichier existant ni celui d'un environnement
        existant, la base ne doit pas être celle d'un autre. Le brouillon est vérifié par le moteur avant d'être
        placé ; la création de la base (--initialiser-base) suit. Si elle échoue, le fichier reste créé : le résultat
        le dit, et la base peut être créée ensuite.

    .PARAMETER Config
        Configuration (Get-CopieConfig).

    .PARAMETER Dossier
        Dossier de paramétrage.

    .PARAMETER Profil
        Profil de l'utilisateur (Get-CopieProfilAcces) : Admin exigé.

    .PARAMETER Saisie
        Table de saisie (voir Test-CopieSaisieEnvironnement).

    .PARAMETER Compte
        Compte tracé (DOMAINE\nom).

    .PARAMETER InitialiserBase
        Crée aussi la base.

    .PARAMETER Existants
        Environnements déjà présents (Get-CopieEnvironnement).

    .PARAMETER Regle
        Règles reprises dans le nouveau fichier (copie d'un environnement) ; aucune pour une création vierge.
        Elles sont écrites telles quelles : leurs chemins complets restent à modifier par l'utilisateur ; leurs chemins
        partiels (sous la racine des sources ou des cibles) suivent les racines du nouvel environnement.

    .PARAMETER DesactiverRegles
        Écrit les règles reprises avec actif = false (recommandé : deux environnements qui livreraient les mêmes
        fichiers au même endroit provoqueraient des doublons).

    .PARAMETER Confirmer
        Bloc appelé avec les avertissements du moteur.

    .PARAMETER PreparerDossiers
        Bloc appelé avec le chemin du fichier créé, avant la création de la base : il contrôle les dossiers de la base,
        des journaux et du travail, pose UNE question pour créer ceux qui manquent, et renvoie $true si tous sont prêts.
        Sans lui, rien n'est contrôlé (le moteur crée alors les dossiers au premier usage).

    .OUTPUTS
        [pscustomobject] Copie.ResultatEnvironnement.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)] [pscustomobject] $Config,
        [Parameter(Mandatory)] [string] $Dossier,
        [Parameter(Mandatory)] [string] $Profil,
        [Parameter(Mandatory)] [hashtable] $Saisie,
        [Parameter(Mandatory)] [string] $Compte,
        [bool] $InitialiserBase = $true,
        [AllowEmptyCollection()] [object[]] $Existants = @(),
        [AllowEmptyCollection()] [object[]] $Regle = @(),
        [bool] $DesactiverRegles = $false,
        [scriptblock] $Confirmer,
        [scriptblock] $PreparerDossiers
    )
    if ($Profil -ne 'Admin') { return (New-CopieResultatEnvironnement -Ok $false -Etape 'droits' -Message 'Créer un environnement est réservé aux administrateurs.') }
    $problemes = @(Test-CopieSaisieEnvironnement -Saisie $Saisie -Existants $Existants)
    if ($problemes.Count -gt 0) { return (New-CopieResultatEnvironnement -Ok $false -Etape 'saisie' -Message ($problemes -join "`n")) }
    if (-not (Test-Path -LiteralPath $Dossier -PathType Container)) {
        return (New-CopieResultatEnvironnement -Ok $false -Etape 'dossier' -Message ('Le dossier de paramétrage n''existe pas : ' + $Dossier))
    }
    $nom = "$($Saisie.Nom)".Trim()
    $fichier = Join-Path $Dossier ($nom + '.jsonl')
    if (Test-Path -LiteralPath $fichier) {
        return (New-CopieResultatEnvironnement -Ok $false -Etape 'existe' -Message ('Le fichier {0} existe déjà : rien n''a été écrit.' -f (Split-Path -Leaf $fichier)))
    }
    $brouillon = $null
    try {
        $entete = ConvertTo-CopieEnteteEnvironnement -Saisie $Saisie
        $regles = @(@($Regle) | Where-Object { $null -ne $_ } | ForEach-Object {
                $r = Copy-CopieObjet -Objet $_
                if ($null -ne $r.PSObject.Properties['Ligne']) { $r.PSObject.Properties.Remove('Ligne') }
                if ($DesactiverRegles) {
                    if ($null -ne $r.PSObject.Properties['actif']) { $r.actif = $false } else { Add-Member -InputObject $r -NotePropertyName 'actif' -NotePropertyValue $false }
                }
                $r
            })
        $brouillon = Confirm-CopieBrouillonEnvironnement -Config $Config -Dossier $Dossier -Entete $entete -Regle $regles -Confirmer $Confirmer
        if (-not $brouillon.Ok) { return $brouillon.Resultat }
        try { [System.IO.File]::Move($brouillon.Brouillon, $fichier) }
        catch { return (New-CopieResultatEnvironnement -Ok $false -Etape 'ecriture' -Message ('Création impossible : ' + $_.Exception.Message)) }
        $baseTexte = 'non créée (à créer avant le premier lancement)'
        $avert = @($brouillon.Avertissements)
        # Dossiers de la base, des journaux et du travail : une seule question (créer ou non) avant de créer la base.
        $dossiersOk = $true
        if ($null -ne $PreparerDossiers) { $dossiersOk = [bool](& $PreparerDossiers $fichier) }
        if ($InitialiserBase -and -not $dossiersOk) { $baseTexte = 'NON créée : les dossiers de la base, des journaux ou du travail ne sont pas prêts' }
        elseif ($InitialiserBase) {
            $b = Initialize-CopieBaseEnvironnement -Config $Config -Fichier $fichier -Compte $Compte
            $baseTexte = switch ($b.Statut) {
                'creee' { 'créée' }
                'existante' { 'déjà présente (reprise telle quelle)' }
                default { 'NON créée : ' + $b.Message }
            }
        }
        $ok = (-not $InitialiserBase) -or $baseTexte -notlike 'NON créée*'
        $message = ('Environnement « {0} » créé ({1}). Base : {2}.' -f $nom, (Split-Path -Leaf $fichier), $baseTexte)
        if ($regles.Count -gt 0) {
            $message += "`n{0} règle(s) copiée(s){1}. Les chemins partiels suivent les racines du nouvel environnement ; modifiez les chemins complets (source, cible, archive) avant de les utiliser." -f $regles.Count, $(if ($DesactiverRegles) { ', désactivées' } else { '' })
        }
        New-CopieResultatEnvironnement -Ok $true -Etape $(if ($ok) { 'ok' } else { 'base' }) -Message $message -Avertissements $avert -Fichier $fichier -Base $baseTexte
    }
    catch { New-CopieResultatEnvironnement -Ok $false -Etape 'ecriture' -Message ('Création impossible : ' + $_.Exception.Message) }
    finally { if ($null -ne $brouillon -and $brouillon.Dossier -and (Test-Path -LiteralPath $brouillon.Dossier)) { Remove-Item -LiteralPath $brouillon.Dossier -Recurse -Force -ErrorAction SilentlyContinue } }
}

function Get-CopieFichierVersionEnvironnement {
    <#
    .SYNOPSIS
        Fichiers de versions (.jsonl et .meta.json) qui appartiennent exactement à un environnement.
    .DESCRIPTION
        <nom>_<AAAAMMJJ>_<hhmmss>_<compte> : l'horodatage évite de confondre « prod » et « prod_b ».
    .PARAMETER Config
        Configuration (Parametrage.DossierVersions).
    .PARAMETER Dossier
        Dossier de paramétrage.
    .PARAMETER Nom
        Nom de l'environnement.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [pscustomobject] $Config, [Parameter(Mandatory)] [string] $Dossier, [Parameter(Mandatory)] [string] $Nom)
    $versions = Join-Path $Dossier $Config.Parametrage.DossierVersions
    if (-not (Test-Path -LiteralPath $versions -PathType Container)) { return @() }
    $modele = '^{0}_(\d{{8}}_\d{{6}}_.+)\.(jsonl|meta\.json)$' -f [regex]::Escape($Nom)
    @(Get-ChildItem -LiteralPath $versions -File | Where-Object { $_.Name -match $modele })
}

function Rename-CopieEnvironnement {
    <#
    .SYNOPSIS
        Renomme un environnement : fichier, en-tête, nom porté par la base, et historique des versions.

    .DESCRIPTION
        Réservé aux administrateurs. Le nouveau fichier est vérifié par le moteur, placé, puis le moteur renomme
        l'environnement dans la base (--renommer-environnement : sans cela, il refuserait la base de « l'autre »
        environnement). Si cette étape échoue, le nouveau fichier est retiré et rien n'a changé. Refusé tant
        qu'une règle est en cours d'exécution. Les jobs Jenkins qui citent l'ancien nom de fichier doivent
        ensuite être modifiés : l'outil ne les connaît pas.

    .PARAMETER Config
        Configuration (Get-CopieConfig).

    .PARAMETER Environnement
        Environnement à renommer (Get-CopieEnvironnement), modifiable et non modifié depuis son chargement.

    .PARAMETER NouveauNom
        Nouveau nom.

    .PARAMETER Profil
        Profil de l'utilisateur : Admin exigé.

    .PARAMETER Compte
        Compte tracé.

    .PARAMETER Commentaire
        Raison, conservée avec la version.

    .PARAMETER Existants
        Environnements déjà présents.

    .PARAMETER Confirmer
        Bloc appelé avec les avertissements du moteur.

    .OUTPUTS
        [pscustomobject] Copie.ResultatEnvironnement.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)] [pscustomobject] $Config,
        [Parameter(Mandatory)] [pscustomobject] $Environnement,
        [Parameter(Mandatory)] [string] $NouveauNom,
        [Parameter(Mandatory)] [string] $Profil,
        [Parameter(Mandatory)] [string] $Compte,
        [Parameter(Mandatory)] [string] $Commentaire,
        [AllowEmptyCollection()] [object[]] $Existants = @(),
        [scriptblock] $Confirmer
    )
    $refus = { param($etape, $message) New-CopieResultatEnvironnement -Ok $false -Etape $etape -Message $message }
    if ($Profil -ne 'Admin') { return (& $refus 'droits' 'Renommer un environnement est réservé aux administrateurs.') }
    if (-not $Environnement.Modifiable) { return (& $refus 'lecture' ('Cet environnement est en lecture seule : ' + $Environnement.Message)) }
    $ancien = $Environnement.Nom
    $NouveauNom = $NouveauNom.Trim()
    if ($NouveauNom -ceq $ancien) { return (& $refus 'saisie' 'Le nouveau nom est identique à l''ancien.') }
    if (-not (Test-CopieNomEnvironnement -Nom $NouveauNom)) { return (& $refus 'saisie' 'Le nom doit contenir 1 à 32 caractères parmi : minuscules, chiffres, _ et -.') }
    if (@($Existants | Where-Object { $_.Nom -eq $NouveauNom }).Count -gt 0) { return (& $refus 'saisie' ('Un environnement « {0} » existe déjà.' -f $NouveauNom)) }
    $dossier = Split-Path -Parent $Environnement.Fichier
    $nouveauFichier = Join-Path $dossier ($NouveauNom + '.jsonl')
    if (Test-Path -LiteralPath $nouveauFichier) { return (& $refus 'existe' ('Le fichier {0} existe déjà : rien n''a été changé.' -f (Split-Path -Leaf $nouveauFichier))) }
    if ((Get-CopieEmpreinteFichier -Chemin $Environnement.Fichier) -ne $Environnement.Parametrage.Empreinte) {
        return (& $refus 'conflit' 'Le fichier a été modifié par quelqu''un d''autre depuis son chargement : rien n''a été changé. Actualisez.')
    }
    $etatBase = Get-CopieEtatBaseEnvironnement -Config $Config -Fichier $Environnement.Fichier
    if ($etatBase.Statut -eq 'illisible') { return (& $refus 'etat' ('Impossible de vérifier l''état de la base, renommage refusé : ' + $etatBase.Message)) }
    if ($etatBase.EnCours.Count -gt 0) {
        return (& $refus 'en_cours' ('Une règle est en cours d''exécution ({0}) : attendez sa fin avant de renommer.' -f ($etatBase.EnCours -join ', ')))
    }

    $brouillon = $null
    try {
        $entete = Copy-CopieObjet -Objet $Environnement.Parametrage.Entete
        if ($null -ne $entete.PSObject.Properties['Ligne']) { $entete.PSObject.Properties.Remove('Ligne') }
        $entete.environnement = $NouveauNom
        # Le code de la plateforme suit le renommage quand le nouveau nom ne permet pas de le déduire.
        if (-not "$(Get-CopieValeur $entete 'code_environnement' '')".Trim() -and -not (Get-CopieCodeEnvironnement -Nom $NouveauNom)) {
            $codeAncien = Get-CopieCodeEnvironnement -Nom $ancien
            if ($codeAncien) { $entete | Add-Member -NotePropertyName 'code_environnement' -NotePropertyValue $codeAncien -Force }
        }
        $brouillon = Confirm-CopieBrouillonEnvironnement -Config $Config -Dossier $dossier -Entete $entete -Regle @($Environnement.Parametrage.Regles) -Confirmer $Confirmer
        if (-not $brouillon.Ok) { return $brouillon.Resultat }
        try { [System.IO.File]::Move($brouillon.Brouillon, $nouveauFichier) }
        catch { return (& $refus 'ecriture' ('Renommage impossible : ' + $_.Exception.Message)) }

        $baseTexte = 'pas encore créée'
        if ($etatBase.Statut -eq 'presente') {
            $r = Invoke-CopieMoteur -Config $Config -Fichier $nouveauFichier -Argument @('--renommer-environnement', $ancien, '--utilisateur', $Compte, '--commentaire', $Commentaire)
            if (-not $r.Reussi) {
                Remove-Item -LiteralPath $nouveauFichier -Force -ErrorAction SilentlyContinue      # l'ancien fichier est intact
                return (& $refus 'base' ('Le moteur n''a pas pu renommer la base, rien n''a été changé : ' + (Get-CopieTexteReponse -Reponse $r)))
            }
            $baseTexte = 'renommée'
        }

        # À partir d'ici la base porte le nouveau nom : on ne revient plus en arrière, on signale ce qui reste.
        $reste = New-Object System.Collections.Generic.List[string]
        $versions = Join-Path $dossier $Config.Parametrage.DossierVersions
        try {
            if (-not (Test-Path -LiteralPath $versions)) { $null = New-Item -ItemType Directory -Path $versions }
            $maintenant = Get-Date
            $copie = Join-Path $versions (Get-CopieNomVersion -Environnement $ancien -Compte $Compte -Date $maintenant)
            Copy-Item -LiteralPath $Environnement.Fichier -Destination $copie -ErrorAction Stop
            $utf8 = New-Object System.Text.UTF8Encoding($false)
            $fiche = [ordered]@{
                environnement = $ancien; compte = $Compte; date = $maintenant.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
                commentaire = ('Renommé en {0} : {1}' -f $NouveauNom, $Commentaire); empreinte_version = $Environnement.Parametrage.Empreinte
                empreinte_nouvelle = (Get-CopieEmpreinteFichier -Chemin $nouveauFichier); avertissements = @()
            }
            [System.IO.File]::WriteAllText(($copie -replace '\.jsonl$', '.meta.json'), ($fiche | ConvertTo-Json -Depth 4), $utf8)
            foreach ($f in @(Get-CopieFichierVersionEnvironnement -Config $Config -Dossier $dossier -Nom $ancien)) {
                Rename-Item -LiteralPath $f.FullName -NewName ($NouveauNom + '_' + $f.Name.Substring($ancien.Length + 1)) -ErrorAction Stop
            }
        }
        catch { $reste.Add('historique des versions non renommé (' + $_.Exception.Message + ')') }
        try { Remove-Item -LiteralPath $Environnement.Fichier -Force -ErrorAction Stop }
        catch { $reste.Add(('l''ancien fichier {0} n''a pas pu être supprimé : supprimez-le à la main (' -f (Split-Path -Leaf $Environnement.Fichier)) + $_.Exception.Message + ')') }

        $message = ('Environnement « {0} » renommé en « {1} » (base : {2}).' -f $ancien, $NouveauNom, $baseTexte)
        if ($reste.Count -gt 0) { $message += "`nÀ terminer : " + ($reste -join ' ; ') + '.' }
        New-CopieResultatEnvironnement -Ok $true -Etape $(if ($reste.Count -gt 0) { 'partiel' } else { 'ok' }) -Message $message `
            -Avertissements @($brouillon.Avertissements) -Fichier $nouveauFichier -Base $baseTexte
    }
    catch { New-CopieResultatEnvironnement -Ok $false -Etape 'ecriture' -Message ('Renommage impossible : ' + $_.Exception.Message) }
    finally { if ($null -ne $brouillon -and $brouillon.Dossier -and (Test-Path -LiteralPath $brouillon.Dossier)) { Remove-Item -LiteralPath $brouillon.Dossier -Recurse -Force -ErrorAction SilentlyContinue } }
}

function Remove-CopieEnvironnement {
    <#
    .SYNOPSIS
        « Supprime » un environnement : son fichier et ses versions sont rangés, la base n'est pas touchée.

    .DESCRIPTION
        Réservé aux administrateurs, refusé tant qu'une règle est en cours d'exécution. Le fichier, ses versions et
        une fiche (compte, date, commentaire, chemin de la base) vont dans <dossier des supprimés>\<nom>_<date> :
        la suppression se défait en remettant le fichier en place. La base, les journaux et les archives restent où
        ils sont (à supprimer à la main si on n'en veut plus). Le double contrôle (avertissement puis saisie du nom)
        est demandé par l'interface avant d'appeler cette fonction.

    .PARAMETER Config
        Configuration (Get-CopieConfig).

    .PARAMETER Environnement
        Environnement à supprimer (Get-CopieEnvironnement).

    .PARAMETER Profil
        Profil de l'utilisateur : Admin exigé.

    .PARAMETER Compte
        Compte tracé.

    .PARAMETER Commentaire
        Raison, conservée dans la fiche.

    .OUTPUTS
        [pscustomobject] Copie.ResultatEnvironnement (Dossier : où tout a été rangé ; Base : chemin de la base laissée en place).
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)] [pscustomobject] $Config,
        [Parameter(Mandatory)] [pscustomobject] $Environnement,
        [Parameter(Mandatory)] [string] $Profil,
        [Parameter(Mandatory)] [string] $Compte,
        [Parameter(Mandatory)] [string] $Commentaire
    )
    $refus = { param($etape, $message) New-CopieResultatEnvironnement -Ok $false -Etape $etape -Message $message }
    if ($Profil -ne 'Admin') { return (& $refus 'droits' 'Supprimer un environnement est réservé aux administrateurs.') }
    if (-not $Commentaire.Trim()) { return (& $refus 'saisie' 'Le commentaire est obligatoire.') }
    $nom = $Environnement.Nom
    $dossier = Split-Path -Parent $Environnement.Fichier
    if (-not (Test-Path -LiteralPath $Environnement.Fichier -PathType Leaf)) { return (& $refus 'absent' 'Le fichier n''existe plus : actualisez.') }
    if ($null -ne $Environnement.Parametrage.Empreinte -and (Get-CopieEmpreinteFichier -Chemin $Environnement.Fichier) -ne $Environnement.Parametrage.Empreinte) {
        return (& $refus 'conflit' 'Le fichier a été modifié par quelqu''un d''autre depuis son chargement : rien n''a été supprimé. Actualisez.')
    }
    $etatBase = Get-CopieEtatBaseEnvironnement -Config $Config -Fichier $Environnement.Fichier
    if ($etatBase.Statut -eq 'illisible') { return (& $refus 'etat' ('Impossible de vérifier qu''aucune règle n''est en cours, suppression refusée : ' + $etatBase.Message)) }
    if ($etatBase.EnCours.Count -gt 0) {
        return (& $refus 'en_cours' ('Une règle est en cours d''exécution ({0}) : attendez sa fin avant de supprimer.' -f ($etatBase.EnCours -join ', ')))
    }
    try {
        $maintenant = Get-Date
        $rangement = Join-Path (Join-Path $dossier $Config.Parametrage.DossierSupprimes) ('{0}_{1}' -f $nom, $maintenant.ToString('yyyyMMdd_HHmmss'))
        $null = New-Item -ItemType Directory -Path (Join-Path $rangement 'versions') -Force
        $baseChemin = (Get-CopieCheminsEnvironnement -Entete $Environnement.Parametrage.Entete).Base
        $fiche = [ordered]@{
            environnement = $nom; compte = $Compte; date = $maintenant.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'); commentaire = $Commentaire
            base = $baseChemin; regles = @($Environnement.Parametrage.Regles).Count; empreinte = $Environnement.Parametrage.Empreinte
            note = 'La base, les journaux et les archives n''ont pas été touchés. Pour annuler : remettre le fichier .jsonl dans le dossier de paramétrage.'
        }
        [System.IO.File]::WriteAllText((Join-Path $rangement 'suppression.json'), ($fiche | ConvertTo-Json -Depth 4), (New-Object System.Text.UTF8Encoding($false)))
        foreach ($f in @(Get-CopieFichierVersionEnvironnement -Config $Config -Dossier $dossier -Nom $nom)) {
            Move-Item -LiteralPath $f.FullName -Destination (Join-Path $rangement 'versions') -ErrorAction Stop
        }
        Move-Item -LiteralPath $Environnement.Fichier -Destination $rangement -ErrorAction Stop
        New-CopieResultatEnvironnement -Ok $true -Etape 'ok' -Dossier $rangement -Base $baseChemin `
            -Message ('Environnement « {0} » supprimé. Son fichier et ses versions sont rangés dans {1}. La base ({2}), les journaux et les archives n''ont pas été touchés.' -f $nom, $rangement, $baseChemin)
    }
    catch { New-CopieResultatEnvironnement -Ok $false -Etape 'ecriture' -Message ('Suppression impossible : ' + $_.Exception.Message) }
}
