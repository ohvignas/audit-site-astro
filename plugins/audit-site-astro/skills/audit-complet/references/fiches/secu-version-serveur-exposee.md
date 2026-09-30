---
id: secu-version-serveur-exposee
titre: "Version du serveur ou du framework visible dans les en-têtes (Server, X-Powered-By)"
domaine: Sécurité
severite_type: basse
effort: S
declencheurs:
  - "http:\\| Server / X-Powered-By \\|.*⚠️ version exposée"
sources:
  - https://nginx.org/en/docs/http/ngx_http_core_module.html#server_tokens
  - https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_hide_header
  - https://caddyserver.com/docs/caddyfile/directives/header
  - https://expressjs.com/en/advanced/best-practice-security.html
---

# Version du serveur ou du framework visible dans les en-têtes (Server, X-Powered-By)

> **En une phrase** : les en-têtes de réponse annoncent le logiciel et sa version exacte (par exemple `nginx/1.18.0`, `X-Powered-By: PHP/7.4`), ce qui aide un attaquant à choisir la faille à essayer.

## Pourquoi c'est important

Ce n'est pas une faille en soi : masquer une version ne corrige rien. Mais les robots d'attaque trient les cibles par version, et afficher une version ancienne signale un serveur non mis à jour. Ce constat est donc surtout un **signal d'hygiène** : (1) cachez la version (quelques minutes de travail), (2) profitez-en pour vérifier que le logiciel est à jour, car c'est la mise à jour qui protège vraiment. Gravité basse.

## Comment le constater soi-même

```bash
curl -sI https://exemple.fr/ | grep -iE '^(server|x-powered-by|x-aspnet-version|x-generator):'
```

Présent : `server: nginx/1.24.0`, `x-powered-by: Express`, `x-powered-by: PHP/8.1.2`. Acceptable : `server: nginx` ou `server: Caddy` sans numéro, et pas de `x-powered-by`.

## Correction

1. **nginx** : supprimer le numéro de version (dans le contexte `http` de `/etc/nginx/nginx.conf`) et ne pas relayer les en-têtes du serveur d'application.

   ```nginx
   server_tokens off;
   # dans le bloc server ou location qui fait le proxy_pass :
   proxy_hide_header X-Powered-By;
   proxy_hide_header Server;
   ```

   `server_tokens off` supprime le numéro mais laisse `Server: nginx`. Pour retirer complètement l'en-tête il faut le module tiers `headers-more` (directive `more_clear_headers Server;`), à n'installer que si nécessaire.
2. **Caddy** : Caddy n'affiche pas de numéro (`Server: Caddy`). Pour retirer aussi l'en-tête et celui de l'application derrière :

   ```caddy
   exemple.fr {
       header {
           -Server
           -X-Powered-By
       }
       reverse_proxy 127.0.0.1:4321
   }
   ```
3. **Application derrière le proxy** : selon le cas.
   - Express ou serveur Node personnalisé : `app.disable('x-powered-by');` (ou le module `helmet`).
   - PHP restant sur le serveur (ancien WordPress) : dans `php.ini`, `expose_php = Off`, puis redémarrer PHP-FPM.
   - Apache : `ServerTokens Prod` et `ServerSignature Off`.
   - Astro avec `@astrojs/node` : l'adaptateur n'ajoute pas de numéro de version ; si un `X-Powered-By` apparaît, il vient du proxy, de l'hébergeur ou d'un middleware personnalisé (`grep -rn "x-powered-by" src`).
4. **CDN ou hébergeur** : si l'en-tête vient de la plateforme (`server: cloudflare`, `x-vercel-id`), il n'y a rien à faire, et ces valeurs ne contiennent pas de numéro.
5. **Profiter de l'occasion** : notez la version affichée avant correction et comparez-la à la version stable actuelle du logiciel ; planifiez la mise à jour si elle est ancienne (`nginx -v`, `caddy version`, `node -v`, `apt list --upgradable`).

## Critères d'acceptation

- [ ] `curl -sI` n'affiche aucun numéro de version dans `Server` ni `X-Powered-By`.
- [ ] Le logiciel exposé est à jour ou une mise à jour est planifiée.
- [ ] Le site répond normalement (`nginx -t` OK avant rechargement).

## Vérification après correction

```bash
curl -sI https://exemple.fr/ | grep -iE '^(server|x-powered-by):'
bash scripts/http_checks.sh https://exemple.fr/ /tmp/verif-http && grep 'Server / X-Powered-By' /tmp/verif-http/http-checks.md
```

## Pièges et retour arrière

- Masquer une version ne protège pas contre une faille : la mise à jour reste l'action principale.
- Une page d'erreur nginx affiche aussi la version dans son corps si `server_tokens` est actif : le réglage la retire.
- Retour arrière : supprimer les lignes ajoutées et recharger (`nginx -s reload`, `caddy reload`, sur le serveur de production : à faire par l'humain, ou avec son accord explicite).

## Pour aller plus loin

- nginx `server_tokens` : masquer le numéro de version.
- nginx `proxy_hide_header` : ne pas relayer un en-tête du serveur d'application.
- Caddy `header` : supprimer un en-tête avec le préfixe `-`.
- Express, bonnes pratiques de sécurité : désactiver `x-powered-by`.
