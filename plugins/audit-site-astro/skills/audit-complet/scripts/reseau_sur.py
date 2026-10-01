#!/usr/bin/env python3
"""reseau_sur.py — requêtes réseau sûres (Python 3.9+, stdlib), partagées par le crawl et les modules qui contactent des tiers.

Un site audité est hostile par hypothèse : une page, un en-tête Location ou un sitemap peuvent désigner une adresse interne de la
machine d'audit (127.0.0.1, 10.x, 169.254.169.254 : métadonnées cloud), un fichier local (file://) ou un service FTP. Ce module
garantit que :
  - seuls http et https sont jamais ouverts (l'opener n'a ni FileHandler, ni FTPHandler, ni DataHandler, ni gestion de cookies) ;
  - les redirections sont suivies à la main, 5 au plus ; chaque saut doit être http(s) et passer adresse_publique ;
  - un hôte n'est contacté que si TOUTES les adresses auxquelles il se résout sont publiques (ipaddress.is_global), après
    normalisation NFKC et IDNA : les formes obfusquées (2130706433, 127.1, 0x7f.1, chiffres Unicode, ::ffff:127.0.0.1) ne passent pas ;
  - aucun cookie n'est envoyé, et Authorization n'est pas renvoyé à un autre hôte.
Exemption : prive_ok = noms d'hôtes exacts (sans port) du site audité quand il est lui-même local (banc de test, développement) ;
TOUS autorise toutes les adresses privées (option explicite --liens-prives). Jamais d'interrupteur global.
Limite connue : la résolution du garde et celle de la connexion sont deux appels (un nom à TTL 0 peut répondre public puis privé) ;
en nuage, exécuter l'audit avec une sortie réseau restreinte (pare-feu de sortie, réseau Docker sans accès aux métadonnées)."""
import ipaddress
import os
import re
import socket
import ssl
import time
import unicodedata
import urllib.error
import urllib.request
import zlib
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

MAX_REDIRECTIONS = 5
SUFFIXES_INTERDITS = (".localhost", ".local", ".internal", ".localdomain", ".lan", ".home.arpa", ".intranet", ".corp", ".private")
# toute forme que inet_aton() accepte (décimal, hexadécimal, octal, « 127.1 ») : jamais un nom de domaine légitime
NUMERIQUE = re.compile(r"^(0x[0-9a-f]*|\d+)(\.(0x[0-9a-f]*|\d+))*\.?$", re.I)
NAT64 = ipaddress.ip_network("64:ff9b::/96")
CACHE_DNS_S = 60
_CACHE = {}
_OPENERS = {}


class _Tous:
    """prive_ok = TOUS : toutes les adresses privées sont autorisées (--liens-prives)."""

    def __contains__(self, _):
        return True

    def __repr__(self):
        return "TOUS"


TOUS = _Tous()


# --------------------------------------------------------------------------- hôtes et adresses

def normaliser_hote(h):
    """Hôte en minuscules ASCII (NFKC puis IDNA), sans crochets, zone IPv6 ni point final ; None si inutilisable."""
    if h is None:
        return None
    h = unicodedata.normalize("NFKC", str(h)).strip().strip("[]").rstrip(".").lower()
    if not h or any(c.isspace() for c in h):
        return None
    if ":" in h:  # IPv6 littérale (avec zone éventuelle)
        h = h.split("%", 1)[0]
        try:
            return str(ipaddress.ip_address(h))
        except ValueError:
            return None
    try:
        return h.encode("idna").decode("ascii")
    except UnicodeError:
        return None


def hote_de(url):
    """Nom d'hôte normalisé d'une adresse (sans identifiants ni port) ; None si absent."""
    try:
        return normaliser_hote(urlsplit(url).hostname)
    except ValueError:
        return None


def _global(adresse):
    a = ipaddress.ip_address(str(adresse).split("%", 1)[0])
    if a.version == 6:
        if a.ipv4_mapped is not None:
            a = a.ipv4_mapped
        elif a in NAT64:
            a = ipaddress.ip_address(int(a) & 0xFFFFFFFF)
    return a.is_global


def _resoudre(hote, port=None):
    """Toutes les adresses (IPv4 et IPv6) d'un hôte ; socket.gaierror si le nom n'existe pas."""
    cle, maintenant = (hote, port), time.monotonic()
    if cle in _CACHE and maintenant - _CACHE[cle][0] < CACHE_DNS_S:
        return _CACHE[cle][1]
    adresses = sorted({i[4][0] for i in socket.getaddrinfo(hote, port or 0, type=socket.SOCK_STREAM)})
    _CACHE[cle] = (maintenant, adresses)
    return adresses


