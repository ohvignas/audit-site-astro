import json
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest

ICI = pathlib.Path(__file__).resolve().parent
RACINE = ICI.parents[1]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ICI))
import extraction_detecteurs as extraction  # noqa: E402
import html_observateurs as ho  # noqa: E402
from site_local import HTML, SiteLocal  # noqa: E402


class Journal(ho.Observateur):
    def __init__(self, entetes=None, url="https://ex.fr/"):
        super().__init__(entetes, url)
        self.ev = []

    def debut(self, noeud, pile):
        self.ev.append(("debut", noeud["tag"], noeud["masque"], [p["tag"] for p in pile]))

    def fin(self, noeud, pile):
        self.ev.append(("fin", noeud["tag"]))

    def texte(self, donnees, pile):
        if donnees.strip():
            self.ev.append(("texte", donnees.strip(), ho.visible(pile)))

    def resultat(self):
        return {"n": len(self.ev)}


def diffuser(html):
    j = Journal()
    ho.Diffuseur([j]).analyser(html)
    return j.ev


class TestDiffuseur(unittest.TestCase):
    def test_pile_masque_herite_et_elements_vides(self):
        self.assertEqual(diffuser('<div hidden><p>a<img alt="x"></p></div><br><span>b</span>'), [
            ("debut", "div", True, []), ("debut", "p", True, ["div"]), ("texte", "a", False),
            ("debut", "img", True, ["div", "p"]), ("fin", "img"), ("fin", "p"), ("fin", "div"),
            ("debut", "br", False, []), ("fin", "br"), ("debut", "span", False, []), ("texte", "b", True), ("fin", "span")])

    def test_fermetures_implicites_et_fin_de_document(self):
        ev = diffuser("<ul><li>un<li>deux</ul><p>sans fin")
        self.assertEqual([e for e in ev if e[0] == "fin"], [("fin", "li"), ("fin", "li"), ("fin", "ul"), ("fin", "p")])

    def test_texte_de_script_non_visible(self):
        self.assertIn(("texte", "var a = 1;", False), diffuser("<script>var a = 1;</script><p>t</p>"))

    def test_module_en_erreur_isole(self):
        class Casse(ho.Observateur):
            def debut(self, noeud, pile):
                raise ValueError("boum")
        mods = [("casse", types.SimpleNamespace(Observateur=Casse)), ("journal", types.SimpleNamespace(Observateur=Journal))]
        res = ho.analyser("<p>x</p>", {}, "https://ex.fr/", modules=mods)
        self.assertEqual(res["casse"], {"erreur": "ValueError: boum"})
        self.assertEqual(res["journal"], {"n": 3})

    def test_groupes_tries_et_exemples(self):
        pages = {"https://ex.fr/b": {"obs": {"m": {"x": [{"signature": "S2", "n": 2}, {"signature": "S1", "n": 1}]}}},
                 "https://ex.fr/a": {"obs": {"m": {"x": [{"signature": "S2", "n": 3}]}}},
                 "https://ex.fr/c": {}}
        vus = []
        ho.ajouter_groupes(lambda *a, **k: vus.append((a, k)), "cle_x", "Libellé", "basse",
                           ho.collecter_groupes(pages, "m", "x"), "Accessibilité")
        self.assertEqual(vus, [
            (("cle_x", "Libellé", "basse", {"signature": "S1", "occurrences": 1, "pages": 1, "exemples_pages": ["https://ex.fr/b"]}),
             {"n": 1, "domaine": "Accessibilité"}),
            (("cle_x", "Libellé", "basse", {"signature": "S2", "occurrences": 5, "pages": 2,
                                            "exemples_pages": ["https://ex.fr/a", "https://ex.fr/b"]}),
             {"n": 5, "domaine": "Accessibilité"})])

    def test_exemple_conserve(self):
        pages = {"https://ex.fr/a": {"obs": {"m": {"x": [{"signature": "h2 → h4", "n": 1, "exemple": "« Sauté »"}]}}},
                 "https://ex.fr/b": {"obs": {"m": {"x": [{"signature": "h2 → h4", "n": 1, "exemple": "« Autre »"}]}}}}
        vus = []
        ho.ajouter_groupes(lambda *a, **k: vus.append(a[3]), "c", "L", "basse", ho.collecter_groupes(pages, "m", "x"), "Accessibilité")
        self.assertEqual(vus, [{"signature": "h2 → h4", "occurrences": 2, "pages": 2,
                                "exemples_pages": ["https://ex.fr/a", "https://ex.fr/b"], "exemple": "« Sauté »"}])


class TestExtraction(unittest.TestCase):
    def test_add_nu_et_ajouter_groupes_seulement(self):  # pré-vol : seen_maps.add(sm) faisait lever ValueError
        src = ("vus = set()\nvus.add(x)\n\n\ndef issues(pages, add, ctx):\n    add('cle_a', 'L', 'basse')\n"
               "    ho.ajouter_groupes(add, 'cle_b', 'L', 'basse', {}, 'A')\n    ajouter_groupes(add, 'cle_c', 'L', 'basse', {}, 'A')\n")
        self.assertEqual(extraction.cles_crawl(src), {"cle_a", "cle_b", "cle_c"})


class TestCrawlAvecModules(unittest.TestCase):
    def test_chaque_page_porte_les_resultats_des_modules(self):
        page = ("<html lang='fr'><head><title>Titre de test suffisamment long</title></head>"
                "<body><main><p>Bonjour</p></main></body></html>")
        with SiteLocal({"/": (200, HTML, page)}) as site, tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, str(SCRIPTS / "crawl_site.py"), site.url, "--out", d, "--delay", "0",
                                "--max-pages", "5", "--timeout", "5", "--liens-externes", "0", "--ressources", "0"],
                               capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            donnees = json.loads(pathlib.Path(d, "pages.json").read_text(encoding="utf-8"))
        accueil = donnees["pages"][0]
        self.assertEqual(sorted(accueil["obs"]), sorted(ho.MODULES))
        self.assertEqual(donnees["meta"]["modules"].get("erreurs_modules", {}), {})
        self.assertNotIn("partiel", donnees["meta"], "pages.json final réécrit après les contrôles réseau")


if __name__ == "__main__":
    unittest.main()
