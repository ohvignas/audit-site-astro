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


def sans_commentaires(t):
    """Retire les commentaires JS/TS (/* … */ et // …) en laissant intacts les littéraux '…', "…" et `…`
    (échappements compris) : un glob '/images/**' ou une URL 'https://…' ne sont pas des commentaires.
    Les retours à la ligne des commentaires sont conservés (numéros de ligne inchangés)."""
    out, i, n = [], 0, len(t)
    while i < n:
        c = t[i]
        if c in "'\"`":
            j = i + 1
            while j < n and t[j] != c:
                if t[j] == "\\":
                    j += 1
                elif c != "`" and t[j] == "\n":  # chaîne non fermée : on s'arrête à la ligne
                    break
                j += 1
            out.append(t[i:j + 1])
            i = j + 1
        elif t.startswith("//", i) and not (i and t[i - 1] == ":"):
            j = t.find("\n", i)
            i = n if j < 0 else j
        elif t.startswith("/*", i):
            j = t.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("\n" * t.count("\n", i, j))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


# Espaces de noms XML : des identifiants, pas des URL chargées (xmlns du sitemap…)
NAMESPACES_XML = re.compile(r"http://(www\.sitemaps\.org|www\.w3\.org|www\.google\.com/schemas|purl\.org)/")


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
    t = sans_commentaires(read(cfg))
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
    "jsonld_script": re.compile(r"type\s*=\s*[\"']application/ld\+json[\"']", re.I),
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
        # JSON-LD (<script type="application/ld+json" set:html={…}>) : pas du HTML interprété, pas un XSS
        set_html += [f"{r}:{i} {l}" for i, l in lines_matching(t, RX["set_html"]) if not RX["jsonld_script"].search(l)]
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
                code = sans_commentaires(t)
                par_requete = re.search(r"url\.origin|request\.url|Astro\.url\.origin|new URL\(\s*request", code)
                # l'identifiant `site` (Astro.site, context.site, ({ site })…), pas la sous-chaîne de « sitemaps.org »
                par_site = re.search(r"\bAstro\.site\b|\bcontext\.site\b|import\.meta\.env\.SITE\b|(?<![\w.$])site\b(?!\s*:)", code)
                if par_requete and not par_site:
                    add("haute", "seo", f"{name} construit les URL depuis l'origine de la requête : derrière un proxy "
                                        f"elles sortent en http:// (constaté sur le sitemap en ligne ?)", [name],
                        "utiliser l'origine canonique : new URL(path, import.meta.env.SITE ?? 'https://domaine.fr')")
                en_dur = [u for u in re.findall(r"http://[^\s'\"`<>)]+", code) if not NAMESPACES_XML.match(u)]
                if en_dur:
                    add("haute", "seo", f"{name} contient une URL http:// en dur ({en_dur[0][:60]})", [name])
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


# --------------------------------------------------------------------------- fonctionnalités Astro (doc officielle)
# Chaque contrôle est conditionné à la version installée : on ne recommande que ce qui existe dans cette version.
# Sources : docs.astro.build — guides/images, reference/modules/astro-assets, guides/fonts, guides/caching,
# reference/configuration-reference, reference/experimental-flags, integrations-guide/node.

DOC = "https://docs.astro.build/en"


def astro_version(root):
    """Version installée (node_modules) sinon plage du package.json → tuple (maj, min, patch) ou None."""
    for src in (root / "node_modules/astro/package.json", root / "package.json"):
        if not src.exists():
            continue
        data = json.loads(read(src) or "{}")
        v = data.get("version") if src.parent.name == "astro" else \
            {**data.get("dependencies", {}), **data.get("devDependencies", {})}.get("astro")
        m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", v or "")
        if m:
            return tuple(int(x or 0) for x in m.groups())
    return None


def latest_astro():
    try:
        import urllib.request
        with urllib.request.urlopen("https://registry.npmjs.org/astro/latest", timeout=6) as r:
            m = re.search(r"(\d+)\.(\d+)\.(\d+)", json.load(r).get("version", ""))
            return tuple(int(x) for x in m.groups()) if m else None
    except Exception:
        return None


