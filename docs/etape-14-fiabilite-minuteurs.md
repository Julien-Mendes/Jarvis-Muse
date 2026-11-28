# Étape 14 — Fiabilité des minuteurs (lot F1)

Avant ce lot, un seul minuteur mal formé dans `data/timers.json` tuait le
surveillant de minuteurs : plus aucune alarme ne sonnait de la session, ni
aux suivantes, car il remourait à chaque démarrage. Un fichier corrompu
était remplacé par une liste vide sans aucune copie. Ce lot rend les
minuteurs robustes avant le lot M (minuteurs vocaux), qui s'appuie dessus.

Rien ne change à l'usage : les commandes de `docs/etape-3-minuteur.md`, les
tuiles de l'application et les minuteurs réglés à la voix fonctionnent
exactement comme avant. Ce qui change, c'est ce qui se passe quand quelque
chose tourne mal.

## Ce que Julien voit quand ça tourne mal

| Situation | Avant | Maintenant |
|---|---|---|
| Une entrée mal formée (échéance absente, date illisible, date sans fuseau) | Le surveillant meurt, aucune alarme ne sonne | L'entrée est **mise de côté** dans `data/timers.json.invalides` et **signalée** ; les autres minuteurs sonnent normalement |
| `timers.json` corrompu (JSON invalide, contenu inattendu) | Liste vide, fichier écrasé au prochain minuteur | Le fichier est **conservé** sous `data/timers.json.corrompu-AAAAMMJJ-HHMMSS`, **signalé**, puis la liste repart de zéro |
| `timers.json` momentanément illisible (verrou Windows, droits) | Liste vide, puis écrasement de tous les minuteurs | **Rien n'est écrit** ; « régler un minuteur » répond qu'il faut réessayer, le surveillant réessaie quelques secondes plus tard |
| L'annonce d'un minuteur plante | Le minuteur était déjà retiré : perdu | Le minuteur **reste enregistré**, l'erreur est signalée, nouvel essai 30 s plus tard (puis 1 min, 2 min… 5 min au plus) |
| Erreur imprévue pendant une vérification | Le surveillant meurt | Signalée une fois, le surveillant continue |
| Le surveillant meurt quand même | Plus d'alarme jusqu'à la fin de la session | Le lanceur **le relance** (journalisé) ; après **3 morts en moins de 10 minutes**, une fenêtre Windows prévient Julien et les relances s'arrêtent |

**Signalé** veut dire trois choses à la fois : une ligne dans
`logs/minuteurs.log`, une ligne sur la sortie d'erreur (donc dans
`logs/minuteur-surveillant.log` quand le lanceur a démarré le surveillant), et
une **fenêtre Windows** « Jarvis — minuteurs ». Le surveillant tourne sans
console : sans cette fenêtre, Julien ne saurait rien. Une même entrée mal
formée n'est signalée qu'une fois, puisqu'elle sort du fichier ; une même
erreur qui se répète n'est signalée qu'une fois tant qu'elle ne change pas.

## Comment ça marche

**Validation par entrée.** Avant de chercher les minuteurs échus, chaque
entrée passe par `minuteur.echeance()` : un objet, une échéance présente,
une date ISO lisible, **avec fuseau**. Toutes les dates écrites par Jarvis ont
un fuseau ; une date sans fuseau ne peut pas être comparée à l'heure actuelle,
c'est elle qui faisait planter la comparaison. Les entrées refusées sortent
de `timers.json` sous verrou et sont ajoutées à `timers.json.invalides`, avec
la raison et l'heure : **jamais supprimées**, Julien peut les relire ou les
recopier. `lister` les ignore sans les déplacer (lecture seule) ; le panneau
de l'application et le HUD les ignoraient déjà.

**Fichier corrompu.** `charger()` distingue trois cas :

- **absent** : liste vide, comme avant ;
- **illisible pour l'instant** (Windows refuse la lecture pendant le
  remplacement par un autre processus, droits) : cinq essais rapprochés,
  puis `FichierIndisponible`. L'appelant **n'écrit rien** : c'était le
  chemin par lequel un simple conflit de lecture pouvait effacer tous les
  minuteurs ;
