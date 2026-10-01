import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
import secrets_js  # noqa: E402

# Valeurs factices construites par concaténation : jamais telles quelles dans le dépôt (push protection GitHub)
OPENAI = "sk-" + "proj-" + "Ab3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3zA5bC7d"
STRIPE = "sk_" + "live_" + "COBAYE0FAUX0SECRET0NE0PAS0UTILISER"
AWS = "AKIA" + "Z7Q3K5L8M2N4P6R9"
GENERIQUE = "sk-" + "Qw8Er7Ty6Ui5Op4As3Df2Gh1Jk"
ANTHROPIC = "sk-" + "ant-" + "api03-" + "Zk3Vb8Nq1Lw7Rt5Yh2Mc9Xd4Pf6Sg0JaUe"
GITHUB = "gh" + "p_" + "q8Wz3Rt5Yh2Mc9Xd4Pf6Sg0JaUe1Bn7Kv2Lx"
SLACK = "xo" + "xb-" + "2951837462-8472619305-q8Wz3Rt5Yh2Mc9Xd"
GOOGLE = "AI" + "za" + "SyD3k9Lm2Qx7Vb5Nr8Tw1Yh4Jf6Cp0Zg3AB"
CLE_PRIVEE = "-----BEGIN " + "RSA PRIVATE KEY-----" + "\\nMIIEowIBAAKCAQEA" + "q8Wz3Rt5Yh2Mc9Xd4Pf6Sg0JaUe1Bn7Kv2Lx" + "q8Wz3Rt5Yh2Mc9Xd4Pf6Sg0JaUe1Bn7Kv2Lx"
CONVEX = "prod:happy-animal-123|" + "eyJ2MiI6IlpxOFhrMlB3TXY0VG45QmNk"
RESEND = "re_" + "Zq8Xk2Pw" + "_" + "Mv4Tn7Bc1Lr9Hs3Dg6Jf5Ya2"
HEX32 = "sk-" + "9f86d081884c7d659a2feaa0c55ad015"
HEX64 = "sk-or-v1-" + "3c9909afec25354d551dae21590bb26e38d53f2173b8d3dc3eee4c047e7ab1c1"


