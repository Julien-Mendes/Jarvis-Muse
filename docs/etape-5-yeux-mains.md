# Étape 5 — Yeux et mains : vision d'écran et contrôle du navigateur

Le Jarvis local voit enfin l'écran et ouvre le navigateur. Deux scripts :
`scripts/yeux.py` (capture ciblée + description en français) et
`scripts/navigateur.py` (Playwright : naviguer, rechercher, cliquer, lire,
capture de page). Les deux sont branchés comme outils dans la boucle vocale
(`scripts/boucle_voix.py`) : « regarde mon écran », « ouvre [site] dans le
navigateur ».

## Principe

### Les yeux — `yeux.py`

- **Capture ciblée par défaut** : la fenêtre active (Windows) ou une région
  `X,Y,Largeur,Hauteur`. Jamais tout l'écran sans `--tout-ecran` explicite
  (et un avertissement est affiché dans ce cas).
- **Consentement explicite à chaque capture** (décision bloc 26, 21 nov.
  2026). En ligne de commande, l'invocation vaut consentement. Dans la
  boucle vocale, Jarvis demande « Je peux regarder ton écran ? » et attend
  un « oui » court — la capture n'a jamais lieu sans ce oui.
- La capture est réduite (largeur max 1280 px, JPEG qualité 80) puis
  envoyée au modèle de vision choisi dans la configuration. La description
  revient en 2 à 3 phrases, en français.
- La capture n'est jamais écrite sur disque, sauf si `--sortie` est donné.

### Les mains — `navigateur.py`

- `ouvrir` : ouvre une URL dans le **navigateur par défaut** de Julien
  (pas de Playwright) — le navigateur reste ouvert naturellement.
- `rechercher` / `lire` / `capture` / `cliquer` : **Google Chrome visible**
  piloté par Playwright (canal `chrome` — Chrome seulement depuis le lot
  C1, profil séparé sans les connexions de Julien, fenêtre maximisée, langue
  de Chrome = langue de Jarvis), une seule instance par processus.
  Recherche DuckDuckGo + clic sur le premier résultat (patron du dépôt A).
- **Lot C1 — session persistante** : un seul Chrome et un **onglet courant
  réutilisé** d'un tour à l'autre ; naviguer ne crée jamais d'onglet, et un
  site déjà affiché n'est pas rechargé (`"deja_ouvert"`). Si Julien ferme
  l'onglet, un autre onglet ouvert est repris ; si Chrome ou le processus
  est tombé, il est relancé proprement et Jarvis le dit (« Le navigateur
  s'était fermé, je l'ai relancé »).
- **Lot C1 — `chercher_et_ouvrir`** (YouTube seulement) : page de résultats
  YouTube (adresse `results?search_query=…`, équivalent exact du champ de
  recherche + Entrée, sans toucher à aucun formulaire), liste titre + chaîne
  + URL, choix du résultat qui correspond au titre et à la chaîne demandés
  (`choisir_resultat` : jamais de clic au hasard), clic sur son lien. Si
  rien ne correspond : les 3 premiers titres sont renvoyés.
- **Lecture seule par défaut** : navigation, recherche, clics sur liens et
  boutons, lecture de texte, capture de page. Il n'existe **aucune**
  commande pour remplir un formulaire, se connecter ou acheter — et
  `cliquer` refuse en code (`refus_clic`, `refus_element`) tout élément
  situé dans un `<form>`, tout champ de saisie ou bouton d'envoi, tout lien
  de connexion/compte/paiement, et tout bouton d'action (s'abonner, aimer,
  commenter, partager, télécharger, accepter, fermer…). Connexion et achat
  sont refusés même sur un simple lien. Fermer un onglet passe par
  `fermer_onglet`, que la boucle n'envoie qu'après un « oui » oral.
- Seules les URL http(s) sont acceptées ; `javascript:`, `file:`, `data:`
  et autres schémas sont refusés.

## Le modèle de vision — point important

