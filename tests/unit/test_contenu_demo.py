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
import contenu_demo  # noqa: E402
import html_observateurs as ho  # noqa: E402
from site_local import HTML, SiteLocal  # noqa: E402


def motifs(html):
    r = ho.analyser(html, {}, "https://ex.fr/", modules=[("contenu_demo", contenu_demo)])["contenu_demo"]
    return [(m["motif"], m["ou"]) for m in r["motifs"]]


class TestMotifs(unittest.TestCase):
    def test_description_et_texte(self):  # beta.illith.com /contact (2026-10-01)
        html = ('<html><head><title>Contact</title><meta name="description" content="Page de démonstration livrée avec '
                'le thème — à remplacer par la vôtre"></head><body><p>Lorem ipsum dolor sit amet.</p>'
                "<code>lorem ipsum</code><p>Nous allons remplacer le tableur partagé.</p></body></html>")
        self.assertEqual(motifs(html), [("texte à remplacer", "description"), ("page de démonstration", "description"),
                                        ("lorem ipsum", "texte")])

    def test_hors_cobaye(self):
        self.assertEqual(motifs("<html><head><title>Welcome to Astro</title></head><body></body></html>"),
                         [("gabarit de démarrage", "titre")])
        self.assertEqual(motifs("<p>Your company here</p>"), [("coordonnées fictives", "texte")])
        self.assertEqual(motifs('<p hidden>Lorem ipsum</p><pre>dolor sit amet</pre><p>Exemple : John Doe, gérant.</p>'), [])

    def test_vrai_contact_astrotan(self):
        html = ('<html><head><title>Contact | ILLITH</title><meta name="description" content="Page de démonstration livrée '
                'avec AstroTan — à remplacer par la vôtre"><meta property="og:description" content="Page de démonstration '
                'livrée avec AstroTan — à remplacer par la vôtre"></head><body><h1>Contact</h1></body></html>')
        self.assertEqual(motifs(html), [("texte à remplacer", "description"), ("page de démonstration", "description")])


class TestFauxPositifs(unittest.TestCase):
    """Un site légitime qui parle du faux texte, ou qui le cite, ne doit pas être signalé."""

    def test_page_sur_la_typographie(self):
        html = ("<html><head><title>Lorem Ipsum : origine et usage du faux texte</title>"
                '<meta name="description" content="Le lorem ipsum, ce faux texte latin utilisé par les imprimeurs depuis le XVIe siècle."></head>'
                "<body><h1>Lorem Ipsum</h1><p>Le lorem ipsum sert à juger une mise en page sans lire le contenu.</p>"
                "<p>Le passage classique commence par « Lorem ipsum dolor sit amet, consectetur adipiscing elit ».</p>"
                '<p>Le texte “Lorem ipsum dolor sit amet” vient de Cicéron.</p>'
                '<p>On écrit souvent "Lorem ipsum dolor sit amet" dans les maquettes.</p>'
                "<blockquote><q>dolor sit amet</q></blockquote><p>Voir <cite>consectetur adipiscing</cite>.</p></body></html>")
        self.assertEqual(motifs(html), [])

    def test_article_technique_avec_code(self):
        html = ("<html><body><p>Dans le fichier :</p><pre><code>description: 'Page de démonstration livrée avec le thème — "
                "à remplacer par la vôtre'</code></pre><p>Tapez <kbd>Welcome to Astro</kbd> ou <samp>Your company here</samp>.</p>"
                "<script>var t='lorem ipsum dolor sit amet'</script><style>/* lorem ipsum dolor */</style>"
                "<template><p>Lorem ipsum dolor</p></template><noscript>Lorem ipsum dolor</noscript>"
                '<div style="display:none">Lorem ipsum dolor sit amet</div><div aria-hidden="true">Lorem ipsum dolor</div></body></html>')
        self.assertEqual(motifs(html), [])

    def test_expressions_voisines(self):
        for texte in ("Nous allons remplacer le tableur partagé.", "Il faut remplacer par la suite les anciens postes ?",
                      "Visitez notre page de démonstration produit.", "Demandez une démo de notre outil.",
                      "Contactez John Doe, notre gérant.", "Voir l'exemple sur example.com.",
                      "Un lorem seul ou un ipsum seul ne disent rien.", "Welcome to Astronomy 101.",
                      "Please replace this file with the new one.", "Ces postes sont à remplacer par la suite."):
            self.assertEqual(motifs("<p>%s</p>" % texte), [], texte)

    def test_citation_dans_le_titre_ou_la_description(self):
        html = ('<html><head><title>Que faire de « Welcome to Astro » après l\'installation ?</title>'
                '<meta name="description" content="Supprimer la phrase « Page de démonstration livrée avec le thème — à remplacer par la vôtre » du site."></head>'
                "<body></body></html>")
        self.assertEqual(motifs(html), [])

    def test_vrai_placeholder_apres_une_citation(self):
        html = '<p>Voir « Lorem ipsum dolor sit amet » plus haut.</p><p>Lorem ipsum dolor sit amet, consectetur.</p>'
        self.assertEqual(motifs(html), [("lorem ipsum", "texte")])


class TestObservateur(unittest.TestCase):
    def test_methodes_dans_la_classe(self):
        for m in ("debut", "fin", "texte"):
            self.assertIsNot(getattr(contenu_demo.Observateur, m), getattr(ho.Observateur, m), m)

    def test_texte_coupe_par_un_commentaire_ou_une_balise_en_ligne(self):
        html = "<p>Lorem <!-- x -->ipsum dolor sit amet</p><p>Texte <b>à remplacer par</b> la vôtre</p>"
        self.assertEqual(motifs(html), [("lorem ipsum", "texte"), ("texte à remplacer", "texte")])

    def test_resultat_json_et_signature(self):
        r = ho.analyser("<p>Your company here</p>", {}, "https://ex.fr/", modules=[("contenu_demo", contenu_demo)])["contenu_demo"]
        m = r["motifs"][0]
        self.assertEqual((m["n"], m["ou"], m["motif"]), (1, "texte", "coordonnées fictives"))
        self.assertTrue(m["signature"].startswith("coordonnées fictives (texte) : « "))
        self.assertIn("Your company here", m["signature"])
        json.dumps(r, allow_nan=False)

    def test_page_sans_motif(self):
        self.assertEqual(motifs("<html><head><title>Contact</title></head><body><p>Bonjour.</p></body></html>"), [])


class TestCrawl(unittest.TestCase):
    def test_constat_regroupe(self):
        page = ('<html lang="fr"><head><title>Contact de démonstration</title><meta name="description" content="Page de '
                'démonstration livrée avec le thème — à remplacer par la vôtre"></head><body><main><p>x</p></main></body></html>')
        with SiteLocal({"/": (200, HTML, page)}) as site, tempfile.TemporaryDirectory() as d:
            subprocess.run([sys.executable, str(SCRIPTS / "crawl_site.py"), site.url, "--out", d, "--delay", "0",
                            "--max-pages", "3", "--liens-externes", "0", "--ressources", "0"], check=True, capture_output=True, timeout=120)
            it = json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8"))["contenu_demo"]
        self.assertEqual((it["count"], it["severity"], it["domaine"]), (2, "moyenne", "Contenu"))
        self.assertTrue(all(e["exemples_pages"] == [site.url] for e in it["examples"]))


if __name__ == "__main__":
    unittest.main()
