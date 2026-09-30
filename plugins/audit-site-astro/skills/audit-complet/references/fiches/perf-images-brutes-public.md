---
id: perf-images-brutes-public
titre: Images en <img> brut ou servies depuis public/ (aucune optimisation Astro)
domaine: Performance
severite_type: moyenne
effort: M
declencheurs:
  - "code:balise\\(s\\) <img> brute\\(s\\)"
  - "code:image\\(s\\) servie\\(s\\) depuis public/"
  - "code:image\\(s\\) Markdown pointant vers public/"
sources:
  - https://docs.astro.build/en/guides/images/
  - https://docs.astro.build/en/reference/modules/astro-assets/
  - https://web.dev/articles/optimize-lcp
---

# Images en <img> brut ou servies depuis public/ (aucune optimisation Astro)

> **En une phrase** : ces images sont envoyées telles quelles au visiteur (souvent des JPEG/PNG de plusieurs centaines de Ko), sans redimensionnement, sans WebP/AVIF et sans `srcset`.

## Pourquoi c'est important

Astro ne traite que les images importées depuis `src/` et affichées avec `<Image />` ou `<Picture />` (module `astro:assets`). La documentation est claire : les fichiers de `public/` sont « servis ou copiés tels quels, sans aucun traitement », y compris quand on les cite dans du Markdown avec `![](/images/x.jpg)`. Sur mobile, une photo d'appareil de 2 à 4 Mo prend plusieurs secondes et fait exploser le LCP (seuil Google : 2,5 s). Une image bien traitée (WebP/AVIF à la bonne taille) pèse en général 5 à 10 fois moins.

## Comment le constater soi-même

```bash
# Balises <img> brutes et références à public/ dans le code
grep -rnE '<img\b' src --include=*.astro --include=*.tsx --include=*.jsx --include=*.mdx | head -30
grep -rnE '!\[[^]]*\]\(/' src --include=*.md --include=*.mdx | head -30
# Images lourdes dans public/ (plus de 200 Ko)
find public -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.gif' \) -size +200k -exec ls -lh {} \;
# Sur le site en ligne : les images optimisées ont une URL /_astro/… ou /_image?… et un srcset
curl -s https://SITE/ | grep -oE '<img[^>]*>' | head
```

Problème présent : des `<img src="/images/...jpg">` sans `srcset`. Corrigé : `src="/_astro/hero.AbC123.webp"` (ou `/_image?...`), avec `srcset`, `width` et `height`.

## Correction

1. **Sauvegarde** : créer une branche Git (`git switch -c fix/images`). Ne jamais supprimer un fichier de `public/` avant d'avoir vérifié qu'aucune autre page, e-mail, flux RSS ou `og:image` n'y renvoie (`grep -rn "images/hero.jpg" src public`).
2. Déplacer les images de contenu dans `src/assets/` : `git mv public/images/hero.jpg src/assets/hero.jpg`. Laisser dans `public/` uniquement ce qui doit garder une URL stable : favicon, `robots.txt`, image Open Graph, fichiers téléchargeables.
3. Remplacer chaque `<img>` par `<Image />` (fichier `.astro`) :

```astro
---
import { Image } from 'astro:assets';
import hero from '../assets/hero.jpg';
---
<Image src={hero} alt="Description utile de l'image" />
```

Astro lit alors les dimensions du fichier, génère WebP et ajoute `loading="lazy"`, `decoding="async"`, `width` et `height`. Pour l'image du haut de page, voir `perf-image-lcp-priorite`.

4. **Liste d'images dans une boucle** (galerie, équipe) : importer le dossier avec `import.meta.glob`.

```astro
---
import { Image } from 'astro:assets';
import type { ImageMetadata } from 'astro';
const modules = import.meta.glob<{ default: ImageMetadata }>('../assets/galerie/*.{jpg,jpeg,png}', { eager: true });
const images = Object.entries(modules).map(([chemin, m]) => ({ chemin, src: m.default }));
---
{images.map(({ chemin, src }) => <Image src={src} alt={chemin.split('/').pop() ?? ''} />)}
```

5. **Markdown / MDX** : remplacer `![Logo](/images/logo.png)` par un chemin relatif vers `src/` : `![Logo](../../assets/logo.png)`. Astro optimise alors l'image.
6. **Composant React/Vue/Svelte** : `<Image />` ne fonctionne pas dans un `.tsx`. Générer l'image côté `.astro` avec `getImage()` et passer l'URL au composant :

```astro
---
import { getImage } from 'astro:assets';
import photo from '../assets/photo.jpg';
import Carte from '../components/Carte.tsx';
const optimisee = await getImage({ src: photo, width: 800, format: 'webp' });
---
<Carte client:visible src={optimisee.src} largeur={optimisee.attributes.width} hauteur={optimisee.attributes.height} />
```

7. **Fond CSS** (`background-image: url(/img/x.jpg)`) : `getImage()` dans le `.astro` et injecter l'URL dans un attribut `style`.

## Critères d'acceptation

- [ ] `astro_scan.py` ne signale plus de `<img>` brut de contenu (les logos SVG et icônes décoratives peuvent rester)
- [ ] Aucune image de contenu de plus de 200 Ko dans `public/`
- [ ] Les images du HTML final sortent de `/_astro/` ou `/_image` en WebP/AVIF avec `width` et `height`
- [ ] Aucune régression : build OK, pages clés en 200, mise en page identique

## Vérification après correction

```bash
npm run build && ls -lh dist/_astro | grep -Ei 'webp|avif|jpg' | head
curl -s https://SITE/ | grep -oE '<img[^>]*>' | head -5
python3 scripts/astro_scan.py /chemin/projet --out /tmp/verif
```

## Pièges et retour arrière

- Le rendu peut changer : `<Image>` ajoute `width`/`height` et, avec `image.responsiveStyles`, `max-width: 100%`. Vérifier les pages à l'écran (mobile et desktop).
- Chemins Markdown relatifs : ils se calculent depuis le fichier `.md`, pas depuis la racine.
- Les images distantes ne sont optimisées que si leur domaine est autorisé (voir `perf-images-convex-storage`).
- Retour arrière : `git revert` du commit ; les anciens fichiers restent dans l'historique.

## Pour aller plus loin

- https://docs.astro.build/en/guides/images/ : `src/` contre `public/`, composants d'image.
- https://docs.astro.build/en/reference/modules/astro-assets/ : props de `<Image />`, `<Picture />`, `getImage()`.
- https://web.dev/articles/optimize-lcp : pourquoi le poids de l'image LCP compte.
