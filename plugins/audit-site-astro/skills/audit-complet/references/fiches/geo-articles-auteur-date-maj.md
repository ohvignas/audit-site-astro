---
id: geo-articles-auteur-date-maj
titre: Articles sans auteur identifiable ou sans date de mise à jour
domaine: GEO / IA
severite_type: moyenne
effort: M
declencheurs:
  - "geo:Articles sans auteur identifiable"
  - "geo:Articles sans date de mise à jour"
versions_astro: ">=5.0"
sources:
  - https://developers.google.com/search/docs/appearance/structured-data/article
  - https://developers.google.com/search/docs/fundamentals/creating-helpful-content
  - https://docs.astro.build/en/guides/content-collections/
  - https://schema.org/Person
---

# Articles sans auteur identifiable ou sans date de mise à jour

> **En une phrase** : des articles ne disent pas qui les a écrits ni quand ils ont été mis à jour pour la dernière fois ; les moteurs et les IA jugent alors leur fiabilité et leur fraîcheur plus difficilement.

## Pourquoi c'est important

Les critères de qualité de Google (E-E-A-T : expérience, expertise, autorité, fiabilité) invitent à indiquer clairement qui a créé le contenu et à le dater. Pour les IA qui citent des pages, un auteur nommé, relié à une page de profil et à des liens externes (LinkedIn), est un signal de confiance ; une date de mise à jour récente évite qu'un contenu soit écarté comme périmé sur les sujets qui évoluent (prix, réglementation, outils). L'outil ne contrôle que les pages dont le JSON-LD déclare un type Article, BlogPosting ou NewsArticle (un article sans ce balisage n'est pas vu, ce qui est déjà un manque) : il y cherche un auteur (lien `rel="author"`, meta `author` ou `author` dans le JSON-LD) et une date de modification (`article:modified_time` ou `dateModified`). Une date de mise à jour n'a de valeur que si le contenu a **réellement** été revu : ne pas la modifier artificiellement.

## Comment le constater soi-même

```bash
curl -s https://SITE/blog/EXEMPLE/ | grep -oiE 'rel="author"|name="author"[^>]*|article:modified_time[^>]*|"dateModified"[^,}]*|"author"[^}]*}' | head
```

Présent (problème) : aucune ligne pour l'auteur ou pour la date. Corrigé : un auteur nommé, `dateModified` au format ISO 8601 (`2026-09-30T10:00:00+02:00`) et une date visible sur la page.

## Correction

1. Créer une branche Git. Ajouter les champs au schéma de la collection d'articles (`src/content.config.ts`) :

```ts
// src/content.config.ts
import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod'; // Astro 6+ ; sur Astro 5 : import { defineCollection, z } from 'astro:content'

const blog = defineCollection({
  loader: glob({ pattern: '**/*.{md,mdx}', base: './src/content/blog' }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    pubDate: z.coerce.date(),
    updatedDate: z.coerce.date().optional(),
    auteur: z.string(),           // clé vers la fiche auteur
  }),
});

export const collections = { blog };
```

2. Créer les fiches auteur (une par personne réelle) : `src/data/auteurs.ts`.

```ts
// src/data/auteurs.ts
export const AUTEURS: Record<string, { nom: string; poste: string; url: string; sameAs: string[] }> = {
  'marie-dupont': {
    nom: 'Marie Dupont',
    poste: 'Consultante SEO',
    url: '/equipe/marie-dupont/',
    sameAs: ['https://www.linkedin.com/in/exemple'],
  },
};
```

3. Dans le gabarit d'article, afficher l'auteur (lien vers sa page) et les dates dans une balise `<time>`, et alimenter le JSON-LD (voir le bloc `BlogPosting` de `geo-jsonld-invalide-champs-manquants`) :

```astro
---
// src/pages/blog/[...slug].astro (extrait)
import { AUTEURS } from '../../data/auteurs';
const { entry } = Astro.props; // entrée de collection
const auteur = AUTEURS[entry.data.auteur];
const maj = entry.data.updatedDate ?? entry.data.pubDate;
---
<meta name="author" content={auteur.nom} />
<meta property="article:modified_time" content={maj.toISOString()} />
<p>
  Par <a rel="author" href={auteur.url}>{auteur.nom}</a>,
  publié le <time datetime={entry.data.pubDate.toISOString()}>{entry.data.pubDate.toLocaleDateString('fr-FR')}</time>
  {entry.data.updatedDate && <>, mis à jour le <time datetime={entry.data.updatedDate.toISOString()}>{entry.data.updatedDate.toLocaleDateString('fr-FR')}</time></>}
</p>
```

4. Créer la page auteur `/equipe/<slug>/` : photo, poste, parcours, liens externes (LinkedIn), articles écrits ; y ajouter un bloc `Person` (`name`, `jobTitle`, `sameAs`, `url`).
5. Renseigner `auteur:` (et `updatedDate:` quand l'article est réellement révisé) dans le frontmatter de **chaque** article existant. Les articles anonymes (« Rédaction ») sont à éviter : rattacher à la personne responsable.
6. Sur les articles qui contiennent des chiffres, prix ou règles : ajouter une revue périodique planifiée et modifier `updatedDate` uniquement après relecture.

## Critères d'acceptation

- [ ] Tous les articles affichent un auteur nommé, avec lien vers une page de profil
- [ ] `dateModified` (JSON-LD) et `article:modified_time` sont présents et exacts
- [ ] Date de publication et de mise à jour visibles sur la page, dans une balise `<time datetime>`
- [ ] Aucune régression : build OK, articles existants tous compilés (le champ `auteur` requis peut casser le build si un article n'en a pas)

## Vérification après correction

```bash
curl -s https://SITE/blog/EXEMPLE/ | grep -oiE 'rel="author"|"dateModified"[^,}]*|article:modified_time[^>]*'
python3 scripts/geo_check.py https://SITE/ --out /tmp/verif/geo --sample 12
grep -iE 'sans auteur|sans date' /tmp/verif/geo/geo-summary.md
```

## Pièges et retour arrière

- Le schéma Zod avec `auteur` obligatoire fait échouer `astro build` pour les anciens articles sans ce champ : d'abord les remplir, ou mettre `auteur` en `.optional()` le temps de la migration.
- Ne jamais inventer un auteur ni un profil : c'est trompeur et contraire aux règles de Google.
- Ne pas mettre `dateModified` = date du jour à chaque build : faux signal de fraîcheur.
- Retour arrière : Git ; le retrait du champ du schéma ne casse rien.

## Pour aller plus loin

- https://developers.google.com/search/docs/appearance/structured-data/article : `author`, `datePublished`, `dateModified`.
- https://developers.google.com/search/docs/fundamentals/creating-helpful-content : contenu utile et E-E-A-T (qui, comment, pourquoi).
- https://docs.astro.build/en/guides/content-collections/ : schéma de collection.
- https://schema.org/Person : propriétés d'une personne.
