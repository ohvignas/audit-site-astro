---
id: convex-mutation-publique-sans-auth
titre: Mutation ou action Convex publique sans vérification d'identité
domaine: Code
severite_type: haute
effort: M
declencheurs:
  - "code:mutation\\(s\\)/action\\(s\\) publique\\(s\\) sans vérification d'identité"
sources:
  - https://docs.convex.dev/auth/functions-auth
  - https://docs.convex.dev/functions/internal-functions
  - https://docs.convex.dev/understanding/best-practices/
---

# Mutation ou action Convex publique sans vérification d'identité

> **En une phrase** : toute `mutation`, `query` ou `action` exportée est appelable par n'importe qui connaissant l'URL du déploiement ; sans contrôle d'identité, un inconnu peut écrire, modifier ou supprimer vos données.

## Pourquoi c'est important

L'URL Convex (`PUBLIC_CONVEX_URL`) est visible dans le code de la page : un visiteur peut appeler directement vos fonctions publiques, sans passer par votre interface. Une mutation sans contrôle permet de polluer la base (faux leads), de modifier ou supprimer du contenu, ou de déclencher des actions coûteuses (envoi d'e-mails, appels d'API payantes). La doc Convex demande de vérifier `ctx.auth.getUserIdentity()` et les droits dans **toutes** les fonctions publiques, et de réserver `internal*` aux fonctions appelées seulement par le serveur.

## Comment le constater soi-même

```bash
grep -rnE "export const \w+ = (mutation|action|query)\(" convex --include=*.ts | grep -v _generated
grep -rn "getUserIdentity" convex
# Appel anonyme direct (remplacer l'URL et le nom de fonction ; sans jeton, donc en tant qu'inconnu) :
curl -s https://VOTRE-DEPLOIEMENT.convex.cloud/api/mutation \
  -H 'Content-Type: application/json' \
  -d '{"path":"leads:creer","args":{"email":"test@exemple.fr"},"format":"json"}'
```

Présent : la réponse contient `"status":"success"` alors que l'appel est anonyme. Corrigé : une erreur « Non authentifié ». Faire ce test sur un environnement de développement, pas sur la production.

## Correction

1. Lister chaque fonction signalée et décider de sa nature :
   - **Appelée seulement par le serveur, un cron ou une autre fonction** : la passer en `internalMutation` / `internalQuery` / `internalAction` et l'appeler par `internal.fichier.nom` (jamais `api.`).
   - **Publique avec utilisateurs connectés** : contrôler l'identité et le rôle (étape 2).
   - **Publique volontairement anonyme** (formulaire de contact) : validateurs stricts, limitation de débit, aucune donnée sensible renvoyée (étape 4).
2. Créer des helpers d'accès dans `convex/model/auth.ts` :
   ```ts
   import type { MutationCtx, QueryCtx } from '../_generated/server';

   export async function requireIdentity(ctx: QueryCtx | MutationCtx) {
     const identity = await ctx.auth.getUserIdentity();
     if (identity === null) {
       throw new Error('Non authentifié');
     }
     return identity;
   }

   export async function requireAdmin(ctx: QueryCtx | MutationCtx) {
     const identity = await requireIdentity(ctx);
     const user = await ctx.db
       .query('users')
       .withIndex('by_token', (q) => q.eq('tokenIdentifier', identity.tokenIdentifier))
       .unique();
     if (user === null || user.role !== 'admin') {
       throw new Error('Accès refusé');
     }
     return user;
   }
   ```
   `getUserIdentity()` renvoie `null` si l'appel est anonyme, sinon un objet avec au moins `tokenIdentifier`, `subject` et `issuer`. Le rôle se lit dans une table `users` (index `by_token` sur `tokenIdentifier` à déclarer dans `schema.ts`) ou dans une revendication personnalisée du jeton si votre fournisseur d'authentification en émet.
3. Les utiliser dans chaque fonction sensible :
   ```ts
   import { mutation } from './_generated/server';
   import { v } from 'convex/values';
   import { requireAdmin } from './model/auth';

   export const supprimerLead = mutation({
     args: { id: v.id('leads') },
     handler: async (ctx, args) => {
       await requireAdmin(ctx);
       await ctx.db.delete('leads', args.id);
     },
   });
   ```
   (Sur une version de `convex` antérieure à 1.31, écrire `ctx.db.delete(args.id)`.)
4. **Formulaire public anonyme** : garder la mutation publique mais borner l'entrée et limiter les abus.
   ```ts
   export const creer = mutation({
     args: { email: v.string() },
     handler: async (ctx, args) => {
       const email = args.email.trim().toLowerCase();
       if (email.length > 254 || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
         throw new Error('E-mail invalide');
       }
       await ctx.db.insert('leads', { email, source: 'site' });
     },
   });
   ```
   Ajouter une limitation de débit (composant Convex « Rate Limiter ») et un anti-spam (champ piège, Turnstile) côté formulaire.
5. **Ne jamais** se fier à un identifiant fourni par le client (`userId`, `email` dans `args`) pour décider des droits : dériver l'utilisateur de `ctx.auth`.
6. Appels serveur → Convex depuis Astro (`ConvexHttpClient`) : seules les fonctions publiques sont joignables. Transmettre le jeton de l'utilisateur (`client.setAuth(token)`) plutôt que d'ouvrir une fonction sans contrôle.

## Critères d'acceptation

- [ ] Chaque mutation et action publique vérifie l'identité (helper) ou est volontairement anonyme, bornée et limitée en débit
- [ ] Les fonctions réservées au serveur sont des `internal*` et référencées via `internal.`
- [ ] L'appel anonyme `curl` sur une fonction protégée renvoie une erreur
- [ ] Aucune régression : les parcours connectés fonctionnent, `npx convex dev --once` compile sans erreur de types

## Vérification après correction

```bash
npx convex dev --once          # déploie sur le déploiement de développement et vérifie les types
python3 scripts/astro_scan.py . --out /tmp/verif   # le constat « sans vérification d'identité » doit disparaître
```

Le script ne reconnaît que certains noms de helper (`requireAdmin`, `requireAuth`, `requireUser`, `getUserIdentity`…) : un helper avec un autre nom donne un faux positif, à justifier en revue.

## Pièges et retour arrière

- Passer une fonction en `internal*` casse les appels `api.fichier.nom` existants (client, Astro) : chercher toutes les références avant (`grep -rn "api\.leads" src convex`).
- Une `query` publique qui renvoie des données personnelles doit aussi être protégée (l'audit automatique ne signale que les mutations et actions).
- Retour arrière : `git revert` puis `npx convex deploy` ; les données modifiées entre-temps ne reviennent pas seules (exporter une sauvegarde avant : `npx convex export --path sauvegarde.zip`).

## Pour aller plus loin

- https://docs.convex.dev/auth/functions-auth : `ctx.auth.getUserIdentity()` et champs d'identité.
- https://docs.convex.dev/functions/internal-functions : fonctions internes et appel via `internal`.
- https://docs.convex.dev/understanding/best-practices/ : validateurs et contrôle d'accès sur toutes les fonctions publiques.
