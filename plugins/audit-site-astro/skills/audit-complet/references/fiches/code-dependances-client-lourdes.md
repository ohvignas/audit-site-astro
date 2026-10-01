---
id: code-dependances-client-lourdes
titre: Dépendances lourdes embarquées dans le JavaScript client
domaine: Code
severite_type: basse
effort: M
declencheurs:
  - "code:Dépendances lourdes à vérifier côté client"
  - "code:Chunks JS > 100 Ko gzip"
sources:
  - https://docs.astro.build/en/concepts/islands/
  - https://docs.astro.build/en/reference/directives-reference/
  - https://docs.astro.build/en/guides/client-side-scripts/
---

# Dépendances lourdes embarquées dans le JavaScript client

> **En une phrase** : une bibliothèque volumineuse (moment, lodash, jQuery, three, gsap, Swiper…) ou un chunk JS de plus de 100 Ko gzip alourdit chaque page qui l'importe et retarde l'interactivité.

## Pourquoi c'est important

Astro n'envoie du JavaScript que pour les îlots (`client:*`) et les balises `<script>`, mais tout ce que ces îlots importent part dans le navigateur. Sur mobile, chaque centaine de Ko gzip de JS ajoute plusieurs centaines de millisecondes de téléchargement et d'exécution : le Total Blocking Time et l'INP (seuil Google « bon » : 200 ms) en souffrent. Les bibliothèques citées ont presque toujours une alternative native (`Intl`, `fetch`, CSS) ou une version modulaire beaucoup plus légère.

## Comment le constater soi-même

```bash
grep -nE '"(moment|lodash|jquery|@fortawesome/fontawesome-free|gsap|three|chart\.js|framer-motion|swiper|aos)"' package.json
npx astro build
find dist -name '*.js' -path '*_astro*' -size +100k -exec ls -lh {} \;    # chunks bruts > 100 Ko
grep -rnE "from ['\"](moment|lodash|swiper|gsap|three)['\"]" src            # qui importe quoi
npx vite-bundle-visualizer                                                  # carte du bundle (ouvre un rapport HTML)
```

Présent : un chunk > 100 Ko gzip ou une de ces bibliothèques importée depuis un composant client. Corrigé : chunk le plus gros nettement réduit, bibliothèque absente ou chargée à la demande.

## Correction

1. Identifier l'îlot ou le script qui importe la bibliothèque (`grep` ci-dessus, ou le visualiseur de bundle).
2. Choisir la remédiation par ordre de préférence :
   - **Supprimer** : `moment` → `Intl.DateTimeFormat` / `date-fns` (imports par fonction) ; `lodash` → imports ciblés (`import debounce from 'lodash-es/debounce'`) ou natif ; `jquery` → JS natif ; `@fortawesome/fontawesome-free` → icônes SVG en ligne ou `astro-icon` ; `aos` → CSS + `IntersectionObserver` ; `swiper` → CSS `scroll-snap`.
   - **Charger tard** : hydrater avec `client:visible` (ou `client:idle`) au lieu de `client:load`, et importer la bibliothèque à la demande :
     ```astro
     ---
     import Carte3D from '../components/Carte3D.tsx';
     ---
     <Carte3D client:visible />
     ```
     ```tsx
     // Carte3D.tsx : three n'est téléchargé qu'à l'affichage du composant
     import { useEffect, useRef } from 'react';

     export default function Carte3D() {
       const ref = useRef<HTMLDivElement>(null);
       useEffect(() => {
         let stop = () => {};
         import('three').then((THREE) => {
           const renderer = new THREE.WebGLRenderer({ antialias: true });
           ref.current?.appendChild(renderer.domElement);
           stop = () => renderer.dispose();
         });
         return () => stop();
       }, []);
       return <div ref={ref} />;
     }
     ```
   - **Remplacer** par une alternative plus légère (`chart.js` → `uPlot` ou SVG généré côté serveur dans un composant `.astro`).
3. Si le composant n'a aucune interactivité, le réécrire en `.astro` : zéro JavaScript envoyé.
4. Reconstruire et comparer la taille des chunks avant/après.

## Critères d'acceptation

- [ ] Aucun chunk JS > 100 Ko gzip dans `dist/_astro` (ou justification écrite)
- [ ] Les bibliothèques listées ne sont plus importées, ou seulement via `import()` dynamique / `client:visible`
- [ ] Aucune régression : composant toujours fonctionnel, pas d'erreur console, build OK

## Vérification après correction

```bash
npx astro build && find dist -name '*.js' -path '*_astro*' -exec ls -l {} \; | sort -k5 -rn | head
python3 scripts/astro_scan.py . --out /tmp/verif --dist dist/client/_astro
```

## Pièges et retour arrière

- Un `import()` dynamique dans un composant `client:load` ne fait que différer le téléchargement ; combiner avec `client:visible` pour le gain réel.
- Vérifier le rendu serveur : `window` et `document` n'existent pas au rendu ; les utiliser dans `useEffect` ou dans un `<script>`.
- Retour arrière : `git revert` du commit ; ne pas désinstaller une dépendance avant d'avoir cherché tous ses imports (`grep -rn`).

## Pour aller plus loin

- https://docs.astro.build/en/concepts/islands/ : îlots et JavaScript envoyé au navigateur.
- https://docs.astro.build/en/reference/directives-reference/ : directives `client:*`.
- https://docs.astro.build/en/guides/client-side-scripts/ : scripts côté client dans Astro.
