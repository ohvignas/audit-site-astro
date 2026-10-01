#!/usr/bin/env python3
"""tete_html.py — <head> interrompu par un élément invalide (img, iframe, div, texte…) : Google considère que la tête est
finie et ignore les métadonnées suivantes (canonical, robots, hreflang, description). Source : Google Search Central,
« Use valid page metadata ». Module du diffuseur html_observateurs (T3).

Suit le mode d'insertion « in head » de la spécification WHATWG (§13.2.6.4.4) : sont permis dans la tête base, basefont,
bgsound, link, meta, noframes, noscript, script, style, template et title ; blancs (tab, LF, FF, CR, espace — pas l'espace
insécable), commentaires et doctype sont ignorés ; <html> et un second <head> sont ignorés ; <body> (ou </head>) termine la
tête. Tout autre élément, ou texte non blanc, ferme la tête : ce qui suit est hors de la tête. <noscript> est lu comme avec
JavaScript actif (celui du rendu de Googlebot) : son contenu est du texte brut, un pixel <noscript><img> n'interrompt rien.
Écarts connus avec un navigateur (identiques au diffuseur) : pas de </br> traité comme <br>, <script/> est fermé aussitôt."""
import html_observateurs as ho

NOM = "tete_html"
VALIDES = {"base", "basefont", "bgsound", "link", "meta", "noframes", "noscript", "script", "style", "template", "title"}
# Éléments dont le contenu n'est pas lu comme des balises de la tête : texte brut (title, script, style, noframes, noscript avec
# JavaScript, iframe, noembed, xmp, textarea), contenu inerte (template) ou espace de noms étranger (svg, math : <svg><title>)
BRUTS = ("title", "script", "style", "noframes", "noscript", "template", "iframe", "noembed", "xmp", "textarea", "svg", "math")
BLANCS = "\t\n\f\r "
META_SEO = ("description", "robots", "googlebot", "viewport")
# Balises dont la perte change l'indexation : constat « haute » ; sinon « moyenne »
PERTES_GRAVES = ("link canonical", "meta robots", "meta googlebot", "link hreflang")
AVANT, TETE, FINI = 0, 1, 2


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.etat, self.interrompu, self.ignorees = AVANT, None, []

    def debut(self, noeud, pile):
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
        if ho.dans(pile, *BRUTS):
            return
        if self.interrompu is None:
            if t not in VALIDES:
                self.interrompu = "<{0}>".format(t)
            return
        # Après l'interruption : balises de référencement qui seront ignorées
        if t == "title":
            self._perdue("title")
        elif t == "meta":
            nom = (a.get("name") or a.get("property") or "").strip().lower()
            if nom in META_SEO or nom.startswith("og:"):
                self._perdue("meta " + nom)
        elif t == "link":
            rel = a.get("rel", "").lower().split()
            if "canonical" in rel:
                self._perdue("link canonical")
            elif "alternate" in rel and a.get("hreflang"):
                self._perdue("link hreflang")

    def _perdue(self, balise):
        if balise not in self.ignorees:
            self.ignorees.append(balise)

    def texte(self, donnees, pile):
        if not donnees.strip(BLANCS):
            return
        if self.etat == AVANT:  # texte avant toute balise : tête implicite aussitôt fermée
            self.etat = FINI
        elif self.etat == TETE and self.interrompu is None and not ho.dans(pile, *BRUTS):
            self.interrompu = "#texte"

    def fin(self, noeud, pile):
        if noeud["tag"] == "head":
            self.etat = FINI

    def resultat(self):
        if self.interrompu and self.ignorees:
            return {"interruptions": [{"signature": "{0} puis : {1}".format(self.interrompu, ", ".join(self.ignorees)), "n": 1}]}
        return {"interruptions": []}


def grave(signature):
    """Vrai si la signature « <img> puis : link canonical, meta description » perd canonical, robots ou hreflang."""
    return any(p in PERTES_GRAVES for p in signature.split(" puis : ", 1)[-1].split(", "))


def issues(pages, add, ctx):
    groupes = ho.collecter_groupes(pages, NOM, "interruptions")
    libelle = "<head> interrompu par un élément invalide : les métadonnées suivantes sont ignorées par Google"
    # Un seul constat : sa sévérité est fixée par le premier ajout, donc les cas graves d'abord
    for severite, choisis in (("haute", True), ("moyenne", False)):
        ho.ajouter_groupes(add, "tete_interrompue", libelle, severite,
                           {s: g for s, g in groupes.items() if grave(s) == choisis}, "SEO technique")
