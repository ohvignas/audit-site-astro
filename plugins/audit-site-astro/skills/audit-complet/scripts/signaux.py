#!/usr/bin/env python3
"""
signaux.py — Collecte des signaux d'un audit à partir de DOSSIER_AUDIT/data/ (module partagé).

Utilisé par rapport_brut.py (Markdown), rapport_html.py (HTML/PDF) et historique.py, pour que tous les
rapports lisent les mêmes signaux, triés de la même façon.

API :
  collecter(audit)   -> liste de dicts {severite, domaine, texte, exemples}, triée par sévérité puis domaine
  lighthouse(audit)  -> entrées de perf/pagespeed.json sans clé « erreur »
  meta_crawl(audit)  -> « meta » de crawl/pages.json ({} si absent)
  charger(p)         -> contenu JSON du fichier p, ou None s'il est absent/illisible
  ORDRE              -> rang de chaque sévérité (critique=0 … info=4)
"""
import json
from pathlib import Path

ORDRE = {"critique": 0, "haute": 1, "moyenne": 2, "basse": 3, "info": 4}

_DOMAINES_CODE = {"performance": "Performance", "seo": "SEO technique", "securite": "Sécurité", "accessibilite": "Accessibilité",
                  "geo": "GEO / IA", "projet": "Code", "config": "Code"}


def charger(p):
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


def lighthouse(audit):
    """Entrées de pagespeed.json sans erreur."""
    perf = charger(Path(audit) / "data/perf/pagespeed.json") or []
    return [r for r in perf if not r.get("erreur")]


def meta_crawl(audit):
    return (charger(Path(audit) / "data/crawl/pages.json") or {}).get("meta", {})


def _signal(sev, domaine, texte, exemples):
    return {"severite": sev, "domaine": domaine, "texte": texte, "exemples": list(exemples)}


def collecter(audit):
    audit = Path(audit)
    d = audit / "data"
    signals = []

    crawl = charger(d / "crawl/issues.json") or {}
    for it in crawl.values():
        signals.append(_signal(it["severity"], "SEO technique", f"{it['label']} — {it['count']}", [ex_str(e) for e in it["examples"][:5]]))

    geo = charger(d / "geo/geo.json") or {}
    for s in geo.get("signaux", []):
        signals.append(_signal(s["severite"], "GEO / IA", s["constat"], []))

    code = charger(d / "code/code-scan.json") or {}
    for f in code.get("constats", []):
        signals.append(_signal(f["severite"], _DOMAINES_CODE.get(f["categorie"], "Code"),
                               f["constat"] + (f" → {f['piste']}" if f["piste"] else ""), f["ou"][:5]))

    seen = set()
    for r in lighthouse(audit):
        for o in r.get("opportunites", [])[:6]:
            key = o["id"]
            if key in seen or not (o.get("gain_ms") or o.get("gain_octets")):
                continue
            seen.add(key)
            sev = "haute" if (o.get("gain_ms") or 0) >= 1000 else "moyenne" if (o.get("gain_ms") or 0) >= 300 else "basse"
            gain = f"{o['gain_ms']} ms" if o.get("gain_ms") else f"{int(o['gain_octets']) // 1024} Ko"
            signals.append(_signal(sev, "Performance", f"{o['titre']} (gain estimé {gain}, {r.get('strategie')})", o.get("exemples", [])[:3]))
        for cat, fails in (r.get("echecs_autres_categories") or {}).items():
            for f in fails:
                key = cat + f
                if key not in seen:
                    seen.add(key)
                    signals.append(_signal("moyenne", "Accessibilité" if cat == "accessibility" else "SEO technique" if cat == "seo" else "Bonnes pratiques",
                                           f"Lighthouse : {f}", []))

    for path, dom_name in ((d / "securite/security-probe.md", "Sécurité"), (d / "http/http-checks.md", "Serveur / HTTP")):
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if "❌" in line:
                    signals.append(_signal("haute", dom_name, line.strip("| ").replace(" | ", " · ")[:220], []))
                elif "⚠️" in line and line.startswith("|"):
                    signals.append(_signal("basse", dom_name, line.strip("| ").replace(" | ", " · ")[:220], []))

    signals.sort(key=lambda s: (ORDRE.get(s["severite"], 9), s["domaine"]))
    return signals
