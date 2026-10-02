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

    def test_virgule_separe_les_politiques_d_un_meme_en_tete(self):
        def pols(v):
            return es.politiques("Content-Security-Policy: " + v + "\r\n", "")[0]
        self.assertEqual(pols("script-src 'self', script-src 'unsafe-inline'"),
                         [("en-tête", "script-src 'self'"), ("en-tête", "script-src 'unsafe-inline'")])
        # P1 bloque l'inline : le 'unsafe-inline' de P2 est sans effet (les politiques se cumulent)
        self.assertEqual(self.codes(pols("script-src 'self', script-src 'unsafe-inline'")), [])
        self.assertEqual(self.codes(pols("default-src 'self' 'unsafe-inline', script-src 'self' 'nonce-x'")), [])
        self.assertEqual(self.codes(pols("script-src 'unsafe-inline' 'self', script-src 'self' 'sha256-x'")), [])
        self.assertEqual(self.codes(pols("script-src 'unsafe-inline' 'self', img-src 'self'")), ["script_unsafe_inline"])
        # cumul avec la meta
        self.assertEqual(self.codes(pols("script-src 'unsafe-inline', img-src 'self'")
                                    + [("meta", "script-src 'self' 'sha256-x'")]), [])
        self.assertEqual(es.politiques("", '<head><meta http-equiv="Content-Security-Policy" content="img-src a, script-src b"></head>')[0],
                         [("meta", "img-src a"), ("meta", "script-src b")])

    def test_meta_lue_dans_le_head_seulement(self):
        def meta(page):
            return es.politiques("", page)[0]
        m = '<meta http-equiv="Content-Security-Policy" content="script-src \'unsafe-inline\'">'
        voulu = [("meta", "script-src 'unsafe-inline'")]
        self.assertEqual(meta("<html><head>" + m + "</head><body></body></html>"), voulu)
        self.assertEqual(meta("<html><head><META HTTP-EQUIV='content-SECURITY-policy' CONTENT=\"script-src 'unsafe-inline'\"></head></html>"), voulu)
        self.assertEqual(meta("<head><title>t</title>" + m), voulu)  # head non refermé
        # jamais une politique : commentaire, script, template, noscript, body, après </head>, Report-Only, nom voisin
        for nom, page in (
                ("commentaire", "<head><!-- " + m + " --></head>"),
                ("script", "<head><script>var s = '" + m.replace("'", "\\'") + "';</script></head>"),
                ("script avec chevrons", "<head><script>document.write('" + m.replace("'", "\\'") + "')</script></head>"),
                ("style", "<head><style>/* " + m + " */</style></head>"),
                ("template", "<head><template>" + m + "</template></head>"),
                ("noscript", "<head><noscript>" + m + "</noscript></head>"),
                ("body", "<head></head><body>" + m + "</body>"),
                ("après </head>", "<html><head></head>" + m + "<body></body></html>"),
                ("body sans head", "<html><body><div>" + m + "</div></body></html>"),
                ("report-only", '<head><meta http-equiv="Content-Security-Policy-Report-Only" content="script-src *"></head>'),
                ("nom voisin", '<head><meta http-equiv="Content-Security-Policy-X" content="script-src *"></head>'),
                ("autre http-equiv", '<head><meta http-equiv="refresh" content="Content-Security-Policy"></head>'),
                ("name seulement", '<head><meta name="Content-Security-Policy" content="script-src *"></head>')):
            self.assertEqual(meta(page), [], nom)

    def test_head_borne_et_pas_quadratique(self):
        import time
        t = time.time()
        self.assertEqual(es.politiques("", "<html><head>" + "<meta " * 20000)[0], [])
        self.assertEqual(es.politiques("", "<head><title>t</title>" + "<meta " * 20000 + "</head>")[0], [])
        self.assertLess(time.time() - t, 1.0)
        m = '<meta http-equiv="Content-Security-Policy" content="script-src \'self\'">'
        self.assertEqual(es.politiques("", "<head>" + m + "</head><body>" + "<p>" * 300000)[0], [("meta", "script-src 'self'")])
        # au-delà de 200 000 caractères : hors du head lu
        self.assertEqual(es.politiques("", "<head>" + " " * 200000 + m)[0], [])
        self.assertEqual(es.politiques("", "<HEAD>" + m + "</HEAD >")[0], [("meta", "script-src 'self'")])

    def test_meta_commentaire_ne_donne_pas_de_meta_seulement(self):
        self.assertEqual(es.politiques("", "<head><!-- <meta http-equiv=\"Content-Security-Policy\" content=\"script-src *\"> --></head>")[0], [])

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
            "| Cookie pref | Domain=…; Secure; SameSite=None | ℹ️ sans HttpOnly (normal s'il est lu par JavaScript) |",
            "| Cookie __Host-mal | Path=…; Secure; SameSite=Lax; HttpOnly | ⚠️ préfixe __Host- non respecté (Path=/, Secure, sans Domain) |"])
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

    def test_aucune_valeur_ecrite_nulle_part(self):
        secret = "SECRETXYZ"
        entetes = "".join("Set-Cookie: " + c + "\r\n" for c in (
            "SECRETXYZ; Path=/",                                                  # pas de « = » : le jeton est une valeur sans nom
            "=SECRETXYZ; Path=/",                                                 # nom vide
            "a=SECRETXYZ; Path=/reset/SECRETXYZ?t=SECRETXYZ; Secure",             # chemin avec jeton
            "b=1; Secure; SameSite=SECRETXYZ; Domain=SECRETXYZ/.fr; HttpOnly",   # SameSite et Domain invalides
            "c=1; Expires=Wed, 21 Oct 2026 07:28:00 GMT, autre=SECRETXYZ; Path=/",  # deux cookies fusionnés
            "d=1; SECRETXYZ=SECRETXYZ; Priority=SECRETXYZ; X-Inconnu; Secure",    # attributs inconnus
            "SECRETXYZ:nom=1; Secure",                                            # nom hors jeton RFC 6265 (« : »)
            "e=1; Max-Age=SECRETXYZ; Partitioned; Secure; SameSite=Lax; HttpOnly"))
        for https in (True, False):
            sortie = "\n".join(es.lignes_cookies(entetes, https))
            self.assertNotIn(secret, sortie)
            self.assertNotIn("SECRET", sortie)
        lignes = es.lignes_cookies(entetes, True)
        self.assertTrue(lignes[0].startswith("| Cookie sans nom | Path=/ |"), lignes[0])
        self.assertTrue(any("| Cookie e | Max-Age; Partitioned; Secure; SameSite=Lax; HttpOnly | ✅ |" == l for l in lignes), lignes)
        self.assertTrue(any(l.startswith("| Cookie c | Expires; Path=/ |") for l in lignes), lignes)

    def test_attributs_en_liste_blanche(self):
        self.assertEqual(es.lignes_cookies("Set-Cookie: k=v; path=/a/b; DOMAIN=ex.fr; samesite=strict; SECURE; httponly; Expires=Thu, 01 Jan 2099 00:00:00 GMT\r\n", True),
                         ["| Cookie k | Path=…; Domain=…; SameSite=Strict; Secure; HttpOnly; Expires | ✅ |"])
        self.assertEqual(es.lignes_cookies("Set-Cookie: k=v; Path=/; Domain=.Ex.fr; Secure; HttpOnly; SameSite=Lax\r\n", True, "ex.fr"),
                         ["| Cookie k | Path=/; Domain=ex.fr; Secure; HttpOnly; SameSite=Lax | ✅ |"])
        self.assertIn("⚠️ sans SameSite", es.lignes_cookies("Set-Cookie: k=v; SameSite=Foo; Secure\r\n", True)[0])

    def test_path_et_domain_masques(self):
        entetes = "".join("Set-Cookie: " + c + "\r\n" for c in (
            "a=1; Path=/SECRETPATH; Secure; SameSite=Lax; HttpOnly",
            "b=1; Path=/reset/SECRETTOKEN123456; Domain=SECRETDOMAIN.example.com; Secure; SameSite=Lax; HttpOnly",
            "c=1; Path=/; Domain=autre.example.com; Secure; SameSite=Lax; HttpOnly"))
        for hote in ("", "www.exemple.fr"):
            sortie = "\n".join(es.lignes_cookies(entetes, True, hote))
            self.assertNotIn("SECRET", sortie)
            self.assertNotIn("autre.example.com", sortie)
        self.assertEqual(es.lignes_cookies(entetes, True, "www.exemple.fr"), [
            "| Cookie a | Path=…; Secure; SameSite=Lax; HttpOnly | ✅ |",
            "| Cookie b | Path=…; Domain=…; Secure; SameSite=Lax; HttpOnly | ✅ |",
            "| Cookie c | Path=/; Domain=…; Secure; SameSite=Lax; HttpOnly | ✅ |"])

    def test_noms_de_cookie_jeton_rfc_6265(self):
        for nom in ("a%20b", "$id", "x!y", "it's", "tab#1", "n&m", "a*b", "p+q", "c^d", "e`f", "g~h", "_ga", "A-b.c_9"):
            ligne = es.lignes_cookies("Set-Cookie: {0}=v; Path=/; Secure; SameSite=Lax; HttpOnly\r\n".format(nom), True)[0]
            self.assertTrue(ligne.startswith("| Cookie {0} |".format(nom)) and ligne.endswith("| ✅ |"), ligne)
        self.assertEqual(es.lignes_cookies("Set-Cookie: a|b=v; Secure; SameSite=Lax; HttpOnly\r\n", True), ["| Cookie a/b | Secure; SameSite=Lax; HttpOnly | ✅ |"])
        for nom in ("a:b", "x[0]", "a b", "a(b)", "a/b"):
            ligne = es.lignes_cookies("Set-Cookie: {0}=v; Path=/; Secure; SameSite=Lax; HttpOnly\r\n".format(nom), True)[0]
            self.assertTrue(ligne.startswith("| Cookie sans nom |") and "⚠️" in ligne, ligne)

    def test_prefixes_insensibles_a_la_casse_sans_doublon(self):
        self.assertIn("préfixe __Host-", es.lignes_cookies("Set-Cookie: __host-x=1; Path=/x; Secure; HttpOnly; SameSite=Lax\r\n", True)[0])
        ligne = es.lignes_cookies("Set-Cookie: __Secure-x=1; SameSite=None; HttpOnly\r\n", True)[0]
        self.assertEqual(ligne.count("sans Secure"), 1, ligne)

    def test_cookie_supprime_ignore_et_pas_de_barre_verticale(self):
        self.assertEqual(es.lignes_cookies("Set-Cookie: sid=; Max-Age=0; Path=/\r\nSet-Cookie: x=1; Expires=Thu, 01 Jan 1970 00:00:00 GMT\r\n", True), [])
        self.assertEqual(es.lignes_cookies("Set-Cookie: c=1; Path=/a|b; Secure; SameSite=Lax; HttpOnly\r\n", True),
                         ["| Cookie c | Path=…; Secure; SameSite=Lax; HttpOnly | ✅ |"])

    def test_chaque_ligne_signalee_a_une_fiche(self):
        f = fiches.charger_fiches(SCRIPTS.parent / "references/fiches")
        lignes = es.lignes_cookies(self.ENTETES, https=True) + es.lignes_csp(
            [("meta", "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; style-src 'unsafe-inline'; frame-ancestors 'none'")], False)
        sigs = [{"source": "http", "cle": l} for l in lignes if "⚠️" in l or "❌" in l]
        self.assertEqual(len(sigs), 7)
        self.assertEqual(fiches.associer(sigs, f)[1], [])


if __name__ == "__main__":
    unittest.main()
