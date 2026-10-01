import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ICI = pathlib.Path(__file__).resolve().parent
SCRIPTS = ICI.parents[1] / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ICI))
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
                + script("https://t.example.org/e.js", 'integrity="  "') + script("https://t.example.org/f.js", 'type="text/javascript"'))
        self.assertEqual(res(html), ["https://t.example.org/c.js", "https://t.example.org/d.js", "https://t.example.org/e.js",
                                     "https://t.example.org/f.js"])

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
        # même hôte : jamais signalé ; hôte frère du même domaine servant /_astro/ en module (assetsPrefix) : idem
        html = (script("/_astro/ChatBubble.abc123.js", 'type="module"') + script("https://cdn.ex.fr/_astro/page.x.js", 'type="module"')
                + script("https://www.ex.fr/_astro/p.js", 'type="module"'))
        self.assertEqual((res(html), dyn(html)), ([], []))
        # un autre domaine qui imite le chemin, ou un script classique, reste signalé
        self.assertEqual(res(script("https://cdn.autre.net/_astro/p.js", 'type="module"')), ["https://cdn.autre.net/_astro/p.js"])
        self.assertEqual(res(script("https://cdn.ex.fr/_astro/p.js")), ["https://cdn.ex.fr/_astro/p.js"])
        self.assertEqual(res(script("https://cdn.ex.fr/autre/p.js", 'type="module"')), ["https://cdn.ex.fr/autre/p.js"])

    def test_issues_info_pour_les_dynamiques(self):
        pages = {"https://ex.fr/": {"obs": {"securite_html": obs(script("https://js.stripe.com/v3/") + script("https://cdn.exemple.org/l.js"))}}}
        vus = []
        securite_html.issues(pages, lambda *a, **k: vus.append((a, k)), {})
        cles = {a[0]: a[2] for a, _ in vus}
        self.assertEqual(cles, {"sri_absent": "basse", "sri_non_applicable": "info"})
        self.assertTrue(all(k["domaine"] == "Sécurité" for _, k in vus))


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
