"""Lot U2 — système de thèmes de l'application (scripts/app.py).

Trois palettes (jarvis_bleu = repli, or_et_nuit = défaut, clair_studio),
réglage [app] theme lu avec config_jarvis, repli garanti sur jarvis_bleu.
Les widgets sont des faux (voir _faux_ctk.py) : on vérifie les couleurs
demandées, pas le rendu réel — à confirmer à l'œil à l'essai.
"""
import io
import tempfile
import tomllib
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import _faux_ctk as faux

EXEMPLE = faux.RACINE / "config" / "config.example.toml"
THEMES_ATTENDUS = {"jarvis_bleu", "or_et_nuit", "clair_studio"}
CLES_OPTIONNELLES = {"fond_fenetre", "champ_fond", "champ_bordure",
                     "champ_texte", "champ_texte_indice"}


def luminance(hexa: str) -> float:
    canaux = [int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    canaux = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
              for c in canaux]
    return 0.2126 * canaux[0] + 0.7152 * canaux[1] + 0.0722 * canaux[2]


def contraste(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def ecrire(dossier: Path, nom: str, contenu: str) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / nom).write_text(contenu, encoding="utf-8")


class Palettes(unittest.TestCase):
    def setUp(self):
        self.app, _ = faux.charger_app()

    def test_trois_themes_et_valeurs_par_defaut(self):
        self.assertEqual(set(self.app.THEMES), THEMES_ATTENDUS)
        self.assertEqual(self.app.THEME_REPLI, "jarvis_bleu")
        self.assertEqual(self.app.THEME_DEFAUT, "or_et_nuit")
        self.assertEqual(self.app.DEFAUTS["theme"], "or_et_nuit")

    def test_memes_cles_partout_et_couleurs_bien_formees(self):
        modele = set(self.app.THEMES["jarvis_bleu"])
        for nom, palette in self.app.THEMES.items():
            self.assertEqual(set(palette), modele, nom)
            self.assertEqual(set(palette["orbe"]), set(self.app.ETATS), nom)
            for cle, valeur in palette.items():
                if cle == "mode":
                    self.assertIn(valeur, ("dark", "light"))
                elif cle == "orbe":
                    for couleur in valeur.values():
                        self.assertRegex(couleur, r"^#[0-9a-f]{6}$")
                elif valeur is None:
                    self.assertIn(cle, CLES_OPTIONNELLES, f"{nom}.{cle}")
                else:
                    self.assertRegex(valeur, r"^#[0-9a-f]{6}$", f"{nom}.{cle}")

    def test_couleurs_imposees_par_julien(self):
        nuit = self.app.THEMES["or_et_nuit"]
        self.assertEqual(nuit["fond"], "#09090b")
        self.assertEqual(nuit["accent"], "#e0a82e")
        clair = self.app.THEMES["clair_studio"]
        self.assertEqual((clair["fond"], clair["panneau"], clair["accent"]),
                         ("#f4f6f9", "#ffffff", "#1d6fd6"))
        self.assertEqual(clair["mode"], "light")

    def test_jarvis_bleu_garde_les_couleurs_d_origine(self):
        bleu = self.app.THEMES["jarvis_bleu"]
        origine = {
            "fond": "#0a0a0f", "panneau": "#14141d",
            "bulle_jarvis": "#1a1a26", "bulle_utilisateur": "#1a3a5c",
            "texte": "#e0e0e0", "texte_faible": "#888888",
            "accent": "#4a9eff", "accent_survol": "#3a7bd5",
            "texte_sur_accent": "#ffffff", "interrompre_texte": "#e07878",
            "interrompre_bordure": "#7a3a3a", "interrompre_survol": "#2a1a1a",
            "survol_liste": "#23232f"}
        for cle, valeur in origine.items():
            self.assertEqual(bleu[cle], valeur, cle)
        self.assertEqual(bleu["orbe"], {
            "repos": "#5b7a99", "ecoute": "#2a6cb8", "reflexion": "#c9a227",
            "reponse": "#27c96a", "erreur": "#c0392b", "arrete": "#666666"})
        # Aucune option facultative : CustomTkinter garde ses couleurs.
        for cle in CLES_OPTIONNELLES:
            self.assertIsNone(bleu[cle], cle)

    def test_au_simple_import_ce_sont_les_couleurs_du_repli(self):
        self.assertEqual(self.app.THEME_ACTIF, "jarvis_bleu")
        self.assertEqual(self.app.COULEUR_FOND, "#0a0a0f")
        self.assertEqual(self.app.ETATS["ecoute"][1], "#2a6cb8")
        self.assertEqual(self.app.OPTIONS_CHAMP, {})

    def test_lisibilite_des_nouveaux_themes(self):
        for nom in ("or_et_nuit", "clair_studio"):
            p = self.app.THEMES[nom]
            for surface in ("fond", "panneau", "bulle_jarvis",
                            "bulle_utilisateur"):
                self.assertGreaterEqual(
                    contraste(p["texte"], p[surface]), 7.0,
                    f"{nom} : texte sur {surface}")
                self.assertGreaterEqual(
                    contraste(p["texte_faible"], p[surface]), 4.5,
                    f"{nom} : texte faible sur {surface}")
            self.assertGreaterEqual(
                contraste(p["texte_sur_accent"], p["accent"]), 4.5, nom)
            self.assertGreaterEqual(contraste(p["accent"], p["fond"]), 3.0, nom)
            self.assertGreaterEqual(
                contraste(p["interrompre_texte"], p["panneau"]), 4.5, nom)
            for etat, couleur in p["orbe"].items():
                self.assertGreaterEqual(
                    contraste(couleur, p["panneau"]), 2.4, f"{nom} orbe {etat}")

    def test_barre_de_defilement_visible_dans_tous_les_themes(self):
        for nom, p in self.app.THEMES.items():
            self.assertGreaterEqual(
                contraste(p["barre_defilement"], p["fond"]), 3.0,
                f"{nom} : barre invisible sur le fond")
            self.assertGreaterEqual(
                contraste(p["barre_defilement_survol"], p["fond"]), 3.0, nom)

    def test_fondu_de_l_orbe(self):
        self.assertEqual(self.app._fondre("#c9a227", "#000000", 0.6),
                         self.app._assombrir("#c9a227", 0.6))
        self.assertEqual(self.app._fondre("#1d6fd6", "#ffffff", 1.0), "#1d6fd6")
        self.assertEqual(self.app._fondre("#1d6fd6", "#ffffff", 0.0), "#ffffff")
        self.assertEqual(self.app._fondre("n'importe quoi", "#000000", 0.5),
                         "n'importe quoi")


