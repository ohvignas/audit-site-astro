#!/usr/bin/env python3
"""
domaine_check.py — Santé DNS du domaine par DNS-over-HTTPS (stdlib, sans clé ni dig) : SPF, DMARC, CAA, DNSSEC (bit AD), IPv6.

Usage : python3 domaine_check.py https://site.fr --out DOSSIER [--resolveur https://cloudflare-dns.com/dns-query]
Sorties : DOSSIER/issues.json (format du crawl, source « domaine »), DOSSIER/domaine.md, DOSSIER/domaine.json. Code 0 toujours.

Résolveurs : Cloudflare puis Google (repli), format application/dns-json, délai ≤ 8 s par requête, budget global de temps,
pause entre deux requêtes, redirections refusées (https uniquement). `--resolveur` (répétable) remplace la liste par défaut ;
le contrôle DNSSEC suppose un résolveur validant (Cloudflare et Google le sont). Panne des résolveurs (réseau, SERVFAIL, réponse
invalide) : le contrôle concerné est affiché « ⚠️ … non vérifié » et ne produit AUCUN constat (une panne n'est pas un défaut du site).

Domaine contrôlé : le domaine enregistrable de la Public Suffix List (module suffixes_publics : www.example.fr et beta.example.fr
→ example.fr ; www.example.co.uk → example.co.uk) ; le SOA ne sert qu'à confirmer qu'il existe. Un site sous un suffixe PRIVÉ
de la PSL (github.io, vercel.app, netlify.app, pages.dev, herokuapp.com…) a le statut « plateforme partagée » et AUCUN constat :
SPF, DMARC, CAA et DNSSEC appartiennent à la plateforme. DMARC : recherche du nom exact puis de ses ancêtres jusqu'au domaine
enregistrable (RFC 7489, remontée de l'arbre) ; si l'enregistrement est publié sur un ancêtre, la politique « sp » prime sur
« p ». CAA : remontée de l'arbre (RFC 8659). DNSSEC : bit AD du SOA du domaine ou de l'adresse du site (un domaine dont la signature
est cassée répond SERVFAIL : « non vérifié »). IPv6 : AAAA du nom audité et de son jumeau apex/www s'il a une adresse.
Seules des données publiques du DNS sont lues et aucune adresse e-mail (ex. rua=mailto:) n'est recopiée en sortie.

SPF (RFC 7208) : le premier mécanisme « all » l'emporte ; `include:` et `redirect=` sont suivis (10 requêtes au plus, boucles
coupées) pour trouver un « +all » hérité.

Gravité (jamais de faux ❌) : SPF « +all » haute ; SPF > 10 requêtes ou plusieurs SPF : moyenne ; SPF ou DMARC absent : moyenne si
le domaine reçoit des e-mails (MX non nul), sinon basse (durcissement recommandé : « v=spf1 -all » et « p=reject » pour un domaine
sans e-mail) ; SPF « ?all » : basse ; DMARC « p=none », CAA, DNSSEC, IPv6 : info. DKIM (sélecteur inconnu) et MTA-STS : non testés.
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

import suffixes_publics as psl

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


class _SansRedirection(urllib.request.HTTPRedirectHandler):
    """Refuse toute redirection (y compris https -> http) : un résolveur DoH ne redirige pas, et les noms interrogés ne doivent pas
    partir ailleurs ni en clair. La réponse 3xx devient une erreur HTTP, donc un échec de ce résolveur."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _ouvreur():
    return urllib.request.build_opener(_SansRedirection)


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
    budget de temps est épuisé. Un résolveur qui échoue ECHECS_MAX fois de suite est abandonné pour la suite de l'exécution.
    Le délai de urlopen vaut par opération de socket : un résolveur « goutte-à-goutte » (--resolveur hostile) peut dépasser 8 s en
    lecture ; le budget global ne borne qu'entre deux requêtes."""
    if isinstance(resolveurs, str):
        resolveurs = [resolveurs]
    liste = [valider_resolveur(r) for r in (resolveurs or RESOLVEURS)]
    delai = min(delai, 8)
    ouvrir = ouvrir or _ouvreur().open
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
                d = _requete(ouvrir, r, nom, type_, min(delai, restant))
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


