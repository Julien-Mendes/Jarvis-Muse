"""Lot U2 — non-régression du défilement de la conversation.

Bug constaté à l'essai réel : la zone de conversation ne suivait pas les
nouveaux messages, on restait bloqué sur les 5-6 premiers échanges, la barre
de défilement ne fonctionnait pas. Deux causes corrigées :

  1. app.py liait <Configure> sur la zone défilante SANS add="+", ce qui
     remplace la liaison interne de CTkScrollableFrame qui tient à jour la
     zone de défilement (scrollregion) : elle restait figée ;
  2. le défilement vers le bas se faisait immédiatement après l'ajout d'une
     bulle, avant la mise en page de Tk : toujours un message de retard.

Les tests utilisent un faux CustomTkinter (voir _faux_ctk.py) avec les deux
modèles de liaison : « remplace » (le bug) et « cumule » (liaison protégée).
Sans écran, sans Windows : à confirmer aussi à l'essai réel.
"""
import tempfile
import unittest

import _faux_ctk as faux

MODELES = ("remplace", "cumule")


class Banc:
    """Une Application sur faux CustomTkinter, pilotée pas à pas."""

    def __init__(self, modele):
        self.module, self.ctk = faux.charger_app(modele)
        self.tmp = tempfile.TemporaryDirectory()
        self.entrees = []
        self.app = faux.creer_application(self.module, self.tmp.name,
                                          self.entrees)
        self.zone = self.app.zone_conversation
        self.canvas = self.zone._parent_canvas
        self.racine = self.app.fenetre

    def fermer(self):
        self.tmp.cleanup()

    def tick(self, ajouts=0):
        """Un rafraîchissement (500 ms) avec `ajouts` nouveaux messages, puis
        la mise en page, les événements et les 120 ms du retour à la ligne."""
        debut = len(self.entrees)
        self.entrees.extend(faux.entree(debut + i) for i in range(ajouts))
        self.app.rafraichir()
        self.racine.tourner()
        self.racine.avancer(120)

    def remplir(self, nombre=40, par_tick=4):
        for _ in range(nombre // par_tick):
            self.tick(par_tick)

    def en_bas(self):
        return self.canvas.bas_visible_px() >= self.zone.hauteur_mise_en_page - 1

    def region_a_jour(self):
        return (self.canvas.scrollregion is not None
                and self.canvas.scrollregion[3] == self.zone.hauteur_mise_en_page)


class Base(unittest.TestCase):
    modele = "remplace"

    def setUp(self):
        self.banc = Banc(self.modele)
        self.addCleanup(self.banc.fermer)


class LiaisonInterne(Base):
    modele = "remplace"  # le modèle où le bind de l'application est dangereux

    def test_le_bind_de_l_application_ne_remplace_pas_la_liaison_interne(self):
        """Cause 1 : la zone défilante doit garder sa liaison <Configure>
        (mise à jour de la zone de défilement) à côté de celle de l'appli."""
        liaisons = self.banc.zone.liaisons.get("<Configure>", [])
        self.assertGreaterEqual(
            len(liaisons), 2,
            "la liaison interne de CTkScrollableFrame a été remplacée "
            "(bind sans add='+')")


class SuiviDesMessages(unittest.TestCase):
    def pour_chaque_modele(self, fonction):
        for modele in MODELES:
            with self.subTest(modele=modele):
                banc = Banc(modele)
                try:
                    fonction(banc)
                finally:
                    banc.fermer()

    def test_la_conversation_suit_les_nouveaux_messages(self):
        def verifier(banc):
            for tour in range(12):
                banc.tick(4)
                self.assertTrue(banc.region_a_jour(), f"tour {tour}")
                self.assertTrue(banc.en_bas(), f"tour {tour} : pas en bas")
            self.assertGreater(banc.zone.hauteur_mise_en_page, 4 * 400)
        self.pour_chaque_modele(verifier)

    def test_un_seul_message_ajoute_apparait_en_bas(self):
        def verifier(banc):
            banc.remplir()
            banc.tick(1)
            self.assertTrue(banc.en_bas())
        self.pour_chaque_modele(verifier)

    def test_premier_chargement_d_une_longue_conversation_arrive_en_bas(self):
        def verifier(banc):
            banc.tick(60)
            self.assertTrue(banc.region_a_jour())
            self.assertTrue(banc.en_bas())
        self.pour_chaque_modele(verifier)

    def test_zone_de_defilement_mise_a_jour_a_chaque_message(self):
        def verifier(banc):
            for tour in range(6):
                banc.tick(3)
                self.assertEqual(banc.canvas.scrollregion[3],
                                 banc.zone.hauteur_mise_en_page)
        self.pour_chaque_modele(verifier)


class Robustesse(unittest.TestCase):
    def test_sans_after_idle_le_defilement_retombe_sur_after(self):
        banc = Banc("cumule")
        try:
            banc.app.fenetre.after_idle = None  # fenêtre sans after_idle
            banc.tick(20)
            banc.racine.avancer(10)
            self.assertTrue(banc.region_a_jour())
            self.assertTrue(banc.en_bas())
        finally:
            banc.fermer()

    def test_une_zone_sans_canvas_interne_ne_plante_pas(self):
        """L'API interne de CTkScrollableFrame peut changer : pas d'exception."""
        banc = Banc("cumule")
        try:
            banc.zone._liaisons_internes.clear()  # la liaison du faux widget
            del banc.zone._parent_canvas          # attribut interne disparu
            banc.tick(5)  # ne doit pas lever
            banc.app._defiler_bas()
            banc.racine.tourner()
        finally:
            banc.fermer()


class PositionDeLUtilisateur(unittest.TestCase):
    def pour_chaque_modele(self, fonction):
        for modele in MODELES:
            with self.subTest(modele=modele):
                banc = Banc(modele)
                try:
                    banc.remplir()
                    fonction(banc)
                finally:
                    banc.fermer()

    def test_lecteur_remonte_n_est_pas_ramene_en_bas(self):
        def verifier(banc):
            banc.canvas.yview_scroll(-30)  # la molette : il relit plus haut
            haut = banc.canvas.haut
            self.assertFalse(banc.en_bas())
            for _ in range(5):
                banc.tick(2)  # de nouveaux messages arrivent
                self.assertEqual(banc.canvas.haut, haut)
                self.assertFalse(banc.en_bas())
        self.pour_chaque_modele(verifier)

    def test_rechargement_toutes_les_500_ms_sans_changement(self):
        def verifier(banc):
            banc.canvas.yview_scroll(-30)
            haut = banc.canvas.haut
            for _ in range(10):
                banc.tick(0)
                self.assertEqual(banc.canvas.haut, haut)
            self.assertGreater(haut, 0, "ne doit pas être ramené en haut")
        self.pour_chaque_modele(verifier)

    def test_il_redescend_lui_meme_puis_le_suivi_reprend(self):
        def verifier(banc):
            banc.canvas.yview_scroll(-30)
            banc.tick(2)
            self.assertFalse(banc.en_bas())
            banc.canvas.yview_moveto(1.0)  # il redescend en bas
            banc.tick(2)
            self.assertTrue(banc.en_bas())
        self.pour_chaque_modele(verifier)

    def test_ne_rien_deplacer_quand_il_n_y_a_pas_de_nouveau_message(self):
        def verifier(banc):
            avant = banc.canvas.haut
            banc.tick(0)
            self.assertEqual(banc.canvas.haut, avant)
            self.assertTrue(banc.en_bas())
        self.pour_chaque_modele(verifier)


class RedimensionnementEtRetourALaLigne(unittest.TestCase):
    def pour_chaque_modele(self, fonction):
        for modele in MODELES:
            with self.subTest(modele=modele):
                banc = Banc(modele)
                try:
                    banc.remplir()
                    fonction(banc)
                finally:
                    banc.fermer()

    def redimensionner(self, banc, largeur):
        banc.zone.largeur = largeur
        banc.zone.declencher("<Configure>")
        banc.racine.tourner()
        banc.racine.avancer(150)

    def test_retour_a_la_ligne_met_a_jour_la_zone_et_garde_le_bas(self):
        def verifier(banc):
            hauteur_large = banc.zone.hauteur_mise_en_page
            self.redimensionner(banc, 330)  # bulles plus étroites : plus hautes
            self.assertGreater(banc.zone.hauteur_mise_en_page, hauteur_large)
            self.assertTrue(banc.region_a_jour())
            self.assertTrue(banc.en_bas())
        self.pour_chaque_modele(verifier)

    def test_retour_a_la_ligne_ne_force_pas_le_bas_si_on_lit_plus_haut(self):
        def verifier(banc):
            banc.canvas.yview_scroll(-30)
            banc.tick(0)  # le rafraîchissement mémorise « pas en bas »
            haut = banc.canvas.haut
            self.redimensionner(banc, 330)
            self.assertTrue(banc.region_a_jour())
            self.assertEqual(banc.canvas.haut, haut)
            self.assertFalse(banc.en_bas())
        self.pour_chaque_modele(verifier)

    def test_ajout_de_messages_apres_redimensionnement(self):
        def verifier(banc):
            self.redimensionner(banc, 330)
            banc.tick(4)
            self.assertTrue(banc.region_a_jour())
            self.assertTrue(banc.en_bas())
        self.pour_chaque_modele(verifier)


class Reconstruction(unittest.TestCase):
    def pour_chaque_modele(self, fonction):
        for modele in MODELES:
            with self.subTest(modele=modele):
                banc = Banc(modele)
                try:
                    banc.remplir()
                    fonction(banc)
                finally:
                    banc.fermer()

    @staticmethod
    def raccourcir(banc, garder=30):
        """Le journal raccourcit (plafond de 200 lignes, nouveau jour)."""
        del banc.entrees[:len(banc.entrees) - garder]
        banc.tick(0)

    def test_reconstruction_en_bas_reste_en_bas(self):
        def verifier(banc):
            self.raccourcir(banc)
            self.assertTrue(banc.region_a_jour())
            self.assertTrue(banc.en_bas())
        self.pour_chaque_modele(verifier)

    def test_reconstruction_ne_ramene_pas_en_haut_un_lecteur(self):
        def verifier(banc):
            banc.canvas.yview_scroll(-30)
            banc.tick(0)
            self.raccourcir(banc, garder=36)
            self.assertGreater(banc.canvas.haut, 0)
            self.assertFalse(banc.en_bas())
        self.pour_chaque_modele(verifier)


class FonctionsPures(unittest.TestCase):
    def test_est_en_bas(self):
        module, _ = faux.charger_app()
        self.assertTrue(module.est_en_bas(0.0, 1.0))      # tout tient
        self.assertTrue(module.est_en_bas(0.8, 1.0))
        self.assertTrue(module.est_en_bas(0.8, 0.9985))   # tolérance
        self.assertFalse(module.est_en_bas(0.7, 0.95))
        self.assertTrue(module.est_en_bas(0.7, 0.95, tolerance=0.1))

    def test_defiler_bas_reste_disponible(self):
        banc = Banc("cumule")
        try:
            banc.tick(40)
            banc.canvas.yview_scroll(-30)
            banc.app._defiler_bas()
            banc.racine.tourner()
            self.assertTrue(banc.en_bas())
        finally:
            banc.fermer()


if __name__ == "__main__":
    unittest.main()
