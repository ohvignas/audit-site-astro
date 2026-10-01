import json
import pathlib
import re
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
import a11y_noms  # noqa: E402


def crawler(routes):
    """Crawl d'un SiteLocal (aucun réseau externe) → issues.json."""
    with SiteLocal(routes) as site, tempfile.TemporaryDirectory() as d:
        subprocess.run([sys.executable, str(SCRIPTS / "crawl_site.py"), site.url, "--out", d, "--delay", "0", "--max-pages", "10",
                        "--liens-externes", "0", "--ressources", "0"], check=True, capture_output=True, timeout=120)
        return json.loads(pathlib.Path(d, "issues.json").read_text(encoding="utf-8")), site.base


def res(html):
    return ho.analyser(html, {}, "https://ex.fr/", modules=[("a11y_noms", a11y_noms)])["a11y_noms"]


def liens(html):
    return sorted(re.search(r'href="([^"]*)"', e["signature"]).group(1) for e in res(html)["liens_sans_nom"])


def nb_boutons(html):
    return sum(e["n"] for e in res(html)["boutons_sans_nom"])


HTML_TEST = ('<a href="/a">Texte</a>'
             '<a href="/b"><img src="x.png" alt="Logo"></a>'
             '<a href="/c"><svg><title>Accueil</title></svg></a>'
             '<a href="/d"><svg aria-hidden="true"></svg></a>'                      # sans nom
             '<a href="/e" aria-label="Fermer"></a>'
             '<a href="/f" aria-labelledby="lib"></a><span id="lib">Panier</span>'   # référence placée après
             '<a href="/g" aria-labelledby="absent"></a>'                            # sans nom
             '<a href="/h"><span aria-hidden="true">→</span></a>'                    # sans nom
             '<a name="ancre"></a>'
             '<button><svg aria-hidden="true"></svg></button>'                       # sans nom
             '<button title="Rechercher"><svg aria-hidden="true"></svg></button>'
             '<input type="submit"><input type="button">'                            # le second : sans nom
             '<div role="button" tabindex="0"></div>'                                # sans nom
             '<button hidden></button>')


