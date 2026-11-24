#!/usr/bin/env python3
"""comparer_cerveaux.py — chronomètre l'appel LLM de la boucle vocale.

Trois modes, à lancer depuis la racine du dépôt (à côté de boucle_voix.py,
dans scripts/) :

  1. Comparer des cerveaux (appels API réels, quelques centimes au plus) :
       python scripts/comparer_cerveaux.py
       python scripts/comparer_cerveaux.py --essais 6 --langue fr \\
           --cible groq:openai/gpt-oss-120b:low \\
           --cible groq:openai/gpt-oss-120b:medium \\
           --cible anthropic:claude-haiku-5-5:low
     Format d'une cible : fournisseur:modele[:effort]   (effort vide = défaut
     du fournisseur). Sans --cible : les deux cerveaux de config.toml.

  2. Lire le journal existant (aucun appel API) :
       python scripts/comparer_cerveaux.py --journal
     Médianes par modèle depuis logs/tours-*.jsonl : transcription, LLM,
     autre, premier audio. Dit où part le temps AVANT la voix.

  3. Mesurer le démarrage à froid de la voix (joue un mot à voix haute) :
       python scripts/comparer_cerveaux.py --tts
     Chaque lecture lance un nouveau processus lire_voix.py, comme dire().

Ce script n'écrit rien dans logs/ ni data/, et n'enregistre aucune réponse.
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import boucle_voix as bv  # même dossier : scripts/

# Phrases sans mot-clé d'outil (minuteur, écran, navigateur).
PHRASES = {
    "en": [
        "What's the difference between weather and climate?",
        "Give me a quick idea for dinner tonight.",
        "Roughly how far away is the Moon?",
        "Explain what an API is in simple words.",
        "What is a haiku?",
        "Why is the sky blue?",
    ],
    "fr": [
        "C'est quoi la différence entre météo et climat ?",
        "Donne-moi une idée rapide pour ce soir.",
        "À peu près, à quelle distance est la Lune ?",
        "Explique ce qu'est une API avec des mots simples.",
        "C'est quoi un haïku ?",
        "Pourquoi le ciel est-il bleu ?",
    ],
}

# Historique factice (≈ taille réaliste d'un échange en cours).
HISTORIQUE = {
    "en": [("Hi Jarvis.", "Hello Julien, how can I help?"),
           ("What's a good book on habits?",
            "Atomic Habits by James Clear is a solid, practical pick."),
           ("Is it long?", "About three hundred pages, and easy to skim.")],
    "fr": [("Salut Jarvis.", "Salut Julien, je t'écoute."),
           ("Un bon livre sur les habitudes ?",
            "« Atomic Habits » de James Clear est un choix solide."),
           ("Il est long ?", "Environ trois cents pages, facile à survoler.")],
}


def historique(langue: str, echanges: int) -> list:
    messages = []
    for question, reponse in HISTORIQUE[langue][:max(0, echanges)]:
        messages.append({"role": "user", "content": question})
        messages.append({"role": "assistant", "content": reponse})
    return messages


def analyser_cible(texte: str) -> tuple:
    morceaux = texte.split(":")
    if len(morceaux) < 2 or morceaux[0] not in ("groq", "anthropic"):
        raise SystemExit(f"Cible invalide : « {texte} » "
                         "(format fournisseur:modele[:effort]).")
    effort = morceaux[2] if len(morceaux) > 2 else ""
    return morceaux[0], morceaux[1], effort


def creer_cerveau(cible: tuple, max_tokens: int):
    fournisseur, modele, effort = cible
    variable = "GROQ_API_KEY" if fournisseur == "groq" else "ANTHROPIC_API_KEY"
    cle = os.environ.get(variable, "").strip()
    if not cle:
        print(f"  ({variable} absente : cible ignorée)", file=sys.stderr)
        return None
    classe = bv.CerveauGroq if fournisseur == "groq" else bv.CerveauAnthropic
    return classe(cle, modele, max_tokens, effort)


def un_appel(cerveau, outils: list, langue: str, phrase: str,
             echanges: int) -> tuple:
    messages = [{"role": "system", "content": bv.prompt_systeme(langue)}]
    messages += historique(langue, echanges)
    messages.append({"role": "user", "content": phrase})
    debut = time.monotonic()
    reponse = cerveau.repondre(messages, outils)
    return time.monotonic() - debut, reponse


def mediane(valeurs: list):
    return statistics.median(valeurs) if valeurs else None


def fmt(valeur, decimales: int = 2) -> str:
    return "—" if valeur is None else f"{valeur:.{decimales}f}"


def comparer(args, config: dict) -> int:
    cibles = ([analyser_cible(c) for c in args.cible] if args.cible else [
        ("groq", str(config["modele_groq"]), str(config["effort_groq"])),
        ("anthropic", str(config["modele_anthropic"]),
         str(config["effort_anthropic"])),
    ])
    langues = ["en", "fr"] if args.langue == "les-deux" else [args.langue]
    lignes = []
    for cible in cibles:
        fournisseur, modele, effort = cible
        etiquette = f"{fournisseur}:{modele}:{effort or 'defaut'}"
        print(f"\n== {etiquette}")
        cerveau = creer_cerveau(cible, int(config["max_tokens_reponse"]))
        if cerveau is None:
            continue
        outils = ([bv.OUTIL_MINUTEUR_GROQ, bv.OUTIL_ECRAN_GROQ,
                   bv.OUTIL_NAVIGATEUR_GROQ] if fournisseur == "groq" else
                  [bv.OUTIL_MINUTEUR_ANTHROPIC, bv.OUTIL_ECRAN_ANTHROPIC,
                   bv.OUTIL_NAVIGATEUR_ANTHROPIC])
        pause = (args.pause if args.pause is not None
                 else (12.0 if fournisseur == "groq" else 0.5))
        durees, premiere, jetons_in, jetons_out, mots = [], None, [], [], []
        erreurs, outils_appeles, premiere_erreur = 0, 0, ""
        for langue in langues:
            for i in range(args.essais):
                phrase = PHRASES[langue][i % len(PHRASES[langue])]
                try:
                    duree, reponse = un_appel(cerveau, outils, langue,
                                              phrase, args.historique)
                except Exception as erreur:  # 429, réseau, modèle retiré…
                    erreurs += 1
                    premiere_erreur = premiere_erreur or str(erreur)[:160]
                    time.sleep(pause)
                    continue
                if premiere is None:
                    premiere = duree  # 1er appel : inclut la connexion TLS.
                else:
                    durees.append(duree)
                usage = reponse.get("utilisation", {})
                jetons_in.append(int(usage.get("entree", 0)))
                jetons_out.append(int(usage.get("sortie", 0)))
                mots.append(len(reponse["texte"].split()))
                outils_appeles += len(reponse["appels_outils"])
                print(f"  [{langue}] {duree:5.2f} s  "
                      f"in={jetons_in[-1]:5d}  out={jetons_out[-1]:4d}  "
                      f"mots={mots[-1]:3d}", flush=True)
                time.sleep(pause)
        cout = None
        if fournisseur == "anthropic" and jetons_in:
            cout = bv.estimer_cout_usd("anthropic",
                                       int(mediane(jetons_in)),
                                       int(mediane(jetons_out)))
        lignes.append((etiquette, premiere, mediane(durees),
                       max(durees) if durees else None,
                       mediane(jetons_in), mediane(jetons_out),
                       mediane(mots), erreurs, outils_appeles, cout))
        if premiere_erreur:
            print(f"  première erreur : {premiere_erreur}")

    print("\nRésumé (durées de l'appel LLM seul, en secondes)")
    print(f"{'cible':46} {'1er':>6} {'méd.':>6} {'max':>6} {'in':>6} "
          f"{'out':>5} {'mots':>5} {'err':>4} {'outil':>5} {'$/appel':>9}")
    for (etiquette, premiere, med, maxi, t_in, t_out, nb_mots, err,
         nb_outils, cout) in lignes:
        print(f"{etiquette:46} {fmt(premiere):>6} {fmt(med):>6} "
              f"{fmt(maxi):>6} {fmt(t_in, 0):>6} {fmt(t_out, 0):>5} "
              f"{fmt(nb_mots, 0):>5} {err:>4} {nb_outils:>5} "
              f"{('—' if cout is None else f'{cout:.5f}'):>9}")
    print("\nLecture : « out » compte aussi les jetons de raisonnement ; "
          "si out >> mots × 1,3, le modèle réfléchit beaucoup en silence "
          "(baisser l'effort). Un « err » élevé sur Groq = palier gratuit "
          "saturé (429) : c'est de la latence que la boucle subit aussi.")
    return 0


def lire_journal(dossier: Path) -> int:
    fichiers = sorted(dossier.glob("tours-*.jsonl"))
    if not fichiers:
        print(f"Aucun journal dans {dossier}.")
        return 1
    groupes = {}
    for fichier in fichiers:
        for ligne in fichier.read_text(encoding="utf-8").splitlines():
            try:
                tour = json.loads(ligne)
            except ValueError:
                continue
            llm = tour.get("premier_token_s")
            if tour.get("erreur") or not llm:
                continue  # erreurs et chemins rapides (sans LLM) exclus
            cle = (tour.get("fournisseur", "?"), tour.get("modele", "?"),
                   tour.get("mode", "voix"))
            groupes.setdefault(cle, []).append(tour)
    print(f"{'fournisseur / modèle / mode':58} {'n':>4} {'transc.':>8} "
          f"{'LLM':>6} {'autre':>6} {'1er audio':>10} {'total*':>7}")
    for (fournisseur, modele, mode), tours in sorted(groupes.items()):
        def col(nom):
            return mediane([t[nom] for t in tours if t.get(nom) is not None])
        autres = [t["premier_audio_s"] - (t.get("transcription_s") or 0)
                  - t["premier_token_s"]
                  for t in tours if t.get("premier_audio_s") is not None]
        print(f"{fournisseur + ' / ' + modele + ' / ' + mode:58} "
              f"{len(tours):>4} {fmt(col('transcription_s')):>8} "
              f"{fmt(col('premier_token_s')):>6} {fmt(mediane(autres)):>6} "
              f"{fmt(col('premier_audio_s')):>10} {fmt(col('total_s')):>7}")
    print("\nMédianes en secondes. « 1er audio » = relâchement de F9 jusqu'au "
          "LANCEMENT de la lecture (transcription + LLM + autre).\n"
          "* « total » inclut la durée de la parole elle-même. Le démarrage "
          "de lire_voix.py (chargement de Piper) n'est dans aucune de ces "
          "colonnes : mesurez-le avec --tts.")
    return 0


def mesurer_tts(langue: str, essais: int) -> int:
    print("Chaque essai joue « Okay. » à voix haute dans un NOUVEAU processus "
          "lire_voix.py (comme dire()).")
    durees = []
    for i in range(essais):
        debut = time.monotonic()
        resultat = subprocess.run(
            [sys.executable, str(bv.SCRIPT_VOIX), "--texte", "Okay.",
             "--langue", langue], capture_output=True, text=True)
        durees.append(time.monotonic() - debut)
        etat = "ok" if resultat.returncode == 0 else f"code {resultat.returncode}"
        print(f"  essai {i + 1}: {durees[-1]:.2f} s ({etat})")
        time.sleep(0.5)
    print(f"Médiane : {mediane(durees):.2f} s. Ce temps = démarrage Python + "
          "chargement de la voix + synthèse + lecture d'un mot (~0,4–0,6 s "
          "de parole). Ce qui dépasse environ 0,6 s est du coût de "
          "démarrage payé avant chaque réponse.")
    return 0


def main() -> int:
    parseur = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawTextHelpFormatter)
    parseur.add_argument("--cible", action="append", default=[],
                         help="fournisseur:modele[:effort] (répétable)")
    parseur.add_argument("--essais", type=int, default=5,
                         help="appels par langue et par cible (défaut 5 ; "
                              "le 1er est compté à part)")
    parseur.add_argument("--langue", choices=["en", "fr", "les-deux"],
                         default="en")
    parseur.add_argument("--historique", type=int, default=3,
                         help="échanges factices dans le prompt (0 à 3)")
    parseur.add_argument("--pause", type=float, default=None,
                         help="secondes entre appels (défaut : 12 Groq — le "
                              "palier gratuit limite les jetons par minute — "
                              "0,5 Anthropic)")
    parseur.add_argument("--journal", action="store_true",
                         help="résume logs/tours-*.jsonl (aucun appel API)")
    parseur.add_argument("--logs", default=str(bv.DOSSIER_TOURS),
                         help="dossier des journaux (défaut : logs/)")
    parseur.add_argument("--tts", action="store_true",
                         help="mesure le démarrage à froid de lire_voix.py")
    args = parseur.parse_args()

    bv.charger_env(bv.RACINE)
    if args.journal:
        return lire_journal(Path(args.logs))
    if args.tts:
        return mesurer_tts("fr" if args.langue == "fr" else "en",
                           max(1, args.essais))
    return comparer(args, bv.charger_config(bv.RACINE))


if __name__ == "__main__":
    sys.exit(main())
