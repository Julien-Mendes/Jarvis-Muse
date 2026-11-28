# Étape 11 — Cerveau plus fiable et plus malin (lot B, partie 1)

Sans clé API Anthropic : le cerveau reste **Groq `openai/gpt-oss-120b`**
(modèle par défaut inchangé) ; le repli Claude Haiku / Sonnet fera l'objet
d'un lot séparé quand la clé existera (le code du repli n'est pas touché).

## En bref

| Quoi | Comment |
|---|---|
| Effort de raisonnement | `[cerveau] effort = "bas"` (défaut), `"moyen"` ou `"auto"` |
| Bon outil du premier coup | règles « quel outil pour quoi » dans le prompt système (fr / en) |
| Question ambiguë | une courte question au lieu de deviner (« cherche X », rappel sans heure) |
| Plusieurs étapes | les outils s'enchaînent dans le même tour (« ouvre YouTube puis mets la vidéo X ») |
| Groq lent ou muet | délai par appel, budget par tour, une reprise, message dit à voix haute |

## 1. Effort de raisonnement — `[cerveau] effort`

```toml
[cerveau]
effort = "bas"     # "bas" (défaut) | "moyen" | "auto"
```

- **bas** : `reasoning_effort = "low"` — le comportement d'avant, le plus
  rapide. Recommandé en voix.
- **moyen** : `reasoning_effort = "medium"` — plus lent, réponses plus
  complètes sur les questions complexes. Les jetons de raisonnement comptant
  dans `max_tokens`, la réponse a alors un plancher de 1 500 jetons (sinon
  elle pourrait revenir vide).
- **auto** : bas, sauf quand la question est jugée complexe (plus de
  25 mots, ou « pourquoi », « compare », « explique », « avantages »,
  « calcule », « why », « explain »…) : moyen pour ce tour seulement.

Lu par `config_jarvis.effort_cerveau()` (couches habituelles :
`config.example.toml` < `config.toml` < `config.local.toml`). Une valeur
inconnue donne « bas » (avec un avertissement). Le réglage prime sur les
anciens `[boucle] effort_groq` / `effort_anthropic`, qui ne servent plus que
si la section `[cerveau]` n'a pas de clé `effort`. Le même vocabulaire
(low / medium) vaut pour Claude le jour où le repli sera branché. L'effort
du tour est noté dans le journal des tours (`logs/tours-*.jsonl`, champ
`effort`).

### Mesures (bas contre moyen)

Mesuré le 28 nov. 2026 avec `python scripts\evaluer_cerveau.py`
(Groq `openai/gpt-oss-120b`, palier gratuit, en français, prompt et outils
réels, sans historique ; durée = un appel au cerveau, sans transcription
ni voix ; limites de débit attendues hors chrono) :

| | bas (low) | moyen (medium) |
|---|---|---|
| Questions simples (3) : médiane | 0,47 s (max 0,58) | 0,45 s (max 0,61) |
| Questions complexes (3) : médiane | 0,65 s (max 1,10) | 0,74 s (max 0,77) |
| Jetons produits, simples / complexes | 50 / 92 | 82 / 225 |
| Outil juste du premier coup (13 phrases) | 12 / 13, médiane 0,29 s | 12 / 13, médiane 0,50 s |

**Temps** : sur Groq, l'écart est faible (+0 à +0,2 s) : « moyen »
produit environ deux fois plus de jetons, mais Groq les sort très vite.
**Qualité** : les réponses sont justes dans les deux modes (haïku, distance
de la Lune, ciel bleu, calcul des œufs : 30). « Moyen » détaille davantage
(le calcul des œufs est expliqué : 36 + 36 − 42), ce qui allonge ce que
Jarvis lit à voix haute ; « bas » donne la réponse seule. La comparaison
thermopompe / plinthe part dans les deux modes vers `lancer_recherche`,
comme le veut le prompt. **Recommandation** : garder « bas » en voix ;
« moyen » ou « auto » si Julien veut des explications plus complètes. Le
coût du palier gratuit est la limite de jetons par minute, que « moyen »
atteint plus vite (plus de 429 pendant les rafales de mesure).

