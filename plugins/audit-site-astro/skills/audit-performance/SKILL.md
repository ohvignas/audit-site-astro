---
name: audit-performance
description: Audit de performance d'un site Astro (SSR Node ou statique, backend Convex possible) — Core Web Vitals (LCP, INP, CLS), Lighthouse mobile/desktop, TTFB et cache serveur/CDN, compression, hydratation des îlots (client:load/idle/visible), images (astro:assets, storage Convex), polices, JS tiers, poids du bundle — avec causes précises (fichier:ligne) et correctifs chiffrés. Utilise ce skill quand l'utilisateur trouve son site lent, veut améliorer son score PageSpeed/Lighthouse, ses Core Web Vitals, son temps de chargement mobile, ou demande « pourquoi mon site est lent », « optimise la vitesse », même sans parler d'Astro.
---

# Audit performance — Astro (+ Convex)

Scripts : `../audit-complet/scripts/` (relatif au dossier de ce skill). Format des constats : `../audit-complet/references/format-constat.md`. Sortie : `rapports/performance.md` dans le dossier d'audit.

## Données

Réutiliser `data/perf/`, `data/http/` et `data/code/` si `collect_all.sh` a tourné. Sinon :

```bash
S=<dossier du skill>/../audit-complet/scripts
bash $S/lighthouse_run.sh "$AUDIT/data/perf" https://site.fr/ https://site.fr/page-cle   # RUNS=3 pour la médiane
bash $S/http_checks.sh https://site.fr/ "$AUDIT/data/http"
python3 $S/astro_scan.py /chemin/projet --out "$AUDIT/data/code"      # BUILD : bash $S/project_checks.sh /chemin/projet "$AUDIT/data/code" --build
```

Seuils de référence (p75 des visiteurs réels, ou labo à défaut) : **LCP ≤ 2,5 s · INP ≤ 200 ms · CLS ≤ 0,1** ; TTFB ≤ 0,8 s (≤ 0,2 s si servi par cache/CDN). Lighthouse varie de ±5 à 10 points d'un passage à l'autre : raisonner sur les **métriques et les opportunités chiffrées**, pas sur le score seul.

## Méthode : partir de l'élément LCP et remonter

Le LCP est la métrique qui pèse le plus et elle a une cause identifiable. Pour chaque page mesurée, `pagespeed-summary.md` donne l'élément LCP. On décompose son temps :

1. **TTFB** (document) → serveur, cache, requêtes Convex au rendu.
2. **Découverte** : la ressource LCP est-elle dans le HTML initial ? (`<img>` avec `fetchpriority="high"` et sans `loading="lazy"` ; pas une image de fond CSS ni une image injectée par un îlot.)
3. **Téléchargement** : poids et format de l'image, compression, CDN.
4. **Rendu** : CSS bloquant, polices, JS qui retarde l'affichage.

Si l'élément LCP est un **texte (H1)** et que le LCP reste élevé : regarder le CSS bloquant, les polices (FOIT) et surtout le **TBT / thread principal** (JS d'îlots qui s'exécute tôt).

## Checklist

