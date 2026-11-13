#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
# Onglet « Outils » : lecture de l'index (outils.json), écriture atomique, lignes du résultat d'un scan, vue WPF, et scan
# par le VRAI moteur Python (COPIE_TEST_PYTHON ; absent, ces tests sont ignorés). Les tests de fenêtre exigent un thread STA.

BeforeDiscovery {
    $Script:PythonDisponible = [bool]$env:COPIE_TEST_PYTHON -and (Test-Path -LiteralPath $env:COPIE_TEST_PYTHON)
    $Script:Sta = ([System.Threading.Thread]::CurrentThread.GetApartmentState() -eq 'STA')
}

BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..\FileManagement.Gui\FileManagement.Gui.psd1') -Force
    $Script:RacineMoteur = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).ProviderPath
    $Script:Utf8 = New-Object System.Text.UTF8Encoding($false)

    function Script:Ecrire([string] $Chemin, [string] $Texte) {
        $dossier = Split-Path -Parent $Chemin
        if (-not (Test-Path -LiteralPath $dossier)) { $null = New-Item -ItemType Directory -Path $dossier -Force }
        [System.IO.File]::WriteAllText($Chemin, $Texte, $Script:Utf8)
    }
    function Script:EnteteOutil([string] $Variable, [string] $Description = 'Fait quelque chose.', [string[]] $Parametres = @()) {
        $l = @("# outil: $Variable", "# description: $Description") + @($Parametres | ForEach-Object { "# parametre: $_" })
        ($l -join "`n") + "`nprint('ok')`n"
    }
    $Script:IndexJson = @'
{
 "version": 1,
 "dossier_outils": "D:\\Scripts\\outils",
 "dossier_resolu": "D:\\Scripts\\outils",
 "scanne_le": "2026-11-13T09:30:00",
 "scanne_par": "DOM\\admin",
 "outils": [
  {"variable": "zip_creer", "fichier": "compression\\zip_creer.py", "description": "Crée une archive zip.",
   "parametres": [{"forme": "CHEMIN", "obligatoire": false, "description": "fichiers"},
                  {"forme": "--sortie ARCHIVE.zip", "obligatoire": true, "description": "archive à créer"}]},
  {"variable": "attendre_stable", "fichier": "controle\\attendre_stable.py", "description": "Attend qu'un fichier cesse de changer.", "parametres": []}
 ]
}
'@
}

