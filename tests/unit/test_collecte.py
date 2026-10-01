import http.server
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import threading
import time
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts/collect_all.sh"


class _JsonSeulement(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        corps = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def log_message(self, *args):
        pass


class _PageHtml(http.server.BaseHTTPRequestHandler):
    PAGE = ("<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\"><title>Accueil de test</title>"
            "<meta name=\"description\" content=\"Page de test\"></head><body><h1>Bonjour</h1></body></html>").encode()

    def _repondre(self):
        ok = self.path in ("/", "/index.html")
        corps = self.PAGE if ok else b"introuvable"
        self.send_response(200 if ok else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8" if ok else "text/plain")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corps)

    do_GET = do_HEAD = _repondre

    def log_message(self, *args):
        pass


class _Erreur503(http.server.BaseHTTPRequestHandler):
    def _repondre(self):
        corps = b"indisponible"
        self.send_response(503)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corps)

    do_GET = do_HEAD = do_POST = _repondre

    def log_message(self, *args):
        pass


def lire_collecte(dossier):
    return pathlib.Path(dossier, "data", "COLLECTE.md").read_text(encoding="utf-8")


class TestPreVol(unittest.TestCase):
    def test_domaine_inexistant_arrete_tout(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run(["bash", str(SCRIPT), "https://nx-audit-cobaye.invalid/", "", d],
                               capture_output=True, text=True, timeout=180)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("injoignable", lire_collecte(d))
            self.assertFalse(pathlib.Path(d, "data", "crawl").exists(), "aucune étape ne doit tourner")

    def test_accueil_en_503_arrete_tout(self):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Erreur503)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_port}/"
            with tempfile.TemporaryDirectory() as d:
                r = subprocess.run(["bash", str(SCRIPT), url, "", d], capture_output=True, text=True, timeout=180)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("HTTP 503", lire_collecte(d))
                self.assertFalse(pathlib.Path(d, "data", "crawl").exists(), "aucune étape ne doit tourner")
        finally:
            srv.shutdown()
            srv.server_close()


class TestValidationDesEtapes(unittest.TestCase):
    def test_site_sans_html_donne_crawl_en_echec(self):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _JsonSeulement)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_port}/"
            with tempfile.TemporaryDirectory() as d:
                env = dict(os.environ, SKIP_LIGHTHOUSE="1", MAX_PAGES="3")
                r = subprocess.run(["bash", str(SCRIPT), url, "", d],
                                   capture_output=True, text=True, timeout=600, env=env)
                collecte = lire_collecte(d)
                ligne_crawl = next(l for l in collecte.splitlines() if l.startswith("| crawl"))
                self.assertIn("❌", ligne_crawl)
                self.assertIn("⏭️", next(l for l in collecte.splitlines() if l.startswith("| lighthouse")))
                self.assertIn("✅", next(l for l in collecte.splitlines() if l.startswith("| rapport-html")))
                # dossier CORRECTIONS/ produit même sans donnée exploitable (plan vide), étape entre « rapport brut » et « rapport-html »
                self.assertIn("✅", next(l for l in collecte.splitlines() if l.startswith("| corrections")))
                self.assertTrue(pathlib.Path(d, "CORRECTIONS", "LISEZ-MOI.md").exists())
                self.assertTrue(pathlib.Path(d, "CORRECTIONS", "00-PLAN.md").exists())
                self.assertIn("⏭️", next(l for l in collecte.splitlines() if l.startswith("| pdf")))
                # dossier d'audit non daté : le parent n'est pas un dossier de site, rien n'y est écrit
                self.assertIn("⏭️", next(l for l in collecte.splitlines() if l.startswith("| historique")))
                self.assertFalse(pathlib.Path(d).parent.joinpath("index.html").exists())
                self.assertTrue(pathlib.Path(d, "RAPPORT.html").exists())
                self.assertFalse(pathlib.Path(d, "RAPPORT.pdf").exists())
                self.assertEqual(r.returncode, 1, r.stdout[-2000:])
        finally:
            srv.shutdown()
            srv.server_close()


