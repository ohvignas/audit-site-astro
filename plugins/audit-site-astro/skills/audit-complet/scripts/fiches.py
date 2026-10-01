#!/usr/bin/env python3
"""
fiches.py — Chargement des fiches de correction (references/fiches/*.md) et association aux signaux d'un audit.

Module partagé (stdlib seule, Python 3.9). Sert à générer le dossier CORRECTIONS/ remis à un agent de code.

API :
  charger_fiches(dossier)      -> liste de dicts (clés du frontmatter + « corps » sans frontmatter + « chemin »), triée par id ;
                                  ignore _MODELE.md et tout fichier dont le nom commence par « _ » ; valide chaque fiche
                                  (id présent, égal au nom de fichier et unique ; déclencheurs à préfixe connu et regex
                                  compilable) et lève ValueError « <fichier> : … » sinon
  associer(signaux, fiches)    -> (fiche id -> signaux déclencheurs, signaux sans fiche) ; ordre déterministe
  fiches_manuelles(fiches)     -> fiches ayant au moins un déclencheur « manuel:<sujet> » (jamais associées automatiquement ;
                                  à lister comme « Contrôles manuels recommandés »)
  fiches_sans_detection(fiches)-> fiches à « declencheurs: [] » (jamais retenues automatiquement)
  declencheur(texte)           -> (préfixe, motif) d'un déclencheur « préfixe:motif »
  correspond(decl, signal)     -> True si le déclencheur reconnaît le signal
  parse_frontmatter(texte)     -> (dict, corps)

Déclencheurs (frontmatter `declencheurs`) : « <source>:<motif> » où source ∈ crawl, geo, code, http, securite, lighthouse, projet, rendu, domaine, terrain.
  crawl  : égalité exacte avec la clé d'issue du crawl (signal["cle"]) ;
  autres (dont rendu, domaine, terrain) : re.search(motif, signal["cle"], re.I) sur les signaux de la source correspondante ;
  manuel : « manuel:<sujet> », jamais reconnu automatiquement.
"""
import re
from functools import lru_cache
from pathlib import Path

PREFIXES_SIGNAL = ("crawl", "geo", "code", "http", "securite", "lighthouse", "projet", "rendu", "domaine", "terrain")
PREFIXE_MANUEL = "manuel"
PREFIXES = PREFIXES_SIGNAL + (PREFIXE_MANUEL,)

PREFIXES_ID = ("perf", "serveur", "seo", "contenu", "geo", "code", "convex", "secu", "a11y", "rgpd")
DOMAINES = ("Performance", "Serveur / HTTP", "SEO technique", "Contenu", "GEO / IA", "Code", "Sécurité", "Accessibilité",
            "RGPD / traceurs")
SEVERITES = ("critique", "haute", "moyenne", "basse")
EFFORTS = ("S", "M", "L")
SECTIONS = ("Pourquoi c'est important", "Comment le constater soi-même", "Correction", "Critères d'acceptation",
            "Vérification après correction", "Pièges et retour arrière")


# --------------------------------------------------------------------------- parseur de frontmatter (sous-ensemble de YAML)

_ECHAPPEMENTS = {"\\": "\\", '"': '"', "/": "/", "n": "\n", "t": "\t"}


def _chaine_double(s, debut):
    """Lit une chaîne entre guillemets doubles commençant à s[debut] == '"'. Retourne (valeur, index après le guillemet fermant)."""
    out = []
    i = debut + 1
    while i < len(s):
        c = s[i]
        if c == "\\":
            if i + 1 >= len(s):
                break
            suivant = s[i + 1]
            if suivant not in _ECHAPPEMENTS:
                raise ValueError(f"séquence d'échappement inconnue « \\{suivant} » dans {s!r} (doubler l'antislash : \\\\)")
            out.append(_ECHAPPEMENTS[suivant])
            i += 2
        elif c == '"':
            return "".join(out), i + 1
        else:
            out.append(c)
            i += 1
    raise ValueError(f"guillemet fermant manquant : {s!r}")


def _chaine_simple(s, debut):
    """Chaîne entre apostrophes ('' = apostrophe littérale)."""
    out = []
    i = debut + 1
    while i < len(s):
        c = s[i]
        if c == "'":
            if s[i + 1:i + 2] == "'":
                out.append("'")
                i += 2
                continue
            return "".join(out), i + 1
        out.append(c)
        i += 1
    raise ValueError(f"apostrophe fermante manquante : {s!r}")


def _fin_ligne(reste, brut):
    """Après une valeur entre guillemets, seul un commentaire « # … » est admis."""
    r = reste.strip()
    if r and not r.startswith("#"):
        raise ValueError(f"texte inattendu après la valeur : {brut!r}")


