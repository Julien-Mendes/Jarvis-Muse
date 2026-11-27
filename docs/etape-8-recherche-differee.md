# Lot R1 — Recherche différée

Julien pose une question qui demande une vraie recherche. Jarvis la lance en
arrière-plan, confirme à voix haute, puis rapporte la réponse plus tard.

## Ce qu'on dit

| Demande | Ce que fait Jarvis |
|---|---|
| « Fais-moi une recherche sur les vélos électriques » / « Research heat pumps » | Enregistre la tâche et répond « C'est lancé… » |
| « Cherche ça et reviens-moi » / « Look into that and get back to me » | Pareil, avec la phrase précédente de Julien comme question |
| Question qui demande plusieurs sources | Le modèle peut choisir l'outil `lancer_recherche` |
| « Où en est ma recherche ? » / « Is my research ready? » | Donne l'état : en file, en cours depuis N minutes, ou échec et raison |
| « Lis-moi le résultat (de ma recherche sur X) » / « Read me the result » | Lit la réponse puis cite les sources (titre et site) |
| « Préviens-moi quand c'est prêt » | Dit la limite : prévient seulement si l'app est ouverte, sinon au prochain lancement |

Les recherches terminées sont annoncées à voix haute au prochain moment calme
de la session. Au lancement suivant, Jarvis annonce celles qui sont prêtes
(ou en échec) et pas encore annoncées : « Ta recherche sur X est prête ».
L'application montre le panneau **Recherches** sous les minuteurs. Un clic
sur une recherche ouvre sa réponse et ses sources (titres et URL).

## Comment ça marche

- **File** (`scripts/recherche.py`) : `data/recherches.json` est écrit de
  façon atomique et sous verrou, comme `timers.json`. Chaque tâche a un
  statut (`en_cours`, `prete` ou `echec`). Une tâche `en_cours` sans
  `demarree_le` est en file d'attente. Il n'y a **qu'une recherche à la
  fois**. On garde au plus 5 tâches en cours ou en attente, et les 30
  dernières terminées.
- **Travailleur** : un fil de la boucle vocale. Il a son **propre** Chrome
  (`navigateur.py --interactif --fond`), dans un autre processus et un autre
  profil, réduit dans la barre des tâches. La session Chrome de la boucle
  n'est jamais touchée. Il a aussi son propre cerveau (repli Groq vers Haiku
  inclus).
- **Étapes** : la page de résultats DuckDuckGo est ouverte par son adresse
  (aucun formulaire). Le travailleur choisit au plus **3 pages** : http(s)
  seulement, une par site, sans PDF ni page de connexion ou de paiement. Il
  les ouvre par un clic gardé (garde-fous C1) et lit leur texte (4000
  caractères au plus, en mémoire seulement). La synthèse fait 3 à 6 phrases,
  et les sources sont gardées (titres et URL).
- **Délai maximum : 5 minutes** par tentative. Il est vérifié entre chaque
  étape, et chaque commande est bornée par le temps qui reste. Un chien de
  garde coupe aussi Chrome si une étape bloque. La tâche passe alors en
  échec avec la raison « délai ».
- **Redémarrage** : si l'app se ferme pendant une recherche, la tâche reste
  `en_cours`. Au lancement suivant, `reprendre_au_demarrage()` la remet en
  file. Après une seconde interruption, elle passe en échec (« interrompue »).
  Une tâche en file depuis plus de 7 jours passe aussi en échec.

## Sécurité

- Le texte des pages est une donnée externe (§1). Chaque page est enveloppée
  dans `<untrusted_data source="page-web" url="…">`, et toute balise
  `untrusted_data` présente dans la page est neutralisée. Ce texte ne va
  qu'à l'appel de synthèse, sans outils, dont la consigne interdit de suivre
  ses instructions.
- Ce texte brut n'est **jamais** écrit sur disque, journalisé, ni donné au
  modèle de conversation. La réponse est nettoyée (ni balises, ni URL, ni
  markdown) puis lue par le code. L'historique du modèle n'en garde qu'un
  repère. `OUTILS_LECTURE_EXTERNE` reste vide (garde F15).
- `lancer_recherche` est une écriture : elle est refusée après une lecture
  externe dans le même tour (hold_writes, échec fermé).
- La recherche ne remplit aucun formulaire, ne se connecte jamais et
  n'achète jamais : ce sont les garde-fous C1, inchangés.

## Limites

- **Pas de notification quand l'app est fermée** : Jarvis ne tourne pas en
  continu. La réponse est livrée au prochain lancement ou sur demande.
- **Pas de mode invisible** : DuckDuckGo oppose un défi anti-robot au Chrome
  headless (constaté le 26 nov. 2026). Le défi n'est pas contourné ; Chrome
  s'ouvre donc réduit dans la barre des tâches pendant une recherche.
- En mode `--texte` (un seul tour), la tâche est enregistrée mais faite au
  prochain lancement de la boucle.
- Consultation en ligne de commande : `python scripts/recherche.py lister`.
