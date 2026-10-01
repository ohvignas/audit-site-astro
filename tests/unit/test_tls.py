import os
import pathlib
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RACINE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"))
import crawl_site  # noqa: E402


class _Ok(BaseHTTPRequestHandler):
    def do_GET(self):
        corps = b"<html lang='fr'><head><title>t</title></head><body>ok</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *a):
        pass


@unittest.skipUnless(shutil.which("openssl"), "openssl requis")
class TestTlsNonVerifie(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        key, crt = pathlib.Path(cls.tmp.name, "k.pem"), pathlib.Path(cls.tmp.name, "c.pem")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=localhost",
                        "-keyout", str(key), "-out", str(crt)], check=True, capture_output=True)
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), _Ok)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(crt), str(key))
        cls.srv.socket = ctx.wrap_socket(cls.srv.socket, server_side=True)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"https://127.0.0.1:{cls.srv.server_port}/"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def test_refuse_par_defaut(self):
        os.environ.pop("AUDIT_INSECURE_TLS", None)
        self.assertEqual(crawl_site.fetch(self.url, timeout=5)["status"], 0)

    def test_accepte_en_mode_test(self):
        os.environ["AUDIT_INSECURE_TLS"] = "1"
        try:
            self.assertEqual(crawl_site.fetch(self.url, timeout=5)["status"], 200)
        finally:
            os.environ.pop("AUDIT_INSECURE_TLS", None)


class TestScriptsBash(unittest.TestCase):
    def test_chaque_script_curl_respecte_le_mode(self):
        scripts = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
        expected_curl = 'curl() { if [ "${AUDIT_INSECURE_TLS:-}" = "1" ]; then command curl -k "$@"; else command curl "$@"; fi; }'
        for nom in ("http_checks.sh", "security_probe.sh", "collect_all.sh"):
            self.assertIn(expected_curl, (scripts / nom).read_text(), nom)
        self.assertIn("--ignore-certificate-errors", (scripts / "lighthouse_run.sh").read_text())


class TestHttpChecksRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), _Ok)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}/"
        cls.script = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts/http_checks.sh"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_http_checks_with_insecure_tls_shows_warning(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            env = os.environ.copy()
            env["AUDIT_INSECURE_TLS"] = "1"
            result = subprocess.run(["bash", str(self.script), self.url, tmp.name],
                                    env=env, timeout=180, capture_output=True, text=True)
            report = pathlib.Path(tmp.name) / "http-checks.md"
            self.assertTrue(report.exists(), f"Report not created: {result.stdout}\n{result.stderr}")
            content = report.read_text()
            self.assertIn("⚠️ TLS non vérifié", content, f"Warning not found in:\n{content[:500]}")
        finally:
            tmp.cleanup()

    def test_http_checks_without_insecure_tls_no_warning(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            env = os.environ.copy()
            env.pop("AUDIT_INSECURE_TLS", None)
            result = subprocess.run(["bash", str(self.script), self.url, tmp.name],
                                    env=env, timeout=180, capture_output=True, text=True)
            report = pathlib.Path(tmp.name) / "http-checks.md"
            self.assertTrue(report.exists(), f"Report not created: {result.stdout}\n{result.stderr}")
            content = report.read_text()
            self.assertNotIn("⚠️ TLS non vérifié", content, f"Unexpected warning found in:\n{content[:500]}")
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
