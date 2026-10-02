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
import a11y_structure  # noqa: E402
from site_local import HTML, SiteLocal  # noqa: E402


def crawler(routes):
    """Crawl d'un SiteLocal (aucun réseau externe) → issues.json."""
    with SiteLocal(routes) as site, tempfile.TemporaryDirectory() as d:
        subprocess.run([sys.executable, str(SCRIPTS / "crawl_site.py"), site.url, "--out", d, "--delay", "0", "--max-pages", "10",
                        "--liens-externes", "0", "--ressources", "0"], check=True, capture_output=True, timeout=120)
        return json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8")), site.base


def res(html):
    return ho.analyser(html, {}, "https://ex.fr/", modules=[("a11y_structure", a11y_structure)])["a11y_structure"]


class TestStructure(unittest.TestCase):
    def test_cinq_controles(self):
        html = ('<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">'
                '<h1>T</h1><h2>A</h2><h4>Sauté</h4><h3>ok</h3><h2 hidden>x</h2>'
                '<input aria-describedby="aide-absente"><input aria-describedby="aide"><p id="aide">Aide</p>'
                '<iframe src="/carte"></iframe><iframe title="Carte" src="/c"></iframe><div hidden><iframe src="/x"></iframe></div>'
                '<iframe src="/pixel" width="1" height="1"></iframe>'
                '<span aria-label="5 sur 5">★★★★★</span><span role="img" aria-label="4 sur 5">★★★★</span>'
                '<nav aria-label="Pied de page"></nav><div aria-label="Zone" tabindex="0"></div>')
        self.assertEqual(res(html), {
            "titres_sautes": [{"signature": "h2 → h4", "n": 1, "exemple": "« Sauté »"}],
            "aria_ref_cassee": [{"signature": 'aria-describedby="aide-absente"', "n": 1}],
            "zoom_bloque": [{"signature": "maximum-scale=1, user-scalable=no", "n": 1}],
            "iframe_sans_titre": [{"signature": "/carte", "n": 1}],
            "aria_label_interdit": [{"signature": '<span aria-label="5 sur 5">', "n": 1}]})

    def test_viewport_hors_cobaye(self):
        self.assertEqual(res('<meta name="viewport" content="width=device-width, maximum-scale=2">')["zoom_bloque"], [])
        self.assertEqual(res('<meta name="viewport" content="width=device-width; maximum-scale=1.5">')["zoom_bloque"],
                         [{"signature": "maximum-scale=1.5", "n": 1}])

    def test_crawl(self):
        page = ('<html lang="fr"><head><meta name="viewport" content="width=device-width, user-scalable=0"><title>Structure '
                'de test assez longue</title></head><body><main><h1>T</h1><h3>Sous-partie</h3></main></body></html>')
        issues, _ = crawler({"/": (200, HTML, page)})
        self.assertEqual(issues["zoom_bloque"]["severity"], "haute")
        self.assertEqual((issues["titres_sautes"]["examples"][0]["signature"], issues["titres_sautes"]["examples"][0]["exemple"]),
                         ("h1 → h3", "« Sous-partie »"))


