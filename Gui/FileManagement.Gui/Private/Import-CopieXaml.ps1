function Import-CopieXaml {
    <#
    .SYNOPSIS
        Charge une vue WPF depuis Gui\Xaml\<Nom>.xaml.

    .DESCRIPTION
        Le dossier Xaml est fourni comme BaseUri : les vues y trouvent Styles.xaml par un chemin relatif.
        Chaque appel crée une nouvelle instance (un onglet par environnement), avec ses propres noms.

    .PARAMETER Nom
        Nom du fichier sans extension (MainWindow, Environnement, Dialog.Diagnostics).

    .OUTPUTS
        L'élément racine de la vue (Window ou TabItem).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $Nom)

    Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase

    $chemin = Join-Path $Script:DossierXaml ($Nom + '.xaml')
    if (-not (Test-Path -LiteralPath $chemin -PathType Leaf)) { throw ('Vue introuvable : {0}' -f $chemin) }
    $contexte = New-Object System.Windows.Markup.ParserContext
    $contexte.BaseUri = New-Object System.Uri(('file:///' + ($Script:DossierXaml -replace '\\', '/').TrimEnd('/') + '/'))
    $flux = [System.IO.File]::OpenRead($chemin)
    try { [System.Windows.Markup.XamlReader]::Load($flux, $contexte) }
    finally { $flux.Dispose() }
}
