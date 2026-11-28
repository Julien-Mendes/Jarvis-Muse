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
  - Panneau recherches (lot R1) : recherches différées lues dans
    data/recherches.json (lecture seule) avec leur statut ; un clic sur
    une recherche ouvre sa réponse et ses sources (titres + URL).
  - Panneau Tâches longues (lot LT), sous les recherches : tâches lues
    dans data/taches_longues.json (lecture seule) avec leur état et leur
    progression (étapes faites / étapes du plan) ; un clic ouvre le détail
    (objectif, plan coché, résultat ou ce qui a arrêté la tâche).
  - Panneau Connaissances (lot KB) : notes personnelles lues dans
    data/connaissances.json (texte + date), la plus récente d'abord ; la
    croix d'une note la supprime après une seconde confirmation (« Supprimer ? »
    pendant 4 s). Cette suppression et les actions des tuiles de minuteur
    (lot U3 : pause, reprise, annulation, via minuteur.py) sont les seules
    écritures de l'application dans data/ (hors PTT, demande texte et
    géométrie), toutes sous verrou.
  - Tableau de bord (lots DB, U5) : moniteur système (CPU, RAM, disque,
    psutil, toutes les 5 s) dans l'en-tête ; colonne Agents + Conversations
    quand la fenêtre est large ; animations courtes (aucune au repos,
    [app] animations = false pour les couper).
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

