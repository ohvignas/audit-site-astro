---
id: seo-exact
titre: "Titre avec \"guillemets\" et deux-points : ok"   # commentaire après une valeur citée
domaine: SEO technique
severite_type: haute      # commentaire après une valeur non citée
effort: S
declencheurs:             # commentaire après une clé sans valeur
  # ligne de commentaire dans la liste
  - "crawl:http_4xx"
  - "crawl:http_5xx"
versions_astro: ">=5.10"
sources:
  - https://docs.astro.build/en/guides/routing/
  - https://developers.google.com/search/docs
---

# Titre du corps

> **En une phrase** : exact.

## Pourquoi c'est important

Texte.