Describe 'Index des outils (outils.json)' {
    BeforeEach { $Script:D = Join-Path $TestDrive ([guid]::NewGuid().ToString('N')); $null = New-Item -ItemType Directory -Path $Script:D }
    It 'sans fichier : pas d''index, sans erreur' {
        $i = InModuleScope FileManagement.Gui -Parameters @{ d = $Script:D } { param($d) Get-CopieIndexOutils -Dossier $d }
        $i.Present | Should -BeFalse
        $i.Erreur | Should -BeNullOrEmpty
        @($i.Outils).Count | Should -Be 0
        $i.Chemin | Should -Be (Join-Path $Script:D 'outils.json')
    }
    It 'lit le dossier, la date, les outils triés et leurs paramètres (accents compris)' {
        Ecrire (Join-Path $Script:D 'outils.json') $Script:IndexJson
        $i = InModuleScope FileManagement.Gui -Parameters @{ d = $Script:D } { param($d) Get-CopieIndexOutils -Dossier $d }
        $i.Present | Should -BeTrue
        $i.Erreur | Should -BeNullOrEmpty
        $i.DossierConfigure | Should -Be 'D:\Scripts\outils'
        $i.ScannePar | Should -Be 'DOM\admin'
        $i.ScanneLe | Should -Be '2026-11-13T09:30:00'
        @($i.Outils).Count | Should -Be 2
        $i.Outils[0].Nom | Should -Be 'attendre_stable'
        $z = $i.Outils[1]
        $z.Variable | Should -Be '{outil:zip_creer}'
        $z.SousDossier | Should -Be 'compression'
        $z.Fichier | Should -Be 'zip_creer.py'
        $z.Description | Should -Be 'Crée une archive zip.'
        $z.Obligatoires | Should -Be '--sortie ARCHIVE.zip'
        @($z.Parametres).Count | Should -Be 2
        $z.Parametres[1].Obligatoire | Should -Be 'Oui'
        $z.Parametres[0].Obligatoire | Should -Be ''
        @($i.Outils[0].Parametres).Count | Should -Be 0
    }
    It 'lit aussi un fichier avec BOM, et un dossier vide dans le réglage veut dire le dossier du moteur' {
        $t = $Script:IndexJson -replace '"dossier_outils": "[^"]*"', '"dossier_outils": ""'
        [System.IO.File]::WriteAllText((Join-Path $Script:D 'outils.json'), $t, (New-Object System.Text.UTF8Encoding($true)))
        $i = InModuleScope FileManagement.Gui -Parameters @{ d = $Script:D } { param($d) Get-CopieIndexOutils -Dossier $d }
        $i.Erreur | Should -BeNullOrEmpty
        $i.DossierConfigure | Should -Be ''
        $i.DossierResolu | Should -Be 'D:\Scripts\outils'
    }
    It 'un fichier illisible ou d''une autre version : erreur claire, aucun outil, pas d''exception' {
        foreach ($contenu in '{pas du json', '{"version": 2, "outils": []}') {
            Ecrire (Join-Path $Script:D 'outils.json') $contenu
            $i = InModuleScope FileManagement.Gui -Parameters @{ d = $Script:D } { param($d) Get-CopieIndexOutils -Dossier $d }
            $i.Present | Should -BeTrue
            $i.Erreur | Should -Match 'outils.json illisible'
            @($i.Outils).Count | Should -Be 0
        }
    }
    It 'écrit de façon atomique, en UTF-8 sans BOM, crée puis remplace, sans fichier temporaire' {
        $texte = "{`n ""version"": 1, ""x"": ""é à""`n}`n"
        $chemin = InModuleScope FileManagement.Gui -Parameters @{ d = $Script:D; t = $texte } { param($d, $t) Save-CopieIndexOutils -Dossier $d -Contenu $t }
        $chemin | Should -Be (Join-Path $Script:D 'outils.json')
        $octets = [System.IO.File]::ReadAllBytes($chemin)
        $octets[0] | Should -Not -Be 0xEF
        [System.Text.Encoding]::UTF8.GetString($octets) | Should -Be $texte
        InModuleScope FileManagement.Gui -Parameters @{ d = $Script:D } { param($d) $null = Save-CopieIndexOutils -Dossier $d -Contenu 'deuxieme' }
        [System.IO.File]::ReadAllText($chemin) | Should -Be 'deuxieme'
        @(Get-ChildItem -LiteralPath $Script:D).Count | Should -Be 1
    }
}

Describe 'Début de commande proposé' {
    It 'variable seule quand rien n''est obligatoire, sinon les paramètres obligatoires avec leur valeur à compléter' {
        Ecrire (Join-Path $TestDrive 'ex\outils.json') $Script:IndexJson
        $i = InModuleScope FileManagement.Gui -Parameters @{ d = (Join-Path $TestDrive 'ex') } { param($d) Get-CopieIndexOutils -Dossier $d }
        $i.Outils[0].Exemple | Should -Be '["{outil:attendre_stable}"]'
        $i.Outils[1].Exemple | Should -Be '["{outil:zip_creer}", "--sortie", "<ARCHIVE.zip>"]'
    }
    It 'prend la forme longue d''un paramètre à alias et un interrupteur sans valeur' {
        $o = InModuleScope FileManagement.Gui {
            ConvertTo-CopieOutilAffichage -Outil ([pscustomobject]@{ variable = 'x'; fichier = 'x.py'; description = 'd'
                    parametres = @([pscustomobject]@{ forme = '--recursif/-r'; obligatoire = $true; description = '' }, [pscustomobject]@{ forme = '--vers DOSSIER A'; obligatoire = $true; description = '' }) })
        }
        $o.Exemple | Should -Be '["{outil:x}", "--recursif", "--vers", "<DOSSIER A>"]'
    }
}

