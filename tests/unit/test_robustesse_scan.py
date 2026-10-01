"""Gardes du scan de code restants après v2.0.1 : le scan finit et note ce qu'il ignore au lieu de planter."""
import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
import astro_scan  # noqa: E402

BASE = {"package.json": json.dumps({"dependencies": {"astro": "^7.3.0"}}), ".gitignore": ".env\n",
        "astro.config.mjs": "export default { site: 'https://ex.fr' };\n", "src/pages/index.astro": "<h1>Ok</h1>\n"}
ENV = dict(os.environ, ASTRO_SCAN_HORS_LIGNE="1")


def projet(d, fichiers):
    for chemin, contenu in dict(BASE, **fichiers).items():
        f = pathlib.Path(d, "projet", chemin)
        f.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contenu, bytes):
            f.write_bytes(contenu)
        else:
            f.write_text(contenu, encoding="utf-8")
    return pathlib.Path(d, "projet")


def scanner(fichiers, prep=None, env=None):
    with tempfile.TemporaryDirectory() as d:
        racine = projet(d, fichiers)
        if prep:
            prep(racine)
        t0 = time.monotonic()
        r = subprocess.run([sys.executable, str(SCRIPTS / "astro_scan.py"), str(racine), "--out", str(pathlib.Path(d, "out"))],
                           capture_output=True, text=True, timeout=120, env=dict(ENV, **(env or {})))
        duree = time.monotonic() - t0
        rapport = json.loads(pathlib.Path(d, "out/code-scan.json").read_text(encoding="utf-8")) if r.returncode == 0 else {}
        md = pathlib.Path(d, "out/code-scan.md").read_text(encoding="utf-8") if r.returncode == 0 else ""
    return r, rapport, md, duree


def raisons(rapport):
    return [(i["fichier"], i["raison"]) for i in rapport.get("fichiers_ignores", [])]


class TestEntreesPathologiques(unittest.TestCase):
    def test_fichier_geant(self):
        r, rap, _, duree = scanner({"src/data/geant.ts": 'export const d = "' + "a" * 6_000_000 + '";\n'})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertEqual(raisons(rap), [("src/data/geant.ts", "fichier ignoré (trop gros : 6.0 Mo > 1.5 Mo)")])
        self.assertLess(duree, 60)

    def test_binaire_ignore_une_seule_fois(self):  # lu par scan_src ET scan_astro_features : une seule entrée
        r, rap, md, _ = scanner({"src/components/Binaire.astro": b"\x00\x01\x02" * 4000})
        self.assertEqual(raisons(rap), [("src/components/Binaire.astro", "fichier ignoré (binaire)")])
        self.assertIn("## Fichiers ignorés et étapes en erreur", md)
        self.assertEqual(md.count("- `src/components/Binaire.astro` : fichier ignoré (binaire)"), 1)

    def test_package_json_invalide(self):
        r, rap, _, _ = scanner({"package.json": '{"dependencies": {"astro": "^7.3.0",}'})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertTrue(raisons(rap)[0][1].startswith("fichier ignoré (JSON invalide"), raisons(rap))

    def test_fichier_minifie_analyse(self):  # décision : jamais ignoré (v2.0.1 rend les lignes longues sûres)
        r, rap, _, _ = scanner({"src/lib/vendor.min.js": ("var a=" + "1," * 150_000 + "0;\n") * 3})
        self.assertEqual(raisons(rap), [])

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root lit tout")
    def test_fichier_illisible(self):
        r, rap, _, _ = scanner({}, prep=lambda racine: os.chmod(racine / "src/pages/index.astro", 0))
        self.assertTrue(dict(raisons(rap))["src/pages/index.astro"].startswith("fichier ignoré (illisible"))


class TestErreurIsolee(unittest.TestCase):
    def test_une_regle_qui_plante_n_arrete_pas_le_scan(self):
        astro_scan.reinitialiser()
        self.addCleanup(astro_scan.reinitialiser)
        with tempfile.TemporaryDirectory() as d:
            racine = projet(d, {"src/pages/a.astro": "<img src=x>\n", "src/lib/b.ts": "export const x = '<Avis client:load />';\n"})
            origine = astro_scan.img_issues

            def boum(texte):
                raise RuntimeError("règle cassée")
            astro_scan.img_issues = boum
            try:
                astro_scan.scan_src(racine, {})
            finally:
                astro_scan.img_issues = origine
        self.assertIn({"fichier": "src/pages/a.astro", "raison": "fichier ignoré (erreur RuntimeError pendant l'analyse)"}, astro_scan.IGNORES)
        self.assertTrue(any("client:load" in f["constat"] for f in astro_scan.findings), "les autres fichiers restent analysés")


