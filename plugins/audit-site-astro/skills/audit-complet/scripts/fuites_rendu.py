#!/usr/bin/env python3
"""fuites_rendu.py — Valeurs techniques affichées au visiteur : undefined, NaN, null, [object Object], Invalid Date, {{ variable }}.
Typique d'un document Convex incomplet ou d'un champ renommé : la page est publiée avec « Prix : undefined € ».
Module du diffuseur html_observateurs (T3).

Le risque est le faux positif : un article qui explique `undefined`, « la valeur null en JavaScript » ou « NaN means
Not-a-Number » est du texte légitime. Un mot undefined / NaN / null n'est donc signalé que s'il se comporte comme une valeur
affichée. Deux familles de règles :
  - « valeur » (toujours actives) : le jeton touche un nombre, une monnaie ou une unité (« undefined € », « NaN min », « NaN inscrits »,
    « NaN/NaN/NaN »), suit une étiquette courte (« Prix : undefined », « Lieu : undefined, Paris »), ou suit une formule de politesse ou
    de signature (« Bonjour undefined », « Écrit par undefined le 12 mars »), ou forme une suite de jetons (« undefined undefined ») ;
  - « nu » : le jeton remplit tout le texte d'un élément (<span>undefined</span>, <td>null</td>), ou une fin d'alt/title/aria-label.
    Ces règles sont abandonnées sur une page technique (elle contient <code> ou <pre>) et quand trois jetons distincts apparaissent nus
    (liste « undefined, null, NaN » d'un tutoriel) : un tableau de types ou une liste de jetons y est de la documentation.
Un mot isolé dans un élément en ligne (<em>null</em>) au milieu d'une phrase d'au moins trois autres mots est de la prose.
Toujours signalés (hors code) : [object Object], Invalid Date, {{ variable }} / ${variable}, un alt/title/aria-label/placeholder/value
réduit au jeton, un segment d'URL /undefined, /null, /NaN (même hôte ou lien relatif seulement : un lien vers MDN n'en est pas une),
?id=undefined sur tout hôte, tel:undefined, mailto:undefined et [object Object] dans une URL.
<title>, meta description, og: et twitter: sont lus : le titre est coupé sur | - — – · » et un segment réduit au jeton est une fuite.
Exclus : code, pre, kbd, samp, var, scripts (JSON-LD compris), styles, noscript, template, textarea et éléments masqués.
« nul » / « nulle » ne correspondent jamais : seul le mot exact null, NaN ou undefined compte."""
import re
from urllib.parse import parse_qsl, unquote, unquote_plus, urlparse

import html_observateurs as ho

NOM = "fuites_rendu"
OBJET = re.compile(r"\[object Object\]")
DATE_INVALIDE = re.compile(r"(?<![\w-])Invalid Date(?![\w-])")
JETON = re.compile(r"(?<![\w-])(undefined|NaN|null)(?![\w-])")
INFINI = re.compile(r"(?<![\w])-?(Infinity)(?![\w-])")
SEUL = re.compile(r"\W*(undefined|NaN|null)\W*")
SUITE_JETONS = re.compile(r"\W*(undefined|NaN|null)(?:[\s/.\-]+(?:undefined|NaN|null))+\W*")
GABARIT = re.compile(r"\{\{\s*[\w.]+\s*\}\}|\$\{[\w.]+\}")
SEGMENT = re.compile(r"(?:^|/)(undefined|null|NaN)(?=[/?#.]|$)")
COURRIEL_TEL = re.compile(r"^(?:undefined|null|NaN)$|^undefined@|@(?:undefined|null|NaN)(?:\.|$)")
VALEURS_URL = ("undefined", "null", "NaN")
EXCLUS = ("code", "pre", "kbd", "samp", "var")
SANS_ATTRIBUT = ("meta", "link", "base", "script", "style", "head", "html")
SCHEMAS_SANS_URL = ("data", "javascript", "blob")
# <input> dont la valeur n'est pas écrite à l'écran
INPUT_SANS_VALEUR = {"hidden", "password", "checkbox", "radio", "file", "image", "color", "range"}
META_TITRE = {"og:title": "titre", "twitter:title": "titre", "description": "description", "og:description": "description",
              "twitter:description": "description"}
SEGMENT_TITRE = re.compile(r"\s*[|–—·»]\s*|\s+-\s+")
MAX_PAR_TEXTE = 20  # plafond de fuites relevées par bloc de texte : borne le coût d'un export collé dans la page

_UNITE = (r"(?:h|hr|hrs|heures?|min|mn|minutes?|sec|secondes?|jours?|j|semaines?|mois|ans|km|m|cm|mm|kg|g|ml|pers|personnes?"
          r"|places?|participants?|stagiaires?|inscrits?|abonnés?|avis|vues?|étoiles?|commentaires?|notes?|mises?|pts|points?|ko|mo|go|px"
          r"|fois|séances?|sessions?|modules?|élèves|étudiants?|eur|usd|euros?)")
