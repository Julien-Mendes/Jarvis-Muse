"""Lot DB (+ U3, U5) — tableau de bord complet de l'application.

Verrouille : le moniteur système (valeurs simulées, aucune mesure réelle),
les tuiles de minuteur cliquables (pause, reprise, annulation confirmée —
dans minuteur.py et depuis l'application), les recherches à point de
couleur et les notes qui s'ouvrent d'un clic, les animations (aucune au
repos, réglage pour les couper), le panneau Agents, le panneau
Conversations, et l'affichage de la colonne du tableau de bord — dans les
deux thèmes (or_et_nuit, centre_de_commande). Faux CustomTkinter
(_faux_ctk.py) : on vérifie ce qui est demandé à Tk, pas le rendu.
"""
import json
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import _faux_ctk as faux

import _chemins_lot01  # noqa: F401 — rend scripts/ importable.
import minuteur

THEMES_TESTES = ("or_et_nuit", "centre_de_commande")


def monter(theme="or_et_nuit", etat="repos", **config):
    module, ctk = faux.charger_app(nom="app_db")
    tmp = tempfile.TemporaryDirectory()
    module.ecrire_ptt = lambda *a, **k: None
    module.charger_recherches = lambda chemin=None: []
    module.charger_notes = lambda chemin=None: []
    module.lister_jours = lambda racine=None: []
    module.mesurer_systeme = lambda *a, **k: {"cpu": 3.0, "ram": 40.0,
                                              "disque": 55.0}
    module.FICHIER_MINUTEURS = Path(tmp.name) / "timers.json"
    module.FICHIER_CONNAISSANCES = Path(tmp.name) / "connaissances.json"
    module.lire_conversation = lambda chemin=None: []
    module.lire_etat = lambda chemin=None: {
        "etat": etat, "transcription": "", "erreur": "", "langue": "",
        "present": True, "agents": {}}
    module.charger_minuteurs = lambda chemin=None: []
    reglages = dict(module.DEFAUTS, langue="en", theme=theme,
                    intervalle_ms=10 ** 7)
    reglages.update(config)
    app = module.Application(Path(tmp.name), reglages)
    return module, app, tmp


class SondeSimulee:
    """Remplace psutil : valeurs fixées par le test."""

    def __init__(self, cpu=12.4, ram=61.0, disque=93.2, panne=()):
        self.cpu, self.ram, self.disque, self.panne = cpu, ram, disque, panne
        self.intervalles = []

    def cpu_percent(self, interval=None):
        self.intervalles.append(interval)
        if "cpu" in self.panne:
            raise OSError("panne")
        return self.cpu

    def virtual_memory(self):
        return types.SimpleNamespace(percent=self.ram)

    def disk_usage(self, chemin):
        if "disque" in self.panne:
            raise OSError("panne")
        return types.SimpleNamespace(percent=self.disque)


# ---------------------------------------------------------------------------
# 1. Moniteur système
# ---------------------------------------------------------------------------

