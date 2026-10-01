#!/usr/bin/env python3
"""
domaine_check.py — Santé DNS du domaine par DNS-over-HTTPS (stdlib, sans clé ni dig) : SPF, DMARC, CAA, DNSSEC (bit AD), IPv6.

Usage : python3 domaine_check.py https://site.fr --out DOSSIER [--resolveur https://cloudflare-dns.com/dns-query]
Sorties : DOSSIER/issues.json (format du crawl, source « domaine »), DOSSIER/domaine.md, DOSSIER/domaine.json. Code 0 toujours.

Résolveurs : Cloudflare puis Google (repli), format application/dns-json, délai ≤ 8 s par requête, budget global de temps,
pause entre deux requêtes. `--resolveur` (répétable) remplace la liste par défaut. Panne des résolveurs (réseau, SERVFAIL, réponse
invalide) : le contrôle concerné est affiché « ⚠️ … non vérifié » et ne produit AUCUN constat (une panne n'est pas un défaut du site).

Domaine contrôlé : le domaine organisationnel, soit le premier ancêtre du nom du site qui a un SOA en réponse (www.example.fr →
example.fr ; pas de liste des suffixes publics en stdlib). DMARC : recherche du nom exact, puis de ses ancêtres dont le domaine
organisationnel ; si l'enregistrement est publié sur un ancêtre, la politique « sp » (sous-domaines) prime sur « p ». CAA : remontée
de l'arbre (RFC 8659). Limite : MX et SPF sont lus sur le domaine organisationnel déduit du SOA ; une zone déléguée (sous-domaine
qui a son propre SOA) est prise pour le domaine organisationnel, d'où des constats SPF « durcissement » possibles. DNSSEC : bit AD du SOA du domaine ou de l'adresse du
site. Seules des données publiques du DNS sont lues et aucune adresse e-mail (ex. rua=mailto:) n'est recopiée en sortie.

Gravité (jamais de faux ❌) : SPF « +all » haute ; SPF > 10 requêtes ou plusieurs SPF : moyenne ; DMARC absent : moyenne si le
domaine reçoit des e-mails (MX), sinon basse (durcissement recommandé : « v=spf1 -all » et « p=reject » pour un domaine sans
e-mail) ; SPF absent, SPF « ?all » : basse ; DMARC « p=none », CAA, DNSSEC, IPv6 : info. DKIM (sélecteur inconnu) et MTA-STS : non testés.
"""
import argparse
import ipaddress
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

RESOLVEURS = ("https://cloudflare-dns.com/dns-query", "https://dns.google/resolve")
RESOLVEUR = RESOLVEURS[0]
TYPES = {"A": 1, "AAAA": 28, "MX": 15, "TXT": 16, "SOA": 6, "CAA": 257}
DELAI = 8          # secondes par requête (plafond dur : 8)
BUDGET = 40        # secondes pour l'ensemble des requêtes d'une exécution
PAUSE = 0.1        # secondes entre deux requêtes
ECHECS_MAX = 2     # échecs consécutifs avant d'abandonner un résolveur pour le reste de l'exécution
TAILLE_MAX = 1000000
LIMITE_SPF = 10    # RFC 7208 §4.6.4
_LOOPBACK = ("localhost", "127.0.0.1", "::1")


class DohErreur(Exception):
    """Résolveur injoignable ou réponse inexploitable : le contrôle est « non vérifié », pas « absent »."""


# --------------------------------------------------------------------------- transport DoH

def valider_resolveur(url):
    p = urlparse(url) if isinstance(url, str) else None
    if p is None or not p.hostname or not (p.scheme == "https" or (p.scheme == "http" and p.hostname in _LOOPBACK)):
        raise ValueError("résolveur DoH invalide (https attendu) : %r" % (url if isinstance(url, str) and "?" not in url else "…"))
    return url


