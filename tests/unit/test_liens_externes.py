import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ICI = pathlib.Path(__file__).resolve().parent
SCRIPTS = ICI.parents[1] / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ICI))
import crawl_site  # noqa: E402
import html_observateurs as ho  # noqa: E402
import liens_externes  # noqa: E402
from site_local import HTML, SiteLocal  # noqa: E402


PUBLIC = "93.184.216.34"


def dns(table=None, appels=None):
    """Faux résolveur DNS (aucun réseau) : « nx… » n'existe pas, « interne… » vise 10.0.0.9, le reste est public ; table l'emporte."""
    table = table or {}

    def r(hote, port=None):
        if appels is not None:
            appels.append(hote)
        if hote in table:
            v = table[hote]
            if isinstance(v, Exception):
                raise v
            if callable(v):
                return v()
            return v
        if hote.startswith("nx"):
            raise socket.gaierror(-2, "Name or service not known")
        return ["10.0.0.9"] if hote.startswith("interne") else [PUBLIC]
    return r


ERREUR_DNS = "<urlopen error [Errno -2] Name or service not known>"


def nv(total=0, plafond=0, budget=0, privee=0, reseau=0, invalide=0):
    return {"total": total, "par_plafond": plafond, "par_budget": budget, "par_adresse_privee": privee,
            "par_reseau_indisponible": reseau, "par_adresse_invalide": invalide}


def constats(pages, ctx):
    """issues() du module : {clé: [exemples]}."""
    recus = {}
    liens_externes.issues(pages, lambda cle, libelle, sev, ex=None, **kw: recus.setdefault(cle, []).append(ex), ctx)
    return recus


def faux(rep):
    """Faux fetch (aucun réseau) : rep(url, method, kw) -> dict de réponse ; enregistre chaque appel."""
    appels = []

    def fetch(u, timeout=20, method="GET", max_bytes=8_000_000, ua=None, extra_headers=None):
        appels.append({"url": u, "method": method, "ua": ua, "extra": extra_headers, "t": time.monotonic(), "timeout": timeout})
        r = rep(u, method)
        return r if isinstance(r, dict) else {"status": r, "error": None}
    fetch.appels = appels
    return fetch


def pages_de(*liens_par_page):
    """pages = {url_page: {"obs": {"liens_externes": {"externes": [...]}}}} dans l'ordre donné."""
    return {"https://ex.fr/p{0}".format(i): {"obs": {"liens_externes": {"externes": list(ls)}}} for i, ls in enumerate(liens_par_page)}


def ctx_de(fetch, **kw):
    ctx = {"fetch": fetch, "delai_externe": 0, "liens_externes_max": 300, "timeout": 5, "meta": {}, "resoudre": dns(),
           "delai_confirmation_dns": 0}
    ctx.update(kw)
    return ctx


class TestClassement(unittest.TestCase):
    def test_classer(self):
        c = liens_externes.classer
        self.assertEqual([c(404, None), c(410, None), c(0, "<urlopen error [Errno -2] Name or service not known>"),
                          c(0, "<urlopen error [Errno 8] nodename nor servname provided, or not known>")], ["casse"] * 4)
        self.assertEqual([c(403, None), c(429, None), c(999, None), c(503, None), c(0, "timed out"),
                          c(0, "Temporary failure in name resolution"), c(-1, "plus de 10 redirections")], ["a_verifier"] * 7)
        self.assertEqual([c(200, None), c(301, None)], [None, None])

    def test_defi_cloudflare_jamais_casse(self):
        self.assertEqual(liens_externes.classer(404, "défi Cloudflare"), "a_verifier")
        self.assertEqual(liens_externes.classer(403, "défi Cloudflare"), "a_verifier")


class TestObservateur(unittest.TestCase):
    def liens(self, html, url="https://www.ex.fr/page"):
        return ho.analyser(html, {}, url, modules=[("liens_externes", liens_externes)])["liens_externes"]["externes"]

    def test_externes_sans_fragment_ni_variantes_du_site(self):
        html = ('<a href="https://autre.org/a#haut">a</a><a href="https://autre.org/a#bas">a bis</a><a href="/local">l</a>'
                '<a href="https://ex.fr/x">www</a><a href="http://WWW.EX.FR/y">www</a><a href="mailto:a@b.fr">m</a>'
                '<a href="https://z.org/b" hidden>caché</a><a href="https://y.org/c">c</a>')
        self.assertEqual(self.liens(html), ["https://autre.org/a", "https://y.org/c"])

    def test_ordre_du_document_et_plafond_par_page(self):
        html = "".join('<a href="https://h{0}.org/">x</a>'.format(i) for i in (9, 1, 5))
        self.assertEqual(self.liens(html), ["https://h9.org/", "https://h1.org/", "https://h5.org/"])  # pas de tri alphabétique
        html = "".join('<a href="https://h{0}.org/">x</a>'.format(i) for i in range(250))
        self.assertEqual(len(self.liens(html)), 200)

    def test_aucun_secret_ni_identifiant_dans_les_liens_notes(self):
        html = '<a href="https://moi:mdp@autre.org/a?token=abcdef123456&page=2">a</a>'
        sortie = json.dumps(self.liens(html))
        self.assertNotIn("abcdef123456", sortie)
        self.assertNotIn("mdp", sortie)
        self.assertIn("autre.org/a", sortie)


