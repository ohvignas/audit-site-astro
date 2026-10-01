---
id: code-astro-version-en-retard
titre: Version d'Astro en retard sur la dernière version majeure
domaine: Code
severite_type: moyenne
effort: L
declencheurs:
  - "code:Astro \\d+\\.x installé, dernière version"
  - "projet:\\| (astro|@astrojs/[a-z-]+|convex) \\| .*⚠️ oui"   # tableau « Dépendances obsolètes » de project-checks.md (saut majeur)
sources:
  - https://docs.astro.build/en/upgrade-astro/
  - https://docs.astro.build/en/guides/upgrade-to/v5/
  - https://docs.astro.build/en/guides/upgrade-to/v6/
  - https://docs.astro.build/en/guides/upgrade-to/v7/
---

# Version d'Astro en retard sur la dernière version majeure

> **En une phrase** : le site tourne sur une version majeure d'Astro plus ancienne que la dernière, donc sans les optimisations récentes (images responsives, API Fonts, CSP intégrée, cache de routes) et avec des correctifs de sécurité qui ne seront plus publiés pour cette branche.

## Pourquoi c'est important

Chaque majeure apporte des gains concrets : images responsives et `priority` (5.10), API Fonts et `security.csp` stables (6.0), cache de routes stable (7.0). Les anciennes branches finissent par ne plus recevoir de correctifs de sécurité, et l'écart rend chaque montée plus coûteuse : mieux vaut monter une majeure à la fois, régulièrement. Le but n'est pas d'être « à la dernière mode » mais de garder une marche d'escalier de hauteur raisonnable.

## Comment le constater soi-même

```bash
node -p "require('./node_modules/astro/package.json').version"   # version installée
npm view astro version                                            # dernière version publiée
npm outdated astro @astrojs/node @astrojs/react @astrojs/sitemap  # écarts (adapter et intégrations compris)
node -v                                                           # Node doit satisfaire la version cible
```

Présent : la majeure installée est inférieure à la majeure publiée. Corrigé : les deux majeures sont égales.

## Correction

Toujours **une majeure à la fois** (4 → 5 → 6 → 7), un commit par étape, sur une branche dédiée.

1. Sauvegarde : `git switch -c chore/upgrade-astro && git status` (arbre propre) ; noter que `package-lock.json` (ou équivalent) est versionné.
2. Vérifier Node : Astro 6 et 7 exigent **Node 22.12.0 ou plus**. Mettre à jour Node en local, en CI et sur le serveur (`.nvmrc`, image Docker, réglage de l'hébergeur).
3. Lancer l'outil officiel, qui met à jour Astro et toutes les intégrations `@astrojs/*` ensemble :
   ```bash
   npx @astrojs/upgrade
   ```
   Pour cibler une majeure précise : `npm install astro@6 @astrojs/node@latest @astrojs/react@latest` (adapter et intégrations sur des versions compatibles avec la majeure visée).
4. Lire le guide de la majeure visée, appliquer ses points, puis lancer `npx astro check && npx astro build`. Points à connaître :
   - **4 → 5** ([guide v5](https://docs.astro.build/en/guides/upgrade-to/v5/)) : Vite 6 ; `output: 'hybrid'` supprimé (utiliser `output: 'static'` + `export const prerender = false` ciblé) ; collections de contenu sur l'API Content Layer (`src/content.config.ts`, `slug` remplacé par `id`, `render(entry)`) ; `<ViewTransitions />` devient `<ClientRouter />` ; `security.checkOrigin` actif par défaut ; les `<script>` ne sont plus remontés dans le `<head>` ; `experimental.env` devient `env`.
   - **5 → 6** ([guide v6](https://docs.astro.build/en/guides/upgrade-to/v6/)) : Node 22.12+ ; Vite 7 ; Zod 4 (`z.string().email()` devient `z.email()`) ; API legacy des collections retirée ; `<ViewTransitions />` et `Astro.glob()` supprimés (`import.meta.glob()`) ; `import.meta.env` toujours inliné ; images recadrées par défaut et jamais agrandies ; `<script>` et `<style>` rendus dans l'ordre de déclaration.
   - **6 → 7** ([guide v7](https://docs.astro.build/en/guides/upgrade-to/v7/)) : Vite 8 ; **compilateur Rust** plus strict (balises non fermées et imbrications invalides comme `<div>` dans `<p>` refusées : corriger le HTML) ; `compressHTML` vaut `'jsx'` par défaut, donc les espaces entre éléments en ligne disparaissent (ajouter `{" "}` ou fixer `compressHTML: true` pour retrouver l'ancien rendu) ; Markdown via Sätteri (les plugins remark/rehype exigent `@astrojs/markdown-remark` et `processor: unified()`) ; `src/fetch.ts` réservé (le renommer ou régler `fetchFile`) ; `@astrojs/db` retiré ; les drapeaux `experimental.cache`, `rustCompiler`, `logger`, `queuedRendering`, `advancedRouting` sont à retirer (le cache passe au premier niveau : `cache` et `routeRules`).
5. Une fois la majeure atteinte, exploiter ce qu'elle apporte (fiches dédiées : images responsives, API Fonts, `security.csp`, cache de routes).

## Critères d'acceptation

- [ ] La majeure d'`astro` égale celle de `npm view astro version`
- [ ] `@astrojs/*` (adapter, react, sitemap…) sont sur des versions compatibles, sans avertissement `peer dependency`
- [ ] `npx astro check` : 0 erreur ; `npx astro build` : code de sortie 0
- [ ] Aucune régression : pages clés en 200, mise en page identique (attention aux espaces avec `compressHTML: 'jsx'`), formulaires fonctionnels (`checkOrigin`)

## Vérification après correction

```bash
node -p "require('./node_modules/astro/package.json').version"
npx astro check && npx astro build
python3 scripts/astro_scan.py . --out /tmp/verif   # le constat « Astro N.x installé, dernière version » doit disparaître
```

## Pièges et retour arrière

- Ne pas sauter de majeure : les guides supposent qu'on vient de la précédente.
- Un build qui passe ne prouve pas que le rendu est identique : comparer visuellement l'accueil, un article et une page dynamique avant/après.
- Retour arrière : `git switch main && npm ci` (ou revert du commit d'étape) ; garder l'ancien `package-lock.json` versionné pour que `npm ci` reproduise l'état antérieur.
- Ne jamais lancer `npm audit fix --force` pour « monter » Astro : il peut sauter plusieurs majeures d'un coup.

## Pour aller plus loin

- https://docs.astro.build/en/upgrade-astro/ : procédure officielle de mise à jour (`@astrojs/upgrade`).
- https://docs.astro.build/en/guides/upgrade-to/v7/ : changements cassants de la v7.
- https://docs.astro.build/en/guides/upgrade-to/v6/ : changements cassants de la v6.
- https://docs.astro.build/en/guides/upgrade-to/v5/ : changements cassants de la v5.
