#!/usr/bin/env python3
"""liens_externes.py — Liens externes cassés (Screaming Frog « External 4XX », Semrush « Broken external links »).
Module du diffuseur html_observateurs : Observateur (un passage par page), apres_crawl (réseau) puis issues(pages, add, ctx).

Réseau poli : HEAD d'abord, GET d'un octet (Range: bytes=0-0) si HEAD est refusé ou répond 404 / 410 (un serveur qui gère mal HEAD ne
doit pas faire passer un lien valide pour cassé : seul le GET conclut) ; une pause entre deux requêtes vers un même hôte (y compris
HEAD puis GET) ; 5 redirections au plus ; jamais de cookie ; un User-Agent qui dit qui on est ; délai court par requête (8 s) ; budget de
temps du crawl (ctx["budget_reseau_s"]) et plafond de liens (ctx["liens_externes_max"]) respectés. Les liens sont vérifiés par ordre
d'importance (nombre de pages qui les contiennent, puis ordre de première apparition), jamais tronqués par ordre alphabétique ; ce que le
plafond ou le budget laisse de côté est compté dans meta.liens_externes_non_verifies.
Cassé : 404, 410 (confirmés par un GET), nom de domaine inexistant. À vérifier, jamais cassé : 401, 403, 429, 999 (LinkedIn), 5xx, défi
Cloudflare, délai dépassé, redirections sans fin, toute autre erreur réseau (blocage des robots fréquent)."""
import inspect
import re
import time
from urllib.parse import urldefrag, urlsplit, urlunsplit

import html_observateurs as ho

NOM = "liens_externes"
MAX_PAR_PAGE = 200
MAX_REDIRECTIONS = 5
TIMEOUT_MAX = 8  # secondes, par requête
GET_APRES_HEAD = (403, 404, 405, 410, 501)  # HEAD mal géré par certains serveurs : le GET tranche (pas après un 429 : on ralentit)
UA_HONNETE = "AuditSiteAstro-LinkChecker/2.1 (verification de liens sortants; +https://github.com/ohvignas/audit-site-astro)"
DNS_INEXISTANT = re.compile(r"Name or service not known|nodename nor servname|No address associated|Errno -2\b|Errno 8\b|getaddrinfo failed", re.I)
DEFI = "défi Cloudflare"


def _nu(h):
    h = (h or "").lower()
    return h[4:] if h.startswith("www.") else h


def _sans_identifiants(u):
    """Adresse sans fragment ni user:pass@, schéma et hôte en minuscules : rien de secret n'est jamais envoyé ni noté."""
    p = urlsplit(urldefrag(u)[0])
    hote = p.netloc.rpartition("@")[2].lower()
    return urlunsplit((p.scheme.lower(), hote, p.path, p.query, "")), hote


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.hote, self.liens = urlsplit(url).netloc.rpartition("@")[2].lower(), {}

    def debut(self, noeud, pile):
        if noeud["tag"] != "a" or noeud["masque"]:
            return
        href = noeud["a"].get("href", "").strip()
        if not href.lower().startswith(("http://", "https://")):
            return
        u, hote = _sans_identifiants(href)
        if hote and _nu(hote) != _nu(self.hote):
            # la requête reste (une page dynamique se distingue par elle) mais sans paramètre qui ressemble à un secret
            self.liens.setdefault(ho.url_page_publique(u), None)

    def resultat(self):
        return {"externes": list(self.liens)[:MAX_PAR_PAGE]}  # ordre du document : le plafond ne favorise aucune lettre


def classer(statut, erreur):
    """« casse » | « a_verifier » | None (lien sain)."""
    if erreur and DEFI in erreur:
        return "a_verifier"
    if statut in (404, 410):
        return "casse"
    if statut is None or statut <= 0:
        return "casse" if erreur and DNS_INEXISTANT.search(erreur) else "a_verifier"
    if statut >= 400:
        return "a_verifier"
    return None


def _accepte(fetch, nom):
    try:
        ps = inspect.signature(fetch).parameters
    except (TypeError, ValueError):
        return False
    return nom in ps or any(p.kind == p.VAR_KEYWORD for p in ps.values())


