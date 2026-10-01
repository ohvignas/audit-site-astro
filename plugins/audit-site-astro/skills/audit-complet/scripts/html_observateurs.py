#!/usr/bin/env python3
"""
html_observateurs.py — Contrôles HTML du crawl en un seul passage du parseur (Python 3.9+, stdlib).

crawl_site.py appelle, pour chaque page HTML analysée :
  analyser(html, entetes, url)  -> {nom_module: résultat JSON}   (pages.json, clé « obs » de chaque page)
puis, une fois le crawl terminé :
  apres_crawl(pages, ctx)       -> requêtes réseau éventuelles des modules (liens externes, ressources…)
  issues(pages, add, ctx)       -> constats ajoutés à issues.json par add(clé, libellé, sévérité, exemple, n=, domaine=)

Un module de MODULES fournit NOM, une classe Observateur (sous-classe de Observateur) et, au besoin, apres_crawl(pages, ctx)
et issues(pages, add, ctx). Une erreur dans un module n'interrompt jamais le crawl (notée dans ctx["meta"]["erreurs_modules"]).
Format commun des résultats : listes de {"signature": str, "n": int, …} ; collecter_groupes() et ajouter_groupes() regroupent
les occurrences de tout le site par signature de composant (128 icônes identiques = 1 constat).
"""
import importlib
import re
from html.parser import HTMLParser

MODULES = ("a11y_svg", "a11y_noms", "a11y_structure", "a11y_textes", "contenu_demo", "fuites_rendu", "tete_html",
           "securite_html", "liens_externes", "ressources_site", "donnees_structurees")

# Éléments sans balise fermante (ne s'empilent pas) ; styles qui masquent un élément
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
STYLE_MASQUE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)
# Classes utilitaires qui masquent (Tailwind, Bootstrap, Bulma) : jetons entiers ; sr-only n'en fait PAS partie
# (masqué visuellement mais lu par les lecteurs d'écran : un libellé reste requis)
CLASSES_MASQUE = {"hidden", "d-none", "is-hidden", "invisible"}
# « hidden md:block » : masqué sur mobile seulement, visible ensuite → pas masqué
CLASSE_REAFFICHE = re.compile(r"^(sm|md|lg|xl|2xl):(block|inline|inline-block|flex|inline-flex|grid|inline-grid|table|contents|visible)$")
SANS_TEXTE_VISIBLE = {"script", "style", "noscript", "template", "textarea", "title"}


def masque(tag, a):
    """Élément absent de l'arbre d'accessibilité (ignoré par axe/Lighthouse) : hidden, aria-hidden, style, classe
    utilitaire de masquage, <template>, <noscript>, <dialog> fermé."""
    classes = a.get("class", "").split()
    par_classe = bool(CLASSES_MASQUE.intersection(classes)) and not any(CLASSE_REAFFICHE.match(c) for c in classes)
    return (tag in ("template", "noscript") or (tag == "dialog" and "open" not in a) or "hidden" in a
            or a.get("aria-hidden", "").lower() == "true" or bool(STYLE_MASQUE.search(a.get("style", "")))
            or par_classe)


class Observateur:
    """Base des observateurs : méthodes vides, à surcharger."""

    def __init__(self, entetes, url):
        self.entetes, self.url = entetes or {}, url

    def debut(self, noeud, pile):
        pass

    def fin(self, noeud, pile):
        pass

    def texte(self, donnees, pile):
        pass

    def resultat(self):
        return {}


def dans(pile, *tags):
    return any(n["tag"] in tags for n in pile)


def visible(pile):
    return not (pile and pile[-1]["masque"]) and not dans(pile, *SANS_TEXTE_VISIBLE)


EVENEMENTS = ("debut", "fin", "texte")


def _surcharge(o, methode):
    f = getattr(type(o), methode, None)
    return f is not None and f is not getattr(Observateur, methode)


