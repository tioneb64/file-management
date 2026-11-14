#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }
# Journaux d'une règle : décomposition du JSON du moteur (--journaux-regle) en lignes lisibles, et fenêtre des journaux.
# La logique est testée sans fenêtre ; la fenêtre simule le moteur (Mock) et exige un thread STA.

BeforeDiscovery {
    $Script:Sta = ([System.Threading.Thread]::CurrentThread.GetApartmentState() -eq 'STA')
}

BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..\FileManagement.Gui\FileManagement.Gui.psd1') -Force
    $Script:Liste = @'
{ "ok": true, "regle": "export", "dossier": "D:\\logs", "tronque": false, "total_fichiers": 3,
  "journaux": [
    { "nom": "export_2026-11-12.jsonl", "jour": "2026-11-12", "evenements": 9, "illisibles": 0, "executions": 2, "avertissements": 0, "erreurs": 0, "statut": "SUCCES", "motif": "2 fichier(s) livre(s)", "dernier": "2026-11-12 10:00:03" },
    { "nom": "export_2026-11-11.jsonl", "jour": "2026-11-11", "evenements": 5, "illisibles": 1, "executions": 1, "avertissements": 1, "erreurs": 1, "statut": "ERREUR", "motif": "1 erreur", "dernier": "2026-11-11 08:00:03" },
    { "nom": "export_2026-11-10.jsonl", "jour": "2026-11-10", "evenements": 3, "illisibles": 0, "executions": 1, "avertissements": 2, "erreurs": 0, "statut": null, "motif": null, "dernier": "2026-11-10 08:00:05" }
  ] }
'@
    $Script:Fichier = @'
{ "ok": true, "regle": "export", "journal": "export_2026-11-11.jsonl", "total": 6, "tronque": false, "illisibles": 1,
  "executions": [
    { "cle": "1", "execution_id": 1, "heure": "2026-11-11 07:00:00", "declencheur": "planifie", "simulation": false, "statut": "SUCCES", "motif": "1 fichier(s) livre(s)", "duree_ms": 900, "avertissements": 0, "erreurs": 0 },
    { "cle": "s1", "execution_id": null, "heure": "2026-11-11 08:00:00", "declencheur": "manuel", "simulation": true, "statut": "ERREUR", "motif": "1 erreur", "duree_ms": 3000, "avertissements": 1, "erreurs": 1 }
  ],
  "evenements": [
    { "numero": 1, "heure": "2026-11-11 07:00:00", "niveau": "INFO", "evenement": "regle_demarree", "message": "Regle demarree (planifie)", "execution_id": 1, "groupe": "1", "duree_ms": null, "erreur": null, "champs": [ { "cle": "declencheur", "valeur": "planifie" } ] },
    { "numero": 2, "heure": "2026-11-11 07:00:01", "niveau": "INFO", "evenement": "fichier_livre", "message": "Fichier livre : a.csv", "execution_id": 1, "groupe": "1", "duree_ms": 12, "erreur": null, "champs": [ { "cle": "fichier", "valeur": "D:\\src\\a.csv" }, { "cle": "cible", "valeur": "D:\\dst\\a.csv" }, { "cle": "taille", "valeur": 2048 }, { "cle": "simulation", "valeur": false } ] },
    { "numero": 3, "heure": "2026-11-11 08:00:00", "niveau": "INFO", "evenement": "regle_demarree", "message": "Regle demarree (manuel)", "execution_id": null, "groupe": "s1", "duree_ms": null, "erreur": null, "champs": [ { "cle": "declencheur", "valeur": "manuel" }, { "cle": "simulation", "valeur": true } ] },
    { "numero": 4, "heure": "2026-11-11 08:00:01", "niveau": "WARNING", "evenement": "tentative_echouee", "message": "Fichier verrouille", "execution_id": null, "groupe": "s1", "duree_ms": null, "erreur": null, "champs": [ { "cle": "situation", "valeur": "fichier_verrouille" }, { "cle": "hors_masque", "valeur": 3 }, { "cle": "champ_inconnu_x", "valeur": null } ] },
    { "numero": 5, "heure": "2026-11-11 08:00:02", "niveau": "ERROR", "evenement": "fichier_erreur", "message": "Erreur sur le fichier a.csv", "execution_id": null, "groupe": "s1", "duree_ms": null, "erreur": { "type": "FILE_IO_ERROR", "exception": "PermissionError", "pile": "ligne 1" }, "champs": [ { "cle": "fichier", "valeur": "a.csv" } ] },
    { "numero": 6, "heure": "2026-11-11 08:00:03", "niveau": "INFO", "evenement": "regle_terminee", "message": "Regle terminee : ERREUR", "execution_id": null, "groupe": "s1", "duree_ms": 3000, "erreur": null, "champs": [ { "cle": "statut", "valeur": "ERREUR" }, { "cle": "compteurs", "valeur": "{\"selectionnes\":1,\"livres\":0,\"octets\":4096}" } ] }
  ] }