class TestDetection(unittest.TestCase):
    def noms(self, texte):
        return [nom for nom, _ in secrets_js.detecter(texte)]

    def test_formats_connus(self):
        self.assertEqual(self.noms("const k='" + OPENAI + "';"), ["OpenAI"])
        self.assertEqual(self.noms("x=" + STRIPE), ["Stripe"])
        self.assertEqual(self.noms("id:" + AWS + ";"), ["AWS"])
        self.assertEqual(self.noms("t='" + GENERIQUE + "'"), ["Clé sk- (format inconnu)"])

    def test_un_cas_positif_par_format(self):
        for nom, valeur in (("Anthropic", ANTHROPIC), ("GitHub", GITHUB), ("Slack", SLACK), ("Google API", GOOGLE),
                            ("Clé privée", CLE_PRIVEE), ("Convex (déploiement)", CONVEX), ("Resend", RESEND),
                            ("Stripe", "rk_" + "live_" + "q8Wz3Rt5Yh2Mc9Xd4Pf6Sg"), ("OpenAI", "sk-" + "svcacct-" + "q8Wz3Rt5Yh2Mc9Xd4Pf6Sg0J")):
            with self.subTest(format=nom):
                self.assertEqual(self.noms("var c='" + valeur + "';"), [nom])

    def test_formats_connus_apres_guillemet_echappement_ou_url(self):
        # clés dans du JSON, une chaîne minifiée ou une query string : le caractère qui précède peut être une lettre ou un chiffre
        for avant in ('"', "'", "=", ":", " ", "\n", "\\n", "\\t", "\\r", "%22", "%27", "%3D", "\\u0022", "\\x22", "&quot;", "Bearer "):
            for nom, valeur in (("OpenAI", OPENAI), ("Stripe", STRIPE), ("AWS", AWS), ("GitHub", GITHUB)):
                with self.subTest(avant=avant, format=nom):
                    self.assertEqual(self.noms("k" + avant + valeur), [nom])
        self.assertEqual(self.noms('{"cle":"' + OPENAI + '","autre":1}'), ["OpenAI"])
        self.assertEqual(self.noms("a\\n" + ANTHROPIC), ["Anthropic"])

    def test_un_format_connu_colle_a_un_mot_n_est_pas_une_cle(self):
        self.assertEqual(self.noms("task" + OPENAI), [])
        self.assertEqual(self.noms("MY_STRIPE_" + STRIPE), [])

    def test_cles_hexadecimales_minuscules(self):
        self.assertEqual(self.noms("t='" + HEX32 + "'"), ["Clé sk- (hexadécimale)"])
        self.assertEqual(self.noms('"' + HEX64 + '"'), ["Clé sk- (hexadécimale)"])
        for t in ("sk-" + "a" * 32,                       # entropie nulle
                  "sk-" + "deadbeef" * 4,                 # répétition
                  HEX32[:-1],                              # 31 caractères : trop court
                  HEX32 + "zz",                            # la suite n'est plus de l'hexadécimal
                  "task" + HEX32,                          # borne gauche
                  "sk-" + "a1b2" * 8,                     # entropie trop faible pour 32 caractères hexadécimaux
                  "sk-" + "1234567890" * 4):               # chiffres seuls
            self.assertEqual(self.noms(t), [], t)

    def test_hex_sans_confusion_avec_les_classes_tailwind(self):
        for t in ("mask-image-b-from-color-transparent mask-image-b-to-color-black-50%",
                  '.mask-image-b-from-pos{mask-position:var(--tw-mask-b-from-pos)}',
                  "sk-image-b-from-color-transparent-to-color-black", "ask-fade-in-up-2s-ease-out-forwards"):
            self.assertEqual(self.noms(t), [], t)

    def test_exemples_et_gabarits_ignores(self):
        for t in ("AKIA" + "IOSFODNN7" + "EXAMPLE",
                  "sk_" + "live_" + "x" * 24,
                  "gh" + "p_" + "x" * 36,
                  "sk-" + "proj-" + "xxxx" * 8,
                  "sk-" + "proj-" + "your_api_key_goes_here_please",
                  "xo" + "xb-your-token-here-please",
                  "sk_" + "live_" + "A" * 24,
                  '<input placeholder="-----BEGIN RSA PRIVATE KEY-----">',
                  "/-----BEGIN (RSA )?PRIVATE KEY-----([\\s\\S]+?)-----END/",
                  "console.log('Set CONVEX_DEPLOY_KEY in CI')",
                  "k='sk_live_<votre cle>'"):
            self.assertEqual(self.noms(t), [], t)

    def test_cle_privee_avec_corps_ou_variantes(self):
        for entete in ("PRIVATE KEY", "RSA PRIVATE KEY", "EC PRIVATE KEY", "OPENSSH PRIVATE KEY", "ENCRYPTED PRIVATE KEY"):
            with self.subTest(entete=entete):
                t = "-----BEGIN " + entete + "-----\n" + "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7" * 2
                self.assertEqual(self.noms(t), ["Clé privée"])

    def test_regle_borne_gauche_seule(self):
        # mixtes, aléatoires : seule la borne gauche les écarte (le préfixe fait partie d'un mot)
        for t in ("task-Zx9Yw8Vu7Ts6Rq5Po4Nm3Lk", "risk-Qw8Er7Ty6Ui5Op4As3Df2Gh1Jk", "x_sk-Zx9Yw8Vu7Ts6Rq5Po4Nm3Lk"):
            self.assertEqual(self.noms(t), [], t)
            self.assertEqual(self.noms(" " + t[t.index("sk-"):]), ["Clé sk- (format inconnu)"], t)

    def test_regle_entropie_seule(self):
        # casse mêlée, deux groupes de chiffres, pas de mots, pas kebab, pas en attribut class : seule l'entropie l'écarte
        faible = "sk-" + "aA1b" * 6
        self.assertEqual(self.noms("t='" + faible + "'"), [])
        self.assertLess(secrets_js.entropie("aA1b" * 6), 3.5)
        self.assertGreaterEqual(secrets_js.entropie(GENERIQUE[3:]), 3.5)

    def test_regle_kebab_seule(self):
        # jeton kebab-case (mots et nombres séparés par « - ») à casse mêlée, chiffres et entropie suffisants : seule la règle kebab l'écarte
        kebab = "sk-" + "Nav-Top-Bar-Box-Max-2024-Pad-Nox-Qu-7"
        self.assertGreaterEqual(secrets_js.entropie(kebab[3:]), 3.5)
        self.assertEqual(self.noms("t='" + kebab + "'"), [])

    def test_regle_attribut_class_seule(self):
        self.assertEqual(self.noms('<i class="a ' + GENERIQUE + '">'), [])
        self.assertEqual(self.noms("<i className='" + GENERIQUE + "'>"), [])
        self.assertEqual(self.noms("<i data-x='1'>" + " " + GENERIQUE), ["Clé sk- (format inconnu)"])

    def test_regle_mots_snake_case_seule(self):
        self.assertEqual(self.noms("x=re_" + "Zq8Xk2Pw_quote_attribute_Mv4Tn"), [])
        self.assertEqual(self.noms("x=" + RESEND), ["Resend"])  # une vraie clé n'a pas deux segments de mots minuscules

    def test_regle_mots_en_camel_case_seule(self):
        faux = "sk-" + "RenderMenuItem2Large3Active"
        self.assertGreaterEqual(secrets_js.entropie(faux[3:]), 3.5)
        self.assertEqual(self.noms("'" + faux + "'"), [])

    def test_regles_casse_et_chiffres(self):
        self.assertEqual(self.noms("t='sk-" + "QwErTyUiOpAsDfGhJkLzXcVb1'"), [])      # un seul groupe de chiffres
        self.assertEqual(self.noms("t='sk-" + "qwertyuiopasdfghjklzxcvbn12'"), [])  # pas de majuscule
        self.assertEqual(self.noms("t='sk-" + "QWERTYUIOPASDFGHJKLZXCVBN1X2'"), [])  # pas de minuscule

    def test_pas_de_chevauchement_ni_de_doublon_entre_formats(self):
        self.assertEqual(self.noms(OPENAI + "," + ANTHROPIC + "," + OPENAI), ["OpenAI", "Anthropic"])

    def test_formats_publics(self):
        self.assertEqual(secrets_js.PUBLICS, ("Google API",))
        self.assertTrue(secrets_js.est_public("Google API"))
        self.assertFalse(secrets_js.est_public("OpenAI"))

    def test_jeton_oauth_anthropic(self):
        oat = "sk-" + "ant-" + "oat01-" + "Zk3Vb8Nq1Lw7Rt5Yh2Mc9Xd4Pf6Sg0JaUe_-" * 2
        self.assertEqual(self.noms("t='" + oat + "'"), ["Anthropic"])

    def test_cles_aleatoires_longues_detectees_a_99_pour_cent(self):
        # N1 : la règle camelCase est proportionnelle ; une vraie clé n'est pas perdue parce qu'elle est longue
        import random
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        rnd = random.Random(20261001)
        for longueur in (48, 100, 120):
            with self.subTest(longueur=longueur):
                trouvees = sum(1 for _ in range(1000)
                               if self.noms("k='sk-" + "".join(rnd.choice(alphabet) for _ in range(longueur)) + "';"))
                self.assertGreaterEqual(trouvees, 990, "%d/1000 détectées" % trouvees)

    def test_identifiants_en_mots_toujours_rejetes_et_regression_tailwind(self):
        for t in ("sk-" + "RenderMenuItem2Large3Active", "re_" + "ValidateFieldArrayName2Values3Mode",
                  "sk-" + "RenderMenuItemActiveStateLarge2Wide3Panel",
                  "mask-image-b-from-color mask-image-b-from-pos mask-image-b-to-color",
                  "mask-image-b-from-color-transparent mask-image-b-from-pos-50%-to-color-black"):
            self.assertEqual(self.noms("'" + t + "'"), [], t)

    def test_cle_dans_un_attribut_html_non_cite(self):
        # N2 : HTML minifié sans guillemets, la clé est la dernière valeur avant « > »
        for t in ("<meta name=api content=" + OPENAI + ">", "<div data-k=" + STRIPE + ">", "<b x=" + AWS + "/>"):
            self.assertEqual(len(self.noms(t)), 1, t)
        for t in ("<" + OPENAI + ">", "<" + STRIPE + ">", "<sk-proj-YOUR_KEY>", "<sk_live_" + "x" * 24 + ">"):
            self.assertEqual(self.noms(t), [], t)

    def test_hexadecimale_dans_un_nom_de_fichier_ou_une_classe(self):
        h = HEX32[3:]
        for t in ("/assets/sk-" + h + ".css", "import('./sk-" + h + ".js')", "u='sk-" + h + ".png'", "https://x.fr/y/sk-" + h,
                  ".sk-" + h + "{color:red}", '<i class="a sk-' + h + '">', "sk-" + h + ".mjs", "sk-" + h + ".map"):
            self.assertEqual(self.noms(t), [], t)
        self.assertEqual(self.noms("t='" + HEX32 + "'."), ["Clé sk- (hexadécimale)"])  # un point final de phrase n'est pas une extension

    def test_faux_positifs_du_vrai_site_et_classes_css(self):
        for t in ('<div class="mask-image-b-from-color mask-image-b-to-color">',     # beta.illith.com, 2026-10-01
                  ".mask-image-b-from-pos{mask-position:var(--tw-mask-b-from-pos)}",
                  '"sk-tooltip-arrow-left-side-panel"',                                # classe kebab-case
                  "sk-" + "a" * 30,                                                    # entropie nulle
                  '<span class="badge sk-' + "Zx9Yw8Vu7Ts6Rq5Po4Nm3Lk" + '">',          # dans un attribut class
                  "x=re_" + "quote_attribute_values_now",                                # identifiant snake_case (pré-vol)
                  "'sk-" + "menuItemActiveStateLarge2024x'"):                            # camelCase daté (pré-vol)
            self.assertEqual(self.noms(t), [], t)

    def test_bundle_css_in_js_minifie_du_vrai_site(self):
        # Cas réel (beta.illith.com, 2026-10-01) : classes Tailwind dans un bundle minifié, aucune clé
        bundle = ('!function(){var a={m:"mask-image-b-from-color",p:"mask-image-b-from-pos",t:"mask-image-b-to-color"};'
                  'e.className=["relative","mask-image-b-from-color","mask-image-b-from-pos","mask-image-b-to-color"].join(" ");'
                  'var v=["mask-image-b-from-color-transparent","mask-image-b-from-pos-50%-to-color-black"];'
                  'document.head.insertAdjacentHTML("beforeend","<style>.mask-image-b-from-color{--tw-mask-b-from:var(--c)}'
                  '.mask-image-b-from-pos{--tw-mask-b-from-position:var(--p)}.mask-image-b-to-color{--tw-mask-b-to:var(--c)}</style>")}();'
                  'const t=`flex mask-image-b-from-color mask-image-b-from-pos mask-image-b-to-color`;')
        self.assertEqual(secrets_js.detecter(bundle), [])
        # la même page contenant en plus une vraie clé : seule celle-ci est signalée
        self.assertEqual(self.noms(bundle + "var k='" + OPENAI + "';"), ["OpenAI"])

    def test_jamais_la_valeur_complete_et_sans_doublon(self):
        self.assertEqual(secrets_js.formater(secrets_js.detecter(OPENAI + " " + OPENAI)), ["OpenAI : sk-proj-Ab3d…"])

    def test_ligne_de_commande(self):
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d, "bundle.js")
            f.write_text("a='" + STRIPE + "';", encoding="utf-8")
            r = subprocess.run([sys.executable, str(SCRIPTS / "secrets_js.py"), str(f)], capture_output=True, text=True, check=True)
        self.assertEqual(r.stdout, "Stripe : sk_live_COBA…\n")

    def lancer(self, contenu, *args, env=None):
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d, "bundle.js")
            f.write_text(contenu, encoding="utf-8")
            return subprocess.run([sys.executable, str(SCRIPTS / "secrets_js.py"), str(f), *args], capture_output=True, text=True,
                                  env=env)

    def test_ligne_de_commande_secrets_puis_cles_publiques(self):
        contenu = "a='" + STRIPE + "';b='" + GOOGLE + "';"
        self.assertEqual(self.lancer(contenu).stdout, "Stripe : sk_live_COBA…\n")
        self.assertEqual(self.lancer(contenu, "--publiques").stdout, "Google API : AIzaSyD3k9Lm…\n")
        self.assertEqual(self.lancer("rien").returncode, 0)

    def test_sortie_ascii_forcee_n_echoue_pas(self):
        env = dict(os.environ, PYTHONIOENCODING="ascii", LC_ALL="C", PYTHONUTF8="0")
        r = self.lancer("a='" + STRIPE + "';", env=env)
        self.assertEqual((r.returncode, r.stdout.encode("utf-8")), (0, "Stripe : sk_live_COBA…\n".encode("utf-8")), r.stderr)

    def test_fichier_illisible_sort_en_erreur(self):
        r = subprocess.run([sys.executable, str(SCRIPTS / "secrets_js.py"), "/introuvable/bundle.js"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")

    def test_au_plus_20_lignes(self):
        contenu = " ".join("sk_" + "live_" + "q8Wz3Rt5Yh2Mc9Xd4Pf6Sg%02d" % i for i in range(30))
        self.assertEqual(len(self.lancer(contenu).stdout.splitlines()), 20)


if __name__ == "__main__":
    unittest.main()
