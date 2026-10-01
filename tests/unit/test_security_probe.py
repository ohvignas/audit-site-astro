import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ICI = pathlib.Path(__file__).resolve().parent
RACINE = ICI.parents[1]
sys.path.insert(0, str(ICI))
sys.path.insert(0, str(RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"))
from site_local import HTML, SiteLocal  # noqa: E402

SCRIPT = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts/security_probe.sh"
JS = {"Content-Type": "text/javascript"}
ACCUEIL = ("<html><head><title>Accueil</title></head><body>"
           '<astro-island uid="1" component-url="/_astro/Chat.abc123.js" renderer-url="/_astro/client.def456.js"></astro-island>'
           "</body></html>")


def lancer(url, d, script=SCRIPT, env_extra=None, retirer=()):
    env = dict(os.environ, AUDIT_IMAGE_DISTANTE="https://images.exemple.org/logo.png", **(env_extra or {}))
    env.pop("AUDIT_INSECURE_TLS", None)
    for k in retirer:
        env.pop(k, None)
    subprocess.run(["bash", str(script), url, d], capture_output=True, text=True, timeout=240, env=env)
    return pathlib.Path(d, "security-probe.md").read_text(encoding="utf-8")


def sonder(routes, prefixes, requetes=None, **options):
    with SiteLocal(routes, prefixes) as site, tempfile.TemporaryDirectory() as d:
        md = lancer(site.url, d, **options)
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


PAGE_JS = '<html><body><script src="/_astro/app.js"></script></body></html>'


def _page(js, **options):
    return sonder({"/": (200, HTML, PAGE_JS), "/_astro/app.js": (200, JS, js)}, {}, **options)


def _section_secrets(md):
    return md.split("## Clés et secrets dans le HTML / JS livrés au navigateur")[1].split("## Méthodes HTTP et CORS")[0]


class TestSecretsV21(unittest.TestCase):
    CLE = "sk-" + "proj-" + "COBAYEa1B2c3D4e5F6g7H8j9K0"   # factice, concaténée
    GOOGLE = "AI" + "za" + "SyD3k9Lm2Qx7Vb5Nr8Tw1Yh4Jf6Cp0Zg3AB"

    def test_cle_connue_signalee_classes_tailwind_ignorees(self):
        page = '<html><body><script src="/_astro/app.js"></script></body></html>'
        casse = sonder({"/": (200, HTML, page), "/_astro/app.js": (200, JS, "const k='" + self.CLE + "';")}, {})
        propre = sonder({"/": (200, HTML, page), "/_astro/app.js": (200, JS, 'e.className="mask-image-b-from-color mask-image-b-to-color"')}, {})
        self.assertIn("OpenAI : sk-proj-", casse)       # X08
        self.assertNotIn(self.CLE, casse, "la clé complète ne doit jamais être écrite")
        self.assertNotIn("Motifs de secrets trouvés", propre)
        self.assertIn("aucun motif de clé secrète", propre)

    def test_cle_google_publique_a_part_et_jamais_a_revoquer(self):
        md = _page("var firebaseConfig={apiKey:'" + self.GOOGLE + "'};")
        sec = _section_secrets(md)
        self.assertIn("⚠️ clé publique Google exposée (normal côté client) : vérifier qu'elle est restreinte par référent HTTP et par API", sec)
        self.assertNotIn("Motifs de secrets trouvés", md)
        self.assertNotIn("RÉVOQUER", md)
        self.assertNotIn("❌", sec)
        self.assertNotIn("✅ aucun motif", sec)
        self.assertNotIn(self.GOOGLE, md, "la clé complète ne doit jamais être écrite")

    def test_cle_google_et_secret_ensemble(self):
        sec = _section_secrets(_page("a='" + self.GOOGLE + "';b='" + self.CLE + "';"))
        self.assertIn("❌ Motifs de secrets trouvés", sec)
        self.assertIn("OpenAI : sk-proj-", sec)
        self.assertIn("⚠️ clé publique Google exposée", sec)
        self.assertNotIn("Google API :", sec.split("```")[1], "la clé publique n'est pas dans le bloc des secrets à révoquer")

    def test_la_ligne_google_est_reconnue_par_une_fiche_non_critique(self):
        import fiches
        base = fiches.charger_fiches(RACINE / "plugins/audit-site-astro/skills/audit-complet/references/fiches")
        ligne = "- ⚠️ clé publique Google exposée (normal côté client) : vérifier qu'elle est restreinte par référent HTTP et par API"
        retenues = [f for f in base if any(fiches.correspond(d, {"source": "securite", "cle": ligne}) for d in f["declencheurs"])]
        self.assertTrue(retenues, "aucune fiche ne reconnaît la ligne Google")
        self.assertEqual({f["severite_type"] for f in retenues} & {"critique", "haute"}, set())
        critique = next(f for f in base if f["id"] == "secu-secret-dans-js-client")
        self.assertFalse(any(fiches.correspond(d, {"source": "securite", "cle": ligne}) for d in critique["declencheurs"]))

    def test_exemples_et_gabarits_jamais_en_rouge(self):
        sec = _section_secrets(_page("var a='AKIA" + "IOSFODNN7" + "EXAMPLE'; var b='sk_" + "live_" + "x" * 24 + "'; "
                                     "placeholder:'-----BEGIN RSA PRIVATE KEY-----'"))
        self.assertNotIn("❌", sec)
        self.assertIn("✅ aucun motif", sec)

    def test_cle_apres_un_echappement_json(self):
        self.assertIn("OpenAI : sk-proj-", _page('var j="{\\"k\\":\\"x\\"}\\n' + self.CLE + '";'))


def _chemin_sans_python(d):
    """Dossier de liens vers tous les outils de /usr/bin et /bin sauf python* : un PATH où python3 est introuvable."""
    bin_ = pathlib.Path(d, "bin")
    bin_.mkdir()
    for dossier in ("/usr/bin", "/bin"):
        for f in sorted(os.listdir(dossier)):
            if not f.startswith("python") and not (bin_ / f).exists():
                os.symlink(os.path.join(dossier, f), str(bin_ / f))
    return str(bin_)


class TestAnalyseDesSecretsEnEchec(unittest.TestCase):
    """Un contrôle de sécurité qui n'a pas pu regarder ne dit jamais « ✅ aucun motif » (revue T5, I1)."""
    CLE = TestSecretsV21.CLE
    MARQUE = "⚠️ analyse des secrets JS impossible"

    def verifier(self, md):
        sec = _section_secrets(md)
        self.assertIn(self.MARQUE, sec)
        self.assertNotIn("✅ aucun motif", sec)
        self.assertNotIn("❌ Motifs de secrets trouvés", sec)
        return sec

    def test_python3_introuvable(self):
        with tempfile.TemporaryDirectory() as d:
            md = _page("const k='" + self.CLE + "';", env_extra={"PATH": _chemin_sans_python(d)})
        self.assertIn("python3", self.verifier(md))

    def test_secrets_js_absent_a_cote_de_la_sonde(self):
        with tempfile.TemporaryDirectory() as d:
            seul = pathlib.Path(d, "security_probe.sh")
            seul.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            md = _page("const k='" + self.CLE + "';", script=seul)
        self.assertIn("secrets_js.py", self.verifier(md))

    def test_secrets_js_qui_plante(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "security_probe.sh").write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            pathlib.Path(d, "secrets_js.py").write_text("import sys\nsys.stderr.write('boom')\nsys.exit(3)\n", encoding="utf-8")
            md = _page("const k='" + self.CLE + "';", script=pathlib.Path(d, "security_probe.sh"))
        self.assertIn("code 3", self.verifier(md))

    def test_sortie_ascii_forcee_detecte_quand_meme(self):
        md = _page("const k='" + self.CLE + "';", env_extra={"PYTHONIOENCODING": "ascii", "LC_ALL": "C", "PYTHONUTF8": "0"})
        sec = _section_secrets(md)
        self.assertIn("OpenAI : sk-proj-", sec)
        self.assertNotIn("✅ aucun motif", sec)


if __name__ == "__main__":
    unittest.main()
