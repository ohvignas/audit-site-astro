---
id: code-astro-check-build-erreurs
titre: Erreurs à astro check ou au build (types, HTML invalide, Node trop ancien)
domaine: Code
severite_type: haute
effort: M
declencheurs:
  - "projet:Lignes d'erreur : [1-9]"          # ligne « astro check » de data/code/project-checks.md
  - "projet:Code de sortie : [1-9]"            # ligne du build d'audit (--build)
  - "projet:Node \\d+ : versions récentes"     # Node < 20 détecté
sources:
  - https://docs.astro.build/en/guides/typescript/
  - https://docs.astro.build/en/guides/upgrade-to/v7/
  - https://docs.astro.build/en/reference/cli-reference/
---

# Erreurs à astro check ou au build (types, HTML invalide, Node trop ancien)

> **En une phrase** : `astro check` remonte des erreurs, ou le build d'audit échoue : le projet n'est pas prêt pour la mise en production tant que les deux ne sont pas à zéro erreur.

## Pourquoi c'est important

Un build qui échoue empêche tout déploiement ; un `astro check` en erreur signale des bugs réels (propriété inexistante, valeur `undefined` non gérée, prop manquante) qui apparaissent en production sous forme de pages cassées. Depuis Astro 7, le compilateur Rust refuse aussi le HTML invalide (balises non fermées, `<div>` dans un `<p>`) que l'ancien compilateur corrigeait en silence. Une version de Node trop ancienne fait échouer l'installation ou le build (Astro 6 et 7 exigent Node 22.12.0 ou plus).

## Comment le constater soi-même

```bash
node -v                                   # >= 22.12.0 pour Astro 6/7
npm ls @astrojs/check typescript          # doivent être installés en devDependencies
npx astro check 2>&1 | tail -30           # 0 error attendu
npx astro build > /tmp/build.log 2>&1; echo "code de sortie : $?"   # 0 attendu
grep -iE "error|warn" /tmp/build.log | sort | uniq -c | sort -rn | head
```

Présent : `Result (N files): - N errors` avec N > 0, ou un code de sortie différent de 0. Corrigé : `0 errors`, code de sortie 0.

## Correction

1. **Installer l'outil s'il manque** (astro check demande sinon à l'installer) :
   ```bash
   npm install --save-dev @astrojs/check typescript
   ```
2. **Aligner `tsconfig.json`** sur le préréglage officiel :
   ```json
   {
     "extends": "astro/tsconfigs/strict",
     "include": [".astro/types.d.ts", "**/*"],
     "exclude": ["dist"]
   }
   ```
3. **Corriger les erreurs par famille**, en lançant `npx astro check` après chaque lot :
   - `Property 'x' does not exist` / `possibly undefined` : typer les données (schéma de collection, type de retour Convex) et gérer le cas vide (`if (!doc) return Astro.rewrite('/404')`).
   - Variables d'environnement : déclarer les types dans `src/env.d.ts` (`interface ImportMetaEnv { readonly PUBLIC_CONVEX_URL: string }`) ou, mieux, via un schéma `astro:env` (voir la fiche `secu-astro-env-schema`).
   - Astro 7 « unclosed tag » / imbrication invalide : fermer les balises et corriger l'imbrication (`<p>` ne contient pas de bloc) ; le message donne le fichier et la ligne.
   - Import introuvable après une montée de version : voir la fiche `code-astro-version-en-retard` (guide de la majeure).
   - Une variable de build manquante (ex. `PUBLIC_CONVEX_URL`) fait échouer le build d'audit : la fournir via `.env` local, jamais dans le dépôt.
4. **Node** : installer Node 22.12+ (`.nvmrc`, `engines` dans `package.json`, image Docker, réglage de l'hébergeur).
5. **Verrouiller le contrôle** dans `package.json` pour ne plus jamais déployer avec des erreurs de types :
   ```json
   {
     "scripts": {
       "check": "astro check",
       "build": "astro check && astro build"
     },
     "engines": { "node": ">=22.12.0" }
   }
   ```

## Critères d'acceptation

- [ ] `npx astro check` : 0 erreur (les avertissements restants sont listés et justifiés)
- [ ] `npx astro build` : code de sortie 0, sans erreur dans le log
- [ ] Node >= 22.12.0 en local, en CI et en production
- [ ] Aucune régression : pages clés en 200, rendu identique

## Vérification après correction

```bash
npx astro check && npx astro build && echo OK
bash scripts/project_checks.sh . /tmp/verif --build   # la section « astro check » doit indiquer « Lignes d'erreur : 0 »
```

## Pièges et retour arrière

- Ne pas faire taire les erreurs avec `// @ts-ignore` ou `any` en masse : cela cache les vrais bugs. Réserver `@ts-expect-error` à un cas précis, avec un commentaire.
- Ne pas désactiver `strict` dans `tsconfig.json` pour « faire passer » le check.
- `astro check` avec `build` dans le script `build` allonge le temps de build : c'est voulu.
- Retour arrière : les modifications de `tsconfig.json` et de `package.json` se défont avec `git checkout -- tsconfig.json package.json`.

## Pour aller plus loin

- https://docs.astro.build/en/guides/typescript/ : `astro check`, configuration TypeScript recommandée.
- https://docs.astro.build/en/guides/upgrade-to/v7/ : compilateur Rust plus strict en Astro 7.
- https://docs.astro.build/en/reference/cli-reference/ : commandes `astro check` et `astro build`.
