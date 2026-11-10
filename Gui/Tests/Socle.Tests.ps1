#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
# Étape A : configuration, droits, lecture du dossier de paramétrage, mise en forme.
# Aucun test ne contacte un serveur, un AD ou une base : tout se passe dans $TestDrive.

BeforeAll {
    $Script:Module = Join-Path $PSScriptRoot '..\Copie.Gui\Copie.Gui.psd1'
    Import-Module $Script:Module -Force
    $Script:Utf8SansBom = New-Object System.Text.UTF8Encoding($false)
    $Script:Ecrire = {
        param($chemin, [string[]]$lignes, [bool]$bom = $false)
        $texte = ($lignes -join "`n") + "`n"
        $octets = $Script:Utf8SansBom.GetBytes($texte)
        if ($bom) { $octets = [byte[]](0xEF, 0xBB, 0xBF) + $octets }
        [System.IO.File]::WriteAllBytes($chemin, $octets)
    }
}

Describe 'Get-CopieConfig' {
    BeforeAll {
        $Script:ConfigValide = @'
@{
    Acces = @{ GroupesAdmin = @('DOMAINE\GG_Copie_Admins') }
    Moteur = @{ Mode = 'Local'; Python = 'p.exe'; Racine = 'r' }
}
'@
    }
    It 'lit une configuration valide et applique les valeurs de secours' {
        $f = Join-Path $TestDrive 'ok.psd1'
        Set-Content -LiteralPath $f -Value $Script:ConfigValide
        $c = InModuleScope Copie.Gui -Parameters @{ f = $f } { param($f) Get-CopieConfig -Chemin $f }
        $c.Acces.GroupesAdmin | Should -Be 'DOMAINE\GG_Copie_Admins'
        $c.Moteur.DelaiMaxSec | Should -Be 120
        $c.Parametrage.Filtre | Should -Be '*.jsonl'
        $c.Parametrage.VersionsSupportees | Should -Be 1
    }
    It 'refuse une configuration sans groupe administrateur' {
        $f = Join-Path $TestDrive 'sans-groupe.psd1'
        Set-Content -LiteralPath $f -Value "@{ Acces = @{ GroupesAdmin = @() }; Moteur = @{ Python = 'p'; Racine = 'r' } }"
        { InModuleScope Copie.Gui -Parameters @{ f = $f } { param($f) Get-CopieConfig -Chemin $f } } | Should -Throw '*GroupesAdmin*'
    }
    It 'refuse une clé ou une section inconnue (faute de frappe)' {
        $f = Join-Path $TestDrive 'inconnue.psd1'
        Set-Content -LiteralPath $f -Value "@{ Acces = @{ GroupesAdmin = @('G'); Groupe = 'x' }; Moteur = @{ Python = 'p'; Racine = 'r' }; Autre = @{} }"
        $erreur = $null
        try { InModuleScope Copie.Gui -Parameters @{ f = $f } { param($f) Get-CopieConfig -Chemin $f } } catch { $erreur = $_.Exception.Message }
        $erreur | Should -Match 'clé inconnue : Acces.Groupe'
        $erreur | Should -Match 'section inconnue : Autre'
    }
    It 'exige le serveur en mode Distant, et Python/Racine sans point d''accès JEA' {
        $f = Join-Path $TestDrive 'distant.psd1'
        Set-Content -LiteralPath $f -Value "@{ Acces = @{ GroupesAdmin = @('G') }; Moteur = @{ Mode = 'Distant' } }"
        $erreur = $null
        try { InModuleScope Copie.Gui -Parameters @{ f = $f } { param($f) Get-CopieConfig -Chemin $f } } catch { $erreur = $_.Exception.Message }
        $erreur | Should -Match 'Moteur.Serveur'
        $erreur | Should -Match 'Moteur.Python'
    }
    It 'accepte un point d''accès JEA sans Python ni Racine' {
        $f = Join-Path $TestDrive 'jea.psd1'
        Set-Content -LiteralPath $f -Value "@{ Acces = @{ GroupesAdmin = @('G') }; Moteur = @{ Mode = 'Distant'; Serveur = 'S'; ConfigurationJea = 'CopieFichiers' } }"
        $c = InModuleScope Copie.Gui -Parameters @{ f = $f } { param($f) Get-CopieConfig -Chemin $f }
        $c.Moteur.ConfigurationJea | Should -Be 'CopieFichiers'
    }
    It 'refuse la JEA en mode Local, un mode inconnu et un fichier absent' {
        $f = Join-Path $TestDrive 'jealocal.psd1'
        Set-Content -LiteralPath $f -Value "@{ Acces = @{ GroupesAdmin = @('G') }; Moteur = @{ Mode = 'Local'; ConfigurationJea = 'X' } }"
        { InModuleScope Copie.Gui -Parameters @{ f = $f } { param($f) Get-CopieConfig -Chemin $f } } | Should -Throw '*réservé au mode Distant*'
        $g = Join-Path $TestDrive 'mode.psd1'
        Set-Content -LiteralPath $g -Value "@{ Acces = @{ GroupesAdmin = @('G') }; Moteur = @{ Mode = 'Cloud'; Python = 'p'; Racine = 'r' } }"
        { InModuleScope Copie.Gui -Parameters @{ f = $g } { param($f) Get-CopieConfig -Chemin $f } } | Should -Throw '*Cloud*'
        { InModuleScope Copie.Gui { Get-CopieConfig -Chemin 'Z:\n\existe\pas.psd1' } } | Should -Throw '*introuvable*'
    }
    It 'accepte la configuration fournie avec l''outil' {
        $c = InModuleScope Copie.Gui -Parameters @{ f = (Join-Path $PSScriptRoot '..\Gestion-Copie.config.psd1') } { param($f) Get-CopieConfig -Chemin $f }
        $c.Moteur.Mode | Should -Be 'Local'
    }
}

