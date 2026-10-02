#!/usr/bin/env python3
"""a11y_structure.py — Structure accessible de chaque page : niveaux de titres sautés (RGAA 9.1), aria-labelledby /
aria-describedby vers un id absent, zoom bloqué par la meta viewport (WCAG 1.4.4), iframes sans titre (RGAA 2.1),
aria-label sur un élément générique sans rôle (ARIA 1.2 : nommage interdit). Module du diffuseur html_observateurs (T3).

Choix pour limiter les faux positifs :
- titres : la hiérarchie est jugée par composant de repère. Les titres d'un <footer>, d'un <aside>, d'un <nav> (ou d'un
  élément portant role contentinfo / complementary / navigation / banner) forment une suite à part : un h4 de pied de page
  après un h2 du contenu n'est pas un saut (WAVE ne l'émet qu'en simple alerte). Un <footer> placé dans un <article>, <section>,
  <main>… n'est pas un repère (HTML-AAM) ; <header> n'en est jamais un. Un vrai saut à l'intérieur d'un même composant, ou du
  contenu principal, reste signalé. Limite : role="heading" aria-level="N" n'est pas lu ;
- références ARIA : les ids sont collectés sur toute la page et comparés après la lecture complète (un id défini plus loin
  que la référence est valide) ; aria-controls est ignoré (souvent créé par JavaScript) ;
- iframes : masquées, de 0/1 px (pixels de suivi), à tabindex négatif ou de rôle presentation/none, ignorées ; la signature ne
  garde que hôte + chemin du src : jamais de query string, de fragment ni d'identifiants (clés d'API, jetons signés) ;
- meta viewport : séparateurs virgule, point-virgule ou espace ; ignorée dans un <template> ou un <noscript>."""
import re

import html_observateurs as ho
from html_observateurs import dans

NOM = "a11y_structure"
NIVEAUX = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
# Balises dont le rôle implicite interdit le nommage (ARIA 1.2 : generic, paragraph, emphasis, strong, code, deletion, insertion,
# subscript, superscript, caption). header, footer, time, mark, label… restent exclus : nommables ou selon le contexte.
GENERIQUES = {"div", "span", "p", "b", "i", "em", "strong", "small", "code", "del", "ins", "s", "sub", "sup", "u",
              "pre", "abbr", "cite", "q", "kbd", "samp", "var", "bdi", "bdo", "data", "caption"}
# Rôles explicites qui ne rendent pas le nommage permis (le rôle ne change rien ou retire la sémantique)
ROLES_SANS_NOM = {"generic", "presentation", "none", "paragraph", "emphasis", "strong", "code", "deletion", "insertion",
                  "subscript", "superscript", "caption"}
REPERES = {"footer", "aside", "nav"}
PORTEES = {"article", "section", "main", "aside", "nav", "blockquote", "dialog"}  # un <footer> qui s'y trouve n'est pas un repère
ROLES_REPERES = {"contentinfo", "complementary", "navigation", "banner"}
TAILLE_NULLE = re.compile(r"\s*[01](\.0+)?\s*(px)?\s*$", re.I)
STYLE_TAILLE_NULLE = re.compile(r"(?:^|;)\s*(?:width|height)\s*:\s*[01](?:\.0+)?(?:px)?\s*(?:;|$)", re.I)


def _ajouter(d, cle):
    d[cle] = d.get(cle, 0) + 1


def _liste(d):
    return [{"signature": k, "n": v} for k, v in sorted(d.items())]


def _src_sans_secret(src):
    """Hôte + chemin d'une URL d'iframe : ni query string, ni fragment, ni identifiants (clés d'API, jetons dans l'URL)."""
    return ho.url_sans_secret(src, 80, avec_schema=False) or "sans src"