def classer_hote(hote, port=None, resoudre=None, prive_ok=()):
    """« publique » (on peut contacter), « privee » (adresse interne, jamais contactée) ou « introuvable » (le nom ne se résout pas :
    la requête échouera d'elle-même, c'est le cas « nom de domaine inexistant »). prive_ok : noms d'hôtes exacts exemptés."""
    h = normaliser_hote(hote)
    if h is None:
        return "privee"
    if h in prive_ok:
        return "publique"
    if ":" in h:  # littérale IPv6
        return "publique" if _global(h) else "privee"
    if h == "localhost" or "." not in h or h.endswith(SUFFIXES_INTERDITS):
        return "privee"
    try:
        return "publique" if _global(h) else "privee"
    except ValueError:
        pass
    if NUMERIQUE.match(h):  # forme obfusquée : jamais valable, sans même résoudre
        return "privee"
    try:
        adresses = (resoudre or _resoudre)(h, port)
    except (OSError, UnicodeError):
        return "introuvable"
    if not adresses:
        return "introuvable"
    try:
        return "publique" if all(_global(a) for a in adresses) else "privee"
    except ValueError:
        return "privee"


def adresse_publique(hote, port=None, resoudre=None, prive_ok=()):
    """Vrai si l'hôte se résout et que TOUTES ses adresses sont publiques (ou si l'hôte est exempté)."""
    return classer_hote(hote, port, resoudre, prive_ok) == "publique"


def adresse_requete(url):
    """Adresse ASCII prête pour http.client : hôte en IDNA, chemin et requête encodés en UTF-8 (« Café » -> « Caf%C3%A9 »), sans
    fragment ni identifiants ; idempotente ; None si ce n'est pas une adresse http(s) avec un hôte."""
    if not url:
        return None
    try:
        p = urlsplit(re.sub(r"[\t\r\n]", "", str(url).strip()))
        hote, port = normaliser_hote(p.hostname), p.port
    except ValueError:
        return None
    if p.scheme.lower() not in ("http", "https") or not hote:
        return None
    netloc = ("[" + hote + "]" if ":" in hote else hote) + (":{0}".format(port) if port else "")
    return urlunsplit((p.scheme.lower(), netloc, quote(p.path or "/", safe="/%:@!$&'()*+,;=~-._"),
                       quote(p.query, safe="=&%+:/?@,;~-._!$'()*"), ""))


# --------------------------------------------------------------------------- ouverture

class _SansRedirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener(proxy=False):
    """Opener sans suivi automatique des redirections, ni cookies, avec les seuls gestionnaires http et https ; TLS non vérifié si
    AUDIT_INSECURE_TLS=1 (tests). proxy=True : variables http(s)_proxy de l'environnement respectées (crawl du site audité)."""
    insecure = os.environ.get("AUDIT_INSECURE_TLS") == "1"
    cle = (insecure, proxy)
    if cle not in _OPENERS:
        contexte = None
        if insecure:
            contexte = ssl.create_default_context()
            contexte.check_hostname = False
            contexte.verify_mode = ssl.CERT_NONE
        o = urllib.request.OpenerDirector()
        gestionnaires = [urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(context=contexte), _SansRedirection(),
                         urllib.request.HTTPDefaultErrorHandler(), urllib.request.HTTPErrorProcessor(), urllib.request.UnknownHandler()]
        if proxy:
            gestionnaires.insert(0, urllib.request.ProxyHandler())
        for g in gestionnaires:
            o.add_handler(g)
        _OPENERS[cle] = o
    return _OPENERS[cle]


LIMITE_HTML = 10_000_000  # octets décompressés : au-delà, le corps est tronqué (bombe gzip : 29 Ko -> 30 Mo et plus)
LIMITE_SITEMAP = 50_000_000  # un sitemap a le droit d'atteindre 50 Mo décompressé (protocole sitemaps.org)


def decompresser_borne(donnees, encodage, limite_octets=LIMITE_HTML):
    """(octets, tronque) : gzip (plusieurs membres compris) ou deflate décompressé par morceaux (zlib.decompressobj avec
    max_length) ; la sortie ne dépasse jamais limite_octets, tronque vaut vrai si le flux en contenait davantage. Flux illisible :
    les données d'origine, inchangées. Autre encodage (br : aucune bibliothèque standard, et crawl_site ne l'annonce pas) :
    inchangé."""
    enc = (encodage or "").lower().strip()
    if enc not in ("gzip", "x-gzip", "deflate") or not donnees:
        return donnees, False
    tentatives = (16 + zlib.MAX_WBITS,) if enc != "deflate" else (zlib.MAX_WBITS, -zlib.MAX_WBITS)
    for wbits in tentatives:
        sortie, total, tronque, restant, ok = [], 0, False, donnees, True
        d = zlib.decompressobj(wbits)
        try:
            while restant and not tronque:
                morceau, restant = restant[:65536], restant[65536:]
                while morceau and not tronque:
                    place = limite_octets - total
                    out = d.decompress(morceau, place + 1)  # +1 : savoir qu'il en restait
                    if len(out) > place:
                        out, tronque = out[:place], True
                    total += len(out)
                    sortie.append(out)
                    morceau = d.unconsumed_tail
                    if d.eof:  # membre gzip suivant éventuel
                        morceau, restant = d.unused_data + morceau + restant, b""
                        if not morceau:
                            break
                        d = zlib.decompressobj(wbits)
        except zlib.error:
            ok = bool(sortie) and total > 0
        if ok:
            return b"".join(sortie), tronque
    return donnees, False


