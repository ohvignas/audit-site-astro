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


class TestSignaux(unittest.TestCase):
    def test_collecter_trie_et_type(self):
        import signaux
        s = signaux.collecter(FIXTURE)
        self.assertTrue(s)
        rangs = [signaux.ORDRE[x["severite"]] for x in s]
        self.assertEqual(rangs, sorted(rangs))
        for x in s:
            self.assertEqual(set(x), {"severite", "domaine", "texte", "exemples"})

    def test_rapport_brut_inchange(self):
        """La sortie de rapport_brut.py doit être identique avant/après le refactor (référence commitée)."""
        with tempfile.TemporaryDirectory() as t:
            copie = pathlib.Path(t, "audit")
            shutil.copytree(FIXTURE, copie)
            subprocess.run([sys.executable, str(SCRIPTS / "rapport_brut.py"), str(copie)], check=True, capture_output=True)
            obtenu = (copie / "RAPPORT-BRUT.md").read_text(encoding="utf-8")
        attendu = (FIXTURE / "RAPPORT-BRUT.attendu.md").read_text(encoding="utf-8")
        self.assertEqual(obtenu, attendu)


if __name__ == "__main__":
    unittest.main()
