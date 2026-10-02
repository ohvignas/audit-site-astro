import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

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
        self.assertNotIn("Options experimental à retirer", t)

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

    def test_action_sans_donnees_en_entree_pas_signalee(self):  # I3 : déconnexion, « moi », rafraîchir : le handler n'utilise pas d'entrée
        src = ("export const server = {\n  heure: defineAction({ handler: async () => new Date().toISOString() }),\n"
               "  ping: defineAction({ handler() { return 1; } }),\n  lire: defineAction({ handler: async (_, ctx) => ctx.locals.user }),\n"
               "  quitter: defineAction({ handler: async (_input, context) => { context.session?.destroy(); } }),\n"
               "  moi: defineAction({ accept: 'json', handler: async (_: unknown, { locals }) => locals.user }),\n"
               "  fleche: defineAction({ handler: async _ => 1 }),\n"
               "  noter: defineAction({ handler: async (d) => d }),\n"
               "  chercher: defineAction({ handler: async ({ id }, ctx) => id }),\n};\n")
        self.assertEqual(self._actions(src), [("Action Astro sans validation input (2)", ["src/actions/index.ts:8", "src/actions/index.ts:9"])])

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

    # --- revue de T25 : I2 (autonomie), minors M1-M5, M7
    def _projet_tmp(self, fichiers):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        racine = pathlib.Path(d.name, "p")
        for chemin, contenu in dict({"package.json": json.dumps({"dependencies": {"astro": "^7.3.0"}})}, **fichiers).items():
            f = racine / chemin
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(contenu, encoding="utf-8")
        sys.path.insert(0, str(SCAN.parent))
        import astro_scan
        os.environ["ASTRO_SCAN_HORS_LIGNE"] = "1"
        astro_scan.reinitialiser(racine)
        self.addCleanup(astro_scan.reinitialiser)
        return astro_scan, racine

    def test_scan_astro7_seul_lit_package_json(self):  # I2
        for fichiers in ({"package.json": json.dumps({"dependencies": {"astro": "^7.3.0", "@astrojs/db": "^0.14"}})},
                         {"package.json": json.dumps({"devDependencies": {"@astrojs/db": "^0.14"}})}):
            m, racine = self._projet_tmp(dict({"astro.config.mjs": self.CFG}, **fichiers))
            m.scan_astro7(racine, {})
            c = [f for f in m.findings if "@astrojs/db" in f["constat"]]
            self.assertEqual([f["ou"] for f in c], [["package.json"]])

    def test_db_dans_la_configuration_seulement(self):
        m, racine = self._projet_tmp({"astro.config.mjs": "import db from '@astrojs/db';\nexport default defineConfig({ integrations: [db()] });\n"})
        m.scan_astro7(racine, {})
        self.assertEqual([f["ou"] for f in m.findings if "@astrojs/db" in f["constat"]], [["astro.config.mjs"]])

    def test_tous_les_scan_s_appellent_seuls_avec_un_rapport_vide(self):
        m, racine = self._projet_tmp({"astro.config.mjs": self.CFG, "src/pages/index.astro": "<h1>Ok</h1>\n"})
        for etape in (m.scan_package, m.scan_astro_config, m.scan_src, m.scan_astro_features, m.scan_astro7, m.scan_convex, m.scan_repo):
            etape(racine, {})
        m.scan_dist(racine, None, {})

    def test_backtick_dans_une_regex_ne_masque_pas_la_suite(self):  # M1
        src = ("const re = /`/g;\nconst s = txt.replace(/['\"]/g, '');\nconst t = x.replace(/{/g, '');\n"
               "export const server = {\n  a: defineAction({ handler: async (d) => d }),\n};\n")
        self.assertEqual(self._actions(src), [("Action Astro sans validation input (1)", ["src/actions/index.ts:5"])])
        cfg = "const re = /`/g;\nexport default defineConfig({ site: 'https://ex.fr', experimental: { cache: true } });\n"
        self.assertIn("Options experimental", textes(scanner({"astro.config.mjs": cfg})))

    def test_division_et_regex_ne_se_confondent_pas(self):
        src = ("const moitie = total / 2; const part = a / b / c;\nconst ok = /a\\/b[/]c/.test(x);\n"
               "export const server = {\n  a: defineAction({ input: z.number(), handler: async (d) => d / 2 }),\n};\n")
        self.assertEqual(self._actions(src), [])

    def test_cles_entre_guillemets(self):  # M2
        cfg = ("export default defineConfig({ site: 'https://ex.fr',\n  'experimental': { 'rustCompiler': true, \"cache\": {} },\n"
               "  'session': { 'driver': 'fs', 'ttl': 60 } });\n")
        t = textes(scanner({"astro.config.mjs": cfg}))
        self.assertIn("Options experimental à retirer ou à sortir avant Astro 7 : cache, rustCompiler", t)
        self.assertNotIn("session configurée", t)
        src = "export const server = {\n  a: defineAction({ 'input': z.string(), handler: async (d) => d }),\n};\n"
        self.assertEqual(self._actions(src), [])

    def test_experimental_et_session_au_premier_niveau_seulement(self):  # M4
        cfg = ("export default defineConfig({ site: 'https://ex.fr',\n  integrations: [foo({ experimental: { cache: true, logger: 1 } }),"
               " auth({ session: { strategy: 'jwt' } })],\n  vite: { experimental: { cache: 1 }, session: { a: 1 } },\n"
               "  adapter: node({ mode: 'standalone', session: { x: 1 } }) });\n")
        t = textes(scanner({"astro.config.mjs": cfg}))
        self.assertNotIn("Options experimental", t)
        self.assertNotIn("session configurée", t)

    def test_config_dans_une_variable_ou_export_default_objet(self):
        for cfg in ("const config = { site: 'https://ex.fr', experimental: { cache: true } };\nexport default config;\n",
                    "export default { site: 'https://ex.fr', experimental: { cache: true } };\n",
                    "export default defineConfig({ site: 'https://ex.fr', experimental: { cache: true } }) satisfies X;\n"):
            self.assertIn("Options experimental à retirer ou à sortir avant Astro 7 : cache", textes(scanner({"astro.config.mjs": cfg})), cfg)

    def test_session_spread_ou_ttl_raccourci_sans_constat(self):  # M3
        for session in ("{ ...sessionOptions }", "{ driver: 'fs', ttl }"):
            cfg = f"export default defineConfig({{ site: 'https://ex.fr', session: {session} }});\n"
            self.assertNotIn("session configurée", textes(scanner({"astro.config.mjs": cfg})), session)

    def test_flag_en_raccourci(self):
        cfg = "export default defineConfig({ site: 'https://ex.fr', experimental: { cache, svgOptimizer: x } });\n"
        self.assertIn("Options experimental à retirer ou à sortir avant Astro 7 : cache", textes(scanner({"astro.config.mjs": cfg})))

    def test_gravite_selon_la_version_installee(self):  # M5 : rien avant Astro 6, anticipation en 6, constat en 7
        cfg = "export default defineConfig({ site: 'https://ex.fr', experimental: { cache: true } });\n"
        db = {"dependencies": {"@astrojs/db": "^0.14"}}

        def constats(version):
            pk = json.dumps({"dependencies": dict(db["dependencies"], astro=version)})
            c = scanner({"astro.config.mjs": cfg, "package.json": pk, "src/fetch.ts": "export default {};\n"})
            return {x["constat"].split(" :")[0].split(" est ")[0].split(" n'est")[0]: x["severite"] for x in c
                    if any(k in x["constat"] for k in ("Options experimental", "@astrojs/db", "src/fetch.ts"))}
        self.assertEqual(constats("^5.4.0"), {})
        self.assertEqual(constats("^6.2.0"), {"Options experimental à retirer ou à sortir avant Astro 7": "basse",
                                              "@astrojs/db": "basse", "src/fetch.ts": "basse"})
        self.assertEqual(constats("^7.3.0"), {"Options experimental à retirer ou à sortir avant Astro 7": "moyenne",
                                              "@astrojs/db": "moyenne"})

    def test_limite_calculee_par_produit(self):  # M7
        for expr, attendu in (("10 * 1024 * 1024", "10485760"), ("10_485_760", "10485760")):
            cfg = f"export default defineConfig({{ site: 'https://ex.fr', security: {{ actionBodySizeLimit: {expr} }} }});\n"
            self.assertIn(f"security.actionBodySizeLimit relevé à {attendu} octets", textes(scanner({"astro.config.mjs": cfg})), expr)

    def test_budget_epuise_dans_les_actions(self):
        m, racine = self._projet_tmp({"astro.config.mjs": self.CFG, "src/actions/a.ts": "export const a = defineAction({ handler: async (d) => d });\n"})
        budget = m.BUDGET_S
        self.addCleanup(setattr, m, "BUDGET_S", budget)
        m.BUDGET_S = -1
        m.scan_astro7(racine, {})
        self.assertTrue(m.INTERROMPU)
        self.assertEqual(m.NON_LUS, {"src/actions/a.ts"})
        self.assertEqual([f for f in m.findings if "Action Astro" in f["constat"]], [])


