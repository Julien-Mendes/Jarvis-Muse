#!/usr/bin/env python3
"""lancer_app.py — Lanceur de session Jarvis sans console (étape 7.1).

Lance l'application (scripts/app.py) et la boucle vocale
(scripts/boucle_voix.py), plus le surveillant de minuteurs
(scripts/minuteur.py surveiller) — sans aucune fenêtre console
(conçu pour être lancé par pythonw.exe, ex. via le raccourci
« Jarvis » du menu Démarrer créé par scripts/installer_raccourci.ps1).

Fonctionnement :
  1. Démarre le surveillant de minuteurs en arrière-plan (il annonce
     les minuteurs manqués au démarrage).
  2. Démarre la boucle vocale en arrière-plan (F9 ou bouton micro pour
     parler, champ de saisie dans l'application pour écrire).
  3. Annonce « Jarvis prêt. » à voix haute (sans attendre).
  4. Lance l'application au premier plan et attend qu'elle se ferme.
  5. Pendant la session, relance le surveillant de minuteurs s'il meurt
     (lot F1 ; après 3 échecs rapprochés : fenêtre d'avertissement et plus
     de relance).
  6. À la fermeture de l'application : arrête la boucle et le
     surveillant, puis quitte. Fermer la fenêtre Jarvis arrête donc
     toute la session — comme le raccourci du dépôt B, où fermer le HUD
     quitte Jarvis.

Différence avec scripts/lancer_session.ps1 : la session complète lit
aussi les résumés Carson (a-dire/) et annonce les minuteurs du jour —
ce lanceur ne le fait pas, il se concentre sur application + boucle.
Pour la session complète, utilisez lancer_session.ps1.

Les sorties des processus sont redirigées vers logs/ (gitignoré) :
logs/lancer-app.log (ce lanceur), logs/boucle.log (boucle vocale),
logs/app.log (application), logs/minuteur-surveillant.log. En cas
d'échec au démarrage (ex. CustomTkinter absent), un message Windows
s'affiche et le détail est dans logs/lancer-app.log.

Usage :
    pythonw scripts/lancer_app.py
    python scripts/lancer_app.py --verifier
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# Modules voisins importables même si ce fichier est chargé par chemin.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import config_jarvis  # noqa: E402
from verrou import VerrouInstance  # noqa: E402

PHRASES_PRET = {"fr": "Jarvis prêt.", "en": "Jarvis ready."}


def langue_active() -> str:
    """Langue active (« fr » ou « en ») : [general] langue, comme la boucle."""
    try:
        langue = config_jarvis.langue()
    except Exception:
        return "en"
    return langue if langue in PHRASES_PRET else "en"


def phrase_pret(langue: str) -> str:
    """Phrase d'annonce de démarrage, dans la langue active."""
    return PHRASES_PRET.get(langue, PHRASES_PRET["en"])
SCRIPT_APP = RACINE / "scripts" / "app.py"
SCRIPT_BOUCLE = RACINE / "scripts" / "boucle_voix.py"
SCRIPT_MINUTEUR = RACINE / "scripts" / "minuteur.py"
SCRIPT_VOIX = RACINE / "scripts" / "lire_voix.py"
DOSSIER_LOGS = RACINE / "logs"
FICHIER_JOURNAL = DOSSIER_LOGS / "lancer-app.log"


def journal(message: str) -> None:
    """Écrit une ligne horodatée dans logs/lancer-app.log (sans jamais
    échouer : le lanceur ne doit pas planter pour son journal)."""
    try:
        DOSSIER_LOGS.mkdir(parents=True, exist_ok=True)
        horodatage = time.strftime("%Y-%m-%d %H:%M:%S")
        with FICHIER_JOURNAL.open("a", encoding="utf-8") as f:
            f.write(f"[{horodatage}] {message}\n")
    except OSError:
        pass


def trouver_python(racine: Path) -> tuple:
    """Retourne (python, pythonw) : l'environnement virtuel d'abord,
    sinon le Python du PATH (pythonw peut être absent — None alors)."""
    import shutil

    venv = racine / ".venv" / "Scripts"
    python = venv / "python.exe"
    pythonw = venv / "pythonw.exe"
    if python.exists():
        return (str(python),
                str(pythonw) if pythonw.exists() else None)
    return (shutil.which("python") or "python",
            shutil.which("pythonw"))


def demarrer(nom: str, commande: list, fichier_log: str):
    """Démarre un processus en arrière-plan, sorties vers logs/.

    Retourne l'objet Popen, ou None si le démarrage échoue.
    """
    try:
        DOSSIER_LOGS.mkdir(parents=True, exist_ok=True)
        sortie = (DOSSIER_LOGS / fichier_log).open("a", encoding="utf-8")
        # UTF-8 forcé pour les enfants : sous Windows, leur sortie
        # redirigée vers un fichier hérite sinon du codage cp1252, qui
        # plante sur les émojis (ex. 🎙️ dans boucle_voix.py).
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        processus = subprocess.Popen(
            commande, cwd=str(RACINE), stdout=sortie,
            stderr=subprocess.STDOUT, env=env)
        journal(f"{nom} démarré (pid {processus.pid}).")
        return processus
    except OSError as erreur:
        journal(f"Échec du démarrage de {nom} : {erreur}")
        return None


