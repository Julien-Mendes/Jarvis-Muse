"""Faux tkinter / CustomTkinter pour tester app.py sans écran (lot U2).

Ce n'est PAS une simulation complète de Tk : seulement ce qu'il faut pour
vérifier le thème et le défilement de la conversation. Deux choses sont
modélisées avec soin parce que le bug de défilement en dépend :

  - la mise en page est PARESSEUSE, comme dans Tk : un widget ajouté n'a sa
    taille qu'au prochain passage de mise en page (update_idletasks() ou tour
    de boucle), et un événement <Configure> n'est livré qu'ensuite ;
  - bind() sans add="+" REMPLACE la liaison existante (comportement de
    tkinter.Frame, dont CTkScrollableFrame hérite). Deux modèles :
    "remplace" (la liaison interne de la zone défilante est remplacée par
    celle de l'application : le bug constaté à l'essai) et "cumule" (la
    liaison interne est préservée : cas où CustomTkinter la protège).

Les modèles et les tailles (hauteur des lignes, vue de 400 px) sont des
conventions de test, pas des mesures de Windows.
"""
import importlib.util
import math
import sys
import types
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SCRIPTS = RACINE / "scripts"
HAUTEUR_VUE = 400
PX_PAR_UNITE = 20


class FausseErreurTcl(Exception):
    pass


class FausseFonte:
    def __init__(self, family=None, size=None, weight="normal", **_):
        self.family, self.size, self.weight = family, size, weight


class FauxWidget:
    """Widget générique : options, enfants, liaisons, destruction."""

    def __init__(self, master=None, **options):
        self.master = master
        self.options = dict(options)
        self.enfants = []
        self.liaisons = {}
        self.detruit = False
        self.largeur = 600
        if master is not None and hasattr(master, "enfants"):
            master.enfants.append(self)

    # -- options
    def configure(self, **options):
        self.options.update(options)

    config = configure

    def cget(self, cle):
        return self.options.get(cle)

    # -- arbre
    def winfo_children(self):
        return list(self.enfants)

    def winfo_width(self):
        return self.largeur

    def winfo_exists(self):
        return not self.detruit

    def destroy(self):
        for enfant in list(self.enfants):
            enfant.destroy()
        self.detruit = True
        if self.master is not None and hasattr(self.master, "enfants") \
                and self in self.master.enfants:
            self.master.enfants.remove(self)

    # -- liaisons (sémantique de tkinter : sans add="+", on REMPLACE)
    def bind(self, sequence=None, func=None, add=None):
        if func is None:
            return None
        if add in ("+", True):
            self.liaisons.setdefault(sequence, []).append(func)
        else:
            self.liaisons[sequence] = [func]
        return None

    def declencher(self, sequence, evenement=None):
        for fonction in list(self.liaisons.get(sequence, [])):
            fonction(evenement)

    # -- taille (mise en page simplifiée : empilement vertical)
    def hauteur(self):
        if self.enfants:
            return sum(e.hauteur() for e in self.enfants) + 16
        return 24

    def __getattr__(self, nom):
        # Méthodes Tk sans effet ici (pack, grid, focus, lift…). Les noms
        # privés restent absents (getattr(..., None) doit fonctionner).
        if nom.startswith("_"):
            raise AttributeError(nom)
        return lambda *args, **kwargs: None