'@
}

Describe 'Liste des journaux d''une règle' {
    It 'présente un journal par jour, avec le dernier statut et les anomalies, la gravité colorant la ligne' {
        $l = @(InModuleScope FileManagement.Gui -Parameters @{ j = $Script:Liste } { param($j) ConvertTo-CopieLignesJournaux -Json ($j | ConvertFrom-Json) })
        $l.Count | Should -Be 3
        $l[0].Nom | Should -Be 'export_2026-11-12.jsonl'
        $l[0].Jour | Should -Match '12/11/2026'
        $l[0].Statut | Should -Be 'SUCCES'
        $l[0].Anomalies | Should -Be 'aucune'
        $l[0].Gravite | Should -Be 'Normal'
        $l[1].Anomalies | Should -Be '1 erreur(s), 1 avertissement(s)'
        $l[1].Gravite | Should -Be 'Erreur'
        $l[2].Statut | Should -Be ([string][char]0x2014)
        $l[2].Gravite | Should -Be 'Avertissement'
    }
}

Describe 'Événements d''un journal' {
    BeforeAll {
        $Script:Lignes = @(InModuleScope FileManagement.Gui -Parameters @{ j = $Script:Fichier } { param($j) ConvertTo-CopieLignesEvenements -Json ($j | ConvertFrom-Json) })
    }
    It 'repère les anomalies et nomme les simulations' {
        $Script:Lignes[0].Niveau | Should -Be 'Information'
        $Script:Lignes[0].Execution | Should -Be 'n° 1'
        $Script:Lignes[1].Detail | Should -Match 'Fichier : D:\\src\\a.csv'
        $Script:Lignes[1].Detail | Should -Match 'Taille : 2[,.]0 Ko'
        $Script:Lignes[1].Detail | Should -Not -Match 'Simulation'
        $Script:Lignes[2].Execution | Should -Be 'Simulation 1'
        $Script:Lignes[3].Niveau | Should -Be 'Avertissement'
        $Script:Lignes[3].Gravite | Should -Be 'Avertissement'
        $Script:Lignes[4].Niveau | Should -Be 'Erreur'
        $Script:Lignes[4].Gravite | Should -Be 'Erreur'
    }
    It 'filtre par exécution et par gravité' {
        $s1 = @(InModuleScope FileManagement.Gui -Parameters @{ l = $Script:Lignes } { param($l) Select-CopieEvenementsJournal -Ligne $l -Groupe 's1' })
        $s1.Count | Should -Be 4
        $anomalies = @(InModuleScope FileManagement.Gui -Parameters @{ l = $Script:Lignes } { param($l) Select-CopieEvenementsJournal -Ligne $l -AnomaliesSeulement })
        ($anomalies | ForEach-Object Numero) -join ',' | Should -Be '4,5'
        $tout = @(InModuleScope FileManagement.Gui -Parameters @{ l = $Script:Lignes } { param($l) Select-CopieEvenementsJournal -Ligne $l })
        $tout.Count | Should -Be 6
        $aucun = @(InModuleScope FileManagement.Gui -Parameters @{ l = $Script:Lignes } { param($l) Select-CopieEvenementsJournal -Ligne $l -Groupe '99' })
        $aucun.Count | Should -Be 0
    }
    It 'propose les exécutions de la plus récente à la plus ancienne, avec « toutes » en tête' {
        $c = @(InModuleScope FileManagement.Gui -Parameters @{ j = $Script:Fichier } { param($j) ConvertTo-CopieChoixExecutions -Json ($j | ConvertFrom-Json) })
        $c.Count | Should -Be 3
        $c[0].Cle | Should -BeNullOrEmpty
        $c[0].Libelle | Should -Be 'Toutes les exécutions (2)'
        $c[1].Cle | Should -Be 's1'
        $c[1].Libelle | Should -Match 'Simulation 1 · 08:00:00 · manuel · ERREUR : 1 erreur'
        $c[2].Cle | Should -Be '1'
        $c[2].Libelle | Should -Match 'n° 1 · 07:00:00 · planifie · SUCCES'
    }
    It 'décompose le détail : valeurs lisibles, compteurs développés, erreur nommée' {
        $d = @(InModuleScope FileManagement.Gui -Parameters @{ l = $Script:Lignes } { param($l) Get-CopieDetailEvenement -Evenement $l[5].Brut })
        ($d | Where-Object Rubrique -eq 'Niveau').Valeur | Should -Be 'Information'
        ($d | Where-Object Rubrique -eq 'Durée').Valeur | Should -Match '^3[,.]0 s$'
        ($d | Where-Object Rubrique -eq 'Exécution').Valeur | Should -Be 'Simulation 1'
        ($d | Where-Object Rubrique -eq 'Compteurs : Sélectionnés').Valeur | Should -Be '1'
        ($d | Where-Object Rubrique -eq 'Compteurs : Volume').Valeur | Should -Match '^4[,.]0 Ko$'
        $e = @(InModuleScope FileManagement.Gui -Parameters @{ l = $Script:Lignes } { param($l) Get-CopieDetailEvenement -Evenement $l[4].Brut })
        ($e | Where-Object Rubrique -eq 'Type d''erreur').Valeur | Should -Be 'FILE_IO_ERROR'
        ($e | Where-Object Rubrique -eq 'Exception').Valeur | Should -Be 'PermissionError'
        $w = @(InModuleScope FileManagement.Gui -Parameters @{ l = $Script:Lignes } { param($l) Get-CopieDetailEvenement -Evenement $l[3].Brut })
        ($w | Where-Object Rubrique -eq 'Hors masque').Valeur | Should -Be '3'
        ($w | Where-Object Rubrique -eq 'Champ inconnu x').Valeur | Should -Be ([string][char]0x2014)
        $f = @(InModuleScope FileManagement.Gui -Parameters @{ l = $Script:Lignes } { param($l) Get-CopieDetailEvenement -Evenement $l[1].Brut })
        ($f | Where-Object Rubrique -eq 'Simulation').Valeur | Should -Be 'Non'
        ($f | Where-Object Rubrique -eq 'Taille').Valeur | Should -Match '^2[,.]0 Ko$'
    }
    It 'résume le fichier : événements, exécutions, anomalies, lignes illisibles' {
        $t = InModuleScope FileManagement.Gui -Parameters @{ j = $Script:Fichier; l = $Script:Lignes } { param($j, $l) Get-CopieResumeJournal -Json ($j | ConvertFrom-Json) -Ligne $l }
        $t | Should -Match '6 événement\(s\), 2 exécution\(s\) ; 1 erreur\(s\), 1 avertissement\(s\)\.'
        $t | Should -Match '1 ligne\(s\) illisible\(s\) ignorée\(s\)\.'
        $t | Should -Not -Match 'derniers'
    }
}