class ChoixDuTheme(unittest.TestCase):
    def setUp(self):
        self.app, self.ctk = faux.charger_app()

    def test_appliquer_regle_couleurs_orbe_et_champs(self):
        self.assertEqual(self.app.appliquer_theme("or_et_nuit"), "or_et_nuit")
        self.assertEqual(self.app.COULEUR_FOND, "#09090b")
        self.assertEqual(self.app.COULEUR_ACCENT, "#e0a82e")
        self.assertEqual(self.app.COULEUR_TEXTE_SUR_ACCENT, "#09090b")
        self.assertEqual(self.app.ETATS["ecoute"][1], "#ffcf5c")
        self.assertEqual(self.app.ETATS["ecoute"][0], "Écoute…")  # texte gardé
        self.assertEqual(self.app.ETATS["ecoute"][2], 1.5)         # période gardée
        self.assertEqual(self.app.OPTIONS_CHAMP["fg_color"], "#18181e")
        self.assertEqual(self.app.appliquer_theme("jarvis_bleu"), "jarvis_bleu")
        self.assertEqual(self.app.COULEUR_FOND, "#0a0a0f")
        self.assertEqual(self.app.ETATS["ecoute"][1], "#2a6cb8")
        self.assertEqual(self.app.OPTIONS_CHAMP, {})

    def test_repli_garanti_sur_jarvis_bleu(self):
        for invalide in ("violet", "", "   ", None, 3, ["or_et_nuit"], {}):
            with self.subTest(valeur=invalide), redirect_stderr(io.StringIO()):
                self.assertEqual(self.app.appliquer_theme(invalide),
                                 "jarvis_bleu")
                self.assertEqual(self.app.THEME_ACTIF, "jarvis_bleu")
                self.assertEqual(self.app.COULEUR_FOND, "#0a0a0f")

    def test_nom_tolerant_a_la_casse_et_aux_espaces(self):
        self.assertEqual(self.app.nom_theme(" Or_Et_Nuit "), "or_et_nuit")
        self.assertEqual(self.app.nom_theme("CLAIR_STUDIO"), "clair_studio")

    def test_theme_inconnu_prevenu_sur_la_sortie_d_erreur(self):
        erreur = io.StringIO()
        with redirect_stderr(erreur):
            self.app.appliquer_theme("violet")
        self.assertIn("violet", erreur.getvalue())


