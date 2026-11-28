"""Lot L1 — langue détectée à chaque tour (français ou anglais).

Jusqu'au lot L1, la langue était verrouillée sur [general] langue : Whisper
était forcé sur cette langue et Jarvis répondait toujours dans celle-ci.
Désormais, chaque tour a sa langue :

1. Tour vocal : la langue détectée par Whisper (Groq ou faster-whisper),
   si c'est « fr » ou « en » et que la détection est sûre ;
2. sinon (ou pour un tour tapé) : une détection sur le texte transcrit,
   par mots-outils propres à chaque langue et accents français ;
3. si la détection reste incertaine : repli sur la langue de la config.

La langue du tour fait suivre tout le reste : prompt système et outils du
cerveau, textes prononcés, voix (Alan / UPMC), interface (champ « langue »
de data/hud-state.json) et annonces de minuteur pendant le tour.

Aucune dépendance : bibliothèque standard seulement. Rien n'est envoyé
nulle part — la détection sur le texte est purement locale.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

LANGUES = ("fr", "en")

# Noms de langue renvoyés par Whisper (Groq verbose_json donne « English »,
# « French » ; faster-whisper donne les codes « en », « fr »).
_NOMS_WHISPER = {
    "fr": "fr", "french": "fr", "français": "fr", "francais": "fr",
    "en": "en", "english": "en", "anglais": "en",
}

# Probabilité minimale (faster-whisper) pour croire la langue détectée.
SEUIL_WHISPER = 0.6

# Mots-outils et mots fréquents des demandes à Jarvis, propres à une langue.
# Exclus volontairement, car ambigus entre les deux langues : « a » (il a /
# a timer — et piège déjà connu des mots-nombres), « on », « me », « son »,
# « plus », « minutes », « note », « page », « messages », « date »,
# « ok », « google », « youtube »…
MOTS_FR = frozenset("""
    je j tu il elle nous vous ils elles le la les l un une des du de d au aux
    et ou est sont suis es c ce cet cette ces ça ca qu que qui quoi quel
    quelle quels quelles pour par pas ne n mon ma mes ton ta tes sa ses
    notre votre leur dans sur sous avec sans chez peux peut veux voudrais
    fais fait mets ouvre ouvrir regarde regarder cherche chercher
    lance lancer ferme fermer dis dit donne montre lis lire garde
    minuteur rappel rappelle rappelle-moi heure heures seconde secondes
    merci bonjour bonsoir salut oui non ouais d'accord comment pourquoi
    combien quand où ou alors aussi très tres bien rien tout tous
    est-ce qu'est-ce s'il plait plaît moi toi lui écran ecran recherche
    connaissances dernière derniere quelque chose
""".split())

MOTS_EN = frozenset("""
    i i'm i'd i'll you you're your yours he she we they it it's its the
    is are am was were be been do does did don't doesn't can can't could
    would will won't should what what's which who whom whose why how when
    where this that these those there here my mine our their his her
    of to for from with without about into onto at by and or but not
    please set open look search find start close tell say give show read
    keep remind reminder timer hour hours seconds thanks thank
    hello hi hey yes yeah yep nope okay anything something
    screen research last just also very well nothing everything
""".split())

_ACCENTS_FR = re.compile(r"[éèêëàâîïôûùüçœ]")
_MOT = re.compile(r"[a-zàâçéèêëîïôûùüœ]+(?:['’-][a-zàâçéèêëîïôûùüœ]+)*")


def normaliser_whisper(nom) -> str | None:
    """« French », « fr »… → « fr » ; None si la langue n'est ni fr ni en."""
    if not nom:
        return None
    return _NOMS_WHISPER.get(str(nom).strip().lower())


def scores_texte(texte: str) -> tuple[int, int]:
    """(score français, score anglais) d'un texte."""
    texte = (texte or "").lower().replace("’", "'")
    fr = en = 0
    for mot in _MOT.findall(texte):
        # « qu'est-ce », « s'il », « i'm » : le mot entier, puis ses morceaux.
        morceaux = {mot, *re.split(r"['-]", mot)}
        if morceaux & MOTS_FR:
            fr += 1
        elif morceaux & MOTS_EN:
            en += 1
    if _ACCENTS_FR.search(texte):
        fr += 1
    return fr, en


def detecter_texte(texte: str) -> str | None:
    """Langue d'un texte (« fr » / « en ») ; None si incertaine.

    Sûre quand une seule langue a des indices, ou quand l'une en a au moins
    deux fois plus que l'autre. Sinon (aucun indice, égalité, mélange) :
    None, et l'appelant se replie sur la langue de la config.
    """
    fr, en = scores_texte(texte)
    if fr == en:
        return None
    if en == 0:
        return "fr"
    if fr == 0:
        return "en"
    if fr >= 2 * en:
        return "fr"
    if en >= 2 * fr:
        return "en"
    return None


def langue_du_tour(texte: str, langue_config: str,
                   langue_whisper=None, probabilite: float | None = None,
                   auto: bool = True) -> str:
    """Langue du tour, « fr » ou « en » — jamais autre chose.

    `langue_whisper` : langue détectée par Whisper sur l'audio (None pour un
    tour tapé) ; `probabilite` : sa confiance si le moteur la donne (Groq ne
    la donne pas : on lui fait alors confiance). `auto=False` ([general]
    langue_auto = false) : la langue de la config, comme avant L1.
    """
    repli = langue_config if langue_config in LANGUES else "en"
    if not auto:
        return repli
    depuis_audio = normaliser_whisper(langue_whisper)
    if depuis_audio and (probabilite is None
                         or probabilite >= SEUIL_WHISPER):
        return depuis_audio
    return detecter_texte(texte) or repli


# ---------------------------------------------------------------------------
# Langue du tour en cours, lue par les autres processus (surveillant des
# minuteurs) dans data/hud-state.json, que la boucle écrit déjà.
# ---------------------------------------------------------------------------

ETATS_TOUR_ACTIF = ("reflexion", "reponse")
# Un tour actif plus vieux que ceci est un fichier abandonné (boucle tuée).
FRAICHEUR_TOUR_ACTIF_S = 300.0
# Juste après la réponse, la conversation est encore « en cours ».
FRAICHEUR_APRES_TOUR_S = 30.0


def langue_tour_en_cours(chemin_etat: Path,
                         maintenant: datetime | None = None) -> str | None:
    """Langue du tour en cours selon data/hud-state.json ; None s'il n'y a
    pas de tour en cours (ou fichier absent, illisible, périmé)."""
    try:
        donnees = json.loads(Path(chemin_etat).read_text(encoding="utf-8"))
        langue = donnees.get("langue")
        if langue not in LANGUES:
            return None
        horodatage = datetime.fromisoformat(str(donnees["horodatage"]))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    maintenant = maintenant or datetime.now(horodatage.tzinfo)
    try:
        age = (maintenant - horodatage).total_seconds()
    except TypeError:  # l'un avec fuseau, l'autre sans.
        return None
    if age < -5:
        return None
    limite = (FRAICHEUR_TOUR_ACTIF_S
              if donnees.get("etat") in ETATS_TOUR_ACTIF
              else FRAICHEUR_APRES_TOUR_S)
    return langue if age <= limite else None


def langue_annonce_minuteur(langue_config: str,
                            langue_tour: str | None) -> str:
    """Décision Q7 + L1 : les annonces de minuteur suivent la config, sauf
    si le tour en cours est dans l'autre langue — elles suivent alors le
    tour."""
    if langue_tour in LANGUES and langue_tour != langue_config:
        return langue_tour
    return langue_config
