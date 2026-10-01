import json
import pathlib
import subprocess
import sys
import random
import re
import tempfile
import threading
import time
import unittest
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ICI = pathlib.Path(__file__).resolve().parent
SCRIPTS = ICI.parents[1] / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ICI))
import crawl_site  # noqa: E402
import html_observateurs as ho  # noqa: E402
import ressources_site  # noqa: E402
from site_local import HTML, SiteLocal  # noqa: E402

PAGE = ('<html lang="fr"><head><title>Ressources de test assez longues</title><link rel="stylesheet" href="/style.css">'
        '<style>@font-face{font-family:"Titre";src:url(/t.woff2);font-display:block}</style></head><body><main>'
        '<img src="/lourde.jpg" alt="x" width="1" height="1"><img src="/_astro/logo.abc12345.png" alt="y" width="1" height="1">'
        '<script src="/_astro/app.Bx9a8K2q.js"></script><img src="https://cdn.ailleurs.org/x.jpg" alt="z" width="1" height="1">'
        '<astro-island uid="1" component-url="/_astro/Chat.X9aB3cD4.js" renderer-url="/_astro/client.Q1w2E3r4.js"></astro-island>'
        '<img src="/_image?href=%2Fa.png&w=10" alt="w" width="1" height="1"></main></body></html>')
ROUTES = {
    "/": (200, HTML, PAGE),
    "/lourde.jpg": (200, {"Content-Type": "image/jpeg", "Cache-Control": "max-age=0"}, "x" * 300_000),
    "/_astro/logo.abc12345.png": (200, {"Content-Type": "image/png", "Cache-Control": "public, max-age=31536000, immutable"}, "p" * 10_000),
    "/_astro/app.Bx9a8K2q.js": (200, {"Content-Type": "text/javascript", "Cache-Control": "public, max-age=31536000, immutable"}, "a" * 200_000),
    "/_astro/Chat.X9aB3cD4.js": (200, {"Content-Type": "text/javascript", "Cache-Control": "public, max-age=31536000, immutable"}, "c" * 200_000),
    "/_astro/client.Q1w2E3r4.js": (200, {"Content-Type": "text/javascript", "Cache-Control": "public, max-age=31536000, immutable"}, "r" * 20_000),
    "/style.css": (200, {"Content-Type": "text/css", "Cache-Control": "public, max-age=86400"},
                   "@font-face{font-family:A;src:url(/a.woff2)}@font-face{font-family:B;font-display:swap;src:url(/b.woff2)}"),
}


class TestRessources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with SiteLocal(ROUTES) as site, tempfile.TemporaryDirectory() as d:
            subprocess.run([sys.executable, str(SCRIPTS / "crawl_site.py"), site.url, "--out", d, "--delay", "0", "--max-pages", "3",
                            "--liens-externes", "0", "--ressources", "50"], check=True, capture_output=True, timeout=180)
            cls.issues = json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8"))
            cls.pages = json.loads(pathlib.Path(d, "pages.json").read_text(encoding="utf-8"))
            cls.requetes = list(site.requetes)

    def sigs(self, cle):
        return [e["signature"] for e in self.issues.get(cle, {}).get("examples", [])]

    def test_quatre_controles(self):
        self.assertEqual(self.sigs("image_lourde"), ["/lourde.jpg (292 Ko)"])
        self.assertEqual(self.sigs("js_lourd"), ["/_astro/Chat.X9aB3cD4.js (195 Ko transférés)",   # îlot (component-url)
                                                 "/_astro/app.Bx9a8K2q.js (195 Ko transférés)"])
        self.assertEqual(self.sigs("asset_sans_cache"), ["/lourde.jpg (Cache-Control : max-age=0)"])
        self.assertEqual(self.sigs("police_sans_font_display"), ["A (/style.css)", "Titre (style en ligne, font-display: block)"])

    def test_severites_et_domaines(self):
        for cle, sev, dom in (("image_lourde", "moyenne", "Performance"), ("js_lourd", "moyenne", "Performance"),
                              ("asset_sans_cache", "moyenne", "Serveur / HTTP"), ("police_sans_font_display", "basse", "Performance")):
            self.assertEqual((self.issues[cle]["severity"], self.issues[cle]["domaine"]), (sev, dom), cle)

    def test_ni_tiers_ni_image_dynamique(self):
        self.assertFalse([r for r in self.requetes if r.startswith("/_image")], "l'endpoint /_image est mesuré ailleurs")
        self.assertNotIn("cdn.ailleurs.org", json.dumps(self.issues))

    def test_meta_et_non_verifiees(self):
        m = self.pages["meta"]["modules"]["ressources"]
        self.assertEqual((m["trouvees"], m["mesurees"], m["budget_atteint"], m["non_verifiees"]), (6, 6, False, 0))

    def test_poids_js_mesure_par_get_serveur_sans_compression(self):
        # serveur de test sans compression : octets transférés = octets décompressés, étiquette « non compressé »
        ex = self.issues["js_lourd"]["examples"][0]
        self.assertIn("non compressé", ex["exemple"])

    def test_hashe(self):
        self.assertTrue(ressources_site.hashe("/_astro/x.png"))
        self.assertTrue(ressources_site.hashe("/assets/app.Bx9a8K2q.js"))
        self.assertFalse(ressources_site.hashe("/agent-avatar.png"))
        self.assertFalse(ressources_site.hashe("/images/hero-4000.jpg"))