class TestNoms(unittest.TestCase):
    def test_liens_et_boutons(self):
        r = res(HTML_TEST)
        hrefs = sorted(re.search(r'href="([^"]*)"', e["signature"]).group(1) for e in r["liens_sans_nom"])
        self.assertEqual(hrefs, ["/d", "/g", "/h"])
        self.assertIn({"signature": '<a href="/d"> contenu : svg masqué', "n": 1}, r["liens_sans_nom"])
        self.assertEqual(sum(e["n"] for e in r["boutons_sans_nom"]), 3)

    def test_sr_only_compte_comme_nom(self):
        # Tailwind / React : bouton d'icône avec libellé réservé aux lecteurs d'écran
        self.assertEqual(liens('<a href="/p"><svg aria-hidden="true"></svg><span class="sr-only">Panier</span></a>'
                               '<a href="/q"><span class="visually-hidden">Compte</span></a>'), [])
        self.assertEqual(nb_boutons('<button><svg aria-hidden="true"></svg><span class="sr-only">Fermer</span></button>'), 0)

    def test_sous_arbre_aria_hidden_exclu(self):
        self.assertEqual(liens('<a href="/m"><span class="sr-only" aria-hidden="true">Menu</span></a>'), ["/m"])
        self.assertEqual(nb_boutons('<button><span hidden>Menu</span></button>'), 1)

    def test_bouton_icone_avec_aria_label(self):
        self.assertEqual(nb_boutons('<button type="button" aria-label="Ouvrir le menu"><svg aria-hidden="true"><path d="M0 0"/></svg></button>'), 0)

    def test_lien_sans_href_n_est_pas_un_lien(self):
        self.assertEqual(liens('<a><svg aria-hidden="true"></svg></a><a class="x"></a><a name="n"></a>'), [])

    def test_nom_par_descendant(self):
        self.assertEqual(liens('<a href="/1"><span aria-label="Panier"></span></a>'
                               '<a href="/2"><i role="img" aria-label="Aide"></i></a>'
                               '<a href="/3"><svg aria-label="Logo"></svg></a>'
                               '<a href="/4"><svg role="img" aria-labelledby="t"></svg></a><span id="t">Titre</span>'
                               '<a href="/5"><img src="x.png" alt=""></a>'), ["/5"])

    def test_aria_labelledby_resolu_apres_et_vide(self):
        self.assertEqual(liens('<a href="/a" aria-labelledby="x y"></a><b id="y">Mot</b>'), [])
        self.assertEqual(liens('<a href="/b" aria-labelledby="z"></a><b id="z"> </b>'), ["/b"])
        self.assertEqual(liens('<a href="/c" aria-labelledby="w"></a><b id="w" aria-label="Libellé"></b>'), [])

    def test_labelledby_prime_sur_le_texte_masque_de_la_cible(self):
        # la cible peut être masquée : son texte compte quand même (accname)
        self.assertEqual(liens('<a href="/a" aria-labelledby="c"></a><span id="c" hidden>Caché</span>'), [])

    def test_title_en_dernier_recours(self):
        self.assertEqual(liens('<a href="/a" title="Accueil"></a><a href="/b"><span title="Aide"></span></a>'), [])
        self.assertEqual(nb_boutons('<button title="Chercher"></button>'), 0)

    def test_inputs(self):
        self.assertEqual(nb_boutons('<input type="submit"><input type="reset">'), 0)
        self.assertEqual(nb_boutons('<input type="button" value="Ok"><input type="submit" value="Envoyer">'), 0)
        self.assertEqual(nb_boutons('<input type="button" value=""><input type="button">'), 2)
        self.assertEqual(nb_boutons('<input type="button" aria-label="Ok"><input type="button" title="Ok">'), 0)
        # type=image : alt (ou aria-label, title) requis, pas de nom par défaut
        self.assertEqual(nb_boutons('<input type="image" src="a.png" alt="Rechercher"><input type="image" src="b.png">'), 1)
        self.assertEqual(nb_boutons('<input type="text"><input type="checkbox"><input>'), 0)

    def test_role_button_sur_lien_et_div(self):
        self.assertEqual(nb_boutons('<div role="button">Ok</div><span role="button" aria-label="X"></span>'), 0)
        self.assertEqual(nb_boutons('<span role="button"><svg aria-hidden="true"></svg></span>'), 1)

    def test_controles_masques_ignores(self):
        self.assertEqual(liens('<div hidden><a href="/x"></a></div><a href="/y" aria-hidden="true"></a>'), [])
        self.assertEqual(nb_boutons('<div style="display:none"><button></button></div><template><button></button></template>'), 0)

    def test_signature_contenu_et_groupes(self):
        r = res('<button class="b a c"><svg aria-hidden="true"><path d="M"/><g></g><rect/></svg></button>'
                '<button class="b a c"><svg aria-hidden="true"><path d="M"/><g></g><rect/></svg></button><button></button>')
        self.assertEqual(r["boutons_sans_nom"], [
            {"signature": '<button class="a b"> contenu : svg masqué, path masqué, g masqué', "n": 2},
            {"signature": '<button> contenu : vide', "n": 1}])

    def test_texte_et_espaces_insecables(self):
        self.assertEqual(liens('<a href="/n">&nbsp;</a><a href="/o"><span> </span></a>'), ["/n", "/o"])
        self.assertEqual(liens('<a href="/ok">  <b>Mot</b> </a>'), [])

    def test_script_et_style_ne_sont_pas_un_nom(self):
        self.assertEqual(liens('<a href="/s"><script>var a=1;</script><style>.a{}</style></a>'), ["/s"])

    def test_imbrication(self):
        # lien contenant un bouton nommé : le texte compte pour les deux ouverts
        self.assertEqual(liens('<a href="/z"><button>Go</button></a>'), [])

    def test_resultat_json_strict(self):
        json.dumps(res(HTML_TEST), allow_nan=False)

    def test_crawl(self):
        page = ('<html lang="fr"><head><title>Barre d outils de test</title></head><body><main>'
                '<a href="/x"><svg aria-hidden="true"></svg></a><button class="fermer"><span aria-hidden="true">×</span></button>'
                '</main></body></html>')
        issues, _ = crawler({"/": (200, HTML, page)})
        self.assertEqual((issues["lien_sans_nom"]["severity"], issues["lien_sans_nom"]["domaine"]), ("haute", "Accessibilité"))
        self.assertEqual(issues["bouton_sans_nom"]["examples"][0]["signature"], '<button class="fermer"> contenu : span masqué')

    def test_crawl_propre_aucune_cle(self):
        page = ('<html lang="fr"><head><title>Barre d outils de test</title></head><body><main>'
                '<a href="/x" aria-label="Accueil"><svg aria-hidden="true"></svg></a>'
                '<button><span class="sr-only">Fermer</span></button></main></body></html>')
        issues, _ = crawler({"/": (200, HTML, page)})
        self.assertNotIn("lien_sans_nom", issues)
        self.assertNotIn("bouton_sans_nom", issues)


if __name__ == "__main__":
    unittest.main()
