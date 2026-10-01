---
id: a11y-svg-inline
titre: "SVG inline sans nom accessible ou non masqués (icônes, étoiles de notes)"
domaine: Accessibilité
severite_type: moyenne
effort: S
declencheurs:
  - "crawl:svg_non_masque"
  - "crawl:svg_img_sans_nom"
  - "crawl:svg_redondant_controle"
sources:
  - https://accessibilite.numerique.gouv.fr/methode/criteres-et-tests/
  - https://www.w3.org/WAI/standards-guidelines/act/rules/7d6734/proposed
  - https://dequeuniversity.com/rules/axe/4.10/svg-img-alt
---

# SVG inline sans nom accessible ou non masqués

> **En une phrase** : les icônes SVG décoratives ne sont pas masquées aux lecteurs d'écran (RGAA 1.2.4) et les SVG porteurs d'information n'ont pas de nom (WCAG 1.1.1) ; un seul composant d'icône mal écrit produit des dizaines d'erreurs dans WAVE.

## Pourquoi c'est important

Un lecteur d'écran annonce « image » ou rien d'utile pour chaque icône non masquée : sur une page qui en compte une centaine, la lecture devient inutilisable. Le RGAA (obligatoire pour les entités assujetties) demande `aria-hidden="true"` sur les SVG décoratifs et un nom (`role="img"` + `aria-label` ou `<title>`) sur les SVG informatifs.

L'audit regroupe les icônes par type : la signature est faite du `viewBox`, du `fill` et du `stroke` du SVG, et l'exemple donne la balise ouverte (taille, couleurs, classe), le début du premier tracé et son empreinte. Un composant d'icônes qui dessine vingt pictogrammes dans la même taille donne un seul constat (« +N autres tracés »), les plus gros groupes en premier. Chercher dans `src/` la classe, les couleurs ou le début du tracé de l'exemple pour trouver le composant.

Trois constats :
- `svg_non_masque` (moyenne) : icône décorative hors lien et bouton, sans `aria-hidden` ;
- `svg_img_sans_nom` (haute) : `role="img"` sans nom ;
- `svg_redondant_controle` (basse) : icône non masquée dans un lien ou un bouton qui a déjà un nom (texte, `aria-label`, `title`) ; même défaut RGAA 1.2.4, impact faible puisque le nom est déjà lu, même correctif.

**Pourquoi WAVE peut en compter plus que l'audit.** L'audit ne retient que les SVG réellement exposés aux lecteurs d'écran. Ne sont **pas** signalés : SVG masqué (lui-même ou un ancêtre : `aria-hidden`, `hidden`, `display:none`, `<template>`), `role="presentation"` ou `"none"`, SVG nommé (`aria-label`, `<title>`, `aria-labelledby` vers un `id` existant), SVG sous une enveloppe `role="img"` nommée, conteneur de définitions (sprite, `width="0"`), SVG imbriqué. Un outil qui compte tout SVG sans `aria-hidden` sur lui-même inclut aussi ceux des ancêtres masqués et des panneaux repliés, d'où un total plus élevé.

## Comment le constater soi-même

```bash
python3 -c "import json;d=json.load(open('data/crawl/issues.json'));[print(e['occurrences'], e['signature'], e.get('exemple','')) for k in ('svg_non_masque','svg_img_sans_nom','svg_redondant_controle') for e in d.get(k,{}).get('examples',[])]"
grep -rn "<svg" src/components | grep -v 'aria-hidden'
```

## Correction

1. Icône décorative (à côté d'un texte, ou dans un bouton qui a un `aria-label`) : la masquer dans le composant, une fois pour tout le site. Exemple d'un composant d'icônes qui inline ses tracés :
```astro
---
// src/components/Icon.astro
const { size = 18, label } = Astro.props;
---
<svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor"
     {...(label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': 'true', focusable: 'false' })}>
  <slot />
</svg>
```
2. SVG informatif seul (graphique, logo seul dans un lien) : `role="img"` et un nom (`aria-label` ou `<title id>` + `aria-labelledby`).
3. Vérifier qu'aucun SVG collé à la main dans une page ou un composant ne contourne le composant d'icône.

### Notes en étoiles

Cinq étoiles ne doivent pas être cinq images « étoile » : la note est **une** information, nommée **une** fois.

```astro
<!-- Les étoiles seules portent la note (carte d'avis) : un nom sur l'enveloppe, étoiles masquées -->
<span role="img" aria-label="Note : 5 sur 5">
  {Array.from({ length: 5 }, () => <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="15" height="15" fill="#FBBC05"><path d="…" /></svg>)}
</span>

<!-- Variante : texte visuellement masqué, étoiles masquées -->
<span><span class="sr-only">Note : 5 sur 5</span>{étoiles avec aria-hidden="true"}</span>

<!-- La note chiffrée est déjà affichée à côté (« 4,8 / 5 ») : aria-hidden sur chaque étoile suffit -->
```
Les enfants d'un `role="img"` sont présentationnels pour les technologies d'assistance : l'audit ne signale donc pas des étoiles sous une enveloppe `role="img"` qui a un nom (`aria-label`, `title`, `aria-labelledby`). Garder malgré tout `aria-hidden="true"` sur chaque étoile : c'est le plus robuste.

### Contenu replié ou masqué au chargement

Onglets, accordéons et cartes repliées sont ignorés par l'audit tant qu'ils sont masqués (`hidden`, `display:none`), mais leurs icônes deviennent exposées dès l'affichage. Corriger le composant d'icône, pas seulement ce qui est visible au chargement.

## Critères d'acceptation

- [ ] `svg_non_masque` et `svg_img_sans_nom` absents de `data/crawl/issues.json` (`svg_redondant_controle` : même correctif, dans le même composant d'icône)
- [ ] Les SVG informatifs gardent un nom lisible, une seule fois par information (vérifier une page avec un lecteur d'écran ou l'arbre d'accessibilité de Chrome)
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
