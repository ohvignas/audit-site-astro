# Phase 1 : combler les trous de détection mesurés par le cobaye — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Passer le banc d'essai cobaye de 90/101 (89 %) avec 2 faux positifs et 1 constat inattendu à **104/104 (100 %) en phase 1, 0 faux positif, 0 inattendu**, en corrigeant chaque raté à sa cause réelle : le détecteur quand il est aveugle, le cobaye quand le défaut n'est pas servi tel que prévu, jamais le matcher pour « faire passer ».

**Architecture:** Corrections ciblées dans les scripts de collecte (`crawl_site.py`, `http_checks.sh`, `security_probe.sh`, `geo_check.py`, `astro_scan.py`, `pagespeed.py`, `rapport_brut.py`), chacune couverte par un test unitaire stdlib qui rejoue le défaut **et** son jumeau propre sur un petit site HTTP local (`tests/unit/site_local.py`, sans réseau externe). Deux corrections de cobaye (défaut masqué côté `casse`, vrais défauts côté `propre`). La CI passe en `--phase 1` et le cliquet monte à 100 % / 0 / 0.

**Tech Stack:** Python 3.9+ (stdlib, `unittest`, `http.server`), Bash (macOS 3.2 + Linux), Astro 7.3 (`@astrojs/node`), nginx, GitHub Actions.

**Spec:** [`docs/superpowers/plans/2026-09-30-00-feuille-de-route.md`](../../docs/superpowers/plans/2026-09-30-00-feuille-de-route.md) §5 Phase 1 ; mesures de référence : `docs/cobaye-baseline.md` (CI run `36722306289`, commit `50c78cb`) ; registre : `.superpowers/sdd/2026-09-30-01-phase0-cobaye/progress.md`.

## Global Constraints

- Python ≥ 3.9, **bibliothèque standard uniquement** (scripts et tests) ; tests : `python3 -m unittest discover -s tests/unit -t . -v`.
- Bash compatible **macOS 3.2 et Linux** : pas de `timeout`, `mapfile`, `declare -A`, `${v,,}`, `sed -i` sans extension, `grep -P`. Les scripts peuvent appeler `python3` (déjà requis par la collecte).
- **Mac de dev : 16 Go, a déjà planté.** En local : tests unitaires, `astro_scan.py`, petits serveurs HTTP de test. **Jamais** `docker`, `lancer.sh`, Chrome, Lighthouse, `npm install` complet ni `astro build`. Toute validation lourde (build des cobayes, audit complet, score) se fait **en CI**.
- **Une seule branche `phase1/detection`, créée depuis `phase0/execution`** (HEAD `350b7c0`), **un commit par tâche**, poussée pour la CI ; PR brouillon (déclencheur `pull_request`), aucun merge sans accord de l'utilisateur.
- Chaque message de commit se termine par la ligne `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Zéro faux positif** : chaque changement de détecteur est testé sur un cas « propre » (même test, variante corrigée) et ne doit rien déclencher sur `tests/cobaye/propre`. Le test statique (`test_cobaye_statique.py`) le vérifie pour `astro_scan`, la CI pour le reste.
- On ne modifie un matcher de `verite-terrain.json` que s'il est faux sur la sortie réelle (ou si le détecteur change de fichier de sortie) ; on ne supprime jamais un défaut du cobaye cassé : on corrige sa **forme** s'il n'est pas servi comme prévu (commentaire d'ID conservé).
- Toute nouvelle recommandation Astro reste alignée sur docs.astro.build (Astro 7) ; ne pas toucher au vrai site beta.illith.com.

## Causes racines (vérifiées sur les sorties réelles de la CI run 2 et sur le code)

Sources : artefact `audits-cobaye` du run `36722306289` (`casse/data/…`, `propre/data/…`), journal de build Astro du même run, code à `350b7c0`.

| Constat | Cause racine (preuve) | Correction | Tâche |
|---|---|---|---|
| **S03** 404 dans le sitemap, **S04** noindex dans le sitemap | Le sitemap du cassé sort en `http://` (S02) : les 12 URL redirigent (302). `crawl_site.py:855-861` est une chaîne `if redirect … elif non200 … elif noindex` : la branche redirection masque l'état de la cible (`http://…/page-404-dans-sitemap` → 404, `http://…/cachee` → page `noindex` bien crawlée, `issues.json` : seul `sitemap_redirect` ×12). | détecteur | 1 |
| **S38** robots.txt bloque `/_astro/` | `robots.txt` du cassé : `Disallow: /_astro/` ; la regex de `crawl_site.py:880` ne connaît que `.css/.js`, `wp-content`, `wp-includes`. | détecteur | 1 |
| **S19** canonical vers 404 non liée | `crawl_site.py:792-793` : `canonical_bad_target` n'est évalué que si la cible est dans `pages` ; `/page-supprimee` n'est liée nulle part, donc jamais crawlée. | détecteur | 2 |
| **A05** champ sans label | Lighthouse `label` = **score 1** sur le cassé : axe-core accepte un `placeholder` non vide comme nom accessible (`casse/src/layouts/Base.astro:49`). Aucun audit Lighthouse ne peut donc lever ce défaut réel (WCAG 3.3.2 : un placeholder disparaît à la saisie). | détecteur (contrôle HTML statique dans le crawl) + matcher A05 repointé vers la nouvelle clé | 3 |
| **C10** sitemap depuis `request.url` | `astro_scan.py:324` : `… and "site" not in t` ; « http://www.**site**maps.org » contient `site` → condition fausse. | détecteur | 4 |
| **C12** pas d'`allowedDomains` | `astro_scan.py:528` : `"allowedDomains" not in t` ; le commentaire `// C12 : pas de security.allowedDomains` (`casse/astro.config.mjs:10`) suffit à le croire configuré. | détecteur | 4 |
| Inattendu Haute sur le propre « URL http:// en dur » | `astro_scan.py:328` : `"http://" in t` se déclenche sur `xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"` (identifiant XML, pas une URL chargée). | détecteur | 4 |
| C07 faux positif masqué par `"propre": "ignorer"` | `astro_scan.py:208` compte `<script type="application/ld+json" set:html={JSON.stringify(…)}>` (JSON-LD, ×2 sur le propre) comme XSS. | détecteur, puis retrait de `ignorer` | 4 |
| **H06** `/_astro/` sans cache long | nginx sert bien `Cache-Control: no-cache` (`casse.conf:21-25`, Lighthouse ignore ces fichiers « explicitement non cacheables »). Mais la page d'accueil ne référence les JS hashés **que** via `<astro-island component-url=… renderer-url=…>` (réseau Lighthouse : `/_astro/Avis…js`, `client…js`, `Chat…js`…) ; CSS inline. `http_checks.sh:106-107` ne lit que `src=`/`href=` : la §4 ne contient aucun `/_astro/`. | détecteur | 5 |
| **S35b** soft 404 en HTTP (phase 1) | `http_checks.sh:190` ne teste qu'une URL à la racine (`/404-page-inexistante-audit`, 404 correct) ; aucune sonde sous une route dynamique (`/formations/zz…` répond 200 sur le cassé). De plus `BASE="https://$HOST"` (`http_checks.sh:16`) ignore le schéma réel. | détecteur (+ ordre de `collect_all.sh` : crawl avant http) | 5 |
| **X02** source maps publiques | `security_probe.sh:87` ne lit que `(src|href)="….js"` : seuls `/bloquant.js` et `/fake-analytics.js` (sans map) sont testés ; les bundles `/_astro/*.js` (buildés avec `sourcemap: true`) sont référencés par les îlots. | détecteur | 6 |
| **X06** proxy `/_image` ouvert (phase 1) | `security_probe.sh:72` sonde `href=https://example.com/x.png`, image inexistante : le cassé répond **500** (distant autorisé mais introuvable), le propre 403 ; la ligne est « ✅ » dans les deux cas. | détecteur (vraie image PNG distante, configurable) | 6 |
| **G08** article sans auteur | `geo_check.py:157` n'échantillonne que les pages `indexable` ; les articles du cassé ne le sont pas (voir S21 : canonical `/blog/article-ok/` ≠ URL). Aucun article dans l'échantillon → signal absent. | cobaye (tâche 9) + échantillon par gabarit pour ne plus évincer un gabarit d'article | 7, 9 |
| **S21** page à 5 clics | Profondeurs correctes (`/profond/5` = 5 clics). Mais `deep_page` n'est évalué que pour les pages indexables (`crawl_site.py:750,775`) et `/profond/n` est **prérendue** (`profond/[n].astro:2`, build : `/profond/1/index.html`) : `Astro.url.pathname` finit par `/`, donc la canonical de `casse/src/layouts/Base.astro:8` pointe vers `/profond/1/` → `canonical_other`, page non indexable. Défaut accidentel du cobaye qui masque S21 (et G08). | cobaye | 9 |
| **S10** redirection 302 | `casse/astro.config.mjs:16` : `'/promo': { status: 302, … }` est **servi en 301** par Astro 7.3 + `@astrojs/node` (crawl : `/promo` 301, 1 saut). Le défaut n'est pas servi. Les 12 `redirect_temp` viennent du 302 http→https de nginx (H07). | cobaye (page `promo.astro` avec `Astro.redirect(…, 302)`) | 9 |
| **S06** faux positif (orpheline sur le propre) | `propre/src/pages/sitemap.xml.ts:3` liste `/blog/article-casse` mais aucune page du propre ne la lie (crawl propre : `inlinks 0`, profondeur « hors liens »). Vrai défaut du jumeau propre ; le détecteur a raison. | cobaye propre | 9 |
| **A06** faux positif (zones tactiles sur le propre) | Lighthouse `target-size` = 0 sur `/`, `/catalogue`, `/formations` du propre : liens de la liste des formations hauts de 20 px et empilés (« safe clickable space 17.8px »). Vrai défaut du propre (styles `nav a, footer a` seulement). | cobaye propre | 9 |
| `rapport_brut.py` classe 6,3 Mo d'images en « basse » | `rapport_brut.py:68` : sévérité calculée sur `gain_ms` seul ; les gains en octets sont ignorés. | détecteur (rapport) | 8 |
| `pagespeed.py` « audit réussi listé en échec » (beta.illith.com) | Vérifié dans la locale Lighthouse `fr` : « Les liens sont identifiables grâce à leur couleur. » est le **failureTitle** de `link-in-text-block` (le titre de succès est « … sans se baser sur la couleur. »). C'était donc un vrai échec, au libellé trompeur. En revanche `pagespeed.py:148-149` (`score not in (None, 1)`) laisse passer les audits `informative`/`manual` notés entre 0 et 1. | durcissement + identifiant d'audit accolé au titre | 8 |
| `test_cobaye_statique` évalue le propre avec le matcher brut | **Déjà corrigé** par `350b7c0` (`test_cobaye_statique.py:26` utilise `score._matcher_fp(d)`). Reste à durcir le test (ratés attendus = `[]`, aucun constat Haute sur le propre). | test | 4 |

