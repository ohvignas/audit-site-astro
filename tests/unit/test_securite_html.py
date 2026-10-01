import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ICI = pathlib.Path(__file__).resolve().parent
RACINE = ICI.parents[1]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ICI))
import fiches  # noqa: E402
import html_observateurs as ho  # noqa: E402
import securite_html  # noqa: E402
from site_local import HTML, SiteLocal  # noqa: E402


def crawler(routes):
    """Crawl d'un SiteLocal (aucun réseau externe) → issues.json."""
    with SiteLocal(routes) as site, tempfile.TemporaryDirectory() as d:
        subprocess.run([sys.executable, str(SCRIPTS / "crawl_site.py"), site.url, "--out", d, "--delay", "0", "--max-pages", "10",
                        "--liens-externes", "0", "--ressources", "0"], check=True, capture_output=True, timeout=120)
        return json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8")), site.base


def obs(html, url="https://ex.fr/page"):
    return ho.analyser(html, {}, url, modules=[("securite_html", securite_html)])["securite_html"]


def res(html, url="https://ex.fr/page"):
    return [e["signature"] for e in obs(html, url)["scripts_sans_sri"]]


def dyn(html, url="https://ex.fr/page"):
    return [e["signature"] for e in obs(html, url)["scripts_dynamiques"]]


def script(src, attrs=""):
    return '<script src="{0}"{1}></script>'.format(src, (" " + attrs) if attrs else "")


