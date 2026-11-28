"""Lot LT — tâches longues (raisonnement long, sans abandon).

Verrouille : le déclenchement à la voix (FR / EN, sans modèle, durée dite =
budget) et la proposition par le cerveau (lancée sur un « oui » ≤ 30 s) ; le
plan, l'exécution étape par étape avec vérification, la persistance
(data/taches_longues.json, point de reprise après chaque étape) ; la reprise
après un redémarrage simulé ; les nouveaux essais après une erreur
transitoire (429, délai, injoignable : attentes croissantes, jamais
d'abandon) et l'arrêt net sur un blocage dur ; le budget (temps et étapes) ;
le débit (palier gratuit Groq) ; l'annonce de fin dans la langue du tour qui
a lancé la tâche et la lecture du résultat ; le suivi « où en est ma tâche ? »
lu dans le fichier ; le panneau de l'application ; le mode privé (mémoire
seulement, travailleur normal suspendu) ; la règle §1 entre les étapes.
Aucun réseau, aucun Chrome, aucune attente réelle : faux cerveau, fausse
horloge.
"""
import json
import shutil
import tempfile
import threading
import time
import unittest
import warnings
from pathlib import Path
from unittest import mock

import _chemins_lot01  # noqa: F401 — rend scripts/ importable.

import boucle_voix as bv
import taches_longues as tl
from test_r1_recherche import INJECTION, FausseSession

warnings.simplefilter("ignore", ResourceWarning)

CONFIG_FR = dict(bv.DEFAUTS, langue="fr", fournisseur_llm="groq")
CONFIG_EN = dict(CONFIG_FR, langue="en")


class ErreurHttp(Exception):
    """Erreur de SDK avec un code d'état (429, 503, 401…)."""

    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.status_code = code


class Horloge:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FauxCerveau:
    """appeler(messages, delai, max_tokens) : reconnaît l'appel à sa
    consigne (plan, étape, vérification, synthèse web R1, synthèse finale)."""

    def __init__(self, etapes=3, types=None, horloge=None, pas_s=0.0,
                 verdicts=None, erreurs=None, plan_brut=None):
        self.etapes = etapes
        self.types = types or ["reflexion"] * etapes
        self.horloge = horloge
        self.pas_s = pas_s
        self.verdicts = verdicts or {}      # n° d'étape -> réponse brute
        self.erreurs = list(erreurs or [])  # exceptions levées d'abord
        self.plan_brut = plan_brut
        self.appels = []                    # (genre, messages)
        self.sur_etape = None               # crochet(n° d'appel d'étape)

    def genre(self, messages):
        systeme = messages[0]["content"]
        if "planificateur" in systeme or "planner" in systeme:
            return "plan"
        if "Tu vérifies" in systeme or "You check" in systeme:
            return "verification"
        if "recherche web faite" in systeme or "web search done" in systeme:
            return "web"
        if "résultat final" in systeme or "final result" in systeme:
            return "synthese"
        return "etape"

    def __call__(self, messages, delai, max_tokens):
        if self.horloge is not None:
            self.horloge.t += self.pas_s
        if self.erreurs:
            raise self.erreurs.pop(0)
        genre = self.genre(messages)
        self.appels.append((genre, messages))
        if genre == "plan":
            if self.plan_brut is not None:
                return self.plan_brut
            return json.dumps({"titre": "Comparer les forfaits", "etapes": [
                {"description": f"Étape {n}", "type": self.types[n - 1],
                 "requete": f"requête {n}"}
                for n in range(1, self.etapes + 1)]})
        if genre == "verification":
            texte_user = messages[1]["content"]
            for n, brut in self.verdicts.items():
                if f"Étape : Étape {n}\n" in texte_user or \
                        f"Step: Étape {n}\n" in texte_user:
                    return brut
            return '{"ok": true}'
        if genre == "web":
            return ("Le forfait A est le moins cher. " + INJECTION)
        if genre == "synthese":
            return "Synthèse finale : le forfait A gagne."
        n = len([g for g, _ in self.appels if g == "etape"])
        if self.sur_etape is not None:
            self.sur_etape(n)
        return f"Résultat de l'étape numéro {n}."

    def nombre(self, genre):
        return len([g for g, _ in self.appels if g == genre])


class BaseTemp(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="jarvis-lt-"))
        self.chemin = self.dossier / "taches_longues.json"
        self.timers = self.dossier / "timers.json"
        self.horloge = Horloge()
        self.attentes = []
        self.config = dict(CONFIG_FR, fichier_taches=str(self.chemin),
                           fichier_recherches=str(self.dossier / "r.json"),
                           fichier_connaissances=str(self.dossier / "c.json"))
        self.config_en = dict(self.config, langue="en")
        bv.PRIVE.sortir()
        self.addCleanup(bv.PRIVE.sortir)
        self.addCleanup(setattr, bv.PRIVE, "suspendus", [])

    def tearDown(self):
        shutil.rmtree(self.dossier, ignore_errors=True)

    def attendre(self, secondes):
        self.attentes.append(round(secondes, 2))
        self.horloge.t += secondes
        return False

    def travailleur(self, cerveau, chemin=None, **options):
        options.setdefault("limiteur", tl.LimiteurJetons(0))
        return tl.Travailleur(chemin or self.chemin, cerveau,
                              bv.classer_erreur_cerveau,
                              horloge=self.horloge, attendre=self.attendre,
                              **options)

    def ajouter(self, objectif="compare les forfaits mobiles", langue="fr",
                **options):
        return tl.ajouter(self.chemin, objectif, langue, **options)["tache"]

    def lire(self):
        return json.loads(self.chemin.read_text(encoding="utf-8"))

    def tour(self, phrase, config=None, historique=None, confirmation=None,
             etat_tour=None, cerveau=None, travailleur=None):
        return bv.traiter_tour(
            phrase, config or self.config, cerveau or mock.Mock(),
            historique or [], self.timers,
            {} if confirmation is None else confirmation,
            etat_tour=etat_tour, travailleur_taches=travailleur)


