<div align="center">

# 🔍 Audit Site Astro

**L'audit complet de votre site Astro, de A à Z, en une commande.**
Performance · SEO technique · Contenu · GEO (visibilité dans les IA) · Code Astro/Convex · Sécurité · Accessibilité

[![Build & test](https://github.com/ohvignas/audit-site-astro/actions/workflows/docker.yml/badge.svg)](https://github.com/ohvignas/audit-site-astro/actions/workflows/docker.yml)
[![Licence MIT](https://img.shields.io/badge/licence-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue?logo=docker)](https://github.com/ohvignas/audit-site-astro/pkgs/container/audit-site-astro)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-d97757)](#-option-2--plugin-claude-code-audit-complet-avec-plan-daction)

</div>

---

## Pourquoi ?

Un site Astro « rapide par défaut » peut quand même :
- servir son HTML **sans compression** (l'adapter Node ne compresse pas) ;
- publier un **sitemap en `http://`** parce que le serveur tourne derrière un proxy ;
- renvoyer **200 sur des pages qui n'existent pas** (soft 404 des routes SSR dynamiques) ;
- afficher des **images de plusieurs Mo** venues du storage Convex, jamais redimensionnées ;
- hydrater un widget de chat en `client:load` et **charger 400 Ko de JS inutile** ;
- être **invisible pour ChatGPT ou Perplexity** à cause d'un pare-feu ou d'une règle Cloudflare.

Ces cas ont tous été trouvés sur de vrais sites. Cet outil les détecte automatiquement, avec la preuve (URL, mesure, `fichier:ligne`) et la correction exacte.

## Ce qui est vérifié

| Domaine | Exemples de contrôles |
|---|---|
| ⚡ **Performance** | Lighthouse mobile + desktop, élément LCP, TBT, CLS, TTFB avec et sans cache, compression, cache des assets `/_astro/`, îlots `client:*`, poids du bundle, polices (API Fonts), cache de routes Astro 7, scripts tiers |
| 🖼️ **Images Astro** | `<Image>`/`<Picture>` vs `<img>` brut, images responsives (`image.layout`), prop `priority` sur l'image LCP (et une seule), AVIF, images de `public/` et du Markdown jamais optimisées, schéma `image()` des collections, domaines distants autorisés, `/_image` recalculé à chaque requête (mesuré en ligne), service passthrough, SVGO |
| 🔎 **SEO technique** | Crawl complet (jusqu'à 500+ pages), statuts, redirections, canonicals, sitemap vs pages réelles, orphelines, profondeur, robots.txt, soft 404, données structurées, variantes http/www |
| ✍️ **Contenu** | Titles, metas, H1, contenus faibles, cannibalisation, maillage et ancres, E-E-A-T, pages légales |
| 🤖 **GEO / IA** | Accès de 19 robots IA (GPTBot, OAI-SearchBot, ClaudeBot, PerplexityBot, Google-Extended…) dans robots.txt **et** en conditions réelles (WAF/CDN), llms.txt, entités schema.org, contenu « citable », pages de confiance |
| 🧱 **Code Astro + Convex** | Config (`site`, `output`, `trailingSlash`, images), `<img>` bruts, canonical fragile, routes dynamiques sans 404, variables d'env côté client, mutations Convex sans auth, requêtes sans index, `npm audit`, `astro check` |
| 🔐 **Sécurité** (non intrusive) | En-têtes (CSP, HSTS…), TLS, `.env` / `.git` / source maps exposés, secrets dans le JS livré, CORS |
| ♿ **Accessibilité** | Contrastes, alt, titres, ARIA, zones tactiles, checklist clavier/focus |

---

## 🚀 Option 1 : Docker (une commande, rien à installer)

```bash
docker run --rm --memory=2g -v "$PWD/audits:/audits" ghcr.io/ohvignas/audit-site-astro https://votre-site.fr
```

Au bout de 5 à 15 minutes, ouvrez **`audits/votre-site.fr/<date>/RAPPORT.html`** dans votre navigateur (ou `RAPPORT-BRUT.md`).

Pour analyser **aussi le code** du projet (monté en lecture seule, jamais modifié) :

```bash
docker run --rm --memory=2g -v "$PWD/audits:/audits" -v /chemin/vers/mon-projet-astro:/projet:ro ghcr.io/ohvignas/audit-site-astro https://votre-site.fr
```

<details>
<summary>Options</summary>

| Variable | Défaut | Rôle |
|---|---|---|
| `MAX_PAGES` | 500 | Pages crawlées au maximum |
| `LH_PAGES` | 5 | Pages mesurées par Lighthouse (mobile + desktop) |
| `RUNS` | 1 | Passages Lighthouse par page (3 = médiane plus fiable) |
| `MIN_FREE_MB` | 1200 | RAM minimale avant de lancer Chrome (protège la machine) |
| `PSI_API_KEY` | — | Clé PageSpeed Insights (gratuite) pour ajouter les données terrain CrUX |
| `SKIP_LIGHTHOUSE` | — | Saute l'étape Lighthouse (⏭️) |

**Codes de sortie** : 0 = tout est ✅/⚠️/⏭️ ; 1 = au moins une étape ❌ ; 2 = site injoignable ou page d'accueil en erreur 5xx (rien n'est collecté).

Exemple : `docker run --rm --memory=2g -e LH_PAGES=8 -e RUNS=3 -v "$PWD/audits:/audits" ghcr.io/ohvignas/audit-site-astro https://votre-site.fr`
</details>

<details>
<summary>Construire l'image soi-même</summary>

```bash
git clone https://github.com/ohvignas/audit-site-astro.git
cd audit-site-astro
docker build -t audit-site-astro .
docker run --rm --memory=2g -v "$PWD/audits:/audits" audit-site-astro https://votre-site.fr
```
</details>

## 🧠 Option 2 : plugin Claude Code (audit complet avec plan d'action)

Docker produit un **rapport brut** : tous les signaux, triés par sévérité. Le plugin va plus loin. L'agent confirme chaque signal, écarte les faux positifs, regroupe les problèmes par cause, lit votre code et rédige un **rapport priorisé** : notes par domaine, top 10 des actions, feuille de route, correctifs `fichier:ligne`. Il peut ensuite **appliquer les corrections lot par lot, après votre accord**.

Dans Claude Code :

```text
/plugin marketplace add ohvignas/audit-site-astro
/plugin install audit-site-astro@audit-site-astro
```

Puis, dans le dossier de votre projet :

```text
Fais un audit complet de https://votre-site.fr, le code est dans ce dossier.
```

ou directement `/audit-site-astro:audit-complet`.

| Skill | Usage |
|---|---|
| `audit-complet` | Orchestrateur : collecte, 7 analyses, rapport consolidé, corrections |
| `audit-performance` | Core Web Vitals, Lighthouse, cache, îlots, images |
| `audit-seo-technique` | Indexation, sitemap, canonicals, soft 404, maillage, logs Googlebot |
| `audit-seo-contenu` | Intention, titles/metas réécrits, cannibalisation, plan de contenu |
| `audit-geo` | Robots IA, entités, contenu citable, protocole de test ChatGPT/Perplexity |
| `audit-code-astro` | Config Astro, architecture, Convex (auth, index), dépendances |
| `audit-securite` | En-têtes, exposition, secrets, fonctions Convex publiques, serveur |
| `audit-accessibilite` | WCAG 2.2 AA / RGAA, tests auto et manuels |

Les skills suivent le format standard des Agent Skills (`SKILL.md`) : ils fonctionnent aussi avec d'autres agents compatibles.

**Cursor** : installer le plugin depuis le dépôt ; voir `.cursor-plugin/`.

## 🛠️ Option 3 : sans Docker

Prérequis : `python3`, `curl`, `node`/`npx`, Google Chrome ou Chromium.

```bash
git clone https://github.com/ohvignas/audit-site-astro.git
bash audit-site-astro/plugins/audit-site-astro/skills/audit-complet/scripts/collect_all.sh https://votre-site.fr [/chemin/du/projet]
```

---

## 📂 Ce que vous obtenez

```
audits/votre-site.fr/
├── index.html                 ← historique des audits, avec le graphique des notes
└── 2026-09-30/
    ├── RAPPORT.html           ← rapport à lire dans un navigateur (un seul fichier, sans JavaScript)
    ├── RAPPORT.pdf            ← le même rapport, à envoyer par e-mail
    ├── RAPPORT-BRUT.md        ← synthèse automatique, triée par sévérité
    ├── RAPPORT-AUDIT.md       ← rapport priorisé (plugin Claude Code)
    ├── CORRECTIONS/           ← à donner à votre agent de code
    │   ├── LISEZ-MOI.md       ← méthode et règles de sécurité
    │   ├── 00-PLAN.md         ← checklist priorisée
    │   ├── NN-<id>.md         ← une fiche par correction
    │   ├── annexes/           ← fiches complémentaires
    │   └── index.json
    └── data/
        ├── COLLECTE.md        ← statut de chaque étape
        ├── crawl/             ← pages.csv, issues.json, summary.md
        ├── perf/              ← rapports Lighthouse JSON + synthèse
        ├── http/              ← en-têtes, compression, TTFB, TLS
        ├── geo/               ← robots IA, llms.txt, entités
        ├── securite/          ← fichiers exposés, secrets, CORS
        └── code/              ← scan Astro/Convex, npm audit, astro check
```

Extrait réel de `RAPPORT-BRUT.md` :

```text
🟧 Haute
- Performance — Activez la compression de texte (gain estimé 2080 ms, mobile)
- SEO technique — URL du sitemap qui redirigent (souvent http:// ou slash final incohérent) — 38
- SEO technique — Pages en erreur 4xx (liens internes cassés si liées) — 1
  - `url: /ressources/guide-ia-8h — status: 404 — liens_depuis: ['/catalogue']`
🟨 Moyenne
- Performance — Réduisez les ressources JavaScript inutilisées (426 Ko) — ChatBubble.js
- SEO technique — Directive Sitemap relative dans robots.txt (Google exige une URL absolue)
```

## 🛠️ Corriger le site avec son agent

Chaque audit produit un dossier `CORRECTIONS/` : une fiche par problème, avec l'explication, les étapes, les critères de réussite et la vérification. Elles s'appuient sur une base de 142 fiches (performance, SEO, sécurité, accessibilité, GEO, contenu, code, serveur, Convex). Donnez ce dossier à votre agent de code.

```text
Ouvre ton projet dans Claude Code ou Cursor et dis : applique les corrections du dossier
audits/votre-site.fr/2026-09-30/CORRECTIONS/ en suivant LISEZ-MOI.md
```

L'agent travaille sur une branche Git, fait un commit par fiche, et vous demande votre accord avant tout changement sensible : problème critique, infrastructure (serveur, DNS, pare-feu), textes éditoriaux ou juridiques. Si vous relancez un audit, `CORRECTIONS/` est régénéré ; créez un fichier `CORRECTIONS/.garder` pour conserver le vôtre (le nouveau est alors écrit dans `CORRECTIONS-<horodatage>/`).

## 📄 Rapports

- **`RAPPORT.html`** : le rapport complet, avec un « Plan de correction » et des « Guides de correction » en annexe. Un seul fichier autonome, sans JavaScript.
- **`RAPPORT.pdf`** : la même chose en A4, produite avec Chrome. Sans Chrome, ou si la mémoire est trop juste, l'étape est sautée avec un ⚠️ et le reste de l'audit continue.
- **`audits/votre-site.fr/index.html`** : l'historique des audits du site, avec l'évolution des notes. Il est mis à jour à chaque audit.

**Partager** : envoyez le PDF, ou hébergez `RAPPORT.html` (il n'a besoin d'aucun autre fichier). Le rapport détaille des failles : ne le publiez pas sur un site ouvert à tous.

## 📚 Calé sur la documentation officielle

Les contrôles Astro suivent [docs.astro.build](https://docs.astro.build) (Astro 7). Chaque recommandation tient compte de la **version installée** : l'outil ne propose jamais une option qui n'existe pas dans votre version. Il indique plutôt ce que la montée de version apporterait. Détail et versions : [`astro-optimisations.md`](plugins/audit-site-astro/skills/audit-complet/references/astro-optimisations.md).

## 🛡️ Principes

- **Lecture seule** : l'audit ne modifie jamais le site ni le code. Les corrections (plugin) ne sont appliquées qu'après votre accord, sur une branche Git, lot par lot.
- **Non intrusif** : crawl poli (délai entre requêtes), sonde de sécurité en simples requêtes GET. À utiliser **uniquement sur vos propres sites** ou avec une autorisation.
- **Aucun secret dans les rapports** : les noms de variables sont cités, jamais leurs valeurs.
- **Économe en RAM** : les étapes tournent une par une, un seul Chrome à la fois. La RAM est vérifiée avant chaque mesure : l'outil s'arrête proprement plutôt que de faire planter la machine.
- **Sans dépendance exotique** : Python (bibliothèque standard uniquement), bash, curl, Lighthouse.

## ❓ FAQ

<details>
<summary>Ça marche sur un site qui n'est pas en Astro ?</summary>

Oui pour le crawl SEO, le GEO, le HTTP, la sécurité et Lighthouse : ils regardent le site en ligne, quelle que soit sa technologie. Le scan de code, lui, est spécifique à Astro (+ Convex).
</details>

<details>
<summary>Pourquoi pas de données PageSpeed Insights par défaut ?</summary>

Sans clé, l'API PageSpeed renvoie presque toujours « 429 Too Many Requests ». Lighthouse tourne donc en local dans le conteneur. Avec une clé gratuite (`-e PSI_API_KEY=…`), on ajoute les données terrain des vrais visiteurs (CrUX), si le site a assez de trafic.
</details>

<details>
<summary>Comment partager le rapport ?</summary>

Envoyez `RAPPORT.pdf`, ou hébergez `RAPPORT.html` : c'est un fichier autonome, sans JavaScript. Le rapport décrit des failles : réservez-le à des personnes de confiance (accès protégé, pas de page publique). Dans Claude Code, l'agent peut aussi le publier comme artefact privé.
</details>

<details>
<summary>Mon Mac rame pendant l'audit</summary>

Lighthouse lance Chrome (0,5 à 1 Go). Limitez Docker Desktop à 4 Go (*Settings → Resources*), gardez `--memory=2g`, fermez les applications lourdes ou réduisez `-e LH_PAGES=2`. L'outil attend puis s'arrête proprement si la RAM libre passe sous `MIN_FREE_MB`.
</details>

<details>
<summary>Le rapport dit que les robots IA sont bloqués alors que robots.txt les autorise</summary>

C'est le test « réponse réelle » : votre pare-feu ou CDN (Cloudflare « Block AI bots », règles de l'hébergeur) renvoie 403 ou une page de challenge. Confirmez dans les logs du serveur : certains pare-feu bloquent les faux robots (le test simule le user-agent) mais laissent passer les vrais, dont l'IP est vérifiée.
</details>

## Banc d'essai (cobaye)

![rappel cobaye](https://img.shields.io/badge/rappel%20cobaye-89%25-yellow)

Deux sites Astro de test (`tests/cobaye/casse`, avec des défauts étiquetés, et `tests/cobaye/propre`, son jumeau corrigé) mesurent à chaque PR ce que l'audit détecte et ce qu'il signale à tort.

Score actuel (2026-09-30) : **89 % des défauts connus détectés, 2 faux positifs**. Les seuils ne peuvent que monter.

Détail et pistes : [docs/cobaye-baseline.md](docs/cobaye-baseline.md) · fonctionnement : [tests/cobaye/README.md](tests/cobaye/README.md).

---

## 🤝 Contribuer

Issues et pull requests bienvenues : nouveaux contrôles, faux positifs à corriger, support d'autres adapters (Vercel, Netlify, Cloudflare) ou backends.

## Licence

[MIT](LICENSE) — créé par [ILLITH](https://illith.com).
