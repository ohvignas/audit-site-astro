"""Aucun secret dans les sorties du crawl : jeton, clé d'API, identifiant de session, identifiants d'URL (user:pass@).

Règle de sécurité : une adresse qui entre dans une signature, un exemple, issues.json, pages.json, pages.csv ou summary.md ne porte
ni requête secrète, ni fragment, ni paramètre de matrice, ni %3F / %23 encodés, ni identifiants. Les secrets de ces tests sont
tous des valeurs fictives reconnaissables (SECRET…, AIzaSy…) : le test échoue si l'une d'elles apparaît dans une sortie.
"""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ICI = pathlib.Path(__file__).resolve().parent
SCRIPTS = ICI.parents[1] / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ICI))
import html_observateurs as ho  # noqa: E402
from site_local import HTML, SiteLocal  # noqa: E402

CLE_API = "AIzaSyA1234567890abcdefghijklmnop"
SECRETS = ("SECRETTOKEN1", "SECRETSESSION2", "SECRETENC3", "SECRETPASS4", "SECRETSIG5", CLE_API, "AIzaSy", "SECRETEXT6", "SECRETNOM7",
           "SECRETALT8", "SECRETFUITE9", "SECRETTXT10", "SECRETMAIL11", "SECRETKEY12", "SECRETSVG13", "SECRETCANON14",
           "SECRETSM15", "SECRETREDIR16", "SECRETFRAG17", "SECRETIFRAME18", "SECRETLABEL19", "SECRETHEAD20")
# Formes qu'aucune sortie ne doit contenir, même sans valeur secrète derrière
FORMES = ("jsessionid", "%3Ftoken", "%3ftoken", "user:SECRET", "key=AIza", "sig=SECRET", "token=SECRET", "#SECRET", "access_token=")

PAGE_HTML = """<html lang='fr'><head><meta name='viewport' content='width=device-width, user-scalable=no'>
<title>Titre de test suffisamment long</title>{tete}</head><body><main>{corps}</main></body></html>"""


def page(corps, tete=""):
    return PAGE_HTML.format(corps=corps, tete=tete)


# Corps qui met un secret dans chaque endroit où un module du crawl écrit une adresse ou un texte
CORPS_MODULES = (
    '<a href="/s?token=SECRETNOM7#SECRETFRAG17"><svg aria-hidden="true"><path d="M0 0"/></svg></a>'            # a11y_noms
    '<img src="/i.png" alt="https://cdn.test/sig=SECRETALT8/photo.png">'                                              # a11y_textes
    '<iframe src="https://user:SECRETPASS4@embed.test/carte;jsessionid=SECRETSESSION2?key=' + CLE_API + '"></iframe>'  # a11y_structure
    '<iframe src="//embed.test/e%3Ftoken%3DSECRETENC3#SECRETFRAG17"></iframe>'
    '<a href="/f?id=undefined&token=SECRETFUITE9">fiche</a><p>Prix : undefined https://x.test/p?token=SECRETTXT10</p>'  # fuites_rendu
    '<a href="mailto:john.doe@example.com?subject=SECRETMAIL11">écrire</a>'                                       # contenu_demo
    '<p>Lorem ipsum dolor sit amet, key=SECRETKEY12 consectetur</p>'
    '<svg class="icone bg-[url(https://cdn.test/i.svg?sig=SECRETSVG13)]" viewBox="0 0 24 24" fill="none" width="24" height="24">'
    '<path d="M5 12h14"/></svg>'                                                                                  # a11y_svg
    '<span aria-label="Voir https://x.test/a?token=SECRETLABEL19">★</span>')


