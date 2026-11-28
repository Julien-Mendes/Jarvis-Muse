"""Lot 0.1 — K1 : configuration unique (config_jarvis) et ses contrats.

Lancer : python -m unittest discover -s tests -p "test_lot01_*.py"
"""
import importlib
import re
import tempfile
import tomllib
import unittest
from pathlib import Path

import _chemins_lot01 as chemins  # noqa: F401  (rend scripts/ importable)

import config_jarvis

EXEMPLE = chemins.RACINE / "config" / "config.example.toml"

# Registre des clés de config.example.toml et du script qui les lit. Une clé
# ajoutée à l'exemple sans être listée ici (donc sans être reliée au code) fait
# échouer test_chaque_cle_de_l_exemple_est_reliee (bug F8 : réglages ignorés).
CLES_LUES = {
    "general": {"langue": "config_jarvis", "langues_disponibles": "config_jarvis",
                "fuseau_horaire": "config_jarvis",
                "langue_auto": "config_jarvis"},
    "voix": {"moteur": "lire_voix", "voix_fr": "lire_voix",
             "voix_en": "lire_voix", "vitesse": "lire_voix"},
    "declenchement": {"touche_push_to_talk": "boucle_voix"},
    "boucle": {"fournisseur_llm": "boucle_voix", "modele_groq": "boucle_voix",
               "modele_anthropic": "boucle_voix", "effort_groq": "boucle_voix",
               "effort_anthropic": "boucle_voix",
               "fournisseur_stt": "boucle_voix", "modele_stt_groq": "boucle_voix",
               "modele_stt_local": "boucle_voix",
               "duree_max_enregistrement": "boucle_voix",
               "duree_min_enregistrement": "boucle_voix",
               "max_tours_outils": "boucle_voix",
               "max_tokens_reponse": "boucle_voix",
               "delai_cerveau_s": "boucle_voix",
               "delai_tour_s": "boucle_voix"},
    "cerveau": {"effort": "config_jarvis"},
    # Lot LT : lues par taches_longues.reglages().
    "taches_longues": {"duree_max_minutes": "taches_longues",
                       "max_etapes": "taches_longues",
                       "jetons_par_minute": "taches_longues",
                       "effort": "taches_longues"},
    "minuteur": {"max_actifs": "minuteur", "duree_max": "minuteur"},
    "yeux": {"fournisseur_vision": "yeux", "modele_vision_groq": "yeux",
             "modele_vision_anthropic": "yeux", "largeur_max": "yeux",
             "max_tokens_description": "yeux"},
    "navigateur": {"navigateur_defaut": "boucle_voix",
                   "delai_apres_navigation": "navigateur",
                   "max_caracteres_page": "navigateur"},
    "securite": {"confirmation_orale_max_mots": "boucle_voix"},
    "hud": {"active": "hud", "position": "hud", "taille": "hud",
            "toujours_au_premier_plan": "hud", "intervalle_ms": "hud"},
    "app": {"active": "app", "largeur": "app", "hauteur": "app",
            "toujours_au_premier_plan": "app", "intervalle_ms": "app",
            "theme": "app", "animations": "app", "tableau_de_bord": "app"},
    "session": {"lire_a_dire": "lancer_session", "annoncer_minuteurs_du_jour":
                "lancer_session", "demarrer_hud": "lancer_session"},
}


def ecrire(dossier: Path, nom: str, contenu: str) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / nom).write_text(contenu, encoding="utf-8")


