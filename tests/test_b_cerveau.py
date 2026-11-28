"""Lot B (partie 1) — cerveau plus fiable et plus malin, sans clé Anthropic.

Verrouille : l'effort configurable ([cerveau] effort : bas / moyen / auto),
la sélection d'outils sur des phrases ambiguës (chemins rapides + règles du
prompt), la clarification (« cherche X », rappel sans heure), le chaînage
de plusieurs outils dans un tour (3 cas concrets), et les délais (délai par
appel, budget du tour, message clair quand Groq ne répond pas). Faux
cerveaux et fausses sessions : aucun appel réseau.
"""
import io
import contextlib
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

import _chemins_lot01  # noqa: F401 — rend scripts/ importable.

import boucle_voix as bv
import config_jarvis

CONFIG_FR = dict(bv.DEFAUTS, langue="fr", fournisseur_llm="groq")
CONFIG_EN = dict(CONFIG_FR, langue="en")
TITRE = "I made the perfect Pokemon Yellow ROM hack"


class FauxCerveau:
    """Réponses scriptées : chaque élément = (texte, [(nom, arguments)…]).
    Garde les messages vus et l'effort de chaque appel."""

    def __init__(self, reponses=(), effort="", max_tokens=400):
        self.reponses = list(reponses)
        self.effort, self.max_tokens = effort, max_tokens
        self.vus, self.efforts = [], []

    def repondre(self, messages, outils):
        self.vus.append(list(messages))
        self.efforts.append(self.effort)
        texte, appels = (self.reponses.pop(0) if self.reponses
                         else ("Réponse du modèle.", []))
        return {"texte": texte, "utilisation": {},
                "appels_outils": [{"id": f"a{len(self.vus)}{i}", "nom": n,
                                   "arguments": a}
                                  for i, (n, a) in enumerate(appels)]}

    def message_assistant(self, reponse):
        return {"role": "assistant", "content": reponse["texte"]}


class Session:
    """Session navigateur : réponse par commande, commandes enregistrées."""

    def __init__(self, reponses=None):
        self.reponses = reponses or {}
        self.commandes = []
        self.navigateur_defaut_force = None

    def envoyer(self, commande, delai=60.0):
        self.commandes.append(commande)
        return dict(self.reponses.get(commande["commande"], {"ok": True}))

    def active(self):
        return True

    def fermer(self, volontaire=False):
        pass


def tour(phrase, cerveau=None, session=None, confirmation=None,
         config=CONFIG_FR, mesures=None):
    etat = {}
    reponse = bv.traiter_tour(
        phrase, config, cerveau if cerveau is not None else FauxCerveau(),
        [], None, confirmation if confirmation is not None else {}, session,
        mesures=mesures, etat_tour=etat)
    return reponse, etat


# ---------------------------------------------------------------------------
# 1. Effort configurable
# ---------------------------------------------------------------------------

