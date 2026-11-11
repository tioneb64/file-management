function Format-CopieTexte {
    <#
    .SYNOPSIS
        Valeur d'un champ -> texte d'affichage (booléen Oui/Non, liste séparée par des virgules, absent = « — »).
    .PARAMETER Valeur
        Valeur issue du JSON.
    .PARAMETER Defaut
        Texte affiché quand la valeur est absente du fichier (par défaut : « défaut du moteur »).
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [AllowNull()] $Valeur,
        [string] $Defaut = 'défaut du moteur'
    )
    if ($null -eq $Valeur) { return $Defaut }
    if ($Valeur -is [bool]) { return $(if ($Valeur) { 'Oui' } else { 'Non' }) }
    if ($Valeur -is [System.Array]) {
        if ($Valeur.Count -eq 0) { return [string][char]0x2014 }
        return (($Valeur | ForEach-Object { "$_" }) -join ', ')
    }
    "$Valeur"
}

function New-CopieLigne {
    param([string] $Libelle, [string] $Valeur)
    [pscustomobject]@{ Libelle = $Libelle; Valeur = $Valeur }
}

function ConvertTo-CopieLigneRegle {
    <#
    .SYNOPSIS
        Ligne de la grille des règles : champs du fichier + état renvoyé par le moteur (--etat).

    .PARAMETER Regle
        Règle lue dans le fichier (Read-CopieFichierParametrage).

    .PARAMETER Etat
        Entrée de la règle dans la réponse de --etat, ou $null (base non initialisée, moteur injoignable).

    .PARAMETER Entete
        En-tête du fichier : ses racines complètent les chemins partiels (Chemins affiche les chemins complets).

    .OUTPUTS
        [pscustomobject] Copie.LigneRegle.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)] $Regle,
        [AllowNull()] $Etat,
        [AllowNull()] $Entete = $null
    )
    $actif = Get-CopieValeur $Regle 'actif' $true
    if ($null -ne $Etat) {
        $statut = "$(Get-CopieValeur $Etat 'statut' '')"
        $planification = "$(Get-CopieValeur $Etat 'planification' '')"
    }
    else {
        $statut = $(if ($actif) { '' } else { 'INACTIVE' })
        $planification = Format-CopiePlanification -Planification (Get-CopieValeur $Regle 'planification')
    }
    $chemins = Get-CopieCheminsRegle -Regle $Regle -Entete $Entete
    $mode = "$(Get-CopieValeur $Regle 'mode' '')"
    $transfert = (@(Get-CopieModesRegle | Where-Object { $_.Nom -eq $mode -and -not $_.Transfert }).Count -eq 0)
    $affichageChemins = $(if ($transfert) { '{0}  {1}  {2}' -f $chemins.Source, [char]0x2192, $chemins.Cible } else { $chemins.Source })
    $enCours = [bool](Get-CopieValeur $Etat 'en_cours' $false)
    $attente = "$(Get-CopieValeur $Etat 'attente' '')"
    # Aspect de la ligne dans la grille : inactive (grise) prime sur erreur (rouge).
    $aspect = $(if (-not $actif) { 'inactive' } elseif ($statut -in 'ERREUR', 'ARRETEE' -or $attente -eq 'BLOQUEE') { 'erreur' } else { '' })
    [pscustomobject]@{
        PSTypeName     = 'Copie.LigneRegle'
        Id             = "$(Get-CopieValeur $Regle 'id' '')"
        Description    = "$(Get-CopieValeur $Regle 'description' '')"
        Mode           = $mode
        Chemins        = $affichageChemins
        EnCours        = $enCours
        Attente        = $attente
        Aspect         = $aspect
        Planification  = $planification
        Actif          = $(if ($actif) { 'Oui' } else { 'Non' })
        Statut         = $(if ($statut) { $statut } else { [string][char]0x2014 })
        StatutCouleur  = (Get-CopieCouleurStatut -Statut $statut)
        Motif          = "$(Get-CopieValeur $Etat 'motif' '')"
        DernierLancement = $(if ($null -ne $Etat) { Format-CopieDate (Get-CopieValeur $Etat 'dernier_lancement') } else { [string][char]0x2014 })
        ProchainCreneau  = $(if ($null -ne $Etat) { Format-CopieDate (Get-CopieValeur $Etat 'prochain_creneau') } else { [string][char]0x2014 })
        Regle          = $Regle
        Etat           = $Etat
    }
}

