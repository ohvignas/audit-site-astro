---
id: a11y-lien-evitement-tabindex
titre: "Lien d'évitement absent ou cassé, tabindex positif, accesskey en double"
domaine: Accessibilité
severite_type: moyenne
effort: S
declencheurs:
  - "lighthouse:bypass|skip-link|tabindex|accesskeys"
  - "lighthouse:lien \"Ignorer\" ni de point de repère|liens d'ancrage ne sont pas sélectionnables|valeur `\\[tabindex\\]` supérieure à 0|valeurs `\\[accesskey\\]` ne sont pas uniques"
sources:
  - https://www.w3.org/WAI/WCAG22/Understanding/bypass-blocks.html
  - https://www.w3.org/WAI/WCAG22/Understanding/focus-order.html
  - https://webaim.org/techniques/skipnav/
  - https://dequeuniversity.com/rules/axe/4.10/bypass
  - https://dequeuniversity.com/rules/axe/4.10/tabindex
  - https://accessibilite.numerique.gouv.fr/methode/criteres-et-tests/#12.7
---

# Lien d'évitement absent ou cassé, tabindex positif, accesskey en double

> **En une phrase** : un utilisateur du clavier doit tabuler à travers tout le menu à chaque page avant d'atteindre le contenu, faute de lien « Aller au contenu » ; ou l'ordre de tabulation est bouleversé par des `tabindex` positifs.

## Pourquoi c'est important

Une personne qui ne peut pas utiliser la souris (handicap moteur, lecteur d'écran, utilisateur avancé) navigue avec Tab. Sans lien d'évitement, un menu de 30 liens se retraverse à chaque page : 30 appuis avant le premier paragraphe. WCAG 2.4.1 « Contourner des blocs » (niveau A) ; RGAA critère 12.7 (lien d'évitement) ; ordre de tabulation logique : WCAG 2.4.3. Les `tabindex` supérieurs à 0 créent un ordre de tabulation séparé de l'ordre visuel, difficile à maintenir et source de pièges. Ce lien profite à tous les utilisateurs du clavier.

## Comment le constater soi-même

Test en 30 secondes : chargez la page, appuyez sur **Tab** une fois. Le premier élément doit être un lien « Aller au contenu » qui apparaît visuellement au focus. Appuyez sur Entrée : le focus passe au contenu (le Tab suivant atteint le premier lien du contenu, pas le menu).

```bash
grep -rnE 'tabindex="[1-9]' src | head                # tabindex positifs : à supprimer
grep -rn 'accesskey=' src | head
curl -s https://exemple.fr/ | grep -oE '<a[^>]+href="#[^"]+"[^>]*>' | head -3   # lien d'évitement
```

## Correction

1. **Ajouter le lien d'évitement en tout premier élément du `<body>`**, dans la mise en page commune, avec une cible qui existe.

   ```astro
   ---
   // src/layouts/Base.astro (extrait)
   ---
   <body>
     <a class="lien-evitement" href="#contenu">Aller au contenu</a>
     <header>...</header>
     <main id="contenu" tabindex="-1">
       <slot />
     </main>
     <footer>...</footer>
   </body>
   ```

   ```css
   .lien-evitement {
     position: absolute; inset-inline-start: 0.5rem; inset-block-start: -4rem;
     padding: 0.75rem 1rem; background: #fff; color: #000; border: 2px solid #000; z-index: 1000;
   }
   .lien-evitement:focus { inset-block-start: 0.5rem; }
      ```

   Le lien doit être visible au focus (ne pas l'écraser avec `display:none` ni `visibility:hidden`, qui le retirent du clavier). `tabindex="-1"` sur `<main>` permet au navigateur de déplacer le focus dessus après l'activation du lien (un contour peut alors entourer `<main>` : c'est acceptable, ne le supprimez pas avec `outline: none`).
2. **La cible existe** (`skip-link`) : l'`id` de `<main>` correspond exactement à l'ancre (`#contenu`), et est unique sur la page.
3. **Repères en complément** (`bypass`) : `<header>`, `<nav>`, `<main>`, `<footer>` : voir `a11y-titres-structure`.
4. **`tabindex` positif** : remplacez par l'ordre naturel du HTML (placez les éléments dans l'ordre de lecture voulu). Valeurs utiles : `tabindex="0"` (rend focalisable un élément interactif personnalisé, préférez plutôt un `<button>`) et `tabindex="-1"` (focalisable uniquement par programme).
5. **`accesskey`** : à éviter (conflits avec les raccourcis des lecteurs d'écran et navigateurs) ; sinon valeurs uniques.
6. **Navigation Astro `<ClientRouter />`** : après un changement de page, contrôlez que le focus revient en haut de la page ou sur le titre (`h1` avec `tabindex="-1"` focalisé par script) ; Astro fournit une annonce de changement de route pour les lecteurs d'écran, à vérifier avec un lecteur d'écran.
7. Ajoutez des liens d'évitement supplémentaires seulement si utile (« Aller à la recherche », « Aller au pied de page ») ; deux ou trois au maximum.

## Critères d'acceptation

- [ ] Le premier Tab sur chaque gabarit met le focus sur « Aller au contenu », visible.
- [ ] Entrée sur ce lien place le focus dans le contenu principal.
- [ ] Aucun `tabindex` supérieur à 0 ; pas d'`accesskey` en double.
- [ ] Lighthouse : `bypass`, `skip-link`, `tabindex` réussis.

## Vérification après correction

```bash
npx lighthouse https://exemple.fr/ --only-categories=accessibility --quiet --output=json --output-path=/tmp/a11y.json --locale=fr
python3 -c "import json; a=json.load(open('/tmp/a11y.json'))['audits']; print({k:a[k]['score'] for k in ('bypass','skip-link','tabindex','accesskeys') if k in a})"
```

## Pièges et retour arrière

- Un en-tête `position: sticky` peut masquer la cible après le saut : ajoutez `scroll-margin-top` (ou `scroll-padding-top` sur `html`) égal à la hauteur de l'en-tête.
- Un composant de bandeau de consentement placé avant le lien d'évitement le prive de sa place de premier élément : voir `a11y-bandeau-consentement`.
- Retour arrière : supprimer le lien ; sans impact sur les données.

## Pour aller plus loin

- WCAG 2.4.1 (contourner des blocs) et 2.4.3 (parcours du focus).
- WebAIM, technique du lien d'évitement.
- Lighthouse, audits `bypass` et `tabindex`.
- RGAA, thématique Navigation (critère 12.7).
