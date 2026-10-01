#!/usr/bin/env python3
"""
crux.py — Données terrain Chrome UX Report (p75 des vrais visiteurs, 28 jours) et tendance (historique hebdomadaire).

Usage : python3 crux.py --out DOSSIER --origine https://site.fr [--urls-file urls.txt] [--max-urls 5]
Clé : CRUX_API_KEY (gratuite, console Google Cloud, API « Chrome UX Report »), à défaut PSI_API_KEY. Sans clé : ⏭️.
Sorties : DOSSIER/issues.json (source « terrain »), crux.json, crux.md. La clé n'est jamais écrite : lue dans l'environnement
(jamais en argument), absente de toute sortie, de tout message d'erreur et de toute adresse affichée (« key=*** »).

API (developer.chrome.com/docs/crux/api et /history-api) : POST records:queryRecord et records:queryHistoryRecord, corps
{"origin"|"url": …, "formFactor": "PHONE"} ; p75 en entiers (ms) sauf CLS (chaîne) ; historique : percentilesTimeseries.p75s
(None quand la période n'a pas de données). 404 « chrome ux report data not found » = pas assez de trafic : info, jamais erreur.
"""
import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import html_observateurs  # noqa: E402

API = "https://chromeuxreport.googleapis.com/v1/records:"
METRIQUES = (("largest_contentful_paint", "LCP", 2500, 4000), ("interaction_to_next_paint", "INP", 200, 500),
             ("cumulative_layout_shift", "CLS", 0.1, 0.25), ("first_contentful_paint", "FCP", 1800, 3000),
             ("experimental_time_to_first_byte", "TTFB", 800, 1800))
SEV = {"mauvais": "haute", "à améliorer": "moyenne"}
FORM_FACTOR = "PHONE"
DELAI_S = 8        # délai court par requête
PAUSE_S = 0.5      # pause entre deux requêtes (quota Google : 150 requêtes/minute/projet)
BUDGET_S = 60      # temps réseau total maximal ; au-delà, les cibles restantes sont passées (⏭️)
STOP = (400, 401, 403, 429)  # clé refusée, API non activée ou quota : inutile d'insister
_CLE_DANS_TEXTE = re.compile(r"(?i)\bkey=[^&\s'\"]*")


def masquer_cle(texte, cle=None):
    """Masque `key=…` et la valeur de la clé dans un texte destiné à être affiché ou écrit (message d'erreur HTTP, adresse…)."""
    texte = _CLE_DANS_TEXTE.sub("key=***", str(texte))
    return texte.replace(cle, "***") if cle else texte


def cle_depuis_environnement():
    """CRUX_API_KEY, à défaut PSI_API_KEY (même clé Google si l'API « Chrome UX Report » y est activée) ; None si absente."""
    for nom in ("CRUX_API_KEY", "PSI_API_KEY"):
        valeur = (os.environ.get(nom) or "").strip()
        if valeur:
            return valeur
    return None


def _nombre(v):
    """Nombre ou None : CrUX renvoie le CLS en chaîne ; None / « NaN » = période sans données."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        n = float(v) if isinstance(v, str) else v
        return None if isinstance(n, float) and math.isnan(n) else (n if isinstance(n, (int, float)) else None)
    except ValueError:
        return None


def analyser_record(record):
    out = {}
    for nom, label, bon, mauvais in METRIQUES:
        p = _nombre((((record or {}).get("metrics") or {}).get(nom) or {}).get("percentiles", {}).get("p75"))
        if p is None:
            continue
        out[label] = {"p75": p, "verdict": "bon" if p <= bon else "à améliorer" if p <= mauvais else "mauvais"}
    return out


def tendances(historique):
    out = {}
    for nom, label, _, _ in METRIQUES:
        brut = (((historique or {}).get("metrics") or {}).get(nom) or {}).get("percentilesTimeseries", {}).get("p75s", [])
        serie = [n for n in (_nombre(x) for x in brut) if n is not None]
        if len(serie) >= 2 and serie[0]:
            out[label] = round((serie[-1] - serie[0]) / serie[0] * 100)
    return out


def transport_http(url, corps):
    """POST JSON ; retourne (statut, dict). Statut 0 = réseau indisponible. Ni l'adresse (elle porte la clé) ni le texte de
    l'exception ne sont conservés ; seul le JSON de la réponse revient."""
    req = urllib.request.Request(url, data=json.dumps(corps).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=DELAI_S) as r:
            return r.status, _json(r.read(2_000_000), url)
    except urllib.error.HTTPError as e:
        try:
            return e.code, _json(e.read(200_000), url)
        except Exception:
            return e.code, {}
    except Exception:
        return 0, {}


