---
id: secu-code-config-exposes
titre: "Fichiers de code, de build ou de configuration servis publiquement"
domaine: Sécurité
severite_type: moyenne
effort: S
declencheurs:
  - "securite:\\| /(package\\.json|package-lock\\.json|astro\\.config\\.(mjs|ts)|Dockerfile|docker-compose\\.yml) \\| \\d+ \\| \\d+ \\| ❌ EXPOSÉ"
  - "securite:\\| /convex/schema\\.ts \\| \\d+ \\| \\d+ \\| ❌ EXPOSÉ"
  - "securite:\\| /src/pages/index\\.astro \\| \\d+ \\| \\d+ \\| ❌ EXPOSÉ"
  - "securite:\\| /(dist/)?server/entry\\.mjs \\| \\d+ \\| \\d+ \\| ❌ EXPOSÉ"
sources:
  - https://docs.astro.build/en/guides/deploy/
  - https://docs.astro.build/en/guides/integrations-guide/node/
  - https://nginx.org/en/docs/http/ngx_http_core_module.html#root
  - https://caddyserver.com/docs/caddyfile/directives/file_server
---

# Fichiers de code, de build ou de configuration servis publiquement

> **En une phrase** : le serveur web publie la racine du projet (ou le dossier de build serveur) au lieu du seul dossier public, ce qui révèle le code source, la liste des dépendances et parfois des secrets.

## Pourquoi c'est important

`package.json` liste les versions exactes de vos dépendances : un attaquant sait immédiatement quelles failles connues essayer. `astro.config.*`, `convex/schema.ts` ou `src/pages/*.astro` dévoilent l'architecture et les routes cachées ; `dist/server/entry.mjs` est le code du serveur SSR (il peut embarquer des valeurs de configuration). `Dockerfile` et `docker-compose.yml` montrent l'infrastructure et parfois des mots de passe écrits en dur. C'est rarement un secret en soi, mais c'est le signe que **la racine du site est mal configurée** : si ces fichiers sortent, `.env` sort probablement aussi (voir `secu-fichiers-caches-exposes`).

## Comment le constater soi-même

```bash
for p in /package.json /package-lock.json /astro.config.mjs /astro.config.ts /convex/schema.ts /src/pages/index.astro /dist/server/entry.mjs /server/entry.mjs /Dockerfile /docker-compose.yml; do
  printf '%s -> ' "$p"; curl -s -o /dev/null -w '%{http_code} %{content_type}\n' "https://exemple.fr$p"
done
```

Présent : 200 avec un type `application/json`, `text/plain`, `text/javascript` ou `application/octet-stream` et le vrai contenu. Corrigé : 404 (une page HTML « 404 » servie avec le code 200 n'est pas une fuite mais est un défaut SEO, voir les fiches Serveur).

## Correction

1. **Pointer le serveur web sur le bon dossier**.
   - Astro en rendu serveur (`@astrojs/node`, mode `standalone`) : ne servez rien depuis le disque. Le proxy transmet tout au processus Node.

     ```nginx
     server {
         server_name exemple.fr;
         location / {
             proxy_pass http://127.0.0.1:4321;
             proxy_set_header Host $host;
             proxy_set_header X-Forwarded-Proto $scheme;
             proxy_set_header X-Forwarded-Host $host;
         }
     }
     ```

     ```caddy
     exemple.fr {
         reverse_proxy 127.0.0.1:4321
     }
     ```
   - Site statique : le `root` (nginx) ou `root *` (Caddy) doit être `dist/`, jamais le dépôt.

     ```nginx
     root /var/www/monsite/dist;
     ```

     ```caddy
     exemple.fr {
         root * /var/www/monsite/dist
         file_server
     }
     ```
2. **Ne rien déployer d'autre que le résultat du build** : copiez `dist/` (et pas le dépôt entier) sur le serveur, ou utilisez une image Docker multi-étapes qui ne garde que `dist/`, `package.json` de production et `node_modules` de production. Ajoutez un `.dockerignore` (`.git`, `.env*`, `Dockerfile`, `docker-compose.yml`).
3. **Filet de sécurité** au serveur web, si le dépôt doit cohabiter avec le site (déconseillé) :

   ```nginx
   location ~* ^/(package(-lock)?\.json|astro\.config\..*|Dockerfile|docker-compose\.ya?ml|convex/|src/|server/|dist/server/) { return 404; }
   ```

   ```caddy
   @interne path /package.json /package-lock.json /astro.config.* /Dockerfile /docker-compose.y*ml /convex/* /src/* /server/* /dist/server/*
   respond @interne 404
   ```
4. Vérifiez qu'aucun de ces fichiers n'est copié dans `public/`.
5. Si `docker-compose.yml` ou `entry.mjs` ont été lus : contrôlez qu'ils ne contiennent aucun mot de passe en clair ; sinon faites-les tourner (`secu-secret-dans-js-client`, section « Rotation »).

## Critères d'acceptation

- [ ] Tous les chemins listés répondent 404.
- [ ] Le serveur web ne sert que `dist/` (statique) ou relaie vers Node (SSR).
- [ ] Aucun secret écrit en dur dans `docker-compose.yml`, `Dockerfile`, `entry.mjs` (sinon rotation faite).
- [ ] Aucune régression : pages et `/_astro/*` en 200.

## Vérification après correction

```bash
bash scripts/security_probe.sh https://exemple.fr/ /tmp/verif-secu
grep '❌' /tmp/verif-secu/security-probe.md || echo "aucun fichier exposé"
```

## Pièges et retour arrière

- En SSR, `dist/server/` contient le code serveur et `dist/client/` les fichiers publics : ne mélangez pas les deux dans un même `root`.
- Un `root` corrigé peut casser des chemins (`/_astro/`) : testez la page d'accueil et une page avec image avant de recharger en production.
- Retour arrière : restaurez la sauvegarde de la configuration du serveur (`cp site.bak site`) puis `nginx -t && systemctl reload nginx`.

## Pour aller plus loin

- Astro, déploiement : ce qu'il faut publier (`dist/`).
- Adaptateur Node : modes `standalone` et `middleware`.
- nginx `root` : dossier servi.
- Caddy `file_server` : dossier servi et options.
