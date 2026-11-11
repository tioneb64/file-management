"""Journal au format de la plateforme d'observabilite : tout ce que le moteur ecrit est conforme,
le catalogue couvre tous les evenements, la trace du lancement est partagee avec les processus fils."""
import glob
import json
import os
import re
import unittest

import journal_si
from file_management import catalogue_journal
from file_management.catalogue_journal import MESSAGES, decrire
from tests.test_orchestrateur import SEPT_HEURES, CasProcessus

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Liste des erreurs de la plateforme (docs de la plateforme, format-log.md, "Liste des erreurs").
TYPES_ERREUR = {
    "CONNECTION_REFUSED", "CONNECTION_TIMEOUT", "CONNECTION_LOST", "DNS_ERROR", "TLS_ERROR",
    "AUTHENTICATION_FAILED", "PERMISSION_DENIED", "DB_CONNECTION_ERROR", "DB_QUERY_ERROR",
    "DB_CONSTRAINT_VIOLATION", "DB_DEADLOCK", "MISSING_MANDATORY_FIELD", "INVALID_VALUE",
    "DATA_FORMAT_ERROR", "BUSINESS_RULE_VIOLATION", "ENTITY_NOT_FOUND", "DUPLICATE_ENTITY",
    "MESSAGE_DELIVERY_FAILED", "MESSAGE_PROCESSING_FAILED", "RESOURCE_EXHAUSTED", "FILE_NOT_FOUND",
    "FILE_IO_ERROR", "EXTERNAL_SERVICE_ERROR", "TIMEOUT", "CONFIGURATION_ERROR", "INTERNAL_ERROR",
    "UNKNOWN_ERROR"}
NIVEAUX = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
ENVIRONNEMENTS = {"dev", "build", "test", "pprod", "prod", "run", "int"}
RE_HORODATAGE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
RE_SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$")
RE_KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def anomalies(l):
    """Ecarts d'une ligne de journal au format de la plateforme (liste vide = conforme)."""
    a = []
    if not set(l) <= {"timestamp", "duration_ms", "level", "message", "trace", "service", "context", "error"}:
        a.append("champs inconnus a la racine : %s" % sorted(l))
    if not RE_HORODATAGE.match(str(l.get("timestamp"))):
        a.append("timestamp")
    if l.get("level") not in NIVEAUX:
        a.append("level %r" % l.get("level"))
    if not isinstance(l.get("message"), str) or not l["message"].strip():
        a.append("message")
    if "duration_ms" in l and not (isinstance(l["duration_ms"], int) and l["duration_ms"] >= 0):
        a.append("duration_ms")
    t = l.get("trace") or {}
    if not re.match(r"^[0-9a-f]{32}$", str(t.get("trace_id"))):
        a.append("trace_id")
    if not re.match(r"^[0-9a-f]{16}$", str(t.get("span_id"))):
        a.append("span_id")
    if not t.get("correlation_id"):
        a.append("correlation_id")
    s = l.get("service") or {}
    if not s.get("name"):
        a.append("service.name")
    if not RE_SEMVER.match(str(s.get("version"))):
        a.append("service.version %r" % s.get("version"))
    if s.get("environment") not in ENVIRONNEMENTS:
        a.append("service.environment %r" % s.get("environment"))
    if not s.get("instance") or s["instance"] != s["instance"].lower():
        a.append("service.instance")
    c = l.get("context") or {}
    if not RE_KEBAB.match(str(c.get("object"))):
        a.append("context.object %r" % c.get("object"))
    if not isinstance(c.get("object_id"), str) or not c["object_id"]:
        a.append("context.object_id")
    if l.get("level") in ("ERROR", "CRITICAL"):
        e = l.get("error") or {}
        if e.get("type") not in TYPES_ERREUR:
            a.append("error.type %r" % e.get("type"))
        if not e.get("message"):
            a.append("error.message")
    elif "error" in l:
        a.append("error present hors ERROR/CRITICAL")
    return a


def lignes_brutes(dossier):
    resultat = []
    for chemin in sorted(glob.glob(os.path.join(dossier, "*.jsonl"))):
        with open(chemin, encoding="utf-8") as f:
            resultat.extend(json.loads(l) for l in f if l.strip())
    return resultat


