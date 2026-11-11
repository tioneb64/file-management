# Simulation d'une règle (étape F) : « déplacera X fichier(s) du répertoire R vers le répertoire D », sans rien écrire.
# Ouverte à tous les comptes : le moteur lit la base en lecture seule et ne touche à aucun fichier.

function Show-CopieSimulation {
    <#
    .SYNOPSIS
        Fenêtre du résultat d'une simulation : phrase de synthèse, remarques, liste des fichiers.
    .PARAMETER Contexte
        Contexte de la session.
    .PARAMETER Regle
        Identifiant de la règle simulée.
    .PARAMETER Resume
        Résultat de ConvertTo-CopieResumeSimulation.
    .OUTPUTS
        [bool] $true si l'administrateur demande la création des dossiers manquants (le bouton n'est montré qu'à lui).
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param([Parameter(Mandatory)] [hashtable] $Contexte, [Parameter(Mandatory)] [string] $Regle, [Parameter(Mandatory)] [pscustomobject] $Resume)
    $fenetre = Import-CopieXaml -Nom 'Dialog.Simulation'
    if ($null -ne $Contexte.Fenetre) { $fenetre.Owner = $Contexte.Fenetre }
    $fenetre.Title = 'Simulation de la règle « {0} »' -f $Regle
    $resumeTexte = $fenetre.FindName('Resume')
    $resumeTexte.Text = $Resume.Phrase
    $couleur = switch ($Resume.Niveau) { 'ERREUR' { '#9A2A1F' } 'WARNING' { '#8A5A00' } default { '#1F3A5F' } }
    $resumeTexte.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString($couleur)
    $fenetre.FindName('Remarques').Text = ($Resume.Remarques -join "`n")
    $fenetre.FindName('Grille').ItemsSource = $Resume.Lignes
    $fenetre.FindName('GrilleControles').ItemsSource = $Resume.Controles
    $fenetre.Tag = @{ Creer = $false }
    if ($Contexte.Profil -eq 'Admin' -and @($Resume.ACreer).Count -gt 0) {
        $bouton = $fenetre.FindName('BtnCreer')
        $bouton.Visibility = 'Visible'
        $bouton.Add_Click({ param($s) $f = [System.Windows.Window]::GetWindow($s); $f.Tag.Creer = $true; $f.Close() })
    }
    $null = $fenetre.ShowDialog()
    [bool]$fenetre.Tag.Creer
}

