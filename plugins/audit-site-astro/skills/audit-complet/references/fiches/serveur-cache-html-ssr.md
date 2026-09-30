---
id: serveur-cache-html-ssr
titre: Pages HTML rendues à chaque requête, sans aucun cache (route, proxy ou CDN)
domaine: Serveur / HTTP
severite_type: haute
effort: M
declencheurs:
  - "code:Rendu à la demande sans cache de routes"
  - "code:Rendu à la demande sans en-têtes de cache"
  - "http:Cache-Control HTML \\| absent"
  - "http:Cache-Control HTML \\|.*non cacheable"
versions_astro: ">=7.0 pour cache/routeRules ; avant : en-têtes Cache-Control manuels"
sources:
  - https://docs.astro.build/en/guides/caching/
  - https://docs.astro.build/en/guides/on-demand-rendering/
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control
  - https://nginx.org/en/docs/http/ngx_http_proxy_module.html
---

# Pages HTML rendues à chaque requête, sans aucun cache (route, proxy ou CDN)

> **En une phrase** : chaque visite déclenche un rendu complet sur le serveur (et les appels Convex qui vont avec) alors que la page est identique pour tous ; le TTFB reste élevé et le serveur sature vite.

## Pourquoi c'est important

Un site Astro en rendu à la demande qui ne met rien en cache refait le même travail des milliers de fois. Conséquences : TTFB de plusieurs centaines de ms (Google vise moins de 0,8 s, et moins de 0,2 s quand un cache répond), LCP dégradé, pics de charge (robots, campagnes) qui font tomber le serveur, facture Convex plus élevée. Une page publique identique pour tous les visiteurs peut être servie depuis un cache pendant quelques minutes sans que le contenu paraisse périmé.

La solution n° 1 reste de **prérendre** les pages qui changent rarement (`export const prerender = true`, voir la fiche `code-prerender-ssr-opportunites`). Cette fiche traite les pages qui doivent rester rendues à la demande.

## Comment le constater soi-même

```bash
curl -sI https://SITE/ | grep -iE '^(cache-control|age|etag|last-modified|x-cache|cf-cache-status|x-vercel-cache)'
# Même page 5 fois : un TTFB constant et élevé = aucun cache
for i in 1 2 3 4 5; do curl -s -o /dev/null -w '%{time_starttransfer}\n' https://SITE/; done
grep -nE "cache\s*:|routeRules" astro.config.*        # Astro 7 : cache de routes configuré ?
grep -rn "Cache-Control\|Astro.cache" src | head       # ou en-têtes / API de cache dans le code
```

Problème présent : pas de `Cache-Control` (ou `no-store`/`private` sur une page publique), pas de `Age`, TTFB identique à chaque appel. Corrigé : `Cache-Control` explicite et TTFB de la 2e requête bien inférieur à la 1re.

## Correction

Sauvegarde : travailler sur une branche Git. **Ne mettre en cache que les pages identiques pour tous les visiteurs** (jamais un espace connecté, un panier, une page qui lit `Astro.cookies`/`Astro.locals`).

1. **Astro 7 ou plus, serveur Node (cache en mémoire du process)** dans `astro.config.mjs` :

```js
import { defineConfig, memoryCache } from 'astro/config';
import node from '@astrojs/node';

export default defineConfig({
  site: 'https://exemple.fr',
  output: 'server',
  adapter: node({ mode: 'standalone' }),
  cache: { provider: memoryCache() },
  routeRules: {
    '/': { maxAge: 300, swr: 60 },
    '/blog/[...slug]': { maxAge: 300, swr: 60, tags: ['blog'] },
    '/formations/[...slug]': { maxAge: 600, swr: 120, tags: ['formations'] },
  },
});
```

`maxAge` = durée de fraîcheur en secondes, `swr` = durée pendant laquelle une réponse périmée est servie pendant qu'elle est régénérée en arrière-plan. Le cache de routes ne s'applique qu'aux pages rendues à la demande (pas aux pages prérendues). Le cache en mémoire est propre à chaque processus : il se vide au redémarrage.

2. **Invalider à la publication** (contenu modifié dans Convex ou le CMS) dans un endpoint appelé après la mise à jour :

```ts
// src/pages/api/revalider.ts
export const prerender = false;
import type { APIRoute } from 'astro';

export const POST: APIRoute = async (context) => {
  const secret = context.request.headers.get('x-revalidate-secret');
  if (secret !== import.meta.env.REVALIDATE_SECRET) return new Response('Interdit', { status: 403 });
  await context.cache.invalidate({ tags: ['blog'] });
  return new Response('OK');
};
```

`REVALIDATE_SECRET` est une variable d'environnement serveur (jamais dans le dépôt). Pour exclure une page personnalisée du cache : `Astro.cache.set(false);` dans son frontmatter.

