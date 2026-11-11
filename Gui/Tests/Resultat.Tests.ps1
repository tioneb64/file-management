#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
# Fenêtre unique de résultat : lignes, synthèse, conversion des contrôles de répertoires. Aucun appel du moteur.

BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..\FileManagement.Gui\FileManagement.Gui.psd1') -Force
}

Describe 'Lignes de résultat' {
    It 'colore chaque gravité et refuse une gravité inconnue' {
        InModuleScope FileManagement.Gui {
            (New-CopieLigneResultat -Gravite 'Erreur' -Sujet 's' -Message 'm').Couleur | Should -Be '#C0392B'
            (New-CopieLigneResultat -Gravite 'Avertissement' -Sujet 's' -Message 'm').Couleur | Should -Be '#C77700'
            (New-CopieLigneResultat -Gravite 'Information' -Sujet 's' -Message 'm').Couleur | Should -Be '#1F6FB2'
            { New-CopieLigneResultat -Gravite 'Autre' -Sujet 's' -Message 'm' } | Should -Throw
        }
    }
    It 'résume : tout va bien, avertissements, erreurs' {
        InModuleScope FileManagement.Gui {
            $i = New-CopieLigneResultat -Gravite 'Information' -Sujet 's' -Message 'm'
            $a = New-CopieLigneResultat -Gravite 'Avertissement' -Sujet 's' -Message 'm'
            $e = New-CopieLigneResultat -Gravite 'Erreur' -Sujet 's' -Message 'm'
            Get-CopieResumeResultat -Ligne @($i) -Debut 'Règle « x » enregistrée.' | Should -Be 'Règle « x » enregistrée. Tout s''est bien passé.'
            Get-CopieResumeResultat -Ligne @($i, $a, $a) | Should -Be '2 avertissement(s), aucune erreur.'
            Get-CopieResumeResultat -Ligne @($i, $a, $e) | Should -Be '1 erreur(s), 1 avertissement(s).'
            Get-CopieResumeResultat -Ligne @() | Should -Be 'Tout s''est bien passé.'
        }
    }
    It 'charge la fenêtre : un titre modifiable, un résumé et une grille de trois colonnes' -Skip:([System.Threading.Thread]::CurrentThread.GetApartmentState() -ne 'STA') {
        InModuleScope FileManagement.Gui {
            $f = Import-CopieXaml -Nom 'Dialog.Resultat'
            $f.FindName('Resume') | Should -Not -BeNullOrEmpty
            $g = $f.FindName('Grille')
            $g.Columns.Count | Should -Be 3
            $g.ItemsSource = @(New-CopieLigneResultat -Gravite 'Erreur' -Sujet 's' -Message 'un message')
            $g.Items.Count | Should -Be 1
        }
    }
}

Describe 'Contrôle des répertoires -> lignes de résultat' {
    It 'une ligne par répertoire : information, erreur ou avertissement selon le verdict' {
        InModuleScope FileManagement.Gui {
            $c = '[{"role":"source","chemin":"D:\\r\\src","existe":true,"lecture":true,"ecriture":null,"a_creer":false,"detail":""},
{"role":"cible","chemin":"D:\\r\\dst","existe":false,"lecture":null,"ecriture":true,"a_creer":true,"detail":""},
{"role":"temporaire","chemin":"D:\\r\\tmp","existe":true,"lecture":true,"ecriture":false,"a_creer":false,"detail":"ecriture impossible"}]' | ConvertFrom-Json
            $l = @(ConvertTo-CopieLignesResultatControle -Controle @(ConvertTo-CopieControleSimulation -Controle $c))
            $l.Count | Should -Be 3
            ($l | ForEach-Object { $_.Gravite }) -join ',' | Should -Be 'Information,Avertissement,Erreur'
            $l[0].Message | Should -Match 'D:\\r\\src : existe'
            $l[1].Message | Should -Match 'n''existe pas.*peut être créé'
            $l[2].Message | Should -Match 'ecriture impossible'
            ($l | ForEach-Object { $_.Sujet }) -join ',' | Should -Be 'Répertoire d''origine,Répertoire cible,Dossier temporaire'
        }
    }
    It 'rassemble les créations réussies et les échecs' {
        InModuleScope FileManagement.Gui {
            $r = [pscustomobject]@{
                Crees = @([pscustomobject]@{ role = 'cible'; chemin = 'D:\dst' })
                Echecs = @([pscustomobject]@{ role = 'archive'; chemin = 'D:\arc'; erreur = 'accès refusé' })
                Erreur = ''
            }
            $l = @(New-CopieLignesCreation -Resultat $r)
            ($l | ForEach-Object { $_.Gravite }) -join ',' | Should -Be 'Information,Erreur'
            $l[0].Message | Should -Be 'cible : D:\dst'
            $l[1].Message | Should -Match 'accès refusé'
            @(New-CopieLignesCreation -Resultat ([pscustomobject]@{ Crees = @(); Echecs = @(); Erreur = 'moteur injoignable' })).Count | Should -Be 1
        }
    }
}