class CouchesEtLangue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dossier = Path(self.tmp.name)
        ecrire(self.dossier, "config.example.toml",
               '[general]\nlangue = "en"\nfuseau_horaire = "America/Toronto"\n'
               '[minuteur]\nmax_actifs = 20\nduree_max = "7j"\n')

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaut_sans_fichier(self):
        with tempfile.TemporaryDirectory() as vide:
            donnees = config_jarvis.charger_donnees(Path(vide))
        self.assertEqual(config_jarvis.langue(donnees), "en")
        self.assertEqual(str(config_jarvis.fuseau(donnees)), "America/Toronto")

    def test_couches_publique_personnelle_locale(self):
        ecrire(self.dossier, "config.toml", '[general]\nlangue = "fr"\n')
        ecrire(self.dossier, "config.local.toml",
               '[general]\nfuseau_horaire = "Europe/Paris"\n'
               '[minuteur]\nmax_actifs = 5\n')
        d = config_jarvis.charger_donnees(self.dossier)
        self.assertEqual(config_jarvis.langue(d), "fr")
        self.assertEqual(str(config_jarvis.fuseau(d)), "Europe/Paris")
        self.assertEqual(d["minuteur"]["max_actifs"], 5)
        self.assertEqual(d["minuteur"]["duree_max"], "7j")  # clé de la couche publique

    def test_ancien_emplacement_boucle_langue_respecte(self):
        ecrire(self.dossier, "config.toml",
               '[general]\nlangue = "en"\n[boucle]\nlangue = "fr"\n')
        self.assertEqual(config_jarvis.langue(
            config_jarvis.charger_donnees(self.dossier)), "fr")

    def test_langue_invalide_retombe_sur_defaut(self):
        ecrire(self.dossier, "config.toml", '[general]\nlangue = "de"\n')
        self.assertEqual(config_jarvis.langue(
            config_jarvis.charger_donnees(self.dossier)), "en")

    def test_fichier_casse_ne_plante_pas(self):
        ecrire(self.dossier, "config.local.toml", "[general\nbroken")
        d = config_jarvis.charger_donnees(self.dossier)
        self.assertEqual(config_jarvis.langue(d), "en")

    def test_fuseau_invalide_retombe_sur_defaut(self):
        ecrire(self.dossier, "config.toml",
               '[general]\nfuseau_horaire = "Mars/Olympus"\n')
        d = config_jarvis.charger_donnees(self.dossier)
        self.assertEqual(str(config_jarvis.fuseau(d)), "America/Toronto")


class Utilitaires(unittest.TestCase):
    def test_duree_en_minutes(self):
        self.assertEqual(config_jarvis.duree_en_minutes("7j", 1), 7 * 1440)
        self.assertEqual(config_jarvis.duree_en_minutes("12h", 1), 720)
        self.assertEqual(config_jarvis.duree_en_minutes("90m", 1), 90)
        self.assertEqual(config_jarvis.duree_en_minutes("n'importe quoi", 42), 42)
        self.assertEqual(config_jarvis.duree_en_minutes(-5, 42), 42)

    def test_nombre_borne(self):
        self.assertEqual(config_jarvis.nombre_borne(500, 1, 8, 8, entier=True), 8)
        self.assertEqual(config_jarvis.nombre_borne(0, 1, 8, 8, entier=True), 1)
        self.assertEqual(config_jarvis.nombre_borne("x", 1, 8, 8, entier=True), 8)


