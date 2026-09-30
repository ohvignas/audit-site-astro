#!/usr/bin/env python3
"""
rapport_brut.py — Assemble les données collectées en un rapport lisible SANS agent IA.

Usage : python3 rapport_brut.py DOSSIER_AUDIT
Sortie : DOSSIER_AUDIT/RAPPORT-BRUT.md

C'est une synthèse automatique des signaux (triés par sévérité indicative). Pour un rapport priorisé,
dédoublonné par cause et avec les correctifs adaptés au code, lancer le skill `audit-complet` dans un agent.
"""
import json
import sys
from pathlib import Path

ORDER = {"critique": 0, "haute": 1, "moyenne": 2, "basse": 3, "info": 4}
ICON = {"critique": "🟥", "haute": "🟧", "moyenne": "🟨", "basse": "🟦", "info": "⬜"}


def load(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def ex_str(e):
    if isinstance(e, str):
        return e
    if isinstance(e, dict):
        return " — ".join(f"{k}: {v}" for k, v in e.items() if not isinstance(v, (list, dict)) or k in ("liens_depuis", "urls"))[:220]
    return str(e)[:220]


def main():
    audit = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    d = audit / "data"
    signals = []  # (sev, domaine, texte, exemples)

    crawl = load(d / "crawl/issues.json") or {}
    for k, it in crawl.items():
        signals.append((it["severity"], "SEO technique", f"{it['label']} — {it['count']}", [ex_str(e) for e in it["examples"][:5]]))

    geo = load(d / "geo/geo.json") or {}
    for s in geo.get("signaux", []):
        signals.append((s["severite"], "GEO / IA", s["constat"], []))

    code = load(d / "code/code-scan.json") or {}
    dom = {"performance": "Performance", "seo": "SEO technique", "securite": "Sécurité", "accessibilite": "Accessibilité",
           "geo": "GEO / IA", "projet": "Code", "config": "Code"}
    for f in code.get("constats", []):
        signals.append((f["severite"], dom.get(f["categorie"], "Code"), f["constat"] + (f" → {f['piste']}" if f["piste"] else ""),
                        f["ou"][:5]))

    perf = load(d / "perf/pagespeed.json") or []
    perf_rows, seen = [], set()
    for r in perf:
        if r.get("erreur"):
            continue
        sc, m = r.get("scores", {}), r.get("metriques", {})
        perf_rows.append(f"| {r['url']} | {r.get('strategie')} | {sc.get('performance', '—')} | {sc.get('accessibility', '—')} | "
                         f"{sc.get('seo', '—')} | {m.get('LCP', {}).get('affiche', '—')} | {m.get('CLS', {}).get('affiche', '—')} | "
                         f"{m.get('TBT', {}).get('affiche', '—')} |")
        for o in r.get("opportunites", [])[:6]:
            key = o["id"]
            if key in seen or not (o.get("gain_ms") or o.get("gain_octets")):
                continue
            seen.add(key)
            sev = "haute" if (o.get("gain_ms") or 0) >= 1000 else "moyenne" if (o.get("gain_ms") or 0) >= 300 else "basse"
            gain = f"{o['gain_ms']} ms" if o.get("gain_ms") else f"{int(o['gain_octets']) // 1024} Ko"
            signals.append((sev, "Performance", f"{o['titre']} (gain estimé {gain}, {r.get('strategie')})", o.get("exemples", [])[:3]))
        for cat, fails in (r.get("echecs_autres_categories") or {}).items():
            for f in fails:
                key = cat + f
                if key not in seen:
                    seen.add(key)
                    signals.append(("moyenne", "Accessibilité" if cat == "accessibility" else "SEO technique" if cat == "seo" else "Bonnes pratiques",
                                    f"Lighthouse : {f}", []))

    for path, dom_name in ((d / "securite/security-probe.md", "Sécurité"), (d / "http/http-checks.md", "Serveur / HTTP")):
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if "❌" in line:
                    signals.append(("haute", dom_name, line.strip("| ").replace(" | ", " · ")[:220], []))
                elif "⚠️" in line and line.startswith("|"):
                    signals.append(("basse", dom_name, line.strip("| ").replace(" | ", " · ")[:220], []))

    signals.sort(key=lambda s: (ORDER.get(s[0], 9), s[1]))
    counts = {k: sum(1 for s in signals if s[0] == k) for k in ORDER}
    meta = (load(d / "crawl/pages.json") or {}).get("meta", {})
    out = [f"# Rapport brut — {meta.get('start_url', audit.name)}", "",
           "_Synthèse automatique des signaux collectés. Pour un rapport priorisé avec correctifs adaptés au code, "
           "lancer le skill **audit-complet** dans un agent (Claude Code…)._", "",
           f"**Signaux** : " + " · ".join(f"{ICON[k]} {k} {v}" for k, v in counts.items() if v), ""]
    if perf_rows:
        out += ["## Lighthouse", "", "| Page | Mode | Perf | A11y | SEO | LCP | CLS | TBT |", "|---|---|---|---|---|---|---|---|"] + perf_rows + [""]
    current = None
    out.append("## Signaux par sévérité")
    for sev, domn, txt, exs in signals:
        if sev != current:
            current = sev
            out += ["", f"### {ICON.get(sev, '')} {sev.capitalize()}", ""]
        out.append(f"- **{domn}** — {txt}")
        out += [f"  - `{e}`" for e in exs if e]
    out += ["", "## Données détaillées", "",
            "- Collecte : `data/COLLECTE.md`", "- Crawl : `data/crawl/summary.md`", "- HTTP : `data/http/http-checks.md`",
            "- GEO : `data/geo/geo-summary.md`", "- Lighthouse : `data/perf/pagespeed-summary.md`",
            "- Sécurité : `data/securite/security-probe.md`", "- Code : `data/code/code-scan.md`"]
    (audit / "RAPPORT-BRUT.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"[ok] {audit / 'RAPPORT-BRUT.md'} — {len(signals)} signaux", file=sys.stderr)


if __name__ == "__main__":
    main()
