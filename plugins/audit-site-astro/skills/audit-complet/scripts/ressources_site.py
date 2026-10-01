#!/usr/bin/env python3
"""ressources_site.py — Ressources de tout le site (pas seulement l'accueil) : images lourdes, JS lourd (octets transférés),
statiques non hashés sans cache long, @font-face sans font-display. Une requête par ressource unique du MÊME hôte (400 au plus),
dans l'ordre du nombre de pages qui l'utilisent (jamais alphabétique : le plafond ou le budget ne doivent pas écarter la
ressource présente partout). Module du diffuseur html_observateurs (T3).

Réseau poli : une pause (ctx["delai"]) entre deux requêtes, délai court (8 s au plus), budget de temps ctx["budget_reseau_s"],
arrêt sur 429 ou après 3 erreurs réseau de suite, jamais d'hôte tiers (une redirection vers un autre hôte n'est pas suivie).
403 / 429 / 999 / erreur réseau = « à vérifier » (compté dans meta, jamais un constat).
Poids : un script (et un SVG, compressible) est mesuré par un GET « Accept-Encoding: gzip, br » : on compte les octets réellement
transférés (un HEAD renvoie souvent la taille brute : nginx et Express ne compressent pas les HEAD). Image raster, police : HEAD
(Content-Length) puis, sans Content-Length, GET borné (Range). Le poids décompressé n'est noté que s'il est connu et borné : jamais plus
de MAX_DECOMPRESSE octets décompressés (le plafond est demandé à fetch quand il l'accepte : paramètre max_decompressed).

Aucun secret en sortie : les signatures passent par ho.url_sans_secret (chemin seul, sans requête, segments secrets masqués)."""
import email.utils
import inspect
import json
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
MAX_OCTETS_JS = 1_048_576
MAX_DECOMPRESSE = 2_000_000   # jamais plus d'octets décompressés (bombe gzip) ; demandé à fetch via max_decompressed
MAX_PROPS = 65_536
IMAGE_PROPS = re.compile(r"^(?:/(?!/)|https?://)[^\s\"'<>]+\.(?:png|jpe?g|gif|webp|avif|svg)(?:\?[^\s\"']*)?$", re.I)
SEUIL_CACHE_MOYENNE = 100 * 1024
SEUIL_CACHE_MINI = 10 * 1024  # en dessous, un fichier non mis en cache ne vaut pas un constat (favicon, petite icône)
PRIORITE_TYPE = {"script": 0, "css": 1, "police": 2, "image": 3}
SANS_EMPREINTE = re.compile(r"-[0-9a-f]{16}$")
MAX_OCTETS_IMAGE = 1_048_576  # lecture plafonnée si le serveur ignore Range
PAUSE_MAX_S = 2.0
ECHECS_DE_SUITE = 3
PAR_PAGE = 150


_EMPREINTE = re.compile(r"[.\-_]([A-Za-z0-9_-]{8})$")


def _empreinte_plausible(e):
    """8 caractères base64url (Vite / Rollup) : chiffres et lettres mêlés, majuscules et minuscules mêlées (la première lettre ne compte pas :
    « Original »), majuscules seules (CPTKQKQK), ou « _ » / « - » au milieu. Une empreinte de lettres minuscules seules (0,07 % des
    tirages) reste « non hashée » : un mot (« original ») lui ressemble, et on préfère un silence à un faux constat.
    Conséquence assumée : 8 majuscules seules après un séparateur comptent comme une empreinte (« -CPTKQKQK »), donc un nom en capitales de
    8 lettres (« logo-BANNIERE ») est lui aussi traité comme hashé : on se trompe dans le sens du silence (aucun constat de cache)."""
    if re.fullmatch(r"\d+[xX]\d+", e):  # 1920x108 : dimensions
        return False
    mixte = re.search(r"\d", e) and re.search(r"[A-Za-z]", e)
    casse = re.search(r"[a-z]", e) and re.search(r"[A-Z]", e[1:])
    return bool(mixte or casse or e.isupper() or re.search(r"[A-Za-z0-9][_-][A-Za-z0-9]", e))


def hashe(chemin):
    """Fichier dont le nom change à chaque version (cache immuable possible, couvert par H06) : « /_astro/ » ou « /_next/static/ » n'importe
    où dans le chemin (site avec base : /blog/_astro/…), ou nom à empreinte : app.f3a9c2d1e8.webp (segment de 8 caractères ou plus mêlant
    lettres et chiffres entre points), index-DiwrgTda.js / index.DiwrgTda.js / Layout-C2xYpQ_9.js (8 caractères base64url en fin de nom)."""
    if "/_astro/" in chemin or "/_next/static/" in chemin:
        return True
    nom = re.sub(r"\.map$", "", chemin.rsplit("/", 1)[-1])
    stem = nom.rsplit(".", 1)[0] if "." in nom else nom
    if any(len(x) >= 8 and re.search(r"\d", x) and re.search(r"[A-Za-z]", x) for x in stem.split(".")[1:]):
        return True
    m = _EMPREINTE.search(stem)
    return bool(m and _empreinte_plausible(m.group(1)))