function Invoke-CopieCreationDossiersRegle {
    <#
    .SYNOPSIS
        Crée les dossiers manquants d'une règle (source, cible, temporaire, archive) avec le compte du moteur ; trace chaque création.
    .DESCRIPTION
        Par défaut, une question Oui / Non liste les dossiers. L'appelant qui a déjà posé la question passe -SansQuestion.
        Le résultat n'est pas affiché ici quand -SansResultat est donné (l'appelant le rassemble dans sa fenêtre) ; sinon,
        seuls les échecs sont montrés : une création réussie se voit à la simulation relancée.
    .PARAMETER Vue
        Vue d'un environnement.
    .PARAMETER Regle
        Identifiant de la règle.
    .PARAMETER Dossier
        Dossiers à créer (lignes ACreer de la simulation), montrés dans la question.
    .PARAMETER SansQuestion
        L'accord a déjà été demandé.
    .PARAMETER SansResultat
        N'affiche rien : l'appelant lit les propriétés du résultat.
    .OUTPUTS
        [pscustomobject] Fait (au moins un dossier créé), Refuse (question refusée), Crees, Echecs, Erreur.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)] [hashtable] $Vue, [Parameter(Mandatory)] [string] $Regle, [Parameter(Mandatory)] [object[]] $Dossier,
        [switch] $SansQuestion, [switch] $SansResultat
    )
    $ctx = $Vue.Contexte
    $sortie = [pscustomobject]@{ Fait = $false; Refuse = $false; Crees = @(); Echecs = @(); Erreur = '' }
    if ($ctx.Profil -ne 'Admin') { return $sortie }
    if (-not $SansQuestion) {
        $liste = (@($Dossier | ForEach-Object { '- {0} : {1}' -f $_.Role, $_.Chemin }) -join "`n")
        $r = [System.Windows.MessageBox]::Show($ctx.Fenetre, ("Créer ces dossiers avec le compte du moteur ?`n`n{0}`n`nAu lancement, le moteur ne crée jamais le répertoire d'origine seul : cette création est faite uniquement ici, sur votre demande." -f $liste), 'Créer les dossiers manquants', 'YesNo', 'Question')
        if ($r -ne [System.Windows.MessageBoxResult]::Yes) { $sortie.Refuse = $true; return $sortie }
    }
    $reponse = Invoke-CopieMoteur -Config $ctx.Config -Fichier $Vue.Env.Fichier -Argument @('--creer-dossiers-regle', $Regle, '--utilisateur', $ctx.Utilisateur)
    $sortie.Crees = @(Get-CopieValeur $reponse.Json 'crees' @())
    $sortie.Echecs = @(Get-CopieValeur $reponse.Json 'echecs' @())
    Write-CopieJournal -Contexte $ctx -Niveau $(if ($reponse.Reussi) { 'INFO' } else { 'ERREUR' }) -Evenement 'exploitation' `
        -Message ('creation_dossiers {0} dans {1} (compte {2}) : {3} créé(s), {4} échec(s)' -f $Regle, $Vue.Env.Nom, $ctx.Utilisateur, $sortie.Crees.Count, $sortie.Echecs.Count) `
        -Donnees @{ environnement = $Vue.Env.Nom; regle = $Regle; action = 'creation_dossiers'; code = $reponse.Code }
    if ($null -eq $reponse.Json) { $sortie.Erreur = 'Création impossible : ' + (Get-CopieTexteReponse -Reponse $reponse) }
    $sortie.Fait = ($sortie.Crees.Count -gt 0)
    if (-not $SansResultat -and ($sortie.Erreur -or $sortie.Echecs.Count -gt 0)) {
        $lignes = @(New-CopieLignesCreation -Resultat $sortie)
        Show-CopieResultat -Contexte $ctx -Titre 'Créer les dossiers manquants' -Resume (Get-CopieResumeResultat -Ligne $lignes) -Ligne $lignes
    }
    $sortie
}

function New-CopieLignesCreation {
    <#
    .SYNOPSIS
        Résultat d'une création de dossiers (Invoke-CopieCreationDossiersRegle) -> lignes de la fenêtre de résultat.
    .PARAMETER Resultat
        Sortie de Invoke-CopieCreationDossiersRegle (Crees, Echecs, Erreur).
    .OUTPUTS
        [pscustomobject[]]
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Resultat)
    foreach ($c in @($Resultat.Crees)) { New-CopieLigneResultat -Gravite 'Information' -Sujet 'Dossier créé' -Message ('{0} : {1}' -f (Get-CopieValeur $c 'role' ''), (Get-CopieValeur $c 'chemin' '')) }
    foreach ($e in @($Resultat.Echecs)) { New-CopieLigneResultat -Gravite 'Erreur' -Sujet 'Création impossible' -Message ('{0} : {1}' -f (Get-CopieValeur $e 'chemin' ''), (Get-CopieValeur $e 'erreur' '')) }
    if ($Resultat.Erreur) { New-CopieLigneResultat -Gravite 'Erreur' -Sujet 'Création impossible' -Message $Resultat.Erreur }
}

function Get-CopieCompteControle {
    <#
    .SYNOPSIS
        Compte avec lequel le moteur contrôle les accès (ses droits sont ceux du moteur, pas forcément les vôtres).
    .PARAMETER Contexte
        Contexte de la session.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [hashtable] $Contexte)
    $m = $Contexte.Config.Moteur
    if ($m.ConfigurationJea) { return 'le compte de service du point d''accès JEA' }
    if ($m.Mode -eq 'Distant') { return ('votre compte ({0}) sur le serveur {1}' -f $Contexte.Utilisateur, $m.Serveur) }
    'votre compte ({0})' -f $Contexte.Utilisateur
}

