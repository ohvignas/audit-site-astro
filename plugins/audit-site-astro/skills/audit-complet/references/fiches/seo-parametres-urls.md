---
id: seo-parametres-urls
titre: URL avec paramètres (UTM, filtres) indexables et URL peu propres
domaine: SEO technique
severite_type: moyenne
effort: M
declencheurs:
  - "crawl:utm_internal"
  - "crawl:param_indexable"
  - "crawl:url_hygiene"
sources:
  - https://developers.google.com/search/docs/crawling-indexing/url-structure
  - https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls
  - https://developers.google.com/search/docs/crawling-indexing/robots/create-robots-txt
---

# URL avec paramètres (UTM, filtres) indexables et URL peu propres

> **En une phrase** : des adresses avec `?utm_...`, `?tab=`, `?page=` ou des majuscules et underscores existent en plus de l'adresse propre, ce qui multiplie les doublons et fausse les statistiques.

## Pourquoi c'est important

Chaque paramètre crée une nouvelle URL pour Google. Des liens internes portant des paramètres UTM (`?utm_source=menu`) sont particulièrement nuisibles : ils envoient les visiteurs internes vers une URL "de campagne" qui écrase la source d'origine dans l'analytics et dédouble la page. Google recommande des URL lisibles, en minuscules, avec des tirets (`-`) plutôt que des underscores, et une canonical propre pour toute variante à paramètres. Les majuscules sont distinctes des minuscules (`/Contact` ≠ `/contact`).

## Comment le constater soi-même

```bash
# Liens internes avec UTM dans le code
grep -rnE 'href="[^"]*\?(utm_|ref=|source=)' src/ | head
# Canonical d'une page avec paramètre (doit pointer vers la version propre)
curl -s 'https://SITE/page/?utm_source=x' | grep -oE '<link rel="canonical"[^>]*>'
# URL avec majuscules ou underscores dans le sitemap
curl -s https://SITE/sitemap-0.xml | grep -oE '<loc>[^<]*' | grep -E '[A-Z_]' | head
```

Les listes complètes sont dans `data/crawl/issues.json` (clés `utm_internal`, `param_indexable`, `url_hygiene`) avec la page d'origine du lien.

## Correction

1. **UTM en interne** : supprimer tout paramètre `utm_*` des liens internes (menus, pieds de page, bannières, boutons, contenu). Le suivi des clics internes se fait avec des événements analytics ou un attribut `data-*`, pas avec l'URL.
2. **URL avec paramètres indexables** : pour chaque paramètre, décider s'il change le contenu.
   - Non (suivi, tri, affichage) : la canonical de la page pointe vers la version sans paramètre (fiche `seo-canonical` : `new URL(Astro.url.pathname, Astro.site)` retire déjà la requête). Ne pas mettre ces variantes dans le sitemap.
   - Oui (pagination, filtre à valeur SEO) : préférer une vraie route (`/blog/page/2/`, `/formations/excel/`) à un paramètre.
3. **Bloquer l'exploration des paramètres sans valeur** dans robots.txt (jamais ceux dont la canonical est utile à lire) :

```txt
User-agent: *
Disallow: /*?utm_
Disallow: /*?fbclid=
Disallow: /*&utm_
```

4. **URL peu propres** (majuscules, underscores, plus de 115 caractères) : créer des slugs en minuscules avec tirets, puis rediriger l'ancienne URL en 301 (fiche `seo-redirections`). Exemple de nettoyage de slug :

```ts
// src/lib/slug.ts
export function slugify(texte: string): string {
  return texte
    .normalize('NFD').replace(/[̀-ͯ]/g, '') // retire les accents
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')                      // tout le reste devient un tiret
    .replace(/^-+|-+$/g, '')
    .slice(0, 80);
}
```

5. **Normaliser au serveur** les majuscules éventuelles vers la version minuscule (redirection 301) ; et ne jamais générer de lien vers la version en majuscules.
6. Vérifier que le sitemap ne contient aucune URL avec paramètre.

## Critères d'acceptation

- [ ] Aucun lien interne ne contient `utm_` ni autre paramètre de suivi (`utm_internal` = 0)
- [ ] Toute URL avec paramètre a une canonical vers la version propre, ou est bloquée/noindex volontairement (`param_indexable` = 0 pour les pages sans valeur SEO)
- [ ] URL en minuscules, avec tirets, de longueur raisonnable ; anciennes URL redirigées en 301 (`url_hygiene` en baisse)
- [ ] Aucune régression : les campagnes externes (avec UTM) arrivent toujours sur la page en 200

## Vérification après correction

```bash
grep -rnE 'href="[^"]*utm_' src/ | wc -l                                    # attendu : 0
curl -s 'https://SITE/page/?utm_source=x' | grep -oE 'rel="canonical"[^>]*'  # href sans paramètre
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif                 # utm_internal, param_indexable, url_hygiene
```

## Pièges et retour arrière

- Les UTM des liens **externes** (newsletters, réseaux sociaux) sont normaux : ne pas les bloquer, seulement les canonicaliser.
- Ne pas mettre `Disallow` sur un paramètre dont la page porte un `noindex` ou une canonical à faire lire à Google.
- Renommer un slug sans redirection 301 crée des 404.
- Retour arrière : restaurer les liens et règles depuis Git.

## Pour aller plus loin

- https://developers.google.com/search/docs/crawling-indexing/url-structure : bonnes pratiques de structure d'URL (tirets, minuscules, paramètres).
- https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls : canonicals pour les variantes à paramètres.
- https://developers.google.com/search/docs/crawling-indexing/robots/create-robots-txt : jokers `*` et `$` dans robots.txt.
