import contextlib
import http.server
import io
import json
import os
import pathlib
import sys
import tempfile
import threading
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
RECORD_BON = {"metrics": {"largest_contentful_paint": {"percentiles": {"p75": 1500}}}}


def _serie(nom, valeurs):
    return {"metrics": {nom: {"percentilesTimeseries": {"p75s": valeurs}}}}


def _lire_tout(dossier):
    return "".join(p.read_text(encoding="utf-8") for p in pathlib.Path(dossier).iterdir())


def _est_histoire(url):
    return "History" in url


class TestCrux(unittest.TestCase):
    def test_verdicts(self):
        self.assertEqual(crux.analyser_record(RECORD), {
            "LCP": {"p75": 4210, "verdict": "mauvais"}, "INP": {"p75": 180, "verdict": "bon"},
            "CLS": {"p75": 0.12, "verdict": "à améliorer"}, "TTFB": {"p75": 950, "verdict": "à améliorer"}})

    def test_tendances(self):
        # moyenne des 4 dernières périodes valides contre les 4 précédentes (ici 1 contre 1 : 3 points valides seulement)
        self.assertEqual(crux.tendances(HISTO), {"LCP": 19, "CLS": 0})

    def test_issues_et_pas_de_cle_dans_les_sorties(self):
        reponses = {("record", "origin"): (200, {"record": RECORD}), ("histoire", "origin"): (200, {"record": HISTO}),
                    ("record", "url"): (404, {"error": {"code": 404}}), ("histoire", "url"): (404, {"error": {"code": 404}})}

        def transport(url, corps, entetes):
            assert CLE not in url, "la clé ne doit jamais être dans l'adresse"
            assert entetes.get("X-Goog-Api-Key") == CLE
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

    def test_points_d_entree_corps_et_cle_en_entete(self):
        vus = []

        def transport(url, corps, entetes):
            vus.append((url, corps, entetes))
            return 200, {"record": RECORD}
        self.assertEqual(crux.interroger({"origin": "https://ex.fr", "formFactor": "PHONE"}, CLE, transport=transport),
                         (200, RECORD))
        crux.interroger({"origin": "https://ex.fr"}, CLE, historique=True, transport=transport)
        self.assertEqual(vus[0][0], "https://chromeuxreport.googleapis.com/v1/records:queryRecord")
        self.assertEqual(vus[1][0], "https://chromeuxreport.googleapis.com/v1/records:queryHistoryRecord")
        self.assertEqual(vus[0][1], {"origin": "https://ex.fr", "formFactor": "PHONE"})
        for url, _, entetes in vus:
            self.assertNotIn(CLE, url)
            self.assertNotIn("key=", url)
            self.assertEqual(entetes["X-Goog-Api-Key"], CLE)

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
        self.assertEqual(crux.tendances(_serie("largest_contentful_paint", ["NaN", None, 3000])), {})

    def test_historique_absent_pas_de_degradation(self):
        def transport(url, corps, entetes):
            return (404, {}) if "History" in url else (200, {"record": RECORD})
        with tempfile.TemporaryDirectory() as d:
            crux.collecter("https://ex.fr", [], CLE, d, transport=transport)
            issues = json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8"))
        self.assertNotIn("terrain_degradation", issues)


