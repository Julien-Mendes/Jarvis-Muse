"""Lot esthétique (suite de U2) — thème « centre_de_commande ».

Bleu nuit / cyan d'après ref-visuel/jarvis-exemple.png : orbe en globe
filaire, panneaux bordés à titres en capitales (Bahnschrift), statuts
colorés, jauges circulaires des minuteurs, pastille d'état, bouton micro en
pilule lumineuse, tuiles pour les listes. Vérifie aussi que or_et_nuit reste
le défaut et que les thèmes classiques n'ont aucun style, que les tailles U1
ne bougent pas, et que le défilement U2 marche avec ce thème. Faux
CustomTkinter (_faux_ctk.py) : on vérifie ce qui est demandé à Tk, pas le
rendu — un aperçu réel a été regardé à l'œil.
"""
import tempfile
import unittest
from datetime import datetime, timedelta

import _faux_ctk as faux
from test_u2_defilement import Banc

THEME = "centre_de_commande"


def monter(theme=THEME, etat="repos"):
    module, ctk = faux.charger_app(nom="app_commande")
    tmp = tempfile.TemporaryDirectory()
    module.ecrire_ptt = lambda *a, **k: None
    module.charger_recherches = lambda chemin=None: []
    module.charger_notes = lambda chemin=None: []
    entrees = []
    app = faux.creer_application(module, tmp.name, entrees, theme=theme)
    module.lire_etat = lambda chemin=None: {
        "etat": etat, "transcription": "", "erreur": "", "langue": "",
        "present": True}
    return module, app, entrees, tmp


class Palette(unittest.TestCase):
    def setUp(self):
        self.app, _ = faux.charger_app()

    def test_defaut_inchange_et_style_reserve_au_nouveau_theme(self):
        self.assertEqual(self.app.THEME_DEFAUT, "or_et_nuit")
        self.assertEqual(self.app.DEFAUTS["theme"], "or_et_nuit")
        for nom in ("jarvis_bleu", "or_et_nuit", "clair_studio"):
            self.assertIsNone(self.app.THEMES[nom]["style"], nom)
        self.assertEqual(self.app.nom_theme(" Centre_De_Commande "), THEME)

    def test_style_complet_et_couleurs_bien_formees(self):
        style = self.app.THEMES[THEME]["style"]
        self.assertEqual(style["orbe"], "globe")
        self.assertTrue(style["titres_majuscules"])
        self.assertEqual(style["police_titre"], "Bahnschrift")
        for cle in ("bordure_panneau", "titre_panneau", "bordure_bulle_jarvis",
                    "bordure_bulle_utilisateur", "micro_fond", "jauge_fond"):
            self.assertRegex(style[cle], r"^#[0-9a-f]{6}$", cle)
        self.assertEqual(set(style["statut"]),
                         {"ok", "actif", "attente", "erreur", "inactif"})
        self.assertEqual(set(self.app.STATUT_DES_ETATS), set(self.app.ETATS))
        for couleur in style["statut"].values():
            self.assertRegex(couleur, r"^#[0-9a-f]{6}$")

    def test_bleu_nuit_et_cyan(self):
        p = self.app.THEMES[THEME]
        self.assertEqual(p["mode"], "dark")
        r, g, b = (int(p["fond"][i:i + 2], 16) for i in (1, 3, 5))
        self.assertTrue(b > r and b > g and max(r, g, b) < 40, p["fond"])
        r, g, b = (int(p["accent"][i:i + 2], 16) for i in (1, 3, 5))
        self.assertTrue(g > 180 and b > 180 and r < 80, p["accent"])

    def test_appliquer_un_theme_classique_efface_le_style(self):
        self.app.appliquer_theme(THEME)
        self.assertEqual(self.app.STYLE["orbe"], "globe")
        self.app.appliquer_theme("or_et_nuit")
        self.assertEqual(self.app.STYLE, {})
        self.assertEqual(self.app.titre_affiche("Minuteurs"), "Minuteurs")
        self.assertEqual(self.app.options_panneau(), {})


