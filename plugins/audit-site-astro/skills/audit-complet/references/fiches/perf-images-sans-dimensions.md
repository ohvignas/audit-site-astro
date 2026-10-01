---
id: perf-images-sans-dimensions
titre: Images sans dimensions (width/height) ou déformées, cause de décalages de mise en page
domaine: Performance
severite_type: moyenne
effort: S
declencheurs:
  - "crawl:img_no_dims"
  - "code:<img> sans width/height"
  - "lighthouse:unsized-images|image-aspect-ratio|Les éléments d'image ne possèdent pas de `width` ni de `height` explicites|Images affichées dans un format incorrect"
sources:
  - https://web.dev/articles/optimize-cls
  - https://docs.astro.build/en/guides/images/
  - https://developer.mozilla.org/en-US/docs/Web/HTML/Element/img#width
---

# Images sans dimensions (width/height) ou déformées, cause de décalages de mise en page

> **En une phrase** : le navigateur ne sait pas quelle place réserver à ces images, donc le texte saute quand elles arrivent (CLS), et certaines peuvent s'afficher étirées.

## Pourquoi c'est important

Le CLS (Cumulative Layout Shift) mesure les sauts de mise en page pendant le chargement ; Google demande 0,1 ou moins pour 75 % des visites. Une image sans `width` et `height` (ou sans `aspect-ratio` CSS) occupe 0 px, puis pousse tout le contenu vers le bas quand elle apparaît. Les navigateurs modernes calculent le ratio à partir des attributs `width` et `height` avant même le téléchargement. Lighthouse signale aussi les images affichées avec un ratio différent de leur ratio naturel (déformation).

## Comment le constater soi-même

```bash
# Sur le site : images sans width ou sans height
curl -s https://SITE/page | grep -oE '<img[^>]*>' | grep -vE 'width=.*height=|height=.*width=' | head
# Dans le code
grep -rnE '<img\b' src --include=*.astro --include=*.tsx --include=*.jsx | grep -vE 'width=.*height=|height=.*width=' | head -20
```

Problème présent : des `<img src="…">` sans les deux attributs. Corrigé : `<img … width="800" height="450">`.

## Correction

1. **Cas idéal : passer par `<Image />`** d'`astro:assets` : pour une image importée depuis `src/`, Astro ajoute lui-même `width` et `height`. Voir `perf-images-brutes-public`.

```astro
---
import { Image } from 'astro:assets';
import equipe from '../assets/equipe.jpg';
---
<Image src={equipe} alt="L'équipe devant l'atelier" />
```

2. **Image distante** (Convex, CMS) : `width` et `height` sont obligatoires, ou la prop `inferSize` (Astro ≥ 4.4) :

```astro
<Image src={url} alt="Couverture" width={1200} height={630} />
```

3. **`<img>` conservée** (SVG, image d'un composant React, contenu HTML riche) : ajouter les dimensions intrinsèques du fichier, puis laisser le CSS gérer l'affichage :

```html
<img src="/logo.svg" alt="Logo Exemple" width="160" height="40" />
```

```css
img { max-width: 100%; height: auto; }
```

`height: auto` garde le bon ratio quand la largeur est réduite.

4. **Image en arrière-plan ou de taille variable** : réserver l'espace avec `aspect-ratio`.

```css
.vignette { aspect-ratio: 16 / 9; width: 100%; object-fit: cover; }
```

5. **Images déformées** (audit « Images affichées dans un format incorrect ») : ne pas forcer à la fois `width` et `height` en CSS avec des valeurs qui changent le ratio. Utiliser `object-fit: cover` (recadrage) ou `contain`, ou corriger le ratio des attributs.
6. **Contenu Markdown/CMS** : une feuille de style qui impose `height: auto` évite la déformation ; les images Markdown locales reçoivent leurs dimensions d'Astro.
7. Les `iframe` (YouTube, cartes) et `video` doivent aussi avoir `width`/`height` ou `aspect-ratio` (voir `perf-cls`).

## Critères d'acceptation

- [ ] Le crawl ne signale plus `img_no_dims` (ou seulement des images décoratives justifiées)
- [ ] Lighthouse : « Les éléments d'image possèdent une `width` et une `height` explicites » réussi
- [ ] CLS ≤ 0,1 sur mobile pour les pages concernées
- [ ] Aucune image étirée ou écrasée à l'écran

## Vérification après correction

```bash
curl -s https://SITE/page | grep -oE '<img[^>]*>' | grep -vcE 'width=.*height=|height=.*width='
python3 scripts/crawl_site.py https://SITE --out /tmp/verif/crawl --max-pages 200   # clé img_no_dims dans issues.json
bash scripts/lighthouse_run.sh /tmp/verif https://SITE/page
```

## Pièges et retour arrière

- Des dimensions fausses provoquent des déformations : prendre la taille réelle du fichier (`file image.jpg`, ou l'aperçu du système).
- Sans `height: auto` en CSS, un `height="450"` peut rester figé quand la largeur diminue sur mobile.
- Retour arrière : retirer les attributs ajoutés (le CLS reviendra).

## Pour aller plus loin

- https://web.dev/articles/optimize-cls : causes du CLS et corrections.
- https://docs.astro.build/en/guides/images/ : dimensions automatiques des images importées.
- https://developer.mozilla.org/en-US/docs/Web/HTML/Element/img#width : attributs `width` et `height`.
