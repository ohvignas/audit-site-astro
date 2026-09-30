---
id: serveur-http2-http3
titre: Site servi en HTTP/1.1 (pas de HTTP/2) ou sans HTTP/3 annoncé
domaine: Serveur / HTTP
severite_type: basse
effort: S
declencheurs:
  - "http:\\| normale #\\d.*\\| 1(\\.1)? \\|\\s*$"
  - "http:HTTP/3 \\(alt-svc\\) \\| non annoncé"
  - "lighthouse:modern-http-insight|HTTP récent"
sources:
  - https://nginx.org/en/docs/http/ngx_http_v2_module.html
  - https://nginx.org/en/docs/quic.html
  - https://caddyserver.com/docs/caddyfile/options
  - https://doc.traefik.io/traefik/reference/install-configuration/entrypoints/
  - https://developer.chrome.com/docs/performance/insights/modern-http
---

# Site servi en HTTP/1.1 (pas de HTTP/2) ou sans HTTP/3 annoncé

> **En une phrase** : le serveur répond en HTTP/1.1, qui télécharge les fichiers presque un par un ; HTTP/2 (et HTTP/3) les charge en parallèle sur une seule connexion, ce qui accélère surtout les pages riches en fichiers.

## Pourquoi c'est important

Avec HTTP/1.1, un navigateur ouvre environ six connexions par hôte : une page avec 30 fichiers CSS, JS, polices et images attend son tour. HTTP/2 multiplexe tout sur une connexion ; HTTP/3 (QUIC, sur UDP) réduit encore la latence sur mobile et réseau instable. Lighthouse signale l'insight « HTTP récent » quand des requêtes passent par un ancien protocole. C'est un gain modéré mais quasi gratuit, à traiter après la compression et le cache. Le HTTP/3 est optionnel : la ligne `HTTP/3 (alt-svc) non annoncé` du rapport n'est qu'une information.

Le serveur Node d'Astro (`@astrojs/node`, mode standalone) parle HTTP/1.1. HTTP/2 et HTTP/3 se terminent donc **au proxy ou au CDN**, jamais dans Astro.

## Comment le constater soi-même

```bash
curl -sI --http2 https://SITE/ -o /dev/null -w 'protocole : HTTP/%{http_version}\n'   # attendu : 2
curl -sI https://SITE/ | grep -i '^alt-svc'                                          # attendu (HTTP/3) : h3=":443"
curl -sI --http3 https://SITE/ -o /dev/null -w 'HTTP/%{http_version}\n' 2>&1 | head -1   # seulement si curl est compilé avec HTTP/3
```

Problème présent : `HTTP/1.1`. Corrigé : `HTTP/2`. `alt-svc` n'apparaît que si HTTP/3 est actif.

## Correction

1. **nginx ≥ 1.25.1** : activer HTTP/2 avec la directive `http2 on;` (l'ancienne syntaxe `listen 443 ssl http2;` est dépréciée). Sur une version plus ancienne, utiliser l'ancienne syntaxe. Dans le bloc `server` du site :

```nginx
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name exemple.fr;
    ssl_certificate     /etc/letsencrypt/live/exemple.fr/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/exemple.fr/privkey.pem;
    # … proxy_pass vers Node
}
```

2. **nginx, HTTP/3 (optionnel)** : nécessite un nginx compilé avec `--with-http_v3_module` et une bibliothèque TLS compatible QUIC. Ouvrir le port **UDP 443** dans le pare-feu, puis :

```nginx
server {
    listen 443 quic reuseport;
    listen 443 ssl;
    listen [::]:443 quic reuseport;
    listen [::]:443 ssl;
    http2 on;
    http3 on;
    add_header Alt-Svc 'h3=":443"; ma=86400' always;
    # … reste de la configuration TLS et proxy
}
```

3. **Caddy** : HTTP/2 et HTTP/3 sont actifs par défaut, et `Alt-Svc` est ajouté automatiquement. Si ce n'est pas le cas, chercher une option globale `servers { protocols h1 }` dans le `Caddyfile` (à retirer) et vérifier que le port UDP 443 est ouvert (`-p 443:443/udp` en Docker).

4. **Traefik** : HTTP/2 est actif sur les points d'entrée TLS. Pour HTTP/3, l'activer sur le point d'entrée TCP (`traefik.yml`) et publier le port UDP :

```yaml
entryPoints:
  websecure:
    address: ":443"
    http3: {}
```

Avec Docker, ajouter `- "443:443/udp"` aux ports du conteneur Traefik.

5. **Vercel / Netlify / Cloudflare** : HTTP/2 et HTTP/3 sont actifs par défaut. Cloudflare : réglage « HTTP/3 (with QUIC) » dans Réseau. Si le site reste en HTTP/1.1, un proxy intermédiaire non prévu termine la connexion : chercher qui répond (`curl -sI` : en-têtes `server`, `via`).

6. **HTTP/1.1 malgré une configuration correcte** : le client de test peut ne pas négocier HTTP/2 (certaines versions de curl sans nghttp2, pare-feu applicatif, ancien mandataire d'entreprise). Refaire le test avec `curl --http2` et un navigateur (onglet Réseau, colonne Protocole : `h2` ou `h3`).

## Critères d'acceptation

- [ ] `curl --http2 -sI https://SITE/` répond en HTTP/2
- [ ] (optionnel) `alt-svc: h3=":443"` présent et HTTP/3 fonctionnel, port UDP 443 ouvert
- [ ] Lighthouse n'affiche plus l'insight « HTTP récent » pour les ressources du site
- [ ] Aucune régression : site accessible en https, y compris pour les clients qui ne supportent que HTTP/1.1

## Vérification après correction

```bash
curl -sI --http2 https://SITE/ -o /dev/null -w 'HTTP/%{http_version}\n'
bash scripts/http_checks.sh https://SITE/ /tmp/verif       # §2 : colonne HTTP = 2, §3 : ligne alt-svc
```

## Pièges et retour arrière

- HTTP/3 annoncé (`Alt-Svc`) alors que le port UDP 443 est fermé : le navigateur essaie, échoue, puis retombe sur HTTP/2 avec un léger retard. N'annoncer `Alt-Svc` qu'une fois UDP 443 ouvert.
- Ne pas exposer directement le port 4321 de Node : il reste en HTTP/1.1 et sans TLS.
- Retour arrière : retirer `http2 on;` / `http3 on;` / `Alt-Svc` puis `nginx -t && systemctl reload nginx`.

## Pour aller plus loin

- https://nginx.org/en/docs/http/ngx_http_v2_module.html : directive `http2 on;` (nginx 1.25.1 et plus).
- https://nginx.org/en/docs/quic.html : HTTP/3 et QUIC dans nginx.
- https://caddyserver.com/docs/caddyfile/options : options globales de protocoles de Caddy.
- https://doc.traefik.io/traefik/reference/install-configuration/entrypoints/ : activer HTTP/3 sur un point d'entrée.
- https://developer.chrome.com/docs/performance/insights/modern-http : insight Lighthouse « HTTP récent ».
