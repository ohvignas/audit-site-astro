#!/usr/bin/env python3
"""
secrets_js.py — Clés secrètes dans le HTML / JS livrés au navigateur (Python 3.9+, stdlib).

Usage : python3 secrets_js.py FICHIER   → « <format> : <12 premiers caractères>… » par clé distincte (20 lignes au plus)
Règles (faux positif constaté sur beta.illith.com le 2026-10-01 : classes Tailwind mask-image-* lues comme « sk-… ») :
  1. borne gauche : le préfixe n'est précédé ni d'une lettre, ni d'un chiffre, ni de « _ », ni de « - » ;
  2. formats à préfixe documenté d'abord (Stripe, OpenAI, Anthropic, AWS, Google, GitHub, Slack, clé privée, Convex) ;
  3. motifs génériques (sk-…, re_…) : majuscule, minuscule, au moins deux groupes de chiffres, pas de mots séparés par « _ »,
     entropie de Shannon ≥ 3,5 bits/caractère ; sinon c'est un identifiant, pas une clé ;
  4. jeton kebab-case en minuscules (sk-tooltip-arrow) ou placé dans un attribut class : classe CSS, ignoré.
La valeur complète n'est jamais écrite.
"""
import math
import re
import sys
from collections import Counter

BORD = r"(?<![A-Za-z0-9_-])"
# (format, motif, générique : soumis à l'entropie et au contexte CSS)
FORMATS = (
    ("Stripe", BORD + r"(?:sk|rk)_live_[A-Za-z0-9]{10,}", False),
    ("OpenAI", BORD + r"sk-(?:proj|svcacct|admin)-[A-Za-z0-9_-]{20,}", False),
    ("Anthropic", BORD + r"sk-ant-(?:api|admin)\d{2}-[A-Za-z0-9_-]{20,}", False),
    ("AWS", BORD + r"AKIA[0-9A-Z]{16}(?![0-9A-Z])", False),
    ("Google API", BORD + r"AIza[0-9A-Za-z_-]{35}", False),
    ("GitHub", BORD + r"(?:(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})", False),
    ("Slack", BORD + r"xox[baprs]-[A-Za-z0-9-]{10,}", False),
    ("Clé privée", r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", False),
    ("Convex (déploiement)", BORD + r"(?:prod|dev|preview):[a-z0-9-]+\|[A-Za-z0-9=+/]{20,}|CONVEX_DEPLOY_KEY", False),
    ("Resend", BORD + r"re_[A-Za-z0-9_]{20,}", True),
    ("Clé sk- (format inconnu)", BORD + r"sk-[A-Za-z0-9_-]{20,}", True),
)
KEBAB = re.compile(r"^[a-z]+(?:-[a-z]+)+$")
DANS_CLASSE = re.compile(r"""class(?:Name)?\s*=\s*["'][^"']*$""")


def entropie(s):
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values()) if n else 0.0


def _generique_plausible(texte, m):
    valeur = m.group(0)
    corps = valeur.split("-", 1)[1] if valeur.startswith("sk-") else valeur.split("_", 1)[1]
    if KEBAB.match(corps) or DANS_CLASSE.search(texte[max(0, m.start() - 200):m.start()]):
        return False
    if re.search(r"[a-z]{3,}_[a-z]{3,}", corps):  # mots séparés par « _ » : un identifiant (re_quote_attribute…)
        return False
    if not (re.search(r"[A-Z]", corps) and re.search(r"[a-z]", corps) and len(re.findall(r"\d+", corps)) >= 2):
        return False  # une clé aléatoire mêle casses et chiffres ; « …Large2024x » n'a qu'un groupe de chiffres
    return entropie(corps) >= 3.5


def detecter(texte):
    trouves, pris, vus = [], [], set()
    for nom, motif, generique in FORMATS:
        for m in re.finditer(motif, texte):
            if any(a < m.end() and m.start() < b for a, b in pris):  # déjà couvert par un format plus précis
                continue
            if generique and not _generique_plausible(texte, m):
                continue
            pris.append((m.start(), m.end()))
            if m.group(0) not in vus:
                vus.add(m.group(0))
                trouves.append((m.start(), nom, m.group(0)))
    return [(nom, v) for _, nom, v in sorted(trouves)]


def formater(paires):
    return ["{0} : {1}…".format(nom, valeur[:12]) for nom, valeur in paires]


def main():
    with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
        texte = f.read()
    for ligne in formater(detecter(texte))[:20]:
        print(ligne)


if __name__ == "__main__":
    main()