Describe 'Get-CopieProfilAcces' {
    BeforeAll {
        $Script:Cfg = [pscustomobject]@{ Acces = [pscustomobject]@{ GroupesAdmin = @('DOMAINE\GG_Copie_Admins', 'Operateurs', 'S-1-5-21-1-2-3-500') } }
    }
    It 'donne Admin pour le nom complet, sans tenir compte de la casse' {
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg } { param($c) Get-CopieProfilAcces -Config $c -Groupe @('domaine\gg_copie_admins') } | Should -Be 'Admin'
    }
    It 'donne Admin pour un groupe sans domaine, quel que soit le domaine' {
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg } { param($c) Get-CopieProfilAcces -Config $c -Groupe @('AUTRE\Operateurs') } | Should -Be 'Admin'
    }
    It 'donne Admin pour un SID' {
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg } { param($c) Get-CopieProfilAcces -Config $c -Groupe @('S-1-5-21-1-2-3-500') } | Should -Be 'Admin'
    }
    It 'donne Lecture sinon, y compris sans aucun groupe, et ne confond pas un nom proche' {
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg } { param($c) Get-CopieProfilAcces -Config $c -Groupe @('DOMAINE\GG_Copie_Admins2', 'X\Operateurs2') } | Should -Be 'Lecture'
        InModuleScope Copie.Gui -Parameters @{ c = $Script:Cfg } { param($c) Get-CopieProfilAcces -Config $c -Groupe @() } | Should -Be 'Lecture'
    }
    It 'lit le jeton Windows de l''utilisateur courant par défaut' {
        $moi = [Security.Principal.WindowsIdentity]::GetCurrent().Groups | Select-Object -First 1
        $cfg = [pscustomobject]@{ Acces = [pscustomobject]@{ GroupesAdmin = @($moi.Value) } }
        InModuleScope Copie.Gui -Parameters @{ c = $cfg } { param($c) Get-CopieProfilAcces -Config $c } | Should -Be 'Admin'
    }
}

