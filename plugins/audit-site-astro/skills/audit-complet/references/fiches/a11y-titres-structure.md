---
id: a11y-titres-structure
titre: "Structure de la page : ordre des titres, titres vides, zone principale absente"
domaine: Accessibilité
severite_type: moyenne
effort: S
declencheurs:
  - "crawl:titres_sautes"
  - "lighthouse:heading-order|empty-heading|landmark-one-main"
  - "lighthouse:éléments d'en-tête ne sont pas classés séquentiellement|éléments de titre n'ont pas de contenu|ne contient pas de repère principal"
sources:
  - https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships.html
  - https://www.w3.org/WAI/WCAG22/Understanding/headings-and-labels.html
  - https://www.w3.org/WAI/tutorials/page-structure/headings/
  - https://dequeuniversity.com/rules/axe/4.10/heading-order
  - https://docs.astro.build/en/basics/astro-syntax/#dynamic-tags
  - https://accessibilite.numerique.gouv.fr/methode/criteres-et-tests/#9.1
---

# Structure de la page : ordre des titres, titres vides, zone principale absente

> **En une phrase** : les titres (`h1` à `h6`) sautent de niveau, sont vides, ou la page n'a pas de zone principale (`<main>`), ce qui empêche de naviguer par sections avec un lecteur d'écran.

## Pourquoi c'est important

Les utilisateurs de lecteurs d'écran naviguent par titres (touche H) et par repères (main, nav, footer) : c'est leur table des matières. Un `h4` juste après un `h2`, ou un titre vide, leur fait croire qu'il manque du contenu. WCAG 1.3.1 (structure), 2.4.6 ; RGAA thématique 9 (Structuration de l'information). Une bonne hiérarchie aide aussi le SEO (un seul `h1`, sections claires).

## Comment le constater soi-même

```bash
# Plan des titres d'une page (niveau + texte)
curl -s https://exemple.fr/ | tr '\n' ' ' | grep -oE '<h[1-6][^>]*>[^<]*' | sed -E 's/<h([1-6])[^>]*>/H\1 /' | head -40
curl -s https://exemple.fr/ | grep -c '<main'           # attendu : 1
```

Corrigé : un seul `H1`, puis des `H2`, chaque `H3` sous un `H2`, aucun niveau sauté vers le bas (passer de H2 à H4). On peut remonter de niveau librement (H4 vers H2).

## Correction

1. **Décider du plan de la page** : `h1` = sujet de la page (un seul) ; `h2` = grandes parties ; `h3` = sous-parties. Le niveau dépend du **plan**, jamais de la taille souhaitée du texte.
2. **Composants avec un niveau de titre fixe** (carte avec `h3` placée sous un `h1`) : rendez le niveau paramétrable.

   ```astro
   ---
   // src/components/Carte.astro
   interface Props { titre: string; niveau?: 2 | 3 | 4 }
   const { titre, niveau = 3 } = Astro.props;
   const Titre = `h${niveau}` as 'h2' | 'h3' | 'h4';
   ---
   <article class="carte">
     <Titre class="carte__titre">{titre}</Titre>
     <slot />
   </article>
   ```

   ```astro
   <h2>Nos formations</h2>
   <Carte titre="SEO technique" niveau={3} />
   ```
3. **Titres choisis pour leur apparence** : remplacez par la balise correcte et gardez l'aspect avec une classe CSS (`<h3 class="text-xl">`), ou utilisez `<p class="titre-visuel">` si ce n'est pas un vrai titre.
4. **Titres vides** (`<h2></h2>`, ou seulement une icône / image sans alt) : supprimez la balise ou ajoutez le texte (masqué visuellement si besoin, voir `a11y-noms-boutons-liens`). Vérifiez les composants qui affichent un titre facultatif.
5. **Zone principale** : la page doit contenir exactement un `<main>`, placé dans la mise en page commune.

   ```astro
   ---
   // src/layouts/Base.astro
   const { titre } = Astro.props;
   ---
   <html lang="fr">
     <head><meta charset="utf-8" /><title>{titre}</title></head>
     <body>
       <a href="#contenu" class="lien-evitement">Aller au contenu</a>
       <header><nav aria-label="Navigation principale"><!-- menu --></nav></header>
       <main id="contenu" tabindex="-1"><slot /></main>
       <footer><!-- pied de page --></footer>
     </body>
   </html>
   ```
6. **Repères** : `<header>`, `<nav aria-label="...">` (un libellé distinct par `nav` si plusieurs), `<main>`, `<aside>`, `<footer>` ; ne mettez pas de `role` inutile sur ces balises natives.
7. Les contenus provenant du CMS ou du Markdown commencent souvent à `h1` : décalez-les (rendu Markdown des articles à partir de `h2`).

## Critères d'acceptation

- [ ] Un seul `h1` par page, aucun niveau sauté vers le bas.
- [ ] Aucun titre vide.
- [ ] Un seul `<main>` par page, hors du `<header>` et du `<footer>`.
- [ ] Les Lighthouse « Les éléments d'en-tête sont classés séquentiellement » et « Le document contient un repère principal » réussis.

## Vérification après correction

```bash
npx lighthouse https://exemple.fr/ --only-categories=accessibility --quiet --output=json --output-path=/tmp/a11y.json --locale=fr
python3 -c "import json; a=json.load(open('/tmp/a11y.json'))['audits']; [print(k, a[k]['score']) for k in ('heading-order','empty-heading','landmark-one-main') if k in a]"
```

## Pièges et retour arrière

- Un composant utilisé à plusieurs niveaux selon la page a besoin de la propriété `niveau` ; sinon il corrigera une page et cassera une autre.
- Ne supprimez pas un titre visuel important pour « corriger » l'ordre : changez son niveau.
- Retour arrière : restaurer le niveau précédent (Git) ; aucun impact sur les données.

## Pour aller plus loin

- WCAG 1.3.1 (information et relations) et 2.4.6 (titres et étiquettes).
- W3C WAI, tutoriel « Titres ».
- Astro, balises dynamiques : `const Titre = ...`.
- RGAA, thématique Structuration de l'information.
