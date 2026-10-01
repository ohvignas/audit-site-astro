---
id: convex-collect-non-borne
titre: .collect() non borné dans une requête Convex
domaine: Code
severite_type: basse
effort: S
declencheurs:
  - "code:\\.collect\\(\\) non bornés"
sources:
  - https://docs.convex.dev/database/pagination
  - https://docs.convex.dev/database/reading-data/
  - https://docs.convex.dev/understanding/best-practices/
---

# .collect() non borné dans une requête Convex

> **En une phrase** : `.collect()` charge tous les résultats en mémoire ; sur une table qui grossit, la fonction ralentit, coûte plus cher et finit par échouer, et une requête publique permet à n'importe qui de la déclencher.

## Pourquoi c'est important

La doc Convex recommande de n'utiliser `.collect()` que sur des résultats de petite taille (de l'ordre de 1000 documents au plus) : tout ce qui est lu compte dans la bande passante de la base, et une requête réactive est relue à chaque modification. Une page qui affiche « tous les articles » peut passer inaperçue avec 30 articles et devenir lente (TTFB élevé côté Astro en SSR) avec 5000. C'est aussi un point d'abus : un appel public sans limite peut être répété pour faire monter la facture.

## Comment le constater soi-même

```bash
grep -rn "\.collect()" convex --include=*.ts | grep -v _generated
```

Pour chaque occurrence : la table est-elle bornée par nature (liste de 10 catégories) ou peut-elle croître (articles, leads, commandes, avis) ? Le résultat est-il filtré par un index qui garantit une petite taille ?

## Correction

Choisir selon le besoin :

1. **Une liste limitée** (dernières entrées, accueil) : `.take(n)` avec `n` fixe et un tri explicite.
   ```ts
   export const derniers = query({
     args: {},
     handler: async (ctx) => {
       return await ctx.db.query('articles').order('desc').take(20);
     },
   });
   ```
2. **Un seul document** : `.first()` (premier ou `null`) ou `.unique()` (erreur s'il y en a plusieurs).
3. **Une liste complète paginée** (archives, admin) : `.paginate()` avec `paginationOptsValidator`.
   ```ts
   import { query } from './_generated/server';
   import { paginationOptsValidator } from 'convex/server';

   export const lister = query({
     args: { paginationOpts: paginationOptsValidator },
     handler: async (ctx, args) => {
       return await ctx.db.query('articles').order('desc').paginate(args.paginationOpts);
     },
   });
   ```
   Le résultat contient `page`, `isDone` et `continueCursor`. Côté React : `usePaginatedQuery`. Côté Astro en SSR, appeler la requête page par page avec `ConvexHttpClient` en repassant `continueCursor` :
   ```astro
   ---
   import { ConvexHttpClient } from 'convex/browser';
   import { api } from '../../convex/_generated/api';

   const client = new ConvexHttpClient(import.meta.env.PUBLIC_CONVEX_URL);
   const page = Number(Astro.url.searchParams.get('p') ?? '1');
   let resultat = await client.query(api.articles.lister, { paginationOpts: { numItems: 20, cursor: null } });
   for (let i = 1; i < page && !resultat.isDone; i++) {
     resultat = await client.query(api.articles.lister, { paginationOpts: { numItems: 20, cursor: resultat.continueCursor } });
   }
   ---
   ```
4. **Filtrer d'abord avec un index** avant tout `.collect()` sur un sous-ensemble naturellement petit (voir `convex-filter-sans-index`) : `.withIndex('by_auteur', (q) => q.eq('auteur', id)).collect()` est acceptable si un auteur a peu de documents.
5. **Compter ou agréger** (totaux, statistiques) : ne pas collecter pour compter ; stocker un compteur dénormalisé dans une table dédiée, ou utiliser les composants Convex prévus (Aggregate, Sharded Counter).
6. Si `.collect()` reste, ajouter un commentaire qui justifie la borne (« table de 12 catégories, figée »).

## Critères d'acceptation

- [ ] Chaque `.collect()` restant porte sur un résultat borné par nature, ou par un index sélectif, et le commentaire le dit
- [ ] Les listes publiques utilisent `.take(n)` ou `.paginate()`
- [ ] Le temps de réponse de la fonction reste stable quand la table double de taille
- [ ] Aucune régression : mêmes éléments affichés sur la première page, navigation vers la suite fonctionnelle

## Vérification après correction

```bash
grep -rn "\.collect()" convex --include=*.ts | grep -v _generated
npx convex dev --once
python3 scripts/astro_scan.py . --out /tmp/verif   # le constat « .collect() non bornés » doit disparaître ou se réduire aux cas justifiés
```

## Pièges et retour arrière

- Un nombre d'éléments par page trop grand recrée le problème ; rester à quelques dizaines.
- Une requête paginée est réactive : la taille d'une page peut varier quand des données sont ajoutées ou supprimées.
- Le curseur est opaque : ne jamais le fabriquer à la main, seulement le repasser tel que reçu.
- Retour arrière : `git revert` puis `npx convex dev --once` ; si la version fautive est déjà en production, le déploiement en production (`npx convex deploy`) est fait par l'humain, pas par l'agent.

## Pour aller plus loin

- https://docs.convex.dev/database/pagination : `paginate`, `paginationOptsValidator`, `usePaginatedQuery`.
- https://docs.convex.dev/database/reading-data/ : `take`, `first`, `unique`, `collect`.
- https://docs.convex.dev/understanding/best-practices/ : « only use `.collect` with a small number of results ».
