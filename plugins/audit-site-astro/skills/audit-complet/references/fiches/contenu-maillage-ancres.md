---
id: contenu-maillage-ancres
titre: Liens internes pauvres ou ancres non descriptives
domaine: Contenu
severite_type: moyenne
effort: M
declencheurs:
  - "lighthouse:link-text|n'ont pas de texte (descriptif|explicite)"
sources:
  - https://developers.google.com/search/docs/crawling-indexing/links-crawlable
  - https://developer.chrome.com/docs/lighthouse/seo/link-text
  - https://docs.astro.build/en/guides/content-collections/#defining-collection-references
---

# Liens internes pauvres ou ancres non descriptives

> **En une phrase** : les liens entre pages sont rares ou s'appellent « cliquez ici » et « en savoir plus », donc Google comprend mal quelle page traite de quoi et les visiteurs ne trouvent pas la suite.

## Pourquoi c'est important

Google découvre les pages et comprend leur sujet en suivant les liens, et le texte du lien (l'ancre) sert d'indice sur la page cible. Google recommande des ancres descriptives, concises et pertinentes. Lighthouse échoue l'audit « link-text » quand des liens ont un texte générique (« cliquez ici », « en savoir plus », « lire la suite »). Un article qui ne renvoie pas vers la page formation ou service qu'il alimente laisse cette page sans soutien : c'est le maillage interne, un des leviers les plus rentables du SEO de contenu. Les données du crawl (`data/crawl/pages.json`, champs `inlinks` et `inlink_anchors`) donnent, pour chaque page, le nombre de liens entrants et ses dix ancres les plus fréquentes.

## Comment le constater soi-même

```bash
# ancres génériques dans le code
grep -rnE ">\s*(cliquez ici|en savoir plus|lire la suite|voir plus|ici|plus d'infos)\s*<" src | head -30
# pages business les moins liées (crawl)
python3 - <<'PY'
import json
d = json.load(open("data/crawl/pages.json"))
for p in sorted(d["pages"], key=lambda p: p.get("inlinks", 0))[:15]:
    print(p.get("inlinks", 0), p["url"], p.get("inlink_anchors", [])[:3])
PY
```

Présent : ancres génériques, pages business avec 0 à 2 liens entrants, ancres entrantes du type « en savoir plus » seulement.

## Correction

1. **Cartographier** (à partir de `pages.json`) : pages business prioritaires (formations, services, contact), leurs liens entrants actuels, et les articles ou pages sœurs qui devraient pointer vers elles. Chaque page business devrait recevoir au moins 5 liens contextuels depuis des pages de la même thématique.
2. **Écrire des ancres descriptives** : elles décrivent la page cible en 2 à 6 mots, naturellement dans la phrase, sans répéter la même ancre exacte partout ni bourrer de mots-clés.

| Mauvais | Bon |
|---|---|
| `Pour en savoir plus, cliquez ici.` | `Découvrez le programme de la formation Excel avancé.` |
| `Lire la suite` | `Lire l'article : devenir développeur web` |
| `Voir` | `Voir les dates des sessions à Lyon` |
| `https://exemple.fr/formations/excel/` (URL nue) | `formation Excel avancé` |

3. **Cartes d'articles et boutons « lire la suite »** : le composant qui les génère répète le même texte partout. Garder un texte visible utile et donner un nom complet au lecteur d'écran :

```astro
---
// src/components/CarteArticle.astro
const { titre, href, extrait } = Astro.props;
---
<article>
  <h3><a href={href}>{titre}</a></h3>
  <p>{extrait}</p>
  <a href={href} aria-label={`Lire l'article : ${titre}`}>Lire l'article</a>
</article>
```

   Encore mieux : ne mettre qu'un seul lien par carte (le titre) et supprimer le second lien.
4. **Liens réels** : tout lien doit être un `<a href="/chemin/">` avec une URL résolvable ; pas de `<span onclick>` ni de `href="#"` pilotés par JavaScript, que Google ne suit pas (docs « links crawlable »).
5. **Maillage automatique via les données**, pour ne pas dépendre de la mémoire de l'éditeur :
   - Collection Astro : un champ de référence entre contenus (`reference` de `astro:content`).

```ts
// src/content.config.ts (extrait)
import { defineCollection, reference } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';   // Astro 5 : z est exporté par 'astro:content'

const blog = defineCollection({
  loader: glob({ pattern: '**/*.{md,mdx}', base: './src/content/blog' }),
  schema: z.object({
    titre: z.string(),
    formationLiee: reference('formations'),                    // page business alimentée par l'article
    articlesLies: z.array(reference('blog')).max(4).default([]),
  }),
});
export const collections = { blog };
```

   Puis dans le gabarit : `const formation = await getEntry(entry.data.formationLiee);` et `<a href={`/formations/${formation.id}/`}>{formation.data.titre}</a>` dans un encadré « Aller plus loin ».
   - Convex : champ `liensAssocies: v.optional(v.array(v.id("pages")))` dans `convex/schema.ts`, résolu par la requête de la page.
6. **Où placer les liens** : dans le corps du texte, à l'endroit où le sujet est évoqué (3 à 8 liens par page, pas 40), plus un bloc « Formations liées » en fin d'article ; le menu et le pied de page portent les pages majeures. Un lien depuis chaque article vers la page business qu'il soutient est prioritaire.
7. **Pages orphelines et profondes** (sans lien entrant, à plus de 3 clics) : les relier depuis une page de liste ou de catégorie ; le détail est dans la fiche SEO sur les pages orphelines.
8. **Liens sortants** : garder les liens vers des sources fiables (officielles) quand ils étayent une affirmation ; `rel="noopener"` inutile sur les navigateurs modernes pour `target="_blank"`, mais éviter `target="_blank"` sur les liens internes.

## Critères d'acceptation

- [ ] Aucun lien avec un texte générique (« cliquez ici », « en savoir plus », « lire la suite » seul, URL nue) ; l'audit Lighthouse `link-text` est réussi.
- [ ] Chaque page business reçoit au moins 5 liens internes contextuels avec des ancres descriptives et variées.
- [ ] Chaque article contient 3 à 8 liens internes dont un vers la page business qu'il soutient.
- [ ] Tous les liens sont de vrais `<a href>` ; aucun lien cassé introduit.
- [ ] Build OK.

## Vérification après correction

```bash
npx astro build
grep -rlE ">\s*(cliquez ici|en savoir plus|lire la suite)\s*<" dist | head       # ne doit rien lister
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl
python3 - <<'PY'
import json
d = json.load(open("/tmp/verif/crawl/pages.json"))
for p in d["pages"]:
    if "/formations/" in p["url"]:
        print(p.get("inlinks", 0), p["url"], p.get("inlink_anchors", [])[:3])
PY
```

## Pièges et retour arrière

- Ne pas placer la même ancre exacte sur 50 liens : variations naturelles.
- Un `aria-label` remplace le texte visible pour les lecteurs d'écran : il doit contenir le texte visible (« Lire l'article ») pour rester cohérent.
- Ne pas ajouter des liens partout dans les menus pour compenser : un menu à 80 entrées dilue tout.
- Retour arrière : `git revert` ; ajouter ou retirer un lien n'a pas d'effet secondaire technique.

## Pour aller plus loin

- https://developers.google.com/search/docs/crawling-indexing/links-crawlable : liens explorables et bonnes pratiques d'ancres.
- https://developer.chrome.com/docs/lighthouse/seo/link-text : audit Lighthouse sur le texte des liens.
- https://docs.astro.build/en/guides/content-collections/#defining-collection-references : références entre collections.
