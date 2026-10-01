#!/usr/bin/env python3
"""
score.py — Compare les sorties de l'audit à la vérité terrain du cobaye.

  python3 tests/cobaye/score.py --casse audits-cobaye/casse --propre audits-cobaye/propre --phase 1 \
      [--sortie audits-cobaye] [--resume "$GITHUB_STEP_SUMMARY"]

Rappel = défauts requis (phase ≤ N) détectés sur le cobaye cassé.
Faux positifs = matchers qui se déclenchent sur le jumeau propre (sauf "propre": "ignorer").
  Sur le propre, les filtres d'emplacement propres au cassé (contient / ou_contient / exemple_contient)
  sont retirés : la seule présence de la détection (clé du crawl, regex du code ou de Lighthouse) compte.
  Un défaut peut fournir un "matcher_propre" explicite, utilisé tel quel à la place.
Inattendus = constats Critique/Haute du jumeau propre (issues.json de crawl, rendu, domaine, terrain + code) : à examiner.

Codes de sortie : 0 = seuils respectés ; 1 = seuil violé ; 2 = audit invalide (collecte incomplète, fichiers manquants).
"""
import argparse
import json
import re
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
SEVERES = {"critique", "haute"}


def _json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def _texte(p):
    try:
        return Path(p).read_text(encoding="utf-8")
    except Exception:
        return ""


def detecte(matcher, audit):
    """True/False selon que la détection est présente dans les sorties ; None pour un défaut couvert par tests unitaires."""
    t = matcher["type"]
    data = Path(audit) / "data"
    if t == "unitaire":
        return None
    if t == "crawl_issue":
        # « fichier » : autre source au format du crawl (rendu/issues.json, domaine/issues.json, terrain/issues.json)
        it = (_json(data / matcher.get("fichier", "crawl/issues.json")) or {}).get(matcher["cle"])
        if not it:
            return False
        c = matcher.get("contient")
        return c is None or c in json.dumps(it.get("examples", []), ensure_ascii=False)
    if t == "code":
        rx = re.compile(matcher["regex"], re.I)
        ou = matcher.get("ou_contient")
        for f in (_json(data / "code/code-scan.json") or {}).get("constats", []):
            if rx.search(f.get("constat", "")) and (not ou or any(ou in w for w in f.get("ou", []))):
                return True
        return False
    if t == "geo_signal":
        rx = re.compile(matcher["regex"], re.I)
        return any(rx.search(s.get("constat", "")) for s in (_json(data / "geo/geo.json") or {}).get("signaux", []))
    if t == "texte":
        return re.search(matcher["regex"], _texte(data / matcher["fichier"]), re.I | re.M) is not None
    if t == "lighthouse":
        rx = re.compile(matcher["regex"], re.I)
        ex = matcher.get("exemple_contient")
        for r in _json(data / "perf/pagespeed.json") or []:
            for o in r.get("opportunites", []):
                if (rx.search(o.get("id", "")) or rx.search(o.get("titre", ""))) and \
                        (not ex or any(ex in e for e in o.get("exemples", []))):
                    return True
            if not ex:
                for echecs in (r.get("echecs_autres_categories") or {}).values():
                    if any(rx.search(e) for e in echecs):
                        return True
        return False
    raise ValueError("type de matcher inconnu : {0}".format(t))


FILTRES_CASSE = ("contient", "ou_contient", "exemple_contient")
FICHIERS_REQUIS = ("crawl/issues.json", "geo/geo.json", "code/code-scan.json", "perf/pagespeed.json")
FICHIERS_ISSUES = ("crawl/issues.json", "rendu/issues.json", "domaine/issues.json", "terrain/issues.json")


def matcher_propre(m):
    """Copie du matcher sans les filtres d'emplacement propres au jumeau cassé (chemins qui n'existent pas sur le propre).

    crawl_issue -> clé seule ; code / lighthouse -> regex seule ; texte et geo_signal inchangés."""
    return {k: v for k, v in m.items() if k not in FILTRES_CASSE}


