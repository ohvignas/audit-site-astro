#!/usr/bin/env python3
"""
pagespeed.py — Lighthouse / PageSpeed Insights : collecte + synthèse (Python 3.8+, stdlib).

Deux modes :

  1) API PageSpeed Insights (données terrain CrUX + Lighthouse labo, sans Chrome local) :
     python3 pagespeed.py psi --out DIR --urls https://site.fr/ https://site.fr/page \
         [--urls-file liste.txt] [--strategies mobile,desktop]
     Clé optionnelle (quota plus large) : variable d'environnement PSI_API_KEY.

  2) Rapports Lighthouse locaux déjà produits (npx lighthouse … --output=json, Unlighthouse…) :
     python3 pagespeed.py parse --out DIR chemin/vers/rapports/ [autre.json …]

Sorties : pagespeed.json (données extraites) + pagespeed-summary.md (tableaux + opportunités).
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PSI = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
METRICS = [
    ("first-contentful-paint", "FCP"),
    ("largest-contentful-paint", "LCP"),
    ("total-blocking-time", "TBT"),
    ("cumulative-layout-shift", "CLS"),
    ("speed-index", "SI"),
    ("server-response-time", "TTFB labo"),
]
FIELD = [
    ("LARGEST_CONTENTFUL_PAINT_MS", "LCP", 2500, 4000, "ms"),
    ("INTERACTION_TO_NEXT_PAINT", "INP", 200, 500, "ms"),
    ("CUMULATIVE_LAYOUT_SHIFT_SCORE", "CLS", 10, 25, "/100"),
    ("FIRST_CONTENTFUL_PAINT_MS", "FCP", 1800, 3000, "ms"),
    ("EXPERIMENTAL_TIME_TO_FIRST_BYTE", "TTFB", 800, 1800, "ms"),
]
# Lighthouse 13 : audits remplacés par des « insights » (developer.chrome.com/blog/lighthouse-13-0). Ancien id → insight.
INSIGHTS_LH13 = {
    "layout-shifts": "cls-culprits-insight", "layout-shift-elements": "cls-culprits-insight",
    "largest-contentful-paint-element": "lcp-phases-insight", "third-party-summary": "third-parties-insight",
    "dom-size": "dom-size-insight", "server-response-time": "document-latency-insight",
    "uses-text-compression": "document-latency-insight", "redirects": "document-latency-insight",
    "render-blocking-resources": "render-blocking-insight", "uses-long-cache-ttl": "use-cache-insight",
    "font-display": "font-display-insight", "uses-http2": "modern-http-insight",
    "prioritize-lcp-image": "lcp-discovery-insight", "lcp-lazy-loaded": "lcp-discovery-insight",
}


def audit_lh(audits, ancien):
    """Audit Lighthouse ≤ 12, sinon l'insight Lighthouse 13 qui l'a remplacé, sinon {}."""
    return audits.get(ancien) or audits.get(INSIGHTS_LH13.get(ancien, ""), {})


def find_snippets(obj, acc, limit=3):
    if len(acc) >= limit:
        return acc
    if isinstance(obj, dict):
        node = obj.get("node")
        if isinstance(node, dict) and node.get("snippet"):
            acc.append({"snippet": node["snippet"][:300], "selector": node.get("selector", "")})
        for v in obj.values():
            find_snippets(v, acc, limit)
    elif isinstance(obj, list):
        for v in obj:
            find_snippets(v, acc, limit)
    return acc


def flat_items(det):
    """Lighthouse 12 : items peut être une liste, un dict, ou des sous-tableaux (details type list)."""
    if not isinstance(det, dict):
        return []
    items = det.get("items") or []
    if isinstance(items, dict):
        items = list(items.values())
    out = []
    for x in items:
        if isinstance(x, dict) and x.get("type") in ("table", "opportunity", "list", "checklist") and "items" in x:
            out += flat_items(x)
        elif isinstance(x, dict):
            out.append(x)
    return out


def audit_en_echec(a):
    """Échec réel seulement : binaire à 0, numérique < 0,9. Informatif, manuel, non applicable, erreur : jamais."""
    mode, score = a.get("scoreDisplayMode"), a.get("score")
    if mode in ("binary", None):
        return score == 0
    if mode in ("numeric", "metricSavings"):
        return score is not None and score < 0.9
    return False


def summarize_lhr(lhr):
    audits = lhr.get("audits", {})
    cats = {k: round((v.get("score") or 0) * 100) for k, v in lhr.get("categories", {}).items()
            if v.get("score") is not None}
    metrics = {}
    for aid, label in METRICS:
        a = audits.get(aid)
        if a and a.get("numericValue") is not None:
            metrics[label] = {"valeur": round(a["numericValue"], 3), "affiche": a.get("displayValue", ""),
                              "score": a.get("score")}
    lcp_el = []
    for aid in ("largest-contentful-paint-element", "lcp-discovery-insight", "lcp-phases-insight",
                "lcp-breakdown-insight"):
        if aid in audits:
            lcp_el = find_snippets(audits[aid].get("details", {}), [], 1)
            if lcp_el:
                break
    cls_el = find_snippets((audits.get("layout-shifts") or audits.get("layout-shift-elements")
                            or audits.get("cls-culprits-insight") or {}).get("details", {}), [], 3)

    opps = []
    perf_refs = [r["id"] for r in lhr.get("categories", {}).get("performance", {}).get("auditRefs", [])]
    for aid in perf_refs:
        a = audits.get(aid) or {}
        mode = a.get("scoreDisplayMode")
        score = a.get("score")
        if mode in ("notApplicable", "manual", "error") or aid in dict(METRICS):
            continue
        det = a.get("details") or {}
        ms = det.get("overallSavingsMs") or 0
        by = det.get("overallSavingsBytes") or 0
        ms_metric = a.get("metricSavings") or {}
        weight = sum(v for v in ms_metric.values() if isinstance(v, (int, float)))
        # LH 13 : les insights n'ont plus overallSavingsMs, seulement metricSavings (FCP/LCP se recouvrent : max, pas somme)
        gain_metrique = max([v for v in ms_metric.values() if isinstance(v, (int, float))] or [0])
        failing = (score is not None and score < 0.9) or (mode == "informative" and (ms or by or weight))
        # LH 13 : la compression du document est une case de document-latency-insight (plus d'audit dédié)
        cases = det.get("items") if det.get("type") == "checklist" and isinstance(det.get("items"), dict) else {}
        echecs_cases = [k for k, v in cases.items() if isinstance(v, dict) and v.get("value") is False]
        if echecs_cases:
            failing = True
        if not failing:
            continue
        items = [] if cases else flat_items(det)
        top = []
        for it in items[:5]:
            if isinstance(it, dict):
                ent = it.get("entity")
                url = it.get("url") or it.get("source", {}).get("url", "") if isinstance(it.get("source"), dict) \
                    else it.get("url", "")
                if not url and ent:
                    url = ent.get("text", "") if isinstance(ent, dict) else str(ent)
                if url:
                    top.append(str(url)[:160])
        opps.append({"id": aid, "titre": a.get("title", aid) + (" (compression du document absente)" if "usesCompression" in echecs_cases else ""),
                     "affiche": a.get("displayValue", ""),
                     "gain_ms": round(ms or gain_metrique), "gain_octets": by, "gains_metriques": ms_metric, "score": score,
                     "exemples": top, "_poids": ms + weight + by / 10000})
    opps.sort(key=lambda o: -o["_poids"])
    for o in opps:
        o.pop("_poids", None)

    third = []
    tp = flat_items(audit_lh(audits, "third-party-summary").get("details", {}))
    for it in tp[:8]:
        ent = it.get("entity")
        name = ent.get("text") if isinstance(ent, dict) else ent
        third.append({"tiers": name, "ko": round((it.get("transferSize") or 0) / 1024),
                      "blocage_ms": round(it.get("blockingTime") or 0)})
    misc = {}
    for aid, key in (("total-byte-weight", "poids_total_ko"), ("dom-size", "noeuds_dom"),
                     ("bootup-time", "js_execution_ms"), ("mainthread-work-breakdown", "thread_principal_ms")):
        a = audit_lh(audits, aid)
        if a and a.get("numericValue") is not None:
            v = a["numericValue"]
            misc[key] = round(v / 1024) if key.endswith("_ko") else round(v)
    reqs = flat_items(audits.get("network-requests", {}).get("details", {}))
    if reqs:
        misc["requetes"] = len(reqs)
    fails = {}
    for cat_id in ("accessibility", "seo", "best-practices"):
        refs = lhr.get("categories", {}).get(cat_id, {}).get("auditRefs", [])
        # titre + [id] : certains titres d'échec traduits se lisent comme un succès
        # (fr : « Les liens sont identifiables grâce à leur couleur. » = ÉCHEC de link-in-text-block)
        fails[cat_id] = ["{0} [{1}]".format(audits[r["id"]].get("title", r["id"]), r["id"]) for r in refs
                         if r.get("weight", 0) > 0 and audit_en_echec(audits.get(r["id"], {}))]
    return {"url": lhr.get("finalDisplayedUrl") or lhr.get("finalUrl") or lhr.get("requestedUrl"),
            "form_factor": (lhr.get("configSettings") or {}).get("formFactor", ""),
            "lighthouse": lhr.get("lighthouseVersion"), "scores": cats, "metriques": metrics,
            "element_lcp": lcp_el, "elements_cls": cls_el, "opportunites": opps[:15], "tiers": third,
            "divers": misc, "echecs_autres_categories": fails}


def field_data(exp):
    if not exp or not exp.get("metrics"):
        return None
    out = {"categorie_globale": exp.get("overall_category")}
    for key, label, good, poor, unit in FIELD:
        m = exp["metrics"].get(key)
        if m and m.get("percentile") is not None:
            p = m["percentile"]
            verdict = "bon" if p <= good else ("à améliorer" if p <= poor else "mauvais")
            out[label] = {"p75": p if unit == "ms" else p / 100, "verdict": verdict}
    return out


def run_psi(args):
    urls = list(args.urls or [])
    if args.urls_file:
        urls += [l.strip() for l in open(args.urls_file, encoding="utf-8") if l.strip().startswith("http")]
    key = os.environ.get("PSI_API_KEY")
    results = []
    raw_dir = Path(args.out) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for url in urls:
        for strategy in args.strategies.split(","):
            q = [("url", url), ("strategy", strategy), ("locale", "fr")]
            q += [("category", c) for c in ("PERFORMANCE", "ACCESSIBILITY", "BEST_PRACTICES", "SEO")]
            if key:
                q.append(("key", key))
            full = PSI + "?" + urllib.parse.urlencode(q)
            print(f"[psi] {strategy} {url}", file=sys.stderr)
            data = None
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(full, timeout=180) as r:
                        data = json.load(r)
                    break
                except Exception as e:  # quota 429, timeout…
                    print(f"  essai {attempt + 1} échoué : {e}", file=sys.stderr)
                    if "429" in str(e) and not key:
                        print("  → quota anonyme PSI épuisé : définir PSI_API_KEY ou utiliser lighthouse_run.sh",
                              file=sys.stderr)
                        break
                    time.sleep(10 * (attempt + 1))
            if not data:
                results.append({"url": url, "strategie": strategy, "erreur": "PSI injoignable ou quota dépassé "
                                "(définir PSI_API_KEY ou utiliser Lighthouse local)"})
                continue
            safe = urllib.parse.quote(url, safe="")[:120]
            (raw_dir / f"{strategy}-{safe}.json").write_text(json.dumps(data), encoding="utf-8")
            s = summarize_lhr(data.get("lighthouseResult", {}))
            s.update({"strategie": strategy, "terrain_page": field_data(data.get("loadingExperience")),
                      "terrain_origine": field_data(data.get("originLoadingExperience"))})
            results.append(s)
            time.sleep(2)
    write(args.out, results)


def run_parse(args):
    files = []
    for p in args.paths:
        p = Path(p)
        files += sorted(p.rglob("*.json")) if p.is_dir() else [p]
    results = []
    for f in files:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        lhr = d.get("lighthouseResult", d) if isinstance(d, dict) else None
        if not (isinstance(lhr, dict) and "audits" in lhr and "categories" in lhr):
            continue
        s = summarize_lhr(lhr)
        s["source"] = str(f)
        s["strategie"] = s.get("form_factor") or "?"
        results.append(s)
    if not results:
        sys.exit("Aucun rapport Lighthouse JSON trouvé")
    write(args.out, results)


def write(out, results):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "pagespeed.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# Performance — Lighthouse / PageSpeed", "",
          "| URL | Mode | Perf | A11y | BP | SEO | LCP | CLS | TBT | FCP | TTFB labo |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        if r.get("erreur"):
            md.append(f"| {r['url']} | {r['strategie']} | ❌ {r['erreur']} |||||||||")
            continue
        sc, m = r["scores"], r["metriques"]
        md.append(f"| {r['url']} | {r['strategie']} | {sc.get('performance', '—')} | {sc.get('accessibility', '—')} | "
                  f"{sc.get('best-practices', '—')} | {sc.get('seo', '—')} | {m.get('LCP', {}).get('affiche', '—')} | "
                  f"{m.get('CLS', {}).get('affiche', '—')} | {m.get('TBT', {}).get('affiche', '—')} | "
                  f"{m.get('FCP', {}).get('affiche', '—')} | {m.get('TTFB labo', {}).get('affiche', '—')} |")
    field = [r for r in results if r.get("terrain_page") or r.get("terrain_origine")]
    md += ["", "## Données terrain (CrUX, p75 des vrais visiteurs, 28 jours)", ""]
    if field:
        for r in field:
            for scope in ("terrain_page", "terrain_origine"):
                fd = r.get(scope)
                if fd:
                    vals = ", ".join(f"{k} {v['p75']} ({v['verdict']})" for k, v in fd.items() if isinstance(v, dict))
                    md.append(f"- {r['url']} [{r['strategie']}, {scope.split('_')[1]}] : {vals}")
    else:
        md.append("- Pas assez de trafic Chrome pour des données terrain : se fier au labo + mesurer en RUM.")
    for r in results:
        if r.get("erreur"):
            continue
        md += ["", f"## {r['url']} — {r['strategie']}", ""]
        if r["element_lcp"]:
            md.append(f"- Élément LCP : `{r['element_lcp'][0]['snippet']}`")
        if r["elements_cls"]:
            md.append("- Éléments qui bougent (CLS) : " + " ; ".join(f"`{e['snippet'][:120]}`" for e in r["elements_cls"]))
        if r["divers"]:
            md.append("- " + ", ".join(f"{k} = {v}" for k, v in r["divers"].items()))
        if r["tiers"]:
            md.append("- Tiers : " + ", ".join(f"{t['tiers']} ({t['ko']} Ko, {t['blocage_ms']} ms)" for t in r["tiers"]))
        if r["opportunites"]:
            md.append("- Opportunités (par gain estimé) :")
            for o in r["opportunites"][:10]:
                gain = f"{o['gain_ms']} ms" if o["gain_ms"] else (f"{int(o['gain_octets']) // 1024} Ko" if o["gain_octets"] else "")
                md.append(f"  - {o['titre']} {('— ' + o['affiche']) if o['affiche'] else ''} {('(' + gain + ')') if gain else ''}"
                          + (f" — ex. {o['exemples'][0]}" if o["exemples"] else ""))
        for cat, fails in r["echecs_autres_categories"].items():
            if fails:
                md.append(f"- Échecs {cat} : " + " ; ".join(fails[:8]))
    (out / "pagespeed-summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"[ok] {len(results)} rapport(s) — {out}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("psi")
    p1.add_argument("--out", required=True)
    p1.add_argument("--urls", nargs="*")
    p1.add_argument("--urls-file")
    p1.add_argument("--strategies", default="mobile,desktop")
    p2 = sub.add_parser("parse")
    p2.add_argument("--out", required=True)
    p2.add_argument("paths", nargs="+")
    a = ap.parse_args()
    run_psi(a) if a.cmd == "psi" else run_parse(a)


if __name__ == "__main__":
    main()