class TestOutilsAdresses(unittest.TestCase):
    def test_url_sans_secret(self):
        cas = {
            "https://user:SECRETPASS4@ex.fr:8443/a/b;jsessionid=SECRETSESSION2?token=SECRETTOKEN1#SECRETFRAG17": "https://ex.fr:8443/a/b",
            "https://ex.fr/a%3Ftoken%3DSECRETENC3": "https://ex.fr/a",
            "https://ex.fr/a%253Ftoken%253DSECRETENC3": "https://ex.fr/a",
            "https://ex.fr/a%23SECRETFRAG17": "https://ex.fr/a",
            "//cdn.test/e?token=SECRETTOKEN1": "//cdn.test/e",
            "/carte?cle=SECRETTOKEN1#x": "/carte",
            "/carte;jsessionid=SECRETSESSION2": "/carte",
            "HTTPS://EX.FR/Page?x=1": "https://ex.fr/Page",
            "data:text/html,SECRETTOKEN1": "data:", "javascript:alert('SECRETTOKEN1')": "javascript:",
            "mailto:a@ex.fr?subject=SECRETMAIL11&body=x": "mailto:a@ex.fr",
            "#access_token=SECRETTOKEN1": "#", "?token=SECRETTOKEN1": "", "": "", None: "",
            "https://ex.fr/hooks/T0AAAAAAA/B0BBBBBB/AbCdEfGhIjKlMnOpQrStUv12": "https://ex.fr/hooks/T0AAAAAAA/B0BBBBBB/…",
            "https://ex.fr/formation-no-code-2024-complete/index.4f3a9c.js": "https://ex.fr/formation-no-code-2024-complete/index.4f3a9c.js",
            "http://[invalide": "adresse illisible",
        }
        for brut, attendu in cas.items():
            with self.subTest(brut):
                self.assertEqual(ho.url_sans_secret(brut), attendu)

    def test_sans_schema_et_longueur_bornee(self):
        self.assertEqual(ho.url_sans_secret("https://user:p@ex.fr/a?k=v", avec_schema=False), "ex.fr/a")
        longue = ho.url_sans_secret("https://ex.fr/" + "a" * 500)
        self.assertEqual(len(longue), 100)
        self.assertTrue(longue.endswith("…"))
        self.assertEqual(len(ho.url_sans_secret("https://ex.fr/" + "a" * 500, 40)), 40)

    def test_url_de_page_garde_les_parametres_sans_risque(self):
        self.assertEqual(ho.url_page_publique("https://ex.fr/p?page=2&token=SECRETTOKEN1&tab=prix#SECRETFRAG17"), "https://ex.fr/p?page=2&tab=prix")
        self.assertEqual(ho.url_page_publique("/p?q=paris&Api_Key=SECRETKEY12&accessKey=SECRETKEY12&sig=SECRETSIG5&sid=SECRETSESSION2"
                                              "&auth=SECRETTOKEN1&code=SECRETTOKEN1&password=SECRETTOKEN1&session=SECRETSESSION2"
                                              "&signature=SECRETSIG5&X-Amz-Signature=SECRETSIG5&cle=SECRETKEY12&keyword=no-code"),
                         "/p?q=paris&keyword=no-code")
        # valeur qui ressemble à une clé, ou requête encodée dans une valeur
        self.assertEqual(ho.url_page_publique("https://ex.fr/p?a=" + CLE_API + "&b=" + "0123456789abcdef" * 2 + "&c=ok"), "https://ex.fr/p?c=ok")
        self.assertEqual(ho.url_page_publique("https://ex.fr/p?next=%2Flogin%3Ftoken%3DSECRETTOKEN1&d=1"), "https://ex.fr/p?d=1")
        self.assertEqual(ho.url_page_publique("https://user:SECRETPASS4@ex.fr/p;jsessionid=SECRETSESSION2?tab=1"), "https://ex.fr/p?tab=1")

    def test_texte_sans_secret(self):
        t = ho.texte_sans_secret("Voir https://ex.fr/p?token=SECRETTOKEN1, et api_key=SECRETKEY12 puis " + CLE_API + " (ok) fill=none")
        self.assertEqual(t, "Voir https://ex.fr/p, et api_key=… puis … (ok) fill=none")
        self.assertEqual(ho.texte_sans_secret("Prix : 49 € — user-scalable=no"), "Prix : 49 € — user-scalable=no")

    def test_assainir_sortie_copie_sans_modifier_l_original(self):
        original = {"https://a.fr/x?token=SECRETTOKEN1": 200,
                    "u": ["https://a.fr/y?sig=SECRETSIG5&page=3", {"img_srcs": ["/i.png?sig=SECRETSIG5"]}], "t": "texte", "n": 3, "ok": True}
        copie = ho.assainir_sortie(original)
        self.assertEqual(copie, {"https://a.fr/x": 200, "u": ["https://a.fr/y?page=3", {"img_srcs": ["/i.png"]}], "t": "texte", "n": 3, "ok": True})
        self.assertIn("SECRETTOKEN1", json.dumps(original))


