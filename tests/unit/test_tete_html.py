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
import tete_html  # noqa: E402
from site_local import HTML, SiteLocal  # noqa: E402


def crawler(routes):
    """Crawl d'un SiteLocal (aucun réseau externe) → issues.json."""
    with SiteLocal(routes) as site, tempfile.TemporaryDirectory() as d:
        subprocess.run([sys.executable, str(SCRIPTS / "crawl_site.py"), site.url, "--out", d, "--delay", "0", "--max-pages", "10",
                        "--liens-externes", "0", "--ressources", "0"], check=True, capture_output=True, timeout=120)
        return json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8")), site.base


def res(html):
    return [e["signature"] for e in ho.analyser(html, {}, "https://ex.fr/", modules=[("tete_html", tete_html)])["tete_html"]["interruptions"]]


def page(tete, corps="<body></body>"):
    return "<!doctype html><html><head>" + tete + "</head>" + corps + "</html>"


class TestTete(unittest.TestCase):
    def test_image_dans_la_tete(self):
        self.assertEqual(res('<html><head><title>T</title><meta name="viewport" content="width=device-width"><img src="/p.png" alt="">'
                             '<link rel="canonical" href="/x"><meta name="description" content="d"></head><body></body></html>'),
                         ["<img> puis : link canonical, meta description"])

    def test_texte_dans_la_tete(self):
        self.assertEqual(res('<html><head><title>T</title>Bonjour<meta name="robots" content="noindex"></head><body></body></html>'),
                         ["#texte puis : meta robots"])

    def test_cas_valides(self):
        self.assertEqual(res('<html><head><title>T</title><noscript><link rel="stylesheet" href="/n.css"><style>a{}</style></noscript>'
                             '<link rel="canonical" href="/x"></head><body></body></html>'), [])
        # pixel en <noscript> APRÈS les balises de référencement : rien n'est perdu
        self.assertEqual(res('<html><head><title>T</title><link rel="canonical" href="/x"><noscript><img src="/px.gif"></noscript>'
                             '</head><body></body></html>'), [])
        self.assertEqual(res('<html><head><meta charset="utf-8"><meta http-equiv="content-security-policy" content="x">'
                             '<link rel="preload" href="/_astro/f.woff2" as="font"><style>:root{}</style>'
                             '<script type="module" src="/_astro/p.js"></script><title>T</title></head><body><img src="/a.png"></body></html>'), [])
        self.assertEqual(res('<html><head><title>T</title><link rel="canonical" href="/x"><div>bandeau</div></head><body></body></html>'), [])

    def test_crawl(self):
        page = ('<html lang="fr"><head><title>Tête interrompue de test</title><iframe src="/x"></iframe>'
                '<meta name="description" content="Description ignorée par Google après l iframe dans la tête."></head>'
                '<body><main><p>x</p></main></body></html>')
        issues, _ = crawler({"/": (200, HTML, page)})
        it = issues["tete_interrompue"]
        # écart au brief : la description seule perdue est « moyenne » (haute seulement si canonical, robots ou hreflang sont perdus)
        self.assertEqual((it["severity"], it["domaine"], it["examples"][0]["signature"]),
                         ("moyenne", "SEO technique", "<iframe> puis : meta description"))

    def test_crawl_canonical_perdue_est_haute(self):
        page = ('<html lang="fr"><head><title>Tête interrompue de test</title><img src="/p.png" alt="">'
                '<meta name="description" content="Description ignorée."><link rel="canonical" href="/"></head>'
                '<body><main><p>x</p></main></body></html>')
        issues, _ = crawler({"/": (200, HTML, page), "/b": (200, HTML, page.replace("/p.png", "/q.png"))})
        it = issues["tete_interrompue"]
        self.assertEqual((it["severity"], it["domaine"]), ("haute", "SEO technique"))
        self.assertEqual(it["examples"][0]["signature"], "<img> puis : meta description, link canonical")

    def test_crawl_page_valide_sans_constat(self):
        page = ('<html lang="fr"><head><meta charset="utf-8"><title>Page valide</title><link rel="canonical" href="/">'
                '<noscript><img src="/px.gif"></noscript></head><body><main><p>x</p></main></body></html>')
        issues, _ = crawler({"/": (200, HTML, page)})
        self.assertNotIn("tete_interrompue", issues)


    def test_crawl_noscript_sans_javascript_est_moyenne(self):
        page = ('<html lang="fr"><head><meta charset="utf-8"><title>Page avec pixel</title>'
                '<noscript><img src="/px.gif" alt=""></noscript><link rel="canonical" href="/"></head>'
                '<body><main><p>x</p></main></body></html>')
        issues, _ = crawler({"/": (200, HTML, page)})
        it = issues["tete_interrompue"]
        self.assertEqual((it["severity"], it["domaine"]), ("moyenne", "SEO technique"))
        self.assertEqual(it["examples"][0]["signature"], "<noscript><img> (sans JavaScript) puis : link canonical")
        self.assertIn("Google", it["label"])
        self.assertIn("sans JavaScript", it["label"])
        self.assertIn("<body>", it["examples"][0]["exemple"])


