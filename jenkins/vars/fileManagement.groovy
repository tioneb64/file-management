/**
 * Appelle le moteur file_management et traduit son code retour en resultat de build Jenkins.
 *
 *   fileManagement(config: 'D:\\Parametrage\\production.jsonl')                       // lancement
 *   fileManagement(config: '...', commande: '--sauvegarder-base D:\\Copie\\sauvegardes')
 *   fileManagement(config: '...', commande: '--verifier')
 *
 * Parametres :
 *   config   (obligatoire) fichier de parametrage de l'environnement
 *   commande options du moteur ; vide = lancement des regles dues
 *   python   interpreteur (defaut : variable COPIE_PYTHON, sinon `python`)
 *   depot    dossier du depot file_management (defaut : variable COPIE_DEPOT)
 *   lanceur  `-m file_management` aujourd'hui ; `file_management.py` quand le lanceur v2 remplacera le v1
 *
 * Codes retour du moteur : 0 -> SUCCESS ; 4 -> UNSTABLE (au moins un avertissement) ;
 * tout autre code -> FAILURE (1 : erreur pendant le lancement, 2 : parametrage ou base inutilisable).
 * Renvoie le code retour et le memorise dans la variable COPIE_CODE_RETOUR.
 */
def call(Map p) {
    if (!p.config) {
        error('fileManagement : le parametre config est obligatoire')
    }
    def python = p.python ?: (env.COPIE_PYTHON ?: 'python')
    def depot = p.depot ?: env.COPIE_DEPOT
    if (!depot) {
        error('fileManagement : dossier du depot inconnu (parametre depot ou variable COPIE_DEPOT)')
    }
    def lanceur = p.lanceur ?: '-m file_management'
    def commande = p.commande ?: ''
    int rc = 0
    dir(depot) {
        // chcp 65001 : la console de l'agent affiche les accents ; le moteur ecrit toujours en UTF-8
        rc = bat(returnStatus: true,
                 script: '@chcp 65001 > nul\r\n@"' + python + '" ' + lanceur + ' --config "' + p.config + '" ' + commande)
    }
    env.COPIE_CODE_RETOUR = rc.toString()      // repris par journalSI.finJob dans le journal du job
    if (rc == 0) {
        echo 'file_management : succes'
    } else if (rc == 4) {
        unstable('file_management : au moins un avertissement (code retour 4), voir le journal du build')
    } else {
        error('file_management : code retour ' + rc)
    }
    return rc
}
