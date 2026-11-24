#!/usr/bin/env python3
"""hud.py — HUD local léger du Jarvis-Muse (étape 6).

Fenêtre Tkinter discrète (bibliothèque standard, pas de navigateur
embarqué) : anneau d'état, heure + compte à rebours du prochain minuteur,
panneau déplié au survol (dernière transcription + 2 prochains minuteurs).
Maintenir le clic sur l'anneau = équivalent F9 (push-to-talk).

Communication avec la boucle vocale (scripts/boucle_voix.py) par fichiers
locaux, sans aucun port réseau :
  - data/hud-state.json : état écrit par la boucle à chaque changement
    (repos / ecoute / reflexion / reponse / erreur).
  - data/hud-ptt.json : demande push-to-talk écrite par le HUD (clic
    maintenu) et lue par la boucle.
  - data/timers.json : minuteurs persistants (lecture seule).

Usage :
    python scripts/hud.py
    python scripts/hud.py --verifier

Cibles (docs/etape-6-preparation.md) : < 100 Mo en veille, ~0 % CPU en
veille, démarrage < 1 s. Le HUD ne montre que l'état local — pas de
météo, calendrier, Gmail ou repas (doublons Carson, bloc 6).

Sécurité (docs/regles-securite.md) : aucun serveur local, aucune donnée
sensible affichée (pas de capture d'écran, pas de texte de page, pas de
courriel) ; les fichiers data/ sont gitignorés.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
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
FICHIER_POSITION = RACINE / "data" / "widget.json"
GUIDE = RACINE / "docs" / "etape-6-hud-session.md"

try:
    import tkinter as tk

    TKINTER_DISPONIBLE = True
except ImportError:  # pragma: no cover - environnement sans Tkinter.
    tk = None
    TKINTER_DISPONIBLE = False

# Valeurs par défaut (surchargées par config.toml [hud]).
DEFAUTS = {
    "active": True,
    "position": "bas-droite",  # bas-droite | bas-gauche | haut-droite | haut-gauche
    "taille": 180,
    "toujours_au_premier_plan": True,
    "intervalle_ms": 500,
}

COULEURS = {
    "repos": "#5b7a99",       # gris-bleu calme
    "ecoute": "#3fae5a",      # vert — enregistrement en cours
    "reflexion": "#e8a13a",   # ambre — appel au cerveau
    "reponse": "#3a7bd5",     # bleu — réponse lue à voix haute
    "erreur": "#c0392b",      # rouge discret
    "minuteur_echu": "#e8a13a",
}
COULEUR_FOND = "#20242a"
COULEUR_TEXTE = "#e8e8e8"
COULEUR_TEXTE_FAIBLE = "#9aa3ad"

ETATS_CONNUS = ("repos", "ecoute", "reflexion", "reponse", "erreur")
DUREE_FLASH_MINUTEUR = 5.0  # secondes d'anneau clignotant après échéance.
FRAICHEUR_PTT = 2.0  # secondes : un fichier PTT plus vieux est périmé.


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def charger_config_hud(racine: Path) -> dict:
    """Lit config.toml [hud], sinon config.example.toml, sinon défauts."""
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
                hud = donnees.get("hud", {})
                for cle in DEFAUTS:
                    if cle in hud:
                        config[cle] = hud[cle]
            except (ValueError, OSError):
                pass
    if str(config.get("position", "")) not in (
            "bas-droite", "bas-gauche", "haut-droite", "haut-gauche"):
        config["position"] = "bas-droite"
    try:
        config["taille"] = max(120, min(320, int(config["taille"])))
    except (TypeError, ValueError):
        config["taille"] = 180
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
    """Lit data/hud-state.json ; état « repos » par défaut si absent."""
    defaut = {"etat": "repos", "transcription": "", "erreur": ""}
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


def prochain_minuteur(minuteurs: list, ref: datetime):
    """Le minuteur le plus proche (échus inclus, pour le flash) ou None."""
    return minuteurs[0] if minuteurs else None


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


def formater_prochains(minuteurs: list, ref: datetime, nombre: int = 2) -> str:
    """Lignes « <étiquette> : dans 12 min » pour le panneau déplié."""
    lignes = []
    for minuteur in minuteurs[:nombre]:
        reste = (minuteur["due"] - ref).total_seconds()
        quoi = minuteur["label"] or minuteur["kind"]
        if reste < 0:
            lignes.append(f"• {quoi} : échue")
        else:
            lignes.append(
                f"• {quoi} : dans {formater_compte_a_rebours(reste)}")
    return "\n".join(lignes) if lignes else "Aucun minuteur en cours."


def ecrire_ptt(chemin: Path, actif: bool) -> None:
    """Écrit data/hud-ptt.json (atomique) : clic maintenu ou relâché."""
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


def lire_ptt(chemin: Path = FICHIER_PTT) -> bool:
    """Vrai si le HUD signale un clic maintenu récent (moins de 2 s)."""
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        if not donnees.get("actif"):
            return False
        moment = _analyser_echeance(donnees.get("horodatage", ""))
        if moment is None:
            return False
        return (datetime.now(FUSEAU) - moment).total_seconds() < FRAICHEUR_PTT
    except (OSError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Position mémorisée (ancre = coin bas-droit de la fenêtre)
# ---------------------------------------------------------------------------

def charger_position(racine: Path) -> dict:
    """Lit data/widget.json ; {"ancre_x": int|None, "ancre_y": int|None}."""
    try:
        donnees = json.loads(
            (racine / "data" / "widget.json").read_text(encoding="utf-8"))
        return {
            "ancre_x": donnees.get("ancre_x"),
            "ancre_y": donnees.get("ancre_y"),
        }
    except (OSError, ValueError, AttributeError):
        return {"ancre_x": None, "ancre_y": None}


def sauvegarder_position(racine: Path, ancre_x: int, ancre_y: int) -> None:
    """Mémorise le coin bas-droit de la fenêtre (atomique, silencieux)."""
    try:
        dossier = racine / "data"
        dossier.mkdir(parents=True, exist_ok=True)
        chemin = dossier / "widget.json"
        temporaire = chemin.with_suffix(".json.tmp")
        temporaire.write_text(json.dumps(
            {"ancre_x": int(ancre_x), "ancre_y": int(ancre_y)},
            ensure_ascii=False), encoding="utf-8")
        os.replace(temporaire, chemin)
    except OSError:
        pass


def calculer_geometrie(taille: int, hauteur_fenetre: int, position: str,
                       largeur_ecran: int, hauteur_ecran: int,
                       ancre_x: int | None = None,
                       ancre_y: int | None = None,
                       marge: int = 12) -> tuple:
    """Coin haut-gauche (x, y) de la fenêtre pour l'ancre demandée.

    Sans ancre mémorisée, la fenêtre s'ancre au coin choisi de l'écran ;
    avec une ancre, le coin bas-droit de la fenêtre reste sur l'ancre
    (le panneau déplié grandit donc vers le haut).
    """
    if ancre_x is not None and ancre_y is not None:
        return (ancre_x - taille, ancre_y - hauteur_fenetre)
    if position == "bas-gauche":
        return (marge, hauteur_ecran - marge - hauteur_fenetre)
    if position == "haut-droite":
        return (largeur_ecran - marge - taille, marge)
    if position == "haut-gauche":
        return (marge, marge)
    return (largeur_ecran - marge - taille,
            hauteur_ecran - marge - hauteur_fenetre)


def couleur_pour_etat(etat: str) -> str:
    """Couleur de l'anneau pour un état (repos par défaut si inconnu)."""
    return COULEURS.get(etat, COULEURS["repos"])


