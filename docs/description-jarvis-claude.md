# Description complète — Les deux Jarvis construits avec Claude Code

**Date :** 22 novembre 2026
**Pour :** Julien Mendes — décider quoi intégrer (ou non) dans son Jarvis basé sur Muse
**Dépôts analysés :** `Julian-Ivanov/jarvis-voice-assistant` et `tanishvbuk/jarvis-assistant`
**Méthode :** lecture directe des fichiers des deux dépôts publics (README, code source, configurations, documentation). Rien n'a été construit, acheté ni contacté. Chaque affirmation renvoie à un fichier lu ; les points non documentés sont signalés comme tels.

**Contexte Muse de Julien (rappel) :** l'équivalent Muse est déjà en partie en place — Carson comme agent (voix temps réel en français et en anglais, mémoire persistante, connecteurs Gmail et Google Calendar, veilles, résumés marchés, balado Business News, rappels) + Muse Code pour l'outillage local + le dépôt privé `Julien-Mendes/Jarvis-Muse` comme pont GitHub (README et dossiers `scripts/`, `config/`, `docs/` en place). Ce document compare les deux Jarvis Claude à cet existant, bloc par bloc.

---

## 0. En bref

| | Dépôt A — Julian-Ivanov | Dépôt B — tanishvbuk |
|---|---|---|
| Nom complet | `Julian-Ivanov/jarvis-voice-assistant` | `tanishvbuk/jarvis-assistant` |
| Description | « Personal AI assistant with voice control, browser automation, and screen capture. Double-clap to launch. Built with Claude Code. » | « Push-to-talk voice assistant for Windows, built with Claude Code » |
| Langage | Python | Python |
| Créé / mis à jour | 8 avril 2026 / 17 nov. 2026 (dernier push le jour de la création) | 16 oct. 2026 / 5 nov. 2026 |
| Popularité | 142 étoiles, 66 forks, 5 issues ouvertes | 2 étoiles, 2 forks, 0 issue ouverte |
| Branche par défaut | `master` | `main` |
| OS | Windows 10/11 | Windows 11 uniquement |
| Langue | Allemand uniquement | Anglais uniquement |
| Déclenchement | Double-clap (lancement de session) ; ensuite écoute continue | Push-to-talk (F9) ou mot de réveil « Hey Jarvis » |
| Cerveau (LLM) | Claude Haiku (`claude-haiku-4-5-20251001`) | Groq `openai/gpt-oss-120b` par défaut, ou Claude Haiku 5.5, ou OpenRouter |
| Voix (TTS) | ElevenLabs (cloud, `eleven_turbo_v2_5`) | Kokoro / Piper / SAPI, en local |
| Transcription (STT) | Web Speech API de Chrome (cloud) | Whisper via Groq (cloud) ou faster-whisper local |
| Points forts | Contrôle du navigateur (Playwright), vision d'écran, lancement de session + fenêtres en quadrants | Mot de réveil local, Gmail/Calendrier/Tâches Google, minuteurs persistants, HUD local, modèle de sécurité anti-injection |
| Points faibles | Aucune mémoire durable, pas de calendrier/courriel/domotique, serveur sans authentification, allemand seulement | Windows seulement, anglais seulement, aucune domotique/musique/messagerie, mémoire en RAM seulement |

**Conclusion en une phrase :** aucun des deux n'est un Jarvis complet — les deux sont des assistants vocaux personnels, mono-machine et mono-utilisateur, sans domotique, sans musique, sans messagerie et sans mémoire persistante. Le dépôt A apporte surtout des « yeux et des mains » (navigateur, écran, lancement d'applications) ; le dépôt B apporte surtout une structure (outils Google, minuteurs, HUD, sécurité). Pour Julien, la plus grande partie de ce que fait le dépôt B est **déjà couverte par Carson** ; ce qui manque vraiment côté Muse, ce sont les capacités **locales** du dépôt A (voir l'écran, contrôler le PC) et le déclenchement vocal local du dépôt B.

---

## 1. Dépôt A — Julian-Ivanov/jarvis-voice-assistant

### 1.1 Vue d'ensemble

But annoncé dès la première ligne du README : *« Double-clap. Jarvis wakes up, greets you with the weather and your tasks, answers your questions with dry British wit, controls your browser, and sees your screen. »* Le projet est construit entièrement avec Claude Code, sans code écrit manuellement (selon le README).

Fonctionnalités annoncées :
- **Double-Clap Trigger** — deux claquements de mains lancent tout l'espace de travail : Spotify, VS Code, Obsidian, Chrome avec l'interface Jarvis.
- **Voice Conversation** — conversation vocale libre par microphone.
- **Sarcastic British Butler** — Jarvis parle **allemand** avec la personnalité du majordome de Tony Stark : sec, spirituel. (Incohérence assumée par le projet : personnalité « britannique », langue allemande.)
- **Weather & Tasks** — à l'allumage, salutation avec la météo et un résumé humoristique des tâches ouvertes d'Obsidian.
- **Browser Automation** — « Search for MiroFish » : ouvre un vrai navigateur, navigue, lit le contenu, résume.
- **Screen Vision** — « What's on my screen? » : capture d'écran, analyse par Claude Vision, description.
- **World News** — « What's happening in the world? » : ouvre `worldmonitor.app` et résume l'actualité mondiale.
- **Window Snapping** — les applications lancées se rangent automatiquement en quadrants.

Une vidéo de démonstration est citée (`https://youtu.be/XsceN-hEit4`) — contenu vidéo non visionné dans cette analyse.

### 1.2 Architecture générale et flux de bout en bout

**Trois couches, simples et lisibles** (`server.py`, 597 lignes, 12 721 octets) :
1. **Frontend web** (`frontend/`) : page HTML avec un orbe, Web Speech API pour la transcription, lecture audio MP3.
2. **Serveur local FastAPI + Uvicorn** (`server.py`) : écoute sur `0.0.0.0:8340`, sert la page (`GET /`) et les fichiers statiques (`/static`), WebSocket sur `/ws`.
3. **Cerveau et voix en infonuagique** : Claude Haiku (`claude-haiku-4-5-20251001`, `max_tokens=400` pour la réponse, `max_tokens=250` pour les résumés) et ElevenLabs (`eleven_turbo_v2_5`, `stability 0.5`, `similarity_boost 0.85`).

**Flux complet :**
1. Au lancement du serveur, `refresh_data()` est appelé : météo via `get_weather_sync()` et tâches via `get_tasks_sync()`.
2. Le frontend ouvre un WebSocket ; un `session_id` est créé. À la déconnexion, l'historique de la session est supprimé.
3. **Réveil :** il n'y a **pas de mot de réveil vocal**. Le frontend envoie automatiquement `{text: 'Jarvis activate'}` dès la connexion, ce qui déclenche la salutation (météo + tâches). Si le texte de l'utilisateur contient « activate », les données sont rafraîchies.
4. Le texte transcrit arrive par WebSocket ; les messages vides sont ignorés.
5. `process_message()` ajoute le message à l'historique de session, tronqué aux **16 derniers messages**, puis appelle Claude Haiku avec le prompt système généré par `build_system_prompt()` (personnalité, météo, tâches, heure courante).
6. La réponse est analysée par `extract_action()` avec la regex `\[ACTION:(\w+)\]\s*(.*?)$`. Le texte avant la balise est lu à voix haute ; la balise est exécutée silencieusement.
7. `synthesize_speech()` découpe les textes de plus de 250 caractères en phrases et appelle ElevenLabs par morceaux ; l'audio MP3 est renvoyé au frontend en base64 (`{"type": "response", "text": ..., "audio": ...}`).
8. Après une action SEARCH / BROWSE / SCREEN / NEWS, un **second appel** à Claude Haiku résume le résultat en max. 3 phrases en allemand, puis ce résumé est vocalisé. Pour OPEN, rien n'est résumé.

**Prompt système** (`build_system_prompt()`, en allemand, codé en dur) : « Du bist Jarvis, der KI-Assistent von Tony Stark aus Iron Man. Dein Dienstherr ist Julian, ein KI-Berater und Automatisierungsexperte. Du sprichst ausschliesslich Deutsch. […] Dein Ton ist trocken, sarkastisch und britisch-hoeflich […] Halte deine Antworten kurz — maximal 3 Saetze. » Il injecte la météo et les tâches ouvertes (max. 5). Règle de grammaire explicite : utiliser « Sie » comme pronom (« FALSCH: "Sir planen", RICHTIG: "Sie planen, Sir" »).

**Données au démarrage :**
- **Météo** (`get_weather_sync()`) : requête sans clé API vers `https://wttr.in/{CITY}?format=j1` (timeout 5 s) : température, ressenti, description, humidité, vent (km/h). En cas d'échec, retourne `None` (silencieux).
- **Tâches** (`get_tasks_sync()`) : lit `{obsidian_inbox_path}/Tasks.md` et extrait les lignes commençant par `- [ ]` (cases non cochées). En cas d'échec, liste vide.

**Points techniques notables :** `execute_action()` gère un type `BROWSE` (appel à `browser_tools.visit(p)`) alors que le prompt système ne documente jamais `[ACTION:BROWSE]` — code atteignable mais non documenté. Les erreurs TTS et d'action sont seulement journalisées (`print`) ; en cas d'échec TTS, l'audio est vide mais le texte est quand même envoyé. `config.json` est lu **à l'import, sans repli** — le serveur plante si le fichier est absent. Valeurs par défaut codées en dur : nom « Julian », adresse « Sir », ville « Hamburg », voice ID ElevenLabs `rDmv3mOhK6TnhYWckFaD`.

### 1.3 Pipeline vocal

- **Mot de réveil : aucun.** Le mécanisme signature est un **déclencheur de lancement par le son, pas un wake word**. `scripts/clap-trigger.py` (123 lignes) écoute le microphone en continu avec `sounddevice` (44 100 Hz, blocs de 1 024 échantillons, mono, `float32`) et calcule le RMS de chaque bloc. Un pic au-dessus du seuil `THRESHOLD = 0.15` (RMS) compte comme un clap. Deux claps espacés de **0,1 s minimum et 1,2 s maximum** déclenchent le lancement de `launch-session.ps1`, puis **le processus s'arrête** (« Trigger fired — stopped listening »). Il faut le relancer (ou l'auto-start au login) pour un prochain double-clap. `COOLDOWN = 3.0` est défini mais **jamais utilisé** dans le code. Réglage documenté : baisser `THRESHOLD` (ex. 0,10) si les claps ne sont pas détectés.
- **STT : Web Speech API de Chrome** (`frontend/main.js`), langue **`de-DE`**, mode continu, résultats finaux uniquement. Aucun autre moteur STT (pas de Whisper, pas de service local). La transcription passe donc par le service de reconnaissance de Google/Chrome (infonuagique).
- **TTS : ElevenLabs**, modèle `eleven_turbo_v2_5`, voix définie par `elevenlabs_voice_id` dans `config.json`. Le README/SETUP recommandent une voix allemande (ex. « Felix Serenitas »).
- **Latence : non documentée.** Aucune mesure annoncée ni mesurable à partir des fichiers. Seuls des timeouts et attentes fixes existent : timeout HTTP 30 s (ElevenLabs), timeout météo 5 s, navigation Playwright 15 s (20 s pour les news), attentes fixes de 2 s (après recherche), 3 s (après clic), 6 s (rendu de worldmonitor.app), reconnexion WebSocket après 3 s. La chaîne comporte au minimum deux appels réseau en série (Claude Haiku puis ElevenLabs), plus un second appel Haiku en cas d'action.

### 1.4 Capacités et outils

