"""Lot F1 — fiabilité des minuteurs : tests de non-régression.

1. Entrée mal formée (due absente, date illisible, date sans fuseau) :
   écartée (mise de côté) et signalée, les autres minuteurs sonnent ; le
   surveillant ne meurt pas.
2. timers.json corrompu : copie conservée avant de repartir de zéro ; un
   fichier momentanément illisible n'est jamais écrasé.
3. Annonce avant retrait : un minuteur dont l'annonce plante reste enregistré.
4. Le lanceur relance le surveillant de minuteurs (3 échecs rapprochés :
   avertissement, plus de relance).
5. Durée « inf » refusée par config_jarvis.duree_en_minutes.

Tout se passe dans un dossier temporaire : data/timers.json et logs/ ne sont
jamais touchés ; aucune fenêtre Windows ne s'ouvre (signalement simulé).
"""
import json
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import _chemins_lot01  # noqa: F401  (rend scripts/ importable)
import config_jarvis
import lancer_app
import minuteur


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dossier = Path(self.tmp.name)
        self.chemin = self.dossier / "timers.json"
        self.ref = datetime.now(minuteur.FUSEAU).replace(microsecond=0)
        self.signalements = []
        # Ni fenêtre Windows ni écriture dans logs/ pendant les tests.
        for nom, valeur in (
                ("_fenetre_windows", lambda message: None),
                ("DOSSIER_LOGS", self.dossier / "logs")):
            if hasattr(minuteur, nom):
                rustine = mock.patch.object(minuteur, nom, valeur)
                rustine.start()
                self.addCleanup(rustine.stop)
        if hasattr(minuteur, "_ECHECS_ANNONCE"):
            minuteur._ECHECS_ANNONCE.clear()
            self.addCleanup(minuteur._ECHECS_ANNONCE.clear)

    def signaler(self):
        """Remplace minuteur.signaler (garde la trace des signalements)."""
        return mock.patch.object(
            minuteur, "signaler",
            lambda message, *a, **k: self.signalements.append(message))

    def ecrire(self, minuteurs, next_id=10):
        self.chemin.write_text(json.dumps(
            {"timers": minuteurs, "next_id": next_id}, ensure_ascii=False),
            encoding="utf-8")

    def lire(self):
        return json.loads(self.chemin.read_text(encoding="utf-8"))

    def echu(self, ident, label="pâtes", secondes=5):
        moment = (self.ref - timedelta(seconds=secondes)).isoformat()
        return {"id": ident, "kind": "timer", "label": label,
                "due": moment, "minutes": 1, "created": moment}

    def futur(self, ident, label="colis", minutes=30):
        return {"id": ident, "kind": "rappel", "label": label,
                "due": (self.ref + timedelta(minutes=minutes)).isoformat(),
                "minutes": None, "created": self.ref.isoformat()}


# ---------------------------------------------------------------------------
# 1. Entrée mal formée
# ---------------------------------------------------------------------------

