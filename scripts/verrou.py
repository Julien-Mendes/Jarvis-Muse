#!/usr/bin/env python3
"""verrou.py — Verrous de fichier du Jarvis-Muse (bibliothèque, pas un script).

Trois usages, tous sans port réseau et sans dépendance :

  - VerrouInstance : « une seule instance ». Un second lancement de la
    boucle vocale, du surveillant de minuteurs ou du lanceur trouve le verrou
    pris et refuse de démarrer (S1). Le verrou est lié au processus : Windows
    le libère tout seul quand le processus se termine, même sur un plantage,
    donc il n'y a jamais de « verrou périmé » à effacer à la main.

  - verrou_fichier : verrou court autour d'un « lire, modifier, écrire »
    d'un fichier partagé entre processus (data/timers.json, écrit par la
    boucle, le surveillant et la ligne de commande). Sans lui, deux
    processus qui écrivent en même temps peuvent perdre un minuteur (M3).

Les verrous sont des verrous d'octet du système (msvcrt.locking sous Windows,
fcntl.flock ailleurs) posés sur un petit fichier .lock du dossier data/.

Principe de sûreté : si le verrou lui-même est impossible à créer (dossier
non accessible en écriture, par exemple), on ne bloque pas Jarvis — on
laisse démarrer plutôt que de refuser à tort.
"""

import contextlib
import os
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _verrouiller(fichier) -> bool:
    """Pose un verrou exclusif non bloquant sur le fichier ; False si pris."""
    if sys.platform == "win32":
        import msvcrt

        fichier.seek(0)
        try:
            msvcrt.locking(fichier.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(fichier.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _deverrouiller(fichier) -> None:
    """Libère le verrou (sans jamais échouer)."""
    try:
        if sys.platform == "win32":
            import msvcrt

            fichier.seek(0)
            msvcrt.locking(fichier.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fichier.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


class VerrouInstance:
    """Verrou « une seule instance » identifié par un nom.

    Usage :
        verrou = VerrouInstance("boucle")
        if not verrou.acquerir():
            ...  # une autre instance tourne déjà : ne pas démarrer
        # garder la référence `verrou` vivante jusqu'à la fin du programme.
    """

    def __init__(self, nom: str, dossier: Path | None = None):
        self.nom = nom
        self.dossier = Path(dossier) if dossier else RACINE / "data"
        self.chemin = self.dossier / f"{nom}.lock"
        self._fichier = None

    def acquerir(self) -> bool:
        """True si ce processus est la seule instance (ou si le verrou est
        impossible à créer) ; False si une autre instance tient le verrou."""
        if self._fichier is not None:
            return True
        try:
            self.dossier.mkdir(parents=True, exist_ok=True)
            fichier = open(self.chemin, "a+b")
        except OSError:
            return True  # Sûreté : ne pas refuser à tort.
        if not _verrouiller(fichier):
            fichier.close()
            return False
        try:
            fichier.seek(0)
            fichier.truncate()
            fichier.write(str(os.getpid()).encode("ascii"))
            fichier.flush()
        except OSError:
            pass
        self._fichier = fichier
        return True

    def liberer(self) -> None:
        """Libère le verrou (sans jamais échouer). Optionnel : le système le
        libère de toute façon à la fin du processus."""
        if self._fichier is None:
            return
        _deverrouiller(self._fichier)
        try:
            self._fichier.close()
        except OSError:
            pass
        self._fichier = None


@contextlib.contextmanager
def verrou_fichier(chemin: Path, delai: float = 5.0, pas: float = 0.05):
    """Verrou exclusif court autour de la modification d'un fichier partagé.

    Usage :
        with verrou_fichier(chemin):
            etat = charger(chemin)   # lire
            ...                      # modifier
            sauvegarder(chemin, etat)  # écrire

    Le verrou est posé sur `<fichier>.lock` (le fichier lui-même est
    remplacé à chaque écriture, il ne peut donc pas servir de support).
    On attend au plus `delai` secondes ; passé ce délai, ou si le fichier
    de verrou est impossible à créer, on continue SANS verrou plutôt que de
    figer Jarvis (avertissement sur la sortie d'erreur). Valeur produite :
    True si le verrou est tenu, False sinon.
    """
    chemin = Path(chemin)
    verrou = chemin.with_name(chemin.name + ".lock")
    try:
        verrou.parent.mkdir(parents=True, exist_ok=True)
        fichier = open(verrou, "a+b")
    except OSError:
        yield False
        return
    pris = False
    fin = time.monotonic() + delai
    try:
        while True:
            if _verrouiller(fichier):
                pris = True
                break
            if time.monotonic() >= fin:
                print(f"Avertissement : verrou de {chemin.name} non obtenu "
                      f"après {delai:g} s ; on continue sans verrou.",
                      file=sys.stderr)
                break
            time.sleep(pas)
        yield pris
    finally:
        if pris:
            _deverrouiller(fichier)
        try:
            fichier.close()
        except OSError:
            pass
