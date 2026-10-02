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

Google lit les métadonnées jusqu'au premier élément invalide. Une canonical ignorée laisse Google choisir lui-même l'URL de référence (doublons) ; un `noindex` ignoré laisse indexer une page privée ; des hreflang ignorés cassent le ciblage par langue. La signature du constat indique l'élément fautif et les balises perdues. Le constat est « haute » quand une canonical, un robots ou des hreflang sont perdus, « moyenne » quand seuls title, description, viewport, Open Graph, twitter:*, theme-color, manifest, alternate ou un préchargement d'image (LCP) le sont.

**Cas « (sans JavaScript) »** : un `<noscript>` au contenu invalide placé dans `<head>` avant ces balises (iframe de Google Tag Manager, pixel Meta en `<img>`, `<div>`) ferme la tête pour les robots qui n'exécutent pas JavaScript et pour la première lecture du HTML brut (aperçus de liens, outils SEO, `curl`). Google, qui rend la page avec JavaScript, n'est pas concerné d'après sa documentation : ce cas est donc plafonné à « moyenne ». Un `<noscript>` de la tête ne ferme la tête que s'il contient un élément invalide dans la tête aussi (`iframe`, `img`, `div`, texte) : `<noscript><link …></noscript>`, `<noscript><style>` ou `<noscript><script>` restent valides.

## Comment le constater soi-même

```bash
curl -s https://SITE/PAGE | python3 -c '
import sys, re
h = sys.stdin.read().split("</head>")[0]
h = re.sub(r"<(script|style|noscript|template)\b.*?</\1>", "", h, flags=re.S | re.I)
print(re.findall(r"<(?!/)(?!html|head|title|meta|link|base|basefont|bgsound|noframes)([a-z][a-z0-9-]*)", h, re.I)[:1])'
```
Affiche le premier élément invalide de la tête (liste vide : tête valide). Pour le cas « sans JavaScript », lister les `<noscript>` de la tête :
```bash
curl -s https://SITE/PAGE | python3 -c '
import sys, re
h = sys.stdin.read().split("</head>")[0]
print(re.findall(r"<noscript\b.*?</noscript>", h, re.S | re.I))'
```
Tout `<noscript>` contenant une `iframe`, une `img`, un `div` ou du texte est à déplacer.

Souvent un composant Astro placé dans le `<head>` du layout (bandeau, pixel `<img>`, `<iframe>` de chat, `<div>` d'un script tiers).

## Correction

1. Repérer l'élément signalé dans `src/layouts/*.astro` (ou le composant inclus dans `<head>`).
2. Le déplacer dans `<body>`. Pour Google Tag Manager, c'est sa propre consigne : le `<noscript><iframe …></iframe></noscript>` va juste après l'ouverture de `<body>`, jamais dans `<head>` ; même règle pour un pixel de suivi en `<noscript><img>` :
```astro
<head>
  <title>{title}</title>
  <link rel="canonical" href={canonical} />
  <meta name="description" content={description} />
</head>
<body>
  <noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-XXXX" height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
  <slot />
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

- Avec JavaScript actif, un `<noscript>` invalide dans la tête « passe » (son contenu est lu comme du texte) ; sans JavaScript, la tête se ferme à cet endroit. Google rend avec JavaScript : c'est pourquoi ce cas reste « moyenne », mais les autres robots et les aperçus de liens perdent canonical, description et Open Graph.
- Le navigateur corrige silencieusement le HTML : l'inspecteur de Chrome montre l'élément dans `<body>`, ce qui masque le problème ; toujours vérifier le HTML brut (`curl`).
- Retour arrière : `git revert` du layout.
