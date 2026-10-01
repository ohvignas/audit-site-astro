#!/usr/bin/env python3
"""a11y_svg.py — SVG inline sans nom accessible et non masqués (RGAA 1.1.5 et 1.2.4, WCAG 1.1.1), regroupés par type d'icône :
une icône répétée cent fois sur le site donne quelques constats, avec le correctif à faire dans le composant (Icon.astro…).
Module du diffuseur html_observateurs (T3).

Trois familles, rendues dans obs["a11y_svg"] (listes {"signature", "n", "exemple"} triées par n décroissant) :
  non_masques          SVG décoratif, hors lien et bouton, ni masqué ni nommé (svg_non_masque, moyenne) ;
  img_sans_nom         SVG role="img" / "graphics-*" sans nom (svg_img_sans_nom, haute) ;
  dans_controle_nomme  SVG décoratif non masqué dans un lien ou un bouton qui a déjà un nom : même défaut RGAA 1.2.4, impact faible
                       puisque le nom est déjà lu (svg_redondant_controle, basse).
Un SVG seul contenu d'un lien ou d'un bouton sans nom n'est compté nulle part ici : lien_sans_nom / bouton_sans_nom (T13)
le signalent une seule fois.

Signature : viewBox, fill et stroke du SVG lui-même. Ni le parent (ses classes changent d'un usage à l'autre : Tailwind) ni la
taille ni le tracé n'en font partie : un composant d'icônes (un tracé par pictogramme, une taille par usage) reste un seul constat.
Le parent (balise et deux premières classes) n'intervient que si le SVG n'a aucun de ces trois attributs. L'exemple donne la balise
ouvrante (viewBox, taille, couleurs, classe), le début du premier tracé et son empreinte (8 hexadécimaux), de quoi chercher le
composant dans src/ ; il ne contient jamais de paramètre de requête.

Ignorés : SVG masqué (lui-même ou un ancêtre : aria-hidden, hidden, display:none, classe hidden, <template>, <noscript>),
role="presentation" / "none", conteneur de définitions (width ou height à 0, en attribut, en style ou en classe w-0 / h-0 ; ou
seulement des defs, symbol, style, dégradés…), SVG imbriqué (seul le plus externe compte), SVG sous un ancêtre role="img" nommé
(ses enfants sont présentationnels : une note en étoiles se nomme une fois, sur l'enveloppe).
Nommé : aria-label non vide, <title> non vide, aria-labelledby dont un identifiant existe dans la page.
Limite : seule l'existence de l'identifiant référencé est vérifiée, pas le texte de l'élément ; une référence cassée est un
SVG sans nom ici (et un constat de a11y_structure)."""
import re
import zlib

import html_observateurs as ho

NOM = "a11y_svg"
TAILLE_NULLE = re.compile(r"^0+(\.0+)?(px|em|rem|%)?$")
STYLE_TAILLE_NULLE = re.compile(r"(^|;)\s*(width|height)\s*:\s*0+(\.0+)?(px|em|rem)?\s*(;|$)", re.I)
CLASSES_TAILLE_NULLE = {"w-0", "h-0"}
CONTROLES_ARIA = {"button", "link", "tab", "menuitem", "menuitemcheckbox", "menuitemradio", "checkbox", "radio", "switch", "option"}
DEFINITIONS = {"defs", "symbol", "style", "lineargradient", "radialgradient", "clippath", "mask", "filter", "pattern", "marker"}
DESSINS = {"path", "circle", "rect", "line", "polyline", "polygon", "ellipse", "text", "image", "use", "foreignobject"}
ATTRIBUTS_EXEMPLE = (("viewbox", "viewBox"), ("width", "width"), ("height", "height"), ("fill", "fill"), ("stroke", "stroke"),
                     ("stroke-width", "stroke-width"), ("class", "class"), ("role", "role"))


def _ajouter(d, cle):
    d[cle] = d.get(cle, 0) + 1


def _refs(valeur):
    return [r for r in (valeur or "").split() if r]


def _net(v, n):
    """Valeur lisible : espaces réduits, jamais de paramètre de requête, guillemets neutralisés, tronquée à n caractères."""
    v = re.sub(r"\s+", " ", (v or "").split("?")[0]).strip().replace('"', "'")
    return v if len(v) <= n else v[:n].rstrip() + "…"


