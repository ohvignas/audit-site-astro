import pathlib
import sys
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
import entetes_securite as es  # noqa: E402
import fiches  # noqa: E402


class TestCsp(unittest.TestCase):
    def codes(self, pols, xfo=False):
        return sorted(c for c, _ in es.analyser_csp(pols, xfo))

    def test_cas(self):
        self.assertEqual(self.codes([("en-tête", "default-src 'self'; script-src 'self' 'unsafe-inline'")]), ["script_unsafe_inline"])
        self.assertEqual(self.codes([("meta", "script-src 'self' 'unsafe-inline' https:; frame-ancestors 'none'")]),
                         ["frame_ancestors_meta", "script_source_large", "script_unsafe_inline"])                    # cassé
        self.assertEqual(self.codes([("meta", "script-src 'self' 'sha256-abc' 'unsafe-inline'; frame-ancestors 'none'")], xfo=True), [])
        self.assertEqual(self.codes([("en-tête", "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"),
                                     ("meta", "script-src 'self' 'sha256-x'; style-src 'self' 'sha256-y'")]), [])   # propre
        self.assertEqual(self.codes([("en-tête", "script-src * 'unsafe-eval'")]), ["script_source_large", "unsafe_eval"])
        self.assertEqual(self.codes([("en-tête", "default-src 'self' 'unsafe-inline'")]), ["script_unsafe_inline"])
        self.assertEqual(self.codes([("en-tête", "default-src 'self' 'unsafe-inline'; script-src 'self'")]), [])
        self.assertEqual(self.codes([("en-tête", "script-src 'nonce-r4nd' 'strict-dynamic' 'unsafe-inline' https:")]), [])

    def test_site_reel_a_plus_pas_de_faux_rouge(self):
        # Observatory A+ avec 'unsafe-inline' : nonce/hash → ignoré par les navigateurs modernes (info au plus), jamais ⚠️/❌
        for pol in ("default-src 'self'; script-src 'self' 'nonce-abc' 'unsafe-inline'; frame-ancestors 'none'",
                    "script-src 'self' 'sha256-abc=' 'unsafe-inline'", "script-src 'strict-dynamic' 'unsafe-inline' https:"):
            lignes = es.lignes_csp([("en-tête", pol)], False)
            self.assertEqual([l for l in lignes if "⚠️" in l or "❌" in l], [], pol)
        info = es.lignes_csp([("en-tête", "script-src 'self' 'nonce-abc' 'unsafe-inline'")], False)
        self.assertEqual(info, ["| CSP | script-src 'unsafe-inline' neutralisé (en-tête) | ℹ️ ignoré par les navigateurs modernes (nonce, hash ou strict-dynamic) |"])

    def test_style_unsafe_inline_basse(self):
        pols = [("en-tête", "default-src 'self'; script-src 'self' 'nonce-a'; style-src 'self' 'unsafe-inline'")]
        self.assertEqual(self.codes(pols), ["style_unsafe_inline"])
        self.assertEqual(es.lignes_csp(pols, False),
                         ["| CSP | style-src 'unsafe-inline' (en-tête) | ⚠️ risque limité : injection de styles, pas de script |"])
        self.assertEqual(self.codes([("en-tête", "style-src 'self' 'nonce-a' 'unsafe-inline'")]), [])
        self.assertEqual(self.codes([("en-tête", "default-src 'self' 'unsafe-inline'; style-src 'self'")]), ["script_unsafe_inline"])

    def test_politiques_cumulees(self):
        # une autre politique qui exige hash/nonce neutralise le 'unsafe-inline' de la première : pas de constat
        pols = [("en-tête", "script-src 'self' 'unsafe-inline'"), ("meta", "script-src 'self' 'sha256-x'")]
        self.assertEqual(self.codes(pols), [])
        self.assertEqual(self.codes([("en-tête", "script-src 'self' 'unsafe-inline'"), ("meta", "img-src 'self'")]), ["script_unsafe_inline"])
        self.assertEqual(self.codes([("en-tête", "script-src 'self' 'unsafe-eval'"), ("meta", "script-src 'self'")]), [])

    def test_meta_ne_porte_pas_certaines_directives(self):
        pols = [("meta", "script-src 'self' 'sha256-x'; frame-ancestors 'none'; report-uri /r; sandbox")]
        # sans en-tête de protection : constat (plafonné à ⚠️ = moyenne, jamais ❌)
        lignes = es.lignes_csp(pols, False)
        self.assertEqual(lignes[0], "| CSP (meta) | frame-ancestors ignoré dans une CSP <meta> | ⚠️ anti-clickjacking inopérant : envoyer "
                                    "X-Frame-Options ou frame-ancestors dans l'en-tête HTTP [moyenne] |")
        self.assertEqual(lignes[1], "| CSP (meta) | report-uri, sandbox ignorés dans une CSP <meta> | ℹ️ ces directives ne fonctionnent que dans l'en-tête HTTP |")
        self.assertFalse(any("❌" in l for l in lignes))
        # avec X-Frame-Options : plus de constat, une info seulement
        self.assertEqual(es.lignes_csp(pols, True),
                         ["| CSP (meta) | frame-ancestors, report-uri, sandbox ignorés dans une CSP <meta> | ℹ️ ces directives ne fonctionnent que dans l'en-tête HTTP |"])
        # frame-ancestors dans l'en-tête CSP : la meta redondante est sans conséquence
        self.assertEqual(self.codes([("en-tête", "frame-ancestors 'none'"), ("meta", "frame-ancestors 'none'")]), [])

    def test_extraction_en_tete_et_meta(self):
        pols, xfo = es.politiques("HTTP/1.1 200 OK\r\nContent-Security-Policy: frame-ancestors 'none'\r\nX-Frame-Options: DENY\r\n",
                                  '<head><meta http-equiv="Content-Security-Policy" content="script-src \'self\'"></head>')
        self.assertEqual((pols, xfo), ([("en-tête", "frame-ancestors 'none'"), ("meta", "script-src 'self'")], True))

    def test_extraction_meta_variantes(self):
        pols, _ = es.politiques("", '<meta content="script-src &#39;self&#39; &apos;unsafe-inline&apos;" HTTP-EQUIV=\'Content-Security-Policy\'>'
                                    '<meta name="description" content="Content-Security-Policy">')
        self.assertEqual(pols, [("meta", "script-src 'self' 'unsafe-inline'")])
        self.assertEqual(es.politiques("Content-Security-Policy-Report-Only: script-src *\r\n", "")[0], [])

    def test_lignes(self):
        self.assertEqual(es.lignes_csp([("meta", "script-src 'self' 'unsafe-inline'; frame-ancestors 'none'")], False), [
            "| CSP | script-src 'unsafe-inline' sans nonce/hash (meta) | ⚠️ protège peu contre le XSS [moyenne] |",
            "| CSP (meta) | frame-ancestors ignoré dans une CSP <meta> | ⚠️ anti-clickjacking inopérant : envoyer X-Frame-Options ou frame-ancestors dans l'en-tête HTTP [moyenne] |"])

    def test_marqueur_moyenne_sur_les_seules_lignes_moyennes(self):
        lignes = es.lignes_csp([("meta", "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; style-src 'unsafe-inline'; frame-ancestors 'none'")], False)
        marques = {c for c, g in es.GRAVITES.items() if g == "moyenne"}
        self.assertEqual(marques, {"script_unsafe_inline", "frame_ancestors_meta"})
        self.assertEqual([("[moyenne]" in l) for l in lignes], [True, False, False, False, True])

    def test_gravites(self):
        self.assertEqual(es.GRAVITES, {"script_unsafe_inline": "moyenne", "unsafe_eval": "basse", "script_source_large": "basse",
                                       "style_unsafe_inline": "basse", "frame_ancestors_meta": "moyenne"})