Thèmes (U2) : quatre palettes — or_et_nuit (défaut), jarvis_bleu (repli),
clair_studio et centre_de_commande (lot esthétique : bleu nuit / cyan façon
« Command Center », orbe en globe filaire, panneaux bordés à titres en
capitales, statuts colorés, jauges des minuteurs, pastille d'état) —
choisies par [app] theme de la configuration. Un thème inconnu ou une
configuration illisible donne jarvis_bleu. Le changement se fait par la
configuration (pas encore de panneau Réglages). Seul centre_de_commande a un
« style » ; les trois autres gardent exactement la présentation U1/U2.

Langue : les textes de la fenêtre principale suivent la langue de la
boucle vocale — [general] langue de config.toml au démarrage, puis la
langue de chaque tour (lot L1 : champ « langue » de data/hud-state.json,
écrit par la boucle dès que la langue du tour est détectée) — en français
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
l'état, l'heure, les minuteurs, les synthèses de recherche (rédigées par
Jarvis, jamais le texte brut des pages) et la conversation avec Jarvis
lui-même sont montrés. Le journal de conversation est local uniquement (data/,
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
import recherche as recherche_mod  # noqa: E402 — lot R1 (lecture seule).
import connaissances as connaissances_mod  # noqa: E402 — lot KB.
import taches_longues as taches_mod  # noqa: E402 — lot LT (lecture seule).

# Fuseau horaire : [general] fuseau_horaire de la configuration (K1).
FUSEAU = config_jarvis.fuseau()

RACINE = Path(__file__).resolve().parent.parent
FICHIER_ETAT = RACINE / "data" / "hud-state.json"
FICHIER_PTT = RACINE / "data" / "hud-ptt.json"
FICHIER_MINUTEURS = RACINE / "data" / "timers.json"
FICHIER_RECHERCHES = RACINE / "data" / "recherches.json"
FICHIER_CONNAISSANCES = RACINE / "data" / "connaissances.json"
FICHIER_TACHES = RACINE / "data" / "taches_longues.json"
DOSSIER_CONVERSATIONS = RACINE / "data" / "conversations"
# Ancien journal unique (étape 7) : plus écrit par la boucle, lu en repli
# si le journal du jour n'existe pas encore.
FICHIER_CONVERSATION = RACINE / "data" / "conversation.jsonl"
FICHIER_DEMANDE_TEXTE = RACINE / "data" / "texte-demande.json"
# Lot PR : interrupteur « Mode privé » ({"actif", "langue", "horodatage"},
# jamais de contenu), consommé par la boucle vocale.
FICHIER_DEMANDE_PRIVE = RACINE / "data" / "prive-demande.json"
# Pastille « Privé » : violet, distinct de toutes les couleurs d'état.
COULEUR_PRIVE = "#B57BFF"
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
    # Thème des couleurs : « or_et_nuit » (défaut, choix de Julien),
    # « jarvis_bleu » (couleurs d'origine, thème de repli) ou
    # « clair_studio ». Lu avec config_jarvis (config.toml, config.local.toml).
    "theme": "or_et_nuit",
    # Lot U5 : animations de l'orbe et des panneaux (false = tout immobile,
    # l'orbe ne pulse plus non plus).
    "animations": True,
    # Lot DB : colonne Agents + Conversations, affichée quand la fenêtre est
    # assez large (LARGEUR_TABLEAU_BORD) ; false = jamais.
    "tableau_de_bord": True,
}

# ---------------------------------------------------------------------------
# Thèmes (U2) — trois palettes, choisies par [app] theme de la configuration.
# ---------------------------------------------------------------------------
#
# jarvis_bleu : ambiance du Jarvis de référence (Julian-Ivanov) : fond très
#   sombre, accent bleu, orbe qui pulse. C'est le thème de REPLI : celui qu'on
#   obtient si le thème demandé est inconnu ou illisible.
# or_et_nuit  : noir et or (thème par défaut, choix de Julien).
# clair_studio: fond clair, panneaux blancs, accent bleu.
#
# Chaque palette définit les mêmes clés (test de contrat). Une valeur None
# pour une option facultative = ne rien envoyer à CustomTkinter (couleur
# d'origine de la bibliothèque), ce qui garde jarvis_bleu identique à avant.
THEME_REPLI = "jarvis_bleu"
THEME_DEFAUT = "or_et_nuit"

THEMES = {
    "jarvis_bleu": {
        "mode": "dark",
        "fond": "#0a0a0f", "panneau": "#14141d",
        "bulle_jarvis": "#1a1a26", "bulle_utilisateur": "#1a3a5c",
        "texte": "#e0e0e0", "texte_faible": "#888888",
        "accent": "#4a9eff", "accent_survol": "#3a7bd5",
        "texte_sur_accent": "#ffffff",
        "barre_defilement": "#62627c", "barre_defilement_survol": "#8a8aa6",
        "interrompre_texte": "#e07878", "interrompre_bordure": "#7a3a3a",
        "interrompre_survol": "#2a1a1a",
        "survol_liste": "#23232f",
        "orbe_fondu": "#000000",
        "orbe": {"repos": "#5b7a99", "ecoute": "#2a6cb8",
                 "reflexion": "#c9a227", "reponse": "#27c96a",
                 "erreur": "#c0392b", "arrete": "#666666"},
        "fond_fenetre": None,
        "champ_fond": None, "champ_bordure": None, "champ_texte": None,
        "champ_texte_indice": None,
        "style": None,
    },
    "or_et_nuit": {
        "mode": "dark",
        "fond": "#09090b", "panneau": "#121216",
        "bulle_jarvis": "#18181e", "bulle_utilisateur": "#2c2412",
        "texte": "#f2efe6", "texte_faible": "#9a9484",
        "accent": "#e0a82e", "accent_survol": "#c4912a",
        "texte_sur_accent": "#09090b",
        "barre_defilement": "#7a6025", "barre_defilement_survol": "#e0a82e",
        "interrompre_texte": "#e88a8a", "interrompre_bordure": "#7a3a3a",
        "interrompre_survol": "#241414",
        "survol_liste": "#1f1f26",
        "orbe_fondu": "#000000",
        "orbe": {"repos": "#8c7a4b", "ecoute": "#ffcf5c",
                 "reflexion": "#f2e6c0", "reponse": "#45c08a",
                 "erreur": "#d9534f", "arrete": "#5c5a52"},
        "fond_fenetre": "#09090b",
        "champ_fond": "#18181e", "champ_bordure": "#4a3d1c",
        "champ_texte": "#f2efe6", "champ_texte_indice": "#9a9484",
        "style": None,
    },
    "clair_studio": {
        "mode": "light",
        "fond": "#f4f6f9", "panneau": "#ffffff",
        "bulle_jarvis": "#e6ebf2", "bulle_utilisateur": "#d4e4fb",
        "texte": "#1b2330", "texte_faible": "#53617a",
        "accent": "#1d6fd6", "accent_survol": "#1658ab",
        "texte_sur_accent": "#ffffff",
        "barre_defilement": "#7f8da3", "barre_defilement_survol": "#1d6fd6",
        "interrompre_texte": "#b3261e", "interrompre_bordure": "#e0a8a4",
        "interrompre_survol": "#fbe9e8",
        "survol_liste": "#e3e9f1",
        "orbe_fondu": "#ffffff",
        "orbe": {"repos": "#7b8da6", "ecoute": "#0f5bb5",
                 "reflexion": "#b87800", "reponse": "#1a8a4e",
                 "erreur": "#c0392b", "arrete": "#9aa5b4"},
        "fond_fenetre": "#f4f6f9",
        "champ_fond": "#ffffff", "champ_bordure": "#c3ccd9",
        "champ_texte": "#1b2330", "champ_texte_indice": "#53617a",
        "style": None,
    },
    # Lot esthétique (suite de U2) : « Command Center » bleu nuit / cyan,
    # d'après ref-visuel/jarvis-exemple.png. Seul thème avec un « style » :
    # orbe en globe filaire, panneaux bordés de cyan à titres en capitales,
    # statuts colorés, jauges circulaires des minuteurs, pastille d'état,
    # bouton micro en pilule lumineuse. Les tailles du lot U1 ne changent pas.
    "centre_de_commande": {
        "mode": "dark",
        "fond": "#050b16", "panneau": "#0a1628",
        "bulle_jarvis": "#0d1f36", "bulle_utilisateur": "#0b3350",
        "texte": "#e3f4ff", "texte_faible": "#8fb0cc",
        "accent": "#22d3ee", "accent_survol": "#06b6d4",
        "texte_sur_accent": "#03121f",
        "barre_defilement": "#1f7096", "barre_defilement_survol": "#22d3ee",
        "interrompre_texte": "#f87171", "interrompre_bordure": "#7f2d3a",
        "interrompre_survol": "#2a0f16",
        "survol_liste": "#10263f",
        "orbe_fondu": "#0a1628",
        "orbe": {"repos": "#38bdf8", "ecoute": "#22d3ee",
                 "reflexion": "#a78bfa", "reponse": "#34d399",
                 "erreur": "#f87171", "arrete": "#5b6b80"},
        "fond_fenetre": "#050b16",
        "champ_fond": "#081627", "champ_bordure": "#1c4f73",
        "champ_texte": "#e3f4ff", "champ_texte_indice": "#6f8fae",
        "style": {
            "orbe": "globe",                 # « disque » : les 3 disques U1
            "bordure_panneau": "#1c4f73",    # liseré cyan des panneaux
            "titre_panneau": "#67e8f9",      # titres en capitales, cyan
            "titres_majuscules": True,
            # Bahnschrift (DIN, fournie avec Windows 10+) pour les titres,
            # l'état et l'horloge ; Tk se rabat sur la police par défaut si
            # elle manque. Le corps reste en Segoe UI.
            "police_titre": "Bahnschrift",
            "bordure_bulle_jarvis": "#16486a",
            "bordure_bulle_utilisateur": "#1f7096",
            "micro_fond": "#082a45",         # pilule sombre, contour cyan
            "jauge_fond": "#12304a",         # piste des jauges circulaires
            "statut": {"ok": "#34d399", "actif": "#22d3ee",
                       "attente": "#fbbf24", "erreur": "#f87171",
                       "inactif": "#5b6b80"},
        },
    },
}

# Couleur de statut par état de la boucle (pastille d'état du thème stylé).
STATUT_DES_ETATS = {"repos": "ok", "ecoute": "actif", "reflexion": "attente",
                    "reponse": "actif", "erreur": "erreur",
                    "arrete": "inactif"}

# Couleurs actives : réglées par appliquer_theme() avant la création des
# widgets (Application.__init__). Au simple import, ce sont celles du thème de
# repli (jarvis_bleu), donc rien ne change pour qui n'ouvre pas la fenêtre.
COULEUR_FOND = THEMES[THEME_REPLI]["fond"]
COULEUR_PANNEAU = THEMES[THEME_REPLI]["panneau"]
COULEUR_BULLE_JARVIS = THEMES[THEME_REPLI]["bulle_jarvis"]
COULEUR_BULLE_UTILISATEUR = THEMES[THEME_REPLI]["bulle_utilisateur"]
COULEUR_TEXTE = THEMES[THEME_REPLI]["texte"]
COULEUR_TEXTE_FAIBLE = THEMES[THEME_REPLI]["texte_faible"]
COULEUR_ACCENT = THEMES[THEME_REPLI]["accent"]
COULEUR_ACCENT_SURVOL = THEMES[THEME_REPLI]["accent_survol"]
COULEUR_TEXTE_SUR_ACCENT = THEMES[THEME_REPLI]["texte_sur_accent"]
COULEUR_BARRE_DEFILEMENT = THEMES[THEME_REPLI]["barre_defilement"]
COULEUR_BARRE_DEFILEMENT_SURVOL = THEMES[THEME_REPLI]["barre_defilement_survol"]
COULEUR_INTERROMPRE_TEXTE = THEMES[THEME_REPLI]["interrompre_texte"]
COULEUR_INTERROMPRE_BORDURE = THEMES[THEME_REPLI]["interrompre_bordure"]
COULEUR_INTERROMPRE_SURVOL = THEMES[THEME_REPLI]["interrompre_survol"]
COULEUR_SURVOL_LISTE = THEMES[THEME_REPLI]["survol_liste"]
COULEUR_ORBE_FONDU = THEMES[THEME_REPLI]["orbe_fondu"]
COULEUR_FOND_FENETRE = THEMES[THEME_REPLI]["fond_fenetre"]
MODE_APPARENCE = THEMES[THEME_REPLI]["mode"]
OPTIONS_CHAMP: dict = {}
THEME_ACTIF = THEME_REPLI
# Style du thème (vide = présentation classique U1/U2, inchangée).
STYLE: dict = {}

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


def nom_theme(valeur) -> str:
    """Nom de thème valide : celui demandé s'il existe, sinon le repli
    (jarvis_bleu) — valeur inconnue, vide ou d'un autre type."""
    if isinstance(valeur, str) and valeur.strip().lower() in THEMES:
        return valeur.strip().lower()
    return THEME_REPLI


def appliquer_theme(nom) -> str:
    """Active un thème : règle les couleurs (COULEUR_*), celles de l'orbe
    (ETATS) et le mode d'apparence. Retourne le nom du thème réellement
    appliqué (jarvis_bleu si `nom` est inconnu). À appeler AVANT de créer
    les widgets : les couleurs sont lues à la création."""
    global COULEUR_FOND, COULEUR_PANNEAU, COULEUR_BULLE_JARVIS
    global COULEUR_BULLE_UTILISATEUR, COULEUR_TEXTE, COULEUR_TEXTE_FAIBLE
    global COULEUR_ACCENT, COULEUR_ACCENT_SURVOL, COULEUR_TEXTE_SUR_ACCENT
    global COULEUR_BARRE_DEFILEMENT, COULEUR_BARRE_DEFILEMENT_SURVOL
    global COULEUR_INTERROMPRE_TEXTE, COULEUR_INTERROMPRE_BORDURE
    global COULEUR_INTERROMPRE_SURVOL, COULEUR_SURVOL_LISTE
    global COULEUR_ORBE_FONDU, COULEUR_FOND_FENETRE, MODE_APPARENCE
    global OPTIONS_CHAMP, THEME_ACTIF, STYLE
    effectif = nom_theme(nom)
    if isinstance(nom, str) and nom.strip().lower() != effectif:
        print(f"Avertissement application : thème « {nom} » inconnu ; "
              f"{THEME_REPLI} utilisé.", file=sys.stderr)
    palette = THEMES[effectif]
    COULEUR_FOND = palette["fond"]
    COULEUR_PANNEAU = palette["panneau"]
    COULEUR_BULLE_JARVIS = palette["bulle_jarvis"]
    COULEUR_BULLE_UTILISATEUR = palette["bulle_utilisateur"]
    COULEUR_TEXTE = palette["texte"]
    COULEUR_TEXTE_FAIBLE = palette["texte_faible"]
    COULEUR_ACCENT = palette["accent"]
    COULEUR_ACCENT_SURVOL = palette["accent_survol"]
    COULEUR_TEXTE_SUR_ACCENT = palette["texte_sur_accent"]
    COULEUR_BARRE_DEFILEMENT = palette["barre_defilement"]
    COULEUR_BARRE_DEFILEMENT_SURVOL = palette["barre_defilement_survol"]
    COULEUR_INTERROMPRE_TEXTE = palette["interrompre_texte"]
    COULEUR_INTERROMPRE_BORDURE = palette["interrompre_bordure"]
    COULEUR_INTERROMPRE_SURVOL = palette["interrompre_survol"]
    COULEUR_SURVOL_LISTE = palette["survol_liste"]
    COULEUR_ORBE_FONDU = palette["orbe_fondu"]
    COULEUR_FOND_FENETRE = palette["fond_fenetre"]
    MODE_APPARENCE = palette["mode"]
    OPTIONS_CHAMP = {
        cle_ctk: palette[cle]
        for cle_ctk, cle in (("fg_color", "champ_fond"),
                             ("border_color", "champ_bordure"),
                             ("text_color", "champ_texte"),
                             ("placeholder_text_color", "champ_texte_indice"))
        if palette[cle] is not None}
    for etat, couleur in palette["orbe"].items():
        texte, _ancienne, periode = ETATS[etat]
        ETATS[etat] = (texte, couleur, periode)
    STYLE = dict(palette.get("style") or {})
    THEME_ACTIF = effectif
    return effectif


def options_tuile() -> dict:
    """Ligne d'une liste (minuteur, recherche, note) : tuile sombre bordée
    dans le thème stylé, comme les éléments de la référence ; transparente
    sinon."""
    if STYLE.get("bordure_panneau"):
        return {"fg_color": COULEUR_FOND, "corner_radius": 8,
                "border_width": 1, "border_color": STYLE["bordure_panneau"]}
    return {"fg_color": "transparent"}


def couleur_statut(cle: str, repli: str) -> str:
    """Couleur de statut du thème stylé (« ok », « actif », « attente »,
    « erreur », « inactif ») ; `repli` pour les thèmes classiques."""
    return (STYLE.get("statut") or {}).get(cle, repli)


def couleur_etat(cle: str) -> str:
    """Couleur d'un statut (« ok », « actif », « attente », « erreur »,
    « inactif ») : celle du thème stylé, sinon prise dans la palette
    classique (orbe, accent, texte faible) — même sens dans tous les thèmes."""
    repli = {"ok": ETATS["reponse"][1], "actif": COULEUR_ACCENT,
             "attente": ETATS["reflexion"][1], "erreur": ETATS["erreur"][1],
             "inactif": COULEUR_TEXTE_FAIBLE}.get(cle, COULEUR_TEXTE_FAIBLE)
    return couleur_statut(cle, repli)


STATUT_DES_AGENTS = {"actif": "actif", "veille": "inactif", "erreur": "erreur"}


def titre_affiche(texte: str) -> str:
    """Titre de panneau : en capitales dans le thème stylé."""
    return texte.upper() if STYLE.get("titres_majuscules") else texte


def options_panneau() -> dict:
    """Options d'un panneau : liseré cyan dans le thème stylé, aucune option
    en plus sinon (panneaux U2 identiques)."""
    if STYLE.get("bordure_panneau"):
        return {"border_width": 1, "border_color": STYLE["bordure_panneau"]}
    return {}
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
DELAI_VERIF_DEFILEMENT_MS = 100   # second contrôle du bas après la mise en page
TOLERANCE_BAS = 0.002             # « en bas » : fin de la vue >= 1 - tolérance
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
        "recherches": "Recherches",
        "aucune_recherche": "Aucune recherche.",
        "recherche_fenetre": "Recherche — Jarvis",
        "recherche_sources": "Sources",
        "recherche_attente": "Pas encore de réponse : la recherche est {statut}.",
        "taches": "Tâches longues",
        "aucune_tache": "Aucune tâche longue.",
        "tache_fenetre": "Tâche longue — Jarvis",
        "tache_objectif": "Objectif",
        "tache_plan": "Plan",
        "tache_resultat": "Résultat",
        "tache_arret": "Arrêtée : {raison}.",
        "tache_attente": "Pas encore de résultat : la tâche avance ({progression}).",
        "tache_budget": "Temps : {duree} sur {budget}",
        "pastille_repos": "● EN LIGNE",
        "pastille_ecoute": "● ÉCOUTE",
        "pastille_reflexion": "● ANALYSE",
        "pastille_reponse": "● RÉPONSE",
        "pastille_erreur": "● ERREUR",
        "pastille_arrete": "● HORS LIGNE",
        "connaissances": "Connaissances",
        "aucune_note": "Aucune note.\nDites « note que… » pour en ajouter une.",
        "supprimer_note": "Supprimer cette note",
        "confirmer_suppression": "Supprimer ?",
        "notes_en_plus": "… et {n} de plus (python scripts\\connaissances.py lister)",
        "fermer": "Fermer",
        "echue": "échue",
        "menu_fichier": "Fichier",
        "menu_historique": "Historique…",
        "menu_guide": "Ouvrir le guide",
        "menu_quitter": "Quitter",
        "vide": ("Aucune conversation pour l'instant.\n"
                 "Maintenez F9 (ou le bouton micro) pour parler à Jarvis,\n"
                 "ou écrivez votre message ci-dessous."),
        # Lot DB / U3 / U5
        "minuteur_pause": "• {quoi} : en pause ({duree})",
        "systeme_cpu": "CPU",
        "systeme_ram": "RAM",
        "systeme_disque": "Disque",
        "systeme_indispo": "—",
        "agents": "Agents",
        "agent_cerveau": "Cerveau",
        "agent_voix": "Voix",
        "agent_navigateur": "Navigateur",
        "agent_minuteurs": "Minuteurs",
        "agent_recherches": "Recherches",
        "agent_taches": "Tâches",
        "agent_notes": "Notes",
        "statut_actif": "actif",
        "statut_veille": "en veille",
        "statut_erreur": "erreur",
        "conversations": "Conversations",
        "aucune_conversation": "Aucune conversation enregistrée.",
        "jour_messages": "{n} message(s)",
        "ancien_journal": "Ancien journal",
        "minuteur_fenetre": "Minuteur — Jarvis",
        "minuteur_pause_btn": "Pause",
        "minuteur_reprendre": "Reprendre",
        "minuteur_annuler": "Annuler",
        "minuteur_confirmer": "Confirmer ?",
        "minuteur_introuvable": "Ce minuteur n'existe plus.",
        "note_fenetre": "Note — Jarvis",
        "menu_affichage": "Affichage",
        "menu_tableau": "Tableau de bord (afficher / masquer)",
        "menu_prive_activer": "Mode privé : activer",
        "menu_prive_quitter": "Mode privé : quitter",
        "pastille_prive": "● PRIVÉ",
        "detail_prive": ("Mode privé : rien n'est gardé, la conversation "
                         "n'est ni écrite ni affichée."),
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
        "recherches": "Research",
        "aucune_recherche": "No research yet.",
        "recherche_fenetre": "Research — Jarvis",
        "recherche_sources": "Sources",
        "recherche_attente": "No answer yet: the research is {statut}.",
        "taches": "Long tasks",
        "aucune_tache": "No long tasks.",
        "tache_fenetre": "Long task — Jarvis",
        "tache_objectif": "Goal",
        "tache_plan": "Plan",
        "tache_resultat": "Result",
        "tache_arret": "Stopped: {raison}.",
        "tache_attente": "No result yet: the task is moving along ({progression}).",
        "tache_budget": "Time: {duree} out of {budget}",
        "pastille_repos": "● ONLINE",
        "pastille_ecoute": "● LISTENING",
        "pastille_reflexion": "● THINKING",
        "pastille_reponse": "● ANSWERING",
        "pastille_erreur": "● ERROR",
        "pastille_arrete": "● OFFLINE",
        "connaissances": "Knowledge",
        "aucune_note": "No notes.\nSay “note that…” to add one.",
        "supprimer_note": "Delete this note",
        "confirmer_suppression": "Delete?",
        "notes_en_plus": "… and {n} more (python scripts\\connaissances.py lister)",
        "fermer": "Close",
        "echue": "expired",
        "menu_fichier": "File",
        "menu_historique": "History…",
        "menu_guide": "Open the guide",
        "menu_quitter": "Quit",
        "vide": ("No conversation yet.\n"
                 "Hold F9 (or the mic button) to talk to Jarvis,\n"
                 "or type your message below."),
        "minuteur_pause": "• {quoi}: paused ({duree})",
        "systeme_cpu": "CPU",
        "systeme_ram": "RAM",
        "systeme_disque": "Disk",
        "systeme_indispo": "—",
        "agents": "Agents",
        "agent_cerveau": "Brain",
        "agent_voix": "Voice",
        "agent_navigateur": "Browser",
        "agent_minuteurs": "Timers",
        "agent_recherches": "Research",
        "agent_taches": "Tasks",
        "agent_notes": "Notes",
        "statut_actif": "active",
        "statut_veille": "idle",
        "statut_erreur": "error",
        "conversations": "Conversations",
        "aucune_conversation": "No saved conversation.",
        "jour_messages": "{n} message(s)",
        "ancien_journal": "Old log",
        "minuteur_fenetre": "Timer — Jarvis",
        "minuteur_pause_btn": "Pause",
        "minuteur_reprendre": "Resume",
        "minuteur_annuler": "Cancel",
        "minuteur_confirmer": "Confirm?",
        "minuteur_introuvable": "This timer no longer exists.",
        "note_fenetre": "Note — Jarvis",
        "menu_affichage": "View",
        "menu_tableau": "Dashboard (show / hide)",
        "menu_prive_activer": "Private mode: turn on",
        "menu_prive_quitter": "Private mode: turn off",
        "pastille_prive": "● PRIVATE",
        "detail_prive": ("Private mode: nothing is kept; the conversation "
                         "is neither written nor shown."),
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

def valeur_booleenne(valeur, defaut: bool) -> bool:
    """true/false de la configuration (booléen TOML, ou texte « oui » /
    « non » / « true » / « false ») ; `defaut` si illisible."""
    if isinstance(valeur, bool):
        return valeur
    texte = str(valeur).strip().lower()
    if texte in ("true", "oui", "yes", "1", "on", "vrai"):
        return True
    if texte in ("false", "non", "no", "0", "off", "faux"):
        return False
    return defaut


def charger_config_app(racine: Path) -> dict:
    """Lit [app] avec config_jarvis (config.example.toml < config.toml <
    config.local.toml, comme tous les scripts), sinon défauts.

    Thème ([app] theme) : absent -> or_et_nuit ; inconnu, ou une couche de
    configuration illisible -> repli sûr sur jarvis_bleu.
    """
    config = dict(DEFAUTS)
    config["langue"] = "en"  # défaut du projet ; voir [general] langue
    dossier = racine / "config"
    try:
        donnees = config_jarvis.charger_donnees(dossier)
        illisible = bool(config_jarvis.fichiers_illisibles(dossier))
    except Exception:  # Une config cassée ne doit jamais empêcher le lancement.
        donnees, illisible = {}, True
    app = config_jarvis.section(donnees, "app")
    for cle in DEFAUTS:
        if cle in app and cle != "theme":
            config[cle] = app[cle]
    # Langue de l'interface = langue de la boucle vocale ([general] langue ;
    # l'ancien [boucle] langue reste respecté).
    langue = config_jarvis.langue(donnees)
    if langue in LANGUES:
        config["langue"] = langue
    try:
        if illisible:
            config["theme"] = THEME_REPLI
        else:
            config["theme"] = nom_theme(app.get("theme", DEFAUTS["theme"]))
    except Exception:  # Un thème illisible ne doit jamais empêcher le lancement.
        config["theme"] = THEME_REPLI
    for cle in ("animations", "tableau_de_bord"):
        config[cle] = valeur_booleenne(config.get(cle), DEFAUTS[cle])
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
              "langue": "", "present": False, "prive": False}
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
        # Lot DB : état signalé par la boucle (cerveau, voix, navigateur).
        "agents": ({str(k): str(v) for k, v in donnees["agents"].items()}
                   if isinstance(donnees.get("agents"), dict) else {}),
        # Lot PR : mode privé actif (pastille « Privé »).
        "prive": donnees.get("prive") is True,
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
        # Durée totale (jauge du thème stylé) : de la création à l'échéance ;
        # None si inconnue (ancien fichier).
        cree = _analyser_echeance(minuteur.get("created"))
        total = (due - cree).total_seconds() if cree is not None else None
        try:
            reste_pause = (float(minuteur.get("remaining_s") or 0)
                           if minuteur.get("paused") else None)
        except (TypeError, ValueError):
            reste_pause = 0.0
        resultat.append({
            "id": minuteur.get("id"),
            "due": due,
            "label": str(minuteur.get("label", "")),
            "kind": str(minuteur.get("kind", "timer")),
            "total_s": total if total and total > 0 else None,
            # Lot U3 : en pause, temps restant figé (le minuteur ne sonne pas).
            "pause_s": reste_pause,
        })
    # En pause : après ceux qui tournent.
    resultat.sort(key=lambda m: (m.get("pause_s") is not None, m["due"]))
    return resultat


def etat_jauge_minuteur(minuteur: dict, ref: datetime) -> tuple:
    """(fraction restante 0..1, clé de statut) d'un minuteur, pour sa jauge :
    « erreur » échu, « attente » dans la dernière minute, « actif » sinon.
    Sans durée totale connue, la jauge est pleine."""
    if minuteur.get("pause_s") is not None:
        total = minuteur.get("total_s")
        reste = minuteur["pause_s"]
        return (min(1.0, reste / total) if total else 1.0), "inactif"
    reste = (minuteur["due"] - ref).total_seconds()
    if reste < 0:
        return 0.0, "erreur"
    total = minuteur.get("total_s")
    fraction = min(1.0, reste / total) if total else 1.0
    return fraction, "attente" if reste < 60 else "actif"


