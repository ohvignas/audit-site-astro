import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
FIXTURE = RACINE / "tests/unit/fixtures/audit-exemple"
sys.path.insert(0, str(SCRIPTS))


class TestRapportHtml(unittest.TestCase):
    def test_notes_par_domaine_bareme(self):
        import rapport_html
        s = [{"severite": "haute", "domaine": "Performance", "texte": "x", "exemples": []},
             {"severite": "moyenne", "domaine": "Performance", "texte": "y", "exemples": []},
             {"severite": "critique", "domaine": "Sécurité", "texte": "z", "exemples": []}]
        n = rapport_html.notes_par_domaine(s)
        self.assertEqual(n["Performance"]["note"], 86)
        self.assertEqual(n["Performance"]["lettre"], "B")
        self.assertEqual(n["Sécurité"]["note"], 80)

    def test_markdown_minimal(self):
        import rapport_html
        h = rapport_html.markdown_vers_html("# Titre\n\n- **gras** et `code`\n\n| A | B |\n|---|---|\n| 1 | <b>2</b> |\n")
        self.assertIn("<h1>Titre</h1>", h)
        self.assertIn("<strong>gras</strong>", h)
        self.assertIn("<code>code</code>", h)
        self.assertIn("<table>", h)
        self.assertIn("&lt;b&gt;2&lt;/b&gt;", h)  # HTML brut échappé

    def test_page_complete_sans_script_ni_ressource_externe(self):
        with tempfile.TemporaryDirectory() as t:
            copie = pathlib.Path(t, "audit")
            shutil.copytree(FIXTURE, copie)
            subprocess.run([sys.executable, str(SCRIPTS / "rapport_html.py"), str(copie)], check=True, capture_output=True)
            h = (copie / "RAPPORT.html").read_text(encoding="utf-8")
        self.assertTrue(h.startswith("<!doctype html>"))
        for section in ("Synthèse", "Lighthouse", "Rapport priorisé", "Signaux", "Annexes"):
            self.assertIn(section, h)
        self.assertNotIn("<script", h.lower())
        self.assertNotRegex(h, r'(src|href)="https?://(?!exemple\.test)')
        self.assertIn("@page", h)
        self.assertIn("prefers-color-scheme", h)

    def test_echappement_des_donnees_du_site(self):
        with tempfile.TemporaryDirectory() as t:
            copie = pathlib.Path(t, "audit")
            shutil.copytree(FIXTURE, copie)
            issues = copie / "data/crawl/issues.json"
            # \\" = guillemet échappé : le JSON reste valide et la charge utile atteint le rapport
            issues.write_text(issues.read_text(encoding="utf-8").replace("exemple.test", 'exemple.test/\\"><img src=x onerror=alert(1)>'), encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPTS / "rapport_html.py"), str(copie)], check=True, capture_output=True)
            h = (copie / "RAPPORT.html").read_text(encoding="utf-8")
        self.assertNotIn("<img src=x", h)
        self.assertIn("&lt;img src=x", h)

    def test_rapport_priorise_integre(self):
        with tempfile.TemporaryDirectory() as t:
            copie = pathlib.Path(t, "audit")
            shutil.copytree(FIXTURE, copie)
            (copie / "RAPPORT-AUDIT.md").write_text("# Audit du site\n\n### [PERF-001] Compression absente\n", encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPTS / "rapport_html.py"), str(copie)], check=True, capture_output=True)
            h = (copie / "RAPPORT.html").read_text(encoding="utf-8")
        self.assertIn("[PERF-001] Compression absente", h)
        self.assertIn("font foi", h)


if __name__ == "__main__":
    unittest.main()
