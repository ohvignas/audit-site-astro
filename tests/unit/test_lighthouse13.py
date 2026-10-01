import pathlib
import sys
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"))
import pagespeed  # noqa: E402

LHR13 = {
    "lighthouseVersion": "13.5.0", "configSettings": {"formFactor": "mobile"}, "finalDisplayedUrl": "https://ex.fr/",
    "categories": {
        "performance": {"score": 0.62, "auditRefs": [{"id": "document-latency-insight", "weight": 0},
                                                     {"id": "cls-culprits-insight", "weight": 0},
                                                     {"id": "render-blocking-insight", "weight": 0}]},
        "accessibility": {"score": 0.9, "auditRefs": [{"id": "color-contrast", "weight": 7}]}},
    "audits": {
        "document-latency-insight": {
            "score": 0, "scoreDisplayMode": "metricSavings", "title": "Latence de la requête de document",
            "metricSavings": {"FCP": 120, "LCP": 120},
            "details": {"type": "checklist", "items": {
                "noRedirects": {"label": "Pas de redirection", "value": True},
                "serverResponseIsFast": {"label": "Le serveur répond rapidement", "value": True},
                "usesCompression": {"label": "Applique la compression", "value": False}}}},
        "cls-culprits-insight": {
            "score": 0, "scoreDisplayMode": "metricSavings", "title": "Causes des décalages de mise en page",
            "details": {"type": "list", "items": [{"type": "table", "items": [
                {"node": {"type": "node", "snippet": '<img src="/hero.jpg">', "selector": "main > img"}, "score": 0.21}]}]}},
        "render-blocking-insight": {
            "score": 0, "scoreDisplayMode": "metricSavings", "title": "Requêtes bloquant l'affichage",
            "metricSavings": {"FCP": 300}, "details": {"type": "table", "items": [{"url": "https://ex.fr/bloquant.js", "wastedMs": 300}]}},
        "dom-size-insight": {"score": 1, "scoreDisplayMode": "numeric", "numericValue": 1812, "title": "Taille du DOM"},
        "color-contrast": {"score": 0, "scoreDisplayMode": "binary",
                           "title": "Les couleurs d'arrière-plan et de premier plan n'ont pas un rapport de contraste suffisant."}}}


class TestLighthouse13(unittest.TestCase):
    def setUp(self):
        self.s = pagespeed.summarize_lhr(LHR13)
        self.opps = {o["id"]: o for o in self.s["opportunites"]}

    def test_fautifs_du_cls(self):
        self.assertEqual(self.s["elements_cls"], [{"snippet": '<img src="/hero.jpg">', "selector": "main > img"}])

    def test_compression_absente_visible(self):
        self.assertEqual(self.opps["document-latency-insight"]["titre"],
                         "Latence de la requête de document (compression du document absente)")

    def test_gain_issu_des_gains_par_metrique(self):
        # sans gain_ms non nul, signaux.py écarterait l'opportunité (P16 perdu)
        self.assertEqual(self.opps["document-latency-insight"]["gain_ms"], 120)
        self.assertEqual(self.opps["render-blocking-insight"]["gain_ms"], 300)

    def test_insight_bloquant(self):
        self.assertEqual(self.opps["render-blocking-insight"]["exemples"], ["https://ex.fr/bloquant.js"])

    def test_divers_et_echecs(self):
        self.assertEqual(self.s["divers"]["noeuds_dom"], 1812)
        self.assertNotIn("TTFB labo", self.s["metriques"])
        self.assertEqual(self.s["echecs_autres_categories"]["accessibility"],
                         ["Les couleurs d'arrière-plan et de premier plan n'ont pas un rapport de contraste suffisant. [color-contrast]"])

    def test_alias_vers_l_insight(self):
        self.assertIs(pagespeed.audit_lh(LHR13["audits"], "layout-shifts"), LHR13["audits"]["cls-culprits-insight"])
        self.assertEqual(pagespeed.audit_lh({}, "layout-shifts"), {})


LHR12 = {
    "lighthouseVersion": "12.6.0", "configSettings": {"formFactor": "desktop"}, "finalDisplayedUrl": "https://ex.fr/",
    "categories": {"performance": {"score": 0.8, "auditRefs": [{"id": "uses-text-compression", "weight": 0}]}},
    "audits": {
        "server-response-time": {"score": 1, "scoreDisplayMode": "metricSavings", "numericValue": 240, "title": "TTFB"},
        "uses-text-compression": {"score": 0, "scoreDisplayMode": "metricSavings", "title": "Activez la compression de texte",
                                  "details": {"type": "opportunity", "overallSavingsMs": 450, "overallSavingsBytes": 90000,
                                              "items": [{"url": "https://ex.fr/"}]}},
        "layout-shifts": {"score": 0, "scoreDisplayMode": "metricSavings", "title": "Décalages",
                          "details": {"type": "table", "items": [
                              {"node": {"type": "node", "snippet": "<div>", "selector": "body > div"}, "score": 0.1}]}},
        "dom-size": {"score": 1, "scoreDisplayMode": "numeric", "numericValue": 950, "title": "DOM"}}}


class TestLighthouse12InchangeEnLecture(unittest.TestCase):
    def test_ancien_format_toujours_lu(self):
        s = pagespeed.summarize_lhr(LHR12)
        self.assertEqual(s["metriques"]["TTFB labo"]["valeur"], 240)
        self.assertEqual(s["elements_cls"], [{"snippet": "<div>", "selector": "body > div"}])
        self.assertEqual(s["divers"]["noeuds_dom"], 950)
        o = s["opportunites"][0]
        self.assertEqual((o["id"], o["titre"], o["gain_ms"], o["exemples"]),
                         ("uses-text-compression", "Activez la compression de texte", 450, ["https://ex.fr/"]))


if __name__ == "__main__":
    unittest.main()
