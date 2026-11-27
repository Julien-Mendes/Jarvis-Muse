#!/usr/bin/env python3
"""navigateur.py — Contrôle du navigateur du Jarvis-Muse (étape 5).

Deux usages :
  1. Une commande (ligne de commande) :
         python scripts/navigateur.py ouvrir <url>
         python scripts/navigateur.py rechercher <requête>
         python scripts/navigateur.py lire <url> [--max-caracteres 5000]
         python scripts/navigateur.py capture <url> --sortie page.png
  2. Interactif (JSON, une commande par ligne sur stdin) — utilisé par
     scripts/boucle_voix.py :
         python scripts/navigateur.py --interactif
     Commandes : ping, naviguer, rechercher, chercher_et_ouvrir, cliquer,
     fermer_onglet, texte, capture, fermer.
     Réponses JSON : {"ok": true, ...} ou {"ok": false, "erreur": "..."} ;
     "redemarre": true quand Chrome a dû être relancé (session tombée).

Comportement :
  - `ouvrir` : ouvre l'URL dans le navigateur par défaut de Julien (pas de
    Playwright) — le navigateur reste ouvert naturellement.
  - `rechercher` / `lire` / `capture` / `cliquer` / `texte` : Google
    Chrome visible piloté par Playwright (canal « chrome », Chrome
    seulement ; fenêtre maximisée), une seule instance par processus et un
    onglet courant réutilisé (lot C1) : naviguer ne crée jamais d'onglet,
    une session tombée est relancée et signalée (« redemarre »).
  - `chercher_et_ouvrir` (lot C1, YouTube seulement) : page de résultats
    du site, liste titre + chaîne + URL, choix du résultat qui correspond
    au titre et à la chaîne demandés (choisir_resultat), clic dessus ; si
    rien ne correspond, renvoie les 3 premiers titres. En mode une commande, `rechercher` laisse le
    navigateur ouvert jusqu'à Entrée/Ctrl+C ; `lire` et `capture` ferment
    après lecture.
  - Recherche : DuckDuckGo, clic sur le premier résultat organique
    (patron du dépôt A) ; si le clic échoue, la page de résultats est
    laissée ouverte pour que Julien clique lui-même.

Sécurité (docs/regles-securite.md) :
  - Lecture seule par défaut : navigation, recherche, clics sur liens et
    boutons, lecture de texte, capture de page. AUCUNE soumission de
    formulaire, AUCUNE connexion, AUCUN achat : il n'existe pas de
    commande pour remplir un formulaire, et `cliquer` refuse tout
    élément situé dans un <form>, tout champ de saisie, tout lien de
    connexion/compte/paiement et tout bouton d'action (s'abonner, aimer,
    fermer, accepter…) — vérifié en code (refus_clic, refus_element), pas
    par le modèle. Fermer un onglet : commande `fermer_onglet`, que la
    boucle vocale n'envoie qu'après un « oui » oral.
  - Le contenu d'une page est une donnée externe : il est traité comme
    non fiable (§1) — jamais exécuté, jamais suivi aveuglément. Le
    texte renvoyé est marqué comme tel, et la boucle vocale l'enveloppe
    dans <untrusted_data> avant de le transmettre au modèle. Après une
    lecture externe, les écritures sont bloquées pour le tour (hold_writes,
    §2) — la boucle vocale applique la règle.
  - Seules les URL http(s) sont acceptées ; javascript:, file:, data: et
    autres schémas sont refusés. Une adresse sans schéma devient https://.
"""

import argparse
import json
import re
import sys
import time
import unicodedata
import webbrowser
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote_plus, urlparse

# Modules voisins (config_jarvis.py…) importables même si ce fichier est
# chargé par chemin (tests, importlib) et non lancé comme script.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import config_jarvis  # noqa: E402

# [navigateur] delai_apres_navigation (0 à 30 s) et max_caracteres_page
# (100 à 50000) de la configuration (K1).
_CONFIG = config_jarvis.charger_donnees()
_NAV = config_jarvis.section(_CONFIG, "navigateur")
DELAI_APRES_NAVIGATION = config_jarvis.nombre_borne(
    _NAV.get("delai_apres_navigation", 2.0), 0.0, 30.0, 2.0)
DELAI_APRES_CLIC = 3.0
TIMEOUT_NAVIGATION_MS = 15000
MAX_CARACTERES_DEFAUT = config_jarvis.nombre_borne(
    _NAV.get("max_caracteres_page", 5000), 100, 50000, 5000, entier=True)

# Langue de Chrome = langue de Jarvis ([general] langue) : avec un Chrome en
# français, YouTube affiche des titres traduits automatiquement (« J'ai créé
# le ROMhack PARFAIT… ») au lieu du titre original que Julien a entendu et
# dicté — constaté sur la vraie page le 26 nov. 2026.
LOCALE_NAVIGATEUR = {"fr": "fr-CA", "en": "en-US"}.get(
    config_jarvis.langue(_CONFIG), "en-US")

