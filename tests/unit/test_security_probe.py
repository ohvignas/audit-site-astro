import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ICI = pathlib.Path(__file__).resolve().parent
RACINE = ICI.parents[1]
sys.path.insert(0, str(ICI))
from site_local import HTML, SiteLocal  # noqa: E402

SCRIPT = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts/security_probe.sh"
JS = {"Content-Type": "text/javascript"}
ACCUEIL = ("<html><head><title>Accueil</title></head><body>"
           '<astro-island uid="1" component-url="/_astro/Chat.abc123.js" renderer-url="/_astro/client.def456.js"></astro-island>'
           "</body></html>")


def sonder(routes, prefixes):
    with SiteLocal(routes, prefixes) as site, tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, AUDIT_IMAGE_DISTANTE="https://images.exemple.org/logo.png")
        env.pop("AUDIT_INSECURE_TLS", None)
        subprocess.run(["bash", str(SCRIPT), site.url, d], capture_output=True, text=True, timeout=240, env=env)
        return pathlib.Path(d, "security-probe.md").read_text(encoding="utf-8")


class TestSondeAstro(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # cassé : source map publique d'un JS d'îlot (X02), /_image transforme une image d'un domaine tiers (X06)
        cls.casse = sonder(
            {"/": (200, HTML, ACCUEIL),
             "/_astro/Chat.abc123.js": (200, JS, "console.log(1)\n//# sourceMappingURL=Chat.abc123.js.map\n"),
             "/_astro/Chat.abc123.js.map": (200, {"Content-Type": "application/json"}, '{"version":3}')},
            {"/_image": (200, {"Content-Type": "image/webp"}, "RIFF")})
        # propre : pas de source map, /_image refuse le domaine tiers (403)
        cls.propre = sonder(
            {"/": (200, HTML, ACCUEIL), "/_astro/Chat.abc123.js": (200, JS, "console.log(1)\n")},
            {"/_image": (403, {"Content-Type": "text/plain"}, "Forbidden")})

    def test_source_map_des_ilots(self):  # X02
        self.assertRegex(self.casse, r"/_astro/Chat\.abc123\.js → \.map HTTP 200")
        self.assertNotRegex(self.propre, r"\.map HTTP 200")

    def test_proxy_images_ouvert(self):  # X06
        self.assertIn("proxy d'images ouvert", self.casse)
        self.assertNotIn("proxy d'images ouvert", self.propre)
        self.assertIn("/_image refuse", self.propre)


if __name__ == "__main__":
    unittest.main()