class TestSpecWhatwg(unittest.TestCase):
    """Mode d'insertion « in head » : éléments permis, blancs, commentaires, doctype, html, contenu brut."""

    def test_astro_et_balises_permises_jamais_signales(self):
        tete = ('<meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta name="generator" content="Astro v5">'
                '<meta name="astro-view-transitions-enabled" content="true"><meta name="astro-view-transitions-fallback" content="animate">'
                '<link rel="modulepreload" href="/_astro/a.js"><link rel="stylesheet" href="/_astro/a.css">'
                '<script type="application/ld+json">{"@type":"Organization"}</script><script type="module" src="/_astro/p.js"></script>'
                '<style>a{}</style><base href="/"><basefont size="3"><bgsound src="x.wav"><noframes>texte</noframes>'
                '<template><div><meta name="robots" content="x"></div></template><title>T</title>'
                '<noscript><link rel="stylesheet" href="/n.css"></noscript>'
                '<link rel="canonical" href="/x"><meta name="robots" content="index"><meta property="og:title" content="T">'
                '<link rel="alternate" hreflang="en" href="/en"><meta name="description" content="d">')
        self.assertEqual(res(page(tete)), [])

    def test_blancs_commentaires_doctype_et_html_ignores(self):
        tete = '\n\t <!-- c --> <title>T</title> \r\n<!--x--> <html lang="fr"> <head> <link rel="canonical" href="/x">'
        self.assertEqual(res("<!DOCTYPE html><!-- avant --><html><head>" + tete + "</head><body></body></html>"), [])

    def test_espace_insecable_est_du_texte(self):
        # seuls tab, LF, FF, CR et espace sont des blancs pour le parseur : &nbsp; interrompt la tête
        self.assertEqual(res(page('<title>T</title>&nbsp;<meta name="description" content="d">')), ["#texte puis : meta description"])
        self.assertEqual(res(page('<title>T</title> <link rel="canonical" href="/x">')), ["#texte puis : link canonical"])
        self.assertEqual(res(page('<title>T</title>&#32;&#9;<link rel="canonical" href="/x">')), [])

    def test_interruption_sans_balise_de_reference_apres(self):
        self.assertEqual(res(page('<title>T</title><meta name="description" content="d"><img src="/p.png"><meta charset="utf-8">')), [])
        self.assertEqual(res(page('<title>T</title><div>x</div>')), [])
        self.assertEqual(res(page("<title>T</title>Bonjour")), [])

    def test_seule_la_premiere_interruption_compte(self):
        self.assertEqual(res(page('<title>T</title><img src="/a.png"><meta name="robots" content="noindex"><div>x</div>'
                                  '<link rel="canonical" href="/x">')), ["<img> puis : meta robots, link canonical"])

    def test_elements_invalides_courants(self):
        for balise, attendu in (('<div>a</div>', "<div>"), ('<iframe src="/x"></iframe>', "<iframe>"), ('<p>a</p>', "<p>"),
                                ('<a href="/x">l</a>', "<a>"), ('<input type="hidden">', "<input>"), ('<svg><title>i</title></svg>', "<svg>"),
                                ('<my-widget></my-widget>', "<my-widget>"), ('<br>', "<br>"), ('<h1>t</h1>', "<h1>")):
            with self.subTest(balise=balise):
                self.assertEqual(res(page('<title>T</title>' + balise + '<link rel="canonical" href="/x">')),
                                 [attendu + " puis : link canonical"])

    def test_contenu_des_conteneurs_n_est_pas_lu_comme_balises(self):
        # <title>, <script>, <style>, <template> : texte brut ou contenu inerte
        self.assertEqual(res(page('<title>A <b>b</b> <div>c</div></title><link rel="canonical" href="/x">')), [])
        self.assertEqual(res(page('<script>var a="<div>";</script><style>/* <img> */</style><meta name="robots" content="x">')), [])
        self.assertEqual(res(page('<template><img><div></div></template><meta name="robots" content="x">')), [])

    def test_apres_interruption_contenus_inertes_ignores(self):
        # <svg><title> ou <iframe>…<meta></iframe> après l'interruption ne sont pas des métadonnées perdues
        self.assertEqual(res(page('<div></div><svg><title>icône</title></svg>')), [])
        self.assertEqual(res(page('<div></div><iframe><meta name="robots" content="x"></iframe>')), [])
        self.assertEqual(res(page('<div></div><noscript><link rel="canonical" href="/x"></noscript>')), [])
        self.assertEqual(res(page('<div></div><template><meta name="robots" content="x"></template>')), [])

    def test_balises_de_reference_reconnues(self):
        tete = ('<div></div><title>T</title><meta name="Description" content="d"><meta name="robots" content="x">'
                '<meta name="googlebot" content="x"><meta name="viewport" content="x"><meta property="og:image" content="x">'
                '<meta name="twitter:card" content="x"><meta name="theme-color" content="x"><meta charset="utf-8">'
                '<link rel="Canonical" href="/x"><link rel="alternate" hreflang="en" href="/en"><link rel="alternate" href="/feed">'
                '<link rel="manifest" href="/m.webmanifest"><link rel="preload" href="/hero.avif" as="image">'
                '<link rel="preload" href="/f.woff2" as="font"><link rel="preload" href="/h.css" as="style" fetchpriority="high">'
                '<link rel="stylesheet" href="/a.css"><meta name="robots" content="y">')
        self.assertEqual(res(page(tete)), ["<div> puis : title, meta description, meta robots, meta googlebot, meta viewport, "
                                           "meta og:image, meta twitter:card, meta theme-color, link canonical, link hreflang, "
                                           "link alternate, link manifest, link preload LCP"])

    def test_deuxieme_head_et_html_dans_la_tete_ne_cassent_pas(self):
        self.assertEqual(res("<html><head><title>T</title><head><html><link rel=canonical href=/x></head><body></body></html>"), [])

    def test_body_termine_la_tete_sans_head_fermant(self):
        self.assertEqual(res('<html><head><title>T</title><body><div></div><link rel="canonical" href="/x"></body></html>'), [])

    def test_head_implicite(self):
        # pas de <head> : les éléments valides ouvrent la tête implicite, l'interruption s'y applique
        self.assertEqual(res('<html><title>T</title><img src="/p.png"><link rel="canonical" href="/x"><body></body></html>'),
                         ["<img> puis : link canonical"])
        self.assertEqual(res('<title>T</title><meta name="robots" content="x"><div>a</div><link rel="canonical" href="/x">'),
                         ["<div> puis : link canonical"])
        # corps direct, sans rien dans la tête : pas une tête interrompue
        self.assertEqual(res('<html><div>a</div><link rel="canonical" href="/x">'), [])
        self.assertEqual(res('<html><body><div>a</div><link rel="canonical" href="/x"></body></html>'), [])
        self.assertEqual(res("Bonjour<link rel=canonical href=/x>"), [])

    def test_metadonnees_dans_le_corps_hors_sujet(self):
        self.assertEqual(res(page('<title>T</title>', '<body><img src="/a.png"><link rel="canonical" href="/x"></body>')), [])

    def test_resultat_json_strict_et_stable(self):
        r = ho.analyser(page('<img src="/a.png"><meta name="robots" content="x">'), {}, "https://ex.fr/",
                        modules=[("tete_html", tete_html)])["tete_html"]
        self.assertEqual(r, {"interruptions": [{"signature": "<img> puis : meta robots", "n": 1}]})
        json.dumps(r, allow_nan=False)
        self.assertEqual(ho.analyser("", {}, "https://ex.fr/", modules=[("tete_html", tete_html)])["tete_html"], {"interruptions": []})