def _assainir(valeur, cle):
    """Masque la clé dans toutes les chaînes d'une réponse (Google recopie parfois l'adresse demandée dans ses messages)."""
    if isinstance(valeur, str):
        return masquer_cle(valeur, cle)
    if isinstance(valeur, list):
        return [_assainir(v, cle) for v in valeur]
    if isinstance(valeur, dict):
        return {k: _assainir(v, cle) for k, v in valeur.items()}
    return valeur


def _json(octets, url=""):
    try:
        donnees = json.loads(octets)
    except ValueError:
        return {}
    cle = (urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get("key") or [None])[0]
    return _assainir(donnees, cle) if isinstance(donnees, dict) else {}


def _appel(corps, cle, historique, transport):
    # La clé voyage dans l'adresse (méthode documentée) ; l'adresse n'est jamais écrite ni affichée.
    url = API + ("queryHistoryRecord" if historique else "queryRecord") + "?key=" + urllib.parse.quote(cle, safe="")
    return (transport or transport_http)(url, corps)


def interroger(corps, cle, historique=False, transport=None):
    """Retourne (statut HTTP, record ou None)."""
    statut, donnees = _appel(corps, cle, historique, transport)
    return statut, (donnees or {}).get("record")


def _periode(record):
    p = (record or {}).get("collectionPeriod") or {}
    try:
        return "/".join("%04d-%02d-%02d" % (p[k]["year"], p[k]["month"], p[k]["day"]) for k in ("firstDate", "lastDate"))
    except (KeyError, TypeError):
        return None


def construire_issues(resultats):
    issues = {}
    for r in resultats:
        for label, m in sorted((r.get("metriques") or {}).items()):
            if m["verdict"] in SEV:
                it = issues.setdefault("terrain_" + label.lower(), {"label": f"{label} terrain (p75 CrUX) à améliorer ou mauvais",
                                                                     "severity": SEV[m["verdict"]], "count": 0, "examples": [],
                                                                     "domaine": "Performance"})
                if SEV[m["verdict"]] == "haute":
                    it["severity"] = "haute"
                it["count"] += 1
                it["examples"].append({"portee": r["portee"], "cible": r["cible"], "p75": m["p75"], "verdict": m["verdict"]})
        hausses = {k: v for k, v in sorted((r.get("tendances") or {}).items()) if k in ("LCP", "INP", "CLS") and v > 10}
        if hausses:
            it = issues.setdefault("terrain_degradation", {"label": "Dégradation des Core Web Vitals terrain sur l'historique CrUX",
                                                           "severity": "moyenne", "count": 0, "examples": [], "domaine": "Performance"})
            it["count"] += 1
            it["examples"].append({"cible": r["cible"], "hausse_pct": hausses})
    return issues


def _origine_propre(origine):
    p = urllib.parse.urlsplit(html_observateurs.url_sans_secret(origine))
    return f"{p.scheme}://{p.netloc}".lower() if p.scheme and p.netloc else ""


def _cibles(origine, urls):
    """Origine puis pages du même site (sans requête ni fragment : rien de secret n'est envoyé ni écrit), sans doublon."""
    base = _origine_propre(origine)
    cibles, vus = [("origine", base)], {base}
    for u in urls:
        propre = html_observateurs.url_sans_secret(u)
        p = urllib.parse.urlsplit(propre)
        if propre in vus or f"{p.scheme}://{p.netloc}".lower() != base:
            continue
        vus.add(propre)
        cibles.append(("url", propre))
    return cibles


