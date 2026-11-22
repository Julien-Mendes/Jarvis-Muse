#!/usr/bin/env python3
"""boucle_voix.py — Boucle vocale interactive du Jarvis-Muse (étape 4).

Fonctionnement (push-to-talk, touche F9 — décision validée le 21 nov. 2026) :
    1. Maintenir F9 pour parler (enregistrement, micro mono 16 kHz, 30 s max).
    2. Relâcher F9 pour envoyer : transcription, puis réponse du « cerveau ».
    3. La réponse est lue à voix haute via scripts/lire_voix.py (étape 2).
    4. F9 pendant la réponse l'interrompt.

Usage :
    python scripts/boucle_voix.py
    python scripts/boucle_voix.py --texte "mets un minuteur d'une minute"
    python scripts/boucle_voix.py --verifier

Cerveau par défaut : Groq (gpt-oss-120b, palier gratuit, sans carte).
Alternative configurable : Claude Haiku par API (payant à l'usage, clé dans
.env). Le fournisseur se choisit dans la configuration, pas dans le code.

Transcription par défaut : Groq Whisper (whisper-large-v3-turbo). Le code est
structuré avec un backend STT interchangeable : faster-whisper local pourra
remplacer Groq plus tard sans réécrire la boucle (décision bloc 5, encore
ouverte).

Premier et seul outil pour cette étape : le minuteur — scripts/minuteur.py
est appelé en sous-processus quand Julien demande un minuteur à voix haute.

Sécurité (docs/regles-securite.md) :
  - Aucune donnée externe n'est lue à cette étape : la seule écriture
    possible est le minuteur, déclenché par la demande orale explicite de
    Julien lui-même (règle hold_writes, §2 : si un futur outil lit du
    contenu externe, toute écriture est bloquée pour le tour).
  - Aucun serveur local à cette étape : rien n'écoute sur un port.
  - Les clés API sont dans .env (gitignoré), jamais dans le code.
  - Avertissement vie privée : Groq indique ne pas entraîner ses modèles
    sur les données (pas de rétention par défaut, ZDR disponible) —
    l'avertissement du README du dépôt B est dépassé (conditions vérifiées
    le 21 nov. 2026). Par prudence, ne rien confier de sensible ; voir
    docs/etape-4-declenchement.md.
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Fuseau horaire de Julien (config/config.example.toml).
FUSEAU = ZoneInfo("America/Toronto")

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]

RACINE = Path(__file__).resolve().parent.parent
SCRIPT_VOIX = RACINE / "scripts" / "lire_voix.py"
SCRIPT_MINUTEUR = RACINE / "scripts" / "minuteur.py"

# Valeurs par défaut (surchargées par config.toml [boucle] puis par .env).
DEFAUTS = {
    "fournisseur_llm": "groq",        # "groq" ou "anthropic".
    "modele_groq": "openai/gpt-oss-120b",
    "modele_anthropic": "claude-haiku-4-5-20251001",
    "fournisseur_stt": "groq",        # "groq" ou "local" (faster-whisper).
    "modele_stt_groq": "whisper-large-v3-turbo",
    "modele_stt_local": "base",
    "langue": "fr",
    "touche": "F9",
    "duree_max_enregistrement": 30.0,
    "duree_min_enregistrement": 0.3,
    "max_tours_outils": 3,
    "max_tokens_reponse": 400,
}


# ---------------------------------------------------------------------------
# Configuration (.env pour les secrets, config.toml pour les choix)
# ---------------------------------------------------------------------------

def charger_env(racine: Path) -> None:
    """Charge .env (à la racine ou dans config/) dans l'environnement.

    Utilise python-dotenv si disponible, sinon un lecteur minimal (lignes
    CLE=VALEUR). Ne pas échouer si le fichier est absent.
    """
    for candidat in (racine / ".env", racine / "config" / ".env"):
        if not candidat.exists():
            continue
        try:
            from dotenv import load_dotenv

            load_dotenv(candidat, override=False)
            return
        except ImportError:
            pass
        for ligne in candidat.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            cle, valeur = ligne.split("=", 1)
            os.environ.setdefault(
                cle.strip(), valeur.strip().strip("\"'"))
        return


def charger_config(racine: Path) -> dict:
    """Lit config.toml ([boucle]), sinon config.example.toml, sinon défauts.

    Les variables d'environnement JARVIS_LLM et JARVIS_STT priment sur le
    fichier. Les clés API ne sont jamais lues ici : elles vivent dans .env.
    """
    config = dict(DEFAUTS)
    fichier = racine / "config" / "config.toml"
    if not fichier.exists():
        fichier = racine / "config" / "config.example.toml"
        if fichier.exists():
            print("Note : config.toml absent, on utilise config.example.toml "
                  "(copiez-le vers config.toml pour personnaliser).")
    if fichier.exists():
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                print("Avertissement : ni tomllib ni tomli disponible ; "
                      "configuration par défaut.", file=sys.stderr)
                tomllib = None
        if tomllib is not None:
            try:
                donnees = tomllib.loads(fichier.read_text(encoding="utf-8"))
                boucle = donnees.get("boucle", {})
                for cle in DEFAUTS:
                    if cle in boucle:
                        config[cle] = boucle[cle]
            except (ValueError, OSError) as erreur:
                print(f"Avertissement : config illisible ({erreur}) ; "
                      "configuration par défaut.", file=sys.stderr)
    if os.environ.get("JARVIS_LLM"):
        config["fournisseur_llm"] = os.environ["JARVIS_LLM"].lower()
    if os.environ.get("JARVIS_STT"):
        config["fournisseur_stt"] = os.environ["JARVIS_STT"].lower()
    return config


def prompt_systeme() -> str:
    """Prompt système : ton de Jarvis, réponses courtes, prénom de Julien."""
    ref = datetime.now(FUSEAU)
    date_heure = (f"{JOURS[ref.weekday()]} {ref.day} "
                  f"{MOIS[ref.month - 1]} {ref.year}, "
                  f"{ref.hour} h {ref.minute:02d}")
    return (
        "Tu es Jarvis, l'assistant vocal de Julien. Tu parles français.\n"
        "Tes réponses sont courtes : 1 à 3 phrases. "
        "Tu appelles Julien par son prénom.\n"
        "Tu ne parles jamais de tes outils internes.\n"
        "Tu n'inventes jamais : si tu ne sais pas, tu le dis.\n"
        f"Nous sommes le {date_heure}."
    )


# ---------------------------------------------------------------------------
# Voix : lecture de la réponse à voix haute (avec interruption)
# ---------------------------------------------------------------------------

def dire(texte: str, langue: str, interruption: threading.Event) -> None:
    """Lit le texte à voix haute via lire_voix.py.

    Si l'événement d'interruption est posé (F9 pressé pendant la lecture),
    le processus de lecture est arrêté. Si la voix est indisponible, le
    texte est déjà affiché à l'écran : la réponse n'est jamais perdue.
    """
    print(f"Jarvis : {texte}", flush=True)
    try:
        processus = subprocess.Popen(
            [sys.executable, str(SCRIPT_VOIX), "--texte", texte,
             "--langue", langue],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
    except OSError as erreur:
        print(f"Annonce vocale indisponible ({erreur}) ; "
              "réponse affichée ci-dessus.", file=sys.stderr)
        return
    while processus.poll() is None:
        if interruption.wait(timeout=0.1):
            processus.terminate()
            try:
                processus.wait(timeout=3)
            except subprocess.TimeoutExpired:
                processus.kill()
                processus.wait()
            print("(Réponse interrompue.)")
            return
    processus.wait()
    if processus.returncode != 0:
        detail = (processus.stderr.read() or "").strip().splitlines()
        print("Annonce vocale indisponible "
              f"({detail[0] if detail else 'code ' + str(processus.returncode)}) ; "
              "réponse affichée ci-dessus.", file=sys.stderr)


# ---------------------------------------------------------------------------
# Enregistrement (micro mono 16 kHz, F9 pour démarrer/arrêter)
# ---------------------------------------------------------------------------

class Enregistreur:
    """Capture le micro avec sounddevice, en mémoire seulement.

    L'audio n'est jamais écrit sur disque : il est transcrit directement
    depuis les octets WAV en mémoire.
    """

    def __init__(self, frequence: int = 16000):
        self.frequence = frequence
        self.morceaux: list = []
        self.flux = None

    def _rappel(self, indata, frames, temps, statut):
        if statut:
            print(f"Avertissement micro : {statut}", file=sys.stderr)
        self.morceaux.append(bytes(indata))

    def demarrer(self) -> None:
        import sounddevice as sd

        self.morceaux = []
        self.flux = sd.InputStream(
            samplerate=self.frequence, channels=1, dtype="int16",
            callback=self._rappel)
        self.flux.start()

    def arreter(self):
        if self.flux is not None:
            self.flux.stop()
            self.flux.close()
            self.flux = None

    def octets_wav(self):
        """Retourne (octets WAV, durée en secondes)."""
        donnees = b"".join(self.morceaux)
        tampon = io.BytesIO()
        with wave.open(tampon, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.frequence)
            wav.writeframes(donnees)
        duree = len(donnees) / 2 / self.frequence
        return tampon.getvalue(), duree


# ---------------------------------------------------------------------------
# Transcription (STT) — backend interchangeable
# ---------------------------------------------------------------------------

class TranscripteurGroq:
    """Whisper infonuagique via Groq (whisper-large-v3-turbo)."""

    def __init__(self, cle_api: str, modele: str):
        from groq import Groq

        self.client = Groq(api_key=cle_api)
        self.modele = modele

    def transcrire(self, octets_wav: bytes) -> str:
        reponse = self.client.audio.transcriptions.create(
            model=self.modele,
            file=("enregistrement.wav", octets_wav, "audio/wav"),
            language="fr",
            response_format="text",
        )
        if isinstance(reponse, str):
            return reponse.strip()
        return str(getattr(reponse, "text", "")).strip()


class TranscripteurLocal:
    """Whisper local hors ligne (faster-whisper, CPU int8).

    Option future (décision bloc 5, encore ouverte) : aucun audio ne quitte
    alors la machine. Le modèle (~150 Mo) est téléchargé au premier usage.
    """

    def __init__(self, modele: str = "base"):
        from faster_whisper import WhisperModel

        self.modele = WhisperModel(modele, device="cpu", compute_type="int8")

    def transcrire(self, octets_wav: bytes) -> str:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            chemin_tmp = Path(tmp.name)
        try:
            chemin_tmp.write_bytes(octets_wav)
            segments, _ = self.modele.transcribe(
                str(chemin_tmp), language="fr")
            return "".join(s.text for s in segments).strip()
        finally:
            chemin_tmp.unlink(missing_ok=True)


def creer_transcripteur(config: dict):
    """Fabrique le transcripteur choisi dans la configuration."""
    if config["fournisseur_stt"] == "local":
        try:
            return TranscripteurLocal(config["modele_stt_local"])
        except ImportError:
            print("Erreur : faster-whisper n'est pas installé.", file=sys.stderr)
            print("Installez-le avec :", file=sys.stderr)
            print("  pip install faster-whisper", file=sys.stderr)
            print("Ou repassez à Groq : fournisseur_stt = \"groq\" dans "
                  "config.toml.", file=sys.stderr)
            raise SystemExit(3)
    cle = os.environ.get("GROQ_API_KEY", "").strip()
    if not cle:
        print("Erreur : GROQ_API_KEY absente.", file=sys.stderr)
        print("Créez une clé gratuite sur https://console.groq.com "
              "(compte gratuit, sans carte) et mettez-la dans .env :",
              file=sys.stderr)
        print("  GROQ_API_KEY=gsk_...", file=sys.stderr)
        raise SystemExit(3)
    try:
        return TranscripteurGroq(cle, config["modele_stt_groq"])
    except ImportError:
        print("Erreur : le module groq n'est pas installé.", file=sys.stderr)
        print("Installez-le avec :", file=sys.stderr)
        print("  pip install -r scripts/requirements-etape4.txt",
              file=sys.stderr)
        raise SystemExit(3)


# ---------------------------------------------------------------------------
# Cerveau (LLM) — backend interchangeable, un appel API par tour
# ---------------------------------------------------------------------------
# Précision importante (décision du 21 nov. 2026) : Muse Code est l'outillage
# de construction du Jarvis (agent de code local pour bâtir et faire évoluer
# les scripts), pas le cerveau de la boucle — ce n'est pas une API temps réel.
# La boucle a donc besoin d'un appel API par tour : Groq gratuit par défaut,
# Claude Haiku par API en alternative configurable.

OUTIL_MINUTEUR_DESCRIPTION = (
    "Règle un minuteur (compte à rebours) ou un rappel à heure fixe pour "
    "Julien. Utilise-le quand Julien demande un minuteur ou un rappel."
)
OUTIL_MINUTEUR_PARAMETRES = {
    "type": "object",
    "properties": {
        "minutes": {
            "type": "number",
            "description": "Durée en minutes pour un compte à rebours "
                           "(ex. 20 pour « minuteur de 20 minutes »).",
        },
        "a": {
            "type": "string",
            "description": "Heure fixe HH:MM (ex. 18:30) ou "
                           "AAAA-MM-JJTHH:MM (ex. 2026-11-22T18:30).",
        },
        "etiquette": {
            "type": "string",
            "description": "Nom du minuteur, en tes mots (ex. « pâtes »).",
        },
    },
    "required": [],
}

OUTIL_MINUTEUR_GROQ = {
    "type": "function",
    "function": {
        "name": "regler_minuteur",
        "description": OUTIL_MINUTEUR_DESCRIPTION,
        "parameters": OUTIL_MINUTEUR_PARAMETRES,
    },
}

OUTIL_MINUTEUR_ANTHROPIC = {
    "name": "regler_minuteur",
    "description": OUTIL_MINUTEUR_DESCRIPTION,
    "input_schema": OUTIL_MINUTEUR_PARAMETRES,
}


class CerveauGroq:
    """Cerveau par défaut : Groq, gpt-oss-120b (palier gratuit, sans carte)."""

    def __init__(self, cle_api: str, modele: str, max_tokens: int):
        from groq import Groq

        self.client = Groq(api_key=cle_api)
        self.modele = modele
        self.max_tokens = max_tokens

    def repondre(self, messages: list, outils: list) -> dict:
        """Un tour de LLM. Retourne {"texte": str, "appels_outils": [...]}."""
        reponse = self.client.chat.completions.create(
            model=self.modele, messages=messages, tools=outils,
            tool_choice="auto", max_tokens=self.max_tokens, temperature=0.3)
        message = reponse.choices[0].message
        appels = []
        for appel in (message.tool_calls or []):
            try:
                arguments = json.loads(appel.function.arguments or "{}")
            except ValueError:
                arguments = {}
            appels.append({
                "nom": appel.function.name,
                "arguments": arguments,
                "id": appel.id,
            })
        return {"texte": message.content or "", "appels_outils": appels}

    def message_assistant(self, reponse: dict) -> dict:
        """Message assistant à réinjecter dans l'historique du tour."""
        appels = [{
            "id": a["id"], "type": "function",
            "function": {"name": a["nom"],
                         "arguments": json.dumps(a["arguments"],
                                                 ensure_ascii=False)},
        } for a in reponse["appels_outils"]]
        message = {"role": "assistant", "content": reponse["texte"] or None}
        if appels:
            message["tool_calls"] = appels
        return message


