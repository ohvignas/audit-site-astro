import os
import pathlib
import signal
import subprocess
import tempfile
import time
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
ETAPES = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts/etapes.sh"


def bash(script, d, env=None):
    return subprocess.run(["bash", "-c", 'set -u; D="$1"; . "$2"; ' + script, "bash", d, str(ETAPES)],
                          capture_output=True, text=True, timeout=60, env=dict(os.environ, **(env or {})))


def vivant(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


class TestEtapes(unittest.TestCase):
    def test_delai_depasse_donne_124_vite(self):
        with tempfile.TemporaryDirectory() as d:
            t0 = time.monotonic()
            r = bash('avec_delai 1 sleep 30; echo "code=$?"', d)
            self.assertIn("code=124", r.stdout)
            self.assertLess(time.monotonic() - t0, 10)

    def test_code_de_la_commande_conserve(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIn("code=3", bash('avec_delai 5 sh -c "exit 3"; echo "code=$?"', d).stdout)
            self.assertIn("code=0", bash('avec_delai 5 true; echo "code=$?"', d).stdout)

    def test_delai_par_etape(self):
        with tempfile.TemporaryDirectory() as d:
            r = bash('delai_etape crawl; echo; delai_etape code; echo; delai_etape rapport-html; echo; delai_etape geo', d,
                     {"DELAI_CRAWL": "7", "DELAI_RAPPORT_HTML": "42"})
            self.assertEqual(r.stdout.split(), ["7", "900", "42", "1800"])
            r = bash("delai_etape crawl", d, {"MAX_PAGES": "500"})
            self.assertEqual(r.stdout.strip(), "3300")

    def test_extrait_du_journal_masque_les_cles(self):
        with tempfile.TemporaryDirectory() as d:
            lignes = [f"ligne {i}" for i in range(30)] + ["GET https://api.ex/v1?key=ABCDEF123456&q=1 → 403"]
            pathlib.Path(d, ".log-crawl.txt").write_text("\n".join(lignes) + "\n", encoding="utf-8")
            r = bash("extrait_journal crawl", d)
            fichier = pathlib.Path(d, ".erreurs-etapes.md").read_text(encoding="utf-8")
        self.assertIn("    │ GET https://api.ex/v1?key=…&q=1 → 403", r.stdout)
        self.assertNotIn("ABCDEF123456", r.stdout + fichier)
        self.assertIn("### crawl", fichier)
        self.assertIn("    ligne 29", fichier)
        self.assertNotIn("ligne 15\n", fichier)   # 15 dernières lignes seulement
        self.assertFalse(any(l.startswith("| ") for l in fichier.splitlines()))

    def test_ctrl_c_arrete_l_etape_et_ses_descendants(self):
        with tempfile.TemporaryDirectory() as d:
            script = ('set -u; D="$1"; . "$2"; trap interrompre_collecte INT TERM; '
                      'avec_delai 60 bash -c "sleep 60 & echo \\$! > $1/petit_enfant; wait"; echo "jamais"')
            p = subprocess.Popen(["bash", "-c", script, "bash", d, str(ETAPES)], stdout=subprocess.PIPE, text=True)
            fichier = pathlib.Path(d, "petit_enfant")
            for _ in range(100):
                if fichier.exists() and fichier.read_text().strip():
                    break
                time.sleep(0.1)
            os.kill(p.pid, signal.SIGINT)
            sortie, _ = p.communicate(timeout=30)
            pid = int(fichier.read_text())
            time.sleep(1)
        self.assertEqual(p.returncode, 130)
        self.assertIn("collecte interrompue", sortie)
        self.assertNotIn("jamais", sortie)
        self.assertFalse(vivant(pid), "le sleep lancé par l'étape doit être arrêté")

    # --- compléments (robustesse) ---------------------------------------------------------------------------------------

    def test_delai_depasse_arrete_aussi_les_descendants(self):
        with tempfile.TemporaryDirectory() as d:
            r = bash('avec_delai 1 bash -c "sleep 60 & echo \\$! > $D/petit_enfant; wait"; echo "code=$?"', d)
            pid = int(pathlib.Path(d, "petit_enfant").read_text())
            time.sleep(1)
            self.assertIn("code=124", r.stdout)
            self.assertFalse(vivant(pid), "le sleep lancé par l'étape doit être arrêté par le délai")
            self.assertEqual([f for f in os.listdir(d) if f.startswith(".delai-")], [], "pas de fichier témoin oublié")

    def test_delai_non_declenche_ne_laisse_aucun_gardien(self):
        """Le gardien du délai (et son « sleep ») est arrêté dès la fin de l'étape : aucun processus orphelin."""
        with tempfile.TemporaryDirectory() as d:
            r = bash('sleep() { command sleep "$@" & echo $! >> "$D/sleeps"; wait $!; }; '
                     'avec_delai 30 bash -c "command sleep 0.5"; echo "code=$?"', d)
            self.assertIn("code=0", r.stdout)
            time.sleep(0.2)   # le sleep orphelin d'un gardien non arrêté vivrait encore ~0,3 s
            sleeps = [int(x) for x in pathlib.Path(d, "sleeps").read_text().split()]
            self.assertTrue(sleeps, "le gardien aurait dû lancer au moins un sleep")
            for pid in sleeps:
                self.assertFalse(vivant(pid), "le sleep du gardien doit être arrêté avec lui")

    def test_delai_invalide_retombe_sur_le_defaut(self):
        with tempfile.TemporaryDirectory() as d:
            r = bash("delai_etape crawl; echo; delai_etape code", d,
                     {"DELAI_CRAWL": "abc", "DELAI_ETAPE": "12; echo pwned", "MAX_PAGES": "x"})
            self.assertEqual(r.stdout.split(), ["3300", "900"])
            self.assertNotIn("pwned", r.stdout)

    def test_delai_etape_global(self):
        with tempfile.TemporaryDirectory() as d:
            r = bash("delai_etape crawl; echo; delai_etape code; echo; delai_etape geo", d, {"DELAI_ETAPE": "60"})
            self.assertEqual(r.stdout.split(), ["60", "60", "60"])

    def test_extrait_sans_journal_ou_vide_n_ecrit_rien(self):
        with tempfile.TemporaryDirectory() as d:
            r = bash("extrait_journal absent; echo fin=$?", d)
            self.assertEqual(r.stdout.strip(), "fin=0")
            self.assertFalse(pathlib.Path(d, ".erreurs-etapes.md").exists())

    def test_extrait_masque_aussi_token_apikey_et_coupe_les_longues_lignes(self):
        with tempfile.TemporaryDirectory() as d:
            lignes = ["a?token=SECRETTOKEN1&b=2", "https://x/?apikey=SECRETAPIKEY2 fin", "https://x/?api_key=SECRETAPI_KEY3", "x" * 400]
            pathlib.Path(d, ".log-geo.txt").write_text("\n".join(lignes) + "\n", encoding="utf-8")
            r = bash("extrait_journal geo", d)
        sortie = r.stdout
        for secret in ("SECRETTOKEN1", "SECRETAPIKEY2", "SECRETAPI_KEY3"):
            self.assertNotIn(secret, sortie)
        self.assertIn("token=…&b=2", sortie)
        self.assertIn("apikey=… fin", sortie)
        self.assertLessEqual(max(len(l) for l in sortie.splitlines()), 4 + 240 + 2)  # préfixe « │ » + 240 caractères

    def test_avertissement_crawl_modules_en_erreur(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "crawl").mkdir()
            pathlib.Path(d, "crawl", "issues.json").write_text(
                '{"modules_en_erreur": {"label": "x", "severity": "haute", "count": 2, "examples": ["a11y_svg", "liens_externes"]}}',
                encoding="utf-8")
            r = bash("avertissement_etape crawl; echo \"code=$?\"", d)
            self.assertIn("a11y_svg", r.stdout)
            self.assertIn("liens_externes", r.stdout)
            self.assertIn("code=0", r.stdout)
            self.assertEqual(bash("avertissement_etape http", d).stdout.strip(), "")  # seule l'étape crawl est concernée

    def test_avertissement_crawl_sans_module_en_erreur(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "crawl").mkdir()
            pathlib.Path(d, "crawl", "issues.json").write_text('{"broken_images": {"count": 1}}', encoding="utf-8")
            self.assertEqual(bash("avertissement_etape crawl", d).stdout.strip(), "")
            pathlib.Path(d, "crawl", "issues.json").write_text("pas du json", encoding="utf-8")
            self.assertEqual(bash("avertissement_etape crawl", d).stdout.strip(), "")
        with tempfile.TemporaryDirectory() as d:  # pas d'issues.json du tout
            self.assertEqual(bash("avertissement_etape crawl", d).stdout.strip(), "")

    def test_avertissement_crawl_repli_sur_le_journal(self):
        """issues.json absent (crawl coupé par le délai avant l'écriture finale) : la ligne du journal suffit."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, ".log-crawl.txt").write_text("[ok] 3 pages\n⚠️ module a11y_noms désactivé : KeyError\n", encoding="utf-8")
            r = bash("avertissement_etape crawl", d)
            self.assertIn("a11y_noms", r.stdout)


if __name__ == "__main__":
    unittest.main()