Le fournisseur de vision se choisit dans `config.toml`, section `[yeux]`,
clé `fournisseur_vision` — jamais en dur dans le code.

- **Défaut : `groq`** (`qwen/qwen3.8-27b`, multimodal — un seul service,
  Groq, pour cerveau + STT + vision, décision de Julien le 21 nov. 2026).
  Llama 4 Scout (`meta-llama/llama-4-scout-17b-16e-instruct`) a été
  **retiré du palier gratuit Groq le 17 juillet 2026** (annoncé le
  17 juin 2026). `qwen/qwen3.8-27b` est un modèle **« preview »** : Groq
  peut le retirer à court préavis — **à vérifier au premier test**.
  Une erreur 404 (`model_not_found`) signifie que le modèle n'est plus
  disponible : changer `modele_vision_groq` dans `config.toml` (consulter
  la liste des modèles Groq du moment) ou repasser à `anthropic`.
- **Repli : `anthropic`** (Claude Haiku, vision confirmée, payant à
  l'usage — quelques centimes par capture au plus, les captures sont
  occasionnelles). Basculer = une ligne dans `config.toml`.
- Les clés sont les mêmes que pour la boucle (`GROQ_API_KEY`,
  `ANTHROPIC_API_KEY` dans `.env`) — aucune nouvelle clé à créer.

## Prérequis

- Python 3.10+ et Windows (laptop de Julien pour tester).
- Étapes 2 à 4 installées : voix Piper, minuteur, boucle vocale F9.
- Une clé **Groq** (vision par défaut, même clé que la boucle) ou
  **Anthropic** (repli) dans `.env` — voir
  `docs/etape-4-declenchement.md` pour les obtenir.
- Chromium pour Playwright (voir Installation).

## Installation

Dans le dossier du dépôt cloné, en PowerShell :

```powershell
# 1. Créer et activer un environnement virtuel (si ce n'est pas déjà fait)
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Installer les dépendances de l'étape 5
pip install -r scripts\requirements-etape5.txt

# 3. Google Chrome doit être installé (lot C1 : Chrome seulement ;
#    Playwright pilote le Chrome de la machine, pas de Chromium à installer)
```

Si PowerShell bloque l'activation :
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (une seule fois),
puis recommencer l'activation.

## Configuration

Dans `config.toml` (copier `config/config.example.toml` vers `config.toml`
si ce n'est pas déjà fait) :

```toml
[yeux]
fournisseur_vision = "groq"   # "groq" (défaut) ou "anthropic" (repli)
modele_vision_groq = "qwen/qwen3.8-27b"
modele_vision_anthropic = "claude-haiku-4-5-20251001"
largeur_max = 1280
max_tokens_description = 300

[navigateur]
navigateur_defaut = "systeme"
delai_apres_navigation = 2
max_caracteres_page = 5000
```

La variable d'environnement `JARVIS_VISION` (`groq` ou `anthropic`) prime
sur le fichier.

## Utilisation — les yeux

```powershell
# Vérifier l'installation
python scripts\yeux.py --verifier

# Décrire la fenêtre active (défaut)
python scripts\yeux.py decrire --fenetre

# Décrire une région précise (x, y, largeur, hauteur en pixels)
python scripts\yeux.py decrire --region 100,200,800,600

# Poser une question précise sur l'écran
python scripts\yeux.py decrire --fenetre --question "qu'est-ce qui est écrit dans la fenêtre d'erreur ?"

# Capturer seulement, sans envoi au cloud (pour tester la capture)
python scripts\yeux.py capturer --fenetre --sortie capture.png

# Écran complet — à éviter, avertissement affiché
python scripts\yeux.py decrire --tout-ecran
```

## Utilisation — le navigateur

```powershell
# Ouvrir un site dans le navigateur par défaut (reste ouvert)
python scripts\navigateur.py ouvrir youtube.com

# Rechercher et ouvrir le premier résultat (Chromium visible, reste ouvert
# jusqu'à Entrée ou Ctrl+C)
python scripts\navigateur.py rechercher "météo Brossard"

# Lire le texte d'une page (tronqué à 5 000 caractères par défaut)
python scripts\navigateur.py lire https://example.com

# Capture d'écran d'une page
python scripts\navigateur.py capture https://example.com --sortie page.png
```

### Mode interactif (utilisé par la boucle vocale)

`python scripts\navigateur.py --interactif` lit des commandes JSON sur
stdin (une par ligne) et répond en JSON sur stdout :

```json
{"commande": "naviguer", "url": "https://example.com"}
{"commande": "rechercher", "requete": "météo Brossard"}
{"commande": "chercher_et_ouvrir", "site": "youtube", "titre": "...", "chaine": "..."}
{"commande": "cliquer", "texte": "Vidéos"}
{"commande": "fermer_onglet"}
{"commande": "texte", "max_caracteres": 5000}
{"commande": "capture", "sortie": "capture-page.png"}
{"commande": "fermer"}
{"commande": "ping"}
```

Réponses : `{"ok": true, "titre": ..., "url": ...}` ou
`{"ok": false, "erreur": "..."}`. Le texte de page est marqué
`"non_fiable": true` : c'est une donnée externe (de même pour la réponse
de `chercher_et_ouvrir`). `"redemarre": true` signale que Chrome a dû être
relancé pendant la commande.