class Globe(unittest.TestCase):
    def setUp(self):
        self.app, _ = faux.charger_app()

    def test_geometrie_dans_le_canevas_de_116_px(self):
        self.assertEqual(self.app.ORBE_TAILLE, 116)
        for echelle in (0.93, 1.0, 1.07):
            for angle in (0.0, 0.6, 1.7, 3.1):
                geo = self.app.geometrie_globe(echelle, angle)
                boites = ([geo[c] for c in ("halo", "sphere", "coeur",
                                            "orbite", "satellite")]
                          + geo["meridiens"] + geo["paralleles"])
                for x0, y0, x1, y1 in boites:
                    self.assertGreaterEqual(min(x0, y0), 0)
                    self.assertLessEqual(max(x1, y1), 116)
                    self.assertLessEqual(x0, x1)
                    self.assertLessEqual(y0, y1)

    def test_les_meridiens_tournent(self):
        a = self.app.geometrie_globe(1.0, 0.0)["meridiens"]
        b = self.app.geometrie_globe(1.0, 0.5)["meridiens"]
        self.assertNotEqual(a, b)
        self.assertEqual(len(a), self.app.GLOBE_MERIDIENS)

    def test_globe_aux_couleurs_de_l_etat_et_pas_de_dessin_au_repos(self):
        module, app, _, tmp = monter()
        self.addCleanup(tmp.cleanup)
        self.assertIsNotNone(app._globe)
        objets = app.canvas_orbe.objets
        couleur = module.THEMES[THEME]["orbe"][app.etat_affiche]
        self.assertEqual(objets[app._orbe_coeur]["fill"], couleur)
        self.assertEqual(objets[app._orbe_milieu]["outline"], couleur)
        self.assertEqual(
            len(objets), 2 + len(module.GLOBE_PARALLELES)
            + module.GLOBE_MERIDIENS + 3)  # créé une fois, jamais recréé
        # Au repos (période nulle) : _animer_orbe ne redessine rien.
        avant = {k: dict(v) for k, v in objets.items()}
        app.etat_affiche = "repos"
        app._animer_orbe()
        self.assertEqual(avant, app.canvas_orbe.objets)
        # En réflexion : le globe tourne.
        app.etat_affiche = "reflexion"
        app._animer_orbe()
        self.assertEqual(len(app.canvas_orbe.objets), len(avant))
        self.assertEqual(objets[app._orbe_coeur]["fill"],
                         module.THEMES[THEME]["orbe"]["reflexion"])
        self.assertNotEqual(objets[app._orbe_coeur], avant[app._orbe_coeur])

    def test_themes_classiques_gardent_les_trois_disques(self):
        module, app, _, tmp = monter("or_et_nuit")
        self.addCleanup(tmp.cleanup)
        self.assertIsNone(app._globe)
        self.assertEqual(len(app.canvas_orbe.objets), 3)


