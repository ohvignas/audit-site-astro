---
id: seo-contenu-rendu-client
titre: Contenu rendu uniquement côté navigateur (client:only) invisible pour les robots
domaine: SEO technique
severite_type: moyenne
effort: M
declencheurs:
  - "code:client:only : rien n.est rendu côté serveur"
sources:
  - https://docs.astro.build/en/reference/directives-reference/
  - https://docs.astro.build/en/concepts/islands/
  - https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics
---

# Contenu rendu uniquement côté navigateur (client:only) invisible pour les robots

> **En une phrase** : des composants sont marqués `client:only`, donc le HTML envoyé par le serveur ne contient rien de leur contenu, et tout robot qui n'exécute pas le JavaScript ne le voit pas.

## Pourquoi c'est important

La directive `client:only` « saute le rendu HTML côté serveur » : le composant n'existe qu'après le chargement et l'exécution du JavaScript. Google sait exécuter le JavaScript, mais en deux temps (exploration puis rendu différé), donc avec du retard et un risque d'échec. Beaucoup de robots d'assistants IA et d'aperçus de liens ne l'exécutent pas : le texte, les titres ou les liens contenus dans ces composants n'existent pas pour eux, et les liens qu'ils portent ne comptent pas dans le maillage interne. C'est acceptable pour un widget purement interactif (calculateur, carte, chat), mais pas pour du contenu qu'on veut faire trouver (texte, liste de produits, avis, FAQ, navigation).

## Comment le constater soi-même

```bash
# Ce que voit un robot sans JavaScript : le texte du composant est-il dans le HTML ?
curl -s https://SITE/page/ | grep -c "un texte qui devrait venir du composant"
curl -s https://SITE/page/ | grep -oE '<astro-island[^>]*client="only"[^>]*>' | head
# Composants concernés dans le code
grep -rn "client:only" src/ | head
```

`data/code/code-scan.md` liste les fichiers (constat « composant(s) client:only »).

## Correction

Pour chaque usage, décider si son contenu doit être indexé.

1. **Contenu à indexer** : passer d'une directive `client:only` à une directive avec rendu serveur. Le composant est alors rendu en HTML par le serveur puis « hydraté » dans le navigateur :

```astro
---
import Avis from '../components/Avis.tsx';
---
<!-- Avant : rien dans le HTML -->
<!-- <Avis client:only="react" /> -->

<!-- Après : rendu serveur + hydratation quand le composant devient visible -->
<Avis client:visible />
```

Choisir `client:visible` (sous la ligne de flottaison), `client:idle` (non critique) ou `client:load` (interaction immédiate). Le composant doit pouvoir s'exécuter côté serveur : pas d'accès à `window`, `document` ou `localStorage` pendant le rendu initial.

2. **Composant qui ne peut pas tourner sur le serveur** (bibliothèque dépendant du navigateur) : garder `client:only="react"` (le nom du framework est obligatoire), mais fournir un contenu de repli dans le HTML avec le slot `fallback`, et mettre le texte important **hors** de l'îlot :

```astro
<section>
  <h2>Nos avis clients</h2>
  <p>Note moyenne 4,8/5 sur 126 avis vérifiés.</p> <!-- texte présent dans le HTML -->
  <Carrousel client:only="react">
    <p slot="fallback">Chargement des avis…</p>
  </Carrousel>
</section>
```

3. **Données venant de Convex** : charger la donnée côté serveur dans la page `.astro` (requête au moment du rendu ou du build) et la passer en `props` au composant, plutôt que de la demander depuis le navigateur après coup :

```astro
---
const avis = await getAvis(); // côté serveur
---
<ListeAvis avis={avis} client:visible />
```

4. **Navigation et liens** : ne jamais placer le menu principal ni les liens vers les pages importantes dans un îlot `client:only`.
5. Garder `client:only` pour les vrais outils interactifs qui n'ont pas de valeur SEO (éditeur, simulateur, tableau de bord privé).

## Critères d'acceptation

- [ ] Tout contenu destiné à être indexé (texte, titres, liens) est présent dans le HTML brut (`curl`)
- [ ] Les `client:only` restants sont documentés comme purement interactifs, avec un repli (`slot="fallback"`)
- [ ] Aucun lien important n'est fourni uniquement par un composant `client:only`
- [ ] Aucune régression : composants toujours interactifs, pas d'erreur d'hydratation dans la console

## Vérification après correction

```bash
curl -s https://SITE/page/ | grep -c "un texte qui devrait venir du composant"   # attendu : >= 1
curl -s https://SITE/page/ | grep -c 'client="only"'                              # nombre d'îlots restants
python3 scripts/astro_scan.py . --out /tmp/verif-code                             # constat client:only
```

Comparer aussi le rendu dans l'outil d'inspection d'URL de la Search Console (HTML exploré).

## Pièges et retour arrière

- Passer de `client:only` à un rendu serveur peut faire apparaître des erreurs (`window is not defined`) : protéger les accès navigateur par un `useEffect` ou `typeof window !== 'undefined'`.
- Un écart entre le rendu serveur et le rendu client provoque une erreur d'hydratation : produire le même HTML des deux côtés.
- Retour arrière : remettre `client:only="react"` (ou le framework utilisé).

## Pour aller plus loin

- https://docs.astro.build/en/reference/directives-reference/ : directives `client:*` et `slot="fallback"`.
- https://docs.astro.build/en/concepts/islands/ : architecture en îlots.
- https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics : Google et le rendu JavaScript.
