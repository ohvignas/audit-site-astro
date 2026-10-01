#!/usr/bin/env python3
"""ressources_site.py — Ressources de tout le site (pas seulement l'accueil) : images lourdes, JS lourd (octets transférés),
statiques non hashés sans cache long, @font-face sans font-display. Une requête par ressource unique du MÊME hôte (400 au plus),
dans l'ordre du nombre de pages qui l'utilisent (jamais alphabétique : le plafond ou le budget ne doivent pas écarter la
ressource présente partout). Module du diffuseur html_observateurs (T3).

Réseau poli : une pause (ctx["delai"]) entre deux requêtes, délai court (8 s au plus), budget de temps ctx["budget_reseau_s"],
arrêt sur 429 ou après 3 erreurs réseau de suite, jamais d'hôte tiers (une redirection vers un autre hôte n'est pas suivie).
403 / 429 / 999 / erreur réseau = « à vérifier » (compté dans meta, jamais un constat).
Poids : HEAD (Content-Length) d'abord ; sans Content-Length, GET borné (Range pour une image, lecture plafonnée pour un script).
Un script est jugé sur les octets TRANSFÉRÉS (compressés) ; le poids décompressé est noté quand on le connaît.

Aucun secret en sortie : les signatures passent par ho.url_sans_secret (chemin seul, sans requête, segments secrets masqués)."""
import email.utils
import inspect
import re
import time
from urllib.parse import urljoin, urlparse

import html_observateurs as ho

NOM = "ressources_site"
FONT_FACE = re.compile(r"@font-face\s*\{([^}]*)\}", re.I)
FAMILLE = re.compile(r"font-family\s*:\s*['\"]?([^;'\"]+)", re.I)
AFFICHAGE = re.compile(r"font-display\s*:\s*([\w-]+)", re.I)
COMMENTAIRE_CSS = re.compile(r"/\*.*?\*/", re.S)
SEUILS = {"image": 200 * 1024, "script": 150 * 1024}
CACHE_MINI_S = 3600
TIMEOUT_MAX_S = 8            # délai court : simple vérification
MAX_CSS_LUS = 10             # feuilles lues en entier (font-display) ; les suivantes : HEAD seulement
MAX_OCTETS_CSS = 1_000_000
MAX_OCTETS_JS = 3_000_000
MAX_OCTETS_IMAGE = 1_048_576  # lecture plafonnée si le serveur ignore Range
PAUSE_MAX_S = 2.0
ECHECS_DE_SUITE = 3
PAR_PAGE = 150


def hashe(chemin):
    """Fichier dont le nom change à chaque version (cache immuable possible) : sous /_astro/ ou /_next/static/, ou segment de nom de
    8 caractères au moins mêlant lettres et chiffres entre points (app.Bx9a8K2q.js), ou de 8 exactement entre tirets (index-Bx9a8K2q.js)."""
    if chemin.startswith(("/_astro/", "/_next/static/")):
        return True
    nom = chemin.rsplit("/", 1)[-1]

    def mixte(s):
        return bool(re.search(r"\d", s) and re.search(r"[A-Za-z]", s))
    if any(len(s) >= 8 and mixte(s) for s in nom.split(".")[1:-1]):
        return True
    return any(len(s) == 8 and mixte(s) for s in re.split(r"[-_]", nom.rsplit(".", 1)[0]))


