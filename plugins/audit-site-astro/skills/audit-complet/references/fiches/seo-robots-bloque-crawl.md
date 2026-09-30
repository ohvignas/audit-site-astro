---
id: seo-robots-bloque-crawl
titre: robots.txt bloque le site, les CSS/JS ou des pages du sitemap
domaine: SEO technique
severite_type: critique
effort: S
declencheurs:
  - "crawl:robots_blocks_all"
  - "crawl:robots_blocks_assets"
  - "crawl:sitemap_blocked"
  - "crawl:linked_blocked"
sources:
  - https://developers.google.com/search/docs/crawling-indexing/robots/create-robots-txt
  - https://developers.google.com/search/docs/crawling-indexing/robots/intro
  - https://developers.google.com/search/docs/crawling-indexing/block-indexing
---

# robots.txt bloque le site, les CSS/JS ou des pages du sitemap

> **En une phrase** : une règle `Disallow` empêche Googlebot d'explorer tout le site, ses fichiers CSS/JS ou des pages que vous voulez pourtant voir indexées.

## Pourquoi c'est important

`Disallow: /` sous `User-agent: *` interdit l'exploration de tout le site : c'est la cause d'une disparition brutale du trafic après une mise en production (le fichier de préproduction a été copié). Bloquer les CSS et JS empêche Google de rendre la page comme un visiteur (mise en page, contenu injecté), ce qui dégrade l'évaluation mobile. Une page bloquée **et** listée dans le sitemap est une contradiction. Attention : bloquer une URL dans robots.txt ne la retire pas de Google (elle peut rester indexée, sans description) ; pour désindexer, il faut un `noindex` que Google puisse lire, donc **sans** blocage robots.txt.

## Comment le constater soi-même

```bash
curl -s https://SITE/robots.txt
curl -s https://SITE/robots.txt | grep -iE '^\s*disallow:\s*/\s*$'      # blocage total
curl -s https://SITE/robots.txt | grep -iE 'disallow:.*(_astro|\.css|\.js|/assets)'   # ressources bloquées
grep -rn "Disallow" public/robots.txt src/pages/robots.txt.* 2>/dev/null
```

Astro sert ses fichiers compilés dans `/_astro/` : un `Disallow: /_astro/` bloque le CSS et le JS du site.

## Correction

1. Ouvrir la source du fichier (`public/robots.txt` ou `src/pages/robots.txt.ts`) et vérifier qu'il n'est pas issu d'une préproduction. Le contenu de production le plus simple :

```txt
User-agent: *
Allow: /

Sitemap: https://exemple.fr/sitemap-index.xml
```

2. Ne bloquer que ce qui est inutile à explorer (espace privé, résultats de recherche interne, paramètres de suivi), jamais `/_astro/`, les images ni les polices.

```txt
User-agent: *
Disallow: /admin/
Disallow: /recherche
Disallow: /*?utm_
Allow: /

Sitemap: https://exemple.fr/sitemap-index.xml
```

3. **Blocage voulu d'une préproduction** : le faire par un contrôle d'accès (mot de passe HTTP) plutôt que par `Disallow: /`, et s'assurer que ce fichier n'est jamais déployé en production. Générer le fichier selon l'environnement :

```ts
// src/pages/robots.txt.ts
import type { APIRoute } from 'astro';

export const prerender = true;

export const GET: APIRoute = ({ site }) => {
  const production = process.env.SITE_ENV === 'production'; // lu pendant le build (endpoint prérendu)
  const lines = production
    ? ['User-agent: *', 'Allow: /', '', `Sitemap: ${new URL('/sitemap-index.xml', site).href}`]
    : ['User-agent: *', 'Disallow: /'];
  return new Response(lines.join('\n') + '\n', {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
```

Attention : ce fichier est prérendu au build ; la variable `SITE_ENV` doit donc exister **au moment du build** de chaque environnement.

4. Pour chaque page du sitemap bloquée (`sitemap_blocked`) : soit retirer la règle qui la bloque, soit la retirer du sitemap. Pour les pages liées mais bloquées (`linked_blocked`) : décider si elles doivent être explorées ; si oui, débloquer.
5. Après correction, demander l'exploration de l'accueil dans la Search Console (Inspection d'URL) pour accélérer la reprise.

## Critères d'acceptation

- [ ] Aucun `Disallow: /` (sous `User-agent: *` ou `Googlebot`) en production
- [ ] Aucune règle ne bloque `/_astro/`, les CSS, JS, images ou polices
- [ ] Aucune URL du sitemap n'est bloquée
- [ ] Aucune régression : les zones privées (admin) restent protégées par authentification, pas seulement par robots.txt

## Vérification après correction

```bash
curl -s https://SITE/robots.txt
curl -s https://SITE/robots.txt | grep -ciE 'disallow:.*(_astro|\.css|\.js)'   # attendu : 0
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif   # robots_blocks_all, robots_blocks_assets, sitemap_blocked, linked_blocked
```

Vérifier aussi dans la Search Console : « Inspection d'URL » → « Explorer l'URL en ligne ».

## Pièges et retour arrière

- La règle la plus **spécifique** l'emporte : `Allow: /_astro/` peut débloquer un sous-chemin d'un `Disallow` plus large.
- Un groupe `User-agent: Googlebot` remplace le groupe `*` pour Googlebot (il ne cumule pas) : recopier les règles utiles dans chaque groupe.
- Ne jamais compter sur robots.txt pour cacher des données sensibles : le fichier est public.
- Retour arrière : restaurer la version précédente du fichier (Git) et demander à l'humain de redéployer immédiatement.

## Pour aller plus loin

- https://developers.google.com/search/docs/crawling-indexing/robots/create-robots-txt : syntaxe, groupes, `Allow`/`Disallow`.
- https://developers.google.com/search/docs/crawling-indexing/robots/intro : robots.txt n'empêche pas l'indexation.
- https://developers.google.com/search/docs/crawling-indexing/block-indexing : désindexer avec `noindex`.
