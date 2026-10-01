#!/usr/bin/env python3
"""a11y_noms.py — Liens et boutons sans nom accessible, sur toutes les pages (WCAG 2.4.4 / 4.1.2 ; axe link-name,
button-name, input-button-name, input-image-alt). Nom calculé comme l'accname, simplifié, dans l'ordre :
aria-labelledby (ids résolus en fin de page), aria-label, texte des descendants (le texte « sr-only » compte, un sous-arbre
aria-hidden / hidden est exclu), alt d'une image descendante, nom d'un SVG descendant (aria-label, aria-labelledby, <title>),
value d'un input bouton (submit / reset ont un nom par défaut), title en dernier recours.
Contrôles : <a href>, <button>, input type=button|submit|reset|image, [role=button] ; un contrôle masqué est ignoré, un <a> sans
href n'est pas un lien. Résultat : obs["a11y_noms"] = {"liens_sans_nom": [...], "boutons_sans_nom": [...]}, listes de
{"signature", "n"} (signature : balise du contrôle + ses trois premiers descendants, « masqué » s'ils le sont).
Faux positif connu : texte injecté par JavaScript dans un îlot hydraté (le HTML serveur est vide) ; la passe rendue
(axe:link-name) le confirme. Module du diffuseur html_observateurs : Observateur (un passage par page) puis issues(pages, add, ctx)."""
import re

import html_observateurs as ho

NOM = "a11y_noms"

_VIDE = re.compile(r"[\s​-‍⁠﻿]*\Z")
TYPES_BOUTON = ("button", "submit", "reset", "image")


def _vide(s):
    return bool(_VIDE.match(s or ""))


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.ouverts, self.finis = [], []  # contrôles en cours de lecture (imbriqués) / terminés
        self.ids, self._ids_ouverts = {}, []  # id → texte (ou aria-label) de l'élément ; éléments à id en cours de lecture
        self._titre_svg = None

    def _nommer(self):
        for c in self.ouverts:
            c["nom"] = True

    def debut(self, noeud, pile):
        t, a = noeud["tag"], noeud["a"]
        if a.get("id"):
            self._ids_ouverts.append((noeud, a["id"], a.get("aria-label", ""), []))  # cible d'un aria-labelledby, même masquée
        if self.ouverts:
            for c in self.ouverts:
                if len(c["contenu"]) < 3:
                    c["contenu"].append(t + (" masqué" if noeud["masque"] else ""))
        if noeud["masque"]:
            return
        if self.ouverts:  # descendant visible d'un contrôle : source de nom
            if not _vide(a.get("aria-label")) or (t == "img" and not _vide(a.get("alt"))):
                self._nommer()
            if a.get("aria-labelledby", "").strip():
                for c in self.ouverts:
                    c["refs"].extend(a["aria-labelledby"].split())
            if not _vide(a.get("title")):
                for c in self.ouverts:
                    c["titre"] = True
            if t == "title" and ho.dans(pile, "svg"):
                self._titre_svg = []
        role = a.get("role", "").split()[0].lower() if a.get("role", "").split() else ""
        type_input = a.get("type", "").strip().lower() if t == "input" else ""
        if role == "button" or t == "button" or (t == "input" and type_input in TYPES_BOUTON):
            type_ = "bouton"
        elif t == "a" and "href" in a:
            type_ = "lien"
        else:
            return
        nom = not _vide(a.get("aria-label"))
        if t == "input":
            nom = nom or (type_input == "image" and not _vide(a.get("alt"))) or (type_input != "image" and (
                not _vide(a.get("value")) or type_input in ("submit", "reset")))
        if t == "a":
            ident = ' href="{0}"'.format(" ".join(a["href"].split())[:80])
        elif t == "input":
            ident = ' type="{0}"'.format(type_input)
        else:
            classes = " ".join(sorted(a.get("class", "").split())[:2])
            ident = ("" if t == "button" else ' role="button"') + (' class="{0}"'.format(classes) if classes else "")
        self.ouverts.append({"noeud": noeud, "type": type_, "nom": nom, "texte": [], "contenu": [],
                             "refs": a.get("aria-labelledby", "").split(), "titre": not _vide(a.get("title")),
                             "balise": "<{0}{1}>".format(t, ident)})

    def texte(self, donnees, pile):
        if self._ids_ouverts and not ho.dans(pile, "script", "style"):
            for e in self._ids_ouverts:
                e[3].append(donnees)
        if self._titre_svg is not None:
            self._titre_svg.append(donnees)
        elif self.ouverts and ho.visible(pile):
            for c in self.ouverts:
                c["texte"].append(donnees)

    def fin(self, noeud, pile):
        if noeud["tag"] == "title" and self._titre_svg is not None:
            if not _vide("".join(self._titre_svg)):
                self._nommer()
            self._titre_svg = None
        if self._ids_ouverts and self._ids_ouverts[-1][0] is noeud:
            _, ident, etiquette, buf = self._ids_ouverts.pop()
            self.ids.setdefault(ident, etiquette.strip() or " ".join("".join(buf).split()))  # premier id gagnant, comme un navigateur
        if self.ouverts and self.ouverts[-1]["noeud"] is noeud:
            self.finis.append(self.ouverts.pop())

    def resultat(self):
        sans = {"lien": {}, "bouton": {}}
        for c in self.finis:
            if c["nom"] or c["titre"] or not _vide("".join(c["texte"])) or any(not _vide(self.ids.get(r)) for r in c["refs"]):
                continue
            sig = "{0} contenu : {1}".format(c["balise"], ", ".join(c["contenu"][:3]) or "vide")
            sans[c["type"]][sig] = sans[c["type"]].get(sig, 0) + 1
        return {"liens_sans_nom": [{"signature": s, "n": n} for s, n in sorted(sans["lien"].items())],
                "boutons_sans_nom": [{"signature": s, "n": n} for s, n in sorted(sans["bouton"].items())]}


def issues(pages, add, ctx):
    ho.ajouter_groupes(add, "lien_sans_nom", "Liens sans nom accessible (icône seule, image sans alt, texte masqué) — WCAG 2.4.4",
                       "haute", ho.collecter_groupes(pages, NOM, "liens_sans_nom"), "Accessibilité")
    ho.ajouter_groupes(add, "bouton_sans_nom", "Boutons sans nom accessible (icône seule, aria-label absent) — WCAG 4.1.2",
                       "haute", ho.collecter_groupes(pages, NOM, "boutons_sans_nom"), "Accessibilité")
