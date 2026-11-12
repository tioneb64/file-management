# Gestion des environnements (étape F) : créer, modifier / renommer, créer la base, supprimer. Administrateurs seulement.
# La logique est dans Private\Environnements.ps1 ; ici, les fenêtres et les confirmations.

function Update-CopieApercuChemins {
    <#
    .SYNOPSIS
        Met à jour, dans la fenêtre d'un environnement, l'aperçu des chemins complets (racines et chemins partiels résolus).
    .PARAMETER Fenetre
        Fenêtre Dialog.Environnement (Tag : Noms).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [System.Windows.Window] $Fenetre)
    $t = $Fenetre.Tag
    if ($null -eq $t -or $null -eq $t.Noms) { return }
    $v = @{}
    foreach ($n in $t.Noms) { $v[$n] = $Fenetre.FindName($n).Text.Trim() }
    $entete = [pscustomobject]@{ racine = $v.Racine; racine_source = $v.RacineSource; racine_cible = $v.RacineCible
        base = $v.Base; dossier_logs = $v.DossierLogs; dossier_travail = $v.DossierTravail }
    $c = Get-CopieCheminsEnvironnement -Entete $entete
    $vide = '(à saisir)'
    $racineSource = $(if ($c.RacineSource) { $c.RacineSource } elseif ($c.Racine) { $c.Racine } else { '(chemins complets seulement)' })
    $racineCible = $(if ($c.RacineCible) { $c.RacineCible } elseif ($c.Racine) { $c.Racine } else { '(chemins complets seulement)' })
    $lignes = @(
        ('Base            : ' + $(if ($c.Base) { $c.Base } else { $vide }))
        ('Journaux        : ' + $(if ($c.DossierLogs) { $c.DossierLogs } else { $vide }))
        ('Travail         : ' + $(if ($c.DossierTravail) { $c.DossierTravail } else { $vide }))
        ('Sources (règles): ' + $racineSource)
        ('Cibles (règles) : ' + $racineCible))
    $Fenetre.FindName('Apercu').Text = ($lignes -join "`n")
}

