#!/usr/bin/env python3
"""securite_html.py — Scripts tiers sans Subresource Integrity (test « SRI » de MDN HTTP Observatory) : un CDN compromis
peut alors exécuter n'importe quel code sur le site. Module du diffuseur html_observateurs (T3).

Seuls comptent les <script src> d'un AUTRE site que la page, sans `integrity`. « Même site » = même hôte (« www. » et port
ignorés) ou sous-domaine du même domaine enregistrable (stats.ex.fr, cdn.ex.fr pour ex.fr : statistiques auto-hébergées,
assetsPrefix d'Astro) ; le domaine enregistrable tient compte d'une petite liste de suffixes publics (co.uk, com.au… et
plateformes d'hébergement où chaque sous-domaine est un autre site : vercel.app, github.io…). Ignorés aussi : les scripts dont le
type n'est pas du JavaScript (text/plain, text/partytown, didomi/javascript, opt-in… : un gestionnaire de consentement les
réécrit plus tard), ceux d'un <template> ou d'un <noscript> (jamais exécutés), et les feuilles de style tierces (Google Fonts sert
un CSS différent selon le navigateur : impossible à hacher). Les adresses relatives suivent <base href>.

Une empreinte ne sert que sur un fichier figé. Deux familles de scripts tiers ne peuvent donc pas en avoir, et ne sont PAS
signalées « sri_absent » : elles sont listées à part (obs « scripts_dynamiques », constat « sri_non_applicable », niveau info,
avec la raison) pour que le rapport montre qu'elles ont été vues et pourquoi rien n'est à corriger :
  - les chargeurs sans version dont le contenu change par conception (Google Tag Manager / gtag, Google Analytics, Plausible,
    Stripe.js — Stripe impose de le charger depuis js.stripe.com —, Cloudflare Insights et Turnstile, reCAPTCHA, hCaptcha,
    lecteurs et API vidéo, cartes, paiement, gestionnaires de consentement, pixels et widgets courants) ;
  - les bibliothèques de jsdelivr / unpkg / cdnjs sans version exacte (`@latest`, `@1`, aucun `@`) : le contenu change à chaque
    publication, une empreinte casserait la page. Le conseil est alors d'épingler une version.
Une bibliothèque de ces CDN à version exacte (`lib@1.2.3`, `/ajax/libs/jquery/3.7.1/`) et tout script d'un hôte inconnu sont
signalés (basse). Les adresses passent par url_sans_secret : ni requête, ni fragment, ni identifiants."""
import ipaddress
import re
from urllib.parse import unquote, urljoin, urlparse

import html_observateurs as ho

NOM = "securite_html"
# Seuls ces types exécutent un script (type absent ou vide = JavaScript) ; tout autre (text/plain, text/partytown, didomi/javascript,
# axeptio/javascript, opt-in, application/json…) n'est pas exécuté tel quel : un gestionnaire de consentement le réécrit plus tard
TYPES_JS = {"", "module", "text/javascript", "application/javascript", "application/x-javascript", "text/ecmascript",
            "application/ecmascript", "text/x-javascript", "text/jscript", "text/livescript", "text/javascript1.0",
            "text/javascript1.1", "text/javascript1.2", "text/javascript1.3", "text/javascript1.4", "text/javascript1.5"}
INERTES = ("template", "noscript")

