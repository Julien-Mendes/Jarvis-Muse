"""Lot L1 — langue détectée à chaque tour (fr / en).

Détection (Whisper puis texte, repli config si incertain), langue du prompt
cerveau et des outils, voix selon la langue (une seule en mémoire), annonces
de minuteur (config sauf tour en cours dans l'autre langue), interface par
tour. Aucun réseau, aucun micro, aucun modèle Piper ni Whisper : tout est
simulé.
"""
import json
import shutil
import tempfile
import threading
import types
import unittest
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import _chemins_lot01  # noqa: F401 — rend scripts/ importable.

import boucle_voix
import config_jarvis
import langue_tour
import lire_voix
import minuteur

warnings.simplefilter("ignore", ResourceWarning)

CONFIG_EN = dict(boucle_voix.DEFAUTS, langue="en", fournisseur_llm="groq")
CONFIG_FR = dict(CONFIG_EN, langue="fr")


class FauxCerveau:
    """Cerveau simulé : garde le prompt et les outils reçus."""

    def __init__(self, texte="ok"):
        self.texte = texte
        self.messages_recus = []
        self.outils_recus = []

    def repondre(self, messages, outils):
        self.messages_recus.append(list(messages))
        self.outils_recus.append(outils)
        return {"texte": self.texte, "appels_outils": [], "utilisation": {}}

    def message_assistant(self, reponse):
        return {"role": "assistant", "content": reponse["texte"]}


# ---------------------------------------------------------------------------
# 1. Détection FR / EN à chaque tour
# ---------------------------------------------------------------------------

