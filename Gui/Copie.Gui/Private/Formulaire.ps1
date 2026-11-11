$Script:JoursSemaine = @('lun', 'mar', 'mer', 'jeu', 'ven', 'sam', 'dim')
$Script:UnitesDuree = @(
    [pscustomobject]@{ Nom = 'secondes'; Secondes = 1 }
    [pscustomobject]@{ Nom = 'minutes'; Secondes = 60 }
    [pscustomobject]@{ Nom = 'heures'; Secondes = 3600 }
    [pscustomobject]@{ Nom = 'jours'; Secondes = 86400 }
)

function ConvertFrom-CopieJours {
    <#
    .SYNOPSIS
        Texte de jours du fichier (« tous », « lun-ven », « lun,mer,ven ») -> les jours cochés.
    .DESCRIPTION
        Le moteur reste juge de la validité ; ici on ne fait que lire pour afficher. Un texte
        incompréhensible renvoie $null (le formulaire affiche alors tous les jours cochés et le signale).
    .PARAMETER Texte
        Texte de la planification.
    .OUTPUTS
        [string[]] jours cochés (abréviations), ou $null si le texte n'est pas compris.
    #>
    [CmdletBinding()]
    param([AllowNull()] [string] $Texte)
    $jours = $Script:JoursSemaine
    if ([string]::IsNullOrWhiteSpace($Texte)) { return $jours }
    $coches = New-Object System.Collections.Generic.List[string]
    foreach ($jeton in ($Texte.Trim().ToLowerInvariant() -split ',')) {
        $jeton = $jeton.Trim()
        if ($jeton -eq 'tous') { return $jours }
        if ($jeton -match '^([a-z]{3})-([a-z]{3})$') {
            $a = [array]::IndexOf($jours, $Matches[1]); $b = [array]::IndexOf($jours, $Matches[2])
            if ($a -lt 0 -or $b -lt 0) { return $null }
            $i = $a
            while ($true) {
                if (-not $coches.Contains($jours[$i])) { $coches.Add($jours[$i]) }
                if ($i -eq $b) { break }
                $i = ($i + 1) % 7
            }
        }
        elseif ($jours -contains $jeton) { if (-not $coches.Contains($jeton)) { $coches.Add($jeton) } }
        else { return $null }
    }
    @($jours | Where-Object { $coches.Contains($_) })
}

function ConvertTo-CopieJours {
    <#
    .SYNOPSIS
        Jours cochés -> texte du fichier : « tous », « lun-ven », « lun,mer,ven ».
    .PARAMETER Jour
        Abréviations des jours cochés.
    .OUTPUTS
        [string] ; $null si aucun jour n'est coché (invalide).
    #>
    [CmdletBinding()]
    param([AllowEmptyCollection()] [string[]] $Jour)
    $jours = $Script:JoursSemaine
    $ordre = @($jours | Where-Object { $Jour -contains $_ })
    if ($ordre.Count -eq 0) { return $null }
    if ($ordre.Count -eq 7) { return 'tous' }
    $indices = @($ordre | ForEach-Object { [array]::IndexOf($jours, $_) })
    if ($ordre.Count -ge 3 -and ($indices[-1] - $indices[0]) -eq ($ordre.Count - 1)) { return ('{0}-{1}' -f $ordre[0], $ordre[-1]) }
    $ordre -join ','
}

function ConvertTo-CopieDureeAffichage {
    <#
    .SYNOPSIS
        Secondes -> valeur et unité d'affichage (la plus grande unité qui divise exactement).
    .PARAMETER Secondes
        Durée en secondes, ou $null.
    .OUTPUTS
        [pscustomobject] Valeur (texte), Unite (secondes|minutes|heures|jours).
    #>
    [CmdletBinding()]
    param([AllowNull()] $Secondes)
    if ($null -eq $Secondes -or "$Secondes" -eq '') { return [pscustomobject]@{ Valeur = ''; Unite = 'secondes' } }
    $n = [long]$Secondes
    $choix = $Script:UnitesDuree[0]
    if ($n -gt 0) { foreach ($u in $Script:UnitesDuree) { if ($n % $u.Secondes -eq 0) { $choix = $u } } }
    [pscustomobject]@{ Valeur = ('{0}' -f ($n / $choix.Secondes)); Unite = $choix.Nom }
}