### A. Serveur, réseau, cache (`data/http/http-checks.md`)
- **Compression** : HTML, CSS, JS et SVG doivent sortir en `br` ou `gzip`. L'adapter `@astrojs/node` en mode standalone **ne compresse pas** : il faut le faire au proxy (Caddy `encode zstd gzip` ; nginx `gzip on` + `gzip_types` ; Traefik middleware `compress`) ou au CDN. C'est souvent le gain n°1 : Lighthouse le chiffre en Kio et en ms.
- **TTFB avec vs sans cache** : aucun écart + TTFB > 0,5 s = chaque page est rendue à la volée. Pistes, dans l'ordre :
  1. passer en `export const prerender = true` les pages qui ne dépendent ni de la requête (cookies, session, paramètres) ni de données qui changent à la minute ;
  2. **Astro ≥ 7 : cache de routes intégré** : `cache: { provider: memoryCache() }` + `routeRules: { '/blog/[...slug]': { maxAge: 300, swr: 60, tags: ['blog'] } }`, `Astro.cache.set(…)` dans les pages, `cache.invalidate({ tags })` au moment de publier (depuis l'admin ou une action Convex qui appelle un endpoint). Avant la v7 : `Cache-Control: public, s-maxage=…, stale-while-revalidate=…` via `Astro.response.headers` + un proxy/CDN qui cache ;
  3. isoler les morceaux personnalisés en **server islands** (`server:defer`) pour que le reste de la page soit prérendu ou mis en cache ;
  4. paralléliser les appels Convex au rendu (`Promise.all`) et vérifier leurs index.
- **Assets `/_astro/`** : hashés, donc `Cache-Control: public, max-age=31536000, immutable`. Les fichiers de `public/` ne sont pas hashés : cache plus court, ou versionnement.
- **HTTP/2 ou 3, TLS 1.3, un seul saut de redirection** vers l'URL canonique.
- Si l'utilisateur a accès au serveur : `uptime`, `free -m`, `nproc`, charge du process Node (`ps aux --sort=-%cpu | head`) et, si Convex est auto-hébergé, les ressources de ce conteneur.

### B. JavaScript et îlots (`code/code-scan.md`, opportunités Lighthouse)
- **`client:load`** : n'est justifié que pour un élément interactif visible et utile tout de suite (menu mobile, recherche en haut de page). Widget de chat, avis, carrousel, formulaire bas de page, bannière de consentement → `client:idle` ou `client:visible`. Un composant qui n'a aucune interaction → le convertir en composant `.astro` sans JS.
- **« JavaScript inutilisé »** et **chunks > 100 Ko gzip** : relier chaque gros fichier `/_astro/X.hash.js` à son îlot (le nom du chunk reprend souvent le composant, ex. `ChatBubble.*.js`). Pistes : hydratation plus tardive, `import()` dynamique à l'ouverture (ex. le chat ne charge son SDK qu'au clic), bibliothèques plus légères, plus de `client:only` inutiles.
- **TBT / thread principal** > 2 s sur mobile : lister les tâches longues (Lighthouse « long tasks ») et leurs scripts ; tiers compris.
- **Scripts tiers** (analytics, chat, vidéo) : après consentement, à l'interaction, façade pour YouTube et Vimeo (`lite-youtube`), Partytown pour les tags analytics.
- **DOM** > 1 500 nœuds : SVG inline répétés (icônes → sprite ou `<img>`), listes longues non paginées, menu desktop et mobile tous deux dans le DOM.

### C. Images (checklist complète, versions : `../audit-complet/references/astro-optimisations.md`)
Données : `code-scan.md` (config, balises, collections, Markdown) + `http-checks.md` §4 bis (mesure en ligne de `/_image` et des images prioritaires) + Lighthouse (« Dimensionnez correctement les images », « formats nouvelle génération », élément LCP).
- **Service d'images** : `passthroughImageService` = aucune optimisation (critique pour la perf si des images lourdes sont servies).
- **Images responsives** (Astro ≥ 5.10) : `image: { layout: 'constrained', responsiveStyles: true }` dans la config (ou la prop `layout` par image ; `full-width` pour les visuels pleine largeur) → `srcset` + `sizes` automatiques. Sans cela et sans `widths`/`sizes`, un mobile télécharge l'image desktop.
- **`priority`** (≥ 5.10) sur l'image LCP **et elle seule** (eager + `decoding="sync"` + `fetchpriority="high"`). Plusieurs images prioritaires (carrousel, logo) = constat : garder la seule vraiment visible en premier, et ne pas mettre le logo en priorité.
- **`<Picture formats={['avif', 'webp']}>`** pour les grands visuels ; `quality` (`mid` suffit souvent pour les photos).
- **Images de `public/`** (balises ou Markdown `![](/…)`) : jamais optimisées → `src/assets/` + import.
- **Collections de contenu** : champs image en `image()` et non `z.string()`.
- **`/_image` en rendu à la demande** : transformation sharp à chaque requête si rien ne cache. Si §4 bis montre un TTFB > 0,3 s aux deux appels : prérendre la page (les images sont alors générées au build), ou mettre `/_image` en cache au proxy/CDN (la réponse porte déjà `Cache-Control: public`). Le cache de routes (v7) ne remplace pas ce point.
- **`<img>` brut vs `<Image>`/`<Picture>`** (`astro_scan.py`) : sans `astro:assets`, pas de redimensionnement, pas d'AVIF/WebP, pas de `srcset`. Dans un composant React, passer l'image optimisée depuis le `.astro` parent (`getImage()` ou slot).
- **SVG** : beaucoup de composants SVG importés → `experimental.svgOptimizer: svgoOptimizer()` (≥ 5.16) ; un SVG inline répété (icônes dans une liste) gonfle le DOM.
- **Images servies depuis le storage Convex** (`/api/storage/…`) : c'est le fichier original. Lighthouse le montre sous « Dimensionnez correctement les images » et « formats nouvelle génération », souvent en Mo. Deux solutions :
  1. autoriser le domaine Convex dans `image.remotePatterns` (ou `image.domains`) et rendre ces images avec `<Image src={url} width height inferSize?>` / `getImage()`. Le service d'images d'Astro (sharp) les redimensionne en SSR via `/_image` ;
  2. générer des variantes redimensionnées en WebP/AVIF à l'upload (action Convex + sharp) et stocker plusieurs tailles.
  Vérifier la présence de `sharp` dans les dépendances de production pour l'adapter Node.
