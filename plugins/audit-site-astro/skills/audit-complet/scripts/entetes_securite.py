#!/usr/bin/env python3
"""
entetes_securite.py — Analyse de la CSP (en-tête et <meta>) et des attributs des cookies, au niveau de MDN HTTP Observatory.

Usage : python3 entetes_securite.py FICHIER_ENTETES PAGE_HTML SCHEMA(http|https)
Écrit des lignes du tableau « Contrôle | Valeur | Verdict » de http-checks.md §3. Aucune requête réseau : les en-têtes et la page
déjà téléchargés par http_checks.sh suffisent. Seuls les NOMS des cookies sont écrits, jamais leurs valeurs.

Gravités (le pipeline lit ❌ = haute, ⚠️ = basse/moyenne, ℹ️ = info, sans signal) :
  script-src 'unsafe-inline' sans nonce/hash/strict-dynamic ........ moyenne (⚠️)
  script-src 'unsafe-inline' avec nonce/hash/strict-dynamic ......... info (ℹ️) : ignoré par les navigateurs modernes
  style-src 'unsafe-inline' sans nonce/hash ......................... basse (⚠️)
  'unsafe-eval', source trop large dans script-src .................. basse (⚠️)
  frame-ancestors dans une CSP <meta> sans X-Frame-Options/en-tête .. moyenne (⚠️, plafonné : jamais ❌)
  cookie de session (sid, session, auth, token) sans HttpOnly/Secure/SameSite ... haute (❌)
  autre cookie sans Secure/SameSite ................................. basse (⚠️) ; sans HttpOnly : info (ℹ️)
"""
import html as _html
import re
import sys

PROTECTIONS = ("'nonce-", "'sha256-", "'sha384-", "'sha512-")
LARGES = ("*", "http:", "https:", "data:")
# Directives qu'une CSP délivrée par <meta> ignore (spec CSP 3)
DIRECTIVES_META_IGNOREES = ("frame-ancestors", "report-uri", "report-to", "sandbox")
GRAVITES = {"script_unsafe_inline": "moyenne", "unsafe_eval": "basse", "script_source_large": "basse",
            "style_unsafe_inline": "basse", "frame_ancestors_meta": "moyenne"}
META_CSP = re.compile(r"<meta\b[^>]*http-equiv\s*=\s*[\"']?content-security-policy[\"']?[^>]*>", re.I)
CONTENU = re.compile(r"""\bcontent\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
# Cookies : session = identifiant de connexion ; mesure = posé pour être lu par JavaScript (HttpOnly impossible par construction)
COOKIE_SESSION = re.compile(r"session|sessid|(?:^|[^a-z])sid(?:$|[^a-z])|[a-z]sid$|auth(?!or)|token|jwt", re.I)
COOKIE_CSRF = re.compile(r"csrf|xsrf", re.I)
COOKIE_MESURE = re.compile(r"^(?:_ga|_gid|_gat|_gcl_|_gac_|_fbp|_fbc|_hj|_pk_|__utm|_clck|_clsk|ajs_|amplitude|mp_|_uet|_scid|_ttp|_tt_|"
                           r"_pin_|_dc_gtm|__hs|hubspotutk|_vwo|_pendo|_cs_|_lr_)", re.I)


def politiques(entetes_txt, html):
    pols, xfo = [], False
    for ligne in entetes_txt.splitlines():
        nom, sep, valeur = ligne.partition(":")
        if not sep:
            continue
        nom = nom.strip().lower()
        if nom == "content-security-policy":
            pols.append(("en-tête", valeur.strip()))
        elif nom == "x-frame-options" and valeur.strip():
            xfo = True
    for m in META_CSP.finditer(html or ""):
        c = CONTENU.search(m.group(0))
        if c:
            pols.append(("meta", _html.unescape(c.group(1) if c.group(1) is not None else c.group(2)).strip()))
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
    "script_unsafe_inline": "| CSP | script-src 'unsafe-inline' sans nonce/hash ({o}) | ⚠️ protège peu contre le XSS |",
    "unsafe_eval": "| CSP | contient 'unsafe-eval' ({o}) | ⚠️ à éviter |",
    "script_source_large": "| CSP | source trop large dans script-src : {l} ({o}) | ⚠️ autorise des scripts de n'importe quel domaine |",
    "style_unsafe_inline": "| CSP | style-src 'unsafe-inline' ({o}) | ⚠️ risque limité : injection de styles, pas de script |",
    # Plafonné à ⚠️ (moyenne) : la CSP <meta> reste utile pour les scripts ; seul l'anti-clickjacking manque
    "frame_ancestors_meta": "| CSP (meta) | frame-ancestors ignoré dans une CSP <meta> | ⚠️ anti-clickjacking inopérant : envoyer "
                            "X-Frame-Options ou frame-ancestors dans l'en-tête HTTP |",
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


def lignes_cookies(entetes_txt, https):
    out = []
    for ligne in entetes_txt.splitlines():
        nom, sep, valeur = ligne.partition(":")
        if not sep or nom.strip().lower() != "set-cookie":
            continue
        morceaux = [m.strip() for m in valeur.split(";")]
        cookie = morceaux[0].split("=", 1)[0].strip()  # le NOM seulement : la valeur n'est jamais conservée
        attributs = [m.replace("|", "/") for m in morceaux[1:] if m]
        cles = {a.split("=", 1)[0].strip().lower(): (a.split("=", 1)[1].strip() if "=" in a else "") for a in attributs}
        age = cles.get("max-age", "")
        if (age.lstrip("-").isdigit() and int(age) <= 0) or "1970" in cles.get("expires", ""):
            continue  # cookie supprimé par le serveur
        session = _est_session(cookie)
        mesure = bool(COOKIE_MESURE.search(cookie))
        marque = "❌" if session else "⚠️"
        verdicts = []
        if https and "secure" not in cles:
            verdicts.append(marque + " sans Secure")
        if "samesite" not in cles:
            verdicts.append(marque + " sans SameSite")
        elif cles["samesite"].lower() == "none" and "secure" not in cles and not https:
            verdicts.append(marque + " SameSite=None sans Secure (refusé par les navigateurs)")
        if cookie.startswith("__Host-") and ("secure" not in cles or cles.get("path") != "/" or "domain" in cles):
            verdicts.append("⚠️ préfixe __Host- non respecté (Path=/, Secure, sans Domain)")
        elif cookie.startswith("__Secure-") and "secure" not in cles:
            verdicts.append("⚠️ préfixe __Secure- sans Secure")
        if "httponly" not in cles:
            if session:
                verdicts.append("❌ sans HttpOnly (cookie de session)")
            elif mesure:
                verdicts.append("ℹ️ sans HttpOnly (normal : cookie de mesure lu par JavaScript)")
            else:
                verdicts.append("ℹ️ sans HttpOnly (normal s'il est lu par JavaScript)")
        out.append("| Cookie {0} | {1} | {2} |".format(cookie.replace("|", "/")[:60], "; ".join(attributs)[:120] or "—", " ; ".join(verdicts) or "✅"))
    return list(dict.fromkeys(out))[:30]


def main():
    try:
        entetes = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    except (OSError, IndexError):
        return
    try:
        html = open(sys.argv[2], encoding="utf-8", errors="replace").read()
    except (OSError, IndexError):
        html = ""
    pols, xfo = politiques(entetes, html)
    for l in lignes_csp(pols, xfo) + lignes_cookies(entetes, https=(sys.argv[3] if len(sys.argv) > 3 else "https") == "https"):
        print(l)


if __name__ == "__main__":
    main()