def arreter(nom: str, processus) -> None:
    """Arrête un processus proprement (terminate, puis kill après 5 s)."""
    if processus is None:
        return
    try:
        if processus.poll() is None:
            processus.terminate()
            try:
                processus.wait(timeout=5)
            except subprocess.TimeoutExpired:
                processus.kill()
                processus.wait()
            journal(f"{nom} arrêté.")
    except Exception as erreur:  # noqa: BLE001 - ne jamais planter ici.
        journal(f"Arrêt de {nom} : {erreur}")


def avertir_windows(message: str) -> None:
    """Affiche un message Windows (boîte de dialogue), sans jamais échouer."""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "Jarvis", 0x10)
    except Exception:
        pass


def avertir_windows_sans_bloquer(message: str) -> None:
    """Comme avertir_windows, dans un fil : le lanceur continue de surveiller
    la fenêtre Jarvis pendant que la boîte de dialogue est ouverte."""
    import threading

    threading.Thread(target=avertir_windows, args=(message,),
                     daemon=True).start()


# Lot F1 — relance du surveillant de minuteurs. Mort en cours de session, il
# est relancé (chaque relance est journalisée). Après MAX_ECHECS_RAPPROCHES
# morts en FENETRE_ECHECS_S, Julien est averti par une fenêtre Windows et les
# relances s'arrêtent (un surveillant qui meurt aussitôt ne doit pas tourner
# en boucle). Une sortie avec le code 0 n'est pas un échec : un autre
# surveillant tient déjà le verrou (session complète, lancer_session.ps1).
MAX_ECHECS_RAPPROCHES = 3
FENETRE_ECHECS_S = 600.0
INTERVALLE_SURVEILLANCE_S = 2.0


class RelanceSurveillant:
    """Garde le surveillant de minuteurs en vie pendant la session.

    `fabrique()` démarre le processus (objet Popen, ou None si le démarrage
    échoue). `verifier()` est appelé régulièrement par le lanceur.
    """

    def __init__(self, fabrique, max_echecs: int = MAX_ECHECS_RAPPROCHES,
                 fenetre_s: float = FENETRE_ECHECS_S,
                 horloge=time.monotonic, avertir=None):
        self.fabrique = fabrique
        self.max_echecs = int(max_echecs)
        self.fenetre_s = float(fenetre_s)
        self.horloge = horloge
        self.avertir = avertir or avertir_windows_sans_bloquer
        self.processus = None
        self.echecs: list = []
        self.abandonne = False
        self.termine = False

    def demarrer(self) -> None:
        self.processus = self.fabrique()
        if self.processus is None:
            self._echec("démarrage impossible")

    def _echec(self, raison: str) -> None:
        maintenant = self.horloge()
        self.echecs = [t for t in self.echecs
                       if maintenant - t < self.fenetre_s] + [maintenant]
        if len(self.echecs) >= self.max_echecs:
            self.abandonne = True
            self.processus = None
            journal(f"Surveillant de minuteurs : {raison} — "
                    f"{len(self.echecs)} échecs en moins de "
                    f"{self.fenetre_s / 60:g} min, relances arrêtées.")
            self.avertir(
                "Le surveillant de minuteurs de Jarvis s'est arrêté "
                f"{len(self.echecs)} fois de suite : les alarmes ne sonneront "
                "plus pendant cette session.\n"
                "Voir logs/minuteur-surveillant.log et logs/minuteurs.log, "
                "puis relancez Jarvis.")
            return
        journal(f"Surveillant de minuteurs : {raison} — relance "
                f"({len(self.echecs)}/{self.max_echecs}).")
        self.processus = self.fabrique()
        if self.processus is None:
            self._echec("relance impossible")

    def verifier(self) -> None:
        """Relance le surveillant s'il est mort (rien d'autre)."""
        if self.abandonne or self.termine:
            return
        if self.processus is None:
            self._echec("absent")
            return
        try:
            code = self.processus.poll()
        except Exception as erreur:  # noqa: BLE001 — jamais planter ici.
            journal(f"Surveillant de minuteurs : état illisible ({erreur}).")
            return
        if code is None:
            return
        if code == 0:
            self.termine = True
            journal("Surveillant de minuteurs terminé normalement (code 0, "
                    "un autre surveillant tourne sans doute déjà) : "
                    "pas de relance.")
            return
        self._echec(f"arrêté avec le code {code}")


