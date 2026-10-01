import json
import pathlib
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"))
import fiches  # noqa: E402
import pagespeed  # noqa: E402
import signaux  # noqa: E402

FICHES = fiches.charger_fiches(RACINE / "plugins/audit-site-astro/skills/audit-complet/references/fiches")

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


def _lhr(audits, refs, version="13.5.0"):
    return {"lighthouseVersion": version, "configSettings": {"formFactor": "mobile"}, "finalDisplayedUrl": "https://ex.fr/",
            "categories": {"performance": {"score": 0.8, "auditRefs": [{"id": r, "weight": 0} for r in refs]}},
            "audits": audits}


# Compression seule, serveur rapide, sans redirection : metricSavings à 0, économie dans debugData.wastedBytes
LHR13_COMPRESSION = _lhr({"document-latency-insight": {
    "score": 0, "scoreDisplayMode": "metricSavings", "title": "Latence de la requête de document",
    "metricSavings": {"FCP": 0, "LCP": 0},
    "details": {"type": "checklist", "items": {
        "noRedirects": {"label": "Pas de redirection", "value": True},
        "serverResponseIsFast": {"label": "Le serveur répond rapidement", "value": True},
        "usesCompression": {"label": "Applique la compression", "value": False}},
        "debugData": {"type": "debugdata", "redirectDuration": 0, "serverResponseTime": 180.4,
                      "uncompressedResponseBytes": 36000, "wastedBytes": 33000}}}},
    ["document-latency-insight"])


def _ecrire_audit(lhr):
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "data/perf").mkdir(parents=True)
    entree = pagespeed.summarize_lhr(lhr)
    entree["strategie"] = "mobile"
    (d / "data/perf/pagespeed.json").write_text(json.dumps([entree]), encoding="utf-8")
    return d


