# Actions d'édition d'un environnement (étape B) : ajouter, dupliquer, modifier, activer/désactiver, supprimer.
# Toute écriture passe par Save-CopieParametrage (vérification du moteur, versions, remplacement atomique).

function Read-CopieCommentaire {
    <#
    .SYNOPSIS
        Demande le commentaire obligatoire d'un enregistrement.
    .PARAMETER Contexte
        Contexte de la session.
    .PARAMETER Question
        Ce qu'on s'apprête à faire (rappelé en tête de la fenêtre).
    .PARAMETER Facultatif
        Le commentaire peut rester vide (la fonction renvoie alors une chaîne vide).
    .OUTPUTS
        Le commentaire, ou $null si annulé.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Contexte, [Parameter(Mandatory)] [string] $Question, [switch] $Facultatif)
    $fenetre = Import-CopieXaml -Nom 'Dialog.Commentaire'
    $fenetre.Tag = @{ Facultatif = [bool]$Facultatif }
    if ($null -ne $Contexte.Fenetre) { $fenetre.Owner = $Contexte.Fenetre }
    $fenetre.FindName('Question').Text = $Question
    $fenetre.FindName('BtnOk').Add_Click({
            param($s)
            $f = [System.Windows.Window]::GetWindow($s)
            if ($f.FindName('Commentaire').Text.Trim().Length -eq 0 -and -not $f.Tag.Facultatif) {
                [void][System.Windows.MessageBox]::Show($f, 'Le commentaire est obligatoire.', 'Commentaire', 'OK', 'Information')
                return
            }
            $f.DialogResult = $true
        })
    if ($fenetre.ShowDialog()) { $fenetre.FindName('Commentaire').Text.Trim() } else { $null }
}

function Confirm-CopieAvertissement {
    <#
    .SYNOPSIS
        Montre les avertissements du moteur et demande s'il faut enregistrer quand même.
    .PARAMETER Contexte
        Contexte de la session.
    .PARAMETER Avertissement
        Avertissements (code, message).
    .OUTPUTS
        [bool]
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Contexte, [Parameter(Mandatory)] [object[]] $Avertissement)
    $texte = (@($Avertissement | ForEach-Object { '- {0} {1}' -f (Get-CopieValeur $_ 'code' ''), (Get-CopieValeur $_ 'message' '') }) -join "`n")
    $r = [System.Windows.MessageBox]::Show($Contexte.Fenetre, ("Le moteur accepte ce paramétrage mais signale :`n`n" + $texte + "`n`nEnregistrer quand même ?"), 'Avertissements', 'YesNo', 'Warning')
    $r -eq [System.Windows.MessageBoxResult]::Yes
}

function Sync-CopieParametrage {
    <#
    .SYNOPSIS
        Relit le fichier d'un environnement et met la vue à jour.
    .PARAMETER Vue
        Vue d'un environnement.
    .PARAMETER Selection
        Identifiant de la règle à resélectionner après le rechargement.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue, [string] $Selection = '')
    $Vue.Env.Parametrage = Read-CopieFichierParametrage -Chemin $Vue.Env.Fichier
    Update-CopieVue -Vue $Vue
    $tiret = [string][char]0x2014
    $Vue.Info.Text = ('{0}  {1}  {2} règle(s)' -f (Split-Path -Leaf $Vue.Env.Fichier), $tiret, @($Vue.Env.Parametrage.Regles).Count)
    if ($Selection) {
        $ligne = @($Vue.Lignes | Where-Object { $_.Id -eq $Selection }) | Select-Object -First 1
        if ($null -ne $ligne) { $Vue.Grille.SelectedItem = $ligne; $Vue.Grille.ScrollIntoView($ligne) }
    }
    Update-CopieBoutons -Vue $Vue
}

function Update-CopieEtatVue {
    <#
    .SYNOPSIS
        Bouton « Actualiser l'état » : relit le fichier et l'état des règles, en gardant la règle choisie.
    .PARAMETER Vue
        Vue d'un environnement.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)
    if ($Vue.Occupe) { return }
    $choisie = $Vue.Grille.SelectedItem
    Sync-CopieParametrage -Vue $Vue -Selection $(if ($null -ne $choisie) { $choisie.Id } else { '' })
}

