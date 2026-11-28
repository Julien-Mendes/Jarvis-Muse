"""Lot PR — mode privé (navigation privée).

Verrouille : l'entrée / la sortie à la voix (FR / EN, sans modèle) et par
l'interrupteur de l'application ; les annonces ; le contexte du modèle vidé à
l'entrée, jeté à la sortie (celui d'avant rendu intact) ; l'absence de toute
écriture de la conversation pendant le mode (journal du jour, journal des
tours, data/recherches.json, notes, transcription de data/hud-state.json,
sortie console) ; les minuteurs qui fonctionnent toujours ; la reprise
normale après la sortie. Aucun appel réseau, aucun vrai Chrome.
"""
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import _chemins_lot01  # noqa: F401 — rend scripts/ importable.
import _faux_ctk as faux

import boucle_voix as bv
import recherche
from test_r1_recherche import FausseSession, FauxSynthetiseur

CONFIG_FR = dict(bv.DEFAUTS, langue="fr", fournisseur_llm="groq")
CONFIG_EN = dict(CONFIG_FR, langue="en")


class BasePrive(unittest.TestCase):
    """Dossier temporaire ; tous les fichiers écrits par la boucle y sont
    redirigés ; le mode privé est toujours remis à zéro."""

    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="jarvis-pr-"))
        self.conversations = self.dossier / "conversations"
        self.logs = self.dossier / "logs"
        self.hud = self.dossier / "hud-state.json"
        self.recherches = self.dossier / "recherches.json"
        self.notes = self.dossier / "connaissances.json"
        self.timers = self.dossier / "timers.json"
        self.demande = self.dossier / "prive-demande.json"
        for nom, valeur in (("DOSSIER_CONVERSATIONS", self.conversations),
                            ("DOSSIER_TOURS", self.logs),
                            ("FICHIER_ETAT_HUD", self.hud),
                            ("FICHIER_DEMANDE_PRIVE", self.demande)):
            patch = mock.patch.object(bv, nom, valeur)
            patch.start()
            self.addCleanup(patch.stop)
        self.config = dict(CONFIG_FR, fichier_recherches=str(self.recherches),
                           fichier_connaissances=str(self.notes))
        self.config_en = dict(self.config, langue="en")
        bv.PRIVE.sortir()
        self.addCleanup(bv.PRIVE.sortir)

    def tearDown(self):
        shutil.rmtree(self.dossier, ignore_errors=True)

    def fichiers(self) -> list:
        """Tous les fichiers présents dans le dossier temporaire."""
        return sorted(str(p.relative_to(self.dossier))
                      for p in self.dossier.rglob("*") if p.is_file())

    def entrer(self, historique=None, confirmation=None, langue="fr"):
        return bv.basculer_mode_prive({"action": "entrer", "langue": langue},
                                      historique or [], confirmation)

    def tour(self, phrase, config=None, historique=None, confirmation=None,
             etat_tour=None, cerveau=None):
        return bv.traiter_tour(
            phrase, config or self.config, cerveau or mock.Mock(),
            historique or [], self.timers,
            {} if confirmation is None else confirmation,
            etat_tour=etat_tour)


# ---------------------------------------------------------------------------
# 1. Entrée / sortie à la voix (FR / EN), sans modèle
# ---------------------------------------------------------------------------

