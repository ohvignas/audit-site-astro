#!/usr/bin/env python3
"""
html_observateurs.py — Contrôles HTML du crawl : une lecture du HTML partagée par les onze modules (en plus de celle de
PageParser, dans crawl_site.py) (Python 3.9+, stdlib).

crawl_site.py appelle, pour chaque page HTML analysée :
  analyser(html, entetes, url)  -> {nom_module: résultat JSON}   (pages.json, clé « obs » de chaque page)
puis, une fois le crawl terminé :
  apres_crawl(pages, ctx)       -> requêtes réseau éventuelles des modules (liens externes, ressources…)
  issues(pages, add, ctx)       -> constats ajoutés à issues.json par add(clé, libellé, sévérité, exemple, n=, domaine=)

Un module de MODULES fournit NOM, une classe Observateur (sous-classe de Observateur) et, au besoin, apres_crawl(pages, ctx)
et issues(pages, add, ctx). Une erreur dans un module n'interrompt jamais le crawl, qu'elle survienne à l'import, à l'instanciation, pendant la lecture, dans
resultat() (un résultat qui n'est pas du JSON strict est remplacé par {"erreur": …}), dans apres_crawl ou dans issues : elle est
notée dans obs[nom] = {"erreur": "Type: message"} et, avec le nom du module, dans ctx["meta"]["erreurs_modules"].
Format commun des résultats : listes de {"signature": str, "n": int, …} ; collecter_groupes() et ajouter_groupes() regroupent
les occurrences de tout le site par signature de composant (128 icônes identiques = 1 constat).

Aucun secret dans les sorties (règle de sécurité) : une adresse qui entre dans une signature, un exemple, issues.json, pages.json ou
summary.md passe par url_sans_secret() (schéma, hôte sans identifiants, chemin ; ni requête, ni fragment, ni paramètre de matrice
« ;jsessionid=… », ni « %3F » / « %23 » encodés ; longueur bornée) ; un texte libre qui peut contenir une adresse (alt, aria-label,
extrait de phrase) par texte_sans_secret(). Les URL des pages du site audité (url de la page) passent par url_page_publique() :
même nettoyage, mais la requête est gardée avec tous ses noms de paramètres : la valeur de ceux dont le nom ressemble à un secret (token,
key, sig, session, sid, auth, code, password, bypass…) ou dont la valeur est opaque (clé AIza…, sk-…, JWT, hexadécimal, base64, courriel)
devient « session=…3f2a ». pages.json et pages.csv ne sont JAMAIS réécrits : ils gardent les vraies URL, que d'autres étapes interrogent.
analyser() et issues() repassent par assainir_sortie() sur tout ce que rend un module : un module qui oublie le helper ne fait
pas fuiter une adresse complète, mais le helper reste la règle (il évite aussi de perdre la signature utile).
"""
import hashlib
import importlib
import json
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import unquote_plus, urlsplit

MODULES = ("a11y_svg", "a11y_noms", "a11y_structure", "a11y_textes", "contenu_demo", "fuites_rendu", "tete_html",
           "securite_html", "liens_externes", "ressources_site", "donnees_structurees")

# Éléments sans balise fermante (ne s'empilent pas) ; styles qui masquent un élément
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
STYLE_MASQUE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)
# Classes utilitaires qui masquent (Tailwind, Bootstrap, Bulma) : jetons entiers ; sr-only n'en fait PAS partie
# (masqué visuellement mais lu par les lecteurs d'écran : un libellé reste requis)
CLASSES_MASQUE = {"hidden", "d-none", "is-hidden", "invisible"}
# « hidden md:block » : masqué sur mobile seulement, visible ensuite → pas masqué
CLASSE_REAFFICHE = re.compile(r"^(sm|md|lg|xl|2xl):(block|inline|inline-block|flex|inline-flex|grid|inline-grid|table|contents|visible)$")
SANS_TEXTE_VISIBLE = {"script", "style", "noscript", "template", "textarea", "title"}


# --------------------------------------------------------------------------- adresses sans secret