def _nombre(v):
    v = (v or "").strip()
    return "%g" % round(float(v), 2) if re.fullmatch(r"-?\d+(\.\d+)?", v) else v


def _ouvrante(a):
    parts = []
    for cle, nom in ATTRIBUTS_EXEMPLE:
        if a.get(cle, "").strip():
            v = _nombre(a[cle]) if cle in ("width", "height", "stroke-width") else _net(a[cle], 40)
            parts.append('{0}="{1}"'.format(nom, v))
    return "<svg" + "".join(" " + p for p in parts) + ">"


def _empreinte(d):
    return "%08x" % (zlib.crc32(re.sub(r"\s+", " ", d).strip().encode("utf-8")) & 0xFFFFFFFF)


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.svg, self.profondeur, self.titre, self.defs = None, 0, None, 0
        self.svgs, self.ids = [], set()
        self.controles = []  # liens / boutons / commandes ARIA ouverts : leurs SVG attendent de savoir si le contrôle a un nom

    def _ancetres_img(self, pile):
        """Ancêtres role="img" : (déjà nommé ?, [identifiants aria-labelledby à résoudre en fin de page])."""
        nomme, refs = False, []
        for n in pile:
            a = n["a"]
            if a.get("role", "").strip().lower() == "img":
                if a.get("aria-label", "").strip() or a.get("title", "").strip():
                    nomme = True
                refs.append(_refs(a.get("aria-labelledby")))
        return nomme, refs

    def debut(self, noeud, pile):
        t, a = noeud["tag"], noeud["a"]
        if a.get("id"):
            self.ids.add(a["id"])
        role = a.get("role", "").strip().lower()
        if not noeud["masque"] and (t == "button" or (t == "a" and "href" in a) or role in CONTROLES_ARIA):
            self.controles.append({"noeud": noeud, "svgs": [], "refs": _refs(a.get("aria-labelledby")),
                                   "nom": any(a.get(k, "").strip() for k in ("aria-label", "title"))})
        elif t == "img" and self.controles and a.get("alt", "").strip():
            self.controles[-1]["nom"] = True
        if t == "svg":
            self.profondeur += 1
            if self.profondeur == 1:
                parent = pile[-1] if pile else {"tag": "—", "a": {}}
                vb, fill, stroke = (a.get(k, "").strip() for k in ("viewbox", "fill", "stroke"))
                signature = "viewBox={0} fill={1} stroke={2}".format(vb or "—", fill or "—", stroke or "—")
                if not (vb or fill or stroke):  # rien de propre au SVG : le parent départage
                    signature += " parent=" + ".".join([parent["tag"]] + sorted(parent["a"].get("class", "").split())[:2])
                nomme_par_enveloppe, refs_enveloppe = self._ancetres_img(pile)
                self.svg = {
                    "ignore": noeud["masque"] or bool(TAILLE_NULLE.match(a.get("width", "").strip()))
                    or bool(TAILLE_NULLE.match(a.get("height", "").strip())) or bool(STYLE_TAILLE_NULLE.search(a.get("style", "")))
                    or bool(CLASSES_TAILLE_NULLE.intersection(a.get("class", "").split())) or role in ("presentation", "none"),
                    "role": role, "defs": False, "dessine": False, "d": None, "ouvrante": _ouvrante(a),
                    "nom": bool(a.get("aria-label", "").strip()), "refs": _refs(a.get("aria-labelledby")),
                    "couvert": nomme_par_enveloppe, "refs_enveloppe": refs_enveloppe, "signature": signature,
                    "controle": self.controles[-1] if self.controles else None}
        elif self.svg is not None:
            if t == "title":
                self.titre = []
            elif t in DEFINITIONS:
                self.svg["defs"] = True
                self.defs += 1
            elif t in DESSINS and not self.defs:
                self.svg["dessine"] = True
                if t == "path" and self.svg["d"] is None and a.get("d", "").strip():
                    self.svg["d"] = a["d"]

    def texte(self, donnees, pile):
        if self.titre is not None:
            self.titre.append(donnees)
        elif self.controles and donnees.strip() and ho.visible(pile) and not ho.dans(pile, "desc"):
            self.controles[-1]["nom"] = True

    def fin(self, noeud, pile):
        t = noeud["tag"]
        if t == "title" and self.titre is not None:
            if "".join(self.titre).strip():
                self.svg["nom"] = True
            self.titre = None
        elif t == "svg" and self.profondeur:
            self.profondeur -= 1
            if self.profondeur == 0 and self.svg is not None:
                s, self.svg, self.defs = self.svg, None, 0
                if s["defs"] and not s["dessine"]:  # conteneur de définitions (sprite, dégradés) : rien n'est dessiné
                    s["ignore"] = True
                if not s["ignore"]:
                    self.svgs.append(s)
                    if s["controle"] is not None:
                        s["controle"]["svgs"].append(s)
        elif t in DEFINITIONS and self.svg is not None and self.defs:
            self.defs -= 1
        elif self.controles and self.controles[-1]["noeud"] is noeud:
            self.controles.pop()

    def _nomme(self, x):
        return x["nom"] or any(r in self.ids for r in x["refs"])  # les ids peuvent venir après : décidé en fin de page

    def _couvert(self, s):
        return s["couvert"] or any(r in self.ids for refs in s["refs_enveloppe"] for r in refs)

    def resultat(self):
        familles = {"non_masques": {}, "img_sans_nom": {}, "dans_controle_nomme": {}}
        for s in self.svgs:
            if self._couvert(s) or self._nomme(s):
                continue
            c = s["controle"]
            if c is not None and not (self._nomme(c) or any(self._nomme(o) for o in c["svgs"])):
                continue  # seul contenu d'un contrôle sans nom : un seul constat, par lien_sans_nom / bouton_sans_nom (T13)
            if s["role"] == "img" or s["role"].startswith("graphics-"):
                famille = "img_sans_nom"
            elif c is None:
                famille = "non_masques"
            else:
                famille = "dans_controle_nomme"  # contrôle nommé : même défaut RGAA 1.2.4, impact faible
            g = familles[famille].setdefault(s["signature"], {"n": 0, "exemple": s, "traces": set()})
            g["n"] += 1
            g["traces"].add(_empreinte(s["d"]) if s["d"] else None)
        return {k: [{"signature": sig, "n": g["n"], "exemple": _exemple(g)}
                    for sig, g in sorted(d.items(), key=lambda x: (-x[1]["n"], x[0]))] for k, d in familles.items()}


