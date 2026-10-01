# Audit Site Astro : feuille de route vers l'audit « ultime »

> Document de cadrage (fait office de spec). Chaque phase a son propre plan d'implémentation détaillé, écrit **au début de la phase** à partir des mesures de la phase précédente. Plan détaillé de la phase 0 : [`2026-09-30-01-phase0-cobaye.md`](2026-09-30-01-phase0-cobaye.md).

## 1. Objectif

Faire de `audit-site-astro` l'audit le plus fiable possible pour un site Astro (+ Convex) : **il trouve tout ce qui est trouvable, ne crie pas au loup, et chaque constat donne une correction exacte.** « Tout trouvé » ne se décrète pas, ça se mesure. D'où le site cobaye.

## 2. Principe central : le site cobaye et la vérité terrain

On construit **deux sites Astro jumeaux**, lancés dans Docker en CI :

| Site | Rôle |
|---|---|
| `cobaye-casse` | Contient volontairement **chaque défaut** du catalogue (§4), avec un identifiant stable (`S07`, `P03`…). |
| `cobaye-propre` | Même structure, **tous les défauts corrigés**. Tout ce que l'audit signale ici est un faux positif. |

Un fichier de **vérité terrain** (`tests/cobaye/verite-terrain.json`) décrit chaque défaut : où il est injecté, dans quelle phase il doit être détecté, et **comment reconnaître sa détection** dans les sorties de l'audit (un « matcher »). Un script de score compare les sorties de l'audit à cette vérité terrain et calcule :

- **Rappel** (sur `casse`) = défauts détectés ÷ défauts attendus dans la phase. Objectif final : 100 % des défauts détectables automatiquement.
- **Faux positifs** (sur `propre`) = matchers qui se déclenchent sur le site corrigé, plus les constats Haute/Critique inattendus. Objectif : 0.
- **Par domaine** : HTTP, SEO technique, GEO, performance, code, sécurité, accessibilité, RGPD.

La CI lance l'audit sur les deux jumeaux à chaque PR et **échoue si le rappel baisse ou si un faux positif apparaît** (système de cliquet : les seuils ne font que monter).

Pourquoi deux jumeaux plutôt qu'un seul site : un détecteur qui signale tout, tout le temps, aurait 100 % de rappel. Seul le jumeau propre le démasque.

## 3. Contraintes globales