class TestSri(unittest.TestCase):
    def test_scripts_tiers(self):
        html = ('<script src="https://cdn.exemple.org/lib.js?v=3"></script><script src="/local.js"></script>'
                '<script src="https://ex.fr/meme-hote.js"></script>'
                '<script src="https://cdn.exemple.org/ok.js" integrity="sha384-abc" crossorigin="anonymous"></script>'
                '<script type="text/plain" src="https://www.googletagmanager.com/gtag/js?id=G-1"></script>'
                '<script src="//cdn.autre.net/widget.js"></script>'
                '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter">')
        self.assertEqual(res(html), ["https://cdn.autre.net/widget.js", "https://cdn.exemple.org/lib.js"])

    def test_crawl(self):
        page = ('<html lang="fr"><head><title>Page avec script tiers</title><script src="https://cdn.cobaye.invalid/w.js"></script>'
                '</head><body><main><p>x</p></main></body></html>')
        issues, _ = crawler({"/": (200, HTML, page)})
        self.assertEqual((issues["sri_absent"]["severity"], issues["sri_absent"]["domaine"]), ("basse", "Sécurité"))

    def test_crawl_page_propre(self):
        page = ('<html lang="fr"><head><title>Page sans script tiers</title><script type="module" src="/_astro/a.js"></script>'
                '<script src="https://js.stripe.com/v3/"></script></head><body><main><p>x</p></main></body></html>')
        issues, _ = crawler({"/": (200, HTML, page)})
        self.assertNotIn("sri_absent", issues)
        self.assertEqual(issues["sri_non_applicable"]["severity"], "info")

    def test_rien_a_signaler(self):
        self.assertEqual(obs("<html><head><title>T</title></head><body><p>x</p></body></html>"),
                         {"scripts_sans_sri": [], "scripts_dynamiques": []})
        self.assertEqual(res(script("/a.js") + script("a.js") + script("https://ex.fr/b.js") + "<script>var x=1;</script>"
                             + '<script src="  "></script>'), [])

    def test_meme_hote_insensible_a_la_casse_au_port_et_au_www(self):
        html = script("https://EX.fr:8443/a.js") + script("https://www.ex.fr/b.js")
        self.assertEqual(res(html, "https://ex.fr/page"), [])
        self.assertEqual(res(script("https://ex.fr/c.js"), "https://www.ex.fr/page"), [])
        self.assertEqual(res(script("https://autre.fr/c.js"), "https://ex.fr/page"), ["https://autre.fr/c.js"])

    def test_adresse_relative_au_protocole_et_au_chemin(self):
        self.assertEqual(res(script("//cdn.autre.net/x.js")), ["https://cdn.autre.net/x.js"])
        self.assertEqual(res(script("//cdn.autre.net/x.js"), "http://ex.fr/"), ["http://cdn.autre.net/x.js"])
        self.assertEqual(res(script("../x.js"), "https://ex.fr/a/b/c"), [])

    def test_types_ignores_et_integrity_vide(self):
        html = (script("https://t.example.org/a.js", 'type="text/partytown"') + script("https://t.example.org/b.js", 'type="TEXT/PLAIN"')
                + script("https://t.example.org/c.js", 'type="module"') + script("https://t.example.org/d.js", 'integrity=""')
                + script("https://t.example.org/e.js", 'integrity="  "') + script("https://t.example.org/f.js", 'type="text/javascript"')
                + script("https://t.example.org/g.js", 'type="application/javascript; charset=utf-8"') + script("https://t.example.org/h.js", 'type=""'))
        self.assertEqual(res(html), ["https://t.example.org/c.js", "https://t.example.org/d.js", "https://t.example.org/e.js",
                                     "https://t.example.org/f.js", "https://t.example.org/g.js", "https://t.example.org/h.js"])

    def test_types_non_javascript_des_gestionnaires_de_consentement(self):
        html = "".join(script("https://t.example.org/{0}.js".format(i), 'type="{0}"'.format(t)) for i, t in enumerate(
            ("didomi/javascript", "axeptio/javascript", "text/plain", "opt-in", "application/json", "text/x-template", "text/babel")))
        self.assertEqual(res(html), [])

    def test_base_href(self):
        html = '<base href="https://cdn.autre.org/js/">' + script("a.js") + script("/b.js") + script("https://ex.fr/c.js")
        self.assertEqual(res(html), ["https://cdn.autre.org/b.js", "https://cdn.autre.org/js/a.js"])
        # seule la première <base href> compte ; une <base target> sans href ne change rien
        self.assertEqual(res('<base target="_blank"><base href="https://ex.fr/x/"><base href="https://cdn.autre.org/">' + script("a.js")), [])

    def test_contenus_inertes(self):
        html = ("<noscript>" + script("https://t.example.org/n.js") + "</noscript><template>" + script("https://t.example.org/t.js")
                + "</template>" + script("https://t.example.org/ok.js"))
        self.assertEqual(res(html), ["https://t.example.org/ok.js"])

    def test_integrity_et_attributs_jamais_dans_la_sortie(self):
        sortie = json.dumps(obs(script("https://cdn.example.org/w.js", 'data-website-id="WID-9f8e7d" nonce="NONCE-123"')
                                + script("https://js.stripe.com/v3/", 'data-key="pk_live_abc" nonce="NONCE-123"')
                                + script("https://cdn.example.org/ok.js", 'integrity="sha384-SECRETHASH" crossorigin="anonymous"')))
        for secret in ("WID-9f8e7d", "NONCE-123", "SECRETHASH", "pk_live_abc"):
            self.assertNotIn(secret, sortie)

    def test_pas_d_autre_schema(self):
        self.assertEqual(res(script("data:text/javascript,alert(1)") + script("javascript:void(0)") + script("blob:https://ex.fr/x")), [])

    def test_comptage_et_tri(self):
        html = script("https://b.example.org/x.js?a=1") + script("https://a.example.org/x.js") + script("https://b.example.org/x.js?a=2")
        self.assertEqual([(e["signature"], e["n"]) for e in obs(html)["scripts_sans_sri"]],
                         [("https://a.example.org/x.js", 1), ("https://b.example.org/x.js", 2)])

    def test_aucun_secret_dans_la_signature(self):
        sigs = res(script("https://cdn.example.org/w.js?token=SECRET123&k=AIzaSyA1234567890abcdefghijklmn#frag")
                   + script("https://user:pass@cdn2.example.org/p/Ab3dEf6hIj9kLm2oPq5sTu8vWx/w.js"))
        self.assertEqual(sigs, ["https://cdn.example.org/w.js", "https://cdn2.example.org/p/…/w.js"])
        self.assertNotIn("SECRET", json.dumps(obs(script("https://cdn.example.org/w.js?token=SECRET123"))))


