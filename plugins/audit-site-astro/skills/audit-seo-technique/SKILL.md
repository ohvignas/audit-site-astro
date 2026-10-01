---
name: audit-seo-technique
description: Audit SEO technique d'un site Astro — crawl complet, indexabilité, robots.txt, sitemap (endpoint custom ou @astrojs/sitemap), canonicals, redirections, http/https, trailing slash, soft 404 des routes SSR dynamiques, maillage interne, pages orphelines, profondeur, données structurées, hreflang, logs de Googlebot — avec corrections précises dans le code (fichier:ligne). Utilise ce skill quand l'utilisateur parle d'indexation, de pages absentes de Google, de Search Console, de sitemap, de robots.txt, de canonical, de redirections, de duplicate content, de crawl ou de « référencement technique », même sans citer Astro.
---

# Audit SEO technique — Astro

Scripts : `../audit-complet/scripts/` (sinon, même commande `find` que dans audit-complet §2). Format : `../audit-complet/references/format-constat.md`. Sortie : `rapports/seo-technique.md`.

## Données

`data/crawl/` (summary.md, issues.json, pages.json/csv), `data/http/http-checks.md`, `data/code/code-scan.md`. Sinon :

```bash
python3 $S/crawl_site.py https://site.fr/ --out "$AUDIT/data/crawl" --max-pages 500 --check-images 200
bash $S/http_checks.sh https://site.fr/ "$AUDIT/data/http" "$AUDIT/data/crawl/pages.json"   # après le crawl (§7)
python3 $S/astro_scan.py /chemin/projet --out "$AUDIT/data/code"
```

`issues.json` regroupe les problèmes par clé, avec une sévérité **indicative** et des exemples. À toi de confirmer, de regrouper par cause et de fixer la sévérité finale.

## Checklist