MAX_RECHERCHES_PANNEAU = 6


def charger_recherches(chemin: Path = FICHIER_RECHERCHES) -> list:
    """Lit data/recherches.json (lecture seule) ; la plus récente d'abord.

    Fichier absent ou illisible : liste vide (l'application ne le répare
    jamais et ne le réécrit jamais — c'est la boucle qui en a la charge).
    """
    try:
        donnees = json.loads(Path(chemin).read_text(encoding="utf-8"))
        taches = donnees.get("recherches", [])
    except (OSError, ValueError, AttributeError):
        return []
    propres = [t for t in taches if isinstance(t, dict)
               and isinstance(t.get("id"), int)
               and t.get("statut") in recherche_mod.STATUTS]
    return sorted(propres, key=lambda t: -t["id"])


def formater_recherches(recherches: list, langue: str = "fr") -> tuple:
    """Lignes « • question — statut » du panneau Recherches."""
    lignes = []
    for tache in recherches[:MAX_RECHERCHES_PANNEAU]:
        question = recherche_mod.texte_parle(tache.get("question", ""), 40)
        lignes.append(f"• {question} — "
                      f"{recherche_mod.etiquette_statut(tache, langue)}")
    return tuple(lignes) if lignes else (_texte(langue, "aucune_recherche"),)


MAX_TACHES_PANNEAU = 4


def charger_taches(chemin: Path | None = None) -> list:
    """Lit data/taches_longues.json (lecture seule) ; la plus récente
    d'abord. Absent ou illisible : liste vide (l'application ne l'écrit
    jamais : c'est le travailleur de la boucle, sous verrou)."""
    try:
        donnees = json.loads(Path(chemin or FICHIER_TACHES).read_text(
            encoding="utf-8"))
        taches = donnees.get("taches", [])
    except (OSError, ValueError, AttributeError):
        return []
    propres = [t for t in taches if isinstance(t, dict)
               and isinstance(t.get("id"), int)
               and t.get("etat") in taches_mod.ETATS
               and isinstance(t.get("plan", []), list)]
    return sorted(propres, key=lambda t: -t["id"])


def formater_taches(taches: list, langue: str = "fr") -> tuple:
    """Lignes « • titre — 3/7 · en cours » du panneau Tâches longues."""
    lignes = []
    for tache in taches[:MAX_TACHES_PANNEAU]:
        titre = recherche_mod.texte_parle(
            tache.get("titre") or tache.get("objectif", ""), 32)
        lignes.append(f"• {titre} — {taches_mod.progression(tache)} · "
                      f"{taches_mod.etiquette_etat(tache, langue)}")
    return tuple(lignes) if lignes else (_texte(langue, "aucune_tache"),)


def statut_tache(tache: dict) -> str:
    """Couleur d'une tâche longue : terminée « ok », en cours « actif »
    (« attente » si elle attend son tour ou un nouvel essai), bloquée
    « erreur », budget épuisé ou annulée « attente »."""
    if tache.get("etat") == "terminee":
        return "ok"
    if tache.get("etat") == "en_cours":
        if not tache.get("demarree") or tache.get("attente"):
            return "attente"
        return "actif"
    raison = str(tache.get("raison") or "")
    return "attente" if raison.startswith("budget") or raison == "annulee" \
        else "erreur"


MAX_NOTES_PANNEAU = 50          # au-delà : « … et N de plus » (widgets légers)
DELAI_CONFIRMATION_SUPPRESSION_MS = 4000


def charger_notes(chemin: Path | None = None) -> list:
    """Lit data/connaissances.json (lecture seule) ; la plus récente d'abord.

    Fichier absent ou illisible : liste vide — l'application ne le répare
    jamais (c'est connaissances.py, sous verrou, qui écrit).
    """
    try:
        donnees = json.loads(Path(chemin or FICHIER_CONNAISSANCES).read_text(
            encoding="utf-8"))
        notes = donnees.get("notes", [])
    except (OSError, ValueError, AttributeError):
        return []
    propres = [n for n in notes if isinstance(n, dict)
               and isinstance(n.get("id"), int)
               and isinstance(n.get("texte"), str) and n["texte"].strip()]
    return sorted(propres, key=lambda n: -n["id"])


def formater_notes(notes: list, langue: str = "fr") -> tuple:
    """(texte court, date) de chaque note du panneau Connaissances."""
    return tuple(
        (recherche_mod.texte_parle(n["texte"], 90),
         connaissances_mod.formater_date(str(n.get("cree_le", "")), langue))
        for n in notes[:MAX_NOTES_PANNEAU])


TAILLE_JAUGE = 22                  # jauge circulaire d'un minuteur (px)
LARGEUR_MONITEUR = 130             # moniteur système de l'en-tête (3 jauges)


def statut_recherche(tache: dict) -> str:
    """Clé de statut (couleur) d'une recherche : prête « ok », en cours
    « actif », en file « attente », échec « erreur »."""
    if tache.get("statut") == "prete":
        return "ok"
    if tache.get("statut") == "echec":
        return "erreur"
    return "actif" if tache.get("demarree_le") else "attente"


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
        if minuteur.get("pause_s") is not None:
            lignes.append(_texte(langue, "minuteur_pause").format(
                quoi=quoi, duree=formater_compte_a_rebours(
                    max(0.0, minuteur["pause_s"]), langue)))
        elif reste < 0:
            lignes.append(_texte(langue, "minuteur_echu").format(quoi=quoi))
        else:
            lignes.append(_texte(langue, "minuteur_reste").format(
                quoi=quoi,
                duree=formater_compte_a_rebours(reste, langue)))
    return tuple(lignes) if lignes else (_texte(langue, "aucun_minuteur"),)


# ---------------------------------------------------------------------------
# Lot DB — moniteur système, agents, conversations (fonctions pures)
# ---------------------------------------------------------------------------

INTERVALLE_SYSTEME_MS = 5000       # moniteur système : une mesure / 5 s
TAILLE_JAUGE_SYSTEME = 34          # jauges CPU / RAM / disque (px)
LARGEUR_TABLEAU_BORD = 1100        # colonne Agents + Conversations dès cette largeur
INTERVALLE_JOURS_S = 300.0         # liste des jours relue au plus toutes les 5 min
MAX_JOURS_PANNEAU = 14


def _psutil():
    """Le module psutil, importé à la première mesure ; None s'il manque."""
    try:
        import psutil  # chargé seulement quand le moniteur mesure.
        return psutil
    except ImportError:
        return None


def disque_systeme() -> str:
    """Racine du disque système (« C:\\ » sous Windows, « / » sinon)."""
    if os.name == "nt":
        return os.environ.get("SystemDrive", "C:") + "\\"
    return "/"


def mesurer_systeme(sonde=None, disque: str | None = None) -> dict | None:
    """{"cpu", "ram", "disque"} en pourcentage (0 à 100, None si illisible),
    ou None si psutil est absent. `sonde` remplace psutil (tests).
    cpu_percent(interval=None) ne bloque jamais : il rend l'usage depuis
    l'appel précédent (0 au tout premier)."""
    sonde = sonde if sonde is not None else _psutil()
    if sonde is None:
        return None
    disque = disque or disque_systeme()
    mesures = {}
    for cle, lire in (
            ("cpu", lambda: sonde.cpu_percent(interval=None)),
            ("ram", lambda: sonde.virtual_memory().percent),
            ("disque", lambda: sonde.disk_usage(disque).percent)):
        try:
            mesures[cle] = max(0.0, min(100.0, float(lire())))
        except Exception:
            mesures[cle] = None
    return mesures


def statut_charge(pourcent) -> str:
    """Couleur d'une jauge système : « ok » sous 70 %, « attente » sous
    90 %, « erreur » au-delà, « inactif » si inconnue."""
    if pourcent is None:
        return "inactif"
    if pourcent >= 90:
        return "erreur"
    return "attente" if pourcent >= 70 else "ok"


AGENTS = ("cerveau", "voix", "navigateur", "minuteurs", "recherches",
          "taches", "notes")


def etats_agents(etat: dict, minuteurs: list, recherches: list,
                 notes_ok: bool = True, taches: list | None = None) -> dict:
    """État de chaque capacité : « actif », « veille » ou « erreur ».

    Cerveau, voix et navigateur dépendent de la boucle vocale : boucle
    arrêtée = erreur. Le champ optionnel « agents » de data/hud-state.json
    (écrit par la boucle) signale une erreur du cerveau ou de la voix, et la
    session Chrome pilotée ouverte (« navigateur » : « actif »).
    """
    boucle = etat.get("etat", "arrete")
    signales = etat.get("agents")
    signales = signales if isinstance(signales, dict) else {}

    def depuis_boucle(nom, actif):
        if boucle == "arrete" or signales.get(nom) == "erreur":
            return "erreur"
        return "actif" if actif else "veille"

    erreur_texte = str(etat.get("erreur", "")).lower()
    erreur_voix = boucle == "erreur" and any(
        mot in erreur_texte for mot in ("micro", "transcription", "voix"))
    resultat = {
        "cerveau": depuis_boucle("cerveau", boucle == "reflexion"),
        "voix": ("erreur" if erreur_voix else
                 depuis_boucle("voix", boucle in ("ecoute", "reponse"))),
        "navigateur": depuis_boucle(
            "navigateur", signales.get("navigateur") == "actif"),
        "minuteurs": ("actif" if any(m.get("pause_s") is None
                                     for m in minuteurs) else "veille"),
        "recherches": ("actif" if any(
            t.get("statut") in ("en_attente", "en_cours")
            for t in recherches) else "veille"),
        "taches": ("actif" if any(t.get("etat") == "en_cours"
                                  for t in taches or []) else "veille"),
        "notes": "veille" if notes_ok else "erreur",
    }
    if boucle == "erreur" and not erreur_voix:
        resultat["cerveau"] = "erreur"
    return resultat


def notes_lisibles(chemin: Path | None = None) -> bool:
    """Faux si data/connaissances.json existe mais ne se lit pas."""
    chemin = Path(chemin or FICHIER_CONNAISSANCES)
    try:
        if not chemin.exists():
            return True
        return isinstance(json.loads(chemin.read_text(encoding="utf-8")),
                          dict)
    except (OSError, ValueError):
        return False


def formater_jours(jours: list, langue: str = "fr") -> tuple:
    """(libellé, nombre de messages) de chaque jour du panneau
    Conversations, du plus récent au plus ancien."""
    lignes = []
    for jour in jours[:MAX_JOURS_PANNEAU]:
        libelle = (_texte(langue, "ancien_journal")
                   if jour["date"] == "Ancien journal"
                   else formater_jour(jour["date"]))
        lignes.append((libelle, _texte(langue, "jour_messages").format(
            n=jour["messages"])))
    return tuple(lignes)


# ---------------------------------------------------------------------------
# Lot U5 — animations (aucune au repos : rien n'est planifié sans animation)
# ---------------------------------------------------------------------------

PAS_TRANSITION_MS = 40             # une image / 40 ms, pendant l'animation seulement
DUREE_ECLOSION_MS = 360            # orbe : petit « gonflement » au changement d'état
AMPLITUDE_ECLOSION = 0.10          # halo 52 px x 1,10 = 57 px : tient dans 116 px
DUREE_SURLIGNAGE_MS = 520          # nouvel élément d'un panneau : fondu de couleur


class Animateur:
    """Animations courtes, toutes sur UNE boucle after() qui ne tourne que
    pendant qu'il y a une animation : au repos, aucun appel planifié
    (~0 % CPU). `actif` False (réglage [app] animations = false) : chaque
    animation saute directement à sa dernière image, sans rien planifier.

    Une animation = durée + fonction(t), t allant de 0 à 1, compté en
    images de PAS_TRANSITION_MS (une machine chargée allonge l'animation au
    lieu de sauter des images). La même clé remplace l'animation en cours.
    """

    def __init__(self, fenetre, actif: bool = True):
        self.fenetre, self.actif = fenetre, actif
        self._animations: dict = {}
        self._planifie = None

    def en_cours(self, cle=None) -> bool:
        if cle is None:
            return bool(self._animations)
        return cle in self._animations

    def lancer(self, cle, duree_ms: int, etape) -> None:
        if not self.actif or duree_ms <= 0:
            self._appeler(etape, 1.0)
            return
        images = max(1, round(duree_ms / PAS_TRANSITION_MS))
        self._animations[cle] = [0, images, etape]
        if self._planifie is None:
            self._planifie = self.fenetre.after(PAS_TRANSITION_MS, self._image)

    @staticmethod
    def _appeler(etape, t: float) -> bool:
        try:
            etape(t)
            return True
        except Exception:  # widget détruit entre-temps : animation abandonnée.
            return False

    def _image(self) -> None:
        self._planifie = None
        for cle, animation in list(self._animations.items()):
            animation[0] += 1
            t = min(1.0, animation[0] / animation[1])
            if not self._appeler(animation[2], t) or t >= 1.0:
                self._animations.pop(cle, None)
        if self._animations:
            try:
                self._planifie = self.fenetre.after(PAS_TRANSITION_MS,
                                                    self._image)
            except Exception:
                self._animations.clear()


def courbe_eclosion(t: float) -> float:
    """Échelle de l'orbe pendant l'éclosion : 1 + A au début, 1 à la fin."""
    return 1.0 + AMPLITUDE_ECLOSION * (1.0 - max(0.0, min(1.0, t))) ** 2


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


def ecrire_demande_prive(chemin: Path, actif: bool, langue: str = "") -> None:
    """Lot PR : demande d'entrer (actif=True) ou de sortir du mode privé,
    pour la boucle (data/prive-demande.json, consommé à la lecture).

    Ne contient aucun contenu de conversation. Écriture atomique ; toute
    erreur est silencieuse.
    """
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        donnees = {
            "actif": bool(actif),
            "langue": langue if langue in LANGUES else "",
            "horodatage": datetime.now(FUSEAU).isoformat(timespec="seconds"),
        }
        temporaire = chemin.with_suffix(".json.tmp")
        temporaire.write_text(json.dumps(donnees), encoding="utf-8")
        os.replace(temporaire, chemin)
    except OSError:
        pass


_POLICES: dict = {}


