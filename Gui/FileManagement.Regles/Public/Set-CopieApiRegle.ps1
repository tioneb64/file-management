function Set-CopieApiRegle {
    <#
    .SYNOPSIS
        Modifie une règle existante : seuls les champs fournis changent, les autres restent tels quels.

    .DESCRIPTION
        Les objets (selection, planification, situations...) sont fusionnés champ par champ ; une liste ou une
        valeur simple est remplacée. Pour passer un champ à « vide », fournir null. La règle est ensuite
        complétée avec le modèle du moteur (un champ ajouté au format par une évolution apparaît avec sa valeur de secours).
        Même garanties que Add-CopieApiRegle, dont le délai minimal d'une planification « unique » (une date non modifiée n'est pas contrôlée).

    .PARAMETER Fichier
        Fichier de paramétrage (parametrage\<env>.jsonl).
    .PARAMETER Id
        Identifiant de la règle à modifier.
    .PARAMETER Modification
        Champs à changer (table de hachage, objet ou texte JSON). Exemple : @{ actif = $false }.
    .PARAMETER Commentaire
        Commentaire tracé avec la version (obligatoire).
    .PARAMETER Appelant
        Nom du programme appelant (tracé).
    .PARAMETER Empreinte
        Empreinte lue avec Get-CopieApiRegle : refuse l'écriture si le fichier a changé depuis.
    .PARAMETER AccepterAvertissements
        Enregistre malgré les avertissements du moteur.
    .PARAMETER Config
        Chemin de Gestion-Copie.config.psd1 (défaut : celui de l'interface).
    .OUTPUTS
        [pscustomobject] Copie.ApiResultat.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)] [string] $Fichier,
        [Parameter(Mandatory)] [string] $Id,
        [Parameter(Mandatory)] $Modification,
        [Parameter(Mandatory)] [string] $Commentaire,
        [string] $Appelant,
        [string] $Empreinte,
        [switch] $AccepterAvertissements,
        [string] $Config
    )
    $patch = ConvertTo-CopieApiObjet -Valeur $Modification
    if ($null -eq $patch) { return New-CopieApiResultat $false 'invalide' 'Modification illisible : un objet JSON est attendu.' }
    $transformer = {
        param($regles, $modele, $a)
        $Id = $a.Id
        $patch = $a.Patch
        $cible = @($regles | Where-Object { "$(Get-CopieValeur $_ 'id' '')".ToLowerInvariant() -eq $Id.ToLowerInvariant() }) | Select-Object -First 1
        if ($null -eq $cible) { return New-CopieApiResultat $false 'introuvable' ('Règle introuvable : ' + $Id) }
        $base = Copy-CopieObjet -Objet $cible
        $base.PSObject.Properties.Remove('Ligne')
        $modifiee = Merge-CopieRegle -Modele $modele -Existante (Merge-CopieApiPatch -Base $base -Patch $patch)
        $tropProche = Test-CopieApiDelai -Regle $modifiee -Initiale $cible -Argument $a
        if ($null -ne $tropProche) { return $tropProche }
        $liste = foreach ($r in $regles) { if ($r -eq $cible) { $modifiee } else { $r } }
        @{ Regles = @($liste); Id = $Id; Regle = $modifiee }
    }
    Invoke-CopieApiModification -Fichier $Fichier -Config $Config -Transformer $transformer -Argument @{ Id = $Id; Patch = $patch } -Action 'modification' -Commentaire $Commentaire `
        -Appelant $Appelant -Empreinte $Empreinte -AccepterAvertissements:$AccepterAvertissements
}
