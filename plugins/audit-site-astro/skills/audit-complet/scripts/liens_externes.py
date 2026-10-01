#!/usr/bin/env python3
"""liens_externes.py — Liens externes cassés (Screaming Frog « External 4XX », Semrush « Broken external links »).
Module du diffuseur html_observateurs : Observateur (un passage par page), apres_crawl (réseau) puis issues(pages, add, ctx).

Sûreté (reseau_sur) : une adresse qui se résout vers une adresse non publique (127.0.0.1, 10.x, 169.254.169.254, localhost, .internal,
formes décimale / hexadécimale / Unicode) n'est JAMAIS requêtée, pas plus qu'une redirection vers elle ou vers file:// : le lien est
« non vérifié (adresse privée) ». Exception : le site audité lui-même (nom d'hôte exact) quand il est local, ou ctx["liens_prives"].
Réseau poli : HEAD d'abord, GET d'un octet (Range: bytes=0-0) si HEAD est refusé ou répond 404 / 410 (un 404 / 410 est confirmé par un
second GET : seul un GET répété conclut « cassé ») ; une pause entre deux requêtes vers un même hôte (HEAD puis GET compris) ; 5
redirections au plus ; jamais de cookie ; un User-Agent qui dit qui on est ; délai court par requête (8 s) ; budget de temps du crawl
(ctx["budget_reseau_s"]) et plafond de liens (ctx["liens_externes_max"]) respectés. Les liens sont vérifiés par ordre d'importance
(nombre de pages qui les contiennent, puis ordre de première apparition), jamais tronqués par ordre alphabétique.
Hors ligne : « nom de domaine inexistant » n'est conclu que si le réseau est prouvé (une réponse HTTP, ou une sonde DNS de référence) et
après une seconde résolution ; sinon tous ces liens sont « non vérifiés (réseau indisponible) », jamais « cassés ».
Ce que le plafond, le budget, une adresse privée ou l'absence de réseau laissent de côté est compté dans meta.liens_externes_non_verifies
et rapporté par le constat external_non_verifie (info). Cassé : 404, 410, nom de domaine inexistant. À vérifier, jamais cassé : 401, 403,
429, 999 (LinkedIn), 5xx, défi Cloudflare, délai dépassé, redirections sans fin, toute autre erreur réseau (blocage des robots fréquent).
L'adresse requêtée est l'adresse brute du lien (sans identifiants ni fragment) ; seules les sorties passent par url_sans_secret."""
import inspect
import re
import time
from urllib.parse import urldefrag, urlsplit, urlunsplit

import html_observateurs as ho
import reseau_sur

NOM = "liens_externes"
MAX_PAR_PAGE = 200
TIMEOUT_MAX = 8  # secondes, par requête
GET_APRES_HEAD = (403, 404, 405, 410, 501)  # HEAD mal géré par certains serveurs : le GET tranche (pas après un 429 : on ralentit)
UA_HONNETE = "AuditSiteAstro-LinkChecker/2.1 (verification de liens sortants; +https://github.com/ohvignas/audit-site-astro)"
DNS_INEXISTANT = re.compile(r"Name or service not known|nodename nor servname|No address associated|Errno -2\b|Errno 8\b|getaddrinfo failed", re.I)
DEFI = "défi Cloudflare"
CANARIS_DNS = ("example.com", "iana.org")
RAISON_PLAFOND, RAISON_BUDGET = "plafond atteint", "budget de temps atteint"
RAISON_PRIVEE, RAISON_RESEAU, RAISON_INVALIDE = "adresse privée", "réseau indisponible", "adresse invalide"
RAISONS = (RAISON_PRIVEE, RAISON_RESEAU, RAISON_INVALIDE, RAISON_PLAFOND, RAISON_BUDGET)

# adresse brute (mémoire seulement, jamais écrite) de chaque adresse assainie notée dans obs : le diffuseur n'écrit que la forme
# assainie, mais c'est l'adresse exacte qu'il faut requêter (jeton, identifiant Drive, URL longue, ?code=FR)
_BRUTES = {}


def _nu(h):
    h = (h or "").lower()
    return h[4:] if h.startswith("www.") else h


def _sans_identifiants(u):
    """(adresse sans fragment ni user:pass@, schéma et hôte en minuscules ; hôte avec port) ; (None, None) si illisible."""
    try:
        p = urlsplit(urldefrag(u)[0])
        hote = p.netloc.rpartition("@")[2].lower()
        return urlunsplit((p.scheme.lower(), hote, p.path, p.query, "")), hote
    except ValueError:
        return None, None


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.hote, self.liens = urlsplit(url).netloc.rpartition("@")[2].lower(), {}
        self.schema = urlsplit(url).scheme.lower() or "https"

    def debut(self, noeud, pile):
        if noeud["tag"] != "a" or noeud["masque"]:
            return
        href = re.sub(r"[\t\r\n]", "", noeud["a"].get("href", "")).strip()  # les navigateurs suppriment ces caractères
        if href.startswith("//"):  # protocole relatif : le schéma de la page
            href = self.schema + ":" + href
        if not href.lower().startswith(("http://", "https://")):
            return
        brute, hote = _sans_identifiants(href)
        if brute and hote and _nu(hote) != _nu(self.hote):
            public = ho.url_page_publique(brute)
            if public and not public.startswith("adresse illisible"):
                _BRUTES.setdefault(public, brute)
                self.liens.setdefault(public, None)

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


