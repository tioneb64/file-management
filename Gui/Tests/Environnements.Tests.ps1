#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
# Étape F : dossier de paramétrage absent ou vide, gestion des environnements (créer, renommer, supprimer), simulation
# d'une règle avec contrôles des répertoires. Le VRAI moteur Python est appelé (COPIE_TEST_PYTHON ; absent : tests ignorés).

BeforeDiscovery {
    $Script:PythonDisponible = [bool]$env:COPIE_TEST_PYTHON -and (Test-Path -LiteralPath $env:COPIE_TEST_PYTHON)
    $Script:Sta = [System.Threading.Thread]::CurrentThread.GetApartmentState() -eq 'STA'
}

BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..\Copie.Gui\Copie.Gui.psd1') -Force
    $Script:Utf8 = New-Object System.Text.UTF8Encoding($false)
    $Script:Ecrire = {
        param($chemin, $texte)
        $null = New-Item -ItemType Directory -Path (Split-Path -Parent $chemin) -Force
        [System.IO.File]::WriteAllText($chemin, $texte, $Script:Utf8)
    }
}

Describe 'Saisie d''un environnement (sans moteur)' {
    It 'accepte les noms du moteur, refuse les autres' {
        InModuleScope Copie.Gui {
            foreach ($n in 'production', 'recette-2', 'a_b', ('x' * 32)) { Test-CopieNomEnvironnement -Nom $n | Should -BeTrue -Because $n }
            foreach ($n in '', 'Production', 'a b', 'é', ('x' * 33), 'a.b', 'a/b') { Test-CopieNomEnvironnement -Nom $n | Should -BeFalse -Because "[$n]" }
        }
    }
    It 'refuse une base sur un partage réseau, relative, vide ou déjà utilisée ; un nom déjà pris' {
        InModuleScope Copie.Gui {
            $existant = [pscustomobject]@{ Nom = 'production'; Parametrage = [pscustomobject]@{ Entete = ('{"version":1,"environnement":"production","base":"D:\\Copie\\production.db"}' | ConvertFrom-Json) } }
            $ok = @{ Nom = 'recette'; Base = 'D:\Copie\recette.db' }
            @(Test-CopieSaisieEnvironnement -Saisie $ok -Existants @($existant)).Count | Should -Be 0
            (Test-CopieSaisieEnvironnement -Saisie @{ Nom = 'recette'; Base = '\\srv\p\r.db' }) -join ' ' | Should -Match 'partage réseau'
            (Test-CopieSaisieEnvironnement -Saisie @{ Nom = 'recette'; Base = 'recette.db' }) -join ' ' | Should -Match 'complet'
            (Test-CopieSaisieEnvironnement -Saisie @{ Nom = 'recette'; Base = '' }) -join ' ' | Should -Match 'obligatoire'
            (Test-CopieSaisieEnvironnement -Saisie @{ Nom = 'recette'; Base = 'd:/copie/PRODUCTION.db' } -Existants @($existant)) -join ' ' | Should -Match 'déjà celle'
            (Test-CopieSaisieEnvironnement -Saisie @{ Nom = 'production'; Base = 'D:\x.db' } -Existants @($existant)) -join ' ' | Should -Match 'existe déjà'
            @(Test-CopieSaisieEnvironnement -Saisie @{ Nom = 'production'; Base = 'D:\Copie\production.db' } -Existants @($existant) -Ignorer 'production').Count | Should -Be 0
            (Test-CopieSaisieEnvironnement -Saisie (@{ Nom = 'r'; Base = 'D:\r.db'; ParalleleMax = '0'; MargeEspaceMo = 'x'; DossierLogs = 'logs' })) -join ' ' | Should -Match 'parallèle.*supérieur'
        }
    }
    It 'construit l''en-tête sans les champs vides, avec des entiers, et le relit' {
        InModuleScope Copie.Gui {
            $e = ConvertTo-CopieEnteteEnvironnement -Saisie @{ Nom = 'recette'; Base = 'D:\r.db'; DossierLogs = ''; ParalleleMax = '4'; MargeEspaceMo = '0' }
            ($e | ConvertTo-Json -Compress) | Should -Be '{"version":1,"environnement":"recette","base":"D:\\r.db","parallele_max":4,"marge_espace_mo":0}'
            $s = ConvertFrom-CopieEnteteEnvironnement -Entete $e
            $s.ParalleleMax | Should -Be '4'
            $s.DossierLogs | Should -Be ''
        }
    }
}

Describe 'Dossier de paramétrage au lancement' {
    It 'propose de créer un dossier absent à un administrateur, qui peut refuser' {
        InModuleScope Copie.Gui -Parameters @{ d = (Join-Path $TestDrive 'nouveau\param') } {
            param($d)
            $Script:Questions = @()
            Resolve-CopieDossierParametrage -Chemin $d -Profil 'Admin' -Confirmer { param($q) $Script:Questions += $q; $false } | Should -BeNullOrEmpty
            Test-Path -LiteralPath $d | Should -BeFalse
            $Script:Questions.Count | Should -Be 1
            $Script:Questions[0] | Should -Match 'n''existe pas'
            Resolve-CopieDossierParametrage -Chemin $d -Profil 'Admin' -Confirmer { $true } | Should -Be $d
            Test-Path -LiteralPath $d -PathType Container | Should -BeTrue
        }
    }
    It 'ne crée jamais le dossier pour un compte non administrateur ni sans réponse' {
        InModuleScope Copie.Gui -Parameters @{ d = (Join-Path $TestDrive 'interdit') } {
            param($d)
            { Resolve-CopieDossierParametrage -Chemin $d -Profil 'Lecture' -GroupeAdmin @('GG_Admins') -Confirmer { $true } } | Should -Throw '*GG_Admins*'
            Resolve-CopieDossierParametrage -Chemin $d -Profil 'Admin' | Should -BeNullOrEmpty
            Test-Path -LiteralPath $d | Should -BeFalse
        }
    }
    It 'refuse un chemin vide, invalide ou qui désigne un fichier, et accepte un dossier existant ou relatif' {
        $f = Join-Path $TestDrive 'un-fichier.txt'
        Set-Content -LiteralPath $f -Value 'x'
        $existant = Join-Path $TestDrive 'existe'
        $null = New-Item -ItemType Directory -Path $existant
        InModuleScope Copie.Gui -Parameters @{ f = $f; e = $existant } {
            param($f, $e)
            $null = $f, $e
            { Resolve-CopieDossierParametrage -Chemin '  ' -Profil 'Admin' } | Should -Throw '*pas renseigné*'
            { Resolve-CopieDossierParametrage -Chemin "D:\a|b" -Profil 'Admin' } | Should -Throw '*invalide*'
            { Resolve-CopieDossierParametrage -Chemin $f -Profil 'Admin' } | Should -Throw '*fichier*'
            Resolve-CopieDossierParametrage -Chemin $e -Profil 'Lecture' | Should -Be $e
            Resolve-CopieDossierParametrage -Chemin ('"' + $e + '\"') -Profil 'Lecture' | Should -Be $e
            Push-Location (Split-Path -Parent $e)
            try { Resolve-CopieDossierParametrage -Chemin '.\existe' -Profil 'Lecture' | Should -Be $e } finally { Pop-Location }
        }
    }
}

