---
id: secu-en-tetes-securite-manquants
titre: "En-têtes de sécurité manquants (X-Content-Type-Options, Referrer-Policy, Permissions-Policy)"
domaine: Sécurité
severite_type: moyenne
effort: S
declencheurs:
  - "http:\\| x-content-type-options \\| — \\| ❌ absent"
  - "http:\\| referrer-policy \\| — \\| ❌ absent"
  - "http:\\| permissions-policy \\| — \\| ❌ absent"
sources:
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Content-Type-Options
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy
  - https://docs.astro.build/en/guides/middleware/
  - https://docs.netlify.com/manage/routing/headers/
  - https://vercel.com/docs/project-configuration#headers
---

# En-têtes de sécurité manquants (X-Content-Type-Options, Referrer-Policy, Permissions-Policy)

> **En une phrase** : trois réglages simples que le navigateur attend du serveur ne sont pas envoyés ; ils coûtent quelques lignes de configuration et ferment des risques courants.

## Pourquoi c'est important

- **`X-Content-Type-Options: nosniff`** : interdit au navigateur de « deviner » qu'un fichier est du script s'il est déclaré autrement (contourne certaines attaques par fichier téléversé).
- **`Referrer-Policy`** : sans consigne, le navigateur peut envoyer l'URL complète de vos pages (avec paramètres, jetons éventuels) aux sites tiers vers lesquels pointent vos liens et ressources. `strict-origin-when-cross-origin` n'envoie que le domaine hors de votre site.
- **`Permissions-Policy`** : désactive par défaut caméra, micro, géolocalisation, etc. pour votre page et ses iframes (widgets tiers) ; un script tiers compromis ne peut pas les demander.

Ces en-têtes sont aussi contrôlés par les scanners de sécurité courants et par certains appels d'offres.

## Comment le constater soi-même

```bash
curl -sI https://exemple.fr/ | grep -iE '^(x-content-type-options|referrer-policy|permissions-policy):'
```

Absent : aucune ligne. Corrigé : trois lignes (voir valeurs ci-dessous).

## Correction

Valeurs recommandées pour un site vitrine sans usage de caméra, micro ni géolocalisation (adaptez `Permissions-Policy` si vous utilisez une carte avec position, un formulaire vidéo…) :

- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()`

Choisissez **un seul** endroit pour poser ces en-têtes (le proxy de préférence) afin d'éviter les doublons.

1. **nginx** (bloc `server` en 443, et répétés dans tout `location` qui a ses propres `add_header`) :

   ```nginx
   add_header X-Content-Type-Options "nosniff" always;
   add_header Referrer-Policy "strict-origin-when-cross-origin" always;
   add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()" always;
   ```
2. **Caddy** :

   ```caddy
   exemple.fr {
       header {
           X-Content-Type-Options nosniff
           Referrer-Policy strict-origin-when-cross-origin
           Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()"
       }
       reverse_proxy 127.0.0.1:4321
   }
   ```
3. **Astro SSR sans proxy configurable** : middleware (`src/middleware.ts`), applicable aux pages rendues par Astro.

   ```ts
   // src/middleware.ts
   import { defineMiddleware } from 'astro:middleware';

   export const onRequest = defineMiddleware(async (_context, next) => {
     const response = await next();
     response.headers.set('X-Content-Type-Options', 'nosniff');
     response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
     response.headers.set('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=()');
     return response;
   });
   ```

   Les fichiers statiques servis directement par l'adaptateur ne passent pas par le middleware : posez plutôt les en-têtes au proxy si possible.
4. **Netlify ou Cloudflare Pages** : fichier `public/_headers`.

   ```text
   /*
     X-Content-Type-Options: nosniff
     Referrer-Policy: strict-origin-when-cross-origin
     Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()
   ```
5. **Vercel** : `vercel.json`.

   ```json
   {
     "headers": [
       {
         "source": "/(.*)",
         "headers": [
           { "key": "X-Content-Type-Options", "value": "nosniff" },
           { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" },
           { "key": "Permissions-Policy", "value": "camera=(), microphone=(), geolocation=(), payment=()" }
         ]
       }
     ]
   }
   ```
6. Pour HSTS, CSP et l'anti-clickjacking, voir `secu-hsts-absent`, `secu-csp-absente`, `secu-anti-clickjacking`.

## Critères d'acceptation

- [ ] Les trois en-têtes sont présents sur la page d'accueil et sur une page interne.
- [ ] Chacun n'apparaît qu'une fois (pas de doublon proxy + Astro).
- [ ] Les fonctions utiles (carte, vidéo, paiement) fonctionnent toujours.
- [ ] Aucune régression : pages et assets en 200.

## Vérification après correction

```bash
curl -sI https://exemple.fr/ | grep -iE '^(x-content-type-options|referrer-policy|permissions-policy):'
bash scripts/http_checks.sh https://exemple.fr/ /tmp/verif-http && grep -E 'x-content-type|referrer|permissions' /tmp/verif-http/http-checks.md
```

## Pièges et retour arrière

- `Permissions-Policy` trop stricte casse une carte qui demande la position ou un iframe de paiement : ouvrez seulement la fonction nécessaire, par exemple `geolocation=(self)`.
- `nosniff` peut révéler un fichier servi avec un mauvais type MIME (un `.js` en `text/plain`) : corrigez le type côté serveur.
- `Referrer-Policy: no-referrer` peut fausser les statistiques ; `strict-origin-when-cross-origin` est le bon compromis.
- Retour arrière : retirer les lignes et recharger le serveur.

## Pour aller plus loin

- MDN `X-Content-Type-Options`, `Referrer-Policy` et `Permissions-Policy` : valeurs et compatibilité.
- Astro, middleware : poser des en-têtes sur les réponses.
- Netlify (`_headers`) et Vercel (`headers`) : équivalents pour ces hébergeurs.