LONGUEUR_URL = 100          # signatures et exemples
LONGUEUR_URL_PAGE = 300     # URL de page du site audité (constats, summary.md)
SCHEMAS_OPAQUES = {"data", "javascript", "blob", "about", "vbscript", "file"}  # le reste de l'adresse n'a aucune valeur de diagnostic
# Le chemin s'arrête au premier « ; » (paramètres de matrice : ;jsessionid=…) ou au premier « ? » / « # » / « ; » encodé (%3F, %23, %3B,
# éventuellement encodés plusieurs fois : %253F) : ce qui suit est une requête ou un fragment déguisés en chemin
COUPE_CHEMIN = re.compile(r";|%(?:25)*(?:3[fF]|23|3[bB])")
# Nom de paramètre qui ressemble à un secret : mots longs en sous-chaîne, mots courts seulement comme mot entier (« key » dans
# « api_key », « accessKey », pas dans « keyword »), ou fin de nom (« …key », « …sig »). Le nom est gardé dans les constats, la valeur masquée.
NOMS_SECRETS_LONGS = ("token", "secret", "passw", "session", "signature", "credential", "bearer", "apikey", "jwt", "cookie",
                      "jeton", "motdepasse", "bypass", "vercel")
NOMS_SECRETS_COURTS = {"key", "cle", "clef", "sig", "sid", "auth", "code", "pwd", "mdp", "pass", "otp", "csrf", "xsrf", "nonce", "hmac",
                       "ticket", "sas", "oauth", "sso", "share", "invite", "magic", "reset"}
FINS_SECRETES = ("key", "sig", "sid", "auth", "pwd")
# Paramètres sans risque, lisibles tels quels (même quand la valeur est longue : un slug n'est pas un secret)
PARAMETRES_INOFFENSIFS = re.compile(r"(?:utm_\w+|page|tab|lang|locale|q|sort|order|ref|limit|offset|per_page)\Z", re.I)
# Formats de clés connus, avec borne gauche (risk-, task-, ask-, desk-, disk- ne sont pas des clés « sk- ») : Google (AIza), OpenAI
# (sk-, qui mêle chiffres, majuscules et minuscules), Stripe, GitHub, Slack, AWS, JWT
FORMATS_CLES = (r"(?<![A-Za-z0-9])AIza[\w-]{20,}",
                r"(?<![A-Za-z0-9])sk-(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Z])(?=[A-Za-z0-9_-]*[a-z])[A-Za-z0-9_-]{20,}",
                r"(?<![A-Za-z0-9])[sp]k_(?:live|test)_\w{8,}", r"(?<![A-Za-z0-9])gh[pousr]_\w{20,}",
                r"(?<![A-Za-z0-9])xox[abprs]-[\w-]{10,}", r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}",
                r"(?<![A-Za-z0-9])eyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]*")
CLE_CONNUE = re.compile("|".join(FORMATS_CLES))
COURRIEL = re.compile(r"[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}\Z")
# Toute adresse « schéma://… » (http, postgres, mongodb+srv, redis, amqp…)
URL_DANS_TEXTE = re.compile(r"(?i)\b[a-z][a-z0-9+.-]{1,15}://[^\s\"'<>\\]+")
# nom=valeur : borne gauche pour rester linéaire sur une longue suite sans espace (un blob base64 de 80 000 caractères)
PAIRE_DANS_TEXTE = re.compile(r"(?<![\w.\-\[\]])([\w.\-\[\]]{1,64})=([^\s&;\"'<>]+)")
JSON_DANS_TEXTE = re.compile(r'"([\w.\-]{1,64})"\s*:\s*"([^"\\]{1,200})"')
PORTEUR_DANS_TEXTE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
PONCTUATION_FINALE = ".,;:!?)]}»”"
PASSES_DECODAGE = 5


