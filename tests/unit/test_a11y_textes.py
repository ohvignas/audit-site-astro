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
import a11y_textes  # noqa: E402
from site_local import HTML, SiteLocal  # noqa: E402


def crawler(routes):
    """Crawl d'un SiteLocal (aucun réseau externe) → issues.json."""
    with SiteLocal(routes) as site, tempfile.TemporaryDirectory() as d:
        subprocess.run([sys.executable, str(SCRIPTS / "crawl_site.py"), site.url, "--out", d, "--delay", "0", "--max-pages", "10",
                        "--liens-externes", "0", "--ressources", "0"], check=True, capture_output=True, timeout=120)
        return json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8")), site.base


def res(html):
    r = ho.analyser(html, {}, "https://ex.fr/", modules=[("a11y_textes", a11y_textes)])["a11y_textes"]
    return {k: [e["signature"] for e in v] for k, v in r.items()}


VIDE = {"liens_generiques": [], "alt_suspects": [], "alt_redondants": []}


class TestTextes(unittest.TestCase):
    def test_trois_controles(self):
        html = ('<a href="/a">Cliquez ici</a> <a href="/b">En savoir plus…</a>'
                '<a href="/c" aria-label="En savoir plus sur le CPF">En savoir plus</a> <a href="/d">Voir le catalogue</a>'
                '<img src="a.jpg" alt="scene-bub-cover.jpg"><img src="b.jpg" alt="IMG_1234"><img src="c.jpg" alt="image">'
                '<img src="d.jpg" alt="Atelier no-code en groupe"><img src="e.jpg" alt="no-code">'
                '<img src="f.jpg" alt="Apprendre &amp;amp; créer"><img src="g.jpg" alt="">'                 # beta.illith.com
                '<a href="/cat"><img src="c.png" alt="Catalogue"> Catalogue</a>'
                '<figure><img src="f.png" alt="Courbe des inscriptions"><figcaption>Courbe des inscriptions</figcaption></figure>')
        self.assertEqual(res(html), {
            "liens_generiques": ["« cliquez ici »", "« en savoir plus »"],
            "alt_suspects": ["Apprendre &amp; créer (double échappement)", "IMG_1234 (identifiant)", "image (mot générique)",
                             "scene-bub-cover.jpg (nom de fichier)"],
            "alt_redondants": ["« Catalogue » (texte du lien)", "« Courbe des inscriptions » (légende)"]})

    def test_liens_generiques_fr_en(self):
        for texte in ("en savoir plus", "Cliquez ici", "Lire la suite", "ici", "Voir plus",
                      "Read more", "Click here", "Learn more", "More"):
            with self.subTest(texte=texte):
                r = res('<a href="/x">{0}</a>'.format(texte))
                self.assertEqual(len(r["liens_generiques"]), 1, r)

    def test_meme_texte_hrefs_differents(self):
        r = res('<a href="/a">En savoir plus</a><a href="/b">En savoir plus</a>')
        self.assertEqual(r["liens_generiques"], ["« en savoir plus »"])

    def test_contexte_ne_declenche_pas(self):
        for html in ('<a href="/x" aria-label="En savoir plus sur le CPF">En savoir plus</a>',
                     '<a href="/x" aria-describedby="t">En savoir plus</a><h3 id="t">Le CPF</h3>',
                     '<a href="/x" aria-labelledby="t">En savoir plus</a><h3 id="t">Le CPF</h3>',
                     '<a href="/x">En savoir plus<span class="sr-only"> sur le CPF</span></a>',
                     '<a href="/x">En savoir plus <span style="position:absolute;width:1px"> : formation CPF</span></a>',
                     '<a href="/x">Voir le catalogue</a>'):
            with self.subTest(html=html):
                self.assertEqual(res(html), VIDE)

    def test_texte_masque_ne_complete_pas(self):
        # aria-hidden retire le texte de l'arbre d'accessibilité : le libellé reste ambigu
        r = res('<a href="/x">En savoir plus<span aria-hidden="true"> sur le CPF</span></a>')
        self.assertEqual(r["liens_generiques"], ["« en savoir plus »"])

    def test_alt_mots_seuls(self):
        r = res('<img alt="logo"><img alt="Photo"><img alt="Logo ILLITH"><img alt="Photo de l\'équipe en atelier">')
        self.assertEqual(r["alt_suspects"], ["Photo (mot générique)", "logo (mot générique)"])

    def test_alt_identifiants(self):
        r = res('<img alt="DSC_0042"><img alt="PXL_20240101_123456789"><img alt="IMG 2034">'
                '<img alt="3f2a9c1e-7b4d-4e8a-9c3b-1a2b3c4d5e6f"><img alt="a1b2c3d4e5f60718">'
                '<img alt="photo-1a2b3c.webp"><img alt="Capture d\'écran 2024-05-12.png">')
        self.assertEqual(sorted(r["alt_suspects"]), sorted([
            "DSC_0042 (identifiant)", "PXL_20240101_123456789 (identifiant)", "IMG 2034 (identifiant)",
            "3f2a9c1e-7b4d-4e8a-9c3b-1a2b3c4d5e6f (identifiant)", "a1b2c3d4e5f60718 (identifiant)",
            "photo-1a2b3c.webp (nom de fichier)", "Capture d'écran 2024-05-12.png (nom de fichier)"]))

    def test_alt_noms_propres_non_suspects(self):
        # M1 : noms propres et sigles avec tirets, pas des identifiants
        for alt in ("Aix-en-Provence", "COVID-19", "Windows-11", "Saint-Jean-de-Luz", "F-35", "Q3-2024", "no-code",
                    "photo-equipe-2024", "hero_banner_v2", "Wi-Fi"):
            with self.subTest(alt=alt):
                self.assertEqual(res('<img alt="{0}">'.format(alt)), VIDE)

    def test_alt_espaces_insecables_et_retours(self):
        # M2 : NBSP et retours à la ligne ne font pas une phrase « sans espace »
        for alt in ("Vue&nbsp;aérienne&nbsp;d'Aix-en-Provence", "Vue\u00a0aérienne\u00a0d'Aix-en-Provence",
                    "Vue\naérienne\nd'Aix-en-Provence", "Salle\u202fA-12_b"):
            with self.subTest(alt=alt):
                self.assertEqual(res('<img alt="{0}">'.format(alt)), VIDE)
        self.assertEqual(res('<img alt="logo&nbsp;">')["alt_suspects"], ["logo (mot générique)"])

    def test_alt_numerote_et_entites_nommees(self):
        r = res('<img alt="Photo 1"><img alt="image1"><img alt="Atelier d&amp;rsquo;été">')
        self.assertEqual(r["alt_suspects"], ["Atelier d&rsquo;été (double échappement)", "Photo 1 (mot générique)",
                                             "image1 (mot générique)"])

    def test_normalisation_libelles(self):
        # M3 : guillemets typographiques, flèches, symboles, NBSP, NFD, caractères de format
        for texte in ("“En savoir plus”", "‘Cliquez ici’", "&laquo;&nbsp;En savoir plus&nbsp;&raquo;", "En savoir plus -&gt;",
                      "En savoir plus →", "En savoir plus ↗", "Lire la suite ➔", "Cliquez&nbsp;ici", "CLIQUEZ ICI",
                      "D\u00e9couvrir".replace("\u00e9", "e\u0301"), "Lire\u200b la suite", "En\u00adsavoir plus",
                      "Cliquez-ici"):
            with self.subTest(texte=texte):
                self.assertEqual(len(res('<a href="/x">{0}</a>'.format(texte))["liens_generiques"]), 1)

    def test_normalisation_alt_redondant(self):
        r = res('<a href="/x"><img alt="L\'atelier"> L’atelier</a><a href="/y"><img alt="Cafe\u0301"> Caf\u00e9</a>')
        self.assertEqual(r["alt_redondants"], ["« Café » (texte du lien)", "« L'atelier » (texte du lien)"])

    def test_contexte_vide_de_sens(self):
        # M5 : title / aria-label qui répètent le libellé générique ne lèvent pas l'ambiguïté
        for html in ('<a href="/x" title="Cliquez ici">Cliquez ici</a>',
                     '<a href="/x" aria-label="Lire la suite">Lire la suite</a>',
                     '<a href="/x" aria-label="Lire la suite →" title="">Lire la suite</a>'):
            with self.subTest(html=html):
                self.assertEqual(len(res(html)["liens_generiques"]), 1)
        self.assertEqual(res('<a href="/x" title="Formation CPF Bubble">En savoir plus</a>'), VIDE)

    def test_nom_accessible_avec_alt_image(self):
        # M4a : l'alt de l'image fait partie du nom du lien
        self.assertEqual(res('<a href="/f"><img alt="Formation Bubble : créer une app"><span>En savoir plus</span></a>'), VIDE)

    def test_lien_jumeau_explicite(self):
        # M4b : carte = titre explicite + « Lire la suite » vers la même destination
        self.assertEqual(res('<h2><a href="/blog/a1">Créer une app Bubble</a></h2><a href="/blog/a1">Lire la suite</a>'), VIDE)
        r = res('<h2><a href="/blog/a1">Créer une app</a></h2><a href="/blog/a2">Lire la suite</a>')
        self.assertEqual(r["liens_generiques"], ["« lire la suite »"])

    def test_destinations_conservees(self):
        r = ho.analyser('<a href="/a">Cliquez ici</a><a href="/b">Cliquez ici</a><a href="/c">Cliquez ici</a>'
                        '<a href="/o">Découvrir</a><a href="/o">Découvrir</a>', {}, "https://ex.fr/",
                        modules=[("a11y_textes", a11y_textes)])["a11y_textes"]["liens_generiques"]
        self.assertEqual({e["signature"]: e["exemple"] for e in r},
                         {"« cliquez ici »": "3 liens, 3 destinations", "« découvrir »": "2 liens, 1 destination"})

    def test_alt_redondant_non_exact(self):
        r = res('<a href="/x"><img alt="Catalogue complet"> Catalogue</a>'
                '<figure><img alt="Courbe"><figcaption>Courbe des inscriptions</figcaption></figure>')
        self.assertEqual(r["alt_redondants"], [])

    def test_contenu_masque_ignore(self):
        self.assertEqual(res('<div hidden><a href="/x">ici</a><img alt="IMG_1234"></div>'), VIDE)

    def test_crawl(self):
        page = ('<html lang="fr"><head><title>Ressources de test assez longues</title></head><body><main>'
                '<a href="/x">Read more</a><img src="/p.png" alt="DSC_0042" width="1" height="1"></main></body></html>')
        issues, _ = crawler({"/": (200, HTML, page), "/x": (200, HTML, page)})
        self.assertEqual(issues["lien_generique"]["examples"][0]["signature"], "« read more »")
        self.assertEqual(issues["alt_suspect"]["severity"], "basse")


if __name__ == "__main__":
    unittest.main()
