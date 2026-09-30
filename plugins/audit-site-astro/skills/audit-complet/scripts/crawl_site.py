#!/usr/bin/env python3
"""
crawl_site.py — Crawler SEO technique pour sites WordPress (Python 3.8+, stdlib uniquement).

Usage :
  python3 crawl_site.py https://exemple.fr --out AUDIT_DIR/data/crawl \
      [--max-pages 500] [--delay 0.3] [--timeout 20] [--ignore-robots] [--check-images 300]

Produit dans --out :
  pages.json   données complètes par URL (réutilisées par les autres skills)
  pages.csv    vue tableur
  issues.json  problèmes détectés, regroupés, avec sévérité indicative et exemples
  summary.md   synthèse lisible

Le crawl part de la page d'accueil (parcours en largeur = profondeur de clic),
puis visite les URL du sitemap non trouvées par les liens (candidates orphelines).
"""
import argparse
import csv
import gzip
import json
import os
import re
import ssl
import sys
import time
import zlib
from collections import Counter, defaultdict, deque
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

UA = "Mozilla/5.0 (compatible; AuditWPAstra/1.0; audit interne)"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

SKIP_EXT = re.compile(
    r"\.(jpe?g|png|gif|webp|avif|svg|ico|bmp|tiff?|pdf|zip|gz|rar|7z|mp[34]|m4a|wav|ogg|webm|mov|avi|"
    r"css|js|json|xml|txt|woff2?|ttf|eot|otf|docx?|xlsx?|pptx?|csv|ics)$", re.I)
SKIP_PATH = re.compile(
    r"(/wp-admin/|/wp-login\.php|/wp-json/|/xmlrpc\.php|/feed/?$|/comments/feed|/wp-content/|"
    r"/wp-includes/|/cdn-cgi/|/trackback/?$)", re.I)
SKIP_QUERY = re.compile(r"(^|&)(replytocom|share|add-to-cart|add_to_wishlist|preview|s|ver|nocache)=", re.I)
COUNT_TAGS = {"ul", "ol", "table", "time", "main", "article", "iframe", "video", "form", "nav", "script", "link"}
SKIP_TEXT_TAGS = {"script", "style", "noscript", "svg", "template"}
# Chemins de CSS/JS nécessaires au rendu : WordPress, Astro (/_astro/), Next.js (/_next/)
# Éléments sans balise fermante (ne s'empilent pas) ; styles qui masquent un élément
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
STYLE_MASQUE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)


def masque(tag, a):
    """Élément absent de l'arbre d'accessibilité (ignoré par axe/Lighthouse) : hidden, aria-hidden, style, template."""
    return (tag in ("template", "noscript") or "hidden" in a or a.get("aria-hidden", "").lower() == "true"
            or bool(STYLE_MASQUE.search(a.get("style", ""))))


ASSETS_RX = re.compile(r"\.(css|js)|wp-content/(themes|plugins)|wp-includes|/_astro\b|/_next/", re.I)


# --------------------------------------------------------------------------- HTTP

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENERS = {}


def _opener():
    """Opener sans suivi automatique des redirections ; TLS non vérifié si AUDIT_INSECURE_TLS=1 (tests)."""
    insecure = os.environ.get("AUDIT_INSECURE_TLS") == "1"
    if insecure not in _OPENERS:
        handlers = [_NoRedirect()]
        if insecure:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            handlers.append(urllib.request.HTTPSHandler(context=ctx))
        _OPENERS[insecure] = urllib.request.build_opener(*handlers)
    return _OPENERS[insecure]


def _decompress(body, enc):
    try:
        if enc == "gzip":
            return gzip.decompress(body)
        if enc == "deflate":
            try:
                return zlib.decompress(body)
            except zlib.error:
                return zlib.decompress(body, -zlib.MAX_WBITS)
    except Exception:
        pass
    return body


def fetch(url, timeout=20, method="GET", max_bytes=8_000_000, ua=UA, extra_headers=None):
    """GET/HEAD en suivant les redirections à la main pour conserver la chaîne complète."""
    chain = []
    current = url
    t_start = time.time()
    for _ in range(10):
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6",
        }
        if extra_headers:
            headers.update(extra_headers)
        try:
            req = urllib.request.Request(current, method=method, headers=headers)
        except ValueError as e:
            return {"url": url, "final_url": current, "status": 0, "error": f"URL invalide : {e}", "chain": chain,
                    "headers": {}, "body": b"", "raw_bytes": 0, "ttfb": None, "time": 0}
        t_hop = time.time()
        try:
            resp = _opener().open(req, timeout=timeout)
            status, hdrs = resp.status, resp.headers
            ttfb = time.time() - t_hop
            body = resp.read(max_bytes) if method == "GET" else b""
            resp.close()
        except urllib.error.HTTPError as e:
            status, hdrs = e.code, e.headers
            ttfb = time.time() - t_hop
            if 300 <= status < 400 and hdrs.get("Location"):
                chain.append({"url": current, "status": status})
                current = urljoin(current, hdrs["Location"])
                continue
            try:
                body = e.read(max_bytes) if method == "GET" else b""
            except Exception:
                body = b""
        except Exception as e:  # DNS, TLS, timeout...
            return {"url": url, "final_url": current, "status": 0, "error": str(e)[:200], "chain": chain,
                    "headers": {}, "body": b"", "raw_bytes": 0, "ttfb": None,
                    "time": round(time.time() - t_start, 3)}
        enc = (hdrs.get("Content-Encoding") or "").lower().strip()
        raw_len = len(body)
        body = _decompress(body, enc)
        return {"url": url, "final_url": current, "status": status, "error": None, "chain": chain,
                "headers": {k.lower(): v for k, v in hdrs.items()}, "body": body, "raw_bytes": raw_len,
                "ttfb": round(ttfb, 3), "time": round(time.time() - t_start, 3)}
    return {"url": url, "final_url": current, "status": -1, "error": "plus de 10 redirections", "chain": chain,
            "headers": {}, "body": b"", "raw_bytes": 0, "ttfb": None, "time": round(time.time() - t_start, 3)}


