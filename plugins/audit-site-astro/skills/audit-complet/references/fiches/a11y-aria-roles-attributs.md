---
id: a11y-aria-roles-attributs
titre: "Usage incorrect d'ARIA : rôles et attributs invalides, interdits ou incomplets"
domaine: Accessibilité
severite_type: moyenne
effort: M
declencheurs:
  - "crawl:aria_ref_cassee"
  - "crawl:aria_label_interdit"
  - "lighthouse:aria-allowed-attr|aria-allowed-role|aria-prohibited-attr|aria-required-attr|aria-required-children|aria-required-parent|aria-roles|aria-valid-attr|aria-valid-attr-value|aria-deprecated-role|aria-conditional-attr|presentation-role-conflict|duplicate-id-aria"
  - "lighthouse:ne correspondent pas à leurs rôles|rôles ARIA sur des éléments incompatibles|attributs ARIA interdits|ne possèdent pas tous les attributs|enfants requis|parent requis|valeurs `\\[role\\]` ne sont pas valides|La valeur des attributs `\\[aria-\\*\\]` n'est pas valide|mal orthographiés|rôles ARIA obsolètes|comme indiqué pour le rôle|présentent des conflits|ID ARIA ne sont pas uniques"
sources:
  - https://www.w3.org/WAI/ARIA/apg/practices/read-me-first/
  - https://www.w3.org/TR/using-aria/
  - https://www.w3.org/WAI/WCAG22/Understanding/name-role-value.html
  - https://dequeuniversity.com/rules/axe/4.10/aria-allowed-attr
  - https://accessibilite.numerique.gouv.fr/methode/criteres-et-tests/#7.1
---

# Usage incorrect d'ARIA : rôles et attributs invalides, interdits ou incomplets

> **En une phrase** : des attributs `role` et `aria-*` sont mal utilisés (rôle qui n'existe pas, attribut interdit sur cet élément, enfants manquants), ce qui donne aux lecteurs d'écran une information fausse ou incohérente.

## Pourquoi c'est important

ARIA remplace ce que les balises natives ne savent pas exprimer, mais un ARIA faux est **pire que pas d'ARIA** : un `role="button"` sans gestion du clavier annonce un bouton qui ne réagit pas à Entrée, un `aria-expanded` mal câblé raconte l'inverse de l'état réel. La première règle d'ARIA (W3C) est de préférer l'élément HTML natif (`<button>`, `<a>`, `<details>`, `<dialog>`, `<nav>`), qui apporte gratuitement rôle, clavier et états. WCAG 4.1.2 (nom, rôle, valeur) ; RGAA thématique 7 (Scripts) et 8 (Éléments obligatoires).

## Comment le constater soi-même

```bash
grep -rnE '(role|aria-[a-z]+)=' src | wc -l          # ampleur d'usage
grep -rnE 'role="(button|link|checkbox|tab|menuitem)"' src | head -20   # rôles posés sur des div/span : à remplacer
```

Lighthouse liste chaque élément fautif avec son sélecteur et la raison ; l'inspecteur du navigateur (onglet Accessibilité) montre le rôle calculé.

## Correction

1. **Remplacer le faux composant par l'élément natif** quand c'est possible.

   ```astro
   <!-- Avant : rôle bricolé, sans clavier -->
   <div role="button" onclick="ouvrir()">Ouvrir</div>
   <!-- Après -->
   <button type="button" id="ouvrir">Ouvrir</button>
   ```

   Menus déroulants et accordéons : `<details><summary>`. Fenêtres modales : `<dialog>`. Navigation : `<nav>` (inutile d'ajouter `role="navigation"`).
2. **Rôle invalide ou obsolète** (`aria-roles`, `aria-deprecated-role`) : corriger la faute de frappe (`role="buton"`) ou utiliser le rôle actuel. Rôle inutile sur une balise native (`<button role="button">`, `<ul role="list">`) : le retirer, sauf cas documenté (liste dont le style `list-style: none` supprime la sémantique sur Safari).
3. **Attribut non autorisé pour le rôle** (`aria-allowed-attr`, `aria-prohibited-attr`) : ne pas mettre `aria-label` sur un `<div>` ou `<span>` sans rôle (nom interdit sur ces éléments génériques), ni `aria-expanded` sur un lien sans lien avec un panneau. Donnez un rôle approprié ou déplacez l'attribut vers l'élément interactif.
4. **Rôle composite sans structure requise** (`aria-required-children`, `aria-required-parent`) : `role="tablist"` doit contenir des `role="tab"`, `role="list"` des `role="listitem"`, `role="menu"` des `menuitem`. Sinon, retirez le rôle ou complétez la structure.
5. **Attributs requis manquants** (`aria-required-attr`) : `role="checkbox"` exige `aria-checked`, `role="slider"` exige `aria-valuenow`, etc. Utilisez l'élément natif (`<input type="checkbox">`, `<input type="range">`) pour éviter ce câblage.
6. **Valeurs invalides** (`aria-valid-attr-value`) : `aria-controls` / `aria-labelledby` / `aria-describedby` doivent référencer un `id` qui existe ; `aria-expanded` vaut `true` ou `false` (chaînes).

   ```astro
   <button type="button" aria-expanded="false" aria-controls="panneau-1" id="bouton-1">Détails</button>
   <div id="panneau-1" role="region" aria-labelledby="bouton-1" hidden>...</div>
   ```
7. **`id` en double** (`duplicate-id-aria`) : rendre chaque `id` référencé par ARIA unique (composants répétés : suffixe basé sur l'identifiant de la donnée).
8. **Conflit `role="presentation"` / `none`** sur un élément focalisable ou porteur d'attribut ARIA global : retirer le rôle, ou l'attribut.
9. **Îlots React / Svelte / Vue** : les bibliothèques de composants accessibles (Radix, Headless UI, Ark UI) évitent la plupart de ces erreurs ; ne les recodez pas à la main.
10. Mettez à jour les états au clic (`aria-expanded`, `aria-selected`, `aria-pressed`) en JavaScript, sinon l'attribut ment.

## Critères d'acceptation

- [ ] Plus d'échec sur les audits `aria-*` de Lighthouse (allowed-attr, allowed-role, prohibited-attr, required-*, roles, valid-attr*, conditional-attr).
- [ ] Chaque `role` est valide, applicable à son élément et complet.
- [ ] Chaque référence `aria-controls` / `aria-labelledby` / `aria-describedby` pointe vers un `id` existant et unique.
- [ ] Les composants interactifs se manient au clavier (voir `a11y-clavier-menus-modales`).

## Vérification après correction

```bash
npx lighthouse https://exemple.fr/ --only-categories=accessibility --quiet --output=json --output-path=/tmp/a11y.json --locale=fr
python3 -c "
import json; a=json.load(open('/tmp/a11y.json'))['audits']
print({k: a[k]['score'] for k in a if k.startswith('aria-') and a[k]['score'] not in (None, 1)})"
```

Une sortie `{}` signifie qu'aucun audit ARIA n'échoue.

## Pièges et retour arrière

- Retirer un ARIA « inutile » peut retirer un vrai nom accessible : contrôlez le nom calculé après modification.
- Les erreurs viennent souvent d'un composant partagé : une correction règle toutes les pages, vérifiez les autres gabarits.
- Retour arrière : restaurer le composant (Git).

## Pour aller plus loin

- W3C, « Read Me First » de l'ARIA Authoring Practices : les cinq règles d'ARIA.
- W3C, Using ARIA : quand utiliser ou non un attribut.
- Lighthouse, audit `aria-allowed-attr`.
- RGAA, thématique Scripts.