Describe 'Get-CopieEnvironnement' {
    BeforeAll {
        $Script:Cfg = [pscustomobject]@{ Parametrage = [pscustomobject]@{ Filtre = '*.jsonl'; VersionsSupportees = @(1) } }
        $Script:Lister = { param($d, $c) InModuleScope Copie.Gui -Parameters @{ d = $d; c = $c } { param($d, $c) Get-CopieEnvironnement -Dossier $d -Config $c } }
    }
    BeforeEach {
        $Script:D = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        $null = New-Item -ItemType Directory -Path $Script:D
    }
    It 'charge un fichier par environnement, avec ou sans BOM, et compte les règles' {
        & $Script:Ecrire (Join-Path $Script:D 'production.jsonl') @('{"version": 1, "environnement": "production", "base": "b"}', '', '{"id": "a"}', '{"id": "b"}')
        & $Script:Ecrire (Join-Path $Script:D 'recette.jsonl') @('{"version": 1, "environnement": "recette", "base": "b"}', '{"id": "é"}') $true
        $liste = & $Script:Lister $Script:D $Script:Cfg
        @($liste).Count | Should -Be 2
        ($liste | Where-Object Nom -eq 'production').Parametrage.Regles.Count | Should -Be 2
        ($liste | Where-Object Nom -eq 'recette').Parametrage.Regles[0].id | Should -Be 'é'
        $liste | ForEach-Object { $_.Modifiable | Should -BeTrue }
    }
    It 'met en lecture seule un environnement différent du nom du fichier' {
        & $Script:Ecrire (Join-Path $Script:D 'ancien.jsonl') @('{"version": 1, "environnement": "autre", "base": "b"}')
        $e = @(& $Script:Lister $Script:D $Script:Cfg)[0]
        $e.Nom | Should -Be 'autre'
        $e.Modifiable | Should -BeFalse
        $e.Message | Should -Match 'diffère du nom du fichier'
    }
    It 'met en lecture seule une version de format inconnue ou absente' {
        & $Script:Ecrire (Join-Path $Script:D 'v9.jsonl') @('{"version": 9, "environnement": "v9", "base": "b"}')
        & $Script:Ecrire (Join-Path $Script:D 'sansversion.jsonl') @('{"environnement": "sansversion", "base": "b"}')
        $liste = & $Script:Lister $Script:D $Script:Cfg
        ($liste | Where-Object Nom -eq 'v9').Message | Should -Match 'version de format non prise en charge : 9'
        ($liste | Where-Object Nom -eq 'sansversion').Message | Should -Match 'absente'
    }
    It 'met en lecture seule les deux fichiers qui déclarent le même environnement' {
        & $Script:Ecrire (Join-Path $Script:D 'production.jsonl') @('{"version": 1, "environnement": "production", "base": "b"}')
        & $Script:Ecrire (Join-Path $Script:D 'copie.jsonl') @('{"version": 1, "environnement": "production", "base": "b"}')
        $liste = & $Script:Lister $Script:D $Script:Cfg
        ($liste | Where-Object Fichier -like '*production.jsonl').Message | Should -Match 'aussi déclaré par copie.jsonl'
        ($liste | Where-Object Fichier -like '*copie.jsonl').Modifiable | Should -BeFalse
    }
    It 'signale un JSON invalide avec son numéro de ligne, sans perdre les autres lignes' {
        & $Script:Ecrire (Join-Path $Script:D 'production.jsonl') @('{"version": 1, "environnement": "production", "base": "b"}', '{"id": "a"', '{"id": "b"}')
        $e = @(& $Script:Lister $Script:D $Script:Cfg)[0]
        $e.Modifiable | Should -BeFalse
        $e.Message | Should -Match 'ligne 2 : JSON invalide'
        $e.Parametrage.Regles.Count | Should -Be 1
    }
    It 'signale un fichier vide, et ignore les autres extensions' {
        [System.IO.File]::WriteAllBytes((Join-Path $Script:D 'vide.jsonl'), [byte[]]@())
        Set-Content -LiteralPath (Join-Path $Script:D 'notes.txt') -Value 'x'
        $liste = @(& $Script:Lister $Script:D $Script:Cfg)
        $liste.Count | Should -Be 1
        $liste[0].Message | Should -Match 'fichier vide'
    }
    It 'refuse un dossier absent et renvoie une liste vide pour un dossier sans fichier' {
        { & $Script:Lister (Join-Path $Script:D 'absent') $Script:Cfg } | Should -Throw '*introuvable*'
        @(& $Script:Lister $Script:D $Script:Cfg).Count | Should -Be 0
    }
    It 'donne une empreinte stable du contenu' {
        $f = Join-Path $Script:D 'production.jsonl'
        & $Script:Ecrire $f @('{"version": 1, "environnement": "production", "base": "b"}')
        $a = (& $Script:Lister $Script:D $Script:Cfg)[0].Parametrage.Empreinte
        $a | Should -Match '^[0-9a-f]{64}$'
        ((& $Script:Lister $Script:D $Script:Cfg)[0].Parametrage.Empreinte) | Should -Be $a
        & $Script:Ecrire $f @('{"version": 1, "environnement": "production", "base": "c"}')
        ((& $Script:Lister $Script:D $Script:Cfg)[0].Parametrage.Empreinte) | Should -Not -Be $a
    }
}

