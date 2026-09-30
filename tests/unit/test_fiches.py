import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
FICHES_REELLES = RACINE / "plugins/audit-site-astro/skills/audit-complet/references/fiches"
FIXTURE_FICHES = RACINE / "tests/unit/fixtures/fiches"
FIXTURE_AUDIT = RACINE / "tests/unit/fixtures/audit-exemple"
sys.path.insert(0, str(SCRIPTS))
import fiches  # noqa: E402
import signaux  # noqa: E402


def sig(source, cle):
    return {"severite": "haute", "domaine": "x", "texte": cle, "exemples": [], "source": source, "cle": cle}


class TestParseur(unittest.TestCase):
    def test_scalaires_listes_et_commentaires(self):
        meta, corps = fiches.parse_frontmatter(
            '---\nid: a-b\ntitre: "Un \\"titre\\" : ok"   # note\neffort: S # note\nvide: []\n'
            'liste:   # note\n  # commentaire\n  - "x:1"\n  - http://ex.fr/#ancre\n  - \'y\'\n---\n\n# Corps\n')
        self.assertEqual(meta["id"], "a-b")
        self.assertEqual(meta["titre"], 'Un "titre" : ok')
        self.assertEqual(meta["effort"], "S")
        self.assertEqual(meta["vide"], [])
        self.assertEqual(meta["liste"], ["x:1", "http://ex.fr/#ancre", "y"])
        self.assertEqual(corps, "# Corps\n")

    def test_antislash_echappe(self):
        meta, _ = fiches.parse_frontmatter('---\ndeclencheurs:\n  - "http:a\\\\.b \\\\| c"\n---\n')
        self.assertEqual(meta["declencheurs"], ["http:a\\.b \\| c"])
        re.compile(fiches.declencheur(meta["declencheurs"][0])[1])

    def test_liste_en_ligne_et_apostrophes(self):
        meta, _ = fiches.parse_frontmatter("---\na: [x, \"y z\", 'l''a']\nb: 'it''s'\n---\n")
        self.assertEqual(meta["a"], ["x", "y z", "l'a"])
        self.assertEqual(meta["b"], "it's")

    def test_liste_vide_sans_element(self):
        meta, _ = fiches.parse_frontmatter("---\ndeclencheurs:\nid: x\n---\n")
        self.assertEqual(meta["declencheurs"], [])
        self.assertEqual(meta["id"], "x")

    def test_erreurs(self):
        for mauvais in ("pas de frontmatter", "---\nid: x\n", '---\nt: "non fermé\n---\n', '---\nt: "a\\.b"\n---\n',
                        "---\nid: x\nid: y\n---\n", "---\n   - orphelin\n---\n", '---\nt: "a" b\n---\n'):
            with self.assertRaises(ValueError, msg=mauvais):
                fiches.parse_frontmatter(mauvais)


class TestChargement(unittest.TestCase):
    def setUp(self):
        self.f = fiches.charger_fiches(FIXTURE_FICHES)
        self.par_id = {x["id"]: x for x in self.f}

    def test_ignore_les_fichiers_a_tiret_bas(self):
        self.assertEqual(sorted(self.par_id), ["a11y-manuel", "geo-vide", "seo-exact", "serveur-regex"])
        self.assertEqual([x["id"] for x in self.f], sorted(self.par_id))

    def test_champs_corps_et_chemin(self):
        x = self.par_id["seo-exact"]
        self.assertEqual(x["titre"], 'Titre avec "guillemets" et deux-points : ok')
        self.assertEqual(x["versions_astro"], ">=5.10")
        self.assertEqual(x["declencheurs"], ["crawl:http_4xx", "crawl:http_5xx"])
        self.assertEqual(len(x["sources"]), 2)
        self.assertTrue(x["corps"].startswith("# Titre du corps"))
        self.assertNotIn("---", x["corps"].splitlines()[0])
        self.assertEqual(x["chemin"].name, "seo-exact.md")

    def test_regex_avec_antislashs(self):
        d = self.par_id["serveur-regex"]["declencheurs"]
        self.assertIn("securite:/\\.env \\| 200", d)
        self.assertIn("code:Routes SSR dynamiques sans gestion", d)

    def test_fichier_malforme_nomme_dans_l_erreur(self):
        with tempfile.TemporaryDirectory() as t:
            pathlib.Path(t, "casse.md").write_text("pas de frontmatter", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "casse.md"):
                fiches.charger_fiches(t)


