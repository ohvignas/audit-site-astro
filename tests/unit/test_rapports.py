import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
import pagespeed  # noqa: E402
import rapport_brut  # noqa: E402


class TestSeveriteOpportunites(unittest.TestCase):
    def test_les_octets_comptent(self):
        self.assertEqual(rapport_brut.severite_opportunite(0, 6600000), "haute")
        self.assertEqual(rapport_brut.severite_opportunite(0, 300000), "moyenne")
        self.assertEqual(rapport_brut.severite_opportunite(1200, 0), "haute")
        self.assertEqual(rapport_brut.severite_opportunite(100, 50000), "basse")

    def test_six_mo_d_images_en_haute(self):  # constaté sur beta.illith.com le 2026-09-30
        with tempfile.TemporaryDirectory() as d:
            perf = pathlib.Path(d, "data/perf")
            perf.mkdir(parents=True)
            (perf / "pagespeed.json").write_text(json.dumps([{
                "url": "https://ex.fr/", "strategie": "mobile", "scores": {}, "metriques": {},
                "opportunites": [{"id": "image-delivery-insight", "titre": "Améliorer la diffusion des images",
                                  "gain_ms": 0, "gain_octets": 6600000, "exemples": []}],
                "echecs_autres_categories": {}}]), encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPTS / "rapport_brut.py"), d], check=True, capture_output=True, timeout=60)
            md = pathlib.Path(d, "RAPPORT-BRUT.md").read_text(encoding="utf-8")
        self.assertIn("### 🟧 Haute", md)
        haute = md.split("### 🟧 Haute", 1)[1].split("\n### ", 1)[0]
        self.assertIn("Améliorer la diffusion des images (gain estimé 6445 Ko", haute)


class TestEchecsLighthouse(unittest.TestCase):
    def test_seuls_les_vrais_echecs_avec_leur_id(self):
        lhr = {"categories": {"accessibility": {"auditRefs": [
                   {"id": "link-in-text-block", "weight": 1}, {"id": "label", "weight": 7},
                   {"id": "color-contrast", "weight": 7}, {"id": "info-x", "weight": 1}, {"id": "manuel", "weight": 0}]}},
               "audits": {
                   "link-in-text-block": {"score": 1, "scoreDisplayMode": "binary",
                                          "title": "Les liens sont identifiables sans se baser sur la couleur."},
                   "label": {"score": 0, "scoreDisplayMode": "binary",
                             "title": "Les éléments de formulaire ne sont pas associés à des libellés"},
                   "color-contrast": {"score": None, "scoreDisplayMode": "notApplicable", "title": "Contraste"},
                   "info-x": {"score": 0.5, "scoreDisplayMode": "informative", "title": "Information"},
                   "manuel": {"score": 0, "scoreDisplayMode": "manual", "title": "Vérification manuelle"}}}
        echecs = pagespeed.summarize_lhr(lhr)["echecs_autres_categories"]
        self.assertEqual(echecs["accessibility"], ["Les éléments de formulaire ne sont pas associés à des libellés [label]"])


if __name__ == "__main__":
    unittest.main()
