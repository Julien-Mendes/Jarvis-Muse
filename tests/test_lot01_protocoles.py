"""Lot 0.1 — tests de contrat entre scripts et non-régression des bugs vérifiés.

Chaque test cite le constat du plan (§3) qu'il verrouille : F1 (champ du
protocole navigateur), F2 (langue de la vision), F3 (annonces et outils),
F4 (fenêtre Jarvis, DPI), F5 (surveillant, verrou, 5 s), F14 (instance
unique), F15 (hold_writes). Aucun accès réseau, aucune capture, aucun son.
"""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

import _chemins_lot01 as chemins

import boucle_voix
import lancer_app
import minuteur
import navigateur
import verrou
import yeux

# Les tests lancent des sous-processus et des verrous : les avertissements de
# fichiers laissés ouverts jusqu'à la fin du processus sont du bruit ici.
warnings.simplefilter("ignore", ResourceWarning)

CONFIG_EN = {"langue": "en", "navigateur_defaut": "systeme"}


class FausseSession:
    """Remplace SessionNavigateur : enregistre les commandes envoyées."""

    def __init__(self):
        self.commandes = []

    def envoyer(self, commande):
        self.commandes.append(commande)
        return {"ok": True}


class FausseNavigateur:
    """Remplace navigateur.Navigateur dans boucle_interactive."""

    appels = []

    def __init__(self):
        FausseNavigateur.appels = []

    def rechercher(self, requete):
        FausseNavigateur.appels.append(("rechercher", requete))
        return {"url": "https://exemple.test"}

    def naviguer(self, url):
        FausseNavigateur.appels.append(("naviguer", url))
        return {"url": url}

    def fermer(self):
        pass


def jouer_commande_sur_navigateur(commande: dict) -> tuple:
    """Envoie une commande JSON à navigateur.boucle_interactive (faux
    navigateur) et retourne (réponse JSON, appels reçus)."""
    sortie = io.StringIO()
    with mock.patch.object(navigateur, "Navigateur", FausseNavigateur), \
            mock.patch.object(sys, "stdin",
                              io.StringIO(json.dumps(commande) + "\n")), \
            contextlib.redirect_stdout(sortie), \
            contextlib.redirect_stderr(io.StringIO()):
        navigateur.boucle_interactive()
    ligne = sortie.getvalue().strip().splitlines()[0]
    return json.loads(ligne), list(FausseNavigateur.appels)


class F1ProtocoleNavigateur(unittest.TestCase):
    def test_la_recherche_de_la_boucle_est_comprise_par_navigateur_py(self):
        """F1 : le champ envoyé par boucle_voix est celui que lit navigateur."""
        session = FausseSession()
        boucle_voix.executer_navigateur({"recherche": "cats"}, session,
                                        CONFIG_EN)
        self.assertEqual(len(session.commandes), 1)
        commande = session.commandes[0]
        self.assertEqual(commande["commande"], "rechercher")
        reponse, appels = jouer_commande_sur_navigateur(commande)
        self.assertTrue(reponse["ok"], reponse)
        self.assertEqual(appels, [("rechercher", "cats")])

    def test_la_navigation_de_la_boucle_est_comprise_par_navigateur_py(self):
        session = FausseSession()
        config = dict(CONFIG_EN, navigateur_defaut="playwright")
        boucle_voix.executer_navigateur({"url": "example.com"}, session, config)
        reponse, appels = jouer_commande_sur_navigateur(session.commandes[0])
        self.assertTrue(reponse["ok"], reponse)
        self.assertEqual(appels, [("naviguer", "example.com")])

    def test_sites_dans_le_navigateur_par_defaut_sans_playwright(self):
        """Y4 : navigateur_defaut = systeme -> un site s'ouvre dans le vrai
        navigateur ; Playwright n'est pas sollicité."""
        session = FausseSession()
        with mock.patch("webbrowser.open", return_value=True) as ouvrir:
            boucle_voix.executer_navigateur({"url": "example.com"}, session,
                                            CONFIG_EN)
        self.assertEqual(session.commandes, [])
        ouvrir.assert_called_once_with("https://example.com")

    def test_playwright_reserve_aux_recherches_en_mode_systeme(self):
        session = FausseSession()
        boucle_voix.executer_navigateur({"recherche": "météo"}, session,
                                        CONFIG_EN)
        self.assertEqual(session.commandes[0]["commande"], "rechercher")

    def test_mode_playwright_envoie_aussi_les_sites_a_playwright(self):
        session = FausseSession()
        boucle_voix.executer_navigateur(
            {"url": "example.com"}, session,
            dict(CONFIG_EN, navigateur_defaut="playwright"))
        self.assertEqual(session.commandes[0]["commande"], "naviguer")

    def test_repli_sur_le_navigateur_par_defaut_sans_session(self):
        with mock.patch("webbrowser.open", return_value=True) as ouvrir:
            boucle_voix.executer_navigateur({"recherche": "a b"}, None,
                                            CONFIG_EN)
        self.assertIn("duckduckgo.com/?q=a+b", ouvrir.call_args[0][0])

    def test_requete_vide_ou_url_refusee_ne_lance_pas_chromium(self):
        """F1 : avant, Chromium s'ouvrait puis la requête vide échouait."""
        nav = navigateur.Navigateur()
        with mock.patch.object(nav, "_assurer_demarre") as demarrer:
            with self.assertRaises(ValueError):
                nav.rechercher("   ")
            with self.assertRaises(ValueError):
                nav.naviguer("ftp://exemple.test")
            demarrer.assert_not_called()