function ConvertFrom-CopieDureeAffichage {
    <#
    .SYNOPSIS
        Valeur saisie et unité -> secondes entières ; erreur claire sinon.
    .PARAMETER Valeur
        Nombre saisi (entier positif ou nul).
    .PARAMETER Unite
        secondes, minutes, heures ou jours.
    .OUTPUTS
        [pscustomobject] Ok, Secondes, Erreur.
    #>
    [CmdletBinding()]
    param([string] $Valeur, [string] $Unite)
    $choix = $Script:UnitesDuree | Where-Object { $_.Nom -eq $Unite } | Select-Object -First 1
    if ($null -eq $choix) { $choix = $Script:UnitesDuree[0] }
    $n = 0L
    if (-not [long]::TryParse($Valeur.Trim(), [System.Globalization.NumberStyles]::None, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$n)) {
        return [pscustomobject]@{ Ok = $false; Secondes = $null; Erreur = 'un nombre entier positif est attendu' }
    }
    [pscustomobject]@{ Ok = $true; Secondes = ($n * $choix.Secondes); Erreur = $null }
}

function Get-CopieValeurChemin {
    <#
    .SYNOPSIS
        Valeur d'un chemin à points (« selection.masque ») dans une règle.
    .PARAMETER Objet
        Règle.
    .PARAMETER Chemin
        Chemin à points.
    #>
    [CmdletBinding()]
    param([AllowNull()] $Objet, [Parameter(Mandatory)] [string] $Chemin)
    $courant = $Objet
    foreach ($nom in $Chemin.Split('.')) {
        if ($null -eq $courant) { return $null }
        $courant = Get-CopieValeur $courant $nom $null
    }
    $courant
}

function Set-CopieValeurChemin {
    <#
    .SYNOPSIS
        Écrit une valeur à un chemin à points dans une règle (les niveaux intermédiaires existent déjà).
    .PARAMETER Objet
        Règle.
    .PARAMETER Chemin
        Chemin à points.
    .PARAMETER Valeur
        Valeur à écrire.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Objet, [Parameter(Mandatory)] [string] $Chemin, [AllowNull()] $Valeur)
    $noms = $Chemin.Split('.')
    $courant = $Objet
    for ($i = 0; $i -lt $noms.Count - 1; $i++) { $courant = $courant.PSObject.Properties[$noms[$i]].Value }
    $propriete = $courant.PSObject.Properties[$noms[-1]]
    if ($null -eq $propriete) { Add-Member -InputObject $courant -NotePropertyName $noms[-1] -NotePropertyValue $Valeur }
    else { $propriete.Value = $Valeur }
}