### 1. Indexabilité globale (les critiques d'abord)
- `robots.txt` : pas de `Disallow: /` pour Googlebot ; CSS et JS non bloqués ; **`Sitemap:` en URL absolue https** (un chemin relatif est invalide : Lighthouse affiche « robots.txt n'est pas valide »). Dans Astro : fichier `public/robots.txt` ou endpoint `src/pages/robots.txt.ts`. L'endpoint est préférable s'il construit l'URL à partir de `site`.
- `x-robots-tag: noindex` ou `<meta name="robots" content="noindex">` involontaires (préprod copiée en prod, prévisualisations). Un domaine de préproduction (`beta.`, `staging.`) indexable qui duplique la production = problème. Un domaine qui **est** la future production doit rester indexable.
- Variantes d'hôte (http, www) → **une seule** URL https en 1 saut 301/308 (`http-checks.md` §1).

### 2. Sitemap
- Toutes les URL en **https**, sur le bon hôte, en statut 200, indexables, canoniques, sans redirection (`sitemap_redirect`, `sitemap_non200`, `sitemap_noindex`, `sitemap_canonicalized`).
- **Cause fréquente sous Astro SSR derrière un proxy** : l'endpoint du sitemap (ou la canonical) utilise `new URL(request.url).origin`, `Astro.url.origin` ou `Astro.url.href`. Le proxy parle en http au serveur Node, donc les URL sortent en `http://`. Correction : utiliser l'origine canonique (`Astro.site` / `import.meta.env.SITE` / constante) → `new URL(path, Astro.site)`. Vérifier aussi `site:` dans `astro.config.*` (https, bon domaine, variable d'environnement correcte en prod). Depuis Astro 5.14.2, configurer aussi `security.allowedDomains: [{ hostname: 'domaine.fr', protocol: 'https' }]` pour qu'Astro accepte les en-têtes `X-Forwarded-Host`/`Proto` du proxy. Sans cela, ils sont ignorés et `Astro.url` reflète l'hôte interne. Le proxy doit transmettre ces en-têtes.
- Pages indexables absentes du sitemap (`not_in_sitemap`) : si le sitemap est généré depuis Convex (routes dynamiques), vérifier que toutes les collections y figurent (blog, formations, pages outils…).
- `<lastmod>` fiable (date réelle de modification, pas la date du build) : utile pour Google et Bing.

### 3. Canonicals et doublons
- Une canonical par page, absolue, en https, auto-référente pour les pages indexables. **Construite avec `new URL(Astro.url.pathname, Astro.site)`**, jamais avec `Astro.url.href` (qui garde `?utm=…` et le http du proxy).
- Paramètres (`?tab=`, `?page=`, `?utm_`) : canonical vers la version propre ; pas de liens internes avec UTM (`utm_internal`).
- `trailingSlash` cohérent (config Astro, sitemap, liens internes, canonical) : `/page` et `/page/` ne doivent pas répondre 200 tous les deux.

### 4. Statuts, redirections, soft 404
- 4xx liés en interne (`http_4xx` avec `liens_depuis`) : corriger le lien à la source (souvent une donnée Convex ou un composant de menu), ou créer une redirection 301 si la page a déménagé (`redirects` dans `astro.config`, ou au proxy).
- **Soft 404** : `http-checks.md` §6 teste une URL inexistante à la racine ; elle doit renvoyer 404. La §7 teste une URL inexistante **sous chaque segment qui regroupe au moins 2 pages du crawl** (`/blog/`, `/formations/`… : routes dynamiques probables) : une ligne `❌ soft 404 sous /SEG/` = la route répond 200. La §7 ne sonde que les chemins à 2 niveaux et ne suit pas les redirections : pour `/fr/blog/x` ou un site en `trailingSlash: 'always'` (308 puis page), tester à la main avec `-L` :
  ```bash
  for p in /fr/blog/zz-audit /blog/categorie/zz-audit; do curl -s -L -o /dev/null -w "%{http_code} $p\n" https://site.fr$p; done
  ```
  Un 200 = soft 404. Correction dans la route `[slug].astro` : `if (!item) return Astro.rewrite('/404');` (Astro ≥ 4.13), ou `Astro.response.status = 404`. `astro_scan.py` liste les routes suspectes.
- Chaînes de redirection et 302 qui devraient être des 301.

### 5. Maillage interne et architecture
- Profondeur : pages importantes à ≤ 3 clics (`deep_page`). Orphelines (`orphan`) : à relier depuis les hubs (catalogue, catégories, articles liés).
- Pages indexables les moins liées (`summary.md`) : ce sont souvent les pages business (métiers, formations) qu'on veut positionner. Ajouter des liens contextuels depuis le blog et les pages proches, avec des ancres descriptives (`inlink_anchors` dans pages.json).
- Liens vers des redirections (`link_to_redirect`) : pointer directement vers l'URL finale.
- Menus et footers identiques sur toutes les pages : normal, mais ce ne sont pas des liens contextuels.

### 6. Balises de base (volume)
- Titles absents, dupliqués, trop courts (ex. « Accueil » seul) ou trop longs ; meta descriptions ; H1 absent ou multiple. Regrouper par gabarit : si toutes les pages `/outils/*` ont le même défaut, c'est **un** correctif dans le composant ou la page dynamique.
- `lang` sur `<html>`, viewport, Open Graph complet (og:title, og:description, og:image **absolue**, og:url), favicon (`/favicon.ico` ou `<link rel="icon">`, affiché dans les résultats Google).

### 7. Données structurées
- Types présents par gabarit (`jsonld_types` dans pages.json) : Organization et WebSite (accueil), BreadcrumbList, Course en **liste de cours** (formations : `name` et `description`, au moins trois cours ; le résultat « Course info » n'existe plus), Article ou BlogPosting (blog, avec author, datePublished, dateModified), FAQPage seulement si la FAQ est visible (Google n'en affiche plus de résultat enrichi depuis mai 2026 ; le balisage reste utile aux assistants IA), LocalBusiness ou EducationalOrganization (si adresse physique).
- JSON invalide (`jsonld_invalid`). Validation manuelle des gabarits clés : https://validator.schema.org et le test des résultats enrichis de Google (donner les URL à tester à l'utilisateur).
- **Validité schema.org et éligibilité Google sont deux contrôles distincts.** `jsonld_proprietes_requises` (moyenne) : un type actif (Event, Product, Course liste, JobPosting, LocalBusiness, Recipe, VideoObject, BreadcrumbList, Review…) n'a pas toutes les propriétés exigées par Google : pas de résultat enrichi, même si le validateur schema.org ne signale rien. `jsonld_type_sans_effet` (info) : type dont Google a retiré l'affichage en 2023-2026 (ClaimReview, Course Info, Estimated salary, Learning video, Special announcement, Vehicle listing, Practice problem, How-to, FAQ, boîte de recherche de sitelinks) : le balisage reste du schema.org valide et sert encore les assistants IA ; ne pas le présenter comme une erreur, seulement ne plus en attendre d'affichage Google. Table et dates : https://developers.google.com/search/updates (relue le 2026-10-01). Ce qui reste actif : liste de cours, Dataset (Dataset Search), Book actions.
- `jsonld_prix_absent_du_texte` (basse, à vérifier) : un prix du JSON-LD n'apparaît pas dans le texte visible ; le balisage doit refléter le contenu affiché (à confirmer à la main si le prix est chargé côté client).

### 8. International (si le site est multilingue)
- `hreflang` réciproques + `x-default` ; config `i18n` d'Astro cohérente avec les URL.

### 9. Logs serveur : ce que Google fait vraiment (si accès)
Chercher les logs du proxy (`/var/log/nginx/access.log*`, `/var/log/caddy/`, `docker logs <proxy>`) :
```bash
LOG=/var/log/nginx/access.log
zgrep -hi 'googlebot' $LOG* | awk '{print $9}' | sort | uniq -c | sort -rn            # statuts servis à Googlebot
zgrep -hi 'googlebot' $LOG* | awk '{print $7}' | sort | uniq -c | sort -rn | head -30 # URL les plus crawlées
zgrep -hi 'googlebot' $LOG* | awk '$9>=400{print $9, $7}' | sort | uniq -c | sort -rn | head -20
```
(Format « combined » : champ 7 = chemin, champ 9 = statut ; adapter pour du JSON avec `jq`.) Budget de crawl gaspillé (paramètres, 404, redirections), pages clés jamais visitées. Vérifier qu'une IP est bien celle de Google : `host <ip>` → `*.googlebot.com`.

### 10. Search Console / Bing Webmaster Tools
Si l'utilisateur peut exporter les rapports « Indexation des pages » et « Performances » (CSV), les croiser avec le crawl : pages « Explorée, non indexée », « Détectée, non indexée », doublons sans canonical choisie par l'utilisateur. Sinon, lister ce qu'il doit vérifier lui-même, et soumettre le sitemap dans les deux outils (Bing alimente aussi Copilot et une partie des assistants IA).

## Correctifs types

```astro
---
// src/layouts/BaseLayout.astro — canonical et og:url robustes derrière un proxy
const canonical = new URL(Astro.url.pathname, Astro.site).href;
---
<link rel="canonical" href={canonical} />
<meta property="og:url" content={canonical} />
```

```ts
// src/pages/robots.txt.ts — robots.txt généré à partir de `site`
import type { APIRoute } from 'astro';
export const prerender = true;
export const GET: APIRoute = ({ site }) =>
  new Response(`User-agent: *\nAllow: /\nDisallow: /*?t=\n\nSitemap: ${new URL('/sitemap.xml', site)}\n`,
    { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
```
(Supprimer alors `public/robots.txt`, qui prendrait le dessus.)

```astro
---
// src/pages/blog/[slug].astro — vrai 404 si l'article n'existe pas
const post = await getPost(Astro.params.slug);
if (!post) return Astro.rewrite('/404');
---
```

## Restitution
`rapports/seo-technique.md` : chiffres clés (pages crawlées, indexables, statuts, sitemap), puis les constats `SEO-NNN`, **une cause par constat** avec tous ses symptômes en preuve.
