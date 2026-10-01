---
id: geo-entite-organization-jsonld
titre: Aucune entité Organization / Person / LocalBusiness en JSON-LD
domaine: GEO / IA
severite_type: haute
effort: S
declencheurs:
  - "geo:Aucune entité Organization"
sources:
  - https://developers.google.com/search/docs/appearance/structured-data/organization
  - https://developers.google.com/search/docs/appearance/structured-data/local-business
  - https://schema.org/Organization
  - https://validator.schema.org/
  - https://docs.astro.build/en/reference/directives-reference/
---

# Aucune entité Organization / Person / LocalBusiness en JSON-LD

> **En une phrase** : aucune page analysée ne déclare qui publie le site (organisation, personne ou entreprise locale) dans des données structurées ; les moteurs et assistants IA identifient mal l'éditeur et l'associent mal à ses profils et avis.

## Pourquoi c'est important

Les assistants IA et les moteurs regroupent l'information par **entité** (une marque, une entreprise, une personne). Un bloc JSON-LD `Organization` sur l'accueil donne le nom exact, l'URL, le logo, les profils officiels (`sameAs`) et les coordonnées, et lui attache un identifiant stable (`@id`) réutilisable sur tout le site. Google le documente pour ses résultats (nom, logo, panneaux de connaissance) ; pour les IA, cela réduit le risque de confusion avec un homonyme et facilite le recoupement avec d'autres sources. L'effet direct sur les citations n'est pas chiffré, mais c'est un socle peu coûteux et sans inconvénient.

## Comment le constater soi-même

```bash
curl -s https://SITE/ | python3 -c "
import sys,re,json
h=sys.stdin.read()
blocs=re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',h,re.S)
print(len(blocs),'bloc(s) JSON-LD')
for b in blocs:
    try:
        d=json.loads(b); print(json.dumps(d,ensure_ascii=False)[:300])
    except Exception as e: print('JSON invalide :',e)
"
grep -rn "application/ld+json" src/ | head
```

Problème présent : `0 bloc(s)`, ou des blocs sans `@type` Organization / LocalBusiness / Person. Corrigé : un bloc `Organization` (ou sous-type) avec `@id`, `name`, `url`, `logo`, `sameAs`.

## Correction

1. Créer une branche Git. Centraliser l'identité de la marque dans **un seul fichier** (réutilisé par le JSON-LD, `og:site_name`, le footer, le suffixe des titres) :

```ts
// src/lib/entite.ts
export const ENTITE = {
  nom: 'Exemple SAS',
  description: "Agence web à Lyon : conception, développement et formation.",
  logo: '/logo.png', // image carrée ou rectangulaire, au moins 112x112 px, accessible publiquement
  sameAs: [
    'https://www.linkedin.com/company/exemple',
    'https://www.youtube.com/@exemple',
  ],
  telephone: '+33 4 00 00 00 00',
  email: 'contact@exemple.fr',
  adresse: { rue: '1 rue Exemple', codePostal: '69000', ville: 'Lyon', pays: 'FR' },
};
```

2. Composant réutilisable, qui échappe `<` pour éviter toute rupture de la balise `<script>` :

```astro
---
// src/components/JsonLd.astro
interface Props { data: Record<string, unknown> | Record<string, unknown>[] }
const { data } = Astro.props;
const json = JSON.stringify(data).replace(/</g, '\\u003c');
---
<script is:inline type="application/ld+json" set:html={json} />
```

3. Ajouter l'entité dans le layout, **complète sur l'accueil**, référencée par `@id` ailleurs. Adapter `@type` : `Organization` par défaut ; `LocalBusiness` (ou un sous-type précis : `ProfessionalService`, `Restaurant`, `EducationalOrganization`…) si l'entreprise reçoit du public à une adresse ; `Person` pour un indépendant qui se présente en son nom.

```astro
---
// src/layouts/Base.astro (extrait)
import JsonLd from '../components/JsonLd.astro';
import { ENTITE } from '../lib/entite';
const site = Astro.site ?? new URL('https://exemple.fr');
const orgId = new URL('/#organization', site).href;
const estAccueil = Astro.url.pathname === '/';
const organisation = {
  '@context': 'https://schema.org',
  '@type': 'Organization',
  '@id': orgId,
  name: ENTITE.nom,
  url: site.href,
  logo: new URL(ENTITE.logo, site).href,
  description: ENTITE.description,
  sameAs: ENTITE.sameAs,
  email: ENTITE.email,
  telephone: ENTITE.telephone,
  address: {
    '@type': 'PostalAddress',
    streetAddress: ENTITE.adresse.rue,
    postalCode: ENTITE.adresse.codePostal,
    addressLocality: ENTITE.adresse.ville,
    addressCountry: ENTITE.adresse.pays,
  },
};
const siteWeb = {
  '@context': 'https://schema.org',
  '@type': 'WebSite',
  '@id': new URL('/#website', site).href,
  name: ENTITE.nom,
  url: site.href,
  publisher: { '@id': orgId },
};
---
<head>
  {estAccueil && <JsonLd data={[organisation, siteWeb]} />}
</head>
```

   Sur les autres gabarits (articles, formations), référencer l'organisation par `publisher: { '@id': orgId }` sans la répéter. Pour `LocalBusiness`, ajouter `openingHoursSpecification` et `geo` ; l'outil signale leur absence en « champs manquants » (voir `geo-jsonld-invalide-champs-manquants`). Ne renseigner que des informations **réelles et visibles** sur le site.
4. Si `site` n'est pas défini dans `astro.config.mjs`, le définir (`site: 'https://exemple.fr'`) ; sinon `Astro.site` est indéfini.
5. Valider l'accueil sur https://validator.schema.org/ et avec le test des résultats enrichis de Google.

## Critères d'acceptation

- [ ] L'accueil contient un bloc JSON-LD valide de type Organization (ou LocalBusiness / Person) avec `@id`, `name`, `url`, `logo`
- [ ] Le même `@id` est réutilisé (pas d'entités concurrentes)
- [ ] Le nom correspond exactement à celui du footer, du titre et de `og:site_name`
- [ ] Aucune régression : build OK, rendu HTML identique hors `<head>`

## Vérification après correction

```bash
curl -s https://SITE/ | grep -c 'application/ld+json'
python3 scripts/geo_check.py https://SITE/ --out /tmp/verif/geo --sample 6
grep -i 'entité' /tmp/verif/geo/geo-summary.md
```

Attendu : plus de signal « Aucune entité Organization ».

## Pièges et retour arrière

- Ne pas dupliquer l'entité si un module (plugin SEO, intégration) en injecte déjà une : vérifier `grep -rn "ld+json" src/ node_modules/<module>` et n'en garder qu'une source.
- Pas d'avis ni de notes inventés (`aggregateRating`) : Google le sanctionne et ce serait faux.
- Retour arrière : retirer l'appel à `<JsonLd>` dans le layout.

## Pour aller plus loin

- https://developers.google.com/search/docs/appearance/structured-data/organization : propriétés Organization que Google lit.
- https://developers.google.com/search/docs/appearance/structured-data/local-business : LocalBusiness.
- https://schema.org/Organization : vocabulaire et sous-types.
- https://validator.schema.org/ : validateur.
- https://docs.astro.build/en/reference/directives-reference/ : `set:html` et `is:inline`.
