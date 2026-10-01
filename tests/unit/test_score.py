import importlib
import json
import pathlib
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE))
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


def collecte_ok(dossier, lignes=None):
    """Écrit un data/COLLECTE.md minimal ; `lignes` = lignes de tableau supplémentaires."""
    d = pathlib.Path(dossier, "data")
    d.mkdir(parents=True, exist_ok=True)
    (d / "COLLECTE.md").write_text("\n".join(
        ["# Collecte", "", "| Étape | Statut | Durée | Sortie |", "|---|---|---|---|", "| pré-vol | ✅ HTTP 200 | | https://x/ |"]
        + list(lignes or [])) + "\n", encoding="utf-8")


class TestMatcherPropre(unittest.TestCase):
    def test_retire_les_trois_filtres_et_garde_le_reste(self):
        self.assertEqual(score.matcher_propre({"type": "crawl_issue", "cle": "orphan", "contient": "/orpheline"}),
                         {"type": "crawl_issue", "cle": "orphan"})
        self.assertEqual(score.matcher_propre({"type": "code", "regex": "x", "ou_contient": "a.ts"}),
                         {"type": "code", "regex": "x"})
        self.assertEqual(score.matcher_propre({"type": "lighthouse", "regex": "x", "exemple_contient": "b.js"}),
                         {"type": "lighthouse", "regex": "x"})
        for m in ({"type": "texte", "fichier": "f.md", "regex": "r"}, {"type": "geo_signal", "regex": "r"}):
            self.assertEqual(score.matcher_propre(m), m)

    def test_ne_modifie_pas_le_matcher_d_origine(self):
        m = {"type": "crawl_issue", "cle": "orphan", "contient": "/orpheline"}
        score.matcher_propre(m)
        self.assertEqual(m["contient"], "/orpheline")

    def _verite(self, defaut):
        return {"defauts": [dict({"id": "T1", "domaine": "seo", "titre": "t", "phase": "base"}, **defaut)]}

    def test_faux_positif_detecte_meme_avec_des_chemins_differents(self):
        verite = self._verite({"matcher": {"type": "crawl_issue", "cle": "orphan", "contient": "/orpheline"}})
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            casse = audit(t1, crawl={"orphan": {"examples": ["https://x/orpheline"]}})
            propre = audit(t2, crawl={"orphan": {"examples": ["https://x/autre-page"]}})
            r = score.scorer(verite, casse, propre, phase=0)
            self.assertEqual([d["id"] for d in r["faux_positifs"]], ["T1"])

    def test_pas_de_faux_positif_si_la_cle_est_absente(self):
        verite = self._verite({"matcher": {"type": "crawl_issue", "cle": "orphan", "contient": "/orpheline"}})
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            casse = audit(t1, crawl={"orphan": {"examples": ["https://x/orpheline"]}})
            propre = audit(t2, crawl={"http_4xx": {"examples": []}})
            self.assertEqual(score.scorer(verite, casse, propre, phase=0)["faux_positifs"], [])

    def test_ignorer_reste_ignore(self):
        verite = self._verite({"propre": "ignorer", "matcher": {"type": "crawl_issue", "cle": "orphan", "contient": "/orpheline"}})
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            casse = audit(t1, crawl={"orphan": {"examples": ["https://x/orpheline"]}})
            propre = audit(t2, crawl={"orphan": {"examples": ["https://x/autre-page"]}})
            self.assertEqual(score.scorer(verite, casse, propre, phase=0)["faux_positifs"], [])

    def test_matcher_propre_explicite_prioritaire(self):
        verite = self._verite({"matcher": {"type": "crawl_issue", "cle": "orphan", "contient": "/orpheline"},
                               "matcher_propre": {"type": "crawl_issue", "cle": "orphan", "contient": "/cible-propre"}})
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2, tempfile.TemporaryDirectory() as t3:
            casse = audit(t1, crawl={"orphan": {"examples": ["https://x/orpheline"]}})
            propre_autre = audit(t2, crawl={"orphan": {"examples": ["https://x/autre-page"]}})
            propre_cible = audit(t3, crawl={"orphan": {"examples": ["https://x/cible-propre"]}})
            self.assertEqual(score.scorer(verite, casse, propre_autre, phase=0)["faux_positifs"], [])
            self.assertEqual([d["id"] for d in score.scorer(verite, casse, propre_cible, phase=0)["faux_positifs"]], ["T1"])