APRES_VALEUR = re.compile(r"\s*(?:[€$£%‰]|\d|" + _UNITE + r"(?![^\W\d_]))", re.I)
AVANT_VALEUR = re.compile(r"[\d€$£%]\s*(?:[/x×+–-]\s*)?$")
APRES_SUITE = re.compile(r"\s*/\s*(?:undefined|NaN|null)(?![\w-])")
AVANT_SUITE = re.compile(r"(?<![\w-])(?:undefined|NaN|null)\s*/\s*$")
ETIQUETTE = re.compile(r"(?:^|[.!?;]\s+)([^:.!?;]{1,30}?)\s*:\s*$")
SALUTATION = re.compile(r"(?:(?:^|[.!?]\s+)(?:Bonjour|Bonsoir|Salut|Bienvenue|Hello|Hi|Hey|Coucou|Cher|Chère|Par|Auteur)"
                        r"|\b(?:écrit|posté|publié|rédigé|ajouté|créé|mis à jour) par)\s*,?\s*(?:à\s+)?$", re.I)
# Ce qui peut suivre un jeton qui termine un texte : ponctuation, autres jetons, « , Paris », « le 12 mars », parenthèse
FIN = re.compile(r"(?:[\s,/.\-]+(?:undefined|NaN|null)(?![\w-]))*[\s.,;!?)\]»”\"']*$|\s*[(\[]|\s*,\s*\S|\s+(?:le|du|au|à|depuis)\s+\d")
# Étiquettes d'un article (« Exemple : null ») : le mot qui suit illustre une notion, ce n'est pas une valeur affichée
ETIQUETTES_PEDAGOGIQUES = {
    "exemple", "exemples", "remarque", "remarques", "astuce", "attention", "définition", "syntaxe", "retour", "résultat", "résultats",
    "sortie", "valeur", "valeurs", "type", "types", "réponse", "erreur", "explication", "conseil", "cas", "output", "example",
    "examples", "result", "returns", "return", "value", "note technique", "valeur retournée", "valeur par défaut", "par défaut",
    "default", "défaut", "number", "string", "boolean", "object", "array", "bigint", "symbol", "function", "nombre", "chaîne",
    "booléen", "tableau", "fonction", "q", "r"}
# Une étiquette de valeur est un à quatre mots, sans opérateur : « La propriété renvoie la valeur : null » est une phrase
ETIQUETTE_VALIDE = re.compile(r"[^\W\d_][^*+=<>/'\"()]*$")

# Éléments en ligne : leur texte se lit dans celui du bloc qui les contient
EN_LIGNE = {"a", "abbr", "b", "bdi", "bdo", "big", "button", "cite", "data", "del", "dfn", "em", "font", "i", "ins", "label", "mark",
            "option", "output", "q", "s", "small", "span", "strong", "sub", "summary", "sup", "time", "tt", "u"}
# En ligne, mais un jeton seul dedans reste une fuite même au milieu d'une phrase (lien, bouton, libellé : leur texte est une valeur)
EN_LIGNE_VALEUR = {"a", "button", "label", "option", "summary"}
MOTS_DE_PROSE = 3
FENETRE = 200  # caractères comptés de part et d'autre d'un jeton pour décider s'il est au milieu d'une phrase


def _norme(texte):
    return " ".join(texte.split())


def _extrait(t, debut, fin):
    if len(t) <= 60:
        return t
    a, b = max(0, debut - 25), min(len(t), fin + 30)
    return ("…" if a else "") + t[a:b] + ("…" if b < len(t) else "")


def _colle_a_une_valeur(avant, apres):
    return bool(APRES_VALEUR.match(apres) or AVANT_VALEUR.search(avant) or APRES_SUITE.match(apres) or AVANT_SUITE.search(avant))


def _etiquette_de_valeur(etiquette):
    e = etiquette.strip()
    return (len(e) >= 3 and len(e.split()) <= 4 and e.lower() not in ETIQUETTES_PEDAGOGIQUES and bool(ETIQUETTE_VALIDE.match(e)))


def _type_jeton(t, m):
    """Type de la fuite que forme le mot trouvé en `m` dans le texte `t` : "valeur", "nu", ou None (c'est un mot dans une phrase)."""
    avant, apres = t[max(0, m.start() - 60):m.start()], t[m.end():]
    if _colle_a_une_valeur(avant, apres):
        return "valeur"
    e = ETIQUETTE.search(avant[-50:])
    if e and _etiquette_de_valeur(e.group(1)) and FIN.match(apres):
        return "valeur"  # « Prix : undefined »
    if SALUTATION.search(avant[-40:]) and FIN.match(apres):
        return "valeur"  # « Bonjour undefined », « Écrit par undefined le 12 mars »
    return None


