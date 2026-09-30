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
            fps = [d["id"] for d in code if d.get("propre", "absent") == "absent" and score.detecte(d["matcher"], propre)]
        # trous connus du scanner, corrigés en phase 1 (la liste ne doit que rétrécir)
        self.assertEqual(rates, ["C10", "C12"], f"défauts de code non détectés : {rates}")
        self.assertEqual(fps, [], f"faux positifs de code : {fps}")


if __name__ == "__main__":
    unittest.main()