class TestTendance(unittest.TestCase):
    """Dégradation = changement de catégorie vers pire, ou hausse absolue au-delà d'un plancher sans être « bon »."""

    def _deg(self, nom, serie):
        return crux.analyser_historique(_serie(nom, serie)).get(crux._LABELS[nom], {}).get("degradation")

    def test_bon_vers_bon_jamais_signale(self):
        self.assertFalse(self._deg("cumulative_layout_shift", ["0.01"] * 8 + ["0.02"] * 4))  # +100 % mais 0,02
        self.assertFalse(self._deg("largest_contentful_paint", [1000] * 8 + [1150] * 4))     # +15 %
        self.assertFalse(self._deg("interaction_to_next_paint", [100] * 8 + [111] * 4))      # +11 %
        self.assertFalse(self._deg("largest_contentful_paint", [1000] * 8 + [2450] * 4))     # +145 % mais encore bon

    def test_pourcentage_expose_meme_sans_degradation(self):
        self.assertEqual(crux.tendances(_serie("largest_contentful_paint", [1000] * 4 + [1150] * 4)), {"LCP": 15})

    def test_base_nulle_cls(self):
        serie = ["0.00"] * 20 + ["0.30"] * 4
        self.assertTrue(self._deg("cumulative_layout_shift", serie))
        self.assertEqual(crux.tendances(_serie("cumulative_layout_shift", serie)), {})  # pourcentage indéfini : omis

    def test_changement_de_categorie_meme_petit(self):
        self.assertTrue(self._deg("largest_contentful_paint", [2400] * 4 + [2600] * 4))  # +200 ms mais bon -> à améliorer

    def test_plancher_absolu_par_metrique(self):
        # même catégorie (à améliorer) : il faut atteindre le plancher
        self.assertFalse(self._deg("largest_contentful_paint", [3000] * 4 + [3400] * 4))  # +400 < 500
        self.assertTrue(self._deg("largest_contentful_paint", [3000] * 4 + [3600] * 4))   # +600
        self.assertFalse(self._deg("interaction_to_next_paint", [250] * 4 + [330] * 4))   # +80 < 100
        self.assertTrue(self._deg("interaction_to_next_paint", [250] * 4 + [360] * 4))
        self.assertFalse(self._deg("cumulative_layout_shift", ["0.12"] * 4 + ["0.16"] * 4))  # +0,04 < 0,05
        self.assertTrue(self._deg("cumulative_layout_shift", ["0.12"] * 4 + ["0.18"] * 4))
        self.assertFalse(self._deg("first_contentful_paint", [2000] * 4 + [2250] * 4))  # +250 < 300
        self.assertTrue(self._deg("first_contentful_paint", [2000] * 4 + [2350] * 4))
        self.assertFalse(self._deg("experimental_time_to_first_byte", [1000] * 4 + [1250] * 4))
        self.assertTrue(self._deg("experimental_time_to_first_byte", [1000] * 4 + [1350] * 4))

    def test_amelioration_jamais_signalee(self):
        self.assertFalse(self._deg("largest_contentful_paint", [4500] * 4 + [2000] * 4))

    def test_moyenne_de_4_periodes_lisse_un_pic(self):
        self.assertFalse(self._deg("largest_contentful_paint", [2000] * 12 + [2000, 2000, 2000, 3000]))  # moyenne 2250 : bon
        self.assertTrue(self._deg("largest_contentful_paint", [2000] * 12 + [3000] * 4))

    def test_fenetre_4_contre_4(self):
        serie = [9000] * 10 + [2000] * 4 + [2100] * 4  # seules les 8 dernières périodes comptent
        self.assertEqual(crux.tendances(_serie("largest_contentful_paint", serie)), {"LCP": 5})

    def test_valeurs_nulles_finales_ecartees_et_anciennete(self):
        h = crux.analyser_historique(_serie("largest_contentful_paint", [2000] * 4 + [3000] * 4 + [None] * 5))
        self.assertEqual(h["LCP"]["age_semaines"], 5)
        self.assertTrue(h["LCP"]["degradation"])
        h2 = crux.analyser_historique(_serie("largest_contentful_paint", [2000] * 4 + [3000] * 4))
        self.assertEqual(h2["LCP"]["age_semaines"], 0)

    def test_serie_vide_ou_un_seul_point(self):
        self.assertEqual(crux.analyser_historique(_serie("largest_contentful_paint", [None] * 6)), {})
        self.assertEqual(crux.analyser_historique(_serie("largest_contentful_paint", [None, 3000, None])), {})
        self.assertEqual(crux.analyser_historique({}), {})

    def test_construire_issues_utilise_le_drapeau_de_degradation(self):
        base = {"portee": "origine", "cible": "https://ex.fr", "appareil": "tous", "metriques": {}}
        pas = {"LCP": {"avant": 1000, "apres": 1150, "pct": 15, "degradation": False}}
        oui = {"LCP": {"avant": 2000, "apres": 3000, "pct": 50, "degradation": True}}
        self.assertEqual(crux.construire_issues([dict(base, historique=pas)]), {})
        res = crux.construire_issues([dict(base, historique=oui)])
        self.assertEqual(res["terrain_degradation"]["severity"], "moyenne")
        self.assertEqual(res["terrain_degradation"]["examples"][0]["variations"]["LCP"]["apres"], 3000)

    def test_collecter_ecrit_degradation_et_anciennete(self):
        histo = _serie("largest_contentful_paint", [2000] * 4 + [3000] * 4 + [None] * 2)

        def transport(url, corps, entetes):
            return (200, {"record": histo}) if _est_histoire(url) else (200, {"record": RECORD_BON})
        with tempfile.TemporaryDirectory() as d:
            crux.collecter("https://ex.fr", [], CLE, d, transport=transport)
            issues = json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8"))
            md = pathlib.Path(d, "crux.md").read_text(encoding="utf-8")
        self.assertIn("terrain_degradation", issues)
        self.assertIn("2 semaines", md)


