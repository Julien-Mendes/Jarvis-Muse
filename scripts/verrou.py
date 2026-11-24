#!/usr/bin/env python3
"""verrou.py — Verrous de fichier du Jarvis-Muse (bibliothèque, pas un script).

Deux usages, tous deux sans port réseau et sans dépendance :

  - VerrouInstance : « une seule instance ». Un second lancement de la
    boucle vocale, du surveillant de minuteurs ou du lanceur trouve le verrou
    pris et refuse de démarrer (S1). Le verrou est lié au processus : Windows
    le libère tout seul quand le processus se termine, même sur un plantage,
    donc il n'y a jamais de « verrou périmé » à effacer à la main.

Les verrous sont des verrous d'octet du système (msvcrt.locking sous Windows,
fcntl.flock ailleurs) posés sur un petit fichier .lock du dossier data/.

Principe de sûreté : si le verrou lui-même est impossible à créer (dossier
non accessible en écriture, par exemple), on ne bloque pas Jarvis — on
laisse démarrer plutôt que de refuser à tort.
"""

import os
import sys
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
