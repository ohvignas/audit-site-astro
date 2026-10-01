---
id: perf-images-formats-modernes
titre: Images trop lourdes ou dans un format ancien (pas d'AVIF/WebP, compression faible)
domaine: Performance
severite_type: moyenne
effort: S
declencheurs:
  - "code:<Picture> sans AVIF"
  - "http:> 250 Ko"
  - "lighthouse:modern-image-formats|uses-optimized-images|efficient-animated-content|image-delivery-insight|Diffusez des images aux formats nouvelle génération|Encodez les images de manière efficace|Utilisez des formats vidéo pour le contenu animé|Améliorer l'affichage des images"
sources:
  - https://docs.astro.build/en/reference/modules/astro-assets/
  - https://docs.astro.build/en/guides/images/
  - https://web.dev/articles/choose-the-right-image-format
---

# Images trop lourdes ou dans un format ancien (pas d'AVIF/WebP, compression faible)

> **En une phrase** : les images sont servies en JPEG/PNG/GIF ou en WebP trop peu compressé, alors qu'AVIF et WebP les allègent de 30 à 80 %.

## Pourquoi c'est important

Les images représentent en général plus de la moitié du poids d'une page. AVIF est en moyenne nettement plus léger que WebP, lui-même plus léger que JPEG à qualité visuelle égale. Un GIF animé est souvent 5 à 20 fois plus lourd qu'une vidéo MP4/WebM équivalente. Lighthouse chiffre le gain en Kio et en millisecondes (audits « Diffusez des images aux formats nouvelle génération », « Encodez les images de manière efficace », « Utilisez des formats vidéo pour le contenu animé », et l'analyse « Améliorer l'affichage des images »). Plus l'image est lourde, plus le LCP monte (seuil : 2,5 s).

## Comment le constater soi-même

```bash
# Poids et type réels des images d'une page
curl -s https://SITE/ | grep -oE '(src|srcset)="[^"]+\.(jpe?g|png|gif|webp|avif)[^"]*"' | head
curl -sI https://SITE/_astro/hero.AbC123.webp | grep -iE 'content-type|content-length'
# Dans le code : <Picture> sans avif
grep -rn "<Picture" src | grep -v avif
```

Problème présent : `content-type: image/jpeg` ou `image/png` sur une photo, ou plus de 250 Ko pour une image de contenu. Corrigé : `image/avif` (ou `image/webp`) et généralement moins de 100 Ko pour une image de contenu.

## Correction

1. Vérifier d'abord que les images passent par Astro (sinon commencer par `perf-images-brutes-public`) : le format ne se choisit que pour les images `astro:assets`.
2. **Photos et grands visuels** : `<Picture />` avec AVIF en premier, WebP ensuite (le navigateur prend le premier format qu'il comprend, l'`<img>` de repli sert les autres).

```astro
---
import { Picture } from 'astro:assets';
import hero from '../assets/hero.jpg';
---
<Picture
  src={hero}
  formats={['avif', 'webp']}
  quality="mid"
  alt="Description utile de l'image"
/>
```

3. **Image simple** : `<Image />` produit du WebP par défaut ; forcer l'AVIF si le rendu est bon : `<Image src={photo} format="avif" quality="mid" alt="…" />`. `quality` accepte `low`, `mid`, `high`, `max` ou un nombre de 0 à 100. `mid` suffit pour la plupart des photos ; comparer à l'œil avant de descendre plus bas.
4. **Réglage global** (sharp, service par défaut) dans `astro.config.mjs` si les sorties restent trop lourdes :

```js
import { defineConfig } from 'astro/config';

export default defineConfig({
  image: {
    service: {
      entrypoint: 'astro/assets/services/sharp',
      config: { webp: { effort: 6 } },
    },
  },
});
```

5. **GIF animés** : les convertir en vidéo et remplacer la balise (les commandes ffmpeg sont à lancer par un humain sur son poste) :

```bash
ffmpeg -i anim.gif -movflags +faststart -pix_fmt yuv420p -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" anim.mp4
```

```html
<video autoplay loop muted playsinline width="640" height="360" poster="/anim-poster.webp">
  <source src="/anim.mp4" type="video/mp4" />
</video>
```

6. **Images déjà trop grandes en pixels** : ne pas envoyer une image de 4000 px pour un emplacement de 800 px (voir `perf-images-responsives`).
7. **Logos et icônes** : préférer le SVG (voir `perf-svg-optimisation`) plutôt qu'un PNG.

## Critères d'acceptation

- [ ] Les images de contenu sortent en AVIF ou WebP (`content-type: image/avif` ou `image/webp`)
- [ ] Aucune image de contenu au-dessus de 250 Ko (au-dessus de 100 Ko, vérifier qu'elle est justifiée)
- [ ] Plus de GIF animé lourd ; les vidéos courtes sont en MP4/WebM
- [ ] Les audits Lighthouse « formats nouvelle génération » et « Encodez les images » ne sont plus signalés
- [ ] Aucune régression visuelle (pas de bandes, de flou ni de couleurs ternes)

## Vérification après correction

```bash
npm run build && du -sh dist/_astro && ls -lS dist/_astro | head
bash scripts/http_checks.sh https://SITE/ /tmp/verif   # section 4 bis
bash scripts/lighthouse_run.sh /tmp/verif https://SITE/
```

## Pièges et retour arrière

- L'encodage AVIF est plus lent : le build peut durer plus longtemps sur un site avec beaucoup d'images (le cache de `node_modules/.astro` accélère les builds suivants ; ne pas le supprimer en CI si possible).
- Les images PNG avec transparence passées en JPEG perdent la transparence ; laisser WebP/AVIF, qui la gèrent.
- Retour arrière : retirer `avif` de `formats` ou `format="avif"`.

## Pour aller plus loin

- https://docs.astro.build/en/reference/modules/astro-assets/ : props `format`, `formats`, `quality`.
- https://docs.astro.build/en/guides/images/ : services d'image et configuration.
- https://web.dev/articles/choose-the-right-image-format : quel format pour quel usage.