class TestFauxPositifs(unittest.TestCase):
    def test_titre_de_pied_de_page_apres_le_contenu(self):
        # composant de repère distinct (footer, aside, nav) : sa hiérarchie est jugée seule (WAVE : simple alerte)
        html = '<main><h1>T</h1><h2>A</h2></main><footer><h4>Contact</h4><h4>Liens</h4></footer><aside><h5>Note</h5></aside>'
        self.assertEqual(res(html)["titres_sautes"], [])

    def test_saut_reel_dans_un_repere_reste_signale(self):
        r = res('<footer><h2>Contact</h2><h4>Adresse</h4></footer>')["titres_sautes"]
        self.assertEqual(r, [{"signature": "h2 → h4", "n": 1, "exemple": "« Adresse »"}])

    def test_retour_au_contenu_apres_un_repere(self):
        # le pied de page ne remplace pas le niveau courant du contenu principal
        html = '<h1>T</h1><nav><h2>Menu</h2></nav><h2>A</h2><h3>B</h3>'
        self.assertEqual(res(html)["titres_sautes"], [])

    def test_saut_vers_le_haut_et_premier_titre_h2(self):
        self.assertEqual(res("<h2>A</h2><h3>B</h3><h4>C</h4><h2>D</h2><h3>E</h3>")["titres_sautes"], [])

    def test_composant_repete_un_seul_constat(self):
        html = "<h1>T</h1>" + "".join("<h2>Carte {0}</h2><h4>Détail {0}</h4>".format(i) for i in range(3))
        self.assertEqual(res(html)["titres_sautes"], [{"signature": "h2 → h4", "n": 3, "exemple": "« Détail 0 »"}])

    def test_titre_masque_ignore(self):
        self.assertEqual(res('<h1>T</h1><h4 aria-hidden="true">x</h4><h2>A</h2>')["titres_sautes"], [])

    def test_reference_vers_un_id_defini_plus_loin(self):
        html = '<input aria-labelledby="lib"><div aria-describedby="a b"></div><label id="lib">L</label><p id="a"></p><p id="b"></p>'
        self.assertEqual(res(html)["aria_ref_cassee"], [])

    def test_reference_cassee_et_aria_controls_ignore(self):
        r = res('<input aria-labelledby="x y"><p id="x"></p><button aria-controls="menu"></button>')["aria_ref_cassee"]
        self.assertEqual(r, [{"signature": 'aria-labelledby="y"', "n": 1}])

    def test_zoom_accepte(self):
        for contenu in ("width=device-width, maximum-scale=5", "width=device-width, initial-scale=1, user-scalable=yes",
                        "width=device-width, maximum-scale=2.0"):
            self.assertEqual(res('<meta name="viewport" content="{0}">'.format(contenu))["zoom_bloque"], [], contenu)

    def test_zoom_bloque_variantes(self):
        self.assertEqual(res('<meta name="viewport" content="user-scalable=0">')["zoom_bloque"],
                         [{"signature": "user-scalable=0", "n": 1}])
        self.assertEqual(res('<meta name="viewport" content="MAXIMUM-SCALE=1.0">')["zoom_bloque"],
                         [{"signature": "maximum-scale=1.0", "n": 1}])
        self.assertEqual(res('<meta name="viewport" content="maximum-scale=abc">')["zoom_bloque"], [])

    def test_iframes_masquees_ou_de_suivi_ignorees(self):
        html = ('<iframe src="/a" aria-hidden="true"></iframe><iframe src="/b" style="display:none"></iframe>'
                '<iframe src="/c" width="0" height="0"></iframe><iframe src="/d" height="1px"></iframe>'
                '<iframe src="/e" style="width:0;height:0;border:0"></iframe><iframe src="/f" width="1" height="1"></iframe>')
        self.assertEqual(res(html)["iframe_sans_titre"], [])

    def test_iframe_nommee_autrement(self):
        html = '<iframe src="/a" aria-label="Carte"></iframe><iframe src="/b" title="  "></iframe><iframe srcdoc="<p>x</p>"></iframe>'
        self.assertEqual(res(html)["iframe_sans_titre"], [{"signature": "/b", "n": 1}, {"signature": "srcdoc", "n": 1}])

    def test_aria_label_interdit_sur_generiques(self):
        html = ('<p aria-label="Intro">x</p><code aria-label="Code">y</code><div aria-label="Zone">z</div>'
                '<span aria-label="a" role="img"></span><div aria-label="b" role="region"></div><span aria-label="c" tabindex="0"></span>'
                '<span aria-label="d" aria-hidden="true"></span><section aria-label="S"></section><main aria-label="M"></main>'
                '<button aria-label="B"></button><a href="/" aria-label="L">l</a><nav aria-label="N"></nav><span>sans nom</span>')
        self.assertEqual(sorted(e["signature"] for e in res(html)["aria_label_interdit"]),
                         ['<code aria-label="Code">', '<div aria-label="Zone">', '<p aria-label="Intro">'])

    def test_resultats_deterministes_et_vides(self):
        vide = {c: [] for c in ("titres_sautes", "aria_ref_cassee", "zoom_bloque", "iframe_sans_titre", "aria_label_interdit")}
        self.assertEqual(res("<main><h1>Titre</h1><h2>Sous-titre</h2></main>"), vide)
        self.assertEqual(res(""), vide)

    def test_titre_non_ferme(self):
        self.assertEqual(res("<h1>T<h3>Sous</h3>")["titres_sautes"], [{"signature": "h1 → h3", "n": 1, "exemple": "« Sous »"}])