function Read-CopieSaisieEnvironnement {
    <#
    .SYNOPSIS
        Fenêtre de saisie d'un environnement (création ou modification).
    .DESCRIPTION
        La saisie est contrôlée avant la fermeture (Test-CopieSaisieEnvironnement) ; le moteur revérifie ensuite.
        En modification, on ne change pas le nom ET d'autres réglages en même temps : le renommage touche à la base,
        il se fait seul.
    .PARAMETER Contexte
        Contexte de la session.
    .PARAMETER Mode
        creation ou modification.
    .PARAMETER Saisie
        Valeurs de départ (ConvertFrom-CopieEnteteEnvironnement) ; vide en création.
    .PARAMETER Existants
        Environnements déjà présents (contrôle des doublons).
    .OUTPUTS
        @{ Saisie = table ; CreerBase = bool }, ou $null si annulé.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [hashtable] $Contexte,
        [Parameter(Mandatory)] [ValidateSet('creation', 'modification', 'copie')] [string] $Mode,
        [hashtable] $Saisie = @{},
        [AllowEmptyCollection()] [object[]] $Existants = @()
    )
    $fenetre = Import-CopieXaml -Nom 'Dialog.Environnement'
    if ($null -ne $Contexte.Fenetre) { $fenetre.Owner = $Contexte.Fenetre }
    $noms = 'Nom', 'CodeEnvironnement', 'Racine', 'RacineSource', 'RacineCible', 'Base', 'DossierLogs', 'DossierTravail', 'ParalleleMax', 'RetentionExecutions', 'RetentionJournaux', 'MargeEspaceMo', 'MotifSuspension'
    foreach ($n in $noms) { $fenetre.FindName($n).Text = $(if ($Saisie.ContainsKey($n)) { "$($Saisie[$n])" } else { '' }) }
    $fenetre.FindName('Suspendu').IsChecked = [bool]($Saisie.ContainsKey('Suspendu') -and $Saisie['Suspendu'])
    $fenetre.Tag = @{ Mode = $Mode; Origine = $Saisie; Existants = $Existants; Noms = $noms; Resultat = $null }
    if ($Mode -eq 'copie') {
        $fenetre.Title = 'Copier vers un nouvel environnement'
        $fenetre.FindName('Intro').Text = 'Le nouvel environnement reçoit toutes les règles de l''original. Donnez-lui un nom et sa propre racine : les chemins partiels (base, journaux, travail, règles) la suivent, il n''y a rien d''autre à modifier.'
        $fenetre.FindName('Avis').Text = 'Les chemins complets de la base, des journaux et du travail ne sont pas repris : ils sont propres à chaque environnement. Les chemins partiels sont conservés et se placent sous la nouvelle racine.'
        $fenetre.FindName('DesactiverRegles').Visibility = 'Visible'
    }
    elseif ($Mode -eq 'creation') {
        $fenetre.Title = 'Nouvel environnement'
        $fenetre.FindName('Intro').Text = 'Un environnement est un fichier de paramétrage et sa propre base (par exemple production, recette). Les règles se créent ensuite dans son onglet.'
        $fenetre.FindName('Avis').Text = 'Le fichier est créé dans le dossier de paramétrage. Les jobs Jenkins s''y réfèrent par son nom.'
    }
    else {
        $fenetre.Title = 'Modifier l''environnement « {0} »' -f $Saisie.Nom
        $fenetre.FindName('Intro').Text = 'Changer le nom renomme le fichier, la base et l''historique des versions ; il se fait seul, sans autre changement, et pas pendant l''exécution d''une règle.'
        $fenetre.FindName('Avis').Text = 'Attention : les jobs Jenkins qui citent l''ancien nom de fichier doivent être modifiés. Changer le chemin de la base ne déplace pas l''historique : la nouvelle base démarre vide.'
        $fenetre.FindName('CreerBase').IsChecked = $false
        $fenetre.FindName('CreerBase').Content = 'Créer la base à son emplacement (sans effet si elle existe déjà)'
    }
    foreach ($n in 'Racine', 'RacineSource', 'RacineCible', 'Base', 'DossierLogs', 'DossierTravail') {
        $fenetre.FindName($n).Add_TextChanged({ param($s) Update-CopieApercuChemins -Fenetre ([System.Windows.Window]::GetWindow($s)) })
    }
    Update-CopieApercuChemins -Fenetre $fenetre
    $fenetre.FindName('BtnOk').Add_Click({
            param($s)
            $f = [System.Windows.Window]::GetWindow($s)
            $t = $f.Tag
            $saisie = @{}
            foreach ($n in $t.Noms) { $saisie[$n] = $f.FindName($n).Text.Trim() }
            $saisie['Suspendu'] = [bool]$f.FindName('Suspendu').IsChecked
            # Renommage seul : le code de la plateforme de l'ancien nom est conservé si le nouveau nom ne permet pas de le déduire.
            $codeAuto = $false
            if ($t.Mode -eq 'modification' -and $saisie.Nom -cne $t.Origine.Nom -and -not $saisie.CodeEnvironnement -and -not (Get-CopieCodeEnvironnement -Nom $saisie.Nom)) {
                $ancienCode = Get-CopieCodeEnvironnement -Nom "$($t.Origine.Nom)"
                if ($ancienCode) { $saisie.CodeEnvironnement = $ancienCode; $codeAuto = $true }
            }
            $problemes = @(Test-CopieSaisieEnvironnement -Saisie $saisie -Existants $t.Existants -Ignorer $(if ($t.Mode -eq 'modification') { "$($t.Origine.Nom)" } else { '' }))
            if ($problemes.Count -eq 0 -and $t.Mode -eq 'modification' -and $saisie.Nom -cne $t.Origine.Nom) {
                if ($saisie.Suspendu -ne [bool]$t.Origine.Suspendu) { $problemes += 'Changez le nom seul, puis les autres réglages dans une seconde modification.' }
                foreach ($n in $t.Noms) {
                    if ($n -ne 'Nom' -and -not ($n -eq 'CodeEnvironnement' -and $codeAuto) -and $saisie[$n] -cne "$($t.Origine[$n])") { $problemes += 'Changez le nom seul, puis les autres réglages dans une seconde modification.'; break }
                }
            }
            if ($problemes.Count -gt 0) {
                [void][System.Windows.MessageBox]::Show($f, ($problemes -join "`n"), 'Saisie à corriger', 'OK', 'Warning')
                return
            }
            $t.Resultat = @{ Saisie = $saisie; CreerBase = [bool]$f.FindName('CreerBase').IsChecked; DesactiverRegles = [bool]$f.FindName('DesactiverRegles').IsChecked }
            $f.DialogResult = $true
        })
    if ($fenetre.ShowDialog()) { $fenetre.Tag.Resultat } else { $null }
}