class TestSeveriteFcpTtfb(unittest.TestCase):
    """FCP et TTFB ne sont pas des Core Web Vitals : sévérité plafonnée à « moyenne » ; LCP, INP et CLS mauvais restent « haute »."""

    def _issues(self, metriques):
        return crux.construire_issues([{"portee": "origine", "cible": "https://ex.fr", "appareil": "tous",
                                        "metriques": metriques, "historique": {}}])

    def test_fcp_ttfb_mauvais_plafonnes_a_moyenne(self):
        res = self._issues({"FCP": {"p75": 3500, "verdict": "mauvais"}, "TTFB": {"p75": 2500, "verdict": "mauvais"}})
        self.assertEqual({k: v["severity"] for k, v in res.items()}, {"terrain_fcp": "moyenne", "terrain_ttfb": "moyenne"})

    def test_cwv_mauvais_restent_haute_et_a_ameliorer_moyenne(self):
        res = self._issues({"LCP": {"p75": 4500, "verdict": "mauvais"}, "INP": {"p75": 600, "verdict": "mauvais"},
                            "CLS": {"p75": 0.3, "verdict": "mauvais"}})
        self.assertEqual({k: v["severity"] for k, v in res.items()}, {"terrain_lcp": "haute", "terrain_inp": "haute", "terrain_cls": "haute"})
        res = self._issues({"LCP": {"p75": 3000, "verdict": "à améliorer"}})
        self.assertEqual(res["terrain_lcp"]["severity"], "moyenne")