Describe 'Lignes du résultat d''un scan' {
    BeforeAll {
        $Script:Reponse = {
            param($json, $reussi = $true, $erreur = '')
            [pscustomobject]@{ Reussi = $reussi; Json = ($json | ConvertFrom-Json); Erreur = $erreur; Code = $(if ($reussi) { 0 } else { 2 }) }
        }
    }
    It 'une ligne par outil retenu et par script non retenu, avec la gravité selon la cause' {
        $json = '{"ok":true,"dossier":"D:\\o","dossiers":3,"fichiers_python":4,"outils":[{"variable":"a","fichier":"d\\a.py","description":"Outil A"}],
"bibliotheques":[{"fichier":"commun\\lib.py","description":"Aides communes."}],
"non_retenus":[{"fichier":"commun\\x.py","cause":"pas d''en-tete d''outil (ligne ''# outil: nom'' absente)"},
{"fichier":"b.py","cause":"en-tete invalide : nom d''outil ''Zip'' refuse"},{"fichier":"c.py","cause":"la variable {outil:a} est deja prise par d\\a.py"}],
"erreurs":[{"chemin":"D:\\o\\prive","message":"dossier illisible : Accès refusé"}]}'
        $l = @(InModuleScope FileManagement.Gui -Parameters @{ r = (& $Script:Reponse $json) } { param($r) ConvertTo-CopieLignesScanOutils -Reponse $r })
        $l.Count | Should -Be 7
        $l[0].Sujet | Should -Be 'Dossier analysé'
        $l[0].Message | Should -Be 'D:\o (3 dossier(s), 4 script(s) Python)'
        $l[1].Sujet | Should -Be 'Outil retenu : {outil:a}'
        $l[1].Message | Should -Be 'd\a.py : Outil A'
        $l[2].Sujet | Should -Be 'Bibliothèque : commun\lib.py'
        $l[2].Message | Should -Be 'Aides communes.'
        $l[2].Gravite | Should -Be 'Information'
        $l[3].Gravite | Should -Be 'Information'
        $l[3].Sujet | Should -Be 'Non retenu : commun\x.py'
        $l[4].Gravite | Should -Be 'Avertissement'
        $l[4].Message | Should -Match 'nom d''outil ''Zip'' refuse'
        $l[5].Message | Should -Match 'deja prise'
        $l[6].Sujet | Should -Be 'Non parcouru : D:\o\prive'
        $l[6].Gravite | Should -Be 'Avertissement'
    }
    It 'aucun outil : avertissement qui annonce que l''index précédent est conservé' {
        $json = '{"ok":true,"dossier":"D:\\vide","dossiers":1,"fichiers_python":0,"outils":[],"non_retenus":[],"erreurs":[]}'
        $l = @(InModuleScope FileManagement.Gui -Parameters @{ r = (& $Script:Reponse $json) } { param($r) ConvertTo-CopieLignesScanOutils -Reponse $r })
        $l[-1].Gravite | Should -Be 'Avertissement'
        $l[-1].Message | Should -Match 'précédents sont conservés'
    }
    It 'échec du moteur : une seule ligne d''erreur avec son message' {
        $json = '{"ok":false,"message":"dossier des outils introuvable : D:\\absent"}'
        $l = @(InModuleScope FileManagement.Gui -Parameters @{ r = (& $Script:Reponse $json $false) } { param($r) ConvertTo-CopieLignesScanOutils -Reponse $r })
        $l.Count | Should -Be 1
        $l[0].Gravite | Should -Be 'Erreur'
        $l[0].Message | Should -Be 'dossier des outils introuvable : D:\absent'
        $sans = [pscustomobject]@{ Reussi = $false; Json = $null; Erreur = 'lancement impossible'; Code = -1 }
        @(InModuleScope FileManagement.Gui -Parameters @{ r = $sans } { param($r) ConvertTo-CopieLignesScanOutils -Reponse $r })[0].Message | Should -Be 'lancement impossible'
    }
}

