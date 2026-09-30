---
id: convex-http-actions-cors-webhooks
titre: HTTP actions Convex sans CORS restreint ni vérification de signature des webhooks
domaine: Code
severite_type: haute
effort: M
declencheurs:
  # Aucun détecteur automatique à ce jour : messages proposés pour astro_scan.py (voir le rapport de rédaction)
  - "code:httpAction sans vérification de signature"
  - "code:httpAction avec Access-Control-Allow-Origin \\*"
sources:
  - https://docs.convex.dev/functions/http-actions
  - https://docs.convex.dev/functions/runtimes
  - https://docs.convex.dev/auth/functions-auth
---

# HTTP actions Convex sans CORS restreint ni vérification de signature des webhooks

> **En une phrase** : une HTTP action (`convex/http.ts`) est un point d'accès public sur Internet ; sans allow-list CORS ni contrôle de signature, n'importe quel site ou n'importe qui peut la solliciter en se faisant passer pour votre fournisseur (Stripe, formulaire, etc.).

## Pourquoi c'est important

Les HTTP actions vivent sur `https://<déploiement>.convex.site` et sont joignables par tous. Un webhook (paiement, e-mail, CRM) dont on ne vérifie pas la signature permet à un inconnu de « confirmer » un paiement ou d'injecter de faux événements. Un `Access-Control-Allow-Origin` trop large laisse des sites tiers appeler l'endpoint depuis le navigateur d'un visiteur. Les HTTP actions ne se réessaient pas automatiquement : il faut aussi les rendre idempotentes.

## Comment le constater soi-même

```bash
grep -n "httpAction\|http.route\|Access-Control" convex/http.ts
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://DEPLOIEMENT.convex.site/webhooks/fournisseur -d '{"id":"evt_test","type":"x"}'
curl -si -X OPTIONS https://DEPLOIEMENT.convex.site/api/contact -H 'Origin: https://evil.example' -H 'Access-Control-Request-Method: POST' | grep -i access-control
```

Présent : le webhook répond 200 sans signature ; l'en-tête CORS renvoie `*` ou l'origine étrangère. Corrigé : 401 sans signature, aucun `Access-Control-Allow-Origin` pour `evil.example`.

## Correction

1. **Webhook : vérifier la signature sur le corps brut**, avant tout traitement. Exemple générique HMAC-SHA256 (schéma `X-Signature: sha256=<hex>`), avec l'API Web Crypto disponible dans le runtime par défaut de Convex :
   ```ts
   // convex/model/signature.ts
   function hexVersOctets(hex: string): Uint8Array | null {
     if (hex.length % 2 !== 0 || /[^0-9a-f]/i.test(hex)) return null;
     const octets = new Uint8Array(hex.length / 2);
     for (let i = 0; i < octets.length; i++) {
       octets[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
     }
     return octets;
   }

   export async function signatureValide(secret: string, corps: string, entete: string | null): Promise<boolean> {
     if (entete === null || !entete.startsWith('sha256=')) return false;
     const attendue = hexVersOctets(entete.slice('sha256='.length));
     if (attendue === null) return false;
     const encodeur = new TextEncoder();
     const cle = await crypto.subtle.importKey('raw', encodeur.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['verify']);
     return await crypto.subtle.verify('HMAC', cle, attendue, encodeur.encode(corps));
   }
   ```
   `crypto.subtle.verify` compare en temps constant : ne pas comparer les signatures avec `===`.
   ```ts
   // convex/http.ts
   import { httpRouter } from 'convex/server';
   import { httpAction } from './_generated/server';
   import { internal } from './_generated/api';
   import { signatureValide } from './model/signature';

   const http = httpRouter();

   http.route({
     path: '/webhooks/fournisseur',
     method: 'POST',
     handler: httpAction(async (ctx, request) => {
       const corps = await request.text();   // corps brut, avant tout JSON.parse
       const secret = process.env.WEBHOOK_SECRET;
       if (!secret) return new Response('Configuration manquante', { status: 500 });
       if (!(await signatureValide(secret, corps, request.headers.get('x-signature')))) {
         return new Response('Signature invalide', { status: 401 });
       }
       const evenement = JSON.parse(corps) as { id: string; type: string };
       await ctx.runMutation(internal.webhooks.traiter, { evenementId: evenement.id, type: evenement.type });
       return new Response(null, { status: 200 });
     }),
   });

   export default http;
   ```
   Le secret se définit côté Convex, jamais dans le dépôt (`npx convex env set WEBHOOK_SECRET <valeur>` sur le déploiement de développement ; en production, c'est l'humain qui le définit, avec `--prod` ou dans le tableau de bord), et se change là après une rotation chez le fournisseur.
