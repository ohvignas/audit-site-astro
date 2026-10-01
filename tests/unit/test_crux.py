import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
import crux  # noqa: E402
import fiches  # noqa: E402

RECORD = {"key": {"origin": "https://ex.fr", "formFactor": "PHONE"}, "metrics": {
    "largest_contentful_paint": {"percentiles": {"p75": 4210}}, "interaction_to_next_paint": {"percentiles": {"p75": 180}},
    "cumulative_layout_shift": {"percentiles": {"p75": "0.12"}}, "experimental_time_to_first_byte": {"percentiles": {"p75": 950}}}}
HISTO = {"key": {"origin": "https://ex.fr"}, "metrics": {
    "largest_contentful_paint": {"percentilesTimeseries": {"p75s": [None, 2400, 2600, 3100]}},
    "cumulative_layout_shift": {"percentilesTimeseries": {"p75s": ["0.10", "0.10"]}}}}
CLE = "CLE-SECRETE"


def _lire_tout(dossier):
    return "".join(p.read_text(encoding="utf-8") for p in pathlib.Path(dossier).iterdir())


class TestCrux(unittest.TestCase):
    def test_verdicts(self):
        self.assertEqual(crux.analyser_record(RECORD), {
            "LCP": {"p75": 4210, "verdict": "mauvais"}, "INP": {"p75": 180, "verdict": "bon"},
            "CLS": {"p75": 0.12, "verdict": "à améliorer"}, "TTFB": {"p75": 950, "verdict": "à améliorer"}})

    def test_tendances(self):
        self.assertEqual(crux.tendances(HISTO), {"LCP": 29, "CLS": 0})

    def test_issues_et_pas_de_cle_dans_les_sorties(self):
        reponses = {("record", "origin"): (200, {"record": RECORD}), ("histoire", "origin"): (200, {"record": HISTO}),
                    ("record", "url"): (404, {"error": {"code": 404}}), ("histoire", "url"): (404, {"error": {"code": 404}})}

        def transport(url, corps):
            assert "CLE-SECRETE" in url
            return reponses[("histoire" if "History" in url else "record", "url" if "url" in corps else "origin")]
        with tempfile.TemporaryDirectory() as d:
            crux.collecter("https://ex.fr", ["https://ex.fr/page"], "CLE-SECRETE", d, transport=transport)
            issues = json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8"))
            tout = "".join(p.read_text(encoding="utf-8") for p in pathlib.Path(d).iterdir())
        self.assertEqual({k: v["severity"] for k, v in issues.items()},
                         {"terrain_lcp": "haute", "terrain_cls": "moyenne", "terrain_ttfb": "moyenne", "terrain_degradation": "moyenne"})
        self.assertNotIn("CLE-SECRETE", tout)
        self.assertIn("⏭️ https://ex.fr/page : pas assez de trafic", tout)

    def test_sans_cle(self):
        with tempfile.TemporaryDirectory() as d:
            crux.collecter("https://ex.fr", [], None, d)
            self.assertEqual(json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8")), {})
            self.assertIn("⏭️ pas de clé CrUX", pathlib.Path(d, "crux.md").read_text(encoding="utf-8"))

    def test_chaque_cle_a_une_fiche(self):
        f = fiches.charger_fiches(SCRIPTS.parent / "references/fiches")
        cles = ["terrain_lcp", "terrain_inp", "terrain_cls", "terrain_fcp", "terrain_ttfb", "terrain_degradation"]
        self.assertEqual(fiches.associer([{"source": "terrain", "cle": c} for c in cles], f)[1], [])


class TestFormeDesRequetes(unittest.TestCase):
    """Formes vérifiées sur developer.chrome.com/docs/crux/api et /history-api."""

    def test_points_d_entree_et_corps(self):
        vus = []

        def transport(url, corps):
            vus.append((url, corps))
            return 200, {"record": RECORD}
        self.assertEqual(crux.interroger({"origin": "https://ex.fr", "formFactor": "PHONE"}, CLE, transport=transport),
                         (200, RECORD))
        crux.interroger({"origin": "https://ex.fr", "formFactor": "PHONE"}, CLE, historique=True, transport=transport)
        self.assertEqual(vus[0][0], "https://chromeuxreport.googleapis.com/v1/records:queryRecord?key=" + CLE)
        self.assertEqual(vus[1][0], "https://chromeuxreport.googleapis.com/v1/records:queryHistoryRecord?key=" + CLE)
        self.assertEqual(vus[0][1], {"origin": "https://ex.fr", "formFactor": "PHONE"})

    def test_cles_de_metriques_cwv(self):
        self.assertEqual([m[0] for m in crux.METRIQUES], [
            "largest_contentful_paint", "interaction_to_next_paint", "cumulative_layout_shift", "first_contentful_paint",
            "experimental_time_to_first_byte"])

    def test_fcp_seuils_et_cls_chaine(self):
        rec = {"metrics": {"first_contentful_paint": {"percentiles": {"p75": 3200}},
                           "cumulative_layout_shift": {"percentiles": {"p75": "0.30"}}}}
        self.assertEqual(crux.analyser_record(rec), {"FCP": {"p75": 3200, "verdict": "mauvais"},
                                                     "CLS": {"p75": 0.3, "verdict": "mauvais"}})

    def test_valeurs_illisibles_ignorees(self):
        rec = {"metrics": {"largest_contentful_paint": {"percentiles": {"p75": "n/a"}}}}
        self.assertEqual(crux.analyser_record(rec), {})
        self.assertEqual(crux.analyser_record({}), {})
        self.assertEqual(crux.tendances({"metrics": {"largest_contentful_paint": {"percentilesTimeseries": {
            "p75s": ["NaN", None, 3000]}}}}), {})

    def test_degradation_seulement_lcp_inp_cls_plus_de_10_pct(self):
        base = {"portee": "origine", "cible": "https://ex.fr", "metriques": {}}
        self.assertEqual(crux.construire_issues([dict(base, tendances={"TTFB": 80, "FCP": 50, "LCP": 10, "CLS": -30})]), {})
        res = crux.construire_issues([dict(base, tendances={"INP": 11})])
        self.assertEqual(res["terrain_degradation"]["severity"], "moyenne")

    def test_historique_absent_pas_de_degradation(self):
        def transport(url, corps):
            return (404, {}) if "History" in url else (200, {"record": RECORD})
        with tempfile.TemporaryDirectory() as d:
            crux.collecter("https://ex.fr", [], CLE, d, transport=transport)
            issues = json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8"))
        self.assertNotIn("terrain_degradation", issues)


class TestStatutsHttp(unittest.TestCase):
    def _collecter(self, statut, corps=None, urls=()):
        def transport(url, c):
            return statut, corps or {}
        d = tempfile.mkdtemp()
        crux.collecter("https://ex.fr", list(urls), CLE, d, transport=transport)
        return d, pathlib.Path(d, "crux.md").read_text(encoding="utf-8"), json.loads(
            pathlib.Path(d, "issues.json").read_text(encoding="utf-8"))

    def test_404_est_une_info_pas_une_erreur(self):
        _, md, issues = self._collecter(404, {"error": {"code": 404, "status": "NOT_FOUND"}})
        self.assertIn("⏭️ https://ex.fr : pas assez de trafic", md)
        self.assertNotIn("❌", md)
        self.assertEqual(issues, {})

    def test_403_cle_refusee_jamais_erreur_et_arret(self):
        _, md, issues = self._collecter(403, {"error": {"code": 403, "status": "PERMISSION_DENIED",
                                                         "message": "API key " + CLE + " blocked"}}, urls=["https://ex.fr/a"])
        self.assertIn("⏭️", md)
        self.assertIn("PERMISSION_DENIED", md)
        self.assertNotIn("❌", md)
        self.assertNotIn(CLE, md)  # le message libre de Google n'est jamais recopié
        self.assertNotIn("https://ex.fr/a", md)  # arrêt après un refus de clé : pas d'insistance
        self.assertEqual(issues, {})

    def test_reseau_indisponible(self):
        _, md, _ = self._collecter(0)
        self.assertIn("⏭️", md)
        self.assertNotIn("❌", md)

    def test_urls_hors_origine_ignorees_et_requetes_sans_secret(self):
        vus = []

        def transport(url, c):
            vus.append(c)
            return 404, {}
        with tempfile.TemporaryDirectory() as d:
            crux.collecter("https://ex.fr/", ["https://ex.fr/p?token=abc#x", "https://autre.fr/q", "https://ex.fr/p?token=abc"],
                           CLE, d, transport=transport)
            tout = _lire_tout(d)
        self.assertEqual([c.get("url") or c.get("origin") for c in vus], ["https://ex.fr", "https://ex.fr/p"])
        self.assertNotIn("token", tout)
        self.assertNotIn("autre.fr", tout)


class TestCleJamaisEcrite(unittest.TestCase):
    def test_masquer_cle(self):
        t = crux.masquer_cle("POST https://x/v1/records:queryRecord?key=" + CLE + "&a=1 : refusé (" + CLE + ")", CLE)
        self.assertNotIn(CLE, t)
        self.assertIn("key=***", t)
        self.assertNotIn("AIzaSyABCDEF", crux.masquer_cle("?foo=1&key=AIzaSyABCDEF123", None))

    def test_transport_http_erreur_http_sans_url_ni_cle(self):
        url = crux.API + "queryRecord?key=" + CLE
        err = urllib.error.HTTPError(url, 403, "Forbidden", {}, io.BytesIO(json.dumps(
            {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": url}}).encode()))
        with mock.patch.object(crux.urllib.request, "urlopen", side_effect=err):
            statut, donnees = crux.transport_http(url, {"origin": "https://ex.fr"})
        self.assertEqual(statut, 403)
        self.assertNotIn(CLE, json.dumps(donnees))

    def test_transport_http_exception_reseau(self):
        url = crux.API + "queryRecord?key=" + CLE
        with mock.patch.object(crux.urllib.request, "urlopen", side_effect=urllib.error.URLError("boom " + url)):
            self.assertEqual(crux.transport_http(url, {"origin": "https://ex.fr"}), (0, {}))

    def test_transport_http_succes(self):
        class Rep(io.BytesIO):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        with mock.patch.object(crux.urllib.request, "urlopen", return_value=Rep(b'{"record": {"a": 1}}')) as m:
            self.assertEqual(crux.transport_http(crux.API + "queryRecord?key=" + CLE, {"origin": "https://ex.fr"}),
                             (200, {"record": {"a": 1}}))
        self.assertLessEqual(m.call_args.kwargs.get("timeout", 99), 8)

    def test_main_lit_l_environnement_et_ne_montre_pas_la_cle(self):
        def transport(url, corps):
            return (200, {"record": RECORD}) if "Record" in url and "History" not in url else (200, {"record": HISTO})
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as e:
            urls = pathlib.Path(e, "urls.txt")
            urls.write_text("https://ex.fr/a\nnon\n", encoding="utf-8")
            sortie, erreur = io.StringIO(), io.StringIO()
            env = {"PSI_API_KEY": CLE}
            with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(crux, "transport_http", transport), \
                    contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur), \
                    mock.patch.object(sys, "argv", ["crux.py", "--out", d, "--origine", "https://ex.fr", "--urls-file", str(urls)]):
                os.environ.pop("CRUX_API_KEY", None)
                crux.main()
            tout = _lire_tout(d) + sortie.getvalue() + erreur.getvalue()
            self.assertIn("terrain_lcp", tout)
        self.assertNotIn(CLE, tout)

    def test_crux_api_key_prioritaire_sur_psi(self):
        with mock.patch.dict(os.environ, {"CRUX_API_KEY": "A", "PSI_API_KEY": "B"}):
            self.assertEqual(crux.cle_depuis_environnement(), "A")
        with mock.patch.dict(os.environ, {"PSI_API_KEY": "B"}):
            os.environ.pop("CRUX_API_KEY", None)
            self.assertEqual(crux.cle_depuis_environnement(), "B")
        with mock.patch.dict(os.environ, {"CRUX_API_KEY": "  "}):
            os.environ.pop("PSI_API_KEY", None)
            self.assertIsNone(crux.cle_depuis_environnement())

    def test_sans_cle_ligne_exacte_et_code_zero(self):
        with tempfile.TemporaryDirectory() as d:
            sortie = io.StringIO()
            with mock.patch.dict(os.environ, {}), contextlib.redirect_stdout(sortie), \
                    mock.patch.object(sys, "argv", ["crux.py", "--out", d, "--origine", "https://ex.fr"]):
                os.environ.pop("CRUX_API_KEY", None)
                os.environ.pop("PSI_API_KEY", None)
                crux.main()
            md = pathlib.Path(d, "crux.md").read_text(encoding="utf-8")
        self.assertIn("- ⏭️ pas de clé CrUX (CRUX_API_KEY) : données terrain non lues", md)
        self.assertIn("⏭️ pas de clé CrUX", sortie.getvalue())


if __name__ == "__main__":
    unittest.main()
