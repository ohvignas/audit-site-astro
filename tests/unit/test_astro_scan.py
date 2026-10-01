import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCAN = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts/astro_scan.py"

XMLNS = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'


def scanner(fichiers):
    """Crée un mini-projet Astro 7 (fichiers = {chemin: contenu}), lance astro_scan et renvoie les constats."""
    with tempfile.TemporaryDirectory() as d:
        base = {"package.json": json.dumps({"dependencies": {"astro": "^7.3.0"}}), ".gitignore": ".env\n"}
        for chemin, contenu in dict(base, **fichiers).items():
            f = pathlib.Path(d, "projet", chemin)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(contenu, encoding="utf-8")
        subprocess.run([sys.executable, str(SCAN), str(pathlib.Path(d, "projet")), "--out", str(pathlib.Path(d, "out"))],
                       check=True, capture_output=True, timeout=120)
        return json.loads(pathlib.Path(d, "out", "code-scan.json").read_text(encoding="utf-8"))["constats"]


def textes(constats):
    return "\n".join(c["constat"] for c in constats)


class TestConfigSansCommentaires(unittest.TestCase):
    def test_globs_dans_des_chaines_ne_sont_pas_des_commentaires(self):  # revue finale I1
        cfg = ("export default defineConfig({\n  site: 'https://ex.fr',\n  output: 'server',\n"
               "  image: { remotePatterns: [{ protocol: 'https', hostname: 'cdn.ex.fr', pathname: '/images/**' }] },\n"
               "  security: { allowedDomains: [{ hostname: 'ex.fr', protocol: 'https' }] },\n"
               "  vite: { server: { watch: { ignored: ['**/tmp/**'] } } },\n});\n")
        self.assertNotIn("sans security.allowedDomains", textes(scanner({"astro.config.mjs": cfg})))

    def test_automate_de_commentaires(self):
        sys.path.insert(0, str(SCAN.parent))
        import astro_scan
        src = ("a = '/images/**'; /* vrai */ b = \"x // pas un commentaire\"; // fin\n"
               "c = `t /* ${d} */ \\` // ok`; e = 'it\\'s /*'; f = 1 /* multi\nligne */ + 2\n")
        out = astro_scan.sans_commentaires(src)
        for garde in ("'/images/**'", "\"x // pas un commentaire\"", "`t /* ${d} */ \\` // ok`", "'it\\'s /*'", "+ 2"):
            self.assertIn(garde, out)
        for retire in ("vrai", "fin", "multi"):
            self.assertNotIn(retire, out)
        self.assertEqual(out.count("\n"), src.count("\n"), "les numéros de ligne sont conservés")

    def test_allowed_domains_cite_en_commentaire_ne_compte_pas(self):  # C12
        cfg = ("export default defineConfig({\n  site: 'https://ex.fr',\n  output: 'server',\n"
               "  // pas de security.allowedDomains ici\n});\n")
        self.assertIn("sans security.allowedDomains", textes(scanner({"astro.config.mjs": cfg})))

    def test_allowed_domains_configure(self):
        cfg = ("export default defineConfig({ site: 'https://ex.fr', output: 'server',\n"
               "  security: { allowedDomains: [{ hostname: 'ex.fr', protocol: 'https' }] } });\n")
        self.assertNotIn("sans security.allowedDomains", textes(scanner({"astro.config.mjs": cfg})))


