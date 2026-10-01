#!/usr/bin/env python3
"""
crux.py — Données terrain Chrome UX Report (p75 des vrais visiteurs, 28 jours) et tendance (historique hebdomadaire).

Usage : python3 crux.py --out DOSSIER --origine https://site.fr [--urls-file urls.txt] [--max-urls 5]
Clé : CRUX_API_KEY (gratuite, console Google Cloud, API « Chrome UX Report »), à défaut PSI_API_KEY. Sans clé : ⏭️.
Sorties : DOSSIER/issues.json (source « terrain »), crux.json, crux.md.

La clé n'est jamais écrite : lue dans l'environnement (jamais en argument), envoyée uniquement dans l'en-tête
« X-Goog-Api-Key » (jamais dans l'adresse), absente de toute sortie et de tout message d'erreur (« key=*** » si elle apparaît).

API (developer.chrome.com/docs/crux/api et /history-api) : POST records:queryRecord et records:queryHistoryRecord, corps
{"origin"|"url": …, "formFactor": "PHONE"|"DESKTOP"} (sans formFactor : tous appareils) ; p75 en entiers (ms) sauf CLS (chaîne) ;
historique : percentilesTimeseries.p75s, du plus ancien au plus récent, None quand la période n'a pas de données.
404 « chrome ux report data not found » = pas assez de trafic : info, jamais erreur.
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
ENTETE_CLE = "X-Goog-Api-Key"
METRIQUES = (("largest_contentful_paint", "LCP", 2500, 4000), ("interaction_to_next_paint", "INP", 200, 500),
             ("cumulative_layout_shift", "CLS", 0.1, 0.25), ("first_contentful_paint", "FCP", 1800, 3000),
             ("experimental_time_to_first_byte", "TTFB", 800, 1800))
_LABELS = {nom: label for nom, label, _, _ in METRIQUES}
PLANCHER_HAUSSE = {"LCP": 500, "INP": 100, "CLS": 0.05, "FCP": 300, "TTFB": 300}  # hausse absolue minimale (même catégorie)
FENETRE = 4        # périodes comparées : moyenne des 4 dernières contre les 4 précédentes
SEV = {"mauvais": "haute", "à améliorer": "moyenne"}
APPAREILS = (("tous", None, "tous appareils"), ("mobile", "PHONE", "mobile"), ("ordinateur", "DESKTOP", "ordinateur"))
DELAI_S = 8        # délai court par requête
PAUSE_S = 0.5      # pause entre deux requêtes (quota Google : 150 requêtes/minute/projet)
BUDGET_S = 60      # temps réseau total maximal ; au-delà, les cibles restantes sont passées (⏭️)
STOP = (401, 403, 429)  # clé refusée ou quota : inutile d'insister (un 400 sur une page n'arrête rien)
SEV_PLAFOND_MOYENNE = ("FCP", "TTFB")  # ni FCP ni TTFB ne sont des Core Web Vitals : jamais au-dessus de « moyenne »
_CLE_DANS_TEXTE = re.compile(r"(?i)\bkey=[^&\s'\"]*")
_CODE = re.compile(r"[A-Z_]{3,60}")


class _SansRedirection(urllib.request.HTTPRedirectHandler):
    """Ne suit aucune redirection : urllib recopie les en-têtes de la requête (donc X-Goog-Api-Key) vers la nouvelle cible.
    Une 3xx remonte comme erreur HTTP (statut 3xx), traitée en ⏭️."""

    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_SansRedirection)


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


def _categorie(label, p):
    """0 = bon, 1 = à améliorer, 2 = mauvais (seuils web.dev)."""
    for _, lab, bon, mauvais in METRIQUES:
        if lab == label:
            return 0 if p <= bon else 1 if p <= mauvais else 2
    return 0


def analyser_record(record):
    out = {}
    for nom, label, bon, mauvais in METRIQUES:
        p = _nombre((((record or {}).get("metrics") or {}).get(nom) or {}).get("percentiles", {}).get("p75"))
        if p is None:
            continue
        out[label] = {"p75": p, "verdict": "bon" if p <= bon else "à améliorer" if p <= mauvais else "mauvais"}
    return out


def analyser_historique(historique):
    """{"LCP": {"avant", "apres", "pct", "age_semaines", "degradation"}, …} pour chaque métrique ayant au moins 2 périodes valides.
    avant / apres = moyennes des 4 périodes valides précédentes / des 4 dernières (moins si la série est courte) ; les périodes
    vides finales sont écartées (age_semaines = leur nombre : ancienneté du dernier point) ; pct est None si la base vaut 0.
    degradation : jamais pour un « bon » ; sinon changement de catégorie vers pire, ou hausse absolue ≥ PLANCHER_HAUSSE."""
    out = {}
    for nom, label, _, _ in METRIQUES:
        brut = (((historique or {}).get("metrics") or {}).get(nom) or {}).get("percentilesTimeseries", {}).get("p75s", [])
        valeurs = [_nombre(x) for x in brut]
        age = 0
        while valeurs and valeurs[-1] is None:
            valeurs.pop()
            age += 1
        serie = [v for v in valeurs if v is not None]
        if len(serie) < 2:
            continue
        k = min(FENETRE, len(serie) // 2)
        apres, avant = sum(serie[-k:]) / k, sum(serie[-2 * k:-k]) / k
        cat_apres, cat_avant = _categorie(label, apres), _categorie(label, avant)
        hausse = round(apres - avant, 6)
        out[label] = {"avant": round(avant, 3), "apres": round(apres, 3),
                      "pct": round((apres - avant) / avant * 100, 1) if avant else None, "age_semaines": age,
                      "degradation": cat_apres > 0 and (cat_apres > cat_avant or hausse >= PLANCHER_HAUSSE[label])}
    return out


def tendances_depuis(analyse):
    return {k: round(v["pct"]) for k, v in analyse.items() if v["pct"] is not None}


def tendances(historique):
    """{"LCP": +19, …} : variation en % (moyenne des 4 dernières périodes contre les 4 précédentes), sans les bases nulles."""
    return tendances_depuis(analyser_historique(historique))


def _assainir(valeur, cle):
    """Masque la clé dans toutes les chaînes d'une réponse (Google recopie parfois l'adresse demandée dans ses messages)."""
    if isinstance(valeur, str):
        return masquer_cle(valeur, cle)
    if isinstance(valeur, list):
        return [_assainir(v, cle) for v in valeur]
    if isinstance(valeur, dict):
        return {k: _assainir(v, cle) for k, v in valeur.items()}
    return valeur


def _json(octets, cle=None):
    try:
        donnees = json.loads(octets)
    except ValueError:
        return {}
    return _assainir(donnees, cle) if isinstance(donnees, dict) else {}


def transport_http(url, corps, entetes=None):
    """POST JSON ; retourne (statut, dict). Statut 0 = réseau indisponible. La clé est dans `entetes` (jamais dans l'adresse) ;
    ni l'adresse ni le texte des exceptions ne sont conservés, seul le JSON assaini de la réponse revient."""
    entetes = dict(entetes or {})
    cle = entetes.get(ENTETE_CLE)
    entetes["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=json.dumps(corps).encode(), headers=entetes, method="POST")
    try:
        with _OPENER.open(req, timeout=DELAI_S) as r:
            return r.status, _json(r.read(2_000_000), cle)
    except urllib.error.HTTPError as e:
        try:
            return e.code, _json(e.read(200_000), cle)
        except Exception:
            return e.code, {}
    except Exception:
        return 0, {}


def _appel(corps, cle, historique, transport):
    url = API + ("queryHistoryRecord" if historique else "queryRecord")
    return (transport or transport_http)(url, corps, {ENTETE_CLE: cle})


def interroger(corps, cle, historique=False, transport=None):
    """Retourne (statut HTTP, record ou None). La clé part dans l'en-tête X-Goog-Api-Key, jamais dans l'adresse."""
    statut, donnees = _appel(corps, cle, historique, transport)
    return statut, (donnees or {}).get("record")


def _periode(record):
    p = (record or {}).get("collectionPeriod") or {}
    try:
        return "/".join("%04d-%02d-%02d" % (p[k]["year"], p[k]["month"], p[k]["day"]) for k in ("firstDate", "lastDate"))
    except (KeyError, TypeError):
        return None


def _severite(label, verdict):
    return "moyenne" if label in SEV_PLAFOND_MOYENNE else SEV[verdict]


def construire_issues(resultats):
    issues = {}
    for r in resultats:
        for label, m in sorted((r.get("metriques") or {}).items()):
            if m["verdict"] in SEV:
                it = issues.setdefault("terrain_" + label.lower(), {"label": f"{label} terrain (p75 CrUX) à améliorer ou mauvais",
                                                                     "severity": _severite(label, m["verdict"]), "count": 0,
                                                                     "examples": [], "domaine": "Performance"})
                if _severite(label, m["verdict"]) == "haute":
                    it["severity"] = "haute"
                it["count"] += 1
                it["examples"].append({"portee": r["portee"], "appareil": r.get("appareil"), "cible": r["cible"],
                                       "p75": m["p75"], "verdict": m["verdict"]})
        hausses = {k: {"avant": v["avant"], "apres": v["apres"], "pct": v["pct"]}
                   for k, v in sorted((r.get("historique") or {}).items()) if v.get("degradation")}
        if hausses:
            it = issues.setdefault("terrain_degradation", {"label": "Dégradation des métriques terrain sur l'historique CrUX",
                                                           "severity": "moyenne", "count": 0, "examples": [], "domaine": "Performance"})
            it["count"] += 1
            it["examples"].append({"appareil": r.get("appareil"), "cible": r["cible"], "variations": hausses})
    return issues


def _decouper(adresse):
    """(schéma, hôte[:port non standard]) en minuscules, ou None si ce n'est pas une adresse http(s) avec hôte."""
    try:
        p = urllib.parse.urlsplit(str(adresse).strip())
        hote, port = p.hostname, p.port
    except ValueError:
        return None
    schema = p.scheme.lower()
    if schema not in ("http", "https") or not hote:
        return None
    if ":" in hote:
        hote = f"[{hote}]"
    if port and port != (443 if schema == "https" else 80):
        hote += f":{port}"
    return schema, hote, p.path


def _origine_propre(origine):
    d = _decouper(origine)
    return f"{d[0]}://{d[1]}" if d else ""


def _url_exacte(adresse):
    """Adresse exacte de la page, sans identifiants, requête ni fragment (rien de secret envoyé), jamais tronquée."""
    d = _decouper(adresse)
    return f"{d[0]}://{d[1]}{d[2] or '/'}" if d else ""


def _cibles(origine, urls):
    """[(portée, adresse exacte envoyée à CrUX, adresse à écrire)] : l'origine, puis les pages du même site sans doublon.
    Liste vide si l'origine est invalide."""
    base = _origine_propre(origine)
    if not base:
        return []
    cibles, vus = [("origine", base, html_observateurs.url_sans_secret(base))], {base}
    for u in urls:
        exacte = _url_exacte(u)
        if not exacte or exacte in vus or _origine_propre(exacte) != base:
            continue
        vus.add(exacte)
        cibles.append(("url", exacte, html_observateurs.url_sans_secret(exacte)))
    return cibles


def _limiter(origine, urls, maximum):
    """Les `maximum` premières pages du même site (les adresses d'autres hôtes ne comptent pas dans la limite)."""
    return [u for _, u, _ in _cibles(origine, urls)[1:]][:max(maximum, 0)]


def _erreur(donnees):
    """(état Google, raison) : codes en majuscules uniquement (« PERMISSION_DENIED », « API_KEY_INVALID »…) ; le message libre
    n'est jamais recopié."""
    err = (donnees or {}).get("error") or {}
    etat = err.get("status") if isinstance(err.get("status"), str) and _CODE.fullmatch(err["status"]) else None
    raison = None
    for detail in err.get("details") or []:
        r = detail.get("reason") if isinstance(detail, dict) else None
        if isinstance(r, str) and _CODE.fullmatch(r):
            raison = r
            break
    return etat, raison


def _arret(statut, raison):
    """Clé refusée, API non activée, clé restreinte ou quota : inutile d'interroger les cibles suivantes."""
    return statut in STOP or bool(raison and (raison.startswith("API_KEY_") or raison == "SERVICE_DISABLED"))


def _ligne_non_lue(cible, statut, donnees, appareil):
    etat, raison = _erreur(donnees)
    if statut == 404:
        suffixe = "pas assez de trafic pour CrUX (HTTP 404)" if appareil == "tous" else "pas assez de trafic sur cet appareil (HTTP 404)"
        return f"- ⏭️ {cible}" + ("" if appareil == "tous" else f" ({appareil})") + f" : {suffixe}"
    quand = "" if appareil == "tous" else f" ({appareil})"
    if statut == 0:
        return f"- ⏭️ {cible}{quand} : API CrUX injoignable, données terrain non lues"
    if raison == "API_KEY_INVALID":
        conseil = " ; clé invalide : vérifier CRUX_API_KEY"
    elif raison == "SERVICE_DISABLED":
        conseil = " ; l'API « Chrome UX Report » n'est pas activée pour ce projet Google Cloud"
    elif raison and raison.startswith("API_KEY_"):
        conseil = " ; clé restreinte (API ou origine non autorisée)"
    elif statut == 429:
        conseil = " ; quota atteint, réessayer plus tard"
    elif 300 <= statut < 400:
        conseil = " ; redirection refusée (la clé n'est jamais envoyée ailleurs)"
    elif statut in (401, 403):
        conseil = " ; clé refusée : vérifier la clé et l'activation de l'API"
    else:
        conseil = ""
    code = ", ".join(x for x in (etat,) if x)
    return f"- ⏭️ {cible}{quand} : données terrain non lues (HTTP {statut}" + (f", {code}" if code else "") + ")" + conseil


def _ligne_resultat(r):
    h = r["historique"]
    tend = tendances_depuis(h)
    degr = [f"{k} {v['avant']:g} → {v['apres']:g}" for k, v in sorted(h.items()) if v["degradation"]]
    age = max([v["age_semaines"] for v in h.values()] or [0])
    libelle = dict((a, lab) for a, _, lab in APPAREILS)[r["appareil"]]
    return (f"- {r['cible']} ({r['portee']}, {libelle}) : "
            + (", ".join(f"{k} {v['p75']} ({v['verdict']})" for k, v in r["metriques"].items()) or "aucune métrique")
            + (f" ; période {r['periode']}" if r["periode"] else "")
            + (" ; tendance : " + ", ".join(f"{k} {v:+d} %" for k, v in sorted(tend.items())) if tend else "")
            + (" ; dégradation : " + ", ".join(degr) if degr else "")
            + (f" ; historique : dernier point il y a {age} semaine{'s' if age > 1 else ''}" if age else ""))


def collecter(origine, urls, cle, dossier, transport=None):
    d = Path(dossier)
    d.mkdir(parents=True, exist_ok=True)
    resultats, lignes = [], ["# Données terrain (Chrome UX Report)", ""]
    if not cle:
        lignes.append("- ⏭️ pas de clé CrUX (CRUX_API_KEY) : données terrain non lues")
    elif not _origine_propre(origine):
        lignes.append("- ⏭️ origine invalide (attendu https://hôte) : aucune requête envoyée")
    else:
        pause = 0 if transport else PAUSE_S
        debut, premiere = time.monotonic(), True

        def requete(corps, historique=False):
            nonlocal premiere
            if not premiere:
                time.sleep(pause)
            premiere = False
            return _appel(corps, cle, historique, transport)

        cibles = _cibles(origine, urls)
        for i, (portee, cible, affichage) in enumerate(cibles):
            if not transport and time.monotonic() - debut > BUDGET_S:
                lignes.append(f"- ⏭️ {affichage} : budget de temps réseau épuisé")
                continue
            arret = False
            for appareil, facteur, _ in APPAREILS:
                corps = {"origin" if portee == "origine" else "url": cible}
                if facteur:
                    corps["formFactor"] = facteur
                statut, donnees = requete(corps)
                record = (donnees or {}).get("record")
                if statut != 200 or not record:
                    lignes.append(_ligne_non_lue(affichage, statut, donnees, appareil))
                    arret = _arret(statut, _erreur(donnees)[1])
                    if arret or appareil == "tous":
                        break  # agrégat absent : chaque appareil a moins d'échantillons, inutile de les ventiler
                    continue
                statut_h, donnees_h = requete(dict(corps), historique=True)
                r = {"portee": portee, "appareil": appareil, "cible": affichage, "metriques": analyser_record(record),
                     "historique": analyser_historique((donnees_h or {}).get("record") or {}), "periode": _periode(record)}
                r["tendances"] = tendances_depuis(r["historique"])
                resultats.append(r)
                lignes.append(_ligne_resultat(r))
                if _arret(statut_h, _erreur(donnees_h)[1]):
                    arret = True
                    lignes.append(_ligne_non_lue(affichage, statut_h, donnees_h, appareil))
                    break
            if arret:
                lignes.append("- ⏭️ interruption : clé refusée, API non activée ou quota atteint ; les cibles suivantes ne sont pas "
                              "interrogées")
                lignes += [f"- ⏭️ {aff} : non interrogée (interruption : clé refusée, API non activée ou quota atteint)"
                           for _, _, aff in cibles[i + 1:]]
                break
    sortie = masquer_cle("\n".join(lignes) + "\n", cle)
    (d / "issues.json").write_text(json.dumps(construire_issues(resultats), ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    (d / "crux.json").write_text(json.dumps(resultats, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    (d / "crux.md").write_text(sortie, encoding="utf-8")
    return sortie


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