def fuite_texte(texte):
    """[(jeton, extrait, type)] des fuites d'un texte visible (liste vide si aucune). type : "objet" (toujours une fuite), "valeur"
    (jeton collé à une valeur ou à une étiquette) ou "nu" (jeton qui remplit tout le texte)."""
    t = _norme(texte)
    if not t:
        return []
    res = []
    for rx, jeton in ((OBJET, "[object Object]"), (DATE_INVALIDE, "Invalid Date")):
        m = rx.search(t)
        if m:
            res.append((jeton, _extrait(t, m.start(), m.end()), "objet"))
    for m in GABARIT.finditer(t):
        res.append((m.group(0), _extrait(t, m.start(), m.end()), "objet"))
    m = SUITE_JETONS.fullmatch(t)
    if m:  # « undefined undefined », « NaN/NaN/NaN »
        return res + [(m.group(1), t[:60], "nu")]
    m = SEUL.fullmatch(t)
    if m:  # le jeton remplit tout le texte
        return res + [(m.group(1), t[:60], "valeur" if _colle_a_une_valeur(t[:m.start(1)], t[m.end(1):]) else "nu")]
    for m in INFINI.finditer(t):  # Infinity n'est une fuite que collé à une valeur
        if _colle_a_une_valeur(t[max(0, m.start() - 60):m.start()], t[m.end():]):
            res.append(("Infinity", _extrait(t, m.start(), m.end()), "valeur"))
    for m in JETON.finditer(t):
        if len(res) >= MAX_PAR_TEXTE:
            break
        typ = _type_jeton(t, m)
        if typ:
            res.append((m.group(1), _extrait(t, m.start(), m.end()), typ))
    return res