def _requete(ouvrir, resolveur, nom, type_, timeout):
    req = urllib.request.Request(resolveur + ("&" if "?" in resolveur else "?") + urllib.parse.urlencode({"name": nom, "type": type_}),
                                 headers={"Accept": "application/dns-json"})
    with ouvrir(req, timeout=timeout) as r:
        corps = r.read(TAILLE_MAX + 1)
    if len(corps) > TAILLE_MAX:
        raise ValueError("réponse trop volumineuse")
    d = json.loads(corps.decode("utf-8"))
    if not isinstance(d, dict):
        raise ValueError("réponse JSON inattendue")
    return d


def transport_http(resolveurs=None, ouvrir=None, horloge=time.monotonic, dormir=time.sleep, delai=DELAI, budget=BUDGET, pause=PAUSE):
    """Retourne q(nom, type) -> dict DoH JSON. Essaie les résolveurs dans l'ordre ; lève DohErreur si aucun ne répond ou si le
    budget de temps est épuisé. Un résolveur qui échoue ECHECS_MAX fois de suite est abandonné pour la suite de l'exécution."""
    if isinstance(resolveurs, str):
        resolveurs = [resolveurs]
    liste = [valider_resolveur(r) for r in (resolveurs or RESOLVEURS)]
    delai = min(delai, 8)
    echecs = {r: 0 for r in liste}
    debut = horloge()
    deja = [False]

    def q(nom, type_):
        for r in liste:
            if echecs[r] >= ECHECS_MAX:
                continue
            restant = budget - (horloge() - debut)
            if restant <= 0:
                break
            if deja[0]:
                dormir(pause)
            deja[0] = True
            try:
                d = _requete(ouvrir or urllib.request.urlopen, r, nom, type_, min(delai, restant))
            except Exception:
                echecs[r] += 1
                continue
            echecs[r] = 0
            if d.get("Status", 0) not in (0, 3):  # SERVFAIL, REFUSED… : on laisse l'autre résolveur trancher
                continue
            return d
        raise DohErreur("aucun résolveur DoH n'a répondu")
    return q


class _Sonde:
    """Enveloppe d'un q(nom, type) : met en cache (une requête par couple nom/type, erreurs comprises) et ne laisse sortir que des
    réponses exploitables (Status 0 ou 3) ou une DohErreur."""

    def __init__(self, q):
        self.q = q
        self.cache = {}

    def __call__(self, nom, type_):
        cle = (nom.lower().rstrip("."), type_)
        if cle not in self.cache:
            try:
                d = self.q(nom, type_)
                if not isinstance(d, dict) or d.get("Status", 0) not in (0, 3):
                    raise DohErreur("réponse DNS inexploitable")
                self.cache[cle] = d
            except DohErreur as e:
                self.cache[cle] = e
            except Exception:
                self.cache[cle] = DohErreur("requête DoH en échec")
        v = self.cache[cle]
        if isinstance(v, DohErreur):
            raise v
        return v


def avec_cache(q):
    return q if isinstance(q, _Sonde) else _Sonde(q)


# --------------------------------------------------------------------------- lectures DNS

_CHAINE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def reponses(q, nom, type_):
    """Données des enregistrements du type demandé ([] si le nom n'existe pas ou n'en a pas). Lève DohErreur en cas de panne."""
    d = q(nom, type_)
    if d.get("Status", 0) != 0:
        return []
    return [r["data"] for r in d.get("Answer") or [] if isinstance(r, dict) and r.get("type") == TYPES[type_] and isinstance(r.get("data"), str)]


def txt(q, nom):
    """Chaînes TXT, morceaux (« "a" "b" ») recollés ; Google les sert sans guillemets."""
    out = []
    for d in reponses(q, nom, "TXT"):
        morceaux = _CHAINE.findall(d)
        out.append("".join(morceaux) if morceaux else d.strip())
    return out


def _spf(q, nom):
    return [t for t in txt(q, nom) if re.match(r"v=spf1(\s|$)", t, re.I)]