class MoniteurSysteme(unittest.TestCase):
    def setUp(self):
        self.module, _ = faux.charger_app(nom="app_db_mesure")

    def test_mesures_simulees_et_non_bloquantes(self):
        sonde = SondeSimulee()
        mesures = self.module.mesurer_systeme(sonde, "C:\\")
        self.assertEqual(mesures, {"cpu": 12.4, "ram": 61.0, "disque": 93.2})
        self.assertEqual(sonde.intervalles, [None])  # jamais d'attente.

    def test_valeurs_bornees_et_panne_partielle(self):
        mesures = self.module.mesurer_systeme(
            SondeSimulee(cpu=140, ram=-3, panne=("disque",)), "/")
        self.assertEqual(mesures, {"cpu": 100.0, "ram": 0.0, "disque": None})

    def test_sans_psutil(self):
        with mock.patch.object(self.module, "_psutil", lambda: None):
            self.assertIsNone(self.module.mesurer_systeme())

    def test_couleurs_des_seuils(self):
        f = self.module.statut_charge
        self.assertEqual([f(10), f(70), f(89.9), f(90), f(None)],
                         ["ok", "attente", "attente", "erreur", "inactif"])

    def test_jauges_dans_les_deux_themes(self):
        for theme in THEMES_TESTES:
            with self.subTest(theme=theme):
                module, app, tmp = monter(theme)
                self.addCleanup(tmp.cleanup)
                app._afficher_systeme({"cpu": 12.4, "ram": 75.0,
                                       "disque": 96.6})
                textes = {k: v[1].options["text"]
                          for k, v in app._jauges_systeme.items()}
                self.assertEqual(textes, {"cpu": "12 %", "ram": "75 %",
                                          "disque": "97 %"})
                canevas = app._jauges_systeme["disque"][0]
                arc = [o for o in canevas.objets.values() if o.get("arc")][0]
                self.assertEqual(arc["outline"], module.couleur_etat("erreur"))
                self.assertAlmostEqual(arc["extent"], -360 * 0.97)
                # Même valeur arrondie : rien n'est redessiné.
                avant = dict(canevas.objets)
                app._afficher_systeme({"cpu": 12.1, "ram": 75.2,
                                       "disque": 96.9})
                self.assertEqual(canevas.objets, avant)

    def test_psutil_absent_tirets(self):
        _module, app, tmp = monter()
        self.addCleanup(tmp.cleanup)
        app._afficher_systeme(None)
        self.assertEqual({v[1].options["text"]
                          for v in app._jauges_systeme.values()}, {"—"})

    def test_une_mesure_toutes_les_5_secondes(self):
        module, app, tmp = monter()
        self.addCleanup(tmp.cleanup)
        appels = []
        module.mesurer_systeme = lambda *a, **k: appels.append(1) or {
            "cpu": 1.0, "ram": 1.0, "disque": 1.0}
        app.fenetre.avancer(module.INTERVALLE_SYSTEME_MS * 3)
        self.assertEqual(len(appels), 3)
        self.assertEqual(module.INTERVALLE_SYSTEME_MS, 5000)


# ---------------------------------------------------------------------------
# 2. Minuteurs : pause, reprise, annulation (minuteur.py)
# ---------------------------------------------------------------------------

