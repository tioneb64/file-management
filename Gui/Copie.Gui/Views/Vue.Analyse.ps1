# Étape D : graphe des dépendances, historique des versions, promotion d'une règle vers un autre environnement.

function Update-CopieGraphe {
    <#
    .SYNOPSIS
        Dessine le graphe des dépendances d'un environnement : une flèche va d'une règle vers celles qui l'attendent.

    .DESCRIPTION
        Chaque nœud porte la couleur du statut de la règle (état du moteur) ; une règle inactive est en pointillés.
        Une règle en attente ou bloquée dont le motif nomme une de ses dépendances a la flèche correspondante en
        rouge : c'est la règle qui la retient. Un clic sur un nœud sélectionne la règle dans la grille.

    .PARAMETER Vue
        Vue d'un environnement.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)

    $canvas = $Vue.Graphe
    $canvas.Children.Clear()
    $g = Get-CopieDispositionGraphe -Regle @($Vue.Env.Parametrage.Regles)
    $texte = New-Object System.Collections.Generic.List[string]
    if (@($g.Noeuds).Count -eq 0) { $texte.Add('Aucune dépendance déclarée entre les règles de cet environnement.') }
    else { $texte.Add(('{0} règle(s) liée(s) ; {1} sans dépendance, non affichée(s).' -f @($g.Noeuds).Count, $g.SansLien)) }
    foreach ($m in @($g.Manquantes)) { $texte.Add(('« {0} » dépend de « {1} », qui n''existe pas (refus D01 du moteur).' -f $m.Regle, $m.Dependance)) }
    $Vue.GrapheInfo.Text = ($texte -join "`n")
    if (@($g.Noeuds).Count -eq 0) { return }

    $largeur = 190; $hauteur = 46
    $canvas.Width = $g.Largeur + 4; $canvas.Height = $g.Hauteur + 4
    $convertisseur = New-Object System.Windows.Media.BrushConverter
    $brosse = { param($hex) $convertisseur.ConvertFromString($hex) }
    $lignes = @{}
    foreach ($l in @($Vue.Lignes)) { $lignes[$l.Id.ToLowerInvariant()] = $l }
    $place = @{}
    foreach ($n in $g.Noeuds) { $place[$n.Id.ToLowerInvariant()] = $n }

    foreach ($a in $g.Aretes) {
        $de = $place[$a.De.ToLowerInvariant()]; $vers = $place[$a.Vers.ToLowerInvariant()]
        $x1 = $de.X + $largeur; $y1 = $de.Y + $hauteur / 2; $x2 = $vers.X; $y2 = $vers.Y + $hauteur / 2
        $ligneVers = $lignes[$a.Vers.ToLowerInvariant()]
        $retient = $false
        if ($null -ne $ligneVers -and $ligneVers.Statut -in 'BLOQUEE', 'EN_ATTENTE') {
            $attente = "$(Get-CopieValeur $ligneVers.Etat 'attente' '')" + ' ' + "$(Get-CopieValeur $ligneVers.Etat 'motif' '')"
            $retient = ($attente.IndexOf($a.De, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
        }
        $couleur = $(if ($retient) { '#C0392B' } else { '#8A97A6' })
        $trait = New-Object System.Windows.Shapes.Line
        $trait.X1 = $x1; $trait.Y1 = $y1; $trait.X2 = $x2 - 7; $trait.Y2 = $y2
        $trait.Stroke = & $brosse $couleur; $trait.StrokeThickness = $(if ($retient) { 2.5 } else { 1.5 })
        $null = $canvas.Children.Add($trait)
        $pointe = New-Object System.Windows.Shapes.Polygon
        $pointe.Points = New-Object System.Windows.Media.PointCollection
        foreach ($pt in @(@($x2, $y2), @(($x2 - 9), ($y2 - 5)), @(($x2 - 9), ($y2 + 5)))) { $pointe.Points.Add((New-Object System.Windows.Point($pt[0], $pt[1]))) }
        $pointe.Fill = & $brosse $couleur
        $null = $canvas.Children.Add($pointe)
    }
    foreach ($n in $g.Noeuds) {
        $l = $lignes[$n.Id.ToLowerInvariant()]
        $statut = $(if ($null -ne $l) { $l.Statut } else { '' })
        $couleur = $(if ($null -ne $l) { $l.StatutCouleur } else { '#7A8796' })
        $cadre = New-Object System.Windows.Controls.Border
        $cadre.Width = $largeur; $cadre.Height = $hauteur; $cadre.CornerRadius = 6; $cadre.BorderThickness = 2
        $cadre.BorderBrush = & $brosse $couleur
        $cadre.Background = [System.Windows.Media.Brushes]::White
        $cadre.Cursor = [System.Windows.Input.Cursors]::Hand
        $cadre.Tag = '{0}|{1}' -f $Vue.Cle, $n.Id
        if ($null -ne $l -and $l.Actif -ne 'Oui') { $cadre.Opacity = 0.6 }
        $pile = New-Object System.Windows.Controls.StackPanel; $pile.VerticalAlignment = 'Center'; $pile.Margin = '8,0'
        $t1 = New-Object System.Windows.Controls.TextBlock; $t1.Text = $n.Id; $t1.FontWeight = 'SemiBold'; $t1.TextTrimming = 'CharacterEllipsis'
        $t2 = New-Object System.Windows.Controls.TextBlock; $t2.Text = $statut; $t2.FontSize = 11.5; $t2.Foreground = & $brosse $couleur
        $null = $pile.Children.Add($t1); $null = $pile.Children.Add($t2)
        $cadre.Child = $pile
        if ($null -ne $l) {
            $info = "$(Get-CopieValeur $l.Etat 'attente' '')"
            $cadre.ToolTip = (@($n.Id, $l.Description, $(if ($info) { 'Attend : ' + $info }), $(if ($l.Actif -ne 'Oui') { '(règle inactive)' })) | Where-Object { $_ }) -join "`n"
        }
        $cadre.Add_MouseLeftButtonUp({ param($s) Select-CopieRegleGraphe -Etiquette "$($s.Tag)" })
        [System.Windows.Controls.Canvas]::SetLeft($cadre, $n.X)
        [System.Windows.Controls.Canvas]::SetTop($cadre, $n.Y)
        $null = $canvas.Children.Add($cadre)
    }
}

function Select-CopieRegleGraphe {
    <#
    .SYNOPSIS
        Clic sur un nœud du graphe : sélectionne la règle dans la grille de son onglet.
    .PARAMETER Etiquette
        « clé de la vue|identifiant de la règle ».
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Etiquette)
    $parties = $Etiquette.Split('|', 2)
    $vue = $Script:Vues[$parties[0]]
    if ($null -eq $vue) { return }
    $ligne = @($vue.Grille.ItemsSource) | Where-Object { $_.Id -eq $parties[1] } | Select-Object -First 1
    if ($null -ne $ligne) { $vue.Grille.SelectedItem = $ligne; $vue.Grille.ScrollIntoView($ligne) }
}

function Update-CopieHistoriqueDiff {
    <#
    .SYNOPSIS
        Affiche ce que la version sélectionnée de l'historique a changé.
    .PARAMETER Fenetre
        Fenêtre de l'historique (son Tag porte les versions).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [System.Windows.Window] $Fenetre)
    $grille = $Fenetre.FindName('Versions')
    $diff = $Fenetre.FindName('Differences')
    $remarque = $Fenetre.FindName('Remarque')
    $v = $grille.SelectedItem
    $diff.ItemsSource = $null
    $remarque.Text = ''
    if ($null -eq $v) { return }
    $avant = Read-CopieFichierParametrage -Chemin $v.Fichier
    $apres = Read-CopieFichierParametrage -Chemin $v.Apres
    if ($null -eq $avant.Entete -or $null -eq $apres.Entete) {
        $remarque.Text = 'Une des deux versions n''est pas lisible : comparaison impossible.'
        return
    }
    $liste = @(Compare-CopieParametrage -Avant $avant -Apres $apres)
    $diff.ItemsSource = $liste
    $notes = New-Object System.Collections.Generic.List[string]
    if ($liste.Count -eq 0) { $notes.Add('Aucune différence de contenu (le fichier a été réenregistré tel quel, ou seuls l''ordre ou la mise en forme ont changé).') }
    if ($v.Avertissements.Count -gt 0) { $notes.Add('Avertissements acceptés à l''enregistrement : ' + ($v.Avertissements -join ' ; ')) }
    if (-not $v.AFiche) { $notes.Add('Pas de fiche pour cette version (copiée à la main ?) : compte et date lus dans le nom du fichier, pas de commentaire.') }
    $remarque.Text = ($notes -join "`n")
}

function Show-CopieHistorique {
    <#
    .SYNOPSIS
        Fenêtre « Historique des modifications » d'un environnement : versions, et différences de chacune.
    .PARAMETER Vue
        Vue d'un environnement.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)
    $ctx = $Vue.Contexte
    try { $versions = @(Get-CopieHistorique -Fichier $Vue.Env.Fichier -Config $ctx.Config) }
    catch {
        [void][System.Windows.MessageBox]::Show($ctx.Fenetre, ('Le dossier des versions n''est pas lisible avec votre compte : ' + $_.Exception.Message), 'Historique', 'OK', 'Warning')
        return
    }
    $fenetre = Import-CopieXaml -Nom 'Dialog.Historique'
    if ($null -ne $ctx.Fenetre) { $fenetre.Owner = $ctx.Fenetre }
    $fenetre.Title = 'Historique des modifications : ' + $Vue.Env.Nom
    $lignes = @($versions | ForEach-Object {
            $_ | Add-Member -NotePropertyName DateTexte -NotePropertyValue $(if ($_.Date -gt [datetime]::MinValue) { $_.Date.ToString('dd/MM/yyyy HH:mm:ss') } else { [string][char]0x2014 }) -PassThru
        })
    $fenetre.FindName('Resume').Text = $(if ($lignes.Count -eq 0) { 'Aucune version : ce fichier n''a pas encore été modifié par l''interface.' } else { '{0} modification(s). Sélectionnez-en une pour voir ce qu''elle a changé.' -f $lignes.Count })
    $grille = $fenetre.FindName('Versions')
    $grille.ItemsSource = $lignes
    $grille.Add_SelectionChanged({ param($s) Update-CopieHistoriqueDiff -Fenetre ([System.Windows.Window]::GetWindow($s)) })
    if ($lignes.Count -gt 0) { $grille.SelectedIndex = 0 }
    $null = $fenetre.ShowDialog()
}

function Update-CopiePromotionApercu {
    <#
    .SYNOPSIS
        Met à jour l'aperçu de la promotion (chemins adaptés, avertissements) quand la saisie change.
    .PARAMETER Fenetre
        Fenêtre de la promotion (son Tag porte la règle d'origine et les environnements).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [System.Windows.Window] $Fenetre)
    $etat = $Fenetre.Tag
    $adapt = Get-CopieRegleAdaptee -Regle $etat.Regle -Chercher $Fenetre.FindName('Chercher').Text -Remplacer $Fenetre.FindName('Remplacer').Text
    $Fenetre.FindName('Apercu').ItemsSource = @($adapt.Changements)
    $notes = New-Object System.Collections.Generic.List[string]
    $nom = "$($Fenetre.FindName('Cible').SelectedItem)"
    $cible = $etat.Cibles | Where-Object { $_.Env.Nom -eq $nom } | Select-Object -First 1
    if ($null -ne $cible) {
        $existantes = @($cible.Env.Parametrage.Regles)
        $id = "$(Get-CopieValeur $etat.Regle 'id' '')"
        if (@($existantes | Where-Object { "$(Get-CopieValeur $_ 'id' '')".ToLowerInvariant() -eq $id.ToLowerInvariant() }).Count -gt 0) {
            $notes.Add(('« {0} » existe déjà dans « {1} » : elle sera remplacée par celle-ci (vous la verrez dans le formulaire).' -f $id, $nom))
        }
        $manquantes = @(Get-CopieDependanceManquante -Regle $etat.Regle -Existantes $existantes)
        if ($manquantes.Count -gt 0) { $notes.Add(('Dépendances absentes de « {0} » : {1}. Le moteur refusera l''enregistrement tant qu''elles n''existent pas (promouvoir d''abord ces règles, ou les retirer dans le formulaire).' -f $nom, ($manquantes -join ', '))) }
    }
    if ($adapt.Changements.Count -eq 0 -and $Fenetre.FindName('Chercher').Text) { $notes.Add('Le texte à remplacer n''apparaît dans aucun chemin de la règle.') }
    $Fenetre.FindName('Remarques').Text = ($notes -join "`n")
}

function Show-CopiePromotion {
    <#
    .SYNOPSIS
        Fenêtre de promotion : choix de l'environnement cible et du remplacement dans les chemins.
    .PARAMETER Contexte
        Contexte de la session.
    .PARAMETER Regle
        Règle à promouvoir.
    .PARAMETER Source
        Nom de l'environnement d'origine.
    .PARAMETER Cibles
        Vues des environnements cibles possibles (modifiables, autres que la source).
    .OUTPUTS
        [pscustomobject] Cible (vue), Chercher, Remplacer ; $null si annulé.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Contexte, [Parameter(Mandatory)] $Regle, [Parameter(Mandatory)] [string] $Source, [Parameter(Mandatory)] [object[]] $Cibles)
    $fenetre = Import-CopieXaml -Nom 'Dialog.Promotion'
    if ($null -ne $Contexte.Fenetre) { $fenetre.Owner = $Contexte.Fenetre }
    $fenetre.FindName('Titre').Text = ('Promouvoir la règle « {0} » de « {1} » vers un autre environnement.' -f (Get-CopieValeur $Regle 'id' ''), $Source)
    $cible = $fenetre.FindName('Cible')
    foreach ($c in $Cibles) { $null = $cible.Items.Add($c.Env.Nom) }
    $fenetre.Tag = @{ Regle = $Regle; Cibles = $Cibles }
    $cible.SelectedIndex = 0
    $cible.Add_SelectionChanged({ param($s) Update-CopiePromotionApercu -Fenetre ([System.Windows.Window]::GetWindow($s)) })
    $fenetre.FindName('Chercher').Add_TextChanged({ param($s) Update-CopiePromotionApercu -Fenetre ([System.Windows.Window]::GetWindow($s)) })
    $fenetre.FindName('Remplacer').Add_TextChanged({ param($s) Update-CopiePromotionApercu -Fenetre ([System.Windows.Window]::GetWindow($s)) })
    $fenetre.FindName('BtnOk').Add_Click({ param($s) [System.Windows.Window]::GetWindow($s).DialogResult = $true })
    Update-CopiePromotionApercu -Fenetre $fenetre
    if (-not $fenetre.ShowDialog()) { return $null }
    $nom = "$($cible.SelectedItem)"
    [pscustomobject]@{ Cible = ($Cibles | Where-Object { $_.Env.Nom -eq $nom } | Select-Object -First 1); Chercher = $fenetre.FindName('Chercher').Text; Remplacer = $fenetre.FindName('Remplacer').Text }
}

function Invoke-CopiePromotion {
    <#
    .SYNOPSIS
        Promeut la règle sélectionnée vers un autre environnement : adaptation des chemins, puis formulaire et enregistrement sécurisé de la cible.

    .DESCRIPTION
        La promotion ne contourne aucun contrôle : la règle adaptée s'ouvre dans le formulaire de la cible (à
        relire et corriger), puis passe par la même vérification du moteur, le même contrôle d'édition
        simultanée, le même commentaire obligatoire et la même version précédente que toute modification.
        Si la règle existe déjà dans la cible, elle est remplacée (après confirmation).

    .PARAMETER Vue
        Vue de l'environnement d'origine.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Vue)
    $ctx = $Vue.Contexte
    if ($ctx.Profil -ne 'Admin' -or $Vue.Occupe) { return }
    $choisie = $Vue.Grille.SelectedItem
    if ($null -eq $choisie) { return }
    $cibles = @($Script:Vues.Values | Where-Object { $_.Env.Nom -ne $Vue.Env.Nom -and $_.Env.Modifiable -and -not $_.Occupe } | Sort-Object { $_.Env.Nom })
    if ($cibles.Count -eq 0) {
        [void][System.Windows.MessageBox]::Show($ctx.Fenetre, 'Aucun autre environnement modifiable dans ce dossier de paramétrage.', 'Promouvoir', 'OK', 'Information')
        return
    }
    $source = Read-CopieFichierParametrage -Chemin $Vue.Env.Fichier
    if ($source.Empreinte -ne $Vue.Env.Parametrage.Empreinte) {
        [void][System.Windows.MessageBox]::Show($ctx.Fenetre, 'Le fichier source a été modifié depuis son affichage. Il est rechargé : recommencez.', 'Fichier modifié', 'OK', 'Information')
        Sync-CopieParametrage -Vue $Vue -Selection $choisie.Id
        return
    }
    $regleSource = @($source.Regles | Where-Object { "$(Get-CopieValeur $_ 'id' '')" -eq $choisie.Id }) | Select-Object -First 1
    if ($null -eq $regleSource) { return }
    try { $modele = Get-CopieModeleRegle -Config $ctx.Config }
    catch { [void][System.Windows.MessageBox]::Show($ctx.Fenetre, $_.Exception.Message, 'Moteur injoignable', 'OK', 'Error'); return }

    $choix = Show-CopiePromotion -Contexte $ctx -Regle $regleSource -Source $Vue.Env.Nom -Cibles $cibles
    if ($null -eq $choix) { return }
    $cible = $choix.Cible
    $frais = Read-CopieFichierParametrage -Chemin $cible.Env.Fichier
    if ($frais.Empreinte -ne $cible.Env.Parametrage.Empreinte) {
        [void][System.Windows.MessageBox]::Show($ctx.Fenetre, ('Le fichier de « {0} » a été modifié depuis son affichage. Il est rechargé : recommencez.' -f $cible.Env.Nom), 'Fichier modifié', 'OK', 'Information')
        Sync-CopieParametrage -Vue $cible
        return
    }
    if ($frais.Erreurs.Count -gt 0 -or $null -eq $frais.Entete) {
        [void][System.Windows.MessageBox]::Show($ctx.Fenetre, ('Le fichier de « {0} » n''est pas lisible, il ne peut pas être modifié.' -f $cible.Env.Nom), 'Promouvoir', 'OK', 'Error')
        return
    }
    $adaptee = Get-CopieRegleAdaptee -Regle $regleSource -Chercher $choix.Chercher -Remplacer $choix.Remplacer
    $regles = @($frais.Regles)
    $ids = @($regles | ForEach-Object { "$(Get-CopieValeur $_ 'id' '')".ToLowerInvariant() })
    $id = $choisie.Id
    $existe = ($ids -contains $id.ToLowerInvariant())
    $mode = 'ajout'
    if ($existe) {
        $idCible = "$(Get-CopieValeur ($regles | Where-Object { "$(Get-CopieValeur $_ 'id' '')".ToLowerInvariant() -eq $id.ToLowerInvariant() } | Select-Object -First 1) 'id')"
        $conf = [System.Windows.MessageBox]::Show($ctx.Fenetre, ("La règle « {0} » existe déjà dans « {1} ». Elle sera remplacée par celle de « {2} ».`n`nContinuer ?" -f $idCible, $cible.Env.Nom, $Vue.Env.Nom), 'Promouvoir', 'YesNo', 'Warning')
        if ($conf -ne [System.Windows.MessageBoxResult]::Yes) { return }
        $mode = 'modification'
        $adaptee.Regle.id = $idCible
        $id = $idCible
    }
    $depart = Merge-CopieRegle -Modele $modele.regle -Existante $adaptee.Regle
    if ($null -ne $Script:Session -and $null -ne $Script:Session.Tabs) { $Script:Session.Tabs.SelectedItem = $cible.Tab }
    Write-CopieJournal -Contexte $ctx -Niveau 'INFO' -Evenement 'promotion_demarree' -Message ('Promotion de {0} de {1} vers {2}' -f $id, $Vue.Env.Nom, $cible.Env.Nom) `
        -Donnees @{ regle = $id; source = $Vue.Env.Nom; cible = $cible.Env.Nom; chemins_modifies = @($adaptee.Changements).Count }
    Invoke-CopieFormulaireEtEnregistrement -Vue $cible -Modele $modele -Depart $depart -Mode $mode -Regle $regles -IdsExistants $ids -IdChoisi $id -Verbe 'promouvoir'
}
