---
id: geo-llms-txt
titre: Pas de llms.txt exploitable (absent ou renvoie du HTML)
domaine: GEO / IA
severite_type: basse
effort: S
declencheurs:
  - "geo:Pas de llms\\.txt exploitable"
  - "code:Pas de llms\\.txt \\(faible coût"
sources:
  - https://llmstxt.org/
  - https://developers.google.com/search/docs/appearance/ai-features
  - https://docs.astro.build/en/guides/endpoints/
  - https://docs.astro.build/en/guides/content-collections/
---

# Pas de llms.txt exploitable

> **En une phrase** : le site ne publie pas de fichier `/llms.txt` valide (ou l'URL renvoie une page HTML) ; c'est un pari à faible coût dont l'effet sur les citations n'est pas prouvé.

## Pourquoi c'est important

`llms.txt` est une proposition (llmstxt.org) : un fichier Markdown à la racine qui résume le site et liste ses pages clés, pensé pour être lu par des agents et des outils IA. **Honnêteté** : Google indique qu'aucun fichier ni balisage spécial n'est nécessaire pour apparaître dans AI Overviews et AI Mode, et l'effet de `llms.txt` sur les citations de ChatGPT, Perplexity ou Claude n'est pas démontré. Il peut servir à des agents de code ou des outils qui le consultent volontairement, et coûte peu s'il est **généré** à partir des données du site. À traiter comme un bonus, jamais avant l'accès des robots, le contenu et l'entité. Cas particulier à corriger vite : une URL `/llms.txt` qui répond 200 avec du HTML (page 404 déguisée, fallback SPA) est pire qu'une absence franche.

## Comment le constater soi-même

```bash
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' https://SITE/llms.txt
curl -s https://SITE/llms.txt | head -15
ls public/llms.txt src/pages/llms.txt.* 2>/dev/null
```

Présent (problème) : `404`, ou `200 text/html` avec un `<!doctype html>`. Corrigé : `200 text/plain; charset=utf-8` et un fichier qui commence par `# Nom du site`.

## Correction

1. Créer une branche Git. Le format (llmstxt.org) : un titre `# …` (obligatoire), un résumé en citation `> …`, du texte facultatif, puis des sections `## …` contenant des listes `- [Titre](URL absolue) : description`. Une section `## Optional` regroupe les liens secondaires.
2. **Recommandé** : un endpoint Astro qui génère le fichier depuis les données (jamais périmé). Créer `src/pages/llms.txt.ts` :

```ts
// src/pages/llms.txt.ts
import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';

export const GET: APIRoute = async ({ site }) => {
  const base = site ?? new URL('https://exemple.fr');
  const articles = (await getCollection('blog')).sort(
    (a, b) => b.data.pubDate.valueOf() - a.data.pubDate.valueOf(),
  );
  const lignes = [
    '# Exemple SAS',
    '> Exemple SAS accompagne les PME de la région dans leur transformation numérique (audit, développement, formation).',
    '',
    '## Pages clés',
    `- [Services](${new URL('/services/', base).href}) : offres et tarifs`,
    `- [À propos](${new URL('/a-propos/', base).href}) : équipe, méthode, références`,
    `- [Contact](${new URL('/contact/', base).href}) : joindre l'équipe`,
    '',
    '## Articles',
    ...articles.map(
      (a) => `- [${a.data.title}](${new URL(`/blog/${a.id}/`, base).href}) : ${a.data.description}`,
    ),
    '',
  ];
  return new Response(lignes.join('\n'), {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
```

   Adapter le nom de la collection (`blog`), les champs (`title`, `description`, `pubDate`) et les chemins à ceux du projet (`a.id` est l'identifiant de l'entrée dans les collections à chargeur `glob` d'Astro 5+ ; avant Astro 5 utiliser `a.slug`). Les pages listées doivent exister et répondre 200.
3. **Variante Convex** : si les contenus sont dans Convex, interroger avec le client HTTP (dans le même endpoint) :

```ts
import { ConvexHttpClient } from 'convex/browser';
import { api } from '../../convex/_generated/api';

const convex = new ConvexHttpClient(import.meta.env.PUBLIC_CONVEX_URL);
const services = await convex.query(api.services.liste); // requête Convex existante du projet
```

4. **Variante minimale** (site sans données) : fichier statique `public/llms.txt`, en pensant qu'il se périme : à mettre à jour à chaque nouvelle page importante.
5. En **rendu à la demande** (adapter Node), ajouter `export const prerender = true;` en tête de l'endpoint pour le figer au build, ou mettre l'endpoint en cache.
6. Si `/llms.txt` renvoie du HTML : c'est un fallback serveur (`try_files … /index.html` dans nginx, page 404 personnalisée avec statut 200). Servir un vrai fichier, ou retourner un vrai 404.
7. Facultatif : `llms-full.txt` avec le contenu complet des pages clés en Markdown, seulement si utile.

## Critères d'acceptation

- [ ] `/llms.txt` répond `200` avec `Content-Type: text/plain` (ou `text/markdown`), pas de HTML
- [ ] Première ligne `# …`, un résumé `> …`, au moins une section `## …` de liens
- [ ] Tous les liens sont absolus, en https, et répondent 200
- [ ] Aucune régression : build OK, les autres pages inchangées

## Vérification après correction

```bash
curl -sI https://SITE/llms.txt | grep -iE 'HTTP|content-type'
curl -s https://SITE/llms.txt | grep -oE '\(https?://[^)]+\)' | tr -d '()' | while read u; do printf '%s ' "$(curl -s -o /dev/null -w '%{http_code}' "$u")"; echo "$u"; done
python3 scripts/geo_check.py https://SITE/ --out /tmp/verif/geo --sample 3
```

## Pièges et retour arrière

- Ne pas y mettre d'informations confidentielles ni de pages `noindex`.
- Ne pas présenter ce fichier au client comme un levier de visibilité garanti.
- Retour arrière : supprimer `src/pages/llms.txt.ts` (ou `public/llms.txt`).

## Pour aller plus loin

- https://llmstxt.org/ : spécification du format.
- https://developers.google.com/search/docs/appearance/ai-features : Google précise qu'aucun fichier spécial n'est requis pour ses fonctions IA.
- https://docs.astro.build/en/guides/endpoints/ : endpoints de fichiers dans Astro.
- https://docs.astro.build/en/guides/content-collections/ : collections de contenu et `getCollection`.
