# Étape 13 — Tâches longues (lot LT)

Jarvis peut travailler plusieurs minutes, voire plusieurs heures, sur une
tâche compliquée, sans abandonner, pendant que la boucle vocale reste
réactive. Il fait d'abord un plan, exécute et vérifie chaque étape une par
une, puis annonce la fin et propose de lire le résultat.

## Ce qu'on dit

| Demande | Ce que fait Jarvis |
|---|---|
| « C'est une longue tâche : compare les trois forfaits mobiles » / *This is a long task: compare the best e-bikes* | Lance la tâche (sans appel au modèle) : « C'est parti, Julien : je travaille sur « … » en arrière-plan, avec un budget de 30 minutes… » |
| « Prends le temps qu'il faut pour planifier mon voyage » / *Take as long as you need to write a study plan* | Pareil |
| « Travaille là-dessus pendant longtemps : … » / *Work on this for a while: …* | Pareil |
| « Travaille là-dessus pendant 2 heures : … » / *Work on my essay for 90 minutes* | Pareil, et **la durée dite devient le budget** de la tâche |
| « C'est une longue tâche » / « Prends le temps qu'il faut » (seul) | La tâche porte sur la phrase précédente de Julien |
| Demande de plus de 3 étapes de recherche, d'analyse ou de rédaction | Le cerveau peut **proposer** : « C'est une grosse tâche, Julien : je peux y travailler en arrière-plan, ça te va ? » — un « oui » oral dans les 30 s la lance ; « non » ou toute autre phrase l'annule |
| « Où en est ma tâche ? » / *How's my task going?* | « Ta tâche « … » avance : 2 étapes faites sur 4, je suis sur « … ». 12 minutes sur un budget de 30 minutes. » |
| « Qu'est-ce qui reste ? » / *What's left?* | La liste des étapes qui restent (seulement si une tâche longue est en cours ; sinon la question va au cerveau comme avant) |
| « Lis-moi le résultat de ma tâche » / *Read me the result of my task* | Lit le résultat (ou ce qui est fait, si la tâche s'est arrêtée) |
| « Annule ma tâche longue » / *Cancel my task* | Arrête la tâche en cours et dit ce qui était fait |

Les durées reconnues : « pendant 2 heures », « pendant 45 minutes », « pendant
une heure et demie », « pendant une demi-heure », « pendant 1h30 », *for two
hours*, *for 90 minutes*, *for half an hour*. Seule la partie **avant les
deux-points** compte : dans « c'est une longue tâche : un plan pour 3 heures
de sport », les 3 heures font partie de l'objectif, pas du budget.

« Où en est ma tâche ? » et « qu'est-ce qui reste ? » sont répondus **à partir
du fichier** `data/taches_longues.json` : le travailleur n'est ni réveillé ni
interrompu, la réponse est immédiate.

**Fin de tâche.** Au prochain moment calme, Jarvis annonce la fin à voix
haute, **dans la langue du tour qui a lancé la tâche** (une tâche lancée en
anglais est annoncée en anglais, avec la voix anglaise, même si la boucle est
réglée en français) : « J'ai terminé ta tâche longue « … », Julien. Veux-tu
que je te lise le résultat ? ». Un « oui » dans les 30 s le lit ; « non »
répond « D'accord, Julien. Le résultat reste dans le panneau Tâches
longues. ».

**Panneau.** L'application montre le panneau **Tâches longues** sous
Recherches (rangée suivante) : « titre — 3/7 · en cours », avec un point de
couleur (en cours, en attente, terminée, bloquée, budget épuisé). Un clic
ouvre le détail : état, progression, temps utilisé sur le budget, objectif,
plan coché (✓ faite, → en cours, · à faire), puis le résultat ou ce qui a
arrêté la tâche. Le tableau de bord gagne une ligne **Tâches** dans Agents.

## Comment ça marche

- **Fichier** (`scripts/taches_longues.py`) : `data/taches_longues.json`
  (gitignoré), écrit de façon atomique et sous verrou, comme
  `recherches.json`. Une tâche : titre, objectif, langue du tour, état
  (`en_cours`, `terminee`, `bloquee`), plan (chaque étape : description,
  type, état, résultat), étape en cours, étapes faites, budget, temps
  utilisé, résultat. Au plus 3 tâches en cours ou en attente (une seule
  travaille à la fois), et les 20 dernières finies.
- **Travailleur** : un fil daemon de la boucle vocale, sur le patron du lot
  R1 — **son propre cerveau** (Groq gpt-oss-120b, effort « moyen » : la
  latence ne compte pas en arrière-plan), jamais celui de la boucle. Au
  repos, il dort sur un événement (réveil à chaque nouvelle tâche, sinon
  toutes les 30 s) : **+0,2 Mo, 0,00 % CPU** mesurés sur 10 s.
- **Plan** : avant d'exécuter, le cerveau découpe la tâche en 2 à 15 étapes
  (JSON ; à défaut, une liste numérotée est acceptée). Le plan est écrit dans
  le fichier et **ne change plus**. Trois plans illisibles de suite =
  blocage (« je n'ai pas réussi à découper la tâche en étapes »).
- **Étapes**, une par une, dans l'ordre :
  - `reflexion` : le cerveau raisonne, analyse ou rédige à partir de
    l'objectif, du plan et des résultats des 6 dernières étapes faites ;
  - `recherche_web` : la recherche du lot R1 (DuckDuckGo, 3 pages au plus)
    dans un **Chrome réduit séparé**, fermé après l'étape ;
  - `notes` : les notes de Julien trouvées par mots-clés (lecture seule).
- **Vérification** : après chaque étape, un second appel vérifie que le
  résultat fait ce que l'étape demande (`{"ok": true}` ou `{"ok": false,
  "remarque": …}`). Refusé : l'étape est refaite avec la remarque, jusqu'à
  3 essais ; au 3e refus, la tâche s'arrête (« l'étape « … » n'a pas passé la
  vérification après 3 essais »). Un vérificateur qui répond mal (pas de
  JSON, vide) ne bloque pas la tâche.
- **Point de reprise** : l'étape en cours est notée avant de la commencer,
  son résultat et le temps utilisé juste après. À la fin, le cerveau rédige
  le résultat final (4 à 10 phrases, à lire à voix haute).
- **Reprise au redémarrage** : au lancement, une tâche `en_cours` déjà
  démarrée reprend **là où elle s'était arrêtée** (l'étape interrompue est
  refaite, les autres non), et Jarvis l'annonce au premier moment calme :
  « Je reprends ta tâche longue « … » là où je l'avais laissée : étape 3 sur
  7. ». Après 10 interruptions, la tâche est arrêtée proprement.

## Ne jamais abandonner sur une erreur transitoire

- **429** (limite de Groq), **délai dépassé**, **cerveau injoignable** (réseau,
  5xx) : le travailleur attend puis réessaie, avec des attentes croissantes
  de 5, 10, 20, 40, 80 puis 120 s (répétées), **autant de fois qu'il faut**
  tant que le budget le permet. Pendant l'attente, « où en est ma tâche ? »
  ajoute « Le cerveau ne répond pas pour l'instant (limite de débit de
  Groq) : j'attends et je réessaie. ».
- **Débit** : un limiteur à fenêtre glissante de 60 s respecte le palier
  gratuit Groq (**8 000 jetons par minute**). Le travailleur réserve avant
  chaque appel (entrée estimée + plafond de sortie) et laisse un quart du
  débit à la boucle vocale, qui note ses propres jetons après chaque tour :
  une conversation pendant une tâche longue ne tombe pas sur un 429.
- **Blocage dur** — arrêt net, sans attente inutile : clé refusée ou absente
  (401 / 403), modèle retiré (404), plan impossible, vérification ratée
  3 fois, Chrome impossible à piloter 3 fois de suite. Jarvis dit **ce qui
  bloque, ce qui est fait et ce qui reste** : « Je me suis arrêté sur ta tâche
  longue « … », Julien : la clé du cerveau est absente ou refusée (à vérifier
  dans .env). Fait : 1 étape sur 3. Il reste : … Veux-tu que je te lise ce
  qui est fait ? »
- **Budget** par tâche : temps maximum (`[taches_longues] duree_max_minutes`,
  **30 minutes** par défaut, ou la durée dite par Julien, de 1 minute à
  24 heures) et **30 étapes** au plus (une étape refaite après une
  vérification ratée compte). Le temps compte le travail réel, attentes de
  nouvel essai comprises, **pas** les heures où Jarvis est fermé. À
  l'épuisement, Jarvis s'arrête proprement et rapporte ce qui est fait et ce
  qui reste (« le budget de 30 minutes est épuisé »).

## Réglages

```toml
[taches_longues]
duree_max_minutes = 30     # 1 à 1440
max_etapes = 30            # 1 à 30
jetons_par_minute = 8000   # 0 = pas de limite (modèle local)
effort = "moyen"           # ou "bas"
```

## Pour le modèle local du mini-PC

Le travailleur ne connaît que deux fonctions : `appeler(messages, delai,
max_tokens) -> texte` et `classer(erreur) -> catégorie`. Aujourd'hui, la
boucle les fournit avec Groq (`fabriquer_appel_tache`,
`classer_erreur_cerveau`) ; un modèle local s'y branchera tel quel (une
branche dans `creer_cerveau`), avec `jetons_par_minute = 0`. Plan,
vérification, reprise, budget, annonces et panneau ne changent pas.

## Mode privé (lot PR)

- Une tâche longue lancée en mode privé vit **seulement en mémoire**
  (`taches_longues.Memoire`), avec son propre travailleur, et elle est
  suivie, annoncée et lue comme d'habitude. Elle **disparaît à la sortie du
  mode** (le travailleur privé est arrêté ; l'appel au cerveau en cours se
  termine sans rien écrire).
- **Rien n'est écrit dans `data/taches_longues.json` pendant le mode** : le
  travailleur normal est **suspendu** à l'entrée (avant toute écriture et
  tout nouvel appel ; le temps suspendu ne compte pas dans le budget) et
  relancé à la sortie. Les tâches normales finies sont annoncées après la
  sortie. (Différence avec le lot R1 : le travailleur des recherches
  normales, lui, continue pendant le mode.)
- Le panneau Tâches longues ne montre pas les tâches privées (il lit le
  fichier).

## Sécurité

- Le travailleur n'a **aucun outil d'écriture** : ni minuteur, ni note, ni
  clic dans la session Chrome de Julien, ni formulaire, ni achat. Ses appels
  au cerveau ne déclarent aucun outil ; ses consignes interdisent toute
  action. Il n'écrit que dans son fichier de tâches.
- **Règle §1 à chaque étape** : le texte des pages, les notes et **tout
  résultat qui en dérive** (contamination : une étape qui s'appuie sur une
  étape web devient externe à son tour) sont enveloppés dans
  `<untrusted_data source="etape-N">` dans les étapes suivantes, la
  vérification et la synthèse, avec les balises neutralisées (une page ne
  peut pas sortir de son enveloppe). Les consignes disent de ne jamais en
  suivre les instructions. Le plan est fait **avant** toute donnée externe et
  ne change plus.
- **Garde-fous C1** inchangés pour les étapes web : la recherche passe par
  l'adresse de la page de résultats, les clics sont vérifiés en code, pas de
  page de connexion ni de paiement, Chrome séparé et réduit.
- Le **résultat** est lu à Julien **par le code**, jamais redonné au modèle
  de conversation : l'historique n'en garde qu'un repère (« [Résultat de la
  tâche longue « … » lu à Julien ; non conservé dans l'historique.] »).
- **Proposition par le cerveau** : l'outil `proposer_tache_longue` ne lance
  rien ; seul un « oui » oral court, vérifié en code dans les 30 s (§3), le
  fait. C'est une écriture : il est refusé après une lecture externe dans le
  tour (hold_writes, §2 — il n'est dans aucune liste d'outils permis).
- Journal des tours (§7) : seulement les noms `lancer_tache_longue`,
  `suivre_tache_longue`, `lire_tache_longue`, `annuler_tache_longue` ; jamais
  l'objectif ni le résultat.

## Tests

`python -m unittest discover -s tests` — `tests/test_lt_taches_longues.py`
(54 tests) : déclenchement FR / EN et durées, proposition + « oui » ≤ 30 s,
plan et persistance, point de reprise à chaque étape, vérification refusée
puis blocage, reprise après redémarrage simulé, nouveaux essais après 429 /
délai / injoignable (attentes 5, 10, 20 s…), jamais d'abandon avant la fin du
budget, blocage dur, débit, budget de temps et d'étapes, annonce dans la
langue du tour, lecture du résultat, suivi lu dans le fichier, annulation,
panneau (deux thèmes), mode privé (mémoire seulement, travailleur normal
suspendu, rien d'écrit), §1 entre les étapes. Faux cerveau, fausse horloge :
aucun réseau, aucune attente réelle.

## Limites

- **Pas de notification quand Jarvis est fermé** : la tâche ne travaille que
  pendant que la boucle vocale tourne ; fermée, elle reprend au lancement
  suivant (et le budget de temps est préservé).
- **Une tâche à la fois.** Les suivantes attendent leur tour (3 au plus).
- **Pas d'actions** : une tâche longue cherche, lit, raisonne et rédige ;
  elle ne règle pas de minuteur, n'ouvre rien dans ton navigateur et ne
  garde pas de note. Pour des actions en plusieurs étapes (« ouvre YouTube
  puis… »), la boucle les enchaîne dans le tour, comme avant.
- **Le résultat n'est pas gardé en note** automatiquement (contrairement à
  une recherche R1, aucune proposition « garder dans tes notes ? » pour
  l'instant) ; il reste lisible dans le panneau.
- La **vérification** est faite par le même modèle : elle attrape les étapes
  vides, hors sujet ou incomplètes, pas toutes les erreurs de fond.
- L'estimation des jetons est prudente (≈ 3 caractères par jeton + le
  plafond de sortie) : avec 8 000 jetons par minute, compter environ une
  étape vérifiée par minute.
- Une **étape interrompue** par une fermeture est refaite en entier au
  lancement suivant (et compte une fois de plus dans les 30 étapes).