class TestCrawl(unittest.TestCase):
    def test_liens_externes_du_site(self):
        externe = {"/ok": (200, HTML, "ok"), "/mort": (404, HTML, "non"), "/interdit": (403, HTML, "non")}
        with SiteLocal(externe) as autre:
            page = ('<html lang="fr"><head><title>Liens externes de test</title></head><body><main>'
                    '<a href="{0}/ok">ok</a> <a href="{0}/mort#x">mort</a> <a href="{0}/interdit">interdit</a>'
                    '<a href="http://nx.cobaye.invalid/ressource">absent</a> <a href="/local">local</a></main></body></html>').format(autre.base)
            with SiteLocal({"/": (200, HTML, page)}) as site, tempfile.TemporaryDirectory() as d:
                subprocess.run([sys.executable, str(SCRIPTS / "crawl_site.py"), site.url, "--out", d, "--delay", "0", "--max-pages", "3",
                                "--liens-externes", "10", "--delai-externe", "0", "--ressources", "0"], check=True, capture_output=True, timeout=180)
                issues = json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8"))
                meta = json.loads(pathlib.Path(d, "pages.json").read_text(encoding="utf-8"))["meta"]["modules"]
        self.assertEqual([e["lien"] for e in issues["external_broken"]["examples"]], [autre.base + "/mort", "http://nx.cobaye.invalid/ressource"])
        self.assertEqual([e["lien"] for e in issues["external_a_verifier"]["examples"]], [autre.base + "/interdit"])
        self.assertEqual(issues["external_broken"]["examples"][0]["liens_depuis"], [site.url])
        self.assertEqual(meta["liens_externes"], {"trouves": 4, "verifies": 4, "budget_atteint": False})
        self.assertEqual(meta["liens_externes_non_verifies"], nv())
        self.assertEqual(meta["liens_externes_reseau"], {"prouve": True, "reseau_indisponible": False, "dns_inexistants": 1})
        self.assertNotIn("external_non_verifie", issues)
        # HEAD d'abord, GET de repli sur 404 / 403, et un 404 confirmé par un second GET (seuls des GET concluent « cassé »)
        self.assertEqual(sorted(autre.requetes), ["/interdit", "/interdit", "/mort", "/mort", "/mort", "/ok"])

    def test_debit_par_hote(self):
        appels = []

        def faux_fetch(u, timeout=20, method="GET", max_bytes=8_000_000, ua=None, extra_headers=None):
            appels.append(time.monotonic())
            return {"status": 200, "error": None}
        pages = {"https://ex.fr/": {"obs": {"liens_externes": {"externes": ["https://a.org/1", "https://a.org/2", "https://a.org/3"]}}}}
        ctx = {"fetch": faux_fetch, "delai_externe": 0.3, "liens_externes_max": 10, "timeout": 5, "meta": {}, "resoudre": dns()}
        liens_externes.apres_crawl(pages, ctx)
        self.assertGreaterEqual(appels[-1] - appels[0], 0.55)

    def test_pause_aussi_entre_head_et_get_du_meme_hote(self):
        f = faux(lambda u, m: 405 if m == "HEAD" else 200)
        liens_externes.apres_crawl(pages_de(["https://a.org/1"]), ctx_de(f, delai_externe=0.3))
        self.assertEqual([a["method"] for a in f.appels], ["HEAD", "GET"])
        self.assertGreaterEqual(f.appels[1]["t"] - f.appels[0]["t"], 0.28)

    def test_pas_de_pause_entre_hotes_differents(self):
        f = faux(lambda u, m: 200)
        liens_externes.apres_crawl(pages_de(["https://a.org/", "https://b.org/", "https://c.org/"]), ctx_de(f, delai_externe=1.0))
        self.assertLess(f.appels[-1]["t"] - f.appels[0]["t"], 0.5)

    def test_budget_de_temps(self):  # pré-vol : sans budget, le délai de l'étape coupait le crawl et perdait tout
        def lent(u, timeout=20, method="GET", max_bytes=8_000_000, ua=None, extra_headers=None):
            time.sleep(0.3)
            return {"status": 200, "error": None}
        pages = {"https://ex.fr/": {"obs": {"liens_externes": {"externes": ["https://h{0}.org/".format(i) for i in range(10)]}}}}
        ctx = {"fetch": lent, "delai_externe": 0, "liens_externes_max": 300, "timeout": 5, "budget_reseau_s": 0.5, "meta": {}, "resoudre": dns()}
        liens_externes.apres_crawl(pages, ctx)
        m = ctx["meta"]["liens_externes"]
        self.assertTrue(m["budget_atteint"])
        self.assertLessEqual(m["verifies"], 3)
        self.assertEqual(ctx["meta"]["liens_externes_non_verifies"], nv(10 - m["verifies"], budget=10 - m["verifies"]))

    def test_la_pause_ne_depasse_pas_le_budget(self):
        f = faux(lambda u, m: 200)
        ctx = ctx_de(f, delai_externe=5.0, budget_reseau_s=0.5)
        t0 = time.monotonic()
        liens_externes.apres_crawl(pages_de(["https://a.org/1", "https://a.org/2"]), ctx)
        self.assertLess(time.monotonic() - t0, 2)
        self.assertEqual((ctx["meta"]["liens_externes"]["verifies"], ctx["meta"]["liens_externes"]["budget_atteint"]), (1, True))

    def test_plafond_et_priorite_par_nombre_de_pages(self):
        # pas de troncature alphabétique : les liens les plus liés d'abord, puis l'ordre de première apparition
        f = faux(lambda u, m: 200)
        pages = pages_de(["https://z.org/rare", "https://a.org/un"], ["https://z.org/rare", "https://m.org/trois"],
                         ["https://m.org/trois", "https://y.org/seul"], ["https://m.org/trois", "https://z.org/rare"])
        ctx = ctx_de(f, liens_externes_max=3)
        liens_externes.apres_crawl(pages, ctx)
        self.assertEqual([a["url"] for a in f.appels], ["https://z.org/rare", "https://m.org/trois", "https://a.org/un"])
        self.assertEqual(ctx["meta"]["liens_externes"], {"trouves": 4, "verifies": 3, "budget_atteint": False})
        self.assertEqual(ctx["meta"]["liens_externes_non_verifies"], nv(1, plafond=1))

    def test_ordre_de_premiere_apparition_a_egalite(self):
        f = faux(lambda u, m: 200)
        pages = pages_de(["https://z.org/1", "https://b.org/2"], ["https://a.org/3"])
        liens_externes.apres_crawl(pages, ctx_de(f))
        self.assertEqual([a["url"] for a in f.appels], ["https://z.org/1", "https://b.org/2", "https://a.org/3"])

    def test_get_apres_un_404_en_head(self):
        def head_404(u, timeout=20, method="GET", max_bytes=8_000_000, ua=None, extra_headers=None):
            return {"status": 404 if method == "HEAD" else 200, "error": None}
        pages = {"https://ex.fr/": {"obs": {"liens_externes": {"externes": ["https://a.org/x"]}}}}
        ctx = {"fetch": head_404, "delai_externe": 0, "liens_externes_max": 10, "timeout": 5, "meta": {}, "resoudre": dns()}
        liens_externes.apres_crawl(pages, ctx)
        self.assertEqual(ctx["externes"]["https://a.org/x"]["statut"], 200)

    def test_repli_get_avec_range_sur_405_et_501(self):
        for refus in (405, 501):
            f = faux(lambda u, m, refus=refus: refus if m == "HEAD" else 206)
            ctx = ctx_de(f)
            liens_externes.apres_crawl(pages_de(["https://a.org/x"]), ctx)
            self.assertEqual([a["method"] for a in f.appels], ["HEAD", "GET"])
            self.assertEqual(f.appels[1]["extra"], {"Range": "bytes=0-0"})
            self.assertIsNone(f.appels[0]["extra"])
            self.assertEqual(ctx["externes"]["https://a.org/x"]["statut"], 206)

    def test_un_404_reste_casse_seulement_si_le_get_le_confirme(self):
        f = faux(lambda u, m: 404)
        ctx = ctx_de(f)
        liens_externes.apres_crawl(pages_de(["https://a.org/x"]), ctx)
        self.assertEqual([a["method"] for a in f.appels], ["HEAD", "GET", "GET"])  # le second GET confirme
        self.assertEqual(liens_externes.classer(**{k: ctx["externes"]["https://a.org/x"][k] for k in ("statut", "erreur")}), "casse")

    def test_pas_de_get_apres_un_429(self):  # le serveur demande de ralentir : on ne le sollicite pas une seconde fois
        f = faux(lambda u, m: 429)
        liens_externes.apres_crawl(pages_de(["https://a.org/x"]), ctx_de(f))
        self.assertEqual([a["method"] for a in f.appels], ["HEAD"])

    def test_user_agent_honnete(self):
        f = faux(lambda u, m: 200)
        liens_externes.apres_crawl(pages_de(["https://a.org/x"]), ctx_de(f, ua_navigateur="Mozilla/5.0 (Macintosh) Chrome/128.0 Safari/537.36"))
        ua = f.appels[0]["ua"]
        self.assertIn("AuditSiteAstro", ua)
        self.assertNotIn("Chrome", ua)
        self.assertNotIn("Safari", ua)

    def test_timeout_court_et_borne_par_le_budget(self):
        f = faux(lambda u, m: 200)
        liens_externes.apres_crawl(pages_de(["https://a.org/x"]), ctx_de(f, timeout=60))
        self.assertLessEqual(f.appels[0]["timeout"], 8)

    def test_defi_cloudflare_et_delai_sont_a_verifier(self):
        f = faux(lambda u, m: {"status": 404, "error": None, "headers": {"cf-mitigated": "challenge"}} if "cf" in u else
                 {"status": 0, "error": "<urlopen error timed out>"})
        ctx = ctx_de(f)
        liens_externes.apres_crawl(pages_de(["https://cf.org/x", "https://lent.org/x"]), ctx)
        ajoutes = []
        liens_externes.issues({}, lambda cle, libelle, sev, ex=None, **kw: ajoutes.append((cle, ex["lien"])), ctx)
        self.assertEqual(sorted(ajoutes), [("external_a_verifier", "https://cf.org/x"), ("external_a_verifier", "https://lent.org/x")])

    def test_issues_sans_secret_et_domaine(self):
        f = faux(lambda u, m: 404)
        ctx = ctx_de(f)
        pages = {"https://ex.fr/p?token=zzzsecretzzz": {"obs": {"liens_externes": {"externes": ["https://a.org/x?cle=secret123456&q=1#f"]}}}}
        liens_externes.apres_crawl(pages, ctx)
        recus = []
        liens_externes.issues(pages, lambda cle, libelle, sev, ex=None, **kw: recus.append((cle, sev, ex, kw)), ctx)
        cle, sev, ex, kw = recus[0]
        self.assertEqual((cle, sev, kw["domaine"]), ("external_broken", "moyenne", "SEO technique"))
        self.assertEqual(ex["lien"], "https://a.org/x")
        self.assertNotIn("secret", json.dumps(recus))

    def test_une_erreur_reseau_non_dns_nest_pas_cassee(self):
        f = faux(lambda u, m: {"status": 0, "error": "<urlopen error [Errno -3] Temporary failure in name resolution>"})
        ctx = ctx_de(f)
        liens_externes.apres_crawl(pages_de(["https://a.org/x"]), ctx)
        recus = []
        liens_externes.issues({}, lambda cle, *a, **kw: recus.append(cle), ctx)
        self.assertEqual(recus, ["external_a_verifier"])