Choix d'outil : la seule erreur, dans les deux modes, est « Mets-moi la
vidéo de Lofi Girl » — le modèle répond sans outil (il demande laquelle :
Lofi Girl est une chaîne, pas un titre), ce qui est défendable. Toutes les
autres phrases ambiguës (vidéo précise, site, recherche web, recherche
différée, suivi de recherche, notes, minuteur « réveille-moi », navigation
dans la page, question simple sans outil) prennent le bon outil.

Premier essai (avant les règles de limite de débit du script) : avec la
reprise du SDK, une limite de débit ajoutait 8 à 15 s à un appel — ce que
Julien ressent quand le palier gratuit sature.

## 2. Le bon outil du premier coup

Le prompt système (français et anglais) contient maintenant une section
« Choix de l'outil » :

- « ouvre / mets / lance la vidéo X » → `chercher_et_ouvrir` (jamais
  `ouvrir_navigateur` ni `lancer_recherche`) ;
- « ouvre <site> » → `ouvrir_navigateur` (adresse) ; « cherche X sur
  internet / dans le navigateur » → `ouvrir_navigateur` (recherche) ;
- « fais une recherche sur X », « compare », « reviens-moi avec ça », une
  question à plusieurs sources → `lancer_recherche` ; une question simple →
  réponse directe, sans outil ;
- « où en est ma recherche ? » → `lire_recherche` ;
- « qu'est-ce que je t'ai dit sur X ? » → `chercher_connaissance` ; « note
  que X » est déjà gardé par le code (aucun outil) ;
- minuteur ou rappel avec durée ou heure → `regler_minuteur` ;
- défiler, revenir, la deuxième, actualiser → `naviguer_page` ; un lien
  nommé par son texte → `cliquer`.

Les chemins rapides (sans appel au cerveau) passent avant, dans cet ordre :
confirmation en attente, « note que… », minuteur, écran, fermeture,
navigation dans la page, recherche différée, ouverture de site, puis
clarification. Les tests vérifient le chemin pris par des phrases
ambiguës (« note que la vidéo X est géniale » est une note, « ouvre la
vidéo X » va au cerveau avec `chercher_et_ouvrir`, « cherche X dans le
navigateur » ouvre la recherche, « cherche X » tout court demande…).

## 3. Questions ambiguës : demander au lieu de deviner

Quand se tromper a un coût, Jarvis pose **une** courte question ; la
réponse est lue au tour suivant, dans les **30 s** (comme les « oui » de
confirmation) — sinon la phrase est traitée comme une nouvelle demande.

- **« cherche X »** tout court : « Tu veux que je cherche « X » dans le
  navigateur, ou que je fasse une recherche et que je te revienne avec la
  réponse ? » — « dans le navigateur » ouvre la recherche ; « fais la
  recherche », « reviens-moi » lance la recherche différée.
- **« rappelle-moi de X »** sans heure ni durée : « Quand est-ce que je te
  le rappelle, Julien : à quelle heure, ou dans combien de temps ? » —
  « dans 20 minutes », « à 18 h 30 », « in 2 hours »… règle le rappel avec
  l'étiquette X.

Pas de question pour les actions sans risque ou déjà claires : « ouvre
youtube.com », « descends », « cherche X dans le navigateur », « rappelle-moi
de X à 18 h 30 ». Pour les autres cas (quel minuteur, quelle note…), le
prompt demande au modèle de poser la question lui-même.

## 4. Plusieurs étapes dans un tour

