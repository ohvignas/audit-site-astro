#!/usr/bin/env python3
"""
secrets_js.py — Clés secrètes dans le HTML / JS livrés au navigateur (Python 3.9+, stdlib).

Usage : python3 secrets_js.py FICHIER             → « <format> : <12 premiers caractères>… » par clé secrète distincte (20 lignes au plus)
        python3 secrets_js.py FICHIER --publiques → mêmes lignes pour les clés publiques par conception (Google AIza…), à part
Code retour non nul si le fichier est illisible : l'appelant ne doit alors jamais conclure « aucun secret ».
Règles (faux positif constaté sur beta.illith.com le 2026-10-01 : classes Tailwind mask-image-* lues comme « sk-… ») :
  1. borne gauche : le préfixe n'est précédé ni d'une lettre, ni d'un chiffre, ni de « _ », ni de « - » ; pour les formats à préfixe
     documenté, une séquence d'échappement (\\n, \\t, %22, \\u0022…) juste avant la clé compte comme une frontière (JSON, chaînes minifiées) ;
  2. formats à préfixe documenté d'abord (Stripe, OpenAI, Anthropic, AWS, Google, GitHub, Slack, clé privée, Convex) ;
  3. motifs génériques (sk-…, re_…) : majuscule, minuscule, au moins deux groupes de chiffres, pas de mots séparés par « _ » ni en
     camelCase, entropie de Shannon ≥ 3,5 bits/caractère ; sinon c'est un identifiant, pas une clé ; clé sk- hexadécimale minuscule
     (DeepSeek, OpenRouter) : au moins 32 caractères, chiffres et lettres, entropie ≥ 3,0 ;
  4. jeton kebab-case (sk-tooltip-arrow, sk-Nav-Top-2024) ou placé dans un attribut class : classe CSS, ignoré ;
  5. exemples et gabarits ignorés (EXAMPLE, xxxx, your_…, <…>, caractère répété, en-tête PEM sans corps).
La valeur complète n'est jamais écrite.
"""
import math
import re
import sys
from collections import Counter

BORD = r"(?<![A-Za-z0-9_-])"
# Pour les formats à préfixe documenté : l'échappement littéral (« \n » = deux caractères, « %22 », « " ») qui précède la clé
# dans du JSON ou une chaîne minifiée ne la colle pas à un mot.
BORD_CONNU = (r"(?:(?<![A-Za-z0-9_-])|(?<=\\[nrt])|(?<=\\u00[02][0-9a-f])|(?<=\\x[02][0-9a-f])"
              r"|(?<=%[0-9A-Fa-f]{2}))")
PEM = r"(?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY|PGP PRIVATE KEY BLOCK"
# (format, motif, générique : soumis à l'entropie et au contexte CSS)
FORMATS = (
    ("Stripe", BORD_CONNU + r"(?:sk|rk)_live_[A-Za-z0-9]{10,}", False),
    ("OpenAI", BORD_CONNU + r"sk-(?:proj|svcacct|admin)-[A-Za-z0-9_-]{20,}", False),
    ("Anthropic", BORD_CONNU + r"sk-ant-(?:api|admin)\d{2}-[A-Za-z0-9_-]{20,}", False),
    ("AWS", BORD_CONNU + r"AKIA[0-9A-Z]{16}(?![0-9A-Z])", False),
    ("Google API", BORD_CONNU + r"AIza[0-9A-Za-z_-]{35}", False),
    ("GitHub", BORD_CONNU + r"(?:(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})", False),
    ("Slack", BORD_CONNU + r"xox[baprs]-[A-Za-z0-9-]{10,}", False),
    # l'en-tête seul (gabarit, documentation, regex d'un analyseur PEM) n'est pas une clé : un corps base64 doit suivre
    ("Clé privée", r"-----BEGIN (?:" + PEM + r")-----(?=(?:\s|\\[nrt])*[A-Za-z0-9+/]{40,})", False),
    ("Convex (déploiement)", BORD_CONNU + r"(?:prod|dev|preview):[a-z0-9-]+(?::[a-z0-9-]+)?\|[A-Za-z0-9=+/]{20,}", False),
    ("Clé sk- (hexadécimale)", BORD_CONNU + r"sk-(?:or-v1-)?[0-9a-f]{32,}(?![A-Za-z0-9])", True),
    ("Resend", BORD_CONNU + r"re_[A-Za-z0-9_]{20,}", True),
    ("Clé sk- (format inconnu)", BORD_CONNU + r"sk-[A-Za-z0-9_-]{20,}", True),
)
# Publiques par conception (Firebase / Maps navigateur) : jamais « à révoquer », mais à restreindre (référent HTTP, API autorisées)
PUBLICS = ("Google API",)
# jeton à tirets dont chaque segment est un mot (≥ 2 lettres) ou un nombre : « Nav-Top-Bar-2024 », « tooltip-arrow-left »
SEGMENT_KEBAB = re.compile(r"^(?:[A-Za-z]{2,}|\d+)$")
DANS_CLASSE = re.compile(r"""class(?:Name)?\s*=\s*["'][^"']*$""")
GABARIT = re.compile(r"example|xxxx|your[_-]|placeholder|redacted", re.I)


