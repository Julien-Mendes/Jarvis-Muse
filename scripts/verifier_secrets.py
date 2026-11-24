#!/usr/bin/env python3
"""verifier_secrets.py — Refuse d'envoyer une clé ou un fichier privé (S5).

Appelé automatiquement par les hooks Git (scripts/hooks/pre-commit et
pre-push, activés par `python scripts/proteger_depot.py --appliquer`) ; peut
aussi se lancer à la main :

    python scripts/verifier_secrets.py --index             # fichiers indexés
    python scripts/verifier_secrets.py --fichiers a b      # fichiers sur disque
    python scripts/verifier_secrets.py --pousse < lignes   # entrée d'un pre-push

Deux contrôles, qui font échouer l'envoi (code 1) :

  1. Contenu : une chaîne qui ressemble à une clé API — Groq (gsk_…) ou
     Anthropic (sk-ant-…). Les valeurs d'exemple faites de répétitions
     (gsk_xxxxxxxx…) sont ignorées. La clé elle-même n'est JAMAIS imprimée
     en entier (6 premiers caractères seulement).
  2. Chemins : un fichier qui ne doit jamais être versionné — .env, la
     configuration privée, les jetons, les données, les journaux, les voix,
     et les dossiers a-dire/ et vers-carson/ (résumés de Carson, notes :
     contenu personnel). Les fichiers d'exemple restent permis.

Le dépôt GitHub peut être public : ce contrôle est le dernier filet de
sécurité, il ne remplace pas le .gitignore (voir proteger_depot.py).

Sortie : 0 = rien à signaler ; 1 = envoi refusé ; 2 = erreur d'utilisation.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# Clés : préfixe reconnaissable + corps d'au moins 20 caractères.
MOTIFS_CLES = {
    "clé Groq (gsk_…)": re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    "clé Anthropic (sk-ant-…)": re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
}

# Chemins interdits (motifs sur le chemin relatif, séparateur « / »).
# Chaque entrée : (motif, explication). Les exceptions sont dans EXCEPTIONS.
CHEMINS_INTERDITS = [
    (re.compile(r"(^|/)\.env$"), "fichier de secrets (.env)"),
    (re.compile(r"(^|/)\.env\.(?!example$)[^/]+$"), "fichier de secrets (.env.*)"),
    (re.compile(r"^config/config\.toml$"), "configuration personnelle"),
    (re.compile(r"^config/config\.local\.toml$"), "configuration privée"),
    (re.compile(r"^tokens/"), "jetons OAuth"),
    (re.compile(r"^data/"), "données locales (minuteurs, conversations)"),
    (re.compile(r"^logs/"), "journaux locaux"),
    (re.compile(r"^models/"), "voix téléchargées"),
    (re.compile(r"^a-dire/"), "résumés de Carson (contenu personnel)"),
    (re.compile(r"^vers-carson/"), "notes pour Carson (contenu personnel)"),
]
EXCEPTIONS = {"a-dire/.gitkeep", "vers-carson/.gitkeep",
              "data/.gitkeep", "logs/.gitkeep", "models/.gitkeep"}

ZEROS = "0" * 40


def est_valeur_exemple(corps: str) -> bool:
    """Vrai pour un corps de clé factice (xxxxxxxx, 00000000, ********)."""
    return len(set(corps.lower())) <= 3


def chercher_cles(texte: str) -> list:
    """Trouve les clés dans un texte : [(nom, numero_de_ligne, apercu)]."""
    trouvees = []
    for numero, ligne in enumerate(texte.splitlines(), start=1):
        for nom, motif in MOTIFS_CLES.items():
            for m in motif.finditer(ligne):
                valeur = m.group(0)
                corps = valeur.split("_", 1)[-1] if valeur.startswith("gsk_") \
                    else valeur[len("sk-ant-"):]
                if est_valeur_exemple(corps):
                    continue
                trouvees.append((nom, numero, valeur[:6] + "…"))
    return trouvees


def chemin_interdit(chemin: str) -> str | None:
    """Raison pour laquelle ce chemin ne doit pas être versionné, sinon None."""
    propre = chemin.replace("\\", "/")
    while propre.startswith("./"):
        propre = propre[2:]
    if propre in EXCEPTIONS or propre.endswith(".example"):
        return None
    for motif, raison in CHEMINS_INTERDITS:
        if motif.search(propre):
            return raison
    return None


def _git(*args: str, racine: Path = RACINE) -> str:
    resultat = subprocess.run(["git", *args], cwd=racine, capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
    if resultat.returncode != 0:
        raise RuntimeError(resultat.stderr.strip() or "erreur git")
    return resultat.stdout


def controler_contenu(chemin: str, texte: str) -> list:
    """Problèmes d'un fichier : [(chemin, ligne, description)]."""
    problemes = []
    raison = chemin_interdit(chemin)
    if raison:
        problemes.append((chemin, 0, f"ne doit pas être versionné : {raison}"))
    for nom, ligne, apercu in chercher_cles(texte):
        problemes.append((chemin, ligne, f"{nom} détectée ({apercu})"))
    return problemes


