---
id: contenu-meta-description
titre: Meta description absente, trop courte ou trop longue
domaine: Contenu
severite_type: moyenne
effort: M
declencheurs:
  - "crawl:desc_missing"
  - "crawl:desc_short"
  - "crawl:desc_long"
  - "code:Layout .* : balises absentes du <head> : .*\\bdescription\\b"
  - "lighthouse:meta-description|méta-description"
sources:
  - https://developers.google.com/search/docs/appearance/snippet
  - https://docs.astro.build/en/guides/content-collections/
  - https://docs.convex.dev/database/schemas
  - https://docs.convex.dev/database/reading-data/indexes/
---

# Meta description absente, trop courte ou trop longue

> **En une phrase** : la page n'a pas de résumé écrit pour Google (ou un résumé bâclé), donc l'extrait affiché est pris au hasard dans le texte et donne peu envie de cliquer.

## Pourquoi c'est important

La meta description n'est pas un critère de classement, mais c'est le texte qui vend le clic sous le titre. Google indique qu'il utilise surtout le contenu de la page pour fabriquer l'extrait, et la meta description « parfois », quand elle décrit mieux la page. Il n'y a pas de limite officielle de longueur : l'extrait est tronqué selon la largeur de l'écran. Les seuils de l'outil (moins de 70 caractères = trop court, plus de 160 = trop long) sont des repères pratiques : 120 à 155 caractères tiennent bien sur mobile et ordinateur. Les pages business (formations, services, contact) sont les premières à soigner ; pour les milliers de pages générées, une description composée depuis les données vaut mieux que rien.

## Comment le constater soi-même

```bash
curl -s https://SITE/formations/excel/ | grep -io '<meta name="description"[^>]*>'
curl -s https://SITE/formations/excel/ | grep -io '<meta name="description" content="[^"]*"' | sed 's/.*content="//;s/"$//' | awk '{ print length($0) " : " $0 }'
grep -rn 'name="description"' src | head
```

Présent : aucune ligne, `content=""`, ou une longueur < 70 ou > 160. Corrigé : une description unique de 120 à 155 caractères par page indexable.

## Correction