# ---------------------------------------------------------------------------
# HUD Tkinter
# ---------------------------------------------------------------------------

class HUD:
    """Fenêtre sans cadre : anneau d'état + panneau déplié au survol.

    Clic maintenu sur l'anneau (sans déplacement) = équivalent F9.
    Glisser déplace la fenêtre ; la position est mémorisée.
    Clic droit : menu (Ouvrir le guide, Masquer, Quitter).
    """

    def __init__(self, racine: Path, config: dict):
        self.racine = racine
        self.config = config
        self.taille = int(config["taille"])
        self.racine_tk = tk.Tk()
        self.racine_tk.title("Jarvis")
        self.racine_tk.overrideredirect(True)
        if config.get("toujours_au_premier_plan", True):
            self.racine_tk.attributes("-topmost", True)
        self.racine_tk.configure(bg=COULEUR_FOND)
        self.racine_tk.protocol("WM_DELETE_WINDOW", self.quitter)

        self.etat_affiche = "repos"
        self.dernier_minuteur = None  # Pour détecter une échéance.
        self.flash_jusqua = 0.0
        self._dernier_rendu = None
        self.panneau_ouvert = False
        self.masque = False
        # Clic : _presse (bouton enfoncé), _deplace (glisser),
        # _ptt (clic maintenu sans déplacement = push-to-talk).
        self._presse = False
        self._deplace = False
        self._ptt = False
        self._clic_x = 0
        self._clic_y = 0
        self._clic_temps = 0.0

        self.canvas = tk.Canvas(
            self.racine_tk, width=self.taille, height=self.taille,
            bg=COULEUR_FOND, highlightthickness=0)
        self.canvas.pack()
        marge_anneau = 8
        self.anneau = self.canvas.create_oval(
            marge_anneau, marge_anneau,
            self.taille - marge_anneau, self.taille - marge_anneau,
            outline=COULEURS["repos"], width=10)
        self.texte_heure = self.canvas.create_text(
            self.taille // 2, self.taille // 2 - 14,
            text="--:--", fill=COULEUR_TEXTE,
            font=("Segoe UI", 20, "bold"))
        self.texte_compte = self.canvas.create_text(
            self.taille // 2, self.taille // 2 + 16,
            text="", fill=COULEUR_TEXTE_FAIBLE, font=("Segoe UI", 11))

        self.panneau = tk.Frame(self.racine_tk, bg=COULEUR_FOND)
        self.texte_transcription = tk.Label(
            self.panneau, text="", bg=COULEUR_FOND, fg=COULEUR_TEXTE,
            font=("Segoe UI", 10), wraplength=self.taille - 16,
            justify="left", anchor="w")
        self.texte_transcription.pack(fill="x", padx=8, pady=(2, 0))
        self.texte_minuteurs = tk.Label(
            self.panneau, text="", bg=COULEUR_FOND, fg=COULEUR_TEXTE_FAIBLE,
            font=("Segoe UI", 10), wraplength=self.taille - 16,
            justify="left", anchor="w")
        self.texte_minuteurs.pack(fill="x", padx=8, pady=(0, 6))

        self.menu = tk.Menu(self.racine_tk, tearoff=0)
        self.menu.add_command(label="Ouvrir le guide",
                              command=self.ouvrir_guide)
        self.menu.add_command(label="Masquer", command=self.masquer)
        self.menu.add_command(label="Quitter", command=self.quitter)

        for evenement, action in (
                ("<ButtonPress-1>", self._clic_presse),
                ("<B1-Motion>", self._clic_glisse),
                ("<ButtonRelease-1>", self._clic_relache),
                ("<Enter>", self._survol_entree),
                ("<Leave>", self._survol_sortie),
                ("<Button-3>", self._clic_droit)):
            self.racine_tk.bind(evenement, action)
            self.canvas.bind(evenement, action)
            self.panneau.bind(evenement, action)

        self._appliquer_geometrie()
        self.rafraichir()

    # -- Géométrie ------------------------------------------------------

    def _hauteur_fenetre(self) -> int:
        """Hauteur courante (anneau seul, ou + panneau si déplié)."""
        self.racine_tk.update_idletasks()
        return self.racine_tk.winfo_reqheight()

    def _appliquer_geometrie(self) -> None:
        """Place la fenêtre en gardant son coin bas-droit sur l'ancre."""
        largeur = self.racine_tk.winfo_screenwidth()
        hauteur = self.racine_tk.winfo_screenheight()
        memoire = charger_position(self.racine)
        x, y = calculer_geometrie(
            self.taille, self._hauteur_fenetre(),
            str(self.config.get("position", "bas-droite")),
            largeur, hauteur,
            memoire.get("ancre_x"), memoire.get("ancre_y"))
        self.racine_tk.geometry(f"{self.taille}x{self._hauteur_fenetre()}"
                                 f"+{x}+{y}")

    def _sauver_ancre(self) -> None:
        """Mémorise le coin bas-droit courant de la fenêtre."""
        x = self.racine_tk.winfo_x()
        y = self.racine_tk.winfo_y()
        sauvegarder_position(
            self.racine, x + self.taille, y + self._hauteur_fenetre())

    # -- Panneau déplié -------------------------------------------------

    def _survol_entree(self, _evenement=None) -> None:
        if self.masque or self.panneau_ouvert:
            return
        self.panneau_ouvert = True
        self.panneau.pack(fill="x")
        self._appliquer_geometrie()

    def _survol_sortie(self, _evenement=None) -> None:
        if not self.panneau_ouvert:
            return
        self.panneau_ouvert = False
        self.panneau.pack_forget()
        self._appliquer_geometrie()

    # -- Clic : push-to-talk ou déplacement -----------------------------

    def _clic_presse(self, evenement) -> None:
        if self.masque:
            # Clic sur le point masqué : réafficher le HUD.
            self.masque = False
            self.racine_tk.geometry(
                f"{self.taille}x{self.taille}")
            self.canvas.pack()
            self._appliquer_geometrie()
            return
        self._presse = True
        self._deplace = False
        self._ptt = False
        self._clic_x = evenement.x_root
        self._clic_y = evenement.y_root
        self._clic_temps = time.monotonic()
        # Si le bouton est toujours enfoncé et immobile après 250 ms,
        # c'est un push-to-talk (équivalent F9), pas un déplacement.
        self.racine_tk.after(250, self._verifier_clic_maintenu)

    def _verifier_clic_maintenu(self) -> None:
        if self._presse and not self._deplace and not self._ptt:
            self._ptt = True
            ecrire_ptt(FICHIER_PTT, True)

    def _clic_glisse(self, evenement) -> None:
        if not self._presse or self.masque:
            return
        dx = evenement.x_root - self._clic_x
        dy = evenement.y_root - self._clic_y
        if abs(dx) + abs(dy) > 5:
            self._deplace = True
        if self._deplace and not self._ptt:
            x = self.racine_tk.winfo_x() + dx
            y = self.racine_tk.winfo_y() + dy
            self.racine_tk.geometry(f"+{x}+{y}")
            self._clic_x = evenement.x_root
            self._clic_y = evenement.y_root

    def _clic_relache(self, _evenement=None) -> None:
        if self._ptt:
            ecrire_ptt(FICHIER_PTT, False)
        elif self._deplace:
            self._sauver_ancre()
        self._presse = False
        self._deplace = False
        self._ptt = False

    def _clic_droit(self, evenement) -> None:
        try:
            self.menu.tk_popup(evenement.x_root, evenement.y_root)
        finally:
            self.menu.grab_release()

    # -- Menu -----------------------------------------------------------

    def ouvrir_guide(self) -> None:
        """Ouvre le guide de l'étape 6 (Windows : application associée)."""
        try:
            os.startfile(str(GUIDE))  # type: ignore[attr-defined]
        except (OSError, AttributeError):
            print(f"Guide : {GUIDE}")

    def masquer(self) -> None:
        """Réduit le HUD à un point discret (clic dessus pour réafficher)."""
        self.masque = True
        self.panneau.pack_forget()
        self.panneau_ouvert = False
        self.canvas.pack_forget()
        x = self.racine_tk.winfo_x() + self.taille - 24
        y = self.racine_tk.winfo_y() + self._hauteur_fenetre() - 24
        self.racine_tk.geometry(f"24x24+{x}+{y}")
        self.racine_tk.configure(bg=COULEURS["repos"])

    def quitter(self) -> None:
        if self._ptt:
            ecrire_ptt(FICHIER_PTT, False)
        self.racine_tk.destroy()

    # -- Rafraîchissement -----------------------------------------------

    def rafraichir(self) -> None:
        """Relit l'état et les minuteurs ; ne redessine que si ça change."""
        try:
            maintenant = datetime.now(FUSEAU)
            etat = lire_etat()
            minuteurs = charger_minuteurs()
            prochain = prochain_minuteur(minuteurs, maintenant)

            # Détection d'une échéance : le prochain minuteur connu vient
            # de disparaître alors que son échéance est passée.
            if (self.dernier_minuteur is not None
                    and (prochain is None
                         or prochain["due"] != self.dernier_minuteur["due"])
                    and self.dernier_minuteur["due"] <= maintenant):
                self.flash_jusqua = time.monotonic() + DUREE_FLASH_MINUTEUR
            if prochain is not None:
                self.dernier_minuteur = prochain

            etat_affiche = etat["etat"]
            if self._ptt:
                etat_affiche = "ecoute"
                # Rafraîchir le fichier PTT pour que la boucle ne le
                # considère pas comme périmé pendant un appui long.
                ecrire_ptt(FICHIER_PTT, True)
            elif time.monotonic() < self.flash_jusqua:
                etat_affiche = "minuteur_echu"

            if prochain is not None:
                reste = (prochain["due"] - maintenant).total_seconds()
                compte = formater_compte_a_rebours(reste)
                if reste < 0:
                    compte = "échue"
            else:
                compte = ""
            heure = maintenant.strftime("%H:%M")
            transcription = (etat["transcription"] or "").strip()
            texte_transcription = (
                f"Dernière phrase : {transcription}" if transcription
                else "En attente de F9…")
            texte_minuteurs = formater_prochains(minuteurs, maintenant)
            if etat["etat"] == "erreur" and etat["erreur"]:
                texte_transcription = f"Erreur : {etat['erreur']}"

            rendu = (etat_affiche, heure, compte, texte_transcription,
                     texte_minuteurs,
                     int(time.monotonic() * 2) % 2
                     if etat_affiche == "minuteur_echu" else 0)
            if rendu != self._dernier_rendu:
                self._dernier_rendu = rendu
                couleur = couleur_pour_etat(etat_affiche)
                if etat_affiche == "minuteur_echu" and rendu[-1] == 1:
                    couleur = COULEUR_FOND
                self.canvas.itemconfig(self.anneau, outline=couleur)
                self.canvas.itemconfig(self.texte_heure, text=heure)
                self.canvas.itemconfig(self.texte_compte, text=compte)
                self.texte_transcription.config(text=texte_transcription)
                self.texte_minuteurs.config(text=texte_minuteurs)
                self.etat_affiche = etat_affiche
        except Exception as erreur:  # Le HUD ne doit jamais planter.
            print(f"Avertissement HUD : {erreur}", file=sys.stderr)
        finally:
            self.racine_tk.after(
                int(self.config.get("intervalle_ms", 500)),
                self.rafraichir)

    def demarrer(self) -> None:
        self.racine_tk.mainloop()


