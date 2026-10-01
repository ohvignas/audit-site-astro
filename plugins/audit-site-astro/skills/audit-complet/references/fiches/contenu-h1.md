---
id: contenu-h1
titre: H1 absent ou multiple
domaine: Contenu
severite_type: haute
effort: S
declencheurs:
  - "crawl:h1_missing"
  - "crawl:h1_multiple"
sources:
  - https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/Heading_Elements
  - https://developers.google.com/search/docs/appearance/title-link
  - https://docs.astro.build/en/basics/astro-components/
---

# H1 absent ou multiple

> **En une phrase** : la page n'a pas de titre principal visible (ou en a plusieurs), ce qui brouille le sujet pour Google, les lecteurs d'écran et les IA.

## Pourquoi c'est important

Le H1 dit en une phrase de quoi parle la page. Sans H1, Google et les assistants IA doivent deviner le sujet, et Google utilise le H1 parmi les sources pour réécrire le titre affiché. Les lecteurs d'écran s'en servent aussi pour se repérer. Plusieurs H1 ne sont pas une erreur bloquante (HTML5 le permet, et Google le tolère), mais MDN recommande un seul H1 par page : c'est le cas courant d'un logo, d'un bandeau et d'un titre de section qui portent tous un `<h1>`. Sur Astro, un H1 manquant vient presque toujours d'un composant `Hero` dont le titre est un `<div>` ou un `<h2>`, d'un titre rendu uniquement en JavaScript (`client:only`), ou d'un layout de blog qui n'affiche pas `entry.data.title`.

## Comment le constater soi-même

```bash
curl -s https://SITE/formations/excel/ | grep -o '<h1[^>]*>.*</h1>' | head
curl -s https://SITE/formations/excel/ | grep -o '<h1' | wc -l     # attendu : 1
grep -rn "<h1" src | head -30
grep -rn "client:only" src | head            # titre rendu seulement côté navigateur ?
```

Présent : 0 ou plus de 1 balise `<h1`. Corrigé : exactement une, dans le HTML servi (pas ajoutée par JavaScript).

## Correction

1. **Décider qui porte le H1.** Une seule source par gabarit : soit la page (`<h1>{titre}</h1>`), soit le layout de contenu (`BlogPostLayout.astro`, `FormationLayout.astro`), jamais les deux. Le logo du header n'est pas un H1 (`<a>` ou `<p>`), sauf sur l'accueil si le H1 est volontairement la marque.
2. **H1 manquant** : ajouter le titre principal dans le gabarit concerné.

```astro
---
// src/layouts/FormationLayout.astro
interface Props { titre: string; accroche?: string }
const { titre, accroche } = Astro.props;
---
<article>
  <header>
    <h1>{titre}</h1>
    {accroche && <p class="accroche">{accroche}</p>}
  </header>
  <slot />
</article>
```

3. **Composant Hero** : rendre le niveau de titre configurable pour qu'un seul H1 existe.

```astro
---
// src/components/Hero.astro
interface Props { titre: string; as?: "h1" | "h2" }
const { titre, as: Tag = "h1" } = Astro.props;
---
<section class="hero"><Tag>{titre}</Tag><slot /></section>
```

   Si une page contient deux Hero, le second reçoit `as="h2"`.
4. **Plusieurs H1** : dans `data/crawl/issues.json` (`h1_multiple`), la liste `h1` donne les textes. Les passer en `h2` ou `p` selon leur rôle, en gardant la classe CSS (le style ne dépend pas du niveau). Dans le Markdown (`src/content/**/*.md`), le titre de la page vient du layout : supprimer le `# Titre` en première ligne du fichier, sinon il double le H1.
5. **Contenu venant de Convex** : le H1 est le champ `titre` du document. Si `titre` est vide, ne pas afficher un H1 vide : repli sur un libellé lisible ou ne pas publier la page.
6. **Écrire le H1** : il décrit la page en langage naturel et ne copie pas mot pour mot le `<title>` (le titre porte aussi la marque et l'accroche de clic). Exemples pour une formation : title `Excel avancé : formation de 3 jours, éligible CPF | Exemple`, H1 `Formation Excel avancé`. Pour un service : title `Création de site vitrine sur mesure à Nantes | Exemple`, H1 `Création de site vitrine à Nantes`.
7. **Hiérarchie** : après le H1, des H2 pour les grandes parties, des H3 sous un H2, sans sauter de niveau pour l'effet visuel.

## Critères d'acceptation

- [ ] Chaque page indexable contient exactement un `<h1>`, présent dans le HTML initial.
- [ ] Le H1 décrit le sujet de la page et diffère du title sans le contredire.
- [ ] Pas de `# Titre` répété dans le Markdown quand le layout affiche déjà le titre.
- [ ] Hiérarchie H1 > H2 > H3 sans saut de niveau.
- [ ] Build OK, rendu visuel identique.

## Vérification après correction

```bash
npx astro build
for f in $(find dist -name '*.html' | head -50); do printf '%s %s\n' "$(grep -o '<h1' "$f" | wc -l | tr -d ' ')" "$f"; done | grep -v '^1 '    # ne doit rien lister (hors pages de redirection)
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl
python3 -c "import json;d=json.load(open('/tmp/verif/crawl/issues.json'));print({k:v['count'] for k,v in d.items() if k.startswith('h1_')})"
```

## Pièges et retour arrière

- Changer `h2` en `h1` sans revoir le CSS peut modifier la taille du texte si les styles ciblent la balise : cibler une classe.
- Une page de redirection ou une 404 peut légitimement n'avoir pas de H1.
- Un H1 invisible (`display:none`) uniquement pour Google est à éviter : préférer un titre visible, ou `sr-only` si le design l'exige.
- Retour arrière : `git revert` ; seules des balises changent.

## Pour aller plus loin

- https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/Heading_Elements : niveaux de titres et recommandation d'un seul H1.
- https://developers.google.com/search/docs/appearance/title-link : le H1 fait partie des sources du titre affiché.
- https://docs.astro.build/en/basics/astro-components/ : props et balises dynamiques dans un composant Astro.