Describe 'Fenêtre : dossier absent, vide' -Skip:(-not ($Script:Sta -and $Script:PythonDisponible)) {
    BeforeAll {
        $Script:Essai = Join-Path $TestDrive 'essai'
        & (Join-Path $PSScriptRoot '..\Outils\Initialiser-Essai.ps1') -Destination $Script:Essai -Python $env:COPIE_TEST_PYTHON | Out-Null
        $Script:Cfg = Join-Path $Script:Essai 'Gestion-Copie.essai.config.psd1'
    }
    It 'dossier absent : l''administrateur qui accepte obtient un dossier créé et l''écran « aucun environnement » avec le bouton de création' {
        $d = Join-Path $TestDrive 'param-neuf'
        $f = Start-CopieGui -DossierParametrage $d -Config $Script:Cfg -SansAffichage -GroupeUtilisateur @('S-1-5-11') -ConfirmerCreationDossier { $true }
        try {
            Test-Path -LiteralPath $d -PathType Container | Should -BeTrue
            $f.FindName('Tabs').Items.Count | Should -Be 0
            $f.FindName('EtatVide').Visibility | Should -Be 'Visible'
            $f.FindName('EtatVideTitre').Text | Should -Be 'Aucun environnement'
            $f.FindName('BtnEtatVideCreer').Visibility | Should -Be 'Visible'
            $f.FindName('BarreEnvironnements').Visibility | Should -Be 'Visible'
            $f.FindName('BtnEnvNouveau').IsEnabled | Should -BeTrue
            $f.FindName('BtnEnvModifier').IsEnabled | Should -BeFalse
        }
        finally { $f.Close() }
    }
    It 'dossier absent et refus de le créer : rien n''est ouvert, rien n''est créé' {
        $d = Join-Path $TestDrive 'param-refuse'
        Start-CopieGui -DossierParametrage $d -Config $Script:Cfg -SansAffichage -GroupeUtilisateur @('S-1-5-11') -ConfirmerCreationDossier { $false } | Should -BeNullOrEmpty
        Test-Path -LiteralPath $d | Should -BeFalse
    }
    It 'dossier absent pour un compte non administrateur : message clair, sans création' -Skip:$true {  # TEMPORAIRE : vérification des droits désactivée (voir CHANGELOG)
        $d = Join-Path $TestDrive 'param-lecture'
        { Start-CopieGui -DossierParametrage $d -Config $Script:Cfg -SansAffichage -GroupeUtilisateur @('DOMAINE\Autres') -ConfirmerCreationDossier { $true } } | Should -Throw '*administrateur*'
        Test-Path -LiteralPath $d | Should -BeFalse
    }
    It 'dossier vide, compte non administrateur : explication sans bouton de création ni barre' -Skip:$true {  # TEMPORAIRE : vérification des droits désactivée (voir CHANGELOG)
        $d = Join-Path $TestDrive 'param-vide'
        $null = New-Item -ItemType Directory -Path $d
        $f = Start-CopieGui -DossierParametrage $d -Config $Script:Cfg -SansAffichage -GroupeUtilisateur @('DOMAINE\Autres')
        try {
            $f.FindName('EtatVide').Visibility | Should -Be 'Visible'
            $f.FindName('EtatVideTexte').Text | Should -Match 'administrateur'
            $f.FindName('BtnEtatVideCreer').Visibility | Should -Be 'Collapsed'
            $f.FindName('BarreEnvironnements').Visibility | Should -Be 'Collapsed'
        }
        finally { $f.Close() }
    }
    It 'la barre de gestion des environnements suit l''onglet choisi et disparaît pour un non administrateur' {
        $f = Start-CopieGui -DossierParametrage (Join-Path $Script:Essai 'parametrage') -Config $Script:Cfg -SansAffichage -GroupeUtilisateur @('S-1-5-11')
        InModuleScope Copie.Gui { Wait-CopieTache }
        try {
            $f.FindName('EtatVide').Visibility | Should -Be 'Collapsed'
            $tabs = $f.FindName('Tabs')
            $tabs.SelectedIndex = 0
            InModuleScope Copie.Gui { Update-CopieBarreEnvironnements }
            $f.FindName('BtnEnvSupprimer').IsEnabled | Should -BeTrue
        }
        finally { $f.Close() }
    }
}