# ---------------------------------------------------------------------------
# 1. Déclenchement (FR / EN, sans modèle) et proposition par le cerveau
# ---------------------------------------------------------------------------

class Declenchement(BaseTemp):
    def test_phrases_francaises(self):
        cas = {
            "c'est une longue tâche : compare les trois forfaits mobiles":
                ("compare les trois forfaits mobiles", None),
            "Jarvis, prends le temps qu'il faut pour planifier mon voyage au "
            "Japon.": ("planifier mon voyage au Japon", None),
            "travaille là-dessus pendant longtemps : analyse mes dépenses":
                ("analyse mes dépenses", None),
            "travaille là-dessus pendant 2 heures : écris un plan d'affaires":
                ("écris un plan d'affaires", 120.0),
            "travaille sur mon discours pendant une heure et demie":
                ("mon discours", 90.0),
            "c'est une grosse tâche": ("", None),
            "prends le temps qu'il faut": ("", None),
        }
        for phrase, (objectif, duree) in cas.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(tl.detecter_lancement(phrase),
                                 {"objectif": objectif, "duree_min": duree})

    def test_phrases_anglaises(self):
        cas = {
            "This is a long task: compare the best e-bikes of 2026.":
                ("compare the best e-bikes of 2026", None),
            "take as long as you need to write a study plan for Python":
                ("write a study plan for Python", None),
            "work on this for a long time: draft my cover letter":
                ("draft my cover letter", None),
            "work on this for 90 minutes: draft a cover letter":
                ("draft a cover letter", 90.0),
            "work on my essay for half an hour": ("my essay", 30.0),
            "take your time to review my CV": ("review my CV", None),
        }
        for phrase, (objectif, duree) in cas.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(tl.detecter_lancement(phrase),
                                 {"objectif": objectif, "duree_min": duree})

    def test_phrases_qui_ne_lancent_rien(self):
        for phrase in ("quelle heure est-il", "travaille là-dessus",
                       "work on it", "take your time",
                       "ne prends pas le temps qu'il faut",
                       "don't take as long as you need",
                       "mets un minuteur de 2 heures",
                       "c'est quoi une longue tâche en informatique ?"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(tl.detecter_lancement(phrase))

    def test_durees(self):
        self.assertEqual(tl.extraire_duree("pendant 1h30 : x")[0], 90.0)
        self.assertEqual(tl.extraire_duree("for two hours")[0], 120.0)
        self.assertEqual(tl.extraire_duree("pendant 45 minutes")[0], 45.0)
        self.assertEqual(tl.extraire_duree("pendant une demi-heure")[0],
                         30.0)
        # Une durée DANS l'objectif (après les deux-points) n'est pas le budget.
        self.assertIsNone(tl.extraire_duree(
            "c'est une longue tâche : un plan pour 3 heures de sport")[0])

    def test_lancement_par_la_voix_sans_modele(self):
        travailleur, cerveau = mock.Mock(), mock.Mock()
        etat_tour = {}
        reponse = self.tour("c'est une longue tâche : compare les forfaits",
                            cerveau=cerveau, travailleur=travailleur,
                            etat_tour=etat_tour)
        self.assertIn("C'est parti", reponse)
        self.assertIn("30 minutes", reponse)
        cerveau.repondre.assert_not_called()
        travailleur.signaler.assert_called_once()
        tache = self.lire()["taches"][0]
        self.assertEqual((tache["objectif"], tache["langue"], tache["etat"]),
                         ("compare les forfaits", "fr", "en_cours"))
        self.assertEqual(tache["budget"], {"duree_max_s": 1800.0,
                                           "max_etapes": 30})
        self.assertIn("Tâche longue lancée", etat_tour["historique"])

    def test_duree_dite_devient_le_budget_et_langue_du_tour(self):
        reponse = self.tour("work on this for 2 hours: draft a cover letter",
                            config=self.config_en, travailleur=mock.Mock())
        self.assertIn("budget of 2 hours", reponse)
        tache = self.lire()["taches"][0]
        self.assertEqual((tache["langue"], tache["budget"]["duree_max_s"]),
                         ("en", 7200.0))

    def test_budget_par_defaut_vient_du_reglage(self):
        config = dict(self.config, taches_longues=dict(
            tl.reglages({}), duree_max_minutes=45, max_etapes=12))
        self.tour("prends le temps qu'il faut pour réviser mon CV",
                  config=config, travailleur=mock.Mock())
        tache = self.lire()["taches"][0]
        self.assertEqual(tache["budget"], {"duree_max_s": 2700.0,
                                           "max_etapes": 12})
        self.assertEqual(tl.reglages({"taches_longues": {
            "duree_max_minutes": 99999, "max_etapes": 500}}),
            {"duree_max_minutes": 1440.0, "max_etapes": 30,
             "jetons_par_minute": 8000, "effort": "moyen"})

    def test_la_dessus_reprend_la_phrase_precedente(self):
        historique = [{"role": "user", "content": "compare trois mini-PC"},
                      {"role": "assistant", "content": "D'accord."}]
        self.tour("prends le temps qu'il faut", historique=historique,
                  travailleur=mock.Mock())
        self.assertEqual(self.lire()["taches"][0]["objectif"],
                         "compare trois mini-PC")
        self.assertEqual(self.tour("c'est une longue tâche",
                                   config=dict(self.config, fichier_taches=str(
                                       self.dossier / "autre.json"))),
                         "Sur quoi veux-tu que je travaille, Julien ?")

    def test_sans_travailleur_la_tache_attend_le_prochain_lancement(self):
        reponse = self.tour("c'est une longue tâche : x", travailleur=None)
        self.assertIn("prochain lancement", reponse)

    def test_doublon_et_file_pleine(self):
        for n in range(tl.MAX_EN_FILE):
            self.ajouter(f"objectif {n}")
        self.assertIn("déjà", self.tour("c'est une longue tâche : objectif 0",
                                        travailleur=mock.Mock()))
        self.assertIn("3 tâches longues en attente",
                      self.tour("c'est une longue tâche : objectif neuf",
                                travailleur=mock.Mock()))

    def test_le_cerveau_propose_et_seul_un_oui_lance(self):
        cerveau = mock.Mock()
        cerveau.repondre.return_value = {
            "texte": "", "utilisation": {}, "appels_outils": [{
                "nom": "proposer_tache_longue", "id": "a1",
                "arguments": {"objectif": "planifier mon déménagement"}}]}
        cerveau.message_assistant.return_value = {"role": "assistant"}
        confirmation = {}
        reponse = self.tour("aide-moi à planifier tout mon déménagement",
                            cerveau=cerveau, confirmation=confirmation)
        self.assertEqual(reponse, tl.texte("fr", "proposition"))
        self.assertFalse(self.chemin.exists())  # rien n'est lancé.
        self.assertEqual(confirmation["outil"], "tache_longue")
        travailleur = mock.Mock()
        reponse = self.tour("oui", confirmation=confirmation,
                            travailleur=travailleur)
        self.assertIn("C'est parti", reponse)
        self.assertEqual(self.lire()["taches"][0]["objectif"],
                         "planifier mon déménagement")
        travailleur.signaler.assert_called_once()

    def test_proposition_perimee_ou_refusee(self):
        confirmation = {}
        bv.armer_proposition_tache(confirmation, "x", "fr")
        confirmation["arme_a"] -= bv.DELAI_CONFIRMATION_S + 1
        cerveau = mock.Mock()
        cerveau.repondre.return_value = {"texte": "Oui ?", "utilisation": {},
                                         "appels_outils": []}
        self.tour("oui", confirmation=confirmation, cerveau=cerveau)
        self.assertFalse(self.chemin.exists())
        bv.armer_proposition_tache(confirmation, "x", "fr")
        self.assertEqual(self.tour("non merci", confirmation=confirmation),
                         tl.texte("fr", "proposition_refusee"))
        self.assertFalse(self.chemin.exists())

    def test_outil_declare_et_jamais_permis_apres_lecture_externe(self):
        for fournisseur in ("groq", "anthropic"):
            for langue in ("fr", "en"):
                noms = {o.get("name") or o["function"]["name"]
                        for o in bv.outils_pour(fournisseur, langue)}
                self.assertIn("proposer_tache_longue", noms)
        self.assertNotIn("proposer_tache_longue", bv.OUTILS_SANS_ECRITURE)
        self.assertNotIn("proposer_tache_longue",
                         bv.OUTILS_APRES_NOTE_EXTERNE)


# ---------------------------------------------------------------------------
# 2. Plan, étapes vérifiées, persistance
# ---------------------------------------------------------------------------

class PlanEtPersistance(BaseTemp):
    def test_plan_puis_etapes_verifiees_puis_resultat(self):
        self.ajouter()
        cerveau = FauxCerveau(etapes=3)
        fins = []
        finale = self.travailleur(cerveau, sur_fin=fins.append).traiter_une()
        self.assertEqual(finale["etat"], "terminee")
        self.assertEqual(finale["resultat"],
                         "Synthèse finale : le forfait A gagne.")
        self.assertEqual(fins, [finale])
        # Un plan, puis pour chaque étape : exécution puis vérification.
        genres = [g for g, _ in cerveau.appels]
        self.assertEqual(genres, ["plan", "etape", "verification", "etape",
                                  "verification", "etape", "verification",
                                  "synthese"])
        tache = self.lire()["taches"][0]
        self.assertEqual(tache["titre"], "Comparer les forfaits")
        self.assertEqual([e["etat"] for e in tache["plan"]], ["faite"] * 3)
        self.assertEqual(tache["plan"][1]["resultat"],
                         "Résultat de l'étape numéro 2.")
        self.assertEqual((tache["etapes_faites"], tache["executions"]),
                         (3, 3))
        self.assertIsNone(tache["etape_en_cours"])
        self.assertEqual(tl.progression(tache), "3/3")
        self.assertEqual(list(self.dossier.glob("*.tmp")), [])

    def test_chaque_etape_voit_l_objectif_le_plan_et_les_precedentes(self):
        self.ajouter()
        cerveau = FauxCerveau(etapes=3)
        self.travailleur(cerveau).traiter_une()
        troisieme = [m for g, m in cerveau.appels if g == "etape"][2]
        contenu = troisieme[1]["content"]
        self.assertIn("compare les forfaits mobiles", contenu)
        self.assertIn("1. Étape 1\n2. Étape 2\n3. Étape 3", contenu)
        self.assertIn("Résultat de l'étape numéro 2.", contenu)
        self.assertIn("Étape à faire maintenant (3/3) : Étape 3", contenu)

    def test_point_de_reprise_ecrit_apres_chaque_etape(self):
        self.ajouter()
        cerveau = FauxCerveau(etapes=3)
        vus = []
        cerveau.sur_etape = lambda n: vus.append(
            (n, self.lire()["taches"][0]["etapes_faites"],
             self.lire()["taches"][0]["etape_en_cours"]))
        self.travailleur(cerveau).traiter_une()
        # Pendant l'étape n : n-1 faites (déjà sur le disque), étape n-1 notée
        # « en cours ».
        self.assertEqual(vus, [(1, 0, 0), (2, 1, 1), (3, 2, 2)])

    def test_verification_refusee_reessaie_puis_bloque(self):
        self.ajouter()
        cerveau = FauxCerveau(etapes=3, verdicts={
            2: '{"ok": false, "remarque": "il manque les prix"}'})
        finale = self.travailleur(cerveau).traiter_une()
        self.assertEqual((finale["etat"], finale["raison"]),
                         ("bloquee", "verification"))
        self.assertEqual(finale["detail"], "Étape 2")
        self.assertEqual(cerveau.nombre("etape"), 1 + tl.MAX_ESSAIS_ETAPE)
        nouvel_essai = [m for g, m in cerveau.appels if g == "etape"][2]
        self.assertIn("il manque les prix", nouvel_essai[1]["content"])
        self.assertIn("Résultat de l'étape numéro 1", finale["resultat"])
        annonce = tl.formater_annonce(finale, "fr")
        self.assertIn("n'a pas passé la vérification", annonce)
        self.assertIn("Fait : 1 étape sur 3.", annonce)
        self.assertIn("Il reste : Étape 2 et Étape 3.", annonce)

    def test_verification_reussie_au_deuxieme_essai(self):
        self.ajouter()
        cerveau = FauxCerveau(etapes=2)
        reponses = iter(['{"ok": false, "remarque": "trop court"}',
                         '{"ok": true}'])
        cerveau.verdicts = {}
        original = cerveau.__call__

        def appel(messages, delai, max_tokens):
            if cerveau.genre(messages) == "verification" and \
                    "Étape 1\n" in messages[1]["content"]:
                cerveau.appels.append(("verification", messages))
                return next(reponses, '{"ok": true}')
            return original(messages, delai, max_tokens)

        finale = self.travailleur(appel).traiter_une()
        self.assertEqual(finale["etat"], "terminee")
        self.assertEqual(self.lire()["taches"][0]["executions"], 3)

    def test_analyse_du_plan(self):
        plan = tl.analyser_plan('Voici : {"titre": "T", "etapes": ['
                                '{"description": "a", "type": "recherche_web",'
                                ' "requete": "q"}, {"description": "b", '
                                '"type": "pirater"}]} fin')
        self.assertEqual(plan["titre"], "T")
        self.assertEqual([(e["type"], e["requete"]) for e in plan["etapes"]],
                         [("recherche_web", "q"), ("reflexion", "b")])
        lignes = tl.analyser_plan("1. Lister\n2) Comparer\n3. Rédiger")
        self.assertEqual([e["description"] for e in lignes["etapes"]],
                         ["Lister", "Comparer", "Rédiger"])
        self.assertIsNone(tl.analyser_plan("je ne sais pas"))
        self.assertEqual(len(tl.analyser_plan(json.dumps(
            {"etapes": [f"e{n}" for n in range(100)]}))["etapes"]),
            tl.LONGUEUR_MAX_PLAN)

    def test_plan_illisible_bloque_proprement(self):
        self.ajouter()
        finale = self.travailleur(FauxCerveau(plan_brut="hmm")).traiter_une()
        self.assertEqual((finale["etat"], finale["raison"]),
                         ("bloquee", "plan"))
        self.assertIn("découper la tâche", tl.formater_annonce(finale, "fr"))

    def test_verdicts(self):
        self.assertEqual(tl.analyser_verdict('{"ok": true}'), (True, ""))
        self.assertEqual(tl.analyser_verdict(
            '```json\n{"ok": false, "remarque": "x"}\n```'), (False, "x"))
        self.assertFalse(tl.analyser_verdict("Non, incomplet.")[0])
        self.assertTrue(tl.analyser_verdict("")[0])

    def test_fichier_illisible_garde_une_copie(self):
        self.chemin.write_text("{cassé", encoding="utf-8")
        self.assertEqual(tl.lister(self.chemin), [])
        self.assertTrue(self.chemin.with_name(
            "taches_longues.json.illisible").exists())

    def test_annulation(self):
        t = self.ajouter()
        tl.point_de_reprise(self.chemin, t["id"], demarree=True, plan=[
            {"description": "a", "etat": "faite", "resultat": "fait A"},
            {"description": "b", "etat": "a_faire"}], etapes_faites=1)
        reponse = self.tour("annule ma tâche longue")
        self.assertIn("j'abandonne la tâche", reponse)
        self.assertIn("Il reste : b.", reponse)
        tache = self.lire()["taches"][0]
        self.assertEqual((tache["etat"], tache["raison"]),
                         ("bloquee", "annulee"))
        self.assertEqual(tl.a_annoncer(self.chemin), [])
        # Le travailleur voit l'annulation à son prochain point de reprise.
        self.assertIsNone(tl.point_de_reprise(self.chemin, t["id"],
                                              etapes_faites=2))
        self.assertEqual(self.tour("cancel my task", config=self.config_en),
                         "No long task is running, Julien.")


# ---------------------------------------------------------------------------
# 3. Reprise après redémarrage simulé
# ---------------------------------------------------------------------------

class RepriseApresRedemarrage(BaseTemp):
    def test_reprend_la_ou_elle_s_etait_arretee(self):
        self.ajouter()
        premier = FauxCerveau(etapes=4)
        travailleur = self.travailleur(premier)
        # « Fermeture de Jarvis » pendant la 3e étape.
        premier.sur_etape = lambda n: n == 3 and travailleur.arreter()
        self.assertIsNone(travailleur.traiter_une())
        avant = self.lire()["taches"][0]
        self.assertEqual((avant["etat"], avant["etapes_faites"],
                          avant["etape_en_cours"]), ("en_cours", 2, 2))
        temps_avant = avant["temps_utilise_s"]

        bilan = tl.reprendre_au_demarrage(self.chemin)
        self.assertEqual([t["id"] for t in bilan["reprises"]], [avant["id"]])
        self.assertEqual(
            tl.formater_reprise(bilan["reprises"][0], "fr"),
            "Je reprends ta tâche longue « Comparer les forfaits » là où je "
            "l'avais laissée : étape 3 sur 4.")
        self.assertEqual(
            tl.formater_reprise(bilan["reprises"][0], "en"),
            "I'm picking your long task \"Comparer les forfaits\" back up "
            "where I left off: step 3 of 4.")

        second = FauxCerveau(etapes=4)
        finale = self.travailleur(second).traiter_une()
        self.assertEqual(finale["etat"], "terminee")
        # Pas de nouveau plan ; seules les étapes 3 et 4 sont faites.
        self.assertEqual(second.nombre("plan"), 0)
        self.assertEqual(second.nombre("etape"), 2)
        self.assertEqual(finale["plan"][0]["resultat"],
                         "Résultat de l'étape numéro 1.")
        self.assertEqual(finale["reprises"], 1)
        self.assertGreaterEqual(finale["temps_utilise_s"], temps_avant)

    def test_annonce_de_reprise_au_demarrage_de_la_boucle(self):
        t = self.ajouter(langue="en")
        tl.prendre_suivante(self.chemin)
        bilan = tl.reprendre_au_demarrage(self.chemin)
        self.assertEqual(bilan["reprises"][0]["id"], t["id"])
        self.assertIn("picking your long task",
                      tl.formater_reprise(bilan["reprises"][0], "en"))
        # Une tâche jamais démarrée reste simplement en file.
        self.ajouter("autre chose")
        self.assertEqual(len(tl.reprendre_au_demarrage(self.chemin)
                             ["reprises"]), 1)

    def test_trop_d_interruptions_bloque_proprement(self):
        t = self.ajouter()
        tl.prendre_suivante(self.chemin)
        for _ in range(tl.MAX_REPRISES):
            self.assertTrue(tl.reprendre_au_demarrage(self.chemin)
                            ["reprises"])
        bilan = tl.reprendre_au_demarrage(self.chemin)
        self.assertEqual(bilan["echecs"], [t["id"]])
        self.assertEqual(self.lire()["taches"][0]["raison"], "interrompue")


# ---------------------------------------------------------------------------
# 4. Erreurs transitoires : attendre et réessayer, jamais abandonner
# ---------------------------------------------------------------------------

class ErreursTransitoires(BaseTemp):
    def test_429_delai_et_injoignable_puis_succes(self):
        self.ajouter()
        cerveau = FauxCerveau(etapes=2, erreurs=[
            ErreurHttp(429), TimeoutError("lent"), ErreurHttp(503)])
        etats = []
        original = tl.point_de_reprise

        def espion(chemin, ident, **champs):
            if "attente" in champs:
                etats.append(champs["attente"] and champs["attente"]["raison"])
            return original(chemin, ident, **champs)

        with mock.patch.object(tl, "point_de_reprise", espion):
            finale = self.travailleur(cerveau).traiter_une()
        self.assertEqual(finale["etat"], "terminee")
        self.assertEqual(self.attentes, [5.0, 10.0, 20.0])  # croissantes.
        self.assertEqual(etats, ["limite", "delai", "injoignable", None])
        self.assertIsNone(finale["attente"])

    def test_etat_pendant_l_attente_dit_que_jarvis_reessaie(self):
        t = self.ajouter()
        tl.point_de_reprise(self.chemin, t["id"], demarree=True,
                            attente={"raison": "limite", "essais": 2})
        reponse = self.tour("où en est ma tâche ?")
        self.assertIn("limite de débit de Groq", reponse)
        self.assertIn("je réessaie", reponse)

    def test_jamais_d_abandon_avant_la_fin_du_budget(self):
        self.ajouter(duree_max_s=600)
        cerveau = FauxCerveau(erreurs=[ErreurHttp(503)] * 1000)
        finale = self.travailleur(cerveau).traiter_une()
        self.assertEqual((finale["etat"], finale["raison"]),
                         ("bloquee", "budget_temps"))
        self.assertEqual(self.attentes[:6], [5.0, 10.0, 20.0, 40.0, 80.0,
                                             120.0])
        self.assertLessEqual(sum(self.attentes), 600.0 + 1e-6)
        self.assertIn("Aucune étape n'était encore faite",
                      tl.formater_annonce(finale, "fr"))

    def test_blocage_dur_arrete_net_et_dit_ce_qui_bloque(self):
        self.ajouter()
        cerveau = FauxCerveau(etapes=3)
        original = cerveau.__call__

        def appel(messages, delai, max_tokens):
            if cerveau.nombre("etape") >= 1 and \
                    cerveau.genre(messages) == "etape":
                raise ErreurHttp(401)
            return original(messages, delai, max_tokens)

        finale = self.travailleur(appel).traiter_une()
        self.assertEqual((finale["etat"], finale["raison"]),
                         ("bloquee", "cle"))
        self.assertEqual(self.attentes, [])  # aucune attente inutile.
        annonce = tl.formater_annonce(finale, "fr")
        self.assertIn("la clé du cerveau est absente ou refusée", annonce)
        self.assertIn("Fait : 1 étape sur 3.", annonce)
        self.assertIn("Veux-tu que je te lise ce qui est fait ?", annonce)

    def test_cle_absente_du_cerveau_du_travailleur(self):
        appeler = bv.fabriquer_appel_tache(dict(CONFIG_FR,
                                                fournisseur_llm="inconnu"))
        with mock.patch.object(bv, "creer_cerveau",
                               side_effect=SystemExit(3)):
            with self.assertRaises(tl.BlocageDur) as contexte:
                appeler([{"role": "user", "content": "x"}], 5, 100)
        self.assertEqual(contexte.exception.raison, "cle")

    def test_debit_du_palier_gratuit(self):
        limiteur = tl.LimiteurJetons(8000, horloge=self.horloge)
        self.assertEqual(limiteur.attente(3000), 0.0)
        limiteur.noter(5000)  # la boucle vocale vient de parler.
        self.assertAlmostEqual(limiteur.attente(2000), 60.0)
        self.horloge.t += 61
        self.assertEqual(limiteur.attente(2000), 0.0)
        self.assertEqual(tl.LimiteurJetons(0).attente(10 ** 6), 0.0)
        # Le travailleur attend que la fenêtre se libère avant d'appeler.
        self.ajouter()
        plein = tl.LimiteurJetons(8000, horloge=self.horloge)
        plein.noter(6000)
        finale = self.travailleur(FauxCerveau(etapes=1),
                                  limiteur=plein).traiter_une()
        self.assertEqual(finale["etat"], "terminee")
        self.assertTrue(self.attentes and self.attentes[0] >= 59.0)


# ---------------------------------------------------------------------------
# 5. Budget : temps et étapes
# ---------------------------------------------------------------------------

class Budget(BaseTemp):
    def test_budget_de_temps(self):
        self.ajouter(duree_max_s=900)
        cerveau = FauxCerveau(etapes=4, horloge=self.horloge, pas_s=300)
        finale = self.travailleur(cerveau).traiter_une()
        self.assertEqual((finale["etat"], finale["raison"]),
                         ("bloquee", "budget_temps"))
        self.assertEqual(finale["etapes_faites"], 1)
        self.assertLessEqual(finale["temps_utilise_s"], 900.0)
        annonce = tl.formater_annonce(finale, "fr")
        self.assertIn("le budget de 15 minutes est épuisé", annonce)
        self.assertIn("Fait : 1 étape sur 4.", annonce)
        self.assertIn("Il reste : Étape 2, Étape 3 et Étape 4.", annonce)
        self.assertIn("Résultat de l'étape numéro 1", finale["resultat"])
        self.assertEqual(tl.etiquette_etat(finale, "fr"), "budget épuisé")

    def test_budget_d_etapes(self):
        self.ajouter(max_etapes=3)
        cerveau = FauxCerveau(etapes=5)
        finale = self.travailleur(cerveau).traiter_une()
        self.assertEqual((finale["raison"], finale["etapes_faites"]),
                         ("budget_etapes", 3))
        self.assertEqual(cerveau.nombre("etape"), 3)
        annonce = tl.formater_annonce(finale, "en")
        self.assertIn("the maximum of 3 steps is reached", annonce)
        self.assertIn("Still to do: Étape 4 and Étape 5.", annonce)

    def test_maximum_trente_etapes_et_duree_bornee(self):
        t = self.ajouter(duree_max_s=10 ** 9, max_etapes=500)
        self.assertEqual(t["budget"], {"duree_max_s": 1440 * 60.0,
                                       "max_etapes": 30})
        self.assertEqual(tl.DUREE_MAX_DEFAUT_MIN, 30.0)

    def test_le_temps_ferme_ne_compte_pas(self):
        """Le budget compte le travail, pas les heures où Jarvis est fermé."""
        self.ajouter(duree_max_s=600)
        premier = FauxCerveau(etapes=2, horloge=self.horloge, pas_s=100)
        travailleur = self.travailleur(premier)
        premier.sur_etape = lambda n: travailleur.arreter()
        travailleur.traiter_une()
        self.horloge.t += 10 * 3600  # Jarvis fermé dix heures.
        tl.reprendre_au_demarrage(self.chemin)
        finale = self.travailleur(FauxCerveau(etapes=2)).traiter_une()
        self.assertEqual(finale["etat"], "terminee")


# ---------------------------------------------------------------------------
# 6. Suivi et annonce de fin
# ---------------------------------------------------------------------------

class SuiviEtAnnonce(BaseTemp):
    def preparer_en_cours(self):
        t = self.ajouter()
        plan = [{"description": f"étape {n}", "etat": "faite" if n <= 2
                 else "a_faire", "resultat": "r"} for n in range(1, 5)]
        tl.point_de_reprise(self.chemin, t["id"], demarree=True, plan=plan,
                            etapes_faites=2, temps_utilise_s=720.0,
                            titre="Forfaits")
        return t

    def test_ou_en_est_ma_tache_lu_dans_le_fichier(self):
        self.preparer_en_cours()
        travailleur, cerveau = mock.Mock(), mock.Mock()
        reponse = self.tour("où en est ma tâche ?", travailleur=travailleur,
                            cerveau=cerveau)
        self.assertEqual(
            reponse, "Ta tâche « Forfaits » avance, Julien : 2 étapes faites "
            "sur 4, je suis sur « étape 3 ». 12 minutes sur un budget de 30 "
            "minutes.")
        self.assertEqual(travailleur.mock_calls, [])  # jamais réveillé.
        cerveau.repondre.assert_not_called()
        self.assertIn("2 steps done out of 4",
                      self.tour("how's my task going?",
                                config=self.config_en))

    def test_qu_est_ce_qui_reste(self):
        self.preparer_en_cours()
        self.assertEqual(self.tour("qu'est-ce qui reste ?"),
                         "Il reste 2 étapes sur « Forfaits », Julien : "
                         "étape 3 et étape 4.")
        self.assertEqual(self.tour("what's left?", config=self.config_en),
                         "There are 2 steps left on \"Forfaits\", Julien: "
                         "étape 3 and étape 4.")

    def test_qu_est_ce_qui_reste_sans_tache_va_au_cerveau(self):
        cerveau = mock.Mock()
        cerveau.repondre.return_value = {"texte": "Rien.", "utilisation": {},
                                         "appels_outils": []}
        self.assertEqual(self.tour("qu'est-ce qui reste ?", cerveau=cerveau),
                         "Rien.")
        self.assertEqual(self.tour("où en est ma tâche ?"),
                         "Tu n'as aucune tâche longue, Julien.")

    def test_fin_annoncee_dans_la_langue_du_tour_qui_l_a_lancee(self):
        t = self.ajouter("compare e-bikes", langue="en")
        tl.prendre_suivante(self.chemin)
        tl.terminer(self.chemin, t["id"], "Bike A wins.", False, 60)
        annonces = bv.annonces_taches(self.config)  # boucle réglée en fr.
        self.assertEqual(annonces, [(
            "I've finished your long task \"compare e-bikes\", Julien. Would "
            "you like me to read you the result?", "en", t["id"])])
        self.assertEqual(bv.annonces_taches(self.config), [])  # une fois.

    def test_oui_lit_le_resultat_sans_le_redonner_au_modele(self):
        t = self.ajouter()
        tl.prendre_suivante(self.chemin)
        tl.terminer(self.chemin, t["id"], "Le forfait A gagne.", True, 60)
        confirmation, etat_tour = {}, {}
        bv.armer_lecture_tache(confirmation, t["id"])
        reponse = self.tour("oui", confirmation=confirmation,
                            etat_tour=etat_tour)
        self.assertEqual(reponse, "Voici le résultat de ta tâche « compare "
                                  "les forfaits mobiles », Julien : Le "
                                  "forfait A gagne.")
        self.assertTrue(etat_tour["externe"])
        self.assertNotIn("forfait A", etat_tour["historique"])
        self.assertTrue(self.lire()["taches"][0]["lue"])
        bv.armer_lecture_tache(confirmation, t["id"])
        self.assertEqual(self.tour("non", confirmation=confirmation),
                         tl.texte("fr", "lecture_refusee"))

    def test_suivi_d_une_tache_finie_propose_la_lecture(self):
        t = self.ajouter()
        tl.prendre_suivante(self.chemin)
        tl.terminer(self.chemin, t["id"], "R.", False, 60)
        confirmation = {}
        self.assertIn("Veux-tu que je te lise le résultat",
                      self.tour("où en est ma tâche ?",
                                confirmation=confirmation))
        self.assertEqual(confirmation["outil"], "lire_tache_longue")
        self.assertIn("R.", self.tour("lis-moi le résultat de ma tâche"))

    def test_textes_memes_cles_en_fr_et_en(self):
        self.assertEqual(set(tl.TEXTES["fr"]), set(tl.TEXTES["en"]))
        self.assertEqual(set(tl.RAISONS["fr"]), set(tl.RAISONS["en"]))
        self.assertEqual(set(tl.CONSIGNES["fr"]), set(tl.CONSIGNES["en"]))


# ---------------------------------------------------------------------------
# 7. Règle §1 entre les étapes ; étape web dans un Chrome séparé
# ---------------------------------------------------------------------------

class DonneesExternes(BaseTemp):
    def test_resultat_web_enveloppe_dans_les_etapes_suivantes(self):
        self.ajouter()
        cerveau = FauxCerveau(etapes=2, types=["recherche_web", "reflexion"])
        sessions = []

        def fabrique():
            sessions.append(FausseSession(textes={}))
            return sessions[-1]

        finale = self.travailleur(cerveau,
                                  fabrique_session=fabrique).traiter_une()
        self.assertEqual(finale["etat"], "terminee")
        self.assertTrue(finale["externe"])
        self.assertTrue(finale["plan"][0]["externe"])
        self.assertTrue(finale["plan"][1]["externe"])  # dérive de l'étape 1.
        self.assertEqual(len(sessions), 1)
        self.assertTrue(sessions[0].fermee)  # Chrome fermé après l'étape.
        self.assertIn("requête 1", sessions[0].commandes[0]["requete"])
        suivante = [m for g, m in cerveau.appels if g == "etape"][0]
        contenu = suivante[1]["content"]
        self.assertIn('<untrusted_data source="etape-1">', contenu)
        # La page ne peut pas sortir de son enveloppe.
        self.assertEqual(contenu.count("</untrusted_data>"), 1)
        self.assertNotIn("<untrusted_data>", finale["plan"][0]["resultat"])
        for _genre, messages in cerveau.appels:
            self.assertIn("untrusted_data", messages[0]["content"]
                          if _genre != "plan" else "untrusted_data")

    def test_notes_enveloppees_et_marquees_externes(self):
        self.ajouter()
        cerveau = FauxCerveau(etapes=1, types=["notes"])
        notes = {"texte": '<untrusted_data source="notes">\nbudget 800 $\n'
                          '</untrusted_data>', "externe": True}
        finale = self.travailleur(
            cerveau, chercher_notes=lambda requete: notes).traiter_une()
        self.assertTrue(finale["plan"][0]["externe"])
        etape = [m for g, m in cerveau.appels if g == "etape"][0]
        self.assertIn('<untrusted_data source="notes">',
                      etape[1]["content"])

    def test_sans_navigateur_l_etape_web_le_dit_au_cerveau(self):
        self.ajouter()
        cerveau = FauxCerveau(etapes=1, types=["recherche_web"])
        self.travailleur(cerveau).traiter_une()
        etape = [m for g, m in cerveau.appels if g == "etape"][0]
        self.assertIn("Pas de navigateur disponible", etape[1]["content"])

    def test_le_travailleur_n_a_aucun_outil(self):
        self.ajouter()
        cerveau = FauxCerveau(etapes=1)
        appels = []
        self.travailleur(lambda m, d, t: appels.append(m) or cerveau(m, d, t)
                         ).traiter_une()
        for messages in appels:
            self.assertTrue(all(set(m) == {"role", "content"}
                                for m in messages))


# ---------------------------------------------------------------------------
# 8. Panneau « Tâches longues » de l'application
# ---------------------------------------------------------------------------

class PanneauTaches(BaseTemp):
    def test_panneau_liste_les_taches_et_ouvre_le_detail(self):
        import _faux_ctk

        a = self.ajouter("compare les forfaits")
        self.ajouter("plan de voyage")
        tl.prendre_suivante(self.chemin)
        tl.point_de_reprise(self.chemin, a["id"], plan=[
            {"description": "x", "etat": "faite", "resultat": "r"},
            {"description": "y", "etat": "a_faire"}], etapes_faites=1)
        app, _ctk = _faux_ctk.charger_app(nom="app_lt")
        taches = app.charger_taches(self.chemin)
        self.assertEqual(app.formater_taches(taches, "fr"), (
            "• plan de voyage — 0/? · en attente",
            "• compare les forfaits — 1/2 · en cours"))
        self.assertEqual(app.formater_taches([], "en"), ("No long tasks.",))
        self.assertEqual([app.statut_tache(t) for t in taches],
                         ["attente", "actif"])
        self.assertEqual(app.charger_taches(self.dossier / "absent.json"), [])
        for theme in ("or_et_nuit", "centre_de_commande"):
            with self.subTest(theme=theme):
                app, _ctk = _faux_ctk.charger_app(nom=f"app_lt_{theme}")
                fenetre = _faux_ctk.creer_application(app, self.dossier, [],
                                                      theme=theme)
                fenetre._rafraichir_taches(taches)
                self.assertEqual(
                    len(fenetre.conteneur_taches.winfo_children()), 2)
                fenetre.ouvrir_tache(taches[1])  # ne plante pas.
                fenetre._rafraichir_taches([])
                self.assertEqual(
                    len(fenetre.conteneur_taches.winfo_children()), 1)
                for nom in ("panneau_minuteurs", "panneau_recherches",
                            "panneau_taches", "panneau_connaissances"):
                    self.assertTrue(hasattr(fenetre, nom))
        etats = app.etats_agents({"etat": "repos"}, [], [], True, taches)
        self.assertEqual(etats["taches"], "actif")
        self.assertIn("taches", app.AGENTS)

    def test_etiquettes(self):
        t = self.ajouter()
        self.assertEqual(tl.etiquette_etat(t, "fr"), "en attente")
        t = tl.prendre_suivante(self.chemin)
        self.assertEqual(tl.etiquette_etat(t, "en"), "planning")
        t["attente"] = {"raison": "limite"}
        self.assertEqual(tl.etiquette_etat(t, "fr"), "réessaie bientôt")


# ---------------------------------------------------------------------------
# 9. Mode privé
# ---------------------------------------------------------------------------

class ModePrive(BaseTemp):
    def entrer(self, **options):
        return bv.basculer_mode_prive({"action": "entrer", "langue": "fr"},
                                      [], {}, None, "fr", **options)

    def test_tache_privee_en_memoire_seulement_puis_jetee(self):
        travailleur_prive = mock.Mock()
        self.entrer(fabrique_travailleur_taches=lambda m: travailleur_prive)
        travailleur_prive.demarrer.assert_called_once()
        self.assertIsInstance(bv.chemin_taches(self.config), tl.Memoire)
        reponse = self.tour("c'est une longue tâche : un sujet privé",
                            travailleur=mock.Mock())
        self.assertIn("C'est parti", reponse)
        travailleur_prive.signaler.assert_called_once()
        self.assertFalse(self.chemin.exists())
        self.assertEqual(list(self.dossier.glob("taches_longues*")), [])
        self.assertEqual(len(tl.lister(bv.PRIVE.taches)), 1)
        self.assertIn("un sujet privé", self.tour("où en est ma tâche ?"))
        bv.basculer_mode_prive({"action": "sortir", "langue": "fr"}, [], {})
        travailleur_prive.arreter.assert_called_once()
        self.assertIsNone(bv.PRIVE.taches)
        self.assertEqual(bv.chemin_taches(self.config), self.chemin)
        self.assertFalse(self.chemin.exists())
        self.assertEqual(self.tour("où en est ma tâche ?"),
                         "Tu n'as aucune tâche longue, Julien.")

    def test_travailleur_prive_n_ecrit_que_dans_la_memoire(self):
        memoire = tl.Memoire()
        tl.ajouter(memoire, "sujet privé", "fr")
        finale = self.travailleur(FauxCerveau(etapes=2),
                                  chemin=memoire).traiter_une()
        self.assertEqual(finale["etat"], "terminee")
        self.assertEqual(tl.lister(memoire)[0]["etat"], "terminee")
        self.assertEqual(list(self.dossier.rglob("*")), [])
        with self.assertRaises(TypeError):
            Path(memoire)

    def test_travailleur_normal_suspendu_pendant_le_mode(self):
        normal = mock.Mock()
        bv.PRIVE.suspendus = [normal]
        self.entrer()
        normal.suspendre.assert_called_once()
        normal.relancer.assert_not_called()
        bv.basculer_mode_prive({"action": "sortir", "langue": "fr"}, [], {})
        normal.relancer.assert_called_once()

    def test_suspendu_rien_n_est_ecrit_dans_le_fichier(self):
        self.ajouter()
        avant = self.chemin.read_text(encoding="utf-8")
        travailleur = tl.Travailleur(self.chemin, FauxCerveau(etapes=1),
                                     limiteur=tl.LimiteurJetons(0))
        travailleur.suspendre()
        travailleur.demarrer()
        time.sleep(0.3)
        self.assertEqual(self.chemin.read_text(encoding="utf-8"), avant)
        fin = threading.Event()
        travailleur.sur_fin = lambda _t: fin.set()
        travailleur.relancer()
        self.assertTrue(fin.wait(5))
        travailleur.arreter()
        self.assertEqual(self.lire()["taches"][0]["etat"], "terminee")

    def test_sortie_du_mode_arrete_le_travailleur_sans_ecrire(self):
        memoire = tl.Memoire()
        tl.ajouter(memoire, "sujet", "fr")
        cerveau = FauxCerveau(etapes=3)
        travailleur = self.travailleur(cerveau, chemin=memoire)
        cerveau.sur_etape = lambda n: travailleur.arreter()
        self.assertIsNone(travailleur.traiter_une())
        self.assertEqual(tl.lister(memoire)[0]["etapes_faites"], 0)


if __name__ == "__main__":
    unittest.main()
