---
id: contenu-open-graph
titre: Open Graph incomplet (aperçu de partage réseaux sociaux)
domaine: Contenu
severite_type: basse
effort: S
declencheurs:
  - "crawl:og_missing"
  - "code:Layout .* : balises absentes du <head> : .*\\bog\\b"
sources:
  - https://ogp.me/
  - https://developer.x.com/en/docs/x-for-websites/cards/overview/summary-card-with-large-image
  - https://docs.astro.build/en/reference/api-reference/#astrosite
---

# Open Graph incomplet (aperçu de partage réseaux sociaux)

> **En une phrase** : quand on partage une page sur LinkedIn, Facebook, WhatsApp ou Slack, l'aperçu n'a ni image ni titre soigné, donc le lien attire moins de clics.

## Pourquoi c'est important

Les balises Open Graph (`og:title`, `og:image`…) pilotent la carte d'aperçu affichée quand un lien est partagé. Sans elles, les réseaux devinent (titre brut, pas d'image ou une image au hasard). Ce n'est pas un critère de classement Google, mais le partage LinkedIn ou WhatsApp est un canal réel pour une formation ou un service. Le protocole Open Graph définit quatre propriétés obligatoires : `og:title`, `og:type`, `og:image`, `og:url` ; `og:description`, `og:site_name`, `og:locale` et `og:image:alt` sont facultatives mais recommandées. L'outil signale une page si `og:title` ou `og:image` manque.

## Comment le constater soi-même

```bash
curl -s https://SITE/formations/excel/ | grep -oiE '<meta (property|name)="(og|twitter):[^"]*" content="[^"]*"' 
grep -rn "og:" src/layouts src/components | head
```

Présent : pas de ligne `og:title` ou `og:image`. Test visuel : coller l'URL dans le débogueur de partage de Facebook ou LinkedIn (Post Inspector), ou dans un message WhatsApp à soi-même.

## Correction

1. **Centraliser dans le layout.** Les balises OG se déduisent des mêmes props que `<title>` et la description : les écrire une seule fois dans `src/layouts/BaseLayout.astro` (ou dans un composant `Seo.astro` appelé par le layout), pas page par page.
2. **Image par défaut** : créer `public/og/defaut.jpg` (1200 x 630 px, JPEG ou PNG, moins de 300 Ko, texte lisible même réduit, marque visible, sans information vitale sur les bords). L'URL doit être **absolue** (https) : construire avec `Astro.site` (le `site` doit être défini dans `astro.config.mjs`).

```astro
---
// src/layouts/BaseLayout.astro
interface Props {
  title: string;
  description: string;
  image?: string;          // chemin depuis la racine, ex. "/og/formation-excel.jpg"
  imageAlt?: string;
  type?: "website" | "article";
}
const { title, description, image = "/og/defaut.jpg", imageAlt = "Exemple, organisme de formation", type = "website" } = Astro.props;
const canonical = new URL(Astro.url.pathname, Astro.site);
const imageUrl = new URL(image, Astro.site);
---
<head>
  <title>{title}</title>
  <meta name="description" content={description} />
  <link rel="canonical" href={canonical.href} />
  <meta property="og:title" content={title} />
  <meta property="og:description" content={description} />
  <meta property="og:type" content={type} />
  <meta property="og:url" content={canonical.href} />
  <meta property="og:image" content={imageUrl.href} />
  <meta property="og:image:alt" content={imageAlt} />
  <meta property="og:site_name" content="Exemple" />
  <meta property="og:locale" content="fr_FR" />
  <meta name="twitter:card" content="summary_large_image" />
</head>
```

   L'URL de la canonical est construite avec `Astro.url.pathname` et `Astro.site`, pas avec `Astro.url.href` (qui peut sortir en http derrière un proxy et garde les paramètres).
3. **Image propre à chaque contenu** (facultatif mais utile) : dans la collection, ajouter `ogImage: z.string().optional()` ou réutiliser l'image de couverture. Convex : champ `ogImage: v.optional(v.string())` (URL absolue ou chemin du dossier `public/`). Ne pas pointer vers une URL de stockage privée ou expirante.
4. **Titre et description OG** : reprendre ceux de la page, ou un titre plus accrocheur si nécessaire. Garder le titre sous 60 caractères et la description sous 155.
5. **Twitter/X** : `twitter:card` à `summary_large_image` suffit, X retombe sur les balises `og:*` pour le reste.
6. Si un composant SEO tiers est déjà utilisé (paquet d'intégration), ne pas dupliquer les balises : vérifier `curl` pour éviter deux `og:title`.

## Critères d'acceptation

- [ ] Chaque page indexable a `og:title`, `og:description`, `og:type`, `og:url`, `og:image` (URL absolue https) et `og:image:alt`.
- [ ] L'image existe (statut 200), mesure 1200 x 630 px, et pèse moins de 300 Ko.
- [ ] Une seule occurrence de chaque balise OG.
- [ ] Le débogueur de partage affiche titre, description et image.

## Vérification après correction

```bash
curl -s https://SITE/ | grep -oE '<meta property="og:(title|image|url)" content="[^"]*"'
curl -sI "$(curl -s https://SITE/ | grep -oE 'og:image" content="[^"]*"' | sed 's/.*content="//;s/"$//')" | head -1     # HTTP/2 200
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif/crawl
python3 -c "import json;d=json.load(open('/tmp/verif/crawl/issues.json'));print(d.get('og_missing',{}).get('count',0))"
```

## Pièges et retour arrière

- Les réseaux gardent l'aperçu en cache : après correction, forcer un nouveau scrape (débogueur Facebook, Post Inspector LinkedIn).
- Une `og:image` relative (`/og/defaut.jpg`) est ignorée par certains réseaux : toujours absolue.
- Les formats WebP et SVG ne sont pas acceptés partout pour `og:image` : préférer JPEG ou PNG.
- Retour arrière : `git revert` ; balises de `<head>` uniquement.

## Pour aller plus loin

- https://ogp.me/ : propriétés obligatoires et facultatives.
- https://developer.x.com/en/docs/x-for-websites/cards/overview/summary-card-with-large-image : carte à grande image.
- https://docs.astro.build/en/reference/api-reference/#astrosite : `Astro.site` pour construire des URL absolues.
