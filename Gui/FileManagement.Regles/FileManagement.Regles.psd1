#
# Manifeste du module FileManagement.Regles : API de règles de file_management.
# SEUL habilité à modifier le fichier des règles (parametrage\<env>.jsonl) : l'interface graphique charge
# le même noyau (dossier Private\), les autres programmes (PowerShell, Python) passent par les fonctions
# ci-dessous ou par Invoke-RegleApi.ps1. Le format des règles reste celui du moteur (--modele-regle).

@{
    RootModule           = 'FileManagement.Regles.psm1'
    ModuleVersion        = '1.0.0'
    GUID                 = '8b1c2d3e-4f50-4a61-9b72-0c1d2e3f4a5b'
    Author               = 'Benoit Thibaudeau'
    CompanyName          = ''
    Copyright            = '(c) Benoit Thibaudeau'
    Description          = 'file_management - API de règles : lecture, ajout, modification, suppression avec contrôle de conflit, versions et vérification du moteur.'
    PowerShellVersion    = '5.1'
    CompatiblePSEditions = @('Desktop', 'Core')

    FunctionsToExport    = @('Get-CopieApiInfo', 'Get-CopieApiModele', 'Get-CopieApiRegle', 'Add-CopieApiRegle', 'Set-CopieApiRegle', 'Remove-CopieApiRegle')
    CmdletsToExport      = @()
    VariablesToExport    = @()
    AliasesToExport      = @()
}