function Invoke-CopieControleRegle {
    <#
    .SYNOPSIS
        Après l'enregistrement d'une règle : contrôle ses répertoires (existence, lecture, écriture, espace) et propose de créer les absents.

    .DESCRIPTION
        Appel court du moteur (--controler-regle : pas de base, rien n'est livré). Les droits vérifiés sont ceux du
        compte qui exécute le moteur. Une seule question Oui / Non (créer les dossiers absents) ; tout le reste, soit
        l'enregistrement, les créations, les répertoires en bon état, les avertissements et les erreurs, est rassemblé
        dans UNE fenêtre de résultat. Le contrôle n'empêche pas l'enregistrement : la règle est déjà enregistrée.

    .PARAMETER Vue
        Vue d'un environnement.

    .PARAMETER Id
        Règle à contrôler.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue, [Parameter(Mandatory)] [string] $Id)
    $ctx = $Vue.Contexte
    $compte = Get-CopieCompteControle -Contexte $ctx
    $titre = 'Contrôle des répertoires'
    $debut = ('Règle « {0} » enregistrée.' -f $Id)
    $faits = New-Object System.Collections.Generic.List[object]          # enregistrement, créations
    $faits.Add((New-CopieLigneResultat -Gravite 'Information' -Sujet 'Enregistrement' -Message ('La règle « {0} » est enregistrée dans {1}.' -f $Id, $Vue.Env.Nom)))
    for ($tour = 0; $tour -lt 2; $tour++) {
        $ctx.Fenetre.Cursor = [System.Windows.Input.Cursors]::Wait
        try { $reponse = Invoke-CopieMoteur -Config $ctx.Config -Fichier $Vue.Env.Fichier -Argument @('--controler-regle', $Id) }
        finally { $ctx.Fenetre.Cursor = $null }
        if ($null -eq $reponse.Json -or $null -eq $reponse.Json.PSObject.Properties['controles']) {
            $faits.Add((New-CopieLigneResultat -Gravite 'Avertissement' -Sujet $titre -Message ('Le contrôle des répertoires n''a pas pu être fait : ' + (Get-CopieTexteReponse -Reponse $reponse))))
            Show-CopieResultat -Contexte $ctx -Titre $titre -Resume (Get-CopieResumeResultat -Ligne $faits.ToArray() -Debut $debut) -Ligne $faits.ToArray()
            return
        }
        $controles = @(ConvertTo-CopieControleSimulation -Controle @($reponse.Json.controles))
        $problemes = @($controles | Where-Object { $_.Verdict -eq 'PROBLEME' })
        $manquants = @($controles | Where-Object { $_.Verdict -eq 'A_CREER' })
        Write-CopieJournal -Contexte $ctx -Niveau $(if ($problemes.Count -gt 0) { 'WARNING' } else { 'INFO' }) -Evenement 'controle_repertoires' `
            -Message ('Contrôle des répertoires de {0} dans {1} : {2} problème(s), {3} dossier(s) à créer' -f $Id, $Vue.Env.Nom, $problemes.Count, $manquants.Count) `
            -Donnees @{ environnement = $Vue.Env.Nom; regle = $Id; problemes = $problemes.Count; a_creer = $manquants.Count }
        if ($ctx.Profil -eq 'Admin' -and $manquants.Count -gt 0 -and $tour -eq 0) {
            # La seule question : l'accord pour créer. Elle liste les dossiers (et les problèmes déjà vus) pour qu'on réponde en connaissance de cause.
            $texte = New-Object System.Collections.Generic.List[string]
            $texte.Add(("Règle « {0} » enregistrée. Contrôle des répertoires avec {1} :" -f $Id, $compte))
            foreach ($l in $problemes) { $texte.Add(('- PROBLÈME, {0} ({1}) : existe {2}, lecture {3}, écriture {4}. {5}' -f $l.Role, $l.Chemin, $l.Existe, $l.Lecture, $l.Ecriture, $l.Remarque)) }
            foreach ($l in $manquants) { $texte.Add(('- À CRÉER, {0} ({1}) : le dossier n''existe pas ; il peut être créé avec ce compte.' -f $l.Role, $l.Chemin)) }
            $texte.Add('')
            $texte.Add('Créer maintenant les dossiers manquants ?')
            $r = [System.Windows.MessageBox]::Show($ctx.Fenetre, ($texte -join "`n"), $titre, 'YesNo', $(if ($problemes.Count -gt 0) { 'Warning' } else { 'Question' }))
            if ($r -eq [System.Windows.MessageBoxResult]::Yes) {
                $c = Invoke-CopieCreationDossiersRegle -Vue $Vue -Regle $Id -Dossier $manquants -SansQuestion -SansResultat
                foreach ($ligne in @(New-CopieLignesCreation -Resultat $c)) { $faits.Add($ligne) }
                if ($c.Fait) { continue }                 # on recontrôle pour montrer l'état final
            }
            else { $faits.Add((New-CopieLigneResultat -Gravite 'Avertissement' -Sujet 'Création' -Message 'Création des dossiers manquants refusée : la règle ne pourra pas fonctionner tant qu''ils n''existent pas.')) }
        }
        $lignes = @($faits.ToArray()) + @(ConvertTo-CopieLignesResultatControle -Controle $controles)
        $debutFinal = ('{0} Répertoires contrôlés avec {1}.' -f $debut, $compte)
        $texteAide = $null
        if ($problemes.Count -gt 0 -or $manquants.Count -gt 0) { $texteAide = 'Corrigez la règle (Modifier) ou les droits, puis relancez « Simuler la règle ».' }
        if ($texteAide) { $lignes += @(New-CopieLigneResultat -Gravite 'Information' -Sujet 'À faire' -Message $texteAide) }
        Show-CopieResultat -Contexte $ctx -Titre $titre -Resume (Get-CopieResumeResultat -Ligne $lignes -Debut $debutFinal) -Ligne $lignes
        return
    }
}

