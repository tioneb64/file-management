#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
# Garde-fou des gestionnaires d'événements, et absence d'appel d'enregistrement avec un identifiant de règle vide.
# Les tests de fenêtre exigent un thread STA (powershell.exe, pas pwsh -MTA).

BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..\FileManagement.Gui\FileManagement.Gui.psd1') -Force
    $Script:Gui = Join-Path $PSScriptRoot '..\FileManagement.Gui'
}

Describe 'Garde-fou de l''interface' {
    It 'une erreur dans un gestionnaire est affichée, journalisée, et ne ferme pas la fenêtre' -Skip:([System.Threading.Thread]::CurrentThread.GetApartmentState() -ne 'STA') {
        $res = InModuleScope FileManagement.Gui {
            Add-Type -AssemblyName PresentationFramework
            $Script:Messages = New-Object System.Collections.Generic.List[string]
            $ctx = @{ Config = @{ Journal = @{ Dossier = $null } }; Utilisateur = 'test'; LogBox = $null }
            $f = New-Object System.Windows.Window
            $f.Width = 100; $f.Height = 100; $f.ShowInTaskbar = $false; $f.WindowStartupLocation = 'Manual'; $f.Left = -2000; $f.Top = -2000
            $bouton = New-Object System.Windows.Controls.Button
            $f.Content = $bouton
            $Script:Apres = $false
            $bouton.Add_Click({ throw 'Impossible de lier l''argument au paramètre "IdRegle"' })
            Register-CopieGardeErreurs -Fenetre $f -Contexte $ctx -Afficher { param($fen, $m) Write-Verbose "$fen"; $Script:Messages.Add($m) }
            # Le clic est lancé par le répartiteur (comme un vrai clic) : l'exception du gestionnaire lui remonte, pas au test.
            $Script:F = $f
            $f.Add_ContentRendered({
                    $this.Dispatcher.BeginInvoke([System.Windows.Threading.DispatcherPriority]::Normal, [Action] {
                            $Script:F.Content.RaiseEvent((New-Object System.Windows.RoutedEventArgs ([System.Windows.Controls.Primitives.ButtonBase]::ClickEvent)))
                        }) | Out-Null
                    $this.Dispatcher.BeginInvoke([System.Windows.Threading.DispatcherPriority]::Background, [Action] {
                            $Script:Apres = $true                  # atteint : l'exception n'a pas interrompu la boucle
                            $Script:F.Close()
                        }) | Out-Null
                })
            $garde = New-Object System.Windows.Threading.DispatcherTimer      # filet : jamais de test bloqué
            $garde.Interval = [TimeSpan]::FromSeconds(20)
            $garde.Add_Tick({ $this.Stop(); $Script:F.Close() })
            $garde.Start()
            $fin = $null
            try { $null = $f.ShowDialog() } catch { $fin = $_.Exception.Message }
            @{ Fin = $fin; Messages = @($Script:Messages); Apres = $Script:Apres }
        }
        $res.Fin | Should -BeNullOrEmpty
        $res.Apres | Should -BeTrue
        $res.Messages.Count | Should -Be 1
        $res.Messages[0] | Should -Match 'l''interface reste ouverte'
        $res.Messages[0] | Should -Match 'IdRegle'
    }
    It 'le texte d''erreur n''affiche pas l''enveloppe technique' {
        InModuleScope FileManagement.Gui {
            $inner = New-Object System.InvalidOperationException 'cause réelle'
            $enveloppe = New-Object System.Reflection.TargetInvocationException $inner
            Get-CopieTexteErreurInterface -Exception $enveloppe | Should -Be 'cause réelle'
            Get-CopieTexteErreurInterface -Exception $null | Should -Be 'erreur inconnue'
        }
    }
}

Describe 'Appels de Invoke-CopieEnregistrement' {
    It 'aucun appel ne passe un identifiant de règle vide (paramètre obligatoire : liaison impossible)' {
        $motif = '-IdRegle\s+(''''|"")'      # -IdRegle '' ou -IdRegle ""
        $fichiers = Get-ChildItem -Path $Script:Gui -Filter '*.ps1' -Recurse
        $suite = $fichiers | Select-String -Pattern $motif
        @($suite).Count | Should -Be 0
    }
    It 'le paramètre IdRegle refuse la chaîne vide : tout appel doit nommer ce qui change' {
        InModuleScope FileManagement.Gui {
            (Get-Command Invoke-CopieEnregistrement).Parameters['IdRegle'].Attributes.Where({ $_ -is [System.Management.Automation.ParameterAttribute] }).Mandatory | Should -BeTrue
        }
    }
}
