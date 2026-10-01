#!/usr/bin/env python3
"""
entetes_securite.py — Analyse de la CSP (en-tête et <meta>) et des attributs des cookies, au niveau de MDN HTTP Observatory.

Usage : python3 entetes_securite.py FICHIER_ENTETES PAGE_HTML SCHEMA(http|https) [HOTE]
        python3 entetes_securite.py --meta FICHIER_ENTETES PAGE_HTML      (affiche « oui » ou « non » : CSP <meta> présente ?)
Écrit des lignes du tableau « Contrôle | Valeur | Verdict » de http-checks.md §3. Aucune requête réseau : les en-têtes et la page
déjà téléchargés par http_checks.sh suffisent. Seuls les NOMS des cookies sont écrits, jamais leurs valeurs, et seuls les attributs d'une liste blanche sont affichés.

Marqueur de gravité : une ligne ⚠️ de gravité moyenne se termine par « [moyenne] » dans sa cellule Verdict (T27 : signaux.py le lit).
Gravités (le pipeline lit ❌ = haute, ⚠️ = basse/moyenne, ℹ️ = info, sans signal) :
  script-src 'unsafe-inline' sans nonce/hash/strict-dynamic ........ moyenne (⚠️)
  script-src 'unsafe-inline' avec nonce/hash/strict-dynamic ......... info (ℹ️) : ignoré par les navigateurs modernes
  style-src 'unsafe-inline' sans nonce/hash ......................... basse (⚠️)
  'unsafe-eval', source trop large dans script-src .................. basse (⚠️)
  frame-ancestors dans une CSP <meta> sans X-Frame-Options/en-tête .. moyenne (⚠️, plafonné : jamais ❌)
  cookie de session (sid, session, auth, token) sans HttpOnly/Secure/SameSite ... haute (❌)
  autre cookie sans Secure/SameSite ................................. basse (⚠️) ; sans HttpOnly : info (ℹ️)
"""
import re
import sys
from html.parser import HTMLParser

PROTECTIONS = ("'nonce-", "'sha256-", "'sha384-", "'sha512-")
LARGES = ("*", "http:", "https:", "data:")
# Directives qu'une CSP délivrée par <meta> ignore (spec CSP 3)
DIRECTIVES_META_IGNOREES = ("frame-ancestors", "report-uri", "report-to", "sandbox")
GRAVITES = {"script_unsafe_inline": "moyenne", "unsafe_eval": "basse", "script_source_large": "basse",
            "style_unsafe_inline": "basse", "frame_ancestors_meta": "moyenne"}
# Éléments d'un <head> ; un autre élément ouvert avant </head> (div, p, section…) referme le <head> pour le navigateur
ELEMENTS_HEAD = {"html", "head", "title", "base", "link", "meta", "style", "script", "noscript", "template"}
CONTENEURS_INERTES = ("template", "noscript")  # leur contenu n'est pas du <head> actif (ni script/style, déjà opaques pour le parseur)
ATTRIBUTS_COOKIE = {"secure": "Secure", "httponly": "HttpOnly", "partitioned": "Partitioned", "max-age": "Max-Age", "expires": "Expires"}
# Nom de cookie : jeton RFC 6265 (« : », « [ », espace, « / »… exclus)
NOM_COOKIE = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]{1,60}$")
TAILLE_HEAD = 200000  # seul le <head> compte : le parseur ne lit que les 200 000 premiers caractères, coupés à </head>
# Cookies : session = identifiant de connexion ; mesure = posé pour être lu par JavaScript (HttpOnly impossible par construction)
COOKIE_SESSION = re.compile(r"session|sessid|(?:^|[^a-z])sid(?:$|[^a-z])|[a-z]sid$|auth(?!or)|token|jwt", re.I)
COOKIE_CSRF = re.compile(r"csrf|xsrf", re.I)
COOKIE_MESURE = re.compile(r"^(?:_ga|_gid|_gat|_gcl_|_gac_|_fbp|_fbc|_hj|_pk_|__utm|_clck|_clsk|ajs_|amplitude|mp_|_uet|_scid|_ttp|_tt_|"
                           r"_pin_|_dc_gtm|__hs|hubspotutk|_vwo|_pendo|_cs_|_lr_)", re.I)