Describe 'Onglet Outils (fenêtre)' -Skip:(-not $Script:Sta) {
    BeforeAll {
        $Script:Contexte = {
            param($dossier, $profil = 'Admin', $mode = 'Local')
            @{ Dossier = $dossier; Profil = $profil; Utilisateur = 'DOM\essai'; LogBox = $null; Fenetre = $null
                Config = [pscustomobject]@{ Moteur = [pscustomobject]@{ Mode = $mode; Python = ''; Racine = ''; Serveur = ''; ConfigurationJea = ''; DelaiMaxSec = 30 }
                    Journal = [pscustomobject]@{ Dossier = $null; Environnement = 'test' } } }
        }
    }
    It 'le XAML contient les contrôles utilisés par le code' {
        InModuleScope FileManagement.Gui {
            $t = Import-CopieXaml -Nom 'Outils'
            foreach ($n in 'DossierOutils', 'BtnOutilsParcourir', 'BtnOutilsScanner', 'InfoDossierOutils', 'InfoScanOutils', 'CompteurOutils', 'RechercheOutils',
                'GrilleOutils', 'OutilTitre', 'OutilDescription', 'OutilFichier', 'OutilExemple', 'GrilleParametres') {
                $t.FindName($n) | Should -Not -BeNullOrEmpty -Because $n
            }
            $t.Header | Should -Be 'Outils'
            $t.FindName('GrilleOutils').Columns.Count | Should -Be 5
        }
    }
    It 'sans index : explication, grille vide, boutons d''administrateur visibles' {
        $d = Join-Path $TestDrive 'v0'; $null = New-Item -ItemType Directory -Path $d
        InModuleScope FileManagement.Gui -Parameters @{ d = $d; c = $Script:Contexte } {
            param($d, $c)
            $tab = New-CopieVueOutils -Contexte (& $c $d)
            $v = $tab.Tag
            $v.Type | Should -Be 'Outils'
            $v.InfoDossier.Text | Should -Match 'Aucun index des outils'
            $v.Grille.Items.Count | Should -Be 0
            $v.Compteur.Text | Should -Be '0 outil(s)'
            $v.Scanner.Visibility | Should -Be 'Visible'
            $v.Parcourir.Visibility | Should -Be 'Visible'
            $v.Dossier.IsReadOnly | Should -BeFalse
        }
    }
    It 'avec un index : grille, compteur, recherche, détail et début de commande' {
        $d = Join-Path $TestDrive 'v1'; Ecrire (Join-Path $d 'outils.json') $Script:IndexJson
        InModuleScope FileManagement.Gui -Parameters @{ d = $d; c = $Script:Contexte } {
            param($d, $c)
            $v = (New-CopieVueOutils -Contexte (& $c $d)).Tag
            $v.Dossier.Text | Should -Be 'D:\Scripts\outils'
            $v.InfoDossier.Text | Should -Be 'Dossier utilisé par le moteur : D:\Scripts\outils'
            $v.InfoScan.Text | Should -Match 'Dernier scan : 2026-11-13 09:30:00 par DOM\\admin — 2 outil\(s\) indexé\(s\)'
            $v.Grille.Items.Count | Should -Be 2
            $v.Compteur.Text | Should -Be '2 outil(s)'
            $v.Recherche.Text = 'archive'
            $v.Grille.Items.Count | Should -Be 1
            $v.Compteur.Text | Should -Be '1 outil(s) sur 2'
            $v.Grille.SelectedItem = $v.Grille.Items[0]
            $v.Titre.Text | Should -Be '{outil:zip_creer}'
            $v.DescriptionOutil.Text | Should -Be 'Crée une archive zip.'
            $v.FichierOutil.Text | Should -Be 'Fichier : D:\Scripts\outils\compression\zip_creer.py'
            $v.Exemple.Text | Should -Be '["{outil:zip_creer}", "--sortie", "<ARCHIVE.zip>"]'
            $v.GrilleParametres.Items.Count | Should -Be 2
            $v.Recherche.Text = 'introuvable-xyz'
            $v.Grille.Items.Count | Should -Be 0
            $v.Titre.Text | Should -Be 'Aucun outil sélectionné'
            $v.GrilleParametres.Items.Count | Should -Be 0
            $v.Recherche.Text = ''
            $v.Grille.Items.Count | Should -Be 2
        }
    }
    It 'réglage vide : le dossier outils du moteur' {
        $d = Join-Path $TestDrive 'v2'; Ecrire (Join-Path $d 'outils.json') ($Script:IndexJson -replace '"dossier_outils": "[^"]*"', '"dossier_outils": ""')
        InModuleScope FileManagement.Gui -Parameters @{ d = $d; c = $Script:Contexte } {
            param($d, $c)
            $v = (New-CopieVueOutils -Contexte (& $c $d)).Tag
            $v.InfoDossier.Text | Should -Match 'dossier « outils » situé à la racine du moteur'
            $v.Dossier.Text | Should -Be ''
        }
    }
    It 'compte non administrateur : consultation seule ; moteur distant : pas de bouton Parcourir' {
        $d = Join-Path $TestDrive 'v3'; Ecrire (Join-Path $d 'outils.json') $Script:IndexJson
        InModuleScope FileManagement.Gui -Parameters @{ d = $d; c = $Script:Contexte } {
            param($d, $c)
            $v = (New-CopieVueOutils -Contexte (& $c $d 'Lecture')).Tag
            $v.Scanner.Visibility | Should -Be 'Collapsed'
            $v.Parcourir.Visibility | Should -Be 'Collapsed'
            $v.Dossier.IsReadOnly | Should -BeTrue
            $v.Grille.Items.Count | Should -Be 2
            $a = (New-CopieVueOutils -Contexte (& $c $d 'Admin' 'Distant')).Tag
            $a.Scanner.Visibility | Should -Be 'Visible'
            $a.Parcourir.Visibility | Should -Be 'Collapsed'
        }
    }
}