def _matcher_fp(d):
    """Matcher évalué sur le jumeau propre : celui fourni explicitement, sinon le matcher dépouillé de ses filtres."""
    return d.get("matcher_propre") or matcher_propre(d["matcher"])


def valider_audit(audit, phase=0):
    """Liste des problèmes qui rendent un dossier d'audit inutilisable pour la mesure (vide = valide).
    À partir de la phase 2, la passe rendue (data/rendu/issues.json) est requise : un propre sans passe rendue
    passerait pour un propre sans faux positif d'accessibilité ou de RGPD."""
    audit = Path(audit)
    data = audit / "data"
    problemes = []
    collecte = data / "COLLECTE.md"
    if not collecte.is_file():
        problemes.append("data/COLLECTE.md manquant")
    else:
        for ligne in _texte(collecte).splitlines():
            if ligne.startswith("| "):
                cellules = ligne.split("|")
                if len(cellules) > 2 and "❌" in cellules[2]:
                    problemes.append("étape en échec dans COLLECTE.md : {0}".format(ligne.strip()))
    for rel in FICHIERS_REQUIS + (("rendu/issues.json",) if phase >= 2 else ()):
        if not (data / rel).is_file():
            problemes.append("data/{0} manquant".format(rel))
    # Un fichier d'issues vide, tronqué ou non-objet serait lu comme « aucun constat » : un propre illisible
    # passerait pour un propre sans faux positif. « {} » reste valide (aucun constat légitime).
    for rel in FICHIERS_ISSUES:
        if (data / rel).is_file() and not isinstance(_json(data / rel), dict):
            problemes.append("data/{0} illisible (JSON de type objet attendu)".format(rel))
    return problemes


def _phase(p):
    return 0 if p == "base" else int(p)


def _inattendus(propre):
    if propre is None:
        return []
    data = Path(propre) / "data"
    out = []
    for rel in FICHIERS_ISSUES:
        source = rel.split("/")[0]
        for cle, it in (_json(data / rel) or {}).items():
            if it.get("severity") in SEVERES:
                out.append({"source": source, "cle": cle, "constat": it.get("label", cle), "nb": it.get("count")})
    for f in (_json(data / "code/code-scan.json") or {}).get("constats", []):
        if f.get("severite") in SEVERES:
            out.append({"source": "code", "cle": f.get("categorie"), "constat": f.get("constat"), "nb": len(f.get("ou", []))})
    return out


def scorer(verite, casse, propre, phase):
    res = {"phase": phase, "par_domaine": {}, "rates": [], "faux_positifs": [], "futurs": [], "unitaires": [], "details": []}
    for d in verite["defauts"]:
        det = detecte(d["matcher"], casse)
        if det is None:
            res["unitaires"].append(d)
            continue
        requis = _phase(d["phase"]) <= phase
        fp = propre is not None and d.get("propre", "absent") == "absent" and bool(detecte(_matcher_fp(d), propre))
        res["details"].append(dict(list(d.items()) + [("detecte", det), ("requis", requis), ("faux_positif", fp)]))
        if fp:
            res["faux_positifs"].append(d)
        if not requis:
            res["futurs"].append(dict(list(d.items()) + [("detecte", det)]))
            continue
        dom = res["par_domaine"].setdefault(d["domaine"], {"requis": 0, "detectes": 0})
        dom["requis"] += 1
        dom["detectes"] += int(det)
        if not det:
            res["rates"].append(d)
    for dom in res["par_domaine"].values():
        dom["rappel"] = round(dom["detectes"] / dom["requis"], 3) if dom["requis"] else 1.0
    req = sum(v["requis"] for v in res["par_domaine"].values())
    det = sum(v["detectes"] for v in res["par_domaine"].values())
    res["global"] = {"requis": req, "detectes": det, "rappel": round(det / req, 3) if req else 1.0}
    res["inattendus"] = _inattendus(propre)
    return res


