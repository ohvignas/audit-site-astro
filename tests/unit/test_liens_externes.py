import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ICI = pathlib.Path(__file__).resolve().parent
SCRIPTS = ICI.parents[1] / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ICI))
import crawl_site  # noqa: E402
import html_observateurs as ho  # noqa: E402
import liens_externes  # noqa: E402
from site_local import HTML, SiteLocal  # noqa: E402


def faux(rep):
    """Faux fetch (aucun réseau) : rep(url, method, kw) -> dict de réponse ; enregistre chaque appel."""
    appels = []

    def fetch(u, timeout=20, method="GET", max_bytes=8_000_000, ua=None, extra_headers=None):
        appels.append({"url": u, "method": method, "ua": ua, "extra": extra_headers, "t": time.monotonic(), "timeout": timeout})
        r = rep(u, method)
        return r if isinstance(r, dict) else {"status": r, "error": None}
    fetch.appels = appels
    return fetch


def pages_de(*liens_par_page):
    """pages = {url_page: {"obs": {"liens_externes": {"externes": [...]}}}} dans l'ordre donné."""
    return {"https://ex.fr/p{0}".format(i): {"obs": {"liens_externes": {"externes": list(ls)}}} for i, ls in enumerate(liens_par_page)}


def ctx_de(fetch, **kw):
    ctx = {"fetch": fetch, "delai_externe": 0, "liens_externes_max": 300, "timeout": 5, "meta": {}}
    ctx.update(kw)
    return ctx


class TestClassement(unittest.TestCase):
    def test_classer(self):
        c = liens_externes.classer
        self.assertEqual([c(404, None), c(410, None), c(0, "<urlopen error [Errno -2] Name or service not known>"),
                          c(0, "<urlopen error [Errno 8] nodename nor servname provided, or not known>")], ["casse"] * 4)
        self.assertEqual([c(403, None), c(429, None), c(999, None), c(503, None), c(0, "timed out"),
                          c(0, "Temporary failure in name resolution"), c(-1, "plus de 10 redirections")], ["a_verifier"] * 7)
        self.assertEqual([c(200, None), c(301, None)], [None, None])

    def test_defi_cloudflare_jamais_casse(self):
        self.assertEqual(liens_externes.classer(404, "défi Cloudflare"), "a_verifier")
        self.assertEqual(liens_externes.classer(403, "défi Cloudflare"), "a_verifier")


class TestObservateur(unittest.TestCase):
    def liens(self, html, url="https://www.ex.fr/page"):
        return ho.analyser(html, {}, url, modules=[("liens_externes", liens_externes)])["liens_externes"]["externes"]

    def test_externes_sans_fragment_ni_variantes_du_site(self):
        html = ('<a href="https://autre.org/a#haut">a</a><a href="https://autre.org/a#bas">a bis</a><a href="/local">l</a>'
                '<a href="https://ex.fr/x">www</a><a href="http://WWW.EX.FR/y">www</a><a href="mailto:a@b.fr">m</a>'
                '<a href="https://z.org/b" hidden>caché</a><a href="https://y.org/c">c</a>')
        self.assertEqual(self.liens(html), ["https://autre.org/a", "https://y.org/c"])

    def test_ordre_du_document_et_plafond_par_page(self):
        html = "".join('<a href="https://h{0}.org/">x</a>'.format(i) for i in (9, 1, 5))
        self.assertEqual(self.liens(html), ["https://h9.org/", "https://h1.org/", "https://h5.org/"])  # pas de tri alphabétique
        html = "".join('<a href="https://h{0}.org/">x</a>'.format(i) for i in range(250))
        self.assertEqual(len(self.liens(html)), 200)

    def test_aucun_secret_ni_identifiant_dans_les_liens_notes(self):
        html = '<a href="https://moi:mdp@autre.org/a?token=abcdef123456&page=2">a</a>'
        sortie = json.dumps(self.liens(html))
        self.assertNotIn("abcdef123456", sortie)
        self.assertNotIn("mdp", sortie)
        self.assertIn("autre.org/a", sortie)


