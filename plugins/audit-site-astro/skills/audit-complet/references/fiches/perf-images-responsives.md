---
id: perf-images-responsives
titre: Images non adaptées à la taille de l'écran (pas de srcset ni de sizes)
domaine: Performance
severite_type: moyenne
effort: S
declencheurs:
  - "code:Images responsives non activées"
  - "code:Images sans widths/sizes"
  - "http:pas de srcset"
  - "lighthouse:uses-responsive-images|image-size-responsive|image-delivery-insight|Dimensionnez correctement les images|Images diffusées en basse résolution|Améliorer l'affichage des images"
versions_astro: ">=5.10 pour image.layout ; widths/sizes manuels dès 3.3"
sources:
  - https://docs.astro.build/en/guides/images/#responsive-image-behavior
  - https://docs.astro.build/en/reference/configuration-reference/#imagelayout
  - https://docs.astro.build/en/reference/modules/astro-assets/
---

# Images non adaptées à la taille de l'écran (pas de srcset ni de sizes)

> **En une phrase** : un téléphone de 390 px de large télécharge la même image que l'écran d'un ordinateur (souvent 1200 à 2000 px), ce qui gaspille des centaines de Ko et retarde le LCP.

## Pourquoi c'est important

Sans attributs `srcset` et `sizes`, le navigateur n'a qu'un seul fichier à télécharger. Sur mobile, la majorité du trafic, c'est autant d'octets et de secondes perdus. Lighthouse le signale par « Dimensionnez correctement les images » (gain estimé en Kio) et, à l'inverse, par « Images diffusées en basse résolution » quand l'image est trop petite pour un écran Retina. Depuis Astro 5.10, un simple réglage génère les tailles et les attributs automatiquement.

## Comment le constater soi-même

```bash
# L'image a-t-elle un srcset ?
curl -s https://SITE/ | grep -oE '<img[^>]*>' | grep -vc srcset
# Combien d'octets un mobile télécharge-t-il ? (largeur affichée 390 px, écran x3)
curl -s https://SITE/ | grep -oE 'src="[^"]+\.(webp|avif|jpg|png)[^"]*"' | head -3
# Version d'Astro et réglage actuel
node -p "require('./node_modules/astro/package.json').version"
grep -n "layout\|responsiveStyles" astro.config.*
```

Problème présent : des `<img>` sans `srcset`/`sizes`. Corrigé : `srcset="… 640w, … 750w, … 828w …"` et `sizes="(min-width: 800px) 800px, 100vw"`.

## Correction

**Astro 5.10 ou plus récent (recommandé)** : régler une fois pour tout le site dans `astro.config.mjs`.

1. Ajouter :

```js
import { defineConfig } from 'astro/config';

export default defineConfig({
  image: {
    layout: 'constrained',
    responsiveStyles: true,
  },
});
```

`constrained` : l'image s'adapte au conteneur sans dépasser sa taille d'origine. `full-width` (bandeaux pleine largeur), `fixed` (taille fixe, ex. avatar) et `none` (aucun comportement responsive) se choisissent aussi par image avec la prop `layout`. `responsiveStyles: true` ajoute les styles CSS globaux nécessaires (`max-width: 100%`, avec une spécificité nulle : vos propres styles gardent la priorité).

2. Surcharger au cas par cas :

```astro
---
import { Image } from 'astro:assets';
import bandeau from '../assets/bandeau.jpg';
import avatar from '../assets/avatar.jpg';
---
<Image src={bandeau} alt="Vue de l'atelier" layout="full-width" />
<Image src={avatar} alt="Portrait de Claire" layout="fixed" width={96} height={96} />
```

3. Facultatif : ajuster les largeurs générées avec `image.breakpoints` (défaut pour les images locales : `[640, 750, 828, 1080, 1280, 1668, 2048, 2560]`). Moins de valeurs = moins de fichiers à construire.

**Astro < 5.10 (ou contrôle manuel)** : `widths` et `sizes` sur chaque image (Astro ≥ 3.3).

```astro
<Image
  src={photo}
  alt="Description"
  widths={[400, 800, 1200]}
  sizes="(max-width: 768px) 100vw, 800px"
/>
```

**Cas particuliers**
- Images de `public/` ou balises `<img>` brutes : aucun traitement responsive possible. Les migrer d'abord (`perf-images-brutes-public`).
- Images distantes (Convex, CMS) : domaine à autoriser, sinon pas de `srcset` (`perf-images-convex-storage`).
- Depuis Astro 6, une image n'est jamais agrandie au-delà de sa taille source : prévoir des sources assez grandes (au moins 2x la largeur affichée pour les écrans Retina).

## Critères d'acceptation

- [ ] Chaque `<img>` de contenu du HTML final a un `srcset` et un `sizes`
- [ ] Sur un test mobile Lighthouse, « Dimensionnez correctement les images » n'est plus signalé (ou gain < 20 Kio)
- [ ] Aucun décalage de mise en page nouveau (CLS ≤ 0,1) et mise en page inchangée

## Vérification après correction

```bash
npm run build
curl -s https://SITE/ | grep -oE '<img[^>]*>' | grep -c srcset
python3 scripts/astro_scan.py /chemin/projet --out /tmp/verif
bash scripts/lighthouse_run.sh /tmp/verif https://SITE/
```

## Pièges et retour arrière

- Avec Tailwind ou du CSS global, vérifier que `width`/`height` et `object-fit` ne se contredisent pas : `responsiveStyles` applique `object-fit: cover` par défaut (réglable avec `image.objectFit` ou la prop `fit`).
- Le site est plus long à construire : plus de fichiers générés par image.
- Retour arrière : retirer `layout` et `responsiveStyles` de la config.

## Pour aller plus loin

- https://docs.astro.build/en/guides/images/#responsive-image-behavior : comportement responsive et exemples.
- https://docs.astro.build/en/reference/configuration-reference/#imagelayout : `image.layout` et options liées.
- https://docs.astro.build/en/reference/modules/astro-assets/ : props `layout`, `widths`, `sizes`, `fit`.
