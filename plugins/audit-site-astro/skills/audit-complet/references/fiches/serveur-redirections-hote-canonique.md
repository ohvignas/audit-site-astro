---
id: serveur-redirections-hote-canonique
titre: Redirections en chaîne ou temporaires (www / sans www, http, slash final)
domaine: Serveur / HTTP
severite_type: moyenne
effort: S
declencheurs:
  - "lighthouse:^redirects$|Évitez les redirections de page multiples|document-latency-insight .*redirections"
sources:
  - https://developers.google.com/search/docs/crawling-indexing/301-redirects
  - https://docs.astro.build/en/guides/routing/
  - https://caddyserver.com/docs/caddyfile/directives/redir
  - https://nginx.org/en/docs/http/ngx_http_rewrite_module.html
---

# Redirections en chaîne ou temporaires (www / sans www, http, slash final)

> **En une phrase** : pour atteindre la bonne URL, le visiteur (et Googlebot) enchaîne plusieurs redirections, ou passe par des redirections « temporaires » qui devraient être permanentes ; chaque saut coûte 100 à 300 ms et dilue les signaux de classement.

## Pourquoi c'est important

_Cette fiche complète `seo-redirections` (détection dans le crawl) : ici l'angle est la configuration du proxy (nginx, Caddy, Traefik), du CDN et des redirections écrites dans Astro, ainsi que l'audit Lighthouse._

Chaque redirection ajoute un aller-retour réseau avant le premier octet de la vraie page, d'où un TTFB, un FCP et un LCP dégradés (Lighthouse : « Évitez les redirections de page multiples »). Google suit les chaînes mais recommande de les limiter, et les 302/307 signalent une redirection provisoire : Google peut continuer à indexer l'ancienne URL. L'objectif est simple : **toutes les variantes** (`http://exemple.fr`, `http://www.exemple.fr`, `https://www.exemple.fr`) mènent à **une seule URL canonique** en **un seul saut** 301/308.

## Comment le constater soi-même

```bash
for v in http://exemple.fr/ http://www.exemple.fr/ https://exemple.fr/ https://www.exemple.fr/; do
  curl -sIL -o /dev/null -w "$v -> %{num_redirects} saut(s) -> %{url_effective} (%{http_code})\n" "$v"
done
curl -sI http://www.exemple.fr/ | grep -iE '^(HTTP|location)'      # premier saut : code + destination
curl -sIL http://www.exemple.fr/ | grep -iE '^(HTTP|location)'     # la chaîne complète
```

Problème présent : 2 sauts ou plus (ex. `http://www` → `https://www` → `https://exemple.fr`), ou un premier saut en 302/307. Corrigé : chaque variante fait 1 saut, en 301 ou 308.

## Correction

1. **Choisir une version canonique** (avec ou sans `www`) et la retrouver dans `site:` de `astro.config.mjs`, dans le sitemap et dans les balises canonical. Les redirections de ce guide utilisent `https://exemple.fr` (sans `www`) ; inverser si le site est canonique en `www`.

2. **nginx** : trois blocs, chacun redirigeant **directement** vers la destination finale. Le certificat du bloc 443 `www` doit couvrir `www.exemple.fr`.

```nginx
# 1) http (les deux hôtes) -> https canonique en un saut
server {
    listen 80;
    listen [::]:80;
    server_name exemple.fr www.exemple.fr;
    return 301 https://exemple.fr$request_uri;
}
# 2) https://www -> https://exemple.fr
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name www.exemple.fr;
    ssl_certificate     /etc/letsencrypt/live/exemple.fr/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/exemple.fr/privkey.pem;
    return 301 https://exemple.fr$request_uri;
}
# 3) le site : server { listen 443 ssl; server_name exemple.fr; … proxy_pass … }
```

3. **Caddy** : déclarer explicitement les adresses `http://` des deux hôtes pour éviter le double saut, et `www` en 301.

```caddy
http://exemple.fr, http://www.exemple.fr {
	redir https://exemple.fr{uri} permanent
}
www.exemple.fr {
	redir https://exemple.fr{uri} permanent
}
exemple.fr {
	encode zstd gzip
	reverse_proxy 127.0.0.1:4321
}
```

