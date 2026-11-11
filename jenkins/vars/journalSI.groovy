/**
 * Bibliotheque partagee "journal-si" : evenements de niveau JOB, dans le meme format JSON que le
 * module Python journal_si.py (fichiers lus par Grafana Alloy).
 *
 * Elle n'ecrit RIEN elle-meme : elle appelle `python journal_si.py`, qui est la seule source du
 * format. Une panne de journalisation n'echoue jamais le build (un message est affiche).
 *
 * Utilisation (voir jenkins/Jenkinsfile.transfert) :
 *
 *   @Library('journal-si') _
 *   journalSI.debutJob(application: 'file_management', environnement: 'production', dossier: 'D:\\Copie\\logs')
 *   ...
 *   post { always { script { journalSI.finJob(application: 'file_management', environnement: 'production',
 *                                             dossier: 'D:\\Copie\\logs') } } }
 *
 * Parametres communs : application, environnement, dossier (obligatoires) ; champs (Map de champs
 * supplementaires) ; python (defaut : variable COPIE_PYTHON, sinon `python`) ;
 * script (defaut : %COPIE_DEPOT%\journal_si.py).
 * Les champs job, build, build_url et noeud sont ajoutes par journal_si.py a partir des variables
 * JOB_NAME, BUILD_NUMBER, BUILD_URL et NODE_NAME de Jenkins.
 */
import groovy.json.JsonOutput

/** Un evenement quelconque : evenement (obligatoire), niveau (INFO, WARNING, ERREUR, defaut INFO). */
def evenement(Map p) {
    try {
        controler(p.application, 'application')
        controler(p.environnement, 'environnement')
        controler(p.evenement, 'evenement')
        def niveau = p.niveau ?: 'INFO'
        controler(niveau, 'niveau')
        if (!p.dossier || p.dossier.contains('"')) {
            throw new IllegalArgumentException('parametre dossier absent ou invalide')
        }
        def python = p.python ?: (env.COPIE_PYTHON ?: 'python')
        def script = p.script ?: ((env.COPIE_DEPOT ?: 'D:\\Scripts\\file_management') + '\\journal_si.py')
        def champs = p.champs ?: [:]
        def fichier = pwd(tmp: true) + '\\journal_si_' + System.nanoTime() + '.json'
        // les champs passent par un fichier JSON : aucun probleme de guillemets ni d'accents sur la ligne de commande
        writeFile file: fichier, text: JsonOutput.toJson(champs), encoding: 'UTF-8'
        def commande = '@"' + python + '" "' + script + '"' +
            ' --dossier "' + p.dossier + '"' +
            ' --application ' + p.application +
            ' --environnement ' + p.environnement +
            ' --evenement ' + p.evenement +
            ' --niveau ' + niveau +
            ' --champs-json "' + fichier + '"'
        bat(returnStatus: true, script: commande + '\r\n@del "' + fichier + '" 2>nul')
    } catch (Exception e) {
        echo 'journal-si : evenement non ecrit (' + e.getMessage() + ')'
    }
}

/** Debut du job. */
def debutJob(Map p) {
    evenement(p + [evenement: 'debut_job', niveau: 'INFO'])
}

/**
 * Fin du job, a appeler dans `post { always { ... } }`. Ajoute le statut Jenkins (SUCCESS, UNSTABLE,
 * FAILURE, ABORTED), la duree en millisecondes ; le niveau suit le statut :
 * SUCCESS -> INFO, UNSTABLE et ABORTED -> WARNING, FAILURE -> ERREUR. Parametre facultatif : codeRetour (le code retour du moteur, entier).
 */
def finJob(Map p) {
    def resultat = currentBuild.currentResult ?: 'SUCCESS'
    def niveaux = [SUCCESS: 'INFO', UNSTABLE: 'WARNING', ABORTED: 'WARNING', FAILURE: 'ERREUR', NOT_BUILT: 'INFO']
    long duree = System.currentTimeMillis() - currentBuild.startTimeInMillis
    def champs = [statut: resultat, duree_ms: duree]
    if (p.codeRetour != null && p.codeRetour.toString().isInteger()) {
        champs.code_retour = p.codeRetour.toString().toInteger()
    }
    if (p.champs) {
        champs.putAll(p.champs)
    }
    evenement(p + [evenement: 'fin_job', niveau: niveaux[resultat] ?: 'INFO', champs: champs])
}

/** Refuse tout ce qui n'est pas un identifiant simple (le texte est place tel quel sur la ligne de commande). */
private void controler(valeur, String nom) {
    if (!valeur || !(valeur.toString() ==~ /[A-Za-z0-9_.-]+/)) {
        throw new IllegalArgumentException('parametre ' + nom + ' absent ou invalide : ' + valeur)
    }
}
