---
id: geo-jsonld-invalide-champs-manquants
titre: JSON-LD invalide ou champs schema.org manquants
domaine: GEO / IA
severite_type: moyenne
effort: S
declencheurs:
  - "geo:JSON-LD invalide"
  - "geo:champs schema manquants"
sources:
  - https://validator.schema.org/
  - https://search.google.com/test/rich-results
  - https://developers.google.com/search/docs/appearance/structured-data/sd-policies
  - https://developers.google.com/search/docs/appearance/structured-data/article
  - https://developers.google.com/search/docs/appearance/structured-data/organization
  - https://docs.astro.build/en/reference/directives-reference/
---

# JSON-LD invalide ou champs schema.org manquants

> **En une phrase** : un bloc de données structurées est illisible (JSON cassé) ou incomplet (champs attendus absents) ; les moteurs l'ignorent ou n'exploitent qu'une partie de l'information sur l'entité, l'article ou le service.

## Pourquoi c'est important

Un JSON-LD syntaxiquement invalide est **ignoré en entier** par les moteurs : c'est comme s'il n'existait pas, et l'entité, l'auteur ou les dates qu'il portait disparaissent. Des champs manquants (`sameAs`, `dateModified`, `author`, `provider`…) n'invalident pas le bloc mais appauvrissent le signal. L'outil compare chaque type à une liste **plus stricte que le minimum de Google** : « champs manquants » est une piste d'amélioration (gravité basse), pas une erreur bloquante ; « JSON-LD invalide » est, lui, à corriger sans attendre. Le balisage doit toujours refléter ce que la page affiche (règles de Google sur les données structurées).

## Comment le constater soi-même

```bash
# Valide-t-il ? (affiche l'erreur JSON exacte)
curl -s https://SITE/PAGE | python3 -c "
import sys,re,json
for i,b in enumerate(re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',sys.stdin.read(),re.S),1):
    try:
        d=json.loads(b); print(i,'OK', (d.get('@type') if isinstance(d,dict) else [x.get('@type') for x in d]))
    except Exception as e: print(i,'INVALIDE :',e)
"
grep -rn "ld+json" src/ | head
```

Puis contrôle officiel : coller l'URL dans https://validator.schema.org/ et dans https://search.google.com/test/rich-results. Les champs manquants sont listés par l'outil dans `geo.json` (clé `champs_manquants`) et dans les signaux `geo-summary.md`.

## Correction

1. Créer une branche Git. Causes fréquentes de JSON invalide : JSON écrit **à la main** dans un gabarit avec des variables (guillemets ou retours à la ligne non échappés dans un titre ou une description), virgule finale, guillemets typographiques, `undefined` sérialisé. Solution : **ne jamais construire le JSON par concaténation**, toujours par `JSON.stringify` d'un objet.
2. Utiliser le composant `JsonLd.astro` (voir `geo-entite-organization-jsonld`) qui sérialise et échappe `<` :

```astro
---
// src/pages/blog/[...slug].astro (extrait)
import JsonLd from '../../components/JsonLd.astro';
const { titre, description, datePub, dateMaj, auteur, image } = Astro.props;
const site = Astro.site ?? new URL('https://exemple.fr');
const article = {
  '@context': 'https://schema.org',
  '@type': 'BlogPosting',
  headline: titre,
  description,
  image: [new URL(image, site).href],
  datePublished: datePub.toISOString(),
  dateModified: (dateMaj ?? datePub).toISOString(),
  author: {
    '@type': 'Person',
    name: auteur.nom,
    jobTitle: auteur.poste,
    url: new URL(auteur.url, site).href,
    sameAs: auteur.sameAs,
  },
  publisher: { '@id': new URL('/#organization', site).href },
  mainEntityOfPage: new URL(Astro.url.pathname, site).href,
};
---
<JsonLd data={article} />
```

