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
  - Astro 6/7 : actions sans validation `input`, security.actionBodySizeLimit relevé, options experimental retirées en Astro 7,
    @astrojs/db, src/fetch.ts réservé, session sans ttl
  - monorepo : node_modules et lockfile cherchés du projet jusqu'à la racine du workspace (pnpm-workspace.yaml, "workspaces", .git)
  - bundle : plus gros fichiers JS/CSS du build (si dist/ présent), tailles gzip

Sorties : code-scan.json, code-scan.md
"""
import argparse
import functools
import gzip
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

EXCLUDE_DIRS = {"node_modules", ".git", "dist", ".astro", ".vercel", ".netlify", ".output", "_generated", ".turbo",
                ".cache", "coverage", ".next"}
SRC_EXT = {".astro", ".tsx", ".jsx", ".ts", ".js", ".mjs", ".svelte", ".vue", ".mdx", ".md"}
CLIENT_EXT = {".tsx", ".jsx", ".svelte", ".vue"}


def _lire_env(nom, defaut, conv):
    """Variable d'environnement numérique ; une valeur invalide retombe sur la valeur par défaut (jamais d'échec à l'import)."""
    try:
        return conv(os.environ.get(nom, defaut))
    except (TypeError, ValueError):
        return conv(defaut)


MAX_OCTETS = _lire_env("ASTRO_SCAN_MAX_OCTETS", "1500000", int)
BUDGET_S = _lire_env("ASTRO_SCAN_BUDGET_S", "300", float)
# État d'un scan : remis à zéro par reinitialiser() au début de main() (jamais hérité d'un scan précédent ni de l'import)
IGNORES = []          # fichiers non analysés et pourquoi (jamais un plantage de l'étape), sans doublon
_IGNORES_VUS = set()  # (fichier, raison) déjà notés : dédoublonnage en O(1)
NON_LUS = set()       # fichiers non lus parce que le budget de temps est épuisé
INTERROMPU = False    # vrai dès que le budget a interrompu une étape : plus aucune conclusion d'absence
_DEBUT = None         # départ du chronomètre (fixé par reinitialiser(), sinon au premier test du budget)
RACINE = None         # racine du projet : chemins relatifs des fichiers notés par read() quand elle n'est pas passée
_ACTIF = False        # vrai pendant main() ou pendant un scan_* appelé seul : le budget est alors partagé par les étapes

findings = []


def add(sev, cat, msg, where=None, fix=None):
    findings.append({"severite": sev, "categorie": cat, "constat": msg, "ou": where or [], "piste": fix or ""})


def add_entree(sev, cat, msg, where=None, fix=None):
    """Constat sur l'entrée du scan (fichiers ignorés, budget épuisé, étape en erreur), pas sur un défaut du site : pas de fiche
    (comme « package.json introuvable »). Nom distinct de add() pour rester hors de la couverture des fiches."""
    findings.append({"severite": sev, "categorie": cat, "constat": msg, "ou": where or [], "piste": fix or ""})


def rel(p, root):
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def reinitialiser(root=None):
    """Remet à zéro l'état d'un scan (constats, fichiers ignorés, budget). Appelée au début de main()."""
    global RACINE, INTERROMPU, _DEBUT
    findings.clear()
    IGNORES.clear()
    _IGNORES_VUS.clear()
    NON_LUS.clear()
    RACINE, INTERROMPU, _DEBUT = root, False, time.monotonic()


def ignorer(p, raison, root=None):
    """Note un fichier non analysé. Chemin relatif à `root` (sinon à RACINE, sinon le seul nom du fichier : jamais un
    chemin absolu, qui changerait d'une machine à l'autre)."""
    p, root = Path(p), root or RACINE
    cle = (rel(p, root) if root else p.name, raison)
    if cle not in _IGNORES_VUS:  # un fichier est lu par plusieurs étapes (scan_src, scan_astro_features)
        _IGNORES_VUS.add(cle)
        IGNORES.append({"fichier": cle[0], "raison": raison})


def budget_epuise():
    """Vrai au-delà de ASTRO_SCAN_BUDGET_S secondes : le scan s'arrête proprement (sorties écrites) et plus aucun
    constat d'absence n'est émis (voir INTERROMPU)."""
    global INTERROMPU, _DEBUT
    if _DEBUT is None:
        _DEBUT = time.monotonic()
    if time.monotonic() - _DEBUT <= BUDGET_S:
        return False
    INTERROMPU = True
    return True


def non_lus(fichiers, root):
    NON_LUS.update(rel(f, root) for f in fichiers)