class TestSitemap(unittest.TestCase):
    CFG = "export default defineConfig({ site: 'https://ex.fr' });\n"

    def test_origine_de_la_requete_malgre_sitemaps_org(self):  # C10 + xmlns
        ep = ("export const GET = ({ request }) => {\n  const origin = new URL(request.url).origin; // http:// derrière un proxy\n"
              "  return new Response(`" + XMLNS + "<url><loc>${origin}/</loc></url></urlset>`);\n};\n")
        t = textes(scanner({"astro.config.mjs": self.CFG, "src/pages/sitemap.xml.ts": ep}))
        self.assertIn("depuis l'origine de la requête", t)
        self.assertNotIn("http:// en dur", t, "l'espace de noms XML et un commentaire ne sont pas des URL en dur")

    def test_mot_site_dans_le_texte_ne_vaut_pas_astro_site(self):  # revue finale M6
        ep = ("export const GET = ({ request }) => {\n  const origin = new URL(request.url).origin;\n"
              "  const titre = 'Plan du site';\n"
              "  return new Response(`" + XMLNS + "<url><loc>${origin}/plan-du-site</loc></url></urlset>`);\n};\n")
        self.assertIn("depuis l'origine de la requête", textes(scanner({"astro.config.mjs": self.CFG, "src/pages/sitemap.xml.ts": ep})))

    def test_sitemap_construit_avec_site(self):
        ep = ("export const GET = ({ site }) => new Response(`" + XMLNS +
              "<url><loc>${new URL('/', site).href}</loc></url></urlset>`);\n")
        t = textes(scanner({"astro.config.mjs": self.CFG, "src/pages/sitemap.xml.ts": ep}))
        self.assertNotIn("depuis l'origine de la requête", t)
        self.assertNotIn("http:// en dur", t)

    def test_vraie_url_http_en_dur(self):
        ep = "export const GET = () => new Response('<url><loc>http://ex.fr/</loc></url>');\n"
        self.assertIn("http:// en dur", textes(scanner({"astro.config.mjs": self.CFG, "src/pages/sitemap.xml.ts": ep})))


class TestSetHtml(unittest.TestCase):
    def test_json_ld_exclu_html_signale(self):  # C07 (faux positif du jumeau propre)
        page = ("---\nconst o = {};\nconst msg = Astro.url.searchParams.get('m');\n---\n"
                '<script type="application/ld+json" set:html={JSON.stringify(o)}></script>\n'
                "<div set:html={msg}></div>\n")
        c = [x for x in scanner({"src/pages/index.astro": page}) if "set:html" in x["constat"]]
        self.assertEqual(len(c), 1)
        self.assertEqual(len(c[0]["ou"]), 1)
        self.assertIn("src/pages/index.astro:6", c[0]["ou"][0])

    def test_json_ld_multiligne_prettier(self):  # revue finale M5
        page = ('---\nconst o = {};\n---\n<script\n  type="application/ld+json"\n  set:html={JSON.stringify(o)}\n></script>\n'
                '<div\n  set:html={o.html}\n></div>\n')
        c = [x for x in scanner({"src/pages/index.astro": page}) if "set:html" in x["constat"]]
        self.assertEqual(len(c), 1)
        self.assertEqual(len(c[0]["ou"]), 1)
        self.assertIn("src/pages/index.astro:9", c[0]["ou"][0])

    def test_json_ld_seul_rien_a_signaler(self):
        page = '---\nconst o = {};\n---\n<script type="application/ld+json" set:html={JSON.stringify(o)}></script>\n'
        self.assertNotIn("set:html", textes(scanner({"src/pages/index.astro": page})))