Describe 'Mise en forme' {
    It 'convertit les secondes UTC du moteur en date locale, « — » si absente' {
        InModuleScope Copie.Gui {
            Format-CopieDate -Secondes $null | Should -Be ([string][char]0x2014)
            $attendu = [DateTimeOffset]::FromUnixTimeSeconds(1793609412).LocalDateTime.ToString('dd/MM/yyyy HH:mm:ss')
            Format-CopieDate -Secondes 1793609412 | Should -Be $attendu
        }
    }
    It 'écrit les durées en unités lisibles' {
        InModuleScope Copie.Gui {
            Format-CopieDuree 45 | Should -Be '45 s'
            Format-CopieDuree 300 | Should -Be '5 min'
            Format-CopieDuree 3600 | Should -Be '1 h'
            Format-CopieDuree 5400 | Should -Be '1 h 30'
            Format-CopieDuree 86400 | Should -Be '1 j'
            Format-CopieDuree 90 | Should -Be '90 s'
        }
    }
    It 'décrit les trois types de planification' {
        InModuleScope Copie.Gui {
            $i = '{"type":"intervalle","frequence_sec":300,"debut":"05:00","fin":"19:00","jours":"lun-ven"}' | ConvertFrom-Json
            Format-CopiePlanification $i | Should -Be 'toutes les 5 min de 05:00 à 19:00, lun-ven'
            $q = '{"type":"quotidien","heure":"07:15"}' | ConvertFrom-Json
            Format-CopiePlanification $q | Should -Be 'à 07:15, tous les jours'
            Format-CopiePlanification ('{"type":"apres_dependances"}' | ConvertFrom-Json) | Should -Be 'après ses dépendances'
            Format-CopiePlanification $null | Should -Be 'non planifiée'
        }
    }
    It 'donne une couleur à chaque statut du contrat, et une couleur neutre aux autres' {
        InModuleScope Copie.Gui {
            foreach ($s in 'SUCCES', 'WARNING', 'ERREUR', 'ACQUITTEE', 'ARRETEE', 'EN_COURS', 'EN_ATTENTE', 'BLOQUEE') {
                Get-CopieCouleurStatut $s | Should -Match '^#[0-9A-F]{6}$'
                Get-CopieCouleurStatut $s | Should -Not -Be (Get-CopieCouleurStatut 'INCONNU')
            }
            Get-CopieCouleurStatut 'INACTIVE' | Should -Be (Get-CopieCouleurStatut 'JAMAIS_LANCEE')
        }
    }
    It 'lit une propriété absente sans échouer' {
        InModuleScope Copie.Gui {
            $o = '{"a":1}' | ConvertFrom-Json
            Get-CopieValeur $o 'a' | Should -Be 1
            Get-CopieValeur $o 'b' 'x' | Should -Be 'x'
            Get-CopieValeur $null 'b' 'y' | Should -Be 'y'
        }
    }
    It 'construit la ligne de grille avec et sans état du moteur' {
        InModuleScope Copie.Gui {
            $regle = '{"id":"r1","mode":"copie","source":"S","cible":"C","actif":false,"planification":{"type":"quotidien","heure":"07:00"}}' | ConvertFrom-Json
            $sans = ConvertTo-CopieLigneRegle -Regle $regle -Etat $null
            $sans.Statut | Should -Be 'INACTIVE'
            $sans.Actif | Should -Be 'Non'
            $sans.Planification | Should -Be 'à 07:00, tous les jours'
            $etat = '{"statut":"ERREUR","planification":"du moteur","motif":"m","dernier_lancement":1793609412,"prochain_creneau":null}' | ConvertFrom-Json
            $avec = ConvertTo-CopieLigneRegle -Regle $regle -Etat $etat
            $avec.Statut | Should -Be 'ERREUR'
            $avec.Planification | Should -Be 'du moteur'
            $avec.StatutCouleur | Should -Be (Get-CopieCouleurStatut 'ERREUR')
            $avec.ProchainCreneau | Should -Be ([string][char]0x2014)
        }
    }
    It 'regroupe le détail d''une règle et tolère les champs absents' {
        InModuleScope Copie.Gui {
            $regle = '{"id":"r1","source":"S","cible":"C","mode":"copie","programmes":{"apres_lot":{"commande":["python","x.py"],"timeout_sec":60}}}' | ConvertFrom-Json
            $g = ConvertTo-CopieGroupeRegle -Regle $regle
            $g.Titre | Should -Contain 'Sélection'
            $g.Titre | Should -Contain 'Purge'
            $prog = $g | Where-Object Titre -like 'Programmes*'
            ($prog.Lignes | Where-Object Libelle -eq 'apres_lot').Valeur | Should -Match 'python, x.py'
            ($prog.Lignes | Where-Object Libelle -eq 'avant_lot').Valeur | Should -Be ([string][char]0x2014)
            $sel = $g | Where-Object Titre -eq 'Sélection'
            ($sel.Lignes | Where-Object Libelle -eq 'Masque').Valeur | Should -Be 'défaut du moteur'
        }
    }
    It 'décrit l''état d''une règle, ou son indisponibilité' {
        InModuleScope Copie.Gui {
            (ConvertTo-CopieGroupeEtat -Etat $null)[0].Lignes[0].Valeur | Should -Match 'indisponible'
            $etat = '{"statut":"WARNING","en_cours":false,"derniere_erreur":{"le":1793609412,"situation":"s","message":"m"},"archivage_degrade":true,"actions_en_attente":12,"livraisons_incertaines":0}' | ConvertFrom-Json
            $g = ConvertTo-CopieGroupeEtat -Etat $etat
            $g.Titre | Should -Contain 'Dernière erreur'
            (($g | Where-Object Titre -like 'Drapeaux*').Lignes | Where-Object Libelle -eq 'Archivage dégradé').Valeur | Should -Be 'Oui'
            (($g | Where-Object Titre -like 'Drapeaux*').Lignes | Where-Object Libelle -eq 'Actions en attente').Valeur | Should -Be '12'
        }
    }
}
