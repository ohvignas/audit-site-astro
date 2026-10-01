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
import a11y_svg  # noqa: E402
from site_local import HTML, SiteLocal  # noqa: E402


def crawler(routes):
    """Crawl d'un SiteLocal (aucun réseau externe) → issues.json."""
    with SiteLocal(routes) as site, tempfile.TemporaryDirectory() as d:
        subprocess.run([sys.executable, str(SCRIPTS / "crawl_site.py"), site.url, "--out", d, "--delay", "0", "--max-pages", "10",
                        "--liens-externes", "0", "--ressources", "0"], check=True, capture_output=True, timeout=120)
        return json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8")), site.base


def res(html):
    return ho.analyser(html, {}, "https://ex.fr/", modules=[("a11y_svg", a11y_svg)])["a11y_svg"]


def vide(html):
    """Aucun constat d'aucune sorte pour ce HTML."""
    return res(html) == {"non_masques": [], "img_sans_nom": [], "dans_controle_nomme": []}


ICONE = '<span class="icone"><svg viewBox="0 0 24 24" fill="none"><path d="M1 1"/></svg></span>'


class TestSvg(unittest.TestCase):
    def test_regroupement_et_cas_ignores(self):
        html = (ICONE * 12
                + '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"></svg>'            # masqué
                + '<svg role="img" viewBox="0 0 10 10"><title>Note : 5 sur 5</title></svg>'    # nommé
                + '<svg role="img" viewBox="0 0 8 8"></svg>'                                   # image sans nom
                + '<div hidden><svg viewBox="0 0 1 1"></svg></div>'                            # ancêtre masqué
                + '<svg role="presentation"></svg><svg width="0" height="0"><defs></defs></svg>'
                + '<svg aria-label="Logo" viewBox="0 0 2 2"><svg viewBox="0 0 3 3"></svg></svg>'  # nommé, imbriqué
                + '<button><svg viewBox="0 0 16 16"></svg>Envoyer</button>'                    # bouton nommé : simple conseil
                + '<a href="/x"><svg viewBox="0 0 9 9"></svg></a>'                              # lien sans nom : laissé à T13
                + '<a href="/y">Voir <svg viewBox="0 0 7 7"></svg></a>')                        # lien nommé : simple conseil
        self.assertEqual(res(html), {
            "non_masques": [{"signature": "viewBox=0 0 24 24 fill=none parent=span.icone", "n": 12}],
            "img_sans_nom": [{"signature": "viewBox=0 0 8 8 fill=— parent=—", "n": 1}],
            "dans_controle_nomme": [{"signature": "viewBox=0 0 16 16 fill=— parent=button", "n": 1},
                                    {"signature": "viewBox=0 0 7 7 fill=— parent=a", "n": 1}]})

    def test_un_constat_pour_un_composant_sur_tout_le_site(self):
        page = '<html lang="fr"><head><title>Page {0} de test assez longue</title></head><body><main>{1}<a href="/b">b</a></main></body></html>'
        issues, base = crawler({"/": (200, HTML, page.format("A", ICONE * 12)), "/b": (200, HTML, page.format("B", ICONE * 12))})
        it = issues["svg_non_masque"]
        self.assertEqual((it["count"], it["severity"], it["domaine"], len(it["examples"])), (24, "moyenne", "Accessibilité", 1))
        self.assertEqual((it["examples"][0]["occurrences"], it["examples"][0]["pages"]), (24, 2))
        self.assertNotIn("svg_img_sans_nom", issues)
        self.assertNotIn("svg_redondant_controle", issues)

    def test_severites_et_exemples_des_trois_constats(self):
        page = ('<html lang="fr"><head><title>Page de test assez longue</title></head><body><main>'
                '<svg role="img" viewBox="0 0 8 8"></svg><a href="/b">Voir <svg viewBox="0 0 7 7"></svg></a></main></body></html>')
        issues, _ = crawler({"/": (200, HTML, page), "/b": (200, HTML, page)})
        self.assertEqual((issues["svg_img_sans_nom"]["severity"], issues["svg_img_sans_nom"]["count"]), ("haute", 2))
        self.assertEqual((issues["svg_redondant_controle"]["severity"], issues["svg_redondant_controle"]["count"]), ("basse", 2))
        self.assertNotIn("svg_non_masque", issues)

    def test_cas_wave_etoiles_et_pictogrammes_donnent_peu_de_constats(self):
        # 74 flèches, 30 étoiles Google (deux jaunes), 24 icônes colorées : une poignée de signatures, pas 128 constats
        html = ('<span class="fleche"><svg viewBox="0 0 24 24" fill="none"><path d="M1 1"/></svg></span>' * 74
                + '<div class="etoile"><svg viewBox="0 0 20 20" fill="#FBBC05"><path d="M1 1"/></svg></div>' * 20
                + '<div class="etoile"><svg viewBox="0 0 20 20" fill="#FFC037"><path d="M1 1"/></svg></div>' * 10
                + '<i class="ico"><svg viewBox="0 0 32 32" fill="#e91e63"></svg></i>' * 24)
        r = res(html)["non_masques"]
        self.assertEqual(sorted((e["signature"], e["n"]) for e in r), [
            ("viewBox=0 0 20 20 fill=#FBBC05 parent=div.etoile", 20),
            ("viewBox=0 0 20 20 fill=#FFC037 parent=div.etoile", 10),
            ("viewBox=0 0 24 24 fill=none parent=span.fleche", 74),
            ("viewBox=0 0 32 32 fill=#e91e63 parent=i.ico", 24)])


