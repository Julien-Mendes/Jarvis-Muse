"""Lot 0.1 — S5 : contrôle anti-clés, .gitignore et hooks.

Tout se passe dans des dépôts Git temporaires : aucun accès réseau.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

import _chemins_lot01 as chemins

import proteger_depot
import verifier_secrets

CLE_GROQ = "gsk_" + "Ab3dE5gH7jK9mN1pQ3sT5v"
CLE_ANTHROPIC = "sk-ant-api03-" + "Zq8Lm2Vx4Rt6Yp0Wn3Bc5Dh"
ZEROS = "0" * 40


def git(dossier: Path, *args: str) -> str:
    resultat = subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=t@t", *args],
        cwd=dossier, capture_output=True, text=True, check=True)
    return resultat.stdout.strip()


def depot_temporaire(tmp: str) -> Path:
    dossier = Path(tmp)
    git(dossier, "init", "-q", "-b", "main")
    return dossier


class DetectionDeCles(unittest.TestCase):
    def test_detecte_les_cles_groq_et_anthropic(self):
        trouvees = verifier_secrets.chercher_cles(
            f"GROQ_API_KEY={CLE_GROQ}\nautre ligne\nk = {CLE_ANTHROPIC}\n")
        self.assertEqual([(n[:8], ligne) for n, ligne, _ in trouvees],
                         [("clé Groq", 1), ("clé Anth", 3)])

    def test_la_cle_n_est_jamais_affichee_en_entier(self):
        for _, _, apercu in verifier_secrets.chercher_cles(
                f"{CLE_GROQ} {CLE_ANTHROPIC}"):
            self.assertLessEqual(len(apercu), 7)
            self.assertNotIn(CLE_GROQ, apercu)

    def test_valeurs_d_exemple_ignorees(self):
        self.assertEqual(verifier_secrets.chercher_cles(
            "GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxx\n"
            "ANTHROPIC_API_KEY=sk-ant-................\n"
            "GROQ_API_KEY=gsk_votre_cle_ici\n"), [])

    def test_chemins_interdits(self):
        interdits = [".env", "config/.env", "config/config.toml",
                     "config/config.local.toml", "tokens/google.json",
                     "data/timers.json", "logs/boucle.log",
                     "models/upmc.onnx", "a-dire/resume.txt",
                     "vers-carson/note.txt", "./a-dire/x.txt",
                     "a-dire\\resume.txt"]
        for chemin in interdits:
            self.assertIsNotNone(verifier_secrets.chemin_interdit(chemin), chemin)

    def test_chemins_permis(self):
        permis = [".env.example", "config/.env.example",
                  "config/config.example.toml",
                  "config/config.local.example.toml", "a-dire/.gitkeep",
                  "scripts/boucle_voix.py", "docs/regles-securite.md",
                  "tests/test_lot01_securite.py", "README.md"]
        for chemin in permis:
            self.assertIsNone(verifier_secrets.chemin_interdit(chemin), chemin)


class ControlesAvantEnvoi(unittest.TestCase):
    def test_index_refuse_une_cle_et_un_fichier_prive(self):
        with tempfile.TemporaryDirectory() as tmp:
            depot = depot_temporaire(tmp)
            (depot / "notes.txt").write_text(f"k={CLE_GROQ}\n", encoding="utf-8")
            (depot / "a-dire").mkdir()
            (depot / "a-dire" / "r.txt").write_text("bonjour", encoding="utf-8")
            (depot / "ok.txt").write_text("rien", encoding="utf-8")
            git(depot, "add", "-f", "notes.txt", "a-dire/r.txt", "ok.txt")
            problemes = verifier_secrets.verifier_index(depot)
            fichiers = {p[0] for p in problemes}
            self.assertEqual(fichiers, {"notes.txt", "a-dire/r.txt"})

    def test_envoi_refuse_un_commit_avec_cle_meme_sans_hook_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            depot = depot_temporaire(tmp)
            (depot / "a.txt").write_text("a", encoding="utf-8")
            git(depot, "add", "a.txt")
            git(depot, "commit", "-q", "-m", "ok")
            propre = git(depot, "rev-parse", "HEAD")
            (depot / "conf.txt").write_text(f"k={CLE_ANTHROPIC}\n", encoding="utf-8")
            git(depot, "add", "conf.txt")
            git(depot, "commit", "-q", "-m", "oups", "--no-verify")
            sale = git(depot, "rev-parse", "HEAD")
            ligne_ok = f"refs/heads/main {propre} refs/heads/main {ZEROS}"
            ligne_sale = f"refs/heads/main {sale} refs/heads/main {propre}"
            self.assertEqual(verifier_secrets.verifier_envoi([ligne_ok], depot), [])
            problemes = verifier_secrets.verifier_envoi([ligne_sale], depot)
            self.assertEqual([p[0] for p in problemes], ["conf.txt"])
            self.assertIn("clé Anthropic", problemes[0][2])

    def test_suppression_de_branche_n_est_pas_controlee(self):
        with tempfile.TemporaryDirectory() as tmp:
            depot = depot_temporaire(tmp)
            self.assertEqual(verifier_secrets.verifier_envoi(
                [f"(delete) {ZEROS} refs/heads/x {ZEROS}"], depot), [])

    def test_hooks_versionnes_appellent_le_controle(self):
        for nom, option in (("pre-commit", "--index"), ("pre-push", "--pousse")):
            hook = chemins.SCRIPTS / "hooks" / nom
            texte = hook.read_text(encoding="utf-8")
            self.assertTrue(texte.startswith("#!/bin/sh"), nom)
            self.assertIn("verifier_secrets.py", texte)
            self.assertIn(option, texte)


class GitignoreEtHooks(unittest.TestCase):
    def test_complete_le_gitignore_sans_toucher_aux_lignes_existantes(self):
        with tempfile.TemporaryDirectory() as tmp:
            depot = depot_temporaire(tmp)
            (depot / ".gitignore").write_text("__pycache__/\n.env\ndata/\n",
                                              encoding="utf-8")
            avant = proteger_depot.lignes_manquantes(depot)
            self.assertIn("a-dire/", avant)
            self.assertIn("vers-carson/", avant)
            self.assertNotIn(".env", avant)  # déjà couvert par une règle.
            self.assertNotIn("data/", avant)
            ajoutees = proteger_depot.appliquer_gitignore(depot)
            self.assertEqual(ajoutees, avant)
            contenu = (depot / ".gitignore").read_text(encoding="utf-8")
            self.assertTrue(contenu.startswith("__pycache__/\n.env\ndata/\n"))
            self.assertEqual(proteger_depot.lignes_manquantes(depot), [])
            # Idempotent : un second passage n'ajoute rien.
            self.assertEqual(proteger_depot.appliquer_gitignore(depot), [])
            self.assertEqual(
                (depot / ".gitignore").read_text(encoding="utf-8"), contenu)

    def test_cree_le_gitignore_s_il_est_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            depot = depot_temporaire(tmp)
            proteger_depot.appliquer_gitignore(depot)
            self.assertEqual(proteger_depot.lignes_manquantes(depot), [])

    def test_activation_des_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            depot = depot_temporaire(tmp)
            self.assertFalse(proteger_depot.hooks_actifs(depot))
            self.assertTrue(proteger_depot.activer_hooks(depot))
            self.assertTrue(proteger_depot.hooks_actifs(depot))

    def test_le_gitignore_du_depot_couvre_les_donnees_privees(self):
        """S5 : a-dire/ et vers-carson/ (entre autres) ne doivent pas pouvoir
        être ajoutés par erreur. Si ce test échoue : lancez
        `python scripts/proteger_depot.py --appliquer`, puis validez le
        .gitignore (git add .gitignore && git commit)."""
        racine = chemins.RACINE
        if subprocess.run(["git", "rev-parse", "--git-dir"], cwd=racine,
                          capture_output=True).returncode != 0:
            self.skipTest("pas un dépôt Git")
        self.assertEqual(
            proteger_depot.lignes_manquantes(racine), [],
            "le .gitignore ne couvre pas tout : "
            "python scripts/proteger_depot.py --appliquer")


if __name__ == "__main__":
    unittest.main()
