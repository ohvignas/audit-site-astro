---
id: geo-robots-bots-entrainement
titre: robots.txt bloque des robots d'entraînement IA (choix business à confirmer)
domaine: GEO / IA
severite_type: basse
effort: S
declencheurs:
  - "geo:robots\\.txt bloque (GPTBot|ClaudeBot|Google-Extended|Applebot-Extended|Meta-ExternalAgent|CCBot|Bytespider) \\("
sources:
  - https://developers.openai.com/api/docs/bots
  - https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler
  - https://developers.google.com/search/docs/crawling-indexing/overview-google-crawlers
  - https://developers.google.com/search/docs/appearance/ai-features
---

# robots.txt bloque des robots d'entraînement IA

> **En une phrase** : le site refuse à certains robots de collecter ses pages pour entraîner des modèles d'IA ; c'est légitime, mais c'est une décision à prendre consciemment, et elle n'empêche pas d'être cité en direct.

## Pourquoi c'est important

Deux usages très différents se cachent derrière « les robots IA ». Les robots de **recherche et de réponse** (OAI-SearchBot, PerplexityBot, Claude-SearchBot…) construisent les index qui produisent des citations : les bloquer fait perdre de la visibilité (fiche `geo-robots-bots-recherche-bloques`). Les robots d'**entraînement** (GPTBot, ClaudeBot, Google-Extended, Applebot-Extended, Meta-ExternalAgent, CCBot, Bytespider) collectent du contenu pour fabriquer ou améliorer des modèles. Selon la documentation d'OpenAI, refuser GPTBot indique que le contenu ne doit pas servir à entraîner ses modèles ; selon Google, Google-Extended contrôle l'usage pour l'entraînement et le « grounding » de Gemini et d'autres systèmes, distinct de Google Search et des AI Overviews. Bloquer l'entraînement est donc **sans effet sur les citations en direct**. Inversement, l'autoriser peut aider les modèles à « connaître » la marque, sans garantie mesurable. Ce point n'est pas technique : il relève de la stratégie et de la propriété intellectuelle du propriétaire. L'outil le signale en information, pas comme une erreur.

## Comment le constater soi-même

```bash
curl -s https://SITE/robots.txt | grep -iE -B1 -A2 'GPTBot|ClaudeBot|Google-Extended|Applebot-Extended|CCBot|Bytespider|Meta-ExternalAgent'
```

Présent : un groupe `User-agent: GPTBot` (etc.) avec `Disallow: /`. Le tableau de `geo-summary.md` (« Accès des robots IA ») liste chaque robot avec la famille « entraînement ».

## Correction

Cette fiche ne prescrit pas de débloquer : **poser la question au propriétaire du site**, puis appliquer l'option choisie.

| Choix | Effet | À faire |
|---|---|---|
| A. Bloquer l'entraînement, rester citable (le plus courant) | Le contenu n'est pas destiné à l'entraînement ; ChatGPT Search, Perplexity, Claude (recherche), AI Overviews restent possibles | Ne rien changer si les robots de recherche sont autorisés |
| B. Tout autoriser | Contenu utilisable pour l'entraînement et la recherche | Supprimer les groupes d'entraînement |
| C. Bloquer aussi certains robots de collecte massive (CCBot, Bytespider) | Réduit la reprise dans des jeux de données | Garder leurs groupes ; ajouter un blocage au pare-feu car certains robots ne respectent pas toujours robots.txt |

1. Créer une branche Git.
2. Éditer la source du robots.txt (`public/robots.txt` ou `src/pages/robots.txt.ts`, voir la fiche `geo-robots-bots-recherche-bloques`).
3. Pour l'option A, un fichier propre qui bloque l'entraînement **sans** toucher à la recherche :

```text
User-agent: GPTBot
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: Google-Extended
Disallow: /

User-agent: Applebot-Extended
Disallow: /

User-agent: Meta-ExternalAgent
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: *
Allow: /

Sitemap: https://exemple.fr/sitemap-index.xml
```

   Chaque robot ayant son propre groupe, `OAI-SearchBot`, `PerplexityBot`, `Claude-SearchBot`, `Googlebot` et `Bingbot` retombent sur `User-agent: *` et restent autorisés.
4. Pour l'option B : retirer les groupes listés et garder uniquement `User-agent: *` + `Sitemap`.

## Critères d'acceptation

- [ ] Le propriétaire a confirmé par écrit son choix (A, B ou C)
- [ ] `robots.txt` reflète ce choix, sans bloquer un robot de recherche par effet de bord
- [ ] `python3 scripts/geo_check.py` : les robots de famille « recherche » sont « autorisé »
- [ ] Aucune régression : build OK, `robots.txt` en 200 avec `Content-Type: text/plain`

## Vérification après correction

```bash
curl -sI https://SITE/robots.txt | head -5
curl -s https://SITE/robots.txt | grep -iE 'user-agent|disallow'
python3 scripts/geo_check.py https://SITE/ --out /tmp/verif/geo --sample 3
```

## Pièges et retour arrière

- `Google-Extended` et `Applebot-Extended` sont des **jetons** de robots.txt (pas de user-agent réel) : on ne peut pas les tester par requête HTTP.
- Bloquer Google-Extended n'a pas d'effet sur le classement ni sur les AI Overviews, selon Google. Ne pas bloquer `Googlebot` pour obtenir ce résultat.
- robots.txt est une demande de courtoisie : elle ne protège pas un contenu réellement confidentiel (utiliser une authentification).
- Retour arrière : restaurer le fichier via Git ; l'effet sur les robots est progressif (ils relisent le fichier périodiquement).

## Pour aller plus loin

- https://developers.openai.com/api/docs/bots : distinction GPTBot / OAI-SearchBot / ChatGPT-User.
- https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler : ClaudeBot (entraînement) vs Claude-SearchBot.
- https://developers.google.com/search/docs/crawling-indexing/overview-google-crawlers : Google-Extended parmi les robots Google.
- https://developers.google.com/search/docs/appearance/ai-features : conditions d'apparition dans les fonctions IA de Google Search.