def _meme_hote(netloc, url_page):
    def norme(h):
        h = h.lower()
        return h[4:] if h.startswith("www.") else h
    return not netloc or norme(netloc) == norme(urlparse(url_page).netloc)


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.fuites = {}
        self.technique = False  # la page contient <code> ou <pre>
        self.titres = {"titre": [], "description": []}
        self._titre = []

    def _ajouter(self, jeton, signature, typ):
        cle = (jeton, signature, typ)
        self.fuites[cle] = self.fuites.get(cle, 0) + 1

    def debut(self, noeud, pile):
        noeud["_t"], noeud["_c"] = [], []  # texte propre de l'élément (et des éléments en ligne qu'il contient), candidats
        tag, a = noeud["tag"], noeud["a"]
        if tag in ("code", "pre"):
            self.technique = True
        if tag == "br" and pile and "_t" in pile[-1]:
            pile[-1]["_t"].append("\n")
        if tag == "meta" and not noeud["masque"]:
            cle = (a.get("property") or a.get("name") or "").strip().lower()
            if cle in META_TITRE:
                self.titres[META_TITRE[cle]].append(a.get("content", ""))
        if noeud["masque"] or tag in SANS_ATTRIBUT or tag in EXCLUS or ho.dans(pile, *EXCLUS, "head"):
            return
        for k in ("alt", "title", "aria-label", "placeholder"):
            self._attribut(k, a.get(k, ""), fin_de_phrase=k != "placeholder")
        self._attribut("datetime", a.get("datetime", ""))
        if tag == "input" and a.get("type", "text").strip().lower() not in INPUT_SANS_VALEUR:
            self._attribut("value", a.get("value", ""))
        for k in ("href", "src"):
            self._url(k, a.get(k, "").strip())

    def _attribut(self, nom, valeur, fin_de_phrase=False):
        if not valeur:
            return
        r = fuite_texte(valeur)
        if r:
            jeton = r[0][0]
            self._ajouter(jeton, '{0} — {1}="{2}"'.format(jeton, nom, _norme(valeur)[:60]), "attribut")
            return
        if fin_de_phrase:  # alt="Photo de undefined" : un alt décrit une image, il ne parle presque jamais de JavaScript
            fin = re.search(r"(?<![\w-])(undefined|NaN|null)\W*$", _norme(valeur))
            if fin:
                self._ajouter(fin.group(1), '{0} — {1}="{2}"'.format(fin.group(1), nom, _norme(valeur)[:60]), "fin_attribut")

    def _url(self, nom, valeur):
        if not valeur:
            return
        try:
            p = urlparse(valeur)
        except ValueError:
            return
        schema = p.scheme.lower()
        if schema in SCHEMAS_SANS_URL:
            return
        jeton = None
        if schema in ("tel", "mailto"):
            reste = unquote(p.path).strip()
            jeton = next((j for j in VALEURS_URL if j in reste), None) if COURRIEL_TEL.search(reste) else None
        else:
            if OBJET.search(unquote_plus(valeur)):
                jeton = "[object Object]"
            elif _meme_hote(p.netloc, self.url):
                m = SEGMENT.search(p.path)
                jeton = m.group(1) if m else None
            if jeton is None:  # une valeur de paramètre est une fuite quel que soit l'hôte
                jeton = next((v for _, v in parse_qsl(p.query, keep_blank_values=True) if v in VALEURS_URL), None)
        if jeton:
            self._ajouter(jeton, "{0} — {1} {2}".format(jeton, nom, valeur[:60]), "url")

    def texte(self, donnees, pile):
        if pile and pile[-1]["tag"] == "title" and not ho.dans(pile, "svg"):
            self._titre.append(donnees)
        elif pile and "_t" in pile[-1] and ho.visible(pile) and not ho.dans(pile, *EXCLUS):
            pile[-1]["_t"].append(donnees)

    def fin(self, noeud, pile):
        if "_t" not in noeud or noeud["masque"]:
            return
        tag, parts, candidats = noeud["tag"], "".join(noeud["_t"]), noeud["_c"]
        en_ligne = (tag in EN_LIGNE or "-" in tag) and pile and "_t" in pile[-1]
        seul = SEUL.fullmatch(_norme(parts)) if en_ligne else None
        if seul:  # le jeton remplit cet élément : le bloc qui le contient décidera s'il s'agit d'une phrase ou d'une valeur
            candidats = [(seul.group(1), tag in EN_LIGNE_VALEUR)]
        elif tag == "button":  # <button>S'inscrire à undefined</button> : le libellé d'un bouton ne parle pas de JavaScript
            fin_bouton = re.search(r"(?<![\w-])(undefined|NaN|null)\W*$", _norme(parts))
            if fin_bouton and len(parts.split()) <= 8:
                candidats = [(fin_bouton.group(1), True)]
        if en_ligne:
            # un lien, un bouton ou un jeton seul ne colle pas aux mots voisins : la signature ne dépend pas des espaces du gabarit
            pile[-1]["_t"].append(" {0} ".format(parts) if (tag in EN_LIGNE_VALEUR or seul) else parts)
            pile[-1]["_c"].extend(candidats)
            return
        t = _norme(parts)
        trouvees = fuite_texte(t)
        for jeton, extrait, typ in trouvees:
            self._ajouter(jeton, "{0} — « {1} »".format(jeton, extrait), typ)
        deja = {j for j, _, _ in trouvees}
        vus = 0
        for jeton, fort in candidats:
            if jeton in deja or vus >= MAX_PAR_TEXTE:
                continue
            vus += 1
            m = re.search(r"(?<![\w-])" + re.escape(jeton) + r"(?![\w-])", t)
            if not m:
                continue
            voisinage = t[max(0, m.start() - FENETRE):m.start()] + " " + t[m.end():m.end() + FENETRE]
            if fort or len(re.findall(r"\w+", voisinage)) < MOTS_DE_PROSE:
                deja.add(jeton)
                self._ajouter(jeton, "{0} — « {1} »".format(jeton, _extrait(t, m.start(), m.end())), "nu")

    def _lire_titres(self):
        if self._titre:
            self.titres["titre"].append("".join(self._titre))
        vus = set()
        for libelle, valeurs in sorted(self.titres.items()):
            for v in valeurs:
                v = _norme(v)
                for seg in SEGMENT_TITRE.split(v):
                    for jeton, _, typ in fuite_texte(seg):
                        if (jeton, libelle, v) not in vus:  # même fuite dans <title>, og:title et twitter:title : un constat
                            vus.add((jeton, libelle, v))
                            self._ajouter(jeton, "{0} — {1} « {2} »".format(jeton, libelle, v[:60]), "nu_titre" if typ == "nu" else typ)

    def resultat(self):
        self._lire_titres()
        f = self.fuites
        nus = {j for (j, _, typ) in f if typ == "nu"}
        if self.technique or len(nus) >= 3:  # page technique ou liste de jetons : un jeton nu y est de la documentation
            f = {c: n for c, n in f.items() if c[2] not in ("nu", "nu_titre", "fin_attribut")}
        agreges = {}
        for (j, s, _), n in f.items():
            agreges[(j, s)] = agreges.get((j, s), 0) + n
        return {"fuites": [{"signature": s, "n": n, "jeton": j} for (j, s), n in sorted(agreges.items(), key=lambda x: (x[0][1], x[0][0]))]}


def issues(pages, add, ctx):
    ho.ajouter_groupes(add, "fuite_rendu", "Valeurs techniques affichées (undefined, NaN, null, [object Object], Invalid Date) : donnée manquante publiée",
                       "haute", ho.collecter_groupes(pages, NOM, "fuites"), "Contenu")