- Mac de développement : 16 Go, swap souvent saturé, **a déjà planté** (docker build + Chrome en parallèle). Tout ce qui est lourd (build Docker, build des cobayes, Lighthouse) tourne **en CI GitHub**. En local : tests unitaires Python et scan statique uniquement.
- Python ≥ 3.9, **bibliothèque standard uniquement** pour les scripts de collecte. Bash compatible macOS et Linux (pas de `timeout`, `date -d` avec repli `date -j`).
- Cobayes : Astro ^7.3 (dernière majeure), `@astrojs/node` (standalone) derrière nginx en HTTPS auto-signé ; option `AUDIT_INSECURE_TLS=1` réservée aux tests.
- Aucun secret réel, aucune donnée personnelle dans le dépôt (les « secrets » des cobayes sont construits par concaténation à l'exécution pour ne pas déclencher le push protection de GitHub).
- Workflow : **une branche et une PR par tâche ou groupe de tâches**, CI verte obligatoire avant merge, commits avec `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Chaque nouvelle recommandation Astro est vérifiée dans docs.astro.build et conditionnée à la version installée (`references/astro-optimisations.md`).

## 4. Catalogue des défauts du cobaye (vérité terrain)

Colonne **Phase** : phase à partir de laquelle la détection est exigée. « Base » = déjà détectable par l'outil actuel (la phase 0 mesure si c'est vrai).

### HTTP / serveur (proxy nginx du cobaye cassé)
| ID | Défaut injecté | Détecteur attendu | Phase |
|---|---|---|---|
| H01 | Compression gzip/brotli désactivée | http-checks « Compression HTML \| aucune » | Base |
| H02 | HSTS absent | http-checks | Base |
| H03 | CSP absente | http-checks | Base |
| H04 | `X-Content-Type-Options` absent | http-checks | Base |
| H05 | `Server: nginx/1.x` + `X-Powered-By` exposés | http-checks « version exposée » | Base |
| H06 | `/_astro/*` servis en `Cache-Control: no-cache` | http-checks « asset hashé Astro » | Base |
| H07 | http→https en **302** | http-checks variantes | Base |
| H11 | Page `/lent` avec 1,5 s de TTFB | crawl `slow_ttfb` | Base |
| H12 | `/_image` transformé à chaque requête (pas de cache proxy) | http-checks §4 bis | Base |
| H13 | Site injoignable / domaine inexistant | collecte ❌ « injoignable » (test unitaire) | 0 |

### SEO technique
| ID | Défaut | Détecteur | Phase |
|---|---|---|---|
| S01 | `Sitemap:` relatif dans robots.txt | crawl `robots_sitemap_relative` | Base |
| S02 | Sitemap en `http://` (endpoint basé sur `request.url` derrière proxy) | crawl `sitemap_redirect` | Base |
| S03 | URL 404 dans le sitemap | crawl `sitemap_non200` | Base |
| S04 | URL noindex dans le sitemap | crawl `sitemap_noindex` | Base |
| S05 | Page indexable absente du sitemap | crawl `not_in_sitemap` | Base |
| S06 | Page orpheline | crawl `orphan` | Base |
| S07 | Lien interne vers une 404 | crawl `http_4xx` | Base |
| S08 | Lien interne vers une redirection | crawl `link_to_redirect` | Base |
| S09 | Chaîne de redirections | crawl `redirect_chain` | Base |
| S10 | Redirection 302 permanente de fait | crawl `redirect_temp` | Base |
| S11 | `<title>` absent | crawl `title_missing` | Base |
| S12 | Titles dupliqués | crawl `title_dup` | Base |
| S13 | Title « Accueil » | crawl `title_short` | Base |
| S14 | Meta description absente | crawl `desc_missing` | Base |
| S15 | Meta descriptions dupliquées | crawl `desc_dup` | Base |
| S16 | H1 absent | crawl `h1_missing` | Base |
| S17 | Plusieurs H1 | crawl `h1_multiple` | Base |
| S18 | Canonical absente | crawl `canonical_missing` | Base |
| S19 | Canonical vers une page 404 **non liée** | crawl `canonical_bad_target` | 1 (raté attendu en base) |
| S20 | Canonical en `http://` (Astro.url.href derrière proxy) | crawl `canonical_other` | Base |
| S21 | Page à 5 clics | crawl `deep_page` | Base |
| S22 | Contenu faible sur une page formation | crawl `thin_content` | Base |
| S23 | Liens internes avec UTM | crawl `utm_internal` | Base |
| S24 | Lien vers la variante http | crawl `variant_links` | Base |
| S25 | Image sans alt | crawl `img_no_alt` | Base |
| S26 | Image sans dimensions | crawl `img_no_dims` | Base |
| S27 | JSON-LD invalide | crawl `jsonld_invalid` | Base |
| S28 | Page sans JSON-LD | crawl `no_jsonld` | Base |
| S29 | `lang` absent | crawl `lang_missing` | Base |
| S30 | Viewport absent | crawl `viewport_missing` | Base |
| S31 | Contenu mixte http | crawl `mixed_content` | Base |
| S32 | Lien interne nofollow | crawl `nofollow_internal` | Base |
| S33 | hreflang sans auto-référence | crawl `hreflang_no_self` | Base |
| S34 | Titles quasi identiques (cannibalisation) | crawl `near_dup_titles` | Base |
| S35 | Route SSR dynamique sans 404 (soft 404) | code + test http sous route dynamique | Base (code) / 1 (http) |
| S36 | URL paramétrée indexable (`?tab=`) | crawl `param_indexable` | Base |
| S38 | robots.txt bloque `/_astro/` | crawl `robots_blocks_assets` | Base |

### GEO
| ID | Défaut | Détecteur | Phase |
|---|---|---|---|
| G01 | robots.txt bloque OAI-SearchBot | geo signal | Base |
| G01b | robots.txt bloque PerplexityBot | geo signal | Base |
| G02 | WAF : 403 pour ClaudeBot / Claude-SearchBot | geo « HTTP 403 » | Base |
| G03 | llms.txt avec lien cassé | geo `liens_casses` | Base |
| G04 | Pas d'Organization JSON-LD | geo signal | Base |
| G05 | Pas de sameAs | geo signal | Base |
| G06 | og:site_name incohérent | geo « incohérent » | Base |
| G07 | `max-snippet:0` sur une page | geo « limite les extraits » | Base (dépend de l'échantillon) |
| G08 | Article sans auteur | geo signal | Base |
| G09 | Pas de page à propos | geo signal | Base |
| G10 | Pas de mentions légales | geo signal | Base |
| G11 | Contenu clé dans un îlot `client:only` (invisible sans JS) | code `client:only` / rendu JS | Base (code) / 2 (rendu) |

### Performance
| ID | Défaut | Détecteur | Phase |
|---|---|---|---|
| P01 | Image hero en `loading="lazy"` | crawl `lazy_first_img` | Base |
| P02 | Hero 4000 px brut depuis `public/` | code « servie(s) depuis public/ » | Base |
| P03 | 3 images en priorité haute | http-checks « Images en priorité haute : 3 » | Base |
| P04 | Îlot `client:load` avec un module de 300 Ko | code `client:load` + Lighthouse `unused-javascript` | Base |
| P05 | Google Fonts externes | code | Base |
| P07 | Script bloquant dans `<head>` | Lighthouse « render-blocking » | Base |
| P08 | prefetch absent | code (info) | Base |
| P09 | SSR sans cache de routes (Astro 7) | code | Base |
| P10 | Images responsives non activées | code | Base |
| P11 | `<Picture>` sans AVIF | code | Base |
| P12 | Collection : image en `z.string()` | code | Base |
| P13 | Image Markdown depuis `public/` | code | Base |
| P14 | Logo servi brut depuis un faux « storage Convex » | code + http-checks « non (brute) » | Base |
| P15 | Polices sans API Fonts | code | Base |
| P16 | Compression absente (vue Lighthouse) | Lighthouse « compression » | Base |

### Code Astro / Convex (analyse statique)
| ID | Défaut | Phase |
|---|---|---|
| C01 | Mutation publique sans auth (`convex/leads.ts`) | Base |
| C02 | Query sans validateur `args` | Base |
| C03 | `.filter()` sans index | Base |
| C04 | `.collect()` non borné | Base |
| C05 | `v.any()` | Base |
| C06 | Variable d'env non `PUBLIC_` dans un `<script>` client | Base |
| C07 | `set:html` de contenu utilisateur | Base |
| C08 | `.env` absent du `.gitignore` | Base |
| C10 | Sitemap construit depuis `request.url` | Base |
| C11 | Canonical depuis `Astro.url.href` | Base |
| C12 | Pas de `security.allowedDomains` | Base |
| C13 | Pas de CSP | Base |
| C14 | Pas d'`astro:env` | Base |
| C15 | `trailingSlash` non fixé | Base |
| C16 | `vite.build.sourcemap: true` | Base |
| C17 | Pas de `404.astro` | Base |

### Sécurité (en ligne)
| ID | Défaut | Phase |
|---|---|---|
| X01 | `/.env` servi par nginx | Base |
| X02 | Source maps publiques | Base |
| X03 | Faux secret `sk_live_…` dans le JS client | Base |
| X04 | CORS qui renvoie n'importe quelle origine | Base |
| X06 | `/_image` proxy ouvert (`remotePatterns` sans hostname) | 1 (sonde à corriger) |
| X07 | `/.git/HEAD` servi | Base |

### Accessibilité (Lighthouse, puis axe/pa11y en phase 2)
| ID | Défaut | Phase |
|---|---|---|
| A01 | Contraste insuffisant | Base |
| A02 | Bouton icône sans nom | Base |
| A03 | Niveaux de titres sautés | Base |
| A04 | Lien sans texte | Base |
| A05 | Champ sans label | Base |
| A06 | Zones tactiles trop petites | Base |

### RGPD, liens externes, domaine (nouveaux contrôles)
| ID | Défaut | Phase |
|---|---|---|
| R01 | Script analytics chargé avant consentement | 2 |
| R02 | Cookie de mesure posé sans consentement | 2 |
| E01 | Lien externe cassé | 2 |
| D01 | DMARC absent / SPF permissif (tests unitaires sur réponses DNS simulées) | 2 |

**Non testable dans le cobaye** (honnêteté) : validité/expiration du vrai certificat TLS, données CrUX, Search Console/Bing, présence réelle dans les IA, logs de vrais robots. Ces contrôles sont testés par des tests unitaires sur des données simulées (phase 3).

## 5. Phases

### Phase 0 : fondations mesurables (plan détaillé : `2026-09-30-01-phase0-cobaye.md`)
1. Collecte honnête : pré-vol (site injoignable → ❌ et arrêt), validation du contenu de chaque étape, `SKIP_LIGHTHOUSE`.
2. `AUDIT_INSECURE_TLS=1` (tests HTTPS auto-signé).
3. Tests unitaires stdlib des analyseurs (robots.txt, parseur HTML, scan Astro, score).
4. Cobaye cassé + cobaye propre + nginx + docker compose.
5. Vérité terrain + script de score.
6. Job CI « cobaye » : score publié dans le résumé de la PR, seuils à cliquet.
7. Mesure de référence (baseline) + une issue GitHub par défaut raté.
**Terminé quand** : la CI affiche rappel et faux positifs par domaine, et les seuils bloquent toute régression.

### Phase 1 : combler les trous révélés par le cobaye
Plan écrit à partir des issues de la phase 0. Attendus connus : cible de canonical non crawlée (S19), soft 404 testé en HTTP sous chaque route dynamique (S35), sonde `/_image` avec une vraie image distante (X06), échantillonnage GEO qui rate des pages (G07/G08), résultat d'une étape vide affiché en ✅.
**Terminé quand** : rappel « Base » = 100 % et 0 faux positif.

### Phase 2 : nouveaux contrôles
- **Rendu JS** (`render_check.mjs` avec puppeteer-core, déjà présent via Lighthouse) : HTML brut vs rendu, contenu invisible sans JS (G11).
- **RGPD** dans la même passe : requêtes et cookies posés **avant toute interaction** (R01, R02), bannière sans « Refuser ».
- **Accessibilité axe-core** sur 5 à 10 gabarits (en plus de Lighthouse).
- **Liens externes cassés** (E01), avec limite de débit.
- **Santé du domaine** : SPF, DKIM (sélecteurs courants), DMARC, CAA, DNSSEC (D01).
- **Soft 404 en HTTP** sous chaque segment de route dynamique découvert.
**Terminé quand** : défauts de phase 2 à 100 % sur le cobaye, 0 faux positif.

### Phase 3 : données réelles (optionnelles, clés fournies par l'utilisateur)
Search Console API (indexation, requêtes, cannibalisation réelle), Bing Webmaster API + IndexNow, CrUX API (données terrain), **suivi de visibilité IA** (questions posées via API à Perplexity / OpenAI avec recherche web, comptage des citations de la marque et des concurrents). Testés par tests unitaires sur réponses simulées ; sans clé, l'étape est ⏭️, pas ❌.

### Phase 4 : suivi dans le temps
`compare_audits.py` (corrigés / nouveaux / régressions), workflow planifié mensuel (modèle à copier dans le dépôt du site), **Lighthouse CI avec budgets** dans le CI du site (bloque une PR qui dégrade), rapport HTML visuel partageable.

### Phase 5 : qualité des skills
Evals du skill-creator (avec / sans skill) sur 3 prompts réalistes, dont un sur les sorties du cobaye. Grille : constats justes, regroupement par cause, corrections exécutables, zéro secret. Optimisation des descriptions (déclenchement). **Audit complet du vrai site ILLITH** (code + en ligne) comme test d'acceptation final.

### Phase 6 : diffusion
README anglais (+ français), CHANGELOG, releases semver (tags `v1.2.0`…) avec image Docker taguée, CONTRIBUTING, actions GitHub à jour (Node 24), badge « rappel cobaye » dans le README.

## 6. Définition de « l'audit ultime » (critères d'acceptation finaux)
- Rappel 100 % sur tous les défauts détectables du cobaye, **0 faux positif** sur le jumeau propre, mesurés en CI à chaque PR.
- Temps de collecte < 15 min pour 500 pages ; empreinte < 2 Go de RAM.
- Chaque constat du rapport consolidé a une preuve et une correction exécutable ; les evals des skills passent.
- L'audit du vrai site ILLITH produit un plan d'action que l'utilisateur juge juste (validation humaine).