class TestAstro7(unittest.TestCase):
    CFG = "export default defineConfig({ site: 'https://ex.fr', output: 'server' });\n"
    SANS_INPUT = ("import { defineAction } from 'astro:actions';\nexport const server = {\n"
                  "  inscrire: defineAction({ accept: 'form', handler: async (d) => ({ ok: true }) }),\n"
                  "  noter: defineAction({\n    input: z.object({ note: z.number() }),\n    handler: async ({ note }) => note,\n  }),\n};\n")

    def test_action_sans_input(self):
        c = [x for x in scanner({"astro.config.mjs": self.CFG, "src/actions/index.ts": self.SANS_INPUT}) if "Action Astro" in x["constat"]]
        self.assertEqual([(x["constat"], x["ou"]) for x in c],
                         [("Action Astro sans validation input (1) : données reçues non validées", ["src/actions/index.ts:3"])])

    def test_montee_astro7(self):
        cfg = ("export default defineConfig({ site: 'https://ex.fr', session: { driver: 'fs' },\n"
               "  security: { actionBodySizeLimit: 10485760 },\n  experimental: { rustCompiler: true, cache: true } });\n")
        t = textes(scanner({"astro.config.mjs": cfg, "package.json": json.dumps({"dependencies": {"astro": "^6.2.0", "@astrojs/db": "^0.14.0"}}),
                            "src/fetch.ts": "export default {};\n"}))
        for attendu in ("Options experimental à retirer ou à sortir avant Astro 7 : cache, rustCompiler",
                        "@astrojs/db n'est plus pris en charge par Astro 7", "src/fetch.ts est un fichier réservé à partir d'Astro 7",
                        "session configurée sans ttl", "security.actionBodySizeLimit relevé à 10485760 octets"):
            self.assertIn(attendu, t)

    def test_projet_a_jour_sans_constat(self):
        cfg = "export default defineConfig({ site: 'https://ex.fr', session: { driver: 'fs', ttl: 3600 } });\n"
        t = textes(scanner({"astro.config.mjs": cfg, "src/actions/index.ts": self.SANS_INPUT.replace("accept: 'form', ", "accept: 'form', input: schema, ")}))
        self.assertNotIn("Action Astro", t)
        self.assertNotIn("session configurée", t)
        self.assertNotIn("experimental", t)

    # --- précisions de la tâche 25 (vérifiées contre docs.astro.build, lu le 2026-10-01)
    def _actions(self, source):
        c = [x for x in scanner({"astro.config.mjs": self.CFG, "src/actions/index.ts": source}) if "Action Astro" in x["constat"]]
        return [(x["constat"].split(" :")[0], x["ou"]) for x in c]

    def test_action_commentee_ou_chaine_ignorees(self):
        src = ("// ancienne : defineAction({ handler: async (d) => d })\n/* defineAction({ handler: async (d) => d }) */\n"
               "const doc = 'defineAction({ handler: async (d) => d })';\n")
        self.assertEqual(self._actions(src), [])

    def test_input_cherche_au_premier_niveau_seulement(self):
        src = ("export const server = {\n  a: defineAction({\n    handler: async (d) => {\n      const x = { input: 1 };\n      return x;\n    },\n  }),\n"
               "  b: defineAction({ input, handler: async (d) => d }),\n"
               "  c: defineAction({ ...base, handler: async (d) => d }),\n"
               "  d: defineAction({ accept: 'form', input: z.object({ nom: z.string() }), handler: async (d) => ({ ok: 1 }) }),\n};\n")
        self.assertEqual(self._actions(src), [("Action Astro sans validation input (1)", ["src/actions/index.ts:2"])])

    def test_action_sans_donnees_en_entree_pas_signalee(self):
        src = ("export const server = {\n  heure: defineAction({ handler: async () => new Date().toISOString() }),\n"
               "  ping: defineAction({ handler() { return 1; } }),\n  lire: defineAction({ handler: async (_, ctx) => ctx.locals.user }),\n};\n")
        self.assertEqual(self._actions(src), [("Action Astro sans validation input (1)", ["src/actions/index.ts:4"])])

    def test_actions_dans_plusieurs_fichiers_et_accolades_dans_les_chaines(self):
        a = "export const a = defineAction({ handler: async (d) => '}' + d });\n"
        b = "export const b = defineAction({\n  handler: async (d) => `${d}}`,\n  input: z.string(),\n});\n"
        c = [x for x in scanner({"astro.config.mjs": self.CFG, "src/actions/a.ts": a, "src/actions/b.ts": b}) if "Action Astro" in x["constat"]]
        self.assertEqual([x["ou"] for x in c], [["src/actions/a.ts:1"]])

    def test_flags_experimental_avec_blocs_imbriques(self):
        cfg = ("export default defineConfig({ site: 'https://ex.fr',\n  experimental: {\n    cache: { provider: memoryCache() },\n"
               "    svgOptimizer: svgoOptimizer({ plugins: [{ name: 'x' }] }),\n    logger: true,\n    queuedRendering: { enabled: true },\n"
               "    advancedRouting: true,\n  },\n  routeRules: {} });\n")
        t = textes(scanner({"astro.config.mjs": cfg}))
        self.assertIn("Options experimental à retirer ou à sortir avant Astro 7 : advancedRouting, cache, logger, queuedRendering", t)
        self.assertNotIn("svgOptimizer", t)

    def test_experimental_sans_flag_retire(self):
        cfg = "export default defineConfig({ site: 'https://ex.fr', experimental: { svgOptimizer: svgoOptimizer() }, cache: { provider: p() } });\n"
        self.assertNotIn("Options experimental", textes(scanner({"astro.config.mjs": cfg})))

    def test_fetch_ts_et_db_selon_la_version(self):
        t = textes(scanner({"astro.config.mjs": self.CFG, "src/fetch.ts": "export default {};\n"}))  # Astro 7 installé : réservé, pas un conseil
        self.assertNotIn("src/fetch.ts", t)

    def test_session_false_ou_avec_ttl(self):
        for session in ("false", "{ driver: sessionDrivers.fs(), ttl: 600 }"):
            cfg = f"export default defineConfig({{ site: 'https://ex.fr', session: {session} }});\n"
            self.assertNotIn("session configurée", textes(scanner({"astro.config.mjs": cfg})), session)

    def test_ttl_dun_autre_bloc_ne_compte_pas(self):
        cfg = ("export default defineConfig({ site: 'https://ex.fr', session: { driver: 'fs' },\n"
               "  vite: { server: { ttl: 5 } } });\n")
        self.assertIn("session configurée sans ttl", textes(scanner({"astro.config.mjs": cfg})))

    def test_limite_de_corps_par_defaut_ou_inferieure_pas_signalee(self):
        for n in ("1048576", "512_000"):
            cfg = f"export default defineConfig({{ site: 'https://ex.fr', security: {{ actionBodySizeLimit: {n} }} }});\n"
            self.assertNotIn("actionBodySizeLimit", textes(scanner({"astro.config.mjs": cfg})), n)

    def test_aucune_adresse_ni_secret_dans_les_constats_de_code(self):
        src = "export const a = defineAction({ handler: async (d) => fetch('https://api.ex.fr/x?token=SECRET123') });\n"
        c = scanner({"astro.config.mjs": self.CFG, "src/actions/index.ts": src})
        self.assertNotIn("SECRET123", json.dumps(c))