class F2LangueDeLaVision(unittest.TestCase):
    def test_invite_dans_la_langue_active(self):
        en = yeux.construire_prompt("en", "what is the error?")
        fr = yeux.construire_prompt("fr", "c'est quoi l'erreur ?")
        self.assertIn("English", en)
        self.assertNotIn("français", en)
        self.assertIn("Julien's question: what is the error?", en)
        self.assertIn("français", fr)
        self.assertIn("Question de Julien : c'est quoi l'erreur ?", fr)
        self.assertEqual(yeux.construire_prompt("de"), yeux.PROMPTS["en"])

    def test_la_boucle_transmet_la_langue_a_yeux_py(self):
        for langue in ("en", "fr"):
            with mock.patch.object(
                    boucle_voix.subprocess, "run",
                    return_value=subprocess.CompletedProcess(
                        [], 0, stdout="description", stderr="")) as lancer:
                boucle_voix.executer_ecran({"question": ""}, {"langue": langue})
            commande = lancer.call_args[0][0]
            i = commande.index("--langue")
            self.assertEqual(commande[i + 1], langue)

    def test_yeux_py_accepte_l_option_langue(self):
        sortie = subprocess.run(
            [sys.executable, str(chemins.SCRIPTS / "yeux.py"), "decrire",
             "--help"], capture_output=True, text=True)
        self.assertIn("--langue", sortie.stdout)


class F3AnnoncesEtOutils(unittest.TestCase):
    @staticmethod
    def _fonction(outil):
        return outil.get("function", outil)

    def test_outils_en_anglais_meme_contrat_que_le_francais(self):
        for fournisseur in ("groq", "anthropic"):
            fr = boucle_voix.outils_pour(fournisseur, "fr")
            en = boucle_voix.outils_pour(fournisseur, "en")
            self.assertEqual(
                [self._fonction(o)["name"] for o in fr],
                [self._fonction(o)["name"] for o in en])
            for f, e in zip(fr, en):
                cle = "parameters" if fournisseur == "groq" else "input_schema"
                self.assertEqual(
                    set(self._fonction(f)[cle]["properties"]),
                    set(self._fonction(e)[cle]["properties"]))
                self.assertNotEqual(self._fonction(f)["description"],
                                    self._fonction(e)["description"])
            for outil in en:
                description = self._fonction(outil)["description"]
                self.assertFalse(any(c in description for c in "éèêàç"),
                                 description)

    def test_outils_francais_inchanges(self):
        self.assertIs(boucle_voix.outils_pour("groq", "fr")[0],
                      boucle_voix.OUTIL_MINUTEUR_GROQ)

    def test_phrase_de_demarrage_suit_la_langue(self):
        self.assertEqual(lancer_app.phrase_pret("en"), "Jarvis ready.")
        self.assertEqual(lancer_app.phrase_pret("fr"), "Jarvis prêt.")
        with mock.patch.object(lancer_app.config_jarvis, "langue",
                               return_value="fr"):
            self.assertEqual(lancer_app.langue_active(), "fr")

    def test_aucune_langue_francaise_codee_en_dur_dans_les_lanceurs(self):
        app = (chemins.SCRIPTS / "lancer_app.py").read_text(encoding="utf-8")
        ps1 = (chemins.SCRIPTS / "lancer_session.ps1").read_text(encoding="utf-8")
        self.assertNotIn('"--langue", "fr"', app)
        self.assertNotIn("--langue fr", ps1)
        self.assertIn("$script:Langue", ps1)


