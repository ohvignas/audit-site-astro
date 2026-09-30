---
name: audit-complet
description: Audit A→Z d'un site Astro (souvent avec backend Convex, SSR Node derrière un proxy) — performance et Core Web Vitals, serveur/cache/compression, SEO technique, contenu, GEO (visibilité dans ChatGPT, Perplexity, Claude, Gemini, AI Overviews), qualité du code Astro/Convex, sécurité, accessibilité — avec rapport priorisé, plan d'action concret (fichier:ligne, code, commande) puis corrections après validation. Utilise ce skill dès que l'utilisateur demande un audit, un check-up, un bilan, un diagnostic ou une optimisation globale de son site, veut savoir s'il est « optimisé », « rapide », « bien référencé », « visible dans les IA », ou dit « audite mon site », « vérifie tout », « de A à Z », « qu'est-ce qu'il faut améliorer » — même s'il ne cite pas Astro. Pour un seul domaine, préférer audit-performance, audit-seo-technique, audit-seo-contenu, audit-geo, audit-code-astro, audit-securite ou audit-accessibilite.
---

# Audit complet — site Astro (+ Convex)

Objectif : un rapport **priorisé et actionnable**. Chaque constat donne sa preuve (mesure, URL, fichier:ligne), la correction exacte et la façon de vérifier qu'elle marche. On mesure avant d'affirmer : pas de constat « de principe » sans donnée qui le montre sur CE site.