2. **Stripe** : ne pas réécrire la vérification, utiliser la bibliothèque officielle dans une action Node (`"use node"` en première ligne du fichier, qui ne doit contenir aucune query ni mutation) :
   ```ts
   // convex/stripeWebhook.ts
   "use node";
   import Stripe from 'stripe';
   import { v } from 'convex/values';
   import { internalAction } from './_generated/server';

   export const verifier = internalAction({
     args: { corps: v.string(), signature: v.string() },
     handler: async (_ctx, args) => {
       const stripe = new Stripe(process.env.STRIPE_SECRET_KEY as string);
       const evenement = await stripe.webhooks.constructEventAsync(args.corps, args.signature, process.env.STRIPE_WEBHOOK_SECRET as string);
       return { id: evenement.id, type: evenement.type };
     },
   });
   ```
   L'HTTP action lit `request.text()` et l'en-tête `stripe-signature`, appelle `ctx.runAction(internal.stripeWebhook.verifier, …)` (une erreur → réponse 400), puis `ctx.runMutation(internal.…)`.
3. **Idempotence** : les fournisseurs renvoient les événements. Dans la mutation interne `traiter`, chercher l'identifiant d'événement dans une table `evenementsTraites` (avec un index `by_evenement`) et sortir si déjà vu, sinon traiter et l'enregistrer dans la même transaction.
4. **CORS restreint à une liste d'origines**, uniquement sur les endpoints appelés depuis un navigateur ; ne jamais mettre `*` sur un endpoint qui renvoie des données personnelles :
   ```ts
   const ORIGINES = (process.env.ORIGINES_AUTORISEES ?? '').split(',').filter(Boolean);   // ex. "https://exemple.fr,https://www.exemple.fr"

   function enteteCors(request: Request): Headers {
     const entetes = new Headers({ Vary: 'Origin' });
     const origine = request.headers.get('Origin');
     if (origine !== null && ORIGINES.includes(origine)) {
       entetes.set('Access-Control-Allow-Origin', origine);
     }
     return entetes;
   }

   http.route({
     path: '/api/contact',
     method: 'OPTIONS',
     handler: httpAction(async (_ctx, request) => {
       const entetes = enteteCors(request);
       entetes.set('Access-Control-Allow-Methods', 'POST');
       entetes.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
       entetes.set('Access-Control-Max-Age', '86400');
       return new Response(null, { status: 204, headers: entetes });
     }),
   });
   ```
   La réponse du `POST` réutilise `enteteCors(request)`. Un webhook (appel de serveur à serveur) n'a pas besoin de CORS.
5. **Authentification** des endpoints navigateur : `Authorization: Bearer <jeton>` et `await ctx.auth.getUserIdentity()` dans l'action ; ne pas s'appuyer sur un paramètre d'URL. Pour les opérations sensibles, appeler des fonctions `internal.*`, jamais `api.*`.

## Critères d'acceptation

- [ ] Chaque webhook vérifie une signature sur le corps brut avant tout effet ; sans signature valide : 401 (ou 400)
- [ ] Les événements rejoués n'ont pas d'effet double (idempotence testée)
- [ ] Aucun `Access-Control-Allow-Origin: *` sur un endpoint qui renvoie des données propres à l'utilisateur ; les origines autorisées sont une liste
- [ ] Aucune régression : le vrai fournisseur (mode test) déclenche bien l'événement, le formulaire du site fonctionne

## Vérification après correction

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://DEPLOIEMENT.convex.site/webhooks/fournisseur -d '{"id":"x"}'   # 401
curl -si -X OPTIONS https://DEPLOIEMENT.convex.site/api/contact -H 'Origin: https://evil.example' -H 'Access-Control-Request-Method: POST' | grep -ci 'access-control-allow-origin: https://evil'   # 0
npx convex dev --once
```

## Pièges et retour arrière

- Vérifier la signature sur le texte **brut** : re-sérialiser le JSON change les octets et invalide la signature.
- Un fichier `"use node"` ne peut pas contenir de `query` ni de `mutation`, et ne peut pas être importé par un fichier du runtime standard.
- Voir aussi `secu-cors-ouvert` (CORS des pages Astro).
- Retour arrière : `git revert` puis `npx convex dev --once` ; si la version fautive est déjà en production, le déploiement en production (`npx convex deploy`) est fait par l'humain, pas par l'agent ; ne pas retirer la vérification de signature en production.

## Pour aller plus loin

- https://docs.convex.dev/functions/http-actions : routes, CORS, corps de requête, limites (20 Mo).
- https://docs.convex.dev/functions/runtimes : Web Crypto dans le runtime par défaut, directive `"use node"`.
- https://docs.convex.dev/auth/functions-auth : authentification par jeton Bearer dans une HTTP action.