class Fenetre(unittest.TestCase):
    def setUp(self):
        self.module, self.app, self.entrees, tmp = monter()
        self.addCleanup(tmp.cleanup)
        self.p = self.module.THEMES[THEME]
        self.s = self.p["style"]

    def test_panneaux_bordes_et_titres_en_capitales(self):
        for nom in ("minuteurs", "recherches", "connaissances"):
            panneau = getattr(self.app, f"panneau_{nom}").options
            self.assertEqual(panneau["border_width"], 1)
            self.assertEqual(panneau["border_color"], self.s["bordure_panneau"])
            titre = getattr(self.app, f"titre_{nom}").options
            self.assertEqual(titre["text"], self.app.t(nom).upper())
            self.assertEqual(titre["text_color"], self.s["titre_panneau"])
            self.assertEqual(titre["font"].family, "Bahnschrift")
            self.assertEqual((titre["font"].size, titre["font"].weight),
                             (14, "bold"))

    def test_tailles_u1_inchangees_police_des_titres(self):
        etat = self.app.texte_etat.options["font"]
        self.assertEqual((etat.family, etat.size, etat.weight),
                         ("Bahnschrift", 20, "bold"))
        horloge = self.app.texte_horloge.options["font"]
        self.assertEqual((horloge.size, horloge.weight), (24, "bold"))
        self.assertEqual(self.app.texte_detail.options["font"].family,
                         "Segoe UI")  # le corps reste en Segoe UI
        self.assertEqual((self.app.canvas_orbe.options["width"],
                          self.app.canvas_orbe.options["height"]), (116, 116))
        self.assertEqual(self.app.bouton_micro.options["height"], 54)
        self.assertEqual(self.app.bouton_micro.options["font"].size, 16)

    def test_pilule_micro_lumineuse(self):
        micro = self.app.bouton_micro.options
        self.assertEqual(micro["fg_color"], self.s["micro_fond"])
        self.assertEqual(micro["border_color"], self.p["accent"])
        self.assertEqual(micro["border_width"], 2)
        self.assertEqual(micro["text_color"], self.p["accent"])
        self.assertEqual(micro["text"], self.app.t("micro_repos").upper())
        self.app._micro_presse()
        self.assertEqual(micro["fg_color"], self.p["orbe"]["ecoute"])
        self.assertEqual(micro["text_color"], self.p["texte_sur_accent"])
        self.app._micro_relache()
        self.assertEqual(micro["fg_color"], self.s["micro_fond"])
        self.assertEqual(micro["text_color"], self.p["accent"])

    def test_pastille_d_etat_coloree(self):
        pastille = self.app.pastille_etat.options
        self.assertEqual(pastille["text"], "● ONLINE")  # état « repos »
        self.assertEqual(pastille["text_color"], self.s["statut"]["ok"])
        for etat, cle in (("reflexion", "attente"), ("erreur", "erreur"),
                          ("ecoute", "actif"), ("repos", "ok")):
            self.module.lire_etat = lambda chemin=None, e=etat: {
                "etat": e, "transcription": "", "erreur": "", "langue": "",
                "present": True}
            self.app.rafraichir()
            self.assertEqual(pastille["text"], self.app.t(f"pastille_{etat}"))
            self.assertEqual(pastille["text_color"], self.s["statut"][cle])

    def test_bulles_bordees(self):
        self.entrees.extend([faux.entree(0, "user"),
                             faux.entree(1, "assistant")])
        self.app.rafraichir()
        utilisateur, jarvis = self.app.zone_conversation.winfo_children()
        self.assertEqual(utilisateur.options["border_color"],
                         self.s["bordure_bulle_utilisateur"])
        self.assertEqual(jarvis.options["border_color"],
                         self.s["bordure_bulle_jarvis"])
        self.assertEqual(jarvis.options["fg_color"], self.p["bulle_jarvis"])

    def test_statuts_des_recherches_colores(self):
        couleurs = []
        for tache in ({"id": 3, "question": "a", "statut": "prete"},
                      {"id": 2, "question": "b", "statut": "en_cours",
                       "demarree_le": "x"},
                      {"id": 1, "question": "c", "statut": "en_cours"},
                      {"id": 0, "question": "d", "statut": "echec"}):
            couleurs.append(self.s["statut"][
                self.module.statut_recherche(tache)])
        self.assertEqual(couleurs, [self.s["statut"][c] for c in
                                    ("ok", "actif", "attente", "erreur")])
        taches = [{"id": 3, "question": "vélos", "statut": "prete"}]
        self.app._rafraichir_recherches(taches)
        tuile, = self.app.conteneur_recherches.winfo_children()
        point, bouton = tuile.winfo_children()
        self.assertEqual(tuile.options["border_color"],
                         self.s["bordure_panneau"])
        self.assertEqual(point.options["text_color"], self.s["statut"]["ok"])
        self.assertIn("vélos", bouton.options["text"])
        bouton.options["command"]  # ouvre le détail, comme en classique.

    def test_jauges_des_minuteurs(self):
        ref = datetime(2026, 11, 26, 12, 0, tzinfo=self.module.FUSEAU)

        def minuteur(reste_s, total_s):
            return {"due": ref + timedelta(seconds=reste_s), "label": "pâtes",
                    "kind": "timer", "total_s": total_s}

        jauge = self.module.etat_jauge_minuteur
        self.assertEqual(jauge(minuteur(300, 600), ref), (0.5, "actif"))
        self.assertEqual(jauge(minuteur(30, 600), ref)[1], "attente")
        self.assertEqual(jauge(minuteur(-5, 600), ref), (0.0, "erreur"))
        self.assertEqual(jauge(minuteur(300, None), ref), (1.0, "actif"))

        self.app._rafraichir_minuteurs([minuteur(300, 600)], ref)
        tuile, = self.app.conteneur_minuteurs.winfo_children()
        canevas, etiquette = tuile.winfo_children()
        self.assertEqual(etiquette.options["text"], "pâtes: in 5 min")
        arcs = [o for o in canevas.objets.values() if o.get("arc")]
        self.assertEqual(arcs[0]["extent"], -180.0)  # moitié restante
        self.assertEqual(arcs[0]["outline"], self.s["statut"]["actif"])
        # La seconde suivante : mise à jour SUR PLACE (rien n'est recréé).
        self.app._rafraichir_minuteurs([minuteur(30, 600)], ref)
        self.assertIs(self.app.conteneur_minuteurs.winfo_children()[0], tuile)
        self.assertEqual(etiquette.options["text"], "pâtes: in 30 s")
        arcs = [o for o in canevas.objets.values() if o.get("arc")]
        self.assertEqual(arcs[0]["outline"], self.s["statut"]["attente"])
        # Échu : texte rouge.
        self.app._rafraichir_minuteurs([minuteur(-1, 600)], ref)
        self.assertEqual(etiquette.options["text_color"],
                         self.s["statut"]["erreur"])
        # Plus aucun minuteur : message habituel.
        self.app._rafraichir_minuteurs([], ref)
        vide, = self.app.conteneur_minuteurs.winfo_children()
        self.assertEqual(vide.options["text"], "No timers running.")

    def test_tuiles_des_notes(self):
        self.app._cle_connaissances = ()
        self.app._rafraichir_connaissances([
            {"id": 1, "texte": "Budget mini-PC : 600 €",
             "cree_le": "2026-11-26T10:00:00-05:00"}])
        tuile, = self.app.conteneur_connaissances.winfo_children()
        self.assertEqual(tuile.options["border_color"],
                         self.s["bordure_panneau"])
        texte, date, bouton = tuile.winfo_children()
        self.assertEqual(date.options["text"], "Nov 26, 2026")
        self.assertEqual(date.options["text_color"], self.s["titre_panneau"])


