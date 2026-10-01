---
id: perf-donnees-terrain-crux
titre: Données terrain Chrome UX Report (p75 des vrais visiteurs) mauvaises ou en dégradation
domaine: Performance
severite_type: haute
effort: M
declencheurs:
  - "terrain:^terrain_(lcp|inp|cls|fcp|ttfb)$"
  - "terrain:^terrain_degradation$"
sources:
  - https://developer.chrome.com/docs/crux/api
  - https://developer.chrome.com/docs/crux/history-api
  - https://web.dev/articles/vitals
---

# Données terrain Chrome UX Report (p75 des vrais visiteurs) mauvaises ou en dégradation

> **En une phrase** : les mesures réelles des visiteurs sur Chrome (75e centile, 28 jours) dépassent les seuils « bon » des Core Web Vitals (LCP, INP, CLS) ou des métriques complémentaires (FCP, TTFB), ou se dégradent sur l'historique ; ce sont les mesures que Google utilise pour les Core Web Vitals, pas les estimations de laboratoire.

## Pourquoi c'est important

Google s'appuie sur les données terrain du Chrome UX Report (CrUX) pour l'expérience de page : le 75e centile (p75) des visites mobiles sur 28 jours glissants. Le laboratoire (Lighthouse) n'en est qu'une estimation sur une machine et un réseau simulés, et peut écarter les vrais problèmes (appareils lents, réseau mobile, interactions réelles pour l'INP). Seuils « bon » des Core Web Vitals : LCP ≤ 2,5 s, INP ≤ 200 ms, CLS ≤ 0,1 ; métriques complémentaires (ni FCP ni TTFB ne sont des Core Web Vitals) : FCP ≤ 1,8 s et TTFB ≤ 0,8 s ; « mauvais » au-delà de 4 s, 500 ms, 0,25, 3 s et 1,8 s. L'outil interroge tous les appareils, puis mobile et ordinateur séparément. Sur l'historique (périodes hebdomadaires de 28 jours, environ 6 mois), il compare la moyenne des 4 dernières périodes à celle des 4 précédentes et signale une dégradation quand une métrique passe dans une catégorie pire (bon → à améliorer → mauvais) ou monte d'au moins 500 ms (LCP), 100 ms (INP), 0,05 (CLS), 300 ms (FCP, TTFB) sans être « bon » : une variation de bon à bon n'est jamais signalée.

## Comment le constater soi-même

```bash
# Résultat de l'audit (clé CRUX_API_KEY ou PSI_API_KEY dans l'environnement, jamais en argument ni dans un fichier du dépôt)
cat data/terrain/crux.md
```

Dans PageSpeed Insights (pagespeed.web.dev), le bloc « Découvrez ce que vivent vos utilisateurs » affiche les mêmes données pour l'URL et pour l'origine. Problème présent : une métrique en « mauvais » ou « à améliorer », ou une tendance en hausse. Corrigé : toutes les métriques en « bon » au p75, tendance stable ou en baisse.

## Correction

Traiter la métrique signalée dans `crux.md`, en partant de la plus mauvaise.

1. **LCP** : suivre les fiches `perf-lcp-diagnostic` (découpage du délai : serveur, découverte, chargement, affichage) et `perf-image-lcp-priorite` (image principale prioritaire, sans chargement différé).
2. **INP** : suivre `perf-js-thread-principal` (tâches longues, JavaScript tiers) et `perf-ilots-hydratation` (îlots hydratés trop tôt ou trop lourds).
3. **CLS** : suivre `perf-cls` (dimensions des images, bandeaux, polices, îlots).
4. **TTFB** (et FCP, qui en dépend) : suivre `serveur-ttfb-lent` ; sur un site Astro en rendu serveur, mettre en cache les routes qui ne dépendent pas de l'utilisateur (cache de routes d'Astro 7, ou en-tête `Cache-Control` / CDN).
5. **Dégradation** : comparer les dates des déploiements des 6 derniers mois avec la période où la courbe monte (l'historique est hebdomadaire, voir l'API d'historique de CrUX ; `crux.md` indique l'ancienneté du dernier point si les semaines récentes sont vides), puis revenir sur le changement fautif (nouvel îlot, script tiers, image plus lourde).
6. Mesurer d'abord en laboratoire (Lighthouse mobile) pour valider la correction, puis attendre que les données terrain se renouvellent.

## Critères d'acceptation

- [ ] p75 mobile « bon » sur 28 jours : LCP ≤ 2,5 s, INP ≤ 200 ms, CLS ≤ 0,1
- [ ] FCP ≤ 1,8 s et TTFB ≤ 0,8 s au p75
- [ ] Plus de changement de catégorie vers pire ni de hausse au-delà des planchers sur l'historique
- [ ] Correction vérifiée en laboratoire avant d'attendre un cycle complet de 28 jours

## Vérification après correction

```bash
# 28 jours après la mise en production (la fenêtre CrUX est glissante sur 28 jours)
python3 scripts/crux.py --out /tmp/verif --origine https://SITE --max-urls 5
cat /tmp/verif/crux.md
```

## Pièges et retour arrière

- Un petit site n'a souvent pas assez de trafic : l'API répond « pas de données » (ligne ⏭️ dans `crux.md`). C'est normal, ce n'est pas une erreur ; s'appuyer alors sur le laboratoire.
- Les données d'origine mélangent toutes les pages ; celles d'une URL n'existent que pour les pages assez visitées.
- Un site visité surtout depuis un ordinateur peut n'avoir aucune donnée mobile : `crux.md` le dit appareil par appareil (⏭️ « sur cet appareil ») sans conclure à un manque de trafic global.
- La fenêtre glissante de 28 jours lisse les changements : une correction n'apparaît pleinement qu'après un cycle complet.
- Les données ne portent que sur les visiteurs de Chrome ayant accepté le partage de statistiques ; elles peuvent différer d'un outil d'analyse.
- La clé CrUX est gratuite mais personnelle : ne jamais la commiter ni la coller dans un rapport.

## Pour aller plus loin

- https://developer.chrome.com/docs/crux/api : API du Chrome UX Report (données des 28 derniers jours).
- https://developer.chrome.com/docs/crux/history-api : API d'historique (séries hebdomadaires).
- https://web.dev/articles/vitals : définition et seuils des Core Web Vitals.