class TestMonorepo(unittest.TestCase):
    """M6 (revue de T8) : en workspace, node_modules et le lockfile sont à la racine du workspace, pas dans apps/web.
    Hermétique : HOME factice = dossier temporaire, la remontée ne dépasse jamais HOME (donc jamais le TMPDIR de la machine)."""

    def _ecrire(self, d, fichiers):
        for chemin, contenu in fichiers.items():
            f = pathlib.Path(d, chemin)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(contenu, encoding="utf-8")

    def _scan(self, fichiers, marqueur="pnpm-workspace.yaml", racine_projet="ws/apps/web", prefixe="ws/"):
        base = {"ws/apps/web/package.json": json.dumps({"dependencies": {"astro": "catalog:"}}),
                "ws/apps/web/astro.config.mjs": "export default defineConfig({ site: 'https://ex.fr' });\n",
                "ws/apps/web/.gitignore": ".env\n", "ws/apps/web/src/fetch.ts": "export default {};\n"}
        if marqueur:
            base["ws/" + marqueur] = "packages:\n  - apps/*\n" if marqueur.endswith(".yaml") else ""
        with tempfile.TemporaryDirectory() as d:
            self._ecrire(d, dict(base, **{prefixe + k: v for k, v in fichiers.items()}))
            subprocess.run([sys.executable, str(SCAN), str(pathlib.Path(d, racine_projet)), "--out", str(pathlib.Path(d, "out"))],
                           check=True, capture_output=True, timeout=120,
                           env=dict(os.environ, ASTRO_SCAN_HORS_LIGNE="1", HOME=d))
            return json.loads(pathlib.Path(d, "out/code-scan.json").read_text(encoding="utf-8"))

    def _module(self):
        sys.path.insert(0, str(SCAN.parent))
        import astro_scan
        return astro_scan

    def test_node_modules_et_lockfile_du_workspace(self):
        rap = self._scan({"node_modules/astro/package.json": json.dumps({"name": "astro", "version": "6.4.1"}),
                          "pnpm-lock.yaml": "lockfileVersion: '9.0'\n"})
        t = textes(rap["constats"])
        self.assertEqual(rap["astro_version"]["installee"], "6.4.1")
        self.assertIn("src/fetch.ts est un fichier réservé", t)  # version trouvée dans le node_modules remonté
        self.assertNotIn("Aucun lockfile", t)
        self.assertEqual(rap["package"]["lockfile"], ["pnpm-lock.yaml"])
        self.assertEqual(rap["package"]["lockfile_dans"], os.path.join("..", ".."))

    def test_workspace_npm_champ_workspaces(self):  # dans un dépôt (.git au-dessus) : le package.json avec "workspaces" est lu
        rap = self._scan({"packages/mono/node_modules/astro/package.json": json.dumps({"version": "6.0.0"}),
                          "packages/mono/package-lock.json": "{}", "packages/mono/package.json": json.dumps({"workspaces": ["apps/*"]}),
                          "packages/mono/apps/web/package.json": json.dumps({"dependencies": {"astro": "catalog:"}}),
                          "packages/mono/apps/web/astro.config.mjs": "export default defineConfig({ site: 'https://ex.fr' });\n"},
                         marqueur=".git", racine_projet="ws/packages/mono/apps/web")
        self.assertEqual(rap["astro_version"]["installee"], "6.0.0")
        self.assertNotIn("Aucun lockfile", textes(rap["constats"]))

    def test_workspace_npm_sans_git_pas_lu(self):  # I1 : sans dépôt connu, aucun package.json d'ancêtre n'est lu
        rap = self._scan({"node_modules/astro/package.json": json.dumps({"version": "6.0.0"}), "package-lock.json": "{}",
                          "package.json": json.dumps({"workspaces": ["apps/*"]})}, marqueur=None)
        self.assertEqual(rap["astro_version"]["installee"], "0.0.0")
        self.assertIn("Aucun lockfile", textes(rap["constats"]))

    def test_workspace_borne_par_git(self):
        rap = self._scan({"node_modules/astro/package.json": json.dumps({"version": "6.0.0"}), "package-lock.json": "{}"},
                         marqueur=".git")
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
        self.assertNotIn("lockfile_dans", rap["package"])

    def test_la_remontee_s_arrete_a_la_racine_du_workspace(self):
        astro_scan = self._module()
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"HOME": d}):
            self._ecrire(d, {"o/node_modules/astro/package.json": json.dumps({"version": "5.0.0"}), "o/pnpm-lock.yaml": "",
                             "o/mono/pnpm-workspace.yaml": "packages: []\n", "o/mono/apps/web/package.json": "{}"})
            web = pathlib.Path(d, "o/mono/apps/web")
            self.assertEqual(astro_scan.dossiers_workspace(web), [web, web.parent, web.parent.parent])
            self.assertEqual(astro_scan.racine_workspace(web), pathlib.Path(d, "o/mono"))
            self.assertIsNone(astro_scan.astro_version(web))
            self.assertEqual(astro_scan.racine_workspace(pathlib.Path(d, "o")), pathlib.Path(d, "o"))

    def test_marqueur_git_fichier_ou_dossier(self):
        astro_scan = self._module()
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"HOME": d}):
            for sous in ("a", "b"):
                (pathlib.Path(d, sous, "apps/web")).mkdir(parents=True)
            pathlib.Path(d, "a/.git").mkdir()
            pathlib.Path(d, "b/.git").write_text("gitdir: ../x\n")  # worktree : .git est un fichier
            self.assertEqual(astro_scan.racine_workspace(pathlib.Path(d, "a/apps/web")), pathlib.Path(d, "a"))
            self.assertEqual(astro_scan.racine_workspace(pathlib.Path(d, "b/apps/web")), pathlib.Path(d, "b"))

    # --- I1 (revue T25) : plafond du répertoire personnel, jamais de lecture hors du dépôt
    def _home_parasite(self, d, avec_git=True):
        self._ecrire(d, {"home/package-lock.json": "{}", "home/node_modules/astro/package.json": json.dumps({"version": "4.0.0"}),
                         "home/package.json": json.dumps({"workspaces": ["*/*"]}),
                         "home/Sites/monsite/package.json": json.dumps({"dependencies": {"astro": "^6.0.0"}}),
                         "home/Sites/monsite/astro.config.mjs": "export default defineConfig({ site: 'https://ex.fr' });\n",
                         "home/Sites/monsite/.gitignore": ".env\n"})
        if avec_git:
            pathlib.Path(d, "home/.git").mkdir()
        return pathlib.Path(d, "home/Sites/monsite")

    def test_home_avec_git_et_lockfile_egares_ne_sont_pas_le_workspace(self):
        astro_scan = self._module()
        with tempfile.TemporaryDirectory() as d:
            projet = self._home_parasite(d)
            with mock.patch.dict(os.environ, {"HOME": str(pathlib.Path(d, "home"))}):
                self.assertEqual(astro_scan.racine_workspace(projet), projet)
                self.assertEqual(astro_scan.dossiers_workspace(projet), [projet])
                self.assertEqual(astro_scan.astro_version(projet), (6, 0, 0))
            r = subprocess.run([sys.executable, str(SCAN), str(projet), "--out", str(pathlib.Path(d, "out"))], check=True,
                               capture_output=True, timeout=120,
                               env=dict(os.environ, ASTRO_SCAN_HORS_LIGNE="1", HOME=str(pathlib.Path(d, "home"))))
            rap = json.loads(pathlib.Path(d, "out/code-scan.json").read_text(encoding="utf-8"))
            self.assertEqual(rap["astro_version"]["installee"], "6.0.0")
            self.assertIn("Aucun lockfile", textes(rap["constats"]))
            self.assertNotIn("lockfile_dans", rap["package"])

    def test_aucune_lecture_hors_du_depot(self):
        astro_scan = self._module()
        lus = []
        lire = pathlib.Path.read_text

        def espion(self_, *a, **k):
            lus.append(str(self_))
            return lire(self_, *a, **k)

        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"HOME": str(pathlib.Path(d, "home"))}):
            # (a) aucun .git au-dessus : seul le package.json du projet est lu, pas ceux des ancêtres (jusqu'à HOME exclu)
            projet = self._home_parasite(d, avec_git=False)
            self._ecrire(d, {"home/Sites/package.json": json.dumps({"workspaces": ["*"]})})
            with mock.patch.object(pathlib.Path, "read_text", espion):
                self.assertEqual(astro_scan.racine_workspace(projet), projet)
            self.assertEqual([l for l in lus if not l.startswith(str(projet))], [])
            # (b) dépôt trouvé : on s'arrête à son premier .git, rien au-dessus n'est lu
            self._ecrire(d, {"home/Sites/depot/apps/web/package.json": "{}", "home/Sites/depot/package.json": "{}"})
            pathlib.Path(d, "home/Sites/depot/.git").mkdir()
            lus.clear()
            with mock.patch.object(pathlib.Path, "read_text", espion):
                self.assertEqual(astro_scan.racine_workspace(pathlib.Path(d, "home/Sites/depot/apps/web")),
                                 pathlib.Path(d, "home/Sites/depot"))
            self.assertTrue(all(l.startswith(str(pathlib.Path(d, "home/Sites/depot"))) for l in lus), lus)

    def test_pnpm_workspace_sans_git_reste_detecte(self):  # archive dézippée d'un monorepo : existence seule, aucune lecture
        astro_scan = self._module()
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"HOME": d}):
            self._ecrire(d, {"mono/pnpm-workspace.yaml": "packages: []\n", "mono/apps/web/package.json": "{}"})
            self.assertEqual(astro_scan.racine_workspace(pathlib.Path(d, "mono/apps/web")), pathlib.Path(d, "mono"))

    def test_racine_du_systeme_jamais_examinee(self):
        astro_scan = self._module()
        self.assertEqual(astro_scan.dossiers_workspace(pathlib.Path("/")), [pathlib.Path("/")])


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