class DefilementAvecLeTheme(unittest.TestCase):
    """U2 : le défilement de la conversation marche aussi avec ce thème."""

    def test_suit_les_nouveaux_messages_et_respecte_la_lecture(self):
        for modele in ("remplace", "cumule"):
            with self.subTest(modele=modele):
                banc = Banc.__new__(Banc)
                banc.module, banc.ctk = faux.charger_app(modele)
                banc.tmp = tempfile.TemporaryDirectory()
                self.addCleanup(banc.tmp.cleanup)
                banc.module.charger_recherches = lambda chemin=None: []
                banc.module.charger_notes = lambda chemin=None: []
                banc.entrees = []
                banc.app = faux.creer_application(
                    banc.module, banc.tmp.name, banc.entrees, theme=THEME)
                banc.zone = banc.app.zone_conversation
                banc.canvas = banc.zone._parent_canvas
                banc.racine = banc.app.fenetre
                banc.remplir(40)
                self.assertTrue(banc.region_a_jour())
                self.assertTrue(banc.en_bas())
                banc.canvas.yview_moveto(0.2)  # Julien remonte lire.
                haut = banc.canvas.haut
                banc.tick(2)
                self.assertEqual(banc.canvas.haut, haut)


if __name__ == "__main__":
    unittest.main()
