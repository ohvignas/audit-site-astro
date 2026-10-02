---
id: a11y-listes-tableaux-iframes
titre: "Listes, tableaux et iframes mal balisés (structure et titres manquants)"
domaine: Accessibilité
severite_type: moyenne
effort: S
declencheurs:
  - "crawl:iframe_sans_titre"
  - "lighthouse:\\blist\\b|listitem|definition-list|dlitem|th-has-data-cells|td-has-header|td-headers-attr|table-fake-caption|table-duplicate-name|frame-title"
  - "lighthouse:Les listes ne contiennent pas uniquement|ne sont pas inclus dans des éléments parents|`<dl>` ne contiennent pas uniquement|liste de définition ne sont pas encapsulés|ne décrivent aucune cellule de données|d'un grand `<table>` n'ont pas|font référence à un élément `id`|n'utilisent pas `<caption>`|attribut \"summary\"|`<frame>` ou `<iframe>` n'ont pas de titre"
sources:
  - https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships.html
  - https://www.w3.org/WAI/tutorials/tables/
  - https://dequeuniversity.com/rules/axe/4.10/frame-title
  - https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/table
  - https://accessibilite.numerique.gouv.fr/methode/criteres-et-tests/#5.4
---

# Listes, tableaux et iframes mal balisés (structure et titres manquants)

> **En une phrase** : des listes, des tableaux de données ou des cadres intégrés (carte, vidéo, formulaire tiers) n'ont pas la structure HTML attendue, si bien que les lecteurs d'écran ne peuvent pas annoncer « liste de 5 éléments » ou « cellule : tarif, ligne Offre pro ».

## Pourquoi c'est important

Les lecteurs d'écran annoncent le nombre d'éléments d'une liste et permettent de se déplacer de cellule en cellule dans un tableau en énonçant l'en-tête de ligne et de colonne. Cela suppose un balisage correct : `<li>` dans `<ul>` ou `<ol>`, `<th>` pour les en-têtes, `<caption>` pour le titre. Une `<iframe>` sans `title` est annoncée « cadre » : l'utilisateur ne sait pas s'il s'agit d'une carte, d'une vidéo ou d'un widget publicitaire. WCAG 1.3.1, 4.1.2, 2.4.1 ; RGAA thématiques 5 (Tableaux), 9 (Structuration) et 2 (Cadres).

## Comment le constater soi-même

```bash
grep -rnE "<iframe" src | grep -v "title=" | head            # iframes sans title
grep -rnE "<table" src | head                                  # tableaux : vérifier th et caption
grep -rnE "<li>" src | head -5                                 # <li> hors ul/ol
```

Navigateur : inspecteur, Accessibilité : la liste est-elle de rôle « list », le tableau de rôle « table » avec ses en-têtes ?

## Correction

1. **Listes** : seuls des `<li>` (et `<script>`/`<template>`) peuvent se trouver directement dans `<ul>`/`<ol>`/`<menu>`, et chaque `<li>` doit avoir un tel parent.

   ```astro
   <ul>
     <li>Audit technique</li>
     <li>Plan d'action</li>
   </ul>
   ```

   Erreur fréquente : un composant qui enveloppe chaque `<li>` dans un `<div>` (rendu `<ul><div><li>`). Retirez le `div` ou passez au `<li>` lui-même la classe.
2. **Listes de définition** : `<dl>` contient des groupes `<dt>` + `<dd>` (un `<div>` autour d'un groupe est autorisé) ; `<dt>`/`<dd>` hors `<dl>` sont interdits.
3. **Tableaux de données** : `<caption>`, `<thead>`, `<th scope="col|row">`.

   ```astro
   <table>
     <caption>Tarifs de la formation</caption>
     <thead>
       <tr><th scope="col">Offre</th><th scope="col">Durée</th><th scope="col">Prix HT</th></tr>
     </thead>
     <tbody>
       <tr><th scope="row">Découverte</th><td>1 jour</td><td>450 €</td></tr>
       <tr><th scope="row">Complète</th><td>3 jours</td><td>1 200 €</td></tr>
     </tbody>
   </table>
   ```

   - Légende faite avec une cellule fusionnée (`colspan`) : remplacez par `<caption>`.
   - `<caption>` et attribut `summary` identiques : supprimez `summary` (obsolète).
   - `headers="..."` : chaque identifiant cité doit exister dans le même tableau.
   - `<th>` qui ne décrit aucune donnée : utilisez `<td>` pour les cellules vides ou de mise en forme.
   - **Ne pas utiliser de tableau pour la mise en page** ; utiliser CSS Grid/Flexbox.
4. **Tableaux qui débordent sur mobile** : enveloppez dans un conteneur défilable focalisable.

   ```html
   <div class="tableau-defilant" role="region" aria-labelledby="titre-tarifs" tabindex="0"> ... </div>
   ```
5. **Iframes** (`frame-title`) : un `title` court et précis qui décrit le contenu.

   ```astro
   <iframe title="Carte : accès à nos bureaux à Lyon" src="https://www.openstreetmap.org/export/embed.html?bbox=..." loading="lazy"></iframe>
   <iframe title="Vidéo de présentation, avec sous-titres" src="https://www.youtube-nocookie.com/embed/IDENTIFIANT" loading="lazy" allowfullscreen></iframe>
   ```

   Iframes purement techniques (pixels de suivi) : `aria-hidden="true"` et `tabindex="-1"`, ou mieux, supprimez-les.
6. **Composants Astro/React de liste** : un composant `Liste` doit produire du vrai `<ul>/<li>` ; testez le rendu HTML final, pas le composant.

## Critères d'acceptation

- [ ] Chaque `<li>` a un parent `ul/ol/menu` ; chaque `<dt>/<dd>` est dans un `dl`.
- [ ] Les tableaux de données ont `<caption>` et des `<th>` avec `scope` ; aucun tableau de mise en page.
- [ ] Toute iframe a un `title` explicite.
- [ ] Lighthouse : audits `list`, `listitem`, `definition-list`, `dlitem`, `th-has-data-cells`, `td-has-header`, `td-headers-attr`, `table-fake-caption`, `table-duplicate-name`, `frame-title` réussis.

## Vérification après correction

```bash
npx lighthouse https://exemple.fr/ --only-categories=accessibility --quiet --output=json --output-path=/tmp/a11y.json --locale=fr
python3 -c "
import json; a=json.load(open('/tmp/a11y.json'))['audits']
ids='list listitem definition-list dlitem th-has-data-cells td-has-header td-headers-attr table-fake-caption table-duplicate-name frame-title'.split()
print({k:a[k]['score'] for k in ids if k in a and a[k]['score'] not in (None,1)})"
```

## Pièges et retour arrière

- Le HTML rendu diffère du composant source : corrigez le rendu final (menus de bibliothèques, contenu CMS).
- Retirer `role="list"` mis pour Safari (après `list-style: none`) peut faire perdre l'annonce de liste : gardez-le seulement sur ces listes-là.
- Retour arrière : restaurer le composant (Git).

## Pour aller plus loin

- WCAG 1.3.1 (information et relations).
- W3C WAI, tutoriel « Tableaux ».
- Lighthouse, audit `frame-title`.
- RGAA, thématique Tableaux et Cadres.