1. **Localiser la source.** La balise est écrite dans le `<head>` du layout (`src/layouts/BaseLayout.astro`), qui reçoit une prop `description`. Le texte vient (a) de la page `.astro` appelante, (b) du frontmatter d'une entrée de collection (`src/content/<collection>/*.md`, champ `description` ou `seoDescription`), (c) d'un document Convex (champ `seoDescription`). Ne pas coder de description par défaut identique pour tout le site (c'est le cas `desc_dup`, voir `contenu-meta-description-doublons`).
2. **Layout : prop obligatoire** (le build signale l'oubli via `astro check`) :

```astro
---
// src/layouts/BaseLayout.astro
interface Props { title: string; description: string }
const { title, description } = Astro.props;
---
<head>
  <title>{title}</title>
  <meta name="description" content={description} />
</head>
```

3. **Schéma de collection : longueur contrôlée** dans `src/content.config.ts` (Astro 6 et 7 : `z` vient de `astro/zod` ; Astro 5 : `import { z } from 'astro:content'`) :

```ts
import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const formations = defineCollection({
  loader: glob({ pattern: '**/*.{md,mdx}', base: './src/content/formations' }),
  schema: z.object({
    titre: z.string(),
    seoTitle: z.string().min(25).max(60).optional(),
    seoDescription: z.string().min(70).max(155).optional(),
  }),
});
export const collections = { formations };
```

   Un build échoue alors si une description est hors limites : c'est voulu.
4. **Écrire la description** : promesse concrète + preuve ou détail chiffré + appel à l'action, en une ou deux phrases, à l'indicatif, sans mot-clé répété ni guillemets doubles (`"` casse l'attribut si le texte est injecté sans échappement ; Astro échappe `{description}`, mais un frontmatter YAML avec `:` doit être entre guillemets). Ne rien inventer : durée, prix, certification et financement viennent de la page ou du propriétaire.

| Type de page | Description proposée (longueur) |
|---|---|
| Formation | `Excel avancé en 3 jours : tableaux croisés, macros et Power Query. Sessions à Lyon ou à distance, éligible CPF. Voir le programme et le tarif.` (142) |
| Service | `Site vitrine sur mesure à Nantes : cadrage, design, développement et mise en ligne en 6 semaines. Devis gratuit sous 48 h, sans engagement.` (139) |
| Catégorie | `Comparez les formations Excel : niveau, durée et prix. Trouvez la session qui correspond à votre poste et faites votre demande en ligne.` (136) |

5. **Convex (CMS)** : ajouter les champs SEO dans `convex/schema.ts` (optionnels : les documents existants restent valides), une requête indexée, et une mutation protégée pour éditer.

```ts
// convex/schema.ts
import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  pages: defineTable({
    slug: v.string(),
    titre: v.string(),
    contenu: v.string(),
    seoTitle: v.optional(v.string()),
    seoDescription: v.optional(v.string()),
  }).index("by_slug", ["slug"]),
});
```

```ts
// convex/pages.ts
import { query, mutation } from "./_generated/server";
import { v } from "convex/values";

export const getBySlug = query({
  args: { slug: v.string() },
  handler: async (ctx, { slug }) =>
    ctx.db.query("pages").withIndex("by_slug", (q) => q.eq("slug", slug)).unique(),
});

export const setSeo = mutation({
  args: { id: v.id("pages"), seoTitle: v.string(), seoDescription: v.string() },
  handler: async (ctx, { id, seoTitle, seoDescription }) => {
    const identity = await ctx.auth.getUserIdentity();
    if (identity === null) throw new Error("Non authentifié");
    if (seoDescription.length < 70 || seoDescription.length > 155) throw new Error("Description : 70 à 155 caractères");
    await ctx.db.patch(id, { seoTitle, seoDescription });
  },
});
```

   Côté Astro (rendu à la demande ou au build) : `const client = new ConvexHttpClient(import.meta.env.PUBLIC_CONVEX_URL); const page = await client.query(api.pages.getBySlug, { slug });` (`ConvexHttpClient` de `convex/browser`, `api` de `convex/_generated/api`), puis `<BaseLayout title={page.seoTitle ?? page.titre} description={page.seoDescription ?? resume(page.contenu)}>` (`resume` est la fonction de l'étape 6). Pour compléter beaucoup de documents d'un coup, utiliser une `internalMutation`, jamais une mutation publique sans authentification ; la tester avec `npx convex run` sur le déploiement de développement uniquement (`CONVEX_DEPLOYMENT` en `dev:`, pas de `CONVEX_DEPLOY_KEY`). En production, la modification des données est lancée par l'humain, après relecture des descriptions.
6. **Repli automatique** (dernier recours pour les pages générées) : premier paragraphe nettoyé, coupé à 155 caractères sur une limite de mot.

```ts
export function resume(texte: string, max = 155): string {
  const propre = texte.replace(/\s+/g, " ").trim();
  if (propre.length <= max) return propre;
  return propre.slice(0, max - 1).replace(/\s+\S*$/, "") + "…";
}
```

## Critères d'acceptation

- [ ] Chaque page indexable a une `<meta name="description">` non vide, entre 70 et 160 caractères (idéal 120 à 155).
- [ ] Aucune description générique commune à plusieurs pages.
- [ ] Le schéma de collection ou la mutation Convex refuse une description hors limites.
- [ ] Build OK, pages clés en 200.

## Vérification après correction

```bash
npx astro check && npx astro build
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl
python3 -c "import json;d=json.load(open('/tmp/verif/crawl/issues.json'));print({k:v['count'] for k,v in d.items() if k.startswith('desc_')})"
```

Attendu : plus de `desc_missing`, `desc_short`, `desc_long`.

## Pièges et retour arrière

- Google réécrit souvent l'extrait selon la requête : ne pas juger la description sur l'affichage d'une seule recherche.
- Une description longue est coupée, pas fausse : mettre l'essentiel dans les 120 premiers caractères.
- Retour arrière : `git revert` ; côté Convex, remettre le champ à `undefined` avec `ctx.db.patch(id, { seoDescription: undefined })`.

## Pour aller plus loin

- https://developers.google.com/search/docs/appearance/snippet : comment Google construit l'extrait et rôle de la meta description.
- https://docs.astro.build/en/guides/content-collections/ : schéma Zod et validation du frontmatter.
- https://docs.convex.dev/database/schemas : champs optionnels et évolution du schéma ; `withIndex` : https://docs.convex.dev/database/reading-data/indexes/
