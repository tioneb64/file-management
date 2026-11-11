# Configuration du point d'accès JEA. Ce fichier est (ré)écrit par Installer-PointAccesJea.ps1 ;
# ne le modifier à la main qu'en connaissance de cause (il décide ce que le compte de service lance).
@{
    Python             = 'C:\Python314\python.exe'          # interpréteur du moteur
    Racine             = 'D:\file_management'                # dossier qui contient le paquet copie\
    DossierParametrage = 'D:\Parametrage'                   # seuls les fichiers de ce dossier sont acceptés
    GroupeAdmin        = 'DOMAINE\GG_Copie_Admins'          # seul ce groupe peut lancer une commande d'écriture
    DelaiMaxSec        = 600                                # au-delà, le moteur est arrêté
}
