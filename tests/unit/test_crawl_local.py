from collections import Counter
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ICI = pathlib.Path(__file__).resolve().parent
RACINE = ICI.parents[1]
sys.path.insert(0, str(ICI))
from site_local import HTML, SiteLocal  # noqa: E402

CRAWL = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts/crawl_site.py"


def page(corps, tete=""):
    return ("<html lang='fr'><head><meta name='viewport' content='width=device-width'>"
            "<title>Titre de test suffisamment long</title>" + tete + "</head><body><main>" + corps + "</main></body></html>")


ROUTES = {
    "/": (200, HTML, page('<a href="/canon-cassee">Canonical</a> <a href="/formulaire">Formulaire</a> '
                          '<a href="/canon-bloquee">Bloquée</a>')),
    # canonical vers une cible interdite par robots.txt : jamais demandée (revue finale M2)
    "/canon-bloquee": (200, HTML, page("<p>Asset</p>", "<link rel='canonical' href='@@BASE@@/_astro/cible'>")),
    "/robots.txt": (200, {"Content-Type": "text/plain"},
                    "User-agent: *\nDisallow: /_astro/\n\nSitemap: @@BASE@@/sitemap.xml\n"),
    "/sitemap.xml": (200, {"Content-Type": "application/xml"},
                     '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                     "<url><loc>@@BASE@@/r/cachee</loc></url><url><loc>@@BASE@@/r/manque</loc></url></urlset>"),
    # URL du sitemap qui redirigent (comme http:// → https:// derrière un proxy) vers une page noindex et une 404
    "/r/cachee": (301, {"Location": "/cachee"}, ""),
    "/r/manque": (301, {"Location": "/manque"}, ""),
    "/cachee": (200, HTML, page("<p>Réservé</p>", "<meta name='robots' content='noindex'>")),
    # canonical vers une page jamais liée, en 404 (tâche 2)
    "/canon-cassee": (200, HTML, page("<p>Programme</p>", "<link rel='canonical' href='@@BASE@@/supprimee'>")),
    # champs de formulaire (tâche 3)
    "/formulaire": (200, HTML, page(
        '<input type="email" placeholder="Votre email">'           # sans libellé (placeholder seul)
        '<label for="nom">Nom</label><input id="nom">'             # libellé explicite
        '<label>Ville <input name="ville"></label>'                # libellé englobant
        '<input type="hidden" name="jeton"><input aria-label="Recherche"><button>OK</button>'
        '<input name="_gotcha" style="display:none" tabindex="-1"><div hidden><input name="bot-field"></div>')),  # pièges
}


class TestCrawlLocal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        with SiteLocal(ROUTES) as site:
            cls.requetes = site.requetes
            r = subprocess.run([sys.executable, str(CRAWL), site.url, "--out", cls.tmp.name, "--delay", "0",
                                "--max-pages", "50", "--timeout", "5"], capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr[-2000:]
        cls.issues = json.loads(pathlib.Path(cls.tmp.name, "issues.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def exemples(self, cle):
        return json.dumps(self.issues.get(cle, {}).get("examples", []), ensure_ascii=False)

    # Tâche 1 : la redirection d'une URL du sitemap ne masque plus la 404 ni le noindex de sa cible (S03, S04)
    def test_sitemap_redirige_puis_404_et_noindex(self):
        self.assertEqual(self.issues["sitemap_redirect"]["count"], 2)
        self.assertIn("/r/manque", self.exemples("sitemap_non200"))
        self.assertIn("/r/cachee", self.exemples("sitemap_noindex"))

    # Tâche 1 : Disallow: /_astro/ bloque le CSS/JS d'Astro (S38)
    def test_robots_bloque_les_assets_astro(self):
        self.assertEqual(self.issues.get("robots_blocks_assets", {}).get("examples"), ["/_astro/"])

    # Tâche 2 : canonical vers une page jamais liée : la cible est vérifiée quand même (S19)
    def test_canonical_vers_page_non_liee_en_404(self):
        ex = self.issues.get("canonical_bad_target", {}).get("examples", [])
        self.assertEqual([(e["url"].endswith("/canon-cassee"), e["statut_cible"]) for e in ex], [(True, 404)])
        self.assertNotIn("/supprimee", self.exemples("http_4xx"), "la cible n'est pas une page liée : pas de http_4xx")

    # Revue finale M2 : robots.txt respecté pour les cibles de canonical
    def test_cible_de_canonical_bloquee_par_robots_non_demandee(self):
        self.assertNotIn("/_astro/cible", self.requetes)
        meta = json.loads(pathlib.Path(self.tmp.name, "pages.json").read_text(encoding="utf-8"))["meta"]
        self.assertFalse(any(u.endswith("/_astro/cible") for u in meta["canonical_targets_checked"]))

    # Tâche 3 : champ de formulaire sans libellé (placeholder seul), invisible pour Lighthouse (A05)
    def test_champ_sans_libelle(self):
        it = self.issues.get("form_no_label", {})
        self.assertEqual(it.get("count"), 1)
        self.assertTrue(it["examples"][0]["url"].endswith("/formulaire"))


sys.path.insert(0, str(CRAWL.parent))
import crawl_site  # noqa: E402


def page_ok(u, og_image=True):
    return {"url": u, "status": 200, "final_status": 200, "final_url": u, "redirect_hops": 0, "redirect_chain": [],
            "is_html": True, "canonicals": [u], "title": "Titre de test suffisamment long " + u[-2:],
            "meta_description": "Description de test assez longue pour ne déclencher aucun contrôle de longueur " + u,
            "h1": ["Titre"], "content_words": 400, "depth": 1, "jsonld_types": ["Organization"], "og_title": True,
            "og_image": og_image, "lang": "fr", "viewport": True, "ttfb": 0.1}


class TestSitemapVariantes(unittest.TestCase):
    """beta.illith.com (2026-10-01) : sitemap en http://, limite de 40 pages atteinte avant la phase « sitemap »."""

    def test_sitemap_http_non_visite(self):
        pages = {"https://ex.fr/": page_ok("https://ex.fr/"), "https://ex.fr/a": page_ok("https://ex.fr/a", og_image=False)}
        sm = ["http://ex.fr/a", "http://ex.fr/"]
        ctx = {"meta": {}, "sitemap_sondes": {"http://ex.fr/": {"statut": 301, "vers": "https://ex.fr/"}}}
        issues = crawl_site.build_issues(pages, {"https://ex.fr/a": {"https://ex.fr/"}}, set(sm), sm, [],
                                         crawl_site.RobotsTxt("User-agent: *\nAllow: /\n"), {}, Counter(), {},
                                         "ex.fr", "https", {}, ctx)
        self.assertNotIn("not_in_sitemap", issues)
        self.assertEqual(issues["sitemap_redirect"]["examples"], [
            {"url": "http://ex.fr/", "vers": "https://ex.fr/", "statut": 301},
            {"url": "http://ex.fr/a", "vers": "https://ex.fr/a", "statut": "non vérifié (limite de crawl atteinte)"}])
        self.assertEqual(issues["og_image_absent"]["examples"], ["https://ex.fr/a"])
        self.assertNotIn("og_title_absent", issues)
        self.assertNotIn("og_missing", issues)

    def test_url_de_sitemap_sondee_quand_la_limite_est_atteinte(self):
        routes = {"/": (200, HTML, page("<p>Accueil</p>")),
                  "/sitemap.xml": (200, {"Content-Type": "application/xml"},
                                   '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>@@BASE@@/r/a</loc></url></urlset>'),
                  "/r/a": (301, {"Location": "/a"}, ""), "/a": (200, HTML, page("<p>A</p>"))}
        with SiteLocal(routes) as site, tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, str(CRAWL), site.url, "--out", d, "--delay", "0", "--max-pages", "1",
                                "--timeout", "5", "--liens-externes", "0", "--ressources", "0"], capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            ex = json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8"))["sitemap_redirect"]["examples"]
            self.assertEqual(ex, [{"url": site.base + "/r/a", "vers": site.base + "/a", "statut": 301}])


class FetchFactice:
    """fetch de remplacement : enregistre les appels ; chaque URL http:// / www répond 301 vers son équivalent https://ex.fr."""

    def __init__(self, statut=301):
        self.appels, self.statut = [], statut

    def __call__(self, url, timeout=20, method="GET", max_hops=10, **kw):
        self.appels.append({"url": url, "timeout": timeout, "method": method, "max_hops": max_hops})
        cible = "https://ex.fr" + url.split("ex.fr", 1)[-1] if "ex.fr" in url else url
        if self.statut in (301, 302):
            return {"url": url, "final_url": cible, "status": -1, "chain": [{"url": url, "status": self.statut}]}
        return {"url": url, "final_url": url, "status": self.statut, "chain": []}


def issues_sitemap(sm, pages, robots="User-agent: *\nAllow: /\n", fetch_fn=None, **kw):
    """sondes (fetch factice) puis build_issues, comme `crawl` pour un site https://ex.fr."""
    rb = crawl_site.RobotsTxt(robots)
    sondes = crawl_site.sonder_sitemap(set(sm), pages, "ex.fr", "https", rb, fetch_fn or FetchFactice(), **kw)
    ctx = {"meta": {}, "sitemap_sondes": sondes}
    return crawl_site.build_issues(pages, {u: {"https://ex.fr/"} for u in pages}, set(sm), sm, [], rb, {}, Counter(), {},
                                   "ex.fr", "https", {}, ctx), sondes


class TestSondesSitemap(unittest.TestCase):
    """Revue T6 (M1-M6) : comptage sans réseau, sondes bornées, hôtes tiers jamais contactés."""

    def pages(self, *chemins):
        return {"https://ex.fr" + c: page_ok("https://ex.fr" + c) for c in ("/",) + chemins}

    def test_sitemap_http_vers_https_compte_sans_reseau_et_sonde_bornee(self):
        pages = self.pages("/a", "/b")
        sm = ["http://ex.fr/", "http://ex.fr/a", "http://ex.fr/b"] + ["http://ex.fr/n%02d" % i for i in range(60)]
        f = FetchFactice()
        issues, sondes = issues_sitemap(sm, pages, fetch_fn=f)
        self.assertEqual(issues["sitemap_redirect"]["count"], len(sm))   # toutes les variantes, pas seulement les sondées
        self.assertNotIn("not_in_sitemap", issues)
        self.assertLessEqual(len(f.appels), 5)
        self.assertEqual(len(sondes), len(f.appels))
        self.assertTrue(all(a["method"] == "HEAD" and a["max_hops"] == 1 and a["timeout"] == 20 for a in f.appels))
        # les URL sondées (priorité à celles sans équivalent crawlé) portent le code observé et passent en tête
        ex = issues["sitemap_redirect"]["examples"]
        self.assertEqual([e["statut"] for e in ex[:len(sondes)]], [301] * len(sondes))
        self.assertTrue(all(e["url"] not in pages and "n0" in e["url"] for e in ex[:len(sondes)]))

    def test_une_sonde_a_200_ne_dit_pas_redirige(self):
        pages = self.pages("/a")
        issues, _ = issues_sitemap(["http://ex.fr/", "http://ex.fr/a"], pages, fetch_fn=FetchFactice(statut=200))
        self.assertNotIn("sitemap_redirect", issues)
        self.assertEqual(sorted(e["statut"] for e in issues["sitemap_sans_redirection"]["examples"]), [200, 200])
        self.assertTrue(all("vers" not in e for e in issues["sitemap_sans_redirection"]["examples"]))

    def test_page_absente_du_sitemap_reste_signalee(self):
        pages = self.pages("/a", "/b")
        issues, _ = issues_sitemap(["http://ex.fr/", "http://www.ex.fr/a"], pages)
        self.assertEqual(issues["not_in_sitemap"]["examples"], ["https://ex.fr/b"])

    def test_variante_www_equivalente(self):
        pages = self.pages("/a")
        issues, _ = issues_sitemap(["https://www.ex.fr/", "https://www.ex.fr/a"], pages, max_sondes=0)
        self.assertNotIn("not_in_sitemap", issues)
        self.assertEqual(issues["sitemap_redirect"]["count"], 2)

    def test_hote_tiers_jamais_sonde_ni_compte(self):
        pages = self.pages("/a")
        sm = ["https://ex.fr/", "https://ex.fr/a", "http://localhost:4321/x", "https://staging.autre.com/a"]
        f = FetchFactice()
        issues, sondes = issues_sitemap(sm, pages, fetch_fn=f)
        self.assertEqual(f.appels, [])
        self.assertEqual(sondes, {})
        self.assertNotIn("sitemap_redirect", issues)
        self.assertNotIn("sitemap_sans_redirection", issues)

    def test_robots_respecte_par_les_sondes(self):
        pages = self.pages()
        sm = ["http://ex.fr/prive/a", "http://ex.fr/prive/b", "http://ex.fr/ok"]
        f = FetchFactice()
        issues, sondes = issues_sitemap(sm, pages, robots="User-agent: *\nDisallow: /prive/\n", fetch_fn=f)
        self.assertEqual([a["url"] for a in f.appels], ["http://ex.fr/ok"])
        self.assertEqual(issues["sitemap_redirect"]["count"], 3)   # comptage sans réseau : robots ne l'affecte pas
        f2 = FetchFactice()
        issues_sitemap(sm, pages, robots="User-agent: *\nDisallow: /prive/\n", fetch_fn=f2, ignore_robots=True, par_groupe=5)
        self.assertEqual(len(f2.appels), 3)

    def test_bornes_par_groupe_echecs_et_budget(self):
        pages = self.pages()
        sm = ["http://ex.fr/%02d" % i for i in range(30)] + ["http://www.ex.fr/%02d" % i for i in range(30)]
        f = FetchFactice()
        crawl_site.sonder_sitemap(set(sm), pages, "ex.fr", "https", crawl_site.RobotsTxt(""), f, max_sondes=20)
        self.assertEqual(len(f.appels), 4)   # 2 par couple (schéma, hôte) : http://ex.fr et http://www.ex.fr
        panne = FetchFactice(statut=0)
        crawl_site.sonder_sitemap(set(sm), pages, "ex.fr", "https", crawl_site.RobotsTxt(""), panne, par_groupe=50, max_sondes=20)
        self.assertEqual(len(panne.appels), 3)   # arrêt après 3 échecs de suite
        nul = FetchFactice()
        crawl_site.sonder_sitemap(set(sm), pages, "ex.fr", "https", crawl_site.RobotsTxt(""), nul, budget_s=-1)
        self.assertEqual(nul.appels, [])

    def test_og_title_absent_seul(self):
        p = page_ok("https://ex.fr/")
        p["og_title"] = False
        issues = crawl_site.build_issues({"https://ex.fr/": p}, {}, set(), [], [], crawl_site.RobotsTxt(""), {}, Counter(), {},
                                         "ex.fr", "https", {}, {"meta": {}})
        self.assertEqual(issues["og_title_absent"]["examples"], ["https://ex.fr/"])
        self.assertNotIn("og_image_absent", issues)


if __name__ == "__main__":
    unittest.main()