def entree_autonome(etape):
    """Point d'entrée d'une étape du scan (`scan_*(root, …)`). Appelée par main(), elle partage le budget de temps et l'état de
    interruption de tout le scan. Appelée seule (tests, autre script), elle repart d'un budget neuf : ni INTERROMPU, ni NON_LUS,
    ni chronomètre d'un scan précédent ne sont hérités (sinon une interruption passée supprimerait à tort des constats d'absence).
    Les constats (`findings`) et les fichiers ignorés s'accumulent jusqu'à reinitialiser() : un appelant qui enchaîne
    plusieurs étapes les retrouve tous."""
    @functools.wraps(etape)
    def enveloppe(root, *args, **kwargs):
        global _ACTIF, INTERROMPU, _DEBUT, RACINE
        if _ACTIF:
            return etape(root, *args, **kwargs)
        _ACTIF = True
        INTERROMPU, _DEBUT, RACINE = False, time.monotonic(), root
        NON_LUS.clear()
        try:
            return etape(root, *args, **kwargs)
        finally:
            _ACTIF = False
    return enveloppe


def _dans(chemin, base):
    """`chemin` est `base` ou lui est sous-jacent (chemins réels)."""
    return chemin == base or chemin.startswith(base.rstrip(os.sep) + os.sep)


def iter_files(dossier, exts, racine=None):
    """Fichiers de `dossier` en ordre trié (ceux d'un dossier, puis ses sous-dossiers), sans descendre dans EXCLUDE_DIRS.
    Les liens symboliques qui restent dans le projet (`racine`) sont suivis, avec une garde de cycle sur le chemin réel :
    une cible déjà couverte par le parcours (dossier parent ou sous-dossier du dossier parcouru, cible déjà vue) n'est pas relue.
    Un lien dont la cible sort du projet n'est jamais suivi : il est noté (« lien hors du projet ») ; un lien cassé aussi."""
    racine_p = Path(racine or dossier)
    racine_r, debut_r = os.path.realpath(racine_p), os.path.realpath(dossier)
    vus = set()

    def exclu(reel):
        try:
            return bool(set(Path(reel).relative_to(racine_r).parts) & EXCLUDE_DIRS)
        except ValueError:
            return False

    def parcourir(d):
        reel = os.path.realpath(d)
        if reel in vus:
            return
        vus.add(reel)
        try:
            noms = sorted(os.listdir(d))
        except OSError as e:
            ignorer(d, f"fichier ignoré (illisible : {e.strerror or e})", racine_p)
            return
        fichiers, dossiers = [], []
        for nom in noms:
            p = Path(d, nom)
            if p.is_symlink():
                if nom in EXCLUDE_DIRS:
                    continue
                cible = os.path.realpath(p)
                if not os.path.exists(cible):
                    if p.suffix in exts:
                        ignorer(p, "fichier ignoré (lien symbolique cassé)", racine_p)
                    continue
                est_dossier = os.path.isdir(cible)
                if not est_dossier and p.suffix not in exts:
                    continue
                if not _dans(cible, racine_r):
                    ignorer(p, "fichier ignoré (lien hors du projet)", racine_p)
                    continue
                if exclu(cible) or _dans(cible, debut_r) or (est_dossier and _dans(debut_r, cible)):
                    continue  # déjà couvert par le parcours (ou exclu), ou cycle : rien n'est perdu
                (dossiers if est_dossier else fichiers).append(p)
            elif p.is_dir():
                if nom not in EXCLUDE_DIRS:
                    dossiers.append(p)
            elif p.suffix in exts:
                fichiers.append(p)
        yield from fichiers
        for sous in dossiers:
            yield from parcourir(sous)

    yield from parcourir(Path(dossier))


def _trop_gros(taille):
    return f"fichier ignoré (trop gros : {taille / 1e6:.1f} Mo > {MAX_OCTETS / 1e6:.1f} Mo)"


def read(p, root=None):
    """Fichiers de configuration : texte, ou "" s'il est absent, illisible ou démesuré (les deux derniers cas notés)."""
    try:
        taille = p.stat().st_size
        if taille > MAX_OCTETS:
            ignorer(p, _trop_gros(taille), root)
            return ""
        return p.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""
    except OSError as e:
        ignorer(p, f"fichier ignoré (illisible : {e.strerror or e})", root)
        return ""
    except Exception:
        return ""


def lire_source(p, root):
    """Texte d'un fichier source, ou None (raison notée dans IGNORES) : trop gros, binaire ou illisible.
    Les fichiers minifiés sont analysés (v2.0.1 : lignes longues sûres)."""
    try:
        taille = p.stat().st_size
        if taille > MAX_OCTETS:
            ignorer(p, _trop_gros(taille), root)
            return None
        brut = p.read_bytes()
    except OSError as e:
        ignorer(p, f"fichier ignoré (illisible : {e.strerror or e})", root)
        return None
    if b"\x00" in brut[:8192]:
        ignorer(p, "fichier ignoré (binaire)", root)
        return None
    return brut.decode("utf-8", errors="replace")


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