class MinuteurPauseReprise(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.chemin = Path(self.tmp.name) / "timers.json"
        self.ref = datetime(2026, 11, 28, 12, 0, tzinfo=minuteur.FUSEAU)
        cree = self.ref - timedelta(minutes=5)
        minuteur.sauvegarder(self.chemin, {"timers": [
            {"id": 1, "kind": "timer", "label": "pâtes",
             "due": (self.ref + timedelta(minutes=5)).isoformat(),
             "minutes": 10, "created": cree.isoformat()},
            {"id": 2, "kind": "rappel", "label": "colis",
             "due": (self.ref + timedelta(hours=3)).isoformat(),
             "minutes": None, "created": cree.isoformat()}], "next_id": 3})

    def lire(self):
        return {m["id"]: m for m in minuteur.charger(self.chemin)["timers"]}

    def a(self, moment):
        return mock.patch.object(minuteur, "maintenant", lambda: moment)

    def test_pause_garde_le_temps_restant_et_ne_sonne_pas(self):
        with self.a(self.ref):
            self.assertIsNotNone(minuteur.mettre_en_pause(self.chemin, 1))
        m = self.lire()[1]
        self.assertTrue(m["paused"])
        self.assertEqual(m["remaining_s"], 300.0)
        # Une heure plus tard, rien ne sonne : il est en pause.
        with self.a(self.ref + timedelta(hours=1)), \
                mock.patch.object(minuteur, "annoncer"):
            self.assertEqual(minuteur.declencher_dus(self.chemin,
                                                     langue="fr"), [])
        self.assertIn(1, self.lire())

    def test_reprise_repart_de_maintenant_et_garde_la_jauge(self):
        with self.a(self.ref):
            minuteur.mettre_en_pause(self.chemin, 1)
        plus_tard = self.ref + timedelta(minutes=20)
        with self.a(plus_tard):
            self.assertIsNotNone(minuteur.reprendre(self.chemin, 1))
        m = self.lire()[1]
        self.assertNotIn("paused", m)
        due = datetime.fromisoformat(m["due"])
        cree = datetime.fromisoformat(m["created"])
        self.assertEqual(due, plus_tard + timedelta(minutes=5))
        self.assertEqual(due - cree, timedelta(minutes=10))  # durée totale.

    def test_rappel_ni_pause_ni_double_pause(self):
        with self.a(self.ref):
            self.assertIsNone(minuteur.mettre_en_pause(self.chemin, 2))
            minuteur.mettre_en_pause(self.chemin, 1)
            self.assertIsNone(minuteur.mettre_en_pause(self.chemin, 1))
            self.assertIsNone(minuteur.reprendre(self.chemin, 2))
            self.assertIsNone(minuteur.mettre_en_pause(self.chemin, 99))

    def test_annuler_par_numero(self):
        self.assertIsNotNone(minuteur.annuler_numero(self.chemin, 2))
        self.assertEqual(list(self.lire()), [1])
        self.assertIsNone(minuteur.annuler_numero(self.chemin, 2))


# ---------------------------------------------------------------------------
# 3. Tuiles cliquables (application)
# ---------------------------------------------------------------------------

class TuilesDeMinuteur(unittest.TestCase):
    def monter_avec_fichier(self, theme):
        module, app, tmp = monter(theme)
        self.addCleanup(tmp.cleanup)
        ref = datetime.now(minuteur.FUSEAU)
        minuteur.sauvegarder(module.FICHIER_MINUTEURS, {"timers": [
            {"id": 7, "kind": "timer", "label": "thé",
             "due": (ref + timedelta(minutes=4)).isoformat(),
             "minutes": 5, "created": (ref - timedelta(minutes=1))
             .isoformat()}], "next_id": 8})
        module.charger_minuteurs = (
            lambda chemin=None, m=module, o=faux: o.__dict__ and
            _charger_vrai(m))
        app._rafraichir_minuteurs(module.charger_minuteurs(), ref)
        return module, app

    def test_clic_pause_reprise_annulation_dans_les_deux_themes(self):
        for theme in THEMES_TESTES:
            with self.subTest(theme=theme):
                module, app = self.monter_avec_fichier(theme)
                tuile = app.conteneur_minuteurs.winfo_children()[0]
                tuile.declencher("<Button-1>")  # clic sur la tuile
                self.assertIsNotNone(app._fenetre_minuteur)
                self.assertEqual(set(app._boutons_minuteur),
                                 {"pause", "annuler"})
                app._boutons_minuteur["pause"].options["command"]()
                fichier = minuteur.charger(module.FICHIER_MINUTEURS)
                self.assertTrue(fichier["timers"][0]["paused"])
                self.assertIsNone(app._fenetre_minuteur)  # fermée.
                ligne = app.conteneur_minuteurs.winfo_children()[0]
                texte = (ligne.options.get("text") or
                         ligne.winfo_children()[1].options["text"])
                self.assertIn("paused", texte)
                # Reprise depuis la tuile en pause.
                app.ouvrir_actions_minuteur(0)
                self.assertIn("reprendre", app._boutons_minuteur)
                app._boutons_minuteur["reprendre"].options["command"]()
                fichier = minuteur.charger(module.FICHIER_MINUTEURS)
                self.assertNotIn("paused", fichier["timers"][0])
                # Annulation : premier clic = « Confirm? », rien d'annulé.
                app.ouvrir_actions_minuteur(0)
                annuler = app._boutons_minuteur["annuler"]
                annuler.options["command"]()
                self.assertEqual(annuler.options["text"], "Confirm?")
                self.assertEqual(len(minuteur.charger(
                    module.FICHIER_MINUTEURS)["timers"]), 1)
                annuler.options["command"]()
                self.assertEqual(minuteur.charger(
                    module.FICHIER_MINUTEURS)["timers"], [])
                vide, = app.conteneur_minuteurs.winfo_children()
                self.assertEqual(vide.options["text"], "No timers running.")

    def test_rappel_seulement_annulable(self):
        module, app = self.monter_avec_fichier("or_et_nuit")
        app._minuteurs_affiches = [dict(app._minuteurs_affiches[0],
                                        kind="rappel")]
        app.ouvrir_actions_minuteur(0)
        self.assertEqual(set(app._boutons_minuteur), {"annuler"})
        app.ouvrir_actions_minuteur(5)  # hors liste : rien.

    def test_minuteur_en_pause_formate_et_jauge_eteinte(self):
        module, app, tmp = monter("centre_de_commande")
        self.addCleanup(tmp.cleanup)
        ref = datetime(2026, 11, 28, 12, 0, tzinfo=module.FUSEAU)
        m = {"id": 1, "due": ref - timedelta(hours=1), "label": "pâtes",
             "kind": "timer", "total_s": 600, "pause_s": 150.0}
        self.assertEqual(module.formater_minuteurs([m], ref, "fr"),
                         ("• pâtes : en pause (2 min)",))
        self.assertEqual(module.etat_jauge_minuteur(m, ref), (0.25, "inactif"))
        actifs = module.etats_agents({"etat": "repos"}, [m], [])
        self.assertEqual(actifs["minuteurs"], "veille")

    def test_lecture_du_fichier_en_pause(self):
        module, _ = faux.charger_app(nom="app_db_lecture")
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "timers.json"
            chemin.write_text(json.dumps({"timers": [
                {"id": 3, "kind": "timer", "label": "a",
                 "due": "2026-11-28T10:00:00-05:00", "paused": True,
                 "remaining_s": 42},
                {"id": 4, "kind": "timer", "label": "b",
                 "due": "2026-11-28T11:00:00-05:00"}]}), encoding="utf-8")
            lus = module.charger_minuteurs(chemin)
        self.assertEqual([m["id"] for m in lus], [4, 3])  # pause en dernier.
        self.assertEqual(lus[1]["pause_s"], 42.0)
        self.assertIsNone(lus[0]["pause_s"])


def _charger_vrai(module):
    """charger_minuteurs d'origine (le montage le remplace par une liste
    vide) sur le fichier temporaire du test."""
    original = faux.charger_app(nom="app_db_orig")[0].charger_minuteurs
    return original(module.FICHIER_MINUTEURS)


class RecherchesEtNotes(unittest.TestCase):
    def test_point_de_couleur_dans_les_deux_themes_et_clic(self):
        for theme in THEMES_TESTES:
            with self.subTest(theme=theme):
                module, app, tmp = monter(theme)
                self.addCleanup(tmp.cleanup)
                ouvertes = []
                app.ouvrir_recherche = ouvertes.append
                taches = [{"id": 2, "question": "vélos", "statut": "prete"},
                          {"id": 1, "question": "pompe", "statut": "echec"}]
                app._rafraichir_recherches(taches)
                rangees = app.conteneur_recherches.winfo_children()
                self.assertEqual(len(rangees), 2)
                point, bouton = rangees[1].winfo_children()
                self.assertEqual(point.options["text_color"],
                                 module.couleur_etat("erreur"))
                bouton.options["command"]()
                self.assertEqual(ouvertes, [taches[1]])

    def test_note_s_ouvre_d_un_clic(self):
        for theme in THEMES_TESTES:
            with self.subTest(theme=theme):
                _module, app, tmp = monter(theme)
                self.addCleanup(tmp.cleanup)
                note = {"id": 1, "texte": "Budget mini-PC : 600 € " * 8,
                        "cree_le": "2026-11-26T10:00:00-05:00"}
                app._rafraichir_connaissances([note])
                tuile, = app.conteneur_connaissances.winfo_children()
                texte = tuile.winfo_children()[0]
                texte.declencher("<Button-1>")
                fenetre = app._fenetre_note
                corps = [e.options.get("text") for e in
                         fenetre.winfo_children()[0].winfo_children()]
                self.assertIn(note["texte"], corps)  # texte entier.


# ---------------------------------------------------------------------------
# 4. Animations (lot U5)
# ---------------------------------------------------------------------------

class FausseFenetre:
    def __init__(self):
        self.taches = []

    def after(self, delai, fonction):
        self.taches.append((delai, fonction))
        return len(self.taches)


class Animations(unittest.TestCase):
    def setUp(self):
        self.module, _ = faux.charger_app(nom="app_db_anim")

    def test_animateur_ne_tourne_que_pendant_une_animation(self):
        fenetre = FausseFenetre()
        animateur = self.module.Animateur(fenetre, True)
        self.assertEqual(fenetre.taches, [])  # au repos : rien de planifié.
        vus = []
        animateur.lancer("a", 200, vus.append)   # 5 images de 40 ms
        animateur.lancer("b", 400, lambda t: None)
        self.assertEqual(len(fenetre.taches), 1)  # une seule boucle.
        images = 0
        while fenetre.taches:
            delai, image = fenetre.taches.pop(0)
            self.assertEqual(delai, self.module.PAS_TRANSITION_MS)
            image()
            images += 1
        self.assertFalse(animateur.en_cours())
        self.assertEqual(vus, [0.2, 0.4, 0.6, 0.8, 1.0])
        self.assertEqual(images, 10)

    def test_animations_coupees_derniere_image_tout_de_suite(self):
        fenetre = FausseFenetre()
        animateur = self.module.Animateur(fenetre, False)
        vus = []
        animateur.lancer("a", 500, vus.append)
        self.assertEqual(vus, [1.0])
        self.assertEqual(fenetre.taches, [])

    def test_widget_detruit_animation_abandonnee(self):
        fenetre = FausseFenetre()
        animateur = self.module.Animateur(fenetre, True)

        def casse(_t):
            raise RuntimeError("détruit")

        animateur.lancer("a", 300, casse)
        fenetre.taches.pop()[1]()
        self.assertFalse(animateur.en_cours())

    def test_eclosion_de_l_orbe(self):
        courbe = self.module.courbe_eclosion
        self.assertAlmostEqual(courbe(0), 1.10)
        self.assertEqual(courbe(1), 1.0)
        self.assertLess(courbe(0.5), courbe(0.2))
        # Tient dans le canevas de 116 px (halo 52 px à l'échelle 1).
        self.assertLessEqual(self.module.ORBE_RAYONS[0] * courbe(0),
                             self.module.ORBE_TAILLE / 2)

    def test_eclosion_au_changement_d_etat_puis_plus_rien(self):
        for theme in THEMES_TESTES:
            with self.subTest(theme=theme):
                module, app, tmp = monter(theme, etat="ecoute")
                self.addCleanup(tmp.cleanup)
                module.lire_etat = lambda chemin=None: {
                    "etat": "repos", "transcription": "", "erreur": "",
                    "langue": "", "present": True, "agents": {}}
                app.rafraichir()
                self.assertTrue(app._animateur.en_cours("orbe"))
                app.fenetre.avancer(1000)
                self.assertFalse(app._animateur.en_cours())

    def test_reglage_animations_false(self):
        for theme in THEMES_TESTES:
            with self.subTest(theme=theme):
                module, app, tmp = monter(theme, etat="reflexion",
                                          animations=False)
                self.addCleanup(tmp.cleanup)
                self.assertFalse(app._animateur.actif)
                avant = {k: dict(v) for k, v in app.canvas_orbe.objets.items()}
                planifies = []
                app.fenetre.after = (lambda delai, f=None, *a:
                                     planifies.append(delai))
                app._animer_orbe()  # réflexion : pas de pulsation.
                self.assertEqual(planifies, [module.PAS_REPOS_MS])
                self.assertEqual(avant, app.canvas_orbe.objets)
                module.lire_etat = lambda chemin=None: {
                    "etat": "repos", "transcription": "", "erreur": "",
                    "langue": "", "present": True, "agents": {}}
                app.rafraichir()
                self.assertFalse(app._animateur.en_cours())

    def test_reglage_lu_dans_la_configuration(self):
        with tempfile.TemporaryDirectory() as dossier:
            (Path(dossier) / "config").mkdir()
            (Path(dossier) / "config" / "config.toml").write_text(
                "[app]\nanimations = false\ntableau_de_bord = \"non\"\n",
                encoding="utf-8")
            config = self.module.charger_config_app(Path(dossier))
        self.assertIs(config["animations"], False)
        self.assertIs(config["tableau_de_bord"], False)
        self.assertIs(self.module.DEFAUTS["animations"], True)
        self.assertIs(self.module.valeur_booleenne("??", True), True)

    def test_nouvel_element_surligne_mais_pas_au_lancement(self):
        _module, app, tmp = monter("centre_de_commande")
        self.addCleanup(tmp.cleanup)
        note = {"id": 1, "texte": "a", "cree_le": ""}
        def surlignage():
            return any(isinstance(cle, tuple) and cle[0] == "surligne"
                       for cle in app._animateur._animations)

        app._rafraichir_connaissances([note])  # premier affichage
        self.assertFalse(surlignage())
        app._rafraichir_connaissances([dict(note, id=2, texte="b"), note])
        self.assertTrue(surlignage())
        app.fenetre.avancer(1000)
        self.assertFalse(surlignage())

    def test_aucune_animation_au_repos(self):
        _module, app, tmp = monter()
        self.addCleanup(tmp.cleanup)
        app.fenetre.avancer(2000)
        self.assertFalse(app._animateur.en_cours())
        self.assertIsNone(app._animateur._planifie)


# ---------------------------------------------------------------------------
# 5. Agents
# ---------------------------------------------------------------------------

class Agents(unittest.TestCase):
    def setUp(self):
        self.module, _ = faux.charger_app(nom="app_db_agents")

    def test_etats_selon_la_boucle(self):
        f = self.module.etats_agents
        arretee = f({"etat": "arrete"}, [], [])
        self.assertEqual([arretee[a] for a in ("cerveau", "voix",
                                               "navigateur")],
                         ["erreur"] * 3)
        self.assertEqual(arretee["notes"], "veille")
        reflexion = f({"etat": "reflexion"}, [], [])
        self.assertEqual((reflexion["cerveau"], reflexion["voix"]),
                         ("actif", "veille"))
        self.assertEqual(f({"etat": "reponse"}, [], [])["voix"], "actif")
        micro = f({"etat": "erreur", "erreur": "Micro indisponible"}, [], [])
        self.assertEqual((micro["voix"], micro["cerveau"]),
                         ("erreur", "veille"))
        self.assertEqual(f({"etat": "erreur", "erreur": "x"}, [], [])
                         ["cerveau"], "erreur")
        signale = f({"etat": "repos", "agents": {"navigateur": "actif",
                                                  "cerveau": "erreur"}},
                    [], [])
        self.assertEqual((signale["navigateur"], signale["cerveau"]),
                         ("actif", "erreur"))

    def test_minuteurs_recherches_notes(self):
        f = self.module.etats_agents
        etats = f({"etat": "repos"}, [{"pause_s": None}],
                  [{"statut": "en_cours"}], notes_ok=False)
        self.assertEqual((etats["minuteurs"], etats["recherches"],
                          etats["notes"]), ("actif", "actif", "erreur"))
        self.assertEqual(f({"etat": "repos"}, [], [{"statut": "prete"}])
                         ["recherches"], "veille")

    def test_notes_illisibles(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "c.json"
            self.assertTrue(self.module.notes_lisibles(chemin))  # absent
            chemin.write_text("{cassé", encoding="utf-8")
            self.assertFalse(self.module.notes_lisibles(chemin))

    def test_panneau_dans_les_deux_themes(self):
        for theme in THEMES_TESTES:
            with self.subTest(theme=theme):
                module, app, tmp = monter(theme)
                self.addCleanup(tmp.cleanup)
                self.assertEqual(list(app._lignes_agents), list(module.AGENTS))
                app._rafraichir_agents({"cerveau": "actif", "voix": "erreur"})
                point, nom, statut = app._lignes_agents["cerveau"]
                self.assertEqual(nom.options["text"], "Brain")
                self.assertEqual(statut.options["text"], "active")
                self.assertEqual(point.options["text_color"],
                                 module.couleur_etat("actif"))
                point, _nom, statut = app._lignes_agents["voix"]
                self.assertEqual(statut.options["text"], "error")
                self.assertEqual(point.options["text_color"],
                                 module.couleur_etat("erreur"))
                self.assertEqual(app._lignes_agents["notes"][2]
                                 .options["text"], "idle")

    def test_la_boucle_signale_ses_agents(self):
        import boucle_voix
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "hud-state.json"
            with mock.patch.object(boucle_voix, "FICHIER_ETAT_HUD", chemin), \
                    mock.patch.dict(boucle_voix.AGENTS_HUD, clear=True):
                boucle_voix.noter_agents(navigateur="actif", cerveau="??")
                boucle_voix.ecrire_etat_hud("repos")
                donnees = json.loads(chemin.read_text(encoding="utf-8"))
        self.assertEqual(donnees["agents"], {"navigateur": "actif"})
        module = self.module
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "hud-state.json"
            chemin.write_text(json.dumps(donnees), encoding="utf-8")
            self.assertEqual(module.lire_etat(chemin)["agents"],
                             {"navigateur": "actif"})


# ---------------------------------------------------------------------------
# 6. Conversations et colonne du tableau de bord
# ---------------------------------------------------------------------------

JOURS = [{"date": "2026-11-28", "chemin": Path("a.jsonl"), "messages": 4},
         {"date": "2026-11-27", "chemin": Path("b.jsonl"), "messages": 1},
         {"date": "Ancien journal", "chemin": Path("c.jsonl"),
          "messages": 2}]


class Conversations(unittest.TestCase):
    def test_formater_les_jours(self):
        module, _ = faux.charger_app(nom="app_db_jours")
        self.assertEqual(module.formater_jours(JOURS, "en"), (
            ("sam. 28 nov. 2026", "4 message(s)"),
            ("ven. 27 nov. 2026", "1 message(s)"),
            ("Old log", "2 message(s)")))

    def test_liste_cliquable_pour_relire(self):
        for theme in THEMES_TESTES:
            with self.subTest(theme=theme):
                module, app, tmp = monter(theme)
                self.addCleanup(tmp.cleanup)
                module.lister_jours = lambda racine=None: list(JOURS)
                lus = []
                module.lire_conversation = lambda chemin=None: (
                    lus.append(chemin) or [])
                app._rafraichir_conversations(JOURS)
                boutons = app.conteneur_conversations.winfo_children()
                self.assertEqual(len(boutons), 3)
                self.assertIn("4 message(s)", boutons[0].options["text"])
                boutons[1].options["command"]()
                self.assertEqual(app._historique["courant"], JOURS[1])
                self.assertEqual(lus[-1], Path("b.jsonl"))

    def test_vide(self):
        _module, app, tmp = monter()
        self.addCleanup(tmp.cleanup)
        app._rafraichir_conversations([])
        vide, = app.conteneur_conversations.winfo_children()
        self.assertEqual(vide.options["text"], "No saved conversation.")

    def test_relue_quand_le_journal_grandit_seulement(self):
        module, app, tmp = monter()
        self.addCleanup(tmp.cleanup)
        lectures = []
        module.lister_jours = lambda racine=None: lectures.append(1) or []
        entrees = []
        module.lire_conversation = lambda chemin=None: list(entrees)
        app._compte_du_jour, app._jours_lus_a = 0, 10 ** 12
        app.rafraichir()
        app.rafraichir()
        self.assertEqual(lectures, [])
        entrees.append({"role": "user", "texte": "x", "heure": ""})
        app.rafraichir()
        self.assertEqual(lectures, [1])


class ColonneDuTableauDeBord(unittest.TestCase):
    def test_masquee_a_900_px_visible_des_1100(self):
        module, app, tmp = monter()
        self.addCleanup(tmp.cleanup)
        self.assertFalse(app._tableau_visible)  # fenêtre de 900 px.
        app.fenetre.largeur = module.LARGEUR_TABLEAU_BORD
        app._maj_tableau_de_bord()
        self.assertTrue(app._tableau_visible)

    def test_reglage_et_menu(self):
        module, app, tmp = monter(tableau_de_bord=False)
        self.addCleanup(tmp.cleanup)
        app.fenetre.largeur = 1400
        app._maj_tableau_de_bord()
        self.assertFalse(app._tableau_visible)
        app.basculer_tableau_de_bord()
        self.assertTrue(app._tableau_visible)
        app.basculer_tableau_de_bord()
        self.assertFalse(app._tableau_visible)

    def test_panneaux_existants_et_tailles_u1_inchanges(self):
        for theme in THEMES_TESTES:
            with self.subTest(theme=theme):
                module, app, tmp = monter(theme)
                self.addCleanup(tmp.cleanup)
                for nom in ("panneau_minuteurs", "panneau_recherches",
                            "panneau_connaissances"):
                    self.assertTrue(hasattr(app, nom))
                self.assertEqual(module.ORBE_TAILLE, 116)
                self.assertEqual(app.canvas_orbe.options["width"], 116)
                self.assertEqual(module.HAUTEUR_BOUTON_PRINCIPAL, 54)
                self.assertEqual(app.panneau_agents.options.get(
                    "border_width"), 1 if theme == "centre_de_commande"
                    else None)
                self.assertEqual(app.titre_agents.options["text"],
                                 "AGENTS" if theme == "centre_de_commande"
                                 else "Agents")


if __name__ == "__main__":
    unittest.main()
