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
    horodatage, alimentée par le journal data/conversation.jsonl écrit par
    la boucle vocale (scripts/boucle_voix.py, étape 7).
  - Panneau minuteurs : liste lue dans data/timers.json (lecture seule),
    avec comptes à rebours.
  - Bouton micro à maintenir enfoncé = push-to-talk (même mécanisme que
    le HUD : data/hud-ptt.json) ; bouton « Interrompre » pour couper la
    réponse en cours (comme F9 pendant une réponse).
  - Menu : Ouvrir le guide, Quitter. Position et taille de la fenêtre
    mémorisées dans data/app.json.

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

# Fuseau horaire de Julien (config/config.example.toml).
FUSEAU = ZoneInfo("America/Toronto")

RACINE = Path(__file__).resolve().parent.parent
FICHIER_ETAT = RACINE / "data" / "hud-state.json"
FICHIER_PTT = RACINE / "data" / "hud-ptt.json"
FICHIER_MINUTEURS = RACINE / "data" / "timers.json"
FICHIER_CONVERSATION = RACINE / "data" / "conversation.jsonl"
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


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def charger_config_app(racine: Path) -> dict:
    """Lit config.toml [app], sinon config.example.toml, sinon défauts."""
    config = dict(DEFAUTS)
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
              "present": False}
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaut
    if not isinstance(donnees, dict):
        return defaut
    etat = str(donnees.get("etat", "repos"))
    if etat not in ETATS_CONNUS:
        etat = "repos"
    return {
        "etat": etat,
        "transcription": str(donnees.get("transcription", "")),
        "erreur": str(donnees.get("erreur", "")),
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


def formater_compte_a_rebours(secondes: float) -> str:
    """« 45 s », « 12 min », « 1 h 05 », « échue »."""
    if secondes < 0:
        return "échue"
    if secondes < 60:
        return f"{int(secondes)} s"
    if secondes < 3600:
        return f"{int(secondes // 60)} min"
    heures = int(secondes // 3600)
    minutes = int((secondes % 3600) // 60)
    return f"{heures} h {minutes:02d}"


def formater_minuteurs(minuteurs: list, ref: datetime) -> tuple:
    """Lignes « <étiquette> : dans 12 min » pour le panneau minuteurs."""
    lignes = []
    for minuteur in minuteurs:
        reste = (minuteur["due"] - ref).total_seconds()
        quoi = minuteur["label"] or minuteur["kind"]
        if reste < 0:
            lignes.append(f"• {quoi} : échue")
        else:
            lignes.append(
                f"• {quoi} : dans {formater_compte_a_rebours(reste)}")
    return tuple(lignes) if lignes else ("Aucun minuteur en cours.",)


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


def lire_conversation(chemin: Path = FICHIER_CONVERSATION) -> list:
    """Lit data/conversation.jsonl ; liste de {"role", "texte", "heure"}.

    Lignes mal formées ignorées. Fichier absent : liste vide.
    """
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
    """Fenêtre Jarvis : orbe d'état, conversation, minuteurs, micro.

    Bouton micro maintenu = push-to-talk (équivalent F9). Bouton
    « Interrompre » = impulsion courte sur data/hud-ptt.json, qui coupe
    la réponse en cours (comme F9 pendant une réponse).
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
        self.fenetre.minsize(640, 480)
        if config.get("toujours_au_premier_plan", False):
            self.fenetre.attributes("-topmost", True)
        self.fenetre.protocol("WM_DELETE_WINDOW", self.quitter)

        self.etat_affiche = "arrete"
        self._entrees_affichees: list = []
        self._texte_minuteurs: tuple = ()
        self._micro_enfonce = False
        self._etiquettes_bulles: list = []
        self._apres_redimensionnement = None
        self._message_vide = None

        # -- Menu ------------------------------------------------------
        barre_menu = tk.Menu(self.fenetre)
        menu_fichier = tk.Menu(barre_menu, tearoff=0)
        menu_fichier.add_command(label="Ouvrir le guide",
                                 command=self.ouvrir_guide)
        menu_fichier.add_separator()
        menu_fichier.add_command(label="Quitter", command=self.quitter)
        barre_menu.add_cascade(label="Fichier", menu=menu_fichier)
        self.fenetre.config(menu=barre_menu)

        # -- Grille principale -----------------------------------------
        self.fenetre.grid_rowconfigure(1, weight=1)
        self.fenetre.grid_columnconfigure(0, weight=1)

        # -- En-tête : orbe + état + horloge ---------------------------
        self.entete = ctk.CTkFrame(
            self.fenetre, fg_color=COULEUR_PANNEAU, corner_radius=0)
        self.entete.grid(row=0, column=0, sticky="ew")
        self.entete.grid_columnconfigure(1, weight=1)

        self.canvas_orbe = tk.Canvas(
            self.entete, width=76, height=76, bg=COULEUR_PANNEAU,
            highlightthickness=0, bd=0)
        self.canvas_orbe.grid(row=0, column=0, rowspan=2,
                              padx=(14, 4), pady=10)
        self._orbe_halo = self.canvas_orbe.create_oval(4, 4, 72, 72, fill="",
                                                        outline="")
        self._orbe_milieu = self.canvas_orbe.create_oval(12, 12, 64, 64,
                                                         fill="", outline="")
        self._orbe_coeur = self.canvas_orbe.create_oval(20, 20, 56, 56,
                                                        fill="", outline="")

        self.texte_etat = ctk.CTkLabel(
            self.entete, text="Jarvis prêt",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=COULEUR_TEXTE, anchor="w")
        self.texte_etat.grid(row=0, column=1, sticky="w", padx=6, pady=(12, 0))
        self.texte_detail = ctk.CTkLabel(
            self.entete, text="Boucle vocale arrêtée",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COULEUR_TEXTE_FAIBLE, anchor="w")
        self.texte_detail.grid(row=1, column=1, sticky="w", padx=6,
                               pady=(0, 12))

        self.texte_horloge = ctk.CTkLabel(
            self.entete, text="--:--:--",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=COULEUR_TEXTE)
        self.texte_horloge.grid(row=0, column=2, rowspan=2, padx=16, pady=10)

        # -- Zone centrale : conversation + minuteurs -------------------
        self.centre = ctk.CTkFrame(self.fenetre, fg_color=COULEUR_FOND,
                                   corner_radius=0)
        self.centre.grid(row=1, column=0, sticky="nsew")
        self.centre.grid_rowconfigure(0, weight=1)
        self.centre.grid_columnconfigure(0, weight=1)

        self.zone_conversation = ctk.CTkScrollableFrame(
            self.centre, fg_color=COULEUR_FOND, corner_radius=0,
            scrollbar_button_color=COULEUR_BARRE_DEFILEMENT)
        self.zone_conversation.grid(row=0, column=0, sticky="nsew",
                                    padx=(8, 0), pady=8)
        self.zone_conversation.bind(
            "<Configure>", self._sur_redimensionnement)

        self.panneau_minuteurs = ctk.CTkFrame(
            self.centre, fg_color=COULEUR_PANNEAU, corner_radius=12)
        self.panneau_minuteurs.grid(row=0, column=1, sticky="ns",
                                    padx=8, pady=8)
        self.panneau_minuteurs.configure(width=230)
        titre_minuteurs = ctk.CTkLabel(
            self.panneau_minuteurs, text="Minuteurs",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=COULEUR_TEXTE, anchor="w")
        titre_minuteurs.pack(fill="x", padx=12, pady=(10, 2))
        self.conteneur_minuteurs = ctk.CTkFrame(
            self.panneau_minuteurs, fg_color="transparent")
        self.conteneur_minuteurs.pack(fill="x", padx=4, pady=(0, 10))

        # -- Barre du bas : micro + interruption ------------------------
        self.barre_bas = ctk.CTkFrame(
            self.fenetre, fg_color=COULEUR_PANNEAU, corner_radius=0)
        self.barre_bas.grid(row=2, column=0, sticky="ew")
        self.barre_bas.grid_columnconfigure(0, weight=1)

        self.bouton_micro = ctk.CTkButton(
            self.barre_bas, text="Maintenir pour parler",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            fg_color=COULEUR_ACCENT, hover_color=COULEUR_ACCENT_SURVOL,
            text_color="#ffffff", corner_radius=24, height=48)
        self.bouton_micro.grid(row=0, column=0, sticky="ew",
                               padx=(14, 6), pady=12)
        self.bouton_micro.bind("<ButtonPress-1>", self._micro_presse)
        self.bouton_micro.bind("<ButtonRelease-1>", self._micro_relache)

        self.bouton_interrompre = ctk.CTkButton(
            self.barre_bas, text="Interrompre",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color="transparent", hover_color="#2a1a1a",
            text_color="#e07878", border_width=1,
            border_color="#7a3a3a", corner_radius=24, height=48,
            command=self.interrompre)
        self.bouton_interrompre.grid(row=0, column=1, padx=(6, 14), pady=12)

        self.texte_astuce = ctk.CTkLabel(
            self.barre_bas, text="ou maintenez F9",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COULEUR_TEXTE_FAIBLE)
        self.texte_astuce.grid(row=1, column=0, columnspan=2, pady=(0, 8))

        self._dessiner_orbe(1.0)
        self.rafraichir()
        self._animer_orbe()

    # -- Orbe ----------------------------------------------------------

    def _dessiner_orbe(self, echelle: float) -> None:
        """Redessine l'orbe (halo + milieu + cœur) à l'échelle donnée."""
        couleur = ETATS[self.etat_affiche][1]
        centre = 38
        for item, rayon, facteur in (
                (self._orbe_halo, 34, 0.30),
                (self._orbe_milieu, 26, 0.60),
                (self._orbe_coeur, 18, 1.0)):
            r = rayon * echelle
            self.canvas_orbe.coords(
                item, centre - r, centre - r, centre + r, centre + r)
            self.canvas_orbe.itemconfig(
                item, fill=_assombrir(couleur, facteur), outline="")

    def _animer_orbe(self) -> None:
        """Pulsation de l'orbe selon l'état (comme le frontend de
        référence : écoute 1,5 s, réflexion 0,8 s, réponse 0,6 s)."""
        try:
            periode = ETATS[self.etat_affiche][2]
            if periode > 0:
                phase = (time.monotonic() % periode) / periode
                echelle = 1.0 + 0.07 * math.sin(2 * math.pi * phase)
            else:
                echelle = 1.0
            self._dessiner_orbe(echelle)
        except Exception:
            pass
        finally:
            self.fenetre.after(90, self._animer_orbe)

    # -- Conversation --------------------------------------------------

    def _ajouter_message(self, entree: dict) -> None:
        """Ajoute une bulle (utilisateur à droite, Jarvis à gauche)."""
        if self._message_vide is not None:
            self._message_vide.destroy()
            self._message_vide = None
        role = entree["role"]
        if role == "user":
            couleur_bulle = COULEUR_BULLE_UTILISATEUR
            ancre = "e"
            marges = (70, 6)
        else:
            couleur_bulle = COULEUR_BULLE_JARVIS
            ancre = "w"
            marges = (6, 70)
        cadre = ctk.CTkFrame(
            self.zone_conversation, fg_color=couleur_bulle,
            corner_radius=12)
        cadre.pack(anchor=ancre, padx=marges, pady=4)
        etiquette = ctk.CTkLabel(
            cadre, text=entree["texte"],
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COULEUR_TEXTE, wraplength=self._largeur_bulle(),
            justify="left", anchor="w")
        etiquette.pack(fill="x", padx=12, pady=(8, 0))
        self._etiquettes_bulles.append(etiquette)
        heure = formater_heure(entree["heure"])
        if heure:
            ctk.CTkLabel(
                cadre, text=heure,
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=COULEUR_TEXTE_FAIBLE, anchor="e").pack(
                    fill="x", padx=12, pady=(2, 6))
        self._entrees_affichees.append(entree)

    def _largeur_bulle(self) -> int:
        """Largeur de retour à la ligne des bulles, selon la fenêtre."""
        try:
            largeur = self.zone_conversation.winfo_width()
        except Exception:
            largeur = 600
        return max(240, largeur - 130)

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
            self.zone_conversation,
            text="Aucune conversation pour l'instant.\n"
                 "Maintenez F9 (ou le bouton micro) pour parler à Jarvis.",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COULEUR_TEXTE_FAIBLE, justify="center")
        self._message_vide.pack(pady=40)

    # -- Minuteurs -----------------------------------------------------

    def _rafraichir_minuteurs(self, minuteurs: list, ref: datetime) -> None:
        """Reconstruit le panneau minuteurs seulement si le texte change."""
        lignes = formater_minuteurs(minuteurs, ref)
        if lignes == self._texte_minuteurs:
            return
        self._texte_minuteurs = lignes
        for enfant in self.conteneur_minuteurs.winfo_children():
            enfant.destroy()
        for ligne in lignes:
            ctk.CTkLabel(
                self.conteneur_minuteurs, text=ligne,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=COULEUR_TEXTE, anchor="w",
                justify="left").pack(fill="x", padx=8, pady=2)

    # -- Micro : push-to-talk et interruption --------------------------

    def _micro_presse(self, _evenement=None) -> None:
        self._micro_enfonce = True
        ecrire_ptt(FICHIER_PTT, True)
        self.bouton_micro.configure(text="Écoute en cours…")

    def _micro_relache(self, _evenement=None) -> None:
        self._micro_enfonce = False
        ecrire_ptt(FICHIER_PTT, False)
        self.bouton_micro.configure(text="Maintenir pour parler")

    def interrompre(self) -> None:
        """Impulsion courte sur data/hud-ptt.json : coupe la réponse en
        cours (la boucle ne réagit qu'au front montant, comme F9)."""
        ecrire_ptt(FICHIER_PTT, True)
        self.fenetre.after(400, lambda: ecrire_ptt(FICHIER_PTT, False))

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

    def _sur_redimensionnement(self, _evenement=None) -> None:
        """Mémorise la géométrie et ajuste le retour à la ligne des
        bulles (avec un petit délai, pour ne pas le faire à chaque pixel).
        """
        if self._apres_redimensionnement is not None:
            try:
                self.fenetre.after_cancel(self._apres_redimensionnement)
            except Exception:
                pass
        self._apres_redimensionnement = self.fenetre.after(
            200, self._apres_redimensionnement_fait)

    def _apres_redimensionnement_fait(self) -> None:
        self._apres_redimensionnement = None
        try:
            if self.fenetre.state() == "normal":
                sauvegarder_geometrie(
                    self.racine, self.fenetre.geometry())
        except Exception:
            pass
        try:
            largeur = self._largeur_bulle()
            for etiquette in self._etiquettes_bulles:
                etiquette.configure(wraplength=largeur)
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
            minuteurs = charger_minuteurs()
            entrees = lire_conversation()

            # État + détail.
            etat_affiche = etat["etat"]
            texte_etat, _couleur, _periode = ETATS[etat_affiche]
            if etat_affiche == "arrete":
                detail = ("Boucle vocale arrêtée — lancez "
                          "python scripts\\boucle_voix.py")
            elif etat_affiche == "erreur" and etat["erreur"]:
                detail = f"Erreur : {etat['erreur']}"
            elif etat["transcription"]:
                detail = (etat["transcription"][:90]
                          + ("…" if len(etat["transcription"]) > 90 else ""))
            else:
                detail = "Maintenez F9 ou le bouton micro pour parler."
            if (etat_affiche != self.etat_affiche
                    or self.texte_etat.cget("text") != texte_etat
                    or self.texte_detail.cget("text") != detail):
                self.etat_affiche = etat_affiche
                self.texte_etat.configure(text=texte_etat)
                self.texte_detail.configure(text=detail)
                self._dessiner_orbe(1.0)

            # Horloge.
            self.texte_horloge.configure(
                text=maintenant.strftime("%H:%M:%S"))

            # Minuteurs.
            self._rafraichir_minuteurs(minuteurs, maintenant)

            # Conversation : ajouts, ou reconstruction si le journal a
            # raccourci (plafond de 200 lignes atteint).
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
    if not FICHIER_CONVERSATION.exists():
        print("  [INFO]   data/conversation.jsonl absent — il sera créé "
              "par la boucle vocale au premier tour.")
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