class EffortConfigurable(unittest.TestCase):
    def test_lecture_du_reglage(self):
        f = config_jarvis.effort_cerveau
        self.assertEqual(f({"cerveau": {"effort": "moyen"}}), "moyen")
        self.assertEqual(f({"cerveau": {"effort": " Medium "}}), "moyen")
        self.assertEqual(f({"cerveau": {"effort": "auto"}}), "auto")
        self.assertIsNone(f({}))  # absent : anciens réglages effort_groq.
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(f({"cerveau": {"effort": "turbo"}}), "bas")

    def test_charger_config_et_defaut_bas_de_l_exemple(self):
        with tempfile.TemporaryDirectory() as dossier:
            (Path(dossier) / "config").mkdir()
            (Path(dossier) / "config" / "config.toml").write_text(
                '[cerveau]\neffort = "moyen"\n', encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(bv.charger_config(Path(dossier))["effort"],
                                 "moyen")
        exemple = config_jarvis.lire_toml(
            bv.RACINE / "config" / "config.example.toml")
        self.assertEqual(exemple["cerveau"]["effort"], "bas")
        self.assertEqual(exemple["boucle"]["modele_groq"],
                         "openai/gpt-oss-120b")  # modèle par défaut inchangé.

    def test_effort_du_tour(self):
        f = bv.effort_du_tour
        self.assertEqual(f(dict(CONFIG_FR, effort="bas"), "x"), "low")
        self.assertEqual(f(dict(CONFIG_FR, effort="moyen"), "x"), "medium")
        auto = dict(CONFIG_FR, effort="auto")
        self.assertEqual(f(auto, "C'est quoi un haïku ?"), "low")
        self.assertEqual(f(auto, "Pourquoi le ciel est bleu ?"), "medium")
        self.assertEqual(f(auto, "Compare Fizz et Public Mobile"), "medium")
        self.assertEqual(f(auto, "mot " * 30), "medium")
        self.assertIsNone(f(CONFIG_FR, "x"))

    def test_plancher_de_jetons_en_moyen(self):
        cerveau = types.SimpleNamespace(effort="low", max_tokens=400)
        bv.appliquer_effort(cerveau, "medium")
        self.assertEqual((cerveau.effort, cerveau.max_tokens),
                         ("medium", bv.MAX_TOKENS_EFFORT_MOYEN))
        bv.appliquer_effort(cerveau, "low")
        self.assertEqual((cerveau.effort, cerveau.max_tokens), ("low", 400))
        bv.appliquer_effort(cerveau, None)  # rien ne change.
        self.assertEqual(cerveau.effort, "low")

    def test_le_tour_envoie_l_effort_et_le_mesure(self):
        for reglage, attendu in (("bas", "low"), ("moyen", "medium")):
            with self.subTest(reglage=reglage):
                cerveau, mesures = FauxCerveau(effort="low"), {}
                tour("Explique-moi les marées", cerveau,
                     config=dict(CONFIG_FR, effort=reglage), mesures=mesures)
                self.assertEqual(cerveau.efforts, [attendu])
                self.assertEqual(mesures["effort"], attendu)
        cerveau = FauxCerveau(effort="high")
        tour("Explique-moi les marées", cerveau)  # [cerveau] absent
        self.assertEqual(cerveau.efforts, ["high"])

    def test_groq_recoit_reasoning_effort(self):
        envoye = {}

        class Completions:
            def create(self, **kwargs):
                envoye.update(kwargs)
                message = types.SimpleNamespace(content="ok", tool_calls=[])
                return types.SimpleNamespace(
                    choices=[types.SimpleNamespace(message=message)],
                    usage=None)

        client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=Completions()))
        client.with_options = lambda timeout: (envoye.__setitem__(
            "timeout", timeout) or client)
        cerveau = object.__new__(bv.CerveauGroq)
        cerveau.client, cerveau.modele = client, "openai/gpt-oss-120b"
        cerveau.max_tokens, cerveau.effort = 400, "low"
        bv.appliquer_effort(cerveau, "medium")
        cerveau.delai_appel = 7.5
        cerveau.repondre([{"role": "user", "content": "x"}], [])
        self.assertEqual(envoye["extra_body"], {"reasoning_effort": "medium"})
        self.assertEqual(envoye["max_tokens"], bv.MAX_TOKENS_EFFORT_MOYEN)
        self.assertEqual(envoye["timeout"], 7.5)
        self.assertEqual(envoye["model"], "openai/gpt-oss-120b")


# ---------------------------------------------------------------------------
# 2. Sélection d'outils sur des phrases ambiguës
# ---------------------------------------------------------------------------

