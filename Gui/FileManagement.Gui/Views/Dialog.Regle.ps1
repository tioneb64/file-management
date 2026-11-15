# Formulaire d'une règle (étape B). Les contrôles sont construits à partir du modèle du moteur : listes de
# valeurs permises, valeurs de secours, situations. L'état du formulaire est rangé dans Window.Tag, car les
# gestionnaires d'événements WPF ne voient pas les variables locales de la fonction qui les a créés.

function New-CopieControleChamp {
    <#
    .SYNOPSIS
        Crée le contrôle d'un champ simple du formulaire et le range dans le panneau.
    .PARAMETER Spec
        Champ (Get-CopieChampsRegle).
    .PARAMETER Regle
        Règle complète servant de valeur initiale.
    .PARAMETER Modele
        Modèle du moteur (regle, listes).
    .PARAMETER Panneau
        StackPanel qui reçoit la ligne.
    .PARAMETER LectureSeule
        Champ non modifiable (identifiant d'une règle existante).
    .OUTPUTS
        [hashtable] Spec, Controle, Unite, Vide (valeur à écrire quand la saisie est vide), Nullable.
    #>
    [CmdletBinding()]
    param($Spec, $Regle, $Modele, [System.Windows.Controls.Panel] $Panneau, [bool] $LectureSeule = $false)

    $valeur = Get-CopieValeurChemin $Regle $Spec.Chemin
    $defaut = Get-CopieValeurChemin $Modele.regle $Spec.Chemin
    $nullable = ($null -eq $defaut) -and (-not $Spec.Obligatoire)
    $entree = @{ Spec = $Spec; Controle = $null; Unite = $null; Vide = $(if ($null -eq $defaut) { $null } else { '' }); Nullable = $nullable }
    $controle = $null
    switch ($Spec.Type) {
        'bool' { $controle = New-Object System.Windows.Controls.CheckBox; $controle.IsChecked = [bool]$valeur; $controle.VerticalAlignment = 'Center' }
        'choix' {
            $controle = New-Object System.Windows.Controls.ComboBox
            $items = New-Object System.Collections.Generic.List[string]
            if ($nullable) { $items.Add('') }
            foreach ($i in @($Modele.listes.($Spec.Liste))) { $items.Add("$i") }
            if ($null -ne $valeur -and -not $items.Contains("$valeur")) { $items.Add("$valeur") }     # valeur inconnue : conservée, le moteur la jugera
            foreach ($i in $items) { $null = $controle.Items.Add($i) }
            $controle.SelectedItem = $(if ($null -eq $valeur) { '' } else { "$valeur" })
            if ($null -eq $controle.SelectedItem -and $controle.Items.Count -gt 0) { $controle.SelectedIndex = 0 }
            $controle.Width = 260; $controle.HorizontalAlignment = 'Left'
        }
        'cases' {
            $controle = New-Object System.Windows.Controls.StackPanel; $controle.Orientation = 'Horizontal'
            $choisis = @($valeur | Where-Object { $null -ne $_ } | ForEach-Object { "$_" })
            $offerts = @($Modele.listes.($Spec.Liste) | ForEach-Object { "$_" }) + @($choisis | Where-Object { @($Modele.listes.($Spec.Liste)) -notcontains $_ })
            $entree.Cases = @{}
            foreach ($o in $offerts) {
                $cb = New-Object System.Windows.Controls.CheckBox; $cb.Content = $o; $cb.Margin = '0,0,14,0'; $cb.IsChecked = ($choisis -contains $o)
                $entree.Cases[$o] = $cb; $null = $controle.Children.Add($cb)
            }
            $entree.Ordre = $offerts
        }
        'duree' {
            $controle = New-Object System.Windows.Controls.StackPanel; $controle.Orientation = 'Horizontal'
            $affichage = ConvertTo-CopieDureeAffichage -Secondes $valeur
            $saisie = New-Object System.Windows.Controls.TextBox; $saisie.Width = 110; $saisie.Text = $affichage.Valeur
            $unite = New-Object System.Windows.Controls.ComboBox; $unite.Width = 110; $unite.Margin = '8,0,0,0'
            foreach ($u in $Script:UnitesDuree) { $null = $unite.Items.Add($u.Nom) }
            $unite.SelectedItem = $affichage.Unite
            $null = $controle.Children.Add($saisie); $null = $controle.Children.Add($unite)
            $entree.Saisie = $saisie; $entree.Unite = $unite
        }
        'lignes' {
            $controle = New-Object System.Windows.Controls.TextBox
            $controle.AcceptsReturn = $true; $controle.Height = 80; $controle.VerticalScrollBarVisibility = 'Auto'
            $controle.Text = (@($valeur) | Where-Object { $null -ne $_ }) -join "`r`n"
        }
        default {
            $controle = New-Object System.Windows.Controls.TextBox
            $controle.Text = $(if ($null -eq $valeur) { '' } else { "$valeur" })
            if ($Spec.Type -eq 'entier') { $controle.Width = 140; $controle.HorizontalAlignment = 'Left' }
        }
    }
    if ($LectureSeule -and $Spec.Chemin -eq 'id') { $controle.IsReadOnly = $true; $controle.Background = [System.Windows.Media.Brushes]::WhiteSmoke }
    $entree.Controle = $controle
    Add-CopieLigneFormulaire -Panneau $Panneau -Libelle $Spec.Libelle -Obligatoire $Spec.Obligatoire -Controle $controle -Aide $Spec.Aide
    $entree
}

function Add-CopieLigneFormulaire {
    <#
    .SYNOPSIS
        Ajoute une ligne « libellé / contrôle / aide » au panneau d'un onglet.
    .PARAMETER Panneau
        StackPanel de l'onglet.
    .PARAMETER Libelle
        Libellé.
    .PARAMETER Obligatoire
        Ajoute un astérisque.
    .PARAMETER Controle
        Contrôle de saisie.
    .PARAMETER Aide
        Texte d'aide sous le contrôle.
    #>
    [CmdletBinding()]
    param([System.Windows.Controls.Panel] $Panneau, [string] $Libelle, [bool] $Obligatoire, $Controle, [string] $Aide = '')
    $grille = New-Object System.Windows.Controls.Grid
    $grille.Margin = '0,0,0,8'
    $c1 = New-Object System.Windows.Controls.ColumnDefinition; $c1.Width = New-Object System.Windows.GridLength(250)
    $c2 = New-Object System.Windows.Controls.ColumnDefinition; $c2.Width = New-Object System.Windows.GridLength(1, 'Star')
    $null = $grille.ColumnDefinitions.Add($c1); $null = $grille.ColumnDefinitions.Add($c2)
    $null = $grille.RowDefinitions.Add((New-Object System.Windows.Controls.RowDefinition))
    $null = $grille.RowDefinitions.Add((New-Object System.Windows.Controls.RowDefinition))
    $texte = New-Object System.Windows.Controls.TextBlock
    $texte.Text = $(if ($Obligatoire) { $Libelle + ' *' } else { $Libelle })
    $texte.TextWrapping = 'Wrap'; $texte.Margin = '0,4,12,0'; $texte.VerticalAlignment = 'Top'
    $texte.Foreground = [System.Windows.Media.Brushes]::DimGray; $texte.FontWeight = 'SemiBold'
    [System.Windows.Controls.Grid]::SetColumn($Controle, 1)
    $null = $grille.Children.Add($texte); $null = $grille.Children.Add($Controle)
    if ($Aide) {
        $a = New-Object System.Windows.Controls.TextBlock
        $a.Text = $Aide; $a.TextWrapping = 'Wrap'; $a.Foreground = [System.Windows.Media.Brushes]::Gray; $a.FontSize = 11.5; $a.Margin = '0,2,0,0'
        [System.Windows.Controls.Grid]::SetColumn($a, 1); [System.Windows.Controls.Grid]::SetRow($a, 1)
        $null = $grille.Children.Add($a)
    }
    $null = $Panneau.Children.Add($grille)
}

function Read-CopieControleChamp {
    <#
    .SYNOPSIS
        Lit et convertit la saisie d'un champ simple.
    .PARAMETER Entree
        Entrée créée par New-CopieControleChamp.
    .OUTPUTS
        [pscustomobject] Ok, Valeur, Erreur.
    #>
    [CmdletBinding()]
    param([hashtable] $Entree)
    $spec = $Entree.Spec
    $ok = { param($v) [pscustomobject]@{ Ok = $true; Valeur = $v; Erreur = $null } }
    $ko = { param($m) [pscustomobject]@{ Ok = $false; Valeur = $null; Erreur = ('{0} : {1}' -f $spec.Libelle, $m) } }
    $c = $Entree.Controle
    switch ($spec.Type) {
        'bool' { return (& $ok ([bool]$c.IsChecked)) }
        'choix' {
            $t = "$($c.SelectedItem)"
            if ($t -eq '') { if ($Entree.Nullable) { return (& $ok $null) } else { return (& $ko 'une valeur est à choisir') } }
            return (& $ok $t)
        }
        'cases' {
            $coches = @($Entree.Ordre | Where-Object { $Entree.Cases[$_].IsChecked })
            if ($coches.Count -eq 0) { return (& $ko 'au moins un choix est attendu') }
            return (& $ok $coches)
        }
        'lignes' {
            return (& $ok @($c.Text -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }))
        }
        'duree' {
            $t = $Entree.Saisie.Text.Trim()
            if ($t -eq '') { if ($Entree.Nullable) { return (& $ok $null) } else { return (& $ko 'une durée est attendue') } }
            $r = ConvertFrom-CopieDureeAffichage -Valeur $t -Unite "$($Entree.Unite.SelectedItem)"
            if (-not $r.Ok) { return (& $ko $r.Erreur) }
            return (& $ok $r.Secondes)
        }
        'entier' {
            $t = $c.Text.Trim()
            if ($t -eq '') { if ($Entree.Nullable) { return (& $ok $null) } else { return (& $ko 'un nombre entier est attendu') } }
            $n = 0L
            if (-not [long]::TryParse($t, [System.Globalization.NumberStyles]::None, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$n)) { return (& $ko 'un nombre entier positif est attendu') }
            return (& $ok $n)
        }
        default {
            $t = $c.Text.Trim()
            if ($t -eq '') { if ($spec.Obligatoire -and $c.IsEnabled) { return (& $ko 'obligatoire') } else { return (& $ok $Entree.Vide) } }
            return (& $ok $t)
        }
    }
}