function ConvertTo-CopieGroupeRegle {
    <#
    .SYNOPSIS
        Détail d'une règle, regroupé en cartes (identification, chemins, sélection, planification...).
    .DESCRIPTION
        Lecture seule. Un champ absent du fichier est affiché « défaut du moteur » : l'interface ne
        répète pas les valeurs de secours du moteur (une seule source de vérité : docs/01 §6).
    .PARAMETER Regle
        Règle lue dans le fichier.
    .PARAMETER Entete
        En-tête du fichier : ses racines complètent les chemins partiels (le détail montre les chemins complets).
    .OUTPUTS
        [pscustomobject[]] Titre, Lignes (Libelle, Valeur).
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject[]])]
    param([Parameter(Mandatory)] $Regle, [AllowNull()] $Entete = $null)

    $chemins = Get-CopieCheminsRegle -Regle $Regle -Entete $Entete
    $tiretLong = [string][char]0x2014
    # Chemin complet ; quand il diffère de ce qui est écrit dans le fichier, la saisie d'origine est rappelée.
    $complet = {
        param($resolu, $nom, $defaut)
        $saisi = "$(Get-CopieValeur $Regle $nom '')".Trim()
        if (-not $saisi) { return $defaut }
        if ($resolu -ceq $saisi) { return $resolu }
        '{0}   (saisi : {1})' -f $resolu, $saisi
    }

    $v = { param($objet, $nom) Format-CopieTexte (Get-CopieValeur $objet $nom) }
    $sel = Get-CopieValeur $Regle 'selection'
    $groupes = New-Object System.Collections.Generic.List[object]
    $ajouter = { param($titre, $lignes) $groupes.Add([pscustomobject]@{ Titre = $titre; Lignes = @($lignes) }) }

    & $ajouter 'Identification' @(
        (New-CopieLigne 'Identifiant' (& $v $Regle 'id')),
        (New-CopieLigne 'Description' (Format-CopieTexte (Get-CopieValeur $Regle 'description') ([string][char]0x2014))),
        (New-CopieLigne 'Active' (& $v $Regle 'actif')),
        (New-CopieLigne 'Ligne du fichier' (& $v $Regle 'Ligne')))
    & $ajouter 'Source, cible, mode' @(
        (New-CopieLigne 'Mode' (& $v $Regle 'mode')),
        (New-CopieLigne 'Source' (& $complet $chemins.Source 'source' 'défaut du moteur')),
        (New-CopieLigne 'Cible' (& $complet $chemins.Cible 'cible' $tiretLong)),
        (New-CopieLigne 'Seuil minimum (count : fichiers, size : octets)' (Format-CopieTexte (Get-CopieValeur $Regle 'seuil_minimum') $tiretLong)),
        (New-CopieLigne 'Seuil maximum (count : fichiers, size : octets)' (Format-CopieTexte (Get-CopieValeur $Regle 'seuil_maximum') $tiretLong)),
        (New-CopieLigne 'Archive' (Format-CopieTexte (Get-CopieValeur $Regle 'archive') ([string][char]0x2014))),
        (New-CopieLigne 'Créer les dossiers' (& $v $Regle 'creer_dossiers')),
        (New-CopieLigne 'Dossier temporaire' $(if ("$(Get-CopieValeur $Regle 'dossier_temporaire' '')".Trim()) { & $complet $chemins.DossierTemporaire 'dossier_temporaire' '' } else { 'dans la cible' })))
    & $ajouter 'Sélection' @(
        (New-CopieLigne 'Masque' (& $v $sel 'masque')),
        (New-CopieLigne 'Exclure' (Format-CopieTexte (Get-CopieValeur $sel 'exclure') ([string][char]0x2014))),
        (New-CopieLigne 'Sous-dossiers' (& $v $sel 'recursif')),
        (New-CopieLigne 'Modifiés depuis' (& $v $sel 'modifie_depuis')),
        (New-CopieLigne 'Âge minimum (s)' (Format-CopieTexte (Get-CopieValeur $sel 'age_minimum_sec') ([string][char]0x2014))),
        (New-CopieLigne 'Âge maximum (s)' (Format-CopieTexte (Get-CopieValeur $sel 'age_maximum_sec') ([string][char]0x2014))),
        (New-CopieLigne 'Taille minimum (octets)' (Format-CopieTexte (Get-CopieValeur $sel 'taille_minimum_octets') ([string][char]0x2014))),
        (New-CopieLigne 'Ordre' (& $v $sel 'ordre')),
        (New-CopieLigne 'Limite de fichiers' (Format-CopieTexte (Get-CopieValeur $sel 'limite_fichiers') 'aucune')))
    & $ajouter 'Anti-doublon et nommage' @(
        (New-CopieLigne 'Identité' (& $v $Regle 'identite')),
        (New-CopieLigne 'Historique conservé (jours)' (& $v $Regle 'retention_historique_jours')),
        (New-CopieLigne 'Si la cible a perdu le fichier' (& $v $Regle 'si_cible_absente')),
        (New-CopieLigne 'Si le fichier existe dans la cible' (& $v $Regle 'si_existe_cible')),
        (New-CopieLigne 'Si le fichier existe dans l''archive' (& $v $Regle 'si_existe_archive')),
        (New-CopieLigne 'Nom dans la cible' (Format-CopieTexte (Get-CopieValeur $Regle 'renommage_cible') 'nom conservé')),
        (New-CopieLigne 'Nom dans l''archive' (Format-CopieTexte (Get-CopieValeur $Regle 'renommage_archive') 'nom conservé')))
    & $ajouter 'Planification' @(
        (New-CopieLigne 'En clair' (Format-CopiePlanification -Planification (Get-CopieValeur $Regle 'planification'))),
        (New-CopieLigne 'Type' (Format-CopieTexte (Get-CopieValeur (Get-CopieValeur $Regle 'planification') 'type') ([string][char]0x2014))),
        (New-CopieLigne 'Rattrapage (s)' (Format-CopieTexte (Get-CopieValeur (Get-CopieValeur $Regle 'planification') 'rattrapage_sec') 'aucun')))
    & $ajouter 'Dépendances' @(
        (New-CopieLigne 'Après' (Format-CopieTexte (Get-CopieValeur $Regle 'apres') 'aucune')),
        (New-CopieLigne 'Condition' (& $v $Regle 'condition')),
        (New-CopieLigne 'Si la condition n''est pas remplie' (& $v $Regle 'si_condition_non_remplie')))
    & $ajouter 'Durée, erreurs, reprise' @(
        (New-CopieLigne 'Durée maximale (s)' (& $v $Regle 'duree_max_sec')),
        (New-CopieLigne 'Si la durée est dépassée' (& $v $Regle 'si_duree_depassee')),
        (New-CopieLigne 'Relances maximum' (& $v $Regle 'relances_max')),
        (New-CopieLigne 'Après une erreur' (& $v $Regle 'apres_erreur')))

    $situations = Get-CopieValeur $Regle 'situations'
    $lignesSituations = @()
    if ($null -ne $situations) {
        foreach ($p in $situations.PSObject.Properties) {
            $s = $p.Value
            $suite = Get-CopieValeur $s 'suite'
            $texte = '{0} essai(s), délai {1} s, puis {2}' -f (Get-CopieValeur $s 'tentatives' '?'), (Get-CopieValeur $s 'delai_sec' '?'), (Get-CopieValeur $s 'niveau_final' '?')
            if ($suite) { $texte += ' (' + $suite + ')' }
            $lignesSituations += New-CopieLigne $p.Name $texte
        }
    }
    if ($lignesSituations.Count -eq 0) { $lignesSituations = @(New-CopieLigne 'Situations' 'toutes aux réactions par défaut du moteur') }
    & $ajouter 'Situations et réactions' $lignesSituations

    $programmes = Get-CopieValeur $Regle 'programmes'
    $lignesProgrammes = @()
    foreach ($point in 'avant_lot', 'avant_fichier', 'apres_fichier', 'apres_lot', 'sur_erreur', 'reprise') {
        $appel = Get-CopieValeur $programmes $point
        $texte = $(if ($null -eq $appel) { [string][char]0x2014 } else { (Format-CopieTexte (Get-CopieValeur $appel 'commande') '?') + '   (délai ' + (Get-CopieValeur $appel 'timeout_sec' '?') + ' s)' })
        $lignesProgrammes += New-CopieLigne $point $texte
    }
    & $ajouter 'Programmes externes (exécutés par le compte de service)' $lignesProgrammes

    & $ajouter 'Purge' @(
        (New-CopieLigne 'Journaux conservés (jours)' (Format-CopieTexte (Get-CopieValeur $Regle 'retention_journaux_jours') 'valeur de l''en-tête')),
        (New-CopieLigne 'Archive conservée (jours)' (Format-CopieTexte (Get-CopieValeur $Regle 'retention_archive_jours') 'jamais purgée')))
    , $groupes.ToArray()
}

