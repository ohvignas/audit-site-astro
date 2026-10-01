#!/usr/bin/env python3
"""
signaux.py — Collecte des signaux d'un audit à partir de DOSSIER_AUDIT/data/ (module partagé).

Utilisé par rapport_brut.py (Markdown), rapport_html.py (HTML/PDF) et historique.py, pour que tous les
rapports lisent les mêmes signaux, triés de la même façon.

API :
  collecter(audit)   -> liste de dicts {severite, domaine, texte, exemples, source, cle}, triée par sévérité puis domaine
  lighthouse(audit)  -> entrées de perf/pagespeed.json sans clé « erreur »
  meta_crawl(audit)  -> « meta » de crawl/pages.json ({} si absent)
  charger(p)         -> contenu JSON du fichier p, ou None s'il est absent/illisible
  severite_opportunite(ms, octets) -> sévérité d'une opportunité Lighthouse (temps OU poids gagné)
  ORDRE              -> rang de chaque sévérité (critique=0 … info=4)
"""
import json
from pathlib import Path

ORDRE = {"critique": 0, "haute": 1, "moyenne": 2, "basse": 3, "info": 4}

_DOMAINES_CODE = {"performance": "Performance", "seo": "SEO technique", "securite": "Sécurité", "accessibilite": "Accessibilité",
                  "geo": "GEO / IA", "projet": "Code", "config": "Code"}


_VULN = {"- **critical**": "critique", "- **high**": "haute", "- **moderate**": "moyenne"}
SOURCES_ISSUES = (("crawl", "crawl/issues.json", "SEO technique"), ("rendu", "rendu/issues.json", "Accessibilité"),
                  ("domaine", "domaine/issues.json", "Sécurité"), ("terrain", "terrain/issues.json", "Performance"))


