#!/usr/bin/env python3
"""fuites_rendu.py — Valeurs techniques affichées au visiteur : undefined, NaN, null, [object Object], {{ variable }}.
Typique d'un document Convex incomplet ou d'un champ renommé : la page est publiée avec « Prix : undefined € ».
Module du diffuseur html_observateurs (T3).

Le risque est le faux positif : un article qui explique `undefined`, « la valeur null en JavaScript » ou « NaN means
Not-a-Number » est du texte légitime. Un mot undefined / NaN / null n'est donc signalé que s'il se comporte comme une valeur
affichée, c'est-à-dire dans l'un de ces cas :
  - il remplit tout le texte d'un élément (<span>undefined</span>, <td>null</td>) ;
  - il touche un nombre, une monnaie ou une unité (« undefined € », « NaN min », « 12 undefined ») ;
  - il suit une étiquette courte et termine le texte (« Prix : undefined », « Places restantes : null ») ;
  - il remplit un attribut que l'utilisateur voit (alt, title, aria-label, value d'un champ visible) ;
  - il forme un segment d'URL ou une valeur de paramètre (/formations/undefined, ?id=null) dans href / src.
Un mot isolé dans un élément en ligne (<em>null</em>) au milieu d'une phrase d'au moins trois autres mots est de la prose.
[object Object] et {{ variable }} / ${variable} sont signalés dans tout texte visible.
Exclus : code, pre, kbd, samp, var, scripts (JSON-LD compris), styles, noscript, template, textarea, title et éléments masqués.
« nul » / « nulle » ne correspondent jamais : seul le mot exact null, NaN ou undefined compte."""
import re
from urllib.parse import parse_qsl, urlparse

import html_observateurs as ho

NOM = "fuites_rendu"
OBJET = re.compile(r"\[object Object\]")
JETON = re.compile(r"(?<![\w-])(undefined|NaN|null)(?![\w-])")
SEUL = re.compile(r"\W*(undefined|NaN|null)\W*")
GABARIT = re.compile(r"\{\{\s*[\w.]+\s*\}\}|\$\{[\w.]+\}")
SEGMENT = re.compile(r"(?:^|/)(undefined|null|NaN)(?=[/?#.]|$)")
VALEURS_URL = ("undefined", "null", "NaN")
EXCLUS = ("code", "pre", "kbd", "samp", "var")
SANS_ATTRIBUT = ("meta", "link", "base", "script", "style", "head", "html")
SCHEMAS_SANS_URL = ("data", "javascript", "mailto", "tel", "blob")
# <input> dont la valeur n'est pas écrite à l'écran
INPUT_SANS_VALEUR = {"hidden", "password", "checkbox", "radio", "file", "image", "color", "range"}

_UNITE = (r"(?:h|hr|hrs|heures?|min|mn|minutes?|sec|secondes?|jours?|j|semaines?|mois|ans|km|m|cm|mm|kg|g|ml|pers|personnes?"
          r"|places?|participants?|stagiaires?|avis|pts|points?|ko|mo|go|px|fois|séances?|sessions?|modules?|élèves|étudiants?"
          r"|eur|usd|euros?)")
APRES_VALEUR = re.compile(r"\s*(?:[€$£%‰]|\d|" + _UNITE + r"(?![^\W\d_]))", re.I)
AVANT_VALEUR = re.compile(r"[\d€$£%]\s*(?:[/x×+–-]\s*)?$")
ETIQUETTE = re.compile(r"(?:^|[.!?;]\s+)([^:.!?;]{1,30}?)\s*:\s*$")
FIN_OU_PONCTUATION = re.compile(r"[\s.,;!?)\]»”\"']*$|\s*[(\[]")
# Étiquettes d'un article (« Exemple : null ») : le mot qui suit illustre une notion, ce n'est pas une valeur affichée
ETIQUETTES_PEDAGOGIQUES = {
    "exemple", "exemples", "remarque", "remarques", "astuce", "attention", "définition", "syntaxe", "retour", "résultat", "résultats",
    "sortie", "valeur", "valeurs", "type", "types", "réponse", "erreur", "explication", "conseil", "cas", "output", "example",
    "examples", "result", "returns", "return", "value", "note technique", "valeur retournée", "valeur par défaut"}

# Éléments en ligne : leur texte se lit dans celui du bloc qui les contient
EN_LIGNE = {"a", "abbr", "b", "bdi", "bdo", "big", "button", "cite", "data", "del", "dfn", "em", "font", "i", "ins", "label", "mark",
            "option", "output", "q", "s", "small", "span", "strong", "sub", "summary", "sup", "time", "tt", "u"}
# En ligne, mais un jeton seul dedans reste une fuite même au milieu d'une phrase (lien, bouton, libellé : leur texte est une valeur)
EN_LIGNE_VALEUR = {"a", "button", "label", "option", "summary"}
MOTS_DE_PROSE = 3


def _norme(texte):
    return " ".join(texte.split())


def _extrait(t, debut, fin):
    if len(t) <= 60:
        return t
    a, b = max(0, debut - 25), min(len(t), fin + 30)
    return ("…" if a else "") + t[a:b] + ("…" if b < len(t) else "")


