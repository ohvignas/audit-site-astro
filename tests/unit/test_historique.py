import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
FIXTURE = RACINE / "tests/unit/fixtures/audit-exemple"
sys.path.insert(0, str(SCRIPTS))


def creer_site(racine, nom="beta.exemple.fr", dates=("2026-09-01", "2026-09-30")):
    """Dossier de site avec un audit par date (le dernier a une issue « haute » en moins) + un dossier parasite."""
    site = pathlib.Path(racine, nom)
    for d in dates:
        shutil.copytree(FIXTURE, site / d)
    p = site / dates[-1] / "data/crawl/issues.json"
    issues = json.loads(p.read_text(encoding="utf-8"))
    del issues["liens_casses"]  # la seule issue « haute » du crawl
    p.write_text(json.dumps(issues), encoding="utf-8")
    (site / "notes").mkdir()
    (site / "notes/lisez-moi.txt").write_text("pas un audit", encoding="utf-8")
    return site


def lancer(site):
    return subprocess.run([sys.executable, str(SCRIPTS / "historique.py"), str(site)], capture_output=True, text=True)


class TestAudits(unittest.TestCase):
    def test_deux_audits_tries_sans_le_dossier_parasite(self):
        import historique
        with tempfile.TemporaryDirectory() as t:
            site = creer_site(t)
            (site / "2026-08-15").mkdir()                      # daté mais sans data/ : ignoré
            (site / "2026-13-45").mkdir()                      # pas une vraie date
            (site / "2026-13-45/data").mkdir()
            (site / "2026-07-04").write_text("fichier", encoding="utf-8")  # fichier, pas dossier
            a = historique.audits(site)
        self.assertEqual([x["date"] for x in a], ["2026-09-01", "2026-09-30"])
        self.assertEqual(a[0]["chemin"], site / "2026-09-01")
        self.assertGreater(a[1]["note_globale"], a[0]["note_globale"])
        self.assertIn("Performance", a[0]["notes"])
        self.assertEqual(a[0]["perf_mobile"], 62)   # fixture : une seule mesure mobile, performance 62

    def test_dossier_vide_ou_absent(self):
        import historique
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(historique.audits(pathlib.Path(t)), [])
            self.assertEqual(historique.audits(pathlib.Path(t, "absent")), [])

    def test_perf_mobile_est_la_mediane_et_tolere_les_donnees_malformees(self):
        import historique
        with tempfile.TemporaryDirectory() as t:
            site = creer_site(t, dates=("2026-09-01",))
            p = site / "2026-09-01/data/perf/pagespeed.json"
            run = lambda s, v: {"url": "https://x/", "strategie": s, "scores": {"performance": v}}
            p.write_text(json.dumps([run("mobile", 40), run("mobile", 90), run("mobile", 70), run("desktop", 99),
                                     "n'importe quoi", {"strategie": "mobile", "scores": None}, run("mobile", None)]),
                         encoding="utf-8")
            self.assertEqual(historique.audits(site)[0]["perf_mobile"], 70)
            p.write_text("[]", encoding="utf-8")
            self.assertIsNone(historique.audits(site)[0]["perf_mobile"])


