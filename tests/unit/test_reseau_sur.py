"""reseau_sur : aucune requête vers une adresse non publique, seulement http(s), redirections et cookies maîtrisés. Sans Internet."""
import gzip
import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import zlib
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ICI = pathlib.Path(__file__).resolve().parent
SCRIPTS = ICI.parents[1] / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ICI))
import crawl_site  # noqa: E402
import reseau_sur  # noqa: E402
from site_local import HTML, SiteLocal  # noqa: E402

PUBLIC = "93.184.216.34"


def resolveur(table, appels=None):
    """Faux résolveur DNS : table {hôte: [adresses]} ; un hôte absent échoue comme un nom inexistant."""
    def r(hote, port=None):
        if appels is not None:
            appels.append(hote)
        if hote in table:
            return table[hote]
        raise socket.gaierror(-2, "Name or service not known")
    return r


def aucun_dns(hote, port=None):
    raise AssertionError("aucune résolution attendue pour " + hote)


class TestAdressePublique(unittest.TestCase):
    def test_formes_litterales_et_obfusquees_refusees_sans_resolution(self):
        for h in ["127.0.0.1", "localhost", "LOCALHOST.", "localhost.", "ｌｏｃａｌｈｏｓｔ", "①②⑦.⓪.⓪.①", "１２７.０.０.１", "2130706433",
                  "127.1", "0x7f.1", "0x7f000001", "0177.0.0.1", "017700000001", "[::1]", "::1", "::ffff:127.0.0.1", "[::ffff:7f00:1]",
                  "169.254.169.254", "10.0.0.5", "192.168.1.1", "172.16.0.1", "100.64.0.1", "0.0.0.0", "fe80::1", "fc00::1", "fe80::1%eth0",
                  "x.internal", "a.local", "b.localhost", "intranet", "foo.localdomain", "imprimante.lan", "", None, "  ", "a b.fr"]:
            with self.subTest(h=h):
                self.assertFalse(reseau_sur.adresse_publique(h, resoudre=aucun_dns))

    def test_nom_qui_resout_vers_une_adresse_privee(self):
        r = resolveur({"127.0.0.1.nip.io": ["127.0.0.1"], "mixte.fr": [PUBLIC, "10.0.0.1"], "v6.fr": ["::1"], "mappe.fr": ["::ffff:10.0.0.1"],
                       "nat64.fr": ["64:ff9b::7f00:1"]})
        for h in ("127.0.0.1.nip.io", "mixte.fr", "v6.fr", "mappe.fr", "nat64.fr"):
            with self.subTest(h=h):
                self.assertFalse(reseau_sur.adresse_publique(h, resoudre=r))

    def test_hotes_publics(self):
        r = resolveur({"exemple.fr": [PUBLIC], "v6.exemple.fr": ["2606:4700:4700::1111"], "double.fr": [PUBLIC, "2606:4700:4700::1111"],
                       "xn--bcher-kva.de": [PUBLIC]})
        for h in ("exemple.fr", "EXEMPLE.fr.", "v6.exemple.fr", "double.fr", "bücher.de", "8.8.8.8", "[2606:4700:4700::1111]"):
            with self.subTest(h=h):
                self.assertTrue(reseau_sur.adresse_publique(h, resoudre=r))

    def test_nom_introuvable_nest_pas_public_mais_se_distingue_dune_adresse_privee(self):
        r = resolveur({})
        self.assertFalse(reseau_sur.adresse_publique("nx.exemple.fr", resoudre=r))
        self.assertEqual(reseau_sur.classer_hote("nx.exemple.fr", resoudre=r), "introuvable")
        self.assertEqual(reseau_sur.classer_hote("127.0.0.1", resoudre=r), "privee")
        self.assertEqual(reseau_sur.classer_hote("exemple.fr", resoudre=resolveur({"exemple.fr": [PUBLIC]})), "publique")

    def test_exemption_par_hote_exact(self):
        r = resolveur({"banc.test": ["10.1.2.3"], "autre.test": ["10.1.2.4"]})
        self.assertEqual(reseau_sur.classer_hote("banc.test", resoudre=r, prive_ok={"banc.test"}), "publique")
        self.assertEqual(reseau_sur.classer_hote("BANC.test.", resoudre=r, prive_ok={"banc.test"}), "publique")
        self.assertEqual(reseau_sur.classer_hote("autre.test", resoudre=r, prive_ok={"banc.test"}), "privee")
        self.assertEqual(reseau_sur.classer_hote("127.0.0.2", resoudre=r, prive_ok={"127.0.0.1"}), "privee")
        self.assertEqual(reseau_sur.classer_hote("autre.test", resoudre=r, prive_ok=reseau_sur.TOUS), "publique")


