---
id: perf-lcp-diagnostic
titre: LCP trop lent - décomposer les quatre phases pour trouver la vraie cause
domaine: Performance
severite_type: haute
effort: M
declencheurs:
  - "lighthouse:largest-contentful-paint-element|lcp-phases-insight|lcp-breakdown-insight|Élément identifié comme|Répartition du LCP"
sources:
  - https://web.dev/articles/optimize-lcp
  - https://web.dev/articles/lcp
  - https://developer.chrome.com/docs/lighthouse/performance/lighthouse-largest-contentful-paint
---

# LCP trop lent - décomposer les quatre phases pour trouver la vraie cause

> **En une phrase** : le plus gros élément visible s'affiche trop tard ; avant de corriger, il faut savoir dans quelle phase le temps se perd (serveur, découverte, téléchargement ou affichage).

## Pourquoi c'est important

Le LCP (Largest Contentful Paint) est la métrique de chargement qui pèse le plus. Google demande 2,5 s ou moins pour 75 % des visites (mesure terrain). Ce temps se compose de quatre phases : TTFB (réponse du serveur), délai de chargement de la ressource, durée de chargement de la ressource, délai d'affichage de l'élément. Répartition idéale d'après web.dev : environ 40 % de TTFB, moins de 10 % de délai de chargement, environ 40 % de durée de chargement et moins de 10 % de délai d'affichage. Un écart net avec ces valeurs indique la phase à traiter. Corriger la mauvaise phase fait perdre du temps sans améliorer le LCP.

## Comment le constater soi-même

```bash
# Élément LCP et métriques mesurés par l'outil
grep -iE "Élément LCP|LCP" /tmp/verif/pagespeed-summary.md
# TTFB de la page
curl -s -o /dev/null -w 'TTFB %{time_starttransfer}s\n' https://SITE/
```

Dans Chrome : DevTools > Performance > enregistrer le chargement (mobile émulé, CPU 4x et réseau « Fast 4G ») ; la piste « Timings » montre le LCP, et l'analyse « LCP breakdown » donne les quatre phases en ms. Lighthouse le rapporte aussi (« Répartition du LCP », « Détection de la requête LCP »).

## Correction

1. **Identifier l'élément LCP** sur mobile ET sur ordinateur (il peut différer). C'est une image, un titre ou un bloc de texte, parfois une image de fond.
2. **Lire la phase la plus longue** et appliquer la fiche correspondante :

| Phase dominante | Cause probable | Fiche à appliquer |
|---|---|---|
| TTFB élevé (> 0,8 s) | Serveur lent, rendu à la demande sans cache, requêtes Convex lentes | fiches serveur / cache ; `perf-streaming-html` |
| Délai de chargement (l'image démarre tard) | Image en `lazy`, sans priorité, découverte par le JavaScript ou le CSS | `perf-image-lcp-priorite`, `perf-prechargement-ressources` |
| Durée de chargement longue | Image trop lourde, mauvais format, pas de `srcset`, pas de compression | `perf-images-formats-modernes`, `perf-images-responsives`, `perf-images-convex-storage`, `perf-images-brutes-public` |
| Délai d'affichage (l'élément est prêt mais pas affiché) | CSS ou polices bloquants, JavaScript qui retarde le rendu, îlot non hydraté | `perf-css-bloquant`, `perf-polices`, `perf-ilots-hydratation`, `perf-js-thread-principal` |

3. **LCP texte (titre H1)** : les causes sont presque toujours la police (`perf-polices`), le CSS bloquant (`perf-css-bloquant`) ou l'exécution JavaScript au chargement (`perf-js-thread-principal`).
4. **Une correction à la fois**, puis remesurer (`RUNS=3` pour la médiane). Noter le LCP avant et après.
5. **Confirmer avec des données terrain** quand elles existent (rapport PageSpeed « Découvrez ce que vivent vos utilisateurs réels »), car le labo peut différer du réel.

## Critères d'acceptation

- [ ] L'élément LCP de chaque page clé est identifié (mobile et ordinateur)
- [ ] La phase dominante est identifiée et traitée par la fiche correspondante
- [ ] LCP mobile en labo ≤ 2,5 s sur les pages clés (idéalement ≤ 2 s)
- [ ] La répartition des phases se rapproche de l'idéal (TTFB environ 40 %, délais < 10 %)

## Vérification après correction

```bash
RUNS=3 bash scripts/lighthouse_run.sh /tmp/verif https://SITE/ https://SITE/page-cle
grep -iE "LCP|Élément LCP" /tmp/verif/pagespeed-summary.md
```

## Pièges et retour arrière

- Lighthouse varie de plus ou moins 5 à 10 points d'un passage à l'autre : raisonner sur la médiane de plusieurs mesures.
- Le LCP terrain dépend des visiteurs (réseau, appareil) : ne pas viser uniquement le score labo.
- Retour arrière : aucun changement à annuler dans cette fiche, qui est une méthode.

## Pour aller plus loin

- https://web.dev/articles/optimize-lcp : les quatre phases et leur optimisation.
- https://web.dev/articles/lcp : définition et seuils du LCP.
- https://developer.chrome.com/docs/lighthouse/performance/lighthouse-largest-contentful-paint : mesure du LCP par Lighthouse.
