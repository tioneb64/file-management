#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
# Chemins racine (environnement, sources, cibles), modes suppression / count / size, lignes de la grille (aspect, chemins
# complets). Aucun appel du moteur : ces fonctions ne font que lire le fichier de paramétrage et composer l'affichage.

BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..\Copie.Gui\Copie.Gui.psd1') -Force
    $Script:Utf8 = New-Object System.Text.UTF8Encoding($false)
}

Describe 'Resolve-CopieChemin' {
    It 'place un chemin partiel sous la racine, avec ou sans séparateur final' {
        InModuleScope Copie.Gui {
            Resolve-CopieChemin -Chemin 'LOGS' -Racine 'D:\r\preprod' | Should -Be 'D:\r\preprod\LOGS'
            Resolve-CopieChemin -Chemin 'LOGS' -Racine 'D:\r\preprod\' | Should -Be 'D:\r\preprod\LOGS'
            Resolve-CopieChemin -Chemin 'BDD\preprod.db' -Racine 'D:\r\preprod\' | Should -Be 'D:\r\preprod\BDD\preprod.db'
            Resolve-CopieChemin -Chemin '\TMP' -Racine 'D:\r\preprod' | Should -Be 'D:\r\preprod\TMP'
            Resolve-CopieChemin -Chemin 'a/b' -Racine 'D:/r' | Should -Be 'D:\r\a\b'
        }
    }
    It 'conserve un chemin complet (lecteur ou partage réseau) et un chemin sans racine' {
        InModuleScope Copie.Gui {
            Resolve-CopieChemin -Chemin 'D:\LOGS' -Racine 'D:\r\preprod\' | Should -Be 'D:\LOGS'
            Resolve-CopieChemin -Chemin 'e:/logs' -Racine 'D:\r' | Should -Be 'e:/logs'
            Resolve-CopieChemin -Chemin '\\srv\partage\x' -Racine 'D:\r' | Should -Be '\\srv\partage\x'
            Resolve-CopieChemin -Chemin 'LOGS' -Racine '' | Should -Be 'LOGS'
            Resolve-CopieChemin -Chemin '' -Racine 'D:\r' | Should -Be ''
            Resolve-CopieChemin -Chemin $null -Racine $null | Should -Be ''
        }
    }
    It 'fonctionne avec un lecteur absent de la machine' {
        InModuleScope Copie.Gui {
            Resolve-CopieChemin -Chemin 'LOGS' -Racine 'Q:\inexistant\racine' | Should -Be 'Q:\inexistant\racine\LOGS'
        }
    }
}

Describe 'Chemins complets d''un environnement et de ses règles' {
    It 'résout la base, les journaux, le travail et les racines des règles' {
        InModuleScope Copie.Gui {
            $e = '{"version":1,"environnement":"preprod","racine":"D:\\t\\preprod\\","racine_source":"SRC","racine_cible":"E:\\dest","base":"BDD\\preprod.db","dossier_logs":"LOGS","dossier_travail":"F:\\tmp"}' | ConvertFrom-Json
            $c = Get-CopieCheminsEnvironnement -Entete $e
            $c.Base | Should -Be 'D:\t\preprod\BDD\preprod.db'
            $c.DossierLogs | Should -Be 'D:\t\preprod\LOGS'
            $c.DossierTravail | Should -Be 'F:\tmp'
            $c.RacineSource | Should -Be 'D:\t\preprod\SRC'
            $c.RacineCible | Should -Be 'E:\dest'
        }
    }
    It 'journaux et travail par défaut : à côté de la base, comme le moteur' {
        InModuleScope Copie.Gui {
            $e = '{"version":1,"environnement":"preprod","racine":"D:\\t","base":"BDD\\p.db"}' | ConvertFrom-Json
            $c = Get-CopieCheminsEnvironnement -Entete $e
            $c.DossierLogs | Should -Be 'D:\t\BDD\logs'
            $c.DossierTravail | Should -Be 'D:\t\BDD\travail'
        }
    }
    It 'place la source sous la racine des sources, la cible sous celle des cibles, sinon sous la racine de l''environnement' {
        InModuleScope Copie.Gui {
            $regle = '{"id":"r","mode":"copie","source":"IN","cible":"OUT","dossier_temporaire":"TMP"}' | ConvertFrom-Json
            $avec = '{"version":1,"racine":"D:\\t","racine_source":"SRC","racine_cible":"E:\\dest","base":"b.db"}' | ConvertFrom-Json
            $r = Get-CopieCheminsRegle -Regle $regle -Entete $avec
            $r.Source | Should -Be 'D:\t\SRC\IN'
            $r.Cible | Should -Be 'E:\dest\OUT'
            $r.DossierTemporaire | Should -Be 'D:\t\TMP'
            $sans = '{"version":1,"racine":"D:\\t","base":"b.db"}' | ConvertFrom-Json
            $r2 = Get-CopieCheminsRegle -Regle $regle -Entete $sans
            $r2.Source | Should -Be 'D:\t\IN'
            $r2.Cible | Should -Be 'D:\t\OUT'
        }
    }
    It 'conserve un chemin de règle complet et rend un chemin partiel sans racine tel quel' {
        InModuleScope Copie.Gui {
            $regle = '{"id":"r","mode":"copie","source":"C:\\libre\\in","cible":"OUT"}' | ConvertFrom-Json
            $e = '{"version":1,"racine":"D:\\t","racine_source":"SRC","base":"b.db"}' | ConvertFrom-Json
            (Get-CopieCheminsRegle -Regle $regle -Entete $e).Source | Should -Be 'C:\libre\in'
            (Get-CopieCheminsRegle -Regle $regle -Entete $null).Cible | Should -Be 'OUT'
        }
    }
}

