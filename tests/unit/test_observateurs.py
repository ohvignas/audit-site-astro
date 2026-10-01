import json
import pathlib
import shutil
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
import crawl_site  # noqa: E402
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


PAGE_SIMPLE = ("<html lang='fr'><head><title>Titre de test suffisamment long</title></head>"
               "<body><main><p>Bonjour</p></main></body></html>")


def crawler_avec_module_modifie(testcase, nom_module, corps, page=PAGE_SIMPLE, attendre_succes=True):
    """Copie les scripts dans un dossier temporaire, remplace le module `nom_module` par `corps`, lance un vrai crawl.
    Retourne (processus, dossier de sortie) ; le dossier temporaire est supprimé en fin de test."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    testcase.addCleanup(shutil.rmtree, str(tmp), True)
    scripts = tmp / "scripts"
    scripts.mkdir()
    for f in SCRIPTS.glob("*.py"):
        shutil.copy(str(f), str(scripts / f.name))
    (scripts / (nom_module + ".py")).write_text(corps, encoding="utf-8")
    sortie = tmp / "out"
    with SiteLocal({"/": (200, HTML, page)}) as site:
        r = subprocess.run([sys.executable, str(scripts / "crawl_site.py"), site.url, "--out", str(sortie), "--delay", "0",
                            "--max-pages", "5", "--timeout", "5", "--liens-externes", "0", "--ressources", "0"],
                           capture_output=True, text=True, timeout=120)
    if attendre_succes:
        testcase.assertEqual(r.returncode, 0, r.stderr[-2000:])
    return r, sortie


ENTETE_MODULE = 'import html_observateurs as ho\n\nNOM = "x"\n\n\n'


class TestIsolationDesModules(unittest.TestCase):
    """I1 : un module qui ne s'importe pas ou ne s'instancie pas est ignoré, jamais fatal."""

    def test_init_qui_leve_isole_unitaire(self):
        class InitCasse(ho.Observateur):
            def __init__(self, entetes, url):
                super().__init__(entetes, url)
                raise KeyError("content-type")
        mods = [("casse", types.SimpleNamespace(Observateur=InitCasse)), ("journal", types.SimpleNamespace(Observateur=Journal))]
        res = ho.analyser("<p>x</p>", {}, "https://ex.fr/", modules=mods)
        self.assertEqual(res["casse"], {"erreur": "KeyError: 'content-type'"})
        self.assertEqual(res["journal"], {"n": 3})

    def test_import_en_echec_isole_unitaire(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "t3_mod_syntaxe.py").write_text("def (:\n", encoding="utf-8")
            pathlib.Path(d, "t3_mod_ok.py").write_text(
                "import html_observateurs as ho\n\n\nclass Observateur(ho.Observateur):\n"
                "    def debut(self, noeud, pile):\n        pass\n\n    def resultat(self):\n        return {'ok': 1}\n",
                encoding="utf-8")
            sys.path.insert(0, d)
            anciens = (ho.MODULES, list(ho._CHARGES), dict(ho._ERREURS_IMPORT))

            def restaurer():
                sys.path.remove(d)
                ho.MODULES = anciens[0]
                ho._CHARGES[:] = anciens[1]
                ho._ERREURS_IMPORT.clear()
                ho._ERREURS_IMPORT.update(anciens[2])
                for nom in ("t3_mod_syntaxe", "t3_mod_ok", "t3_mod_absent"):
                    sys.modules.pop(nom, None)
            self.addCleanup(restaurer)
            ho.MODULES = ("t3_mod_syntaxe", "t3_mod_absent", "t3_mod_ok")
            ho._CHARGES[:] = []
            ho._ERREURS_IMPORT.clear()
            res = ho.analyser("<p>x</p>", {}, "https://ex.fr/")
            self.assertTrue(res["t3_mod_syntaxe"]["erreur"].startswith("SyntaxError"), res)
            self.assertTrue(res["t3_mod_absent"]["erreur"].startswith("ModuleNotFoundError"), res)
            self.assertEqual(res["t3_mod_ok"], {"ok": 1})
            ctx = {}
            ho.apres_crawl({}, ctx)
            erreurs = ctx["meta"]["erreurs_modules"]
            self.assertTrue(erreurs["t3_mod_syntaxe"].startswith("SyntaxError"), erreurs)
            self.assertTrue(erreurs["t3_mod_absent"].startswith("ModuleNotFoundError"), erreurs)
            self.assertNotIn("t3_mod_ok", erreurs)

    def test_crawl_avec_init_qui_leve(self):
        r, sortie = crawler_avec_module_modifie(
            self, "a11y_svg", ENTETE_MODULE + "class Observateur(ho.Observateur):\n    def __init__(self, entetes, url):\n"
            "        super().__init__(entetes, url)\n        entetes['content-type-absent']\n")
        donnees = json.loads((sortie / "pages.json").read_text(encoding="utf-8"))
        accueil = donnees["pages"][0]
        self.assertEqual(accueil["obs"]["a11y_svg"], {"erreur": "KeyError: 'content-type-absent'"})
        self.assertEqual(sorted(accueil["obs"]), sorted(ho.MODULES))
        self.assertEqual(accueil["title"], "Titre de test suffisamment long", "les données de PageParser sont conservées")
        self.assertTrue(donnees["meta"]["modules"]["erreurs_modules"]["a11y_svg"].startswith("KeyError"))
        self.assertNotIn("a11y_noms", donnees["meta"]["modules"]["erreurs_modules"])
        self.assertTrue((sortie / "issues.json").is_file())

    def test_crawl_avec_module_non_importable(self):
        r, sortie = crawler_avec_module_modifie(self, "a11y_noms", "def (:\n")  # SyntaxError : cas du 3.10+ sous Python 3.9
        donnees = json.loads((sortie / "pages.json").read_text(encoding="utf-8"))
        self.assertTrue(donnees["pages"][0]["obs"]["a11y_noms"]["erreur"].startswith("SyntaxError"))
        self.assertTrue(donnees["meta"]["modules"]["erreurs_modules"]["a11y_noms"].startswith("SyntaxError"))
        self.assertEqual(donnees["pages"][0]["title"], "Titre de test suffisamment long")


class TestSortiesJson(unittest.TestCase):
    """I2 : résultat non sérialisable remplacé par une erreur ; pages.json et issues.json écrits atomiquement."""

    def _res(self, valeur):
        class R(ho.Observateur):
            def resultat(self):
                return valeur
        return ho.analyser("<p>x</p>", {}, "https://ex.fr/", modules=[("r", types.SimpleNamespace(Observateur=R))])["r"]

    def test_resultat_non_serialisable_remplace_par_une_erreur(self):
        self.assertTrue(self._res({"ids": {1, 2}})["erreur"].startswith("TypeError"))
        self.assertTrue(self._res({"x": float("nan")})["erreur"].startswith("ValueError"), "NaN n'est pas du JSON valide")
        self.assertTrue(self._res({("a", "b"): 1})["erreur"].startswith("TypeError"))
        self.assertEqual(self._res({"signature": [{"signature": "S", "n": 1}]}), {"signature": [{"signature": "S", "n": 1}]})

    def test_erreurs_des_pages_remontees_dans_meta(self):
        class R(ho.Observateur):
            def resultat(self):
                return {1, 2}
        pages = {"https://ex.fr/": {"obs": ho.analyser("<p>x</p>", {}, "https://ex.fr/",
                                                        modules=[("r", types.SimpleNamespace(Observateur=R))])}}
        ctx = {}
        ho.apres_crawl(pages, ctx)
        self.assertTrue(ctx["meta"]["erreurs_modules"]["r"].startswith("TypeError"), ctx)

    def test_crawl_avec_resultat_set_garde_un_pages_json_valide(self):
        r, sortie = crawler_avec_module_modifie(
            self, "a11y_svg", ENTETE_MODULE + "class Observateur(ho.Observateur):\n    def resultat(self):\n"
            "        return {'ids': {1, 2}}\n")
        donnees = json.loads((sortie / "pages.json").read_text(encoding="utf-8"))
        self.assertTrue(donnees["pages"][0]["obs"]["a11y_svg"]["erreur"].startswith("TypeError"))
        self.assertTrue(donnees["meta"]["modules"]["erreurs_modules"]["a11y_svg"].startswith("TypeError"))
        json.loads((sortie / "issues.json").read_text(encoding="utf-8"))
        self.assertEqual(list(sortie.glob("*.tmp")), [])

    def test_ecriture_atomique_laisse_l_ancien_fichier_intact(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = pathlib.Path(d, "pages.json")
            crawl_site.ecrire_json(chemin, {"a": 1})
            with self.assertRaises(TypeError):
                crawl_site.ecrire_json(chemin, {"a": {1, 2}})
            self.assertEqual(json.loads(chemin.read_text(encoding="utf-8")), {"a": 1})
            self.assertEqual(sorted(p.name for p in pathlib.Path(d).iterdir()), ["pages.json"], "aucun fichier temporaire")

    def test_coupure_pendant_apres_crawl_laisse_pages_et_issues_valides(self):
        r, sortie = crawler_avec_module_modifie(
            self, "liens_externes", ENTETE_MODULE + "import os\nimport signal\n\n\nclass Observateur(ho.Observateur):\n    pass\n\n\n"
            "def apres_crawl(pages, ctx):\n    os.kill(os.getpid(), signal.SIGKILL)  # coupure brutale de l'étape\n",
            attendre_succes=False)
        self.assertNotEqual(r.returncode, 0)
        donnees = json.loads((sortie / "pages.json").read_text(encoding="utf-8"))
        self.assertTrue(donnees["meta"]["partiel"])
        issues = json.loads((sortie / "issues.json").read_text(encoding="utf-8"))  # issues.json provisoire, valide
        self.assertIsInstance(issues, dict)
        self.assertEqual(list(sortie.glob("*.tmp")), [])


class TestTableDEnvoi(unittest.TestCase):
    """M1 : un observateur ne reçoit que les événements qu'il surcharge dans sa classe."""

    def test_methode_non_surchargee_jamais_appelee(self):
        recus = []

        class SansTexte(ho.Observateur):
            def debut(self, noeud, pile):
                recus.append(("debut", noeud["tag"]))

            def texte(self, donnees, pile):  # surchargé : reçoit
                recus.append(("texte", donnees))
        ho.Diffuseur([SansTexte(None, "u")]).analyser("<p>a</p>")
        self.assertEqual(recus, [("debut", "p"), ("texte", "a")])

        class SansRien(ho.Observateur):
            pass
        o = SansRien(None, "u")
        o.texte = lambda donnees, pile: recus.append("INTERDIT")  # affectation sur l'instance : ignorée
        o.debut = lambda noeud, pile: recus.append("INTERDIT")
        ho.Diffuseur([o]).analyser("<p>a</p>")
        self.assertNotIn("INTERDIT", recus)

    def test_surcharge_heritee_vue(self):
        recus = []

        class Parent(ho.Observateur):
            def texte(self, donnees, pile):
                recus.append(donnees)

        class Enfant(Parent):
            pass
        ho.Diffuseur([Enfant(None, "u")]).analyser("a")
        self.assertEqual(recus, ["a"])

    def test_observateur_en_erreur_retire_de_tous_les_evenements(self):
        recus = []

        class Fautif(ho.Observateur):
            def texte(self, donnees, pile):
                raise ValueError("boum")

            def fin(self, noeud, pile):
                recus.append(("fin", noeud["tag"]))

        class Temoin(ho.Observateur):
            def fin(self, noeud, pile):
                recus.append(("temoin", noeud["tag"]))
        f, t = Fautif(None, "u"), Temoin(None, "u")
        d = ho.Diffuseur([f, t])
        d.analyser("<p>a</p>")
        self.assertEqual(recus, [("temoin", "p")], "le fautif ne reçoit plus de fin après son erreur")
        self.assertEqual(d.erreurs[id(f)], "ValueError: boum")