class TestAppareils(unittest.TestCase):
    def _lancer(self, reponses, urls=()):
        vus = []

        def transport(url, corps, entetes):
            vus.append((("histoire" if _est_histoire(url) else "record"), dict(corps)))
            return reponses(url, corps)
        d = tempfile.mkdtemp()
        crux.collecter("https://ex.fr", list(urls), CLE, d, transport=transport)
        return vus, pathlib.Path(d, "crux.md").read_text(encoding="utf-8"), json.loads(
            pathlib.Path(d, "issues.json").read_text(encoding="utf-8")), json.loads(pathlib.Path(d, "crux.json").read_text(encoding="utf-8"))

    def test_tous_appareils_d_abord_puis_mobile_et_ordinateur(self):
        vus, md, _, res = self._lancer(lambda u, c: (200, {"record": RECORD_BON}))
        records = [c for t, c in vus if t == "record"]
        self.assertEqual([c.get("formFactor") for c in records], [None, "PHONE", "DESKTOP"])
        self.assertEqual([r["appareil"] for r in res], ["tous", "mobile", "ordinateur"])
        self.assertIn("(origine, tous appareils)", md)
        self.assertIn("(origine, mobile)", md)
        self.assertIn("(origine, ordinateur)", md)

    def test_site_desktop_seul_pas_de_faux_manque_de_trafic(self):
        def rep(u, c):
            if c.get("formFactor") == "PHONE":
                return 404, {"error": {"code": 404}}
            return 200, {"record": RECORD}
        _, md, issues, _ = self._lancer(rep)
        self.assertNotIn("⏭️ https://ex.fr : pas assez de trafic", md)
        self.assertIn("⏭️ https://ex.fr (mobile) : pas assez de trafic sur cet appareil", md)
        self.assertIn("terrain_lcp", issues)

    def test_agrege_absent_pas_de_ventilation(self):
        vus, md, issues, _ = self._lancer(lambda u, c: (404, {"error": {"code": 404}}))
        self.assertEqual(len(vus), 1)  # l'agrégat porte au moins autant d'échantillons que chaque appareil
        self.assertIn("⏭️ https://ex.fr : pas assez de trafic", md)
        self.assertEqual(issues, {})