Describe 'Une seule boîte de message par demande' {
    It 'Invoke-CopieControleRegle ne montre plus aucune boîte « OK » : seulement la question Oui / Non et la fenêtre de résultat' {
        $source = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\FileManagement.Gui\Views\Vue.Simulation.ps1') -Raw
        $debut = $source.IndexOf('function Invoke-CopieControleRegle')
        $fin = $source.IndexOf('function Invoke-CopieSimulation')
        $corps = $source.Substring($debut, $fin - $debut)
        ([regex]::Matches($corps, "MessageBox\]::Show")).Count | Should -Be 1
        $corps | Should -Match "'YesNo'"
        $corps | Should -Match 'Show-CopieResultat'
    }
}

Describe 'Collecteur d''une opération en plusieurs étapes' {
    It 'rassemble les notes des étapes, les rend en une fois avec les lignes données, puis se vide' {
        InModuleScope FileManagement.Gui {
            Reset-CopieOperation
            Add-CopieLigneOperation -Gravite 'Information' -Sujet 'Dossier créé' -Message 'base : D:\x'
            Add-CopieLigneOperation -Gravite 'Avertissement' -Sujet 'Base' -Message 'pas prête'
            $Script:LignesOperation.Count | Should -Be 2
            Reset-CopieOperation
            $Script:LignesOperation.Count | Should -Be 0
        }
    }
    It 'convertit une icône de boîte de message en gravité' {
        InModuleScope FileManagement.Gui {
            Get-CopieGraviteIcone -Icone 'Error' | Should -Be 'Erreur'
            Get-CopieGraviteIcone -Icone 'Warning' | Should -Be 'Avertissement'
            Get-CopieGraviteIcone -Icone 'Information' | Should -Be 'Information'
            Get-CopieGraviteIcone | Should -Be 'Information'
        }
    }
    It 'Show-CopieOperation ne montre rien (et ne bloque pas) quand il n''y a rien à dire' {
        InModuleScope FileManagement.Gui {
            Reset-CopieOperation
            { Show-CopieOperation -Contexte @{ Fenetre = $null } -Titre 't' } | Should -Not -Throw
        }
    }
}

Describe 'Opérations sur les environnements : plus de série de boîtes « OK »' {
    BeforeAll {
        $Script:Source = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\FileManagement.Gui\Views\Vue.Environnements.ps1') -Raw
        $Script:Corps = {
            param($debut, $fin)
            $a = $Script:Source.IndexOf("function $debut")
            $b = $(if ($fin) { $Script:Source.IndexOf("function $fin") } else { $Script:Source.Length })
            $Script:Source.Substring($a, $b - $a)
        }
    }
    It 'le résultat d''une opération passe par la fenêtre unique' {
        $c = & $Script:Corps 'Show-CopieResultatEnvironnement' 'Get-CopieEnvironnementsActuels'
        $c | Should -Not -Match 'MessageBox'
        $c | Should -Match 'Show-CopieOperation'
    }
    It 'la question sur les dossiers n''ouvre que sa question Oui / Non' {
        $c = & $Script:Corps 'Invoke-CopieQuestionDossiers' 'Invoke-CopieNouvelEnvironnement'
        $c | Should -Not -Match "'OK'"
        $c | Should -Match "'YesNo'"
    }
    It 'créer la base : une question Oui / Non puis la fenêtre unique' {
        $c = & $Script:Corps 'Invoke-CopieCreerBase' 'Read-CopieConfirmationSuppression'
        $c | Should -Not -Match "'OK'"
        $c | Should -Match 'Show-CopieOperation'
    }
    It 'modifier un environnement : seules deux sorties immédiates gardent une boîte « OK » (lecture seule, fichier changé)' {
        $c = & $Script:Corps 'Invoke-CopieModifierEnvironnement' 'Invoke-CopieRenommage'
        ([regex]::Matches($c, "'OK'")).Count | Should -Be 2
        $c | Should -Match 'Show-CopieOperation'
    }
}
