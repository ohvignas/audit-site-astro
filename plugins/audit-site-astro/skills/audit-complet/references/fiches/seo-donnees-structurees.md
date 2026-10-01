---
id: seo-donnees-structurees
titre: Données structurées JSON-LD absentes, invalides ou incomplètes pour Google
domaine: SEO technique
severite_type: moyenne
effort: M
declencheurs:
  - "crawl:no_jsonld"
  - "crawl:jsonld_invalid"
  - "crawl:jsonld_proprietes_requises"
  - "crawl:jsonld_type_sans_effet"
  - "crawl:jsonld_prix_absent_du_texte"
sources:
  - https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data
  - https://developers.google.com/search/docs/appearance/structured-data/article
  - https://developers.google.com/search/docs/appearance/structured-data/breadcrumb
  - https://developers.google.com/search/updates
  - https://developers.google.com/search/docs/appearance/structured-data/search-gallery
  - https://schema.org/docs/gs.html
---

# Données structurées JSON-LD absentes, invalides ou incomplètes pour Google

> **En une phrase** : les pages ne décrivent pas leur contenu dans un format lisible par les machines (JSON-LD), le bloc existant est cassé et ignoré, ou il manque des propriétés que Google exige pour afficher un résultat enrichi.

## Pourquoi c'est important

Les données structurées aident Google (et les moteurs de réponse) à comprendre qui publie la page et de quoi elle parle, et rendent possibles des résultats enrichis (fil d'Ariane, événement, liste de cours, produit, offre d'emploi, entreprise locale selon les cas). Google recommande JSON-LD. Un bloc dont le JSON n'est pas valide (virgule en trop, guillemet mal échappé, date mal formée) est simplement ignoré, sans erreur visible. Autre règle : le balisage doit correspondre à du contenu visible sur la page.

Il faut distinguer deux choses. La **validité schema.org** (validateur schema.org : 0 erreur) dit que le balisage est bien formé ; l'**éligibilité à un résultat enrichi Google** demande en plus les propriétés « requises » de la documentation Google du type concerné (`jsonld_proprietes_requises`, sévérité moyenne : sans elles, pas de résultat enrichi, même avec un balisage valide). Inversement, Google a retiré plusieurs affichages en 2023-2026 (`jsonld_type_sans_effet`, info) : le balisage correspondant reste du schema.org valide et continue d'aider les assistants IA, il n'y a rien d'urgent à faire. Dernier contrôle, volontairement minimal : un prix déclaré en JSON-LD qui n'apparaît pas dans le texte visible de la page (`jsonld_prix_absent_du_texte`, basse, à vérifier : le balisage doit refléter le contenu visible).