class TestLectureDuHtml(unittest.TestCase):
    def test_premier_attribut_double_l_emporte_comme_un_navigateur(self):
        class Alt(ho.Observateur):
            def __init__(self, entetes, url):
                super().__init__(entetes, url)
                self.alts = []

            def debut(self, noeud, pile):
                self.alts.append(noeud["a"].get("alt"))
        o = Alt(None, "u")
        ho.Diffuseur([o]).analyser('<img alt="" alt="Logo">')
        self.assertEqual(o.alts, [""])

    def test_erreur_de_lecture_remontee(self):
        class Compte(ho.Observateur):
            def resultat(self):
                return {"ok": 1}
        erreurs = []
        res = ho.analyser("<p>a</p><![foo]><p>b</p>", {}, "https://ex.fr/",
                          modules=[("c", types.SimpleNamespace(Observateur=Compte))], erreurs=erreurs)
        self.assertEqual(res, {"c": {"ok": 1}})
        self.assertEqual(len(erreurs), 1)
        self.assertTrue(erreurs[0].startswith("parse: "), erreurs)


class TestExtraction(unittest.TestCase):
    def test_add_nu_et_ajouter_groupes_seulement(self):  # pré-vol : seen_maps.add(sm) faisait lever ValueError
        src = ("vus = set()\nvus.add(x)\n\n\ndef issues(pages, add, ctx):\n    add('cle_a', 'L', 'basse')\n"
               "    ho.ajouter_groupes(add, 'cle_b', 'L', 'basse', {}, 'A')\n    ajouter_groupes(add, 'cle_c', 'L', 'basse', {}, 'A')\n")
        self.assertEqual(extraction.cles_crawl(src), {"cle_a", "cle_b", "cle_c"})

    def test_cle_passee_par_mot_cle_ou_absente_refusee(self):  # M4 : jamais ignorée en silence
        self.assertEqual(extraction.cles_crawl("add(key='cle_a', label='L')\nho.ajouter_groupes(add, cle='cle_b')\n"), {"cle_a", "cle_b"})
        with self.assertRaises(ValueError):
            extraction.cles_crawl("add(label='L')\n")
        with self.assertRaises(ValueError):
            extraction.cles_crawl("ajouter_groupes(add)\n")


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
