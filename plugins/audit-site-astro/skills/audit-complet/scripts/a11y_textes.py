#!/usr/bin/env python3
"""a11y_textes.py — Qualité des textes : libellés de lien génériques (RGAA 6.1, « à vérifier » : le contexte peut suffire),
textes alternatifs suspects (nom de fichier, identifiant, mot générique, double échappement HTML) et redondants
(alt identique au texte du lien ou à la légende). Module du diffuseur html_observateurs (T3)."""
import re

import html_observateurs as ho

NOM = "a11y_textes"
GENERIQUES = {"cliquez ici", "cliquer ici", "ici", "en savoir plus", "savoir plus", "lire la suite", "la suite", "suite",
              "voir plus", "plus", "lire plus", "découvrir", "voir", "lien", "cette page", "click here", "here", "read more",
              "learn more", "more", "see more", "link", "this page"}
MOTS_ALT = {"image", "img", "photo", "picture", "logo", "icon", "icône", "icone", "illustration", "graphic", "graphique",
            "untitled", "sans titre", "alt", "placeholder", "banner", "bannière", "visuel"}
FICHIER = re.compile(r"\.(jpe?g|png|gif|webp|avif|svg|bmp|tiff?)$", re.I)
CONTEXTE = ("aria-label", "aria-labelledby", "aria-describedby", "title")


def normaliser(t):
    return " ".join(re.sub(r"[.…:!?»«›→>|]+", " ", t.lower()).split())


def alt_suspect(alt):
    a = alt.strip()
    if not a:
        return None
    if FICHIER.search(a):
        return "nom de fichier"
    seps = len(re.findall(r"[-_]", a))
    if " " not in a and (seps >= 2 or (seps >= 1 and re.search(r"\d", a))):
        return "identifiant"
    if normaliser(a) in MOTS_ALT:
        return "mot générique"
    if re.search(r"&(amp|lt|gt|quot|#\d+);", a):
        return "double échappement"
    return None


def _ajouter(d, cle):
    d[cle] = d.get(cle, 0) + 1


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.liens, self.figures, self._legende = [], [], None
        self.generiques, self.suspects, self.redondants = {}, {}, {}

    def debut(self, noeud, pile):
        t, a = noeud["tag"], noeud["a"]
        if noeud["masque"]:
            return
        if t == "a" and "href" in a:
            self.liens.append({"noeud": noeud, "texte": [], "alts": [], "contexte": any(a.get(k, "").strip() for k in CONTEXTE)})
        elif t == "img" and a.get("alt") is not None:
            alt = a["alt"]
            raison = alt_suspect(alt)
            if raison:
                _ajouter(self.suspects, "{0} ({1})".format(alt.strip()[:80], raison))
            for conteneur in self.liens + self.figures:
                conteneur["alts"].append(alt)
        elif t == "figure":
            self.figures.append({"noeud": noeud, "alts": [], "legende": ""})
        elif t == "figcaption" and self.figures:
            self._legende = []

    def texte(self, donnees, pile):
        if not ho.visible(pile):
            return
        for lien in self.liens:
            lien["texte"].append(donnees)
        if self._legende is not None:
            self._legende.append(donnees)

    def fin(self, noeud, pile):
        if noeud["tag"] == "figcaption" and self._legende is not None:
            self.figures[-1]["legende"] = "".join(self._legende)
            self._legende = None
        elif self.figures and self.figures[-1]["noeud"] is noeud:
            f = self.figures.pop()
            for alt in f["alts"]:
                if normaliser(f["legende"]) and normaliser(alt) == normaliser(f["legende"]):
                    _ajouter(self.redondants, "« {0} » (légende)".format(alt.strip()[:80]))
        elif self.liens and self.liens[-1]["noeud"] is noeud:
            lien = self.liens.pop()
            txt = normaliser("".join(lien["texte"]))
            if not lien["contexte"] and txt in GENERIQUES:
                _ajouter(self.generiques, "« {0} »".format(txt))
            for alt in lien["alts"]:
                if txt and normaliser(alt) == txt:
                    _ajouter(self.redondants, "« {0} » (texte du lien)".format(alt.strip()[:80]))

    def resultat(self):
        conv = lambda d: [{"signature": k, "n": v} for k, v in sorted(d.items())]  # noqa: E731
        return {"liens_generiques": conv(self.generiques), "alt_suspects": conv(self.suspects), "alt_redondants": conv(self.redondants)}


def issues(pages, add, ctx):
    g = lambda champ: ho.collecter_groupes(pages, NOM, champ)  # noqa: E731
    ho.ajouter_groupes(add, "lien_generique", "Liens au texte générique (« cliquez ici », « en savoir plus ») — à vérifier, RGAA 6.1",
                       "basse", g("liens_generiques"), "Accessibilité")
    ho.ajouter_groupes(add, "alt_suspect", "Textes alternatifs suspects (nom de fichier, identifiant, mot générique, double échappement)",
                       "basse", g("alt_suspects"), "Accessibilité")
    ho.ajouter_groupes(add, "alt_redondant", "Textes alternatifs redondants (répètent le texte du lien ou la légende)", "basse",
                       g("alt_redondants"), "Accessibilité")
