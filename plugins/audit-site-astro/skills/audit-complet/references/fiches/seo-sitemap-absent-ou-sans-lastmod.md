---
id: seo-sitemap-absent-ou-sans-lastmod
titre: Sitemap XML absent ou sans date de modification (lastmod)
domaine: SEO technique
severite_type: haute
effort: S
declencheurs:
  - "crawl:no_sitemap"
  - "code:sans <lastmod>"
sources:
  - https://docs.astro.build/en/guides/integrations-guide/sitemap/
  - https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap
  - https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview
---

# Sitemap XML absent ou sans date de modification (lastmod)

> **En une phrase** : aucun sitemap n'est publié (ou il ne dit pas quand les pages ont changé), donc Google et Bing découvrent et rafraîchissent les pages plus lentement.

## Pourquoi c'est important

Le sitemap ne remplace pas les liens internes, mais il liste les pages à indexer et accélère la découverte des pages récentes ou peu liées. Google utilise `<lastmod>` seulement s'il est « régulièrement et vérifiablement exact » : il doit refléter la dernière modification significative, pas la date du build. Google ignore `<priority>` et `<changefreq>` : inutile d'y passer du temps. Bing, qui alimente aussi Copilot et une partie des assistants IA, s'appuie fortement sur `lastmod`.

## Comment le constater soi-même

```bash
for f in sitemap.xml sitemap-index.xml sitemap-0.xml; do
  curl -s -o /dev/null -w "%{http_code} /$f\n" https://SITE/$f
done
curl -s https://SITE/robots.txt | grep -i '^sitemap:'
# lastmod présent ?
curl -s https://SITE/sitemap-0.xml | grep -c '<lastmod>'
```

Présent : 404 partout et aucune ligne `Sitemap:` dans robots.txt (ou `<lastmod>` à 0). Corrigé : un sitemap en 200 déclaré dans robots.txt, avec un `<lastmod>` par URL.

## Correction

**Cas A : site statique ou pages connues au build (recommandé).** Utiliser l'intégration officielle.

1. Installer : `npx astro add sitemap` (ou `npm i @astrojs/sitemap`).
2. Vérifier que `site` est défini en https dans `astro.config.mjs` (obligatoire pour l'intégration).
3. Exclure les pages non indexables (`filter`) et renseigner `lastmod` via `serialize`, à partir de la vraie date de modification si elle est connue.

```js
// astro.config.mjs
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://exemple.fr',
  integrations: [
    sitemap({
      filter: (page) => !page.includes('/admin') && !page.includes('/merci'),
      // lastmod global = date du build : acceptable seulement si le contenu change à chaque build.
      // Idéal : dater chaque URL depuis sa source (voir serialize ci-dessous).
      serialize(item) {
        // Exemple : date de modification connue par URL (table construite depuis le contenu)
        const dates = { 'https://exemple.fr/': new Date('2026-01-15') };
        return { ...item, lastmod: (dates[item.url] ?? new Date()).toISOString() };
      },
    }),
  ],
});
```

L'intégration écrit `sitemap-index.xml` et `sitemap-0.xml` dans `dist/`. Son option `lastmod` globale attend un objet `Date`.

**Cas B : pages dynamiques (rendu serveur, contenu Convex).** Écrire un endpoint `src/pages/sitemap.xml.ts` qui lit la liste des contenus (Convex ou collection) avec leur date de mise à jour : voir le modèle complet dans la fiche `seo-sitemap-urls-http`, en fournissant `lastmod` réel.

4. Déclarer le sitemap dans `robots.txt` avec une URL absolue (fiche `seo-robots-txt-invalide-absent`) :
   `Sitemap: https://exemple.fr/sitemap-index.xml`
5. Soumettre l'URL dans Google Search Console et Bing Webmaster Tools.

## Critères d'acceptation

- [ ] `https://SITE/sitemap-index.xml` (ou `sitemap.xml`) répond 200 en XML
- [ ] Toutes les pages indexables y figurent, aucune page en `noindex` ni redirigée
- [ ] Chaque `<url>` a un `<lastmod>` fiable (pas la date du jour pour toutes les pages sans raison)
- [ ] `robots.txt` contient une ligne `Sitemap:` absolue en https
- [ ] Aucune régression : build OK

## Vérification après correction

```bash
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' https://SITE/sitemap-index.xml
curl -s https://SITE/sitemap-0.xml | grep -c '<url>'
curl -s https://SITE/sitemap-0.xml | grep -c '<lastmod>'
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif   # no_sitemap doit disparaître
```

## Pièges et retour arrière

- Un `lastmod` identique et faux sur toutes les pages est ignoré par Google, voire nuit à la confiance dans le fichier.
- Ne pas laisser un fichier `public/sitemap.xml` obsolète : il masquerait l'endpoint ou l'intégration.
- Au-delà de 50 000 URL ou 50 Mo, découper en plusieurs fichiers (l'intégration le fait via `entryLimit`).
- Retour arrière : retirer l'intégration ou supprimer l'endpoint, puis retirer la ligne `Sitemap:`.

## Pour aller plus loin

- https://docs.astro.build/en/guides/integrations-guide/sitemap/ : options `filter`, `serialize`, `lastmod`, `entryLimit`.
- https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap : formats, limites, `lastmod`, éléments ignorés.
- https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview : quand un sitemap est utile.
