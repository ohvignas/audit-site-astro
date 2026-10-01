---
id: perf-view-transitions
titre: View Transitions (ClientRouter) actives sur tout le site - coût JavaScript à justifier
domaine: Performance
severite_type: basse
effort: S
declencheurs:
  - "code:View Transitions \\(ClientRouter\\) actives"
sources:
  - https://docs.astro.build/en/guides/view-transitions/
  - https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API
  - https://docs.astro.build/en/guides/upgrade-to/v6/
---

# View Transitions (ClientRouter) actives sur tout le site - coût JavaScript à justifier

> **En une phrase** : le composant `<ClientRouter />` transforme le site en application à navigation côté client, ce qui ajoute du JavaScript sur toutes les pages et change le comportement des scripts ; à garder seulement s'il apporte une vraie valeur.

## Pourquoi c'est important

`<ClientRouter />` (ou l'ancien `<ViewTransitions />`) est chargé dans le `<head>` du layout, donc sur chaque page. Il intercepte les clics, télécharge la page suivante et remplace le contenu du DOM, ce qui permet des animations et la persistance d'éléments (lecteur audio, menu). Le coût : du JavaScript en plus au premier chargement, des navigations qui remplacent le DOM au lieu de recharger la page, des scripts qui ne s'exécutent qu'une fois, des extensions et outils d'analyse à reconfigurer. Si le site n'utilise ni animations de page ni éléments persistants, ce coût n'a aucun bénéfice.

## Comment le constater soi-même

```bash
grep -rnE "ClientRouter|ViewTransitions|transition:(animate|persist|name)" src | head
# Dans le HTML servi : le routeur est présent ?
curl -s https://SITE/ | grep -oE 'astro-route-announcer|data-astro-transition|<meta name="astro-view-transitions-enabled"[^>]*>' | sort -u
```

Problème présent : `<ClientRouter />` dans le layout principal sans aucun `transition:*` dans le code. Corrigé : routeur retiré, ou utilisé volontairement avec des directives.

## Correction

Choisir l'une des trois options.

1. **Le site n'utilise pas les transitions (cas le plus fréquent)** : retirer le composant du layout.

```astro
---
// AVANT
import { ClientRouter } from 'astro:transitions';
---
<head>
  <ClientRouter />
</head>

<!-- APRÈS : ni import, ni balise -->
```

Ensuite, si `prefetch` n'est plus activé automatiquement, le configurer explicitement (`perf-prefetch`).
2. **On veut seulement un fondu entre les pages, sans JavaScript** : utiliser les transitions natives entre documents du navigateur (API View Transition, supportée par les navigateurs récents ; ignorée par les autres, sans effet négatif). Dans le CSS global :

```css
@view-transition {
  navigation: auto;
}

@media (prefers-reduced-motion: reduce) {
  @view-transition { navigation: none; }
}
```

Chaque page se recharge normalement ; aucun routeur n'est chargé.
3. **On garde `<ClientRouter />`** (animations personnalisées, `transition:persist`) : le rendre sûr.
   - Limiter le repli : `<ClientRouter fallback="none" />` évite de simuler l'animation sur les navigateurs sans support.
   - Placer les initialisations de scripts dans l'événement `astro:page-load` (ils ne se rejouent pas sinon) :

```astro
<script>
  document.addEventListener('astro:page-load', () => {
    document.querySelector('#menu-bouton')?.addEventListener('click', () => {
      document.querySelector('#menu')?.classList.toggle('ouvert');
    });
  });
</script>
```

   - Les scripts `is:inline` ne se rejouent qu'avec `data-astro-rerun`.
   - Exclure du routeur les liens qui doivent recharger la page : `data-astro-reload`.
   - Respecter `prefers-reduced-motion` : Astro le fait pour ses animations par défaut, vérifier vos animations personnalisées.
4. Depuis Astro 6, `<ViewTransitions />` n'existe plus : le remplacer par `<ClientRouter />` (`import { ClientRouter } from 'astro:transitions'`).

## Critères d'acceptation

- [ ] `<ClientRouter />` est absent, ou justifié par au moins une directive `transition:*` utile
- [ ] Le JavaScript de page chargé sur une page sans îlot est réduit (comparer avant/après)
- [ ] Les menus, formulaires, analytics et scripts fonctionnent après navigation
- [ ] Aucune régression d'accessibilité (focus, annonce de changement de page, mouvement réduit)

## Vérification après correction

```bash
npm run build && du -sh dist/client/_astro 2>/dev/null || du -sh dist/_astro
curl -s https://SITE/ | grep -c 'astro-view-transitions-enabled'    # attendu : 0 si retiré
python3 scripts/astro_scan.py /chemin/projet --out /tmp/verif
```

## Pièges et retour arrière

- Retirer le routeur casse les composants qui écoutent `astro:page-load` : remplacer par un `DOMContentLoaded` ou un script de module simple.
- Les mesures d'analytics à navigation client demandent un événement de page vue spécifique ; retirer le routeur les simplifie.
- Retour arrière : remettre l'import et la balise dans le layout.

## Pour aller plus loin

- https://docs.astro.build/en/guides/view-transitions/ : `ClientRouter`, directives et repli.
- https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API : transitions natives entre documents.
- https://docs.astro.build/en/guides/upgrade-to/v6/ : suppression de `<ViewTransitions />`.
