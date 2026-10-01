---
id: perf-streaming-html
titre: Streaming HTML désactivé ou neutralisé (le navigateur attend la page entière)
domaine: Performance
severite_type: moyenne
effort: S
declencheurs:
  - "code:Streaming HTML désactivé"
sources:
  - https://docs.astro.build/en/guides/integrations-guide/node/
  - https://docs.astro.build/en/recipes/streaming-improve-page-performance/
  - https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_buffering
  - https://caddyserver.com/docs/caddyfile/directives/reverse_proxy
---

# Streaming HTML désactivé ou neutralisé (le navigateur attend la page entière)

> **En une phrase** : l'adapter Node est réglé pour envoyer la page en un seul bloc, ce qui supprime l'affichage progressif d'Astro et retarde le premier rendu quand la page attend des données.

## Pourquoi c'est important

Pour les pages rendues à la demande, Astro envoie le HTML par morceaux dès que chaque composant est prêt : l'en-tête et le début de la page arrivent pendant que les parties lentes (requêtes Convex, API) se calculent. Avec `experimentalDisableStreaming: true`, le navigateur ne reçoit rien tant que la page complète n'est pas rendue : le FCP et le LCP sont retardés d'autant. La documentation de l'adapter précise que cette option existe pour quelques hébergements qui ne savent mettre en cache que du HTML non streamé, et qu'elle n'est pas recommandée dans les autres cas.

## Comment le constater soi-même

```bash
grep -rn "experimentalDisableStreaming" astro.config.* 
# Une réponse streamée est en transfert par morceaux (HTTP/1.1) ; le premier octet arrive tôt
curl -s -o /dev/null -w 'TTFB %{time_starttransfer}s | total %{time_total}s\n' https://SITE/page-lente
curl -sI https://SITE/page-lente | grep -iE 'transfer-encoding|content-length'
```

Problème présent : `experimentalDisableStreaming: true` dans la config, ou un `content-length` sur une page rendue à la demande dont le TTFB est proche du temps total. Corrigé : TTFB nettement inférieur au temps total sur une page qui attend des données.

## Correction

1. **Retirer l'option** dans `astro.config.mjs` (ou la mettre à `false`, sa valeur par défaut) :

```js
import { defineConfig } from 'astro/config';
import node from '@astrojs/node';

export default defineConfig({
  output: 'server',
  adapter: node({
    mode: 'standalone',
  }),
});
```

2. **Si l'option avait été ajoutée pour une raison** (cache HTML d'un CDN qui ne gère pas le streaming), regarder d'abord si la page peut être prérendue (`export const prerender = true;`) ou mise en cache : c'est meilleur qu'un rendu non streamé.
3. **Profiter du streaming** : déplacer les `await` de longue durée hors du frontmatter de la page, dans des composants enfants. Le haut de la page part sans attendre les données.

```astro
---
// src/pages/cours.astro : le frontmatter n'attend rien
import Layout from '../layouts/Layout.astro';
import ListeCours from '../components/ListeCours.astro';
---
<Layout titre="Cours">
  <h1>Nos cours</h1>
  <ListeCours />
</Layout>
```

```astro
---
// src/components/ListeCours.astro : l'attente se fait ici
const reponse = await fetch('https://api.exemple.fr/cours');
const cours: { id: string; titre: string }[] = await reponse.json();
---
<ul>{cours.map((c) => <li>{c.titre}</li>)}</ul>
```

4. **Vérifier que le proxy ne recolle pas la réponse.** nginx met par défaut les réponses en mémoire tampon (`proxy_buffering on`). Pour les pages HTML qui doivent streamer :

```nginx
location / {
    proxy_pass http://127.0.0.1:4321;
    proxy_buffering off;
}
```

   Alternative sans toucher à nginx : envoyer l'en-tête `X-Accel-Buffering: no` depuis l'application. Avec Caddy : `reverse_proxy 127.0.0.1:4321 { flush_interval -1 }` (mode faible latence).
5. Faire recharger le proxy (`sudo nginx -t && sudo systemctl reload nginx`, sur le serveur de production : à faire par l'humain, ou avec son accord explicite) et redéployer par l'humain, puis remesurer.

## Critères d'acceptation

- [ ] `experimentalDisableStreaming` absent de la configuration (ou `false`)
- [ ] Sur une page qui attend des données, le premier octet arrive nettement avant la fin de la réponse
- [ ] Aucune régression : pages en 200, contenu identique
- [ ] Le proxy ne met pas en tampon les pages HTML streamées

## Vérification après correction

```bash
curl -s -o /dev/null -w 'TTFB %{time_starttransfer}s | total %{time_total}s\n' https://SITE/page-lente
bash scripts/http_checks.sh https://SITE/ /tmp/verif
python3 scripts/astro_scan.py /chemin/projet --out /tmp/verif
```

## Pièges et retour arrière

- Avec le streaming, le code de statut HTTP et les en-têtes sont envoyés avant la fin du rendu : ne pas modifier `Astro.response.status` ni les en-têtes après le début du corps (dans un composant enfant) ; les positionner dans le frontmatter de la page.
- Un CDN qui met en cache le HTML peut nécessiter le mode non streamé : c'est le cas d'usage prévu de l'option.
- Retour arrière : remettre `experimentalDisableStreaming: true`.

## Pour aller plus loin

- https://docs.astro.build/en/guides/integrations-guide/node/ : option `experimentalDisableStreaming` de l'adapter Node.
- https://docs.astro.build/en/recipes/streaming-improve-page-performance/ : exploiter le streaming.
- https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_buffering : mise en tampon de nginx.
- https://caddyserver.com/docs/caddyfile/directives/reverse_proxy : `flush_interval`.