# Chargeurs au contenu changeant : (hôte ou domaine parent, préfixe de chemin exigé ou None, nom affiché). Un hôte n'en fait
# partie que s'il est ce domaine ou un sous-domaine (« googletagmanager.com.evil.example » n'en est pas un).
CHARGEURS = (
    ("googletagmanager.com", None, "Google Tag Manager / gtag"),
    ("google-analytics.com", None, "Google Analytics"),
    ("plausible.io", None, "Plausible"),
    ("js.stripe.com", None, "Stripe.js"),
    ("static.cloudflareinsights.com", None, "Cloudflare Web Analytics"),
    ("challenges.cloudflare.com", None, "Cloudflare Turnstile"),
    ("recaptcha.net", None, "reCAPTCHA"),
    ("google.com", "/recaptcha/", "reCAPTCHA"),
    ("gstatic.com", "/recaptcha/", "reCAPTCHA"),
    ("hcaptcha.com", None, "hCaptcha"),
    ("connect.facebook.net", None, "Pixel / SDK Meta"),
    ("static.hotjar.com", None, "Hotjar"),
    ("clarity.ms", None, "Microsoft Clarity"),
    ("snap.licdn.com", None, "LinkedIn Insight"),
    ("js.hs-scripts.com", None, "HubSpot"),
    ("js.hsforms.net", None, "HubSpot"),
    ("widget.intercom.io", None, "Intercom"),
    ("client.crisp.chat", None, "Crisp"),
    ("embed.tawk.to", None, "Tawk.to"),
    ("assets.calendly.com", None, "Calendly"),
    ("consent.cookiebot.com", None, "Cookiebot"),
    ("player.vimeo.com", None, "lecteur Vimeo"),
    ("youtube.com", "/iframe_api", "API YouTube"),
    ("ytimg.com", "/yts/jsbin/", "API YouTube"),
    ("maps.googleapis.com", None, "Google Maps"),
    ("accounts.google.com", "/gsi/", "Google Sign-In"),
    ("apis.google.com", None, "API Google"),
    ("googleadservices.com", None, "Google Ads"),
    ("cal.com", None, "Cal.com"),
    ("paypal.com", None, "PayPal"),
    ("paypalobjects.com", None, "PayPal"),
    ("cookielaw.org", None, "OneTrust"),
    ("onetrust.com", None, "OneTrust"),
    ("privacy-center.org", None, "Didomi"),
    ("didomi.io", None, "Didomi"),
    ("axept.io", None, "Axeptio"),
    ("cdn.segment.com", None, "Segment"),
    ("bat.bing.com", None, "Bing UET"),
    ("sibforms.com", None, "Brevo"),
    ("sendinblue.com", None, "Brevo"),
    ("brevo.com", None, "Brevo"),
    ("sibautomation.com", None, "Brevo"),
    ("platform.twitter.com", None, "widgets X / Twitter"),
    ("static.ads-twitter.com", None, "pixel X / Twitter"),
    ("js.sentry-cdn.com", None, "Sentry"),
    ("embed.typeform.com", None, "Typeform"),
    ("js.hs-analytics.net", None, "HubSpot"),
)
# CDN de bibliothèques npm / GitHub : figé seulement à version exacte
CDN_NPM = ("jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com")
VERSION_NPM = re.compile(r"@v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]*)?(?:/|$)|@[0-9a-f]{40}(?:/|$)")
VERSION_CDNJS = re.compile(r"/ajax/libs/[^/]+/v?\d+\.\d+(?:\.\d+)*[0-9A-Za-z.+-]*/")
RAISON_CHARGEUR = "chargeur au contenu changeant ({0}) : une empreinte ne peut pas tenir"
RAISON_CDN = "bibliothèque d'un CDN sans version exacte : épingler une version (lib@1.2.3), puis ajouter integrity"


# Suffixes publics : un domaine enregistrable = un libellé de plus que le suffixe. Liste volontairement courte (pas la Public Suffix
# List complète) : suffixes à deux libellés des pays courants, plateformes d'hébergement où chaque sous-domaine est un autre site.
SUFFIXES_PAYS = (
    "co.uk org.uk me.uk ltd.uk plc.uk net.uk ac.uk gov.uk sch.uk com.au net.au org.au edu.au gov.au asn.au id.au co.nz net.nz "
    "org.nz govt.nz ac.nz co.jp ne.jp or.jp ac.jp go.jp com.br net.br org.br gov.br com.ar com.mx com.co com.pe com.ve com.uy "
    "com.cn net.cn org.cn gov.cn co.in net.in org.in firm.in gen.in ind.in co.za org.za web.za com.tr org.tr com.sg com.hk "
    "com.tw co.kr or.kr co.id web.id co.il org.il com.my com.ph com.vn co.th in.th com.ua com.pl com.es com.pt com.eg com.sa "
    "com.ng co.ke com.gr com.ro asso.fr com.fr gouv.fr nom.fr prd.fr presse.fr tm.fr").split()
SUFFIXES_PLATEFORMES = (
    "vercel.app netlify.app pages.dev github.io gitlab.io herokuapp.com onrender.com fly.dev workers.dev web.app firebaseapp.com "
    "appspot.com azurewebsites.net cloudfront.net surge.sh glitch.me repl.co pythonanywhere.com convex.cloud convex.site "
    "ngrok.io ngrok-free.app trycloudflare.com s3.amazonaws.com").split()