class TestMonorepo(unittest.TestCase):
    """M6 (revue de T8) : en workspace, node_modules et le lockfile sont à la racine du workspace, pas dans apps/web."""

    def _projet(self, d, fichiers):
        for chemin, contenu in fichiers.items():
            f = pathlib.Path(d, chemin)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(contenu, encoding="utf-8")
        sys.path.insert(0, str(SCAN.parent))
        return pathlib.Path(d, "apps/web")

    def _scan(self, fichiers, marqueur="pnpm-workspace.yaml"):
        base = {"apps/web/package.json": json.dumps({"dependencies": {"astro": "catalog:"}}),
                "apps/web/astro.config.mjs": "export default defineConfig({ site: 'https://ex.fr' });\n",
                "apps/web/.gitignore": ".env\n", "apps/web/src/fetch.ts": "export default {};\n"}
        if marqueur:
            base[marqueur] = "packages:\n  - apps/*\n" if marqueur.endswith(".yaml") else ""
        with tempfile.TemporaryDirectory() as d:
            web = self._projet(d, dict(base, **fichiers))
            subprocess.run([sys.executable, str(SCAN), str(web), "--out", str(pathlib.Path(d, "out"))], check=True,
                           capture_output=True, timeout=120, env=dict(os.environ, ASTRO_SCAN_HORS_LIGNE="1"))
            return json.loads(pathlib.Path(d, "out/code-scan.json").read_text(encoding="utf-8"))

    def test_node_modules_et_lockfile_du_workspace(self):
        rap = self._scan({"node_modules/astro/package.json": json.dumps({"name": "astro", "version": "6.4.1"}),
                          "pnpm-lock.yaml": "lockfileVersion: '9.0'\n"})
        t = textes(rap["constats"])
        self.assertEqual(rap["astro_version"]["installee"], "6.4.1")
        self.assertIn("src/fetch.ts est un fichier réservé", t)  # version trouvée dans le node_modules remonté
        self.assertNotIn("Aucun lockfile", t)
        self.assertEqual(rap["package"]["lockfile"], ["pnpm-lock.yaml"])

    def test_workspace_npm_champ_workspaces(self):
        rap = self._scan({"node_modules/astro/package.json": json.dumps({"version": "6.0.0"}), "package-lock.json": "{}",
                          "package.json": json.dumps({"workspaces": ["apps/*"]})}, marqueur=None)
        self.assertEqual(rap["astro_version"]["installee"], "6.0.0")
        self.assertNotIn("Aucun lockfile", textes(rap["constats"]))

    def test_node_modules_du_projet_prioritaire(self):
        rap = self._scan({"node_modules/astro/package.json": json.dumps({"version": "6.0.0"}),
                          "apps/web/node_modules/astro/package.json": json.dumps({"version": "7.1.0"}), "pnpm-lock.yaml": ""})
        self.assertEqual(rap["astro_version"]["installee"], "7.1.0")
        self.assertNotIn("src/fetch.ts", textes(rap["constats"]))

    def test_sans_workspace_on_ne_remonte_pas(self):  # aucun marqueur : le node_modules d'un dossier parent n'est pas le nôtre
        rap = self._scan({"node_modules/astro/package.json": json.dumps({"version": "6.4.1"}), "pnpm-lock.yaml": ""}, marqueur=None)
        self.assertEqual(rap["astro_version"]["installee"], "0.0.0")
        self.assertIn("Aucun lockfile", textes(rap["constats"]))

    def test_la_remontee_s_arrete_a_la_racine_du_workspace(self):
        with tempfile.TemporaryDirectory() as d:
            for chemin, contenu in {"node_modules/astro/package.json": json.dumps({"version": "5.0.0"}), "pnpm-lock.yaml": "",
                                    "mono/pnpm-workspace.yaml": "packages: []\n", "mono/apps/web/package.json": "{}"}.items():
                f = pathlib.Path(d, chemin)
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(contenu, encoding="utf-8")
            sys.path.insert(0, str(SCAN.parent))
            import astro_scan
            web = pathlib.Path(d, "mono/apps/web")
            self.assertEqual(astro_scan.dossiers_workspace(web), [web, web.parent, web.parent.parent])
            self.assertEqual(astro_scan.racine_workspace(web), pathlib.Path(d, "mono"))
            self.assertEqual(astro_scan.racine_workspace(pathlib.Path(d)), pathlib.Path(d))
            self.assertIsNone(astro_scan.astro_version(web))

    def test_marqueur_git_fichier_ou_dossier(self):
        with tempfile.TemporaryDirectory() as d:
            for sous in ("a", "b"):
                (pathlib.Path(d, sous, "apps/web")).mkdir(parents=True)
            pathlib.Path(d, "a/.git").mkdir()
            pathlib.Path(d, "b/.git").write_text("gitdir: ../x\n")  # worktree : .git est un fichier
            sys.path.insert(0, str(SCAN.parent))
            import astro_scan
            self.assertEqual(astro_scan.racine_workspace(pathlib.Path(d, "a/apps/web")), pathlib.Path(d, "a"))
            self.assertEqual(astro_scan.racine_workspace(pathlib.Path(d, "b/apps/web")), pathlib.Path(d, "b"))


