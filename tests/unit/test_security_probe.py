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


def lancer(url, d):
    env = dict(os.environ, AUDIT_IMAGE_DISTANTE="https://images.exemple.org/logo.png")
    env.pop("AUDIT_INSECURE_TLS", None)
    subprocess.run(["bash", str(SCRIPT), url, d], capture_output=True, text=True, timeout=240, env=env)
    return pathlib.Path(d, "security-probe.md").read_text(encoding="utf-8")


def sonder(routes, prefixes, requetes=None):
    with SiteLocal(routes, prefixes) as site, tempfile.TemporaryDirectory() as d:
        md = lancer(site.url, d)
        if requetes is not None:
            requetes.extend(site.requetes)
        return md


class TestSondeAstro(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # cassé : source map publique d'un JS d'îlot (X02), /_image transforme une image d'un domaine tiers (X06)
        cls.requetes_casse = []
        cls.casse = sonder(
            {"/": (200, HTML, ACCUEIL),
             "/_astro/Chat.abc123.js": (200, JS, "console.log(1)\n//# sourceMappingURL=Chat.abc123.js.map\n"),
             "/_astro/Chat.abc123.js.map": (200, {"Content-Type": "application/json"}, '{"version":3}')},
            {"/_image": (200, {"Content-Type": "image/webp"}, "RIFF")}, cls.requetes_casse)
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
        # la sonde envoie bien l'image tierce, encodée, en paramètre href (revue finale M12)
        self.assertIn("/_image?href=https%3A%2F%2Fimages.exemple.org%2Flogo.png&w=16&f=webp", self.requetes_casse)

    def test_proxy_images_indetermine_si_erreur_serveur(self):  # revue finale I3
        md = sonder({"/": (200, HTML, ACCUEIL)}, {"/_image": (500, {"Content-Type": "text/plain"}, "fetch failed")})
        self.assertIn("⚠️ /_image indéterminé (HTTP 500)", md)
        self.assertNotIn("/_image refuse", md)
        self.assertNotIn("proxy d'images ouvert", md)

    def test_origine_effective_apres_redirection(self):  # revue finale I3 : apex → www
        with SiteLocal({"/": (200, HTML, ACCUEIL)},
                       {"/_image": (200, {"Content-Type": "image/webp"}, "RIFF")}) as final:
            with SiteLocal({"/": (301, {"Location": final.url}, "")}) as apex, tempfile.TemporaryDirectory() as d:
                md = lancer(apex.url, d)
        self.assertIn("proxy d'images ouvert", md)
        self.assertIn("# Sonde d'exposition — " + final.base, md)


class TestSecurityTxt(unittest.TestCase):
    """security.txt (RFC 9116) est un fichier que le site DOIT publier : jamais « EXPOSÉ »."""

    def ligne(self, md):
        return next(l for l in md.splitlines() if l.startswith("| /.well-known/security.txt |"))

    def test_present(self):
        md = sonder({"/": (200, HTML, ACCUEIL),
                     "/.well-known/security.txt": (200, {"Content-Type": "text/plain"},
                                                   "Contact: mailto:securite@ex.fr\nExpires: 2027-01-01T00:00:00Z\n")}, {})
        self.assertIn("✅ présent", self.ligne(md))
        self.assertNotIn("EXPOSÉ", md)

    def test_absent(self):
        md = sonder({"/": (200, HTML, ACCUEIL)}, {})
        self.assertIn("⚠️ absent (recommandé, RFC 9116)", self.ligne(md))

    def test_page_generique_en_200_vaut_absent(self):  # SPA / soft 404 : ce n'est pas un security.txt
        md = sonder({"/": (200, HTML, ACCUEIL)}, {"/": (200, HTML, "<html><body>accueil</body></html>")})
        self.assertIn("⚠️ absent", self.ligne(md))
        self.assertNotIn("✅ présent", self.ligne(md))


class TestSecretsV21(unittest.TestCase):
    CLE = "sk-" + "proj-" + "COBAYEa1B2c3D4e5F6g7H8j9K0"   # factice, concaténée

    def test_cle_connue_signalee_classes_tailwind_ignorees(self):
        page = '<html><body><script src="/_astro/app.js"></script></body></html>'
        casse = sonder({"/": (200, HTML, page), "/_astro/app.js": (200, JS, "const k='" + self.CLE + "';")}, {})
        propre = sonder({"/": (200, HTML, page), "/_astro/app.js": (200, JS, 'e.className="mask-image-b-from-color mask-image-b-to-color"')}, {})
        self.assertIn("OpenAI : sk-proj-", casse)       # X08
        self.assertNotIn(self.CLE, casse, "la clé complète ne doit jamais être écrite")
        self.assertNotIn("Motifs de secrets trouvés", propre)
        self.assertIn("aucun motif de clé secrète", propre)


if __name__ == "__main__":
    unittest.main()
