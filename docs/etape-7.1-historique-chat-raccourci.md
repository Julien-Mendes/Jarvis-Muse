# Étape 7.1 — Historique, chat texte, raccourci et journal des tours

Trois ajouts approuvés par Julien le 21 nov. 2026 (tout sauf le mot de
réveil), inspirés des deux Jarvis Claude de référence :
- **Historique + chat texte** : le journal de conversation devient un
  fichier par jour, lisible dans une fenêtre Historique séparée (avec
  recherche) ; on peut aussi écrire à Jarvis dans l'application au
  lieu de parler.
- **Raccourci « Jarvis »** : icône dans le menu Démarrer, épinglable à
  la barre des tâches, qui lance la session sans fenêtre console
  (modèle : `--install-shortcut` du dépôt B).
- **Journal des tours** : durées, jetons, coût estimé et outils utilisés,
  un fichier par jour, sans jamais le contenu des conversations
  (modèle : `turnlog.py` du dépôt B).

## A. Historique par jour + fenêtre Historique

### Journal par jour

La boucle vocale (`scripts/boucle_voix.py`, fonction
`journaliser_echange()`) écrit désormais chaque tour dans
`data/conversations/AAAA-MM-JJ.jsonl` — une ligne JSON par message,
`{"role": "user"|"jarvis", "texte": ..., "heure": "ISO"}`, ajoutée en
fin de fichier, sans plafond. L'ancien journal unique
`data/conversation.jsonl` (étape 7, plafonné à 200 lignes) n'est plus
écrit : l'application le lit seulement en repli, s'il existe et que
le journal du jour n'existe pas encore (compatibilité avec la session
en cours lors de la mise à jour).

Le journal est local uniquement (`data/`, gitignoré) : c'est
l'historique affiché par l'application sur la machine de Julien, comme
l'historique d'une application de messagerie — jamais envoyé nulle
part, jamais lu par personne d'autre que Julien sur son propre écran
(voir la note §7 ci-dessous).

### Fenêtre Historique

Menu **Fichier → Historique…** dans l'application : une fenêtre
séparée (pas un panneau de l'écran principal, comme demandé par
Julien) avec :
- **à gauche**, la liste des jours (du plus récent au plus ancien),
  avec le nombre de messages — l'ancien journal apparaît en dernier
  sous « Ancien journal » ;
- **en haut**, un champ de recherche qui filtre les messages du jour
  affiché (texte uniquement, insensible à la casse) ;
- **à droite**, la conversation du jour, en lecture seule (mêmes
  bulles que l'écran principal).

Si la fenêtre est déjà ouverte, le menu la ramène simplement au
premier plan. Fermer la fenêtre Historique ne ferme pas
l'application.

## B. Chat texte dans l'application

Sous le bouton micro : un champ **« Écrire à Jarvis… »** + bouton
**« Envoyer »** (la touche Entrée envoie aussi). Le texte tapé est
écrit dans `data/texte-demande.json` (`{"texte": ..., "horodatage":
"ISO"}`), que la boucle vocale sonde toutes les 0,2 s — exactement
comme le fichier push-to-talk du HUD. La boucle le traite comme un
tour vocal : la réponse apparaît dans la conversation **et** est lue à
voix haute (même chemin que F9, minuteur et outils compris).

Règles du mécanisme :
- Une demande n'est traitée qu'une fois : la boucle supprime le
  fichier dès sa lecture.
- Une demande périmée (plus de 5 minutes, ex. boucle arrêtée
  entre-temps) est ignorée.
- **La boucle vocale doit tourner** pour que le message reçoive une
  réponse — sinon rien ne se passe (la demande expire). L'état
  « Boucle arrêtée » dans l'application l'indique.

C'est le pendant du mode `--text` du dépôt B (taper au lieu de
parler), intégré à la fenêtre au lieu d'une ligne de commande.

## C. Raccourci « Jarvis » (menu Démarrer / barre des tâches)

### Installation

