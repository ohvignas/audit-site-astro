---
id: seo-robots-txt-invalide-absent
titre: robots.txt absent, invalide ou avec un Sitemap en URL relative
domaine: SEO technique
severite_type: moyenne
effort: S
declencheurs:
  - "crawl:robots_missing"
  - "crawl:robots_sitemap_relative"
  - "code:Sitemap relatif"
  - "code:Aucun robots\\.txt"
  - "lighthouse:robots-txt|robots\\.txt n.est pas valide"
  - "http:\\| /robots\\.txt \\| (404|5\\d\\d|000)"
sources:
  - https://developers.google.com/search/docs/crawling-indexing/robots/create-robots-txt
  - https://docs.astro.build/en/guides/endpoints/
  - https://developer.chrome.com/docs/lighthouse/seo/invalid-robots-txt
---

# robots.txt absent, invalide ou avec un Sitemap en URL relative

> **En une phrase** : le fichier `robots.txt` manque, ne répond pas correctement ou contient une directive `Sitemap:` sans adresse complète, ce que Google ignore et que Lighthouse signale comme invalide.

## Pourquoi c'est important

Sans `robots.txt` valide, les robots n'ont ni règle ni indication de sitemap. Google exige que `Sitemap:` soit une **URL complète** (schéma, hôte, chemin) : `Sitemap: /sitemap.xml` est ignoré et Lighthouse affiche « robots.txt n'est pas valide ». Un `robots.txt` qui répond en erreur 5xx est plus grave : Google peut suspendre l'exploration du site le temps qu'il redevienne lisible. Sans le fichier (404), Google explore tout, ce qui est acceptable mais perd la déclaration du sitemap.

## Comment le constater soi-même

```bash
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' https://SITE/robots.txt   # attendu : 200 text/plain
curl -s https://SITE/robots.txt
curl -s https://SITE/robots.txt | grep -i '^sitemap:' | grep -vi '^sitemap: https://'   # doit ne rien afficher
grep -rn "Sitemap" public/robots.txt src/pages/robots.txt.* 2>/dev/null
```

## Correction

Le fichier est servi à la racine : `https://exemple.fr/robots.txt` (pas dans un sous-dossier), en texte brut UTF-8.

**Option A : fichier statique** dans `public/robots.txt`, avec une URL absolue en dur :

```txt
User-agent: *
Allow: /

Sitemap: https://exemple.fr/sitemap-index.xml
```

**Option B : endpoint Astro qui s'appuie sur `site`** (évite de se tromper de domaine entre production et préproduction). Supprimer alors `public/robots.txt`, qui prendrait le dessus.

```ts
// src/pages/robots.txt.ts
import type { APIRoute } from 'astro';

export const prerender = true; // statique : généré au build à partir de `site`

export const GET: APIRoute = ({ site }) => {
  const sitemap = new URL('/sitemap-index.xml', site).href;
  const body = ['User-agent: *', 'Allow: /', '', `Sitemap: ${sitemap}`, ''].join('\n');
  return new Response(body, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
};
```

Adapter le nom du fichier sitemap : `sitemap-index.xml` avec `@astrojs/sitemap`, ou `sitemap.xml` pour un endpoint maison. `site` doit être défini dans `astro.config.mjs` (fiche `seo-astro-site-et-proxy`).

Points de syntaxe à respecter (Google) : chaque règle `Allow`/`Disallow` commence par `/` ; les directives sont sur des lignes séparées ; les règles sont sensibles à la casse ; `*` et `$` sont acceptés ; le fichier reste sous 500 Kio.

Pour une préproduction à ne pas indexer, ne pas se limiter à `Disallow: /` (Google peut indexer l'URL sans la lire) : ajouter une authentification ou un `noindex` (fiche `seo-noindex`), et **ne jamais** copier ce fichier en production.

## Critères d'acceptation

- [ ] `https://SITE/robots.txt` répond 200 en `text/plain`
- [ ] Chaque ligne `Sitemap:` est une URL absolue en `https://`, sur le domaine canonique
- [ ] Aucune directive inconnue ni ligne mal formée ; Lighthouse : audit `robots-txt` réussi
- [ ] Aucune régression : pas de `Disallow: /` non voulu

## Vérification après correction

```bash
curl -s https://SITE/robots.txt
curl -s https://SITE/robots.txt | grep -i '^sitemap:'
bash scripts/lighthouse_run.sh /tmp/verif-lh https://SITE/          # audit robots.txt
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif        # robots_missing, robots_sitemap_relative
```

Test officiel : rapport « robots.txt » de la Search Console.

## Pièges et retour arrière

- Un fichier `public/robots.txt` et un endpoint `robots.txt.ts` coexistent : garder un seul des deux.
- Un CDN ou un WAF peut renvoyer une page HTML (200) pour `/robots.txt` : contrôler le `content-type`.
- `robots.txt` n'est pas un mécanisme de sécurité ni de désindexation.
- Retour arrière : restaurer le fichier depuis Git.

## Pour aller plus loin

- https://developers.google.com/search/docs/crawling-indexing/robots/create-robots-txt : syntaxe, emplacement, `Sitemap` en URL complète.
- https://docs.astro.build/en/guides/endpoints/ : endpoints statiques et à la demande.
- https://developer.chrome.com/docs/lighthouse/seo/invalid-robots-txt : ce que vérifie l'audit Lighthouse.
