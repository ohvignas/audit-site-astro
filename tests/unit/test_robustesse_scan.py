"""Gardes du scan de code restants après v2.0.1 : le scan finit et note ce qu'il ignore au lieu de planter."""
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


def scanner(fichiers, prep=None):
    with tempfile.TemporaryDirectory() as d:
        racine = projet(d, fichiers)
        if prep:
            prep(racine)
        t0 = time.monotonic()
        r = subprocess.run([sys.executable, str(SCRIPTS / "astro_scan.py"), str(racine), "--out", str(pathlib.Path(d, "out"))],
                           capture_output=True, text=True, timeout=120, env=ENV)
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
        astro_scan.findings.clear()
        astro_scan.IGNORES.clear()
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


if __name__ == "__main__":
    unittest.main()