class F4FenetreJarvisEtDpi(unittest.TestCase):
    @staticmethod
    def fenetre(titre, classe="Chrome_WidgetWin_1", **autres):
        base = {"titre": titre, "classe": classe, "visible": True,
                "reduite": False, "masquee": False}
        base.update(autres)
        return base

    def test_reconnait_les_fenetres_de_jarvis(self):
        self.assertTrue(yeux.est_fenetre_jarvis("Jarvis", "TkTopLevel"))
        self.assertTrue(yeux.est_fenetre_jarvis("Historique — Jarvis", "TkTopLevel"))
        # Un onglet de navigateur ou un autre titre n'est pas Jarvis.
        self.assertFalse(yeux.est_fenetre_jarvis("Jarvis", "Chrome_WidgetWin_1"))
        self.assertFalse(yeux.est_fenetre_jarvis("Jarvis-Muse - GitHub", "TkTopLevel"))

    def test_jarvis_au_premier_plan_on_prend_la_fenetre_d_apres(self):
        pile = [self.fenetre("Jarvis", "TkTopLevel"),
                self.fenetre("", hwnd=2),
                self.fenetre("réduite", reduite=True),
                self.fenetre("fantôme", masquee=True),
                self.fenetre("Program Manager", "Progman"),
                self.fenetre("Excel — budget.xlsx")]
        self.assertEqual(yeux.choisir_fenetre(pile)["titre"],
                         "Excel — budget.xlsx")

    def test_fenetre_normale_au_premier_plan_inchangee(self):
        pile = [self.fenetre("Notepad"), self.fenetre("Autre")]
        self.assertEqual(yeux.choisir_fenetre(pile)["titre"], "Notepad")

    def test_rien_a_capturer_si_seule_jarvis_est_ouverte(self):
        self.assertIsNone(yeux.choisir_fenetre(
            [self.fenetre("Jarvis", "TkTopLevel"),
             self.fenetre("Historique — Jarvis", "TkTopLevel")]))
        self.assertIsNone(yeux.choisir_fenetre([]))

    @unittest.skipIf(sys.platform == "win32", "sans effet hors Windows")
    def test_activer_dpi_sans_effet_hors_windows(self):
        self.assertFalse(yeux.activer_dpi())


