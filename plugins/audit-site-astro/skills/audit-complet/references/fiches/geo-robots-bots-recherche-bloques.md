---
id: geo-robots-bots-recherche-bloques
titre: robots.txt bloque des robots IA de recherche ou de réponse (ChatGPT Search, Perplexity, Claude, Bing, Google…)
domaine: GEO / IA
severite_type: haute
effort: S
declencheurs:
  - "geo:robots\\.txt bloque (OAI-SearchBot|ChatGPT-User|Claude-SearchBot|Claude-User|PerplexityBot|Perplexity-User|Googlebot|Bingbot|Applebot|Amazonbot|DuckAssistBot|MistralAI-User) \\("
sources:
  - https://developers.openai.com/api/docs/bots
  - https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler
  - https://docs.perplexity.ai/guides/bots
  - https://developers.google.com/search/docs/crawling-indexing/robots/intro
  - https://docs.astro.build/en/guides/endpoints/
---

# robots.txt bloque des robots IA de recherche ou de réponse

> **En une phrase** : le fichier `robots.txt` interdit l'accès à la page d'accueil à au moins un robot qui alimente une recherche ou une réponse IA (OAI-SearchBot, PerplexityBot, Claude-SearchBot, Bingbot, Googlebot…) : le site ne peut alors pas être cité par cet assistant.

## Pourquoi c'est important

Les assistants IA ne citent que des pages qu'ils ont pu récupérer. OAI-SearchBot alimente ChatGPT Search, PerplexityBot l'index de Perplexity, Claude-SearchBot celui d'Anthropic, Bingbot celui de Bing (base de Copilot et d'autres assistants), Googlebot celui de Google (AI Overviews, AI Mode). Si l'un d'eux est refusé, le site disparaît des réponses de l'assistant correspondant, quelle que soit la qualité du contenu. Ces robots sont à distinguer des robots d'**entraînement** (GPTBot, ClaudeBot…), dont le blocage est un choix business sans effet sur les citations en direct (voir la fiche `geo-robots-bots-entrainement`). Cause fréquente : une liste « bloquer toutes les IA » copiée depuis un tutoriel, un `Disallow: /` de préproduction oublié, ou un robots.txt géré par un CDN.

## Comment le constater soi-même

```bash
# Contenu réel du fichier
curl -s https://SITE/robots.txt

# Groupes qui visent des robots IA ou tout le monde
curl -s https://SITE/robots.txt | grep -inE 'user-agent|disallow|allow' | head -60
```

Problème présent : un groupe `User-agent: OAI-SearchBot` (ou `PerplexityBot`, `Claude-SearchBot`, `Bingbot`, `Googlebot`, `*`) suivi de `Disallow: /`. Attention : un robot qui a un groupe **dédié** ignore le groupe `*`. Corrigé : ces robots n'ont aucun `Disallow` couvrant `/`, ou un `Allow: /` explicite.

Si le site est derrière Cloudflare, le fichier servi peut différer du fichier du dépôt (robots.txt géré, voir `geo-content-signal`). Toujours tester l'URL publique, pas seulement `public/robots.txt`.

## Correction

1. **Sauvegarde** : travailler sur une branche Git (`git switch -c fix/robots-ia`).
2. Trouver la source du fichier servi, dans cet ordre : `src/pages/robots.txt.ts` (ou `.js`), `public/robots.txt`, règle du serveur (nginx `location = /robots.txt`, Caddy `respond`), réglage du CDN. Ne garder qu'une seule source : avec une route `src/pages/robots.txt.ts` **et** un `public/robots.txt`, on ne sait pas lequel sera servi ; supprimer l'un des deux.
3. Retirer les groupes qui refusent les robots de recherche ou à la demande de la liste ci-dessous. **Ne pas trancher à la place du propriétaire** pour les robots d'entraînement (autre fiche).

   Robots à laisser passer pour être cité : `OAI-SearchBot`, `ChatGPT-User`, `PerplexityBot`, `Perplexity-User`, `Claude-SearchBot`, `Claude-User`, `Googlebot`, `Bingbot`, `Applebot`, `DuckAssistBot`, `MistralAI-User`, `Amazonbot`.