class TestCookies(unittest.TestCase):
    ENTETES = ("HTTP/1.1 200 OK\r\nSet-Cookie: session_cobaye=valeur-secrete; Path=/\r\n"
               "set-cookie: __Host-sid=abc; Path=/; Secure; HttpOnly; SameSite=Lax\r\n"
               "Set-Cookie: pref=1; Domain=ex.fr; Secure; SameSite=None\r\n"
               "Set-Cookie: __Host-mal=1; Path=/admin; Secure; SameSite=Lax; HttpOnly\r\n")

    def test_attributs_sans_valeur(self):
        lignes = es.lignes_cookies(self.ENTETES, https=True)
        self.assertEqual(lignes, [
            "| Cookie session_cobaye | Path=/ | ❌ sans Secure ; ❌ sans SameSite ; ❌ sans HttpOnly (cookie de session) |",
            "| Cookie __Host-sid | Path=/; Secure; HttpOnly; SameSite=Lax | ✅ |",
            "| Cookie pref | Domain=ex.fr; Secure; SameSite=None | ℹ️ sans HttpOnly (normal s'il est lu par JavaScript) |",
            "| Cookie __Host-mal | Path=/admin; Secure; SameSite=Lax; HttpOnly | ⚠️ préfixe __Host- non respecté (Path=/, Secure, sans Domain) |"])
        self.assertNotIn("valeur-secrete", "\n".join(lignes))

    def test_site_http_secure_non_exige(self):
        self.assertEqual(es.lignes_cookies("Set-Cookie: session_cobaye=x; Path=/\r\n", https=False),
                         ["| Cookie session_cobaye | Path=/ | ❌ sans SameSite ; ❌ sans HttpOnly (cookie de session) |"])

    def test_cookies_de_session_haute_et_autres_basse(self):
        def verdict(nom, attrs="Path=/", https=True):
            return es.lignes_cookies("Set-Cookie: {0}=v; {1}\r\n".format(nom, attrs), https)[0]
        for nom in ("sid", "connect.sid", "PHPSESSID", "JSESSIONID", "laravel_session", "auth", "authToken", "access_token", "__Secure-session"):
            self.assertIn("❌", verdict(nom), nom)
            self.assertNotIn("ℹ️", verdict(nom), nom)
        complet = "Path=/; Secure; HttpOnly; SameSite=Lax"
        for nom in ("sid", "session", "auth_token"):
            self.assertTrue(verdict(nom, complet).endswith("| ✅ |"), nom)
        # pas de faux « session » : noms voisins, jeton CSRF lu par JavaScript
        for nom in ("author_pref", "residence", "lang", "csrftoken", "XSRF-TOKEN"):
            self.assertNotIn("❌", verdict(nom), nom)
        self.assertEqual(verdict("lang", "Path=/; Secure"), "| Cookie lang | Path=/; Secure | ⚠️ sans SameSite ; ℹ️ sans HttpOnly (normal s'il est lu par JavaScript) |")

    def test_cookies_de_mesure_httponly_info(self):
        for nom in ("_ga", "_ga_ABC123", "_gid", "_fbp", "_hjSessionUser_1", "__utma", "_pk_id.1.abcd", "ajs_user_id"):
            ligne = es.lignes_cookies("Set-Cookie: {0}=v; Path=/; Secure; SameSite=Lax\r\n".format(nom), True)[0]
            self.assertTrue(ligne.endswith("| ℹ️ sans HttpOnly (normal : cookie de mesure lu par JavaScript) |"), ligne)
            self.assertNotIn("⚠️", ligne)
            self.assertNotIn("❌", ligne)

    def test_cookie_supprime_ignore_et_pas_de_barre_verticale(self):
        self.assertEqual(es.lignes_cookies("Set-Cookie: sid=; Max-Age=0; Path=/\r\nSet-Cookie: x=1; Expires=Thu, 01 Jan 1970 00:00:00 GMT\r\n", True), [])
        self.assertEqual(es.lignes_cookies("Set-Cookie: c=1; Path=/a|b; Secure; SameSite=Lax; HttpOnly\r\n", True),
                         ["| Cookie c | Path=/a/b; Secure; SameSite=Lax; HttpOnly | ✅ |"])

    def test_chaque_ligne_signalee_a_une_fiche(self):
        f = fiches.charger_fiches(SCRIPTS.parent / "references/fiches")
        lignes = es.lignes_cookies(self.ENTETES, https=True) + es.lignes_csp(
            [("meta", "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; style-src 'unsafe-inline'; frame-ancestors 'none'")], False)
        sigs = [{"source": "http", "cle": l} for l in lignes if "⚠️" in l or "❌" in l]
        self.assertEqual(len(sigs), 7)
        self.assertEqual(fiches.associer(sigs, f)[1], [])


if __name__ == "__main__":
    unittest.main()
