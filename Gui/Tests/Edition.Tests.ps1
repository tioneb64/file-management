#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
# Étape B : modèle du moteur, fusion, tri, enregistrement sécurisé. Le VRAI moteur Python est appelé
# (interpréteur lu dans COPIE_TEST_PYTHON ; absent : tests ignorés). Aucun accès à un serveur.

BeforeDiscovery {
    $Script:PythonDisponible = [bool]$env:COPIE_TEST_PYTHON -and (Test-Path -LiteralPath $env:COPIE_TEST_PYTHON)
}

BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..\FileManagement.Gui\FileManagement.Gui.psd1') -Force
    $Script:RacineMoteur = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).ProviderPath
    $Script:Config = [pscustomobject]@{
        Moteur      = [pscustomobject]@{ Mode = 'Local'; Python = $env:COPIE_TEST_PYTHON; Racine = $Script:RacineMoteur; ConfigurationJea = ''; Serveur = ''; DelaiMaxSec = 60 }
        Parametrage = [pscustomobject]@{ DossierVersions = 'versions'; DossierBrouillons = '.brouillons'; PeriodeDeclencheurSec = 300 }
    }
}

Describe 'Edition (sans moteur)' {
    It 'écrit une ligne JSON compacte qui garde les tableaux à un élément, les null, les accents et les caractères spéciaux' {
        InModuleScope FileManagement.Gui {
            $o = '{"id":"r","apres":["a"],"condition":[],"x":null,"description":"é <b> & l''a","p":{"q":{"r":{"s":1}}}}' | ConvertFrom-Json
            $ligne = ConvertTo-CopieLigneJson -Objet $o
            $ligne | Should -Not -Match "`n"
            $ligne | Should -Match '"apres":\["a"\]'
            $ligne | Should -Match '"condition":\[\]'
            $ligne | Should -Match '"x":null'
            $ligne | Should -Match '"s":1'
            ($ligne | ConvertFrom-Json).description | Should -Be 'é <b> & l''a'
        }
    }
    It 'n''écrit jamais le numéro de ligne, propre à l''affichage' {
        InModuleScope FileManagement.Gui {
            $o = '{"id":"r"}' | ConvertFrom-Json
            Add-Member -InputObject $o -NotePropertyName Ligne -NotePropertyValue 4
            ConvertTo-CopieLigneJson -Objet $o | Should -Be '{"id":"r"}'
            $o.Ligne | Should -Be 4
        }
    }
    It 'range les dépendances avant les règles qui en dépendent, sans bouger le reste' {
        InModuleScope FileManagement.Gui {
            $r = @('{"id":"c","apres":["b"]}', '{"id":"a"}', '{"id":"b","apres":["A"]}', '{"id":"d"}') | ForEach-Object { $_ | ConvertFrom-Json }
            ((Get-CopieRegleOrdonnee -Regle $r) | ForEach-Object id) -join '' | Should -Be 'abcd'
        }
    }
    It 'ne boucle pas sur une dépendance circulaire, inconnue ou vers elle-même' {
        InModuleScope FileManagement.Gui {
            $r = @('{"id":"a","apres":["b"]}', '{"id":"b","apres":["a"]}', '{"id":"c","apres":["inconnue","c"]}') | ForEach-Object { $_ | ConvertFrom-Json }
            @(Get-CopieRegleOrdonnee -Regle $r).Count | Should -Be 3
            @(Get-CopieRegleOrdonnee -Regle @()).Count | Should -Be 0
        }
    }
    It 'nomme les versions avec l''environnement, la date et le compte' {
        InModuleScope FileManagement.Gui {
            Get-CopieNomVersion -Environnement 'production' -Compte 'DOMAINE\benoit' -Date ([datetime]'2026-11-03T10:15:00') | Should -Be 'production_20261103_101500_DOMAINE_benoit.jsonl'
            Get-CopieNomVersion -Environnement 'p' -Compte 'a:b*c' -Date ([datetime]'2026-01-02T03:04:05') | Should -Be 'p_20260102_030405_a_b_c.jsonl'
        }
    }
}

