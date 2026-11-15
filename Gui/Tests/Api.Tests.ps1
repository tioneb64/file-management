#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
# API de règles (module FileManagement.Regles) : seul habilité à modifier le fichier des règles.
# Le VRAI moteur Python est appelé (interpréteur lu dans COPIE_TEST_PYTHON ; absent : tests ignorés).

BeforeDiscovery {
    $Script:PythonDisponible = [bool]$env:COPIE_TEST_PYTHON -and (Test-Path -LiteralPath $env:COPIE_TEST_PYTHON)
}

BeforeAll {
    $Script:Regles = (Resolve-Path (Join-Path $PSScriptRoot '..\FileManagement.Regles')).ProviderPath
    Import-Module (Join-Path $Script:Regles 'FileManagement.Regles.psd1') -Force
    $Script:RacineMoteur = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).ProviderPath
    $Script:Dossier = Join-Path ([System.IO.Path]::GetTempPath()) ('copie_api_' + [guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path (Join-Path $Script:Dossier 'Parametrage')
    $ecrireConfig = {
        param($nom, $groupe)
        $texte = @"
@{
    Acces = @{ GroupesAdmin = @('$groupe') }
    Moteur = @{ Mode = 'Local'; Python = '$($env:COPIE_TEST_PYTHON)'; Racine = '$($Script:RacineMoteur)'; Serveur = ''; ConfigurationJea = ''; DelaiMaxSec = 120 }
    Parametrage = @{ Filtre = '*.jsonl'; VersionsSupportees = @(1); DossierVersions = 'versions'; DossierBrouillons = '.brouillons'; DossierSupprimes = '.supprimes'; PeriodeDeclencheurSec = 300 }
    Journal = @{ Dossier = '$($Script:Dossier)'; Environnement = 'test' }
}
"@
        $chemin = Join-Path $Script:Dossier $nom
        [System.IO.File]::WriteAllText($chemin, $texte, (New-Object System.Text.UTF8Encoding($false)))
        $chemin
    }
    $Script:Config = & $ecrireConfig 'admin.psd1' 'S-1-5-32-545'                  # groupe local « Utilisateurs » : le compte de test en fait partie
    $Script:ConfigLecture = & $ecrireConfig 'lecture.psd1' 'S-1-5-21-1-2-3-99999'   # groupe que le compte n'a pas
    $Script:Fichier = Join-Path $Script:Dossier 'Parametrage\test.jsonl'
    $base = ($Script:Dossier -replace '\\', '/')
    [System.IO.File]::WriteAllText($Script:Fichier, ('{{"version":1,"environnement":"test","racine":"{0}/","base":"{0}/test.db"}}' -f $base) + "`n", (New-Object System.Text.UTF8Encoding($false)))
    $Script:Nouvelle = { @{ id = 'r1'; source = ($Script:Dossier + '\s'); cible = ($Script:Dossier + '\c'); mode = 'copie'
            planification = @{ type = 'intervalle'; frequence_sec = 600; debut = '06:00'; fin = '20:00' } } }
}

AfterAll {
    if ($Script:Dossier -and (Test-Path -LiteralPath $Script:Dossier)) { Remove-Item -LiteralPath $Script:Dossier -Recurse -Force -ErrorAction SilentlyContinue }
}

Describe 'API de règles : un seul écrivain' {
    It 'le noyau d''écriture vit dans FileManagement.Regles, pas dans l''interface' {
        Test-Path (Join-Path $Script:Regles 'Private\Edition.ps1') | Should -BeTrue
        Test-Path (Join-Path $Script:Regles '..\FileManagement.Gui\Private\Edition.ps1') | Should -BeFalse
        (Get-Content -Raw -LiteralPath (Join-Path $Script:Regles 'Private\Edition.ps1')) | Should -Match 'function Save-CopieParametrage'
    }
    It 'exporte seulement les fonctions de l''API' {
        (Get-Module FileManagement.Regles).ExportedFunctions.Keys | Sort-Object | Should -Be @('Add-CopieApiRegle', 'Get-CopieApiInfo', 'Get-CopieApiModele', 'Get-CopieApiRegle', 'Remove-CopieApiRegle', 'Set-CopieApiRegle')
    }
}

Describe 'API de règles' -Skip:(-not $Script:PythonDisponible) {
    It 'donne les versions et le modèle du moteur' {
        $i = Get-CopieApiInfo -Config $Script:Config
        $i.Succes | Should -BeTrue
        $i.VersionFormat | Should -Be 1
        $m = Get-CopieApiModele -Config $Script:Config
        $m.Regle.PSObject.Properties.Name | Should -Contain 'retention_historique_jours'
    }

    It 'ajoute une règle complétée par le modèle, garde la version précédente avec le commentaire et l''appelant' {
        $l = Get-CopieApiRegle -Fichier $Script:Fichier
        $r = Add-CopieApiRegle -Fichier $Script:Fichier -Config $Script:Config -Regle (& $Script:Nouvelle) -Commentaire 'ajout de test' -Appelant 'pester' -Empreinte $l.Empreinte
        $r.Succes | Should -BeTrue -Because $r.Message
        $r.Regle.retention_historique_jours | Should -Be 90
        $lu = Get-CopieApiRegle -Fichier $Script:Fichier -Id 'R1'
        $lu.Regle.source | Should -Be ($Script:Dossier + '\s')
        $lu.Empreinte | Should -Be $r.Empreinte
        $fiche = Get-Content -Raw -LiteralPath ($r.Version -replace '\.jsonl$', '.meta.json') | ConvertFrom-Json
        $fiche.commentaire | Should -Be '[API pester] ajout de test'
        @(Get-ChildItem (Join-Path $Script:Dossier 'Parametrage\.brouillons') -Recurse -File -ErrorAction SilentlyContinue).Count | Should -Be 0
    }

    It 'refuse un doublon, un id absent, un commentaire vide' {
        (Add-CopieApiRegle -Fichier $Script:Fichier -Config $Script:Config -Regle (& $Script:Nouvelle) -Commentaire 'doublon').Etape | Should -Be 'existe'
        (Add-CopieApiRegle -Fichier $Script:Fichier -Config $Script:Config -Regle @{ source = 'a' } -Commentaire 'x').Etape | Should -Be 'invalide'
        (Set-CopieApiRegle -Fichier $Script:Fichier -Config $Script:Config -Id 'r1' -Modification @{ actif = $false } -Commentaire ' ').Etape | Should -Be 'invalide'
    }

    It 'modifie seulement les champs fournis (objets fusionnés) et refuse une empreinte périmée' {
        $avant = Get-CopieApiRegle -Fichier $Script:Fichier
        $r = Set-CopieApiRegle -Fichier $Script:Fichier -Config $Script:Config -Id 'r1' -Modification @{ description = 'changée'; planification = @{ frequence_sec = 900 } } -Commentaire 'modif' -Empreinte $avant.Empreinte
        $r.Succes | Should -BeTrue -Because $r.Message
        $x = (Get-CopieApiRegle -Fichier $Script:Fichier -Id 'r1').Regle
        $x.description | Should -Be 'changée'
        $x.planification.frequence_sec | Should -Be 900
        $x.planification.debut | Should -Be '06:00'
        $x.source | Should -Be ($Script:Dossier + '\s')
        $perime = Set-CopieApiRegle -Fichier $Script:Fichier -Config $Script:Config -Id 'r1' -Modification @{ description = 'autre' } -Commentaire 'modif' -Empreinte $avant.Empreinte
        $perime.Etape | Should -Be 'conflit'
        (Get-CopieApiRegle -Fichier $Script:Fichier -Id 'r1').Regle.description | Should -Be 'changée'
    }

    It 'laisse le moteur refuser un champ inconnu : rien n''est écrit' {
        $avant = (Get-CopieApiRegle -Fichier $Script:Fichier).Empreinte
        $r = Set-CopieApiRegle -Fichier $Script:Fichier -Config $Script:Config -Id 'r1' -Modification '{"champ_inconnu":1}' -Commentaire 'x'
        $r.Succes | Should -BeFalse
        $r.Etape | Should -Be 'refus'
        ($r.Refus | ForEach-Object { $_.code }) | Should -Contain 'E06'
        (Get-CopieApiRegle -Fichier $Script:Fichier).Empreinte | Should -Be $avant
    }

    It 'soumet les avertissements à un accord explicite' {
        $refuse = Set-CopieApiRegle -Fichier $Script:Fichier -Config $Script:Config -Id 'r1' -Modification @{ selection = @{ masque = '*.txt' } } -Commentaire 'masque'
        $refuse.Etape | Should -Be 'avertissements'
        $refuse.Avertissements.Count | Should -BeGreaterThan 0
        $ok = Set-CopieApiRegle -Fichier $Script:Fichier -Config $Script:Config -Id 'r1' -Modification @{ selection = @{ masque = '*.txt' } } -Commentaire 'masque' -AccepterAvertissements
        $ok.Succes | Should -BeTrue -Because $ok.Message
    }

    It 'planification unique : refuse une date à moins de deux périodes du déclencheur (étape delai), sans rien écrire' {
        $avant = (Get-CopieApiRegle -Fichier $Script:Fichier).Empreinte
        $texte = { param($minutes) (Get-Date).AddMinutes($minutes).ToString('yyyy-MM-dd HH:mm', [System.Globalization.CultureInfo]::InvariantCulture) }
        $unique = { param($minutes) $r = & $Script:Nouvelle; $r.id = 'u1'; $r.source = $Script:Dossier + '\su'; $r.cible = $Script:Dossier + '\cu'; $r.planification = @{ type = 'unique'; date_heure = (& $texte $minutes); rattrapage_sec = $null }; $r }
        $proche = Add-CopieApiRegle -Fichier $Script:Fichier -Config $Script:Config -Regle (& $unique 4) -Commentaire 'trop proche' -Appelant 'pester'
        $proche.Succes | Should -BeFalse
        $proche.Etape | Should -Be 'delai'
        $proche.DateMinimale | Should -Match '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$'
        $proche.Message | Should -Match '10 min d''avance'
        (Get-CopieApiRegle -Fichier $Script:Fichier).Empreinte | Should -Be $avant
        $r30 = & $unique 30
        $ok = Add-CopieApiRegle -Fichier $Script:Fichier -Config $Script:Config -Regle $r30 -Commentaire 'assez loin' -Appelant 'pester'
        $ok.Succes | Should -BeTrue -Because $ok.Message
        $modif = Set-CopieApiRegle -Fichier $Script:Fichier -Config $Script:Config -Id 'u1' -Modification @{ planification = @{ date_heure = (& $texte 5) } } -Commentaire 'rapprochée'
        $modif.Etape | Should -Be 'delai'
        (Get-CopieApiRegle -Fichier $Script:Fichier -Id 'u1').Regle.planification.date_heure | Should -Be $r30.planification.date_heure
        # une date non modifiée n'est pas contrôlée (règle déjà jouée, ou proche de sa date) : le reste de la règle reste modifiable
        $reste = Set-CopieApiRegle -Fichier $Script:Fichier -Config $Script:Config -Id 'u1' -Modification @{ description = 'autre champ' } -Commentaire 'sans toucher la date'
        $reste.Succes | Should -BeTrue -Because $reste.Message
        $loin = Set-CopieApiRegle -Fichier $Script:Fichier -Config $Script:Config -Id 'u1' -Modification @{ planification = @{ date_heure = (& $texte 60) } } -Commentaire 'reportée' -AccepterAvertissements
        $loin.Succes | Should -BeTrue -Because $loin.Message
        (Remove-CopieApiRegle -Fichier $Script:Fichier -Config $Script:Config -Id 'u1' -Commentaire 'nettoyage' -AccepterAvertissements).Succes | Should -BeTrue
    }

    It 'refuse un compte hors Acces.GroupesAdmin, sans rien écrire' {
        $avant = (Get-CopieApiRegle -Fichier $Script:Fichier).Empreinte
        $r = Add-CopieApiRegle -Fichier $Script:Fichier -Config $Script:ConfigLecture -Regle @{ id = 'r9'; source = 'a'; cible = 'b'; mode = 'copie' } -Commentaire 'x'
        $r.Etape | Should -Be 'droits'
        (Get-CopieApiRegle -Fichier $Script:Fichier).Empreinte | Should -Be $avant
    }

    It 'trace chaque action dans le journal de l''API' {
        $fichierJournal = Join-Path $Script:Dossier ('ApiRegles_{0}.jsonl' -f (Get-Date -Format 'yyyy-MM-dd'))
        Test-Path $fichierJournal | Should -BeTrue
        $lignes = @(Get-Content -LiteralPath $fichierJournal | ForEach-Object { $_ | ConvertFrom-Json })
        @($lignes | Where-Object { $_.action -eq 'ajout' -and $_.appelant -eq 'pester' -and $_.succes }).Count | Should -BeGreaterThan 0
    }

    It 'passe par la ligne de commande avec des codes retour stables (0 fait, 1 refusé)' {
        $demande = Join-Path $Script:Dossier 'demande.json'
        $sortie = Join-Path $Script:Dossier 'sortie.json'
        $script = Join-Path $Script:Regles 'Invoke-RegleApi.ps1'
        $ecrire = { param($texte) [System.IO.File]::WriteAllText($demande, $texte, (New-Object System.Text.UTF8Encoding($false))) }
        $lancer = {
            param($action, $id)
            $liste = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $script, '-Action', $action, '-Fichier', $Script:Fichier, '-Config', $Script:Config, '-EntreeJson', $demande, '-SortieJson', $sortie)
            if ($id) { $liste += @('-Id', $id) }
            & powershell.exe @liste | Out-Null
            $LASTEXITCODE
        }
        & $ecrire '{"modification":{"description":"par la ligne de commande"},"commentaire":"cli","appelant":"pester-cli"}'
        (& $lancer 'modifier' 'r1') | Should -Be 0
        $j = Get-Content -Raw -LiteralPath $sortie | ConvertFrom-Json
        $j.succes | Should -BeTrue
        $j.regle.description | Should -Be 'par la ligne de commande'
        & $ecrire '{"modification":{"champ_inconnu":1},"commentaire":"cli"}'
        (& $lancer 'modifier' 'r1') | Should -Be 1
        (Get-Content -Raw -LiteralPath $sortie | ConvertFrom-Json).etape | Should -Be 'refus'
        (& $lancer 'modifier' $null) | Should -Be 2
    }

    It 'supprime une règle ; une règle absente est « introuvable »' {
        (Remove-CopieApiRegle -Fichier $Script:Fichier -Config $Script:Config -Id 'zz' -Commentaire 'x').Etape | Should -Be 'introuvable'
        $r = Remove-CopieApiRegle -Fichier $Script:Fichier -Config $Script:Config -Id 'r1' -Commentaire 'fin' -AccepterAvertissements
        $r.Succes | Should -BeTrue -Because $r.Message
        @((Get-CopieApiRegle -Fichier $Script:Fichier).Regles).Count | Should -Be 0
    }

    It 'le client Python rend les mêmes résultats (lecture, ajout, conflit)' {
        $client = Join-Path $Script:Regles 'Clients'
        $script = @"
import sys, json
sys.path.insert(0, r'$client')
from copie_regles_client import ClientRegles
api = ClientRegles(appelant='py', config=r'$($Script:Config)')
f = r'$($Script:Fichier)'
l = api.lire(f)
r = api.ajouter(f, {'id': 'rpy', 'source': r'$($Script:Dossier)\s', 'cible': r'$($Script:Dossier)\c', 'mode': 'copie', 'planification': {'type': 'intervalle', 'frequence_sec': 600, 'debut': '06:00', 'fin': '20:00'}}, 'ajout python', empreinte=l['empreinte'])
perime = api.modifier(f, 'rpy', {'actif': False}, 'x', empreinte=l['empreinte'])
print(json.dumps([r['succes'], perime['etape']]))
"@
        $fichierPy = Join-Path $Script:Dossier 'client.py'
        [System.IO.File]::WriteAllText($fichierPy, $script, (New-Object System.Text.UTF8Encoding($false)))
        $sortie = & $env:COPIE_TEST_PYTHON -I $fichierPy
        ($sortie | Select-Object -Last 1) | Should -Be '[true, "conflit"]'
        (Get-CopieApiRegle -Fichier $Script:Fichier -Id 'rpy').Succes | Should -BeTrue
    }
}
