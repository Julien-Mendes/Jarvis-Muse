# Étape 4 — Déclenchement : boucle vocale interactive F9

Première vraie conversation avec le Jarvis local : on maintient F9 pour
parler, on relâche pour envoyer, et Jarvis répond à voix haute. Le seul
outil pour cette étape est le minuteur (étape 3).

## Principe

- Maintenir **F9** : enregistrement (micro mono 16 kHz, 30 secondes
  maximum). Relâcher F9 : transcription, puis réponse du cerveau.
- La réponse est lue à voix haute via `scripts/lire_voix.py` (étape 2).
- **F9 pendant la réponse l'interrompt** : la lecture s'arrête, on peut
  parler de nouveau.
- Un enregistrement de moins de 0,3 seconde est ignoré (fausse manipulation).
- L'historique de conversation est gardé en mémoire vive seulement (10
  derniers échanges) et s'efface à l'arrêt de la boucle — comme le dépôt B.
- Les réponses sont courtes (1 à 3 phrases), en français, et Jarvis appelle
  Julien par son prénom.

## Muse Code n'est pas le cerveau de la boucle

Précision importante, à ne pas confondre :

- **Muse Code est l'outillage de construction** : c'est l'agent de code
  local qui bâtit et fait évoluer le Jarvis (scripts, guides, corrections).
  Ce n'est pas une API temps réel.
- **La boucle a donc besoin d'un appel API par tour** pour son cerveau :
  **Groq gratuit par défaut** (gpt-oss-120b, palier gratuit, sans carte),
  ou **Claude Haiku par API en alternative configurable** (payant à
  l'usage, clé dans `.env`).
- Le fournisseur se choisit dans la configuration (`config.toml`,
  section `[boucle]`, clé `fournisseur_llm`), pas dans le code : passer
  de Groq à Haiku est une ligne à changer. Une comparaison complète des
  cerveaux (coût, performance, confidentialité) a été faite le 21 nov.
  2026 ; le choix définitif du défaut appartient à Julien.

## Prérequis

- Python 3.10+ et Windows (laptop de Julien pour tester).
- Microphone et haut-parleurs.
- Étapes 2 et 3 installées : Piper + voix `alan` (anglais, défaut à moyen terme) et `upmc` (français) (lecture des réponses),
  minuteur (outil de la boucle).
- Une clé **Groq** gratuite (voir ci-dessous) — sauf si le fournisseur est
  passé à Anthropic dans la configuration.

## Installation

Dans le dossier du dépôt cloné, en PowerShell :

```powershell
# 1. Créer et activer un environnement virtuel (si ce n'est pas déjà fait)
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Installer les dépendances de la boucle
pip install -r scripts\requirements-etape4.txt
```

Si PowerShell bloque l'activation :
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (une seule fois),
puis recommencer l'activation.

## Configuration : obtenir la clé Groq (gratuite, sans carte)

1. Créer un compte sur https://console.groq.com (gratuit, sans carte
   bancaire).
2. Dans le tableau de bord, aller dans **API Keys** puis **Create API Key**.
3. Copier la clé (elle commence par `gsk_`) et la mettre dans `.env`
   à la racine du dépôt (copier `config/.env.example` vers `.env` si
   besoin) :
   ```
   GROQ_API_KEY=gsk_...
   ```
4. Le fichier `.env` est gitignoré : il ne part jamais dans le dépôt.
   Ne jamais coller la clé dans une conversation ou une capture d'écran.

Pour utiliser Claude Haiku à la place : mettre `ANTHROPIC_API_KEY=sk-ant-...`
dans `.env` et `fournisseur_llm = "anthropic"` dans `config.toml`
(section `[boucle]`). C'est payant à l'usage (environ 0,25 $ / 1 M de
tokens en entrée pour Haiku).

Pour la transcription locale (faster-whisper, hors ligne) : décision
encore ouverte (bloc 5). Quand elle sera prise, il suffira de
`fournisseur_stt = "local"` dans `config.toml` — la boucle n'a pas
besoin d'être réécrite.

## Utilisation

```powershell
# Vérifier l'installation et la configuration (sans micro)
python scripts\boucle_voix.py --verifier

# Lancer la boucle interactive
python scripts\boucle_voix.py

# Un seul tour à partir d'un texte (sans micro) — utile pour tester
python scripts\boucle_voix.py --texte "mets un minuteur d'une minute"
```

Dans la boucle :
- Maintenir **F9**, parler, relâcher : la réponse arrive à voix haute.
- **F9 pendant la réponse** : elle s'interrompt.
- **Ctrl+C** : quitter la boucle.

> **Alarme du minuteur :** la boucle règle les minuteurs, mais l'alarme
> ne sonne que si la surveillance tourne. Lancer dans une autre fenêtre :
> `python scripts\minuteur.py surveiller` (voir `docs/etape-3-minuteur.md`).

## Premier test

```powershell
# 1. Vérifier l'installation
python scripts\boucle_voix.py --verifier

# 2. Un tour sans micro (chemin rapide du minuteur, pas besoin du LLM)
python scripts\boucle_voix.py --texte "mets un minuteur d'une minute"

# 3. Vérifier que le minuteur est bien enregistré
python scripts\minuteur.py lister

# 4. Lancer la boucle et la surveillance (deux fenêtres), puis dire à voix haute :
#    « mets un minuteur d'une minute » — l'alarme doit sonner au bout d'une minute.
python scripts\boucle_voix.py
python scripts\minuteur.py surveiller
```