class ContratsAvecLesScripts(unittest.TestCase):
    def test_chaque_cle_de_l_exemple_est_reliee(self):
        exemple = tomllib.loads(EXEMPLE.read_text(encoding="utf-8"))
        for section, valeurs in exemple.items():
            self.assertIn(section, CLES_LUES, f"section [{section}] non reliée")
            for cle in valeurs:
                self.assertIn(
                    cle, CLES_LUES[section],
                    f"[{section}] {cle} : clé non reliée au code (F8). "
                    "Reliez-la ou retirez-la de config.example.toml.")

    def test_cles_lues_sont_dans_l_exemple(self):
        exemple = tomllib.loads(EXEMPLE.read_text(encoding="utf-8"))
        for section, cles in CLES_LUES.items():
            for cle in cles:
                self.assertIn(cle, exemple.get(section, {}),
                              f"[{section}] {cle} déclarée lue mais absente de l'exemple")

    def test_boucle_ne_porte_plus_de_langue_dans_l_exemple(self):
        exemple = tomllib.loads(EXEMPLE.read_text(encoding="utf-8"))
        self.assertNotIn("langue", exemple["boucle"])
        self.assertIn("langue", exemple["general"])

    def test_langue_unique_vue_par_tous_les_scripts(self):
        import boucle_voix
        import minuteur
        import yeux
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            ecrire(racine / "config", "config.toml", '[general]\nlangue = "fr"\n')
            self.assertEqual(boucle_voix.charger_config(racine)["langue"], "fr")
            self.assertEqual(yeux.charger_config(racine)["langue"], "fr")
            self.assertEqual(minuteur.langue_courante(racine / "config"), "fr")

    def test_touche_et_sections_de_la_boucle_viennent_de_la_config(self):
        import boucle_voix
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            ecrire(racine / "config", "config.toml",
                   '[declenchement]\ntouche_push_to_talk = "F8"\n'
                   '[boucle]\nmax_tours_outils = 2\n'
                   '[navigateur]\nnavigateur_defaut = "playwright"\n'
                   '[yeux]\nfournisseur_vision = "anthropic"\n')
            c = boucle_voix.charger_config(racine)
        self.assertEqual(c["touche"], "F8")
        self.assertEqual(c["max_tours_outils"], 2)
        self.assertEqual(c["navigateur_defaut"], "playwright")
        self.assertEqual(c["fournisseur_vision"], "anthropic")

    def test_config_locale_prime_sur_config_personnelle(self):
        import boucle_voix
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            ecrire(racine / "config", "config.toml", '[boucle]\nmax_tours_outils = 2\n')
            ecrire(racine / "config", "config.local.toml", '[boucle]\nmax_tours_outils = 1\n')
            self.assertEqual(boucle_voix.charger_config(racine)["max_tours_outils"], 1)

    def test_fuseau_jamais_code_en_dur_hors_config_jarvis(self):
        """F8 : plus aucun ZoneInfo("America/Toronto") codé en dur dans le code
        (les mentions dans les docstrings et commentaires sont tolérées)."""
        motif = re.compile(r"""ZoneInfo\(\s*["']America/Toronto["']""")
        fautifs = []
        for script in chemins.SCRIPTS.glob("*.py"):
            if script.name == "config_jarvis.py":
                continue
            if motif.search(script.read_text(encoding="utf-8")):
                fautifs.append(script.name)
        self.assertEqual(fautifs, [], "fuseau codé en dur dans : "
                         + ", ".join(fautifs))

    def test_fuseau_des_scripts_suit_la_config(self):
        import boucle_voix
        import minuteur
        self.assertEqual(str(boucle_voix.FUSEAU), str(config_jarvis.fuseau()))
        self.assertEqual(str(minuteur.FUSEAU), str(config_jarvis.fuseau()))

    def test_limites_du_minuteur_viennent_de_la_config(self):
        import minuteur
        d = config_jarvis.charger_donnees()
        self.assertEqual(minuteur.MAX_ACTIFS,
                         int(d["minuteur"]["max_actifs"]))
        self.assertEqual(minuteur.DUREE_MAX_MINUTES,
                         config_jarvis.duree_en_minutes(d["minuteur"]["duree_max"], 0))

    def test_voix_noms_courts_et_complets(self):
        import lire_voix
        d = {"voix": {"voix_fr": "upmc", "voix_en": "en_GB-alan-medium"}}
        self.assertEqual(lire_voix.nom_voix_configure(d, "fr"), "fr_FR-upmc-medium")
        self.assertEqual(lire_voix.nom_voix_configure(d, "en"), "en_GB-alan-medium")
        self.assertEqual(lire_voix.nom_voix_configure({}, "en"), "en_GB-alan-medium")

    def test_confirmation_max_mots_ne_peut_que_resserrer(self):
        import boucle_voix
        self.assertLessEqual(boucle_voix.CONFIRMATION_MAX_MOTS, 8)
        self.assertGreaterEqual(boucle_voix.CONFIRMATION_MAX_MOTS, 1)


if __name__ == "__main__":
    unittest.main()
