#!/usr/bin/env python3
"""securite_html.py — Scripts tiers sans Subresource Integrity (test « SRI » de MDN HTTP Observatory) : un CDN compromis
peut alors exécuter n'importe quel code sur le site. Module du diffuseur html_observateurs (T3).

Seuls comptent les <script src> d'un AUTRE site que la page, sans `integrity`. Ignorés : type="text/plain" / "text/partytown"
(bloqués par un gestionnaire de consentement), feuilles de style tierces (Google Fonts sert un CSS différent selon le
navigateur : impossible à hacher), scripts du même hôte (« www. » et port ignorés) et modules `/_astro/` servis par un hôte
frère du même domaine (assetsPrefix d'Astro).

Une empreinte ne sert que sur un fichier figé. Deux familles de scripts tiers ne peuvent donc pas en avoir, et ne sont PAS
signalées « sri_absent » : elles sont listées à part (obs « scripts_dynamiques », constat « sri_non_applicable », niveau info,
avec la raison) pour que le rapport montre qu'elles ont été vues et pourquoi rien n'est à corriger :
  - les chargeurs sans version dont le contenu change par conception (Google Tag Manager / gtag, Google Analytics, Plausible,
    Stripe.js — Stripe déconseille le SRI —, Cloudflare Insights et Turnstile, reCAPTCHA, hCaptcha, pixels et widgets courants) ;
  - les bibliothèques de jsdelivr / unpkg / cdnjs sans version exacte (`@latest`, `@1`, aucun `@`) : le contenu change à chaque
    publication, une empreinte casserait la page. Le conseil est alors d'épingler une version.
Une bibliothèque de ces CDN à version exacte (`lib@1.2.3`, `/ajax/libs/jquery/3.7.1/`) et tout script d'un hôte inconnu sont
signalés (basse). Les adresses passent par url_sans_secret : ni requête, ni fragment, ni identifiants."""
import ipaddress
import re
from urllib.parse import unquote, urljoin, urlparse

import html_observateurs as ho

NOM = "securite_html"
TYPES_BLOQUES = ("text/plain", "text/partytown")

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
)
# CDN de bibliothèques npm / GitHub : figé seulement à version exacte
CDN_NPM = ("jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com")
VERSION_NPM = re.compile(r"@v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]*)?(?:/|$)|@[0-9a-f]{40}(?:/|$)")
VERSION_CDNJS = re.compile(r"/ajax/libs/[^/]+/v?\d+\.\d+(?:\.\d+)*[0-9A-Za-z.+-]*/")
RAISON_CHARGEUR = "chargeur au contenu changeant ({0}) : une empreinte ne peut pas tenir"
RAISON_CDN = "bibliothèque d'un CDN sans version exacte : épingler une version (lib@1.2.3), puis ajouter integrity"


def _hote(url):
    h = (urlparse(url).hostname or "").lower().rstrip(".")
    return h[4:] if h.startswith("www.") else h


def _est_ip(h):
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


def _domaine(h):
    """Deux derniers libellés (« cdn.ex.fr » → « ex.fr ») ; une adresse IP ou un nom sans point se compare entier."""
    morceaux = h.split(".")
    return h if _est_ip(h) or len(morceaux) < 3 else ".".join(morceaux[-2:])


def _sous_domaine(h, parent):
    return h == parent or h.endswith("." + parent)


def classer(url_script, hote_page, a):
    """None (rien à signaler), « sri » (à signaler) ou (« dynamique », raison) pour un script tiers sans integrity."""
    p = urlparse(url_script)
    h = _hote(url_script)
    chemin = unquote(p.path)
    if h == hote_page:
        return None
    if (a.get("type", "").strip().lower() == "module" and chemin.startswith("/_astro/")
            and (_domaine(h) == _domaine(hote_page))):
        return None  # module Astro du site, servi par un sous-domaine du site (assetsPrefix)
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
        self.hote = _hote(url)
        self.sans_sri, self.dynamiques = {}, {}

    def debut(self, noeud, pile):
        a = noeud["a"]
        if noeud["tag"] != "script" or not a.get("src", "").strip():
            return
        if a.get("type", "").strip().lower() in TYPES_BLOQUES or a.get("integrity", "").strip():
            return
        absolue = urljoin(self.url, a["src"].strip())
        if urlparse(absolue).scheme not in ("http", "https") or not urlparse(absolue).netloc:
            return
        verdict = classer(absolue, self.hote, a)
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
    ho.ajouter_groupes(add, "sri_absent", "Scripts tiers sans Subresource Integrity (integrity) — à vérifier : impossible pour GTM, Stripe…",
                       "basse", ho.collecter_groupes(pages, NOM, "scripts_sans_sri"), "Sécurité")
    ho.ajouter_groupes(add, "sri_non_applicable", "Scripts tiers sans SRI par construction (chargeur au contenu changeant ou version "
                       "non figée) — rien à corriger, pour information", "info",
                       ho.collecter_groupes(pages, NOM, "scripts_dynamiques"), "Sécurité")