# ---------------------------------------------------------------------------
# Repli : icône de barre système seule (si Tkinter indisponible)
# ---------------------------------------------------------------------------

def lancer_barre_systeme(racine: Path, config: dict) -> int:
    """Icône de barre système : couleur = état, infobulle = prochain
    minuteur. Nécessite pystray (optionnel, voir requirements-etape6.txt).
    """
    try:
        import threading

        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        print("Erreur : Tkinter est indisponible et pystray n'est pas "
              "installé.", file=sys.stderr)
        print("Installez-le avec :", file=sys.stderr)
        print("  pip install pystray", file=sys.stderr)
        print("Ou réinstallez Python avec l'option « tcl/tk and IDLE ».",
              file=sys.stderr)
        return 3

    def image_etat(etat: str):
        image = Image.new("RGB", (64, 64), (32, 36, 42))
        dessin = ImageDraw.Draw(image)
        dessin.ellipse([8, 8, 56, 56],
                       fill=couleur_pour_etat(etat))
        return image

    def infobulle() -> str:
        maintenant = datetime.now(FUSEAU)
        etat = lire_etat()
        minuteurs = charger_minuteurs()
        prochain = prochain_minuteur(minuteurs, maintenant)
        texte = f"Jarvis — {etat['etat']}"
        if prochain is not None:
            reste = (prochain["due"] - maintenant).total_seconds()
            texte += (f" — prochain : "
                      f"{formater_compte_a_rebours(reste)}")
        return texte

    icone = pystray.Icon(
        "jarvis", image_etat("repos"), "Jarvis",
        menu=pystray.Menu(
            pystray.MenuItem("Ouvrir le guide",
                             lambda: os.startfile(str(GUIDE))),
            pystray.MenuItem("Quitter", lambda: icone.stop())))
    arret = threading.Event()

    def surveiller():
        dernier = None
        while not arret.is_set():
            courant = (lire_etat()["etat"], infobulle())
            if courant != dernier:
                dernier = courant
                icone.icon = image_etat(courant[0])
                icone.title = courant[1]
            arret.wait(1.0)

    fil = threading.Thread(target=surveiller, daemon=True)
    fil.start()
    print("HUD (barre système) : Tkinter indisponible, repli sur l'icône.")
    print("Couleur de l'icône = état ; infobulle = prochain minuteur.")
    try:
        icone.run()
    finally:
        arret.set()
    return 0


