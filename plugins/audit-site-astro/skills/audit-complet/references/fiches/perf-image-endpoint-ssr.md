---
id: perf-image-endpoint-ssr
titre: Images transformées à chaque requête par /_image (rendu à la demande sans cache)
domaine: Performance
severite_type: moyenne
effort: M
declencheurs:
  - "code:Rendu à la demande \\+ <Image>"
  - "http:transformée à chaque requête"
sources:
  - https://docs.astro.build/en/guides/images/
  - https://docs.astro.build/en/reference/configuration-reference/#imageendpoint
  - https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_cache_path
---

# Images transformées à chaque requête par /_image (rendu à la demande sans cache)

> **En une phrase** : sur les pages rendues à la demande, chaque image passe par l'endpoint `/_image` et peut être redimensionnée par le serveur à chaque visite, ce qui ralentit le premier octet de l'image et charge le processeur.

## Pourquoi c'est important

Pour une page prérendue (générée au build), les images optimisées sont des fichiers statiques dans `/_astro/`. Pour une page en `prerender = false` (SSR), Astro sert les images via l'endpoint `/_image` (route configurable avec `image.endpoint`), qui applique `sharp` à la demande. Sans cache devant, une page avec 12 images peut déclencher 12 transformations à chaque visiteur : le TTFB des images grimpe (souvent 300 ms à plusieurs secondes), le LCP suit, et un pic de trafic sature le CPU. L'outil mesure cet endpoint deux fois de suite ; si les deux appels dépassent 0,3 s, rien ne le met en cache.

## Comment le constater soi-même

```bash
# Récupérer une URL /_image de la page, puis mesurer deux appels de suite
U=$(curl -s https://SITE/ | grep -oE '/_image\?[^" ]+' | sed 's/&amp;/\&/g' | head -1)
for i in 1 2; do curl -s -o /dev/null -w "appel $i : %{time_starttransfer}s\n" "https://SITE$U"; done
curl -sI "https://SITE$U" | grep -iE 'cache-control|etag|x-cache|age'
```

Problème présent : les deux appels dépassent 0,3 s (et aucun en-tête `age` ou `x-cache`). Corrigé : le 2e appel est nettement plus rapide (< 0,1 s) ou l'image est un fichier statique.

## Correction

Ordre de préférence :

1. **Prérendre les pages dont le contenu ne change pas à chaque visite** : `export const prerender = true;` en tête du fichier de page (avec un site en `output: 'server'`), ou passer le site en statique avec quelques routes dynamiques ciblées (`prerender = false` seulement là où c'est nécessaire). Les images sont alors générées au build.
2. **Mettre `/_image` en cache au proxy**. Les réponses portent déjà un `Cache-Control` public. Exemple nginx :

```nginx
# Dans le bloc http { } (par exemple /etc/nginx/conf.d/astro-cache.conf)
proxy_cache_path /var/cache/nginx/astro_img levels=1:2 keys_zone=astro_img:10m max_size=1g inactive=30d use_temp_path=off;

# Dans le bloc server { } du site
location /_image {
    proxy_pass http://127.0.0.1:4321;
    proxy_set_header Host $host;
    proxy_cache astro_img;
    proxy_cache_key "$scheme$host$request_uri";
    proxy_cache_valid 200 30d;
    proxy_cache_lock on;
    add_header X-Cache-Status $upstream_cache_status always;
}
```

Créer le dossier (`sudo mkdir -p /var/cache/nginx/astro_img && sudo chown www-data /var/cache/nginx/astro_img`, utilisateur à adapter), puis `sudo nginx -t && sudo systemctl reload nginx`.
3. **Avec un CDN** (Cloudflare, Bunny, Fastly…) devant le site : créer une règle de cache pour le chemin `/_image*`, avec une durée longue et la chaîne de requête dans la clé de cache.
4. **Caddy** ne met pas en cache par défaut : passer par un CDN, ou ajouter un module de cache (plugin à compiler), ou prérendre.
5. **Réduire le travail** : moins de tailles générées (`image.breakpoints` réduit, voir `perf-images-responsives`) et des sources déjà raisonnables (pas d'originaux de 6000 px).
6. Vérifier que `sharp` est installé en production (`npm ls sharp`) : sans lui Astro retombe sur un service bien plus lent ou échoue.

## Critères d'acceptation

- [ ] Le 2e appel d'une URL `/_image` répond en moins de 0,1 s (ou ces images sont des fichiers statiques `/_astro/`)
- [ ] L'en-tête `x-cache-status: HIT` (ou équivalent CDN) apparaît au 2e appel
- [ ] Charge CPU du serveur stable pendant un parcours de plusieurs pages
- [ ] Les images s'affichent toujours à la bonne taille

## Vérification après correction

```bash
for i in 1 2 3; do curl -s -o /dev/null -w "%{time_starttransfer}s\n" "https://SITE$U"; done
bash scripts/http_checks.sh https://SITE/ /tmp/verif    # section 4 bis, colonne Verdict
```

## Pièges et retour arrière

- Ne pas mettre en cache des pages HTML personnalisées par erreur : la règle ne doit viser que `/_image`.
- Un cache disque non purgé grossit : `max_size` et `inactive` le bornent.
- Retour arrière : retirer le bloc `location /_image` et recharger nginx ; supprimer `prerender = true` d'une page.

## Pour aller plus loin

- https://docs.astro.build/en/guides/images/ : fonctionnement des images en rendu à la demande.
- https://docs.astro.build/en/reference/configuration-reference/#imageendpoint : `image.endpoint`.
- https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_cache_path : cache de proxy nginx.
