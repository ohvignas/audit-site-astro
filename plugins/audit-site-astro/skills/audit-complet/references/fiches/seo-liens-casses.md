---
id: seo-liens-casses
titre: Pages en erreur 4xx et liens internes cassés
domaine: SEO technique
severite_type: haute
effort: S
declencheurs:
  - "crawl:http_4xx"
  - "crawl:external_broken"
  - "crawl:external_a_verifier"
  - "lighthouse:http-status-code|code HTTP d.échec"
sources:
  - https://developers.google.com/search/docs/crawling-indexing/http-network-errors
  - https://docs.astro.build/en/guides/routing/
  - https://docs.astro.build/en/reference/configuration-reference/
---

# Pages en erreur 4xx et liens internes cassés

> **En une phrase** : des liens du site mènent à des pages introuvables (404, 410, 403), ce qui casse la navigation et gaspille le crawl.

## Pourquoi c'est important

Un lien interne vers une page en 404 donne une mauvaise expérience et signale un site mal entretenu. Google ne transmet aucune valeur à une page en erreur et perd du budget de crawl à revisiter des liens morts. Une page qui a réellement disparu doit répondre 404 ou 410, c'est normal ; le défaut est le **lien** qui y mène, ou une page qui a déménagé sans redirection 301.

## Comment le constater soi-même

Le fichier `data/crawl/issues.json` (clé `http_4xx`) donne, pour chaque URL en erreur, `liens_depuis` (les pages qui la lient).

```bash
# Statut d'une URL
curl -s -o /dev/null -w '%{http_code}\n' https://SITE/page-cassee
# Trouver la source du lien dans le code
grep -rn "page-cassee" src/ public/ | head
# Liens cassés dans les données (Convex ou contenu) : chercher aussi dans les exports
grep -rn "page-cassee" convex/ content/ 2>/dev/null | head
```

## Correction

Pour chaque URL en 4xx, décider :

1. **La page existe ailleurs** (déplacée, renommée) : créer une redirection 301 de l'ancienne URL vers la nouvelle (fiche `seo-redirections` : `redirects` dans `astro.config.mjs`, nginx ou Caddy), **et** corriger le lien à la source.
2. **La page n'existe plus, sans équivalent** : supprimer ou remplacer le lien à la source (menu, pied de page, composant, article Markdown, donnée Convex). Laisser l'URL répondre 404 (ou 410 si suppression définitive).
3. **Faute de frappe ou mauvaise casse** : corriger l'URL (les chemins sont sensibles à la casse sur la plupart des serveurs).
4. **403 / 401** sur une page publique : vérifier la protection (WAF, authentification de préproduction, règle nginx) qui bloque le crawler.
5. Si le contenu vient d'une donnée (Convex, CMS), corriger la donnée, pas seulement le gabarit.

```js
// astro.config.mjs : ancienne URL -> nouvelle URL (301 par défaut)
export default defineConfig({
  redirects: {
    '/formation-excel': '/formations/excel/',
    '/blog/[...slug]': '/articles/[...slug]/',
  },
});
```

6. Prévoir une vraie page 404 utile (fiche `seo-page-404-manquante`) pour les visiteurs qui arrivent par un vieux lien externe.
7. Vérifier les images et fichiers liés : un `<img>` ou un PDF en 404 apparaît dans `broken_images`.

## Liens vers d'autres sites

Les clés `external_broken` (404, 410, nom de domaine inexistant) et `external_a_verifier` (401, 403, 429, 999 de LinkedIn, 5xx, délai dépassé) du même fichier concernent les liens sortants. Le crawler les vérifie avec un HEAD puis un GET d'un octet, au plus une requête par seconde et par hôte, en commençant par les liens présents sur le plus de pages ; le nombre de liens laissés de côté (plafond ou budget de temps) est dans `pages.json` (`meta.modules.liens_externes_non_verifies`). Un lien « à vérifier » n'est pas cassé : beaucoup de sites refusent les robots, ouvrez-le dans un navigateur avant de le corriger. Pour un lien réellement cassé, le remplacer par une page équivalente ou le retirer (`liens_depuis` indique la page à modifier).

## Critères d'acceptation

- [ ] Aucun lien interne du site ne mène à une réponse 4xx (`http_4xx` sans `liens_depuis`)
- [ ] Les URL déplacées répondent par une redirection 301 vers l'équivalent
- [ ] Lighthouse : « La page renvoie un code HTTP de réussite » (audit `http-status-code`) est OK sur les pages testées
- [ ] Aucune régression : pages clés en 200

## Vérification après correction

```bash
# liste des URL en 4xx à partir du crawl
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif
python3 - <<'EOF'
import json
d = json.load(open('/tmp/verif/issues.json'))
for e in d.get('http_4xx', {}).get('examples', []):
    print(e['status'], e['url'], e.get('liens_depuis'))
EOF
```

## Pièges et retour arrière

- Ne pas rediriger toutes les 404 vers l'accueil : Google le traite comme une erreur douce (soft 404).
- Un 404 sur une URL sans lien interne (ancien lien externe) n'est pas un défaut à corriger ; ne traiter que celles qui ont des liens entrants utiles.
- Le crawler ne suit que les liens rendus dans le HTML : les liens ajoutés par JavaScript n'apparaissent pas.
- Retour arrière : retirer la redirection ajoutée ; restaurer le lien depuis Git.

## Pour aller plus loin

- https://developers.google.com/search/docs/crawling-indexing/http-network-errors : comment Google traite les codes 4xx et 5xx.
- https://docs.astro.build/en/guides/routing/ : redirections et page 404.
- https://docs.astro.build/en/reference/configuration-reference/ : option `redirects`.