function New-CopieOngletPlanification {
    <#
    .SYNOPSIS
        Construit l'onglet Planification (champs différents selon le type) et renvoie ses contrôles.
    .PARAMETER Modele
        Modèle du moteur.
    .PARAMETER Regle
        Règle complète.
    .PARAMETER Panneau
        Panneau de l'onglet.
    #>
    [CmdletBinding()]
    param($Modele, $Regle, [System.Windows.Controls.Panel] $Panneau)
    $p = Get-CopieValeur $Regle 'planification'
    $etat = [ordered]@{}
    $type = New-Object System.Windows.Controls.ComboBox; $type.Width = 260; $type.HorizontalAlignment = 'Left'
    foreach ($t in @($Modele.listes.types_planification)) { $null = $type.Items.Add("$t") }
    $initial = "$(Get-CopieValeur $p 'type' '')"
    $type.SelectedItem = $(if ($initial) { $initial } else { 'quotidien' })
    if ($null -eq $type.SelectedItem) { $type.SelectedIndex = 0 }
    Add-CopieLigneFormulaire -Panneau $Panneau -Libelle 'Type de planification' -Obligatoire $true -Controle $type `
        -Aide 'quotidien : une fois par jour à une heure fixe. intervalle : toutes les N secondes dans une plage horaire. apres_dependances : se lance après les règles dont elle dépend. unique (OneShot) : une seule fois, à une date et une heure précises, puis la règle est terminée.'
    $etat.Type = $type

    $champ = {
        param($nom, $libelle, $kind, $aide)
        $spec = [pscustomobject]@{ Chemin = "planification.$nom"; Libelle = $libelle; Type = $kind; Liste = $null; Obligatoire = ($kind -ne 'duree' -or $nom -ne 'rattrapage_sec'); Aide = $aide }
        $boite = New-Object System.Windows.Controls.StackPanel
        $r = [pscustomobject]@{ planification = $p }
        $e = New-CopieControleChamp -Spec $spec -Regle $r -Modele ([pscustomobject]@{ regle = [pscustomobject]@{ planification = [pscustomobject]@{ $nom = $(if ($spec.Obligatoire) { '' } else { $null }) } }; listes = $Modele.listes }) -Panneau $boite
        $e.Boite = $boite
        $null = $Panneau.Children.Add($boite)
        $e
    }
    $etat.Heure = & $champ 'heure' 'Heure de lancement' 'texte' 'Format HH:MM, exemple 07:00.'
    $etat.DateHeure = & $champ 'date_heure' 'Date et heure de lancement' 'texte' 'Format AAAA-MM-JJ HH:MM, heure locale du serveur (exemple : 2026-12-01 07:15). La règle part une seule fois à cette date, puis elle est terminée ; changer la date la réarme.'
    $etat.Frequence = & $champ 'frequence_sec' 'Fréquence' 'duree' 'Délai entre deux lancements dans la plage horaire. Moins de 5 minutes provoque un avertissement du moteur.'
    $etat.Debut = & $champ 'debut' 'Début de plage' 'texte' 'Format HH:MM.'
    $etat.Fin = & $champ 'fin' 'Fin de plage' 'texte' 'Format HH:MM, postérieur au début.'

    $coches = ConvertFrom-CopieJours -Texte "$(Get-CopieValeur $p 'jours' 'tous')"
    $bj = New-Object System.Windows.Controls.StackPanel; $bj.Orientation = 'Horizontal'
    $etat.Jours = @{}
    foreach ($j in $Script:JoursSemaine) {
        $cb = New-Object System.Windows.Controls.CheckBox; $cb.Content = $j; $cb.Margin = '0,0,12,0'
        $cb.IsChecked = ($null -eq $coches) -or ($coches -contains $j)
        $etat.Jours[$j] = $cb; $null = $bj.Children.Add($cb)
    }
    $boiteJours = New-Object System.Windows.Controls.StackPanel
    Add-CopieLigneFormulaire -Panneau $boiteJours -Libelle 'Jours' -Obligatoire $true -Controle $bj -Aide 'Au moins un jour.'
    $null = $Panneau.Children.Add($boiteJours)
    $etat.BoiteJours = $boiteJours
    $etat.Rattrapage = & $champ 'rattrapage_sec' 'Rattrapage d''un créneau manqué' 'duree' 'Vide : pas de rattrapage. Sinon, un créneau manqué est rattrapé s''il a moins de cette durée.'

    $type.Add_SelectionChanged({ param($s) Update-CopiePlanificationVisible -Fenetre ([System.Windows.Window]::GetWindow($s)) })
    $etat
}

function Update-CopiePlanificationVisible {
    <#
    .SYNOPSIS
        Montre les champs de planification qui correspondent au type choisi.
    .PARAMETER Fenetre
        Fenêtre du formulaire (son Tag porte l'état).
    #>
    [CmdletBinding()]
    param([System.Windows.Window] $Fenetre)
    $pl = $Fenetre.Tag.Planif
    if ($null -eq $pl) { return }
    $type = "$($pl.Type.SelectedItem)"
    $v = { param($visible) if ($visible) { 'Visible' } else { 'Collapsed' } }
    $pl.Heure.Boite.Visibility = & $v ($type -eq 'quotidien')
    $pl.DateHeure.Boite.Visibility = & $v ($type -eq 'unique')
    foreach ($n in 'Frequence', 'Debut', 'Fin') { $pl[$n].Boite.Visibility = & $v ($type -eq 'intervalle') }
    $pl.BoiteJours.Visibility = & $v ($type -in 'quotidien', 'intervalle')
    $pl.Rattrapage.Boite.Visibility = & $v ($type -in 'quotidien', 'intervalle', 'unique')
}

function Update-CopieHorodatageDisponible {
    <#
    .SYNOPSIS
        Ne propose la case « Horodater les fichiers traités » que pour les modes copie et archivage.
    .PARAMETER Fenetre
        Fenêtre du formulaire (son Tag porte les champs). Pour un autre mode, la case est grisée et décochée.
    #>
    [CmdletBinding()]
    param([System.Windows.Window] $Fenetre)
    $champs = @($Fenetre.Tag.Champs)
    $mode = $champs | Where-Object { $_.Spec.Chemin -eq 'mode' } | Select-Object -First 1
    $horodatage = $champs | Where-Object { $_.Spec.Chemin -eq 'horodater' } | Select-Object -First 1
    if ($null -eq $mode -or $null -eq $horodatage) { return }
    $permis = "$($mode.Controle.SelectedItem)" -in 'copie', 'archivage'
    $horodatage.Controle.IsEnabled = $permis
    if (-not $permis) { $horodatage.Controle.IsChecked = $false }
}

function Update-CopieModeSynchro {
    <#
    .SYNOPSIS
        Mode synchro : grise et vide les dossiers et les seuils, impose la planification « apres_dependances ».
    .PARAMETER Fenetre
        Fenêtre du formulaire (son Tag porte les champs et la planification). Pour un autre mode, tout redevient saisissable.
    #>
    [CmdletBinding()]
    param([System.Windows.Window] $Fenetre)
    $champs = @($Fenetre.Tag.Champs)
    $mode = $champs | Where-Object { $_.Spec.Chemin -eq 'mode' } | Select-Object -First 1
    if ($null -eq $mode) { return }
    $synchro = "$($mode.Controle.SelectedItem)" -eq 'synchro'
    foreach ($e in @($champs | Where-Object { $_.Spec.Chemin -in 'source', 'cible', 'archive', 'dossier_temporaire', 'fichier_declencheur', 'seuil_minimum', 'seuil_maximum' })) {
        $e.Controle.IsEnabled = -not $synchro
        if ($synchro) { $e.Controle.Text = '' }
    }
    $temoin = $champs | Where-Object { $_.Spec.Chemin -eq 'temoin_cible' } | Select-Object -First 1
    if ($null -ne $temoin) {
        $transfert = "$($mode.Controle.SelectedItem)" -in 'copie', 'deplacement', 'archivage'
        $temoin.Controle.IsEnabled = $transfert
        if (-not $transfert) { $temoin.Controle.Text = '' }
    }
    $pl = $Fenetre.Tag.Planif
    if ($null -ne $pl) {
        if ($synchro) { $pl.Type.SelectedItem = 'apres_dependances' }
        $pl.Type.IsEnabled = -not $synchro
    }
}

function New-CopieOngletSituations {
    <#
    .SYNOPSIS
        Construit l'onglet Situations : tentatives, délai, niveau final et suite de chaque situation.
    .PARAMETER Modele
        Modèle du moteur.
    .PARAMETER Regle
        Règle complète.
    .PARAMETER Panneau
        Panneau de l'onglet.
    #>
    [CmdletBinding()]
    param($Modele, $Regle, [System.Windows.Controls.Panel] $Panneau)
    $note = New-Object System.Windows.Controls.TextBlock
    $note.Text = 'Pour chaque situation : combien de tentatives, quel délai entre elles, quel niveau de journal si elles échouent, et que faire ensuite.'
    $note.TextWrapping = 'Wrap'; $note.Foreground = [System.Windows.Media.Brushes]::Gray; $note.Margin = '0,0,0,8'
    $null = $Panneau.Children.Add($note)
    $lignes = [ordered]@{}
    $existantes = Get-CopieValeur $Regle 'situations'
    foreach ($def in $Modele.situations.PSObject.Properties) {
        $nom = $def.Name; $info = $def.Value
        $actuelle = Get-CopieValeur $existantes $nom
        $ligne = New-Object System.Windows.Controls.StackPanel; $ligne.Orientation = 'Horizontal'; $ligne.Margin = '0,0,0,4'
        $lib = New-Object System.Windows.Controls.TextBlock; $lib.Text = $nom; $lib.Width = 210; $lib.VerticalAlignment = 'Center'; $lib.FontWeight = 'SemiBold'; $lib.Foreground = [System.Windows.Media.Brushes]::DimGray
        $tent = New-Object System.Windows.Controls.TextBox; $tent.Width = 50; $tent.Text = "$(Get-CopieValeur $actuelle 'tentatives' $info.tentatives)"; $tent.ToolTip = 'Tentatives'
        $delaiAff = ConvertTo-CopieDureeAffichage -Secondes (Get-CopieValeur $actuelle 'delai_sec' $info.delai_sec)
        $delai = New-Object System.Windows.Controls.TextBox; $delai.Width = 60; $delai.Margin = '8,0,0,0'; $delai.Text = $delaiAff.Valeur; $delai.ToolTip = 'Délai entre deux tentatives'
        $unite = New-Object System.Windows.Controls.ComboBox; $unite.Width = 90; $unite.Margin = '4,0,0,0'
        foreach ($u in $Script:UnitesDuree) { $null = $unite.Items.Add($u.Nom) }
        $unite.SelectedItem = $delaiAff.Unite
        $niveau = New-Object System.Windows.Controls.ComboBox; $niveau.Width = 100; $niveau.Margin = '8,0,0,0'; $niveau.ToolTip = 'Niveau de journal si les tentatives échouent'
        foreach ($n in @($Modele.listes.niveaux)) { $null = $niveau.Items.Add("$n") }
        $niveau.SelectedItem = "$(Get-CopieValeur $actuelle 'niveau_final' $info.niveau_final)"
        $suite = New-Object System.Windows.Controls.ComboBox; $suite.Width = 190; $suite.Margin = '8,0,0,0'; $suite.ToolTip = 'Suite donnée'
        $suites = @($info.suites)
        if ($suites.Count -gt 0) {
            foreach ($s in $suites) { $null = $suite.Items.Add("$s") }
            $courante = "$(Get-CopieValeur $actuelle 'suite' $info.suite_defaut)"
            if ($courante -and -not $suite.Items.Contains($courante)) { $null = $suite.Items.Add($courante) }
            $suite.SelectedItem = $courante
        }
        else { $suite.IsEnabled = $false }
        foreach ($x in $lib, $tent, $delai, $unite, $niveau, $suite) { $null = $ligne.Children.Add($x) }
        $null = $Panneau.Children.Add($ligne)
        $lignes[$nom] = @{ Tentatives = $tent; Delai = $delai; Unite = $unite; Niveau = $niveau; Suite = $suite; ASuite = ($suites.Count -gt 0) }
    }
    $entete = New-Object System.Windows.Controls.TextBlock
    $entete.Text = 'situation  |  tentatives  |  délai  |  niveau final  |  suite'
    $entete.Foreground = [System.Windows.Media.Brushes]::Gray; $entete.FontSize = 11.5; $entete.Margin = '0,6,0,0'
    $null = $Panneau.Children.Insert(1, $entete)
    $lignes
}

function New-CopieOngletProgrammes {
    <#
    .SYNOPSIS
        Construit l'onglet Programmes : un programme optionnel à chaque point d'appel.
    .PARAMETER Modele
        Modèle du moteur.
    .PARAMETER Regle
        Règle complète.
    .PARAMETER Panneau
        Panneau de l'onglet.
    #>
    [CmdletBinding()]
    param($Modele, $Regle, [System.Windows.Controls.Panel] $Panneau)
    $note = New-Object System.Windows.Controls.TextBlock
    $note.Text = 'Programme lancé par le moteur à un point donné. La commande se saisit un élément par ligne : le programme d''abord, puis chaque argument (jamais une seule chaîne).'
    $note.TextWrapping = 'Wrap'; $note.Foreground = [System.Windows.Media.Brushes]::Gray; $note.Margin = '0,0,0,8'
    $null = $Panneau.Children.Add($note)
    $points = [ordered]@{}
    $existants = Get-CopieValeur $Regle 'programmes'
    foreach ($def in $Modele.listes.points_programme) {
        $nom = "$def"
        $actuel = Get-CopieValeur $existants $nom
        $carte = New-Object System.Windows.Controls.Border
        $carte.BorderBrush = [System.Windows.Media.Brushes]::LightGray; $carte.BorderThickness = 1; $carte.CornerRadius = 4; $carte.Padding = 8; $carte.Margin = '0,0,0,8'
        $boite = New-Object System.Windows.Controls.StackPanel
        # Dans un libellé WPF, « _ » est la touche d'accès : doublé, il s'affiche (avant_lot, apres_fichier...).
        $active = New-Object System.Windows.Controls.CheckBox; $active.Content = ('Programme « {0} »' -f $nom.Replace('_', '__')); $active.FontWeight = 'SemiBold'
        $active.IsChecked = ($null -ne $actuel)
        $variables = @($Modele.listes.variables_par_point.$nom | ForEach-Object { '{' + $_ + '}' }) -join ' '
        $cmd = New-Object System.Windows.Controls.TextBox; $cmd.AcceptsReturn = $true; $cmd.Height = 62; $cmd.VerticalScrollBarVisibility = 'Auto'; $cmd.Margin = '0,6,0,0'
        $cmd.Text = (@(Get-CopieValeur $actuel 'commande' @())) -join "`r`n"
        $timeoutAff = ConvertTo-CopieDureeAffichage -Secondes (Get-CopieValeur $actuel 'timeout_sec' 300)
        $timeout = New-Object System.Windows.Controls.TextBox; $timeout.Width = 80; $timeout.Text = $timeoutAff.Valeur
        $unite = New-Object System.Windows.Controls.ComboBox; $unite.Width = 90; $unite.Margin = '6,0,0,0'
        foreach ($u in $Script:UnitesDuree) { $null = $unite.Items.Add($u.Nom) }
        $unite.SelectedItem = $timeoutAff.Unite
        $ligneT = New-Object System.Windows.Controls.StackPanel; $ligneT.Orientation = 'Horizontal'; $ligneT.Margin = '0,6,0,0'
        $lt = New-Object System.Windows.Controls.TextBlock; $lt.Text = 'Délai maximum : '; $lt.VerticalAlignment = 'Center'
        foreach ($x in $lt, $timeout, $unite) { $null = $ligneT.Children.Add($x) }
        $aide = New-Object System.Windows.Controls.TextBlock; $aide.Text = 'Variables permises ici : ' + $variables; $aide.Foreground = [System.Windows.Media.Brushes]::Gray; $aide.FontSize = 11.5; $aide.Margin = '0,4,0,0'; $aide.TextWrapping = 'Wrap'
        foreach ($x in $active, $cmd, $ligneT, $aide) { $null = $boite.Children.Add($x) }
        $carte.Child = $boite
        $null = $Panneau.Children.Add($carte)
        $points[$nom] = @{ Active = $active; Commande = $cmd; Delai = $timeout; Unite = $unite }
    }
    $points
}

function Read-CopieFormulaire {
    <#
    .SYNOPSIS
        Lit tout le formulaire : renvoie la règle saisie ou la liste des erreurs de saisie.
    .PARAMETER Etat
        État du formulaire (Window.Tag).
    .OUTPUTS
        [pscustomobject] Regle, Erreurs.
    #>
    [CmdletBinding()]
    param([hashtable] $Etat)
    $erreurs = New-Object System.Collections.Generic.List[string]
    $regle = Copy-CopieObjet -Objet $Etat.Base
    foreach ($e in $Etat.Champs) {
        $r = Read-CopieControleChamp -Entree $e
        if ($r.Ok) { Set-CopieValeurChemin -Objet $regle -Chemin $e.Spec.Chemin -Valeur $r.Valeur } else { $erreurs.Add($r.Erreur) }
    }
    $mode = "$(Get-CopieValeur $regle 'mode' '')"
    if (@(Get-CopieModesRegle | Where-Object { $_.Nom -eq $mode -and $_.Transfert }).Count -gt 0 -and -not "$(Get-CopieValeur $regle 'cible' '')".Trim()) {
        $erreurs.Add(('Dossier cible : obligatoire pour le mode {0}.' -f $mode))
    }
    $id = "$(Get-CopieValeur $regle 'id' '')"
    if ($id -and $Etat.Mode -ne 'modification' -and @($Etat.IdsExistants | Where-Object { $_ -eq $id.ToLowerInvariant() }).Count -gt 0) {
        $erreurs.Add(('Identifiant : « {0} » existe déjà dans cet environnement.' -f $id))
    }

    $pl = $Etat.Planif
    $type = "$($pl.Type.SelectedItem)"
    $planif = [ordered]@{ type = $type }
    $lire = { param($e) $r = Read-CopieControleChamp -Entree $e; if (-not $r.Ok) { $erreurs.Add($r.Erreur) }; $r.Valeur }
    if ($type -eq 'quotidien') { $planif.heure = & $lire $pl.Heure }
    if ($type -eq 'unique') {
        $planif.date_heure = & $lire $pl.DateHeure
        $planif.rattrapage_sec = & $lire $pl.Rattrapage
        $texteDate = "$($planif.date_heure)".Trim()
        $date = [datetime]::MinValue
        if ($texteDate -and -not [datetime]::TryParseExact($texteDate, [string[]]@('yyyy-MM-dd HH:mm', 'yyyy-MM-ddTHH:mm'), [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::None, [ref]$date)) {
            $erreurs.Add('Date et heure de lancement : format AAAA-MM-JJ HH:MM attendu (exemple : 2026-12-01 07:15).')
        }
        elseif ($texteDate) {
            # Le moteur ne démarre une règle unique que s'il l'a vue avant sa date : sinon, à son premier passage, la date est déjà
            # passée, la règle est « nouvelle » donc considérée comme manquée. Il faut donc au moins deux périodes du déclencheur.
            $periode = $(if ($Etat.ContainsKey('PeriodeDeclencheurSec')) { [int]$Etat.PeriodeDeclencheurSec } else { 300 })
            $limite = (Get-Date).AddSeconds(2 * $periode)
            if ($date -le $limite) {
                # n'est refusée que la date qui vient d'être saisie : l'édition d'une règle déjà jouée reste possible
                $initiale = "$(Get-CopieValeur (Get-CopieValeur $Etat.Base 'planification') 'date_heure' '')".Trim()
                if ($Etat.Mode -ne 'modification' -or $texteDate -ne $initiale) {
                    $erreurs.Add(("Date et heure de lancement : au moins {0} min d'avance (deux fois la période du déclencheur Jenkins) : le moteur doit voir la règle avant sa date, sinon elle est considérée comme manquée et ne part pas. Date minimale : {1:yyyy-MM-dd HH:mm}." -f [math]::Ceiling(2 * $periode / 60), $limite))
                }
            }
        }
    }
    if ($type -eq 'intervalle') {
        $planif.frequence_sec = & $lire $pl.Frequence
        $planif.debut = & $lire $pl.Debut
        $planif.fin = & $lire $pl.Fin
    }
    if ($type -in 'quotidien', 'intervalle') {
        $jours = ConvertTo-CopieJours -Jour @($Script:JoursSemaine | Where-Object { $pl.Jours[$_].IsChecked })
        if ($null -eq $jours) { $erreurs.Add('Jours : au moins un jour doit être coché.') } else { $planif.jours = $jours }
        $planif.rattrapage_sec = & $lire $pl.Rattrapage
    }
    $regle.planification = [pscustomobject]$planif

    $situations = [ordered]@{}
    foreach ($nom in $Etat.Situations.Keys) {
        $l = $Etat.Situations[$nom]
        $tent = 0L; $d = ConvertFrom-CopieDureeAffichage -Valeur $l.Delai.Text -Unite "$($l.Unite.SelectedItem)"
        if (-not [long]::TryParse($l.Tentatives.Text.Trim(), [System.Globalization.NumberStyles]::None, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$tent)) { $erreurs.Add(('Situation {0} : tentatives : un nombre entier est attendu.' -f $nom)) }
        if (-not $d.Ok) { $erreurs.Add(('Situation {0} : délai : {1}.' -f $nom, $d.Erreur)) }
        $s = [ordered]@{ tentatives = $tent; delai_sec = $d.Secondes; niveau_final = "$($l.Niveau.SelectedItem)" }
        if ($l.ASuite) { $s.suite = "$($l.Suite.SelectedItem)" }
        $situations[$nom] = [pscustomobject]$s
    }
    $regle.situations = [pscustomobject]$situations

    $programmes = [ordered]@{}
    foreach ($nom in $Etat.Programmes.Keys) {
        $p = $Etat.Programmes[$nom]
        if (-not $p.Active.IsChecked) { $programmes[$nom] = $null; continue }
        $commande = @($p.Commande.Text -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        $d = ConvertFrom-CopieDureeAffichage -Valeur $p.Delai.Text -Unite "$($p.Unite.SelectedItem)"
        if ($commande.Count -eq 0) { $erreurs.Add(('Programme {0} : la commande est vide (décochez le programme pour ne pas en lancer).' -f $nom)) }
        if (-not $d.Ok) { $erreurs.Add(('Programme {0} : délai maximum : {1}.' -f $nom, $d.Erreur)) }
        $programmes[$nom] = [pscustomobject]@{ commande = $commande; timeout_sec = $d.Secondes }
    }
    $regle.programmes = [pscustomobject]$programmes
    [pscustomobject]@{ Regle = $regle; Erreurs = $erreurs.ToArray() }
}

function Confirm-CopieFormulaire {
    <#
    .SYNOPSIS
        Valide la saisie : erreurs affichées dans le formulaire, ou fermeture avec la règle saisie.
    .PARAMETER Fenetre
        Fenêtre du formulaire.
    #>
    [CmdletBinding()]
    param([System.Windows.Window] $Fenetre)
    $etat = $Fenetre.Tag
    $lecture = Read-CopieFormulaire -Etat $etat
    $bandeau = $Fenetre.FindName('BandeauErreur')
    if ($lecture.Erreurs.Count -gt 0) {
        $Fenetre.FindName('TexteErreur').Text = ($lecture.Erreurs -join "`n")
        $bandeau.Visibility = 'Visible'
        return
    }
    $bandeau.Visibility = 'Collapsed'
    $etat.Resultat = $lecture.Regle
    $Fenetre.DialogResult = $true
}