def constat(rapport, debut):
    return [c for c in rapport.get("constats", []) if c["constat"].startswith(debut)]


class TestLiensSymboliques(unittest.TestCase):
    """Fix round 1 (I1) : les liens qui restent dans le projet sont suivis (garde de cycle sur le realpath),
    ceux qui en sortent ne sont jamais suivis et sont notés."""

    WIDGET = "<Avis client:visible />\n<div set:html={x} />\n<script async src=\"https://code.tawk.to/x.js\"></script>\n"

    def test_liens_dans_le_projet_suivis(self):  # monorepo : composants partagés sous packages/, liés dans src/
        def prep(racine):
            os.symlink("../../packages/shared", racine / "src/lib/shared")      # dossier lié
            os.symlink("../../packages/solo.astro", racine / "src/lib/solo.astro")  # fichier lié
            os.symlink("../../packages/shared", racine / "src/lib/shared-bis")  # même cible : lue une seule fois
        r, rap, _, _ = scanner({"packages/shared/Widget.astro": self.WIDGET, "packages/solo.astro": "<Chat client:load />\n",
                                "src/lib/.gardien": ""}, prep=prep)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertEqual(rap["hydratation"]["compte"], {"visible": 1, "load": 1})
        self.assertTrue(constat(rap, "1 usage(s) de set:html"), [c["constat"] for c in rap["constats"]])
        self.assertTrue(constat(rap, "1 script(s)/embed(s) tiers"), [c["constat"] for c in rap["constats"]])
        self.assertEqual(raisons(rap), [])

    def test_liens_hors_du_projet_jamais_suivis_et_notes(self):
        def prep(racine):
            ext = racine.parent / "exterieur"
            ext.mkdir()
            (ext / "Ext.astro").write_text("<Piege client:load />\n", encoding="utf-8")
            os.symlink("../../../exterieur", racine / "src/lib/ext")                 # dossier hors du projet
            os.symlink("../../../exterieur/Ext.astro", racine / "src/lib/Out.astro")  # fichier hors du projet
        r, rap, _, _ = scanner({"src/lib/.gardien": ""}, prep=prep)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertEqual(rap["hydratation"]["compte"], {}, "rien de l'extérieur n'est lu")
        self.assertEqual(sorted(raisons(rap)), [("src/lib/Out.astro", "fichier ignoré (lien hors du projet)"),
                                                ("src/lib/ext", "fichier ignoré (lien hors du projet)")])

    def test_boucle_de_liens(self):
        def prep(racine):
            os.symlink("..", racine / "src/boucle")
            os.symlink(".", racine / "src/pages/self")
            os.symlink("../pages", racine / "src/pages/miroir")
        r, rap, _, duree = scanner({"src/pages/hydrate.astro": "<A client:load />\n"}, prep=prep)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertEqual(rap["hydratation"]["compte"], {"load": 1}, "chaque fichier est lu une seule fois")
        self.assertEqual(raisons(rap), [])
        self.assertLess(duree, 30)


class TestBudget(unittest.TestCase):
    MIDDLEWARE = "export const onRequest = (c, next) => { r.headers.set('Content-Security-Policy', \"default-src 'self'\"); return next(); };\n"

    def test_budget_epuise_pas_de_constat_d_absence(self):
        r, rap, md, _ = scanner({"src/middleware/index.ts": self.MIDDLEWARE}, env={"ASTRO_SCAN_BUDGET_S": "0"})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        textes = [c["constat"] for c in rap["constats"]]
        self.assertFalse([t for t in textes if "Aucune Content-Security-Policy" in t], textes)
        interrompu = constat(rap, "Scan du code interrompu")
        self.assertEqual(len(interrompu), 1, textes)
        self.assertEqual(interrompu[0]["severite"], "moyenne")
        self.assertEqual(interrompu[0]["constat"], "Scan du code interrompu (budget de 0 s) : 2 fichiers non lus — constats d'absence non évalués")
        self.assertEqual(rap["scan_interrompu"], {"budget_s": 0, "fichiers_non_lus": 2})

    def test_sans_interruption_la_regle_d_absence_reste_evaluee(self):  # témoin : sans CSP, le constat sort bien
        r, rap, _, _ = scanner({})
        self.assertTrue(constat(rap, "Aucune Content-Security-Policy"))
        self.assertEqual(constat(rap, "Scan du code interrompu"), [])

    def test_variables_d_environnement_invalides(self):
        r, rap, _, _ = scanner({}, env={"ASTRO_SCAN_MAX_OCTETS": "abc", "ASTRO_SCAN_BUDGET_S": "xyz"})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertEqual(constat(rap, "Scan du code interrompu"), [])