def _meme_nom(a, b):
    return a.lower().rstrip(".") == b.lower().rstrip(".")


def reponses(q, nom, type_):
    """Données des enregistrements du type demandé ([] si le nom n'existe pas ou n'en a pas). Lève DohErreur en cas de panne.
    Un SOA n'est retenu que s'il appartient au nom demandé (une réponse suivie par CNAME porte le SOA d'un autre nom)."""
    d = q(nom, type_)
    if d.get("Status", 0) != 0:
        return []
    out = []
    for r in d.get("Answer") or []:
        if not isinstance(r, dict) or r.get("type") != TYPES[type_] or not isinstance(r.get("data"), str):
            continue
        if type_ == "SOA" and isinstance(r.get("name"), str) and not _meme_nom(r["name"], nom):
            continue
        out.append(r["data"])
    return out


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
    """Domaine enregistrable (Public Suffix List) du nom, s'il existe dans le DNS (SOA propre en réponse) ; None sinon (suffixe
    public, nom inexistant ou DNS interne). Lève DohErreur si la lecture du SOA échoue."""
    dom = psl.domaine_enregistrable(hote)
    if not dom:
        return None
    return dom if reponses(avec_cache(q), dom, "SOA") else None


def _termes(spf):
    """(qualificateur, mécanisme) des termes de l'enregistrement, sans « v=spf1 » ; les modificateurs gardent « redirect=cible »."""
    for terme in spf.split()[1:]:
        t = terme.lower()
        if t.startswith(("redirect=", "exp=")):
            yield "", t
        else:
            yield (t[0] if t[0] in "+-~?" else "+"), t.lstrip("+-~?")


def lookups_spf(q, domaine, _chemin=frozenset()):
    """Requêtes DNS consommées par l'évaluation SPF (RFC 7208 §4.6.4 : 10 au plus). Compte include, redirect, a, mx, ptr et exists
    (répétés compris) jusqu'au premier « all » ; au-delà, et pour « redirect= » quand un « all » existe, rien n'est évalué. S'arrête
    dès que la limite est dépassée (valeur alors minorante). Lève DohErreur si une lecture échoue."""
    q = avec_cache(q)
    if domaine in _chemin or len(_chemin) > LIMITE_SPF:
        return 0
    spf = _spf(q, domaine)
    if not spf:
        return 0
    n, redirect, vu_all = 0, None, False
    for qual, m in _termes(spf[0]):
        if m.startswith("redirect="):
            redirect = m.split("=", 1)[1]
        elif m.startswith("exp="):
            continue
        elif m == "all":
            vu_all = True
            break
        elif m.startswith("include:"):
            n += 1 + lookups_spf(q, m.split(":", 1)[1], _chemin | {domaine})
        elif m in ("a", "mx", "ptr") or m.startswith(("a:", "a/", "mx:", "mx/", "ptr:", "exists:")):
            n += 1
        if n > LIMITE_SPF:
            return n
    if redirect and not vu_all:
        n += 1 + lookups_spf(q, redirect, _chemin | {domaine})
    return n


def _effet_all(q, domaine, etat, chemin=()):
    """Résultat SPF d'une adresse quelconque : (qualificateur du premier « all » atteint, domaine de l'enregistrement qui le porte),
    ou None. Le premier « all » l'emporte (RFC 7208 §5.1) ; un `include:` dont le résultat est « + » pour toute adresse correspond
    donc pour toutes (le résultat est le qualificateur du terme, §5.2) ; sans « all », `redirect=` donne le résultat de sa cible (§6.1).
    Au plus LIMITE_SPF enregistrements suivis, boucles coupées ; une lecture en échec marque etat["incomplet"]."""
    if domaine in chemin or etat["suivis"] > LIMITE_SPF:
        return None
    spf = _spf(q, domaine)
    if not spf:
        return None
    redirect = None
    for qual, m in _termes(spf[0]):
        if m.startswith("redirect="):
            redirect = m.split("=", 1)[1]
        elif m == "all":
            return qual, domaine
        elif m.startswith("include:"):
            etat["suivis"] += 1
            try:
                res = _effet_all(q, m.split(":", 1)[1], etat, chemin + (domaine,))
            except DohErreur:
                etat["incomplet"] = True
                continue
            if res and res[0] == "+":
                return qual, res[1]
    if redirect:
        etat["suivis"] += 1
        try:
            return _effet_all(q, redirect, etat, chemin + (domaine,))
        except DohErreur:
            etat["incomplet"] = True
    return None