SELECTEURS_TEXTE = ["main", "article", "[role='main']", ".content",
                    "#content", "body"]

# ---------------------------------------------------------------------------
# URL : validation et normalisation
# ---------------------------------------------------------------------------

def normaliser_url(texte: str) -> str:
    """Valide et normalise une URL (http/https seulement)."""
    texte = (texte or "").strip()
    if not texte:
        raise ValueError("URL vide.")
    if re.match(r"(?i)^[a-z][a-z0-9+.-]*:", texte):
        schema = texte.split(":", 1)[0].lower()
        if schema not in ("http", "https"):
            raise ValueError(
                f"Schéma refusé : {schema!r} — seules les URL http(s) "
                "sont acceptées.")
    else:
        texte = "https://" + texte
    partie = urlparse(texte)
    if not partie.netloc or "." not in partie.netloc:
        raise ValueError(f"URL invalide : {texte!r}.")
    return texte


def url_recherche(requete: str) -> str:
    """URL de recherche DuckDuckGo pour une requête."""
    return "https://duckduckgo.com/?q=" + quote_plus(requete.strip())


# ---------------------------------------------------------------------------
# Garde-fous du clic (C1) — vérifiés en code, jamais laissés au modèle
# ---------------------------------------------------------------------------
# Jamais de connexion, jamais d'achat, jamais de formulaire ; fermer un onglet
# passe par la commande fermer_onglet (confirmée oralement côté boucle) ;
# toute autre action qui n'est pas de la navigation ou de la lecture (s'abonner,
# aimer, commenter, partager, télécharger, accepter…) est refusée : Julien la
# fait lui-même. La liste ne peut que s'allonger (ne pas l'assouplir).
# Toujours refusés, lien ou bouton : connexion, compte, achat, paiement.
MOTS_INTERDITS_TOUJOURS = (
    r"connexion", r"se connecter", r"connecter", r"identifier", r"s'identifier",
    r"inscription", r"s'inscrire", r"inscrire", r"creer un compte",
    r"mot de passe", r"sign ?in", r"log ?in", r"sign ?up", r"log ?out",
    r"sign ?out", r"create account", r"password", r"deconnexion",
    r"acheter", r"achat", r"payer", r"paiement", r"panier", r"checkout",
    r"buy", r"purchase", r"add to cart", r"faire un don", r"donate",
    r"essai gratuit", r"free trial",
)
# Refusés en plus sur un bouton (un élément qui agit au lieu de naviguer) et
# dans le texte demandé : actions sur un compte, fermeture, consentement.
MOTS_INTERDITS_BOUTONS = MOTS_INTERDITS_TOUJOURS + (
    r"register", r"commander", r"order", r"louer", r"rent", r"pay",
    r"cart", r"join", r"rejoindre", r"premium",
    r"s'abonner", r"abonner", r"abonnement", r"subscribe", r"like",
    r"j'aime", r"dislike", r"commenter", r"comment", r"partager", r"share",
    r"publier", r"post", r"envoyer", r"send", r"supprimer", r"delete",
    r"remove", r"signaler", r"report", r"enregistrer", r"save",
    r"telecharger", r"download", r"installer", r"install",
    r"fermer", r"close", r"quitter", r"quit", r"exit", r"accepter",
    r"accept", r"autoriser", r"allow", r"agree", r"j'accepte", r"refuser",
    r"reject", r"consent",
)


def _motif(mots: tuple):
    return re.compile(r"(?<![\w'])(?:" + "|".join(mots) + r")(?![\w'])")


_MOTIF_TOUJOURS = _motif(MOTS_INTERDITS_TOUJOURS)
_MOTIF_BOUTONS = _motif(MOTS_INTERDITS_BOUTONS)
# Adresses de lien refusées : connexion, compte, paiement.
_MOTIF_LIEN_INTERDIT = re.compile(
    r"(?i)(accounts\.google\.|/signin|/sign-in|/login|/log-in|/logout|"
    r"/register|/signup|/sign-up|/checkout|/cart|/payment|/purchase|"
    r"/account|/premium|servicelogin)")