class CerveauAnthropic:
    """Alternative configurable : Claude Haiku par API (payant à l'usage)."""

    def __init__(self, cle_api: str, modele: str, max_tokens: int):
        from anthropic import Anthropic

        self.client = Anthropic(api_key=cle_api)
        self.modele = modele
        self.max_tokens = max_tokens

    def repondre(self, messages: list, outils: list) -> dict:
        """Un tour de LLM. Retourne {"texte": str, "appels_outils": [...]}."""
        systeme = next(
            (m["content"] for m in messages if m["role"] == "system"), "")
        conversation = [m for m in messages if m["role"] != "system"]
        outils_anthropic = [{
            "name": o["name"],
            "description": o["description"],
            "input_schema": o["input_schema"],
        } for o in outils]
        reponse = self.client.messages.create(
            model=self.modele, max_tokens=self.max_tokens, system=systeme,
            messages=conversation, tools=outils_anthropic)
        texte = ""
        appels = []
        for bloc in reponse.content:
            if bloc.type == "text":
                texte += bloc.text
            elif bloc.type == "tool_use":
                appels.append({
                    "nom": bloc.name,
                    "arguments": dict(bloc.input or {}),
                    "id": bloc.id,
                })
        return {"texte": texte, "appels_outils": appels,
                "_contenu_brut": reponse.content}

    def message_assistant(self, reponse: dict) -> dict:
        return {"role": "assistant", "content": reponse["_contenu_brut"]}


