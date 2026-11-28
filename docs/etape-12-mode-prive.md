# Étape 12 — Mode privé (lot PR)

En mode privé, Jarvis marche comme d'habitude pendant la session, mais
**rien n'est gardé** : aucune recherche, aucune demande, aucune conversation
n'est écrite sur le disque, et tout est oublié quand tu sors du mode.

## En bref

| Quoi | Comment |
|---|---|
| Entrer (voix) | « mode privé », « navigation privée », « passe en mode privé » — *private mode*, *go private*, *switch to private mode* |
| Sortir (voix) | « sors du mode privé », « quitte le mode privé », « mode normal » — *exit private mode*, *leave private mode*, *normal mode* |
| Entrer / sortir (application) | menu **Affichage → Mode privé : activer / quitter** |
| Indicateur | pastille violette **● PRIVÉ** dans l'en-tête, et « Mode privé : rien n'est gardé… » sous l'état au repos |
| Annonces | « Mode privé activé : rien ne sera gardé. » / « Mode privé désactivé. » (*Private mode on: nothing will be kept.* / *Private mode off.*) |

La commande est reconnue **par le code, sans appel au modèle**, et seulement
quand la phrase entière est la commande (avec « Jarvis », « s'il te plaît »,
« please »… autour) : « c'est quoi le mode privé de Chrome ? » reste une
question normale. L'annonce est dite dans la langue de la commande ; pour
l'interrupteur, dans la langue affichée par l'application.

## Ce qui se passe

**À l'entrée.** Le contexte du modèle repart de zéro (la session privée ne
voit pas l'historique d'avant). Le contexte d'avant est mis de côté en
mémoire ; une confirmation en attente (« garder ce résumé ? », « je peux
regarder ton écran ? »…) est annulée.

**Pendant le mode** — rien n'est écrit pour la conversation :

| Fichier | En mode privé |
|---|---|
| `data/conversations/AAAA-MM-JJ.jsonl` (historique du jour) | rien n'est écrit — les échanges ne s'affichent donc pas dans la fenêtre |
| `logs/tours-AAAA-MM-JJ.jsonl` (journal des tours) | rien n'est écrit : il ne contient pas de texte, mais les heures et les noms d'outils suffiraient à retracer la session |
| `data/recherches.json` | rien n'est écrit : les recherches de la session vivent en mémoire (`recherche.Memoire`), avec leur propre travailleur, et sont annoncées / lues comme d'habitude |
| `data/taches_longues.json` (lot LT) | rien n'est écrit : une tâche longue lancée en mode privé vit en mémoire avec son travailleur ; le travailleur normal est suspendu jusqu'à la sortie — voir `docs/etape-13-taches-longues.md` |
| `data/connaissances.json` (notes) | « note que… » est refusé : « En mode privé, je ne garde pas de notes. » ; Jarvis ne propose pas de garder un résultat de recherche |
| `data/hud-state.json` | état, langue et agents oui ; `transcription` toujours vide ; `"prive": true` |
| `logs/boucle.log` (sortie console via `lancer_app.py`) | « Julien : (mode privé) » / « Jarvis : (mode privé) » à la place du texte |

**Les minuteurs** continuent de fonctionner : ce sont des actions, pas de
l'historique. Ils sont écrits dans `data/timers.json` (sinon ils ne
sonneraient pas) et apparaissent dans le panneau Minuteurs ; la demande
elle-même n'est écrite nulle part ailleurs.

**À la sortie.** Le contexte de la session privée et ses recherches sont
jetés (le travailleur privé est arrêté ; une recherche en cours est
abandonnée sans rien écrire ni relancer Chrome). Le contexte d'avant est
rendu, l'historique, le journal des tours et les notes reprennent. Les
recherches normales terminées pendant le mode privé sont annoncées à ce
moment-là. Rien de la session privée n'apparaît dans le panneau
Conversations ni dans l'Historique. Fermer Jarvis en mode privé jette aussi
tout.

## Comment l'interrupteur parle à la boucle

L'application écrit `data/prive-demande.json` — `{"actif": true|false,
"langue": "fr"|"en", "horodatage": …}`, **sans aucun contenu** — que la
boucle sonde avec la demande texte (toutes les 0,2 s, coût négligeable) et
supprime à la lecture ; une demande de plus de 5 minutes est ignorée. La
pastille suit l'état que la boucle **confirme** (`"prive"` de
`hud-state.json`), pas le clic : si la boucle est arrêtée, rien ne change.

En ligne de commande (`boucle_voix.py --texte "mode privé"`), un tour isolé
ne peut pas rester en mode privé : Jarvis le dit, sans rien écrire.

## Garde-fous inchangés

Règles §1 (données externes enveloppées, jamais redonnées au modèle), §2
(hold_writes) et §3 (confirmations en code), garde-fous C1 du navigateur :
rien ne change en mode privé. Budget 200 Mo / ~0 % CPU au repos : aucun fil
de plus hors mode privé (le travailleur privé n'existe que pendant le mode).

## Limites

- **Messages tapés** : le texte transite par `data/texte-demande.json`, écrit
  par l'application et supprimé par la boucle dans les 0,2 s — c'est le
  seul canal entre les deux processus. À la voix, la demande ne touche
  jamais le disque.
- **Voix** : chaque phrase dite est synthétisée dans un fichier WAV
  temporaire (`%TEMP%`), supprimé dès qu'il a été joué (comme hors mode
  privé).
- **Affichage** : comme l'historique du jour n'est pas écrit, la fenêtre
  n'affiche pas les bulles de la session privée (les réponses sont dites à
  voix haute). Les afficher sans disque demanderait un canal direct entre
  l'application et la boucle (tube nommé), hors de ce lot.
- **Services externes** : Groq (transcription, cerveau) et les sites visités
  reçoivent les demandes comme d'habitude ; le mode privé ne couvre que ce
  que Jarvis garde sur la machine. La session Chrome pilotée est déjà
  éphémère (aucun profil gardé sur le disque).
- Le mode privé ne survit pas à un redémarrage de la boucle : elle repart
  toujours en mode normal.