def _exemple(g):
    s, traces = g["exemple"], g["traces"] - {None}
    texte = s["ouvrante"]
    if s["d"]:
        texte += ' <path d="{0}"> tracé {1}'.format(_net(s["d"], 32), _empreinte(s["d"]))
        if len(traces) > 1:
            k = len(traces) - 1
            texte += " (+{0} autre{1} tracé{1})".format(k, "s" if k > 1 else "")
    return texte


def _exemples(groupes):
    """[(n, exemple)] du plus gros groupe au plus petit (signature pour départager) : l'agent n'affiche que les premiers exemples."""
    sortie = []
    for sig in sorted(groupes, key=lambda s: (-groupes[s]["n"], s)):
        g = groupes[sig]
        urls = sorted(set(g["pages"]))
        e = {"signature": sig, "occurrences": g["n"], "pages": len(urls)}
        if "exemple" in g:
            e["exemple"] = g["exemple"]  # avant les URL : ex_str coupe le texte d'un exemple à 220 caractères
        e["exemples_pages"] = urls[:3]
        sortie.append((g["n"], e))
    return sortie


def issues(pages, add, ctx):
    for n, e in _exemples(ho.collecter_groupes(pages, NOM, "non_masques")):
        add("svg_non_masque", "SVG inline décoratifs non masqués : aria-hidden=\"true\" manquant (RGAA 1.2.4), regroupés par type d'icône",
            "moyenne", e, n=n, domaine="Accessibilité")
    for n, e in _exemples(ho.collecter_groupes(pages, NOM, "img_sans_nom")):
        add("svg_img_sans_nom", "SVG role=\"img\" sans nom accessible (aria-label, aria-labelledby ou <title>) — WCAG 1.1.1, RGAA 1.1.5",
            "haute", e, n=n, domaine="Accessibilité")
    for n, e in _exemples(ho.collecter_groupes(pages, NOM, "dans_controle_nomme")):
        add("svg_redondant_controle", "SVG décoratif non masqué dans un lien ou un bouton déjà nommé : non conforme RGAA 1.2.4 "
            "(impact faible, le nom est déjà lu), même correctif que svg_non_masque",
            "basse", e, n=n, domaine="Accessibilité")
