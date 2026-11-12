#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
# Étape B : formulaire de règle. Les contrôles WPF sont construits pour de bon (sans être affichés) et
# relus : un formulaire non touché doit redonner exactement la règle de départ, et la règle saisie doit être
# acceptée par le VRAI moteur (COPIE_TEST_PYTHON ; absent : ces tests sont ignorés).

BeforeDiscovery {
    $Script:PythonDisponible = [bool]$env:COPIE_TEST_PYTHON -and (Test-Path -LiteralPath $env:COPIE_TEST_PYTHON)
    $Script:Sta = ([System.Threading.Thread]::CurrentThread.GetApartmentState() -eq 'STA')
}

BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..\FileManagement.Gui\FileManagement.Gui.psd1') -Force
}

Describe 'Jours' {
    It 'lit et écrit tous, les plages et les listes' {
        InModuleScope FileManagement.Gui {
            (ConvertFrom-CopieJours 'tous') -join ',' | Should -Be 'lun,mar,mer,jeu,ven,sam,dim'
            (ConvertFrom-CopieJours 'lun-ven') -join ',' | Should -Be 'lun,mar,mer,jeu,ven'
            (ConvertFrom-CopieJours 'sam,lun') -join ',' | Should -Be 'lun,sam'
            (ConvertFrom-CopieJours 'ven-lun') -join ',' | Should -Be 'lun,ven,sam,dim'
            ConvertFrom-CopieJours 'n''importe quoi' | Should -BeNullOrEmpty
            ConvertTo-CopieJours -Jour @('lun', 'mar', 'mer', 'jeu', 'ven') | Should -Be 'lun-ven'
            ConvertTo-CopieJours -Jour @('lun', 'mer', 'ven') | Should -Be 'lun,mer,ven'
            ConvertTo-CopieJours -Jour @('lun', 'mar') | Should -Be 'lun,mar'
            ConvertTo-CopieJours -Jour $Script:JoursSemaine | Should -Be 'tous'
            ConvertTo-CopieJours -Jour @() | Should -BeNullOrEmpty
        }
    }
    It 'relit ce qu''il écrit' {
        InModuleScope FileManagement.Gui {
            foreach ($t in 'lun-ven', 'lun,mer,ven', 'sam,dim', 'tous', 'mar') {
                ConvertTo-CopieJours -Jour (ConvertFrom-CopieJours $t) | Should -Be $t
            }
        }
    }
}

Describe 'Durées' {
    It 'choisit la plus grande unité exacte' {
        InModuleScope FileManagement.Gui {
            (ConvertTo-CopieDureeAffichage 1800) | ForEach-Object { "$($_.Valeur) $($_.Unite)" } | Should -Be '30 minutes'
            (ConvertTo-CopieDureeAffichage 86400) | ForEach-Object { "$($_.Valeur) $($_.Unite)" } | Should -Be '1 jours'
            (ConvertTo-CopieDureeAffichage 90) | ForEach-Object { "$($_.Valeur) $($_.Unite)" } | Should -Be '90 secondes'
            (ConvertTo-CopieDureeAffichage 0) | ForEach-Object { "$($_.Valeur) $($_.Unite)" } | Should -Be '0 secondes'
            (ConvertTo-CopieDureeAffichage $null).Valeur | Should -Be ''
        }
    }
    It 'convertit la saisie en secondes et refuse le reste' {
        InModuleScope FileManagement.Gui {
            (ConvertFrom-CopieDureeAffichage -Valeur '2' -Unite 'heures').Secondes | Should -Be 7200
            (ConvertFrom-CopieDureeAffichage -Valeur ' 45 ' -Unite 'secondes').Secondes | Should -Be 45
            (ConvertFrom-CopieDureeAffichage -Valeur 'abc' -Unite 'minutes').Ok | Should -BeFalse
            (ConvertFrom-CopieDureeAffichage -Valeur '-3' -Unite 'minutes').Ok | Should -BeFalse
            (ConvertFrom-CopieDureeAffichage -Valeur '1,5' -Unite 'minutes').Ok | Should -BeFalse
        }
    }
}