class CommandesVocales(unittest.TestCase):
    ENTREES_FR = ["mode privé", "Mode privé.", "Navigation privée",
                  "passe en mode privé", "Passe en navigation privée.",
                  "Jarvis, active le mode privé s'il te plaît",
                  "mets le mode privé", "MODE PRIVE"]
    SORTIES_FR = ["sors du mode privé", "Quitte le mode privé.",
                  "mode normal", "Repasse en mode normal",
                  "désactive le mode privé", "sors de la navigation privée",
                  "fin du mode privé"]
    ENTREES_EN = ["private mode", "Private browsing.", "go private",
                  "Switch to private mode", "turn on private mode",
                  "enter private mode please", "Jarvis, private mode on"]
    SORTIES_EN = ["exit private mode", "Leave private mode.",
                  "normal mode", "back to normal mode",
                  "turn off private mode", "turn private mode off",
                  "quit private browsing", "go back to normal mode"]
    PAS_DES_COMMANDES = [
        "c'est quoi le mode privé de Chrome ?", "what is private mode",
        "ouvre youtube", "est-ce que le mode privé garde l'historique",
        "explique-moi la navigation privée en détail s'il te plaît",
        "mets un minuteur de 5 minutes", "", "   ",
        "note que le mode privé est pratique",
    ]

    def test_entrees_et_sorties_francaises(self):
        for phrase in self.ENTREES_FR:
            self.assertEqual(bv.detecter_mode_prive(phrase),
                             {"action": "entrer", "langue": "fr"}, phrase)
        for phrase in self.SORTIES_FR:
            self.assertEqual(bv.detecter_mode_prive(phrase),
                             {"action": "sortir", "langue": "fr"}, phrase)

    def test_entrees_et_sorties_anglaises(self):
        for phrase in self.ENTREES_EN:
            self.assertEqual(bv.detecter_mode_prive(phrase),
                             {"action": "entrer", "langue": "en"}, phrase)
        for phrase in self.SORTIES_EN:
            self.assertEqual(bv.detecter_mode_prive(phrase),
                             {"action": "sortir", "langue": "en"}, phrase)

    def test_questions_et_autres_phrases_ne_basculent_pas(self):
        for phrase in self.PAS_DES_COMMANDES:
            self.assertIsNone(bv.detecter_mode_prive(phrase), phrase)

    def test_messages_dans_les_deux_langues(self):
        self.assertEqual(bv.msg("fr", "prive_active"),
                         "Mode privé activé : rien ne sera gardé.")
        self.assertEqual(bv.msg("fr", "prive_desactive"),
                         "Mode privé désactivé.")
        self.assertEqual(bv.msg("en", "prive_active"),
                         "Private mode on: nothing will be kept.")
        self.assertEqual(bv.msg("en", "prive_desactive"), "Private mode off.")
        self.assertEqual(bv.msg("fr", "prive_note_refusee"),
                         "En mode privé, je ne garde pas de notes.")
        self.assertEqual(set(bv.MESSAGES["fr"]), set(bv.MESSAGES["en"]))