## Structure des fichiers

```
plugins/audit-site-astro/skills/audit-complet/
  scripts/crawl_site.py        (modifié : sitemap → état de la cible, robots /_astro/, cibles de canonical, champs sans libellé)
  scripts/astro_scan.py        (modifié : commentaires ignorés, identifiant `site`, xmlns, set:html JSON-LD)
  scripts/http_checks.sh       (modifié : BASE réelle, JS des îlots en §4, §7 soft 404 sous routes dynamiques)
  scripts/collect_all.sh       (modifié : crawl avant http, pages.json passé à http_checks)
  scripts/security_probe.sh    (modifié : JS des îlots pour les source maps, section proxy /_image)
  scripts/geo_check.py         (modifié : échantillon par gabarit)
  scripts/pagespeed.py         (modifié : vrais échecs seulement, [id] accolé)
  scripts/rapport_brut.py      (modifié : sévérité par ms OU octets)
  SKILL.md                     (modifié : ligne HTTP)
tests/unit/
  site_local.py                (nouveau : site HTTP local de test)
  test_crawl_local.py          (nouveau)   test_astro_scan.py (nouveau)   test_http_checks.py (nouveau)
  test_security_probe.py       (nouveau)   test_geo_echantillon.py (nouveau)   test_rapports.py (nouveau)
  test_analyseurs.py, test_cobaye_statique.py, test_score.py (modifiés)
tests/cobaye/
  verite-terrain.json          (modifié : A05 repointé, C07 sans « ignorer »)
  seuils.json                  (modifié : 1.0 partout, 0 faux positif, 0 inattendu)
  README.md                    (modifié : --phase 1)
  casse/astro.config.mjs, casse/src/layouts/Base.astro, casse/src/pages/promo.astro (nouveau)
  propre/src/layouts/Base.astro, propre/src/pages/index.astro
.github/workflows/docker.yml   (modifié : score en --phase 1)
docs/cobaye-baseline.md, README.md (modifiés : mesure phase 1)
```

## Effet attendu sur le score (CI)

| Après la tâche | Rappel base (/101) | Phase 1 (S19, S35b, X06) | Faux positifs | Inattendus |
|---|---|---|---|---|
| départ (`350b7c0`) | 90 | 0/3 | 2 (S06, A06) | 1 |
| 1 | 93 (+S03, S04, S38) | 0/3 | 2 | 1 |
| 2 | 93 | 1/3 (+S19) | 2 | 1 |
| 3 | 94 (+A05) | 1/3 | 2 | 1 |
| 4 | 96 (+C10, C12) | 1/3 | 2 (C07 désormais mesuré : 0) | 0 |
| 5 | 97 (+H06) | 2/3 (+S35b) | 2 | 0 |
| 6 | 98 (+X02) | 3/3 (+X06) | 2 | 0 |
| 7, 8 | 98 | 3/3 | 2 | 0 |
| 9 | 101 (+S10, S21, G08) | 3/3 | 0 | 0 |
| 10 (CI `--phase 1`) | **104/104 (100 %)** | requis | **0** | **0** |

Les seuils actuels (`seuils.json` de `350b7c0`) restent respectés à chaque étape : le rappel ne fait que monter, faux positifs ≤ 2, inattendus ≤ 1.

---

### Task 1 : crawl — l'état de la cible d'une URL de sitemap redirigée, et `/_astro/` bloqué dans robots.txt (S03, S04, S38)

**Files:**
- Create: `tests/unit/site_local.py`, `tests/unit/test_crawl_local.py`
- Modify: `plugins/audit-site-astro/skills/audit-complet/scripts/crawl_site.py` (constante `ASSETS_RX`, bloc sitemap de `build_issues`, contrôle `robots_blocks_assets`)