def creer_cerveau(config: dict):
    """Fabrique le cerveau choisi dans la configuration.

    Pour ajouter un fournisseur plus tard (ex. Ollama local, voir
    docs/etape-4-declenchement.md « Plus tard : modèle local ») : créer
    une classe CerveauXxx avec une méthode repondre(messages, outils),
    puis ajouter une branche ici — la boucle n'a pas besoin d'être
    réécrite.
    """
    fournisseur = config["fournisseur_llm"]
    if fournisseur == "anthropic":
        cle = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not cle:
            print("Erreur : ANTHROPIC_API_KEY absente.", file=sys.stderr)
            print("Mettez votre clé Anthropic dans .env :", file=sys.stderr)
            print("  ANTHROPIC_API_KEY=sk-ant-...", file=sys.stderr)
            raise SystemExit(3)
        try:
            return CerveauAnthropic(
                cle, config["modele_anthropic"],
                config["max_tokens_reponse"])
        except ImportError:
            print("Erreur : le module anthropic n'est pas installé.",
                  file=sys.stderr)
            print("Installez-le avec :", file=sys.stderr)
            print("  pip install anthropic", file=sys.stderr)
            raise SystemExit(3)
    if fournisseur != "groq":
        print(f"Erreur : fournisseur_llm inconnu : « {fournisseur} » "
              "(« groq » ou « anthropic »).", file=sys.stderr)
        raise SystemExit(1)
    cle = os.environ.get("GROQ_API_KEY", "").strip()
    if not cle:
        print("Erreur : GROQ_API_KEY absente.", file=sys.stderr)
        print("Créez une clé gratuite sur https://console.groq.com "
              "(compte gratuit, sans carte) et mettez-la dans .env :",
              file=sys.stderr)
        print("  GROQ_API_KEY=gsk_...", file=sys.stderr)
        raise SystemExit(3)
    try:
        return CerveauGroq(cle, config["modele_groq"],
                           config["max_tokens_reponse"])
    except ImportError:
        print("Erreur : le module groq n'est pas installé.", file=sys.stderr)
        print("Installez-le avec :", file=sys.stderr)
        print("  pip install -r scripts/requirements-etape4.txt",
              file=sys.stderr)
        raise SystemExit(3)