class TestPage(unittest.TestCase):
    def test_page_historique(self):
        with tempfile.TemporaryDirectory() as t:
            site = creer_site(t)
            (site / "2026-09-30/RAPPORT.html").write_text("<p>rapport</p>", encoding="utf-8")
            r = lancer(site)
            self.assertEqual(r.returncode, 0, r.stderr)
            h = (site / "index.html").read_text(encoding="utf-8")
        self.assertTrue(h.startswith("<!doctype html>"))
        self.assertIn("<title>Historique des audits — beta.exemple.fr</title>", h)
        self.assertIn("2026-09-01", h)
        self.assertIn("2026-09-30", h)
        self.assertIn("<polyline", h)
        self.assertIn('href="2026-09-30/RAPPORT.html"', h)
        self.assertNotIn("2026-09-01/RAPPORT.html", h)   # fichier absent : pas de lien mort
        self.assertNotIn("RAPPORT.pdf", h)
        self.assertNotIn("notes/", h)
        self.assertNotIn("<script", h.lower())
        self.assertNotRegex(h, r"(?i)(src|href)=\"https?://")
        self.assertIn("prefers-color-scheme: dark", h)
        self.assertIn("@page", h)

    def test_lien_pdf_seulement_si_le_fichier_existe(self):
        with tempfile.TemporaryDirectory() as t:
            site = creer_site(t)
            (site / "2026-09-01/RAPPORT.pdf").write_bytes(b"%PDF-1.4\n")
            lancer(site)
            h = (site / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="2026-09-01/RAPPORT.pdf"', h)
        self.assertNotIn("2026-09-30/RAPPORT.pdf", h)

    def test_ecart_avec_l_audit_precedent(self):
        import historique
        with tempfile.TemporaryDirectory() as t:
            site = creer_site(t)
            a = historique.audits(site)
            ecart = a[1]["note_globale"] - a[0]["note_globale"]
            lancer(site)
            h = (site / "index.html").read_text(encoding="utf-8")
        self.assertGreater(ecart, 0)
        self.assertIn(f"▲ +{ecart}", h)
        self.assertNotIn("▼", h)

    def test_baisse_affichee_en_rouge_avec_fleche_vers_le_bas(self):
        with tempfile.TemporaryDirectory() as t:
            site = creer_site(t, dates=("2026-09-01", "2026-09-30"))
            shutil.rmtree(site / "2026-09-30")
            shutil.copytree(FIXTURE, site / "2026-09-30")
            shutil.rmtree(site / "2026-09-01")
            shutil.copytree(FIXTURE, site / "2026-09-01")
            p = site / "2026-09-01/data/crawl/issues.json"       # le premier audit est meilleur que le second
            issues = json.loads(p.read_text(encoding="utf-8"))
            del issues["liens_casses"]
            p.write_text(json.dumps(issues), encoding="utf-8")
            lancer(site)
            h = (site / "index.html").read_text(encoding="utf-8")
        self.assertIn("▼ −", h)
        self.assertNotIn("▲", h)

    def test_un_seul_audit(self):
        with tempfile.TemporaryDirectory() as t:
            site = creer_site(t, dates=("2026-09-30",))
            r = lancer(site)
            self.assertEqual(r.returncode, 0, r.stderr)
            h = (site / "index.html").read_text(encoding="utf-8")
        self.assertIn("2026-09-30", h)
        self.assertIn("<circle", h)
        self.assertNotIn("<polyline", h)
        self.assertIn("premier audit", h.lower())

    def test_aucun_audit_produit_quand_meme_une_page(self):
        with tempfile.TemporaryDirectory() as t:
            site = creer_site(t, dates=("2026-09-30",))
            self.assertEqual(lancer(site).returncode, 0)
            shutil.rmtree(site / "2026-09-30")          # tous les audits supprimés : la page existante est régénérée
            r = lancer(site)
            self.assertEqual(r.returncode, 0, r.stderr)
            h = (site / "index.html").read_text(encoding="utf-8")
        self.assertIn("Aucun audit", h)

    def test_dossier_sans_audit_date_refuse_sans_rien_ecrire(self):
        with tempfile.TemporaryDirectory() as t:
            site = pathlib.Path(t, "vide.exemple.fr")
            site.mkdir()
            r = lancer(site)
            self.assertEqual(r.returncode, 2)
            self.assertIn("AAAA-MM-JJ", r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            self.assertFalse((site / "index.html").exists())

    def test_index_html_du_projet_jamais_ecrase(self):
        """Audit non daté (collect_all.sh URL . ./audit) puis « Régénérer » de SKILL.md : le parent est le projet."""
        with tempfile.TemporaryDirectory() as t:
            projet = pathlib.Path(t, "projet")
            shutil.copytree(FIXTURE, projet / "audit")
            original = "<!doctype html><title>Mon site</title><h1>Accueil du projet</h1>\n"
            (projet / "index.html").write_text(original, encoding="utf-8")
            r = lancer(projet)
            self.assertEqual(r.returncode, 2)
            self.assertIn("n'est pas une page historique", r.stderr)
            self.assertEqual((projet / "index.html").read_text(encoding="utf-8"), original)
            # même avec un dossier daté à côté : un index.html étranger n'est jamais remplacé
            shutil.copytree(FIXTURE, projet / "2026-09-30")
            self.assertEqual(lancer(projet).returncode, 2)
            self.assertEqual((projet / "index.html").read_text(encoding="utf-8"), original)
            self.assertFalse((projet / "index.html.tmp").exists())

    def test_page_historique_marquee_et_regeneree(self):
        import historique
        with tempfile.TemporaryDirectory() as t:
            site = creer_site(t)
            self.assertEqual(lancer(site).returncode, 0)
            h = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn(historique.MARQUEUR, h)
            self.assertEqual(lancer(site).returncode, 0)   # deuxième passage : la page de l'outil est remplacée
            # page d'une version précédente, sans marqueur : reconnue à son en-tête
            (site / "index.html").write_text(h.replace(historique.MARQUEUR, ""), encoding="utf-8")
            self.assertEqual(lancer(site).returncode, 0, "page historique sans marqueur refusée")

    def test_skill_ne_regenere_l_historique_que_pour_un_dossier_date(self):
        skill = (SCRIPTS.parent / "SKILL.md").read_text(encoding="utf-8")
        ligne = next(l for l in skill.splitlines() if "historique.py" in l and "dirname" in l)
        self.assertIn("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]", ligne)
        self.assertIn('basename "$AUDIT"', ligne)

    def test_texte_dynamique_echappe(self):
        with tempfile.TemporaryDirectory() as t:
            site = creer_site(t, nom="<img src=x onerror=alert(1)>.fr")
            r = lancer(site)
            self.assertEqual(r.returncode, 0, r.stderr)
            h = (site / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("<img", h)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;.fr", h)

    def test_dossier_de_site_inexistant(self):
        with tempfile.TemporaryDirectory() as t:
            r = lancer(pathlib.Path(t, "absent"))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)

    def test_courbe_avec_beaucoup_d_audits(self):
        import historique
        dates = [f"2026-{m:02d}-{j:02d}" for m in (7, 8, 9) for j in (1, 8, 15, 22)]
        with tempfile.TemporaryDirectory() as t:
            site = creer_site(t, dates=dates)
            self.assertEqual(len(historique.audits(site)), 12)
            lancer(site)
            h = (site / "index.html").read_text(encoding="utf-8")
        pts = re.search(r'<polyline[^>]*points="([^"]+)"', h).group(1).split()
        self.assertEqual(len(pts), 12)


if __name__ == "__main__":
    unittest.main()