class TestSSRF(unittest.TestCase):
    """C1 : une adresse non publique n'est jamais requêtée, quelle que soit sa forme."""
    PRIVEES = ["http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/", "http://localhost:8080", "http://[::1]/", "http://2130706433/",
               "http://x.internal/", "http://intranet/", "http://127.1/", "http://0x7f.1/", "http://0177.0.0.1/",
               "http://①②⑦.⓪.⓪.①/", "http://ｌｏｃａｌｈｏｓｔ/", "http://10.0.0.5:6379/", "http://192.168.1.1/", "http://[::ffff:127.0.0.1]/",
               "http://100.64.0.1/", "http://0.0.0.0/", "http://interne.exemple.fr/", "http://imprimante.local/"]

    def test_zero_requete_vers_une_adresse_privee(self):
        f = faux(lambda u, m: 200)
        ctx = ctx_de(f)
        pages = pages_de(self.PRIVEES + ["https://public.org/ok"])
        liens_externes.apres_crawl(pages, ctx)
        self.assertEqual([a["url"] for a in f.appels], ["https://public.org/ok"])
        self.assertEqual(ctx["meta"]["liens_externes_non_verifies"], nv(len(self.PRIVEES), privee=len(self.PRIVEES)))
        c = constats(pages, ctx)
        self.assertEqual(sorted(c), ["external_non_verifie"])
        self.assertEqual((c["external_non_verifie"][0]["raison"], c["external_non_verifie"][0]["n"]), ("adresse privée", len(self.PRIVEES)))

    def test_l_hote_prive_du_site_audite_est_seul_exempte(self):
        f = faux(lambda u, m: 200)
        ctx = ctx_de(f, host="banc.test:8080", resoudre=dns({"banc.test": ["10.0.0.2"], "images.banc.test": ["10.0.0.3"]}))
        liens_externes.apres_crawl(pages_de(["http://banc.test:9000/a", "http://images.banc.test/b", "http://127.0.0.1/c"]), ctx)
        self.assertEqual([a["url"] for a in f.appels], ["http://banc.test:9000/a"])  # même nom d'hôte, autre port : exempté
        self.assertEqual(ctx["meta"]["liens_externes_non_verifies"], nv(2, privee=2))

    def test_option_liens_prives(self):
        f = faux(lambda u, m: 200)
        ctx = ctx_de(f, liens_prives=True, resoudre=dns({"images.banc.test": ["10.0.0.3"]}))
        liens_externes.apres_crawl(pages_de(["http://images.banc.test/b", "http://127.0.0.1/c"]), ctx)
        self.assertEqual(len(f.appels), 2)

    def test_les_options_de_securite_sont_transmises_au_fetch(self):
        recu = {}

        def f(u, timeout=20, method="GET", max_bytes=8_000_000, ua=None, extra_headers=None, **kw):
            recu.update(kw)
            return {"status": 200, "error": None}
        liens_externes.apres_crawl(pages_de(["https://a.org/"]), ctx_de(f, host="www.ex.fr", budget_reseau_s=50))
        self.assertEqual(recu["max_hops"], 6)
        self.assertEqual(recu["prive_ok"], frozenset({"www.ex.fr"}))
        self.assertTrue(0 < recu["echeance"] - time.monotonic() <= 50)
        self.assertIn("resoudre", recu)

    def test_redirection_vers_une_adresse_interne_reelle(self):
        with SiteLocal({"/interne": (200, HTML, "secret")}) as interne, SiteLocal({}) as autre:
            autre.routes["/r"] = (302, {"Location": "http://localhost:{0}/interne".format(interne.srv.server_port)}, "")
            ctx = ctx_de(crawl_site.fetch, host="127.0.0.1:1", resoudre=None)  # site audité local : 127.0.0.1 exempté, localhost non
            del ctx["resoudre"]
            pages = pages_de([autre.base + "/r"])
            liens_externes.apres_crawl(pages, ctx)
            c = constats(pages, ctx)
        self.assertEqual(interne.requetes, [])
        self.assertEqual(sorted(c), ["external_non_verifie"])
        self.assertEqual(c["external_non_verifie"][0]["raison"], "adresse privée")

    def test_redirection_vers_file_ou_ftp_jamais_suivie(self):
        for cible in ("file:///etc/hosts", "ftp://127.0.0.1:21/x", "data:text/html,x"):
            with SiteLocal({"/r": (302, {"Location": cible}, "")}) as autre:
                ctx = ctx_de(crawl_site.fetch, host="127.0.0.1:1")
                del ctx["resoudre"]
                pages = pages_de([autre.base + "/r"])
                liens_externes.apres_crawl(pages, ctx)
                c = constats(pages, ctx)
            self.assertEqual(sorted(c), ["external_non_verifie"], cible)
            self.assertEqual(c["external_non_verifie"][0]["raison"], "adresse invalide")
            self.assertNotIn("hosts", json.dumps(c))

    def test_lien_prive_reel_jamais_contacte(self):
        with SiteLocal({}) as interne:
            ctx = ctx_de(crawl_site.fetch)  # pas d'hôte de site : aucune exemption
            del ctx["resoudre"]
            liens_externes.apres_crawl(pages_de([interne.base + "/x"]), ctx)
        self.assertEqual(interne.requetes, [])