# ---------------------------------------------------------------------------
# Vérification et point d'entrée
# ---------------------------------------------------------------------------

def verifier(config: dict) -> int:
    """Vérifie l'installation et la configuration, puis affiche un bilan."""
    print("Vérification du HUD (étape 6) :")
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
    if not TKINTER_DISPONIBLE:
        try:
            import pystray  # noqa: F401

            ligne(True, "pystray (repli barre système)")
        except ImportError:
            ligne(False, "pystray (repli barre système)",
                  "pip install pystray")
    try:
        (RACINE / "data").mkdir(parents=True, exist_ok=True)
        ligne(os.access(RACINE / "data", os.W_OK), "dossier data/ en écriture")
    except OSError as erreur:
        ligne(False, "dossier data/ en écriture", str(erreur))
    ligne(bool(config.get("active", True)), "HUD activé ([hud] active)",
          "mettre active = true dans config.toml" if not config.get(
              "active", True) else "")
    print()
    if problemes:
        print(f"{len(problemes)} élément(s) à régler : "
              + ", ".join(problemes) + ".")
        print("Voir docs/etape-6-hud-session.md pour les détails.")
        return 1
    print("Tout est en place. Lancez le HUD avec :")
    print("  python scripts\\hud.py")
    print("Ou lancez une session complète avec :")
    print("  powershell -ExecutionPolicy Bypass -File "
          "scripts\\lancer_session.ps1")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="HUD local léger : anneau d'état, heure et prochain "
                    "minuteur (Tkinter, bibliothèque standard).")
    parser.add_argument(
        "--verifier", action="store_true",
        help="Vérifier l'installation et la configuration, puis quitter.")
    parser.add_argument(
        "--taille", type=int, default=None,
        help="Taille de la fenêtre en pixels (défaut : config.toml).")
    parser.add_argument(
        "--position", default=None,
        choices=["bas-droite", "bas-gauche", "haut-droite", "haut-gauche"],
        help="Coin de l'écran (défaut : config.toml).")
    args = parser.parse_args()

    config = charger_config_hud(RACINE)
    if args.taille is not None:
        config["taille"] = args.taille
    if args.position is not None:
        config["position"] = args.position

    if args.verifier:
        return verifier(config)
    if not config.get("active", True):
        print("HUD désactivé dans config.toml ([hud] active = false).")
        return 0
    if not TKINTER_DISPONIBLE:
        return lancer_barre_systeme(RACINE, config)
    try:
        hud = HUD(RACINE, config)
    except Exception as erreur:
        print(f"Erreur : impossible d'ouvrir une fenêtre ({erreur}).",
              file=sys.stderr)
        print("Sur une machine sans écran, le HUD ne peut pas s'afficher.",
              file=sys.stderr)
        return 3
    hud.demarrer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
