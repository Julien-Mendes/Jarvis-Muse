#!/usr/bin/env python3
"""app.py — Application Jarvis (étape 7).

Vraie fenêtre d'application desktop moderne (CustomTkinter, thème sombre)
qui remplace à terme le HUD Tkinter (scripts/hud.py, étape 6 — jugé trop
« bancal » par Julien le 21 nov. 2026). L'ambiance reprend celle du Jarvis
de référence (dépôt Julian-Ivanov, frontend web) : fond très sombre, orbe
lumineux qui pulse selon l'état, conversation écrite en dessous.

Ce que montre la fenêtre :
  - En-tête : orbe d'état (repos / écoute / réflexion / réponse / erreur)
    + texte d'état + horloge locale (America/Toronto).
  - Zone de conversation défilante : bulles utilisateur / Jarvis avec
    horodatage, alimentée par le journal du jour
    (data/conversations/AAAA-MM-JJ.jsonl, écrit par la boucle vocale —
    étape 7.1 ; ancien data/conversation.jsonl lu en repli).
  - Panneau minuteurs : liste lue dans data/timers.json (lecture seule),
    avec comptes à rebours.
  - Bouton micro à maintenir enfoncé = push-to-talk (même mécanisme que
    le HUD : data/hud-ptt.json) ; bouton « Interrompre » pour couper la
    réponse en cours (comme F9 pendant une réponse).
  - Champ de saisie + bouton « Envoyer » (étape 7.1) : écrire à Jarvis
    au lieu de parler — le texte part dans data/texte-demande.json et
    la boucle le traite comme un tour vocal (réponse affichée et lue
    à voix haute).
  - Menu Fichier : Historique (fenêtre séparée, lecture seule, avec
    recherche), Ouvrir le guide, Quitter. Position et taille de la
    fenêtre mémorisées dans data/app.json.

Langue : les textes de la fenêtre principale suivent la langue de la
boucle vocale — [boucle] langue de config.toml, ou le champ optionnel
« langue » de data/hud-state.json quand la boucle l'écrit — en français
ou en anglais. La fenêtre Historique reste en français pour l'instant.

L'application n'est qu'une interface : la boucle vocale
(scripts/boucle_voix.py) doit tourner à côté (ou via
scripts/lancer_session.ps1) — c'est elle qui écoute, réfléchit et parle.
Aucun serveur, aucun port réseau : tout passe par des fichiers locaux
(data/, gitignorés), comme le HUD.

Usage :
    python scripts/app.py
    python scripts/app.py --verifier

Sécurité (docs/regles-securite.md) : aucune donnée sensible affichée —
pas de capture d'écran, pas de texte de page, pas de courriel ; seuls
l'état, l'heure, les minuteurs et la conversation avec Jarvis lui-même
sont montrés. Le journal de conversation est local uniquement (data/,
gitignoré) : c'est l'historique affiché sur la machine de Julien, pas
un journal de télémétrie (§7).
"""

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Modules voisins (config_jarvis.py…) importables même si ce fichier est
# chargé par chemin (tests, importlib) et non lancé comme script.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import config_jarvis  # noqa: E402

# Fuseau horaire : [general] fuseau_horaire de la configuration (K1).
FUSEAU = config_jarvis.fuseau()

RACINE = Path(__file__).resolve().parent.parent
FICHIER_ETAT = RACINE / "data" / "hud-state.json"
FICHIER_PTT = RACINE / "data" / "hud-ptt.json"
FICHIER_MINUTEURS = RACINE / "data" / "timers.json"
DOSSIER_CONVERSATIONS = RACINE / "data" / "conversations"
# Ancien journal unique (étape 7) : plus écrit par la boucle, lu en repli
# si le journal du jour n'existe pas encore.
FICHIER_CONVERSATION = RACINE / "data" / "conversation.jsonl"
FICHIER_DEMANDE_TEXTE = RACINE / "data" / "texte-demande.json"
FICHIER_POSITION = RACINE / "data" / "app.json"
GUIDE = RACINE / "docs" / "etape-7-application.md"
SCRIPT_BOUCLE = RACINE / "scripts" / "boucle_voix.py"

try:
    import tkinter as tk

    TKINTER_DISPONIBLE = True
except ImportError:  # pragma: no cover - environnement sans Tkinter.
    tk = None
    TKINTER_DISPONIBLE = False

try:
    import customtkinter as ctk

    CTK_DISPONIBLE = True
except ImportError:
    ctk = None
    CTK_DISPONIBLE = False

# Valeurs par défaut (surchargées par config.toml [app]).
DEFAUTS = {
    "active": True,
    "largeur": 900,
    "hauteur": 650,
    "toujours_au_premier_plan": False,
    "intervalle_ms": 500,
}

# Palette — ambiance du Jarvis de référence (Julian-Ivanov) : fond très
# sombre, accent bleu, orbe qui pulse (bleu écoute, doré réflexion,
# vert parole). Note : les couleurs d'état diffèrent volontairement de
# celles du HUD (étape 6 : vert écoute, bleu réponse) — l'application
# suit la palette des vidéos.
COULEUR_FOND = "#0a0a0f"
COULEUR_PANNEAU = "#14141d"
COULEUR_BULLE_JARVIS = "#1a1a26"
COULEUR_BULLE_UTILISATEUR = "#1a3a5c"
COULEUR_TEXTE = "#e0e0e0"
COULEUR_TEXTE_FAIBLE = "#888888"
COULEUR_ACCENT = "#4a9eff"
COULEUR_ACCENT_SURVOL = "#3a7bd5"
COULEUR_BARRE_DEFILEMENT = "#2a2a38"

ETATS = {
    # état : (texte affiché, couleur de l'orbe, période de pulsation en s)
    "repos": ("Jarvis prêt", "#5b7a99", 0.0),
    "ecoute": ("Écoute…", "#2a6cb8", 1.5),
    "reflexion": ("Réflexion…", "#c9a227", 0.8),
    "reponse": ("Réponse…", "#27c96a", 0.6),
    "erreur": ("Erreur", "#c0392b", 0.0),
    "arrete": ("Boucle arrêtée", "#666666", 0.0),
}
ETATS_CONNUS = ("repos", "ecoute", "reflexion", "reponse", "erreur")
FRAICHEUR_PTT = 2.0  # secondes : un fichier PTT plus vieux est périmé.

# Mise en page (lot U1 : polissage ; les couleurs ne changent pas).
ORBE_TAILLE = 116                 # côté du canevas de l'orbe, en pixels
ORBE_CENTRE = ORBE_TAILLE // 2
ORBE_RAYONS = (52, 40, 28)        # halo, milieu, cœur (échelle 1,0)
RAYON_BULLE = 14
MARGE_BULLE_PROCHE = 8            # côté de celui qui parle
MARGE_BULLE_LOIN = 72             # côté opposé : jamais pleine largeur
RESERVE_LARGEUR_BULLE = 124       # marges (80) + marges internes (28) + barre (16)
HAUTEUR_BOUTON_PRINCIPAL = 54     # micro et Interrompre
LARGEUR_BOUTON_COLONNE = 150      # Interrompre et Envoyer : même colonne
HAUTEUR_SAISIE = 42               # champ texte et Envoyer
DELAI_REFLUX_MS = 120             # retour à la ligne des bulles (anti-rebond)
DELAI_GEOMETRIE_MS = 800          # mémorisation de la géométrie (anti-rebond)
PAS_ANIMATION_MS = 90             # orbe qui pulse
PAS_REPOS_MS = 200                # orbe au repos : surveillance, aucun dessin
LARGEUR_FENETRE_MIN = 640
HAUTEUR_FENETRE_MIN = 520         # garde ~210 px à la conversation (orbe 116 px)