4. Fichier recommandé, généré depuis `site` pour que l'URL du sitemap soit toujours absolue et en https.

```ts
// src/pages/robots.txt.ts
import type { APIRoute } from 'astro';

export const GET: APIRoute = ({ site }) => {
  const sitemap = new URL('/sitemap-index.xml', site ?? 'https://exemple.fr').href;
  const body = [
    'User-agent: *',
    'Allow: /',
    'Disallow: /api/',
    '',
    `Sitemap: ${sitemap}`,
    '',
  ].join('\n');
  return new Response(body, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
};
```

   Variante statique équivalente (`public/robots.txt`), avec l'URL absolue écrite en dur :

```text
User-agent: *
Allow: /
Disallow: /api/

Sitemap: https://exemple.fr/sitemap-index.xml
```

   Adapter `Disallow: /api/` aux chemins réellement privés du site (le retirer s'il n'y en a pas). `site` doit être défini dans `astro.config.mjs` (`site: 'https://exemple.fr'`). Le nom `sitemap-index.xml` est celui produit par `@astrojs/sitemap` ; adapter s'il y a un sitemap personnalisé. En rendu à la demande (adapter Node), ajouter `export const prerender = true;` pour que le fichier soit figé au build.
5. Si vous voulez bloquer certains robots d'entraînement, ajouter leurs groupes **séparément** (voir la fiche dédiée) sans toucher aux robots de recherche.
6. Redéployer, puis contrôler le fichier public (et non le dépôt).

## Critères d'acceptation

- [ ] `curl -s https://SITE/robots.txt` ne contient aucun `Disallow: /` (ni `Disallow: /` sous un groupe `*`) applicable à `OAI-SearchBot`, `ChatGPT-User`, `PerplexityBot`, `Perplexity-User`, `Claude-SearchBot`, `Claude-User`, `Googlebot`, `Bingbot`
- [ ] La ligne `Sitemap:` est une URL absolue en https
- [ ] Le tableau « Accès des robots IA » de `geo-summary.md` n'affiche plus de robot de recherche « bloqué »
- [ ] Aucune régression : les pages privées (admin, API) restent exclues, build OK

## Vérification après correction

```bash
curl -s https://SITE/robots.txt | head -30
python3 scripts/geo_check.py https://SITE/ --out /tmp/verif/geo --sample 3
grep -A30 'Accès des robots IA' /tmp/verif/geo/geo-summary.md
```

Attendu : plus aucune ligne « robots.txt bloque … » dans la section « Signaux » (mêmes commandes que le constat).

## Pièges et retour arrière

- `robots.txt` interdit de **crawler**, pas d'**indexer** : pour retirer une page d'un index il faut `noindex` (et la page doit rester crawlable pour que la directive soit lue).
- Selon OpenAI et Perplexity, `ChatGPT-User` et `Perplexity-User` (visites déclenchées par un utilisateur) peuvent ne pas respecter robots.txt : l'absence de blocage ici ne garantit donc pas l'accès si un pare-feu les bloque (voir `geo-waf-cdn-bloque-bots-ia`).
- Un cache CDN peut servir l'ancien robots.txt quelques heures : purger si besoin.
- Retour arrière : `git revert` du commit ; le fichier redevient celui d'avant.

## Pour aller plus loin

- https://developers.openai.com/api/docs/bots : rôle de OAI-SearchBot, GPTBot et ChatGPT-User, listes d'IP officielles.
- https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler : ClaudeBot, Claude-User, Claude-SearchBot.
- https://docs.perplexity.ai/guides/bots : PerplexityBot et Perplexity-User.
- https://developers.google.com/search/docs/crawling-indexing/robots/intro : fonctionnement de robots.txt chez Google.
- https://docs.astro.build/en/guides/endpoints/ : fichiers générés par des endpoints Astro.
