"""Lot V1 — vitesse de la voix : voix résidente, lecture phrase par phrase,
marge de fin réduite, [voix] vitesse transmise partout.

Aucun son, aucun modèle Piper : la synthèse et la lecture sont simulées.
"""
import contextlib
import io
import sys
import tempfile
import threading
import types
import unittest
import wave
from pathlib import Path
from unittest import mock

import _chemins_lot01  # noqa: F401  (rend scripts/ importable)

import boucle_voix
import lire_voix
import minuteur


class FausseVoixPiper:
    """Remplace une PiperVoice chargée : 0,1 s de silence par caractère."""

    def __init__(self):
        self.textes = []

    def synthesize(self, texte, syn_config=None, **_):
        self.textes.append(texte)
        yield types.SimpleNamespace(sample_rate=1000,
                                    audio_int16_bytes=b"\0\0" * 10 * len(texte))


def voix_residente_simulee(echec_a=None):
    """VoixResidente dont le modèle est simulé ; `echec_a` = texte dont la
    synthèse échoue."""
    voix = lire_voix.VoixResidente(dossier_modeles=Path("inexistant"),
                                   donnees={})
    fausse = FausseVoixPiper()
    chargements = []

    def charger(langue, nom=None):
        chargements.append(langue)
        return fausse

    voix.charger = charger
    if echec_a is not None:
        origine = voix.synthetiser

        def synthetiser(texte, langue, vitesse=1.0):
            if texte == echec_a:
                raise RuntimeError("synthèse impossible")
            return origine(texte, langue, vitesse)

        voix.synthetiser = synthetiser
    return voix, fausse, chargements


class DecoupagePhrases(unittest.TestCase):
    def test_phrases_separees(self):
        self.assertEqual(
            lire_voix.decouper_phrases("Sure, Julien. Timer set! Anything else?"),
            ["Sure, Julien.", "Timer set!", "Anything else?"])

    def test_nombres_et_abreviations_courtes_non_coupes(self):
        self.assertEqual(lire_voix.decouper_phrases("Il fait 3.5 degrés."),
                         ["Il fait 3.5 degrés."])
        self.assertEqual(lire_voix.decouper_phrases("M. Dupont arrive."),
                         ["M. Dupont arrive."])

    def test_sauts_de_ligne_et_texte_vide(self):
        self.assertEqual(lire_voix.decouper_phrases("Bonjour\n\nDeux trois"),
                         ["Bonjour", "Deux trois"])
        self.assertEqual(lire_voix.decouper_phrases("Ok.\nDeux trois"),
                         ["Ok. Deux trois"])  # trop court : collé au suivant.
        self.assertEqual(lire_voix.decouper_phrases("  "), [])


class VoixResidenteLecture(unittest.TestCase):
    def setUp(self):
        self.joues = []

        def jouer(chemin, interruption=None):
            with wave.open(str(chemin), "rb") as wav:
                self.joues.append(wav.getnframes())
            return True

        patcheur = mock.patch.object(lire_voix, "jouer_wav", side_effect=jouer)
        patcheur.start()
        self.addCleanup(patcheur.stop)

    def test_lit_chaque_phrase_dans_l_ordre_avec_un_seul_chargement(self):
        voix, fausse, chargements = voix_residente_simulee()
        premier = []
        self.assertTrue(voix.lire("First one. Second one.", "en", 1.0,
                                  threading.Event(), lambda: premier.append(1)))
        self.assertEqual(fausse.textes, ["First one.", "Second one."])
        self.assertEqual(len(self.joues), 2)
        self.assertEqual(premier, [1])  # appelé une seule fois.

    def test_le_modele_reel_n_est_charge_qu_une_fois(self):
        voix = lire_voix.VoixResidente(dossier_modeles=Path("x"), donnees={})
        chargements = []
        piper = types.ModuleType("piper")
        piper.PiperVoice = types.SimpleNamespace(
            load=lambda m, c: chargements.append(m) or FausseVoixPiper())
        with mock.patch.dict(sys.modules, {"piper": piper}), \
                mock.patch.object(lire_voix, "trouver_modele",
                                  return_value=(Path("v.onnx"),
                                                Path("v.onnx.json"))):
            voix.prechauffer("en")
            voix.lire("Hello there. Again.", "en")
        self.assertEqual(len(chargements), 1)

    def test_interruption_arrete_la_lecture(self):
        voix, fausse, _ = voix_residente_simulee()
        interruption = threading.Event()

        def jouer(chemin, interruption_recue=None):
            interruption.set()  # F9 pendant la première phrase.
            return False

        with mock.patch.object(lire_voix, "jouer_wav", side_effect=jouer):
            self.assertFalse(voix.lire("One here. Two here. Three here.", "en",
                                       1.0, interruption))

    def test_echec_de_synthese_rend_le_texte_non_joue(self):
        voix, _, _ = voix_residente_simulee(echec_a="Two here.")
        with self.assertRaises(lire_voix.ErreurLecture) as contexte:
            voix.lire("One here. Two here. Three here.", "en")
        self.assertEqual(contexte.exception.reste, "Two here. Three here.")
        self.assertEqual(len(self.joues), 1)  # « One here. » a été joué.

    def test_moteur_autre_que_piper_refuse(self):
        voix = lire_voix.VoixResidente(donnees={"voix": {"moteur": "autre"}})
        with self.assertRaises(RuntimeError):
            voix.charger("en")
        self.assertFalse(voix.prechauffer("en"))


