# outil: image_convertir
# description: Convertit le format (--format), redimensionne (--largeur-max / --hauteur-max, proportions conservees, jamais d'agrandissement) et compresse (--qualite) des images.
# parametre: --format {bmp,gif,jpeg,jpg,png,tiff,webp} | facultatif | format cible (defaut : celui de chaque image)
# parametre: --largeur-max PX | facultatif | largeur maximale en pixels
# parametre: --hauteur-max PX | facultatif | hauteur maximale en pixels
# parametre: --qualite 1-95 | facultatif | qualite JPEG / WEBP (defaut 85)
# parametre: --vers DOSSIER | facultatif | dossier des images produites
# parametre: --sur-place | facultatif | remplace l'image d'origine (ou la reecrit dans son format)
# parametre: --ecraser | facultatif | remplace une image de sortie existante
# parametre: CHEMIN | facultatif | fichiers ou dossiers (jokers * ? [] acceptes) (a defaut : {fichier}, puis {liste}, puis {source} du moteur)
# parametre: --liste FICHIER | facultatif | fichier texte UTF-8, un chemin par ligne (comme {liste} du moteur) ; repetable
# parametre: --masque JOKER | facultatif | ne garder que les noms correspondant (ex. *.csv) ; repetable
# parametre: --exclure JOKER | facultatif | ecarter les noms correspondant ; repetable
# parametre: --recursif/-r | facultatif | descendre dans les sous-dossiers des dossiers designes
"""Convertit, redimensionne et compresse des images (png <-> jpg, webp, bmp, tiff, gif) avec Pillow."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
import amorce_outils  # noqa: F401  (outils.commun et journal_si, ou que soit le dossier des outils)
from outils.commun import dependances
from outils.commun.entrees import options_entrees
from outils.commun.erreurs import BUSINESS_RULE_VIOLATION, ErreurOutil, ErreurParametres
from outils.commun.fichiers import sortie_atomique, verifier_ecrasement
from outils.commun.outil import Outil

FORMATS = {"png": ("PNG", ".png"), "jpg": ("JPEG", ".jpg"), "jpeg": ("JPEG", ".jpg"), "webp": ("WEBP", ".webp"),
           "bmp": ("BMP", ".bmp"), "tiff": ("TIFF", ".tif"), "gif": ("GIF", ".gif")}
EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif")
OUTIL = Outil("image_convertir", "Convertit le format (--format), redimensionne (--largeur-max / --hauteur-max, "
              "proportions conservees, jamais d'agrandissement) et compresse (--qualite) des images. Necessite le "
              "module Python Pillow (pip install Pillow), sinon code retour 4. Ecrit dans --vers, ou sur place avec "
              "--sur-place (alors, si le resultat est plus gros que l'original, l'original est conserve). "
              "L'orientation EXIF est appliquee ; l'EXIF des JPEG est conserve.", "conversion")


@OUTIL.arguments
def arguments(p):
    options_entrees(p)
    p.add_argument("--format", choices=sorted(FORMATS), help="format cible (defaut : celui de chaque image)")
    p.add_argument("--largeur-max", type=int, metavar="PX", help="largeur maximale en pixels")
    p.add_argument("--hauteur-max", type=int, metavar="PX", help="hauteur maximale en pixels")
    p.add_argument("--qualite", type=int, default=85, metavar="1-95", help="qualite JPEG / WEBP (defaut 85)")
    p.add_argument("--vers", metavar="DOSSIER", help="dossier des images produites")
    p.add_argument("--sur-place", action="store_true", help="remplace l'image d'origine (ou la reecrit dans son format)")
    p.add_argument("--ecraser", action="store_true", help="remplace une image de sortie existante")


@OUTIL.principal
def principal(ctx, args):
    if not args.vers and not args.sur_place:
        raise ErreurParametres("indiquer --vers DOSSIER ou --sur-place")
    if args.vers and args.sur_place:
        raise ErreurParametres("--vers et --sur-place sont exclusifs")
    if not 1 <= args.qualite <= 95:
        raise ErreurParametres("--qualite : entre 1 et 95")
    for nom, valeur in (("--largeur-max", args.largeur_max), ("--hauteur-max", args.hauteur_max)):
        if valeur is not None and valeur < 1:
            raise ErreurParametres("%s doit etre positif" % nom)
    images = [c for c, _ in ctx.fichiers()]
    if not images:
        return
    dependances.module_optionnel("PIL", "Pillow")
    from PIL import Image, ImageOps
    for chemin in images:
        with ctx.tolerer("conversion_echec", fichier=chemin):
            if not chemin.lower().endswith(EXTENSIONS):
                raise ErreurOutil("format d'image non pris en charge : %s" % os.path.basename(chemin), BUSINESS_RULE_VIOLATION)
            with Image.open(chemin) as source:
                format_source = source.format
                nom_format, extension = FORMATS[args.format] if args.format else (
                    format_source, os.path.splitext(chemin)[1].lower())
                racine = os.path.splitext(os.path.basename(chemin))[0]
                sortie = chemin if args.sur_place and not args.format else os.path.join(
                    args.vers or os.path.dirname(os.path.abspath(chemin)), racine + extension)
                ecraser = args.ecraser or sortie == chemin
                if ctx.simulation:
                    verifier_ecrasement(sortie, ecraser)
                    ctx.action("image_a_convertir", "Serait convertie : %s" % os.path.basename(chemin), fichier=chemin,
                               cible=sortie, format=nom_format)
                    continue
                image = ImageOps.exif_transpose(source)
                exif = source.info.get("exif") if nom_format == "JPEG" and format_source == "JPEG" else None
                if args.largeur_max or args.hauteur_max:
                    limite = (args.largeur_max or image.width, args.hauteur_max or image.height)
                    if image.width > limite[0] or image.height > limite[1]:
                        image = image.copy()
                        image.thumbnail(limite, Image.LANCZOS)
                if nom_format == "JPEG" and image.mode not in ("RGB", "L", "CMYK"):
                    fond = Image.new("RGB", image.size, (255, 255, 255))
                    image = image.convert("RGBA")
                    fond.paste(image, mask=image.split()[-1])
                    image = fond
                options = {"format": nom_format}
                if nom_format in ("JPEG", "WEBP"):
                    options["quality"] = args.qualite
                if nom_format in ("JPEG", "PNG"):
                    options["optimize"] = True
                if exif:
                    options["exif"] = exif
                avant = os.path.getsize(chemin)
                try:
                    with sortie_atomique(sortie, ecraser) as tmp:
                        with open(tmp, "wb") as f:
                            image.save(f, **options)
                        if sortie == chemin and os.path.getsize(tmp) >= avant and not (args.largeur_max or args.hauteur_max):
                            raise _PasPlusPetit()
                except _PasPlusPetit:
                    ctx.compter("deja_optimales")
                    ctx.debug("image_non_reduite", "Image deja optimale, conservee : %s" % os.path.basename(chemin),
                              fichier=chemin)
                    continue
            ctx.action("image_convertie", "Image convertie : %s" % os.path.basename(chemin), fichier=chemin, cible=sortie,
                       format=nom_format, taille_avant=avant, taille=os.path.getsize(sortie))


class _PasPlusPetit(Exception):
    pass


if __name__ == "__main__":
    OUTIL.lancer()
