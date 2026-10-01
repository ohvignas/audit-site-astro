# Mesure de référence du banc d'essai cobaye (phase 0)

- **Date** : 2026-09-30
- **Commit mesuré** : `50c78cb`
- **Exécution CI** : GitHub Actions, run `36722306289` (les 3 jobs sont verts)
- **Sondes** : collecte stricte sur les deux jumeaux (`casse` et `propre`) ; un audit partiel (fichier de données manquant, étape ❌) est rejeté au lieu d'être compté.

## Décisions de mesure

- **Faux positifs** : pour évaluer le jumeau `propre`, le scorer retire des matchers les filtres propres au cobaye cassé (`contient`, `ou_contient`, `exemple_contient` : emplacements qui n'existent que dans `casse`), sauf si le défaut fournit un `matcher_propre`. Un matcher qui se déclenche encore sur `propre` est un faux positif. Les défauts marqués `"propre": "ignorer"` (ex. C07) sont exclus de cette mesure.
- **Collecte stricte** : un dossier d'audit incomplet est rejeté (`valider_audit`), il n'est pas compté comme « non détecté ». Les 11 ratés ci-dessous sont donc de vrais trous de détection.
- **Cliquet** : `tests/cobaye/seuils.json` reprend chaque ratio mesuré arrondi vers le bas à 2 décimales. Une PR ne peut que les égaler ou les dépasser.

## Résultat

**Rappel global : 90/101 (89%)** · faux positifs : 2 · inattendus (propre) : 1

| Domaine | Détectés | Rappel |
|---|---|---|
| a11y | 5/6 | 83% |
| code | 14/16 | 88% |
| geo | 11/12 | 92% |
| http | 8/9 | 89% |
| perf | 17/17 | 100% |
| securite | 4/5 | 80% |
| seo | 31/36 | 86% |

### Ratés

- **H06** (http) — /_astro/ sans cache long
- **S03** (seo) — 404 dans le sitemap
- **S04** (seo) — noindex dans le sitemap
- **S10** (seo) — Redirection 302
- **S21** (seo) — Page trop profonde
- **S38** (seo) — robots.txt bloque /_astro/
- **G08** (geo) — Article sans auteur
- **C10** (code) — Sitemap depuis request.url
- **C12** (code) — Pas d'allowedDomains
- **X02** (securite) — Source maps publiques
- **A05** (a11y) — Champ sans label

### Faux positifs (jumeau propre)

- **S06** — Page orpheline
- **A06** — Zones tactiles trop petites

### Constats Critique/Haute inattendus sur le jumeau propre

- [code] src/pages/sitemap.xml.ts contient une URL http:// en dur

### Défauts des phases suivantes

- S19 (phase 1) — pas encore
- S35b (phase 1) — pas encore
- X06 (phase 1) — pas encore
- R01 (phase 2) — pas encore
- R02 (phase 2) — pas encore
- E01 (phase 2) — pas encore

## Seuils (cliquet)

| Seuil | Valeur |
|---|---|
| rappel global | 0,89 |
| a11y | 0,83 |
| code | 0,87 |
| geo | 0,91 |
| http | 0,88 |
| perf | 1,00 |
| securite | 0,80 |
| seo | 0,86 |
| faux positifs max | 2 |
| inattendus max | 1 |

Vérifié : `python3 tests/cobaye/score.py --casse <audits>/casse --propre <audits>/propre --phase 0` rend « seuils respectés » (code 0) sur cette mesure ; monter seo à 0,87 ou baisser les faux positifs à 1 le fait échouer.

## Issues à créer (phase 1)

Une ligne par raté ou faux positif (identifiant, domaine, titre, matcher). Les issues ne sont pas encore publiées ; elles le seront après accord (étiquette `phase-1`, préfixe `[cobaye]`).

### Ratés (à détecter)

- **H06** (http) — /_astro/ sans cache long — `{"type": "texte", "fichier": "http/http-checks.md", "regex": "asset hashé Astro"}`
- **S03** (seo) — 404 dans le sitemap — `{"type": "crawl_issue", "cle": "sitemap_non200", "contient": "/page-404-dans-sitemap"}`
- **S04** (seo) — noindex dans le sitemap — `{"type": "crawl_issue", "cle": "sitemap_noindex", "contient": "/cachee"}`
- **S10** (seo) — Redirection 302 — `{"type": "crawl_issue", "cle": "redirect_temp", "contient": "/promo"}`
- **S21** (seo) — Page trop profonde — `{"type": "crawl_issue", "cle": "deep_page", "contient": "/profond/5"}`
- **S38** (seo) — robots.txt bloque /_astro/ — `{"type": "crawl_issue", "cle": "robots_blocks_assets"}`
- **G08** (geo) — Article sans auteur — `{"type": "geo_signal", "regex": "Articles sans auteur"}`
- **C10** (code) — Sitemap depuis request.url — `{"type": "code", "regex": "depuis l'origine de la requête"}`
- **C12** (code) — Pas d'allowedDomains — `{"type": "code", "regex": "sans security\\.allowedDomains"}`
- **X02** (securite) — Source maps publiques — `{"type": "texte", "fichier": "securite/security-probe.md", "regex": "\\.map HTTP 200"}`
- **A05** (a11y) — Champ sans label — `{"type": "lighthouse", "regex": "(libellé|label)"}`

### Faux positifs sur le jumeau propre (à corriger)

- **S06** (seo) — Page orpheline — `{"type": "crawl_issue", "cle": "orphan", "contient": "/orpheline"}`
- **A06** (a11y) — Zones tactiles trop petites — `{"type": "lighthouse", "regex": "(zones cibles|target|tactile)"}`

### Constat inattendu sur le jumeau propre

- **xmlns** (code) — `src/pages/sitemap.xml.ts` contient une URL `http://` en dur (l'espace de noms `xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"` du sitemap, légitime) et sort en Haute. À exclure dans `astro_scan.py`. Plafond actuel : `inattendus_max` = 1.

## Prochaine étape : phase 1

Corriger les 11 ratés et les 2 faux positifs ci-dessus, puis remonter les seuils au fur et à mesure (le cliquet ne descend jamais). Les défauts S19, S35b et X06 (phase 1) et R01, R02, E01 (phase 2) ne comptent pas encore dans le rappel.