**Interfaces:**
- Produces : `SiteLocal(routes, prefixes)` (gestionnaire de contexte, attributs `url`, `base`, jeton `@@BASE@@`), réutilisé par les tâches 2, 3, 5, 6. Clés `issues.json` inchangées (`sitemap_redirect`, `sitemap_non200`, `sitemap_noindex`, `robots_blocks_assets`), mais une URL de sitemap qui redirige peut désormais lever **aussi** `sitemap_non200` / `sitemap_noindex` (exemple = l'URL du sitemap).

- [ ] **Step 0 : branche**

```bash
git fetch origin
git checkout -b phase1/detection phase0/execution
```

- [ ] **Step 1 : le site HTTP local de test** — `tests/unit/site_local.py` :

```python
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
```

- [ ] **Step 2 : tests qui échouent** — `tests/unit/test_crawl_local.py` (le site contient déjà les routes des tâches 2 et 3 ; leurs tests sont ajoutés par ces tâches) :

```python
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ICI = pathlib.Path(__file__).resolve().parent
RACINE = ICI.parents[1]
sys.path.insert(0, str(ICI))
from site_local import HTML, SiteLocal  # noqa: E402

CRAWL = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts/crawl_site.py"


def page(corps, tete=""):
    return ("<html lang='fr'><head><meta name='viewport' content='width=device-width'>"
            "<title>Titre de test suffisamment long</title>" + tete + "</head><body><main>" + corps + "</main></body></html>")


ROUTES = {
    "/": (200, HTML, page('<a href="/canon-cassee">Canonical</a> <a href="/formulaire">Formulaire</a>')),
    "/robots.txt": (200, {"Content-Type": "text/plain"},
                    "User-agent: *\nDisallow: /_astro/\n\nSitemap: @@BASE@@/sitemap.xml\n"),
    "/sitemap.xml": (200, {"Content-Type": "application/xml"},
                     '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                     "<url><loc>@@BASE@@/r/cachee</loc></url><url><loc>@@BASE@@/r/manque</loc></url></urlset>"),
    # URL du sitemap qui redirigent (comme http:// → https:// derrière un proxy) vers une page noindex et une 404
    "/r/cachee": (301, {"Location": "/cachee"}, ""),
    "/r/manque": (301, {"Location": "/manque"}, ""),
    "/cachee": (200, HTML, page("<p>Réservé</p>", "<meta name='robots' content='noindex'>")),
    # canonical vers une page jamais liée, en 404 (tâche 2)
    "/canon-cassee": (200, HTML, page("<p>Programme</p>", "<link rel='canonical' href='@@BASE@@/supprimee'>")),
    # champs de formulaire (tâche 3)
    "/formulaire": (200, HTML, page(
        '<input type="email" placeholder="Votre email">'           # sans libellé (placeholder seul)
        '<label for="nom">Nom</label><input id="nom">'             # libellé explicite
        '<label>Ville <input name="ville"></label>'                # libellé englobant
        '<input type="hidden" name="jeton"><input aria-label="Recherche"><button>OK</button>')),
}


class TestCrawlLocal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        with SiteLocal(ROUTES) as site:
            r = subprocess.run([sys.executable, str(CRAWL), site.url, "--out", cls.tmp.name, "--delay", "0",
                                "--max-pages", "50", "--timeout", "5"], capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr[-2000:]
        cls.issues = json.loads(pathlib.Path(cls.tmp.name, "issues.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def exemples(self, cle):
        return json.dumps(self.issues.get(cle, {}).get("examples", []), ensure_ascii=False)

    # Tâche 1 : la redirection d'une URL du sitemap ne masque plus la 404 ni le noindex de sa cible (S03, S04)
    def test_sitemap_redirige_puis_404_et_noindex(self):
        self.assertEqual(self.issues["sitemap_redirect"]["count"], 2)
        self.assertIn("/r/manque", self.exemples("sitemap_non200"))
        self.assertIn("/r/cachee", self.exemples("sitemap_noindex"))

    # Tâche 1 : Disallow: /_astro/ bloque le CSS/JS d'Astro (S38)
    def test_robots_bloque_les_assets_astro(self):
        self.assertEqual(self.issues.get("robots_blocks_assets", {}).get("examples"), ["/_astro/"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3 : vérifier l'échec** — `python3 -m unittest tests.unit.test_crawl_local -v` → 2 échecs (`'/r/manque' not found in '[]'`, `None != ['/_astro/']`).

- [ ] **Step 4 : implémenter** dans `crawl_site.py`.

Après `SKIP_TEXT_TAGS = {…}` (ligne 48), ajouter :
```python
# Chemins de CSS/JS nécessaires au rendu : WordPress, Astro (/_astro/), Next.js (/_next/)
ASSETS_RX = re.compile(r"\.(css|js)|wp-content/(themes|plugins)|wp-includes|/_astro\b|/_next/", re.I)
```

Remplacer le bloc sitemap de `build_issues` (lignes 851-864) :
```python
    for u in sitemap_set:
        p = pages.get(u)
        if not p:
            continue
        if p["redirect_hops"]:
            add("sitemap_redirect", "URL du sitemap qui redirigent (souvent http:// ou slash final incohérent)", "moyenne",
            {"url": u, "vers": p["final_url"]})
        elif p["final_status"] != 200:
            add("sitemap_non200", "URL du sitemap en erreur", "haute", {"url": u, "status": p["final_status"]})
        elif p.get("noindex"):
            add("sitemap_noindex", "URL du sitemap en noindex (signal contradictoire)", "haute", u)
        elif p.get("canonicals") and p["canonicals"][0] != u:
            add("sitemap_canonicalized", "URL du sitemap canonisées ailleurs", "moyenne",
                {"url": u, "canonical": p["canonicals"][0]})
```
par :
```python
    for u in sitemap_set:
        p = pages.get(u)
        if not p:
            continue
        cible = p
        if p["redirect_hops"]:
            add("sitemap_redirect", "URL du sitemap qui redirigent (souvent http:// ou slash final incohérent)", "moyenne",
                {"url": u, "vers": p["final_url"]})
            cible = pages.get(p["final_url"]) or p
        # une redirection ne masque plus l'état de la cible : 404 et noindex restent signalés
        if cible["final_status"] != 200:
            add("sitemap_non200", "URL du sitemap en erreur", "haute", {"url": u, "status": cible["final_status"]})
        elif cible.get("noindex"):
            add("sitemap_noindex", "URL du sitemap en noindex (signal contradictoire)", "haute", u)
        elif cible.get("canonicals") and cible["canonicals"][0] != cible["url"]:
            add("sitemap_canonicalized", "URL du sitemap canonisées ailleurs", "moyenne",
                {"url": u, "canonical": cible["canonicals"][0]})
```

Remplacer (ligne 880) :
```python
        if not rule_allow and re.search(r"\.(css|js)|wp-content/(themes|plugins)|wp-includes", pat, re.I):
```
par :
```python
        if not rule_allow and ASSETS_RX.search(pat):
```

- [ ] **Step 5 : tests verts** — `python3 -m unittest tests.unit.test_crawl_local tests.unit.test_analyseurs -v` → `OK`.
Propre : son sitemap est en https sans redirection, ses cibles sont en 200 sans noindex, son robots.txt est `Allow: /` → rien de nouveau. Cassé (CI) : `sitemap_non200` contient `http://casse.cobaye.test/page-404-dans-sitemap` (S03), `sitemap_noindex` contient `http://casse.cobaye.test/cachee` (S04), `robots_blocks_assets` = `["/_astro/"]` (S38).

- [ ] **Step 6 : commit**

```bash
git add tests/unit/site_local.py tests/unit/test_crawl_local.py plugins/audit-site-astro/skills/audit-complet/scripts/crawl_site.py
git commit -m "fix(crawl): état de la cible des URL de sitemap redirigées et /_astro/ bloqué par robots.txt

Une URL du sitemap qui redirige (http:// derrière un proxy) masquait sa 404
ou son noindex ; Disallow: /_astro/ n'était pas reconnu (regex WordPress).
Cobaye : S03, S04, S38.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2 : crawl — vérifier la cible d'une canonical même si la page n'est liée nulle part (S19)

**Files:**
- Modify: `…/scripts/crawl_site.py` (fonction `crawl`, signature et corps de `build_issues`)
- Modify: `tests/unit/test_crawl_local.py`

**Interfaces:**
- Consumes : `SiteLocal`, route `/canon-cassee` de la tâche 1.
- Produces : `build_issues(…, host, scheme, canon_targets=None)` ; `pages.json` → `meta.canonical_targets_checked` (`{url: statut}`) ; `canonical_bad_target` levé aussi pour une cible hors crawl (au plus 50 cibles vérifiées, sans les ajouter aux pages : pas de faux `http_4xx`).

- [ ] **Step 1 : test qui échoue** — dans `TestCrawlLocal` (`tests/unit/test_crawl_local.py`), après `test_robots_bloque_les_assets_astro` :

```python
    # Tâche 2 : canonical vers une page jamais liée : la cible est vérifiée quand même (S19)
    def test_canonical_vers_page_non_liee_en_404(self):
        ex = self.issues.get("canonical_bad_target", {}).get("examples", [])
        self.assertEqual([(e["url"].endswith("/canon-cassee"), e["statut_cible"]) for e in ex], [(True, 404)])
        self.assertNotIn("/supprimee", self.exemples("http_4xx"), "la cible n'est pas une page liée : pas de http_4xx")
```

- [ ] **Step 2 : vérifier l'échec** — `python3 -m unittest tests.unit.test_crawl_local -v` → `[] != [(True, 404)]`.

- [ ] **Step 3 : implémenter** dans `crawl_site.py`.

Juste après la boucle
```python
    # --- statut des cibles de liens non visitées (limite atteinte) : on ne les invente pas
    for u, p in pages.items():
        p["inlinks"] = len(inlinks.get(u, ()))
        p["inlink_anchors"] = anchors[u].most_common(10)
```
ajouter :
```python

    # --- cibles de canonical jamais crawlées (page non liée) : vérifier quand même leur statut (50 au plus)
    canon_targets = {}
    for p in list(pages.values()):
        c = (p.get("canonicals") or [None])[0]
        if (c and c != p["url"] and c not in pages and c not in canon_targets and (internal(c) or variant(c))
                and len(canon_targets) < 50):
            canon_targets[c], _ = analyze_page(c, fetch(c, timeout=args.timeout))
            time.sleep(args.delay)
```
Remplacer l'appel :
```python
    issues = build_issues(pages, inlinks, sitemap_set, sm_urls, blocked, robots, variant_links,
                          nofollow_internal, broken_imgs, host, scheme)
```
par :
```python
    issues = build_issues(pages, inlinks, sitemap_set, sm_urls, blocked, robots, variant_links,
                          nofollow_internal, broken_imgs, host, scheme, canon_targets)
```
Dans `meta`, après `"blocked_by_robots": blocked[:500], "broken_images": broken_imgs,` ajouter :
```python
        "canonical_targets_checked": {u: c["final_status"] for u, c in canon_targets.items()},
```
Remplacer l'en-tête de `build_issues` :
```python
def build_issues(pages, inlinks, sitemap_set, sm_urls, blocked, robots, variant_links, nofollow_internal,
                 broken_imgs, host, scheme):
    issues = {}
```
par :
```python
def build_issues(pages, inlinks, sitemap_set, sm_urls, blocked, robots, variant_links, nofollow_internal,
                 broken_imgs, host, scheme, canon_targets=None):
    issues = {}
    canon_targets = canon_targets or {}
```
et, dans le contrôle `canonical_other`, remplacer `tgt = pages.get(canon[0])` par :
```python
            tgt = pages.get(canon[0]) or canon_targets.get(canon[0])
```

- [ ] **Step 4 : tests verts** — `python3 -m unittest tests.unit.test_crawl_local -v` → `OK` (3 tests).
Propre : toutes ses canonicals sont auto-référentes → aucune cible à vérifier. Cassé (CI) : `canonical_bad_target` contient `/canonical-cassee` → `/page-supprimee` (404) ; il contient aussi `/canonical-http` → `http://…` (302), vrai défaut.

- [ ] **Step 5 : commit** — `git add` des deux fichiers ; message :
```
fix(crawl): vérifier la cible d'une canonical même quand la page n'est liée nulle part

canonical_bad_target exigeait que la cible ait été crawlée. Cobaye : S19.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 3 : crawl — champs de formulaire sans libellé (A05)

Lighthouse (axe-core) considère un `placeholder` comme nom accessible : le défaut réel « champ sans libellé » (WCAG 1.3.1 / 3.3.2) lui est invisible. On le détecte dans le HTML servi, au crawl.

**Files:**
- Modify: `…/scripts/crawl_site.py` (`PageParser`, `analyze_page`, `build_issues`)
- Modify: `tests/unit/test_analyseurs.py`, `tests/unit/test_crawl_local.py`
- Modify: `tests/cobaye/verite-terrain.json` (matcher A05)

**Interfaces:**
- Produces : `PageParser.champs_sans_libelle()` (liste) ; `pages.json` → `form_fields_no_label` (entier) ; `issues.json` → clé `form_no_label` (sévérité `moyenne`, exemples `{"url", "n"}`).

- [ ] **Step 1 : tests qui échouent**

`tests/unit/test_analyseurs.py`, dans `TestParseur`, après `test_listes_dans_main` :
```python
    def test_champs_sans_libelle(self):
        p = self.parse('<input type="email" placeholder="Votre email">'
                       '<input id="n"><label for="n">Nom</label>'
                       '<label>Ville <input name="v"></label>'
                       '<select title="Pays"></select><textarea aria-labelledby="t"></textarea>'
                       '<input type="hidden"><input type="submit"><button>OK</button><textarea></textarea>')
        self.assertEqual(len(p.champs_sans_libelle()), 2)
```
`tests/unit/test_crawl_local.py`, dans `TestCrawlLocal` :
```python
    # Tâche 3 : champ de formulaire sans libellé (placeholder seul), invisible pour Lighthouse (A05)
    def test_champ_sans_libelle(self):
        it = self.issues.get("form_no_label", {})
        self.assertEqual(it.get("count"), 1)
        self.assertTrue(it["examples"][0]["url"].endswith("/formulaire"))
```

- [ ] **Step 2 : vérifier l'échec** — `python3 -m unittest tests.unit.test_analyseurs tests.unit.test_crawl_local -v` → `AttributeError: … champs_sans_libelle` et `None != 1`.

- [ ] **Step 3 : implémenter** dans `crawl_site.py`.

Dans `PageParser.__init__`, remplacer
```python
        self.has_author_link = False

    def handle_starttag(self, tag, attrs):
```
par :
```python
        self.has_author_link = False
        self.fields = []        # champs de formulaire saisissables
        self.label_for = set()  # id visés par <label for>
        self._label_depth = 0

    def champs_sans_libelle(self):
        """Champs sans nom accessible fiable : ni <label for>, ni <label> englobant, ni aria-label(ledby), ni title.
        Un placeholder seul ne compte pas (il disparaît à la saisie — WCAG 3.3.2), même si Lighthouse l'accepte."""
        return [c for c in self.fields
                if not (c["nomme"] or c["dans_label"] or (c["id"] and c["id"] in self.label_for))]

    def handle_starttag(self, tag, attrs):
```
Dans `handle_starttag`, remplacer `        elif tag in ("iframe", "source", "video", "audio", "embed"):` par :
```python
        elif tag == "label":
            self._label_depth += 1
            if a.get("for"):
                self.label_for.add(a["for"])
        elif tag in ("input", "select", "textarea"):
            kind = (a.get("type") or "text").lower() if tag == "input" else tag
            if kind not in ("hidden", "submit", "button", "reset", "image"):
                self.fields.append({"id": a.get("id", ""), "dans_label": self._label_depth > 0,
                                    "nomme": any(a.get(k, "").strip() for k in ("aria-label", "aria-labelledby", "title"))})
        elif tag in ("iframe", "source", "video", "audio", "embed"):
```
Dans `handle_endtag`, remplacer
```python
        elif tag in SKIP_TEXT_TAGS and self._skip:
            self._skip -= 1
```
par :
```python
        elif tag in SKIP_TEXT_TAGS and self._skip:
            self._skip -= 1
        elif tag == "label" and self._label_depth:
            self._label_depth -= 1
```
Dans `analyze_page`, après `"tag_counts": dict(parser.tags),` ajouter :
```python
        "form_fields_no_label": len(parser.champs_sans_libelle()),
```
Dans `build_issues`, juste avant `        if p.get("imgs_no_dims"):` ajouter :
```python
        if p.get("form_fields_no_label"):
            add("form_no_label", "Champs de formulaire sans libellé (placeholder seul ou rien) — WCAG 1.3.1 / 3.3.2",
                "moyenne", {"url": p["url"], "n": p["form_fields_no_label"]}, n=p["form_fields_no_label"])
```

- [ ] **Step 4 : matcher A05** — dans `tests/cobaye/verite-terrain.json`, remplacer la ligne A05 par :
```json
    {"id": "A05", "domaine": "a11y", "titre": "Champ sans label", "phase": "base", "matcher": {"type": "crawl_issue", "cle": "form_no_label"}},
```
(Justification à reporter dans le message de commit : le matcher Lighthouse ne peut jamais se déclencher sur ce défaut, l'audit `label` étant réussi à 1 sur le cassé.)

- [ ] **Step 5 : tests verts** — `python3 -m unittest tests.unit.test_analyseurs tests.unit.test_crawl_local tests.unit.test_score -v` → `OK`.
Propre : son seul champ (`contact.astro:13`) a `<label for="email">` + `id="email"` ; le bouton du chat est un `<button>` → aucun `form_no_label`. Cassé (CI) : le champ du pied de page (`Base.astro:49`) → `form_no_label` sur chaque page.

- [ ] **Step 6 : commit** — fichiers : `crawl_site.py`, `test_analyseurs.py`, `test_crawl_local.py`, `verite-terrain.json` ; message :
```
feat(crawl): champs de formulaire sans libellé (placeholder seul)

Lighthouse accepte un placeholder comme nom accessible : l'audit label était
réussi sur le cobaye cassé. Contrôle déplacé dans le HTML servi ; matcher A05
repointé vers form_no_label.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 4 : astro_scan — commentaires, identifiant `site`, espaces de noms XML, JSON-LD (C10, C12, inattendu, C07)

**Files:**
- Create: `tests/unit/test_astro_scan.py`
- Modify: `…/scripts/astro_scan.py`, `tests/unit/test_cobaye_statique.py`, `tests/cobaye/verite-terrain.json` (C07)

**Interfaces:**
- Produces : `sans_commentaires(t)` et `NAMESPACES_XML` dans `astro_scan.py` ; le constat « contient une URL http:// en dur » cite désormais l'URL (`… en dur (http://…)`) ; `set:html` sur `<script type="application/ld+json">` n'est plus compté.

- [ ] **Step 1 : tests qui échouent** — `tests/unit/test_astro_scan.py` :

```python
import json
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

    def test_json_ld_seul_rien_a_signaler(self):
        page = '---\nconst o = {};\n---\n<script type="application/ld+json" set:html={JSON.stringify(o)}></script>\n'
        self.assertNotIn("set:html", textes(scanner({"src/pages/index.astro": page})))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2 : vérifier l'échec** — `python3 -m unittest tests.unit.test_astro_scan -v` → 5 échecs (C12 en commentaire, 2× sitemap, 2× set:html) ; `test_allowed_domains_configure` et `test_vraie_url_http_en_dur` passent déjà (garde-fous).

- [ ] **Step 3 : implémenter** dans `astro_scan.py`.

Avant `def lines_matching(text, rx, limit=50):` ajouter :
```python
def sans_commentaires(t):
    """Retire les commentaires JS/TS (/* … */ et // …) sans toucher aux URL (https://…).
    Réservé aux fichiers de config et aux endpoints : un motif « /* » dans une chaîne (glob) serait mal lu."""
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    return re.sub(r"(?<![:\w\"'`/])//[^\n]*", "", t)


# Espaces de noms XML : des identifiants, pas des URL chargées (xmlns du sitemap…)
NAMESPACES_XML = re.compile(r"http://(www\.sitemaps\.org|www\.w3\.org|www\.google\.com/schemas|purl\.org)/")
```
Dans `scan_astro_config`, remplacer `    t = read(cfg)` par `    t = sans_commentaires(read(cfg))`.
Dans `RX`, après la clé `"astro_url_href"` ajouter :
```python
    "jsonld_script": re.compile(r"type\s*=\s*[\"']application/ld\+json[\"']", re.I),
```
Dans `scan_src`, remplacer
```python
        set_html += [f"{r}:{i} {l}" for i, l in lines_matching(t, RX["set_html"])]
```
par :
```python
        # JSON-LD (<script type="application/ld+json" set:html={…}>) : pas du HTML interprété, pas un XSS
        set_html += [f"{r}:{i} {l}" for i, l in lines_matching(t, RX["set_html"]) if not RX["jsonld_script"].search(l)]
```
Remplacer le bloc des endpoints sitemap (lignes 322-329) :
```python
        for name, t in eps.items():
            if "sitemap" in name:
                if re.search(r"url\.origin|request\.url|Astro\.url\.origin|new URL\(\s*request", t) and "site" not in t:
                    add("haute", "seo", f"{name} construit les URL depuis l'origine de la requête : derrière un proxy "
                                        f"elles sortent en http:// (constaté sur le sitemap en ligne ?)", [name],
                        "utiliser l'origine canonique : new URL(path, import.meta.env.SITE ?? 'https://domaine.fr')")
                if "http://" in t:
                    add("haute", "seo", f"{name} contient une URL http:// en dur", [name])
```
par :
```python
        for name, t in eps.items():
            if "sitemap" in name:
                code = sans_commentaires(t)
                par_requete = re.search(r"url\.origin|request\.url|Astro\.url\.origin|new URL\(\s*request", code)
                # l'identifiant `site` (Astro.site, context.site, ({ site })…), pas la sous-chaîne de « sitemaps.org »
                par_site = re.search(r"\bAstro\.site\b|\bcontext\.site\b|import\.meta\.env\.SITE\b|(?<![\w.$])site\b(?!\s*:)", code)
                if par_requete and not par_site:
                    add("haute", "seo", f"{name} construit les URL depuis l'origine de la requête : derrière un proxy "
                                        f"elles sortent en http:// (constaté sur le sitemap en ligne ?)", [name],
                        "utiliser l'origine canonique : new URL(path, import.meta.env.SITE ?? 'https://domaine.fr')")
                en_dur = [u for u in re.findall(r"http://[^\s'\"`<>)]+", code) if not NAMESPACES_XML.match(u)]
                if en_dur:
                    add("haute", "seo", f"{name} contient une URL http:// en dur ({en_dur[0][:60]})", [name])
```
Dans `scan_astro_features`, remplacer `    t = read(cfg) if cfg else ""` par `    t = sans_commentaires(read(cfg)) if cfg else ""`, puis
```python
    if ssr and at_least(5, 14) and "allowedDomains" not in t:
```
par :
```python
    if ssr and at_least(5, 14) and not re.search(r"\ballowedDomains\s*:", t):
```

- [ ] **Step 4 : C07 mesuré sur le propre** — dans `tests/cobaye/verite-terrain.json`, remplacer la ligne C07 par (retrait de `propre: ignorer` et de sa raison, devenue caduque) :
```json
    {"id": "C07", "domaine": "code", "titre": "set:html non assaini", "phase": "base", "matcher": {"type": "code", "regex": "set:html", "ou_contient": "src/pages/index.astro"}},
```

- [ ] **Step 5 : durcir le test statique** — `tests/unit/test_cobaye_statique.py`. Le passage à `score._matcher_fp(d)` pour le propre (report de la revue phase 0) est **déjà fait** dans `350b7c0` (ligne 26) : vérifier qu'il est présent, ne pas le refaire. Remplacer :
```python
        # trous connus du scanner, corrigés en phase 1 (la liste ne doit que rétrécir)
        self.assertEqual(rates, ["C10", "C12"], f"défauts de code non détectés : {rates}")
        self.assertEqual(fps, [], f"faux positifs de code : {fps}")
```
par :
```python
        self.assertEqual(rates, [], f"défauts de code non détectés : {rates}")
        self.assertEqual(fps, [], f"faux positifs de code : {fps}")

    def test_propre_sans_constat_critique_ni_haut(self):
        with tempfile.TemporaryDirectory() as t:
            propre = self._scan("propre", t)
            constats = json.loads((propre / "data/code/code-scan.json").read_text(encoding="utf-8"))["constats"]
        hauts = [c["constat"] for c in constats if c["severite"] in score.SEVERES]
        self.assertEqual(hauts, [], "constats Critique/Haute sur le jumeau propre (comptés « inattendus » en CI)")
```

- [ ] **Step 6 : tests verts** — `python3 -m unittest tests.unit.test_astro_scan tests.unit.test_cobaye_statique tests.unit.test_score -v` → `OK`.
Contrôle manuel (léger) : `python3 plugins/audit-site-astro/skills/audit-complet/scripts/astro_scan.py tests/cobaye/propre --out /tmp/scan-propre && grep '^### \[\(critique\|haute\)' /tmp/scan-propre/code-scan.md` → **aucune** ligne ; sur `casse` : « depuis l'origine de la requête » (C10), « sans security.allowedDomains » (C12), « 1 usage(s) de set:html » (C07, `src/pages/index.astro`) et plus aucun « http:// en dur ».

- [ ] **Step 7 : commit** — fichiers : `astro_scan.py`, `test_astro_scan.py`, `test_cobaye_statique.py`, `verite-terrain.json` ; message :
```
fix(astro_scan): commentaires ignorés, identifiant site, xmlns et JSON-LD

« sitemaps.org » contenait « site » (C10), un commentaire citant allowedDomains
valait configuration (C12), le xmlns du sitemap sortait en Haute sur le propre,
set:html de JSON-LD comptait comme XSS (C07 désormais mesuré sur le propre).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 5 : http_checks — JS des îlots (H06), soft 404 sous les routes dynamiques (S35b)

**Files:**
- Create: `tests/unit/test_http_checks.py`
- Modify: `…/scripts/http_checks.sh`, `…/scripts/collect_all.sh`, `plugins/audit-site-astro/skills/audit-complet/SKILL.md`

**Interfaces:**
- Consumes : `SiteLocal` (tâche 1) ; `pages.json` du crawl (`url`, `final_status`, `redirect_hops`).
- Produces : `http_checks.sh URL [DOSSIER] [PAGES_JSON]` ; `BASE` = origine réellement servie (après redirections) ; §4 inclut jusqu'à 4 assets `/_astro/` lus dans `src|href|component-url|renderer-url` ; nouvelle **§7** avec, par segment d'au moins 2 pages, une ligne `- ❌ soft 404 sous /SEG/ : /SEG/zz-audit-inexistant-N répond 200 …` ou `- ✅ /SEG/… inexistant → HTTP 404`. `collect_all.sh` lance le crawl **avant** http.

- [ ] **Step 1 : tests qui échouent** — `tests/unit/test_http_checks.py` :

```python
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ICI = pathlib.Path(__file__).resolve().parent
RACINE = ICI.parents[1]
sys.path.insert(0, str(ICI))
from site_local import HTML, SiteLocal  # noqa: E402

SCRIPT = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts/http_checks.sh"
JS = {"Content-Type": "text/javascript"}

# Page d'accueil Astro typique : les JS hashés n'apparaissent QUE dans les attributs de l'îlot (component-url / renderer-url)
ACCUEIL = ("<html lang='fr'><head><title>Accueil</title></head><body>"
           '<astro-island uid="1" component-url="/_astro/Chat.abc123.js" renderer-url="/_astro/client.def456.js"></astro-island>'
           '<a href="/formations/a">A</a> <a href="/formations/b">B</a> <a href="/blog/x">X</a></body></html>')


def lancer(routes, prefixes, pages_json=None):
    with SiteLocal(routes, prefixes) as site, tempfile.TemporaryDirectory() as d:
        args = ["bash", str(SCRIPT), site.url, d] + ([pages_json(site.base, d)] if pages_json else [])
        env = dict(os.environ)
        env.pop("AUDIT_INSECURE_TLS", None)
        subprocess.run(args, capture_output=True, text=True, timeout=240, env=env)
        return pathlib.Path(d, "http-checks.md").read_text(encoding="utf-8")


class TestHttpChecksAstro(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # jumeau « cassé » : /_astro/ en no-cache (H06), toute URL sous /formations/ répond 200 (S35b)
        cls.casse = lancer({"/": (200, HTML, ACCUEIL)},
                           {"/_astro/": (200, dict(JS, **{"Cache-Control": "no-cache"}), "console.log(1)"),
                            "/formations/": (200, HTML, "<html><body>Formation</body></html>")})
        # jumeau « propre » : /_astro/ immuable, seules les formations existantes répondent 200
        cls.propre = lancer({"/": (200, HTML, ACCUEIL), "/formations/a": (200, HTML, "<html></html>"),
                             "/formations/b": (200, HTML, "<html></html>")},
                            {"/_astro/": (200, dict(JS, **{"Cache-Control": "public, max-age=31536000, immutable"}), "x")})

    def test_assets_des_ilots_controles(self):  # H06
        self.assertIn("/_astro/Chat.abc123.js", self.casse)
        self.assertIn("asset hashé Astro", self.casse)
        self.assertIn("/_astro/Chat.abc123.js", self.propre)
        self.assertNotIn("asset hashé Astro", self.propre)

    def test_soft_404_sous_route_dynamique(self):  # S35b
        self.assertRegex(self.casse, r"soft 404.*/formations/")
        self.assertNotIn("soft 404 sous /blog/", self.casse, "un seul lien /blog/ : pas une route dynamique")
        self.assertNotIn("soft 404 sous", self.propre)

    def test_segments_lus_dans_le_crawl(self):
        def pages(base, d):
            f = pathlib.Path(d, "pages.json")
            f.write_text(json.dumps({"pages": [{"url": base + u, "final_status": 200, "redirect_hops": 0}
                                               for u in ("/", "/cours/x", "/cours/y")]}), encoding="utf-8")
            return str(f)
        md = lancer({"/": (200, HTML, "<html><body>vide</body></html>")},
                    {"/cours/": (200, HTML, "<html><body>Cours</body></html>")}, pages)
        self.assertIn("soft 404 sous /cours/", md)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2 : vérifier l'échec** — `python3 -m unittest tests.unit.test_http_checks -v` → 3 échecs (la §4 est vide : `BASE` forcé en https et îlots ignorés ; pas de §7). Durée ≈ 10 s, sans réseau externe.

- [ ] **Step 3 : implémenter** dans `http_checks.sh`.

En-tête : remplacer
```bash
# Usage : bash http_checks.sh https://exemple.fr [DOSSIER_SORTIE]
# Sortie : DOSSIER_SORTIE/http-checks.md (lisible) — aucune modification du site.
```
par :
```bash
# Usage : bash http_checks.sh https://exemple.fr [DOSSIER_SORTIE] [PAGES_JSON]
#   PAGES_JSON (optionnel) : pages.json du crawl, pour trouver les routes dynamiques à tester (soft 404, §7) ;
#   sans lui, les liens de la page d'accueil servent de repli.
# Sortie : DOSSIER_SORTIE/http-checks.md (lisible) — aucune modification du site.
```
Remplacer `OUT="${2:-.}"` + `mkdir -p "$OUT"` par :
```bash
OUT="${2:-.}"
PAGES_JSON="${3:-}"
mkdir -p "$OUT"
```
Remplacer `BASE="https://$HOST"` par :
```bash
# Origine réellement servie (après redirections http→https, www…) : base des URL relatives de la page
FINAL=$(curl -s -o /dev/null -L --max-redirs 10 --max-time 20 -A "$UA" -w '%{url_effective}' "$URL" 2>/dev/null)
BASE=$(printf '%s' "${FINAL:-$URL}" | awk -F/ '{print $1"//"$3}')
```
§4 : remplacer les deux lignes
```bash
grep -oE '(src|href)="[^"]+\.(js|css|woff2?|webp|avif|png|jpe?g|svg)(\?[^"]*)?"' "$TMP/body.html" \
  | sed -E 's/^(src|href)="//; s/"$//' | awk '!seen[$0]++' | head -12 | while read -r a; do
```
par :
```bash
# Les JS hashés d'Astro sont souvent référencés seulement par les îlots (component-url / renderer-url) :
# on en prend toujours quelques-uns, puis les ressources classiques (src / href).
{ grep -oE '(src|href|component-url|renderer-url)="(https?://[^"/]+)?/_astro/[^"]+"' "$TMP/body.html" \
    | sed -E 's/^[a-z-]+="//; s/"$//' | head -4
  grep -oE '(src|href)="[^"]+\.(js|css|woff2?|webp|avif|png|jpe?g|svg)(\?[^"]*)?"' "$TMP/body.html" \
    | sed -E 's/^(src|href)="//; s/"$//'
} | sed 's/&amp;/\&/g' | awk '!seen[$0]++' | head -12 | while read -r a; do
```
À la fin du fichier (après la note de la §6), ajouter :
```bash

echo
echo "## 7. Soft 404 sous les routes dynamiques"
echo
# Segments qui regroupent au moins 2 pages (/formations/a, /formations/b…) = route dynamique probable.
SEGS=$(python3 - "$PAGES_JSON" "$TMP/body.html" "$(printf '%s' "$BASE" | awk -F/ '{print $3}')" <<'PY'
import json, re, sys
from collections import defaultdict
from urllib.parse import urlparse
pages_json, accueil, hote = sys.argv[1:4]
urls = []
try:
    urls = [p["url"] for p in json.load(open(pages_json, encoding="utf-8"))["pages"]
            if p.get("final_status") == 200 and not p.get("redirect_hops")]
except Exception:
    try:
        urls = re.findall(r'href="((?:https?://[^/"]+)?/[^"#?]*)"', open(accueil, encoding="utf-8", errors="replace").read())
    except Exception:
        pass
enfants = defaultdict(set)
for u in urls:
    p = urlparse(u)
    if p.netloc and p.netloc != hote:
        continue
    parts = [x for x in p.path.split("/") if x]
    if len(parts) == 2:
        enfants[parts[0]].add(parts[1])
print("\n".join(sorted(s for s, e in enfants.items() if len(e) >= 2)[:6]))
PY
)
if [ -z "$SEGS" ]; then
  echo "- Aucune route dynamique repérée (aucun segment avec au moins 2 pages)."
else
  for seg in $SEGS; do
    faux="/$seg/zz-audit-inexistant-$RANDOM"
    code=$(curl -s -o /dev/null -A "$UA" --max-time 15 -w '%{http_code}' "$BASE$faux")
    if [ "$code" = "200" ]; then
      echo "- ❌ soft 404 sous /$seg/ : $faux répond 200 (page vide indexable) — si l'élément n'existe pas : return Astro.rewrite('/404') ou Astro.response.status = 404"
    else
      echo "- ✅ /$seg/… inexistant → HTTP $code"
    fi
  done
fi
```

- [ ] **Step 4 : ordre de la collecte** — dans `collect_all.sh`, remplacer
```bash
step http "$D/http/http-checks.md" valid_aucun bash "$DIR/http_checks.sh" "$URL" "$D/http"
step crawl "$D/crawl/pages.json" valid_crawl python3 "$DIR/crawl_site.py" "$URL" --out "$D/crawl" \
     --max-pages "${MAX_PAGES:-500}" --delay 0.3 --check-images 200
```
par :
```bash
step crawl "$D/crawl/pages.json" valid_crawl python3 "$DIR/crawl_site.py" "$URL" --out "$D/crawl" \
     --max-pages "${MAX_PAGES:-500}" --delay 0.3 --check-images 200
# après le crawl : http_checks y lit les routes dynamiques à tester en soft 404
step http "$D/http/http-checks.md" valid_aucun bash "$DIR/http_checks.sh" "$URL" "$D/http" "$D/crawl/pages.json"
```
Et dans `SKILL.md` (tableau des étapes, ligne HTTP), remplacer « fichiers techniques, test de soft 404 » par « fichiers techniques, soft 404 à la racine et sous chaque route dynamique (§7, via `pages.json` du crawl) ».

- [ ] **Step 5 : tests verts** — `bash -n plugins/audit-site-astro/skills/audit-complet/scripts/http_checks.sh && bash -n plugins/audit-site-astro/skills/audit-complet/scripts/collect_all.sh && python3 -m unittest tests.unit.test_http_checks tests.unit.test_tls tests.unit.test_collecte -v` → `OK`.
Propre (CI) : ses `/_astro/*` sont servis `public, max-age=31536000, immutable` (déjà visibles en §4 du run 2 : ✅) ; `/formations/zz…` → `Astro.rewrite('/404')` = 404, `/blog/zz…` (prérendu) = 404. Cassé : lignes `/_astro/Avis…js | no-cache | … | ⚠️ asset hashé Astro` (H06) et `- ❌ soft 404 sous /formations/ …` (S35b) ; `/blog/` et `/profond/` (prérendus) en 404.

- [ ] **Step 6 : commit** — fichiers : `http_checks.sh`, `collect_all.sh`, `SKILL.md`, `test_http_checks.py` ; message :
```
fix(http): JS des îlots Astro contrôlés, soft 404 sous les routes dynamiques

Les /_astro/*.js ne sont référencés que par component-url / renderer-url (H06) ;
nouvelle §7 : une URL inexistante sous chaque segment à plusieurs pages (S35b),
segments lus dans pages.json (crawl désormais avant http). BASE = origine servie.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 6 : security_probe — source maps des îlots (X02), proxy `/_image` ouvert (X06)

**Files:**
- Create: `tests/unit/test_security_probe.py`
- Modify: `…/scripts/security_probe.sh`

**Interfaces:**
- Consumes : `SiteLocal`.
- Produces : variable `AUDIT_IMAGE_DISTANTE` (URL d'une image PNG publique sur un domaine tiers ; défaut `https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png`) ; section `## Proxy d'images /_image` avec `- ❌ proxy d'images ouvert : …` ou `- ✅ /_image refuse une image d'un domaine tiers (HTTP N)` ; la ligne `/_image?href=https://example.com/x.png` du tableau disparaît.

- [ ] **Step 1 : tests qui échouent** — `tests/unit/test_security_probe.py` :

```python
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ICI = pathlib.Path(__file__).resolve().parent
RACINE = ICI.parents[1]
sys.path.insert(0, str(ICI))
from site_local import HTML, SiteLocal  # noqa: E402

SCRIPT = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts/security_probe.sh"
JS = {"Content-Type": "text/javascript"}
ACCUEIL = ("<html><head><title>Accueil</title></head><body>"
           '<astro-island uid="1" component-url="/_astro/Chat.abc123.js" renderer-url="/_astro/client.def456.js"></astro-island>'
           "</body></html>")


def sonder(routes, prefixes):
    with SiteLocal(routes, prefixes) as site, tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, AUDIT_IMAGE_DISTANTE="https://images.exemple.org/logo.png")
        env.pop("AUDIT_INSECURE_TLS", None)
        subprocess.run(["bash", str(SCRIPT), site.url, d], capture_output=True, text=True, timeout=240, env=env)
        return pathlib.Path(d, "security-probe.md").read_text(encoding="utf-8")


class TestSondeAstro(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # cassé : source map publique d'un JS d'îlot (X02), /_image transforme une image d'un domaine tiers (X06)
        cls.casse = sonder(
            {"/": (200, HTML, ACCUEIL),
             "/_astro/Chat.abc123.js": (200, JS, "console.log(1)\n//# sourceMappingURL=Chat.abc123.js.map\n"),
             "/_astro/Chat.abc123.js.map": (200, {"Content-Type": "application/json"}, '{"version":3}')},
            {"/_image": (200, {"Content-Type": "image/webp"}, "RIFF")})
        # propre : pas de source map, /_image refuse le domaine tiers (403)
        cls.propre = sonder(
            {"/": (200, HTML, ACCUEIL), "/_astro/Chat.abc123.js": (200, JS, "console.log(1)\n")},
            {"/_image": (403, {"Content-Type": "text/plain"}, "Forbidden")})

    def test_source_map_des_ilots(self):  # X02
        self.assertRegex(self.casse, r"/_astro/Chat\.abc123\.js → \.map HTTP 200")
        self.assertNotRegex(self.propre, r"\.map HTTP 200")

    def test_proxy_images_ouvert(self):  # X06
        self.assertIn("proxy d'images ouvert", self.casse)
        self.assertNotIn("proxy d'images ouvert", self.propre)
        self.assertIn("/_image refuse", self.propre)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2 : vérifier l'échec** — `python3 -m unittest tests.unit.test_security_probe -v` → 2 échecs (aucun JS d'îlot testé ; pas de section proxy).

- [ ] **Step 3 : implémenter** dans `security_probe.sh`.

Remplacer
```bash
# Debug / outils de dev
check "/_image?href=https://example.com/x.png" "" "info"
check "/__vite_ping" "" "moyenne"
```
par :
```bash
# Debug / outils de dev (le proxy /_image a sa propre section, avec une vraie image distante)
check "/__vite_ping" "" "moyenne"
```
Après `check "/wp-content/debug.log" "PHP (Warning|Notice|Fatal)" "haute"` ajouter :
```bash

echo
echo "## Proxy d'images /_image"
echo
# Image PNG réelle sur un domaine tiers : si /_image la transforme, n'importe qui fait travailler le serveur.
IMG_TIERS="${AUDIT_IMAGE_DISTANTE:-https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png}"
enc=$(printf '%s' "$IMG_TIERS" | sed -e 's/%/%25/g' -e 's/:/%3A/g' -e 's#/#%2F#g' -e 's/?/%3F/g' -e 's/&/%26/g' -e 's/=/%3D/g')
r=$(curl -s -o /dev/null -A "$UA" --max-time 30 -w '%{http_code}|%{content_type}' "$BASE/_image?href=$enc&w=16&f=webp")
icode=${r%%|*}; ictype=${r#*|}
if [ "$icode" = "200" ] && printf '%s' "$ictype" | grep -qi '^image/'; then
  echo "- ❌ proxy d'images ouvert : /_image transforme une image d'un domaine tiers ($IMG_TIERS → HTTP 200, $ictype) — n'importe qui peut consommer le CPU et la bande passante du serveur : image.remotePatterns avec un hostname explicite (jamais le protocole seul)"
else
  echo "- ✅ /_image refuse une image d'un domaine tiers (HTTP ${icode:-000})"
fi
```
Remplacer
```bash
js=$(grep -oE '(src|href)="[^"]+\.js"' "$TMP/home.html" | sed -E 's/^(src|href)="//; s/"$//' | awk '!s[$0]++' | head -8)
```
par :
```bash
# JS de la page, y compris ceux des îlots Astro (component-url / renderer-url), sans query string
js=$(grep -oE '(src|href|component-url|renderer-url)="[^"]+\.m?js(\?[^"]*)?"' "$TMP/home.html" \
  | sed -E 's/^[a-z-]+="//; s/"$//; s/\?.*$//' | awk '!s[$0]++' | head -12)
```

- [ ] **Step 4 : tests verts** — `bash -n plugins/audit-site-astro/skills/audit-complet/scripts/security_probe.sh && python3 -m unittest tests.unit.test_security_probe tests.unit.test_tls -v` → `OK`.
Propre (CI) : `location ~* \.map$ { return 404; }` + build sans sourcemap ; `remotePatterns` limité à `propre.cobaye.test` → `/_image` 403 (déjà mesuré au run 2). Cassé : bundles `/_astro/*.js` construits avec `vite.build.sourcemap: true` → `.map HTTP 200` (X02) ; `remotePatterns: [{ protocol: 'https' }]` → `/_image` 200 `image/webp` (X06).
Risque CI : X06 exige que le conteneur `app-casse` joigne Internet (réseau Docker `cobaye` non interne, runners GitHub connectés). Si la CI montre `HTTP 500` sur le cassé (image injoignable), fixer `AUDIT_IMAGE_DISTANTE` dans `auditer.sh` vers une autre image PNG publique stable ; ne jamais rendre le matcher plus lâche.

- [ ] **Step 5 : commit** — fichiers : `security_probe.sh`, `test_security_probe.py` ; message :
```
fix(securite): source maps des îlots Astro et vrai test du proxy /_image

Les bundles /_astro/ ne sont référencés que par les îlots (X02) ; la sonde
/_image visait une image inexistante (500 = « ✅ ») : elle demande désormais
une vraie image PNG distante, configurable par AUDIT_IMAGE_DISTANTE (X06).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 7 : geo_check — un représentant par gabarit avant les pages isolées (G08 durable)

**Files:**
- Create: `tests/unit/test_geo_echantillon.py`
- Modify: `…/scripts/geo_check.py` (`pick_sample`)

**Interfaces:**
- Produces : `pick_sample(crawl_path, home, n)` → même signature et même format ; ordre : la home, puis un représentant par segment de premier niveau, **les segments de plusieurs pages (gabarits : blog, formations…) avant les pages isolées**, chacun par liens entrants décroissants ; puis complément.

- [ ] **Step 1 : test qui échoue** — `tests/unit/test_geo_echantillon.py` :

```python
import json
import pathlib
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"))
import geo_check  # noqa: E402


def p(url, inlinks):
    return {"url": url, "indexable": True, "inlinks": inlinks, "final_status": 200, "redirect_hops": 0}


class TestEchantillonGeo(unittest.TestCase):
    def test_gabarit_d_article_jamais_evince(self):
        home = "https://ex.fr/"
        pages = [p(home, 50)] + [p("https://ex.fr/page-{0}".format(i), 20) for i in range(14)] + \
                [p("https://ex.fr/blog/a", 1), p("https://ex.fr/blog/b", 1)]
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d, "pages.json")
            f.write_text(json.dumps({"pages": pages}), encoding="utf-8")
            echantillon, _ = geo_check.pick_sample(str(f), home, 12)
        self.assertEqual(len(echantillon), 12)
        self.assertEqual(echantillon[0], home)
        self.assertEqual(sum("/blog/" in u for u in echantillon), 1, echantillon)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2 : vérifier l'échec** — `python3 -m unittest tests.unit.test_geo_echantillon -v` → `0 != 1` (les 11 pages isolées très liées remplissent l'échantillon).

- [ ] **Step 3 : implémenter** — dans `geo_check.py`, remplacer toute la fonction `pick_sample` par :

```python
def pick_sample(crawl_path, home, n):
    """Échantillon : la home, puis un représentant par gabarit (1er segment d'URL). Les segments qui regroupent
    plusieurs pages (blog/…, formations/… : un gabarit partagé) passent avant les pages isolées, pour qu'un gabarit
    d'article ne soit jamais évincé par des pages uniques très liées ; puis complément par liens entrants."""
    if not crawl_path or not Path(crawl_path).exists():
        return [home], []
    data = json.load(open(crawl_path, encoding="utf-8"))
    pages = data["pages"]
    idx = [p for p in pages if p.get("indexable")]
    idx.sort(key=lambda p: -(p.get("inlinks") or 0))

    def seg(p):
        return (urlparse(p["url"]).path.strip("/").split("/") or [""])[0]

    taille = Counter(seg(p) for p in idx)
    chosen, segs = [home], set()
    for p in sorted(idx, key=lambda p: (-min(taille[seg(p)], 2), -(p.get("inlinks") or 0))):
        s = seg(p)
        if p["url"] != home and s not in segs:
            chosen.append(p["url"])
            segs.add(s)
        if len(chosen) >= n:
            break
    for p in idx:
        if len(chosen) >= n:
            break
        if p["url"] not in chosen:
            chosen.append(p["url"])
    return chosen, [p["url"] for p in pages if p.get("final_status") == 200 and not p.get("redirect_hops")]
```
(`Counter` et `urlparse` sont déjà importés.)

- [ ] **Step 4 : tests verts** — `python3 -m unittest tests.unit.test_geo_echantillon -v` → `OK`.
Propre : 12 pages, 8 segments → toutes les pages restent échantillonnées. Cassé (après la tâche 9) : home, puis `profond`, `formations`, `catalogue`, `blog` (gabarits), puis `snippet` (G07), `contact` (G06), … : l'article `/blog/article-ok` (JSON-LD `Article` sans auteur) est analysé (G08).

- [ ] **Step 5 : commit** — fichiers : `geo_check.py`, `test_geo_echantillon.py` ; message :
```
fix(geo): échantillon par gabarit, les familles de pages avant les pages isolées

Un gabarit d'article pouvait être évincé par des pages uniques très liées
(G08 dépendait de l'échantillon, feuille de route §5).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 8 : rapports — sévérité des gains en octets, vrais échecs Lighthouse avec leur identifiant

**Files:**
- Create: `tests/unit/test_rapports.py`
- Modify: `…/scripts/rapport_brut.py`, `…/scripts/pagespeed.py`

**Interfaces:**
- Produces : `rapport_brut.severite_opportunite(ms, octets)` ; `pagespeed.audit_en_echec(audit)` ; chaque entrée de `echecs_autres_categories` devient `"Titre [id-audit]"` (les regex des matchers Lighthouse A01–A04, A06 portent sur le titre et restent valides).

- [ ] **Step 1 : tests qui échouent** — `tests/unit/test_rapports.py` :

```python
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
sys.path.insert(0, str(SCRIPTS))
import pagespeed  # noqa: E402
import rapport_brut  # noqa: E402


class TestSeveriteOpportunites(unittest.TestCase):
    def test_les_octets_comptent(self):
        self.assertEqual(rapport_brut.severite_opportunite(0, 6600000), "haute")
        self.assertEqual(rapport_brut.severite_opportunite(0, 300000), "moyenne")
        self.assertEqual(rapport_brut.severite_opportunite(1200, 0), "haute")
        self.assertEqual(rapport_brut.severite_opportunite(100, 50000), "basse")

    def test_six_mo_d_images_en_haute(self):  # constaté sur beta.illith.com le 2026-09-30
        with tempfile.TemporaryDirectory() as d:
            perf = pathlib.Path(d, "data/perf")
            perf.mkdir(parents=True)
            (perf / "pagespeed.json").write_text(json.dumps([{
                "url": "https://ex.fr/", "strategie": "mobile", "scores": {}, "metriques": {},
                "opportunites": [{"id": "image-delivery-insight", "titre": "Améliorer la diffusion des images",
                                  "gain_ms": 0, "gain_octets": 6600000, "exemples": []}],
                "echecs_autres_categories": {}}]), encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPTS / "rapport_brut.py"), d], check=True, capture_output=True, timeout=60)
            md = pathlib.Path(d, "RAPPORT-BRUT.md").read_text(encoding="utf-8")
        self.assertIn("### 🟧 Haute", md)
        haute = md.split("### 🟧 Haute", 1)[1].split("\n### ", 1)[0]
        self.assertIn("Améliorer la diffusion des images (gain estimé 6445 Ko", haute)


class TestEchecsLighthouse(unittest.TestCase):
    def test_seuls_les_vrais_echecs_avec_leur_id(self):
        lhr = {"categories": {"accessibility": {"auditRefs": [
                   {"id": "link-in-text-block", "weight": 1}, {"id": "label", "weight": 7},
                   {"id": "color-contrast", "weight": 7}, {"id": "info-x", "weight": 1}, {"id": "manuel", "weight": 0}]}},
               "audits": {
                   "link-in-text-block": {"score": 1, "scoreDisplayMode": "binary",
                                          "title": "Les liens sont identifiables sans se baser sur la couleur."},
                   "label": {"score": 0, "scoreDisplayMode": "binary",
                             "title": "Les éléments de formulaire ne sont pas associés à des libellés"},
                   "color-contrast": {"score": None, "scoreDisplayMode": "notApplicable", "title": "Contraste"},
                   "info-x": {"score": 0.5, "scoreDisplayMode": "informative", "title": "Information"},
                   "manuel": {"score": 0, "scoreDisplayMode": "manual", "title": "Vérification manuelle"}}}
        echecs = pagespeed.summarize_lhr(lhr)["echecs_autres_categories"]
        self.assertEqual(echecs["accessibility"], ["Les éléments de formulaire ne sont pas associés à des libellés [label]"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2 : vérifier l'échec** — `python3 -m unittest tests.unit.test_rapports -v` → `AttributeError: … severite_opportunite`, pas de section Haute, et l'audit informatif listé sans `[id]`.

- [ ] **Step 3 : implémenter.**

`rapport_brut.py`, après `ICON = {…}` :
```python


def severite_opportunite(ms, octets):
    """Sévérité d'un gain Lighthouse : le temps OU le poids économisé (6 Mo d'images = haute même sans ms estimées)."""
    ms, octets = ms or 0, octets or 0
    if ms >= 1000 or octets >= 1000000:
        return "haute"
    if ms >= 300 or octets >= 250000:
        return "moyenne"
    return "basse"
```
Remplacer
```python
            sev = "haute" if (o.get("gain_ms") or 0) >= 1000 else "moyenne" if (o.get("gain_ms") or 0) >= 300 else "basse"
            gain = f"{o['gain_ms']} ms" if o.get("gain_ms") else f"{int(o['gain_octets']) // 1024} Ko"
```
par :
```python
            sev = severite_opportunite(o.get("gain_ms"), o.get("gain_octets"))
            gain = " + ".join(g for g in (f"{o['gain_ms']} ms" if o.get("gain_ms") else "",
                                          f"{int(o['gain_octets']) // 1024} Ko" if o.get("gain_octets") else "") if g)
```

`pagespeed.py`, avant `def summarize_lhr(lhr):` :
```python
def audit_en_echec(a):
    """Échec réel seulement : binaire à 0, numérique < 0,9. Informatif, manuel, non applicable, erreur : jamais."""
    mode, score = a.get("scoreDisplayMode"), a.get("score")
    if mode in ("binary", None):
        return score == 0
    if mode in ("numeric", "metricSavings"):
        return score is not None and score < 0.9
    return False


```
Remplacer
```python
        fails[cat_id] = [audits[r["id"]].get("title", r["id"]) for r in refs
                         if r.get("weight", 0) > 0 and audits.get(r["id"], {}).get("score") not in (None, 1)]
```
par :
```python
        # titre + [id] : certains titres d'échec traduits se lisent comme un succès
        # (fr : « Les liens sont identifiables grâce à leur couleur. » = ÉCHEC de link-in-text-block)
        fails[cat_id] = ["{0} [{1}]".format(audits[r["id"]].get("title", r["id"]), r["id"]) for r in refs
                         if r.get("weight", 0) > 0 and audit_en_echec(audits.get(r["id"], {}))]
```

- [ ] **Step 4 : tests verts** — `python3 -m unittest tests.unit.test_rapports tests.unit.test_score -v` → `OK`. Aucun effet attendu sur le score (sorties du run 2 : tous les échecs listés sont binaires à 0 ; les matchers Lighthouse restent vrais sur le cassé, et le propre n'a plus d'échec après la tâche 9).

- [ ] **Step 5 : commit** — fichiers : `rapport_brut.py`, `pagespeed.py`, `test_rapports.py` ; message :
```
fix(rapports): gains en octets dans la sévérité, vrais échecs Lighthouse avec leur id

6,3 Mo d'images économisables sortaient en « basse » (sévérité par ms seules).
Les échecs listés excluent informatif/manuel et portent l'id de l'audit : le
libellé français d'échec de link-in-text-block se lit comme un succès.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 9 : cobayes — défauts masqués côté cassé, vrais défauts côté propre (S10, S21, G08 ; S06, A06)

**Files:**
- Modify: `tests/cobaye/casse/src/layouts/Base.astro`, `tests/cobaye/casse/astro.config.mjs`
- Create: `tests/cobaye/casse/src/pages/promo.astro`
- Modify: `tests/cobaye/propre/src/layouts/Base.astro`, `tests/cobaye/propre/src/pages/index.astro`

**Interfaces:**
- Produces (cassé) : canonicals sans slash final sur les pages prérendues (les pages `/profond/n` et `/blog/*` deviennent indexables : `deep_page` sur `/profond/4` et `/profond/5`, article dans l'échantillon GEO) ; `/promo` → **302** vers `/formations/no-code`.
- Produces (propre) : `/blog/article-casse` liée depuis l'accueil ; liens de liste du `<main>` hauts de 44 px.

- [ ] **Step 1 : canonical du cassé** — `casse/src/layouts/Base.astro`, remplacer
```astro
// Canonical https correcte ici (sinon aucune page ne serait « indexable » pour le crawler) ; S36 : garde ?tab=
const canonicalUrl = canonical ?? new URL(Astro.url.pathname + Astro.url.search, Astro.site).href;
```
par :
```astro
// Canonical https correcte ici (sinon aucune page ne serait « indexable » pour le crawler) ; S36 : garde ?tab=.
// Pages prérendues (format « directory ») : Astro.url.pathname finit par « / » ; sans ce retrait la canonical
// pointait vers /profond/1/ au lieu de /profond/1 et masquait S21 (profondeur) et G08 (article hors échantillon).
const chemin = Astro.url.pathname.length > 1 ? Astro.url.pathname.replace(/\/$/, '') : '/';
const canonicalUrl = canonical ?? new URL(chemin + Astro.url.search, Astro.site).href;
```

- [ ] **Step 2 : S10 servi en 302** — `casse/astro.config.mjs`, retirer la ligne
```js
    '/promo': { status: 302, destination: '/formations/no-code' }, // S10
```
et créer `casse/src/pages/promo.astro` :
```astro
---
export const prerender = false;
// S10 : redirection temporaire (302) pour une promotion devenue permanente.
// La forme `redirects: { '/promo': { status: 302, … } }` a été servie en 301 par Astro 7.3 + @astrojs/node (CI run 36722306289).
return Astro.redirect('/formations/no-code', 302);
---
```
(Doc : https://docs.astro.build/en/reference/api-reference/#redirect — ne pas retirer le lien `/promo` de l'accueil.)

- [ ] **Step 3 : S06 sur le propre** — `propre/src/pages/index.astro` : ajouter dans le front-matter, après `import { formations } from '../data/formations';` :
```astro
import { getCollection } from 'astro:content';
const articles = await getCollection('blog');
```
et, après la liste des formations (`<ul>{formations.map(…)}</ul>`), avant `</Base>` :
```astro
  <h2>Nos articles</h2>
  <ul>{articles.map((a) => <li><a href={`/blog/${a.id}`}>{a.data.titre}</a></li>)}</ul>
```

- [ ] **Step 4 : A06 sur le propre** — `propre/src/layouts/Base.astro`, dans `<style is:global>`, après `nav a, footer a { display: inline-block; padding: 12px; }` ajouter :
```css
      main li a { display: inline-block; padding: 12px 0; } /* cibles tactiles ≥ 44 px (listes de liens empilés) */
```

- [ ] **Step 5 : vérification locale légère** — `python3 -m unittest tests.unit.test_cobaye_statique -v` → `OK` (aucun changement de constat de code : `promo.astro` n'est pas une route dynamique, `Base.astro` du cassé ne lit pas `Astro.url.href`). **Pas de build Astro en local** : la syntaxe est validée par le job CI (`lancer.sh`). Si le build CI casse, consulter la doc Astro 7 et adapter la forme sans retirer le défaut.

- [ ] **Step 6 : commit** — fichiers : les 5 fichiers ci-dessus ; message :
```
test(cobaye): défauts masqués du cassé (S10, S21, G08) et vrais défauts du propre (S06, A06)

Cassé : canonical avec slash final sur les pages prérendues (masquait S21 et
G08) ; redirects { status: 302 } servi en 301 → page promo.astro en 302.
Propre : article du sitemap enfin lié ; liens de liste à 44 px (target-size).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 10 : cliquet de phase 1 — CI en `--phase 1`, seuils 100 % / 0 / 0

Les défauts S19, S35b et X06 gardent `"phase": 1` dans `verite-terrain.json` (ils décrivent quand leur détection est apparue) ; ils deviennent **requis** parce que le banc mesure désormais la phase 1 (`score.py --phase 1`) : 101 + 3 = **104** défauts requis.

**Files:**
- Modify: `.github/workflows/docker.yml`, `tests/cobaye/seuils.json`, `tests/cobaye/README.md`, `tests/unit/test_score.py`, `docs/cobaye-baseline.md`, `README.md`

- [ ] **Step 1 : test qui échoue** — `tests/unit/test_score.py`, avant `if __name__ == "__main__":` :

```python
class TestCliquetPhase1(unittest.TestCase):
    def test_banc_mesure_la_phase_1(self):
        ci = (RACINE / ".github/workflows/docker.yml").read_text(encoding="utf-8")
        self.assertIn("--phase 1", ci)
        verite = json.loads((RACINE / "tests/cobaye/verite-terrain.json").read_text(encoding="utf-8"))
        requis = {d["id"] for d in verite["defauts"] if d["matcher"]["type"] != "unitaire" and score._phase(d["phase"]) <= 1}
        self.assertTrue({"S19", "S35b", "X06"} <= requis)
        self.assertEqual(len(requis), 104)

    def test_seuils_au_maximum(self):
        seuils = json.loads((RACINE / "tests/cobaye/seuils.json").read_text(encoding="utf-8"))
        self.assertEqual(seuils["rappel_min_global"], 1.0)
        self.assertEqual(set(seuils["rappel_min_par_domaine"].values()), {1.0})
        self.assertEqual((seuils["faux_positifs_max"], seuils["inattendus_max"]), (0, 0))
```
Run : `python3 -m unittest tests.unit.test_score -v` → 2 échecs.

- [ ] **Step 2 : implémenter.**

`.github/workflows/docker.yml`, étape « Score » : `--phase 0` → `--phase 1`.
`tests/cobaye/README.md`, bloc de commandes : `--phase 0` → `--phase 1`.
`tests/cobaye/seuils.json` (valeurs cibles de la phase : la CI vérifie qu'elles sont atteintes ; le cliquet ne redescend jamais) :
```json
{
  "rappel_min_global": 1.0,
  "rappel_min_par_domaine": {"a11y": 1.0, "code": 1.0, "geo": 1.0, "http": 1.0, "perf": 1.0, "securite": 1.0, "seo": 1.0},
  "faux_positifs_max": 0,
  "inattendus_max": 0
}
```
Run : `python3 -m unittest discover -s tests/unit -t . -v` → `OK` (toute la suite, ≈ 1 min, sans réseau externe).

- [ ] **Step 3 : commit, push et mesure en CI**

```bash
git add .github/workflows/docker.yml tests/cobaye/seuils.json tests/cobaye/README.md tests/unit/test_score.py
git commit -m "test(cobaye): banc en phase 1, cliquet à 100 % de rappel, 0 faux positif, 0 inattendu

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push -u origin phase1/detection
gh pr create --draft --base phase0/execution --title "Phase 1 : détection à 100 % sur le cobaye" --body "Plan : .superpowers/sdd/2026-09-30-03-phase1-detection.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```
Lire le résumé du job « Banc d'essai cobaye » (`gh run view <id>` ; artefact `audits-cobaye` si besoin, **pas de Docker local**). Attendu : **Rappel global 104/104 (100 %) · faux positifs : 0 · inattendus : 0**, verdict ✅.
Si un défaut reste raté ou un faux positif apparaît : lire la sortie brute dans l'artefact, revenir à la tâche concernée (nouveau commit `fix(…)` sur la même branche, avec test), **ne jamais baisser un seuil ni élargir un matcher**.

- [ ] **Step 4 : documenter la mesure** — `docs/cobaye-baseline.md` : ajouter en fin de fichier une section `## Phase 1 (AAAA-MM-JJ, commit <sha>, run <id>)` avec le tableau par domaine copié du résumé CI et la liste des corrections (tableau « Causes racines » ci-dessus, une ligne par défaut). `README.md` : badge `rappel%20cobaye-100%25-brightgreen` et phrase « Score actuel : **100 % des défauts connus détectés (phase 1), 0 faux positif** ».
```bash
git add docs/cobaye-baseline.md README.md
git commit -m "docs(cobaye): mesure de la phase 1 (100 %, 0 faux positif)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```
Ce commit documentaire complète la tâche 10 (données issues de la CI, connues seulement après le push du step 3).

---

## Hors périmètre (reporté)

- « Résultat d'une étape vide affiché en ✅ » (feuille de route §5) : déjà traité en phase 0 (validateurs `valid_crawl`, `valid_geo`, `valid_perf` de `collect_all.sh`, collecte stricte de `score.py`).
- G11 en rendu réel, R01, R02, E01, D01 : phase 2.
- Pages légales du propre au texte générique (minor différé phase 0) : aucun détecteur concerné.

## Self-review (fait)

- **Couverture** : les 11 ratés (H06, S03, S04, S10, S21, S38, G08, C10, C12, X02, A05), les 2 faux positifs (S06, A06), l'inattendu (xmlns), les 3 matchers sans producteur (S19, S35b, X06) et les problèmes connus (C07, rapport_brut, pagespeed, elif du sitemap, regex robots, `_matcher_fp`) ont chacun une cause citée (fichier:ligne, sortie CI) et une tâche.
- **Type de correction justifié** : détecteur quand la sortie réelle ne contient pas le signal alors que le défaut est servi (H06, S03, S04, S38, S19, S35b, X02, X06, C10, C12, A05, xmlns, C07) ; cobaye quand le défaut n'est pas servi tel que prévu (S10 servi en 301) ou masqué par un défaut accidentel (S21, G08 : canonical avec slash) ; cobaye propre quand le « faux positif » est un vrai défaut du propre (S06, A06). Un seul matcher change (A05), parce que son détecteur change : l'audit Lighthouse `label` est réussi par construction sur un champ à placeholder.
- **Zéro faux positif** : chaque test de détecteur a sa variante « propre » (tâches 1-8) ; le propre a été vérifié sur les sorties du run 2 pour chaque nouvelle règle (sitemap https sans redirection, canonicals auto-référentes, champ labellisé, `/_astro/` immuables, `.map` en 404, `/_image` en 403, `/formations/zz` en 404, aucune Haute dans le scan de code).
- **Tests déjà prototypés** : le code des tâches 1 à 8 a été rejoué sur une copie de travail de `350b7c0` : chaque nouveau test est rouge avant la correction (messages cités aux steps « vérifier l'échec »), vert après ; suite complète `discover` = 59 tests OK en ≈ 30 s, sans réseau externe ; 104 défauts requis en phase 1 vérifiés. Non rejouables en local (Astro/Docker) : tâche 9 et la mesure CI de la tâche 10.
- **Contraintes** : stdlib uniquement ; bash sans extension GNU (sed/awk/grep -E portables) ; aucun Docker/Chrome/npm local ; une branche, un commit par tâche (+ un commit documentaire en fin de tâche 10).
- **Noms cohérents** : `SiteLocal`, `ASSETS_RX`, `canon_targets`, `champs_sans_libelle`, `form_no_label`, `sans_commentaires`, `NAMESPACES_XML`, `AUDIT_IMAGE_DISTANTE`, `severite_opportunite`, `audit_en_echec` ; textes produits = regex des matchers (`asset hashé Astro`, `soft 404.*/formations/`, `\.map HTTP 200`, `proxy d'images ouvert`, `depuis l'origine de la requête`, `sans security\.allowedDomains`, `Articles sans auteur`).