class TestValidateur(unittest.TestCase):
    """Le validateur de ce fichier doit lui-meme reconnaitre une ligne valide et refuser les autres."""

    def ligne(self, **modif):
        l = {"timestamp": "2026-11-03T06:30:12.481Z", "level": "INFO", "message": "ok",
             "trace": {"trace_id": "a" * 32, "span_id": "b" * 16, "correlation_id": "c"},
             "service": {"name": "file_management", "version": "1.0.0", "environment": "prod", "instance": "srv"},
             "context": {"object": "fichier", "object_id": "a.csv", "event": "x"}}
        l.update(modif)
        return l

    def test_ligne_valide(self):
        self.assertEqual(anomalies(self.ligne()), [])

    def test_lignes_refusees(self):
        self.assertTrue(anomalies(self.ligne(level="ERREUR")))
        self.assertTrue(anomalies(self.ligne(level="ERROR")))                      # error absent
        self.assertTrue(anomalies(self.ligne(error={"type": "X", "message": "m"})))
        self.assertTrue(anomalies(self.ligne(service={"name": "n", "version": "2.0.0.dev0",
                                                      "environment": "prod", "instance": "i"})))
        self.assertTrue(anomalies(self.ligne(service={"name": "n", "version": "1.0.0",
                                                      "environment": "production", "instance": "i"})))


class TestExemples(unittest.TestCase):
    def test_les_exemples_de_journal_sont_conformes(self):
        lignes = lignes_brutes(os.path.join(RACINE, "exemples", "journal"))
        self.assertGreaterEqual(len(lignes), 8)
        for l in lignes:
            self.assertEqual(anomalies(l), [], l)
        self.assertTrue({"INFO", "WARNING", "ERROR"} <= {l["level"] for l in lignes})


class TestCatalogue(unittest.TestCase):
    def test_messages_avec_champs(self):
        self.assertEqual(decrire("fichier_livre", "INFO", {"fichier": "D:\\a\\b.csv"})["message"],
                         "Fichier livre : b.csv")
        self.assertEqual(decrire("regle_terminee", "INFO", {"statut": "SUCCES"})["message"],
                         "Regle terminee : SUCCES")
        self.assertEqual(decrire("regle_terminee", "INFO", {})["message"], "Regle terminee")     # champ absent
        self.assertEqual(decrire("evenement_inconnu", "INFO", {})["message"], "evenement inconnu")

    def test_pas_d_erreur_hors_error(self):
        for niveau in ("DEBUG", "INFO", "WARNING"):
            self.assertNotIn("error_type", decrire("fichier_erreur", niveau, {"situation": "copie_echec"}))

    def test_types_d_erreur_et_niveaux_critiques(self):
        cas = (("base_indisponible", {}, "CRITICAL", "DB_CONNECTION_ERROR"),
               ("livraison_incertaine", {"fichier": "a"}, "CRITICAL", "FILE_IO_ERROR"),
               ("erreur_interne", {"message": "ValueError: x"}, "CRITICAL", "INTERNAL_ERROR"),
               ("fichier_erreur", {"situation": "espace_insuffisant_cible"}, "CRITICAL", "RESOURCE_EXHAUSTED"),
               ("regle_anomalie", {"situation": "espace_insuffisant_cible"}, "CRITICAL", "RESOURCE_EXHAUSTED"),
               ("fichier_erreur", {"situation": "copie_echec"}, None, "FILE_IO_ERROR"),
               ("fichier_erreur", {"situation": "fichier_existe_cible"}, None, "DUPLICATE_ENTITY"),
               ("fichier_erreur", {"situation": "fichier_disparu"}, None, "FILE_NOT_FOUND"),
               ("regle_anomalie", {"situation": "programme_avant_lot"}, None, "EXTERNAL_SERVICE_ERROR"),
               ("duree_depassee", {}, None, "TIMEOUT"),
               ("arret_anormal", {}, None, "INTERNAL_ERROR"),
               ("regle_terminee", {"situation": "source_inaccessible"}, None, "FILE_IO_ERROR"),
               ("regle_terminee", {}, None, "UNKNOWN_ERROR"),
               ("regle_non_lancee", {}, None, "BUSINESS_RULE_VIOLATION"))
        for nom, champs, niveau, type_ in cas:
            d = decrire(nom, "ERROR", champs)
            self.assertEqual((d.get("niveau"), d["error_type"]), (niveau, type_), (nom, champs))

    def test_exception_de_l_erreur_interne(self):
        self.assertEqual(decrire("erreur_interne", "ERROR", {"message": "KeyError: 'x'"})["exception"], "KeyError")
        self.assertNotIn("exception", decrire("erreur_interne", "ERROR", {"message": "plantage"}))

    def test_tous_les_types_sont_dans_la_liste_de_la_plateforme(self):
        for table in (catalogue_journal.TYPES_SITUATION, catalogue_journal.TYPES_EVENEMENT):
            self.assertTrue(set(table.values()) <= TYPES_ERREUR, set(table.values()) - TYPES_ERREUR)

    def test_toutes_les_situations_ont_un_type(self):
        from file_management.parametrage import SITUATIONS
        manquantes = [s for s in SITUATIONS if s not in catalogue_journal.TYPES_SITUATION]
        self.assertEqual(manquantes, [])

    def test_tous_les_evenements_emis_ont_un_message(self):
        """Un evenement ajoute au moteur sans message dans le catalogue serait journalise avec son seul nom."""
        emis = set()
        for chemin in glob.glob(os.path.join(RACINE, "file_management", "*.py")):
            with open(chemin, encoding="utf-8") as f:
                emis.update(re.findall(r'(?:\.evenement|\._log)\(\s*"([a-z_0-9]+)"', f.read()))
        self.assertGreater(len(emis), 30)
        self.assertEqual(sorted(e for e in emis if e not in MESSAGES), [])


