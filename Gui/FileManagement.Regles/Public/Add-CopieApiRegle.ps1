function Add-CopieApiRegle {
    <#
    .SYNOPSIS
        Ajoute une règle. Les champs non fournis prennent la valeur de secours du moteur (format toujours à jour).

    .DESCRIPTION
        Le module est le seul à écrire le fichier : même contrôle de conflit, mêmes versions conservées et même
        vérification du moteur que l'interface graphique. Réservé aux comptes de Acces.GroupesAdmin.
        Une planification « unique » à moins de deux périodes du déclencheur Jenkins (10 minutes par défaut) est refusée
        (étape delai, DateMinimale renseignée) : le moteur ne la verrait pas à temps et l'ordre ne partirait jamais.
        Ne fournissez que ce qui compte (id, source, cible, mode, planification...) ; un champ inconnu du format
        est refusé par le moteur (refus E06), jamais écrit en silence.

    .PARAMETER Fichier
        Fichier de paramétrage (parametrage\<env>.jsonl).
    .PARAMETER Regle
        Règle (table de hachage, objet ou texte JSON). Champ id obligatoire.
    .PARAMETER Commentaire
        Commentaire tracé avec la version (obligatoire).
    .PARAMETER Appelant
        Nom du programme appelant (tracé).
    .PARAMETER Empreinte
        Empreinte lue avec Get-CopieApiRegle : refuse l'écriture si le fichier a changé depuis.
    .PARAMETER AccepterAvertissements
        Enregistre malgré les avertissements du moteur (sinon ils annulent l'enregistrement).
    .PARAMETER Config
        Chemin de Gestion-Copie.config.psd1 (défaut : celui de l'interface).
    .OUTPUTS
        [pscustomobject] Copie.ApiResultat : Succes, Etape, Message, Refus, Avertissements, Version, Empreinte, Regle.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param(
        [Parameter(Mandatory)] [string] $Fichier,
        [Parameter(Mandatory)] $Regle,
        [Parameter(Mandatory)] [string] $Commentaire,
        [string] $Appelant,
        [string] $Empreinte,
        [switch] $AccepterAvertissements,
        [string] $Config
    )
    $entree = ConvertTo-CopieApiObjet -Valeur $Regle
    if ($null -eq $entree -or -not "$(Get-CopieValeur $entree 'id' '')".Trim()) {
        return New-CopieApiResultat $false 'invalide' 'Règle illisible ou sans id : un objet JSON avec un champ id est attendu.'
    }
    $id = "$($entree.id)".Trim()
    $transformer = {
        param($regles, $modele, $a)
        $id = $a.Id
        $entree = $a.Entree
        if (@($regles | Where-Object { "$(Get-CopieValeur $_ 'id' '')".ToLowerInvariant() -eq $id.ToLowerInvariant() }).Count -gt 0) {
            return New-CopieApiResultat $false 'existe' ('Une règle porte déjà l''id ' + $id + ' : utilisez Set-CopieApiRegle.')
        }
        $nouvelle = Merge-CopieRegle -Modele $modele -Existante $entree
        $tropProche = Test-CopieApiDelai -Regle $nouvelle -Initiale $null -Argument $a
        if ($null -ne $tropProche) { return $tropProche }
        @{ Regles = @($regles) + @($nouvelle); Id = $id; Regle = $nouvelle }
    }
    Invoke-CopieApiModification -Fichier $Fichier -Config $Config -Transformer $transformer -Argument @{ Id = $id; Entree = $entree } -Action 'ajout' -Commentaire $Commentaire `
        -Appelant $Appelant -Empreinte $Empreinte -AccepterAvertissements:$AccepterAvertissements
}