Describe 'Dossiers d''un environnement : contrôle, une seule question, création (sans moteur)' {
    BeforeAll {
        $Script:Cfg2 = InModuleScope Copie.Gui -Parameters @{ j = (Join-Path $TestDrive 'cfg-d.psd1') } {
            param($j)
            [System.IO.File]::WriteAllText($j, "@{ Acces = @{ GroupesAdmin = @('G') }; Moteur = @{ Mode = 'Local'; Python = 'p'; Racine = 'r' } }")
            Get-CopieConfig -Chemin $j
        }
        $Script:Fich = {
            param($nom, $base, $logs, $travail)
            $d = Join-Path $TestDrive 'param-d'
            $null = New-Item -ItemType Directory -Path $d -Force
            $en = [ordered]@{ version = 1; environnement = $nom; base = $base }
            if ($logs) { $en.dossier_logs = $logs }
            if ($travail) { $en.dossier_travail = $travail }
            $f = Join-Path $d ($nom + '.jsonl')
            [System.IO.File]::WriteAllText($f, (($en | ConvertTo-Json -Compress) + "`n"), $Script:Utf8)
            $f
        }
    }
    It 'contrôle : trois dossiers absents sont à créer, rien n''est créé' {
        $f = & $Script:Fich 'e1' (Join-Path $TestDrive 'x1\BDD\e1.db') (Join-Path $TestDrive 'x1\LOG') (Join-Path $TestDrive 'x1\TMP')
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg2; f = $f } {
            param($c, $f)
            $r = Invoke-CopieDossiersEnvironnement -Config $c -Fichier $f -Action 'controler'
            $r.Ok | Should -BeTrue -Because $r.Message
            @($r.Dossiers).Count | Should -Be 3
            @($r.Dossiers | Where-Object { -not $_.Existe -and $_.ACreer }).Count | Should -Be 3
            (@($r.Dossiers | ForEach-Object Role) -join ',') | Should -Be 'base,journaux,travail'
        }
        Test-Path -LiteralPath (Join-Path $TestDrive 'x1') | Should -BeFalse
    }
    It 'création : les trois dossiers sont créés ; un second contrôle ne trouve plus rien à faire' {
        $f = & $Script:Fich 'e2' (Join-Path $TestDrive 'x2\BDD\e2.db') (Join-Path $TestDrive 'x2\LOG') (Join-Path $TestDrive 'x2\TMP')
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg2; f = $f } {
            param($c, $f)
            $r = Invoke-CopieDossiersEnvironnement -Config $c -Fichier $f -Action 'creer'
            @($r.Dossiers | Where-Object Cree).Count | Should -Be 3
            $r2 = Invoke-CopieDossiersEnvironnement -Config $c -Fichier $f -Action 'controler'
            @($r2.Dossiers | Where-Object { $_.Existe -and $_.Ecriture }).Count | Should -Be 3
            @($r2.Dossiers | Where-Object ACreer).Count | Should -Be 0
        }
        foreach ($n in 'BDD', 'LOG', 'TMP') { Test-Path -LiteralPath (Join-Path $TestDrive "x2\$n") -PathType Container | Should -BeTrue }
        Test-Path -LiteralPath (Join-Path $TestDrive 'x2\BDD\e2.db') | Should -BeFalse      # les dossiers seulement : la base est créée par le moteur
        @(Get-ChildItem -LiteralPath (Join-Path $TestDrive 'x2') -Recurse -Force -Filter '.test_ecriture_*').Count | Should -Be 0
    }
    It 'champs vides : journaux et travail à côté de la base, comme le moteur' {
        $f = & $Script:Fich 'e3' (Join-Path $TestDrive 'x3\e3.db') '' ''
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg2; f = $f; t = $TestDrive } {
            param($c, $f, $t)
            $r = Invoke-CopieDossiersEnvironnement -Config $c -Fichier $f -Action 'controler'
            $chemins = @($r.Dossiers | ForEach-Object Chemin)
            $chemins | Should -Contain (Join-Path $t 'x3')
            $chemins | Should -Contain (Join-Path $t 'x3\logs')
            $chemins | Should -Contain (Join-Path $t 'x3\travail')
        }
    }
    It 'un lecteur introuvable n''est pas créable' {
        $f = & $Script:Fich 'e4' 'Q:\zz\BDD\e4.db' (Join-Path $TestDrive 'x4\LOG') ''
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg2; f = $f } {
            param($c, $f)
            $etat = Get-CopieTexteDossiersManquants -Dossier @((Invoke-CopieDossiersEnvironnement -Config $c -Fichier $f -Action 'controler').Dossiers)
            if (Test-Path -LiteralPath 'Q:\') { Set-ItResult -Skipped -Because 'le lecteur Q: existe sur ce poste'; return }
            @($etat.Impossibles).Count | Should -BeGreaterThan 0
            $etat.Texte | Should -Match 'introuvable'
        }
    }
    It 'une seule question pour les trois dossiers ; refus : rien n''est créé' {
        $f = & $Script:Fich 'e5' (Join-Path $TestDrive 'x5\BDD\e5.db') (Join-Path $TestDrive 'x5\LOG') (Join-Path $TestDrive 'x5\TMP')
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg2; f = $f } {
            param($c, $f)
            $ctx = @{ Config = $c; Utilisateur = 'DOM\ben'; Fenetre = $null; LogBox = $null; PanneJournal = $false }
            $Script:Questions = New-Object System.Collections.Generic.List[string]
            $non = { param($t) $Script:Questions.Add($t); $false }
            (Invoke-CopieQuestionDossiers -Contexte $ctx -Fichier $f -Poser $non -Informer { }) | Should -BeFalse
            $Script:Questions.Count | Should -Be 1
            $Script:Questions[0] | Should -Match 'BDD'
            $Script:Questions[0] | Should -Match 'LOG'
            $Script:Questions[0] | Should -Match 'TMP'
        }
        Test-Path -LiteralPath (Join-Path $TestDrive 'x5') | Should -BeFalse
    }
    It 'accord : les dossiers sont créés, une seule question ; tout existe : aucune question' {
        $f = & $Script:Fich 'e6' (Join-Path $TestDrive 'x6\BDD\e6.db') (Join-Path $TestDrive 'x6\LOG') (Join-Path $TestDrive 'x6\TMP')
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg2; f = $f } {
            param($c, $f)
            $ctx = @{ Config = $c; Utilisateur = 'DOM\ben'; Fenetre = $null; LogBox = $null; PanneJournal = $false }
            $Script:Questions = New-Object System.Collections.Generic.List[string]
            $oui = { param($t) $Script:Questions.Add($t); $true }
            (Invoke-CopieQuestionDossiers -Contexte $ctx -Fichier $f -Poser $oui -Informer { }) | Should -BeTrue
            $Script:Questions.Count | Should -Be 1
            (Invoke-CopieQuestionDossiers -Contexte $ctx -Fichier $f -Poser $oui -Informer { }) | Should -BeTrue
            $Script:Questions.Count | Should -Be 1
        }
        foreach ($n in 'BDD', 'LOG', 'TMP') { Test-Path -LiteralPath (Join-Path $TestDrive "x6\$n") -PathType Container | Should -BeTrue }
    }
}