def verifier_index(racine: Path = RACINE) -> list:
    """Contrôle les fichiers ajoutés ou modifiés dans l'index (pre-commit)."""
    noms = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR",
                "-z", racine=racine).split("\0")
    problemes = []
    for nom in filter(None, noms):
        raison = chemin_interdit(nom)
        if raison:
            problemes.append((nom, 0, f"ne doit pas être versionné : {raison}"))
            continue
        try:
            texte = _git("show", f":{nom}", racine=racine)
        except RuntimeError:
            continue
        problemes += [p for p in controler_contenu(nom, texte) if p[1] > 0]
    return problemes


def verifier_fichiers(fichiers: list, racine: Path = RACINE) -> list:
    """Contrôle des fichiers sur disque (chemins relatifs à la racine)."""
    problemes = []
    for fichier in fichiers:
        chemin = Path(fichier)
        absolu = chemin if chemin.is_absolute() else racine / chemin
        try:
            relatif = absolu.resolve().relative_to(racine.resolve()).as_posix()
        except ValueError:
            relatif = chemin.as_posix()
        try:
            texte = absolu.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        problemes += controler_contenu(relatif, texte)
    return problemes


def verifier_envoi(lignes_stdin: list, racine: Path = RACINE) -> list:
    """Contrôle les commits qui vont partir (entrée standard d'un pre-push :
    « <réf locale> <sha local> <réf distante> <sha distant> » par ligne)."""
    problemes = []
    vus = set()
    for ligne in lignes_stdin:
        morceaux = ligne.split()
        if len(morceaux) < 4:
            continue
        _, sha_local, _, sha_distant = morceaux[:4]
        if sha_local == ZEROS:  # suppression de branche : rien à envoyer.
            continue
        plage = ([sha_local, "--not", "--remotes"] if sha_distant == ZEROS
                 else [f"{sha_distant}..{sha_local}"])
        try:
            commits = _git("rev-list", *plage, racine=racine).split()
        except RuntimeError:
            # Plage introuvable (historique réécrit) : tout l'historique local.
            commits = _git("rev-list", sha_local, racine=racine).split()
        for commit in commits:
            if commit in vus:
                continue
            vus.add(commit)
            noms = _git("diff-tree", "--no-commit-id", "--name-only", "-r",
                        "--root", "-m", "--diff-filter=ACMR", "-z", commit,
                        racine=racine).split("\0")
            for nom in filter(None, noms):
                raison = chemin_interdit(nom)
                if raison:
                    problemes.append(
                        (nom, 0, f"ne doit pas être versionné : {raison} "
                                 f"(commit {commit[:8]})"))
                    continue
                try:
                    texte = _git("show", f"{commit}:{nom}", racine=racine)
                except RuntimeError:
                    continue
                problemes += [
                    (c, n, f"{d} (commit {commit[:8]})")
                    for c, n, d in controler_contenu(nom, texte) if n > 0]
    return problemes


def afficher(problemes: list) -> None:
    print("ENVOI REFUSÉ — des éléments privés ou des clés ont été détectés :",
          file=sys.stderr)
    for chemin, ligne, description in problemes:
        endroit = f"{chemin}:{ligne}" if ligne else chemin
        print(f"  - {endroit} — {description}", file=sys.stderr)
    print("Retirez-les (git rm --cached <fichier>, ajoutez-les au .gitignore, "
          "et faites pivoter toute clé exposée) puis recommencez.",
          file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refuse l'envoi de clés API ou de fichiers privés.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--index", action="store_true",
                      help="Contrôler les fichiers indexés (pre-commit).")
    mode.add_argument("--pousse", action="store_true",
                      help="Contrôler les commits à envoyer (entrée d'un "
                           "pre-push, sur l'entrée standard).")
    mode.add_argument("--fichiers", nargs="+", metavar="FICHIER",
                      help="Contrôler ces fichiers sur disque.")
    args = parser.parse_args()
    try:
        if args.index:
            problemes = verifier_index()
        elif args.pousse:
            problemes = verifier_envoi(sys.stdin.read().splitlines())
        else:
            problemes = verifier_fichiers(args.fichiers)
    except (RuntimeError, OSError) as erreur:
        # Échec du contrôle lui-même : on ne bloque pas silencieusement un
        # envoi légitime, mais on le dit clairement.
        print(f"Avertissement : contrôle des secrets impossible ({erreur}).",
              file=sys.stderr)
        return 2
    if problemes:
        afficher(problemes)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
