---
id: a11y-zones-tactiles
titre: "Zones cliquables trop petites ou trop rapprochées (taille de cible)"
domaine: Accessibilité
severite_type: moyenne
effort: S
declencheurs:
  - "lighthouse:target-size|zones cibles tactiles sont insuffisants"
sources:
  - https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
  - https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html
  - https://dequeuniversity.com/rules/axe/4.10/target-size
  - https://web.dev/articles/accessible-tap-targets
---

# Zones cliquables trop petites ou trop rapprochées (taille de cible)

> **En une phrase** : des boutons et liens sont trop petits ou collés les uns aux autres, si bien qu'on clique à côté au doigt ou avec un tremblement de main.

## Pourquoi c'est important

Sur mobile, un doigt couvre environ 9 à 10 mm. Des icônes de 16 px collées (réseaux sociaux, pagination, croix de fermeture) provoquent des clics erronés, de la frustration et des abandons ; pour une personne avec un handicap moteur, ce peut être impossible. WCAG 2.2 a ajouté le critère 2.5.8 « Taille de cible (minimum) » au niveau AA : au moins **24 × 24 pixels CSS**, ou un espacement suffisant autour de la cible. Le niveau AAA (2.5.5) recommande 44 × 44. Google recommande aussi environ 48 px sur mobile. Le RGAA 4.1.2 repose sur WCAG 2.1 et ne contient pas encore ce critère ; il reste une bonne pratique et une exigence de WCAG 2.2 AA.

## Comment le constater soi-même

```bash
npx lighthouse https://exemple.fr/ --only-categories=accessibility --form-factor=mobile --quiet --output=json --output-path=/tmp/a11y.json --locale=fr
python3 -c "import json; a=json.load(open('/tmp/a11y.json'))['audits']['target-size']; [print(i['node']['snippet'][:90]) for i in a.get('details',{}).get('items',[])[:15]]"
```

Navigateur : outils de développement, mode appareil mobile, survolez l'élément (la taille s'affiche) ; ou bookmarklet « Target Size ».

Exceptions de WCAG 2.5.8 (pas d'erreur) : lien dans une phrase de texte, cible dont la taille est imposée par le navigateur (case à cocher native non stylée), cible équivalente disponible ailleurs.

## Correction

1. **Agrandir la zone cliquable, pas forcément le dessin** : l'icône peut rester petite si le bouton qui la contient fait 24 px ou plus (mieux 44 px).

   ```css
   /* src/styles/global.css */
   :root { --cible-min: 2.75rem; } /* 44 px */

   button, [role="button"], .bouton-icone, nav a, .pagination a, .reseaux a {
     min-inline-size: 24px;
     min-block-size: 24px;
   }
   @media (pointer: coarse) {
     button, [role="button"], .bouton-icone, nav a, .pagination a, .reseaux a {
       min-inline-size: var(--cible-min);
       min-block-size: var(--cible-min);
     }
   }
   ```
2. **Bouton d'icône** : ajoutez du remplissage plutôt que de grossir l'icône.

   ```css
   .bouton-icone { display: inline-grid; place-items: center; padding: 0.625rem; }
   .bouton-icone svg { inline-size: 1.25rem; block-size: 1.25rem; }
   ```
3. **Liens de navigation, pagination, pied de page** : `padding-block: 0.5rem` sur les liens en liste ; `gap: 0.5rem` ou plus entre éléments voisins.
4. **Cibles rapprochées** : si l'agrandissement est impossible, WCAG accepte 24 px de cercle libre autour de la cible (l'espacement compte) : ajoutez `margin` ou `gap` d'au moins 8 px entre petits éléments.
5. **Cases à cocher / boutons radio** : rendez le libellé cliquable (`<label for>`, voir `a11y-formulaires-labels`), ce qui agrandit la cible.
6. **Zones cliquables superposées** (lien qui recouvre toute la carte via `::after`) : vérifiez qu'elles ne masquent pas des liens ou boutons internes.
7. Contrôlez à 320 px de large et en zoom 200 % (la taille se mesure en pixels CSS).

## Critères d'acceptation

- [ ] Lighthouse : « La taille et l'espacement des zones cibles tactiles sont suffisants » réussi sur mobile.
- [ ] Toutes les cibles font au moins 24 × 24 px CSS (idéalement 44 px sur écran tactile) ou respectent l'espacement.
- [ ] Aucun chevauchement de cibles ; mise en page inchangée sur ordinateur.

## Vérification après correction

```bash
npx lighthouse https://exemple.fr/ --only-categories=accessibility --form-factor=mobile --quiet --output=json --output-path=/tmp/a11y.json --locale=fr
python3 -c "import json; print(json.load(open('/tmp/a11y.json'))['audits']['target-size']['score'])"
```

## Pièges et retour arrière

- Grossir tous les boutons peut casser une barre d'outils dense : ciblez les composants signalés, avec `@media (pointer: coarse)` pour ne changer que le tactile.
- `min-height` sur un lien `inline` sans effet : passez-le en `inline-block` ou `inline-flex`.
- Retour arrière : supprimer les règles ajoutées.

## Pour aller plus loin

- WCAG 2.2, 2.5.8 taille de cible (minimum) et 2.5.5 (amélioré).
- Lighthouse, audit `target-size`.
- web.dev, cibles tactiles accessibles.