class TestHorsLigne(unittest.TestCase):
    """C2 : sans réseau, aucun lien n'est « cassé »."""

    def dns_partout(self, u, m):
        return {"status": 0, "error": ERREUR_DNS}

    def test_machine_hors_ligne(self):
        f = faux(self.dns_partout)
        liens = ["https://nx{0}.org/".format(i) for i in range(10)]
        ctx = ctx_de(f, resoudre=lambda h, p=None: (_ for _ in ()).throw(socket.gaierror(-2, "Name or service not known")))
        pages = pages_de(liens)
        liens_externes.apres_crawl(pages, ctx)
        c = constats(pages, ctx)
        self.assertEqual(sorted(c), ["external_non_verifie"])
        self.assertEqual((c["external_non_verifie"][0]["raison"], c["external_non_verifie"][0]["n"]), ("réseau indisponible", 10))
        self.assertEqual(len(f.appels), 3)  # arrêt après 3 échecs DNS sans réponse HTTP et sonde en échec
        self.assertEqual(ctx["meta"]["liens_externes_non_verifies"], nv(10, reseau=10))
        self.assertEqual(ctx["meta"]["liens_externes"]["verifies"], 0)
        self.assertTrue(ctx["meta"]["liens_externes_reseau"]["reseau_indisponible"])

    def test_moins_de_trois_liens_hors_ligne(self):
        f = faux(self.dns_partout)
        ctx = ctx_de(f, resoudre=lambda h, p=None: (_ for _ in ()).throw(socket.gaierror(-2, "Name or service not known")))
        pages = pages_de(["https://nx1.org/", "https://nx2.org/"])
        liens_externes.apres_crawl(pages, ctx)
        self.assertEqual(sorted(constats(pages, ctx)), ["external_non_verifie"])

    def test_une_reponse_http_prouve_le_reseau(self):
        f = faux(lambda u, m: 200 if "ok.org" in u else {"status": 0, "error": ERREUR_DNS})
        ctx = ctx_de(f)
        pages = pages_de(["https://ok.org/", "https://nx1.org/", "https://nx2.org/", "https://nx3.org/", "https://nx4.org/"])
        liens_externes.apres_crawl(pages, ctx)
        c = constats(pages, ctx)
        self.assertEqual([e["lien"] for e in c["external_broken"]], ["https://nx1.org/", "https://nx2.org/", "https://nx3.org/", "https://nx4.org/"])
        self.assertNotIn("external_non_verifie", c)
        self.assertEqual(ctx["meta"]["liens_externes_reseau"], {"prouve": True, "reseau_indisponible": False, "dns_inexistants": 4})

    def test_une_sonde_dns_reussie_prouve_le_reseau(self):
        f = faux(self.dns_partout)  # aucune réponse HTTP, mais example.com se résout : les noms inexistants le sont vraiment
        ctx = ctx_de(f)
        pages = pages_de(["https://nx{0}.org/".format(i) for i in range(5)])
        liens_externes.apres_crawl(pages, ctx)
        c = constats(pages, ctx)
        self.assertEqual(len(c["external_broken"]), 5)
        self.assertEqual(len(f.appels), 5)

    def test_chaque_nxdomain_est_confirme_par_une_seconde_resolution(self):
        appels = []
        f = faux(lambda u, m: 200 if "ok.org" in u else {"status": 0, "error": ERREUR_DNS})
        ctx = ctx_de(f, resoudre=dns({"instable.org": [PUBLIC]}, appels))  # se résout au second essai : pas « cassé »
        pages = pages_de(["https://ok.org/", "https://instable.org/", "https://nx9.org/"])
        liens_externes.apres_crawl(pages, ctx)
        c = constats(pages, ctx)
        self.assertEqual([e["lien"] for e in c["external_broken"]], ["https://nx9.org/"])
        self.assertEqual([e["lien"] for e in c["external_a_verifier"]], ["https://instable.org/"])
        self.assertGreaterEqual(appels.count("nx9.org"), 2)  # garde + confirmation

    def test_echec_dns_temporaire_pas_casse(self):
        f = faux(lambda u, m: 200 if "ok.org" in u else {"status": 0, "error": "<urlopen error [Errno -3] Temporary failure in name resolution>"})
        ctx = ctx_de(f)
        pages = pages_de(["https://ok.org/", "https://lent.org/"])
        liens_externes.apres_crawl(pages, ctx)
        self.assertEqual(sorted(constats(pages, ctx)), ["external_a_verifier"])