def _police(taille: int, gras: bool = False, titre: bool = False):
    """Police Segoe UI partagée : une seule par (taille, graisse), au lieu
    d'une par étiquette (la conversation compte jusqu'à 200 bulles).

    `titre` : police des titres du thème stylé (Bahnschrift) — mêmes tailles
    que le lot U1 ; Segoe UI dans les thèmes classiques."""
    famille = (STYLE.get("police_titre") if titre else None) or "Segoe UI"
    cle = (taille, gras, famille)
    if cle not in _POLICES:
        _POLICES[cle] = ctk.CTkFont(family=famille, size=taille,
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
    # Thème stylé : liseré fin autour des bulles (comme les panneaux).
    bordure = STYLE.get("bordure_bulle_utilisateur" if entree["role"] == "user"
                        else "bordure_bulle_jarvis")
    options = {"border_width": 1, "border_color": bordure} if bordure else {}
    cadre = ctk.CTkFrame(conteneur, fg_color=couleur_bulle,
                         corner_radius=RAYON_BULLE, **options)
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


def est_en_bas(debut: float, fin: float,
               tolerance: float = TOLERANCE_BAS) -> bool:
    """Vrai si la vue défilante est en bas (ou si tout le contenu tient dans
    la fenêtre) : `debut` et `fin` sont les fractions visibles de yview()."""
    return fin >= 1.0 - tolerance


def _fond_de_fenetre(fenetre) -> None:
    """Applique le fond du thème à une fenêtre (racine ou Historique). Sans
    effet pour jarvis_bleu (fond d'origine de CustomTkinter) ; jamais
    bloquant : une couleur de fond refusée n'empêche pas d'ouvrir la fenêtre."""
    if not COULEUR_FOND_FENETRE:
        return
    try:
        fenetre.configure(fg_color=COULEUR_FOND_FENETRE)
    except Exception as erreur:
        print(f"Avertissement application : fond de fenêtre : {erreur}",
              file=sys.stderr)


def _fondre(couleur_hex: str, fond_hex: str, facteur: float) -> str:
    """Mélange une couleur #RRGGBB avec le fond de l'orbe : `facteur` 1,0 =
    la couleur pure, 0,0 = le fond. Fond noir : identique à _assombrir()
    (thèmes sombres) ; fond blanc : halo qui s'éclaircit (thème clair)."""
    try:
        c = [int(couleur_hex[i:i + 2], 16) for i in (1, 3, 5)]
        f = [int(fond_hex[i:i + 2], 16) for i in (1, 3, 5)]
    except (ValueError, IndexError):
        return couleur_hex
    mix = [int(c[i] * facteur + f[i] * (1.0 - facteur)) for i in range(3)]
    return f"#{mix[0]:02x}{mix[1]:02x}{mix[2]:02x}"


# ---------------------------------------------------------------------------
# Orbe en globe filaire (thème stylé) — géométrie pure, testable sans écran
# ---------------------------------------------------------------------------

GLOBE_RAYON = 38                   # sphère (échelle 1,0) ; halo : ORBE_RAYONS[0]
GLOBE_MERIDIENS = 4                # ellipses verticales qui tournent
GLOBE_PARALLELES = (-50, -25, 0, 25, 50)   # latitudes (degrés)
GLOBE_INCLINAISON = 0.24           # aplatissement des parallèles (vue de biais)
GLOBE_ORBITE = (1.34, 0.30)        # anneau d'orbite : (rx, ry) / rayon (satellite compris, tient dans 116 px)
GLOBE_COEUR = 4                    # point central


def geometrie_globe(echelle: float, angle: float) -> dict:
    """Coordonnées (x0, y0, x1, y1) des éléments du globe, centrées dans le
    canevas de l'orbe (ORBE_TAILLE, inchangé). `angle` (radians) fait
    tourner les méridiens et le satellite. Tout tient dans le canevas."""
    c = ORBE_CENTRE
    r = GLOBE_RAYON * echelle

    def boite(cx, cy, rx, ry):
        return (cx - rx, cy - ry, cx + rx, cy + ry)

    meridiens = []
    for k in range(GLOBE_MERIDIENS):
        phi = angle + k * math.pi / GLOBE_MERIDIENS
        meridiens.append(boite(c, c, max(0.6, r * abs(math.cos(phi))), r))
    paralleles = []
    for latitude in GLOBE_PARALLELES:
        lat = math.radians(latitude)
        rx = r * math.cos(lat)
        cy = c - r * math.sin(lat) * math.cos(GLOBE_INCLINAISON * math.pi / 2)
        paralleles.append(boite(c, cy, rx, max(0.6, rx * GLOBE_INCLINAISON)))
    orx, ory = GLOBE_ORBITE[0] * r, GLOBE_ORBITE[1] * r
    sx = c + orx * math.cos(angle * 0.7)
    sy = c + ory * math.sin(angle * 0.7)
    return {
        "halo": boite(c, c, ORBE_RAYONS[0] * echelle, ORBE_RAYONS[0] * echelle),
        "sphere": boite(c, c, r, r),
        "coeur": boite(c, c, GLOBE_COEUR, GLOBE_COEUR),
        "meridiens": meridiens,
        "paralleles": paralleles,
        "orbite": boite(c, c, orx, ory),
        "satellite": boite(sx, sy, 2.5, 2.5),
    }


def dessiner_jauge(canevas, taille: int, fraction: float, couleur: str,
                   piste: str, epaisseur: int = 3) -> None:
    """Jauge circulaire (piste + arc de `fraction`, de 0 à 1, sens horaire
    depuis midi) sur un petit canevas carré."""
    fraction = max(0.0, min(1.0, float(fraction)))
    m = epaisseur + 1
    canevas.create_oval(m, m, taille - m, taille - m, outline=piste,
                        width=epaisseur)
    if fraction >= 0.999:
        canevas.create_oval(m, m, taille - m, taille - m, outline=couleur,
                            width=epaisseur)
    elif fraction > 0:
        canevas.create_arc(m, m, taille - m, taille - m, start=90,
                           extent=-360 * fraction, style="arc",
                           outline=couleur, width=epaisseur)


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
        # Thème (U2) : appliqué AVANT la création des widgets, qui lisent
        # les couleurs à leur création. Inconnu : repli jarvis_bleu.
        self.theme = appliquer_theme(config.get("theme", DEFAUTS["theme"]))
        ctk.set_appearance_mode(MODE_APPARENCE)

        self.fenetre = ctk.CTk()
        _fond_de_fenetre(self.fenetre)
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
        self._tuiles_minuteurs: list = []  # thème stylé : (texte, jauge)
        self._cle_recherches: tuple = ()
        self._cle_taches: tuple = ()
        self._micro_enfonce = False
        self._etiquettes_bulles: list = []
        self._apres_redimensionnement = None
        self._apres_geometrie = None
        self._derniere_largeur = 0
        self._horloge_affichee = ""
        self._message_vide = None
        self._fenetre_historique = None
        self._historique: dict | None = None
        # Défilement de la conversation (U2) : suivre les nouveaux messages
        # seulement si l'utilisateur était en bas.
        self._apres_defilement = None
        self._verif_defilement = None
        self._defilement_bas_voulu = False
        self._defilement_fraction: float | None = None
        self._dernier_bas = True
        # Lot U5 : animations (une seule boucle after, seulement pendant une
        # animation) ; [app] animations = false les coupe toutes.
        self._animations = bool(config.get("animations", True))
        self._animateur = Animateur(self.fenetre, self._animations)
        self._ids_vus: dict = {}          # panneau -> identifiants déjà vus
        # Lot U3 : minuteurs affichés (le clic d'une tuile retrouve le sien
        # par sa position, même quand la tuile est mise à jour sur place).
        self._minuteurs_affiches: list = []
        self._fenetre_minuteur = None
        self._annulation_armee = None
        # Lot DB : moniteur système, agents, conversations.
        self._mesures_systeme: dict | None = None
        self._cle_systeme = None
        self._cle_agents = None
        self._cle_jours = None
        self._jours_lus_a = float("-inf")
        self._compte_du_jour = None
        self._tableau_force: bool | None = None
        self._tableau_visible = False
        # Lot PR : mode privé tel que signalé par la boucle (hud-state.json).
        self.prive = False
        self.libelle_menu_prive = self.t("menu_prive_activer")

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
        # Lot DB : afficher / masquer la colonne Agents + Conversations.
        self._menu_affichage = tk.Menu(self._barre_menu, tearoff=0)
        self._menu_affichage.add_command(label=self.t("menu_tableau"),
                                         command=self.basculer_tableau_de_bord)
        # Lot PR : interrupteur du mode privé (entrée n° 1 du menu).
        self._menu_affichage.add_command(label=self.libelle_menu_prive,
                                         command=self.basculer_mode_prive)
        self._barre_menu.add_cascade(label=self.t("menu_affichage"),
                                     menu=self._menu_affichage)
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
        # Thème stylé : globe filaire (même canevas de 116 px) ; sinon les
        # trois disques du lot U1.
        self._globe: dict | None = None
        self._angle_globe = 0.6  # radians ; fixe au repos (aucun dessin).
        if STYLE.get("orbe") == "globe":
            self._creer_globe()
        else:
            (self._orbe_halo, self._orbe_milieu,
             self._orbe_coeur) = (
                self.canvas_orbe.create_oval(
                    ORBE_CENTRE - r, ORBE_CENTRE - r,
                    ORBE_CENTRE + r, ORBE_CENTRE + r, fill="", outline="")
                for r in ORBE_RAYONS)

        self.texte_etat = ctk.CTkLabel(
            self.entete, text=self.t("etat_arrete"),
            font=_police(20, True, titre=True),
            text_color=COULEUR_TEXTE, anchor="w")
        self.texte_etat.grid(row=0, column=1, sticky="sw", padx=10,
                             pady=(0, 2))
        self.texte_detail = ctk.CTkLabel(
            self.entete, text=self.t("detail_arrete"), font=_police(12),
            text_color=COULEUR_TEXTE_FAIBLE, anchor="w", justify="left",
            wraplength=max(200, config["largeur"] - 340 - LARGEUR_MONITEUR))
        self.texte_detail.grid(row=1, column=1, sticky="nw", padx=10,
                               pady=(2, 0))
        # Lot PR : pastille « ● PRIVÉ » (violet), visible en mode privé.
        self.pastille_prive = ctk.CTkLabel(
            self.entete, text=self.t("pastille_prive"),
            font=_police(11, True, titre=True), fg_color=COULEUR_PRIVE,
            text_color="#FFFFFF", corner_radius=10, height=22)
        self.pastille_prive.grid(row=0, column=1, sticky="se", padx=10,
                                 pady=(0, 2))
        self.pastille_prive.grid_remove()

        # Lot DB : moniteur système (CPU, RAM, disque), jauges circulaires
        # comme celles des minuteurs ; une mesure toutes les 5 s.
        self.panneau_systeme = ctk.CTkFrame(self.entete,
                                            fg_color="transparent")
        self.panneau_systeme.grid(row=0, column=2, rowspan=2, padx=(6, 0),
                                  pady=12)
        self._jauges_systeme: dict = {}
        for colonne, cle in enumerate(("cpu", "ram", "disque")):
            cellule = ctk.CTkFrame(self.panneau_systeme,
                                   fg_color="transparent")
            cellule.grid(row=0, column=colonne, padx=4)
            canevas = tk.Canvas(cellule, width=TAILLE_JAUGE_SYSTEME,
                                height=TAILLE_JAUGE_SYSTEME,
                                bg=COULEUR_PANNEAU, highlightthickness=0, bd=0)
            canevas.pack()
            valeur = ctk.CTkLabel(cellule, text=self.t("systeme_indispo"),
                                  font=_police(10, True, titre=True),
                                  text_color=COULEUR_TEXTE, height=14)
            valeur.pack()
            nom = ctk.CTkLabel(cellule, text=self._titre(f"systeme_{cle}"),
                               font=_police(9, titre=True),
                               text_color=COULEUR_TEXTE_FAIBLE, height=12)
            nom.pack()
            self._jauges_systeme[cle] = (canevas, valeur, nom)

        self.texte_horloge = ctk.CTkLabel(
            self.entete, text="--:--:--", font=_police(24, True, titre=True),
            text_color=COULEUR_TEXTE)
        # Thème stylé : pastille d'état colorée (« ● EN LIGNE ») au-dessus de
        # l'horloge, comme « SYSTEM STATUS ● OPTIMAL » de la référence.
        self.pastille_etat = None
        if STYLE:
            self.pastille_etat = ctk.CTkLabel(
                self.entete, text="", font=_police(11, True, titre=True),
                fg_color=COULEUR_FOND, corner_radius=10, height=22,
                text_color=couleur_statut("inactif", COULEUR_TEXTE_FAIBLE))
            self.pastille_etat.grid(row=0, column=3, sticky="s", padx=24,
                                    pady=(12, 0))
            self.texte_horloge.grid(row=1, column=3, sticky="n", padx=24,
                                    pady=(2, 12))
            self._maj_pastille()
        else:
            self.texte_horloge.grid(row=0, column=3, rowspan=2, padx=24,
                                    pady=12)

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
                scrollbar_button_hover_color=COULEUR_BARRE_DEFILEMENT_SURVOL)
        except (TypeError, ValueError, tk.TclError):
            # Version de CustomTkinter sans ces options : barre d'origine.
            self.zone_conversation = ctk.CTkScrollableFrame(
                self.centre, fg_color=COULEUR_FOND, corner_radius=0,
                scrollbar_button_color=COULEUR_BARRE_DEFILEMENT)
        try:  # Barre fine (attribut interne : au mieux, sans incidence).
            self.zone_conversation._scrollbar.configure(width=8)
        except Exception:
            pass
        self.zone_conversation.grid(row=0, column=0, rowspan=4,
                                    sticky="nsew", padx=(8, 0), pady=8)
        # add="+" : CTkScrollableFrame met à jour sa zone de défilement
        # (scrollregion) dans sa propre liaison <Configure> ; sans add="+",
        # ce bind la REMPLACE et la barre de défilement ne suit plus le
        # contenu (bug constaté à l'essai : bloqué sur les premiers échanges).
        self.zone_conversation.bind(
            "<Configure>", self._sur_redimensionnement, add="+")

        self.panneau_minuteurs = ctk.CTkFrame(
            self.centre, fg_color=COULEUR_PANNEAU, corner_radius=12,
            **options_panneau())
        self.panneau_minuteurs.grid(row=0, column=1, sticky="new",
                                    padx=8, pady=(8, 4))
        self.panneau_minuteurs.configure(width=230)
        self.titre_minuteurs = ctk.CTkLabel(
            self.panneau_minuteurs, text=self._titre("minuteurs"),
            font=_police(14, True, titre=True),
            text_color=STYLE.get("titre_panneau") or COULEUR_TEXTE,
            anchor="w")
        self.titre_minuteurs.pack(fill="x", padx=12, pady=(10, 2))
        self.conteneur_minuteurs = ctk.CTkFrame(
            self.panneau_minuteurs, fg_color="transparent")
        self.conteneur_minuteurs.pack(fill="x", padx=4, pady=(0, 10))

        # Panneau Recherches (lot R1), sous les minuteurs : lecture seule.
        # Lot KB : minuteurs et recherches restent compacts en haut ; le
        # panneau Connaissances (rangée 3 depuis le lot LT) prend la hauteur
        # qui reste.
        self.centre.grid_rowconfigure(0, weight=0)
        self.centre.grid_rowconfigure(1, weight=0)
        self.centre.grid_rowconfigure(2, weight=0)
        self.centre.grid_rowconfigure(3, weight=1)
        self.panneau_recherches = ctk.CTkFrame(
            self.centre, fg_color=COULEUR_PANNEAU, corner_radius=12,
            **options_panneau())
        self.panneau_recherches.grid(row=1, column=1, sticky="new",
                                     padx=8, pady=4)
        self.panneau_recherches.configure(width=230)
        self.titre_recherches = ctk.CTkLabel(
            self.panneau_recherches, text=self._titre("recherches"),
            font=_police(14, True, titre=True),
            text_color=STYLE.get("titre_panneau") or COULEUR_TEXTE,
            anchor="w")
        self.titre_recherches.pack(fill="x", padx=12, pady=(10, 2))
        self.conteneur_recherches = ctk.CTkFrame(
            self.panneau_recherches, fg_color="transparent")
        self.conteneur_recherches.pack(fill="x", padx=4, pady=(0, 10))

        # Panneau Tâches longues (lot LT), rangée suivante, comme Recherches :
        # lecture seule, état et progression, clic = détail.
        self.panneau_taches = ctk.CTkFrame(
            self.centre, fg_color=COULEUR_PANNEAU, corner_radius=12,
            **options_panneau())
        self.panneau_taches.grid(row=2, column=1, sticky="new", padx=8,
                                 pady=4)
        self.panneau_taches.configure(width=230)
        self.titre_taches = ctk.CTkLabel(
            self.panneau_taches, text=self._titre("taches"),
            font=_police(14, True, titre=True),
            text_color=STYLE.get("titre_panneau") or COULEUR_TEXTE,
            anchor="w")
        self.titre_taches.pack(fill="x", padx=12, pady=(10, 2))
        self.conteneur_taches = ctk.CTkFrame(
            self.panneau_taches, fg_color="transparent")
        self.conteneur_taches.pack(fill="x", padx=4, pady=(0, 10))

        # Panneau Connaissances (lot KB), sous les recherches : notes (texte
        # + date) et suppression confirmée. Liste défilante à elle : la
        # conversation garde son propre défilement (U2), inchangé.
        self.panneau_connaissances = ctk.CTkFrame(
            self.centre, fg_color=COULEUR_PANNEAU, corner_radius=12,
            **options_panneau())
        self.panneau_connaissances.grid(row=3, column=1, sticky="nsew",
                                        padx=8, pady=(4, 8))
        self.panneau_connaissances.configure(width=230)
        self.titre_connaissances = ctk.CTkLabel(
            self.panneau_connaissances, text=self._titre("connaissances"),
            font=_police(14, True, titre=True),
            text_color=STYLE.get("titre_panneau") or COULEUR_TEXTE,
            anchor="w")
        self.titre_connaissances.pack(fill="x", padx=12, pady=(10, 2))
        self.conteneur_connaissances = ctk.CTkScrollableFrame(
            self.panneau_connaissances, fg_color=COULEUR_PANNEAU,
            corner_radius=0, width=200, height=120,
            scrollbar_button_color=COULEUR_BARRE_DEFILEMENT)
        self.conteneur_connaissances.pack(fill="both", expand=True,
                                          padx=4, pady=(0, 10))
        self._cle_connaissances: tuple = ()
        self._note_a_confirmer: int | None = None
        self._apres_confirmation_note = None

        # Lot DB : colonne du tableau de bord (Agents, Conversations), à
        # droite des panneaux existants, affichée quand la fenêtre est assez
        # large (ou par le menu Affichage). Les panneaux U2/R1/KB ne bougent
        # pas.
        self.colonne_bord = ctk.CTkFrame(self.centre, fg_color="transparent",
                                         corner_radius=0)
        self.colonne_bord.grid_rowconfigure(1, weight=1)
        self.colonne_bord.grid_columnconfigure(0, weight=1)
        self.panneau_agents = ctk.CTkFrame(
            self.colonne_bord, fg_color=COULEUR_PANNEAU, corner_radius=12,
            **options_panneau())
        self.panneau_agents.grid(row=0, column=0, sticky="new", padx=(0, 8),
                                 pady=(8, 4))
        self.panneau_agents.configure(width=220)
        self.titre_agents = ctk.CTkLabel(
            self.panneau_agents, text=self._titre("agents"),
            font=_police(14, True, titre=True),
            text_color=STYLE.get("titre_panneau") or COULEUR_TEXTE,
            anchor="w")
        self.titre_agents.pack(fill="x", padx=12, pady=(10, 2))
        self.conteneur_agents = ctk.CTkFrame(self.panneau_agents,
                                             fg_color="transparent")
        self.conteneur_agents.pack(fill="x", padx=4, pady=(0, 10))
        self._lignes_agents: dict = {}
        for cle in AGENTS:
            rangee = ctk.CTkFrame(self.conteneur_agents, **options_tuile())
            rangee.pack(fill="x", padx=6, pady=2)
            point = ctk.CTkLabel(rangee, text="●", font=_police(12), width=14,
                                 height=22,
                                 text_color=couleur_etat("inactif"))
            point.pack(side="left", padx=(8, 4), pady=2)
            nom = ctk.CTkLabel(rangee, text=self.t(f"agent_{cle}"),
                               font=_police(12), text_color=COULEUR_TEXTE,
                               anchor="w", height=22)
            nom.pack(side="left", fill="x", expand=True, pady=2)
            statut = ctk.CTkLabel(rangee, text="", font=_police(11),
                                  text_color=COULEUR_TEXTE_FAIBLE, anchor="e",
                                  height=22)
            statut.pack(side="right", padx=(4, 8), pady=2)
            self._lignes_agents[cle] = (point, nom, statut)

        self.panneau_conversations = ctk.CTkFrame(
            self.colonne_bord, fg_color=COULEUR_PANNEAU, corner_radius=12,
            **options_panneau())
        self.panneau_conversations.grid(row=1, column=0, sticky="nsew",
                                        padx=(0, 8), pady=(4, 8))
        self.panneau_conversations.configure(width=220)
        self.titre_conversations = ctk.CTkLabel(
            self.panneau_conversations, text=self._titre("conversations"),
            font=_police(14, True, titre=True),
            text_color=STYLE.get("titre_panneau") or COULEUR_TEXTE,
            anchor="w")
        self.titre_conversations.pack(fill="x", padx=12, pady=(10, 2))
        self.conteneur_conversations = ctk.CTkScrollableFrame(
            self.panneau_conversations, fg_color=COULEUR_PANNEAU,
            corner_radius=0, width=190, height=120,
            scrollbar_button_color=COULEUR_BARRE_DEFILEMENT)
        self.conteneur_conversations.pack(fill="both", expand=True, padx=4,
                                          pady=(0, 10))

        # -- Barre du bas : micro + interruption ------------------------
        self.barre_bas = ctk.CTkFrame(
            self.fenetre, fg_color=COULEUR_PANNEAU, corner_radius=0)
        self.barre_bas.grid(row=2, column=0, sticky="ew")
        self.barre_bas.grid_columnconfigure(0, weight=1)

        self.bouton_micro = ctk.CTkButton(
            self.barre_bas, text=self.t("micro_repos"),
            font=_police(16, True, titre=True),
            fg_color=COULEUR_ACCENT, hover_color=COULEUR_ACCENT_SURVOL,
            text_color=COULEUR_TEXTE_SUR_ACCENT,
            corner_radius=HAUTEUR_BOUTON_PRINCIPAL // 2,
            height=HAUTEUR_BOUTON_PRINCIPAL)
        self.bouton_micro.grid(row=0, column=0, sticky="ew",
                               padx=(16, 8), pady=(12, 4))
        if STYLE:  # pilule sombre au contour cyan (« TALK TO JARVIS »).
            self._style_micro(False)
        self.bouton_micro.bind("<ButtonPress-1>", self._micro_presse)
        self.bouton_micro.bind("<ButtonRelease-1>", self._micro_relache)

        self.bouton_interrompre = ctk.CTkButton(
            self.barre_bas, text=self.t("interrompre"), font=_police(14),
            fg_color="transparent", hover_color=COULEUR_INTERROMPRE_SURVOL,
            text_color=COULEUR_INTERROMPRE_TEXTE, border_width=1,
            border_color=COULEUR_INTERROMPRE_BORDURE,
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
            font=_police(14), height=HAUTEUR_SAISIE, **OPTIONS_CHAMP)
        self.champ_texte.grid(row=2, column=0, sticky="ew",
                              padx=(16, 8), pady=(4, 14))
        self.champ_texte.bind("<Return>", lambda _e: self.envoyer_texte())

        self.bouton_envoyer = ctk.CTkButton(
            self.barre_bas, text=self.t("envoyer"), font=_police(14, True),
            fg_color=COULEUR_ACCENT, hover_color=COULEUR_ACCENT_SURVOL,
            text_color=COULEUR_TEXTE_SUR_ACCENT,
            corner_radius=HAUTEUR_SAISIE // 2,
            height=HAUTEUR_SAISIE, width=LARGEUR_BOUTON_COLONNE,
            command=self.envoyer_texte)
        self.bouton_envoyer.grid(row=2, column=1, padx=(8, 16), pady=(4, 14))

        self._dessiner_orbe(1.0)
        self._maj_tableau_de_bord()
        self.rafraichir()
        self._animer_orbe()
        self._mesurer_systeme()

    # -- Langue --------------------------------------------------------

    def t(self, cle: str) -> str:
        """Texte de l'interface dans la langue courante."""
        return _texte(self.langue, cle)

    def _titre(self, cle: str) -> str:
        """Titre de panneau (en capitales dans le thème stylé)."""
        return titre_affiche(self.t(cle))

    def _appliquer_langue(self) -> None:
        """Applique la langue courante aux textes fixes de la fenêtre. Les
        textes d'état, de minuteurs et la conversation se rafraîchissent
        seuls au prochain passage de rafraichir()."""
        def vider_minuteurs():
            self._texte_minuteurs = ()  # force la reconstruction du panneau
            self._cle_recherches = ()
            self._cle_taches = ()
            self._cle_connaissances = ()
            self._cle_agents = None
            self._cle_jours = None
            self._cle_systeme = None

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
            lambda: self.titre_minuteurs.configure(
                text=self._titre("minuteurs")),
            lambda: self.titre_recherches.configure(
                text=self._titre("recherches")),
            lambda: self.titre_taches.configure(text=self._titre("taches")),
            lambda: self.titre_connaissances.configure(
                text=self._titre("connaissances")),
            lambda: self._barre_menu.entryconfigure(
                1, label=self.t("menu_affichage")),
            lambda: self._menu_affichage.entryconfigure(
                0, label=self.t("menu_tableau")),
            self._maj_mode_prive_affiche,
            lambda: self.titre_agents.configure(text=self._titre("agents")),
            lambda: self.titre_conversations.configure(
                text=self._titre("conversations")),
            self._langue_tableau_de_bord,
            lambda: self.bouton_interrompre.configure(
                text=self.t("interrompre")),
            lambda: self.texte_astuce.configure(text=self.t("astuce")),
            lambda: self.bouton_envoyer.configure(text=self.t("envoyer")),
            lambda: self.champ_texte.configure(
                placeholder_text=self.t("placeholder")),
            lambda: self._style_micro(self._micro_enfonce),
            self._maj_pastille,
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

    def _maj_pastille(self) -> None:
        """Pastille d'état du thème stylé : texte et couleur de statut."""
        if self.pastille_etat is None:
            return
        etat = self.etat_affiche
        self.pastille_etat.configure(
            text=self.t(f"pastille_{etat}"),
            text_color=couleur_statut(STATUT_DES_ETATS.get(etat, "inactif"),
                                      COULEUR_TEXTE_FAIBLE))

    def _creer_globe(self) -> None:
        """Crée les éléments du globe filaire (thème stylé), une fois pour
        toutes : ensuite on ne fait que déplacer et recolorer (coords,
        itemconfig), jamais recréer. Dessinés du fond vers l'avant."""
        canvas = self.canvas_orbe

        def ovale(largeur=1):
            return canvas.create_oval(0, 0, 0, 0, fill="", outline="",
                                      width=largeur)

        halo = ovale()
        sphere = ovale(2)
        paralleles = [ovale() for _ in GLOBE_PARALLELES]
        meridiens = [ovale() for _ in range(GLOBE_MERIDIENS)]
        orbite = ovale()
        coeur = ovale()
        satellite = ovale()
        self._globe = {"halo": halo, "sphere": sphere,
                       "paralleles": paralleles, "meridiens": meridiens,
                       "orbite": orbite, "coeur": coeur,
                       "satellite": satellite}
        # Mêmes noms que l'orbe U1 (halo, milieu, cœur).
        self._orbe_halo, self._orbe_milieu, self._orbe_coeur = (
            halo, sphere, coeur)

    def _dessiner_globe(self, echelle: float) -> None:
        """Place et colore le globe filaire selon l'état et l'angle courant."""
        couleur = ETATS[self.etat_affiche][1]
        fond = COULEUR_ORBE_FONDU
        g = self._globe
        geo = geometrie_globe(echelle, self._angle_globe)
        canvas = self.canvas_orbe
        canvas.coords(g["halo"], *geo["halo"])
        canvas.itemconfig(g["halo"], fill=_fondre(couleur, fond, 0.10),
                          outline=_fondre(couleur, fond, 0.35))
        canvas.coords(g["sphere"], *geo["sphere"])
        canvas.itemconfig(g["sphere"], fill=_fondre(couleur, fond, 0.16),
                          outline=couleur)
        trait_parallele = _fondre(couleur, fond, 0.45)
        for item, boite in zip(g["paralleles"], geo["paralleles"]):
            canvas.coords(item, *boite)
            canvas.itemconfig(item, outline=trait_parallele)
        trait_meridien = _fondre(couleur, fond, 0.60)
        for item, boite in zip(g["meridiens"], geo["meridiens"]):
            canvas.coords(item, *boite)
            canvas.itemconfig(item, outline=trait_meridien)
        canvas.coords(g["orbite"], *geo["orbite"])
        canvas.itemconfig(g["orbite"], outline=_fondre(couleur, fond, 0.80))
        canvas.coords(g["coeur"], *geo["coeur"])
        canvas.itemconfig(g["coeur"], fill=couleur, outline="")
        canvas.coords(g["satellite"], *geo["satellite"])
        canvas.itemconfig(g["satellite"], fill=couleur, outline="")

    def _dessiner_orbe(self, echelle: float) -> None:
        """Redessine l'orbe (halo + milieu + cœur) à l'échelle donnée."""
        if self._globe is not None:
            self._dessiner_globe(echelle)
            return
        couleur = ETATS[self.etat_affiche][1]
        for item, rayon, facteur in zip(
                (self._orbe_halo, self._orbe_milieu, self._orbe_coeur),
                ORBE_RAYONS, (0.30, 0.60, 1.0)):
            r = rayon * echelle
            self.canvas_orbe.coords(
                item, ORBE_CENTRE - r, ORBE_CENTRE - r,
                ORBE_CENTRE + r, ORBE_CENTRE + r)
            self.canvas_orbe.itemconfig(
                item, fill=_fondre(couleur, COULEUR_ORBE_FONDU, facteur),
                outline="")

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
            # Lot U5 : animations coupées = orbe immobile (il change quand
            # même de couleur avec l'état).
            if not getattr(self, "_animations", True):
                periode = 0
            if periode > 0:
                if self._globe is not None:
                    # Le globe tourne (un tour en ~7 s) pendant qu'il pulse.
                    self._angle_globe = (time.monotonic() * 0.9) % (2 * math.pi)
                phase = (time.monotonic() % periode) / periode
                self._dessiner_orbe(1.0 + 0.07 * math.sin(2 * math.pi * phase))
                delai = PAS_ANIMATION_MS
        except Exception:
            pass
        finally:
            # Replanifié seulement si la fenêtre existe encore : après sa
            # fermeture, after() lèverait une TclError à chaque tour.
            try:
                existe = getattr(self.fenetre, "winfo_exists", None)
                if existe is None or existe():
                    self.fenetre.after(delai, self._animer_orbe)
            except Exception:
                pass

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

    # -- Défilement de la conversation (au mieux : l'API interne de
    # CTkScrollableFrame, `_parent_canvas`, peut changer d'une version à l'autre)

    def _canvas_conversation(self):
        return getattr(self.zone_conversation, "_parent_canvas", None)

    def _vue_conversation(self) -> tuple:
        """(début, fin) : fractions visibles de la conversation ; (0, 1) si
        illisible (tout est considéré visible)."""
        try:
            debut, fin = self._canvas_conversation().yview()
            return float(debut), float(fin)
        except Exception:
            return 0.0, 1.0

    def _est_en_bas(self) -> bool:
        return est_en_bas(*self._vue_conversation())

    def _position_avant_changement(self) -> bool:
        """Vrai si la vue est en bas. À lire AVANT de modifier la
        conversation. Pendant un redimensionnement ou un défilement en
        attente, la vue n'est pas fiable : on garde la dernière valeur."""
        if (self._apres_redimensionnement is not None
                or self._apres_defilement is not None):
            return self._dernier_bas
        self._dernier_bas = self._est_en_bas()
        return self._dernier_bas

    def _maj_zone_defilement(self) -> None:
        """Remet la zone de défilement (scrollregion) à la taille réelle du
        contenu, sans dépendre de la liaison interne de CTkScrollableFrame."""
        canvas = self._canvas_conversation()
        try:
            canvas.configure(scrollregion=canvas.bbox("all"))
        except Exception:
            pass

    def _planifier_defilement(self, bas: bool,
                              fraction: float | None = None) -> None:
        """Programme, APRÈS la mise en page de Tk, la mise à jour de la zone
        de défilement puis : le bas (`bas`), ou la position `fraction`, ou
        rien (l'utilisateur lit plus haut : on ne le fait pas redescendre).
        Plusieurs demandes dans le même passage n'en font qu'une."""
        if bas:
            self._defilement_bas_voulu = True
        elif fraction is not None and not self._defilement_bas_voulu:
            self._defilement_fraction = fraction
        if self._apres_defilement is None:
            # after_idle : après la mise en page de Tk (repli : after(1)).
            planifier = getattr(self.fenetre, "after_idle", None)
            self._apres_defilement = (
                planifier(self._executer_defilement) if planifier
                else self.fenetre.after(1, self._executer_defilement))

    def _executer_defilement(self) -> None:
        self._apres_defilement = None
        bas = self._defilement_bas_voulu
        fraction = self._defilement_fraction
        self._defilement_bas_voulu = False
        self._defilement_fraction = None
        try:
            # Termine la mise en page en attente : sans cela, le contenu
            # qu'on vient d'ajouter n'a pas encore sa taille (défilement en
            # retard d'un message).
            self.fenetre.update_idletasks()
        except Exception:
            pass
        self._maj_zone_defilement()
        canvas = self._canvas_conversation()
        try:
            if bas:
                canvas.yview_moveto(1.0)
            elif fraction is not None:
                canvas.yview_moveto(fraction)
        except Exception:
            pass
        if bas:
            self._dernier_bas = True
            # Second contrôle : une bulle qui change de hauteur après coup
            # (retour à la ligne) ne doit pas laisser la vue juste au-dessus.
            self._reprogrammer("_verif_defilement",
                               DELAI_VERIF_DEFILEMENT_MS,
                               self._verifier_defilement)

    def _verifier_defilement(self) -> None:
        self._verif_defilement = None
        self._maj_zone_defilement()
        debut, fin = self._vue_conversation()
        # Seulement si on était en bas et qu'il ne manque presque rien :
        # jamais contre un utilisateur qui a remonté la conversation.
        if (self._dernier_bas and not est_en_bas(debut, fin)
                and est_en_bas(debut, fin, tolerance=0.1)):
            try:
                self._canvas_conversation().yview_moveto(1.0)
            except Exception:
                pass

    def _defiler_bas(self) -> None:
        """Défile la conversation tout en bas, une fois la mise en page
        terminée (conservé pour compatibilité)."""
        self._planifier_defilement(True)

    def _reconstruire_conversation(self, entrees: list) -> None:
        """Efface et ré-affiche toute la conversation (après un
        raccourcissement du journal, ex. plafond de 200 lignes). La position
        est conservée : en bas on reste en bas, sinon on revient là où
        l'utilisateur lisait."""
        bas = self._position_avant_changement()
        debut = self._vue_conversation()[0]
        for enfant in self.zone_conversation.winfo_children():
            enfant.destroy()
        self._entrees_affichees = []
        self._etiquettes_bulles = []
        self._message_vide = None
        for entree in entrees:
            self._ajouter_message(entree)
        if not entrees:
            self._afficher_message_vide()
        self._planifier_defilement(bas, None if bas else debut)

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
        self._minuteurs_affiches = list(minuteurs)
        lignes = formater_minuteurs(minuteurs, ref, self.langue)
        jauges = (tuple(etat_jauge_minuteur(m, ref) for m in minuteurs)
                  if STYLE else ())
        # Jauges arrondies au 1/24 de tour : on ne redessine pas à chaque
        # seconde pour un changement invisible.
        cle = (lignes, tuple((round(f * 24), s) for f, s in jauges))
        if cle == self._texte_minuteurs:
            return
        self._texte_minuteurs = cle
        if (STYLE and minuteurs
                and len(self._tuiles_minuteurs) == len(minuteurs)):
            # Même nombre de minuteurs : texte et jauge mis à jour sur place
            # (le compte à rebours change chaque seconde ; rien n'est recréé).
            for (etiquette, jauge), ligne, etat in zip(
                    self._tuiles_minuteurs, lignes, jauges):
                self._remplir_tuile_minuteur(etiquette, jauge, ligne, *etat)
            return
        self._tuiles_minuteurs = []
        for enfant in self.conteneur_minuteurs.winfo_children():
            enfant.destroy()
        nouveaux = self._nouveaux("minuteurs",
                                  [m.get("id") for m in minuteurs])
        if STYLE and minuteurs:
            self._lignes_minuteurs_stylees(lignes, jauges)
            for index, (rangee, m) in enumerate(zip(
                    self.conteneur_minuteurs.winfo_children(), minuteurs)):
                if m.get("id") in nouveaux:
                    self._surligner(rangee, "border_color", COULEUR_ACCENT,
                                    STYLE["bordure_panneau"])
            return
        for index, ligne in enumerate(lignes):
            etiquette = ctk.CTkLabel(
                self.conteneur_minuteurs, text=ligne, font=_police(12),
                text_color=COULEUR_TEXTE, anchor="w",
                justify="left", **({"cursor": "hand2"} if minuteurs else {}))
            etiquette.pack(fill="x", padx=8, pady=2)
            if minuteurs:
                # Lot U3 : un clic ouvre pause / reprise / annulation.
                self._cliquable(etiquette, index)
                if minuteurs[index].get("id") in nouveaux:
                    self._surligner(etiquette, "text_color", COULEUR_ACCENT,
                                    COULEUR_TEXTE)

    def _lignes_minuteurs_stylees(self, lignes: tuple, jauges: tuple) -> None:
        """Thème stylé : une jauge circulaire par minuteur (temps restant,
        couleur de statut) devant son texte, sans la puce « • »."""
        for ligne, (fraction, statut) in zip(lignes, jauges):
            rangee = ctk.CTkFrame(self.conteneur_minuteurs, **options_tuile())
            rangee.pack(fill="x", padx=6, pady=2)
            jauge = tk.Canvas(rangee, width=TAILLE_JAUGE, height=TAILLE_JAUGE,
                              bg=COULEUR_FOND, highlightthickness=0, bd=0)
            jauge.pack(side="left", padx=(6, 6), pady=4)
            etiquette = ctk.CTkLabel(
                rangee, text="", font=_police(12), anchor="w",
                justify="left", height=24)
            etiquette.pack(side="left", fill="x", padx=(0, 8), pady=4)
            self._remplir_tuile_minuteur(etiquette, jauge, ligne, fraction,
                                         statut)
            index = len(self._tuiles_minuteurs)
            for widget in (rangee, jauge, etiquette):
                self._cliquable(widget, index)  # lot U3
            self._tuiles_minuteurs.append((etiquette, jauge))

    def _remplir_tuile_minuteur(self, etiquette, jauge, ligne: str,
                                fraction: float, statut: str) -> None:
        """Texte (rouge si échu) et jauge d'une tuile de minuteur."""
        etiquette.configure(
            text=ligne.removeprefix("• "),
            text_color=(couleur_statut("erreur", COULEUR_TEXTE)
                        if statut == "erreur" else COULEUR_TEXTE))
        jauge.delete("all")
        dessiner_jauge(jauge, TAILLE_JAUGE, fraction,
                       couleur_statut(statut, COULEUR_ACCENT),
                       STYLE.get("jauge_fond", COULEUR_FOND))

    # -- Recherches (lot R1) -------------------------------------------

    def _rafraichir_recherches(self, recherches: list) -> None:
        """Reconstruit le panneau Recherches seulement s'il a changé."""
        lignes = formater_recherches(recherches, self.langue)
        cle = (lignes, tuple((t.get("id"), t.get("statut"))
                             for t in recherches[:MAX_RECHERCHES_PANNEAU]))
        if cle == self._cle_recherches:
            return
        self._cle_recherches = cle
        for enfant in self.conteneur_recherches.winfo_children():
            enfant.destroy()
        if not recherches:
            ctk.CTkLabel(
                self.conteneur_recherches, text=lignes[0], font=_police(12),
                text_color=COULEUR_TEXTE_FAIBLE, anchor="w",
                justify="left").pack(fill="x", padx=8, pady=2)
            return
        nouveaux = self._nouveaux("recherches",
                                  [t.get("id") for t in recherches])
        for ligne, tache in zip(lignes, recherches):
            if not STYLE:
                # Lot U3 : point de statut coloré dans tous les thèmes.
                rangee = ctk.CTkFrame(self.conteneur_recherches,
                                      fg_color="transparent")
                rangee.pack(fill="x", padx=2, pady=1)
                ctk.CTkLabel(
                    rangee, text="●", font=_police(12), width=14, height=22,
                    text_color=couleur_etat(statut_recherche(tache))
                ).pack(side="left", padx=(6, 0))
                bouton = ctk.CTkButton(
                    rangee, text=ligne.removeprefix("• "), font=_police(12),
                    fg_color="transparent", hover_color=COULEUR_SURVOL_LISTE,
                    text_color=COULEUR_TEXTE, anchor="w", height=26,
                    command=lambda t=tache: self.ouvrir_recherche(t))
                bouton.pack(fill="x", padx=(0, 4), pady=1)
                if tache.get("id") in nouveaux:
                    self._surligner(bouton, "text_color", COULEUR_ACCENT,
                                    COULEUR_TEXTE)
                continue
            if STYLE:
                # Thème stylé : point de statut coloré, puis la ligne.
                rangee = ctk.CTkFrame(self.conteneur_recherches,
                                      **options_tuile())
                rangee.pack(fill="x", padx=6, pady=2)
                ctk.CTkLabel(
                    rangee, text="●", font=_police(12), width=14, height=22,
                    text_color=couleur_statut(statut_recherche(tache),
                                              COULEUR_TEXTE)
                ).pack(side="left", padx=(8, 0), pady=4)
                # Plus court qu'en classique : le point prend de la place.
                texte_ligne = (
                    recherche_mod.texte_parle(tache.get("question", ""), 30)
                    + " — " + recherche_mod.etiquette_statut(tache,
                                                             self.langue))
                parent, placement = rangee, {"padx": (0, 6), "pady": 4}
                if tache.get("id") in nouveaux:
                    self._surligner(rangee, "border_color", COULEUR_ACCENT,
                                    STYLE["bordure_panneau"])
            else:
                parent, texte_ligne = self.conteneur_recherches, ligne
                placement = {"padx": 4, "pady": 1}
            ctk.CTkButton(
                parent, text=texte_ligne, font=_police(12),
                fg_color="transparent", hover_color=COULEUR_SURVOL_LISTE,
                text_color=COULEUR_TEXTE, anchor="w",
                height=22 if STYLE else 26,
                command=lambda t=tache: self.ouvrir_recherche(t)
            ).pack(fill="x", **placement)

    def ouvrir_recherche(self, tache: dict) -> None:
        """Fenêtre de lecture d'une recherche : question, statut, réponse
        (synthèse rédigée par Jarvis) et sources (titres + URL)."""
        fenetre = ctk.CTkToplevel(self.fenetre)
        _fond_de_fenetre(fenetre)
        fenetre.title(self.t("recherche_fenetre"))
        fenetre.geometry("560x460")
        zone = ctk.CTkScrollableFrame(
            fenetre, fg_color=COULEUR_FOND, corner_radius=0,
            scrollbar_button_color=COULEUR_BARRE_DEFILEMENT)
        zone.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        statut = recherche_mod.etiquette_statut(tache, self.langue)
        ctk.CTkLabel(zone, text=str(tache.get("question", "")),
                     font=_police(15, True), text_color=COULEUR_TEXTE,
                     anchor="w", justify="left", wraplength=500
                     ).pack(fill="x", padx=6, pady=(4, 2))
        ctk.CTkLabel(zone, text=statut, font=_police(12),
                     text_color=COULEUR_TEXTE_FAIBLE, anchor="w"
                     ).pack(fill="x", padx=6, pady=(0, 8))
        if tache.get("statut") == "prete":
            corps = str(tache.get("reponse", ""))
        elif tache.get("statut") == "echec":
            corps = recherche_mod.raison(self.langue,
                                         str(tache.get("raison", "")))
        else:
            corps = self.t("recherche_attente").format(statut=statut)
        ctk.CTkLabel(zone, text=corps, font=_police(13),
                     text_color=COULEUR_TEXTE, anchor="w", justify="left",
                     wraplength=500).pack(fill="x", padx=6, pady=(0, 8))
        sources = [s for s in tache.get("sources", []) if isinstance(s, dict)]
        if sources:
            ctk.CTkLabel(zone, text=self.t("recherche_sources"),
                         font=_police(13, True), text_color=COULEUR_TEXTE,
                         anchor="w").pack(fill="x", padx=6, pady=(4, 2))
            for source in sources:
                ctk.CTkLabel(
                    zone, text=(
                        "• " + recherche_mod.texte_parle(source.get("titre"),
                                                         120)
                        + "\n  " + str(source.get("url", ""))[:300]),
                    font=_police(12), text_color=COULEUR_TEXTE_FAIBLE,
                    anchor="w", justify="left", wraplength=500
                ).pack(fill="x", padx=6, pady=2)
        ctk.CTkButton(
            fenetre, text=self.t("fermer"), font=_police(13),
            fg_color=COULEUR_ACCENT, hover_color=COULEUR_ACCENT_SURVOL,
            text_color=COULEUR_TEXTE_SUR_ACCENT, corner_radius=18, height=34,
            command=fenetre.destroy).pack(pady=(0, 10))

    # -- Tâches longues (lot LT) ---------------------------------------

    def _rafraichir_taches(self, taches: list) -> None:
        """Reconstruit le panneau Tâches longues seulement s'il a changé."""
        lignes = formater_taches(taches, self.langue)
        cle = (lignes, tuple((t.get("id"), statut_tache(t))
                             for t in taches[:MAX_TACHES_PANNEAU]))
        if cle == self._cle_taches:
            return
        self._cle_taches = cle
        for enfant in self.conteneur_taches.winfo_children():
            enfant.destroy()
        if not taches:
            ctk.CTkLabel(
                self.conteneur_taches, text=lignes[0], font=_police(12),
                text_color=COULEUR_TEXTE_FAIBLE, anchor="w",
                justify="left").pack(fill="x", padx=8, pady=2)
            return
        nouveaux = self._nouveaux("taches", [t.get("id") for t in taches])
        for ligne, tache in zip(lignes, taches):
            rangee = ctk.CTkFrame(self.conteneur_taches,
                                  **(options_tuile() if STYLE
                                     else {"fg_color": "transparent"}))
            rangee.pack(fill="x", padx=6 if STYLE else 2,
                        pady=2 if STYLE else 1)
            ctk.CTkLabel(
                rangee, text="●", font=_police(12), width=14, height=22,
                text_color=(couleur_statut(statut_tache(tache), COULEUR_TEXTE)
                            if STYLE else couleur_etat(statut_tache(tache)))
            ).pack(side="left", padx=(8 if STYLE else 6, 0),
                   pady=4 if STYLE else 0)
            bouton = ctk.CTkButton(
                rangee, text=ligne.removeprefix("• "), font=_police(12),
                fg_color="transparent", hover_color=COULEUR_SURVOL_LISTE,
                text_color=COULEUR_TEXTE, anchor="w",
                height=22 if STYLE else 26,
                command=lambda t=tache: self.ouvrir_tache(t))
            bouton.pack(fill="x", padx=(0, 6 if STYLE else 4),
                        pady=4 if STYLE else 1)
            if tache.get("id") in nouveaux:
                if STYLE:
                    self._surligner(rangee, "border_color", COULEUR_ACCENT,
                                    STYLE["bordure_panneau"])
                else:
                    self._surligner(bouton, "text_color", COULEUR_ACCENT,
                                    COULEUR_TEXTE)

    def ouvrir_tache(self, tache: dict) -> None:
        """Fenêtre de détail d'une tâche longue : titre, état, temps,
        objectif, plan coché, puis résultat (ou ce qui l'a arrêtée)."""
        fenetre = ctk.CTkToplevel(self.fenetre)
        _fond_de_fenetre(fenetre)
        fenetre.title(self.t("tache_fenetre"))
        fenetre.geometry("580x520")
        zone = ctk.CTkScrollableFrame(
            fenetre, fg_color=COULEUR_FOND, corner_radius=0,
            scrollbar_button_color=COULEUR_BARRE_DEFILEMENT)
        zone.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        def libelle(texte, taille=13, gras=False, faible=False, marge=(0, 6)):
            ctk.CTkLabel(zone, text=texte, font=_police(taille, gras),
                         text_color=(COULEUR_TEXTE_FAIBLE if faible
                                     else COULEUR_TEXTE),
                         anchor="w", justify="left", wraplength=520
                         ).pack(fill="x", padx=6, pady=marge)

        libelle(str(tache.get("titre") or tache.get("objectif", "")), 15,
                True, marge=(4, 2))
        budget = tache.get("budget") or {}
        libelle(f"{taches_mod.etiquette_etat(tache, self.langue)} · "
                f"{taches_mod.progression(tache)} · "
                + self.t("tache_budget").format(
                    duree=taches_mod.formater_duree(
                        tache.get("temps_utilise_s", 0), self.langue),
                    budget=taches_mod.formater_duree(
                        budget.get("duree_max_s", 0), self.langue)),
                12, faible=True, marge=(0, 8))
        libelle(self.t("tache_objectif"), 13, True, marge=(2, 2))
        libelle(str(tache.get("objectif", "")))
        plan = [e for e in tache.get("plan", []) if isinstance(e, dict)]
        if plan:
            libelle(self.t("tache_plan"), 13, True, marge=(2, 2))
            for n, etape in enumerate(plan, start=1):
                marque = "✓" if etape.get("etat") == "faite" else (
                    "→" if tache.get("etape_en_cours") == n - 1 else "·")
                libelle(f"{marque} {n}. "
                        + recherche_mod.texte_parle(etape.get("description"),
                                                    160), 12,
                        faible=etape.get("etat") != "faite", marge=(0, 1))
        if tache.get("etat") == "bloquee":
            libelle(self.t("tache_arret").format(
                raison=taches_mod.raison(self.langue, tache)), 13,
                marge=(8, 4))
        if tache.get("resultat"):
            libelle(self.t("tache_resultat"), 13, True, marge=(6, 2))
            libelle(recherche_mod.texte_parle(
                tache["resultat"], taches_mod.LONGUEUR_MAX_RESULTAT))
        elif tache.get("etat") == "en_cours":
            libelle(self.t("tache_attente").format(
                progression=taches_mod.progression(tache)), 13, marge=(8, 4))
        ctk.CTkButton(
            fenetre, text=self.t("fermer"), font=_police(13),
            fg_color=COULEUR_ACCENT, hover_color=COULEUR_ACCENT_SURVOL,
            text_color=COULEUR_TEXTE_SUR_ACCENT, corner_radius=18, height=34,
            command=fenetre.destroy).pack(pady=(0, 10))

    # -- Connaissances (lot KB) ----------------------------------------

    def _rafraichir_connaissances(self, notes: list) -> None:
        """Reconstruit le panneau Connaissances seulement s'il a changé."""
        lignes = formater_notes(notes, self.langue)
        cle = (lignes, len(notes), self._note_a_confirmer,
               tuple(n["id"] for n in notes[:MAX_NOTES_PANNEAU]))
        if cle == self._cle_connaissances:
            return
        self._cle_connaissances = cle
        for enfant in self.conteneur_connaissances.winfo_children():
            enfant.destroy()
        if not notes:
            ctk.CTkLabel(
                self.conteneur_connaissances, text=self.t("aucune_note"),
                font=_police(12), text_color=COULEUR_TEXTE_FAIBLE,
                anchor="w", justify="left", wraplength=180
            ).pack(fill="x", padx=8, pady=2)
            return
        nouveaux = self._nouveaux("notes", [n["id"] for n in notes])
        for (texte_note, date), note in zip(lignes, notes):
            ligne = ctk.CTkFrame(self.conteneur_connaissances,
                                 **options_tuile())
            ligne.pack(fill="x", padx=2, pady=2)
            ligne.grid_columnconfigure(0, weight=1)
            marge = (8, 2) if STYLE else (6, 2)  # hors du liseré de la tuile
            etiquette_note = ctk.CTkLabel(
                ligne, text=texte_note, font=_police(12),
                text_color=COULEUR_TEXTE, anchor="w", justify="left",
                wraplength=150, cursor="hand2")
            etiquette_note.grid(row=0, column=0, sticky="w", padx=marge,
                                pady=(4, 0) if STYLE else 0)
            # Lot U3 : un clic sur le texte ouvre la note entière.
            etiquette_note.bind(
                "<Button-1>", lambda _e, n=note: self.ouvrir_note(n), add="+")
            if note["id"] in nouveaux and self._note_a_confirmer is None:
                self._surligner(etiquette_note, "text_color", COULEUR_ACCENT,
                                COULEUR_TEXTE)
            ctk.CTkLabel(
                ligne, text=date, font=_police(10),
                text_color=STYLE.get("titre_panneau") or COULEUR_TEXTE_FAIBLE,
                anchor="w"
            ).grid(row=1, column=0, sticky="w", padx=marge,
                   pady=(0, 4) if STYLE else 0)
            arme = self._note_a_confirmer == note["id"]
            ctk.CTkButton(
                ligne, text=self.t("confirmer_suppression") if arme else "✕",
                font=_police(11, arme), width=72 if arme else 26, height=24,
                corner_radius=12, fg_color="transparent",
                hover_color=COULEUR_INTERROMPRE_SURVOL,
                text_color=(COULEUR_INTERROMPRE_TEXTE if arme
                            else COULEUR_TEXTE_FAIBLE),
                border_width=1 if arme else 0,
                border_color=COULEUR_INTERROMPRE_BORDURE,
                command=lambda i=note["id"]: self.supprimer_note(i)
            ).grid(row=0, column=1, rowspan=2, padx=(2, 4))
        if len(notes) > MAX_NOTES_PANNEAU:
            ctk.CTkLabel(
                self.conteneur_connaissances,
                text=self.t("notes_en_plus").format(
                    n=len(notes) - MAX_NOTES_PANNEAU),
                font=_police(10), text_color=COULEUR_TEXTE_FAIBLE,
                anchor="w", justify="left", wraplength=180
            ).pack(fill="x", padx=8, pady=2)

    def supprimer_note(self, ident: int) -> None:
        """Premier clic sur la croix : « Supprimer ? » pendant 4 s. Second
        clic sur la même note : suppression (data/connaissances.json, sous
        verrou). Jamais de suppression sur un seul clic."""
        if self._note_a_confirmer != ident:
            self._note_a_confirmer = ident
            self._reprogrammer("_apres_confirmation_note",
                               DELAI_CONFIRMATION_SUPPRESSION_MS,
                               self._annuler_confirmation_note)
        else:
            self._note_a_confirmer = None
            try:
                connaissances_mod.supprimer(FICHIER_CONNAISSANCES, ident)
            except OSError as erreur:
                print(f"Avertissement application : suppression de la note : "
                      f"{erreur}", file=sys.stderr)
        self._rafraichir_connaissances(charger_notes())

    def _annuler_confirmation_note(self) -> None:
        self._apres_confirmation_note = None
        if self._note_a_confirmer is not None:
            self._note_a_confirmer = None
            self._rafraichir_connaissances(charger_notes())

    def ouvrir_note(self, note: dict) -> None:
        """Fenêtre de lecture d'une note (texte entier + date). Lecture
        seule : la suppression reste la croix confirmée du panneau."""
        fenetre = ctk.CTkToplevel(self.fenetre)
        _fond_de_fenetre(fenetre)
        fenetre.title(self.t("note_fenetre"))
        fenetre.geometry("460x300")
        zone = ctk.CTkScrollableFrame(
            fenetre, fg_color=COULEUR_FOND, corner_radius=0,
            scrollbar_button_color=COULEUR_BARRE_DEFILEMENT)
        zone.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        ctk.CTkLabel(zone, text=connaissances_mod.formater_date(
            str(note.get("cree_le", "")), self.langue), font=_police(11),
            text_color=COULEUR_TEXTE_FAIBLE, anchor="w"
        ).pack(fill="x", padx=6, pady=(4, 2))
        ctk.CTkLabel(zone, text=str(note.get("texte", "")), font=_police(14),
                     text_color=COULEUR_TEXTE, anchor="w", justify="left",
                     wraplength=400).pack(fill="x", padx=6, pady=(0, 8))
        ctk.CTkButton(
            fenetre, text=self.t("fermer"), font=_police(13),
            fg_color=COULEUR_ACCENT, hover_color=COULEUR_ACCENT_SURVOL,
            text_color=COULEUR_TEXTE_SUR_ACCENT, corner_radius=18, height=34,
            command=fenetre.destroy).pack(pady=(0, 10))
        self._fenetre_note = fenetre

    # -- Lot U3 : actions des tuiles de minuteur ------------------------

    def _cliquable(self, widget, index: int) -> None:
        """Clic sur une tuile de minuteur : fenêtre d'actions (pause,
        reprise, annulation). L'index est relu au clic dans
        _minuteurs_affiches (la tuile peut être mise à jour sur place)."""
        try:
            widget.bind("<Button-1>",
                        lambda _e, i=index: self.ouvrir_actions_minuteur(i),
                        add="+")
        except Exception:
            pass

    def ouvrir_actions_minuteur(self, index: int) -> None:
        """Petite fenêtre : « Pause » ou « Reprendre » (comptes à rebours
        seulement), « Annuler » (second clic : « Confirmer ? »)."""
        if not 0 <= index < len(self._minuteurs_affiches):
            return
        minuteur = self._minuteurs_affiches[index]
        self._fermer_actions_minuteur()
        fenetre = ctk.CTkToplevel(self.fenetre)
        _fond_de_fenetre(fenetre)
        fenetre.title(self.t("minuteur_fenetre"))
        fenetre.geometry("360x160")
        self._fenetre_minuteur = fenetre
        self._annulation_armee = None
        ligne = formater_minuteurs([minuteur], datetime.now(FUSEAU),
                                   self.langue)[0].removeprefix("• ")
        ctk.CTkLabel(fenetre, text=ligne, font=_police(14, True),
                     text_color=COULEUR_TEXTE, wraplength=320,
                     justify="left").pack(fill="x", padx=16, pady=(16, 10))
        boutons = ctk.CTkFrame(fenetre, fg_color="transparent")
        boutons.pack(pady=(0, 12))
        ident = minuteur.get("id")
        self._boutons_minuteur: dict = {}
        if minuteur.get("kind") == "timer":
            en_pause = minuteur.get("pause_s") is not None
            action = "reprendre" if en_pause else "pause"
            bouton = ctk.CTkButton(
                boutons, text=self.t("minuteur_reprendre" if en_pause
                                     else "minuteur_pause_btn"),
                font=_police(13, True), fg_color=COULEUR_ACCENT,
                hover_color=COULEUR_ACCENT_SURVOL,
                text_color=COULEUR_TEXTE_SUR_ACCENT, corner_radius=16,
                height=32, width=120,
                command=lambda: self.action_minuteur(ident, action))
            bouton.pack(side="left", padx=6)
            self._boutons_minuteur[action] = bouton
        annuler = ctk.CTkButton(
            boutons, text=self.t("minuteur_annuler"), font=_police(13),
            fg_color="transparent", hover_color=COULEUR_INTERROMPRE_SURVOL,
            text_color=COULEUR_INTERROMPRE_TEXTE, border_width=1,
            border_color=COULEUR_INTERROMPRE_BORDURE, corner_radius=16,
            height=32, width=140,
            command=lambda: self.demander_annulation_minuteur(ident))
        annuler.pack(side="left", padx=6)
        self._boutons_minuteur["annuler"] = annuler

    def demander_annulation_minuteur(self, ident) -> bool:
        """Premier clic : « Confirmer ? » ; second clic : annulation. Jamais
        d'annulation sur un seul clic (comme la suppression d'une note)."""
        if self._annulation_armee != ident:
            self._annulation_armee = ident
            bouton = getattr(self, "_boutons_minuteur", {}).get("annuler")
            if bouton is not None:
                bouton.configure(text=self.t("minuteur_confirmer"))
            return False
        self._annulation_armee = None
        return self.action_minuteur(ident, "annuler")

    def action_minuteur(self, ident, action: str) -> bool:
        """Pause, reprise ou annulation du minuteur n° `ident` dans
        data/timers.json (minuteur.py, sous verrou — même fichier que le
        surveillant). Ferme la fenêtre d'actions et rafraîchit le panneau.
        Retourne False si rien n'a changé (minuteur échu ou disparu)."""
        import minuteur as minuteur_mod  # chargé au premier clic seulement.

        fonction = {"pause": minuteur_mod.mettre_en_pause,
                    "reprendre": minuteur_mod.reprendre,
                    "annuler": minuteur_mod.annuler_numero}.get(action)
        resultat = None
        if fonction is not None:
            try:
                resultat = fonction(FICHIER_MINUTEURS, int(ident))
            except (OSError, ValueError, TypeError) as erreur:
                print(f"Avertissement application : minuteur : {erreur}",
                      file=sys.stderr)
        self._fermer_actions_minuteur()
        self._texte_minuteurs = ()
        self._rafraichir_minuteurs(charger_minuteurs(), datetime.now(FUSEAU))
        return resultat is not None

    def _fermer_actions_minuteur(self) -> None:
        fenetre, self._fenetre_minuteur = self._fenetre_minuteur, None
        if fenetre is not None:
            try:
                fenetre.destroy()
            except Exception:
                pass

    # -- Lot U5 : surlignage des nouveaux éléments ----------------------

    def _nouveaux(self, panneau: str, identifiants: list) -> set:
        """Identifiants apparus depuis le dernier affichage du panneau (vide
        au premier affichage : rien ne clignote au lancement)."""
        vus = self._ids_vus.get(panneau)
        actuels = {i for i in identifiants if i is not None}
        self._ids_vus[panneau] = actuels
        return set() if vus is None else actuels - vus

    def _surligner(self, widget, option: str, depart: str,
                   arrivee: str) -> None:
        """Fondu de couleur d'un nouvel élément (de l'accent vers sa couleur
        normale). Animations coupées : couleur finale tout de suite."""
        self._animateur.lancer(
            ("surligne", id(widget)), DUREE_SURLIGNAGE_MS,
            lambda t: widget.configure(**{option: _fondre(depart, arrivee,
                                                          1.0 - t)}))

    # -- Lot DB : moniteur système, agents, conversations ---------------

    def _mesurer_systeme(self) -> None:
        """Une mesure (psutil, non bloquante) puis la suivante dans 5 s."""
        try:
            self._afficher_systeme(mesurer_systeme())
        except Exception as erreur:
            print(f"Avertissement application : moniteur : {erreur}",
                  file=sys.stderr)
        finally:
            try:
                existe = getattr(self.fenetre, "winfo_exists", None)
                if existe is None or existe():
                    self.fenetre.after(INTERVALLE_SYSTEME_MS,
                                       self._mesurer_systeme)
            except Exception:
                pass

    def _afficher_systeme(self, mesures: dict | None) -> None:
        """Jauges CPU / RAM / disque ; redessinées seulement si un
        pourcentage arrondi change. psutil absent : « — »."""
        self._mesures_systeme = mesures
        valeurs = mesures or {}
        cle = tuple(None if valeurs.get(k) is None else round(valeurs[k])
                    for k in ("cpu", "ram", "disque"))
        if cle == self._cle_systeme:
            return
        self._cle_systeme = cle
        piste = STYLE.get("jauge_fond") or _fondre(
            COULEUR_TEXTE_FAIBLE, COULEUR_PANNEAU, 0.35)
        for nom, pourcent in zip(("cpu", "ram", "disque"), cle):
            canevas, valeur, _etiquette = self._jauges_systeme[nom]
            canevas.delete("all")
            dessiner_jauge(canevas, TAILLE_JAUGE_SYSTEME,
                           (pourcent or 0) / 100.0,
                           couleur_etat(statut_charge(pourcent)), piste, 4)
            valeur.configure(text=(self.t("systeme_indispo") if pourcent
                                   is None else f"{pourcent} %"))

    def _rafraichir_agents(self, etats: dict) -> None:
        """Point coloré + état de chaque capacité, mis à jour sur place."""
        cle = tuple(etats.get(a, "veille") for a in AGENTS)
        if cle == self._cle_agents:
            return
        self._cle_agents = cle
        for agent, statut in zip(AGENTS, cle):
            point, _nom, texte = self._lignes_agents[agent]
            couleur = couleur_etat(STATUT_DES_AGENTS.get(statut, "inactif"))
            point.configure(text_color=couleur)
            texte.configure(text=self.t(f"statut_{statut}"),
                            text_color=(couleur if statut != "veille"
                                        else COULEUR_TEXTE_FAIBLE))

    def _langue_tableau_de_bord(self) -> None:
        for agent, (_point, nom, _texte) in self._lignes_agents.items():
            nom.configure(text=self.t(f"agent_{agent}"))
        for cle, (_canevas, _valeur, nom) in self._jauges_systeme.items():
            nom.configure(text=self._titre(f"systeme_{cle}"))
        self._jours_lus_a = float("-inf")

    def _rafraichir_conversations(self, jours: list) -> None:
        """Liste des jours (du plus récent), un clic relit le jour dans la
        fenêtre Historique."""
        lignes = formater_jours(jours, self.langue)
        cle = (lignes, self.langue)
        if cle == self._cle_jours:
            return
        self._cle_jours = cle
        self._jours_affiches = list(jours[:MAX_JOURS_PANNEAU])
        for enfant in self.conteneur_conversations.winfo_children():
            enfant.destroy()
        if not jours:
            ctk.CTkLabel(
                self.conteneur_conversations,
                text=self.t("aucune_conversation"), font=_police(12),
                text_color=COULEUR_TEXTE_FAIBLE, anchor="w", justify="left",
                wraplength=170).pack(fill="x", padx=8, pady=2)
            return
        for (libelle, detail), jour in zip(lignes, jours):
            ctk.CTkButton(
                self.conteneur_conversations, text=f"{libelle}\n{detail}",
                font=_police(12), fg_color="transparent",
                hover_color=COULEUR_SURVOL_LISTE, text_color=COULEUR_TEXTE,
                anchor="w", height=36,
                command=lambda j=jour: self.ouvrir_jour(j)
            ).pack(fill="x", padx=4, pady=2)

    def ouvrir_jour(self, jour: dict) -> None:
        """Ouvre l'Historique sur ce jour (lecture seule)."""
        self.ouvrir_historique()
        try:
            self._choisir_jour_historique(jour)
        except Exception as erreur:
            print(f"Avertissement application : historique : {erreur}",
                  file=sys.stderr)

    def _maj_tableau_de_bord(self) -> None:
        """Affiche la colonne Agents + Conversations si elle est voulue :
        choix du menu Affichage, sinon [app] tableau_de_bord et fenêtre
        d'au moins LARGEUR_TABLEAU_BORD px."""
        if self._tableau_force is not None:
            voulu = self._tableau_force
        else:
            try:
                largeur = int(self.fenetre.winfo_width())
            except Exception:
                largeur = 0
            voulu = (bool(self.config.get("tableau_de_bord", True))
                     and largeur >= LARGEUR_TABLEAU_BORD)
        if voulu == self._tableau_visible:
            return
        self._tableau_visible = voulu
        if voulu:
            self.colonne_bord.grid(row=0, column=2, rowspan=4, sticky="nsew")
        else:
            self.colonne_bord.grid_remove()

    def basculer_tableau_de_bord(self) -> None:
        """Menu Affichage : afficher / masquer la colonne (pour la session)."""
        self._tableau_force = not self._tableau_visible
        self._maj_tableau_de_bord()

    # -- Mode privé (lot PR) -------------------------------------------

    def basculer_mode_prive(self) -> None:
        """Menu Affichage : demande à la boucle d'entrer en mode privé ou
        d'en sortir. L'affichage suit l'état que la boucle signale
        (data/hud-state.json), pas la demande : la pastille n'apparaît que
        quand la boucle est vraiment en mode privé."""
        ecrire_demande_prive(FICHIER_DEMANDE_PRIVE, not self.prive,
                             self.langue)

    def _maj_mode_prive_affiche(self) -> None:
        """Pastille « Privé » et libellé du menu selon self.prive."""
        self.libelle_menu_prive = self.t(
            "menu_prive_quitter" if self.prive else "menu_prive_activer")
        try:
            self._menu_affichage.entryconfigure(
                1, label=self.libelle_menu_prive)
        except Exception:
            pass
        self.pastille_prive.configure(text=self.t("pastille_prive"))
        if self.prive:
            self.pastille_prive.grid()
        else:
            self.pastille_prive.grid_remove()

    # -- Micro : push-to-talk et interruption --------------------------

    def _style_micro(self, enfonce: bool) -> None:
        """Bouton micro bien visible quand il est maintenu : couleur de
        l'état « écoute » (celle de l'orbe) + liseré clair."""
        if enfonce:
            couleur = ETATS["ecoute"][1]
            self.bouton_micro.configure(
                text=titre_affiche(self.t("micro_actif")), fg_color=couleur,
                hover_color=couleur, border_width=2,
                border_color=COULEUR_TEXTE)
            if STYLE:
                self.bouton_micro.configure(text_color=COULEUR_TEXTE_SUR_ACCENT)
        elif STYLE:
            # Thème stylé : pilule sombre, contour et texte cyan.
            self.bouton_micro.configure(
                text=titre_affiche(self.t("micro_repos")),
                fg_color=STYLE.get("micro_fond", COULEUR_PANNEAU),
                hover_color=COULEUR_SURVOL_LISTE, border_width=2,
                border_color=COULEUR_ACCENT, text_color=COULEUR_ACCENT)
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
        _fond_de_fenetre(fenetre)
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
            font=ctk.CTkFont(family="Segoe UI", size=13), height=36,
            **OPTIONS_CHAMP)
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
                fg_color="transparent", hover_color=COULEUR_SURVOL_LISTE,
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
            text_color=COULEUR_TEXTE_SUR_ACCENT, corner_radius=20, height=36,
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
        de fichier pendant qu'on tire sur le bord de la fenêtre).

        Garde aussi la zone de défilement à jour, et mémorise si la vue
        était en bas avant que le retour à la ligne ne change la hauteur."""
        if (self._apres_redimensionnement is None
                and self._apres_defilement is None):
            self._dernier_bas = self._est_en_bas()
        self._maj_zone_defilement()
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
        bas = self._dernier_bas  # vue avant le changement de retour à la ligne
        try:
            largeur = self._largeur_bulle()  # d'après winfo_width()
            if largeur != self._derniere_largeur:
                self._derniere_largeur = largeur
                for etiquette in self._etiquettes_bulles:
                    etiquette.configure(wraplength=largeur)
                # Les bulles changent de hauteur : zone de défilement à
                # recalculer, et on reste en bas si on y était.
                self._planifier_defilement(bas)
            # Le détail d'état passe à la ligne avant le moniteur.
            self.texte_detail.configure(wraplength=max(
                200, self.fenetre.winfo_width() - 340 - LARGEUR_MONITEUR))
            self._maj_tableau_de_bord()
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
            recherches = charger_recherches()
            taches = charger_taches()
            notes = charger_notes()
            entrees = lire_conversation()
            prive = bool(etat.get("prive"))
            if prive != self.prive:
                self.prive = prive
                self._maj_mode_prive_affiche()

            # État + détail.
            etat_affiche = etat["etat"]
            texte_etat = self.t(f"etat_{etat_affiche}")
            if etat_affiche == "arrete":
                detail = self.t("detail_arrete")
            elif etat_affiche == "erreur" and etat["erreur"]:
                detail = (self.t("detail_erreur_prefixe")
                          + etat["erreur"][:110]
                          + ("…" if len(etat["erreur"]) > 110 else ""))
            elif self.prive and etat_affiche == "repos":
                detail = self.t("detail_prive")
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
                self._maj_pastille()
                # Lot U5 : petite éclosion de l'orbe quand il s'arrête sur
                # un état immobile (repos, erreur, arrêt) ; les états actifs
                # pulsent déjà. Rien si les animations sont coupées.
                if ETATS[etat_affiche][2] == 0:
                    self._animateur.lancer(
                        "orbe", DUREE_ECLOSION_MS,
                        lambda t: self._dessiner_orbe(courbe_eclosion(t)))

            # Horloge (redessinée seulement quand la seconde change).
            horloge = maintenant.strftime("%H:%M:%S")
            if horloge != self._horloge_affichee:
                self._horloge_affichee = horloge
                self.texte_horloge.configure(text=horloge)

            # Minuteurs.
            self._rafraichir_minuteurs(minuteurs, maintenant)
            self._rafraichir_recherches(recherches)
            self._rafraichir_taches(taches)
            self._rafraichir_connaissances(notes)
            # Lot DB : agents (à chaque passage, mis à jour sur place) et
            # liste des jours (relue quand le journal du jour grandit, au
            # plus toutes les 5 min sinon).
            self._rafraichir_agents(etats_agents(
                etat, minuteurs, recherches, notes_lisibles(), taches))
            if (len(entrees) != self._compte_du_jour
                    or time.monotonic() - self._jours_lus_a
                    > INTERVALLE_JOURS_S):
                self._compte_du_jour = len(entrees)
                self._jours_lus_a = time.monotonic()
                self._rafraichir_conversations(lister_jours(self.racine))

            # Conversation : ajouts, ou reconstruction si le journal a
            # raccourci (changement de jour : nouveau fichier).
            # La position de la vue est lue AVANT toute modification : en
            # bas on suit le nouveau message, sinon on ne bouge pas.
            affichees = self._entrees_affichees
            bas = self._position_avant_changement()
            if (len(entrees) < len(affichees)
                    or entrees[:len(affichees)] != affichees):
                self._reconstruire_conversation(entrees)
            elif len(entrees) > len(affichees):
                for entree in entrees[len(affichees):]:
                    self._ajouter_message(entree)
                self._planifier_defilement(bas)
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
    print(f"  [INFO]   thème : {nom_theme(config.get('theme'))} "
          "([app] theme ; repli : jarvis_bleu)")
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
