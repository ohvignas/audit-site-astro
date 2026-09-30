---
id: geo-mesure-visibilite-ia
titre: Mesurer sa visibilité dans les IA (protocole de test mensuel)
domaine: GEO / IA
severite_type: basse
effort: M
declencheurs: []
sources:
  - https://developers.google.com/search/docs/appearance/ai-features
  - https://blogs.bing.com/webmaster/February-2026/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview
  - https://developers.openai.com/api/docs/bots
  - https://docs.perplexity.ai/guides/bots
---

# Mesurer sa visibilité dans les IA

> **En une phrase** : sans mesure, on ne sait pas si les corrections GEO ont un effet ; un test manuel mensuel, sur des questions réelles, dans les principaux assistants, est l'indicateur le plus honnête disponible.

*Fiche sans déclencheur automatique : elle ne répond à aucun signal de l'outil. À inclure sur demande ou en annexe de tout plan GEO.*

## Pourquoi c'est important

Les réponses des assistants IA varient d'un jour à l'autre, d'un utilisateur à l'autre et d'un pays à l'autre. Il n'existe pas de « position » stable comme dans Google. Aucune métrique unique ne fait référence, et les outils payants de « suivi de visibilité IA » reposent sur des échantillons de requêtes : à prendre comme des indices. Un protocole simple, répété à l'identique chaque mois, avec les mêmes questions, permet de repérer les tendances et de valider (ou non) l'intérêt d'un chantier (accès des robots, contenu, entité). Il faut rester honnête avec le propriétaire : citation non garantie, résultats lents, présence hors site souvent plus déterminante que le code.

## Comment le constater soi-même

Trois sources de données complémentaires :

1. **Test manuel de présence** (protocole ci-dessous).
2. **Logs serveur** : les robots IA viennent-ils, et que reçoivent-ils ?

```bash
zgrep -hoiE 'gptbot|oai-searchbot|chatgpt-user|claudebot|claude-searchbot|claude-user|perplexitybot|perplexity-user|bingbot|googlebot|applebot|duckassistbot|mistralai-user|meta-externalagent|amazonbot|ccbot|bytespider' /var/log/nginx/access.log* | tr A-Z a-z | sort | uniq -c | sort -rn
zgrep -hi 'oai-searchbot\|perplexitybot\|claude-searchbot' /var/log/nginx/access.log* | awk '{print $9}' | sort | uniq -c
```

3. **Trafic référent IA** (logs ou outil d'analyse) : origines `chatgpt.com`, `perplexity.ai`, `gemini.google.com`, `copilot.microsoft.com`, `claude.ai`.

```bash
zgrep -hoE '"https?://(chatgpt\.com|chat\.openai\.com|(www\.)?perplexity\.ai|gemini\.google\.com|copilot\.microsoft\.com|claude\.ai)[^"]*"' /var/log/nginx/access.log* | cut -d/ -f3 | sort | uniq -c | sort -rn
```

Compléments officiels : Google Search Console (les clics et impressions issus des fonctionnalités IA de Google sont comptés dans le rapport Performance « Search ») et le rapport « AI Performance » de Bing Webmaster Tools (citations dans Copilot, en aperçu public).

## Correction

Ce n'est pas un correctif de code, mais un protocole à mettre en place.

1. **Constituer la liste de 10 à 15 questions** que les clients posent réellement (à partir des mails, appels, Search Console, page « Autres questions posées »). Répartir : 4 questions de marque (« que pense-t-on de Exemple SAS ? »), 6 questions de catégorie sans marque (« meilleure agence web à Lyon pour une PME »), 3 à 5 questions de problème (« comment refaire mon site sans perdre mon référencement »).
2. **Fixer les conditions** : navigation privée, compte non connecté si possible, même langue et même pays, recherche web activée dans l'assistant. Noter la date.
3. **Tester chaque question** dans : ChatGPT (recherche activée), Perplexity, Gemini, Copilot, Claude (recherche web activée) et Google (AI Overview / AI Mode). Renseigner le tableau ci-dessous, une ligne par question et par assistant.

| Date | Question | Assistant | Marque citée (oui/non) | URL du site citée | Concurrents cités | Position (1er, 2e…) | Remarque (exact ? erreur ?) |
|---|---|---|---|---|---|---|---|
| 2026-10-01 | (question 1) | ChatGPT | non | — | A, B | — | |

4. **Analyser les écarts** : marque absente mais concurrents cités → regarder quelles sources sont citées (annuaires, avis, articles) : c'est là qu'il faut être présent. Informations fausses → corriger la source (page « à propos », fiche Google Business Profile, Wikidata s'il existe).
5. **Refaire chaque mois** avec les mêmes questions ; garder l'historique dans un tableur. Comparer sur 3 mois plutôt que d'un mois à l'autre.
6. **Lier chaque chantier à un indicateur** : par exemple, après avoir débloqué OAI-SearchBot (fiche `geo-robots-bots-recherche-bloques`), vérifier dans les logs qu'il reçoit des `200` puis observer la citation dans ChatGPT Search.

## Critères d'acceptation

- [ ] Liste de 10 à 15 questions validée par le propriétaire
- [ ] Tableau de résultats initial rempli (mesure de départ) et archivé
- [ ] Test répété à date fixe chaque mois, avec la même méthode
- [ ] Logs ou analytics consultés pour les robots IA et le trafic référent

## Vérification après correction

Chaque mois : compter le nombre de questions où la marque et/ou une URL du site est citée, par assistant, et l'écrire en tête du tableau (« 4/12 questions citées »). Contrôler les logs avec les commandes ci-dessus.

## Pièges et retour arrière

- Un seul test ne prouve rien : les réponses fluctuent. Répéter et ne conclure que sur une tendance.
- Ne pas interroger l'IA avec la marque dans toutes les questions : cela ne mesure que la notoriété.
- Ne pas promettre de résultats chiffrés au client.
- Ne pas automatiser des requêtes en masse sur les assistants sans respecter leurs conditions d'utilisation.
- Retour arrière : sans objet (protocole).

## Pour aller plus loin

- https://developers.google.com/search/docs/appearance/ai-features : fonctions IA de Google Search et suivi dans Search Console.
- https://blogs.bing.com/webmaster/February-2026/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview : citations dans Copilot.
- https://developers.openai.com/api/docs/bots : identifier les robots d'OpenAI dans les logs.
- https://docs.perplexity.ai/guides/bots : identifier les robots de Perplexity.