class SelectionDOutils(unittest.TestCase):
    def setUp(self):
        self.appels = []
        rec = self.appels
        self.patches = [
            mock.patch.object(bv, "executer_ajout_note",
                              lambda d, c, s: rec.append(("note", d))
                              or {"texte": "noté"}),
            mock.patch.object(bv, "executer_minuteur",
                              lambda d, *a: rec.append(("minuteur", d))
                              or "réglé"),
            mock.patch.object(bv, "executer_lancement_recherche",
                              lambda d, *a: rec.append(("recherche", d))
                              or {"texte": "lancée"}),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_phrases_ambigues_vont_au_bon_chemin(self):
        cas = [
            # (phrase, chemin attendu, le modèle est-il appelé ?)
            ("Note que la vidéo de Lofi Girl est géniale", "note", False),
            ("Note que je dois chercher un vélo", "note", False),
            ("Ouvre la vidéo de Lofi Girl", "modele", True),
            ("Mets la vidéo X de SmithPlaysPokemon", "modele", True),
            ("Cherche la météo dans le navigateur", "navigateur", False),
            ("Fais-moi une recherche sur les vélos et reviens-moi",
             "recherche", False),
            ("Mets un minuteur de 5 minutes", "minuteur", False),
            ("Cherche les vélos électriques", "clarification", False),
            ("Ouvre youtube.com", "navigateur", False),
            ("Descends", "page", False),
            ("Qu'est-ce que je t'ai dit sur la voiture ?", "modele", True),
        ]
        for phrase, chemin, modele in cas:
            with self.subTest(phrase=phrase):
                self.appels.clear()
                cerveau = FauxCerveau()
                session = Session({"defiler": {"ok": True, "bouge": True}})
                reponse, _ = tour(phrase, cerveau, session)
                self.assertEqual(bool(cerveau.vus), modele)
                if chemin in ("note", "minuteur", "recherche"):
                    self.assertEqual(self.appels[0][0], chemin)
                elif chemin == "navigateur":
                    self.assertIn(session.commandes[0]["commande"],
                                  ("naviguer", "rechercher"))
                elif chemin == "page":
                    self.assertEqual(session.commandes[0]["commande"],
                                     "defiler")
                elif chemin == "clarification":
                    self.assertIn("navigateur", reponse)
                    self.assertEqual(session.commandes, [])

    def test_prompt_dit_quel_outil_pour_quoi(self):
        for langue in ("fr", "en"):
            with self.subTest(langue=langue):
                prompt = bv.prompt_systeme(langue)
                for outil in ("chercher_et_ouvrir", "ouvrir_navigateur",
                              "lancer_recherche", "lire_recherche",
                              "chercher_connaissance", "regler_minuteur",
                              "naviguer_page", "cliquer"):
                    self.assertIn(outil, prompt)
        self.assertIn("chercher_et_ouvrir (jamais ouvrir_navigateur ni "
                      "lancer_recherche)", bv.prompt_systeme("fr"))
        self.assertIn("« note que X » est déjà gardé par le code",
                      bv.prompt_systeme("fr"))


# ---------------------------------------------------------------------------
# 3. Clarification
# ---------------------------------------------------------------------------

class Clarification(unittest.TestCase):
    def setUp(self):
        self.lancements, self.minuteurs = [], []
        for nom, liste, retour in (
                ("executer_lancement_recherche", self.lancements,
                 {"texte": "C'est lancé."}),
                ("executer_minuteur", self.minuteurs, "C'est réglé.")):
            p = mock.patch.object(
                bv, nom, lambda d, *a, l=liste, r=retour: l.append(d) or r)
            p.start()
            self.addCleanup(p.stop)

    def test_cherche_x_demande_navigateur_ou_recherche(self):
        session, confirmation = Session(), {}
        reponse, _ = tour("Cherche les horaires de la STM", FauxCerveau(),
                          session, confirmation)
        self.assertEqual(reponse, bv.msg("fr", "clarifier_cherche",
                                         sujet="les horaires de la stm"))
        self.assertEqual(confirmation["outil"], "clarification")
        reponse, _ = tour("Dans le navigateur", FauxCerveau(), session,
                          confirmation)
        self.assertEqual(session.commandes, [
            {"commande": "rechercher", "requete": "les horaires de la stm"}])
        # Autre réponse : recherche en arrière-plan.
        tour("cherche les horaires de la STM", FauxCerveau(), session,
             confirmation)
        tour("Fais la recherche et reviens-moi", FauxCerveau(), session,
             confirmation)
        self.assertEqual(self.lancements[0]["sujet"], "les horaires de la stm")

    def test_reponse_hors_sujet_ou_tardive_est_une_nouvelle_demande(self):
        session, confirmation = Session(), {}
        tour("Cherche les horaires de la STM", FauxCerveau(), session,
             confirmation)
        cerveau = FauxCerveau()
        tour("Quelle heure est-il ?", cerveau, session, confirmation)
        self.assertEqual(len(cerveau.vus), 1)
        self.assertEqual(session.commandes, [])
        tour("Cherche les horaires de la STM", FauxCerveau(), session,
             confirmation)
        confirmation["arme_a"] = time.monotonic() - 60
        tour("dans le navigateur", FauxCerveau(), session, confirmation)
        self.assertEqual(session.commandes, [])

    def test_rappel_sans_heure_demande_quand(self):
        for phrase, reponse, langue, attendu in (
                ("Rappelle-moi de sortir les poubelles", "Dans 20 minutes",
                 "fr", {"minutes": 20.0, "a": None}),
                ("Rappelle-moi d'appeler maman", "à 18h30", "fr",
                 {"minutes": None, "a": "18:30"}),
                ("Remind me to call mom", "in 2 hours", "en",
                 {"minutes": 120.0, "a": None})):
            with self.subTest(phrase=phrase):
                self.minuteurs.clear()
                confirmation = {}
                config = CONFIG_EN if langue == "en" else CONFIG_FR
                question, _ = tour(phrase, FauxCerveau(), Session(),
                                   confirmation, config)
                self.assertEqual(question, bv.msg(langue, "clarifier_rappel"))
                self.assertEqual(self.minuteurs, [])  # rien deviné.
                tour(reponse, FauxCerveau(), Session(), confirmation, config)
                demande, = self.minuteurs
                self.assertEqual({k: demande[k] for k in ("minutes", "a")},
                                 attendu)
                self.assertIn(phrase.split(" ", 3)[-1].split("'")[-1][:5],
                              demande["etiquette"])

    def test_pas_de_question_quand_c_est_clair_ou_sans_risque(self):
        f = bv.detecter_ambiguite
        for phrase in ("Ouvre youtube.com", "Descends",
                       "Cherche la météo dans le navigateur",
                       "Cherche la vidéo de Lofi Girl sur YouTube",
                       "Rappelle-moi de sortir les poubelles à 18h30",
                       "Rappelle-moi de sortir les poubelles dans 10 minutes",
                       "Remind me to call mom tomorrow",
                       "C'est quoi un haïku ?"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(f(phrase))
        self.assertEqual(f("Cherche les vélos électriques")["type"],
                         "cherche")
        self.assertEqual(f("search for e-bikes")["type"], "cherche")


# ---------------------------------------------------------------------------
# 4. Chaînage multi-étapes (3 cas concrets)
# ---------------------------------------------------------------------------

VIDEO = {"ok": True, "trouve": True, "titre_resultat":
         "I Made the PERFECT Pokémon Yellow Romhack!",
         "chaine_resultat": "SmithPlays Pokémon"}


class Chainage(unittest.TestCase):
    def test_cas_1_ouvrir_youtube_puis_mettre_la_video(self):
        session = Session({"chercher_et_ouvrir": VIDEO})
        cerveau = FauxCerveau([
            ("", [("ouvrir_navigateur", {"url": "youtube.com"})]),
            ("", [("chercher_et_ouvrir", {"titre": TITRE,
                                          "chaine": "SmithPlaysPokemon"})]),
            ("", [])])
        reponse, etat = tour(f"Ouvre youtube.com puis mets la vidéo {TITRE}",
                             cerveau, session)
        self.assertEqual([c["commande"] for c in session.commandes],
                         ["naviguer", "chercher_et_ouvrir"])
        self.assertEqual(len(cerveau.vus), 3)  # sans redemander à Julien.
        self.assertIn("PERFECT Pokémon Yellow Romhack", reponse)
        # Le titre trouvé (donnée externe) n'est jamais redonné au modèle.
        self.assertNotIn("PERFECT", str(cerveau.vus[-1]))
        self.assertNotIn("PERFECT", etat["historique"])
        self.assertTrue(etat["externe"])

    def test_cas_2_chercher_la_video_puis_ouvrir_la_deuxieme(self):
        session = Session({
            "chercher_et_ouvrir": VIDEO,
            "position": {"ok": True, "rang": 2, "nombre": 5,
                         "titre": "BEATING the Yellow Romhack! - YouTube"}})
        cerveau = FauxCerveau([
            ("", [("chercher_et_ouvrir", {"titre": TITRE})]),
            ("", [("naviguer_page", {"action": "position", "rang": 2,
                                     "genre": "video"})]),
            ("", [])])
        reponse, _ = tour(f"Cherche la vidéo {TITRE} puis ouvre la "
                          "deuxième", cerveau, session)
        self.assertEqual([c["commande"] for c in session.commandes],
                         ["chercher_et_ouvrir", "position"])
        self.assertIn("PERFECT Pokémon Yellow Romhack", reponse)
        self.assertIn("Tu es sur « BEATING the Yellow Romhack! »", reponse)
        self.assertLess(reponse.index("PERFECT"), reponse.index("BEATING"))

    def test_cas_3_minuteur_puis_video_le_chemin_rapide_ne_coupe_pas(self):
        minuteurs = []
        session = Session({"chercher_et_ouvrir": VIDEO})
        cerveau = FauxCerveau([
            ("", [("regler_minuteur", {"minutes": 10,
                                       "etiquette": "pâtes"})]),
            ("", [("chercher_et_ouvrir", {"titre": TITRE})]),
            ("", [])])
        with mock.patch.object(bv, "executer_minuteur",
                               lambda d, *a: minuteurs.append(d)
                               or "C'est réglé : minuteur de 10 minutes."):
            reponse, _ = tour("Mets un minuteur de 10 minutes pour les pâtes "
                              f"et lance la vidéo {TITRE}", cerveau, session)
        self.assertEqual(minuteurs[0]["minutes"], 10)
        self.assertEqual(session.commandes[0]["commande"],
                         "chercher_et_ouvrir")
        self.assertIn("PERFECT", reponse)
        self.assertEqual(len(cerveau.vus), 3)

    def test_plusieurs_appels_dans_une_reponse(self):
        session = Session({"defiler": {"ok": True, "bouge": True},
                           "historique": {"ok": True, "bouge": True,
                                          "titre": "Accueil"}})
        cerveau = FauxCerveau([
            ("", [("naviguer_page", {"action": "descendre"}),
                  ("naviguer_page", {"action": "retour"})]),
            ("", [])])
        reponse, _ = tour("fais défiler et reviens à la page d'avant stp",
                          cerveau, session)
        self.assertEqual([c["commande"] for c in session.commandes],
                         ["defiler", "historique"])
        self.assertIn("Je descends", reponse)
        self.assertIn("Tu es sur « Accueil »", reponse)

    def test_une_seule_etape_reste_a_un_seul_appel(self):
        session = Session({"chercher_et_ouvrir": VIDEO})
        cerveau = FauxCerveau([("", [("chercher_et_ouvrir",
                                      {"titre": TITRE})])])
        tour(f"Ouvre la vidéo {TITRE}", cerveau, session)
        self.assertEqual(len(cerveau.vus), 1)  # latence inchangée.

    def test_cerveau_qui_tombe_en_cours_dit_ce_qui_est_fait(self):
        session = Session({"chercher_et_ouvrir": VIDEO})

        class Panne(FauxCerveau):
            def repondre(self, messages, outils):
                if self.vus:
                    raise ConnectionError("Groq ne répond plus")
                return super().repondre(messages, outils)

        cerveau = Panne([("", [("chercher_et_ouvrir", {"titre": TITRE})])])
        with contextlib.redirect_stderr(io.StringIO()):
            reponse, _ = tour(f"Mets la vidéo {TITRE} puis descends",
                              cerveau, session)
        self.assertIn("PERFECT", reponse)

    def test_detection_des_etapes(self):
        f = bv.demande_multi_etapes
        for phrase in ("ouvre YouTube puis mets la vidéo X",
                       "mets un minuteur et lance la vidéo X",
                       "open YouTube then play X", "search X and open it"):
            self.assertTrue(f(phrase), phrase)
        for phrase in ("cherche ça et reviens-moi", "Simon et Garfunkel",
                       "mets la vidéo de Tom and Jerry",
                       "note que X", "c'est quoi un haïku"):
            self.assertFalse(f(phrase), phrase)


# ---------------------------------------------------------------------------
# 5. Délais et reprises
# ---------------------------------------------------------------------------

class FauxGroq:
    crees = []

    def __init__(self, **options):
        FauxGroq.crees.append(options)


class DelaisEtReprises(unittest.TestCase):
    def test_clients_groq_avec_delai_et_une_reprise(self):
        FauxGroq.crees = []
        with mock.patch.dict(sys.modules,
                             {"groq": types.SimpleNamespace(Groq=FauxGroq)}):
            bv.CerveauGroq("cle", "openai/gpt-oss-120b", 400, "low", 12.0)
            bv.TranscripteurGroq("cle", "whisper-large-v3-turbo")
        cerveau, stt = FauxGroq.crees
        self.assertEqual((cerveau["timeout"], cerveau["max_retries"]),
                         (12.0, 1))
        self.assertEqual((stt["timeout"], stt["max_retries"]),
                         (bv.DELAI_STT_S, 1))

    def test_bornes_des_delais(self):
        self.assertEqual(bv.delai_tour({"delai_tour_s": 2}), 5.0)
        self.assertEqual(bv.delai_tour({"delai_tour_s": 1000}), 300.0)
        self.assertEqual(bv.delai_tour({"delai_tour_s": "x"}), 45.0)
        self.assertEqual(bv.delai_tour({}), 45.0)

    def test_chaque_appel_est_borne_au_temps_qui_reste(self):
        cerveau = FauxCerveau()
        cerveau.client = object()
        tour("Bonjour", cerveau, config=dict(CONFIG_FR, delai_tour_s=10))
        self.assertAlmostEqual(cerveau.delai_appel, 10 / 2, places=2)  # 1 reprise.
        cerveau = FauxCerveau()
        cerveau.client = object()
        tour("Bonjour", cerveau)
        self.assertEqual(cerveau.delai_appel, 20.0)  # delai_cerveau_s

    def test_budget_du_tour_depasse_message_clair(self):
        horloge = [1000.0]

        class Lent(FauxCerveau):
            def repondre(self, messages, outils):
                horloge[0] += 30  # Groq met 30 s à répondre.
                return super().repondre(messages, outils)

        cerveau = Lent([("", [("regler_minuteur", {})])] * 5)
        with mock.patch.object(bv.time, "monotonic", lambda: horloge[0]), \
                contextlib.redirect_stderr(io.StringIO()):
            reponse, _ = tour("Règle quelque chose", cerveau,
                              config=dict(CONFIG_FR, delai_tour_s=45))
        self.assertEqual(len(cerveau.vus), 2)  # 30 s + 30 s > 45 s : stop.
        self.assertEqual(reponse, bv.msg("fr", "cerveau_lent"))

    def test_groq_ne_repond_pas_jamais_de_silence(self):
        class Erreur(Exception):
            pass

        class APITimeoutError(Exception):
            pass

        limite = Erreur("trop de requêtes")
        limite.status_code = 429
        for erreur, cle in ((APITimeoutError("délai"), "cerveau_lent"),
                            (ConnectionError("réseau"),
                             "cerveau_injoignable"),
                            (limite, "limite")):
            with self.subTest(erreur=type(erreur).__name__):
                class Panne(FauxCerveau):
                    def repondre(self, messages, outils, e=erreur):
                        raise e

                with contextlib.redirect_stderr(io.StringIO()):
                    for config, langue in ((CONFIG_FR, "fr"),
                                           (CONFIG_EN, "en")):
                        mesures = {}
                        reponse, _ = tour("Bonjour", Panne(), config=config,
                                          mesures=mesures)
                        self.assertEqual(reponse, bv.msg(langue, cle))
                        self.assertTrue(reponse.strip())
                        self.assertIn("erreur", mesures)

    def test_transcription_impossible_dite_dans_les_deux_langues(self):
        for langue in ("fr", "en"):
            self.assertIn("F9", bv.msg(langue, "transcription_impossible"))


if __name__ == "__main__":
    unittest.main()
