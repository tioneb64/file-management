<#
    Chargeur du module FileManagement.Regles.

    Private\  : noyau partagé avec l'interface (lecture/écriture du fichier de règles, moteur, configuration).
    Internal\ : aides propres à l'API.
    Public\   : une fonction par fichier, exportée.
#>

$moduleRoot = $PSScriptRoot
$publics = New-Object System.Collections.Generic.List[string]
foreach ($dossier in 'Private', 'Internal', 'Public') {
    $chemin = Join-Path $moduleRoot $dossier
    foreach ($fichier in @(Get-ChildItem -LiteralPath $chemin -Filter '*.ps1' -File | Sort-Object FullName)) {
        try { . $fichier.FullName }
        catch { throw ('FileManagement.Regles : chargement de {0} impossible : {1}' -f $fichier.FullName, $_.Exception.Message) }
        if ($dossier -eq 'Public') { $publics.Add($fichier.BaseName) }
    }
}
# Configuration par défaut : celle de l'interface, voisine du module (Gui\Gestion-Copie.config.psd1).
$Script:ConfigurationParDefaut = Join-Path (Split-Path -Parent $moduleRoot) 'Gestion-Copie.config.psd1'
$Script:VersionApi = 1

Export-ModuleMember -Function $publics.ToArray()
