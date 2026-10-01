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


# Étape qui résiste : l'enfant et le petit-enfant (et son sleep) ignorent TERM, comme un Chrome bloqué.
RECALCITRANT = """trap '' TERM INT
( trap '' TERM INT; sleep 60 & echo $! > "$1/petit"; wait ) &
echo $! > "$1/enfant"
wait
"""


# Variante : la tête de l'étape meurt au TERM, seuls les descendants résistent (ils deviennent orphelins, introuvables par ppid ensuite).
TETE_MEURT = """( trap '' TERM INT; sleep 60 & echo $! > "$1/petit"; wait ) &
echo $! > "$1/enfant"
wait
"""


def attendre_pids(d, noms=("enfant", "petit")):
    for _ in range(100):
        if all(pathlib.Path(d, n).exists() and pathlib.Path(d, n).read_text().strip() for n in noms):
            return [int(pathlib.Path(d, n).read_text()) for n in noms]
        time.sleep(0.1)
    raise AssertionError("l'étape récalcitrante n'a pas démarré")


class TestArbreTue(unittest.TestCase):
    """I1 : un descendant qui ignore TERM (Chrome bloqué, lancé dans sa propre session) ne doit survivre ni à un délai ni à Ctrl-C."""

    def test_delai_depasse_tue_les_descendants_qui_ignorent_term(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "recalcitrant.sh").write_text(RECALCITRANT, encoding="utf-8")
            t0 = time.monotonic()
            r = bash('avec_delai 2 bash "$D/recalcitrant.sh" "$D"; echo "code=$?"', d)
            duree = time.monotonic() - t0
            pids = attendre_pids(d)
            time.sleep(0.5)
            self.assertIn("code=124", r.stdout)
            self.assertLess(duree, 20)
            for pid in pids:
                self.assertFalse(vivant(pid), f"le processus {pid} (ignore TERM) doit être tué par KILL")
            self.assertEqual([f for f in os.listdir(d) if f.startswith(".delai-")], [])

    def test_ctrl_c_tue_les_descendants_qui_ignorent_term(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "recalcitrant.sh").write_text(RECALCITRANT, encoding="utf-8")
            script = ('set -u; D="$1"; . "$2"; trap interrompre_collecte INT TERM; '
                      'avec_delai 120 bash "$D/recalcitrant.sh" "$D"; echo "jamais"')
            p = subprocess.Popen(["bash", "-c", script, "bash", d, str(ETAPES)], stdout=subprocess.PIPE, text=True)
            pids = attendre_pids(d)
            os.kill(p.pid, signal.SIGINT)
            sortie, _ = p.communicate(timeout=30)
            time.sleep(0.5)
            self.assertEqual(p.returncode, 130)
            self.assertIn("collecte interrompue", sortie)
            for pid in pids:
                self.assertFalse(vivant(pid), f"le processus {pid} (ignore TERM) doit être tué par KILL au Ctrl-C")

    def test_ctrl_c_pendant_la_grace_d_un_delai_n_abandonne_aucun_processus(self):
        """N1 : le délai vient de se dépasser (TERM envoyé, KILL dans ≤ 5 s) ; un Ctrl-C à ce moment ne doit pas tuer le gardien avant son KILL.
        La tête de l'étape meurt au TERM : ses descendants récalcitrants sont orphelins, seule la liste prise par le gardien les retrouve."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "recalcitrant.sh").write_text(TETE_MEURT, encoding="utf-8")
            script = ('set -u; D="$1"; . "$2"; trap interrompre_collecte INT TERM; '
                      'avec_delai 1 bash "$D/recalcitrant.sh" "$D"; echo "jamais"')
            sortie_f = pathlib.Path(d, "sortie.txt")
            pids = []
            try:
                with open(sortie_f, "w", encoding="utf-8") as out:
                    p = subprocess.Popen(["bash", "-c", script, "bash", d, str(ETAPES)], stdout=out)
                pids = attendre_pids(d)
                for _ in range(100):   # témoin du délai dépassé : la grâce de 5 s commence
                    if any(f.startswith(".delai-") for f in os.listdir(d)):
                        break
                    time.sleep(0.1)
                else:
                    self.fail("le délai n'a pas été dépassé")
                time.sleep(1)
                for pid in pids:
                    self.assertTrue(vivant(pid), "pendant la grâce, le descendant résiste encore à TERM")
                os.kill(p.pid, signal.SIGINT)
                p.wait(timeout=30)
                time.sleep(0.5)
                self.assertEqual(p.returncode, 130)
                sortie = sortie_f.read_text(encoding="utf-8")
                self.assertNotIn("jamais", sortie)
                self.assertIn("collecte interrompue", sortie)
                for pid in pids:
                    self.assertFalse(vivant(pid), f"le processus {pid} doit être tué malgré le Ctrl-C pendant la grâce")
            finally:
                for pid in pids:   # ne rien laisser tourner si le test échoue
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_arbre_complet_gele_puis_tue(self):
        """tuer_arbre liste tout l'arbre avant de tuer : un enfant qui se relance en boucle ne laisse pas de petit-enfant."""
        with tempfile.TemporaryDirectory() as d:
            r = bash('bash -c "while :; do sleep 30 & echo \\$! >> $D/pids; wait; done" & P=$!; sleep 1; '
                     'tuer_arbre $P 2; sleep 0.3; kill -0 $P 2>/dev/null && echo "vivant" || echo "mort"', d)
            pids = [int(x) for x in pathlib.Path(d, "pids").read_text().split()]
            time.sleep(0.3)
            self.assertIn("mort", r.stdout)
            for pid in pids:
                self.assertFalse(vivant(pid))


