import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ICI = pathlib.Path(__file__).resolve().parent
RACINE = ICI.parents[1]
sys.path.insert(0, str(ICI))
from site_local import HTML, SiteLocal  # noqa: E402

SCRIPT = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts/http_checks.sh"
JS = {"Content-Type": "text/javascript"}

# Page d'accueil Astro typique : les JS hashés n'apparaissent QUE dans les attributs de l'îlot (component-url / renderer-url)
ACCUEIL = ("<html lang='fr'><head><title>Accueil</title></head><body>"
           '<astro-island uid="1" component-url="/_astro/Chat.abc123.js" renderer-url="/_astro/client.def456.js"></astro-island>'
           '<a href="/formations/a">A</a> <a href="/formations/b">B</a> <a href="/blog/x">X</a></body></html>')


def lancer(routes, prefixes, pages_json=None):
    with SiteLocal(routes, prefixes) as site, tempfile.TemporaryDirectory() as d:
        args = ["bash", str(SCRIPT), site.url, d] + ([pages_json(site.base, d)] if pages_json else [])
        env = dict(os.environ)
        env.pop("AUDIT_INSECURE_TLS", None)
        subprocess.run(args, capture_output=True, text=True, timeout=240, env=env)
        return pathlib.Path(d, "http-checks.md").read_text(encoding="utf-8")


class TestHttpChecksAstro(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # jumeau « cassé » : /_astro/ en no-cache (H06), toute URL sous /formations/ répond 200 (S35b)
        cls.casse = lancer({"/": (200, HTML, ACCUEIL)},
                           {"/_astro/": (200, dict(JS, **{"Cache-Control": "no-cache"}), "console.log(1)"),
                            "/formations/": (200, HTML, "<html><body>Formation</body></html>")})
        # jumeau « propre » : /_astro/ immuable, seules les formations existantes répondent 200
        cls.propre = lancer({"/": (200, HTML, ACCUEIL), "/formations/a": (200, HTML, "<html></html>"),
                             "/formations/b": (200, HTML, "<html></html>")},
                            {"/_astro/": (200, dict(JS, **{"Cache-Control": "public, max-age=31536000, immutable"}), "x")})

    def test_assets_des_ilots_controles(self):  # H06
        self.assertIn("/_astro/Chat.abc123.js", self.casse)
        self.assertIn("asset hashé Astro", self.casse)
        self.assertIn("/_astro/Chat.abc123.js", self.propre)
        self.assertNotIn("asset hashé Astro", self.propre)

    def test_soft_404_sous_route_dynamique(self):  # S35b
        self.assertRegex(self.casse, r"soft 404.*/formations/")
        self.assertNotIn("soft 404 sous /blog/", self.casse, "un seul lien /blog/ : pas une route dynamique")
        self.assertNotIn("soft 404 sous", self.propre)

    def test_segments_lus_dans_le_crawl(self):
        def pages(base, d):
            f = pathlib.Path(d, "pages.json")
            f.write_text(json.dumps({"pages": [{"url": base + u, "final_status": 200, "redirect_hops": 0}
                                               for u in ("/", "/cours/x", "/cours/y")]}), encoding="utf-8")
            return str(f)
        md = lancer({"/": (200, HTML, "<html><body>vide</body></html>")},
                    {"/cours/": (200, HTML, "<html><body>Cours</body></html>")}, pages)
        self.assertIn("soft 404 sous /cours/", md)


if __name__ == "__main__":
    unittest.main()
