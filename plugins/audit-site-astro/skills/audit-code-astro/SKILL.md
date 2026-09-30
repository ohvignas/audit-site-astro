---
name: audit-code-astro
description: Audit de la qualité et de la santé du code d'un projet Astro (et de son backend Convex) — versions et dépendances, vulnérabilités npm, astro check, build, configuration (site, output, adapter, trailingSlash, images), architecture des îlots, rendu SSR vs prérendu, fonctions Convex (auth, validateurs, index, pagination), variables d'environnement, dette technique — avec corrections fichier:ligne. Utilise ce skill quand l'utilisateur demande une revue de son projet Astro, veut savoir si son code est propre, maintenable, à jour, bien configuré, si ses fonctions Convex sont sûres et performantes, ou avant une mise en production.
---

# Audit du code — Astro + Convex

Scripts : `../audit-complet/scripts/`. Format : `../audit-complet/references/format-constat.md`. Sortie : `rapports/code.md`.

## Données
```bash
bash $S/project_checks.sh /chemin/projet "$AUDIT/data/code" --build   # --build : build d'audit dans le dossier d'audit, jamais dans dist/
python3 $S/astro_scan.py /chemin/projet --out "$AUDIT/data/code" --dist "$AUDIT/data/code/build/client/_astro"
```
`astro_scan.py` produit des **indices** heuristiques. Ouvrir chaque fichier signalé avant d'en faire un constat : c'est ce qui distingue un audit d'un linter.

## Checklist

### 1. Socle
- **Versions** : Astro (installée vs dernière, dans `code-scan.md`), adapters, intégrations, Convex, Node (LTS ≥ 20). Montées de version majeures à planifier : lire le guide de migration officiel avant de proposer, et lister les gains concrets pour ce site (tableau des versions dans `../audit-complet/references/astro-optimisations.md`). Points de vigilance v7 : compilateur Rust (HTML invalide refusé), Vite 8, `compressHTML: 'jsx'` (espaces entre éléments inline supprimés), Markdown via Sätteri (plugins remark/rehype → installer `@astrojs/markdown-remark`), `src/fetch.ts` réservé.
- **Fonctionnalités de la version installée non exploitées** : images responsives et `priority` (5.10), API Fonts et `security.csp` (6.0), cache de routes `cache`/`routeRules` (7.0), `security.allowedDomains` (5.14.2), `astro:env` (5.0), server islands (5.0). Chacune est détectée par `astro_scan.py` ; confirmer en lisant le code.
- **`npm audit`** (production) : critiques et hautes d'abord ; vérifier que la vulnérabilité touche un chemin réellement utilisé.
- **`astro check`** : erreurs TypeScript et diagnostics. 0 erreur attendu avant toute mise en prod.
- **Build** : réussi ? Avertissements (images non optimisables, dépendances circulaires, chunks trop gros, routes dupliquées) ? Durée ?
- Lockfile versionné, scripts `package.json` clairs (`dev`, `build`, `preview`, `check`), `.env.example` à jour (noms des variables, sans valeurs).

### 2. Configuration Astro (`astro.config.*`)
- `site` : https, bon domaine, valeur réelle en production si elle vient d'une variable d'environnement (fausse, elle casse sitemap, canonical et og:url).
- `output` et prérendu : en `server`, chaque page est rendue à chaque requête. Lister les pages qui pourraient passer en `export const prerender = true` (pas de cookies, session, `Astro.request`, ni paramètres de requête ; données qui changent peu, avec rebuild ou revalidation au besoin). Gain de TTFB et de charge serveur.
- `trailingSlash`, `build.format` cohérents avec les URL publiées.
- `image` : `remotePatterns` pour les domaines d'images distantes (storage Convex), service sharp installé.
- `security.checkOrigin` actif (défaut) si formulaires ou actions ; pas de `vite.build.sourcemap: true` en prod.
- Intégrations inutilisées à retirer.

### 3. Architecture front
- **Îlots** : liste `client:*` (code-scan). Chaque `client:load` doit se justifier. Composant sans état ni interaction → `.astro`. Gros îlot qui n'est pas nécessaire au premier écran → `client:visible` + `import()` dynamique de ses dépendances lourdes.
- **Un seul framework UI** si possible (React + Svelte + Vue = plusieurs runtimes).
- `set:html` / `dangerouslySetInnerHTML` : d'où vient le HTML ? S'il vient du CMS ou d'utilisateurs, il faut un assainissement côté serveur.
- Composants SEO centralisés (un seul composant `<SEO>` ou `<BaseHead>` qui gère title, description, canonical, og, JSON-LD) plutôt que dupliqués dans chaque page.
- Images : `<Image>`/`<Picture>` partout où c'est possible ; assets dans `src/assets/`, pas dans `public/`.
- Routes dynamiques SSR : chaque `[param].astro` gère l'absence de donnée (`Astro.rewrite('/404')`).
- Middleware (`src/middleware.ts`) : ce qu'il fait à chaque requête (auth, en-têtes, redirections) et son coût (appel réseau à chaque page = TTFB).

### 4. Convex (`convex/`)
- **Frontière publique** : toute `query`, `mutation` ou `action` exportée est appelable par n'importe qui connaissant l'URL du déploiement. Pour chacune (liste dans code-scan) : doit-elle être publique ? Si elle n'est appelée que par le serveur ou un cron, la passer en `internalQuery`/`internalMutation`/`internalAction`. Si elle est publique, vérifier l'identité (`ctx.auth.getUserIdentity()`) **et** le rôle pour tout ce qui écrit, lit des données personnelles ou fait de l'administration. Ouvrir le code : l'auth peut être dans un helper (faux positif du script).
- **Validateurs `args`** sur toutes les fonctions publiques (sans eux, n'importe quel payload passe) ; pas de `v.any()` sur des entrées externes.
- **Requêtes** : `.filter()` sans `.withIndex()` = scan complet de la table. Ajouter l'index dans `schema.ts`. Sur une petite table figée, c'est une remarque basse. `.collect()` sur des tables qui grossissent → `.paginate()` ou `.take(n)`.
- **Rendu Astro ↔ Convex** : appels séquentiels au rendu SSR (`await` en cascade) → `Promise.all` ; même donnée demandée plusieurs fois par page → une requête agrégée.
- **Fichiers (storage)** : images servies brutes → voir audit-performance (optimisation via `<Image>` ou variantes à l'upload). Contrôle d'accès des fichiers privés.
- **HTTP actions** (`convex/http.ts`) : CORS (pas de `*` avec des cookies ou identifiants), vérification des signatures des webhooks (Stripe, etc.).
- **Crons et planification** : liste, fréquence, idempotence.
- Déploiement : `CONVEX_DEPLOY_KEY` uniquement côté CI/serveur, jamais dans un fichier versionné ni dans une variable `PUBLIC_`.

### 5. Hygiène et dette
- Code mort (composants et pages non référencés : `grep -rL` sur les imports), `console.log` restants, `TODO/FIXME` (compter et lister les plus importants), fichiers de plus de 400 lignes à découper.
- Tests : présence d'au moins un smoke test (build + quelques routes), lint et format (ESLint, Prettier ou Biome) en CI.
- `git status` : modifications non commitées sur le serveur de prod = dérive par rapport au dépôt (à signaler).

## Restitution
`rapports/code.md` : tableau d'identité du projet (versions, adapter, output, Convex), puis les constats `CODE-NNN` au format commun, avec `fichier:ligne` et diff proposé pour chacun.