class TestAssociation(unittest.TestCase):
    def setUp(self):
        self.f = fiches.charger_fiches(FIXTURE_FICHES)

    def test_crawl_egalite_exacte(self):
        r, sans = fiches.associer([sig("crawl", "http_4xx"), sig("crawl", "http_4xx_bis"), sig("crawl", "xhttp_4xx")], self.f)
        self.assertEqual([s["cle"] for s in r["seo-exact"]], ["http_4xx"])
        self.assertEqual([s["cle"] for s in sans], ["http_4xx_bis", "xhttp_4xx"])

    def test_regex_insensible_a_la_casse_sur_la_bonne_source(self):
        s_http = sig("http", "| Compression HTML | aucune (HTML décompressé : 42 Ko) | ❌ activer |")
        s_sec = sig("securite", "| /.env | 200 | ❌ |")
        s_geo = sig("geo", "robots.txt bloque PERPLEXITYBOT")
        s_code = sig("code", "Routes SSR dynamiques sans gestion du cache")
        s_lh = sig("lighthouse", "uses-text-compression Activer la compression du texte")
        s_projet = sig("projet", "| Dépendances obsolètes | ⚠️ |")
        r, sans = fiches.associer([s_http, s_sec, s_geo, s_code, s_lh, s_projet], self.f)
        self.assertEqual(sans, [])
        self.assertEqual(len(r["serveur-regex"]), 6)

    def test_source_differente_ne_correspond_pas(self):
        # même texte que le motif http:, mais signal de source « code »
        r, sans = fiches.associer([sig("code", "| Compression HTML | aucune | ❌ |")], self.f)
        self.assertEqual(r, {})
        self.assertEqual(len(sans), 1)

    def test_signal_multi_fiches(self):
        # http_4xx retient seo-exact (exact) ET serveur-regex (autre déclencheur crawl:http_4xx)
        r, sans = fiches.associer([sig("crawl", "http_4xx")], self.f)
        self.assertEqual(sorted(r), ["seo-exact", "serveur-regex"])
        self.assertEqual(sans, [])

    def test_ordre_deterministe(self):
        signaux_ = [sig("crawl", "http_5xx"), sig("crawl", "http_4xx"), sig("lighthouse", "focus-visible")]
        r1, _ = fiches.associer(signaux_, self.f)
        r2, _ = fiches.associer(signaux_, list(reversed(self.f)))
        self.assertEqual(list(r1), list(r2))
        self.assertEqual(list(r1), sorted(r1))
        self.assertEqual([s["cle"] for s in r1["seo-exact"]], ["http_5xx", "http_4xx"])

    def test_fiche_sans_declencheur_jamais_retenue(self):
        r, _ = fiches.associer([sig("geo", "vide"), sig("crawl", "geo-vide"), sig("code", "")], self.f)
        self.assertNotIn("geo-vide", r)
        self.assertEqual([x["id"] for x in fiches.fiches_sans_detection(self.f)], ["geo-vide"])

    def test_manuel_jamais_associe_automatiquement(self):
        r, sans = fiches.associer([sig("crawl", "focus-visible"), sig("code", "focus-visible"), sig("geo", "focus-visible")], self.f)
        self.assertEqual(r, {})
        self.assertEqual(len(sans), 3)
        self.assertEqual([x["id"] for x in fiches.fiches_manuelles(self.f)], ["a11y-manuel"])
        # ses autres déclencheurs (lighthouse:focus) restent actifs
        r, _ = fiches.associer([sig("lighthouse", "focus-traps")], self.f)
        self.assertEqual(list(r), ["a11y-manuel"])

    def test_signal_sans_fiche(self):
        r, sans = fiches.associer([sig("crawl", "inconnu"), sig("projet", "rien")], self.f)
        self.assertEqual(r, {})
        self.assertEqual([s["cle"] for s in sans], ["inconnu", "rien"])

    def test_declencheur_invalide(self):
        for mauvais in ("inconnu:x", "crawl:", "crawl", ":x"):
            with self.assertRaises(ValueError, msg=mauvais):
                fiches.declencheur(mauvais)