class TestAdresseBrute(unittest.TestCase):
    """I1 : on requête l'adresse exacte du lien ; seules les sorties sont assainies."""
    JETON = "abcdef123456SECRET"
    DOC = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

    def obs(self, html, url="https://ex.fr/page"):
        return {url: {"obs": ho.analyser(html, {}, url, modules=[("liens_externes", liens_externes)])}}

    def test_requete_exacte_et_sortie_masquee(self):
        longue = "https://tracking.org/p?" + "&".join("a{0}=valeur{0}".format(i) for i in range(60)) + "&ref=" + "z" * 100
        brutes = ["https://ex.com/unsub?user=42&token={0}".format(self.JETON), "https://docs.google.com/document/d/{0}/edit".format(self.DOC),
                  "https://app.org/go?code=FR&page=2", longue, "https://ex.com/a%3Fb"]
        pages = self.obs("".join('<a href="{0}">x</a>'.format(b) for b in brutes))
        self.assertLess(len(json.dumps(pages)), 5000)
        self.assertNotIn(self.JETON, json.dumps(pages))  # ce que le crawl écrit (obs) est masqué
        self.assertNotIn(self.DOC, json.dumps(pages))
        self.assertGreater(len(longue), 300)
        f = faux(lambda u, m: 404)
        ctx = ctx_de(f)
        liens_externes.apres_crawl(pages, ctx)
        self.assertEqual([a["url"] for a in f.appels if a["method"] == "HEAD"], brutes)  # l'adresse exacte, jamais tronquée
        sortie = json.dumps(constats(pages, ctx))
        self.assertNotIn(self.JETON, sortie)
        self.assertNotIn(self.DOC, sortie)
        self.assertNotIn("code=FR", sortie)
        self.assertIn("docs.google.com/document", sortie)

    def test_adresse_masquee_sans_brute_jamais_requetee(self):
        f = faux(lambda u, m: 404)
        ctx = ctx_de(f)
        pages = pages_de(["https://docs.google.com/document/d/…/edit"])
        liens_externes.apres_crawl(pages, ctx)
        self.assertEqual(f.appels, [])
        self.assertEqual(ctx["meta"]["liens_externes_non_verifies"], nv(1, invalide=1))

    def test_identifiants_user_pass_jamais_envoyes(self):
        pages = self.obs('<a href="https://moi:mdp@autre.org/a?page=2#haut">a</a>')
        f = faux(lambda u, m: 200)
        liens_externes.apres_crawl(pages, ctx_de(f))
        self.assertEqual(f.appels[0]["url"], "https://autre.org/a?page=2")

    def test_les_adresses_brutes_ne_survivent_pas_au_crawl(self):
        pages = self.obs('<a href="https://ex.com/x?token={0}">a</a>'.format(self.JETON))
        liens_externes.apres_crawl(pages, ctx_de(faux(lambda u, m: 200)))
        self.assertEqual(liens_externes._BRUTES, {})