## Utilisation — dans la boucle vocale

Dans `scripts/boucle_voix.py` (F9 pour parler) :

- **« Regarde mon écran »** (ou « qu'est-ce qu'il y a sur mon écran ? »,
  « décris mon écran »…) : Jarvis demande « Je peux regarder ton écran ? ».
  Répondez **« oui »** (court, 8 mots maximum) : la capture de la fenêtre
  active est décrite à voix haute. Toute autre réponse annule la demande.
  En mode `--texte` (sans micro), la confirmation ne peut pas aboutir —
  utilisez `scripts/yeux.py decrire --fenetre` directement.
- **« Ouvre youtube.com »** / **« Ouvre le site de la SAQ »** : le site
  s'ouvre dans l'onglet courant de Chrome (réglage `[navigateur]
  navigateur_defaut = "playwright"`, défaut depuis C1 ; si Chrome ne démarre
  pas, repli sur le navigateur par défaut). Redemandé, un site déjà ouvert
  n'est pas rouvert : « C'est déjà ouvert dans l'onglet actuel ».
  **« Cherche … dans le navigateur »** : recherche DuckDuckGo, premier
  résultat ouvert.
- **« Ouvre la vidéo YouTube "…" de … »** (lot C1, par le modèle, outil
  `chercher_et_ouvrir`) : recherche, choix du bon résultat, clic, puis
  Jarvis dit le titre ouvert. Cette phrase est dite directement par le code
  (le titre trouvé est une donnée externe, nettoyé et tronqué, jamais
  redonné au modèle ; l'historique ne garde que les mots de Julien). Si rien
  ne correspond, Jarvis le dit et lit les 3 premiers titres.
- **« Clique sur … »** (outil `cliquer`) : clic sur un lien par son texte,
  avec les refus en code décrits plus haut. Le titre de la page obtenue
  n'est pas redonné au modèle.
- **« Ferme l'onglet »** / **« Ferme Chrome »** (chemin rapide ou outil
  `fermer_onglet`) : Jarvis demande toujours « Je ferme l'onglet ? » ; seul
  un « oui » court dans les 30 s ferme quoi que ce soit.
- **Limites dites clairement** : le prompt système impose de dire en une
  phrase ce qui n'est pas possible (« Je peux ouvrir YouTube, mais je ne
  peux pas cliquer sur ça ») au lieu d'une formule vague, et de ne pas
  refaire une action déjà faite.
