---
id: a11y-svg-inline
titre: "SVG inline sans nom accessible ou non masqués (icônes)"
domaine: Accessibilité
severite_type: moyenne
effort: S
declencheurs:
  - "crawl:svg_non_masque"
  - "crawl:svg_img_sans_nom"
  - "crawl:svg_redondant_controle"
  - "lighthouse:svg-img-alt"
sources:
  - https://accessibilite.numerique.gouv.fr/methode/criteres-et-tests/
  - https://www.w3.org/WAI/standards-guidelines/act/rules/7d6734/proposed
  - https://dequeuniversity.com/rules/axe/4.10/svg-img-alt
---

# SVG inline sans nom accessible ou non masqués

> **En une phrase** : les icônes SVG décoratives ne sont pas masquées aux lecteurs d'écran (RGAA 1.2.4) et les SVG porteurs d'information n'ont pas de nom (WCAG 1.1.1) ; WAVE compte chaque icône comme une erreur.

## Pourquoi c'est important

Un lecteur d'écran annonce « image » ou rien d'utile pour chaque icône non masquée : sur une page de 130 icônes, la lecture devient inutilisable. Le RGAA (obligatoire pour les entités assujetties) demande `aria-hidden="true"` sur les SVG décoratifs et un nom (`role="img"` + `aria-label` ou `<title>`) sur les SVG informatifs. Sur beta.illith.com, WAVE relevait 136 erreurs « Missing alternative text » sur l'accueil, dues à 128 icônes SVG ni masquées ni nommées, issues d'un petit nombre de composants.

Le rapport regroupe les icônes par composant (`viewBox`, `fill`, balise parente et ses deux premières classes) : 128 icônes donnent quelques constats avec le nombre d'occurrences et des pages d'exemple, pas 128 lignes. Trois constats :
- `svg_non_masque` (moyenne) : icône décorative hors lien et bouton, sans `aria-hidden` ;
- `svg_img_sans_nom` (haute) : `role="img"` sans nom ;
- `svg_redondant_controle` (basse, simple conseil) : icône non masquée dans un lien ou un bouton qui a déjà un nom (texte, `aria-label`, `title`) ; ce n'est pas une erreur, le lecteur d'écran lit juste une redite.

Ne sont **pas** signalés : SVG masqué (lui-même ou un ancêtre : `aria-hidden`, `hidden`, `display:none`, `<template>`), `role="presentation"` ou `"none"`, SVG nommé (`aria-label`, `<title>`, `aria-labelledby` vers un `id` existant), conteneur de définitions (`width="0"`), SVG imbriqué.

## Comment le constater soi-même

```bash
python3 -c "import json;d=json.load(open('data/crawl/issues.json'));[print(e['occurrences'], e['signature'], e['exemples_pages'][0]) for k in ('svg_non_masque','svg_img_sans_nom','svg_redondant_controle') for e in d.get(k,{}).get('examples',[])]"
grep -rn "<svg" src/components | grep -v 'aria-hidden'
```
La signature (`viewBox`, `fill`, parent et ses classes) désigne le composant à corriger : chercher ce `viewBox` dans `src/`.

## Correction

1. Icône décorative (à côté d'un texte, ou dans un bouton qui a un `aria-label`) : la masquer dans le composant, une fois pour tout le site.
```astro
---
// src/components/Icon.astro
const { name, label } = Astro.props;
---
{label
  ? <svg role="img" aria-label={label} viewBox="0 0 24 24"><use href={`#${name}`} /></svg>
  : <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24"><use href={`#${name}`} /></svg>}
```
2. SVG informatif (note, graphique, logo seul dans un lien) : `role="img"` et un nom (`aria-label` ou `<title id>` + `aria-labelledby`).
3. Avec `astro-icon`, `<Icon name="…" />` sans `title` produit déjà `aria-hidden="true"` : vérifier que le composant n'est pas contourné par des SVG collés à la main.

## Critères d'acceptation

- [ ] `svg_non_masque` et `svg_img_sans_nom` absents de `data/crawl/issues.json` (`svg_redondant_controle` est un conseil : le traiter dans le même composant d'icône)
- [ ] Les SVG informatifs gardent un nom lisible (vérifier une page avec un lecteur d'écran ou l'arbre d'accessibilité de Chrome)
- [ ] Aucune régression visuelle (rendu des icônes identique)

## Vérification après correction

```bash
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl --liens-externes 0
python3 -c "import json;d=json.load(open('/tmp/verif/crawl/issues.json'));print(d.get('svg_non_masque',{}).get('count',0), d.get('svg_img_sans_nom',{}).get('count',0))"   # 0 0
```

## Pièges et retour arrière

- Ne pas masquer un SVG qui est le **seul** contenu d'un lien ou d'un bouton : le lien perdrait son nom ; lui donner plutôt un `aria-label` (voir la fiche des noms de liens et boutons). Ce cas relève de `lien_sans_nom` / `bouton_sans_nom`, pas de cette fiche.
- `aria-labelledby` vers un `id` absent ne donne aucun nom : le SVG est signalé ici, et la référence cassée dans la fiche des références ARIA.
- `focusable="false"` évite un arrêt de tabulation parasite dans d'anciens navigateurs.
- Retour arrière : `git revert` du composant d'icône.
