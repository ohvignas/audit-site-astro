---
id: geo-extraits-limites
titre: Des directives (nosnippet, max-snippet, noai…) limitent les extraits et excluent des AI Overviews
domaine: GEO / IA
severite_type: haute
effort: S
declencheurs:
  - "geo:limite les extraits"
sources:
  - https://developers.google.com/search/docs/appearance/snippet
  - https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag
  - https://developers.google.com/search/docs/appearance/ai-features
  - https://docs.astro.build/en/reference/api-reference/
---

# Des directives limitent les extraits

> **En une phrase** : une page porte `nosnippet`, `max-snippet` réduit, `noai`, `noimageai` ou `noarchive` (dans une balise meta ou l'en-tête `X-Robots-Tag`) ; Google n'affiche alors que peu ou pas de son contenu, y compris dans les AI Overviews.

## Pourquoi c'est important

Selon Google, les contrôles d'extraits (`nosnippet`, `max-snippet`, `data-nosnippet`) limitent ce qui est montré depuis vos pages dans Search, ce qui inclut AI Overviews et AI Mode. Une page qui interdit l'extrait se prive de ces emplacements, même si elle est bien classée. Ces directives sont souvent héritées : réglage global d'un plugin, en-tête posé par le serveur pour un usage précis puis oublié, copie d'un guide « anti-IA ». `noai` et `noimageai` ne sont pas des directives standard ni reconnues par Google ; les inclure n'a pas d'effet garanti et donne un faux sentiment de protection. L'outil signale aussi `noarchive` (copie en cache) ; Google ne le présente pas comme un contrôle d'extrait, donc son impact GEO est faible, mais il est rarement utile aujourd'hui.

## Comment le constater soi-même

```bash
# En-tête HTTP
curl -sI https://SITE/PAGE | grep -i 'x-robots-tag'
# Balises meta
curl -s https://SITE/PAGE | grep -oiE '<meta[^>]*name="(robots|googlebot)"[^>]*>'
# Dans le code
grep -rniE "nosnippet|max-snippet|noai|noimageai|noarchive|x-robots-tag" src/ astro.config.* public/ 2>/dev/null
# Configuration serveur
grep -rniE "x-robots-tag" /etc/nginx /etc/caddy Caddyfile 2>/dev/null
```

Présent : `nosnippet`, `max-snippet:0`, `max-snippet:50`, `noai`… Corrigé : aucune de ces directives sur les pages publiques utiles.

## Correction

1. Créer une branche Git ; repérer l'origine (`grep` ci-dessus, en-têtes réels du serveur, réglages du CDN qui ajoutent `X-Robots-Tag`). L'en-tête l'emporte sur un oubli côté HTML : les deux sont à contrôler.
2. Dans le layout Astro, une seule balise robots explicite et ouverte (directives documentées par Google) :

```astro
---
// src/layouts/Base.astro (extrait)
const { noindex = false } = Astro.props;
const robots = noindex
  ? 'noindex, nofollow'
  : 'index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1';
---
<meta name="robots" content={robots} />
```

   `max-snippet:-1` signifie « aucune limite de longueur » ; c'est aussi l'état par défaut, cette balise sert à écarter une limite héritée. Retirer toute mention `nosnippet`, `noai`, `noimageai`, `noarchive`.
3. Supprimer l'en-tête fautif côté serveur. nginx : retirer la ligne `add_header X-Robots-Tag "nosnippet";` du `server`/`location`. Caddy : retirer la directive `header X-Robots-Tag` correspondante. Astro : retirer l'appel `Astro.response.headers.set('X-Robots-Tag', valeur)` du middleware (`src/middleware.ts`).
4. **Cas légitimes à conserver** : `noindex` sur les espaces privés (admin, compte client), pages de remerciement, résultats de recherche interne. Ne pas les rouvrir.
5. `data-nosnippet` sert à exclure un passage précis (bandeau, mention légale) : c'est acceptable sur les éléments accessoires, mais ne jamais le poser sur le texte principal ou les réponses que l'on veut voir citées.

```html
<div data-nosnippet>Bandeau cookies, mention interne</div>
```

   `data-nosnippet` fonctionne sur `span`, `div` et `section` ; le code HTML doit être valide.
6. Faire redéployer par l'humain ; Google peut mettre des jours à des semaines à recrawler (demander une nouvelle indexation depuis Search Console pour les pages clés).

## Critères d'acceptation

- [ ] Aucune page publique utile ne porte `nosnippet`, `max-snippet` inférieur à 160 (sauf `-1`), `noai`, `noimageai`
- [ ] Aucun en-tête `X-Robots-Tag` restrictif hérité du serveur ou du CDN
- [ ] Les pages privées gardent leur `noindex`
- [ ] Aucune régression : build OK, pas de page publique passée en `noindex` par erreur

## Vérification après correction

```bash
curl -sI https://SITE/PAGE | grep -i 'x-robots-tag'
curl -s https://SITE/PAGE | grep -oiE '<meta[^>]*name="(robots|googlebot)"[^>]*>'
python3 scripts/geo_check.py https://SITE/ --out /tmp/verif/geo --sample 12
grep -i 'limite les extraits' /tmp/verif/geo/geo-summary.md
```

Contrôler ensuite dans Search Console (Inspection d'URL) que la page est « indexable ».

## Pièges et retour arrière

- Ne pas confondre avec `noindex` : ce dernier retire la page de Google. Le corriger ici n'est pas l'objectif sauf erreur.
- Des directives peuvent venir d'un module d'intégration SEO : les désactiver dans sa configuration plutôt que dans le HTML généré.
- Retour arrière : Git ; rétablir la ligne d'origine si la restriction était voulue (à valider avec le propriétaire).

## Pour aller plus loin

- https://developers.google.com/search/docs/appearance/snippet : `nosnippet`, `max-snippet`, `data-nosnippet`.
- https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag : liste des directives robots reconnues.
- https://developers.google.com/search/docs/appearance/ai-features : rôle des contrôles d'extraits pour les fonctions IA.
- https://docs.astro.build/en/reference/api-reference/ : `Astro.response.headers`.
