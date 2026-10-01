import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCAN = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts/astro_scan.py"

XMLNS = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'


def scanner(fichiers):
    """Crée un mini-projet Astro 7 (fichiers = {chemin: contenu}), lance astro_scan et renvoie les constats."""
    with tempfile.TemporaryDirectory() as d:
        base = {"package.json": json.dumps({"dependencies": {"astro": "^7.3.0"}}), ".gitignore": ".env\n"}
        for chemin, contenu in dict(base, **fichiers).items():
            f = pathlib.Path(d, "projet", chemin)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(contenu, encoding="utf-8")
        subprocess.run([sys.executable, str(SCAN), str(pathlib.Path(d, "projet")), "--out", str(pathlib.Path(d, "out"))],
                       check=True, capture_output=True, timeout=120)
        return json.loads(pathlib.Path(d, "out", "code-scan.json").read_text(encoding="utf-8"))["constats"]


def textes(constats):
    return "\n".join(c["constat"] for c in constats)


class TestConfigSansCommentaires(unittest.TestCase):
    def test_globs_dans_des_chaines_ne_sont_pas_des_commentaires(self):  # revue finale I1
        cfg = ("export default defineConfig({\n  site: 'https://ex.fr',\n  output: 'server',\n"
               "  image: { remotePatterns: [{ protocol: 'https', hostname: 'cdn.ex.fr', pathname: '/images/**' }] },\n"
               "  security: { allowedDomains: [{ hostname: 'ex.fr', protocol: 'https' }] },\n"
               "  vite: { server: { watch: { ignored: ['**/tmp/**'] } } },\n});\n")
        self.assertNotIn("sans security.allowedDomains", textes(scanner({"astro.config.mjs": cfg})))

    def test_automate_de_commentaires(self):
        sys.path.insert(0, str(SCAN.parent))
        import astro_scan
        src = ("a = '/images/**'; /* vrai */ b = \"x // pas un commentaire\"; // fin\n"
               "c = `t /* ${d} */ \\` // ok`; e = 'it\\'s /*'; f = 1 /* multi\nligne */ + 2\n")
        out = astro_scan.sans_commentaires(src)
        for garde in ("'/images/**'", "\"x // pas un commentaire\"", "`t /* ${d} */ \\` // ok`", "'it\\'s /*'", "+ 2"):
            self.assertIn(garde, out)
        for retire in ("vrai", "fin", "multi"):
            self.assertNotIn(retire, out)
        self.assertEqual(out.count("\n"), src.count("\n"), "les numéros de ligne sont conservés")

    def test_allowed_domains_cite_en_commentaire_ne_compte_pas(self):  # C12
        cfg = ("export default defineConfig({\n  site: 'https://ex.fr',\n  output: 'server',\n"
               "  // pas de security.allowedDomains ici\n});\n")
        self.assertIn("sans security.allowedDomains", textes(scanner({"astro.config.mjs": cfg})))

    def test_allowed_domains_configure(self):
        cfg = ("export default defineConfig({ site: 'https://ex.fr', output: 'server',\n"
               "  security: { allowedDomains: [{ hostname: 'ex.fr', protocol: 'https' }] } });\n")
        self.assertNotIn("sans security.allowedDomains", textes(scanner({"astro.config.mjs": cfg})))


class TestSitemap(unittest.TestCase):
    CFG = "export default defineConfig({ site: 'https://ex.fr' });\n"

    def test_origine_de_la_requete_malgre_sitemaps_org(self):  # C10 + xmlns
        ep = ("export const GET = ({ request }) => {\n  const origin = new URL(request.url).origin; // http:// derrière un proxy\n"
              "  return new Response(`" + XMLNS + "<url><loc>${origin}/</loc></url></urlset>`);\n};\n")
        t = textes(scanner({"astro.config.mjs": self.CFG, "src/pages/sitemap.xml.ts": ep}))
        self.assertIn("depuis l'origine de la requête", t)
        self.assertNotIn("http:// en dur", t, "l'espace de noms XML et un commentaire ne sont pas des URL en dur")

    def test_mot_site_dans_le_texte_ne_vaut_pas_astro_site(self):  # revue finale M6
        ep = ("export const GET = ({ request }) => {\n  const origin = new URL(request.url).origin;\n"
              "  const titre = 'Plan du site';\n"
              "  return new Response(`" + XMLNS + "<url><loc>${origin}/plan-du-site</loc></url></urlset>`);\n};\n")
        self.assertIn("depuis l'origine de la requête", textes(scanner({"astro.config.mjs": self.CFG, "src/pages/sitemap.xml.ts": ep})))

    def test_sitemap_construit_avec_site(self):
        ep = ("export const GET = ({ site }) => new Response(`" + XMLNS +
              "<url><loc>${new URL('/', site).href}</loc></url></urlset>`);\n")
        t = textes(scanner({"astro.config.mjs": self.CFG, "src/pages/sitemap.xml.ts": ep}))
        self.assertNotIn("depuis l'origine de la requête", t)
        self.assertNotIn("http:// en dur", t)

    def test_vraie_url_http_en_dur(self):
        ep = "export const GET = () => new Response('<url><loc>http://ex.fr/</loc></url>');\n"
        self.assertIn("http:// en dur", textes(scanner({"astro.config.mjs": self.CFG, "src/pages/sitemap.xml.ts": ep})))


class TestSetHtml(unittest.TestCase):
    def test_json_ld_exclu_html_signale(self):  # C07 (faux positif du jumeau propre)
        page = ("---\nconst o = {};\nconst msg = Astro.url.searchParams.get('m');\n---\n"
                '<script type="application/ld+json" set:html={JSON.stringify(o)}></script>\n'
                "<div set:html={msg}></div>\n")
        c = [x for x in scanner({"src/pages/index.astro": page}) if "set:html" in x["constat"]]
        self.assertEqual(len(c), 1)
        self.assertEqual(len(c[0]["ou"]), 1)
        self.assertIn("src/pages/index.astro:6", c[0]["ou"][0])

    def test_json_ld_multiligne_prettier(self):  # revue finale M5
        page = ('---\nconst o = {};\n---\n<script\n  type="application/ld+json"\n  set:html={JSON.stringify(o)}\n></script>\n'
                '<div\n  set:html={o.html}\n></div>\n')
        c = [x for x in scanner({"src/pages/index.astro": page}) if "set:html" in x["constat"]]
        self.assertEqual(len(c), 1)
        self.assertEqual(len(c[0]["ou"]), 1)
        self.assertIn("src/pages/index.astro:9", c[0]["ou"][0])

    def test_json_ld_seul_rien_a_signaler(self):
        page = '---\nconst o = {};\n---\n<script type="application/ld+json" set:html={JSON.stringify(o)}></script>\n'
        self.assertNotIn("set:html", textes(scanner({"src/pages/index.astro": page})))


if __name__ == "__main__":
    unittest.main()