function New-CopieFormulaireRegle {
    <#
    .SYNOPSIS
        Construit (sans l'afficher) le formulaire de création, de duplication ou de modification d'une règle.

    .DESCRIPTION
        Les champs absents de la règle reçoivent la valeur de secours du moteur. Les saisies incorrectes
        (nombre, durée, jours) sont signalées dans le formulaire ; les autres contrôles (identifiant,
        chemins, dépendances...) sont ceux du moteur, appliqués à l'enregistrement.

    .PARAMETER Contexte
        Contexte de la session (Fenetre = propriétaire).

    .PARAMETER Modele
        Modèle du moteur (Get-CopieModeleRegle).

    .PARAMETER Regle
        Règle de départ (complète, Merge-CopieRegle).

    .PARAMETER Mode
        ajout, duplication ou modification.

    .PARAMETER IdsExistants
        Identifiants déjà présents (minuscules), pour refuser un doublon à l'ajout.

    .OUTPUTS
        [System.Windows.Window] ; son Tag porte l'état (Resultat = règle saisie après validation).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [hashtable] $Contexte,
        [Parameter(Mandatory)] $Modele,
        [Parameter(Mandatory)] $Regle,
        [Parameter(Mandatory)] [ValidateSet('ajout', 'duplication', 'modification')] [string] $Mode,
        [string[]] $IdsExistants = @()
    )
    $fenetre = Import-CopieXaml -Nom 'Dialog.Regle'
    if ($null -ne $Contexte.Fenetre) { $fenetre.Owner = $Contexte.Fenetre }
    $id = "$(Get-CopieValeur $Regle 'id' '')"
    $fenetre.Title = switch ($Mode) { 'ajout' { 'Nouvelle règle' } 'duplication' { 'Dupliquer une règle' } default { 'Modifier la règle ' + $id } }
    $fenetre.FindName('Intro').Text = 'Les champs marqués * sont obligatoires. Le moteur contrôle l''ensemble avant tout enregistrement.'
    $onglets = $fenetre.FindName('Onglets')

    $creerOnglet = {
        param($titre)
        $tab = New-Object System.Windows.Controls.TabItem; $tab.Header = $titre
        $defil = New-Object System.Windows.Controls.ScrollViewer; $defil.VerticalScrollBarVisibility = 'Auto'
        $panneau = New-Object System.Windows.Controls.StackPanel; $panneau.Margin = '14'
        $defil.Content = $panneau; $tab.Content = $defil
        $null = $onglets.Items.Add($tab)
        $panneau
    }

    $champs = New-Object System.Collections.Generic.List[object]
    $planif = $null
    $situations = $null
    $programmes = $null
    foreach ($onglet in (Get-CopieChampsRegle)) {
        $panneau = & $creerOnglet $onglet.Titre
        foreach ($spec in $onglet.Champs) {
            $champs.Add((New-CopieControleChamp -Spec $spec -Regle $Regle -Modele $Modele -Panneau $panneau -LectureSeule:($Mode -eq 'modification')))
        }
        if ($onglet.Titre -eq 'Anti-doublon et nommage') {
            $v = New-Object System.Windows.Controls.TextBlock
            $v.Text = 'Variables de renommage : ' + (@($Modele.listes.variables_renommage | ForEach-Object { '{' + $_ + '}' }) -join ' ') + "`nVariables de date : " + (@($Modele.listes.variables_date | ForEach-Object { '{' + $_ + '}' }) -join ' ')
            $v.TextWrapping = 'Wrap'; $v.Foreground = [System.Windows.Media.Brushes]::Gray; $v.FontSize = 11.5
            $null = $panneau.Children.Add($v)
            $planif = New-CopieOngletPlanification -Modele $Modele -Regle $Regle -Panneau (& $creerOnglet 'Planification')
        }
        if ($onglet.Titre -eq 'Durée et erreurs') { $situations = New-CopieOngletSituations -Modele $Modele -Regle $Regle -Panneau (& $creerOnglet 'Situations') }
    }
    $programmes = New-CopieOngletProgrammes -Modele $Modele -Regle $Regle -Panneau (& $creerOnglet 'Programmes')

    # période du déclencheur Jenkins : une planification unique doit laisser au moins deux périodes au moteur pour voir la règle
    $periode = 300
    if ($Contexte.ContainsKey('Config') -and [int](Get-CopieValeur (Get-CopieValeur $Contexte.Config 'Parametrage') 'PeriodeDeclencheurSec' 0) -gt 0) {
        $periode = [int]$Contexte.Config.Parametrage.PeriodeDeclencheurSec
    }
    $fenetre.Tag = @{
        Champs = $champs.ToArray(); Planif = $planif; Situations = $situations; Programmes = $programmes
        Base = $Regle; Mode = $Mode; IdsExistants = $IdsExistants; Resultat = $null; PeriodeDeclencheurSec = $periode
    }
    Update-CopiePlanificationVisible -Fenetre $fenetre
    $champMode = $champs | Where-Object { $_.Spec.Chemin -eq 'mode' } | Select-Object -First 1
    if ($null -ne $champMode) {
        $champMode.Controle.Add_SelectionChanged({
                param($s)
                $f = [System.Windows.Window]::GetWindow($s)
                Update-CopieHorodatageDisponible -Fenetre $f
                Update-CopieModeSynchro -Fenetre $f
            })
    }
    Update-CopieHorodatageDisponible -Fenetre $fenetre
    Update-CopieModeSynchro -Fenetre $fenetre
    $fenetre.FindName('BtnOk').Add_Click({ param($s) Confirm-CopieFormulaire -Fenetre ([System.Windows.Window]::GetWindow($s)) })
    $fenetre
}

function Show-CopieFormulaireRegle {
    <#
    .SYNOPSIS
        Affiche le formulaire d'une règle (voir New-CopieFormulaireRegle pour les paramètres).
    .PARAMETER Contexte
        Contexte de la session.
    .PARAMETER Modele
        Modèle du moteur.
    .PARAMETER Regle
        Règle de départ.
    .PARAMETER Mode
        ajout, duplication ou modification.
    .PARAMETER IdsExistants
        Identifiants déjà présents.
    .OUTPUTS
        La règle saisie, ou $null si le formulaire est annulé.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [hashtable] $Contexte,
        [Parameter(Mandatory)] $Modele,
        [Parameter(Mandatory)] $Regle,
        [Parameter(Mandatory)] [string] $Mode,
        [string[]] $IdsExistants = @()
    )
    $fenetre = New-CopieFormulaireRegle -Contexte $Contexte -Modele $Modele -Regle $Regle -Mode $Mode -IdsExistants $IdsExistants
    if ($fenetre.ShowDialog()) { $fenetre.Tag.Resultat } else { $null }
}