function Update-CopieBoutons {
    <#
    .SYNOPSIS
        Active les boutons : édition (administrateur, environnement modifiable), exploitation (administrateur,
        fichier lisible), et règle choisie quand l'action en exige une. Tout est grisé pendant un appel en arrière-plan.
    .PARAMETER Vue
        Vue d'un environnement.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)
    $admin = ($Vue.Contexte.Profil -eq 'Admin')
    $occupe = [bool]$Vue.Occupe
    $parametrage = $Vue.Env.Parametrage
    $lisible = ($null -ne $parametrage.Entete -and $parametrage.Erreurs.Count -eq 0)
    $choisie = ($null -ne $Vue.Grille.SelectedItem)
    $edition = $admin -and $Vue.Env.Modifiable
    $exploitation = $admin -and $lisible
    $visible = { param($v) if ($v) { 'Visible' } else { 'Collapsed' } }
    $Vue.Ajouter.IsEnabled = ($edition -and -not $occupe)
    foreach ($b in $Vue.Dupliquer, $Vue.Modifier, $Vue.Activer, $Vue.Supprimer) { $b.IsEnabled = ($edition -and $choisie -and -not $occupe) }
    $Vue.Activer.Content = $(if ($choisie -and $Vue.Grille.SelectedItem.Actif -eq 'Oui') { 'Désactiver' } else { 'Activer' })
    foreach ($b in $Vue.Ajouter, $Vue.Dupliquer, $Vue.Modifier, $Vue.Activer, $Vue.Supprimer) { $b.Visibility = & $visible $edition }
    foreach ($b in $Vue.Reprise, $Vue.Lancer, $Vue.Acquitter, $Vue.Debloquer) { $b.Visibility = & $visible $exploitation; $b.IsEnabled = ($exploitation -and $choisie -and -not $occupe) }
    $Vue.Purger.Visibility = & $visible $exploitation
    $Vue.Purger.IsEnabled = ($exploitation -and -not $occupe)
    $Vue.Verifier.IsEnabled = (-not $occupe)
    $Vue.Actualiser.IsEnabled = (-not $occupe)
}