class MargeDeFin(unittest.TestCase):
    def test_attente_duree_plus_0_1_et_coupure_si_interrompu(self):
        faux_winsound = types.SimpleNamespace(
            SND_FILENAME=1, SND_ASYNC=2, appels=[])
        faux_winsound.PlaySound = lambda *a: faux_winsound.appels.append(a)

        class Interruption:
            def __init__(self, posee):
                self.posee, self.delais = posee, []

            def wait(self, timeout=None):
                self.delais.append(timeout)
                return self.posee

        with tempfile.TemporaryDirectory() as tmp:
            chemin = Path(tmp) / "a.wav"
            lire_voix.ecrire_wav(chemin, 1000, b"\0\0" * 2000)  # 2 s.
            with mock.patch.object(sys, "platform", "win32"), \
                    mock.patch.dict(sys.modules, {"winsound": faux_winsound}):
                attente = Interruption(False)
                self.assertTrue(lire_voix.jouer_wav(chemin, attente))
                self.assertAlmostEqual(attente.delais[0], 2.1, places=6)
                coupure = Interruption(True)
                self.assertFalse(lire_voix.jouer_wav(chemin, coupure))
                self.assertEqual(faux_winsound.appels[-1], (None, 0))
                with mock.patch.object(lire_voix.time, "sleep") as dormir:
                    lire_voix.jouer_wav(chemin)
                dormir.assert_called_once()
                self.assertAlmostEqual(dormir.call_args[0][0], 2.1, places=6)


class FauxProcessus:
    def __init__(self, commande, **_):
        self.commande = commande
        self.returncode = 0
        self.stderr = io.StringIO("")

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0


class DireDansLaBoucle(unittest.TestCase):
    def setUp(self):
        self.commandes = []

        def popen(commande, **kw):
            self.commandes.append(commande)
            return FauxProcessus(commande)

        patcheur = mock.patch.object(boucle_voix.subprocess, "Popen",
                                     side_effect=popen)
        patcheur.start()
        self.addCleanup(patcheur.stop)

    def _dire(self, *args, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            boucle_voix.dire(*args, **kwargs)

    def test_voix_residente_sans_sous_processus(self):
        voix = mock.Mock()
        voix.lire.return_value = True
        self._dire("Hello.", "en", threading.Event(), vitesse=1.3, voix=voix)
        self.assertEqual(self.commandes, [])
        self.assertEqual(voix.lire.call_args[0][2], 1.3)

    def test_repli_ne_relit_que_le_reste_et_transmet_la_vitesse(self):
        voix = mock.Mock()
        voix.lire.side_effect = lire_voix.ErreurLecture(OSError("x"), "Reste.")
        self._dire("Début. Reste.", "fr", threading.Event(), vitesse=0.8,
                   voix=voix)
        self.assertEqual(len(self.commandes), 1)
        commande = self.commandes[0]
        self.assertEqual(commande[commande.index("--texte") + 1], "Reste.")
        self.assertEqual(commande[commande.index("--vitesse") + 1], "0.8")

    def test_sans_voix_residente_lire_voix_recoit_la_vitesse(self):
        self._dire("Hi.", "en", threading.Event(), vitesse=1.5)
        self.assertIn("--vitesse", self.commandes[0])
        self.assertEqual(self.commandes[0][-1], "1.5")

    def test_vitesse_lue_dans_la_section_voix(self):
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            (racine / "config").mkdir()
            (racine / "config" / "config.toml").write_text(
                "[voix]\nvitesse = 1.25\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                config = boucle_voix.charger_config(racine)
        self.assertEqual(config["vitesse_voix"], 1.25)


class AnnonceDuMinuteur(unittest.TestCase):
    def test_annoncer_transmet_la_vitesse(self):
        with mock.patch.object(minuteur, "carillon"), \
                mock.patch.object(minuteur.subprocess, "run") as lancer, \
                contextlib.redirect_stdout(io.StringIO()):
            lancer.return_value = types.SimpleNamespace(returncode=0, stderr="")
            minuteur.annoncer("Timer done.", "en", vitesse=1.4)
            commande = lancer.call_args[0][0]
            self.assertEqual(commande[commande.index("--vitesse") + 1], "1.4")
            minuteur.annoncer("Timer done.", "en")
            commande = lancer.call_args[0][0]
            self.assertEqual(commande[commande.index("--vitesse") + 1],
                             f"{minuteur.VITESSE_VOIX:g}")


if __name__ == "__main__":
    unittest.main()
