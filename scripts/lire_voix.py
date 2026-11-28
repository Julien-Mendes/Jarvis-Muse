#!/usr/bin/env python3
"""lire_voix.py — Lire un texte à voix haute avec Piper (TTS 100 % local).

Usage :
    python scripts/lire_voix.py --texte "Bonjour Julien."
    python scripts/lire_voix.py --fichier a-dire/resume.txt
    python scripts/lire_voix.py --texte "Hello." --langue en

Tout se passe sur la machine : aucune donnée ne quitte le poste, aucun appel
réseau. Les voix sont téléchargées une seule fois (voir docs/etape-2-voix.md).

Voix par défaut (décisions du 21 nov. 2026) :
  - français : Piper « upmc » (féminine, UPMC/LIMSI) — choisie le 21 nov. 2026
    (Gilles jugée trop robotique, Tom écartée aussi).
  - anglais : Piper « alan » (masculine britannique) — langue par défaut à
    moyen terme, jusqu'à ce qu'une voix française plus écoutable soit trouvée.
"""

import argparse
import gc
import queue
import re
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

# Modules voisins (config_jarvis.py…) importables même si ce fichier est
# chargé par chemin (tests, importlib) et non lancé comme script.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import config_jarvis  # noqa: E402

# Voix par défaut par langue.
VOIX_DEFAUT = {
    "fr": "fr_FR-upmc-medium",  # Piper, féminine (UPMC/LIMSI) — choisie le 21 nov. 2026.
    "en": "en_GB-alan-medium",   # Piper, masculine britannique.
}
# Noms courts de la configuration ([voix] voix_fr, voix_en) -> voix Piper.
# Un nom complet (« en_GB-alan-medium ») est accepté tel quel.
VOIX_COURTES = {
    "upmc": "fr_FR-upmc-medium",
    "alan": "en_GB-alan-medium",
}


def nom_voix_configure(donnees: dict, langue: str) -> str:
    """Voix Piper de [voix] voix_<langue> (nom court ou complet), sinon la
    voix par défaut de la langue."""
    valeur = str(config_jarvis.section(donnees, "voix").get(
        f"voix_{langue}", "")).strip()
    if not valeur:
        return VOIX_DEFAUT[langue]
    if "-" in valeur or "_" in valeur:
        return valeur
    if valeur.lower() in VOIX_COURTES:
        return VOIX_COURTES[valeur.lower()]
    print(f"Avertissement : voix « {valeur} » inconnue dans [voix] "
          f"voix_{langue} ; voix par défaut utilisée.", file=sys.stderr)
    return VOIX_DEFAUT[langue]


def trouver_modele(dossier_modeles: Path, nom_voix: str):
    """Cherche le modèle .onnx (et son fichier .json) dans le dossier des modèles.

    Le dossier peut être plat ou organisé en sous-dossiers : la recherche est
    récursive pour rester compatible avec la façon dont les voix sont
    téléchargées (voir docs/etape-2-voix.md).
    """
    for chemin in sorted(dossier_modeles.rglob(f"{nom_voix}.onnx")):
        config = chemin.with_suffix(".onnx.json")
        if config.exists():
            return chemin, config
    return None, None


def _synthetiser_avec(voix, texte: str, vitesse: float):
    """Synthétise avec une voix Piper déjà chargée : (fréquence, audio brut)."""
    # Piper : length_scale < 1 = plus rapide, > 1 = plus lent.
    echelle = 1.0 / vitesse
    morceaux = []
    frequence = None
    try:
        # piper-tts récent : length_scale passe par SynthesisConfig
        # (l'appel direct plantait : « unexpected keyword argument
        # 'length_scale' », constaté au premier test le 21 nov. 2026).
        from piper.config import SynthesisConfig

        generateur = voix.synthesize(
            texte, syn_config=SynthesisConfig(length_scale=echelle)
        )
    except (ImportError, TypeError):
        # Ancienne API piper-tts : length_scale en paramètre direct.
        generateur = voix.synthesize(texte, length_scale=echelle)
    for morceau in generateur:
        frequence = morceau.sample_rate
        morceaux.append(morceau.audio_int16_bytes)
    return frequence, b"".join(morceaux)


def synthetiser(texte: str, chemin_modele: Path, chemin_config: Path, vitesse: float):
    """Charge la voix, synthétise le texte et retourne (fréquence, audio brut)."""
    from piper import PiperVoice

    voix = PiperVoice.load(str(chemin_modele), str(chemin_config))
    return _synthetiser_avec(voix, texte, vitesse)


