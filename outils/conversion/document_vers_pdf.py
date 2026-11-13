# outil: document_vers_pdf
# description: Convertit en PDF des documents Word (docx, doc), OpenDocument (odt, ods, odp), RTF, Excel (xlsx), PowerPoint (pptx) avec LibreOffice (soffice --headless) ; LibreOffice doit etre installe, sinon code retour 4 (OUTIL_SOFFICE peut donner...
# parametre: --vers DOSSIER | facultatif | dossier des PDF (defaut : a cote du document)
# parametre: --ecraser | facultatif | remplace un PDF existant
# parametre: --delai SECONDES | facultatif | delai maximal par document (defaut 300)
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
"""Convertit des documents (docx, doc, odt, rtf, xlsx, pptx...) en PDF avec LibreOffice (soffice --headless)."""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun import dependances
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import BUSINESS_RULE_VIOLATION, EXTERNAL_SERVICE_ERROR, ErreurOutil
from outils.commun.fichiers import verifier_ecrasement
from outils.commun.outil import Outil

OUTIL = Outil("document_vers_pdf", "Convertit en PDF des documents Word (docx, doc), OpenDocument (odt, ods, odp), "
              "RTF, Excel (xlsx), PowerPoint (pptx) avec LibreOffice (soffice --headless) ; LibreOffice doit etre "
              "installe, sinon code retour 4 (OUTIL_SOFFICE peut donner le chemin de soffice.exe). Chaque "
              "conversion utilise un profil LibreOffice temporaire : plusieurs conversions peuvent tourner en "
              "meme temps sans se bloquer.", "conversion")
EXTENSIONS = (".docx", ".doc", ".odt", ".rtf", ".xlsx", ".xls", ".ods", ".pptx", ".ppt", ".odp", ".txt", ".html")


@OUTIL.arguments
def arguments(p):
    options_entrees(p, recursif=False)
    p.add_argument("--vers", metavar="DOSSIER", help="dossier des PDF (defaut : a cote du document)")
    p.add_argument("--ecraser", action="store_true", help="remplace un PDF existant")
    p.add_argument("--delai", type=int, default=300, metavar="SECONDES", help="delai maximal par document (defaut 300)")


@OUTIL.principal
def principal(ctx, args):
    documents = [c for c, _ in ctx.fichiers()]
    if not documents:
        return
    soffice = dependances.trouver_programme("soffice", ctx.env)
    for document in documents:
        with ctx.tolerer("conversion_echec", fichier=document):
            if not document.lower().endswith(EXTENSIONS):
                raise ErreurOutil("format non pris en charge : %s" % os.path.basename(document), BUSINESS_RULE_VIOLATION)
            dossier = args.vers or os.path.dirname(os.path.abspath(document))
            sortie = os.path.join(dossier, os.path.splitext(os.path.basename(document))[0] + ".pdf")
            verifier_ecrasement(sortie, args.ecraser)
            if ctx.simulation:
                ctx.action("document_a_convertir", "Serait converti en PDF : %s" % os.path.basename(document),
                           fichier=document, cible=sortie)
                continue
            os.makedirs(dossier, exist_ok=True)
            travail = tempfile.mkdtemp(prefix="copie_soffice_")
            try:
                profil = "file:///" + os.path.join(travail, "profil").replace("\\", "/")
                code, sortie_prog = dependances.executer_externe(
                    [soffice, "-env:UserInstallation=" + profil, "--headless", "--norestore", "--convert-to", "pdf",
                     "--outdir", os.path.join(travail, "sortie"), os.path.abspath(document)], delai=args.delai)
                produit = os.path.join(travail, "sortie", os.path.splitext(os.path.basename(document))[0] + ".pdf")
                if code != 0 or not os.path.isfile(produit):
                    raise ErreurOutil("LibreOffice n'a pas produit de PDF (code %s) : %s"
                                      % (code, sortie_prog.strip()[-400:]), EXTERNAL_SERVICE_ERROR)
                verifier_ecrasement(sortie, args.ecraser)
                temporaire = sortie + ".copie_en_cours"
                shutil.copyfile(produit, temporaire)
                os.replace(temporaire, sortie)
            finally:
                shutil.rmtree(travail, ignore_errors=True)
            ctx.action("document_converti", "Converti en PDF : %s" % os.path.basename(document), fichier=document,
                       cible=sortie, taille=os.path.getsize(sortie))


if __name__ == "__main__":
    OUTIL.lancer()
