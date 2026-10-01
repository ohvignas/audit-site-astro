---
id: seo-sitemap-urls-http
titre: URL du sitemap en http:// ou construites depuis la requête (redirigées)
domaine: SEO technique
severite_type: haute
effort: S
declencheurs:
  - "crawl:sitemap_redirect"
  - "code:construit les URL depuis l'origine de la requête"
  - "code:contient une URL http:// en dur"
sources:
  - https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap
  - https://docs.astro.build/en/reference/api-reference/
  - https://docs.astro.build/en/guides/integrations-guide/sitemap/
---

# URL du sitemap en http:// ou construites depuis la requête (redirigées)

> **En une phrase** : le sitemap liste des URL qui redirigent (souvent `http://` au lieu de `https://`, ou avec/sans slash final) au lieu des URL finales, ce qui gaspille le crawl et affaiblit la confiance de Google dans le fichier.

## Pourquoi c'est important

Google explore les URL du sitemap « exactement comme elles sont listées » et demande des URL absolues et complètes. Une URL qui redirige n'est pas une URL canonique : Google doit suivre la redirection avant d'indexer. Sur un site Astro en rendu serveur derrière nginx ou Caddy, la cause la plus fréquente est un endpoint de sitemap qui lit `new URL(request.url).origin` : le proxy parle en `http://` au serveur Node, donc toutes les URL sortent en `http://`. Le même défaut fausse les canonicals et l'alerte « robots.txt n'est pas valide » de Lighthouse.

## Comment le constater soi-même

```bash
# URL du sitemap qui ne commencent pas par https://exemple.fr
curl -s https://SITE/sitemap.xml | grep -o '<loc>[^<]*' | grep -v '^<loc>https://exemple.fr' | head
# Statut de la première URL listée, sans suivre les redirections
u=$(curl -s https://SITE/sitemap.xml | grep -o '<loc>[^<]*' | head -1 | sed 's/<loc>//')
curl -s -o /dev/null -w '%{http_code} -> %{redirect_url}\n' "$u"
# Dans le code
grep -rnE "url\.origin|request\.url|http://" src/pages/ | grep -i sitemap
```

Présent : des `<loc>` en `http://` ou un statut 301/302 sur les URL. Corrigé : toutes les `<loc>` en `https://` sur le domaine canonique, statut 200.

## Correction

1. Si le site utilise `@astrojs/sitemap` : vérifier `site: 'https://exemple.fr'` dans `astro.config.mjs` (voir la fiche `seo-astro-site-et-proxy`) et reconstruire. L'intégration génère `sitemap-index.xml` et `sitemap-0.xml`.
2. Si un endpoint personnalisé existe (`src/pages/sitemap.xml.ts`) : ne plus utiliser l'origine de la requête. Partir de `site` (contexte d'endpoint : `site`).
3. Aligner le slash final avec `trailingSlash` (voir `seo-trailing-slash`) : une URL du sitemap en `/page` alors que le site redirige vers `/page/` est aussi signalée.
4. Supprimer les URL `http://` écrites en dur.

```ts
// src/pages/sitemap.xml.ts : origine fiable, jamais celle de la requête
import type { APIRoute } from 'astro';

export const prerender = false; // retirer cette ligne si la liste des pages est connue au build

const escapeXml = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

export const GET: APIRoute = async ({ site }) => {
  if (!site) {
    return new Response('`site` doit être défini dans astro.config', { status: 500 });
  }
  // Remplacer par la vraie source (collection de contenu, requête Convex...) :
  const pages: { path: string; lastmod: Date }[] = [
    { path: '/', lastmod: new Date('2026-01-15') },
    { path: '/contact/', lastmod: new Date('2026-01-10') },
  ];
  const urls = pages
    .map(
      (p) =>
        `<url><loc>${escapeXml(new URL(p.path, site).href)}</loc><lastmod>${p.lastmod.toISOString()}</lastmod></url>`,
    )
    .join('');
  const body = `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls}</urlset>`;
  return new Response(body, { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
};
```

(Le `http://www.sitemaps.org/...` est l'espace de noms XML officiel : il reste en `http://`.)

5. Mettre en cache la réponse côté proxy ou avec `Cache-Control` si la liste vient d'une base de données.

## Critères d'acceptation

- [ ] 0 `<loc>` en `http://` ; toutes sur le domaine canonique
- [ ] Chaque URL du sitemap répond 200 sans redirection (`curl -o /dev/null -w '%{http_code}'`)
- [ ] `robots.txt` référence le sitemap en URL absolue https (voir `seo-robots-txt-invalide-absent`)
- [ ] Aucune régression : build OK, sitemap valide en XML

## Vérification après correction

```bash
curl -s https://SITE/sitemap.xml | grep -c '<loc>http://'                 # attendu : 0
curl -s https://SITE/sitemap.xml | grep -o '<loc>[^<]*' | sed 's/<loc>//' | head -20 \
  | while read u; do curl -s -o /dev/null -w "%{http_code} $u\n" "$u"; done   # attendu : 200 partout
```

Relancer `python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif` : `sitemap_redirect` doit disparaître.

## Pièges et retour arrière

- Un sitemap est limité à 50 000 URL ou 50 Mo non compressé : au-delà, utiliser un index de sitemaps.
- Échapper `&` dans les URL (`&amp;`), sinon le XML est invalide.
- Ne pas confondre l'espace de noms XML (`http://www.sitemaps.org`) et une vraie URL de page.
- Retour arrière : `git revert` du fichier d'endpoint.

## Pour aller plus loin

- https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap : URL absolues, limites de taille, `lastmod`.
- https://docs.astro.build/en/reference/api-reference/ : `Astro.site` et le contexte des endpoints.
- https://docs.astro.build/en/guides/integrations-guide/sitemap/ : intégration `@astrojs/sitemap`.