def _est_dns(statut, erreur):
    return statut <= 0 and classer(statut, erreur) == "casse"


def apres_crawl(pages, ctx):
    sources = {}  # lien -> pages qui le contiennent ; le dict garde l'ordre de première apparition
    hote_site = _nu((ctx.get("host") or "").rpartition("@")[2])
    for u, p in pages.items():
        for lien in ((p.get("obs") or {}).get(NOM) or {}).get("externes", []):
            if hote_site and _nu(urlsplit(lien).netloc.rpartition("@")[2].lower()) == hote_site:
                continue  # le site lui-même (variantes www) n'est pas un lien externe
            vues = sources.setdefault(lien, [])
            if u not in vues:
                vues.append(u)
    ordre = sorted(sources, key=lambda lien: -len(sources[lien]))  # tri stable : à égalité, première apparition d'abord
    ctx["sources_externes"] = sources
    meta = ctx.setdefault("meta", {})
    plafond = max(0, ctx.get("liens_externes_max", 300))
    if plafond == 0:  # --liens-externes 0 : vérification désactivée, rien à rapporter
        ctx["externes"], ctx["non_verifies_externes"] = {}, {}
        meta["liens_externes"] = {"trouves": len(sources), "verifies": 0, "budget_atteint": False, "desactive": True}
        meta["liens_externes_non_verifies"] = {"total": 0, "par_plafond": 0, "par_budget": 0, "par_adresse_privee": 0,
                                               "par_reseau_indisponible": 0, "par_adresse_invalide": 0}
        _BRUTES.clear()
        return

    fetch, resoudre, resultats, non_verifies, dernier = ctx["fetch"], ctx.get("resoudre"), {}, {}, {}
    ua = ctx.get("ua_liens_externes") or UA_HONNETE  # volontairement pas ctx["ua_navigateur"] : on ne se fait pas passer pour un navigateur
    pause, pause_dns = ctx.get("delai_externe", 1.0), ctx.get("delai_confirmation_dns", 0.5)
    budget, timeout, t0 = ctx.get("budget_reseau_s", 300), min(ctx.get("timeout", 20), TIMEOUT_MAX), time.monotonic()
    # exemption du refus des adresses privées : l'hôte exact du site audité (il est local : banc, développement) ; TOUS avec --liens-prives
    exemptions = reseau_sur.TOUS if ctx.get("liens_prives") else frozenset(
        h for h in [reseau_sur.hote_de("//" + (ctx.get("host") or "").rpartition("@")[2])] if h)
    options = {}
    if _accepte(fetch, "max_hops"):
        options["max_hops"] = reseau_sur.MAX_REDIRECTIONS + 1  # n requêtes = n - 1 redirections suivies
    if _accepte(fetch, "prive_ok"):
        options["prive_ok"] = exemptions
    if resoudre is not None and _accepte(fetch, "resoudre"):
        options["resoudre"] = resoudre
    if _accepte(fetch, "echeance"):
        options["echeance"] = t0 + budget
    resoudre_vraie = resoudre or reseau_sur._resoudre

    def demander(req, **kw):
        """Une requête, après la pause due à l'hôte ; None si la pause ou la requête dépasserait le budget de temps du crawl."""
        cle = _nu(reseau_sur.hote_de(req))
        restant = budget - (time.monotonic() - t0)
        attente = pause - (time.monotonic() - dernier[cle]) if cle in dernier else 0
        if restant <= 0 or attente >= restant:
            return None
        if attente > 0:
            time.sleep(attente)
        r = fetch(req, timeout=max(1, min(timeout, restant - max(attente, 0))), ua=ua, **options, **kw)
        dernier[cle] = time.monotonic()
        return r

    def sonde():
        for nom in ctx.get("canari_dns", CANARIS_DNS):
            try:
                resoudre_vraie(nom, None)
                return True
            except (OSError, UnicodeError):
                continue
        return False

    arret, prouve, dns_echecs, sonde_faite = None, False, 0, False
    for lien in ordre:
        if len(resultats) >= plafond:
            arret = RAISON_PLAFOND
            break
        brute = _BRUTES.get(lien, lien)
        req = None if ("…" in brute and lien not in _BRUTES) else reseau_sur.adresse_requete(brute)
        if req is None:
            non_verifies[lien] = RAISON_INVALIDE
            continue
        hote, port = reseau_sur.hote_de(req), urlsplit(req).port
        if reseau_sur.classer_hote(hote, port, resoudre, exemptions) == "privee":
            non_verifies[lien] = RAISON_PRIVEE  # jamais requêtée
            continue
        r = demander(req, method="HEAD")
        if r is not None and r["status"] in GET_APRES_HEAD:
            r = demander(req, max_bytes=2048, extra_headers={"Range": "bytes=0-0"})
            if r is not None and r["status"] in (404, 410):  # un 404 / 410 ne conclut qu'après une seconde observation
                r = demander(req, max_bytes=2048, extra_headers={"Range": "bytes=0-0"}) or r
        if r is None:
            arret = RAISON_BUDGET
            break
        if r.get("refus"):
            non_verifies[lien] = RAISON_PRIVEE if r["refus"] == "adresse_privee" else RAISON_INVALIDE  # redirection refusée
            continue
        statut = r["status"] if isinstance(r["status"], int) else 0
        erreur = r.get("error")
        if statut == -1:
            erreur = "plus de {0} redirections".format(reseau_sur.MAX_REDIRECTIONS)
        if str((r.get("headers") or {}).get("cf-mitigated", "")).lower() == "challenge":
            erreur = DEFI
        if _est_dns(statut, erreur):
            dns_echecs += 1
            if pause_dns > 0 and budget - (time.monotonic() - t0) > pause_dns:
                time.sleep(pause_dns)
            try:  # seconde résolution : un résolveur capricieux ne doit pas faire conclure « cassé »
                resoudre_vraie(hote, None)
                erreur = "résolution instable (le nom se résout au second essai)"
            except (OSError, UnicodeError) as e:
                erreur = "<urlopen error {0}>".format(e)
        resultats[lien] = {"statut": statut, "erreur": erreur}
        if statut > 0:
            prouve = True
        elif dns_echecs >= 3 and not prouve and not sonde_faite:  # 3 échecs DNS, aucune réponse HTTP : la machine est-elle en ligne ?
            sonde_faite = True
            if sonde():
                prouve = True
            else:
                arret = RAISON_RESEAU
                break
    reseau_ko = arret == RAISON_RESEAU
    if not prouve and not sonde_faite and any(_est_dns(r["statut"], r["erreur"]) for r in resultats.values()):
        reseau_ko = not sonde()
        arret = RAISON_RESEAU if reseau_ko else arret
    if reseau_ko:  # hors ligne : aucun « nom inexistant » n'est fiable
        for lien in [x for x, r in resultats.items() if _est_dns(r["statut"], r["erreur"])]:
            del resultats[lien]
            non_verifies[lien] = RAISON_RESEAU
    for lien in ordre:
        if lien not in resultats and lien not in non_verifies:
            non_verifies[lien] = arret or RAISON_PLAFOND
    compte = lambda raison: sum(1 for x in non_verifies.values() if x == raison)  # noqa: E731
    ctx["externes"], ctx["non_verifies_externes"] = resultats, non_verifies
    meta["liens_externes"] = {"trouves": len(sources), "verifies": len(resultats), "budget_atteint": arret == RAISON_BUDGET}
    meta["liens_externes_non_verifies"] = {
        "total": len(non_verifies), "par_plafond": compte(RAISON_PLAFOND), "par_budget": compte(RAISON_BUDGET),
        "par_adresse_privee": compte(RAISON_PRIVEE), "par_reseau_indisponible": compte(RAISON_RESEAU),
        "par_adresse_invalide": compte(RAISON_INVALIDE)}
    meta["liens_externes_reseau"] = {"prouve": prouve or (sonde_faite and not reseau_ko), "reseau_indisponible": reseau_ko,
                                     "dns_inexistants": sum(1 for r in resultats.values() if _est_dns(r["statut"], r["erreur"]))}
    _BRUTES.clear()