class TestCrawl(unittest.TestCase):
    def test_liens_externes_du_site(self):
        externe = {"/ok": (200, HTML, "ok"), "/mort": (404, HTML, "non"), "/interdit": (403, HTML, "non")}
        with SiteLocal(externe) as autre:
            page = ('<html lang="fr"><head><title>Liens externes de test</title></head><body><main>'
                    '<a href="{0}/ok">ok</a> <a href="{0}/mort#x">mort</a> <a href="{0}/interdit">interdit</a>'
                    '<a href="http://nx.cobaye.invalid/ressource">absent</a> <a href="/local">local</a></main></body></html>').format(autre.base)
            with SiteLocal({"/": (200, HTML, page)}) as site, tempfile.TemporaryDirectory() as d:
                subprocess.run([sys.executable, str(SCRIPTS / "crawl_site.py"), site.url, "--out", d, "--delay", "0", "--max-pages", "3",
                                "--liens-externes", "10", "--delai-externe", "0", "--ressources", "0"], check=True, capture_output=True, timeout=180)
                issues = json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8"))
                meta = json.loads(pathlib.Path(d, "pages.json").read_text(encoding="utf-8"))["meta"]["modules"]
        self.assertEqual([e["lien"] for e in issues["external_broken"]["examples"]], [autre.base + "/mort", "http://nx.cobaye.invalid/ressource"])
        self.assertEqual([e["lien"] for e in issues["external_a_verifier"]["examples"]], [autre.base + "/interdit"])
        self.assertEqual(issues["external_broken"]["examples"][0]["liens_depuis"], [site.url])
        self.assertEqual(meta["liens_externes"], {"trouves": 4, "verifies": 4, "budget_atteint": False})
        self.assertEqual(meta["liens_externes_non_verifies"], {"total": 0, "par_plafond": 0, "par_budget": 0})
        # HEAD d'abord, GET de repli sur 404 / 403 (seul le GET conclut « cassé »)
        self.assertEqual(sorted(autre.requetes), ["/interdit", "/interdit", "/mort", "/mort", "/ok"])

    def test_debit_par_hote(self):
        appels = []

        def faux_fetch(u, timeout=20, method="GET", max_bytes=8_000_000, ua=None, extra_headers=None):
            appels.append(time.monotonic())
            return {"status": 200, "error": None}
        pages = {"https://ex.fr/": {"obs": {"liens_externes": {"externes": ["https://a.org/1", "https://a.org/2", "https://a.org/3"]}}}}
        ctx = {"fetch": faux_fetch, "delai_externe": 0.3, "liens_externes_max": 10, "timeout": 5, "meta": {}}
        liens_externes.apres_crawl(pages, ctx)
        self.assertGreaterEqual(appels[-1] - appels[0], 0.55)

    def test_pause_aussi_entre_head_et_get_du_meme_hote(self):
        f = faux(lambda u, m: 405 if m == "HEAD" else 200)
        liens_externes.apres_crawl(pages_de(["https://a.org/1"]), ctx_de(f, delai_externe=0.3))
        self.assertEqual([a["method"] for a in f.appels], ["HEAD", "GET"])
        self.assertGreaterEqual(f.appels[1]["t"] - f.appels[0]["t"], 0.28)

    def test_pas_de_pause_entre_hotes_differents(self):
        f = faux(lambda u, m: 200)
        liens_externes.apres_crawl(pages_de(["https://a.org/", "https://b.org/", "https://c.org/"]), ctx_de(f, delai_externe=1.0))
        self.assertLess(f.appels[-1]["t"] - f.appels[0]["t"], 0.5)

    def test_budget_de_temps(self):  # pré-vol : sans budget, le délai de l'étape coupait le crawl et perdait tout
        def lent(u, timeout=20, method="GET", max_bytes=8_000_000, ua=None, extra_headers=None):
            time.sleep(0.3)
            return {"status": 200, "error": None}
        pages = {"https://ex.fr/": {"obs": {"liens_externes": {"externes": ["https://h{0}.org/".format(i) for i in range(10)]}}}}
        ctx = {"fetch": lent, "delai_externe": 0, "liens_externes_max": 300, "timeout": 5, "budget_reseau_s": 0.5, "meta": {}}
        liens_externes.apres_crawl(pages, ctx)
        m = ctx["meta"]["liens_externes"]
        self.assertTrue(m["budget_atteint"])
        self.assertLessEqual(m["verifies"], 3)
        self.assertEqual(ctx["meta"]["liens_externes_non_verifies"], {"total": 10 - m["verifies"], "par_plafond": 0, "par_budget": 10 - m["verifies"]})

    def test_la_pause_ne_depasse_pas_le_budget(self):
        f = faux(lambda u, m: 200)
        ctx = ctx_de(f, delai_externe=5.0, budget_reseau_s=0.5)
        t0 = time.monotonic()
        liens_externes.apres_crawl(pages_de(["https://a.org/1", "https://a.org/2"]), ctx)
        self.assertLess(time.monotonic() - t0, 2)
        self.assertEqual((ctx["meta"]["liens_externes"]["verifies"], ctx["meta"]["liens_externes"]["budget_atteint"]), (1, True))

    def test_plafond_et_priorite_par_nombre_de_pages(self):
        # pas de troncature alphabétique : les liens les plus liés d'abord, puis l'ordre de première apparition
        f = faux(lambda u, m: 200)
        pages = pages_de(["https://z.org/rare", "https://a.org/un"], ["https://z.org/rare", "https://m.org/trois"],
                         ["https://m.org/trois", "https://y.org/seul"], ["https://m.org/trois", "https://z.org/rare"])
        ctx = ctx_de(f, liens_externes_max=3)
        liens_externes.apres_crawl(pages, ctx)
        self.assertEqual([a["url"] for a in f.appels], ["https://z.org/rare", "https://m.org/trois", "https://a.org/un"])
        self.assertEqual(ctx["meta"]["liens_externes"], {"trouves": 4, "verifies": 3, "budget_atteint": False})
        self.assertEqual(ctx["meta"]["liens_externes_non_verifies"], {"total": 1, "par_plafond": 1, "par_budget": 0})

    def test_ordre_de_premiere_apparition_a_egalite(self):
        f = faux(lambda u, m: 200)
        pages = pages_de(["https://z.org/1", "https://b.org/2"], ["https://a.org/3"])
        liens_externes.apres_crawl(pages, ctx_de(f))
        self.assertEqual([a["url"] for a in f.appels], ["https://z.org/1", "https://b.org/2", "https://a.org/3"])

    def test_get_apres_un_404_en_head(self):
        def head_404(u, timeout=20, method="GET", max_bytes=8_000_000, ua=None, extra_headers=None):
            return {"status": 404 if method == "HEAD" else 200, "error": None}
        pages = {"https://ex.fr/": {"obs": {"liens_externes": {"externes": ["https://a.org/x"]}}}}
        ctx = {"fetch": head_404, "delai_externe": 0, "liens_externes_max": 10, "timeout": 5, "meta": {}}
        liens_externes.apres_crawl(pages, ctx)
        self.assertEqual(ctx["externes"]["https://a.org/x"]["statut"], 200)

    def test_repli_get_avec_range_sur_405_et_501(self):
        for refus in (405, 501):
            f = faux(lambda u, m, refus=refus: refus if m == "HEAD" else 206)
            ctx = ctx_de(f)
            liens_externes.apres_crawl(pages_de(["https://a.org/x"]), ctx)
            self.assertEqual([a["method"] for a in f.appels], ["HEAD", "GET"])
            self.assertEqual(f.appels[1]["extra"], {"Range": "bytes=0-0"})
            self.assertIsNone(f.appels[0]["extra"])
            self.assertEqual(ctx["externes"]["https://a.org/x"]["statut"], 206)

    def test_un_404_reste_casse_seulement_si_le_get_le_confirme(self):
        f = faux(lambda u, m: 404)
        ctx = ctx_de(f)
        liens_externes.apres_crawl(pages_de(["https://a.org/x"]), ctx)
        self.assertEqual([a["method"] for a in f.appels], ["HEAD", "GET"])
        self.assertEqual(liens_externes.classer(**{k: ctx["externes"]["https://a.org/x"][k] for k in ("statut", "erreur")}), "casse")

    def test_pas_de_get_apres_un_429(self):  # le serveur demande de ralentir : on ne le sollicite pas une seconde fois
        f = faux(lambda u, m: 429)
        liens_externes.apres_crawl(pages_de(["https://a.org/x"]), ctx_de(f))
        self.assertEqual([a["method"] for a in f.appels], ["HEAD"])

    def test_user_agent_honnete(self):
        f = faux(lambda u, m: 200)
        liens_externes.apres_crawl(pages_de(["https://a.org/x"]), ctx_de(f, ua_navigateur="Mozilla/5.0 (Macintosh) Chrome/128.0 Safari/537.36"))
        ua = f.appels[0]["ua"]
        self.assertIn("AuditSiteAstro", ua)
        self.assertNotIn("Chrome", ua)
        self.assertNotIn("Safari", ua)

    def test_timeout_court_et_borne_par_le_budget(self):
        f = faux(lambda u, m: 200)
        liens_externes.apres_crawl(pages_de(["https://a.org/x"]), ctx_de(f, timeout=60))
        self.assertLessEqual(f.appels[0]["timeout"], 8)

    def test_defi_cloudflare_et_delai_sont_a_verifier(self):
        f = faux(lambda u, m: {"status": 404, "error": None, "headers": {"cf-mitigated": "challenge"}} if "cf" in u else
                 {"status": 0, "error": "<urlopen error timed out>"})
        ctx = ctx_de(f)
        liens_externes.apres_crawl(pages_de(["https://cf.org/x", "https://lent.org/x"]), ctx)
        ajoutes = []
        liens_externes.issues({}, lambda cle, libelle, sev, ex=None, **kw: ajoutes.append((cle, ex["lien"])), ctx)
        self.assertEqual(sorted(ajoutes), [("external_a_verifier", "https://cf.org/x"), ("external_a_verifier", "https://lent.org/x")])

    def test_issues_sans_secret_et_domaine(self):
        f = faux(lambda u, m: 404)
        ctx = ctx_de(f)
        pages = {"https://ex.fr/p?token=zzzsecretzzz": {"obs": {"liens_externes": {"externes": ["https://a.org/x?cle=secret123456&q=1#f"]}}}}
        liens_externes.apres_crawl(pages, ctx)
        recus = []
        liens_externes.issues(pages, lambda cle, libelle, sev, ex=None, **kw: recus.append((cle, sev, ex, kw)), ctx)
        cle, sev, ex, kw = recus[0]
        self.assertEqual((cle, sev, kw["domaine"]), ("external_broken", "moyenne", "SEO technique"))
        self.assertEqual(ex["lien"], "https://a.org/x")
        self.assertNotIn("secret", json.dumps(recus))

    def test_une_erreur_reseau_non_dns_nest_pas_cassee(self):
        f = faux(lambda u, m: {"status": 0, "error": "<urlopen error [Errno -3] Temporary failure in name resolution>"})
        ctx = ctx_de(f)
        liens_externes.apres_crawl(pages_de(["https://a.org/x"]), ctx)
        recus = []
        liens_externes.issues({}, lambda cle, *a, **kw: recus.append(cle), ctx)
        self.assertEqual(recus, ["external_a_verifier"])


