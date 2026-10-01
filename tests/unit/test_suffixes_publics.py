import pathlib
import sys
import tempfile
import unittest
from unittest import mock

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
import suffixes_publics as psl  # noqa: E402

# Aucun accès réseau : le module lit un fichier local.
_GARDE = [mock.patch("urllib.request.urlopen", side_effect=AssertionError("réseau interdit")),
          mock.patch("socket.socket.connect", side_effect=AssertionError("réseau interdit"))]


def setUpModule():
    for g in _GARDE:
        g.start()


def tearDownModule():
    for g in _GARDE:
        g.stop()


MINI = """// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0.
// ===BEGIN ICANN DOMAINS===
com
jp
ac.jp
*.kawasaki.jp
!city.kawasaki.jp
// ===END ICANN DOMAINS===
// ===BEGIN PRIVATE DOMAINS===
uk.com
vercel.app
// ===END PRIVATE DOMAINS===
""" + "\n".join("tld{0}".format(i) for i in range(120)) + "\n"


class TestAlgorithme(unittest.TestCase):
    """Vecteurs inspirés de la suite de tests officielle de la PSL, sur une mini-liste figée (indépendante de l'instantané)."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d, "mini.dat")
            p.write_text(MINI, encoding="utf-8")
            cls.r = psl.charger(p)

    def dom(self, h):
        return psl.domaine_enregistrable(h, regles=self.r)

    def test_regles_normales(self):
        self.assertEqual(self.dom("example.com"), "example.com")
        self.assertEqual(self.dom("www.example.com"), "example.com")
        self.assertEqual(self.dom("a.b.example.com"), "example.com")
        self.assertIsNone(self.dom("com"))
        self.assertEqual(self.dom("www.test.ac.jp"), "test.ac.jp")
        self.assertIsNone(self.dom("ac.jp"))

    def test_regle_la_plus_longue(self):
        self.assertEqual(self.dom("b.example.uk.com"), "example.uk.com")
        self.assertEqual(self.dom("a.b.example.uk.com"), "example.uk.com")
        self.assertIsNone(self.dom("uk.com"))

    def test_joker_et_exception(self):
        self.assertIsNone(self.dom("b.kawasaki.jp"))                 # *.kawasaki.jp : b.kawasaki.jp est un suffixe public
        self.assertEqual(self.dom("a.b.kawasaki.jp"), "a.b.kawasaki.jp")
        self.assertEqual(self.dom("city.kawasaki.jp"), "city.kawasaki.jp")   # !city.kawasaki.jp : exception
        self.assertEqual(self.dom("www.city.kawasaki.jp"), "city.kawasaki.jp")
        self.assertEqual(self.dom("kawasaki.jp"), "kawasaki.jp")     # jp seul s'applique
        self.assertEqual(psl.suffixe_public("www.city.kawasaki.jp", regles=self.r), "kawasaki.jp")

    def test_suffixe_inconnu_regle_etoile(self):
        self.assertEqual(self.dom("example.inconnu"), "example.inconnu")
        self.assertEqual(self.dom("a.example.inconnu"), "example.inconnu")
        self.assertIsNone(self.dom("inconnu"))
        self.assertEqual(psl.suffixe_public("a.example.inconnu", regles=self.r), "inconnu")

    def test_section_privee(self):
        self.assertTrue(psl.suffixe_prive("site.vercel.app", regles=self.r))
        self.assertTrue(psl.suffixe_prive("vercel.app", regles=self.r))
        self.assertTrue(psl.suffixe_prive("x.example.uk.com", regles=self.r))
        self.assertFalse(psl.suffixe_prive("example.com", regles=self.r))
        self.assertFalse(psl.suffixe_prive("www.test.ac.jp", regles=self.r))
        self.assertFalse(psl.suffixe_prive("example.inconnu", regles=self.r))

    def test_normalisation(self):
        self.assertEqual(self.dom("WWW.Example.COM."), "example.com")
        self.assertEqual(self.dom("Bücher.COM"), "xn--bcher-kva.com")
        self.assertEqual(self.dom("xn--bcher-kva.com"), "xn--bcher-kva.com")

    def test_entrees_invalides(self):
        for h in (None, "", ".", ".com", "a..com", "   ", 42):
            with self.subTest(h=h):
                self.assertIsNone(self.dom(h))
                self.assertFalse(psl.suffixe_prive(h, regles=self.r))

    def test_nom_tres_long_sans_erreur(self):
        self.assertEqual(self.dom(".".join(["a"] * 120) + ".example.com"), "example.com")


class TestInstantane(unittest.TestCase):
    """Instantané vendu : en-tête MPL-2.0 conservé, deux sections, règles usuelles (valeurs stables dans le temps)."""

    def test_fichier_present_non_modifie(self):
        texte = psl.DAT.read_text(encoding="utf-8")
        self.assertIn("Mozilla Public", texte[:400])
        self.assertIn("mozilla.org/MPL/2.0", texte[:400])
        self.assertRegex(texte, r"// VERSION: \d{4}-\d\d-\d\d_")
        self.assertIn("===BEGIN ICANN DOMAINS===", texte)
        self.assertIn("===BEGIN PRIVATE DOMAINS===", texte)
        self.assertGreater(len(psl.charger().normal), 5000)
        self.assertEqual(psl.charger().source, str(psl.DAT))

    def test_docstring_trace_la_source_et_la_date(self):
        doc = psl.__doc__
        self.assertIn("https://publicsuffix.org/list/public_suffix_list.dat", doc)
        self.assertRegex(doc, r"Récupéré\s*: \d{4}-\d\d-\d\d")
        self.assertIn("VERSION    : " + __import__("re").search(r"// VERSION: (\S+)", psl.DAT.read_text(encoding="utf-8")).group(1), doc)

    def test_registrables_usuels(self):
        for hote, attendu in (("www.example.fr", "example.fr"), ("beta.example.fr", "example.fr"), ("www.example.co.uk", "example.co.uk"),
                              ("a.b.example.com.au", "example.com.au"), ("www.example.com", "example.com"),
                              ("x.inconnu.co.uk", "inconnu.co.uk")):
            with self.subTest(hote=hote):
                self.assertEqual(psl.domaine_enregistrable(hote), attendu)
        for suffixe in ("co.uk", "com.au", "fr", "com"):
            self.assertIsNone(psl.domaine_enregistrable(suffixe), suffixe)

    def test_plateformes_privees(self):
        for hote in ("site.vercel.app", "foo.netlify.app", "someone.github.io", "proj.pages.dev", "app.herokuapp.com", "a.b.github.io",
                     "x.web.app", "y.workers.dev"):
            with self.subTest(hote=hote):
                self.assertTrue(psl.suffixe_prive(hote), hote)
        for hote in ("www.example.fr", "example.co.uk", "example.com", "www.example.org", "example.dev"):
            with self.subTest(hote=hote):
                self.assertFalse(psl.suffixe_prive(hote), hote)

    def test_domaine_enregistrable_sous_plateforme(self):
        self.assertEqual(psl.domaine_enregistrable("a.b.someone.github.io"), "someone.github.io")
        self.assertEqual(psl.suffixe_public("a.someone.github.io"), "github.io")


class TestRepli(unittest.TestCase):
    def test_fichier_absent_ne_leve_pas_et_utilise_le_repli(self):
        r = psl.charger("/chemin/inexistant/public_suffix_list.dat")
        self.assertEqual(r.source, "repli")
        self.assertEqual(psl.domaine_enregistrable("www.example.co.uk", regles=r), "example.co.uk")
        self.assertEqual(psl.domaine_enregistrable("www.example.fr", regles=r), "example.fr")
        for hote in ("site.vercel.app", "foo.netlify.app", "x.github.io", "a.pages.dev", "app.herokuapp.com"):
            self.assertTrue(psl.suffixe_prive(hote, regles=r), hote)
        self.assertFalse(psl.suffixe_prive("www.example.fr", regles=r))

    def test_fichier_illisible_ou_vide(self):
        with tempfile.TemporaryDirectory() as d:
            vide = pathlib.Path(d, "vide.dat")
            vide.write_text("", encoding="utf-8")
            binaire = pathlib.Path(d, "bin.dat")
            binaire.write_bytes(b"\xff\xfe\x00\x80" * 50)
            for p in (vide, binaire):
                with self.subTest(p=p.name):
                    self.assertEqual(psl.charger(p).source, "repli")

    def test_repli_utilise_quand_le_dat_par_defaut_manque(self):
        with mock.patch.object(psl, "DAT", pathlib.Path("/chemin/inexistant/x.dat")):
            psl._charger.cache_clear()
            try:
                self.assertEqual(psl.domaine_enregistrable("www.example.co.uk"), "example.co.uk")
                self.assertTrue(psl.suffixe_prive("x.github.io"))
            finally:
                psl._charger.cache_clear()


if __name__ == "__main__":
    unittest.main()