class FauxLabel(FauxWidget):
    def hauteur(self):
        texte = str(self.options.get("text") or "")
        retour = self.options.get("wraplength") or 0
        par_ligne = max(1, int(retour) // 7) if retour else 10 ** 6
        lignes = max(1, math.ceil(len(texte) / par_ligne))
        return lignes * 18 + 4


class FauxEntree(FauxWidget):
    def get(self):
        return self.options.get("_texte", "")


class FauxCanvasOrbe(FauxWidget):
    def __init__(self, master=None, **options):
        super().__init__(master, **options)
        self.objets = {}

    def create_oval(self, *coords, **options):
        identifiant = len(self.objets) + 1
        self.objets[identifiant] = dict(options, coords=coords)
        return identifiant

    def coords(self, identifiant, *coords):
        self.objets[identifiant]["coords"] = coords

    def itemconfig(self, identifiant, **options):
        self.objets[identifiant].update(options)


class FauxCanvasDefilement(FauxWidget):
    """Le `_parent_canvas` de CTkScrollableFrame : région, vue, position."""

    def __init__(self, proprietaire):
        super().__init__(None)
        self.proprietaire = proprietaire
        self.scrollregion = None
        self.haut = 0.0  # pixels, comme le décalage de la vue dans Tk

    def bbox(self, _etiquette="all"):
        return (0, 0, self.proprietaire.largeur,
                self.proprietaire.hauteur_mise_en_page)

    def configure(self, **options):
        super().configure(**options)
        if "scrollregion" in options:
            self.scrollregion = options["scrollregion"]
            self._borner()

    config = configure

    def _total(self):
        return 0 if not self.scrollregion else (
            self.scrollregion[3] - self.scrollregion[1])

    def _borner(self):
        self.haut = max(0.0, min(self.haut,
                                 max(0.0, self._total() - HAUTEUR_VUE)))

    def yview(self):
        total = self._total()
        if total <= HAUTEUR_VUE:
            return (0.0, 1.0)
        return (self.haut / total, (self.haut + HAUTEUR_VUE) / total)

    def yview_moveto(self, fraction):
        self.haut = float(fraction) * self._total()
        self._borner()

    def yview_scroll(self, nombre, _unite="units"):
        self.haut += nombre * PX_PAR_UNITE
        self._borner()

    def bas_visible_px(self):
        """Pixel du contenu affiché tout en bas de la vue."""
        return min(self.haut + HAUTEUR_VUE, max(self._total(), HAUTEUR_VUE))


class FauxScrollableFrame(FauxWidget):
    """CTkScrollableFrame : zone défilante avec sa liaison interne
    <Configure> qui met à jour la zone de défilement."""

    modele = "remplace"  # ou "cumule" (réglé par fabriquer())

    def __init__(self, master=None, **options):
        super().__init__(master, **options)
        self._parent_canvas = FauxCanvasDefilement(self)
        self._scrollbar = FauxWidget(None)
        self.hauteur_mise_en_page = 0
        self._configure_en_attente = False
        self._liaisons_internes = []
        racine = master
        while racine is not None and not isinstance(racine, FauxRacine):
            racine = racine.master
        if racine is not None:
            racine.zones.append(self)
        # Liaison interne de CTkScrollableFrame : scrollregion = bbox("all").
        def mise_a_jour_region(_evenement=None):
            canvas = self._parent_canvas
            canvas.configure(scrollregion=canvas.bbox("all"))

        if self.modele == "cumule":
            self._liaisons_internes.append(mise_a_jour_region)
        else:
            self.bind("<Configure>", mise_a_jour_region)  # même table

    def declencher(self, sequence, evenement=None):
        if sequence == "<Configure>":
            for fonction in list(self._liaisons_internes):
                fonction(evenement)
        super().declencher(sequence, evenement)

    def hauteur_contenu(self):
        return sum(e.hauteur() for e in self.enfants)


class FauxRacine(FauxWidget):
    """CTk : fenêtre racine avec planificateur (after, after_idle) et boucle
    d'événements simplifiée."""

    def __init__(self, *args, **options):
        super().__init__(None, **options)
        self.zones = []
        self.maintenant = 0
        self._taches = []
        self._idle = []
        self._compteur = 0
        self.largeur = 900

    # -- planificateur
    def after(self, delai_ms, fonction=None, *args):
        self._compteur += 1
        self._taches.append([self.maintenant + delai_ms, self._compteur,
                             fonction, args])
        return f"after#{self._compteur}"

    def after_idle(self, fonction, *args):
        self._compteur += 1
        identifiant = f"idle#{self._compteur}"
        self._idle.append((identifiant, fonction, args))
        return identifiant

    def after_cancel(self, identifiant):
        self._taches = [t for t in self._taches
                        if f"after#{t[1]}" != identifiant]
        self._idle = [t for t in self._idle if t[0] != identifiant]

    def state(self):
        return "normal"

    # -- mise en page paresseuse
    def mise_en_page(self):
        for zone in self.zones:
            hauteur = zone.hauteur_contenu()
            if hauteur != zone.hauteur_mise_en_page:
                zone.hauteur_mise_en_page = hauteur
                zone._configure_en_attente = True

    def update_idletasks(self):
        self.mise_en_page()  # la mise en page, PAS la livraison d'événements

    def tourner(self):
        """Un tour de boucle : mise en page, événements <Configure>, puis
        callbacks after_idle (dans cet ordre, comme Tk)."""
        for _ in range(20):
            self.mise_en_page()
            livres = False
            for zone in list(self.zones):
                if zone._configure_en_attente:
                    zone._configure_en_attente = False
                    zone.declencher("<Configure>")
                    livres = True
            idle, self._idle = self._idle, []
            for _, fonction, args in idle:
                fonction(*args)
            if not livres and not idle and not self._idle:
                break

    def avancer(self, ms):
        """Fait avancer l'horloge de `ms` : exécute les after() échus."""
        fin = self.maintenant + ms
        while True:
            echues = sorted((t for t in self._taches if t[0] <= fin),
                            key=lambda t: (t[0], t[1]))
            if not echues:
                break
            tache = echues[0]
            self._taches.remove(tache)
            self.maintenant = max(self.maintenant, tache[0])
            tache[2](*tache[3])
            self.tourner()
        self.maintenant = fin
        self.tourner()


def fabriquer(modele: str = "remplace"):
    """Construit les faux modules tkinter et customtkinter."""
    tk = types.ModuleType("tkinter")
    tk.TclError = FausseErreurTcl
    tk.Canvas = FauxCanvasOrbe
    tk.Menu = FauxWidget
    ctk = types.ModuleType("customtkinter")
    ctk.modes = []
    ctk.CTk = FauxRacine
    ctk.CTkToplevel = FauxWidget
    ctk.CTkFrame = FauxWidget
    ctk.CTkLabel = FauxLabel
    ctk.CTkButton = FauxWidget
    ctk.CTkEntry = FauxEntree
    ctk.CTkFont = FausseFonte
    ctk.set_appearance_mode = lambda mode: ctk.modes.append(mode)

    class Zone(FauxScrollableFrame):
        pass

    Zone.modele = modele
    ctk.CTkScrollableFrame = Zone
    return tk, ctk


def charger_app(modele: str = "remplace", nom: str = "app_faux"):
    """Charge une copie neuve de scripts/app.py liée aux faux modules."""
    tk, ctk = fabriquer(modele)
    sauvegarde = {cle: sys.modules.get(cle)
                  for cle in ("tkinter", "customtkinter")}
    sys.modules["tkinter"], sys.modules["customtkinter"] = tk, ctk
    try:
        chemin_scripts = str(SCRIPTS)
        if chemin_scripts not in sys.path:
            sys.path.insert(0, chemin_scripts)
        spec = importlib.util.spec_from_file_location(
            nom, SCRIPTS / "app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for cle, ancien in sauvegarde.items():
            if ancien is None:
                sys.modules.pop(cle, None)
            else:
                sys.modules[cle] = ancien
    return module, ctk


def creer_application(module, racine, entrees_ref, theme="or_et_nuit"):
    """Crée une Application avec des entrées de conversation pilotées par le
    test : `entrees_ref` est une liste modifiable relue à chaque rafraîchissement.
    """
    module.lire_conversation = lambda chemin=None: list(entrees_ref)
    module.lire_etat = lambda chemin=None: {
        "etat": "repos", "transcription": "", "erreur": "", "langue": "",
        "present": True}
    module.charger_minuteurs = lambda chemin=None: []
    config = dict(module.DEFAUTS, langue="en", theme=theme,
                  intervalle_ms=10 ** 7)
    return module.Application(Path(racine), config)


def entree(numero: int, role=None, caracteres=60):
    """Une entrée de journal : alternance utilisateur / Jarvis."""
    return {"role": role or ("user" if numero % 2 == 0 else "assistant"),
            "texte": f"message {numero} " + "x" * caracteres,
            "heure": "2026-11-25T10:00:00-05:00"}