class TestValiderAudit(unittest.TestCase):
    def _complet(self, dossier, lignes=None):
        collecte_ok(dossier, lignes)
        return audit(dossier, crawl={}, code={"constats": []}, geo={"signaux": []}, perf=[])

    def test_audit_valide(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(score.valider_audit(self._complet(t, ["| crawl | ✅ | 3 s | data/crawl/pages.json |",
                                                                   "| lighthouse | ⚠️ code 1 (voir data/.log) | 2 s | x |"])), [])

    def test_etape_en_echec(self):
        with tempfile.TemporaryDirectory() as t:
            problemes = score.valider_audit(self._complet(t, ["| geo | ❌ résultat vide ou inexploitable | 1 s | data/geo/geo.json |"]))
            self.assertEqual(len(problemes), 1)
            self.assertIn("geo", problemes[0])

    def test_fichier_manquant(self):
        with tempfile.TemporaryDirectory() as t:
            a = self._complet(t)
            (a / "data/perf/pagespeed.json").unlink()
            problemes = score.valider_audit(a)
            self.assertEqual(len(problemes), 1)
            self.assertIn("perf/pagespeed.json", problemes[0])

    def test_collecte_absente(self):
        with tempfile.TemporaryDirectory() as t:
            a = self._complet(t)
            (a / "data/COLLECTE.md").unlink()
            self.assertTrue(any("COLLECTE.md" in p for p in score.valider_audit(a)))

    def test_croix_hors_colonne_statut_ignoree(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(score.valider_audit(self._complet(t, ["| http | ✅ | 1 s | http/❌.md |"])), [])


class TestVeriteUnitaires(unittest.TestCase):
    def test_tests_unitaires_references_existent(self):
        verite = json.loads((RACINE / "tests/cobaye/verite-terrain.json").read_text(encoding="utf-8"))
        vus = 0
        for d in verite["defauts"]:
            m = d["matcher"]
            if m["type"] != "unitaire" or score._phase(d["phase"]) > 0:
                continue
            vus += 1
            chemin = m["test"]
            try:
                importlib.import_module(chemin)
            except ImportError:
                module, _, classe = chemin.rpartition(".")
                self.assertTrue(module, "test {0} introuvable".format(chemin))
                obj = getattr(importlib.import_module(module), classe, None)
                self.assertIsNotNone(obj, "défaut {0} : {1} n'existe pas".format(d["id"], chemin))
        self.assertGreater(vus, 0)


class TestSeuils(unittest.TestCase):
    def test_seuils_bien_formes(self):
        seuils = json.loads((RACINE / "tests/cobaye/seuils.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(seuils["rappel_min_global"], 0)
        self.assertLessEqual(seuils["rappel_min_global"], 1)
        domaines = seuils["rappel_min_par_domaine"]
        self.assertEqual(sorted(domaines), ["a11y", "code", "geo", "http", "perf", "securite", "seo"])
        for domaine, v in domaines.items():
            self.assertTrue(0 <= v <= 1, "rappel {0} hors [0,1] : {1}".format(domaine, v))
        for cle in ("faux_positifs_max", "inattendus_max"):
            self.assertIsInstance(seuils[cle], int, cle)
            self.assertGreaterEqual(seuils[cle], 0, cle)


class TestCliquetPhase1(unittest.TestCase):
    def test_banc_mesure_la_phase_1(self):
        ci = (RACINE / ".github/workflows/docker.yml").read_text(encoding="utf-8")
        self.assertIn("--phase 1", ci)
        verite = json.loads((RACINE / "tests/cobaye/verite-terrain.json").read_text(encoding="utf-8"))
        requis = {d["id"] for d in verite["defauts"] if d["matcher"]["type"] != "unitaire" and score._phase(d["phase"]) <= 1}
        self.assertTrue({"S19", "S35b", "X06"} <= requis)
        self.assertEqual(len(requis), 104)

    def test_seuils_au_maximum(self):
        seuils = json.loads((RACINE / "tests/cobaye/seuils.json").read_text(encoding="utf-8"))
        self.assertEqual(seuils["rappel_min_global"], 1.0)
        self.assertEqual(set(seuils["rappel_min_par_domaine"].values()), {1.0})
        self.assertEqual((seuils["faux_positifs_max"], seuils["inattendus_max"]), (0, 0))


class TestSourcesV21(unittest.TestCase):
    def _audit(self, d, fichiers):
        for rel, contenu in fichiers.items():
            f = pathlib.Path(d, "data", rel)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(contenu), encoding="utf-8")
        return pathlib.Path(d)

    def test_crawl_issue_dans_un_autre_fichier(self):
        with tempfile.TemporaryDirectory() as d:
            a = self._audit(d, {"rendu/issues.json": {"axe:color-contrast": {
                "label": "Contraste", "severity": "haute", "count": 2,
                "examples": [{"signature": ".discret", "exemples_pages": ["https://c.test/v21/contraste"],
                              "variables": ["--texte-discret"]}]}}})
            m = {"type": "crawl_issue", "fichier": "rendu/issues.json", "cle": "axe:color-contrast", "contient": "--texte-discret"}
            self.assertTrue(score.detecte(m, a))
            self.assertFalse(score.detecte(dict(m, cle="axe:region"), a))
            self.assertFalse(score.detecte({"type": "crawl_issue", "cle": "axe:color-contrast"}, a), "défaut : crawl/issues.json")

    def test_inattendus_de_toutes_les_sources(self):
        def it(sev):
            return {"label": "l", "severity": sev, "count": 1, "examples": []}
        with tempfile.TemporaryDirectory() as d:
            a = self._audit(d, {
                "crawl/issues.json": {"http_5xx": it("haute"), "noindex": it("info"), "lent": it("moyenne")},
                "rendu/issues.json": {"axe:link-name": it("haute")},
                "domaine/issues.json": {"spf_permissif": it("critique")},
                "terrain/issues.json": {"terrain_lcp": it("haute"), "terrain_cls": it("moyenne")}})
            inattendus = score._inattendus(a)
        self.assertEqual(sorted((i["source"], i["cle"]) for i in inattendus),
                         [("crawl", "http_5xx"), ("domaine", "spf_permissif"), ("rendu", "axe:link-name"), ("terrain", "terrain_lcp")])

    def test_rendu_requis_a_partir_de_la_phase_2(self):
        with tempfile.TemporaryDirectory() as d:
            a = self._audit(d, {"crawl/issues.json": {}, "geo/geo.json": {}, "code/code-scan.json": {}, "perf/pagespeed.json": []})
            (a / "data/COLLECTE.md").write_text("| crawl | ✅ | 1 s | x |\n", encoding="utf-8")
            self.assertEqual(score.valider_audit(a, phase=1), [])
            self.assertEqual(score.valider_audit(a, phase=2), ["data/rendu/issues.json manquant"])

    def _propre_valide(self, d, **extra):
        fichiers = {"crawl/issues.json": {}, "geo/geo.json": {}, "code/code-scan.json": {}, "perf/pagespeed.json": [],
                    "rendu/issues.json": {}}
        fichiers.update(extra)
        a = self._audit(d, {k: v for k, v in fichiers.items() if v is not None})
        (a / "data/COLLECTE.md").write_text("| crawl | ✅ | 1 s | x |\n", encoding="utf-8")
        return a

    def test_issues_vide_valide_mais_illisible_refuse(self):
        with tempfile.TemporaryDirectory() as d:
            a = self._propre_valide(d)
            self.assertEqual(score.valider_audit(a, phase=2), [], "{} = aucun constat, valide")
            cible = a / "data/rendu/issues.json"
            for contenu in ("", '{"axe:region": {"severity": "haute", "examples": [', "[]", "null"):
                cible.write_text(contenu, encoding="utf-8")
                self.assertEqual(score.valider_audit(a, phase=2),
                                 ["data/rendu/issues.json illisible (JSON de type objet attendu)"], repr(contenu))

    def test_issues_illisible_refuse_pour_toutes_les_sources(self):
        with tempfile.TemporaryDirectory() as d:
            a = self._propre_valide(d)
            for rel in ("crawl", "domaine", "terrain"):
                (a / "data" / rel).mkdir(parents=True, exist_ok=True)
                (a / "data" / rel / "issues.json").write_text("{", encoding="utf-8")
            self.assertEqual(score.valider_audit(a, phase=1), [
                "data/crawl/issues.json illisible (JSON de type objet attendu)",
                "data/domaine/issues.json illisible (JSON de type objet attendu)",
                "data/terrain/issues.json illisible (JSON de type objet attendu)"])

    def test_matcher_propre_garde_la_source_domaine_terrain(self):
        for src in ("rendu", "domaine", "terrain"):
            m = {"type": "crawl_issue", "fichier": src + "/issues.json", "cle": "k", "contient": "x"}
            self.assertEqual(score.matcher_propre(m), {"type": "crawl_issue", "fichier": src + "/issues.json", "cle": "k"})


if __name__ == "__main__":
    unittest.main()
