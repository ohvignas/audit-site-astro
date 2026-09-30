---
id: convex-stockage-controle-acces
titre: Fichiers du storage Convex accessibles ou téléversables sans contrôle d'accès
domaine: Code
severite_type: haute
effort: M
declencheurs:
  # Aucun détecteur automatique à ce jour : messages proposés pour astro_scan.py (voir le rapport de rédaction)
  - "code:generateUploadUrl sans vérification d'identité"
  - "code:storage\\.getUrl sur des fichiers privés"
sources:
  - https://docs.convex.dev/file-storage/serve-files
  - https://docs.convex.dev/file-storage/upload-files
  - https://docs.convex.dev/functions/http-actions
---

# Fichiers du storage Convex accessibles ou téléversables sans contrôle d'accès

> **En une phrase** : une URL de fichier Convex (`ctx.storage.getUrl`) est publique pour quiconque la possède, et une mutation `generateUploadUrl` ouverte permet à n'importe qui de remplir votre stockage.

## Pourquoi c'est important

Selon la doc Convex, les URL renvoyées par `getUrl` sont des URL « porteur » : toute personne qui les détient accède au fichier, sans autre authentification, et elles ne s'invalident pas d'elles-mêmes. Pour des contrats, factures ou documents personnels, une URL qui fuite (historique, e-mail transféré, capture d'écran) donne un accès permanent. Côté dépôt, une mutation qui appelle `generateUploadUrl()` sans vérifier l'identité laisse n'importe qui téléverser des fichiers (coût de stockage, contenu illicite hébergé sous votre nom).

## Comment le constater soi-même

```bash
grep -rnE "generateUploadUrl|storage\.getUrl|storage\.get\(|storage\.store\(" convex --include=*.ts | grep -v _generated
grep -rnE "storage\.getUrl|convex\.cloud/api/storage" src        # URL de fichiers exposées dans les pages
```

Pour chaque `getUrl` : le fichier est-il **public par nature** (logo, image d'article) ou **privé** (document d'un utilisateur) ? Pour chaque `generateUploadUrl` : la mutation appelle-t-elle `ctx.auth.getUserIdentity()` ?

## Correction

1. **Trier** : fichiers publics (`getUrl` acceptable, éventuellement via `<Image>` pour l'optimisation) et fichiers privés (étapes 3 à 5).
2. **Protéger le téléversement** : identité obligatoire, et enregistrement du propriétaire ensuite.
   ```ts
   // convex/fichiers.ts
   import { mutation } from './_generated/server';
   import { v } from 'convex/values';

   export const genererUrlTeleversement = mutation({
     args: {},
     handler: async (ctx) => {
       const identity = await ctx.auth.getUserIdentity();
       if (identity === null) throw new Error('Non authentifié');
       return await ctx.storage.generateUploadUrl();
     },
   });

   export const enregistrer = mutation({
     args: { storageId: v.id('_storage'), nom: v.string() },
     handler: async (ctx, args) => {
       const identity = await ctx.auth.getUserIdentity();
       if (identity === null) throw new Error('Non authentifié');
       const meta = await ctx.db.system.get(args.storageId);   // taille, contentType, sha256
       if (meta === null || meta.size > 10 * 1024 * 1024) {
         await ctx.storage.delete(args.storageId);
         throw new Error('Fichier refusé');
       }
       await ctx.db.insert('documents', {
         storageId: args.storageId,
         nom: args.nom.slice(0, 200),
         proprietaire: identity.tokenIdentifier,
       });
     },
   });
   ```
   L'URL de téléversement est à durée courte (1 heure). Vérifier la taille et le type après coup et supprimer (`ctx.storage.delete`) ce qui est refusé. Sur `convex` 1.31 ou plus, la doc propose aussi la forme avec nom de table pour `ctx.db.system.get` ; vérifier la version installée.
3. **Servir un fichier privé par une HTTP action** qui contrôle les droits à **chaque** requête, au lieu de distribuer une URL `getUrl` :
   ```ts
   // convex/documents.ts : requête interne, non appelable depuis un navigateur
   import { internalQuery } from './_generated/server';
   import { v } from 'convex/values';

   export const documentAutorise = internalQuery({
     args: { id: v.string(), tokenIdentifier: v.string() },
     handler: async (ctx, args) => {
       const id = ctx.db.normalizeId('documents', args.id);
       if (id === null) return null;
       const doc = await ctx.db.get(id); // convex ≥ 1.31 accepte aussi ctx.db.get('documents', id)
       return doc !== null && doc.proprietaire === args.tokenIdentifier ? doc : null;
     },
   });
   ```
   ```ts
   // convex/http.ts
   import { httpRouter } from 'convex/server';
   import { httpAction } from './_generated/server';
   import { internal } from './_generated/api';

   const http = httpRouter();

   http.route({
     path: '/document',
     method: 'GET',
     handler: httpAction(async (ctx, request) => {
       const identity = await ctx.auth.getUserIdentity();
       if (identity === null) return new Response('Non authentifié', { status: 401 });
       const id = new URL(request.url).searchParams.get('id');
       if (id === null) return new Response('Requête invalide', { status: 400 });
       const doc = await ctx.runQuery(internal.documents.documentAutorise, { id, tokenIdentifier: identity.tokenIdentifier });
       if (doc === null) return new Response('Introuvable', { status: 404 });
       const blob = await ctx.storage.get(doc.storageId);
       if (blob === null) return new Response('Introuvable', { status: 404 });
       return new Response(blob, {
         headers: {
           'Content-Type': blob.type || 'application/octet-stream',
           'Cache-Control': 'private, no-store',
           'X-Content-Type-Options': 'nosniff',
         },
       });
     }),
   });

   export default http;
   ```
   Le point d'accès est sur le domaine `https://<déploiement>.convex.site/document?id=…`, avec l'en-tête `Authorization: Bearer <jeton>`. Limite : 20 Mo par réponse d'HTTP action ; au-delà, passer par un service de fichiers à URL signées expirantes (la doc Convex cite Cloudflare R2).
4. Ne jamais stocker ni afficher l'URL `getUrl` d'un fichier privé dans une page publique ou un e-mail.
5. Les images publiques du site (logos, articles) restent en `getUrl`, servies via `<Image>` (fiche `perf-images-convex-storage`).

## Critères d'acceptation

- [ ] `generateUploadUrl` n'est appelable qu'avec une identité valide, taille et type contrôlés
- [ ] Aucun fichier privé n'est distribué par une URL `getUrl` ; l'accès passe par une HTTP action qui vérifie les droits
- [ ] Une requête anonyme sur `/document?id=…` renvoie 401, un autre utilisateur 404
- [ ] Aucune régression : téléversement et téléchargement fonctionnent pour le propriétaire

## Vérification après correction

```bash
curl -s -o /dev/null -w '%{http_code}\n' "https://DEPLOIEMENT.convex.site/document?id=abc"     # 401 attendu (anonyme)
npx convex dev --once
```

## Pièges et retour arrière

- Une URL `getUrl` déjà distribuée reste valable tant que le fichier existe : pour la révoquer, supprimer le fichier (`ctx.storage.delete`) ou le re-téléverser sous un nouvel identifiant.
- Un contrôle d'accès basé sur l'e-mail ou un identifiant fourni par le client est contournable : n'utiliser que `ctx.auth`.
- Retour arrière : `git revert` puis `npx convex dev --once` ; si la version fautive est déjà en production, le déploiement en production (`npx convex deploy`) est fait par l'humain, pas par l'agent ; ne pas rétablir un `generateUploadUrl` anonyme.

## Pour aller plus loin

- https://docs.convex.dev/file-storage/serve-files : `getUrl`, `storage.get` et contrôle d'accès par HTTP action.
- https://docs.convex.dev/file-storage/upload-files : URL de téléversement et métadonnées.
- https://docs.convex.dev/functions/http-actions : HTTP actions, en-têtes, limites.