def domaine_organisationnel(hote, q):
    """Premier ancêtre (le nom lui-même compris, jamais le TLD seul) qui a un SOA en réponse ; None si aucun (nom inexistant ou DNS
    interne). Lève DohErreur si aucun SOA n'a été trouvé alors que des requêtes ont échoué."""
    q = avec_cache(q)
    labels = hote.rstrip(".").split(".")
    erreur = None
    for i in range(len(labels) - 1):
        nom = ".".join(labels[i:])
        try:
            if reponses(q, nom, "SOA"):
                return nom
        except DohErreur as e:
            erreur = e
    if erreur:
        raise erreur
    return None


def lookups_spf(q, domaine, _chemin=frozenset()):
    """Requêtes DNS consommées par l'évaluation SPF (RFC 7208 §4.6.4 : 10 au plus). Chaque include/redirect/a/mx/ptr/exists compte,
    y compris répété ; s'arrête dès que la limite est dépassée (valeur alors minorante). Lève DohErreur si une lecture échoue."""
    q = avec_cache(q)
    if domaine in _chemin or len(_chemin) > LIMITE_SPF:
        return 0
    spf = _spf(q, domaine)
    n = 0
    for terme in (spf[0].split()[1:] if spf else []):
        t = terme.lstrip("+-~?").lower()
        if t.startswith("include:") or t.startswith("redirect="):
            n += 1 + lookups_spf(q, re.split(r"[:=]", t, maxsplit=1)[1], _chemin | {domaine})
        elif t in ("a", "mx", "ptr") or t.startswith(("a:", "a/", "mx:", "mx/", "ptr:", "exists:")):
            n += 1
        if n > LIMITE_SPF:
            break
    return n


def _chaine(hote):
    """Nom du site puis ses ancêtres, jusqu'au domaine à deux étiquettes inclus (8 noms au plus). Contient toujours le domaine
    organisationnel ; va au-delà quand celui-ci est une zone déléguée (sous-domaine qui a son propre SOA)."""
    labels = hote.split(".")
    return [".".join(labels[i:]) for i in range(max(1, len(labels) - 1))][:8]


def _dmarc(q, hote):
    """(nom où l'enregistrement a été trouvé, enregistrement) : recherche DMARC du nom exact, puis de ses ancêtres dont le domaine
    organisationnel (remontée de l'arbre DNS) ; None si aucun enregistrement valide. Lève DohErreur si rien n'est trouvé alors
    qu'une lecture a échoué."""
    erreur = None
    for nom in _chaine(hote):
        try:
            trouves = [t for t in txt(q, "_dmarc." + nom) if re.match(r"v=dmarc1\b", t.strip(), re.I)]
        except DohErreur as e:
            erreur = e
            continue
        if len(trouves) == 1:  # plusieurs enregistrements : DMARC ignoré (RFC 7489 §6.6.3)
            return nom, trouves[0]
    if erreur:
        raise erreur
    return None


def _ad(q, nom, type_):
    try:
        return bool(q(nom, type_).get("AD"))
    except DohErreur:
        return False


def normaliser(hote):
    hote = (hote or "").strip().lower().rstrip(".")
    try:
        return hote.encode("idna").decode("ascii")
    except UnicodeError:
        return hote


def _est_ip(hote):
    try:
        ipaddress.ip_address(hote.split("%")[0])
        return True
    except ValueError:
        return False


# --------------------------------------------------------------------------- contrôles

