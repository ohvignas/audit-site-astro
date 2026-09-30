---
id: contenu-eeat-preuves
titre: Contenu sans preuves d'expertise (auteurs, formateurs, chiffres, avis)
domaine: Contenu
severite_type: moyenne
effort: L
declencheurs:
  - "geo:Articles sans auteur identifiable"
sources:
  - https://developers.google.com/search/docs/fundamentals/creating-helpful-content
  - https://developers.google.com/search/docs/appearance/structured-data/review-snippet
  - https://schema.org/Person
  - https://docs.astro.build/en/guides/content-collections/
---

# Contenu sans preuves d'expertise (auteurs, formateurs, chiffres, avis)

> **En une phrase** : les pages affirment sans montrer qui parle, quelle expérience il a et sur quelles preuves, ce que Google (E-E-A-T) et les IA récompensent de plus en plus.

## Pourquoi c'est important

E-E-A-T signifie expérience, expertise, autorité, fiabilité. Ce n'est pas un score mesurable, c'est la grille qu'utilisent les évaluateurs de Google et que reprennent les IA pour choisir leurs sources. Google invite à se demander : qui a écrit ce contenu, quelle est son expérience directe du sujet, y a-t-il des preuves (chiffres sourcés, cas concrets, méthodes) ? Une page formation qui n'indique ni le formateur, ni son parcours, ni le taux de réussite, ni un avis vérifiable est interchangeable avec mille autres. La fiche `geo-articles-auteur-date-maj` traite le balisage technique (auteur et dates dans le JSON-LD) ; celle-ci traite le fond éditorial. Le signal `Articles sans auteur identifiable` de l'outil ne mesure que la présence d'un auteur ; le reste (preuves, avis, parcours) se juge en lisant les pages.

## Comment le constater soi-même

Lire une page formation, une page service et un article, en se posant 6 questions :

1. Le nom de la personne qui parle est-il affiché, avec son parcours ?
2. Y a-t-il au moins un chiffre vérifiable et sourcé (durée d'activité, nombre de stagiaires, taux de réussite, année) ?
3. Y a-t-il un cas concret, un exemple client, une capture, une réalisation ?
4. Les certifications sont-elles nommées avec leur numéro ou lien de vérification (Qualiopi, RNCP ou RS, éditeur) ?
5. Les avis sont-ils datés, attribués et vérifiables (source externe) ?
6. Un visiteur sait-il où joindre une vraie personne ?

```bash
curl -s https://SITE/formations/excel/ | grep -ciE 'formateur|certifi|qualiopi|avis|témoignage|taux de réussite'
ls src/pages | grep -iE "equipe|formateur|auteur"
```

Zéro occurrence sur une page business = manque de preuves.

## Correction

1. **Récolter les faits auprès du propriétaire** : parcours et années d'expérience de chaque formateur ou consultant, chiffres réels (avec période et source), certifications, exemples clients autorisés. Ne jamais inventer un chiffre, un avis, un diplôme ou une photo : c'est trompeur et contraire aux règles de Google sur les contenus et les avis.
2. **Fiches personnes** dans une collection (`src/content/equipe/*.md`) :

```ts
// src/content.config.ts (extrait ; Astro 6+ : z vient de 'astro/zod', sur Astro 5 : de 'astro:content')
import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const equipe = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/equipe' }),
  schema: ({ image }) => z.object({
    nom: z.string(),
    poste: z.string(),
    photo: image(),
    photoAlt: z.string(),
    experienceAnnees: z.number().int().positive().optional(),
    certifications: z.array(z.string()).default([]),
    linkedin: z.string().url().optional(),
  }),
});
export const collections = { equipe };
```

   Page `/equipe/<slug>/` : photo, parcours en 3 à 6 lignes, spécialités, formations ou articles associés (liens internes), lien LinkedIn. En Convex : table `equipe` avec les mêmes champs (`nom`, `poste`, `bio`, `linkedin`, `photoAlt`).
3. **Encadré « auteur » et « formateur » sur chaque page** : nom cliquable vers sa fiche, en une ligne (« Animée par Prénom Nom, formatrice depuis 12 ans »), uniquement avec des données réelles.
4. **Preuves chiffrées et cas** : ajouter à chaque page business au moins un bloc de preuve : chiffre daté et sourcé (forme attendue, chiffres fictifs : « X % de stagiaires satisfaits en 2025, enquête interne sur N réponses »), ou étude de cas courte (contexte, action, résultat). Les données viennent du propriétaire.
5. **Certifications** : nom exact, organisme, numéro ou lien de vérification, date (par exemple mention Qualiopi avec la catégorie d'action, RNCP ou RS avec l'intitulé et le code). Un logo sans lien de vérification pèse peu.
6. **Avis** : reprendre des avis réels avec prénom, contexte et date, idéalement d'une plateforme tierce avec lien. Ne pas baliser des avis rédigés par le site lui-même pour l'afficher en étoiles : Google n'affiche pas ces extraits pour un avis sur sa propre organisation.
7. **Ne pas rendre l'auteur décoratif** : un « Rédaction » anonyme ou une photo libre de droits présentée comme le formateur nuit à la fiabilité.

## Critères d'acceptation

- [ ] Chaque page formation, service et article nomme son auteur ou intervenant, avec lien vers une fiche détaillée.
- [ ] Chaque page business contient au moins un élément de preuve réel (chiffre sourcé, cas, avis vérifiable, certification avec référence).
- [ ] Aucun chiffre, avis ou diplôme inventé ; chaque donnée est validée par le propriétaire.
- [ ] Les photos ont un `alt` descriptif (voir `contenu-textes-alternatifs`).
- [ ] Build OK.

## Vérification après correction

```bash
npx astro check && npx astro build
python3 scripts/geo_check.py https://SITE/ --out /tmp/verif/geo --crawl /tmp/verif/crawl/pages.json
grep -iE 'sans auteur' /tmp/verif/geo/geo-summary.md     # ne doit rien renvoyer
```

Relecture humaine : refaire les 6 questions sur 3 pages.

## Pièges et retour arrière

- Un chiffre non sourcé ou obsolète nuit plus qu'il ne sert : dater chaque chiffre et prévoir une revue annuelle.
- Le champ `certifications` ou `photo` obligatoire dans le schéma fait échouer le build s'il manque : le mettre `optional()` le temps de la collecte.
- Retirer un profil d'équipe casse les liens internes qui y pointent : contrôler avec `grep -rn "/equipe/" src`.
- Retour arrière : `git revert` ; les documents Convex ajoutés peuvent être laissés en place.

## Pour aller plus loin

- https://developers.google.com/search/docs/fundamentals/creating-helpful-content : les questions de Google sur le « qui, comment, pourquoi » et l'expertise.
- https://developers.google.com/search/docs/appearance/structured-data/review-snippet : règles sur les avis (pas d'avis auto-attribués).
- https://schema.org/Person : décrire une personne (nom, poste, sameAs).
- https://docs.astro.build/en/guides/content-collections/ : collections et schémas.