# ---------------------------------------------------------------------------
# Outil minuteur : chemin rapide (regex) + appel au script minuteur
# ---------------------------------------------------------------------------

def extraire_etiquette(texte: str, fin: int) -> str:
    """Prend ce qui suit « pour … » comme étiquette (« pour les pâtes »)."""
    reste = texte[fin:].strip(" .,!")
    if reste.startswith("pour "):
        return reste[5:].strip(" .,!")
    return ""


NOMBRES_FR = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11,
    "douze": 12, "quinze": 15, "vingt": 20, "trente": 30, "quarante": 40,
    "cinquante": 50, "soixante": 60,
}
_MOTIF_NOMBRE = (r"(\d+(?:[.,]\d+)?|un|une|deux|trois|quatre|cinq|six|sept|"
                 r"huit|neuf|dix|onze|douze|quinze|vingt|trente|quarante|"
                 r"cinquante|soixante)")


def _en_minutes(texte_nombre: str, unite: str) -> float:
    """Convertit un nombre (chiffres ou lettres) + une unité en minutes."""
    if texte_nombre in NOMBRES_FR:
        nombre = float(NOMBRES_FR[texte_nombre])
    else:
        nombre = float(texte_nombre.replace(",", "."))
    if unite.startswith("seconde"):
        return nombre / 60
    if unite.startswith("heure"):
        return nombre * 60
    return nombre


