---
id: serveur-regex
titre: Déclencheurs à regex, antislashs et apostrophes
domaine: Serveur / HTTP
severite_type: moyenne
effort: M
declencheurs:
  - "crawl:http_4xx"
  - "http:Compression HTML \\| aucune"
  - "securite:/\\.env \\| 200"
  - "geo:robots\\.txt bloque (OAI-SearchBot|PerplexityBot)"
  - 'code:Routes SSR dynamiques sans gestion'
  - "lighthouse:uses-text-compression|compression"
  - "projet:dépendances obsolètes"
sources: []
---

# Regex