def normaliser_texte(texte: str) -> str:
    """Minuscules, sans accents ni ponctuation (sauf l'apostrophe), espaces
    simples — pour comparer titres, chaînes et textes de boutons."""
    texte = unicodedata.normalize("NFKD", str(texte or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = texte.lower().replace("’", "'")
    texte = re.sub(r"[^\w\s']", " ", texte)
    return " ".join(texte.split())


def refus_clic(texte: str, bouton: bool = True) -> str | None:
    """Raison du refus si le texte à cliquer désigne une action interdite.

    `bouton=False` (lien de navigation ordinaire) : seuls connexion et achat
    sont vérifiés — un titre de vidéo « Songs like this » reste cliquable.
    """
    t = normaliser_texte(texte)
    if not t:
        return None
    m = (_MOTIF_BOUTONS if bouton else _MOTIF_TOUJOURS).search(t)
    if m:
        return (f"« {m.group(0)} » n'est pas une simple navigation "
                "(connexion, achat, formulaire, fermeture ou action sur un "
                "compte) : Julien doit le faire lui-même")
    return None


def refus_element(info: dict) -> str | None:
    """Raison du refus d'après l'élément trouvé sur la page (vérifié en code).

    `info` vient de la page : {"formulaire": bool, "balise": str,
    "type": str, "editable": bool, "href": str, "texte": str}.
    """
    if info.get("formulaire"):
        return ("cet élément fait partie d'un formulaire (aucune soumission "
                "de formulaire, connexion ou achat n'est autorisée)")
    balise = str(info.get("balise", "")).lower()
    if balise in ("input", "textarea", "select", "option") or info.get(
            "editable"):
        return "c'est un champ de saisie, pas un lien"
    if str(info.get("type", "")).lower() in ("submit", "password"):
        return "c'est un bouton d'envoi de formulaire"
    href = str(info.get("href", "") or "").strip()
    if href and not re.match(r"(?i)^(https?:|/|#|\?)", href):
        return "lien refusé (schéma non http(s))"
    if href and _MOTIF_LIEN_INTERDIT.search(href):
        return "ce lien mène à une page de connexion, de compte ou de paiement"
    # Un vrai lien (avec adresse) navigue ; tout le reste agit.
    est_lien = bool(href) and not href.startswith("#")
    return refus_clic(str(info.get("texte", "") or "")[:200],
                      bouton=not est_lien)


# ---------------------------------------------------------------------------
# Recherche sur un site et choix du bon résultat (C1)
# ---------------------------------------------------------------------------
# YouTube seulement pour l'instant. La recherche passe par l'adresse de la
# page de résultats (équivalent exact de « champ de recherche + Entrée ») :
# on ne remplit ni ne soumet aucun formulaire, conformément aux garde-fous.
SITES_RECHERCHE = {
    "youtube": "https://www.youtube.com/results?search_query=",
}
ALIAS_SITES = {"youtube": "youtube", "youtube.com": "youtube",
               "youtube com": "youtube",
               "www.youtube.com": "youtube", "yt": "youtube",
               "you tube": "youtube"}

SEUIL_TITRE_SEUL = 0.75        # sans chaîne demandée
SEUIL_TITRE_CHAINE_OK = 0.5    # la chaîne correspond
SEUIL_TITRE_CHAINE_KO = 0.9    # la chaîne ne correspond pas

# Extraction des résultats YouTube : titre, chaîne, URL de chaque vidéo
# (publicités, Shorts et listes de lecture ignorés : seules les URL /watch).
SCRIPT_RESULTATS_YOUTUBE = r"""
(() => {
  // Lien du TITRE d'un résultat, par ordre de priorité : un querySelector
  // avec une liste de sélecteurs rendrait le premier lien du document — la
  // miniature (« 45:39 En cours de lecture »), vérifié sur la vraie page.
  const SELECTEURS_TITRE = [
    "a#video-title", "a#video-title-link",
    "a.yt-lockup-metadata-view-model__title",
    "h3 a[href*='/watch?v=']", "a[href*='/watch?v='][title]"];
  const SELECTEURS_CHAINE = [
    "ytd-channel-name a", "ytd-channel-name #text", "a[href^='/@']",
    "a[href*='youtube.com/@']", "a[href^='/channel/']"];
  const premier = (racine, liste) => {
    for (const sel of liste) {
      const el = racine.querySelector(sel);
      if (el) return el;
    }
    return null;
  };
  const vus = new Set();
  const sortie = [];
  const ajouter = (lien, conteneur) => {
    if (!lien) return;
    const href = lien.href || "";
    const m = href.match(/[?&]v=([\w-]{6,})/);
    if (!m || !/youtube\.com\/watch/.test(href) || vus.has(m[1])) return;
    const titre = (lien.getAttribute("title") || lien.textContent || "")
      .replace(/\s+/g, " ").trim();
    if (!titre || /^\d+(:\d+)+\b/.test(titre)) return;  // durée, miniature
    let chaine = "";
    const c = conteneur ? premier(conteneur, SELECTEURS_CHAINE) : null;
    if (c) chaine = (c.textContent || "").trim().split("\n")[0].trim();
    vus.add(m[1]);
    sortie.push({titre: titre, chaine: chaine,
                 url: "https://www.youtube.com/watch?v=" + m[1], id: m[1]});
  };
  for (const r of document.querySelectorAll(
      "ytd-video-renderer, yt-lockup-view-model, ytd-rich-item-renderer")) {
    ajouter(premier(r, SELECTEURS_TITRE), r);
    if (sortie.length >= 20) break;
  }
  if (!sortie.length) {
    for (const a of document.querySelectorAll("a[href*='/watch?v=']")) {
      if (a.id === "thumbnail") continue;
      ajouter(a, a.closest("div"));
      if (sortie.length >= 20) break;
    }
  }
  return sortie;
})()
"""


def site_recherche(site: str) -> str | None:
    """Nom canonique du site de recherche pris en charge, ou None."""
    s = re.sub(r"(?i)^https?://", "", str(site or "").strip()).strip("/ ")
    return ALIAS_SITES.get(s.lower()) or ALIAS_SITES.get(normaliser_texte(s))


def url_recherche_site(site: str, requete: str) -> str:
    """URL de la page de résultats d'un site pris en charge."""
    canonique = site_recherche(site)
    if canonique is None:
        raise ValueError(f"recherche non prise en charge sur {site!r} "
                         "(YouTube seulement pour l'instant)")
    return SITES_RECHERCHE[canonique] + quote_plus(requete.strip())


def _compact(texte: str) -> str:
    return normaliser_texte(texte).replace(" ", "").replace("'", "")


def score_titre(demande: str, candidat: str) -> float:
    """Ressemblance 0..1 entre le titre demandé et un titre trouvé.

    70 % : part des mots demandés présents dans le titre trouvé (un mot de
    3 lettres ou plus compte aussi s'il est collé à un autre : « rom hack »
    / « romhack ») ; 30 % : ressemblance des deux phrases.
    """
    a, b = normaliser_texte(demande), normaliser_texte(candidat)
    if not a or not b:
        return 0.0
    mots_a, mots_b = a.split(), set(b.split())
    colle_b = _compact(b)
    rappel = sum(1 for m in mots_a if m in mots_b
                 or (len(m) >= 3 and m.replace("'", "") in colle_b)
                 ) / len(mots_a)
    ratio = SequenceMatcher(None, _compact(a), _compact(b)).ratio()
    return round(0.7 * rappel + 0.3 * ratio, 4)


def chaine_correspond(demandee: str | None, trouvee: str) -> bool | None:
    """True / False si une chaîne est demandée et connue ; None sinon."""
    d, t = _compact(demandee or ""), _compact(trouvee or "")
    if not d or not t:
        return None
    if d == t or d in t or t in d:
        return True
    return SequenceMatcher(None, d, t).ratio() >= 0.85


def choisir_resultat(resultats: list, titre: str,
                     chaine: str | None = None) -> dict | None:
    """Le résultat qui correspond le mieux au titre et à la chaîne demandés,
    ou None si aucun n'est assez proche (on ne clique jamais au hasard)."""
    meilleur, meilleur_score = None, -1.0
    for resultat in resultats or []:
        st = score_titre(titre, resultat.get("titre", ""))
        ok_chaine = chaine_correspond(chaine, resultat.get("chaine", ""))
        if ok_chaine is True:
            acceptable, score = st >= SEUIL_TITRE_CHAINE_OK, st + 0.25
        elif ok_chaine is False:
            acceptable, score = st >= SEUIL_TITRE_CHAINE_KO, st - 0.25
        else:
            acceptable, score = st >= SEUIL_TITRE_SEUL, st
        if acceptable and score > meilleur_score:
            meilleur, meilleur_score = resultat, score
    return meilleur


def cle_url(url: str) -> str:
    """Clé de comparaison d'une adresse : hôte sans « www. », chemin sans
    barre finale, requête — sans schéma ni fragment."""
    partie = urlparse(url if "://" in url else "https://" + url)
    hote = partie.netloc.lower()
    if hote.startswith("www."):
        hote = hote[4:]
    if hote.startswith("m."):
        hote = hote[2:]
    chemin = partie.path.rstrip("/")
    return hote + chemin + (("?" + partie.query) if partie.query else "")


def _session_tombee(erreur: Exception) -> bool:
    """L'erreur Playwright signale-t-elle une page ou un navigateur fermé ?"""
    texte = str(erreur).lower()
    return any(m in texte for m in (
        "has been closed", "target closed", "target page, context or browser",
        "browser has been closed", "connection closed", "page closed",
        "browser closed", "not connected"))


# ---------------------------------------------------------------------------
# Navigateur Playwright (une instance par processus, Chrome seulement)
# ---------------------------------------------------------------------------

class Navigateur:
    """Google Chrome visible piloté par Playwright, avec les gardes de
    sécurité de l'étape 5 et du lot C1.

    Une seule fenêtre, un onglet courant réutilisé d'une commande à l'autre :
    naviguer ne crée jamais d'onglet. Si Julien ferme l'onglet, on reprend un
    autre onglet ouvert ; si la fenêtre ou Chrome est tombé, on relance
    proprement et `redemarre` passe à True (la boucle le dit à Julien).
    """

    def __init__(self):
        self._playwright = None
        self._navigateur = None
        self._contexte = None
        self.page = None
        self._a_demarre = False
        self.redemarre = False

    def demarrer(self) -> None:
        """Lance Google Chrome visible (canal « chrome », pas Chromium).

        Lève RuntimeError avec un message clair si Playwright ou Chrome
        manque — en mode interactif, l'erreur devient une réponse JSON et
        la session reste en vie ; en ligne de commande, main() l'affiche
        et quitte avec le code 3.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "le module playwright n'est pas installé — installez-le "
                "avec : pip install -r scripts/requirements-etape5.txt")
        try:
            self._playwright = sync_playwright().start()
            self._navigateur = self._playwright.chromium.launch(
                channel="chrome", headless=False, args=["--start-maximized"])
            self._contexte = self._navigateur.new_context(
                no_viewport=True, locale=LOCALE_NAVIGATEUR)
            # Un lien qui ouvre un nouvel onglet devient l'onglet courant.
            self._contexte.on("page", self._nouvel_onglet)
            self.page = self._contexte.new_page()
        except Exception as erreur:
            self.fermer()
            message = str(erreur)
            if ("chrome" in message.lower()
                    and ("not found" in message.lower()
                         or "executable" in message.lower())):
                raise RuntimeError(
                    "Google Chrome introuvable — le contrôle du navigateur "
                    "ne fonctionne qu'avec Chrome : installez-le")
            raise RuntimeError(
                f"impossible de lancer Chrome ({erreur})")
        self._a_demarre = True

    def _nouvel_onglet(self, page) -> None:
        self.page = page

    def est_demarre(self) -> bool:
        return self.page is not None

    def _page_vivante(self) -> bool:
        if self.page is None:
            return False
        try:
            if self.page.is_closed():
                return False
            if (self._navigateur is not None
                    and not self._navigateur.is_connected()):
                return False
        except Exception:
            return False
        return True

    def fermer(self) -> None:
        """Ferme page, contexte, navigateur et Playwright (sans échouer)."""
        for nom in ("page", "_contexte", "_navigateur", "_playwright"):
            objet = getattr(self, nom, None)
            if objet is None:
                continue
            try:
                objet.close() if nom != "_playwright" else objet.stop()
            except Exception:
                pass
            setattr(self, nom, None)

    def _assurer_demarre(self) -> None:
        """Réutilise l'onglet courant ; sinon un autre onglet ouvert ; sinon
        relance Chrome (et le signale si une session existait déjà)."""
        if self._page_vivante():
            return
        if self._contexte is not None and self._navigateur is not None:
            try:
                if self._navigateur.is_connected():
                    ouverts = [p for p in self._contexte.pages
                               if not p.is_closed()]
                    if ouverts:
                        self.page = ouverts[-1]
                        return
            except Exception:
                pass
        etait_demarre = self._a_demarre
        self.fermer()
        self.demarrer()
        if etait_demarre:
            self.redemarre = True

    def avec_reprise(self, action):
        """Exécute `action()` ; si la page ou Chrome est tombé pendant
        l'action, relance proprement et réessaie une seule fois."""
        try:
            return action()
        except Exception as erreur:
            if not _session_tombee(erreur):
                raise
        self.page = None
        self._assurer_demarre()
        self.redemarre = True
        return action()

    def naviguer(self, url: str) -> dict:
        """Va à l'URL dans l'onglet courant et retourne titre + URL finale.

        Si l'onglet affiche déjà cette adresse, rien n'est rechargé :
        `deja_ouvert` vaut True (la boucle le dit au lieu de rouvrir).
        """
        # Valider avant de lancer Chrome : une adresse refusée ne doit
        # pas ouvrir de fenêtre.
        url = normaliser_url(url)
        self._assurer_demarre()
        try:
            if self.page.url and cle_url(self.page.url) == cle_url(url):
                return {"titre": self.page.title(), "url": self.page.url,
                        "deja_ouvert": True}
        except Exception:
            pass

        def _aller():
            self.page.goto(url, timeout=TIMEOUT_NAVIGATION_MS,
                           wait_until="domcontentloaded")

        self.avec_reprise(_aller)
        time.sleep(DELAI_APRES_NAVIGATION)
        return {"titre": self.page.title(), "url": self.page.url}

    def rechercher(self, requete: str) -> dict:
        """Recherche DuckDuckGo et clique le premier résultat organique.

        Si le clic échoue, la page de résultats reste ouverte pour que
        Julien clique lui-même — on retourne quand même titre + URL.
        """
        # Valider avant de lancer Chrome : une requête vide ne doit pas
        # ouvrir de fenêtre (bug F1 : le navigateur s'ouvrait puis échouait).
        requete = (requete or "").strip()
        if not requete:
            raise ValueError("Requête de recherche vide.")
        self._assurer_demarre()
        self.avec_reprise(lambda: self.page.goto(
            url_recherche(requete), timeout=TIMEOUT_NAVIGATION_MS,
            wait_until="domcontentloaded"))
        time.sleep(DELAI_APRES_NAVIGATION)
        clique = False
        for selecteur in ('a[data-testid="result-title-a"]', ".result__a"):
            try:
                lien = self.page.query_selector(selecteur)
                if lien is not None:
                    lien.click(timeout=5000)
                    clique = True
                    break
            except Exception:
                continue
        time.sleep(DELAI_APRES_CLIC if clique else 0)
        return {"titre": self.page.title(), "url": self.page.url,
                "premier_resultat_clique": clique}

    def resultats_youtube(self) -> list:
        """Résultats de la page de recherche YouTube affichée (données
        externes : titre, chaîne, URL)."""
        try:
            self.page.wait_for_selector(
                "ytd-video-renderer, yt-lockup-view-model, "
                "a[href*='/watch?v=']", timeout=8000)
            # La liste se remplit par morceaux : attendre quelques résultats.
            self.page.wait_for_function(
                "document.querySelectorAll('ytd-video-renderer, "
                "yt-lockup-view-model').length >= 5", timeout=4000)
        except Exception:
            pass  # page lente ou sans résultat : on lit ce qu'il y a.
        resultats = self.page.evaluate(SCRIPT_RESULTATS_YOUTUBE) or []
        propres = []
        for r in resultats:
            if not isinstance(r, dict):
                continue
            url = str(r.get("url", ""))
            if not url.startswith("https://www.youtube.com/watch?v="):
                continue
            propres.append({"titre": str(r.get("titre", ""))[:200],
                            "chaine": str(r.get("chaine", ""))[:100],
                            "url": url, "id": str(r.get("id", ""))[:20]})
        return propres

    def chercher_et_ouvrir(self, site: str, titre: str,
                           chaine: str | None = None) -> dict:
        """Recherche sur le site (YouTube), choisit le résultat qui
        correspond au titre et à la chaîne demandés, et clique dessus.

        Retour : {"trouve": True, "titre_resultat", "chaine_resultat", "url"}
        ou {"trouve": False, "resultats": [3 premiers {titre, chaine}]}.
        """
        titre = (titre or "").strip()
        chaine = (chaine or "").strip() or None
        if not titre:
            raise ValueError("Titre à chercher vide.")
        requete = titre + (" " + chaine if chaine else "")
        url = url_recherche_site(site, requete)  # valide le site d'abord
        self._assurer_demarre()

        def _chercher():
            self.page.goto(url, timeout=TIMEOUT_NAVIGATION_MS,
                           wait_until="domcontentloaded")
            return self.resultats_youtube()

        resultats = self.avec_reprise(_chercher)
        choix = choisir_resultat(resultats, titre, chaine)
        if choix is None:
            return {"trouve": False,
                    "resultats": [{"titre": r["titre"], "chaine": r["chaine"]}
                                  for r in resultats[:3]]}
        clique = self._cliquer_resultat(choix)
        if not clique:
            # Le lien du résultat n'a pas pu être cliqué (page qui bouge) :
            # même cible, même onglet — c'est toujours une navigation.
            self.page.goto(choix["url"], timeout=TIMEOUT_NAVIGATION_MS,
                           wait_until="domcontentloaded")
        time.sleep(DELAI_APRES_NAVIGATION)
        return {"trouve": True, "titre_resultat": choix["titre"],
                "chaine_resultat": choix["chaine"], "url": self.page.url,
                "clique": clique}

    def _cliquer_resultat(self, choix: dict) -> bool:
        """Clique le lien d'un résultat (jamais dans un formulaire)."""
        ident = re.sub(r"[^\w-]", "", choix.get("id", ""))
        if not ident:
            return False
        try:
            lien = self.page.locator(f"a[href*='v={ident}']").first
            if lien.count() == 0:
                return False
            if lien.evaluate("el => !!el.closest('form')"):
                return False
            lien.click(timeout=5000)
            return True
        except Exception:
            return False

    def texte_page(self, max_caracteres: int = MAX_CARACTERES_DEFAUT) -> str:
        """Extrait le texte visible de la page courante (tronqué).

        Le texte est une donnée externe (non fiable) : l'appelant doit le
        traiter comme tel (voir docs/regles-securite.md §1).
        """
        self._assurer_demarre()
        script = """
        (() => {
          const cibles = %s;
          for (const sel of cibles) {
            const el = document.querySelector(sel);
            if (el && el.innerText && el.innerText.trim()) {
              return el.innerText;
            }
          }
          return document.body ? document.body.innerText || "" : "";
        })()
        """ % json.dumps(SELECTEURS_TEXTE)
        texte = self.page.evaluate(script) or ""
        texte = re.sub(r"\n{3,}", "\n\n", texte).strip()
        if len(texte) > max_caracteres:
            texte = texte[:max_caracteres] + "\n[… texte tronqué …]"
        return texte

    def cliquer(self, texte: str) -> dict:
        """Clique un lien ou un bouton par son texte visible, dans l'onglet
        courant.

        Refusé en code (avant tout clic) : texte d'action interdite
        (connexion, achat, fermeture, abonnement…), élément dans un <form>,
        champ de saisie, bouton d'envoi, lien de connexion ou de paiement.
        """
        texte = (texte or "").strip()
        if not texte:
            raise ValueError("Texte à cliquer vide.")
        # Texte demandé : connexion et achat refusés d'emblée ; le reste est
        # jugé sur l'élément trouvé (lien de navigation ou bouton d'action).
        raison = refus_clic(texte, bouton=False)
        if raison:
            raise RuntimeError(f"Clic refusé : {raison}.")
        if not self._a_demarre:
            raise RuntimeError("Aucune page n'est ouverte dans Chrome : "
                               "rien à cliquer.")
        self._assurer_demarre()
        candidat = None
        for role in ("link", "button"):
            try:
                candidat = self.page.get_by_role(role, name=texte,
                                                 exact=False).first
                if candidat.count() > 0:
                    break
                candidat = None
            except Exception:
                candidat = None
        if candidat is None:
            try:
                candidat = self.page.get_by_text(texte, exact=False).first
                if candidat.count() == 0:
                    candidat = None
            except Exception:
                candidat = None
        if candidat is None:
            raise RuntimeError(
                f"Aucun lien ni bouton « {texte} » trouvé sur la page.")
        info = candidat.evaluate(SCRIPT_INFO_ELEMENT)
        raison = refus_element(info if isinstance(info, dict) else
                               {"formulaire": True})
        if raison:
            raise RuntimeError(f"Clic refusé : {raison}.")
        candidat.click(timeout=5000)
        time.sleep(DELAI_APRES_CLIC)
        return {"titre": self.page.title(), "url": self.page.url}

    def fermer_onglet(self) -> dict:
        """Ferme l'onglet courant (la boucle exige un « oui » oral avant).

        S'il reste des onglets, le dernier devient l'onglet courant ; sinon
        Chrome est fermé (sans compter comme une chute de session).
        """
        if not self._page_vivante():
            return {"ferme": False, "onglets_restants": 0}
        try:
            self.page.close()
        except Exception:
            pass
        self.page = None
        restants = []
        try:
            if self._contexte is not None:
                restants = [p for p in self._contexte.pages
                            if not p.is_closed()]
        except Exception:
            restants = []
        if restants:
            self.page = restants[-1]
        else:
            self.fermer()
            self._a_demarre = False
        return {"ferme": True, "onglets_restants": len(restants)}

    def capture(self, sortie: Path) -> dict:
        """Capture d'écran (viewport) de la page courante, en PNG."""
        self._assurer_demarre()
        self.page.screenshot(path=str(sortie))
        return {"sortie": str(sortie), "url": self.page.url}


# Ce que le code vérifie de l'élément avant de cliquer (refus_element).
SCRIPT_INFO_ELEMENT = """
el => {
  const lien = el.closest('a');
  return {
    formulaire: !!el.closest('form'),
    balise: (el.tagName || '').toLowerCase(),
    type: (el.getAttribute('type') || ''),
    editable: !!el.isContentEditable,
    href: lien ? (lien.getAttribute('href') || '') : '',
    texte: ((el.innerText || el.textContent || '') + ' '
            + (el.getAttribute('aria-label') || '')).trim(),
  };
}
"""


# ---------------------------------------------------------------------------
# Mode interactif (JSON lignes) — utilisé par scripts/boucle_voix.py
# ---------------------------------------------------------------------------

def boucle_interactive() -> int:
    """Lit des commandes JSON sur stdin, répond en JSON sur stdout."""
    navigateur = Navigateur()
    print("Navigateur interactif prêt (JSON lignes sur stdin).",
          file=sys.stderr, flush=True)
    try:
        for ligne in sys.stdin:
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                commande = json.loads(ligne)
            except ValueError:
                print(json.dumps({"ok": False,
                                  "erreur": "ligne JSON invalide"}),
                      flush=True)
                continue
            nom = str(commande.get("commande", "")).strip().lower()
            try:
                if nom == "ping":
                    reponse = {"ok": True, "reponse": "pong"}
                elif nom == "naviguer":
                    info = navigateur.naviguer(commande.get("url", ""))
                    reponse = {"ok": True, **info}
                elif nom == "rechercher":
                    info = navigateur.rechercher(commande.get("requete", ""))
                    reponse = {"ok": True, **info}
                elif nom == "chercher_et_ouvrir":
                    info = navigateur.chercher_et_ouvrir(
                        commande.get("site", ""), commande.get("titre", ""),
                        commande.get("chaine") or None)
                    reponse = {"ok": True, **info, "non_fiable": True}
                elif nom == "cliquer":
                    info = navigateur.cliquer(commande.get("texte", ""))
                    reponse = {"ok": True, **info}
                elif nom == "fermer_onglet":
                    info = navigateur.fermer_onglet()
                    reponse = {"ok": True, **info}
                elif nom == "texte":
                    texte = navigateur.texte_page(
                        int(commande.get("max_caracteres",
                                         MAX_CARACTERES_DEFAUT)))
                    reponse = {"ok": True, "texte": texte,
                               "url": navigateur.page.url,
                               "non_fiable": True}
                elif nom == "capture":
                    sortie = commande.get("sortie", "capture-page.png")
                    info = navigateur.capture(Path(sortie))
                    reponse = {"ok": True, **info}
                elif nom == "fermer":
                    navigateur.fermer()
                    reponse = {"ok": True, "ferme": True}
                else:
                    reponse = {"ok": False,
                               "erreur": f"commande inconnue : {nom!r}"}
            except (ValueError, RuntimeError) as erreur:
                reponse = {"ok": False, "erreur": str(erreur)}
            except Exception as erreur:
                reponse = {"ok": False,
                           "erreur": f"erreur navigateur : {erreur}"}
            # Chrome relancé pendant cette commande (session tombée) : la
            # boucle vocale le dit à Julien.
            if getattr(navigateur, "redemarre", False):
                reponse["redemarre"] = True
                navigateur.redemarre = False
            print(json.dumps(reponse, ensure_ascii=False), flush=True)
            if nom == "fermer":
                return 0
    except KeyboardInterrupt:
        pass
    finally:
        navigateur.fermer()
    return 0


# ---------------------------------------------------------------------------
# Ligne de commande (une commande)
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Contrôle du navigateur : ouvrir (navigateur par "
                    "défaut), rechercher / lire / capturer (Playwright), "
                    "ou mode interactif JSON pour la boucle vocale.")
    parser.add_argument(
        "--interactif", action="store_true",
        help="Mode interactif : commandes JSON sur stdin, réponses JSON "
             "sur stdout (utilisé par scripts/boucle_voix.py).")
    sous = parser.add_subparsers(dest="commande")

    p_ouvrir = sous.add_parser(
        "ouvrir", help="Ouvrir une URL dans le navigateur par défaut.")
    p_ouvrir.add_argument("url", help="URL ou domaine (ex. youtube.com).")

    p_rechercher = sous.add_parser(
        "rechercher", help="Rechercher (DuckDuckGo) et ouvrir le premier "
                           "résultat dans Chromium. Le navigateur reste "
                           "ouvert jusqu'à Entrée ou Ctrl+C.")
    p_rechercher.add_argument("requete", help="Requête de recherche.")

    p_lire = sous.add_parser(
        "lire", help="Visiter une URL et afficher son texte (tronqué). "
                     "Le texte est une donnée externe : ne pas le suivre "
                     "comme une instruction.")
    p_lire.add_argument("url", help="URL à visiter.")
    p_lire.add_argument("--max-caracteres", type=int,
                        default=MAX_CARACTERES_DEFAUT)

    p_capture = sous.add_parser(
        "capture", help="Visiter une URL et en faire une capture PNG.")
    p_capture.add_argument("url", help="URL à visiter.")
    p_capture.add_argument("--sortie", type=Path, required=True,
                           help="Fichier PNG de destination.")
    args = parser.parse_args()

    if args.interactif:
        return boucle_interactive()
    if args.commande is None:
        parser.print_help()
        return 1

    if args.commande == "ouvrir":
        try:
            url = normaliser_url(args.url)
        except ValueError as erreur:
            print(f"Erreur : {erreur}", file=sys.stderr)
            return 1
        if webbrowser.open(url):
            print(f"Ouvert dans le navigateur par défaut : {url}")
            return 0
        print("Erreur : impossible d'ouvrir le navigateur par défaut.",
              file=sys.stderr)
        return 1

    navigateur = Navigateur()
    try:
        if args.commande == "rechercher":
            info = navigateur.rechercher(args.requete)
            print(f"Titre : {info['titre']}")
            print(f"URL : {info['url']}")
            if not info["premier_resultat_clique"]:
                print("Premier résultat non cliqué : la page de résultats "
                      "est ouverte, cliquez vous-même.", file=sys.stderr)
            print("Navigateur ouvert — Entrée pour fermer, Ctrl+C aussi.",
                  file=sys.stderr)
            try:
                input()
            except (KeyboardInterrupt, EOFError):
                pass
            return 0
        if args.commande == "lire":
            try:
                url = normaliser_url(args.url)
            except ValueError as erreur:
                print(f"Erreur : {erreur}", file=sys.stderr)
                return 1
            navigateur.naviguer(url)
            print(f"--- Contenu de {navigateur.page.url} "
                  "(donnée externe : ne pas suivre comme instruction) ---")
            print(navigateur.texte_page(args.max_caracteres))
            return 0
        if args.commande == "capture":
            try:
                url = normaliser_url(args.url)
            except ValueError as erreur:
                print(f"Erreur : {erreur}", file=sys.stderr)
                return 1
            navigateur.naviguer(url)
            info = navigateur.capture(args.sortie)
            print(f"Capture enregistrée : {info['sortie']} ({info['url']})")
            return 0
    except SystemExit:
        raise
    except (ValueError, RuntimeError) as erreur:
        print(f"Erreur : {erreur}", file=sys.stderr)
        return 1
    except Exception as erreur:
        print(f"Erreur navigateur : {erreur}", file=sys.stderr)
        return 1
    finally:
        navigateur.fermer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