LANGUES = ("fr", "en")

# Textes de la fenêtre principale, par langue. Les clés « etat_* » et
# « detail_* » correspondent aux états de ETATS. La fenêtre Historique n'est
# pas encore traduite.
TEXTES = {
    "fr": {
        "etat_repos": "Jarvis est prêt",
        "etat_ecoute": "Écoute en cours…",
        "etat_reflexion": "Réflexion en cours…",
        "etat_reponse": "Jarvis répond…",
        "etat_erreur": "Une erreur est survenue",
        "etat_arrete": "Boucle vocale arrêtée",
        "detail_repos": "Maintenez F9 ou le bouton micro pour parler.",
        "detail_ecoute": "Parlez, puis relâchez F9 (ou le bouton) pour envoyer.",
        "detail_reflexion": "Jarvis prépare sa réponse…",
        "detail_reponse": "F9 ou « Interrompre » pour couper la réponse.",
        "detail_erreur": "Réessayez en maintenant F9.",
        "detail_erreur_prefixe": "Erreur : ",
        "detail_arrete": ("Lancez python scripts\\boucle_voix.py "
                          "(ou la session Jarvis) pour démarrer."),
        "micro_repos": "Maintenir pour parler",
        "micro_actif": "Écoute en cours…",
        "interrompre": "Interrompre",
        "astuce": "ou maintenez F9",
        "placeholder": "Écrire à Jarvis…",
        "envoyer": "Envoyer",
        "minuteurs": "Minuteurs",
        "aucun_minuteur": "Aucun minuteur en cours.",
        "minuteur_reste": "• {quoi} : dans {duree}",
        "minuteur_echu": "• {quoi} : échue",
        "echue": "échue",
        "menu_fichier": "Fichier",
        "menu_historique": "Historique…",
        "menu_guide": "Ouvrir le guide",
        "menu_quitter": "Quitter",
        "vide": ("Aucune conversation pour l'instant.\n"
                 "Maintenez F9 (ou le bouton micro) pour parler à Jarvis,\n"
                 "ou écrivez votre message ci-dessous."),
    },
    "en": {
        "etat_repos": "Jarvis is ready",
        "etat_ecoute": "Listening…",
        "etat_reflexion": "Thinking…",
        "etat_reponse": "Jarvis is answering…",
        "etat_erreur": "Something went wrong",
        "etat_arrete": "Voice loop stopped",
        "detail_repos": "Hold F9 or the mic button to talk.",
        "detail_ecoute": "Speak, then release F9 (or the button) to send.",
        "detail_reflexion": "Jarvis is preparing an answer…",
        "detail_reponse": "Press F9 or “Interrupt” to cut the answer short.",
        "detail_erreur": "Try again by holding F9.",
        "detail_erreur_prefixe": "Error: ",
        "detail_arrete": ("Start it with python scripts\\boucle_voix.py "
                          "(or the Jarvis session)."),
        "micro_repos": "Hold to talk",
        "micro_actif": "Listening…",
        "interrompre": "Interrupt",
        "astuce": "or hold F9",
        "placeholder": "Write to Jarvis…",
        "envoyer": "Send",
        "minuteurs": "Timers",
        "aucun_minuteur": "No timers running.",
        "minuteur_reste": "• {quoi}: in {duree}",
        "minuteur_echu": "• {quoi}: expired",
        "echue": "expired",
        "menu_fichier": "File",
        "menu_historique": "History…",
        "menu_guide": "Open the guide",
        "menu_quitter": "Quit",
        "vide": ("No conversation yet.\n"
                 "Hold F9 (or the mic button) to talk to Jarvis,\n"
                 "or type your message below."),
    },
}
# Nom affiché d'un minuteur sans étiquette (« kind » du fichier timers.json).
GENRES_MINUTEUR = {
    "fr": {"timer": "minuteur", "rappel": "rappel"},
    "en": {"timer": "timer", "rappel": "reminder"},
}


def _texte(langue: str, cle: str) -> str:
    """Texte de l'interface dans la langue donnée (anglais si inconnue)."""
    return TEXTES.get(langue, TEXTES["en"])[cle]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def charger_config_app(racine: Path) -> dict:
    """Lit config.toml [app], sinon config.example.toml, sinon défauts."""
    config = dict(DEFAUTS)
    config["langue"] = "en"  # défaut du projet ; voir [boucle] langue
    fichier = racine / "config" / "config.toml"
    if not fichier.exists():
        fichier = racine / "config" / "config.example.toml"
    if fichier.exists():
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                tomllib = None
        if tomllib is not None:
            try:
                donnees = tomllib.loads(fichier.read_text(encoding="utf-8"))
                app = donnees.get("app", {})
                for cle in DEFAUTS:
                    if cle in app:
                        config[cle] = app[cle]
                # Langue de l'interface = langue de la boucle vocale : même
                # lecture que partout (config_jarvis, K1 : [general] langue ;
                # l'ancien [boucle] langue reste respecté).
                langue = config_jarvis.langue(
                    config_jarvis.charger_donnees(racine / "config"))
                if langue in LANGUES:
                    config["langue"] = langue
            except (ValueError, OSError):
                pass
    try:
        config["largeur"] = max(640, min(1600, int(config["largeur"])))
    except (TypeError, ValueError):
        config["largeur"] = 900
    try:
        config["hauteur"] = max(480, min(1200, int(config["hauteur"])))
    except (TypeError, ValueError):
        config["hauteur"] = 650
    try:
        config["intervalle_ms"] = max(
            200, min(2000, int(config["intervalle_ms"])))
    except (TypeError, ValueError):
        config["intervalle_ms"] = 500
    return config


# ---------------------------------------------------------------------------
# Fichiers d'état (lecture tolérante — un fichier absent n'est pas une erreur)
# ---------------------------------------------------------------------------

def lire_etat(chemin: Path = FICHIER_ETAT) -> dict:
    """Lit data/hud-state.json ; état « arrete » si le fichier est absent
    (la boucle vocale n'a jamais écrit d'état), « repos » par défaut sinon.
    """
    defaut = {"etat": "arrete", "transcription": "", "erreur": "",
              "langue": "", "present": False}
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaut
    if not isinstance(donnees, dict):
        return defaut
    etat = str(donnees.get("etat", "repos"))
    if etat not in ETATS_CONNUS:
        etat = "repos"
    langue = str(donnees.get("langue", ""))
    return {
        "etat": etat,
        "transcription": str(donnees.get("transcription", "")),
        "erreur": str(donnees.get("erreur", "")),
        # Champ optionnel : écrit par la boucle quand elle détecte la langue
        # parlée du moment ; vide = rester sur la langue de la config.
        "langue": langue if langue in LANGUES else "",
        "present": True,
    }


def _analyser_echeance(valeur) -> datetime | None:
    """Parse une échéance ISO (avec ou sans fuseau) ; None si invalide."""
    try:
        moment = datetime.fromisoformat(str(valeur))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=FUSEAU)
    return moment


