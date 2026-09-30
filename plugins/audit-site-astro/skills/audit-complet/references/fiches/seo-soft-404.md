---
id: seo-soft-404
titre: Soft 404 — une URL inexistante répond 200 (routes dynamiques SSR)
domaine: SEO technique
severite_type: haute
effort: S
declencheurs:
  - "code:Routes SSR dynamiques sans gestion explicite du 404"
  - "http:404-page-inexistante-audit \\| 200"
sources:
  - https://docs.astro.build/en/guides/on-demand-rendering/
  - https://docs.astro.build/en/guides/routing/
  - https://developers.google.com/search/docs/crawling-indexing/http-network-errors
---

# Soft 404 — une URL inexistante répond 200 (routes dynamiques SSR)

> **En une phrase** : quand l'adresse demandée n'existe pas, le site affiche une page « introuvable » (ou une page vide) mais répond avec le code 200 au lieu de 404.

## Pourquoi c'est important

Pour Google, le code HTTP décide de tout : 200 = « cette page existe, indexez-la ». Une infinité d'URL inventées (`/blog/nimporte-quoi`) répondent alors 200, Google les explore, les classe comme « soft 404 » dans la Search Console, gaspille du budget de crawl et peut en indexer des pages vides. Le défaut est typique d'une route dynamique en rendu à la demande (`src/pages/blog/[slug].astro` avec `prerender = false`) qui va chercher une donnée (Convex, base, API) et affiche un message quand elle est absente, sans changer le statut.

## Comment le constater soi-même

```bash
# URL inexistante à la racine : doit donner 404
curl -s -o /dev/null -w '%{http_code}\n' https://SITE/404-page-inexistante-audit
# Une URL inexistante sous CHAQUE route dynamique
for p in /blog/zz-audit /formations/zz-audit /outils/zz-audit; do
  curl -s -o /dev/null -w "%{http_code} $p\n" https://SITE$p
done
# Routes dynamiques du projet
find src/pages -name '*\[*'
```

Présent : un `200` sur une URL inventée. Corrigé : `404` partout.

## Correction

1. Lister les routes dynamiques signalées (`find src/pages -name '*\[*'`). Une route avec `getStaticPaths()` prérendue n'est pas concernée : l'hébergeur renvoie 404 pour un chemin inconnu.
2. Dans chaque route à la demande (`export const prerender = false` ou `output: 'server'`), tester la donnée **avant** tout rendu et sortir en 404.
3. Deux formes valables (documentées). Forme 1 : afficher la page `404.astro` :

```astro
---
// src/pages/blog/[slug].astro
export const prerender = false;
import BaseLayout from '../../layouts/BaseLayout.astro';
import { getPost } from '../../lib/posts';

const { slug } = Astro.params;
const post = await getPost(slug);
if (!post) {
  return Astro.rewrite('/404'); // la page 404.astro est servie avec le statut 404
}
---
<BaseLayout title={post.title} description={post.summary}>
  <h1>{post.title}</h1>
  <article set:html={post.html} />
</BaseLayout>
```

Forme 2 : garder le rendu de la page, mais forcer le statut (fonctionne uniquement au niveau de la page, pas dans un composant) :

```astro
---
export const prerender = false;
const post = await getPost(Astro.params.slug);
if (!post) {
  Astro.response.status = 404;
  Astro.response.statusText = 'Not found';
}
---
{post ? <article>{post.title}</article> : <p>Cette page n'existe pas. <a href="/">Retour à l'accueil</a></p>}
```

Forme 3 (API ou endpoint) : `return new Response(null, { status: 404, statusText: 'Not found' });`

4. Vérifier que `src/pages/404.astro` existe (fiche `seo-page-404-manquante`).
5. Si la donnée vient de Convex : distinguer « absente » (404) de « erreur réseau » (500/503, voir `seo-erreurs-serveur-5xx`), pour ne pas transformer une panne en 404.
6. Derrière un proxy, ne pas laisser `proxy_intercept_errors` ou une règle `try_files` remplacer les 404 de Node par la page d'accueil.

## Critères d'acceptation

- [ ] Toute URL inexistante (racine et sous chaque route dynamique) répond 404, y compris son corps HTML (page 404 lisible)
- [ ] Les pages existantes répondent toujours 200
- [ ] Plus de « soft 404 » dans la Search Console après quelques semaines
- [ ] Aucune régression : build OK

## Vérification après correction

```bash
for p in /404-page-inexistante-audit /blog/zz-audit /formations/zz-audit; do
  curl -s -o /dev/null -w "%{http_code} $p\n" https://SITE$p
done                                                      # attendu : 404 partout
bash scripts/http_checks.sh https://SITE/ /tmp/verif      # section 6 : dernière ligne en 404
python3 scripts/astro_scan.py . --out /tmp/verif-code     # le constat « Routes SSR dynamiques sans gestion explicite du 404 » disparaît
```

## Pièges et retour arrière

- Si le statut reste 200 après `Astro.rewrite('/404')`, utiliser la forme 2 : `curl -I` fait foi.
- Fixer le statut dans le frontmatter (entre les `---`) de la **page**, pas dans un composant enfant ni dans le gabarit HTML : la réponse est envoyée en flux dès que le rendu commence.
- Le détecteur de l'outil cherche `status = 404`, `Astro.rewrite('/404')` ou `notFound` : si la gestion existe sous une autre forme (fonction utilitaire), c'est un faux positif à confirmer avec `curl`.
- Retour arrière : `git revert` du fichier de route.

## Pour aller plus loin

- https://docs.astro.build/en/guides/on-demand-rendering/ : `Astro.response.status`, `new Response(null, { status: 404 })`.
- https://docs.astro.build/en/guides/routing/ : `Astro.rewrite('/404')` et page 404 personnalisée.
- https://developers.google.com/search/docs/crawling-indexing/http-network-errors : codes de statut et indexation.