def _chaine(hote, dom):
    """Nom du site puis ses ancêtres jusqu'au domaine enregistrable inclus (8 noms au plus : le nom exact et les 7 derniers)."""
    labels = hote.split(".")
    chaine = [".".join(labels[i:]) for i in range(len(labels) - dom.count("."))]
    return chaine[:1] + chaine[-7:] if len(chaine) > 8 else chaine


def _dmarc(q, hote, dom, info):
    """(nom où l'enregistrement a été trouvé, enregistrement) : recherche DMARC du nom exact puis de ses ancêtres jusqu'au domaine
    enregistrable ; None si aucun enregistrement valide. Lève DohErreur si rien n'est trouvé alors qu'une lecture a échoué."""
    erreur = None
    for nom in _chaine(hote, dom):
        try:
            trouves = [t for t in txt(q, "_dmarc." + nom) if re.match(r"v=dmarc1\b", t.strip(), re.I)]
        except DohErreur as e:
            erreur = e
            continue
        if len(trouves) == 1:
            return nom, trouves[0]
        if len(trouves) > 1:  # plusieurs enregistrements : DMARC ignoré (RFC 7489 §6.6.3)
            info["multiples"] = True
    if erreur:
        raise erreur
    return None


def _caa_actif(enregistrements):
    """Vrai si l'ensemble CAA restreint l'émission (propriété issue ou issuewild, RFC 8659) ; « iodef » seul ne restreint rien."""
    for e in enregistrements:
        m = re.match(r"\s*\d+\s+([A-Za-z0-9]+)", e)
        if not m or m.group(1).lower() in ("issue", "issuewild"):  # forme illisible : on ne conclut pas à tort à l'absence
            return True
    return False


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


def _nom_valide(hote):
    return 0 < len(hote) <= 253 and all(0 < len(e) <= 63 for e in hote.split("."))


def _est_ip(hote):
    try:
        ipaddress.ip_address(hote.split("%")[0])
        return True
    except ValueError:
        return False


# --------------------------------------------------------------------------- contrôles