class TestChargeursDynamiques(unittest.TestCase):
    """Chargeurs dont le contenu change par conception : SRI impossible, pas de constat « sri_absent »."""

    def test_chargeurs_connus_non_signales(self):
        html = "".join(script(s) for s in (
            "https://www.googletagmanager.com/gtm.js?id=GTM-ABC123", "https://www.googletagmanager.com/gtag/js?id=G-XYZ",
            "https://plausible.io/js/script.js", "https://js.stripe.com/v3/", "https://static.cloudflareinsights.com/beacon.min.js",
            "https://www.google.com/recaptcha/api.js?render=KEY", "https://www.gstatic.com/recaptcha/releases/x/recaptcha__fr.js",
            "https://www.google-analytics.com/analytics.js", "https://challenges.cloudflare.com/turnstile/v0/api.js"))
        self.assertEqual(res(html), [])
        self.assertEqual(len(dyn(html)), 9)
        self.assertIn("https://js.stripe.com/v3/", dyn(html))
        self.assertIn("https://www.googletagmanager.com/gtag/js", dyn(html))

    def test_chargeur_dynamique_mais_pas_un_autre_chemin_du_meme_hote(self):
        # google.com n'est exempté que sous /recaptcha/ ; un autre script du même domaine reste signalé
        self.assertEqual(res(script("https://www.google.com/recaptcha/api.js")), [])
        self.assertEqual(res(script("https://www.google.com/other/lib.js")), ["https://www.google.com/other/lib.js"])
        # hôte voisin d'un chargeur connu : pas d'exemption par simple ressemblance
        self.assertEqual(res(script("https://googletagmanager.com.evil.example/gtm.js")), ["https://googletagmanager.com.evil.example/gtm.js"])
        self.assertEqual(res(script("https://notstripe.com/v3/")), ["https://notstripe.com/v3/"])

    def test_chargeur_avec_integrity_ni_signale_ni_liste(self):
        self.assertEqual(obs(script("https://js.stripe.com/v3/", 'integrity="sha384-x" crossorigin="anonymous"')),
                         {"scripts_sans_sri": [], "scripts_dynamiques": []})

    def test_scripts_astro_modules_du_site(self):
        # même hôte, www, et sous-domaine du même domaine (assetsPrefix) : jamais signalé
        html = (script("/_astro/ChatBubble.abc123.js", 'type="module"') + script("https://cdn.ex.fr/_astro/page.x.js", 'type="module"')
                + script("https://www.ex.fr/_astro/p.js", 'type="module"'))
        self.assertEqual((res(html), dyn(html)), ([], []))
        # un autre domaine qui imite le chemin reste signalé
        self.assertEqual(res(script("https://cdn.autre.net/_astro/p.js", 'type="module"')), ["https://cdn.autre.net/_astro/p.js"])

    def test_sous_domaine_du_meme_domaine_est_du_site(self):
        # statistiques auto-hébergées (script classique) : ni signalé ni listé
        html = script("https://stats.ex.fr/script.js", 'data-website-id="abc"') + script("https://cdn.ex.fr/lib.js") + script("https://a.b.ex.fr/x.js")
        self.assertEqual((res(html, "https://www.ex.fr/page"), dyn(html, "https://www.ex.fr/page")), ([], []))
        self.assertEqual((res(html, "https://beta.ex.fr/"), dyn(html, "https://beta.ex.fr/")), ([], []))
        self.assertEqual(res(script("https://stats.ex.fr.evil.example/s.js"), "https://ex.fr/"), ["https://stats.ex.fr.evil.example/s.js"])
        self.assertEqual(res(script("https://autreex.fr/s.js"), "https://ex.fr/"), ["https://autreex.fr/s.js"])

    def test_suffixes_publics_pays(self):
        # evil.co.uk n'est pas du site monsite.co.uk, même en module /_astro/ ; un sous-domaine de monsite.co.uk l'est
        for page, autre, meme in (("https://monsite.co.uk/", "https://evil.co.uk", "https://stats.monsite.co.uk"),
                                  ("https://monsite.com.au/", "https://evil.com.au", "https://cdn.monsite.com.au"),
                                  ("https://monsite.co.jp/", "https://evil.co.jp", "https://cdn.monsite.co.jp"),
                                  ("https://monsite.com.br/", "https://evil.com.br", "https://cdn.monsite.com.br"),
                                  ("https://monsite.asso.fr/", "https://evil.asso.fr", "https://cdn.monsite.asso.fr")):
            with self.subTest(page=page):
                self.assertEqual(res(script(autre + "/_astro/x.js", 'type="module"') + script(autre + "/s.js"), page),
                                 [autre + "/_astro/x.js", autre + "/s.js"])
                self.assertEqual(res(script(meme + "/s.js") + script(meme + "/_astro/x.js", 'type="module"'), page), [])

    def test_plateformes_d_hebergement(self):
        for plateforme in ("vercel.app", "netlify.app", "pages.dev", "github.io", "herokuapp.com", "onrender.com", "fly.dev",
                           "workers.dev", "web.app", "firebaseapp.com"):
            with self.subTest(plateforme=plateforme):
                page = "https://monsite.{0}/".format(plateforme)
                autre = "https://autre.{0}".format(plateforme)
                self.assertEqual(res(script(autre + "/_astro/x.js", 'type="module"') + script(autre + "/s.js"), page),
                                 [autre + "/_astro/x.js", autre + "/s.js"])
                self.assertEqual(res(script("https://monsite.{0}/s.js".format(plateforme)) + script("https://www.monsite.{0}/t.js".format(plateforme)), page), [])

    def test_domaine_enregistrable(self):
        d = securite_html.domaine_enregistrable
        self.assertEqual([d(h) for h in ("ex.fr", "stats.ex.fr", "a.b.ex.fr", "localhost", "monsite.co.uk", "a.monsite.co.uk", "co.uk",
                                         "x.vercel.app", "vercel.app", "127.0.0.1", "10.0.0.1")],
                         ["ex.fr", "ex.fr", "ex.fr", "localhost", "monsite.co.uk", "monsite.co.uk", "co.uk", "x.vercel.app", "vercel.app",
                          "127.0.0.1", "10.0.0.1"])

    def test_chargeurs_courants_par_famille(self):
        familles = {
            "vimeo": ["https://player.vimeo.com/api/player.js"],
            "youtube": ["https://www.youtube.com/iframe_api", "https://s.ytimg.com/yts/jsbin/www-widgetapi-vflx.js"],
            "google maps": ["https://maps.googleapis.com/maps/api/js?key=AIzaSyA1234567890abcdefghijklmn&callback=init"],
            "google sign-in": ["https://accounts.google.com/gsi/client", "https://apis.google.com/js/api.js"],
            "google ads": ["https://www.googleadservices.com/pagead/conversion.js"],
            "cal.com": ["https://app.cal.com/embed/embed.js", "https://cal.com/embed/embed.js"],
            "paypal": ["https://www.paypal.com/sdk/js?client-id=abc", "https://www.paypalobjects.com/api/checkout.js"],
            "onetrust": ["https://cdn.cookielaw.org/scripttemplates/otSDKStub.js"],
            "didomi": ["https://sdk.privacy-center.org/loader.js"],
            "axeptio": ["https://static.axept.io/sdk.js"],
            "segment": ["https://cdn.segment.com/analytics.js/v1/abc/analytics.min.js"],
            "bing uet": ["https://bat.bing.com/bat.js"],
            "brevo": ["https://sibforms.com/forms/end-form/build/main.js", "https://sibautomation.com/sa.js"],
            "x / twitter": ["https://platform.twitter.com/widgets.js"],
            "sentry": ["https://js.sentry-cdn.com/abc.min.js"],
            "typeform": ["https://embed.typeform.com/next/embed.js"],
            "hubspot": ["https://js.hs-analytics.net/analytics/1/1.js"],
        }
        for nom, srcs in familles.items():
            for src in srcs:
                with self.subTest(famille=nom, src=src):
                    self.assertEqual(res(script(src)), [])
                    self.assertEqual(dyn(script(src)), [ho.url_sans_secret(src)])
        # un autre chemin des mêmes domaines génériques reste signalé
        self.assertEqual(res(script("https://www.youtube.com/other.js")), ["https://www.youtube.com/other.js"])
        self.assertEqual(res(script("https://accounts.google.com/other.js")), ["https://accounts.google.com/other.js"])

    def test_issues_info_pour_les_dynamiques(self):
        pages = {"https://ex.fr/": {"obs": {"securite_html": obs(script("https://js.stripe.com/v3/") + script("https://cdn.exemple.org/l.js"))}}}
        vus = []
        securite_html.issues(pages, lambda *a, **k: vus.append((a, k)), {})
        cles = {a[0]: a[2] for a, _ in vus}
        self.assertEqual(cles, {"sri_absent": "basse", "sri_non_applicable": "info"})
        self.assertTrue(all(k["domaine"] == "Sécurité" for _, k in vus))