function Show-CopieResultatEnvironnement {
    <#
    .SYNOPSIS
        Montre le résultat d'une opération sur un environnement (succès, refus du moteur, erreur) et le journalise.
    .PARAMETER Contexte
        Contexte de la session.
    .PARAMETER Resultat
        Copie.ResultatEnvironnement.
    .PARAMETER Titre
        Titre de la fenêtre.
    .PARAMETER Action
        Nom de l'action, pour le journal.
    .PARAMETER Environnement
        Nom de l'environnement concerné, pour le journal.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [hashtable] $Contexte,
        [Parameter(Mandatory)] [pscustomobject] $Resultat,
        [Parameter(Mandatory)] [string] $Titre,
        [Parameter(Mandatory)] [string] $Action,
        [string] $Environnement = ''
    )
    $niveau = $(if ($Resultat.Ok -and $Resultat.Etape -eq 'ok') { 'INFO' } elseif ($Resultat.Ok) { 'WARNING' } else { 'ERREUR' })
    Write-CopieJournal -Contexte $Contexte -Niveau $niveau -Evenement 'environnement' `
        -Message ('{0} {1} (compte {2}) : {3} - {4}' -f $Action, $Environnement, $Contexte.Utilisateur, $Resultat.Etape, ($Resultat.Message -replace '\s+', ' ')) `
        -Donnees @{ action = $Action; environnement = $Environnement; etape = $Resultat.Etape; compte = $Contexte.Utilisateur }
    if ($Resultat.Etape -eq 'refus' -and $Resultat.Refus.Count -gt 0) {
        Reset-CopieOperation
        Show-CopieDiagnostics -Contexte $Contexte -Reponse ([pscustomobject]@{ Json = [pscustomobject]@{ refus = $Resultat.Refus; avertissements = $Resultat.Avertissements; informations = @() } })
        return
    }
    $gravite = $(if ($Resultat.Ok -and $Resultat.Etape -eq 'ok') { 'Information' } elseif ($Resultat.Ok) { 'Avertissement' } else { 'Erreur' })
    $principale = New-CopieLigneResultat -Gravite $gravite -Sujet $Titre -Message "$($Resultat.Message)"
    Show-CopieOperation -Contexte $Contexte -Titre $Titre -Ligne @($principale)
}

function Get-CopieEnvironnementsActuels {
    <#
    .SYNOPSIS
        Relit le dossier de paramétrage (pour contrôler les doublons avec des données fraîches) ; vide en cas d'erreur.
    .PARAMETER Contexte
        Contexte de la session.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Contexte)
    try { @(Get-CopieEnvironnement -Dossier $Contexte.Dossier -Config $Contexte.Config) } catch { @() }
}

