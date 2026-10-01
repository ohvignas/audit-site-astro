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


LOREM = "<p>Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>"
GABARIT = [("gabarit de démarrage", "titre")]


class TestFrontieresDeBloc(unittest.TestCase):
    """Revue T7 I1 : un guillemet orphelin d'un autre bloc ne fait pas taire un vrai placeholder ; la jointure ne fabrique pas de motif."""

    def test_guillemet_orphelin_ailleurs(self):
        for avant in ("<nav>« Page précédente</nav>", "<nav>&laquo; Précédent</nav>", '<p>Écran 27" 4K</p>',
                      "<p>He said \u201chello</p>", '<p>"a" "b" "c</p>'):
            self.assertEqual(motifs(avant + LOREM), [("lorem ipsum", "texte")], avant)

    def test_jointure_entre_blocs_sans_motif(self):
        self.assertEqual(motifs("<ul><li>Fenêtres à remplacer</li><li>Par votre menuisier habituel</li></ul>"), [])
        self.assertEqual(motifs("<h2>Sed do</h2><p>Lorem</p><p>ipsum dolor</p>"), [])

    def test_description_independante_de_og(self):
        html = ('<head><meta name="description" content="Écran 27&quot;"><meta property="og:description" '
                'content="Lorem ipsum dolor sit amet"></head>')
        self.assertEqual(motifs(html), [("lorem ipsum", "description")])

    def test_phrase_coupee_par_une_balise_en_ligne_reste_lue(self):
        self.assertEqual(motifs("<p>Lorem <em>ipsum</em> dolor sit</p>"), [("lorem ipsum", "texte")])

    def test_guillemets_simples_et_longue_citation(self):
        for cite_ in ("<p>'Lorem ipsum dolor sit amet'</p>", "<p>\u2018Lorem ipsum dolor sit amet\u2019</p>",
                      "<p>\u201eLorem ipsum dolor sit amet\u201c</p>",
                      "<p>« " + "Le texte classique des imprimeurs, repris partout, " * 5 + "Lorem ipsum dolor sit amet »</p>"):
            self.assertEqual(motifs(cite_), [], cite_)

    def test_gabarit_basics_html_reel(self):  # examples/basics : le code est exclu, le reste du h1 doit suffire
        html = "<h1>To get started, open the <code><pre>src/pages</pre></code> directory in your project.</h1>"
        self.assertEqual(motifs(html), [("gabarit de démarrage", "texte")])


