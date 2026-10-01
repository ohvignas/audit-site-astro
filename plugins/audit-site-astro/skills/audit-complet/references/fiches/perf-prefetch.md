---
id: perf-prefetch
titre: Navigation interne non accélérée (prefetch absent) et prérendu client possible
domaine: Performance
severite_type: basse
effort: S
declencheurs:
  - "code:prefetch non configuré"
  - "code:prefetch actif : experimental\\.clientPrerender"
versions_astro: ">=3.5 pour prefetch ; >=4.2 pour experimental.clientPrerender (expérimental)"
sources:
  - https://docs.astro.build/en/guides/prefetch/
  - https://docs.astro.build/en/reference/experimental-flags/client-prerender/
  - https://developer.mozilla.org/en-US/docs/Web/API/Speculation_Rules_API
---

# Navigation interne non accélérée (prefetch absent) et prérendu client possible

> **En une phrase** : quand un visiteur clique sur un lien interne, la page suivante n'est demandée qu'à ce moment-là ; le prefetch la charge à l'avance et la navigation paraît instantanée.

## Pourquoi c'est important

Sans prefetch, chaque clic déclenche une requête complète (TTFB, HTML, ressources) et le visiteur attend. Avec le prefetch d'Astro, le HTML de la page cible est récupéré quand le lien est survolé (ordinateur) ou touché juste avant le clic : la page suivante s'affiche souvent en quelques dizaines de ms. C'est un gain de ressenti sur tout le parcours, sans coût de JavaScript notable. Il n'améliore pas le LCP de la première page visitée : c'est une optimisation de confort, d'où la sévérité basse.

## Comment le constater soi-même

```bash
grep -nE "prefetch|clientPrerender" astro.config.*
grep -rn "data-astro-prefetch" src | head
# Dans le HTML servi : les liens portent-ils l'attribut ?
curl -s https://SITE/ | grep -c 'data-astro-prefetch'
```

Problème présent : ni `prefetch` dans la config, ni attribut `data-astro-prefetch`. Corrigé : `prefetch` configuré et, dans le navigateur (DevTools > Réseau), une requête de la page cible apparaît au survol d'un lien.

## Correction

1. Activer le prefetch dans `astro.config.mjs`. Recommandation prudente : stratégie `hover` (défaut), et seulement les liens marqués :

```js
import { defineConfig } from 'astro/config';

export default defineConfig({
  prefetch: {
    prefetchAll: false,
    defaultStrategy: 'hover',
  },
});
```

2. Marquer les liens importants (menu, cartes d'articles, boutons d'action) :

```astro
<a href="/tarifs" data-astro-prefetch>Tarifs</a>
<a href="/blog" data-astro-prefetch="viewport">Blog</a>
```

Stratégies : `hover` (survol ou focus, défaut), `tap` (juste avant le clic), `viewport` (dès que le lien entre dans l'écran), `load` (tous les liens après chargement de la page).
3. **Option** `prefetchAll: true` : tous les liens sont préchargés, sauf ceux marqués `data-astro-prefetch="false"`. À réserver aux petits sites : sur un site avec des centaines de liens, `viewport` ou `load` multiplient les requêtes (charge serveur, données mobiles du visiteur).
4. **Liens à exclure** : déconnexion, actions par lien GET, pages personnalisées lourdes, téléchargements.

```astro
<a href="/deconnexion" data-astro-prefetch="false">Se déconnecter</a>
```

5. **Prérendu côté navigateur (optionnel, expérimental)** : `experimental.clientPrerender` (Astro ≥ 4.2) utilise l'API Speculation Rules pour prérendre la page cible dans le navigateur (Chrome et navigateurs compatibles). Il exige que `prefetch` soit activé.

```js
export default defineConfig({
  prefetch: { prefetchAll: true, defaultStrategy: 'viewport' },
  experimental: { clientPrerender: true },
});
```

Ne l'activer qu'après test : la page prérendue exécute ses scripts (analytics, compteurs) avant d'être vue, et une page en rendu à la demande sollicite le serveur. Sur les navigateurs sans Speculation Rules, Astro retombe sur le prefetch classique.
6. **Firefox et Safari** exigent des en-têtes de cache sur la page préchargée (`Cache-Control`, `Expires` ou `ETag`) : sans eux, le prefetch est ignoré. Vérifier qu'un `Cache-Control` existe sur le HTML (voir les fiches serveur).
7. `<ClientRouter />` (View Transitions) active `prefetchAll: true` par défaut (voir `perf-view-transitions`).

## Critères d'acceptation

- [ ] `prefetch` présent dans `astro.config.*` avec une stratégie choisie
- [ ] Les liens clés portent `data-astro-prefetch` (ou `prefetchAll` volontairement activé)
- [ ] Au survol d'un lien, une requête vers la page cible apparaît dans l'onglet Réseau
- [ ] Aucun lien à effet de bord n'est préchargé

## Vérification après correction

```bash
npm run build && grep -rl "data-astro-prefetch" dist | head -3
python3 scripts/astro_scan.py /chemin/projet --out /tmp/verif
```

## Pièges et retour arrière

- Sur un site en rendu à la demande sans cache, le prefetch augmente la charge du serveur : surveiller le TTFB.
- Le prérendu client n'est pas stable : le flag peut évoluer d'une version à l'autre.
- Retour arrière : retirer `prefetch` (et `experimental.clientPrerender`) de la config.

## Pour aller plus loin

- https://docs.astro.build/en/guides/prefetch/ : stratégies, API `prefetch()` et compatibilité navigateurs.
- https://docs.astro.build/en/reference/experimental-flags/client-prerender/ : prérendu côté client.
- https://developer.mozilla.org/en-US/docs/Web/API/Speculation_Rules_API : API Speculation Rules.
