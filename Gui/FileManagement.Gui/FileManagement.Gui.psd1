#
# Manifeste du module FileManagement.Gui : interface WPF de gestion du paramétrage et de l'état des
# règles de file_management. Aucune logique métier : le moteur (python -m file_management) valide, calcule l'état
# et exécute les actions ; l'interface l'appelle et affiche le JSON (docs/07-contrat-moteur-frontend.md).

@{
    RootModule           = 'FileManagement.Gui.psm1'
    ModuleVersion        = '0.1.0'
    GUID                 = '3f6f0a54-0d57-4a2c-9a3e-6c1e5a3d7b11'
    Author               = 'Benoit Thibaudeau (benoit.thibaudeau64@gmail.com)'
    CompanyName          = ''
    Copyright            = '(c) Benoit Thibaudeau'
    Description          = 'file_management - Interface graphique WPF : environnements, règles, état.'
    PowerShellVersion    = '5.1'
    CompatiblePSEditions = @('Desktop', 'Core')

    # Liste explicite, jamais '*'.
    FunctionsToExport    = @('Start-CopieGui')
    CmdletsToExport      = @()
    VariablesToExport    = @()
    AliasesToExport      = @()

    PrivateData          = @{
        PSData = @{
            Tags = @('file_management', 'WPF')
        }
    }
}