class EntreeMalFormee(_Base):
    def invalides(self):
        return [
            {"id": 1, "kind": "timer", "label": "sans échéance"},
            {"id": 2, "kind": "timer", "label": "illisible",
             "due": "pas une date"},
            {"id": 3, "kind": "timer", "label": "sans fuseau",
             "due": (self.ref - timedelta(minutes=1)).replace(
                 tzinfo=None).isoformat()},
        ]

    def test_entree_invalide_ecartee_et_les_autres_sonnent(self):
        self.ecrire(self.invalides() + [self.echu(4), self.futur(5)])
        annonces = []
        with self.signaler(), mock.patch.object(
                minuteur, "annoncer",
                lambda m, langue="fr", *a, **k: annonces.append(m)):
            messages = minuteur.declencher_dus(self.chemin, langue="fr")
        self.assertEqual(len(messages), 1)
        self.assertIn("pâtes", annonces[0])
        restants = [m["id"] for m in self.lire()["timers"]]
        self.assertEqual(restants, [5])  # l'échu sonné, les invalides écartés
        # Écartées mais jamais perdues : mises de côté, et signalées.
        mises_de_cote = json.loads(
            (self.dossier / "timers.json.invalides").read_text(
                encoding="utf-8"))
        self.assertEqual(sorted(m["minuteur"]["id"] for m in mises_de_cote),
                         [1, 2, 3])
        self.assertTrue(all(m.get("raison") for m in mises_de_cote))
        self.assertEqual(len(self.signalements), 1)
        self.assertIn("3", self.signalements[0])

    def test_entree_invalide_signalee_une_seule_fois(self):
        self.ecrire(self.invalides()[:1] + [self.futur(5)])
        with self.signaler(), mock.patch.object(minuteur, "annoncer"):
            minuteur.declencher_dus(self.chemin, langue="fr")
            minuteur.declencher_dus(self.chemin, langue="fr")
        self.assertEqual(len(self.signalements), 1)

    def test_surveillant_ne_meurt_pas_sur_une_entree_invalide(self):
        self.ecrire(self.invalides() + [self.futur(5)])
        sommeils = []

        def dormir(secondes):
            sommeils.append(secondes)
            if len(sommeils) >= 3:
                raise KeyboardInterrupt

        args = types.SimpleNamespace(donnees=self.chemin, langue="fr")
        with self.signaler(), mock.patch.object(minuteur, "annoncer"), \
                mock.patch.object(minuteur.time, "sleep", dormir):
            self.assertEqual(minuteur.cmd_surveiller(args), 0)
        self.assertEqual(len(sommeils), 3)
        self.assertEqual([m["id"] for m in self.lire()["timers"]], [5])

    def test_surveillant_survit_a_une_erreur_imprevue(self):
        self.ecrire([self.futur(5)])
        appels = {"n": 0}

        def declencher(*_a, **_k):
            appels["n"] += 1
            if appels["n"] == 2:
                raise RuntimeError("panne imprévue")
            return []

        sommeils = []

        def dormir(secondes):
            sommeils.append(secondes)
            if len(sommeils) >= 3:
                raise KeyboardInterrupt

        args = types.SimpleNamespace(donnees=self.chemin, langue="fr")
        with self.signaler(), \
                mock.patch.object(minuteur, "declencher_dus", declencher), \
                mock.patch.object(minuteur.time, "sleep", dormir):
            self.assertEqual(minuteur.cmd_surveiller(args), 0)
        self.assertGreaterEqual(appels["n"], 3)  # a continué après la panne

    def test_lister_tolere_une_entree_invalide(self):
        self.ecrire(self.invalides() + [self.futur(5)])
        args = types.SimpleNamespace(donnees=self.chemin)
        self.assertEqual(minuteur.cmd_lister(args), 0)


# ---------------------------------------------------------------------------
# 2. Fichier corrompu
# ---------------------------------------------------------------------------