class DetectionTexte(unittest.TestCase):
    FRANCAIS = (
        "Mets un minuteur de cinq minutes",
        "Qu'est-ce que je t'ai dit sur le budget ?",
        "Regarde mon écran",
        "Ouvre YouTube",
        "Note que le code du portail est 4521",
        "oui",
        "Bonjour Jarvis",
        "Recherche les meilleurs vélos électriques",
    )
    ANGLAIS = (
        "Set a timer for five minutes",
        "What did I tell you about the budget?",
        "Look at my screen",
        "Open YouTube",
        "Note that the gate code is 4521",
        "yes",
        "Hello Jarvis",
        "Research the best electric bikes",
    )

    def test_phrases_francaises(self):
        for phrase in self.FRANCAIS:
            with self.subTest(phrase=phrase):
                self.assertEqual(langue_tour.detecter_texte(phrase), "fr")

    def test_phrases_anglaises(self):
        for phrase in self.ANGLAIS:
            with self.subTest(phrase=phrase):
                self.assertEqual(langue_tour.detecter_texte(phrase), "en")

    def test_chaque_tour_a_sa_langue(self):
        # Alternance d'un tour à l'autre : rien ne « colle » au tour d'avant.
        tours = ["Set a timer for two minutes", "Merci, et quelle heure est-il ?",
                 "Thanks, what time is it?", "Ferme le navigateur"]
        self.assertEqual(
            [langue_tour.langue_du_tour(t, "en") for t in tours],
            ["en", "fr", "en", "fr"])

    def test_incertain_donne_none(self):
        for phrase in ("", "OK", "Google", "4521", "Jarvis", "a",
                       "merci, thanks", "oui yes"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(langue_tour.detecter_texte(phrase))

    def test_incertain_repli_sur_la_langue_de_la_config(self):
        for phrase in ("OK", "Google", "4521", ""):
            with self.subTest(phrase=phrase):
                self.assertEqual(langue_tour.langue_du_tour(phrase, "en"), "en")
                self.assertEqual(langue_tour.langue_du_tour(phrase, "fr"), "fr")

    def test_config_invalide_repli_anglais(self):
        self.assertEqual(langue_tour.langue_du_tour("OK", "de"), "en")

    def test_le_a_n_est_pas_un_indice_anglais(self):
        # Piège connu (mots-nombres) : « a » est aussi français (« il a »).
        self.assertEqual(langue_tour.scores_texte("a"), (0, 0))
        self.assertEqual(langue_tour.detecter_texte("il a fini"), "fr")

    def test_mots_ambigus_exclus_des_deux_listes(self):
        self.assertFalse(langue_tour.MOTS_FR & langue_tour.MOTS_EN)
        for ambigu in ("a", "on", "me", "minutes", "note", "ok"):
            self.assertNotIn(ambigu, langue_tour.MOTS_FR)
            self.assertNotIn(ambigu, langue_tour.MOTS_EN)


class DetectionWhisper(unittest.TestCase):
    def test_noms_whisper_normalises(self):
        self.assertEqual(langue_tour.normaliser_whisper("French"), "fr")
        self.assertEqual(langue_tour.normaliser_whisper("english"), "en")
        self.assertEqual(langue_tour.normaliser_whisper("fr"), "fr")
        self.assertIsNone(langue_tour.normaliser_whisper("dutch"))
        self.assertIsNone(langue_tour.normaliser_whisper(None))

    def test_la_langue_de_whisper_prime(self):
        # Mot isolé ambigu, mais Whisper a entendu du français.
        self.assertEqual(
            langue_tour.langue_du_tour("Google", "en", "French"), "fr")

    def test_whisper_peu_sur_repli_sur_le_texte_puis_la_config(self):
        self.assertEqual(langue_tour.langue_du_tour(
            "Set a timer", "fr", "fr", probabilite=0.3), "en")
        self.assertEqual(langue_tour.langue_du_tour(
            "OK", "fr", "en", probabilite=0.3), "fr")

    def test_whisper_autre_langue_ignore(self):
        self.assertEqual(langue_tour.langue_du_tour("OK", "fr", "Dutch"), "fr")

    def test_langue_auto_desactivee(self):
        self.assertEqual(langue_tour.langue_du_tour(
            "Mets un minuteur", "en", "French", auto=False), "en")

    def test_cle_de_config_langue_auto(self):
        self.assertTrue(config_jarvis.langue_auto({}))
        self.assertFalse(config_jarvis.langue_auto(
            {"general": {"langue_auto": False}}))
        self.assertFalse(config_jarvis.langue_auto(
            {"general": {"langue_auto": "false"}}))
        self.assertIn("langue_auto", boucle_voix.DEFAUTS)


class ConfigDuTour(unittest.TestCase):
    def test_copie_sans_modifier_la_config(self):
        config = dict(CONFIG_EN)
        tour = boucle_voix.config_du_tour(config, "Mets un minuteur")
        self.assertEqual(tour["langue"], "fr")
        self.assertEqual(tour["langue_config"], "en")
        self.assertEqual(config["langue"], "en")

    def test_attributs_du_transcripteur_utilises(self):
        faux = types.SimpleNamespace(derniere_langue="en",
                                     derniere_probabilite=0.95)
        tour = boucle_voix.config_du_tour(CONFIG_FR, "Google", faux)
        self.assertEqual(tour["langue"], "en")

    def test_tour_tape_sans_transcripteur(self):
        tour = boucle_voix.config_du_tour(CONFIG_FR, "OK")
        self.assertEqual(tour["langue"], "fr")  # incertain -> config.

    def test_langue_auto_false_garde_la_config(self):
        config = dict(CONFIG_EN, langue_auto=False)
        self.assertEqual(
            boucle_voix.config_du_tour(config, "Mets un minuteur")["langue"],
            "en")


class TranscripteursSansForcage(unittest.TestCase):
    def groq(self, reponses, auto=True):
        transcripteur = object.__new__(boucle_voix.TranscripteurGroq)
        appels = []

        def creer(**options):
            appels.append(options)
            return reponses.pop(0)

        transcripteur.client = types.SimpleNamespace(audio=types.SimpleNamespace(
            transcriptions=types.SimpleNamespace(create=creer)))
        transcripteur.modele = "whisper-large-v3-turbo"
        transcripteur.langue = "en"
        transcripteur.auto = auto
        return transcripteur, appels

    def test_groq_detecte_sans_forcer_la_langue(self):
        t, appels = self.groq([types.SimpleNamespace(
            text=" Mets un minuteur. ", language="French")])
        self.assertEqual(t.transcrire(b"wav"), "Mets un minuteur.")
        self.assertEqual(t.derniere_langue, "fr")
        self.assertNotIn("language", appels[0])
        self.assertEqual(appels[0]["response_format"], "verbose_json")

    def test_groq_autre_langue_retranscrit_dans_la_config(self):
        t, appels = self.groq([
            types.SimpleNamespace(text="Zet een timer", language="Dutch"),
            "Set a timer"])
        self.assertEqual(t.transcrire(b"wav"), "Set a timer")
        self.assertIsNone(t.derniere_langue)
        self.assertEqual(appels[1]["language"], "en")

    def test_groq_langue_auto_false_force_comme_avant(self):
        t, appels = self.groq(["Set a timer"], auto=False)
        self.assertEqual(t.transcrire(b"wav"), "Set a timer")
        self.assertEqual(appels[0]["language"], "en")

    def test_local_donne_langue_et_probabilite(self):
        t = object.__new__(boucle_voix.TranscripteurLocal)
        t.langue, t.auto = "en", True
        options = []

        def transcribe(chemin, language=None):
            options.append(language)
            return ([types.SimpleNamespace(text="Bonjour")],
                    types.SimpleNamespace(language="fr",
                                          language_probability=0.91))

        t.modele = types.SimpleNamespace(transcribe=transcribe)
        self.assertEqual(t.transcrire(b"RIFF"), "Bonjour")
        self.assertEqual((t.derniere_langue, t.derniere_probabilite),
                         ("fr", 0.91))
        self.assertEqual(options, [None])


# ---------------------------------------------------------------------------
# 2. Cerveau : prompt système et outils dans la langue du tour
# ---------------------------------------------------------------------------

class LangueDuCerveau(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="jarvis-l1-"))
        self.base = {"fichier_connaissances":
                     str(self.dossier / "connaissances.json"),
                     "fichier_recherches": str(self.dossier / "recherches.json")}

    def tearDown(self):
        shutil.rmtree(self.dossier, ignore_errors=True)

    def tour(self, phrase, config):
        config = dict(config, **self.base)
        cerveau = FauxCerveau()
        boucle_voix.traiter_tour(phrase, boucle_voix.config_du_tour(
            config, phrase), cerveau, [], None, {})
        return cerveau

    def test_question_francaise_config_anglaise(self):
        cerveau = self.tour("Quelle est la capitale de l'Australie ?",
                            CONFIG_EN)
        systeme = cerveau.messages_recus[0][0]
        self.assertEqual(systeme["role"], "system")
        self.assertEqual(systeme["content"].split("\n")[0],
                         boucle_voix.prompt_systeme("fr").split("\n")[0])
        self.assertEqual(cerveau.outils_recus[0],
                         boucle_voix.outils_pour("groq", "fr"))

    def test_question_anglaise_config_francaise(self):
        cerveau = self.tour("What is the capital of Australia?", CONFIG_FR)
        self.assertEqual(cerveau.messages_recus[0][0]["content"].split("\n")[0],
                         boucle_voix.prompt_systeme("en").split("\n")[0])
        self.assertEqual(cerveau.outils_recus[0],
                         boucle_voix.outils_pour("groq", "en"))

    def test_question_incertaine_prompt_de_la_config(self):
        cerveau = self.tour("Google", CONFIG_FR)
        self.assertEqual(cerveau.messages_recus[0][0]["content"].split("\n")[0],
                         boucle_voix.prompt_systeme("fr").split("\n")[0])

    def test_les_prompts_fr_et_en_different(self):
        self.assertNotEqual(boucle_voix.prompt_systeme("fr").split("\n")[0],
                            boucle_voix.prompt_systeme("en").split("\n")[0])

    def test_declencheurs_kb_dans_les_deux_langues(self):
        # « note que… » en config anglaise : noté, réponse en français.
        config = dict(CONFIG_EN, **self.base)
        phrase = "Note que le code du portail est 4521"
        reponse = boucle_voix.traiter_tour(
            phrase, boucle_voix.config_du_tour(config, phrase), None, [],
            None, {})
        self.assertEqual(reponse, boucle_voix.connaissances_mod.texte(
            "fr", "note_ok"))
        config = dict(CONFIG_FR, **self.base)
        phrase = "Note that the gate code is 4521"
        reponse = boucle_voix.traiter_tour(
            phrase, boucle_voix.config_du_tour(config, phrase), None, [],
            None, {})
        self.assertEqual(reponse, boucle_voix.connaissances_mod.texte(
            "en", "note_ok"))

    def test_minuteur_du_tour_confirme_dans_la_langue_du_tour(self):
        config = dict(CONFIG_EN, **self.base)
        phrase = "Mets un minuteur de 5 minutes"
        with mock.patch.object(boucle_voix, "executer_minuteur",
                               return_value="ok") as executer:
            boucle_voix.traiter_tour(phrase, boucle_voix.config_du_tour(
                config, phrase), None, [], None, {})
        self.assertEqual(executer.call_args.args[-1], "fr")