« Ouvre YouTube puis mets la vidéo X », « cherche la vidéo X puis ouvre la
deuxième », « mets un minuteur de 10 minutes et lance la vidéo X » : la
phrase est reconnue comme une demande à plusieurs étapes (puis, ensuite,
« et » suivi d'un verbe d'action) et va directement au cerveau — un chemin
rapide n'en aurait fait qu'une partie. Le cerveau enchaîne les outils dans
le tour (jusqu'à `max_tours_outils` rondes, 3 par défaut), sans redemander à
Julien entre les étapes.

Les outils à réponse directe (vidéo ouverte, titre de page, recherche
lancée ou lue) gardent la règle §1 : leur texte, qui contient des données
externes, est **dit à Julien** à la fin du tour mais **jamais redonné au
modèle** ; le modèle reçoit seulement « Fait, et déjà annoncé à Julien ».
Une demande à une seule étape s'arrête toujours à la première réponse
directe : aucune latence en plus. Si le cerveau tombe au milieu d'un
enchaînement, Jarvis dit ce qui est déjà fait.

## 5. Fiabilité : quand Groq ne répond pas

- **Délai par appel** : `[boucle] delai_cerveau_s` (20 s par défaut), une
  seule reprise automatique du SDK (inchangé, B1).
- **Budget du tour** : `[boucle] delai_tour_s` (45 s par défaut, 5 à 300) —
  toutes les rondes d'outils comprises. Chaque appel est borné au temps qui
  reste (divisé par deux : la reprise doit aussi tenir). Budget épuisé :
  plus aucun appel ; Jarvis dit ce qui est déjà fait, ou que le cerveau est
  trop lent.
- **Transcription Groq** : délai explicite de 20 s et une reprise (avant :
  60 s et deux reprises, le défaut du SDK).

Ce que Julien entend — **jamais de silence** :

| Situation | Message (fr) |
|---|---|
| Délai dépassé (appel ou tour) | « Désolé Julien, le cerveau met trop de temps à répondre. Réessaie dans un instant. » |
| Groq injoignable (réseau, 5xx) | « Désolé Julien, je n'ai pas pu joindre le cerveau pour l'instant. » |
| Limite de débit (429) | « Je suis limité en ce moment, Julien — le palier gratuit me fait attendre. Réessaie dans quelques secondes. » |
| Clé refusée (401/403) | « Mon accès au cerveau est refusé, Julien — vérifie la clé dans le fichier .env. » |
| Modèle retiré (404) | « Le modèle du cerveau n'est plus disponible… » |
| Transcription impossible | « Désolé Julien, je n'ai pas pu transcrire ce que tu as dit. Réessaie en maintenant F9. » (nouveau : avant, rien n'était dit) |

Les mêmes messages existent en anglais. La catégorie vient du code d'état
HTTP ou du type d'erreur, jamais du texte du message. Le repli automatique
vers Claude Haiku (lot robustesse) reste en place mais inactif sans
`ANTHROPIC_API_KEY`. Le panneau Agents de l'application passe « Cerveau » ou
« Voix » en erreur.

Pire cas d'attente d'un tour : environ `delai_tour_s` (45 s), contre
`max_tours_outils × 2 × delai_cerveau_s` (120 s) avant.

## Mesurer soi-même

```powershell
python scripts\evaluer_cerveau.py                 # bas puis moyen, en français
python scripts\evaluer_cerveau.py --efforts moyen --langue en
python scripts\evaluer_cerveau.py --sortie mesures.json
```

Appels réels (palier gratuit Groq) ; rien n'est exécuté ni écrit dans
`logs/` ou `data/`. Une limite de débit (429) est attendue **hors chrono**
puis l'appel est refait : les durées sont celles du modèle.

## Limites

- Repli Claude Haiku / Sonnet : lot séparé, quand la clé API sera créée.
- La complexité du mode « auto » est une heuristique (mots-clés, longueur),
  pas un jugement du modèle.
- Clarification par le code pour deux cas seulement (« cherche X »,
  rappel sans heure) ; les autres ambiguïtés reposent sur le prompt.
- Enchaînement : `max_tours_outils` rondes (3) — une demande à quatre étapes
  s'arrête après la troisième et dit ce qui est fait.
- Palier gratuit Groq : la limite de jetons par minute se fait sentir
  pendant les rafales (mesures ci-dessus) ; Jarvis le dit mais ne peut pas
  l'éviter.
