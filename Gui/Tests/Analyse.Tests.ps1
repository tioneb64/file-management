#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
# Étape D : historique des versions, graphe des dépendances, promotion. La logique est testée sans fenêtre ;
# l'historique de bout en bout utilise le VRAI moteur (COPIE_TEST_PYTHON ; absent : ce test est ignoré).

BeforeDiscovery {
    $Script:PythonDisponible = [bool]$env:COPIE_TEST_PYTHON -and (Test-Path -LiteralPath $env:COPIE_TEST_PYTHON)
    $Script:Sta = ([System.Threading.Thread]::CurrentThread.GetApartmentState() -eq 'STA')
}

BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..\FileManagement.Gui\FileManagement.Gui.psd1') -Force
    $Script:RacineMoteur = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).ProviderPath
    $Script:Regles = {
        param($json)
        @($json | ForEach-Object { $_ | ConvertFrom-Json })
    }
}

Describe 'Graphe des dépendances' {
    It 'place chaque règle à droite de ses dépendances et ignore celles sans lien' {
        $g = InModuleScope FileManagement.Gui {
            $r = @('{"id":"c","apres":["a","b"]}', '{"id":"a"}', '{"id":"b"}', '{"id":"seule"}', '{"id":"d","apres":["c"]}') | ForEach-Object { $_ | ConvertFrom-Json }
            Get-CopieDispositionGraphe -Regle $r
        }
        ($g.Noeuds | Where-Object Id -eq 'a').Niveau | Should -Be 0
        ($g.Noeuds | Where-Object Id -eq 'c').Niveau | Should -Be 1
        ($g.Noeuds | Where-Object Id -eq 'd').Niveau | Should -Be 2
        ($g.Noeuds | Where-Object Id -eq 'seule') | Should -BeNullOrEmpty
        $g.SansLien | Should -Be 1
        @($g.Aretes).Count | Should -Be 3
        ($g.Aretes | Where-Object Vers -eq 'c' | ForEach-Object De | Sort-Object) -join ',' | Should -Be 'a,b'
        $g.Largeur | Should -BeGreaterThan 0
        $g.Hauteur | Should -BeGreaterThan 0
    }
    It 'ne place jamais deux nœuds au même endroit' {
        $g = InModuleScope FileManagement.Gui {
            $r = @('{"id":"a"}', '{"id":"b"}', '{"id":"c","apres":["a"]}', '{"id":"d","apres":["b"]}', '{"id":"e","apres":["a","b"]}') | ForEach-Object { $_ | ConvertFrom-Json }
            Get-CopieDispositionGraphe -Regle $r
        }
        @($g.Noeuds | ForEach-Object { '{0}/{1}' -f $_.X, $_.Y } | Sort-Object -Unique).Count | Should -Be @($g.Noeuds).Count
    }
    It 'tient compte de la casse des identifiants et signale les dépendances inconnues' {
        $g = InModuleScope FileManagement.Gui {
            $r = @('{"id":"Amont"}', '{"id":"aval","apres":["AMONT","fantome"]}') | ForEach-Object { $_ | ConvertFrom-Json }
            Get-CopieDispositionGraphe -Regle $r
        }
        @($g.Aretes).Count | Should -Be 1
        @($g.Manquantes).Count | Should -Be 1
        $g.Manquantes[0].Dependance | Should -Be 'fantome'
    }
    It 'ne boucle pas sur une dépendance circulaire ou vers soi-même' {
        $g = InModuleScope FileManagement.Gui {
            $r = @('{"id":"a","apres":["b"]}', '{"id":"b","apres":["a"]}', '{"id":"c","apres":["c"]}') | ForEach-Object { $_ | ConvertFrom-Json }
            Get-CopieDispositionGraphe -Regle $r
        }
        @($g.Noeuds).Count | Should -Be 2
    }
    It 'accepte une liste vide' {
        $g = InModuleScope FileManagement.Gui { Get-CopieDispositionGraphe -Regle @() }
        @($g.Noeuds).Count | Should -Be 0
        $g.Largeur | Should -Be 0
    }
}

