# Étape 6 — HUD léger + lancement de session

Le HUD est un petit anneau d'état (Tkinter, bibliothèque standard — pas de
navigateur embarqué, pas de serveur réseau) et le lancement de session est
un script unique qui démarre tout : minuteurs, résumés Carson, HUD, boucle
vocale. Objectif : un poste prêt en une commande, sans le coût du HUD du
dépôt B (~760 Mo en veille, 42–54 % d'un cœur) — cibles : **< 100 Mo,
~0 % CPU en veille, démarrage < 1 s**.

## Ce que montre le HUD (état local seulement)

- **Anneau** : couleur selon l'état de la boucle vocale — gris-bleu
  (repos), vert (écoute, F9 enfoncé), ambre (réflexion, appel au cerveau),
  bleu (réponse lue à voix haute), rouge discret (erreur), clignotant
  discret (~5 s) quand un minuteur vient d'arriver à échéance.
- **Centre** : heure locale (America/Toronto) + compte à rebours du
  prochain minuteur (« 12 min », « 45 s », « 1 h 05 »).
- **Panneau déplié au survol** : dernière phrase entendue + 2 prochains
  minuteurs.
- **Maintenir le clic sur l'anneau = équivalent F9** : parler, relâcher
  pour envoyer ; un clic pendant une réponse l'interrompt (comme F9).
  Glisser déplace la fenêtre (position mémorisée).
- **Clic droit** : menu — Ouvrir le guide, Masquer (réduit à un point
  discret, clic dessus pour réafficher), Quitter.

Le HUD ne montre **pas** de météo, calendrier, Gmail, tâches ou repas :
tout cela est déjà couvert par Carson (bloc 6, doublons). Il ne montre
jamais de contenu sensible : pas de capture d'écran, pas de texte de page,
pas de courriel.

## Comment ça communique (sans port réseau)

La boucle vocale (`scripts/boucle_voix.py`) écrit son état dans
`data/hud-state.json` à chaque changement de phase (fonction
`ecrire_etat_hud()`, jamais bloquante). Le HUD relit ce petit fichier
toutes les 500 ms. Le clic maintenu du HUD est signalé par
`data/hud-ptt.json`, sondé par la boucle toutes les 0,2 s. Les minuteurs
sont lus directement dans `data/timers.json` (lecture seule). Tous ces
fichiers sont dans `data/` (gitignoré, jamais poussés).

## Prérequis

- Python 3.10+ et Windows (laptop de Julien pour tester).
- Étapes 2 à 5 installées : voix Piper, minuteur, boucle vocale F9, yeux
  et mains. Le HUD fonctionne aussi avec les étapes 1–4 seules (il
  affiche alors « En attente de F9… » et les minuteurs).
- Rien à installer : Tkinter fait partie de la bibliothèque standard.
  Si Tkinter est absent (rare sous Windows), le HUD bascule sur une
  icône de barre système (couleur = état, infobulle = prochain minuteur)
  — cela demande `pystray` : `pip install pystray`
  (voir `scripts/requirements-etape6.txt`).

## Installation

Dans le dossier du dépôt cloné, en PowerShell :

```powershell
# 1. Créer et activer un environnement virtuel (si ce n'est pas déjà fait)
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Vérifier l'installation (rien à installer pour l'étape 6)
python scripts\hud.py --verifier
```

Si PowerShell bloque l'activation :
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (une seule fois),
puis recommencer l'activation.

## Utilisation — le HUD seul

```powershell
# Lancer le HUD (fenêtre en bas à droite, toujours au premier plan)
python scripts\hud.py

# Lancer le HUD dans un coin précis ou une autre taille
python scripts\hud.py --position bas-gauche --taille 220
```

Le HUD suit ensuite la boucle vocale tout seul : F9 → l'anneau passe au
vert ; relâcher → ambre puis bleu pendant la réponse. Créer un minuteur
(« mets un minuteur de 20 minutes ») → le compte à rebours apparaît au
centre. Un clic maintenu sur l'anneau parle à la place de F9.

## Utilisation — lancer une session complète

```powershell
# Lancer tout d'un coup (recommandé) :
powershell -ExecutionPolicy Bypass -File scripts\lancer_session.ps1

# Sans le HUD, ou sans la boucle vocale (pour tester) :
powershell -ExecutionPolicy Bypass -File scripts\lancer_session.ps1 -SansHud
powershell -ExecutionPolicy Bypass -File scripts\lancer_session.ps1 -SansBoucle
```

La session fait, dans l'ordre :
1. **Vérifie** l'environnement (Python, venv, `.env`) — avertit sans
   planter si quelque chose manque.
2. **Démarre le surveillant de minuteurs** dans une fenêtre à part —
   c'est lui qui fait sonner les minuteurs et qui annonce ceux qui sont
   arrivés à échéance pendant que la machine était éteinte.
3. **Annonce les minuteurs et rappels du jour**, en une phrase, à voix
   haute (« Aujourd'hui : minuteur « pâtes » dans 20 minutes, rappel
   « colis » à 18 h 30. »). Rien à annoncer s'il n'y en a pas.
4. **Lit les résumés Carson du dossier `a-dire/`** (fichiers `.txt`,
   dans l'ordre alphabétique), s'il y en a. Rien s'il n'y en a pas :
   pas de météo ni de briefing reconstruit localement (doublons Carson).
5. **Lance le HUD** en arrière-plan.
6. **Range les fenêtres en quadrants** si `[quadrants]` est configuré
   (voir Personnalisation ci-dessous).
7. **Lance la boucle vocale** au premier plan et dit « Jarvis prêt ».

Ctrl+C dans la fenêtre de la boucle quitte la session. Le surveillant
de minuteurs et le HUD continuent de tourner dans leurs fenêtres —
fermez-les pour tout arrêter.

## Démarrage automatique au login (bloc 25, validé le 21 nov. 2026)

En deux temps : raccourci manuel d'abord (une semaine de test), puis
Planificateur de tâches.

### Étape 1 — Raccourci manuel (semaine de test)

```powershell
# Installer le raccourci dans le dossier Démarrage de Windows :
powershell -ExecutionPolicy Bypass -File scripts\installer_demarrage.ps1

# Retirer le raccourci (la session ne démarre plus au login) :
powershell -ExecutionPolicy Bypass -File scripts\installer_demarrage.ps1 -Desinstaller
```

Le raccourci lance `scripts\lancer_session.ps1` dans une fenêtre
PowerShell visible au login : la session démarre toute seule (minuteurs,
résumés, HUD, boucle vocale, « Jarvis prêt »). Ctrl+C dans cette fenêtre
quitte la session ; le surveillant de minuteurs et le HUD continuent de
tourner.

Vérifier : Win+R → `shell:startup` → le raccourci « Jarvis-Muse » est
présent. Tester en vous déconnectant puis reconnectant (ou en redémarrant).

Pendant la semaine de test, noter ce qui gêne : fenêtre au premier plan
au login, voix « Jarvis prêt » au démarrage, session lancée alors qu'on ne
la veut pas ce jour-là… C'est ce retour qui décidera du passage à l'étape 2
ou du retrait pur et simple.

**Alternative manuelle** (si le script est bloqué) : Win+R →
`shell:startup` → clic droit → Nouveau → Raccourci → emplacement :
`powershell.exe -ExecutionPolicy Bypass -File "C:\chemin\vers\Jarvis-Muse\scripts\lancer_session.ps1"`
→ nom « Jarvis-Muse ».

### Étape 2 — Planificateur de tâches (après la semaine de test, pas maintenant)

À configurer sur le laptop de Julien une fois la semaine de test terminée
— **rien à faire pour l'instant**. Pourquoi le Planificateur : lancer la
session en arrière-plan (sans fenêtre visible au premier plan), avec un
délai pour laisser le bureau se stabiliser, et sans dépendre du dossier
Démarrage.

Étapes (à faire plus tard) :
1. Ouvrir le Planificateur de tâches (`taskschd.msc`).
2. Créer une tâche « Jarvis-Muse » : déclencheur « À l'ouverture de
   session » ; action « Démarrer un programme » : Programme =
   `powershell.exe`, Arguments =
   `-ExecutionPolicy Bypass -File "C:\chemin\vers\Jarvis-Muse\scripts\lancer_session.ps1"`,
   « Démarrer dans » = dossier du dépôt.
3. Options recommandées : « Exécuter uniquement si l'utilisateur est
   connecté » ; délai de 30 s ; « Ne pas démarrer si l'ordinateur
   fonctionne sur batterie » décoché si besoin.
4. Retirer le raccourci du dossier Démarrage une fois la tâche en place
   (éviter un double lancement au login).
5. Tester : redémarrer, vérifier que la session démarre une seule fois.

## Personnalisation

Dans `config.toml` (copier `config/config.example.toml` vers `config.toml`
si ce n'est pas déjà fait) :

```toml
[hud]
active = true            # false = le HUD ne démarre pas
position = "bas-droite"  # bas-droite | bas-gauche | haut-droite | haut-gauche
taille = 180             # taille de la fenêtre en pixels (120 à 320)
toujours_au_premier_plan = true
intervalle_ms = 500      # relecture de l'état, en millisecondes

[session]
lire_a_dire = true                 # lire les résumés Carson au lancement
annoncer_minuteurs_du_jour = true  # annoncer les minuteurs du jour
demarrer_hud = true                # démarrer le HUD avec la session
```

La position exacte de la fenêtre est mémorisée dans `data/widget.json`
(gitignoré) quand vous la déplacez à la souris.

### Fenêtres en quadrants (bloc 28, validé le 21 nov. 2026)

Dans `config.local.toml` (privé, gitignoré) — **liste vide par défaut,
à compléter avec Julien** : rien n'est ouvert ni déplacé tant que la
liste est vide.

```toml
[quadrants]
actif = true
apps = [
  { nom = "Code", processus = "Code", quadrant = "haut-gauche" },
  { nom = "Chrome", processus = "chrome", quadrant = "bas-gauche" },
]
```

- `nom` : nom affiché dans les messages.
- `processus` : nom du processus Windows (sans `.exe`).
- `chemin` (optionnel) : chemin complet de l'exécutable à lancer si
  l'application n'est pas déjà ouverte (ex.
  `chemin = "C:\\Users\\Julien\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe"`).
  Sans `chemin`, le lancement utilise le nom du processus (fonctionne
  s'il est sur le PATH).
- `quadrant` : `haut-gauche`, `haut-droite`, `bas-gauche` ou `bas-droite`.
- Une application introuvable ou sans fenêtre est ignorée avec un
  avertissement — la session continue.

## Sécurité

- **Aucun serveur réseau** : le HUD et la boucle communiquent par
  fichiers locaux uniquement. Si un serveur local devient nécessaire
  plus tard (étape 7, mini-PC) : `127.0.0.1` seulement, jamais `0.0.0.0`
  sans authentification (faille du dépôt A).
- **Rien de sensible affiché** : le HUD ne montre que l'état, l'heure,
  les minuteurs et la dernière phrase entendue.
- **Les fichiers `data/` sont gitignorés** : état, position et minuteurs
  ne quittent jamais la machine.

## Dépannage

- **« Tkinter est indisponible »** : réinstallez Python depuis
  python.org avec l'option « tcl/tk and IDLE » ; en attendant, le HUD
  bascule sur l'icône de barre système (`pip install pystray`).
- **Le HUD ne s'affiche pas** : vérifiez avec
  `python scripts\hud.py --verifier`. Sur une machine sans écran
  (connexion distante sans bureau), le HUD ne peut pas s'afficher.
- **L'anneau reste gris-bleu** : la boucle vocale n'a pas encore écrit
  `data/hud-state.json` — lancez-la (`python scripts\boucle_voix.py`),
  l'état apparaît au premier changement de phase.
- **Le clic maintenu ne démarre pas l'enregistrement** : vérifiez que
  la boucle vocale tourne (c'est elle qui lit `data/hud-ptt.json`) et
  que le clic ne déplace pas la fenêtre (maintenir sans bouger la souris
  250 ms ; glisser = déplacer).
- **Le minuteur n'apparaît pas dans le HUD** : vérifiez
  `python scripts\minuteur.py lister` — le HUD lit le même fichier
  (`data/timers.json`).
- **« Impossible de démarrer le surveillant »** : lancez-le à la main
  dans une autre fenêtre : `python scripts\minuteur.py surveiller`.
- **PowerShell bloque le script** : lancez avec
  `powershell -ExecutionPolicy Bypass -File scripts\lancer_session.ps1`,
  ou une fois : `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- **Le double-clic ouvre le Bloc-notes** : clic droit sur
  `lancer_session.ps1` → « Exécuter avec PowerShell », ou créez un
  raccourci vers la commande de la section Utilisation.

## Ce qui reste à faire

- Tester sur le laptop de Julien : HUD seul (anneau, panneau, clic = F9),
  session complète (minuteurs du jour, `a-dire/`, HUD, boucle), mesure
  RAM/CPU réelles (cibles : < 100 Mo, ~0 % en veille).
- Compléter la liste des applications en quadrants avec Julien.
- Auto-start : étape 1 livrée (raccourci manuel, semaine de test en cours),
  étape 2 (Planificateur de tâches) à configurer après la semaine de test.
- Notes quotidiennes (bloc 23) et lecture de page complète en boucle vocale
  (bloc 16) : décisions encore ouvertes, non construites dans cette étape.
- Étape suivante (7) : serveur local sur mini-PC (si acheté).
