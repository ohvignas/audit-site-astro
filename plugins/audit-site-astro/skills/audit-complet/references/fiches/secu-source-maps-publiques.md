---
id: secu-source-maps-publiques
titre: "Source maps JavaScript publiques en production"
domaine: Sécurité
severite_type: basse
effort: S
declencheurs:
  - "securite:⚠️ https?://\\S+\\.js → \\.map HTTP 200"
  - "securite:sourceMappingURL"
  - "code:Source maps activées en build"
sources:
  - https://vite.dev/config/build-options.html#build-sourcemap
  - https://docs.astro.build/en/reference/configuration-reference/#vite
  - https://nginx.org/en/docs/http/ngx_http_core_module.html#location
---

# Source maps JavaScript publiques en production

> **En une phrase** : les fichiers `.js.map` permettent à n'importe qui de reconstituer le code source lisible de votre site côté navigateur.

## Pourquoi c'est important

Le JavaScript livré est déjà lisible pour un développeur motivé, mais une source map restitue les noms de variables, les commentaires et la structure des fichiers d'origine. Ce n'est pas une faille en soi (gravité basse). Le vrai danger : si un secret a été écrit dans le code client, la source map le rend trivial à trouver ; et des commentaires internes (`TODO`, adresses de serveurs de test, routes d'administration) deviennent visibles. Les maps alourdissent aussi les déploiements. Elles ont leur utilité pour le suivi d'erreurs (Sentry…), mais sans avoir à être publiques.

## Comment le constater soi-même

```bash
# 1. repérer un script de la page
curl -s https://exemple.fr/ | grep -oE '/_astro/[^"]+\.js' | head -3
# 2. tester la map du premier script (remplacer le nom)
curl -s -o /dev/null -w '%{http_code}\n' https://exemple.fr/_astro/index.AbC123.js.map
# 3. le script référence-t-il sa map ?
curl -s https://exemple.fr/_astro/index.AbC123.js | tail -c 200 | grep sourceMappingURL
```

Présent : 200 sur la `.map` ou une ligne `//# sourceMappingURL=...`. Corrigé : 404 et plus de ligne `sourceMappingURL`.

## Correction

1. **Ne pas générer les maps en production** dans `astro.config.mjs` (Astro s'appuie sur Vite, option `vite.build.sourcemap`, `false` par défaut).

   ```js
   // astro.config.mjs
   import { defineConfig } from 'astro/config';

   export default defineConfig({
     vite: {
       build: {
         sourcemap: false,
       },
     },
   });
   ```

   Cherchez aussi `sourcemap: true` ou `'inline'` dans les intégrations (Sentry, Tailwind…), dans `vite.config.*` et les scripts `package.json`.
2. **Si vous avez besoin des maps pour le suivi d'erreurs** : générez-les en mode `'hidden'` (les fichiers `.map` existent mais le script n'y renvoie plus), envoyez-les à l'outil d'erreurs pendant l'intégration continue, puis supprimez-les du dossier publié.

   ```js
   vite: { build: { sourcemap: 'hidden' } },
   ```

   ```bash
   npm run build
   # ... envoi des maps à votre outil (commande fournie par l'outil) ...
   find dist -name '*.map' -delete
   ```
3. **Filet de sécurité serveur** : refuser les `.map` même si elles sont déployées par erreur.

   ```nginx
   location ~* \.map$ { return 404; }
   ```

   ```caddy
   @maps path *.map
   respond @maps 404
   ```
4. Reconstruisez, redéployez, videz le cache du CDN s'il y en a un.
5. Si des secrets sont apparus dans le code source exposé, faites-les tourner : `secu-secret-dans-js-client`.

## Critères d'acceptation

- [ ] `find dist -name '*.map'` ne trouve rien (ou seulement en dehors du dossier publié).
- [ ] Les URL `.js.map` répondent 404.
- [ ] Les scripts ne contiennent plus `sourceMappingURL` (sauf configuration `hidden` assumée sans fichier public).
- [ ] Site identique, aucune erreur JavaScript dans la console.

## Vérification après correction

```bash
grep -rl sourceMappingURL dist/client 2>/dev/null | head
bash scripts/security_probe.sh https://exemple.fr/ /tmp/verif-secu && grep -A3 'Source maps' /tmp/verif-secu/security-probe.md
```

## Pièges et retour arrière

- Sans maps, les erreurs de production sont plus difficiles à lire : prévoyez l'envoi privé des maps avant de les supprimer.
- La sonde ne teste que les scripts de la page d'accueil : vérifiez aussi les autres gabarits si vous avez du code par page.
- Retour arrière : remettre `sourcemap: true` (sans exposer les fichiers).

## Pour aller plus loin

- Vite, option `build.sourcemap` : valeurs `true`, `false`, `'inline'`, `'hidden'`.
- Astro, clé `vite` : passer une configuration à Vite.
- nginx `location` : filtrer par extension.