Describe 'Comparaison de deux versions' {
    It 'rapproche les règles par identifiant et compare champ par champ' {
        $d = InModuleScope FileManagement.Gui {
            $e = '{"version":1,"environnement":"p","base":"D:\\a.db"}' | ConvertFrom-Json
            $e2 = '{"version":1,"environnement":"p","base":"D:\\b.db"}' | ConvertFrom-Json
            $avant = [pscustomobject]@{ Entete = $e; Regles = @(('{"id":"a","duree_max_sec":10,"selection":{"masque":"*"},"apres":["x"],"actif":true}' | ConvertFrom-Json), ('{"id":"sup","description":"à supprimer"}' | ConvertFrom-Json)) }
            $apres = [pscustomobject]@{ Entete = $e2; Regles = @(('{"id":"nouvelle","description":"neuve"}' | ConvertFrom-Json), ('{"id":"A","duree_max_sec":20,"selection":{"masque":"*.csv"},"apres":["x","y"],"actif":false}' | ConvertFrom-Json)) }
            Compare-CopieParametrage -Avant $avant -Apres $apres
        }
        ($d | Where-Object Changement -eq 'En-tête').Champ | Should -Be 'base'
        ($d | Where-Object Changement -eq 'Supprimée').Regle | Should -Be 'sup'
        ($d | Where-Object Changement -eq 'Ajoutée').Regle | Should -Be 'nouvelle'
        $m = @($d | Where-Object Changement -eq 'Modifiée')
        ($m | ForEach-Object Champ | Sort-Object) -join ',' | Should -Be 'actif,apres,duree_max_sec,selection.masque'
        ($m | Where-Object Champ -eq 'apres').Avant | Should -Be '["x"]'
        ($m | Where-Object Champ -eq 'apres').Apres | Should -Be '["x","y"]'
        ($m | Where-Object Champ -eq 'actif').Avant | Should -Be 'true'
    }
    It 'ne voit pas un simple déplacement de règle comme une modification' {
        $d = InModuleScope FileManagement.Gui {
            $e = '{"version":1,"environnement":"p"}' | ConvertFrom-Json
            $a = '{"id":"a","x":1}' | ConvertFrom-Json; $b = '{"id":"b","x":2}' | ConvertFrom-Json
            Add-Member -InputObject $a -NotePropertyName Ligne -NotePropertyValue 2
            Compare-CopieParametrage -Avant ([pscustomobject]@{ Entete = $e; Regles = @($a, $b) }) -Apres ([pscustomobject]@{ Entete = $e; Regles = @(($b | ConvertTo-Json | ConvertFrom-Json), ($a | ConvertTo-Json | ConvertFrom-Json)) })
        }
        @($d).Count | Should -Be 0
    }
}