class TestEconomiesEtUnites(unittest.TestCase):
    def test_compression_seule_gain_en_octets(self):
        o = pagespeed.summarize_lhr(LHR13_COMPRESSION)["opportunites"][0]
        self.assertEqual((o["gain_ms"], o["gain_octets"]), (0, 33000))
        self.assertEqual(o["titre"], "Latence de la requête de document (compression du document absente)")

    def test_compression_seule_signal_conserve(self):
        sigs = [x for x in signaux.collecter(_ecrire_audit(LHR13_COMPRESSION)) if x["source"] == "lighthouse"]
        self.assertEqual(len(sigs), 1)
        self.assertIn("32 Ko", sigs[0]["texte"])
        self.assertRegex(sigs[0]["cle"], "compression du document absente")

    def test_compression_seule_ne_declenche_pas_ttfb_lent(self):
        sig = [x for x in signaux.collecter(_ecrire_audit(LHR13_COMPRESSION)) if x["source"] == "lighthouse"][0]
        retenues, _ = fiches.associer([sig], FICHES)
        self.assertIn("serveur-compression-texte-absente", retenues)
        self.assertNotIn("serveur-ttfb-lent", retenues)
        self.assertNotIn("serveur-redirections-hote-canonique", retenues)

    def test_serveur_lent_et_redirections_declenchent_leurs_fiches(self):
        lhr = _lhr({"document-latency-insight": {
            "score": 0, "scoreDisplayMode": "metricSavings", "title": "Latence de la requête de document",
            "metricSavings": {"FCP": 900, "LCP": 900},
            "details": {"type": "checklist", "items": {
                "noRedirects": {"value": False}, "serverResponseIsFast": {"value": False}, "usesCompression": {"value": True}}}}},
            ["document-latency-insight"])
        sig = [x for x in signaux.collecter(_ecrire_audit(lhr)) if x["source"] == "lighthouse"][0]
        retenues, _ = fiches.associer([sig], FICHES)
        self.assertIn("serveur-ttfb-lent", retenues)
        self.assertIn("serveur-redirections-hote-canonique", retenues)
        self.assertNotIn("serveur-compression-texte-absente", retenues)

    def test_titre_serveur_lent_et_redirections(self):
        lhr = _lhr({"document-latency-insight": {
            "score": 0, "scoreDisplayMode": "metricSavings", "title": "Latence", "metricSavings": {"FCP": 900, "LCP": 900},
            "details": {"type": "checklist", "items": {
                "noRedirects": {"value": False}, "serverResponseIsFast": {"value": False}, "usesCompression": {"value": True}}}}},
            ["document-latency-insight"])
        t = pagespeed.summarize_lhr(lhr)["opportunites"][0]["titre"]
        self.assertIn("redirections", t)
        self.assertIn("réponse serveur lente", t)
        self.assertNotIn("compression", t)

    def test_ttfb_labo_depuis_le_diagnostic(self):
        m = pagespeed.summarize_lhr(LHR13_COMPRESSION)["metriques"]["TTFB labo"]
        self.assertEqual((m["valeur"], m["affiche"], m["score"]), (180.4, "180 ms", None))

    def test_cls_jamais_compte_en_ms_lh13(self):
        lhr = _lhr({"cls-culprits-insight": {
            "score": 0, "scoreDisplayMode": "metricSavings", "title": "Causes des décalages", "metricSavings": {"CLS": 0.62},
            "details": {"type": "list", "items": []}}}, ["cls-culprits-insight"])
        o = pagespeed.summarize_lhr(lhr)["opportunites"][0]
        self.assertEqual(o["gain_ms"], 0)

    def test_cls_jamais_compte_en_ms_lh12(self):
        lhr = _lhr({"layout-shifts": {
            "score": 0, "scoreDisplayMode": "metricSavings", "title": "Décalages", "metricSavings": {"CLS": 0.62},
            "details": {"type": "table", "items": []}}}, ["layout-shifts"], version="12.6.0")
        self.assertEqual(pagespeed.summarize_lhr(lhr)["opportunites"][0]["gain_ms"], 0)

    def test_cls_informatif_bon_pas_une_opportunite(self):
        lhr = _lhr({"cls-culprits-insight": {
            "score": None, "scoreDisplayMode": "informative", "title": "Causes", "metricSavings": {"CLS": 0.03},
            "details": {"type": "list", "items": []}}}, ["cls-culprits-insight"])
        self.assertEqual(pagespeed.summarize_lhr(lhr)["opportunites"], [])

    def test_ms_des_autres_metriques_inchange_avec_cls(self):
        lhr = _lhr({"x-insight": {"score": 0, "scoreDisplayMode": "metricSavings", "title": "X",
                                  "metricSavings": {"LCP": 400, "CLS": 0.5}, "details": {"type": "table", "items": []}}},
                   ["x-insight"])
        self.assertEqual(pagespeed.summarize_lhr(lhr)["opportunites"][0]["gain_ms"], 400)