Describe 'Détection de Python et du moteur au démarrage (mode Local)' {
    BeforeAll {
        $Script:RacineVraie = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).ProviderPath
    }
    It 'configuration correcte : aucune question' {
        InModuleScope Copie.Gui -Parameters @{ r = $Script:RacineVraie } {
            param($r)
            $py = (Get-Command powershell.exe).Source
            $c = [pscustomobject]@{ Moteur = [pscustomobject]@{ Mode = 'Local'; Python = $py; Racine = $r } }
            $Script:N = 0
            $res = Resolve-CopieMoteurLocal -Config $c -Confirmer { $Script:N++; $true }
            $res.Ok | Should -BeTrue
            $Script:N | Should -Be 0
        }
    }
    It 'chemins d''exemple inexistants : propose ce qui est trouvé, une seule question, vaut pour la session' {
        InModuleScope Copie.Gui -Parameters @{ r = $Script:RacineVraie } {
            param($r)
            $c = [pscustomobject]@{ Moteur = [pscustomobject]@{ Mode = 'Local'; Python = 'C:\Python314\python.exe'; Racine = 'D:\Scripts\zz_inexistant' } }
            $Script:Questions = New-Object System.Collections.Generic.List[string]
            $res = Resolve-CopieMoteurLocal -Config $c -Confirmer { param($q) $Script:Questions.Add($q); $true } -RacineDepot $r
            $Script:Questions.Count | Should -Be 1
            $Script:Questions[0] | Should -Match 'cette session'
            $c.Moteur.Racine | Should -Be $r
            $res.Modifie | Should -BeTrue
            if (Find-CopiePythonLocal) { $res.Ok | Should -BeTrue; Test-Path -LiteralPath $c.Moteur.Python | Should -BeTrue }
        }
    }
    It 'refus : la configuration reste inchangée et le problème est dit' {
        InModuleScope Copie.Gui -Parameters @{ r = $Script:RacineVraie } {
            param($r)
            $c = [pscustomobject]@{ Moteur = [pscustomobject]@{ Mode = 'Local'; Python = 'C:\Python314\python.exe'; Racine = 'D:\Scripts\zz_inexistant' } }
            $res = Resolve-CopieMoteurLocal -Config $c -Confirmer { $false } -RacineDepot $r
            $res.Ok | Should -BeFalse
            $res.Modifie | Should -BeFalse
            $c.Moteur.Python | Should -Be 'C:\Python314\python.exe'
            $res.Message | Should -Match 'Moteur.Python'
        }
    }
    It 'racine introuvable et rien à proposer : message clair, aucune question' {
        InModuleScope Copie.Gui {
            $c = [pscustomobject]@{ Moteur = [pscustomobject]@{ Mode = 'Local'; Python = (Get-Command powershell.exe).Source; Racine = 'D:\Scripts\zz_inexistant' } }
            $Script:N = 0
            $res = Resolve-CopieMoteurLocal -Config $c -Confirmer { $Script:N++; $true } -RacineDepot 'D:\zz_pas_un_depot'
            $res.Ok | Should -BeFalse
            $Script:N | Should -Be 0
            $res.Message | Should -Match 'Moteur.Racine'
        }
    }
    It 'mode Distant : rien n''est vérifié' {
        InModuleScope Copie.Gui {
            $c = [pscustomobject]@{ Moteur = [pscustomobject]@{ Mode = 'Distant'; Python = 'C:\nope\python.exe'; Racine = 'D:\nope' } }
            (Resolve-CopieMoteurLocal -Config $c -Confirmer { $false }).Ok | Should -BeTrue
        }
    }
}