def charger_minuteurs(chemin: Path = FICHIER_MINUTEURS) -> list:
    """Lit data/timers.json (lecture seule) ; liste triée par échéance.

    Chaque élément : {"due": datetime, "label": str, "kind": str}.
    Fichier absent ou illisible : liste vide.
    """
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        minuteurs = donnees.get("timers", [])
    except (OSError, ValueError, AttributeError):
        return []
    resultat = []
    for minuteur in minuteurs:
        if not isinstance(minuteur, dict):
            continue
        due = _analyser_echeance(minuteur.get("due"))
        if due is None:
            continue
        resultat.append({
            "due": due,
            "label": str(minuteur.get("label", "")),
            "kind": str(minuteur.get("kind", "timer")),
        })
    resultat.sort(key=lambda m: m["due"])
    return resultat


def formater_compte_a_rebours(secondes: float, langue: str = "fr") -> str:
    """« 45 s », « 12 min », « 1 h 05 », « échue » (« expired » en anglais)."""
    if secondes < 0:
        return _texte(langue, "echue")
    if secondes < 60:
        return f"{int(secondes)} s"
    if secondes < 3600:
        return f"{int(secondes // 60)} min"
    heures = int(secondes // 3600)
    minutes = int((secondes % 3600) // 60)
    return f"{heures} h {minutes:02d}"


def formater_minuteurs(minuteurs: list, ref: datetime,
                       langue: str = "fr") -> tuple:
    """Lignes « <étiquette> : dans 12 min » pour le panneau minuteurs."""
    genres = GENRES_MINUTEUR.get(langue, GENRES_MINUTEUR["en"])
    lignes = []
    for minuteur in minuteurs:
        reste = (minuteur["due"] - ref).total_seconds()
        quoi = minuteur["label"] or genres.get(minuteur["kind"],
                                               minuteur["kind"])
        if reste < 0:
            lignes.append(_texte(langue, "minuteur_echu").format(quoi=quoi))
        else:
            lignes.append(_texte(langue, "minuteur_reste").format(
                quoi=quoi,
                duree=formater_compte_a_rebours(reste, langue)))
    return tuple(lignes) if lignes else (_texte(langue, "aucun_minuteur"),)


def ecrire_ptt(chemin: Path, actif: bool) -> None:
    """Écrit data/hud-ptt.json (atomique) : micro maintenu ou relâché.

    Même fichier que le HUD (étape 6) : la boucle vocale le sonde toutes
    les 0,2 s — un appui maintenu démarre l'enregistrement, un appui
    pendant une réponse l'interrompt (comme F9).
    """
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        donnees = {
            "actif": bool(actif),
            "horodatage": datetime.now(FUSEAU).isoformat(timespec="seconds"),
        }
        temporaire = chemin.with_suffix(".json.tmp")
        temporaire.write_text(
            json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
        os.replace(temporaire, chemin)
    except OSError:
        pass


def chemin_journal_jour(jour: datetime | None = None) -> Path:
    """Chemin du journal du jour : data/conversations/AAAA-MM-JJ.jsonl."""
    ref = jour or datetime.now(FUSEAU)
    return DOSSIER_CONVERSATIONS / f"{ref.strftime('%Y-%m-%d')}.jsonl"


def lire_conversation(chemin: Path | None = None) -> list:
    """Lit un journal de conversation ; liste de {"role", "texte", "heure"}.

    Sans chemin : le journal du jour s'il existe, sinon l'ancien journal
    unique data/conversation.jsonl (étape 7, repli). Lignes mal formées
    ignorées. Fichier absent : liste vide.
    """
    if chemin is None:
        chemin = chemin_journal_jour()
        if not chemin.exists():
            chemin = FICHIER_CONVERSATION
    try:
        lignes = chemin.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entrees = []
    for ligne in lignes:
        ligne = ligne.strip()
        if not ligne:
            continue
        try:
            donnees = json.loads(ligne)
        except ValueError:
            continue
        if not isinstance(donnees, dict):
            continue
        role = str(donnees.get("role", ""))
        if role not in ("user", "jarvis"):
            continue
        entrees.append({
            "role": role,
            "texte": str(donnees.get("texte", "")),
            "heure": str(donnees.get("heure", "")),
        })
    return entrees


JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi",
            "dimanche"]
MOIS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.",
           "août", "sept.", "oct.", "nov.", "déc."]


def formater_jour(date_iso: str) -> str:
    """« sam. 21 nov. 2026 » à partir de « 2026-11-21 » ; tel quel sinon."""
    try:
        moment = datetime.strptime(date_iso, "%Y-%m-%d")
    except ValueError:
        return date_iso
    return (f"{JOURS_FR[moment.weekday()][:3]}. {moment.day} "
            f"{MOIS_FR[moment.month - 1]} {moment.year}")


def lister_jours(racine: Path = RACINE) -> list:
    """Jours avec un journal : [{"date", "chemin", "messages"}].

    Du plus récent au plus ancien. L'ancien journal unique
    (data/conversation.jsonl, étape 7) apparaît en dernier sous
    « Ancien journal » s'il contient des messages. Dossier absent :
    liste vide.
    """
    jours = []
    dossier = racine / "data" / "conversations"
    try:
        fichiers = sorted(dossier.glob("????-??-??.jsonl"), reverse=True)
    except OSError:
        fichiers = []
    for fichier in fichiers:
        entrees = lire_conversation(fichier)
        if entrees:
            jours.append({"date": fichier.stem, "chemin": fichier,
                          "messages": len(entrees)})
    try:
        anciennes = lire_conversation(FICHIER_CONVERSATION)
    except OSError:
        anciennes = []
    if anciennes:
        jours.append({"date": "Ancien journal",
                      "chemin": FICHIER_CONVERSATION,
                      "messages": len(anciennes)})
    return jours


def filtrer_entrees(entrees: list, requete: str) -> list:
    """Filtre des entrées de conversation par texte (insensible à la casse).

    Requête vide : toutes les entrées. La recherche porte sur le texte
    des messages, pas sur les rôles ni les heures.
    """
    requete = (requete or "").strip().lower()
    if not requete:
        return list(entrees)
    return [e for e in entrees if requete in str(e.get("texte", "")).lower()]


def ecrire_demande_texte(chemin: Path, texte: str) -> None:
    """Écrit une demande texte pour la boucle (data/texte-demande.json).

    {"texte": ..., "horodatage": "ISO"} — écriture atomique (fichier
    temporaire + os.replace). La boucle vocale le sonde toutes les
    0,2 s et le consomme (le fichier est supprimé à la lecture). Toute
    erreur est silencieuse : l'envoi ne doit jamais faire planter
    l'application.
    """
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        donnees = {
            "texte": str(texte),
            "horodatage": datetime.now(FUSEAU).isoformat(timespec="seconds"),
        }
        temporaire = chemin.with_suffix(".json.tmp")
        temporaire.write_text(
            json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
        os.replace(temporaire, chemin)
    except OSError:
        pass


_POLICES: dict = {}


def _police(taille: int, gras: bool = False):
    """Police Segoe UI partagée : une seule par (taille, graisse), au lieu
    d'une par étiquette (la conversation compte jusqu'à 200 bulles)."""
    cle = (taille, gras)
    if cle not in _POLICES:
        _POLICES[cle] = ctk.CTkFont(family="Segoe UI", size=taille,
                                    weight="bold" if gras else "normal")
    return _POLICES[cle]


def ajouter_bulle(conteneur, entree: dict, wraplength: int,
                  role_precedent: str | None = None):
    """Crée une bulle (utilisateur à droite, Jarvis à gauche) dans un
    conteneur ; retourne l'étiquette du texte (pour ajuster le retour à
    la ligne au redimensionnement).

    `role_precedent` (optionnel) : rôle de la bulle juste au-dessus ; plus
    d'air quand l'interlocuteur change.
    """
    if entree["role"] == "user":
        couleur_bulle = COULEUR_BULLE_UTILISATEUR
        ancre = "e"
        marges = (MARGE_BULLE_LOIN, MARGE_BULLE_PROCHE)
    else:
        couleur_bulle = COULEUR_BULLE_JARVIS
        ancre = "w"
        marges = (MARGE_BULLE_PROCHE, MARGE_BULLE_LOIN)
    interlocuteur_change = (role_precedent is not None
                            and role_precedent != entree["role"])
    cadre = ctk.CTkFrame(conteneur, fg_color=couleur_bulle,
                         corner_radius=RAYON_BULLE)
    cadre.pack(anchor=ancre, padx=marges,
               pady=(10 if interlocuteur_change else 3, 3))
    heure = formater_heure(entree["heure"])
    etiquette = ctk.CTkLabel(
        cadre, text=entree["texte"], font=_police(14),
        text_color=COULEUR_TEXTE, wraplength=wraplength,
        justify="left", anchor="w")
    etiquette.pack(fill="x", padx=14, pady=(10, 0) if heure else (10, 10))
    if heure:
        ctk.CTkLabel(
            cadre, text=heure, font=_police(10),
            text_color=COULEUR_TEXTE_FAIBLE, anchor="e").pack(
                fill="x", padx=14, pady=(2, 8))
    return etiquette


def formater_heure(heure_iso: str) -> str:
    """« 21:47 » à partir d'une heure ISO ; « » si invalide."""
    try:
        moment = datetime.fromisoformat(heure_iso)
    except ValueError:
        return ""
    return moment.strftime("%H:%M")


def _assombrir(couleur_hex: str, facteur: float) -> str:
    """Assombrit une couleur #RRGGBB (facteur 0.0 à 1.0)."""
    try:
        r = int(couleur_hex[1:3], 16)
        g = int(couleur_hex[3:5], 16)
        b = int(couleur_hex[5:7], 16)
    except (ValueError, IndexError):
        return couleur_hex
    r = int(r * facteur)
    g = int(g * facteur)
    b = int(b * facteur)
    return f"#{r:02x}{g:02x}{b:02x}"


# ---------------------------------------------------------------------------
# Position et taille mémorisées (data/app.json, gitignoré)
# ---------------------------------------------------------------------------

def charger_geometrie(racine: Path) -> str | None:
    """Lit la géométrie mémorisée (« 900x650+120+80 ») ou None.

    Seules les géométries bien formées sont acceptées : un fichier
    corrompu ne doit jamais empêcher le lancement.
    """
    import re

    try:
        donnees = json.loads(
            (racine / "data" / "app.json").read_text(encoding="utf-8"))
        geometrie = str(donnees.get("geometrie", ""))
        if re.fullmatch(r"\d+x\d+[+-]\d+[+-]\d+", geometrie):
            return geometrie
        return None
    except (OSError, ValueError, AttributeError):
        return None


def sauvegarder_geometrie(racine: Path, geometrie: str) -> None:
    """Mémorise la géométrie de la fenêtre (atomique, silencieux)."""
    try:
        dossier = racine / "data"
        dossier.mkdir(parents=True, exist_ok=True)
        chemin = dossier / "app.json"
        temporaire = chemin.with_suffix(".json.tmp")
        temporaire.write_text(json.dumps(
            {"geometrie": str(geometrie)}, ensure_ascii=False),
            encoding="utf-8")
        os.replace(temporaire, chemin)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Application CustomTkinter
# ---------------------------------------------------------------------------

class Application:
    """Fenêtre Jarvis : orbe d'état, conversation, minuteurs, micro,
    saisie texte et fenêtre Historique séparée.

    Bouton micro maintenu = push-to-talk (équivalent F9). Bouton
    « Interrompre » = impulsion courte sur data/hud-ptt.json, qui coupe
    la réponse en cours (comme F9 pendant une réponse). Le champ de
    saisie envoie un message texte à la boucle (data/texte-demande.json).
    """

    def __init__(self, racine: Path, config: dict):
        self.racine = racine
        self.config = config
        ctk.set_appearance_mode("dark")

        self.fenetre = ctk.CTk()
        self.fenetre.title("Jarvis")
        geometrie = charger_geometrie(racine)
        if geometrie:
            self.fenetre.geometry(geometrie)
        else:
            self.fenetre.geometry(
                f"{config['largeur']}x{config['hauteur']}")
        self.fenetre.minsize(LARGEUR_FENETRE_MIN, HAUTEUR_FENETRE_MIN)
        if config.get("toujours_au_premier_plan", False):
            self.fenetre.attributes("-topmost", True)
        self.fenetre.protocol("WM_DELETE_WINDOW", self.quitter)

        self.langue = str(config.get("langue", "en"))
        if self.langue not in LANGUES:
            self.langue = "en"
        self.etat_affiche = "arrete"
        self._entrees_affichees: list = []
        self._texte_minuteurs: tuple = ()
        self._micro_enfonce = False
        self._etiquettes_bulles: list = []
        self._apres_redimensionnement = None
        self._apres_geometrie = None
        self._derniere_largeur = 0
        self._horloge_affichee = ""
        self._message_vide = None
        self._fenetre_historique = None
        self._historique: dict | None = None

        # -- Menu ------------------------------------------------------
        self._barre_menu = tk.Menu(self.fenetre)
        self._menu_fichier = tk.Menu(self._barre_menu, tearoff=0)
        self._menu_fichier.add_command(label=self.t("menu_historique"),
                                       command=self.ouvrir_historique)
        self._menu_fichier.add_command(label=self.t("menu_guide"),
                                       command=self.ouvrir_guide)
        self._menu_fichier.add_separator()
        self._menu_fichier.add_command(label=self.t("menu_quitter"),
                                       command=self.quitter)
        self._barre_menu.add_cascade(label=self.t("menu_fichier"),
                                     menu=self._menu_fichier)
        self.fenetre.config(menu=self._barre_menu)

        # -- Grille principale -----------------------------------------
        self.fenetre.grid_rowconfigure(1, weight=1)
        self.fenetre.grid_columnconfigure(0, weight=1)

        # -- En-tête : orbe + état + horloge ---------------------------
        self.entete = ctk.CTkFrame(
            self.fenetre, fg_color=COULEUR_PANNEAU, corner_radius=0)
        self.entete.grid(row=0, column=0, sticky="ew")
        self.entete.grid_columnconfigure(1, weight=1)
        # Les deux lignes de texte se partagent la hauteur de l'orbe : le
        # bloc de texte reste centré en face de lui.
        self.entete.grid_rowconfigure(0, weight=1)
        self.entete.grid_rowconfigure(1, weight=1)

        self.canvas_orbe = tk.Canvas(
            self.entete, width=ORBE_TAILLE, height=ORBE_TAILLE,
            bg=COULEUR_PANNEAU, highlightthickness=0, bd=0)
        self.canvas_orbe.grid(row=0, column=0, rowspan=2,
                              padx=(20, 6), pady=12)
        (self._orbe_halo, self._orbe_milieu,
         self._orbe_coeur) = (
            self.canvas_orbe.create_oval(
                ORBE_CENTRE - r, ORBE_CENTRE - r,
                ORBE_CENTRE + r, ORBE_CENTRE + r, fill="", outline="")
            for r in ORBE_RAYONS)

        self.texte_etat = ctk.CTkLabel(
            self.entete, text=self.t("etat_arrete"), font=_police(20, True),
            text_color=COULEUR_TEXTE, anchor="w")
        self.texte_etat.grid(row=0, column=1, sticky="sw", padx=10,
                             pady=(0, 2))
        self.texte_detail = ctk.CTkLabel(
            self.entete, text=self.t("detail_arrete"), font=_police(12),
            text_color=COULEUR_TEXTE_FAIBLE, anchor="w", justify="left",
            wraplength=max(220, config["largeur"] - 340))
        self.texte_detail.grid(row=1, column=1, sticky="nw", padx=10,
                               pady=(2, 0))

        self.texte_horloge = ctk.CTkLabel(
            self.entete, text="--:--:--", font=_police(24, True),
            text_color=COULEUR_TEXTE)
        self.texte_horloge.grid(row=0, column=2, rowspan=2, padx=24, pady=12)

        # -- Zone centrale : conversation + minuteurs -------------------
        self.centre = ctk.CTkFrame(self.fenetre, fg_color=COULEUR_FOND,
                                   corner_radius=0)
        self.centre.grid(row=1, column=0, sticky="nsew")
        self.centre.grid_rowconfigure(0, weight=1)
        self.centre.grid_columnconfigure(0, weight=1)

        try:
            self.zone_conversation = ctk.CTkScrollableFrame(
                self.centre, fg_color=COULEUR_FOND, corner_radius=0,
                scrollbar_fg_color=COULEUR_FOND,
                scrollbar_button_color=COULEUR_BARRE_DEFILEMENT,
                scrollbar_button_hover_color=COULEUR_TEXTE_FAIBLE)
        except (TypeError, ValueError, tk.TclError):
            # Version de CustomTkinter sans ces options : barre d'origine.
            self.zone_conversation = ctk.CTkScrollableFrame(
                self.centre, fg_color=COULEUR_FOND, corner_radius=0,
                scrollbar_button_color=COULEUR_BARRE_DEFILEMENT)
        try:  # Barre fine (attribut interne : au mieux, sans incidence).
            self.zone_conversation._scrollbar.configure(width=8)
        except Exception:
            pass
        self.zone_conversation.grid(row=0, column=0, sticky="nsew",
                                    padx=(8, 0), pady=8)
        self.zone_conversation.bind(
            "<Configure>", self._sur_redimensionnement)

        self.panneau_minuteurs = ctk.CTkFrame(
            self.centre, fg_color=COULEUR_PANNEAU, corner_radius=12)
        self.panneau_minuteurs.grid(row=0, column=1, sticky="ns",
                                    padx=8, pady=8)
        self.panneau_minuteurs.configure(width=230)
        self.titre_minuteurs = ctk.CTkLabel(
            self.panneau_minuteurs, text=self.t("minuteurs"),
            font=_police(14, True), text_color=COULEUR_TEXTE, anchor="w")
        self.titre_minuteurs.pack(fill="x", padx=12, pady=(10, 2))
        self.conteneur_minuteurs = ctk.CTkFrame(
            self.panneau_minuteurs, fg_color="transparent")
        self.conteneur_minuteurs.pack(fill="x", padx=4, pady=(0, 10))

        # -- Barre du bas : micro + interruption ------------------------
        self.barre_bas = ctk.CTkFrame(
            self.fenetre, fg_color=COULEUR_PANNEAU, corner_radius=0)
        self.barre_bas.grid(row=2, column=0, sticky="ew")
        self.barre_bas.grid_columnconfigure(0, weight=1)

        self.bouton_micro = ctk.CTkButton(
            self.barre_bas, text=self.t("micro_repos"), font=_police(16, True),
            fg_color=COULEUR_ACCENT, hover_color=COULEUR_ACCENT_SURVOL,
            text_color="#ffffff",
            corner_radius=HAUTEUR_BOUTON_PRINCIPAL // 2,
            height=HAUTEUR_BOUTON_PRINCIPAL)
        self.bouton_micro.grid(row=0, column=0, sticky="ew",
                               padx=(16, 8), pady=(12, 4))
        self.bouton_micro.bind("<ButtonPress-1>", self._micro_presse)
        self.bouton_micro.bind("<ButtonRelease-1>", self._micro_relache)

        self.bouton_interrompre = ctk.CTkButton(
            self.barre_bas, text=self.t("interrompre"), font=_police(14),
            fg_color="transparent", hover_color="#2a1a1a",
            text_color="#e07878", border_width=1,
            border_color="#7a3a3a",
            corner_radius=HAUTEUR_BOUTON_PRINCIPAL // 2,
            height=HAUTEUR_BOUTON_PRINCIPAL, width=LARGEUR_BOUTON_COLONNE,
            command=self.interrompre)
        self.bouton_interrompre.grid(row=0, column=1, padx=(8, 16),
                                     pady=(12, 4))

        self.texte_astuce = ctk.CTkLabel(
            self.barre_bas, text=self.t("astuce"), font=_police(11),
            text_color=COULEUR_TEXTE_FAIBLE)
        self.texte_astuce.grid(row=1, column=0, columnspan=2, pady=(0, 2))

        # -- Barre du bas : saisie texte (étape 7.1) --------------------
        self.champ_texte = ctk.CTkEntry(
            self.barre_bas, placeholder_text=self.t("placeholder"),
            font=_police(14), height=HAUTEUR_SAISIE)
        self.champ_texte.grid(row=2, column=0, sticky="ew",
                              padx=(16, 8), pady=(4, 14))
        self.champ_texte.bind("<Return>", lambda _e: self.envoyer_texte())

        self.bouton_envoyer = ctk.CTkButton(
            self.barre_bas, text=self.t("envoyer"), font=_police(14, True),
            fg_color=COULEUR_ACCENT, hover_color=COULEUR_ACCENT_SURVOL,
            text_color="#ffffff", corner_radius=HAUTEUR_SAISIE // 2,
            height=HAUTEUR_SAISIE, width=LARGEUR_BOUTON_COLONNE,
            command=self.envoyer_texte)
        self.bouton_envoyer.grid(row=2, column=1, padx=(8, 16), pady=(4, 14))

        self._dessiner_orbe(1.0)
        self.rafraichir()
        self._animer_orbe()

    # -- Langue --------------------------------------------------------

    def t(self, cle: str) -> str:
        """Texte de l'interface dans la langue courante."""
        return _texte(self.langue, cle)

    def _appliquer_langue(self) -> None:
        """Applique la langue courante aux textes fixes de la fenêtre. Les
        textes d'état, de minuteurs et la conversation se rafraîchissent
        seuls au prochain passage de rafraichir()."""
        def vider_minuteurs():
            self._texte_minuteurs = ()  # force la reconstruction du panneau

        def message_vide():
            if self._message_vide is not None:
                self._message_vide.configure(text=self.t("vide"))

        mises_a_jour = (
            lambda: self._barre_menu.entryconfigure(
                0, label=self.t("menu_fichier")),
            lambda: self._menu_fichier.entryconfigure(
                0, label=self.t("menu_historique")),
            lambda: self._menu_fichier.entryconfigure(
                1, label=self.t("menu_guide")),
            lambda: self._menu_fichier.entryconfigure(
                3, label=self.t("menu_quitter")),
            lambda: self.titre_minuteurs.configure(text=self.t("minuteurs")),
            lambda: self.bouton_interrompre.configure(
                text=self.t("interrompre")),
            lambda: self.texte_astuce.configure(text=self.t("astuce")),
            lambda: self.bouton_envoyer.configure(text=self.t("envoyer")),
            lambda: self.champ_texte.configure(
                placeholder_text=self.t("placeholder")),
            lambda: self._style_micro(self._micro_enfonce),
            message_vide,
            vider_minuteurs,
        )
        for mise_a_jour in mises_a_jour:
            try:
                mise_a_jour()
            except Exception as erreur:  # Un texte non traduit n'est pas grave.
                print(f"Avertissement application : {erreur}",
                      file=sys.stderr)

    # -- Orbe ----------------------------------------------------------

    def _dessiner_orbe(self, echelle: float) -> None:
        """Redessine l'orbe (halo + milieu + cœur) à l'échelle donnée."""
        couleur = ETATS[self.etat_affiche][1]
        for item, rayon, facteur in zip(
                (self._orbe_halo, self._orbe_milieu, self._orbe_coeur),
                ORBE_RAYONS, (0.30, 0.60, 1.0)):
            r = rayon * echelle
            self.canvas_orbe.coords(
                item, ORBE_CENTRE - r, ORBE_CENTRE - r,
                ORBE_CENTRE + r, ORBE_CENTRE + r)
            self.canvas_orbe.itemconfig(
                item, fill=_assombrir(couleur, facteur), outline="")

    def _animer_orbe(self) -> None:
        """Pulsation de l'orbe selon l'état (comme le frontend de
        référence : écoute 1,5 s, réflexion 0,8 s, réponse 0,6 s).

        Au repos (période nulle) rien n'est redessiné : l'orbe reste tel
        que rafraichir() l'a dessiné au dernier changement d'état, et on
        ne fait que surveiller l'état toutes les 200 ms.
        """
        delai = PAS_REPOS_MS
        try:
            periode = ETATS[self.etat_affiche][2]
            if periode > 0:
                phase = (time.monotonic() % periode) / periode
                self._dessiner_orbe(1.0 + 0.07 * math.sin(2 * math.pi * phase))
                delai = PAS_ANIMATION_MS
        except Exception:
            pass
        finally:
            self.fenetre.after(delai, self._animer_orbe)

    # -- Conversation --------------------------------------------------

    def _ajouter_message(self, entree: dict) -> None:
        """Ajoute une bulle (utilisateur à droite, Jarvis à gauche)."""
        if self._message_vide is not None:
            self._message_vide.destroy()
            self._message_vide = None
        precedent = (self._entrees_affichees[-1]["role"]
                     if self._entrees_affichees else None)
        etiquette = ajouter_bulle(self.zone_conversation, entree,
                                  self._largeur_bulle(), precedent)
        self._etiquettes_bulles.append(etiquette)
        self._entrees_affichees.append(entree)

    def _largeur_bulle(self) -> int:
        """Largeur de retour à la ligne des bulles, selon la fenêtre."""
        try:
            largeur = self.zone_conversation.winfo_width()
        except Exception:
            largeur = 600
        return max(240, largeur - RESERVE_LARGEUR_BULLE)

    def _defiler_bas(self) -> None:
        """Défile la conversation tout en bas (au mieux : l'API interne
        de CTkScrollableFrame peut changer d'une version à l'autre)."""
        try:
            self.zone_conversation._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _reconstruire_conversation(self, entrees: list) -> None:
        """Efface et ré-affiche toute la conversation (après un
        raccourcissement du journal, ex. plafond de 200 lignes)."""
        for enfant in self.zone_conversation.winfo_children():
            enfant.destroy()
        self._entrees_affichees = []
        self._etiquettes_bulles = []
        self._message_vide = None
        for entree in entrees:
            self._ajouter_message(entree)
        if not entrees:
            self._afficher_message_vide()
        self._defiler_bas()

    def _afficher_message_vide(self) -> None:
        """Message d'accueil quand le journal est vide."""
        if self._message_vide is not None:
            return
        self._message_vide = ctk.CTkLabel(
            self.zone_conversation, text=self.t("vide"), font=_police(14),
            text_color=COULEUR_TEXTE_FAIBLE, justify="center")
        self._message_vide.pack(pady=40)

    # -- Minuteurs -----------------------------------------------------

    def _rafraichir_minuteurs(self, minuteurs: list, ref: datetime) -> None:
        """Reconstruit le panneau minuteurs seulement si le texte change."""
        lignes = formater_minuteurs(minuteurs, ref, self.langue)
        if lignes == self._texte_minuteurs:
            return
        self._texte_minuteurs = lignes
        for enfant in self.conteneur_minuteurs.winfo_children():
            enfant.destroy()
        for ligne in lignes:
            ctk.CTkLabel(
                self.conteneur_minuteurs, text=ligne, font=_police(12),
                text_color=COULEUR_TEXTE, anchor="w",
                justify="left").pack(fill="x", padx=8, pady=2)

    # -- Micro : push-to-talk et interruption --------------------------

    def _style_micro(self, enfonce: bool) -> None:
        """Bouton micro bien visible quand il est maintenu : couleur de
        l'état « écoute » (celle de l'orbe) + liseré clair."""
        if enfonce:
            couleur = ETATS["ecoute"][1]
            self.bouton_micro.configure(
                text=self.t("micro_actif"), fg_color=couleur,
                hover_color=couleur, border_width=2,
                border_color=COULEUR_TEXTE)
        else:
            self.bouton_micro.configure(
                text=self.t("micro_repos"), fg_color=COULEUR_ACCENT,
                hover_color=COULEUR_ACCENT_SURVOL, border_width=0)

    def _micro_presse(self, _evenement=None) -> None:
        self._micro_enfonce = True
        ecrire_ptt(FICHIER_PTT, True)
        self._style_micro(True)

    def _micro_relache(self, _evenement=None) -> None:
        self._micro_enfonce = False
        ecrire_ptt(FICHIER_PTT, False)
        self._style_micro(False)

    def interrompre(self) -> None:
        """Impulsion courte sur data/hud-ptt.json : coupe la réponse en
        cours (la boucle ne réagit qu'au front montant, comme F9)."""
        ecrire_ptt(FICHIER_PTT, True)
        self.fenetre.after(400, lambda: ecrire_ptt(FICHIER_PTT, False))

    def envoyer_texte(self) -> None:
        """Envoie le texte tapé à la boucle (data/texte-demande.json).

        La boucle le traite comme un tour vocal : réponse affichée dans
        la conversation et lue à voix haute. Si la boucle ne tourne pas,
        la demande expire après 5 minutes (elle est alors ignorée) —
        la boucle doit tourner pour que le message reçoive une réponse.
        """
        texte = self.champ_texte.get().strip()
        if not texte:
            return
        ecrire_demande_texte(FICHIER_DEMANDE_TEXTE, texte)
        self.champ_texte.delete(0, "end")

    # -- Historique (fenêtre séparée, lecture seule) -------------------

    def ouvrir_historique(self) -> None:
        """Ouvre la fenêtre Historique (jours + recherche + relecture).

        Fenêtre séparée de l'écran principal : liste des jours (du plus
        récent au plus ancien), champ de recherche qui filtre les
        messages du jour affiché, conversation en lecture seule. Si la
        fenêtre est déjà ouverte, elle est simplement ramenée au premier
        plan.
        """
        existante = getattr(self, "_fenetre_historique", None)
        if existante is not None:
            try:
                if existante.winfo_exists():
                    existante.lift()
                    existante.focus()
                    return
            except Exception:
                pass
        fenetre = ctk.CTkToplevel(self.fenetre)
        fenetre.title("Historique — Jarvis")
        fenetre.geometry("820x600")
        fenetre.minsize(560, 400)
        self._fenetre_historique = fenetre
        self._historique = {"jours": lister_jours(self.racine),
                            "courant": None, "entrees": []}

        fenetre.grid_rowconfigure(1, weight=1)
        fenetre.grid_columnconfigure(1, weight=1)

        # Recherche (filtre les messages du jour affiché).
        self._champ_recherche = ctk.CTkEntry(
            fenetre, placeholder_text="Rechercher dans la conversation…",
            font=ctk.CTkFont(family="Segoe UI", size=13), height=36)
        self._champ_recherche.grid(row=0, column=0, columnspan=2,
                                   sticky="ew", padx=10, pady=10)
        self._champ_recherche.bind(
            "<KeyRelease>", lambda _e: self._afficher_jour_historique())

        # Liste des jours (à gauche).
        self._liste_jours = ctk.CTkScrollableFrame(
            fenetre, fg_color=COULEUR_PANNEAU, corner_radius=12,
            scrollbar_button_color=COULEUR_BARRE_DEFILEMENT, width=200)
        self._liste_jours.grid(row=1, column=0, sticky="nsew",
                               padx=(10, 4), pady=(0, 10))
        for jour in self._historique["jours"]:
            libelle = formater_jour(jour["date"])
            if jour["date"] != "Ancien journal":
                libelle = (f"{libelle}\n{jour['messages']} message"
                           + ("s" if jour["messages"] > 1 else ""))
            else:
                libelle = (f"Ancien journal\n{jour['messages']} message"
                           + ("s" if jour["messages"] > 1 else ""))
            ctk.CTkButton(
                self._liste_jours, text=libelle,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                fg_color="transparent", hover_color="#23232f",
                text_color=COULEUR_TEXTE, anchor="w",
                command=lambda j=jour: self._choisir_jour_historique(j)
            ).pack(fill="x", padx=6, pady=3)
        if not self._historique["jours"]:
            ctk.CTkLabel(
                self._liste_jours, text="Aucun historique pour l'instant.",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=COULEUR_TEXTE_FAIBLE, wraplength=180,
                justify="left").pack(padx=8, pady=10)

        # Conversation du jour (à droite, lecture seule).
        self._zone_historique = ctk.CTkScrollableFrame(
            fenetre, fg_color=COULEUR_FOND, corner_radius=0,
            scrollbar_button_color=COULEUR_BARRE_DEFILEMENT)
        self._zone_historique.grid(row=1, column=1, sticky="nsew",
                                   padx=(4, 10), pady=(0, 10))

        bouton_fermer = ctk.CTkButton(
            fenetre, text="Fermer",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=COULEUR_ACCENT, hover_color=COULEUR_ACCENT_SURVOL,
            text_color="#ffffff", corner_radius=20, height=36,
            command=fenetre.destroy)
        bouton_fermer.grid(row=2, column=0, columnspan=2, pady=(0, 10))

        fenetre.protocol(
            "WM_DELETE_WINDOW",
            lambda: (setattr(self, "_fenetre_historique", None),
                     fenetre.destroy()))
        if self._historique["jours"]:
            self._choisir_jour_historique(self._historique["jours"][0])

    def _choisir_jour_historique(self, jour: dict) -> None:
        """Charge un jour dans la fenêtre Historique."""
        self._historique["courant"] = jour
        self._historique["entrees"] = lire_conversation(jour["chemin"])
        self._afficher_jour_historique()

    def _afficher_jour_historique(self) -> None:
        """Affiche le jour courant (filtré par la recherche, le cas échéant)."""
        zone = getattr(self, "_zone_historique", None)
        if zone is None:
            return
        for enfant in zone.winfo_children():
            enfant.destroy()
        requete = ""
        try:
            requete = self._champ_recherche.get()
        except Exception:
            pass
        entrees = filtrer_entrees(self._historique["entrees"], requete)
        if not entrees:
            texte = ("Aucun message ce jour-là."
                     if not requete
                     else "Aucun message ne contient cette recherche.")
            ctk.CTkLabel(
                zone, text=texte,
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=COULEUR_TEXTE_FAIBLE,
                justify="center").pack(pady=40)
            return
        precedent = None
        for entree in entrees:
            ajouter_bulle(zone, entree, 520, precedent)
            precedent = entree["role"]
        try:
            zone._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    # -- Menu ----------------------------------------------------------

    def ouvrir_guide(self) -> None:
        """Ouvre le guide de l'étape 7 (Windows : application associée)."""
        try:
            os.startfile(str(GUIDE))  # type: ignore[attr-defined]
        except (OSError, AttributeError):
            print(f"Guide : {GUIDE}")

    def quitter(self) -> None:
        if self._micro_enfonce:
            ecrire_ptt(FICHIER_PTT, False)
        try:
            sauvegarder_geometrie(
                self.racine, self.fenetre.geometry())
        except Exception:
            pass
        self.fenetre.destroy()

    # -- Redimensionnement (géométrie + retour à la ligne) -------------

    def _reprogrammer(self, attribut: str, delai_ms: int, fonction) -> None:
        """Anti-rebond : annule l'appel en attente (s'il y en a un) et en
        programme un nouveau dans `delai_ms`."""
        en_attente = getattr(self, attribut)
        if en_attente is not None:
            try:
                self.fenetre.after_cancel(en_attente)
            except Exception:
                pass
        setattr(self, attribut, self.fenetre.after(delai_ms, fonction))

    def _sur_redimensionnement(self, _evenement=None) -> None:
        """Ajuste le retour à la ligne des bulles (120 ms après le dernier
        événement) et mémorise la géométrie (800 ms après : pas d'écriture
        de fichier pendant qu'on tire sur le bord de la fenêtre)."""
        self._reprogrammer("_apres_redimensionnement", DELAI_REFLUX_MS,
                           self._apres_redimensionnement_fait)
        self._reprogrammer("_apres_geometrie", DELAI_GEOMETRIE_MS,
                           self._sauver_geometrie_differee)

    def _sauver_geometrie_differee(self) -> None:
        self._apres_geometrie = None
        try:
            if self.fenetre.state() == "normal":
                sauvegarder_geometrie(
                    self.racine, self.fenetre.geometry())
        except Exception:
            pass

    def _apres_redimensionnement_fait(self) -> None:
        self._apres_redimensionnement = None
        try:
            largeur = self._largeur_bulle()  # d'après winfo_width()
            if largeur != self._derniere_largeur:
                self._derniere_largeur = largeur
                for etiquette in self._etiquettes_bulles:
                    etiquette.configure(wraplength=largeur)
            # Le détail d'état passe à la ligne avant l'horloge.
            self.texte_detail.configure(wraplength=max(
                220, self.fenetre.winfo_width() - 340))
        except Exception:
            pass

    # -- Rafraîchissement ----------------------------------------------

    def rafraichir(self) -> None:
        """Relit l'état, la conversation et les minuteurs ; ne redessine
        que ce qui a changé. L'application ne plante jamais sur une
        lecture illisible : elle affiche l'état par défaut."""
        try:
            maintenant = datetime.now(FUSEAU)
            etat = lire_etat()
            # Langue parlée du moment (champ optionnel écrit par la boucle).
            if etat["langue"] and etat["langue"] != self.langue:
                self.langue = etat["langue"]
                self._appliquer_langue()
            minuteurs = charger_minuteurs()
            entrees = lire_conversation()

            # État + détail.
            etat_affiche = etat["etat"]
            texte_etat = self.t(f"etat_{etat_affiche}")
            if etat_affiche == "arrete":
                detail = self.t("detail_arrete")
            elif etat_affiche == "erreur" and etat["erreur"]:
                detail = (self.t("detail_erreur_prefixe")
                          + etat["erreur"][:110]
                          + ("…" if len(etat["erreur"]) > 110 else ""))
            elif etat["transcription"]:
                detail = (etat["transcription"][:90]
                          + ("…" if len(etat["transcription"]) > 90 else ""))
            else:
                detail = self.t(f"detail_{etat_affiche}")
            if (etat_affiche != self.etat_affiche
                    or self.texte_etat.cget("text") != texte_etat
                    or self.texte_detail.cget("text") != detail):
                self.etat_affiche = etat_affiche
                self.texte_etat.configure(text=texte_etat)
                self.texte_detail.configure(text=detail)
                self._dessiner_orbe(1.0)

            # Horloge (redessinée seulement quand la seconde change).
            horloge = maintenant.strftime("%H:%M:%S")
            if horloge != self._horloge_affichee:
                self._horloge_affichee = horloge
                self.texte_horloge.configure(text=horloge)

            # Minuteurs.
            self._rafraichir_minuteurs(minuteurs, maintenant)

            # Conversation : ajouts, ou reconstruction si le journal a
            # raccourci (changement de jour : nouveau fichier).
            affichees = self._entrees_affichees
            if (len(entrees) < len(affichees)
                    or entrees[:len(affichees)] != affichees):
                self._reconstruire_conversation(entrees)
            elif len(entrees) > len(affichees):
                for entree in entrees[len(affichees):]:
                    self._ajouter_message(entree)
                self._defiler_bas()
            elif not entrees and self._message_vide is None:
                self._afficher_message_vide()

            # Micro maintenu : rafraîchir le fichier PTT pour que la
            # boucle ne le considère pas comme périmé.
            if self._micro_enfonce:
                ecrire_ptt(FICHIER_PTT, True)
        except Exception as erreur:  # L'application ne doit jamais planter.
            print(f"Avertissement application : {erreur}", file=sys.stderr)
        finally:
            self.fenetre.after(
                int(self.config.get("intervalle_ms", 500)),
                self.rafraichir)

    def demarrer(self) -> None:
        self.fenetre.mainloop()


# ---------------------------------------------------------------------------
# Vérification et point d'entrée
# ---------------------------------------------------------------------------

def verifier(config: dict) -> int:
    """Vérifie l'installation et la configuration, puis affiche un bilan."""
    print("Vérification de l'application Jarvis (étape 7) :")
    problemes = []

    def ligne(ok: bool, nom: str, detail: str = ""):
        marque = "OK     " if ok else "MANQUANT"
        print(f"  [{marque}] {nom}" + (f" — {detail}" if detail else ""))
        if not ok:
            problemes.append(nom)

    version = sys.version_info
    ligne(version >= (3, 10), "Python 3.10+",
          f"{version.major}.{version.minor}.{version.micro}")
    ligne(TKINTER_DISPONIBLE, "Tkinter (bibliothèque standard)",
          "réinstaller Python avec tcl/tk si absent" if not
          TKINTER_DISPONIBLE else "")
    if CTK_DISPONIBLE:
        try:
            import importlib.metadata

            version_ctk = importlib.metadata.version("customtkinter")
        except Exception:
            version_ctk = "installé (version inconnue)"
        ligne(True, "CustomTkinter", version_ctk)
    else:
        ligne(False, "CustomTkinter",
              "pip install -r scripts/requirements-etape7.txt")
    ligne(SCRIPT_BOUCLE.exists(),
          "scripts/boucle_voix.py (écrit le journal de conversation)")
    ligne(GUIDE.exists(), "docs/etape-7-application.md")
    try:
        (RACINE / "data").mkdir(parents=True, exist_ok=True)
        ligne(os.access(RACINE / "data", os.W_OK), "dossier data/ en écriture")
    except OSError as erreur:
        ligne(False, "dossier data/ en écriture", str(erreur))
    ligne(bool(config.get("active", True)), "Application activée ([app] active)",
          "mettre active = true dans config.toml" if not config.get(
              "active", True) else "")
    print(f"  [INFO]   langue de l'interface : {config.get('langue', 'en')} "
          "([boucle] langue de config.toml)")
    if not (DOSSIER_CONVERSATIONS.exists()
            or FICHIER_CONVERSATION.exists()):
        print("  [INFO]   aucun journal de conversation — il sera créé "
              "par la boucle vocale au premier tour "
              "(data/conversations/AAAA-MM-JJ.jsonl).")
    print()
    if problemes:
        print(f"{len(problemes)} élément(s) à régler : "
              + ", ".join(problemes) + ".")
        print("Voir docs/etape-7-application.md pour les détails.")
        return 1
    print("Tout est en place. Lancez l'application avec :")
    print("  python scripts\\app.py")
    print("Pensez à lancer aussi la boucle vocale (dans une autre fenêtre) :")
    print("  python scripts\\boucle_voix.py")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Application Jarvis : fenêtre desktop moderne — orbe "
                    "d'état, conversation, minuteurs, micro (CustomTkinter).")
    parser.add_argument(
        "--verifier", action="store_true",
        help="Vérifier l'installation et la configuration, puis quitter.")
    args = parser.parse_args()

    config = charger_config_app(RACINE)

    if args.verifier:
        return verifier(config)
    if not config.get("active", True):
        print("Application désactivée dans config.toml ([app] active = false).")
        return 0
    if not TKINTER_DISPONIBLE:
        print("Erreur : Tkinter est indisponible.", file=sys.stderr)
        print("Réinstallez Python avec l'option « tcl/tk and IDLE ».",
              file=sys.stderr)
        return 3
    if not CTK_DISPONIBLE:
        print("Erreur : CustomTkinter n'est pas installé.", file=sys.stderr)
        print("Installez-le avec :", file=sys.stderr)
        print("  pip install -r scripts/requirements-etape7.txt",
              file=sys.stderr)
        return 3
    try:
        app = Application(RACINE, config)
    except Exception as erreur:
        print(f"Erreur : impossible d'ouvrir une fenêtre ({erreur}).",
              file=sys.stderr)
        print("Sur une machine sans écran, l'application ne peut pas "
              "s'afficher.", file=sys.stderr)
        return 3
    app.demarrer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
