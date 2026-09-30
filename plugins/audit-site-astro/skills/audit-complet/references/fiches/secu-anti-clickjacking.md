---
id: secu-anti-clickjacking
titre: "Protection contre l'intégration en iframe absente (clickjacking)"
domaine: Sécurité
severite_type: moyenne
effort: S
declencheurs:
  - "http:\\| x-frame-options \\| — \\| ❌ absent"
sources:
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/frame-ancestors
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Frame-Options
  - https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP#delivery_of_csp
  - https://docs.astro.build/en/guides/middleware/
---

# Protection contre l'intégration en iframe absente (clickjacking)

> **En une phrase** : n'importe quel autre site peut afficher vos pages dans une iframe invisible et pousser vos visiteurs à cliquer sur vos boutons à leur insu.

## Pourquoi c'est important

Dans une attaque de « clickjacking », un site pirate superpose votre page (transparente) à un faux bouton : le visiteur croit cliquer sur autre chose et déclenche une action chez vous (valider un formulaire, confirmer une suppression, se connecter). Le risque est faible sur un site vitrine sans compte, et réel dès qu'il y a des actions authentifiées (espace client, administration). La parade est un simple en-tête : `frame-ancestors` (moderne, dans la CSP) et `X-Frame-Options` (ancien, encore lu par certains navigateurs). L'outil ne signale le constat que si les deux manquent.

## Comment le constater soi-même

```bash
curl -sI https://exemple.fr/ | grep -iE '^(x-frame-options|content-security-policy):'
```

Absent : aucune ligne `x-frame-options` et aucun `frame-ancestors` dans la CSP. Corrigé : `x-frame-options: SAMEORIGIN` et/ou `frame-ancestors 'self'`.

## Correction

**Attention : `frame-ancestors` est ignoré dans une balise `<meta http-equiv="Content-Security-Policy">`.** Il doit être envoyé comme **en-tête HTTP**. La CSP générée par Astro (`security.csp`) est une balise meta : elle ne suffit donc pas pour cette protection. Posez donc l'en-tête au proxy (ou dans un middleware).

Si le site ne doit être intégré nulle part (cas général) :

1. **nginx** :

   ```nginx
   add_header Content-Security-Policy "frame-ancestors 'self'" always;
   add_header X-Frame-Options "SAMEORIGIN" always;
   ```

   Si vous avez déjà un en-tête `Content-Security-Policy` complet (voir `secu-csp-absente`), ajoutez-y `frame-ancestors 'self'` plutôt qu'une seconde ligne.
2. **Caddy** :

   ```caddy
   exemple.fr {
       header {
           Content-Security-Policy "frame-ancestors 'self'"
           X-Frame-Options SAMEORIGIN
       }
       reverse_proxy 127.0.0.1:4321
   }
   ```
3. **Middleware Astro (SSR)** si vous ne contrôlez pas le proxy :

   ```ts
   // src/middleware.ts
   import { defineMiddleware } from 'astro:middleware';

   export const onRequest = defineMiddleware(async (_context, next) => {
     const response = await next();
     response.headers.set('Content-Security-Policy', "frame-ancestors 'self'");
     response.headers.set('X-Frame-Options', 'SAMEORIGIN');
     return response;
   });
   ```

   Si Astro produit déjà une CSP par balise meta (`security.csp`), les deux politiques se cumulent : c'est voulu, le navigateur applique la plus restrictive de chaque directive.
4. **Netlify / Cloudflare Pages** : `public/_headers`, ligne `Content-Security-Policy: frame-ancestors 'self'` et `X-Frame-Options: SAMEORIGIN` sous `/*`. **Vercel** : entrées équivalentes dans `headers` de `vercel.json` (voir `secu-en-tetes-securite-manquants`).
5. **Si votre site doit être intégré ailleurs** (widget, application partenaire) : listez les origines exactes, par exemple `frame-ancestors 'self' https://partenaire.exemple.fr`. `X-Frame-Options` ne sait pas gérer plusieurs origines : dans ce cas ne l'envoyez pas, ou seulement `SAMEORIGIN` si l'intégration est sur le même domaine.
6. Ne mettez pas `X-Frame-Options: ALLOW-FROM` (valeur abandonnée, ignorée par les navigateurs actuels).

## Critères d'acceptation

- [ ] `curl -sI` montre `frame-ancestors` dans la CSP en en-tête et/ou `x-frame-options`.
- [ ] Une page de test sur un autre domaine qui contient `<iframe src="https://exemple.fr">` n'affiche pas votre site (console : « refused to display »).
- [ ] Les intégrations légitimes (YouTube chez vous n'est pas concerné, seulement l'intégration DE votre site ailleurs) fonctionnent toujours.

## Vérification après correction

```bash
curl -sI https://exemple.fr/ | grep -iE '^(x-frame-options|content-security-policy):'
bash scripts/http_checks.sh https://exemple.fr/ /tmp/verif-http && grep -E 'x-frame|frame-ancestors' /tmp/verif-http/http-checks.md
```

## Pièges et retour arrière

- Ne confondez pas : vos propres iframes (carte, vidéo) ne sont pas concernées ; c'est `child-src` / `frame-src` qui les gouvernent dans une CSP complète.
- Dans nginx, `add_header` dans un `location` remplace celui du `server` : répétez la ligne si besoin.
- Un aperçu de page dans un outil interne (CMS, prévisualisation) peut utiliser une iframe : ajoutez son origine à `frame-ancestors`.
- Retour arrière : retirer les deux lignes et recharger.

## Pour aller plus loin

- MDN `frame-ancestors` : syntaxe et différences avec `X-Frame-Options`.
- MDN `X-Frame-Options` : valeurs `DENY` et `SAMEORIGIN`.
- MDN, mise en oeuvre d'une CSP : en-tête ou balise meta, limites de la balise.
- Astro, middleware : poser des en-têtes sur les réponses.