3. Compléter les champs manquants selon le type (liste utilisée par l'outil) :

| Type | Champs vérifiés par l'outil |
|---|---|
| Organization | name, url, logo, sameAs |
| LocalBusiness et sous-types (dont EducationalOrganization) | name, address, telephone, url, openingHoursSpecification, geo |
| Person | name, sameAs, jobTitle |
| WebSite | name, url |
| Article / BlogPosting / NewsArticle | headline, author, datePublished, dateModified, image, publisher |
| Product | name, offers, image, description |
| Course | name, description, provider |
| Service | name, provider, areaServed, description |
| FAQPage | mainEntity |
| Event | name, startDate, location |

   Ne renseigner **que des valeurs vraies et visibles** sur la page : ne pas inventer un téléphone, des horaires ou des avis pour faire disparaître un signal. Si un champ n'a pas de sens pour l'entreprise (pas d'horaires), le signal peut être laissé.
4. Exemples de champs locaux corrects :

```ts
const local = {
  '@context': 'https://schema.org',
  '@type': 'LocalBusiness',
  name: 'Exemple SAS',
  url: 'https://exemple.fr/',
  telephone: '+33 4 00 00 00 00',
  address: { '@type': 'PostalAddress', streetAddress: '1 rue Exemple', postalCode: '69000', addressLocality: 'Lyon', addressCountry: 'FR' },
  geo: { '@type': 'GeoCoordinates', latitude: 45.764, longitude: 4.8357 },
  openingHoursSpecification: [{ '@type': 'OpeningHoursSpecification', dayOfWeek: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'], opens: '09:00', closes: '18:00' }],
};
```

5. **FAQPage** : à n'utiliser que si la FAQ est visible sur la page. Google a restreint ces résultats enrichis en 2023 aux sites gouvernementaux et de santé faisant autorité et, d'après sa documentation actuelle, ne les affiche plus : le balisage reste utile pour la compréhension du contenu, pas pour un gain d'affichage. Ne pas le promettre comme un levier de visibilité.

6. Attention aux objets **imbriqués** : l'outil contrôle aussi un `Person` ou une `Organization` placés dans `author` ou `publisher` s'ils ont un `@type` (d'où `jobTitle` et `sameAs` dans l'exemple d'article ci-dessus). Une simple référence `{ '@id': '…' }` sans `@type` n'est pas contrôlée.

## Critères d'acceptation

- [ ] Chaque bloc JSON-LD du site passe `JSON.parse` sans erreur
- [ ] https://validator.schema.org/ n'affiche aucune erreur sur les gabarits clés (accueil, article, service)
- [ ] Les champs renseignés existent réellement dans le contenu visible
- [ ] Aucune régression : build OK, JSON-LD toujours présent dans le HTML servi (pas injecté en JS)

## Vérification après correction

```bash
python3 scripts/geo_check.py https://SITE/ --out /tmp/verif/geo --sample 12
grep -iE 'json-ld|champs schema' /tmp/verif/geo/geo-summary.md
```

Attendu : plus de « JSON-LD invalide » ; « champs schema manquants » réduit ou justifié.

## Pièges et retour arrière

- `set:html` avec `JSON.stringify` de données **maîtrisées** est sûr ; ne jamais y injecter du texte utilisateur brut sans l'échapper (le remplacement de `<` est fait dans le composant).
- Deux blocs qui déclarent le même `@id` avec des valeurs différentes : n'en garder qu'un.
- Retour arrière : Git ; retirer le composant du gabarit concerné.

## Pour aller plus loin

- https://validator.schema.org/ : validation syntaxique schema.org.
- https://search.google.com/test/rich-results : test Google.
- https://developers.google.com/search/docs/appearance/structured-data/sd-policies : règles (le balisage doit refléter le contenu visible).
- https://developers.google.com/search/docs/appearance/structured-data/article : propriétés d'un article.
- https://developers.google.com/search/docs/appearance/structured-data/organization : propriétés d'une organisation.