class TestFauxPositifs(unittest.TestCase):
    """Cas qui ne doivent produire AUCUN constat (ni principal, ni conseil)."""

    def test_ancetre_aria_hidden(self):
        self.assertTrue(vide('<div aria-hidden="true"><span><svg viewBox="0 0 24 24"></svg></span></div>'))

    def test_svg_aria_hidden(self):
        self.assertTrue(vide('<svg aria-hidden="true" viewBox="0 0 24 24"></svg>'))

    def test_role_presentation_et_none(self):
        self.assertTrue(vide('<svg role="presentation" viewBox="0 0 1 1"></svg><svg role="none" viewBox="0 0 1 1"></svg>'
                             '<svg role=" NONE " viewBox="0 0 1 1"></svg>'))

    def test_role_img_avec_aria_label(self):
        self.assertTrue(vide('<svg role="img" aria-label="Logo" viewBox="0 0 1 1"></svg>'))

    def test_titre(self):
        self.assertTrue(vide('<svg viewBox="0 0 1 1"><title>Note</title></svg>'))
        self.assertTrue(vide('<svg role="img" viewBox="0 0 1 1"><title>Note</title></svg>'))

    def test_aria_labelledby_vers_un_id_existant(self):
        self.assertTrue(vide('<svg role="img" aria-labelledby="t" viewBox="0 0 1 1"></svg><p id="t">Note</p>'))
        self.assertTrue(vide('<p id="t">Note</p><svg aria-labelledby="t" viewBox="0 0 1 1"></svg>'))
        self.assertTrue(vide('<svg role="img" aria-labelledby="a b" viewBox="0 0 1 1"><title id="b">N</title></svg>'))

    def test_svg_dans_template_ou_element_masque(self):
        for h in ('<template><svg viewBox="0 0 1 1"></svg></template>', '<div hidden><svg viewBox="0 0 1 1"></svg></div>',
                  '<div style="display:none"><svg viewBox="0 0 1 1"></svg></div>', '<div class="hidden"><svg viewBox="0 0 1 1"></svg></div>',
                  '<svg style="display: none" viewBox="0 0 1 1"></svg>', '<noscript><svg viewBox="0 0 1 1"></svg></noscript>',
                  '<span hidden><a href="/x">Voir <svg viewBox="0 0 1 1"></svg></a></span>'):
            self.assertTrue(vide(h), h)

    def test_conteneur_de_definitions_et_imbrique(self):
        self.assertTrue(vide('<svg width="0" height="0" style="position:absolute"><symbol id="a"></symbol></svg>'))
        self.assertTrue(vide('<svg height="0"><defs></defs></svg>'))
        self.assertTrue(vide('<svg aria-label="Logo"><svg viewBox="0 0 1 1"><g></g></svg></svg>'))

    def test_svg_seul_contenu_d_un_lien_ou_bouton_sans_nom_laisse_a_t13(self):
        self.assertTrue(vide('<a href="/x"><svg viewBox="0 0 1 1"></svg></a>'))
        self.assertTrue(vide('<button type="button"><svg viewBox="0 0 1 1"></svg></button>'))
        self.assertTrue(vide('<a href="/x"><span><svg viewBox="0 0 1 1"></svg></span> <span aria-hidden="true">texte masqué</span></a>'))

    def test_svg_dans_lien_ou_bouton_nomme_n_est_pas_le_constat_principal(self):
        for h in ('<button aria-label="Fermer"><svg viewBox="0 0 1 1"></svg></button>',
                  '<a href="/x" title="Accueil"><svg viewBox="0 0 1 1"></svg></a>',
                  '<a href="/x">Contact <svg viewBox="0 0 1 1"></svg></a>',
                  '<button><svg viewBox="0 0 1 1"></svg> <span class="sr-only">Menu</span></button>',
                  '<a href="/x"><svg viewBox="0 0 1 1"></svg><img src="/l.png" alt="Logo"></a>'):
            r = res(h)
            self.assertEqual(r["non_masques"], [], h)
            self.assertEqual(r["img_sans_nom"], [], h)
            self.assertEqual([e["n"] for e in r["dans_controle_nomme"]], [1], h)  # au plus un conseil séparé

    def test_svg_nomme_dans_un_lien_donne_un_nom_au_lien(self):
        self.assertTrue(vide('<a href="/"><svg role="img" aria-label="Accueil" viewBox="0 0 1 1"></svg></a>'))
        r = res('<a href="/"><svg role="img" aria-label="Accueil" viewBox="0 0 1 1"></svg><svg viewBox="0 0 2 2"></svg></a>')
        self.assertEqual((r["non_masques"], r["img_sans_nom"], len(r["dans_controle_nomme"])), ([], [], 1))

    def test_lien_sans_href_n_est_pas_un_controle(self):
        self.assertEqual(res('<a><svg viewBox="0 0 1 1"></svg></a>')["non_masques"],
                         [{"signature": "viewBox=0 0 1 1 fill=— parent=a", "n": 1}])


