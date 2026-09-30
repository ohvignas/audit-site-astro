---
id: perf-image-service-passthrough
titre: Service d'images désactivé (passthroughImageService) - aucune image n'est optimisée
domaine: Performance
severite_type: haute
effort: S
declencheurs:
  - "code:image\\.service = passthroughImageService"
sources:
  - https://docs.astro.build/en/guides/images/
  - https://docs.astro.build/en/reference/configuration-reference/#imageservice
  - https://docs.astro.build/en/guides/integrations-guide/cloudflare/
---

# Service d'images désactivé (passthroughImageService) - aucune image n'est optimisée

> **En une phrase** : la configuration Astro remplace le service d'images par un service « sans traitement » : même avec `<Image />`, les fichiers sont recopiés tels quels, sans redimensionnement ni conversion.

## Pourquoi c'est important

`passthroughImageService()` est un service qui ne fait rien : la documentation le réserve aux hébergements qui ne peuvent pas exécuter `sharp` (certains environnements comme Cloudflare Workers). On y garde les bénéfices d'`astro:assets` (pas de décalage de mise en page, `alt` obligatoire), mais aucune image n'est allégée. Sur un serveur Node ou un hébergeur classique, c'est souvent un réglage laissé par erreur, qui annule tout le travail sur les images.

## Comment le constater soi-même

```bash
grep -n "passthroughImageService\|image:" astro.config.*
# Les images sortent-elles en WebP/AVIF ?
curl -s https://SITE/ | grep -oE '<img[^>]*>' | head -3
# Poids d'une image servie
curl -sI "https://SITE/_astro/hero.AbC123.jpg" | grep -iE 'content-type|content-length'
```

Problème présent : les images gardent leur extension et leur poids d'origine (`.jpg` de plusieurs centaines de Ko), sans `srcset` de tailles variées. Corrigé : fichiers `.webp`/`.avif` de tailles différentes.

## Correction

1. **Identifier l'hébergement**. `grep -n "adapter" astro.config.*` :
   - **`@astrojs/node`, Vercel, Netlify, VPS, Docker** : `sharp` fonctionne, il faut retirer le service passthrough.
   - **Cloudflare** : ne pas retirer sans vérifier ; utiliser l'option `imageService` de l'adapter (étape 3).
2. **Serveur Node / Vercel / Netlify** : dans `astro.config.mjs`, supprimer `image.service` et l'import `passthroughImageService`. Le service par défaut est `sharp`.

```js
// AVANT
import { defineConfig, passthroughImageService } from 'astro/config';
export default defineConfig({
  image: { service: passthroughImageService() },
});

// APRÈS
import { defineConfig } from 'astro/config';
export default defineConfig({
  image: {
    layout: 'constrained',
    responsiveStyles: true,
  },
});
```

   Avec un gestionnaire strict comme pnpm, installer `sharp` explicitement : `pnpm add sharp`. En rendu à la demande sur Node, `sharp` doit faire partie des dépendances de production (`npm ls sharp`).
3. **Cloudflare** : l'adapter propose `imageService` avec les valeurs `'passthrough'`, `'cloudflare'` (Cloudflare Image Resizing), `'cloudflare-binding'` (valeur par défaut, binding Images), `'compile'` et `'custom'`. Choisir selon votre offre Cloudflare :

```js
import cloudflare from '@astrojs/cloudflare';
import { defineConfig } from 'astro/config';

export default defineConfig({
  adapter: cloudflare({ imageService: 'cloudflare-binding' }),
});
```

4. Relancer le build et regarder la taille des images de `dist/` avant et après (`du -sh dist/_astro`).
5. Si le passthrough est voulu (hébergement sans sharp), le noter dans un commentaire du fichier de config, et faire optimiser les images en amont (sources déjà en WebP/AVIF à la bonne taille) ou via un CDN d'images.

## Critères d'acceptation

- [ ] Plus de `passthroughImageService` dans `astro.config.*` (ou choix documenté pour un hébergement sans sharp)
- [ ] Les images de contenu sont servies en WebP/AVIF avec plusieurs tailles
- [ ] Build OK et pages clés en 200
- [ ] Poids total des images de la page d'accueil en baisse mesurable

## Vérification après correction

```bash
npm run build && du -sh dist/client/_astro 2>/dev/null || du -sh dist/_astro
python3 scripts/astro_scan.py /chemin/projet --out /tmp/verif
bash scripts/lighthouse_run.sh /tmp/verif https://SITE/
```

## Pièges et retour arrière

- `sharp` est un module natif : l'image Docker de production doit être construite pour la même architecture (linux/amd64 ou arm64) que celle où les dépendances sont installées.
- Le build devient plus long et plus gourmand en mémoire.
- Retour arrière : remettre `image: { service: passthroughImageService() }` (les images repassent en brut).

## Pour aller plus loin

- https://docs.astro.build/en/guides/images/ : services d'images, sharp et passthrough.
- https://docs.astro.build/en/reference/configuration-reference/#imageservice : option `image.service`.
- https://docs.astro.build/en/guides/integrations-guide/cloudflare/ : option `imageService` de l'adapter Cloudflare.
