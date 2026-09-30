---
id: seo-erreurs-serveur-5xx
titre: Pages en erreur serveur (5xx) ou injoignables
domaine: SEO technique
severite_type: critique
effort: M
declencheurs:
  - "crawl:http_5xx"
  - "crawl:fetch_error"
sources:
  - https://developers.google.com/search/docs/crawling-indexing/http-network-errors
  - https://docs.astro.build/en/basics/astro-pages/
  - https://docs.astro.build/en/guides/on-demand-rendering/
---

# Pages en erreur serveur (5xx) ou injoignables

> **En une phrase** : certaines pages plantent côté serveur (500, 502, 503, 504) ou ne répondent pas (délai dépassé, TLS, DNS), et Google finit par les retirer de l'index.

## Pourquoi c'est important

Un 5xx signifie « le serveur a échoué ». Google réduit la fréquence de crawl quand le serveur renvoie des erreurs, et retire de l'index les URL qui restent en erreur pendant des jours. Sur un site Astro en rendu à la demande, un 500 vient presque toujours d'une exception dans le rendu (donnée absente, appel à l'API Convex en échec, variable d'environnement manquante). Un 502/504 vient du proxy qui n'arrive plus à joindre le processus Node (processus arrêté, mémoire saturée, délai trop court).

## Comment le constater soi-même

```bash
curl -s -o /dev/null -w '%{http_code} %{time_total}s\n' https://SITE/page-en-erreur
# Logs du processus Node et du proxy au moment de l'erreur
docker logs --since 1h <conteneur-astro> 2>&1 | grep -iE 'error|exception' | tail -30
journalctl -u astro-site --since '1 hour ago' | grep -iE 'error|exception' | tail -30
tail -n 200 /var/log/nginx/error.log | grep -iE 'upstream|timed out|refused'
```

`issues.json` (clés `http_5xx` et `fetch_error`) donne l'URL, le statut ou l'erreur, et les pages qui la lient.

## Correction

1. **Reproduire** l'erreur en local (`npm run build && npm run preview` ou `astro dev`) avec la même donnée que la production, puis lire la trace.
2. **Cas 500 dans une page dynamique** : gérer les données manquantes au lieu de laisser l'exception remonter. Une donnée absente doit produire un 404 (fiche `seo-soft-404`), pas un 500.
3. **Cas appel Convex ou API externe en échec** : capturer l'erreur, prévoir un repli, ne pas faire planter tout le rendu.
4. **Cas 502/504** : vérifier que le processus Node tourne et redémarre seul (systemd `Restart=always`, Docker `restart: unless-stopped`), augmenter les délais du proxy si les pages sont lentes, surveiller la mémoire.
5. **Cas TLS/DNS/délai** (`fetch_error`) : vérifier le certificat (`openssl s_client -connect SITE:443 -servername SITE`), le DNS, le pare-feu.
6. Ajouter une page d'erreur utile : `src/pages/500.astro` (Astro >= 4.10.3, la prop `error` est passée depuis 4.11.0).

```astro
---
// src/pages/500.astro : page affichée quand le rendu échoue
import BaseLayout from '../layouts/BaseLayout.astro';
const { error } = Astro.props; // sert à journaliser côté serveur, ne jamais l'afficher au visiteur
console.error(error);
---
<BaseLayout title="Erreur temporaire" description="Le site rencontre une erreur temporaire.">
  <h1>Une erreur est survenue</h1>
  <p>Réessayez dans quelques instants ou <a href="/">revenez à l'accueil</a>.</p>
</BaseLayout>
```

```astro
---
// Exemple : donnée manquante -> 404 propre, jamais une exception
const item = await getItem(Astro.params.slug).catch(() => null);
if (!item) return Astro.rewrite('/404');
---
```

7. Pour une maintenance planifiée, répondre **503** avec `Retry-After` plutôt qu'un 200 ou un 500 : Google comprend que c'est temporaire.

## Critères d'acceptation

- [ ] Aucune URL du site ne renvoie 5xx (`http_5xx` = 0, `fetch_error` = 0)
- [ ] Le processus Node redémarre automatiquement après un plantage
- [ ] Une donnée absente donne un 404, pas un 500
- [ ] Aucune régression : pages clés en 200

## Vérification après correction

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://SITE/page-en-erreur    # attendu : 200 ou 404 selon le cas
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif            # http_5xx, fetch_error
```

## Pièges et retour arrière

- Une erreur intermittente (une fois sur dix) est plus grave que constante : surveiller les logs sur plusieurs heures.
- Ne jamais afficher la trace d'erreur au visiteur (fuite d'information) : n'afficher que `error` en développement.
- Le crawler peut surcharger un serveur fragile : une erreur 5xx peut venir du crawl lui-même ; relancer avec un `--delay` plus grand pour départager.
- Retour arrière : `git revert` du correctif, redémarrer le service.

## Pour aller plus loin

- https://developers.google.com/search/docs/crawling-indexing/http-network-errors : effet des 5xx et 503 sur le crawl.
- https://docs.astro.build/en/basics/astro-pages/ : pages `404.astro` et `500.astro`.
- https://docs.astro.build/en/guides/on-demand-rendering/ : statut de réponse en rendu à la demande.