class Bascule(BasePrive):
    def test_entree_annonce_et_vide_le_contexte_sans_modele(self):
        avant = [{"role": "user", "content": "parle-moi des pâtes"},
                 {"role": "assistant", "content": "Les pâtes…"}]
        confirmation = {"outil": "garder_note", "arguments": {}, "arme_a": 0}
        demande = bv.detecter_mode_prive("passe en mode privé")
        bascule = bv.basculer_mode_prive(demande, avant, confirmation)
        self.assertEqual(bascule["texte"],
                         "Mode privé activé : rien ne sera gardé.")
        self.assertEqual(bascule["langue"], "fr")
        self.assertTrue(bascule["change"])
        self.assertEqual(bascule["historique"], [])  # part de zéro.
        self.assertEqual(confirmation, {})            # rien en attente.
        self.assertTrue(bv.PRIVE.actif)
        self.assertIsInstance(bv.PRIVE.recherches, recherche.Memoire)
        self.assertEqual(self.fichiers(), [])         # rien écrit.

    def test_sortie_jette_le_contexte_prive_et_rend_le_precedent(self):
        avant = [{"role": "user", "content": "bonjour"},
                 {"role": "assistant", "content": "Bonjour Julien."}]
        historique = self.entrer(list(avant))["historique"]
        historique.append({"role": "user", "content": "secret privé"})
        historique.append({"role": "assistant", "content": "réponse privée"})
        demande = bv.detecter_mode_prive("sors du mode privé")
        bascule = bv.basculer_mode_prive(demande, historique, {})
        self.assertEqual(bascule["texte"], "Mode privé désactivé.")
        self.assertEqual(bascule["historique"], avant)
        self.assertNotIn("secret privé", json.dumps(bascule["historique"]))
        self.assertFalse(bv.PRIVE.actif)
        self.assertIsNone(bv.PRIVE.recherches)
        self.assertIsNone(bv.PRIVE._historique_normal)

    def test_annonces_en_anglais(self):
        entree = bv.basculer_mode_prive(
            bv.detecter_mode_prive("go private"), [], {})
        self.assertEqual(entree["texte"],
                         "Private mode on: nothing will be kept.")
        self.assertEqual(entree["langue"], "en")
        sortie = bv.basculer_mode_prive(
            bv.detecter_mode_prive("exit private mode"), [], {})
        self.assertEqual(sortie["texte"], "Private mode off.")

    def test_deja_actif_et_pas_actif(self):
        self.assertEqual(
            bv.basculer_mode_prive({"action": "sortir", "langue": "fr"},
                                   [], {})["texte"],
            "Le mode privé n'est pas actif, Julien.")
        self.entrer()
        historique = [{"role": "user", "content": "x"}]
        deja = bv.basculer_mode_prive({"action": "entrer", "langue": "fr"},
                                      historique, {})
        self.assertFalse(deja["change"])
        self.assertIs(deja["historique"], historique)  # contexte gardé.
        self.assertTrue(bv.PRIVE.actif)

    def test_travailleur_prive_demarre_puis_arrete(self):
        cree = []

        def fabrique(memoire):
            travailleur = mock.Mock()
            travailleur.memoire = memoire
            cree.append(travailleur)
            return travailleur

        bv.basculer_mode_prive({"action": "entrer", "langue": "fr"}, [], {},
                               fabrique)
        self.assertIs(cree[0].memoire, bv.PRIVE.recherches)
        cree[0].demarrer.assert_called_once()
        bv.basculer_mode_prive({"action": "sortir", "langue": "fr"}, [], {})
        cree[0].arreter.assert_called_once()
        self.assertIsNone(bv.PRIVE.travailleur)

    def test_mode_texte_isole_refuse_sans_rien_ecrire(self):
        sortie = io.StringIO()
        with mock.patch("sys.argv", ["boucle_voix.py", "--texte",
                                     "mode privé"]), \
                mock.patch.object(bv, "charger_env"), \
                mock.patch.object(bv, "charger_config",
                                  return_value=dict(self.config)), \
                mock.patch.object(bv, "creer_cerveau") as creer, \
                contextlib.redirect_stdout(sortie):
            self.assertEqual(bv.main(), 0)
        creer.assert_not_called()
        self.assertIn("boucle vocale", sortie.getvalue())
        self.assertFalse(bv.PRIVE.actif)
        self.assertEqual(self.fichiers(), [])


# ---------------------------------------------------------------------------
# 2. Interrupteur de l'application
# ---------------------------------------------------------------------------

