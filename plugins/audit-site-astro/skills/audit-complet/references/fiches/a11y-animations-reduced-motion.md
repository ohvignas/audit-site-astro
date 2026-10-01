---
id: a11y-animations-reduced-motion
titre: "Animations, défilements et vidéos automatiques sans respect de prefers-reduced-motion"
domaine: Accessibilité
severite_type: moyenne
effort: S
declencheurs:
  - "manuel:reduced-motion"
sources:
  - https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html
  - https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html
  - https://www.w3.org/WAI/WCAG22/Understanding/three-flashes-or-below-threshold.html
  - https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion
  - https://web.dev/articles/prefers-reduced-motion
---

# Animations, défilements et vidéos automatiques sans respect de prefers-reduced-motion

> **En une phrase** : des animations (parallaxe, apparitions au défilement, carrousel, vidéo de fond) démarrent toujours, même chez les personnes qui ont demandé « réduire les animations » dans leur système, et peuvent provoquer nausées, vertiges ou gêne de lecture.

## Pourquoi c'est important

Les troubles vestibulaires, la migraine, l'épilepsie photosensible ou simplement les difficultés de concentration rendent les mouvements à l'écran pénibles, voire dangereux. Le réglage « Réduire les animations » des systèmes se lit dans CSS et JavaScript avec `prefers-reduced-motion`. WCAG 2.2.2 (mettre en pause, arrêter, masquer, niveau A) impose une commande pour tout mouvement automatique de plus de 5 secondes ; 2.3.1 interdit plus de trois flashs par seconde ; 2.3.3 (AAA) demande de pouvoir désactiver les animations déclenchées par l'interaction. RGAA thématiques 4 (Multimédia, critère 4.10) et 13 (Consultation, critère 13.8). **Contrôle manuel** : aucun outil automatique ne le détecte.

## Comment le constater soi-même

1. Activez « Réduire les animations » : macOS, Réglages Système, Accessibilité, Affichage ; Windows, Accessibilité, Effets visuels ; ou, dans Chrome, outils de développement, Rendu, « Emuler prefers-reduced-motion : reduce ».
2. Rechargez la page : plus aucun mouvement non essentiel (parallaxe, apparitions, défilement fluide, vidéo de fond).

```bash
grep -rnE "animation:|@keyframes|transition:|scroll-behavior|autoplay|data-aos|gsap|animate-|transition-" src | head -30
grep -rn "prefers-reduced-motion" src | head
```

## Correction

1. **Règle globale de repli** (en fin de la feuille de styles globale) : réduit les animations et transitions pour ceux qui l'ont demandé.

   ```css
   @media (prefers-reduced-motion: reduce) {
     *, *::before, *::after {
       animation-duration: 0.01ms !important;
       animation-iteration-count: 1 !important;
       transition-duration: 0.01ms !important;
       scroll-behavior: auto !important;
     }
   }
   ```

   Astuce plus douce : n'animer **que** si l'utilisateur ne s'y oppose pas.

   ```css
   @media (prefers-reduced-motion: no-preference) {
     .apparition { animation: fondu 0.6s ease both; }
   }
   ```
2. **Défilement fluide** : `html { scroll-behavior: smooth; }` seulement sous `@media (prefers-reduced-motion: no-preference)`.
3. **JavaScript** (parallaxe, bibliothèques d'animation) :

   ```ts
   const reduit = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
   if (!reduit) { /* initialiser l'animation */ }
   ```
4. **Vidéo de fond ou GIF animé** : pas de lecture automatique avec son ; si mouvement continu de plus de 5 secondes, offrir un bouton « Pause ». Sous `prefers-reduced-motion`, affichez une image fixe (`<video>` sans `autoplay`, ou `poster`).

   ```html
   <video muted loop playsinline poster="/img/fond.webp"></video>
   ```

   Puis lancez la lecture par JavaScript seulement si `!reduit`, avec un bouton pause/lecture visible.
5. **Carrousel automatique** : pas de rotation automatique par défaut, ou bouton de pause et arrêt au focus / survol.
6. **Contenus clignotants** : rien qui clignote plus de trois fois par seconde ; les animations Lottie/GIF sont à contrôler.
7. **Astro View Transitions** (`<ClientRouter />`) : gardez les animations discrètes et vérifiez qu'elles sont neutralisées sous `reduced-motion` (le test manuel ci-dessus le confirme ; sinon appliquez la règle globale).
8. **Défilement déclenché** (`data-aos`, GSAP ScrollTrigger) : contenu visible sans animation si JavaScript est désactivé ou si l'utilisateur a demandé moins de mouvement ; sinon le contenu reste invisible.

## Critères d'acceptation

- [ ] Avec « Réduire les animations » actif : plus de parallaxe, d'apparition animée ni de défilement fluide ; le contenu reste visible.
- [ ] Toute animation ou vidéo automatique de plus de 5 secondes a un bouton pause/arrêt.
- [ ] Aucune vidéo avec son en lecture automatique.
- [ ] Rien ne clignote plus de 3 fois par seconde.

## Vérification après correction

Refaire le test d'émulation dans Chrome sur l'accueil et une page à animations, puis désactiver l'émulation pour vérifier que les animations reviennent chez les autres utilisateurs.

## Pièges et retour arrière

- `animation-duration: 0.01ms` (et non `0`) évite de casser les scripts qui attendent l'événement `animationend`.
- Des éléments cachés en attente d'animation (`opacity: 0`) restent invisibles si l'animation est neutralisée : prévoyez l'état final visible par défaut.
- Retour arrière : retirer le bloc `@media` ; à éviter.

## Pour aller plus loin

- WCAG 2.2.2 (pause, arrêt, masquage) et 2.3.3 (animation liée aux interactions).
- MDN, `prefers-reduced-motion`.
- web.dev, guide `prefers-reduced-motion`.
- RGAA, critères 13.8 (contenus en mouvement ou clignotants contrôlables) et 4.10 (son déclenché automatiquement).
