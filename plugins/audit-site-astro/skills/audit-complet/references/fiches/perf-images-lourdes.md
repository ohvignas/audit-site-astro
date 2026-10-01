---
id: perf-images-lourdes
titre: Images de plus de 200 Ko servies sur le site
domaine: Performance
severite_type: moyenne
effort: S
declencheurs:
  - "crawl:image_lourde"
sources:
  - https://docs.astro.build/en/guides/images/
  - https://web.dev/articles/serve-images-with-correct-dimensions
---

# Images de plus de 200 Ko servies sur le site

> **En une phrase** : une image de plus de 200 Ko est téléchargée en entier par chaque visiteur, ce qui retarde l'affichage (LCP) surtout en 4G, alors qu'une version redimensionnée en pèserait souvent dix fois moins.

## Pourquoi c'est important

Chaque image de plus de 200 Ko retarde le LCP en 4G et consomme le forfait des visiteurs mobiles. Le cas typique : un avatar de 112 px affiché à partir d'un fichier de 189 Ko placé dans `public/`, que PageSpeed Insights chiffre à près de 300 Ko d'économie sur la page. Les fichiers de `public/` sont recopiés tels quels : Astro ne les redimensionne ni ne les convertit.

## Comment le constater soi-même

```bash
curl -sI https://SITE/chemin-de-l-image.png | grep -i content-length
# Dimensions réelles du fichier (macOS / Linux)
curl -s https://SITE/chemin-de-l-image.png -o /tmp/i.png && file /tmp/i.png
```

Problème présent : `content-length` supérieur à 204800 pour une image affichée en petit. Corrigé : moins de 200 Ko, à dimensions d'affichage égales.

## Correction

1. Déplacer l'image de `public/` vers `src/assets/` et l'afficher avec le composant `Image` : Astro génère des versions redimensionnées, converties en WebP ou AVIF et au nom hashé.

```astro
---
import { Image } from 'astro:assets';
import avatar from '../assets/agent-avatar.png';
---
<Image src={avatar} widths={[112, 224]} sizes="112px" alt="Assistant virtuel du site" />
```

2. Image hébergée ailleurs (stockage Convex par exemple) : la passer par l'endpoint `/_image` en déclarant le domaine dans `image.remotePatterns` de `astro.config.mjs`, puis utiliser `<Image src="https://…" width={…} height={…} alt="…" />`.
3. Hors Astro ou fichier à garder dans `public/` : l'exporter en AVIF ou WebP à la taille d'affichage (deux fois la taille d'affichage au plus pour les écrans Retina).

## Critères d'acceptation

- [ ] La clé `image_lourde` n'apparaît plus dans `issues.json`
- [ ] Chaque image du site pèse moins de 200 Ko transférés
- [ ] Rendu identique à l'œil, sans flou sur écran Retina

## Vérification après correction

```bash
curl -sI https://SITE/_astro/avatar.AbC123.webp | grep -i content-length
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif
```

## Pièges et retour arrière

- Une image redimensionnée trop petite devient floue sur écran Retina : prévoir `densities={[1, 2]}` ou une largeur double.
- Retour arrière : remettre le fichier d'origine dans `public/` et le `<img>` précédent.

## Pour aller plus loin

- https://docs.astro.build/en/guides/images/ : le composant `Image`, `src/assets/` et `public/`.
- https://web.dev/articles/serve-images-with-correct-dimensions : servir des images à la bonne taille.
