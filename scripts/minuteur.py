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
voix locale). Si la voix n'est pas disponible, le message est affiché à
l'écran et le carillon est joué quand même.

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

# Fuseau horaire de Julien (config/config.example.toml).
FUSEAU = ZoneInfo("America/Toronto")

MAX_ACTIFS = 20
DUREE_MAX_MINUTES = 7 * 24 * 60  # 1 semaine.
AVANCE_MAX = timedelta(days=365)  # 1 an.
LONGUEUR_MAX_ETIQUETTE = 80

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]


def maintenant() -> datetime:
    """Heure locale actuelle."""
    return datetime.now(FUSEAU)


def chemin_donnees_defaut() -> Path:
    """Chemin du fichier de persistance (data/timers.json à la racine)."""
    return Path(__file__).resolve().parent.parent / "data" / "timers.json"


# ---------------------------------------------------------------------------
# Persistance (écriture atomique : fichier temporaire puis remplacement)
# ---------------------------------------------------------------------------

def charger(chemin: Path) -> dict:
    """Lit l'état des minuteurs ; repart d'un état vide si absent ou illisible."""
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except FileNotFoundError:
        pass
    except (ValueError, OSError) as erreur:
        print(f"Avertissement : impossible de lire {chemin} ({erreur}) ; "
              "on repart d'une liste vide.", file=sys.stderr)
    return {"timers": [], "next_id": 1}


def sauvegarder(chemin: Path, etat: dict) -> None:
    """Écrit l'état de façon atomique."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_suffix(".tmp")
    temporaire.write_text(json.dumps(etat, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    temporaire.replace(chemin)


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


def annoncer(message: str) -> None:
    """Carillon + lecture du message à voix haute via lire_voix.py.

    Si la voix n'est pas disponible (Piper non installé, voix absente), le
    message est affiché à l'écran : l'alerte n'est jamais perdue.
    """
    print(f"🔔 {message}", flush=True)
    carillon()
    script_voix = Path(__file__).resolve().parent / "lire_voix.py"
    try:
        resultat = subprocess.run(
            [sys.executable, str(script_voix), "--texte", message],
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

def declencher_dus(chemin: Path, debut_surveillance=None) -> list:
    """Annonce et retire tous les minuteurs échus. Retourne les messages.

    Si debut_surveillance est fourni (démarrage de `surveiller`), les
    minuteurs échus avant (début - 1 minute) sont annoncés comme manqués
    pendant que la machine était éteinte.
    """
    ref = maintenant()
    etat = charger(chemin)
    minuteurs = etat["timers"]
    dus = sorted(
        (m for m in minuteurs
         if datetime.fromisoformat(m["due"]) <= ref),
        key=lambda m: m["due"],
    )
    if not dus:
        return []
    etat["timers"] = [m for m in minuteurs if m not in dus]
    sauvegarder(chemin, etat)

    messages = []
    for minuteur in dus:
        quand = datetime.fromisoformat(minuteur["due"])
        etiquette = minuteur["label"]
        if debut_surveillance and quand < debut_surveillance - timedelta(minutes=1):
            messages.append(
                f"Pendant que j'étais éteint, ton {minuteur['kind']} "
                f"{'« ' + etiquette + ' » ' if etiquette else ''}"
                f"est arrivé à échéance {formater_echeance(quand, ref)}.")
        elif minuteur["kind"] == "timer":
            messages.append(
                f"Ton minuteur {'« ' + etiquette + ' » ' if etiquette else ''}"
                "est terminé.")
        else:
            messages.append(
                f"Rappel : {etiquette}." if etiquette
                else "Ton rappel est arrivé à échéance.")
    for message in messages:
        annoncer(message)
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

    etat = charger(args.donnees)
    if len(etat["timers"]) >= MAX_ACTIFS:
        print(f"Erreur : il y a déjà {MAX_ACTIFS} minuteurs actifs ; "
              "annulez-en d'abord.", file=sys.stderr)
        return 1
    minuteur = {"id": etat["next_id"], "kind": genre, "label": etiquette,
                "due": due.isoformat(), "minutes": minutes,
                "created": ref.isoformat()}
    etat["next_id"] += 1
    etat["timers"].append(minuteur)
    sauvegarder(args.donnees, etat)

    quoi = (f"Minuteur de {formater_duree(minutes)}" if genre == "timer"
            else "Rappel")
    if etiquette:
        quoi += f" « {etiquette} »"
    print(f"Réglé : {quoi}, pour {formater_echeance(due, ref)} "
          f"(n° {minuteur['id']}).")
    return 0


def cmd_lister(args) -> int:
    ref = maintenant()
    etat = charger(args.donnees)
    minuteurs = sorted(etat["timers"], key=lambda m: m["due"])
    if not minuteurs:
        print("Aucun minuteur ni rappel en cours.")
        return 0
    print(f"{len(minuteurs)} en cours :")
    for minuteur in minuteurs:
        due = datetime.fromisoformat(minuteur["due"])
        reste = due - ref
        quoi = minuteur["kind"] + (
            f" « {minuteur['label']} »" if minuteur["label"] else "")
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
    etat = charger(args.donnees)
    minuteurs = etat["timers"]
    cible = args.cible.strip()

    if cible.lower() in ("tout", "tous", "all", "everything"):
        supprimes = list(minuteurs)
    elif cible.isdigit():
        supprimes = [m for m in minuteurs if m["id"] == int(cible)]
    else:
        recherche = cible.lower()
        supprimes = [m for m in minuteurs
                     if recherche and recherche in m["label"].lower()]
        if len(supprimes) > 1:
            noms = ", ".join(
                f"n° {m['id']} « {m['label']} »" for m in supprimes)
            print(f"Erreur : plusieurs minuteurs correspondent : {noms}. "
                  "Précisez le numéro.", file=sys.stderr)
            return 1

    if not supprimes:
        noms = ", ".join(
            f"n° {m['id']} « {m['label'] or m['kind']} »" for m in minuteurs) \
            or "aucun"
        print(f"Erreur : aucun minuteur ne correspond à « {cible} » ; "
              f"en cours : {noms}.", file=sys.stderr)
        return 1

    etat["timers"] = [m for m in minuteurs if m not in supprimes]
    sauvegarder(args.donnees, etat)
    noms = ", ".join(
        f"n° {m['id']} « {m['label'] or m['kind']} »" for m in supprimes)
    print(f"Annulé : {noms}.")
    return 0


def cmd_declencher(args) -> int:
    messages = declencher_dus(args.donnees)
    if not messages:
        print("Aucun minuteur arrivé à échéance.")
    return 0


def cmd_surveiller(args) -> int:
    debut = maintenant()
    print("Surveillance des minuteurs démarrée "
          "(vérification toutes les 30 secondes au plus).", flush=True)
    print("Arrêter avec Ctrl+C.", flush=True)
    declencher_dus(args.donnees, debut_surveillance=debut)
    try:
        while True:
            etat = charger(args.donnees)
            prochaines = [datetime.fromisoformat(m["due"])
                          for m in etat["timers"]]
            if prochaines:
                attente = max(
                    0.0,
                    min(30.0, (min(prochaines) - maintenant()).total_seconds()))
            else:
                attente = 30.0
            time.sleep(attente)
            declencher_dus(args.donnees)
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
    return args.fonction(args)


if __name__ == "__main__":
    sys.exit(main())