function Invoke-CopieQuestionDossiers {
    <#
    .SYNOPSIS
        Contrôle les dossiers de la base, des journaux et du travail d'un environnement et propose de créer ceux qui manquent (une seule question).

    .DESCRIPTION
        Les chemins sont lus dans l'en-tête du fichier déjà écrit. Le contrôle et la création se font là où tourne
        le moteur (Invoke-CopieDossiersEnvironnement), avec le compte indiqué dans la question. Un dossier qui existe
        mais où l'écriture est refusée, ou qu'on ne peut pas créer, est signalé en clair. Chaque création est tracée.

    .PARAMETER Contexte
        Contexte de la session.

    .PARAMETER Fichier
        Fichier de paramétrage de l'environnement.

    .PARAMETER Poser
        Bloc appelé avec le texte de la question (renvoie $true pour accepter) ; par défaut une fenêtre Oui / Non (tests).

    .PARAMETER Informer
        Bloc appelé avec un message d'information ou d'erreur ; par défaut une fenêtre (tests).

    .OUTPUTS
        [bool] $true si, à la fin, les trois dossiers existent et sont accessibles en écriture.
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter(Mandatory)] [hashtable] $Contexte,
        [Parameter(Mandatory)] [string] $Fichier,
        [scriptblock] $Poser,
        [scriptblock] $Informer
    )
    if ($null -eq $Poser) {
        $Poser = {
            param($texte)
            [System.Windows.MessageBox]::Show($Contexte.Fenetre, $texte, 'Dossiers de l''environnement', 'YesNo', 'Question', 'Yes') -eq [System.Windows.MessageBoxResult]::Yes
        }
    }
    if ($null -eq $Informer) {
        # Pas de boîte « OK » : l'opération en cours montre tout dans sa fenêtre de fin (Show-CopieOperation).
        $Informer = {
            param($texte, $icone)
            Add-CopieLigneOperation -Gravite (Get-CopieGraviteIcone -Icone $icone) -Sujet 'Dossiers de l''environnement' -Message $texte
        }
    }
    $compte = Get-CopieCompteControle -Contexte $Contexte
    $nom = [System.IO.Path]::GetFileNameWithoutExtension($Fichier)
    $controle = Invoke-CopieDossiersEnvironnement -Config $Contexte.Config -Fichier $Fichier -Action 'controler'
    if (-not $controle.Ok) {
        Write-CopieJournal -Contexte $Contexte -Niveau 'ERREUR' -Evenement 'dossiers_environnement' -Message ('controle des dossiers de {0} impossible : {1}' -f $nom, $controle.Message) -Donnees @{ environnement = $nom }
        & $Informer ("Le contrôle des dossiers n'a pas pu être fait : {0}" -f $controle.Message) 'Warning'
        return $false
    }
    $etat = Get-CopieTexteDossiersManquants -Dossier @($controle.Dossiers) -Compte $compte
    if ($etat.ACreer.Count -eq 0 -and $etat.Impossibles.Count -eq 0) {
        Add-CopieLigneOperation -Gravite 'Information' -Sujet 'Dossiers de l''environnement' -Message 'La base, les journaux et le dossier de travail existent et sont accessibles en écriture.'
        return $true
    }
    if ($etat.ACreer.Count -eq 0) {
        & $Informer ($etat.Texte) 'Warning'
        return $false
    }
    if (-not [bool](& $Poser ($etat.Texte + "`n`nCréer les dossiers manquants maintenant ?"))) {
        Write-CopieJournal -Contexte $Contexte -Niveau 'WARNING' -Evenement 'dossiers_environnement' -Message ('creation des dossiers de {0} refusee par l''utilisateur' -f $nom) -Donnees @{ environnement = $nom; a_creer = $etat.ACreer.Count }
        return $false
    }
    $creation = Invoke-CopieDossiersEnvironnement -Config $Contexte.Config -Fichier $Fichier -Action 'creer'
    if (-not $creation.Ok) {
        Write-CopieJournal -Contexte $Contexte -Niveau 'ERREUR' -Evenement 'dossiers_environnement' -Message ('creation des dossiers de {0} impossible : {1}' -f $nom, $creation.Message) -Donnees @{ environnement = $nom }
        & $Informer ("Création impossible : {0}" -f $creation.Message) 'Error'
        return $false
    }
    foreach ($d in @($creation.Dossiers | Where-Object { $_.Cree })) {
        Write-CopieJournal -Contexte $Contexte -Niveau 'INFO' -Evenement 'dossier_cree' -Message ('dossier cree pour {0} ({1}) : {2} (compte {3})' -f $nom, $d.Role, $d.Chemin, $Contexte.Utilisateur) -Donnees @{ environnement = $nom; role = $d.Role; chemin = $d.Chemin }
        Add-CopieLigneOperation -Gravite 'Information' -Sujet 'Dossier créé' -Message ('{0} : {1}' -f $d.Role, $d.Chemin)
    }
    $reste = Get-CopieTexteDossiersManquants -Dossier @($creation.Dossiers) -Compte $compte
    if ($reste.ACreer.Count -gt 0 -or $reste.Impossibles.Count -gt 0) {
        & $Informer ("Tous les dossiers n'ont pas pu être créés :`n`n" + $reste.Texte) 'Error'
        return $false
    }
    $true
}