def _titres(corps):
    """Titres « ## » du corps, hors blocs de code."""
    en_code, out = False, []
    for ligne in corps.splitlines():
        if ligne.lstrip().startswith(("```", "~~~")):
            en_code = not en_code
        elif not en_code and ligne.startswith("## "):
            out.append(ligne[3:].strip())
    return out


class TestBaseReelle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = fiches.charger_fiches(FICHES_REELLES)

    def test_toutes_les_fiches_se_chargent(self):
        self.assertEqual(len(self.f), len(list(FICHES_REELLES.glob("[!_]*.md"))))
        self.assertGreaterEqual(len(self.f), 142)
        self.assertEqual(len({x["id"] for x in self.f}), len(self.f), "ids en double")

    def test_metadonnees(self):
        for x in self.f:
            with self.subTest(fiche=x["chemin"].name):
                self.assertEqual(x["id"], x["chemin"].stem, "id différent du nom de fichier")
                self.assertRegex(x["id"], r"^[a-z0-9]+(-[a-z0-9]+)+$")
                self.assertIn(x["id"].split("-")[0], fiches.PREFIXES_ID)
                self.assertTrue(x.get("titre"))
                self.assertIn(x.get("domaine"), fiches.DOMAINES)
                self.assertIn(x.get("severite_type"), fiches.SEVERITES)
                self.assertIn(x.get("effort"), fiches.EFFORTS)
                self.assertIsInstance(x["sources"], list)
                self.assertTrue(all(isinstance(s, str) and s.startswith("http") for s in x["sources"]), x["sources"])

    def test_declencheurs_valides(self):
        for x in self.f:
            with self.subTest(fiche=x["id"]):
                for d in x["declencheurs"]:
                    self.assertIsInstance(d, str)
                    prefixe, motif = fiches.declencheur(d)  # préfixe connu, motif non vide
                    if prefixe not in ("crawl", fiches.PREFIXE_MANUEL):
                        re.compile(motif, re.I)

    def test_sections_du_modele_dans_l_ordre(self):
        for x in self.f:
            with self.subTest(fiche=x["id"]):
                titres = _titres(x["corps"])
                pos = []
                for s in fiches.SECTIONS:
                    self.assertIn(s, titres, f"section manquante : ## {s}")
                    pos.append(titres.index(s))
                self.assertEqual(pos, sorted(pos), f"sections dans le désordre : {titres}")

    def test_manuelles_et_sans_detection(self):
        self.assertEqual([x["id"] for x in fiches.fiches_sans_detection(self.f)], ["geo-bing-webmaster-indexnow", "geo-mesure-visibilite-ia"])
        self.assertTrue(fiches.fiches_manuelles(self.f))
        for x in fiches.fiches_manuelles(self.f):
            self.assertTrue(any(d.startswith("manuel:") for d in x["declencheurs"]))


