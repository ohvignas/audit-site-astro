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


class TestDetection(unittest.TestCase):
    def noms(self, texte):
        return [nom for nom, _ in secrets_js.detecter(texte)]

    def test_formats_connus(self):
        self.assertEqual(self.noms("const k='" + OPENAI + "';"), ["OpenAI"])
        self.assertEqual(self.noms("x=" + STRIPE), ["Stripe"])
        self.assertEqual(self.noms("id:" + AWS + ";"), ["AWS"])
        self.assertEqual(self.noms("t='" + GENERIQUE + "'"), ["Clé sk- (format inconnu)"])

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


if __name__ == "__main__":
    unittest.main()