class TestModules(unittest.TestCase):
    """Sortie brute de chaque module (obs de pages.json) puis constats issues() : aucune valeur secrète, aucune forme dangereuse."""

    @classmethod
    def setUpClass(cls):
        html = page(CORPS_MODULES, "<title>x</title><meta name='description' content='Voir https://x.test/d?token=SECRETHEAD20'>")
        cls.url = "https://ex.fr/p?token=SECRETTOKEN1&page=2"
        cls.obs = ho.analyser(html, {}, cls.url)
        pages = {cls.url: {"obs": cls.obs}, "https://ex.fr/q;jsessionid=SECRETSESSION2": {"obs": cls.obs}}
        cls.constats = {}

        def add(cle, libelle, severite, exemple=None, n=1, domaine=None):
            cls.constats.setdefault(cle, []).append(exemple)

        ho.issues(pages, add, {"meta": {}})

    def verifier(self, brut):
        for secret in SECRETS:
            self.assertNotIn(secret, brut)
        for forme in FORMES:
            self.assertNotIn(forme, brut)

    def test_aucun_module_ne_laisse_passer_un_secret(self):
        for nom, resultat in self.obs.items():
            with self.subTest(nom):
                self.assertNotIn("erreur", resultat)
                self.verifier(json.dumps(resultat, ensure_ascii=False))

    def test_constats_sans_secret_y_compris_les_pages_exemples(self):
        brut = json.dumps(self.constats, ensure_ascii=False)
        self.verifier(brut)
        self.assertIn("https://ex.fr/p?page=2", brut)  # l'URL de la page garde son paramètre sans risque

    def test_les_modules_ont_bien_detecte_les_defauts(self):
        # sans cela le test précédent passerait pour une raison triviale (aucune sortie)
        for cle in ("lien_sans_nom", "iframe_sans_titre", "fuite_rendu", "contenu_demo", "svg_non_masque", "aria_label_interdit",
                    "alt_suspect"):
            self.assertIn(cle, self.constats)
        signatures = json.dumps(self.constats["iframe_sans_titre"], ensure_ascii=False)
        self.assertIn("embed.test/carte", signatures)
        self.assertEqual([e["signature"] for e in self.constats["alt_suspect"]], ["https://cdn.test/sig=… (nom de fichier)"])

    def test_signature_de_lien_sans_requete(self):
        sig = [e["signature"] for e in self.constats["lien_sans_nom"]]
        self.assertEqual(sig, ['<a href="/s"> contenu : svg masqué, path masqué'])

    def test_fuite_en_parametre_garde_le_parametre_fautif_seulement(self):
        sig = " ".join(e["signature"] for e in self.constats["fuite_rendu"])
        self.assertIn("undefined — href /f?id=undefined", sig)
        self.assertNotIn("SECRETFUITE9", sig)

    def test_module_qui_oublie_le_helper_ne_fait_pas_fuiter(self):
        class Etourdi(ho.Observateur):
            def debut(self, noeud, pile):
                if noeud["tag"] == "a":
                    self.href = noeud["a"].get("href", "")

            def resultat(self):
                return {"liens": [{"signature": "https://ex.fr/x?token=SECRETTOKEN1&page=2#SECRETFRAG17 " + self.href, "n": 1}]}

        class Mod:
            Observateur = Etourdi

        sortie = ho.analyser('<a href="https://ex.fr/y?key=' + CLE_API + '">x</a>', {}, "https://ex.fr/", modules=[("etourdi", Mod)])
        brut = json.dumps(sortie)
        for secret in ("SECRETTOKEN1", "SECRETFRAG17", CLE_API):
            self.assertNotIn(secret, brut)
        self.assertIn("https://ex.fr/x?page=2", brut)


