# Lot L1 — Langue détectée à chaque tour

Avant L1, la langue était verrouillée sur `[general] langue` (anglais par
défaut) : Whisper était forcé sur cette langue et Jarvis répondait toujours
en anglais. Désormais, **chaque tour a sa langue** (français ou anglais) et
tout le reste suit.

## Ce qui change pour Julien

| Julien dit (config en anglais) | Jarvis |
|---|---|
| « Mets un minuteur de cinq minutes » | confirme en français, voix UPMC |
| « What time is it? » | répond en anglais, voix Alan |
| « Note que le code du portail est 4521 » | note gardée, confirmation en français |
| « OK » (incertain) | langue de la config (repli) |

L'interface (titres des panneaux Minuteurs, Recherches, Connaissances,
bouton, astuce, pastille d'état…) bascule dans la langue du tour dès qu'elle
est détectée, avec les deux thèmes (`or_et_nuit`, `centre_de_commande`). La
fenêtre Historique reste en français, comme avant.

## Réglage

```toml
[general]
langue = "en"        # langue de repli (et des annonces de minuteur)
langue_auto = true   # false = une seule langue, comportement d'avant L1
```

`python scripts\boucle_voix.py --texte "…" --langue fr` force la langue
(pas de détection).

## Comment ça marche

1. **Whisper n'est plus forcé.** Groq renvoie la langue détectée
   (`verbose_json`) ; faster-whisper renvoie la langue et sa probabilité
   (seuil 0,6). Si Whisper entend une autre langue que fr / en, l'audio est
   retranscrit en forçant la langue de la config : aucune phrase en
   néerlandais n'arrive au cerveau.
2. **Sinon, détection sur le texte** (`scripts/langue_tour.py`) : mots-outils
   propres à chaque langue + accents français. Les mots ambigus sont exclus
   des deux listes (« a » — le piège déjà connu des mots-nombres —, « on »,
   « me », « minutes », « note », « ok »…). Sûre si une seule langue a des
   indices ou si l'une en a au moins deux fois plus.
3. **Incertain → langue de la config.**

Un tour tapé dans l'application passe directement par l'étape 2.

La boucle fait une copie de la config pour le tour (`config_du_tour`) :
prompt système, descriptions d'outils, textes prononcés, confirmations de
minuteur, recherches (lancées dans la langue du tour) et notes la lisent. La
langue du tour est écrite dans le champ `langue` de `data/hud-state.json`
(états réflexion, réponse, puis repos) et dans le journal des tours
(`logs/tours-*.jsonl`, champ `langue` — jamais le contenu).

Les déclencheurs rapides (minuteur, écran, navigateur, R1, KB) reconnaissent
déjà le français et l'anglais quelle que soit la config : ils sont inchangés.

## Voix et mémoire

Mesure du 27 nov. 2026 (working set du processus, Python 3.14, piper-tts
1.8) :

| Voix en mémoire | Working set |
|---|---|
| aucune | ~17 Mo |
| Alan | ~183 Mo |
| Alan + UPMC | ~316 à 333 Mo — **au-delà du budget de 200 Mo** |
| une seule, cache de la dernière (alternance fr/en ×4) | ~196 Mo, stable |

D'où le choix : **une voix chargée à la demande, cache de la dernière
utilisée** (`VoixResidente(max_voix=1)`). Changer de langue décharge l'autre
voix et coûte ~1 s (chargement + première synthèse) ; la boucle préchauffe la
nouvelle voix dès que la langue du tour est connue, pendant que le cerveau
réfléchit, ce qui masque l'essentiel de ce délai. Deux tours de suite dans
la même langue : aucun rechargement.

## Annonces de minuteur (décision Q7)

Les annonces du surveillant (`minuteur.py surveiller`) suivent toujours la
langue de la config, **sauf si un tour est en cours dans l'autre langue** :
elles suivent alors la langue du tour. « En cours » = état réflexion ou
réponse dans `data/hud-state.json` (moins de 5 minutes), ou fin de tour il y
a moins de 30 secondes. Fichier absent, illisible ou périmé : la config.

Les annonces de recherches terminées (R1), faites au repos, restent dans la
langue de la config, par cohérence avec cette règle.

## Limites

- Tests sans réseau : la réponse `verbose_json` de Groq (champ `language`)
  est simulée ; à confirmer au premier tour vocal réel.
- Une phrase très courte ou mélangée (« OK », « Google », « merci, thanks »)
  ne donne pas d'indice : repli sur la config, même si le tour d'avant était
  dans l'autre langue.
- Le premier changement de langue de la session coûte ~1 s de voix.

## Tests

`tests/test_l1_langue.py` (45 tests) : détection FR / EN par tour,
alternance, cas incertains avec repli config, Whisper (langue, probabilité,
autre langue), transcripteurs sans forçage, langue du prompt et des outils,
déclencheurs KB et minuteur dans les deux langues, voix selon la langue et
cache d'une voix, annonces de minuteur, interface par tour (deux thèmes).
