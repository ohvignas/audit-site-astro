---
id: perf-svg-optimisation
titre: Composants SVG importés en nombre, sans optimisation SVGO
domaine: Performance
severite_type: basse
effort: S
declencheurs:
  - "code:composants SVG importés, sans optimisation SVGO"
versions_astro: ">=5.7 pour les composants SVG ; >=5.16 pour experimental.svgOptimizer"
sources:
  - https://docs.astro.build/en/reference/experimental-flags/svg-optimization/
  - https://docs.astro.build/en/guides/images/#svg-components
  - https://github.com/svg/svgo
---

# Composants SVG importés en nombre, sans optimisation SVGO

> **En une phrase** : au moins cinq fichiers `.svg` sont importés comme composants (SVG en ligne dans le HTML) sans passer par un optimiseur, donc chaque page embarque le code brut des exports d'éditeur (métadonnées, décimales inutiles).

## Pourquoi c'est important

Depuis Astro 5.7, `import Logo from './logo.svg'` insère le SVG directement dans le HTML. C'est pratique (couleur pilotable en CSS, aucune requête), mais le contenu des fichiers exportés par Figma, Illustrator ou Inkscape contient des commentaires, des identifiants, des métadonnées et des coordonnées à 8 décimales. Multipliés par le nombre d'icônes et de pages, ils alourdissent le HTML et le DOM. L'optimiseur SVGO, intégré expérimentalement à Astro depuis la 5.16, réduit couramment un SVG de 30 à 70 %.

## Comment le constater soi-même

```bash
# Nombre d'imports de SVG comme composants
grep -rnE "import\s+\w+\s+from\s+['\"][^'\"]+\.svg['\"]" src | wc -l
# Poids des SVG sources
find src public -name '*.svg' -size +5k -exec ls -lh {} \;
# Poids des SVG en ligne dans une page
curl -s https://SITE/ | grep -o '<svg' | wc -l
grep -n "svgOptimizer" astro.config.*
```

Problème présent : cinq imports ou plus, aucun `svgOptimizer`, SVG de plus de 5 Ko. Corrigé : `svgOptimizer` configuré et SVG de quelques centaines d'octets.

## Correction

1. Vérifier la version : `node -p "require('./node_modules/astro/package.json').version"`. Le réglage exige Astro 5.16 ou plus. Sinon, mettre à jour Astro (`code-astro-version-en-retard`) ou optimiser les fichiers à la main avec SVGO : `npx svgo -f src/assets/icons` (à lancer par un humain, sur une copie).
2. Activer l'optimiseur dans `astro.config.mjs` :

```js
import { defineConfig, svgoOptimizer } from 'astro/config';

export default defineConfig({
  experimental: {
    svgOptimizer: svgoOptimizer(),
  },
});
```

L'optimisation a lieu uniquement lors du build de production (pas en développement) et s'applique à tous les SVG importés comme composants.
3. Réglages facultatifs (plus d'optimisation, au risque de modifier certains dessins) :

```js
svgOptimizer: svgoOptimizer({
  multipass: true,
  floatPrecision: 2,
  plugins: ['preset-default', 'removeXMLNS'],
})
```

4. **Ne pas répéter** un SVG en ligne dans une boucle (liste de 30 cartes avec la même icône) : utiliser `<img src>` ou un sprite (`perf-dom-html-lourd`). Un SVG chargé par `<img>` est mis en cache par le navigateur ; un SVG en ligne est rechargé avec chaque HTML.
5. **Gros illustrations** (plus de 20 Ko) : les servir comme fichier (`<img src>`), pas en ligne.
6. **Logos** : garder en SVG, avec `width`/`height` ou `viewBox` correct pour éviter le CLS.
7. Ouvrir les pages qui contiennent des SVG et comparer visuellement (couleurs, épaisseurs de trait, dégradés) avant et après.

## Critères d'acceptation

- [ ] `experimental.svgOptimizer` présent dans la config (Astro ≥ 5.16), ou fichiers optimisés avec SVGO
- [ ] Aucun SVG en ligne de plus de 5 Ko sans raison
- [ ] Rendu visuel des icônes et logos inchangé
- [ ] HTML des pages concernées plus léger

## Vérification après correction

```bash
npm run build
curl -s https://SITE/ | wc -c
python3 scripts/astro_scan.py /chemin/projet --out /tmp/verif
```

## Pièges et retour arrière

- Le paramètre est expérimental : son nom ou son comportement peut changer ; relire les notes de version à chaque mise à jour d'Astro.
- SVGO peut retirer un `id` ou un `viewBox` nécessaire à une animation : tester les SVG animés ou stylés par CSS.
- Retour arrière : retirer `svgOptimizer` de la config.

## Pour aller plus loin

- https://docs.astro.build/en/reference/experimental-flags/svg-optimization/ : activation et options de `svgoOptimizer()`.
- https://docs.astro.build/en/guides/images/#svg-components : composants SVG dans Astro.
- https://github.com/svg/svgo : documentation de SVGO.
