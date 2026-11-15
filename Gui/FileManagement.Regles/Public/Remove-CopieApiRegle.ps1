function Remove-CopieApiRegle {
    <#
    .SYNOPSIS
        Supprime une règle (la version précédente du fichier reste dans le dossier des versions).

    .DESCRIPTION
        Même garanties que Add-CopieApiRegle. Une règle dont d'autres dépendent est refusée par le moteur (refus D01).

    .PARAMETER Fichier
        Fichier de paramétrage (parametrage\<env>.jsonl).
    .PARAMETER Id
        Identifiant de la règle à supprimer.
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
        [Parameter(Mandatory)] [string] $Commentaire,
        [string] $Appelant,
        [string] $Empreinte,
        [switch] $AccepterAvertissements,
        [string] $Config
    )
    $transformer = {
        param($regles, $modele, $a)
        $null = $modele
        $Id = $a.Id
        $cible = @($regles | Where-Object { "$(Get-CopieValeur $_ 'id' '')".ToLowerInvariant() -eq $Id.ToLowerInvariant() }) | Select-Object -First 1
        if ($null -eq $cible) { return New-CopieApiResultat $false 'introuvable' ('Règle introuvable : ' + $Id) }
        @{ Regles = @($regles | Where-Object { $_ -ne $cible }); Id = $Id; Regle = $null }
    }
    Invoke-CopieApiModification -Fichier $Fichier -Config $Config -Transformer $transformer -Argument @{ Id = $Id } -Action 'suppression' -Commentaire $Commentaire `
        -Appelant $Appelant -Empreinte $Empreinte -AccepterAvertissements:$AccepterAvertissements
}