class TestAdresseRequete(unittest.TestCase):
    def test_chemin_et_hote_non_ascii(self):
        f = reseau_sur.adresse_requete
        self.assertEqual(f("https://fr.wikipedia.org/wiki/Café"), "https://fr.wikipedia.org/wiki/Caf%C3%A9")
        self.assertEqual(f("https://bücher.de/x?q=é&a=1"), "https://xn--bcher-kva.de/x?q=%C3%A9&a=1")
        self.assertEqual(f("http://日本語.jp:8080/"), "http://xn--wgv71a119e.jp:8080/")
        self.assertEqual(f("https://a.org/déjà%20encodé/(x)?t=1,2;3"), "https://a.org/d%C3%A9j%C3%A0%20encod%C3%A9/(x)?t=1,2;3")  # idempotent sur l'existant
        self.assertEqual(f(f("https://fr.wikipedia.org/wiki/Café")), "https://fr.wikipedia.org/wiki/Caf%C3%A9")
        self.assertEqual(f("http://[2606:4700::1111]:81/a"), "http://[2606:4700::1111]:81/a")
        self.assertEqual(f("https://a.org"), "https://a.org/")

    def test_adresses_inutilisables(self):
        for u in ("file:///etc/hosts", "ftp://a.org/", "data:text/plain,x", "http://", "https:///x", "javascript:alert(1)", "", None):
            self.assertIsNone(reseau_sur.adresse_requete(u), u)


class TestOpener(unittest.TestCase):
    def test_seulement_http_et_https(self):
        o = reseau_sur._opener()
        noms = {type(h).__name__ for h in o.handlers}
        for interdit in ("FileHandler", "FTPHandler", "DataHandler", "CacheFTPHandler", "HTTPCookieProcessor", "HTTPRedirectHandler"):
            self.assertNotIn(interdit, noms)
        for h in o.handlers:
            self.assertNotIsInstance(h, (urllib.request.FileHandler, urllib.request.FTPHandler, urllib.request.DataHandler))
        self.assertIn("HTTPHandler", noms)
        self.assertIn("HTTPSHandler", noms)


class Serveur:
    """Serveur local qui enregistre ce qu'il reçoit et répond selon routes {chemin: (statut, {en-têtes})}."""

    def __init__(self, routes):
        self.vus, self.routes = [], routes

    def __enter__(self):
        s = self

        class H(BaseHTTPRequestHandler):
            def _r(self):
                s.vus.append((self.command, self.path, self.headers.get("Cookie"), self.headers.get("Authorization")))
                statut, ent = s.routes.get(self.path, (200, {}))
                self.send_response(statut)
                for k, v in ent.items():
                    self.send_header(k, v.replace("@@BASE@@", s.base))
                self.send_header("Content-Length", "0")
                self.end_headers()
            do_GET = do_HEAD = _r

            def log_message(self, *a):
                pass
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:{0}".format(self.srv.server_port)
        return self

    def __exit__(self, *e):
        self.srv.shutdown()
        self.srv.server_close()