class Interrupteur(BasePrive):
    def setUp(self):
        super().setUp()
        self.app_mod, _ctk = faux.charger_app(nom="app_pr")

    def ecrire(self, actif, langue="fr", age_s=0):
        moment = datetime.now(bv.FUSEAU) - timedelta(seconds=age_s)
        self.demande.write_text(json.dumps(
            {"actif": actif, "langue": langue,
             "horodatage": moment.isoformat(timespec="seconds")}),
            encoding="utf-8")

    def test_demande_de_l_application_lue_par_la_boucle(self):
        self.app_mod.ecrire_demande_prive(self.demande, True, "en")
        contenu = json.loads(self.demande.read_text(encoding="utf-8"))
        self.assertEqual(set(contenu), {"actif", "langue", "horodatage"})
        self.assertEqual(bv.lire_demande_prive(),
                         {"action": "entrer", "langue": "en"})
        self.assertFalse(self.demande.exists())  # consommée.
        self.assertIsNone(bv.lire_demande_prive())
        self.app_mod.ecrire_demande_prive(self.demande, False, "fr")
        self.assertEqual(bv.lire_demande_prive(),
                         {"action": "sortir", "langue": "fr"})

    def test_demande_perimee_ou_invalide_ignoree(self):
        self.ecrire(True, age_s=bv.FRAICHEUR_DEMANDE_TEXTE + 60)
        self.assertIsNone(bv.lire_demande_prive())
        self.demande.write_text('{"actif": "oui"}', encoding="utf-8")
        self.assertIsNone(bv.lire_demande_prive())
        self.demande.write_text("pas du json", encoding="utf-8")
        self.assertIsNone(bv.lire_demande_prive())

    def test_interrupteur_bascule_comme_la_voix(self):
        self.ecrire(True, "fr")
        bascule = bv.basculer_mode_prive(bv.lire_demande_prive(), [], {})
        self.assertEqual(bascule["texte"],
                         "Mode privé activé : rien ne sera gardé.")
        self.assertTrue(bv.PRIVE.actif)
        self.ecrire(False, "en")
        bascule = bv.basculer_mode_prive(bv.lire_demande_prive(), [], {})
        self.assertEqual(bascule["texte"], "Private mode off.")
        self.assertFalse(bv.PRIVE.actif)

    def monter_app(self, prive=False):
        module = self.app_mod
        etat = {"etat": "repos", "transcription": "", "erreur": "",
                "langue": "", "present": True, "agents": {}, "prive": prive}
        module.ecrire_ptt = lambda *a, **k: None
        module.charger_recherches = lambda chemin=None: []
        module.charger_notes = lambda chemin=None: []
        module.lister_jours = lambda racine=None: []
        module.mesurer_systeme = lambda *a, **k: None
        module.lire_conversation = lambda chemin=None: []
        module.charger_minuteurs = lambda chemin=None: []
        module.lire_etat = lambda chemin=None: dict(etat)
        module.FICHIER_DEMANDE_PRIVE = self.demande
        reglages = dict(module.DEFAUTS, langue="fr", intervalle_ms=10 ** 7)
        app = module.Application(self.dossier, reglages)
        return app, etat

    def test_menu_ecrit_la_demande_et_la_pastille_suit_la_boucle(self):
        app, etat = self.monter_app()
        self.assertFalse(app.prive)
        self.assertEqual(app.libelle_menu_prive, "Mode privé : activer")
        app.basculer_mode_prive()
        self.assertTrue(json.loads(
            self.demande.read_text(encoding="utf-8"))["actif"])
        # La boucle confirme (hud-state.json « prive »: true).
        etat["prive"] = True
        app.rafraichir()
        self.assertTrue(app.prive)
        self.assertEqual(app.libelle_menu_prive, "Mode privé : quitter")
        self.assertEqual(app.pastille_prive.cget("text"), "● PRIVÉ")
        self.assertEqual(app.pastille_prive.cget("fg_color"),
                         self.app_mod.COULEUR_PRIVE)
        self.assertIn("rien n'est gardé", app.texte_detail.cget("text"))
        app.basculer_mode_prive()
        self.assertFalse(json.loads(
            self.demande.read_text(encoding="utf-8"))["actif"])
        etat["prive"] = False
        app.rafraichir()
        self.assertFalse(app.prive)
        self.assertEqual(app.libelle_menu_prive, "Mode privé : activer")

    def test_lire_etat_de_l_application(self):
        self.hud.write_text(json.dumps({"etat": "repos", "prive": True}),
                            encoding="utf-8")
        self.assertTrue(self.app_mod.lire_etat(self.hud)["prive"])
        self.hud.write_text(json.dumps({"etat": "repos"}), encoding="utf-8")
        self.assertFalse(self.app_mod.lire_etat(self.hud)["prive"])
        self.assertFalse(
            self.app_mod.lire_etat(self.dossier / "absent.json")["prive"])


# ---------------------------------------------------------------------------
# 3. Rien d'écrit pendant le mode privé
# ---------------------------------------------------------------------------