def polices_sans_display(css, source):
    """Signatures des @font-face sans font-display, ou en block / auto. Un @font-face dont la seule source est local() (repli ajusté
    généré par Astro) ne charge rien : pas concerné. L'API Fonts d'Astro émet font-display (option `display`, « swap » par défaut)."""
    out = []
    for m in FONT_FACE.finditer(COMMENTAIRE_CSS.sub("", css)):
        bloc = m.group(1)
        if re.search(r"\blocal\(", bloc, re.I) and not re.search(r"\burl\(", bloc, re.I):
            continue
        f, d = FAMILLE.search(bloc), AFFICHAGE.search(bloc)
        famille = f.group(1).strip() if f else "?"
        if not d:
            out.append("{0} ({1})".format(famille, source))
        elif d.group(1).lower() in ("block", "auto"):
            out.append("{0} ({1}, font-display: {2})".format(famille, source, d.group(1).lower()))
    return out


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.ressources, self.polices, self._style = {}, {}, None

    def _ajouter(self, type_, href):
        u = urljoin(self.url, href.strip())
        if urlparse(u).scheme in ("http", "https"):
            self.ressources.setdefault(u, type_)

    def debut(self, noeud, pile):
        t, a = noeud["tag"], noeud["a"]
        if ho.dans(pile, "template", "noscript"):
            return
        if t == "img" and a.get("src"):
            self._ajouter("image", a["src"])
        elif t == "script" and a.get("src"):
            self._ajouter("script", a["src"])
        elif t == "astro-island":  # le JS d'un îlot n'est référencé que par ces attributs
            for k in ("component-url", "renderer-url", "before-hydration-url"):
                if a.get(k):
                    self._ajouter("script", a[k])
        elif t == "link" and a.get("href"):
            rel = a.get("rel", "").lower().split()
            if "modulepreload" in rel:
                self._ajouter("script", a["href"])
            elif "stylesheet" in rel:
                self._ajouter("css", a["href"])
            elif "preload" in rel and a.get("as") in ("image", "script", "font"):
                self._ajouter({"font": "police"}.get(a["as"], a["as"]), a["href"])
        elif t == "style":
            self._style = []

    def texte(self, donnees, pile):
        if self._style is not None:
            self._style.append(donnees)

    def fin(self, noeud, pile):
        if noeud["tag"] == "style" and self._style is not None:
            for sig in polices_sans_display("".join(self._style), "style en ligne"):
                self.polices[sig] = self.polices.get(sig, 0) + 1
            self._style = None

    def resultat(self):
        # ordre d'apparition (déterministe) : la coupe à PAR_PAGE garde les premières ressources de la page
        return {"ressources": [{"type": t, "url": u} for u, t in self.ressources.items()][:PAR_PAGE],
                "polices": [{"signature": k, "n": v} for k, v in sorted(self.polices.items())]}


# --------------------------------------------------------------------------- réseau

def _accepte_max_hops(fetch):
    try:
        return "max_hops" in inspect.signature(fetch).parameters
    except (TypeError, ValueError):
        return False


def _requete(ctx, url, methode, max_bytes, entetes=None, restant=TIMEOUT_MAX_S):
    """Une requête vers le MÊME hôte : jamais de saut vers un tiers. Une redirection vers le même hôte est suivie (2 sauts au plus)."""
    fetch = ctx["fetch"]
    hote = urlparse(url).netloc.lower()
    cible, r = url, None
    for _ in range(3):
        kw = {"timeout": max(1, min(ctx.get("timeout", 20), TIMEOUT_MAX_S, restant)), "method": methode, "max_bytes": max_bytes}
        if entetes:
            kw["extra_headers"] = entetes
        if _accepte_max_hops(fetch):
            kw["max_hops"] = 1
        r = fetch(cible, **kw)
        if r.get("status") == -1 and r.get("chain"):  # redirection non suivie par fetch (max_hops=1)
            suite = r.get("final_url") or ""
            if urlparse(suite).netloc.lower() == hote and suite != cible:
                cible = suite
                continue
            return dict(r, status=r["chain"][0]["status"], headers={}, body=b"")  # vers un tiers : on s'arrête là
        return r
    return dict(r, status=r["chain"][0]["status"] if r.get("chain") else 0, headers={}, body=b"")


def _entier(v):
    try:
        n = int(str(v).strip())
        return n if n >= 0 else None
    except (TypeError, ValueError):
        return None


