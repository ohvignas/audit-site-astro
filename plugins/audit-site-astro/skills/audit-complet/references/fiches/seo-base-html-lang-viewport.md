---
id: seo-base-html-lang-viewport
titre: Layout sans balises de base (lang, viewport, canonical, description, Open Graph, favicon)
domaine: SEO technique
severite_type: haute
effort: S
declencheurs:
  - "crawl:lang_missing"
  - "crawl:viewport_missing"
  - "code:Layout .* : balises absentes du <head>"
  - "code:Pas de favicon dans public/"
  - "lighthouse:viewport"
sources:
  - https://docs.astro.build/en/basics/layouts/
  - https://developer.mozilla.org/en-US/docs/Web/HTML/Viewport_meta_tag
  - https://developer.mozilla.org/en-US/docs/Web/HTML/Global_attributes/lang
  - https://developers.google.com/search/docs/appearance/favicon-in-search
---

# Layout sans balises de base (lang, viewport, canonical, description, Open Graph, favicon)

> **En une phrase** : le gabarit commun du site oublie une ou plusieurs balises de base du `<head>`, et l'oubli se répète sur toutes les pages.

## Pourquoi c'est important

Ces balises sont dans le layout : un oubli touche donc **toutes** les pages d'un coup, et une correction unique les règle toutes. Sans `<meta name="viewport" content="width=device-width, initial-scale=1">`, les mobiles affichent la page « bureau » réduite (mauvaise expérience, mauvais signal mobile). Sans `lang` sur `<html>`, les lecteurs d'écran prononcent mal le texte et les moteurs devinent la langue. Un favicon manquant prive le site de son icône dans les résultats Google. Les balises canonical, description et Open Graph sont détaillées dans `seo-canonical` et dans le domaine Contenu.

## Comment le constater soi-même

```bash
curl -s https://SITE/ | grep -oE '<html[^>]*>'                       # doit contenir lang="fr"
curl -s https://SITE/ | grep -oE '<meta[^>]+name="viewport"[^>]*>'   # doit exister
curl -s https://SITE/ | grep -oE '<link[^>]+rel="[^"]*icon[^"]*"[^>]*>'
curl -s -o /dev/null -w '%{http_code}\n' https://SITE/favicon.ico
# côté code : quel layout est utilisé, et que contient son <head> ?
grep -rlE "<head" src/layouts src/components | head
```

## Correction

1. Repérer le ou les layouts qui contiennent `<head>` (`src/layouts/*.astro`). S'assurer que **toutes** les pages passent par eux (pas de page avec son propre `<html>`).
2. Compléter le layout avec les balises manquantes. Modèle minimal complet :

```astro
---
// src/layouts/BaseLayout.astro
interface Props {
  title: string;
  description: string;
  image?: string; // chemin ou URL absolue de l'image de partage (1200x630)
  lang?: string;
}
const { title, description, image = '/og-default.jpg', lang = 'fr' } = Astro.props;
const canonicalUrl = new URL(Astro.url.pathname, Astro.site).href;
const imageUrl = new URL(image, Astro.site).href; // og:image doit être absolue
---
<!doctype html>
<html lang={lang}>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <meta name="description" content={description} />
    <link rel="canonical" href={canonicalUrl} />
    <link rel="icon" href="/favicon.ico" sizes="48x48" />
    <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
    <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
    <meta property="og:type" content="website" />
    <meta property="og:title" content={title} />
    <meta property="og:description" content={description} />
    <meta property="og:url" content={canonicalUrl} />
    <meta property="og:image" content={imageUrl} />
    <meta name="twitter:card" content="summary_large_image" />
  </head>
  <body>
    <slot />
  </body>
</html>
```

3. Déposer les fichiers d'icône dans `public/` : un `favicon.ico` ou `.png` carré d'au moins 48x48 px (Google : minimum 8x8, recommandé plus grand que 48x48 ; formats ICO, PNG, GIF, JPEG, BMP...), et si possible `apple-touch-icon.png` (180x180). Un `favicon.svg` est un plus pour les navigateurs, mais garder une version ICO/PNG pour Google. Une seule icône par nom d'hôte, à une URL stable et accessible à Googlebot.
4. Site multilingue : passer `lang` selon la page (`Astro.currentLocale` si l'i18n d'Astro est configurée) plutôt que de figer `fr`.
5. Ne pas ajouter `maximum-scale=1` ni `user-scalable=no` : cela empêche le zoom (accessibilité).

## Critères d'acceptation

- [ ] `<html lang="...">` présent sur 100 % des pages (valeur correcte : `fr`, `en`…)
- [ ] `<meta name="viewport" content="width=device-width, initial-scale=1">` présent partout
- [ ] Un favicon déclaré et accessible en 200 ; `og:image` en URL absolue
- [ ] Aucune régression visuelle sur mobile ; build OK

## Vérification après correction

```bash
for p in / /contact/; do
  curl -s "https://SITE$p" | grep -cE '<html[^>]+lang=|name="viewport"|rel="canonical"|rel="icon"'
done   # attendu : 4 lignes détectées ou plus par page
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif   # lang_missing, viewport_missing = 0
```

Relancer Lighthouse (`lighthouse_run.sh`) : plus d'échec « viewport ».

## Pièges et retour arrière

- Un composant SEO importé peut déjà fournir certaines balises : ne pas les dupliquer (doublons de `canonical` ou de `title`).
- Avec Astro 7 (compilateur Rust), un HTML invalide est refusé : garder `<head>` dans le layout et une seule balise `<html>`.
- Retour arrière : `git revert` du layout.

## Pour aller plus loin

- https://docs.astro.build/en/basics/layouts/ : layouts et `<slot />`.
- https://developer.mozilla.org/en-US/docs/Web/HTML/Viewport_meta_tag : valeurs du viewport.
- https://developer.mozilla.org/en-US/docs/Web/HTML/Global_attributes/lang : attribut `lang`.
- https://developers.google.com/search/docs/appearance/favicon-in-search : exigences du favicon dans les résultats.