class AucuneEcriture(BasePrive):
    def test_journal_du_jour_et_journal_des_tours(self):
        self.entrer()
        bv.journaliser_echange("ma question privée", "ma réponse privée")
        bv.journaliser_echange(None, "annonce privée")
        bilan = bv._nouveau_bilan(self.config, "voix")
        bilan["outils"] = ["lancer_recherche"]
        bv.journaliser_tour(bilan)
        self.assertFalse(self.conversations.exists())
        self.assertFalse(self.logs.exists())

    def test_transcription_absente_de_l_etat_hud(self):
        self.entrer()
        bv.ecrire_etat_hud("reflexion", transcription="mon secret",
                           langue="fr")
        etat = json.loads(self.hud.read_text(encoding="utf-8"))
        self.assertEqual(etat["transcription"], "")
        self.assertTrue(etat["prive"])
        self.assertNotIn("mon secret", self.hud.read_text(encoding="utf-8"))

    def test_console_sans_le_texte_des_reponses(self):
        self.entrer()
        voix = mock.Mock()
        voix.lire.return_value = True
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            bv.dire("réponse confidentielle", "fr", mock.Mock(), voix=voix)
        self.assertNotIn("confidentielle", sortie.getvalue())
        self.assertIn("(mode privé)", sortie.getvalue())
        voix.lire.assert_called_once()  # mais elle est bien dite.

    def test_note_refusee_poliment(self):
        self.entrer()
        cerveau = mock.Mock()
        reponse = self.tour("note que mon code est 1234", cerveau=cerveau)
        self.assertEqual(reponse, "En mode privé, je ne garde pas de notes.")
        cerveau.repondre.assert_not_called()
        self.assertFalse(self.notes.exists())
        reponse = self.tour("remember that my code is 1234",
                            config=self.config_en)
        self.assertEqual(reponse, "In private mode, I don't keep notes.")
        self.assertFalse(self.notes.exists())

    def test_recherche_en_memoire_seulement(self):
        self.entrer()
        travailleur = mock.Mock()
        bv.PRIVE.travailleur = travailleur
        etat_tour = {}
        reponse = self.tour("cherche les meilleurs vélos et reviens-moi",
                            etat_tour=etat_tour)
        self.assertIn("vélos", reponse)
        travailleur.signaler.assert_called_once()
        self.assertFalse(self.recherches.exists())
        self.assertFalse(list(self.dossier.glob("recherches.json*")))
        taches = recherche.lister(bv.PRIVE.recherches)
        self.assertEqual(len(taches), 1)
        self.assertIn("vélos", taches[0]["question"])

    def test_lecture_du_resultat_sans_proposer_de_note(self):
        self.entrer()
        memoire = bv.PRIVE.recherches
        t = recherche.ajouter(memoire, "vélos", "fr")["tache"]
        recherche.prendre_suivante(memoire)
        recherche.terminer(memoire, t["id"], "Le vélo A gagne.", [])
        confirmation = {}
        reponse = self.tour("lis-moi le résultat", confirmation=confirmation)
        self.assertIn("Le vélo A gagne.", reponse)
        self.assertNotIn("notes", reponse)
        self.assertEqual(confirmation, {})  # aucune proposition armée.
        phrase, propose = bv.formater_annonce_recherches(
            recherche.lister(memoire), "fr")
        self.assertIsNone(propose)
        self.assertNotIn("notes", phrase)
        # Un « oui » arrivé quand même ne garde rien.
        self.assertEqual(bv.executer_garder_recherche(t["id"], self.config),
                         "En mode privé, je ne garde pas de notes.")
        self.assertFalse(self.notes.exists())
        self.assertFalse(self.recherches.exists())

    def test_travailleur_prive_n_ecrit_que_dans_la_memoire(self):
        memoire = recherche.Memoire()
        recherche.ajouter(memoire, "sujet privé", "fr")
        travailleur = recherche.Travailleur(
            memoire, FausseSession, FauxSynthetiseur())
        finale = travailleur.traiter_une()
        self.assertEqual(finale["statut"], "prete")
        self.assertEqual(recherche.lister(memoire)[0]["statut"], "prete")
        self.assertEqual(self.fichiers(), [])
        with self.assertRaises(TypeError):
            Path(memoire)  # jamais confondue avec un chemin de fichier.

    def test_travailleur_arrete_ne_relance_pas_chrome(self):
        memoire = recherche.Memoire()
        recherche.ajouter(memoire, "sujet", "fr")
        sessions = []
        travailleur = recherche.Travailleur(
            memoire, lambda: sessions.append(FausseSession()) or sessions[-1],
            FauxSynthetiseur())
        travailleur.arreter()
        self.assertIsNone(travailleur.traiter_une())
        self.assertEqual(sessions, [])

    def test_session_privee_complete_ne_laisse_aucune_trace(self):
        """Une session privée simulée comme la boucle : chaque tour passe
        par traiter_tour, puis journal, HUD et journal des tours."""
        historique = self.entrer()["historique"]
        cerveau = mock.Mock()
        cerveau.repondre.return_value = {
            "texte": "Paris est la capitale.", "appels_outils": [],
            "utilisation": {"entree": 10, "sortie": 5}}
        for phrase in ("quelle est la capitale de la France",
                       "note que j'aime Paris",
                       "cherche des hôtels à Paris et reviens-moi"):
            bilan = bv._nouveau_bilan(self.config, "voix")
            bv.ecrire_etat_hud("reflexion", transcription=phrase)
            reponse = bv.traiter_tour(phrase, self.config, cerveau,
                                      historique, self.timers, {},
                                      mesures=bilan)
            bv.journaliser_echange(phrase, reponse)
            historique += [{"role": "user", "content": phrase},
                           {"role": "assistant", "content": reponse}]
            bv.ecrire_etat_hud("repos", transcription=phrase)
            bv.journaliser_tour(bilan)
        # Le modèle a bien vu le contexte privé (en mémoire)…
        self.assertEqual(cerveau.repondre.call_count, 1)
        self.assertEqual(self.fichiers(), ["hud-state.json"])
        brut = self.hud.read_text(encoding="utf-8")
        for mot in ("capitale", "Paris", "hôtels"):
            self.assertNotIn(mot, brut)


