---
id: secu-allowed-domains-host-header
titre: "security.allowedDomains absent derrière un proxy (injection d'en-tête Host / X-Forwarded-Host)"
domaine: Sécurité
severite_type: moyenne
effort: S
declencheurs:
  - "code:Serveur derrière un proxy sans security\\.allowedDomains"
versions_astro: ">=5.14.2"
sources:
  - https://docs.astro.build/en/reference/configuration-reference/#securityalloweddomains
  - https://docs.astro.build/en/guides/on-demand-rendering/
  - https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header
  - https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#headers
  - https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
---

# security.allowedDomains absent derrière un proxy (injection d'en-tête Host / X-Forwarded-Host)

> **En une phrase** : Astro ne sait pas quels noms de domaine sont légitimes, donc soit il ignore les en-têtes du proxy (et construit des URL `http://localhost:4321`), soit un visiteur malveillant peut lui faire croire que le site s'appelle autrement.

## Pourquoi c'est important

Derrière nginx ou Caddy, l'application Node voit `localhost:4321`, pas `https://exemple.fr`. Le proxy transmet le vrai nom dans `X-Forwarded-Host`. Depuis Astro 5.14.2, `security.allowedDomains` définit la liste blanche des hôtes acceptés : tant qu'elle est vide, `X-Forwarded-Host` est **ignoré** (donc `Astro.url` reflète l'hôte interne, souvent en http : canonicals, sitemap, redirections et cookies faux). Le domaine listé, lui, protège contre l'**injection d'en-tête Host** : un attaquant qui envoie `X-Forwarded-Host: pirate.example` ne peut plus faire générer par votre site des liens de réinitialisation de mot de passe, des redirections ou des canonicals vers son domaine, ni empoisonner un cache partagé.

## Comment le constater soi-même

```bash
grep -n "allowedDomains" astro.config.*                       # absent : constat confirmé
# Test avec un hôte forgé : la page ne doit jamais contenir pirate.example
curl -s -H 'X-Forwarded-Host: pirate.example' -H 'X-Forwarded-Proto: https' https://exemple.fr/ | grep -c 'pirate.example'
# URL vue par Astro : canonical et og:url doivent être en https://exemple.fr
curl -s https://exemple.fr/ | grep -oE '<link rel="canonical"[^>]*>'
```

Problème présent : pas de `allowedDomains`, canonicals en `http://localhost:4321/...` ou en `http://`, ou `pirate.example` reflété dans la page (le test peut aussi être bloqué par le proxy, qui écrase l'en-tête : dans ce cas la protection existe côté proxy mais la configuration Astro reste à faire). Corrigé : résultat `0` et canonicals en `https://exemple.fr`.

## Correction

1. **Astro 5.14.2 ou plus** (`npm ls astro`). Sinon, mettez à jour Astro (voir la fiche Code) ou configurez le proxy pour toujours envoyer `Host: exemple.fr` fixe.
2. **Déclarer les domaines** dans `astro.config.mjs` (les jokers `*.exemple.fr` = un seul niveau, `**.exemple.fr` = tous niveaux) :

   ```js
   // astro.config.mjs
   import { defineConfig } from 'astro/config';
   import node from '@astrojs/node';

   export default defineConfig({
     site: 'https://exemple.fr',
     output: 'server',
     adapter: node({ mode: 'standalone' }),
     security: {
       allowedDomains: [
         { hostname: 'exemple.fr', protocol: 'https' },
         { hostname: 'www.exemple.fr', protocol: 'https' },
       ],
     },
   });
   ```

   Chaque motif accepte `protocol`, `hostname` et `port` (tous validés s'ils sont fournis). Évitez `allowedDomains: [{}]` (accepte tout) sauf besoin précis derrière un proxy de confiance à domaines dynamiques.
3. **Proxy** : il doit transmettre l'hôte et le protocole d'origine.

   nginx :

   ```nginx
   location / {
       proxy_pass http://127.0.0.1:4321;
       proxy_set_header Host $host;
       proxy_set_header X-Forwarded-Proto $scheme;
       proxy_set_header X-Forwarded-Host $host;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
   }
   ```

   Caddy : `reverse_proxy 127.0.0.1:4321` pose déjà `X-Forwarded-For`, `X-Forwarded-Proto` et `X-Forwarded-Host`, et ignore les valeurs envoyées par le client (sauf `trusted_proxies`, à ne renseigner que si un CDN se trouve devant).
4. **Construire les URL publiques à partir de `Astro.site`**, jamais de l'en-tête de la requête :

   ```astro
   ---
   const canonical = new URL(Astro.url.pathname, Astro.site).href;
   ---
   <link rel="canonical" href={canonical} />
   ```
5. Faites redéployer par l'humain, puis contrôlez canonical, `og:url`, sitemap et redirections.

## Critères d'acceptation

- [ ] `security.allowedDomains` liste exactement les hôtes publics du site (https).
- [ ] Le proxy transmet `Host`, `X-Forwarded-Proto` et `X-Forwarded-Host`.
- [ ] Canonicals, `og:url` et sitemap sont en `https://exemple.fr/...`.
- [ ] Une requête avec `X-Forwarded-Host: pirate.example` ne produit aucune URL vers ce domaine.
- [ ] Les formulaires fonctionnent (voir `secu-check-origin-desactive`).

## Vérification après correction

```bash
curl -s -H 'X-Forwarded-Host: pirate.example' https://exemple.fr/ | grep -c 'pirate.example'      # 0
curl -s https://exemple.fr/ | grep -oE '<link rel="canonical"[^>]*>'
python3 scripts/astro_scan.py . --out /tmp/verif-code && grep -i allowedDomains /tmp/verif-code/code-scan.md || echo "constat levé"
```

## Pièges et retour arrière

- Oublier `www.exemple.fr` ou un domaine de préproduction : les pages de ces hôtes retomberont sur l'hôte interne.
- Un site servi sur plusieurs ports / domaines : ajoutez chaque combinaison.
- `Astro.url` a plusieurs usages (cookies, redirections) : testez la connexion et les redirections après le changement.
- Retour arrière : supprimer le bloc `allowedDomains` (retour au comportement précédent : en-têtes du proxy ignorés).

## Pour aller plus loin

- Astro, `security.allowedDomains` : format des motifs et jokers.
- Astro, rendu à la demande : `Astro.url` et `Astro.site`.
- nginx `proxy_set_header` et Caddy `reverse_proxy` : en-têtes transmis à l'application.
- OWASP, en-têtes HTTP : risques liés à l'en-tête `Host`.
