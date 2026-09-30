---
id: serveur-compression-texte-absente
titre: HTML, CSS ou JavaScript servis sans compression (ni brotli ni gzip)
domaine: Serveur / HTTP
severite_type: haute
effort: S
declencheurs:
  - "http:Compression HTML \\| aucune"
  - "http:non compressé"
  - "lighthouse:uses-text-compression"
  - "lighthouse:Activez la compression de texte"
sources:
  - https://docs.astro.build/en/guides/integrations-guide/node/
  - https://nginx.org/en/docs/http/ngx_http_gzip_module.html
  - https://caddyserver.com/docs/caddyfile/directives/encode
  - https://doc.traefik.io/traefik/reference/routing-configuration/http/middlewares/compress/
  - https://developer.chrome.com/docs/lighthouse/performance/uses-text-compression
---

# HTML, CSS ou JavaScript servis sans compression (ni brotli ni gzip)

> **En une phrase** : le serveur envoie les fichiers texte en clair ; ils pèsent 3 à 5 fois plus lourd que nécessaire, ce qui retarde l'affichage surtout sur mobile.

## Pourquoi c'est important

Le texte (HTML, CSS, JavaScript, JSON, SVG) se compresse très bien : gzip réduit typiquement de 65 à 80 %, brotli et zstd font un peu mieux. Sans compression, un fichier CSS de 200 Ko et un bundle JS de 400 Ko sont téléchargés en entier. Lighthouse chiffre ce gain (en Kio et en ms) et il pèse directement sur le FCP et le LCP. C'est souvent la correction la plus rentable et la moins risquée.

Avec Astro en rendu serveur (`@astrojs/node` en mode standalone), la documentation de l'adaptateur ne prévoit aucune compression : elle se fait donc **devant** Node, dans le proxy (nginx, Caddy, Traefik) ou au CDN. Sur Vercel, Netlify et Cloudflare elle est normalement automatique.

## Comment le constater soi-même

```bash
# En-tête de compression du HTML puis d'un fichier CSS et d'un fichier JS de la page
curl -sI -H 'Accept-Encoding: br, gzip' https://SITE/ | grep -i content-encoding
for p in $(curl -s https://SITE/ | grep -oE '/_astro/[^"]+\.(css|js)' | sort -u | head -4); do
  printf '%s : ' "$p"
  curl -s -o /dev/null -D - -H 'Accept-Encoding: br, gzip' "https://SITE$p" | grep -i '^content-encoding' || echo 'AUCUNE COMPRESSION'
done
# Poids réellement transféré, sans puis avec compression
curl -s -o /dev/null -w 'brut : %{size_download} o\n' https://SITE/
curl -s -o /dev/null -H 'Accept-Encoding: gzip' -w 'gzip : %{size_download} o\n' https://SITE/
```

Problème présent : aucune ligne `content-encoding`, et les deux tailles sont identiques. Corrigé : `content-encoding: br` (ou `gzip`, `zstd`) et une taille très inférieure.

## Correction

1. Repérer qui répond devant Node : `curl -sI https://SITE/ | grep -iE '^(server|via|x-powered-by|cf-ray|x-vercel-id|x-nf-request-id)'`. Appliquer ensuite **une seule** des variantes ci-dessous (ne pas compresser à deux niveaux).

2. **nginx** (SSR Node derrière nginx). Dans `/etc/nginx/conf.d/compression.conf` (contexte `http`), puis `nginx -t && systemctl reload nginx` :

```nginx
gzip on;
gzip_vary on;
gzip_comp_level 5;
gzip_min_length 1024;
gzip_proxied any;
gzip_types text/plain text/css text/javascript application/javascript application/json
           application/xml application/rss+xml application/manifest+json image/svg+xml
           font/ttf font/otf application/wasm;
```