# ---------------------------------------------------------------------------
# 4. Minuteurs : toujours actifs en mode privé
# ---------------------------------------------------------------------------

class MinuteursEnModePrive(BasePrive):
    def test_minuteur_regle_et_ecrit_pour_sonner(self):
        self.entrer()
        cerveau = mock.Mock()
        reponse = self.tour("mets un minuteur de 5 minutes pour les pâtes",
                            cerveau=cerveau)
        cerveau.repondre.assert_not_called()
        self.assertTrue(reponse.startswith("C'est réglé"), reponse)
        minuteurs = json.loads(self.timers.read_text(encoding="utf-8"))
        self.assertEqual(len(minuteurs["timers"]), 1)
        # Aucune trace de la demande dans l'historique ni le journal.
        bv.journaliser_echange("mets un minuteur de 5 minutes", reponse)
        bv.journaliser_tour(bv._nouveau_bilan(self.config, "voix"))
        self.assertFalse(self.conversations.exists())
        self.assertFalse(self.logs.exists())


# ---------------------------------------------------------------------------
# 5. Reprise normale après la sortie
# ---------------------------------------------------------------------------

class RepriseNormale(BasePrive):
    def test_historique_d_avant_intact_et_journaux_reactives(self):
        bv.journaliser_echange("avant", "réponse d'avant")
        jour = bv.chemin_journal_jour()
        avant = jour.read_text(encoding="utf-8")
        self.entrer()
        bv.journaliser_echange("pendant", "réponse privée")
        self.tour("cherche les vélos et reviens-moi")
        self.assertEqual(jour.read_text(encoding="utf-8"), avant)
        bv.basculer_mode_prive({"action": "sortir", "langue": "fr"}, [], {})
        # Rien de la session privée : ni journal, ni recherche.
        self.assertEqual(jour.read_text(encoding="utf-8"), avant)
        self.assertFalse(self.recherches.exists())
        self.assertEqual(bv.chemin_recherches(self.config), self.recherches)
        # Fonctionnement normal : journal, tours, HUD, notes.
        bv.journaliser_echange("après", "réponse d'après")
        self.assertIn("après", jour.read_text(encoding="utf-8"))
        self.assertNotIn("pendant", jour.read_text(encoding="utf-8"))
        bv.journaliser_tour(bv._nouveau_bilan(self.config, "voix"))
        self.assertEqual(len(list(self.logs.glob("tours-*.jsonl"))), 1)
        bv.ecrire_etat_hud("reflexion", transcription="visible")
        etat = json.loads(self.hud.read_text(encoding="utf-8"))
        self.assertEqual(etat["transcription"], "visible")
        self.assertFalse(etat["prive"])
        self.assertEqual(self.tour("note que j'aime le vélo"),
                         bv.connaissances_mod.texte("fr", "note_ok"))
        self.assertTrue(self.notes.exists())

    def test_recherches_normales_non_touchees_par_le_mode_prive(self):
        recherche.ajouter(self.recherches, "sujet normal", "fr")
        self.entrer()
        self.assertEqual(recherche.lister(bv.chemin_recherches(self.config)),
                         [])
        bv.basculer_mode_prive({"action": "sortir", "langue": "fr"}, [], {})
        taches = recherche.lister(self.recherches)
        self.assertEqual([t["question"] for t in taches], ["sujet normal"])


if __name__ == "__main__":
    unittest.main()