def sans_texte_litteral(t):
    """Vide le contenu des chaînes '…' et "…" et le texte des gabarits `…` en gardant leurs expressions ${…} :
    pour chercher un identifiant (site) dans le code seulement, pas dans du texte (« plan-du-site »)."""
    out, i, n = [], 0, len(t)
    while i < n:
        c = t[i]
        if c in "'\"":
            j = i + 1
            while j < n and t[j] != c and t[j] != "\n":
                j += 2 if t[j] == "\\" else 1
            out.append(c + " " * (min(j, n) - i - 1) + (c if j < n and t[j] == c else ""))
            i = j + 1 if j < n and t[j] == c else j
        elif c == "`":
            out.append(c)
            i += 1
            while i < n and t[i] != "`":
                if t[i] == "\\":
                    out.append("  ")
                    i += 2
                elif t.startswith("${", i):
                    prof, j = 1, i + 2
                    while j < n and prof:
                        prof += {"{": 1, "}": -1}.get(t[j], 0)
                        j += 1
                    out.append(t[i:j])
                    i = j
                else:
                    out.append("\n" if t[i] == "\n" else " ")
                    i += 1
            if i < n:
                out.append("`")
                i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


# Espaces de noms XML : des identifiants, pas des URL chargées (xmlns du sitemap…)
NAMESPACES_XML = re.compile(r"http://(www\.sitemaps\.org|www\.w3\.org|www\.google\.com/schemas|purl\.org)/")


def lines_matching(text, rx, limit=50):
    """(n° de ligne, extrait ≤ 160 car.) des lignes où rx trouve un motif. L'extrait est centré sur le motif :
    sur une ligne longue (minifiée, SVG inline…), couper au début perdrait le motif lui-même."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        m = rx.search(line)
        if m:
            debut = max(0, m.start() - 40) if m.end() > 160 else 0
            out.append((i, line[debut:debut + 160].strip()))
            if len(out) >= limit:
                break
    return out


def lignes_completes(text, rx, limit=50):
    """(n° de ligne, ligne entière) des lignes où rx trouve un motif : pour compter ou extraire sans troncature."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        if rx.search(line):
            out.append((i, line))
            if len(out) >= limit:
                break
    return out


# --------------------------------------------------------------------------- package.json / config

def _marque_workspace(d):
    """`d` est la racine d'un workspace/dépôt : pnpm-workspace.yaml, package.json avec "workspaces", ou .git (dossier ou fichier
    de worktree)."""
    if (d / "pnpm-workspace.yaml").exists() or (d / ".git").exists():
        return True
    try:
        pj = d / "package.json"
        if pj.stat().st_size > MAX_OCTETS:
            return False
        return bool(json.loads(pj.read_text(encoding="utf-8", errors="replace")).get("workspaces"))
    except (OSError, ValueError, AttributeError):
        return False


def racine_workspace(root):
    """Racine du workspace (monorepo pnpm / npm / yarn) qui contient `root`, `root` lui-même s'il n'y en a pas : le premier dossier,
    en remontant, qui contient pnpm-workspace.yaml, un package.json avec "workspaces" ou .git. La remontée s'arrête là
    (jamais au-delà) et n'a pas lieu du tout hors d'un workspace."""
    root = Path(os.path.abspath(root))
    return next((d for d in (root, *root.parents) if _marque_workspace(d)), root)


def dossiers_workspace(root):
    """De `root` jusqu'à la racine du workspace incluse : là où chercher node_modules et le lockfile (en monorepo, les
    dépendances sont hissées à la racine du workspace, pas dans apps/web). Contrairement à Node, qui remonte sans limite."""
    root = Path(os.path.abspath(root))
    haut = racine_workspace(root)
    return [root, *(d for d in root.parents if _dans(str(d), str(haut)))] if haut != root else [root]