def fetch_faux(table, appels):
    """Faux fetch : table {url: (statut, entetes, taille)} ; enregistre (url, méthode, extra_headers)."""
    def f(u, timeout=20, method="GET", max_bytes=3_000_000, ua=None, extra_headers=None, max_hops=10):
        appels.append((u, method, dict(extra_headers or {}), max_bytes))
        statut, entetes, corps = table.get(u, (404, {}, b""))
        h = {k.lower(): v for k, v in entetes.items()}
        if method == "HEAD":
            return {"status": statut, "headers": h, "raw_bytes": 0, "body": b"", "chain": [], "final_url": u}
        if extra_headers and "Range" in extra_headers and statut == 200 and "x-sans-range" not in h:
            h["content-range"] = "bytes 0-0/{0}".format(len(corps))
            return {"status": 206, "headers": h, "raw_bytes": 1, "body": corps[:1], "chain": [], "final_url": u}
        corps = corps[:max_bytes]
        return {"status": statut, "headers": h, "raw_bytes": len(corps), "body": corps, "chain": [], "final_url": u}
    return f


def pages_de(*ressources, page="https://ex.fr/"):
    return {page: {"obs": {"ressources_site": {"ressources": [{"type": t, "url": u} for t, u in ressources]}}}}


class TestMesures(unittest.TestCase):
    def lancer(self, table, pages, **ctx_extra):
        appels = []
        ctx = {"fetch": fetch_faux(table, appels), "host": "ex.fr", "ressources_max": 400, "timeout": 5, "budget_reseau_s": 30,
               "meta": {}}
        ctx.update(ctx_extra)
        ressources_site.apres_crawl(pages, ctx)
        return ctx, appels

    def test_head_d_abord_puis_range_sans_content_length(self):
        table = {"https://ex.fr/a.png": (200, {"Content-Type": "image/png"}, b"x" * 250_000)}
        ctx, appels = self.lancer(table, pages_de(("image", "https://ex.fr/a.png")))
        self.assertEqual([a[1] for a in appels], ["HEAD", "GET"])
        self.assertEqual(appels[1][2], {"Range": "bytes=0-0"})   # jamais l'image entière
        self.assertEqual(ctx["ressources"]["https://ex.fr/a.png"]["octets"], 250_000)

    def test_lecture_plafonnee_si_le_serveur_ignore_range(self):
        table = {"https://ex.fr/a.png": (200, {"Content-Type": "image/png", "x-sans-range": "1"}, b"x" * 2_000_000)}
        ctx, appels = self.lancer(table, pages_de(("image", "https://ex.fr/a.png")))
        self.assertLessEqual(appels[1][3], 1_048_576)
        m = ctx["ressources"]["https://ex.fr/a.png"]
        self.assertTrue(m["tronque"])
        self.assertGreater(m["octets"], 200 * 1024)

    def test_head_avec_content_length_suffit(self):
        table = {"https://ex.fr/a.png": (200, {"Content-Type": "image/png", "Content-Length": "300000"}, b"")}
        ctx, appels = self.lancer(table, pages_de(("image", "https://ex.fr/a.png")))
        self.assertEqual([a[1] for a in appels], ["HEAD"])
        self.assertEqual(ctx["ressources"]["https://ex.fr/a.png"]["octets"], 300_000)

    def test_js_sans_content_length_lu_en_get_compresse_et_decompresse(self):
        u = "https://ex.fr/_astro/Chat.X9aB3cD4.js"
        def f(url, timeout=20, method="GET", max_bytes=3_000_000, ua=None, extra_headers=None, max_hops=10):
            self.assertEqual(method, "GET")   # un script n'est jamais jugé sur le HEAD
            return {"status": 200, "headers": {"content-encoding": "gzip", "content-type": "text/javascript"}, "raw_bytes": 120_000,
                    "body": b"a" * 447_000, "chain": [], "final_url": url}
        ctx = {"fetch": f, "host": "ex.fr", "ressources_max": 10, "timeout": 5, "budget_reseau_s": 30, "meta": {}}
        ressources_site.apres_crawl(pages_de(("script", u)), ctx)
        m = ctx["ressources"][u]
        self.assertEqual((m["octets"], m["octets_decompresses"]), (120_000, 447_000))

    def test_priorite_par_nombre_de_pages_et_non_alphabetique(self):
        pages = {"https://ex.fr/1": pages_de(("image", "https://ex.fr/aaa.png"), ("image", "https://ex.fr/zzz.png"))["https://ex.fr/"],
                 "https://ex.fr/2": pages_de(("image", "https://ex.fr/zzz.png"))["https://ex.fr/"],
                 "https://ex.fr/3": pages_de(("image", "https://ex.fr/zzz.png"))["https://ex.fr/"]}
        table = {u: (200, {"Content-Length": "10"}, b"") for u in ("https://ex.fr/aaa.png", "https://ex.fr/zzz.png")}
        ctx, appels = self.lancer(table, pages, ressources_max=1)
        self.assertEqual([a[0] for a in appels], ["https://ex.fr/zzz.png"])
        self.assertEqual(ctx["meta"]["ressources"]["non_verifiees"], 1)
        self.assertTrue(ctx["meta"]["ressources"]["plafond_atteint"])

    def test_pause_entre_requetes(self):
        table = {"https://ex.fr/a.png": (200, {"Content-Length": "1"}, b""), "https://ex.fr/b.png": (200, {"Content-Length": "1"}, b"")}
        t = time.monotonic()
        self.lancer(table, pages_de(("image", "https://ex.fr/a.png"), ("image", "https://ex.fr/b.png")), delai=0.2)
        self.assertGreaterEqual(time.monotonic() - t, 0.15)

    def test_429_arrete_les_requetes_sans_constat(self):
        table = {"https://ex.fr/a.png": (429, {}, b""), "https://ex.fr/b.png": (200, {"Content-Length": "999999"}, b"")}
        ctx, appels = self.lancer(table, pages_de(("image", "https://ex.fr/a.png"), ("image", "https://ex.fr/b.png")))
        self.assertEqual(len(appels), 1)
        self.assertEqual(ctx["meta"]["ressources"]["mesurees"], 1)
        self.assertEqual(ctx["meta"]["ressources"]["a_verifier"], 1)
        ajouts = []
        ressources_site.issues(pages_de(), lambda *a, **k: ajouts.append(a), ctx)
        self.assertEqual(ajouts, [])

    def test_403_a_verifier_jamais_un_constat(self):
        table = {"https://ex.fr/a.png": (403, {"Content-Length": "999999"}, b"")}
        ctx, _ = self.lancer(table, pages_de(("image", "https://ex.fr/a.png")))
        ajouts = []
        ressources_site.issues(pages_de(), lambda *a, **k: ajouts.append(a), ctx)
        self.assertEqual(ajouts, [])

    def test_hote_tiers_jamais_contacte_meme_apres_redirection(self):
        appels = []

        def f(url, timeout=20, method="GET", max_bytes=3_000_000, ua=None, extra_headers=None, max_hops=10):
            appels.append((url, max_hops))
            return {"status": -1, "headers": {}, "raw_bytes": 0, "body": b"", "chain": [{"url": url, "status": 302}],
                    "final_url": "https://cdn.ailleurs.org/a.png"}
        ctx = {"fetch": f, "host": "ex.fr", "ressources_max": 10, "timeout": 5, "budget_reseau_s": 30, "meta": {}}
        ressources_site.apres_crawl(pages_de(("image", "https://ex.fr/a.png"), ("image", "https://cdn.ailleurs.org/b.png")), ctx)
        self.assertEqual(appels, [("https://ex.fr/a.png", 1)])   # un seul saut autorisé : la redirection vers un tiers n'est pas suivie

    def test_redirection_meme_hote_suivie(self):
        appels = []

        def f(url, timeout=20, method="GET", max_bytes=3_000_000, ua=None, extra_headers=None, max_hops=10):
            appels.append(url)
            if url == "https://ex.fr/a.png":
                return {"status": -1, "headers": {}, "raw_bytes": 0, "body": b"", "chain": [{"url": url, "status": 301}],
                        "final_url": "https://ex.fr/b.png"}
            return {"status": 200, "headers": {"content-length": "300000", "content-type": "image/png"}, "raw_bytes": 0, "body": b"",
                    "chain": [], "final_url": url}
        ctx = {"fetch": f, "host": "ex.fr", "ressources_max": 10, "timeout": 5, "budget_reseau_s": 30, "meta": {}}
        ressources_site.apres_crawl(pages_de(("image", "https://ex.fr/a.png")), ctx)
        self.assertEqual(ctx["ressources"]["https://ex.fr/a.png"]["octets"], 300_000)

    def test_trois_echecs_reseau_de_suite_arretent(self):
        urls = ["https://ex.fr/{0}.png".format(i) for i in range(6)]
        table_vide = {u: (0, {}, b"") for u in urls}
        ctx, appels = self.lancer(table_vide, pages_de(*[("image", u) for u in urls]))
        self.assertEqual(len(appels), 3)