def decode_body(res):
    ctype = res["headers"].get("content-type", "")
    m = re.search(r"charset=([\w-]+)", ctype, re.I)
    enc = m.group(1) if m else "utf-8"
    try:
        return res["body"].decode(enc, errors="replace")
    except LookupError:
        return res["body"].decode("utf-8", errors="replace")


def normalize(u):
    if not u:
        return None
    u, _ = urldefrag(u.strip())
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    netloc = p.netloc.lower()
    if (p.scheme == "http" and netloc.endswith(":80")) or (p.scheme == "https" and netloc.endswith(":443")):
        netloc = netloc.rsplit(":", 1)[0]
    return urlunparse((p.scheme.lower(), netloc, p.path or "/", p.params, p.query, ""))


# --------------------------------------------------------------------------- robots.txt (sémantique Google)

class RobotsTxt:
    """Groupes par user-agent, règle la plus longue gagnante, égalité => Allow (comme Google)."""

    def __init__(self, text=""):
        self.groups = []      # [(set(agents), [(allow, pattern)])]
        self.sitemaps = []
        self.raw = text or ""
        self.other_lines = []  # ex. Content-Signal (Cloudflare)
        agents, rules, last_was_agent = set(), [], False
        for line in self.raw.splitlines():
            line = line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, val = [x.strip() for x in line.split(":", 1)]
            key = key.lower()
            if key == "user-agent":
                if not last_was_agent and (agents or rules):
                    self.groups.append((agents, rules))
                    agents, rules = set(), []
                agents.add(val.lower())
                last_was_agent = True
            elif key in ("allow", "disallow"):
                last_was_agent = False
                if val or key == "allow":
                    rules.append((key == "allow", val))
            elif key == "sitemap":
                self.sitemaps.append(val)
            else:
                last_was_agent = False
                self.other_lines.append(f"{key}: {val}")
        if agents or rules:
            self.groups.append((agents, rules))

    def rules_for(self, token):
        token = token.lower()
        matched = [r for a, r in self.groups if token in a]
        if not matched:
            matched = [r for a, r in self.groups if "*" in a]
        return [rule for group in matched for rule in group], bool(matched)

    def explicit_group(self, token):
        return any(token.lower() in a for a, _ in self.groups)

    @staticmethod
    def _match(pattern, path):
        if not pattern:
            return False
        rx = re.escape(pattern).replace(r"\*", ".*")
        if rx.endswith(r"\$"):
            rx = rx[:-2] + "$"
        return re.match(rx, path) is not None

    def allowed(self, token, url):
        p = urlparse(url)
        path = (p.path or "/") + (("?" + p.query) if p.query else "")
        rules, _ = self.rules_for(token)
        best_len, best_allow = -1, True
        for allow, pattern in rules:
            if self._match(pattern, path):
                length = len(pattern)
                if length > best_len or (length == best_len and allow):
                    best_len, best_allow = length, allow
        return best_allow


