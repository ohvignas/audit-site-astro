---
id: serveur-redirection-http-vers-https
titre: La version http:// du site répond sans rediriger vers https://
domaine: Serveur / HTTP
severite_type: haute
effort: S
declencheurs:
  - "lighthouse:redirects-http"
  - "lighthouse:Ne redirige pas le trafic HTTP vers HTTPS"
sources:
  - https://caddyserver.com/docs/caddyfile/directives/redir
  - https://doc.traefik.io/traefik/reference/install-configuration/entrypoints/
  - https://nginx.org/en/docs/http/ngx_http_rewrite_module.html
  - https://developers.google.com/search/docs/crawling-indexing/site-move-with-url-changes
---

# La version http:// du site répond sans rediriger vers https://

> **En une phrase** : quelqu'un qui tape `http://exemple.fr` reste en clair (ou tombe sur une page différente) au lieu d'être renvoyé vers `https://exemple.fr` ; deux versions du site coexistent pour Google et les données circulent sans chiffrement.

## Pourquoi c'est important

_Cette fiche complète `seo-hote-canonique-http-www` (qui traite la détection dans le crawl et les lignes du tableau d'hôtes) : ici l'angle est la configuration du proxy, de Traefik et du CDN, et l'audit Lighthouse._

Sans redirection, Google peut indexer et classer les deux versions (`http` et `https`) : contenu dupliqué, signaux de liens dispersés. Les visiteurs qui arrivent par un lien ou un marque-page en `http://` envoient cookies et formulaires en clair, et les navigateurs affichent « Non sécurisé ». Lighthouse signale l'audit « Ne redirige pas le trafic HTTP vers HTTPS ». La redirection doit être **permanente** (301 ou 308) et se faire en **un seul saut**.

L'outil lit la table « Variantes d'hôte » : la ligne `http://…` doit renvoyer 301/308 avec 1 saut vers une URL `https://`. Ici, soit la réponse est 200 sans aucun saut, soit la redirection aboutit encore sur `http://`.

## Comment le constater soi-même

```bash
curl -sI http://SITE/ | head -5            # attendu : HTTP/1.1 301 (ou 308) + location: https://SITE/
curl -sIL -o /dev/null -w 'sauts : %{num_redirects} | finale : %{url_effective} | code : %{http_code}\n' http://SITE/
```

Problème présent : `HTTP/1.1 200 OK` (le site répond en clair), ou une `location:` qui recommence en `http://`. Corrigé : `301 Moved Permanently` puis `location: https://SITE/`.

## Correction

1. Le certificat TLS doit déjà couvrir le domaine (voir la fiche `secu-tls-certificat` pour le renouvellement). Ensuite, ajouter la redirection **au premier niveau qui reçoit le trafic** (proxy ou CDN), pas dans Astro.

2. **nginx** : un bloc dédié au port 80, qui redirige tout en conservant le chemin et les paramètres :

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name exemple.fr www.exemple.fr;
    return 301 https://exemple.fr$request_uri;
}
```

`exemple.fr` est ici la version canonique (voir la fiche `serveur-redirections-hote-canonique` pour le choix avec ou sans `www`). Ne pas laisser l'ancien `server { listen 80; … proxy_pass … }` qui sert le site en clair.

3. **Caddy** : Caddy redirige déjà `http` vers `https` automatiquement (code 308) pour les domaines déclarés dans le `Caddyfile`. Si la redirection manque, chercher `auto_https off`, `auto_https disable_redirects`, une adresse écrite avec `http://` ou un port 80 non ouvert. Pour la forcer explicitement en un saut :

```caddy
http://exemple.fr, http://www.exemple.fr {
	redir https://exemple.fr{uri} permanent
}
```

4. **Traefik** (fichier statique `traefik.yml`, redirection au niveau du point d'entrée) :

```yaml
entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
          permanent: true
  websecure:
    address: ":443"
```

Équivalent en arguments de ligne de commande (rubrique `command:` du conteneur Traefik dans `docker-compose.yml`) : `--entrypoints.web.http.redirections.entrypoint.to=websecure`, `--entrypoints.web.http.redirections.entrypoint.scheme=https`, `--entrypoints.web.http.redirections.entrypoint.permanent=true`.

5. **Vercel / Netlify / Cloudflare** : la redirection est automatique sur le domaine géré par la plateforme. Si elle manque : Cloudflare → SSL/TLS > « Toujours utiliser HTTPS » ; Netlify → Domain management > HTTPS > « Force HTTPS » ; Vercel → domaine ajouté au projet (les redirections http vers https sont automatiques).

6. **Côté Astro** : définir `site: 'https://exemple.fr'` dans `astro.config.mjs` pour que canonicals, sitemap et liens absolus soient en https, et déclarer `security.allowedDomains` si Astro est derrière un proxy (voir la fiche `seo-astro-site-et-proxy`).

7. Ne pas ajouter d'en-tête HSTS avant d'avoir vérifié que **tout** le site (et ses sous-domaines) fonctionne en https : c'est traité par la fiche de sécurité correspondante.

## Critères d'acceptation

- [ ] `curl -sI http://SITE/` renvoie 301 ou 308 avec `location: https://…`
- [ ] Le chemin et les paramètres sont conservés (`http://SITE/blog/x?a=1` → `https://SITE/blog/x?a=1`)
- [ ] Un seul saut jusqu'à l'URL finale en https (200)
- [ ] Aucune régression : le site en https répond toujours, le certificat est valide

## Vérification après correction

```bash
curl -sIL -o /dev/null -w '%{num_redirects} saut(s) -> %{url_effective} (%{http_code})\n' http://SITE/blog/
bash scripts/http_checks.sh https://SITE/ /tmp/verif        # §1 : lignes http:// en 301/308, 1 saut
```

## Pièges et retour arrière

- Boucle de redirection derrière un CDN : si Cloudflare est en mode SSL « Flexible » et que l'origine redirige aussi vers https, la page boucle. Passer en « Full (strict) » avec un certificat valide sur l'origine.
- Derrière un proxy, l'origine voit `http` : ne pas ajouter une seconde redirection dans Astro sans `X-Forwarded-Proto`.
- Utiliser 301/308, pas 302 : un 302 ne transfère pas les signaux de classement de façon durable.
- Retour arrière : restaurer l'ancien bloc `server`/`Caddyfile` et recharger ; tester d'abord la configuration (`nginx -t`, `caddy validate`).

## Pour aller plus loin

- https://caddyserver.com/docs/caddyfile/directives/redir : directive `redir` et code `permanent`.
- https://doc.traefik.io/traefik/reference/install-configuration/entrypoints/ : redirections au niveau du point d'entrée.
- https://nginx.org/en/docs/http/ngx_http_rewrite_module.html : directive `return`.
- https://developers.google.com/search/docs/crawling-indexing/site-move-with-url-changes : redirections permanentes et signaux de classement.
