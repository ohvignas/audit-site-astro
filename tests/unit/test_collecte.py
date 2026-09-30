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
                self.assertEqual(r.returncode, 1, r.stdout[-2000:])
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