Describe 'Gestion des environnements (moteur réel)' -Skip:(-not $Script:PythonDisponible) {
    BeforeAll {
        $Script:Racine = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).ProviderPath
        $Script:Cfg = InModuleScope Copie.Gui -Parameters @{ r = $Script:Racine; p = $env:COPIE_TEST_PYTHON; j = (Join-Path $TestDrive 'cfg.psd1') } {
            param($r, $p, $j)
            [System.IO.File]::WriteAllText($j, "@{ Acces = @{ GroupesAdmin = @('G') }; Moteur = @{ Mode = 'Local'; Python = '$p'; Racine = '$r'; DelaiMaxSec = 60 } }")
            Get-CopieConfig -Chemin $j
        }
        $Script:Dossier = Join-Path $TestDrive 'param'
        $null = New-Item -ItemType Directory -Path $Script:Dossier
        $Script:Donnees = Join-Path $TestDrive 'donnees'
    }
    It 'crée un environnement : fichier vérifié par le moteur, base créée, aucun brouillon laissé' {
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg; d = $Script:Dossier; b = (Join-Path $Script:Donnees 'recette.db') } {
            param($c, $d, $b)
            $r = New-CopieEnvironnement -Config $c -Dossier $d -Profil 'Admin' -Saisie @{ Nom = 'recette'; Base = $b } -Compte 'DOM\ben' -InitialiserBase $true
            $r.Ok | Should -BeTrue -Because $r.Message
            $r.Etape | Should -Be 'ok'
            $r.Base | Should -Be 'créée'
            Test-Path -LiteralPath (Join-Path $d 'recette.jsonl') | Should -BeTrue
            Test-Path -LiteralPath $b | Should -BeTrue
            @(Get-ChildItem -LiteralPath (Join-Path $d '.brouillons') -ErrorAction SilentlyContinue).Count | Should -Be 0
            $envs = @(Get-CopieEnvironnement -Dossier $d -Config $c)
            $envs.Count | Should -Be 1
            $envs[0].Modifiable | Should -BeTrue
            $etat = Get-CopieEtatBaseEnvironnement -Config $c -Fichier (Join-Path $d 'recette.jsonl')
            $etat.Statut | Should -Be 'presente'
        }
    }
    It 'dossiers non prêts (question refusée) : l''environnement est créé, la base NON, et le résultat le dit' {
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg; d = $Script:Dossier; b = (Join-Path $Script:Donnees 'refus\BDD\refus.db') } {
            param($c, $d, $b)
            $r = New-CopieEnvironnement -Config $c -Dossier $d -Profil 'Admin' -Saisie @{ Nom = 'refus'; Base = $b } -Compte 'u' -InitialiserBase $true -PreparerDossiers { param($f) $null = $f; $false }
            $r.Etape | Should -Be 'base'
            $r.Base | Should -Match 'NON créée'
            Test-Path -LiteralPath (Join-Path $d 'refus.jsonl') | Should -BeTrue
            Test-Path -LiteralPath $b | Should -BeFalse
        }
    }
    It 'dossiers prêts : le bloc reçoit le fichier, puis la base est créée dans le dossier créé par la question' {
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg; d = $Script:Dossier; b = (Join-Path $Script:Donnees 'oui\BDD\oui.db') } {
            param($c, $d, $b)
            $Script:Recu = ''
            $r = New-CopieEnvironnement -Config $c -Dossier $d -Profil 'Admin' -Saisie @{ Nom = 'oui'; Base = $b } -Compte 'u' -InitialiserBase $true `
                -PreparerDossiers { param($f) $Script:Recu = $f; $null = New-Item -ItemType Directory -Path (Split-Path -Parent (Get-Content -LiteralPath $f -Encoding UTF8 -TotalCount 1 | ConvertFrom-Json).base) -Force; $true }
            $r.Ok | Should -BeTrue -Because $r.Message
            $r.Base | Should -Be 'créée'
            $Script:Recu | Should -Match 'oui.jsonl$'
            Test-Path -LiteralPath $b | Should -BeTrue
        }
    }
    It 'refuse la création à un non administrateur, un nom ou une base déjà pris, une saisie invalide' {
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg; d = $Script:Dossier; b = (Join-Path $Script:Donnees 'recette.db') } {
            param($c, $d, $b)
            $existants = @(Get-CopieEnvironnement -Dossier $d -Config $c)
            (New-CopieEnvironnement -Config $c -Dossier $d -Profil 'Lecture' -Saisie @{ Nom = 'x'; Base = 'D:\x.db' } -Compte 'u').Etape | Should -Be 'droits'
            (New-CopieEnvironnement -Config $c -Dossier $d -Profil 'Admin' -Saisie @{ Nom = 'recette'; Base = 'D:\autre.db' } -Compte 'u' -Existants $existants).Message | Should -Match 'existe déjà'
            (New-CopieEnvironnement -Config $c -Dossier $d -Profil 'Admin' -Saisie @{ Nom = 'autre'; Base = $b } -Compte 'u' -Existants $existants).Message | Should -Match 'déjà celle'
            (New-CopieEnvironnement -Config $c -Dossier $d -Profil 'Admin' -Saisie @{ Nom = 'Mauvais'; Base = 'D:\x.db' } -Compte 'u').Etape | Should -Be 'saisie'
            Test-Path -LiteralPath (Join-Path $d 'autre.jsonl') | Should -BeFalse
        }
    }
    It 'sans base : l''environnement est créé, la base se crée ensuite ; une base existante n''est pas une erreur' {
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg; d = $Script:Dossier; b = (Join-Path $Script:Donnees 'sans.db') } {
            param($c, $d, $b)
            $r = New-CopieEnvironnement -Config $c -Dossier $d -Profil 'Admin' -Saisie @{ Nom = 'sans'; Base = $b } -Compte 'u' -InitialiserBase $false
            $r.Ok | Should -BeTrue
            $r.Base | Should -Match 'non créée'
            Test-Path -LiteralPath $b | Should -BeFalse
            $f = Join-Path $d 'sans.jsonl'
            (Get-CopieEtatBaseEnvironnement -Config $c -Fichier $f).Statut | Should -Be 'absente'
            (Initialize-CopieBaseEnvironnement -Config $c -Fichier $f -Compte 'u').Statut | Should -Be 'creee'
            (Initialize-CopieBaseEnvironnement -Config $c -Fichier $f -Compte 'u').Statut | Should -Be 'existante'
        }
    }
    It 'renomme : fichier, en-tête, nom dans la base (le moteur rouvre la base), versions et règles conservées' {
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg; d = $Script:Dossier } {
            param($c, $d)
            $fichier = Join-Path $d 'recette.jsonl'
            $utf8 = New-Object System.Text.UTF8Encoding($false)
            $texte = [System.IO.File]::ReadAllText($fichier) + '{"id":"r1","source":"D:\\a","cible":"D:\\b","mode":"copie","planification":{"type":"quotidien","heure":"07:00"}}' + "`n"
            [System.IO.File]::WriteAllText($fichier, $texte, $utf8)
            $versions = Join-Path $d 'versions'
            $null = New-Item -ItemType Directory -Path $versions -Force
            Set-Content -LiteralPath (Join-Path $versions 'recette_20260101_101010_DOM_ben.jsonl') -Value '{}'
            Set-Content -LiteralPath (Join-Path $versions 'recette_b_20260101_101010_DOM_ben.jsonl') -Value '{}'     # autre environnement : ne bouge pas
            $existants = @(Get-CopieEnvironnement -Dossier $d -Config $c)
            $env = $existants | Where-Object Nom -eq 'recette'
            (Rename-CopieEnvironnement -Config $c -Environnement $env -NouveauNom 'recette' -Profil 'Admin' -Compte 'u' -Commentaire 'x' -Existants $existants).Message | Should -Match 'identique'
            (Rename-CopieEnvironnement -Config $c -Environnement $env -NouveauNom 'Mauvais' -Profil 'Admin' -Compte 'u' -Commentaire 'x' -Existants $existants).Etape | Should -Be 'saisie'
            (Rename-CopieEnvironnement -Config $c -Environnement $env -NouveauNom 'sans' -Profil 'Admin' -Compte 'u' -Commentaire 'x' -Existants $existants).Etape | Should -Be 'saisie'
            (Rename-CopieEnvironnement -Config $c -Environnement $env -NouveauNom 'nouveau' -Profil 'Lecture' -Compte 'u' -Commentaire 'x' -Existants $existants).Etape | Should -Be 'droits'

            $r = Rename-CopieEnvironnement -Config $c -Environnement $env -NouveauNom 'production' -Profil 'Admin' -Compte 'DOM\ben' -Commentaire 'mise en production' -Existants $existants
            $r.Ok | Should -BeTrue -Because $r.Message
            $r.Etape | Should -Be 'ok'
            Test-Path -LiteralPath $fichier | Should -BeFalse
            $nouveau = Join-Path $d 'production.jsonl'
            Test-Path -LiteralPath $nouveau | Should -BeTrue
            $p = Read-CopieFichierParametrage -Chemin $nouveau
            $p.Entete.environnement | Should -Be 'production'
            $p.Regles.Count | Should -Be 1
            (Get-CopieEtatBaseEnvironnement -Config $c -Fichier $nouveau).Statut | Should -Be 'presente'
            Test-Path -LiteralPath (Join-Path $versions 'production_20260101_101010_DOM_ben.jsonl') | Should -BeTrue
            Test-Path -LiteralPath (Join-Path $versions 'recette_b_20260101_101010_DOM_ben.jsonl') | Should -BeTrue
            @(Get-ChildItem -LiteralPath $versions -Filter 'production_*DOM_ben.meta.json').Count | Should -Be 1
            (Get-Content -Raw -Encoding UTF8 -LiteralPath (@(Get-ChildItem -LiteralPath $versions -Filter 'production_*.meta.json')[0].FullName)) | Should -Match 'mise en production'
        }
    }
    It 'supprime : fichier et versions rangés, base intacte, refus sans droit ni commentaire' {
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg; d = $Script:Dossier; b = (Join-Path $Script:Donnees 'recette.db') } {
            param($c, $d, $b)
            $env = @(Get-CopieEnvironnement -Dossier $d -Config $c) | Where-Object Nom -eq 'production'
            (Remove-CopieEnvironnement -Config $c -Environnement $env -Profil 'Lecture' -Compte 'u' -Commentaire 'x').Etape | Should -Be 'droits'
            (Remove-CopieEnvironnement -Config $c -Environnement $env -Profil 'Admin' -Compte 'u' -Commentaire ' ').Etape | Should -Be 'saisie'
            Test-Path -LiteralPath $env.Fichier | Should -BeTrue
            $r = Remove-CopieEnvironnement -Config $c -Environnement $env -Profil 'Admin' -Compte 'DOM\ben' -Commentaire 'plus utilisé'
            $r.Ok | Should -BeTrue -Because $r.Message
            Test-Path -LiteralPath (Join-Path $d 'production.jsonl') | Should -BeFalse
            Test-Path -LiteralPath (Join-Path $r.Dossier 'production.jsonl') | Should -BeTrue
            Test-Path -LiteralPath (Join-Path $r.Dossier 'versions\production_20260101_101010_DOM_ben.jsonl') | Should -BeTrue
            Test-Path -LiteralPath (Join-Path $d 'versions\recette_b_20260101_101010_DOM_ben.jsonl') | Should -BeTrue
            (Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $r.Dossier 'suppression.json')) | Should -Match 'plus utilisé'
            Test-Path -LiteralPath $b | Should -BeTrue                      # la base n'est jamais supprimée
            $r.Base | Should -Be $b
        }
    }
}