def detecter_minuteur(texte: str):
    """Détecte une demande de minuteur explicite, sans passer par le LLM.

    Chemin rapide pour les formulations courantes ; le LLM (avec l'outil
    minuteur déclaré) couvre les autres formulations. Retourne un dict
    {"minutes": float|None, "a": str|None, "etiquette": str} ou None.
    """
    t = texte.strip().lower()
    # « d'une minute » -> « de une minute » pour simplifier les motifs.
    t = t.replace("d'une", "de une").replace("d'un", "de un")
    m = re.search(r"minuteur(?: de)?\s+(?:une\s+)?demi-?heure", t)
    if m:
        return {"minutes": 30.0, "a": None,
                "etiquette": extraire_etiquette(t, m.end())}
    m = re.search(
        r"minuteur(?: de)?\s+" + _MOTIF_NOMBRE +
        r"\s*(secondes?|minutes?|heures?)", t)
    if m:
        return {"minutes": _en_minutes(m.group(1), m.group(2)), "a": None,
                "etiquette": extraire_etiquette(t, m.end())}
    m = re.search(r"rappel(?:le-moi)?\s+(?:à|a)\s+(\d{1,2})[:h](\d{2})", t)
    if m:
        return {"minutes": None,
                "a": f"{int(m.group(1)):02d}:{m.group(2)}",
                "etiquette": extraire_etiquette(t, m.end())}
    m = re.search(
        r"rappelle?-?moi dans\s+" + _MOTIF_NOMBRE +
        r"\s*(secondes?|minutes?|heures?)", t)
    if m:
        return {"minutes": _en_minutes(m.group(1), m.group(2)), "a": None,
                "etiquette": extraire_etiquette(t, m.end())}
    return None


