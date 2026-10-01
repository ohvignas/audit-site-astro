#!/usr/bin/env python3
"""contenu_demo.py — Contenu de démonstration resté en ligne : lorem ipsum, « à remplacer par… », gabarit de démarrage,
coordonnées fictives. Lu dans le title, les descriptions (meta, og:, twitter:) et le texte visible (hors code/pre).
Module du diffuseur html_observateurs (T3).

Faux positifs écartés : texte de <code>, <pre>, <kbd>, <samp>, <q>, <cite>, scripts et éléments masqués ; expression citée entre
guillemets (« … », “ … ”, " … ") ; motifs en expressions entières et assez longues pour qu'un article ou une page sur le
« lorem ipsum » (le terme seul) ne soit pas signalé. « example.com » est volontairement absent (légitime dans un article technique)."""
import re

import html_observateurs as ho

NOM = "contenu_demo"
MOTIFS = (
    # le terme seul (« le lorem ipsum est un faux texte ») est légitime ; le passage de gabarit ne l'est pas
    ("lorem ipsum", re.compile(r"\blorem ipsum dolor\b|\bdolor sit amet\b|\bconsectetur adipiscing\b", re.I)),
    ("texte à remplacer", re.compile(r"\bà remplacer par (?:(?:la|le|les) v[oô]tres?|votre|vos|du vrai|le vrai|un vrai|le contenu)\b"
                                     r"|[\[(]\s*à remplacer\s*[\])]|\bremplacez[- ]moi\b"
                                     r"|\breplace (?:this (?:text|content|paragraph)|me\b|with your (?:own )?(?:text|content))", re.I)),
    ("page de démonstration", re.compile(r"\bpage de d[ée]monstration (?:livr[ée]e|fournie|du th[èe]me|de ce th[èe]me|par d[ée]faut|g[ée]n[ée]r[ée]e)\b"
                                         r"|\bdemo page (?:shipped|provided|included|that comes) with\b"
                                         r"|\bcontenu de d[ée]monstration\b|\b(?:texte|contenu) (?:factice|de remplissage)\b", re.I)),
    ("gabarit de démarrage", re.compile(r"\bWelcome to Astro\b|\bTo get started, open the directory\b|\bAstro Starter Kit\b", re.I)),
    ("coordonnées fictives", re.compile(r"\b(?:your|votre) (?:company|name|tagline|entreprise|slogan) (?:here|ici)\b|\bjohn\.doe@", re.I)),
)
EXCLUS = ("code", "pre", "kbd", "samp", "q", "cite")
DESCRIPTIONS = ("description", "og:description", "og:title", "twitter:description", "twitter:title")
FENETRE = 160  # caractères relus avant une occurrence pour savoir si elle est citée


def cite(texte, debut):
    """Vrai si l'occurrence en `debut` est dans une citation ouverte avant elle : « … », “ … ” ou " … " (parité des guillemets droits)."""
    avant = texte[max(0, debut - FENETRE):debut]
    return (avant.rfind("«") > avant.rfind("»") or avant.rfind("“") > avant.rfind("”")
            or avant.count('"') % 2 == 1)


def premiere_occurrence(rx, texte):
    for m in rx.finditer(texte):
        if not cite(texte, m.start()):
            return m
    return None


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.sources = {"titre": [], "description": [], "texte": []}
        self._titre = False

    def debut(self, noeud, pile):
        t, a = noeud["tag"], noeud["a"]
        if t == "title" and not ho.dans(pile, "svg"):
            self._titre = True
        elif t == "meta" and not noeud["masque"] and (a.get("name") or a.get("property") or "").lower() in DESCRIPTIONS:
            self.sources["description"].append(a.get("content", ""))

    def fin(self, noeud, pile):
        if noeud["tag"] == "title":
            self._titre = False

    def texte(self, donnees, pile):
        if self._titre:
            self.sources["titre"].append(donnees)
        elif ho.visible(pile) and not ho.dans(pile, *EXCLUS):
            self.sources["texte"].append(donnees)

    def resultat(self):
        out = []
        for ou in ("titre", "description", "texte"):
            t = " ".join(" ".join(self.sources[ou]).split())
            for motif, rx in MOTIFS:
                m = premiere_occurrence(rx, t)
                if m:
                    extrait = t[max(0, m.start() - 20):m.end() + 30]
                    out.append({"signature": "{0} ({1}) : « {2} »".format(motif, ou, extrait), "n": 1, "motif": motif, "ou": ou})
        return {"motifs": out}


def issues(pages, add, ctx):
    ho.ajouter_groupes(add, "contenu_demo", "Contenu de démonstration resté en ligne (lorem ipsum, « à remplacer », gabarit de démarrage)",
                       "moyenne", ho.collecter_groupes(pages, NOM, "motifs"), "Contenu")
