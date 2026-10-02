#!/usr/bin/env python3
"""tete_html.py — <head> interrompu par un élément invalide (img, iframe, div, texte…) : Google considère que la tête est
finie et ignore les métadonnées suivantes (canonical, robots, hreflang, description). Source : Google Search Central,
« Use valid page metadata ». Module du diffuseur html_observateurs (T3).

Suit le mode d'insertion « in head » de la spécification WHATWG (§13.2.6.4.4) : sont permis dans la tête base, basefont,
bgsound, link, meta, noframes, noscript, script, style, template et title ; blancs (tab, LF, FF, CR, espace — pas l'espace
insécable), commentaires et doctype sont ignorés ; <html> et un second <head> sont ignorés ; <body> (ou </head>) termine la
tête. Tout autre élément, ou texte non blanc, ferme la tête : ce qui suit est hors de la tête. Un BOM UTF-8 en tête de document
est ignoré, comme dans un navigateur.

<noscript> a deux lectures. Avec JavaScript (rendu de Googlebot) son contenu est du texte brut : un pixel <noscript><img>
n'interrompt rien et le constat « haute/moyenne » ne le concerne pas. Sans JavaScript (première lecture du HTML brut, autres
robots, aperçus de liens) c'est le mode « in head noscript » (§13.2.6.4.5) : basefont, bgsound, link, meta, noframes et style
y restent ; tout autre jeton dépile le <noscript> et est retraité dans la tête, donc ne la ferme que s'il y est invalide aussi
(iframe de GTM, img d'un pixel, div, texte : oui ; script, template, title, base : non). Ce cas est signalé à part,
avec la mention « (sans JavaScript) » et une sévérité plafonnée à « moyenne » : Google, qui rend avec JavaScript, n'est pas
concerné d'après sa documentation.

Limites connues (rares) : une page sans <head> dont le premier élément est invalide (<html><div>…</div><link rel=canonical>)
n'est pas signalée (« pas de tête », pas « tête interrompue ») ; après une interruption puis </head>, des meta/link écrits avant
<body> sont, selon la spécification, dans le corps implicite : ils ne sont pas comptés ; </br> (traité comme <br> par un
navigateur) et <script/> auto-fermé ne sont pas modélisés (limites du diffuseur)."""
import html_observateurs as ho

NOM = "tete_html"
VALIDES = {"base", "basefont", "bgsound", "link", "meta", "noframes", "noscript", "script", "style", "template", "title"}
# Éléments dont le contenu n'est pas lu comme des balises de la tête : texte brut (title, script, style, noframes, iframe, noembed,
# xmp, textarea), contenu inerte (template) ou espace de noms étranger (svg, math : <svg><title>)
BRUTS_SANS_NOSCRIPT = ("title", "script", "style", "noframes", "template", "iframe", "noembed", "xmp", "textarea", "svg", "math")
# Avec JavaScript actif, le contenu de <noscript> est aussi du texte brut
BRUTS = BRUTS_SANS_NOSCRIPT + ("noscript",)
BLANCS = "\t\n\f\r "
BOM = "﻿"
META_SEO = ("description", "robots", "googlebot", "viewport", "theme-color")
# Balises dont la perte change l'indexation : constat « haute » ; sinon « moyenne »
PERTES_GRAVES = ("link canonical", "meta robots", "meta googlebot", "link hreflang")
SANS_JS = " (sans JavaScript)"
AVANT, TETE, FINI = 0, 1, 2
EXPLICATION_SANS_JS = ("Un <noscript> au contenu invalide dans la tête (iframe de Google Tag Manager, pixel <img>, div…) ferme la tête "
                       "pour les robots qui n'exécutent pas JavaScript et pour la première lecture du HTML brut : les balises qui le "
                       "suivent y sont perdues. Google, qui rend la page avec JavaScript, n'est pas concerné d'après sa documentation. "
                       "Correction : placer le <noscript> au début du <body>, comme l'indique Google Tag Manager.")


