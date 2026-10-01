---
id: code-prerender-ssr-opportunites
titre: Pages rendues à chaque requête alors qu'elles pourraient être prérendues
domaine: Code
severite_type: moyenne
effort: M
declencheurs:
  - "code:Rendu à la demande sans en-têtes de cache"
  - "code:Rendu à la demande sans cache de routes"   # recoupe la fiche perf du cache de routes ; ici l'angle est le prérendu
versions_astro: ">=5.0"
sources:
  - https://docs.astro.build/en/guides/on-demand-rendering/
  - https://docs.astro.build/en/guides/caching/
  - https://docs.astro.build/en/guides/middleware/
---

# Pages rendues à chaque requête alors qu'elles pourraient être prérendues

> **En une phrase** : le site est en `output: 'server'` (ou équivalent) et re-génère chaque page à chaque visite, avec un appel Convex à la clé, alors que la plupart des pages changent rarement.

## Pourquoi c'est important

Une page prérendue est un fichier HTML servi en quelques millisecondes, sans CPU serveur ni requête backend. Une page rendue à la demande paie à chaque visite le rendu, les appels à Convex et le TTFB associé (Google considère un TTFB sous 800 ms comme bon). La doc Astro conseille de rester en mode statique « tant que la plupart des pages ne sont pas dynamiques » et de ne passer en `prerender = false` que les routes qui en ont besoin.

## Comment le constater soi-même

```bash
grep -n "output" astro.config.*                                  # output: 'server' ?
grep -rn "prerender" src/pages                                    # routes déjà classées
grep -rlE "Astro\.(cookies|request\.headers|locals)|Astro\.url\.searchParams" src/pages src/layouts src/components   # ce qui exige vraiment le rendu à la demande
for i in 1 2 3; do curl -s -o /dev/null -w '%{time_starttransfer}\n' https://SITE/; done   # TTFB : stable et bas = déjà cache/prérendu
```

Présent : `output: 'server'`, peu ou pas de `prerender = true`, TTFB de plusieurs centaines de ms sur des pages éditoriales. Corrigé : TTFB de quelques dizaines de ms sur ces pages.

## Correction

1. Sauvegarde : branche Git dédiée. Dresser la liste des routes de `src/pages` et classer chacune :
   - **Prérendable** : ne lit ni cookies, ni session, ni `Astro.request.headers`, ni paramètres de requête ; les données changent rarement (accueil, tarifs, articles, fiches formation).
   - **À la demande** : utilisateur connecté, panier, recherche avec `?q=`, tableau de bord, endpoints d'API, webhooks.
2. **Astro 5 ou plus** : passer en `static` (le défaut) et marquer les seules routes dynamiques :
   ```js
   // astro.config.mjs
   import { defineConfig } from 'astro/config';
   import node from '@astrojs/node';

   export default defineConfig({
     site: 'https://exemple.fr',
     output: 'static',                       // défaut ; l'adapter reste nécessaire pour les routes à la demande
     adapter: node({ mode: 'standalone' }),
   });
   ```
   ```astro
   ---
   // src/pages/mon-compte.astro : seule cette page reste à la demande
   export const prerender = false;
   const session = Astro.cookies.get('session')?.value;
   ---
   ```
   Si tout le site doit rester en `output: 'server'`, ajouter `export const prerender = true;` en tête des pages éditoriales.
3. **Pages dynamiques prérendues** (`[slug].astro`) : fournir `getStaticPaths()`, qui interroge Convex **au build** :
   ```astro
   ---
   export const prerender = true;
   import { ConvexHttpClient } from 'convex/browser';
   import { api } from '../../../convex/_generated/api';

   export async function getStaticPaths() {
     const client = new ConvexHttpClient(import.meta.env.PUBLIC_CONVEX_URL);
     const articles = await client.query(api.articles.lister, {});
     return articles.map((a) => ({ params: { slug: a.slug }, props: { article: a } }));
   }
   const { article } = Astro.props;
   ---
   <h1>{article.titre}</h1>
   ```
   Les contenus modifiés dans Convex n'apparaissent alors qu'après un **nouveau build** : déclencher un rebuild à la publication (webhook de l'hébergeur), ou garder la page à la demande avec un cache.
4. **Pages qui doivent rester à la demande** : les mettre en cache. Astro 7 : `cache: { provider: memoryCache() }` et `routeRules`, ou `Astro.cache.set({ maxAge: 300, swr: 60 })` ; Astro < 7 : `Astro.response.headers.set('Cache-Control', 'public, s-maxage=300, stale-while-revalidate=600')`. Les parties personnalisées d'une page publique se règlent avec les server islands (fiche `code-server-islands`).
5. **Middleware** (`src/middleware.ts`) : il s'exécute à chaque requête des pages à la demande (et une fois au build pour les pages prérendues). Y interdire tout appel réseau systématique (validation de session distante, requête Convex) sur les routes publiques ; limiter son travail aux chemins protégés :
   ```ts
   import { defineMiddleware } from 'astro:middleware';

   export const onRequest = defineMiddleware(async (context, next) => {
     if (!context.url.pathname.startsWith('/mon-compte')) return next();
     // contrôle de session uniquement ici
     return next();
   });
   ```

## Critères d'acceptation

- [ ] Chaque page éditoriale a `prerender = true` (ou le site est en `static`) ; le build produit ses fichiers HTML
- [ ] Les seules routes à la demande sont celles qui lisent cookies, session ou paramètres
- [ ] TTFB des pages prérendues nettement inférieur à celui d'avant (quelques dizaines de ms), pages à la demande en cache ou < 800 ms
- [ ] Aucune régression : contenus Convex à jour après rebuild, pages dynamiques inexistantes en 404

## Vérification après correction

```bash
npx astro build && find dist -name '*.html' | wc -l        # le nombre de pages HTML doit augmenter
curl -s -o /dev/null -w '%{http_code} %{time_starttransfer}\n' https://SITE/
python3 scripts/astro_scan.py . --out /tmp/verif
```

## Pièges et retour arrière

- Une page prérendue ne voit jamais les cookies ni les en-têtes de la requête : si elle affiche l'utilisateur connecté, isoler ce morceau en server island.
- `getStaticPaths()` s'exécute au build : `PUBLIC_CONVEX_URL` doit exister dans l'environnement du build.
- Les valeurs de `prerender` doivent être `true` ou `false` littéraux (pas de calcul dynamique).
- Retour arrière : remettre `output: 'server'` et retirer les `prerender = true` ajoutés (`git revert`).

## Pour aller plus loin

- https://docs.astro.build/en/guides/on-demand-rendering/ : modes de rendu et `prerender`.
- https://docs.astro.build/en/guides/caching/ : cache de routes (Astro 7).
- https://docs.astro.build/en/guides/middleware/ : middleware et son exécution au build.
