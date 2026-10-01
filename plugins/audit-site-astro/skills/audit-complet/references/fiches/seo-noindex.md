---
id: seo-noindex
titre: Pages en noindex (meta robots ou en-tête X-Robots-Tag) à vérifier
domaine: SEO technique
severite_type: haute
effort: S
declencheurs:
  - "crawl:noindex"
  - "lighthouse:is-crawlable|bloquée pour l.indexation"
sources:
  - https://developers.google.com/search/docs/crawling-indexing/block-indexing
  - https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag
  - https://developer.chrome.com/docs/lighthouse/seo/is-crawlable
---

# Pages en noindex (meta robots ou en-tête X-Robots-Tag) à vérifier

> **En une phrase** : certaines pages demandent à Google de ne pas les indexer ; c'est normal pour l'espace privé, mais catastrophique si une page importante (ou tout le site) l'a par erreur.

## Pourquoi c'est important

Une page en `noindex` disparaît des résultats de Google. C'est l'outil voulu pour les pages de remerciement, l'espace client, les résultats de recherche interne. Mais l'erreur classique est un `noindex` copié de la préproduction vers la production, ou posé par un layout partagé. Lighthouse échoue alors à « La page est bloquée pour l'indexation ». L'outil signale toutes les pages en `noindex` en information : il faut les relire et confirmer chacune.

## Comment le constater soi-même

```bash
# meta robots dans le HTML
curl -s https://SITE/page/ | grep -oiE '<meta[^>]+name="(robots|googlebot)"[^>]*>'
# en-tête HTTP
curl -sI https://SITE/page/ | grep -i '^x-robots-tag'
# dans le code
grep -rniE "noindex" src/ astro.config.* public/ 2>/dev/null | head
# côté proxy
grep -rniE "x-robots-tag" /etc/nginx/ /etc/caddy/ Caddyfile 2>/dev/null
```

La liste des pages concernées est dans `data/crawl/issues.json` (clé `noindex`).

## Correction

1. Pour chaque page listée, décider : **volontaire** (à garder) ou **par erreur** (à corriger).
2. Par erreur : trouver la source. Dans Astro, elle est dans un layout (`<meta name="robots" content="noindex">`), un composant SEO qui reçoit une prop, une variable d'environnement, un en-tête ajouté par le proxy (`X-Robots-Tag`) ou un middleware (`context.response.headers.set('X-Robots-Tag', ...)`).
3. Rendre le `noindex` **explicite et piloté par une prop** dans le layout, jamais global :

```astro
---
// src/layouts/BaseLayout.astro
interface Props {
  title: string;
  description: string;
  noindex?: boolean;
}
const { title, description, noindex = false } = Astro.props;
// Sécurité : n'autoriser noindex sur toutes les pages QUE hors production
const stagingNoindex = import.meta.env.PUBLIC_SITE_ENV === 'staging';
---
<html lang="fr">
  <head>
    <meta charset="utf-8" />
    <title>{title}</title>
    <meta name="description" content={description} />
    {(noindex || stagingNoindex) && <meta name="robots" content="noindex, follow" />}
  </head>
  <body><slot /></body>
</html>
```

```astro
---
// src/pages/merci.astro : page volontairement non indexée
import BaseLayout from '../layouts/BaseLayout.astro';
---
<BaseLayout title="Merci" description="Confirmation d'envoi." noindex>
  <h1>Merci pour votre message</h1>
</BaseLayout>
```

4. Pour des fichiers non HTML (PDF) ou un dossier entier, utiliser l'en-tête `X-Robots-Tag` :

```nginx
location /prive/ { add_header X-Robots-Tag "noindex" always; }
```

5. Ne **pas** bloquer en plus dans robots.txt une page qu'on veut désindexer : Google ne pourrait pas lire le `noindex` (fiche `seo-robots-bloque-crawl`).
6. Retirer du sitemap toute page en `noindex` (fiche `seo-sitemap-coherence`).

## Critères d'acceptation

- [ ] Chaque page en `noindex` est documentée comme volontaire (remerciement, espace privé, recherche interne)
- [ ] Aucune page stratégique (accueil, offres, articles, pages de service) n'est en `noindex`
- [ ] Aucune page en `noindex` dans le sitemap
- [ ] Lighthouse : l'audit `is-crawlable` réussit sur les pages indexables
- [ ] Aucune régression : build OK

## Vérification après correction

```bash
for p in / /contact/ /blog/; do
  echo "$p : $(curl -s https://SITE$p | grep -ciE '<meta[^>]+robots[^>]+noindex') meta, $(curl -sI https://SITE$p | grep -ci '^x-robots-tag: .*noindex') en-tête"
done                                                        # attendu : 0 meta, 0 en-tête
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif   # clé noindex : uniquement les pages voulues
```

Dans la Search Console : rapport « Pages » → motif « Exclue par la balise noindex ».

## Pièges et retour arrière

- Après retrait du `noindex`, Google met plusieurs jours à réindexer ; demander l'indexation de l'URL dans la Search Console.
- Une variable d'environnement de préproduction oubliée en production peut poser un `noindex` global : vérifier la valeur à chaque déploiement.
- Retour arrière : remettre la prop `noindex` ou l'en-tête, puis faire redéployer par l'humain.

## Pour aller plus loin

- https://developers.google.com/search/docs/crawling-indexing/block-indexing : méthodes pour bloquer l'indexation.
- https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag : balise meta robots et `X-Robots-Tag`.
- https://developer.chrome.com/docs/lighthouse/seo/is-crawlable : audit Lighthouse `is-crawlable`.
