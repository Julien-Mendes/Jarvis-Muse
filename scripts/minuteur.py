#!/usr/bin/env python3
"""minuteur.py — Minuteur local persistant du Jarvis-Muse.

Usage :
    python scripts/minuteur.py demarrer --minutes 40 --etiquette "pâtes"
    python scripts/minuteur.py demarrer --a 18:30 --etiquette "poster les colis"
    python scripts/minuteur.py lister
    python scripts/minuteur.py annuler 3
    python scripts/minuteur.py annuler "pâtes"
    python scripts/minuteur.py annuler tout
    python scripts/minuteur.py declencher
    python scripts/minuteur.py surveiller

Tout se passe sur la machine : aucune donnée ne quitte le poste, aucun appel
réseau. Les minuteurs sont conservés dans data/timers.json (gitignoré) et
survivent à un redémarrage. Ceux arrivés à échéance pendant que la machine
était éteinte sont annoncés au démarrage de la surveillance.

À l'échéance : carillon + annonce vocale via scripts/lire_voix.py (Piper,
voix locale), dans la langue de config.toml ([general] langue, relue à chaque
annonce ; --langue fr|en la remplace) — sauf pendant un tour de la boucle
vocale dans l'autre langue (lot L1, champ « langue » de data/hud-state.json) :
l'annonce suit alors la langue du tour. Si la voix n'est pas disponible, le
message est affiché à l'écran et le carillon est joué quand même.

Lot F1 (docs/etape-14-fiabilite-minuteurs.md) : une entrée mal formée est
mise de côté (data/timers.json.invalides) sans arrêter les autres ; un fichier
corrompu est conservé (data/timers.json.corrompu-…) avant de repartir de zéro ;
un minuteur n'est retiré qu'après une annonce réussie ; chaque problème est
signalé (logs/minuteurs.log + fenêtre Windows) et le surveillant ne meurt pas.

Limites (patron du dépôt B, décisions du 21 nov. 2026) :
  - 20 minuteurs actifs maximum.
  - compte à rebours : entre quelques secondes et 1 semaine.
  - rappel à heure fixe : jusqu'à 1 an dans le futur.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Modules voisins (verrou.py…) importables même si ce fichier est chargé
# par chemin (tests, importlib) et non lancé comme script.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import config_jarvis
import langue_tour as langue_tour_mod  # lot L1
from verrou import VerrouInstance, verrou_fichier

# Réglages lus une fois à l'import (K1) : fuseau et limites du minuteur.
_CONFIG = config_jarvis.charger_donnees()
FUSEAU = config_jarvis.fuseau(_CONFIG)

# [minuteur] max_actifs (1 à 100) et duree_max (« 7j », « 12h », « 90m ») ;
# défauts : 20 minuteurs, 1 semaine. Le fichier (data/timers.json) n'est pas
# réglable : l'application, le HUD et le lanceur le lisent à cet endroit.
MAX_ACTIFS = config_jarvis.nombre_borne(
    config_jarvis.section(_CONFIG, "minuteur").get("max_actifs", 20),
    1, 100, 20, entier=True)
DUREE_MAX_MINUTES = config_jarvis.duree_en_minutes(
    config_jarvis.section(_CONFIG, "minuteur").get("duree_max", "7j"),
    7 * 24 * 60)
# [voix] vitesse (0.5 à 2.0), transmise à lire_voix.py pour les annonces (V1).
VITESSE_VOIX = config_jarvis.nombre_borne(
    config_jarvis.section(_CONFIG, "voix").get("vitesse", 1.0), 0.5, 2.0, 1.0)
AVANCE_MAX = timedelta(days=365)  # 1 an.
LONGUEUR_MAX_ETIQUETTE = 80

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
JOURS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday"]
MOIS_EN = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]


# Intervalle de vérification du surveillant (secondes) : un minuteur de
# quelques secondes réglé pendant que le surveillant dort sonne au pire
# 5 s en retard (avant : 30 s).
INTERVALLE_VERIFICATION_S = 5.0


def maintenant() -> datetime:
    """Heure locale actuelle."""
    return datetime.now(FUSEAU)


def langue_courante(dossier_config: Path | None = None) -> str:
    """Langue des annonces : « fr » ou « en ».

    Celle de la configuration ([general] langue ; config.toml puis
    config.local.toml par-dessus config.example.toml), comme boucle_voix.py ;
    « en » si rien n'est lisible. Relue à chaque annonce : changer la langue
    n'exige pas de redémarrer `surveiller`.
    """
    return config_jarvis.langue(config_jarvis.charger_donnees(dossier_config))


def chemin_etat_hud() -> Path:
    """data/hud-state.json, écrit par la boucle vocale (langue du tour)."""
    return Path(__file__).resolve().parent.parent / "data" / "hud-state.json"


def langue_annonce(dossier_config: Path | None = None,
                   chemin_etat: Path | None = None) -> str:
    """Langue d'une annonce de minuteur (décision Q7 + lot L1).

    Celle de la config, sauf si un tour est en cours dans l'autre langue
    (champ « langue » de data/hud-state.json, frais) : l'annonce suit alors
    la langue du tour. Avec [general] langue_auto = false : la config seule.
    """
    donnees = config_jarvis.charger_donnees(dossier_config)
    langue_config = config_jarvis.langue(donnees)
    if not config_jarvis.langue_auto(donnees):
        return langue_config
    return langue_tour_mod.langue_annonce_minuteur(
        langue_config,
        langue_tour_mod.langue_tour_en_cours(chemin_etat or chemin_etat_hud()))


def chemin_donnees_defaut() -> Path:
    """Chemin du fichier de persistance (data/timers.json à la racine)."""
    return Path(__file__).resolve().parent.parent / "data" / "timers.json"


# ---------------------------------------------------------------------------
# Persistance (écriture atomique : fichier temporaire puis remplacement)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Lot F1 — signalement (journal + avertissement visible)
# ---------------------------------------------------------------------------
# Le surveillant tourne sans console (pythonw, lancé par lancer_app.py) : une
# ligne dans un journal ne suffit pas. Chaque problème est écrit dans
# logs/minuteurs.log ET affiché dans une fenêtre Windows, ouverte par un petit
# processus détaché : elle ne bloque jamais le surveillant, et elle reste
# affichée même quand l'appelant est une commande courte (minuteur.py demarrer
# lancé par la boucle vocale), qui se termine aussitôt.

DOSSIER_LOGS = Path(__file__).resolve().parent.parent / "logs"
_SCRIPT_FENETRE = (
    "import ctypes, sys; "
    "ctypes.windll.user32.MessageBoxW(0, sys.argv[1], 'Jarvis — minuteurs', "
    "0x30 | 0x40000 | 0x10000)")


def _journaliser(message: str) -> None:
    """Ajoute une ligne horodatée à logs/minuteurs.log (jamais d'exception)."""
    try:
        DOSSIER_LOGS.mkdir(parents=True, exist_ok=True)
        horodatage = datetime.now(FUSEAU).isoformat(timespec="seconds")
        with (DOSSIER_LOGS / "minuteurs.log").open("a", encoding="utf-8") as f:
            f.write(f"[{horodatage}] {message}\n")
    except OSError:
        pass


def _fenetre_windows(message: str) -> None:
    """Fenêtre d'avertissement Windows, dans un processus détaché (ne bloque
    pas l'appelant). Hors Windows : rien (le message est déjà affiché)."""
    if sys.platform != "win32":
        return
    interpreteur = Path(sys.executable)
    sans_console = interpreteur.with_name("pythonw.exe")
    if sans_console.exists():
        interpreteur = sans_console
    try:
        subprocess.Popen(
            [str(interpreteur), "-c", _SCRIPT_FENETRE, message],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, ValueError):
        pass


def signaler(message: str) -> None:
    """Problème de minuteur : sortie d'erreur, journal, fenêtre Windows.
    Ne lève jamais d'exception."""
    try:
        print(f"Avertissement minuteurs : {message}", file=sys.stderr,
              flush=True)
    except (OSError, ValueError, AttributeError):
        pass  # pythonw sans sortie : le journal et la fenêtre suffisent.
    _journaliser(message)
    try:
        _fenetre_windows(message)
    except Exception:  # noqa: BLE001 — le signalement ne plante jamais.
        pass


class FichierIndisponible(OSError):
    """timers.json existe mais ne peut pas être lu pour l'instant (verrou
    Windows, droits…). Ce n'est pas une corruption : l'appelant ne doit
    surtout pas repartir d'une liste vide et la réécrire par-dessus."""


def _etat_vide() -> dict:
    return {"timers": [], "next_id": 1}


def _mettre_de_cote_corrompu(chemin: Path, brut: bytes, raison: str) -> None:
    """Renomme le fichier corrompu en timers.json.corrompu-AAAAMMJJ-HHMMSS.

    Seulement s'il contient toujours ce qui a été lu (un autre processus a pu
    le remplacer par un état valide entre-temps). Si le renommage échoue, on
    lève FichierIndisponible : jamais d'écrasement silencieux.
    """
    try:
        actuel = chemin.read_bytes()
    except FileNotFoundError:
        return  # déjà mis de côté par un autre processus.
    except OSError as erreur:
        raise FichierIndisponible(
            f"{chemin.name} corrompu et impossible à relire ({erreur})"
        ) from erreur
    if actuel != brut:
        raise _ContenuChange()
    horodatage = datetime.now(FUSEAU).strftime("%Y%m%d-%H%M%S")
    copie = chemin.with_name(f"{chemin.name}.corrompu-{horodatage}")
    numero = 1
    while copie.exists():
        numero += 1
        copie = chemin.with_name(
            f"{chemin.name}.corrompu-{horodatage}-{numero}")
    try:
        chemin.replace(copie)
    except FileNotFoundError:
        return
    except OSError as erreur:
        raise FichierIndisponible(
            f"{chemin.name} corrompu ({raison}) et impossible à mettre de "
            f"côté ({erreur}) : aucun minuteur ne sera enregistré par-dessus."
        ) from erreur
    signaler(f"Le fichier des minuteurs était illisible ({raison}). Il a été "
             f"conservé sous le nom {copie.name} (dossier data) ; la liste "
             "des minuteurs repart de zéro.")


class _ContenuChange(Exception):
    """Le fichier a changé pendant sa mise de côté : relire."""


def _lire_brut(chemin: Path) -> bytes | None:
    """Octets de timers.json ; None s'il n'existe pas. Quelques reprises si
    Windows le refuse un instant (remplacement en cours par un autre
    processus) ; ensuite FichierIndisponible."""
    for essai in range(5):
        try:
            return chemin.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as erreur:
            if essai == 4:
                raise FichierIndisponible(
                    f"{chemin.name} momentanément illisible ({erreur})"
                ) from erreur
            time.sleep(0.05)
    return None


def charger(chemin: Path) -> dict:
    """Lit l'état des minuteurs ; état vide si le fichier est absent.

    Lot F1 : un fichier corrompu (JSON invalide, structure inattendue) est
    d'abord conservé (timers.json.corrompu-…, signalé) avant de repartir
    d'une liste vide. Un fichier momentanément illisible lève
    FichierIndisponible (sous-classe d'OSError) : on ne repart jamais d'une
    liste vide qui serait ensuite écrite par-dessus les vrais minuteurs.
    """
    chemin = Path(chemin)
    for _ in range(3):
        brut = _lire_brut(chemin)
        if brut is None:
            return _etat_vide()
        try:
            etat = json.loads(brut.decode("utf-8"))
            raison = None
            if not isinstance(etat, dict):
                raison = "contenu inattendu"
            elif not isinstance(etat.get("timers", []), list):
                raison = "liste des minuteurs inattendue"
        except ValueError as erreur:  # JSON ou UTF-8 invalide.
            raison = f"JSON invalide : {erreur}"
        if raison is None:
            break
        try:
            _mettre_de_cote_corrompu(chemin, brut, raison)
        except _ContenuChange:
            continue
        return _etat_vide()
    else:
        raise FichierIndisponible(f"{chemin.name} change sans cesse")
    etat.setdefault("timers", [])
    if not isinstance(etat.get("next_id"), int) or isinstance(
            etat.get("next_id"), bool):
        identifiants = [m.get("id") for m in etat["timers"]
                        if isinstance(m, dict)
                        and isinstance(m.get("id"), int)]
        etat["next_id"] = max(identifiants, default=0) + 1
    return etat


# ---------------------------------------------------------------------------
# Lot F1 — validation des entrées
# ---------------------------------------------------------------------------

def echeance(minuteur) -> datetime:
    """Échéance d'un minuteur, avec fuseau. ValueError (raison lisible) si
    l'entrée est mal formée : pas un objet, échéance absente, date
    illisible, date sans fuseau (incomparable avec l'heure actuelle)."""
    if not isinstance(minuteur, dict):
        raise ValueError("entrée qui n'est pas un minuteur")
    brut = minuteur.get("due")
    if brut is None or brut == "":
        raise ValueError("échéance absente")
    if not isinstance(brut, str):
        raise ValueError("échéance illisible")
    try:
        due = datetime.fromisoformat(brut)
    except ValueError:
        raise ValueError(f"échéance illisible (« {brut[:40]} »)") from None
    if due.tzinfo is None or due.utcoffset() is None:
        raise ValueError("échéance sans fuseau horaire")
    return due


def _nom_minuteur(minuteur) -> str:
    if isinstance(minuteur, dict):
        etiquette = str(minuteur.get("label") or "").strip()
        if etiquette:
            return f"« {etiquette[:LONGUEUR_MAX_ETIQUETTE]} »"
        if minuteur.get("id") is not None:
            return f"n° {minuteur.get('id')}"
    return "sans nom"


def chemin_invalides(chemin: Path) -> Path:
    """timers.json.invalides : entrées mal formées mises de côté (lot F1)."""
    chemin = Path(chemin)
    return chemin.with_name(chemin.name + ".invalides")


def _ecarter_invalides(chemin: Path, etat: dict) -> list:
    """Retire de `etat` les entrées mal formées, les ajoute (avec la raison)
    à timers.json.invalides et les signale. À appeler sous verrou ; l'appelant
    sauvegarde `etat`. Retourne les minuteurs valides (avec leur échéance)."""
    valides, ecartes = [], []
    for minuteur in etat["timers"]:
        try:
            valides.append((minuteur, echeance(minuteur)))
        except ValueError as erreur:
            ecartes.append({"minuteur": minuteur, "raison": str(erreur),
                            "ecarte_le": maintenant().isoformat()})
    if not ecartes:
        return valides
    fichier = chemin_invalides(chemin)
    try:
        deja = json.loads(fichier.read_text(encoding="utf-8"))
        if not isinstance(deja, list):
            deja = []
    except (OSError, ValueError):
        deja = []
    sauvegarder(fichier, deja + ecartes)
    etat["timers"] = [m for m, _ in valides]
    noms = ", ".join(f"{_nom_minuteur(e['minuteur'])} ({e['raison']})"
                     for e in ecartes[:5])
    signaler(f"{len(ecartes)} minuteur(s) mal formé(s) écarté(s) : {noms}. "
             f"Ils sont conservés dans {fichier.name} (dossier data) ; les "
             "autres minuteurs continuent normalement.")
    return valides


def sauvegarder(chemin: Path, etat: dict) -> None:
    """Écrit l'état de façon atomique."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_suffix(".tmp")
    temporaire.write_text(json.dumps(etat, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    # Windows refuse parfois le remplacement quand un autre processus lit le
    # fichier à cet instant (l'application, par exemple) : quelques reprises.
    for essai in range(5):
        try:
            temporaire.replace(chemin)
            return
        except PermissionError:
            if essai == 4:
                raise
            time.sleep(0.05)


# ---------------------------------------------------------------------------
# Formatage en français (sans dépendre de la locale Windows)
# ---------------------------------------------------------------------------

def formater_duree(minutes: float) -> str:
    """« 45 secondes », « 40 minutes », « 1 heure 30 »."""
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


def formater_echeance(due: datetime, ref: datetime) -> str:
    """« aujourd'hui à 18 h 42 », « demain à 9 h 00 », « le samedi 22 novembre à 10 h 00 »."""
    heure = f"{due.hour} h {due.minute:02d}"
    if due.date() == ref.date():
        return f"aujourd'hui à {heure}"
    if due.date() == (ref + timedelta(days=1)).date():
        return f"demain à {heure}"
    return (f"le {JOURS[due.weekday()]} {due.day} {MOIS[due.month - 1]} "
            f"à {heure}")


def formater_echeance_en(due: datetime, ref: datetime) -> str:
    """« today at 6:42 PM », « tomorrow at 9:00 AM », « on Saturday, November 22 at 10:00 AM »."""
    heure = f"{(due.hour % 12) or 12}:{due.minute:02d} {'AM' if due.hour < 12 else 'PM'}"
    if due.date() == ref.date():
        return f"today at {heure}"
    if due.date() == (ref + timedelta(days=1)).date():
        return f"tomorrow at {heure}"
    return (f"on {JOURS_EN[due.weekday()]}, {MOIS_EN[due.month - 1]} "
            f"{due.day} at {heure}")


def message_echeance_en(minuteur: dict, quand: datetime, ref: datetime,
                        manque: bool) -> str:
    """Message d'échéance en anglais (même sens que les messages français)."""
    etiquette = minuteur["label"]
    genre = "timer" if minuteur["kind"] == "timer" else "reminder"
    if manque:
        nom = f'"{etiquette}" ' if etiquette else ""
        return (f"While I was off, your {genre} {nom}came due "
                f"{formater_echeance_en(quand, ref)}.")
    if minuteur["kind"] == "timer":
        return (f'Your timer "{etiquette}" is done.' if etiquette
                else "Your timer is done.")
    return f"Reminder: {etiquette}." if etiquette else "Your reminder is due."


def nettoyer_etiquette(etiquette: str) -> str:
    """Normalise l'étiquette (espaces, 80 caractères maximum)."""
    return " ".join(etiquette.split())[:LONGUEUR_MAX_ETIQUETTE]


# ---------------------------------------------------------------------------
# Analyse de l'heure fixe demandée
# ---------------------------------------------------------------------------

def analyser_heure(texte: str, ref: datetime) -> datetime:
    """Comprend « 18:30 », « 2026-11-22T18:30 » et « 2026-11-22 18:30 ».

    « 18:30 » seul vise aujourd'hui, ou demain si l'heure est déjà passée.
    """
    texte = texte.strip()
    for motif in ("%H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            analyse = datetime.strptime(texte, motif)
        except ValueError:
            continue
        if motif == "%H:%M":
            due = ref.replace(hour=analyse.hour, minute=analyse.minute,
                              second=0, microsecond=0)
            if due <= ref:
                due += timedelta(days=1)
            return due
        return analyse.replace(tzinfo=FUSEAU)
    raise ValueError(
        f"« {texte} » n'est pas une heure comprise ; "
        "utilisez HH:MM (ex. 18:30) ou AAAA-MM-JJTHH:MM (ex. 2026-11-22T18:30).")


# ---------------------------------------------------------------------------
# Carillon et annonce vocale
# ---------------------------------------------------------------------------

def carillon() -> None:
    """Deux notes (880 Hz puis 1318,5 Hz), comme le carillon du dépôt B."""
    if sys.platform != "win32":
        print("(Carillon non disponible hors Windows ; l'annonce suit.)")
        return
    import winsound

    winsound.Beep(880, 400)
    winsound.Beep(1318, 600)


def annoncer(message: str, langue: str = "fr",
             vitesse: float | None = None) -> None:
    """Carillon + lecture du message à voix haute via lire_voix.py.

    `langue` (« fr » ou « en ») choisit la voix : elle doit être celle du
    message (voir declencher_dus).

    Si la voix n'est pas disponible (Piper non installé, voix absente), le
    message est affiché à l'écran : l'alerte n'est jamais perdue.
    `vitesse` : [voix] vitesse par défaut (VITESSE_VOIX).
    """
    print(f"🔔 {message}", flush=True)
    vitesse = VITESSE_VOIX if vitesse is None else vitesse
    carillon()
    script_voix = Path(__file__).resolve().parent / "lire_voix.py"
    try:
        # La voix suit la langue du message, donc la langue de la config
        # (décision de Julien, 22 nov. 2026 : fini le français forcé).
        resultat = subprocess.run(
            [sys.executable, str(script_voix), "--texte", message,
             "--langue", langue, "--vitesse", f"{float(vitesse):g}"],
            capture_output=True, text=True, timeout=120,
        )
        if resultat.returncode != 0:
            erreur = (resultat.stderr or "").strip().splitlines()
            detail = erreur[0] if erreur else "code de sortie " \
                f"{resultat.returncode}"
            print(f"Annonce vocale indisponible ({detail}) ; "
                  "message affiché ci-dessus.", file=sys.stderr)
    except FileNotFoundError:
        print("Annonce vocale indisponible : lire_voix.py introuvable ; "
              "message affiché ci-dessus.", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("Annonce vocale : délai dépassé ; message affiché ci-dessus.",
              file=sys.stderr)
    except OSError as erreur:
        print(f"Annonce vocale indisponible ({erreur}) ; "
              "message affiché ci-dessus.", file=sys.stderr)


# ---------------------------------------------------------------------------
# Déclenchement des minuteurs échus
# ---------------------------------------------------------------------------

# Lot F1 : une annonce qui plante laisse le minuteur enregistré ; nouvel essai
# après un délai croissant (30 s, 1 min, 2 min… 5 min au plus), pour ne pas
# relancer le carillon toutes les 5 s. Mémoire du processus : un surveillant
# relancé réessaie tout de suite. Clé : (id, échéance).
_ECHECS_ANNONCE: dict = {}
DELAI_NOUVEL_ESSAI_S = 30.0
DELAI_NOUVEL_ESSAI_MAX_S = 300.0


def _cle_annonce(minuteur: dict) -> tuple:
    return (minuteur.get("id"), minuteur.get("due"))


def message_echeance(minuteur: dict, quand: datetime, ref: datetime,
                     langue: str, debut_surveillance=None) -> str:
    """Phrase d'échéance d'un minuteur (fr ou en), manqué ou non."""
    manque = bool(debut_surveillance
                  and quand < debut_surveillance - timedelta(minutes=1))
    minuteur = dict(minuteur)
    minuteur["label"] = str(minuteur.get("label") or "")
    minuteur["kind"] = str(minuteur.get("kind") or "timer")
    etiquette = minuteur["label"]
    if langue == "en":
        return message_echeance_en(minuteur, quand, ref, manque)
    if manque:
        return (f"Pendant que j'étais éteint, ton {minuteur['kind']} "
                f"{'« ' + etiquette + ' » ' if etiquette else ''}"
                f"est arrivé à échéance {formater_echeance(quand, ref)}.")
    if minuteur["kind"] == "timer":
        return (f"Ton minuteur {'« ' + etiquette + ' » ' if etiquette else ''}"
                "est terminé.")
    return (f"Rappel : {etiquette}." if etiquette
            else "Ton rappel est arrivé à échéance.")


def _retirer(chemin: Path, minuteur: dict) -> None:
    """Retire un minuteur annoncé (sous verrou ; relu : un autre processus a
    pu modifier le fichier pendant l'annonce)."""
    with verrou_fichier(chemin):
        etat = charger(chemin)
        restants = [m for m in etat["timers"] if m != minuteur]
        if len(restants) != len(etat["timers"]):
            etat["timers"] = restants
            sauvegarder(chemin, etat)


def declencher_dus(chemin: Path, debut_surveillance=None,
                   langue: str | None = None) -> list:
    """Annonce puis retire les minuteurs échus. Retourne les messages dits.

    `langue` : « fr » ou « en » ; None = langue de la config (relue ici),
    ou celle du tour en cours s'il est dans l'autre langue (L1).

    Si debut_surveillance est fourni (démarrage de `surveiller`), les
    minuteurs échus avant (début - 1 minute) sont annoncés comme manqués
    pendant que la machine était éteinte.

    Lot F1 : une entrée mal formée est mise de côté et signalée (les autres
    sonnent) ; un minuteur n'est retiré qu'après une annonce réussie — si
    l'annonce plante, il reste enregistré, l'erreur est signalée et un
    nouvel essai suit. Les seules exceptions possibles viennent du fichier
    lui-même (FichierIndisponible) : le surveillant les rattrape.
    """
    # Le minuteur n'étant retiré qu'après son annonce, deux déclencheurs
    # simultanés (le surveillant et `minuteur.py declencher`) l'annonceraient
    # deux fois : un seul annonce à la fois, l'autre passe son tour.
    annonceur = VerrouInstance("annonce-minuteurs", Path(chemin).parent)
    if not annonceur.acquerir():
        return []
    try:
        return _declencher_dus(chemin, debut_surveillance, langue)
    finally:
        annonceur.liberer()


def _declencher_dus(chemin: Path, debut_surveillance, langue) -> list:
    ref = maintenant()
    # Lire, écarter les entrées mal formées et repérer les échus sous verrou
    # (M3) ; les annonces, longues, se font hors verrou.
    with verrou_fichier(chemin):
        etat = charger(chemin)
        avant = len(etat["timers"])
        valides = _ecarter_invalides(chemin, etat)
        if len(etat["timers"]) != avant:
            sauvegarder(chemin, etat)
    horloge = time.monotonic()
    # Un minuteur en pause (lot U3) ne sonne jamais.
    dus = sorted(((m, quand) for m, quand in valides
                  if not m.get("paused") and quand <= ref
                  and _ECHECS_ANNONCE.get(_cle_annonce(m), (0, 0.0))[1]
                  <= horloge),
                 key=lambda paire: paire[1])
    if not dus:
        return []
    langue = langue or langue_annonce()

    messages = []
    for minuteur, quand in dus:
        message = message_echeance(minuteur, quand, ref, langue,
                                   debut_surveillance)
        cle = _cle_annonce(minuteur)
        try:
            annoncer(message, langue)
        except Exception as erreur:  # noqa: BLE001 — le minuteur reste.
            echecs = _ECHECS_ANNONCE.get(cle, (0, 0.0))[0] + 1
            delai = min(DELAI_NOUVEL_ESSAI_MAX_S,
                        DELAI_NOUVEL_ESSAI_S * 2 ** (echecs - 1))
            _ECHECS_ANNONCE[cle] = (echecs, time.monotonic() + delai)
            if echecs == 1:
                signaler(f"L'annonce du minuteur {_nom_minuteur(minuteur)} a "
                         f"échoué ({type(erreur).__name__} : {erreur}). Il "
                         "reste enregistré ; nouvel essai dans "
                         f"{delai:g} s. Message : {message}")
            else:
                _journaliser(f"Annonce de {_nom_minuteur(minuteur)} : nouvel "
                             f"échec n° {echecs} ({erreur}).")
            continue
        _ECHECS_ANNONCE.pop(cle, None)
        messages.append(message)
        _retirer(chemin, minuteur)
    return messages


# ---------------------------------------------------------------------------
# Commandes
# ---------------------------------------------------------------------------

def cmd_demarrer(args) -> int:
    ref = maintenant()
    etiquette = nettoyer_etiquette(args.etiquette or "")

    if args.a is not None:
        try:
            due = analyser_heure(args.a, ref)
        except ValueError as erreur:
            print(f"Erreur : {erreur}", file=sys.stderr)
            return 1
        genre, minutes = "rappel", None
    elif args.minutes is not None:
        minutes = args.minutes
        if not 0 < minutes <= DUREE_MAX_MINUTES:
            print("Erreur : un minuteur doit durer entre quelques secondes "
                  "et une semaine.", file=sys.stderr)
            return 1
        due = ref + timedelta(minutes=minutes)
        genre = "timer"
    else:
        print("Erreur : indiquez une durée (--minutes) ou une heure (--a).",
              file=sys.stderr)
        return 1

    if due <= ref:
        print(f"Erreur : {formater_echeance(due, ref)} est déjà passé.",
              file=sys.stderr)
        return 1
    if due - ref > AVANCE_MAX:
        print("Erreur : c'est à plus d'un an ; trop loin.", file=sys.stderr)
        return 1

    try:
        minuteur = _ajouter(args.donnees, genre, etiquette, due, minutes, ref)
    except FichierIndisponible as erreur:
        print(f"Erreur : fichier des minuteurs indisponible pour l'instant "
              f"({erreur}) ; réessayez.", file=sys.stderr)
        return 1
    if minuteur is None:
        return 1

    quoi = (f"Minuteur de {formater_duree(minutes)}" if genre == "timer"
            else "Rappel")
    if etiquette:
        quoi += f" « {etiquette} »"
    print(f"Réglé : {quoi}, pour {formater_echeance(due, ref)} "
          f"(n° {minuteur['id']}).")
    return 0


def _ajouter(chemin: Path, genre: str, etiquette: str, due: datetime,
             minutes, ref: datetime) -> dict | None:
    """Ajoute un minuteur sous verrou ; None (message affiché) si la limite
    est atteinte. FichierIndisponible : rien n'est écrit."""
    with verrou_fichier(chemin):  # M3 : lire-modifier-écrire d'un bloc.
        etat = charger(chemin)
        if len(etat["timers"]) >= MAX_ACTIFS:
            print(f"Erreur : il y a déjà {MAX_ACTIFS} minuteurs actifs ; "
                  "annulez-en d'abord.", file=sys.stderr)
            return None
        minuteur = {"id": etat["next_id"], "kind": genre,
                    "label": etiquette, "due": due.isoformat(),
                    "minutes": minutes, "created": ref.isoformat()}
        etat["next_id"] += 1
        etat["timers"].append(minuteur)
        sauvegarder(chemin, etat)
    return minuteur


def cmd_lister(args) -> int:
    ref = maintenant()
    etat = charger(args.donnees)
    # Lot F1 : une entrée mal formée est ignorée ici (lecture seule) ; le
    # surveillant la met de côté et la signale.
    valides, ignores = [], 0
    for minuteur in etat["timers"]:
        try:
            valides.append((echeance(minuteur), minuteur))
        except ValueError:
            ignores += 1
    valides.sort(key=lambda paire: paire[0])
    if ignores:
        print(f"({ignores} entrée(s) mal formée(s) ignorée(s).)")
    if not valides:
        print("Aucun minuteur ni rappel en cours.")
        return 0
    print(f"{len(valides)} en cours :")
    for due, minuteur in valides:
        reste = due - ref
        etiquette = str(minuteur.get("label") or "")
        quoi = str(minuteur.get("kind") or "timer") + (
            f" « {etiquette} »" if etiquette else "")
        if minuteur.get("paused"):
            secondes = int(float(minuteur.get("remaining_s") or 0))
            print(f"- n° {minuteur['id']} — {quoi} : en pause "
                  f"({formater_duree(max(1, round(secondes / 60)))} restantes)")
            continue
        if reste.total_seconds() <= 0:
            detail = "échue (sera annoncée au prochain déclenchement)"
        else:
            secondes = int(reste.total_seconds())
            if secondes < 60:
                detail = f"dans {secondes} s"
            elif secondes < 3 * 3600:
                detail = f"dans {formater_duree(round(secondes / 60))}"
            else:
                detail = ""
        ligne = f"- n° {minuteur['id']} — {quoi} : {formater_echeance(due, ref)}"
        if detail:
            ligne += f" ({detail})"
        print(ligne)
    return 0


def cmd_annuler(args) -> int:
    with verrou_fichier(args.donnees):  # M3 : lire-modifier-écrire d'un bloc.
        etat = charger(args.donnees)
        minuteurs = etat["timers"]
        cible = args.cible.strip()

        if cible.lower() in ("tout", "tous", "all", "everything"):
            supprimes = list(minuteurs)
        elif cible.isdigit():
            supprimes = [m for m in minuteurs
                         if isinstance(m, dict) and m.get("id") == int(cible)]
        else:
            recherche = cible.lower()
            supprimes = [m for m in minuteurs if isinstance(m, dict)
                         and recherche
                         and recherche in str(m.get("label") or "").lower()]
            if len(supprimes) > 1:
                noms = ", ".join(
                    f"n° {m['id']} « {m['label']} »" for m in supprimes)
                print(f"Erreur : plusieurs minuteurs correspondent : {noms}. "
                      "Précisez le numéro.", file=sys.stderr)
                return 1

        if not supprimes:
            noms = ", ".join(
                f"n° {m.get('id')} « {m.get('label') or m.get('kind')} »"
                for m in minuteurs if isinstance(m, dict)) or "aucun"
            print(f"Erreur : aucun minuteur ne correspond à « {cible} » ; "
                  f"en cours : {noms}.", file=sys.stderr)
            return 1

        etat["timers"] = [m for m in minuteurs if m not in supprimes]
        sauvegarder(args.donnees, etat)
    noms = ", ".join(
        f"n° {m.get('id')} « {m.get('label') or m.get('kind')} »"
        if isinstance(m, dict) else "entrée mal formée" for m in supprimes)
    print(f"Annulé : {noms}.")
    return 0


# ---------------------------------------------------------------------------
# Pause, reprise, annulation par numéro (lot U3 : tuiles de l'application)
# ---------------------------------------------------------------------------
# Un minuteur en pause garde le temps qui lui restait (« remaining_s ») et ne
# sonne pas ; à la reprise, l'échéance repart de maintenant. Seuls les
# comptes à rebours se mettent en pause : un rappel à heure fixe s'annule.

def _modifier(chemin: Path, ident: int, action) -> dict | None:
    """Lit, applique `action(minuteur, ref)` au minuteur n° `ident`, écrit —
    sous verrou. `action` retourne False pour ne rien changer. Retourne le
    minuteur modifié (ou retiré), None s'il est introuvable ou inchangé."""
    ref = maintenant()
    with verrou_fichier(chemin):
        etat = charger(chemin)
        for minuteur in etat["timers"]:
            if minuteur.get("id") == ident:
                break
        else:
            return None
        if action(etat, minuteur, ref) is False:
            return None
        sauvegarder(chemin, etat)
    return minuteur


def mettre_en_pause(chemin: Path, ident: int) -> dict | None:
    """Met un compte à rebours en pause (temps restant gardé)."""
    def pause(_etat, minuteur, ref):
        if minuteur.get("kind") != "timer" or minuteur.get("paused"):
            return False
        reste = (echeance(minuteur) - ref).total_seconds()
        if reste <= 0:
            return False  # déjà échu : il va sonner.
        minuteur["paused"] = True
        minuteur["remaining_s"] = round(reste, 1)
    return _modifier(chemin, ident, pause)


def reprendre(chemin: Path, ident: int) -> dict | None:
    """Reprend un minuteur en pause : échéance = maintenant + temps restant ;
    la création est décalée d'autant (la jauge garde sa durée totale)."""
    def reprise(_etat, minuteur, ref):
        if not minuteur.get("paused"):
            return False
        reste = max(1.0, float(minuteur.pop("remaining_s", 0) or 0))
        minuteur.pop("paused", None)
        ancienne = echeance(minuteur)
        due = ref + timedelta(seconds=reste)
        if minuteur.get("created"):
            cree = datetime.fromisoformat(minuteur["created"])
            minuteur["created"] = (cree + (due - ancienne)).isoformat()
        minuteur["due"] = due.isoformat()
    return _modifier(chemin, ident, reprise)


def annuler_numero(chemin: Path, ident: int) -> dict | None:
    """Annule le minuteur n° `ident` (en pause ou non)."""
    def retrait(etat, minuteur, _ref):
        etat["timers"] = [m for m in etat["timers"] if m is not minuteur]
    return _modifier(chemin, ident, retrait)


def cmd_declencher(args) -> int:
    messages = declencher_dus(args.donnees, langue=args.langue)
    if not messages:
        print("Aucun minuteur arrivé à échéance.")
    return 0


def cmd_surveiller(args) -> int:
    # S1 — un seul surveillant par fichier de minuteurs : deux surveillants
    # annonceraient chaque minuteur deux fois. Le verrou est dans le dossier
    # du fichier de minuteurs (data/ par défaut).
    verrou = VerrouInstance("surveillant", Path(args.donnees).parent)
    if not verrou.acquerir():
        print("Le surveillant de minuteurs tourne déjà : celui-ci ne "
              "démarre pas.", flush=True)
        return 0
    debut = maintenant()
    print("Surveillance des minuteurs démarrée "
          f"(vérification toutes les {INTERVALLE_VERIFICATION_S:g} secondes "
          "au plus).", flush=True)
    print("Arrêter avec Ctrl+C.", flush=True)
    # Lot F1 : rien ne doit tuer le surveillant. Une erreur de déclenchement
    # (fichier momentanément illisible, panne imprévue) est signalée — une
    # fois tant qu'elle se répète à l'identique — et la boucle continue.
    derniere_erreur = {"texte": None}

    def _tour(premier: bool) -> None:
        try:
            if premier:
                declencher_dus(args.donnees, debut_surveillance=debut,
                               langue=args.langue)
            else:
                declencher_dus(args.donnees, langue=args.langue)
        except KeyboardInterrupt:
            raise
        except Exception as erreur:  # noqa: BLE001 — le surveillant reste.
            texte = f"{type(erreur).__name__} : {erreur}"
            if texte != derniere_erreur["texte"]:
                signaler("Vérification des minuteurs impossible "
                         f"({texte}) ; nouvel essai dans quelques secondes.")
            derniere_erreur["texte"] = texte
            return
        derniere_erreur["texte"] = None

    def _attente() -> float:
        try:
            etat = charger(args.donnees)
        except Exception:  # noqa: BLE001 — signalé par _tour.
            return INTERVALLE_VERIFICATION_S
        prochaines = []
        for m in etat["timers"]:
            try:
                if not m.get("paused"):
                    prochaines.append(echeance(m))
            except (ValueError, AttributeError):
                continue  # écartée (et signalée) au prochain tour.
        if not prochaines:
            return INTERVALLE_VERIFICATION_S
        return max(0.0, min(INTERVALLE_VERIFICATION_S,
                            (min(prochaines) - maintenant()).total_seconds()))

    try:
        _tour(premier=True)
        while True:
            time.sleep(_attente())
            _tour(premier=False)
    except KeyboardInterrupt:
        print("\nSurveillance arrêtée. Les minuteurs restent enregistrés.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Minuteur local persistant (100 % local, hors ligne).")
    parser.add_argument(
        "--donnees", type=Path, default=None,
        help="Fichier JSON de persistance (défaut : data/timers.json).",
    )
    parser.add_argument(
        "--langue", choices=["fr", "en"], default=None,
        help="Langue des annonces (défaut : celle de config.toml, [boucle] langue).",
    )
    sous = parser.add_subparsers(dest="commande", required=True)

    p_demarrer = sous.add_parser(
        "demarrer", help="Régler un minuteur ou un rappel.")
    p_demarrer.add_argument(
        "--minutes", type=float, default=None,
        help="Compte à rebours en minutes (ex. 40, ou 0.1 pour 6 secondes).")
    p_demarrer.add_argument(
        "--a", default=None,
        help="Rappel à heure fixe : HH:MM (ex. 18:30) ou "
        "AAAA-MM-JJTHH:MM (ex. 2026-11-22T18:30).")
    p_demarrer.add_argument(
        "--etiquette", default="",
        help="Nom du minuteur, en tes mots (ex. « pâtes »).")
    p_demarrer.set_defaults(fonction=cmd_demarrer)

    p_lister = sous.add_parser("lister", help="Lister les minuteurs actifs.")
    p_lister.set_defaults(fonction=cmd_lister)

    p_annuler = sous.add_parser(
        "annuler", help="Annuler un minuteur (numéro, étiquette ou « tout »).")
    p_annuler.add_argument(
        "cible", help="Numéro (n°), bout d'étiquette, ou « tout ».")
    p_annuler.set_defaults(fonction=cmd_annuler)

    p_declencher = sous.add_parser(
        "declencher",
        help="Déclencher une fois les minuteurs échus, puis quitter.")
    p_declencher.set_defaults(fonction=cmd_declencher)

    p_surveiller = sous.add_parser(
        "surveiller",
        help="Surveiller en continu (alarme en arrière-plan, Ctrl+C pour arrêter).")
    p_surveiller.set_defaults(fonction=cmd_surveiller)

    args = parser.parse_args()
    if args.donnees is None:
        args.donnees = chemin_donnees_defaut()
    try:
        return args.fonction(args)
    except FichierIndisponible as erreur:
        # Lot F1 : rien n'a été écrit. Première ligne lue par la boucle
        # vocale (« je n'ai pas pu régler le minuteur : … »).
        print(f"Erreur : fichier des minuteurs indisponible pour l'instant "
              f"({erreur}) ; réessayez.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