def charger(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def ex_str(e):
    if isinstance(e, str):
        return e
    if isinstance(e, dict):
        return " — ".join(f"{k}: {v}" for k, v in e.items() if not isinstance(v, (list, dict)) or k in ("liens_depuis", "urls", "exemples_pages"))[:220]
    return str(e)[:220]


def severite_opportunite(ms, octets):
    """Sévérité d'un gain Lighthouse : le temps OU le poids économisé (6 Mo d'images = haute même sans ms estimées)."""
    ms, octets = ms or 0, octets or 0
    if ms >= 1000 or octets >= 1000000:
        return "haute"
    if ms >= 300 or octets >= 250000:
        return "moyenne"
    return "basse"


def lighthouse(audit):
    """Entrées de pagespeed.json sans erreur."""
    perf = charger(Path(audit) / "data/perf/pagespeed.json") or []
    if not isinstance(perf, list):
        return []
    return [r for r in perf if isinstance(r, dict) and not r.get("erreur")]


def meta_crawl(audit):
    return (charger(Path(audit) / "data/crawl/pages.json") or {}).get("meta", {})


def _signal(sev, domaine, texte, exemples, source, cle):
    """source ∈ {crawl, rendu, domaine, terrain, geo, code, http, securite, lighthouse, projet} ; cle identifie le constat dans sa source
    (crawl : clé d'issue ; geo : texte du signal ; code : texte du constat ; http/securite/projet : ligne brute
    du fichier ; lighthouse : « <id> <titre> » ou titre de l'échec). Sert à associer les fiches de correction."""
    return {"severite": sev, "domaine": domaine, "texte": texte, "exemples": list(exemples), "source": source, "cle": cle}


def collecter(audit):
    audit = Path(audit)
    d = audit / "data"
    signals = []

    # Sources au format du crawl : {clé: {label, severity, count, examples, domaine?}} ; « domaine » remplace le défaut de la source
    for source, rel, dom_defaut in SOURCES_ISSUES:
        for k, it in (charger(d / rel) or {}).items():
            signals.append(_signal(it["severity"], it.get("domaine") or dom_defaut, f"{it['label']} — {it['count']}",
                                   [ex_str(e) for e in it["examples"][:5]], source, k))

    geo = charger(d / "geo/geo.json") or {}
    for s in geo.get("signaux", []):
        signals.append(_signal(s["severite"], "GEO / IA", s["constat"], [], "geo", s["constat"]))

    code = charger(d / "code/code-scan.json") or {}
    for f in code.get("constats", []):
        signals.append(_signal(f["severite"], _DOMAINES_CODE.get(f["categorie"], "Code"),
                               f["constat"] + (f" → {f['piste']}" if f["piste"] else ""), f["ou"][:5],
                               "code", f["constat"]))

    seen = set()
    for r in lighthouse(audit):
        for o in r.get("opportunites", [])[:6]:
            key = o["id"]
            if key in seen or not (o.get("gain_ms") or o.get("gain_octets")):
                continue
            seen.add(key)
            sev = severite_opportunite(o.get("gain_ms"), o.get("gain_octets"))
            gain = " + ".join(g for g in (f"{o['gain_ms']} ms" if o.get("gain_ms") else "",
                                          f"{int(o['gain_octets']) // 1024} Ko" if o.get("gain_octets") else "") if g)
            signals.append(_signal(sev, "Performance", f"{o['titre']} (gain estimé {gain}, {r.get('strategie')})", o.get("exemples", [])[:3],
                                   "lighthouse", f"{o['id']} {o['titre']}"))
        for cat, fails in (r.get("echecs_autres_categories") or {}).items():
            for f in fails:
                key = cat + f
                if key not in seen:
                    seen.add(key)
                    signals.append(_signal("moyenne", "Accessibilité" if cat == "accessibility" else "SEO technique" if cat == "seo" else "Bonnes pratiques",
                                           f"Lighthouse : {f}", [], "lighthouse", f))

    for path, dom_name, source in ((d / "securite/security-probe.md", "Sécurité", "securite"), (d / "http/http-checks.md", "Serveur / HTTP", "http")):
        if path.exists():
            # « > ⚠️ TLS non vérifié (mode test AUDIT_INSECURE_TLS=1) » : avis du mode test de l'audit, pas un constat sur le site
            lignes = [l for l in path.read_text(encoding="utf-8").splitlines() if not ("mode test" in l and "AUDIT_INSECURE_TLS" in l)]
            source_signals = []
            for line in lignes:
                if "❌" in line:
                    source_signals.append(_signal("haute", dom_name, line.strip("| ").replace(" | ", " · ")[:220], [], source, line.strip()))
                elif "⚠️" in line and line.startswith("|"):
                    source_signals.append(_signal("basse", dom_name, line.strip("| ").replace(" | ", " · ")[:220], [], source, line.strip()))
            # Avertissements ⚠️ hors tableau (puces « - ⚠️ … », citations « > ⚠️ … », lignes en gras, « - TLS 1.0 : ⚠️ … »), même sévérité
            # que ceux des tableaux. Ignorés : titres (#), lignes ✅ (légendes, verdicts favorables), doublons d'un constat déjà signalé
            # par une ligne de tableau ou une puce précédente (même texte, préfixe compris).
            for line in lignes:
                brute = line.strip()
                if "⚠️" not in brute or "❌" in brute or "✅" in brute or brute.startswith(("|", "#")):
                    continue
                texte = brute.lstrip("->* ").replace("**", "")[:220]
                message = brute.lstrip("->* ").rstrip("| ")  # « ⚠️ msg » ou « TLS 1.0 : ⚠️ msg » : le préfixe distingue les puces
                if any(message in s["cle"] for s in source_signals):
                    continue
                source_signals.append(_signal("basse", dom_name, texte, [], source, brute))
            signals.extend(source_signals)

    # Santé du projet (project_checks.sh) : lignes ❌ / ⚠️ et vulnérabilités critical/high/moderate.
    path = d / "code/project-checks.md"
    if path.exists():
        majeurs = []  # lignes du tableau « Dépendances obsolètes » avec saut de version majeure : un seul signal agrégé
        for line in path.read_text(encoding="utf-8").splitlines():
            brute = line.strip()
            if brute.startswith("|") and "⚠️ oui" in brute:
                majeurs.append(brute)
                continue
            sev = next((v for m, v in _VULN.items() if brute.startswith(m)), None) or ("haute" if "❌" in line else "basse" if "⚠️" in line else None)
            if sev:
                texte = brute.strip("| ").lstrip("- ").rstrip("| ").replace(" | ", " · ").replace("**", "")[:220]
                signals.append(_signal(sev, "Code", texte, [], "projet", brute))
        if majeurs:
            noms = [m.strip("| ").split("|")[0].strip() for m in majeurs]
            reste = len(noms) - 10
            liste = ", ".join(noms[:10]) + (f", … et {reste} autres" if reste > 0 else "")
            exemples = [m.strip("| ").replace(" | ", " · ") for m in majeurs[:10]] + ([f"… et {reste} autres"] if reste > 0 else [])
            signals.append(_signal("basse", "Code", f"{len(noms)} dépendance(s) avec saut de version majeure : {liste}", exemples,
                                   "projet", "dépendances obsolètes saut majeur : " + ", ".join(noms)))

    signals.sort(key=lambda s: (ORDRE.get(s["severite"], 9), s["domaine"]))
    return signals