class TestCouverture(unittest.TestCase):
    """Chaque détecteur de l'outil doit être couvert par au moins une fiche (les trous sont listés dans le message d'échec)."""

    @classmethod
    def setUpClass(cls):
        cls.f = fiches.charger_fiches(FICHES_REELLES)

    def _trous(self, sigs):
        _, sans = fiches.associer(sigs, self.f)
        return [f"{s['source']}: {s['cle'][:160]}" for s in sans]

    def test_cles_du_crawl(self):
        src = (SCRIPTS / "crawl_site.py").read_text(encoding="utf-8")
        cles = set(re.findall(r'\badd\(\s*"([a-z0-9_]+)"', src))
        cles |= set(re.findall(r'\bissues\[\s*"([a-z0-9_]+)"\s*\]\s*=', src))
        cles |= set(re.findall(r'\bissues\.setdefault\(\s*"([a-z0-9_]+)"', src))
        self.assertGreater(len(cles), 40, f"extraction des clés du crawl suspecte : {sorted(cles)}")
        trous = self._trous([sig("crawl", k) for k in sorted(cles)])
        self.assertEqual(trous, [], f"clés d'issue du crawl sans fiche : {trous}")

    def _constats_du_scan(self, variante):
        with tempfile.TemporaryDirectory() as t:
            subprocess.run([sys.executable, str(SCRIPTS / "astro_scan.py"), str(RACINE / "tests/cobaye" / variante), "--out", t],
                           check=True, capture_output=True, timeout=180)
            rapport = json.loads(pathlib.Path(t, "code-scan.json").read_text(encoding="utf-8"))
        return [sig("code", c["constat"]) for c in rapport["constats"]]

    def test_constats_du_scan_sur_le_cobaye(self):
        sigs = self._constats_du_scan("casse") + self._constats_du_scan("propre")
        self.assertGreater(len(sigs), 20)
        trous = sorted(set(self._trous(sigs)))
        self.assertEqual(trous, [], f"constats astro_scan.py (cobaye casse/propre) sans fiche : {trous}")

    # Signaux de la fixture audit-exemple qui ne ressemblent à aucune sortie réelle de l'outil (clés d'issue de crawl inventées,
    # textes de constats/audits reformulés, ligne de sonde sécurité au format simplifié) : aucune fiche ne peut les reconnaître.
    # Ce ne sont pas des trous de détecteurs mais des artefacts de la fixture. À trancher : aligner la fixture sur les vraies
    # sorties (et son RAPPORT-BRUT.attendu.md), ou renoncer à cette assertion.
    FIXTURE_SYNTHETIQUES = [
        "code: Image d'en-tête non optimisée (<img> au lieu de <Image>)",
        "code: Balise canonical absente du layout",
        "crawl: liens_casses",
        "crawl: title_manquant",
        "crawl: h1_multiples",
        "securite: | /.git/config | ❌ EXPOSÉ (critique) |",
        "lighthouse: Les liens n'ont pas de nom discernable",
        "lighthouse: Le contraste des couleurs est insuffisant",
        "geo: llms.txt absent : les assistants IA n'ont pas de résumé du site",
        "geo: Aucune donnée structurée Organization sur la page d'accueil",
    ]

    def test_signaux_de_la_fixture(self):
        trous = [t for t in self._trous(signaux.collecter(FIXTURE_AUDIT)) if t not in self.FIXTURE_SYNTHETIQUES]
        self.assertEqual(trous, [], f"signaux de la fixture audit-exemple sans fiche : {trous}")

    @unittest.expectedFailure
    def test_signaux_synthetiques_de_la_fixture_couverts(self):
        """ÉCHEC ATTENDU : les signaux de FIXTURE_SYNTHETIQUES n'ont pas de fiche (voir le commentaire ci-dessus). Si ce test
        réussit, la fixture a été alignée : retirer @expectedFailure, FIXTURE_SYNTHETIQUES et le filtre du test précédent."""
        trous = self._trous(signaux.collecter(FIXTURE_AUDIT))
        self.assertEqual(trous, [], f"signaux de la fixture audit-exemple sans fiche : {trous}")


if __name__ == "__main__":
    unittest.main()
