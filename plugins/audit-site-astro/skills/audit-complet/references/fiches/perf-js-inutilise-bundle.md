---
id: perf-js-inutilise-bundle
titre: JavaScript inutilisé, en double ou obsolète dans les fichiers envoyés au navigateur
domaine: Performance
severite_type: moyenne
effort: M
declencheurs:
  - "lighthouse:unused-javascript|legacy-javascript|duplicated-javascript|unminified-javascript|Réduisez les ressources JavaScript inutilisées|Évitez d'utiliser de l'ancien code JavaScript|Supprimez les modules en double|Ancien JavaScript|JavaScript en double|Réduisez la taille des ressources JavaScript"
sources:
  - https://docs.astro.build/en/guides/client-side-scripts/
  - https://docs.astro.build/en/reference/configuration-reference/#vite
  - https://web.dev/articles/reduce-javascript-payloads-with-code-splitting
  - https://developer.chrome.com/docs/lighthouse/performance/unused-javascript
---

# JavaScript inutilisé, en double ou obsolète dans les fichiers envoyés au navigateur

> **En une phrase** : le navigateur télécharge et analyse du code JavaScript dont la page n'a pas besoin (bibliothèque entière pour une fonction, modules répétés, code pour vieux navigateurs), ce qui ralentit le chargement et bloque le thread principal.

## Pourquoi c'est important

Chaque Ko de JavaScript coûte plus cher qu'un Ko d'image : il faut le télécharger, l'analyser, le compiler et l'exécuter, sur un processeur de téléphone modeste. Lighthouse chiffre en Kio le code chargé mais non exécuté (« Réduisez les ressources JavaScript inutilisées »), les modules présents en plusieurs exemplaires dans les paquets (« Supprimez les modules en double »), le code de compatibilité inutile pour les navigateurs récents (« Ancien JavaScript ») et le code non minifié. Le gain typique : 50 à 300 Ko économisés, un TBT plus bas et un LCP plus tôt.

## Comment le constater soi-même

```bash
# Poids des fichiers JS du build (brut et gzip)
npm run build
find dist -name '*.js' -path '*_astro*' -exec sh -c 'printf "%8d %8d %s\n" "$(wc -c < "$1")" "$(gzip -c "$1" | wc -c)" "$1"' _ {} \; | sort -rn | head -10
# Scripts réellement chargés par la page
curl -s https://SITE/ | grep -oE '(src|href)="[^"]+\.js"' | sort -u
```

Problème présent : un ou plusieurs fichiers de plus de 100 Ko gzip, ou Lighthouse indiquant plus de 50 Kio inutilisés. Corrigé : chaque fichier correspond à un composant réellement utilisé sur la page.

## Correction

1. **Relier chaque gros fichier à sa cause.** Le nom de `/_astro/NomDuComposant.HASH.js` reprend souvent celui de l'îlot. Pour une cartographie complète, ajouter temporairement un visualiseur (`npm i -D rollup-plugin-visualizer`) :

```js
// astro.config.mjs (à retirer une fois l'analyse faite)
import { defineConfig } from 'astro/config';
import { visualizer } from 'rollup-plugin-visualizer';

export default defineConfig({
  vite: {
    plugins: [visualizer({ filename: 'stats.html', gzipSize: true, emitFile: false })],
  },
});
```

Après `npm run build`, ouvrir `stats.html` : les plus gros rectangles sont les cibles.
2. **Importer uniquement ce qui sert.** Remplacer les imports globaux par des imports ciblés :

```ts
// AVANT : embarque toute la bibliothèque
import _ from 'lodash';
// APRÈS : uniquement la fonction (ou lodash-es, qui se prête au tree-shaking)
import debounce from 'lodash/debounce';
```

Pour les icônes, importer chaque icône individuellement (pas le paquet complet). Pour les dates, préférer `Intl.DateTimeFormat` ou une bibliothèque légère à `moment`.
3. **Ne pas hydrater ce qui n'a pas besoin de l'être.** Un composant sans interaction en `.astro` supprime son JavaScript (voir `perf-ilots-hydratation`).
4. **Charger à la demande** les modules lourds (éditeur riche, carte, graphique) avec `import()` au clic ou à l'apparition, plutôt qu'à l'ouverture.
5. **Modules en double** : lancer `npm ls NOM_DU_PAQUET` pour repérer plusieurs versions, puis `npm dedupe`. Aligner les versions dans `package.json` pour qu'une seule soit embarquée.
6. **Ancien JavaScript** : le plus souvent dû à des dépendances qui livrent du code transpilé pour de vieux navigateurs. Mettre à jour ces dépendances (`npm outdated`), ou les remplacer par des équivalents modernes. Ne pas ajouter de polyfills inutiles.
7. **Minification** : Astro/Vite minifient au build. Un script en `is:inline` n'est ni minifié ni regroupé : le déplacer dans un `<script>` normal quand c'est possible, ou minifier le fichier à la main.
8. Pour les dépendances lourdes et les chunks de plus de 100 Ko gzip, voir aussi `code-dependances-client-lourdes`.

## Critères d'acceptation

- [ ] Aucun fichier JS de plus de 100 Ko gzip sur les pages courantes, ou chaque exception est justifiée
- [ ] Lighthouse : gain « JavaScript inutilisé » inférieur à 50 Kio sur les pages clés
- [ ] Plus de module présent en plusieurs versions (`npm ls` propre)
- [ ] Site fonctionnel après nettoyage (menus, formulaires, recherche, paiements)

## Vérification après correction

```bash
npm run build && du -sh dist/client/_astro 2>/dev/null || du -sh dist/_astro
python3 scripts/astro_scan.py /chemin/projet --out /tmp/verif --dist dist/client/_astro
bash scripts/lighthouse_run.sh /tmp/verif https://SITE/
```

## Pièges et retour arrière

- Le « JavaScript inutilisé » de Lighthouse compte ce qui n'a pas servi pendant le test : un code utile lors d'un clic apparaît comme inutilisé. Ne pas supprimer sans tester les interactions.
- Retirer un paquet peut casser un import caché : lancer `npm run build` et parcourir les pages.
- Retirer le visualiseur (`package.json` et config) avant de livrer.
- Retour arrière : `git revert` ; réinstaller le paquet retiré.

## Pour aller plus loin

- https://docs.astro.build/en/guides/client-side-scripts/ : comment Astro traite les scripts.
- https://docs.astro.build/en/reference/configuration-reference/#vite : configurer Vite/Rollup dans Astro.
- https://web.dev/articles/reduce-javascript-payloads-with-code-splitting : découper le code.
- https://developer.chrome.com/docs/lighthouse/performance/unused-javascript : repérer et supprimer le code inutilisé.