class TestExtraitUtf8EtMasquage(unittest.TestCase):
    def _extrait(self, lignes_ou_octets, nom="crawl"):
        with tempfile.TemporaryDirectory() as d:
            donnees = lignes_ou_octets if isinstance(lignes_ou_octets, bytes) else lignes_ou_octets.encode("utf-8")
            pathlib.Path(d, f".log-{nom}.txt").write_bytes(donnees)
            r = subprocess.run(["bash", "-c", 'set -u; D="$1"; . "$2"; extrait_journal ' + nom, "bash", d, str(ETAPES)],
                               capture_output=True, timeout=60)
            fichier = pathlib.Path(d, ".erreurs-etapes.md").read_bytes()
        # décodage strict : une coupe au milieu d'un caractère lèverait UnicodeDecodeError
        return r.stdout.decode("utf-8"), fichier.decode("utf-8")

    def test_coupe_par_caracteres_jamais_au_milieu_d_un_caractere(self):
        for debut in range(0, 6):  # la frontière des 240 caractères tombe sur é, — ou ⚠️ selon le décalage
            ligne = "x" * debut + ("é—⚠️" * 100)
            ecran, fichier = self._extrait(ligne + "\n")
            lue = next(l for l in ecran.splitlines() if l.startswith("    │ "))[len("    │ "):]
            self.assertEqual(len(lue), 240)
            self.assertIn("    " + lue, fichier)

    def test_octets_invalides_dans_le_journal_donnent_un_utf8_valide(self):
        ecran, fichier = self._extrait(b"avant \xff\xfe apres \xc3\n" + "é".encode() * 300 + b"\n")
        self.assertIn("avant", ecran)
        self.assertIn("### crawl", fichier)

    def test_masquage_elargi(self):
        secrets = {
            "PSI_API_KEY=SECRETPSI111 fin": "PSI_API_KEY=… fin",
            "API_KEY=SECRETAPI222&x=1": "API_KEY=…&x=1",
            "Key=SECRETKEY333": "Key=…",
            "TOKEN=SECRETTOK444": "TOKEN=…",
            "Authorization: Bearer SECRETBEAR555.abc": "Authorization: Bearer …",
            "authorization: bearer SECRETBEAR666": "authorization: bearer …",
            '{"password": "SECRETPASS777", "x": 1}': '{"password": "…", "x": 1}',
            '{"secret":"SECRETSEC888"}': '{"secret":"…"}',
            '{"token": "SECRETJSON999"}': '{"token": "…"}',
            '{"apiKey": "SECRETCAMEL000"}': '{"apiKey": "…"}',
            "password=SECRETPW1111": "password=…",
            "client_secret=SECRETCS2222&a=b": "client_secret=…&a=b",
            "token: SECRETCOLON3333": "token: …",
            "https://user:SECRETURL4444@hote.fr/": "https://user:…@hote.fr/",
        }
        ecran, fichier = self._extrait("\n".join(secrets) + "\n")
        for entree, attendu in secrets.items():
            self.assertIn(attendu, ecran, entree)
            self.assertIn(attendu, fichier, entree)
        for brut in ("SECRETPSI111", "SECRETAPI222", "SECRETKEY333", "SECRETTOK444", "SECRETBEAR555", "SECRETBEAR666", "SECRETPASS777",
                     "SECRETSEC888", "SECRETJSON999", "SECRETCAMEL000", "SECRETPW1111", "SECRETCS2222", "SECRETCOLON3333", "SECRETURL4444"):
            self.assertNotIn(brut, ecran + fichier)

    def test_extrait_calcule_une_seule_fois(self):
        """Écran et fichier viennent du même calcul : mêmes lignes."""
        ecran, fichier = self._extrait("\n".join(f"ligne {i}" for i in range(40)) + "\n")
        a = [l[len("    │ "):] for l in ecran.splitlines() if l.startswith("    │ ")]
        b = [l[4:] for l in fichier.splitlines() if l.startswith("    ligne")]
        self.assertEqual(a, b)
        self.assertEqual(len(a), 15)


class TestDelaisLimites(unittest.TestCase):
    def test_max_pages_avec_zero_initial_est_decimal(self):
        with tempfile.TemporaryDirectory() as d:
            for v, attendu in (("08", "1824"), ("09", "1827"), ("010", "1830")):
                self.assertEqual(bash("delai_etape crawl", d, {"MAX_PAGES": v}).stdout.strip(), attendu, v)

    def test_delai_nul_signifie_sans_limite(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(bash("delai_etape code", d, {"DELAI_CODE": "0"}).stdout.strip(), "0")
            t0 = time.monotonic()
            r = bash('avec_delai 0 bash -c "sleep 2"; echo "code=$?"', d)
            self.assertIn("code=0", r.stdout)
            self.assertGreaterEqual(time.monotonic() - t0, 1.5)  # pas tuée aussitôt

    def test_delai_invalide_dans_avec_delai_ne_tue_pas_l_etape(self):
        with tempfile.TemporaryDirectory() as d:
            r = bash('avec_delai "" bash -c "sleep 1"; echo "code=$?"; avec_delai 08 true; echo "code=$?"', d)
            self.assertEqual(r.stdout.split(), ["code=0", "code=0"])

    def test_delai_lighthouse_suit_runs_et_pages(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(bash("delai_etape lighthouse", d).stdout.strip(), "1800")
            self.assertEqual(bash("delai_etape lighthouse", d, {"RUNS": "3", "LH_PAGES": "5"}).stdout.strip(), "4200")
            self.assertEqual(bash("delai_etape lighthouse", d, {"RUNS": "x", "LH_PAGES": "y"}).stdout.strip(), "1800")
            self.assertEqual(bash("delai_etape lighthouse", d, {"RUNS": "3", "DELAI_LIGHTHOUSE": "99"}).stdout.strip(), "99")


if __name__ == "__main__":
    unittest.main()
