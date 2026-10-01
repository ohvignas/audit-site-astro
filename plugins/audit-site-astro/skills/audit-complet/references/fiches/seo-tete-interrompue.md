---
id: seo-tete-interrompue
titre: "<head> interrompu par un élément invalide : canonical, robots ou description ignorés par Google"
domaine: SEO technique
severite_type: haute
effort: S
declencheurs:
  - "crawl:tete_interrompue"
sources:
  - https://developers.google.com/search/docs/crawling-indexing/valid-page-metadata
  - https://html.spec.whatwg.org/multipage/semantics.html#the-head-element
---

# `<head>` interrompu par un élément invalide

> **En une phrase** : un élément interdit dans `<head>` (image, iframe, div, texte) fait croire à Google que la tête est finie : la canonical, le noindex ou les hreflang placés après sont ignorés, sans aucun message.

## Pourquoi c'est important

Google lit les métadonnées jusqu'au premier élément invalide. Une canonical ignorée laisse Google choisir lui-même l'URL de référence (doublons) ; un `noindex` ignoré laisse indexer une page privée ; des hreflang ignorés cassent le ciblage par langue. La signature du constat indique l'élément fautif et les balises perdues. Le constat est « haute » quand une canonical, un robots ou des hreflang sont perdus, « moyenne » quand seuls title, description, viewport ou Open Graph le sont.

## Comment le constater soi-même

```bash
curl -s https://SITE/PAGE | python3 -c "import sys,re;h=sys.stdin.read().split('</head>')[0];print(re.findall(r'<(?!/)(?!title|meta|link|style|script|noscript|base|template)([a-z0-9-]+)', h)[:5])"
```
Souvent un composant Astro placé dans le `<head>` du layout (bandeau, pixel `<img>`, `<iframe>` de chat, `<div>` d'un script tiers).

## Correction

1. Repérer l'élément signalé dans `src/layouts/*.astro` (ou le composant inclus dans `<head>`).
2. Le déplacer dans `<body>` ; pour un pixel de suivi, le mettre dans `<noscript>` en fin de `<body>` :
```astro
<head>
  <title>{title}</title>
  <link rel="canonical" href={canonical} />
  <meta name="description" content={description} />
</head>
<body>
  <slot />
  <noscript><img src="https://exemple-pixel/p.gif" alt="" width="1" height="1" /></noscript>
</body>
```
3. Placer les balises de référencement **avant** tout script tiers dans le `<head>`, par prudence.

## Critères d'acceptation

- [ ] `tete_interrompue` absent de `data/crawl/issues.json`
- [ ] Inspection d'URL de la Search Console : la canonical déclarée est bien lue
- [ ] Aucune régression : rendu visuel identique, scripts tiers toujours chargés

## Vérification après correction

```bash
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl --liens-externes 0
python3 -c "import json;print(json.load(open('/tmp/verif/crawl/issues.json')).get('tete_interrompue',{}).get('count',0))"   # 0
```

## Pièges et retour arrière

- Le navigateur corrige silencieusement le HTML : l'inspecteur de Chrome montre l'élément dans `<body>`, ce qui masque le problème ; toujours vérifier le HTML brut (`curl`).
- Retour arrière : `git revert` du layout.