class TestAnalyse(unittest.TestCase):
    def constats(self, ressources, polices_css=None, sources=None):
        ctx = {"ressources": ressources, "sources_ressources": sources or {u: ["https://ex.fr/"] for u in ressources},
               "polices_css": polices_css or {}}
        out = []
        ressources_site.issues({}, lambda cle, lib, sev, ex, n=1, domaine=None: out.append((cle, ex["signature"])), ctx)
        return out

    def base(self, **kw):
        m = {"type": "image", "statut": 200, "octets": 10, "cache": "public, max-age=86400", "ctype": "image/png"}
        m.update(kw)
        return m

    def test_cache(self):
        r = {"https://ex.fr/a.png": self.base(cache="max-age=0"),
             "https://ex.fr/b.png": self.base(cache="public, max-age=86400"),
             "https://ex.fr/c.png": self.base(cache="no-store"),
             "https://ex.fr/d.png": self.base(cache=""),
             "https://ex.fr/e.png": self.base(cache="public, s-maxage=86400"),
             "https://ex.fr/_astro/f.png": self.base(cache="max-age=0")}  # hashé : couvert par H06
        self.assertEqual([s for c, s in self.constats(r) if c == "asset_sans_cache"],
                         ["/a.png (Cache-Control : max-age=0)", "/c.png (Cache-Control : no-store)", "/d.png (Cache-Control : absent)",
                          "/e.png (Cache-Control : public, s-maxage=86400)"])

    def test_expires_futur_vaut_cache(self):
        r = {"https://ex.fr/a.png": self.base(cache="", expire_dans_s=86400 * 30)}
        self.assertEqual(self.constats(r), [])

    def test_html_ou_non_200_ignores(self):
        r = {"https://ex.fr/a.png": self.base(cache="max-age=0", ctype="text/html; charset=utf-8"),
             "https://ex.fr/b.png": self.base(cache="max-age=0", statut=404)}
        self.assertEqual(self.constats(r), [])

    def test_seuils(self):
        r = {"https://ex.fr/a.jpg": self.base(octets=200 * 1024),
             "https://ex.fr/b.jpg": self.base(octets=200 * 1024 + 1, cache="max-age=86400"),
             "https://ex.fr/c.js": self.base(type="script", octets=150 * 1024 + 1, ctype="text/javascript"),
             "https://ex.fr/d.js": self.base(type="script", octets=150 * 1024, ctype="text/javascript")}
        cles = [c for c, _ in self.constats(r)]
        self.assertEqual(sorted(cles), ["image_lourde", "js_lourd"])

    def test_secrets_retires_des_signatures(self):
        u = "https://ex.fr/img/a.png?token=SECRETVALUE123&v=2"
        r = {u: self.base(octets=300_000, cache="max-age=0")}
        sortie = json.dumps(self.constats(r))
        self.assertNotIn("SECRETVALUE123", sortie)
        self.assertNotIn("token", sortie)
        self.assertIn("/img/a.png (", sortie)

    def test_segment_secret_du_chemin_masque(self):
        r = {"https://ex.fr/k/AbCdEfGhIjKlMnOpQrStUv123/a.png": self.base(octets=300_000)}
        self.assertNotIn("AbCdEfGhIjKlMnOpQrStUv123", json.dumps(self.constats(r)))


