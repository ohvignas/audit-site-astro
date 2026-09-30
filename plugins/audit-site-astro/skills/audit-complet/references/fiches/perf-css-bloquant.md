---
id: perf-css-bloquant
titre: CSS et scripts qui bloquent le rendu, CSS inutilisé ou mal inséré (inlineStylesheets)
domaine: Performance
severite_type: moyenne
effort: M
declencheurs:
  - "code:build\\.inlineStylesheets: 'always'"
  - "lighthouse:render-blocking-resources|render-blocking-insight|unused-css-rules|unminified-css|Éliminez les ressources qui bloquent le rendu|Requêtes de blocage du rendu|Réduisez les ressources CSS inutilisées|Réduisez la taille des ressources CSS"
sources:
  - https://docs.astro.build/en/reference/configuration-reference/#buildinlinestylesheets
  - https://docs.astro.build/en/guides/styling/
  - https://developer.chrome.com/docs/lighthouse/performance/render-blocking-resources
  - https://web.dev/articles/defer-non-critical-css
---

# CSS et scripts qui bloquent le rendu, CSS inutilisé ou mal inséré (inlineStylesheets)

> **En une phrase** : le navigateur doit télécharger des feuilles de style (ou des scripts) avant d'afficher quoi que ce soit ; plus elles sont lourdes ou nombreuses, plus l'écran reste blanc.

## Pourquoi c'est important

Le CSS bloque le rendu par nature : tant qu'il n'est pas reçu, la page ne s'affiche pas. Une feuille de 300 Ko, un `@import` en cascade ou une feuille tierce lente retardent le FCP et le LCP, d'autant plus sur mobile. À l'inverse, inliner tout le CSS dans chaque page (`inlineStylesheets: 'always'`) supprime la requête mais alourdit chaque page HTML et empêche le cache navigateur de servir le CSS aux pages suivantes. Lighthouse mesure le gain (« Éliminez les ressources qui bloquent le rendu », « Réduisez les ressources CSS inutilisées »).

## Comment le constater soi-même

```bash
# Feuilles de style et scripts bloquants dans le <head>
curl -s https://SITE/ | grep -oE '<link[^>]*rel="stylesheet"[^>]*>' | head
curl -s https://SITE/ | grep -oE '<script[^>]*src="[^"]+"[^>]*>' | grep -vE 'defer|async|type="module"' | head
# Poids du CSS servi (gzip)
curl -s -H 'Accept-Encoding: gzip' https://SITE/_astro/NOM.HASH.css | wc -c
# Réglage actuel
grep -n "inlineStylesheets" astro.config.*
```

Problème présent : plusieurs feuilles bloquantes (dont tierces), CSS > 50 Ko gzip, ou `inlineStylesheets: 'always'` avec un HTML lourd. Corrigé : une petite feuille locale, CSS inutilisé retiré, pas de blocage tiers.

## Correction

1. **Revenir au réglage par défaut** si `build.inlineStylesheets` vaut `'always'` : `'auto'` inline les feuilles de moins de 4 Ko et laisse les grosses en fichier séparé, donc cacheable.

```js
import { defineConfig } from 'astro/config';

export default defineConfig({
  build: {
    inlineStylesheets: 'auto',
  },
});
```

`'never'` sert les styles en fichiers externes uniquement. `'always'` reste défendable pour un site presque sans navigation entre pages et un CSS très petit.
2. **Réduire le CSS** :
   - Tailwind : vérifier que le contenu analysé (`content` en v3, détection automatique des sources en v4) couvre seulement `src/` et pas `node_modules` ; supprimer les composants CSS non utilisés.
   - Ne pas importer une bibliothèque CSS entière (Bootstrap, Font Awesome complet) pour quelques classes ou icônes.
   - Astro place le CSS d'un composant dans la page qui l'utilise : éviter d'importer un gros fichier global dans un layout partagé s'il ne sert qu'à une page.
3. **Supprimer les `@import` CSS** (chaîne de requêtes) : les remplacer par un `import` dans le frontmatter ou le layout, que Vite regroupe.

```astro
---
import '../styles/global.css';
---
```

4. **Feuilles tierces** (widgets, polices) : les auto-héberger (`perf-polices`) ou les charger uniquement sur les pages concernées. Pour une feuille non critique, la charger sans bloquer :

```html
<link rel="stylesheet" href="/widget.css" media="print" onload="this.media='all'" />
<noscript><link rel="stylesheet" href="/widget.css" /></noscript>
```

5. **Scripts dans le `<head>`** : les scripts modules d'Astro (`<script>` sans `is:inline`) sont différés par défaut. Un `<script is:inline src="…">` ou un script classique bloque : ajouter `defer` ou `async`, ou le déplacer en fin de `<body>`.
6. **Minification** : Vite minifie le CSS au build ; un CSS non minifié signalé vient d'un fichier de `public/` ou d'un tiers : le minifier ou le remplacer.
7. Après changement, comparer le nombre de requêtes bloquantes et le poids du CSS (`du -sh dist/client/_astro/*.css`).

## Critères d'acceptation

- [ ] `build.inlineStylesheets` vaut `'auto'` (ou choix justifié et documenté)
- [ ] Au plus une feuille de style bloquante locale sur les pages courantes, aucune feuille tierce bloquante
- [ ] CSS principal < 50 Ko gzip ; « CSS inutilisé » < 20 Kio sur les pages clés
- [ ] Rendu identique (aucune page « sans style » au chargement)

## Vérification après correction

```bash
npm run build && ls -lh dist/client/_astro/*.css 2>/dev/null || ls -lh dist/_astro/*.css
bash scripts/lighthouse_run.sh /tmp/verif https://SITE/
python3 scripts/astro_scan.py /chemin/projet --out /tmp/verif
```

## Pièges et retour arrière

- Un CSS « inutilisé » pour Lighthouse peut servir après une interaction (menu, modale) : ne pas le supprimer sans test.
- La technique `media="print" onload` est un compromis : le contenu stylé par cette feuille peut apparaître nu un instant.
- Retour arrière : remettre l'ancienne valeur de `inlineStylesheets` et les anciens liens.

## Pour aller plus loin

- https://docs.astro.build/en/reference/configuration-reference/#buildinlinestylesheets : options `always`, `auto`, `never`.
- https://docs.astro.build/en/guides/styling/ : styles dans Astro.
- https://developer.chrome.com/docs/lighthouse/performance/render-blocking-resources : éliminer les ressources bloquantes.
- https://web.dev/articles/defer-non-critical-css : différer le CSS non critique.
