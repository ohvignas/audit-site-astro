---
id: domaine-sujet-court            # identifiant unique, kebab-case, préfixé par le domaine (perf-, serveur-, seo-, contenu-, geo-, code-, convex-, secu-, a11y-)
titre: Titre court et factuel du problème
domaine: Performance               # Performance | Serveur / HTTP | SEO technique | Contenu | GEO / IA | Code | Sécurité | Accessibilité
severite_type: haute               # critique | haute | moyenne | basse — sévérité habituelle (le rapport priorisé peut l'ajuster)
effort: S                          # S (< 1 h) | M (< 1 jour) | L (> 1 jour)
declencheurs:                      # comment l'outil reconnaît ce problème dans ses données (au moins un)
  - "crawl:http_4xx"               # clé exacte d'issue de crawl_site.py
  - "code:Routes SSR dynamiques sans gestion"   # regex sur le texte d'un constat astro_scan.py
  - "geo:robots\\.txt bloque (OAI-SearchBot|PerplexityBot)"  # regex sur un signal geo_check.py
  - "http:Compression HTML \\| aucune"          # regex sur une ligne de data/http/http-checks.md
  - "securite:/\\.env \\| 200"                  # regex sur une ligne de data/securite/security-probe.md
  - "lighthouse:uses-text-compression|compression"  # regex sur l'id ou le titre (FR) d'un audit Lighthouse
versions_astro: ">=5.10"           # facultatif : version d'Astro requise par la correction proposée
sources:                           # documentation officielle vérifiée
  - https://docs.astro.build/en/...
---

# Titre court et factuel du problème

> **En une phrase** : ce qui ne va pas et ce que ça coûte.

## Pourquoi c'est important

2 à 5 phrases concrètes : impact sur le référencement Google, la visibilité dans les IA, la vitesse, la conversion ou la sécurité. Chiffrer quand c'est possible (seuils Google, ordres de grandeur).

## Comment le constater soi-même

Commandes ou vérifications reproductibles (curl, grep dans le code, outil en ligne), avec le résultat attendu quand le problème est présent et quand il est corrigé.

```bash
curl -sI -H 'Accept-Encoding: br, gzip' https://SITE/ | grep -i content-encoding
```

## Correction

Étapes numérotées, dans l'ordre, pour un site **Astro** (et ses variantes quand elles diffèrent : SSR Node derrière nginx / Caddy / Traefik, statique, Vercel / Netlify / Cloudflare ; backend **Convex** quand c'est pertinent). Chaque étape dit **quel fichier** modifier et donne le **code exact**. Si la correction dépend de la version d'Astro, le dire et donner l'alternative pour les versions antérieures.

1. …
2. …

```astro
---
// exemple de code complet et correct
---
```

## Critères d'acceptation

- [ ] Condition vérifiable 1 (ex. `content-encoding: br` ou `gzip` sur le HTML, le CSS et le JS)
- [ ] Condition vérifiable 2
- [ ] Aucune régression : build OK, pages clés en 200, rendu identique

## Vérification après correction

Commandes à relancer (souvent les mêmes que « Comment le constater ») et le script de l'outil à relancer pour confirmer (ex. `bash scripts/http_checks.sh https://SITE/ /tmp/verif`).

## Pièges et retour arrière

- Ce qui peut casser, comment l'éviter.
- Comment annuler la modification.

## Pour aller plus loin

- Liens de documentation (les mêmes que `sources`, avec une phrase chacun).
