import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts/rapport_pdf.sh"
FIXTURE = RACINE / "tests/unit/fixtures/audit-exemple"


class TestRapportPdf(unittest.TestCase):
    def test_chrome_introuvable_donne_code_2(self):
        # Ne lance JAMAIS de navigateur : chemin inexistant, PATH réduit, recherche automatique désactivée.
        env = dict(os.environ, CHROME_PATH="/inexistant/chrome", PATH="/usr/bin:/bin",
                   AUDIT_NO_CHROME_DISCOVERY="1")
        with tempfile.TemporaryDirectory() as t:
            copie = pathlib.Path(t, "dossier avec espaces", "audit")
            shutil.copytree(FIXTURE, copie)
            r = subprocess.run(["bash", str(SCRIPT), str(copie)], capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("Chrome introuvable", r.stdout)
            self.assertFalse((copie / "RAPPORT.pdf").exists())

    def test_sans_chrome_ni_variable_donne_code_2(self):
        env = dict(os.environ, PATH="/usr/bin:/bin", AUDIT_NO_CHROME_DISCOVERY="1")
        env.pop("CHROME_PATH", None)
        with tempfile.TemporaryDirectory() as t:
            copie = pathlib.Path(t, "audit")
            shutil.copytree(FIXTURE, copie)
            r = subprocess.run(["bash", str(SCRIPT), str(copie)], capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    @unittest.skipUnless(os.environ.get("RUN_CHROME_TESTS") == "1", "Chrome requis (CI)")
    def test_pdf_a4_genere(self):
        with tempfile.TemporaryDirectory() as t:
            copie = pathlib.Path(t, "dossier avec espaces", "audit")
            shutil.copytree(FIXTURE, copie)
            r = subprocess.run(["bash", str(SCRIPT), str(copie)], capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            pdf = copie / "RAPPORT.pdf"
            self.assertTrue(pdf.exists())
            self.assertEqual(pdf.read_bytes()[:5], b"%PDF-")
            self.assertGreater(pdf.stat().st_size, 20 * 1024)


if __name__ == "__main__":
    unittest.main()
