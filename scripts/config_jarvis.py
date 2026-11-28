#!/usr/bin/env python3
"""config_jarvis.py — Configuration unique du Jarvis-Muse (bibliothèque).

Tous les scripts (boucle vocale, application, minuteur, yeux, navigateur,
voix, lanceurs) lisent la configuration ICI, pas chacun de leur côté (K1).

Trois couches, de la plus faible à la plus forte :

  1. config/config.example.toml — publique, versionnée : les valeurs par
     défaut du projet.
  2. config/config.toml         — copie personnelle (gitignorée) : vos choix.
  3. config/config.local.toml   — privée (gitignorée) : comptes, chemins de
     la machine, applications du lancement de session, quadrants.

Les sections sont fusionnées clé par clé : une clé absente de la couche
supérieure retombe sur la couche inférieure. Les secrets (clés API) ne sont
jamais dans ces fichiers : ils vivent dans .env (charger_env), gitignoré.

La langue est UNE seule : [general] langue. Compatibilité : une ancienne
copie personnelle qui définit encore [boucle] langue est respectée (elle
l'emporte sur [general] dans la même couche) tant que vous ne l'avez pas
retirée ; la valeur finale est toujours lue dans donnees["general"]["langue"].
Le fuseau horaire vient de [general] fuseau_horaire (jamais codé en dur).

Aucun réglage n'est lu « à moitié » : chaque clé du fichier d'exemple est lue
par un script, ou absente du fichier.
"""

import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_CONFIG = RACINE / "config"

LANGUES = ("fr", "en")
LANGUE_DEFAUT = "en"  # Décision du 21 nov. 2026 : anglais par défaut.
FUSEAU_DEFAUT = "America/Toronto"

NOM_PUBLIC = "config.example.toml"
NOM_PERSONNEL = "config.toml"
NOM_LOCAL = "config.local.toml"


def _bibliotheque_toml():
    """Retourne le module tomllib (ou tomli), ou None s'il manque."""
    try:
        import tomllib

        return tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib

            return tomllib
        except ImportError:
            return None


def lire_toml(chemin: Path, avertir: bool = False) -> dict:
    """Lit un fichier TOML ; {} s'il est absent, illisible ou sans lecteur.

    Ne lève jamais d'exception : un fichier de configuration cassé ne doit
    pas empêcher Jarvis de démarrer (avertissement si `avertir`).
    """
    if not chemin.exists():
        return {}
    lecteur = _bibliotheque_toml()
    if lecteur is None:
        if avertir:
            print("Avertissement : ni tomllib ni tomli disponible ; "
                  "configuration par défaut.", file=sys.stderr)
        return {}
    try:
        donnees = lecteur.loads(chemin.read_text(encoding="utf-8"))
    except (ValueError, OSError) as erreur:
        if avertir:
            print(f"Avertissement : config illisible ({chemin.name} : "
                  f"{erreur}) ; configuration par défaut.", file=sys.stderr)
        return {}
    return donnees if isinstance(donnees, dict) else {}


def fusionner(base: dict, ajout: dict) -> dict:
    """Fusion section par section : `ajout` complète et remplace `base`."""
    resultat = {cle: (dict(valeur) if isinstance(valeur, dict) else valeur)
                for cle, valeur in base.items()}
    for cle, valeur in ajout.items():
        if isinstance(valeur, dict) and isinstance(resultat.get(cle), dict):
            resultat[cle].update(valeur)
        else:
            resultat[cle] = dict(valeur) if isinstance(valeur, dict) else valeur
    return resultat


def _langue_valide(valeur, disponibles) -> str | None:
    texte = str(valeur).strip().lower() if valeur is not None else ""
    return texte if texte in disponibles else None


def _resoudre_langue(couches: list, disponibles) -> str:
    """Langue finale : couche la plus forte d'abord ; [boucle] langue (ancien
    emplacement) l'emporte sur [general] dans une même couche."""
    for _, donnees in reversed(couches):
        ancien = _langue_valide(donnees.get("boucle", {}).get("langue"),
                                disponibles)
        courant = _langue_valide(donnees.get("general", {}).get("langue"),
                                 disponibles)
        if ancien or courant:
            return ancien or courant
    return LANGUE_DEFAUT