class TestEtapeCorrections(unittest.TestCase):
    def _lancer(self, script, d):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _PageHtml)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_port}/"
            env = dict(os.environ, MAX_PAGES="3", SKIP_LIGHTHOUSE="1")
            r = subprocess.run(["bash", str(script), url, "", str(d)], capture_output=True, text=True, timeout=600, env=env)
            return r, url
        finally:
            srv.shutdown()
            srv.server_close()

    def test_etape_entre_rapport_brut_et_rapport_html(self):
        with tempfile.TemporaryDirectory() as t:
            audit = pathlib.Path(t, "site.exemple.fr", "2026-09-30")
            r, url = self._lancer(SCRIPT, audit)
            lignes = [l for l in lire_collecte(audit).splitlines() if l.startswith("| ") and not l.startswith("| Étape")]
            noms = [l.split("|")[1].strip() for l in lignes]
            self.assertLess(noms.index("rapport-brut"), noms.index("corrections"))
            self.assertEqual(noms.index("corrections") + 1, noms.index("rapport-html"))
            ligne = lignes[noms.index("corrections")]
            self.assertIn("✅", ligne)
            self.assertIn("CORRECTIONS/LISEZ-MOI.md", ligne)
            corr = audit / "CORRECTIONS"
            self.assertTrue((corr / "LISEZ-MOI.md").exists() and (corr / "00-PLAN.md").exists() and (corr / "index.json").exists())
            self.assertIn(url, (corr / "LISEZ-MOI.md").read_text(encoding="utf-8"))
            self.assertIn("2026-09-30", (corr / "LISEZ-MOI.md").read_text(encoding="utf-8"))
            self.assertEqual(r.returncode, 0, r.stdout[-2000:])

    def test_echec_de_l_etape_compte_comme_les_autres(self):
        # copie des scripts sans references/fiches : corrections.py ne trouve pas ses fiches -> ❌ et code de sortie 1
        with tempfile.TemporaryDirectory() as t:
            scripts = pathlib.Path(t, "skill", "scripts")
            shutil.copytree(SCRIPT.parent, scripts, ignore=shutil.ignore_patterns("__pycache__"))
            audit = pathlib.Path(t, "audit")
            r, _ = self._lancer(scripts / "collect_all.sh", audit)
            ligne = next(l for l in lire_collecte(audit).splitlines() if l.startswith("| corrections"))
            self.assertIn("❌", ligne)
            self.assertFalse((audit / "CORRECTIONS").exists())
            self.assertIn("✅", next(l for l in lire_collecte(audit).splitlines() if l.startswith("| rapport-html")))
            self.assertEqual(r.returncode, 1, r.stdout[-2000:])


    # --- dossier réellement écrit : data/corrections-dossier.txt ---------------------------------------------------
    def _ancien_dossier(self, audit, age=3600):
        """CORRECTIONS/ d'une exécution précédente (LISEZ-MOI.md + index.json datés d'il y a `age` secondes) et son pointeur."""
        corr = audit / "CORRECTIONS"
        corr.mkdir(parents=True)
        (audit / "data").mkdir(exist_ok=True)
        (audit / "data/corrections-dossier.txt").write_text("CORRECTIONS\n", encoding="utf-8")
        ancien = time.time() - age
        for nom, contenu in (("LISEZ-MOI.md", "ancien"), ("index.json", json.dumps({"version": 1, "corrections": [], "sans_fiche": []}))):
            (corr / nom).write_text(contenu, encoding="utf-8")
            os.utime(str(corr / nom), (ancien, ancien))
        return corr

    def _scripts_sans_fiches(self, t):
        scripts = pathlib.Path(t, "skill", "scripts")
        shutil.copytree(SCRIPT.parent, scripts, ignore=shutil.ignore_patterns("__pycache__"))
        return scripts

    def test_garder_l_etape_valide_le_nouveau_dossier_pas_l_ancien(self):
        with tempfile.TemporaryDirectory() as t:
            audit = pathlib.Path(t, "site.exemple.fr", "2026-09-30")
            ancien = self._ancien_dossier(audit)
            (ancien / ".garder").write_text("", encoding="utf-8")
            r, _ = self._lancer(SCRIPT, audit)
            ligne = next(l for l in lire_collecte(audit).splitlines() if l.startswith("| corrections"))
            nom = (audit / "data/corrections-dossier.txt").read_text(encoding="utf-8").strip()
            self.assertRegex(nom, r"^CORRECTIONS-\d{8}-\d{6}(-\d+)?$")
            self.assertIn("✅", ligne)
            self.assertIn(f"{nom}/LISEZ-MOI.md", ligne)
            self.assertEqual((ancien / "LISEZ-MOI.md").read_text(encoding="utf-8"), "ancien")
            self.assertTrue((audit / nom / "index.json").exists())
            # l'avertissement de corrections.py (rangé dans le log de l'étape) est répété à l'écran et dans COLLECTE.md
            self.assertIn(".garder", r.stdout)
            self.assertIn(nom, r.stdout)
            conserve = next(l for l in lire_collecte(audit).splitlines() if l.startswith("| corrections (dossier conservé)"))
            self.assertIn(f"donner {nom}/", conserve)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:])

    def test_ancien_dossier_ne_valide_pas_une_etape_en_echec(self):
        # fiches introuvables : corrections.py échoue ; CORRECTIONS/ (ancien) et son pointeur existent, mais l'index est plus vieux que l'étape
        with tempfile.TemporaryDirectory() as t:
            scripts = self._scripts_sans_fiches(t)
            audit = pathlib.Path(t, "audit")
            self._ancien_dossier(audit)
            r, _ = self._lancer(scripts / "collect_all.sh", audit)
            ligne = next(l for l in lire_collecte(audit).splitlines() if l.startswith("| corrections"))
            self.assertIn("❌", ligne)
            self.assertIn("inexploitable", ligne)
            self.assertTrue((audit / "CORRECTIONS/LISEZ-MOI.md").exists())
            self.assertNotIn("dossier conservé", lire_collecte(audit))
            self.assertEqual(r.returncode, 1, r.stdout[-2000:])

    def test_pointeur_hostile_invalide_l_etape(self):
        for hostile in ("../x\n", "/etc\n", "CORRECTIONS\nautre\n", "CORRECTIONS/../CORRECTIONS\n", ""):
            with self.subTest(hostile=hostile), tempfile.TemporaryDirectory() as t:
                scripts = self._scripts_sans_fiches(t)
                audit = pathlib.Path(t, "audit")
                ancien = self._ancien_dossier(audit, age=0)  # même un index tout neuf ne sauve pas un pointeur hostile
                (audit / "data/corrections-dossier.txt").write_text(hostile, encoding="utf-8")
                pathlib.Path(t, "x").mkdir()
                pathlib.Path(t, "x/index.json").write_text("{}", encoding="utf-8")
                self.assertTrue(ancien.is_dir())
                r, _ = self._lancer(scripts / "collect_all.sh", audit)
                ligne = next(l for l in lire_collecte(audit).splitlines() if l.startswith("| corrections"))
                self.assertIn("❌", ligne)
                self.assertNotIn("../x", ligne)
                self.assertEqual(r.returncode, 1, r.stdout[-2000:])

    def test_dossier_frais_sans_garder_reste_corrections(self):
        with tempfile.TemporaryDirectory() as t:
            audit = pathlib.Path(t, "site.exemple.fr", "2026-09-30")
            self._ancien_dossier(audit)  # ancien plan sans suivi ni .garder : recréé
            r, _ = self._lancer(SCRIPT, audit)
            ligne = next(l for l in lire_collecte(audit).splitlines() if l.startswith("| corrections"))
            self.assertIn("✅", ligne)
            self.assertIn("CORRECTIONS/LISEZ-MOI.md", ligne)
            self.assertEqual((audit / "data/corrections-dossier.txt").read_text(encoding="utf-8"), "CORRECTIONS\n")
            self.assertNotIn("dossier conservé", lire_collecte(audit))
            self.assertNotEqual((audit / "CORRECTIONS/LISEZ-MOI.md").read_text(encoding="utf-8"), "ancien")
            self.assertEqual(r.returncode, 0, r.stdout[-2000:])