class FichierCorrompu(_Base):
    def copies(self):
        return sorted(self.dossier.glob("timers.json.corrompu*"))

    def test_copie_conservee_avant_de_repartir_de_zero(self):
        self.chemin.write_text('{"timers": [{"id": 1, "due": ',
                               encoding="utf-8")
        with self.signaler():
            etat = minuteur.charger(self.chemin)
        self.assertEqual(etat["timers"], [])
        copies = self.copies()
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0].read_text(encoding="utf-8"),
                         '{"timers": [{"id": 1, "due": ')
        self.assertFalse(self.chemin.exists())
        self.assertEqual(len(self.signalements), 1)

    def test_structure_inattendue_compte_comme_corrompue(self):
        self.chemin.write_text('[1, 2, 3]', encoding="utf-8")
        with self.signaler():
            self.assertEqual(minuteur.charger(self.chemin)["timers"], [])
        self.assertEqual(len(self.copies()), 1)

    def test_nouveau_minuteur_apres_corruption_garde_la_copie(self):
        self.chemin.write_text("pas du json", encoding="utf-8")
        args = types.SimpleNamespace(donnees=self.chemin, a=None, minutes=5,
                                     etiquette="thé")
        with self.signaler():
            self.assertEqual(minuteur.cmd_demarrer(args), 0)
        self.assertEqual([m["label"] for m in self.lire()["timers"]], ["thé"])
        copies = self.copies()
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0].read_text(encoding="utf-8"), "pas du json")

    def test_fichier_momentanement_illisible_jamais_ecrase(self):
        self.ecrire([self.futur(1), self.futur(2, "pain")], next_id=3)
        avant = self.chemin.read_text(encoding="utf-8")
        args = types.SimpleNamespace(donnees=self.chemin, a=None, minutes=5,
                                     etiquette="thé")
        vraie_lecture = Path.read_bytes
        vrai_texte = Path.read_text

        def lecture_bloquee(chemin, *a, **k):
            if Path(chemin) == self.chemin:
                raise PermissionError("fichier utilisé par un autre processus")
            return vraie_lecture(chemin, *a, **k)

        def texte_bloque(chemin, *a, **k):
            if Path(chemin) == self.chemin:
                raise PermissionError("fichier utilisé par un autre processus")
            return vrai_texte(chemin, *a, **k)

        with self.signaler(), \
                mock.patch.object(Path, "read_bytes", lecture_bloquee), \
                mock.patch.object(Path, "read_text", texte_bloque), \
                mock.patch.object(minuteur.time, "sleep", lambda s: None):
            self.assertNotEqual(minuteur.cmd_demarrer(args), 0)
        self.assertEqual(self.chemin.read_text(encoding="utf-8"), avant)
        self.assertEqual(self.copies(), [])

    def test_next_id_absent_recalcule(self):
        self.chemin.write_text(json.dumps({"timers": [self.futur(7)]}),
                               encoding="utf-8")
        self.assertEqual(minuteur.charger(self.chemin)["next_id"], 8)


# ---------------------------------------------------------------------------
# 3. Annonce avant retrait
# ---------------------------------------------------------------------------

class AnnonceAvantRetrait(_Base):
    def test_minuteur_encore_enregistre_pendant_son_annonce(self):
        self.ecrire([self.echu(1)])
        vus = []

        def annoncer(message, langue="fr", *a, **k):
            vus.append([m["id"] for m in self.lire()["timers"]])

        with self.signaler(), mock.patch.object(minuteur, "annoncer",
                                                annoncer):
            minuteur.declencher_dus(self.chemin, langue="fr")
        self.assertEqual(vus, [[1]])
        self.assertEqual(self.lire()["timers"], [])

    def test_annonce_qui_plante_garde_le_minuteur(self):
        self.ecrire([self.echu(1), self.echu(2, "pain", secondes=2)])

        def annoncer(message, langue="fr", *a, **k):
            if "pâtes" in message:
                raise RuntimeError("haut-parleur débranché")

        with self.signaler(), mock.patch.object(minuteur, "annoncer",
                                                annoncer):
            messages = minuteur.declencher_dus(self.chemin, langue="fr")
        self.assertEqual(len(messages), 1)  # « pain » a sonné
        self.assertEqual([m["id"] for m in self.lire()["timers"]], [1])
        self.assertEqual(len(self.signalements), 1)
        self.assertIn("pâtes", self.signalements[0])

    def test_annonce_reessayee_puis_retiree(self):
        self.ecrire([self.echu(1)])
        with self.signaler(), mock.patch.object(
                minuteur, "annoncer", side_effect=RuntimeError("panne")):
            minuteur.declencher_dus(self.chemin, langue="fr")
        self.assertEqual(len(self.lire()["timers"]), 1)
        # Pendant le délai avant nouvel essai : pas de nouvelle tentative.
        with self.signaler(), mock.patch.object(minuteur,
                                                "annoncer") as annoncer:
            minuteur.declencher_dus(self.chemin, langue="fr")
        annoncer.assert_not_called()
        # Délai écoulé : l'annonce réussit, le minuteur est retiré.
        minuteur._ECHECS_ANNONCE.clear()
        with self.signaler(), mock.patch.object(minuteur,
                                                "annoncer") as annoncer:
            minuteur.declencher_dus(self.chemin, langue="fr")
        annoncer.assert_called_once()
        self.assertEqual(self.lire()["timers"], [])


