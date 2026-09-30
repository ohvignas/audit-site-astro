---
id: convex-args-validateurs-manquants
titre: Fonctions Convex publiques sans validateur d'arguments (args)
domaine: Code
severite_type: moyenne
effort: S
declencheurs:
  - "code:fonction\\(s\\) publique\\(s\\) sans validateur args"
sources:
  - https://docs.convex.dev/functions/validation
  - https://docs.convex.dev/understanding/best-practices/
---

# Fonctions Convex publiques sans validateur d'arguments (args)

> **En une phrase** : une `query`, `mutation` ou `action` sans `args: { … }` accepte n'importe quelle charge utile envoyée par n'importe qui, sans contrôle de type ni de forme.

## Pourquoi c'est important

La doc Convex est explicite : sans validation des arguments, un utilisateur malveillant peut appeler vos fonctions publiques avec des arguments inattendus et provoquer des effets surprenants (documents mal formés, `patch` avec des champs qu'il ne devrait pas toucher, chaînes de plusieurs mégaoctets). Les validateurs `v.*` vérifient les types à l'exécution **et** donnent à TypeScript les types des arguments. Ils protègent aussi la base : un champ `email` toujours de type chaîne, un identifiant toujours d'une table précise.

## Comment le constater soi-même

```bash
# Fonctions publiques : repérer celles dont le corps n'a pas de "args:"
grep -rnE "export const \w+ = (query|mutation|action)\(" convex --include=*.ts | grep -v _generated
# Forme dangereuse : handler qui prend un argument sans déclaration
grep -rnE "handler: async \(ctx, \{|handler: async \(ctx, args" convex --include=*.ts
```

Ouvrir chaque fonction : présent = pas de bloc `args`, ou `handler: async (ctx, args)` sans validateur. Corrigé = tous les arguments déclarés avec `v.*`.

## Correction

1. Importer `v` : `import { v } from 'convex/values';`.
2. Déclarer chaque argument avec le validateur le plus précis (`args: {}` si la fonction n'a aucun argument, pour que ce soit explicite) :
   ```ts
   import { mutation, query } from './_generated/server';
   import { v } from 'convex/values';

   export const creer = mutation({
     args: {
       email: v.string(),
       source: v.optional(v.union(v.literal('site'), v.literal('salon'), v.literal('parrainage'))),
     },
     handler: async (ctx, args) => {
       await ctx.db.insert('leads', { email: args.email.trim().toLowerCase(), source: args.source ?? 'site' });
     },
   });

   export const lister = query({
     args: { limite: v.optional(v.number()) },
     handler: async (ctx, args) => {
       return await ctx.db.query('leads').order('desc').take(Math.min(args.limite ?? 50, 100));
     },
   });
   ```
3. Validateurs utiles : `v.string()`, `v.number()`, `v.boolean()`, `v.null()`, `v.id("table")` (identifiant d'une table précise), `v.array(...)`, `v.object({...})`, `v.record(...)`, `v.union(...)`, `v.literal(...)`, `v.optional(...)`.
4. Ajouter aussi une valeur de retour vérifiée quand la forme compte, avec `returns: v.null()` ou `returns: v.array(v.object({...}))`.
5. Réutiliser les validateurs du schéma pour ne pas les dupliquer : définir `const lead = v.object({...})` dans un fichier partagé, l'utiliser dans `defineTable(...)` (objet simple) et dans `args`. Les validateurs d'objet offrent `.pick()`, `.omit()`, `.extend()`, `.partial()`.
6. Une longueur maximale n'existe pas dans `v.string()` : la vérifier dans le `handler` (`if (args.message.length > 5000) throw new Error('Trop long')`).
7. Automatiser : la règle ESLint `@convex-dev/require-argument-validators` fait échouer le lint si un `args` manque.

## Critères d'acceptation

- [ ] Toutes les `query`, `mutation` et `action` publiques déclarent `args`
- [ ] Aucun argument de type identifiant n'est un `v.string()` (utiliser `v.id('table')`)
- [ ] Les chaînes libres ont une limite de longueur vérifiée dans le `handler`
- [ ] Aucune régression : `npx convex dev --once` compile, les appels existants (client et Astro) passent les mêmes arguments

## Vérification après correction

```bash
npx convex dev --once
python3 scripts/astro_scan.py . --out /tmp/verif   # le constat « sans validateur args » doit disparaître
```

## Pièges et retour arrière

- La validation est stricte : un objet contenant des propriétés non déclarées est refusé. Un appel client qui envoie un champ en trop échouera : ajuster l'appelant ou le validateur.
- Rendre un argument obligatoire casse les appels qui ne le fournissent pas : passer par `v.optional` le temps de migrer.
- Les fonctions `internal*` gagnent aussi à être validées, même si le risque est moindre.
- Retour arrière : `git revert` puis `npx convex dev --once` ; si la version fautive est déjà en production, le déploiement en production (`npx convex deploy`) est fait par l'humain, pas par l'agent.

## Pour aller plus loin

- https://docs.convex.dev/functions/validation : validateurs d'arguments et de retour.
- https://docs.convex.dev/understanding/best-practices/ : « use argument validators for all public functions ».