def _sans_commentaire(v):
    """Retire un commentaire de fin de ligne (« # » précédé d'un espace) d'une valeur non citée."""
    m = re.search(r"\s#", v)
    return (v[:m.start()] if m else v).strip()


def _scalaire(v):
    """Valeur d'une ligne (déjà strip) : chaîne citée, liste en ligne « [] » / « [a, "b"] », ou scalaire non cité."""
    if v.startswith('"'):
        val, fin = _chaine_double(v, 0)
        _fin_ligne(v[fin:], v)
        return val
    if v.startswith("'"):
        val, fin = _chaine_simple(v, 0)
        _fin_ligne(v[fin:], v)
        return val
    if v.startswith("["):
        return _liste_en_ligne(v)
    return _sans_commentaire(v)


def _liste_en_ligne(v):
    """« [] » ou « [a, "b", 'c'] » (éléments scalaires uniquement)."""
    i = 1
    items = []
    while True:
        while i < len(v) and v[i] in " \t":
            i += 1
        if i >= len(v):
            raise ValueError(f"liste non refermée : {v!r}")
        if v[i] == "]":
            i += 1
            break
        if v[i] == '"':
            val, i = _chaine_double(v, i)
        elif v[i] == "'":
            val, i = _chaine_simple(v, i)
        else:
            j = i
            while j < len(v) and v[j] not in ",]":
                j += 1
            val, i = v[i:j].strip(), j
        items.append(val)
        while i < len(v) and v[i] in " \t":
            i += 1
        if i < len(v) and v[i] == ",":
            i += 1
        elif i < len(v) and v[i] != "]":
            raise ValueError(f"liste mal formée : {v!r}")
    _fin_ligne(v[i:], v)
    return items


_CLE = re.compile(r"^([A-Za-z_][\w-]*):(?:\s+(.*)|\s*)$")
_ITEM = re.compile(r"^\s+-(?:\s+(.*)|\s*)$")


def parse_frontmatter(texte):
    """Sépare un fichier en (dict du frontmatter, corps). Lève ValueError si le frontmatter est absent ou mal formé.

    Sous-ensemble de YAML pris en charge : « clé: valeur » au niveau 0 ; valeurs = scalaire non cité, chaîne entre guillemets
    doubles (échappements \\\\ \\" \\/ \\n \\t) ou simples, « [] » / liste en ligne ; listes en blocs « - élément » indentées (non indentées : refusées) sous une
    clé sans valeur ; commentaires « # … » (ligne entière ou fin de ligne après un espace) ; lignes vides ignorées."""
    lignes = texte.replace("\r\n", "\n").split("\n")
    if not lignes or lignes[0].strip() != "---":
        raise ValueError("frontmatter absent (le fichier doit commencer par « --- »)")
    try:
        fin = next(i for i in range(1, len(lignes)) if lignes[i].strip() == "---")
    except StopIteration:
        raise ValueError("frontmatter non refermé (« --- » de fin manquant)")
    meta = {}
    cle = None  # clé dont les éléments de liste suivent
    for n, ligne in enumerate(lignes[1:fin], start=2):
        if not ligne.strip() or ligne.lstrip().startswith("#"):
            continue
        m_item = _ITEM.match(ligne)
        if m_item and cle is not None and isinstance(meta.get(cle), list):
            meta[cle].append(_scalaire((m_item.group(1) or "").strip()))
            continue
        m = _CLE.match(ligne)
        if not m:
            raise ValueError(f"ligne {n} du frontmatter non reconnue : {ligne!r}")
        cle = m.group(1)
        if cle in meta:
            raise ValueError(f"clé « {cle} » en double (ligne {n})")
        valeur = (m.group(2) or "").strip()
        if valeur and not valeur.startswith("#"):
            meta[cle] = _scalaire(valeur)
            cle = None
        else:
            meta[cle] = []  # liste en blocs (éventuellement vide) ; les « - … » suivants la remplissent
    corps = "\n".join(lignes[fin + 1:]).lstrip("\n")
    return meta, corps


# --------------------------------------------------------------------------- chargement