def lancer_main(racine, sortie):
    argv = sys.argv
    sys.argv = ["astro_scan.py", str(racine), "--out", str(sortie)]
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            astro_scan.main()
    finally:
        sys.argv = argv
    return json.loads(pathlib.Path(sortie, "code-scan.json").read_text(encoding="utf-8"))


class TestEtatGlobal(unittest.TestCase):
    def setUp(self):
        self.addCleanup(astro_scan.reinitialiser)

    def test_deux_main_dans_le_meme_processus(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2, tempfile.TemporaryDirectory() as d3:
            p1 = projet(d1, {"src/data/geant.ts": "export const d = '" + "a" * 2_000_000 + "';\n"})
            p2 = projet(d2, {})
            seul = lancer_main(p2, pathlib.Path(d2, "out0"))
            lancer_main(p1, pathlib.Path(d1, "out"))
            second = lancer_main(p2, pathlib.Path(d2, "out"))
            self.assertEqual(second["fichiers_ignores"], [])
            self.assertEqual(second["constats"], seul["constats"], "aucun constat du projet précédent")

    def test_le_chronometre_demarre_avec_main(self):
        astro_scan._DEBUT = time.monotonic() - 10_000  # import « ancien » : ne doit pas épuiser le budget
        with tempfile.TemporaryDirectory() as d:
            rapport = lancer_main(projet(d, {}), pathlib.Path(d, "out"))
        self.assertNotIn("scan_interrompu", rapport)

    def test_chemins_relatifs_sans_main(self):
        astro_scan.reinitialiser()
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d, "gros.json")
            f.write_bytes(b"x" * 10)
            ancien, astro_scan.MAX_OCTETS = astro_scan.MAX_OCTETS, 5
            try:
                astro_scan.read(f)                      # racine inconnue : jamais de chemin absolu
                astro_scan.read(f, pathlib.Path(d))     # racine explicite : même entrée, pas de doublon
            finally:
                astro_scan.MAX_OCTETS = ancien
        self.assertEqual([i["fichier"] for i in astro_scan.IGNORES], ["gros.json"], "ni chemin absolu ni doublon")


class TestVisibilite(unittest.TestCase):
    def test_fichiers_ignores_dans_les_constats(self):
        binaires = {f"src/bin/b{i:02d}.astro": b"\x00\x01" * 100 for i in range(12)}
        r, rap, md, _ = scanner(binaires)
        c = constat(rap, "12 fichier(s) ignoré(s) par le scan (trop gros / binaire / illisible / lien hors projet)")
        self.assertEqual(len(c), 1, [x["constat"] for x in rap["constats"]])
        self.assertEqual(c[0]["severite"], "basse")
        self.assertEqual(len(c[0]["ou"]), 11)
        self.assertEqual(c[0]["ou"][0], "src/bin/b00.astro : fichier ignoré (binaire)")
        self.assertEqual(c[0]["ou"][-1], "… et 2 autres")
        self.assertIn("src/bin/b00.astro", md)

    def test_liste_plafonnee_a_50(self):
        binaires = {f"src/bin/b{i:03d}.astro": b"\x00\x01" * 100 for i in range(60)}
        r, rap, md, _ = scanner(binaires)
        self.assertEqual(len(rap["fichiers_ignores"]), 51)
        self.assertEqual(rap["fichiers_ignores"][-1], {"fichier": "…", "raison": "… et 10 autres"})
        self.assertEqual(rap["nb_fichiers_ignores"], 60)
        self.assertIn("- … et 10 autres", md)
        self.assertTrue(constat(rap, "60 fichier(s) ignoré(s) par le scan"))

    def test_rien_d_ignore_pas_de_constat(self):
        r, rap, _, _ = scanner({})
        self.assertEqual(constat(rap, "0 fichier"), [])
        self.assertFalse([c for c in rap["constats"] if "ignoré(s) par le scan" in c["constat"]])

    def test_etape_en_erreur_visible(self):
        astro_scan.reinitialiser()
        self.addCleanup(astro_scan.reinitialiser)
        original = astro_scan.scan_repo

        def boum(root, report):
            raise RuntimeError("dépôt cassé")
        astro_scan.scan_repo = boum
        try:
            with tempfile.TemporaryDirectory() as d:
                rapport = lancer_main(projet(d, {}), pathlib.Path(d, "out"))
        finally:
            astro_scan.scan_repo = original
        self.assertTrue(rapport["etapes_en_erreur"][0].startswith("scan_repo : RuntimeError"))
        self.assertTrue(constat(rapport, "1 étape(s) du scan de code en erreur"), [c["constat"] for c in rapport["constats"]])


