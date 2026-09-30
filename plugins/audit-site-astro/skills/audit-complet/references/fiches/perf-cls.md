---
id: perf-cls
titre: Décalages de mise en page (CLS) - contenu qui saute pendant le chargement
domaine: Performance
severite_type: haute
effort: M
declencheurs:
  - "lighthouse:layout-shifts|layout-shift-elements|cls-culprits-insight|non-composited-animations|Éviter les changements de mise en page importants|Causes des décalages de mise en page|Éviter les animations non composées"
sources:
  - https://web.dev/articles/optimize-cls
  - https://web.dev/articles/cls
  - https://developer.mozilla.org/en-US/docs/Web/CSS/aspect-ratio
  - https://docs.astro.build/en/concepts/islands/
---

# Décalages de mise en page (CLS) - contenu qui saute pendant le chargement

> **En une phrase** : des éléments apparaissent ou changent de taille après l'affichage initial et poussent le contenu, ce qui fait cliquer au mauvais endroit et dégrade la note Core Web Vitals.

## Pourquoi c'est important

Le CLS additionne l'ampleur des sauts de mise en page inattendus. Google demande 0,1 ou moins pour 75 % des visites ; au-delà de 0,25, c'est jugé mauvais. Les sauts frustrent les visiteurs (bouton qui se décale au moment du clic) et pèsent sur le classement via l'expérience de page. L'outil liste dans le rapport Lighthouse les éléments qui bougent (« Causes des décalages de mise en page ») : c'est le point de départ.

## Comment le constater soi-même

```bash
# Éléments qui bougent, d'après le dernier passage Lighthouse de l'outil
grep -i "Éléments qui bougent" /tmp/verif/pagespeed-summary.md
```

Dans Chrome : DevTools > Performance > cocher « Layout shifts » (ou la piste « Layout Shifts ») > enregistrer un chargement de page ; chaque saut est détaillé avec l'élément déplacé. Ou onglet Rendering > « Layout Shift Regions » (les zones qui sautent clignotent en bleu).

Problème présent : CLS > 0,1, éléments déplacés attribués à des images, iframes, bannières, polices. Corrigé : CLS ≤ 0,1.

## Correction

Traiter les causes dans cet ordre (les plus fréquentes d'abord).

1. **Images sans dimensions** : voir `perf-images-sans-dimensions`. `<Image />` d'Astro les ajoute ; sinon `width` + `height` ou `aspect-ratio`.
2. **Iframes, vidéos, cartes, widgets** : réserver l'espace avant le chargement.

```css
.video, .carte { aspect-ratio: 16 / 9; width: 100%; }
.video iframe, .carte iframe { width: 100%; height: 100%; border: 0; }
```

3. **Bannière de consentement / bandeau d'annonce inséré au-dessus du contenu** : la superposer au lieu de pousser la page.

```css
.consentement { position: fixed; inset: auto 0 0 0; z-index: 50; }
```

Si un bandeau doit rester dans le flux, réserver sa hauteur dès le HTML serveur (`min-height`), même quand il est vide.
4. **Îlots hydratés dont la taille change** : le rendu serveur et le rendu client doivent occuper la même place. Donner au conteneur un `min-height` égal à la taille finale, ou fournir un squelette de même hauteur (slot `fallback` pour `client:only`).

```astro
<div class="avis" style="min-height: 320px">
  <Avis client:visible />
</div>
```

5. **Polices** : une police de repli de dimensions différentes provoque un saut au remplacement. Solution la plus simple sur Astro 6+ : l'API Fonts génère un repli ajusté (`perf-polices`). Sinon `font-display: optional`, ou `size-adjust` / `ascent-override` / `descent-override` sur un `@font-face` de repli.
6. **Contenu injecté par JavaScript** (liste chargée après coup, publicité, recommandations) : conteneur de taille fixe ou squelette ; ne pas insérer de contenu au-dessus de ce que l'utilisateur voit déjà.
7. **Animations** (audit « Éviter les animations non composées ») : animer `transform` et `opacity`, pas `top`, `left`, `width`, `height`, `margin`.

```css
.menu { transform: translateY(-100%); transition: transform .2s; }
.menu.ouvert { transform: translateY(0); }
```

8. **Éléments collants ou en-têtes qui changent de hauteur** au défilement : fixer leur hauteur ou utiliser `position: sticky` sans changer la taille du bloc.
9. **Éviter d'empêcher le cache de retour** (bfcache) : les pages éligibles évitent de recalculer la mise en page à chaque retour.

## Critères d'acceptation

- [ ] CLS ≤ 0,1 en labo (Lighthouse mobile) sur les pages clés ; viser 0,05
- [ ] Aucun élément de la liste « Causes des décalages de mise en page » n'est attribué à une image, un iframe, une bannière ou un îlot
- [ ] CLS terrain (CrUX/PageSpeed) en baisse lorsque disponible
- [ ] Mise en page inchangée une fois chargée

## Vérification après correction

```bash
bash scripts/lighthouse_run.sh /tmp/verif https://SITE/ https://SITE/page-cle
grep -iE "CLS|Éléments qui bougent" /tmp/verif/pagespeed-summary.md
```

## Pièges et retour arrière

- Un CLS bas sur la page d'accueil n'exclut pas un CLS élevé ailleurs : tester chaque type de page (article, liste, fiche).
- Un `min-height` trop grand crée un vide visible : le régler sur la hauteur réelle mesurée.
- Retour arrière : retirer les styles ajoutés (le CLS reviendra).

## Pour aller plus loin

- https://web.dev/articles/optimize-cls : causes et corrections détaillées.
- https://web.dev/articles/cls : définition et seuils du CLS.
- https://developer.mozilla.org/en-US/docs/Web/CSS/aspect-ratio : réserver un ratio avec CSS.
- https://docs.astro.build/en/concepts/islands/ : îlots et rendu serveur.
