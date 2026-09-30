import pathlib
import sys
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"))
import crawl_site  # noqa: E402
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


class TestAssetsBloques(unittest.TestCase):  # revue finale M7
    def test_motifs_css_js(self):
        for motif in ("/*.css$", "/*.js", "/app.mjs", "/_astro/", "/_next/static/", "/wp-content/themes/", "/wp-includes/"):
            self.assertTrue(crawl_site.ASSETS_RX.search(motif), motif)

    def test_json_n_est_pas_du_js(self):
        for motif in ("/*.json$", "/api/*.json", "/data.jsonld"):
            self.assertIsNone(crawl_site.ASSETS_RX.search(motif), motif)


def _page(url, status=200, html="", error=None):
    res = {"chain": [], "status": status, "final_url": url, "error": error, "ttfb": 0.1, "time": 0.1,
           "raw_bytes": len(html), "body": html.encode("utf-8"), "headers": {"content-type": "text/html"} if html else {}}
    return crawl_site.analyze_page(url, res)[0]


class TestCiblesDeCanonical(unittest.TestCase):  # revue finale M2
    def issues(self, statut_cible):
        u, c = "https://ex.fr/a", "https://ex.fr/b"
        p = _page(u, html="<html><head><link rel='canonical' href='" + c + "'></head><body></body></html>")
        p["depth"] = 0
        cible = _page(c, status=statut_cible, error="timeout" if statut_cible <= 0 else None)
        from collections import Counter
        return crawl_site.build_issues({u: p}, {}, set(), [], [], RobotsTxt(""), {}, Counter(), {}, "ex.fr", "https",
                                       {c: cible})

    def test_cible_injoignable_n_est_pas_une_erreur_haute(self):
        it = self.issues(0)
        self.assertNotIn("canonical_bad_target", it)
        self.assertEqual(it["canonical_target_unreachable"]["severity"], "basse")

    def test_cible_404_reste_haute(self):
        it = self.issues(404)
        self.assertEqual(it["canonical_bad_target"]["severity"], "haute")
        self.assertNotIn("canonical_target_unreachable", it)


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

    def test_champs_sans_libelle(self):
        p = self.parse('<input type="email" placeholder="Votre email">'
                       '<input id="n"><label for="n">Nom</label>'
                       '<label>Ville <input name="v"></label>'
                       '<select title="Pays"></select><textarea aria-labelledby="t"></textarea>'
                       '<input type="hidden"><input type="submit"><button>OK</button><textarea></textarea>')
        self.assertEqual(len(p.champs_sans_libelle()), 2)

    def test_champs_masques_et_pieges_ignores(self):  # revue finale I2
        p = self.parse('<form><label for="e">Email</label><input id="e" type="email">'
                       '<input name="_gotcha" style="display: none">'
                       '<input name="piege" tabindex="-1" autocomplete="off">'
                       '<div hidden><input name="bot-field"><div><span></span></div><input name="bot-2"></div>'
                       '<p style="visibility:hidden"><input name="v"></p>'
                       '<div aria-hidden="true"><input name="a"></div><input name="h" hidden>'
                       '<input name="ah" aria-hidden="true"><input name="d" disabled>'
                       '<template><input placeholder="modèle"></template><noscript><input name="n"></noscript>'
                       '</form>')
        self.assertEqual(p.champs_sans_libelle(), [])

    def test_champ_visible_apres_un_bloc_masque_reste_signale(self):
        p = self.parse('<div hidden><div><input name="x"></div></div>'
                       '<footer><input type="email" placeholder="Votre email"></footer>')
        self.assertEqual(len(p.champs_sans_libelle()), 1)


class TestJsonLd(unittest.TestCase):
    def test_graph_et_erreurs(self):
        ok = '{"@context":"https://schema.org","@graph":[{"@type":"Organization","name":"X"},{"@type":["WebSite","Thing"]}]}'
        types, errors, objects = jsonld_types([ok, '{"@type": "Article",}'])
        self.assertIn("Organization", types)
        self.assertIn("WebSite", types)
        self.assertEqual(errors, 1)


if __name__ == "__main__":
    unittest.main()