Describe 'Fenêtre des journaux' -Skip:(-not $Script:Sta) {
    It 'ouvre le journal le plus récent sur sa dernière exécution, puis filtre et détaille' {
        Mock Invoke-CopieMoteur -ModuleName FileManagement.Gui {
            [pscustomobject]@{ Code = 0; Json = ($Script:Fichier | ConvertFrom-Json); Erreur = '' }
        }
        $res = InModuleScope FileManagement.Gui -Parameters @{ liste = $Script:Liste } {
            param($liste)
            $vue = @{ Contexte = @{ Config = [pscustomobject]@{}; Fenetre = $null }; Env = [pscustomobject]@{ Fichier = 'x.jsonl'; Nom = 'prod' } }
            $json = $liste | ConvertFrom-Json
            $f = Show-CopieFenetreJournaux -Vue $vue -Regle 'export' -Ligne @(ConvertTo-CopieLignesJournaux -Json $json) -Json $json -SansAffichage
            $execs = $f.FindName('Executions')
            $premier = @{ Choix = @($execs.ItemsSource).Count; Index = $execs.SelectedIndex; Evenements = @($f.FindName('Evenements').ItemsSource).Count
                Titre = $f.Title; Selection = $f.FindName('Evenements').SelectedItem.Numero; Detail = @($f.FindName('Detail').ItemsSource).Count
                Copier = $f.FindName('BtnCopier').IsEnabled; Resume = $f.FindName('ResumeJournal').Text }
            $execs.SelectedIndex = 0
            $tout = @($f.FindName('Evenements').ItemsSource).Count
            $f.FindName('Anomalies').IsChecked = $true
            Update-CopieJournauxAffichage -Fenetre $f
            $anomalies = @($f.FindName('Evenements').ItemsSource).Count
            @{ Premier = $premier; Tout = $tout; Anomalies = $anomalies }
        }
        $res.Premier.Choix | Should -Be 3
        $res.Premier.Index | Should -Be 1
        $res.Premier.Evenements | Should -Be 4
        $res.Premier.Selection | Should -Be 4 -Because 'on se place sur la première anomalie'
        $res.Premier.Detail | Should -BeGreaterThan 5
        $res.Premier.Copier | Should -BeTrue
        $res.Premier.Titre | Should -Match 'export'
        $res.Tout | Should -Be 6
        $res.Anomalies | Should -Be 2
    }
}
