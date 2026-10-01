---
id: code-config-compression-html-streaming
titre: Options de build qui dégradent le HTML servi (compressHTML, inlineStylesheets, streaming)
domaine: Code
severite_type: basse
effort: S
declencheurs:
  - "code:compressHTML désactivé"
  - "code:inlineStylesheets: 'always'"
  - "code:Streaming HTML désactivé"
sources:
  - https://docs.astro.build/en/reference/configuration-reference/
  - https://docs.astro.build/en/guides/integrations-guide/node/
  - https://docs.astro.build/en/guides/on-demand-rendering/
---

# Options de build qui dégradent le HTML servi (compressHTML, inlineStylesheets, streaming)

> **En une phrase** : une option d'`astro.config` alourdit le HTML de chaque page ou retarde son affichage sans raison : `compressHTML: false`, `build.inlineStylesheets: 'always'` ou `experimentalDisableStreaming: true`.

## Pourquoi c'est important

- `compressHTML: false` conserve tous les espaces et retours à la ligne du HTML : quelques pourcents de poids en plus sur chaque page.
- `build.inlineStylesheets: 'always'` recopie tout le CSS dans chaque page HTML : le navigateur ne peut plus le mettre en cache, donc il le retélécharge à chaque page visitée.
- `experimentalDisableStreaming: true` (adapter `@astrojs/node`) force le serveur à terminer toute la page avant d'envoyer le premier octet : le TTFB et le LCP augmentent, surtout sur les pages qui attendent Convex.

Ces réglages sont souvent des restes d'un test ou d'un contournement ancien.

## Comment le constater soi-même

```bash
grep -nE "compressHTML|inlineStylesheets|experimentalDisableStreaming" astro.config.* 
curl -s https://SITE/ | wc -c                                   # poids HTML brut
curl -s https://SITE/ | grep -c "<style"                         # feuilles inlinées (nombreuses = 'always')
curl -s -o /dev/null -w 'ttfb=%{time_starttransfer} total=%{time_total}\n' https://SITE/lente
```

Streaming actif : `time_starttransfer` nettement inférieur à `time_total` sur une page lente. Désactivé : les deux valeurs sont presque égales.

## Correction

1. Ouvrir `astro.config.mjs` (ou `.ts`) et repérer les lignes signalées.
2. Remettre les valeurs par défaut (ou retirer l'option) :
   ```js
   // astro.config.mjs
   import { defineConfig } from 'astro/config';
   import node from '@astrojs/node';

   export default defineConfig({
     site: 'https://exemple.fr',
     adapter: node({ mode: 'standalone' }),   // sans experimentalDisableStreaming
     // compressHTML : retirer la ligne (défaut 'jsx' en Astro 7, true avant)
     build: {
       inlineStylesheets: 'auto',               // défaut : n'inline que les petites feuilles
     },
   });
   ```
   - `compressHTML` accepte `true`, `false` ou `'jsx'`. Le défaut est `'jsx'` depuis Astro 7 (règles d'espaces de JSX) et `true` avant. Si un espace entre deux éléments en ligne disparaît après la montée en v7, mettre explicitement `compressHTML: true` plutôt que `false`.
   - `inlineStylesheets` accepte `'always'`, `'auto'`, `'never'` (Astro 2.6+) ; `'auto'` n'inline que les feuilles plus petites que la limite Vite `assetsInlineLimit`.
   - `experimentalDisableStreaming` est une option de l'adapter Node (9.3 et suivantes). Si un proxy en amont (nginx) bufferise la réponse, corriger le proxy (`proxy_buffering off;` sur ce `location`) plutôt que d'éteindre le streaming côté Astro.
3. Reconstruire : `npm run build`, redémarrer le serveur.

## Critères d'acceptation

- [ ] Aucune des trois options n'est présente avec la valeur dégradante
- [ ] Le HTML servi est minifié (peu d'espaces entre balises) et le rendu visuel est identique
- [ ] Le CSS principal est un fichier `/_astro/*.css` mis en cache, pas recopié dans chaque page (hors petites feuilles)
- [ ] Sur une page lente, `time_starttransfer` < `time_total` (streaming actif)
- [ ] Aucune régression : build OK, pages clés en 200

## Vérification après correction

```bash
grep -nE "compressHTML|inlineStylesheets|experimentalDisableStreaming" astro.config.*
npm run build && curl -s -o /dev/null -w 'ttfb=%{time_starttransfer} total=%{time_total}\n' https://SITE/
python3 scripts/astro_scan.py . --out /tmp/verif
```

## Pièges et retour arrière

- Réactiver le streaming peut révéler un proxy qui bufferise : la page s'affiche alors d'un bloc, comme avant, sans casse.
- Certaines pages qui posent des cookies ou modifient les en-têtes après un `await` doivent le faire avant l'envoi du premier fragment.
- Retour arrière : restaurer l'option d'origine (`git checkout -- astro.config.mjs`).

## Pour aller plus loin

- https://docs.astro.build/en/reference/configuration-reference/ : `compressHTML`, `build.inlineStylesheets`.
- https://docs.astro.build/en/guides/integrations-guide/node/ : options de l'adapter Node.
- https://docs.astro.build/en/guides/on-demand-rendering/ : streaming HTML des pages à la demande.
