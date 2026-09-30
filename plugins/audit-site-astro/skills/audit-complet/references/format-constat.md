# Format commun d'un constat

Tous les rapports de domaine (`rapports/*.md`) utilisent **exactement** ce bloc, pour que le rapport consolidé puisse les agréger et les trier.

```markdown
### [PERF-003] Le HTML, le CSS et le JS sont servis sans compression
- **Sévérité** : Haute
- **Impact** : ~790 Ko de plus à télécharger par visite ; Lighthouse estime 2,1 s de gain sur mobile (LCP, FCP).
- **Effort** : S (< 1 h)
- **Preuve** : `curl -sI -H 'Accept-Encoding: br, gzip' https://site.fr/` → aucun `content-encoding` ; data/perf/pagespeed-summary.md « Activez la compression de texte — 789 Kio ».
- **Correction** : activer la compression au reverse proxy.
  - Caddy : `encode zstd gzip` dans le bloc du site.
  - nginx : `gzip on; gzip_types text/css application/javascript application/json image/svg+xml; gzip_min_length 1024;` (+ `brotli on;` si le module est présent).
  - Si aucun proxy n'est configurable : middleware de compression dans le serveur Node.
- **Vérification** : `curl -sI -H 'Accept-Encoding: br, gzip' https://site.fr/ | grep -i content-encoding` renvoie `br` ou `gzip` ; relancer lighthouse_run.sh.
- **Risque** : très faible. Retour arrière : retirer la directive et recharger le proxy.
```

## Préfixes d'ID

| Préfixe | Domaine |
|---|---|
| PERF | Performance |
| SEO | SEO technique |
| CONT | Contenu |
| GEO | Visibilité IA |
| CODE | Qualité du code Astro / Convex |
| SEC | Sécurité |
| A11Y | Accessibilité |

## Sévérités

| Sévérité | Définition | Exemples |
|---|---|---|
| **Critique** | Casse le site, le désindexe, expose des données ou un secret, faille exploitable maintenant | robots.txt `Disallow: /`, `.env` public, clé de déploiement dans le JS, mutation Convex d'administration sans auth |
| **Haute** | Perte nette de trafic, de conversions ou de sécurité, mesurée sur le site | LCP mobile > 4 s, pas de compression, sitemap en http, soft 404 en masse, robots IA de recherche bloqués |
| **Moyenne** | Gain réel mais limité, ou risque qui grandira | meta descriptions manquantes, `client:load` superflu, `.filter` sans index sur une table qui grossit |
| **Basse** | Finition, bonne pratique | title un peu long, favicon manquant, `lastmod` absent |

`Info` sert aux observations qui n'appellent pas d'action : on ne les note pas.

## Règles d'écriture

- **Preuve obligatoire** : une mesure, une commande reproductible, une URL ou un `fichier:ligne`. Au-delà de 10 URL : en citer 10, puis « et N autres » avec le chemin du fichier de données.
- **Correction exécutable** : quelqu'un qui ne connaît pas le projet doit pouvoir l'appliquer. Donner le code ou la config exacte, adaptée au projet (lire le fichier avant de proposer un diff).
- **Un constat par cause**, pas par symptôme. Exemple : « le sitemap est généré depuis l'origine de la requête » explique les 38 URL http du sitemap, les canonicals http et l'avertissement Lighthouse sur robots.txt. On l'écrit une seule fois, avec tous les symptômes en preuve.
- **Faux positifs** : si un script signale un problème qui n'en est pas un, l'écarter et l'expliquer en une ligne dans une section « Écartés » en fin de rapport.
- **Pas de secret** dans les preuves : nom de variable ou de fichier, jamais la valeur.
