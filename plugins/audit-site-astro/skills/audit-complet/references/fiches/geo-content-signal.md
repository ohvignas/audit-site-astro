---
id: geo-content-signal
titre: Lignes Content-Signal dans robots.txt (robots.txt géré par Cloudflare) à vérifier
domaine: GEO / IA
severite_type: basse
effort: S
declencheurs:
  - "geo:Content-Signal présent"
sources:
  - https://blog.cloudflare.com/content-independence-day-ai-options/
  - https://developers.cloudflare.com/ai-crawl-control/features/manage-ai-crawlers/
  - https://developers.google.com/search/docs/crawling-indexing/robots/intro
---

# Lignes Content-Signal dans robots.txt

> **En une phrase** : le robots.txt contient des lignes `Content-Signal:` (typiquement ajoutées par Cloudflare) qui déclarent ce que les robots peuvent faire du contenu ; il faut vérifier qu'elles correspondent au choix du propriétaire.

## Pourquoi c'est important

Cloudflare propose un robots.txt « géré » qui ajoute une politique de « Content Signals » : trois usages, `search` (indexation et liste de résultats), `ai-input` (réponses IA en direct, RAG, grounding) et `ai-train` (entraînement de modèles), chacun à `yes` ou `no`. Par défaut, selon Cloudflare, la valeur posée est « recherche oui, entraînement non, réponses IA non précisées ». Si le propriétaire ne l'a pas demandé, il peut avoir une politique qu'il ignore. Ce n'est pas une erreur : c'est un signal à valider. Attention, c'est une **déclaration de préférence**, pas un mécanisme de blocage : un robot peut l'ignorer, et ce qui bloque réellement un robot reste `Disallow` ou le pare-feu. Pour être cité en direct, la ligne `ai-input=no` est contre-productive.

## Comment le constater soi-même

```bash
curl -s https://SITE/robots.txt | grep -i 'content-signal'
curl -sI https://SITE/ | grep -iE '^(server|cf-ray)'     # cloudflare ?
grep -rn -i 'content-signal' public/ src/ 2>/dev/null     # présent dans le dépôt ?
```

Si `grep` ne trouve rien dans le dépôt mais que `curl` montre les lignes : elles sont ajoutées par Cloudflare (robots.txt géré), pas par le code du site.

Exemple typique (source : annonce Cloudflare) :

```text
User-agent: *
Content-Signal: search=yes, ai-train=no
Allow: /
```

## Correction

1. Demander au propriétaire quelle politique il souhaite (voir tableau).
2. Si les lignes viennent du dépôt : modifier `public/robots.txt` ou `src/pages/robots.txt.ts` (voir `geo-robots-bots-recherche-bloques`) en ajoutant la ligne sous le bon groupe. Si elles viennent de Cloudflare : ajuster dans le tableau de bord (réglage du robots.txt géré, dans AI Crawl Control) ou désactiver ce robots.txt géré pour reprendre la main sur le fichier du site. L'interface change : suivre la documentation Cloudflare.

| Objectif | Ligne à publier |
|---|---|
| Être indexé et cité, ne pas servir à l'entraînement (cas courant) | `Content-Signal: search=yes, ai-input=yes, ai-train=no` |
| Tout autoriser | `Content-Signal: search=yes, ai-input=yes, ai-train=yes` |
| Ne pas s'exprimer sur un usage | omettre la clé (pas de préférence exprimée) |

3. Exemple de fichier cohérent avec le premier objectif :

```text
User-agent: *
Content-Signal: search=yes, ai-input=yes, ai-train=no
Allow: /

Sitemap: https://exemple.fr/sitemap-index.xml
```

4. Les Content-Signals **ne remplacent pas** les groupes par robot : pour interdire concrètement GPTBot ou ClaudeBot, garder les `Disallow` (fiche `geo-robots-bots-entrainement`).

## Critères d'acceptation

- [ ] Le propriétaire connaît et valide la politique publiée
- [ ] `ai-input` n'est pas à `no` si l'objectif est d'être cité dans les réponses IA
- [ ] `search` n'est pas à `no`
- [ ] `robots.txt` reste servi en 200, `text/plain`, avec un `Sitemap:` absolu

## Vérification après correction

```bash
curl -s https://SITE/robots.txt | grep -iE 'content-signal|user-agent|sitemap'
python3 scripts/geo_check.py https://SITE/ --out /tmp/verif/geo --sample 3
```

Le signal « Content-Signal présent » reste affiché en information tant que les lignes existent : c'est normal. L'objectif est la validation du contenu, pas la disparition.

## Pièges et retour arrière

- Modifier `public/robots.txt` sans effet visible : c'est que Cloudflare fusionne ou remplace le fichier ; vérifier avec `curl` sur l'URL publique.
- Ne pas supposer que `ai-train=no` bloque techniquement : ce n'est pas le cas.
- Retour arrière : restaurer le fichier (Git) ou réactiver le réglage précédent dans Cloudflare.

## Pour aller plus loin

- https://blog.cloudflare.com/content-independence-day-ai-options/ : options Cloudflare pour le trafic IA.
- https://developers.cloudflare.com/ai-crawl-control/features/manage-ai-crawlers/ : gestion des crawlers dans AI Crawl Control.
- https://developers.google.com/search/docs/crawling-indexing/robots/intro : règles de base de robots.txt.
