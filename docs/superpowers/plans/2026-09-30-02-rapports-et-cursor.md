# Rapports HTML/PDF, historique et compatibilité Cursor — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chaque audit produit une page web autonome (`RAPPORT.html`) et un PDF A4 (`RAPPORT.pdf`) avec les résultats réels, une page d'historique par site montre l'évolution, et le plugin s'installe et fonctionne dans Cursor comme dans Claude Code.

**Architecture:** Les signaux aujourd'hui calculés dans `rapport_brut.py` sont extraits dans un module partagé `signaux.py`. `rapport_html.py` en fait une page HTML autonome (CSS et graphiques SVG en ligne, aucun appel réseau, tout le texte échappé), en y intégrant le rapport priorisé `RAPPORT-AUDIT.md` quand l'agent l'a écrit. `rapport_pdf.sh` imprime cette page en PDF avec le Chrome headless déjà utilisé par Lighthouse. `historique.py` régénère `<dossier du site>/index.html` à partir de tous les audits datés. Cursor : manifestes `.cursor-plugin/` à côté de ceux de Claude Code, même dossier `skills/`.

**Tech Stack:** Python 3.9+ (stdlib), Bash, Chrome/Chromium headless (`--print-to-pdf`), GitHub Actions, formats de plugin Claude Code et Cursor.