def classer(t, a):
    """Libellé de la balise de référencement `t` (attributs `a`), ou None si elle n'en est pas une."""
    if t == "title":
        return "title"
    if t == "meta":
        nom = (a.get("name") or a.get("property") or "").strip().lower()
        if nom in META_SEO or nom.startswith(("og:", "twitter:")):
            return "meta " + nom
    elif t == "link":
        rel = a.get("rel", "").lower().split()
        if "canonical" in rel:
            return "link canonical"
        if "alternate" in rel:
            return "link hreflang" if a.get("hreflang") else "link alternate"
        if "manifest" in rel:
            return "link manifest"
        if "preload" in rel and (a.get("as", "").lower() == "image" or a.get("fetchpriority", "").lower() == "high"):
            return "link preload LCP"
    return None


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.etat, self.interrompu, self.ignorees = AVANT, None, []
        self.sans_js, self.ignorees_sans_js = None, []  # interruption par un <noscript> sans JavaScript
        self.debut_vu = False

    def _perdue(self, liste, balise):
        if balise not in liste:
            liste.append(balise)

    def _noscript_de_tete(self, pile):
        return [n["tag"] for n in pile if n["tag"] not in ("html", "head")] == ["noscript"]

    def debut(self, noeud, pile):
        self.debut_vu = True
        t, a = noeud["tag"], noeud["a"]
        if self.etat == FINI:
            return
        if self.etat == AVANT:  # mode « before head » : <html> ignoré, <head> explicite ou tête implicite
            if t == "html":
                return
            if t == "head":
                self.etat = TETE
                return
            if t in VALIDES:
                self.etat = TETE  # tête implicite : l'élément est traité ci-dessous
            else:
                self.etat = FINI  # le corps commence sans rien dans la tête : rien n'a pu être interrompu
                return
        if t in ("html", "head"):  # ignorés dans la tête (attributs fusionnés / second <head>)
            return
        if t in ("body", "frameset"):
            self.etat = FINI
            return
        # Lecture sans JavaScript : <noscript> est du balisage, restreint à NOSCRIPT_VALIDES
        if not ho.dans(pile, *BRUTS_SANS_NOSCRIPT):
            if self.sans_js is not None:
                c = classer(t, a)
                if c:
                    self._perdue(self.ignorees_sans_js, c)
            elif self.interrompu is None and self._noscript_de_tete(pile) and t not in VALIDES:
                self.sans_js = "<noscript><{0}>".format(t)
        # Lecture avec JavaScript : contenu de <noscript> = texte brut
        if ho.dans(pile, *BRUTS):
            return
        if self.interrompu is None:
            if t not in VALIDES:
                self.interrompu = "<{0}>".format(t)
            return
        c = classer(t, a)  # après l'interruption : balises de référencement qui seront ignorées
        if c:
            self._perdue(self.ignorees, c)

    def texte(self, donnees, pile):
        if not self.debut_vu and donnees.startswith(BOM):
            donnees = donnees[1:]  # BOM UTF-8 en tête de document : ignoré par les navigateurs
        self.debut_vu = True
        if not donnees.strip(BLANCS):
            return
        if self.etat == AVANT:  # texte avant toute balise : tête implicite aussitôt fermée
            self.etat = FINI
            return
        if self.etat != TETE:
            return
        if self.interrompu is None and not ho.dans(pile, *BRUTS):
            self.interrompu = "#texte"
        if (self.sans_js is None and self.interrompu is None and self._noscript_de_tete(pile)
                and not ho.dans(pile, *BRUTS_SANS_NOSCRIPT)):
            self.sans_js = "<noscript>#texte"

    def fin(self, noeud, pile):
        if noeud["tag"] == "head":
            self.etat = FINI

    def resultat(self):
        out = []
        if self.interrompu and self.ignorees:
            out.append({"signature": "{0} puis : {1}".format(self.interrompu, ", ".join(self.ignorees)), "n": 1})
        # Même pertes déjà rapportées par l'interruption avec JavaScript (au moins aussi grave) : pas de double signature
        if self.sans_js and self.ignorees_sans_js and not (self.interrompu and set(self.ignorees_sans_js) <= set(self.ignorees)):
            out.append({"signature": "{0}{1} puis : {2}".format(self.sans_js, SANS_JS, ", ".join(self.ignorees_sans_js)), "n": 1,
                        "exemple": EXPLICATION_SANS_JS})
        return {"interruptions": out}


def grave(signature):
    """Vrai si la signature « <img> puis : link canonical, meta description » perd canonical, robots ou hreflang.
    Les signatures « (sans JavaScript) » ne le sont jamais : Google rend avec JavaScript."""
    if SANS_JS in signature:
        return False
    return any(p in PERTES_GRAVES for p in signature.split(" puis : ", 1)[-1].split(", "))


def issues(pages, add, ctx):
    groupes = ho.collecter_groupes(pages, NOM, "interruptions")
    sans_js = {s: g for s, g in groupes.items() if SANS_JS in s}
    avec_js = {s: g for s, g in groupes.items() if s not in sans_js}
    # Libellé unique et neutre (fixé par le premier ajout) : valable pour les exemples avec et sans JavaScript
    libelle = ("<head> interrompu par un élément invalide : les balises suivantes sont perdues (ignorées par Google ; pour les exemples "
               "« (sans JavaScript) », perdues par les robots qui n'exécutent pas JavaScript seulement, Google n'est pas concerné)")
    # Un seul constat : libellé et sévérité sont fixés par le premier ajout, donc les cas graves d'abord
    for severite, choisis in (("haute", {s: g for s, g in avec_js.items() if grave(s)}),
                              ("moyenne", {s: g for s, g in avec_js.items() if not grave(s)}),
                              ("moyenne", sans_js)):
        ho.ajouter_groupes(add, "tete_interrompue", libelle, severite, choisis, "SEO technique")
