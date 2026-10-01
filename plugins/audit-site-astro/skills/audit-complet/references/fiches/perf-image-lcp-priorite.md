---
id: perf-image-lcp-priorite
titre: "Image principale (LCP) chargée trop tard, ou priorité donnée à trop d'images"
domaine: Performance
severite_type: haute
effort: S
declencheurs:
  - "crawl:lazy_first_img"
  - "code:Aucune <Image> marquée `priority`"
  - "code:images en `priority`"
  - "http:Aucune image avec fetchpriority"
  - "http:une seule devrait"
  - "http:prop `priority` → decoding=sync"
  - "lighthouse:lcp-lazy-loaded|prioritize-lcp-image|lcp-discovery-insight|L'image Largest Contentful Paint a eu un chargement différé|Précharger l'image Largest Contentful Paint|Détection de la requête LCP"
versions_astro: ">=5.10 pour la prop priority ; avant : attributs manuels"
sources:
  - https://docs.astro.build/en/reference/modules/astro-assets/
  - https://web.dev/articles/optimize-lcp
  - https://web.dev/articles/fetch-priority
---

# Image principale (LCP) chargée trop tard, ou priorité donnée à trop d'images

> **En une phrase** : l'image la plus visible en haut de page (souvent le LCP) est chargée en différé ou sans priorité, ou au contraire toutes les images se disputent la priorité, et l'affichage principal arrive plus tard qu'il ne devrait.

## Pourquoi c'est important

Le LCP (Largest Contentful Paint) mesure quand le plus gros élément visible s'affiche ; Google demande 2,5 s ou moins pour 75 % des visites. Quand cet élément est une image, deux erreurs coûtent cher : la mettre en `loading="lazy"` (le navigateur attend de connaître la mise en page avant de la télécharger : « ne jamais lazy-loader l'image LCP », dit web.dev) et ne pas lui donner `fetchpriority="high"`. Inversement, marquer plusieurs images en priorité annule l'effet : elles se partagent la bande passante.

## Comment le constater soi-même

```bash
# Image en priorité dans le HTML servi : il doit y en avoir UNE (celle du haut de page)
curl -s https://SITE/ | grep -oE '<img[^>]*fetchpriority="high"[^>]*>'
# Première image de la page : ne doit pas être en lazy
curl -s https://SITE/ | grep -oE '<img[^>]*>' | head -1
# Élément LCP mesuré (mobile)
grep -i "Élément LCP" /tmp/verif/pagespeed-summary.md
```

Problème présent : la première `<img>` porte `loading="lazy"`, ou aucune image n'a `fetchpriority="high"`, ou plusieurs l'ont. Corrigé : exactement une image (l'image LCP) avec `loading="eager"`, `fetchpriority="high"`, `decoding="sync"`.

## Correction

1. **Identifier l'image LCP** sur mobile ET desktop (l'élément peut différer) : rapport Lighthouse, ou DevTools > Performance > LCP. Une page peut aussi avoir un LCP texte : dans ce cas, ne rien marquer en priorité.
2. **Astro ≥ 5.10** : ajouter la prop `priority` sur cette seule image (elle règle `loading="eager"`, `decoding="sync"`, `fetchpriority="high"`).

```astro
---
import { Image } from 'astro:assets';
import hero from '../assets/hero.jpg';
---
<Image src={hero} alt="Description utile de l'image" priority />
```

3. **Astro < 5.10** : mettre les attributs à la main.

```astro
<Image src={hero} alt="Description utile de l'image" loading="eager" decoding="sync" fetchpriority="high" />
```

4. **Retirer la priorité des autres images** : garder `priority` sur une seule image par page. Le logo, les images d'un carrousel (sauf la première diapositive visible), les vignettes et tout ce qui est sous la ligne de flottaison restent en chargement différé (comportement par défaut d'`<Image />`).
5. **Corriger un `loading="lazy"` sur la première image** (clé `lazy_first_img`) : supprimer l'attribut ou passer `loading="eager"`. Si l'image est dans un composant partagé (carte, en-tête), ajouter une prop pour ne mettre `priority` que sur la première occurrence.
6. **LCP découvert trop tard** (audit « Détection de la requête LCP ») : l'image doit être dans le HTML envoyé par le serveur. Ne pas l'afficher via un îlot `client:only` ni via `background-image` CSS. Si un fond CSS est indispensable, préférer une `<img>` positionnée en absolu, ou précharger : `<link rel="preload" as="image" href="/_astro/hero.AbC123.webp" fetchpriority="high" />` dans le `<head>` (URL à récupérer dans le HTML construit).
7. **Image servie par Convex ou un CMS** : elle doit aussi passer par `<Image />` (voir `perf-images-convex-storage`), sinon `priority` n'a aucun effet sur son poids.

## Critères d'acceptation

- [ ] Le HTML servi contient au plus une image avec `fetchpriority="high"` par page, et c'est l'image LCP
- [ ] La première image visible n'a pas `loading="lazy"`
- [ ] Lighthouse : « L'image Largest Contentful Paint n'a pas eu de chargement différé » et plus d'alerte sur la détection de la requête LCP
- [ ] LCP mobile en amélioration (viser ≤ 2,5 s) ; aucune régression sur les autres pages

## Vérification après correction

```bash
curl -s https://SITE/ | grep -oE '<img[^>]*fetchpriority="high"[^>]*>' | wc -l
bash scripts/http_checks.sh https://SITE/ /tmp/verif    # section 4 bis
bash scripts/lighthouse_run.sh /tmp/verif https://SITE/
```

## Pièges et retour arrière

- `priority` sur une image qui n'est pas visible au chargement (menu caché, onglet, diapositive 2) télécharge inutilement un fichier lourd en premier.
- Une image LCP différente sur mobile et desktop : utiliser `<Picture>` avec des sources adaptées, plutôt que deux images en priorité.
- Retour arrière : retirer la prop `priority`.

## Pour aller plus loin

- https://docs.astro.build/en/reference/modules/astro-assets/ : prop `priority` d'`<Image />`.
- https://web.dev/articles/optimize-lcp : les quatre phases du LCP et leur répartition idéale.
- https://web.dev/articles/fetch-priority : quand et comment utiliser `fetchpriority`.