function Invoke-CopieNouvelEnvironnement {
    <#
    .SYNOPSIS
        Crée un environnement : fenêtre de saisie, vérification par le moteur, fichier, base. Administrateurs seulement.
    .PARAMETER Contexte
        Contexte de la session.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Contexte)
    if ($Contexte.Profil -ne 'Admin') { return }
    Reset-CopieOperation
    $existants = Get-CopieEnvironnementsActuels -Contexte $Contexte
    $saisie = @{}
    while ($true) {
        $reponse = Read-CopieSaisieEnvironnement -Contexte $Contexte -Mode 'creation' -Saisie $saisie -Existants $existants
        if ($null -eq $reponse) { return }
        $saisie = $reponse.Saisie
        $Script:ContexteEnCours = $Contexte
        $Contexte.Fenetre.Cursor = [System.Windows.Input.Cursors]::Wait
        try {
            $res = New-CopieEnvironnement -Config $Contexte.Config -Dossier $Contexte.Dossier -Profil $Contexte.Profil -Saisie $saisie `
                -Compte $Contexte.Utilisateur -InitialiserBase $reponse.CreerBase -Existants $existants `
                -Confirmer { param($a) Confirm-CopieAvertissement -Contexte $Script:ContexteEnCours -Avertissement $a } `
                -PreparerDossiers { param($f) Invoke-CopieQuestionDossiers -Contexte $Script:ContexteEnCours -Fichier $f }
        }
        finally { $Contexte.Fenetre.Cursor = $null }
        Show-CopieResultatEnvironnement -Contexte $Contexte -Resultat $res -Titre 'Nouvel environnement' -Action 'creation' -Environnement $saisie.Nom
        if ($res.Ok) { Update-CopieEnvironnements -Selection $saisie.Nom; return }
        if ($res.Etape -notin 'refus', 'avertissements', 'saisie') { return }     # sinon : on rouvre le formulaire pour corriger
    }
}

function Invoke-CopieCopierEnvironnement {
    <#
    .SYNOPSIS
        Copie un environnement vers un nouveau : même en-tête (sauf nom, base, dossiers propres) et toutes les règles.
    .DESCRIPTION
        Les règles gardent leurs répertoires : c'est à l'utilisateur de les modifier ensuite. Par défaut elles sont
        copiées désactivées, pour que deux environnements ne livrent pas les mêmes fichiers au même endroit.
    .PARAMETER Vue
        Vue de l'environnement à copier.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)
    $ctx = $Vue.Contexte
    if ($ctx.Profil -ne 'Admin' -or $Vue.Occupe) { return }
    Reset-CopieOperation
    $source = Read-CopieFichierParametrage -Chemin $Vue.Env.Fichier
    if ($null -eq $source.Entete -or $source.Erreurs.Count -gt 0) {
        [void][System.Windows.MessageBox]::Show($ctx.Fenetre, ('Le fichier de l''environnement n''est pas lisible, il ne peut pas être copié : ' + ($source.Erreurs -join ' ')), 'Copie impossible', 'OK', 'Error')
        return
    }
    $existants = Get-CopieEnvironnementsActuels -Contexte $ctx
    $saisie = ConvertFrom-CopieEnteteEnvironnement -Entete $source.Entete
    # Un chemin partiel est conservé (il suit la nouvelle racine) ; un chemin complet appartient à l'original : il est vidé.
    $saisie.Nom = ''
    $saisie.Racine = ''
    foreach ($n in 'Base', 'DossierLogs', 'DossierTravail', 'RacineSource', 'RacineCible') {
        if (Test-CopieCheminAbsolu -Chemin "$($saisie[$n])") { $saisie[$n] = '' }
    }
    while ($true) {
        $reponse = Read-CopieSaisieEnvironnement -Contexte $ctx -Mode 'copie' -Saisie $saisie -Existants $existants
        if ($null -eq $reponse) { return }
        $saisie = $reponse.Saisie
        $Script:ContexteEnCours = $ctx
        $ctx.Fenetre.Cursor = [System.Windows.Input.Cursors]::Wait
        try {
            $res = New-CopieEnvironnement -Config $ctx.Config -Dossier $ctx.Dossier -Profil $ctx.Profil -Saisie $saisie -Compte $ctx.Utilisateur `
                -InitialiserBase $reponse.CreerBase -Existants $existants -Regle @($source.Regles) -DesactiverRegles $reponse.DesactiverRegles `
                -Confirmer { param($a) Confirm-CopieAvertissement -Contexte $Script:ContexteEnCours -Avertissement $a } `
                -PreparerDossiers { param($f) Invoke-CopieQuestionDossiers -Contexte $Script:ContexteEnCours -Fichier $f }
        }
        finally { $ctx.Fenetre.Cursor = $null }
        Show-CopieResultatEnvironnement -Contexte $ctx -Resultat $res -Titre 'Copier un environnement' -Action 'copie' -Environnement ('{0} -> {1}' -f $Vue.Env.Nom, $saisie.Nom)
        if ($res.Ok) { Update-CopieEnvironnements -Selection $saisie.Nom; return }
        if ($res.Etape -notin 'refus', 'avertissements', 'saisie') { return }
    }
}