def formater_duree_simple(minutes: float) -> str:
    """« 6 secondes », « 1 minute », « 20 minutes », « 1 heure 30 »."""
    if minutes < 1:
        secondes = round(minutes * 60)
        return f"{secondes} seconde" + ("s" if secondes > 1 else "")
    if minutes < 60:
        total = int(minutes) if minutes == int(minutes) else minutes
        return f"{total:g} minute" + ("s" if total > 1 else "")
    heures = int(minutes // 60)
    reste = int(minutes % 60)
    texte = f"{heures} heure" + ("s" if heures > 1 else "")
    if reste:
        texte += f" {reste}"
    return texte


def executer_minuteur(demande: dict, donnees: Path | None) -> str:
    """Appelle scripts/minuteur.py en sous-processus.

    Retourne une phrase de confirmation courte, à lire à voix haute.
    Sécurité (hold_writes, docs/regles-securite.md §2) : la seule écriture
    possible est ce minuteur, déclenché par la demande orale explicite de
    Julien lui-même — aucune donnée externe n'est lue dans ce tour.
    """
    commande = [sys.executable, str(SCRIPT_MINUTEUR)]
    if donnees is not None:
        # --donnees est une option globale de minuteur.py : elle passe
        # AVANT le sous-commande (demarrer / lister / annuler…).
        commande += ["--donnees", str(donnees)]
    commande += ["demarrer"]
    if demande["minutes"] is not None:
        commande += ["--minutes", str(demande["minutes"])]
    else:
        commande += ["--a", demande["a"]]
    if demande["etiquette"]:
        commande += ["--etiquette", demande["etiquette"]]
    try:
        resultat = subprocess.run(commande, capture_output=True, text=True,
                                  timeout=60)
    except (OSError, subprocess.TimeoutExpired) as erreur:
        return (f"Désolé Julien, je n'ai pas pu régler le minuteur "
                f"({erreur}).")
    if resultat.returncode != 0:
        detail = (resultat.stderr or "").strip().splitlines()
        message = detail[0] if detail else "erreur inconnue"
        return f"Désolé Julien, je n'ai pas pu régler le minuteur : {message}"
    quoi = (f"minuteur de {formater_duree_simple(demande['minutes'])}"
            if demande["minutes"] is not None
            else f"rappel à {demande['a']}")
    if demande["etiquette"]:
        quoi += f" « {demande['etiquette']} »"
    return f"C'est réglé, Julien : {quoi}."


# ---------------------------------------------------------------------------
# Traitement d'un tour : transcription -> réponse
# ---------------------------------------------------------------------------

def traiter_tour(transcription: str, config: dict, cerveau, historique: list,
                donnees: Path | None) -> str:
    """Traite une phrase entendue et retourne la réponse à lire à voix haute."""
    # 1. Chemin rapide : demande de minuteur explicite (sans appel LLM).
    demande = detecter_minuteur(transcription)
    if demande is not None:
        return executer_minuteur(demande, donnees)

    # 2. Cerveau, avec l'outil minuteur déclaré (3 rondes maximum).
    messages = [{"role": "system", "content": prompt_systeme()}]
    messages += historique
    messages.append({"role": "user", "content": transcription})
    outils = [OUTIL_MINUTEUR_GROQ if config["fournisseur_llm"] == "groq"
              else OUTIL_MINUTEUR_ANTHROPIC]
    try:
        for _ in range(int(config["max_tours_outils"])):
            reponse = cerveau.repondre(messages, outils)
            messages.append(cerveau.message_assistant(reponse))
            if not reponse["appels_outils"]:
                return reponse["texte"].strip() or (
                    "Je n'ai pas de réponse, Julien.")
            for appel in reponse["appels_outils"]:
                if appel["nom"] != "regler_minuteur":
                    resultat_outil = (
                        "Outil inconnu : je ne sais faire que les minuteurs "
                        "pour l'instant.")
                else:
                    args = appel["arguments"] or {}
                    demande_outil = {
                        "minutes": args.get("minutes"),
                        "a": args.get("a"),
                        "etiquette": args.get("etiquette", "") or "",
                    }
                    if (demande_outil["minutes"] is None
                            and not demande_outil["a"]):
                        resultat_outil = (
                            "Il me manque la durée ou l'heure du minuteur.")
                    else:
                        resultat_outil = executer_minuteur(
                            demande_outil, donnees)
                if config["fournisseur_llm"] == "groq":
                    messages.append({
                        "role": "tool",
                        "tool_call_id": appel["id"],
                        "content": resultat_outil,
                    })
                else:
                    messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": appel["id"],
                            "content": resultat_outil,
                        }],
                    })
        return ("Je n'ai pas réussi à aboutir, Julien — "
                "peux-tu reformuler ?")
    except Exception as erreur:
        message = str(erreur)
        print(f"Erreur du cerveau : {message}", file=sys.stderr)
        if "429" in message or "rate" in message.lower():
            return ("Je suis limité en ce moment, Julien — le palier "
                    "gratuit me fait attendre. Réessaie dans quelques "
                    "secondes.")
        return ("Désolé Julien, je n'ai pas pu joindre le cerveau "
                "pour l'instant.")