## Dépannage

- **« GROQ_API_KEY absente »** : la clé n'est pas dans `.env`. Vérifier
  que le fichier `.env` est à la racine du dépôt (ou dans `config/`) et
  qu'il contient `GROQ_API_KEY=gsk_...` sans espaces autour du `=`.
- **« module groq / pynput / sounddevice non installé »** :
  `pip install -r scripts\requirements-etape4.txt` dans l'environnement
  virtuel activé.
- **F9 ne répond pas** : vérifier que la fenêtre PowerShell de la boucle
  est bien la fenêtre active (le clavier global écoute partout, mais
  certains logiciels peuvent capturer F9). Essayer en fermant les autres
  applications. Sur certains claviers de portable, F9 partage sa touche
  avec une fonction (volume, luminosité) : utiliser la touche `Fn` en
  même temps si besoin.
- **Micro non détecté / « Erreur micro »** : vérifier dans les paramètres
  Windows que le micro est autorisé pour les applications de bureau, et
  que le bon micro est celui par défaut (Paramètres → Son → Entrée).
  Tester avec l'Enregistreur vocal Windows pour confirmer que le micro
  fonctionne.
- **« Je n'ai rien compris »** : l'enregistrement était trop court ou
  silencieux. Maintenir F9 un peu plus longtemps, parler plus fort ou
  plus près du micro.
- **« Je suis limité en ce moment »** : le palier gratuit Groq limite à
  8 000 tokens par minute. Quelques questions rapides d'affilée peuvent
  faire attendre jusqu'à ~12 secondes : la boucle le signale et il suffit
  de réessayer. (C'est le même comportement que dans le dépôt B.)
- **« Annonce vocale indisponible »** : Piper ou la voix n'est pas
  installé. La réponse est affichée à l'écran quand même. Suivre
  `docs/etape-2-voix.md` pour installer Piper et la voix `alan` (anglais) ou `upmc` (français).
- **« Je n'ai pas pu régler le minuteur »** : le message d'erreur du
  minuteur est affiché (durée trop longue, 20 minuteurs déjà actifs…).
  Voir `docs/etape-3-minuteur.md`.
- **La boucle se ferme toute seule** : vérifier le message d'erreur
  affiché (souvent une clé absente ou un module non installé). Relancer
  avec `--verifier` pour le bilan complet.

## Vie privée

- **Groq, conditions vérifiées le 21 nov. 2026** : Groq indique ne pas
  entraîner ses modèles sur les données envoyées (pas de rétention par
  défaut, ZDR disponible). L'avertissement du README du dépôt B (« le
  palier gratuit peut utiliser vos prompts pour l'entraînement ») est
  dépassé. Par prudence, on ne confie quand même rien de sensible à la
  boucle (pas de mots de passe, pas de données bancaires ou médicales) —
  les conditions peuvent évoluer.
- **Anthropic (Haiku par API)** : les prompts ne servent pas à
  l'entraînement ; facturation à l'usage.
- **Ce qui part en infonuagique à cette étape** : l'audio enregistré
  (transcription Groq Whisper) et le texte transcrit (LLM Groq ou
  Anthropic). La voix de lecture (Piper) reste 100 % locale.
- **Option future** : transcription locale faster-whisper (hors ligne) —
  décision encore ouverte ; la boucle est déjà structurée pour l'accueillir
  sans réécriture.

## Plus tard : modèle local (Ollama)

Décision confirmée le 21 nov. 2026 : **on garde Groq gratuit comme cerveau
par défaut pour le moment**. Un modèle local reste une option pour plus
tard, quand le mini-PC sera là — il n'est pas construit dans cette étape.

- **Faisable selon le matériel** : 32 Go de RAM recommandés ; Apple
  Silicon ou GPU idéal.
- **gpt-oss-20b**, même famille que le cerveau Groq (gpt-oss-120b),
  tourne dans 16 Go.
- **Sur CPU seulement**, un modèle 8B fait environ 8 à 15 tokens par
  seconde : réponses courtes seulement. Un modèle local sur CPU n'est
  donc pas fait pour de longues réponses — à réserver aux échanges brefs
  ou à un petit modèle.
- **Le code est déjà prêt à l'accueillir** : le cerveau est un backend
  interchangeable (`creer_cerveau` dans `scripts/boucle_voix.py`).
  Ajouter Ollama = une nouvelle classe avec une méthode
  `repondre(messages, outils)`, une branche dans la fabrique et une ligne
  dans `config.toml` (`fournisseur_llm = "ollama"`) — sans réécrire la
  boucle.

## Sécurité

Conforme à `docs/regles-securite.md` :
- **Hold_writes (§2)** : à cette étape, aucun outil ne lit de contenu
  externe. La seule écriture possible est le minuteur, déclenché par la
  demande orale explicite de Julien lui-même. Si un futur outil lit des
  données externes (courriel, page web…), le tour doit bloquer toute
  écriture.
- **Aucun serveur local à cette étape** : rien n'écoute sur un port. Si
  un serveur local arrive plus tard (étape 7), il n'écoutera que sur
  127.0.0.1, jamais sur 0.0.0.0.
- **Secrets** : clés API dans `.env` (gitignoré), jamais dans le code ni
  dans le dépôt.
- **Journaux** : aucun contenu de conversation n'est enregistré ; seul
  l'historique des 10 derniers échanges est gardé en mémoire vive pendant
  la boucle.