class TestPolices(unittest.TestCase):
    def test_cas(self):
        css = ("/* @font-face{font-family:Commentee} */"
               "@font-face{font-family:'A';src:url(a.woff2)}"
               "@font-face{font-family:B;font-display:swap;src:url(b.woff2)}"
               "@font-face{font-family:C;font-display:optional;src:url(c.woff2)}"
               "@font-face{font-family:D;font-display:fallback;src:url(d.woff2)}"
               "@font-face{font-family:E;font-display:AUTO;src:url(e.woff2)}"
               "@font-face{font-family:\"F F\";font-display:block;src:url(f.woff2)}"
               "@font-face{font-family:'Inter fallback';src:local('Arial');size-adjust:107%}")  # repli Astro : rien à charger
        self.assertEqual(ressources_site.polices_sans_display(css, "/s.css"),
                         ["A (/s.css)", "E (/s.css, font-display: auto)", "F F (/s.css, font-display: block)"])

    def test_astro_fonts_api_swap_par_defaut_non_signale(self):
        # L'API Fonts d'Astro émet font-display: swap (valeur par défaut de l'option `display`)
        css = '@font-face{font-family:"Inter";src:url("/_astro/fonts/abc.woff2") format("woff2");font-display:swap;font-weight:400}'
        self.assertEqual(ressources_site.polices_sans_display(css, "style en ligne"), [])


class TestObservateur(unittest.TestCase):
    def lire(self, html):
        return ho.analyser(html, {}, "https://ex.fr/p", modules=[("ressources_site", ressources_site)])["ressources_site"]

    def test_ilots_modulepreload_et_exclusions(self):
        r = self.lire('<head><link rel="modulepreload" href="/_astro/m.A1b2C3d4.js"><link rel="preload" as="font" href="/f.woff2">'
                      '<link rel="stylesheet" href="/s.css"><link rel="icon" href="/favicon.ico"></head><body>'
                      '<astro-island component-url="/_astro/C.A1b2C3d4.js" renderer-url="/_astro/r.A1b2C3d4.js" '
                      'before-hydration-url="/_astro/h.A1b2C3d4.js"></astro-island>'
                      '<template><img src="/dans-template.png"></template><noscript><img src="/dans-noscript.png"></noscript>'
                      '<img src="data:image/png;base64,AAAA"><script src="//cdn.x.org/a.js"></script></body>')
        paires = sorted((x["type"], x["url"].replace("https://ex.fr", "")) for x in r["ressources"])
        self.assertEqual(paires, [("css", "/s.css"), ("police", "/f.woff2"), ("script", "/_astro/C.A1b2C3d4.js"),
                                  ("script", "/_astro/h.A1b2C3d4.js"), ("script", "/_astro/m.A1b2C3d4.js"),
                                  ("script", "/_astro/r.A1b2C3d4.js")])   # le tiers (cdn.x.org) n'est plus collecté

    def test_style_en_ligne_decoupe_en_plusieurs_morceaux(self):
        r = self.lire('<style>@font-face{font-family:X;<!-- c -->src:url(x.woff2)}</style>')
        self.assertEqual(r["polices"], [{"signature": "X (style en ligne)", "n": 1}])


