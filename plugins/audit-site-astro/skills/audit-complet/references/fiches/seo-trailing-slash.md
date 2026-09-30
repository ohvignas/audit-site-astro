---
id: seo-trailing-slash
titre: Slash final non fixé (trailingSlash) — /page et /page/ en doublon
domaine: SEO technique
severite_type: moyenne
effort: S
declencheurs:
  - "code:trailingSlash non fixé"
sources:
  - https://docs.astro.build/en/reference/configuration-reference/
  - https://developers.google.com/search/docs/crawling-indexing/url-structure
  - https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls
---

# Slash final non fixé (trailingSlash) — /page et /page/ en doublon

> **En une phrase** : le site accepte `/page` et `/page/` comme deux adresses différentes qui affichent le même contenu, ce qui crée des doublons et des redirections inutiles.

## Pourquoi c'est important

Pour Google, `/contact` et `/contact/` sont deux URL distinctes. Si les deux répondent 200, le contenu est dupliqué, les liens et signaux se répartissent, et le sitemap ou les canonicals peuvent pointer vers la version qui redirige. Astro laisse `trailingSlash` à `'ignore'` par défaut (les deux formes fonctionnent), et le comportement réel dépend alors de l'hébergeur. Il faut choisir **une** forme et s'y tenir partout : configuration, liens, sitemap, canonical, redirections.

## Comment le constater soi-même

```bash
# Les deux formes doivent NE PAS répondre 200 toutes les deux
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://SITE/contact
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://SITE/contact/
grep -nE "trailingSlash|format" astro.config.*
```

Présent : deux `200`. Corrigé : une forme en `200`, l'autre en `301` vers elle.

## Correction

1. **Choisir** : avec slash (`always`, cohérent avec `build.format: 'directory'` par défaut : `/contact/index.html`) ou sans slash (`never`, à associer à `build.format: 'file'`). Astro recommande d'aligner les deux réglages. Sur un site existant, garder la forme déjà indexée par Google pour éviter une migration.
2. **Fixer** dans `astro.config.mjs` :

```js
// astro.config.mjs : forme avec slash (défaut historique d'Astro pour les pages statiques)
import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://exemple.fr',
  trailingSlash: 'always',
  build: { format: 'directory' },
});
```

```js
// Variante sans slash final
export default defineConfig({
  site: 'https://exemple.fr',
  trailingSlash: 'never',
  build: { format: 'file' },
});
```

3. **Redirection de l'autre forme** :
   - Pages **rendues à la demande** : Astro redirige tout seul en 301 (GET) pour les requêtes qui ne respectent pas le réglage.
   - Pages **prérendues** : « le slash final des pages prérendues est géré par la plateforme d'hébergement » (documentation Astro). Configurer le serveur :

```nginx
# nginx : ajouter le slash final (forme "always") sauf pour les fichiers
location ~ ^([^.]*[^/])$ { return 301 $uri/; }
```

```caddy
# Caddyfile : retirer le slash final (forme "never")
@slash path_regexp slash ^(.+)/$
redir @slash {re.slash.1} permanent
```

4. **Aligner tout le reste** : liens internes (utiliser la même forme partout), canonicals, sitemap (fiches `seo-canonical` et `seo-sitemap-urls-http`), redirections `redirects`. Dans le code : `grep -rnE 'href="/[a-z-]+"' src/` révèle les liens sans slash quand la forme choisie est avec slash.
5. Ne pas modifier la forme d'un site déjà bien indexé sans plan de redirection complet.

## Critères d'acceptation

- [ ] `trailingSlash` vaut `'always'` ou `'never'`, cohérent avec `build.format`
- [ ] L'autre forme redirige en 301 en un saut vers la forme choisie
- [ ] Liens internes, canonicals et sitemap utilisent la même forme
- [ ] Aucune régression : pas de boucle de redirection, fichiers statiques (`.xml`, `.txt`, images) toujours servis

## Vérification après correction

```bash
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://SITE/contact      # 301 vers /contact/ (forme always)
curl -s -o /dev/null -w '%{http_code}\n' https://SITE/contact/                       # 200
curl -s https://SITE/sitemap-0.xml | grep -c '<loc>[^<]*[^/]</loc>'                  # forme always : attendu 0 (hors fichiers)
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif                         # link_to_redirect, sitemap_redirect
```

## Pièges et retour arrière

- En développement, avec `'always'` ou `'never'`, le serveur `astro dev` affiche un avertissement sur les URL qui ne respectent pas le réglage.
- Les endpoints (`sitemap.xml.ts`, `robots.txt.ts`) et fichiers avec extension ne prennent pas de slash final : les exclure de la règle.
- Un changement de forme demande de tout redéployer et de laisser les redirections en place au moins un an.
- Retour arrière : remettre les valeurs précédentes dans `astro.config.mjs` et la règle du serveur.

## Pour aller plus loin

- https://docs.astro.build/en/reference/configuration-reference/ : `trailingSlash` et `build.format`.
- https://developers.google.com/search/docs/crawling-indexing/url-structure : structure d'URL recommandée.
- https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls : consolider les doublons.
