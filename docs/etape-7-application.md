# Étape 7 — Application Jarvis

L'application est une vraie fenêtre desktop moderne (CustomTkinter,
thème sombre) qui remplace à terme le HUD Tkinter (étape 6 — jugé trop
« bancal » par Julien le 21 nov. 2026). L'ambiance reprend celle du
Jarvis de référence (dépôt Julian-Ivanov, frontend web) : fond très
sombre (`#0a0a0f`), orbe lumineux qui pulse selon l'état, conversation
écrite en dessous.

## Ce que montre l'application (état local seulement)

- **En-tête** : orbe d'état + texte + horloge locale (America/Toronto).
  L'orbe pulse comme dans le frontend de référence — bleu quand Jarvis
  écoute, doré quand il réfléchit, vert quand il parle ; gris-bleu au
  repos, rouge discret en cas d'erreur. Si la boucle vocale n'a jamais
  tourné, l'état est « Boucle arrêtée ».
- **Zone de conversation** : bulles utilisateur (à droite, bleu sombre)
  et Jarvis (à gauche, gris sombre), avec horodatage. Elle est
  alimentée par le journal du jour `data/conversations/AAAA-MM-JJ.jsonl`,
  écrit par la boucle vocale à chaque tour (voir « Comment ça
  communique » ; depuis l'étape 7.1, l'ancien journal unique
  `data/conversation.jsonl` n'est plus écrit et n'est lu qu'en repli).
- **Panneau minuteurs** : liste lue dans `data/timers.json` (lecture
  seule), avec comptes à rebours (« pâtes : dans 12 min »).
- **Bouton micro** : maintenir enfoncé pour parler (= équivalent F9) ;
  relâcher pour envoyer. Un appui pendant une réponse l'interrompt,
  comme F9.
- **Bouton « Interrompre »** : coupe la réponse en cours.
- **Champ de saisie + bouton « Envoyer »** (étape 7.1) : écrire à
  Jarvis au lieu de parler — le texte est traité comme un tour vocal,
  réponse affichée et lue à voix haute.
- **Menu Fichier** : Historique (fenêtre séparée, étape 7.1), Ouvrir
  le guide, Quitter.
- La fenêtre est redimensionnable ; sa position et sa taille sont
  mémorisées dans `data/app.json` (gitignoré) quand elle est déplacée
  ou redimensionnée.

L'application ne montre **pas** de météo, calendrier, Gmail, tâches ou
repas : tout cela est déjà couvert par Carson (bloc 6, doublons). Elle
ne montre jamais de contenu sensible : pas de capture d'écran, pas de
texte de page, pas de courriel — seulement l'état, l'heure, les
minuteurs et la conversation avec Jarvis lui-même.

## Comment ça communique (sans port réseau)

La boucle vocale (`scripts/boucle_voix.py`) écrit :
- son état dans `data/hud-state.json` à chaque changement de phase
  (fonction `ecrire_etat_hud()`, jamais bloquante) — le même fichier
  que le HUD ;
- chaque tour dans `data/conversations/AAAA-MM-JJ.jsonl` (fonction
  `journaliser_echange()`, jamais bloquante, depuis l'étape 7.1) : une
  ligne JSON par message, `{"role": "user"|"jarvis", "texte": ...,
  "heure": "ISO"}`, ajoutée en fin de fichier, sans plafond. Avant
  l'étape 7.1, c'était le journal unique `data/conversation.jsonl`
  (plafonné à 200 lignes) — il n'est plus écrit, l'application le lit
  seulement en repli.
- chaque tour (télémétrie seulement, sans contenu) dans
  `logs/tours-AAAA-MM-JJ.jsonl` (fonction `journaliser_tour()`, étape
  7.1) — voir `docs/etape-7.1-historique-chat-raccourci.md`.

L'application relit ces fichiers (et `data/timers.json`) toutes les
500 ms. Le bouton micro écrit `data/hud-ptt.json`, sondé par la boucle
toutes les 0,2 s — exactement comme le clic maintenu sur l'anneau du
HUD. Le champ de saisie écrit `data/texte-demande.json`, sondé par la
boucle au même rythme — voir l'étape 7.1. Tous ces fichiers sont dans
`data/` (gitignoré, jamais poussés) ; le journal des tours est dans
`logs/` (gitignoré aussi).

**Note sur le journal de conversation (règles de sécurité §7).** La
règle §7 dit que les journaux ne contiennent que des métadonnées,
jamais le contenu des conversations : elle vise les journaux de
télémétrie et de facturation (durées, jetons, coûts) — c'est
exactement ce que fait le journal des tours (`logs/tours-AAAA-MM-JJ.jsonl`,
étape 7.1). Le journal `data/conversations/AAAA-MM-JJ.jsonl` n'en est
pas un : c'est l'historique affiché par l'application sur la machine
de Julien, comme l'historique d'une application de messagerie — local
uniquement, gitignoré, jamais envoyé nulle part, jamais lu par
personne d'autre que Julien sur son propre écran. Si ce journal doit
un jour quitter la machine (ce n'est pas prévu), il faudra d'abord
en reparler avec Julien.

## Prérequis

- Python 3.10+ et Windows (laptop de Julien pour tester).
- Étapes 2 à 6 installées : voix Piper, minuteur, boucle vocale F9,
  yeux et mains, HUD. L'application fonctionne aussi avec les étapes
  1–4 seules (elle affiche alors « Boucle arrêtée » et les minuteurs
  si le fichier existe).
- CustomTkinter 6.0.0 (vérifié compatible Python 3.14 — voir
  `scripts/requirements-etape7.txt`).

## Installation

Dans le dossier du dépôt cloné, en PowerShell :

```powershell
# 1. Créer et activer un environnement virtuel (si ce n'est pas déjà fait)
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Installer CustomTkinter
pip install -r scripts\requirements-etape7.txt

# 3. Vérifier l'installation
python scripts\app.py --verifier
```

Si PowerShell bloque l'activation :
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (une seule fois),
puis recommencer l'activation.

## Utilisation

```powershell
# Lancer l'application
python scripts\app.py
```

L'application ne fait qu'afficher et écouter : **la boucle vocale doit
tourner à côté** (dans une autre fenêtre PowerShell), sinon l'état
reste « Boucle arrêtée » et le bouton micro ne fait rien :

```powershell
# Dans une deuxième fenêtre PowerShell :
python scripts\boucle_voix.py
```

Ensuite : maintenir F9 (ou le bouton micro) pour parler, relâcher pour
envoyer ; la conversation apparaît dans la fenêtre, bulle par bulle.
Créer un minuteur (« set a timer for one minute ») → il apparaît dans
le panneau minuteurs avec son compte à rebours.

Pour l'instant, la session complète (`scripts\lancer_session.ps1`)
lance encore le HUD, pas l'application : lancez l'application à la
main à côté de la session. Quand l'application sera validée, le
lanceur sera mis à jour pour démarrer l'application à la place du HUD
(voir « Ce qui reste à faire »).

## Personnalisation

Dans `config.toml` (copier `config/config.example.toml` vers `config.toml`
si ce n'est pas déjà fait) :

```toml
[app]
active = true                  # false = l'application ne démarre pas
largeur = 900                  # largeur en pixels (640 à 1600)
hauteur = 650                  # hauteur en pixels (480 à 1200)
toujours_au_premier_plan = false
intervalle_ms = 500            # relecture de l'état, en millisecondes
```

La position et la taille exactes sont mémorisée dans `data/app.json`
(gitignoré) quand vous déplacez ou redimensionnez la fenêtre — elles
priment sur `largeur` / `hauteur` au démarrage suivant.

## Sécurité

- **Aucun serveur réseau** : l'application et la boucle communiquent
  par fichiers locaux uniquement. Si un serveur local devient
  nécessaire plus tard (mini-PC) : `127.0.0.1` seulement, jamais
  `0.0.0.0` sans authentification (faille du dépôt A).
- **Rien de sensible affiché** : l'application ne montre que l'état,
  l'heure, les minuteurs et la conversation avec Jarvis.
- **Les fichiers `data/` sont gitignorés** : état, conversation,
  position et minuteurs ne quittent jamais la machine.
- **Couleurs d'état** : l'application suit la palette du Jarvis de
  référence (bleu écoute, doré réflexion, vert parole), qui diffère
  volontairement de celle du HUD (vert écoute, bleu réponse). Les deux
  fenêtres peuvent tourner en même temps : elles lisent les mêmes
  fichiers.

## Dépannage

- **« CustomTkinter n'est pas installé »** : `pip install -r
  scripts\requirements-etape7.txt` (dans le venv activé).
- **L'application ne s'affiche pas** : vérifiez avec
  `python scripts\app.py --verifier`. Sur une machine sans écran
  (connexion distante sans bureau), elle ne peut pas s'afficher.
- **L'état reste « Boucle arrêtée »** : la boucle vocale n'a pas
  encore écrit `data/hud-state.json` — lancez-la
  (`python scripts\boucle_voix.py`), l'état apparaît au premier
  changement de phase.
- **La conversation reste vide** : le journal du jour
  `data/conversations/AAAA-MM-JJ.jsonl` est créé par la boucle au
  premier tour — parlez une fois à Jarvis (F9 ou bouton micro) ou
  écrivez-lui (champ de saisie, étape 7.1), puis vérifiez que le
  fichier existe. Les tours en mode `--texte` y apparaissent aussi.
  La fenêtre Historique (menu Fichier → Historique…) relit les jours
  précédents ; l'ancien journal unique `data/conversation.jsonl` n'est
  plus écrit (lu en repli seulement).
- **Le bouton micro ne démarre pas l'enregistrement** : vérifiez que
  la boucle vocale tourne (c'est elle qui lit `data/hud-ptt.json`).
  Un appui pendant une réponse l'interrompt au lieu d'enregistrer —
  c'est le comportement voulu (comme F9).
- **Le minuteur n'apparaît pas dans l'application** : vérifiez
  `python scripts\minuteur.py lister` — l'application lit le même
  fichier (`data/timers.json`).
- **Les bulles ne reviennent pas à la ligne en redimensionnant** :
  le retour à la ligne s'ajuste ~200 ms après le redimensionnement ;
  si une bulle reste trop large, redimensionnez une deuxième fois.
- **« Impossible d'ouvrir une fenêtre »** : l'application a besoin
  d'un bureau Windows ; en connexion distante sans écran, elle ne
  peut pas s'afficher (le HUD a la même limite).

## Ce qui reste à faire

- Tester sur le laptop de Julien : application seule (orbe, conversation,
  minuteurs, micro, interruption), puis avec la boucle vocale et le
  minuteur ; mesure RAM/CPU réelles (cibles : < 100 Mo, ~0 % en veille,
  comme le HUD).
- Décider avec Julien si l'application remplace le HUD : si oui, mettre
  à jour `scripts/lancer_session.ps1` (démarrer l'application au lieu
  du HUD) et `scripts/installer_demarrage.ps1` si besoin ; le HUD reste
  disponible en repli (`python scripts\hud.py`). Le raccourci
  « Jarvis » de l'étape 7.1 (`scripts/installer_raccourci.ps1`) lance
  déjà l'application seule (sans console).
- Améliorations possibles après validation : bouton pour vider
  l'historique affiché (sans toucher au journal), thème clair en option,
  raccourci clavier global pour ouvrir la fenêtre.
- Notes quotidiennes (bloc 23) et lecture de page complète en boucle
  vocale (bloc 16) : décisions encore ouvertes, non construites dans
  cette étape.
