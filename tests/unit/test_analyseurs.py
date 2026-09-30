import pathlib
import sys
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"))
from crawl_site import PageParser, RobotsTxt, jsonld_types  # noqa: E402

ROBOTS = """User-agent: *
Disallow: /admin
Allow: /admin/public

User-agent: GPTBot
Disallow: /

Sitemap: https://ex.fr/sitemap.xml
"""


class TestRobots(unittest.TestCase):
    def setUp(self):
        self.r = RobotsTxt(ROBOTS)

    def test_regle_la_plus_longue_gagne(self):
        self.assertFalse(self.r.allowed("Googlebot", "https://ex.fr/admin/x"))
        self.assertTrue(self.r.allowed("Googlebot", "https://ex.fr/admin/public/y"))

    def test_groupe_dedie(self):
        self.assertFalse(self.r.allowed("GPTBot", "https://ex.fr/"))
        self.assertTrue(self.r.explicit_group("gptbot"))
        self.assertFalse(self.r.explicit_group("ClaudeBot"))

    def test_sitemaps(self):
        self.assertEqual(self.r.sitemaps, ["https://ex.fr/sitemap.xml"])

    def test_jokers_et_dollar(self):
        r = RobotsTxt("User-agent: *\nDisallow: /*?t=\nDisallow: /*.pdf$\n")
        self.assertFalse(r.allowed("Googlebot", "https://ex.fr/page?t=abc"))
        self.assertFalse(r.allowed("Googlebot", "https://ex.fr/doc.pdf"))
        self.assertTrue(r.allowed("Googlebot", "https://ex.fr/doc.pdf?v=2"))


class TestParseur(unittest.TestCase):
    def parse(self, html):
        p = PageParser()
        p.feed(html)
        return p

    def test_mots_dans_main_seulement(self):
        p = self.parse("<nav>un deux trois</nav><main><h1>Titre</h1><p>quatre cinq</p></main>")
        self.assertEqual(p.main_words, 3)
        self.assertEqual(p.words, 6)

    def test_scripts_et_styles_ignores(self):
        p = self.parse("<main><script>var a = 'x y z';</script><style>.a{}</style><p>ok</p></main>")
        self.assertEqual(p.main_words, 1)

    def test_images_alt_absent_vs_vide(self):
        p = self.parse('<img src="a.jpg"><img src="b.jpg" alt="">')
        self.assertIsNone(p.imgs[0]["alt"])
        self.assertEqual(p.imgs[1]["alt"], "")

    def test_listes_dans_main(self):
        p = self.parse("<nav><ul><li>a</li></ul></nav><main><ul><li>b</li></ul><table></table></main>")
        self.assertEqual(p.tags_main["ul"], 1)
        self.assertEqual(p.tags["ul"], 2)
        self.assertEqual(p.tags_main["table"], 1)


class TestJsonLd(unittest.TestCase):
    def test_graph_et_erreurs(self):
        ok = '{"@context":"https://schema.org","@graph":[{"@type":"Organization","name":"X"},{"@type":["WebSite","Thing"]}]}'
        types, errors, objects = jsonld_types([ok, '{"@type": "Article",}'])
        self.assertIn("Organization", types)
        self.assertIn("WebSite", types)
        self.assertEqual(errors, 1)


if __name__ == "__main__":
    unittest.main()
