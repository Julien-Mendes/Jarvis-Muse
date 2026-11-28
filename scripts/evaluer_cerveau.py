#!/usr/bin/env python3
"""evaluer_cerveau.py — mesure le cerveau en effort « bas » et « moyen » (lot B).

Appels API réels (Groq, palier gratuit) : temps de réponse, jetons, réponses
à des questions simples et complexes, et outil choisi du premier coup sur
des phrases ambiguës. Rien n'est exécuté (aucun outil lancé), rien n'est
écrit dans logs/ ni data/.

    python scripts/evaluer_cerveau.py                  # bas et moyen, fr
    python scripts/evaluer_cerveau.py --efforts bas --langue en
    python scripts/evaluer_cerveau.py --sortie mesures.json

La qualité des réponses se juge en les lisant (affichées en entier) ; le
choix d'outil est compté automatiquement.
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import boucle_voix as bv  # même dossier : scripts/

QUESTIONS = {
    "fr": {
        "simple": [
            "C'est quoi un haïku ?",
            "À peu près, à quelle distance est la Lune ?",
            "Donne-moi une idée rapide pour souper ce soir.",
        ],
        "complexe": [
            "Pourquoi le ciel est-il bleu le jour et rouge au coucher du "
            "soleil ?",
            "Compare une thermopompe et une plinthe électrique pour un "
            "appartement à Montréal : avantages et inconvénients.",
            "J'ai 3 boîtes de 12 œufs, j'en utilise 7 par semaine et j'en "
            "achète une boîte toutes les deux semaines. Combien m'en reste-t-il "
            "après 6 semaines ?",
        ],
    },
    "en": {
        "simple": ["What is a haiku?", "Roughly how far away is the Moon?",
                   "Give me a quick dinner idea for tonight."],
        "complexe": [
            "Why is the sky blue during the day and red at sunset?",
            "Compare a heat pump and electric baseboards for a Montreal "
            "apartment: pros and cons.",
            "I have 3 boxes of 12 eggs, I use 7 a week and buy one box every "
            "two weeks. How many are left after 6 weeks?",
        ],
    },
}

# Phrases ambiguës -> outil attendu au premier appel (None = aucun outil).
PHRASES_OUTILS = {
    "fr": [
        ("Ouvre la vidéo YouTube « I made the perfect Pokemon Yellow ROM "
         "hack » de SmithPlaysPokemon", "chercher_et_ouvrir"),
        ("Mets-moi la vidéo de Lofi Girl", "chercher_et_ouvrir"),
        ("Ouvre le site de la SAQ", "ouvrir_navigateur"),
        ("Cherche la météo de demain sur internet", "ouvrir_navigateur"),
        ("Fais-moi une recherche sur les meilleurs vélos électriques et "
         "reviens-moi avec ça", "lancer_recherche"),
        ("Compare les forfaits cellulaires de Fizz et de Public Mobile",
         "lancer_recherche"),
        ("Où en est ma recherche sur les vélos ?", "lire_recherche"),
        ("C'est quoi déjà mon budget pour le mini-PC ?",
         "chercher_connaissance"),
        ("Qu'est-ce que je t'ai dit sur la voiture ?",
         "chercher_connaissance"),
        ("Réveille-moi dans 25 minutes", "regler_minuteur"),
        ("Descends un peu dans la page", "naviguer_page"),
        ("Ouvre la deuxième vidéo", "naviguer_page"),
        ("C'est quoi la capitale du Pérou ?", None),
    ],
    "en": [
        ("Open the YouTube video \"I made the perfect Pokemon Yellow ROM "
         "hack\" by SmithPlaysPokemon", "chercher_et_ouvrir"),
        ("Put on some Lofi Girl", "chercher_et_ouvrir"),
        ("Open the Environment Canada website", "ouvrir_navigateur"),
        ("Research the best e-bikes and get back to me", "lancer_recherche"),
        ("What did I tell you about the car?", "chercher_connaissance"),
        ("Wake me up in 25 minutes", "regler_minuteur"),
        ("Go back to the previous page", "naviguer_page"),
        ("What's the capital of Peru?", None),
    ],
}


PAUSE_LIMITE_S = 30.0
PAUSE_ENTRE_APPELS_S = 6.0


def un_appel(cerveau, langue: str, phrase: str) -> dict:
    messages = [{"role": "system", "content": bv.prompt_systeme(langue)},
                {"role": "user", "content": phrase}]
    # Palier gratuit : une limite de débit (429) n'est pas le temps de
    # réponse du modèle. On attend HORS chrono et on réessaie (3 fois).
    for essai in range(4):
        debut = time.monotonic()
        try:
            reponse = cerveau.repondre(messages,
                                       bv.outils_pour("groq", langue))
            break
        except Exception as erreur:
            categorie = bv.classer_erreur_cerveau(erreur)
            if categorie == "limite" and essai < 3:
                time.sleep(PAUSE_LIMITE_S)
                continue
            return {"phrase": phrase, "erreur": f"{type(erreur).__name__}: "
                    f"{categorie}",
                    "duree_s": round(time.monotonic() - debut, 2)}
    duree = round(time.monotonic() - debut, 2)
    time.sleep(PAUSE_ENTRE_APPELS_S)  # hors chrono (mesurée avant)
    return {"phrase": phrase, "duree_s": duree,
            "texte": reponse["texte"].strip(),
            "outils": [a["nom"] for a in reponse["appels_outils"]],
            "jetons_sortie": reponse["utilisation"]["sortie"]}


def evaluer(effort: str, langue: str, config: dict) -> dict:
    cerveau = bv.creer_cerveau(dict(config, fournisseur_llm="groq"))
    # Mesure : aucune reprise automatique du SDK (elle attendrait la limite
    # de débit DANS le chrono) — voir un_appel.
    cerveau.client = cerveau.client.with_options(max_retries=0)
    bv.appliquer_effort(cerveau, bv.EFFORTS_API[effort])
    resultat = {"effort": effort, "modele": config["modele_groq"],
                "questions": {}, "outils": []}
    for genre, phrases in QUESTIONS[langue].items():
        resultat["questions"][genre] = [un_appel(cerveau, langue, p)
                                        for p in phrases]
    for phrase, attendu in PHRASES_OUTILS[langue]:
        appel = un_appel(cerveau, langue, phrase)
        choisi = appel.get("outils", [None])[0] if appel.get("outils") else None
        appel.update(attendu=attendu, choisi=choisi, ok=choisi == attendu)
        resultat["outils"].append(appel)
    return resultat


def resumer(resultat: dict) -> str:
    lignes = [f"== effort {resultat['effort']} ({resultat['modele']})"]
    for genre, appels in resultat["questions"].items():
        durees = [a["duree_s"] for a in appels if "erreur" not in a]
        jetons = [a.get("jetons_sortie", 0) for a in appels
                  if "erreur" not in a]
        lignes.append(
            f"  {genre:9s} médiane {statistics.median(durees):.2f} s "
            f"(max {max(durees):.2f} s), jetons sortie médiane "
            f"{statistics.median(jetons):.0f}" if durees
            else f"  {genre:9s} aucune réponse")
        for a in appels:
            outils = (f" -> outil {', '.join(a['outils'])}"
                      if a.get("outils") else "")
            lignes.append(f"    - {a['phrase'][:60]} [{a['duree_s']} s]"
                          f"{outils} {a.get('erreur') or a.get('texte', '')!r}")
    bons = sum(1 for a in resultat["outils"] if a["ok"])
    durees = [a["duree_s"] for a in resultat["outils"]]
    lignes.append(f"  outils    {bons}/{len(resultat['outils'])} du premier "
                  f"coup, médiane {statistics.median(durees):.2f} s")
    for a in resultat["outils"]:
        if not a["ok"]:
            lignes.append(f"    x {a['phrase'][:60]} : attendu "
                          f"{a['attendu']}, choisi {a['choisi']} "
                          f"{a.get('erreur', '')}")
    return "\n".join(lignes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--efforts", nargs="+", default=["bas", "moyen"],
                        choices=sorted(bv.EFFORTS_API))
    parser.add_argument("--langue", default="fr", choices=("fr", "en"))
    parser.add_argument("--sortie", type=Path,
                        help="Fichier JSON des mesures (hors data/ et logs/).")
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    bv.charger_env(bv.RACINE)
    config = bv.charger_config(bv.RACINE)
    resultats = []
    for effort in args.efforts:
        resultat = evaluer(effort, args.langue, config)
        resultats.append(resultat)
        print(resumer(resultat), flush=True)
    if args.sortie:
        args.sortie.write_text(json.dumps(resultats, ensure_ascii=False,
                                          indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