class TestBudget(unittest.TestCase):
    def test_arret_au_budget(self):
        def lent(u, timeout=20, method="GET", max_bytes=3_000_000, ua=None, extra_headers=None):
            time.sleep(0.3)
            return {"status": 200, "headers": {}, "raw_bytes": 10, "body": b""}
        pages = {"https://ex.fr/": {"obs": {"ressources_site": {"ressources": [
            {"type": "image", "url": "https://ex.fr/i{0}.png".format(i)} for i in range(10)]}}}}
        ctx = {"fetch": lent, "host": "ex.fr", "ressources_max": 400, "timeout": 5, "budget_reseau_s": 0.5, "meta": {}}
        ressources_site.apres_crawl(pages, ctx)
        self.assertTrue(ctx["meta"]["ressources"]["budget_atteint"])
        self.assertLessEqual(ctx["meta"]["ressources"]["mesurees"], 3)
        self.assertEqual(ctx["meta"]["ressources"]["non_verifiees"], 10 - ctx["meta"]["ressources"]["mesurees"])


class TestAnalyseSeverite(unittest.TestCase):
    """I5 : une seule gravité par clé asset_sans_cache : moyenne si un asset >= 100 Ko est servi sans cache (max-age=0, no-cache, no-store)."""

    def sev(self, ressources):
        vus = []
        ctx = {"ressources": ressources, "sources_ressources": {u: ["https://ex.fr/"] for u in ressources}, "polices_css": {}}
        ressources_site.issues({}, lambda cle, lib, sev, ex, n=1, domaine=None: vus.append((cle, sev)), ctx)
        return sorted({s for c, s in vus if c == "asset_sans_cache"})

    def m(self, octets, cache):
        return {"type": "image", "statut": 200, "octets": octets, "cache": cache, "ctype": "image/png"}

    def test_189_ko_max_age_0_moyenne(self):
        self.assertEqual(self.sev({"https://ex.fr/agent-avatar.png": self.m(189 * 1024, "max-age=0")}), ["moyenne"])

    def test_seuil_100_ko_inclus(self):
        self.assertEqual(self.sev({"https://ex.fr/a.png": self.m(100 * 1024, "no-store")}), ["moyenne"])
        self.assertEqual(self.sev({"https://ex.fr/a.png": self.m(100 * 1024, "no-cache")}), ["moyenne"])
        self.assertEqual(self.sev({"https://ex.fr/a.png": self.m(100 * 1024 - 1, "no-store")}), ["basse"])

    def test_gros_mais_cache_non_nul_ou_absent_basse(self):
        self.assertEqual(self.sev({"https://ex.fr/a.png": self.m(300_000, "max-age=60")}), ["basse"])
        self.assertEqual(self.sev({"https://ex.fr/a.png": self.m(300_000, "")}), ["basse"])
        self.assertEqual(self.sev({"https://ex.fr/a.png": self.m(300_000, "public, s-maxage=86400")}), ["basse"])

    def test_melange_une_seule_gravite_pour_la_cle(self):
        r = {"https://ex.fr/petit.png": self.m(2_000, "max-age=0"), "https://ex.fr/gros.png": self.m(189 * 1024, "max-age=0")}
        self.assertEqual(self.sev(r), ["moyenne"])
        self.assertEqual(self.sev({"https://ex.fr/petit.png": self.m(2_000, "max-age=0")}), ["basse"])

    def test_police_sans_font_display_reste_basse(self):
        vus = []
        ressources_site.issues({}, lambda cle, lib, sev, ex, n=1, domaine=None: vus.append((cle, sev)),
                               {"ressources": {}, "polices_css": {"A (/s.css)": ["https://ex.fr/"]}})
        self.assertEqual(vus, [("police_sans_font_display", "basse")])