class S1InstanceUnique(unittest.TestCase):
    def test_second_verrou_refuse_puis_liberation(self):
        with tempfile.TemporaryDirectory() as tmp:
            premier = verrou.VerrouInstance("essai", Path(tmp))
            self.assertTrue(premier.acquerir())
            self.assertFalse(verrou.VerrouInstance("essai", Path(tmp)).acquerir())
            premier.liberer()
            second = verrou.VerrouInstance("essai", Path(tmp))
            self.assertTrue(second.acquerir())
            second.liberer()

    def test_verrou_refuse_aussi_entre_deux_processus(self):
        with tempfile.TemporaryDirectory() as tmp:
            premier = verrou.VerrouInstance("essai", Path(tmp))
            self.assertTrue(premier.acquerir())
            code = ("import sys; sys.path.insert(0, r'%s');"
                    "from verrou import VerrouInstance;"
                    "print(VerrouInstance('essai', r'%s').acquerir())"
                    % (chemins.SCRIPTS, tmp))
            sortie = subprocess.run([sys.executable, "-c", code],
                                    capture_output=True, text=True)
            self.assertEqual(sortie.stdout.strip(), "False")
            premier.liberer()

    def test_verrou_impossible_a_creer_ne_bloque_pas_jarvis(self):
        with tempfile.NamedTemporaryFile() as fichier:
            # Un « dossier » qui est en fait un fichier : mkdir échoue.
            self.assertTrue(verrou.VerrouInstance(
                "essai", Path(fichier.name) / "sous").acquerir())

    def test_les_trois_points_d_entree_utilisent_le_verrou(self):
        for nom in ("boucle_voix.py", "minuteur.py", "lancer_app.py"):
            texte = (chemins.SCRIPTS / nom).read_text(encoding="utf-8")
            self.assertIn("VerrouInstance(", texte, nom)

    def test_second_surveillant_refuse_de_demarrer(self):
        with tempfile.TemporaryDirectory() as tmp:
            donnees = Path(tmp) / "timers.json"
            premier = verrou.VerrouInstance("surveillant", Path(tmp))
            self.assertTrue(premier.acquerir())
            args = mock.Mock(donnees=donnees, langue=None)
            with contextlib.redirect_stdout(io.StringIO()) as sortie:
                code = minuteur.cmd_surveiller(args)  # ne doit pas boucler
            self.assertEqual(code, 0)
            self.assertIn("tourne déjà", sortie.getvalue())
            premier.liberer()