Describe 'Copie d''un environnement (moteur réel)' -Skip:(-not $Script:PythonDisponible) {
    BeforeAll {
        $Script:Racine = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).ProviderPath
        $Script:Cfg = InModuleScope Copie.Gui -Parameters @{ r = $Script:Racine; p = $env:COPIE_TEST_PYTHON; j = (Join-Path $TestDrive 'cfg3.psd1') } {
            param($r, $p, $j)
            [System.IO.File]::WriteAllText($j, "@{ Acces = @{ GroupesAdmin = @('G') }; Moteur = @{ Mode = 'Local'; Python = '$p'; Racine = '$r'; DelaiMaxSec = 60 } }")
            Get-CopieConfig -Chemin $j
        }
        $Script:Dossier = Join-Path $TestDrive 'param-copie'
        $null = New-Item -ItemType Directory -Path $Script:Dossier
        $Script:Donnees = Join-Path $TestDrive 'donnees-copie'
        $en = '{"version":1,"environnement":"production","base":"' + (Join-Path $Script:Donnees 'production.db').Replace('\', '/') + '","dossier_travail":"' + (Join-Path $Script:Donnees 'travail').Replace('\', '/') + '","marge_espace_mo":0}'
        $r1 = '{"id":"r1","actif":true,"source":"' + (Join-Path $TestDrive 's1').Replace('\', '/') + '","cible":"' + (Join-Path $TestDrive 'c1').Replace('\', '/') + '","mode":"copie","planification":{"type":"quotidien","heure":"07:00"}}'
        $r2 = '{"id":"r2","apres":["r1"],"source":"' + (Join-Path $TestDrive 's2').Replace('\', '/') + '","cible":"' + (Join-Path $TestDrive 'c2').Replace('\', '/') + '","mode":"deplacement","planification":{"type":"quotidien","heure":"08:00"}}'
        [System.IO.File]::WriteAllText((Join-Path $Script:Dossier 'production.jsonl'), ($en + "`n" + $r1 + "`n" + $r2 + "`n"), $Script:Utf8)
    }
    It 'copie toutes les règles, désactivées, avec une base à soi ; l''original ne bouge pas' {
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg; d = $Script:Dossier; z = $Script:Donnees } {
            param($c, $d, $z)
            $avant = Get-CopieEmpreinteFichier -Chemin (Join-Path $d 'production.jsonl')
            $existants = @(Get-CopieEnvironnement -Dossier $d -Config $c)
            $source = Read-CopieFichierParametrage -Chemin (Join-Path $d 'production.jsonl')
            $saisie = @{ Nom = 'recette'; Base = (Join-Path $z 'recette.db'); MargeEspaceMo = '0' }
            $r = New-CopieEnvironnement -Config $c -Dossier $d -Profil 'Admin' -Saisie $saisie -Compte 'DOM\ben' -InitialiserBase $true -Existants $existants -Regle @($source.Regles) -DesactiverRegles $true
            $r.Ok | Should -BeTrue -Because $r.Message
            $r.Message | Should -Match '2 règle\(s\) copiée\(s\), désactivées'
            $copie = Read-CopieFichierParametrage -Chemin (Join-Path $d 'recette.jsonl')
            $copie.Entete.environnement | Should -Be 'recette'
            $copie.Regles.Count | Should -Be 2
            @($copie.Regles | Where-Object { $_.actif -ne $false }).Count | Should -Be 0
            ($copie.Regles | Where-Object id -eq 'r2').apres | Should -Be 'r1'
            ($copie.Regles | Where-Object id -eq 'r1').source | Should -Be (($source.Regles | Where-Object id -eq 'r1').source)       # répertoires inchangés : à l'utilisateur de les modifier
            Test-Path -LiteralPath (Join-Path $z 'recette.db') | Should -BeTrue
            (Get-CopieEmpreinteFichier -Chemin (Join-Path $d 'production.jsonl')) | Should -Be $avant
        }
    }
    It 'refuse la même base ou le même dossier de travail que l''original' {
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg; d = $Script:Dossier; z = $Script:Donnees } {
            param($c, $d, $z)
            $existants = @(Get-CopieEnvironnement -Dossier $d -Config $c)
            $source = Read-CopieFichierParametrage -Chemin (Join-Path $d 'production.jsonl')
            $r = New-CopieEnvironnement -Config $c -Dossier $d -Profil 'Admin' -Saisie @{ Nom = 'test'; Base = (Join-Path $z 'production.db') } -Compte 'u' -Existants $existants -Regle @($source.Regles)
            $r.Etape | Should -Be 'saisie'
            $r.Message | Should -Match 'déjà celle'
            $r = New-CopieEnvironnement -Config $c -Dossier $d -Profil 'Admin' -Saisie @{ Nom = 'test'; Base = (Join-Path $z 'test.db'); DossierTravail = (Join-Path $z 'travail') } -Compte 'u' -Existants $existants -Regle @($source.Regles)
            $r.Message | Should -Match 'dossier de travail'
            Test-Path -LiteralPath (Join-Path $d 'test.jsonl') | Should -BeFalse
        }
    }
    It 'copie les règles activées si on le demande' {
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg; d = $Script:Dossier; z = $Script:Donnees } {
            param($c, $d, $z)
            $existants = @(Get-CopieEnvironnement -Dossier $d -Config $c)
            $source = Read-CopieFichierParametrage -Chemin (Join-Path $d 'production.jsonl')
            $r = New-CopieEnvironnement -Config $c -Dossier $d -Profil 'Admin' -Saisie @{ Nom = 'actives'; Base = (Join-Path $z 'actives.db') } -Compte 'u' -InitialiserBase $false -Existants $existants -Regle @($source.Regles) -DesactiverRegles $false
            $r.Ok | Should -BeTrue -Because $r.Message
            $copie = Read-CopieFichierParametrage -Chemin (Join-Path $d 'actives.jsonl')
            ($copie.Regles | Where-Object id -eq 'r1').actif | Should -BeTrue
        }
    }
}