@entree_autonome
def scan_package(root, report):
    pj = root / "package.json"
    if not pj.exists():
        add("haute", "projet", "package.json introuvable — est-ce bien la racine du projet Astro ?")
        return {}
    try:
        data = json.loads(read(pj, root) or "{}")
    except ValueError as e:
        ignorer(pj, f"fichier ignoré (JSON invalide : {getattr(e, 'msg', e)}, ligne {getattr(e, 'lineno', '?')})", root)
        data = {}
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
    lock, lock_dans = [], root
    for d in dossiers_workspace(root):  # le lockfile d'un monorepo est à la racine du workspace
        lock = [f for f in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock") if (d / f).exists()]
        if lock:
            lock_dans = d
            break
    report["package"]["lockfile"] = lock
    if lock and lock_dans != root:
        report["package"]["lockfile_dans"] = os.path.relpath(lock_dans, root)
    if not lock:
        add("moyenne", "projet", "Aucun lockfile : builds non reproductibles", fix="commiter le lockfile du gestionnaire utilisé")
    heavy = [d for d in deps if d in ("moment", "lodash", "jquery", "@fortawesome/fontawesome-free", "gsap", "three",
                                        "chart.js", "framer-motion", "swiper", "aos")]
    if heavy:
        add("basse", "performance", f"Dépendances lourdes à vérifier côté client : {', '.join(heavy)}",
            fix="n'importer que le nécessaire, charger à la demande (import() dynamique) ou remplacer")
    return deps


@entree_autonome
def scan_astro_config(root, report):
    cfg = next((root / f for f in ("astro.config.mjs", "astro.config.ts", "astro.config.js", "astro.config.mts")
                if (root / f).exists()), None)
    if not cfg:
        add("haute", "config", "astro.config.* introuvable")
        return {}
    t = sans_commentaires(read(cfg, root))
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


def _scanner_source(f, t, r, hyd, hyd_where, raw_imgs, img_no_alt, img_no_dims, compteurs, set_html, env_client, third,
                    gfonts, inline_scripts, storage_imgs):
    for i, line in lignes_completes(t, RX["client"], 200):
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
        compteurs["image_comp"] += len(RX["image_comp"].findall(t))
        if RX["storage_url"].search(t) and imgs:
            storage_imgs.append(r)
    # JSON-LD (<script type="application/ld+json" set:html={…}>) : pas du HTML interprété, pas un XSS.
    # La balise peut s'étaler sur plusieurs lignes (Prettier) : on exclut les lignes de toute la balise ouvrante.
    lignes_jsonld = set()
    for m in re.finditer(r"<script\b[^>]*>", t, re.I):
        if RX["jsonld_script"].search(m.group(0)):
            debut = t.count("\n", 0, m.start()) + 1
            lignes_jsonld.update(range(debut, debut + m.group(0).count("\n") + 1))
    set_html += [f"{r}:{i} {l}" for i, l in lines_matching(t, RX["set_html"]) if i not in lignes_jsonld]
    if f.suffix in CLIENT_EXT or ("<script" in t and f.suffix == ".astro"):
        # dans un .astro, seul le contenu des <script> part au navigateur
        scope = t if f.suffix in CLIENT_EXT else "\n".join(re.findall(r"<script\b[^>]*>(.*?)</script>", t, re.S))
        for m in RX["env_private"].finditer(scope):
            env_client.append(f"{r} : import.meta.env.{m.group(1)}")
        for m in RX["process_env"].finditer(scope):
            env_client.append(f"{r} : process.env.{m.group(1)}")
    third += [f"{r}:{i} {RX['third'].search(l).group(0)}" for i, l in lignes_completes(t, RX["third"])]
    gfonts += [f"{r}:{i}" for i, _ in lines_matching(t, RX["gfonts"])]
    inline_scripts += [f"{r}:{i}" for i, _ in lines_matching(t, RX["is_inline"])]


@entree_autonome
def scan_src(root, report):
    src = root / "src"
    if not src.exists():
        add("haute", "projet", "Dossier src/ introuvable")
        return
    hyd = Counter()
    hyd_where = defaultdict(list)
    raw_imgs, img_no_alt, img_no_dims, compteurs = [], [], [], {"image_comp": 0}
    set_html, env_client, third, gfonts, inline_scripts, storage_imgs = [], [], [], [], [], []
    fichiers_src = list(iter_files(src, SRC_EXT, root))
    for n, f in enumerate(fichiers_src):
        if budget_epuise():
            non_lus(fichiers_src[n:], root)
            break
        t = lire_source(f, root)
        if t is None:
            continue
        try:
            _scanner_source(f, t, rel(f, root), hyd, hyd_where, raw_imgs, img_no_alt, img_no_dims, compteurs, set_html,
                            env_client, third, gfonts, inline_scripts, storage_imgs)
        except Exception as e:  # une règle qui plante ignore ce fichier, pas toute l'étape
            ignorer(f, f"fichier ignoré (erreur {type(e).__name__} pendant l'analyse)", root)
    image_comp = compteurs["image_comp"]

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

    if INTERROMPU:  # fichiers non lus : ni layouts, ni routes, ni sitemap/robots (conclusions d'absence) — voir main()
        report["layouts"], report["routes"] = {}, {}
        return

    # --- SEO dans les layouts / head
    heads = [f for f in iter_files(src, {".astro"}, root) if re.search(r"<head\b", read(f, root))]
    head_report = {}
    for f in heads:
        t = read(f, root)
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
        dyn = [f for f in iter_files(pages, {".astro", ".ts", ".js"}, root) if "[" in f.name]
        risky = []
        for f in dyn:
            t = read(f, root)
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
        srv = [rel(f, root) for f in iter_files(pages, {".astro"}, root) if "prerender = false" in read(f, root)]
        pre = [rel(f, root) for f in iter_files(pages, {".astro"}, root) if "prerender = true" in read(f, root)]
        report["routes"]["prerender_false"] = srv
        report["routes"]["prerender_true"] = pre
        eps = {}
        for f in iter_files(pages, {".ts", ".js"}, root):
            n = f.name.lower()
            if any(k in n for k in ("sitemap", "robots", "llms", "rss", "feed")):
                eps[rel(f, root)] = read(f, root)
        report["routes"]["endpoints_seo"] = list(eps)
        for name, t in eps.items():
            if "sitemap" in name:
                code = sans_commentaires(t)
                par_requete = re.search(r"url\.origin|request\.url|Astro\.url\.origin|new URL\(\s*request", code)
                # l'identifiant `site` (Astro.site, context.site, ({ site })…), pas la sous-chaîne de « sitemaps.org »
                par_site = re.search(r"\bAstro\.site\b|\bcontext\.site\b|import\.meta\.env\.SITE\b|(?<![\w.$-])site\b(?!\s*:)",
                                     sans_texte_litteral(code))
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
        rt = read(rob, root)
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
    """Version installée (node_modules du projet, sinon celui du workspace) sinon plage du package.json → tuple
    (maj, min, patch) ou None. En monorepo, node_modules est hissé à la racine du workspace (voir dossiers_workspace)."""
    root = Path(root)
    sources = [d / "node_modules/astro/package.json" for d in dossiers_workspace(root)] + [root / "package.json"]
    for src in sources:
        if not src.exists():
            continue
        installe = src != root / "package.json"  # le package.json d'astro lui-même, pas celui du projet
        try:
            data = json.loads(read(src, src.parents[2] if installe else root) or "{}")
        except ValueError:
            continue
        v = data.get("version") if installe else \
            {**data.get("dependencies", {}), **data.get("devDependencies", {})}.get("astro")
        m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", v or "")
        if m:
            return tuple(int(x or 0) for x in m.groups())
    return None


def latest_astro():
    if os.environ.get("ASTRO_SCAN_HORS_LIGNE") == "1":
        return None
    try:
        import urllib.request
        with urllib.request.urlopen("https://registry.npmjs.org/astro/latest", timeout=6) as r:
            m = re.search(r"(\d+)\.(\d+)\.(\d+)", json.load(r).get("version", ""))
            return tuple(int(x) for x in m.groups()) if m else None
    except Exception:
        return None


@entree_autonome
def scan_astro_features(root, report):
    cfg = next((root / f for f in ("astro.config.mjs", "astro.config.ts", "astro.config.js", "astro.config.mts")
                if (root / f).exists()), None)
    t = sans_commentaires(read(cfg, root)) if cfg else ""
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
    files = list(iter_files(src, {".astro", ".mdx", ".md", ".ts", ".tsx", ".jsx"}, root)) if src.exists() else []
    texts = {}
    for n, f in enumerate(files):
        if budget_epuise():
            non_lus(files[n:], root)
            break
        contenu = lire_source(f, root)  # (pas `t` : c'est le texte de astro.config, utilisé plus bas)
        if contenu is not None:
            texts[f] = contenu
    if INTERROMPU:  # `texts` est partiel : « aucune CSP », « aucune <Image priority> »… seraient faux — voir main()
        return
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
            ct = read(cc, root)
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


# --------------------------------------------------------------------------- Astro 6 / 7 : actions, montée de version, sessions
# Sources (docs.astro.build, lues le 2026-10-01 — tâche 25 du plan v2.1) :
#   /en/guides/upgrade-to/v7/  : `rustCompiler`, `queuedRendering`, `advancedRouting` retirés (comportement par défaut), `logger`
#                                stabilisé (champ `logger` de premier niveau), `cache` et `routeRules` sortis de `experimental` ;
#                                `@astrojs/db` supprimé ; `src/fetch.ts` (ou .js) fichier réservé (option `fetchFile` pour le garder).
#   /en/reference/configuration-reference/ : security.actionBodySizeLimit (défaut 1048576, depuis 5.18.0) ; session.ttl
#                                (secondes, défaut Infinity, depuis 5.7.0).
#   /en/guides/actions/        : `input` est facultatif ; sans lui le handler reçoit les données brutes (FormData avec accept: 'form').
FLAGS_ASTRO7 = ("rustCompiler", "queuedRendering", "advancedRouting", "cache", "routeRules", "logger")
LIMITE_CORPS_DEFAUT = 1048576  # security.actionBodySizeLimit


def _structure(t):
    """Code sans commentaires ni texte de chaînes : seule la structure reste (accolades, clés). Les numéros de ligne sont conservés."""
    return sans_texte_litteral(sans_commentaires(t))


def _bloc_equilibre(n, ouvrante):
    """Contenu de l'objet dont l'accolade ouvrante est n[ouvrante] (accolades équilibrées ; `n` vient de _structure)."""
    prof = 0
    for j in range(ouvrante, len(n)):
        prof += {"{": 1, "}": -1}.get(n[j], 0)
        if prof == 0:
            return n[ouvrante + 1:j]
    return n[ouvrante + 1:]  # accolade jamais fermée : le reste du fichier


def _premier_niveau(bloc):
    """`bloc` dont le contenu des sous-blocs {…}, (…) et […] est vidé (mêmes positions) : il ne reste que les clés de l'objet lui-même,
    pas celles de ses imbriqués (`input` dans un handler, `ttl` dans un autre bloc)."""
    sortie, prof = [], 0
    for c in bloc:
        if c in "{([":
            sortie.append(c if prof == 0 else " ")
            prof += 1
        elif c in "})]":
            prof = max(prof - 1, 0)
            sortie.append(c if prof == 0 else " ")
        else:
            sortie.append(c if prof == 0 or c == "\n" else " ")
    return "".join(sortie)


def _a_cle(premier_niveau, cle):
    return bool(re.search(rf"(?<![\w$.]){cle}\s*(?::|,|\Z)", premier_niveau))


def _handler_sans_parametre(bloc, n0):
    """Le handler (clé de premier niveau) ne déclare aucun paramètre : il ne reçoit aucune donnée, rien à valider."""
    return any(re.match(r"\s*(?::\s*(?:async\s*)?(?:function\s*\w*\s*)?)?\(\s*\)", bloc[m.end():])
               for m in re.finditer(r"(?<![\w$.])handler\b", n0))


def _blocs_define_action(texte):
    """(ligne, bloc, premier niveau du bloc) de chaque `defineAction({ … })` du code (commentaires et chaînes exclus)."""
    n = _structure(texte)
    for m in re.finditer(r"(?<![\w$.])defineAction\s*\(\s*\{", n):
        bloc = _bloc_equilibre(n, m.end() - 1)
        yield n.count("\n", 0, m.start()) + 1, bloc, _premier_niveau(bloc)


def _action_sans_validation(bloc, n0):
    """Pas d'`input` au premier niveau, pas de `...autres` (qui peut l'apporter : on ne conclut pas), et un handler qui reçoit des données."""
    return not _a_cle(n0, "input") and "..." not in n0 and not _handler_sans_parametre(bloc, n0)


def _octets(expr):
    """`10485760`, `10_485_760`, `10 * 1024 * 1024` → entier."""
    total = 1
    for facteur in expr.replace("_", "").split("*"):
        total *= int(facteur)
    return total


@entree_autonome
def scan_astro7(root, report):
    cfg = next((root / f for f in ("astro.config.mjs", "astro.config.ts", "astro.config.js", "astro.config.mts")
                if (root / f).exists()), None)
    t = sans_commentaires(read(cfg, root)) if cfg else ""
    n = _structure(t)
    cname = rel(cfg, root) if cfg else "astro.config"
    v = astro_version(root) or (0, 0, 0)
    # --- Actions : validation des entrées
    sans_input = []
    actions = root / "src/actions"
    if actions.exists():
        fichiers = list(iter_files(actions, {".ts", ".js", ".mjs", ".mts"}, root))
        for k, f in enumerate(fichiers):
            if budget_epuise():  # constats positifs par fichier : ceux déjà trouvés restent valables
                non_lus(fichiers[k:], root)
                break
            texte = lire_source(f, root)
            if texte is None or "defineAction" not in texte:
                continue
            sans_input += [f"{rel(f, root)}:{ligne}" for ligne, bloc, n0 in _blocs_define_action(texte)
                           if _action_sans_validation(bloc, n0)]
    if sans_input:
        add("moyenne", "securite", f"Action Astro sans validation input ({len(sans_input)}) : données reçues non validées", sans_input[:20],
            "input: z.object({ … }) dans chaque defineAction (import { z } from 'astro/zod') — https://docs.astro.build/en/guides/actions/")
    m = re.search(r"\bactionBodySizeLimit\s*:\s*(\d[\d_]*(?:\s*\*\s*\d[\d_]*)*)", n)
    if m and _octets(m.group(1)) > LIMITE_CORPS_DEFAUT:
        add("basse", "securite", f"security.actionBodySizeLimit relevé à {_octets(m.group(1))} octets (défaut 1 Mo)", [cname],
            "ne relever que pour les actions d'envoi de fichiers, et vérifier l'identité avant de lire le corps")
    # --- Montée en Astro 7
    exp = set()
    for e in re.finditer(r"\bexperimental\s*:\s*\{", n):
        n0 = _premier_niveau(_bloc_equilibre(n, e.end() - 1))
        exp.update(f for f in FLAGS_ASTRO7 if re.search(rf"(?<![\w$.]){f}\s*:", n0))
    if exp:
        add("moyenne", "code", f"Options experimental à retirer ou à sortir avant Astro 7 : {', '.join(sorted(exp))}", [cname],
            f"suivre {DOC}/guides/upgrade-to/v7/")
    pk = (report.get("package") or {})
    ou_db = (["package.json"] if "@astrojs/db" in (pk.get("integrations") or []) else []) + \
            ([cname] if "@astrojs/db" in t else [])
    if ou_db:
        add("moyenne", "code", "@astrojs/db n'est plus pris en charge par Astro 7", ou_db, f"voir {DOC}/guides/upgrade-to/v7/")
    fetch = [rel(f, root) for f in (root / "src/fetch.ts", root / "src/fetch.js") if f.exists()]
    if fetch and v[0] and v[0] < 7 and not re.search(r"\bfetchFile\s*:", n):
        add("basse", "code", "src/fetch.ts est un fichier réservé à partir d'Astro 7", fetch,
            "renommer le fichier avant la montée de version (ou fixer fetchFile dans la configuration)")
    # --- Sessions (session.ttl : en secondes, infini par défaut)
    for s_ in re.finditer(r"\bsession\s*:\s*\{", n):
        if not _a_cle(_premier_niveau(_bloc_equilibre(n, s_.end() - 1)), "ttl"):
            add("info", "securite", "session configurée sans ttl : sessions sans expiration", [cname], "session: { ttl: 60 * 60 * 24 * 7 }")
            break


# --------------------------------------------------------------------------- Convex

FN_RX = re.compile(r"export\s+const\s+(\w+)\s*=\s*(query|mutation|action|internalQuery|internalMutation|internalAction|"
                   r"httpAction)\s*\(", re.M)
AUTH_RX = re.compile(r"getUserIdentity|ctx\.auth|getAuthUserId|requireAuth|requireUser|requireAdmin|assertAdmin|"
                     r"checkAuth|ensureAdmin|isAdmin|authorize|withAuth|currentUser|getCurrentUser|viewer", re.I)


@entree_autonome
def scan_convex(root, report):
    cdir = root / "convex"
    if not cdir.exists():
        report["convex"] = None
        return
    rep = {"fonctions": Counter(), "tables": 0, "index": 0}
    schema = cdir / "schema.ts"
    if schema.exists():
        st = read(schema, root)
        rep["tables"] = len(re.findall(r"defineTable\(", st))
        rep["index"] = len(re.findall(r"\.index\(", st)) + len(re.findall(r"\.searchIndex\(", st))
    no_auth, no_args, filters, collects, anys = [], [], [], [], []
    fichiers_convex = [f for f in iter_files(cdir, {".ts", ".js"}, root) if "_generated" not in f.parts]
    for n, f in enumerate(fichiers_convex):
        if budget_epuise():
            non_lus(fichiers_convex[n:], root)
            break
        t = lire_source(f, root)
        if t is None:
            continue
        try:
            r = rel(f, root)
            lignes = t.splitlines()
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
                ctx = "\n".join(lignes[max(0, i - 4): i])
                if "ctx.db.query" in ctx and "withIndex" not in ctx and "withSearchIndex" not in ctx:
                    filters.append(f"{r}:{i}")
            for i, l in lines_matching(t, re.compile(r"\.collect\(\)"), 200):
                ctx = "\n".join(lignes[max(0, i - 4): i])
                if "withIndex" not in ctx and ".take(" not in ctx:
                    collects.append(f"{r}:{i}")
            anys += [f"{r}:{i}" for i, _ in lines_matching(t, re.compile(r"v\.any\(\)"))]
        except Exception as e:  # une règle qui plante ignore ce fichier, pas toute l'étape
            ignorer(f, f"fichier ignoré (erreur {type(e).__name__} pendant l'analyse)", root)
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

@entree_autonome
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
    files = list(iter_files(d, {".js", ".css"}, root))
    rows = []
    for n, f in enumerate(files):
        if budget_epuise():
            non_lus(files[n:], root)
            break
        try:
            if f.stat().st_size > 20_000_000:
                ignorer(f, "fichier ignoré (trop gros pour la mesure gzip : > 20 Mo)", root)
                continue
            raw = f.read_bytes()
        except OSError as e:
            ignorer(f, f"fichier ignoré (illisible : {e.strerror or e})", root)
            continue
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

@entree_autonome
def scan_repo(root, report):
    gi = read(root / ".gitignore", root) if (root / ".gitignore").exists() else ""
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

MAX_LISTE = 50  # entrées de `fichiers_ignores` conservées (le reste : « … et N autres »)


def _exemples(lignes, n=10):
    return lignes[:n] + ([f"… et {len(lignes) - n} autres"] if len(lignes) > n else [])


def constats_de_synthese(report):
    """Rend visibles dans `constats` (seule liste lue par le rapport final) les entrées, fichiers ou étapes perdus."""
    if INTERROMPU:
        report["scan_interrompu"] = {"budget_s": int(BUDGET_S), "fichiers_non_lus": len(NON_LUS)}
        add_entree("moyenne", "code", f"Scan du code interrompu (budget de {BUDGET_S:.0f} s) : {len(NON_LUS)} fichiers non lus — "
                               f"constats d'absence non évalués", _exemples(sorted(NON_LUS)),
            "relancer avec un budget plus large (ASTRO_SCAN_BUDGET_S, en secondes) ou sur un sous-dossier")
    if IGNORES:
        n = len({i["fichier"] for i in IGNORES})
        add_entree("basse", "code", f"{n} fichier(s) ignoré(s) par le scan (trop gros / binaire / illisible / lien hors projet)",
            _exemples([f"{i['fichier']} : {i['raison']}" for i in IGNORES]),
            "les constats de ces fichiers manquent : les alléger ou les exclure, relever ASTRO_SCAN_MAX_OCTETS, "
            "ou lancer le scan depuis la racine du monorepo si un lien pointe hors du projet")
    if report.get("etapes_en_erreur"):
        add_entree("moyenne", "code", f"{len(report['etapes_en_erreur'])} étape(s) du scan de code en erreur : constats incomplets",
            report["etapes_en_erreur"][:10])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dist", help="dossier des assets buildés (défaut : dist/client/_astro ou dist/_astro)")
    a = ap.parse_args()
    root = Path(a.project).resolve()
    reinitialiser(root)  # état d'un scan précédent (même processus) ou de l'import : jamais hérité
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    report = {"projet": str(root)}
    etapes = [("scan_package", lambda: scan_package(root, report)), ("scan_astro_config", lambda: scan_astro_config(root, report)),
              ("scan_src", lambda: scan_src(root, report)), ("scan_astro_features", lambda: scan_astro_features(root, report)),
              ("scan_astro7", lambda: scan_astro7(root, report)), ("scan_convex", lambda: scan_convex(root, report)), ("scan_dist", lambda: scan_dist(root, a.dist, report)),
              ("scan_repo", lambda: scan_repo(root, report))]
    global _ACTIF
    _ACTIF = True  # budget et interruption partagés par toutes les étapes (voir entree_autonome)
    try:
        for nom, etape in etapes:
            try:
                etape()
            except Exception as e:  # une étape en erreur n'empêche ni les autres ni l'écriture des sorties
                report.setdefault("etapes_en_erreur", []).append(f"{nom} : {type(e).__name__}: {e}"[:300])
    finally:
        _ACTIF = False
    constats_de_synthese(report)
    n_ignores = len(IGNORES)
    report["fichiers_ignores"] = IGNORES[:MAX_LISTE] + ([{"fichier": "…", "raison": f"… et {n_ignores - MAX_LISTE} autres"}]
                                                         if n_ignores > MAX_LISTE else [])
    report["nb_fichiers_ignores"] = n_ignores
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
    if IGNORES or report.get("etapes_en_erreur") or INTERROMPU:
        md += ["## Fichiers ignorés et étapes en erreur", ""]
        md += [f"- {i['raison']}" if i["fichier"] == "…" else f"- `{i['fichier']}` : {i['raison']}" for i in report["fichiers_ignores"]]
        md += [f"- étape {e}" for e in report.get("etapes_en_erreur", [])]
        if INTERROMPU:
            md.append(f"- scan interrompu : budget de {BUDGET_S:.0f} s épuisé, {len(NON_LUS)} fichiers non lus")
        md.append("")
    if IGNORES:
        print(f"[attention] {n_ignores} fichier(s) ignoré(s) — voir code-scan.md", file=sys.stderr)
    (out / "code-scan.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"[ok] {len(findings)} constats — {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
