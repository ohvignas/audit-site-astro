---
id: convex-ssr-appels-sequentiels
titre: Appels Convex en cascade au rendu d'une page Astro (SSR)
domaine: Code
severite_type: moyenne
effort: S
declencheurs:
  # Aucun détecteur automatique à ce jour : messages proposés pour astro_scan.py (voir le rapport de rédaction)
  - "code:Appels Convex séquentiels"
sources:
  - https://docs.convex.dev/client/javascript/node
  - https://docs.convex.dev/database/reading-data/
  - https://docs.convex.dev/understanding/best-practices/
---

# Appels Convex en cascade au rendu d'une page Astro (SSR)

> **En une phrase** : une page qui enchaîne plusieurs `await client.query(...)` l'un après l'autre additionne les temps de réponse au lieu de les recouvrir, et fait grimper le TTFB.

## Pourquoi c'est important

Chaque `await` en cascade ajoute un aller-retour réseau vers Convex avant que le premier octet du HTML ne parte. Trois requêtes de 80 ms enchaînées valent 240 ms de TTFB, contre environ 80 ms si elles partent en même temps. Google considère un TTFB de 800 ms ou moins comme bon : les cascades consomment ce budget. De plus, plusieurs `client.query` distincts s'exécutent dans des transactions séparées, donc les données peuvent être incohérentes entre elles.

## Comment le constater soi-même

```bash
# Pages qui contiennent plusieurs await de requêtes Convex dans le frontmatter
grep -rnE "await \w+\.(query|mutation|action)\(" src/pages src/layouts src/components | sort
# Mesure du TTFB (3 essais) ; comparer avant/après
for i in 1 2 3; do curl -s -o /dev/null -w '%{time_starttransfer}\n' https://SITE/formations/exemple; done
```

Présent : deux appels ou plus, l'un après l'autre, dont les arguments **ne dépendent pas** du résultat précédent. Corrigé : ces appels indépendants sont lancés ensemble avec `Promise.all`, ou remplacés par une seule requête agrégée.

## Correction

1. Dans le frontmatter de la page, distinguer les appels **indépendants** (mêmes arguments d'entrée : le slug, un identifiant connu) des appels **dépendants** (qui utilisent le résultat du précédent).
2. Lancer les indépendants ensemble :
   ```astro
   ---
   // src/pages/formations/[slug].astro
   import { ConvexHttpClient } from 'convex/browser';
   import { api } from '../../../convex/_generated/api';

   export const prerender = false;

   const client = new ConvexHttpClient(import.meta.env.PUBLIC_CONVEX_URL);
   const { slug } = Astro.params;

   // Avant : trois await à la suite = trois temps additionnés
   // Après : lancés en parallèle
   const [formation, temoignages, faq] = await Promise.all([
     client.query(api.formations.parSlug, { slug: slug! }),
     client.query(api.temoignages.parFormationSlug, { slug: slug! }),
     client.query(api.faq.parFormationSlug, { slug: slug! }),
   ]);

   if (!formation) {
     return Astro.rewrite('/404');
   }
   ---
   ```
3. Pour un appel **dépendant** (il faut d'abord l'identifiant de la formation pour charger ses avis), ne pas enchaîner côté Astro : créer **une requête Convex agrégée** qui fait tout en une transaction cohérente, avec `Promise.all` pour les lectures indépendantes à l'intérieur :
   ```ts
   // convex/formations.ts
   import { query } from './_generated/server';
   import { v } from 'convex/values';

   export const pagePubliqueParSlug = query({
     args: { slug: v.string() },
     handler: async (ctx, args) => {
       const formation = await ctx.db
         .query('formations')
         .withIndex('by_slug', (q) => q.eq('slug', args.slug))
         .unique();
       if (formation === null) return null;
       const [temoignages, faq] = await Promise.all([
         ctx.db.query('temoignages').withIndex('by_formation', (q) => q.eq('formationId', formation._id)).take(20),
         ctx.db.query('faq').withIndex('by_formation', (q) => q.eq('formationId', formation._id)).take(30),
       ]);
       return { formation, temoignages, faq };
     },
   });
   ```
   Côté Astro : un seul `await client.query(api.formations.pagePubliqueParSlug, { slug })`.
4. Ne pas redemander la même donnée dans le layout, le composant d'en-tête et la page : la charger une fois dans la page et la passer en props.
5. Créer le `ConvexHttpClient` une fois (module partagé, par exemple `src/lib/convex.ts`) plutôt qu'à chaque composant.
6. Aller plus loin : si les données changent peu, prérendre la page (fiche `code-prerender-ssr-opportunites`) ou la mettre en cache (fiche `serveur-cache-html-ssr`).
7. Même règle **à l'intérieur** de Convex : dans une action, éviter d'enchaîner plusieurs `ctx.runQuery` / `ctx.runMutation` successifs (chacun est une transaction séparée) ; regrouper en une seule fonction interne.

## Critères d'acceptation

- [ ] Aucune page ne contient deux `await` Convex successifs indépendants
- [ ] Les lectures dépendantes passent par une requête Convex agrégée
- [ ] Le TTFB de la page est réduit d'au moins l'écart d'un aller-retour Convex par appel supprimé
- [ ] Aucune régression : mêmes données affichées, route inexistante toujours en 404

## Vérification après correction

```bash
for i in 1 2 3; do curl -s -o /dev/null -w '%{time_starttransfer}\n' https://SITE/formations/exemple; done
bash scripts/http_checks.sh https://SITE/ /tmp/verif
```

## Pièges et retour arrière

- `Promise.all` échoue dès qu'une promesse échoue : si une donnée est facultative (avis), l'encapsuler avec `.catch(() => [])`.
- Une requête agrégée qui lit sans limite recrée le problème de coût côté Convex : garder des `.take(n)` (fiche `convex-collect-non-borne`).
- Retour arrière : `git revert` ; le comportement fonctionnel est identique, seul le temps change.

## Pour aller plus loin

- https://docs.convex.dev/client/javascript/node : `ConvexHttpClient` côté serveur.
- https://docs.convex.dev/database/reading-data/ : jointures écrites en JavaScript, `Promise.all` pour les lectures parallèles.
- https://docs.convex.dev/understanding/best-practices/ : éviter les `ctx.runQuery` / `ctx.runMutation` consécutifs.