class _MetaCsp(HTMLParser):
    """Méta CSP active : <meta http-equiv="Content-Security-Policy"> (exact, sans casse) enfant du <head>. Jamais comptée : commentaire,
    <script>, <style> (contenu opaque pour le parseur), <template>, <noscript>, <body> ou autre élément de corps, Report-Only."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.contenus, self.dans_head, self.inertes = [], True, 0

    def handle_starttag(self, tag, attrs):
        if tag in CONTENEURS_INERTES:
            self.inertes += 1
        elif tag not in ELEMENTS_HEAD:
            self.dans_head = False
        if tag == "meta" and self.dans_head and not self.inertes:
            a = {k.lower(): (v or "") for k, v in attrs}
            if a.get("http-equiv", "").strip().lower() == "content-security-policy" and "content" in a:
                self.contenus.append(a["content"].strip())

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in CONTENEURS_INERTES:
            self.inertes -= 1

    def handle_endtag(self, tag):
        if tag in CONTENEURS_INERTES and self.inertes:
            self.inertes -= 1
        elif tag == "head":
            self.dans_head = False


def _liste(valeur):
    """Une valeur de CSP peut contenir plusieurs politiques séparées par « , » (CSP 3) : le navigateur les applique toutes."""
    return [p.strip() for p in valeur.split(",") if p.strip()]


def politiques(entetes_txt, html):
    pols, xfo = [], False
    for ligne in entetes_txt.splitlines():
        nom, sep, valeur = ligne.partition(":")
        if not sep:
            continue
        nom = nom.strip().lower()
        if nom == "content-security-policy":
            pols.extend(("en-tête", p) for p in _liste(valeur))
        elif nom == "x-frame-options" and valeur.strip():
            xfo = True
    parseur = _MetaCsp()
    head = (html or "")[:TAILLE_HEAD]
    fin = re.search(r"</head\b", head, re.I)
    if fin:
        head = head[:fin.start()]
    try:
        # pas de close() : il rejoue chaque balise ouverte sans « > » (temps quadratique) ; une balise inachevée n'est pas une meta valide
        parseur.feed(head)
    except Exception:  # HTML illisible : on garde ce qui a été lu avant l'erreur
        pass
    for contenu in parseur.contenus:
        pols.extend(("meta", p) for p in _liste(contenu))
    return pols, xfo


def directives(valeur):
    d = {}
    for partie in valeur.split(";"):
        mots = partie.split()
        if mots:
            d.setdefault(mots[0].lower(), [m.lower() for m in mots[1:]])
    return d


def _protege(src):
    """Un nonce, un hash ou 'strict-dynamic' fait ignorer 'unsafe-inline' par les navigateurs modernes (CSP 2/3)."""
    return "'strict-dynamic'" in src or any(s.startswith(PROTECTIONS) for s in src)


def _constats(pols, xfo):
    """[(code, origine, detail)] : un constat par défaut. Les politiques se cumulent (le navigateur les applique toutes) :
    un défaut de script n'est signalé que si TOUTES les politiques qui restreignent les scripts l'ont, car une seule suffit à le neutraliser."""
    ds = [(o, directives(v)) for o, v in pols]
    scripts = [(o, d.get("script-src", d.get("default-src"))) for o, d in ds]
    scripts = [(o, s) for o, s in scripts if s is not None]
    styles = [d.get("style-src", d.get("default-src")) for _, d in ds]
    styles = [s for s in styles if s is not None]

    def inline(s): return "'unsafe-inline'" in s and not _protege(s)
    def large(s): return "'strict-dynamic'" not in s and any(x in LARGES for x in s)
    def evaluation(s): return "'unsafe-eval'" in s

    tous = {nom: bool(scripts) and all(f(s) for _, s in scripts) for nom, f in (("inline", inline), ("large", large), ("eval", evaluation))}
    tous["style"] = bool(styles) and all(inline(s) for s in styles)
    entete_fa = any("frame-ancestors" in d for o, d in ds if o == "en-tête")
    out = []
    for origine, d in ds:
        src = d.get("script-src", d.get("default-src"))
        if src is not None:
            if tous["inline"] and inline(src):
                out.append(("script_unsafe_inline", origine, ""))
            if tous["eval"] and evaluation(src):
                out.append(("unsafe_eval", origine, ""))
            if tous["large"] and large(src):
                out.append(("script_source_large", origine, " ".join(x for x in src if x in LARGES)))
        if "style-src" in d and tous["style"] and inline(d["style-src"]):
            out.append(("style_unsafe_inline", origine, ""))
        if origine == "meta" and "frame-ancestors" in d and not xfo and not entete_fa:
            out.append(("frame_ancestors_meta", origine, ""))
    return out


def analyser_csp(pols, xfo):
    return [(code, origine) for code, origine, _ in _constats(pols, xfo)]


MODELES = {
    "script_unsafe_inline": "| CSP | script-src 'unsafe-inline' sans nonce/hash ({o}) | ⚠️ protège peu contre le XSS [moyenne] |",
    "unsafe_eval": "| CSP | contient 'unsafe-eval' ({o}) | ⚠️ à éviter |",
    "script_source_large": "| CSP | source trop large dans script-src : {l} ({o}) | ⚠️ autorise des scripts de n'importe quel domaine |",
    "style_unsafe_inline": "| CSP | style-src 'unsafe-inline' ({o}) | ⚠️ risque limité : injection de styles, pas de script |",
    # Plafonné à ⚠️ (moyenne) : la CSP <meta> reste utile pour les scripts ; seul l'anti-clickjacking manque
    "frame_ancestors_meta": "| CSP (meta) | frame-ancestors ignoré dans une CSP <meta> | ⚠️ anti-clickjacking inopérant : envoyer "
                            "X-Frame-Options ou frame-ancestors dans l'en-tête HTTP [moyenne] |",
}


def _infos(pols, xfo, constats):
    """Constats sans gravité (ℹ️, jamais un signal) : 'unsafe-inline' neutralisé ; directives que <meta> ne peut pas porter."""
    out = []
    deja = {(c, o) for c, o, _ in constats}
    for origine, valeur in pols:
        d = directives(valeur)
        src = d.get("script-src", d.get("default-src"))
        if src is not None and "'unsafe-inline'" in src and ("script_unsafe_inline", origine) not in deja:
            out.append("| CSP | script-src 'unsafe-inline' neutralisé ({0}) | ℹ️ ignoré par les navigateurs modernes (nonce, hash ou strict-dynamic) |".format(origine))
        if origine == "meta":
            ignorees = [x for x in DIRECTIVES_META_IGNOREES if x in d and not (x == "frame-ancestors" and ("frame_ancestors_meta", origine) in deja)]
            if ignorees:
                out.append("| CSP (meta) | {0} ignorés dans une CSP <meta> | ℹ️ ces directives ne fonctionnent que dans l'en-tête HTTP |"
                           .format(", ".join(ignorees)))
    return out


def lignes_csp(pols, xfo):
    constats = _constats(pols, xfo)
    lignes = [MODELES[c].format(o=o, l=detail) for c, o, detail in constats] + _infos(pols, xfo, constats)
    return list(dict.fromkeys(lignes))


def _est_session(nom):
    n = re.sub(r"^__(?:host|secure)-", "", nom, flags=re.I)
    return not COOKIE_CSRF.search(n) and not COOKIE_MESURE.search(n) and bool(COOKIE_SESSION.search(n))


def _attributs_affichables(attributs, hote=""):
    """Liste blanche : aucun attribut inconnu ni valeur libre n'est recopié (le rapport est partagé)."""
    out = []
    for a in attributs:
        cle, _, val = a.partition("=")
        cle, val = cle.strip().lower(), val.strip()
        if cle in ATTRIBUTS_COOKIE:
            out.append(ATTRIBUTS_COOKIE[cle])
        elif cle == "samesite" and val.lower() in ("strict", "lax", "none"):
            out.append("SameSite=" + val.capitalize())
        elif cle == "path":
            out.append("Path=" + ("/" if val == "/" else "…"))  # seul « / » compte pour l'audit (préfixe __Host-)
        elif cle == "domain":
            d = val.lstrip(".").lower()
            out.append("Domain=" + (d if hote and d == hote.lower() else "…"))  # le domaine n'est écrit que s'il est celui de l'audit
    return out


