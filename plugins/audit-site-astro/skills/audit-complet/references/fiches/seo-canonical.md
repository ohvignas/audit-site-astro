---
id: seo-canonical
titre: Balise canonical absente, multiple, mal construite ou vers une mauvaise cible
domaine: SEO technique
severite_type: haute
effort: S
declencheurs:
  - "crawl:canonical_missing"
  - "crawl:canonical_multiple"
  - "crawl:canonical_other"
  - "crawl:canonical_bad_target"
  - "code:canonical construite depuis Astro\\.url\\.href"
  - "lighthouse:rel=canonical|canonical"
sources:
  - https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls
  - https://developers.google.com/search/docs/crawling-indexing/special-tags
  - https://docs.astro.build/en/reference/api-reference/
---

# Balise canonical absente, multiple, mal construite ou vers une mauvaise cible

> **En une phrase** : Google ne reçoit pas une seule adresse de référence claire par page, et peut indexer la mauvaise variante (http, avec paramètres, avec/sans slash).

## Pourquoi c'est important

La balise `rel="canonical"` indique à Google l'URL à conserver quand une même page est accessible par plusieurs adresses (`?utm_source=`, `http://`, `/page` et `/page/`). Google la traite comme un signal fort (les redirections sont plus fortes, le sitemap plus faible). Elle doit être dans le `<head>`, en URL absolue, et ne jamais pointer vers une page redirigée, en erreur ou en `noindex`. Deux canonicals différentes sur une même page : Google les ignore et choisit lui-même.

Cause fréquente sous Astro : construire la canonical avec `Astro.url.href`. Cette valeur garde les paramètres de requête (`?utm=...`) et, derrière un proxy mal déclaré, sort en `http://`.

## Comment le constater soi-même

```bash
# canonical(s) d'une page
curl -s https://SITE/page/ | grep -oE '<link[^>]+rel="canonical"[^>]*>'
# la page avec un paramètre doit garder la même canonical propre
curl -s 'https://SITE/page/?utm_source=test' | grep -oE '<link[^>]+rel="canonical"[^>]*>'
# dans le code
grep -rnE "canonical" src/layouts src/components | head
```

Présent : aucune balise, deux balises différentes, canonical avec `?utm_source=test`, ou en `http://`. Corrigé : une seule balise, absolue, en https, identique avec ou sans paramètre.

## Correction

1. Vérifier que `site` est bien défini en https dans `astro.config.mjs` (fiche `seo-astro-site-et-proxy`).
2. Construire la canonical à partir du **chemin** seul, ancré sur `Astro.site`. Le faire **une seule fois**, dans le layout commun (par exemple `src/layouts/BaseLayout.astro`).
3. Supprimer toute autre balise canonical (composant SEO, `<head>` de page, plugin) pour qu'il n'en reste qu'une.
4. Pour une page qui doit pointer vers une autre (contenu dupliqué volontaire), passer la canonical en prop et vérifier que la cible répond 200, est indexable et non redirigée.

```astro
---
// src/layouts/BaseLayout.astro
interface Props {
  title: string;
  description: string;
  canonical?: string; // chemin ou URL absolue, si différent de la page courante
}
const { title, description, canonical } = Astro.props;
// Chemin propre : pas de paramètres de requête, hôte de production
const canonicalUrl = new URL(canonical ?? Astro.url.pathname, Astro.site).href;
---
<html lang="fr">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <meta name="description" content={description} />
    <link rel="canonical" href={canonicalUrl} />
    <meta property="og:url" content={canonicalUrl} />
  </head>
  <body><slot /></body>
</html>
```

5. Aligner le slash final de la canonical avec `trailingSlash` (fiche `seo-trailing-slash`) : `new URL(Astro.url.pathname, Astro.site)` reprend le chemin tel que servi, ce qui est correct si la redirection vers la forme choisie est en place.
6. Pour les pages paginées ou filtrées (`?page=2`, `?tab=`), soit garder la canonical auto-référente propre (page 2 → `/blog/?page=2` si elle est indexable), soit canonicaliser vers la page principale lorsque le paramètre ne change pas le contenu (voir `seo-parametres-urls`).

## Critères d'acceptation

- [ ] Exactement une balise `rel="canonical"` par page HTML, dans le `<head>`
- [ ] URL absolue en `https://`, sur le domaine canonique, sans paramètres UTM
- [ ] Auto-référente pour les pages indexables ; sinon cible en 200, indexable, non redirigée
- [ ] Aucune régression : build OK, `og:url` cohérent

## Vérification après correction

```bash
for p in / /contact/ '/contact/?utm_source=x'; do
  echo "$p -> $(curl -s "https://SITE$p" | grep -oE '<link[^>]+rel="canonical"[^>]*>' | wc -l) balise(s)"
  curl -s "https://SITE$p" | grep -oE 'rel="canonical"[^>]*href="[^"]+"'
done
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif   # canonical_* doivent disparaître
```

Relancer Lighthouse : l'audit « Le document n'a pas d'attribut `rel=canonical` valide » ne doit plus échouer.

## Pièges et retour arrière

- `canonical_other` seul (canonical vers une autre URL) n'est un défaut que si ce n'est pas voulu ; vérifier page par page.
- Ne jamais mettre un `noindex` sur une page **et** une canonical vers une autre : signaux contradictoires.
- N'utiliser ni robots.txt ni `noindex` pour « canonicaliser ».
- Retour arrière : `git revert` du layout.

## Pour aller plus loin

- https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls : méthodes de canonicalisation et leur force relative.
- https://developers.google.com/search/docs/crawling-indexing/special-tags : balises prises en charge par Google.
- https://docs.astro.build/en/reference/api-reference/ : `Astro.url`, `Astro.site`.