- **Image LCP** : `loading="eager"` + `fetchpriority="high"`, dimensions correctes pour le viewport mobile (pas une image de 1408 px pour un écran de 390 px sans `srcset`/`sizes`).
- **Images de `public/`** : pas optimisées par Astro. Les déplacer dans `src/assets/` (liste des plus lourdes dans `project-checks.md`).
- `width`/`height` ou `aspect-ratio` partout (CLS).

### D. CSS et polices
- **CSS bloquant** : un seul gros `BaseLayout.*.css`, c'est normal avec Tailwind. Vérifier qu'il reste < 50 Ko gzip. `build.inlineStylesheets: 'auto'` (défaut) inline les petites feuilles.
- **Polices** : auto-hébergées, woff2, `font-display: swap`, 1 ou 2 fichiers préchargés maximum (ceux du texte au-dessus de la ligne de flottaison), sous-ensemble latin. Astro ≥ 6 : **API Fonts** (`fonts: [{ provider: fontProviders.google(), name: 'Inter', cssVariable: '--font-inter', weights: [400, 700], subsets: ['latin'] }]` + `<Font cssVariable="--font-inter" preload />`), qui génère aussi des polices de repli ajustées (moins de CLS). Google Fonts via `fonts.googleapis.com` = requêtes tierces en plus (et question RGPD).

### E. CLS et INP
- CLS : éléments listés dans « Éléments qui bougent » ; causes typiques : images ou iframes sans dimensions, polices, bannière de consentement insérée au-dessus du contenu, îlot qui s'hydrate avec une hauteur différente.
- INP (terrain seulement ; en labo, TBT sert d'indicateur) : gestionnaires d'événements lourds, hydratation au moment de l'interaction, re-rendus React de listes longues.

### F. Navigation
- `prefetch` (config Astro) sur les liens clés ; `experimental.clientPrerender` (Speculation Rules) pour aller plus loin ; View Transitions (`<ClientRouter />`) uniquement si c'est utile (elles ajoutent du JS).

### G. Version d'Astro
Beaucoup de ces leviers dépendent de la version (images responsives 5.10, API Fonts et CSP 6.0, cache de routes 7.0). `code-scan.md` affiche la version installée et la dernière. Si le retard est d'une version majeure ou plus, en faire un constat avec la liste des gains concrets qu'apporte la montée de version pour CE site, et renvoyer au guide de migration.

## Correctifs types (à adapter après lecture du fichier concerné)

```astro
---
// Image Convex optimisée par Astro (domaine autorisé dans astro.config : image.remotePatterns)
import { Image } from 'astro:assets';
---
<Image src={course.coverUrl} alt={course.title} width={800} height={450}
       widths={[400, 800, 1200]} sizes="(max-width: 768px) 100vw, 800px" format="avif" />
```

```js
// astro.config.mjs
image: { remotePatterns: [{ protocol: 'https', hostname: 'convex.mondomaine.fr' }] },
prefetch: { prefetchAll: false, defaultStrategy: 'hover' },
```

```astro
<!-- Chat : hydraté quand le navigateur est libre, pas au chargement -->
<ChatBubble client:idle />
```

```caddy
# Caddyfile : compression au proxy
site.fr {
  encode zstd gzip
  reverse_proxy 127.0.0.1:4321
}
```

## Restitution

`rapports/performance.md` : tableau Lighthouse (mobile/desktop, par page), données terrain si disponibles, puis les constats `PERF-NNN` au format commun, triés par gain estimé. Pour chaque constat chiffré par Lighthouse, reprendre son estimation (Kio, ms) comme impact.