4. **Traefik** : la redirection http vers https se règle sur le point d'entrée (voir la fiche `serveur-redirection-http-vers-https`) ; `www` vers apex avec un middleware `redirectregex` (labels Docker, `$$` protège le `$` dans `docker-compose.yml`) :

```yaml
labels:
  - "traefik.http.routers.www.rule=Host(`www.exemple.fr`)"
  - "traefik.http.routers.www.entrypoints=websecure"
  - "traefik.http.routers.www.tls.certresolver=letsencrypt"
  - "traefik.http.routers.www.middlewares=www-vers-apex"
  - "traefik.http.middlewares.www-vers-apex.redirectregex.regex=^https://www\\.exemple\\.fr/(.*)"
  - "traefik.http.middlewares.www-vers-apex.redirectregex.replacement=https://exemple.fr/$${1}"
  - "traefik.http.middlewares.www-vers-apex.redirectregex.permanent=true"
```

Le premier saut `http://www` sera encore redirigé par le point d'entrée vers `https://www` puis vers l'apex (2 sauts) : pour n'en avoir qu'un, ajouter un second routeur sur le point d'entrée `web` (règle `Host` pour `www.exemple.fr`) avec un middleware `redirectregex` dont la regex accepte aussi `http` (`^https?://www\.exemple\.fr/(.*)`) ; ce routeur doit être prioritaire sur la redirection globale du point d'entrée, ce qui est à vérifier avec `curl -sIL` après déploiement.

5. **Vercel / Netlify / Cloudflare** : définir le domaine principal dans le tableau de bord de la plateforme ; l'autre variante est redirigée automatiquement en 301/308 (Vercel : Settings > Domains ; Netlify : Domain management > « Set as primary domain » ; Cloudflare : règle de redirection « Redirect Rules » en 301).

6. **Redirections écrites dans Astro** : `Astro.redirect('/nouvelle-url')` renvoie **302 par défaut**. Pour une redirection définitive, passer le code :

```astro
---
export const prerender = false;
return Astro.redirect('/nouvelle-url', 301);
---
```

Pour des anciennes URL connues, préférer la configuration (statut 301 par défaut) :

```js
// astro.config.mjs
export default defineConfig({
  redirects: {
    '/ancienne-page': '/nouvelle-page',
    '/ancien-blog/[slug]': { status: 301, destination: '/blog/[slug]' },
  },
});
```

7. **Slash final** : si `trailingSlash` (Astro) et le proxy ne sont pas d'accord, chaque URL provoque un saut. Aligner `trailingSlash: 'always'` ou `'never'` dans `astro.config.mjs` avec les liens internes et le sitemap, et ne pas ajouter de règle de proxy qui ajoute ou retire le slash.

## Critères d'acceptation

- [ ] Les quatre variantes d'hôte aboutissent à la même URL https en 1 saut, code 301 ou 308
- [ ] Aucun 302, 303 ou 307 sur une redirection définitive
- [ ] `curl -sIL` d'une URL du crawl signalée `redirect_chain` ne montre plus qu'un saut
- [ ] Aucune régression : chemin et paramètres conservés, pas de boucle

## Vérification après correction

```bash
for v in http://exemple.fr/ http://www.exemple.fr/ https://www.exemple.fr/; do
  curl -sIL -o /dev/null -w "%{num_redirects} saut(s) %{url_effective}\n" "$v"
done
bash scripts/http_checks.sh https://exemple.fr/ /tmp/verif       # §1 : 1 saut partout
python3 scripts/crawl_site.py https://exemple.fr/ --out /tmp/verif/crawl
```

## Pièges et retour arrière

- Ne jamais rediriger vers une URL qui redirige elle-même (test à faire après chaque changement).
- Les navigateurs gardent les 301 en cache très longtemps : tester avec `curl` ou une fenêtre privée, et éviter de publier une redirection permanente erronée.
- Retour arrière : restaurer la configuration précédente ; un 301 déjà diffusé peut rester en cache côté navigateur.

## Pour aller plus loin

- https://developers.google.com/search/docs/crawling-indexing/301-redirects : types de redirections et effet sur Google.
- https://docs.astro.build/en/guides/routing/ : redirections configurées (`redirects`) et `Astro.redirect()`.
- https://caddyserver.com/docs/caddyfile/directives/redir : `redir` et l'option `permanent`.
- https://nginx.org/en/docs/http/ngx_http_rewrite_module.html : `return` pour rediriger.