class TestEtapePdf(unittest.TestCase):
    def _lancer(self, handler, **env_extra):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_port}/"
            with tempfile.TemporaryDirectory() as d:
                env = dict(os.environ, MAX_PAGES="3", **env_extra)
                r = subprocess.run(["bash", str(SCRIPT), url, "", d], capture_output=True, text=True,
                                   timeout=600, env=env)
                return r, lire_collecte(d)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_chrome_absent_est_un_avertissement_pas_un_echec(self):
        # SKIP_LIGHTHOUSE=1 évite tout navigateur ; FORCE_PDF=1 (tests) force quand même l'étape pdf.
        r, collecte = self._lancer(_PageHtml, SKIP_LIGHTHOUSE="1", FORCE_PDF="1", CHROME_PATH="/inexistant",
                                   AUDIT_NO_CHROME_DISCOVERY="1")
        ligne = next(l for l in collecte.splitlines() if l.startswith("| pdf"))
        self.assertIn("⚠️ PDF non généré : Chrome introuvable", ligne)
        self.assertNotIn("❌", collecte, collecte)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:])

    def test_historique_est_la_derniere_etape_dans_le_dossier_du_site(self):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _PageHtml)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_port}/"
            with tempfile.TemporaryDirectory() as t:
                site = pathlib.Path(t, "beta.exemple.fr")
                audit = site / "2026-09-30"
                env = dict(os.environ, MAX_PAGES="3", SKIP_LIGHTHOUSE="1")
                r = subprocess.run(["bash", str(SCRIPT), url, "", str(audit)], capture_output=True, text=True,
                                   timeout=600, env=env)
                lignes = [l for l in lire_collecte(audit).splitlines() if l.startswith("| ") and not l.startswith("| Étape")]
                self.assertTrue(lignes[-1].startswith("| historique"), lignes[-1])
                self.assertIn("✅", lignes[-1])
                index = site / "index.html"
                self.assertTrue(index.exists(), r.stdout[-2000:])
                self.assertIn("2026-09-30", index.read_text(encoding="utf-8"))
                self.assertIn("Historique des audits — beta.exemple.fr", index.read_text(encoding="utf-8"))
        finally:
            srv.shutdown()
            srv.server_close()

    def test_skip_pdf_seul_ignore_l_etape(self):
        r, collecte = self._lancer(_PageHtml, SKIP_LIGHTHOUSE="1", SKIP_PDF="1", FORCE_PDF="1")
        ligne = next(l for l in collecte.splitlines() if l.startswith("| pdf"))
        self.assertIn("⏭️", ligne)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:])



