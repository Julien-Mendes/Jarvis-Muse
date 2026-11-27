"""Lot robustesse — verrous des journaux, repli Groq -> Haiku, configuration
unique pour l'application et le HUD, transcriptions vides, langue des erreurs
de vision, « a » / « an » hors des nombres, animation de l'orbe.

Aucun réseau, aucun micro, aucun son : cerveaux et widgets sont simulés.
"""
import contextlib
import io
import json
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

import _chemins_lot01  # noqa: F401  (rend scripts/ importable)

import _faux_ctk as faux
import boucle_voix
import hud
import yeux


class ErreurHttp(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class FauxCerveau:
    """Cerveau simulé : lève `erreur`, ou répond `texte` (après des appels
    d'outils éventuels)."""

    def __init__(self, texte="ok", erreur=None, appels=None):
        self.texte, self.erreur = texte, erreur
        self.appels = list(appels or [])
        self.nombre_appels = 0

    def repondre(self, messages, outils):
        self.nombre_appels += 1
        if self.appels:
            return {"texte": "", "appels_outils": [self.appels.pop(0)],
                    "utilisation": {}}
        if self.erreur is not None:
            raise self.erreur
        return {"texte": self.texte, "appels_outils": [], "utilisation": {}}

    def message_assistant(self, reponse):
        return {"role": "assistant", "content": reponse["texte"]}


def repli_avec(secours):
    config = dict(boucle_voix.DEFAUTS, langue="en", fournisseur_llm="groq")
    repli = boucle_voix.Repli(config)
    repli._essaye, repli._cerveau = True, secours
    return config, repli


def tour(config, principal, repli, mesures=None):
    with contextlib.redirect_stderr(io.StringIO()):
        return boucle_voix.traiter_tour("tell me a joke", config, principal,
                                        [], None, mesures=mesures,
                                        repli=repli)


class RepliAutomatique(unittest.TestCase):
    def test_429_delai_et_panne_basculent_sur_haiku(self):
        for erreur in (ErreurHttp(429), TimeoutError(), ErreurHttp(503)):
            secours = FauxCerveau("from haiku")
            config, repli = repli_avec(secours)
            mesures = boucle_voix._nouveau_bilan(config, "texte")
            self.assertEqual(tour(config, FauxCerveau(erreur=erreur), repli,
                                  mesures), "from haiku", erreur)
            self.assertTrue(mesures["repli"])
            self.assertEqual(mesures["fournisseur"], "anthropic")
            self.assertTrue(repli.principal_en_pause())

    def test_pendant_la_pause_groq_n_est_pas_rappele(self):
        secours = FauxCerveau("from haiku")
        config, repli = repli_avec(secours)
        tour(config, FauxCerveau(erreur=ErreurHttp(429)), repli)
        principal = FauxCerveau("from groq")
        self.assertEqual(tour(config, principal, repli), "from haiku")
        self.assertEqual(principal.nombre_appels, 0)
        repli.pause_jusqua = 0.0  # pause finie : retour à Groq.
        self.assertEqual(tour(config, principal, repli), "from groq")

    def test_cle_refusee_ou_modele_inconnu_ne_basculent_pas(self):
        for statut, cle in ((401, "cerveau_cle"), (404, "cerveau_modele")):
            secours = FauxCerveau("from haiku")
            config, repli = repli_avec(secours)
            self.assertEqual(
                tour(config, FauxCerveau(erreur=ErreurHttp(statut)), repli),
                boucle_voix.msg("en", cle))
            self.assertEqual(secours.nombre_appels, 0)

    def test_pas_de_repli_apres_un_outil_execute(self):
        appel = {"nom": "regler_minuteur", "id": "t1",
                 "arguments": {"minutes": 5}}
        principal = FauxCerveau(erreur=ErreurHttp(429), appels=[appel])
        secours = FauxCerveau("from haiku")
        config, repli = repli_avec(secours)
        with mock.patch.object(boucle_voix, "executer_minuteur",
                               return_value="timer set") as minuteur:
            reponse = tour(config, principal, repli)
        minuteur.assert_called_once()  # jamais deux minuteurs.
        self.assertEqual(reponse, boucle_voix.msg("en", "limite"))
        self.assertEqual(secours.nombre_appels, 0)

    def test_sans_cle_anthropic_message_b1_inchange(self):
        config = dict(boucle_voix.DEFAUTS, langue="en", fournisseur_llm="groq")
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            repli = boucle_voix.Repli(config)
            reponse = tour(config, FauxCerveau(erreur=ErreurHttp(429)), repli)
        self.assertEqual(reponse, boucle_voix.msg("en", "limite"))

    def test_pas_de_repli_si_le_principal_est_deja_anthropic(self):
        config = dict(boucle_voix.DEFAUTS, fournisseur_llm="anthropic")
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            self.assertIsNone(boucle_voix.Repli(config).obtenir())

    def test_le_journal_des_tours_note_le_repli(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(boucle_voix, "DOSSIER_TOURS", Path(tmp)):
            boucle_voix.journaliser_tour({"repli": True})
            ligne = json.loads(next(Path(tmp).glob("tours-*.jsonl"))
                               .read_text(encoding="utf-8"))
        self.assertIs(ligne["repli"], True)


class VerrouDesJournaux(unittest.TestCase):
    def test_les_deux_journaux_ecrivent_sous_verrou(self):
        cibles = []

        @contextlib.contextmanager
        def faux_verrou(chemin, delai=5.0, pas=0.05):
            cibles.append((Path(chemin), delai))
            yield True

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(boucle_voix, "verrou_fichier", faux_verrou), \
                mock.patch.object(boucle_voix, "DOSSIER_CONVERSATIONS",
                                  Path(tmp) / "conv"), \
                mock.patch.object(boucle_voix, "DOSSIER_TOURS",
                                  Path(tmp) / "logs"):
            boucle_voix.journaliser_echange("salut", "bonjour")
            boucle_voix.journaliser_tour({})
        self.assertEqual([c.parent.name for c, _ in cibles], ["conv", "logs"])
        self.assertTrue(all(c.suffix == ".jsonl" for c, _ in cibles))
        self.assertTrue(all(d <= 1.0 for _, d in cibles))  # jamais figé.

    def test_ecritures_concurrentes_lignes_intactes(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(boucle_voix, "DOSSIER_CONVERSATIONS",
                                  Path(tmp)):
            def ecrire(n):
                for i in range(25):
                    boucle_voix.journaliser_echange(f"u{n}-{i}" * 40,
                                                    f"j{n}-{i}" * 40)

            fils = [threading.Thread(target=ecrire, args=(n,)) for n in range(4)]
            for fil in fils:
                fil.start()
            for fil in fils:
                fil.join()
            lignes = next(Path(tmp).glob("*.jsonl")).read_text(
                encoding="utf-8").splitlines()
        self.assertEqual(len(lignes), 4 * 25 * 2)
        for ligne in lignes:
            json.loads(ligne)


class TranscriptionsVides(unittest.TestCase):
    def test_sans_lettre_ni_chiffre_rejetee(self):
        for texte in ("", "   ", "...", "♪ ♪", " - ", "?!", "…"):
            self.assertFalse(boucle_voix.transcription_utile(texte), texte)
        for texte in ("oui", "5", "Écran", "ok."):
            self.assertTrue(boucle_voix.transcription_utile(texte), texte)


class LangueDesErreursDeVision(unittest.TestCase):
    def test_messages_dans_la_langue_demandee(self):
        for statut, cle in ((404, "modele"), (429, "limite"), (401, "cle")):
            for langue in ("fr", "en"):
                self.assertEqual(
                    yeux.decrire_erreur_vision(ErreurHttp(statut), langue),
                    yeux.ERREURS_VISION[langue][cle])
        self.assertTrue(yeux.decrire_erreur_vision(
            ValueError("boom"), "en").startswith("Vision model error"))

    def test_generate_n_est_plus_une_limite(self):
        self.assertNotEqual(
            yeux.decrire_erreur_vision(Exception("could not generate"), "en"),
            yeux.ERREURS_VISION["en"]["limite"])

    def test_invite_par_defaut_suit_la_langue_configuree(self):
        self.assertEqual(yeux.PROMPT_DEFAUT,
                         yeux.PROMPTS[yeux.config_jarvis.langue()])


class ArticlesAnglais(unittest.TestCase):
    def test_a_et_an_ne_sont_plus_des_nombres(self):
        self.assertNotIn("a", boucle_voix.NOMBRES_EN)
        self.assertNotIn("an", boucle_voix.NOMBRES_EN)
        for phrase in ("set a timer for a minute", "remind me in an hour",
                       "give me a minute timer"):
            self.assertIsNone(boucle_voix.detecter_minuteur(phrase), phrase)

    def test_les_vrais_nombres_restent_reconnus(self):
        attendu = {"wait a minute, set a timer for 10 minutes": 10.0,
                   "set a timer for one hour": 60.0,
                   "set a timer for half an hour": 30.0,
                   "set a timer for 5minutes": 5.0,
                   "a 20 minute timer": 20.0}
        for phrase, minutes in attendu.items():
            self.assertEqual(boucle_voix.detecter_minuteur(phrase)["minutes"],
                             minutes, phrase)


def ecrire(dossier: Path, nom: str, contenu: str) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / nom).write_text(contenu, encoding="utf-8")


class ConfigurationUnique(unittest.TestCase):
    def test_hud_lit_les_trois_couches(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config"
            ecrire(config, "config.example.toml", "[hud]\ntaille = 150\n")
            ecrire(config, "config.toml", '[hud]\nposition = "haut-gauche"\n')
            ecrire(config, "config.local.toml", "[hud]\ntaille = 200\n")
            resultat = hud.charger_config_hud(Path(tmp))
        self.assertEqual(resultat["taille"], 200)
        self.assertEqual(resultat["position"], "haut-gauche")

    def test_application_lit_config_local(self):
        app, _ = faux.charger_app(nom="app_robustesse")
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config"
            ecrire(config, "config.example.toml", "[app]\nlargeur = 900\n")
            ecrire(config, "config.local.toml", "[app]\nlargeur = 1200\n")
            with contextlib.redirect_stderr(io.StringIO()):
                resultat = app.charger_config_app(Path(tmp))
        self.assertEqual(resultat["largeur"], 1200)
        self.assertEqual(resultat["theme"], "or_et_nuit")

    def test_application_couche_illisible_theme_de_repli(self):
        app, _ = faux.charger_app(nom="app_robustesse2")
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config"
            ecrire(config, "config.example.toml", "[app]\nlargeur = 1000\n")
            ecrire(config, "config.local.toml", "[app\ncassé")
            with contextlib.redirect_stderr(io.StringIO()):
                resultat = app.charger_config_app(Path(tmp))
        self.assertEqual(resultat["theme"], app.THEME_REPLI)
        self.assertEqual(resultat["largeur"], 1000)  # couche lisible gardée.


class AnimationDeLOrbe(unittest.TestCase):
    def _animer(self, existe):
        app, _ = faux.charger_app(nom="app_orbe")
        planifies = []
        fenetre = types.SimpleNamespace(
            winfo_exists=lambda: existe,
            after=lambda delai, rappel: planifies.append(delai))
        soi = types.SimpleNamespace(etat_affiche="reflexion", fenetre=fenetre,
                                    _dessiner_orbe=lambda echelle: None,
                                    _animer_orbe=lambda: None)
        app.Application._animer_orbe(soi)
        return planifies

    def test_replanifie_tant_que_la_fenetre_existe(self):
        self.assertEqual(len(self._animer(True)), 1)

    def test_s_arrete_quand_la_fenetre_est_detruite(self):
        self.assertEqual(self._animer(False), [])


if __name__ == "__main__":
    unittest.main()