function Invoke-CopieSimulation {
    <#
    .SYNOPSIS
        Simule la règle choisie (--lancer-regle ID --simulation, en arrière-plan) et affiche ce qui serait traité.
    .PARAMETER Vue
        Vue d'un environnement.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)
    $ctx = $Vue.Contexte
    $choisie = $Vue.Grille.SelectedItem
    if ($null -eq $choisie -or $Vue.Occupe) { return }
    Set-CopieOccupe -Vue $Vue -Occupe $true -Libelle ('Simulation de la règle {0}' -f $choisie.Id)
    $null = Start-CopieTache -Config $ctx.Config -Fichier $Vue.Env.Fichier -Argument @('--lancer-regle', $choisie.Id, '--simulation') `
        -SurFin { param($t) Complete-CopieSimulation -Tache $t } -Donnees @{ Vue = $Vue; Contexte = $ctx; Regle = $choisie.Id }
}

function Complete-CopieSimulation {
    <#
    .SYNOPSIS
        Fin de la simulation (arrière-plan) : journal, puis résultat ou message du moteur (règle inactive, base absente...).
    .PARAMETER Tache
        Tâche terminée (Donnees : Vue, Contexte, Regle).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Tache)
    $vue = $Tache.Donnees.Vue
    $ctx = $Tache.Donnees.Contexte
    $regle = $Tache.Donnees.Regle
    $reponse = $Tache.Reponse
    Set-CopieOccupe -Vue $vue -Occupe $false
    $detaille = ($null -ne $reponse.Json -and $null -ne $reponse.Json.PSObject.Properties['compteurs'])
    Write-CopieJournal -Contexte $ctx -Niveau $(if ($detaille) { 'INFO' } else { 'WARNING' }) -Evenement 'simulation' `
        -Message ('Simulation de {0} dans {1} (compte {2}) : code {3}' -f $regle, $vue.Env.Nom, $ctx.Utilisateur, $reponse.Code) `
        -Donnees @{ environnement = $vue.Env.Nom; regle = $regle; code = $reponse.Code }
    if (-not $detaille) {
        $message = Get-CopieTexteReponse -Reponse $reponse
        [void][System.Windows.MessageBox]::Show($ctx.Fenetre, ('Simulation impossible : ' + $message), 'Simulation', 'OK', 'Warning')
        return
    }
    $resume = ConvertTo-CopieResumeSimulation -Json $reponse.Json
    $creer = Show-CopieSimulation -Contexte $ctx -Regle $regle -Resume $resume
    # Création demandée : on crée, puis on relance la simulation pour montrer le nouveau résultat.
    if ($creer -and (Invoke-CopieCreationDossiersRegle -Vue $vue -Regle $regle -Dossier @($resume.ACreer)).Fait) {
        if ($Script:Vues.ContainsKey($vue.Cle)) { Invoke-CopieSimulation -Vue $vue }
    }
}