def _empreintes(forme, n, graine):
    """Empreintes Vite/Rollup : 8 caractères de l'alphabet base64url (A-Za-z0-9_-)."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
    r = random.Random(graine)
    return ["/assets/index{0}{1}.js".format(forme, "".join(r.choice(alphabet) for _ in range(8))) for _ in range(n)]


class TestHashe(unittest.TestCase):
    """I4 : empreintes Vite/Astro en formes tiret et point, avec lettres seules, « _ » ou « - » dans l'empreinte, et préfixe base."""

    def test_empreintes_aleatoires_99_pour_cent(self):
        for forme in ("-", "."):
            chemins = _empreintes(forme, 5000, 2024)
            reconnus = sum(ressources_site.hashe(c) for c in chemins)
            self.assertGreaterEqual(reconnus / len(chemins), 0.99, "forme {0!r} : {1}/{2}".format(forme, reconnus, len(chemins)))

    def test_cas_precis_reconnus(self):
        for c in ("/assets/index-DiwrgTda.js", "/assets/Layout-C2xYpQ_9.js", "/assets/Layout-C2xY-Q9a.js", "/assets/index.Bx9a8K2q.js.map",
                  "/blog/_astro/x.png", "/base/_next/static/chunks/a.js", "/assets/app.f3a9c2d1e8.webp", "/assets/index-CPTKQKQK.js",
                  "/assets/index.DiwrgTda.js"):
            self.assertTrue(ressources_site.hashe(c), c)

    def test_noms_ordinaires_non_hashes(self):
        for c in ("/logo.png", "/hero-image.webp", "/logo-original.png", "/Settings.css", "/hero-banner.jpg", "/team-photos-2023.jpg",
                  "/IMG-20240115.jpg", "/agent-avatar.png", "/images/hero-4000.jpg", "/hero-1920x1080.png", "/background.jpg",
                  "/fonts/open-sans.woff2", "/images/team-members.png", "/favicon.ico", "/og-image.png"):
            self.assertFalse(ressources_site.hashe(c), c)


class TestProprietesIlots(unittest.TestCase):
    """I3 : les images passées en props d'un <astro-island> (îlot rendu vide) sont lues. Îlot SYNTHÉTIQUE (aucune donnée de site réel)."""

    def lire(self, html, url="https://ex.fr/p"):
        return ho.analyser(html, {}, url, modules=[("ressources_site", ressources_site)])["ressources_site"]

    def test_props_image(self):
        r = self.lire('<astro-island uid="1" component-url="/_astro/C.A1b2C3d4.js" renderer-url="/_astro/client.Q1w2E3r4.js" '
                      'props="{&quot;avatarUrl&quot;:[0,&quot;/agent-avatar.png&quot;],&quot;color&quot;:[0,&quot;#171717&quot;]}" '
                      'ssr client="idle"></astro-island>')
        urls = sorted((x["type"], x["url"]) for x in r["ressources"])
        self.assertIn(("image", "https://ex.fr/agent-avatar.png"), urls)
        self.assertEqual([u for _, u in urls if "171717" in u], [])
        self.assertEqual(len(urls), 3)

    def test_props_imbriquees_et_hotes(self):
        r = self.lire('<astro-island props="{&quot;items&quot;:[1,[[0,{&quot;src&quot;:[0,&quot;/a/b.WEBP?v=2&quot;]}],'
                      '[0,{&quot;src&quot;:[0,&quot;https://cdn.ailleurs.org/c.png&quot;]}],[0,{&quot;src&quot;:[0,&quot;https://ex.fr/d.svg&quot;]}]]],'
                      '&quot;titre&quot;:[0,&quot;logo.png est mon fichier&quot;]}"></astro-island>')
        urls = sorted(x["url"] for x in r["ressources"])
        self.assertEqual(urls, ["https://ex.fr/a/b.WEBP?v=2", "https://ex.fr/d.svg"])   # le tiers et le texte libre sont écartés

    def test_props_invalides_ou_enormes_ignorees(self):
        self.assertEqual(self.lire('<astro-island props="pas du json {"></astro-island>')["ressources"], [])
        enorme = "{&quot;a&quot;:[0,&quot;" + "x" * 70_000 + ".png&quot;]}"
        self.assertEqual(self.lire('<astro-island props="{0}"></astro-island>'.format(enorme))["ressources"], [])


class TestCoupePage(unittest.TestCase):
    """I6 : filtre hôte / /_image AVANT la coupe, scripts et CSS d'abord, ressources coupées dénombrées."""

    def lire(self, html):
        return ho.analyser(html, {}, "https://ex.fr/p", modules=[("ressources_site", ressources_site)])["ressources_site"]

    def test_ilot_apres_200_images_present(self):
        imgs = "".join('<img src="/i{0}.png" alt="">'.format(i) for i in range(200))
        tiers = "".join('<img src="https://t.example.org/t{0}.png" alt="">'.format(i) for i in range(50))
        dyn = "".join('<img src="/_image?href=%2Fa{0}.png&w=10" alt="">'.format(i) for i in range(50))
        r = self.lire(tiers + dyn + imgs + '<astro-island component-url="/_astro/Chat.X9aB3cD4.js" renderer-url="/_astro/client.Q1w2E3r4.js">'
                      '</astro-island>')
        urls = [x["url"] for x in r["ressources"]]
        self.assertEqual(len(urls), 150)
        self.assertIn("https://ex.fr/_astro/Chat.X9aB3cD4.js", urls)
        self.assertIn("https://ex.fr/_astro/client.Q1w2E3r4.js", urls)
        self.assertFalse([u for u in urls if "t.example.org" in u or "/_image" in u])
        self.assertEqual(r["ressources_coupees"], 52)   # 200 images + 2 scripts - 150

    def test_meta_cumule_les_coupes(self):
        pages = {"https://ex.fr/a": {"obs": {"ressources_site": {"ressources": [], "ressources_coupees": 7}}},
                 "https://ex.fr/b": {"obs": {"ressources_site": {"ressources": [], "ressources_coupees": 5}}}}
        ctx = {"fetch": lambda *a, **k: None, "host": "ex.fr", "ressources_max": 400, "timeout": 5, "budget_reseau_s": 5, "meta": {}}
        ressources_site.apres_crawl(pages, ctx)
        self.assertEqual(ctx["meta"]["ressources"]["coupees_par_page"], 12)


