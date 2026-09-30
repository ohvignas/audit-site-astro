#!/usr/bin/env python3
"""
astro_scan.py — Analyse statique d'un projet Astro (+ Convex si présent). Lecture seule.

Usage :
  python3 astro_scan.py CHEMIN_DU_PROJET --out AUDIT_DIR/data/code [--dist dist]

Repère, avec fichier:ligne :
  - config Astro : site (http ?), output, adapter, trailingSlash, image.remotePatterns, sourcemap…
  - îlots : client:load / idle / visible / only (hydratation trop agressive = JS inutile)
  - images : <img> brut au lieu de <Image>/<Picture>, alt manquant, dimensions manquantes
  - SEO dans les layouts : title, description, canonical (Astro.url.href = piège derrière proxy), og, JSON-LD, lang
  - routes SSR dynamiques sans gestion du 404 (soft 404), 404.astro, sitemap (endpoint custom en http ?),
    robots.txt (Sitemap relatif), llms.txt
  - sécurité : set:html / dangerouslySetInnerHTML, variables d'env non PUBLIC_ dans du code client
  - tiers : Google Fonts, GTM, pixels, chat
  - Convex : fonctions publiques sans vérification d'auth, sans validateur d'args, .filter() sans index,
    .collect() non borné, v.any(), URLs de storage servies brutes en <img>
  - bundle : plus gros fichiers JS/CSS du build (si dist/ présent), tailles gzip

Sorties : code-scan.json, code-scan.md
"""
import argparse
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

EXCLUDE_DIRS = {"node_modules", ".git", "dist", ".astro", ".vercel", ".netlify", ".output", "_generated", ".turbo",
                ".cache", "coverage", ".next"}
SRC_EXT = {".astro", ".tsx", ".jsx", ".ts", ".js", ".mjs", ".svelte", ".vue", ".mdx", ".md"}
CLIENT_EXT = {".tsx", ".jsx", ".svelte", ".vue"}

findings = []


def add(sev, cat, msg, where=None, fix=None):
    findings.append({"severite": sev, "categorie": cat, "constat": msg, "ou": where or [], "piste": fix or ""})


def rel(p, root):
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def iter_files(root, exts):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in exts and not (set(p.relative_to(root).parts) & EXCLUDE_DIRS):
            yield p


def read(p):
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def lines_matching(text, rx, limit=50):
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        if rx.search(line):
            out.append((i, line.strip()[:160]))
            if len(out) >= limit:
                break
    return out


# --------------------------------------------------------------------------- package.json / config