def polices_sans_display(css, source):
    """Signatures des @font-face sans font-display, ou en block / auto. Un @font-face dont la seule source est local() (repli ajusté
    généré par Astro) ne charge rien : pas concerné. L'API Fonts d'Astro émet font-display (option `display`, « swap » par défaut)."""
    out = []
    for m in FONT_FACE.finditer(COMMENTAIRE_CSS.sub("", css)):
        bloc = m.group(1)
        if re.search(r"\blocal\(", bloc, re.I) and not re.search(r"\burl\(", bloc, re.I):
            continue
        f, d = FAMILLE.search(bloc), AFFICHAGE.search(bloc)
        famille = SANS_EMPREINTE.sub("", f.group(1).strip()) if f else "?"  # l'API Fonts suffixe un hachage de build
        if not d:
            out.append("{0} ({1})".format(famille, source))
        elif d.group(1).lower() in ("block", "auto"):
            out.append("{0} ({1}, font-display: {2})".format(famille, source, d.group(1).lower()))
    return out


def _chaines(o, profondeur=0):
    """Chaînes d'une valeur JSON (les props d'un îlot Astro enveloppent chaque valeur : [0, "x"], [1, [...]])."""
    if profondeur > 25:
        return
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _chaines(v, profondeur + 1)
    elif isinstance(o, list):
        for v in o:
            yield from _chaines(v, profondeur + 1)


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.hote = urlparse(url).netloc.lower()
        self.ressources, self.polices, self._style = {}, {}, None
        self.ilot = set()  # ressources d'un îlot (props) : même priorité que les scripts, la coupe ne doit pas les écarter

    def _ajouter(self, type_, href, ilot=False):
        u = urljoin(self.url, href.strip())
        pr = urlparse(u)
        # même hôte seulement, hors /_image : le filtre est posé AVANT la coupe à PAR_PAGE (un tiers ne doit pas évincer un îlot)
        if pr.scheme in ("http", "https") and pr.netloc.lower() == self.hote and not pr.path.startswith("/_image"):
            self.ressources.setdefault(u, type_)
            if ilot:
                self.ilot.add(u)

    def _props(self, props):
        """Images passées en props d'un îlot (rendu côté client : aucun <img> dans le HTML). Rien d'autre n'est supposé."""
        if len(props) >= MAX_PROPS:
            return
        try:
            donnees = json.loads(props)
        except ValueError:
            return
        for c in _chaines(donnees):
            if IMAGE_PROPS.match(c):
                self._ajouter("image", c, ilot=True)

    def debut(self, noeud, pile):
        t, a = noeud["tag"], noeud["a"]
        if ho.dans(pile, "template", "noscript"):
            return
        if t == "img" and a.get("src"):
            self._ajouter("image", a["src"])
        elif t == "script" and a.get("src") and "nomodule" not in a:  # polyfills « legacy » : jamais chargés par un navigateur récent
            self._ajouter("script", a["src"])
        elif t == "astro-island":  # le JS d'un îlot n'est référencé que par ces attributs
            for k in ("component-url", "renderer-url", "before-hydration-url"):
                if a.get(k):
                    self._ajouter("script", a[k])
            if a.get("props"):
                self._props(a["props"])
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
        # scripts, images d'îlot (props) et CSS d'abord (le cas lourd n°1 : le JS d'un îlot, en fin de <body>), images ensuite ; ordre d'apparition dans chaque
        # groupe (tri stable, déterministe). Ce qui dépasse PAR_PAGE est compté, pas perdu en silence.
        toutes = sorted(self.ressources.items(), key=lambda e: 0 if e[0] in self.ilot else PRIORITE_TYPE.get(e[1], 9))
        return {"ressources": [{"type": t, "url": u} for u, t in toutes[:PAR_PAGE]],
                "ressources_coupees": max(0, len(toutes) - PAR_PAGE),
                "polices": [{"signature": k, "n": v} for k, v in sorted(self.polices.items())]}


# --------------------------------------------------------------------------- réseau

def _parametres(fetch):
    try:
        return set(inspect.signature(fetch).parameters)
    except (TypeError, ValueError):
        return set()