class TestRestesDesGabarits(unittest.TestCase):
    """Revue T7 I2 : chaque ancre sûre a son test de rappel et son test de faux positif."""

    def test_titre_ou_description_par_defaut_blog_basics_starlight(self):
        self.assertEqual(motifs("<head><title>Astro Basics</title></head>"), GABARIT)
        self.assertEqual(motifs("<head><title>Astro Blog</title></head>"), GABARIT)
        self.assertEqual(motifs("<head><title>Getting started | My Docs</title></head>"), GABARIT)
        self.assertEqual(motifs('<head><meta name="description" content="Welcome to my website!"></head>'),
                         [("gabarit de démarrage", "description")])
        self.assertEqual(motifs('<head><meta property="og:description" content="Get started building your docs site with Starlight."></head>'),
                         [("gabarit de démarrage", "description")])
        self.assertEqual(motifs('<head><meta name="description" content="A guide in my new Starlight docs site."></head>'),
                         [("gabarit de démarrage", "description")])

    def test_titre_ou_description_par_defaut_faux_positifs(self):
        for titre in ("Astro Blog : nos actualités sur le framework", "Notre avis sur Astro Basics et ses limites", "Mes docs"):
            self.assertEqual(motifs("<head><title>%s</title></head>" % titre), [], titre)
        for desc in ("Welcome to my website, a place about woodworking.", "Bienvenue sur Astro Blog", "Get started building with Astro."):
            self.assertEqual(motifs('<head><meta name="description" content="%s"></head>' % desc), [], desc)

    def test_phrases_longues_du_gabarit(self):
        self.assertEqual(motifs("<p>Welcome to the official Astro blog starter template</p>"), [("gabarit de démarrage", "texte")])
        self.assertEqual(motifs("<p>Congrats on setting up a new Starlight project!</p>"), [("gabarit de démarrage", "texte")])
        self.assertEqual(motifs("<h1>\U0001F9D1\u200d\U0001F680 Hello, Astronaut!</h1>"), [("gabarit de démarrage", "texte")])

    def test_phrases_longues_faux_positifs(self):
        self.assertEqual(motifs("<p>Le chat dit Hello, Astronaut! au chien.</p>"), [])
        self.assertEqual(motifs("<p>Le blog officiel d'Astro propose un gabarit de blog.</p>"), [])

    def test_lorem_mots_de_queue(self):
        for t in ("Sed do eiusmod tempor", "ut labore et dolore, incididunt ut labore", "Ut enim ad minim veniam", "adipisicing elit",
                  "Vitae ultricies leo integer"):
            self.assertEqual(motifs("<p>%s</p>" % t), [("lorem ipsum", "texte")], t)

    def test_lorem_mots_de_queue_faux_positifs(self):
        for t in ("Ad hoc, minimum veniam au quotidien.", "Un sed de plus.", "Il travaille ut labore."):
            self.assertEqual(motifs("<p>%s</p>" % t), [], t)

    def test_copyright_fictif(self):
        for t in ("© 2026 Votre Nom. Tous droits réservés.", "Copyright Your Company", "&copy; 2026 Your name here", "© Company Name",
                  "© Nom de l'entreprise"):
            self.assertEqual(motifs("<footer>%s</footer>" % t), [("coordonnées fictives", "texte")], t)

    def test_copyright_faux_positifs(self):
        for t in ("<label>Votre nom</label>", "<h1>Your Name</h1>", "© 2026 ILLITH", "Nom de l'entreprise : ILLITH", "Votre nom complet"):
            self.assertEqual(motifs("<div>%s</div>" % t), [], t)

    def test_liens_fictifs(self):
        for href in ("mailto:contact@example.com", "mailto:hello@yourdomain.com", "mailto:moi@votredomaine.fr", "tel:+15555550123",
                     "tel:(555) 123-4567", "tel:0123456789", "tel:01 23 45 67 89"):
            self.assertEqual(motifs('<a href="%s">Contact</a>' % href), [("coordonnées fictives", "texte")], href)

    def test_liens_fictifs_faux_positifs(self):
        for html in ('<a href="mailto:contact@illith.com">c</a>', '<a href="tel:+33612345678">t</a>', "<p>Écrire à email@example.com</p>",
                     "<code>mailto:contact@example.com</code>", '<a hidden href="mailto:contact@example.com">c</a>',
                     '<a href="https://example.com/">exemple</a>', '<a href="tel:+33 4 91 02 03 04">t</a>'):
            self.assertEqual(motifs(html), [], html)

    def test_page_d_attente_dans_le_titre(self):
        for t in ("Coming soon", "Under construction", "Site en construction", "Bientôt disponible"):
            self.assertEqual(motifs("<head><title>%s</title></head>" % t), GABARIT, t)

    def test_page_d_attente_faux_positifs(self):
        self.assertEqual(motifs("<head><title>Coming soon à Paris : notre boutique</title></head><body><span>Bientôt disponible</span></body>"), [])


class TestAReplacerAgence(unittest.TestCase):
    """Revue T7 I3 : phrases plausibles d'une agence de refonte."""

    def test_agence_non_signalee(self):
        for t in ("Votre ancien site est à remplacer par votre nouveau site Astro.",
                  "Les pages obsolètes sont à remplacer par vos nouvelles pages optimisées.",
                  "Le champ est à remplacer par le contenu de votre base.", "Cette fenêtre est à remplacer par un vrai bois massif."):
            self.assertEqual(motifs("<p>%s</p>" % t), [], t)

    def test_gabarit_signale(self):
        for t in ("Texte à remplacer par la vôtre", "À remplacer par votre texte", "à remplacer par votre propre logo",
                  "à remplacer par un vrai texte", "à remplacer par le contenu réel", "(à remplacer)"):
            self.assertEqual(motifs("<p>%s</p>" % t), [("texte à remplacer", "texte")], t)


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