class TestAdresseIDN(unittest.TestCase):
    """I2 : chemins accentués et domaines IDN."""

    def test_cafe_et_idn_arrivent_encodes(self):
        f = faux(lambda u, m: 200)
        appels_dns = []
        ctx = ctx_de(f, resoudre=dns(appels=appels_dns))
        liens_externes.apres_crawl(pages_de(["https://fr.wikipedia.org/wiki/Café", "https://bücher.de/x", "https://日本語.jp/路径?q=é"]), ctx)
        self.assertEqual([a["url"] for a in f.appels], ["https://fr.wikipedia.org/wiki/Caf%C3%A9", "https://xn--bcher-kva.de/x",
                                                       "https://xn--wgv71a119e.jp/%E8%B7%AF%E5%BE%84?q=%C3%A9"])
        self.assertIn("xn--bcher-kva.de", appels_dns)  # la résolution du garde se fait sur la forme IDNA

    def test_via_l_observateur(self):
        pages = {"https://ex.fr/": {"obs": ho.analyser('<a href="https://fr.wikipedia.org/wiki/Café">c</a>', {}, "https://ex.fr/",
                                                       modules=[("liens_externes", liens_externes)])}}
        f = faux(lambda u, m: 200)
        liens_externes.apres_crawl(pages, ctx_de(f))
        self.assertEqual(f.appels[0]["url"], "https://fr.wikipedia.org/wiki/Caf%C3%A9")