# --------------------------------------------------------------------------- HTML

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = None
        self._in_title = False
        self._title_buf = []
        self.metas = {}
        self.canonicals = []
        self.hreflang = []
        self.links = []  # dict(href, rel, text)
        self.headings = []  # (level, text)
        self._h = None
        self._h_buf = []
        self.imgs = []
        self.jsonld_raw = []
        self._in_jsonld = False
        self._jsonld_buf = []
        self.lang = None
        self.body_class = ""
        self._skip = 0
        self.words = 0
        self.main_words = 0
        self._main_depth = 0
        self._main_by_article = False
        self._a = None
        self.resources = []
        self.microdata = 0
        self.tags = Counter()
        self.tags_main = Counter()
        self.has_author_link = False
        self.fields = []        # champs de formulaire saisissables
        self.label_for = set()  # id visés par <label for>
        self._label_depth = 0
        self._ouverts = []      # pile [balise, masquée] des éléments ouverts (ancêtres masqués des champs)
        self._masques = 0

    def champs_sans_libelle(self):
        """Champs sans nom accessible fiable : ni <label for>, ni <label> englobant, ni aria-label(ledby), ni title.
        Un placeholder seul ne compte pas (il disparaît à la saisie — WCAG 3.3.2), même si Lighthouse l'accepte."""
        return [c for c in self.fields
                if not (c["nomme"] or c["dans_label"] or (c["id"] and c["id"] in self.label_for))]

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        cache = masque(tag, a)
        if tag not in VOID_TAGS:
            self._ouverts.append((tag, cache))
            self._masques += cache
        if tag in COUNT_TAGS:
            self.tags[tag] += 1
            if self._main_depth:
                self.tags_main[tag] += 1
        if "itemtype" in a:
            self.microdata += 1
        if tag == "html":
            self.lang = a.get("lang") or None
        elif tag == "body":
            self.body_class = a.get("class", "")
        elif tag == "title" and self.title is None:
            self._in_title = True
        elif tag == "meta":
            name = (a.get("name") or a.get("property") or a.get("http-equiv") or "").lower()
            if name and name not in self.metas:
                self.metas[name] = a.get("content", "")
        elif tag == "link":
            rel = a.get("rel", "").lower().split()
            href = a.get("href", "")
            if "canonical" in rel:
                self.canonicals.append(href)
            if "alternate" in rel and a.get("hreflang"):
                self.hreflang.append((a["hreflang"].lower(), href))
            if "author" in rel:
                self.has_author_link = True
            if "stylesheet" in rel and href:
                self.resources.append(href)
        elif tag == "a":
            rel = a.get("rel", "").lower()
            if "author" in rel.split():
                self.has_author_link = True
            self._a = {"href": a.get("href", ""), "rel": rel, "text": []}
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._h, self._h_buf = int(tag[1]), []
        elif tag == "img":
            self.imgs.append({
                "src": a.get("src") or a.get("data-src") or "",
                "alt": a.get("alt") if "alt" in a else None,
                "width": a.get("width"), "height": a.get("height"),
                "loading": a.get("loading"), "fetchpriority": a.get("fetchpriority"),
            })
            if a.get("src"):
                self.resources.append(a["src"])
        elif tag == "script":
            if "ld+json" in a.get("type", "").lower():
                self._in_jsonld, self._jsonld_buf = True, []
            else:
                self._skip += 1
            if a.get("src"):
                self.resources.append(a["src"])
        elif tag == "label":
            self._label_depth += 1
            if a.get("for"):
                self.label_for.add(a["for"])
        elif tag in ("input", "select", "textarea"):
            kind = (a.get("type") or "text").lower() if tag == "input" else tag
            # champs masqués, désactivés ou pièges à robots (honeypot : tabindex=-1) : hors de l'arbre d'accessibilité
            invisible = self._masques or cache or "disabled" in a or a.get("tabindex", "").strip() == "-1"
            if kind not in ("hidden", "submit", "button", "reset", "image") and not invisible:
                self.fields.append({"id": a.get("id", ""), "dans_label": self._label_depth > 0,
                                    "nomme": any(a.get(k, "").strip() for k in ("aria-label", "aria-labelledby", "title"))})
        elif tag in ("iframe", "source", "video", "audio", "embed"):
            if a.get("src"):
                self.resources.append(a["src"])
        if tag in SKIP_TEXT_TAGS and tag != "script":
            self._skip += 1
        if tag == "main":
            self._main_depth += 1
        elif tag == "article" and self._main_depth == 0 and self.tags["main"] == 0:
            self._main_depth += 1
            self._main_by_article = True

    def handle_endtag(self, tag):
        for i in range(len(self._ouverts) - 1, -1, -1):
            if self._ouverts[i][0] == tag:  # ferme aussi les éléments laissés ouverts (<li>, <p>…)
                self._masques -= sum(m for _, m in self._ouverts[i:])
                del self._ouverts[i:]
                break
        if tag == "title" and self._in_title:
            self._in_title = False
            self.title = " ".join("".join(self._title_buf).split())
        elif tag == "script":
            if self._in_jsonld:
                self._in_jsonld = False
                self.jsonld_raw.append("".join(self._jsonld_buf))
            elif self._skip:
                self._skip -= 1
        elif tag in SKIP_TEXT_TAGS and self._skip:
            self._skip -= 1
        elif tag == "label" and self._label_depth:
            self._label_depth -= 1
        elif tag == "a" and self._a is not None:
            self._a["text"] = " ".join(" ".join(self._a["text"]).split())[:120]
            self.links.append(self._a)
            self._a = None
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self._h:
            self.headings.append((self._h, " ".join(" ".join(self._h_buf).split())[:200]))
            self._h = None
        if self._main_depth and (tag == "main" or (tag == "article" and self._main_by_article)):
            self._main_depth -= 1

    def handle_data(self, data):
        if self._in_title:
            self._title_buf.append(data)
            return
        if self._in_jsonld:
            self._jsonld_buf.append(data)
            return
        if self._skip:
            return
        n = len(data.split())
        self.words += n
        if self._main_depth:
            self.main_words += n
        if self._a is not None:
            self._a["text"].append(data)
        if self._h:
            self._h_buf.append(data)


def jsonld_types(raw_blocks):
    types, errors, objects = [], 0, []

    def walk(o):
        if isinstance(o, dict):
            t = o.get("@type")
            if isinstance(t, list):
                types.extend(str(x) for x in t)
            elif t:
                types.append(str(t))
            if t:
                objects.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for raw in raw_blocks:
        try:
            walk(json.loads(raw))
        except Exception:
            errors += 1
    return types, errors, objects


# --------------------------------------------------------------------------- sitemaps

def parse_sitemaps(start_urls, timeout, limit_maps=200):
    urls, lastmods, seen_maps, errors = [], {}, set(), []
    todo = deque(start_urls)
    while todo and len(seen_maps) < limit_maps:
        sm = todo.popleft()
        if sm in seen_maps:
            continue
        seen_maps.add(sm)
        res = fetch(sm, timeout=timeout, ua=UA)
        if res["status"] != 200 or not res["body"]:
            errors.append(f"{sm} → HTTP {res['status']}")
            continue
        body = res["body"]
        if body[:2] == b"\x1f\x8b":
            body = _decompress(body, "gzip")
        try:
            root = ET.fromstring(body)
        except ET.ParseError as e:
            errors.append(f"{sm} → XML invalide ({e})")
            continue
        tag = root.tag.split("}")[-1]
        for node in root:
            loc = lastmod = None
            for child in node:
                ctag = child.tag.split("}")[-1]
                if ctag == "loc":
                    loc = (child.text or "").strip()
                elif ctag == "lastmod":
                    lastmod = (child.text or "").strip()
            if not loc:
                continue
            if tag == "sitemapindex":
                todo.append(loc)
            else:
                n = normalize(loc)
                if n:
                    urls.append(n)
                    if lastmod:
                        lastmods[n] = lastmod
    return urls, lastmods, sorted(seen_maps), errors


# --------------------------------------------------------------------------- analyse

