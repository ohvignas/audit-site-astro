import json
import pathlib
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"))
import geo_check  # noqa: E402


def p(url, inlinks):
    return {"url": url, "indexable": True, "inlinks": inlinks, "final_status": 200, "redirect_hops": 0}


class TestEchantillonGeo(unittest.TestCase):
    def test_gabarit_d_article_jamais_evince(self):
        home = "https://ex.fr/"
        pages = [p(home, 50)] + [p("https://ex.fr/page-{0}".format(i), 20) for i in range(14)] + \
                [p("https://ex.fr/blog/a", 1), p("https://ex.fr/blog/b", 1)]
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d, "pages.json")
            f.write_text(json.dumps({"pages": pages}), encoding="utf-8")
            echantillon, _ = geo_check.pick_sample(str(f), home, 12)
        self.assertEqual(len(echantillon), 12)
        self.assertEqual(echantillon[0], home)
        self.assertEqual(sum("/blog/" in u for u in echantillon), 1, echantillon)

    def test_pages_isolees_cles_gardees_malgre_beaucoup_de_gabarits(self):  # revue finale M9
        home = "https://ex.fr/"
        familles = ["tag", "categorie", "auteur", "en", "formations", "blog", "cours", "outils", "cas", "guides"]
        pages = [p(home, 50)] + [p("https://ex.fr/{0}/{1}".format(f, i), 5) for f in familles for i in "ab"] + \
                [p("https://ex.fr/contact", 3), p("https://ex.fr/tarifs", 2)]
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d, "pages.json")
            f.write_text(json.dumps({"pages": pages}), encoding="utf-8")
            echantillon, _ = geo_check.pick_sample(str(f), home, 12)
        self.assertEqual(len(echantillon), 12)
        self.assertIn("https://ex.fr/contact", echantillon)
        self.assertIn("https://ex.fr/tarifs", echantillon)


if __name__ == "__main__":
    unittest.main()