class TestOuvrir(unittest.TestCase):
    def test_schemas_non_http_refuses_des_la_premiere_requete(self):
        for u in ("file:///etc/hosts", "ftp://127.0.0.1:1/x", "data:text/plain;base64,QQ==", "gopher://a.org/"):
            with self.subTest(u=u):
                r = reseau_sur.ouvrir(u, method="HEAD", prive_ok=reseau_sur.TOUS)
                self.assertEqual((r["status"], r["refus"]), (0, "schema"))
                self.assertEqual(r["body"], b"")

    def test_redirection_vers_file_refusee(self):
        with Serveur({"/f": (302, {"Location": "file:///etc/hosts"}), "/d": (302, {"Location": "data:text/html,x"}),
                      "/t": (301, {"Location": "ftp://127.0.0.1:21/x"})}) as s:
            for chemin in ("/f", "/d", "/t"):
                r = reseau_sur.ouvrir(s.base + chemin, method="HEAD", prive_ok={"127.0.0.1"})
                self.assertEqual((r["status"], r["refus"]), (0, "schema"), chemin)
                self.assertNotIn("No such file", r["error"])
                self.assertNotIn("hosts", r["error"])

    def test_redirection_vers_une_adresse_privee_refusee_sans_requete(self):
        with Serveur({}) as interne, Serveur({}) as s:
            s.routes["/r"] = (302, {"Location": "http://localhost:{0}/interne".format(interne.srv.server_port)})
            s.routes["/v6"] = (302, {"Location": "http://[::1]:{0}/interne".format(interne.srv.server_port)})
            s.routes["/dec"] = (302, {"Location": "http://2130706433:{0}/interne".format(interne.srv.server_port)})
            s.routes["/meta"] = (302, {"Location": "http://169.254.169.254/latest/meta-data/"})
            for chemin in ("/r", "/v6", "/dec", "/meta"):
                r = reseau_sur.ouvrir(s.base + chemin, method="HEAD", prive_ok={"127.0.0.1"})
                self.assertEqual((r["status"], r["refus"]), (0, "adresse_privee"), chemin)
            self.assertEqual(interne.vus, [])

    def test_premier_hote_prive_refuse_sans_exemption(self):
        with Serveur({}) as s:
            r = reseau_sur.ouvrir(s.base + "/", method="HEAD")
            self.assertEqual((r["status"], r["refus"]), (0, "adresse_privee"))
            self.assertEqual(s.vus, [])
            self.assertEqual(reseau_sur.ouvrir(s.base + "/", method="HEAD", prive_ok={"127.0.0.1"})["status"], 200)

    def test_cinq_redirections_au_plus_aucun_cookie_ni_autorisation_inter_hotes(self):
        with Serveur({}) as s:
            for i in range(10):
                s.routes["/b{0}".format(i)] = (302, {"Location": "/b{0}".format(i + 1), "Set-Cookie": "session=abc; Path=/"})
            r = reseau_sur.ouvrir(s.base + "/b0", method="HEAD", prive_ok={"127.0.0.1"},
                                  extra_headers={"Cookie": "a=b", "Authorization": "Bearer x"})
        self.assertEqual(len(s.vus), 6)  # 5 redirections suivies
        self.assertEqual((r["status"], r["refus"]), (-1, None))
        self.assertEqual({v[2] for v in s.vus}, {None})  # jamais de Cookie, même demandé

    def test_hote_introuvable_rend_l_erreur_dns_sans_connexion(self):
        r = reseau_sur.ouvrir("http://nx.exemple.fr/", method="HEAD", resoudre=resolveur({}))
        self.assertEqual((r["status"], r["refus"]), (0, None))
        self.assertIn("Name or service not known", r["error"])

    def test_echeance_depassee(self):
        r = reseau_sur.ouvrir("http://exemple.fr/", method="HEAD", resoudre=resolveur({"exemple.fr": [PUBLIC]}), echeance=0)
        self.assertEqual(r["status"], 0)
        self.assertIn("délai", r["error"])


class TestCrawlSiteFetch(unittest.TestCase):
    """C3 : crawl_site.fetch ne lit jamais un fichier local, même si le site audité le demande par une redirection."""

    def test_le_site_audite_ne_peut_pas_faire_lire_un_fichier(self):
        for cible in ("file:///etc/hosts", "ftp://127.0.0.1:1/x", "data:text/html,x"):
            with SiteLocal({"/": (302, {"Location": cible}, ""), "/ok": (200, HTML, "ok")}) as site:
                r = crawl_site.fetch(site.url, timeout=5)
                self.assertEqual(r["status"], 0, cible)
                self.assertEqual(r["body"], b"")
                self.assertEqual(r["refus"], "schema")
                self.assertEqual(crawl_site.fetch(site.base + "/ok", timeout=5)["status"], 200)

    def test_fetch_direct_d_un_fichier_refuse(self):
        r = crawl_site.fetch("file:///etc/hosts", timeout=5)
        self.assertEqual((r["status"], r["body"]), (0, b""))

    def test_redirection_du_site_vers_une_adresse_interne_refusee(self):
        with SiteLocal({"/": (200, HTML, "ok")}) as interne, SiteLocal({}) as site:
            site.routes["/"] = (302, {"Location": "http://localhost:{0}/".format(interne.srv.server_port)}, "")
            r = crawl_site.fetch(site.url, timeout=5)
            self.assertEqual((r["status"], r["refus"]), (0, "adresse_privee"))
            self.assertEqual(interne.requetes, [])

    def test_le_site_audite_local_reste_atteignable_et_ses_redirections_internes_aussi(self):
        with SiteLocal({"/a": (302, {"Location": "/b"}, ""), "/b": (200, HTML, "ok")}) as site:
            r = crawl_site.fetch(site.base + "/a", timeout=5)
            self.assertEqual((r["status"], r["final_url"]), (200, site.base + "/b"))


