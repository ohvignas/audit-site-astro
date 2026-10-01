---
id: perf-polices
titre: Polices web chargées depuis Google ou sans optimisation (API Fonts, preload, font-display)
domaine: Performance
severite_type: moyenne
effort: S
declencheurs:
  - "code:Google Fonts chargées depuis Google"
  - "code:Polices chargées sans l'API Fonts d'Astro"
  - "code:API Fonts configurée mais aucune <Font preload>"
  - "lighthouse:font-display|preload-fonts|font-display-insight|Assurez-vous que le texte reste visible pendant le chargement des polices Web|Affichage de la police|polices qui utilisent `font-display: optional`"
versions_astro: ">=6.0 pour l'API Fonts ; avant : @fontsource"
sources:
  - https://docs.astro.build/en/guides/fonts/
  - https://docs.astro.build/en/reference/modules/astro-assets/
  - https://web.dev/articles/font-best-practices
  - https://developer.mozilla.org/en-US/docs/Web/CSS/@font-face/font-display
---

# Polices web chargées depuis Google ou sans optimisation (API Fonts, preload, font-display)

> **En une phrase** : les polices viennent d'un serveur tiers (Google Fonts) ou sont chargées tard et sans réglage, ce qui retarde l'affichage du texte, fait sauter la mise en page et pose une question de vie privée.

## Pourquoi c'est important

Une feuille `fonts.googleapis.com` oblige le navigateur à ouvrir deux connexions tierces (feuille de styles, puis fichiers `fonts.gstatic.com`) avant d'afficher le texte : le LCP texte et le FCP en pâtissent. Les visiteurs européens transmettent aussi leur adresse IP à Google : plusieurs autorités et tribunaux ont jugé cela contraire au RGPD sans consentement. Sans `font-display` adapté, le texte reste invisible pendant le chargement (FOIT) ; avec une police de repli mal ajustée, le texte saute quand la vraie police arrive (CLS). Auto-héberger et précharger la seule police utile au premier écran règle ces trois points.

## Comment le constater soi-même

```bash
# Google Fonts ou @font-face dans le code
grep -rnE "fonts\.(googleapis|gstatic)\.com|@font-face|@fontsource" src public astro.config.* package.json | head
# Requêtes de polices tierces dans le HTML servi
curl -s https://SITE/ | grep -oE 'https://fonts\.(googleapis|gstatic)\.com[^"]*' | head
# Polices préchargées
curl -s https://SITE/ | grep -oE '<link[^>]*rel="preload"[^>]*as="font"[^>]*>'
```

Problème présent : des requêtes vers `fonts.googleapis.com`, aucun `preload` de police, ou `font-display` absent. Corrigé : polices servies depuis votre domaine (`/_astro/fonts/…`), une ou deux préchargées.

## Correction

**Astro 6 ou plus récent : API Fonts (recommandée).** Elle télécharge la police au build, l'héberge chez vous, génère `@font-face` et une police de repli ajustée (moins de CLS).

1. Dans `astro.config.mjs` (remplacer `Inter` par la police du site, et les graisses par celles réellement utilisées) :

```js
import { defineConfig, fontProviders } from 'astro/config';

export default defineConfig({
  fonts: [
    {
      provider: fontProviders.google(),
      name: 'Inter',
      cssVariable: '--font-inter',
      weights: [400, 700],
      styles: ['normal'],
      subsets: ['latin'],
      fallbacks: ['sans-serif'],
    },
  ],
});
```

2. Dans le `<head>` du layout commun, ajouter le composant en ne préchargeant que ce qui sert au texte principal au-dessus de la ligne de flottaison (le tableau évite de tout précharger) :

```astro
---
import { Font } from 'astro:assets';
---
<head>
  <Font cssVariable="--font-inter" preload={[{ weight: '400', style: 'normal', subset: 'latin' }]} />
</head>
```

3. Utiliser la variable CSS et supprimer les anciennes sources : retirer les `<link href="https://fonts.googleapis.com/...">`, les `@import url(...)` et les `@font-face` dupliqués.

```css
body { font-family: var(--font-inter); }
```

Avec Tailwind CSS 4 : `@theme inline { --font-sans: var(--font-inter); }`.
4. Limiter les polices : 1 ou 2 familles, 2 à 4 graisses au total. Une police variable remplace souvent plusieurs graisses.

**Astro 5 ou plus ancien : @fontsource.** `npm i @fontsource-variable/inter`, puis `import '@fontsource-variable/inter';` dans le layout. Précharger le fichier woff2 principal :

```astro
---
import interWoff2 from '@fontsource-variable/inter/files/inter-latin-wght-normal.woff2?url';
---
<link rel="preload" href={interWoff2} as="font" type="font/woff2" crossorigin />
```

(vérifier le nom du fichier dans `node_modules/@fontsource-variable/inter/files/`).

**Toutes versions**
5. `font-display: swap` (texte visible tout de suite) ou `optional` (pas de saut, la police n'est utilisée que si elle arrive vite). L'API Fonts d'Astro accepte l'option `display` par police.
6. Le `preload` d'une police exige l'attribut `crossorigin` (même pour un fichier hébergé chez vous) ; le composant `<Font />` le gère.

## Critères d'acceptation

- [ ] Aucune requête vers `fonts.googleapis.com` ou `fonts.gstatic.com`
- [ ] Une ou deux polices préchargées (woff2), celles du premier écran
- [ ] Lighthouse : « Assurez-vous que le texte reste visible pendant le chargement des polices Web » réussi
- [ ] Pas de saut de texte visible au chargement (CLS ≤ 0,1) et rendu typographique identique

## Vérification après correction

```bash
curl -s https://SITE/ | grep -c "fonts.googleapis.com"      # attendu : 0
curl -s https://SITE/ | grep -oE '<link[^>]*as="font"[^>]*>'
python3 scripts/astro_scan.py /chemin/projet --out /tmp/verif
bash scripts/lighthouse_run.sh /tmp/verif https://SITE/
```

## Pièges et retour arrière

- `preload` sans tableau (`preload` seul) précharge toutes les variantes déclarées : c'est lourd. Toujours restreindre.
- Une graisse déclarée mais non utilisée est téléchargée pour rien : retirer les graisses inutiles.
- Retour arrière : remettre le `<link>` Google Fonts (à éviter pour le RGPD) ; retirer `fonts` de la config.

## Pour aller plus loin

- https://docs.astro.build/en/guides/fonts/ : configuration et fournisseurs de polices.
- https://docs.astro.build/en/reference/modules/astro-assets/ : composant `<Font />` et prop `preload`.
- https://web.dev/articles/font-best-practices : bonnes pratiques de polices web.
- https://developer.mozilla.org/en-US/docs/Web/CSS/@font-face/font-display : valeurs de `font-display`.