def ecrire_wav(chemin: Path, frequence: int, donnees: bytes) -> None:
    """Écrit l'audio brut (16 bits, mono) dans un fichier WAV."""
    with wave.open(str(chemin), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(frequence)
        wav.writeframes(donnees)


def jouer_wav(chemin_wav: Path, interruption: threading.Event | None = None) -> bool:
    """Joue un fichier WAV sur la sortie audio par défaut (Windows).

    Retourne False si `interruption` a été posé pendant la lecture (la
    lecture est alors coupée net), True sinon.
    """
    if sys.platform != "win32":
        print(f"Fichier audio enregistré : {chemin_wav}")
        print("Lecture automatique disponible seulement sous Windows pour l'instant.")
        return True
    import winsound

    with wave.open(str(chemin_wav), "rb") as wav:
        duree = wav.getnframes() / wav.getframerate()
    winsound.PlaySound(
        str(chemin_wav), winsound.SND_FILENAME | winsound.SND_ASYNC
    )
    # V1 : marge de fin ramenée de 0,5 s à 0,1 s (elle s'ajoutait à chaque
    # lecture : un temps mort audible avant le retour au repos).
    attente = max(0.0, duree + 0.1)
    if interruption is None:
        time.sleep(attente)
        return True
    if interruption.wait(timeout=attente):
        winsound.PlaySound(None, 0)  # coupe la lecture en cours.
        return False
    return True


# ---------------------------------------------------------------------------
# V1 — voix résidente : Piper chargé une seule fois, lecture phrase par phrase
# ---------------------------------------------------------------------------
# Mesuré le 26 nov. 2026 (voix alan, phrase de 5,6 s d'audio) : relancer
# lire_voix.py coûtait ~0,5 s (processus + imports) + 0,8 à 1,3 s (chargement
# du modèle) + 0,4 à 2,4 s (première synthèse après chargement) avant le
# premier son, plus 0,5 s de silence en fin. À chaud, la synthèse d'une phrase
# courte prend ~0,07 s : la voix résidente joue la première phrase pendant que
# les suivantes se synthétisent.

# Fin de phrase : . ! ? … suivis d'un blanc, ou un saut de ligne.
_FIN_PHRASE = re.compile(r"(?<=[.!?\u2026])\s+|\n+")
# Morceau trop court pour être lu seul (« M. », « Dr. ») : collé au suivant.
_MORCEAU_MIN_CARACTERES = 4


def decouper_phrases(texte: str) -> list:
    """Découpe un texte en phrases à lire l'une après l'autre."""
    phrases: list = []
    tampon = ""
    for morceau in _FIN_PHRASE.split(texte.strip()):
        morceau = morceau.strip()
        if not morceau:
            continue
        tampon = f"{tampon} {morceau}" if tampon else morceau
        if len(tampon) >= _MORCEAU_MIN_CARACTERES:
            phrases.append(tampon)
            tampon = ""
    if tampon:
        if phrases:
            phrases[-1] = f"{phrases[-1]} {tampon}"
        else:
            phrases.append(tampon)
    return phrases


class ErreurLecture(Exception):
    """La voix résidente n'a pas pu tout lire. `reste` = texte non encore
    joué : l'appelant qui passe à un autre moyen de lecture ne relit rien."""

    def __init__(self, cause: BaseException, reste: str):
        super().__init__(str(cause) or type(cause).__name__)
        self.cause = cause
        self.reste = reste


class VoixResidente:
    """Voix Piper gardée en mémoire par la boucle vocale (V1).

    Les modèles sont chargés une fois (par voix) puis réutilisés ; `lire`
    synthétise la phrase suivante pendant que la précédente est jouée.
    Utilisable depuis plusieurs fils : chargement et synthèse sont sous verrou.

    Lot L1 (langue du tour) : la voix suit la langue de chaque tour. Mesuré
    le 27 nov. 2026 (working set du processus, Python 3.14, piper-tts 1.8) :
    ~17 Mo à vide, ~183 Mo avec Alan, ~316 à 333 Mo avec Alan + UPMC — au-delà
    du budget de 200 Mo. D'où `max_voix` = 1 par défaut : une voix chargée à
    la demande, cache de la dernière utilisée ; changer de langue décharge
    l'autre (rechargement ~1 à 4 s, préchauffé par la boucle dès que la
    langue du tour est connue).
    """

    MAX_VOIX_DEFAUT = 1

    def __init__(self, dossier_modeles: Path | None = None,
                 donnees: dict | None = None,
                 max_voix: int | None = None):
        racine = Path(__file__).resolve().parent.parent
        self.dossier_modeles = Path(dossier_modeles or (racine / "models"))
        self.donnees = (config_jarvis.charger_donnees()
                        if donnees is None else donnees)
        self.max_voix = max(1, int(max_voix or self.MAX_VOIX_DEFAUT))
        # Ordre = du moins au plus récemment utilisé (dict garde l'ordre).
        self._voix: dict = {}
        self._verrou_chargement = threading.Lock()
        self._verrou_synthese = threading.Lock()

    def charger(self, langue: str, voix: str | None = None):
        """Voix Piper de la langue (chargée au premier appel seulement)."""
        moteur = config_jarvis.section(self.donnees, "voix").get("moteur", "piper")
        if str(moteur).strip().lower() != "piper":
            raise RuntimeError("seul le moteur « piper » est pris en charge "
                               "([voix] moteur)")
        nom = voix or nom_voix_configure(self.donnees, langue)
        with self._verrou_chargement:
            if nom in self._voix:
                self._voix[nom] = self._voix.pop(nom)  # la plus récente.
                return self._voix[nom]
            chemin_modele, chemin_config = trouver_modele(
                self.dossier_modeles, nom)
            if chemin_modele is None:
                raise FileNotFoundError(
                    f"voix « {nom} » introuvable dans {self.dossier_modeles}")
            # Budget mémoire (L1) : décharger d'abord la voix la moins
            # récente, pour ne jamais avoir les deux modèles en même temps.
            while len(self._voix) >= self.max_voix:
                del self._voix[next(iter(self._voix))]
            gc.collect()
            self._voix[nom] = self._charger_modele(chemin_modele,
                                                   chemin_config)
            return self._voix[nom]

    @staticmethod
    def _charger_modele(chemin_modele, chemin_config):
        from piper import PiperVoice

        return PiperVoice.load(str(chemin_modele), str(chemin_config))

    def est_chargee(self, langue: str) -> bool:
        """Vrai si la voix de cette langue est déjà en mémoire."""
        try:
            nom = nom_voix_configure(self.donnees, langue)
        except KeyError:
            return False
        return nom in self.voix_chargees()

    def voix_chargees(self) -> list:
        """Noms des voix en mémoire, de la moins à la plus récente."""
        with self._verrou_chargement:
            return list(self._voix)

    def synthetiser(self, texte: str, langue: str, vitesse: float = 1.0):
        """(fréquence, audio brut) d'un texte, avec la voix résidente."""
        voix = self.charger(langue)
        with self._verrou_synthese:
            return _synthetiser_avec(voix, texte, vitesse)

    def prechauffer(self, langue: str, vitesse: float = 1.0) -> bool:
        """Charge la voix et fait la première synthèse (la plus lente) à
        l'avance. Ne lève jamais : False si la voix est indisponible."""
        try:
            self.synthetiser("OK.", langue, vitesse)
            return True
        except Exception as erreur:  # noqa: BLE001 — repli géré par l'appelant.
            print(f"Voix résidente non préchargée ({erreur}) ; nouvel essai "
                  "à la première réponse.", file=sys.stderr)
            return False

    def lire(self, texte: str, langue: str, vitesse: float = 1.0,
             interruption: threading.Event | None = None,
             au_premier_son=None) -> bool:
        """Lit le texte phrase par phrase. True = lu jusqu'au bout, False =
        interrompu. Lève ErreurLecture (avec le texte non joué) si la synthèse
        ou la lecture échoue. `au_premier_son()` est appelé juste avant que
        la première phrase soit jouée (mesure de latence)."""
        phrases = decouper_phrases(texte)
        if not phrases:
            return True
        file: queue.Queue = queue.Queue(maxsize=2)
        arret = threading.Event()

        def deposer(element) -> bool:
            while not arret.is_set():
                try:
                    file.put(element, timeout=0.1)
                    return True
                except queue.Full:
                    continue
            return False

        def produire():
            for indice, phrase in enumerate(phrases):
                if arret.is_set():
                    return
                try:
                    resultat = self.synthetiser(phrase, langue, vitesse)
                except BaseException as erreur:  # noqa: BLE001
                    deposer(("erreur", indice, erreur))
                    return
                if not deposer(("audio", indice, resultat)):
                    return
            deposer(("fin", len(phrases), None))

        threading.Thread(target=produire, daemon=True).start()
        premier = True
        try:
            while True:
                try:
                    nature, indice, contenu = file.get(timeout=0.1)
                except queue.Empty:
                    if interruption is not None and interruption.is_set():
                        return False
                    continue
                if nature == "fin":
                    return True
                if nature == "erreur":
                    raise ErreurLecture(contenu, " ".join(phrases[indice:]))
                if interruption is not None and interruption.is_set():
                    return False
                frequence, audio = contenu
                if not audio:
                    continue
                with tempfile.NamedTemporaryFile(suffix=".wav",
                                                 delete=False) as tmp:
                    chemin_tmp = Path(tmp.name)
                try:
                    try:
                        ecrire_wav(chemin_tmp, frequence, audio)
                        if premier and au_premier_son is not None:
                            au_premier_son()
                        premier = False
                        complet = jouer_wav(chemin_tmp, interruption)
                    except Exception as erreur:  # noqa: BLE001
                        raise ErreurLecture(
                            erreur, " ".join(phrases[indice:])) from erreur
                    if not complet:
                        return False
                finally:
                    chemin_tmp.unlink(missing_ok=True)
        finally:
            arret.set()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lit un texte à voix haute avec Piper (TTS local, hors ligne)."
    )
    groupe = parser.add_mutually_exclusive_group(required=True)
    groupe.add_argument("--texte", help="Texte à lire à voix haute.")
    groupe.add_argument("--fichier", help="Fichier texte (.txt) à lire à voix haute.")
    parser.add_argument(
        "--langue", choices=["fr", "en"], default=None,
        help="Langue du texte (défaut : celle de la configuration, "
        "[general] langue ; en par défaut, décision 21 nov. 2026).",
    )
    parser.add_argument(
        "--voix", default=None,
        help="Nom de la voix Piper (défaut : fr_FR-upmc-medium en fr, "
        "en_GB-alan-medium en en).",
    )
    parser.add_argument(
        "--vitesse", type=float, default=None,
        help="Vitesse de lecture, 0.5 à 2.0 (défaut : [voix] vitesse de la "
        "configuration, 1.0 sinon).",
    )
    parser.add_argument(
        "--dossier-modeles", type=Path, default=None,
        help="Dossier des voix téléchargées (défaut : models/ à la racine du dépôt).",
    )
    parser.add_argument(
        "--sortie", type=Path, default=None,
        help="Enregistrer l'audio dans ce fichier .wav au lieu de le jouer.",
    )
    args = parser.parse_args()

    # Configuration (K1) : langue, voix, vitesse, moteur.
    donnees = config_jarvis.charger_donnees()
    voix_cfg = config_jarvis.section(donnees, "voix")
    if str(voix_cfg.get("moteur", "piper")).strip().lower() != "piper":
        print("Erreur : seul le moteur « piper » est pris en charge "
              "([voix] moteur).", file=sys.stderr)
        return 1
    if args.langue is None:
        args.langue = config_jarvis.langue(donnees)
    if args.vitesse is None:
        args.vitesse = config_jarvis.nombre_borne(
            voix_cfg.get("vitesse", 1.0), 0.5, 2.0, 1.0)
    if not 0.5 <= args.vitesse <= 2.0:
        print("Erreur : --vitesse doit être entre 0.5 et 2.0.", file=sys.stderr)
        return 1

    # Texte à lire.
    if args.fichier:
        chemin_texte = Path(args.fichier)
        if not chemin_texte.exists():
            print(f"Erreur : fichier introuvable : {chemin_texte}", file=sys.stderr)
            return 1
        texte = chemin_texte.read_text(encoding="utf-8").strip()
    else:
        texte = args.texte.strip()
    if not texte:
        print("Erreur : le texte à lire est vide.", file=sys.stderr)
        return 1

    # Voix à utiliser.
    nom_voix = args.voix or nom_voix_configure(donnees, args.langue)
    racine = Path(__file__).resolve().parent.parent
    dossier_modeles = args.dossier_modeles or (racine / "models")
    chemin_modele, chemin_config = trouver_modele(dossier_modeles, nom_voix)
    if chemin_modele is None:
        print(f"Erreur : voix « {nom_voix} » introuvable dans {dossier_modeles}.",
              file=sys.stderr)
        print("Téléchargez-la avec :", file=sys.stderr)
        print(f"  python -m piper.download_voices {nom_voix} "
              f"--data-dir {dossier_modeles}", file=sys.stderr)
        print("Voir docs/etape-2-voix.md pour les détails.", file=sys.stderr)
        return 2

    # Synthèse.
    try:
        frequence, donnees = synthetiser(texte, chemin_modele, chemin_config,
                                         args.vitesse)
    except ImportError:
        print("Erreur : le module piper n'est pas installé.", file=sys.stderr)
        print("Installez-le avec :", file=sys.stderr)
        print("  pip install -r scripts/requirements-etape2.txt", file=sys.stderr)
        return 3
    if not donnees:
        print("Erreur : la synthèse n'a produit aucun audio.", file=sys.stderr)
        return 1

    # Lecture (ou enregistrement).
    if args.sortie:
        ecrire_wav(args.sortie, frequence, donnees)
        print(f"Audio enregistré : {args.sortie}")
    else:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            chemin_tmp = Path(tmp.name)
        try:
            ecrire_wav(chemin_tmp, frequence, donnees)
            print(f"Lecture avec la voix « {nom_voix} » ({args.langue})…")
            jouer_wav(chemin_tmp)
        finally:
            chemin_tmp.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
