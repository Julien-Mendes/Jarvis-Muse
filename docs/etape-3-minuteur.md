# Étape 3 — Minuteur local persistant

Première brique qui agit seule, sans Carson : un minuteur qui survit au
redémarrage de la machine, avec carillon et annonce vocale à l'échéance.

## Principe

- Tout se passe sur la machine : aucune donnée ne quitte le poste, aucun
  appel réseau. Les minuteurs sont conservés dans `data/timers.json`
  (gitignoré, jamais poussé dans le dépôt).
- Limites (patron du dépôt B, décisions du 21 nov. 2026) :
  - 20 minuteurs actifs maximum.
  - compte à rebours : entre quelques secondes et 1 semaine.
  - rappel à heure fixe : jusqu'à 1 an dans le futur.
- Le script n'utilise que la bibliothèque standard Python : aucune
  dépendance à installer pour le minuteur lui-même. L'annonce vocale passe
  par `scripts/lire_voix.py` (étape 2) : si Piper ou la voix n'est pas
  installé, le message est affiché à l'écran et le carillon est joué quand
  même — l'alerte n'est jamais perdue.

## Utilisation

Dans le dossier du dépôt cloné, en PowerShell :

```powershell
# Compte à rebours de 40 minutes
python scripts\minuteur.py demarrer --minutes 40 --etiquette "pâtes"

# Rappel à heure fixe (aujourd'hui, ou demain si l'heure est passée)
python scripts\minuteur.py demarrer --a 18:30 --etiquette "poster les colis"

# Rappel à une date précise
python scripts\minuteur.py demarrer --a 2026-11-22T08:30 --etiquette "appel Dre Désiel"

# Lister les minuteurs actifs
python scripts\minuteur.py lister

# Annuler (par numéro, par bout d'étiquette, ou tous)
python scripts\minuteur.py annuler 3
python scripts\minuteur.py annuler "pâtes"
python scripts\minuteur.py annuler tout
```

## Comment fonctionne l'alarme

Le minuteur ne sonne que si quelqu'un le surveille. Deux façons :

```powershell
# 1. Surveillance en continu (à lancer dans une fenêtre à part)
python scripts\minuteur.py surveiller
#    Arrêter avec Ctrl+C. Les minuteurs restent enregistrés.

# 2. Déclenchement unique (vérifie une fois les minuteurs échus, puis quitte)
python scripts\minuteur.py declencher
```

- `surveiller` vérifie toutes les 30 secondes au plus, et se réveille plus
  tôt quand une échéance approche.
- À l'échéance : carillon (deux notes, 880 Hz puis 1318,5 Hz) + annonce
  vocale du message via `lire_voix.py`, puis le minuteur est retiré de la
  liste.
- **Minuteurs manqués** : ceux arrivés à échéance pendant que la machine
  était éteinte sont annoncés au démarrage de `surveiller`
  (« Pendant que j'étais éteint, ton minuteur … est arrivé à échéance … »),
  puis retirés.

> **Important — lancement automatique :** l'auto-start au démarrage de
> Windows (bloc 25 des décisions) est une décision encore ouverte : il
> n'est **pas** configuré dans cette étape. Pour l'instant, il faut lancer
> `surveiller` manuellement quand on veut que les alarmes sonnent. Quand
> l'auto-start sera décidé, `surveiller` sera la commande à lancer au login.

## Exemple de test (1 minute)

```powershell
python scripts\minuteur.py demarrer --minutes 1 --etiquette "test"
python scripts\minuteur.py lister
python scripts\minuteur.py surveiller
#    Attendre : le carillon et l'annonce « Ton minuteur "test" est terminé. »
#    doivent se produire au bout d'une minute. Arrêter avec Ctrl+C.
python scripts\minuteur.py lister
#    La liste doit être vide.
```

Pour un test plus rapide : `--minutes 0.1` = 6 secondes.

## Dépannage

- **« Annonce vocale indisponible »** : Piper ou la voix n'est pas
  installé. Le message est affiché à l'écran, le minuteur est quand même
  retiré. Suivre `docs/etape-2-voix.md` pour installer Piper et la voix
  `upmc` (français).
- **« il y a déjà 20 minuteurs actifs »** : annulez-en d'abord
  (`annuler tout` pour tout effacer).
- **« … est déjà passé »** : l'heure demandée est dans le passé. Pour
  `HH:MM`, une heure déjà passée aujourd'hui vise demain.
- **« … n'est pas une heure comprise »** : utilisez `HH:MM`
  (ex. `18:30`) ou `AAAA-MM-JJTHH:MM` (ex. `2026-11-22T18:30`).
- **Plusieurs minuteurs correspondent** à l'étiquette donnée à `annuler` :
  précisez le numéro (`annuler 3`).
- **Le fichier `data/timers.json` est corrompu** : le script repart d'une
  liste vide et affiche un avertissement. Pour repartir de zéro,
  supprimez simplement le fichier.
- **La surveillance ne démarre pas / se ferme** : vérifiez que Python 3.10+
  est installé (`python --version`). `surveiller` doit tourner tant qu'on
  veut des alarmes : fermer sa fenêtre arrête la surveillance (les
  minuteurs restent enregistrés et seront annoncés comme manqués au
  prochain démarrage).

## Sécurité

Conforme à `docs/regles-securite.md` : données 100 % locales, journal
sans contenu (les messages ne contiennent que l'étiquette donnée par
Julien), aucun secret, aucun appel réseau. Les minuteurs ne déclenchent
aucune écriture externe : ils se contentent d'annoncer.