function Invoke-CopieModifierEnvironnement {
    <#
    .SYNOPSIS
        Modifie un environnement : renommage, ou réglages de l'en-tête (base, dossiers, parallélisme, rétentions).
    .PARAMETER Vue
        Vue de l'environnement choisi.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)
    $ctx = $Vue.Contexte
    if ($ctx.Profil -ne 'Admin' -or $Vue.Occupe) { return }
    if (-not $Vue.Env.Modifiable) {
        [void][System.Windows.MessageBox]::Show($ctx.Fenetre, ('Cet environnement est en lecture seule : ' + $Vue.Env.Message), 'Modification impossible', 'OK', 'Warning')
        return
    }
    $frais = Read-CopieFichierParametrage -Chemin $Vue.Env.Fichier
    if ($frais.Empreinte -ne $Vue.Env.Parametrage.Empreinte) {
        [void][System.Windows.MessageBox]::Show($ctx.Fenetre, 'Le fichier a été modifié depuis son affichage. Il est rechargé : recommencez.', 'Fichier modifié', 'OK', 'Information')
        Update-CopieEnvironnements -Selection $Vue.Env.Nom
        return
    }
    $origine = ConvertFrom-CopieEnteteEnvironnement -Entete $Vue.Env.Parametrage.Entete
    $existants = Get-CopieEnvironnementsActuels -Contexte $ctx
    $saisie = $origine
    Reset-CopieOperation
    while ($true) {
        $reponse = Read-CopieSaisieEnvironnement -Contexte $ctx -Mode 'modification' -Saisie $saisie -Existants $existants
        if ($null -eq $reponse) { return }
        $nouveau = $reponse.Saisie
        $renomme = ($nouveau.Nom -cne $origine.Nom)
        $change = $false
        foreach ($n in $origine.Keys) { if ($nouveau[$n] -cne "$($origine[$n])") { $change = $true } }
        if (-not $change -and -not $reponse.CreerBase) { return }       # rien à faire : on ne dérange pas l'utilisateur
        if ($renomme) {
            $suite = Invoke-CopieRenommage -Vue $Vue -NouveauNom $nouveau.Nom -Existants $existants
            if ($suite -eq 'corriger') { $saisie = $nouveau; continue }
            return
        }
        if ($change) {
            if ($nouveau.Base -cne $origine.Base) {
                $r = [System.Windows.MessageBox]::Show($ctx.Fenetre, ("Vous changez le chemin de la base.`n`nL'historique et l'état des règles restent dans l'ancienne base ({0}) ; la nouvelle base démarre vide : les fichiers déjà livrés ne seront plus reconnus et pourraient être relivrés.`n`nContinuer ?" -f (Get-CopieCheminsEnvironnement -Entete $Vue.Env.Parametrage.Entete).Base), 'Changement de base', 'YesNo', 'Warning', 'No')
                if ($r -ne [System.Windows.MessageBoxResult]::Yes) { $saisie = $nouveau; continue }
            }
            $entete = ConvertTo-CopieEnteteEnvironnement -Saisie $nouveau
            $issue = Invoke-CopieEnregistrement -Vue $Vue -Regle @($Vue.Env.Parametrage.Regles) -Entete $entete `
                -Question ('Modification de l''environnement « {0} »' -f $origine.Nom) -Action 'modification_environnement' -IdRegle '(environnement)'
            if ($issue -eq 'corriger') { $saisie = $nouveau; continue }
            if ($issue -ne 'ok') { Reset-CopieOperation; Update-CopieEnvironnements -Selection $origine.Nom; return }
            Add-CopieLigneOperation -Gravite 'Information' -Sujet 'Enregistrement' -Message ('Les réglages de l''environnement « {0} » sont enregistrés.' -f $origine.Nom)
        }
        $dossiersPrets = Invoke-CopieQuestionDossiers -Contexte $ctx -Fichier $Vue.Env.Fichier
        if ($reponse.CreerBase -and -not $dossiersPrets) {
            Add-CopieLigneOperation -Gravite 'Avertissement' -Sujet 'Base' -Message 'Base NON créée : les dossiers de la base, des journaux ou du travail ne sont pas prêts.'
        }
        elseif ($reponse.CreerBase) {
            $b = Initialize-CopieBaseEnvironnement -Config $ctx.Config -Fichier $Vue.Env.Fichier -Compte $ctx.Utilisateur
            $texte = switch ($b.Statut) { 'creee' { 'Base créée.' } 'existante' { 'La base existe déjà : rien à créer.' } default { 'Base NON créée : ' + $b.Message } }
            Write-CopieJournal -Contexte $ctx -Niveau $(if ($b.Statut -eq 'echec') { 'ERREUR' } else { 'INFO' }) -Evenement 'environnement' -Message ('creation_base {0} : {1}' -f $origine.Nom, $texte) `
                -Donnees @{ action = 'creation_base'; environnement = $origine.Nom; etape = $b.Statut }
            Add-CopieLigneOperation -Gravite $(if ($b.Statut -eq 'echec') { 'Erreur' } else { 'Information' }) -Sujet 'Base' -Message $texte
        }
        Show-CopieOperation -Contexte $ctx -Titre 'Modification de l''environnement' -Debut ('Environnement « {0} ».' -f $origine.Nom)
        Update-CopieEnvironnements -Selection $origine.Nom
        return
    }
}