Describe 'Edition (moteur réel)' -Skip:(-not $Script:PythonDisponible) {
    BeforeAll {
        $Script:Modele = InModuleScope FileManagement.Gui -Parameters @{ c = $Script:Config } { param($c) Get-CopieModeleRegle -Config $c }
        $Script:Utf8 = New-Object System.Text.UTF8Encoding($false)
        $Script:Nouvelle = {
            param($id, $surcharges = @{})
            $r = InModuleScope FileManagement.Gui -Parameters @{ m = $Script:Modele; id = $id; s = $surcharges; d = $TestDrive } {
                param($m, $id, $s, $d)
                $b = Merge-CopieRegle -Modele $m.regle -Existante $null
                $b.id = $id; $b.source = (Join-Path $d "s_$id"); $b.cible = (Join-Path $d "c_$id"); $b.mode = 'copie'
                $b.planification = '{"type":"quotidien","heure":"07:00","jours":"tous","rattrapage_sec":null}' | ConvertFrom-Json
                foreach ($k in $s.Keys) { $b.$k = $s[$k] }
                $b
            }
            $r
        }
        $Script:Initialiser = {
            param($nom)
            $d = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
            $null = New-Item -ItemType Directory -Path $d
            $f = Join-Path $d "$nom.jsonl"
            $entete = [pscustomobject]@{ version = 1; environnement = $nom; base = (Join-Path $d 'donnees\base.db') }
            $a = & $Script:Nouvelle 'a'
            $b = & $Script:Nouvelle 'b' @{ apres = @('a') }
            $lignes = InModuleScope FileManagement.Gui -Parameters @{ e = $entete; a = $a; b = $b } { param($e, $a, $b) @(ConvertTo-CopieLigneJson $e; ConvertTo-CopieLigneJson $a; ConvertTo-CopieLigneJson $b) }
            [System.IO.File]::WriteAllText($f, (($lignes -join "`n") + "`n"), $Script:Utf8)
            [pscustomobject]@{ Dossier = $d; Fichier = $f; Entete = $entete; Nom = $nom }
        }
        $Script:Lire = { param($f) InModuleScope FileManagement.Gui -Parameters @{ f = $f } { param($f) Read-CopieFichierParametrage -Chemin $f } }
        $Script:Enregistrer = {
            param($env, $regles, $confirmer = $null, $empreinte = $null)
            $p = & $Script:Lire $env.Fichier
            if (-not $empreinte) { $empreinte = $p.Empreinte }
            InModuleScope FileManagement.Gui -Parameters @{ c = $Script:Config; env = $env; r = $regles; e = $empreinte; conf = $confirmer } {
                param($c, $env, $r, $e, $conf)
                Save-CopieParametrage -Config $c -Fichier $env.Fichier -EmpreinteAttendue $e -Entete $env.Entete -Regle $r -Compte 'DOMAINE\benoit' -Commentaire 'essai' -Confirmer $conf
            }
        }
    }

    It 'le modèle du moteur complète une nouvelle règle, et la règle écrite est acceptée telle quelle' {
        $env = & $Script:Initialiser 'essai'
        $p = & $Script:Lire $env.Fichier
        $p.Erreurs.Count | Should -Be 0
        $p.Regles.Count | Should -Be 2
        $r = $p.Regles[0]
        $r.retention_historique_jours | Should -Be 90
        $r.situations.fichier_verrouille.tentatives | Should -Be 5
        $r.programmes.avant_lot | Should -BeNullOrEmpty
    }
    It 'conserve les valeurs d''une règle existante et complète les champs absents' {
        InModuleScope FileManagement.Gui -Parameters @{ m = $Script:Modele } {
            param($m)
            $existante = '{"id":"x","source":"S","cible":"C","mode":"copie","duree_max_sec":99,"selection":{"masque":"*.csv"},"situations":{"copie_echec":{"tentatives":9,"delai_sec":1,"niveau_final":"WARNING"}},"champ_inconnu":1}' | ConvertFrom-Json
            Add-Member -InputObject $existante -NotePropertyName Ligne -NotePropertyValue 5
            $r = Merge-CopieRegle -Modele $m.regle -Existante $existante
            $r.duree_max_sec | Should -Be 99
            $r.selection.masque | Should -Be '*.csv'
            $r.selection.ordre | Should -Be 'nom'
            $r.situations.copie_echec.tentatives | Should -Be 9
            $r.situations.copie_echec.suite | Should -Be 'arreter_regle'
            $r.situations.fichier_verrouille.tentatives | Should -Be 5
            $r.champ_inconnu | Should -Be 1
            $r.PSObject.Properties['Ligne'] | Should -BeNullOrEmpty
            $r.PSObject.Properties.Name[0] | Should -Be 'id'
            $existante.selection.PSObject.Properties['ordre'] | Should -BeNullOrEmpty
        }
    }
    It 'enregistre : fichier remplacé, version et fiche créées, brouillons supprimés, UTF-8 sans BOM' {
        $env = & $Script:Initialiser 'prod'
        $avant = [System.IO.File]::ReadAllBytes($env.Fichier)
        $p = & $Script:Lire $env.Fichier
        $nouvelle = & $Script:Nouvelle 'c' @{ description = 'Règle accentuée é' }
        $res = & $Script:Enregistrer $env (@($p.Regles) + $nouvelle)
        $res.Etape | Should -Be 'ok'
        $res.Enregistre | Should -BeTrue
        $apres = [System.IO.File]::ReadAllBytes($env.Fichier)
        $apres[0] | Should -Not -Be 0xEF
        (& $Script:Lire $env.Fichier).Regles.Count | Should -Be 3
        (& $Script:Lire $env.Fichier).Empreinte | Should -Be $res.Empreinte
        $res.Version | Should -Match 'prod_\d{8}_\d{6}_DOMAINE_benoit\.jsonl$'
        [System.IO.File]::ReadAllBytes($res.Version) | Should -Be $avant
        $fiche = Get-Content -LiteralPath ($res.Version -replace '\.jsonl$', '.meta.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $fiche.compte | Should -Be 'DOMAINE\benoit'
        $fiche.commentaire | Should -Be 'essai'
        Test-Path (Join-Path $env.Dossier '.brouillons\*') | Should -BeFalse
        (Get-ChildItem -LiteralPath (Join-Path $env.Dossier '.brouillons')).Count | Should -Be 0
    }
    It 'range les règles : une dépendante est écrite après sa dépendance' {
        $env = & $Script:Initialiser 'tri'
        $p = & $Script:Lire $env.Fichier
        $res = & $Script:Enregistrer $env @($p.Regles[1], $p.Regles[0])
        $res.Enregistre | Should -BeTrue
        ((& $Script:Lire $env.Fichier).Regles | ForEach-Object id) -join ',' | Should -Be 'a,b'
    }
    It 'refuse un paramétrage invalide : le fichier n''est pas touché et le refus est renvoyé' {
        $env = & $Script:Initialiser 'refus'
        $avant = (& $Script:Lire $env.Fichier).Empreinte
        $p = & $Script:Lire $env.Fichier
        $doublon = & $Script:Nouvelle 'a'
        $res = & $Script:Enregistrer $env (@($p.Regles) + $doublon)
        $res.Enregistre | Should -BeFalse
        $res.Etape | Should -Be 'refus'
        ($res.Refus | ForEach-Object code) | Should -Contain 'R02'
        (& $Script:Lire $env.Fichier).Empreinte | Should -Be $avant
        Test-Path (Join-Path $env.Dossier 'versions') | Should -BeFalse
        (Get-ChildItem -LiteralPath (Join-Path $env.Dossier '.brouillons')).Count | Should -Be 0
    }
    It 'refuse de modifier l''identifiant d''une règle existante (V01) et de rendre dépendante une règle inactive (D03)' {
        $env = & $Script:Initialiser 'v01'
        $p = & $Script:Lire $env.Fichier
        $renommee = InModuleScope FileManagement.Gui -Parameters @{ r = $p.Regles[0] } { param($r) $c = Copy-CopieObjet $r; $c.id = 'a_renommee'; $c }
        $res = & $Script:Enregistrer $env @($renommee, $p.Regles[1])
        $res.Enregistre | Should -BeFalse
        ($res.Refus | ForEach-Object code) | Should -Contain 'V01'
        $inactive = InModuleScope FileManagement.Gui -Parameters @{ r = $p.Regles[0] } { param($r) $c = Copy-CopieObjet $r; $c.actif = $false; $c }
        $res2 = & $Script:Enregistrer $env @($inactive, $p.Regles[1])
        ($res2.Refus | ForEach-Object code) | Should -Contain 'D03'
    }
    It 'refuse si le fichier a changé depuis son chargement (édition simultanée)' {
        $env = & $Script:Initialiser 'conflit'
        $p = & $Script:Lire $env.Fichier
        $empreinte = $p.Empreinte
        [System.IO.File]::AppendAllText($env.Fichier, "`n", $Script:Utf8)
        $res = & $Script:Enregistrer $env $p.Regles $null $empreinte
        $res.Etape | Should -Be 'conflit'
        $res.Enregistre | Should -BeFalse
        Test-Path (Join-Path $env.Dossier 'versions') | Should -BeFalse
    }
    It 'soumet les avertissements à confirmation : refusés, rien n''est écrit ; acceptés, enregistré' {
        $env = & $Script:Initialiser 'avert'
        $p = & $Script:Lire $env.Fichier
        $rapide = & $Script:Nouvelle 'rapide' @{ planification = ('{"type":"intervalle","frequence_sec":60,"debut":"05:00","fin":"19:00","jours":"tous","rattrapage_sec":null}' | ConvertFrom-Json) }
        $avant = $p.Empreinte
        $res = & $Script:Enregistrer $env (@($p.Regles) + $rapide)
        $res.Etape | Should -Be 'avertissements'
        ($res.Avertissements | ForEach-Object code) | Should -Contain 'P02'
        $res2 = & $Script:Enregistrer $env (@($p.Regles) + $rapide) { $false }
        $res2.Enregistre | Should -BeFalse
        (& $Script:Lire $env.Fichier).Empreinte | Should -Be $avant
        $res3 = & $Script:Enregistrer $env (@($p.Regles) + $rapide) { $true }
        $res3.Enregistre | Should -BeTrue
        $res3.Avertissements.Count | Should -BeGreaterThan 0
        $fiche = Get-Content -LiteralPath ($res3.Version -replace '\.jsonl$', '.meta.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        ($fiche.avertissements -join ' ') | Should -Match 'P02'
    }
    It 'signale un moteur injoignable sans rien écrire' {
        $env = & $Script:Initialiser 'panne'
        $p = & $Script:Lire $env.Fichier
        $cfg = [pscustomobject]@{
            Moteur = [pscustomobject]@{ Mode = 'Local'; Python = (Join-Path $TestDrive 'absent.exe'); Racine = $Script:RacineMoteur; ConfigurationJea = ''; Serveur = ''; DelaiMaxSec = 5 }
            Parametrage = $Script:Config.Parametrage }
        $res = InModuleScope FileManagement.Gui -Parameters @{ c = $cfg; env = $env; p = $p } {
            param($c, $env, $p)
            Save-CopieParametrage -Config $c -Fichier $env.Fichier -EmpreinteAttendue $p.Empreinte -Entete $env.Entete -Regle $p.Regles -Compte 'x' -Commentaire 'y'
        }
        $res.Etape | Should -Be 'moteur'
        (& $Script:Lire $env.Fichier).Empreinte | Should -Be $p.Empreinte
    }
}