class TestMineurs(unittest.TestCase):
    def lire(self, html):
        return ho.analyser(html, {}, "https://ex.fr/p", modules=[("ressources_site", ressources_site)])["ressources_site"]

    def test_nomodule_ignore(self):
        r = self.lire('<script nomodule src="/_astro/polyfills-legacy.A1b2C3d4.js"></script><script type="module" src="/_astro/m.A1b2C3d4.js"></script>')
        self.assertEqual([x["url"] for x in r["ressources"]], ["https://ex.fr/_astro/m.A1b2C3d4.js"])

    def test_famille_de_l_api_fonts_sans_empreinte_de_build(self):
        css = '@font-face{font-family:"Inter Variable-b5cc9897a86da6fa";src:url(/_astro/fonts/a.woff2);font-display:block}'
        self.assertEqual(ressources_site.polices_sans_display(css, "style en ligne"),
                         ["Inter Variable (style en ligne, font-display: block)"])
        self.assertEqual(ressources_site.polices_sans_display('@font-face{font-family:Poppins-de0d09395361de89;src:url(a.woff2)}', "/s.css"),
                         ["Poppins (/s.css)"])

    def test_compteurs_secret_et_css_non_lus(self):
        urls = ["https://ex.fr/css/{0}.css".format(i) for i in range(12)]
        pages = pages_de(*([("css", u) for u in urls] + [("image", "https://ex.fr/k/…/a.png")]))

        def f(u, timeout=20, method="GET", max_bytes=3_000_000, ua=None, extra_headers=None):
            return {"status": 200, "headers": {"content-length": "5"}, "raw_bytes": 5, "body": b"a{}", "chain": [], "final_url": u}
        ctx = {"fetch": f, "host": "ex.fr", "ressources_max": 400, "timeout": 5, "budget_reseau_s": 30, "meta": {}}
        ressources_site.apres_crawl(pages, ctx)
        m = ctx["meta"]["ressources"]
        self.assertEqual((m["ignorees_secret"], m["css_non_lus"]), (1, 2))


class TestSurete(unittest.TestCase):
    """M6 : aucune requête vers un autre hôte, port ou IP ; filtre figé."""

    def test_aucun_hote_ni_port_etranger(self):
        appels = []

        def f(u, timeout=20, method="GET", max_bytes=3_000_000, ua=None, extra_headers=None):
            appels.append(u)
            return {"status": 200, "headers": {"content-length": "5"}, "raw_bytes": 5, "body": b"", "chain": [], "final_url": u}
        mauvais = ["http://169.254.169.254/x.png", "//169.254.169.254/x.png", "http://ex.fr@169.254.169.254/x.png",
                   "http://ex.fr:8080/x.png", "http://ex.fr.evil.com/x.png", "http://[::1]/x.png", "http://127.0.0.1/x.png"]
        pages = pages_de(*[("image", u) for u in mauvais] + [("image", "https://ex.fr/ok.png")])
        ctx = {"fetch": f, "host": "ex.fr", "ressources_max": 400, "timeout": 5, "budget_reseau_s": 30, "meta": {}}
        ressources_site.apres_crawl(pages, ctx)
        self.assertEqual(appels, ["https://ex.fr/ok.png"])


def _serveur(corps, gz):
    """Serveur imitant nginx / Express : HEAD jamais compressé (Content-Length du fichier brut), GET compressé si gzip accepté."""
    class H(BaseHTTPRequestHandler):
        requetes = []

        def _rep(self):
            H.requetes.append((self.command, self.path, self.headers.get("Accept-Encoding", "")))
            h = {"Content-Type": "text/javascript", "Cache-Control": "public, max-age=31536000, immutable"}
            if self.command == "GET" and "gzip" in self.headers.get("Accept-Encoding", ""):
                data, h["Content-Encoding"] = gz, "gzip"
            else:
                data = corps
            self.send_response(200)
            for k, v in h.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(corps) if self.command == "HEAD" else len(data)))
            self.end_headers()
            if self.command == "GET":
                self.wfile.write(data)
        do_GET = do_HEAD = _rep

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, H


