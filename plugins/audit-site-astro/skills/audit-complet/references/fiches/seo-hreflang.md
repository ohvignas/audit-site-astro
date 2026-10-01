---
id: seo-hreflang
titre: hreflang incomplet (sans auto-référence, non réciproque, invalide)
domaine: SEO technique
severite_type: moyenne
effort: M
declencheurs:
  - "crawl:hreflang_no_self"
  - "lighthouse:hreflang"
sources:
  - https://developers.google.com/search/docs/specialty/international/localized-versions
  - https://docs.astro.build/en/guides/internationalization/
  - https://docs.astro.build/en/guides/integrations-guide/sitemap/
---

# hreflang incomplet (sans auto-référence, non réciproque, invalide)

> **En une phrase** : sur un site multilingue, les balises `hreflang` qui relient les versions d'une page ne se citent pas toutes entre elles, donc Google peut les ignorer et servir la mauvaise langue.

## Pourquoi c'est important

`hreflang` indique à Google quelle version d'une page correspond à quelle langue ou région. Google est clair : chaque version doit se lister **elle-même** et lister toutes les autres, et les liens doivent être **réciproques** (si A cite B, B cite A), sinon les annotations peuvent être ignorées. Les adresses doivent être complètes (`https://exemple.fr/en/...`), les codes valides (langue ISO 639-1, région ISO 3166-1 alpha 2, par exemple `fr`, `fr-CA`, `en-GB`) : `GB` seul n'existe pas. `x-default` indique la version de repli. Astro ne génère **pas** les balises hreflang automatiquement.

Ce constat ne concerne que les sites qui ont déjà des balises hreflang ou plusieurs langues. Un site monolingue n'en a pas besoin.

## Comment le constater soi-même

```bash
curl -s https://SITE/ | grep -oE '<link[^>]+hreflang[^>]*>'
curl -s https://SITE/en/ | grep -oE '<link[^>]+hreflang[^>]*>'
grep -rn "hreflang" src/ | head
grep -n "i18n" astro.config.*
```

Présent : l'URL de la page courante ne figure pas parmi ses propres balises, ou la page anglaise ne cite pas la française. Corrigé : chaque page liste toutes ses versions, y compris elle-même, plus `x-default`.

## Correction

1. Si le site n'a qu'une langue : supprimer les balises hreflang partielles (elles ne servent à rien et peuvent être erronées).
2. Sinon, configurer l'i18n d'Astro (`locales`, `defaultLocale`, routage) :

```js
// astro.config.mjs
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://exemple.fr',
  i18n: {
    defaultLocale: 'fr',
    locales: ['fr', 'en'],
    routing: { prefixDefaultLocale: false },
  },
  integrations: [
    sitemap({
      // Génère aussi les liens xhtml:link hreflang dans le sitemap
      i18n: { defaultLocale: 'fr', locales: { fr: 'fr-FR', en: 'en-GB' } },
    }),
  ],
});
```

3. Générer les balises dans le layout, à partir de la liste des versions de la page. `getAbsoluteLocaleUrl` (module `astro:i18n`) construit les URL complètes :

```astro
---
// src/layouts/BaseLayout.astro (extrait)
import { getAbsoluteLocaleUrl } from 'astro:i18n';

// `path` = chemin de la page sans préfixe de langue, fourni par la page (ex. "contact/")
const { path = '' } = Astro.props;
const versions = [
  { hreflang: 'fr-FR', locale: 'fr' },
  { hreflang: 'en-GB', locale: 'en' },
];
---
<head>
  {versions.map((v) => (
    <link rel="alternate" hreflang={v.hreflang} href={getAbsoluteLocaleUrl(v.locale, path)} />
  ))}
  <link rel="alternate" hreflang="x-default" href={getAbsoluteLocaleUrl('fr', path)} />
</head>
```

La liste inclut la langue de la page courante : c'est l'auto-référence exigée. Les traductions qui n'existent pas pour une page ne doivent **pas** être listées (sinon le lien mène à une 404).

4. Vérifier que la canonical de chaque version pointe vers elle-même (jamais vers la version d'une autre langue).
5. Le code de langue de `<html lang="...">` doit correspondre à la version de la page (fiche `seo-base-html-lang-viewport`).

## Critères d'acceptation

- [ ] Chaque version d'une page contient une balise hreflang pour elle-même et pour toutes ses traductions existantes
- [ ] Les annotations sont réciproques et toutes les URL sont absolues, en 200
- [ ] `x-default` présent ; codes de langue et région valides
- [ ] Lighthouse : audit `hreflang` réussi
- [ ] Aucune régression : build OK, canonicals auto-référentes

## Vérification après correction

```bash
for p in / /en/; do echo "== $p"; curl -s https://SITE$p | grep -oE '<link[^>]+hreflang[^>]*>'; done
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif   # hreflang_no_self doit disparaître
```

Contrôle des retours réciproques et des codes : rapport « Ciblage international » de la Search Console.

## Pièges et retour arrière

- Un `hreflang` pointant vers une URL redirigée, en `noindex` ou en 404 est ignoré.
- Ne pas mélanger les trois méthodes (HTML, en-tête HTTP, sitemap) avec des valeurs différentes.
- Retour arrière : retirer le bloc de balises du layout.

## Pour aller plus loin

- https://developers.google.com/search/docs/specialty/international/localized-versions : règles hreflang, codes, `x-default`, trois méthodes.
- https://docs.astro.build/en/guides/internationalization/ : configuration i18n et `getAbsoluteLocaleUrl`.
- https://docs.astro.build/en/guides/integrations-guide/sitemap/ : option `i18n` du sitemap.
