<#
    Chargeur du module FileManagement.Gui.

    Dot-source les fichiers de Private\ puis de Views\ puis de Public\ (ordre alphabétique) ; une
    erreur de chargement nomme le fichier fautif. Exporte, pour chaque fichier de Public\, la
    fonction du même nom (règle « un fichier = une fonction »). Le manifeste (FunctionsToExport)
    reste la liste qui fait foi.
#>

$moduleRoot = $PSScriptRoot

$dossiers = 'Private', 'Views', 'Public'
$publics = New-Object System.Collections.Generic.List[string]
foreach ($dossier in $dossiers) {
    $chemin = Join-Path $moduleRoot $dossier
    if (-not (Test-Path -LiteralPath $chemin)) { continue }
    foreach ($fichier in @(Get-ChildItem -LiteralPath $chemin -Filter '*.ps1' -File -Recurse | Sort-Object FullName)) {
        try { . $fichier.FullName }
        catch { throw ('FileManagement.Gui : chargement de {0} impossible : {1}' -f $fichier.FullName, $_.Exception.Message) }
        if ($dossier -eq 'Public') {
            if (-not (Get-Command -Name $fichier.BaseName -CommandType Function -ErrorAction SilentlyContinue)) {
                throw ('FileManagement.Gui : {0} ne définit pas la fonction {1} (nom de fichier = nom de fonction).' -f $fichier.FullName, $fichier.BaseName)
            }
            $publics.Add($fichier.BaseName)
        }
    }
}

# Dossier des vues XAML (Gui\Xaml), voisin du dossier du module.
$Script:DossierXaml = Join-Path (Split-Path -Parent $moduleRoot) 'Xaml'

Export-ModuleMember -Function $publics.ToArray()
