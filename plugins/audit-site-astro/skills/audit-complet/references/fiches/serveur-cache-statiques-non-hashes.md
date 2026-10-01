---
id: serveur-cache-statiques-non-hashes
titre: Fichiers statiques non hashés servis sans cache navigateur
domaine: Serveur / HTTP
severite_type: basse
effort: S
declencheurs:
  - "crawl:asset_sans_cache"
sources:
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching
  - https://docs.astro.build/en/guides/images/
---

# Fichiers statiques non hashés servis sans cache navigateur

> **En une phrase** : un fichier du dossier `public/` (image, police, script) servi avec `max-age=0`, `no-cache` ou sans `Cache-Control` est revalidé ou retéléchargé à chaque visite.

## Pourquoi c'est important

Les fichiers d'`/_astro/` portent un hash dans leur nom : ils peuvent être mis en cache un an. Un fichier de `public/` (`/agent-avatar.png`) garde le même nom d'une version à l'autre : le serveur de votre hébergeur y met souvent `max-age=0`, et le navigateur redemande le fichier à chaque page. Un fichier non hashé ne peut pas être `immutable` (sa mise à jour resterait invisible) ; un cache de quelques heures à un jour est le bon compromis.

## Comment le constater soi-même

```bash
curl -sI https://SITE/chemin-du-fichier.png | grep -i cache-control
```

Problème présent : `max-age=0`, `no-cache`, `no-store`, ou aucune ligne `cache-control`. Corrigé : `public, max-age=86400` (un jour) au moins.

## Correction

1. Préférer `src/assets/` : le fichier reçoit un nom hashé et un cache d'un an automatique (voir `serveur-cache-assets-astro-immutable`).
2. Sinon, un cache court mais non nul au niveau du proxy. nginx :

```nginx
location ~* ^/(?!_astro/).+\.(png|jpe?g|webp|avif|svg|ico|woff2?)$ {
  add_header Cache-Control "public, max-age=86400";
}
```

3. Vercel ou Netlify : une règle `headers` équivalente (`Cache-Control: public, max-age=86400`) sur les extensions concernées.

## Critères d'acceptation

- [ ] La clé `asset_sans_cache` n'apparaît plus dans `issues.json`
- [ ] `cache-control` contient `max-age=3600` ou plus sur les fichiers de `public/`
- [ ] Aucun fichier non hashé en `immutable`

## Vérification après correction

```bash
curl -sI https://SITE/chemin-du-fichier.png | grep -i cache-control
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif
```

## Pièges et retour arrière

- Ne jamais mettre `immutable` sur un fichier non hashé : les visiteurs garderaient l'ancienne version.
- Après un changement du fichier, le cache d'un jour retarde la mise à jour : renommer le fichier ou le passer par `src/assets/` si le délai gêne.
- Retour arrière : retirer la directive `add_header` ou la règle `headers`.

## Pour aller plus loin

- https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching : fonctionnement du cache HTTP.
- https://docs.astro.build/en/guides/images/ : images hashées dans `src/assets/`.