- **corrompu** (JSON invalide, UTF-8 invalide, contenu qui n'est pas un
  objet, liste des minuteurs qui n'est pas une liste) : le fichier est
  renommé `timers.json.corrompu-…`, seulement s'il contient toujours ce qui
  a été lu (un autre processus a pu le réparer entre-temps). Si le renommage
  échoue, on n'écrit rien non plus.

Un `next_id` absent ou invalide est recalculé à partir des numéros présents.

**Annonce avant retrait.** Un minuteur échu est annoncé (carillon et voix),
puis retiré du fichier, sous verrou et après relecture : l'application a pu
modifier le fichier pendant l'annonce. Si l'annonce lève une exception, le
minuteur reste et un nouvel essai est prévu, à délai croissant pour ne pas
relancer le carillon toutes les 5 s. Ces délais sont gardés en mémoire : un
surveillant relancé réessaie tout de suite. Une voix indisponible (Piper
absent) n'est **pas** un échec, comme avant : le message est affiché et le
carillon joué, l'alerte est donnée.

Retirer après l'annonce voudrait dire que deux déclencheurs simultanés
annonceraient deux fois le même minuteur : le surveillant et un
`minuteur.py declencher` lancé à la main, par exemple. Un verrou d'annonce
(`data/annonce-minuteurs.lock`) l'empêche : un seul annonce à la fois,
l'autre passe son tour.

**Relance par le lanceur.** `lancer_app.py` ne bloque plus sur la fenêtre
Jarvis : il vérifie toutes les 2 s si elle est fermée et, en attendant, si le
surveillant vit encore (`RelanceSurveillant`). Chaque relance est écrite dans
`logs/lancer-app.log` (« arrêté avec le code 1 — relance (1/3) »). Une
sortie avec le **code 0** n'est pas un échec : c'est un surveillant qui a
trouvé le verrou déjà pris, par exemple par la session complète
(`lancer_session.ps1`). Il n'est pas relancé, sinon il tournerait en boucle.
La fenêtre d'abandon s'ouvre dans un fil : le lanceur continue de surveiller
la fenêtre Jarvis et arrête bien toute la session à sa fermeture.

**Durée infinie.** `config_jarvis.duree_en_minutes` refuse les valeurs non
finies : `inf`, `infj`, `Infinity` ou `nan`, écrits en texte ou en nombre TOML,
donnent la valeur par défaut. Un `[minuteur] duree_max` ou un budget de tâche
longue infini ne passe plus.

## Réglages

Aucun nouveau réglage. Les seuils sont des constantes :
`DELAI_NOUVEL_ESSAI_S` (30 s) et `DELAI_NOUVEL_ESSAI_MAX_S` (300 s) dans
`minuteur.py` ; `MAX_ECHECS_RAPPROCHES` (3), `FENETRE_ECHECS_S` (600 s) et
`INTERVALLE_SURVEILLANCE_S` (2 s) dans `lancer_app.py`.

## Que faire quand une fenêtre « Jarvis — minuteurs » apparaît

- **« … mal formé(s) écarté(s) »** : ouvrir `data/timers.json.invalides`.
  Chaque entrée garde le minuteur d'origine et la raison. Pour le récupérer,
  le recréer simplement (« mets un minuteur de… »). Le fichier peut ensuite
  être supprimé.
- **« Le fichier des minuteurs était illisible »** : la copie
  `data/timers.json.corrompu-…` contient l'ancien fichier, octet pour octet.
  Les minuteurs encore utiles se recréent ; la copie peut ensuite être
  supprimée.
- **« L'annonce du minuteur … a échoué »** : le message de la fenêtre
  contient le texte de l'alarme, elle n'est donc pas perdue. Le détail est
  dans `logs/minuteurs.log`. Le minuteur sonnera au prochain essai réussi.
- **« Le surveillant de minuteurs s'est arrêté 3 fois de suite »** : les
  alarmes ne sonnent plus pour cette session. Lire
  `logs/minuteur-surveillant.log` (la cause est à la fin), puis relancer
  Jarvis.

## Sécurité

Rien ne change aux règles (`docs/regles-securite.md`) : tout reste local,
aucun appel réseau, aucune nouvelle donnée externe, §1 non concerné (les
minuteurs ne contiennent que les mots de Julien). Les copies
`timers.json.invalides` et `timers.json.corrompu-…` restent dans `data/`
(gitignoré), comme `timers.json`. La fenêtre Windows est ouverte par un
petit processus Python détaché qui n'affiche que le texte du signalement.

## Mesures

Sur ce poste, avec 20 minuteurs et aucun échu :

- un cycle de vérification du surveillant (`declencher_dus`) prend
  **1,9 ms** (médiane ; 3,2 ms au 95ᵉ centile), contre 0,5 ms avant. La
  différence vient du verrou d'annonce. Avec un cycle toutes les 5 s au
  plus, c'est négligeable ;
- le surveillant au repos occupe **21,8 Mo** de mémoire ;
- la vérification du lanceur, un `poll()` toutes les 2 s, ne coûte rien de
  mesurable.

## Tests

`python -m unittest discover -s tests` : `tests/test_f1_minuteurs.py`
(20 tests). Couverture :

- entrées mal formées (échéance absente, date illisible, date sans fuseau) :
  mises de côté avec leur raison, les autres sonnent, signalement unique ;
- surveillant qui ne meurt ni sur une entrée invalide ni sur une erreur
  imprévue ; `lister` tolérant ;
- fichier corrompu : copie octet pour octet, structure inattendue, nouveau
  minuteur après corruption qui garde la copie, fichier momentanément
  illisible jamais écrasé, `next_id` recalculé ;
- minuteur encore présent pendant son annonce, annonce qui plante (minuteur
  gardé), nouvel essai différé puis retrait ;
- relance du surveillant : relance journalisée, code 0 non relancé, 3 échecs
  rapprochés (avertissement unique, relances arrêtées), échecs espacés
  toujours relancés, démarrage impossible compté comme échec ;
- durée `inf` refusée, valeurs normales inchangées.

Chaque test a d'abord été lancé sur le code d'avant le lot, et chacun a
échoué pour la raison attendue : `KeyError 'due'`, aucune copie, fichier
écrasé, exception d'annonce qui remonte, `inf` accepté, classe de relance
absente. Les tests se font dans un dossier temporaire, avec signalement
simulé : ils n'ouvrent aucune fenêtre et ne touchent ni `data/` ni `logs/`.

## Limites

- **Au moins une fois, pas exactement une fois** : si le surveillant meurt
  entre l'annonce et le retrait, le minuteur sera annoncé une seconde fois
  au redémarrage. C'est préférable à une alarme perdue.
- **Délais de nouvel essai en mémoire** : un surveillant relancé réessaie
  aussitôt une annonce qui venait d'échouer.
- **Sans le lanceur** (surveillant lancé à la main dans une console),
  personne ne le relance ; les signalements, eux, fonctionnent.
- Les signalements peuvent contenir l'étiquette d'un minuteur, donc les mots
  de Julien, dans `logs/minuteurs.log`, comme le faisait déjà
  `logs/minuteur-surveillant.log`.
- Le verrou de fichier (`verrou_fichier`) continue sans verrou après 5 s
  d'attente, pour ne jamais figer Jarvis. Inchangé dans ce lot.