class TestRequeteReelle(unittest.TestCase):
    """Vraie requête vers un serveur local : cookies jamais renvoyés, redirections limitées à 5."""

    def serveur(self):
        vus = []

        class H(BaseHTTPRequestHandler):
            def _r(self):
                vus.append((self.command, self.path, self.headers.get("Cookie"), self.headers.get("User-Agent")))
                self.send_response(302)
                self.send_header("Location", "/suite{0}".format(len(vus)))
                self.send_header("Set-Cookie", "session=abc; Path=/")
                self.send_header("Content-Length", "0")
                self.end_headers()
            do_GET = do_HEAD = _r

            def log_message(self, *a):
                pass
        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv, vus

    def test_cinq_redirections_au_plus_et_aucun_cookie(self):
        srv, vus = self.serveur()
        try:
            lien = "http://127.0.0.1:{0}/boucle".format(srv.server_port)
            ctx = ctx_de(crawl_site.fetch)
            liens_externes.apres_crawl(pages_de([lien]), ctx)
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual(len(vus), 6)  # 5 redirections suivies, la 6e réponse n'est pas suivie ; HEAD seul : -1 est « à vérifier », pas de GET de repli
        self.assertEqual({v[0] for v in vus}, {"HEAD"})
        self.assertEqual({v[2] for v in vus}, {None})
        self.assertIn("AuditSiteAstro", vus[0][3])
        r = ctx["externes"][lien]
        self.assertEqual(liens_externes.classer(r["statut"], r["erreur"]), "a_verifier")
        self.assertIn("5 redirections", r["erreur"])


if __name__ == "__main__":
    unittest.main()