class LectureDeLaConfiguration(unittest.TestCase):
    """Contrat T1 : la clé [app] theme est lue, via config_jarvis."""

    def setUp(self):
        self.app, _ = faux.charger_app()
        self.tmp = tempfile.TemporaryDirectory()
        self.racine = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def theme(self) -> str:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return self.app.charger_config_app(self.racine)["theme"]

    def test_la_cle_de_l_exemple_est_reliee_et_valide(self):
        exemple = tomllib.loads(EXEMPLE.read_text(encoding="utf-8"))
        self.assertIn("theme", exemple["app"])
        self.assertIn(exemple["app"]["theme"], THEMES_ATTENDUS)
        self.assertEqual(exemple["app"]["theme"], self.app.THEME_DEFAUT)
        for cle in exemple["app"]:
            self.assertIn(cle, self.app.DEFAUTS, f"[app] {cle} non lue")
        texte = EXEMPLE.read_text(encoding="utf-8")
        for nom in THEMES_ATTENDUS:
            self.assertIn(nom, texte, f"{nom} non documenté dans l'exemple")

    def test_defaut_sans_configuration(self):
        self.assertEqual(self.theme(), "or_et_nuit")

    def test_defaut_avec_l_exemple_du_projet(self):
        ecrire(self.racine / "config", "config.example.toml",
               EXEMPLE.read_text(encoding="utf-8"))
        self.assertEqual(self.theme(), "or_et_nuit")

    def test_theme_de_config_toml(self):
        ecrire(self.racine / "config", "config.toml",
               '[app]\ntheme = "clair_studio"\n')
        self.assertEqual(self.theme(), "clair_studio")

    def test_les_couches_de_config_jarvis_s_appliquent(self):
        ecrire(self.racine / "config", "config.example.toml",
               '[app]\ntheme = "or_et_nuit"\n')
        ecrire(self.racine / "config", "config.toml",
               '[app]\ntheme = "clair_studio"\n')
        ecrire(self.racine / "config", "config.local.toml",
               '[app]\ntheme = "jarvis_bleu"\n')
        self.assertEqual(self.theme(), "jarvis_bleu")  # config.local gagne

    def test_theme_inconnu_ou_mal_type_donne_le_repli(self):
        for ligne in ('theme = "violet"', "theme = 3", 'theme = ["or_et_nuit"]',
                      'theme = ""'):
            with self.subTest(ligne=ligne):
                ecrire(self.racine / "config", "config.toml", f"[app]\n{ligne}\n")
                self.assertEqual(self.theme(), "jarvis_bleu")

    def test_configuration_illisible_donne_le_repli(self):
        ecrire(self.racine / "config", "config.toml", "[app\ntheme = oups")
        self.assertEqual(self.theme(), "jarvis_bleu")

    def test_les_autres_reglages_de_l_application_restent_lus(self):
        ecrire(self.racine / "config", "config.toml",
               '[app]\ntheme = "clair_studio"\nlargeur = 1000\n')
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            config = self.app.charger_config_app(self.racine)
        self.assertEqual(config["largeur"], 1000)
        self.assertEqual(config["theme"], "clair_studio")

    def test_verifier_affiche_le_theme(self):
        self.app.RACINE = self.racine  # verifier() crée data/ : pas dans le dépôt
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            self.app.verifier({"theme": "clair_studio", "langue": "en"})
        self.assertIn("thème : clair_studio", sortie.getvalue())