# ---------------------------------------------------------------------------
# Vérification de l'installation (sans micro, sans clé requise pour --texte)
# ---------------------------------------------------------------------------

def verifier(config: dict) -> int:
    """Vérifie l'installation et la configuration, puis affiche un bilan."""
    print("Vérification de la boucle vocale (étape 4) :")
    problemes = []

    def ligne(ok: bool, nom: str, detail: str = ""):
        marque = "OK     " if ok else "MANQUANT"
        print(f"  [{marque}] {nom}" + (f" — {detail}" if detail else ""))
        if not ok:
            problemes.append(nom)

    version = sys.version_info
    ligne(version >= (3, 10), "Python 3.10+",
          f"{version.major}.{version.minor}.{version.micro}")
    for module in ("sounddevice", "pynput", "groq", "dotenv"):
        try:
            __import__(module)
            ligne(True, f"module {module}")
        except ImportError:
            ligne(False, f"module {module}",
                  "pip install -r scripts/requirements-etape4.txt")
    ligne(SCRIPT_VOIX.exists(), "scripts/lire_voix.py")
    ligne(SCRIPT_MINUTEUR.exists(), "scripts/minuteur.py")
    ligne((RACINE / "models").exists(), "dossier models/ (voix Piper)",
          "voir docs/etape-2-voix.md" if not (RACINE / "models").exists()
          else "")
    if config["fournisseur_llm"] == "groq":
        ligne(bool(os.environ.get("GROQ_API_KEY", "").strip()),
              "GROQ_API_KEY dans .env",
              "clé gratuite sur https://console.groq.com")
    else:
        ligne(bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()),
              "ANTHROPIC_API_KEY dans .env")
    if config["fournisseur_stt"] == "local":
        try:
            __import__("faster_whisper")
            ligne(True, "module faster_whisper")
        except ImportError:
            ligne(False, "module faster_whisper", "pip install faster-whisper")
    print()
    if problemes:
        print(f"{len(problemes)} élément(s) à régler : "
              + ", ".join(problemes) + ".")
        print("Voir docs/etape-4-declenchement.md pour les détails.")
        return 1
    print("Tout est en place. Lancez la boucle avec :")
    print("  python scripts\\boucle_voix.py")
    return 0


# ---------------------------------------------------------------------------
# Boucle interactive F9
# ---------------------------------------------------------------------------

