"""Garde-fous statiques du banc v2.1 (sans build Astro) : les pages du jumeau propre ne doivent déclencher aucun contrôle
existant (title/description, contenu faible, titres quasi identiques, assets non hashés) et la vérité terrain reste cohérente."""
import itertools
import json
import pathlib
import re
import sys
import unittest

ICI = pathlib.Path(__file__).resolve().parent
RACINE = ICI.parents[1]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ICI))
import crawl_site  # noqa: E402
import extraction_detecteurs as extraction  # noqa: E402
import html_observateurs  # noqa: E402

PAGES_PROPRE = RACINE / "tests/cobaye/propre/src/pages"
BASE = re.compile(r'<Base\s+title="([^"]+)"\s+description="([^"]+)"')


class TestPagesPropresV21(unittest.TestCase):
    def setUp(self):
        self.pages = sorted((PAGES_PROPRE / "v21").glob("*.astro"))

    def test_existe(self):
        self.assertIn("index.astro", [p.name for p in self.pages])

    def test_title_description_h1_et_texte_long(self):
        titres, descs = {}, {}
        for f in self.pages:
            t = f.read_text(encoding="utf-8")
            m = BASE.search(t)
            self.assertIsNotNone(m, f'{f.name} : <Base title="…" description="…"> attendu, en littéraux')
            titre, desc = m.groups()
            self.assertTrue(25 <= len(titre) <= 65, f"{f.name} : title de {len(titre)} caractères (25 à 65)")
            self.assertTrue(70 <= len(desc) <= 160, f"{f.name} : description de {len(desc)} caractères (70 à 160)")
            self.assertNotIn(titre.lower(), titres, f"{f.name} : title déjà utilisé par {titres.get(titre.lower())}")
            self.assertNotIn(desc.lower(), descs, f"{f.name} : description déjà utilisée")
            titres[titre.lower()], descs[desc.lower()] = f.name, f.name
            self.assertIn("<TexteLong ", t, f"{f.name} : <TexteLong …/> attendu (sinon thin_content < 300 mots)")
            self.assertEqual(len(re.findall(r"<h1\b", t)), 1, f"{f.name} : un seul <h1>")
            self.assertNotRegex(t, r'(src|href)="/(?!v21|catalogue|formations|blog|contact|a-propos|_astro)',
                                f"{f.name} : pas de fichier de public/ (asset non hashé) ni de lien hors site")
            self.assertNotRegex(t, r"\sstyle=|is:inline", f"{f.name} : aucun style en ligne (la CSP <meta> d'Astro le bloquerait)")

    def test_pas_de_titres_quasi_identiques_sur_le_propre(self):
        # même règle que near_dup_titles (crawl_site.tokenize, mots de marque retirés, Jaccard ≥ 0,7)
        jetons = {}
        for f in PAGES_PROPRE.rglob("*.astro"):
            t = f.read_text(encoding="utf-8")
            m, h1 = BASE.search(t), re.search(r"<h1>([^<{]+)</h1>", t)
            if m:
                jetons[f.name if f.parent.name != "v21" else "v21/" + f.name] = crawl_site.tokenize(
                    m.group(1) + " " + (h1.group(1) if h1 else ""))
        freq = {}
        for s in jetons.values():
            for j in s:
                freq[j] = freq.get(j, 0) + 1
        marque = {j for j, c in freq.items() if c > 0.5 * len(jetons)}
        for (a, sa), (b, sb) in itertools.combinations(sorted(jetons.items()), 2):
            x, y = sa - marque, sb - marque
            if len(x) >= 2 and len(y) >= 2 and x & y:
                self.assertLess(len(x & y) / len(x | y), 0.7, f"titres quasi identiques : {a} / {b}")


class TestVeriteTerrainV21(unittest.TestCase):
    def test_identifiants_uniques_et_cles_produites(self):
        verite = json.loads((RACINE / "tests/cobaye/verite-terrain.json").read_text(encoding="utf-8"))
        ids = [d["id"] for d in verite["defauts"]]
        self.assertEqual(len(ids), len(set(ids)), "identifiants en double dans verite-terrain.json")
        cles = set()
        for nom in ("crawl_site",) + tuple(html_observateurs.MODULES):
            cles |= extraction.cles_crawl((SCRIPTS / (nom + ".py")).read_text(encoding="utf-8"))
        for d in verite["defauts"]:
            m = d["matcher"]
            if d["phase"] == 2 and m["type"] == "crawl_issue" and m.get("fichier", "crawl/issues.json") == "crawl/issues.json":
                self.assertIn(m["cle"], cles, f"{d['id']} : clé {m['cle']} produite par aucun détecteur du crawl")


if __name__ == "__main__":
    unittest.main()
