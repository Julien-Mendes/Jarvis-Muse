# Étape 2 — Voix locale (Piper, bilingue FR + EN)

**Décision (21 nov. 2026) :** voix locale pour lire les résumés de Carson à voix
haute à la maison, bilingue français + anglais. Le script `scripts/lire_voix.py`
lit un texte avec Piper, un moteur de synthèse vocale 100 % local : aucune
donnée ne quitte la machine, aucun appel réseau pendant la lecture.

**Choix des voix (vérifié le 21 nov. 2026) :**
- Français : Piper `fr_FR-upmc-medium` — voix féminine (UPMC/LIMSI), choisie
  le 21 nov. 2026 (Gilles jugée trop robotique, Tom écartée aussi).
- Anglais : Piper `en_GB-alan-medium` — voix masculine britannique. **Langue
  par défaut à moyen terme** (décision 21 nov. 2026) : les voix françaises
  écoutées ne sont pas assez naturelles pour l'instant ; le français reste
  disponible avec `--langue fr` (voix UPMC).
- Kokoro (voix britanniques `bm_george`, `bm_lewis`, `bm_daniel`, `bm_fable`)
  reste une option ultérieure pour l'anglais, pas pour cette étape.

## Prérequis

- Windows 10/11 (laptop de Julien).
- Python 3.10 ou plus, installé avec l'option « Add Python to PATH » cochée.
- Une sortie audio (haut-parleurs ou écouteurs).
- Connexion Internet **seulement** pour l'installation et le téléchargement
  des voix (une fois). La lecture ensuite est hors ligne.

## Installation (à faire une seule fois, sur le laptop)

Ouvrir PowerShell dans le dossier du dépôt (cloné depuis GitHub), puis taper
ces commandes dans l'ordre :

```powershell
# 1. Créer et activer un environnement virtuel
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Installer les dépendances
pip install -r scripts\requirements-etape2.txt

# 3. Télécharger les deux voix (français + anglais, ~60 Mo chacune)
python -m piper.download_voices fr_FR-upmc-medium en_GB-alan-medium --data-dir models
```

Si PowerShell refuse d'activer l'environnement (`running scripts is disabled`),
lancer d'abord (une seule fois) :
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
puis recommencer l'activation.

## Utilisation

```powershell
# Lire un texte directement
python scripts\lire_voix.py --texte "Bonjour Julien, voici ton résumé du matin."

# Lire un texte en anglais
python scripts\lire_voix.py --texte "Good morning, sir." --langue en

# Lire un fichier texte (par exemple un résumé déposé par Carson)
python scripts\lire_voix.py --fichier a-dire\resume.txt

# Changer de voix ou de vitesse (0.5 à 2.0, défaut 1.0)
python scripts\lire_voix.py --texte "Test." --voix fr_FR-siwis-medium --vitesse 1.2

# Enregistrer l'audio dans un fichier .wav au lieu de le jouer
python scripts\lire_voix.py --texte "Test." --sortie test.wav
```

## Tester avec un résumé de Carson

C'est le premier test concret de cette étape :

1. Carson dépose un résumé en `.txt` dans le dossier `a-dire/` via le pont
   GitHub (le dossier est versionné dans le dépôt).
2. Sur le laptop, récupérer la mise à jour : `git pull` (ou synchroniser
   le dépôt dans Muse Code).
3. Lancer la lecture :
   ```powershell
   python scripts\lire_voix.py --fichier a-dire\resume.txt
   ```

Le dossier `a-dire/` ne doit contenir que des textes à lire : jamais de
contenu sensible (mot de passe, code, information privée).

## Dépannage

| Problème | Solution |
|---|---|
| `python n'est pas reconnu` | Python n'est pas dans le PATH : réinstaller Python en cochant « Add Python to PATH », ou utiliser `py` à la place de `python`. |
| `le module piper n'est pas installé` | Activer l'environnement virtuel (`.venv\Scripts\Activate.ps1`), puis `pip install -r scripts\requirements-etape2.txt`. |
| `voix introuvable dans models` | Télécharger la voix indiquée : `python -m piper.download_voices fr_FR-upmc-medium --data-dir models` (ou `en_GB-alan-medium` pour l'anglais). Vérifier que les fichiers `.onnx` et `.onnx.json` sont bien dans `models/`. |
| Pas de son | Vérifier le volume et la sortie audio par défaut de Windows (icône haut-parleur). Tester avec `--sortie test.wav`, puis ouvrir le fichier : si le WAV contient du son, le problème vient de la sortie audio, pas de Piper. |
| La voix parle trop vite / trop lentement | Ajuster avec `--vitesse` (ex. `--vitesse 0.9` pour ralentir). |
| Erreur liée à espeak / phonèmes | Réinstaller Piper : `pip install --force-reinstall piper-tts` (le paquet inclut ses propres données de prononciation). |
| `running scripts is disabled` | Voir la section Installation : `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |

## Sécurité (rappel)

- Lecture 100 % locale : le texte lu et l'audio généré ne quittent jamais la
  machine. Aucune clé API, aucun compte, aucun appel réseau pendant la lecture.
- Les voix téléchargées (`models/`) sont gitignorées : elles ne sont jamais
  poussées dans le dépôt.
- Le script ne fait qu'une chose : lire un texte à voix haute. Il n'écrit
  rien d'autre, ne modifie aucun fichier, ne lance aucune application.
- Règles complètes : `docs/regles-securite.md`.

## Ce qui n'est pas dans cette étape

- Pas de mot de réveil (« Hey Carson ») : décision « plus tard ».
- Pas de double-clap : décision « plus tard ».
- Pas de boucle interactive ni d'écoute en continu : le script est invoqué en
  ligne de commande. Le déclencheur choisi pour la suite est le **push-to-talk
  F9** (validé le 21 nov. 2026 : maintenir F9 pour parler, relâcher pour
  arrêter) — il sera construit à l'étape 4, après le minuteur.
- Pas de STT (transcription) : décision non tranchée.

## Statut

- ✅ Script `scripts/lire_voix.py` et guide livrés dans le dépôt (21 nov. 2026).
- ⏳ Reste : installation et premier test sur le laptop de Julien (Python +
  Piper + voix `upmc` (français) et `alan` (anglais, défaut à moyen terme)), puis premier résumé lu à voix haute.