def apres_crawl(pages, ctx):
    sources = {}  # lien -> pages qui le contiennent ; le dict garde l'ordre de première apparition
    hote_site = _nu(ctx.get("host"))
    for u, p in pages.items():
        for lien in ((p.get("obs") or {}).get(NOM) or {}).get("externes", []):
            if hote_site and _nu(urlsplit(lien).netloc.rpartition("@")[2]) == hote_site:
                continue  # le site lui-même (variantes www) n'est pas un lien externe
            vues = sources.setdefault(lien, [])
            if u not in vues:
                vues.append(u)
    ordre = sorted(sources, key=lambda lien: -len(sources[lien]))  # tri stable : à égalité, première apparition d'abord

    fetch, resultats, dernier = ctx["fetch"], {}, {}
    ua = ctx.get("ua_liens_externes") or UA_HONNETE  # volontairement pas ctx["ua_navigateur"] : on ne se fait pas passer pour un navigateur
    plafond, pause = max(0, ctx.get("liens_externes_max", 300)), ctx.get("delai_externe", 1.0)
    budget, timeout, t0 = ctx.get("budget_reseau_s", 300), min(ctx.get("timeout", 20), TIMEOUT_MAX), time.monotonic()
    options = {"max_hops": MAX_REDIRECTIONS + 1} if _accepte(fetch, "max_hops") else {}  # n requêtes = n - 1 redirections suivies

    def demander(lien, **kw):
        """Une requête, après la pause due à l'hôte ; None si la pause ou la requête dépasserait le budget de temps du crawl."""
        hote = urlsplit(lien).netloc.lower()
        restant = budget - (time.monotonic() - t0)
        attente = pause - (time.monotonic() - dernier[hote]) if hote in dernier else 0
        if restant <= 0 or attente >= restant:
            return None
        if attente > 0:
            time.sleep(attente)
        r = fetch(lien, timeout=max(1, min(timeout, restant - max(attente, 0))), ua=ua, **options, **kw)
        dernier[hote] = time.monotonic()
        return r

    arret = None
    for lien in ordre:
        if len(resultats) >= plafond:
            arret = "plafond"
            break
        r = demander(lien, method="HEAD")
        if r is not None and r["status"] in GET_APRES_HEAD:
            r = demander(lien, max_bytes=2048, extra_headers={"Range": "bytes=0-0"})
        if r is None:
            arret = "budget"
            break
        erreur = r.get("error")
        if r["status"] == -1:
            erreur = "plus de {0} redirections".format(MAX_REDIRECTIONS)
        if str((r.get("headers") or {}).get("cf-mitigated", "")).lower() == "challenge":
            erreur = DEFI
        resultats[lien] = {"statut": r["status"], "erreur": erreur}
    reste = len(sources) - len(resultats)
    ctx["externes"], ctx["sources_externes"] = resultats, sources
    meta = ctx.setdefault("meta", {})
    meta["liens_externes"] = {"trouves": len(sources), "verifies": len(resultats), "budget_atteint": arret == "budget"}
    meta["liens_externes_non_verifies"] = {"total": reste, "par_plafond": reste if arret == "plafond" else 0,
                                           "par_budget": reste if arret == "budget" else 0}


def issues(pages, add, ctx):
    externes, sources = ctx.get("externes", {}), ctx.get("sources_externes", {})
    for lien in sorted(externes, key=lambda x: (-len(sources.get(x, ())), x)):  # les plus liés d'abord, déterministe
        r = externes[lien]
        classe = classer(r["statut"], r["erreur"])
        if classe is None:
            continue
        erreur = ho.texte_sans_secret(r["erreur"] or "")[:80]
        statut = r["statut"] if r["statut"] > 0 and not erreur else ("{0} ({1})".format(r["statut"], erreur) if r["statut"] > 0 else erreur)
        ex = {"lien": ho.url_sans_secret(lien), "statut": statut,
              "liens_depuis": sorted({ho.url_page_publique(u) for u in sources.get(lien, ())})[:3]}
        if classe == "casse":
            add("external_broken", "Liens externes cassés (404, 410 ou nom de domaine inexistant)", "moyenne", ex, domaine="SEO technique")
        else:
            add("external_a_verifier", "Liens externes à vérifier (401/403/429/999/5xx, délai : souvent un blocage des robots)", "basse",
                ex, domaine="SEO technique")