def _requete(ctx, url, methode, max_bytes, entetes=None, restant=TIMEOUT_MAX_S, decompresse_max=None):
    """Une requête vers le MÊME hôte : jamais de saut vers un tiers. Une redirection vers le même hôte est suivie (2 sauts au plus)."""
    fetch = ctx["fetch"]
    hote = urlparse(url).netloc.lower()
    cible, r = url, None
    for _ in range(3):
        kw = {"timeout": max(1, min(ctx.get("timeout", 20), TIMEOUT_MAX_S, restant)), "method": methode, "max_bytes": max_bytes}
        if entetes:
            kw["extra_headers"] = entetes
        params = _parametres(fetch)
        if "max_hops" in params:
            kw["max_hops"] = 1
        if decompresse_max and "max_decompressed" in params:  # plafond de décompression (gzip bomb) : fetch partagé, T22
            kw["max_decompressed"] = decompresse_max
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
    """{"type", "statut", "octets", "cache", "ctype", + octets_decompresses, decompresse_tronque, encodage, expire_dans_s, tronque} ;
    "corps" (texte d'un CSS lu, borné) est retiré par l'appelant."""
    tronque = False
    decompresses, decompresse_tronque = None, False
    corps = None
    chemin = urlparse(url).path.lower()
    lu_en_get = (type_ == "css" and lire_css) or type_ == "script" or chemin.endswith((".svg", ".svgz"))
    if lu_en_get:
        # GET : octets réellement transférés (jamais le Content-Length d'un HEAD, souvent la taille brute). Le CSS est lu en gzip/deflate
        # (fetch les décode) ; script et SVG sont annoncés « gzip, br » comme un navigateur : seul raw_bytes compte.
        plafond = MAX_OCTETS_CSS if type_ == "css" else MAX_OCTETS_JS
        entetes = None if type_ == "css" else {"Accept-Encoding": "gzip, br"}
        r = _requete(ctx, url, "GET", plafond, entetes=entetes, restant=restant, decompresse_max=MAX_DECOMPRESSE)
        h = r.get("headers") or {}
        octets = r.get("raw_bytes") or 0
        tronque = octets >= plafond
        corps = (r.get("body") or b"")
        enc = (h.get("content-encoding") or "").strip().lower()
        if len(corps) > MAX_DECOMPRESSE:  # fetch non borné : on ne garde jamais plus que le plafond
            corps = corps[:MAX_DECOMPRESSE]
            decompresse_tronque = enc in ("gzip", "x-gzip", "deflate")
        elif not tronque and enc in ("gzip", "x-gzip", "deflate") and len(corps) >= MAX_DECOMPRESSE:
            decompresse_tronque = True
        elif not tronque and enc in ("", "identity", "gzip", "x-gzip", "deflate"):
            decompresses = len(corps)  # brotli : fetch ne le décode pas, le corps reçu n'est pas le texte
        if decompresse_tronque:
            decompresses = None
    else:
        r = _requete(ctx, url, "HEAD", 0, restant=restant)
        h = r.get("headers") or {}
        octets = _entier(h.get("content-length"))
        if r["status"] in (405, 501) or (r["status"] == 200 and octets is None):
            # HEAD refusé, ou Content-Length absent : GET borné (Range : jamais l'image entière)
            r = _requete(ctx, url, "GET", MAX_OCTETS_IMAGE, entetes={"Range": "bytes=0-0"}, restant=restant)
            h = r.get("headers") or {}
            total = re.search(r"/(\d+)\s*$", h.get("content-range", ""))
            if r["status"] == 206 and total:
                octets = int(total.group(1))
            else:  # le serveur ignore Range : lecture plafonnée
                octets = r.get("raw_bytes") or 0
                tronque = octets >= MAX_OCTETS_IMAGE
    statut = 200 if r["status"] == 206 else r["status"]
    m = {"type": type_, "statut": statut, "octets": octets or 0, "cache": h.get("cache-control", ""), "ctype": h.get("content-type", "")}
    if decompresses is not None:
        m["octets_decompresses"] = decompresses
    if decompresse_tronque:
        m["decompresse_tronque"] = True
    if (h.get("content-encoding") or "").strip().lower() not in ("", "identity"):
        m["encodage"] = h["content-encoding"].strip().lower()
    exp = _expire_dans(h)
    if exp is not None:
        m["expire_dans_s"] = exp
    if tronque:
        m["tronque"] = True
    m["corps"] = corps if type_ == "css" and lire_css and statut == 200 else None
    return m


