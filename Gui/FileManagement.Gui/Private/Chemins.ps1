# Chemins racine : un chemin partiel se place sous une racine, un chemin complet reste tel quel. Même règle que le moteur
# (file_management\parametrage.py : resoudre_chemin) ; l'interface n'en tire que l'affichage (grille, détail, messages, formulaire).
# Environnement : « racine » (base, journaux, travail). Règles : « racine_source » et « racine_cible », qui se placent
# elles-mêmes sous la racine de l'environnement quand elles sont partielles. Pas de racine de source ou de cible :
# la racine de l'environnement sert aux deux.

function Resolve-CopieChemin {
    <#
    .SYNOPSIS
        Chemin complet d'un chemin saisi : un chemin complet est conservé, un chemin partiel est placé sous la racine.
    .DESCRIPTION
        Le séparateur final de la racine est facultatif (« D:\r\preprod » ou « D:\r\preprod\ »). Sans racine, ou pour
        un chemin vide, le chemin est rendu tel quel. N'utilise ni Join-Path ni Split-Path (ils échouent sur un
        lecteur absent) : seules des méthodes .NET sur le texte.
    .PARAMETER Chemin
        Chemin saisi (complet ou partiel).
    .PARAMETER Racine
        Racine sous laquelle placer un chemin partiel (peut être vide).
    .OUTPUTS
        [string]
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([AllowNull()] [AllowEmptyString()] [string] $Chemin = '', [AllowNull()] [AllowEmptyString()] [string] $Racine = '')
    $c = "$Chemin".Trim()
    $r = "$Racine".Trim()
    if (-not $c -or -not $r -or (Test-CopieCheminAbsolu -Chemin $c)) { return $c }
    ([System.IO.Path]::Combine($r.TrimEnd('\', '/'), $c.TrimStart('\', '/'))).Replace('/', '\')
}

function Get-CopieTexteChamp {
    # Champ d'un objet lu dans le fichier, en texte rogné ; vide si absent.
    [CmdletBinding()]
    [OutputType([string])]
    param([AllowNull()] $Objet, [Parameter(Mandatory)] [string] $Nom)
    $v = Get-CopieValeur $Objet $Nom $null
    if ($null -eq $v) { '' } else { "$v".Trim() }
}

function Get-CopieCheminsEnvironnement {
    <#
    .SYNOPSIS
        Chemins complets d'un environnement (racines, base, journaux, travail), tels que le moteur les comprendra.
    .DESCRIPTION
        Les dossiers des journaux et de travail absents prennent la valeur du moteur : « logs » et « travail » à côté
        de la base. Un chemin qui reste partiel faute de racine est rendu tel quel (le moteur le refusera : E07).
    .PARAMETER Entete
        En-tête du fichier de paramétrage (Read-CopieFichierParametrage).Entete, ou $null.
    .OUTPUTS
        [pscustomobject] Racine, RacineSource, RacineCible, Base, DossierLogs, DossierTravail (texte vide si inconnu).
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param([AllowNull()] $Entete)
    $racine = Get-CopieTexteChamp -Objet $Entete -Nom 'racine'
    $base = Resolve-CopieChemin -Chemin (Get-CopieTexteChamp -Objet $Entete -Nom 'base') -Racine $racine
    $dossierBase = ''
    if ($base) { try { $dossierBase = [System.IO.Path]::GetDirectoryName($base) } catch { $dossierBase = '' } }
    $logs = Resolve-CopieChemin -Chemin (Get-CopieTexteChamp -Objet $Entete -Nom 'dossier_logs') -Racine $racine
    if (-not $logs -and $dossierBase) { $logs = [System.IO.Path]::Combine($dossierBase, 'logs') }
    $travail = Resolve-CopieChemin -Chemin (Get-CopieTexteChamp -Objet $Entete -Nom 'dossier_travail') -Racine $racine
    if (-not $travail -and $dossierBase) { $travail = [System.IO.Path]::Combine($dossierBase, 'travail') }
    [pscustomobject]@{
        PSTypeName = 'Copie.CheminsEnvironnement'
        Racine = $racine
        RacineSource = (Resolve-CopieChemin -Chemin (Get-CopieTexteChamp -Objet $Entete -Nom 'racine_source') -Racine $racine)
        RacineCible = (Resolve-CopieChemin -Chemin (Get-CopieTexteChamp -Objet $Entete -Nom 'racine_cible') -Racine $racine)
        Base = $base; DossierLogs = $logs; DossierTravail = $travail
    }
}

function Get-CopieCheminsRegle {
    <#
    .SYNOPSIS
        Chemins complets d'une règle (source, cible, dossier temporaire) : les chemins partiels se placent sous les racines.
    .DESCRIPTION
        Source sous la racine des sources, cible sous la racine des cibles (à défaut, la racine de l'environnement),
        dossier temporaire sous la racine de l'environnement. Le dossier d'archive n'est pas touché : relatif, il se
        calcule depuis la source à chaque lancement (variables de date comprises).
    .PARAMETER Regle
        Règle lue dans le fichier.
    .PARAMETER Entete
        En-tête du fichier de paramétrage, ou $null (aucune racine : chemins rendus tels quels).
    .OUTPUTS
        [pscustomobject] Source, Cible, DossierTemporaire (texte vide si absent).
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param([Parameter(Mandatory)] $Regle, [AllowNull()] $Entete)
    $chemins = Get-CopieCheminsEnvironnement -Entete $Entete
    $racineSource = $(if ($chemins.RacineSource) { $chemins.RacineSource } else { $chemins.Racine })
    $racineCible = $(if ($chemins.RacineCible) { $chemins.RacineCible } else { $chemins.Racine })
    [pscustomobject]@{
        PSTypeName = 'Copie.CheminsRegle'
        Source = (Resolve-CopieChemin -Chemin (Get-CopieTexteChamp -Objet $Regle -Nom 'source') -Racine $racineSource)
        Cible = (Resolve-CopieChemin -Chemin (Get-CopieTexteChamp -Objet $Regle -Nom 'cible') -Racine $racineCible)
        DossierTemporaire = (Resolve-CopieChemin -Chemin (Get-CopieTexteChamp -Objet $Regle -Nom 'dossier_temporaire') -Racine $chemins.Racine)
    }
}

function Get-CopieModesRegle {
    <#
    .SYNOPSIS
        Les modes d'une règle, avec ce qu'ils font : sert aux filtres et aux aides du formulaire.
    .DESCRIPTION
        Le moteur reste la source de vérité (--modele-regle) : cette liste ne sert qu'aux filtres de la fenêtre
        principale, qui s'affichent avant tout appel du moteur.
    .OUTPUTS
        [pscustomobject[]] Nom, Transfert (a une cible), Resume.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject[]])]
    param()
    @(
        [pscustomobject]@{ Nom = 'copie'; Transfert = $true; Resume = 'copie les fichiers vers la cible, la source est conservée' }
        [pscustomobject]@{ Nom = 'deplacement'; Transfert = $true; Resume = 'copie vers la cible puis supprime l''original' }
        [pscustomobject]@{ Nom = 'archivage'; Transfert = $true; Resume = 'copie vers la cible puis range l''original dans l''archive' }
        [pscustomobject]@{ Nom = 'suppression'; Transfert = $false; Resume = 'SUPPRIME DÉFINITIVEMENT les fichiers sélectionnés (sans cible)' }
        [pscustomobject]@{ Nom = 'count'; Transfert = $false; Resume = 'compte les fichiers sélectionnés et les compare aux seuils, sans rien toucher' }
        [pscustomobject]@{ Nom = 'size'; Transfert = $false; Resume = 'mesure le volume des fichiers sélectionnés et le compare aux seuils, sans rien toucher' }
        [pscustomobject]@{ Nom = 'synchro'; Transfert = $false; Resume = 'aucun dossier : lance avant_lot puis avant_fichier après ses dépendances et rend un statut' }
    )
}
