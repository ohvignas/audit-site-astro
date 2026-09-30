import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
FIXTURE = RACINE / "tests/unit/fixtures/audit-exemple"
sys.path.insert(0, str(SCRIPTS))


class TestSignaux(unittest.TestCase):
    def test_collecter_trie_et_type(self):
        import signaux
        s = signaux.collecter(FIXTURE)
        self.assertTrue(s)
        rangs = [signaux.ORDRE[x["severite"]] for x in s]
        self.assertEqual(rangs, sorted(rangs))
        for x in s:
            self.assertEqual(set(x), {"severite", "domaine", "texte", "exemples", "source", "cle"})

    def test_source_et_cle_coherentes(self):
        import signaux
        s = signaux.collecter(FIXTURE)
        for x in s:
            self.assertIn(x["source"], {"crawl", "geo", "code", "http", "securite", "lighthouse", "projet"})
            self.assertTrue(x["cle"], x)
        par = {}
        for x in s:
            par.setdefault(x["source"], []).append(x["cle"])
        self.assertEqual(set(par), {"crawl", "geo", "code", "http", "securite", "lighthouse"})
        # crawl : clé d'issue
        self.assertIn("liens_casses", par["crawl"])
        self.assertIn("title_manquant", par["crawl"])
        # geo : texte du signal
        self.assertIn("llms.txt absent : les assistants IA n'ont pas de résumé du site", par["geo"])
        # code : texte du constat, sans la piste
        self.assertIn("Image d'en-tête non optimisée (<img> au lieu de <Image>)", par["code"])
        self.assertIn("Balise canonical absente du layout", par["code"])
        # http / sécurité : ligne brute du fichier
        self.assertIn("| /.git/config | ❌ EXPOSÉ (critique) |", par["securite"])
        self.assertIn("| Server / X-Powered-By | nginx/1.24.0 / — | ⚠️ version exposée |", par["http"])
        self.assertEqual(len(par["http"]), 2)
        # lighthouse : "<id> <titre>" (opportunités) ou titre de l'échec
        self.assertIn("render-blocking-resources Éliminer les ressources qui bloquent le rendu", par["lighthouse"])
        self.assertIn("Les liens n'ont pas de nom discernable", par["lighthouse"])
        self.assertIn("Le contraste des couleurs est insuffisant", par["lighthouse"])

    def test_signaux_projet(self):
        import signaux
        with tempfile.TemporaryDirectory() as t:
            copie = pathlib.Path(t, "audit")
            shutil.copytree(FIXTURE, copie)
            (copie / "data/code/project-checks.md").write_text(
                "# Santé du projet — site\n\n"
                "- Node : v18.0.0 — gestionnaire : npm 9\n"
                "- \u26a0\ufe0f Node 18 : versions récentes d'Astro exigent Node \u2265 20 (LTS conseillée)\n\n"
                "## Dépendances obsolètes\n\n"
                "| Paquet | Installé | Compatible | Dernière | Saut majeur |\n|---|---|---|---|---|\n"
                "| astro | 4.0.0 | 4.16.0 | 5.1.0 | \u26a0\ufe0f oui |\n"
                "| vite | 4.0.0 | 4.5.0 | 6.0.0 | \u26a0\ufe0f oui |\n"
                "| tailwindcss | 3.4.0 | 3.4.1 | 4.0.0 | \u26a0\ufe0f oui |\n"
                "| zod | 3.22.0 | 3.23.0 | 3.23.8 | non |\n\n"
                "## Vulnérabilités connues (dépendances de production)\n\n"
                "- Total : high 1, moderate 1, low 2 (total 4)\n"
                "- **critical** lodash — Prototype Pollution (correctif dispo)\n"
                "- **high** vite — Path traversal (via vite@5.4.0)\n"
                "- **moderate** esbuild — Dev server SSRF (pas de correctif)\n"
                "- **low** foo — mineur (correctif dispo)\n\n"
                "## astro check (types et diagnostics)\n\n"
                "- Lignes d'erreur : 3 \u2014 avertissements : 2 (détail : astro-check.txt)\n"
                "- \u274c astro check : 3 erreur(s) de diagnostic\n"
                "- \u26a0\ufe0f astro check : 2 avertissement(s)\n",
                encoding="utf-8")
            s = signaux.collecter(copie)
        p = [x for x in s if x["source"] == "projet"]
        par = {x["cle"]: x for x in p}
        self.assertEqual(len(p), len(par))
        self.assertEqual(len(p), 7)
        for x in p:
            self.assertEqual(x["domaine"], "Code")
        ligne = "- **critical** lodash \u2014 Prototype Pollution (correctif dispo)"
        self.assertEqual(par[ligne]["severite"], "critique")
        self.assertEqual(par[ligne]["texte"], "critical lodash \u2014 Prototype Pollution (correctif dispo)")
        self.assertEqual(par["- **high** vite \u2014 Path traversal (via vite@5.4.0)"]["severite"], "haute")
        self.assertEqual(par["- **moderate** esbuild \u2014 Dev server SSRF (pas de correctif)"]["severite"], "moyenne")
        ligne = "- \u274c astro check : 3 erreur(s) de diagnostic"
        self.assertEqual(par[ligne]["severite"], "haute")
        self.assertEqual(par[ligne]["texte"], "\u274c astro check : 3 erreur(s) de diagnostic")
        ligne = "- \u26a0\ufe0f astro check : 2 avertissement(s)"
        self.assertEqual(par[ligne]["severite"], "basse")
        # sauts de version majeure : UN seul signal agrégé (pas de signal par ligne de tableau)
        self.assertFalse([c for c in par if c.startswith("| astro") or c.startswith("| vite")])
        agg = par["dépendances obsolètes saut majeur : astro, vite, tailwindcss"]
        self.assertEqual(agg["severite"], "basse")
        self.assertEqual(agg["texte"], "3 dépendance(s) avec saut de version majeure : astro, vite, tailwindcss")
        self.assertEqual(agg["exemples"], ["astro \u00b7 4.0.0 \u00b7 4.16.0 \u00b7 5.1.0 \u00b7 \u26a0\ufe0f oui",
                                           "vite \u00b7 4.0.0 \u00b7 4.5.0 \u00b7 6.0.0 \u00b7 \u26a0\ufe0f oui",
                                           "tailwindcss \u00b7 3.4.0 \u00b7 3.4.1 \u00b7 4.0.0 \u00b7 \u26a0\ufe0f oui"])
        self.assertIn("- \u26a0\ufe0f Node 18 : versions récentes d'Astro exigent Node \u2265 20 (LTS conseillée)", par)
        rangs = [signaux.ORDRE[x["severite"]] for x in s]
        self.assertEqual(rangs, sorted(rangs))

    def test_rapport_brut_inchange(self):
        """La sortie de rapport_brut.py doit être identique avant/après le refactor (référence commitée)."""
        with tempfile.TemporaryDirectory() as t:
            copie = pathlib.Path(t, "audit")
            shutil.copytree(FIXTURE, copie)
            subprocess.run([sys.executable, str(SCRIPTS / "rapport_brut.py"), str(copie)], check=True, capture_output=True)
            obtenu = (copie / "RAPPORT-BRUT.md").read_text(encoding="utf-8")
        attendu = (FIXTURE / "RAPPORT-BRUT.attendu.md").read_text(encoding="utf-8")
        self.assertEqual(obtenu, attendu)

    def test_sauts_majeurs_plafonnes(self):
        import signaux
        with tempfile.TemporaryDirectory() as t:
            copie = pathlib.Path(t, "audit")
            shutil.copytree(FIXTURE, copie)
            lignes = "".join(f"| pkg{i} | 1.0.0 | 1.0.1 | 2.0.0 | \u26a0\ufe0f oui |\n" for i in range(13))
            (copie / "data/code/project-checks.md").write_text("## Dépendances obsolètes\n\n" + lignes, encoding="utf-8")
            p = [x for x in signaux.collecter(copie) if x["source"] == "projet"]
        self.assertEqual(len(p), 1)
        self.assertTrue(p[0]["texte"].startswith("13 dépendance(s) avec saut de version majeure : pkg0, pkg1"))
        self.assertTrue(p[0]["texte"].endswith("pkg9, … et 3 autres"))
        self.assertEqual(len(p[0]["exemples"]), 11)
        self.assertEqual(p[0]["exemples"][-1], "… et 3 autres")
        self.assertEqual(p[0]["cle"], "dépendances obsolètes saut majeur : " + ", ".join(f"pkg{i}" for i in range(13)))

    def test_project_checks_emet_les_lignes_astro_check(self):
        """Le snippet de project_checks.sh produit exactement les lignes que signaux.py transforme en signaux."""
        script = (SCRIPTS / "project_checks.sh").read_text(encoding="utf-8")
        self.assertIn('echo "- ❌ astro check : ${errs} erreur(s) de diagnostic"', script)
        self.assertIn('echo "- ⚠️ astro check : ${warns} avertissement(s)"', script)
        debut = script.index("  errs=$(grep")
        fin = script.index('  grep -q "@astrojs/check"')
        with tempfile.TemporaryDirectory() as t:
            pathlib.Path(t, "astro-check.txt").write_text("a.astro:1:1 - error ts(1): x\nb.astro:2:2 - error ts(2): y\nc.astro - warning: z\n", encoding="utf-8")
            r = subprocess.run(["bash", "-c", "set -u\nOUT=" + t + "\n" + script[debut:fin] + "\ntrue"], capture_output=True, text=True, check=True)
            sortie = r.stdout
            pathlib.Path(t, "astro-check.txt").write_text("tout va bien\n", encoding="utf-8")
            propre = subprocess.run(["bash", "-c", "set -u\nOUT=" + t + "\n" + script[debut:fin] + "\ntrue"], capture_output=True, text=True, check=True).stdout
        self.assertIn("- ❌ astro check : 2 erreur(s) de diagnostic", sortie)
        self.assertIn("- ⚠️ astro check : 1 avertissement(s)", sortie)
        self.assertNotIn("astro check :", propre.replace("Lignes", ""))


if __name__ == "__main__":
    unittest.main()
