#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
# Point d'accès JEA : grammaire, chemins, droits, et appel du VRAI moteur Python (COPIE_TEST_PYTHON ;
# absent : ces derniers tests sont ignorés). La session JEA elle-même (New-PSSession, compte virtuel)
# n'est pas testée ici : elle exige un serveur et des droits d'administrateur (cahier de tests, J10E-M*).

BeforeDiscovery {
    $Script:PythonDisponible = [bool]$env:COPIE_TEST_PYTHON -and (Test-Path -LiteralPath $env:COPIE_TEST_PYTHON)
}

BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..\Jea\Copie.Jea\Copie.Jea.psd1') -Force
    $Script:Racine = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).ProviderPath
    $Script:Dossier = Join-Path $TestDrive 'param'
    $null = New-Item -ItemType Directory -Path $Script:Dossier
    $Script:Fichier = Join-Path $Script:Dossier 'production.jsonl'
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Script:Fichier, '{"version":1,"environnement":"production","base":"' + (Join-Path $TestDrive 'b.sqlite').Replace('\', '/') +'"}' + "`n", $utf8)
    $Script:Cfg = Join-Path $TestDrive 'jea.config.psd1'
    $python = "$env:COPIE_TEST_PYTHON"
    [System.IO.File]::WriteAllText($Script:Cfg, "@{ Python = '$python'; Racine = '$($Script:Racine)'; DossierParametrage = '$($Script:Dossier)'; GroupeAdmin = 'DOM\Admins'; DelaiMaxSec = 60 }", $utf8)
}

Describe 'Grammaire du point d''accès' {
    BeforeAll {
        $Script:Ligne = {
            param($argument, $fichier, $utilisateur)
            InModuleScope Copie.Jea -Parameters @{ a = $argument; f = $fichier; u = $utilisateur; d = $Script:Dossier } {
                param($a, $f, $u, $d)
                $c = [pscustomobject]@{ DossierParametrage = $d; Python = 'p'; Racine = 'r'; DelaiMaxSec = 1; GroupeAdmin = 'G' }
                ConvertTo-CopieJeaLigne -Argument $a -Fichier $f -Config $c -Utilisateur $u
            }
        }
    }
    It 'accepte les commandes du contrat et construit --option=valeur' {
        $l = & $Script:Ligne @('--etat', '--regle', 'r1') $Script:Fichier ''
        $l.Erreur | Should -Be ''
        $l.Droit | Should -Be 'lecture'
        $l.Arguments[0..1] -join ' ' | Should -Be '-m copie'
        $l.Arguments | Should -Contain '--regle=r1'
        $l.Arguments | Should -Contain '--format=json'
        $l.Arguments | Should -Contain ('--config=' + $Script:Fichier)
        (& $Script:Ligne @('--verifier', '--syntaxe-seule', '--precedent', (Join-Path $Script:Dossier 'versions\x.jsonl')) $Script:Fichier '').Erreur | Should -Be ''
        (& $Script:Ligne @('--purger', '--regle', 'r1', '--appliquer') $Script:Fichier 'DOM\ben').Droit | Should -Be 'ecriture'
        (& $Script:Ligne @('--trancher-incertain', '00ff', '--decision', 'livre', '--commentaire', 'vérifié') $Script:Fichier 'DOM\ben').Erreur | Should -Be ''
    }
    It '--modele-regle n''a pas besoin de fichier' {
        $l = & $Script:Ligne @('--modele-regle') '' ''
        $l.Erreur | Should -Be ''
        $l.Arguments | Should -Not -Contain '--config'
    }
    It 'refuse les commandes hors contrat et celles qui ne servent pas au front-end' {
        foreach ($c in '--initialiser-base', '--sauvegarder-base', '--lancer-regle', '--executer-regle', '--migrer-ancien', '--importer-historique', '--simulation', '-c', 'import os', '') {
            (& $Script:Ligne @($c) $Script:Fichier 'u').Erreur | Should -Not -BeNullOrEmpty -Because $c
        }
        (& $Script:Ligne @() $Script:Fichier 'u').Erreur | Should -Not -BeNullOrEmpty
    }
    It 'refuse une option inconnue, répétée, sans valeur, ou d''une autre commande' {
        (& $Script:Ligne @('--etat', '--appliquer') $Script:Fichier '').Erreur | Should -Match 'non permise'
        (& $Script:Ligne @('--etat', '--regle', 'a', '--regle', 'b') $Script:Fichier '').Erreur | Should -Match 'répétée'
        (& $Script:Ligne @('--etat', '--regle') $Script:Fichier '').Erreur | Should -Match 'manquante'
        (& $Script:Ligne @('--etat', '--python', 'x') $Script:Fichier '').Erreur | Should -Match 'non permise'
        (& $Script:Ligne @('--reprise') $Script:Fichier 'u').Erreur | Should -Match 'incorrecte'
    }
    It 'refuse les valeurs qui ne sont pas du type attendu' {
        foreach ($v in 'a;b', 'a b', '..\x', 'a"b', '') {
            (& $Script:Ligne @('--reprise', $v) $Script:Fichier 'u').Erreur | Should -Not -BeNullOrEmpty -Because "id '$v'"
        }
        (& $Script:Ligne @('--trancher-incertain', 'zz', '--decision', 'livre') $Script:Fichier 'u').Erreur | Should -Match 'incorrecte'
        (& $Script:Ligne @('--trancher-incertain', '00ff', '--decision', 'peut-etre') $Script:Fichier 'u').Erreur | Should -Match 'incorrecte'
    }
    It 'passe un commentaire qui commence par un tiret sans le prendre pour une option' {
        $l = & $Script:Ligne @('--acquitter', 'r1', '--commentaire', '--refait à la main') $Script:Fichier 'u'
        $l.Erreur | Should -Be ''
        $l.Arguments | Should -Contain '--commentaire=--refait à la main'
    }
    It 'trace le compte de la session, jamais celui que le front-end annonce' {
        $l = & $Script:Ligne @('--reprise', 'r1', '--utilisateur', 'DOM\usurpe') $Script:Fichier 'DOM\ben'
        $l.Arguments | Should -Contain '--utilisateur=DOM\ben'
        $l.Arguments | Should -Not -Contain '--utilisateur=DOM\usurpe'
        # option absente : ajoutée ; aucun compte connu : refus
        (& $Script:Ligne @('--reprise', 'r1') $Script:Fichier 'DOM\ben').Arguments | Should -Contain '--utilisateur=DOM\ben'
        (& $Script:Ligne @('--reprise', 'r1') $Script:Fichier '').Erreur | Should -Match 'utilisateur'
    }
    It 'n''accepte que les fichiers du dossier de paramétrage' {
        (& $Script:Ligne @('--etat') (Join-Path $Script:Dossier '..\autre.jsonl') '').Erreur | Should -Match 'hors du dossier'
        (& $Script:Ligne @('--etat') ($Script:Dossier + '2\x.jsonl') '').Erreur | Should -Match 'hors du dossier'
        (& $Script:Ligne @('--etat') 'C:\Windows\win.ini' '').Erreur | Should -Match 'hors du dossier'
        (& $Script:Ligne @('--etat') (Join-Path $Script:Dossier '..\param\production.jsonl') '').Erreur | Should -Be ''
        (& $Script:Ligne @('--etat') ($Script:Fichier.ToUpper()) '').Erreur | Should -Be ''
        (& $Script:Ligne @('--etat') '' '').Erreur | Should -Match 'obligatoire'
        (& $Script:Ligne @('--verifier', '--precedent', 'C:\Windows\win.ini') $Script:Fichier '').Erreur | Should -Match 'hors du dossier'
    }
}

Describe 'Droits de l''appelant' {
    It 'refuse les commandes d''écriture à qui n''est pas dans le groupe administrateur' {
        InModuleScope Copie.Jea -Parameters @{ c = $Script:Cfg; f = $Script:Fichier } {
            param($c, $f)
            $Script:CheminConfig = $c
            Mock Get-CopieJeaIdentite { [pscustomobject]@{ Compte = 'DOM\lecteur'; Principal = [pscustomobject]@{} | Add-Member -MemberType ScriptMethod -Name IsInRole -Value { $false } -PassThru } }
            $r = Invoke-CopieMoteurJea -Argument @('--reprise', 'r1') -Fichier $f
            $r.Code | Should -Be -1
            $r.Erreur | Should -Match 'administrateurs'
            Should -Invoke Get-CopieJeaIdentite -Times 1
        }
    }
    It 'laisse un non-administrateur consulter (la commande part, le refus ne vient pas du droit)' -Skip:(-not $Script:PythonDisponible) {
        InModuleScope Copie.Jea -Parameters @{ c = $Script:Cfg; f = $Script:Fichier } {
            param($c, $f)
            $Script:CheminConfig = $c
            Mock Get-CopieJeaIdentite { [pscustomobject]@{ Compte = 'DOM\lecteur'; Principal = $null } }
            $r = Invoke-CopieMoteurJea -Argument @('--verifier', '--syntaxe-seule') -Fichier $f
            $r.Erreur | Should -Not -Match 'administrateurs'
            $r.Sortie | Should -Match '"version_contrat"'
        }
    }
    It 'refuse sans configuration lisible' {
        InModuleScope Copie.Jea {
            $Script:CheminConfig = 'C:\absent\config.psd1'
            $r = Invoke-CopieMoteurJea -Argument @('--etat') -Fichier 'x'
            $r.Code | Should -Be -1
            $r.Erreur | Should -Match 'introuvable'
        }
    }
}

Describe 'Appel du moteur réel' -Skip:(-not $Script:PythonDisponible) {
    It 'renvoie le JSON du moteur : --modele-regle sans fichier, --verifier avec fichier' {
        InModuleScope Copie.Jea -Parameters @{ c = $Script:Cfg; f = $Script:Fichier } {
            param($c, $f)
            $Script:CheminConfig = $c
            $r = Invoke-CopieMoteurJea -Argument @('--modele-regle')
            $r.Code | Should -Be 0
            ($r.Sortie | ConvertFrom-Json).version_contrat | Should -Be 1
            $r = Invoke-CopieMoteurJea -Argument @('--verifier', '--syntaxe-seule') -Fichier $f
            ($r.Sortie | ConvertFrom-Json).regles_lues | Should -Be 0
        }
    }
    It 'rend un code 0 ou 4 et aucune erreur pour un paramétrage valide' {
        InModuleScope Copie.Jea -Parameters @{ c = $Script:Cfg; f = $Script:Fichier } {
            param($c, $f)
            $Script:CheminConfig = $c
            $r = Invoke-CopieMoteurJea -Argument @('--verifier', '--syntaxe-seule') -Fichier $f
            $r.Code | Should -BeIn 0, 4
            $r.Erreur | Should -Be ''
        }
    }
    It 'refuse une commande hors contrat sans lancer le moteur' {
        InModuleScope Copie.Jea -Parameters @{ c = $Script:Cfg; f = $Script:Fichier } {
            param($c, $f)
            $Script:CheminConfig = $c
            $r = Invoke-CopieMoteurJea -Argument @('--initialiser-base') -Fichier $f
            $r.Code | Should -Be -1
            $r.Sortie | Should -Be ''
        }
    }
}

Describe 'Installateur' {
    It 'se lit sans erreur et refuse un groupe mal écrit' {
        $script = Join-Path $PSScriptRoot '..\Installer-PointAccesJea.ps1'
        $erreurs = $null
        $null = [System.Management.Automation.Language.Parser]::ParseFile($script, [ref]$null, [ref]$erreurs)
        @($erreurs).Count | Should -Be 0
        { & $script -GroupeAdmin 'sansdomaine' -Python $env:ComSpec -Racine $Script:Racine -DossierParametrage $Script:Dossier -WhatIf } | Should -Throw '*DOMAINE*'
    }
    It 'ne touche à rien avec -WhatIf (et n''exige pas d''être administrateur)' {
        $script = Join-Path $PSScriptRoot '..\Installer-PointAccesJea.ps1'
        $null = & $script -Nom 'CopieFichiersTest' -GroupeAdmin 'DOM\G' -Python $env:ComSpec -Racine $Script:Racine -DossierParametrage $Script:Dossier -DossierTraces (Join-Path $TestDrive 'traces') -WhatIf 4>&1 5>&1 6>&1
        Test-Path (Join-Path $TestDrive 'traces') | Should -BeFalse
    }
}
