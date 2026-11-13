# bibliotheque: socle des outils : options communes, journal, codes retour, tolerance aux erreurs par element
"""Socle des outils : options communes, journal, codes retour, tolerance aux erreurs par element.

Un outil est un script :

    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_amorce"))
    import amorce_outils
    from outils.commun.outil import Outil

    OUTIL = Outil("zip_creer", "Cree une archive zip", "compression")

    @OUTIL.arguments
    def arguments(p):
        p.add_argument("--sortie", required=True)

    @OUTIL.principal
    def principal(ctx, args):
        with ctx.tolerer(fichier=...):
            ...
            ctx.action("fichier_zippe", "Fichier ajoute a l'archive", fichier=...)

    if __name__ == "__main__":
        OUTIL.lancer()

Codes retour : 0 fait ; 1 "rien a faire" (seulement avec --code-si-rien 1) ; 2 erreur d'execution ;
3 parametres invalides ; 4 dependance externe absente.
"""
import argparse
import collections
import contextlib
import os
import sys
import traceback

from outils.commun import erreurs, journal
from outils.commun.entrees import designes, fichiers
from outils.commun.erreurs import (ArretOutil, DependanceAbsente, ErreurOutil, ErreurParametres, CODE_DEPENDANCE,
                                   CODE_ERREUR, CODE_OK, CODE_PARAMETRES)


class _Sortie(Exception):
    def __init__(self, code):
        Exception.__init__(self)
        self.code = code


class _Parser(argparse.ArgumentParser):
    """argparse qui ne quitte jamais le processus : erreur de parametres -> ErreurParametres (code 3)."""

    def error(self, message):
        raise ErreurParametres(message)

    def exit(self, status=0, message=None):
        if message:
            raise ErreurParametres(message.strip())
        raise _Sortie(status)


class Contexte(object):
    """Ce que voit un outil : ses options, son journal et ses compteurs."""

    def __init__(self, outil, args, journal_, env, simulation):
        self.outil = outil
        self.args = args
        self.journal = journal_
        self.env = env
        self.simulation = simulation
        self.compteurs = collections.OrderedDict()
        self.nb_actions = 0
        self.nb_erreurs = 0
        self.nb_avertissements = 0
        self.type_erreur = None
        self.code_impose = None
        self.sortie = sys.stdout
        self._sortie_erreur = sys.stderr

    # ----- journal ----- #
    def _ecrire(self, evenement, niveau, message, champs):
        champs = dict((k, v) for k, v in champs.items() if v is not None)
        champs["message"] = message
        self.journal.evenement(evenement, niveau, **champs)

    def debug(self, evenement, message, **champs):
        self._ecrire(evenement, "DEBUG", message, champs)

    def info(self, evenement, message, **champs):
        self._ecrire(evenement, "INFO", message, champs)

    def action(self, evenement, message, compteur="traites", **champs):
        """Une action faite (ou, en simulation, qui serait faite) : INFO + compteur."""
        self.nb_actions += 1
        if compteur:
            self.compter(compteur)
        self._ecrire(evenement, "INFO", message, champs)

    def avertir(self, evenement, message, **champs):
        self.nb_avertissements += 1
        self._ecrire(evenement, "WARNING", message, champs)
        self.ecrire_erreur("ATTENTION : " + message)

    def echec(self, evenement, message, error_type=erreurs.FILE_IO_ERROR, **champs):
        """Erreur sur un element : ERROR dans le journal ; l'outil continue (sauf --arreter-si-erreur)."""
        self.nb_erreurs += 1
        self.type_erreur = self.type_erreur or error_type
        self._ecrire(evenement, "ERROR", message, dict(champs, error_type=error_type))
        self.ecrire_erreur("ERREUR : " + message)
        if getattr(self.args, "arreter_si_erreur", False):
            raise ArretOutil()

    def compter(self, nom, n=1):
        self.compteurs[nom] = self.compteurs.get(nom, 0) + n

    def imposer_code(self, code):
        """Code retour force en fin d'outil (ex. 1 = fichier invalide, a ignorer, pour avant_fichier)."""
        self.code_impose = code

    # ----- sorties ----- #
    def afficher(self, texte):
        """Ligne sur la sortie standard (reprise, tronquee a 8 Ko, par le moteur) : rester concis."""
        self.sortie.write(texte + "\n")

    def ecrire_erreur(self, texte):
        try:
            self._sortie_erreur.write(texte + "\n")
        except Exception:
            pass

    # ----- elements ----- #
    @contextlib.contextmanager
    def tolerer(self, evenement="element_en_echec", **champs):
        """Journalise l'exception de l'element en cours et laisse l'outil passer au suivant."""
        try:
            yield
        except (ArretOutil, DependanceAbsente, ErreurParametres, _Sortie):
            raise
        except ErreurOutil as e:
            self.echec(evenement, str(e), e.type_erreur, **champs)
        except OSError as e:
            self.echec(evenement, erreurs.decrire_os(e), erreurs.type_erreur_os(e), **champs)
        except Exception as e:
            self.echec(evenement, "Erreur inattendue (%s) : %s" % (type(e).__name__, e),
                       erreurs.INTERNAL_ERROR, exception=type(e).__name__,
                       stacktrace=traceback.format_exc(), **champs)

    def designes(self):
        """Chemins designes (arguments, --liste, sinon COPIE_FICHIER / COPIE_LISTE / COPIE_SOURCE)."""
        try:
            return designes(self.args, self.env)
        except OSError as e:
            raise ErreurParametres("liste de fichiers illisible : %s" % erreurs.decrire_os(e))

    def fichiers(self, chemins=None, recursif=None, dossiers=True):
        return fichiers(self, chemins, recursif, dossiers)


