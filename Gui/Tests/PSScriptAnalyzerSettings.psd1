@{
    # Règles par défaut, sauf celles qui ne s'appliquent pas à une application WPF interactive.
    Severity     = @('Error', 'Warning')
    ExcludeRules = @(
        'PSAvoidUsingWriteHost'                  # Run-Tests.ps1 et Initialiser-*.ps1 sont des scripts interactifs
        'PSUseShouldProcessForStateChangingFunctions'
        'PSUseSingularNouns'                     # Get-CopieEnvironnement renvoie une liste : nom volontaire
        'PSUseBOMForUnicodeEncodedFile'          # les fichiers ont un BOM ; l'analyse ne voit pas l'encodage des .xaml
    )
}