def enregistrer_jusqu_a_relache(fin: threading.Event, duree_max: float):
    """Enregistre jusqu'à ce que l'événement de relâche soit posé (ou 30 s).

    Retourne (octets WAV, durée en secondes)."""
    enregistreur = Enregistreur()
    enregistreur.demarrer()
    debut = time.monotonic()
    try:
        while not fin.wait(timeout=0.05):
            if time.monotonic() - debut >= duree_max:
                print("(30 secondes maximum atteintes.)")
                break
    finally:
        enregistreur.arreter()
    return enregistreur.octets_wav()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Boucle vocale interactive (F9 pour parler, "
                    "relâcher pour envoyer).")
    parser.add_argument(
        "--texte", default=None,
        help="Un seul tour à partir d'un texte (sans micro) — utile pour "
             "tester le cerveau et le minuteur.")
    parser.add_argument(
        "--verifier", action="store_true",
        help="Vérifier l'installation et la configuration, puis quitter.")
    parser.add_argument(
        "--donnees", type=Path, default=None,
        help="Fichier JSON des minuteurs (défaut : data/timers.json) — "
             "utile pour tester sans toucher les vrais minuteurs.")
    parser.add_argument(
        "--langue", choices=["fr", "en"], default=None,
        help="Langue des réponses (défaut : celle de config.toml).")
    args = parser.parse_args()

    charger_env(RACINE)
    config = charger_config(RACINE)
    if args.langue:
        config["langue"] = args.langue

    if args.verifier:
        return verifier(config)

    if args.texte is not None:
        if not args.texte.strip():
            print("Erreur : --texte est vide.", file=sys.stderr)
            return 1
        cerveau = None
        if detecter_minuteur(args.texte) is None:
            cerveau = creer_cerveau(config)
        reponse = traiter_tour(args.texte, config, cerveau, [], args.donnees)
        print(f"Jarvis : {reponse}")
        return 0

    # --- Boucle interactive ---
    touche_nom = str(config["touche"]).upper()
    if touche_nom != "F9":
        print("Erreur : seule la touche F9 est prise en charge pour "
              "l'instant.", file=sys.stderr)
        return 1

    try:
        from pynput import keyboard
    except ImportError:
        print("Erreur : le module pynput n'est pas installé.", file=sys.stderr)
        print("Installez-le avec :", file=sys.stderr)
        print("  pip install -r scripts/requirements-etape4.txt",
              file=sys.stderr)
        return 3

    transcripteur = creer_transcripteur(config)
    cerveau = creer_cerveau(config)
    historique: list = []

    print("Boucle vocale Jarvis — prête.")
    print("Maintenez F9 pour parler, relâchez pour envoyer.")
    print("F9 pendant une réponse l'interrompt. Ctrl+C pour quitter.")
    print("Pensez à lancer la surveillance des minuteurs dans une autre "
          "fenêtre pour que les alarmes sonnent :")
    print("  python scripts\\minuteur.py surveiller")
    print()

    etat = {"phase": "repos"}  # repos | enregistrement | traitement | parle
    evenement_presse = threading.Event()
    evenement_relache = threading.Event()
    evenement_interruption = threading.Event()

    def on_press(touche):
        try:
            if touche == keyboard.Key.f9:
                if etat["phase"] == "parle":
                    evenement_interruption.set()
                elif etat["phase"] == "repos":
                    evenement_presse.set()
        except AttributeError:
            pass

    def on_release(touche):
        try:
            if touche == keyboard.Key.f9 \
                    and etat["phase"] == "enregistrement":
                evenement_relache.set()
        except AttributeError:
            pass

    ecouteur = keyboard.Listener(on_press=on_press, on_release=on_release)
    ecouteur.start()
    try:
        while True:
            evenement_presse.wait()
            evenement_presse.clear()
            if etat["phase"] != "repos":
                continue
            etat["phase"] = "enregistrement"
            evenement_relache.clear()
            print("🎙️  J'écoute… (relâchez F9 pour envoyer)", flush=True)
            try:
                octets, duree = enregistrer_jusqu_a_relache(
                    evenement_relache,
                    float(config["duree_max_enregistrement"]))
            except Exception as erreur:
                print(f"Erreur micro : {erreur}", file=sys.stderr)
                etat["phase"] = "repos"
                continue
            etat["phase"] = "traitement"
            if duree < float(config["duree_min_enregistrement"]):
                print("Trop court, ignoré.")
                etat["phase"] = "repos"
                continue
            try:
                transcription = transcripteur.transcrire(octets)
            except Exception as erreur:
                print(f"Erreur de transcription : {erreur}", file=sys.stderr)
                print("Réessayez en maintenant F9 un peu plus longtemps.")
                etat["phase"] = "repos"
                continue
            if not transcription.strip():
                print("Je n'ai rien compris — réessayez.")
                etat["phase"] = "repos"
                continue
            print(f"Julien : {transcription}")
            reponse = traiter_tour(transcription, config, cerveau,
                                   historique, args.donnees)
            historique.append({"role": "user", "content": transcription})
            historique.append({"role": "assistant", "content": reponse})
            historique = historique[-20:]
            etat["phase"] = "parle"
            evenement_interruption.clear()
            dire(reponse, str(config["langue"]), evenement_interruption)
            etat["phase"] = "repos"
    except KeyboardInterrupt:
        print("\nAu revoir, Julien.")
    finally:
        ecouteur.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