function Invoke-CopieRenommage {
    <#
    .SYNOPSIS
        Renomme l'environnement d'une vue après avoir demandé la raison (commentaire).
    .PARAMETER Vue
        Vue de l'environnement.
    .PARAMETER NouveauNom
        Nouveau nom.
    .PARAMETER Existants
        Environnements présents (doublons).
    .OUTPUTS
        [string] ok, corriger (rouvrir la saisie) ou abandon.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [hashtable] $Vue, [Parameter(Mandatory)] [string] $NouveauNom, [AllowEmptyCollection()] [object[]] $Existants = @())
    $ctx = $Vue.Contexte
    $ancien = $Vue.Env.Nom
    Reset-CopieOperation
    $commentaire = Read-CopieCommentaire -Contexte $ctx -Question ('Renommer l''environnement « {0} » en « {1} »' -f $ancien, $NouveauNom)
    if ($null -eq $commentaire) { return 'corriger' }
    $Script:ContexteEnCours = $ctx
    $ctx.Fenetre.Cursor = [System.Windows.Input.Cursors]::Wait
    try {
        $res = Rename-CopieEnvironnement -Config $ctx.Config -Environnement $Vue.Env -NouveauNom $NouveauNom -Profil $ctx.Profil `
            -Compte $ctx.Utilisateur -Commentaire $commentaire -Existants $Existants `
            -Confirmer { param($a) Confirm-CopieAvertissement -Contexte $Script:ContexteEnCours -Avertissement $a }
    }
    finally { $ctx.Fenetre.Cursor = $null }
    Show-CopieResultatEnvironnement -Contexte $ctx -Resultat $res -Titre 'Renommer l''environnement' -Action 'renommage' -Environnement ('{0} -> {1}' -f $ancien, $NouveauNom)
    if ($res.Ok) { Update-CopieEnvironnements -Selection $NouveauNom; return 'ok' }
    if ($res.Etape -in 'refus', 'avertissements', 'saisie') { return 'corriger' }
    Update-CopieEnvironnements -Selection $ancien
    'abandon'
}

