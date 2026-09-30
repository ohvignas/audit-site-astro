#!/usr/bin/env python3
"""
geo_check.py — Signaux GEO (visibilité dans ChatGPT, Perplexity, Claude, Gemini, Copilot, AI Overviews).

Usage :
  python3 geo_check.py https://exemple.fr --out AUDIT_DIR/data/geo \
      [--crawl AUDIT_DIR/data/crawl/pages.json] [--sample 12] [--delay 0.5]

Vérifie :
  1. robots.txt pour chaque robot IA (sémantique Google : groupe le plus spécifique, règle la plus longue)
  2. Réponse réelle du serveur/CDN/WAF à chaque user-agent IA (403, challenge Cloudflare…)
  3. llms.txt / llms-full.txt (présence, format, liens)
  4. Directives qui limitent les extraits (nosnippet, max-snippet, noai, data-nosnippet)
  5. Données structurées d'entité (Organization, Person, WebSite, Article, FAQ, LocalBusiness…)
  6. Extractibilité du contenu (texte sans JS, questions en titres, listes, tableaux, dates, auteur)
  7. Pages de confiance (à propos, contact, mentions légales, auteurs, FAQ, avis)

Sorties : geo.json, geo-summary.md
"""
import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crawl_site import BROWSER_UA, PageParser, RobotsTxt, decode_body, fetch, jsonld_types, normalize  # noqa: E402

