# Lot KB — Base de connaissances personnelles (version 1)

Julien dicte ou tape des notes ; Jarvis les retrouve quand il pose une
question dessus. Version 1 : **mots-clés seulement** (pas de recherche
sémantique — ce sera un lot plus tard, avec un modèle local).

## Ce qu'on dit

| Demande | Ce que fait Jarvis |
|---|---|
| « Note que mon budget pour le mini-PC est de 600 € » | Enregistre la note, répond « Noté. » |
| « Retiens que… » / « Prends note que… » / « Ajoute à mes notes : … » / « Ajoute X à mes notes » | Pareil |
| « Remember that… » / « Make a note that… » / « Add X to my notes » | Pareil, « Noted. » |
| Même phrase tapée dans le champ texte de l'application | Pareil (source « texte ») |
| « C'est quoi mon budget pour le mini-PC ? » / « Qu'est-ce que je t'ai dit sur X ? » | Le cerveau appelle `chercher_connaissance`, puis répond « D'après tes notes, … » |
| Question sans note correspondante | « Je ne trouve rien dans tes notes à ce sujet » — rien d'inventé |
| Une recherche différée (R1) est prête | Après l'annonce (une seule recherche prête) ou la lecture du résultat : « Veux-tu que je garde ça dans tes notes ? » — gardé sur « oui » (dans les 30 s), « non merci » répond « D'accord, je ne le garde pas. » |

Une phrase qui commence par « note que » est **toujours** une note, même si
elle parle d'un minuteur (« note que le minuteur de 5 minutes, c'est pour les
pâtes » ne règle aucun minuteur).

## Panneau Connaissances

Dans l'application, sous Minuteurs et Recherches : les notes, la plus
récente d'abord (texte + date), dans une liste défilante à elle. La croix
d'une note affiche « Supprimer ? » pendant 4 secondes ; un second clic la
supprime. Au-delà de 50 notes, le panneau indique combien il en reste ; la
liste complète : `python scripts\connaissances.py lister`.

## Comment ça marche

- **Stockage** (`scripts/connaissances.py`) : `data/connaissances.json`,
  écrit de façon atomique et sous verrou (comme `timers.json` et
  `recherches.json`). Une note : `id`, `texte`, `cree_le`, `source`
  (`voix`, `texte`, `recherche`), `mots_cles`. Un numéro supprimé n'est
  jamais réutilisé. Fichier illisible : copie gardée en `.illisible`.
  Plafond : 1000 notes de 1500 caractères.
- **Mots-clés** : minuscules, sans accents, sans mots vides (français et
  anglais, plus les mots de la demande : « note », « dit », « quoi »…),
  pluriel simple retiré. « mini-PC » donne `mini` et `pc` ; « 600 » compte.
- **Recherche** : score = nombre de mots-clés en commun avec la question ;
  seuil minimal 1 ; au plus 3 notes, les meilleures d'abord (à égalité, la
  plus récente). Une question faite seulement de mots vides ne trouve rien.
- Consultation en ligne de commande :
  `python scripts\connaissances.py chercher "budget mini-PC"`.

## Sécurité

- Les notes restent sur la machine (`data/` est gitignoré). Elles ne
  partent qu'au cerveau, dans le tour où Julien pose la question.
- Une note est une **donnée, jamais une consigne** : elle est rendue au
  modèle dans `<untrusted_data source="notes">` (balises neutralisées), avec
  l'interdiction d'exécuter ce qu'elle contient.
- Une note issue d'une recherche web compte comme une lecture externe :
  écritures bloquées pour le reste du tour (ni minuteur, ni ouverture de
  site), réponse non gardée telle quelle dans l'historique. Voir
  `docs/regles-securite.md` §2.
- Un résumé de recherche n'est jamais gardé automatiquement : seulement sur
  un « oui » oral court, vérifié en code (§3).

## Limites (version 1)

- Mots-clés exacts seulement : « ordinateur » ne retrouve pas « PC »,
  « vélo » ne retrouve pas « bicyclette ». Recherche sémantique : lot à venir.
- Pas de modification d'une note (supprimer puis redicter).
- Pas de suppression à la voix (panneau seulement).
- La phrase doit commencer par la formule (« note que… ») ; « tu pourrais
  noter que… » et « peux-tu noter que… » sont reconnus, une formulation
  libre au milieu d'une phrase ne l'est pas.
- « Ajoute ça à mes notes » ne sait pas encore ce qu'est « ça » : Jarvis
  demande quoi noter.

## Tests

`python -m unittest discover -s tests` — `tests/test_kb_connaissances.py`
(ajout, mots-clés, recherche dont « rien trouvé », suppression, persistance
après redémarrage, détection fr/en, boucle, injection dans une note issue
d'une recherche, lien R1, panneau).