def verdict(r, seuils):
    v = []
    if r["global"]["rappel"] < seuils.get("rappel_min_global", 0):
        v.append("rappel global {0:.0%} < seuil {1:.0%}".format(r["global"]["rappel"], seuils["rappel_min_global"]))
    for dom, mini in seuils.get("rappel_min_par_domaine", {}).items():
        got = r["par_domaine"].get(dom, {}).get("rappel", 0)
        if got < mini:
            v.append("rappel {0} {1:.0%} < seuil {2:.0%}".format(dom, got, mini))
    if len(r["faux_positifs"]) > seuils.get("faux_positifs_max", 0):
        v.append("{0} faux positif(s) > {1}".format(len(r["faux_positifs"]), seuils.get("faux_positifs_max", 0)))
    if len(r["inattendus"]) > seuils.get("inattendus_max", 0):
        v.append("{0} constat(s) Critique/Haute inattendu(s) sur le jumeau propre > {1}".format(len(r["inattendus"]), seuils.get("inattendus_max", 0)))
    return v


def markdown(r, violations):
    g = r["global"]
    md = ["## Banc d'essai cobaye — phase {0}".format(r["phase"]), "",
          "**Rappel global : {0}/{1} ({2:.0%})** · faux positifs : {3} · inattendus (propre) : {4}".format(
              g["detectes"], g["requis"], g["rappel"], len(r["faux_positifs"]), len(r["inattendus"])), "",
          "| Domaine | Détectés | Rappel |", "|---|---|---|"]
    for dom, v in sorted(r["par_domaine"].items()):
        md.append("| {0} | {1}/{2} | {3:.0%} |".format(dom, v["detectes"], v["requis"], v["rappel"]))
    md += ["", "### Ratés", ""] + ([("- **{0}** ({1}) — {2}".format(d["id"], d["domaine"], d["titre"])) for d in r["rates"]] or ["- aucun 🎉"])
    md += ["", "### Faux positifs (jumeau propre)", ""] + ([("- **{0}** — {1}".format(d["id"], d["titre"])) for d in r["faux_positifs"]] or ["- aucun"])
    md += ["", "### Constats Critique/Haute inattendus sur le jumeau propre", ""] + \
          ([("- [{0}] {1}".format(i["source"], i["constat"])) for i in r["inattendus"]] or ["- aucun"])
    fut = [d for d in r["futurs"]]
    if fut:
        md += ["", "### Défauts des phases suivantes", ""] + \
              [("- {0} (phase {1}) — {2}".format(d["id"], d["phase"], ("déjà détecté ✅" if d["detecte"] else "pas encore"))) for d in fut]
    md += ["", "### Verdict", ""] + ([("- ❌ {0}".format(x)) for x in violations] or ["- ✅ seuils respectés"])
    return "\n".join(md) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--casse", required=True)
    ap.add_argument("--propre")
    ap.add_argument("--phase", type=int, default=0)
    ap.add_argument("--verite", default=str(ICI / "verite-terrain.json"))
    ap.add_argument("--seuils", default=str(ICI / "seuils.json"))
    ap.add_argument("--sortie")
    ap.add_argument("--resume")
    a = ap.parse_args()
    invalides = []
    for nom, chemin in (("casse", a.casse), ("propre", a.propre)):
        if chemin:
            invalides += ["[{0}] {1}".format(nom, p) for p in valider_audit(chemin, a.phase)]
    if invalides:
        print("❌ Audit invalide : impossible de mesurer.\n" + "\n".join("  - " + p for p in invalides), file=sys.stderr)
        sys.exit(2)
    r = scorer(_json(a.verite), Path(a.casse), Path(a.propre) if a.propre else None, a.phase)
    violations = verdict(r, _json(a.seuils) or {})
    md = markdown(r, violations)
    if a.sortie:
        Path(a.sortie).mkdir(parents=True, exist_ok=True)
        Path(a.sortie, "resultats.json").write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        Path(a.sortie, "resultats.md").write_text(md, encoding="utf-8")
    if a.resume:
        with open(a.resume, "a", encoding="utf-8") as f:
            f.write(md)
    print(md)
    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
