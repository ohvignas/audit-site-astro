---
id: geo-entite-doublons-nom-marque
titre: Nom de marque incohérent ou entités déclarées en double (JSON-LD + Microdata)
domaine: GEO / IA
severite_type: moyenne
effort: S
declencheurs:
  - "geo:Nom de marque incohérent"
  - "geo:Microdata \\(souvent Astra\\)"
sources:
  - https://developers.google.com/search/docs/appearance/site-names
  - https://developers.google.com/search/docs/appearance/structured-data/organization
  - https://schema.org/alternateName
  - https://docs.astro.build/en/reference/directives-reference/
---

# Nom de marque incohérent ou entités en double

> **En une phrase** : la marque s'écrit de plusieurs façons selon les balises (JSON-LD, `og:site_name`, titres, pied de page), ou est déclarée deux fois (JSON-LD et Microdata) ; les moteurs et les IA risquent de la traiter comme deux entités.

## Pourquoi c'est important

Les assistants IA agrègent les informations par nom. Si le JSON-LD dit « Exemple SAS », `og:site_name` « exemple.fr » et le pied de page « Exemple Agency », le recoupement avec les avis, annuaires et articles de presse se fait moins bien. Google demande aussi un nom de site cohérent (`WebSite` + `og:site_name`, `alternateName` pour une variante) pour son affichage. Le doublon Microdata + JSON-LD vient souvent d'un thème ou d'un plugin importé d'un ancien site (le message cite Astra/WordPress) : deux blocs qui décrivent la même entité avec des valeurs différentes créent des contradictions.

## Comment le constater soi-même

```bash
# Toutes les variantes du nom sur l'accueil
curl -s https://SITE/ | grep -oiE '<meta[^>]*og:site_name[^>]*>|<title>[^<]*</title>|"name": ?"[^"]*"' | sort -u
# Microdata présent ?
curl -s https://SITE/ | grep -oE 'itemscope|itemtype="[^"]+"' | sort | uniq -c
grep -rn "itemscope\|itemtype" src/ | head
```

Problème présent : plusieurs graphies (majuscules, avec/sans forme juridique, domaine vs nom), ou `itemscope` en plus d'un bloc `ld+json`. Corrigé : un seul nom partout, une seule technique de balisage.

## Correction

1. Décider **avec le propriétaire** de la graphie officielle (ex. « Exemple ») et d'une éventuelle variante (« Exemple SAS », sigle) qui ira dans `alternateName`.
2. Centraliser dans `src/lib/entite.ts` (voir `geo-entite-organization-jsonld`) et remplacer toutes les occurrences en dur :

```ts
// src/lib/entite.ts (extrait)
export const ENTITE = {
  nom: 'Exemple',
  nomAlternatif: ['Exemple SAS'],
  // ...
};
```

3. Utiliser cette source unique dans le layout : `og:site_name`, suffixe du titre, JSON-LD `Organization` et `WebSite`, pied de page.

```astro
---
// src/layouts/Base.astro (extrait)
import { ENTITE } from '../lib/entite';
const { titre } = Astro.props;
const titreComplet = `${titre} | ${ENTITE.nom}`;
---
<head>
  <title>{titreComplet}</title>
  <meta property="og:site_name" content={ENTITE.nom} />
</head>
<footer>© {new Date().getFullYear()} {ENTITE.nom}</footer>
```

   Et dans le JSON-LD : `name: ENTITE.nom`, `alternateName: ENTITE.nomAlternatif` sur `WebSite` (propriété documentée par Google pour le nom de site) et sur `Organization`.
4. Rechercher les restes : `grep -rniE "ancien nom|autre graphie" src/ public/ convex/` sur les graphies obsolètes ; corriger aussi les contenus Markdown/MDX, `manifest`, flux RSS, e-mails, `llms.txt`.
5. **Doublon Microdata + JSON-LD** : choisir JSON-LD (plus simple à maintenir), supprimer les attributs `itemscope`, `itemtype`, `itemprop` des composants/thèmes fautifs, ou désactiver le module qui les injecte. Ne pas laisser les deux décrire la même entité avec des valeurs différentes.
6. Hors site (à traiter avec le propriétaire, pas dans le code) : aligner le nom sur les profils (LinkedIn, Google Business Profile, annuaires).

## Critères d'acceptation

- [ ] Une seule graphie de la marque dans `Organization.name`, `WebSite.name`, `og:site_name`, `<title>` (suffixe) et pied de page
- [ ] Les variantes officielles sont dans `alternateName`, pas dispersées
- [ ] Plus de page qui cumule `itemscope` et JSON-LD pour la même entité
- [ ] Aucune régression : les titres restent lisibles, build OK

## Vérification après correction

```bash
curl -s https://SITE/ | grep -oiE '<meta[^>]*og:site_name[^>]*>|"name": ?"[^"]*"' | sort -u
curl -s https://SITE/ | grep -c 'itemscope'
python3 scripts/geo_check.py https://SITE/ --out /tmp/verif/geo --sample 8
grep -iE 'incohérent|microdata' /tmp/verif/geo/geo-summary.md
```

## Pièges et retour arrière

- Le signal compare **tous les noms d'entité** (Organization, WebSite, sous-types locaux) et `og:site_name` : le nom d'une `Person`, d'un `Product` ou d'un produit n'entre pas en compte, mais un `WebSite.name` différent, si.
- La casse compte (« exemple » ≠ « Exemple ») : uniformiser.
- Ne pas renommer légalement la marque dans les mentions légales (raison sociale) : y garder la forme juridique exacte.
- Retour arrière : Git ; les changements sont textuels.

## Pour aller plus loin

- https://developers.google.com/search/docs/appearance/site-names : nom de site, `WebSite`, `alternateName`.
- https://developers.google.com/search/docs/appearance/structured-data/organization : propriétés Organization.
- https://schema.org/alternateName : variantes de nom.
- https://docs.astro.build/en/reference/directives-reference/ : `set:html`, `is:inline` pour le JSON-LD.