def charger_fiches(dossier):
    """Charge toutes les fiches *.md du dossier (hors fichiers commençant par « _ »), triées par id.
    Chaque fiche = clés du frontmatter + « corps » (Markdown sans frontmatter) + « chemin » (Path). Les listes
    « declencheurs » et « sources » sont toujours présentes (liste, éventuellement vide).
    Lève ValueError (« <fichier> : … », avec le déclencheur fautif le cas échéant) si le frontmatter est mal formé, si « id »
    manque, diffère du nom de fichier ou est en double, ou si un déclencheur a un préfixe inconnu ou une regex invalide."""
    fiches = []
    vus = {}
    for chemin in sorted(Path(dossier).glob("*.md")):
        if chemin.name.startswith("_"):
            continue
        try:
            meta, corps = parse_frontmatter(chemin.read_text(encoding="utf-8-sig"))
        except ValueError as e:
            raise ValueError(f"{chemin.name} : {e}") from None
        for k, v in list(meta.items()):
            if v == [] and k not in ("declencheurs", "sources"):
                meta[k] = ""  # clé scalaire sans valeur
        for k in ("declencheurs", "sources"):
            if not isinstance(meta.get(k), list):
                meta[k] = [] if meta.get(k) in (None, "") else [meta[k]]
        _valider(chemin, meta)
        if meta["id"] in vus:
            raise ValueError(f"{chemin.name} : id « {meta['id']} » déjà utilisé par {vus[meta['id']]}")
        vus[meta["id"]] = chemin.name
        fiches.append(dict(meta, corps=corps, chemin=chemin))
    return sorted(fiches, key=lambda f: f["id"])


def _valider(chemin, meta):
    ident = meta.get("id")
    if not isinstance(ident, str) or not ident:
        raise ValueError(f"{chemin.name} : clé « id » absente ou vide")
    if ident != chemin.stem:
        raise ValueError(f"{chemin.name} : id « {ident} » différent du nom de fichier")
    for d in meta["declencheurs"]:
        try:
            prefixe, motif = declencheur(d)
            if prefixe not in ("crawl", PREFIXE_MANUEL):
                re.compile(motif, re.I)
        except (ValueError, re.error) as e:
            raise ValueError(f"{chemin.name} : déclencheur {d!r} : {e}") from None


# --------------------------------------------------------------------------- association

def declencheur(texte):
    """« crawl:http_4xx » -> ("crawl", "http_4xx"). Lève ValueError si le préfixe est inconnu ou le motif vide."""
    if not isinstance(texte, str):
        raise ValueError(f"déclencheur invalide : {texte!r} (chaîne attendue)")
    prefixe, sep, motif = texte.partition(":")
    if not sep or prefixe not in PREFIXES or not motif.strip():
        raise ValueError(f"déclencheur invalide : {texte!r} (attendu « <{'|'.join(PREFIXES)}>:<motif> »)")
    return prefixe, motif


@lru_cache(maxsize=None)
def _regex(motif):
    return re.compile(motif, re.I)


def correspond(decl, signal):
    """True si le déclencheur (texte « préfixe:motif ») reconnaît le signal (dict avec « source » et « cle »).
    Les déclencheurs « manuel: » ne correspondent jamais."""
    prefixe, motif = declencheur(decl)
    if prefixe == PREFIXE_MANUEL or signal.get("source") != prefixe:
        return False
    cle = signal.get("cle") or ""
    if prefixe == "crawl":
        return cle == motif
    return _regex(motif).search(cle) is not None


def associer(signaux, fiches):
    """Associe les signaux aux fiches. Retourne (retenues, sans_fiche) :
      retenues  : {id de fiche -> [signaux déclencheurs]} (uniquement les fiches retenues), dans l'ordre des fiches (id) puis des signaux ;
      sans_fiche: signaux qu'aucune fiche ne reconnaît, dans l'ordre d'entrée.
    Un signal peut retenir plusieurs fiches (toutes sont retenues). Les fiches sans déclencheur ou à déclencheurs
    « manuel: » ne sont jamais retenues automatiquement."""
    ordre = sorted(fiches, key=lambda f: f["id"])
    retenues = {}
    reconnus = set()
    for fiche in ordre:
        decls = [d for d in fiche.get("declencheurs", []) if declencheur(d)[0] != PREFIXE_MANUEL]
        for i, s in enumerate(signaux):
            if any(correspond(d, s) for d in decls):
                retenues.setdefault(fiche["id"], []).append(s)
                reconnus.add(i)
    return retenues, [s for i, s in enumerate(signaux) if i not in reconnus]


def fiches_manuelles(fiches):
    """Fiches ayant au moins un déclencheur « manuel:<sujet> » (contrôles à faire à la main), triées par id."""
    return sorted((f for f in fiches if any(declencheur(d)[0] == PREFIXE_MANUEL for d in f.get("declencheurs", []))),
                  key=lambda f: f["id"])


def fiches_sans_detection(fiches):
    """Fiches à « declencheurs: [] » : jamais retenues automatiquement, triées par id."""
    return sorted((f for f in fiches if not f.get("declencheurs")), key=lambda f: f["id"])
