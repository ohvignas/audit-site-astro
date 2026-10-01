#!/usr/bin/env python3
"""a11y_textes.py — Qualité des textes : libellés de lien génériques (RGAA 6.1, « à vérifier » : le contexte peut suffire),
textes alternatifs suspects (nom de fichier, identifiant, mot générique, double échappement HTML) et redondants
(alt identique au texte du lien ou à la légende). Module du diffuseur html_observateurs (T3)."""
import re
import unicodedata

import html_observateurs as ho

NOM = "a11y_textes"
GENERIQUES = {"cliquez ici", "cliquer ici", "ici", "en savoir plus", "savoir plus", "lire la suite", "la suite", "suite",
              "voir plus", "plus", "lire plus", "découvrir", "voir", "lien", "cette page", "click here", "here", "read more",
              "learn more", "more", "see more", "link", "this page"}
MOTS_ALT = {"image", "img", "photo", "picture", "logo", "icon", "icône", "icone", "illustration", "graphic", "graphique",
            "untitled", "sans titre", "alt", "placeholder", "banner", "bannière", "visuel"}
FICHIER = re.compile(r"\.(jpe?g|png|gif|webp|avif|svg|bmp|tiff?|heic)$", re.I)
# Noms d'appareil photo (IMG_1234, DSC_0042, PXL_20240101_…) et condensats (UUID, ≥ 12 caractères hexadécimaux)
APPAREIL = re.compile(r"^(IMG|DSCF?N?|PXL|MVIMG|VID)[ _-]?\d{3,}([_-][0-9a-z]+)*$", re.I)
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
CONDENSAT = re.compile(r"(?<![0-9a-f])(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{12,}(?![0-9a-f])", re.I)
NUMEROTE = re.compile(r"^(image|img|photo|picture|logo|icon)\s*\d+$")
ENTITE = re.compile(r"&(#x?[0-9a-f]+|[a-z][a-z0-9]{1,8});", re.I)
CONTEXTE_TEXTE = ("aria-label", "title")
CONTEXTE_ID = ("aria-labelledby", "aria-describedby")
APOSTROPHES = "\u2018\u2019\u02bc\u2032`\u00b4"


def normaliser(t):
    """Minuscules, Unicode NFKC (NBSP, formes composées), apostrophes typographiques unifiées, ponctuation, symboles
    (flèches, guillemets, ↗…) et caractères de format (U+200B, U+00AD) retirés, espaces repliés."""
    t = unicodedata.normalize("NFKC", t)
    for c in APOSTROPHES:
        t = t.replace(c, "'")
    t = "".join(" " if c != "'" and unicodedata.category(c)[0] in "PSC" and not c.isspace() else c for c in t)
    return " ".join(m.strip("'") for m in t.casefold().split())


def _propre(alt):
    """Alt lisible : NFKC, espaces (NBSP, retours à la ligne) repliés."""
    return " ".join(unicodedata.normalize("NFKC", alt).split())


def alt_suspect(alt):
    a = _propre(alt)
    if not a:
        return None
    if FICHIER.search(a):
        return "nom de fichier"
    if APPAREIL.match(a) or (" " not in a and (UUID.search(a) or CONDENSAT.search(a))):
        return "identifiant"
    n = normaliser(a)
    if n in MOTS_ALT or NUMEROTE.match(n):
        return "mot générique"
    if ENTITE.search(a):
        return "double échappement"
    return None


def contexte(a):
    """Contexte fourni par l'auteur : aria-labelledby / aria-describedby non vides, ou aria-label / title qui ne répètent pas
    simplement un libellé générique."""
    if any(a.get(k, "").strip() for k in CONTEXTE_ID):
        return True
    return any(normaliser(a.get(k, "")) not in GENERIQUES | {""} for k in CONTEXTE_TEXTE)


def _ajouter(d, cle):
    d[cle] = d.get(cle, 0) + 1


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.liens, self.figures, self._legende = [], [], None
        self.generiques, self.suspects, self.redondants = {}, {}, {}
        self.vus = []  # (href, libellé générique ou None) de chaque lien, pour écarter les liens jumeaux explicites

    def debut(self, noeud, pile):
        t, a = noeud["tag"], noeud["a"]
        if noeud["masque"]:
            return
        if t == "a" and "href" in a:
            self.liens.append({"noeud": noeud, "texte": [], "alts": [], "contexte": contexte(a), "href": a["href"].strip()})
        elif t == "img" and a.get("alt") is not None:
            alt = a["alt"]
            raison = alt_suspect(alt)
            if raison:
                _ajouter(self.suspects, "{0} ({1})".format(_propre(alt)[:80], raison))
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
                    _ajouter(self.redondants, "« {0} » (légende)".format(_propre(alt)[:80]))
        elif self.liens and self.liens[-1]["noeud"] is noeud:
            lien = self.liens.pop()
            txt = normaliser("".join(lien["texte"]))
            # nom accessible : texte + alt des images (« <a><img alt="Formation Bubble"> En savoir plus</a> » est explicite)
            nom = normaliser(" ".join(["".join(lien["texte"])] + lien["alts"]))
            generique = nom if (not lien["contexte"] and nom in GENERIQUES) else None
            self.vus.append((lien["href"], generique, bool(nom)))
            for alt in lien["alts"]:
                if txt and normaliser(alt) == txt:
                    _ajouter(self.redondants, "« {0} » (texte du lien)".format(_propre(alt)[:80]))

    def resultat(self):
        # Un lien générique dont la même destination a aussi un lien explicite sur la page (carte : titre + « Lire la suite »)
        # est compris par le contexte (RGAA 6.1) : non compté.
        explicites = {h for h, g, nomme in self.vus if g is None and nomme and h not in ("", "#")}
        groupes = {}
        for h, g, _ in self.vus:
            if g is not None and (h in ("", "#") or h not in explicites):
                e = groupes.setdefault("« {0} »".format(g), {"n": 0, "hrefs": set()})
                e["n"] += 1
                e["hrefs"].add(h)
        generiques = [{"signature": k, "n": v["n"], "exemple": "{0} lien{1}, {2} destination{3}".format(
            v["n"], "s" if v["n"] > 1 else "", len(v["hrefs"]), "s" if len(v["hrefs"]) > 1 else "")}
            for k, v in sorted(groupes.items())]
        conv = lambda d: [{"signature": k, "n": v} for k, v in sorted(d.items())]  # noqa: E731
        return {"liens_generiques": generiques, "alt_suspects": conv(self.suspects), "alt_redondants": conv(self.redondants)}


def issues(pages, add, ctx):
    g = lambda champ: ho.collecter_groupes(pages, NOM, champ)  # noqa: E731
    ho.ajouter_groupes(add, "lien_generique", "Liens au texte générique (« cliquez ici », « en savoir plus ») — à vérifier, RGAA 6.1",
                       "basse", g("liens_generiques"), "Accessibilité")
    ho.ajouter_groupes(add, "alt_suspect", "Textes alternatifs suspects (nom de fichier, identifiant, mot générique, double échappement)",
                       "basse", g("alt_suspects"), "Accessibilité")
    ho.ajouter_groupes(add, "alt_redondant", "Textes alternatifs redondants (répètent le texte du lien ou la légende)", "basse",
                       g("alt_redondants"), "Accessibilité")
