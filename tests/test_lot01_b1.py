"""Lot 0.1 — B1 : délais explicites et erreurs reconnues par code d'état.

Aucun appel réseau : les SDK groq et anthropic sont remplacés par de faux
modules. Le repli automatique vers Haiku a été décidé le 26 nov. 2026 (lot
robustesse, tests/test_robustesse.py) ; pas de plafond de dépense : un test le
verrouille.
"""
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

import _chemins_lot01 as chemins  # noqa: F401

import boucle_voix


class ErreurHttp(Exception):
    def __init__(self, message="x", status_code=None):
        super().__init__(message)
        self.status_code = status_code


class APITimeoutError(Exception):
    """Même nom que la classe des SDK groq et anthropic."""


class ReadTimeout(Exception):
    """Même nom que la classe d'httpx."""


class ErreurAvecReponse(Exception):
    def __init__(self, code):
        super().__init__("sans attribut status_code direct")
        self.response = types.SimpleNamespace(status_code=code)


class ClassementDesErreurs(unittest.TestCase):
    def test_codes_d_etat(self):
        attendu = {429: "limite", 401: "cle", 403: "cle", 404: "modele",
                   408: "delai", 504: "delai", 500: "injoignable",
                   503: "injoignable", 400: "injoignable"}
        for code, categorie in attendu.items():
            self.assertEqual(
                boucle_voix.classer_erreur_cerveau(ErreurHttp(status_code=code)),
                categorie, code)

    def test_code_d_etat_lu_aussi_sur_la_reponse(self):
        self.assertEqual(boucle_voix.classer_erreur_cerveau(
            ErreurAvecReponse(429)), "limite")

    def test_delais(self):
        for erreur in (TimeoutError(), APITimeoutError(), ReadTimeout()):
            self.assertEqual(boucle_voix.classer_erreur_cerveau(erreur),
                             "delai", type(erreur).__name__)

    def test_le_texte_du_message_ne_compte_plus(self):
        """Ancien bug : « rate » dans « generate » passait pour une limite."""
        for texte in ("could not generate a response", "iterate failed",
                      "rate", "429 Too Many Requests"):
            self.assertEqual(boucle_voix.classer_erreur_cerveau(
                Exception(texte)), "injoignable", texte)

    def test_erreur_inconnue(self):
        self.assertEqual(boucle_voix.classer_erreur_cerveau(
            ValueError("autre")), "injoignable")


class CerveauEnPanne:
    def __init__(self, erreur):
        self.erreur = erreur

    def repondre(self, messages, outils):
        raise self.erreur


def repondre_a(erreur, langue):
    config = dict(boucle_voix.DEFAUTS, langue=langue)
    mesures = {}
    with mock.patch("sys.stderr"):
        reponse = boucle_voix.traiter_tour(
            "tell me a story", config, CerveauEnPanne(erreur), [], None,
            mesures=mesures)
    return reponse, mesures


class MessagesParLangue(unittest.TestCase):
    def test_chaque_categorie_a_son_message_dans_les_deux_langues(self):
        cas = {"limite": ErreurHttp(status_code=429),
               "cerveau_lent": APITimeoutError(),
               "cerveau_cle": ErreurHttp(status_code=401),
               "cerveau_modele": ErreurHttp(status_code=404),
               "cerveau_injoignable": ErreurHttp(status_code=500)}
        for langue in ("fr", "en"):
            for cle, erreur in cas.items():
                reponse, mesures = repondre_a(erreur, langue)
                self.assertEqual(reponse, boucle_voix.msg(langue, cle),
                                 (langue, cle))
                self.assertIn("erreur", mesures)

    def test_messages_distincts(self):
        for langue in ("fr", "en"):
            textes = {boucle_voix.msg(langue, c) for c in (
                "limite", "cerveau_lent", "cerveau_cle", "cerveau_modele",
                "cerveau_injoignable")}
            self.assertEqual(len(textes), 5)

    def test_un_message_contenant_rate_n_est_plus_une_limite(self):
        reponse, _ = repondre_a(Exception("could not generate"), "en")
        self.assertEqual(reponse, boucle_voix.msg("en", "cerveau_injoignable"))


