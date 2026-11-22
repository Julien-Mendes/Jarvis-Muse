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
| 2 — Voix locale | Vérifier une voix française (Piper `gilles` / Kokoro) ; petit script qui lit à voix haute un texte fourni par Carson. Bilingue FR + EN. Push-to-talk (F9) comme déclencheur simple, avant tout mot de réveil. | À faire |
| 3 — Minuteur local persistant | Reprendre le patron `timers.py` du dépôt B (JSON persistant, carillon, annonce des retards au démarrage). Première brique qui agit seule, sans Carson. | À faire |
| 4 — Déclenchement | Mot de réveil français (si un modèle existe) ou double-clap ; sinon, garder le push-to-talk. | Plus tard |
| 5 — Yeux et mains | Vision d'écran ciblée + contrôle navigateur (Playwright), avec consentement explicite et capture limitée. Plus gros chantier ; comble la plus grande limite de Carson. | À faire |
| 6 — HUD local léger + lancement de session | Anneau d'état et cartes, version allégée ; séquence de lancement (apps + quadrants) et auto-start au login. | À faire |
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

Reste à décider : push-to-talk F9, STT local, notes quotidiennes, lecture de
page complète, lancement de session + quadrants, auto-start, bloc 6 (doublons).

## Sécurité

Voir `docs/regles-securite.md`. En résumé : données externes traitées comme non
fiables, écritures bloquées après lecture externe, confirmations vérifiées en
code, serveur local sur 127.0.0.1 seulement, secrets dans `.env` (gitignoré).

## Limites connues
- Pas de mot de réveil.
- Pas de serveur local toujours allumé (logiciel testable sur le laptop ;
  hardware mini-PC en suspens).
- Carson ne voit pas l'écran et ne contrôle pas le PC directement (étape 5
  en cours de planification).

## Structure
- `scripts/` — scripts du Jarvis local
- `config/` — configurations (`config.example.toml`, `config.local.example.toml`, `.env.example`)
- `docs/` — notes et plans (description complète des deux Jarvis Claude, règles de sécurité)

## Statut
Étape 1 (fondations) en place — rien d'acheté, rien de construit pour l'instant.