Describe 'Promotion' {
    It 'remplace un texte dans les chemins et les commandes, sans tenir compte de la casse, sans toucher à l''original' {
        $r = InModuleScope FileManagement.Gui {
            $o = '{"id":"r","source":"\\\\PROD\\export\\a","cible":"D:\\Prod\\c","archive":null,"description":"prod ne change pas","programmes":{"avant_lot":{"commande":["\\\\prod\\outils\\x.exe","--dossier","\\\\prod\\export"],"timeout_sec":60},"apres_lot":null}}' | ConvertFrom-Json
            $a = Get-CopieRegleAdaptee -Regle $o -Chercher '\\prod\' -Remplacer '\\recette\'
            @{ Adaptee = $a; Original = $o }
        }
        $r.Adaptee.Regle.source | Should -Be '\\recette\export\a'
        $r.Adaptee.Regle.cible | Should -Be 'D:\Prod\c'
        $r.Adaptee.Regle.description | Should -Be 'prod ne change pas'
        $r.Adaptee.Regle.programmes.avant_lot.commande[0] | Should -Be '\\recette\outils\x.exe'
        $r.Adaptee.Regle.programmes.avant_lot.commande[1] | Should -Be '--dossier'
        $r.Adaptee.Regle.programmes.apres_lot | Should -BeNullOrEmpty
        @($r.Adaptee.Changements).Count | Should -Be 3
        $r.Original.source | Should -Be '\\PROD\export\a'
    }
    It 'prend le texte cherché littéralement et le remplacement tel quel (pas de $1, pas de regex)' {
        $r = InModuleScope FileManagement.Gui {
            $o = '{"source":"D:\\a.b\\x"}' | ConvertFrom-Json
            Get-CopieRegleAdaptee -Regle $o -Chercher 'a.b' -Remplacer '$1+(z)'
        }
        $r.Regle.source | Should -Be 'D:\$1+(z)\x'
        $r2 = InModuleScope FileManagement.Gui { Get-CopieRegleAdaptee -Regle ('{"source":"D:\\axb"}' | ConvertFrom-Json) -Chercher 'a.b' -Remplacer 'z' }
        $r2.Regle.source | Should -Be 'D:\axb'
        @($r2.Changements).Count | Should -Be 0
    }
    It 'garde un tableau commande à un élément et ne remplace rien si le texte cherché est vide' {
        $r = InModuleScope FileManagement.Gui {
            $o = '{"source":"D:\\a","programmes":{"avant_lot":{"commande":["C:\\x.exe"],"timeout_sec":5}}}' | ConvertFrom-Json
            Get-CopieRegleAdaptee -Regle $o -Chercher 'C:' -Remplacer 'E:'
        }
        (ConvertTo-Json $r.Regle -Compress -Depth 10) | Should -Match '"commande":\["E:\\\\x\.exe"\]'
        $v = InModuleScope FileManagement.Gui { Get-CopieRegleAdaptee -Regle ('{"source":"D:\\a"}' | ConvertFrom-Json) }
        @($v.Changements).Count | Should -Be 0
    }
    It 'repère les dépendances absentes de la cible' {
        InModuleScope FileManagement.Gui {
            $r = '{"id":"x","apres":["Amont","manque"]}' | ConvertFrom-Json
            $cible = @('{"id":"amont"}', '{"id":"autre"}') | ForEach-Object { $_ | ConvertFrom-Json }
            (Get-CopieDependanceManquante -Regle $r -Existantes $cible) -join ',' | Should -Be 'manque'
            @(Get-CopieDependanceManquante -Regle ('{"id":"y"}' | ConvertFrom-Json) -Existantes @()).Count | Should -Be 0
        }
    }
}

Describe 'Historique des versions' {
    It 'liste les versions d''un environnement, de la plus récente à la plus ancienne, avec leur fiche' {
        $dossier = Join-Path $TestDrive 'h1'
        $versions = Join-Path $dossier 'versions'
        $null = New-Item -ItemType Directory -Path $versions
        $fichier = Join-Path $dossier 'prod.jsonl'
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($fichier, '{"version":1,"environnement":"prod"}' + "`n", $utf8)
        foreach ($n in 'prod_20260101_100000_DOM_ben.jsonl', 'prod_20260102_090000_DOM_ben.jsonl', 'prod_x_20260103_090000_DOM_ben.jsonl', 'autre_20260101_100000_u.jsonl', 'prod_texte.jsonl') {
            [System.IO.File]::WriteAllText((Join-Path $versions $n), '{"version":1,"environnement":"prod"}' + "`n", $utf8)
        }
        $fiche = [ordered]@{ environnement = 'prod'; compte = 'DOM\ben'; date = '2026-01-02T08:00:00Z'; commentaire = 'Mise à jour é'; avertissements = @('P02 trop fréquent') }
        [System.IO.File]::WriteAllText((Join-Path $versions 'prod_20260102_090000_DOM_ben.meta.json'), ($fiche | ConvertTo-Json), $utf8)
        $cfg = [pscustomobject]@{ Parametrage = [pscustomobject]@{ DossierVersions = 'versions' } }
        $h = @(InModuleScope FileManagement.Gui -Parameters @{ f = $fichier; c = $cfg } { param($f, $c) Get-CopieHistorique -Fichier $f -Config $c })
        $h.Count | Should -Be 2
        $h[0].Cle | Should -Be 'prod_20260102_090000_DOM_ben.jsonl'
        $h[0].Commentaire | Should -Be 'Mise à jour é'
        $h[0].Compte | Should -Be 'DOM\ben'
        $h[0].AFiche | Should -BeTrue
        $h[0].Avertissements | Should -Contain 'P02 trop fréquent'
        $h[0].Apres | Should -Be $fichier
        $h[1].Compte | Should -Be 'DOM_ben'
        $h[1].AFiche | Should -BeFalse
        $h[1].Apres | Should -Be $h[0].Fichier
    }
    It 'renvoie une liste vide quand il n''y a pas de dossier de versions' {
        $cfg = [pscustomobject]@{ Parametrage = [pscustomobject]@{ DossierVersions = 'versions' } }
        @(InModuleScope FileManagement.Gui -Parameters @{ f = (Join-Path $TestDrive 'rien\prod.jsonl'); c = $cfg } { param($f, $c) Get-CopieHistorique -Fichier $f -Config $c }).Count | Should -Be 0
    }
}

