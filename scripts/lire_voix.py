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
import sys
import tempfile
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


def synthetiser(texte: str, chemin_modele: Path, chemin_config: Path, vitesse: float):
    """Synthétise le texte et retourne (fréquence d'échantillonnage, audio brut)."""
    from piper import PiperVoice

    voix = PiperVoice.load(str(chemin_modele), str(chemin_config))
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


def ecrire_wav(chemin: Path, frequence: int, donnees: bytes) -> None:
    """Écrit l'audio brut (16 bits, mono) dans un fichier WAV."""
    with wave.open(str(chemin), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(frequence)
        wav.writeframes(donnees)


def jouer_wav(chemin_wav: Path) -> None:
    """Joue un fichier WAV sur la sortie audio par défaut (Windows)."""
    if sys.platform != "win32":
        print(f"Fichier audio enregistré : {chemin_wav}")
        print("Lecture automatique disponible seulement sous Windows pour l'instant.")
        return
    import winsound

    with wave.open(str(chemin_wav), "rb") as wav:
        duree = wav.getnframes() / wav.getframerate()
    winsound.PlaySound(
        str(chemin_wav), winsound.SND_FILENAME | winsound.SND_ASYNC
    )
    time.sleep(duree + 0.5)  # Laisser le temps à la lecture de se terminer.


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