class TestRobustesse(unittest.TestCase):
    def test_statut_none_ne_perd_pas_les_constats_suivants(self):  # I3
        f = faux(lambda u, m: {"status": None, "error": None} if "premier" in u else 404)
        ctx = ctx_de(f)
        pages = pages_de(["https://premier.org/", "https://second.org/"])
        liens_externes.apres_crawl(pages, ctx)
        c = constats(pages, ctx)
        self.assertEqual([e["lien"] for e in c["external_broken"]], ["https://second.org/"])
        self.assertEqual([e["lien"] for e in c["external_a_verifier"]], ["https://premier.org/"])

    def test_issues_tolere_un_statut_none_en_memoire(self):
        ctx = {"externes": {"https://a.org/": {"statut": None, "erreur": None}, "https://b.org/": {"statut": 404, "erreur": None}},
               "sources_externes": {"https://a.org/": ["https://ex.fr/"], "https://b.org/": ["https://ex.fr/"]}}
        c = constats({}, ctx)
        self.assertEqual(len(c["external_a_verifier"]) + len(c["external_broken"]), 2)

    def test_non_verifies_rapportes_plafond_budget(self):  # I4
        f = faux(lambda u, m: 200)
        ctx = ctx_de(f, liens_externes_max=2)
        pages = pages_de(["https://a{0}.org/".format(i) for i in range(5)])
        liens_externes.apres_crawl(pages, ctx)
        e = constats(pages, ctx)["external_non_verifie"]
        self.assertEqual([(x["raison"], x["n"]) for x in e], [("plafond atteint", 3)])
        self.assertEqual(len(e[0]["liens"]), 3)

        def lent(u, timeout=20, method="GET", max_bytes=8_000_000, ua=None, extra_headers=None):
            time.sleep(0.3)
            return {"status": 200, "error": None}
        ctx = ctx_de(lent, budget_reseau_s=0.5)
        pages = pages_de(["https://h{0}.org/".format(i) for i in range(8)])
        liens_externes.apres_crawl(pages, ctx)
        e = constats(pages, ctx)["external_non_verifie"]
        self.assertEqual(e[0]["raison"], "budget de temps atteint")

    def test_aucun_constat_non_verifie_quand_tout_est_verifie(self):
        f = faux(lambda u, m: 200)
        pages = pages_de(["https://a.org/"])
        ctx = ctx_de(f)
        liens_externes.apres_crawl(pages, ctx)
        self.assertEqual(constats(pages, ctx), {})

    def test_verification_desactivee(self):  # --liens-externes 0
        f = faux(lambda u, m: 200)
        ctx = ctx_de(f, liens_externes_max=0)
        pages = pages_de(["https://a.org/", "http://127.0.0.1/"])
        liens_externes.apres_crawl(pages, ctx)
        self.assertEqual(f.appels, [])
        self.assertEqual(ctx["meta"]["liens_externes"], {"trouves": 2, "verifies": 0, "budget_atteint": False, "desactive": True})
        self.assertEqual(constats(pages, ctx), {})

    def test_liens_a_ignorer_et_protocole_relatif(self):
        html = ('<a href="//cdn.autre.org/x">proto</a><a href="javascript:void(0)">j</a><a href="tel:+33123456789">t</a>'
                '<a href="data:text/html,x">d</a><a href="#haut">ancre</a><a href="http://">vide</a><a href="mailto:a@b.fr">m</a>'
                '<a href="https:///x">sans hôte</a><a href="/local">l</a><a href="ht\ntps://a\t.org/ok">espaces</a>')
        r = ho.analyser(html, {}, "https://www.ex.fr/p", modules=[("liens_externes", liens_externes)])["liens_externes"]["externes"]
        self.assertEqual(r, ["https://cdn.autre.org/x", "https://a.org/ok"])
        r = ho.analyser('<a href="//cdn.autre.org/x">p</a>', {}, "http://ex.fr/p", modules=[("liens_externes", liens_externes)])["liens_externes"]["externes"]
        self.assertEqual(r, ["http://cdn.autre.org/x"])  # le schéma de la page

    def test_404_confirme_par_un_second_get(self):
        for second, attendu in ((404, "external_broken"), (410, "external_broken"), (200, None), (503, "external_a_verifier")):
            n = {"get": 0}

            def rep(u, m, second=second, n=n):
                if m == "HEAD":
                    return 404
                n["get"] += 1
                return 404 if n["get"] == 1 else second
            f = faux(rep)
            ctx = ctx_de(f)
            pages = pages_de(["https://a.org/x"])
            liens_externes.apres_crawl(pages, ctx)
            c = constats(pages, ctx)
            self.assertEqual(sorted(c), [attendu] if attendu else [], second)

    def test_la_pause_porte_sur_le_meme_hote_avec_ou_sans_www(self):
        f = faux(lambda u, m: 200)
        liens_externes.apres_crawl(pages_de(["https://a.org/1", "https://www.a.org/2"]), ctx_de(f, delai_externe=0.3))
        self.assertGreaterEqual(f.appels[1]["t"] - f.appels[0]["t"], 0.28)