def verifier(hote, q):
    """Contrôle SPF, DMARC, CAA, DNSSEC et IPv6 du site `hote` (nom d'hôte, sans schéma) avec le résolveur DoH injectable `q`.
    Retourne {"statut": ok | non résolu | adresse IP | non vérifié, "domaine", "hote", "issues", "lignes", "non_verifies"}."""
    hote = normaliser(hote)
    base = {"hote": hote, "domaine": None, "issues": {}, "non_verifies": []}
    if not hote or _est_ip(hote):
        return dict(base, statut="adresse IP", lignes=["- ⏭️ adresse IP : contrôles DNS sans objet"])
    q = avec_cache(q)
    try:
        dom = domaine_organisationnel(hote, q)
    except DohErreur:
        return dict(base, statut="non vérifié",
                    lignes=["- ⚠️ DNS : non vérifié (résolveurs DNS-over-HTTPS injoignables ou en erreur) : aucun constat"])
    if not dom:
        return dict(base, statut="non résolu",
                    lignes=["- ⏭️ domaine non résolu publiquement (DNS interne ou nom inexistant) : contrôles DNS ignorés"])

    issues, etat, non_verifies = {}, {}, []
    icones = {"haute": "❌", "moyenne": "⚠️", "basse": "⚠️", "info": "ℹ️"}

    def ajouter(cle, label, severite, exemple, domaine="Sécurité"):
        issues[cle] = {"label": label, "severity": severite, "count": 1, "examples": [exemple], "domaine": domaine}
        return "{0} {1}".format(icones[severite], label)

    def inconnu(controle, detail):
        non_verifies.append(controle)
        return "⚠️ {0} : non vérifié ({1})".format(controle, detail)

    # E-mail : seul un domaine qui reçoit du courrier (MX non nul, RFC 7505) donne du poids à SPF et DMARC
    try:
        nb_mx = len([m for m in reponses(q, dom, "MX") if m.split()[-1] != "."])
    except DohErreur:
        nb_mx = 0
        etat["MX"] = inconnu("MX", "gravité de SPF et de DMARC peut être sous-estimée")
    recoit = nb_mx > 0

    try:
        spf = _spf(q, dom)
        if not spf:
            etat["SPF"] = ajouter("spf_absent",
                                  "Aucun enregistrement SPF alors que le domaine reçoit des e-mails (MX)" if recoit else
                                  "Aucun enregistrement SPF : durcissement recommandé, un domaine sans e-mail devrait publier « v=spf1 -all »",
                                  "basse", {"domaine": dom, "mx": nb_mx})
        elif len(spf) > 1:
            etat["SPF"] = ajouter("spf_multiple", "Plusieurs enregistrements SPF (erreur permanente : SPF ignoré par les destinataires)",
                                  "moyenne", {"domaine": dom, "n": len(spf)})
        else:
            fins = re.findall(r"(?:^|\s)([+\-~?]?)all(?=\s|$)", spf[0].lower())
            if fins and fins[-1] in ("", "+"):
                etat["SPF"] = ajouter("spf_permissif", "SPF « +all » : n'importe quel serveur peut envoyer des e-mails au nom du domaine",
                                      "haute", {"domaine": dom, "spf": spf[0][:120]})
            elif fins and fins[-1] == "?":
                etat["SPF"] = ajouter("spf_permissif", "SPF « ?all » (neutre) : aucune protection contre l'usurpation", "basse",
                                      {"domaine": dom, "spf": spf[0][:120]})
            n = lookups_spf(q, dom)
            if n > LIMITE_SPF:
                etat["SPF"] = ajouter("spf_trop_de_requetes", "SPF : plus de 10 requêtes DNS (erreur permanente, RFC 7208)", "moyenne",
                                      {"domaine": dom, "requetes": n})
            elif "SPF" not in etat:
                etat["SPF"] = "✅ SPF : en place ({0} requête(s) DNS sur {1})".format(n, LIMITE_SPF)
    except DohErreur:
        etat["SPF"] = inconnu("SPF", "résolveur en panne")

    try:
        trouve = _dmarc(q, hote)
        if not trouve:
            etat["DMARC"] = ajouter("dmarc_absent",
                                    "Aucun enregistrement DMARC valide (_dmarc) alors que le domaine reçoit des e-mails (MX)" if recoit else
                                    "Aucun enregistrement DMARC valide (_dmarc) : durcissement recommandé, un domaine sans e-mail devrait "
                                    "publier « p=reject »",
                                    "moyenne" if recoit else "basse", {"domaine": dom, "mx": nb_mx})
        else:
            nom, enr = trouve
            tags = {k.strip().lower(): v.strip().lower() for k, _, v in (x.partition("=") for x in enr.split(";")) if v.strip()}
            politique = tags.get("sp") if nom != hote and tags.get("sp") else tags.get("p")  # « sp » : sous-domaines du nom où l'enregistrement est publié
            if politique == "none":
                etat["DMARC"] = ajouter("dmarc_none", "DMARC en p=none : surveillance seule, aucune protection", "info", {"domaine": nom})
            else:
                etat["DMARC"] = "✅ DMARC : en place (politique {0})".format(politique or "non lisible")
    except DohErreur:
        etat["DMARC"] = inconnu("DMARC", "résolveur en panne")

    try:
        if any(reponses(q, n, "CAA") for n in _chaine(hote)):
            etat["CAA"] = "✅ CAA : en place"
        else:
            etat["CAA"] = ajouter("caa_absent", "Aucun enregistrement CAA : toute autorité peut émettre un certificat", "info",
                                  {"domaine": dom}, "Serveur / HTTP")
    except DohErreur:
        etat["CAA"] = inconnu("CAA", "résolveur en panne")

    # Le SOA du domaine a déjà été lu avec succès (il a servi à trouver le domaine organisationnel)
    if _ad(q, dom, "SOA") or _ad(q, hote, "A"):
        etat["DNSSEC"] = "✅ DNSSEC : réponses validées (bit AD)"
    else:
        etat["DNSSEC"] = ajouter("dnssec_absent", "Domaine non signé DNSSEC (bit AD absent)", "info", {"domaine": dom}, "Serveur / HTTP")

    try:
        if reponses(q, hote, "AAAA"):
            etat["IPv6"] = "✅ IPv6 : adresse AAAA présente"
        else:
            etat["IPv6"] = ajouter("ipv6_absent", "Pas d'adresse IPv6 (AAAA) pour le site", "info", {"hote": hote}, "Serveur / HTTP")
    except DohErreur:
        etat["IPv6"] = inconnu("IPv6", "résolveur en panne")

    lignes = ["- " + etat[c] for c in ("MX", "SPF", "DMARC", "CAA", "DNSSEC", "IPv6") if c in etat]
    return {"statut": "ok", "domaine": dom, "hote": hote, "issues": issues, "lignes": lignes, "non_verifies": non_verifies}