3. **Astro < 7** : pas de cache de routes. Poser les en-têtes dans chaque page publique (ou dans `src/middleware.ts`) et faire cacher par le proxy ou le CDN :

```astro
---
export const prerender = false;
Astro.response.headers.set('Cache-Control', 'public, max-age=0, s-maxage=300, stale-while-revalidate=600');
Astro.response.headers.set('X-Accel-Expires', '300'); // lu et retiré par nginx, ignoré ailleurs
---
```

`max-age=0` : le navigateur revalide toujours ; `s-maxage` : les caches partagés (CDN) gardent 5 minutes. Ces en-têtes ne peuvent être posés que dans une **page** ou un middleware, pas dans un composant.

4. **nginx devant Node** : cache disque partagé entre tous les visiteurs, avec service de la version périmée pendant le rechargement. Dans `http {}` puis dans le `location /` du site :

```nginx
proxy_cache_path /var/cache/nginx/astro levels=1:2 keys_zone=astro:10m max_size=500m inactive=60m use_temp_path=off;

map $http_cookie $astro_skip_cache {
    default 0;
    ~*session 1;              # adapter au nom réel du cookie de session
}

server {
    location / {
        proxy_pass http://127.0.0.1:4321;
        proxy_cache astro;
        proxy_cache_bypass $astro_skip_cache;
        proxy_no_cache $astro_skip_cache;
        proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
        proxy_cache_background_update on;
        proxy_cache_lock on;
        add_header X-Cache-Status $upstream_cache_status always;
    }
}
```

nginx ne met en cache que si la réponse le permet (`X-Accel-Expires` en priorité, sinon `Cache-Control`/`Expires`). Une page sans ces en-têtes n'est pas cachée : c'est voulu, on active le cache page par page (étape 3). nginx ne cache pas non plus les réponses qui portent un `Set-Cookie`.

5. **CDN** : Vercel, Netlify et Cloudflare peuvent cacher le HTML si la réponse porte `s-maxage`. Astro 7 propose des fournisseurs de cache d'adaptateur (expérimentaux) : `cacheVercel()` (`@astrojs/vercel/cache`), `cacheNetlify()` (`@astrojs/netlify/cache`), `cacheCloudflare()` (`@astrojs/cloudflare/cache`) à passer à `cache: { provider: … }`. Cloudflare seul ne met **pas** le HTML en cache par défaut : il faut une règle de cache qui respecte les en-têtes de l'origine.

## Critères d'acceptation

- [ ] Les pages publiques ont un mécanisme de cache (règle `routeRules`, `Astro.cache.set` ou `Cache-Control` avec `s-maxage`)
- [ ] Une même page appelée deux fois : la 2e réponse est nettement plus rapide (ou `X-Cache-Status: HIT`, `Age` > 0)
- [ ] Aucune page connectée ou personnalisée n'est servie à un autre visiteur (test avec deux sessions)
- [ ] Une modification de contenu apparaît en moins de `maxAge` secondes, ou immédiatement après l'appel d'invalidation

## Vérification après correction

```bash
for i in 1 2 3; do curl -s -o /dev/null -D - https://SITE/ | grep -iE '^(cache-control|age|x-cache-status)'; echo ---; done
bash scripts/http_checks.sh https://SITE/ /tmp/verif        # §2 : écart entre « normale » et « sans cache »
python3 scripts/astro_scan.py . --out /tmp/verif            # plus de constat « Rendu à la demande sans cache »
```

## Pièges et retour arrière

- Fuite de données : mettre en cache une page qui affiche l'utilisateur connecté la montre aux autres. Toujours exclure les pages lisant cookies ou session, et tester avec deux comptes.
- Le cache en mémoire d'Astro se vide à chaque redémarrage et n'est pas partagé entre plusieurs instances : pour plusieurs conteneurs, préférer le cache nginx ou le CDN.
- `stale-while-revalidate` masque une panne courte de Convex mais aussi une erreur : ne pas cacher les réponses 5xx.
- Retour arrière : retirer `cache`/`routeRules` (ou les en-têtes ajoutés) et `proxy_cache`, recharger le service.

## Pour aller plus loin

- https://docs.astro.build/en/guides/caching/ : cache de routes d'Astro 7 (`memoryCache`, `routeRules`, invalidation par tags).
- https://docs.astro.build/en/guides/on-demand-rendering/ : en-têtes de réponse posés depuis une page.
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control : `s-maxage`, `stale-while-revalidate`, `private`, `no-store`.
- https://nginx.org/en/docs/http/ngx_http_proxy_module.html : `proxy_cache`, `proxy_cache_use_stale`, `X-Accel-Expires`.
