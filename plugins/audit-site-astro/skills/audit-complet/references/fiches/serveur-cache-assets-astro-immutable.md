---
id: serveur-cache-assets-astro-immutable
titre: Fichiers /_astro/ (hashés) sans cache long navigateur
domaine: Serveur / HTTP
severite_type: moyenne
effort: S
declencheurs:
  - "http:asset hashé Astro : viser max-age=31536000"
  - "http:pas de cache navigateur"
  - "lighthouse:uses-long-cache-ttl"
  - "lighthouse:cache-insight"
  - "lighthouse:règles de cache efficaces|durées de mise en cache efficaces"
sources:
  - https://docs.astro.build/en/guides/integrations-guide/node/
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control
  - https://nginx.org/en/docs/http/ngx_http_headers_module.html
  - https://caddyserver.com/docs/caddyfile/directives/header
---

# Fichiers /_astro/ (hashés) sans cache long navigateur

> **En une phrase** : les CSS, JS, polices et images générés par Astro portent un hash dans leur nom mais le serveur ne les fait pas garder au navigateur ; chaque visite de retour les retélécharge pour rien.

## Pourquoi c'est important

Les fichiers de `/_astro/` changent de nom dès que leur contenu change. On peut donc les mettre en cache pour un an sans risque. Sans en-tête adapté, un visiteur qui revient (ou qui change de page) revalide ou retélécharge des centaines de Ko : pages plus lentes, plus de requêtes, plus de charge serveur. Lighthouse le signale par « Utiliser des règles de cache efficaces sur les éléments statiques » ou l'insight « Utiliser des durées de mise en cache efficaces ».

L'adaptateur `@astrojs/node` envoie déjà `Cache-Control: public, max-age=31536000, immutable` pour `/_astro/`. Si le constat apparaît, c'est presque toujours que **le proxy ou le CDN écrase cet en-tête**, ou que l'hébergement statique n'applique pas de règle.

## Comment le constater soi-même

```bash
for p in $(curl -s https://SITE/ | grep -oE '/_astro/[^"]+\.(css|js|woff2|webp|avif)' | sort -u | head -5); do
  printf '%s : ' "$p"; curl -sI "https://SITE$p" | grep -i '^cache-control' || echo 'cache-control ABSENT'
done
```

Problème présent : `cache-control` absent, `max-age=0`, `no-cache` ou une durée courte (`max-age=3600`). Corrigé : `public, max-age=31536000, immutable`.

## Correction

1. Repérer où l'en-tête est perdu : appeler directement Node (`curl -sI http://127.0.0.1:4321/_astro/<fichier>`). S'il porte `immutable` mais pas la réponse publique, le proxy ou le CDN l'écrase. Sinon le site est hébergé en statique et la règle manque.

2. **nginx** devant Node : ne pas ajouter un second `Cache-Control` (deux lignes = comportement imprévisible). Laisser passer celui de Node, ou le remplacer proprement :

```nginx
location /_astro/ {
    proxy_pass http://127.0.0.1:4321;
    proxy_hide_header Cache-Control;
    add_header Cache-Control "public, max-age=31536000, immutable" always;
}
```

Ne pas mélanger avec `expires 1y;` dans le même bloc : `expires` écrit aussi un `Cache-Control`.

3. **Caddy** :

```caddy
exemple.fr {
	encode zstd gzip
	handle /_astro/* {
		reverse_proxy 127.0.0.1:4321 {
			header_down Cache-Control "public, max-age=31536000, immutable"
		}
	}
	handle {
		reverse_proxy 127.0.0.1:4321
	}
}
```

4. **Traefik** : ne modifie pas `Cache-Control` par défaut. Si un middleware `headers` le fait (`customResponseHeaders`), le restreindre au chemin `/_astro/` via un routeur dédié (règle `PathPrefix` sur `/_astro/`) ou le retirer.

5. **Hébergement statique** (Netlify, Cloudflare Pages / Workers static assets) : créer `public/_headers` (copié tel quel dans le build) :

```
/_astro/*
  Cache-Control: public, max-age=31536000, immutable
```

6. **Vercel** : ajouter dans `vercel.json` (les fichiers hashés de `/_astro/` sont normalement déjà servis en cache long ; à vérifier avec le `curl` ci-dessus avant d'ajouter) :

```json
{
  "headers": [
    {
      "source": "/_astro/(.*)",
      "headers": [{ "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }]
    }
  ]
}
```

7. **Fichiers de `public/`** (non hashés : `favicon`, `robots.txt`, images copiées telles quelles) : ne **pas** leur donner `immutable`, car leur URL ne change pas quand le contenu change. Viser `public, max-age=86400` (1 jour) ou un renommage versionné (`logo.v2.svg`).

## Critères d'acceptation

- [ ] Tous les fichiers de `/_astro/` répondent `Cache-Control: public, max-age=31536000, immutable` (une seule ligne `Cache-Control`)
- [ ] Le HTML n'a **pas** reçu cette règle (il doit rester revalidable, voir la fiche du cache HTML)
- [ ] Les fichiers de `public/` ont un cache court ou versionné
- [ ] Lighthouse ne liste plus les fichiers `/_astro/` dans les règles de cache

## Vérification après correction

```bash
curl -sI https://SITE/_astro/<fichier-hashé> | grep -i cache-control
bash scripts/http_checks.sh https://SITE/ /tmp/verif   # §4 : plus de « viser max-age=31536000 »
```

## Pièges et retour arrière

- Ne jamais appliquer `immutable` à `/` ni à des URL non hashées : les visiteurs garderaient une vieille version pendant un an.
- Après un déploiement, si le HTML est mis en cache trop longtemps, il peut référencer d'anciens fichiers hashés supprimés du serveur : conserver l'ancien build quelques minutes (voir la fiche sur les assets en erreur).
- Retour arrière : retirer le bloc `location` / `handle` ou le fichier `_headers` et recharger le service.

## Pour aller plus loin

- https://docs.astro.build/en/guides/integrations-guide/node/ : indique que les fichiers de `_astro/` portent un hash et peuvent recevoir un cache long.
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control : directives `immutable`, `max-age`, `no-cache`.
- https://nginx.org/en/docs/http/ngx_http_headers_module.html : `add_header` et `expires` de nginx.
- https://caddyserver.com/docs/caddyfile/directives/header : manipulation des en-têtes dans Caddy.