def _raison(donnees):
    """Code d'état Google (« PERMISSION_DENIED »…) uniquement ; le message libre n'est jamais recopié."""
    s = ((donnees or {}).get("error") or {}).get("status")
    return s if isinstance(s, str) and re.fullmatch(r"[A-Z_]{3,40}", s) else None


def _ligne_non_lue(cible, statut, raison):
    if statut == 404:
        return f"- ⏭️ {cible} : pas assez de trafic pour CrUX (HTTP 404)"
    if statut == 0:
        return f"- ⏭️ {cible} : API CrUX injoignable, données terrain non lues"
    suite = " ; réessayer plus tard" if statut == 429 else (
        " ; vérifier que l'API « Chrome UX Report » est activée pour cette clé" if statut in (400, 401, 403) else "")
    return f"- ⏭️ {cible} : données terrain non lues (HTTP {statut}" + (f", {raison}" if raison else "") + ")" + suite


def collecter(origine, urls, cle, dossier, transport=None):
    d = Path(dossier)
    d.mkdir(parents=True, exist_ok=True)
    resultats, lignes = [], ["# Données terrain (Chrome UX Report)", ""]
    if not cle:
        lignes.append("- ⏭️ pas de clé CrUX (CRUX_API_KEY) : données terrain non lues")
    else:
        pause = 0 if transport else PAUSE_S
        debut, premiere = time.monotonic(), True

        def requete(corps, historique=False):
            nonlocal premiere
            if not premiere:
                time.sleep(pause)
            premiere = False
            return _appel(corps, cle, historique, transport)

        for portee, cible in _cibles(origine, urls):
            if not transport and time.monotonic() - debut > BUDGET_S:
                lignes.append(f"- ⏭️ {cible} : budget de temps réseau épuisé")
                continue
            corps = {"origin" if portee == "origine" else "url": cible, "formFactor": FORM_FACTOR}
            statut, donnees = requete(corps)
            record = (donnees or {}).get("record")
            if statut != 200 or not record:
                lignes.append(_ligne_non_lue(cible, statut, _raison(donnees)))
                if statut in STOP:
                    break
                continue
            histo = (requete(dict(corps), historique=True)[1] or {}).get("record")
            r = {"portee": portee, "cible": cible, "metriques": analyser_record(record), "tendances": tendances(histo or {}),
                 "periode": _periode(record)}
            resultats.append(r)
            lignes.append(f"- {cible} ({portee}, mobile) : "
                          + (", ".join(f"{k} {v['p75']} ({v['verdict']})" for k, v in r["metriques"].items()) or "aucune métrique")
                          + (f" ; période {r['periode']}" if r["periode"] else "")
                          + (" ; tendance : " + ", ".join(f"{k} {v:+d} %" for k, v in sorted(r["tendances"].items()))
                             if r["tendances"] else ""))
    sortie = masquer_cle("\n".join(lignes) + "\n", cle)
    (d / "issues.json").write_text(json.dumps(construire_issues(resultats), ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    (d / "crux.json").write_text(json.dumps(resultats, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    (d / "crux.md").write_text(sortie, encoding="utf-8")
    return sortie


def _limiter(origine, urls, maximum):
    """Les `maximum` premières pages du même site (les adresses d'autres hôtes ne comptent pas dans la limite)."""
    return [u for _, u in _cibles(origine, urls)[1:]][:max(maximum, 0)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--origine", required=True)
    ap.add_argument("--urls-file")
    ap.add_argument("--max-urls", type=int, default=5)
    a = ap.parse_args()
    urls = []
    if a.urls_file and Path(a.urls_file).exists():
        with open(a.urls_file, encoding="utf-8") as f:
            urls = [l.strip() for l in f if l.strip().startswith("http")]
    print(collecter(a.origine, _limiter(a.origine, urls, a.max_urls), cle_depuis_environnement(), a.out), end="")


if __name__ == "__main__":
    main()