def entropie(s):
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values()) if n else 0.0


def est_public(nom):
    return nom in PUBLICS


def _corps(valeur):
    """La partie aléatoire d'une clé générique : ce qui suit le premier « - » (sk-…) ou « _ » (re_…)."""
    return valeur.split("-", 1)[1] if valeur.startswith("sk-") else valeur.split("_", 1)[1]


def _est_kebab(corps):
    segments = corps.split("-")
    return len(segments) >= 3 and all(SEGMENT_KEBAB.match(s) for s in segments)


def _gabarit(texte, m):
    valeur = m.group(0)
    if GABARIT.search(valeur) or (m.start() > 0 and texte[m.start() - 1] == "<") or texte[m.end():m.end() + 1] == ">":
        return True
    if valeur.startswith("-----BEGIN"):
        return False
    return len(set(valeur[-16:])) < 4  # fin de la clé faite d'un ou deux caractères répétés (sk_live_AAAA…, ghp_0000…)


def _generique_plausible(texte, m):
    corps = _corps(m.group(0))
    if _est_kebab(corps) or DANS_CLASSE.search(texte[max(0, m.start() - 200):m.start()]):
        return False
    if len([p for p in corps.split("_") if re.fullmatch(r"[a-z]{3,}", p)]) >= 2:  # mots séparés par « _ » : re_quote_attribute_…
        return False
    if len(re.findall(r"[A-Z][a-z]{3,}", corps)) >= 4:  # camelCase : RenderMenuItem2Large3Active
        return False
    if not (re.search(r"[A-Z]", corps) and re.search(r"[a-z]", corps) and len(re.findall(r"\d+", corps)) >= 2):
        return False  # une clé aléatoire mêle casses et chiffres ; « …Large2024x » n'a qu'un groupe de chiffres
    return entropie(corps) >= 3.5


def _hexadecimale_plausible(texte, m):
    corps = m.group(0).rsplit("-", 1)[-1] if m.group(0).startswith("sk-or-v1-") else m.group(0)[3:]
    if DANS_CLASSE.search(texte[max(0, m.start() - 200):m.start()]):
        return False
    return bool(re.search(r"\d", corps) and re.search(r"[a-f]", corps)) and entropie(corps) >= 3.0


def detecter(texte):
    trouves, pris, vus = [], [], set()
    for nom, motif, generique in FORMATS:
        for m in re.finditer(motif, texte):
            if any(a < m.end() and m.start() < b for a, b in pris):  # déjà couvert par un format plus précis
                continue
            if _gabarit(texte, m):
                continue
            if generique and not (_hexadecimale_plausible(texte, m) if "hexa" in nom else _generique_plausible(texte, m)):
                continue
            pris.append((m.start(), m.end()))
            if m.group(0) not in vus:
                vus.add(m.group(0))
                trouves.append((m.start(), nom, m.group(0)))
    return [(nom, v) for _, nom, v in sorted(trouves)]


def formater(paires):
    return ["{0} : {1}…".format(nom, valeur[:12]) for nom, valeur in paires]


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("-"):
        sys.stderr.write("usage : secrets_js.py FICHIER [--publiques]\n")
        return 2
    publiques = "--publiques" in sys.argv[2:]
    if hasattr(sys.stdout, "reconfigure"):  # sortie toujours en UTF-8, même sous LC_ALL=C / PYTHONIOENCODING=ascii
        sys.stdout.reconfigure(encoding="utf-8")
    with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
        texte = f.read()
    paires = [(n, v) for n, v in detecter(texte) if est_public(n) == publiques]
    for ligne in formater(paires)[:20]:
        print(ligne)
    return 0


if __name__ == "__main__":
    sys.exit(main())