def lignes_cookies(entetes_txt, https, hote=""):
    out = []
    for ligne in entetes_txt.splitlines():
        nom, sep, valeur = ligne.partition(":")
        if not sep or nom.strip().lower() != "set-cookie":
            continue
        morceaux = [m.strip() for m in valeur.split(";")]
        premier, egal, _ = morceaux[0].partition("=")  # la valeur (après « = ») n'est jamais conservée
        cookie = premier.strip() if egal and NOM_COOKIE.match(premier.strip()) else ""  # sans « = » : c'est une valeur, pas un nom
        attributs = [m for m in morceaux[1:] if m]
        cles = {a.split("=", 1)[0].strip().lower(): (a.split("=", 1)[1].strip() if "=" in a else "") for a in attributs}
        age = cles.get("max-age", "")
        if (age.lstrip("-").isdigit() and int(age) <= 0) or "1970" in cles.get("expires", ""):
            continue  # cookie supprimé par le serveur
        session = bool(cookie) and _est_session(cookie)
        mesure = bool(COOKIE_MESURE.search(cookie))
        marque = "❌" if session else "⚠️"
        verdicts = []
        if not cookie:
            verdicts.append("⚠️ cookie sans nom (en-tête Set-Cookie mal formé)")
        if https and "secure" not in cles:
            verdicts.append(marque + " sans Secure")
        if cles.get("samesite", "").lower() not in ("strict", "lax", "none"):
            verdicts.append(marque + " sans SameSite")
        elif cles["samesite"].lower() == "none" and "secure" not in cles and not https:
            verdicts.append(marque + " SameSite=None sans Secure (refusé par les navigateurs)")
        bas = cookie.lower()
        if bas.startswith("__host-") and ("secure" not in cles or cles.get("path") != "/" or "domain" in cles):
            verdicts.append("⚠️ préfixe __Host- non respecté (Path=/, Secure, sans Domain)")
        elif bas.startswith("__secure-") and "secure" not in cles and not https:
            verdicts.append("⚠️ préfixe __Secure- sans Secure")
        if "httponly" not in cles:
            if session:
                verdicts.append("❌ sans HttpOnly (cookie de session)")
            elif mesure:
                verdicts.append("ℹ️ sans HttpOnly (normal : cookie de mesure lu par JavaScript)")
            else:
                verdicts.append("ℹ️ sans HttpOnly (normal s'il est lu par JavaScript)")
        out.append("| Cookie {0} | {1} | {2} |".format(cookie.replace("|", "/") or "sans nom", "; ".join(_attributs_affichables(attributs, hote)) or "—", " ; ".join(verdicts) or "✅"))
    return list(dict.fromkeys(out))[:30]


def main():
    if sys.argv[1:2] == ["--meta"]:  # « oui » si la page porte une CSP <meta> : sert au verdict de la ligne content-security-policy
        try:
            html = open(sys.argv[3], encoding="utf-8", errors="replace").read()
        except (OSError, IndexError):
            html = ""
        print("oui" if any(o == "meta" for o, _ in politiques("", html)[0]) else "non")
        return
    try:
        entetes = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    except (OSError, IndexError):
        return
    try:
        html = open(sys.argv[2], encoding="utf-8", errors="replace").read()
    except (OSError, IndexError):
        html = ""
    pols, xfo = politiques(entetes, html)
    hote = sys.argv[4] if len(sys.argv) > 4 else ""
    for l in lignes_csp(pols, xfo) + lignes_cookies(entetes, https=(sys.argv[3] if len(sys.argv) > 3 else "https") == "https", hote=hote):
        print(l)


if __name__ == "__main__":
    main()