# ---------------------------------------------------------------------------
# 3. Voix selon la langue du tour (une seule en mémoire)
# ---------------------------------------------------------------------------

class VoixSelonLaLangue(unittest.TestCase):
    def voix(self, max_voix=None):
        voix = lire_voix.VoixResidente(dossier_modeles=Path("inexistant"),
                                       donnees={}, max_voix=max_voix)
        chargees = []

        def charger_modele(chemin_modele, chemin_config):
            chargees.append(Path(chemin_modele).name)
            return types.SimpleNamespace(nom=Path(chemin_modele).name)

        voix._charger_modele = charger_modele
        trouver = lambda dossier, nom: (Path(nom + ".onnx"),
                                        Path(nom + ".onnx.json"))
        return voix, chargees, trouver

    def test_upmc_en_francais_alan_en_anglais(self):
        voix, chargees, trouver = self.voix()
        with mock.patch.object(lire_voix, "trouver_modele", trouver):
            self.assertIn("upmc", voix.charger("fr").nom)
            self.assertIn("alan", voix.charger("en").nom)

    def test_une_seule_voix_en_memoire_cache_de_la_derniere(self):
        voix, chargees, trouver = self.voix()
        with mock.patch.object(lire_voix, "trouver_modele", trouver):
            voix.charger("en")
            voix.charger("en")  # cache : pas de rechargement.
            self.assertEqual(len(chargees), 1)
            voix.charger("fr")
            self.assertEqual(voix.voix_chargees(),
                             [lire_voix.nom_voix_configure({}, "fr")])
            voix.charger("en")
            self.assertEqual(len(chargees), 3)
            self.assertEqual(len(voix.voix_chargees()), 1)

    def test_deux_voix_si_le_budget_le_permet(self):
        voix, chargees, trouver = self.voix(max_voix=2)
        with mock.patch.object(lire_voix, "trouver_modele", trouver):
            voix.charger("en")
            voix.charger("fr")
            voix.charger("en")
        self.assertEqual(len(chargees), 2)
        self.assertEqual(voix.voix_chargees()[-1],
                         lire_voix.nom_voix_configure({}, "en"))

    def test_dire_transmet_la_langue_du_tour(self):
        recu = []
        fausse = types.SimpleNamespace(
            lire=lambda texte, langue, *a, **k: recu.append(langue) or True)
        with mock.patch("builtins.print"):
            boucle_voix.dire("Bonjour Julien.", "fr", threading.Event(),
                             voix=fausse)
            boucle_voix.dire("Hello Julien.", "en", threading.Event(),
                             voix=fausse)
        self.assertEqual(recu, ["fr", "en"])

    def test_repli_sous_processus_avec_la_langue_du_tour(self):
        lance = []

        class FauxProcessus:
            returncode = 0
            stderr = None

            def __init__(self, commande, **_):
                lance.append(commande)

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

        with mock.patch.object(boucle_voix.subprocess, "Popen", FauxProcessus), \
                mock.patch("builtins.print"):
            boucle_voix.dire("Bonjour.", "fr", threading.Event())
        self.assertEqual(lance[0][lance[0].index("--langue") + 1], "fr")


