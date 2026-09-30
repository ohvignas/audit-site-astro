---
id: contenu-title-doublons
titre: Plusieurs pages ont exactement le même <title>
domaine: Contenu
severite_type: moyenne
effort: M
declencheurs:
  - "crawl:title_dup"
sources:
  - https://developers.google.com/search/docs/appearance/title-link
  - https://docs.astro.build/en/guides/content-collections/
  - https://docs.astro.build/en/reference/routing-reference/
---

# Plusieurs pages ont exactement le même <title>

> **En une phrase** : des pages différentes portent le même titre (souvent celui du site), donc Google ne sait pas les distinguer et l'internaute non plus.

## Pourquoi c'est important

Google recommande d'éviter le texte répété ou générique dans les titres : chaque page doit avoir un texte distinct qui décrit son contenu. Des titres identiques rendent les résultats indiscernables (« Exemple | Exemple » cent fois), font réécrire le titre par Google, et signalent souvent des pages trop proches (voir aussi `contenu-cannibalisation`). Sur un site Astro, la cause est presque toujours la même : un titre par défaut dans le layout qu'une famille de pages (blog paginé, catégories, fiches générées depuis Convex ou une collection) n'écrase pas.

## Comment le constater soi-même

```bash
# titres de toutes les pages du sitemap, avec doublons en tête
curl -s https://SITE/sitemap-0.xml | grep -o '<loc>[^<]*</loc>' | sed 's/<[^>]*>//g' | while read u; do
  printf '%s\t%s\n' "$(curl -s "$u" | grep -o '<title>[^<]*</title>' | sed 's/<[^>]*>//g')" "$u"
done | sort | awk -F'\t' '{c[$1]++; l[$1]=l[$1] " " $2} END {for (t in c) if (c[t]>1) print c[t] " x " t "\n  " l[t]}'
# où le titre par défaut est défini
grep -rn "title" src/layouts/*.astro | head -20
```

Présent : des lignes « N x titre ». Corrigé : aucune sortie. Le détail (titre, URL) se trouve aussi dans `data/crawl/issues.json`, clé `title_dup`.

## Correction

1. **Classer chaque groupe de doublons par cause** (lire les URL de `issues.json`) :
   - **Titre par défaut du layout** (`title = "Exemple"` en valeur par défaut) : la page ne transmet pas sa prop. Supprimer la valeur par défaut, rendre `title` obligatoire (voir `contenu-title`) et transmettre un titre réel.
   - **Pages générées depuis des données** (`src/pages/formations/[slug].astro`, `getStaticPaths`, Convex) : le titre est le même car il ne dépend pas de la donnée. Construire le titre à partir des champs de la page.
   - **Pagination** (`/blog/2/`, `/blog/3/`) : ajouter le numéro de page.
   - **Vraies pages jumelles** (deux pages qui traitent le même sujet) : ne pas maquiller avec deux titres différents ; suivre `contenu-cannibalisation`.
2. **Générer le titre depuis la donnée**, avec un repli lisible :

```astro
---
// src/pages/formations/[slug].astro (Astro 5+, collection « formations », rendu prérendu)
import { getCollection, render } from 'astro:content';
import BaseLayout from '../../layouts/BaseLayout.astro';

export async function getStaticPaths() {
  const formations = await getCollection('formations');
  return formations.map((entry) => ({ params: { slug: entry.id }, props: { entry } }));
}
const { entry } = Astro.props;
const { Content } = await render(entry);
const { titre, duree, ville, seoTitle, seoDescription } = entry.data;
// Titre explicite si fourni, sinon composé à partir des champs qui différencient la page
const title = seoTitle ?? `${titre} : formation de ${duree}${ville ? ` à ${ville}` : ""}`;
---
<BaseLayout title={title} description={seoDescription ?? `Programme, durée et tarif de la formation ${titre}.`}>
  <h1>{titre}</h1>
  <Content />
</BaseLayout>
```

3. **Pagination** (Astro `paginate()`) : le composant reçoit `page.currentPage`.

```astro
---
const { page } = Astro.props;
const title = page.currentPage === 1 ? "Blog formation et emploi" : `Blog formation et emploi, page ${page.currentPage}`;
---
```

4. **Convex** : si le titre vient d'un champ du document (`seoTitle`), lister les documents sans titre propre ou avec un titre en double, puis les compléter. Requête de contrôle (à lancer avec `npx convex run seoAudit:doublonsTitres`) :

```ts
// convex/seoAudit.ts
import { internalQuery } from "./_generated/server";

export const doublonsTitres = internalQuery({
  args: {},
  handler: async (ctx) => {
    const pages = await ctx.db.query("pages").take(1000);
    const parTitre = new Map<string, string[]>();
    for (const p of pages) {
      const t = (p.seoTitle ?? p.titre).trim().toLowerCase();
      parTitre.set(t, [...(parTitre.get(t) ?? []), p.slug]);
    }
    return [...parTitre.entries()].filter(([, slugs]) => slugs.length > 1);
  },
});
```

   (adapter la table `pages` et les noms de champs au schéma réel, lus dans `convex/schema.ts`).
5. **Différencier sans bourrer** : ajouter ce qui distingue vraiment la page (ville, niveau, durée, public, année de session), pas un mot-clé de plus. Ne jamais numéroter artificiellement (« Formation Excel 2 »).

## Critères d'acceptation

- [ ] Aucune paire d'URL indexables avec le même `<title>` (la comparaison de l'outil ignore la casse et les espaces autour).
- [ ] Le titre par défaut du layout ne peut plus être utilisé par oubli (prop obligatoire).
- [ ] Les pages paginées ont un titre distinct par numéro de page.
- [ ] Build OK, pages clés en 200.

## Vérification après correction

```bash
npx astro check && npx astro build
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl
python3 -c "import json;d=json.load(open('/tmp/verif/crawl/issues.json'));print(d.get('title_dup',{}).get('count',0))"   # attendu : 0
```

## Pièges et retour arrière

- Des titres différents sur des pages qui répondent à la même recherche ne règlent pas le fond : voir `contenu-cannibalisation`.
- Une page à ne pas faire indexer (résultats de recherche interne, filtres) se règle par `noindex` ou canonical, pas par un titre unique.
- Pagination : garder le titre de la page 1 stable, il porte le trafic.
- Retour arrière : `git revert` ; aucun effet sur les URL.

## Pour aller plus loin

- https://developers.google.com/search/docs/appearance/title-link : titres distincts et descriptifs pour chaque page.
- https://docs.astro.build/en/guides/content-collections/ : `getCollection`, `render()`, `entry.id`.
- https://docs.astro.build/en/reference/routing-reference/ : `getStaticPaths()` et `paginate()`.