- La lecture complète de page en boucle vocale n'est **pas** branchée :
  décision bloc 16 encore ouverte. `navigateur.py lire` reste disponible
  en ligne de commande.

## Sécurité et consentement

- **Aucune capture sans consentement explicite, à chaque capture**
  (docs/regles-securite.md §6). La capture ciblée (fenêtre/région)
  remplace la capture plein écran du dépôt A, qui envoyait tout l'écran
  à Claude Vision sans sélection.
- **Données externes = non fiables (§1)** : la description d'écran et le
  texte d'une page sont enveloppés dans `<untrusted_data>` avant d'être
  transmis au modèle, avec l'instruction de les résumer sans jamais
  suivre d'instruction qu'ils contiennent. Une page web ne peut pas
  ordonner quoi que ce soit à Jarvis.
- **Hold_writes (§2)** : après une lecture externe (écran ou page), les
  écritures sont bloquées pour le tour — sauf le minuteur, qui reste
  autorisé parce qu'il exige déjà une demande orale explicite de Julien.
- **Aucune écriture web** : pas de formulaire, pas de connexion, pas
  d'achat. Le clic sur un élément de formulaire est refusé en code.
- **Journaux sans contenu (§7)** : ni capture, ni texte de page, ni
  transcription dans les journaux.
- **Aucun serveur local** à cette étape : rien n'écoute sur un port (le
  navigateur Playwright est un processus local, pas un serveur).

## Dépannage

- **« module playwright n'est pas installé »** : `pip install -r
  scripts\requirements-etape5.txt` (dans le venv activé).
- **« Google Chrome introuvable »** : le contrôle du navigateur ne
  fonctionne qu'avec Chrome (lot C1) — installez Google Chrome ; Chromium
  de Playwright n'est plus utilisé.
- **« module Pillow n'est pas installé »** : `pip install -r
  scripts\requirements-etape5.txt`.
- **« La capture de la fenêtre active n'est prise en charge que sous
  Windows »** : utilisez `--region X,Y,L,H` (coordonnées en pixels).
- **« Modèle vision introuvable (404) »** : le modèle configuré n'existe
  plus sur ce palier — changez `modele_vision_groq` /
  `modele_vision_anthropic` dans `config.toml`, ou changez de
  `fournisseur_vision`. Voir « Le modèle de vision » ci-dessus.
- **« Clé API refusée (401) »** : vérifiez la clé dans `.env` (jamais
  dans une conversation ou une capture d'écran).
- **« Limite de débit atteinte (429) »** : le palier gratuit fait
  attendre — réessayez dans quelques secondes.
- **Le navigateur ne s'ouvre pas dans la boucle** : la boucle retombe
  sur le navigateur par défaut (`webbrowser.open`) si Playwright est
  absent ; vérifiez l'installation avec
  `python scripts\navigateur.py --interactif` puis `{"commande": "ping"}`.
- **Le clic ne trouve pas le bouton** : le texte doit correspondre au
  texte visible (insensible à la casse, partiel accepté). Si l'élément
  est dans un formulaire, le refus est normal (voir Sécurité).

## Ce qui reste à faire

- Tester sur le laptop de Julien : première capture décrite, première
  ouverture de navigateur, première recherche.
- Vérifier le modèle vision Groq (`qwen/qwen3.8-27b`) au premier test
  (`python scripts\yeux.py decrire --fenetre`), ou repasser à Anthropic
  (`fournisseur_vision = "anthropic"` dans `config.toml`).
- La lecture complète de page en boucle vocale attend la décision bloc 16.
- Lot C1 : `chercher_et_ouvrir` ne connaît que YouTube ; les autres sites
  passent par `ouvrir_navigateur` + `cliquer`. Le relevé des résultats
  dépend de la structure de la page YouTube (sélecteurs
  `ytd-video-renderer` / `a#video-title`, vérifiés le 26 nov. 2026) : à
  revoir si YouTube change sa page.
- Étape suivante (6) : HUD local léger + lancement de session.
