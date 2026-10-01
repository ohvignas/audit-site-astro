---
id: convex-filter-sans-index
titre: Requête Convex avec .filter() sans index (parcours complet de la table)
domaine: Code
severite_type: moyenne
effort: S
declencheurs:
  - "code:\\.filter\\(\\) sur ctx\\.db\\.query sans withIndex"
sources:
  - https://docs.convex.dev/database/reading-data/indexes/
  - https://docs.convex.dev/database/reading-data/
  - https://docs.convex.dev/understanding/best-practices/
---

# Requête Convex avec .filter() sans index (parcours complet de la table)

> **En une phrase** : `ctx.db.query('table').filter(...)` lit tous les documents de la table puis en jette ; c'est lent et coûteux dès que la table grossit, alors qu'un index ne lirait que les documents utiles.

## Pourquoi c'est important

`.filter()` n'accélère rien : Convex lit chaque document de la table et applique le filtre ensuite. Tous les documents lus comptent dans la bande passante de la base, même ceux écartés. Sur quelques dizaines de lignes, aucune différence ; sur des milliers, la requête ralentit, coûte plus cher et peut atteindre les limites de lecture d'une fonction. Une requête Convex est aussi *réactive* : elle est réévaluée à chaque changement de la table, donc le coût se répète. Un index (`.index()` dans `schema.ts` + `.withIndex()`) restreint la lecture aux documents concernés.

## Comment le constater soi-même

```bash
grep -rn "\.filter(" convex --include=*.ts | grep -v _generated
grep -n "\.index(" convex/schema.ts          # index déjà déclarés
```

Tableau de bord Convex → onglet « Logs » / « Functions » : une fonction dont le nombre de documents lus est très supérieur au nombre renvoyé est suspecte. Sur une petite table figée (quelques dizaines de lignes), c'est une remarque de faible priorité.

## Correction

1. Repérer, pour chaque `.filter()`, le champ testé par égalité (`q.eq(q.field('x'), valeur)`).
2. Déclarer l'index dans `convex/schema.ts` (le nom est libre mais unique par table ; l'ordre des champs compte) :
   ```ts
   import { defineSchema, defineTable } from 'convex/server';
   import { v } from 'convex/values';

   export default defineSchema({
     leads: defineTable({
       email: v.string(),
       source: v.string(),
       traite: v.boolean(),
     })
       .index('by_email', ['email'])
       .index('by_traite', ['traite']),
   });
   ```
   Convex ajoute automatiquement `_creationTime` à la fin de chaque index (tri stable). Limites : 32 index par table, 16 champs par index.
3. Remplacer le `.filter()` par `.withIndex()` :
   ```ts
   // Avant
   const leads = await ctx.db.query('leads').filter((q) => q.eq(q.field('email'), args.email)).collect();

   // Après
   const leads = await ctx.db
     .query('leads')
     .withIndex('by_email', (q) => q.eq('email', args.email))
     .take(50);
   ```
   Règle d'un intervalle d'index : d'abord des `.eq()` sur les champs dans l'ordre de l'index, puis éventuellement une borne basse (`.gt`/`.gte`) et une borne haute (`.lt`/`.lte`).
4. Cas particuliers :
   - `q.neq(...)` ne peut pas être un intervalle d'index. Si la condition est « non vide », soit le retirer (le champ est déjà obligatoire), soit stocker un booléen (`traite`, `actif`) et l'indexer.
   - Un filtre supplémentaire **après** `.withIndex()` est acceptable et n'affecte pas ce qui est lu : seul l'intervalle d'index détermine les documents parcourus.
   - Filtrer en TypeScript (`documents.filter(...)`) donne la même performance que `.filter()` de Convex et est plus lisible, mais pas plus rapide : il faut quand même réduire la lecture avec un index.
   - Recherche de texte : `searchIndex` et `.withSearchIndex()`, pas `.filter()`.
5. Supprimer les index redondants : si `by_equipe` existe et que `by_equipe_et_utilisateur` couvre déjà les mêmes préfixes, garder seulement le second (chaque index recopie la table et compte dans le stockage), sauf besoin de tri différent.
6. Tester sur le **déploiement de développement** : `npx convex dev --once` (pousse le schéma et les index vers le déploiement de développement, jamais vers la production). Le déploiement en production (`npx convex deploy`) est fait **par l'humain**, après relecture : ne pas le lancer. Sur une grosse table, signaler à l'humain qu'il peut créer l'index en mode « staged » pour ne pas bloquer le déploiement pendant le remplissage, puis l'activer une fois prêt.

## Critères d'acceptation

- [ ] Plus de `.filter()` directement sur `ctx.db.query(...)` sans `.withIndex()` (hors petites tables figées justifiées)
- [ ] Chaque `.withIndex()` référence un index déclaré dans `schema.ts`
- [ ] Le nombre de documents lus par appel est proche du nombre renvoyé (tableau de bord)
- [ ] Aucune régression : mêmes résultats qu'avant, `npx convex dev --once` sans erreur

## Vérification après correction

```bash
npx convex dev --once
python3 scripts/astro_scan.py . --out /tmp/verif   # le constat « .filter() sans withIndex » doit disparaître
```

## Pièges et retour arrière

- Une requête `.withIndex('by_email', ...)` avec un nom d'index absent du schéma échoue au déploiement (et aux types) : toujours déclarer avant d'utiliser.
- L'ordre des champs d'un index composite est déterminant : `['equipe', 'utilisateur']` sert « équipe » seule ou « équipe + utilisateur », pas « utilisateur » seul.
- Retour arrière : `git revert` du commit, puis `npx convex dev --once` ; si la version fautive est déjà en production, le déploiement en production (`npx convex deploy`) est fait par l'humain, pas par l'agent. Les index créés en trop peuvent rester sans danger.

## Pour aller plus loin

- https://docs.convex.dev/database/reading-data/indexes/ : définir des index et `withIndex`.
- https://docs.convex.dev/database/reading-data/ : `filter`, `take`, `paginate`, tri.
- https://docs.convex.dev/understanding/best-practices/ : « avoid `.filter` on database queries ».
