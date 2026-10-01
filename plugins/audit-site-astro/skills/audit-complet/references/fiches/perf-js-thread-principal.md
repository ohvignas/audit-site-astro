---
id: perf-js-thread-principal
titre: Thread principal saturé (tâches longues, TBT élevé, exécution JavaScript trop lourde)
domaine: Performance
severite_type: haute
effort: M
declencheurs:
  - "lighthouse:bootup-time|mainthread-work-breakdown|long-tasks|forced-reflow-insight|slow-css-selector|interaction-to-next-paint-insight|Réduisez le temps d'exécution de JavaScript|Réduisez le travail du thread principal|Évitez les tâches longues dans le thread principal|Ajustement forcé de la mise en page|Coûts des sélecteurs CSS"
sources:
  - https://web.dev/articles/optimize-long-tasks
  - https://web.dev/articles/tbt
  - https://web.dev/articles/inp
  - https://developer.mozilla.org/en-US/docs/Web/API/Scheduler/yield
---

# Thread principal saturé (tâches longues, TBT élevé, exécution JavaScript trop lourde)

> **En une phrase** : le navigateur passe des centaines de millisecondes à exécuter du JavaScript sans pouvoir répondre aux clics ni afficher la page, ce qui dégrade l'interactivité (TBT en labo, INP en réel).

## Pourquoi c'est important

Le navigateur n'a qu'un seul thread pour exécuter le JavaScript, calculer la mise en page et réagir aux actions. Une « tâche longue » dure plus de 50 ms ; le TBT additionne la part au-delà de 50 ms de toutes ces tâches (bon : moins de 200 ms sur mobile en labo). En conditions réelles, l'INP (bon : 200 ms ou moins, pour 75 % des visites) mesure le délai entre une action et la mise à jour de l'écran. Ces mesures dépendent surtout du JavaScript qui s'exécute au chargement : hydratation d'îlots, scripts tiers, boucles lourdes, lectures de mise en page répétées.

## Comment le constater soi-même

```bash
# Synthèse de l'outil : TBT, temps d'exécution JS, travail du thread principal
grep -iE "TBT|js_execution_ms|thread_principal_ms|Tiers" /tmp/verif/pagespeed-summary.md
# Îlots hydratés au chargement
grep -rn "client:load" src | head
```

Ensuite, dans Chrome : DevTools > Performance > enregistrer un chargement (option « CPU 4x slowdown ») ; les tâches longues sont marquées d'un triangle rouge. L'onglet « Bottom-Up » indique quels scripts consomment le plus.

Problème présent : TBT supérieur à 300 ms, tâches longues attribuées à `/_astro/…js` ou à des scripts tiers. Corrigé : TBT < 200 ms, aucune tâche de plus de 200 ms au chargement.

## Correction

1. **Identifier les coupables** avec l'enregistrement de performance : fichier, fonction, durée. Quatre familles : hydratation d'îlots, scripts tiers, code de la page, mise en page forcée.
2. **Hydratation** : réduire les `client:load`, passer à `client:idle` / `client:visible`, et convertir en `.astro` ce qui est statique (`perf-ilots-hydratation`).
3. **Scripts tiers** : différer ou retirer (`perf-js-tiers`).
4. **Découper une longue boucle** pour laisser respirer le navigateur. `scheduler.yield()` n'existe pas dans tous les navigateurs : prévoir un repli.

```ts
const rendreLaMain = (): Promise<void> =>
  'scheduler' in globalThis && 'yield' in (globalThis as any).scheduler
    ? (globalThis as any).scheduler.yield()
    : new Promise((resolve) => setTimeout(resolve, 0));

export async function traiterEnLots<T>(elements: T[], traiter: (e: T) => void, tailleLot = 50) {
  for (let i = 0; i < elements.length; i += tailleLot) {
    elements.slice(i, i + tailleLot).forEach(traiter);
    await rendreLaMain();
  }
}
```

5. **Éviter la mise en page forcée** (audit « Ajustement forcé de la mise en page ») : ne pas alterner lecture (`offsetHeight`, `getBoundingClientRect()`) et écriture de styles dans une boucle. Lire tout d'abord, écrire ensuite, ou passer par `requestAnimationFrame`.
6. **Longues listes** : paginer, ou laisser le navigateur ignorer le rendu hors écran :

```css
.liste-item { content-visibility: auto; contain-intrinsic-size: auto 200px; }
```

7. **CSS coûteux** (audit « Coûts des sélecteurs CSS ») : simplifier les sélecteurs très profonds ou universels (`*`, `[class*=…]` sur de larges zones).
8. **Travail de calcul lourd** (tri, recherche locale, traitement d'image) : le déplacer dans un Web Worker.
9. **Écouteurs d'événements** : garder les gestionnaires de clic courts ; déclencher les calculs longs après avoir mis à jour l'interface.

## Critères d'acceptation

- [ ] TBT mobile inférieur à 200 ms sur les pages clés (labo)
- [ ] Aucune tâche longue de plus de 200 ms pendant le chargement dans l'enregistrement DevTools
- [ ] « Réduisez le temps d'exécution de JavaScript » sous 2 s (mobile) ou plus signalé
- [ ] Fonctionnalités inchangées ; INP terrain (CrUX/PageSpeed) sous 200 ms lorsqu'il est disponible

## Vérification après correction

```bash
RUNS=3 bash scripts/lighthouse_run.sh /tmp/verif https://SITE/    # médiane de 3 passages
grep -iE "TBT|js_execution_ms" /tmp/verif/pagespeed-summary.md
```

## Pièges et retour arrière

- Lighthouse varie de plus ou moins 5 à 10 points d'un passage à l'autre : comparer sur 3 passages.
- Un TBT bas ne garantit pas un bon INP : tester les interactions réelles (menu, filtre, formulaire).
- Retour arrière : restaurer les directives et scripts d'origine (`git revert`).

## Pour aller plus loin

- https://web.dev/articles/optimize-long-tasks : découper les tâches longues.
- https://web.dev/articles/tbt : ce que mesure le Total Blocking Time.
- https://web.dev/articles/inp : Interaction to Next Paint.
- https://developer.mozilla.org/en-US/docs/Web/API/Scheduler/yield : `scheduler.yield()`.
