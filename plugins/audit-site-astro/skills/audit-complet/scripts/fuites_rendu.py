#!/usr/bin/env python3
"""fuites_rendu.py — Valeurs techniques affichées au visiteur : undefined, NaN, null, [object Object], Invalid Date, {{ variable }}.
Typique d'un document Convex incomplet ou d'un champ renommé : la page est publiée avec « Prix : undefined € ».
Module du diffuseur html_observateurs (T3).

Le risque est le faux positif : un article qui explique `undefined`, « la valeur null en JavaScript » ou « NaN means
Not-a-Number » est du texte légitime. Un mot undefined / NaN / null n'est donc signalé que s'il se comporte comme une valeur
affichée. Deux clés de constat :
  - fuite_rendu (haute) : le jeton touche un nombre, une monnaie ou une unité (« undefined € », « NaN min », « NaN inscrits »,
    « NaN/NaN/NaN »), suit une étiquette courte (« Prix : undefined », « Lieu : undefined, Paris »), une formule de politesse, de
    signature ou de date (« Bonjour undefined », « Écrit par undefined », « Ajouté le undefined », « Du undefined au undefined »), ou
    forme une suite de jetons (« undefined undefined ») ; [object Object], Invalid Date, {{ variable }} / ${variable} (hors code) ;
    un alt/title/aria-label/placeholder/value réduit au jeton ; un segment d'URL /undefined, /null, /NaN (même hôte ou lien relatif
    seulement : un lien vers MDN n'en est pas une), ?id=undefined sur tout hôte, tel:undefined, mailto:undefined, [object Object]
    dans une URL ; le <title>, la meta description, og: et twitter: (coupés sur | - — – · », un segment réduit au jeton ou fini par
    un jeton est une fuite), évalués sur toute page, technique ou non ;
  - fuite_rendu_isolee (basse) : le jeton remplit tout le texte d'un élément (<td>null</td>, <li>undefined</li>, <h3>undefined</h3>,
    <span>NaN</span>), ou termine un alt/title/aria-label/libellé de bouton. Ces constats sont marqués "isolee": true dans la liste.
    Ils ne sont jamais supprimés : un tutoriel sans <code> en produit au pire quelques-uns à vérifier ; une carte Convex à champs vides
    (prix, note, stock) en produit autant que de champs. Le test de la page ne les masque pas.
Un mot isolé dans un élément en ligne (<em>null</em>) au milieu d'une phrase d'au moins trois autres mots est de la prose.
Les liens externes à identifiant manquant (https://wa.me/undefined) ne sont pas signalés : un lien vers la documentation d'un autre site
(MDN, /Global_Objects/undefined) n'est pas une fuite, et le segment n'est lu que sur le site audité.
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
TYPES_ISOLES = ("nu", "fin_attribut")  # gravité basse : clé fuite_rendu_isolee
FIN_DE_TITRE = re.compile(r"(?<![\w-])(undefined|NaN|null)[\s.!]*$")
# Mot qui précède un jeton dans une phrase de titre (« Tout savoir sur undefined », « Le rôle de null ») : le titre parle du jeton
MOTS_DE_PHRASE = {"de", "du", "des", "que", "qu", "le", "la", "les", "l", "en", "à", "au", "aux", "sur", "et", "ou", "vs", "avec", "sans",
                  "pour", "par", "ce", "cet", "cette", "un", "une", "pourquoi", "comment", "quand", "si", "is", "the", "of", "about", "and",
                  "with", "to", "a", "an", "what", "why", "how", "or", "valeur", "type", "mot", "variable", "propriété", "erreur", "constante",
                  "résultat", "value", "type", "keyword", "error", "variable"}
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
                        r"|\b(?:écrit|posté|publié|rédigé|ajouté|créé|mis à jour) par"
                        r"|\b(?:ajouté|publié|créé|modifié|posté|édité|écrit|rédigé|mis à jour|mise à jour)\s+(?:le|en))\s*[,:]?\s*(?:à\s+)?$", re.I)
# « Du undefined au undefined », « Entre le NaN et le NaN » : début d'une période dont les deux bornes manquent
DEBUT_PERIODE = re.compile(r"(?:^|[.!?]\s+)(?:Du|De|Entre le)\s*$", re.I)
APRES_BORNE = re.compile(r"\s+(?:au|à|et)\s+(?:le\s+)?(?:undefined|NaN|null)(?![\w-])")
AVANT_BORNE = re.compile(r"(?:^|[.!?]\s+)(?:Du|De|Entre le)\s+(?:undefined|NaN|null)\s+(?:au|à|et)\s+(?:le\s+)?$", re.I)
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
        return "valeur"  # « Bonjour undefined », « Écrit par undefined le 12 mars », « Ajouté le undefined »
    if (DEBUT_PERIODE.search(avant[-12:]) and APRES_BORNE.match(apres)) or AVANT_BORNE.search(avant[-50:]):
        return "valeur"  # « Du undefined au undefined »
    return None


def fuite_texte(texte):
    """[(jeton, extrait, type)] des fuites d'un texte visible (liste vide si aucune). type : "objet" (toujours une fuite), "valeur"
    (jeton collé à une valeur ou à une étiquette) ou "nu" (jeton qui remplit tout le texte)."""
    t = ho.texte_sans_secret(_norme(texte))  # une adresse ou une clé dans le texte n'entre jamais dans une signature
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
    if m:  # « undefined undefined », « NaN/NaN/NaN » : champs vides d'un gabarit ; jetons distincts (« undefined NaN null ») : isolés
        distincts = sorted(set(JETON.findall(t)))
        if len(distincts) == 1:
            return res + [(distincts[0], t[:60], "valeur")]
        return res + [(j, t[:60], "nu") for j in distincts]
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


def _mot_de_phrase(avant):
    mots = re.findall(r"[\w]+", avant.lower())
    return bool(mots) and (mots[-1] in MOTS_DE_PHRASE or mots[0] in ("le", "la", "les", "l", "un", "une", "the", "a", "an"))


def _meme_hote(netloc, url_page):
    def norme(h):
        h = h.lower()
        return h[4:] if h.startswith("www.") else h
    return not netloc or norme(netloc) == norme(urlparse(url_page).netloc)


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.fuites = {}
        self.titres = {"titre": [], "description": []}
        self._titre = []

    def _ajouter(self, jeton, signature, typ):
        cle = (jeton, signature, typ)
        self.fuites[cle] = self.fuites.get(cle, 0) + 1

    def debut(self, noeud, pile):
        noeud["_t"], noeud["_c"] = [], []  # texte propre de l'élément (et des éléments en ligne qu'il contient), candidats
        tag, a = noeud["tag"], noeud["a"]
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
        valeur = ho.texte_sans_secret(_norme(valeur))
        r = fuite_texte(valeur)
        if r:
            jeton = r[0][0]
            self._ajouter(jeton, '{0} — {1}="{2}"'.format(jeton, nom, valeur[:60]), "attribut")
            return
        if fin_de_phrase:  # alt="Photo de undefined" : un alt décrit une image, il ne parle presque jamais de JavaScript
            fin = re.search(r"(?<![\w-])(undefined|NaN|null)\W*$", valeur)
            if fin:
                self._ajouter(fin.group(1), '{0} — {1}="{2}"'.format(fin.group(1), nom, valeur[:60]), "fin_attribut")

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
        jeton, param = None, None
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
                trouve = next(((n, v) for n, v in parse_qsl(p.query, keep_blank_values=True) if v in VALEURS_URL), None)
                jeton, param = (trouve[1], trouve[0]) if trouve else (None, None)
        if jeton:
            # adresse sans requête ni fragment (jetons, clés) : seul le paramètre fautif est rappelé, et son nom s'il n'a rien d'un secret
            cible = ho.url_sans_secret(valeur, 60)
            if param is not None:
                cible += "?{0}={1}".format("…" if ho._nom_secret(param) else param[:20], jeton)
            self._ajouter(jeton, "{0} — {1} {2}".format(jeton, nom, cible), "url")

    def texte(self, donnees, pile):
        if pile and pile[-1]["tag"] == "title" and not ho.dans(pile, "svg"):
            self._titre.append(donnees)
        elif pile and "_t" in pile[-1] and ho.visible(pile) and not ho.dans(pile, *EXCLUS):
            pile[-1]["_t"].append(donnees)

    def fin(self, noeud, pile):
        if "_t" not in noeud or noeud["masque"]:
            return
        tag, parts, candidats = noeud["tag"], ho.texte_sans_secret("".join(noeud["_t"])), noeud["_c"]
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
        """<title>, meta description, og: et twitter: : toujours lus, sur toute page. Gravité haute (jamais isolée)."""
        if self._titre:
            self.titres["titre"].append("".join(self._titre))
        vus = set()
        for libelle, valeurs in sorted(self.titres.items()):
            for v in valeurs:
                v = ho.texte_sans_secret(_norme(v))
                for seg in SEGMENT_TITRE.split(v):
                    trouvees = [(j, "titre" if typ == "nu" else typ) for j, _, typ in fuite_texte(seg)]
                    fin = FIN_DE_TITRE.search(seg) if libelle == "titre" and not trouvees else None
                    if fin and not _mot_de_phrase(seg[:fin.start()]):  # « Formation undefined » ; « Tout savoir sur undefined » est une phrase
                        trouvees = [(fin.group(1), "titre")]
                    for jeton, typ in trouvees:
                        if (jeton, libelle, v) not in vus:  # même fuite dans <title>, og:title et twitter:title : un constat
                            vus.add((jeton, libelle, v))
                            self._ajouter(jeton, "{0} — {1} « {2} »".format(jeton, libelle, v[:60]), typ)

    def resultat(self):
        self._lire_titres()
        agreges = {}
        for (j, s, typ), n in self.fuites.items():
            cle = (j, s, typ in TYPES_ISOLES)
            agreges[cle] = agreges.get(cle, 0) + n
        res = []
        for (j, s, isolee), n in sorted(agreges.items(), key=lambda x: (x[0][1], x[0][0], x[0][2])):
            e = {"signature": s, "n": n, "jeton": j}
            if isolee:
                e["isolee"] = True
            res.append(e)
        return {"fuites": res}


def _pages(pages, isolee):
    """Copie minimale des pages avec seulement les fuites hautes (isolee=False) ou isolées (isolee=True) de obs[NOM]."""
    return {u: {"obs": {NOM: {"fuites": [e for e in ((p.get("obs") or {}).get(NOM) or {}).get("fuites", []) if bool(e.get("isolee")) == isolee]}}}
            for u, p in pages.items()}


def issues(pages, add, ctx):
    ho.ajouter_groupes(add, "fuite_rendu", "Valeurs techniques affichées (undefined, NaN, null, [object Object], Invalid Date) : donnée manquante publiée",
                       "haute", ho.collecter_groupes(_pages(pages, False), NOM, "fuites"), "Contenu")
    ho.ajouter_groupes(add, "fuite_rendu_isolee", "Mot technique (undefined, NaN, null) seul dans une cellule, un item ou un titre : fuite possible, à vérifier",
                       "basse", ho.collecter_groupes(_pages(pages, True), NOM, "fuites"), "Contenu")