ASTRO = ('<meta charset="utf-8"><meta http-equiv="content-security-policy" content="script-src \'self\'">'
         '<meta name="viewport" content="width=device-width"><meta name="generator" content="Astro v5.1">'
         '<meta name="astro-view-transitions-enabled" content="true"><meta name="astro-view-transitions-fallback" content="animate">'
         '<link rel="preload" href="/_astro/inter.woff2" as="font" type="font/woff2" crossorigin>'
         '<link rel="modulepreload" href="/_astro/client.js"><style>@font-face{font-family:Inter}</style>'
         '<script>document.documentElement.dataset.theme=localStorage.theme||"light"</script>'
         '<script type="text/partytown">1</script><script type="module" src="/_astro/page.js"></script>'
         '<link rel="icon" href="/favicon.svg" type="image/svg+xml">')
SEO = ('<title>Titre</title><meta name="description" content="d"><link rel="canonical" href="https://ex.fr/">'
       '<meta name="robots" content="index, follow"><link rel="alternate" hreflang="en" href="https://ex.fr/en">'
       '<meta property="og:title" content="T"><meta name="twitter:card" content="summary">'
       '<script type="application/ld+json">{"@type":"Organization"}</script>')
GTM_NOSCRIPT = ('<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-XXXX" height="0" width="0" '
                'style="display:none;visibility:hidden"></iframe></noscript>')