| Capacité | État | Preuve (fichier) |
|---|---|---|
| Conversation vocale libre, questions générales | ✅ Oui | `server.py` (Claude Haiku), `frontend/main.js` (Web Speech API) |
| Météo au démarrage / sur demande | ✅ Oui | `server.py` (`get_weather_sync`, `wttr.in`, sans clé) |
| Tâches Obsidian lues au démarrage | ✅ Oui, lecture seule | `server.py` (`get_tasks_sync`, lit `Tasks.md`, lignes `- [ ]`) |
| Recherche web + lecture de page | ✅ Oui | `browser_tools.py` (`search_and_read` : DuckDuckGo, 1er résultat, 3 000 car.) ; action `[ACTION:SEARCH]` |
| Ouvrir une URL dans le navigateur | ✅ Oui | `browser_tools.py` (`open_url` via `webbrowser.open`) ; action `[ACTION:OPEN]` ; `visit()` (5 000 car., action `BROWSE` non documentée au prompt) |
| Actualités mondiales | ✅ Oui | `browser_tools.py` (`fetch_news`, `worldmonitor.app`, 4 000 car.) ; action `[ACTION:NEWS]` |
| Voir et décrire l'écran | ✅ Oui | `screen_capture.py` (`ImageGrab.grab()` + Claude Vision, 2–3 phrases) ; action `[ACTION:SCREEN]` |
| Lancer des applications + musique au double-clap | ✅ Oui | `scripts/launch-session.ps1` (serveur, URI Spotify, VS Code, `config.apps`, Chrome) ; `scripts/clap-trigger.py` |
| Ranger les fenêtres en quadrants | ✅ Oui | `scripts/launch-session.ps1` (`Snap-Window`, Win32 `MoveWindow` : VS Code haut-gauche, Obsidian haut-droite, Chrome bas-gauche, Spotify bas-droite) |
| Calendrier | ❌ Non | Aucune mention de calendrier dans aucun fichier lu |
| Courriels (lecture/envoi) | ❌ Non | Aucun connecteur courriel |
| Messages (SMS, WhatsApp, etc.) | ❌ Non | Aucun connecteur de messagerie |
| Domotique | ❌ Non | Aucun protocole domotique |
| Fichiers (créer/modifier/rechercher) | ⚠️ Lecture seule d'un fichier | Seule lecture : `Tasks.md` d'Obsidian |
| Musique (contrôle de lecture) | ⚠️ Lancement seulement | `launch-session.ps1` ouvre un URI `spotify:track:...` au démarrage ; aucun contrôle (pause, volume, piste suivante) |
| Rappels / alarmes | ❌ Non | Aucun minuteur, rappel ou alarme |
| Tâches planifiées / automatisations | ⚠️ Auto-start seulement | Auto-start du double-clap au login Windows via le Planificateur de tâches |
| Personnalité configurable | ✅ Oui | `server.py` (`build_system_prompt()`) ; README § Customization |
| Voix / ville / applications configurables | ✅ Oui | `config.example.json` |

**En résumé :** conversation + météo + tâches Obsidian (lecture) + recherche web + ouverture d'URL + actualités + vision d'écran + lancement d'applications. Tout le reste (calendrier, courriels, messages, domotique, rappels, écriture de fichiers) est **absent**.

**Détail des modules :**
- **`browser_tools.py`** (266 lignes) : « Web search via DuckDuckGo Lite, page visits via Playwright, URL opening. » Navigateur Playwright Chromium **visible** (`headless=False`, `--start-maximized`), user-agent Windows Chrome. Instance unique (singleton global) ; jamais fermée par le serveur (la fonction `close()` existe mais n'est appelée nulle part). `search_and_read(query)` : recherche DuckDuckGo, attend 2 s, clique le **premier résultat organique** (`[data-testid="result-title-a"]`), attend 3 s, extrait le texte (sélecteurs essayés dans l'ordre : `main`, `article`, `[role="main"]`, `.content`, `#content`, `body`), tronqué à **3 000 caractères**. La page ouverte n'est **pas fermée** (`finally: pass`). `visit(url, max_chars=5000)` : visite directe (timeout 15 s, `domcontentloaded`), la page **est** fermée. `fetch_news()` : ouvre `https://www.worldmonitor.app/`, attend 6 s (rendu JS), lit `document.body.innerText` tronqué à **4 000 caractères** ; la page reste ouverte pour que l'utilisateur la voie. `open_url(url)` : ouvre l'URL dans le **navigateur par défaut** via `webbrowser.open`. `_bring_chromium_to_front()` : ramène Chromium au premier plan via PowerShell + Win32 `SetForegroundWindow`. Choix de DuckDuckGo justifié dans les commentaires : « no cookie banner, no reCAPTCHA ».
- **`screen_capture.py`** (85 lignes) : `capture_screen()` — `PIL.ImageGrab.grab()` capture **tout l'écran** (pas une fenêtre ciblée), PNG en mémoire. `describe_screen()` — envoie la capture en base64 à Claude Haiku (`max_tokens=300`) : « Beschreibe kurz auf Deutsch was auf diesem Bildschirm zu sehen ist. Maximal 2-3 Saetze. » Aucune sélection de région, de moniteur ou de floutage.
- **`frontend/`** (3 fichiers) : `index.html` (19 lignes, page unique, orbe `#orb`, `#status` « Klicke den Orb um zu sprechen », `#transcript`) ; `main.js` (319 lignes : WebSocket `ws://${location.host}/ws`, reconnexion après 3 s, envoi automatique de `{text: 'Jarvis activate'}` à la connexion, Web Speech API `de-DE` continue, file d'attente audio base64 MP3, MP3 silencieux au premier clic pour contourner l'autoplay de Chrome, orbe cliquable pour pause/reprise, transcription affichée « Du: … » / « Jarvis: … ») ; `style.css` (185 lignes, thème sombre `#0a0a0f`, orbe 150 px, 4 états : `idle` bleu foncé, `listening` bleu pulsation 1,5 s, `thinking` doré 0,8 s, `speaking` vert 0,6 s).
- **`scripts/`** : `clap-trigger.py` (voir §1.3) et `launch-session.ps1` (106 lignes : serveur dans Windows Terminal minimisé, Spotify, VS Code, applications configurées, Chrome avec `http://localhost:8340` + `browser_url`, rangement des fenêtres après 3 s).
- **`.claude/`** : un seul fichier, `settings.local.json` — **contenu non lisible** (accès refusé par GitHub, HTTP 403, non réessayé). Il n'y a ni dossier de commandes, ni agents, ni autre configuration Claude Code ; la configuration tient dans `CLAUDE.md` et `SETUP.md` à la racine.
- **`CLAUDE.md`** (allemand) : instructions pour Claude Code — suivre `SETUP.md`, demander nom, activité et formule d'adresse, les inscrire dans le prompt système de `server.py` (remplacer « Julian », « KI-Berater und Automatisierungsexperte », « Sir »). Ordre impératif : vérifier et installer **d'abord** les prérequis (Python 3.10+, Chrome, `pip install -r requirements.txt`, `playwright install chromium`), **ensuite seulement** le setup (clés API, `config.json`).
- **`SETUP.md`** (allemand) : guide détaillé. Claude Code demande à l'utilisateur : nom et formule d'adresse, clé API Anthropic, clé API ElevenLabs, morceau Spotify, programmes à lancer, site web à ouvrir, ville pour la météo, chemin du coffre Obsidian (optionnel), rôle/tâche de l'utilisateur (intégré au prompt système). Protocole d'installation en étapes 0 à 6, dont l'installation de Python 3.12 via `winget`, le choix d'une voix allemande ElevenLabs (recommandation « Felix Serenitas », plan Starter nécessaire, ou voix standard du plan gratuit), et le remplacement de **toutes** les occurrences de « Julian », « KI-Berater und Automatisierungsexperte », « Sir » et « Hamburg » dans `server.py`.

### 1.5 Mémoire et contexte

- **Historique de conversation en mémoire vive uniquement** (`server.py`) : `conversations: dict[str, list]`, clé = `session_id` (connexion WebSocket). Les 16 derniers messages sont envoyés à Claude Haiku. **À la déconnexion WebSocket, l'historique est supprimé.**
- **Aucune persistance :** pas de base de données, pas de fichier d'historique, pas de journal des conversations, pas de mémoire entre sessions. Chaque reconnexion repart de zéro (sauf la salutation « Jarvis activate »).
- **Contexte injecté à chaque appel :** le prompt système est **régénéré à chaque message** avec l'heure courante, la météo et les tâches — mais météo et tâches ne sont **rafraîchies** qu'au démarrage du serveur et quand le texte contient « activate ».
- **Seule « mémoire » durable :** le fichier `Tasks.md` d'Obsidian, lu depuis le disque (source externe). Les préférences durables sont `config.json` (nom, adresse, ville, voix, applications).
- Pas de résumé de conversations passées, pas de profil utilisateur évolutif, pas de mémoire vectorielle ou sémantique.

### 1.6 Planification et tâches en arrière-plan

- **Aucun planificateur interne :** pas de cron, pas de file de tâches, pas de rappels, pas de tâches différées. `server.py` ne contient aucune boucle de fond (hormis le serveur WebSocket lui-même).
- **Seule planification : l'auto-start Windows.** Le README et `SETUP.md` décrivent la création d'une tâche du Planificateur de tâches Windows (« At log on ») qui lance `scripts/clap-trigger.py` au login. Le déclencheur lui-même est **à usage unique** : après un double-clap, le processus se termine ; il faut le relancer manuellement (ou via le login suivant) pour réarmer l'écoute.
- **`launch-session.ps1`** est une séquence de lancement ponctuelle, pas une tâche récurrente. Les rafraîchissements de données sont déclenchés par événement (démarrage du serveur, message contenant « activate »), jamais par minuterie.

### 1.7 Sécurité et vie privée