def scan_package(root, report):
    pj = root / "package.json"
    if not pj.exists():
        add("haute", "projet", "package.json introuvable — est-ce bien la racine du projet Astro ?")
        return {}
    data = json.loads(read(pj) or "{}")
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    report["package"] = {
        "astro": deps.get("astro"), "convex": deps.get("convex"),
        "adapters": [d for d in deps if d.startswith("@astrojs/") and d.split("/")[1] in
                     ("node", "vercel", "netlify", "cloudflare", "deno")],
        "integrations": sorted(d for d in deps if d.startswith("@astrojs/")),
        "frameworks_ui": [d for d in ("react", "preact", "svelte", "vue", "solid-js", "@builder.io/qwik") if d in deps],
        "scripts": data.get("scripts", {}),
        "engines": data.get("engines", {}),
        "nb_dependances": len(deps),
    }
    lock = [f for f in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock") if (root / f).exists()]
    report["package"]["lockfile"] = lock
    if not lock:
        add("moyenne", "projet", "Aucun lockfile : builds non reproductibles", fix="commiter le lockfile du gestionnaire utilisé")
    heavy = [d for d in deps if d in ("moment", "lodash", "jquery", "@fortawesome/fontawesome-free", "gsap", "three",
                                        "chart.js", "framer-motion", "swiper", "aos")]
    if heavy:
        add("basse", "performance", f"Dépendances lourdes à vérifier côté client : {', '.join(heavy)}",
            fix="n'importer que le nécessaire, charger à la demande (import() dynamique) ou remplacer")
    return deps


def scan_astro_config(root, report):
    cfg = next((root / f for f in ("astro.config.mjs", "astro.config.ts", "astro.config.js", "astro.config.mts")
                if (root / f).exists()), None)
    if not cfg:
        add("haute", "config", "astro.config.* introuvable")
        return {}
    t = read(cfg)
    name = rel(cfg, root)

    def val(key):
        m = re.search(rf"\b{key}\s*:\s*([^,\n}}]+)", t)
        return m.group(1).strip() if m else None

    conf = {"fichier": name, "site": val("site"), "output": val("output"), "trailingSlash": val("trailingSlash"),
            "base": val("base"), "compressHTML": val("compressHTML"), "prefetch": val("prefetch"),
            "sourcemap": val("sourcemap"), "adapter": bool(re.search(r"adapter\s*:", t)),
            "sitemap_integration": "sitemap(" in t, "remotePatterns": "remotePatterns" in t or "domains" in t,
            "i18n": "i18n" in t, "redirects": "redirects" in t, "checkOrigin": val("checkOrigin"),
            "fonts_api": bool(re.search(r"\bfonts\s*:", t)), "security_csp": bool(re.search(r"\bcsp\s*:", t))}
    report["astro_config"] = conf
    site = conf["site"] or ""
    if not site:
        add("haute", "seo", f"`site` non défini dans {name} : sitemap, canonical et URL absolues risquent d'être fausses",
            [name], "définir site: 'https://domaine.fr'")
    elif "http://" in site:
        add("haute", "seo", f"`site` en http:// dans {name} ({site}) : sitemap/canonical générés en http", [name],
            "passer en https://")
    elif "import.meta.env" in site or "process.env" in site:
        add("info", "seo", f"`site` dépend d'une variable d'environnement ({site}) : vérifier sa valeur en production "
                           f"(https, bon domaine)", [name])
    if conf["sourcemap"] and "true" in conf["sourcemap"]:
        add("basse", "securite", "Source maps activées en build : code source lisible en production", [name],
            "vite.build.sourcemap: false (ou 'hidden' + upload vers l'outil d'erreurs)")
    if conf["trailingSlash"] is None:
        add("basse", "seo", "trailingSlash non fixé : risque de doublons /page et /page/ selon l'hébergeur", [name],
            "trailingSlash: 'never' ou 'always', cohérent avec sitemap, canonical et redirections")
    if conf["compressHTML"] and "false" in conf["compressHTML"]:
        add("basse", "performance", "compressHTML désactivé", [name])
    if conf["prefetch"] is None:
        add("info", "performance", "prefetch non configuré : la navigation interne peut être accélérée", [name],
            "prefetch: { prefetchAll: false, defaultStrategy: 'hover' } + data-astro-prefetch sur les liens clés")
    if conf["checkOrigin"] and "false" in conf["checkOrigin"]:
        add("moyenne", "securite", "security.checkOrigin désactivé (protection CSRF des formulaires/actions)", [name])
    return conf


# --------------------------------------------------------------------------- src/

RX = {
    "client": re.compile(r"\bclient:(load|idle|visible|only|media)\b"),
    "img_tag": re.compile(r"<img\b", re.I),
    "image_comp": re.compile(r"<(Image|Picture)\b"),
    "set_html": re.compile(r"set:html\s*=|dangerouslySetInnerHTML"),
    "env_private": re.compile(r"import\.meta\.env\.(?!PUBLIC_|MODE|DEV|PROD|SSR|BASE_URL|SITE)([A-Z0-9_]+)"),
    "process_env": re.compile(r"process\.env\.([A-Z0-9_]+)"),
    "gfonts": re.compile(r"fonts\.(googleapis|gstatic)\.com"),
    "third": re.compile(r"googletagmanager|google-analytics|gtag\(|connect\.facebook|fbq\(|hotjar|clarity\.ms|"
                        r"intercom|crisp\.chat|tawk\.to|hs-scripts|linkedin\.com/insight|tiktok|calendly|"
                        r"youtube\.com/embed|player\.vimeo", re.I),
    "is_inline": re.compile(r"<script[^>]*is:inline"),
    "storage_url": re.compile(r"storage\.getUrl|/api/storage/|convex\.cloud/api/storage|getUrl\("),
    "astro_url_href": re.compile(r"Astro\.url\.href|Astro\.request\.url|url\.origin|request\.url"),
}


def img_issues(text):
    """<img> sans alt / sans width+height (multi-lignes)."""
    no_alt, no_dims = [], []
    for m in re.finditer(r"<img\b[^>]*?>", text, re.I | re.S):
        tag = m.group(0)
        line = text.count("\n", 0, m.start()) + 1
        if not re.search(r"\balt\s*=", tag):
            no_alt.append(line)
        if not (re.search(r"\bwidth\s*=", tag) and re.search(r"\bheight\s*=", tag)):
            no_dims.append(line)
    return no_alt, no_dims


def scan_src(root, report):
    src = root / "src"
    if not src.exists():
        add("haute", "projet", "Dossier src/ introuvable")
        return
    hyd = Counter()
    hyd_where = defaultdict(list)
    raw_imgs, img_no_alt, img_no_dims, image_comp = [], [], [], 0
    set_html, env_client, third, gfonts, inline_scripts, storage_imgs = [], [], [], [], [], []
    for f in iter_files(src, SRC_EXT):
        t = read(f)
        r = rel(f, root)
        for i, line in lines_matching(t, RX["client"], 200):
            for d in RX["client"].findall(line):
                hyd[d] += 1
                comp = re.search(r"<([A-Z][\w.]*)", line)
                hyd_where[d].append(f"{r}:{i} {comp.group(1) if comp else ''}".strip())
        if f.suffix in (".astro", ".tsx", ".jsx", ".svelte", ".vue", ".mdx"):
            imgs = lines_matching(t, RX["img_tag"])
            raw_imgs += [f"{r}:{i}" for i, _ in imgs]
            na, nd = img_issues(t)
            img_no_alt += [f"{r}:{i}" for i in na]
            img_no_dims += [f"{r}:{i}" for i in nd]
            image_comp += len(RX["image_comp"].findall(t))
            if RX["storage_url"].search(t) and imgs:
                storage_imgs.append(r)
        set_html += [f"{r}:{i} {l}" for i, l in lines_matching(t, RX["set_html"])]
        if f.suffix in CLIENT_EXT or ("<script" in t and f.suffix == ".astro"):
            # dans un .astro, seul le contenu des <script> part au navigateur
            scope = t if f.suffix in CLIENT_EXT else "\n".join(re.findall(r"<script\b[^>]*>(.*?)</script>", t, re.S))
            for m in RX["env_private"].finditer(scope):
                env_client.append(f"{r} : import.meta.env.{m.group(1)}")
            for m in RX["process_env"].finditer(scope):
                env_client.append(f"{r} : process.env.{m.group(1)}")
        third += [f"{r}:{i} {RX['third'].search(l).group(0)}" for i, l in lines_matching(t, RX["third"])]
        gfonts += [f"{r}:{i}" for i, _ in lines_matching(t, RX["gfonts"])]
        inline_scripts += [f"{r}:{i}" for i, _ in lines_matching(t, RX["is_inline"])]

    report["hydratation"] = {"compte": dict(hyd), "ou": {k: v[:40] for k, v in hyd_where.items()}}
    report["images"] = {"img_brut": len(raw_imgs), "Image_Picture": image_comp, "sans_alt": img_no_alt[:60],
                        "sans_dimensions": len(img_no_dims)}
    if hyd["load"]:
        add("moyenne", "performance",
            f"{hyd['load']} îlot(s) en client:load (hydratés immédiatement, bloquent l'interactivité)",
            hyd_where["load"][:20],
            "client:idle pour ce qui n'est pas critique, client:visible pour ce qui est sous la ligne de flottaison "
            "(chat, avis, carrousels, formulaires en bas de page), ou un composant .astro sans JS si aucune interaction")
    if hyd["only"]:
        add("basse", "seo", f"{hyd['only']} composant(s) client:only : rien n'est rendu côté serveur (contenu invisible "
                            f"pour les robots sans JS)", hyd_where["only"][:20])
    if raw_imgs:
        add("moyenne", "performance", f"{len(raw_imgs)} balise(s) <img> brute(s) vs {image_comp} <Image>/<Picture> : pas "
                                      f"de redimensionnement, ni AVIF/WebP, ni srcset automatiques", raw_imgs[:25],
            "utiliser <Image>/<Picture> d'astro:assets (images locales dans src/assets ou distantes autorisées via "
            "image.remotePatterns)")
    if storage_imgs:
        add("haute", "performance", "Images servies directement depuis le storage Convex (fichier original, non "
                                    "redimensionné) dans des <img>", storage_imgs[:15],
            "déclarer le domaine Convex dans image.remotePatterns et passer par <Image> (ou getImage()), "
            "ou générer des variantes redimensionnées à l'upload")
    if img_no_alt:
        add("moyenne", "accessibilite", f"{len(img_no_alt)} <img> sans attribut alt", img_no_alt[:25],
            "alt descriptif, ou alt=\"\" si l'image est décorative")
    if img_no_dims:
        add("basse", "performance", f"{len(img_no_dims)} <img> sans width/height (CLS)", img_no_dims[:15])
    if set_html:
        add("moyenne", "securite", f"{len(set_html)} usage(s) de set:html / dangerouslySetInnerHTML — XSS si le "
                                   f"contenu vient d'un utilisateur ou du CMS sans assainissement", set_html[:20],
            "assainir (sanitize-html / DOMPurify côté serveur) ou rendre en Markdown maîtrisé")
    if env_client:
        add("haute", "securite", "Variables d'environnement non PUBLIC_ référencées dans du code client "
                                 "(fuite de secret possible ou valeur undefined)", env_client[:20],
            "ne jamais utiliser de secret côté client ; passer par un endpoint/action serveur")
    if gfonts:
        add("moyenne", "performance", "Google Fonts chargées depuis Google (requêtes tierces, RGPD)", gfonts[:10],
            "auto-héberger (@fontsource ou API fonts d'Astro), woff2, font-display: swap, précharger 1-2 fichiers max")
    if third:
        add("info", "performance", f"{len(third)} script(s)/embed(s) tiers repérés", third[:20],
            "charger après consentement et/ou à l'interaction (façade YouTube/Vimeo), Partytown pour les tags analytics")

    # --- SEO dans les layouts / head
    heads = [f for f in iter_files(src, {".astro"}) if re.search(r"<head\b", read(f))]
    head_report = {}
    for f in heads:
        t = read(f)
        head_report[rel(f, root)] = {
            "title": bool(re.search(r"<title\b", t)),
            "description": bool(re.search(r"name=[\"']description", t)),
            "canonical": bool(re.search(r"rel=[\"']canonical", t)),
            "og": "og:title" in t or "og:image" in t,
            "jsonld": "ld+json" in t,
            "lang": bool(re.search(r"<html[^>]*\blang=", t)),
            "viewport": "viewport" in t,
            "canonical_depuis_Astro_url_href": bool(re.search(r"canonical[^\n]*(Astro\.url\.href|Astro\.request\.url)", t)
                                                    or re.search(r"(canonical\w*|canonicalURL)\s*=\s*[^\n]*Astro\.url\.href", t)),
            "robots_meta": "name=\"robots\"" in t or "name='robots'" in t,
        }
    report["layouts"] = head_report
    for name, h in head_report.items():
        miss = [k for k in ("title", "description", "canonical", "og", "lang", "viewport") if not h[k]]
        if miss:
            add("moyenne", "seo", f"Layout {name} : balises absentes du <head> : {', '.join(miss)}", [name],
                "vérifier qu'elles ne viennent pas d'un composant SEO importé ; sinon les ajouter")
        if h["canonical_depuis_Astro_url_href"]:
            add("haute", "seo", f"{name} : canonical construite depuis Astro.url.href / request.url — derrière un "
                                f"proxy elle peut sortir en http:// et garde les paramètres de requête", [name],
                "canonical = new URL(Astro.url.pathname, Astro.site).href")

    # --- routes
    pages = src / "pages"
    report["routes"] = {}
    if pages.exists():
        if not any((pages / n).exists() for n in ("404.astro", "404.md", "404.mdx")):
            add("moyenne", "seo", "Pas de src/pages/404.astro : page d'erreur par défaut, peu utile", fix="créer une 404 "
                "avec recherche/liens clés, renvoyant bien le statut 404")
        dyn = [f for f in iter_files(pages, {".astro", ".ts", ".js"}) if "[" in f.name]
        risky = []
        for f in dyn:
            t = read(f)
            if "getStaticPaths" in t and "prerender = false" not in t:
                continue  # page statique : Astro renvoie 404 pour les chemins inconnus
            handles_404 = re.search(r"status\s*[:=]\s*404|Astro\.redirect\(\s*['\"]/404|rewrite\(\s*['\"]/404|"
                                    r"new Response\([^)]*404|notFound", t)
            if not handles_404 and f.suffix == ".astro":
                risky.append(rel(f, root))
        report["routes"]["dynamiques"] = [rel(f, root) for f in dyn]
        if risky:
            add("haute", "seo", "Routes SSR dynamiques sans gestion explicite du 404 : une URL inexistante peut "
                                "renvoyer 200 (soft 404, pages vides indexées)", risky,
                "si l'élément n'existe pas : return Astro.rewrite('/404') (ou Astro.response.status = 404)")
        srv = [rel(f, root) for f in iter_files(pages, {".astro"}) if "prerender = false" in read(f)]
        pre = [rel(f, root) for f in iter_files(pages, {".astro"}) if "prerender = true" in read(f)]
        report["routes"]["prerender_false"] = srv
        report["routes"]["prerender_true"] = pre
        eps = {}
        for f in iter_files(pages, {".ts", ".js"}):
            n = f.name.lower()
            if any(k in n for k in ("sitemap", "robots", "llms", "rss", "feed")):
                eps[rel(f, root)] = read(f)
        report["routes"]["endpoints_seo"] = list(eps)
        for name, t in eps.items():
            if "sitemap" in name:
                if re.search(r"url\.origin|request\.url|Astro\.url\.origin|new URL\(\s*request", t) and "site" not in t:
                    add("haute", "seo", f"{name} construit les URL depuis l'origine de la requête : derrière un proxy "
                                        f"elles sortent en http:// (constaté sur le sitemap en ligne ?)", [name],
                        "utiliser l'origine canonique : new URL(path, import.meta.env.SITE ?? 'https://domaine.fr')")
                if "http://" in t:
                    add("haute", "seo", f"{name} contient une URL http:// en dur", [name])
                if "lastmod" not in t:
                    add("basse", "seo", f"{name} sans <lastmod> (aide Google et Bing à recrawler le contenu modifié)", [name])
    # public/
    pub = root / "public"
    rob = pub / "robots.txt"
    has_robots_ep = any("robots" in n for n in report["routes"].get("endpoints_seo", []))
    if rob.exists():
        rt = read(rob)
        for i, l in enumerate(rt.splitlines(), 1):
            if l.lower().startswith("sitemap:") and not re.search(r"sitemap:\s*https?://", l, re.I):
                add("moyenne", "seo", f"public/robots.txt:{i} Sitemap relatif « {l.strip()} » (URL absolue exigée)",
                    [f"public/robots.txt:{i}"], "Sitemap: https://domaine.fr/sitemap.xml (ou générer robots.txt via "
                                                "un endpoint qui lit `site`)")
    elif not has_robots_ep:
        add("moyenne", "seo", "Aucun robots.txt (ni public/robots.txt ni endpoint)")
    if not (pub / "llms.txt").exists() and not any("llms" in n for n in report["routes"].get("endpoints_seo", [])):
        add("basse", "geo", "Pas de llms.txt (faible coût, effet non prouvé)")
    if not any((pub / n).exists() for n in ("favicon.ico", "favicon.svg", "favicon.png")):
        add("basse", "seo", "Pas de favicon dans public/ (affiché par Google dans les résultats)")

    mw = next((f for f in (src / "middleware.ts", src / "middleware.js", src / "middleware" / "index.ts") if f.exists()), None)
    report["middleware"] = rel(mw, root) if mw else None


# --------------------------------------------------------------------------- Convex

FN_RX = re.compile(r"export\s+const\s+(\w+)\s*=\s*(query|mutation|action|internalQuery|internalMutation|internalAction|"
                   r"httpAction)\s*\(", re.M)
AUTH_RX = re.compile(r"getUserIdentity|ctx\.auth|getAuthUserId|requireAuth|requireUser|requireAdmin|assertAdmin|"
                     r"checkAuth|ensureAdmin|isAdmin|authorize|withAuth|currentUser|getCurrentUser|viewer", re.I)


def scan_convex(root, report):
    cdir = root / "convex"
    if not cdir.exists():
        report["convex"] = None
        return
    rep = {"fonctions": Counter(), "tables": 0, "index": 0}
    schema = cdir / "schema.ts"
    if schema.exists():
        st = read(schema)
        rep["tables"] = len(re.findall(r"defineTable\(", st))
        rep["index"] = len(re.findall(r"\.index\(", st)) + len(re.findall(r"\.searchIndex\(", st))
    no_auth, no_args, filters, collects, anys = [], [], [], [], []
    for f in iter_files(cdir, {".ts", ".js"}):
        if "_generated" in f.parts:
            continue
        t = read(f)
        r = rel(f, root)
        matches = list(FN_RX.finditer(t))
        for k, m in enumerate(matches):
            name, kind = m.group(1), m.group(2)
            rep["fonctions"][kind] += 1
            body = t[m.start(): matches[k + 1].start() if k + 1 < len(matches) else len(t)]
            line = t.count("\n", 0, m.start()) + 1
            if kind in ("query", "mutation", "action"):
                if not re.search(r"\bargs\s*:", body[:1500]):
                    no_args.append(f"{r}:{line} {kind} {name}")
                if kind in ("mutation", "action") and not AUTH_RX.search(body):
                    no_auth.append(f"{r}:{line} {kind} {name}")
        for i, l in lines_matching(t, re.compile(r"\.filter\("), 200):
            ctx = "\n".join(t.splitlines()[max(0, i - 4): i])
            if "ctx.db.query" in ctx and "withIndex" not in ctx and "withSearchIndex" not in ctx:
                filters.append(f"{r}:{i}")
        for i, l in lines_matching(t, re.compile(r"\.collect\(\)"), 200):
            ctx = "\n".join(t.splitlines()[max(0, i - 4): i])
            if "withIndex" not in ctx and ".take(" not in ctx:
                collects.append(f"{r}:{i}")
        anys += [f"{r}:{i}" for i, _ in lines_matching(t, re.compile(r"v\.any\(\)"))]
    rep["fonctions"] = dict(rep["fonctions"])
    report["convex"] = rep
    if no_auth:
        add("haute", "securite", f"{len(no_auth)} mutation(s)/action(s) publique(s) sans vérification d'identité "
                                 f"visible — appelables par n'importe qui avec l'URL Convex", no_auth[:30],
            "vérifier chaque cas : ctx.auth.getUserIdentity() + contrôle de rôle, ou passer en internalMutation "
            "si seulement appelée par le serveur (faux positif possible si l'auth est dans un helper non reconnu)")
    if no_args:
        add("moyenne", "securite", f"{len(no_args)} fonction(s) publique(s) sans validateur args", no_args[:30],
            "toujours déclarer args: { … } avec v.* (validation d'entrée)")
    if filters:
        add("moyenne", "performance", f"{len(filters)} .filter() sur ctx.db.query sans withIndex (scan complet de la "
                                      f"table, lent quand elle grossit)", filters[:30],
            "ajouter un .index() dans schema.ts et utiliser .withIndex()")
    if collects:
        add("basse", "performance", f"{len(collects)} .collect() non bornés (tout charger en mémoire)", collects[:30],
            ".take(n), .paginate() ou .first() selon le besoin")
    if anys:
        add("basse", "securite", f"{len(anys)} validateur(s) v.any()", anys[:20])


# --------------------------------------------------------------------------- bundle

def scan_dist(root, dist, report):
    d = (root / dist) if dist else None
    if not d or not d.exists():
        for cand in ("dist/client/_astro", "dist/_astro"):
            if (root / cand).exists():
                d = root / cand
                break
        else:
            report["bundle"] = None
            return
    files = [f for f in d.rglob("*") if f.is_file() and f.suffix in (".js", ".css")]
    rows = []
    for f in files:
        raw = f.read_bytes()
        rows.append((len(raw), len(gzip.compress(raw, 6)), rel(f, root)))
    rows.sort(reverse=True)
    tot_js = sum(r[1] for r in rows if r[2].endswith(".js"))
    tot_css = sum(r[1] for r in rows if r[2].endswith(".css"))
    report["bundle"] = {"dossier": rel(d, root), "js_gzip_ko": tot_js // 1024, "css_gzip_ko": tot_css // 1024,
                        "plus_gros": [{"fichier": r[2], "ko": r[0] // 1024, "gzip_ko": r[1] // 1024} for r in rows[:15]]}
    big = [f"{r[2]} ({r[1] // 1024} Ko gzip)" for r in rows if r[1] > 100 * 1024 and r[2].endswith(".js")]
    if big:
        add("moyenne", "performance", "Chunks JS > 100 Ko gzip", big[:10],
            "identifier l'îlot qui l'importe (npx vite-bundle-visualizer ou rollup-plugin-visualizer), "
            "hydrater plus tard (client:visible/idle), import() dynamique, alléger les dépendances")


# --------------------------------------------------------------------------- git / secrets

def scan_repo(root, report):
    gi = read(root / ".gitignore") if (root / ".gitignore").exists() else ""
    if ".env" not in gi:
        add("haute", "securite", ".env absent du .gitignore", [".gitignore"])
    tracked = []
    if (root / ".git").exists():
        import subprocess
        try:
            out = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, timeout=30).stdout
            tracked = [l for l in out.splitlines() if re.search(r"(^|/)\.env(\.|$)", l) and not l.endswith(".example")]
        except Exception:
            pass
    if tracked:
        add("critique", "securite", "Fichiers .env versionnés dans git (secrets dans l'historique)", tracked,
            "retirer du suivi, RÉVOQUER/ROTER les clés, purger l'historique si le dépôt est partagé")


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dist", help="dossier des assets buildés (défaut : dist/client/_astro ou dist/_astro)")
    a = ap.parse_args()
    root = Path(a.project).resolve()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    report = {"projet": str(root)}
    scan_package(root, report)
    scan_astro_config(root, report)
    scan_src(root, report)
    scan_convex(root, report)
    scan_dist(root, a.dist, report)
    scan_repo(root, report)
    order = {"critique": 0, "haute": 1, "moyenne": 2, "basse": 3, "info": 4}
    findings.sort(key=lambda f: order.get(f["severite"], 9))
    report["constats"] = findings
    (out / "code-scan.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    pk = report.get("package", {}) or {}
    cf = report.get("astro_config", {}) or {}
    md = [f"# Scan du code Astro — {root.name}", "",
          f"- Astro {pk.get('astro')} — adapter : {', '.join(pk.get('adapters') or []) or 'aucun (statique)'} — "
          f"UI : {', '.join(pk.get('frameworks_ui') or []) or 'aucun'} — Convex : {pk.get('convex') or 'non'}",
          f"- Config ({cf.get('fichier')}) : site={cf.get('site')}, output={cf.get('output')}, "
          f"trailingSlash={cf.get('trailingSlash')}, intégration sitemap={cf.get('sitemap_integration')}, "
          f"remotePatterns={cf.get('remotePatterns')}",
          f"- Hydratation : {report.get('hydratation', {}).get('compte')}",
          f"- Images : {report.get('images')}".replace("'sans_alt': [", "'sans_alt': [liste dans le JSON] ["),
          f"- Middleware : {report.get('middleware')}",
          ]
    if report.get("convex"):
        md.append(f"- Convex : {report['convex']}")
    if report.get("bundle"):
        b = report["bundle"]
        md.append(f"- Bundle ({b['dossier']}) : JS {b['js_gzip_ko']} Ko gzip, CSS {b['css_gzip_ko']} Ko gzip")
        md += [f"  - {x['fichier']} : {x['ko']} Ko ({x['gzip_ko']} Ko gzip)" for x in b["plus_gros"][:8]]
    md += ["", "## Constats", ""]
    for f in findings:
        md.append(f"### [{f['severite']}] {f['categorie']} — {f['constat']}")
        if f["ou"]:
            md += [f"- `{w}`" for w in f["ou"][:12]] + ([f"- … et {len(f['ou']) - 12} autres"] if len(f["ou"]) > 12 else [])
        if f["piste"]:
            md.append(f"- **Piste** : {f['piste']}")
        md.append("")
    (out / "code-scan.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"[ok] {len(findings)} constats — {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