class TestScriptsStatiques(unittest.TestCase):
    """Garde-fous lus dans le source (sans lancer d'audit)."""

    def test_sorties_a_chemin_fixe_effacees_avant_leur_etape(self):
        src = SCRIPT.read_text(encoding="utf-8")
        for sortie, etape in (('"$AUDIT/RAPPORT-BRUT.md"', "step rapport-brut "), ('"$AUDIT/RAPPORT.html"', "step rapport-html ")):
            i = src.index(etape)
            self.assertIn(f"rm -f {sortie}", src[src.rindex("\n", 0, i - 1) - 200:i], etape)

    def test_fraicheur_de_l_index_tolere_deux_secondes(self):
        self.assertIn(">= float(sys.argv[2]) - 2", SCRIPT.read_text(encoding="utf-8"))

    def test_entrypoint_calcule_la_date_une_seule_fois(self):
        e = (RACINE / "docker/entrypoint.sh").read_text(encoding="utf-8")
        self.assertEqual(e.count("date +%F"), 1)
        self.assertIn('AUDIT="/audits/$HOST/$JOUR"', e)

if __name__ == "__main__":
    unittest.main()


class TestEtapeSortieVide(unittest.TestCase):
    """Rapport utilisateur v2.0.0 : disque plein → RAPPORT.html de 0 octet affiché ✅. Une sortie vide est un échec,
    et la fin du journal de l'étape est affichée pour voir la vraie erreur."""

    def test_sortie_vide_echoue_et_journal_affiche(self):
        src = SCRIPT.read_text(encoding="utf-8")
        debut = src.index("step() {")
        fin = src.index("\n}\n", debut) + 3
        with tempfile.TemporaryDirectory() as d:
            prog = (f'set -u\nD="{d}"; AUDIT="{d}"; LOG="{d}/collecte.md"; FAILS=0\nvalid_aucun() {{ return 0; }}\n'
                    + src[debut:fin]
                    + f'\nstep essai "{d}/sortie.html" valid_aucun bash -c "echo No space left on device >&2; : > {d}/sortie.html"\n'
                    'echo "FAILS=$FAILS"\n')
            r = subprocess.run(["bash", "-c", prog], capture_output=True, text=True, timeout=60)
            self.assertIn("❌ sortie vide, 0 octet", r.stdout)
            self.assertIn("FAILS=1", r.stdout)
            self.assertIn("No space left on device", r.stdout)
