#!/usr/bin/env python3
"""a11y_svg.py — SVG inline sans nom accessible et non masqués (RGAA 1.1.5 et 1.2.4, WCAG 1.1.1), regroupés par composant :
une icône répétée 128 fois sur le site donne un constat, avec le correctif à faire dans le composant (Icon.astro…).
Module du diffuseur html_observateurs (T3).

Trois familles, rendues dans obs["a11y_svg"] :
  non_masques          SVG décoratif, hors lien et bouton, ni masqué ni nommé (svg_non_masque, moyenne) ;
  img_sans_nom         SVG role="img" / "graphics-*" sans nom (svg_img_sans_nom, haute) ;
  dans_controle_nomme  SVG décoratif non masqué dans un lien ou un bouton qui a déjà un nom : bruit pour le lecteur d'écran,
                       pas une erreur (svg_redondant_controle, basse — simple conseil, jamais le constat principal).
Un SVG seul contenu d'un lien ou d'un bouton sans nom n'est compté nulle part ici : lien_sans_nom / bouton_sans_nom (T13)
le signalent une seule fois.

Ignorés : SVG masqué (lui-même ou un ancêtre : aria-hidden, hidden, display:none, classe hidden, <template>, <noscript>),
role="presentation" / "none", conteneur de définitions (width ou height à 0), SVG imbriqué (seul le plus externe compte).
Nommé : aria-label non vide, <title> non vide, aria-labelledby dont un identifiant existe dans la page.
Limite : seule l'existence de l'identifiant référencé est vérifiée, pas le texte de l'élément ; une référence cassée est un
SVG sans nom ici (et un constat de a11y_structure)."""
import re

import html_observateurs as ho

NOM = "a11y_svg"
TAILLE_NULLE = re.compile(r"^0+(\.0+)?(px|em|rem|%)?$")


def _ajouter(d, cle):
    d[cle] = d.get(cle, 0) + 1


def _refs(valeur):
    return [r for r in (valeur or "").split() if r]


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.svg, self.profondeur, self.titre = None, 0, None
        self.svgs, self.ids = [], set()
        self.controles = []  # liens / boutons ouverts : leurs SVG attendent de savoir si le contrôle a un nom

    def debut(self, noeud, pile):
        t, a = noeud["tag"], noeud["a"]
        if a.get("id"):
            self.ids.add(a["id"])
        if t in ("a", "button") and not noeud["masque"] and (t == "button" or "href" in a):
            self.controles.append({"noeud": noeud, "svgs": [], "refs": _refs(a.get("aria-labelledby")),
                                   "nom": any(a.get(k, "").strip() for k in ("aria-label", "title"))})
        elif t == "img" and self.controles and a.get("alt", "").strip():
            self.controles[-1]["nom"] = True
        if t == "svg":
            self.profondeur += 1
            if self.profondeur == 1:
                parent = pile[-1] if pile else {"tag": "—", "a": {}}
                classes = sorted(parent["a"].get("class", "").split())[:2]
                self.svg = {
                    "ignore": noeud["masque"] or bool(TAILLE_NULLE.match(a.get("width", "").strip()))
                    or bool(TAILLE_NULLE.match(a.get("height", "").strip()))
                    or a.get("role", "").strip().lower() in ("presentation", "none"),
                    "role": a.get("role", "").strip().lower(),
                    "nom": bool(a.get("aria-label", "").strip()), "refs": _refs(a.get("aria-labelledby")),
                    "signature": "viewBox={0} fill={1} parent={2}".format(
                        a.get("viewbox") or "—", a.get("fill") or "—", ".".join([parent["tag"]] + classes)),
                    "controle": self.controles[-1] if self.controles else None}
        elif t == "title" and self.svg is not None:
            self.titre = []

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
                s, self.svg = self.svg, None
                if not s["ignore"]:
                    self.svgs.append(s)
                    if s["controle"] is not None:
                        s["controle"]["svgs"].append(s)
        elif self.controles and self.controles[-1]["noeud"] is noeud:
            self.controles.pop()

    def _nomme(self, x):
        return x["nom"] or any(r in self.ids for r in x["refs"])  # les ids peuvent venir après : décidé en fin de page

    def resultat(self):
        non_masques, img_sans_nom, conseils = {}, {}, {}
        for s in self.svgs:
            if self._nomme(s):
                continue
            c = s["controle"]
            if s["role"] == "img" or s["role"].startswith("graphics-"):
                _ajouter(img_sans_nom, s["signature"])
            elif c is None:
                _ajouter(non_masques, s["signature"])
            elif self._nomme(c) or any(self._nomme(o) for o in c["svgs"]):
                _ajouter(conseils, s["signature"])  # contrôle nommé : l'icône est redondante (RGAA 1.2.4), pas une erreur
            # contrôle sans nom : le SVG est son contenu, signalé une seule fois par lien_sans_nom / bouton_sans_nom (T13)
        return {k: [{"signature": sig, "n": n} for sig, n in sorted(d.items())]
                for k, d in (("non_masques", non_masques), ("img_sans_nom", img_sans_nom), ("dans_controle_nomme", conseils))}


def issues(pages, add, ctx):
    ho.ajouter_groupes(add, "svg_non_masque", "SVG inline décoratifs non masqués (aria-hidden absent) — RGAA 1.2.4, regroupés par composant",
                       "moyenne", ho.collecter_groupes(pages, NOM, "non_masques"), "Accessibilité")
    ho.ajouter_groupes(add, "svg_img_sans_nom", "SVG role=\"img\" sans nom accessible (aria-label, aria-labelledby ou <title>) — WCAG 1.1.1",
                       "haute", ho.collecter_groupes(pages, NOM, "img_sans_nom"), "Accessibilité")
    ho.ajouter_groupes(add, "svg_redondant_controle", "Conseil : SVG décoratif non masqué dans un lien ou bouton déjà nommé (aria-hidden évite la redite)",
                       "basse", ho.collecter_groupes(pages, NOM, "dans_controle_nomme"), "Accessibilité")