- **Local :** serveur FastAPI sur la machine (`0.0.0.0:8340`), orchestration, capture d'écran (Pillow) et détection de clap (microphone local) en local.
- **Infonuagique — Anthropic :** chaque message utilisateur (historique de 16 messages), chaque capture d'écran complète et chaque demande de résumé sont envoyés à Claude Haiku.
- **Infonuagique — ElevenLabs :** chaque réponse textuelle est envoyée pour synthèse vocale.
- **Infonuagique — Google/Chrome :** la transcription vocale utilise la Web Speech API de Chrome (service de reconnaissance distant, pas de STT local).
- **Infonuagique — tiers :** météo via `wttr.in` (sans clé, ville en clair dans l'URL), recherche via DuckDuckGo, actualités via `worldmonitor.app`.
- **Clés API :** les deux clés (Anthropic, ElevenLabs) sont stockées **en clair dans `config.json`**, simple fichier JSON local. Le fichier est exclu du dépôt par `.gitignore`, mais il n'y a ni chiffrement, ni variables d'environnement, ni gestionnaire de secrets. `server.py` lit le fichier à l'import et conserve les clés en variables globales. Aucun secret n'est présent dans le dépôt public (seul `config.example.json` avec des placeholders est versionné).
- **Microphone :** en continu, deux fois — par Chrome (reconnaissance vocale) et par `clap-trigger.py` (écoute des claps).
- **Écran :** capture complète envoyée à Claude Vision à chaque demande « What's on my screen? ».
- **Navigateur :** Playwright Chromium visible, contrôlé par le serveur (navigation, clics, lecture de pages) + ouverture d'URL dans le navigateur par défaut ; la fenêtre Chromium est ramenée au premier plan par PowerShell/Win32.
- **Système Windows :** PowerShell, Win32 API (`MoveWindow`, `ShowWindow`, `SetForegroundWindow`), lancement de processus (`wt.exe`, `code`, Spotify, Chrome, applications arbitraires via URI dans `config.apps`).
- **Réseau : point faible majeur.** Le serveur écoute sur **`0.0.0.0:8340`** (toutes les interfaces, pas seulement `localhost`), **sans authentification, sans HTTPS, sans limitation de débit** sur `/` et `/ws`. Toute personne pouvant joindre le port 8340 de la machine peut ouvrir l'interface et envoyer des messages à l'assistant. À n'utiliser que sur un réseau de confiance, ou à restreindre à `127.0.0.1` (modification non documentée dans le projet).
- **Données personnelles codées en dur :** le prompt système contient le nom, le rôle et la ville de l'utilisateur d'origine (« Julian », « KI-Berater und Automatisierungsexperte », « Hamburg ») ; `SETUP.md` insiste pour remplacer **toutes** les occurrences lors de l'installation chez un autre utilisateur.

### 1.8 Prérequis, coûts, installation

| Catégorie | Prérequis (source) |
|---|---|
| OS | **Windows 10/11** (README, SETUP.md). PowerShell, Win32 API, `wt.exe`, Planificateur de tâches. macOS : conversion manuelle via Claude Code, non fournie. |
| Matériel | **Non documenté** précisément : aucun CPU/RAM/stockage minimum indiqué. Implicite : un PC Windows avec microphone, haut-parleurs et écran. |
| Logiciels | Python 3.10+ (3.12 via `winget` dans SETUP.md), Google Chrome (STT + interface), VS Code + Claude Code (recommandés), Spotify et Obsidian (optionnels), Windows Terminal (`wt.exe`). |
| Comptes | Compte Anthropic, compte ElevenLabs, compte Spotify (pour l'URI de morceau), éventuellement Obsidian (coffre local). |
| Clés API | Anthropic (`sk-ant-...`), ElevenLabs (`sk_...`) + Voice ID ElevenLabs. |
| Coûts annoncés | Anthropic : ~0,25 $ / 1 M de tokens (README) ; ElevenLabs : offre gratuite 10 000 caractères/mois (README). Aucun autre coût chiffré ; le coût réel dépend de l'usage (chaque échange = 1 à 2 appels Haiku + 1 appel TTS ; chaque capture d'écran = 1 appel Vision). |
| Dépendances Python | 7 paquets (`fastapi`, `uvicorn`, `anthropic`, `httpx`, `playwright`, `Pillow`, `websockets`), versions minimales seulement. **Manquants : `sounddevice`, `numpy`** (requis par `clap-trigger.py`). |
| Dépendances hors pip | `playwright install chromium` ; Chrome ; `winget install Python.Python.3.12` si Python absent. |
| Réseau | Accès Internet vers `api.anthropic.com`, `api.elevenlabs.io`, `wttr.in`, `duckduckgo.com`, `worldmonitor.app` + service de reconnaissance vocale de Chrome. |

**Installation — deux options :**
- **Option A (recommandée) :** cloner, ouvrir dans VS Code, lancer Claude Code et dire « Set up Jarvis for me » ; Claude Code demande les clés, le nom, les préférences et configure tout automatiquement.
- **Option B (manuelle) :** `pip install -r requirements.txt`, `playwright install chromium`, `cp config.example.json config.json`, éditer `config.json`, `python server.py`, puis ouvrir `http://localhost:8340` dans Chrome et « cliquer n'importe où sur la page, puis parler ».

**Configuration** (`config.example.json`, 11 clés) : `anthropic_api_key`, `elevenlabs_api_key`, `elevenlabs_voice_id`, `user_name`, `user_address` (« Sir » par défaut), `city`, `workspace_path`, `spotify_track` (URI Spotify), `browser_url` (site ouvert avec Chrome au lancement), `obsidian_inbox_path`, `apps` (liste d'URI d'applications, ex. `obsidian://open`). Le vrai `config.json` n'est pas dans le dépôt (ignoré par `.gitignore`) ; seul le modèle est versionné.

### 1.9 Limites connues

- **Allemand uniquement** : prompt système (« Du sprichst ausschliesslich Deutsch »), STT `de-DE`, voix allemande recommandée, interface en allemand. Aucune option de langue dans `config.json`.
- **Windows uniquement** : scripts PowerShell, Win32, chemins `C:\...`, `wt.exe`. La conversion macOS est renvoyée à Claude Code, sans script fourni.
- **Pas de mot de réveil vocal** : écoute continue une fois la page ouverte ; le double-clap ne sert qu'au lancement de la session.
- **Mémoire éphémère** : historique de 16 messages, effacé à la déconnexion.
- **Aucun calendrier, courriel, message, domotique, rappel, écriture de fichier.**
- **Recherche fragile** : `search_and_read` clique le premier résultat DuckDuckGo sans vérification de pertinence ; les pages ouvertes par recherche/news ne sont jamais fermées (fuite de pages Playwright) ; les sélecteurs de titre dépendent du HTML de DuckDuckGo.
- **Dépendances incomplètes** : `sounddevice`/`numpy` absents de `requirements.txt` ; `COOLDOWN` inutilisé dans `clap-trigger.py`.
- **Code mort / non documenté** : action `BROWSE` gérée dans `server.py` mais jamais émise par le prompt.
- **Sécurité** : serveur sans authentification sur `0.0.0.0:8340`, clés en clair dans `config.json`.
- **Dépannage documenté** (README) : Jarvis ne parle pas (serveur arrêté / vieux processus sur le port 8340 → `taskkill /f /im python.exe`), « Connection lost » (vieux serveur), clap non détecté (baisser `THRESHOLD` à 0,10), recherche navigateur en échec (`playwright install chromium`), pas d'audio dans Chrome (cliquer d'abord sur la page — politique d'autoplay), faute de grammaire « Sir planen » au lieu de « Sie planen » (corriger le prompt système).
- **Maintenance du dépôt :** créé et poussé le 2026-04-08, dernière mise à jour le 2026-11-17. Aucun test, aucun CI, aucune licence en fichier, aucune version figée des dépendances.
- **Divergence licence :** le README annonce une licence MIT, mais aucun fichier `LICENSE` n'existe et l'API GitHub indique `license: null`.

---

## 2. Dépôt B — tanishvbuk/jarvis-assistant

### 2.1 Vue d'ensemble

But annoncé (`README.md`) : « A personal push-to-talk voice assistant for Windows. Hold a key, speak, and hear a calm British butler answer. » Forme générale décrite : mot de réveil (« Hey Jarvis ») ou push-to-talk, puis STT infonuagique, un LLM avec outils (courriel, calendrier, tâches, minuteurs, recherche web, suivi de gym), puis une voix britannique locale avec effet « voice in the walls ». Un HUD de science-fiction (adapté de A.L.I.C.E.) montre ce qu'il fait, plus un petit widget rond en verre pour le bureau.

**Fonctionnalités annoncées dans le README :**
- Voix : maintenir F9, parler, relâcher ; F9 pendant qu'il parle l'interrompt ; Ctrl+C quitte.
- Modes de lancement : voix avec HUD, `--no-hud`, `--no-wake` (push-to-talk seulement), `--text`, `--text --hud`, `--text --speak`, `--list-devices`, `--list-voices`, `--google-login`, `pytest`.
- Raccourci en un clic : `--install-shortcut` ajoute « Jarvis » au menu Démarrer, à épingler à la barre des tâches ; fermer la fenêtre du HUD quitte Jarvis.
- HUD : anneau dont la couleur change selon l'état (calme / écoute / traitement / réponse), transcription affichée, horloge et date au centre, repas du jour (en haut à droite, rotation entre plans toutes les 12 s, rafraîchi toutes les 10 min et après minuit), minuteurs (à gauche, les 2 prochains), calendrier (en bas à gauche, reste du jour puis lendemain). Maintenir l'anneau à la souris ou au doigt équivaut à F9. Mode kiosque Edge possible.
- Google : lecture multi-comptes Gmail en lecture seule ; calendrier lu sur tous les comptes, ajout/déplacement/suppression par voix sur les calendriers personnel et « shop » uniquement, après un « oui » oral explicite ; tâches Google Tasks ; plans de repas via Google Sheets.
- Mot de réveil « Hey Jarvis » (modèle openWakeWord, local).
- Minuteurs et rappels persistants (`data/timers.json`).
- Briefing du matin (5 h–12 h, première activation).
- Recherche d'embargos dans les courriels.
- Suivi de gym via openGym auto-hébergé.
- Conversion de devises (taux BCE via Frankfurter).
- Journaux : `logs/turns-YYYY-MM-DD.jsonl` (timings, tokens, coût estimé, noms des outils — jamais le contenu) et `logs/jarvis.log`.

**Avertissement de l'auteur (README) :** « It works for me on one Windows 11 laptop, so expect rough edges. I'd like to port it to a Raspberry Pi eventually. » L'auteur se décrit comme sans formation de programmeur (« Claude Code wrote this under my direction », `README.md`). Version `0.1.0`.

### 2.2 Architecture générale et flux de bout en bout

**Architecture en paquet Python structuré** (62 fichiers Python/HTML/Markdown dans `jarvis/`, hors `__pycache__`) :

- **Point d'entrée** : `jarvis/__main__.py` — `python -m jarvis`. Analyse les arguments, construit l'assistant, lance la boucle vocale (`run_voice`) ou textuelle (`run_text`), le HUD, les tâches de fond (`Jobs`, tick toutes les 30 s) et les minuteurs. Contient aussi le verrou d'instance unique Windows (mutex `Local\JarvisVoiceLoop`) et la salutation selon l'heure. Aucun script console déclaré dans `pyproject.toml` (`[project.scripts]` absent).
- **Cœur conversationnel** : `jarvis/assistant.py` — un tour = texte entré, phrases sorties en streaming. Gère les appels d'outils (max 3 rondes, `MAX_TOOL_ROUNDS = 3`), les réessais sur rate-limit/panne (délai 2 s, plafond 12 s), la déduplication des phrases, l'historique, le calcul du coût estimé, et la règle de sécurité « hold writes » (voir §2.7).
- **Bus d'événements interne** : `jarvis/events.py` — pub/sub (états `idle/listening/thinking/speaking`, texte entendu, phrases dites, niveau audio, cartes HUD, événement `watched`). Fonction `level_of()` : volume en échelle log (−60 dBFS → 0, −10 dBFS → 1).
- **Configuration** : `jarvis/config.py` — chargement de `config.toml`, puis fusion de `config.local.toml` s'il existe (fichier privé, ignoré par Git ; il surcharge `config.toml`), plus `.env`.
- **Texte parlé** : `jarvis/text.py` — `SentenceSplitter` : découpe le texte streamé en phrases parlables (gère les abréviations `Mr`, `Dr`, `etc.`) ; `clean_for_speech` retire markdown et URL.
- **Journalisation** : `jarvis/turnlog.py` — `TurnRecord` / `TurnLog` : une ligne JSON par tour dans `logs/turns-YYYY-MM-DD.jsonl` (timings, tokens, coût estimé, noms des outils — jamais le contenu ni l'audio).
- **Lanceur** : `jarvis/launcher.py` — raccourci du menu Démarrer (`--install-shortcut`) ; dessine l'icône « arc reactor » en code (numpy, sans bibliothèque d'images) aux tailles 256/64/48/32/24/16 ; boîte de message Windows en cas d'erreur sans console.

**Flux d'un tour :** déclenchement (F9 ou « Hey Jarvis ») → enregistrement → transcription (Whisper) → LLM avec outils (max 3 rondes) → streaming découpé en phrases → synthèse vocale par phrase (file `SpeechQueue`, pré-rendu possible) → lecture interruptible. Le HUD reflète chaque état en temps réel via WebSocket.

**Persona** (`jarvis/persona/jarvis.md`, texte brut) : majordome britannique formel et calme, « sir », humour sec, anglais britannique, réponses courtes (1–3 phrases), pas de markdown/listes/emoji (car parlé à voix haute), ne jamais inventer, ne jamais prétendre avoir fait ce qui n'a pas été fait ; blague récurrente « run diagnostics » → « All systems nominal, sir » sans citer de chiffres. `jarvis/persona/__init__.py` (`system_prompt()`) : lit `jarvis.md`, ajoute date/heure locale et la liste des 8 prochains jours (contournement documenté : les modèles se trompent dans le calcul des dates) ; fuseau `JARVIS_TZ` ou UTC.

### 2.3 Pipeline vocal

**Déclenchement — deux voies (`jarvis/__main__.py`, `run_voice`) :**
1. **Push-to-talk (par défaut) :** maintenir **F9** (configurable : `f8`, `scroll_lock`, une lettre — `audio/capture.py`, `parse_key`), parler, relâcher. Enregistrement mono int16 16 kHz, max 30 s (`max_record_seconds`) ; moins de 0,3 s = « too short ». F9 pendant qu'il parle l'interrompt (`speech.stop()`).
2. **Mot de réveil « Hey Jarvis »** (`jarvis/audio/wake.py`, openWakeWord ONNX) : écoute locale en continu ; modèles `melspectrogram.onnx`, `embedding_model.onnx`, `hey_jarvis_v0.1.onnx` (~4 Mo) dans `models/openwakeword`. Deux usages : « Hey Jarvis, <question> » en une fois, ou « Hey Jarvis » seul → il répond « Yes, sir? » puis écoute une fois. Fin d'énoncé après ~0,9 s de silence (max 12 s). La détection est suspendue pendant qu'il parle/pense/enregistre ; F9 reste prioritaire. Seuil configurable (`wake_threshold = 0.5`). Double contrôle : la transcription doit commencer par « hey Jarvis » (tolère `jervis`, `javis`, `travis`), sinon fausse alerte ignorée. Coût annoncé : ~4 % d'un cœur CPU (README).

**STT :** Groq Whisper (`whisper-large-v3-turbo`, `jarvis/stt/groq_whisper.py`, timeout 20 s, 1 seul réessai côté client) par défaut ; variante locale faster-whisper `base.en` (CPU int8, `beam_size=1`, `vad_filter=True` ; ~150 Mo téléchargés au premier usage). L'audio est converti en WAV **en mémoire** et n'est jamais écrit sur disque.

**LLM :** Groq `openai/gpt-oss-120b` par défaut (raisonnement `low`, sans raisonnement dans la réponse), ou OpenRouter, ou Claude Haiku 5.5 (`effort = "low"`, `thinking = "disabled"`). Réponses streamées, découpées en phrases par `jarvis/text.py` et envoyées à la parole au fur et à mesure. Plafond 200 tokens par réponse (400 avec données). Jusqu'à 3 rondes d'appels d'outils. Réessai unique sur rate-limit/panne (attente selon `Retry-After`, plafond 12 s, puis phrase d'excuse parlée).

