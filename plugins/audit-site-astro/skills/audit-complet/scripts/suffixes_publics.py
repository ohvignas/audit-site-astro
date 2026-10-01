#!/usr/bin/env python3
"""
suffixes_publics.py — Public Suffix List (PSL) : domaine enregistrable d'un nom d'hôte et détection des suffixes « privés » de
plateformes (github.io, vercel.app, netlify.app, pages.dev, herokuapp.com…). Module partagé, stdlib seule, Python 3.9, aucun accès
réseau à l'exécution.

Données : `public_suffix_list.dat` (même dossier), instantané de la PSL, non modifié (en-tête MPL-2.0 conservé).
  Source     : https://publicsuffix.org/list/public_suffix_list.dat
  Récupéré   : 2026-10-01 (lecture seule, un seul téléchargement)
  VERSION    : 2026-09-30_20-56-07_UTC
  COMMIT     : 714ac1bf5f2d038161c7419478cc3207431d706d
  Licence    : Mozilla Public License 2.0 (https://mozilla.org/MPL/2.0/), voir l'en-tête du fichier.
  Rafraîchir : retélécharger le fichier à la main depuis l'URL ci-dessus, le recopier tel quel, mettre à jour VERSION/COMMIT et la date
               ci-dessus. Aucun script ne le fait pendant un audit.
Repli : si le fichier est absent, illisible ou vide, une courte liste figée (principaux suffixes à plusieurs étiquettes et plateformes)
est utilisée ; aucune fonction ne lève.

Algorithme standard de la PSL (https://github.com/publicsuffix/list/wiki/Format) : règles normales, jokers « *.x » et exceptions
« !x.y » ; la règle gagnante est l'exception si elle existe, sinon la règle la plus longue, sinon « * » (un seul niveau) ; les
sections ICANN et PRIVATE sont toutes deux prises en compte (« privé » = règle de la section PRIVATE).

API :
  domaine_enregistrable(hote) -> str | None   suffixe public + une étiquette (None si le nom est lui-même un suffixe public,
                                               un nom à une étiquette inconnue ou invalide)
  suffixe_public(hote)        -> str | None   suffixe public du nom (règle « * » par défaut : le dernier niveau)
  suffixe_prive(hote)         -> bool         True si le suffixe public vient de la section PRIVATE (le DNS est celui de la plateforme)
  charger(chemin=None)        -> Regles       règles (mises en cache) ; chaque fonction accepte `regles=` pour les injecter
"""
from functools import lru_cache
from pathlib import Path

DAT = Path(__file__).resolve().with_name("public_suffix_list.dat")

# Repli figé, utilisé uniquement si le fichier .dat est absent ou inexploitable (liste volontairement courte).
_REPLI_ICANN = ("co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk", "ltd.uk", "plc.uk", "com.au", "net.au", "org.au", "edu.au", "gov.au",
                "co.nz", "org.nz", "net.nz", "co.jp", "ne.jp", "or.jp", "ac.jp", "com.br", "net.br", "org.br", "co.za", "org.za",
                "com.cn", "net.cn", "org.cn", "co.in", "net.in", "co.kr", "com.mx", "com.ar", "com.tr", "com.sg", "com.hk", "com.tw",
                "gouv.fr", "asso.fr", "com.fr")
_REPLI_PRIVE = ("github.io", "githubusercontent.com", "gitlab.io", "vercel.app", "now.sh", "netlify.app", "pages.dev", "workers.dev",
                "herokuapp.com", "herokussl.com", "web.app", "firebaseapp.com", "onrender.com", "fly.dev", "convex.site",
                "convex.cloud", "blogspot.com", "azurewebsites.net", "cloudfront.net", "amazonaws.com", "s3.amazonaws.com",
                "appspot.com", "glitch.me", "repl.co", "replit.app", "surge.sh", "railway.app", "deno.dev", "pythonanywhere.com",
                "wixsite.com", "weebly.com")


class Regles:
    """Règles de la PSL : `normal` / `joker` / `exception` -> {règle sans « *. » ni « ! » : vrai si section PRIVATE}."""

    def __init__(self, normal, joker, exception, source):
        self.normal, self.joker, self.exception, self.source = normal, joker, exception, source


def _ascii(regle):
    try:
        return ".".join(l if l.isascii() else l.encode("idna").decode("ascii") for l in regle.split("."))
    except UnicodeError:
        return None


def _analyser(texte):
    normal, joker, exception = {}, {}, {}
    prive = False
    for ligne in texte.splitlines():
        ligne = ligne.strip()
        if ligne.startswith("//"):
            if "===BEGIN PRIVATE DOMAINS===" in ligne:
                prive = True
            elif "===END PRIVATE DOMAINS===" in ligne:
                prive = False
            continue
        if not ligne:
            continue
        regle = _ascii(ligne.split()[0].lower())
        if not regle:
            continue
        if regle.startswith("!"):
            exception[regle[1:]] = prive
        elif regle.startswith("*."):
            joker[regle[2:]] = prive
        else:
            normal[regle] = prive
    return normal, joker, exception


def _repli():
    return Regles({r: False for r in _REPLI_ICANN} | {r: True for r in _REPLI_PRIVE}, {}, {}, "repli")


@lru_cache(maxsize=8)
def _charger(chemin):
    try:
        normal, joker, exception = _analyser(Path(chemin).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return _repli()
    if len(normal) < 100:  # fichier vide, tronqué ou qui n'est pas une PSL
        return _repli()
    return Regles(normal, joker, exception, str(chemin))


def charger(chemin=None):
    """Règles de la PSL du fichier (par défaut l'instantané vendu avec le module) ; repli figé si le fichier est inexploitable."""
    return _charger(str(chemin or DAT))


def _etiquettes(hote):
    if not isinstance(hote, str):
        return None
    hote = hote.strip().lower().rstrip(".")
    if not hote:
        return None
    try:
        hote = hote.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    etiquettes = hote.split(".")
    return None if any(not e for e in etiquettes) else etiquettes


def _regle(etiquettes, r):
    """(nombre d'étiquettes du suffixe public, vrai si la règle gagnante est de la section PRIVATE)."""
    n = len(etiquettes)
    for i in range(n):
        candidat = ".".join(etiquettes[i:])
        if candidat in r.exception:  # l'exception l'emporte ; le suffixe est la règle privée de sa première étiquette
            return n - i - 1, r.exception[candidat]
    for i in range(n):  # du suffixe le plus long au plus court : la première règle qui s'applique est la plus longue
        candidat = ".".join(etiquettes[i:])
        if candidat in r.normal:
            return n - i, r.normal[candidat]
        if i + 1 < n and ".".join(etiquettes[i + 1:]) in r.joker:
            return n - i, r.joker[".".join(etiquettes[i + 1:])]
    return 1, False  # aucune règle : « * »


def suffixe_public(hote, regles=None):
    e = _etiquettes(hote)
    if not e:
        return None
    k, _ = _regle(e, regles or charger())
    return ".".join(e[-k:]) if 0 < k <= len(e) else None


def domaine_enregistrable(hote, regles=None):
    e = _etiquettes(hote)
    if not e:
        return None
    k, _ = _regle(e, regles or charger())
    return ".".join(e[-(k + 1):]) if 0 < k < len(e) else None


def suffixe_prive(hote, regles=None):
    e = _etiquettes(hote)
    if not e:
        return False
    k, prive = _regle(e, regles or charger())
    return bool(prive) and k > 0
