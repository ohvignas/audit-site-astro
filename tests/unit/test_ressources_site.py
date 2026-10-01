import json
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

ICI = pathlib.Path(__file__).resolve().parent
SCRIPTS = ICI.parents[1] / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ICI))
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
                              ("asset_sans_cache", "basse", "Serveur / HTTP"), ("police_sans_font_display", "basse", "Performance")):
            self.assertEqual((self.issues[cle]["severity"], self.issues[cle]["domaine"]), (sev, dom), cle)

    def test_ni_tiers_ni_image_dynamique(self):
        self.assertFalse([r for r in self.requetes if r.startswith("/_image")], "l'endpoint /_image est mesuré ailleurs")
        self.assertNotIn("cdn.ailleurs.org", json.dumps(self.issues))

    def test_meta_et_non_verifiees(self):
        m = self.pages["meta"]["modules"]["ressources"]
        self.assertEqual((m["trouvees"], m["mesurees"], m["budget_atteint"], m["non_verifiees"]), (6, 6, False, 0))

    def test_poids_compresse_et_non_compresse_connus(self):
        # le JS de l'îlot est mesuré par HEAD (Content-Length) : même poids avec ou sans compression quand le serveur ne compresse pas
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
            if method == "HEAD":
                return {"status": 200, "headers": {"content-encoding": "gzip", "content-type": "text/javascript"}, "raw_bytes": 0,
                        "body": b"", "chain": [], "final_url": url}
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
                                  ("script", "/_astro/r.A1b2C3d4.js"), ("script", "https://cdn.x.org/a.js")])

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


if __name__ == "__main__":
    unittest.main()