**TTS :** Kokoro local (voix britannique `bm_daniel`, vitesse 1,05, langue `en-gb` ; autres voix britanniques : `bm_george`, `bm_lewis`, `bm_fable`), repli Piper (voix `en_GB-northern_english_male-medium`, la plus rapide selon la config), repli voix Windows SAPI (préfère une voix britannique masculine, puis britannique féminine, puis masculine ; « David » US par défaut sans le pack vocal UK). Effet `film` appliqué avant lecture (`jarvis/audio/effects.py` : filtre en peigne, écho 11 ms, trois réflexions précoces 23/37/53 ms, passe-haut ~180 Hz, normalisation des pics). `SpeechQueue` : rendu anticipé des phrases (`prefetch`/`prepare`), interruption possible.

**Latence — annoncée ou mesurable :**
- **Aucune latence de bout en bout annoncée** dans le README ou la config. **Non documenté** comme chiffre global.
- Éléments mesurables : Kokoro « 0.3–1.2 s per sentence » (commentaire dans `jarvis/tts/kokoro.py`) ; chaque tour journalise `record_s`, `transcribe_s`, `first_token_s`, `first_audio_s`, `total_s` (`jarvis/turnlog.py`) — donc mesurable a posteriori, non promis a priori.
- Contrainte documentée (README, « Using Claude ») : le palier gratuit Groq autorise 8 000 tokens/minute ; chaque question utilise ~1 600 tokens (3 000 si elle récupère des données), donc « a few quick questions in a row make Jarvis wait » (il dit qu'il est rate-limité et attend jusqu'à 12 s).
- Wake word : ~4 % d'un cœur ; HUD : 42–54 % d'un cœur et ~760 Mo en veille (voir §2.6).

**Autres modes :** `--text` (clavier, sans microphone), `--text --speak`, `--text --hud`. L'anneau du HUD (maintenu à la souris/doigt) équivaut à F9. Le widget répond sur place ; le HUD complet s'ouvre sur demande (« show me »).

### 2.4 Capacités et outils concrets

Chaque capacité est un **outil** déclaré au LLM (nom + description + schéma JSON), exécuté par un connecteur. **11 outils au total :** `check_email`, `find_embargoes`, `calendar`, `calendar_change`, `todo`, `timer`, `web_search`, `convert_currency`, `meal_plan`, `gym`, `briefing`.