def verifier(hote, q):
    """Contrôle SPF, DMARC, CAA, DNSSEC et IPv6 du site `hote` (nom d'hôte, sans schéma) avec le résolveur DoH injectable `q`.
    Retourne {"statut": ok | non résolu | adresse IP | plateforme partagée | nom invalide | non vérifié, "domaine", "hote", "suffixe",
    "issues", "lignes", "non_verifies"}."""
    hote = normaliser(hote)
    base = {"hote": hote, "domaine": None, "suffixe": None, "issues": {}, "non_verifies": []}
    if hote and _est_ip(hote):
        return dict(base, statut="adresse IP", lignes=["- ⏭️ adresse IP : contrôles DNS sans objet"])
    if not _nom_valide(hote):
        return dict(base, statut="nom invalide", lignes=["- ⏭️ nom d'hôte invalide : contrôles DNS ignorés"])
    if psl.suffixe_prive(hote):
        suffixe = psl.suffixe_public(hote)
        return dict(base, statut="plateforme partagée", suffixe=suffixe,
                    lignes=["- ⏭️ sous-domaine de {0} (plateforme partagée) : le DNS est géré par la plateforme, SPF, DMARC, CAA, DNSSEC et "
                            "IPv6 ne dépendent pas du propriétaire du site ; un domaine personnalisé permettrait ces contrôles".format(suffixe)])
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

    def ajouter(cle, label, severite, exemple, domaine="Sécurité", controle=None, icone=None):
        issues[cle] = {"label": label, "severity": severite, "count": 1, "examples": [exemple], "domaine": domaine}
        etat.setdefault(controle, []).append("{0} {1}".format(icone or icones[severite], label))

    def inconnu(controle, detail):
        non_verifies.append(controle)
        etat.setdefault(controle, []).append("⚠️ {0} : non vérifié ({1})".format(controle, detail))

    # E-mail : seul un domaine qui reçoit du courrier (MX non nul, RFC 7505) donne du poids à SPF et DMARC
    try:
        nb_mx = len([m for m in reponses(q, dom, "MX") if m.split()[-1] != "."])
    except DohErreur:
        nb_mx = 0
        inconnu("MX", "gravité de SPF et de DMARC peut être sous-estimée")
    recoit = nb_mx > 0

    try:
        spf = _spf(q, dom)
        if not spf:
            ajouter("spf_absent",
                    "Aucun enregistrement SPF alors que le domaine reçoit des e-mails (MX)" if recoit else
                    "Aucun enregistrement SPF : durcissement recommandé, un domaine sans e-mail devrait publier « v=spf1 -all »",
                    "moyenne" if recoit else "basse", {"domaine": dom, "mx": nb_mx}, controle="SPF")
        elif len(spf) > 1:
            ajouter("spf_multiple", "Plusieurs enregistrements SPF : SPF invalide (PermError), les destinataires ne peuvent pas l'évaluer",
                    "moyenne", {"domaine": dom, "n": len(spf)}, controle="SPF")
        else:
            suivi = {"suivis": 0, "incomplet": False}
            res = _effet_all(q, dom, suivi)
            qual, origine = res if res else (None, None)
            exemple = {"domaine": dom, "spf": spf[0][:120]}
            if origine and origine != dom:
                exemple["via"] = origine
            herite = " (hérité de {0} par include/redirect)".format(origine) if origine and origine != dom else ""
            if qual == "+":
                ajouter("spf_permissif", "SPF « +all »{0} : n'importe quel serveur peut envoyer des e-mails au nom du domaine".format(herite),
                        "haute", exemple, controle="SPF")
            elif qual == "?":
                ajouter("spf_permissif", "SPF « ?all »{0} (neutre) : aucune protection contre l'usurpation".format(herite), "basse", exemple,
                        controle="SPF")
            try:
                n = lookups_spf(q, dom)
            except DohErreur:
                n, suivi["incomplet"] = 0, True
            if n > LIMITE_SPF:
                ajouter("spf_trop_de_requetes", "SPF : plus de 10 requêtes DNS (erreur permanente, RFC 7208)", "moyenne",
                        {"domaine": dom, "requetes": n}, controle="SPF")
            if "SPF" not in etat:
                if suivi["incomplet"]:
                    inconnu("SPF", "include ou redirect injoignable")
                else:
                    etat["SPF"] = ["✅ SPF : en place ({0} requête(s) DNS sur {1})".format(n, LIMITE_SPF)]
    except DohErreur:
        inconnu("SPF", "résolveur en panne")

    try:
        info = {}
        trouve = _dmarc(q, hote, dom, info)
        if not trouve:
            ajouter("dmarc_absent",
                    "Aucun enregistrement DMARC valide (_dmarc){0} alors que le domaine reçoit des e-mails (MX)".format(
                        " : plusieurs enregistrements sur un même nom, un seul est permis" if info.get("multiples") else "") if recoit else
                    "Aucun enregistrement DMARC valide (_dmarc){0} : durcissement recommandé, un domaine sans e-mail devrait publier "
                    "« p=reject »".format(" : plusieurs enregistrements sur un même nom, un seul est permis" if info.get("multiples") else ""),
                    "moyenne" if recoit else "basse", {"domaine": dom, "mx": nb_mx}, controle="DMARC")
        else:
            nom, enr = trouve
            tags = {k.strip().lower(): v.strip().lower() for k, _, v in (x.partition("=") for x in enr.split(";")) if v.strip()}
            valides = ("none", "quarantine", "reject")
            if tags.get("p") not in valides:
                etat["DMARC"] = ["⚠️ DMARC : enregistrement invalide (p= absent ou illisible), il est ignoré par les destinataires"]
            else:
                par_sp = nom != hote and tags.get("sp") in valides  # « sp » : sous-domaines du nom où l'enregistrement est publié
                politique = tags["sp"] if par_sp else tags["p"]
                if politique == "none":
                    ajouter("dmarc_none", "DMARC : politique effective « none » pour ce sous-domaine (sp=none), surveillance seule, aucune "
                            "protection" if par_sp else "DMARC en p=none : surveillance seule, aucune protection", "info", {"domaine": nom},
                            controle="DMARC")
                else:
                    etat["DMARC"] = ["✅ DMARC : en place (politique {0})".format(politique)]
    except DohErreur:
        inconnu("DMARC", "résolveur en panne")

    try:
        caa = []
        for nom in _chaine(hote, dom):
            caa = reponses(q, nom, "CAA")
            if caa:  # le premier ensemble CAA rencontré en remontant s'applique (RFC 8659 §3)
                break
        if not caa:
            ajouter("caa_absent", "Aucun enregistrement CAA : toute autorité peut émettre un certificat", "info", {"domaine": dom},
                    "Serveur / HTTP", "CAA")
        elif not _caa_actif(caa):
            ajouter("caa_absent", "Enregistrement CAA sans « issue » ni « issuewild » (iodef seul) : il n'empêche l'émission d'aucune autorité",
                    "info", {"domaine": dom}, "Serveur / HTTP", "CAA", icone="⚠️")
        else:
            etat["CAA"] = ["✅ CAA : en place"]
    except DohErreur:
        inconnu("CAA", "résolveur en panne")

    # Le SOA du domaine a déjà été lu avec succès (il a servi à confirmer le domaine) ; AD suppose un résolveur validant
    if _ad(q, dom, "SOA") or _ad(q, hote, "A"):
        etat["DNSSEC"] = ["✅ DNSSEC : réponses validées (bit AD)"]
    else:
        ajouter("dnssec_absent", "Chaîne DNSSEC non validée : zone non signée, ou enregistrement DS absent chez le registrar (bit AD absent)",
                "info", {"domaine": dom}, "Serveur / HTTP", "DNSSEC")

    try:
        manquants = [] if reponses(q, hote, "AAAA") else [hote]
        jumeau = "www." + dom if hote == dom else dom if hote == "www." + dom else None
        if jumeau:
            try:
                if not reponses(q, jumeau, "AAAA") and reponses(q, jumeau, "A"):
                    manquants.append(jumeau)
            except DohErreur:
                pass
        if manquants:
            ajouter("ipv6_absent", "Pas d'adresse IPv6 (AAAA) pour : {0}".format(", ".join(manquants)), "info",
                    {"hote": hote, "sans_ipv6": manquants}, "Serveur / HTTP", "IPv6")
        else:
            etat["IPv6"] = ["✅ IPv6 : adresse AAAA présente"]
    except DohErreur:
        inconnu("IPv6", "résolveur en panne")

    lignes = ["- " + x for c in ("MX", "SPF", "DMARC", "CAA", "DNSSEC", "IPv6") for x in etat.get(c, [])]
    return dict(base, statut="ok", domaine=dom, issues=issues, lignes=lignes, non_verifies=non_verifies)


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
                    help="résolveur DoH (application/dns-json, https), répétable ; défaut : Cloudflare puis Google. Le contrôle DNSSEC "
                         "(bit AD) suppose un résolveur validant")
    a = ap.parse_args(argv)
    hote = urlparse(a.url if "://" in a.url else "https://" + a.url).hostname or ""
    r = verifier(hote, transport or transport_http(a.resolveur))
    ecrire(r, a.out)
    print("domaine : {0} ({1} constat(s){2})".format(r["statut"], len(r["issues"]),
                                                       ", non vérifié : " + ", ".join(r["non_verifies"]) if r["non_verifies"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