class M3MinuteursSousVerrou(unittest.TestCase):
    def test_creations_en_parallele_ne_perdent_aucun_minuteur(self):
        with tempfile.TemporaryDirectory() as tmp:
            donnees = Path(tmp) / "timers.json"
            processus = [subprocess.Popen(
                [sys.executable, str(chemins.SCRIPTS / "minuteur.py"),
                 "--donnees", str(donnees), "demarrer", "--minutes", "5",
                 "--etiquette", f"t{i}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                for i in range(12)]
            codes = [p.wait() for p in processus]
            self.assertEqual(codes, [0] * 12)
            etat = json.loads(donnees.read_text(encoding="utf-8"))
            identifiants = [m["id"] for m in etat["timers"]]
            self.assertEqual(len(identifiants), 12)
            self.assertEqual(len(set(identifiants)), 12)

    def test_verrou_fichier_exclusion_mutuelle(self):
        with tempfile.TemporaryDirectory() as tmp:
            compteur = Path(tmp) / "compteur.txt"
            compteur.write_text("0")
            code = (
                "import sys; sys.path.insert(0, r'%s')\n"
                "from pathlib import Path\n"
                "from verrou import verrou_fichier\n"
                "p = Path(r'%s')\n"
                "for _ in range(40):\n"
                "    with verrou_fichier(p):\n"
                "        n = int(p.read_text()); p.write_text(str(n + 1))\n"
                % (chemins.SCRIPTS, compteur))
            processus = [subprocess.Popen([sys.executable, "-c", code])
                         for _ in range(4)]
            for p in processus:
                self.assertEqual(p.wait(), 0)
            self.assertEqual(int(compteur.read_text()), 160)

    def test_surveillant_verifie_toutes_les_5_secondes_au_plus(self):
        self.assertLessEqual(minuteur.INTERVALLE_VERIFICATION_S, 5.0)
        with tempfile.TemporaryDirectory() as tmp:
            donnees = Path(tmp) / "timers.json"
            attentes = []

            def dormir(secondes):
                attentes.append(secondes)
                raise KeyboardInterrupt

            args = mock.Mock(donnees=donnees, langue="en")
            with mock.patch.object(minuteur.time, "sleep", dormir), \
                    mock.patch.object(minuteur, "declencher_dus", return_value=[]), \
                    contextlib.redirect_stdout(io.StringIO()):
                minuteur.cmd_surveiller(args)
                self.assertEqual(attentes, [5.0])  # aucun minuteur : 5 s.
            # Un minuteur dans 2 s : on se réveille à temps.
            ref = minuteur.maintenant()
            etat = {"timers": [{"id": 1, "kind": "timer", "label": "",
                                "due": (ref + minuteur.timedelta(seconds=2)).isoformat(),
                                "minutes": 1, "created": ref.isoformat()}],
                    "next_id": 2}
            donnees.write_text(json.dumps(etat), encoding="utf-8")
            attentes.clear()
            args2 = mock.Mock(donnees=donnees, langue="en")
            # Libère le verrou « surveillant » du premier appel (même processus).
            with mock.patch.object(minuteur, "VerrouInstance") as faux_verrou, \
                    mock.patch.object(minuteur.time, "sleep", dormir), \
                    mock.patch.object(minuteur, "declencher_dus", return_value=[]), \
                    contextlib.redirect_stdout(io.StringIO()):
                faux_verrou.return_value.acquerir.return_value = True
                minuteur.cmd_surveiller(args2)
            self.assertEqual(len(attentes), 1)
            self.assertLessEqual(attentes[0], 2.0)


class FormatDeTimersJson(unittest.TestCase):
    """Contrat de data/timers.json entre minuteur.py, app.py, le lanceur
    PowerShell et le HUD : mêmes champs, mêmes valeurs."""

    def test_format_ecrit_par_minuteur_lu_par_l_application(self):
        import app
        with tempfile.TemporaryDirectory() as tmp:
            donnees = Path(tmp) / "timers.json"
            subprocess.run(
                [sys.executable, str(chemins.SCRIPTS / "minuteur.py"),
                 "--donnees", str(donnees), "demarrer", "--minutes", "10",
                 "--etiquette", "pâtes"], check=True, capture_output=True)
            etat = json.loads(donnees.read_text(encoding="utf-8"))
            self.assertEqual(set(etat), {"timers", "next_id"})
            minuteur_json = etat["timers"][0]
            self.assertTrue({"id", "kind", "label", "due", "minutes",
                             "created"} <= set(minuteur_json))
            self.assertIn(minuteur_json["kind"], ("timer", "reminder"))
            lus = app.charger_minuteurs(donnees)
            self.assertEqual(len(lus), 1)
            self.assertEqual(lus[0]["label"], "pâtes")
            self.assertEqual(lus[0]["kind"], "timer")

    def test_le_lanceur_powershell_lit_les_memes_champs(self):
        ps1 = (chemins.SCRIPTS / "lancer_session.ps1").read_text(encoding="utf-8")
        for champ in ("$etat.timers", ".due", ".kind", ".label"):
            self.assertIn(champ, ps1)


class F15HoldWrites(unittest.TestCase):
    def test_tripwire_aucun_outil_ne_lit_de_texte_externe_pour_le_modele(self):
        """F15 : OUTILS_LECTURE_EXTERNE est vide car aucun outil ne renvoie de
        texte externe au modèle. Le jour où ce test échoue (lecture de page,
        suivi de question sur l'écran…), il faut AUSSI revoir OUTILS_SANS_ECRITURE
        (ouvrir_navigateur ne doit plus y figurer) et ajouter un test
        d'injection : voir docs/regles-securite.md §1-§2."""
        self.assertEqual(boucle_voix.OUTILS_LECTURE_EXTERNE, set())
        self.assertEqual(boucle_voix.OUTILS_SANS_ECRITURE,
                         {"decrire_ecran", "ouvrir_navigateur"})

    def test_confirmation_orale_regles_inchangees(self):
        f = boucle_voix.est_confirmation_courte
        self.assertTrue(f("Oui."))
        self.assertTrue(f("yes"))
        self.assertFalse(f("oui, mais en 4"))
        self.assertFalse(f("non"))
        self.assertFalse(f("oui " * 9))  # plus de 8 mots.
        self.assertEqual(boucle_voix.DELAI_CONFIRMATION_S, 30.0)


if __name__ == "__main__":
    unittest.main()
