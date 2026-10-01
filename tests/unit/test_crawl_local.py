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


if __name__ == "__main__":
    unittest.main()