def charger_couches(dossier_config: Path | None = None,
                    avertir: bool = False) -> list:
    """Les couches lues, de la plus faible à la plus forte : [(nom, dict)]."""
    dossier = Path(dossier_config) if dossier_config else DOSSIER_CONFIG
    public = dossier / NOM_PUBLIC
    personnel = dossier / NOM_PERSONNEL
    if avertir and not personnel.exists() and public.exists():
        print("Note : config.toml absent, on utilise config.example.toml "
              "(copiez-le vers config.toml pour personnaliser).")
    return [(nom, lire_toml(dossier / nom, avertir))
            for nom in (NOM_PUBLIC, NOM_PERSONNEL, NOM_LOCAL)]


def fichiers_illisibles(dossier_config: Path | None = None) -> list:
    """Noms des couches présentes mais impossibles à lire (TOML cassé,
    fichier inaccessible). lire_toml les traite comme vides ; un script qui
    doit se replier prudemment dans ce cas (thème de l'application) le
    demande ici. Sans lecteur TOML, aucune couche n'est dite illisible."""
    dossier = Path(dossier_config) if dossier_config else DOSSIER_CONFIG
    lecteur = _bibliotheque_toml()
    if lecteur is None:
        return []
    illisibles = []
    for nom in (NOM_PUBLIC, NOM_PERSONNEL, NOM_LOCAL):
        chemin = dossier / nom
        if not chemin.exists():
            continue
        try:
            lecteur.loads(chemin.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            illisibles.append(nom)
    return illisibles


def charger_donnees(dossier_config: Path | None = None,
                    avertir: bool = False) -> dict:
    """Configuration fusionnée (publique < personnelle < locale).

    `donnees["general"]["langue"]` est toujours une langue valide.
    """
    couches = charger_couches(dossier_config, avertir)
    donnees: dict = {}
    for _, couche in couches:
        donnees = fusionner(donnees, couche)
    general = donnees.setdefault("general", {})
    disponibles = tuple(
        str(x).lower() for x in general.get("langues_disponibles", LANGUES)
        if str(x).lower() in LANGUES) or LANGUES
    general["langues_disponibles"] = list(disponibles)
    general["langue"] = _resoudre_langue(couches, disponibles)
    if avertir:
        for nom, couche in couches:
            ancien = _langue_valide(section(couche, "boucle").get("langue"),
                                    disponibles)
            courant = _langue_valide(section(couche, "general").get("langue"),
                                     disponibles)
            if ancien and courant and ancien != courant:
                print(f"Avertissement : {nom} définit [boucle] langue "
                      f"({ancien}) ET [general] langue ({courant}) ; "
                      "l'ancien emplacement [boucle] l'emporte. Supprimez la "
                      "ligne langue de la section [boucle].",
                      file=sys.stderr)
    return donnees


def section(donnees: dict, nom: str) -> dict:
    """Une section de la configuration ({} si absente ou mal formée)."""
    valeur = donnees.get(nom, {})
    return valeur if isinstance(valeur, dict) else {}


def langue(donnees: dict | None = None) -> str:
    """Langue active (« fr » ou « en »)."""
    donnees = charger_donnees() if donnees is None else donnees
    return _langue_valide(section(donnees, "general").get("langue"),
                          LANGUES) or LANGUE_DEFAUT


def langue_auto(donnees: dict | None = None) -> bool:
    """Lot L1 : vrai si la langue de chaque tour est détectée ([general]
    langue_auto, vrai par défaut). Faux = la langue de la config partout,
    comme avant L1."""
    donnees = charger_donnees() if donnees is None else donnees
    valeur = section(donnees, "general").get("langue_auto", True)
    if isinstance(valeur, str):
        return valeur.strip().lower() not in ("false", "non", "0", "no", "")
    return bool(valeur)


EFFORTS_CERVEAU = ("bas", "moyen", "auto")
_SYNONYMES_EFFORT = {"low": "bas", "medium": "moyen", "faible": "bas",
                     "moyenne": "moyen"}


def effort_cerveau(donnees: dict | None = None) -> str | None:
    """Lot B : [cerveau] effort — « bas » (rapide, défaut), « moyen »
    (questions complexes), « auto » (bas, moyen seulement quand la question
    est complexe). None si la clé est absente (les anciens réglages
    [boucle] effort_groq / effort_anthropic s'appliquent alors) ; « bas » si
    la valeur est inconnue."""
    donnees = charger_donnees() if donnees is None else donnees
    valeur = section(donnees, "cerveau").get("effort")
    if valeur is None:
        return None
    texte = str(valeur).strip().lower()
    texte = _SYNONYMES_EFFORT.get(texte, texte)
    if texte not in EFFORTS_CERVEAU:
        print(f"Avertissement : [cerveau] effort inconnu ({valeur!r}) ; "
              "« bas » utilisé.", file=sys.stderr)
        return "bas"
    return texte


def fuseau(donnees: dict | None = None) -> ZoneInfo:
    """Fuseau horaire de [general] fuseau_horaire (America/Toronto si absent
    ou invalide). Jamais codé en dur ailleurs."""
    donnees = charger_donnees() if donnees is None else donnees
    nom = str(section(donnees, "general").get("fuseau_horaire",
                                              FUSEAU_DEFAUT)).strip()
    try:
        return ZoneInfo(nom)
    except Exception:  # ZoneInfoNotFoundError, ValueError, OSError…
        print(f"Avertissement : fuseau horaire inconnu ({nom!r}) ; "
              f"{FUSEAU_DEFAUT} utilisé.", file=sys.stderr)
        return ZoneInfo(FUSEAU_DEFAUT)


def reprendre(config: dict, donnees: dict, sections: tuple) -> dict:
    """Copie dans `config` les clés de `sections` qui y existent déjà
    (les clés du dictionnaire de défauts du script font foi)."""
    for nom in sections:
        valeurs = section(donnees, nom)
        for cle in config:
            if cle in valeurs:
                config[cle] = valeurs[cle]
    return config


def nombre_borne(valeur, minimum: float, maximum: float, defaut: float,
                 entier: bool = False):
    """`valeur` convertie en nombre et bornée ; `defaut` si inutilisable."""
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return int(defaut) if entier else defaut
    nombre = max(minimum, min(maximum, nombre))
    return int(nombre) if entier else nombre


def duree_en_minutes(texte, defaut: float) -> float:
    """« 7j », « 12h », « 90m » (ou un nombre = minutes) -> minutes."""
    if isinstance(texte, (int, float)) and not isinstance(texte, bool):
        return float(texte) if texte > 0 else defaut
    brut = str(texte or "").strip().lower()
    unites = {"j": 1440.0, "d": 1440.0, "h": 60.0, "m": 1.0}
    if brut and brut[-1] in unites:
        brut, facteur = brut[:-1], unites[brut[-1]]
    else:
        facteur = 1.0
    try:
        minutes = float(brut) * facteur
    except ValueError:
        return defaut
    return minutes if minutes > 0 else defaut


def chemin_relatif_racine(valeur, defaut: str,
                          racine: Path | None = None) -> Path:
    """Chemin de config : relatif à la racine du projet, ou absolu."""
    base = Path(racine) if racine else RACINE
    chemin = Path(str(valeur).strip() or defaut)
    return chemin if chemin.is_absolute() else base / chemin


def charger_env(racine: Path | None = None) -> None:
    """Charge .env (à la racine ou dans config/) dans l'environnement.

    Utilise python-dotenv si disponible, sinon un lecteur minimal (lignes
    CLE=VALEUR). Ne pas échouer si le fichier est absent. Les variables déjà
    définies dans l'environnement priment (override=False).
    """
    racine = Path(racine) if racine else RACINE
    for candidat in (racine / ".env", racine / "config" / ".env"):
        if not candidat.exists():
            continue
        try:
            from dotenv import load_dotenv

            load_dotenv(candidat, override=False)
            return
        except ImportError:
            pass
        for ligne in candidat.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            cle, valeur = ligne.split("=", 1)
            os.environ.setdefault(cle.strip(), valeur.strip().strip("\"'"))
        return
