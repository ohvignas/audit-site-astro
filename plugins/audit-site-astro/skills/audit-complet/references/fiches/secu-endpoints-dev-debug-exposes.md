---
id: secu-endpoints-dev-debug-exposes
titre: "Outils de développement, pages de debug et restes WordPress accessibles en production"
domaine: Sécurité
severite_type: haute
effort: S
declencheurs:
  - "securite:\\| /@vite/client \\| \\d+ \\| \\d+ \\| ❌ EXPOSÉ"
  - "securite:\\| /__vite_ping \\| 200 \\| \\d+ \\| ⚠️"
  - "securite:\\| /(phpinfo\\.php|server-status|wp-content/debug\\.log) \\| \\d+ \\| \\d+ \\| ❌ EXPOSÉ"
  - "securite:\\| /(wp-login\\.php|xmlrpc\\.php) \\| \\d+ \\| \\d+ \\| ❌ EXPOSÉ"
sources:
  - https://docs.astro.build/en/reference/cli-reference/
  - https://docs.astro.build/en/guides/deploy/
  - https://nginx.org/en/docs/http/ngx_http_access_module.html
  - https://caddyserver.com/docs/caddyfile/directives/respond
---

# Outils de développement, pages de debug et restes WordPress accessibles en production

> **En une phrase** : le serveur de développement (Vite/Astro) ou des pages techniques (`phpinfo`, `server-status`, journaux WordPress) répondent sur le site public, ce qui ouvre des informations et des fonctions qui ne devraient exister qu'en local.

## Pourquoi c'est important

- **`/@vite/client` ou `/__vite_ping` qui répondent** : c'est le signe que `astro dev` (serveur de développement) tourne en production. Ce serveur n'est pas conçu pour Internet : il expose le code source, permet de lire des fichiers du projet, n'a aucune optimisation et casse les performances.
- **`phpinfo.php`, `server-status`** : révèlent versions, chemins, modules et connexions en cours.
- **`wp-content/debug.log`** : peut contenir des chemins, des requêtes SQL, parfois des données de visiteurs.
- **`wp-login.php`, `xmlrpc.php`** (restes d'un ancien WordPress après migration vers Astro) : cibles de robots de force brute ; sans WordPress derrière, ces URL n'ont aucune raison de répondre.

## Comment le constater soi-même

```bash
for p in /@vite/client /__vite_ping /phpinfo.php /server-status /wp-content/debug.log /wp-login.php /xmlrpc.php; do
  printf '%s -> ' "$p"; curl -s -o /dev/null -w '%{http_code} %{content_type}\n' "https://exemple.fr$p"
done
# Sur le serveur : quel processus écoute ?
ps aux | grep -E 'astro (dev|preview)|vite' | grep -v grep
```

Présent : 200 avec du JavaScript (`import.meta.hot`) pour `/@vite/client`, `PHP Version` pour phpinfo. Corrigé : 404.

## Correction

1. **Serveur de développement en production** : faites-le arrêter (`systemctl stop`, `pm2 delete`, `docker compose down`, sur le serveur de production : à faire par l'humain, ou avec son accord explicite) et remplacez la commande de démarrage par le build de production.

   ```bash
   npm run build                       # produit dist/
   node ./dist/server/entry.mjs        # Astro SSR avec @astrojs/node (mode standalone)
   ```

   Pour un site statique : servez `dist/` avec nginx/Caddy (`astro preview` est aussi réservé aux tests locaux). Vérifiez le `CMD` du `Dockerfile` et la commande du service systemd / PM2 : ils ne doivent pas contenir `dev` ni `preview`.
2. **Bloquer les URL techniques héritées** (WordPress, PHP) qui ne servent plus.

   nginx :

   ```nginx
   location ~* ^/(wp-login\.php|xmlrpc\.php|wp-admin|wp-content/debug\.log|phpinfo\.php|server-status)(/|$) { return 404; }
   location ~ ^/(@vite|__vite) { return 404; }
   ```

   Caddy :

   ```caddy
   @heritage path /wp-login.php /xmlrpc.php /wp-admin/* /wp-content/debug.log /phpinfo.php /server-status /@vite/* /__vite*
   respond @heritage 404
   ```

   Si un ancien site WordPress a été supprimé, mieux vaut aussi laisser ces URL en 404 (plutôt qu'une redirection) et retirer les anciens fichiers `.php`, `wp-*` du serveur.
3. Si le serveur Apache `server-status` est réellement utilisé, restreignez-le à `127.0.0.1` (`Require local`) et ne l'exposez pas via le proxy.
4. **Regarder les journaux** pour voir si ces URL ont été appelées avant correction (`grep -E 'wp-login|xmlrpc|@vite' /var/log/nginx/access.log | tail`). Des centaines de tentatives sur `wp-login.php` sont normales pour tout site public : elles sont sans danger quand l'URL répond 404.

## Critères d'acceptation

- [ ] Aucun processus `astro dev` / `vite` en production (`ps aux`).
- [ ] Les 7 URL répondent 404.
- [ ] Le service démarre avec le build de production et redémarre seul après un reboot.
- [ ] Aucune régression : pages, images et formulaires fonctionnent.

## Vérification après correction

```bash
bash scripts/security_probe.sh https://exemple.fr/ /tmp/verif-secu
grep -E 'vite|php|wp-|xmlrpc|server-status' /tmp/verif-secu/security-probe.md
```

## Pièges et retour arrière

- Un `Dockerfile` qui lance `npm run dev` fonctionne « par hasard » : tests et déploiement doivent utiliser le build.
- Si le site utilise encore WordPress derrière un autre chemin (`/blog`), ne bloquez pas `wp-login.php` sans vérifier ; protégez-le plutôt par IP ou authentification.
- Retour arrière : supprimer les blocs ajoutés puis recharger le serveur ; le serveur de développement ne doit pas être remis en production.

## Pour aller plus loin

- Astro, référence CLI : différence entre `dev`, `build` et `preview`.
- Astro, guide de déploiement : servir le résultat du build.
- nginx `ngx_http_access_module` : restreindre par IP.
- Caddy `respond` : répondre un code fixe.
