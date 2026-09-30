---
id: seo-redirections
titre: Liens internes vers des redirections, chaînes de redirections et redirections temporaires
domaine: SEO technique
severite_type: moyenne
effort: S
declencheurs:
  - "crawl:link_to_redirect"
  - "crawl:redirect_chain"
  - "crawl:redirect_temp"
  - "http:\\| https?://\\S+ \\| (302|303|307) \\|"
  - "http:\\| https?://\\S+ \\| \\d{3} \\| ([2-9]|[1-9]\\d) \\|"
sources:
  - https://developers.google.com/search/docs/crawling-indexing/301-redirects
  - https://developers.google.com/search/docs/crawling-indexing/site-move-with-url-changes
  - https://docs.astro.build/en/guides/routing/
  - https://docs.astro.build/en/reference/configuration-reference/
---

# Liens internes vers des redirections, chaînes de redirections et redirections temporaires

> **En une phrase** : des liens du site passent par une ou plusieurs redirections avant d'arriver à la vraie page, ou utilisent une redirection temporaire (302/307) alors que le changement est définitif.

## Pourquoi c'est important

Chaque redirection ajoute un aller-retour réseau (un utilisateur mobile attend plus, le budget de crawl de Google se consomme). Googlebot suit jusqu'à 10 sauts, mais Google conseille de rester en dessous de 3 à 5. Une redirection permanente (301/308) transmet les signaux à la nouvelle URL ; une redirection temporaire (302/303/307) laisse croire que l'ancienne URL reste la référence. Corriger le lien à la source vaut mieux que garder la redirection.

## Comment le constater soi-même

```bash
# Chaîne complète d'une URL : statuts, sauts, URL finale
curl -sIL -o /dev/null -w 'sauts=%{num_redirects} final=%{url_effective} code=%{http_code}\n' https://SITE/ancienne-url
# Détail de chaque saut
curl -sIL https://SITE/ancienne-url | grep -iE '^(HTTP|location)'
# Liens internes concernés (liste "link_to_redirect" et "liens_depuis" dans data/crawl/issues.json)
grep -rn "/ancienne-url" src/ | head
```

Présent : plus d'un saut, un `302`/`307`, ou une URL de menu / de contenu qui redirige. Corrigé : `sauts=0` pour les URL liées, un seul `301`/`308` pour les anciennes adresses.

## Correction

1. **Corriger la source du lien** : ouvrir le fichier qui contient le lien (`liens_depuis` dans `issues.json`) : menu, pied de page, composant, contenu Markdown ou donnée Convex. Remplacer par l'URL finale exacte (avec la bonne casse, le bon slash final, en https).
2. **Supprimer les chaînes** : A → B → C devient A → C et B → C. Toujours rediriger vers la destination finale, jamais vers une autre redirection.
3. **Passer en permanent** ce qui est définitif : 301 (ou 308), pas 302/307. Garder 302/307 uniquement pour un déplacement réellement temporaire.
4. **Déclarer les anciennes URL** dans Astro (site rendu à la demande) :

```js
// astro.config.mjs
import { defineConfig } from 'astro/config';

export default defineConfig({
  redirects: {
    '/ancienne-page': '/nouvelle-page/',                       // 301 par défaut
    '/blog/[...slug]': '/articles/[...slug]/',                // mêmes paramètres des deux côtés
    '/promo': { status: 302, destination: '/offres/' },       // temporaire assumé (302 : rendu à la demande)
  },
});
```

Le statut par défaut est 301 ; 302 et 308 sont pris en charge avec un adaptateur (rendu à la demande). Sur un site **statique** sans adaptateur, Astro génère une page HTML avec `meta refresh`, pas un vrai 301 HTTP : dans ce cas, mettre la redirection au serveur ou à l'hébergeur.

5. **Redirection au serveur** (site statique, ou cas plus simple à maintenir) :

```nginx
# nginx
location = /ancienne-page { return 301 /nouvelle-page/; }
```

```caddy
# Caddyfile
redir /ancienne-page /nouvelle-page/ permanent
```

6. Redirection dynamique dans une page rendue à la demande : `return Astro.redirect('/nouvelle-page/', 301);` (sans second argument, le statut est 302).

## Critères d'acceptation

- [ ] Aucun lien interne ne pointe vers une URL qui redirige (`link_to_redirect` = 0)
- [ ] Toute redirection d'ancienne URL se fait en **un seul saut** (`redirect_chain` = 0)
- [ ] Les redirections définitives sont en 301 ou 308 (`redirect_temp` = 0, sauf cas voulu documenté)
- [ ] Aucune régression : pages de destination en 200, aucune boucle de redirection

## Vérification après correction

```bash
curl -sIL -o /dev/null -w '%{num_redirects} %{url_effective} %{http_code}\n' https://SITE/ancienne-page   # attendu : 1 (URL finale) 200
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif   # link_to_redirect, redirect_chain, redirect_temp
bash scripts/http_checks.sh https://SITE/ /tmp/verif           # section 1 : variantes d'hôte en 1 saut 301/308
```

## Pièges et retour arrière

- Ne pas créer de boucle (A → B → A) : tester chaque règle avec `curl -sIL`.
- Garder les redirections d'anciennes URL au moins un an (recommandation de Google pour les changements d'adresse).
- Ne pas rediriger massivement vers l'accueil : Google le traite comme une erreur douce ; viser la page équivalente.
- Retour arrière : retirer la règle (`redirects`, nginx, Caddy), recharger le serveur, redéployer.

## Pour aller plus loin

- https://developers.google.com/search/docs/crawling-indexing/301-redirects : types de redirections et effet sur la recherche.
- https://developers.google.com/search/docs/crawling-indexing/site-move-with-url-changes : chaînes (10 sauts maximum), durée de conservation.
- https://docs.astro.build/en/guides/routing/ : `redirects`, `Astro.redirect()`.
- https://docs.astro.build/en/reference/configuration-reference/ : option `redirects`.
