# Optimisations Astro : référence vérifiée dans la documentation officielle

Vérifiée sur docs.astro.build le 2026-09-30 (Astro 7.3.x). **Avant de recommander une option, vérifier la version installée** (`node -p "require('./node_modules/astro/package.json').version"`). Une option absente de cette version = proposer la montée de version, jamais une config qui ne marchera pas. En cas de doute, relire la page de doc citée : Astro évolue vite.

## Images (guides/images, reference/modules/astro-assets)

| Élément | Version | À vérifier / recommander |
|---|---|---|
| `<Image>` / `<Picture>` d'`astro:assets` | 3.0 / 3.3 | Toute image de contenu doit passer par eux (sinon : pas de redimensionnement, pas de WebP/AVIF, pas de dimensions → CLS). Défauts : `format` webp, `loading="lazy"`, `decoding="async"`. |
| Emplacement | — | `src/` (optimisé) vs `public/` (« servi tel quel, sans aucun traitement »). Les images de `public/`, même dans `![]()` Markdown, ne sont **jamais** optimisées. |
| Images distantes (CMS, storage Convex) | 2.10 | À autoriser dans `image.domains` ou `image.remotePatterns` (`{ protocol, hostname, pathname, port }`), sinon non optimisées. `inferSize` (4.4) ou `inferRemoteSize()` (4.12) si les dimensions sont inconnues. |
| **Images responsives** | **5.10** | `image.layout` (global) ou prop `layout` : `constrained` \| `full-width` \| `fixed` \| `none` → `srcset` + `sizes` générés automatiquement. `image.responsiveStyles: true` ajoute les styles de redimensionnement (spécificité nulle). `image.breakpoints` règle les largeurs générées. Props `fit` / `position` (défauts `image.objectFit` = cover, `image.objectPosition` = center). |
| **`priority`** | **5.10** | Sur l'image LCP **uniquement** : `loading="eager"`, `decoding="sync"`, `fetchpriority="high"`. Plusieurs images `priority` se font concurrence. |
| `widths` / `densities` / `sizes` | 3.3 | Alternative manuelle au layout responsive. |
| `quality` | — | `low` \| `mid` \| `high` \| `max` ou 0-100. |
| `<Picture formats>` | 3.3 | Défaut `['webp']` : ajouter `'avif'` en premier. `fallbackFormat`, `pictureAttributes`. |
| `background` | 5.17 | Couleur d'aplatissement quand on passe d'un format transparent à un format opaque. |
| `getImage()` | 2.x | Images hors balise `<img>` (fonds CSS, og:image, JSON-LD). Mêmes options que `<Image>` sauf `alt`/`sizes`. |
| Collections de contenu | 2.x | Champs image avec le helper `image()` du schéma, pas `z.string()`. |
| Composants SVG | 5.7 | `import Logo from './logo.svg'` → SVG inline (attention à la taille du DOM s'il est répété). |
| `experimental.svgOptimizer: svgoOptimizer()` | 5.16 (expérimental) | SVGO au build (import depuis `astro/config`). |
| `image.service` | 2.1 | Défaut sharp. `passthroughImageService()` = **aucune optimisation**. |
| `image.dangerouslyProcessSVG` | 6.3 | Laisser à `false` sauf besoin réel. |
| Cache des images | 5.1 | Build : `node_modules/.astro` (`cacheDir`), revalidation ETag/Last-Modified des images distantes. **Rendu à la demande** : l'endpoint `/_image` (`image.endpoint`) transforme à la requête. Mesurer son TTFB deux fois (`http_checks.sh` §4 bis) ; s'il reste lent, prérendre la page ou mettre `/_image` en cache au proxy/CDN. |
| Composants de framework (React…) | — | `<Image>` inutilisable dans un `.tsx` : passer l'image optimisée depuis un `.astro` (slot / children / `getImage()`). |

## Rendu et cache

| Élément | Version | À vérifier / recommander |
|---|---|---|
| `output: 'static'` + `export const prerender = false` ciblé | — | La doc recommande le statique par défaut « tant que la plupart des pages ne sont pas dynamiques ». |
| **Cache de routes** : `cache: { provider: memoryCache() }`, `routeRules`, `Astro.cache.set({ maxAge, swr, tags, etag, lastModified })`, `cache.invalidate({ tags \| path })` | **7.0 (stable)** | Pour tout site en rendu à la demande. Fournisseurs d'adapter (expérimentaux) : `@astrojs/netlify/cache`, `@astrojs/vercel/cache`, `@astrojs/cloudflare/cache`. Pour Node : `memoryCache()` (en mémoire du processus). |
| En-têtes manuels | tous | `Astro.response.headers.set('Cache-Control', …)` si la version est < 7. |
| Server islands `server:defer` | 5.0 | Isoler les parties personnalisées (menu connecté, panier) pour prérendre ou cacher le reste. |
| Streaming HTML | — | Actif par défaut ; `experimentalDisableStreaming` (@astrojs/node 9.3) le coupe. |
| `@astrojs/node` | — | `/_astro/` servis en `public, max-age=31536000, immutable`. **La compression n'est pas mentionnée par la doc** : la mesurer (`http_checks.sh`) et la faire au proxy. `staticHeaders` (v10) pour les en-têtes des pages prérendues. |

## Chargement

| Élément | Version | À vérifier / recommander |
|---|---|---|
| `prefetch` (`prefetchAll`, `defaultStrategy` : hover \| tap \| viewport \| load) + `data-astro-prefetch` | 3.5 | Navigation interne quasi instantanée. |
| `experimental.clientPrerender` | 4.2 (expérimental) | Speculation Rules : prérendu dans le navigateur ; nécessite `prefetch`. |
| **API Fonts** : `fonts: [{ provider: fontProviders.google() \| fontsource() \| local() …, name, cssVariable, weights, styles, subsets }]` + `<Font cssVariable preload />` | **6.0 (stable)** | Auto-hébergement, preload, fallbacks optimisés (moins de CLS), fichiers dans `_astro/fonts` en cache long. Précharger seulement la police du texte au-dessus de la ligne de flottaison. |
| `build.inlineStylesheets` | 2.6 | `'auto'` (défaut, < 4 Ko inlinés) ; `'always'` gonfle chaque page HTML. |
| `compressHTML` | — | v7 : défaut `'jsx'`. |
| Îlots `client:*` | — | `load` \| `idle` \| `visible` \| `media` \| `only`. |

## SEO, proxy, sécurité

| Élément | Version | À vérifier / recommander |
|---|---|---|
| `site` | — | URL finale en https : source du sitemap, des canonicals et d'`Astro.site`. |
| **`security.allowedDomains`** | **5.14.2** | Derrière un proxy : sans lui, `X-Forwarded-Host` est ignoré et `Astro.url` reflète l'hôte interne (souvent http). `[{ hostname: 'domaine.fr', protocol: 'https' }]`. Construire les URL publiques avec `new URL(path, Astro.site)`. |
| `trailingSlash`, `build.format`, `redirects` | — | Cohérents avec le sitemap et les canonicals. |
| **`security.csp`** | **6.0 (stable)** | Balise meta CSP avec les hashes des scripts et styles ; `scriptDirective`, `styleDirective`, `directives`, `algorithm`. |
| `security.checkOrigin` | 4.9 | Actif par défaut (CSRF) : ne pas le désactiver. |
| `env.schema` / `astro:env` | 5.0 | `envField.string({ context: 'server', access: 'secret' })` : un secret ne peut plus fuir côté client. |
| `security.actionBodySizeLimit` / `serverIslandBodySizeLimit` | 5.18 / 6.0 | Limites de payload (1 Mo par défaut). |

## Notes de version à connaître

- **v7** : compilateur Rust (HTML invalide refusé), Vite 8, `compressHTML: 'jsx'` par défaut (les espaces entre éléments inline disparaissent : vérifier le rendu), Markdown via Sätteri (les plugins remark/rehype exigent `@astrojs/markdown-remark`), `src/fetch.ts` réservé, `@astrojs/db` retiré, cache de routes stable.
- **v6** : API Fonts et `security.csp` stables.
- **v5.10** : images responsives et `priority`.

Guides de migration : https://docs.astro.build/en/guides/upgrade-to/v6/ et /v7/ (une version majeure à la fois).
