---
id: perf-images-collections
titre: Champs image des collections de contenu typés z.string() au lieu de image()
domaine: Performance
severite_type: moyenne
effort: S
declencheurs:
  - "code:Champs image des collections typés z\\.string\\(\\)"
sources:
  - https://docs.astro.build/en/guides/images/
  - https://docs.astro.build/en/guides/content-collections/
  - https://docs.astro.build/en/guides/upgrade-to/v6/
---

# Champs image des collections de contenu typés z.string() au lieu de image()

> **En une phrase** : la couverture des articles (`cover`, `image`, `thumbnail`…) est déclarée comme du texte, donc Astro ne peut ni la vérifier ni l'optimiser.

## Pourquoi c'est important

Avec `z.string()`, le champ n'est qu'un chemin quelconque : une faute de frappe ne fait pas échouer le build, et l'image est servie brute (souvent depuis `public/`), sans WebP/AVIF, sans `srcset` et sans dimensions (donc risque de décalage de mise en page). Avec l'assistant `image()` du schéma, Astro vérifie que le fichier existe, lit ses dimensions et fournit un objet directement utilisable par `<Image />`.

## Comment le constater soi-même

```bash
grep -nE "(image|cover|thumbnail|hero|heroImage|avatar|photo|banner)\s*:\s*z\.string\(\)" src/content.config.* src/content/config.* 2>/dev/null
# Les articles pointent vers /images/... (public/) ?
grep -rnE "^(image|cover|heroImage|thumbnail):" src/content | head
```

Problème présent : `cover: z.string()` et des valeurs `/images/x.jpg` dans le frontmatter. Corrigé : `cover: image()` et des valeurs relatives `./x.jpg`.

## Correction

1. **Sauvegarde** : branche Git. Le changement touche le schéma ET chaque fichier de contenu.
2. Modifier `src/content.config.ts` : le schéma devient une fonction qui reçoit `image`. Depuis Astro 6, `z` vient de `astro/zod` (l'import depuis `astro:content` est déprécié ; avant la v6, garder `import { defineCollection, z } from 'astro:content'`).

```ts
import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const blog = defineCollection({
  loader: glob({ pattern: '**/*.{md,mdx}', base: './src/content/blog' }),
  schema: ({ image }) =>
    z.object({
      title: z.string(),
      cover: image(),
      coverAlt: z.string(),
    }),
});

export const collections = { blog };
```

3. Dans chaque article, remplacer le chemin absolu par un chemin **relatif au fichier** vers une image de `src/` :

```yaml
---
title: "Mon article"
cover: "./couverture.jpg"
coverAlt: "Un atelier de poterie"
---
```

Déplacer l'image de `public/images/` vers `src/content/blog/` (à côté de l'article) ou `src/assets/` (dans ce cas : `../../assets/couverture.jpg`).
4. Afficher le champ avec `<Image />` (ou `<Picture />`) :

```astro
---
import { Image } from 'astro:assets';
import { getEntry } from 'astro:content';
const article = await getEntry('blog', Astro.params.slug!);
---
<Image src={article.data.cover} alt={article.data.coverAlt} />
```

5. Pour une image dans `og:image`, utiliser `getImage({ src: article.data.cover, format: 'jpg', width: 1200 })` et construire l'URL absolue avec `new URL(resultat.src, Astro.site)`.
6. Lancer `astro check` ou le build : une erreur claire signale chaque chemin d'image invalide.

## Critères d'acceptation

- [ ] Plus de champ image en `z.string()` dans `src/content.config.ts`
- [ ] `npm run build` passe sans erreur de validation
- [ ] Les couvertures sont servies depuis `/_astro/` ou `/_image` avec `srcset`, `width` et `height`
- [ ] Aucune image d'article ne reste dans `public/images/` sans raison

## Vérification après correction

```bash
npm run build
python3 scripts/astro_scan.py /chemin/projet --out /tmp/verif
curl -s https://SITE/blog/un-article/ | grep -oE '<img[^>]*>' | head -3
```

## Pièges et retour arrière

- Les articles sans image doivent utiliser `cover: image().optional()`.
- Les collections chargées par un loader distant (API, CMS) n'ont pas de fichier local : voir `perf-images-convex-storage` pour les images distantes.
- Retour arrière : remettre `z.string()` et les chemins d'origine (`git revert`).

## Pour aller plus loin

- https://docs.astro.build/en/guides/images/ : `image()` dans un schéma de collection.
- https://docs.astro.build/en/guides/content-collections/ : définir et interroger une collection.
- https://docs.astro.build/en/guides/upgrade-to/v6/ : nouvel import de `z` depuis `astro/zod`.