Dans le dossier du dépôt cloné, en PowerShell :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\installer_raccourci.ps1
```

Le script crée `Jarvis.lnk` dans le menu Démarrer (dossier
`Programmes` de l'utilisateur). Il lance `scripts/lancer_app.py`
avec `pythonw.exe` (sans fenêtre console) :
1. le surveillant de minuteurs en arrière-plan ;
2. la boucle vocale en arrière-plan ;
3. « Jarvis prêt. » à voix haute ;
4. l'application au premier plan.

### Épingler à la barre des tâches

Touche Windows, taper « Jarvis », clic droit sur « Jarvis » →
« Épingler à la barre des tâches » (Windows ne laisse pas un
programme s'épingler tout seul — même limite que dans le dépôt B).

### Arrêter proprement

**Fermer la fenêtre de l'application arrête toute la session** :
le lanceur arrête alors la boucle vocale et le surveillant de
minuteurs (c'est le comportement voulu, comme dans le dépôt B où
fermer le HUD quitte Jarvis). Si un processus reste coincé malgré
tout : Gestionnaire des tâches → terminer les processus
`pythonw.exe` du dossier Jarvis-Muse.

### Retirer

```powershell
powershell -ExecutionPolicy Bypass -File scripts\installer_raccourci.ps1 -Desinstaller
```

### Vérifier sans lancer

```powershell
python scripts\lancer_app.py --verifier
```

Vérifie python/pythonw, les scripts, CustomTkinter et le dossier
`logs/` en écriture. Les sorties des processus vont dans `logs/`
(gitignoré) : `lancer-app.log`, `boucle.log`, `app.log`,
`minuteur-surveillant.log` — c'est là qu'il faut regarder si la
session ne démarre pas.

Différence avec le raccourci de démarrage automatique
(`scripts/installer_demarrage.ps1`, étape 6) : celui-ci ne lance rien
au login — c'est un raccourci à cliquer quand Julien veut Jarvis. Et
différence avec la session complète (`scripts/lancer_session.ps1`) :
le lanceur sans console ne lit pas les résumés Carson (`a-dire/`) et
n'annonce pas les minuteurs du jour — il se concentre sur
application + boucle. Pour la session complète, utiliser
`lancer_session.ps1`.

## D. Journal des tours

La boucle vocale écrit chaque tour dans
`logs/tours-AAAA-MM-JJ.jsonl` (fonction `journaliser_tour()`, modèle
`turnlog.py` du dépôt B) — une ligne JSON par tour :

| Champ | Contenu |
|---|---|
| `horodatage`, `mode` | quand, et comment (« voix » ou « texte ») |
| `fournisseur`, `modele`, `stt`, `voix` | cerveau, STT et voix utilisés |
| `enregistrement_s` | durée de l'enregistrement (0 pour un tour texte) |
| `transcription_s` | durée de la transcription (0 pour un tour texte) |
| `premier_token_s` | durée de l'appel LLM — le client Groq ne diffuse pas les jetons en continu, donc le premier jeton arrive avec la réponse complète : cette durée égale la durée de l'appel LLM |
| `premier_audio_s` | de la fin de l'enregistrement (ou de la réception du texte) au lancement de la lecture vocale — ce que Julien attend vraiment |
| `total_s` | de la fin de l'enregistrement à la fin de la lecture vocale |
| `entree_tokens`, `sortie_tokens` | jetons du tour (cumulés sur les rondes d'outils) |
| `cout_estime_usd`, `cout_estime_gbp` | coût estimé (voir ci-dessous) |
| `reprises` | tentatives (0 pour l'instant — réservé) |
| `outils` | noms des outils utilisés (jamais leurs arguments) |
| `erreur` | message d'erreur court, le cas échéant |

**JAMAIS le contenu des conversations, jamais l'audio, jamais les
transcriptions** (règle §7). Le journal des tours est un journal de
télémétrie ; le journal de conversation (`data/conversations/`) est
un historique local — les deux sont séparés, comme dans le dépôt B.

### Coût et limites Groq

- **Groq est gratuit : le coût estimé est 0 $** tant que le
  fournisseur est `groq`. Pour Anthropic (Haiku, payant à l'usage),
  le coût est estimé avec le tarif Haiku (1,00 $ / 1 M de jetons en
  entrée, 5,00 $ / 1 M en sortie — estimation, à vérifier sur
  console.anthropic.com) ; le coût en livres utilise un taux
  approximatif (0,79).
- **Limite Groq : 8 000 jetons par minute.** Avec les outils déclarés,
  chaque question utilise environ 1 600 jetons (3 000 si elle va
  chercher des données) : quelques questions rapides d'affilée peuvent
  faire attendre Jarvis — il le dit alors (« je suis limité en ce
  moment ») et il faut réessayer après quelques secondes. Le journal
  des tours permet de voir ces ralentissements (durées qui grimpent,
  `erreur` de limitation).

## Sécurité

- **Aucun serveur réseau** : comme avant, tout passe par des fichiers
  locaux (`data/`, `logs/`), jamais par un port.
- **Journal des tours sans contenu** (règle §7) : durées, jetons,
  coûts, noms d'outils — jamais ce qui a été dit. Voir la note §7
  ci-dessous pour la distinction avec le journal de conversation.
- **Fichiers locaux gitignorés** : `data/` (conversations, demande
  texte, état) et `logs/` (tours, sorties du lanceur) ne quittent
  jamais la machine.
- **Demande texte** : un message tapé est une instruction de Julien
  lui-même, comme une phrase parlée — le même traitement (hold_writes,
  confirmations) s'applique.

**Note sur le journal de conversation (règles de sécurité §7).** La
règle §7 dit que les journaux ne contiennent que des métadonnées,
jamais le contenu des conversations : elle vise les journaux de
télémétrie et de facturation (durées, jetons, coûts) — c'est
exactement ce que fait le nouveau journal des tours. Le journal de
conversation (`data/conversations/`) n'en est pas un : c'est
l'historique affiché par l'application sur la machine de Julien,
comme l'historique d'une application de messagerie — local
uniquement, gitignoré, jamais envoyé nulle part, jamais lu par
personne d'autre que Julien sur son propre écran. Si ce journal doit
un jour quitter la machine (ce n'est pas prévu), il faudra d'abord
en reparler avec Julien.

## Prérequis

- Étapes 2 à 7 installées (voix, minuteur, boucle, yeux et mains,
  HUD, application). Rien de nouveau à installer : le lanceur et
  l'historique utilisent les dépendances déjà présentes (CustomTkinter
  pour l'application, le reste en bibliothèque standard).

## Dépannage

- **La fenêtre Historique est vide** : le journal du jour est créé
  par la boucle au premier tour — parlez (ou écrivez) une fois à
  Jarvis, puis rouvrez la fenêtre. Les jours plus anciens n'apparaissent
  que s'ils ont un fichier dans `data/conversations/`.
- **La recherche ne trouve rien** : elle filtre les messages du jour
  affiché seulement, sur le texte (insensible à la casse). Changez de
  jour dans la liste de gauche pour chercher ailleurs.
- **Le message tapé n'obtient pas de réponse** : vérifiez que la
  boucle vocale tourne (état autre que « Boucle arrêtée » dans
  l'application). Une demande expire après 5 minutes si la boucle
  était arrêtée — retapez le message après avoir relancé la boucle.
- **Le raccourci ne démarre rien** : vérifiez avec
  `python scripts\lancer_app.py --verifier`, puis regardez
  `logs/lancer-app.log` et `logs/app.log`. Cause fréquente :
  CustomTkinter absent (`pip install -r
  scripts/requirements-etape7.txt`).
- **La fenêtre se ferme mais la boucle continue** : normalement le
  lanceur arrête la boucle à la fermeture. Si un processus reste
  coincé : Gestionnaire des tâches → terminer les processus
  `pythonw.exe` du dossier Jarvis-Muse.
- **Le journal des tours est vide** : il est écrit à la fin de chaque
  tour traité par la boucle (voix ou texte). Les tours interrompus
  avant la transcription (trop courts, micro coupé) ne sont pas
  journalisés. Vérifiez `logs/tours-AAAA-MM-JJ.jsonl`.

## Ce qui reste à faire

- Tester sur le laptop de Julien : fenêtre Historique (jours,
  recherche, relecture), chat texte (envoi, réponse lue à voix
  haute, expiration après 5 min), raccourci (installation, épinglage,
  fermeture propre), journal des tours (une ligne par tour, coût 0 $
  sur Groq).
- Mot de réveil « Hey Jarvis » : **refusé par Julien pour ce lot** —
  ne pas construire.
- Double-clap : plus tard (décision 21 nov. 2026).
- Effet « voix dans les murs » : plus tard (décision 21 nov. 2026).
- Mise à jour de `scripts/lancer_session.ps1` pour démarrer
  l'application à la place du HUD : après validation de
  l'application (voir docs/etape-7-application.md).
- Notes quotidiennes (bloc 23) et lecture de page complète en boucle
  vocale (bloc 16) : décisions encore ouvertes, non construites dans
  cette étape.