class Outil(object):
    def __init__(self, nom, description, domaine):
        self.nom = nom
        self.description = description
        self.domaine = domaine
        self._arguments = []
        self._principal = None

    # ----- declaration ----- #
    def arguments(self, fonction):
        self._arguments.append(fonction)
        return fonction

    def principal(self, fonction):
        self._principal = fonction
        return fonction

    def parser(self):
        p = _Parser(prog=self.nom, description=self.description, add_help=False, allow_abbrev=False,
                    formatter_class=argparse.RawDescriptionHelpFormatter,
                    epilog="Codes retour : 0 fait, 1 rien a faire (seulement avec --code-si-rien 1), "
                           "2 erreur, 3 parametres invalides, 4 dependance externe absente.")
        for fonction in self._arguments:
            fonction(p)
        g = p.add_argument_group("options communes")
        g.add_argument("--aide", "-h", action="help", help="affiche cette aide")
        g.add_argument("--simulation", action="store_true",
                       help="n'ecrit, ne supprime rien : journalise ce qui serait fait (aussi actif si "
                            "COPIE_SIMULATION=1)")
        g.add_argument("--dossier-logs", metavar="DOSSIER",
                       help="dossier du journal (defaut : COPIE_DOSSIER_LOGS, puis JOURNAL_SI_DOSSIER, puis logs)")
        g.add_argument("--regle", metavar="ID", help="regle appelante (defaut : COPIE_REGLE)")
        g.add_argument("--environnement", metavar="CODE",
                       help="code d'environnement de la plateforme : dev, build, test, pprod, prod, run, int "
                            "(defaut : COPIE_CODE_ENVIRONNEMENT, sinon deduit de COPIE_ENVIRONNEMENT, sinon dev)")
        g.add_argument("--console", action="store_true", help="ecrit aussi le journal sur la sortie standard")
        g.add_argument("--verbeux", action="store_true", help="journalise aussi le niveau DEBUG")
        g.add_argument("--code-si-rien", type=int, default=0, metavar="N",
                       help="code retour quand il n'y a rien a faire (defaut 0 ; 1 = 'ne rien livrer' "
                            "pour avant_lot, 'ignorer le fichier' pour avant_fichier)")
        g.add_argument("--arreter-si-erreur", action="store_true",
                       help="s'arrete a la premiere erreur au lieu de traiter les autres elements")
        return p

    # ----- execution ----- #
    def lancer(self):
        for flux in (sys.stdout, sys.stderr):
            try:
                flux.reconfigure(errors="replace")
            except Exception:
                pass
        sys.exit(self.executer(sys.argv[1:]))

    def executer(self, argv=None, env=None):
        """Execute l'outil et renvoie le code retour (aucune exception ne sort). `env` : variables
        d'environnement (defaut : celles du processus)."""
        env = dict(os.environ) if env is None else dict(env)
        argv = list(sys.argv[1:] if argv is None else argv)
        try:
            args = self.parser().parse_args(argv)
            if args.code_si_rien not in (0, 1):
                raise ErreurParametres("--code-si-rien : 0 ou 1")
        except _Sortie as s:
            return s.code
        except ErreurParametres as e:
            print("ERREUR : parametres invalides : %s (voir --aide)" % e, file=sys.stderr)
            return CODE_PARAMETRES
        simulation = bool(args.simulation or env.get("COPIE_SIMULATION") == "1")
        try:
            j = journal.ouvrir(self.nom, args, env, simulation)
        except ValueError as e:
            print("ERREUR : parametres invalides : %s" % e, file=sys.stderr)
            return CODE_PARAMETRES
        ctx = Contexte(self, args, j, env, simulation)
        statut, code, motif = None, None, None
        try:
            self._principal(ctx, args)
        except ArretOutil:
            pass
        except ErreurParametres as e:
            ctx.nb_erreurs += 1
            ctx._ecrire("parametres_invalides", "ERROR", "Parametres invalides : %s" % e,
                        {"error_type": erreurs.BUSINESS_RULE_VIOLATION})
            ctx.ecrire_erreur("ERREUR : parametres invalides : %s" % e)
            ctx.type_erreur, code = erreurs.BUSINESS_RULE_VIOLATION, CODE_PARAMETRES
        except DependanceAbsente as e:
            ctx.nb_erreurs += 1
            ctx._ecrire("dependance_absente", "ERROR", "Dependance absente : %s" % e,
                        {"error_type": erreurs.EXTERNAL_SERVICE_ERROR})
            ctx.ecrire_erreur("DEPENDANCE ABSENTE : %s" % e)
            ctx.type_erreur, code = erreurs.EXTERNAL_SERVICE_ERROR, CODE_DEPENDANCE
        except ErreurOutil as e:               # erreur fatale, hors element
            ctx.nb_erreurs += 1
            ctx._ecrire("erreur_outil", "ERROR", str(e), {"error_type": e.type_erreur})
            ctx.ecrire_erreur("ERREUR : %s" % e)
            ctx.type_erreur = e.type_erreur
        except OSError as e:
            ctx.nb_erreurs += 1
            ctx._ecrire("erreur_outil", "ERROR", erreurs.decrire_os(e), {"error_type": erreurs.type_erreur_os(e)})
            ctx.ecrire_erreur("ERREUR : %s" % erreurs.decrire_os(e))
            ctx.type_erreur = erreurs.type_erreur_os(e)
        except Exception as e:
            ctx.nb_erreurs += 1
            ctx._ecrire("erreur_interne", "ERROR", "Erreur inattendue (%s) : %s" % (type(e).__name__, e),
                        {"error_type": erreurs.INTERNAL_ERROR, "exception": type(e).__name__,
                         "stacktrace": traceback.format_exc()})
            ctx.ecrire_erreur("ERREUR : erreur inattendue (%s) : %s (detail dans le journal)"
                              % (type(e).__name__, e))
            ctx.type_erreur = erreurs.INTERNAL_ERROR
        if ctx.nb_erreurs:
            statut = "ERREUR"
            code = code if code is not None else CODE_ERREUR
        elif ctx.nb_actions == 0 and ctx.code_impose is None:
            statut, code = "RIEN", args.code_si_rien
            motif = "rien a faire"
        else:
            statut = "WARNING" if ctx.nb_avertissements else "SUCCES"
            code = ctx.code_impose if ctx.code_impose is not None else CODE_OK
        champs = {"code_retour": code}
        if statut == "ERREUR":
            champs["error_type"] = ctx.type_erreur or erreurs.INTERNAL_ERROR
            champs["message"] = "Outil termine en erreur : %d erreur(s)" % ctx.nb_erreurs
        if motif:
            champs["motif"] = motif
        compteurs = dict(ctx.compteurs)
        if ctx.nb_erreurs:
            compteurs["erreurs"] = ctx.nb_erreurs
        if ctx.nb_avertissements:
            compteurs["avertissements"] = ctx.nb_avertissements
        j.fin(statut=statut, compteurs=compteurs, **champs)
        j.fermer()
        if j.pannes():
            print("ATTENTION : %d evenement(s) non ecrit(s) dans le dossier de journaux" % j.pannes(),
                  file=sys.stderr)
        detail = ", ".join("%s=%s" % (k, v) for k, v in compteurs.items())
        print("%s : %s%s%s" % ({"SUCCES": "OK", "WARNING": "OK AVEC AVERTISSEMENT", "RIEN": "RIEN A FAIRE",
                                "ERREUR": "ERREUR"}[statut], self.nom,
                               " (simulation)" if simulation else "", " : " + detail if detail else ""))
        return code
