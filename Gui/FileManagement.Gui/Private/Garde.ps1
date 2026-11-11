# Garde-fou des gestionnaires d'événements : une erreur dans un clic de bouton ne doit pas tuer l'interface.
# Sans lui, l'exception d'un gestionnaire remonte jusqu'à ShowDialog(), la fenêtre principale reste affichée mais
# figée et le processus s'arrête (Lancer-GestionCopie.ps1 affiche l'erreur puis quitte).

function Register-CopieGardeErreurs {
    <#
    .SYNOPSIS
        Intercepte les exceptions non gérées du répartiteur WPF : message à l'utilisateur, trace au journal, l'interface continue.
    .DESCRIPTION
        À appeler avant ShowDialog() de la fenêtre principale, sur son thread. L'erreur est affichée en clair
        (message, puis origine), écrite dans le journal de l'interface, et le répartiteur reprend la main.
    .PARAMETER Fenetre
        Fenêtre principale (propriétaire de la boîte de message).
    .PARAMETER Contexte
        Contexte de la session (pour le journal).
    .PARAMETER Afficher
        Bloc qui montre le message à l'utilisateur (reçoit la fenêtre et le texte). Par défaut : boîte de message ; les tests
        le remplacent pour ne pas bloquer.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Fenetre, [Parameter(Mandatory)] [hashtable] $Contexte, [scriptblock] $Afficher = $null)
    $Script:GardeFenetre = $Fenetre
    $Script:GardeContexte = $Contexte
    $Script:GardeAfficher = $(if ($null -ne $Afficher) { $Afficher } else {
            { param($f, $m) [void][System.Windows.MessageBox]::Show($f, $m, 'Gestion des transferts de fichiers', 'OK', 'Error') } })
    [System.Windows.Threading.Dispatcher]::CurrentDispatcher.add_UnhandledException({
            param($emetteur, $evenement)
            Write-Verbose ('erreur du répartiteur ({0})' -f $emetteur.GetType().Name)
            $evenement.Handled = $true
            try {
                $texte = Get-CopieTexteErreurInterface -Exception $evenement.Exception
                try {
                    Write-CopieJournal -Contexte $Script:GardeContexte -Niveau 'ERREUR' -Evenement 'erreur_interface' -Message ('Erreur dans l''interface : ' + $texte) `
                        -Donnees @{ erreur = $texte; type = $evenement.Exception.GetType().FullName }
                }
                catch { Write-Verbose ('journal indisponible : ' + $_.Exception.Message) }
                & $Script:GardeAfficher $Script:GardeFenetre ("Une erreur est survenue ; l'interface reste ouverte.`n`n{0}`n`nL'action en cours est abandonnée : vérifiez son résultat (bouton Actualiser)." -f $texte)
            }
            catch { Write-Verbose ('garde : ' + $_.Exception.Message) }
        })
}

function Get-CopieTexteErreurInterface {
    <#
    .SYNOPSIS
        Message lisible d'une exception remontée par un gestionnaire d'événement (sans l'enveloppe technique).
    .PARAMETER Exception
        Exception reçue.
    .OUTPUTS
        [string]
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param([AllowNull()] $Exception)
    $e = $Exception
    for ($i = 0; $i -lt 6 -and $null -ne $e -and $null -ne $e.InnerException -and ($e -is [System.Management.Automation.RuntimeException] -or $e -is [System.Reflection.TargetInvocationException] -or $e -is [System.Management.Automation.MethodInvocationException]); $i++) { $e = $e.InnerException }
    if ($null -eq $e) { return 'erreur inconnue' }
    "$($e.Message)".Trim()
}