function Get-CopieChampsRegle {
    <#
    .SYNOPSIS
        Description des onglets « simples » du formulaire de règle : champs, types, listes.

    .DESCRIPTION
        Les valeurs de secours et les listes viennent du moteur ; ici on ne décrit que la présentation
        (libellé, type de contrôle, aide). Les onglets Planification, Situations et Programmes sont
        construits à part. Types : texte, entier, duree, bool, choix, lignes, cases (plusieurs choix cumulables).

    .OUTPUTS
        Liste d'onglets : Titre, Champs (Chemin, Libelle, Type, Liste, Obligatoire, Aide).
    #>
    [CmdletBinding()]
    param()
    function champ($chemin, $libelle, $type, $liste = $null, $obligatoire = $false, $aide = '') {
        [pscustomobject]@{ Chemin = $chemin; Libelle = $libelle; Type = $type; Liste = $liste; Obligatoire = $obligatoire; Aide = $aide }
    }
    @(
        [pscustomobject]@{ Titre = 'Général'; Champs = @(
                (champ 'id' 'Identifiant' 'texte' $null $true 'Lettres, chiffres, _ et -, 64 caractères au plus. Ne se modifie plus une fois la règle créée.')
                (champ 'description' 'Description' 'texte')
                (champ 'actif' 'Règle active' 'bool' $null $false 'Une règle inactive n''est jamais lancée.')
                (champ 'mode' 'Mode' 'choix' 'modes' $true 'copie, deplacement, archivage : transfèrent vers la cible. suppression : SUPPRIME DÉFINITIVEMENT les fichiers sélectionnés (avertissement à l''enregistrement). count / size : comptent ou mesurent les fichiers sélectionnés et les comparent aux seuils, sans rien toucher.')
                (champ 'source' 'Dossier source' 'texte' $null $true 'Chemin complet, ou partiel : il se place alors sous la racine des sources de l''environnement.')
                (champ 'cible' 'Dossier cible' 'texte' $null $false 'Chemin complet, ou partiel (racine des cibles de l''environnement). Obligatoire pour copie, deplacement et archivage ; sans objet pour suppression, count et size.')
                (champ 'archive' 'Dossier d''archive' 'texte' $null $false 'Vide : pas d''archivage. Relatif, il se calcule depuis la source.')
                (champ 'seuil_minimum' 'Seuil minimum (count, size)' 'entier' $null $false 'count : nombre de fichiers ; size : octets. La règle sort en ATTENTE (ni succès ni erreur) tant que la valeur est en dessous : les règles qui en dépendent patientent.')
                (champ 'seuil_maximum' 'Seuil maximum (count, size)' 'entier' $null $false 'Même unité. Vide : pas de maximum.')
                (champ 'creer_dossiers' 'Créer les dossiers manquants' 'bool')
                (champ 'dossier_temporaire' 'Dossier temporaire' 'texte' $null $false 'Vide : le moteur choisit.')
                (champ 'identite' 'Identité d''un fichier' 'choix' 'identites')
            )
        }
        [pscustomobject]@{ Titre = 'Sélection'; Champs = @(
                (champ 'selection.masque' 'Masque(s)' 'texte' $null $false 'Exemple : *.csv')
                (champ 'selection.exclure' 'Exclure' 'texte' $null $false 'Masque(s) à écarter.')
                (champ 'selection.recursif' 'Parcourir les sous-dossiers' 'bool')
                (champ 'selection.modifie_depuis' 'Modifié depuis' 'texte' $null $false 'TOUT, J (aujourd''hui) ou J-N (les N derniers jours).')
                (champ 'selection.age_minimum_sec' 'Âge minimum du fichier' 'duree' $null $false 'Évite de prendre un fichier encore en cours d''écriture.')
                (champ 'selection.age_maximum_sec' 'Âge maximum du fichier' 'duree')
                (champ 'selection.taille_minimum_octets' 'Taille minimum (octets)' 'entier')
                (champ 'selection.ordre' 'Ordre de traitement' 'choix' 'ordres')
                (champ 'selection.limite_fichiers' 'Nombre maximum de fichiers par lot' 'entier' $null $false 'Vide : pas de limite.')
            )
        }
        [pscustomobject]@{ Titre = 'Anti-doublon et nommage'; Champs = @(
                (champ 'si_cible_absente' 'Si la cible est absente' 'choix' 'si_cible_absente')
                (champ 'si_existe_cible' 'Si le fichier existe déjà dans la cible' 'choix' 'si_existe_cible')
                (champ 'si_existe_archive' 'Si le fichier existe déjà dans l''archive' 'choix' 'si_existe_archive')
                (champ 'renommage_cible' 'Renommage dans la cible' 'texte' $null $false 'Variables : voir la liste du moteur ci-dessous. Vide : nom d''origine.')
                (champ 'renommage_archive' 'Renommage dans l''archive' 'texte')
            )
        }
        [pscustomobject]@{ Titre = 'Dépendances'; Champs = @(
                (champ 'apres' 'Se lance après (une règle par ligne)' 'lignes' $null $false 'Identifiants de règles du même fichier ; elles seront rangées avant celle-ci.')
                (champ 'condition' 'Conditions (cumulables)' 'cases' 'conditions' $false 'termine : la règle amont a fini, quel qu''en soit le résultat. succes : finie sans erreur (une règle count ou size en ATTENTE n''est pas un succès). fichiers : a livré au moins un fichier.')
                (champ 'si_condition_non_remplie' 'Si la condition n''est pas remplie' 'choix' 'niveaux')
            )
        }
        [pscustomobject]@{ Titre = 'Durée et erreurs'; Champs = @(
                (champ 'duree_max_sec' 'Durée maximale d''une exécution' 'duree' $null $false 'Au-delà, voir la ligne suivante.')
                (champ 'si_duree_depassee' 'Si la durée est dépassée' 'choix' 'si_duree_depassee')
                (champ 'relances_max' 'Relances maximum' 'entier')
                (champ 'apres_erreur' 'Après une erreur' 'choix' 'apres_erreur')
            )
        }
        [pscustomobject]@{ Titre = 'Purge'; Champs = @(
                (champ 'retention_historique_jours' 'Conservation de l''historique (jours)' 'entier' $null $false 'Vide : valeur du moteur.')
                (champ 'retention_journaux_jours' 'Conservation des journaux (jours)' 'entier')
                (champ 'retention_archive_jours' 'Conservation des archives (jours)' 'entier')
            )
        }
    )
}