function ConvertTo-CopieGroupeEtat {
    <#
    .SYNOPSIS
        État d'une règle (entrée de --etat) regroupé en cartes.
    .PARAMETER Etat
        Entrée de la règle dans la réponse de --etat, ou $null.
    .OUTPUTS
        [pscustomobject[]] Titre, Lignes (Libelle, Valeur).
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject[]])]
    param([AllowNull()] $Etat)

    if ($null -eq $Etat) {
        return , @([pscustomobject]@{ Titre = 'État'; Lignes = @(New-CopieLigne 'État' 'indisponible : base non initialisée ou moteur injoignable (voir le journal)') })
    }
    $tiret = [string][char]0x2014
    $t = { param($nom, $defaut) Format-CopieTexte (Get-CopieValeur $Etat $nom) $defaut }
    $exec = Get-CopieValeur $Etat 'derniere_execution'
    $err = Get-CopieValeur $Etat 'derniere_erreur'
    $groupes = @(
        [pscustomobject]@{ Titre = 'Résumé'; Lignes = @(
                (New-CopieLigne 'Statut' (& $t 'statut' $tiret)),
                (New-CopieLigne 'Motif' (& $t 'motif' $tiret)),
                (New-CopieLigne 'Attente' (& $t 'attente' $tiret)),
                (New-CopieLigne 'Dernier lancement' (Format-CopieDate (Get-CopieValeur $Etat 'dernier_lancement'))),
                (New-CopieLigne 'Dernier créneau' (Format-CopieDate (Get-CopieValeur $Etat 'dernier_creneau'))),
                (New-CopieLigne 'Prochain créneau' (Format-CopieDate (Get-CopieValeur $Etat 'prochain_creneau'))),
                (New-CopieLigne 'Dernier succès' (Format-CopieDate (Get-CopieValeur $Etat 'dernier_succes')))) },
        [pscustomobject]@{ Titre = 'Dernière exécution'; Lignes = @(
                (New-CopieLigne 'Statut' (Format-CopieTexte (Get-CopieValeur $exec 'statut') $tiret)),
                (New-CopieLigne 'Fichiers livrés' (Format-CopieTexte (Get-CopieValeur $exec 'nb_livres') $tiret)),
                (New-CopieLigne 'Erreurs' (Format-CopieTexte (Get-CopieValeur $exec 'nb_erreurs') $tiret)),
                (New-CopieLigne 'Déclencheur' (Format-CopieTexte (Get-CopieValeur $exec 'declencheur') $tiret)),
                (New-CopieLigne 'Durée (s)' (Format-CopieTexte (Get-CopieValeur $exec 'duree_sec') $tiret))) },
        [pscustomobject]@{ Titre = 'Dernière erreur'; Lignes = @(
                (New-CopieLigne 'Quand' (Format-CopieDate (Get-CopieValeur $err 'le'))),
                (New-CopieLigne 'Situation' (Format-CopieTexte (Get-CopieValeur $err 'situation') $tiret)),
                (New-CopieLigne 'Message' (Format-CopieTexte (Get-CopieValeur $err 'message') $tiret))) },
        [pscustomobject]@{ Titre = 'Drapeaux et actions en attente'; Lignes = @(
                (New-CopieLigne 'Reprise demandée' (& $t 'reprise' $tiret)),
                (New-CopieLigne 'Lancement manuel demandé' (& $t 'lancement_manuel' $tiret)),
                (New-CopieLigne 'Arrêtée après erreur' (& $t 'arret_apres_erreur' $tiret)),
                (New-CopieLigne 'Archivage dégradé' (& $t 'archivage_degrade' $tiret)),
                (New-CopieLigne 'Actions en attente' (& $t 'actions_en_attente' $tiret)),
                (New-CopieLigne 'Livraisons incertaines' (& $t 'livraisons_incertaines' $tiret))) }
    )
    , $groupes
}