class TestDecompressionBornee(unittest.TestCase):
    """Bombe gzip : quelques dizaines de Ko compressés, des dizaines de Mo décompressés."""

    def bombe(self, octets=30_000_000):
        return gzip.compress(b"a" * octets, 9)

    def test_gzip_borne_et_signale(self):
        b = self.bombe()
        self.assertLess(len(b), 100_000)
        sortie, tronque = reseau_sur.decompresser_borne(b, "gzip", 1_000_000)
        self.assertEqual((len(sortie), tronque), (1_000_000, True))

    def test_deflate_zlib_et_deflate_brut_bornes(self):
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            c = zlib.compressobj(9, zlib.DEFLATED, wbits)
            b = c.compress(b"b" * 20_000_000) + c.flush()
            sortie, tronque = reseau_sur.decompresser_borne(b, "deflate", 500_000)
            self.assertEqual((len(sortie), tronque), (500_000, True), wbits)

    def test_sous_la_limite_rien_n_est_perdu(self):
        texte = "<html>" + "é" * 1000 + "</html>"
        for enc, comp in (("gzip", gzip.compress(texte.encode())), ("deflate", zlib.compress(texte.encode()))):
            self.assertEqual(reseau_sur.decompresser_borne(comp, enc, 10_000), (texte.encode(), False))
        pile = gzip.compress(b"x" * 1000)
        self.assertEqual(reseau_sur.decompresser_borne(pile, "gzip", 1000), (b"x" * 1000, False))  # pile à la limite : pas tronqué
        self.assertEqual(reseau_sur.decompresser_borne(gzip.compress(b"un ") + gzip.compress(b"deux"), "gzip", 100), (b"un deux", False))

    def test_flux_illisible_ou_encodage_inconnu_inchanges(self):
        self.assertEqual(reseau_sur.decompresser_borne(b"pas du gzip", "gzip", 100), (b"pas du gzip", False))
        self.assertEqual(reseau_sur.decompresser_borne(b"\x1b\x00", "br", 100), (b"\x1b\x00", False))
        self.assertEqual(reseau_sur.decompresser_borne(b"abc", None, 100), (b"abc", False))
        self.assertEqual(reseau_sur.decompresser_borne(b"", "gzip", 100), (b"", False))

    def test_crawl_site_decompress_borne(self):
        self.assertEqual(len(crawl_site._decompress(self.bombe(60_000_000), "gzip")), reseau_sur.LIMITE_SITEMAP)

    def test_fetch_borne_la_page_et_survit(self):
        corps = self.bombe()
        with SiteLocal({"/": (200, {"Content-Type": "text/html; charset=utf-8", "Content-Encoding": "gzip"}, corps)}) as site:
            r = crawl_site.fetch(site.url, timeout=20)
        self.assertEqual(r["status"], 200)
        self.assertLessEqual(len(r["body"]), reseau_sur.LIMITE_HTML)
        self.assertTrue(r["tronque"])

    def test_le_crawl_survit_a_une_bombe(self):
        # servie en text/plain : la lecture du corps (décompression bornée) est ce qui est testé, pas l'analyse HTML d'un texte géant
        bombe = gzip.compress(b"a" * 40_000_000, 9)
        with SiteLocal({"/": (200, {"Content-Type": "text/plain; charset=utf-8", "Content-Encoding": "gzip"}, bombe)}) as site, \
                tempfile.TemporaryDirectory() as d:
            subprocess.run([sys.executable, str(SCRIPTS / "crawl_site.py"), site.url, "--out", d, "--delay", "0", "--max-pages", "2",
                            "--liens-externes", "0", "--ressources", "0"], check=True, capture_output=True, timeout=240)
            pages = json.loads(pathlib.Path(d, "pages.json").read_text(encoding="utf-8"))["pages"]
        self.assertEqual(pages[0]["final_status"], 200)


if __name__ == "__main__":
    unittest.main()
