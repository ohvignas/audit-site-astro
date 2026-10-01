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
        r = res('<img alt="photo-equipe-2024"><img alt="no-code"><img alt="DSC_0042"><img alt="hero_banner_v2"><img alt="e-mail">')
        self.assertEqual(r["alt_suspects"], ["DSC_0042 (identifiant)", "hero_banner_v2 (identifiant)",
                                             "photo-equipe-2024 (identifiant)"])

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