def scan_astro_features(root, report):
    cfg = next((root / f for f in ("astro.config.mjs", "astro.config.ts", "astro.config.js", "astro.config.mts")
                if (root / f).exists()), None)
    t = sans_commentaires(read(cfg)) if cfg else ""
    cname = rel(cfg, root) if cfg else "astro.config"
    v = astro_version(root) or (0, 0, 0)
    latest = latest_astro()
    at_least = lambda *x: v >= x  # noqa: E731
    report["astro_version"] = {"installee": ".".join(map(str, v)), "derniere": ".".join(map(str, latest)) if latest else None}
    if latest and v[0] and v[0] < latest[0]:
        add("moyenne", "code", f"Astro {v[0]}.x installé, dernière version {latest[0]}.x : optimisations récentes "
                               f"indisponibles (images responsives, cache de routes, API fonts, CSP…)", [cname],
            f"planifier la montée de version en suivant {DOC}/guides/upgrade-to/v{latest[0]}/ (une majeure à la fois)")

    src = root / "src"
    files = list(iter_files(src, {".astro", ".mdx", ".md", ".ts", ".tsx", ".jsx"})) if src.exists() else []
    texts = {f: read(f) for f in files}
    astro_like = {f: tx for f, tx in texts.items() if f.suffix in (".astro", ".mdx")}
    image_tags = []  # (fichier, ligne, balise)
    for f, tx in astro_like.items():
        for m in re.finditer(r"<(Image|Picture)\b[^>]*?/?>", tx, re.S):
            image_tags.append((rel(f, root), tx.count("\n", 0, m.start()) + 1, m.group(0)))
    report["images_astro"] = {"balises": len(image_tags)}

    # --- service d'images
    if "passthroughImageService" in t:
        add("haute", "performance", "image.service = passthroughImageService : AUCUNE image n'est optimisée "
                                    "(ni redimensionnée, ni convertie)", [cname],
            f"revenir au service sharp par défaut (retirer image.service) si l'hébergeur le permet — {DOC}/guides/images/")
    # --- images responsives (5.10+)
    uses_layout = "layout" in t and re.search(r"image\s*:\s*\{[^}]*layout", t, re.S)
    tag_layout = sum(1 for _, _, tag in image_tags if re.search(r"\blayout\s*=", tag))
    tag_sizes = sum(1 for _, _, tag in image_tags if re.search(r"\b(widths|densities|sizes)\s*=", tag))
    if image_tags and at_least(5, 10) and not uses_layout and tag_layout == 0 and tag_sizes < len(image_tags) / 2:
        add("moyenne", "performance", f"Images responsives non activées : {len(image_tags) - tag_sizes} <Image>/<Picture> "
                                      f"sans srcset (une seule taille servie à tous les écrans)",
            [f"{a}:{b}" for a, b, _ in image_tags[:10]],
            "astro.config : image: { layout: 'constrained', responsiveStyles: true } → srcset et sizes générés "
            f"automatiquement ; layout=\"full-width\" pour les visuels pleine largeur — {DOC}/guides/images/#responsive-image-behavior")
    elif image_tags and not at_least(5, 10) and tag_sizes < len(image_tags) / 2:
        add("moyenne", "performance", "Images sans widths/sizes : une seule taille servie à tous les écrans",
            [f"{a}:{b}" for a, b, _ in image_tags[:10]], "ajouter widths={[400, 800, 1200]} et sizes=\"…\"")
    # --- priority (5.10+) sur l'image LCP
    prio = [f"{a}:{b}" for a, b, tag in image_tags if re.search(r"\bpriority\b", tag)]
    manual = [f"{a}:{b}" for a, b, tag in image_tags if "fetchpriority" in tag and "priority" not in tag.replace("fetchpriority", "")]
    if image_tags and at_least(5, 10) and not prio:
        add("moyenne", "performance", "Aucune <Image> marquée `priority` : l'image LCP (hero) est chargée comme les autres"
            + (f" ({len(manual)} avec fetchpriority manuel, sans decoding=\"sync\")" if manual else ""),
            manual[:5], "ajouter la prop `priority` sur l'image principale au-dessus de la ligne de flottaison "
                        "(loading=eager + decoding=sync + fetchpriority=high) — et seulement sur elle")
    if len(prio) > 2:
        add("basse", "performance", f"{len(prio)} images en `priority` : la priorité perd son effet si elle est partout", prio[:8])
    # --- Picture sans AVIF
    pic_no_avif = [f"{a}:{b}" for a, b, tag in image_tags if tag.startswith("<Picture") and "avif" not in tag]
    if pic_no_avif:
        add("basse", "performance", f"{len(pic_no_avif)} <Picture> sans AVIF (format le plus léger)", pic_no_avif[:8],
            "formats={['avif', 'webp']}")
    # --- images de public/ passées en chaîne
    pub_imgs = [f"{a}:{b}" for a, b, tag in image_tags if re.search(r"\bsrc\s*=\s*[\"']/(?!_astro)", tag)]
    for f, tx in astro_like.items():
        for i, line in enumerate(tx.splitlines(), 1):
            if re.search(r"<img\b[^>]*\bsrc=[\"']/[^\"']+\.(jpe?g|png|webp|gif|avif)", line, re.I):
                pub_imgs.append(f"{rel(f, root)}:{i}")
    if pub_imgs:
        add("moyenne", "performance", f"{len(pub_imgs)} image(s) servie(s) depuis public/ : « servies telles quelles, "
                                      f"sans aucun traitement » (doc Astro)", pub_imgs[:12],
            "déplacer dans src/assets/ et importer : import hero from '../assets/hero.jpg' → <Image src={hero} … />")
    # --- Markdown / MDX : images de public/
    md_pub = []
    for f, tx in texts.items():
        if f.suffix in (".md", ".mdx"):
            for i, line in enumerate(tx.splitlines(), 1):
                if re.search(r"!\[[^\]]*\]\(/[^)]+\)", line):
                    md_pub.append(f"{rel(f, root)}:{i}")
    if md_pub:
        add("moyenne", "performance", f"{len(md_pub)} image(s) Markdown pointant vers public/ : jamais optimisées",
            md_pub[:12], "chemins relatifs vers des fichiers de src/ (ex. ![alt](./images/x.jpg)) pour qu'Astro les optimise")
    # --- collections de contenu : image() plutôt que z.string()
    for cc in (root / "src/content.config.ts", root / "src/content/config.ts", root / "src/content.config.mjs"):
        if cc.exists():
            ct = read(cc)
            bad = [f"{rel(cc, root)}:{i}" for i, l in lines_matching(ct, re.compile(
                r"\b(image|images|cover|thumbnail|hero|heroImage|avatar|photo|visuel|banner)\s*:\s*z\.string\(\)"))]
            if bad:
                add("moyenne", "performance", "Champs image des collections typés z.string() : Astro ne peut ni valider "
                                              "ni optimiser ces images", bad,
                    "schema: ({ image }) => z.object({ cover: image() }) puis <Image src={entry.data.cover} … />")
    # --- endpoint /_image en SSR
    ssr = "output: 'server'" in t or 'output: "server"' in t or any("prerender = false" in tx for tx in texts.values())
    if ssr and image_tags:
        add("info", "performance", "Rendu à la demande + <Image> : les images des pages non prérendues passent par "
                                   "l'endpoint /_image, transformées à la requête (sharp) — coût CPU et latence si "
                                   "rien ne les met en cache côté serveur", [cname],
            "vérifier dans data/http/http-checks.md (§ /_image) ; prérendre les pages concernées, ou mettre /_image "
            "en cache au proxy/CDN (les réponses portent déjà Cache-Control public)")

    # --- polices : API Fonts (v6+)
    gfonts = any(re.search(r"fonts\.googleapis\.com|@fontsource", tx) for tx in texts.values())
    has_fonts_api = bool(re.search(r"\bfonts\s*:\s*\[", t))
    if at_least(6, 0) and not has_fonts_api:
        if gfonts or any("@font-face" in tx for tx in texts.values()):
            add("moyenne", "performance", "Polices chargées sans l'API Fonts d'Astro (v6+)", [cname],
                "fonts: [{ provider: fontProviders.google() | fontsource() | local(), name, cssVariable, weights, subsets }] "
                f"+ <Font cssVariable=\"--font-x\" preload /> : auto-hébergement, preload, fallbacks ajustés (moins de CLS) — {DOC}/guides/fonts/")
    if has_fonts_api and not any(re.search(r"<Font\b[^>]*\bpreload", tx) for tx in texts.values()):
        add("basse", "performance", "API Fonts configurée mais aucune <Font preload> : la police du texte principal "
                                    "arrive tard (FOUT / LCP texte)", [cname], "<Font cssVariable=\"…\" preload /> dans le <head>")

    # --- cache de routes (v7) / en-têtes de cache
    uses_cache_api = any("Astro.cache" in tx or "context.cache" in tx for tx in texts.values())
    has_cache_cfg = bool(re.search(r"\b(cache\s*:\s*\{|routeRules\s*:)", t))
    cc_headers = any(re.search(r"Cache-Control", tx) for tx in texts.values())
    report["cache"] = {"ssr": ssr, "config_cache": has_cache_cfg, "Astro.cache": uses_cache_api, "Cache-Control_manuel": cc_headers}
    if ssr and at_least(7, 0) and not (has_cache_cfg or uses_cache_api):
        add("haute", "performance", "Rendu à la demande sans cache de routes (Astro 7) : chaque visite re-rend la page "
                                    "et refait les requêtes backend", [cname],
            "cache: { provider: memoryCache() } + routeRules: { '/blog/[...slug]': { maxAge: 300, swr: 60 }, … } ; "
            "Astro.cache.set({ maxAge, swr, tags }) et cache.invalidate({ tags }) à la publication — "
            f"{DOC}/guides/caching/")
    elif ssr and not at_least(7, 0) and not cc_headers:
        add("moyenne", "performance", "Rendu à la demande sans en-têtes de cache : ni navigateur ni proxy/CDN ne peuvent "
                                      "réutiliser les pages", [cname],
            "Astro.response.headers.set('Cache-Control', 'public, s-maxage=300, stale-while-revalidate=600') sur les "
            "pages publiques + cache au proxy ; ou prérendre (export const prerender = true)")
    if ssr and not any("server:defer" in tx for tx in texts.values()) and \
            any("Astro.cookies" in tx or "Astro.locals" in tx for f, tx in texts.items() if "/components/" in str(f)):
        add("info", "performance", "Des composants lisent cookies/session : les isoler en server islands (server:defer) "
                                   "permettrait de prérendre ou de mettre en cache le reste de la page",
            fix=f"<UserMenu server:defer><Fallback slot=\"fallback\" /></UserMenu> — {DOC}/guides/server-islands/")

    # --- SVG
    svg_imports = sum(len(re.findall(r"import\s+\w+\s+from\s+['\"][^'\"]+\.svg['\"]", tx)) for tx in texts.values())
    if svg_imports >= 5 and "svgOptimizer" not in t and at_least(5, 16):
        add("basse", "performance", f"{svg_imports} composants SVG importés, sans optimisation SVGO", [cname],
            "experimental: { svgOptimizer: svgoOptimizer() } (import depuis 'astro/config', build uniquement)")

    # --- préchargement
    if "clientPrerender" not in t and re.search(r"prefetch\s*:", t):
        add("info", "performance", "prefetch actif : experimental.clientPrerender (Speculation Rules) peut prérendre "
                                   "les pages liées dans le navigateur", [cname])

    # --- proxy / URL : security.allowedDomains (5.14.2+)
    if ssr and at_least(5, 14) and not re.search(r"\ballowedDomains\s*:", t):
        add("moyenne", "seo", "Serveur derrière un proxy sans security.allowedDomains : Astro ignore X-Forwarded-Host/"
                              "Proto et Astro.url reflète l'hôte interne (souvent en http://) — cause typique de "
                              "canonicals/sitemap en http", [cname],
            "security: { allowedDomains: [{ hostname: 'mondomaine.fr', protocol: 'https' }] } + le proxy transmet "
            "X-Forwarded-Host et X-Forwarded-Proto ; et construire les URL publiques avec Astro.site")

    # --- sécurité : CSP intégrée (v6+) et astro:env
    mw_csp = any("Content-Security-Policy" in tx for tx in texts.values())
    if at_least(6, 0) and not re.search(r"\bcsp\s*:", t) and not mw_csp:
        add("basse", "securite", "Aucune Content-Security-Policy (ni security.csp d'Astro ≥ 6, ni en-tête via middleware)",
            [cname], "security: { csp: true } (hashes des scripts/styles générés automatiquement), tester d'abord en préproduction")
    secret_env = any(RX["env_private"].search(tx) for f, tx in texts.items() if f.suffix != ".md")
    if secret_env and not re.search(r"\benv\s*:\s*\{[^}]*schema", t, re.S):
        add("basse", "securite", "Variables d'environnement sans schéma astro:env : un secret peut finir côté client "
                                 "sans erreur de build", [cname],
            "env: { schema: { CLE: envField.string({ context: 'server', access: 'secret' }) } } puis import depuis astro:env/server")

    # --- divers perf
    if re.search(r"inlineStylesheets\s*:\s*['\"]always", t):
        add("basse", "performance", "build.inlineStylesheets: 'always' : tout le CSS est répété dans chaque page HTML "
                                    "(pas de cache navigateur)", [cname], "revenir à 'auto' (défaut)")
    if re.search(r"experimentalDisableStreaming\s*:\s*true", t):
        add("moyenne", "performance", "Streaming HTML désactivé (@astrojs/node) : le navigateur attend la page entière",
            [cname], "retirer experimentalDisableStreaming sauf contrainte du proxy")
    if any("<ClientRouter" in tx or "<ViewTransitions" in tx for tx in texts.values()):
        add("info", "performance", "View Transitions (ClientRouter) actives : routeur côté client chargé sur chaque page ; "
                                   "vérifier qu'elles servent réellement l'expérience")


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
    scan_astro_features(root, report)
    scan_convex(root, report)
    scan_dist(root, a.dist, report)
    scan_repo(root, report)
    order = {"critique": 0, "haute": 1, "moyenne": 2, "basse": 3, "info": 4}
    findings.sort(key=lambda f: order.get(f["severite"], 9))
    report["constats"] = findings
    (out / "code-scan.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    pk = report.get("package", {}) or {}
    cf = report.get("astro_config", {}) or {}
    av = report.get("astro_version", {})
    md = [f"# Scan du code Astro — {root.name}", "",
          f"- Version Astro : installée {av.get('installee')} — dernière {av.get('derniere') or 'inconnue (hors ligne)'}",
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