Describe 'Formulaire de règle' -Skip:(-not ($Script:PythonDisponible -and $Script:Sta)) {
    BeforeAll {
        $Script:Config = [pscustomobject]@{
            Moteur      = [pscustomobject]@{ Mode = 'Local'; Python = $env:COPIE_TEST_PYTHON; Racine = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).ProviderPath; ConfigurationJea = ''; Serveur = ''; DelaiMaxSec = 60 }
            Parametrage = [pscustomobject]@{ DossierVersions = 'versions'; DossierBrouillons = '.brouillons'; PeriodeDeclencheurSec = 300 }
        }
        $Script:Construire = {
            param($regle, $mode = 'ajout', $ids = @())
            InModuleScope FileManagement.Gui -Parameters @{ c = $Script:Config; regle = $regle; mode = $mode; ids = $ids } {
                param($c, $regle, $mode, $ids)
                $m = Get-CopieModeleRegle -Config $c
                $depart = Merge-CopieRegle -Modele $m.regle -Existante $regle
                $f = New-CopieFormulaireRegle -Contexte @{ Fenetre = $null } -Modele $m -Regle $depart -Mode $mode -IdsExistants $ids
                @{ Fenetre = $f; Depart = $depart }
            }
        }
        $Script:Existante = '{"id":"r1","description":"Copie é du soir","actif":false,"source":"\\\\srv\\a","cible":"D:\\b","mode":"deplacement","archive":"D:\\arch","selection":{"masque":"*.csv","age_minimum_sec":120},"planification":{"type":"intervalle","frequence_sec":3600,"debut":"06:00","fin":"20:00","jours":"lun-ven","rattrapage_sec":7200},"apres":["amont"],"duree_max_sec":5400,"situations":{"copie_echec":{"tentatives":7,"delai_sec":90,"niveau_final":"WARNING","suite":"fichier_suivant"}},"programmes":{"avant_lot":{"commande":["C:\\x.exe"],"timeout_sec":600}}}' | ConvertFrom-Json
    }

    It 'un formulaire non touché redonne exactement la règle de départ' {
        $o = & $Script:Construire $Script:Existante 'modification'
        $lecture = InModuleScope FileManagement.Gui -Parameters @{ f = $o.Fenetre } { param($f) Read-CopieFormulaire -Etat $f.Tag }
        $lecture.Erreurs.Count | Should -Be 0
        $apres = InModuleScope FileManagement.Gui -Parameters @{ r = $lecture.Regle } { param($r) ConvertTo-CopieLigneJson $r }
        $avant = InModuleScope FileManagement.Gui -Parameters @{ r = $o.Depart } { param($r) ConvertTo-CopieLigneJson $r }
        $apres | Should -Be $avant
    }
    It 'garde les tableaux à un élément (apres, commande) après lecture du formulaire' {
        $o = & $Script:Construire $Script:Existante 'modification'
        $json = InModuleScope FileManagement.Gui -Parameters @{ f = $o.Fenetre } { param($f) ConvertTo-CopieLigneJson (Read-CopieFormulaire -Etat $f.Tag).Regle }
        $json | Should -Match '"apres":\["amont"\]'
        $json | Should -Match '"commande":\["C:\\\\x\.exe"\]'
        $json | Should -Match '"planification":\{"type":"intervalle","frequence_sec":3600,"debut":"06:00","fin":"20:00","jours":"lun-ven","rattrapage_sec":7200\}'
    }
    It 'signale les saisies incorrectes avec le nom du champ' {
        $o = & $Script:Construire $null 'ajout'
        $erreurs = InModuleScope FileManagement.Gui -Parameters @{ f = $o.Fenetre } {
            param($f)
            $t = $f.Tag
            foreach ($e in $t.Champs) {
                switch ($e.Spec.Chemin) {
                    'id' { $e.Controle.Text = 'ok' }; 'source' { $e.Controle.Text = 'S' }; 'cible' { $e.Controle.Text = 'C' }
                    'relances_max' { $e.Controle.Text = 'beaucoup' }
                    'selection.age_minimum_sec' { $e.Saisie.Text = '-4' }
                }
            }
            $t.Planif.Heure.Controle.Text = ''
            foreach ($j in $Script:JoursSemaine) { $t.Planif.Jours[$j].IsChecked = $false }
            (Read-CopieFormulaire -Etat $t).Erreurs
        }
        ($erreurs -join '|') | Should -Match 'Relances maximum'
        ($erreurs -join '|') | Should -Match 'Âge minimum'
        ($erreurs -join '|') | Should -Match 'Heure de lancement'
        ($erreurs -join '|') | Should -Match 'Jours'
    }
    It 'refuse à l''ajout un identifiant déjà pris (sans tenir compte de la casse)' {
        $o = & $Script:Construire $null 'ajout' @('r1')
        $erreurs = InModuleScope FileManagement.Gui -Parameters @{ f = $o.Fenetre } {
            param($f)
            foreach ($e in $f.Tag.Champs) { switch ($e.Spec.Chemin) { 'id' { $e.Controle.Text = 'R1' }; 'source' { $e.Controle.Text = 'S' }; 'cible' { $e.Controle.Text = 'C' } } }
            $f.Tag.Planif.Heure.Controle.Text = '07:00'
            (Read-CopieFormulaire -Etat $f.Tag).Erreurs
        }
        ($erreurs -join '|') | Should -Match 'existe déjà'
    }
    It 'ne propose la case Horodater que pour copie et archivage, et la décoche pour un autre mode' {
        $o = & $Script:Construire $null 'ajout'
        InModuleScope FileManagement.Gui -Parameters @{ f = $o.Fenetre } {
            param($f)
            $mode = $f.Tag.Champs | Where-Object { $_.Spec.Chemin -eq 'mode' }
            $horo = $f.Tag.Champs | Where-Object { $_.Spec.Chemin -eq 'horodater' }
            $horo.Spec.Type | Should -Be 'bool'
            $mode.Controle.SelectedItem = 'copie'
            $horo.Controle.IsEnabled | Should -BeTrue
            $horo.Controle.IsChecked = $true
            $mode.Controle.SelectedItem = 'archivage'
            $horo.Controle.IsEnabled | Should -BeTrue
            $horo.Controle.IsChecked | Should -BeTrue
            (Read-CopieFormulaire -Etat $f.Tag).Regle.horodater | Should -BeTrue
            foreach ($autre in 'deplacement', 'suppression', 'count', 'size') {
                $mode.Controle.SelectedItem = $autre
                $horo.Controle.IsEnabled | Should -BeFalse
                $horo.Controle.IsChecked | Should -BeFalse
            }
            (Read-CopieFormulaire -Etat $f.Tag).Regle.horodater | Should -BeFalse
        }
    }
    It 'mode synchro : dossiers et seuils grisés et vides, planification imposée, aucune erreur de saisie' {
        $o = & $Script:Construire $null 'ajout'
        InModuleScope FileManagement.Gui -Parameters @{ f = $o.Fenetre } {
            param($f)
            $t = $f.Tag
            $champ = { param($nom) $t.Champs | Where-Object { $_.Spec.Chemin -eq $nom } }
            (& $champ 'id').Controle.Text = 'sync'
            (& $champ 'source').Controle.Text = 'S'
            (& $champ 'cible').Controle.Text = 'C'
            (& $champ 'mode').Controle.SelectedItem = 'synchro'
            foreach ($nom in 'source', 'cible', 'archive', 'dossier_temporaire', 'seuil_minimum', 'seuil_maximum') {
                (& $champ $nom).Controle.IsEnabled | Should -BeFalse -Because $nom
                (& $champ $nom).Controle.Text | Should -Be '' -Because $nom
            }
            $t.Planif.Type.SelectedItem | Should -Be 'apres_dependances'
            $t.Planif.Type.IsEnabled | Should -BeFalse
            $lecture = Read-CopieFormulaire -Etat $t
            $lecture.Erreurs.Count | Should -Be 0 -Because ($lecture.Erreurs -join '|')
            $lecture.Regle.mode | Should -Be 'synchro'
            $lecture.Regle.planification.type | Should -Be 'apres_dependances'
            # un autre mode : tout redevient saisissable (et la source obligatoire)
            (& $champ 'mode').Controle.SelectedItem = 'copie'
            (& $champ 'source').Controle.IsEnabled | Should -BeTrue
            $t.Planif.Type.IsEnabled | Should -BeTrue
            ((Read-CopieFormulaire -Etat $t).Erreurs -join '|') | Should -Match 'Dossier source'
        }
    }
    It 'montre seulement les champs du type de planification choisi' {
        $o = & $Script:Construire $null 'ajout'
        InModuleScope FileManagement.Gui -Parameters @{ f = $o.Fenetre } {
            param($f)
            $pl = $f.Tag.Planif
            $pl.Type.SelectedItem = 'quotidien'
            $pl.Heure.Boite.Visibility | Should -Be 'Visible'
            $pl.Frequence.Boite.Visibility | Should -Be 'Collapsed'
            $pl.Type.SelectedItem = 'intervalle'
            $pl.Heure.Boite.Visibility | Should -Be 'Collapsed'
            $pl.Frequence.Boite.Visibility | Should -Be 'Visible'
            $pl.Type.SelectedItem = 'apres_dependances'
            $pl.BoiteJours.Visibility | Should -Be 'Collapsed'
        }
    }
    It 'une règle saisie dans le formulaire est acceptée par le moteur et enregistrée' {
        $o = & $Script:Construire $null 'ajout'
        $dossier = Join-Path $TestDrive 'ok'; $null = New-Item -ItemType Directory $dossier
        $res = InModuleScope FileManagement.Gui -Parameters @{ f = $o.Fenetre; c = $Script:Config; d = $dossier } {
            param($f, $c, $d)
            $t = $f.Tag
            foreach ($e in $t.Champs) {
                switch ($e.Spec.Chemin) {
                    'id' { $e.Controle.Text = 'saisie' }; 'source' { $e.Controle.Text = (Join-Path $d 's') }; 'cible' { $e.Controle.Text = (Join-Path $d 'c') }
                    'selection.age_minimum_sec' { $e.Saisie.Text = '2'; $e.Unite.SelectedItem = 'minutes' }
                }
            }
            $t.Planif.Heure.Controle.Text = '07:15'
            foreach ($j in 'sam', 'dim') { $t.Planif.Jours[$j].IsChecked = $false }
            $t.Programmes['avant_lot'].Active.IsChecked = $true
            $t.Programmes['avant_lot'].Commande.Text = "C:\outils\x.exe`r`n--option`r`n{regle}"
            $lecture = Read-CopieFormulaire -Etat $t
            if ($lecture.Erreurs.Count -gt 0) { return $lecture }
            $entete = [pscustomobject]@{ version = 1; environnement = 'saisie'; code_environnement = 'test'; base = (Join-Path $d 'x.db') }
            $fichier = Join-Path $d 'saisie.jsonl'
            [System.IO.File]::WriteAllText($fichier, ((ConvertTo-CopieLigneJson $entete) + "`n"), (New-Object System.Text.UTF8Encoding($false)))
            $p = Read-CopieFichierParametrage -Chemin $fichier
            Save-CopieParametrage -Config $c -Fichier $fichier -EmpreinteAttendue $p.Empreinte -Entete $entete -Regle @($lecture.Regle) -Compte 'D\b' -Commentaire 'x' -Confirmer { $true }
        }
        $res.Erreurs | Should -BeNullOrEmpty
        ($res.Refus | ForEach-Object { "$($_.code) $($_.message)" }) -join '; ' | Should -BeNullOrEmpty
        $res.Etape | Should -Be 'ok'
        $ecrit = (Get-Content -LiteralPath (Join-Path $dossier 'saisie.jsonl') -Encoding UTF8)[1] | ConvertFrom-Json
        $ecrit.planification.jours | Should -Be 'lun-ven'
        $ecrit.selection.age_minimum_sec | Should -Be 120
        $ecrit.programmes.avant_lot.commande.Count | Should -Be 3
    }
}