`text/html` est toujours compressé. Lister **à la fois** `text/javascript` et `application/javascript` : selon la version de nginx et du fichier `mime.types`, les `.js` sortent avec l'un ou l'autre. Pour brotli il faut le module tiers `ngx_brotli` (non inclus par défaut) : `brotli on; brotli_comp_level 5; brotli_types <mêmes types>;`. Sinon gzip suffit largement.

3. **Caddy** (dans le bloc du site du `Caddyfile`, puis `caddy reload --config /etc/caddy/Caddyfile`) :

```caddy
exemple.fr {
	encode zstd gzip
	reverse_proxy 127.0.0.1:4321
}
```

Caddy compresse par défaut les types texte courants au-delà de 512 octets. Brotli n'est pas fourni par le module standard `encode` de Caddy (zstd et gzip le sont).

4. **Traefik v3** : déclarer le middleware `compress` et l'attacher au routeur. Fichier dynamique :

```yaml
http:
  middlewares:
    compress:
      compress: {}
  routers:
    astro:
      rule: Host(`exemple.fr`)
      entryPoints: [websecure]
      middlewares: [compress]
      service: astro
      tls:
        certResolver: letsencrypt
  services:
    astro:
      loadBalancer:
        servers:
          - url: http://127.0.0.1:4321
```

Avec des labels Docker : `traefik.http.middlewares.compress.compress=true` puis `traefik.http.routers.astro.middlewares=compress`. Par défaut Traefik accepte gzip, br et zstd et ne compresse pas sous 1024 octets.

5. **Vercel / Netlify / Cloudflare** : la compression est automatique pour les types texte. Si elle manque, chercher un proxy intermédiaire qui retire `Accept-Encoding`, un `Content-Type` erroné (ex. `application/octet-stream`) ou une règle personnalisée qui désactive la compression.

6. Vérifier que le HTML, le CSS et le JS sortent compressés (voir « Vérification »).

## Critères d'acceptation

- [ ] `content-encoding: br`, `gzip` ou `zstd` sur le HTML, sur au moins un `.css` et un `.js` de `/_astro/`
- [ ] `Vary: Accept-Encoding` présent sur les réponses compressées
- [ ] Les images (`.webp`, `.avif`, `.jpg`) et polices `.woff2` ne sont **pas** recompressées (déjà compressées)
- [ ] Aucune régression : pages en 200, rendu identique, Lighthouse n'affiche plus « Activez la compression de texte »

## Vérification après correction

```bash
curl -sI -H 'Accept-Encoding: br, gzip' https://SITE/ | grep -iE 'content-encoding|vary'
bash scripts/http_checks.sh https://SITE/ /tmp/verif   # ligne « Compression HTML » en ✅, plus de « non compressé »
```

Relancer ensuite `lighthouse_run.sh` : l'audit `uses-text-compression` doit disparaître.

## Pièges et retour arrière

- Ne pas activer la compression deux fois (CDN et proxy) : le second niveau ne recompresse pas mais complique le diagnostic.
- Un CDN devant nginx ajoute un en-tête `Via` ; sans `gzip_proxied any`, nginx refuse alors de compresser.
- Un niveau de compression trop haut (9 en gzip) coûte du CPU pour un gain minime : rester à 4-6.
- Retour arrière : retirer le fichier `compression.conf` (ou la ligne `encode` / le middleware) puis recharger le service.

## Pour aller plus loin

- https://docs.astro.build/en/guides/integrations-guide/node/ : fonctionnement standalone de l'adaptateur Node et ressources statiques.
- https://nginx.org/en/docs/http/ngx_http_gzip_module.html : directives gzip de nginx et valeurs par défaut.
- https://caddyserver.com/docs/caddyfile/directives/encode : encodages pris en charge et seuils de Caddy.
- https://doc.traefik.io/traefik/reference/routing-configuration/http/middlewares/compress/ : algorithmes et options du middleware `compress`.
- https://developer.chrome.com/docs/lighthouse/performance/uses-text-compression : explication de l'audit Lighthouse.
