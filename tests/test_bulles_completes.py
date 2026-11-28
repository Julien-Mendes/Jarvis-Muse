"""Correctif — bulles de chat coupées.

Constaté dans la fenêtre réelle : « Awesome. Let me know when you're re »
au lieu de « … when you're ready » ; le texte était coupé en plein mot.

Cause : la largeur de retour à la ligne venait de winfo_width() (pixels
RÉELS), alors que CustomTkinter multiplie ensuite `wraplength` par l'échelle
de l'écran (1,25 à 125 % sous Windows). Le texte se repliait 1,25 fois trop
large : la fin de chaque ligne sortait de la bulle et était coupée par le
bord du panneau. (Mesure à 125 % : repli à 903 px, 713 px visibles.)
L'Historique avait le même défaut (520 fixe, plus large que sa colonne).

Deux niveaux de tests :
  - sans écran (faux CustomTkinter) : le calcul de largeur tient compte de
    l'échelle, à l'ajout comme au redimensionnement ;
  - avec un vrai Tk (sauté s'il n'y a pas d'écran) : pour des messages
    courts, moyens, très longs et des mots très longs, à 100 / 125 / 150 %,
    tout le texte tient dans la bulle et la bulle dans la zone.
"""
import tempfile
import unittest

import _faux_ctk as faux

TEXTES = {
    "court": "Awesome. Let me know when you're ready",
    "moyen": ("Will do, Julien. I'll let you know as soon as the "
              "comparison is ready"),
    "tres_long": "Voici le résumé complet de la comparaison demandée. " * 15,
    "mot_long": "Lien : https://exemple.org/" + "a" * 300 + " fin",
    "mots_colles": "anticonstitutionnellement" * 8,
}


class CalculDeLargeur(unittest.TestCase):
    def setUp(self):
        self.module, _ = faux.charger_app("cumule", nom="app_bulles_calcul")

    def test_sans_echelle_rien_ne_change(self):
        reserve = self.module.RESERVE_LARGEUR_BULLE
        self.assertEqual(self.module.largeur_bulle_logique(800, 1.0),
                         800 - reserve)

    def test_la_bulle_tient_dans_la_zone_a_toutes_les_echelles(self):
        """Texte + marges, remis à l'échelle par CustomTkinter, ne doivent
        jamais dépasser la largeur réelle de la zone."""
        reserve = self.module.RESERVE_LARGEUR_BULLE
        for echelle in (1.0, 1.25, 1.5, 1.75, 2.0):
            for largeur_px in (500, 640, 847, 1200, 2400):
                with self.subTest(echelle=echelle, largeur=largeur_px):
                    logique = self.module.largeur_bulle_logique(
                        largeur_px, echelle)
                    if logique > 240:  # au-dessus du plancher
                        self.assertLessEqual(
                            (logique + reserve) * echelle, largeur_px)

    def test_cas_constate_a_125_pourcent(self):
        # Avant : 847 - 124 = 723, mis à l'échelle à 903 px > 847 px.
        logique = self.module.largeur_bulle_logique(847, 1.25)
        self.assertEqual(logique, 553)
        self.assertLess(logique * 1.25, 847)

    def test_echelle_invalide_vaut_un(self):
        for echelle in (0, -1, None):
            self.assertEqual(self.module.largeur_bulle_logique(800, echelle),
                             self.module.largeur_bulle_logique(800, 1.0))

    def test_plancher(self):
        self.assertEqual(self.module.largeur_bulle_logique(100, 1.5), 240)

    def test_echelle_illisible_vaut_un(self):
        # Le faux CustomTkinter n'a pas de ScalingTracker.
        self.assertEqual(self.module.echelle_widget(object()), 1.0)


