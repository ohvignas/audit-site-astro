import json
import pathlib
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"))
import fiches  # noqa: E402
import rapport_html  # noqa: E402
import signaux  # noqa: E402


def ecrire(d, rel, contenu):
    f = pathlib.Path(d, "data", rel)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(contenu), encoding="utf-8")


def issue(sev, domaine=None):
    it = {"label": "Libellé", "severity": sev, "count": 1, "examples": [{"signature": "x"}]}
    if domaine:
        it["domaine"] = domaine
    return it


class TestNouvellesSources(unittest.TestCase):
    def test_issues_de_toutes_les_sources(self):
        with tempfile.TemporaryDirectory() as d:
            ecrire(d, "crawl/issues.json", {"svg_non_masque": issue("moyenne", "Accessibilité"), "title_dup": issue("moyenne")})
            ecrire(d, "rendu/issues.json", {"axe:color-contrast": issue("haute"),
                                            "cookies_avant_consentement": issue("haute", "RGPD / traceurs")})
            ecrire(d, "domaine/issues.json", {"dmarc_absent": issue("basse")})
            ecrire(d, "terrain/issues.json", {"terrain_lcp": issue("haute")})
            vus = sorted((s["source"], s["cle"], s["domaine"]) for s in signaux.collecter(d))
        self.assertEqual(vus, [
            ("crawl", "svg_non_masque", "Accessibilité"), ("crawl", "title_dup", "SEO technique"),
            ("domaine", "dmarc_absent", "Sécurité"),
            ("rendu", "axe:color-contrast", "Accessibilité"), ("rendu", "cookies_avant_consentement", "RGPD / traceurs"),
            ("terrain", "terrain_lcp", "Performance")])

    def test_declencheurs_regex_des_nouvelles_sources(self):
        sig = {"source": "rendu", "cle": "axe:color-contrast"}
        self.assertTrue(fiches.correspond("rendu:^axe:color-contrast$", sig))
        self.assertFalse(fiches.correspond("rendu:^axe:color$", sig))
        self.assertFalse(fiches.correspond("domaine:^axe:color-contrast$", sig))
        self.assertTrue(fiches.correspond("domaine:^spf_(permissif|absent)$", {"source": "domaine", "cle": "spf_absent"}))
        self.assertTrue(fiches.correspond("terrain:^terrain_lcp$", {"source": "terrain", "cle": "terrain_lcp"}))

    def test_fiche_rgpd_valide(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "rgpd-essai.md").write_text(
                '---\nid: rgpd-essai\ntitre: "Essai"\ndomaine: RGPD / traceurs\nseverite_type: haute\neffort: S\n'
                'declencheurs:\n  - "rendu:^cookies_avant_consentement$"\nsources:\n  - https://www.cnil.fr/\n---\n\n# Essai\n',
                encoding="utf-8")
            self.assertEqual([f["id"] for f in fiches.charger_fiches(d)], ["rgpd-essai"])

    def test_rgpd_compte_avec_la_securite(self):
        notes = rapport_html.notes_par_domaine([{"domaine": "RGPD / traceurs", "severite": "haute"}])
        self.assertEqual(notes["Sécurité"]["note"], 90)
        self.assertEqual(notes["Sécurité"]["inclut"], ["RGPD / traceurs"])


    def test_domaine_invalide_retombe_sur_le_defaut(self):
        with tempfile.TemporaryDirectory() as d:
            ecrire(d, "rendu/issues.json", {"a": issue("haute", "Domaine fantôme"), "b": {**issue("haute"), "domaine": ["x"]},
                                            "c": issue("haute", "RGPD / traceurs")})
            vus = {s["cle"]: s["domaine"] for s in signaux.collecter(d)}
        self.assertEqual(vus, {"a": "Accessibilité", "b": "Accessibilité", "c": "RGPD / traceurs"})

    def test_issues_non_dict_ignore(self):
        with tempfile.TemporaryDirectory() as d:
            ecrire(d, "rendu/issues.json", [1, 2])
            self.assertEqual(signaux.collecter(d), [])

    def test_exemples_pages_conserves(self):
        self.assertIn("exemples_pages", signaux.ex_str({"exemples_pages": ["/a"], "signature": "s"}))


class TestAuditeSeulementSiSortie(unittest.TestCase):
    def notes(self, fichiers=(), dossiers=()):
        with tempfile.TemporaryDirectory() as d:
            for rel, contenu in fichiers:
                f = pathlib.Path(d, "data", rel)
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(contenu, encoding="utf-8")
            for rel in dossiers:
                pathlib.Path(d, "data", rel).mkdir(parents=True, exist_ok=True)
            return rapport_html.notes_audit(d)

    def test_dossiers_vides_ne_comptent_pas(self):
        self.assertEqual(self.notes(dossiers=("rendu", "crawl", "terrain", "domaine", "geo", "securite", "code")), {})

    def test_fichiers_vides_ne_comptent_pas(self):
        self.assertEqual(self.notes(fichiers=(("rendu/issues.json", ""), ("crawl/issues.json", ""))), {})

    def test_rendu_valide_audite_l_accessibilite(self):
        n = self.notes(fichiers=(("rendu/issues.json", "{}"),))
        self.assertEqual(n["Accessibilité"]["note"], 100)
        self.assertNotIn("SEO technique", n)

    def test_crawl_valide_audite_le_seo(self):
        self.assertEqual(self.notes(fichiers=(("crawl/pages.json", "{}"),))["SEO technique"]["note"], 100)

    def test_domaine_valide_audite_la_securite(self):
        self.assertEqual(self.notes(fichiers=(("domaine/issues.json", "{}"),))["Sécurité"]["note"], 100)

    def test_terrain_n_audite_pas_la_performance(self):
        self.assertEqual(self.notes(fichiers=(("terrain/issues.json", "{}"),)), {})

    def test_sources_existantes_exigent_leur_fichier(self):
        n = self.notes(fichiers=(("geo/geo.json", "{}"), ("code/code-scan.json", "{}"), ("securite/security-probe.md", "x")))
        self.assertEqual(sorted(n), ["Code", "GEO / IA", "Sécurité"])

    def test_dedoublonnage_securite(self):
        n = self.notes(fichiers=(("securite/security-probe.md", "x"), ("domaine/issues.json", "{}")))
        self.assertEqual(list(n), ["Sécurité"])


if __name__ == "__main__":
    unittest.main()
