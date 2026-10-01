# Rapport brut — https://exemple.test/

_Synthèse automatique des signaux collectés. Pour un rapport priorisé avec correctifs adaptés au code, lancer le skill **audit-complet** dans un agent (Claude Code…)._

**Signaux** : 🟧 haute 5 · 🟨 moyenne 5 · 🟦 basse 5

## Lighthouse

| Page | Mode | Perf | A11y | SEO | LCP | CLS | TBT |
|---|---|---|---|---|---|---|---|
| https://exemple.test/ | mobile | 62 | 88 | 100 | 4,1 s | 0,02 | 310 ms |
| https://exemple.test/ | desktop | 91 | 88 | 100 | 1,2 s | 0,01 | 20 ms |

## Signaux par sévérité

### 🟧 Haute

- **Performance** — Image d'en-tête non optimisée (<img> au lieu de <Image>) → utiliser astro:assets et <Image> avec width/height
  - `src/components/Hero.astro:12`
  - `src/pages/index.astro:30`
- **Performance** — Éliminer les ressources qui bloquent le rendu (gain estimé 1350 ms, mobile)
  - `https://exemple.test/_astro/styles.abc123.css`
- **SEO technique** — Liens internes cassés (404) — 2
  - `lien: https://exemple.test/ancienne-page`
  - `lien: https://exemple.test/promo-2020`
- **Serveur / HTTP** — Compression HTML · aucune (HTML décompressé : 42 Ko) · ❌ activer brotli/gzip (proxy, CDN ou middleware)
- **Sécurité** — /.git/config · ❌ EXPOSÉ (critique)

### 🟨 Moyenne

- **Accessibilité** — Lighthouse : Les liens n'ont pas de nom discernable
- **Accessibilité** — Lighthouse : Le contraste des couleurs est insuffisant
- **GEO / IA** — llms.txt absent : les assistants IA n'ont pas de résumé du site
- **Performance** — Réduire le JavaScript inutilisé (gain estimé 420 ms, mobile)
- **SEO technique** — Pages sans balise title — 1
  - `https://exemple.test/mentions-legales/`

### 🟦 Basse

- **GEO / IA** — Aucune donnée structurée Organization sur la page d'accueil
- **Performance** — Dimensionner correctement les images (gain estimé 84 Ko, mobile)
  - `https://exemple.test/img/hero.jpg`
- **SEO technique** — Pages avec plusieurs H1 — 3
  - `https://exemple.test/a/`
  - `https://exemple.test/b/`
  - `https://exemple.test/c/`
- **SEO technique** — Balise canonical absente du layout
  - `src/layouts/Base.astro:8`
- **Serveur / HTTP** — Server / X-Powered-By · nginx/1.24.0 / — · ⚠️ version exposée

## Données détaillées

- Collecte : `data/COLLECTE.md`
- Crawl : `data/crawl/summary.md`
- HTTP : `data/http/http-checks.md`
- GEO : `data/geo/geo-summary.md`
- Lighthouse : `data/perf/pagespeed-summary.md`
- Sécurité : `data/securite/security-probe.md`
- Code : `data/code/code-scan.md`