SUFFIXES_PUBLICS = frozenset(SUFFIXES_PAYS + SUFFIXES_PLATEFORMES)


def _hote(url):
    h = (urlparse(url).hostname or "").lower().rstrip(".")
    return h[4:] if h.startswith("www.") else h


def _est_ip(h):
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


def domaine_enregistrable(h):
    """Domaine d'un site : suffixe public + un libellé (« stats.ex.fr » → « ex.fr », « a.b.co.uk » → « b.co.uk »,
    « x.vercel.app » → « x.vercel.app »). Une adresse IP, un nom sans point ou un suffixe public seul se compare entier."""
    if _est_ip(h):
        return h
    m = h.split(".")
    for k in (3, 2):  # plus long suffixe public d'abord
        if len(m) > k and ".".join(m[-k:]) in SUFFIXES_PUBLICS:
            return ".".join(m[-(k + 1):])
    return h if len(m) < 3 else ".".join(m[-2:])


def _sous_domaine(h, parent):
    return h == parent or h.endswith("." + parent)


def classer(url_script, hote_page):
    """None (rien à signaler), « sri » (à signaler) ou (« dynamique », raison) pour un script tiers sans integrity."""
    h = _hote(url_script)
    chemin = unquote(urlparse(url_script).path)
    if h == hote_page or domaine_enregistrable(h) == domaine_enregistrable(hote_page):
        return None  # même site : hôte identique ou sous-domaine du même domaine (stats.ex.fr, cdn.ex.fr/_astro/…)
    for domaine, prefixe, nom in CHARGEURS:
        if _sous_domaine(h, domaine) and (prefixe is None or chemin.startswith(prefixe)):
            return "dynamique", RAISON_CHARGEUR.format(nom)
    if any(_sous_domaine(h, c) for c in CDN_NPM):
        if VERSION_NPM.search(chemin) or VERSION_CDNJS.search(chemin):
            return "sri"
        return "dynamique", RAISON_CDN
    return "sri"


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self.hote, self.base = _hote(url), url
        self.base_vue = False
        self.sans_sri, self.dynamiques = {}, {}

    def debut(self, noeud, pile):
        a, tag = noeud["a"], noeud["tag"]
        if tag == "base":
            if not self.base_vue and a.get("href", "").strip():  # seule la première <base href> compte
                self.base_vue, self.base = True, urljoin(self.url, a["href"].strip())
            return
        if tag != "script" or not a.get("src", "").strip() or ho.dans(pile, *INERTES):
            return
        if a.get("type", "").split(";")[0].strip().lower() not in TYPES_JS or a.get("integrity", "").strip():
            return
        absolue = urljoin(self.base, a["src"].strip())
        p = urlparse(absolue)
        if p.scheme not in ("http", "https") or not p.netloc:
            return
        verdict = classer(absolue, self.hote)
        if verdict is None:
            return
        sig = ho.url_sans_secret(absolue)
        if verdict == "sri":
            self.sans_sri[sig] = self.sans_sri.get(sig, 0) + 1
        else:
            n, raison = self.dynamiques.get(sig, (0, verdict[1]))
            self.dynamiques[sig] = (n + 1, raison)

    def resultat(self):
        return {"scripts_sans_sri": [{"signature": k, "n": v} for k, v in sorted(self.sans_sri.items())],
                "scripts_dynamiques": [{"signature": k, "n": n, "exemple": r} for k, (n, r) in sorted(self.dynamiques.items())]}


def issues(pages, add, ctx):
    ho.ajouter_groupes(add, "sri_absent", "Scripts d'un autre site sans Subresource Integrity (integrity) — à vérifier : bibliothèque figée à épingler ou fichier à auto-héberger (les chargeurs dynamiques sont listés à part)",
                       "basse", ho.collecter_groupes(pages, NOM, "scripts_sans_sri"), "Sécurité")
    ho.ajouter_groupes(add, "sri_non_applicable", "Scripts d'un autre site sans SRI par construction (chargeur au contenu changeant ou version "
                       "non figée) — rien à corriger, pour information", "info",
                       ho.collecter_groupes(pages, NOM, "scripts_dynamiques"), "Sécurité")