class DelaisDesClients(unittest.TestCase):
    def faux_sdk(self, nom, classe):
        appels = []

        def constructeur(**kwargs):
            appels.append(kwargs)
            return mock.MagicMock()

        module = types.ModuleType(nom)
        setattr(module, classe, constructeur)
        return module, appels

    def test_groq_recoit_delai_et_reprise_explicites(self):
        module, appels = self.faux_sdk("groq", "Groq")
        with mock.patch.dict(sys.modules, {"groq": module}):
            boucle_voix.CerveauGroq("cle", "modele", 100, "low", delai=7.0)
        self.assertEqual(appels[0]["timeout"], 7.0)
        self.assertEqual(appels[0]["max_retries"],
                         boucle_voix.NOMBRE_REPRISES_CERVEAU)

    def test_anthropic_recoit_delai_et_reprise_explicites(self):
        module, appels = self.faux_sdk("anthropic", "Anthropic")
        with mock.patch.dict(sys.modules, {"anthropic": module}):
            boucle_voix.CerveauAnthropic("cle", "modele", 100, "low", delai=9.0)
        self.assertEqual(appels[0]["timeout"], 9.0)
        self.assertEqual(appels[0]["max_retries"],
                         boucle_voix.NOMBRE_REPRISES_CERVEAU)

    def test_creer_cerveau_transmet_le_delai_de_la_config(self):
        for fournisseur, classe, variable in (
                ("groq", "Groq", "GROQ_API_KEY"),
                ("anthropic", "Anthropic", "ANTHROPIC_API_KEY")):
            module, appels = self.faux_sdk(fournisseur, classe)
            config = dict(boucle_voix.DEFAUTS, fournisseur_llm=fournisseur,
                          delai_cerveau_s=12)
            with mock.patch.dict(sys.modules, {fournisseur: module}), \
                    mock.patch.dict("os.environ", {variable: "cle-test"}):
                boucle_voix.creer_cerveau(config)
            self.assertEqual(appels[0]["timeout"], 12.0, fournisseur)

    def test_delai_borne_et_defaut(self):
        self.assertEqual(boucle_voix.DEFAUTS["delai_cerveau_s"], 20.0)
        self.assertEqual(boucle_voix.delai_cerveau({}), 20.0)
        self.assertEqual(boucle_voix.delai_cerveau({"delai_cerveau_s": 0}), 1.0)
        self.assertEqual(boucle_voix.delai_cerveau({"delai_cerveau_s": 9999}), 120.0)
        self.assertEqual(boucle_voix.delai_cerveau({"delai_cerveau_s": "x"}), 20.0)

    def test_delai_lu_dans_la_configuration(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            (racine / "config").mkdir()
            (racine / "config" / "config.toml").write_text(
                "[boucle]\ndelai_cerveau_s = 8\n", encoding="utf-8")
            self.assertEqual(
                boucle_voix.charger_config(racine)["delai_cerveau_s"], 8)


class HorsPerimetre(unittest.TestCase):
    def test_pas_de_plafond_de_depense(self):
        """Décision du 26 nov. 2026 : repli automatique Groq -> Haiku ajouté
        (lot robustesse, classe Repli) ; le plafond de dépense reste hors
        périmètre (ni réglage ni classe). Si ce test échoue, une décision de
        Julien a été prise : mettre ce test à jour avec elle."""
        import re
        import tomllib
        motif = re.compile(r"plafond|budget|depense", re.I)
        exemple = tomllib.loads(
            (chemins.RACINE / "config" / "config.example.toml")
            .read_text(encoding="utf-8"))
        cles = list(boucle_voix.DEFAUTS)
        for valeurs in exemple.values():
            cles += list(valeurs)
        fautives = [cle for cle in cles if motif.search(cle)]
        self.assertEqual(fautives, [])
        classes = [nom for nom in dir(boucle_voix) if motif.search(nom)]
        self.assertEqual(classes, [])

    def test_le_repli_n_a_pas_de_reglage(self):
        """Le repli suit la présence d'ANTHROPIC_API_KEY : aucune clé de
        configuration ne l'active ou ne le coupe (pas de réglage à moitié lu)."""
        import re
        import tomllib
        motif = re.compile(r"repli|fallback", re.I)
        exemple = tomllib.loads(
            (chemins.RACINE / "config" / "config.example.toml")
            .read_text(encoding="utf-8"))
        cles = list(boucle_voix.DEFAUTS)
        for valeurs in exemple.values():
            cles += list(valeurs)
        self.assertEqual([c for c in cles if motif.search(c)], [])


if __name__ == "__main__":
    unittest.main()
