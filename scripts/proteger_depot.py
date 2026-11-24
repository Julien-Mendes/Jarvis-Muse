#!/usr/bin/env python3
"""proteger_depot.py — Protège le dépôt contre l'envoi de données privées (S5).

    python scripts/proteger_depot.py               # vérifier seulement
    python scripts/proteger_depot.py --appliquer   # corriger

Ce que fait --appliquer (sans danger : on peut le relancer à volonté) :

  1. Complète le .gitignore avec ce qui manque, SANS toucher aux lignes
     existantes : .env, la configuration privée, les jetons, data/, logs/,
     models/, a-dire/ (résumés de Carson) et vers-carson/. Un chemin déjà
     ignoré par une règle existante n'est pas ajouté une seconde fois (on
     interroge Git lui-même : `git check-ignore`).
  2. Active les hooks versionnés de scripts/hooks/ (git config
     core.hooksPath) : avant chaque commit et chaque envoi, Git lance
     scripts/verifier_secrets.py, qui refuse une clé API (gsk_…, sk-ant-…)
     ou un fichier privé.

Sans option, le script vérifie et affiche ce qui manque (code de sortie 1).

Limite à connaître : un .gitignore n'empêche pas qu'un fichier DÉJÀ suivi par
Git, ou déposé directement dans le dépôt distant (par exemple par Carson via
GitHub), soit public si le dépôt est public. Si les résumés de Carson passent
par ce dépôt, il doit être privé.
"""

import argparse
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# (chemin d'essai, ligne à ajouter si ce chemin n'est pas déjà ignoré)
REQUIS = [
    (".env", ".env"),
    ("config/.env", "config/.env"),
    ("config/config.toml", "config/config.toml"),
    ("config/config.local.toml", "config/config.local.toml"),
    ("tokens/exemple.json", "tokens/"),
    ("data/exemple.json", "data/"),
    ("logs/exemple.log", "logs/"),
    ("models/exemple.onnx", "models/"),
    ("a-dire/exemple.txt", "a-dire/"),
    ("vers-carson/exemple.txt", "vers-carson/"),
]
EN_TETE = "# Données privées : jamais versionnées (S5, lot 0.1)"


def _git(*args: str, racine: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=racine, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def est_ignore(chemin: str, racine: Path) -> bool:
    """Vrai si Git ignore ce chemin (toutes les règles prises en compte)."""
    resultat = _git("check-ignore", "-q", "--no-index", chemin, racine=racine)
    return resultat.returncode == 0


def lignes_manquantes(racine: Path) -> list:
    """Lignes à ajouter au .gitignore pour couvrir REQUIS."""
    return [ligne for chemin, ligne in REQUIS
            if not est_ignore(chemin, racine)]


def appliquer_gitignore(racine: Path) -> list:
    """Ajoute à la fin du .gitignore les lignes manquantes ; retourne-les."""
    manquantes = lignes_manquantes(racine)
    if not manquantes:
        return []
    fichier = racine / ".gitignore"
    contenu = fichier.read_text(encoding="utf-8") if fichier.exists() else ""
    if contenu and not contenu.endswith("\n"):
        contenu += "\n"
    if EN_TETE not in contenu:
        contenu += ("\n" if contenu else "") + EN_TETE + "\n"
    contenu += "\n".join(manquantes) + "\n"
    fichier.write_text(contenu, encoding="utf-8")
    return manquantes


def hooks_actifs(racine: Path) -> bool:
    resultat = _git("config", "--get", "core.hooksPath", racine=racine)
    return resultat.stdout.strip().replace("\\", "/").rstrip("/") \
        == "scripts/hooks"


def activer_hooks(racine: Path) -> bool:
    resultat = _git("config", "core.hooksPath", "scripts/hooks", racine=racine)
    return resultat.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Vérifie (ou corrige) la protection du dépôt (.gitignore "
                    "et hooks anti-clés).")
    parser.add_argument("--appliquer", action="store_true",
                        help="Compléter le .gitignore et activer les hooks.")
    args = parser.parse_args()

    if _git("rev-parse", "--git-dir", racine=RACINE).returncode != 0:
        print("Erreur : ce dossier n'est pas un dépôt Git.", file=sys.stderr)
        return 2

    manquantes = lignes_manquantes(RACINE)
    hooks_ok = hooks_actifs(RACINE)

    if args.appliquer:
        ajoutees = appliquer_gitignore(RACINE)
        if ajoutees:
            print(".gitignore complété : " + ", ".join(ajoutees))
            print("→ pensez à le valider : git add .gitignore && "
                  "git commit -m \"Protéger les données privées\"")
        else:
            print(".gitignore : déjà complet.")
        if not hooks_ok:
            if activer_hooks(RACINE):
                print("Hooks activés (scripts/hooks/) : clés et fichiers "
                      "privés refusés avant commit et avant envoi.")
            else:
                print("Erreur : impossible d'activer les hooks.",
                      file=sys.stderr)
                return 1
        else:
            print("Hooks : déjà actifs.")
        # Fichiers privés déjà suivis par Git (le .gitignore ne les retire pas).
        suivis = _git("ls-files", "--", ".env", "config/config.toml",
                      "config/config.local.toml", "tokens", "data", "logs",
                      "models", "a-dire", "vers-carson", racine=RACINE)
        interdits = [f for f in suivis.stdout.splitlines()
                     if f not in ("a-dire/.gitkeep", "vers-carson/.gitkeep")
                     and not f.endswith((".gitkeep", ".example"))]
        if interdits:
            print("ATTENTION — fichiers privés déjà suivis par Git (à retirer "
                  "avec git rm --cached) :", file=sys.stderr)
            for f in interdits:
                print(f"  - {f}", file=sys.stderr)
            return 1
        return 0

    problemes = False
    if manquantes:
        problemes = True
        print("Le .gitignore ne couvre pas : " + ", ".join(manquantes))
    else:
        print(".gitignore : complet.")
    if not hooks_ok:
        problemes = True
        print("Les hooks anti-clés ne sont pas actifs.")
    else:
        print("Hooks anti-clés : actifs.")
    if problemes:
        print("Corriger : python scripts/proteger_depot.py --appliquer")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