function Invoke-CopieEnregistrement {
    <#
    .SYNOPSIS
        Demande un commentaire, enregistre le paramétrage et gère le résultat (refus, avertissements, conflit).

    .DESCRIPTION
        Renvoie 'ok' si le fichier est enregistré, 'corriger' si l'utilisateur veut reprendre la saisie
        (refus du moteur, avertissements non acceptés), 'abandon' sinon (conflit, erreur, annulation).

    .PARAMETER Vue
        Vue d'un environnement.
    .PARAMETER Regle
        Liste complète des règles à écrire.
    .PARAMETER Question
        Description de l'action, pour la fenêtre de commentaire.
    .PARAMETER Action
        Nom de l'action, pour le journal.
    .PARAMETER IdRegle
        Règle concernée, pour le journal.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)] [hashtable] $Vue,
        [Parameter(Mandatory)] [AllowEmptyCollection()] [object[]] $Regle,
        [Parameter(Mandatory)] [string] $Question,
        [Parameter(Mandatory)] [string] $Action,
        [Parameter(Mandatory)] [string] $IdRegle
    )
    $ctx = $Vue.Contexte
    $commentaire = Read-CopieCommentaire -Contexte $ctx -Question $Question
    if ($null -eq $commentaire) { return 'corriger' }
    $ctx.Fenetre.Cursor = [System.Windows.Input.Cursors]::Wait
    try {
        $confirmer = { param($a) Confirm-CopieAvertissement -Contexte $Script:ContexteEnCours -Avertissement $a }
        $Script:ContexteEnCours = $ctx
        $res = Save-CopieParametrage -Config $ctx.Config -Fichier $Vue.Env.Fichier -EmpreinteAttendue $Vue.Env.Parametrage.Empreinte `
            -Entete $Vue.Env.Parametrage.Entete -Regle $Regle -Compte $ctx.Utilisateur -Commentaire $commentaire -Confirmer $confirmer
    }
    finally { $ctx.Fenetre.Cursor = $null }

    $niveau = $(if ($res.Enregistre) { 'INFO' } else { 'WARNING' })
    Write-CopieJournal -Contexte $ctx -Niveau $niveau -Evenement 'parametrage_enregistrement' `
        -Message ('{0} {1} dans {2} : {3}' -f $Action, $IdRegle, $Vue.Env.Nom, $res.Etape) `
        -Donnees @{ environnement = $Vue.Env.Nom; regle = $IdRegle; action = $Action; etape = $res.Etape; commentaire = $commentaire }
    if ($res.Enregistre) { return 'ok' }

    switch ($res.Etape) {
        'refus' {
            Show-CopieDiagnostics -Contexte $ctx -Reponse ([pscustomobject]@{ Json = [pscustomobject]@{ refus = $res.Refus; avertissements = $res.Avertissements; informations = @() } })
            return 'corriger'
        }
        'avertissements' { return 'corriger' }
        'conflit' {
            [void][System.Windows.MessageBox]::Show($ctx.Fenetre, ($res.Message + "`n`nLe fichier va être rechargé ; refaites votre modification."), 'Fichier modifié', 'OK', 'Warning')
            return 'abandon'
        }
        default {
            [void][System.Windows.MessageBox]::Show($ctx.Fenetre, $res.Message, 'Enregistrement', 'OK', 'Error')
            return 'abandon'
        }
    }
}

function Invoke-CopieEdition {
    <#
    .SYNOPSIS
        Exécute une action d'édition sur un environnement : ajout, duplication, modification, activation, suppression.

    .DESCRIPTION
        Le fichier est relu avant d'agir : s'il a changé depuis son affichage, la vue est rechargée et
        l'action est abandonnée (aucune écriture sur des données périmées). Après un refus du moteur, le
        formulaire est rouvert avec la saisie pour la corriger.

    .PARAMETER Vue
        Vue d'un environnement.
    .PARAMETER Action
        ajout, duplication, modification, activation ou suppression.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [hashtable] $Vue,
        [Parameter(Mandatory)] [ValidateSet('ajout', 'duplication', 'modification', 'activation', 'suppression')] [string] $Action
    )
    $ctx = $Vue.Contexte
    if ($ctx.Profil -ne 'Admin' -or -not $Vue.Env.Modifiable) { return }
    $choisie = $Vue.Grille.SelectedItem
    if ($Action -ne 'ajout' -and $null -eq $choisie) { return }
    $idChoisi = $(if ($null -ne $choisie) { $choisie.Id } else { '' })

    # Données fraîches : on n'édite jamais une vue périmée.
    $frais = Read-CopieFichierParametrage -Chemin $Vue.Env.Fichier
    if ($frais.Empreinte -ne $Vue.Env.Parametrage.Empreinte) {
        [void][System.Windows.MessageBox]::Show($ctx.Fenetre, 'Le fichier a été modifié depuis son affichage. Il est rechargé : recommencez votre action.', 'Fichier modifié', 'OK', 'Information')
        Sync-CopieParametrage -Vue $Vue -Selection $idChoisi
        return
    }
    if ($frais.Erreurs.Count -gt 0 -or $null -eq $frais.Entete) {
        [void][System.Windows.MessageBox]::Show($ctx.Fenetre, ('Le fichier n''est pas lisible, il ne peut pas être modifié : ' + ($frais.Erreurs -join ' ')), 'Édition impossible', 'OK', 'Error')
        return
    }
    try { $modele = Get-CopieModeleRegle -Config $ctx.Config }
    catch {
        [void][System.Windows.MessageBox]::Show($ctx.Fenetre, $_.Exception.Message, 'Moteur injoignable', 'OK', 'Error')
        return
    }

    $regles = @($frais.Regles)
    $ids = @($regles | ForEach-Object { "$(Get-CopieValeur $_ 'id' '')".ToLowerInvariant() })
    $existante = $regles | Where-Object { "$(Get-CopieValeur $_ 'id' '')" -eq $idChoisi } | Select-Object -First 1

    switch ($Action) {
        'activation' {
            $nouveau = Merge-CopieRegle -Modele $modele.regle -Existante $existante
            $nouveau.actif = -not [bool](Get-CopieValeur $existante 'actif' $true)
            $verbe = $(if ($nouveau.actif) { 'activer' } else { 'désactiver' })
            $liste = @($regles | ForEach-Object { if ("$(Get-CopieValeur $_ 'id' '')" -eq $idChoisi) { $nouveau } else { $_ } })
            $r = Invoke-CopieEnregistrement -Vue $Vue -Regle $liste -Question ('Vous allez {0} la règle « {1} ».' -f $verbe, $idChoisi) -Action $verbe -IdRegle $idChoisi
            if ($r -eq 'ok') { Sync-CopieParametrage -Vue $Vue -Selection $idChoisi } elseif ($r -eq 'abandon') { Sync-CopieParametrage -Vue $Vue -Selection $idChoisi }
            return
        }
        'suppression' {
            $liste = @($regles | Where-Object { "$(Get-CopieValeur $_ 'id' '')" -ne $idChoisi })
            $conf = [System.Windows.MessageBox]::Show($ctx.Fenetre, ("Supprimer la règle « {0} » du fichier ?`n`nSon historique dans la base est conservé jusqu'à la purge. La version actuelle du fichier est gardée dans le dossier des versions." -f $idChoisi), 'Supprimer la règle', 'YesNo', 'Warning')
            if ($conf -ne [System.Windows.MessageBoxResult]::Yes) { return }
            $r = Invoke-CopieEnregistrement -Vue $Vue -Regle $liste -Question ('Vous allez supprimer la règle « {0} ».' -f $idChoisi) -Action 'supprimer' -IdRegle $idChoisi
            if ($r -ne 'corriger') { Sync-CopieParametrage -Vue $Vue }
            return
        }
    }

    # ajout, duplication, modification : formulaire, avec reprise de la saisie après un refus.
    $depart = switch ($Action) {
        'ajout' { Merge-CopieRegle -Modele $modele.regle -Existante $null }
        'duplication' {
            $copie = Merge-CopieRegle -Modele $modele.regle -Existante $existante
            $copie.id = $idChoisi + '_copie'
            $copie
        }
        default { Merge-CopieRegle -Modele $modele.regle -Existante $existante }
    }
    while ($true) {
        $saisie = Show-CopieFormulaireRegle -Contexte $ctx -Modele $modele -Regle $depart -Mode $Action -IdsExistants $ids
        if ($null -eq $saisie) { return }
        $nouvelId = "$($saisie.id)"
        if ($Action -eq 'modification') {
            $liste = @($regles | ForEach-Object { if ("$(Get-CopieValeur $_ 'id' '')" -eq $idChoisi) { $saisie } else { $_ } })
            $question = 'Vous allez modifier la règle « {0} ».' -f $nouvelId
            $verbe = 'modifier'
        }
        else {
            $liste = @($regles) + @($saisie)
            $question = 'Vous allez ajouter la règle « {0} ».' -f $nouvelId
            $verbe = $(if ($Action -eq 'duplication') { 'dupliquer' } else { 'ajouter' })
        }
        $r = Invoke-CopieEnregistrement -Vue $Vue -Regle $liste -Question $question -Action $verbe -IdRegle $nouvelId
        if ($r -eq 'ok') {
            Sync-CopieParametrage -Vue $Vue -Selection $nouvelId
            $suite = [System.Windows.MessageBox]::Show($ctx.Fenetre, ("Règle « {0} » enregistrée.`n`nLancer maintenant la vérification complète (accès aux dossiers, programmes...) ?" -f $nouvelId), 'Enregistré', 'YesNo', 'Information')
            if ($suite -eq [System.Windows.MessageBoxResult]::Yes) { Invoke-CopieVerification -Vue $Vue }
            return
        }
        if ($r -eq 'abandon') { Sync-CopieParametrage -Vue $Vue -Selection $idChoisi; return }
        $depart = $saisie       # refus : on rouvre le formulaire avec ce qui vient d'être saisi
    }
}