function Invoke-CopieCreerBase {
    <#
    .SYNOPSIS
        Crée la base d'un environnement dont la base n'existe pas encore (--initialiser-base).
    .PARAMETER Vue
        Vue de l'environnement.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)
    $ctx = $Vue.Contexte
    if ($ctx.Profil -ne 'Admin' -or $Vue.Occupe) { return }
    $chemin = (Get-CopieCheminsEnvironnement -Entete $Vue.Env.Parametrage.Entete).Base
    $r = [System.Windows.MessageBox]::Show($ctx.Fenetre, ("Créer la base de l'environnement « {0} » ?`n`n{1}`n`nLe moteur refuse d'écraser une base qui existe déjà." -f $Vue.Env.Nom, $chemin), 'Créer la base', 'YesNo', 'Question')
    if ($r -ne [System.Windows.MessageBoxResult]::Yes) { return }
    Reset-CopieOperation
    if (-not (Invoke-CopieQuestionDossiers -Contexte $ctx -Fichier $Vue.Env.Fichier)) {
        Add-CopieLigneOperation -Gravite 'Avertissement' -Sujet 'Base' -Message 'Base NON créée : les dossiers de la base, des journaux ou du travail ne sont pas prêts.'
        Show-CopieOperation -Contexte $ctx -Titre 'Créer la base' -Debut ('Environnement « {0} ».' -f $Vue.Env.Nom)
        return
    }
    $ctx.Fenetre.Cursor = [System.Windows.Input.Cursors]::Wait
    try { $b = Initialize-CopieBaseEnvironnement -Config $ctx.Config -Fichier $Vue.Env.Fichier -Compte $ctx.Utilisateur }
    finally { $ctx.Fenetre.Cursor = $null }
    $texte = switch ($b.Statut) { 'creee' { 'Base créée : ' + $chemin } 'existante' { 'La base existe déjà : rien à créer.' } default { 'Base NON créée : ' + $b.Message } }
    Write-CopieJournal -Contexte $ctx -Niveau $(if ($b.Statut -eq 'echec') { 'ERREUR' } else { 'INFO' }) -Evenement 'environnement' -Message ('creation_base {0} (compte {1}) : {2}' -f $Vue.Env.Nom, $ctx.Utilisateur, $b.Statut) `
        -Donnees @{ action = 'creation_base'; environnement = $Vue.Env.Nom; etape = $b.Statut; compte = $ctx.Utilisateur }
    Add-CopieLigneOperation -Gravite $(if ($b.Statut -eq 'echec') { 'Erreur' } else { 'Information' }) -Sujet 'Base' -Message $texte
    Show-CopieOperation -Contexte $ctx -Titre 'Créer la base' -Debut ('Environnement « {0} ».' -f $Vue.Env.Nom)
    Update-CopieEtatVue -Vue $Vue
}

function Read-CopieConfirmationSuppression {
    <#
    .SYNOPSIS
        Second contrôle de la suppression : saisir le nom exact de l'environnement et un commentaire.
    .PARAMETER Contexte
        Contexte de la session.
    .PARAMETER Nom
        Nom de l'environnement à supprimer.
    .OUTPUTS
        Le commentaire, ou $null si annulé.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Contexte, [Parameter(Mandatory)] [string] $Nom)
    $fenetre = Import-CopieXaml -Nom 'Dialog.Suppression'
    if ($null -ne $Contexte.Fenetre) { $fenetre.Owner = $Contexte.Fenetre }
    $fenetre.Tag = @{ Nom = $Nom }
    $fenetre.FindName('Question').Text = ('Supprimer l''environnement « {0} » ?' -f $Nom)
    $fenetre.FindName('Consigne').Text = ('Pour confirmer, saisissez exactement son nom : {0}' -f $Nom)
    $verifier = {
        param($s)
        $f = [System.Windows.Window]::GetWindow($s)
        $f.FindName('BtnOk').IsEnabled = ($f.FindName('Nom').Text -ceq $f.Tag.Nom -and $f.FindName('Commentaire').Text.Trim().Length -gt 0)
    }
    $fenetre.FindName('Nom').Add_TextChanged($verifier)
    $fenetre.FindName('Commentaire').Add_TextChanged($verifier)
    $fenetre.FindName('BtnOk').Add_Click({ param($s) [System.Windows.Window]::GetWindow($s).DialogResult = $true })
    if ($fenetre.ShowDialog()) { $fenetre.FindName('Commentaire').Text.Trim() } else { $null }
}

function Invoke-CopieSupprimerEnvironnement {
    <#
    .SYNOPSIS
        Supprime un environnement après une double validation : avertissement, puis saisie du nom exact.
    .DESCRIPTION
        Rien n'est effacé : le fichier et ses versions sont rangés, la base est laissée (voir Remove-CopieEnvironnement).
    .PARAMETER Vue
        Vue de l'environnement choisi.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)
    $ctx = $Vue.Contexte
    if ($ctx.Profil -ne 'Admin' -or $Vue.Occupe) { return }
    $nom = $Vue.Env.Nom
    $nombre = @($Vue.Env.Parametrage.Regles).Count
    $texte = ("Vous allez supprimer l'environnement « {0} » ({1} règle(s)).`n`n" +
        "- Il disparaît de l'outil : ses règles ne seront plus lancées par Jenkins (les jobs qui le citent échoueront).`n" +
        "- Son fichier et ses versions sont rangés dans {2}, rien n'est effacé.`n" +
        "- Sa base, ses journaux et ses archives ne sont pas touchés.`n`nContinuer ?") -f $nom, $nombre, $ctx.Config.Parametrage.DossierSupprimes
    $r = [System.Windows.MessageBox]::Show($ctx.Fenetre, $texte, 'Supprimer un environnement (1/2)', 'YesNo', 'Warning', 'No')
    if ($r -ne [System.Windows.MessageBoxResult]::Yes) { return }
    $commentaire = Read-CopieConfirmationSuppression -Contexte $ctx -Nom $nom
    if ($null -eq $commentaire) { return }
    $ctx.Fenetre.Cursor = [System.Windows.Input.Cursors]::Wait
    try { $res = Remove-CopieEnvironnement -Config $ctx.Config -Environnement $Vue.Env -Profil $ctx.Profil -Compte $ctx.Utilisateur -Commentaire $commentaire }
    finally { $ctx.Fenetre.Cursor = $null }
    Show-CopieResultatEnvironnement -Contexte $ctx -Resultat $res -Titre 'Supprimer un environnement' -Action 'suppression' -Environnement $nom
    Update-CopieEnvironnements
}

function Update-CopieBarreEnvironnements {
    <#
    .SYNOPSIS
        Montre la barre de gestion des environnements aux administrateurs et active ses boutons selon l'onglet choisi.
    #>
    [CmdletBinding()]
    param()
    $session = $Script:Session
    if ($null -eq $session -or $null -eq $session.Barre) { return }
    $ctx = $session.Contexte
    $admin = ($ctx.Profil -eq 'Admin')
    $session.Barre.Visibility = $(if ($admin) { 'Visible' } else { 'Collapsed' })
    $vue = $null
    if ($session.Tabs.SelectedItem -and $session.Tabs.SelectedItem.Tag) { $vue = $session.Tabs.SelectedItem.Tag }
    $pret = ($null -ne $vue -and -not $vue.Occupe)
    $session.BtnNouveau.IsEnabled = $admin
    $session.BtnModifier.IsEnabled = ($admin -and $pret -and $vue.Env.Modifiable)
    $session.BtnSupprimer.IsEnabled = ($admin -and $pret)
    $session.BtnBase.IsEnabled = ($admin -and $pret -and $vue.Env.Modifiable)
    $session.BtnCopier.IsEnabled = ($admin -and $pret -and $null -ne $vue.Env.Parametrage.Entete -and $vue.Env.Parametrage.Erreurs.Count -eq 0)
}
