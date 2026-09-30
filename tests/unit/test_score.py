import json
import pathlib
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "tests/cobaye"))
import score  # noqa: E402


def audit(dossier, crawl=None, code=None, geo=None, perf=None, textes=None):
    d = pathlib.Path(dossier, "data")
    for sous, contenu, nom in (("crawl", crawl, "issues.json"), ("code", code, "code-scan.json"),
                               ("geo", geo, "geo.json"), ("perf", perf, "pagespeed.json")):
        if contenu is not None:
            (d / sous).mkdir(parents=True, exist_ok=True)
            (d / sous / nom).write_text(json.dumps(contenu), encoding="utf-8")
    for rel, txt in (textes or {}).items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(txt, encoding="utf-8")
    return pathlib.Path(dossier)


class TestMatchers(unittest.TestCase):
    def test_crawl_issue_avec_exemple(self):
        with tempfile.TemporaryDirectory() as t:
            a = audit(t, crawl={"http_4xx": {"examples": [{"url": "https://x/guide-supprime"}]}})
            self.assertTrue(score.detecte({"type": "crawl_issue", "cle": "http_4xx", "contient": "guide-supprime"}, a))
            self.assertFalse(score.detecte({"type": "crawl_issue", "cle": "http_4xx", "contient": "autre"}, a))
            self.assertFalse(score.detecte({"type": "crawl_issue", "cle": "orphan"}, a))

    def test_code_avec_emplacement(self):
        with tempfile.TemporaryDirectory() as t:
            a = audit(t, code={"constats": [{"constat": "1 mutation(s) publique(s) sans vérification d'identité", "ou": ["convex/leads.ts:4 mutation creer"]}]})
            self.assertTrue(score.detecte({"type": "code", "regex": "sans vérification d'identité", "ou_contient": "convex/leads.ts"}, a))
            self.assertFalse(score.detecte({"type": "code", "regex": "sans vérification d'identité", "ou_contient": "autre.ts"}, a))

    def test_geo_texte_lighthouse(self):
        with tempfile.TemporaryDirectory() as t:
            a = audit(t, geo={"signaux": [{"constat": "robots.txt bloque OAI-SearchBot (…)"}]},
                      perf=[{"opportunites": [{"id": "render-blocking-insight", "titre": "Requêtes bloquantes", "exemples": ["https://x/bloquant.js"]}],
                             "echecs_autres_categories": {"accessibility": ["Les couleurs ne sont pas suffisamment contrastées"]}}],
                      textes={"http/http-checks.md": "| Compression HTML | aucune |"})
            self.assertTrue(score.detecte({"type": "geo_signal", "regex": "bloque OAI-SearchBot"}, a))
            self.assertTrue(score.detecte({"type": "texte", "fichier": "http/http-checks.md", "regex": r"Compression HTML \| aucune"}, a))
            self.assertTrue(score.detecte({"type": "lighthouse", "regex": "render-blocking", "exemple_contient": "bloquant.js"}, a))
            self.assertTrue(score.detecte({"type": "lighthouse", "regex": "contrast"}, a))
            self.assertIsNone(score.detecte({"type": "unitaire", "test": "x"}, a))


class TestHosts(unittest.TestCase):
    def test_matchers_independants_de_l_hote(self):
        verite = json.loads((RACINE / "tests/cobaye/verite-terrain.json").read_text(encoding="utf-8"))
        forbidden = ["casse.cobaye.test", "propre.cobaye.test"]
        for defect in verite["defauts"]:
            matcher = defect["matcher"]
            for field in ["regex", "contient", "exemple_contient"]:
                if field in matcher:
                    value = matcher[field]
                    for host in forbidden:
                        self.assertNotIn(host, value, "matcher {0} field {1} contains hardcoded host '{2}'".format(defect["id"], field, host))


class TestScore(unittest.TestCase):
    VERITE = {"defauts": [
        {"id": "S07", "domaine": "seo", "titre": "404", "phase": "base", "matcher": {"type": "crawl_issue", "cle": "http_4xx"}},
        {"id": "S06", "domaine": "seo", "titre": "orpheline", "phase": "base", "matcher": {"type": "crawl_issue", "cle": "orphan"}},
        {"id": "R01", "domaine": "rgpd", "titre": "futur", "phase": 2, "matcher": {"type": "crawl_issue", "cle": "rgpd"}},
    ]}

    def test_rappel_faux_positifs_et_futurs(self):
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            casse = audit(t1, crawl={"http_4xx": {"severity": "haute", "examples": []}})
            propre = audit(t2, crawl={"orphan": {"severity": "moyenne", "examples": []},
                                      "fetch_error": {"severity": "haute", "label": "Pages injoignables", "examples": []}})
            r = score.scorer(self.VERITE, casse, propre, phase=0)
            self.assertEqual(r["global"]["requis"], 2)
            self.assertEqual(r["global"]["detectes"], 1)
            self.assertEqual([d["id"] for d in r["rates"]], ["S06"])
            self.assertEqual([d["id"] for d in r["faux_positifs"]], ["S06"])
            self.assertEqual(len(r["inattendus"]), 1)
            self.assertEqual([d["id"] for d in r["futurs"]], ["R01"])

    def test_verdict_seuils(self):
        r = {"global": {"rappel": 0.5}, "par_domaine": {"seo": {"rappel": 0.5}}, "faux_positifs": [{}], "inattendus": []}
        v = score.verdict(r, {"rappel_min_global": 0.6, "rappel_min_par_domaine": {"seo": 0.4}, "faux_positifs_max": 0, "inattendus_max": 5})
        self.assertEqual(len(v), 2)


if __name__ == "__main__":
    unittest.main()