class TestRequeteReelle(unittest.TestCase):
    """Vraie requête vers un serveur local : cookies jamais renvoyés, redirections limitées à 5."""

    def serveur(self):
        vus = []

        class H(BaseHTTPRequestHandler):
            def _r(self):
                vus.append((self.command, self.path, self.headers.get("Cookie"), self.headers.get("User-Agent")))
                self.send_response(302)
                self.send_header("Location", "/suite{0}".format(len(vus)))
                self.send_header("Set-Cookie", "session=abc; Path=/")
                self.send_header("Content-Length", "0")
                self.end_headers()
            do_GET = do_HEAD = _r

            def log_message(self, *a):
                pass
        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv, vus

    def test_cinq_redirections_au_plus_et_aucun_cookie(self):
        srv, vus = self.serveur()
        try:
            lien = "http://127.0.0.1:{0}/boucle".format(srv.server_port)
            ctx = ctx_de(crawl_site.fetch, liens_prives=True)
            liens_externes.apres_crawl(pages_de([lien]), ctx)
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual(len(vus), 6)  # 5 redirections suivies, la 6e réponse n'est pas suivie ; HEAD seul : -1 est « à vérifier », pas de GET de repli
        self.assertEqual({v[0] for v in vus}, {"HEAD"})
        self.assertEqual({v[2] for v in vus}, {None})
        self.assertIn("AuditSiteAstro", vus[0][3])
        r = ctx["externes"][lien]
        self.assertEqual(liens_externes.classer(r["statut"], r["erreur"]), "a_verifier")
        self.assertIn("5 redirections", r["erreur"])


if __name__ == "__main__":
    unittest.main()
