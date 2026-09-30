---
id: a11y-focus-visible
titre: "Indicateur de focus clavier invisible ou masqué (outline supprimé)"
domaine: Accessibilité
severite_type: haute
effort: S
declencheurs:
  - "manuel:focus-visible"
sources:
  - https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html
  - https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html
  - https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html
  - https://developer.mozilla.org/en-US/docs/Web/CSS/:focus-visible
  - https://accessibilite.numerique.gouv.fr/methode/criteres-et-tests/#10.7
---

# Indicateur de focus clavier invisible ou masqué (outline supprimé)

> **En une phrase** : quand on navigue au clavier, on ne voit pas quel élément est sélectionné, parce que le contour de focus a été supprimé (`outline: none`) ou est masqué par un en-tête collant.

## Pourquoi c'est important

Le focus est le « curseur » du clavier. S'il est invisible, une personne qui ne peut pas utiliser la souris ne sait plus où elle est : elle appuie sur Entrée à l'aveugle. C'est l'un des défauts les plus fréquents, introduit par les feuilles de style de réinitialisation ou par une volonté esthétique. WCAG 2.4.7 « Focus visible » (AA) ; 2.4.11 « Focus non masqué (minimum) » (AA, nouveau dans WCAG 2.2) ; contraste de l'indicateur d'au moins 3:1 (1.4.11) ; RGAA critère 10.7. Lighthouse ne le détecte pas : **contrôle manuel**.

## Comment le constater soi-même

Test manuel (2 minutes par gabarit) : en haut de page, appuyez sur **Tab** en continu ; à chaque pression, un contour ou un changement de style net doit apparaître sur l'élément actif (lien, bouton, champ, case, onglet). Faites aussi Maj+Tab et testez à 200 % de zoom.

```bash
grep -rnE "outline:[[:space:]]*(none|0)|outline-none|focus:outline-none|\*:focus[[:space:]]*\{" src public | head -30
grep -rn "focus-visible" src | head
```

Chaque `outline: none` doit être accompagné d'un remplacement visible dans le même sélecteur.

## Correction

1. **Style de focus global** pour tous les éléments interactifs, en tête de la feuille de styles.

   ```css
   /* src/styles/global.css */
   :focus-visible {
     outline: 3px solid var(--couleur-focus, #1d4ed8);
     outline-offset: 2px;
   }
   /* sur fond sombre */
   .fond-sombre :focus-visible { outline-color: #fff; }
   ```

   `:focus-visible` n'affiche le contour qu'au clavier (pas au clic souris), ce qui répond à la crainte esthétique. Contraste d'au moins 3:1 entre le contour et le fond adjacent.
2. **Supprimer ou remplacer chaque `outline: none`**. Si un composant a un style personnalisé (ombre `box-shadow`, bordure), il doit rester nettement visible (épaisseur d'au moins 2 px, contraste 3:1). Ne laissez jamais `outline: none` sans état de remplacement, et ne masquez pas le focus des cases à cocher / boutons radio personnalisés (sinon montrez-le sur leur étiquette).

   Tailwind : `focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700` ; pas de `focus:outline-none` seul.
3. **Focus masqué par un en-tête ou un bandeau collant** (WCAG 2.4.11) : l'élément focalisé ne doit pas être entièrement recouvert.

   ```css
   html { scroll-padding-block: 6rem; }       /* hauteur de l'en-tête sticky + marge */
   ```

   Vérifiez aussi le bandeau de cookies et les chats flottants (voir `a11y-bandeau-consentement`).
4. **Éléments personnalisés** : un `<div>` cliquable doit être remplacé par un `<button>` (focalisable et stylable) ; voir `a11y-aria-roles-attributs`.
5. **Ordre et pièges** : vérifiez qu'aucun élément visible n'est inatteignable (`tabindex="-1"` sur un lien utile) et qu'aucun élément invisible ne prend le focus (menu fermé, voir `a11y-aria-noms-masquage`).
6. Ajoutez le contrôle au processus de revue : « Tab sur la page modifiée » avant de fusionner.

## Critères d'acceptation

- [ ] Tab/Maj+Tab : chaque élément interactif montre un indicateur net (≥ 3:1, ≥ 2 px).
- [ ] Aucun `outline: none` sans remplacement ; `:focus-visible` défini globalement.
- [ ] L'élément focalisé n'est jamais entièrement caché par un élément fixe.
- [ ] Rendu à la souris inchangé (pas de contour parasite au clic).

## Vérification après correction

```bash
grep -rnE "outline:[[:space:]]*(none|0)|focus:outline-none" src public
```

Chaque résultat restant doit être justifié (remplacement visible dans la même règle). Refaire le parcours au clavier sur l'accueil, un article, le contact.

## Pièges et retour arrière

- Les navigateurs récents affichent déjà un focus par défaut ; c'est souvent la réinitialisation CSS (`* { outline: 0 }`) qui le retire.
- `:focus-visible` peut se déclencher au clic sur un champ de texte : c'est normal et souhaitable.
- Retour arrière : supprimer la règle globale ; sans impact fonctionnel (mais l'accessibilité se dégrade).

## Pour aller plus loin

- WCAG 2.4.7 (focus visible), 2.4.11 (focus non masqué, minimum) et 2.4.13 (apparence du focus, niveau AAA).
- MDN, pseudo-classe `:focus-visible`.
- RGAA, thématique Présentation de l'information (critère 10.7).