**Spec:** demande utilisateur du 2026-09-30 (« un PDF complet avec l'audit complet du site, une page web avec les résultats à jour et réels », « le plugin doit être validé aussi pour Cursor ») + feuille de route `2026-09-30-00-feuille-de-route.md` §5 phase 4 (rapport HTML visuel) et §3 (contraintes). Docs Cursor vérifiées le 2026-09-30 : https://cursor.com/docs/reference/plugins et https://cursor.com/docs/skills.

## Global Constraints

- Python ≥ 3.9, bibliothèque standard uniquement ; tests `python3 -m unittest discover -s tests/unit -t . -v`.
- **Mac de dev 16 Go (a planté le 2026-09-30)** : aucune génération de PDF, aucun Chrome, docker ni build en local pendant l'implémentation. Les tests qui lancent Chrome sont sautés sauf si `RUN_CHROME_TESTS=1` (défini en CI).
- **Sécurité** : tout texte venant du site audité (titres, URL, extraits) est échappé avec `html.escape` avant insertion dans le HTML. Aucun JavaScript dans les rapports générés. Aucune ressource externe (polices, CDN, images distantes).
- Rapport autonome : un seul fichier HTML, lisible hors ligne, imprimable en A4 (`@page { size: A4; margin: 14mm }`), clair et sombre (`prefers-color-scheme`).
- Notes : barème de `references/notation.md` (100 − 20 × critiques − 10 × hautes − 4 × moyennes − 1 × basse, plancher 0, lettres A-E) appliqué aux **signaux bruts**, affiché comme « note indicative (signaux automatiques) » ; si `RAPPORT-AUDIT.md` existe, ses notes font foi et le rapport le dit.
- Cursor : manifeste `.cursor-plugin/plugin.json` (champ requis `name` en kebab-case ; optionnels `description`, `version`, `author{name,email}`), `.cursor-plugin/marketplace.json` à la racine (`name`, `owner{name}`, `plugins[{name, source, description}]`) ; skills découverts dans `skills/<nom>/SKILL.md`, `name` = nom du dossier, minuscules, chiffres et tirets.
- Une branche `feat/rapports-cursor` (depuis `phase0/execution`), un commit par tâche, une PR à la fin. Commits terminés par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Structure des fichiers

```
plugins/audit-site-astro/skills/audit-complet/scripts/
  signaux.py        (nouveau) collecte des signaux à partir de data/ — partagé
  rapport_brut.py   (modifié) utilise signaux.py, sortie inchangée
  rapport_html.py   (nouveau) RAPPORT.html autonome
  rapport_pdf.sh    (nouveau) RAPPORT.pdf via Chrome headless
  historique.py     (nouveau) index.html de l'historique d'un site
  collect_all.sh    (modifié) étapes « rapport html », « pdf », « historique »
plugins/audit-site-astro/.cursor-plugin/plugin.json   (nouveau)
.cursor-plugin/marketplace.json                        (nouveau)
tests/unit/
  fixtures/audit-exemple/data/…   jeu de données d'audit réduit, anonymisé
  test_signaux.py, test_rapport_html.py, test_rapport_pdf.py, test_historique.py, test_manifestes.py
```

---

### Task 1 : module partagé `signaux.py` (refactor sans changement de sortie)

**Files:**
- Create: `…/scripts/signaux.py`, `tests/unit/fixtures/audit-exemple/data/{crawl/issues.json,crawl/pages.json,geo/geo.json,perf/pagespeed.json,http/http-checks.md,securite/security-probe.md,code/code-scan.json}`, `tests/unit/test_signaux.py`
- Modify: `…/scripts/rapport_brut.py`

**Interfaces:**
- Produces : `signaux.collecter(audit: Path) -> list[dict]`, chaque dict `{"severite": str, "domaine": str, "texte": str, "exemples": list[str]}`, trié par sévérité (critique→info) puis domaine ; `signaux.ORDRE` (dict sévérité→rang) ; `signaux.charger(p) -> obj|None` ; `signaux.lighthouse(audit) -> list[dict]` (entrées de `pagespeed.json` sans `erreur`) ; `signaux.meta_crawl(audit) -> dict` (`meta` de `pages.json` ou `{}`).

- [ ] **Step 1 : fixture.** Créer un jeu de données réduit et **anonymisé** (hôte `exemple.test`, aucune donnée réelle) couvrant chaque source lue par `rapport_brut.py` : 3 issues de crawl (une `haute` avec exemples dict, une `moyenne`, une `basse`), 2 signaux GEO, 2 constats de code (avec `piste` et `ou`), 2 entrées `pagespeed.json` (mobile/desktop, avec `opportunites` dont une à gain_ms ≥ 1000 et `echecs_autres_categories.accessibility`), une ligne `❌` et une ligne `| … ⚠️ …` dans `http/http-checks.md`, une ligne `❌` dans `securite/security-probe.md`, et un `pages.json` minimal avec `meta.start_url`.
- [ ] **Step 2 : test d'égalité (échoue).** `tests/unit/test_signaux.py` :
```python
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
FIXTURE = RACINE / "tests/unit/fixtures/audit-exemple"
sys.path.insert(0, str(SCRIPTS))


class TestSignaux(unittest.TestCase):
    def test_collecter_trie_et_type(self):
        import signaux
        s = signaux.collecter(FIXTURE)
        self.assertTrue(s)
        rangs = [signaux.ORDRE[x["severite"]] for x in s]
        self.assertEqual(rangs, sorted(rangs))
        for x in s:
            self.assertEqual(set(x), {"severite", "domaine", "texte", "exemples"})

    def test_rapport_brut_inchange(self):
        """La sortie de rapport_brut.py doit être identique avant/après le refactor (référence commitée)."""
        with tempfile.TemporaryDirectory() as t:
            copie = pathlib.Path(t, "audit")
            shutil.copytree(FIXTURE, copie)
            subprocess.run([sys.executable, str(SCRIPTS / "rapport_brut.py"), str(copie)], check=True, capture_output=True)
            obtenu = (copie / "RAPPORT-BRUT.md").read_text(encoding="utf-8")
        attendu = (FIXTURE / "RAPPORT-BRUT.attendu.md").read_text(encoding="utf-8")
        self.assertEqual(obtenu, attendu)


if __name__ == "__main__":
    unittest.main()
```
- [ ] **Step 3 : référence.** AVANT de modifier `rapport_brut.py`, générer la référence avec la version actuelle : copier la fixture dans un dossier temporaire, lancer `rapport_brut.py`, copier le `RAPPORT-BRUT.md` produit en `tests/unit/fixtures/audit-exemple/RAPPORT-BRUT.attendu.md`. Vérifier `test_collecter_trie_et_type` en échec (module absent) et `test_rapport_brut_inchange` en succès.
- [ ] **Step 4 : implémenter** `signaux.py` en déplaçant **telle quelle** la logique de collecte de `rapport_brut.main()` (crawl, geo, code, perf, textes http/sécurité) dans `collecter()`, qui retourne des dicts au lieu de tuples ; déplacer `load`→`charger`, `ex_str`, `ORDER`→`ORDRE`. `rapport_brut.py` importe `signaux` (même dossier, `sys.path.insert(0, dirname(__file__))`) et ne garde que la mise en forme Markdown.
- [ ] **Step 5 : tests verts** (`python3 -m unittest tests.unit.test_signaux -v` puis la suite complète) et **commit** `refactor(rapport): signaux partagés entre rapports brut, HTML et PDF`.

---

### Task 2 : `rapport_html.py` — page web autonome

**Files:**
- Create: `…/scripts/rapport_html.py`, `tests/unit/test_rapport_html.py`

**Interfaces:**
- Consumes : `signaux.collecter`, `signaux.lighthouse`, `signaux.meta_crawl`, `signaux.ORDRE`.
- Produces : CLI `python3 rapport_html.py DOSSIER_AUDIT [--sortie FICHIER]` (défaut `DOSSIER_AUDIT/RAPPORT.html`) ; fonctions `notes_par_domaine(signaux: list) -> dict[str, dict]` (`{"note": int, "lettre": str, "critique": n, "haute": n, "moyenne": n, "basse": n}`), `markdown_vers_html(md: str) -> str`, `generer(audit: Path) -> str` (HTML complet).

**Contenu attendu de la page (dans cet ordre) :**
1. En-tête : « Audit du site — <start_url> », date (nom du dossier ou date du jour), mention « Rapport généré par audit-site-astro vX.Y.Z ».
2. **Synthèse** : note globale (moyenne pondérée des domaines présents, poids de `notation.md` ; domaines absents exclus et poids renormalisés) + tableau par domaine (note, lettre, nombre de constats par sévérité) + barres SVG horizontales (une par domaine, largeur = note).
3. **Lighthouse** : tableau page × mode (perf, a11y, BP, SEO, LCP, CLS, TBT) avec couleur de score (≥ 90 vert, 50-89 orange, < 50 rouge) ; données terrain CrUX si présentes.
4. **Rapport priorisé** : si `DOSSIER_AUDIT/RAPPORT-AUDIT.md` existe, son contenu converti par `markdown_vers_html` (titres, listes, tableaux, gras, code en ligne, blocs de code, liens) et la mention « notes du rapport priorisé : elles font foi ». Sinon, un encadré « Rapport priorisé non encore rédigé : lancer le skill audit-complet dans Claude Code ou Cursor ».
5. **Top 15 des signaux** (critique → basse) puis **tous les signaux par domaine** avec leurs exemples.
6. **Annexes** : `data/COLLECTE.md` rendu en HTML (statut des étapes) et liste des fichiers de données.

**Règles de rendu :** tout texte dynamique passe par `html.escape` ; pas de `<script>` ; CSS en ligne avec variables (`--fond`, `--texte`, `--accent`, `--critique`, `--haute`, `--moyenne`, `--basse`), mode sombre via `@media (prefers-color-scheme: dark)`, impression `@media print` (fond blanc, pas d'ombres, `break-inside: avoid` sur tableaux et cartes, `@page { size: A4; margin: 14mm }`) ; police système (`system-ui`) ; largeur max 1100 px ; tableaux défilants horizontalement sur mobile.

- [ ] **Step 1 : tests (échouent)** — `tests/unit/test_rapport_html.py` :
```python
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

RACINE = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = RACINE / "plugins/audit-site-astro/skills/audit-complet/scripts"
FIXTURE = RACINE / "tests/unit/fixtures/audit-exemple"
sys.path.insert(0, str(SCRIPTS))


class TestRapportHtml(unittest.TestCase):
    def test_notes_par_domaine_bareme(self):
        import rapport_html
        s = [{"severite": "haute", "domaine": "Performance", "texte": "x", "exemples": []},
             {"severite": "moyenne", "domaine": "Performance", "texte": "y", "exemples": []},
             {"severite": "critique", "domaine": "Sécurité", "texte": "z", "exemples": []}]
        n = rapport_html.notes_par_domaine(s)
        self.assertEqual(n["Performance"]["note"], 86)
        self.assertEqual(n["Performance"]["lettre"], "B")
        self.assertEqual(n["Sécurité"]["note"], 80)

    def test_markdown_minimal(self):
        import rapport_html
        h = rapport_html.markdown_vers_html("# Titre\n\n- **gras** et `code`\n\n| A | B |\n|---|---|\n| 1 | <b>2</b> |\n")
        self.assertIn("<h1>Titre</h1>", h)
        self.assertIn("<strong>gras</strong>", h)
        self.assertIn("<code>code</code>", h)
        self.assertIn("<table>", h)
        self.assertIn("&lt;b&gt;2&lt;/b&gt;", h)  # HTML brut échappé

    def test_page_complete_sans_script_ni_ressource_externe(self):
        with tempfile.TemporaryDirectory() as t:
            copie = pathlib.Path(t, "audit")
            shutil.copytree(FIXTURE, copie)
            subprocess.run([sys.executable, str(SCRIPTS / "rapport_html.py"), str(copie)], check=True, capture_output=True)
            h = (copie / "RAPPORT.html").read_text(encoding="utf-8")
        self.assertTrue(h.startswith("<!doctype html>"))
        for section in ("Synthèse", "Lighthouse", "Rapport priorisé", "Signaux", "Annexes"):
            self.assertIn(section, h)
        self.assertNotIn("<script", h.lower())
        self.assertNotRegex(h, r'(src|href)="https?://(?!exemple\.test)')
        self.assertIn("@page", h)
        self.assertIn("prefers-color-scheme", h)

    def test_echappement_des_donnees_du_site(self):
        with tempfile.TemporaryDirectory() as t:
            copie = pathlib.Path(t, "audit")
            shutil.copytree(FIXTURE, copie)
            issues = copie / "data/crawl/issues.json"
            issues.write_text(issues.read_text(encoding="utf-8").replace("exemple.test", 'exemple.test/"><img src=x onerror=alert(1)>'), encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPTS / "rapport_html.py"), str(copie)], check=True, capture_output=True)
            h = (copie / "RAPPORT.html").read_text(encoding="utf-8")
        self.assertNotIn("<img src=x", h)
        self.assertIn("&lt;img src=x", h)

    def test_rapport_priorise_integre(self):
        with tempfile.TemporaryDirectory() as t:
            copie = pathlib.Path(t, "audit")
            shutil.copytree(FIXTURE, copie)
            (copie / "RAPPORT-AUDIT.md").write_text("# Audit du site\n\n### [PERF-001] Compression absente\n", encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPTS / "rapport_html.py"), str(copie)], check=True, capture_output=True)
            h = (copie / "RAPPORT.html").read_text(encoding="utf-8")
        self.assertIn("[PERF-001] Compression absente", h)
        self.assertIn("font foi", h)


if __name__ == "__main__":
    unittest.main()
```
Barème vérifié à la main : Performance = 100 − 10 − 4 = 86 → B (75-89) ; Sécurité = 100 − 20 = 80.
- [ ] **Step 2 : implémenter** `rapport_html.py` selon le contenu et les règles ci-dessus (≈ 300-400 lignes ; si le fichier dépasse 450 lignes, extraire le CSS dans une constante en tête de fichier plutôt que de découper en modules). Domaines et poids : Performance 20, SEO technique 20, Contenu 15, GEO / IA 15, Sécurité 12, Code 10, Accessibilité 8 ; les domaines de signaux hors de cette liste (« Serveur / HTTP », « Bonnes pratiques ») sont affichés mais comptés avec Performance (HTTP) et Code (bonnes pratiques).
- [ ] **Step 3 : tests verts + contrôle visuel sans navigateur** : ouvrir le HTML produit sur la fixture n'est pas possible sans Chrome ; vérifier à la place la taille (< 400 Ko), l'absence de `<script`, et relire le fichier. **Commit** `feat(rapport): page web autonome RAPPORT.html (notes, Lighthouse, rapport priorisé, signaux)`.

---

### Task 3 : PDF et intégration à la collecte

**Files:**
- Create: `…/scripts/rapport_pdf.sh`, `tests/unit/test_rapport_pdf.py`
- Modify: `…/scripts/collect_all.sh`, `docker/entrypoint.sh`, `.github/workflows/docker.yml` (job `lint` : `RUN_CHROME_TESTS=1` n'y a pas Chrome → le test PDF tourne dans le job `cobaye`, voir step 4)

**Interfaces:**
- Produces : `bash rapport_pdf.sh DOSSIER_AUDIT` → `DOSSIER_AUDIT/RAPPORT.pdf` (code 0), code 2 si Chrome introuvable, code 3 si RAM insuffisante ; `collect_all.sh` gagne les lignes `| rapport html |`, `| pdf |` (⏭️ si `SKIP_PDF=1` ou `SKIP_LIGHTHOUSE=1`), `| historique |` (tâche 4).

- [ ] **Step 1 : `rapport_pdf.sh`**
```bash
#!/usr/bin/env bash
# rapport_pdf.sh — Imprime DOSSIER_AUDIT/RAPPORT.html en DOSSIER_AUDIT/RAPPORT.pdf (A4) avec Chrome headless.
# Codes : 0 ok, 1 échec d'impression, 2 Chrome introuvable, 3 RAM insuffisante (MIN_FREE_MB, défaut 800).
set -u
AUDIT="${1:?usage: rapport_pdf.sh DOSSIER_AUDIT}"
HTML="$AUDIT/RAPPORT.html"
PDF="$AUDIT/RAPPORT.pdf"
[ -f "$HTML" ] || python3 "$(cd "$(dirname "$0")" && pwd)/rapport_html.py" "$AUDIT" || exit 1

if [ -z "${CHROME_PATH:-}" ]; then
  for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
           "$(command -v chromium 2>/dev/null)" "$(command -v chromium-browser 2>/dev/null)" \
           "$(command -v google-chrome 2>/dev/null)" "$(command -v google-chrome-stable 2>/dev/null)"; do
    [ -n "$c" ] && [ -x "$c" ] && { CHROME_PATH="$c"; break; }
  done
fi
[ -z "${CHROME_PATH:-}" ] && { echo "❌ Chrome introuvable (CHROME_PATH)"; exit 2; }

free_mb() {
  if [ -r /proc/meminfo ]; then awk '/MemAvailable/ {print int($2 / 1024)}' /proc/meminfo
  elif command -v vm_stat >/dev/null 2>&1; then
    local ps; ps=$(sysctl -n hw.pagesize 2>/dev/null || echo 4096)
    vm_stat | awk -v ps="$ps" '/Pages free/ {gsub(/\./, "", $3); f=$3} /Pages inactive/ {gsub(/\./, "", $3); i=$3}
                               /Pages speculative/ {gsub(/\./, "", $3); s=$3} END {print int((f + i + s) * ps / 1048576)}'
  else echo 99999; fi
}
[ "$(free_mb)" -lt "${MIN_FREE_MB:-800}" ] && { echo "⛔ RAM insuffisante pour imprimer le PDF ($(free_mb) Mo)"; exit 3; }

PROFIL=$(mktemp -d)
trap 'rm -rf "$PROFIL"' EXIT
"$CHROME_PATH" --headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage --disable-extensions \
  --no-first-run --user-data-dir="$PROFIL" --no-pdf-header-footer --print-to-pdf="$PDF" \
  "file://$(cd "$AUDIT" && pwd)/RAPPORT.html" >/dev/null 2>&1
[ -s "$PDF" ] && head -c 5 "$PDF" | grep -q '%PDF-' && { echo "✅ $PDF"; exit 0; }
echo "❌ impression PDF échouée"; exit 1
```
- [ ] **Step 2 : test** `tests/unit/test_rapport_pdf.py` : `@unittest.skipUnless(os.environ.get("RUN_CHROME_TESTS") == "1", "Chrome requis (CI)")` ; copie la fixture, lance `rapport_pdf.sh`, vérifie code 0, fichier commençant par `%PDF-` et > 20 Ko. Un second test, toujours actif, vérifie le code 2 avec `CHROME_PATH=/inexistant` et `PATH` réduit à `/usr/bin:/bin`.
- [ ] **Step 3 : `collect_all.sh`** — après la ligne `rapport brut`, ajouter :
```bash
step "rapport html" "$AUDIT/RAPPORT.html" valid_aucun python3 "$DIR/rapport_html.py" "$AUDIT"
if [ "${SKIP_PDF:-0}" = "1" ] || [ "${SKIP_LIGHTHOUSE:-0}" = "1" ]; then
  echo "| pdf | ⏭️ ignoré | | |" >> "$LOG"
else
  step pdf "$AUDIT/RAPPORT.pdf" valid_aucun bash "$DIR/rapport_pdf.sh" "$AUDIT"
fi
```
(la ligne `rapport brut` reste ; `step` exige un nom sans espace pour le fichier de log : utiliser `rapport-html`). Mettre à jour l'en-tête (variables `SKIP_PDF`) et le test de collecte existant (`test_site_sans_html…` doit voir `| pdf | ⏭️`).
- [ ] **Step 4 : CI** — dans le job `cobaye`, après « Score », ajouter l'étape `RUN_CHROME_TESTS=1 CHROME_PATH=$(command -v google-chrome) python3 -m unittest tests.unit.test_rapport_pdf -v` (Chrome est préinstallé sur ubuntu-latest).
- [ ] **Step 5 : entrypoint Docker** — afficher aussi « 🌐 Page web : audits/<hôte>/<date>/RAPPORT.html » et « 📕 PDF : …/RAPPORT.pdf » (sauf code 2). **Commit** `feat(rapport): PDF A4 via Chrome headless et intégration à la collecte`.

---

### Task 4 : page d'historique par site

**Files:**
- Create: `…/scripts/historique.py`, `tests/unit/test_historique.py`
- Modify: `…/scripts/collect_all.sh` (dernière étape `historique`)

**Interfaces:**
- Consumes : `rapport_html.notes_par_domaine`, `signaux.collecter`, `signaux.lighthouse`.
- Produces : `python3 historique.py DOSSIER_SITE` (ex. `~/audits-site/beta.exemple.fr`) → `DOSSIER_SITE/index.html` ; fonction `audits(dossier_site: Path) -> list[dict]` triée par date (`{"date": "2026-09-30", "chemin": Path, "note_globale": int, "notes": dict, "perf_mobile": int|None}`), en ne retenant que les sous-dossiers `AAAA-MM-JJ` contenant `data/`.

Page : titre « Historique des audits — <hôte> », tableau (date, note globale, notes par domaine, perf mobile médiane, liens `RAPPORT.html` / `RAPPORT.pdf` relatifs quand ils existent), courbe SVG de la note globale dans le temps (polyline, points et étiquettes), écart avec l'audit précédent (▲/▼ + valeur). Mêmes règles que la tâche 2 : autonome, sans script, texte échappé, sombre/clair, imprimable.

- [ ] **Step 1 : tests (échouent)** — créer deux audits datés à partir de la fixture (`2026-09-01`, `2026-09-30`, le second avec une issue `haute` en moins) + un dossier parasite `notes/` ; vérifier : `audits()` renvoie 2 entrées triées, la note du second > premier, `index.html` contient les deux dates, un `<polyline`, un lien `2026-09-30/RAPPORT.html` seulement si le fichier existe, aucun `<script`.
- [ ] **Step 2 : implémenter**, **Step 3 : collecte** — dans `collect_all.sh`, en dernier : `step historique "$(dirname "$AUDIT")/index.html" valid_aucun python3 "$DIR/historique.py" "$(dirname "$AUDIT")"`. **Commit** `feat(rapport): page d'historique des audits par site`.

---

### Task 5 : compatibilité Cursor

**Files:**
- Create: `plugins/audit-site-astro/.cursor-plugin/plugin.json`, `.cursor-plugin/marketplace.json`, `tests/unit/test_manifestes.py`
- Modify: `plugins/audit-site-astro/skills/audit-complet/SKILL.md` et les 7 skills de domaine (repli pour trouver les scripts), `README.md`

- [ ] **Step 1 : manifestes**

`plugins/audit-site-astro/.cursor-plugin/plugin.json` :
```json
{
  "name": "audit-site-astro",
  "description": "Audit A→Z de sites Astro (+ Convex) : performance & Core Web Vitals, SEO technique, contenu, GEO (ChatGPT, Perplexity, Claude, Gemini, AI Overviews), code, sécurité, accessibilité — rapport priorisé, page web et PDF.",
  "version": "1.2.0",
  "author": { "name": "ILLITH" }
}
```
`.cursor-plugin/marketplace.json` :
```json
{
  "name": "audit-site-astro",
  "owner": { "name": "ILLITH" },
  "plugins": [
    {
      "name": "audit-site-astro",
      "source": "plugins/audit-site-astro",
      "description": "8 skills + scripts de collecte pour auditer un site Astro de A à Z : rapport priorisé, page web et PDF."
    }
  ]
}
```
Passer aussi `version` à `1.2.0` dans les deux manifestes Claude Code.
- [ ] **Step 2 : test** `tests/unit/test_manifestes.py` : les 4 manifestes sont du JSON valide ; `name` kebab-case (`^[a-z0-9][a-z0-9.-]*$`) ; `source` des deux marketplaces pointe vers un dossier existant contenant `skills/` ; mêmes `name` et `version` entre manifestes Claude et Cursor ; pour chaque `skills/*/SKILL.md` : frontmatter présent, `name` = nom du dossier et `^[a-z0-9-]+$`, `description` non vide et ≤ 1024 caractères.
- [ ] **Step 3 : scripts introuvables hors Claude Code.** Cursor n'annonce pas le dossier du skill comme Claude Code (« Base directory for this skill »). Dans `audit-complet/SKILL.md`, au §2, ajouter : « Si le chemin du skill n'est pas connu : `S=$(dirname "$(find ~/.cursor ~/.claude ~/.agents . -path '*audit-complet/scripts/collect_all.sh' 2>/dev/null | head -1)")` ». Dans chaque skill de domaine, à la ligne « Scripts : `../audit-complet/scripts/` », ajouter « (sinon, même commande `find` que dans audit-complet §2) ».
- [ ] **Step 4 : README** — section « Option 2 bis : Cursor » : (a) Customize → Plugins → *From GitHub repository* → `https://github.com/ohvignas/audit-site-astro` ; (b) ou copie des skills : `git clone https://github.com/ohvignas/audit-site-astro ~/.audit-site-astro && mkdir -p ~/.cursor/skills && cp -R ~/.audit-site-astro/plugins/audit-site-astro/skills/* ~/.cursor/skills/` ; invocation `/audit-complet` ou en langage naturel. Mentionner la limite connue : le CLI `cursor-agent` ne charge pas les skills des plugins installés depuis le marketplace (bug signalé sur le forum Cursor), utiliser `--plugin-dir` ou la copie dans `~/.cursor/skills/`. Section « Rapports » : RAPPORT.html, RAPPORT.pdf, index.html d'historique.
- [ ] **Step 5 : tests + commit** `feat(cursor): manifestes Cursor, validation des manifestes et skills portables`.
- [ ] **Step 6 (contrôleur, léger) : validation réelle dans Cursor** — `cursor-agent --print --mode ask --plugin-dir plugins/audit-site-astro --trust "Liste les skills disponibles dont le nom commence par audit- et donne pour chacun sa description en une phrase."` (aucune écriture, aucun build) ; attendu : les 8 skills listés. Consigner la sortie dans la PR.

---

### Task 6 : documentation des skills

**Files:** Modify `audit-complet/SKILL.md` (§2 tableau des sorties, §5, §6), `README.md` (arborescence « Ce que vous obtenez »), `plugins/audit-site-astro/skills/audit-complet/references/format-constat.md` (rien si inchangé).

- [ ] **Step 1** : §5 « Rapport consolidé » — après l'écriture de `RAPPORT-AUDIT.md`, lancer `python3 "$S/rapport_html.py" "$AUDIT"` puis `bash "$S/rapport_pdf.sh" "$AUDIT"` (après vérification RAM) et `python3 "$S/historique.py" "$(dirname "$AUDIT")"` : la page web et le PDF intègrent alors le rapport priorisé. §6 « Restitution » : donner les chemins `RAPPORT.html`, `RAPPORT.pdf`, `index.html` ; dans Claude Code, proposer de publier la page (artefact privé) pour la partager.
- [ ] **Step 2** : README — arborescence avec `RAPPORT.html`, `RAPPORT.pdf`, `../index.html` ; ligne dans la FAQ « Comment partager le rapport ? » (envoyer le PDF, ou héberger `RAPPORT.html`, fichier autonome).
- [ ] **Step 3** : validation (`quick_validate` si disponible, tests unitaires) et **commit** `docs: rapports HTML/PDF et historique dans le skill et le README`.

## Self-review (fait)
- Couverture : PDF complet (T3 + T6 pour le rapport priorisé), page web avec résultats réels (T2), résultats à jour (T4 historique, régénéré à chaque audit), Cursor (T5 manifestes + validation réelle).
- Noms cohérents : `signaux.collecter/charger/lighthouse/meta_crawl/ORDRE`, `rapport_html.notes_par_domaine/markdown_vers_html/generer`, `historique.audits`.
- Écart assumé : `rapport_html.py` et `historique.py` sont spécifiés par contenu + tests plutôt que par code complet (mise en page et CSS relèvent du jugement) → implémenteur de niveau intermédiaire.