PIXEL_META = '<noscript><img height="1" width="1" style="display:none" src="https://www.facebook.com/tr?id=1&ev=PageView&noscript=1"></noscript>'


class TestAstroGtmBom(unittest.TestCase):
    def test_tete_astro_complete_sans_constat(self):
        for ordre in (ASTRO + SEO, SEO + ASTRO):
            with self.subTest(debut=ordre[:30]):
                self.assertEqual(res("<!doctype html><html lang=fr><head>" + ordre + "</head><body><main></main></body></html>"), [])

    def test_gtm_noscript_en_tete_avant_les_balises_est_signale_sans_javascript(self):
        r = res(page(ASTRO + GTM_NOSCRIPT + SEO))
        self.assertEqual(r, ["<noscript><iframe> (sans JavaScript) puis : title, meta description, link canonical, meta robots, "
                             "link hreflang, meta og:title, meta twitter:card"])

    def test_pixel_meta_en_tete_avant_les_balises(self):
        self.assertEqual(res(page(ASTRO + PIXEL_META + SEO)),
                         ["<noscript><img> (sans JavaScript) puis : title, meta description, link canonical, meta robots, "
                          "link hreflang, meta og:title, meta twitter:card"])

    def test_noscript_invalide_apres_les_balises_ou_dans_le_corps_sans_constat(self):
        self.assertEqual(res(page(ASTRO + SEO + GTM_NOSCRIPT + PIXEL_META)), [])
        self.assertEqual(res(page(ASTRO + SEO, "<body>" + GTM_NOSCRIPT + PIXEL_META + "<main></main></body>")), [])

    def test_noscript_div_et_texte(self):
        self.assertEqual(res(page('<noscript><div>x</div></noscript><link rel="canonical" href="/x">')),
                         ["<noscript><div> (sans JavaScript) puis : link canonical"])
        self.assertEqual(res(page('<noscript>Activez JavaScript</noscript><link rel="canonical" href="/x">')),
                         ["<noscript>#texte (sans JavaScript) puis : link canonical"])
        self.assertEqual(res(page('<noscript>  \n </noscript><link rel="canonical" href="/x">')), [])

    def test_noscript_valide_jamais_signale(self):
        for contenu in ('<link rel="stylesheet" href="/n.css">', '<style>a{}</style>', '<meta http-equiv="refresh" content="0;url=/x">',
                        '<link rel="stylesheet" href="/a.css"><style>b{}</style><!-- c --> '):
            with self.subTest(contenu=contenu):
                self.assertEqual(res(page("<noscript>" + contenu + '</noscript><title>T</title><link rel="canonical" href="/x">')), [])

    def test_noscript_avec_element_valide_dans_la_tete_ne_ferme_pas_la_tete(self):
        # « in head noscript » retraite le jeton dans la tête : script, template, title, base, noscript y sont permis
        for contenu in ('<script src="/x.js"></script>', '<template><div></div></template>', '<title>T</title>', '<base href="/">',
                        '<noscript></noscript>', '<script>1</script><link rel="stylesheet" href="/a.css">'):
            with self.subTest(contenu=contenu):
                self.assertEqual(res(page("<noscript>" + contenu + '</noscript><link rel="canonical" href="/x">')), [])
        # un élément invalide après un élément valide du noscript ferme bien la tête
        self.assertEqual(res(page('<noscript><script></script><img src="/p.gif"></noscript><link rel="canonical" href="/x">')),
                         ["<noscript><img> (sans JavaScript) puis : link canonical"])

    def test_pas_de_double_signature_quand_l_interruption_avec_javascript_rapporte_les_memes_pertes(self):
        tete = GTM_NOSCRIPT + '<meta name="description" content="d"><video></video><meta name="description" content="d">'
        self.assertEqual(res(page(tete)), ["<video> puis : meta description"])
        # pertes plus nombreuses sans JavaScript : les deux signatures restent
        self.assertEqual(res(page(GTM_NOSCRIPT + '<title>T</title><video></video><meta name="description" content="d">')),
                         ["<video> puis : meta description", "<noscript><iframe> (sans JavaScript) puis : title, meta description"])

    def test_noscript_invalide_perd_aussi_ce_qui_suit_dans_le_noscript(self):
        self.assertEqual(res(page('<noscript><img src="/p.gif"><link rel="canonical" href="/x"></noscript>')),
                         ["<noscript><img> (sans JavaScript) puis : link canonical"])

    def test_noscript_dans_un_noscript_ou_un_template_ou_apres_interruption(self):
        self.assertEqual(res(page('<template><noscript><img></noscript></template><link rel="canonical" href="/x">')), [])
        # interruption avec JavaScript d'abord : un seul constat, celui de l'interruption ordinaire
        self.assertEqual(res(page('<div></div>' + GTM_NOSCRIPT + '<link rel="canonical" href="/x">')), ["<div> puis : link canonical"])

    def test_les_deux_constats_quand_noscript_puis_interruption(self):
        self.assertEqual(res(page(GTM_NOSCRIPT + '<meta name="description" content="d"><div></div><link rel="canonical" href="/x">')),
                         ["<div> puis : link canonical", "<noscript><iframe> (sans JavaScript) puis : meta description, link canonical"])

    def test_noscript_implicite_sans_head(self):
        self.assertEqual(res('<html>' + GTM_NOSCRIPT + '<title>T</title><body></body></html>'),
                         ["<noscript><iframe> (sans JavaScript) puis : title"])

    def test_bom_utf8_tolere(self):
        tete = '<title>T</title><div></div><link rel="canonical" href="/x">'
        for html in ("\ufeff<!doctype html><html><head>" + tete + "</head><body></body></html>",
                     "\ufeff" + page(tete), "\ufeff<html><head>" + tete + "</head></html>", "\ufeff\n<html><head>" + tete + "</head>"):
            with self.subTest(html=html[:25]):
                self.assertEqual(res(html), ["<div> puis : link canonical"])
        self.assertEqual(res("\ufeff" + page(ASTRO + SEO)), [])
        self.assertEqual(res("\ufeff" + page(ASTRO + GTM_NOSCRIPT + SEO))[0][:36], "<noscript><iframe> (sans JavaScript)")

    def test_bom_ailleurs_reste_du_texte(self):
        self.assertEqual(res(page('<title>T</title>\ufeff<link rel="canonical" href="/x">')), ["#texte puis : link canonical"])
        self.assertEqual(res("\ufeff\ufeff" + page('<title>T</title><link rel="canonical" href="/x">')), [])  # 2e BOM : texte avant la tête