| Capacité | Outil(s) | Fichier de preuve | Détail |
|---|---|---|---|
| Courriels (lecture seule) | `check_email`, `find_embargoes` | `jarvis/connectors/gmail.py` | Multi-comptes ; expéditeur, objet, heure, aperçu de 160 caractères ; filtre `gmail_query` par compte, jamais élargi ; notifications automatiques comptées, non listées par défaut ; recherche d'embargos (phrases sur l'embargo seulement, 14 jours par défaut, note quotidienne) ; cache 120 s ; carte HUD (comptes seulement) |
| Calendrier | `calendar`, `calendar_change` | `jarvis/connectors/calendar.py` | Lecture fusionnée de tous les calendriers + jours fériés UK ; ajout/déplacement/suppression **en deux temps** : proposition lue à voix haute, puis confirmation uniquement si le tour suivant est un « oui » clair (`is_clear_yes`) ; seuls les événements créés par Jarvis (`jarvis=1`) peuvent être déplacés/supprimés ; calendrier pro en lecture seule ; mention « Added by Jarvis. » |
| Tâches | `todo` | `jarvis/connectors/tasks.py` | Google Tasks (liste `@default`, aussi sur le téléphone) ; actions `add`, `list`, `done`, `move`, `undo`, `delete`, `confirm_delete` ; ajout/cochage/déplacement immédiats, `undo` du dernier changement ; suppression après « oui » ; rappel parlé 1 h avant une échéance avec heure (via minuteurs) ; note quotidienne des tâches dues/en retard |
| Minuteur & rappels | `timer` | `jarvis/skills/timers.py` | Compte à rebours (minutes) ou rappel à heure fixe ; max 20 actifs, max 1 semaine (durée) / 1 an ; persistant dans `data/timers.json` ; carillon + annonce vocale ; retards survenus pendant l'arrêt annoncés au démarrage |
| Recherche web | `web_search` | `jarvis/connectors/websearch.py` | Tavily ; actualités (semaine écoulée) ou général ; max 5 résultats, extraits de 320 caractères ; compteur mensuel local (`data/websearch_state.json`, limite 900/1 000) ; cache 10 min ; consigne de ne jamais mettre de données personnelles dans la requête |
| Conversion de devises | `convert_currency` | `jarvis/connectors/currency.py` | Taux quotidiens BCE via Frankfurter (gratuit, sans clé) ; ~30 devises majeures, **pas de crypto** ; taux du jour (fixé vers 16 h CET), pas un taux en direct ; taux historique possible |
| Plans de repas | `meal_plan` | `jarvis/connectors/meal_plan.py` | Google Sheets en lecture seule (un onglet par semaine, dates en série) ; seul le jour demandé est transmis au modèle ; recettes, listes d'épicerie et onglets de suivi jamais lus (sauf le journal de poids, pour openGym) ; carte HUD des repas du jour |
| Suivi de gym | `gym` | `jarvis/connectors/opengym.py` | openGym auto-hébergé (`http://127.0.0.1:8080`) : séance du jour, sessions récentes, progression par exercice (meilleure série, 1RM estimé par formule d'Epley), poids et rythme (moindres carrés sur 42 jours), enregistrement d'une pesée à la voix (+ `undo`) ; synchronisation des pesées de la feuille de repas toutes les 3 h ; gestion des conflits de révision (409, 3 réessais) ; apairage par code à 5 minutes (`--opengym-pair`) |
| Briefing du matin | `briefing` | `jarvis/connectors/briefing.py` | Première activation entre 5 h et 12 h (ou « brief me ») : calendrier, tâches, repas, gym, courriels, minuteurs — 3 à 5 phrases courtes ; préparé en arrière-plan (cache 15 min) ; notes quotidiennes des autres connecteurs fusionnées |
| Contrôle du PC Windows | — | `jarvis/__main__.py`, `jarvis/launcher.py`, `jarvis/hud/window.py` | **Très limité** : raccourci du menu Démarrer / barre des tâches, fenêtre HUD, interruption par F9, instance unique. **Aucun outil** pour lancer des applications, contrôler le volume, éteindre, ouvrir des fichiers ou taper au clavier — **non documenté / absent** |
| Domotique / maison connectée | — | — | **Absente. Non documenté.** Aucun module, aucune dépendance, aucun outil |
| Musique / lecture audio | — | — | **Absente. Non documenté.** Aucun outil de lecture musicale (seuls le carillon et la voix existent) |
| Messages (SMS, WhatsApp, Messenger…) | — | — | **Absents. Non documenté.** Aucun connecteur de messagerie |
| Fichiers locaux | — | — | **Absent.** La persona dit explicitement : « If no tool covers something (his files or the internet, say), say you have no access » (`jarvis/persona/jarvis.md`). Le seul accès fichier est la lecture des feuilles Google Sheets et du catalogue d'exercices openGym |
| Automatisations / rappels planifiés | partiel | `jarvis/skills/timers.py`, `jarvis/connectors/briefing.py` | Minuteur/rappels + briefing matinal + notes quotidiennes (embargos, tâches dues, rythme de poids). **Aucun planificateur général** (pas de cron, pas de routines « si… alors… »), **non documenté** au-delà de ces cas |

**Modules du paquet `jarvis/` (sélection) :**
- `audio/` : `capture.py` (enregistrement mono int16, 16 kHz, blocs de 40 ms qui alimentent l'anneau du HUD, audio gardé en mémoire ; `PushToTalk` via pynput, sans droits admin), `wake.py` (voir §2.3), `playback.py` (lecture par blocs de 50 ms, interruptible), `chime.py` (carillon synthétisé : deux notes, 880 Hz puis 1318,5 Hz, sans fichier son), `effects.py` (effet `film`).
- `stt/` : `groq_whisper.py`, `local_whisper.py` (voir §2.3).
- `tts/` : `kokoro.py`, `piper.py`, `sapi.py` (voir §2.3).
- `llm/` : `openai_compat.py` (Groq/OpenRouter, streaming, `max_retries=0`, timeout 30 s), `anthropic_backend.py` (API Messages de Claude, `effort` et `thinking` configurables, ligne de refus polie en cas de `stop_reason == "refusal"`), `base.py` (types partagés, exceptions `LLMError`, `RateLimited`, `Unavailable`, `AuthFailed`).
- `connectors/` : `base.py` (`Tool`, `DailyNote`, `untrusted()`, `is_clear_yes()`), `google.py` (OAuth multi-comptes, client « Desktop app », `tokens/client_secret.json`, un jeton par compte `tokens/google-<nom>.json`, scopes `gmail.readonly`, `calendar.readonly`, `calendar.events`, `spreadsheets.readonly`, `tasks`), `web.py` (helpers HTTP sans dépendance, user-agent `Jarvis/0.1`, plafond 3 Mo).
- `hud/` : `server.py` (serveur aiohttp sur `127.0.0.1` uniquement, routes `/`, `/widget`, `/ws` ; vérification des en-têtes Host/Origin, anti DNS-rebinding ; file d'événements de 256 par client), `static/index.html` (956 lignes, page HUD autonome, sans étape de build, hors ligne ; anneau et effets adaptés de A.L.I.C.E., MIT, © 2026 Simon Shih), `static/widget.html`, `widget.py` (reconnaissance de « show me » **en code, avant le modèle**, aucun token), `window.py` (fenêtre pywebview/WebView2 en processus séparé, mode widget rond sans cadre, position mémorisée, raccourci global, menu clic droit « Quit Jarvis », code de sortie 3 si WebView2 indisponible, repli navigateur).

**`docs/` — point important : `docs/` ne contient aucun document écrit.** Il ne contient que deux captures d'écran (`docs/hud.png`, `docs/widget.png`, données de démonstration inventées). Il n'y a **aucun fichier d'architecture, aucun guide** : toute la documentation est dans `README.md` et dans les docstrings des modules.

**`scripts/` — un seul fichier :** `scripts/measure_hud_cpu.ps1` — mesure la CPU et la mémoire de la fenêtre HUD et du processus Jarvis sur 15 s. Référence inscrite (15 oct. 2026, portable de test, 16 cœurs logiques) : fenêtre HUD complète **42–54 % d'un cœur et ~760 Mo en veille** (87 % avant les correctifs d'inactivité) ; cœur Jarvis **~12 %**. C'est la seule mesure de performance chiffrée du dépôt.

**`tests/` — 18 fichiers (pytest) :** `test_assistant.py`, `test_backends.py`, `test_briefing.py`, `test_calendar.py`, `test_currency.py`, `test_gmail.py`, `test_hud.py`, `test_meal_plan.py`, `test_opengym.py`, `test_tasks.py`, `test_text_and_config.py`, `test_timers.py`, `test_voice.py`, `test_wake.py`, `test_websearch.py`, `test_widget.py`, `conftest.py` (fixture `cfg`, `JARVIS_TZ = "Europe/Lisbon"`). Les tests utilisent des faux clients ; aucun test d'intégration en conditions réelles (microphone, API Groq, compte Google) n'est présent dans la liste.

### 2.5 Mémoire et contexte

- **Mémoire conversationnelle :** `jarvis/memory/history.py` — les **10 derniers tours** (configurable, `history_turns`), **en RAM seulement**, effacée au redémarrage. Les résultats d'outils ne sont conservés que pour le tour en cours (« Tool results are used for this turn only: memory keeps just what was said », `jarvis/assistant.py`).
- **Aucune mémoire persistante :** pas de base de données, pas de vecteurs, pas de résumé des conversations passées, pas de profil utilisateur stocké (hormis la persona et la config). **Non documenté** : tout mécanisme d'apprentissage ou de souvenir entre sessions.
- **Contexte injecté à chaque tour :** prompt système = `jarvis/persona/jarvis.md` + date/heure locale + liste des 8 prochains jours + notes quotidiennes éventuelles + historique des 10 derniers tours + message de l'utilisateur.
- **État persistant (fichiers JSON locaux, gitignorés) :** `data/timers.json` (minuteurs), `data/gmail_state.json` (jour de mention des embargos), `data/tasks_state.json`, `data/briefing_state.json`, `data/websearch_state.json` (compteur mensuel), `data/opengym_sync.json` + `data/opengym_names.json`, `data/widget.json` (position du widget). Journaux : `logs/turns-YYYY-MM-DD.jsonl`, `logs/jarvis.log`, `logs/hud-window.log`.
- **Jetons :** `tokens/` (secret client Google + un jeton par compte + session openGym), gitignoré.

### 2.6 Planification et tâches en arrière-plan

- **Boucle de tâches (`jarvis/__main__.py`, classe `Jobs`) :** toutes les 30 s, chaque connecteur possédant `tick()` décide ce qui est dû ; l'arrivée d'une page HUD à l'écran déclenche un rafraîchissement immédiat. Les échecs sont journalisés, jamais fatals.
- **Ce que font les `tick()` :** Gmail prépare la note quotidienne d'embargos et rafraîchit la carte courriel (toutes les 10 min) ; calendrier et tâches rafraîchissent leurs cartes HUD ; plans de repas (toutes les 10 min et après minuit) ; briefing prépare son texte (cache 15 min, fenêtre 5 h–12 h) ; openGym renouvelle le jeton (vérifié quotidiennement), synchronise les pesées de la feuille (toutes les 3 h), prépare le rappel de séance et le contrôle de rythme hebdomadaire ; recherche web : aucun tick.
- **Minuteur (`jarvis/skills/timers.py`) :** thread d'alarme dédié, vérification toutes les 30 s au plus ; les échéances manquées pendant l'arrêt sont annoncées au démarrage.
- **Ce qui n'existe pas :** aucun planificateur de type cron, aucune tâche récurrente configurable par l'utilisateur, aucune automatisation déclenchée par un événement externe (courriel entrant, etc.) — les « daily notes » sont le seul mécanisme quasi planifié, et elles ne se déclenchent qu'au premier tour de la journée. **Non documenté** au-delà de ce qui précède.

### 2.7 Sécurité et vie privée

**Ce qui reste local (README, « Privacy ») :** le mot de réveil (microphone écouté localement jusqu'à « Hey Jarvis »), la voix (Kokoro/Piper/SAPI), le HUD. Aucun audio ni transcription écrit sur disque ; les journaux ne contiennent que timings, nombres de tokens et noms d'outils.

**Ce qui part en infonuagique :** la transcription (Groq Whisper par défaut ; `local` hors ligne possible) et le LLM. Quand une question exige des données, l'extrait pertinent part aussi vers le LLM. Pour le courriel : expéditeur, objet, heure et court aperçu Gmail — jamais le message entier — et chaque compte a un filtre Gmail limitant la visibilité.

**Avertissement explicite du README :** « This is **not** a local-LLM setup » ; « Free tiers may use your prompts for training. Only use dummy data with Groq » ; pour un usage réel, passer à Anthropic (Claude Haiku) et lire les conditions du fournisseur. Groq est le défaut « for testing with dummy data only ».

**Protections contre l'injection indirecte (point fort, bien conçu) :**
- `jarvis/connectors/base.py`, `untrusted()` : tout contenu externe (courriel, pages web, feuilles, invitations) est enveloppé dans `<untrusted_data source="…">` avec l'instruction de le résumer sans jamais suivre d'instructions internes.
- `jarvis/assistant.py` + `[safety] hold_writes = true` : dès qu'un tour a lu du texte externe, toute écriture de données (tâches, pesées) est bloquée pour ce tour ; l'utilisateur doit redemander séparément. Les minuteurs et les changements de calendrier (qui exigent déjà un « oui » oral) ne sont pas bloqués.
- Confirmations **en code, pas laissées au modèle** : `is_clear_yes()` (oui court et non qualifié, max 8 mots ; « yes, but make it 4 » ne compte pas) et vérification du numéro de tour (`current_turn`) ; le texte d'un courriel ne peut jamais compter comme un « oui ». Le calendrier exige en outre que la proposition date du tour précédent.
- Gmail : le filtre du compte ne peut être que restreint, jamais élargi, par le modèle ; les catégories promotionnelles ne passent jamais le filtre.

**Accès demandés :** microphone (écoute locale permanente pour le wake word + enregistrement push-to-talk), haut-parleur, touche clavier globale F9 (pynput, sans droits admin), OAuth Google (scopes en lecture seule sauf `calendar.events` et `tasks`), accès réseau vers Groq/Anthropic/OpenRouter, Tavily, Frankfurter, Google APIs, openGym local. HUD lié à `127.0.0.1` seulement, avec contrôle Host/Origin (anti DNS-rebinding) ; le widget/HUD ne peut pas piloter le microphone depuis un autre site.

**Secrets :** `.env` (clés API), `tokens/` (secret client OAuth + jetons), `config.local.toml` — tous gitignorés (`.gitignore`). Le README prévient de ne jamais partager `client_secret.json` et de révoquer l'accès via myaccount.google.com/permissions.

### 2.8 Prérequis, coûts, installation

- **OS : Windows 11** (le README dit « for Windows » ; l'auteur précise « one Windows 11 laptop »). Dépendances Windows-only : `pywin32`, `pywebview` (Edge WebView2, livré avec Windows 11), SAPI, mutex d'instance unique, raccourci `.lnk`. **Aucun support macOS/Linux/Raspberry Pi** — le portage vers Raspberry Pi est un souhait futur explicite de l'auteur. **Non documenté** : version minimale de Windows 10.
- **Matériel :** un portable Windows 11 avec microphone et haut-parleurs. Aucune exigence CPU/GPU chiffrée, hormis les mesures du §2.3/§2.4 (HUD ~760 Mo en veille ; wake word ~4 % d'un cœur). **Non documenté** : RAM minimale, espace disque total.
- **Logiciels :** Python 3.10+ et Git ; PowerShell.
- **Comptes :** compte Groq (gratuit) et/ou Anthropic (payant), compte Tavily (gratuit, sans carte) ; projet Google Cloud personnel (Gmail + Calendar + Sheets + Tasks APIs) avec application OAuth « Desktop app » non publiée (mode Testing : reconnexion tous les 7 jours, `--google-login all`) ; compte openGym auto-hébergé (optionnel, Docker sur le PC).
- **Clés :** au minimum `GROQ_API_KEY` (ou `ANTHROPIC_API_KEY`) ; `TAVILY_API_KEY` pour la recherche web ; `OPENROUTER_API_KEY` optionnelle. (`.env.example` : 5 variables, toutes facultatives selon le fournisseur choisi, plus `JARVIS_TZ`, fuseau IANA, défaut UTC.)
- **Téléchargements de modèles :** environnement virtuel ~200 Mo ; Kokoro ~120 Mo ; Piper ~60 Mo ; openWakeWord ~4 Mo ; faster-whisper `base.en` ~150 Mo (si STT local).
- **Coûts :** Groq palier gratuit (8 000 tokens/min ; ~1 600 tokens/question) ; Tavily gratuit 1 000 recherches/mois (Jarvis s'arrête à 900) ; Claude Haiku ~1/20e de penny par question selon le README (0,10 $ / 0,50 $ par million de tokens) ; Frankfurter gratuit ; Google APIs gratuites dans cet usage ; openGym auto-hébergé (coût nul, hors électricité). **Aucun abonnement** au projet lui-même (MIT, gratuit).
- **Licence :** code MIT (`LICENSE`, © 2026 tanishvbuk). Dépendances aux licences distinctes : Kokoro-82M Apache-2.0, kokoro-onnx MIT (avec espeak-ng GPL-3.0), Piper GPL-3.0, HUD adapté de A.L.I.C.E. (MIT). « Jarvis » est un personnage Marvel : projet personnel de fan, non affilié à Marvel/Disney (README, « Licences »).
- **Installation (README, « Setup on Windows ») :** Python 3.10+ et Git ; `python -m venv .venv` puis `pip install -e ".[dev]"` (~200 Mo) ; copier `.env.example` vers `.env` et y coller `GROQ_API_KEY` ; télécharger les voix Kokoro (~120 Mo) et Piper (~60 Mo) ; télécharger les modèles openWakeWord (~4 Mo) dans `models/openwakeword`.
- **Configuration (`config.toml`, sections) :** `[llm]` (fournisseur, `max_tokens`, `history_turns`, `max_turns_per_session`) ; `[llm.providers.groq/openrouter/anthropic]` (modèles, prix) ; `[stt]` (fournisseur, modèles, langue `en`) ; `[tts]` (fournisseur, voix, vitesse, effet `film`) ; `[audio]` (touche F9, 16 kHz, max 30 s, wake word, seuil) ; `[hud]` (port 8765, fenêtre `widget`) ; `[widget]` (orbe 320 px, raccourci `ctrl+alt+j`) ; `[google]`, `[gmail]`, `[meal_plan]`, `[calendar]`, `[tasks]`, `[safety]` (`hold_writes = true`), `[currency]`, `[websearch]` (limite 900/mois), `[briefing]` (5 h–12 h), `[opengym]` (127.0.0.1:8080, sync 3 h), `[timers]`, `[logging]`. `config.local.example.toml` : comptes Google `personal`/`work`, plans de repas (`sheet_id`), openGym. Le compte `shop` cité dans le README n'y figure pas (**non documenté** dans l'exemple de configuration).
- **Dépendances (`pyproject.toml`) :** `openai>=3.27`, `anthropic>=1.13`, `sounddevice>=0.5`, `numpy>=2.0`, `pynput>=1.8`, `pywin32>=306`, `piper-tts>=1.8`, `kokoro-onnx>=0.6`, `python-dotenv>=1.0`, `aiohttp>=3.9`, `pywebview>=5.0`, `tzdata`, `google-api-python-client>=2.100`, `google-auth-oauthlib>=1.2`, `openwakeword>=0.6`, `tomli>=2.0` ; optionnelles : `local = ["faster-whisper>=1.0"]`, `dev = ["pytest>=8"]`.

### 2.9 Limites connues

- « It works for me on one Windows 11 laptop, so expect rough edges » (README). Projet solo, version 0.1.0, écrit sous la direction de Claude Code par un auteur sans formation de programmeur.
- **Pas de LLM local** (README, « Privacy ») : STT et LLM partent en infonuagique par défaut ; le palier gratuit Groq peut utiliser les prompts pour l'entraînement — données fictives seulement.
- **Groq gratuit limité** : 8 000 tokens/min ; quelques questions rapides d'affilée déclenchent l'attente de rate-limit (jusqu'à 12 s).
- **Google en mode Testing** : reconnexion tous les 7 jours (`--google-login all`) ; application non vérifiée (avertissement Google à contourner par « Continuer ») ; un compte Google Workspace peut être bloqué par son administrateur.
- **Calendrier :** seuls les événements créés par Jarvis peuvent être déplacés/supprimés ; le calendrier pro est en lecture seule ; un changement de périmètre exige une nouvelle connexion.
- **Gmail :** lecture seule (ni envoi, ni suppression, ni étiquetage) ; aperçu seulement, jamais le message entier ; les promotions ne passent jamais le filtre.
- **Google Tasks :** ne conserve que la date d'échéance (l'heure est écrite dans les notes).
- **Plans de repas :** si la semaine n'a pas été ajoutée, Jarvis dit simplement qu'elle n'y est pas ; la détection de date suppose une structure d'onglet hebdomadaire.
- **Voix :** si Kokoro et Piper échouent, repli sur la voix Windows (« David » US sauf si le pack vocal anglais UK est installé) ; Kokoro prend 0,3–1,2 s par phrase.
- **Mot de réveil :** dire « *Hey* Jarvis » — « Jarvis » seul est souvent manqué ; sensibilité à régler (`wake_threshold`) si la télévision le déclenche.
- **HUD :** coûteux en ressources (42–54 % d'un cœur, ~760 Mo en veille, avant correctifs 87 % d'un cœur) ; la fenêtre transparente ne fonctionnait pas avec WebView2 sur certains portables (`transparent = false` par défaut) ; le HUD n'est joignable que depuis l'ordinateur lui-même.
- **openGym :** nécessite Docker Desktop en cours d'exécution sur le PC ; la synchronisation des pesées peut signaler des dates incohérentes sans les copier.
- **Recherche web :** ne lit jamais une page (extraits Tavily seulement), ne suit aucun lien, ne peut pas agir sur une page.
- **Devises :** taux quotidien officiel, pas un taux en direct ; ~30 devises, pas de crypto.
- **Langue :** anglais uniquement — STT `language = "en"`, voix `en-gb`, persona en anglais britannique, dates en anglais. **Aucune prise en charge du français documentée** (ni STT `fr`, ni voix française, ni persona française) : point majeur pour une adaptation francophone.
- **Absences (non documenté = absent du code) :** domotique, musique, messagerie (SMS/WhatsApp), contrôle d'applications ou de fichiers locaux, mémoire entre sessions, planificateur général, notifications push, application mobile (openGym a une appli, Jarvis n'en a pas), multi-utilisateur (assistant « to one man », « sir »), portage Raspberry Pi (souhait futur seulement).
- **Tests :** couverture par tests unitaires avec faux clients ; aucun test d'intégration en conditions réelles listé.

---

## 3. Synthèse comparative

| Critère | Dépôt A — Julian-Ivanov | Dépôt B — tanishvbuk | Équivalent Muse de Julien |
|---|---|---|---|
| Idée centrale | Lancer une session de travail à voix haute, voir l'écran, piloter le navigateur | Un majordome vocal discret, toujours présent, branché à Google | Carson (agent) + Muse Code (outillage) + pont GitHub |
| Déclenchement | Double-clap (lancement), puis écoute continue | F9 (push-to-talk) ou « Hey Jarvis » (wake word local) | Voix temps réel sur appel ; **pas de mot de réveil, pas de serveur local toujours allumé** |
| STT | Web Speech API Chrome, allemand | Whisper Groq ou local, anglais | Voix temps réel Muse (FR/EN) |
| TTS | ElevenLabs cloud, voix allemande | Kokoro/Piper/SAPI en local, voix britannique | Voix temps réel Muse ; balado narré (voix fixe) |
| Cerveau | Claude Haiku, actions par balises `[ACTION:...]` | Groq / Claude Haiku / OpenRouter, 11 outils déclarés | Carson (Muse) |
| Interface | Page web + orbe (4 états) sur `localhost:8340` | HUD local `127.0.0.1:8765` + widget rond | « Chez Carson », tableau de bord du livre (web) |
| Mémoire | 16 messages en RAM, effacée à la déconnexion | 10 tours en RAM, effacée au redémarrage | **Mémoire persistante Muse (supérieure aux deux)** |
| Courriel / calendrier / tâches | Absents (sauf lecture `Tasks.md` Obsidian) | Gmail lecture seule, calendrier lecture+écriture confirmée, Google Tasks | **Déjà couverts par Carson (Gmail, Google Calendar, rappels)** |
| Minuteur / rappels | Absents | Minuteur persistant + rappel 1 h avant échéance | Rappels par crons Muse ; pas de minuteur local |
| Recherche web | DuckDuckGo + lecture de page (Playwright) | Tavily, extraits seulement | Recherche web Muse ; pas de lecture de page locale |
| Yeux et mains | Capture d'écran + Vision ; navigateur contrôlé ; lancement d'apps + quadrants | Aucun contrôle du PC | **Carson ne voit pas l'écran et ne contrôle pas le PC** |
| Planification | Auto-start au login seulement | Boucle `Jobs` toutes les 30 s, notes quotidiennes, briefing | Crons et veilles Muse |
| Sécurité | Serveur `0.0.0.0:8340` sans auth ; clés en clair | `untrusted()` + `hold_writes` + confirmations en code ; HUD `127.0.0.1` | Connecteurs Muse gérés ; secrets hors du dépôt |
| Langue | Allemand seulement | Anglais seulement | **Français (prioritaire), anglais** |
| OS | Windows 10/11 | Windows 11 seulement | Windows (PC de Julien) ; pont GitHub multiplateforme |
| Coût d'usage | Anthropic ~0,25 $/1M tokens + ElevenLabs (10 000 car./mois gratuits) | Groq gratuit (8 000 tokens/min) + Tavily gratuit (1 000/mois) + Haiku ~1/20e de penny/question | Abonnements Muse envisagés (Power 20 $ US/mois + Code 5 $ US/mois, séparés) |
| Maturité | Démo personnelle, avril 2026, pas de tests, pas de licence en fichier | v0.1.0, oct. 2026, 18 fichiers de tests unitaires, licence MIT | Pont GitHub créé le 21 nov. 2026, exploration seulement |
| Licence | MIT annoncée au README, **aucun fichier LICENSE** (`license: null`) | MIT (`LICENSE` présent) | Dépôt privé |

**Ce que les deux dépôts ne font ni l'un ni l'autre :** domotique, musique (sauf lancement d'un morceau Spotify au démarrage, dépôt A), messagerie (SMS/WhatsApp/Messenger), mémoire persistante entre sessions, planificateur général (cron/routines), notifications push, application mobile, multi-utilisateur, français.

---

## 4. Plan détaillé, capability par capability

Pour chaque bloc : ce que ça fait, ce que ça exige, l'équivalent Muse, et une recommandation.

**Légende des recommandations :**
- **Déjà couvert** — Carson / Muse le fait déjà, ne pas reconstruire.
- **Intégrer** — reprendre le patron ou le code, adapté au français et à Muse.
- **Adapter** — bonne idée, mais à repenser pour le contexte de Julien (langue, OS, pont GitHub).
- **Plus tard** — intéressant, mais pas prioritaire ; à revisiter après les fondations.
- **Écarter** — ne pas intégrer (doublon, besoin absent, ou trop spécifique à l'auteur).

### 4.1 Voix et déclenchement

| # | Capacité | Source | Ce que ça fait | Ce que ça exige | Équivalent Muse | Recommandation |
|---|---|---|---|---|---|---|
| 1 | Conversation vocale temps réel | A + B | Parler librement, réponses parlées | Micro, haut-parleurs, STT + TTS + LLM | **Voix temps réel Carson (FR/EN)** | **Déjà couvert** |
| 2 | Mot de réveil local « Hey Jarvis » | B (`audio/wake.py`, openWakeWord) | Écoute locale en continu, double vérification par transcription, ~4 % d'un cœur | Modèles ONNX ~4 Mo, micro toujours ouvert, Windows | Aucun (pas de mot de réveil côté Muse) | **Adapter — plus tard.** Modèle anglophone : il faudrait un modèle français (« Hey Carson ») ou un autre déclencheur. À vérifier : disponibilité d'un modèle openWakeWord français. |
| 3 | Double-clap (lancement de session) | A (`scripts/clap-trigger.py`) | Deux claps (0,1–1,2 s) lancent la session complète, puis le processus s'arrête | Micro, `sounddevice` + `numpy` (absents de `requirements.txt` !), Windows | Aucun | **Adapter — plus tard.** Geste amusant, peu coûteux, mais à usage unique et fragile (seuil RMS à régler). |
| 4 | Push-to-talk (F9) | B (`audio/capture.py`) | Maintenir une touche pour parler, relâcher pour envoyer ; F9 interrompt la réponse | Touche globale (pynput, sans droits admin), Windows | Aucun | **Adapter — plus tard.** Simple et fiable ; utile quand le micro est ouvert en continu. |
| 5 | STT Whisper (Groq ou local) | B (`stt/`) | Transcription, cloud (20 s timeout) ou locale (faster-whisper `base.en`, CPU int8, ~150 Mo) | Clé Groq (gratuit) ou CPU local ; anglais seulement | Voix temps réel Muse | **Déjà couvert** côté Muse ; la variante locale reste une option vie privée — **plus tard**. |
| 6 | TTS local (Kokoro / Piper / SAPI) | B (`tts/`) | Voix britannique locale, chaîne de repli Kokoro → Piper → SAPI, effet « voice in the walls », 0,3–1,2 s par phrase | Modèles ~120 Mo (Kokoro) + ~60 Mo (Piper), Windows | Voix temps réel Muse ; balado narré | **Adapter — à vérifier.** C'est la brique qui rendrait possible la lecture des résumés Carson à voix haute à la maison (l'idée qui plaît à Julien). Point à vérifier : voix **française** disponible (Kokoro/Piper) — les deux dépôts sont anglophones/allemands. |
| 7 | TTS cloud ElevenLabs | A (`server.py`) | Voix réaliste, modèle `eleven_turbo_v2_5`, découpage par phrases >250 car. | Clé ElevenLabs, ~10 000 car./mois gratuits | Voix temps réel Muse | **Écarter.** Coût récurrent, cloud, doublon avec la voix Muse. |
| 8 | Persona majordome (ton, règles) | A + B (`server.py`, `persona/jarvis.md`) | Ton sec et poli, réponses courtes (1–3 phrases), « sir », pas de markdown à voix haute, ne jamais inventer | Un fichier texte de prompt système | Carson a déjà son ton (léger, direct, français) | **Adapter — plus tard.** Une persona Jarvis locale en français serait à écrire ; le ton existe déjà côté Carson. |

### 4.2 Données et outils quotidiens

| # | Capacité | Source | Ce que ça fait | Ce que ça exige | Équivalent Muse | Recommandation |
|---|---|---|---|---|---|---|
| 9 | Météo au démarrage | A (`server.py`, wttr.in) | Température, ressenti, humidité, vent, sans clé API | Accès à `wttr.in` | Résumés marchés / météo via Carson | **Déjà couvert — écarter.** |
| 10 | Tâches Obsidian (lecture `Tasks.md`) | A (`server.py`) | Lit les cases `- [ ]` non cochées au démarrage | Coffre Obsidian local, chemin en dur | Aucun (Julien n'utilise pas Obsidian d'après ce qui est connu) | **Écarter** sauf si Julien utilise Obsidian — à confirmer. |
| 11 | Google Tasks | B (`connectors/tasks.py`) | Ajouter, lister, cocher, déplacer, annuler, supprimer (après « oui ») | Compte Google, OAuth, scope `tasks` | Rappels et suivis via crons Muse ; pas de Google Tasks natif | **Écarter.** Doublon fonctionnel avec les rappels Carson. |
| 12 | Calendrier Google (lecture + écriture confirmée) | B (`connectors/calendar.py`) | Lecture fusionnée multi-comptes ; ajout/déplacement/suppression en deux temps, seuls les événements créés par Jarvis sont modifiables | Compte Google, OAuth, scopes calendrier | **Google Calendar via Carson (lecture + création d'événements)** | **Déjà couvert — écarter.** |
| 13 | Gmail (lecture seule, multi-comptes) | B (`connectors/gmail.py`) | Expéditeur, objet, heure, aperçu 160 car., filtre par compte, cache 120 s | Compte Google, OAuth, scope `gmail.readonly` | **Gmail via Carson** | **Déjà couvert — écarter.** |
| 14 | Recherche d'embargos dans les courriels | B (`find_embargoes`) | Repère les phrases sur l'embargo (14 jours), note quotidienne | Gmail (voir 13) | Aucun | **Écarter.** Besoin très spécifique à l'auteur. |
| 15 | Recherche web (Tavily, extraits) | B (`connectors/websearch.py`) | Actualités ou général, max 5 résultats, extraits 320 car., limite 900/1 000 par mois | Clé Tavily (gratuite, sans carte) | Recherche web Muse | **Déjà couvert — écarter.** |
| 16 | Recherche web + lecture de page (DuckDuckGo + Playwright) | A (`browser_tools.py`) | Recherche, clic du 1er résultat, extraction du texte (3 000 car.), visite directe (5 000 car.) | Playwright + Chromium, Windows | Recherche web Muse (sans lecture de page locale) | **Adapter — plus tard.** La lecture de page complète est un vrai plus pour un Jarvis local ; fragilité connue (1er résultat sans vérification, pages jamais fermées). |
| 17 | Actualités mondiales (worldmonitor.app) | A (`browser_tools.py`) | Ouvre le site, lit le texte (4 000 car.), résume | Accès à `worldmonitor.app` | Résumés marchés + balado Business News | **Déjà couvert — écarter.** |
| 18 | Conversion de devises (BCE via Frankfurter) | B (`connectors/currency.py`) | ~30 devises, taux du jour (pas en direct), pas de crypto | Aucune clé, gratuit | Carson peut convertir | **Déjà couvert — écarter.** |
| 19 | Plans de repas (Google Sheets) | B (`connectors/meal_plan.py`) | Lecture seule, un onglet par semaine, carte HUD du jour | Feuille Google structurée, OAuth Sheets | Aucun | **Écarter.** Pas un besoin exprimé. |
| 20 | Suivi de gym (openGym auto-hébergé) | B (`connectors/opengym.py`) | Séance du jour, progression, 1RM (Epley), pesée à la voix + `undo`, sync 3 h | openGym auto-hébergé (Docker), `http://127.0.0.1:8080` | **App d'entraînement Android de Julien (en pause)** | **Écarter.** Doublon avec son app d'entraînement ; openGym exigerait Docker en continu. |

### 4.3 Temps, rappels et routines

| # | Capacité | Source | Ce que ça fait | Ce que ça exige | Équivalent Muse | Recommandation |
|---|---|---|---|---|---|---|
| 21 | Minuteur et rappels persistants | B (`skills/timers.py`) | Compte à rebours ou heure fixe, max 20 actifs, persistant (`data/timers.json`), carillon + annonce, retards annoncés au démarrage | Fichier JSON local, thread d'alarme | Rappels par crons Muse (ex. Dre Désiel, stationnement) | **Adapter.** Le minuteur local persistant est un vrai complément aux rappels Carson (qui sont planifiés, pas déclenchés à la voix). Candidat pour une première brique locale. |
| 22 | Briefing du matin | B (`connectors/briefing.py`) | Première activation 5 h–12 h : calendrier, tâches, repas, gym, courriels, minuteurs — 3 à 5 phrases ; cache 15 min | Les connecteurs Google (voir 11–13) | **Résumé marchés 7h30 + balado Business News** | **Déjà couvert — écarter** (ou **adapter** uniquement comme version locale lue à voix haute, voir bloc 6). |
| 23 | Notes quotidiennes (DailyNote) | B (`connectors/base.py`) | Mention une fois par jour (embargos, tâches dues, rythme de poids) | État JSON local | Veilles et résumés Muse | **Adapter — plus tard.** Le patron « une mention par jour, pas plus » est utile contre le bruit. |
| 24 | Boucle de tâches de fond (tick 30 s) | B (`__main__.py`, `Jobs`) | Chaque connecteur rafraîchit ses cartes / prépare ses notes ; échecs journalisés, jamais fatals | Processus Python en continu | Crons et veilles Muse | **Adapter — plus tard.** C'est le patron d'un futur serveur local toujours allumé — mais Julien n'a pas de serveur local toujours allumé aujourd'hui (limite connue). |
| 25 | Auto-start au login Windows | A (README/SETUP) | Lance le double-clap au login via le Planificateur de tâches | Windows, Planificateur de tâches | Aucun | **Adapter — plus tard.** Simple et utile quand le Jarvis local existera. |

### 4.4 Yeux, mains et interface locale

| # | Capacité | Source | Ce que ça fait | Ce que ça exige | Équivalent Muse | Recommandation |
|---|---|---|---|---|---|---|
| 26 | Vision d'écran (capture + Claude Vision) | A (`screen_capture.py`) | Capture tout l'écran, description en 2–3 phrases par Claude Haiku | Anthropic, écran ; **écran complet envoyé au cloud** | **Carson ne voit pas l'écran** | **Adapter — plus tard.** Candidat fort : c'est exactement une limite connue de Carson. À durcir : capture ciblée (fenêtre, région), jamais d'écran complet avec données sensibles, consentement explicite à chaque capture. |
| 27 | Contrôle du navigateur (Playwright visible) | A (`browser_tools.py`) | Naviguer, cliquer, lire des pages, ouvrir des URL, ramener Chromium au premier plan | Playwright + Chromium, Windows | **Carson ne contrôle pas le PC** | **Adapter — plus tard.** Candidat fort avec la vision d'écran : les « mains » locales qui manquent à Carson. |
| 28 | Lancement d'applications + fenêtres en quadrants | A (`scripts/launch-session.ps1`) | Lance serveur, Spotify, VS Code, apps configurées, Chrome ; range les fenêtres (VS Code, Obsidian, Chrome, Spotify) | PowerShell, Win32 API, Windows | Aucun | **Adapter — plus tard.** Séquence de lancement de session agréable ; Windows seulement. |
| 29 | HUD local + widget (anneau, cartes, transcription) | B (`hud/`) | Anneau coloré selon l'état, transcription, horloge, repas, minuteurs, calendrier ; widget rond ; serveur `127.0.0.1:8765` | pywebview / WebView2, ~760 Mo en veille, 42–54 % d'un cœur | « Chez Carson » et tableau de bord (web) | **Adapter — plus tard.** Beau, mais coûteux en ressources ; le tableau de bord web existe déjà. À envisager en version légère. |
| 30 | Orbe web + états colorés | A (`frontend/`) | Page `localhost:8340`, orbe 4 états (idle/listening/thinking/speaking), transcription affichée | Chrome, serveur FastAPI | « Chez Carson » (web) | **Écarter.** Doublon avec les interfaces web existantes. |

### 4.5 Fondations transverses

| # | Capacité | Source | Ce que ça fait | Ce que ça exige | Équivalent Muse | Recommandation |
|---|---|---|---|---|---|---|
| 31 | Mémoire conversationnelle en RAM (10–16 messages) | A + B | Historique court, effacé à la déconnexion / au redémarrage | Rien | **Mémoire persistante Muse (supérieure)** | **Écarter.** Les deux modèles sont inférieurs à la mémoire de Carson. |
| 32 | Sécurité anti-injection : données externes enveloppées + blocage des écritures + confirmations en code | B (`connectors/base.py`, `assistant.py`) | `<untrusted_data>` autour des contenus externes ; `hold_writes` bloque les écritures après lecture externe ; `is_clear_yes()` (oui court, max 8 mots) ; vérification du numéro de tour | Discipline de code, aucun coût | Règles de prudence de Carson | **Intégrer comme principe.** Le patron le plus précieux du dépôt B : à reprendre tel quel dans tout outil local qui écrit (calendrier, tâches, fichiers). Coût nul, valeur élevée. |
| 33 | Journalisation par tour (timings, tokens, coût — sans contenu) | B (`turnlog.py`) | Une ligne JSON par tour dans `logs/turns-YYYY-MM-DD.jsonl` | Dossier `logs/` | Journaux et registres Muse | **Adapter — plus tard.** Sobre et utile pour mesurer la latence et les coûts locaux. |
| 34 | Serveur local (FastAPI / aiohttp) | A (`server.py`) + B (`hud/server.py`) | Sert l'interface, orchestre les outils, WebSocket temps réel | Python, port local, machine allumée | Pont GitHub (déjà en place) ; pas de serveur local | **Adapter — plus tard.** L'architecture de référence pour le jour où un serveur local toujours allumé existera (mini-PC envisagé, rien acheté). En attendant, le pont GitHub suffit. Ne pas exposer sur `0.0.0.0` sans authentification (faille du dépôt A) : `127.0.0.1` seulement, comme le dépôt B. |
| 35 | Configuration par fichiers (TOML/JSON + `.env`) | A + B | Paramètres, voix, seuils, comptes, secrets séparés du code | Fichiers locaux, `.gitignore` | Dépôt `Jarvis-Muse` (`config/`) | **Intégrer.** Déjà la structure prévue (`config/`) ; reprendre la séparation config publique / config locale privée / secrets en `.env`. |
| 36 | Domotique | Absente des deux | — | — | Aucune | **Plus tard / hors scope.** Ni l'un ni l'autre ne couvre la maison connectée ; à construire séparément (ex. Home Assistant) si le besoin apparaît. |
| 37 | Musique (contrôle de lecture) | A : lancement d'un morceau seulement ; B : absente | Ouvrir un URI `spotify:track:...` au démarrage | Compte Spotify | Aucun | **Écarter.** Lancement seulement, aucun contrôle. |
| 38 | Messagerie (SMS, WhatsApp, Messenger) | Absente des deux | — | — | Messenger autorisé côté Muse ; SMS interdits (choix de Julien) | **Écarter.** |
| 39 | Accès aux fichiers locaux | A : lecture `Tasks.md` seulement ; B : absent | Lire un fichier précis | Chemin local | Muse Code (lecture/écriture locale, via Julien) | **Adapter — plus tard**, via Muse Code et le pont GitHub, pas via un nouveau connecteur. |

---

## 5. Décisions à cocher pour Julien

Cocher chaque bloc : **Oui / Non / Plus tard**. (Cases vides = à décider.)

### Bloc 1 — Fondations (à décider en premier)
- [ ] **Règles de sécurité (bloc 32)** : adopter le patron `untrusted()` + `hold_writes` + confirmation orale vérifiée en code pour tout outil local qui écrit. — Recommandation : **Oui**.
- [ ] **Configuration séparée (bloc 35)** : config publique / config locale privée / secrets en `.env`, dans `config/` du dépôt. — Recommandation : **Oui**.
- [ ] **Journalisation par tour sans contenu (bloc 33)** : logs locaux sobres (timings, tokens, coûts). — Recommandation : **Oui, plus tard**.

### Bloc 2 — Voix locale
- [ ] **TTS locale française (bloc 6)** : voix hors ligne pour lire les résumés Carson à voix haute à la maison — après vérification qu'une voix française existe (Kokoro/Piper). — Recommandation : **Oui, à vérifier**.
- [ ] **Mot de réveil (bloc 2)** : « Hey Carson » ou autre déclencheur local (modèle français à trouver). — Recommandation : **Plus tard**.
- [ ] **Double-clap (bloc 3)** : geste de lancement de session. — Recommandation : **Plus tard**.
- [ ] **Push-to-talk F9 (bloc 4)** : touche globale pour parler. — Recommandation : **Plus tard**.
- [ ] **STT local faster-whisper (bloc 5)** : transcription hors ligne, option vie privée. — Recommandation : **Plus tard**.

### Bloc 3 — Temps et rappels locaux
- [ ] **Minuteur / rappels persistants (bloc 21)** : minuteurs locaux avec persistance JSON. — Recommandation : **Oui, comme première brique locale**.
- [ ] **Notes quotidiennes (bloc 23)** : une mention par jour maximum par sujet. — Recommandation : **Plus tard**.

### Bloc 4 — Yeux et mains (le plus gros apport possible)
- [ ] **Vision d'écran (bloc 26)** : capture ciblée + description, avec consentement explicite à chaque capture. — Recommandation : **Plus tard, avec durcissement vie privée**.
- [ ] **Contrôle du navigateur Playwright (bloc 27)** : naviguer, lire des pages, ouvrir des URL localement. — Recommandation : **Plus tard**.
- [ ] **Lecture de page web complète (bloc 16)** : DuckDuckGo + extraction de texte. — Recommandation : **Plus tard**.

### Bloc 5 — Interface et session
- [ ] **HUD local léger (bloc 29)** : anneau d'état + cartes, version allégée (le HUD du dépôt B coûte ~760 Mo en veille). — Recommandation : **Plus tard**.
- [ ] **Lancement de session + quadrants (bloc 28)** : ouvrir les apps et ranger les fenêtres au démarrage. — Recommandation : **Plus tard**.
- [ ] **Auto-start au login (bloc 25)** : lancer le Jarvis local au démarrage de Windows. — Recommandation : **Plus tard**.
- [ ] **Serveur local (bloc 34)** : FastAPI/aiohttp sur `127.0.0.1` seulement, quand un PC/serveur local toujours allumé existera. — Recommandation : **Plus tard**.

### Bloc 6 — À ne pas reconstruire (déjà couvert par Carson)
- [ ] Conversation vocale, météo, calendrier, Gmail, Google Tasks, recherche web, actualités, briefing du matin, conversion de devises, mémoire persistante, orbe web. — Recommandation : **Non (doublons)**.
- [ ] Plans de repas, suivi de gym (openGym), recherche d'embargos, musique, messagerie, domotique (pour l'instant). — Recommandation : **Non**.

---

## 6. Ordre de construction recommandé, étape par étape

**Principe :** ne pas transcrire le code Claude vers Muse Code d'un bloc. Construire étape par étape, en français, en gardant Carson comme cerveau et le dépôt `Jarvis-Muse` comme pont — et ne construire une brique locale que si elle apporte quelque chose que Carson ne fait pas déjà.

1. **Étape 0 — Décisions.** Cocher la liste du §5. Sans ces choix, rien d'autre ne démarre.
2. **Étape 1 — Fondations.** Dans `Jarvis-Muse` : `config/` séparé (publique / locale / secrets), règles de sécurité écrites (patron `untrusted()` + `hold_writes` + confirmation en code), `docs/` avec ce document. Aucun code d'agent à ce stade.
3. **Étape 2 — Voix locale (première brique utile).** Vérifier une voix française (Kokoro/Piper) ; petit script qui lit à voix haute un texte fourni par Carson — c'est l'idée « résumés lus à la maison » qui plaît à Julien. Push-to-talk (F9) comme déclencheur simple, avant tout mot de réveil.
4. **Étape 3 — Minuteur local persistant.** Reprendre le patron `timers.py` du dépôt B (JSON persistant, carillon, annonce des retards au démarrage). Première brique qui agit seule, sans Carson.
5. **Étape 4 — Déclenchement.** Mot de réveil français (si un modèle existe) ou double-clap ; sinon, garder le push-to-talk.
6. **Étape 5 — Yeux et mains.** Vision d'écran ciblée + contrôle navigateur (Playwright), avec consentement explicite et capture limitée (fenêtre/région, jamais l'écran complet avec données sensibles). C'est le plus gros chantier, et celui qui comble la plus grande limite de Carson.
7. **Étape 6 — HUD local léger + lancement de session.** Anneau d'état et cartes, version allégée ; séquence de lancement (apps + quadrants) et auto-start au login.
8. **Étape 7 — Serveur local (seulement si un mini-PC / PC toujours allumé entre en jeu).** FastAPI ou aiohttp sur `127.0.0.1` uniquement, jamais `0.0.0.0` sans authentification. Tailscale comme pont distant, après GitHub.

**À ne pas construire :** tout le bloc 6 du §5 (doublons de Carson), la domotique et la musique tant que le besoin n'est pas exprimé, et aucune transcription intégrale du code allemand ou anglais — chaque brique est réécrite en français, pour Muse Code, avec les règles de sécurité du §4, bloc 32.

---

## 7. Incertitudes et points non vérifiés

- **Dépôt A — 5 issues ouvertes :** le nombre est confirmé par les métadonnées GitHub, mais leurs titres et contenus n'ont pas pu être récupérés (requête refusée par GitHub, HTTP 403, non réessayée). Sujets inconnus.
- **Dépôt A — `.claude/settings.local.json` :** contenu non lu (HTTP 403, non réessayé). Fichier de paramètres locaux de Claude Code, inhabituel dans un dépôt.
- **Dépôt A — vidéo de démonstration** (`https://youtu.be/XsceN-hEit4`) : citée, non visionnée.
- **Dépôt A — licence :** le README annonce MIT, mais aucun fichier `LICENSE` n'existe et l'API GitHub indique `license: null`. La réutilisation du code doit donc être prudente (demander ou considérer la licence comme non établie).
- **Dépôt A — `sounddevice` et `numpy`** (importés par `clap-trigger.py`) manquent dans `requirements.txt` : le double-clap ne fonctionnerait pas après un simple `pip install -r requirements.txt`.
- **Dépôt B — compte Google « shop » :** cité dans le README pour l'écriture du calendrier, mais absent de `config.local.example.toml` — périmètre non documenté dans l'exemple.
- **Dépôt B — tests et pages HUD :** le contenu détaillé de chaque fichier de test et des pages `hud/static/index.html` (956 lignes) et `widget.html` n'a pas été lu intégralement — seuls leurs en-têtes et structures ont été vérifiés.
- **Latence :** aucune latence de bout en bout n'est annoncée par l'un ou l'autre dépôt ; seuls des éléments partiels existent (Kokoro 0,3–1,2 s par phrase, rate-limit Groq jusqu'à 12 s, timeouts divers).
- **Voix française :** aucun des deux dépôts ne documente de voix française (Kokoro/Piper) ni de STT français — point à vérifier avant l'étape 2 du §6.

---

## Annexe — Sources

**Dépôt A — `Julian-Ivanov/jarvis-voice-assistant`** (branche `master`, consulté le 22 nov. 2026) : `README.md`, `SETUP.md`, `CLAUDE.md`, `server.py`, `browser_tools.py`, `screen_capture.py`, `frontend/index.html`, `frontend/main.js`, `frontend/style.css`, `scripts/clap-trigger.py`, `scripts/launch-session.ps1`, `config.example.json`, `requirements.txt`, `.gitignore`, arborescence de `.claude/`, `frontend/` et `scripts/`, métadonnées du dépôt (API GitHub). https://github.com/Julian-Ivanov/jarvis-voice-assistant

**Dépôt B — `tanishvbuk/jarvis-assistant`** (branche `main`, commit `debf995c1309e3796c16b8c1777afaaa1899a518`, consulté le 22 nov. 2026) : `README.md`, `pyproject.toml`, `config.toml`, `config.local.example.toml`, `.env.example`, `LICENSE`, paquet `jarvis/` (62 fichiers : `__main__.py`, `assistant.py`, `config.py`, `events.py`, `launcher.py`, `text.py`, `turnlog.py`, `audio/`, `stt/`, `tts/`, `llm/`, `connectors/`, `memory/`, `persona/`, `skills/`, `hud/`), `docs/` (`hud.png`, `widget.png`), `scripts/measure_hud_cpu.ps1`, `tests/` (18 fichiers, inventoriés par nom). https://github.com/tanishvbuk/jarvis-assistant

**Contexte Muse de Julien :** dépôt privé `Julien-Mendes/Jarvis-Muse` (README + `scripts/`, `config/`, `docs/`, branche `main`, accès vérifié le 21 nov. 2026) ; Carson comme agent (voix temps réel, mémoire, connecteurs, veilles) + Muse Code pour l'outillage local.

*Document préparé le 22 novembre 2026, à partir de la lecture directe des deux dépôts. Aucun code construit, aucun achat, aucun contact.*