class TestAutresGardes(unittest.TestCase):
    def test_config_trop_grosse_notee(self):
        r, rap, _, _ = scanner({"astro.config.mjs": "// " + "x" * 2_000_000 + "\nexport default { site: 'https://ex.fr' };\n"})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertIn(("astro.config.mjs", "fichier ignoré (trop gros : 2.0 Mo > 1.5 Mo)"), raisons(rap))

    def test_bundle_demesure_note(self):
        r, rap, _, _ = scanner({"dist/client/_astro/enorme.js": b"a" * 21_000_000})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertIn(("dist/client/_astro/enorme.js", "fichier ignoré (trop gros pour la mesure gzip : > 20 Mo)"), raisons(rap))

    def test_package_astro_installe_invalide(self):
        r, rap, _, _ = scanner({"node_modules/astro/package.json": "{pas du json"})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])


class TestProjectChecks(unittest.TestCase):
    def test_sans_node_modules_ni_npm(self):
        with tempfile.TemporaryDirectory() as d:
            racine = projet(d, {"src/assets/photo lourde.png": os.urandom(300_000)})
            fauxbin = pathlib.Path(d, "bin")
            fauxbin.mkdir()
            (fauxbin / "npm").write_text("#!/bin/sh\ntouch \"$NPM_APPELE\"\nexit 1\n", encoding="utf-8")
            os.chmod(fauxbin / "npm", 0o755)
            env = dict(os.environ, PATH=str(fauxbin) + os.pathsep + os.environ["PATH"], NPM_APPELE=str(pathlib.Path(d, "npm-appele")))
            r = subprocess.run(["bash", str(SCRIPTS / "project_checks.sh"), str(racine), str(pathlib.Path(d, "out"))],
                               capture_output=True, text=True, timeout=120, env=env)
            md = pathlib.Path(d, "out/project-checks.md").read_text(encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stdout[-1500:])
            self.assertFalse(pathlib.Path(d, "npm-appele").exists(), "npm ne doit pas tourner sans node_modules")
        self.assertIn("node_modules absent", md)
        self.assertIn("src/assets/photo lourde.png", md)

    def test_coupe_utf8_sans_casser_un_caractere(self):  # fix round 1 (I2) : cut -c en octets tranchait les accents
        with tempfile.TemporaryDirectory() as d:
            racine = projet(d, {})
            (racine / "node_modules/astro").mkdir(parents=True)
            fauxbin = pathlib.Path(d, "bin")
            fauxbin.mkdir()
            journal = pathlib.Path(d, "journal.txt")
            # l'octet 300 tombe au milieu du « é » ; une 2e ligne contient un octet invalide
            journal.write_bytes(b"warn: " + b"a" * 293 + "é suite ✓".encode() + b"\nwarn: octet \xff invalide\n")
            (fauxbin / "npm").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            (fauxbin / "npx").write_text("#!/bin/sh\ncat \"$JOURNAL\"\n", encoding="utf-8")  # astro check / astro build : le journal
            for nom in ("npm", "npx"):
                os.chmod(fauxbin / nom, 0o755)
            env = dict(os.environ, PATH=str(fauxbin) + os.pathsep + os.environ["PATH"], JOURNAL=str(journal), LC_ALL="C")
            r = subprocess.run(["bash", str(SCRIPTS / "project_checks.sh"), str(racine), str(pathlib.Path(d, "out")), "--build"],
                               capture_output=True, timeout=120, env=env)
            brut = pathlib.Path(d, "out/project-checks.md").read_bytes()
        self.assertEqual(r.returncode, 0, r.stdout[-1500:])
        md = brut.decode("utf-8")  # lève UnicodeDecodeError si une coupe a tranché un caractère
        self.assertIn("a" * 293 + "é\n", md, "300 caractères, pas 300 octets")
        self.assertTrue([l for l in md.splitlines() if l.strip().endswith("warn: " + "a" * 293 + "é")], "ligne du résumé du build coupée à 300")
        self.assertIn("octet \ufffd invalide", md)


if __name__ == "__main__":
    unittest.main()
