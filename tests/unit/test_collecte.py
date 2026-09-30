import http.server
import os
import pathlib
import subprocess
import tempfile
import threading
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
                self.assertIn("⏭️", next(l for l in collecte.splitlines() if l.startswith("| pdf")))
                self.assertTrue(pathlib.Path(d, "RAPPORT.html").exists())
                self.assertFalse(pathlib.Path(d, "RAPPORT.pdf").exists())
                self.assertEqual(r.returncode, 1, r.stdout[-2000:])
        finally:
            srv.shutdown()
            srv.server_close()


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

    def test_skip_pdf_seul_ignore_l_etape(self):
        r, collecte = self._lancer(_PageHtml, SKIP_LIGHTHOUSE="1", SKIP_PDF="1", FORCE_PDF="1")
        ligne = next(l for l in collecte.splitlines() if l.startswith("| pdf"))
        self.assertIn("⏭️", ligne)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:])


if __name__ == "__main__":
    unittest.main()