class TestRevue(unittest.TestCase):
    def test_iframe_sans_requete_ni_fragment(self):
        html = ('<iframe src="https://www.google.com/maps/embed/v1/place?key=AIzaSyA1234567890abcdefghijklmnop&q=Paris"></iframe>'
                '<iframe src="https://video.test/embed/123?token=0123456789abcdef0123#t=5"></iframe>'
                '<iframe src="//cdn.test/e?token=SECRET2"></iframe><iframe src="/carte?cle=SECRET3#x"></iframe>'
                '<iframe src="https://user:motdepasse@h.test/p?a=1"></iframe><iframe src="data:text/html,SECRET4"></iframe>')
        sortie = res(html)
        brut = json.dumps(sortie, ensure_ascii=False)
        for secret in ("AIza", "key=", "token", "0123456789abcdef", "SECRET", "motdepasse", "user:", "?", "#"):
            self.assertNotIn(secret, brut)
        self.assertEqual(sorted(e["signature"] for e in sortie["iframe_sans_titre"]),
                         ["/carte", "cdn.test/e", "data:", "h.test/p", "video.test/embed/123",
                          "www.google.com/maps/embed/v1/place"])

    def test_iframes_identiques_a_jeton_different_regroupees(self):
        html = '<iframe src="https://v.test/e/1?token=aaa"></iframe><iframe src="https://v.test/e/1?token=bbb"></iframe>'
        self.assertEqual(res(html)["iframe_sans_titre"], [{"signature": "v.test/e/1", "n": 2}])

    def test_aria_label_sur_role_sans_nom_explicite(self):
        html = ''.join('<div role="{0}" aria-label="x"></div>'.format(r) for r in ("generic", "none", "presentation", "GENERIC paragraph"))
        self.assertEqual(res(html)["aria_label_interdit"], [{"signature": '<div aria-label="x">', "n": 4}])
        self.assertEqual(res('<div role="region" aria-label="x"></div><div role="button" aria-label="y"></div>')["aria_label_interdit"], [])

    def test_aria_label_balises_completees(self):
        tags = ("pre", "abbr", "cite", "q", "kbd", "samp", "var", "bdi", "bdo", "data", "caption")
        html = "".join('<{0} aria-label="x"></{0}>'.format(t) for t in tags)
        self.assertEqual(sorted(e["signature"] for e in res(html)["aria_label_interdit"]),
                         sorted('<{0} aria-label="x">'.format(t) for t in tags))
        for t in ("header", "footer", "time", "mark", "label", "blockquote", "address"):
            self.assertEqual(res('<{0} aria-label="x"></{0}>'.format(t))["aria_label_interdit"], [], t)

    def test_contenteditable_non_signale(self):
        self.assertEqual(res('<div contenteditable aria-label="Message"></div><div contenteditable="true" aria-label="M"></div>')
                         ["aria_label_interdit"], [])

    def test_iframe_technique_ignoree(self):
        html = ('<iframe src="/a" tabindex="-1"></iframe><iframe src="/b" role="presentation"></iframe>'
                '<iframe src="/c" role="NONE"></iframe><iframe src="/d" tabindex="0"></iframe>')
        self.assertEqual(res(html)["iframe_sans_titre"], [{"signature": "/d", "n": 1}])

    def test_footer_ou_header_de_section_pas_un_repere(self):
        html = '<main><article><h1>T</h1><h2>A</h2><footer><h4>Auteur</h4></footer></article></main>'
        self.assertEqual(res(html)["titres_sautes"], [{"signature": "h2 → h4", "n": 1, "exemple": "« Auteur »"}])
        html = '<section><h2>A</h2><header><h4>B</h4></header></section>'
        self.assertEqual(res(html)["titres_sautes"], [{"signature": "h2 → h4", "n": 1, "exemple": "« B »"}])
        # pied de page de la page (hors article/section/main) : toujours un repère
        self.assertEqual(res('<main><h2>A</h2></main><footer><h4>Pied</h4></footer>')["titres_sautes"], [])
        # rôle explicite : repère même dans un article
        self.assertEqual(res('<article><h2>A</h2><div role="contentinfo"><h4>Pied</h4></div></article>')["titres_sautes"], [])

    def test_viewport_separateur_espace_et_template(self):
        r = res('<meta name="viewport" content="width=device-width initial-scale=1 maximum-scale=1 user-scalable=no">')
        self.assertEqual(r["zoom_bloque"], [{"signature": "maximum-scale=1, user-scalable=no", "n": 1}])
        r = res('<meta name="viewport" content="width=device-width, maximum-scale = 1">')
        self.assertEqual(r["zoom_bloque"], [{"signature": "maximum-scale=1", "n": 1}])
        self.assertEqual(res('<template><meta name="viewport" content="user-scalable=no"></template>')["zoom_bloque"], [])
        self.assertEqual(res('<noscript><meta name="viewport" content="user-scalable=no"></noscript>')["zoom_bloque"], [])

    def test_titre_sans_texte(self):
        self.assertEqual(res("<h1>T</h1><h2>A</h2><h4></h4>")["titres_sautes"],
                         [{"signature": "h2 → h4", "n": 1, "exemple": "« titre vide »"}])
        self.assertEqual(res('<h1>T</h1><h3><img src="l.png" alt="Logo Illith"></h3>')["titres_sautes"],
                         [{"signature": "h1 → h3", "n": 1, "exemple": "« Logo Illith »"}])

    def test_saut_dans_main_malgre_un_footer(self):
        html = '<header><h1>S</h1></header><main><h2>A</h2><h4>B</h4></main><footer><h4>Pied</h4></footer>'
        self.assertEqual(res(html)["titres_sautes"], [{"signature": "h2 → h4", "n": 1, "exemple": "« B »"}])

    def test_reperes_par_role_et_header_non_exempte(self):
        for role in ("complementary", "navigation", "contentinfo", "banner"):
            html = '<h1>T</h1><h2>A</h2><div role="{0}"><h5>X</h5></div>'.format(role)
            self.assertEqual(res(html)["titres_sautes"], [], role)
        # <header> n'est pas un repère : son h1 compte dans la suite du contenu
        self.assertEqual(res("<header><h1>S</h1></header><main><h3>B</h3></main>")["titres_sautes"],
                         [{"signature": "h1 → h3", "n": 1, "exemple": "« B »"}])

    def test_section_et_article_n_isolent_pas(self):
        self.assertEqual(res("<main><section><h2>A</h2><article><h4>B</h4></article></section></main>")["titres_sautes"],
                         [{"signature": "h2 → h4", "n": 1, "exemple": "« B »"}])

    def test_aria_labelledby_sur_generique(self):
        r = res('<span id="l">L</span><div aria-labelledby="l"></div>')["aria_label_interdit"]
        self.assertEqual(r, [{"signature": '<div aria-labelledby="l">', "n": 1}])


if __name__ == "__main__":
    unittest.main()