# ---------------------------------------------------------------------------
# 4. Relance du surveillant par le lanceur
# ---------------------------------------------------------------------------

class _FauxProcessus:
    def __init__(self, code=None):
        self.code = code
        self.pid = 4242

    def poll(self):
        return self.code


class RelanceDuSurveillant(unittest.TestCase):
    def setUp(self):
        self.temps = [0.0]
        self.processus = []
        self.avertissements = []
        self.journal = []
        rustine = mock.patch.object(lancer_app, "journal",
                                    self.journal.append)
        rustine.start()
        self.addCleanup(rustine.stop)

    def fabrique(self):
        processus = _FauxProcessus()
        self.processus.append(processus)
        return processus

    def relance(self):
        return lancer_app.RelanceSurveillant(
            self.fabrique, horloge=lambda: self.temps[0],
            avertir=self.avertissements.append)

    def test_surveillant_mort_relance_et_journalise(self):
        relance = self.relance()
        relance.demarrer()
        self.processus[-1].code = 1
        self.temps[0] = 30.0
        relance.verifier()
        self.assertEqual(len(self.processus), 2)
        self.assertIs(relance.processus, self.processus[-1])
        self.assertTrue(any("relanc" in ligne for ligne in self.journal))
        self.assertEqual(self.avertissements, [])

    def test_sortie_normale_pas_relancee(self):
        # Code 0 : un autre surveillant tient déjà le verrou (session
        # complète) — le relancer tournerait en boucle.
        relance = self.relance()
        relance.demarrer()
        self.processus[-1].code = 0
        relance.verifier()
        relance.verifier()
        self.assertEqual(len(self.processus), 1)

    def test_trois_echecs_rapproches_avertissent_et_arretent(self):
        relance = self.relance()
        relance.demarrer()
        for _ in range(5):
            self.processus[-1].code = 1
            self.temps[0] += 20.0
            relance.verifier()
        self.assertEqual(len(self.processus), 3)  # 1 départ + 2 relances
        self.assertEqual(len(self.avertissements), 1)
        self.assertTrue(relance.abandonne)

    def test_echecs_espaces_toujours_relances(self):
        relance = self.relance()
        relance.demarrer()
        for _ in range(5):
            self.processus[-1].code = 1
            self.temps[0] += 3600.0
            relance.verifier()
        self.assertEqual(len(self.processus), 6)
        self.assertEqual(self.avertissements, [])

    def test_demarrage_impossible_compte_comme_echec(self):
        relance = lancer_app.RelanceSurveillant(
            lambda: None, horloge=lambda: self.temps[0],
            avertir=self.avertissements.append)
        relance.demarrer()
        for _ in range(3):
            self.temps[0] += 10.0
            relance.verifier()
        self.assertEqual(len(self.avertissements), 1)


# ---------------------------------------------------------------------------
# 5. Durée « inf »
# ---------------------------------------------------------------------------

class DureeInfinie(unittest.TestCase):
    def test_inf_refusee(self):
        for valeur in ("inf", "infj", "infh", "Infinity", "-inf", "nan",
                       float("inf"), float("nan")):
            with self.subTest(valeur=valeur):
                self.assertEqual(config_jarvis.duree_en_minutes(valeur, 30.0),
                                 30.0)

    def test_valeurs_normales_inchangees(self):
        self.assertEqual(config_jarvis.duree_en_minutes("7j", 1.0), 10080.0)
        self.assertEqual(config_jarvis.duree_en_minutes("90m", 1.0), 90.0)
        self.assertEqual(config_jarvis.duree_en_minutes(45, 1.0), 45.0)


if __name__ == "__main__":
    unittest.main()