class TestLignesDuMoteur(CasProcessus):
    """Un lancement reel (processus fils compris) n'ecrit que des lignes conformes, dans une seule trace."""

    def preparer_deux_regles(self):
        self.source_reelle()
        self.brute(id="a", cible=self.chemin("da"), planification=SEPT_HEURES)
        self.brute(id="mauvaise", source=self.chemin("absente"), cible=self.chemin("dm"),
                   planification=SEPT_HEURES, situations={"source_inaccessible": {"tentatives": 1}})

    def test_toutes_les_lignes_sont_conformes(self):
        self.preparer_deux_regles()
        self.lancer_reel("a", "mauvaise")
        self.journal.fin(statut="ERREUR")
        lignes = lignes_brutes(self.chemin("logs"))
        self.assertGreater(len(lignes), 10)
        for l in lignes:
            self.assertEqual(anomalies(l), [], l)
        niveaux = {l["level"] for l in lignes}
        self.assertTrue({"INFO", "ERROR"} <= niveaux, niveaux)
        erreurs = [l for l in lignes if l["level"] == "ERROR"]
        self.assertIn("FILE_IO_ERROR", {l["error"]["type"] for l in erreurs})

    def test_les_fils_journalisent_dans_la_trace_du_lancement(self):
        self.preparer_deux_regles()
        self.lancer_reel("a", "mauvaise")
        lignes = lignes_brutes(self.chemin("logs"))
        self.assertEqual({l["trace"]["trace_id"] for l in lignes}, {self.journal.trace_id})
        demarrees = [l for l in lignes if l["context"].get("event") == "regle_demarree"]
        terminees = [l for l in lignes if l["context"].get("event") == "regle_terminee"]
        self.assertEqual(len(demarrees), 2)
        for d in demarrees:                          # fils (regle_demarree) et orchestrateur (regle_terminee)
            fin = next(t for t in terminees if t["context"]["regle"] == d["context"]["regle"])
            self.assertEqual(d["trace"]["span_id"], fin["trace"]["span_id"])
            self.assertEqual(d["service"]["name"], "file_management." + d["context"]["regle"])
        self.assertEqual(len({d["trace"]["span_id"] for d in demarrees}), 2)

    def test_objets_des_evenements_d_une_regle(self):
        self.preparer_deux_regles()
        self.lancer_reel("a", "mauvaise")
        lignes = lignes_brutes(self.chemin("logs"))
        livre = next(l for l in lignes if l["context"].get("event") == "fichier_livre")
        self.assertEqual((livre["context"]["object"], livre["context"]["object_id"]), ("fichier", "a.csv"))
        self.assertEqual(livre["message"], "Fichier livre : a.csv")
        fin = next(l for l in lignes if l["context"].get("event") == "regle_terminee" and l["context"]["regle"] == "a")
        self.assertEqual((fin["context"]["object"], fin["context"]["object_id"]), ("regle", "a"))
        self.assertIn("duration_ms", fin)


if __name__ == "__main__":
    unittest.main()
