#
# Manifeste du module Copie.Gui : interface WPF de gestion du paramétrage et de l'état des
# règles de copie_fichiers. Aucune logique métier : le moteur (python -m copie) valide, calcule l'état
# et exécute les actions ; l'interface l'appelle et affiche le JSON (docs/07-contrat-moteur-frontend.md).

@{
    RootModule           = 'Copie.Gui.psm1'
    ModuleVersion        = '0.1.0'
    GUID                 = '3f6f0a54-0d57-4a2c-9a3e-6c1e5a3d7b11'
    Author               = 'copie_fichiers'
    CompanyName          = ''
    Copyright            = '(c) copie_fichiers'
    Description          = 'copie_fichiers - Interface graphique WPF : environnements, règles, état.'
    PowerShellVersion    = '5.1'
    CompatiblePSEditions = @('Desktop', 'Core')

    # Liste explicite, jamais '*'.
    FunctionsToExport    = @('Start-CopieGui')
    CmdletsToExport      = @()
    VariablesToExport    = @()
    AliasesToExport      = @()

    PrivateData          = @{
        PSData = @{
            Tags = @('copie_fichiers', 'WPF')
        }
    }
}