def _expire_dans(h):
    """Secondes entre Date (ou maintenant) et Expires ; None si absent ou illisible. Sert quand Cache-Control est absent."""
    try:
        exp = email.utils.parsedate_to_datetime(h["expires"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return None
    try:
        ref = email.utils.parsedate_to_datetime(h["date"]).timestamp()
    except (KeyError, TypeError, ValueError):
        ref = time.time()
    return int(exp - ref)


def _mesurer(ctx, url, type_, lire_css, restant):
    """{"type", "statut", "octets", "cache", "ctype", + octets_decompresses, expire_dans_s, tronque} pour une ressource."""
    tronque = False
    decompresses = None
    if type_ == "css" and lire_css:
        r = _requete(ctx, url, "GET", MAX_OCTETS_CSS, restant=restant)
        h = r.get("headers") or {}
        octets = r.get("raw_bytes") or 0
        decompresses = len(r.get("body") or b"")
        tronque = octets >= MAX_OCTETS_CSS
    else:
        r = _requete(ctx, url, "HEAD", 0, restant=restant)
        h = r.get("headers") or {}
        octets = _entier(h.get("content-length"))
        if r["status"] in (405, 501) or (r["status"] == 200 and octets is None):
            # HEAD refusé, ou Content-Length absent (réponse compressée en flux) : GET borné
            if type_ == "script":
                r = _requete(ctx, url, "GET", MAX_OCTETS_JS, restant=restant)
                h = r.get("headers") or {}
                octets = r.get("raw_bytes") or 0
                decompresses = len(r.get("body") or b"")
                tronque = octets >= MAX_OCTETS_JS
            else:
                r = _requete(ctx, url, "GET", MAX_OCTETS_IMAGE, entetes={"Range": "bytes=0-0"}, restant=restant)
                h = r.get("headers") or {}
                total = re.search(r"/(\d+)\s*$", h.get("content-range", ""))
                if r["status"] == 206 and total:
                    octets = int(total.group(1))
                else:  # le serveur ignore Range : lecture plafonnée
                    octets = r.get("raw_bytes") or 0
                    tronque = octets >= MAX_OCTETS_IMAGE
        elif octets is not None and (h.get("content-encoding") or "").strip().lower() in ("", "identity"):
            decompresses = octets  # pas de compression : poids transféré = poids décompressé
    statut = 200 if r["status"] == 206 else r["status"]
    m = {"type": type_, "statut": statut, "octets": octets or 0, "cache": h.get("cache-control", ""), "ctype": h.get("content-type", "")}
    if decompresses is not None:
        m["octets_decompresses"] = decompresses
    if (h.get("content-encoding") or "").strip().lower() not in ("", "identity"):
        m["encodage"] = h["content-encoding"].strip().lower()
    exp = _expire_dans(h)
    if exp is not None:
        m["expire_dans_s"] = exp
    if tronque:
        m["tronque"] = True
    m["corps"] = r.get("body") if type_ == "css" and lire_css and statut == 200 else None
    return m


def apres_crawl(pages, ctx):
    hote = (ctx.get("host") or "").lower()
    sources = {}  # url -> {"type", "pages"}
    for u in sorted(pages):
        for r in ((pages[u].get("obs") or {}).get(NOM) or {}).get("ressources", []):
            pr = urlparse(r["url"])
            if pr.netloc.lower() != hote or pr.path.startswith("/_image") or "…" in r["url"]:  # « … » : segment secret masqué
                continue
            e = sources.setdefault(r["url"], {"type": r["type"], "pages": []})
            if u not in e["pages"]:
                e["pages"].append(u)
    # priorité : nombre de pages qui utilisent la ressource (décroissant), puis adresse (ordre stable) ; jamais l'ordre alphabétique seul
    ordre = sorted(sources, key=lambda x: (-len(sources[x]["pages"]), x))
    plafond = max(0, ctx.get("ressources_max", 400))
    mesures, polices_css = {}, {}
    debut, budget = time.monotonic(), ctx.get("budget_reseau_s", 300)
    pause = min(max(ctx.get("delai") or 0, 0), PAUSE_MAX_S)
    atteint = arret = False
    a_verifier = echecs = lus = 0
    for url in ordre[:plafond]:
        ecoule = time.monotonic() - debut
        if ecoule > budget:  # jamais de crawl coupé par le délai de l'étape
            atteint = True
            break
        if mesures:
            time.sleep(pause)
        type_ = sources[url]["type"]
        m = _mesurer(ctx, url, type_, lire_css=lus < MAX_CSS_LUS, restant=budget - ecoule)
        if type_ == "css" and m.get("corps") is not None:
            lus += 1
        corps = m.pop("corps", None)
        mesures[url] = m
        if m["statut"] in (403, 429, 999) or m["statut"] <= 0:
            a_verifier += 1
        echecs = echecs + 1 if m["statut"] <= 0 else 0
        if corps is not None:
            for sig in polices_sans_display(corps.decode("utf-8", "replace"), ho.url_sans_secret(urlparse(url).path)):
                polices_css.setdefault(sig, []).extend(sources[url]["pages"])
        if m["statut"] == 429 or echecs >= ECHECS_DE_SUITE:
            arret = True
            break
    ctx["ressources"] = mesures
    ctx["sources_ressources"] = {u: e["pages"] for u, e in sources.items()}
    ctx["polices_css"] = polices_css
    ctx.setdefault("meta", {})["ressources"] = {
        "trouvees": len(sources), "mesurees": len(mesures), "non_verifiees": len(sources) - len(mesures),
        "budget_atteint": atteint, "plafond_atteint": len(ordre) > plafond, "interrompu": arret, "a_verifier": a_verifier}


# --------------------------------------------------------------------------- constats

def _cache_court(cc, expire_dans_s=None):
    cc = (cc or "").lower()
    if "no-store" in cc or "no-cache" in cc:
        return True
    m = re.search(r"(?<![\w-])max-age=(\d+)", cc)
    if m:
        return int(m.group(1)) < CACHE_MINI_S
    return not (expire_dans_s is not None and expire_dans_s >= CACHE_MINI_S)  # sans Cache-Control, Expires lointain = cache


def _ko(octets):
    return octets // 1024


def issues(pages, add, ctx):
    lourdes, js, sans_cache = {}, {}, {}
    for url, m in sorted(ctx.get("ressources", {}).items()):
        if m["statut"] != 200 or m["ctype"].lower().startswith("text/html"):
            continue
        chemin = urlparse(url).path
        sig_chemin = ho.url_sans_secret(chemin)
        pages_src = ctx.get("sources_ressources", {}).get(url, [])
        if (m["type"] == "image" or m["ctype"].lower().startswith("image/")) and m["octets"] > SEUILS["image"]:
            plus = "plus de " if m.get("tronque") else ""
            lourdes["{0} ({1}{2} Ko)".format(sig_chemin, plus, _ko(m["octets"]))] = {"n": 1, "pages": pages_src}
        if m["type"] == "script" and m["octets"] > SEUILS["script"]:
            detail = "{0} Ko transférés".format(_ko(m["octets"]))
            if "octets_decompresses" in m:
                detail += ", {0} Ko décompressés".format(_ko(m["octets_decompresses"]))
            detail += " ({0})".format(m["encodage"] if m.get("encodage") else "non compressé")
            js["{0} ({1} Ko transférés)".format(sig_chemin, _ko(m["octets"]))] = {"n": 1, "pages": pages_src, "exemple": detail}
        if not hashe(chemin) and _cache_court(m["cache"], m.get("expire_dans_s")):
            cc = ho.texte_sans_secret(m["cache"] or "absent")[:80]
            sans_cache["{0} (Cache-Control : {1})".format(sig_chemin, cc)] = {"n": 1, "pages": pages_src}
    polices = ho.collecter_groupes(pages, NOM, "polices")
    for sig, srcs in ctx.get("polices_css", {}).items():
        g = polices.setdefault(sig, {"n": 0, "pages": []})
        g["n"] += 1
        g["pages"].extend(srcs)
    ho.ajouter_groupes(add, "image_lourde", "Images de plus de 200 Ko (tout le site)", "moyenne", lourdes, "Performance")
    ho.ajouter_groupes(add, "js_lourd", "Scripts du site de plus de 150 Ko transférés", "moyenne", js, "Performance")
    ho.ajouter_groupes(add, "asset_sans_cache", "Fichiers statiques non hashés sans cache navigateur long (max-age < 1 h)", "basse",
                       sans_cache, "Serveur / HTTP")
    ho.ajouter_groupes(add, "police_sans_font_display", "@font-face sans font-display (ou en block/auto) : texte invisible au chargement",
                       "basse", polices, "Performance")