class ApplicationAvecEchelle(unittest.TestCase):
    """L'Application utilise l'échelle de l'écran à l'ajout d'une bulle et
    au retour à la ligne après un redimensionnement (défilement U2 inclus)."""

    def setUp(self):
        self.module, self.ctk = faux.charger_app("cumule",
                                                 nom="app_bulles_echelle")
        self.echelle = 1.25
        self.ctk.ScalingTracker = type("Suivi", (), {
            "get_widget_scaling": staticmethod(lambda _w: self.echelle)})
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.entrees = []
        self.app = faux.creer_application(self.module, self.tmp.name,
                                          self.entrees)
        self.zone = self.app.zone_conversation
        self.zone.largeur = 847

    def _tick(self, textes):
        debut = len(self.entrees)
        for i, texte in enumerate(textes):
            self.entrees.append({
                "role": "user" if (debut + i) % 2 == 0 else "assistant",
                "texte": texte, "heure": "2026-11-28T10:33:00-05:00"})
        self.app.rafraichir()
        self.app.fenetre.tourner()
        self.app.fenetre.avancer(150)

    def test_ajout_utilise_la_largeur_a_l_echelle(self):
        self._tick(list(TEXTES.values()))
        attendu = self.module.largeur_bulle_logique(847, 1.25)
        self.assertEqual(len(self.app._etiquettes_bulles), len(TEXTES))
        for etiquette in self.app._etiquettes_bulles:
            self.assertEqual(etiquette.cget("wraplength"), attendu)
            # Le texte est complet, jamais raccourci.
            self.assertIn(etiquette.cget("text"), TEXTES.values())

    def test_redimensionnement_garde_l_echelle_et_le_bas(self):
        self._tick(list(TEXTES.values()) * 4)
        self.zone.largeur = 640
        self.zone.declencher("<Configure>")
        self.app.fenetre.tourner()
        self.app.fenetre.avancer(150)
        attendu = self.module.largeur_bulle_logique(640, 1.25)
        for etiquette in self.app._etiquettes_bulles:
            self.assertEqual(etiquette.cget("wraplength"), attendu)
        canvas = self.zone._parent_canvas
        self.assertGreaterEqual(canvas.bas_visible_px(),
                                self.zone.hauteur_mise_en_page - 1)

    def test_historique_suit_la_largeur_de_sa_zone(self):
        zone = faux.FauxWidget()
        zone.largeur = 600
        self.app._zone_historique = zone
        self.assertEqual(self.app._largeur_bulle_historique(),
                         self.module.largeur_bulle_logique(600, 1.25))
        zone.largeur = 1  # pas encore affichée
        self.assertEqual(self.app._largeur_bulle_historique(),
                         self.module.largeur_bulle_logique(425, 1.25))


def _tk_disponible() -> bool:
    try:
        import customtkinter  # noqa: F401
        import tkinter
        racine = tkinter.Tk()
        racine.destroy()
        return True
    except Exception:
        return False


@unittest.skipUnless(_tk_disponible(), "pas d'écran ni de CustomTkinter")
class VraiTk(unittest.TestCase):
    """Mesure réelle : la largeur demandée par le texte replié ne dépasse
    jamais la largeur visible de l'étiquette, et la bulle reste dans la
    zone (sinon, le bord coupe le texte)."""

    def setUp(self):
        import importlib.util
        import customtkinter as ctk
        self.ctk = ctk
        spec = importlib.util.spec_from_file_location(
            "app_bulles_vrai_tk", faux.SCRIPTS / "app.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.addCleanup(ctk.set_widget_scaling, 1.0)

    def _verifier(self, echelle, largeur_fenetre):
        ctk = self.ctk
        ctk.set_widget_scaling(echelle)
        fenetre = ctk.CTk()
        try:
            fenetre.geometry(f"{largeur_fenetre}x500")
            zone = ctk.CTkScrollableFrame(fenetre)
            zone.pack(fill="both", expand=True)
            fenetre.update()
            largeur = self.module.largeur_bulle_logique(
                zone.winfo_width(), self.module.echelle_widget(zone))
            etiquettes = []
            precedent = None
            for nom, texte in TEXTES.items():
                for role in ("user", "assistant"):
                    etiquettes.append((nom, self.module.ajouter_bulle(
                        zone, {"role": role, "texte": texte,
                               "heure": "2026-11-28T10:33:00-05:00"},
                        largeur, precedent)))
                    precedent = role
            fenetre.update()
            for nom, etiquette in etiquettes:
                with self.subTest(echelle=echelle, fenetre=largeur_fenetre,
                                  texte=nom):
                    label = etiquette._label
                    self.assertEqual(label.cget("text"), TEXTES[nom])
                    self.assertLessEqual(label.winfo_reqwidth(),
                                         label.winfo_width())
                    cadre = etiquette.master
                    self.assertGreaterEqual(cadre.winfo_x(), 0)
                    self.assertLessEqual(
                        cadre.winfo_x() + cadre.winfo_width(),
                        zone.winfo_width())
                    if nom in ("tres_long", "mot_long", "mots_colles"):
                        # Retour à la ligne réel : plusieurs lignes.
                        self.assertGreater(label.winfo_height(), 40)
        finally:
            fenetre.destroy()

    def test_toutes_longueurs_et_echelles(self):
        for echelle in (1.0, 1.25, 1.5):
            for largeur_fenetre in (640, 1100):
                self._verifier(echelle, largeur_fenetre)


if __name__ == "__main__":
    unittest.main()