class ApplicationThemee(unittest.TestCase):
    def monter(self, theme):
        module, ctk = faux.charger_app()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        module.ecrire_ptt = lambda *a, **k: None  # pas d'écriture dans data/
        entrees = []
        app = faux.creer_application(module, tmp.name, entrees, theme=theme)
        return module, ctk, app, entrees

    def test_chaque_theme_colore_tous_les_elements(self):
        for nom in THEMES_ATTENDUS:
            with self.subTest(theme=nom):
                module, ctk, app, entrees = self.monter(nom)
                p = module.THEMES[nom]
                self.assertEqual(app.theme, nom)
                self.assertEqual(ctk.modes[-1], p["mode"])
                # Fenêtre, en-tête, orbe, textes
                if p["fond_fenetre"]:
                    self.assertEqual(app.fenetre.options["fg_color"],
                                     p["fond_fenetre"])
                else:
                    self.assertNotIn("fg_color", app.fenetre.options)
                self.assertEqual(app.entete.options["fg_color"], p["panneau"])
                self.assertEqual(app.canvas_orbe.options["bg"], p["panneau"])
                self.assertEqual(app.texte_etat.options["text_color"], p["texte"])
                self.assertEqual(app.texte_horloge.options["text_color"],
                                 p["texte"])
                self.assertEqual(app.texte_detail.options["text_color"],
                                 p["texte_faible"])
                # Panneaux et zone de conversation
                self.assertEqual(app.centre.options["fg_color"], p["fond"])
                self.assertEqual(app.panneau_minuteurs.options["fg_color"],
                                 p["panneau"])
                self.assertEqual(app.barre_bas.options["fg_color"], p["panneau"])
                zone = app.zone_conversation.options
                self.assertEqual(zone["fg_color"], p["fond"])
                self.assertEqual(zone["scrollbar_button_color"],
                                 p["barre_defilement"])
                self.assertEqual(zone["scrollbar_button_hover_color"],
                                 p["barre_defilement_survol"])
                # Boutons (Hold to talk, Interrupt, Send)
                for bouton in (app.bouton_micro, app.bouton_envoyer):
                    self.assertEqual(bouton.options["fg_color"], p["accent"])
                    self.assertEqual(bouton.options["hover_color"],
                                     p["accent_survol"])
                    self.assertEqual(bouton.options["text_color"],
                                     p["texte_sur_accent"])
                stop = app.bouton_interrompre.options
                self.assertEqual(stop["text_color"], p["interrompre_texte"])
                self.assertEqual(stop["border_color"], p["interrompre_bordure"])
                self.assertEqual(stop["hover_color"], p["interrompre_survol"])
                # Champ de saisie
                for cle, valeur in module.OPTIONS_CHAMP.items():
                    self.assertEqual(app.champ_texte.options[cle], valeur)

    def test_bulles_utilisateur_et_assistant(self):
        for nom in THEMES_ATTENDUS:
            with self.subTest(theme=nom):
                module, _, app, entrees = self.monter(nom)
                p = module.THEMES[nom]
                entrees.extend([faux.entree(0, "user"),
                                faux.entree(1, "assistant")])
                app.rafraichir()
                bulles = app.zone_conversation.winfo_children()
                self.assertEqual(
                    [b.options["fg_color"] for b in bulles],
                    [p["bulle_utilisateur"], p["bulle_jarvis"]])
                for bulle in bulles:
                    textes = [e for e in bulle.winfo_children()]
                    self.assertEqual(textes[0].options["text_color"], p["texte"])
                    self.assertEqual(textes[1].options["text_color"],
                                     p["texte_faible"])

    def test_orbe_aux_couleurs_du_theme(self):
        for nom in THEMES_ATTENDUS:
            with self.subTest(theme=nom):
                module, _, app, _ = self.monter(nom)
                p = module.THEMES[nom]
                couleur = p["orbe"][app.etat_affiche]  # état affiché
                halo, milieu, coeur = (app._orbe_halo, app._orbe_milieu,
                                       app._orbe_coeur)
                objets = app.canvas_orbe.objets
                for item, facteur in ((halo, 0.30), (milieu, 0.60),
                                      (coeur, 1.0)):
                    self.assertEqual(
                        objets[item]["fill"],
                        module._fondre(couleur, p["orbe_fondu"], facteur))
                self.assertEqual(objets[coeur]["fill"], couleur)

    def test_micro_maintenu_utilise_la_couleur_d_ecoute_du_theme(self):
        for nom in THEMES_ATTENDUS:
            with self.subTest(theme=nom):
                module, _, app, _ = self.monter(nom)
                p = module.THEMES[nom]
                app._micro_presse()
                self.assertEqual(app.bouton_micro.options["fg_color"],
                                 p["orbe"]["ecoute"])
                self.assertEqual(app.bouton_micro.options["text_color"],
                                 p["texte_sur_accent"])
                app._micro_relache()
                self.assertEqual(app.bouton_micro.options["fg_color"],
                                 p["accent"])

    def test_fenetre_historique_suit_le_theme(self):
        for nom in THEMES_ATTENDUS:
            with self.subTest(theme=nom):
                module, ctk, app, _ = self.monter(nom)
                p = module.THEMES[nom]
                app.ouvrir_historique()
                historique = app._fenetre_historique
                if p["fond_fenetre"]:
                    self.assertEqual(historique.options["fg_color"],
                                     p["fond_fenetre"])
                self.assertEqual(app._liste_jours.options["fg_color"],
                                 p["panneau"])
                self.assertEqual(app._zone_historique.options["fg_color"],
                                 p["fond"])
                self.assertEqual(
                    app._zone_historique.options["scrollbar_button_color"],
                    p["barre_defilement"])
                for cle, valeur in module.OPTIONS_CHAMP.items():
                    self.assertEqual(app._champ_recherche.options[cle], valeur)

    def test_un_fond_de_fenetre_refuse_ne_bloque_pas_l_ouverture(self):
        module, _, app, _ = self.monter("or_et_nuit")

        class Refuse:
            def configure(self, **_):
                raise RuntimeError("couleur refusée")

        with redirect_stderr(io.StringIO()) as erreur:
            module._fond_de_fenetre(Refuse())
        self.assertIn("couleur refusée", erreur.getvalue())

    def test_theme_inconnu_dans_la_config_de_l_application_donne_le_repli(self):
        module, _, app, _ = self.monter("violet")
        self.assertEqual(app.theme, "jarvis_bleu")
        self.assertEqual(app.entete.options["fg_color"], "#14141d")

    def test_tailles_et_typographie_du_lot_u1_inchangees(self):
        module, _, app, _ = self.monter("or_et_nuit")
        self.assertEqual(module.ORBE_TAILLE, 116)
        self.assertEqual((app.canvas_orbe.options["width"],
                          app.canvas_orbe.options["height"]), (116, 116))
        self.assertEqual(module.ORBE_RAYONS, (52, 40, 28))
        self.assertEqual((module.HAUTEUR_BOUTON_PRINCIPAL,
                          module.LARGEUR_BOUTON_COLONNE,
                          module.HAUTEUR_SAISIE, module.RAYON_BULLE),
                         (54, 150, 42, 14))
        police = app.texte_etat.options["font"]
        self.assertEqual((police.family, police.size, police.weight),
                         ("Segoe UI", 20, "bold"))
        police = app.bouton_micro.options["font"]
        self.assertEqual((police.size, police.weight), (16, "bold"))
        police = app.texte_detail.options["font"]
        self.assertEqual(police.size, 12)

    def test_le_changement_de_theme_ne_touche_pas_aux_fichiers_d_etat(self):
        # Le thème n'écrit rien : ni data/, ni config (aucune écriture de
        # fichier hors celle de la géométrie, déjà présente avant U2).
        module, _, app, _ = self.monter("or_et_nuit")
        self.assertFalse((Path(app.racine) / "data" / "hud-state.json").exists())
        self.assertFalse((Path(app.racine) / "data" / "timers.json").exists())


if __name__ == "__main__":
    unittest.main()