def ecrire(r, dossier):
    d = Path(dossier)
    d.mkdir(parents=True, exist_ok=True)
    (d / "issues.json").write_text(json.dumps(r["issues"], ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    (d / "domaine.json").write_text(json.dumps({k: v for k, v in r.items() if k != "lignes"}, ensure_ascii=False, indent=1, sort_keys=True),
                                    encoding="utf-8")
    titre = r["domaine"] or r.get("hote") or "non résolu"
    (d / "domaine.md").write_text("# Domaine — {0}\n\n{1}\n".format(titre, "\n".join(r["lignes"])), encoding="utf-8")


def _resolveur_arg(valeur):
    try:
        return valider_resolveur(valeur)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def main(argv=None, transport=None):
    ap = argparse.ArgumentParser(description="Santé DNS du domaine (SPF, DMARC, CAA, DNSSEC, IPv6) par DNS-over-HTTPS.")
    ap.add_argument("url")
    ap.add_argument("--out", required=True)
    ap.add_argument("--resolveur", action="append", type=_resolveur_arg, metavar="URL",
                    help="résolveur DoH (application/dns-json), répétable ; défaut : Cloudflare puis Google")
    a = ap.parse_args(argv)
    hote = urlparse(a.url if "://" in a.url else "https://" + a.url).hostname or ""
    r = verifier(hote, transport or transport_http(a.resolveur))
    ecrire(r, a.out)
    print("domaine : {0} ({1} constat(s){2})".format(r["statut"], len(r["issues"]),
                                                       ", non vérifié : " + ", ".join(r["non_verifies"]) if r["non_verifies"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
