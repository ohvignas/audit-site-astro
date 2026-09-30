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


    # --- correctifs de la revue (tour 1) ---------------------------------------------------------------------------
    def _audit_minimal(self, racine, issues=None, code=None, pagespeed=None):
        """Dossier d'audit réduit pour piloter les cas limites de generer()."""
        import json
        a = pathlib.Path(racine, "audit")
        (a / "data/crawl").mkdir(parents=True)
        (a / "data/crawl/pages.json").write_text(json.dumps({"meta": {"start_url": "https://exemple.test/"}}), encoding="utf-8")
        (a / "data/crawl/issues.json").write_text(json.dumps(issues or {}), encoding="utf-8")
        if code is not None:
            (a / "data/code").mkdir()
            (a / "data/code/code-scan.json").write_text(json.dumps({"constats": code}), encoding="utf-8")
        if pagespeed is not None:
            (a / "data/perf").mkdir()
            (a / "data/perf/pagespeed.json").write_text(json.dumps(pagespeed), encoding="utf-8")
        return a

    def test_liens_dangereux_neutralises(self):
        import rapport_html
        for url in ("\x01javascript:alert(1)", "java\tscript:alert(1)", "java\nscript:alert(1)", "JaVaScRiPt:alert(1)",
                    "data:text/html;base64,AAAA", "vbscript:msgbox(1)", "//evil.example/x", "\\\\evil.example",
                    "&#x6A;avascript:alert(1)", "ftp://exemple.test/f"):
            h = rapport_html.markdown_vers_html(f"[x]({url})")
            self.assertNotIn("<a ", h, url)
            self.assertNotIn("href", h, url)

    def test_liens_sains_conserves(self):
        import rapport_html
        for url in ("https://exemple.test/a?b=1&c=2", "http://exemple.test", "mailto:a@exemple.test", "#ancre", "/chemin/page",
                    "./page.html", "../page", "page.html", "dossier/page?x=1", "?q=1"):
            self.assertIn('<a href="', rapport_html.markdown_vers_html(f"[x]({url})"), url)
        self.assertIn('href="https://exemple.test/a?b=1&amp;c=2"', rapport_html.markdown_vers_html("[x](https://exemple.test/a?b=1&c=2)"))

    def test_lighthouse_malforme_tolere(self):
        with tempfile.TemporaryDirectory() as t:
            a = self._audit_minimal(t, pagespeed=[
                {"url": "https://exemple.test/", "strategie": "mobile", "scores": "x", "metriques": ["y"], "terrain_page": "z", "terrain_origine": 3},
                {"url": "https://exemple.test/b", "strategie": "desktop", "scores": {"performance": "NaN?"}, "metriques": {"LCP": "4 s", "CLS": None},
                 "terrain_page": {"categorie_globale": "FAST", "LCP": "vite", "CLS": {"p75": 0.1, "verdict": "bon"}}}])
            import rapport_html
            h = rapport_html.generer(a)
        self.assertIn("https://exemple.test/b", h)
        self.assertIn("Lighthouse", h)

    def test_markdown_tableau_gfm_un_tiret_et_code_avec_barre(self):
        import rapport_html
        h = rapport_html.markdown_vers_html("| A | B |\n|-|-|\n| 1 | 2 |\n\n| C | D |\n|:-|-:|\n| `x|y` | z \\| w |\n")
        self.assertEqual(h.count("<table>"), 2)
        self.assertIn("<code>x|y</code>", h)
        self.assertEqual(h.count("<td>"), 4)
        self.assertIn("z | w", h)

    def test_markdown_titre_garde_diese_final(self):
        import rapport_html
        self.assertIn("<h1>C#</h1>", rapport_html.markdown_vers_html("# C#"))
        self.assertIn("<h2>Titre</h2>", rapport_html.markdown_vers_html("## Titre ##"))
        self.assertIn("<h3>Titre #tag</h3>", rapport_html.markdown_vers_html("### Titre #tag"))

    def test_note_globale_renormalisee(self):
        import rapport_html
        n = {"Performance": {"note": 80, "critique": 0}, "Sécurité": {"note": 90, "critique": 0}, "Divers": {"note": 0, "critique": 0}}
        # (20 x 80 + 12 x 90) / 32 = 83,75 ; « Divers » (hors grille) et les domaines absents sont exclus
        self.assertEqual(rapport_html.note_globale(n), (84, False))
        self.assertEqual(rapport_html.note_globale({}), (None, False))

    def test_plafond_49_avec_critique_securite_ou_seo(self):
        import rapport_html
        bon = {"note": 100, "critique": 0}
        self.assertEqual(rapport_html.note_globale({"Performance": bon, "Sécurité": {"note": 80, "critique": 1}}), (49, True))
        self.assertEqual(rapport_html.note_globale({"Performance": bon, "SEO technique": {"note": 80, "critique": 1}}), (49, True))
        self.assertEqual(rapport_html.note_globale({"Performance": {"note": 80, "critique": 1}, "Code": bon}), (87, False))  # critique hors sécurité/SEO
        with tempfile.TemporaryDirectory() as t:
            a = self._audit_minimal(t, code=[{"severite": "critique", "categorie": "securite", "constat": "Clé secrète exposée", "piste": "", "ou": []}])
            import rapport_html as r
            h = r.generer(a)
        self.assertIn("Note plafonnée à 49/100", h)
        self.assertIn("Note globale indicative : 49 sur 100", h)
        with tempfile.TemporaryDirectory() as t:
            h = rapport_html.generer(self._audit_minimal(t))
        self.assertNotIn("Note plafonnée", h)


if __name__ == "__main__":
    unittest.main()