class Diffuseur(HTMLParser):
    """Parcourt le HTML une fois et transmet les événements à chaque observateur, avec la pile des ancêtres."""

    def __init__(self, observateurs):
        super().__init__(convert_charrefs=True)
        self.obs, self.pile, self.erreurs = list(observateurs), [], {}
        # Table d'envoi par événement : seuls les observateurs qui surchargent la méthode sont appelés (un module qui
        # n'écoute que <a> et <svg> ne coûte rien sur les événements de texte)
        self._envoi = {m: [(o, getattr(o, m)) for o in self.obs if _surcharge(o, m)] for m in EVENEMENTS}

    def _notifier(self, methode, *args):
        for o, f in list(self._envoi[methode]):
            try:
                f(*args)
            except Exception as e:  # observateur fautif : retiré partout, les autres continuent
                self.erreurs[id(o)] = "{0}: {1}".format(type(e).__name__, e)[:200]
                self.obs.remove(o)
                for m in EVENEMENTS:
                    self._envoi[m] = [c for c in self._envoi[m] if c[0] is not o]

    def _noeud(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        return {"tag": tag, "a": a, "masque": bool(self.pile and self.pile[-1]["masque"]) or masque(tag, a)}

    def handle_starttag(self, tag, attrs):
        noeud = self._noeud(tag, attrs)
        self._notifier("debut", noeud, self.pile)
        if tag in VOID_TAGS:
            self._notifier("fin", noeud, self.pile)
        else:
            self.pile.append(noeud)

    def handle_startendtag(self, tag, attrs):
        noeud = self._noeud(tag, attrs)
        self._notifier("debut", noeud, self.pile)
        self._notifier("fin", noeud, self.pile)

    def handle_endtag(self, tag):
        for i in range(len(self.pile) - 1, -1, -1):
            if self.pile[i]["tag"] == tag:  # ferme aussi les éléments laissés ouverts (<li>, <p>…)
                while len(self.pile) > i:
                    self._notifier("fin", self.pile.pop(), self.pile)
                return

    def handle_data(self, data):
        self._notifier("texte", data, self.pile)

    def analyser(self, html):
        try:
            self.feed(html)
            self.close()
        except Exception as e:  # HTML impossible à lire jusqu'au bout : on garde ce qui a été vu
            for o in self.obs:
                self.erreurs.setdefault(id(o), "parse: {0}".format(e)[:200])
        while self.pile:
            self._notifier("fin", self.pile.pop(), self.pile)


_CHARGES = []


def modules():
    if not _CHARGES:
        _CHARGES.extend((nom, importlib.import_module(nom)) for nom in MODULES)
    return _CHARGES


def analyser(html, entetes, url, modules=None):
    obs = []
    for nom, mod in (modules if modules is not None else globals()["modules"]()):
        cls = getattr(mod, "Observateur", None)
        if cls is not None:
            obs.append((nom, cls(entetes, url)))
    d = Diffuseur([o for _, o in obs])
    d.analyser(html)
    res = {}
    for nom, o in obs:
        if id(o) in d.erreurs and o not in d.obs:
            res[nom] = {"erreur": d.erreurs[id(o)]}
            continue
        try:
            res[nom] = o.resultat()
        except Exception as e:
            res[nom] = {"erreur": "{0}: {1}".format(type(e).__name__, e)[:200]}
    return res


def _appeler(nom_fonction, ctx, *args):
    for nom, mod in modules():
        f = getattr(mod, nom_fonction, None)
        if f is None:
            continue
        try:
            f(*args)
        except Exception as e:
            ctx.setdefault("meta", {}).setdefault("erreurs_modules", {})[nom] = "{0}: {1}".format(type(e).__name__, e)[:200]


def apres_crawl(pages, ctx):
    _appeler("apres_crawl", ctx, pages, ctx)


def issues(pages, add, ctx):
    _appeler("issues", ctx, pages, add, ctx)


def collecter_groupes(pages, nom, champ):
    """{signature: {"n": occurrences, "pages": [url…]}} pour obs[nom][champ] de toutes les pages."""
    groupes = {}
    for u, p in pages.items():
        for e in ((p.get("obs") or {}).get(nom) or {}).get(champ, []):
            g = groupes.setdefault(e["signature"], {"n": 0, "pages": []})
            g["n"] += e.get("n", 1)
            g["pages"].append(u)
            if "exemple" in e and "exemple" not in g:
                g["exemple"] = e["exemple"]
    return groupes


def ajouter_groupes(add, cle, libelle, severite, groupes, domaine):
    """Un constat par signature (ordre trié = sortie déterministe), avec 3 pages d'exemple."""
    for sig in sorted(groupes):
        g = groupes[sig]
        urls = sorted(set(g["pages"]))
        exemple = {"signature": sig, "occurrences": g["n"], "pages": len(urls), "exemples_pages": urls[:3]}
        if "exemple" in g:
            exemple["exemple"] = g["exemple"]
        add(cle, libelle, severite, exemple, n=g["n"], domaine=domaine)
