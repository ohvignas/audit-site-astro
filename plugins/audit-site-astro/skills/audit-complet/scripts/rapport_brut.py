#!/usr/bin/env python3
"""
rapport_brut.py — Assemble les données collectées en un rapport lisible SANS agent IA.

Usage : python3 rapport_brut.py DOSSIER_AUDIT
Sortie : DOSSIER_AUDIT/RAPPORT-BRUT.md

C'est une synthèse automatique des signaux (triés par sévérité indicative). Pour un rapport priorisé,
dédoublonné par cause et avec les correctifs adaptés au code, lancer le skill `audit-complet` dans un agent.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import signaux  # noqa: E402

ORDER = signaux.ORDRE
severite_opportunite = signaux.severite_opportunite  # compatibilité : la règle vit dans signaux.py
ICON = {"critique": "🟥", "haute": "🟧", "moyenne": "🟨", "basse": "🟦", "info": "⬜"}


def main():
    audit = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    signals = signaux.collecter(audit)

    perf_rows = []
    for r in signaux.lighthouse(audit):
        sc, m = r.get("scores", {}), r.get("metriques", {})
        perf_rows.append(f"| {r['url']} | {r.get('strategie')} | {sc.get('performance', '—')} | {sc.get('accessibility', '—')} | "
                         f"{sc.get('seo', '—')} | {m.get('LCP', {}).get('affiche', '—')} | {m.get('CLS', {}).get('affiche', '—')} | "
                         f"{m.get('TBT', {}).get('affiche', '—')} |")

    counts = {k: sum(1 for s in signals if s["severite"] == k) for k in ORDER}
    meta = signaux.meta_crawl(audit)
    out = [f"# Rapport brut — {meta.get('start_url', audit.name)}", "",
           "_Synthèse automatique des signaux collectés. Pour un rapport priorisé avec correctifs adaptés au code, "
           "lancer le skill **audit-complet** dans un agent (Claude Code…)._", "",
           f"**Signaux** : " + " · ".join(f"{ICON[k]} {k} {v}" for k, v in counts.items() if v), ""]
    if perf_rows:
        out += ["## Lighthouse", "", "| Page | Mode | Perf | A11y | SEO | LCP | CLS | TBT |", "|---|---|---|---|---|---|---|---|"] + perf_rows + [""]
    current = None
    out.append("## Signaux par sévérité")
    for s in signals:
        sev, domn, txt, exs = s["severite"], s["domaine"], s["texte"], s["exemples"]
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
