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
        code = [d for d in verite["defauts"] if d["matcher"]["type"] == "code" and score._phase(d["phase"]) <= 2]  # phase ≤ 2 : défauts de code vérifiés en local, sans build
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


class TestX06Hermetique(unittest.TestCase):
    """X06 (proxy /_image ouvert) ne doit dépendre d'aucun hôte Internet : l'image « tierce » est servie
    dans le réseau docker du banc, par nginx, sous un nom dédié (revue finale I4)."""
    COBAYE = RACINE / "tests/cobaye"

    def setUp(self):
        import re
        from urllib.parse import urlparse
        m = re.search(r"AUDIT_IMAGE_DISTANTE=(\S+)", (self.COBAYE / "auditer.sh").read_text(encoding="utf-8"))
        self.assertIsNotNone(m, "auditer.sh doit fixer AUDIT_IMAGE_DISTANTE")
        self.url = urlparse(m.group(1).strip("'\""))
        self.re = re

    def test_image_servie_dans_le_reseau_du_banc(self):
        self.assertTrue(self.url.hostname.endswith(".cobaye.test"), self.url.geturl())
        compose = (self.COBAYE / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertRegex(compose, r"aliases: \[[^\]]*\b" + self.re.escape(self.url.hostname) + r"\b")
        self.assertIn("./nginx/images:/srv/images:ro", compose)
        confs = "\n".join(f.read_text(encoding="utf-8") for f in (self.COBAYE / "nginx/conf.d").glob("*.conf"))
        self.assertRegex(confs, r"server_name\s+" + self.re.escape(self.url.hostname) + r";")
        self.assertIn("root /srv/images;", confs)
        png = self.COBAYE / "nginx/images" / self.url.path.lstrip("/")
        self.assertTrue(png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), png)

    def test_casse_accepte_le_protocole_sans_hote_propre_le_refuse(self):
        casse = (self.COBAYE / "casse/astro.config.mjs").read_text(encoding="utf-8")
        motifs = self.re.search(r"remotePatterns:\s*\[(.*?)\]\s*}", casse).group(1)
        self.assertIn("{ protocol: '" + self.url.scheme + "' }", motifs, "le cassé autorise tout hôte sur ce protocole")
        self.assertNotIn("hostname", motifs)
        propre = (self.COBAYE / "propre/astro.config.mjs").read_text(encoding="utf-8")
        self.assertNotIn(self.url.hostname, propre, "le propre ne doit pas autoriser l'hôte d'images du banc")


if __name__ == "__main__":
    unittest.main()