def analyze_page(url, res):
    page = {
        "url": url,
        "status": res["chain"][0]["status"] if res["chain"] else res["status"],
        "final_status": res["status"],
        "final_url": normalize(res["final_url"]) or res["final_url"],
        "redirect_hops": len(res["chain"]),
        "redirect_chain": res["chain"],
        "error": res["error"],
        "ttfb": res["ttfb"],
        "time": res["time"],
        "bytes_transfer": res["raw_bytes"],
        "bytes_html": len(res["body"]),
        "content_type": res["headers"].get("content-type", ""),
        "x_robots_tag": res["headers"].get("x-robots-tag", ""),
        "cache_headers": {k: v for k, v in res["headers"].items()
                          if k in ("cache-control", "age", "x-cache", "cf-cache-status", "x-litespeed-cache",
                                   "x-proxy-cache", "x-cache-status", "x-fastcgi-cache", "x-wp-cache",
                                   "x-rocket-nginx-serving-static", "server", "x-powered-by")},
    }
    is_html = "html" in page["content_type"].lower()
    page["is_html"] = is_html
    # une URL qui redirige n'est pas analysée : sa cible est crawlée pour elle-même
    if not (is_html and res["status"] == 200) or res["chain"]:
        return page, None
    html = decode_body(res)
    parser = PageParser()
    try:
        parser.feed(html)
    except Exception as e:
        page["error"] = f"parse: {e}"
    robots_meta = (parser.metas.get("robots", "") + "," + parser.metas.get("googlebot", "")).lower()
    xr = page["x_robots_tag"].lower()
    types, jl_err, _ = jsonld_types(parser.jsonld_raw)
    h1 = [t for lvl, t in parser.headings if lvl == 1]
    imgs = parser.imgs
    page.update({
        "title": parser.title or "",
        "meta_description": parser.metas.get("description", ""),
        "meta_robots": robots_meta.strip(","),
        "noindex": "noindex" in robots_meta or "noindex" in xr or "none" in robots_meta.split(","),
        "nofollow_meta": "nofollow" in robots_meta,
        "canonicals": [normalize(urljoin(res["final_url"], c)) or c for c in parser.canonicals],
        "hreflang": parser.hreflang,
        "lang": parser.lang,
        "viewport": bool(parser.metas.get("viewport")),
        "og_title": bool(parser.metas.get("og:title")),
        "og_image": bool(parser.metas.get("og:image")),
        "og_site_name": parser.metas.get("og:site_name", ""),
        "article_modified": parser.metas.get("article:modified_time", ""),
        "article_published": parser.metas.get("article:published_time", ""),
        "h1": h1,
        "headings": parser.headings[:80],
        "words": parser.words,
        "content_words": parser.main_words if parser.main_words else parser.words,
        "has_main": parser.tags["main"] > 0,
        "imgs": len(imgs),
        "imgs_no_alt": sum(1 for i in imgs if i["alt"] is None),
        "imgs_empty_alt": sum(1 for i in imgs if i["alt"] == ""),
        "imgs_no_dims": sum(1 for i in imgs if not (i["width"] and i["height"])),
        "imgs_lazy_first": bool(imgs and (imgs[0].get("loading") == "lazy")),
        "img_srcs": [i["src"] for i in imgs][:200],
        "jsonld_types": sorted(set(types)),
        "jsonld_errors": jl_err,
        "microdata_items": parser.microdata,
        "tag_counts": dict(parser.tags),
        "form_fields_no_label": len(parser.champs_sans_libelle()),
        "has_author_link": parser.has_author_link,
        "body_class": parser.body_class[:300],
        "astra": "ast-" in parser.body_class or "/themes/astra" in html,
        "astro": "data-astro-cid" in html or "astro-island" in html or "/_astro/" in html,
        "astro_islands": html.count("<astro-island"),
        "hydration": dict(Counter(re.findall(r'client="(load|idle|visible|media|only)"', html))),
        "mixed_content": sorted({r for r in parser.resources if r.startswith("http://")})[:20]
        if res["final_url"].startswith("https://") else [],
    })
    return page, parser


def tokenize(title):
    stop = {"les", "des", "une", "pour", "avec", "dans", "sur", "par", "est", "vos", "nos", "votre", "notre",
            "the", "and", "for", "you", "your", "comment", "qui", "que", "aux", "plus", "tout", "tous"}
    return {t for t in re.findall(r"[a-zà-ÿ0-9]{3,}", title.lower()) if t not in stop}


# --------------------------------------------------------------------------- crawl

