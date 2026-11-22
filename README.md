# Jarvis-Muse

Pont entre Carson (Muse) et un assistant local façon Jarvis.

## Le plan

### Étape 1 — L’équivalent Muse (en place)
- Carson comme agent : voix temps réel, mémoire, connecteurs, veilles.
- Muse Code pour l’outillage local.

### Étape 2 — Connecter Carson au Jarvis local
Ce dépôt est le pont : scripts, configurations et petites fonctions versionnés ici, que Carson peut lire et mettre à jour.

Ponts envisagés, dans l’ordre :
1. **GitHub** (ce dépôt) — modèle éprouvé, comme pour l’app d’entraînement.
2. Tailscale
3. Muse Mail
4. Docs / Drive partagés

Idée en réflexion : Carson envoie ses résumés au Jarvis local pour lecture à voix haute à la maison.

## Limites connues
- Pas de mot de réveil.
- Pas de serveur local toujours allumé.
- Carson ne voit pas l’écran et ne contrôle pas le PC directement.

## Structure
- `scripts/` — scripts du Jarvis local
- `config/` — configurations
- `docs/` — notes et plans

## Statut
Exploration — rien d’acheté, rien de construit pour l’instant.