class TestElementLcpEtTiers(unittest.TestCase):
    def test_element_lcp_noeud_nu_lh13(self):
        for aid in ("lcp-breakdown-insight", "lcp-discovery-insight"):
            lhr = _lhr({aid: {"score": 1, "scoreDisplayMode": "numeric", "title": "LCP", "details": {
                "type": "list", "items": [{"type": "table", "items": [
                    {"type": "node", "snippet": '<img src="/hero.jpg">', "selector": "main > img", "nodeLabel": "img"}]}]}}},
                ["lcp-breakdown-insight"])
            self.assertEqual(pagespeed.summarize_lhr(lhr)["element_lcp"],
                             [{"snippet": '<img src="/hero.jpg">', "selector": "main > img"}], aid)

    def test_element_lcp_lh12_inchange(self):
        lhr = _lhr({"largest-contentful-paint-element": {"score": None, "scoreDisplayMode": "informative", "title": "LCP", "details": {
            "type": "table", "items": [{"node": {"type": "node", "snippet": "<h1>", "selector": "h1"}}]}}},
            ["largest-contentful-paint-element"], version="12.6.0")
        self.assertEqual(pagespeed.summarize_lhr(lhr)["element_lcp"], [{"snippet": "<h1>", "selector": "h1"}])

    def test_tiers_lh13_temps_thread_principal(self):
        lhr = _lhr({"third-parties-insight": {"score": 1, "scoreDisplayMode": "numeric", "title": "Tiers", "details": {
            "type": "table", "items": [{"entity": "Google Tag Manager", "transferSize": 90112, "mainThreadTime": 120.5}]}}}, [])
        t = pagespeed.summarize_lhr(lhr)["tiers"][0]
        self.assertEqual((t["tiers"], t["ko"], t["thread_ms"], t["blocage_ms"]), ("Google Tag Manager", 88, 120, None))

    def test_tiers_lh12_blocage_conserve(self):
        lhr = _lhr({"third-party-summary": {"score": 1, "scoreDisplayMode": "informative", "title": "Tiers", "details": {
            "type": "table", "items": [{"entity": {"type": "link", "text": "GTM"}, "transferSize": 2048,
                                        "blockingTime": 33.2, "mainThreadTime": 50}]}}}, [], version="12.6.0")
        t = pagespeed.summarize_lhr(lhr)["tiers"][0]
        self.assertEqual((t["blocage_ms"], t["thread_ms"]), (33, 50))

    def test_table_des_insights_ids_reels(self):
        self.assertEqual(pagespeed.INSIGHTS_LH13["uses-long-cache-ttl"], "cache-insight")
        self.assertEqual(pagespeed.INSIGHTS_LH13["largest-contentful-paint-element"], "lcp-breakdown-insight")


class TestSignalInsightSansGain(unittest.TestCase):
    CLS = _lhr({"cls-culprits-insight": {
        "score": 0, "scoreDisplayMode": "metricSavings", "title": "Causes des décalages de mise en page",
        "metricSavings": {"CLS": 0.4},
        "details": {"type": "list", "items": [{"type": "table", "items": [
            {"node": {"type": "node", "snippet": "<img>", "selector": "img"}, "score": 0.4}]}]}}}, ["cls-culprits-insight"])

    def test_insight_en_echec_sans_gain_conserve_sans_texte_vide(self):
        sigs = [x for x in signaux.collecter(_ecrire_audit(self.CLS)) if x["source"] == "lighthouse"]
        self.assertEqual(len(sigs), 1)
        self.assertEqual(sigs[0]["texte"], "Causes des décalages de mise en page (mobile)")
        self.assertEqual(sigs[0]["cle"], "cls-culprits-insight Causes des décalages de mise en page")
        self.assertEqual(sigs[0]["severite"], "basse")

    def test_fiche_perf_cls_se_declenche(self):
        sig = [x for x in signaux.collecter(_ecrire_audit(self.CLS)) if x["source"] == "lighthouse"][0]
        retenues, _ = fiches.associer([sig], FICHES)
        self.assertIn("perf-cls", retenues)

    def test_audit_lh12_sans_gain_toujours_ecarte(self):
        lhr = _lhr({"unsized-images": {"score": 0, "scoreDisplayMode": "binary", "title": "Images sans dimensions",
                                       "details": {"type": "table", "items": []}}}, ["unsized-images"], version="12.6.0")
        self.assertEqual([x for x in signaux.collecter(_ecrire_audit(lhr)) if x["source"] == "lighthouse"], [])

    def test_insight_informatif_sans_gain_ecarte(self):
        lhr = _lhr({"dom-size-insight": {"score": None, "scoreDisplayMode": "informative", "title": "Taille du DOM",
                                         "numericValue": 800, "details": {"type": "table", "items": []}}}, ["dom-size-insight"])
        self.assertEqual([x for x in signaux.collecter(_ecrire_audit(lhr)) if x["source"] == "lighthouse"], [])


if __name__ == "__main__":
    unittest.main()