# ---------------------------------------------------------------------------
# 4. Annonces de minuteur : config, sauf tour en cours dans l'autre langue
# ---------------------------------------------------------------------------

class AnnoncesMinuteur(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="jarvis-l1-min-"))
        self.etat = self.dossier / "hud-state.json"
        (self.dossier / "config.toml").write_text(
            '[general]\nlangue = "en"\n', encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.dossier, ignore_errors=True)

    def ecrire_etat(self, etat, langue, age_s=0):
        quand = datetime.now(minuteur.FUSEAU) - timedelta(seconds=age_s)
        self.etat.write_text(json.dumps({
            "etat": etat, "langue": langue,
            "horodatage": quand.isoformat(timespec="seconds")}),
            encoding="utf-8")

    def langue(self):
        return minuteur.langue_annonce(self.dossier, self.etat)

    def test_sans_tour_la_config(self):
        self.assertEqual(self.langue(), "en")

    def test_tour_en_cours_dans_l_autre_langue(self):
        for etat in ("reflexion", "reponse"):
            self.ecrire_etat(etat, "fr", age_s=60)
            self.assertEqual(self.langue(), "fr")

    def test_juste_apres_le_tour(self):
        self.ecrire_etat("repos", "fr", age_s=10)
        self.assertEqual(self.langue(), "fr")

    def test_tour_termine_depuis_longtemps_retour_config(self):
        self.ecrire_etat("repos", "fr", age_s=120)
        self.assertEqual(self.langue(), "en")

    def test_etat_perime_ignore(self):
        self.ecrire_etat("reponse", "fr", age_s=3600)
        self.assertEqual(self.langue(), "en")

    def test_etat_illisible_ou_sans_langue(self):
        self.etat.write_text("{pas du json", encoding="utf-8")
        self.assertEqual(self.langue(), "en")
        self.ecrire_etat("reponse", "", age_s=1)
        self.assertEqual(self.langue(), "en")

    def test_langue_auto_false_ignore_le_tour(self):
        (self.dossier / "config.toml").write_text(
            '[general]\nlangue = "en"\nlangue_auto = false\n', encoding="utf-8")
        self.ecrire_etat("reponse", "fr", age_s=1)
        self.assertEqual(self.langue(), "en")

    def test_regle_pure(self):
        self.assertEqual(langue_tour.langue_annonce_minuteur("en", None), "en")
        self.assertEqual(langue_tour.langue_annonce_minuteur("en", "en"), "en")
        self.assertEqual(langue_tour.langue_annonce_minuteur("en", "fr"), "fr")
        self.assertEqual(langue_tour.langue_annonce_minuteur("fr", "en"), "en")

    def test_declencher_dus_annonce_dans_la_langue_du_tour(self):
        timers = self.dossier / "timers.json"
        echu = (datetime.now(minuteur.FUSEAU)
                - timedelta(seconds=5)).isoformat(timespec="seconds")
        timers.write_text(json.dumps({"timers": [{
            "id": 1, "kind": "timer", "label": "", "due": echu,
            "created": echu}]}), encoding="utf-8")
        annonces = []
        with mock.patch.object(minuteur, "langue_annonce", return_value="fr"), \
                mock.patch.object(minuteur, "annoncer",
                                  lambda m, l="fr", *a, **k:
                                  annonces.append(l)):
            messages = minuteur.declencher_dus(timers)
        self.assertEqual(annonces, ["fr"])
        self.assertIn("minuteur", messages[0])