Describe 'Historique de bout en bout (moteur réel)' -Skip:(-not $Script:PythonDisponible) {
    It 'trace deux enregistrements successifs et montre ce que chacun a changé' {
        $res = InModuleScope FileManagement.Gui -Parameters @{ r = $Script:RacineMoteur; d = $TestDrive } {
            param($r, $d)
            $cfg = [pscustomobject]@{
                Moteur = [pscustomobject]@{ Mode = 'Local'; Python = $env:COPIE_TEST_PYTHON; Racine = $r; ConfigurationJea = ''; Serveur = ''; DelaiMaxSec = 60 }
                Parametrage = [pscustomobject]@{ DossierVersions = 'versions'; DossierBrouillons = '.brouillons'; PeriodeDeclencheurSec = 300 } }
            $m = Get-CopieModeleRegle -Config $cfg
            $dossier = Join-Path $d 'bout'; $null = New-Item -ItemType Directory -Path $dossier
            $fichier = Join-Path $dossier 'essai.jsonl'
            $entete = [pscustomobject]@{ version = 1; environnement = 'essai'; base = (Join-Path $dossier 'x.db') }
            [System.IO.File]::WriteAllText($fichier, ((ConvertTo-CopieLigneJson $entete) + "`n"), (New-Object System.Text.UTF8Encoding($false)))
            $nouvelle = {
                param($id)
                $b = Merge-CopieRegle -Modele $m.regle -Existante $null
                $b.id = $id; $b.source = (Join-Path $dossier "s_$id"); $b.cible = (Join-Path $dossier "c_$id"); $b.mode = 'copie'
                $b.planification = '{"type":"quotidien","heure":"07:00","jours":"tous","rattrapage_sec":null}' | ConvertFrom-Json
                $b
            }
            $p0 = Read-CopieFichierParametrage -Chemin $fichier
            $s1 = Save-CopieParametrage -Config $cfg -Fichier $fichier -EmpreinteAttendue $p0.Empreinte -Entete $entete -Regle @(& $nouvelle 'a') -Compte 'DOM\ben' -Commentaire 'première règle'
            Start-Sleep -Seconds 1.2
            $p1 = Read-CopieFichierParametrage -Chemin $fichier
            $modifiee = Merge-CopieRegle -Modele $m.regle -Existante $p1.Regles[0]
            $modifiee.duree_max_sec = 600
            $s2 = Save-CopieParametrage -Config $cfg -Fichier $fichier -EmpreinteAttendue $p1.Empreinte -Entete $entete -Regle @($modifiee, (& $nouvelle 'b')) -Compte 'DOM\ben' -Commentaire 'durée et seconde règle'
            $h = @(Get-CopieHistorique -Fichier $fichier -Config $cfg)
            $diffs = foreach ($v in $h) { , @(Compare-CopieParametrage -Avant (Read-CopieFichierParametrage -Chemin $v.Fichier) -Apres (Read-CopieFichierParametrage -Chemin $v.Apres)) }
            @{ S1 = $s1.Etape; S2 = $s2.Etape; H = $h; D = $diffs }
        }
        $res.S1 | Should -Be 'ok'
        $res.S2 | Should -Be 'ok'
        $res.H.Count | Should -Be 2
        $res.H[0].Commentaire | Should -Be 'durée et seconde règle'
        $res.H[1].Commentaire | Should -Be 'première règle'
        ($res.D[1] | ForEach-Object Changement) | Should -Contain 'Ajoutée'
        ($res.D[0] | Where-Object Changement -eq 'Ajoutée').Regle | Should -Be 'b'
        ($res.D[0] | Where-Object Changement -eq 'Modifiée').Champ | Should -Be 'duree_max_sec'
    }
    It 'restaure l''état d''avant une modification par l''enregistrement sécurisé, sans rien effacer de l''historique' {
        $res = InModuleScope FileManagement.Gui -Parameters @{ r = $Script:RacineMoteur; d = $TestDrive } {
            param($r, $d)
            $cfg = [pscustomobject]@{
                Moteur = [pscustomobject]@{ Mode = 'Local'; Python = $env:COPIE_TEST_PYTHON; Racine = $r; ConfigurationJea = ''; Serveur = ''; DelaiMaxSec = 60 }
                Parametrage = [pscustomobject]@{ DossierVersions = 'versions'; DossierBrouillons = '.brouillons'; PeriodeDeclencheurSec = 300 } }
            $m = Get-CopieModeleRegle -Config $cfg
            $dossier = Join-Path $d 'restaure'; $null = New-Item -ItemType Directory -Path $dossier
            $fichier = Join-Path $dossier 'essai.jsonl'
            $entete = [pscustomobject]@{ version = 1; environnement = 'essai'; base = (Join-Path $dossier 'x.db') }
            [System.IO.File]::WriteAllText($fichier, ((ConvertTo-CopieLigneJson $entete) + "`n"), (New-Object System.Text.UTF8Encoding($false)))
            $nouvelle = {
                param($id)
                $b = Merge-CopieRegle -Modele $m.regle -Existante $null
                $b.id = $id; $b.source = (Join-Path $dossier "s_$id"); $b.cible = (Join-Path $dossier "c_$id"); $b.mode = 'copie'
                $b.planification = '{"type":"quotidien","heure":"07:00","jours":"tous","rattrapage_sec":null}' | ConvertFrom-Json
                $b
            }
            $p0 = Read-CopieFichierParametrage -Chemin $fichier
            $null = Save-CopieParametrage -Config $cfg -Fichier $fichier -EmpreinteAttendue $p0.Empreinte -Entete $entete -Regle @(& $nouvelle 'a') -Compte 'DOMen' -Commentaire 'première règle'
            Start-Sleep -Seconds 1.2
            $p1 = Read-CopieFichierParametrage -Chemin $fichier
            $null = Save-CopieParametrage -Config $cfg -Fichier $fichier -EmpreinteAttendue $p1.Empreinte -Entete $entete -Regle @($p1.Regles[0], (& $nouvelle 'b')) -Compte 'DOMen' -Commentaire 'ajout de b'
            Start-Sleep -Seconds 1.2
            # Restauration : ce que fait Invoke-CopieRestauration, sans les fenêtres
            $h = @(Get-CopieHistorique -Fichier $fichier -Config $cfg)
            $actuel = Read-CopieFichierParametrage -Chemin $fichier
            $ancien = Read-CopieFichierParametrage -Chemin $h[0].Fichier
            $ecarts = @(Compare-CopieParametrage -Avant $actuel -Apres $ancien)
            $s = Save-CopieParametrage -Config $cfg -Fichier $fichier -EmpreinteAttendue $actuel.Empreinte -Entete $ancien.Entete -Regle @($ancien.Regles) -Compte 'DOMen' -Commentaire 'retour avant b' -Confirmer { $true }       # la fenêtre d'avertissements : accepter la suppression de b
            $apres = Read-CopieFichierParametrage -Chemin $fichier
            $h2 = @(Get-CopieHistorique -Fichier $fichier -Config $cfg)
            @{ Ecarts = $ecarts; Etape = $s.Etape; Ids = @($apres.Regles | ForEach-Object { $_.id }); Reste = @(Compare-CopieParametrage -Avant $apres -Apres $ancien); Histo = $h2 }
        }
        $res.Ecarts.Count | Should -BeGreaterThan 0
        ($res.Ecarts | Where-Object Changement -eq 'Supprimée').Regle | Should -Be 'b'
        $res.Etape | Should -Be 'ok'
        $res.Ids -join ',' | Should -Be 'a'
        $res.Reste.Count | Should -Be 0
        $res.Histo.Count | Should -Be 3
        $res.Histo[0].Commentaire | Should -Be 'retour avant b'
        $res.Histo[1].Commentaire | Should -Be 'ajout de b'
    }
}