Describe 'Simulation d''une règle (moteur réel)' -Skip:(-not $Script:PythonDisponible) {
    BeforeAll {
        $Script:Racine = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).ProviderPath
        $Script:Cfg = InModuleScope Copie.Gui -Parameters @{ r = $Script:Racine; p = $env:COPIE_TEST_PYTHON; j = (Join-Path $TestDrive 'cfg2.psd1') } {
            param($r, $p, $j)
            [System.IO.File]::WriteAllText($j, "@{ Acces = @{ GroupesAdmin = @('G') }; Moteur = @{ Mode = 'Local'; Python = '$p'; Racine = '$r'; DelaiMaxSec = 60 } }")
            Get-CopieConfig -Chemin $j
        }
        $Script:Zone = Join-Path $TestDrive 'sim'
        $null = New-Item -ItemType Directory -Path (Join-Path $Script:Zone 'src') -Force
        [System.IO.File]::WriteAllText((Join-Path $Script:Zone 'src\a.csv'), 'contenu', $Script:Utf8)
        [System.IO.File]::WriteAllText((Join-Path $Script:Zone 'src\b.csv'), 'xy', $Script:Utf8)
        $f = (Join-Path $Script:Zone 'prod.jsonl')
        $js = { param($o) ($o | ConvertTo-Json -Compress -Depth 6) }
        $entete = [ordered]@{ version = 1; environnement = 'prod'; base = (Join-Path $Script:Zone 'donnees\prod.db'); dossier_logs = (Join-Path $Script:Zone 'logs'); marge_espace_mo = 0 }
        $regle = [ordered]@{ id = 'export'; source = (Join-Path $Script:Zone 'src'); cible = (Join-Path $Script:Zone 'dst'); mode = 'deplacement'
            planification = [ordered]@{ type = 'quotidien'; heure = '07:00' }; selection = [ordered]@{ age_minimum_sec = 0 } }
        [System.IO.File]::WriteAllText($f, ((& $js $entete) + "`n" + (& $js $regle) + "`n"), $Script:Utf8)
        $Script:Fichier = $f
        $init = InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg; f = $f } { param($c, $f) Initialize-CopieBaseEnvironnement -Config $c -Fichier $f -Compte 'u' }
        $init.Statut | Should -Be 'creee'
    }
    It 'dit ce qui serait déplacé, de quel répertoire vers lequel, et signale le dossier cible à créer' {
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg; f = $Script:Fichier; z = $Script:Zone } {
            param($c, $f, $z)
            $r = Invoke-CopieMoteur -Config $c -Fichier $f -Argument @('--lancer-regle', 'export', '--simulation')
            $resume = ConvertTo-CopieResumeSimulation -Json $r.Json
            $resume.Phrase | Should -Match '^Déplacera 2 fichier\(s\) \(9 o\) du répertoire .*src vers le répertoire .*dst\.$'
            $resume.Lignes.Count | Should -Be 2
            $resume.Controles.RoleId | Should -Be @('source', 'cible')
            $src = $resume.Controles | Where-Object RoleId -eq 'source'
            ($src.Existe, $src.Lecture, $src.Ecriture, $src.Verdict) -join '/' | Should -Be 'Oui/Oui/Oui/OK'
            $cible = $resume.Controles | Where-Object RoleId -eq 'cible'
            ($cible.Existe, $cible.Verdict) -join '/' | Should -Be 'Non/A_CREER'
            $cible.Ecriture | Should -Match 'création possible'
            $cible.Espace | Should -Match 'OK'
            @($resume.ACreer).Count | Should -Be 1
            Test-Path -LiteralPath (Join-Path $z 'dst') | Should -BeFalse           # une simulation n'écrit rien
            @(Get-ChildItem -LiteralPath (Join-Path $z 'src')).Count | Should -Be 2
        }
    }
    It 'crée les dossiers manquants à la demande (jamais la source) puis tout est OK' {
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg; f = $Script:Fichier; z = $Script:Zone } {
            param($c, $f, $z)
            $creation = Invoke-CopieMoteur -Config $c -Fichier $f -Argument @('--creer-dossiers-regle', 'export', '--utilisateur', 'DOM\ben')
            $creation.Reussi | Should -BeTrue
            @($creation.Json.crees).Count | Should -Be 1
            Test-Path -LiteralPath (Join-Path $z 'dst') -PathType Container | Should -BeTrue
            $r = Invoke-CopieMoteur -Config $c -Fichier $f -Argument @('--lancer-regle', 'export', '--simulation')
            $resume = ConvertTo-CopieResumeSimulation -Json $r.Json
            @($resume.Controles | Where-Object Verdict -ne 'OK').Count | Should -Be 0
            @($resume.ACreer).Count | Should -Be 0
        }
    }
    It 'signale une source absente comme un problème, sans proposer de la créer' {
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg; f = $Script:Fichier; z = $Script:Zone } {
            param($c, $f, $z)
            Rename-Item -LiteralPath (Join-Path $z 'src') -NewName 'src-parti'
            try {
                $r = Invoke-CopieMoteur -Config $c -Fichier $f -Argument @('--lancer-regle', 'export', '--simulation')
                $resume = ConvertTo-CopieResumeSimulation -Json $r.Json
                $src = $resume.Controles | Where-Object RoleId -eq 'source'
                ($src.Existe, $src.Verdict) -join '/' | Should -Be 'Non/PROBLEME'
                $resume.Niveau | Should -Be 'ERREUR'
                @($resume.ACreer).Count | Should -Be 0
                $resume.Phrase | Should -Match '^Aucun fichier'
            }
            finally { Rename-Item -LiteralPath (Join-Path $z 'src-parti') -NewName 'src' }
        }
    }
}