def _pixel_de_suivi(a):
    return (any(TAILLE_NULLE.match(a.get(k, "x")) for k in ("width", "height"))
            or bool(STYLE_TAILLE_NULLE.search(a.get("style", ""))))


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.titres, self._ouverts = [], []  # titres : [niveau, repère, [morceaux de texte]] dans l'ordre du document
        self._reperes, self._garde = {}, []
        self.ids, self.refs = set(), []
        self.zoom, self.iframes, self.interdits = set(), {}, {}

    def debut(self, noeud, pile):
        t, a = noeud["tag"], noeud["a"]
        if a.get("id"):
            self.ids.add(a["id"])
        if noeud["masque"]:
            return
        if t == "meta" and a.get("name", "").lower() == "viewport":
            self._viewport(a.get("content", ""))
        role = (a.get("role", "").split() or [""])[0].lower()
        if (t in REPERES and not (t == "footer" and dans(pile, *PORTEES))) or role in ROLES_REPERES:
            self._reperes[id(noeud)] = len(self._garde)
            self._garde.append(noeud)  # garde le nœud vivant : id() ne sera pas réutilisé par un autre
        if t in NIVEAUX:
            repere = next((self._reperes[id(n)] for n in reversed(pile) if id(n) in self._reperes), None)
            titre = [NIVEAUX[t], repere, []]
            self.titres.append(titre)
            self._ouverts.append((noeud, titre))
        for attr in ("aria-labelledby", "aria-describedby"):
            for ident in a.get(attr, "").split():
                self.refs.append((attr, ident))
        if t == "img" and self._ouverts and a.get("alt", "").strip():
            self._ouverts[-1][1][2].append(a["alt"] + " ")  # titre fait d'une image : son alt tient lieu de texte
        if (t == "iframe" and not _pixel_de_suivi(a) and not a.get("tabindex", "").strip().startswith("-")
                and role not in ("presentation", "none")
                and not any(a.get(k, "").strip() for k in ("title", "aria-label", "aria-labelledby"))):
            _ajouter(self.iframes, _src_sans_secret(a["src"]) if a.get("src", "").strip()
                     else ("srcdoc" if "srcdoc" in a else "sans src"))
        if (t in GENERIQUES and (not role or role in ROLES_SANS_NOM) and "tabindex" not in a
                and "contenteditable" not in a):
            for k in ("aria-label", "aria-labelledby"):
                if a.get(k, "").strip():
                    _ajouter(self.interdits, '<{0} {1}="{2}">'.format(t, k, ho.texte_sans_secret(a[k].strip())[:60]))

    def texte(self, donnees, pile):
        if self._ouverts:
            self._ouverts[-1][1][2].append(donnees)

    def fin(self, noeud, pile):
        if self._ouverts and self._ouverts[-1][0] is noeud:
            self._ouverts.pop()

    def _viewport(self, contenu):
        mauvais = []
        for part in re.split(r"[,;\s]+", re.sub(r"\s*=\s*", "=", contenu)):
            if "=" not in part:
                continue
            k, v = [x.strip().lower() for x in part.split("=", 1)]
            if k == "user-scalable" and v in ("no", "0"):
                mauvais.append("{0}={1}".format(k, v))
            elif k == "maximum-scale":
                try:
                    if float(v) < 2:
                        mauvais.append("{0}={1}".format(k, v))
                except ValueError:
                    pass
        if mauvais:
            self.zoom.add(", ".join(mauvais))

    def resultat(self):
        sautes, precedent = {}, {}  # signature = le saut ; exemple = texte du premier titre fautif ; suite de titres par repère
        for niveau, repere, morceaux in self.titres:
            prec = precedent.get(repere)
            if prec is not None and niveau > prec + 1:
                texte = " ".join("".join(morceaux).split())[:60] or "titre vide"
                s = sautes.setdefault("h{0} → h{1}".format(prec, niveau), {"n": 0, "exemple": "« {0} »".format(texte)})
                s["n"] += 1
            precedent[repere] = niveau
        cassees = {}
        for attr, ident in self.refs:
            if ident not in self.ids:
                _ajouter(cassees, '{0}="{1}"'.format(attr, ident))
        return {"titres_sautes": [{"signature": k, "n": v["n"], "exemple": v["exemple"]} for k, v in sorted(sautes.items())],
                "aria_ref_cassee": _liste(cassees),
                "zoom_bloque": [{"signature": z, "n": 1} for z in sorted(self.zoom)],
                "iframe_sans_titre": _liste(self.iframes), "aria_label_interdit": _liste(self.interdits)}


def issues(pages, add, ctx):
    g = lambda champ: ho.collecter_groupes(pages, NOM, champ)  # noqa: E731
    ho.ajouter_groupes(add, "titres_sautes", "Niveaux de titres sautés (ex. h2 puis h4) — RGAA 9.1", "moyenne", g("titres_sautes"), "Accessibilité")
    ho.ajouter_groupes(add, "aria_ref_cassee", "aria-labelledby / aria-describedby vers un id absent de la page", "moyenne",
                       g("aria_ref_cassee"), "Accessibilité")
    ho.ajouter_groupes(add, "zoom_bloque", "Zoom bloqué par la meta viewport (user-scalable=no ou maximum-scale < 2) — WCAG 1.4.4",
                       "haute", g("zoom_bloque"), "Accessibilité")
    ho.ajouter_groupes(add, "iframe_sans_titre", "Iframes sans titre (title) — RGAA 2.1", "moyenne", g("iframe_sans_titre"), "Accessibilité")
    ho.ajouter_groupes(add, "aria_label_interdit", "aria-label / aria-labelledby sur un élément générique sans rôle (nom ignoré, ARIA interdit)", "moyenne",
                       g("aria_label_interdit"), "Accessibilité")