class TestPoidsTransfere(unittest.TestCase):
    """I2 : un bundle bien servi (HEAD brut, GET gzip) n'est pas un js_lourd ; mesure sur les octets réellement transférés."""

    def test_head_brut_get_gzip(self):
        corps = (b"export const a = function(){ return 'texte repetitif de bundle'; };\n" * 9000)   # ~590 Ko brut, quelques Ko gzip
        gz = gzip.compress(corps)
        self.assertLess(len(gz), 20_000)
        srv, H = _serveur(corps, gz)
        try:
            hote = "127.0.0.1:{0}".format(srv.server_port)
            u = "http://{0}/_astro/ChatBubble.DKLw9cvg.js".format(hote)
            ctx = {"fetch": crawl_site.fetch, "host": hote, "ressources_max": 10, "timeout": 5, "budget_reseau_s": 30, "meta": {}}
            ressources_site.apres_crawl(pages_de(("script", u), page="http://{0}/".format(hote)), ctx)
            m = ctx["ressources"][u]
            self.assertEqual(m["octets"], len(gz))
            self.assertEqual(m["octets_decompresses"], len(corps))
            self.assertEqual(m["encodage"], "gzip")
            self.assertEqual([r[0] for r in H.requetes], ["GET"])
            self.assertIn("gzip", H.requetes[0][2])
            self.assertIn("br", H.requetes[0][2])
            vus = []
            ressources_site.issues({}, lambda cle, *a, **k: vus.append(cle), ctx)
            self.assertNotIn("js_lourd", vus)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_svg_lu_en_get_aussi(self):
        appels = []

        def f(u, timeout=20, method="GET", max_bytes=3_000_000, ua=None, extra_headers=None):
            appels.append(method)
            return {"status": 200, "headers": {"content-encoding": "gzip", "content-type": "image/svg+xml"}, "raw_bytes": 4000,
                    "body": b"<svg/>" * 1000, "chain": [], "final_url": u}
        ctx = {"fetch": f, "host": "ex.fr", "ressources_max": 10, "timeout": 5, "budget_reseau_s": 30, "meta": {}}
        ressources_site.apres_crawl(pages_de(("image", "https://ex.fr/logo.svg")), ctx)
        self.assertEqual(appels, ["GET"])
        self.assertEqual(ctx["ressources"]["https://ex.fr/logo.svg"]["octets"], 4000)

    def test_brotli_sans_chiffre_decompresse(self):
        def f(u, timeout=20, method="GET", max_bytes=3_000_000, ua=None, extra_headers=None):
            return {"status": 200, "headers": {"content-encoding": "br", "content-type": "text/javascript"}, "raw_bytes": 90_000,
                    "body": b"\x00" * 90_000, "chain": [], "final_url": u}
        ctx = {"fetch": f, "host": "ex.fr", "ressources_max": 10, "timeout": 5, "budget_reseau_s": 30, "meta": {}}
        ressources_site.apres_crawl(pages_de(("script", "https://ex.fr/a.js")), ctx)
        m = ctx["ressources"]["https://ex.fr/a.js"]
        self.assertEqual((m["octets"], m["encodage"]), (90_000, "br"))
        self.assertNotIn("octets_decompresses", m)   # fetch ne décode pas le brotli : le corps reçu n'est pas le texte


class TestDecompressionBornee(unittest.TestCase):
    """I1 : jamais plus que le plafond de lecture une fois décompressé ; le plafond est demandé à fetch quand il l'accepte."""

    def test_plafond_transmis_et_aucun_chiffre_si_atteint(self):
        recus = []

        def f(u, timeout=20, method="GET", max_bytes=3_000_000, ua=None, extra_headers=None, max_decompressed=None):
            recus.append(max_decompressed)
            n = max_decompressed or 30_000_000
            return {"status": 200, "headers": {"content-encoding": "gzip", "content-type": "text/javascript"}, "raw_bytes": 29_000,
                    "body": b"\x00" * n, "chain": [], "final_url": u}
        ctx = {"fetch": f, "host": "ex.fr", "ressources_max": 10, "timeout": 5, "budget_reseau_s": 30, "meta": {}}
        ressources_site.apres_crawl(pages_de(("script", "https://ex.fr/bombe.js"), ("css", "https://ex.fr/b.css")), ctx)
        self.assertTrue(recus and all(r is not None and r <= 2_000_000 for r in recus), recus)
        m = ctx["ressources"]["https://ex.fr/bombe.js"]
        self.assertNotIn("octets_decompresses", m)
        self.assertTrue(m["decompresse_tronque"])

    def test_corps_demesure_d_un_fetch_non_borne_jamais_conserve(self):
        def f(u, timeout=20, method="GET", max_bytes=3_000_000, ua=None, extra_headers=None):
            return {"status": 200, "headers": {"content-encoding": "gzip", "content-type": "text/css"}, "raw_bytes": 29_000,
                    "body": b"a{}" * 10_000_000, "chain": [], "final_url": u}
        ctx = {"fetch": f, "host": "ex.fr", "ressources_max": 10, "timeout": 5, "budget_reseau_s": 30, "meta": {}}
        ressources_site.apres_crawl(pages_de(("css", "https://ex.fr/b.css")), ctx)
        self.assertNotIn("corps", ctx["ressources"]["https://ex.fr/b.css"])
        self.assertLess(len(json.dumps(ctx["ressources"])), 2000)


if __name__ == "__main__":
    unittest.main()
