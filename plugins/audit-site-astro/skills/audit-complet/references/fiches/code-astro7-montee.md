---
id: code-astro7-montee
titre: Configuration à corriger avant la montée en Astro 7 (options experimental, @astrojs/db, src/fetch.ts)
domaine: Code
severite_type: moyenne
effort: M
declencheurs:
  - "code:Options experimental à retirer ou à sortir avant Astro 7"
  - "code:@astrojs/db n'est plus pris en charge"
  - "code:src/fetch\\.ts est un fichier réservé"
versions_astro: ">=6.0 pour préparer la montée ; ces corrections se font avant de passer en 7.0"
sources:
  - https://docs.astro.build/en/guides/upgrade-to/v7/
---

# Configuration à corriger avant la montée en Astro 7 (options experimental, @astrojs/db, src/fetch.ts)

> **En une phrase** : certains réglages de votre projet n'existent plus (ou ont changé de place) en Astro 7, et le build casse à la montée de version tant qu'ils restent.

## Pourquoi c'est important

Astro 7 a stabilisé ou retiré plusieurs options expérimentales, supprimé le paquet `@astrojs/db` et réservé le fichier `src/fetch.ts`. Sur Astro 6 le constat est une anticipation (gravité basse) ; sur Astro 7 il est à traiter tout de suite. Un projet qui les garde ne se construit plus (option inconnue, paquet absent) ou se comporte autrement (un `src/fetch.ts` à vous est lu comme le fichier de routage avancé d'Astro). Les corriger avant la montée, une majeure à la fois, évite un week-end de débogage en production.

## Comment le constater soi-même

```bash
grep -n experimental -A5 astro.config.*          # options experimental présentes
grep -n "@astrojs/db" package.json astro.config.*  # intégration supprimée
ls src/fetch.ts src/fetch.js 2>/dev/null          # fichier désormais réservé
```

Présent : une de ces trois lignes répond. Corrigé : aucune ne répond (ou `fetchFile` est fixé, voir plus bas).

## Correction

1. **Options `experimental`** (guide v7) : retirer `rustCompiler`, `queuedRendering` et `advancedRouting` (comportement par défaut en Astro 7, le compilateur Rust est le seul), passer `logger` de `experimental.logger` au champ de premier niveau `logger`, et sortir `cache` et `routeRules` du bloc `experimental` vers le premier niveau :

   ```js
   // avant
   export default defineConfig({
     experimental: { rustCompiler: true, cache: { provider: memoryCache() }, routeRules: { '/blog/[...slug]': { maxAge: 300 } } },
   });
   // après
   export default defineConfig({
     cache: { provider: memoryCache() },
     routeRules: { '/blog/[...slug]': { maxAge: 300 } },
   });
   ```
2. **`@astrojs/db`** : supprimé et plus maintenu en Astro 7. Le remplacer par la base de votre projet (Convex pour un site Astro + Convex), SQLite intégré à Node.js, Drizzle ORM ou une autre bibliothèque ; migrer les données avant de retirer le paquet.
3. **`src/fetch.ts`** (ou `src/fetch.js`) : nom réservé à partir d'Astro 7. Le renommer, ou garder le nom en fixant `fetchFile: './src/router.ts'` (ou `fetchFile: null` pour désactiver la fonction) dans la configuration.
4. Monter **une majeure à la fois** (voir `code-astro-version-en-retard`), un commit par étape, en lisant le guide de chaque majeure.

## Critères d'acceptation

- [ ] Plus aucune des options retirées dans `experimental` (`grep -n experimental -A5 astro.config.*`).
- [ ] `cache` et `routeRules` au premier niveau de la configuration.
- [ ] `@astrojs/db` absent de `package.json` et de la configuration.
- [ ] `src/fetch.ts` renommé ou `fetchFile` fixé.
- [ ] `npx astro check` et `npx astro build` sans erreur.

## Vérification après correction

```bash
npx astro check && npx astro build
python3 scripts/astro_scan.py . --out /tmp/verif   # les constats de montée en Astro 7 doivent disparaître
```

## Pièges et retour arrière

- Sortir `cache` / `routeRules` de `experimental` n'a de sens qu'en Astro 7 : sur une version antérieure, ces options restent dans `experimental` ; ne faire le changement qu'au moment de la montée.
- Lire le guide de chaque majeure intermédiaire (5, 6 puis 7) : d'autres points cassants y figurent (Zod 4, Vite, compilateur Rust plus strict).
- Retour arrière : revert du commit d'étape et `npm ci` avec l'ancien lockfile.

## Pour aller plus loin

- https://docs.astro.build/en/guides/upgrade-to/v7/ : changements cassants de la v7 (options experimental, `@astrojs/db`, `src/fetch.ts`).