def routes_crawl():
    """Site local dont chaque lien, canonical, redirection et sitemap porte un secret (valeurs fictives)."""
    tete_canonique = "<link rel='canonical' href='@@HOTE_AUTH@@/p?token=SECRETCANON14'>"
    return {
        "/": (200, HTML, page(
            '<a href="/p?token=SECRETTOKEN1&page=2">p</a> <a href="/q;jsessionid=SECRETSESSION2">q</a> '
            '<a href="/r%3Ftoken%3DSECRETENC3">r</a> <a href="/go">go</a> <a href="/m">m</a> <a href="/n">n</a> '
            '<a href="https://autre.test/x?token=SECRETEXT6&id=null">externe</a><img src="/i.png?sig=SECRETSIG5" alt="x">')),
        "/p": (200, HTML, page(CORPS_MODULES + "<p>Page de test avec un jeton dans l'adresse.</p>")),
        "/q": (200, HTML, page("<p>Page avec paramètre de matrice dans l'adresse.</p>")),
        "/r": (200, HTML, page("<p>Page avec requête encodée dans le chemin.</p>")),
        "/go": (302, {"Location": "/p?token=SECRETREDIR16&tab=prix"}, ""),
        "/m": (200, HTML, page("<p>Canonical avec identifiants.</p>", tete_canonique)),
        "/n": (200, HTML, page("<p>Image et lien.</p>", "<link rel='alternate' hreflang='en' href='/n?sig=SECRETSIG5'>")),
        "/robots.txt": (200, {"Content-Type": "text/plain"}, "User-agent: *\nDisallow: /secret?token=SECRETHEAD20\nSitemap: @@BASE@@/sitemap.xml\n"),
        "/sitemap.xml": (200, {"Content-Type": "application/xml"},
                         '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                         "<url><loc>@@BASE@@/p?token=SECRETSM15</loc></url><url><loc>@@BASE@@/absent?token=SECRETSM15</loc></url></urlset>"),
    }


class TestCrawlSansSecret(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        routes = routes_crawl()
        prefixes = {"/q": routes["/q"], "/r": routes["/r"]}  # chemins avec « ; » et « %3F » : routes exactes impossibles
        with SiteLocal(routes, prefixes) as site:
            auth = site.base.replace("http://", "http://user:SECRETPASS4@")
            for k, (st, h, corps) in list(site.routes.items()):
                if isinstance(corps, str):
                    site.routes[k] = (st, h, corps.replace("@@HOTE_AUTH@@", auth))
            r = subprocess.run([sys.executable, str(SCRIPTS / "crawl_site.py"), site.url, "--out", cls.tmp.name, "--delay", "0",
                                "--max-pages", "30", "--timeout", "5", "--liens-externes", "0", "--ressources", "0"],
                               capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr[-2000:]
        cls.stderr = r.stderr
        cls.sorties = {nom: pathlib.Path(cls.tmp.name, nom).read_text(encoding="utf-8")
                       for nom in ("pages.json", "issues.json", "pages.csv", "summary.md")}
        cls.pages = json.loads(cls.sorties["pages.json"])
        cls.issues = json.loads(cls.sorties["issues.json"])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_aucune_sortie_ne_contient_de_secret(self):
        sorties = dict(self.sorties, stderr=self.stderr)
        for nom, brut in sorties.items():
            with self.subTest(nom):
                for secret in SECRETS:
                    self.assertNotIn(secret, brut)
                for forme in FORMES:
                    self.assertNotIn(forme, brut)
                for encode in ("%3Ftoken", "%3ftoken", "%253F", "%23SECRET"):
                    self.assertNotIn(encode, brut)

    def test_le_crawl_a_vu_les_pages_a_secret(self):
        # sans cela le test précédent passerait pour une raison triviale (pages jamais crawlées)
        urls = [p["url"] for p in self.pages["pages"]]
        self.assertGreaterEqual(len(urls), 6, urls)
        self.assertTrue(any("/q" in u for u in urls), urls)
        self.assertTrue(any("/m" in u for u in urls), urls)
        self.assertTrue(any(u.endswith("/p?page=2") for u in urls), urls)  # URL de page : le paramètre sans risque reste
        for it in ("lien_sans_nom", "fuite_rendu", "iframe_sans_titre", "contenu_demo"):
            self.assertIn(it, self.issues)

    def test_canonical_avec_identifiants_nettoyee(self):
        ex = json.dumps(self.issues.get("canonical_other", {}).get("examples", []))
        self.assertIn("/p", ex)
        self.assertNotIn("user", ex)

    def test_redirection_vers_une_url_a_jeton(self):
        pages = {p["url"]: p for p in self.pages["pages"]}
        go = next(p for u, p in pages.items() if u.endswith("/go"))
        self.assertTrue(go["final_url"].endswith("/p?tab=prix"), go["final_url"])

    def test_les_constats_des_modules_gardent_leurs_signatures_utiles(self):
        ex = json.dumps(self.issues["iframe_sans_titre"]["examples"], ensure_ascii=False)
        self.assertIn("embed.test/carte", ex)
        self.assertIn("embed.test/e", ex)
        self.assertEqual([e["signature"] for e in self.issues["lien_sans_nom"]["examples"]], ['<a href="/s"> contenu : svg masqué, path masqué'])


if __name__ == "__main__":
    unittest.main()
