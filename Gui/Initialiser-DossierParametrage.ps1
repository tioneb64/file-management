<#
    .SYNOPSIS
        Crée et protège le dossier des fichiers de paramétrage de file_management.

    .DESCRIPTION
        Le fichier de paramétrage décide quels programmes le compte de service exécute et où il lit et
        écrit : celui qui peut le modifier agit avec les droits de ce compte. Ce dossier ne doit donc être
        accessible qu'aux administrateurs et au compte de service qui lance les jobs Jenkins.

        Droits posés (l'héritage est coupé, les droits hérités ne sont pas conservés) :
          - dossier de paramétrage : le groupe administrateur en modification ; le compte de service en
            LECTURE seule (le moteur lit le paramétrage, il ne l'écrit jamais) ; SYSTEM en contrôle total ;
          - sous-dossier des versions (historique des modifications) : le groupe administrateur et
            SYSTEM seulement ; le compte de service n'y a aucun accès.
        Les administrateurs locaux (BUILTIN\Administrators) n'ont PAS accès, sauf avec
        -InclureAdministrateursLocaux.

        Cette commande modifie des droits : elle demande une confirmation (ou -Confirm:$false) et
        accepte -WhatIf pour afficher ce qui serait fait. Elle refuse de s'appliquer si le compte qui la
        lance n'appartient pas au groupe administrateur indiqué (il se couperait l'accès au dossier).

    .PARAMETER Dossier
        Dossier de paramétrage (créé s'il n'existe pas). C'est celui passé à Lancer-GestionCopie.ps1.

    .PARAMETER GroupeAdmin
        Groupe administrateur (DOMAINE\Groupe ou SID) : modification du paramétrage.

    .PARAMETER CompteService
        Compte de service Jenkins (DOMAINE\compte, compte de service géré DOMAINE\compte$ ou SID) : lecture.

    .PARAMETER DossierVersions
        Nom du sous-dossier des versions (par défaut : versions, comme Parametrage.DossierVersions).

    .PARAMETER InclureAdministrateursLocaux
        Ajoute BUILTIN\Administrators en modification (à éviter : le but est de limiter l'accès).

    .EXAMPLE
        .\Initialiser-DossierParametrage.ps1 -Dossier D:\Parametrage -GroupeAdmin 'DOMAINE\GG_Copie_Admins' -CompteService 'DOMAINE\svc-jenkins' -WhatIf
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory)] [string] $Dossier,
    [Parameter(Mandatory)] [string] $GroupeAdmin,
    [Parameter(Mandatory)] [string] $CompteService,
    [string] $DossierVersions = 'versions',
    [switch] $InclureAdministrateursLocaux
)

$ErrorActionPreference = 'Stop'

function Resolve-Identite {
    param([string] $Nom)
    try {
        if ($Nom -match '^S-\d-') { return (New-Object System.Security.Principal.SecurityIdentifier($Nom)) }
        return (New-Object System.Security.Principal.NTAccount($Nom)).Translate([System.Security.Principal.SecurityIdentifier])
    }
    catch { throw ('Identité introuvable : {0} ({1})' -f $Nom, $_.Exception.Message) }
}

$sidAdmin = Resolve-Identite -Nom $GroupeAdmin
$sidService = Resolve-Identite -Nom $CompteService
$sidSysteme = New-Object System.Security.Principal.SecurityIdentifier([System.Security.Principal.WellKnownSidType]::LocalSystemSid, $null)
$sidAdminsLocaux = New-Object System.Security.Principal.SecurityIdentifier([System.Security.Principal.WellKnownSidType]::BuiltinAdministratorsSid, $null)
if ($sidAdmin -eq $sidService) { throw 'Le groupe administrateur et le compte de service doivent être distincts.' }

# Garde-fou : ne pas se couper l'accès. Le jeton de l'utilisateur courant doit contenir le groupe.
$jeton = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$membre = ($jeton.User -eq $sidAdmin) -or (@($jeton.Groups | Where-Object { $_ -eq $sidAdmin }).Count -gt 0)
if (-not $membre) {
    throw ('Le compte {0} n''appartient pas à {1} : appliquer ces droits le priverait de l''accès au dossier. Lancez la commande avec un compte du groupe.' -f $jeton.Name, $GroupeAdmin)
}

$cheminVersions = Join-Path $Dossier $DossierVersions
$droits = [System.Security.AccessControl.FileSystemRights]
$heritage = [System.Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
$propagation = [System.Security.AccessControl.PropagationFlags]::None
$autoriser = [System.Security.AccessControl.AccessControlType]::Allow

function New-Regle {
    param($Sid, $Droit)
    New-Object System.Security.AccessControl.FileSystemAccessRule($Sid, $Droit, $heritage, $propagation, $autoriser)
}

$planDossier = @(
    @{ Sid = $sidSysteme; Droit = $droits::FullControl; Texte = 'SYSTEM : contrôle total' },
    @{ Sid = $sidAdmin; Droit = $droits::Modify; Texte = ('{0} : modification' -f $GroupeAdmin) },
    @{ Sid = $sidService; Droit = $droits::ReadAndExecute; Texte = ('{0} : lecture seule' -f $CompteService) }
)
$planVersions = @(
    @{ Sid = $sidSysteme; Droit = $droits::FullControl; Texte = 'SYSTEM : contrôle total' },
    @{ Sid = $sidAdmin; Droit = $droits::Modify; Texte = ('{0} : modification' -f $GroupeAdmin) }
)
if ($InclureAdministrateursLocaux) {
    $planDossier += @{ Sid = $sidAdminsLocaux; Droit = $droits::Modify; Texte = 'BUILTIN\Administrators : modification' }
    $planVersions += @{ Sid = $sidAdminsLocaux; Droit = $droits::Modify; Texte = 'BUILTIN\Administrators : modification' }
}

function Set-Protection {
    param([string] $Chemin, [object[]] $Plan)
    $acl = Get-Acl -LiteralPath $Chemin
    $acl.SetAccessRuleProtection($true, $false)          # coupe l'héritage, ne copie pas les droits hérités
    foreach ($ancien in @($acl.Access)) { $null = $acl.RemoveAccessRule($ancien) }
    foreach ($ligne in $Plan) { $acl.AddAccessRule((New-Regle -Sid $ligne.Sid -Droit $ligne.Droit)) }
    Set-Acl -LiteralPath $Chemin -AclObject $acl
}

foreach ($ligne in $planDossier) { Write-Verbose ('{0} : {1}' -f $Dossier, $ligne.Texte) }
foreach ($ligne in $planVersions) { Write-Verbose ('{0} : {1}' -f $cheminVersions, $ligne.Texte) }

if ($PSCmdlet.ShouldProcess($Dossier, ('créer le dossier et le sous-dossier "{0}", puis remplacer leurs droits : {1}' -f $DossierVersions, (($planDossier | ForEach-Object { $_.Texte }) -join ' ; ')))) {
    foreach ($d in $Dossier, $cheminVersions) {
        if (-not (Test-Path -LiteralPath $d)) { $null = New-Item -ItemType Directory -Path $d }
    }
    Set-Protection -Chemin $Dossier -Plan $planDossier
    Set-Protection -Chemin $cheminVersions -Plan $planVersions
    Write-Output ('Dossier protégé : {0}' -f $Dossier)
    Write-Output ('  - {0}' -f (($planDossier | ForEach-Object { $_.Texte }) -join "`n  - "))
    Write-Output ('Versions : {0} (compte de service sans accès)' -f $cheminVersions)
}
