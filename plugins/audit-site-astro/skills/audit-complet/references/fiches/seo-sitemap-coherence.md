---
id: seo-sitemap-coherence
titre: Sitemap incohérent avec le site (erreurs, noindex, canonicals, pages manquantes)
domaine: SEO technique
severite_type: haute
effort: M
declencheurs:
  - "crawl:sitemap_non200"
  - "crawl:sitemap_noindex"
  - "crawl:sitemap_canonicalized"
  - "crawl:not_in_sitemap"
sources:
  - https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap
  - https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls
  - https://docs.astro.build/en/guides/integrations-guide/sitemap/
---

# Sitemap incohérent avec le site (erreurs, noindex, canonicals, pages manquantes)

> **En une phrase** : le sitemap contient des pages qui ne devraient pas y être (erreurs, `noindex`, canonical ailleurs) ou omet des pages qui devraient y être.

## Pourquoi c'est important

Le sitemap est lu comme la liste des URL que vous voulez voir indexées. Y mettre une page en erreur, en `noindex` ou dont la canonical pointe ailleurs envoie des signaux contradictoires : Google perd du temps et fait moins confiance au fichier. À l'inverse, une page indexable absente du sitemap (fréquent pour les contenus venus de Convex ou d'une collection oubliée dans l'endpoint) est découverte plus tard, surtout si elle est peu liée. Le sitemap doit être **la liste des URL canoniques, indexables, en 200**.

## Comment le constater soi-même

```bash
curl -s https://SITE/sitemap-0.xml | grep -o '<loc>[^<]*' | sed 's/<loc>//' > /tmp/sitemap-urls.txt
wc -l /tmp/sitemap-urls.txt
# statut + noindex + canonical de chaque URL
while read u; do
  code=$(curl -s -o /tmp/p.html -w '%{http_code}' "$u")
  ni=$(grep -ciE '<meta[^>]+name="robots"[^>]+noindex' /tmp/p.html)
  can=$(grep -oE '<link[^>]+rel="canonical"[^>]+href="[^"]+"' /tmp/p.html | grep -oE 'href="[^"]+"' | head -1)
  echo "$code noindex=$ni $u $can"
done < /tmp/sitemap-urls.txt | awk '$1!=200 || $2!="noindex=0"' | head -30
```

Les lignes affichées sont des URL à retirer du sitemap (ou des pages à corriger). Pour les pages manquantes, comparer avec `data/crawl/pages.csv` (pages indexables absentes du sitemap : clé `not_in_sitemap`).

## Correction

1. Pour chaque URL en 4xx/5xx listée : soit corriger la page, soit la retirer du sitemap (source : collection Convex, contenu supprimé non filtré, page dépubliée).
2. Pour chaque URL en `noindex` : la retirer du sitemap, ou retirer le `noindex` si l'indexation est voulue (voir `seo-noindex`).
3. Pour chaque URL dont la canonical pointe ailleurs : lister l'URL canonique à la place (voir `seo-canonical`).
4. Pour les pages indexables absentes : ajouter leur source de données à la génération du sitemap.
5. Avec `@astrojs/sitemap`, exclure par motif et ajouter les pages hors routes Astro :

```js
// astro.config.mjs
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://exemple.fr',
  integrations: [
    sitemap({
      // Exclure les pages sans valeur SEO (noindex, espace privé, remerciements)
      filter: (page) => !/\/(admin|compte|merci|recherche)(\/|$)/.test(page),
      // Ajouter des URL qui ne sont pas des routes Astro (pages servies ailleurs)
      customPages: ['https://exemple.fr/temoignages/'],
    }),
  ],
});
```

6. Avec un endpoint personnalisé alimenté par Convex ou une collection de contenu : boucler sur **toutes** les collections publiques (blog, formations, pages outils…) et filtrer sur `publié = true`.

```ts
// Extrait : ne lister que le contenu publié
const publies = articles.filter((a) => a.publie && !a.noindex);
```

7. Rebuilder, puis faire redéployer par l'humain ; le sitemap doit refléter l'état réel du site à chaque déploiement.

## Critères d'acceptation

- [ ] 100 % des URL du sitemap répondent 200 sans redirection
- [ ] Aucune URL du sitemap n'est en `noindex` ni canonisée vers une autre URL
- [ ] Toutes les pages indexables du crawl sont dans le sitemap (`not_in_sitemap` = 0), hors pages volontairement exclues
- [ ] Aucune régression : pages clés en 200, build OK

## Vérification après correction

```bash
curl -s https://SITE/sitemap-0.xml | grep -o '<loc>[^<]*' | sed 's/<loc>//' \
  | xargs -n1 -P4 -I{} curl -s -o /dev/null -w '%{http_code}\n' {} | sort | uniq -c   # attendu : une seule ligne, 200
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif   # sitemap_non200, sitemap_noindex, sitemap_canonicalized, not_in_sitemap
```

## Pièges et retour arrière

- Ne pas exclure une page du sitemap pour la « désindexer » : seul `noindex` (ou une redirection) le fait.
- Une page bloquée par robots.txt ne doit pas être dans le sitemap (voir `seo-robots-bloque-crawl`).
- Sur un très gros site, le crawl a une limite de pages : `not_in_sitemap` peut être surévalué si `--max-pages` est atteint.
- Retour arrière : restaurer la version précédente de la configuration ou de l'endpoint avec Git.

## Pour aller plus loin

- https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap : ce que doit contenir un sitemap.
- https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls : canonicals et signaux contradictoires.
- https://docs.astro.build/en/guides/integrations-guide/sitemap/ : `filter` et `customPages`.
