---
id: secu-cors-ouvert
titre: "CORS ouvert à n'importe quelle origine"
domaine: Sécurité
severite_type: moyenne
effort: S
declencheurs:
  - "securite:CORS sur la page HTML pour une origine arbitraire"
sources:
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin
  - https://docs.convex.dev/functions/http-actions
  - https://caddyserver.com/docs/caddyfile/directives/header
---

# CORS ouvert à n'importe quelle origine

> **En une phrase** : le serveur répond `Access-Control-Allow-Origin` à une origine quelconque (`https://evil.example` dans le test), donc le navigateur autorise des sites tiers à lire ses réponses.

## Pourquoi c'est important

CORS décide quels sites web peuvent lire, depuis le navigateur d'un visiteur, les réponses de votre serveur. Sur des pages publiques sans données personnelles, `Access-Control-Allow-Origin: *` est généralement sans conséquence. Le risque devient réel dès que l'URL renvoie des données propres à l'utilisateur ou accepte des cookies : un site pirate ouvert par la victime pourrait alors lire ces données. Le pire cas est un serveur qui **reflète** l'origine reçue **et** envoie `Access-Control-Allow-Credentials: true`. Le constat de l'outil porte ici sur la page HTML : à vérifier, puis à restreindre aux endpoints qui en ont vraiment besoin.

## Comment le constater soi-même

```bash
curl -s -o /dev/null -D - -H 'Origin: https://evil.example' https://exemple.fr/ | grep -i '^access-control-'
# Endpoints d'API éventuels :
curl -s -o /dev/null -D - -H 'Origin: https://evil.example' https://exemple.fr/api/contact | grep -i '^access-control-'
```

- Présent : `access-control-allow-origin: *` ou `https://evil.example` (origine reflétée). Grave si `access-control-allow-credentials: true` accompagne une origine reflétée.
- Corrigé : aucun en-tête `access-control-*` sur la page HTML ; sur un endpoint public, seulement vos propres origines.

## Correction

1. **Trouver qui ajoute l'en-tête** : configuration du proxy (`add_header Access-Control-Allow-Origin`), middleware Astro, endpoint `src/pages/api/*`, CDN ou hébergeur (règle d'en-têtes), intégration ajoutée pour un besoin ponctuel.
2. **Retirer l'en-tête des pages HTML** (elles n'ont aucune raison d'être lues par un autre site).

   nginx : supprimez la ligne `add_header Access-Control-Allow-Origin ...` du bloc `server` ou `location /`.

   Caddy : supprimez la ligne `header Access-Control-Allow-Origin ...` ou ajoutez `header -Access-Control-Allow-Origin` dans le bloc du site.
3. **Si une API doit vraiment être appelée depuis un autre site**, autorisez une liste précise d'origines, jamais `*` ni le reflet aveugle.

   nginx (dans le `location` de l'API uniquement) :

   ```nginx
   map $http_origin $cors_ok {
       default "";
       "https://app.exemple.fr" $http_origin;
       "https://www.exemple.fr" $http_origin;
   }
   server {
       location /api/ {
           add_header Access-Control-Allow-Origin $cors_ok always;
           add_header Vary Origin always;
           proxy_pass http://127.0.0.1:4321;
       }
   }
   ```

   (le bloc `map` va dans le contexte `http`, hors `server`.)

   Caddy :

   ```caddy
   exemple.fr {
       @cors_ok header Origin https://app.exemple.fr
       handle /api/* {
           header @cors_ok Access-Control-Allow-Origin "https://app.exemple.fr"
           header Vary Origin
           reverse_proxy 127.0.0.1:4321
       }
       reverse_proxy 127.0.0.1:4321
   }
   ```
4. **Endpoint Astro** : posez les en-têtes vous-même, avec une liste blanche.

   ```ts
   // src/pages/api/public.ts
   import type { APIRoute } from 'astro';

   export const prerender = false;
   const ORIGINES = new Set(['https://app.exemple.fr', 'https://www.exemple.fr']);

   export const GET: APIRoute = ({ request }) => {
     const origine = request.headers.get('Origin') ?? '';
     const headers = new Headers({ 'Content-Type': 'application/json', Vary: 'Origin' });
     if (ORIGINES.has(origine)) headers.set('Access-Control-Allow-Origin', origine);
     return new Response(JSON.stringify({ ok: true }), { headers });
   };
   ```
5. **HTTP Actions Convex** (`convex/http.ts`) : même principe, l'origine autorisée vient d'une variable d'environnement Convex (par exemple `CLIENT_ORIGIN`), sans `*`, avec `Vary: Origin` et un gestionnaire `OPTIONS` pour les requêtes préalables.

   ```ts
   // convex/http.ts
   import { httpRouter } from 'convex/server';
   import { httpAction } from './_generated/server';

   const http = httpRouter();
   const origine = process.env.CLIENT_ORIGIN ?? 'https://www.exemple.fr';

   http.route({
     path: '/lead',
     method: 'OPTIONS',
     handler: httpAction(async () =>
       new Response(null, {
         headers: {
           'Access-Control-Allow-Origin': origine,
           'Access-Control-Allow-Methods': 'POST',
           'Access-Control-Allow-Headers': 'Content-Type',
           'Access-Control-Max-Age': '86400',
           Vary: 'Origin',
         },
       }),
     ),
   });

   export default http;
   ```

   Ajoutez ensuite la route `POST` qui répond avec les mêmes en-têtes `Access-Control-Allow-Origin` et `Vary`.
6. Ne combinez jamais `Access-Control-Allow-Credentials: true` avec `*` (le navigateur le refuse) ni avec une origine reflétée sans liste blanche.

## Critères d'acceptation

- [ ] La page HTML n'envoie aucun `access-control-allow-origin`.
- [ ] Les endpoints qui en ont besoin répondent uniquement à vos origines déclarées.
- [ ] Le site et ses appels d'API légitimes fonctionnent depuis vos domaines.

## Vérification après correction

```bash
curl -s -o /dev/null -D - -H 'Origin: https://evil.example' https://exemple.fr/ | grep -ci '^access-control-'   # attendu : 0
bash scripts/security_probe.sh https://exemple.fr/ /tmp/verif-secu && tail -3 /tmp/verif-secu/security-probe.md
```

## Pièges et retour arrière

- CORS ne protège pas votre serveur : il limite ce que le navigateur laisse lire. Une API sensible doit de toute façon exiger une authentification.
- Une liste blanche trop stricte casse un widget ou une application mobile web : listez tous vos sous-domaines réels.
- Ajoutez `Vary: Origin` quand la réponse dépend de l'origine, sinon un cache peut resservir la mauvaise.
- Retour arrière : remettre la ligne précédente du fichier de configuration (sauvegarde `cp site site.bak`).

## Pour aller plus loin

- MDN, guide CORS : fonctionnement des requêtes simples et préalables.
- MDN, `Access-Control-Allow-Origin` : valeurs autorisées.
- Convex, HTTP Actions : exemple de gestion de CORS.
- Caddy, directive `header` : syntaxe et matchers.