# ---------------------------------------------------------------------------
# 5. Interface : textes de l'application dans la langue du tour
# ---------------------------------------------------------------------------

class InterfaceParTour(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="jarvis-l1-app-"))

    def tearDown(self):
        shutil.rmtree(self.dossier, ignore_errors=True)

    def test_la_boucle_ecrit_la_langue_du_tour(self):
        chemin = self.dossier / "hud-state.json"
        with mock.patch.object(boucle_voix, "FICHIER_ETAT_HUD", chemin):
            boucle_voix.ecrire_etat_hud("reflexion", langue="fr")
            self.assertEqual(json.loads(chemin.read_text("utf-8"))["langue"],
                             "fr")
            boucle_voix.ecrire_etat_hud("ecoute")  # langue pas encore connue.
            self.assertNotIn("langue", json.loads(chemin.read_text("utf-8")))
        self.assertEqual(langue_tour.langue_tour_en_cours(chemin), None)

    def test_l_application_suit_la_langue_de_chaque_tour(self):
        import _faux_ctk

        for theme in ("or_et_nuit", "centre_de_commande"):
            with self.subTest(theme=theme):
                app, _ctk = _faux_ctk.charger_app(nom=f"app_l1_{theme}")
                fenetre = _faux_ctk.creer_application(app, self.dossier, [],
                                                      theme=theme)
                self.assertEqual(fenetre.langue, "en")
                titre_en = fenetre.titre_minuteurs.options["text"]
                for langue in ("fr", "en", "fr"):
                    app.lire_etat = lambda chemin=None, l=langue: {
                        "etat": "reponse", "transcription": "", "erreur": "",
                        "langue": l, "present": True}
                    fenetre.rafraichir()
                    self.assertEqual(fenetre.langue, langue)
                    self.assertEqual(fenetre.titre_minuteurs.options["text"],
                                     fenetre._titre("minuteurs"))
                self.assertNotEqual(fenetre.titre_minuteurs.options["text"],
                                    titre_en)
                # Sans langue écrite (écoute) : l'interface garde la sienne.
                app.lire_etat = lambda chemin=None: {
                    "etat": "ecoute", "transcription": "", "erreur": "",
                    "langue": "", "present": True}
                fenetre.rafraichir()
                self.assertEqual(fenetre.langue, "fr")

    def test_lecture_du_fichier_ecrit_par_la_boucle(self):
        import _faux_ctk

        app, _ctk = _faux_ctk.charger_app(nom="app_l1_lecture")
        chemin = self.dossier / "hud-state.json"
        with mock.patch.object(boucle_voix, "FICHIER_ETAT_HUD", chemin):
            boucle_voix.ecrire_etat_hud("reponse", langue="fr")
        self.assertEqual(app.lire_etat(chemin)["langue"], "fr")


if __name__ == "__main__":
    unittest.main()