def _nom_secret(nom):
    """Vrai si le nom d'un paramètre (ou d'un attribut) ressemble à un secret."""
    nom = unicodedata.normalize("NFKC", nom)  # ｔｏｋｅｎ (pleine chasse) -> token
    n = nom.lower()
    if any(m in n for m in NOMS_SECRETS_LONGS):
        return True
    morceaux = re.split(r"[^a-z0-9]+", re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", nom).lower())
    return any(m in NOMS_SECRETS_COURTS for m in morceaux) or n.endswith(FINS_SECRETES)


def _opaque(x, mini=20, mini_hex=None):
    """Valeur opaque (jeton, condensat, base64) : `mini` caractères ou plus, sans séparateur de mots, hexadécimale (chiffres et lettres)
    ou mêlant chiffres, majuscules et minuscules. Un slug en minuscules à tirets (formation-no-code-2024) n'est jamais opaque."""
    if not re.fullmatch(r"[A-Za-z0-9+/=_-]+", x) or not any(c.isdigit() for c in x):
        return False
    if re.fullmatch(r"[0-9a-fA-F]+", x):
        return len(x) >= (mini_hex or mini) and any(c.isalpha() for c in x)
    return len(x) >= mini and any(c.isupper() for c in x) and any(c.islower() for c in x)


def _decodages(valeur):
    """La valeur puis ses décodages successifs jusqu'au point fixe (5 passes au plus) : une requête imbriquée est parfois encodée
    plusieurs fois (?r=%2Fcb%253Fapi_key%253D…)."""
    vus = [valeur]
    for _ in range(PASSES_DECODAGE):
        n = unquote_plus(vus[-1])
        if n == vus[-1]:
            break
        vus.append(n)
    return vus


def _valeur_secrete(valeur, opaque=True):
    """Valeur de paramètre à masquer : clé de format connu, courriel, valeur opaque (sauf paramètre inoffensif, opaque=False), ou
    requête imbriquée dont un nom ressemble à un secret, à n'importe quel niveau d'encodage."""
    for v in _decodages(valeur):
        if CLE_CONNUE.search(v) or COURRIEL.match(v.strip()) or (opaque and _opaque(v)):
            return True
        if any(_nom_secret(m.group(1)) for m in PAIRE_DANS_TEXTE.finditer(v)):
            return True
    return False


def _masque(valeur):
    """« … » et 4 caractères d'un condensat : deux valeurs différentes restent distinguables, sans rien révéler."""
    return "…" + hashlib.sha256(valeur.encode("utf-8", "replace")).hexdigest()[:4]


def _segment_secret(seg):
    """Segment de chemin qui est un secret (webhook, lien de partage ou de réinitialisation, clé dans l'URL) : format de clé connu,
    valeur opaque de 24 caractères ou plus (base64 : = + - _ compris), hexadécimal de 32 caractères ou plus. Les noms de fichiers à
    condensat (index.4f3a9c.js) et les slugs à tirets restent intacts."""
    return bool(CLE_CONNUE.search(seg)) or _opaque(seg, 24, 32)


def _chemin_net(chemin):
    chemin = COUPE_CHEMIN.split(chemin, 1)[0]
    return "/".join("…" if _segment_secret(s) else s for s in chemin.split("/"))


def _borner(texte, n):
    return texte if len(texte) <= n else texte[:max(n - 1, 0)] + "…"


def _decouper(url):
    """(urlsplit, texte nettoyé), ou (None, texte) si l'adresse est illisible (« http://[invalide »). Comme un navigateur : tabulations et
    sauts de ligne retirés (« java\\nscript: »), « \\ » lu comme « / » dans une adresse http(s)."""
    u = re.sub(r"[\t\r\n]", "", str(url or ""))
    u = "".join(c for c in " ".join(u.split()) if c.isprintable())
    if re.match(r"(?i)(?:[a-z][a-z0-9+.-]*:)?[/\\]{2}|(?:https?|wss?|ftp):[/\\]", u):
        u = u.replace("\\", "/")
    try:
        return urlsplit(u), u
    except ValueError:
        return None, u


def _base(p, avec_schema):
    """schéma://hôte (sans identifiants), « //hôte » ou « hôte » ; vide pour une adresse relative."""
    hote = p.netloc.rpartition("@")[2].lower()
    if not hote:
        return ""
    if not avec_schema:
        return hote
    return (p.scheme.lower() + "://" if p.scheme else "//") + hote


def _opaque_schema(p):
    """Adresse sans hôte à traiter à part : schéma opaque (data:, javascript:…), mailto: / tel: (adresse sans « ?objet=… »)."""
    schema = p.scheme.lower()
    if schema in SCHEMAS_OPAQUES:
        return schema + ":"
    if schema in ("mailto", "tel"):
        return schema + ":" + COUPE_CHEMIN.split(p.path, 1)[0]
    return None


def _ancre(u):
    """Ancre seule (« #contenu ») : gardée si c'est un identifiant de page ; « # » si elle ressemble à une valeur (#access_token=…)."""
    ident = u[1:]
    if not ident or "=" in ident or "&" in ident or len(ident) > 40 or _valeur_secrete(ident):
        return "#"
    return u


def url_sans_secret(url, longueur=LONGUEUR_URL, avec_schema=True):
    """Adresse sans le moindre secret, pour les signatures et exemples de modules : schéma, hôte (sans identifiants user:pass@) et
    chemin. Ni requête, ni fragment (ils portent les jetons, clés d'API et signatures), chemin coupé aux paramètres de matrice
    « ;jsessionid=… » et aux « %3F » / « %23 » encodés, segment qui ressemble à une clé masqué (« … »), longueur bornée (« … »).
    Une adresse relative reste relative, une ancre seule garde son identifiant (« #contenu »), data: / javascript: / blob: deviennent
    « data: »… avec_schema=False : « hôte/chemin » (signature d'une iframe)."""
    if not url or not str(url).strip():
        return ""
    p, u = _decouper(url)
    if p is None:
        return "adresse illisible"
    if u.startswith("#"):
        return _ancre(u)
    opaque = _opaque_schema(p)
    if opaque is not None:
        return _borner(opaque, longueur)
    base = _base(p, avec_schema)
    chemin = _chemin_net(p.path)
    if not base and p.scheme:  # « foo:bar » : schéma inconnu sans hôte
        return _borner(p.scheme.lower() + ":" + chemin, longueur)
    return _borner(base + chemin, longueur)


def url_page_publique(url, longueur=LONGUEUR_URL_PAGE):
    """URL d'une page du site audité telle qu'on peut l'écrire dans un constat, summary.md ou la sortie d'erreur (jamais dans
    pages.json / pages.csv : ces données gardent les vraies URL, d'autres étapes les interrogent). Identifiants, fragment, paramètres de
    matrice et segments secrets retirés ; la requête est gardée avec TOUS ses paramètres, mais la valeur de ceux qui ressemblent à un
    secret (nom : token, key, sig, signature, session, sid, auth, bypass… ; valeur : clé de format connu, courriel, valeur opaque de
    20 caractères ou plus) devient « … » suivi de 4 caractères d'un condensat : session=…3f2a. ?page=2, ?tab=prix, ?utm_campaign=un-slug
    restent lisibles."""
    if not url or not str(url).strip():
        return "" if not url else str(url)
    p, u = _decouper(url)
    if p is None:
        return "adresse illisible"
    if u.startswith("#"):
        return _ancre(u)
    opaque = _opaque_schema(p)
    if opaque is not None:
        return _borner(opaque, longueur)
    gardes = []
    for morceau in p.query.split("&"):
        if not morceau:
            continue
        nom, egal, valeur = morceau.partition("=")
        n = unquote_plus(nom)
        if CLE_CONNUE.search(n):  # la clé elle-même sert de nom de paramètre
            gardes.append("…=" + _masque(valeur) if egal else _masque(morceau))
        elif not egal:
            gardes.append(_masque(morceau) if _valeur_secrete(morceau) else morceau)
        elif _nom_secret(n) or _valeur_secrete(valeur, opaque=PARAMETRES_INOFFENSIFS.match(n) is None):
            gardes.append(nom + "=" + _masque(valeur))
        else:
            gardes.append(morceau)
    base = _base(p, True)
    chemin = _chemin_net(p.path)
    if not base and p.scheme:
        return _borner(p.scheme.lower() + ":" + chemin, longueur)
    return _borner(base + chemin + ("?" + "&".join(gardes) if gardes else ""), longueur)


def texte_sans_secret(texte, adresse=url_sans_secret):
    """Texte libre (alt, aria-label, extrait de phrase, message d'erreur) sans secret : chaque adresse schéma://… devient `adresse(url)`
    (url_sans_secret par défaut ; identifiants retirés aussi pour postgres://, redis://…), « nom=valeur », « "nom": "valeur" » et
    « Bearer valeur » à nom ou jeton secret deviennent « nom=… », une clé de format connu (AIza…, sk-…, ghp_…, JWT) devient « … »."""
    def remplacer(m):
        brut = m.group(0)
        coupe = len(brut.rstrip(PONCTUATION_FINALE))
        return adresse(brut[:coupe]) + brut[coupe:]

    def paire(m):
        # « Disallow: /*?session=* » (motif de robots.txt) ou une valeur déjà masquée : rien à cacher
        if m.group(2).startswith("…") or not _nom_secret(m.group(1)) or re.fullmatch(r"[*$.+?^|()\[\]\\]+", m.group(2)):
            return m.group(0)
        return m.group(1) + "=…"

    def json_(m):
        return '"{0}": "…"'.format(m.group(1)) if _nom_secret(m.group(1)) and m.group(2) != "…" else m.group(0)

    t = URL_DANS_TEXTE.sub(remplacer, str(texte))
    t = JSON_DANS_TEXTE.sub(json_, PAIRE_DANS_TEXTE.sub(paire, t))
    return CLE_CONNUE.sub("…", PORTEUR_DANS_TEXTE.sub("Bearer …", t))


def _parcourir(o, fn, cle=None):
    if isinstance(o, dict):
        sortie = {}
        for k, v in o.items():
            nk = fn(k, None) if isinstance(k, str) and URL_DANS_TEXTE.match(k) else k
            base, i = nk, 2
            while nk in sortie:  # deux adresses qui n'en font plus qu'une : aucune entrée n'est perdue
                nk, i = "{0} ({1})".format(base, i), i + 1
            sortie[nk] = _parcourir(v, fn, k)
        return sortie
    if isinstance(o, (list, tuple)):
        return [_parcourir(v, fn, cle) for v in o]
    if isinstance(o, str):
        return fn(o, cle)
    return o


# Champs qui portent une adresse pouvant être relative (les adresses absolues sont reconnues seules)
CHAMPS_ADRESSE = {"img_srcs", "hreflang", "canonicals", "canonical", "src", "href", "mixed_content"}


def _chaine_publique(s, cle):
    if re.match(r"(?i)(?:https?:)?//", s) and not any(c.isspace() for c in s):
        return url_page_publique(s)
    if cle in CHAMPS_ADRESSE and s and not any(c.isspace() for c in s):
        return url_page_publique(s)
    return texte_sans_secret(s, adresse=url_page_publique)


def assainir_sortie(o):
    """Copie de `o` (dict, listes, chaînes JSON) sans secret, pour les constats (issues.json), summary.md, la sortie d'erreur et les
    résultats de modules : une chaîne qui est une adresse (ou qui en contient) passe par url_page_publique (noms de paramètres gardés,
    valeurs secrètes masquées) ; les clés de dictionnaire qui sont des adresses aussi. À NE PAS appliquer à pages.json ni pages.csv :
    ces données gardent les vraies URL, que Lighthouse, geo_check et http_checks interrogent. L'original n'est pas modifié."""
    return _parcourir(o, _chaine_publique)


def _erreur(e):
    return "{0}: {1}".format(type(e).__name__, e)[:200]


def masque(tag, a):
    """Élément absent de l'arbre d'accessibilité (ignoré par axe/Lighthouse) : hidden, aria-hidden, style, classe
    utilitaire de masquage, <template>, <noscript>, <dialog> fermé."""
    classes = a.get("class", "").split()
    par_classe = bool(CLASSES_MASQUE.intersection(classes)) and not any(CLASSE_REAFFICHE.match(c) for c in classes)
    return (tag in ("template", "noscript") or (tag == "dialog" and "open" not in a) or "hidden" in a
            or a.get("aria-hidden", "").lower() == "true" or bool(STYLE_MASQUE.search(a.get("style", "")))
            or par_classe)


class Observateur:
    """Base des observateurs : méthodes vides, à surcharger.

    Surcharger debut, fin et texte DANS LA CLASSE : le diffuseur n'appelle un observateur que pour les méthodes que sa classe
    surcharge (hérité d'une classe intermédiaire compris). Une méthode non surchargée n'est jamais appelée, et une méthode posée
    sur l'instance (self.texte = …) est ignorée. Le texte d'un même nœud peut arriver en plusieurs appels de texte() (autour des
    commentaires HTML, par exemple) : accumuler soi-même."""

    def __init__(self, entetes, url):
        self.entetes, self.url = entetes or {}, url

    def debut(self, noeud, pile):
        pass

    def fin(self, noeud, pile):
        pass

    def texte(self, donnees, pile):
        pass

    def resultat(self):
        return {}


def dans(pile, *tags):
    return any(n["tag"] in tags for n in pile)


def visible(pile):
    """Texte hors des éléments sans texte rendu (script, style, noscript, template, textarea, title) et hors d'un ancêtre masqué
    (hidden, aria-hidden, display:none…) : logique de l'arbre d'accessibilité, pas exactement de l'écran (sr-only est visible,
    aria-hidden ne l'est pas)."""
    return not (pile and pile[-1]["masque"]) and not dans(pile, *SANS_TEXTE_VISIBLE)


EVENEMENTS = ("debut", "fin", "texte")


def _surcharge(o, methode):
    f = getattr(type(o), methode, None)
    return f is not None and f is not getattr(Observateur, methode)


class Diffuseur(HTMLParser):
    """Parcourt le HTML une fois et transmet les événements à chaque observateur, avec la pile des ancêtres.

    Écarts connus avec un navigateur (identiques à PageParser) : un élément non vide écrit en balise auto-fermante hors SVG
    (<a href="/x" />) est fermé aussitôt ; pas de fermeture implicite à la HTML5 (<p> avant <div>) ; les noms de balises et
    d'attributs sont en minuscules (viewbox, clippath, foreignobject) ; pour un attribut en double, la première valeur l'emporte."""

    def __init__(self, observateurs):
        super().__init__(convert_charrefs=True)
        self.obs, self.pile, self.erreurs = list(observateurs), [], {}
        # Table d'envoi par événement : seuls les observateurs qui surchargent la méthode sont appelés (un module qui
        # n'écoute que <a> et <svg> ne coûte rien sur les événements de texte)
        self._envoi = {m: [(o, getattr(o, m)) for o in self.obs if _surcharge(o, m)] for m in EVENEMENTS}

    def _notifier(self, methode, *args):
        for o, f in list(self._envoi[methode]):
            try:
                f(*args)
            except Exception as e:  # observateur fautif : retiré partout, les autres continuent
                self.erreurs[id(o)] = _erreur(e)
                self.obs.remove(o)
                for m in EVENEMENTS:
                    self._envoi[m] = [c for c in self._envoi[m] if c[0] is not o]

    def _noeud(self, tag, attrs):
        a = {}
        for k, v in attrs:
            a.setdefault(k.lower(), v or "")  # attribut en double : le premier compte, comme dans un navigateur
        return {"tag": tag, "a": a, "masque": bool(self.pile and self.pile[-1]["masque"]) or masque(tag, a)}

    def handle_starttag(self, tag, attrs):
        noeud = self._noeud(tag, attrs)
        self._notifier("debut", noeud, self.pile)
        if tag in VOID_TAGS:
            self._notifier("fin", noeud, self.pile)
        else:
            self.pile.append(noeud)

    def handle_startendtag(self, tag, attrs):
        noeud = self._noeud(tag, attrs)
        self._notifier("debut", noeud, self.pile)
        self._notifier("fin", noeud, self.pile)

    def handle_endtag(self, tag):
        for i in range(len(self.pile) - 1, -1, -1):
            if self.pile[i]["tag"] == tag:  # ferme aussi les éléments laissés ouverts (<li>, <p>…)
                while len(self.pile) > i:
                    self._notifier("fin", self.pile.pop(), self.pile)
                return

    def handle_data(self, data):
        self._notifier("texte", data, self.pile)

    def analyser(self, html):
        try:
            self.feed(html)
            self.close()
        except Exception as e:  # HTML impossible à lire jusqu'au bout : on garde ce qui a été vu
            for o in self.obs:
                self.erreurs.setdefault(id(o), "parse: {0}".format(e)[:200])
        while self.pile:
            self._notifier("fin", self.pile.pop(), self.pile)


_CHARGES = []
_ERREURS_IMPORT = {}


def modules():
    """[(nom, module)] des modules importés. Un module qui ne s'importe pas (ImportError, SyntaxError sous une version de
    Python plus ancienne…) est écarté et noté dans _ERREURS_IMPORT : les autres continuent."""
    if not _CHARGES and not _ERREURS_IMPORT:
        for nom in MODULES:
            try:
                _CHARGES.append((nom, importlib.import_module(nom)))
            except Exception as e:  # SyntaxError, ImportError, erreur à l'exécution du module
                _ERREURS_IMPORT[nom] = _erreur(e)
    return _CHARGES


def analyser(html, entetes, url, modules=None, erreurs=None):
    """{nom: résultat} pour chaque module. `erreurs` (liste, facultatif) reçoit « parse: … » si la lecture du HTML s'est arrêtée."""
    res, obs = {}, []
    if modules is None:
        charges = globals()["modules"]()
        res.update({nom: {"erreur": msg} for nom, msg in _ERREURS_IMPORT.items()})
    else:
        charges = modules
    for nom, mod in charges:
        cls = getattr(mod, "Observateur", None)
        if cls is None:
            continue
        try:
            obs.append((nom, cls(entetes, url)))
        except Exception as e:  # __init__ fautif : module ignoré pour cette page
            res[nom] = {"erreur": _erreur(e)}
    d = Diffuseur([o for _, o in obs])
    d.analyser(html)
    if erreurs is not None:
        erreurs.extend(sorted({m for i, m in d.erreurs.items() if m.startswith("parse: ")}))
    for nom, o in obs:
        if id(o) in d.erreurs and o not in d.obs:
            res[nom] = {"erreur": d.erreurs[id(o)]}
            continue
        try:
            r = o.resultat()
            json.dumps(r, allow_nan=False)  # le résultat finit dans pages.json : JSON strict exigé
            res[nom] = r
        except Exception as e:
            res[nom] = {"erreur": _erreur(e)}
    # filet de sécurité : aucune adresse complète ni clé de format connu ne sort d'un module, même s'il oublie url_sans_secret()
    return {nom: assainir_sortie(res[nom]) for nom in sorted(res, key=lambda n: _ordre(n))}


def _ordre(nom):
    return MODULES.index(nom) if nom in MODULES else len(MODULES)


def _noter_erreurs_import(ctx):
    for nom, msg in _ERREURS_IMPORT.items():
        ctx.setdefault("meta", {}).setdefault("erreurs_modules", {})[nom] = msg


def _appeler(nom_fonction, ctx, *args):
    _noter_erreurs_import(ctx)
    for nom, mod in modules():
        f = getattr(mod, nom_fonction, None)
        if f is None:
            continue
        try:
            f(*args)
        except Exception as e:
            ctx.setdefault("meta", {}).setdefault("erreurs_modules", {})[nom] = _erreur(e)


def _noter_erreurs_des_pages(pages, ctx):
    """Reporte dans meta.erreurs_modules les modules en erreur sur au moins une page (première erreur + nombre de pages)."""
    vues = {}
    for p in pages.values():
        for nom, r in (p.get("obs") or {}).items():
            if isinstance(r, dict) and set(r) == {"erreur"}:
                premiere, n = vues.get(nom, (r["erreur"], 0))
                vues[nom] = (premiere, n + 1)
    for nom, (msg, n) in sorted(vues.items()):
        ctx.setdefault("meta", {}).setdefault("erreurs_modules", {}).setdefault(
            nom, "{0} ({1} page{2})".format(msg, n, "s" if n > 1 else ""))


def apres_crawl(pages, ctx):
    _noter_erreurs_des_pages(pages, ctx)
    _appeler("apres_crawl", ctx, pages, ctx)


def issues(pages, add, ctx):
    def add_net(cle, libelle, severite, exemple=None, *args, **kw):
        if "example" in kw:  # nom du paramètre de build_issues
            kw["example"] = assainir_sortie(kw["example"])
        add(cle, libelle, severite, assainir_sortie(exemple), *args, **kw)

    _appeler("issues", ctx, pages, add_net, ctx)


def collecter_groupes(pages, nom, champ):
    """{signature: {"n": occurrences, "pages": [url…]}} pour obs[nom][champ] de toutes les pages."""
    groupes = {}
    for u, p in pages.items():
        for e in ((p.get("obs") or {}).get(nom) or {}).get(champ, []):
            g = groupes.setdefault(e["signature"], {"n": 0, "pages": []})
            g["n"] += e.get("n", 1)
            g["pages"].append(u)
            if "exemple" in e and "exemple" not in g:
                g["exemple"] = e["exemple"]
    return groupes


def ajouter_groupes(add, cle, libelle, severite, groupes, domaine):
    """Un constat par signature (ordre trié = sortie déterministe), avec 3 pages d'exemple."""
    for sig in sorted(groupes):
        g = groupes[sig]
        urls = sorted(set(g["pages"]))  # le nombre de pages se compte sur les vraies URL ; l'affichage masque les valeurs secrètes
        exemple = {"signature": sig, "occurrences": g["n"], "pages": len(urls), "exemples_pages": [url_page_publique(u) for u in urls[:3]]}
        if "exemple" in g:
            exemple["exemple"] = g["exemple"]
        add(cle, libelle, severite, exemple, n=g["n"], domaine=domaine)