class TestEntreesAutonomes(unittest.TestCase):
    """N2 (revue de T8) : chaque scan_* appelé seul repart d'un budget neuf, sans hériter d'un scan interrompu."""

    def setUp(self):
        sys.path.insert(0, str(SCAN.parent))
        import astro_scan
        self.m = astro_scan
        self.budget = astro_scan.BUDGET_S
        self.d = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.d.name, "p")
        for chemin, contenu in {"package.json": json.dumps({"dependencies": {"astro": "^7.3.0"}}), ".gitignore": ".env\n",
                                "astro.config.mjs": "export default defineConfig({ site: 'https://ex.fr' });\n",
                                "src/pages/index.astro": "<h1>Ok</h1>\n"}.items():
            f = self.root / chemin
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(contenu, encoding="utf-8")
        os.environ["ASTRO_SCAN_HORS_LIGNE"] = "1"

    def tearDown(self):
        self.m.BUDGET_S = self.budget
        self.m.reinitialiser()
        self.d.cleanup()

    def test_interruption_non_heritee_par_un_appel_autonome(self):
        self.m.reinitialiser(self.root)
        self.m.BUDGET_S = -1  # épuisé dès le premier test
        self.m.scan_astro_features(self.root, {})
        self.assertTrue(self.m.INTERROMPU)
        self.m.BUDGET_S = self.budget
        self.m.findings.clear()
        for etape in (lambda: self.m.scan_astro_features(self.root, {}), lambda: self.m.scan_src(self.root, {}),
                      lambda: self.m.scan_astro7(self.root, {})):
            self.m.INTERROMPU = True  # état périmé laissé par un appel précédent
            etape()
            self.assertFalse(self.m.INTERROMPU)
        self.assertIn("Aucune Content-Security-Policy", "\n".join(f["constat"] for f in self.m.findings))
        self.assertEqual(self.m.NON_LUS, set())

    def test_dans_main_le_budget_reste_partage(self):
        r = subprocess.run([sys.executable, str(SCAN), str(self.root), "--out", str(pathlib.Path(self.d.name, "o"))],
                           capture_output=True, text=True, timeout=120, env=dict(os.environ, ASTRO_SCAN_BUDGET_S="-1"))
        rap = json.loads(pathlib.Path(self.d.name, "o/code-scan.json").read_text(encoding="utf-8"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("scan_interrompu", rap)  # le budget est global à un main()


if __name__ == "__main__":
    unittest.main()


class TestLignesLongues(unittest.TestCase):
    """Rapport utilisateur v2.0.0 : un script tiers après le 160e caractère d'une ligne faisait planter le scan
    (« 'NoneType' object has no attribute 'group' »), l'extrait tronqué ne contenant plus le motif."""

    def test_script_tiers_apres_160_caracteres(self):
        ligne = "<div>" + "x" * 300 + '<script async src="https://www.googletagmanager.com/gtag/js?id=G-X"></script></div>'
        constats = scanner({"src/pages/index.astro": "---\n---\n" + ligne + "\n"})
        tiers = [c for c in constats if any("googletagmanager" in o for o in c["ou"])]
        self.assertTrue(tiers, textes(constats))

    def test_hydratation_comptee_sur_toute_la_ligne(self):
        ligne = "<A client:load/>" + " " * 200 + "<B client:load/>" + " " * 200 + "<C client:load/>"
        sys.path.insert(0, str(SCAN.parent))
        import astro_scan
        lignes = astro_scan.lignes_completes(ligne, astro_scan.RX["client"])
        self.assertEqual(len(astro_scan.RX["client"].findall(lignes[0][1])), 3)

    def test_extrait_contient_le_motif(self):
        sys.path.insert(0, str(SCAN.parent))
        import astro_scan, re
        texte = "a" * 500 + "set:html={x}" + "b" * 500
        (_, extrait), = astro_scan.lines_matching(texte, re.compile(r"set:html"))
        self.assertIn("set:html", extrait)
        self.assertLessEqual(len(extrait), 160)
