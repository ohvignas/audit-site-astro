---
id: perf-dom-html-lourd
titre: Page HTML trop lourde ou DOM trop volumineux (nombre d'éléments excessif)
domaine: Performance
severite_type: moyenne
effort: M
declencheurs:
  - "crawl:heavy_html"
  - "code:compressHTML désactivé"
  - "http:Poids HTML \\|"
  - "lighthouse:dom-size|Évitez une taille excessive de DOM|Éviter une taille excessive de DOM|Optimiser la taille du DOM"
sources:
  - https://web.dev/articles/dom-size-and-interactivity
  - https://docs.astro.build/en/reference/configuration-reference/#compresshtml
  - https://developer.mozilla.org/en-US/docs/Web/CSS/content-visibility
---

# Page HTML trop lourde ou DOM trop volumineux (nombre d'éléments excessif)

> **En une phrase** : le HTML dépasse 150 à 300 Ko ou contient plus de 1 400 éléments, ce qui ralentit le téléchargement, la mise en page et toutes les interactions.

## Pourquoi c'est important

Un DOM volumineux allonge chaque calcul de styles et de mise en page, consomme de la mémoire sur mobile et dégrade l'INP. Lighthouse alerte à partir d'environ 800 éléments et juge la situation mauvaise vers 1 400. Un HTML de plus de 300 Ko retarde aussi le FCP, surtout si la compression n'est pas active. Sur Astro, les causes typiques sont les icônes SVG en ligne répétées, deux menus (bureau + mobile) dans le HTML, les listes non paginées, les propriétés d'îlots sérialisées dans le HTML, et le CSS entièrement inséré dans chaque page.

## Comment le constater soi-même

```bash
# Poids du HTML brut, puis compressé
curl -s https://SITE/page | wc -c
curl -s -H 'Accept-Encoding: gzip' https://SITE/page | wc -c
# Nombre approximatif de balises
curl -s https://SITE/page | grep -o '<[a-zA-Z]' | wc -l
# Ce qui pèse : SVG en ligne, JSON d'îlots, styles en ligne
curl -s https://SITE/page | grep -o '<svg' | wc -l
curl -s https://SITE/page | grep -oE '<astro-island[^>]*props="[^"]{2000,}' | wc -l
curl -s https://SITE/page | grep -o '<style' | wc -l
```

Dans DevTools : console, `document.querySelectorAll('*').length`. Problème présent : plus de 1 400 éléments, HTML > 300 Ko. Corrigé : moins de 800 à 1 400 éléments et HTML < 150 Ko.

## Correction

1. **Icônes SVG répétées** : ne pas coller le même SVG 50 fois. Utiliser un sprite référencé par `<use>`, ou un fichier `<img src="/icons/fleche.svg">` (voir `perf-svg-optimisation`).

```html
<svg width="20" height="20" aria-hidden="true"><use href="/icons.svg#fleche"></use></svg>
```

2. **Listes longues** : paginer (12 à 24 éléments par page), ou charger la suite sur demande. Pour ce qui reste, laisser le navigateur ignorer le rendu hors écran :

```css
.carte { content-visibility: auto; contain-intrinsic-size: auto 320px; }
```

3. **Menus dupliqués** : un seul menu adaptatif par CSS, plutôt qu'une version bureau et une version mobile entièrement présentes dans le HTML.
4. **Props d'îlots trop grosses** : Astro sérialise les propriétés passées à un composant `client:*` dans l'attribut `props` de `<astro-island>`. Ne passer que les champs nécessaires, pas des objets complets venant de la base.

```astro
<!-- AVANT : tout l'objet -->
<Liste client:visible items={cours} />
<!-- APRÈS : uniquement ce qu'affiche le composant -->
<Liste client:visible items={cours.map((c) => ({ id: c.id, titre: c.titre }))} />
```

5. **CSS inséré partout** : vérifier `build.inlineStylesheets` (`perf-css-bloquant`).
6. **`compressHTML`** : garder l'option activée. Sur Astro 7 la valeur par défaut est `'jsx'` (supprime les espaces et sauts de ligne autour des éléments) ; `true` est la compression sans perte ; `false` ne fait rien. Contrôler le rendu après changement (espaces entre éléments en ligne).

```js
import { defineConfig } from 'astro/config';

export default defineConfig({
  compressHTML: true,
});
```

7. **Compression réseau** : vérifier qu'un `content-encoding: br` ou `gzip` est actif sur le HTML (fiches serveur).
8. **Contenu généré** (tables énormes, index de recherche inline) : déplacer vers un fichier JSON chargé à la demande.

## Critères d'acceptation

- [ ] Pages courantes sous 800 à 1 400 éléments DOM (mesure DevTools)
- [ ] HTML non compressé sous 150 Ko sur les pages courantes (les exceptions sont justifiées)
- [ ] Le crawl ne signale plus `heavy_html`
- [ ] `compressHTML` n'est pas désactivé

## Vérification après correction

```bash
curl -s https://SITE/page | wc -c
python3 scripts/crawl_site.py https://SITE --out /tmp/verif/crawl --max-pages 200
bash scripts/http_checks.sh https://SITE/ /tmp/verif
```

## Pièges et retour arrière

- La pagination change les URL et le maillage interne : prévoir les liens et le SEO de la suite.
- `content-visibility: auto` avec une mauvaise `contain-intrinsic-size` fait varier la barre de défilement.
- Retour arrière : remettre le composant ou la valeur d'origine.

## Pour aller plus loin

- https://web.dev/articles/dom-size-and-interactivity : effet de la taille du DOM sur l'interactivité.
- https://docs.astro.build/en/reference/configuration-reference/#compresshtml : option `compressHTML`.
- https://developer.mozilla.org/en-US/docs/Web/CSS/content-visibility : ignorer le rendu hors écran.