def verifier(python: str, pythonw: str | None) -> int:
    """Vérifie que le lancement est possible, puis affiche un bilan."""
    print("Vérification du lanceur Jarvis (étape 7.1) :")
    problemes = []

    def ligne(ok: bool, nom: str, detail: str = ""):
        marque = "OK     " if ok else "MANQUANT"
        print(f"  [{marque}] {nom}" + (f" — {detail}" if detail else ""))
        if not ok:
            problemes.append(nom)

    ligne(Path(python).exists() or python == "python",
          "Python", python)
    ligne(pythonw is not None, "pythonw (sans console)",
          pythonw or "introuvable — le lanceur utilisera python "
          "(fenêtre console visible)")
    ligne(SCRIPT_APP.exists(), "scripts/app.py")
    ligne(SCRIPT_BOUCLE.exists(), "scripts/boucle_voix.py")
    ligne(SCRIPT_MINUTEUR.exists(), "scripts/minuteur.py")
    try:
        resultat = subprocess.run(
            [sys.executable, "-c", "import customtkinter"],
            capture_output=True, timeout=30)
        ligne(resultat.returncode == 0, "CustomTkinter",
              "pip install -r scripts/requirements-etape7.txt"
              if resultat.returncode != 0 else "")
    except (OSError, subprocess.TimeoutExpired) as erreur:
        ligne(False, "CustomTkinter", str(erreur))
    try:
        DOSSIER_LOGS.mkdir(parents=True, exist_ok=True)
        import os

        ligne(os.access(DOSSIER_LOGS, os.W_OK), "dossier logs/ en écriture")
    except OSError as erreur:
        ligne(False, "dossier logs/ en écriture", str(erreur))
    print()
    if problemes:
        print(f"{len(problemes)} élément(s) à régler : "
              + ", ".join(problemes) + ".")
        return 1
    print("Tout est en place. Lancez la session sans console avec :")
    print("  pythonw scripts\\lancer_app.py")
    print("Ou créez le raccourci du menu Démarrer :")
    print("  powershell -ExecutionPolicy Bypass -File "
          "scripts\\installer_raccourci.ps1")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lanceur de session Jarvis sans console — application "
                    "+ boucle vocale + surveillant de minuteurs.")
    parser.add_argument(
        "--verifier", action="store_true",
        help="Vérifier que le lancement est possible, puis quitter.")
    args = parser.parse_args()

    python, pythonw = trouver_python(RACINE)
    # pythonw pour les processus d'arrière-plan (sans console) ; python
    # pour l'application si pythonw est absent (fenêtre console visible).
    interpreteur_fond = pythonw or python

    if args.verifier:
        return verifier(python, pythonw)

    # S1 — une seule session Jarvis : un second clic sur le raccourci ne doit
    # pas démarrer une deuxième boucle ni une deuxième fenêtre.
    verrou_session = VerrouInstance("lancer-app", RACINE / "data")
    if not verrou_session.acquerir():
        journal("Jarvis est déjà lancé : second lancement ignoré.")
        avertir_windows("Jarvis est déjà lancé.\n"
                        "Cherchez sa fenêtre (barre des tâches).")
        return 0
    journal("Lancement de la session Jarvis (sans console).")
    # Lot F1 : le surveillant est relancé s'il meurt en cours de session.
    relance = RelanceSurveillant(lambda: demarrer(
        "surveillant de minuteurs",
        [interpreteur_fond, str(SCRIPT_MINUTEUR), "surveiller"],
        "minuteur-surveillant.log"))
    relance.demarrer()
    boucle = demarrer(
        "boucle vocale",
        [interpreteur_fond, str(SCRIPT_BOUCLE)],
        "boucle.log")
    if boucle is None:
        avertir_windows(
            "Jarvis n'a pas pu démarrer la boucle vocale.\n"
            "Voir logs/lancer-app.log pour le détail.")
        arreter("surveillant de minuteurs", relance.processus)
        return 1
    # Annonce de démarrage (sans attendre : la voix joue en arrière-plan),
    # dans la langue active de la configuration (F3).
    langue = langue_active()
    try:
        subprocess.Popen(
            [python, str(SCRIPT_VOIX), "--texte", phrase_pret(langue),
             "--langue", langue],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass
    application = demarrer(
        "application",
        [interpreteur_fond, str(SCRIPT_APP)],
        "app.log")
    if application is None:
        avertir_windows(
            "Jarvis n'a pas pu ouvrir sa fenêtre.\n"
            "Voir logs/lancer-app.log pour le détail.")
        arreter("boucle vocale", boucle)
        arreter("surveillant de minuteurs", relance.processus)
        return 1
    # Attendre la fermeture de la fenêtre : elle arrête la session. En
    # attendant, le surveillant de minuteurs est relancé s'il meurt (F1).
    try:
        while True:
            try:
                code = application.wait(timeout=INTERVALLE_SURVEILLANCE_S)
                break
            except subprocess.TimeoutExpired:
                relance.verifier()
    except KeyboardInterrupt:
        code = 0
    if code != 0:
        journal(f"L'application s'est fermée avec le code {code} "
                "(voir logs/app.log).")
        avertir_windows(
            "La fenêtre Jarvis s'est fermée avec une erreur.\n"
            "Voir logs/app.log pour le détail.")
    arreter("boucle vocale", boucle)
    arreter("surveillant de minuteurs", relance.processus)
    journal("Session terminée.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