def apres_crawl(pages, ctx):
    hote = (ctx.get("host") or "").lower()
    sources = {}  # url -> {"type", "pages"}
    secret = set()
    coupees = 0
    for u in sorted(pages):
        obs = (pages[u].get("obs") or {}).get(NOM) or {}
        coupees += obs.get("ressources_coupees", 0) if isinstance(obs.get("ressources_coupees"), int) else 0
        for r in obs.get("ressources", []):
            pr = urlparse(r["url"])
            if pr.netloc.lower() != hote or pr.path.startswith("/_image"):
                continue
            if "…" in r["url"]:  # segment secret masqué par l'assainissement : jamais requêté, mais compté
                secret.add(r["url"])
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
    a_verifier = echecs = lus = css_non_lus = 0
    for url in ordre[:plafond]:
        ecoule = time.monotonic() - debut
        if ecoule > budget:  # jamais de crawl coupé par le délai de l'étape
            atteint = True
            break
        if mesures:
            time.sleep(pause)
        type_ = sources[url]["type"]
        lire_css = lus < MAX_CSS_LUS
        if type_ == "css" and not lire_css:
            css_non_lus += 1  # font-display de cette feuille non vérifié
        m = _mesurer(ctx, url, type_, lire_css=lire_css, restant=budget - ecoule)
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
        "budget_atteint": atteint, "plafond_atteint": len(ordre) > plafond, "interrompu": arret, "a_verifier": a_verifier,
        "ignorees_secret": len(secret), "css_non_lus": css_non_lus, "coupees_par_page": coupees}


# --------------------------------------------------------------------------- constats

def _cache_court(cc, expire_dans_s=None):
    cc = (cc or "").lower()
    if "no-store" in cc or "no-cache" in cc:
        return True
    m = re.search(r"(?<![\w-])max-age=(\d+)", cc)
    if m:
        return int(m.group(1)) < CACHE_MINI_S
    return not (expire_dans_s is not None and expire_dans_s >= CACHE_MINI_S)  # sans Cache-Control, Expires lointain = cache


def _cache_nul(cc):
    """max-age=0, no-cache ou no-store : le navigateur revalide ou retélécharge à chaque usage."""
    cc = (cc or "").lower()
    m = re.search(r"(?<![\w-])max-age=(\d+)", cc)
    return "no-store" in cc or "no-cache" in cc or bool(m and int(m.group(1)) == 0)


def _ko(octets):
    return octets // 1024


def issues(pages, add, ctx):
    lourdes, js, sans_cache = {}, {}, {}
    grave = False  # un asset >= SEUIL_CACHE_MOYENNE sans aucun cache : la clé entière passe en « moyenne » (une gravité par clé)
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
            plus = "plus de " if m.get("tronque") else ""
            detail = "{0}{1} Ko transférés".format(plus, _ko(m["octets"]))
            if "octets_decompresses" in m:
                detail += ", {0} Ko décompressés".format(_ko(m["octets_decompresses"]))
            elif m.get("decompresse_tronque"):
                detail += ", plus de {0} Ko décompressés".format(MAX_DECOMPRESSE // 1000)
            detail += " ({0})".format(m["encodage"] if m.get("encodage") else "non compressé")
            js["{0} ({1}{2} Ko transférés)".format(sig_chemin, plus, _ko(m["octets"]))] = {"n": 1, "pages": pages_src, "exemple": detail}
        if not hashe(chemin) and m["octets"] >= SEUIL_CACHE_MINI and _cache_court(m["cache"], m.get("expire_dans_s")):
            cc = ho.texte_sans_secret(m["cache"] or "absent")[:80]
            sans_cache["{0} (Cache-Control : {1})".format(sig_chemin, cc)] = {"n": 1, "pages": pages_src}
            grave = grave or (m["octets"] >= SEUIL_CACHE_MOYENNE and _cache_nul(m["cache"]))
    polices = ho.collecter_groupes(pages, NOM, "polices")
    for sig, srcs in ctx.get("polices_css", {}).items():
        g = polices.setdefault(sig, {"n": 0, "pages": []})
        g["n"] += 1
        g["pages"].extend(srcs)
    ho.ajouter_groupes(add, "image_lourde", "Images de plus de 200 Ko (tout le site)", "moyenne", lourdes, "Performance")
    ho.ajouter_groupes(add, "js_lourd", "Scripts du site de plus de 150 Ko transférés", "moyenne", js, "Performance")
    ho.ajouter_groupes(add, "asset_sans_cache", "Fichiers statiques non hashés sans cache navigateur long (max-age < 1 h)",
                       "moyenne" if grave else "basse", sans_cache, "Serveur / HTTP")
    ho.ajouter_groupes(add, "police_sans_font_display", "@font-face sans font-display (ou en block/auto) : texte invisible au chargement",
                       "basse", polices, "Performance")