Describe 'Scan des outils par le moteur' -Skip:(-not ($Script:Sta -and $Script:PythonDisponible)) {
    BeforeAll {
        Add-Type -AssemblyName PresentationFramework
        $Script:Cfg = [pscustomobject]@{
            Moteur = [pscustomobject]@{ Mode = 'Local'; Python = $env:COPIE_TEST_PYTHON; Racine = $Script:RacineMoteur; ConfigurationJea = ''; Serveur = ''; DelaiMaxSec = 60 }
            Journal = [pscustomobject]@{ Dossier = $null; Environnement = 'test' } }
        Mock Show-CopieOperation { } -ModuleName FileManagement.Gui
    }
    BeforeEach {
        function Script:LireJournal {
            @(Get-ChildItem -LiteralPath $Script:DossierJournal -Filter '*.jsonl' -ErrorAction SilentlyContinue | ForEach-Object {
                    [System.IO.File]::ReadAllLines($_.FullName, (New-Object System.Text.UTF8Encoding($false))) } |
                    Where-Object { $_ } | ForEach-Object { $_ | ConvertFrom-Json })
        }
        $Script:Param = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        $null = New-Item -ItemType Directory -Path $Script:Param
        $Script:Outils = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        Ecrire (Join-Path $Script:Outils 'compression\zip_x.py') (EnteteOutil 'zip_x' 'Crée une archive.' @('--sortie ARCHIVE | obligatoire | archive à créer'))
        Ecrire (Join-Path $Script:Outils 'controle\attente.py') (EnteteOutil 'attente' 'Attend.')
        Ecrire (Join-Path $Script:Outils 'commun\module.py') "import os`n"
        Ecrire (Join-Path $Script:Outils 'commun\lib.py') "# bibliotheque: Aides communes.`nimport os`n"
        Ecrire (Join-Path $Script:Outils 'casse.py') (EnteteOutil 'Mauvais Nom')
        $Script:DossierJournal = Join-Path $TestDrive ('journal-' + [guid]::NewGuid().ToString('N'))
        $Script:Cfg.Journal.Dossier = $Script:DossierJournal
        $Script:Fenetre = New-Object System.Windows.Window
        $Script:Ctx = @{ Dossier = $Script:Param; Profil = 'Admin'; Utilisateur = 'DOM\essai'; LogBox = $null; Fenetre = $Script:Fenetre; Config = $Script:Cfg }
    }
    It 'enregistre le dossier : outils.json écrit, grille remplie, fenêtre et journal détaillent retenus et non retenus' {
        $r = InModuleScope FileManagement.Gui -Parameters @{ c = $Script:Ctx; o = $Script:Outils } {
            param($c, $o)
            $v = (New-CopieVueOutils -Contexte $c).Tag
            $v.Dossier.Text = $o
            Invoke-CopieScanOutils -Vue $v
        }
        $r.Enregistre | Should -BeTrue
        $index = InModuleScope FileManagement.Gui -Parameters @{ d = $Script:Param } { param($d) Get-CopieIndexOutils -Dossier $d }
        $index.DossierConfigure | Should -Be $Script:Outils
        $index.ScannePar | Should -Be 'DOM\essai'
        ($index.Outils | ForEach-Object Nom) -join ',' | Should -Be 'attente,zip_x'
        $zip = $index.Outils | Where-Object Nom -eq 'zip_x'
        $zip.Description | Should -Be 'Crée une archive.'
        $zip.Obligatoires | Should -Be '--sortie ARCHIVE'
        $zip.SousDossier | Should -Be 'compression'
        @(Get-ChildItem -LiteralPath $Script:Param).Count | Should -Be 1
        $lignes = $r.Lignes
        Should -Invoke Show-CopieOperation -ModuleName FileManagement.Gui -Exactly -Times 1 -ParameterFilter { $Titre -eq 'Scan des outils' -and $Debut -eq 'Dossier des outils enregistré.' }
        ($lignes | Where-Object { $_.Sujet -like 'Outil retenu*' }).Count | Should -Be 2
        ($lignes | Where-Object { $_.Sujet -eq 'Non retenu : commun\module.py' }).Gravite | Should -Be 'Information'
        $biblio = $lignes | Where-Object { $_.Sujet -eq 'Bibliothèque : commun\lib.py' }
        $biblio.Gravite | Should -Be 'Information'
        $biblio.Message | Should -Be 'Aides communes.'
        ($lignes | Where-Object { $_.Sujet -like 'Non retenu : commun\lib.py' }) | Should -BeNullOrEmpty
        $casse = $lignes | Where-Object { $_.Sujet -eq 'Non retenu : casse.py' }
        $casse.Gravite | Should -Be 'Avertissement'
        $casse.Message | Should -Match 'nom d''outil ''Mauvais Nom'' refuse'
        ($lignes | Where-Object { $_.Sujet -eq 'Index enregistré' }).Message | Should -Match 'outils.json'
        $journal = @(Script:LireJournal)
        $scan = $journal | Where-Object { $_.context.event -eq 'outils_scan' }
        $scan.context.retenus | Should -Be 2
        $scan.context.non_retenus | Should -Be 2
        $scan.context.bibliotheques | Should -Be 1
        @($journal | Where-Object { $_.context.event -eq 'outil_bibliotheque' }).Count | Should -Be 1
        @($journal | Where-Object { $_.context.event -eq 'outil_retenu' }).Count | Should -Be 2
        ($journal | Where-Object { $_.context.event -eq 'outil_retenu' } | Select-Object -First 1).message | Should -Match '^Outil retenu : \{outil:\w+\}'
        $nr = @($journal | Where-Object { $_.context.event -eq 'outil_non_retenu' })
        $nr.Count | Should -Be 2
        ($nr | Where-Object { $_.message -like '*casse.py*' }).level | Should -Be 'WARNING'
        ($nr | Where-Object { $_.message -like '*module.py*' }).level | Should -Be 'INFO'
    }
    It 'le moteur lit l''index enregistré : une règle appelle l''outil par sa variable' {
        InModuleScope FileManagement.Gui -Parameters @{ c = $Script:Ctx; o = $Script:Outils } {
            param($c, $o)
            $v = (New-CopieVueOutils -Contexte $c).Tag
            $v.Dossier.Text = $o
            $null = Invoke-CopieScanOutils -Vue $v
        }
        $entete = @{ version = 1; environnement = 'essai'; code_environnement = 'test'; base = (Join-Path $TestDrive 'essai.db') } | ConvertTo-Json -Compress
        $regle = @{ id = 'r1'; source = (Join-Path $TestDrive 's'); cible = (Join-Path $TestDrive 'c'); mode = 'copie'
            planification = @{ type = 'quotidien'; heure = '07:00'; jours = 'tous' }
            programmes = @{ avant_lot = @{ commande = @('{outil:attente}', '--aide-inconnue'); timeout_sec = 30 } } } | ConvertTo-Json -Compress -Depth 6
        $f = Join-Path $Script:Param 'essai.jsonl'
        Ecrire $f ($entete + "`n" + $regle + "`n")
        $r = InModuleScope FileManagement.Gui -Parameters @{ c = $Script:Cfg; f = $f } { param($c, $f) Invoke-CopieMoteur -Config $c -Fichier $f -Argument @('--verifier', '--syntaxe-seule') }
        $r.Reussi | Should -BeTrue -Because ($r.Sortie + ' ' + $r.Erreur)
        Ecrire $f ($entete + "`n" + ($regle -replace 'attente', 'inexistant') + "`n")
        $r = InModuleScope FileManagement.Gui -Parameters @{ c = $Script:Cfg; f = $f } { param($c, $f) Invoke-CopieMoteur -Config $c -Fichier $f -Argument @('--verifier', '--syntaxe-seule') }
        $r.Reussi | Should -BeFalse
        ($r.Json.refus | ForEach-Object { $_.message }) -join ' ' | Should -Match 'outil inconnu : \{outil:inexistant\} \(outils indexes : attente, zip_x\)'
    }
    It 'dossier introuvable : erreur dans la fenêtre et le journal, rien d''écrit' {
        $r = InModuleScope FileManagement.Gui -Parameters @{ c = $Script:Ctx; o = (Join-Path $TestDrive 'absent') } {
            param($c, $o)
            $v = (New-CopieVueOutils -Contexte $c).Tag
            Invoke-CopieScanOutils -Vue $v -Dossier $o
        }
        $r.Enregistre | Should -BeFalse
        Test-Path -LiteralPath (Join-Path $Script:Param 'outils.json') | Should -BeFalse
        $r.Lignes[0].Gravite | Should -Be 'Erreur'
        $r.Lignes[0].Message | Should -Match 'dossier des outils introuvable'
        Should -Invoke Show-CopieOperation -ModuleName FileManagement.Gui -Exactly -Times 1 -ParameterFilter { $Debut -match 'rien n''a été enregistré' }
        (Script:LireJournal | Where-Object { $_.context.event -eq 'outils_scan' }).level | Should -Be 'ERROR'
    }
    It 'dossier sans aucun outil : l''index précédent est conservé' {
        InModuleScope FileManagement.Gui -Parameters @{ c = $Script:Ctx; o = $Script:Outils } {
            param($c, $o)
            $v = (New-CopieVueOutils -Contexte $c).Tag
            $null = Invoke-CopieScanOutils -Vue $v -Dossier $o
        }
        $avant = [System.IO.File]::ReadAllText((Join-Path $Script:Param 'outils.json'))
        Remove-Item -LiteralPath $Script:DossierJournal -Recurse -Force
        $vide = Join-Path $TestDrive 'vide'; $null = New-Item -ItemType Directory -Path $vide
        $r = InModuleScope FileManagement.Gui -Parameters @{ c = $Script:Ctx; o = $vide } {
            param($c, $o)
            $v = (New-CopieVueOutils -Contexte $c).Tag
            Invoke-CopieScanOutils -Vue $v -Dossier $o
        }
        $r.Enregistre | Should -BeFalse
        [System.IO.File]::ReadAllText((Join-Path $Script:Param 'outils.json')) | Should -Be $avant
        Should -Invoke Show-CopieOperation -ModuleName FileManagement.Gui -Exactly -Times 1 -ParameterFilter { $Debut -match 'Aucun outil trouvé' }
        (Script:LireJournal | Where-Object { $_.context.event -eq 'outils_scan' }).level | Should -Be 'WARNING'
    }
    It 'dossier vide dans l''onglet : le dossier outils du moteur (les 38 outils du dépôt)' {
        $r = InModuleScope FileManagement.Gui -Parameters @{ c = $Script:Ctx } {
            param($c)
            $v = (New-CopieVueOutils -Contexte $c).Tag
            $v.Dossier.Text = ''
            $null = Invoke-CopieScanOutils -Vue $v
            @{ Compteur = $v.Compteur.Text; Info = $v.InfoDossier.Text }
        }
        $r.Compteur | Should -Be '38 outil(s)'
        $r.Info | Should -Match 'dossier « outils » situé à la racine du moteur'
        (InModuleScope FileManagement.Gui -Parameters @{ d = $Script:Param } { param($d) (Get-CopieIndexOutils -Dossier $d).DossierConfigure }) | Should -Be ''
    }
}