class TestAdressesEtArret(unittest.TestCase):
    def _lancer(self, rep, origine="https://ex.fr", urls=()):
        vus = []

        def transport(url, corps, entetes):
            vus.append(dict(corps))
            return rep(corps)
        d = tempfile.mkdtemp()
        crux.collecter(origine, list(urls), CLE, d, transport=transport)
        return vus, pathlib.Path(d, "crux.md").read_text(encoding="utf-8")

    def test_url_exacte_sans_requete_ni_fragment_jamais_tronquee(self):
        longue = "https://ex.fr/blog/" + "comment-ameliorer-le-referencement-" * 8 + "fin"
        self.assertGreater(len(longue), 200)
        vus, md = self._lancer(lambda c: (404, {}), urls=[longue + "?token=abc#x"])
        self.assertEqual([c.get("url") for c in vus if "url" in c], [longue])
        self.assertNotIn("token", md)
        self.assertNotIn("abc", md)

    def test_identifiants_retires_de_l_adresse_envoyee(self):
        vus, _ = self._lancer(lambda c: (404, {}), urls=["https://user:pw@ex.fr/p"])
        self.assertEqual([c.get("url") for c in vus if "url" in c], ["https://ex.fr/p"])

    def test_400_sur_une_page_ne_stoppe_pas_les_suivantes(self):
        def rep(c):
            if c.get("url", "").endswith("/a"):
                return 400, {"error": {"code": 400, "status": "INVALID_ARGUMENT", "details": [{"reason": "BAD_URL"}]}}
            return 404, {}
        vus, md = self._lancer(rep, urls=["https://ex.fr/a", "https://ex.fr/b"])
        self.assertIn("https://ex.fr/b", [c.get("url") for c in vus])
        self.assertIn("⏭️ https://ex.fr/a : données terrain non lues (HTTP 400, INVALID_ARGUMENT)", md)
        self.assertNotIn("interruption", md)

    def test_arret_sur_401_403_429_et_cle_invalide_avec_message_clair(self):
        cas = [(401, {"error": {"status": "UNAUTHENTICATED"}}), (403, {"error": {"status": "PERMISSION_DENIED"}}),
               (429, {"error": {"status": "RESOURCE_EXHAUSTED"}}),
               (400, {"error": {"status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}})]
        for statut, corps in cas:
            with self.subTest(statut=statut):
                vus, md = self._lancer(lambda c: (statut, corps), urls=["https://ex.fr/a", "https://ex.fr/b"])
                self.assertEqual(len(vus), 1)
                self.assertIn("interruption", md)
                self.assertIn("⏭️ https://ex.fr/a : non interrogée (interruption", md)
                self.assertIn("⏭️ https://ex.fr/b : non interrogée (interruption", md)
                self.assertNotIn("❌", md)

    def test_conseil_selon_la_raison(self):
        _, md = self._lancer(lambda c: (400, {"error": {"status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}))
        self.assertIn("clé invalide", md)
        self.assertNotIn("est activée", md)
        _, md = self._lancer(lambda c: (403, {"error": {"status": "PERMISSION_DENIED", "details": [{"reason": "SERVICE_DISABLED"}]}}))
        self.assertIn("n'est pas activée", md)
        _, md = self._lancer(lambda c: (403, {"error": {"status": "PERMISSION_DENIED",
                                                         "details": [{"reason": "API_KEY_SERVICE_BLOCKED"}]}}))
        self.assertIn("restreinte", md)
        _, md = self._lancer(lambda c: (429, {}))
        self.assertIn("réessayer plus tard", md)

    def test_reseau_indisponible(self):
        _, md = self._lancer(lambda c: (0, {}))
        self.assertIn("⏭️", md)
        self.assertNotIn("❌", md)

    def test_404_est_une_info_pas_une_erreur(self):
        _, md = self._lancer(lambda c: (404, {"error": {"code": 404, "status": "NOT_FOUND"}}))
        self.assertIn("⏭️ https://ex.fr : pas assez de trafic", md)
        self.assertNotIn("❌", md)

    def test_urls_hors_origine_ignorees_et_doublons(self):
        vus, md = self._lancer(lambda c: (404, {}), origine="https://EX.fr:443/",
                               urls=["https://ex.fr/p?token=abc#x", "https://autre.fr/q", "https://ex.fr/p?token=abc"])
        self.assertEqual([c.get("url") or c.get("origin") for c in vus], ["https://ex.fr", "https://ex.fr/p"])
        self.assertNotIn("autre.fr", md)

    def test_origine_invalide_aucune_requete(self):
        for mauvaise in ("ex.fr", "", "ftp://ex.fr", "https://"):
            with self.subTest(origine=mauvaise):
                vus, md = self._lancer(lambda c: (200, {}), origine=mauvaise, urls=["https://ex.fr/a"])
                self.assertEqual(vus, [])
                self.assertIn("origine invalide", md)
                self.assertNotIn("⏭️  :", md)

    def test_max_urls_ne_compte_que_les_pages_du_site(self):
        self.assertEqual(crux._limiter("https://ex.fr", ["https://x.fr/1", "https://ex.fr/2", "https://ex.fr/3", "https://ex.fr/4"], 2),
                         ["https://ex.fr/2", "https://ex.fr/3"])


class TestCleJamaisEcrite(unittest.TestCase):
    def test_masquer_cle(self):
        t = crux.masquer_cle("POST https://x/v1/records:queryRecord?key=" + CLE + "&a=1 : refusé (" + CLE + ")", CLE)
        self.assertNotIn(CLE, t)
        self.assertIn("key=***", t)
        self.assertNotIn("AIzaSyABCDEF", crux.masquer_cle("?foo=1&key=AIzaSyABCDEF123", None))

    def test_transport_http_cle_en_entete_jamais_dans_l_adresse(self):
        class Rep(io.BytesIO):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        with mock.patch.object(crux._OPENER, "open", return_value=Rep(b'{"record": {"a": 1}}')) as m:
            self.assertEqual(crux.transport_http(crux.API + "queryRecord", {"origin": "https://ex.fr"}, {"X-Goog-Api-Key": CLE}),
                             (200, {"record": {"a": 1}}))
        req = m.call_args.args[0]
        self.assertNotIn(CLE, req.full_url)
        self.assertNotIn("key=", req.full_url)
        self.assertEqual(req.get_header("X-goog-api-key"), CLE)
        self.assertEqual(req.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(req.data), {"origin": "https://ex.fr"})
        self.assertLessEqual(m.call_args.kwargs.get("timeout", 99), 8)

    def test_transport_http_erreur_http_sans_url_ni_cle(self):
        url = crux.API + "queryRecord"
        err = urllib.error.HTTPError(url, 403, "Forbidden", {}, io.BytesIO(json.dumps(
            {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "clé " + CLE + " refusée ; " + url + "?key=" + CLE}}).encode()))
        with mock.patch.object(crux._OPENER, "open", side_effect=err):
            statut, donnees = crux.transport_http(url, {"origin": "https://ex.fr"}, {"X-Goog-Api-Key": CLE})
        self.assertEqual(statut, 403)
        self.assertNotIn(CLE, json.dumps(donnees))

    def test_transport_http_exception_reseau(self):
        url = crux.API + "queryRecord"
        with mock.patch.object(crux._OPENER, "open", side_effect=urllib.error.URLError("boom " + url + CLE)):
            self.assertEqual(crux.transport_http(url, {"origin": "https://ex.fr"}, {"X-Goog-Api-Key": CLE}), (0, {}))

    def test_redirection_jamais_suivie_et_cle_jamais_envoyee_ailleurs(self):
        recus = {"cible": [], "origine": []}

        def serveur(nom, reponse):
            class H(http.server.BaseHTTPRequestHandler):
                def do_POST(self):
                    self.rfile.read(int(self.headers.get("Content-Length") or 0))
                    recus[nom].append({k.lower(): v for k, v in self.headers.items()})
                    reponse(self)

                do_GET = do_POST

                def log_message(self, *a):
                    pass
            srv = http.server.HTTPServer(("127.0.0.1", 0), H)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self.addCleanup(srv.server_close)
            self.addCleanup(srv.shutdown)
            return srv.server_address[1]
        port_cible = serveur("cible", lambda h: (h.send_response(200), h.send_header("Content-Length", "2"), h.end_headers(),
                                                  h.wfile.write(b"{}")))
        for code in (301, 302, 303, 307, 308):
            def rediriger(h, code=code):
                h.send_response(code)
                h.send_header("Location", f"http://localhost:{port_cible}/pris")
                h.send_header("Content-Length", "0")
                h.end_headers()
            port = serveur("origine", rediriger)
            with self.subTest(code=code):
                statut, donnees = crux.transport_http(f"http://127.0.0.1:{port}/x", {"origin": "https://ex.fr"},
                                                      {"X-Goog-Api-Key": CLE})
                self.assertEqual((statut, donnees), (code, {}))
        self.assertEqual(recus["cible"], [], "la redirection ne doit jamais être suivie")
        self.assertEqual(len(recus["origine"]), 5)
        self.assertTrue(all(r.get("x-goog-api-key") == CLE for r in recus["origine"]))

    def test_redirection_est_un_constat_ignore_pas_une_erreur(self):
        _, md = TestAdressesEtArret()._lancer(lambda c: (302, {}))
        self.assertIn("⏭️ https://ex.fr : données terrain non lues (HTTP 302)", md)
        self.assertIn("redirection refusée", md)
        self.assertNotIn("❌", md)

    def test_message_libre_de_google_jamais_recopie(self):
        _, md = TestAdressesEtArret()._lancer(lambda c: (403, {"error": {"status": "PERMISSION_DENIED",
                                                                          "message": "API key " + CLE + " blocked"}}))
        self.assertNotIn(CLE, md)
        self.assertIn("PERMISSION_DENIED", md)

    def test_main_lit_l_environnement_et_ne_montre_pas_la_cle(self):
        def transport(url, corps, entetes):
            assert entetes["X-Goog-Api-Key"] == CLE and CLE not in url
            return (200, {"record": RECORD}) if not _est_histoire(url) else (200, {"record": HISTO})
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as e:
            urls = pathlib.Path(e, "urls.txt")
            urls.write_text("https://ex.fr/a\nnon\n", encoding="utf-8")
            sortie, erreur = io.StringIO(), io.StringIO()
            with mock.patch.dict(os.environ, {"PSI_API_KEY": CLE}, clear=False), mock.patch.object(crux, "transport_http", transport), \
                    mock.patch.object(crux.time, "sleep"), contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur), \
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
