---
id: seo-hote-canonique-http-www
titre: Plusieurs versions du site accessibles (http, https, www, sans www)
domaine: SEO technique
severite_type: haute
effort: S
declencheurs:
  - "crawl:variant_links"
  - "http:\\| http://\\S+ \\| 200 \\|"
  - "http:\\| http://\\S+ \\| \\d{3} \\| \\d+ \\| http://\\S+ \\("
sources:
  - https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls
  - https://nginx.org/en/docs/http/ngx_http_rewrite_module.html
  - https://caddyserver.com/docs/caddyfile/directives/redir
---

# Plusieurs versions du site accessibles (http, https, www, sans www)

> **En une phrase** : le même site répond sur `http://` et `https://`, avec et sans `www`, au lieu de rediriger toutes les variantes vers une seule adresse https.

## Pourquoi c'est important

Quatre adresses d'accueil (`http://exemple.fr`, `http://www.exemple.fr`, `https://exemple.fr`, `https://www.exemple.fr`) sont quatre sites différents pour Google. Les liens et les signaux se dispersent, le contenu est dupliqué, et Google peut choisir la mauvaise version. Les redirections sont le signal de canonicalisation le plus fort. L'attendu est : **toutes les variantes → une seule URL https, en un saut 301 ou 308**. Les liens internes doivent aussi viser directement la variante choisie (sinon chaque clic passe par une redirection).

## Comment le constater soi-même

```bash
for v in http://exemple.fr/ http://www.exemple.fr/ https://exemple.fr/ https://www.exemple.fr/; do
  curl -s -o /dev/null -w "$v -> %{http_code} sauts=%{num_redirects} final=%{url_effective}\n" -L "$v"
  curl -s -o /dev/null -w '   1er saut : %{http_code} %{redirect_url}\n' "$v"
done
# liens internes vers une autre variante (dans le code)
grep -rnE "https?://(www\.)?exemple\.fr" src/ | grep -v "https://exemple.fr" | head
```

Présent : plusieurs variantes en `200` sans redirection, ou une redirection vers `http://`. Corrigé : trois variantes en `301`/`308` vers `https://exemple.fr/` (200), une seule en 200.

## Correction

1. **Choisir** l'hôte canonique (avec ou sans `www`) et s'y tenir partout : `site` dans `astro.config.mjs`, certificat TLS, liens, sitemap.
2. **Rediriger au reverse proxy** toutes les autres variantes vers l'hôte canonique en https, en un seul saut.

```nginx
# nginx : http (toutes variantes) -> https canonique
server {
  listen 80;
  server_name exemple.fr www.exemple.fr;
  return 301 https://exemple.fr$request_uri;
}
# nginx : https://www -> https://exemple.fr
server {
  listen 443 ssl;
  server_name www.exemple.fr;
  # ssl_certificate ... (certificat valable pour www.exemple.fr)
  return 301 https://exemple.fr$request_uri;
}
```

```caddy
# Caddyfile : Caddy redirige déjà http -> https ; ajouter www -> sans www
www.exemple.fr {
  redir https://exemple.fr{uri} permanent
}
exemple.fr {
  reverse_proxy 127.0.0.1:4321
}
```

3. Hébergement géré (Vercel, Netlify, Cloudflare Pages) : définir le domaine principal dans le tableau de bord ; les autres domaines redirigent automatiquement.
4. **Corriger les liens internes** listés dans `variant_links` (`issues.json`) : utiliser des chemins relatifs (`/contact/`) plutôt que des URL absolues codées en dur, ou la bonne variante.
5. Vérifier `site` (fiche `seo-astro-site-et-proxy`) : il doit être l'hôte canonique exact, avec ou sans `www`.

## Critères d'acceptation

- [ ] Les 4 variantes d'accueil aboutissent à **une seule** URL https en **1 saut** 301/308
- [ ] Aucun lien interne ne pointe vers une autre variante (`variant_links` = 0)
- [ ] `site`, canonicals et sitemap utilisent l'hôte canonique
- [ ] Aucune régression : certificat valide sur chaque nom de l'hôte redirigé, pas de boucle

## Vérification après correction

```bash
bash scripts/http_checks.sh https://SITE/ /tmp/verif   # section 1 : variantes d'hôte
curl -sIL https://www.exemple.fr/ | grep -iE '^(HTTP|location)'
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif   # variant_links doit disparaître
```

## Pièges et retour arrière

- Le certificat TLS doit couvrir aussi le nom qui redirige, sinon le navigateur affiche une erreur avant la redirection.
- Une préproduction (`beta.exemple.fr`) est un site distinct : la rendre non indexable (`noindex` ou authentification) tant qu'elle duplique la production.
- Activer HSTS seulement une fois toutes les variantes stables (l'effet est durable dans les navigateurs).
- Retour arrière : restaurer la configuration du proxy sauvegardée avant modification (`nginx -t` avant de recharger).

## Pour aller plus loin

- https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls : consolider les URL dupliquées.
- https://nginx.org/en/docs/http/ngx_http_rewrite_module.html : directive `return`.
- https://caddyserver.com/docs/caddyfile/directives/redir : directive `redir` et `permanent`.