def decompresser(body, enc):
    return decompresser_borne(body, enc, LIMITE_HTML)[0]


def _echec(url, courant, statut, erreur, chaine, debut, refus=None):
    return {"url": url, "final_url": courant, "status": statut, "error": erreur, "chain": chaine, "headers": {}, "body": b"",
            "raw_bytes": 0, "ttfb": None, "time": round(time.time() - debut, 3), "refus": refus, "tronque": False}


def ouvrir(url, timeout=20, method="GET", max_bytes=8_000_000, ua=None, extra_headers=None, max_hops=MAX_REDIRECTIONS + 1,
           prive_ok=(), resoudre=None, echeance=None, proxy=False, max_decompresse=LIMITE_HTML):
    """GET/HEAD sûr. Redirections suivies à la main (max_hops requêtes au plus : 6 = 5 redirections) ; à chaque saut, le schéma doit
    être http(s) et l'hôte public (ou exempté par prive_ok). Même forme de résultat que crawl_site.fetch, plus « refus » :
    "schema" | "adresse_privee" | None (aucune requête n'est alors partie vers la cible refusée). echeance : instant time.monotonic()
    au-delà duquel plus aucune requête ne part. Jamais de cookie ; Authorization non renvoyé à un autre hôte."""
    chaine, courant, debut, premier = [], url, time.time(), None
    base = {"User-Agent": ua or "AuditSiteAstro/2.1", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate", "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6"}
    supplementaires = {k: v for k, v in (extra_headers or {}).items() if k.lower() not in ("cookie", "host")}
    for _ in range(max_hops):
        cible = adresse_requete(courant)
        if cible is None:
            p = urlsplit(str(courant)) if courant else None
            if p is not None and p.scheme.lower() not in ("http", "https"):
                return _echec(url, courant, 0, "adresse refusée : seuls http et https sont ouverts", chaine, debut, "schema")
            return _echec(url, courant, 0, "URL invalide", chaine, debut)
        hote = hote_de(cible)
        premier = premier or hote
        try:
            port = urlsplit(cible).port
        except ValueError:
            return _echec(url, courant, 0, "URL invalide", chaine, debut)
        etat = classer_hote(hote, port, resoudre, prive_ok)
        if etat == "privee":
            return _echec(url, courant, 0, "adresse non publique refusée", chaine, debut, "adresse_privee")
        if etat == "introuvable":
            try:  # l'erreur réelle du résolveur (nom inexistant ou échec temporaire) : le classement en dépend
                (resoudre or _resoudre)(hote, port)
                erreur = "<urlopen error nom non résolu>"
            except (OSError, UnicodeError) as e:
                erreur = "<urlopen error {0}>".format(e)
            return _echec(url, courant, 0, erreur[:200], chaine, debut)
        delai = timeout
        if echeance is not None:
            delai = min(timeout, echeance - time.monotonic())
            if delai <= 0:
                return _echec(url, courant, 0, "délai global dépassé", chaine, debut)
        entetes = dict(base)
        if hote == premier:
            entetes.update(supplementaires)
        else:
            entetes.update({k: v for k, v in supplementaires.items() if k.lower() not in ("authorization", "proxy-authorization")})
        req = urllib.request.Request(cible, method=method, headers=entetes)
        t_hop = time.time()
        try:
            resp = _opener(proxy).open(req, timeout=delai)
            status, hdrs = resp.status, resp.headers
            ttfb = time.time() - t_hop
            body = resp.read(max_bytes) if method == "GET" else b""
            resp.close()
        except urllib.error.HTTPError as e:
            status, hdrs = e.code, e.headers
            ttfb = time.time() - t_hop
            if 300 <= status < 400 and hdrs.get("Location"):
                chaine.append({"url": courant, "status": status})
                courant = urljoin(cible, hdrs["Location"].strip())
                continue
            try:
                body = e.read(max_bytes) if method == "GET" else b""
            except Exception:
                body = b""
        except Exception as e:  # DNS, TLS, délai...
            r = _echec(url, courant, 0, str(e)[:200], chaine, debut)
            return r
        enc = (hdrs.get("Content-Encoding") or "").lower().strip()
        brut = len(body)
        body, tronque = decompresser_borne(body, enc, max_decompresse)
        return {"url": url, "final_url": cible, "status": status, "error": None, "chain": chaine,
                "headers": {k.lower(): v for k, v in hdrs.items()}, "body": body, "raw_bytes": brut,
                "ttfb": round(ttfb, 3), "time": round(time.time() - debut, 3), "refus": None, "tronque": tronque}
    r = _echec(url, courant, -1, "plus de {0} redirections".format(max_hops), chaine, debut)
    return r