AI_BOTS = [
    # (jeton robots.txt, user-agent de test ou None si jeton seul, rôle, famille)
    ("OAI-SearchBot", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot", "OpenAI — index de ChatGPT Search (citations)", "recherche"),
    ("ChatGPT-User", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot", "OpenAI — visite quand un utilisateur demande", "à la demande"),
    ("GPTBot", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.1; +https://openai.com/gptbot", "OpenAI — entraînement des modèles", "entraînement"),
    ("Claude-SearchBot", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-SearchBot/1.0; +Claude-SearchBot@anthropic.com)", "Anthropic — index de recherche", "recherche"),
    ("Claude-User", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-User/1.0; +Claude-User@anthropic.com)", "Anthropic — visite à la demande", "à la demande"),
    ("ClaudeBot", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)", "Anthropic — entraînement", "entraînement"),
    ("PerplexityBot", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)", "Perplexity — index (citations)", "recherche"),
    ("Perplexity-User", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Perplexity-User/1.0; +https://perplexity.ai/perplexity-user)", "Perplexity — visite à la demande", "à la demande"),
    ("Googlebot", "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "Google Search + AI Overviews + AI Mode", "recherche"),
    ("Google-Extended", None, "Google — Gemini / entraînement (jeton robots.txt, pas de UA)", "entraînement"),
    ("Bingbot", "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)", "Bing + Copilot (et source d'index pour d'autres assistants)", "recherche"),
    ("Applebot", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15 (Applebot/0.1; +http://www.apple.com/go/applebot)", "Apple — Siri / Spotlight", "recherche"),
    ("Applebot-Extended", None, "Apple — entraînement IA (jeton seul)", "entraînement"),
    ("DuckAssistBot", "DuckAssistBot/1.2; (+http://duckduckgo.com/duckassistbot.html)", "DuckDuckGo — réponses IA", "à la demande"),
    ("MistralAI-User", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; MistralAI-User/1.0; +https://docs.mistral.ai/robots)", "Mistral Le Chat", "à la demande"),
    ("Meta-ExternalAgent", "meta-externalagent/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)", "Meta AI — entraînement", "entraînement"),
    ("Amazonbot", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Amazonbot/0.1; +https://developer.amazon.com/support/amazonbot) Chrome/119.0 Safari/537.36", "Amazon — Alexa / Rufus", "recherche"),
    ("CCBot", "CCBot/2.0 (https://commoncrawl.org/faq/)", "Common Crawl — jeux de données", "entraînement"),
    ("Bytespider", "Mozilla/5.0 (Linux; Android 5.0) AppleWebKit/537.36 (KHTML, like Gecko) Mobile Safari/537.36 (compatible; Bytespider; spider-feedback@bytedance.com)", "ByteDance — entraînement", "entraînement"),
]

CHALLENGE_MARKERS = re.compile(r"just a moment|cf-browser-verification|challenge-platform|attention required|"
                               r"captcha|access denied|request blocked|sucuri website firewall|wordfence", re.I)
QUESTION_RX = re.compile(r"\?\s*$|^(comment|pourquoi|quel|quelle|quels|quelles|qu['’]est|combien|où|quand|"
                         r"faut-il|peut-on|est-ce|how|what|why|which|when|where|can|does|is)\b", re.I)
TRUST_PAGES = {
    "a_propos": r"a-propos|about|qui-sommes-nous|notre-histoire|l-agence|le-cabinet|presentation",
    "contact": r"contact",
    "mentions_legales": r"mentions-legales|legal-notice|imprint|informations-legales",
    "confidentialite": r"confidentialit|privacy|donnees-personnelles|rgpd",
    "equipe_auteurs": r"equipe|team|auteur|author|fondateur|formateur|expert",
    "faq": r"faq|questions-frequentes|foire-aux-questions",
    "avis": r"avis|temoignages|testimonials|reviews|references|realisations|etudes-de-cas|case-stud",
    "cgv": r"cgv|conditions-generales|terms",
}
TYPE_REQUIRED = {
    "Organization": ["name", "url", "logo", "sameAs"],
    "LocalBusiness": ["name", "address", "telephone", "url", "openingHoursSpecification", "geo"],
    "Person": ["name", "sameAs", "jobTitle"],
    "WebSite": ["name", "url"],
    "Article": ["headline", "author", "datePublished", "dateModified", "image", "publisher"],
    "BlogPosting": ["headline", "author", "datePublished", "dateModified", "image", "publisher"],
    "NewsArticle": ["headline", "author", "datePublished", "dateModified", "image", "publisher"],
    "Product": ["name", "offers", "image", "description"],
    "Course": ["name", "description", "provider"],
    "Service": ["name", "provider", "areaServed", "description"],
    "FAQPage": ["mainEntity"],
    "Event": ["name", "startDate", "location"],
}
LOCAL_TYPES = {"LocalBusiness", "ProfessionalService", "LegalService", "Attorney", "Dentist", "Restaurant", "Store",
               "HealthAndBeautyBusiness", "EducationalOrganization", "MedicalBusiness", "HomeAndConstructionBusiness"}


def check_robots(robots, home):
    rows = []
    for token, ua, role, family in AI_BOTS:
        rows.append({
            "bot": token, "role": role, "famille": family,
            "groupe_dedie": robots.explicit_group(token),
            "home_autorisee": robots.allowed(token, home),
        })
    return rows


def check_live_access(home, delay, timeout):
    base = fetch(home, timeout=timeout, ua=BROWSER_UA)
    base_len = len(base["body"])
    rows = [{"bot": "navigateur (référence)", "status": base["status"], "octets": base_len, "signal": ""}]
    for token, ua, _, _ in AI_BOTS:
        if not ua:
            continue
        r = fetch(home, timeout=timeout, ua=ua)
        body = decode_body(r)[:20000] if r["body"] else ""
        signal = []
        if r["status"] in (401, 403, 406, 429, 503):
            signal.append(f"HTTP {r['status']}")
        if r["headers"].get("cf-mitigated"):
            signal.append("cf-mitigated: " + r["headers"]["cf-mitigated"])
        if CHALLENGE_MARKERS.search(body) and not CHALLENGE_MARKERS.search(decode_body(base)[:20000]):
            signal.append("page de challenge / blocage WAF")
        if base_len and r["status"] == 200 and len(r["body"]) < 0.3 * base_len:
            signal.append(f"contenu réduit ({len(r['body'])} vs {base_len} octets)")
        rows.append({"bot": token, "status": r["status"], "octets": len(r["body"]), "signal": "; ".join(signal)})
        time.sleep(delay)
    return rows


def check_llms(origin, timeout):
    out = {}
    for name in ("llms.txt", "llms-full.txt"):
        r = fetch(f"{origin}/{name}", timeout=timeout, ua=BROWSER_UA)
        info = {"status": r["status"], "content_type": r["headers"].get("content-type", ""), "octets": len(r["body"])}
        if r["status"] == 200 and r["body"]:
            txt = decode_body(r)
            if txt.lstrip().lower().startswith(("<!doctype", "<html")):
                info["probleme"] = "renvoie du HTML (page WordPress/404 déguisée), pas un fichier texte"
            else:
                lines = [l for l in txt.splitlines() if l.strip()]
                links = re.findall(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", txt)
                info.update({
                    "h1_ok": bool(lines) and lines[0].startswith("# "),
                    "resume_blockquote": any(l.startswith("> ") for l in lines[:10]),
                    "sections_h2": sum(1 for l in lines if l.startswith("## ")),
                    "liens": len(links),
                })
                if name == "llms.txt":
                    broken = []
                    for _, u in links[:20]:
                        rr = fetch(u, timeout=timeout, method="HEAD", ua=BROWSER_UA)
                        if rr["status"] in (405, 501):
                            rr = fetch(u, timeout=timeout, max_bytes=2048, ua=BROWSER_UA)
                        if rr["status"] >= 400 or rr["status"] <= 0:
                            broken.append({"url": u, "status": rr["status"]})
                    info["liens_casses"] = broken
        out[name] = info
    return out


def pick_sample(crawl_path, home, n):
    """Échantillon : la home, puis un représentant par gabarit (1er segment d'URL). Les segments qui regroupent
    plusieurs pages (blog/…, formations/… : un gabarit partagé) passent avant les pages isolées, pour qu'un gabarit
    d'article ne soit jamais évincé par des pages uniques très liées ; puis complément par liens entrants."""
    if not crawl_path or not Path(crawl_path).exists():
        return [home], []
    data = json.load(open(crawl_path, encoding="utf-8"))
    pages = data["pages"]
    idx = [p for p in pages if p.get("indexable")]
    idx.sort(key=lambda p: -(p.get("inlinks") or 0))

    def seg(p):
        return (urlparse(p["url"]).path.strip("/").split("/") or [""])[0]

    taille = Counter(seg(p) for p in idx)
    chosen, segs = [home], set()
    for p in sorted(idx, key=lambda p: (-min(taille[seg(p)], 2), -(p.get("inlinks") or 0))):
        s = seg(p)
        if p["url"] != home and s not in segs:
            chosen.append(p["url"])
            segs.add(s)
        if len(chosen) >= n:
            break
    for p in idx:
        if len(chosen) >= n:
            break
        if p["url"] not in chosen:
            chosen.append(p["url"])
    return chosen, [p["url"] for p in pages if p.get("final_status") == 200 and not p.get("redirect_hops")]


def analyze_page(url, timeout):
    r = fetch(url, timeout=timeout, ua=BROWSER_UA)
    if r["status"] != 200 or not r["body"]:
        return {"url": url, "status": r["status"]}
    html = decode_body(r)
    p = PageParser()
    try:
        p.feed(html)
    except Exception:
        pass
    types, errors, objects = jsonld_types(p.jsonld_raw)
    missing = {}
    for o in objects:
        t = o.get("@type")
        for tt in (t if isinstance(t, list) else [t]):
            key = "LocalBusiness" if tt in LOCAL_TYPES else tt
            req = TYPE_REQUIRED.get(key)
            if req:
                miss = [f for f in req if not o.get(f)]
                if miss:
                    missing.setdefault(str(tt), set()).update(miss)
    names = sorted({str(o.get("name")) for o in objects
                    if o.get("@type") in ("Organization", "WebSite") or o.get("@type") in LOCAL_TYPES
                    if o.get("name")})
    same_as = sorted({s for o in objects for s in (o.get("sameAs") if isinstance(o.get("sameAs"), list)
                                                   else [o.get("sameAs")] if o.get("sameAs") else [])})
    has_author = p.has_author_link or bool(p.metas.get("author")) or any(o.get("author") for o in objects)
    has_modified = bool(p.metas.get("article:modified_time")) or any(o.get("dateModified") for o in objects)
    robots_meta = ",".join(filter(None, [p.metas.get("robots", ""), p.metas.get("googlebot", ""),
                                         r["headers"].get("x-robots-tag", "")])).lower()
    snippet_limits = [d for d in ("nosnippet", "noai", "noimageai", "noarchive") if d in robots_meta]
    m = re.search(r"max-snippet\s*:\s*(-?\d+)", robots_meta)
    if m and m.group(1) != "-1" and int(m.group(1)) < 160:
        snippet_limits.append(f"max-snippet:{m.group(1)}")
    headings = [t for lvl, t in p.headings if lvl in (2, 3)]
    return {
        "url": url, "status": 200,
        "jsonld_types": sorted(set(types)), "jsonld_errors": errors,
        "champs_manquants": {k: sorted(v) for k, v in missing.items()},
        "noms_entite": names, "sameAs": same_as[:20],
        "og_site_name": p.metas.get("og:site_name", ""),
        "microdata_items": p.microdata,
        "mots_sans_js": p.main_words or p.words,
        "ratio_texte_html": round(p.words * 6 / max(len(html), 1), 3),
        "titres_h2_h3": len(headings),
        "titres_questions": sum(1 for h in headings if QUESTION_RX.search(h.strip())),
        # dans <main> si présent (sinon toute la page, menus compris)
        "listes": (p.tags_main if p.main_words else p.tags).get("ul", 0) + (p.tags_main if p.main_words else p.tags).get("ol", 0),
        "tableaux": (p.tags_main if p.main_words else p.tags).get("table", 0),
        "balises_time": p.tags.get("time", 0),
        "auteur": has_author,
        "date_maj": has_modified,
        "limites_extraits": snippet_limits,
        "data_nosnippet": len(re.findall(r"data-nosnippet", html, re.I)),
        "iframes": p.tags.get("iframe", 0),
    }


def trust_pages(all_urls, origin, timeout):
    found = {}
    for key, rx in TRUST_PAGES.items():
        hits = [u for u in all_urls if re.search(rx, urlparse(u).path, re.I)]
        found[key] = hits[:3]
    if not all_urls:  # pas de crawl : on teste quelques slugs courants
        for key, slug in (("a_propos", "a-propos"), ("contact", "contact"), ("mentions_legales", "mentions-legales"),
                          ("faq", "faq")):
            r = fetch(f"{origin}/{slug}/", timeout=timeout, ua=BROWSER_UA, max_bytes=4096)
            found[key] = [f"{origin}/{slug}/"] if r["status"] == 200 else []
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", required=True)
    ap.add_argument("--crawl", help="pages.json produit par crawl_site.py")
    ap.add_argument("--sample", type=int, default=12)
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--timeout", type=int, default=20)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    home = normalize(a.url)
    first = fetch(home, timeout=a.timeout, ua=BROWSER_UA)
    home = normalize(first["final_url"]) or home
    origin = f"{urlparse(home).scheme}://{urlparse(home).netloc}"

    rr = fetch(f"{origin}/robots.txt", timeout=a.timeout, ua=BROWSER_UA)
    robots = RobotsTxt(decode_body(rr) if rr["status"] == 200 else "")
    print("[geo] robots.txt…", file=sys.stderr)
    robots_rows = check_robots(robots, home)
    print("[geo] accès réel par user-agent…", file=sys.stderr)
    live_rows = check_live_access(home, a.delay, a.timeout)
    print("[geo] llms.txt…", file=sys.stderr)
    llms = check_llms(origin, a.timeout)
    sample, all_urls = pick_sample(a.crawl, home, a.sample)
    print(f"[geo] analyse de {len(sample)} pages…", file=sys.stderr)
    pages = []
    for u in sample:
        pages.append(analyze_page(u, a.timeout))
        time.sleep(a.delay)
    trust = trust_pages(all_urls, origin, a.timeout)

    signals = []

    def sig(sev, msg):
        signals.append({"severite": sev, "constat": msg})

    for row in robots_rows:
        if not row["home_autorisee"]:
            sev = "haute" if row["famille"] in ("recherche", "à la demande") else "info"
            sig(sev, f"robots.txt bloque {row['bot']} ({row['role']})"
                + ("" if sev == "haute" else " — choix business possible, sans effet sur les citations en direct"))
    for row in live_rows[1:]:
        if row["signal"]:
            sig("haute", f"{row['bot']} : {row['signal']} (WAF/CDN ? — à confirmer dans les logs : certains pare-feu "
                         f"bloquent les faux bots dont l'IP n'est pas vérifiée)")
    if robots.other_lines:
        cs = [l for l in robots.other_lines if l.startswith("content-signal")]
        if cs:
            sig("info", "Content-Signal présent (robots.txt géré par Cloudflare ?) : " + " | ".join(cs[:3]))
    if llms["llms.txt"]["status"] != 200 or llms["llms.txt"].get("probleme"):
        sig("basse", "Pas de llms.txt exploitable (faible coût, effet non prouvé — utile surtout pour agents/outils IA)")
    ok_pages = [p for p in pages if p.get("status") == 200]
    all_types = Counter(t for p in ok_pages for t in p["jsonld_types"])
    if not any(t in all_types for t in ["Organization", "Person"] + sorted(LOCAL_TYPES)):
        sig("haute", "Aucune entité Organization / Person / LocalBusiness en JSON-LD — les IA identifient mal qui publie")
    if not any(p["sameAs"] for p in ok_pages):
        sig("moyenne", "Aucun sameAs (liens vers LinkedIn, Google Business Profile, Wikidata, réseaux) — "
                       "signal d'entité faible")
    names = sorted({n for p in ok_pages for n in p["noms_entite"]} | {p["og_site_name"] for p in ok_pages if p["og_site_name"]})
    if len(names) > 1:
        sig("moyenne", f"Nom de marque incohérent selon les pages/balises : {names[:6]}")
    micro = [p["url"] for p in ok_pages if p["microdata_items"] and p["jsonld_types"]]
    if micro:
        sig("basse", f"Microdata (souvent Astra) + JSON-LD (plugin SEO) sur {len(micro)} page(s) — vérifier doublons/"
                     f"incohérences d'entités")
    for p in ok_pages:
        if p["limites_extraits"]:
            sig("haute", f"{p['url']} limite les extraits ({', '.join(p['limites_extraits'])}) — exclut des AI Overviews")
        if p["jsonld_errors"]:
            sig("moyenne", f"{p['url']} : JSON-LD invalide")
        if p["champs_manquants"]:
            sig("basse", f"{p['url']} : champs schema manquants {p['champs_manquants']}")
    arts = [p for p in ok_pages if any(t in p["jsonld_types"] for t in ("Article", "BlogPosting", "NewsArticle"))]
    if arts and not all(p["auteur"] for p in arts):
        sig("moyenne", "Articles sans auteur identifiable (E-E-A-T)")
    if arts and not all(p["date_maj"] for p in arts):
        sig("moyenne", "Articles sans date de mise à jour (fraîcheur)")
    q = sum(p["titres_questions"] for p in ok_pages)
    if ok_pages and q < len(ok_pages):
        sig("moyenne", f"Peu de titres formulés en questions ({q} sur {len(ok_pages)} pages) — format peu « citable »")
    for k in ("a_propos", "contact", "mentions_legales", "confidentialite"):
        if not trust[k]:
            sig("moyenne" if k != "mentions_legales" else "haute",
                f"Page « {k.replace('_', ' ')} » introuvable" + (" (obligatoire en France — LCEN)" if k == "mentions_legales" else ""))

    result = {"home": home, "robots": robots_rows, "acces_reel": live_rows, "llms": llms,
              "pages": pages, "pages_confiance": trust, "types_jsonld_site": dict(all_types), "signaux": signals}
    (out / "geo.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    md = [f"# Signaux GEO — {home}", "", "## Accès des robots IA", "",
          "| Robot | Rôle | robots.txt (home) | Groupe dédié |", "|---|---|---|---|"]
    md += [f"| {r['bot']} | {r['role']} | {'✅ autorisé' if r['home_autorisee'] else '⛔ bloqué'} | "
           f"{'oui' if r['groupe_dedie'] else 'non (règles *)'} |" for r in robots_rows]
    md += ["", "## Réponse réelle du serveur par user-agent", "", "| UA | HTTP | Octets | Signal |", "|---|---|---|---|"]
    md += [f"| {r['bot']} | {r['status']} | {r['octets']} | {r['signal'] or '—'} |" for r in live_rows]
    md += ["", "## llms.txt", ""] + [f"- `{k}` : {json.dumps(v, ensure_ascii=False)}" for k, v in llms.items()]
    md += ["", "## Pages analysées", "",
           "| URL | Types JSON-LD | Mots | Q° | Listes | Tabl. | Auteur | Date MAJ | Limites |", "|---|---|---|---|---|---|---|---|---|"]
    for p in pages:
        if p.get("status") != 200:
            md.append(f"| {p['url']} | HTTP {p.get('status')} | | | | | | | |")
            continue
        md.append(f"| {p['url']} | {', '.join(p['jsonld_types'][:6]) or '—'} | {p['mots_sans_js']} | "
                  f"{p['titres_questions']}/{p['titres_h2_h3']} | {p['listes']} | {p['tableaux']} | "
                  f"{'oui' if p['auteur'] else 'non'} | {'oui' if p['date_maj'] else 'non'} | "
                  f"{', '.join(p['limites_extraits']) or '—'} |")
    md += ["", "## Pages de confiance", ""] + [f"- {k} : {', '.join(v) if v else '❌ non trouvée'}" for k, v in trust.items()]
    md += ["", "## Signaux", ""] + [f"- **{s['severite']}** — {s['constat']}" for s in signals]
    (out / "geo-summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"[ok] résultats dans {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
