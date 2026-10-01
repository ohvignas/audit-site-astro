---
id: seo-astro-site-et-proxy
titre: "`site` d'Astro absent, en http ou mal réglé, et proxy non déclaré (allowedDomains)"
domaine: SEO technique
severite_type: haute
effort: S
declencheurs:
  - "code:`site` non défini"
  - "code:`site` en http"
  - "code:`site` dépend d'une variable"
  - "code:Serveur derrière un proxy sans security\\.allowedDomains"
versions_astro: ">=5.14.2 pour security.allowedDomains"
sources:
  - https://docs.astro.build/en/reference/configuration-reference/
  - https://docs.astro.build/en/reference/api-reference/
  - https://docs.astro.build/en/guides/integrations-guide/sitemap/
---

# `site` d'Astro absent, en http ou mal réglé, et proxy non déclaré (allowedDomains)

> **En une phrase** : Astro ne connaît pas l'adresse publique du site (ou la connaît en http), donc le sitemap, les canonicals et toutes les URL absolues sortent fausses ou en `http://`.

## Pourquoi c'est important

`site` est « l'URL finale et déployée » du site : Astro s'en sert pour le sitemap et les URL canoniques (`Astro.site`). Sans elle, `@astrojs/sitemap` refuse de générer le sitemap et `Astro.site` vaut `undefined`. Derrière un reverse proxy (nginx, Caddy, Traefik), le serveur Node reçoit la requête en `http://` sur un hôte interne : sans `security.allowedDomains`, Astro ignore les en-têtes `X-Forwarded-Host` / `X-Forwarded-Proto` et `Astro.url` reflète l'adresse interne. Résultat typique : sitemap et canonicals en `http://`, que Google doit ensuite rapprocher de la version https (signaux contradictoires, indexation ralentie).

## Comment le constater soi-même

```bash
# 1. Valeur de site dans le code
grep -nE "site\s*:" astro.config.*
# 2. Sortie réelle en production : le canonical et le sitemap doivent être en https
curl -s https://SITE/ | grep -oE '<link rel="canonical"[^>]*>'
curl -s https://SITE/sitemap-index.xml | grep -o 'http://[^<]*' | head
```

Problème présent : `site` absent, en `http://` ou en `localhost`, ou canonical / sitemap avec `http://`. Corrigé : aucune ligne `http://` dans le sitemap, canonical en `https://` sur le bon domaine.

## Correction

1. Ouvrir `astro.config.mjs` (ou `.ts`) et fixer `site` avec l'adresse publique finale, en https, sans chemin. Choisir le domaine **canonique** (avec ou sans `www`, un seul).
2. Si le domaine change selon l'environnement (préproduction), lire une variable d'environnement avec une valeur par défaut de production. Dans un fichier de config Astro, `import.meta.env` n'est pas garanti : utiliser `process.env`.
3. Pour un site en rendu à la demande derrière un proxy (Astro >= 5.14.2), déclarer les hôtes autorisés dans `security.allowedDomains`.
4. Vérifier que le proxy transmet les en-têtes `X-Forwarded-Host` et `X-Forwarded-Proto`.
5. Dans le code, construire toute URL publique avec `Astro.site` (jamais avec `Astro.url.origin` ni `request.url`).

```js
// astro.config.mjs
import { defineConfig } from 'astro/config';
import node from '@astrojs/node';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: process.env.SITE_URL ?? 'https://exemple.fr',
  output: 'server',
  adapter: node({ mode: 'standalone' }),
  integrations: [sitemap()],
  security: {
    // Astro >= 5.14.2 : hôtes acceptés via X-Forwarded-Host (motifs *.exemple.fr autorisés)
    allowedDomains: [
      { hostname: 'exemple.fr', protocol: 'https' },
    ],
  },
});
```

nginx : transmettre les en-têtes au serveur Node.

```nginx
location / {
  proxy_pass http://127.0.0.1:4321;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-Host $host;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

Caddy : `reverse_proxy 127.0.0.1:4321` ajoute les en-têtes `X-Forwarded-*` par défaut (à vérifier avec la commande ci-dessous). Traefik les ajoute aussi.

```astro
---
// Dans une page ou un layout : URL publique fiable, quel que soit le proxy
const url = new URL(Astro.url.pathname, Astro.site);
---
```

Si la version d'Astro est antérieure à 5.14.2, `allowedDomains` n'existe pas : ne pas l'écrire (la config serait refusée) ; s'appuyer uniquement sur `site` et `Astro.site`, ou monter de version.

## Critères d'acceptation

- [ ] `site` est défini, en `https://`, sur le domaine canonique, sans `localhost`
- [ ] Le build produit un sitemap dont toutes les URL commencent par `https://` et le bon domaine
- [ ] Le canonical de chaque page est en `https://` (test `curl` ci-dessus)
- [ ] Si SSR derrière proxy et Astro >= 5.14.2 : `security.allowedDomains` renseigné
- [ ] Aucune régression : build OK, pages clés en 200

## Vérification après correction

```bash
grep -nE "site\s*:|allowedDomains" astro.config.*
curl -s https://SITE/ | grep -oE '<link rel="canonical"[^>]*>'
curl -s https://SITE/sitemap-index.xml | grep -c 'http://'   # attendu : 0
# Simuler le proxy contre le serveur Node local
curl -s -H 'X-Forwarded-Host: exemple.fr' -H 'X-Forwarded-Proto: https' http://127.0.0.1:4321/ | grep -oE '<link rel="canonical"[^>]*>'
```

Relancer ensuite le crawl : `python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif`.

## Pièges et retour arrière

- Une variable `SITE_URL` absente en production retombe sur la valeur par défaut : vérifier qu'elle vaut bien l'adresse publique, pas celle de la préproduction.
- Avec `allowedDomains`, une requête dont l'hôte n'est pas listé est traitée comme si l'en-tête n'existait pas : ne pas oublier `www.` si ce domaine sert du contenu.
- Changer `site` change toutes les canonicals : tester sur une branche Git avant de déployer.
- Retour arrière : `git revert` du commit de config, reconstruire ; l'humain redéploie.

## Pour aller plus loin

- https://docs.astro.build/en/reference/configuration-reference/ : `site` et `security.allowedDomains` (ajouté en 5.14.2).
- https://docs.astro.build/en/reference/api-reference/ : `Astro.site` (`undefined` si `site` manque) et `Astro.url` (dérivé de `request.url`).
- https://docs.astro.build/en/guides/integrations-guide/sitemap/ : `site` obligatoire pour `@astrojs/sitemap`.