def issues(pages, add, ctx):
    externes, sources = ctx.get("externes", {}), ctx.get("sources_externes", {})
    ordre = lambda x: (-len(sources.get(x, ())), x)  # noqa: E731  les plus liés d'abord, déterministe
    for lien in sorted(externes, key=ordre):
        r = externes[lien]
        statut = r["statut"] if isinstance(r["statut"], int) else 0
        classe = classer(statut, r["erreur"])
        if classe is None:
            continue
        erreur = ho.texte_sans_secret(r["erreur"] or "")[:80]
        ex = {"lien": ho.url_sans_secret(lien),
              "statut": statut if statut > 0 and not erreur else ("{0} ({1})".format(statut, erreur) if statut > 0 else erreur),
              "liens_depuis": sorted({ho.url_page_publique(u) for u in sources.get(lien, ())})[:3]}
        if classe == "casse":
            add("external_broken", "Liens externes cassés (404, 410 ou nom de domaine inexistant)", "moyenne", ex, domaine="SEO technique")
        else:
            add("external_a_verifier", "Liens externes à vérifier (401/403/429/999/5xx, délai : souvent un blocage des robots)", "basse",
                ex, domaine="SEO technique")
    non = ctx.get("non_verifies_externes", {})
    for raison in RAISONS:
        liens = sorted((x for x, v in non.items() if v == raison), key=ordre)
        if liens:
            add("external_non_verifie", "Liens externes non vérifiés (plafond, budget de temps, adresse privée, réseau indisponible)", "info",
                {"raison": raison, "n": len(liens), "liens": [ho.url_sans_secret(x) for x in liens[:3]]},
                n=len(liens), domaine="SEO technique")