class TestFiche(unittest.TestCase):
    def test_seul_sri_absent_ouvre_la_fiche(self):
        fiche = fiches.charger_fiches(RACINE / "plugins/audit-site-astro/skills/audit-complet/references/fiches")
        s = lambda cle: {"severite": "info", "domaine": "Sécurité", "texte": cle, "exemples": [], "source": "crawl", "cle": cle}  # noqa: E731
        retenues, sans = fiches.associer([s("sri_non_applicable")], fiche)
        self.assertEqual((retenues, [x["cle"] for x in sans]), ({}, ["sri_non_applicable"]))
        retenues, _ = fiches.associer([s("sri_absent")], fiche)
        self.assertEqual(list(retenues), ["secu-sri-scripts-tiers"])


class TestCdnVersionnes(unittest.TestCase):
    """jsdelivr / unpkg / cdnjs : contenu figé (version exacte) → SRI recommandé ; version flottante → contenu changeant."""

    def test_versions_exactes_signalees(self):
        for src in ("https://cdn.jsdelivr.net/npm/lib@1.2.3/dist/lib.min.js", "https://unpkg.com/lib@1.2.3/dist/lib.js",
                    "https://cdnjs.cloudflare.com/ajax/libs/jquery/3.7.1/jquery.min.js",
                    "https://cdn.jsdelivr.net/npm/@scope/pkg@2.0.0-beta.1/dist/x.js", "https://cdn.jsdelivr.net/gh/user/repo@v1.4.0/x.js",
                    "https://cdn.jsdelivr.net/gh/user/repo@" + "a" * 40 + "/x.js"):
            with self.subTest(src=src):
                self.assertEqual(res(script(src)), [ho.url_sans_secret(src)])
                self.assertEqual(dyn(script(src)), [])

    def test_version_flottante_non_signalee_mais_expliquee(self):
        for src in ("https://cdn.jsdelivr.net/npm/lib/dist/lib.js", "https://cdn.jsdelivr.net/npm/lib@latest/dist/lib.js",
                    "https://cdn.jsdelivr.net/npm/lib@1/dist/lib.js", "https://cdn.jsdelivr.net/npm/lib@1.2/dist/lib.js",
                    "https://unpkg.com/lib/dist/lib.js", "https://unpkg.com/lib@^1.0.0/x.js"):
            with self.subTest(src=src):
                self.assertEqual(res(script(src)), [])
                self.assertEqual(dyn(script(src)), [ho.url_sans_secret(src)])

    def test_cdn_versionne_avec_integrity_rien(self):
        html = script("https://cdn.jsdelivr.net/npm/lib@1.2.3/dist/lib.min.js", 'integrity="sha384-abc" crossorigin="anonymous"')
        self.assertEqual(obs(html), {"scripts_sans_sri": [], "scripts_dynamiques": []})

    def test_hote_inconnu_toujours_signale(self):
        self.assertEqual(res(script("https://cdn.exemple.org/lib.js")), ["https://cdn.exemple.org/lib.js"])


if __name__ == "__main__":
    unittest.main()
