---
name: audit-accessibilite
description: Audit d'accessibilité (WCAG 2.2 AA, RGAA) d'un site Astro ou autre — contrastes, textes alternatifs, titres, navigation clavier, focus, formulaires, ARIA, zones tactiles, animations, avec tests automatisés (Lighthouse, pa11y/axe) et vérifications manuelles guidées, et corrections dans les composants. Utilise ce skill quand l'utilisateur parle d'accessibilité, d'a11y, de RGAA, de WCAG, de l'European Accessibility Act, de contraste, de navigation au clavier, de lecteurs d'écran, ou quand le score accessibilité de Lighthouse est bas.
---

# Audit accessibilité

Format : `../audit-complet/references/format-constat.md`. Sortie : `rapports/accessibilite.md`.

Pourquoi c'est dans un audit SEO/perf : une partie des critères recoupe le SEO (alt, titres, liens explicites), l'accessibilité améliore la conversion pour tous, et c'est une obligation légale pour une partie des sites (European Accessibility Act en vigueur depuis le 28 juin 2025 pour de nombreux services B2C en ligne, hors micro-entreprises ; RGAA et déclaration d'accessibilité pour le secteur public et les grandes entreprises en France). Pour savoir si l'obligation s'applique à l'utilisateur, le renvoyer vers un juriste : ne pas trancher.

## Données
- `data/perf/pagespeed.json` → `echecs_autres_categories.accessibility` par page.
- `data/code/code-scan.md` → `<img>` sans alt.
- `data/crawl/issues.json` → `form_no_label` : champs de formulaire sans libellé (placeholder seul ou rien), relevés dans le HTML servi. Lighthouse ne les voit pas : il accepte un `placeholder` comme nom accessible. Les champs masqués, désactivés ou pièges à robots sont ignorés.
- Test automatisé plus complet sur 5 à 10 gabarits (accueil, formation, article, catalogue, contact) :
  ```bash
  bash -c 'npx -y pa11y --standard WCAG2AA --runner axe --reporter json https://site.fr/ > "$AUDIT/data/a11y/accueil.json"'
  ```
  (Chrome requis : même `CHROME_PATH` que pour Lighthouse, via la variable `PUPPETEER_EXECUTABLE_PATH`.) Les outils automatiques trouvent environ 30 à 40 % des problèmes : le reste se vérifie à la main.

## Checklist
### Automatisable (à confirmer)
- **Contrastes** : texte ≥ 4,5:1 (≥ 3:1 au-delà de 24 px, ou 18,5 px en gras). Remonter à la **couleur du design system** (variable Tailwind ou CSS) plutôt que de corriger élément par élément.
- **Images** : alt descriptif ; `alt=""` pour les images décoratives ; pas d'alt qui répète le texte voisin (« texte redondant » dans Lighthouse).
- **Titres** : un seul H1, pas de niveau sauté, pas de titre utilisé pour le style seul.
- **ARIA** : pas d'attributs ARIA interdits sur le rôle de l'élément ; un bouton est un `<button>`, pas une `<div onClick>`.
- **Liens et boutons** avec un nom accessible (icônes : `aria-label`) ; pas de « En savoir plus » répété sans contexte.
- **Formulaires** : chaque champ a un `<label>` associé, les erreurs sont annoncées, l'autocomplete est pertinent.
- **Zones tactiles** ≥ 24×24 px (WCAG 2.2) ; 44×44 recommandé sur mobile.
- `lang` sur `<html>`, titre de page unique.

### Manuel (5 minutes par gabarit)
- **Clavier seul** (Tab, Maj+Tab, Entrée, Échap) : tout est atteignable, l'ordre est logique, le **focus est visible** (pas de `outline: none` sans remplacement), aucun piège. Menu mobile, modales et chat : le focus entre, reste et revient ; Échap ferme.
- **Lien d'évitement** « Aller au contenu » en premier élément focusable.
- **Zoom 200 %** et largeur 320 px : pas de perte de contenu ni de défilement horizontal.
- **Animations** : respect de `prefers-reduced-motion` ; pas de carrousel automatique sans pause.
- **Vidéos** : sous-titres ; pas de lecture automatique avec son.
- **Bannière de consentement** : utilisable au clavier, n'enferme pas le focus, refuser est aussi simple qu'accepter (c'est aussi du RGPD).
- **Îlots** (React/Svelte) : les composants interactifs gardent la sémantique (`aria-expanded` sur les accordéons et menus, `aria-live` pour les messages du chat).

## Correctifs types
```css
/* Focus visible sans casser le design */
:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; scroll-behavior: auto !important; } }
```
```astro
<a href="#contenu" class="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2">Aller au contenu</a>
…
<main id="contenu">
```

## Restitution
`rapports/accessibilite.md` : score Lighthouse a11y par page, constats `A11Y-NNN` (groupés par composant ou gabarit : un correctif dans un composant corrige toutes les pages), puis la checklist manuelle cochée ou à faire par l'utilisateur.
