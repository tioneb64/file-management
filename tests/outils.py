"""Aides communes aux tests : dossiers temporaires et fichiers de test."""
import os
import shutil
import tempfile
import time
import unittest


class CasTemporaire(unittest.TestCase):
    """Chaque test dispose d'un dossier temporaire vide, supprime a la fin."""

    def setUp(self):
        self.racine = tempfile.mkdtemp(prefix="copie_test_")
        self.addCleanup(self.nettoyer)

    def nettoyer(self):
        def forcer(fonction, chemin, _info):
            os.chmod(chemin, 0o700)
            fonction(chemin)
        shutil.rmtree(self.racine, onerror=forcer)

    def chemin(self, *morceaux):
        return os.path.join(self.racine, *morceaux)

    def ecrire(self, chemin_relatif, contenu=b"contenu", age_jours=None):
        """Cree un fichier (et ses dossiers) ; age_jours recule sa date de modification."""
        chemin = self.chemin(chemin_relatif)
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        if isinstance(contenu, str):
            contenu = contenu.encode("utf-8")
        with open(chemin, "wb") as f:
            f.write(contenu)
        if age_jours is not None:
            instant = time.time() - age_jours * 86400
            os.utime(chemin, (instant, instant))
        return chemin

    def lire(self, chemin):
        with open(chemin, "rb") as f:
            return f.read()