class TestConstats(unittest.TestCase):
    def constats(self, signatures):
        pages = {"https://ex.fr/p%d" % i: {"obs": {"tete_html": {"interruptions": [{"signature": s, "n": 1}]}}}
                 for i, s in enumerate(signatures)}
        issues = {}

        def add(cle, libelle, sev, exemple=None, n=1, domaine=None):
            it = issues.setdefault(cle, {"severity": sev, "count": 0, "examples": [], "domaine": domaine})
            it["count"] += n
            it["examples"].append(exemple)
        tete_html.issues(pages, add, {})
        return issues

    def test_haute_si_canonical_robots_ou_hreflang_perdus(self):
        for perdu in ("link canonical", "meta robots", "meta googlebot", "link hreflang", "meta description, link canonical"):
            with self.subTest(perdu=perdu):
                self.assertEqual(self.constats(["<img> puis : " + perdu])["tete_interrompue"]["severity"], "haute")

    def test_moyenne_sinon(self):
        for perdu in ("meta description", "title", "meta og:title, meta viewport"):
            with self.subTest(perdu=perdu):
                self.assertEqual(self.constats(["<img> puis : " + perdu])["tete_interrompue"]["severity"], "moyenne")

    def test_un_constat_au_plus_haute_gravite_et_tous_les_exemples(self):
        it = self.constats(["<div> puis : meta description", "<img> puis : link canonical"])["tete_interrompue"]
        self.assertEqual((it["severity"], it["count"], it["domaine"]), ("haute", 2, "SEO technique"))
        self.assertEqual(sorted(e["signature"] for e in it["examples"]), ["<div> puis : meta description", "<img> puis : link canonical"])

    def test_sans_javascript_plafonne_a_moyenne_meme_avec_canonical(self):
        for perdu in ("link canonical", "meta robots", "link hreflang", "meta description, link canonical"):
            with self.subTest(perdu=perdu):
                it = self.constats(["<noscript><iframe> (sans JavaScript) puis : " + perdu])["tete_interrompue"]
                self.assertEqual(it["severity"], "moyenne")
        self.assertFalse(tete_html.grave("<noscript><img> (sans JavaScript) puis : link canonical"))
        self.assertTrue(tete_html.grave("<img> puis : link canonical"))

    def test_melange_la_gravite_vient_du_cas_avec_javascript(self):
        it = self.constats(["<noscript><iframe> (sans JavaScript) puis : link canonical", "<div> puis : meta description"])["tete_interrompue"]
        self.assertEqual((it["severity"], it["count"]), ("moyenne", 2))
        it = self.constats(["<noscript><iframe> (sans JavaScript) puis : link canonical", "<div> puis : link canonical"])["tete_interrompue"]
        self.assertEqual(it["severity"], "haute")

    def test_aucun_constat_sans_interruption(self):
        self.assertEqual(self.constats([]), {})


if __name__ == "__main__":
    unittest.main()