Describe 'Fenêtres Historique et Promotion' -Skip:(-not $Script:Sta) {
    It 'l''historique affiche les différences de la version sélectionnée' {
        $dossier = Join-Path $TestDrive 'fh'; $null = New-Item -ItemType Directory -Path $dossier
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        $avant = Join-Path $dossier 'avant.jsonl'; $apres = Join-Path $dossier 'apres.jsonl'
        [System.IO.File]::WriteAllText($avant, '{"version":1,"environnement":"e"}' + "`n" + '{"id":"a","duree_max_sec":1}' + "`n", $utf8)
        [System.IO.File]::WriteAllText($apres, '{"version":1,"environnement":"e"}' + "`n" + '{"id":"a","duree_max_sec":2}' + "`n", $utf8)
        $res = InModuleScope FileManagement.Gui -Parameters @{ a = $avant; b = $apres } {
            param($a, $b)
            $f = Import-CopieXaml -Nom 'Dialog.Historique'
            $v = [pscustomobject]@{ Fichier = $a; Apres = $b; DateTexte = 'x'; Compte = 'c'; Commentaire = 'k'; Avertissements = @('P02 x'); AFiche = $true }
            $f.FindName('Versions').ItemsSource = @($v)
            $f.FindName('Versions').SelectedIndex = 0
            Update-CopieHistoriqueDiff -Fenetre $f
            @{ Diff = @($f.FindName('Differences').ItemsSource); Remarque = $f.FindName('Remarque').Text }
        }
        $res.Diff.Count | Should -Be 1
        $res.Diff[0].Champ | Should -Be 'duree_max_sec'
        $res.Diff[0].Avant | Should -Be '1'
        $res.Diff[0].Apres | Should -Be '2'
        $res.Remarque | Should -Match 'P02'
    }
    It 'la promotion montre les chemins adaptés, la règle déjà présente et les dépendances absentes' {
        $res = InModuleScope FileManagement.Gui {
            $regle = '{"id":"r","source":"\\\\prod\\a","cible":"D:\\c","apres":["amont"]}' | ConvertFrom-Json
            $cibleEnv = [pscustomobject]@{ Nom = 'recette'; Parametrage = [pscustomobject]@{ Regles = @(('{"id":"R"}' | ConvertFrom-Json)) } }
            $f = Import-CopieXaml -Nom 'Dialog.Promotion'
            $f.Tag = @{ Regle = $regle; Cibles = @(@{ Env = $cibleEnv }) }
            $f.FindName('Cible').Items.Add('recette') | Out-Null
            $f.FindName('Cible').SelectedIndex = 0
            $f.FindName('Chercher').Text = '\\prod\'
            $f.FindName('Remplacer').Text = '\\recette\'
            Update-CopiePromotionApercu -Fenetre $f
            @{ Apercu = @($f.FindName('Apercu').ItemsSource); Remarques = $f.FindName('Remarques').Text }
        }
        $res.Apercu.Count | Should -Be 1
        $res.Apercu[0].Apres | Should -Be '\\recette\a'
        $res.Remarques | Should -Match 'existe déjà'
        $res.Remarques | Should -Match 'amont'
    }
}