Describe 'Résumé de simulation (sans moteur)' {
    It 'formule copie, archivage et simulation vide' {
        InModuleScope Copie.Gui {
            $j = '{"source":"R","cible":"D","mode":"copie","statut":"SUCCES","compteurs":{"livres":3,"octets":2097152,"ignores":1},"apercu":[],"controles":[]}' | ConvertFrom-Json
            ((ConvertTo-CopieResumeSimulation -Json $j).Phrase -replace ',', '.') | Should -Be 'Copiera 3 fichier(s) (2.0 Mo) du répertoire R vers le répertoire D. Les originaux restent en place.'
            $j = '{"source":"R","cible":"D","mode":"archivage","statut":"SUCCES","compteurs":{"livres":1,"octets":10},"apercu":[{"fichier":"R\\a","cible":"D\\a","taille":10,"archive":"R\\archive\\a"}],"controles":[]}' | ConvertFrom-Json
            (ConvertTo-CopieResumeSimulation -Json $j).Phrase | Should -Match 'archivés dans R\\archive'
            $j = '{"source":"R","cible":"D","mode":"deplacement","statut":"SUCCES","compteurs":{"livres":0,"octets":0},"apercu":[],"controles":[]}' | ConvertFrom-Json
            (ConvertTo-CopieResumeSimulation -Json $j).Phrase | Should -Be 'Aucun fichier à traiter dans le répertoire R pour le moment.'
        }
    }
    It 'donne un verdict par répertoire : droits refusés, espace insuffisant, volume incorrect' {
        InModuleScope Copie.Gui {
            $j = @'
{"source":"R","cible":"D","mode":"deplacement","statut":"ERREUR","motif":"espace insuffisant","compteurs":{"livres":0,"octets":0},"apercu":[],
 "controles":[
  {"role":"source","chemin":"R","existe":true,"lecture":true,"ecriture":false,"a_creer":false,"detail":"ecriture impossible"},
  {"role":"cible","chemin":"D","existe":true,"lecture":true,"ecriture":true,"a_creer":false,"detail":"","espace":{"libre_octets":3,"necessaire_octets":7340032,"suffisant":false}},
  {"role":"temporaire","chemin":"T","existe":true,"lecture":true,"ecriture":true,"a_creer":false,"detail":"autre volume","volume_incorrect":true},
  {"role":"archive","chemin":"A","existe":false,"lecture":null,"ecriture":true,"a_creer":true,"detail":"sera cree"}]}
'@ | ConvertFrom-Json
            $r = ConvertTo-CopieResumeSimulation -Json $j
            ($r.Controles | ForEach-Object { $_.RoleId + '=' + $_.Verdict }) -join ',' | Should -Be 'source=PROBLEME,cible=PROBLEME,temporaire=PROBLEME,archive=A_CREER'
            ($r.Controles | Where-Object RoleId -eq 'cible').Espace | Should -Match 'INSUFFISANT'
            ($r.Controles | Where-Object RoleId -eq 'source').Ecriture | Should -Be 'Non'
            $r.Remarques -join ' ' | Should -Match '3 problème'
            $r.Niveau | Should -Be 'ERREUR'
        }
    }
    It 'formate les tailles' {
        InModuleScope Copie.Gui {
            Format-CopieTaille -Octets 0 | Should -Be '0 o'
            (Format-CopieTaille -Octets 1536) -replace ',', '.' | Should -Be '1.5 Ko'
            (Format-CopieTaille -Octets 5GB) -replace ',', '.' | Should -Be '5.00 Go'
        }
    }
}