`no_jsonld` est une observation de basse priorité si le site est petit ; elle devient utile pour les gabarits qui portent un enjeu (articles, formations, organisation, fil d'Ariane).

## Comment le constater soi-même

```bash
# Extraire et valider les blocs JSON-LD d'une page
curl -s https://SITE/page/ | python3 -c "
import sys, re, json
html = sys.stdin.read()
blocs = re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S)
print(len(blocs), 'bloc(s)')
for b in blocs:
    try:
        d = json.loads(b); print('OK', d.get('@type') if isinstance(d, dict) else [x.get('@type') for x in d])
    except Exception as e:
        print('INVALIDE :', e)
"
grep -rn "ld+json" src/ | head
```

Test officiel : « Test des résultats enrichis » de Google et le validateur schema.org (à donner à l'utilisateur pour les gabarits clés).

## Correction

1. Créer un composant réutilisable qui **sérialise un objet JavaScript** (jamais du JSON écrit à la main : il reste valide par construction). Échapper `<` pour empêcher toute fermeture prématurée de la balise `<script>` :

```astro
---
// src/components/JsonLd.astro
interface Props {
  data: Record<string, unknown> | Record<string, unknown>[];
}
const { data } = Astro.props;
const json = JSON.stringify(data).replace(/</g, '\\u003c');
---
<script is:inline type="application/ld+json" set:html={json} />
```

2. Ajouter dans le layout un bloc `Organization` + `WebSite` (page d'accueil) :

```astro
---
// dans BaseLayout.astro ou index.astro
import JsonLd from '../components/JsonLd.astro';
const site = Astro.site!.href;
const identite = [
  {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: 'Exemple SAS',
    url: site,
    logo: new URL('/logo.png', site).href,
    sameAs: ['https://www.linkedin.com/company/exemple'],
  },
  { '@context': 'https://schema.org', '@type': 'WebSite', name: 'Exemple', url: site },
];
---
<JsonLd data={identite} />
```

3. Ajouter `BreadcrumbList` sur les pages profondes et `Article` (ou `BlogPosting`) sur les articles :

```astro
---
const { post } = Astro.props;
const url = new URL(Astro.url.pathname, Astro.site).href;
const article = {
  '@context': 'https://schema.org',
  '@type': 'Article',
  headline: post.title,
  datePublished: post.date.toISOString(),
  dateModified: (post.updated ?? post.date).toISOString(),
  author: { '@type': 'Person', name: post.author },
  image: [new URL(post.image, Astro.site).href],
  mainEntityOfPage: url,
};
const fil = {
  '@context': 'https://schema.org',
  '@type': 'BreadcrumbList',
  itemListElement: [
    { '@type': 'ListItem', position: 1, name: 'Accueil', item: new URL('/', Astro.site).href },
    { '@type': 'ListItem', position: 2, name: 'Blog', item: new URL('/blog/', Astro.site).href },
    { '@type': 'ListItem', position: 3, name: post.title, item: url },
  ],
};
---
<JsonLd data={[article, fil]} />
```

4. Réparer un bloc invalide : trouver l'écriture manuelle (`<script type="application/ld+json">` avec du JSON en dur, ou un modèle qui injecte du texte avec guillemets) et passer par le composant ci-dessus.
5. Dates au format ISO 8601, URL absolues, champs conformes à la documentation Google du type concerné (les propriétés obligatoires diffèrent selon le résultat enrichi visé).
6. Ne balisez que ce qui est visible (une `FAQPage` seulement si la FAQ est affichée).
7. Propriétés requises par Google (signalées par `jsonld_proprietes_requises`) : Event : `name`, `startDate`, `location` ; Product : `name` et au moins un de `offers`, `review`, `aggregateRating` ; Course (liste de cours, au moins trois cours) : `name`, `description` ; JobPosting : `datePosted`, `description`, `hiringOrganization`, `jobLocation` (ou `applicantLocationRequirements` en télétravail), `title` ; LocalBusiness et sous-types : `name`, `address` ; Recipe : `name`, `image` ; VideoObject : `name`, `thumbnailUrl`, `uploadDate` ; BreadcrumbList : `itemListElement` ; Review : `author`, `reviewRating` ; AggregateRating : `ratingValue` et `ratingCount` ou `reviewCount`. Compléter le gabarit avec des valeurs réelles, jamais inventées.
8. Types retirés (ClaimReview, Course Info, Estimated salary, Learning video, Special announcement, Vehicle listing, Practice problem, How-to, FAQ, boîte de recherche de sitelinks) : les garder seulement s'ils servent schema.org et les assistants IA ; ne plus en attendre d'affichage Google. Ne pas confondre avec ce qui reste actif : liste de cours (Course avec `name` et `description`), Dataset (Dataset Search), Book actions, Event, Product, Organization, BreadcrumbList.

## Critères d'acceptation

- [ ] Chaque bloc JSON-LD est un JSON valide (script de contrôle ci-dessus : aucun « INVALIDE »)
- [ ] Organization + WebSite sur l'accueil ; BreadcrumbList et Article/BlogPosting sur les gabarits concernés
- [ ] Test des résultats enrichis sans erreur sur les gabarits clés, propriétés requises de Google présentes (plus de `jsonld_proprietes_requises`)
- [ ] Aucune régression : build OK, aucune donnée inventée

## Vérification après correction

```bash
curl -s https://SITE/ | grep -c 'application/ld+json'
python3 scripts/crawl_site.py https://SITE/ --out /tmp/verif   # no_jsonld, jsonld_invalid, jsonld_proprietes_requises
```

Puis tester 2 ou 3 URL représentatives avec le Test des résultats enrichis et https://validator.schema.org.

## Pièges et retour arrière

- Le JSON-LD ne remplace pas le contenu visible ; ne pas y mettre d'informations absentes de la page.
- Ne pas marquer un avis ou une note inventés (violation des consignes Google).
- Retour arrière : retirer le composant `JsonLd` des layouts.

## Pour aller plus loin

- https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data : formats et principes.
- https://developers.google.com/search/docs/appearance/structured-data/article : propriétés d'Article.
- https://developers.google.com/search/docs/appearance/structured-data/breadcrumb : BreadcrumbList.
- https://developers.google.com/search/docs/appearance/structured-data/search-gallery : types qui donnent encore un résultat enrichi.
- https://developers.google.com/search/updates : journal des types retirés (2023 à 2026).
- https://schema.org/docs/gs.html : prise en main de schema.org.
