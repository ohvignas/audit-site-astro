---
id: perf-images-chargement-differe
titre: Images hors écran chargées immédiatement (lazy loading absent)
domaine: Performance
severite_type: moyenne
effort: S
declencheurs:
  - "lighthouse:offscreen-images|Différez le chargement des images hors écran"
sources:
  - https://developer.mozilla.org/en-US/docs/Web/Performance/Guides/Lazy_loading
  - https://docs.astro.build/en/reference/modules/astro-assets/
  - https://web.dev/articles/browser-level-image-lazy-loading
---

# Images hors écran chargées immédiatement (lazy loading absent)

> **En une phrase** : des images situées bien plus bas que l'écran visible sont téléchargées dès l'ouverture de la page, et concurrencent les ressources dont dépend l'affichage.

## Pourquoi c'est important

Chaque image téléchargée au démarrage prend de la bande passante que l'image LCP, le CSS et les polices auraient pu utiliser, surtout sur mobile. Sur une page longue (blog, catalogue, galerie), charger 30 images d'un coup peut ajouter plusieurs Mo au chargement initial pour rien. Lighthouse le signale sous « Différez le chargement des images hors écran », avec le gain en Kio. Le chargement différé natif (`loading="lazy"`) suffit dans la plupart des cas, sans JavaScript.

## Comment le constater soi-même

```bash
# Images sans loading="lazy" dans le HTML servi
curl -s https://SITE/page | grep -oE '<img[^>]*>' | grep -vc 'loading="lazy"'
# Dans le code : <img> brutes (Astro <Image /> met lazy par défaut)
grep -rnE '<img\b' src --include=*.astro | grep -v 'loading=' | head -20
```

Problème présent : beaucoup d'`<img>` sans `loading="lazy"`, en dessous du premier écran. Corrigé : seules les 1 à 3 premières images visibles n'ont pas `lazy`.

## Correction

1. **Utiliser `<Image />` / `<Picture />`** : ils ajoutent `loading="lazy"` et `decoding="async"` par défaut (voir `perf-images-brutes-public` pour migrer les `<img>` brutes).
2. **Pour une `<img>` qui doit rester brute**, ajouter les attributs à la main, en plus de `width` et `height` :

```html
<img src="/photo.jpg" alt="Description" width="800" height="600" loading="lazy" decoding="async" />
```

3. **Ne jamais mettre `loading="lazy"` sur l'image LCP ni sur les images du premier écran** (voir `perf-image-lcp-priorite`). Pour les images « juste sous la ligne de flottaison » sur un écran de bureau, garder `lazy` ; le navigateur les charge un peu avant qu'elles n'apparaissent.
4. **Iframes** (cartes, vidéos) : `loading="lazy"` fonctionne aussi. Pour YouTube, préférer une façade (`perf-js-tiers`).
5. **Carrousels et onglets** : seule la première diapositive visible est chargée immédiatement ; les autres en `lazy`.
6. **Images de fond CSS** hors écran : les appliquer par une classe ajoutée au défilement, ou les remplacer par une `<img loading="lazy">`. Un `background-image` n'a pas de chargement différé natif.

```astro
<Image src={photo} alt="Atelier" loading="lazy" />
```

Le comportement par défaut d'`<Image />` est déjà `lazy` ; ne l'écrire que pour rendre l'intention explicite.

## Critères d'acceptation

- [ ] Les images sous la ligne de flottaison portent `loading="lazy"`
- [ ] L'image LCP et celles du premier écran ne sont pas en `lazy`
- [ ] Lighthouse : « Différez le chargement des images hors écran » n'est plus signalé (ou gain négligeable)
- [ ] Aucune image ne s'affiche avec retard visible au défilement normal

## Vérification après correction

```bash
curl -s https://SITE/page | grep -oE '<img[^>]*>' | grep -c 'loading="lazy"'
bash scripts/lighthouse_run.sh /tmp/verif https://SITE/page
```

## Pièges et retour arrière

- Un `lazy` mal placé sur l'image LCP fait perdre plusieurs centaines de ms : toujours vérifier l'élément LCP après le changement.
- Les images au sein d'un conteneur masqué (`display: none`) ne sont pas chargées tant qu'il est masqué : normal.
- Retour arrière : retirer l'attribut `loading`.

## Pour aller plus loin

- https://developer.mozilla.org/en-US/docs/Web/Performance/Guides/Lazy_loading : principes du chargement différé.
- https://docs.astro.build/en/reference/modules/astro-assets/ : valeurs par défaut de `<Image />`.
- https://web.dev/articles/browser-level-image-lazy-loading : chargement différé natif des images.
