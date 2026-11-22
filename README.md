# Jarvis-Muse

Pont entre Carson (Muse) et un assistant local façon Jarvis.

## Direction (décidée le 21 novembre 2026)

Hybride : le spectaculaire du dépôt A (Julian-Ivanov/jarvis-voice-assistant —
vision d'écran, contrôle du navigateur et du PC) + la structure du dépôt B
(tanishvbuk/jarvis-assistant — outils Google, minuteurs, HUD, sécurité), le tout
en français, avec Carson comme cerveau.

Analyse complète des deux dépôts : `docs/` (25 pages, 39 capacités,
19 décisions à cocher).

## Le plan

### Étape 1 — L'équivalent Muse (en place)
- Carson comme agent : voix temps réel, mémoire, connecteurs, veilles.
- Muse Code pour l'outillage local.

### Étape 2 — Connecter Carson au Jarvis local
Ce dépôt est le pont : scripts, configurations et petites fonctions versionnés ici, que Carson peut lire et mettre à jour.

Ponts envisagés, dans l'ordre :
1. **GitHub** (ce dépôt) — modèle éprouvé, comme pour l'app d'entraînement.
2. Tailscale
3. Muse Mail
4. Docs / Drive partagés

Idée en réflexion : Carson envoie ses résumés au Jarvis local pour lecture à voix haute à la maison.

## Feuille de route

Principe : ne pas transcrire le code Claude vers Muse Code d'un bloc. Construire
étape par étape, en français, en gardant Carson comme cerveau et ce dépôt comme
pont — et ne construire une brique locale que si elle apporte quelque chose que
Carson ne fait pas déjà.

| Étape | Contenu | Statut |
|---|---|---|
| 0 — Décisions | Cocher la liste du §5 de la description | ✅ En cours — 11 décisions validées le 21 nov. 2026 |
| 1 — Fondations | `config/` séparé (publique / locale / secrets), règles de sécurité écrites (`docs/regles-securite.md`) | ✅ Fait |
| 2 — Voix locale | Vérifier une voix française (Piper `gilles` / Kokoro) ; petit script qui lit à voix haute un texte fourni par Carson. Bilingue FR + EN. Push-to-talk (F9) comme déclencheur simple, avant tout mot de réveil. | 🚧 En cours — livré le 21 nov. : `scripts/lire_voix.py` (Piper, bilingue FR/EN), `scripts/requirements-etape2.txt`, `docs/etape-2-voix.md`, dossier `a-dire/` pour les textes à lire. Reste : installation et test sur le laptop de Julien (Python + Piper + voix `gilles`), puis premier résumé lu à voix haute. Déclencheur F9 validé le 21 nov. comme déclencheur pour la suite (étape 4) — le script s'invoque en ligne de commande pour l'instant. |
| 3 — Minuteur local persistant | Reprendre le patron `timers.py` du dépôt B (JSON persistant, carillon, annonce des retards au démarrage). Première brique qui agit seule, sans Carson. | 🚧 En cours — livré le 21 nov. : `scripts/minuteur.py` (compte à rebours / rappel à heure fixe, JSON persistant, carillon + annonce vocale via `lire_voix.py`, annonce des retards au démarrage), `docs/etape-3-minuteur.md`. Reste : test sur le laptop de Julien (minuteur d'1 minute, lister, annuler). Auto-start au login : décision encore ouverte, non configuré dans cette étape. |
| 4 — Déclenchement | Boucle vocale interactive F9 (maintenir pour parler, relâcher pour envoyer, F9 pour interrompre). Cerveau par défaut : Groq gratuit (gpt-oss-120b) ; Claude Haiku par API en alternative configurable. STT Groq Whisper, interchangeable avec faster-whisper local. Premier outil : le minuteur. | 🚧 En cours — livré le 21 nov. : `scripts/boucle_voix.py` (F9, STT Groq Whisper interchangeable, cerveau Groq / Haiku configurable, outil minuteur), `scripts/requirements-etape4.txt`, `docs/etape-4-declenchement.md`. Reste : test sur le laptop de Julien (clé Groq gratuite, premier tour « mets un minuteur d'une minute »). |
| 5 — Yeux et mains | Vision d'écran ciblée + contrôle navigateur (Playwright), avec consentement explicite et capture limitée. Plus gros chantier ; comble la plus grande limite de Carson. | 🚧 En cours — livré le 21 nov. : `scripts/yeux.py` (capture ciblée fenêtre/région, vision Groq qwen3.8-27b par défaut — un seul service Groq — Haiku en repli, confirmation orale avant chaque capture), `scripts/navigateur.py` (Playwright : ouvrir, rechercher, cliquer, lire, capture de page ; lecture seule, aucun formulaire/connexion/achat), `scripts/requirements-etape5.txt`, `docs/etape-5-yeux-mains.md`. Branchés dans `scripts/boucle_voix.py` (« regarde mon écran » avec confirmation, « ouvre [site] »). Reste : test sur le laptop de Julien (première capture décrite, première ouverture de navigateur). Modèle vision Groq (Llama 4 Scout) retiré du palier gratuit le 17 juill. 2026 — défaut basculé vers Groq qwen3.8-27b (preview, retirable à court préavis) le 21 nov., Haiku en repli. |
| 6 — HUD local léger + lancement de session | Anneau d'état et cartes, version allégée ; séquence de lancement (apps + quadrants) et auto-start au login. | 🚧 En cours — livré le 21 nov. : `scripts/hud.py` (Tkinter, bibliothèque standard — anneau d'état 4 états + minuteur échu/erreur, panneau au survol, clic maintenu = F9, < 100 Mo et ~0 % CPU visés), `scripts/lancer_session.ps1` (vérifications → surveillant de minuteurs → minuteurs du jour → lecture de a-dire/ → HUD → quadrants → boucle vocale, puis « Jarvis prêt »), `docs/etape-6-hud-session.md`, `scripts/requirements-etape6.txt` (aucune dépendance nouvelle — Tkinter standard), sections `[hud]` et `[session]` dans `config.example.toml`, `[quadrants]` dans `config.local.example.toml` (vide par défaut, à compléter avec Julien). Auto-start (bloc 25, validé le 21 nov.) : étape 1 livrée — `scripts/installer_demarrage.ps1` (raccourci dans le dossier Démarrage, semaine de test) ; étape 2 (Planificateur de tâches) documentée dans le guide, à configurer après la semaine de test. Reste : test sur le laptop de Julien (HUD seul, session complète, mesure RAM/CPU, raccourci au login). Notes quotidiennes et lecture de page complète : décisions encore ouvertes, non construites. |
| 7 — Serveur local | FastAPI ou aiohttp sur 127.0.0.1 uniquement, jamais 0.0.0.0 sans authentification. Seulement si un mini-PC / PC toujours allumé entre en jeu. Tailscale comme pont distant, après GitHub. | En suspens (hardware) |

À ne pas construire : tout le bloc 6 (doublons de Carson), la domotique et la
musique tant que le besoin n'est pas exprimé, et aucune transcription intégrale
du code allemand ou anglais.

## Décisions validées le 21 novembre 2026

| Bloc | Capacité | Décision |
|---|---|---|
| 1 — Fondations | Règles de sécurité (données externes enveloppées + blocage des écritures + confirmation en code) | ✅ Oui |
| 1 — Fondations | Configuration séparée (publique / locale privée / secrets en .env) | ✅ Oui |
| 1 — Fondations | Journalisation par tour sans contenu | ⏳ Plus tard |
| 2 — Voix locale | TTS locale bilingue FR + EN (Piper `gilles` en français, Kokoro/Piper en anglais) | ✅ Oui |
| 2 — Voix locale | Mot de réveil local | ⏳ Plus tard |
| 2 — Voix locale | Double-clap | ⏳ Plus tard |
| 3 — Temps et rappels | Minuteur / rappels persistants | ✅ Oui |
| 4 — Yeux et mains | Vision d'écran (capture ciblée, consentement explicite à chaque capture) | ✅ Oui |
| 4 — Yeux et mains | Contrôle du navigateur (Playwright) | ✅ Oui |
| 5 — Interface et session | HUD local léger | ✅ Oui |
| 5 — Interface et session | Serveur local | ⏳ En suspens — hardware (mini-PC) à venir ; le logiciel tourne sur le laptop en attendant pour tester |

Reste à décider : STT local, notes quotidiennes, lecture de
page complète, lancement de session + quadrants, auto-start, bloc 6 (doublons).

## Sécurité

Voir `docs/regles-securite.md`. En résumé : données externes traitées comme non
fiables, écritures bloquées après lecture externe, confirmations vérifiées en
code, serveur local sur 127.0.0.1 seulement, secrets dans `.env` (gitignoré).

## Limites connues
- Pas de mot de réveil.
- Pas de serveur local toujours allumé (logiciel testable sur le laptop ;
  hardware mini-PC en suspens).
- Vision d'écran et contrôle navigateur livrés (étape 5) — test à faire sur
  le laptop de Julien. La lecture complète de page en boucle vocale attend
  la décision bloc 16 (disponible en ligne de commande seulement).

## Structure
- `scripts/` — scripts du Jarvis local (`lire_voix.py`, `minuteur.py`, `boucle_voix.py`, `yeux.py`, `navigateur.py`, `hud.py`, `lancer_session.ps1`, `installer_demarrage.ps1`, `requirements-etape2.txt`, `requirements-etape4.txt`, `requirements-etape5.txt`, `requirements-etape6.txt`)
- `data/` — minuteurs persistants (`timers.json`, gitignoré, jamais poussé), état du HUD (`hud-state.json`, `hud-ptt.json`, `widget.json`, gitignorés)
- `a-dire/` — textes à lire à voix haute (déposés par Carson via le pont GitHub)
- `config/` — configurations (`config.example.toml`, `config.local.example.toml`, `.env.example`)
- `docs/` — notes et plans (description complète des deux Jarvis Claude, règles de sécurité, guide de la voix locale)
- `models/` — voix Piper téléchargées (gitignoré, jamais poussé dans le dépôt)

## Statut
Étape 1 (fondations) en place. Étape 2 (voix locale) livrée dans le dépôt —
test à faire sur le laptop de Julien. Étape 3 (minuteur persistant) livrée
dans le dépôt — test à faire sur le laptop de Julien (minuteur d'1 minute).
Étape 4 (boucle vocale F9) livrée dans le dépôt — test à faire sur le laptop
de Julien (clé Groq gratuite, premier tour « mets un minuteur d'une minute »).
Étape 5 (yeux et mains) livrée dans le dépôt — test à faire sur le laptop de
Julien (première capture décrite, première ouverture de navigateur, première
recherche). Étape 6 (HUD léger + lancement de session) livrée dans le dépôt —
test à faire sur le laptop de Julien (HUD seul, session complète, mesure
RAM/CPU). Rien d'acheté, rien de construit pour l'instant.