def _jeton_valeur(t, m):
    """Le mot trouvé en `m` se comporte-t-il comme une valeur affichée (et non comme un mot dans une phrase) ?"""
    avant, apres = t[:m.start()], t[m.end():]
    if not avant.strip(" \t\n\"'«»“”(") and not apres.strip(" \t\n\"'«»“”).,;:!?…"):
        return True  # le jeton remplit tout le texte
    if APRES_VALEUR.match(apres) or AVANT_VALEUR.search(avant):
        return True  # collé à un nombre, une monnaie ou une unité
    e = ETIQUETTE.search(avant)
    if e and e.group(1).strip().lower() not in ETIQUETTES_PEDAGOGIQUES and FIN_OU_PONCTUATION.match(apres):
        return True  # « Prix : undefined »
    return False


def fuite_texte(texte):
    """[(jeton, extrait)] des fuites d'un texte visible (liste vide si aucune). Un même texte peut en contenir plusieurs."""
    t = _norme(texte)
    if not t:
        return []
    res = []
    m = OBJET.search(t)
    if m:
        res.append(("[object Object]", _extrait(t, m.start(), m.end())))
    for m in GABARIT.finditer(t):
        res.append((m.group(0), _extrait(t, m.start(), m.end())))
    for m in JETON.finditer(t):
        if _jeton_valeur(t, m):
            res.append((m.group(1), _extrait(t, m.start(), m.end())))
    return res


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.fuites = {}

    def _ajouter(self, jeton, signature):
        cle = (jeton, signature)
        self.fuites[cle] = self.fuites.get(cle, 0) + 1

    def debut(self, noeud, pile):
        noeud["_t"], noeud["_c"] = [], []  # texte propre de l'élément (et des éléments en ligne qu'il contient), candidats
        if noeud["tag"] == "br" and pile and "_t" in pile[-1]:
            pile[-1]["_t"].append("\n")
        if noeud["masque"] or noeud["tag"] in SANS_ATTRIBUT or noeud["tag"] in EXCLUS or ho.dans(pile, *EXCLUS, "head"):
            return
        a = noeud["a"]
        for k in ("alt", "title", "aria-label"):
            self._attribut(k, a.get(k, ""))
        if noeud["tag"] == "input" and a.get("type", "text").strip().lower() not in INPUT_SANS_VALEUR:
            self._attribut("value", a.get("value", ""))
        for k in ("href", "src"):
            self._url(k, a.get(k, "").strip())

    def _attribut(self, nom, valeur):
        r = fuite_texte(valeur)
        if r:
            self._ajouter(r[0][0], '{0} — {1}="{2}"'.format(r[0][0], nom, _norme(valeur)[:60]))

    def _url(self, nom, valeur):
        if not valeur:
            return
        p = urlparse(valeur)
        if p.scheme.lower() in SCHEMAS_SANS_URL:
            return
        m = SEGMENT.search(p.path)
        jeton = m.group(1) if m else next((v for _, v in parse_qsl(p.query, keep_blank_values=True) if v in VALEURS_URL), None)
        if jeton:
            self._ajouter(jeton, "{0} — {1} {2}".format(jeton, nom, valeur[:60]))

    def texte(self, donnees, pile):
        if pile and "_t" in pile[-1] and ho.visible(pile) and not ho.dans(pile, *EXCLUS):
            pile[-1]["_t"].append(donnees)

    def fin(self, noeud, pile):
        if "_t" not in noeud or noeud["masque"]:
            return
        tag, parts, candidats = noeud["tag"], "".join(noeud["_t"]), noeud["_c"]
        en_ligne = (tag in EN_LIGNE or "-" in tag) and pile and "_t" in pile[-1]
        if en_ligne:
            m = SEUL.fullmatch(_norme(parts))
            if m:  # le jeton remplit cet élément : le bloc qui le contient décidera s'il s'agit d'une phrase ou d'une valeur
                candidats = [(m.group(1), tag in EN_LIGNE_VALEUR)]
            pile[-1]["_t"].append(" {0} ".format(parts) if tag in EN_LIGNE_VALEUR else parts)  # un lien ou un bouton ne colle pas aux mots voisins
            pile[-1]["_c"].extend(candidats)
            return
        t = _norme(parts)
        trouvees = fuite_texte(t)
        for jeton, extrait in trouvees:
            self._ajouter(jeton, "{0} — « {1} »".format(jeton, extrait))
        deja = {j for j, _ in trouvees}
        for jeton, fort in candidats:
            if jeton in deja:
                continue
            m = re.search(r"(?<![\w-])" + re.escape(jeton) + r"(?![\w-])", t)
            autres = len(re.findall(r"\w+", t[:m.start()] + " " + t[m.end():])) if m else 0
            if m and (fort or autres < MOTS_DE_PROSE):
                deja.add(jeton)
                self._ajouter(jeton, "{0} — « {1} »".format(jeton, _extrait(t, m.start(), m.end())))

    def resultat(self):
        return {"fuites": [{"signature": s, "n": n, "jeton": j}
                           for (j, s), n in sorted(self.fuites.items(), key=lambda x: (x[0][1], x[0][0]))]}


def issues(pages, add, ctx):
    ho.ajouter_groupes(add, "fuite_rendu", "Valeurs techniques affichées (undefined, NaN, null, [object Object]) : donnée manquante publiée",
                       "haute", ho.collecter_groupes(pages, NOM, "fuites"), "Contenu")
