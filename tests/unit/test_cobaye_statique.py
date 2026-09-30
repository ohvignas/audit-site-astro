import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCAN = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts/astro_scan.py"
sys.path.insert(0, str(RACINE / "tests/cobaye"))
import score  # noqa: E402


class TestCobayeStatique(unittest.TestCase):
    def _scan(self, variante, dossier):
        subprocess.run([sys.executable, str(SCAN), str(RACINE / "tests/cobaye" / variante), "--out", str(pathlib.Path(dossier, "data/code"))],
                       check=True, capture_output=True, timeout=120)
        return pathlib.Path(dossier)

    def test_defauts_de_code_detectes_sur_casse_et_absents_sur_propre(self):
        verite = json.loads((RACINE / "tests/cobaye/verite-terrain.json").read_text(encoding="utf-8"))
        code = [d for d in verite["defauts"] if d["matcher"]["type"] == "code" and d["phase"] == "base"]
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            casse, propre = self._scan("casse", t1), self._scan("propre", t2)
            rates = [d["id"] for d in code if not score.detecte(d["matcher"], casse)]
            fps = [d["id"] for d in code if d.get("propre", "absent") == "absent" and score.detecte(score._matcher_fp(d), propre)]
        self.assertEqual(rates, [], f"défauts de code non détectés : {rates}")
        self.assertEqual(fps, [], f"faux positifs de code : {fps}")

    def test_propre_sans_constat_critique_ni_haut(self):
        with tempfile.TemporaryDirectory() as t:
            propre = self._scan("propre", t)
            constats = json.loads((propre / "data/code/code-scan.json").read_text(encoding="utf-8"))["constats"]
        hauts = [c["constat"] for c in constats if c["severite"] in score.SEVERES]
        self.assertEqual(hauts, [], "constats Critique/Haute sur le jumeau propre (comptés « inattendus » en CI)")


if __name__ == "__main__":
    unittest.main()