Describe 'Saisie d''un environnement avec une racine' {
    It 'accepte des chemins partiels quand la racine les complète, les refuse sinon' {
        InModuleScope Copie.Gui {
            @(Test-CopieSaisieEnvironnement -Saisie @{ Nom = 'preprod'; Racine = 'D:\t\preprod\'; Base = 'BDD\preprod.db'; DossierLogs = 'LOGS'; DossierTravail = 'TMP' }).Count | Should -Be 0
            (Test-CopieSaisieEnvironnement -Saisie @{ Nom = 'preprod'; Base = 'BDD\preprod.db' }) -join ' ' | Should -Match 'racine'
            (Test-CopieSaisieEnvironnement -Saisie @{ Nom = 'preprod'; Base = 'D:\b.db'; DossierLogs = 'LOGS' }) -join ' ' | Should -Match 'journaux.*racine'
            (Test-CopieSaisieEnvironnement -Saisie @{ Nom = 'preprod'; Racine = 'preprod'; Base = 'D:\b.db' }) -join ' ' | Should -Match 'racine de l''environnement doit être un chemin complet'
            (Test-CopieSaisieEnvironnement -Saisie @{ Nom = 'preprod'; Base = 'D:\b.db'; RacineSource = 'SRC' }) -join ' ' | Should -Match 'racine des sources'
        }
    }
    It 'un chemin complet reste complet même avec une racine' {
        InModuleScope Copie.Gui {
            @(Test-CopieSaisieEnvironnement -Saisie @{ Nom = 'preprod'; Racine = 'D:\t\preprod'; Base = 'D:\autre\p.db'; DossierLogs = 'D:\LOGS' }).Count | Should -Be 0
        }
    }
    It 'repère la même base atteinte par une racine et un chemin partiel' {
        InModuleScope Copie.Gui {
            $existant = [pscustomobject]@{ Nom = 'preprod'; Parametrage = [pscustomobject]@{ Entete = ('{"version":1,"environnement":"preprod","racine":"D:\\t\\preprod","base":"BDD\\p.db"}' | ConvertFrom-Json) } }
            (Test-CopieSaisieEnvironnement -Saisie @{ Nom = 'copie'; Racine = 'D:\t\preprod\'; Base = 'BDD\p.db' } -Existants @($existant)) -join ' ' | Should -Match 'déjà celle'
            @(Test-CopieSaisieEnvironnement -Saisie @{ Nom = 'copie'; Racine = 'D:\t\copie'; Base = 'BDD\p.db' } -Existants @($existant)).Count | Should -Be 0
        }
    }
    It 'écrit les racines dans l''en-tête (sans les champs vides) et les relit' {
        InModuleScope Copie.Gui {
            $e = ConvertTo-CopieEnteteEnvironnement -Saisie @{ Nom = 'preprod'; Racine = 'D:\t\preprod'; RacineSource = 'SRC'; RacineCible = ''; Base = 'BDD\p.db' }
            ($e | ConvertTo-Json -Compress) | Should -Be '{"version":1,"environnement":"preprod","racine":"D:\\t\\preprod","racine_source":"SRC","base":"BDD\\p.db"}'
            $s = ConvertFrom-CopieEnteteEnvironnement -Entete $e
            $s.Racine | Should -Be 'D:\t\preprod'
            $s.RacineSource | Should -Be 'SRC'
            $s.RacineCible | Should -Be ''
        }
    }
}

Describe 'Dossiers d''un environnement avec une racine (sans moteur)' {
    It 'le contrôle part des chemins complets : base, journaux et travail sous la racine' {
        $cfg = InModuleScope Copie.Gui -Parameters @{ j = (Join-Path $TestDrive 'cfg-r.psd1') } {
            param($j)
            [System.IO.File]::WriteAllText($j, "@{ Acces = @{ GroupesAdmin = @('G') }; Moteur = @{ Mode = 'Local'; Python = 'p'; Racine = 'r' } }")
            Get-CopieConfig -Chemin $j
        }
        $racine = Join-Path $TestDrive 'preprod'
        $d = Join-Path $TestDrive 'param-r'
        $null = New-Item -ItemType Directory -Path $d -Force
        $f = Join-Path $d 'preprod.jsonl'
        $en = [ordered]@{ version = 1; environnement = 'preprod'; racine = ($racine + '\'); base = 'BDD\preprod.db'; dossier_logs = 'LOGS'; dossier_travail = (Join-Path $TestDrive 'ailleurs\TMP') }
        [System.IO.File]::WriteAllText($f, (($en | ConvertTo-Json -Compress) + "`n"), $Script:Utf8)
        InModuleScope Copie.Gui -Parameters @{ c = $cfg; f = $f; racine = $racine; t = $TestDrive } {
            param($c, $f, $racine, $t)
            $r = Invoke-CopieDossiersEnvironnement -Config $c -Fichier $f -Action 'creer'
            $r.Ok | Should -BeTrue -Because $r.Message
            $chemins = @($r.Dossiers | ForEach-Object Chemin)
            $chemins | Should -Contain (Join-Path $racine 'BDD')
            $chemins | Should -Contain (Join-Path $racine 'LOGS')
            $chemins | Should -Contain (Join-Path $t 'ailleurs\TMP')
        }
        Test-Path -LiteralPath (Join-Path $racine 'BDD') -PathType Container | Should -BeTrue
        Test-Path -LiteralPath (Join-Path $racine 'LOGS') -PathType Container | Should -BeTrue
        Test-Path -LiteralPath (Join-Path $TestDrive 'ailleurs\TMP') -PathType Container | Should -BeTrue
    }
}

Describe 'Ligne de la grille : chemins complets, modes et aspect' {
    It 'affiche source → cible pour un transfert et la source seule pour suppression, count et size' {
        InModuleScope Copie.Gui {
            $e = '{"version":1,"racine":"D:\\t","base":"b.db"}' | ConvertFrom-Json
            $copie = '{"id":"r1","mode":"copie","source":"IN","cible":"OUT","planification":{"type":"quotidien","heure":"07:00"}}' | ConvertFrom-Json
            (ConvertTo-CopieLigneRegle -Regle $copie -Etat $null -Entete $e).Chemins | Should -Be ('D:\t\IN  {0}  D:\t\OUT' -f [char]0x2192)
            foreach ($mode in 'suppression', 'count', 'size') {
                $r = ('{"id":"r2","mode":"' + $mode + '","source":"IN","planification":{"type":"quotidien","heure":"07:00"}}') | ConvertFrom-Json
                (ConvertTo-CopieLigneRegle -Regle $r -Etat $null -Entete $e).Chemins | Should -Be 'D:\t\IN' -Because $mode
            }
        }
    }
    It 'donne à la ligne son aspect : inactive (grise), en erreur (rouge), sinon normal ; l''inactive prime' {
        InModuleScope Copie.Gui {
            $actif = '{"id":"r","mode":"copie","source":"S","cible":"C"}' | ConvertFrom-Json
            $inactif = '{"id":"r","mode":"copie","source":"S","cible":"C","actif":false}' | ConvertFrom-Json
            (ConvertTo-CopieLigneRegle -Regle $actif -Etat ('{"statut":"ERREUR"}' | ConvertFrom-Json)).Aspect | Should -Be 'erreur'
            (ConvertTo-CopieLigneRegle -Regle $actif -Etat ('{"statut":"ARRETEE"}' | ConvertFrom-Json)).Aspect | Should -Be 'erreur'
            (ConvertTo-CopieLigneRegle -Regle $actif -Etat ('{"statut":"SUCCES","attente":"BLOQUEE"}' | ConvertFrom-Json)).Aspect | Should -Be 'erreur'
            (ConvertTo-CopieLigneRegle -Regle $actif -Etat ('{"statut":"SUCCES"}' | ConvertFrom-Json)).Aspect | Should -Be ''
            (ConvertTo-CopieLigneRegle -Regle $actif -Etat ('{"statut":"ATTENTE"}' | ConvertFrom-Json)).Aspect | Should -Be ''
            (ConvertTo-CopieLigneRegle -Regle $inactif -Etat $null).Aspect | Should -Be 'inactive'
            (ConvertTo-CopieLigneRegle -Regle $inactif -Etat ('{"statut":"ERREUR"}' | ConvertFrom-Json)).Aspect | Should -Be 'inactive'
        }
    }
    It 'le détail montre le chemin complet et rappelle la saisie quand elle diffère' {
        InModuleScope Copie.Gui {
            $e = '{"version":1,"racine":"D:\\t","base":"b.db"}' | ConvertFrom-Json
            $regle = '{"id":"r","mode":"count","source":"IN","seuil_minimum":5,"planification":{"type":"quotidien","heure":"07:00"}}' | ConvertFrom-Json
            $g = ConvertTo-CopieGroupeRegle -Regle $regle -Entete $e
            $carte = $g | Where-Object Titre -like 'Source*'
            ($carte.Lignes | Where-Object Libelle -eq 'Source').Valeur | Should -Be 'D:\t\IN   (saisi : IN)'
            ($carte.Lignes | Where-Object Libelle -like 'Seuil minimum*').Valeur | Should -Be '5'
            ($carte.Lignes | Where-Object Libelle -eq 'Cible').Valeur | Should -Be ([string][char]0x2014)
        }
    }
    It 'colore le statut ATTENTE' {
        InModuleScope Copie.Gui {
            Get-CopieCouleurStatut 'ATTENTE' | Should -Match '^#[0-9A-F]{6}$'
            Get-CopieCouleurStatut 'ATTENTE' | Should -Not -Be (Get-CopieCouleurStatut 'INCONNU')
        }
    }
}

Describe 'Modes d''une règle' {
    It 'liste les six modes, dont suppression, count et size, sans cible' {
        InModuleScope Copie.Gui {
            $modes = @(Get-CopieModesRegle)
            ($modes | ForEach-Object Nom) -join ',' | Should -Be 'copie,deplacement,archivage,suppression,count,size'
            @($modes | Where-Object { -not $_.Transfert } | ForEach-Object Nom) -join ',' | Should -Be 'suppression,count,size'
        }
    }
    It 'le formulaire ne demande pas de cible pour suppression, count et size' {
        InModuleScope Copie.Gui {
            $champs = (Get-CopieChampsRegle | ForEach-Object Champs) | Where-Object Chemin -eq 'cible'
            $champs.Obligatoire | Should -BeFalse
            ((Get-CopieChampsRegle | ForEach-Object Champs) | Where-Object Chemin -like 'seuil_*').Count | Should -Be 2
        }
    }
    It 'décrit la simulation d''une suppression et d''un comptage' {
        InModuleScope Copie.Gui {
            $sup = '{"source":"D:\\in","cible":null,"mode":"suppression","statut":"SUCCES","motif":"","compteurs":{"livres":3,"octets":3072},"apercu":[]}' | ConvertFrom-Json
            (ConvertTo-CopieResumeSimulation -Json $sup).Phrase | Should -Match 'Supprimera DÉFINITIVEMENT 3 fichier'
            $att = '{"source":"D:\\in","cible":null,"mode":"count","statut":"ATTENTE","motif":"condition non remplie : 4 fichier(s), attendu au moins 5 fichier(s)","compteurs":{},"apercu":[]}' | ConvertFrom-Json
            $r = ConvertTo-CopieResumeSimulation -Json $att
            $r.Phrase | Should -Match 'ATTENTE'
            $r.Niveau | Should -Be 'WARNING'
        }
    }
}