class TestVrais_positifs(unittest.TestCase):
    def test_icone_non_masquee_hors_controle(self):
        self.assertEqual(res('<p>Texte <svg viewBox="0 0 1 1"></svg></p>')["non_masques"],
                         [{"signature": "viewBox=0 0 1 1 fill=— parent=p", "n": 1}])

    def test_signature_parent_et_deux_premieres_classes_triees(self):
        r = res('<div class="z b a"><svg viewBox="0 0 2 2" fill="red"></svg></div>')["non_masques"]
        self.assertEqual(r[0]["signature"], "viewBox=0 0 2 2 fill=red parent=div.a.b")

    def test_aria_labelledby_vide_ou_vers_un_id_absent_n_est_pas_un_nom(self):
        self.assertEqual(len(res('<svg role="img" aria-labelledby="" viewBox="0 0 1 1"></svg>')["img_sans_nom"]), 1)
        self.assertEqual(len(res('<svg role="img" aria-labelledby="absent" viewBox="0 0 1 1"></svg>')["img_sans_nom"]), 1)
        self.assertEqual(len(res('<svg aria-labelledby="absent" viewBox="0 0 1 1"></svg>')["non_masques"]), 1)

    def test_aria_label_ou_titre_vides_ne_nomment_pas(self):
        self.assertEqual(len(res('<svg role="img" aria-label="  " viewBox="0 0 1 1"></svg>')["img_sans_nom"]), 1)
        self.assertEqual(len(res('<svg role="img" viewBox="0 0 1 1"><title> </title></svg>')["img_sans_nom"]), 1)

    def test_role_graphics_sans_nom(self):
        self.assertEqual(len(res('<svg role="graphics-document" viewBox="0 0 1 1"></svg>')["img_sans_nom"]), 1)

    def test_svg_auto_ferme(self):
        self.assertEqual(len(res('<p><svg viewBox="0 0 1 1"/></p><p><svg viewBox="0 0 1 1"/></p>')["non_masques"]), 1)

    def test_titre_du_document_ne_nomme_pas_un_svg(self):
        r = res('<html><head><title>Page</title></head><body><svg viewBox="0 0 1 1"></svg></body></html>')
        self.assertEqual(len(r["non_masques"]), 1)

    def test_resultat_est_du_json_et_deterministe(self):
        h = ICONE * 3 + '<svg role="img" viewBox="0 0 8 8"></svg>'
        self.assertEqual(json.dumps(res(h)), json.dumps(res(h)))


if __name__ == "__main__":
    unittest.main()