def crawl(args):
    start = normalize(args.url)
    if not start:
        sys.exit("URL invalide")
    host = urlparse(start).netloc
    bare = host[4:] if host.startswith("www.") else host
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # Suivre une éventuelle redirection de la home (http→https, www) pour fixer l'hôte canonique
    first = fetch(start, timeout=args.timeout)
    if first["final_url"] and normalize(first["final_url"]):
        final_home = normalize(first["final_url"])
        if urlparse(final_home).netloc != host:
            print(f"[info] la home redirige vers {final_home} — hôte de crawl ajusté", file=sys.stderr)
            host = urlparse(final_home).netloc
            start = final_home
    scheme = urlparse(start).scheme

    robots_res = fetch(f"{scheme}://{host}/robots.txt", timeout=args.timeout)
    robots = RobotsTxt(decode_body(robots_res) if robots_res["status"] == 200 else "")
    relative_sitemaps = [sm for sm in robots.sitemaps if not sm.lower().startswith("http")]
    robots.sitemaps = [urljoin(f"{scheme}://{host}/", sm) for sm in robots.sitemaps]
    sm_candidates = robots.sitemaps or [f"{scheme}://{host}/sitemap_index.xml", f"{scheme}://{host}/sitemap.xml",
                                        f"{scheme}://{host}/wp-sitemap.xml"]
    sm_urls, lastmods, sm_files, sm_errors = parse_sitemaps(sm_candidates, args.timeout)
    if not sm_urls and robots.sitemaps:
        more, lm2, f2, e2 = parse_sitemaps([f"{scheme}://{host}/sitemap_index.xml",
                                            f"{scheme}://{host}/wp-sitemap.xml"], args.timeout)
        sm_urls, sm_files, sm_errors = more, sm_files + f2, sm_errors + e2
        lastmods.update(lm2)
    sitemap_set = set(sm_urls)

    def internal(u):
        p = urlparse(u)
        return p.netloc == host and p.scheme == scheme

    def variant(u):
        p = urlparse(u)
        h = p.netloc
        return (h in (bare, "www." + bare) and h != host) or (h == host and p.scheme != scheme)

    def crawlable(u):
        p = urlparse(u)
        return not (SKIP_EXT.search(p.path) or SKIP_PATH.search(p.path) or SKIP_QUERY.search(p.query))

    pages = {}
    blocked = []
    inlinks = defaultdict(set)
    anchors = defaultdict(Counter)
    nofollow_internal = Counter()
    variant_links = defaultdict(set)
    utm_links = defaultdict(set)
    seen = {start: 0}
    queue = deque([start])
    phase2 = False
    t0 = time.time()

    while len(pages) < args.max_pages:
        if not queue:
            if phase2:
                break
            phase2 = True
            for u in sm_urls:  # y compris variantes http/www : on veut voir leur redirection
                if u not in seen and (internal(u) or variant(u)):
                    seen[u] = None
                    queue.append(u)
            if not queue:
                break
            continue
        url = queue.popleft()
        if not args.ignore_robots and not robots.allowed("Googlebot", url):
            blocked.append(url)
            continue
        res = fetch(url, timeout=args.timeout)
        page, parser = analyze_page(url, res)
        page["depth"] = seen.get(url)
        page["in_sitemap"] = url in sitemap_set
        page["sitemap_lastmod"] = lastmods.get(url)
        pages[url] = page
        fin = page["final_url"]
        if fin and fin != url and internal(fin) and fin not in seen and crawlable(fin):
            seen[fin] = seen.get(url)
            queue.append(fin)
        if parser is not None:
            base = res["final_url"]
            outs = set()
            for link in parser.links:
                href = link["href"]
                if not href or href.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
                    continue
                target = normalize(urljoin(base, href))
                if not target:
                    continue
                if variant(target):
                    variant_links[target].add(url)
                    continue
                if not internal(target):
                    continue
                if re.search(r"(^|&)utm_", urlparse(target).query, re.I):
                    utm_links[target].add(url)
                    continue
                outs.add(target)
                inlinks[target].add(url)
                if link["text"]:
                    anchors[target][link["text"].lower()[:80]] += 1
                if "nofollow" in link["rel"]:
                    nofollow_internal[target] += 1
                if target not in seen and crawlable(target):
                    d = seen.get(url)
                    seen[target] = (d + 1) if d is not None else None
                    queue.append(target)
            page["outlinks_internal"] = len(outs)
            page["external_links"] = sum(1 for l in parser.links
                                         if l["href"].startswith("http") and not internal(normalize(l["href"]) or ""))
        if len(pages) % 25 == 0:
            print(f"[crawl] {len(pages)} pages — {len(queue)} en file — {time.time() - t0:.0f}s", file=sys.stderr)
        time.sleep(args.delay)

    # --- statut des cibles de liens non visitées (limite atteinte) : on ne les invente pas
    for u, p in pages.items():
        p["inlinks"] = len(inlinks.get(u, ()))
        p["inlink_anchors"] = anchors[u].most_common(10)

    # --- cibles de canonical jamais crawlées (page non liée) : vérifier quand même leur statut (50 au plus)
    canon_targets = {}
    for p in list(pages.values()):
        c = (p.get("canonicals") or [None])[0]
        if (c and c != p["url"] and c not in pages and c not in canon_targets and (internal(c) or variant(c))
                and len(canon_targets) < 50):
            canon_targets[c], _ = analyze_page(c, fetch(c, timeout=args.timeout))
            time.sleep(args.delay)

    # --- images cassées (optionnel)
    broken_imgs = {}
    if args.check_images:
        uniq = []
        for p in pages.values():
            for src in p.get("img_srcs", []):
                s = normalize(urljoin(p["final_url"], src))
                if s and s not in uniq:
                    uniq.append(s)
        for s in uniq[:args.check_images]:
            r = fetch(s, timeout=args.timeout, method="HEAD")
            if r["status"] in (405, 501):
                r = fetch(s, timeout=args.timeout, max_bytes=1024)
            if r["status"] >= 400 or r["status"] <= 0:
                broken_imgs[s] = r["status"]
            time.sleep(args.delay / 2)

    issues = build_issues(pages, inlinks, sitemap_set, sm_urls, blocked, robots, variant_links,
                          nofollow_internal, broken_imgs, host, scheme, canon_targets)
    if relative_sitemaps:
        issues["robots_sitemap_relative"] = {"label": "Directive Sitemap relative dans robots.txt (Google exige une URL absolue)",
                                             "severity": "moyenne", "count": len(relative_sitemaps),
                                             "examples": relative_sitemaps}
    for tgt, srcs in utm_links.items():
        it = issues.setdefault("utm_internal", {"label": "Liens internes avec paramètres UTM (faussent l'analytics, dupliquent les URL)",
                                                "severity": "basse", "count": 0, "examples": []})
        it["count"] += 1
        if len(it["examples"]) < 25:
            it["examples"].append({"lien": tgt, "depuis": sorted(srcs)[:3]})

    meta = {
        "start_url": start, "host": host, "pages_crawled": len(pages), "max_pages": args.max_pages,
        "limit_reached": len(pages) >= args.max_pages, "duration_s": round(time.time() - t0, 1),
        "robots_txt_status": robots_res["status"], "robots_txt": robots.raw[:5000],
        "robots_other_directives": robots.other_lines[:50],
        "sitemap_files": sm_files, "sitemap_errors": sm_errors, "sitemap_url_count": len(sitemap_set),
        "blocked_by_robots": blocked[:500], "broken_images": broken_imgs,
        "canonical_targets_checked": {u: c["final_status"] for u, c in canon_targets.items()},
        "astra_detected": any(p.get("astra") for p in pages.values()),
        "astro_detected": any(p.get("astro") for p in pages.values()),
    }
    with open(out / "pages.json", "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "pages": list(pages.values())}, f, ensure_ascii=False, indent=1)
    with open(out / "issues.json", "w", encoding="utf-8") as f:
        json.dump(issues, f, ensure_ascii=False, indent=1)
    write_csv(out / "pages.csv", pages.values())
    write_summary(out / "summary.md", meta, pages, issues)
    print(f"[ok] {len(pages)} pages — résultats dans {out}", file=sys.stderr)


# --------------------------------------------------------------------------- problèmes

def build_issues(pages, inlinks, sitemap_set, sm_urls, blocked, robots, variant_links, nofollow_internal,
                 broken_imgs, host, scheme, canon_targets=None):
    issues = {}
    canon_targets = canon_targets or {}

    def add(key, label, sev, example=None, n=1):
        it = issues.setdefault(key, {"label": label, "severity": sev, "count": 0, "examples": []})
        it["count"] += n
        if example is not None and len(it["examples"]) < 25:
            it["examples"].append(example)

    html_ok = [p for p in pages.values() if p.get("is_html") and p["final_status"] == 200 and not p["redirect_hops"]]
    sitemap_eff = set()
    for u in sitemap_set:
        sp = pages.get(u)
        sitemap_eff.add(sp["final_url"] if sp and sp["redirect_hops"] else u)
    indexable = []
    for p in html_ok:
        canon = p.get("canonicals") or []
        p["indexable"] = not p.get("noindex") and (not canon or canon[0] == p["url"])
        if p["indexable"]:
            indexable.append(p)

    for p in pages.values():
        u = p["url"]
        st, fst = p["status"], p["final_status"]
        srcs = sorted(inlinks.get(u, ()))[:3]
        if fst >= 500:
            add("http_5xx", "Pages en erreur serveur (5xx)", "critique", {"url": u, "status": fst, "liens_depuis": srcs})
        elif 400 <= fst < 500:
            add("http_4xx", "Pages en erreur 4xx (liens internes cassés si liées)", "haute",
                {"url": u, "status": fst, "liens_depuis": srcs})
        elif fst <= 0:
            add("fetch_error", "Pages injoignables (timeout, TLS, DNS)", "haute", {"url": u, "erreur": p["error"]})
        if p["redirect_hops"] >= 1 and inlinks.get(u):
            add("link_to_redirect", "Liens internes pointant vers une redirection", "moyenne",
                {"url": u, "vers": p["final_url"], "hops": p["redirect_hops"], "liens_depuis": srcs})
        if p["redirect_hops"] > 1:
            add("redirect_chain", "Chaînes de redirections (>1 saut)", "moyenne",
                {"url": u, "chaine": [c["status"] for c in p["redirect_chain"]], "final": p["final_url"]})
        if st in (302, 303, 307) and p["redirect_hops"]:
            add("redirect_temp", "Redirections temporaires (302/307) à passer en 301 si définitives", "basse",
                {"url": u, "status": st, "vers": p["final_url"]})
        if p.get("ttfb") and p["ttfb"] > 1.0 and fst == 200:
            add("slow_ttfb", "Temps de réponse serveur > 1 s (TTFB mesuré depuis le crawler)", "moyenne",
                {"url": u, "ttfb_s": p["ttfb"]})

    titles, descs = defaultdict(list), defaultdict(list)
    for p in html_ok:
        u = p["url"]
        t, d = p.get("title", ""), p.get("meta_description", "")
        if p.get("indexable"):
            if not t:
                add("title_missing", "Balise <title> absente ou vide", "haute", u)
            else:
                titles[t.strip().lower()].append(u)
                if len(t) > 65:
                    add("title_long", "Title > 65 caractères (tronqué dans Google)", "basse", {"url": u, "len": len(t)})
                if len(t) < 25:
                    add("title_short", "Title < 25 caractères (peu descriptif)", "basse", {"url": u, "title": t})
            if not d:
                add("desc_missing", "Meta description absente", "moyenne", u)
            else:
                descs[d.strip().lower()].append(u)
                if len(d) > 160:
                    add("desc_long", "Meta description > 160 caractères", "basse", {"url": u, "len": len(d)})
                if len(d) < 70:
                    add("desc_short", "Meta description < 70 caractères", "basse", {"url": u, "len": len(d)})
            nh1 = len(p.get("h1", []))
            if nh1 == 0:
                add("h1_missing", "Aucun H1 (fréquent avec Astra « Désactiver le titre » + page builder)", "haute", u)
            elif nh1 > 1:
                add("h1_multiple", "Plusieurs H1 sur la page", "basse", {"url": u, "h1": p["h1"][:4]})
            if p.get("content_words", 0) < 300:
                add("thin_content", "Contenu court (< 300 mots dans la zone principale)", "moyenne",
                    {"url": u, "mots": p.get("content_words")})
            if p.get("depth") is not None and p["depth"] > 3:
                add("deep_page", "Pages à plus de 3 clics de l'accueil", "moyenne", {"url": u, "profondeur": p["depth"]})
            if not p.get("jsonld_types"):
                add("no_jsonld", "Aucune donnée structurée JSON-LD", "basse", u)
            if not (p.get("og_title") and p.get("og_image")):
                add("og_missing", "Open Graph incomplet (og:title / og:image)", "basse", u)
            if sm_urls and p["url"] not in sitemap_eff:
                add("not_in_sitemap", "Pages indexables absentes du sitemap", "moyenne", u)
        canon = p.get("canonicals") or []
        if not canon:
            add("canonical_missing", "Balise canonical absente", "moyenne", p["url"])
        elif len(set(canon)) > 1:
            add("canonical_multiple", "Plusieurs canonicals différentes (conflit Astra/plugin SEO ?)", "haute",
                {"url": p["url"], "canonicals": canon})
        elif canon[0] != p["url"]:
            add("canonical_other", "Canonical vers une autre URL (vérifier que c'est voulu)", "basse",
                {"url": p["url"], "canonical": canon[0]})
            tgt = pages.get(canon[0]) or canon_targets.get(canon[0])
            if tgt and (tgt["final_status"] != 200 or tgt["redirect_hops"] or tgt.get("noindex")):
                add("canonical_bad_target", "Canonical vers une URL en erreur, redirigée ou noindex", "haute",
                    {"url": p["url"], "canonical": canon[0], "statut_cible": tgt["final_status"]})
        if p.get("noindex"):
            add("noindex", "Pages en noindex (vérifier que c'est voulu)", "info", p["url"])
        if p.get("imgs_no_alt"):
            add("img_no_alt", "Images sans attribut alt", "moyenne", {"url": p["url"], "n": p["imgs_no_alt"]},
                n=p["imgs_no_alt"])
        if p.get("form_fields_no_label"):
            add("form_no_label", "Champs de formulaire sans libellé (placeholder seul ou rien) — WCAG 1.3.1 / 3.3.2",
                "moyenne", {"url": p["url"], "n": p["form_fields_no_label"]}, n=p["form_fields_no_label"])
        if p.get("imgs_no_dims"):
            add("img_no_dims", "Images sans width/height (risque de CLS)", "basse",
                {"url": p["url"], "n": p["imgs_no_dims"]}, n=p["imgs_no_dims"])
        if p.get("imgs_lazy_first"):
            add("lazy_first_img", "Première image en loading=lazy (souvent l'image LCP — à charger tout de suite)",
                "moyenne", p["url"])
        if not p.get("lang"):
            add("lang_missing", "Attribut lang absent sur <html>", "moyenne", p["url"])
        if not p.get("viewport"):
            add("viewport_missing", "Meta viewport absente (mobile)", "haute", p["url"])
        if p.get("mixed_content"):
            add("mixed_content", "Contenu mixte (ressources http:// sur page https)", "haute",
                {"url": p["url"], "ressources": p["mixed_content"][:5]})
        if p.get("jsonld_errors"):
            add("jsonld_invalid", "Bloc JSON-LD invalide (JSON non parsable)", "moyenne", p["url"])
        if p.get("bytes_html", 0) > 300_000:
            add("heavy_html", "HTML > 300 Ko (DOM lourd, CSS inline excessif ?)", "basse",
                {"url": p["url"], "ko": p["bytes_html"] // 1024})
        if p.get("hreflang") and not any(normalize(h) == p["url"] for _, h in p["hreflang"]):
            add("hreflang_no_self", "hreflang sans auto-référence", "basse", p["url"])
        path = urlparse(p["url"]).path
        if re.search(r"[A-Z]", path) or "_" in path or len(p["url"]) > 115:
            add("url_hygiene", "URL peu propres (majuscules, underscores, > 115 caractères)", "basse", p["url"])
        if urlparse(p["url"]).query and p.get("indexable"):
            add("param_indexable", "URL avec paramètres indexables (risque de duplication)", "moyenne", p["url"])

    for t, us in titles.items():
        if len(us) > 1:
            add("title_dup", "Titles dupliqués", "moyenne", {"title": t[:90], "urls": us[:6], "n": len(us)}, n=len(us))
    for d, us in descs.items():
        if len(us) > 1:
            add("desc_dup", "Meta descriptions dupliquées", "moyenne", {"desc": d[:90], "urls": us[:6]}, n=len(us))

    # Cannibalisation potentielle : titles très proches (hors mots de marque récurrents)
    idx = indexable[:2000]
    tok = {p["url"]: tokenize(p.get("title", "") + " " + " ".join(p.get("h1", []))) for p in idx}
    freq = Counter(t for s in tok.values() for t in s)
    brand = {t for t, c in freq.items() if len(idx) > 4 and c > 0.5 * len(idx)}
    urls = [u for u in tok if len(tok[u] - brand) >= 2]
    for i in range(len(urls)):
        a = tok[urls[i]] - brand
        for j in range(i + 1, len(urls)):
            b = tok[urls[j]] - brand
            inter = len(a & b)
            if inter and inter / len(a | b) >= 0.7:
                add("near_dup_titles", "Titles/H1 quasi identiques (cannibalisation possible)", "moyenne",
                    {"a": urls[i], "b": urls[j], "mots_communs": sorted(a & b)[:8]})

    if not sitemap_set:
        add("no_sitemap", "Aucun sitemap XML trouvé (robots.txt, /sitemap_index.xml, /wp-sitemap.xml)", "haute")
    for u in sitemap_set:
        p = pages.get(u)
        if not p:
            continue
        cible = p
        if p["redirect_hops"]:
            add("sitemap_redirect", "URL du sitemap qui redirigent (souvent http:// ou slash final incohérent)", "moyenne",
                {"url": u, "vers": p["final_url"]})
            cible = pages.get(p["final_url"]) or p
        # une redirection ne masque plus l'état de la cible : 404 et noindex restent signalés
        if cible["final_status"] != 200:
            add("sitemap_non200", "URL du sitemap en erreur", "haute", {"url": u, "status": cible["final_status"]})
        elif cible.get("noindex"):
            add("sitemap_noindex", "URL du sitemap en noindex (signal contradictoire)", "haute", u)
        elif cible.get("canonicals") and cible["canonicals"][0] != cible["url"]:
            add("sitemap_canonicalized", "URL du sitemap canonisées ailleurs", "moyenne",
                {"url": u, "canonical": cible["canonicals"][0]})
    home_url = next(iter(pages), None)
    for u in sitemap_eff:
        p = pages.get(u)
        if p and not inlinks.get(u) and p.get("final_status") == 200 and not p["redirect_hops"] and u != home_url:
            add("orphan", "Pages orphelines (dans le sitemap, aucun lien interne trouvé)", "moyenne", u)
    for u in blocked:
        if u in sitemap_set:
            add("sitemap_blocked", "URL du sitemap bloquées par robots.txt", "haute", u)
        elif inlinks.get(u):
            add("linked_blocked", "Pages liées mais bloquées par robots.txt", "basse", u)
    if not robots.raw:
        add("robots_missing", "robots.txt absent ou inaccessible", "moyenne")
    elif not robots.allowed("Googlebot", f"{scheme}://{host}/"):
        add("robots_blocks_all", "robots.txt bloque tout le site pour Googlebot", "critique")
    for rule_allow, pat in robots.rules_for("Googlebot")[0]:
        if not rule_allow and ASSETS_RX.search(pat):
            add("robots_blocks_assets", "robots.txt bloque CSS/JS (empêche le rendu par Google)", "haute", pat)
    for tgt, srcs in variant_links.items():
        add("variant_links", "Liens internes vers une autre variante d'hôte (http / www)", "moyenne",
            {"lien": tgt, "depuis": sorted(srcs)[:3]})
    for tgt, n in nofollow_internal.items():
        add("nofollow_internal", "Liens internes en nofollow", "basse", {"url": tgt, "n": n}, n=n)
    for src, st in broken_imgs.items():
        add("broken_images", "Images cassées", "moyenne", {"src": src, "status": st})
    return issues


def write_csv(path, pages):
    cols = ["url", "status", "final_status", "final_url", "redirect_hops", "ttfb", "time", "bytes_html",
            "indexable", "noindex", "canonical", "title", "title_len", "meta_description_len", "h1_count", "h1",
            "content_words", "words", "inlinks", "outlinks_internal", "depth", "in_sitemap", "imgs", "imgs_no_alt",
            "jsonld_types", "lang"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for p in pages:
            w.writerow([p.get("url"), p.get("status"), p.get("final_status"), p.get("final_url"),
                        p.get("redirect_hops"), p.get("ttfb"), p.get("time"), p.get("bytes_html"),
                        p.get("indexable"), p.get("noindex"), (p.get("canonicals") or [""])[0], p.get("title", ""),
                        len(p.get("title", "") or ""), len(p.get("meta_description", "") or ""),
                        len(p.get("h1", []) or []), " | ".join(p.get("h1", []) or []), p.get("content_words"),
                        p.get("words"), p.get("inlinks"), p.get("outlinks_internal"), p.get("depth"),
                        p.get("in_sitemap"), p.get("imgs"), p.get("imgs_no_alt"),
                        ",".join(p.get("jsonld_types", []) or []), p.get("lang")])


def write_summary(path, meta, pages, issues):
    order = {"critique": 0, "haute": 1, "moyenne": 2, "basse": 3, "info": 4}
    st = Counter(p["final_status"] if not p["redirect_hops"] else p["status"] for p in pages.values())
    depth = Counter(p.get("depth") for p in pages.values() if p.get("final_status") == 200)
    ttfbs = sorted(p["ttfb"] for p in pages.values() if p.get("ttfb"))
    lines = [f"# Crawl — {meta['start_url']}", "",
             f"- Pages analysées : **{meta['pages_crawled']}**" + (" (limite atteinte — relancer avec --max-pages plus grand)"
                                                                   if meta["limit_reached"] else ""),
             f"- Durée : {meta['duration_s']} s",
             f"- Framework : {'Astro' if meta['astro_detected'] else ('WordPress/Astra' if meta['astra_detected'] else 'non identifié')}",
             f"- robots.txt : HTTP {meta['robots_txt_status']}",
             f"- Sitemaps lus : {len(meta['sitemap_files'])} — {meta['sitemap_url_count']} URL"
             + (f" — erreurs : {'; '.join(meta['sitemap_errors'][:5])}" if meta["sitemap_errors"] else ""),
             f"- Bloquées par robots.txt : {len(meta['blocked_by_robots'])}",
             f"- Statuts : " + ", ".join(f"{k}×{v}" for k, v in sorted(st.items(), key=lambda x: str(x[0]))),
             f"- Profondeur de clic : " + ", ".join(f"{k if k is not None else 'hors liens'}→{v}"
                                                   for k, v in sorted(depth.items(), key=lambda x: (x[0] is None, x[0] or 0))),
             ]
    if ttfbs:
        lines.append(f"- TTFB crawler : médiane {ttfbs[len(ttfbs) // 2]} s, max {ttfbs[-1]} s")
    lines += ["", "## Problèmes détectés", "", "| Sévérité | Problème | Nb |", "|---|---|---|"]
    for k, it in sorted(issues.items(), key=lambda x: (order.get(x[1]["severity"], 9), -x[1]["count"])):
        lines.append(f"| {it['severity']} | {it['label']} (`{k}`) | {it['count']} |")
    lines += ["", "Détails et exemples : `issues.json`. Données par page : `pages.json` / `pages.csv`.", ""]
    ranked = sorted((p for p in pages.values() if p.get("indexable")), key=lambda p: -p.get("inlinks", 0))
    lines += ["## Pages les plus liées", ""] + [f"- {p['inlinks']} ← {p['url']}" for p in ranked[:10]]
    lines += ["", "## Pages indexables les moins liées", ""] + [f"- {p['inlinks']} ← {p['url']}" for p in ranked[-10:]]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Crawler SEO technique (stdlib)")
    ap.add_argument("url")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-pages", type=int, default=500)
    ap.add_argument("--delay", type=float, default=0.3, help="pause entre requêtes (s) — rester poli avec le serveur")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--ignore-robots", action="store_true", help="crawler aussi les URL bloquées par robots.txt")
    ap.add_argument("--check-images", type=int, default=0, help="vérifier le statut de N images uniques")
    crawl(ap.parse_args())


if __name__ == "__main__":
    main()
