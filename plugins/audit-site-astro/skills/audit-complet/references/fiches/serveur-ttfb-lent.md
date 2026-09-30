---
id: serveur-ttfb-lent
titre: Temps de réponse du serveur trop long (TTFB élevé)
domaine: Serveur / HTTP
severite_type: haute
effort: M
declencheurs:
  - "crawl:slow_ttfb"
  - "lighthouse:server-response-time"
  - "lighthouse:Réduire le temps de réponse initial du serveur"
  - "lighthouse:document-latency-insight|Latence de la demande de document"
sources:
  - https://web.dev/articles/ttfb
  - https://docs.astro.build/en/guides/caching/
  - https://docs.astro.build/en/guides/server-islands/
  - https://docs.convex.dev/client/javascript
---

# Temps de réponse du serveur trop long (TTFB élevé)

> **En une phrase** : le serveur met plus d'une seconde à envoyer le premier octet de la page ; tout le reste (affichage, LCP) démarre en retard d'autant.

## Pourquoi c'est important

Le TTFB (Time To First Byte) précède toutes les autres métriques de chargement : chaque milliseconde perdue ici est perdue sur le FCP et le LCP. Google donne comme repère un bon TTFB à 0,8 s ou moins et un mauvais TTFB au-delà de 1,8 s. Le crawler de l'outil signale `slow_ttfb` au-delà de 1 s ; Lighthouse signale « Réduire le temps de réponse initial du serveur » (audit `server-response-time`, seuil 600 ms) et l'insight « Latence de la demande de document ». Un serveur lent réduit aussi le rythme de crawl de Googlebot.

Le TTFB additionne : redirections, DNS, connexion TCP, TLS, **puis le temps de traitement du serveur**. Il faut d'abord savoir laquelle de ces parties est en cause.

## Comment le constater soi-même

```bash
# Décomposition d'une requête : si « TTFB » - « TLS » est grand, c'est le serveur
curl -s -o /dev/null -H 'Accept-Encoding: br, gzip' -w 'DNS %{time_namelookup}s | connexion %{time_connect}s | TLS %{time_appconnect}s | TTFB %{time_starttransfer}s | total %{time_total}s | redirections %{num_redirects}\n' https://SITE/
# Répéter 5 fois : stable et haut = rendu à chaque requête ; 1re requête lente puis rapide = cache ou démarrage à froid
for i in 1 2 3 4 5; do curl -s -o /dev/null -w '%{time_starttransfer}\n' https://SITE/; done
# Depuis le serveur lui-même (sans réseau ni proxy) : mesure le temps de rendu de Node
curl -s -o /dev/null -w '%{time_starttransfer}\n' http://127.0.0.1:4321/
```

Lecture : si `127.0.0.1:4321` est lent, le problème est dans Astro / Convex. S'il est rapide mais pas la version publique, le problème est le proxy, le réseau, le TLS ou la distance.

## Correction

Traiter les causes dans cet ordre (de la plus rentable à la plus coûteuse) :

1. **Prérendre** les pages qui changent peu : `export const prerender = true;` (voir la fiche `code-prerender-ssr-opportunites`). TTFB de quelques dizaines de ms, sans serveur.

2. **Mettre en cache** les pages qui doivent rester dynamiques : cache de routes Astro 7, `Cache-Control` + proxy ou CDN (voir la fiche `serveur-cache-html-ssr`).

3. **Paralléliser les appels Convex** dans le frontmatter : des `await` successifs additionnent leurs latences.

```astro
---
import { ConvexHttpClient } from 'convex/browser';
import { api } from '../../convex/_generated/api';

const client = new ConvexHttpClient(import.meta.env.PUBLIC_CONVEX_URL);
// Mauvais : const a = await client.query(api.a.liste, {}); const b = await client.query(api.b.liste, {});
const [articles, categories] = await Promise.all([
  client.query(api.articles.liste, {}),
  client.query(api.categories.liste, {}),
]);
---
```

Vérifier aussi côté Convex que les requêtes utilisent un index (`withIndex`) et ne parcourent pas toute la table.

4. **Isoler les morceaux lents ou personnalisés** en server islands (`server:defer`) : la page part tout de suite, le morceau lent arrive ensuite (voir la fiche `code-server-islands`).

5. **Rapprocher les services** : héberger le serveur Astro dans la même région que le déploiement Convex, et utiliser un CDN pour les visiteurs éloignés. Un aller-retour transatlantique coûte environ 80 à 150 ms par appel.

6. **Éviter les démarrages à froid** : sur du serverless (Vercel, Netlify, Cloudflare), la première requête après une période creuse est plus lente ; réduire la taille du bundle serveur et éviter les imports lourds au niveau du module. Sur un serveur Node classique, garder le process actif (`systemd` avec `Restart=always`, ou conteneur `restart: unless-stopped`).

7. **Ressources du serveur** : `uptime` (charge), `free -m` (mémoire, swap actif = très mauvais signe), `top` (process Node à 100 % CPU). Un VPS sous-dimensionné ou qui swappe ralentit tout.

8. **Côté proxy** : activer les connexions persistantes vers Node pour éviter d'ouvrir une connexion à chaque requête.

```nginx
upstream astro_node {
    server 127.0.0.1:4321;
    keepalive 16;
}
server {
    location / {
        proxy_pass http://astro_node;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
```

## Critères d'acceptation

- [ ] TTFB des pages publiques principales < 0,8 s (idéalement < 0,2 s quand elles viennent d'un cache), médiane de 5 mesures
- [ ] Lighthouse n'affiche plus « Réduire le temps de réponse initial du serveur »
- [ ] Aucune page du crawl n'est signalée `slow_ttfb`
- [ ] Aucune régression : contenu à jour, pages personnalisées non mises en cache

## Vérification après correction

```bash
for i in 1 2 3 4 5; do curl -s -o /dev/null -w '%{time_starttransfer}\n' https://SITE/; done
bash scripts/http_checks.sh https://SITE/ /tmp/verif                  # §2 : 5 mesures « normale » et « sans cache »
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl     # slow_ttfb absent
```

## Pièges et retour arrière

- Le crawler mesure depuis sa propre machine : un TTFB élevé peut venir de la distance. Comparer avec la mesure faite depuis le serveur avant d'accuser Astro.
- La première requête d'un cache vide reste lente : mesurer la deuxième.
- Mesurer avec plusieurs pages (accueil, article, page dynamique) : le goulot est souvent sur une seule route.
- Retour arrière : chaque étape est indépendante ; annuler avec `git revert` (code) ou en retirant la configuration ajoutée (proxy).

## Pour aller plus loin

- https://web.dev/articles/ttfb : définition du TTFB et seuils de référence.
- https://docs.astro.build/en/guides/caching/ : cache de routes pour le rendu à la demande.
- https://docs.astro.build/en/guides/server-islands/ : isoler les parties lentes ou personnalisées.
- https://docs.convex.dev/client/javascript : client JavaScript de Convex utilisé côté serveur.
