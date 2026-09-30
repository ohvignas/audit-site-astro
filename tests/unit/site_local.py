"""Petit site HTTP local pour les tests (stdlib, aucun réseau externe).

routes   : {chemin sans requête: (statut, en-têtes, corps)}
prefixes : {préfixe: (statut, en-têtes, corps)} utilisés si aucune route exacte ne correspond ; sinon 404.
Le jeton @@BASE@@ du corps et des en-têtes est remplacé par l'origine du serveur (http://127.0.0.1:PORT).
"""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HTML = {"Content-Type": "text/html; charset=utf-8"}
PAGE_404 = (404, HTML, "<html><body>introuvable</body></html>")


class SiteLocal:
    def __init__(self, routes, prefixes=None):
        self.routes, self.prefixes = routes, prefixes or {}
        self.base = ""

    def _reponse(self, chemin):
        rep = self.routes.get(chemin.split("?", 1)[0])
        if rep is None:
            rep = next((v for k, v in self.prefixes.items() if chemin.startswith(k)), None)
        return rep or PAGE_404

    def __enter__(self):
        site = self

        class Gestionnaire(BaseHTTPRequestHandler):
            def _repondre(self):
                statut, entetes, corps = site._reponse(self.path)
                if isinstance(corps, str):
                    corps = corps.replace("@@BASE@@", site.base).encode("utf-8")
                self.send_response(statut)
                for k, v in entetes.items():
                    self.send_header(k, v.replace("@@BASE@@", site.base))
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(corps)

            do_GET = do_HEAD = do_OPTIONS = _repondre

            def log_message(self, *args):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:{0}".format(self.srv.server_port)
        self.url = self.base + "/"
        return self

    def __exit__(self, *exc):
        self.srv.shutdown()
        self.srv.server_close()