Les scripts de collecte sont dans `scripts/`, dans le dossier de ce skill (le chemin s'affiche au chargement : « Base directory for this skill »). Les 7 skills de domaine du plugin s'appuient sur les mêmes données.

## 0. Règles (à lire avant de toucher à quoi que ce soit)

- **Lecture seule pendant l'audit.** On n'édite ni code, ni config, ni serveur avant l'étape 7 et l'accord explicite de l'utilisateur. Un audit qui modifie en douce n'est plus fiable, et un site en production peut casser.
- **Dossier d'audit hors du dossier servi.** Par défaut `~/audits-site/<hôte>/<date>/`. Jamais dans `public/`, `dist/` ou la racine web : le rapport contient des détails sensibles (failles, versions, chemins).
- **Aucun secret dans le rapport.** Ne jamais recopier la valeur d'un `.env`, d'une clé Convex (`CONVEX_DEPLOY_KEY`), d'un token, d'un mot de passe. Citer le **nom** de la variable et le fichier, pas la valeur.
- **Ne jamais écraser le `dist/` servi.** Le build d'audit va dans le dossier d'audit (`astro build --outDir …`, déjà géré par `project_checks.sh`).
- **Crawl poli.** Délai de 0,3 s entre requêtes, 500 pages max par défaut. Sonde de sécurité uniquement sur le site de l'utilisateur, en GET simples.
- **macOS vs Linux.** Pas de commande `timeout` sur macOS. Dans un shell zsh avec nvm « lazy », lancer npx via `bash -c '…'` si `npx` échoue avec `_nvm_lazy_load`.
- **Ménager la RAM** (un audit a déjà fait planter un Mac de 16 Go) :
  - la collecte tourne **une étape à la fois**. Ne jamais lancer deux `collect_all.sh` ou `lighthouse_run.sh` en même temps, ni les faire tourner pendant un `docker build` ou un build Astro ;
  - chaque Chrome de Lighthouse prend 0,5 à 1 Go. Le script vérifie la RAM libre avant chaque mesure (`MIN_FREE_MB`, 1 200 par défaut) et s'arrête proprement si elle manque ;
  - les **sous-agents parallèles** servent uniquement à l'analyse (lecture de fichiers), jamais à la collecte ;
  - avant de lancer : `vm_stat` (macOS) ou `free -m` (Linux). Si moins de 2 Go sont disponibles, proposer à l'utilisateur de fermer les applications lourdes (navigateurs, IDE, Docker Desktop, outils Adobe) ou de réduire `LH_PAGES` ;
  - ne pas construire l'image Docker localement sur une machine chargée : l'intégration continue GitHub la construit.

## 1. Cadrage (2 minutes, sans questionner l'utilisateur pour ce qu'on peut détecter)

1. **URL du site** : fournie par l'utilisateur, sinon lire `site` dans `astro.config.*`, sinon la demander.
2. **Racine du projet** : dossier contenant `astro.config.*` et `package.json`. Chercher d'abord le répertoire courant, puis `find ~ /var/www /srv /opt -maxdepth 4 -name 'astro.config.*' -not -path '*/node_modules/*' 2>/dev/null`.
3. **Environnement** : production ou préproduction ? Adapter (`@astrojs/node` = serveur Node derrière nginx/Caddy/Traefik ?) et hébergement de Convex (cloud `*.convex.cloud` ou auto-hébergé) → à lire dans `package.json`, `astro.config.*`, `.env*` (noms des variables seulement), `docker-compose.yml`, config du proxy (`/etc/nginx/sites-enabled/`, `Caddyfile`).
4. **Outils** : `for t in node npx python3 curl openssl git; do command -v $t >/dev/null && echo "$t OK" || echo "$t ABSENT"; done`. Chrome pour Lighthouse : le script le trouve seul ; sur un serveur sans Chrome, `npx -y @puppeteer/browsers install chrome-headless-shell@stable`, puis `export CHROME_PATH=…`.
5. **Contexte business** (facultatif, améliore contenu et GEO) : activité, cibles, 5 à 10 requêtes/questions sur lesquelles l'utilisateur veut être trouvé, zone géographique. S'il ne répond pas, déduire du site (titres, H1, offres) et le signaler.

## 2. Collecte : une commande

```bash
bash "<dossier du skill>/scripts/collect_all.sh" https://site.fr /chemin/du/projet
# options : MAX_PAGES=800  LH_PAGES=8  RUNS=3 (médiane Lighthouse)  BUILD=1 (build d'audit + poids du bundle)  PSI_API_KEY=…
```

Durée typique : 5 à 15 minutes. Le script écrit `data/COLLECTE.md` avec le statut de chaque étape. **Lire ce fichier d'abord**, puis le code de sortie du script :

- **0** : toutes les étapes sont ✅/⚠️/⏭️. Passer à l'analyse.
- **1** : au moins une étape est ❌ (sortie absente ou inexploitable). Les autres données restent utilisables : continuer l'analyse, dire clairement ce qui manque, corriger la cause si possible (voir « Dépannage » en bas) et relancer cette étape seule.
- **2** : le pré-vol a échoué (site injoignable ou page d'accueil en erreur 5xx). Rien n'a été collecté : vérifier l'adresse, le DNS et le certificat avec l'utilisateur avant de relancer.

| Étape | Script | Produit (dans `data/`) |
|---|---|---|
| HTTP | `http_checks.sh` | `http/http-checks.md` : variantes d'hôte, TTFB avec et sans cache, compression, cache des `/_astro/`, en-têtes de sécurité, TLS, fichiers techniques, test de soft 404 |
| Crawl | `crawl_site.py` | `crawl/pages.json`, `pages.csv`, `issues.json`, `summary.md` : statuts, redirections, titles, metas, H1, canonicals, sitemap vs pages, orphelines, profondeur, maillage, images, JSON-LD, îlots Astro |
| GEO | `geo_check.py` | `geo/geo.json`, `geo-summary.md` : robots.txt par robot IA, réponse réelle du serveur/WAF, llms.txt, entités schema, extractibilité, pages de confiance |
| Sécurité | `security_probe.sh` | `securite/security-probe.md` : fichiers exposés, source maps, secrets dans le JS, CORS |
| Lighthouse | `lighthouse_run.sh` → `pagespeed.py` | `perf/pagespeed-summary.md` : scores, LCP/CLS/TBT, élément LCP, opportunités chiffrées, tiers ; mobile + desktop |
| Projet | `project_checks.sh` | `code/project-checks.md` : versions, `npm outdated`, `npm audit`, `astro check`, build d'audit |
| Code | `astro_scan.py` | `code/code-scan.md` : config Astro, hydratation, `<img>` bruts, head SEO, soft 404, sitemap/robots, env côté client, Convex (auth, args, index), bundle |

L'API PageSpeed sans clé renvoie quasi toujours 429 : Lighthouse local est la voie par défaut. Avec une `PSI_API_KEY` (gratuite), on obtient en plus les **données terrain CrUX**, si le site a assez de trafic.

## 3. Analyse par domaine

Pour chaque domaine, charger le skill correspondant et suivre sa checklist **en réutilisant les données déjà collectées** (ne pas recrawler). Chaque skill écrit `rapports/<domaine>.md` au format commun.

| Domaine | Skill | Données principales | Fichier |
|---|---|---|---|
| Performance | `audit-performance` | perf/, http/, code/ (bundle, îlots, images) | `rapports/performance.md` |
| SEO technique | `audit-seo-technique` | crawl/, http/, code/ (config, routes, sitemap) | `rapports/seo-technique.md` |
| Contenu | `audit-seo-contenu` | crawl/pages.json + lecture des pages clés | `rapports/seo-contenu.md` |
| GEO / IA | `audit-geo` | geo/, crawl/, logs serveur | `rapports/geo.md` |
| Code Astro/Convex | `audit-code-astro` | code/ + lecture du code | `rapports/code.md` |
| Sécurité | `audit-securite` | securite/, http/, code/ | `rapports/securite.md` |
| Accessibilité | `audit-accessibilite` | perf/ (catégorie a11y), code/, pa11y | `rapports/accessibilite.md` |

Si des sous-agents sont disponibles, lancer les 7 domaines **en parallèle**. Chacun reçoit le chemin de son skill, le dossier d'audit et l'URL, et ne fait que lire et écrire son rapport. Sinon, les traiter dans l'ordre du tableau.

**Options Astro : se caler sur la version installée.** `references/astro-optimisations.md` recense les leviers d'optimisation vérifiés dans la documentation officielle (images responsives, `priority`, API Fonts, cache de routes, `allowedDomains`, CSP…) avec leur version d'apparition. Ne recommander que ce qui existe dans la version du projet. Sinon, en faire un argument pour la montée de version.

**Vérifier avant d'affirmer.** Les scripts produisent des *indices*. Avant de les écrire comme constats, confirmer les plus importants à la main : un `curl -sI`, l'ouverture du fichier signalé, la lecture de la page. Exemple : un « .filter sans index » sur une table de 20 lignes est une remarque basse, pas une urgence. Écarter les faux positifs et dire pourquoi.

## 4. Format commun des constats

Voir `references/format-constat.md` (à suivre exactement : le rapport consolidé les agrège automatiquement). En bref : ID `DOM-NNN`, titre factuel, sévérité (Critique/Haute/Moyenne/Basse), impact, effort (S/M/L), preuve, correction précise (fichier:ligne, code, commande), vérification, risque et retour arrière.

## 5. Rapport consolidé

Écrire `RAPPORT-AUDIT.md` à la racine du dossier d'audit, à partir de `assets/modele-rapport.md` :

1. **Note par domaine et note globale** selon `references/notation.md` (barème transparent : 100 moins les pénalités). Les scores Lighthouse sont affichés à part, jamais mélangés.
2. **Top 10 des actions** par ratio impact / effort. Les P0 (site cassé, désindexation, secret exposé, faille exploitable) passent toujours en tête.
3. **Feuille de route** : *Cette semaine* (P0 + quick wins S), *Ce mois-ci* (M), *Ce trimestre* (L + chantiers de contenu).
4. **Tous les constats**, regroupés par domaine, triés par sévérité.
5. **Annexes** : chemins des données brutes, pages mesurées, limites de l'audit (ce qui n'a pas pu être testé, et pourquoi).

Ton : direct, concret, sans jargon inutile. L'utilisateur doit pouvoir confier chaque action à quelqu'un (ou à son agent) sans autre explication.

## 6. Restitution dans le chat

Court : notes par domaine, les 5 actions prioritaires (une ligne chacune, avec le gain attendu), le chemin du rapport. Puis proposer les corrections **par lots** : « Lot 1 — quick wins sans risque (≈ 30 min) : A, B, C. Je les applique ? »

## 7. Corrections (uniquement après un « oui » explicite, lot par lot)

1. **Sauvegarde** : `git status` propre, sinon demander. Créer une branche `audit/<date>-lot-N`. Pour la config serveur, faire une copie datée du fichier avant modification.
2. **Un changement = un commit** avec un message clair. Aucune modification du `dist/` servi ni du serveur de production sans accord séparé.
3. **Vérifier** : `astro check` + build d'audit, puis re-mesurer ce qui est concerné (relancer le script du domaine, ou `curl`). Montrer l'avant/après.
4. **Déploiement** : proposer, ne pas le faire seul. Après le déploiement, re-mesure en ligne.
5. Tenir `CHANGELOG-AUDIT.md` dans le dossier d'audit : lot, fichiers, commit, mesure avant/après, comment revenir en arrière.

Quick wins typiques, à faible risque, sur ce type de site : compression brotli/gzip au proxy, `Sitemap:` absolu dans robots.txt, URL du sitemap en https, title de l'accueil, `client:load` → `client:idle`/`client:visible` sur les widgets, meta descriptions manquantes, favicon. À risque, à faire sur une branche et à tester : CSP, refonte du rendu des images Convex, passage de pages en `prerender`, changement de `trailingSlash`.

## 8. Re-audit

Relancer `collect_all.sh` avec un nouveau dossier daté, puis comparer les notes et les constats avec l'audit précédent (fermés / nouveaux / régressions) dans une section « Évolution » du rapport.

## Dépannage de la collecte

- `pré-vol` ❌ (code 2) → site injoignable (nom de domaine, DNS, certificat TLS, serveur arrêté) ou page d'accueil en 5xx : aucune donnée n'est collectée. Vérifier l'URL exacte (`https://…`) et l'état du site avec l'utilisateur, puis relancer. Un ⚠️ HTTP 4xx (pare-feu, page protégée) ne bloque pas l'audit.
- `lighthouse` ❌ « Chrome introuvable » → installer chrome-headless-shell (voir §1) ou fournir `PSI_API_KEY`.
- `crawl` très long → `MAX_PAGES=200`. Site derrière un WAF qui bloque → le signaler, crawler depuis le serveur avec l'URL interne si possible.
- `projet` : « node_modules absent » → proposer `npm ci` (modifie `node_modules/` seulement, accord requis sur un serveur de production).
- `code` sans bundle → relancer avec `BUILD=1` si les variables de build sont disponibles.
- Une sortie vide ou étrange → lire `data/.log-<étape>.txt` avant toute conclusion.
